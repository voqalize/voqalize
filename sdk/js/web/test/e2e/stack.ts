/**
 * The live suite's harness: the page, the browser, the audio and the stack's
 * session logs. Nothing here holds a key: the agent, the publishable key and
 * the stack come from the environment at run time.
 *
 *   VQL_E2E_STACK         the origin the page is served on, one the key allows
 *                         (for local: https://local.voqalize.com)
 *   VQL_E2E_API           the API base (default: the stack's /api/v1)
 *   VQL_E2E_AGENT         the agent to call
 *   VQL_E2E_KEY           its publishable key
 *   VQL_E2E_SESSION_LOGS  optional: the directory gato's session logs land in
 *                         (local: platform/.local-gcs/local-session-logs)
 *   VQL_E2E_OUT           optional: where screenshots and wire dumps go
 */

import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { platform } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { gunzipSync } from "node:zlib";
import { type Browser, type BrowserContext, type Page, chromium, webkit } from "@playwright/test";
import { build } from "esbuild";
import { type ProbeEvent, type ProbeStat, installProbe } from "./probe.js";

const here = fileURLToPath(new URL(".", import.meta.url));

export const env = {
  stack: process.env.VQL_E2E_STACK ?? "",
  api: process.env.VQL_E2E_API ?? (process.env.VQL_E2E_STACK ? `${process.env.VQL_E2E_STACK}/api/v1` : ""),
  agent: process.env.VQL_E2E_AGENT ?? "",
  key: process.env.VQL_E2E_KEY ?? "",
  sessionLogs: process.env.VQL_E2E_SESSION_LOGS ?? "",
  out: process.env.VQL_E2E_OUT ?? join(here, "..", "..", "test-results", "e2e"),
};

export const configured = Boolean(env.stack && env.agent && env.key);

/** The engine the suite runs in: Chromium unless `VQL_BROWSER` says `webkit`. */
export const engine: "chromium" | "webkit" = process.env.VQL_BROWSER === "webkit" ? "webkit" : "chromium";

/** Where generated audio goes: build output, never checked in. */
const audioDir = join(here, "..", "..", "test-results", "e2e-audio");

/** The clips the suite speaks, in the Travel Desk's language. */
export const CLIPS = {
  open_dubai: "Open the Dubai trip.",
  hold_on: "Hold on, hold on, wait a moment please.",
} as const;
export type ClipName = keyof typeof CLIPS;

/** A low noise bed for the fake device, so the mic is never digital silence. */
function writeNoise(path: string): void {
  const rate = 48000;
  const seconds = 20;
  const samples = rate * seconds;
  const data = Buffer.alloc(samples * 2);
  let seed = 7;
  for (let i = 0; i < samples; i++) {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    data.writeInt16LE(Math.round(((seed / 0x7fffffff) * 2 - 1) * 40), i * 2);
  }
  const header = Buffer.alloc(44);
  header.write("RIFF", 0);
  header.writeUInt32LE(36 + data.length, 4);
  header.write("WAVEfmt ", 8);
  header.writeUInt32LE(16, 16);
  header.writeUInt16LE(1, 20);
  header.writeUInt16LE(1, 22);
  header.writeUInt32LE(rate, 24);
  header.writeUInt32LE(rate * 2, 28);
  header.writeUInt16LE(2, 32);
  header.writeUInt16LE(16, 34);
  header.write("data", 36);
  header.writeUInt32LE(data.length, 40);
  writeFileSync(path, Buffer.concat([header, data]));
}

export const canSpeak = platform() === "darwin";

/** Make the noise bed and the spoken clips (macOS `say`), once. */
export function prepareAudio(): { noise: string } {
  mkdirSync(audioDir, { recursive: true });
  const noise = join(audioDir, "noise.wav");
  if (!existsSync(noise)) writeNoise(noise);
  if (canSpeak) {
    for (const [name, text] of Object.entries(CLIPS)) {
      const wav = join(audioDir, `${name}.wav`);
      if (existsSync(wav)) continue;
      const aiff = join(audioDir, `${name}.aiff`);
      execFileSync("say", ["-v", "Rishi", "-r", "165", "-o", aiff, text]);
      execFileSync("afconvert", ["-f", "WAVE", "-d", "LEI16@16000", "-c", "1", aiff, wav]);
    }
  }
  return { noise };
}

