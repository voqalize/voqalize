/**
 * The built extension (`VOQALIZE_TEST_BUILD=1`, test/.build/ext) in a headless
 * Chromium whose network is `server.ts`: the saved pages of www.unosalud.cl
 * with the site's real headers, over HTTPS, and nothing else. For the specs
 * of the headers, the adapters and the guards.
 */

import { type BrowserContext, chromium, expect, type Page, test as base, type Worker } from "@playwright/test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { serveSite, type Site } from "./server";

const here = dirname(fileURLToPath(import.meta.url));
const EXT = join(here, ".build", "ext");
export const ORIGIN = "https://www.unosalud.cl";
/** The extension's id, fixed by the manifest's `key`. */
export const EXTENSION_ID = "ohogdknmaklhlnkbcemmhhejadjlfibd";

export interface SiteExt {
  ctx: BrowserContext;
  sw: Worker;
  site: Site;
  /** Open `path` in the first tab and wait for the widget. */
  open(path: string): Promise<Page>;
}

export const test = base.extend<{ ext: SiteExt }>({
  // eslint-disable-next-line no-empty-pattern
  ext: async ({}, use) => {
    const site = await serveSite();
    const dir = mkdtempSync(join(tmpdir(), "unosalud-site-"));
    const ctx = await chromium.launchPersistentContext(dir, {
      channel: "chromium",
      headless: true,
      viewport: { width: 1366, height: 900 },
      locale: "es-CL",
      args: [
        `--disable-extensions-except=${EXT}`,
        `--load-extension=${EXT}`,
        "--use-fake-device-for-media-stream",
        "--use-fake-ui-for-media-stream",
        "--autoplay-policy=no-user-gesture-required",
        ...site.args,
      ],
    });
    const sw = ctx.serviceWorkers()[0] ?? (await ctx.waitForEvent("serviceworker"));
    await use({
      ctx,
      sw,
      site,
      async open(path) {
        const page = ctx.pages()[0] ?? (await ctx.newPage());
        await page.goto(ORIGIN + path, { waitUntil: "domcontentloaded" });
        await page.locator("[data-voqalize=widget] .invite").waitFor({ timeout: 15_000 });
        return page;
      },
    });
    await ctx.close();
    await site.close();
  },
});

export { expect };

interface Outcome {
  event: string;
  payload: Record<string, unknown>;
}

/** Perform an Action on the page as the holder would, through the page's own
 *  console hook; its outcome (`command_done`, `command_failed`, or null). */
export function perform(page: Page, command: string, payload: Record<string, unknown>): Promise<Outcome | null> {
  return page.evaluate(
    ([c, p]) => (window as unknown as { __voqalizeUnosalud: { perform(c: string, p: unknown): Promise<unknown> } }).__voqalizeUnosalud.perform(c, p),
    [command, payload] as const,
  ) as Promise<Outcome | null>;
}

/** What the page's adapter reports (`start`), collected in the page. */
export async function listen(page: Page): Promise<void> {
  await page.evaluate(() => {
    const w = window as unknown as { __events: [string, unknown][]; voqalizeUnosalud: { start(e: (n: string, p: unknown) => void): () => void } };
    w.__events = [];
    w.voqalizeUnosalud.start((n, p) => w.__events.push([n, JSON.parse(JSON.stringify(p))]));
  });
}

export const events = (page: Page, name: string) =>
  page.evaluate((n) => (window as unknown as { __events: [string, unknown][] }).__events.filter(([e]) => e === n).map(([, p]) => p), name) as Promise<
    Record<string, unknown>[]
  >;

export const toHolder = (sw: Worker, msg: Record<string, unknown>) =>
  sw.evaluate((m) => chrome.runtime.sendMessage({ to: "holder", op: "test", ...m }), msg);

/** Make the holder ahead of the press, so a test can stub the microphone. */
export async function makeHolder(sw: Worker): Promise<void> {
  await sw.evaluate(async () => {
    const up = (await chrome.runtime.getContexts({ contextTypes: [chrome.runtime.ContextType.OFFSCREEN_DOCUMENT] })).length > 0;
    if (!up) {
      await chrome.offscreen.createDocument({
        url: "call.html",
        reasons: [chrome.offscreen.Reason.USER_MEDIA, chrome.offscreen.Reason.WEB_RTC],
        justification: "test",
      });
    }
  });
  await expect.poll(async () => ((await toHolder(sw, { what: "status" }).catch(() => null)) as { state?: { status?: string } } | null)?.state?.status ?? null).toBe("idle");
}