export function clip(name: ClipName): string {
  return readFileSync(join(audioDir, `${name}.wav`)).toString("base64");
}

let bundled: Uint8Array | null = null;
async function pageBundle(): Promise<Uint8Array> {
  if (bundled) return bundled;
  const result = await build({
    entryPoints: [join(here, "page.ts")],
    bundle: true,
    format: "esm",
    target: "es2022",
    write: false,
    conditions: ["production"],
    define: { "process.env.NODE_ENV": '"production"' },
    logLevel: "silent",
  });
  bundled = (result.outputFiles[0] as { contents: Uint8Array }).contents;
  return bundled;
}

/**
 * Chromium with a fake capture device and no fake prompt: a mic request the
 * permission has not allowed is refused, as a visitor's "Block" is, and a
 * grant through CDP later lets the next request through.
 */
export async function launch(noise: string): Promise<Browser> {
  // WebKit, the engine Safari is built on (`VQL_BROWSER=webkit`): its capture
  // is a mock device, and a mic it has not been granted is refused.
  if (engine === "webkit") return webkit.launch();
  return chromium.launch({
    channel: "chromium",
    args: [
      "--use-fake-device-for-media-stream",
      `--use-file-for-fake-audio-capture=${noise}`,
      "--autoplay-policy=no-user-gesture-required",
      // The page is served by the test, so Chromium cannot place it in an
      // address space and refuses its requests to a stack on loopback.
      "--disable-features=LocalNetworkAccessChecks",
    ],
  });
}

export interface OpenOptions {
  /** Allow the mic before the page loads. Default false: the prompt is refused. */
  granted?: boolean;
  attributes?: Record<string, string>;
  viewport?: { width: number; height: number };
  colorScheme?: "light" | "dark";
  isMobile?: boolean;
  hasTouch?: boolean;
}

const consoleLines = new WeakMap<Page, string[]>();

/** The pages opened since the last `takeOpened()`, so a test's wire can be kept when it fails. */
let opened: Page[] = [];
export function takeOpened(): Page[] {
  const pages = opened;
  opened = [];
  return pages;
}

export async function openPage(browser: Browser, options: OpenOptions = {}): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({
    viewport: options.viewport ?? { width: 1280, height: 800 },
    colorScheme: options.colorScheme ?? "light",
    isMobile: options.isMobile ?? false,
    hasTouch: options.hasTouch ?? false,
  });
  if (options.granted) await context.grantPermissions(["microphone"], { origin: env.stack });
  const js = await pageBundle();
  const html = readFileSync(join(here, "index.html"));
  await context.route(`${env.stack}/__vql-e2e/**`, (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/page.js")) return route.fulfill({ body: Buffer.from(js), contentType: "text/javascript" });
    return route.fulfill({ body: html, contentType: "text/html" });
  });
  await context.addInitScript(installProbe);
  await context.addInitScript(
    (c) => {
      (window as unknown as { __vqlE2EConfig: unknown }).__vqlE2EConfig = c;
    },
    { agent: env.agent, key: env.key, api: env.api, attributes: options.attributes ?? {} },
  );
  const page = await context.newPage();
  const lines: string[] = [];
  consoleLines.set(page, lines);
  opened.push(page);
  page.on("console", (m) => lines.push(`${m.type()}: ${m.text()}`.slice(0, 2000)));
  page.on("pageerror", (e) => lines.push(`pageerror: ${e.message}`));
  await page.goto(`${env.stack}/__vql-e2e/`);
  await page.locator("vql-widget").waitFor({ state: "attached" });
  return { context, page };
}

/**
 * Allow the mic from the "address bar", as a visitor does after blocking it.
 * The CDP session stays attached: Chromium drops a DevTools permission
 * override when the session that set it detaches.
 */
export async function grantMic(page: Page): Promise<void> {
  if (engine !== "chromium") {
    await page.context().grantPermissions(["microphone"], { origin: env.stack });
    return;
  }
  const cdp = await page.context().newCDPSession(page);
  const { targetInfo } = (await cdp.send("Target.getTargetInfo")) as { targetInfo: { browserContextId: string } };
  await cdp.send("Browser.setPermission", {
    permission: { name: "microphone" },
    setting: "granted",
    origin: env.stack,
    browserContextId: targetInfo.browserContextId,
  });
}

export const events = (page: Page): Promise<ProbeEvent[]> => page.evaluate(() => window.__vqlE2E.events);
export const stats = (page: Page): Promise<ProbeStat[]> => page.evaluate(() => window.__vqlE2E.stats);
export const sessionId = (page: Page): Promise<string | undefined> => page.evaluate(() => window.__vqlE2E.sessionId);
export const now = (page: Page): Promise<number> => page.evaluate(() => window.__vqlE2E.now());

export async function speak(page: Page, name: ClipName): Promise<{ startedAt: number; endedAt: number }> {
  return page.evaluate(([b64, label]) => window.__vqlE2E.speak(b64, label), [clip(name), name] as const);
}

/** Wait for a probe event that matches; returns it. */
export async function waitForEvent(
  page: Page,
  match: (e: ProbeEvent) => boolean,
  timeout = 20_000,
  after = 0,
): Promise<ProbeEvent> {
  const deadline = Date.now() + timeout;
  for (;;) {
    const found = (await events(page)).find((e) => e.t >= after && match(e));
    if (found) return found;
    if (Date.now() > deadline) throw new Error(`timed out waiting for a probe event (${match.toString().slice(0, 160)})`);
    await page.waitForTimeout(100);
  }
}

export const botText = (e: ProbeEvent): string =>
  e.dir === "in" && e.type === "bot-output" ? String((e.data as { text?: string })?.text ?? "") : "";

/** gato's session log for one session, once the stack has written it. */
export async function sessionLog(id: string, timeout = 30_000): Promise<string[] | null> {
  if (!env.sessionLogs) return null;
  const deadline = Date.now() + timeout;
  for (;;) {
    for (const tenant of existsSync(env.sessionLogs) ? readdirSync(env.sessionLogs) : []) {
      const path = join(env.sessionLogs, tenant, id, "logs", "pygato.jsonl.gz");
      if (existsSync(path)) {
        const lines = gunzipSync(readFileSync(path)).toString("utf8").split("\n").filter(Boolean);
        return lines.map((l) => {
          try {
            return String((JSON.parse(l) as { message?: string }).message ?? l);
          } catch {
            return l;
          }
        });
      }
    }
    if (Date.now() > deadline) return [];
    await new Promise((r) => setTimeout(r, 500));
  }
}

const snapshots = new WeakMap<Page, { events: ProbeEvent[]; sessionId?: string }>();

/** Keep the page's wire, then close its context. */
export async function closePage(page: Page): Promise<void> {
  const data = await page
    .evaluate(() => ({ events: window.__vqlE2E.events, sessionId: window.__vqlE2E.sessionId }))
    .catch(() => null);
  if (data) snapshots.set(page, data);
  await page.context().close();
  // Let the call's speech sockets close before the next call dials: back to
  // back, a shared speech tier can answer "at capacity".
  await new Promise((r) => setTimeout(r, Number(process.env.VQL_E2E_GAP_MS ?? 3000)));
}

/** Write a page's wire and console next to the screenshots, for the evidence. */
export async function dump(page: Page, name: string): Promise<void> {
  mkdirSync(env.out, { recursive: true });
  const data =
    snapshots.get(page) ??
    (await page.evaluate(() => ({
      events: window.__vqlE2E.events,
      sessionId: window.__vqlE2E.sessionId,
    })));
  writeFileSync(join(env.out, `${name}.json`), JSON.stringify({ ...data, console: consoleLines.get(page) ?? [] }, null, 1));
}
