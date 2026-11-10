/**
 * `<vql-widget>` against a real stack: gato, the control plane and an agent.
 * Opt in with the `VQL_E2E_*` variables (see `stack.ts`); without them every
 * test here is skipped. Run it with `npm run test:live`.
 */

import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { type Browser, type Page, expect, test } from "@playwright/test";
import {
  botText,
  closePage,
  canSpeak,
  configured,
  dump,
  engine,
  env,
  events,
  grantMic,
  launch,
  now,
  openPage,
  prepareAudio,
  sessionId,
  speak,
  stats,
  takeOpened,
  waitForEvent,
} from "./stack.js";

test.skip(!configured, "set VQL_E2E_STACK, VQL_E2E_AGENT and VQL_E2E_KEY to run against a stack");

let browser: Browser;
test.beforeAll(async () => {
  const { noise } = prepareAudio();
  browser = await launch(noise);
});
test.afterAll(async () => {
  await browser?.close();
});
test.beforeEach(() => {
  takeOpened();
});
test.afterEach(async ({}, info) => {
  // A failed test keeps every page's wire and console, for the flake log.
  const pages = takeOpened();
  if (info.status === info.expectedStatus) return;
  const slug = info.title.replace(/[^a-z0-9]+/gi, "-").slice(0, 60);
  for (const [i, page] of pages.entries()) await dump(page, `FAILED-${slug}-${i}-retry${info.retry}`).catch(() => {});
});

/** The tone's first note, in Hz; see `src/session/tone.ts`. */
const TONE_FIRST_NOTE = 880;
const isTone = (e: { dir: string; type: string; data?: unknown }) =>
  e.dir === "tone" && (e.data as { frequency: number }).frequency === TONE_FIRST_NOTE;
/** A client message about the mic: the widget sends none. */
const isMicMessage = (e: { dir: string; type: string; data?: unknown }) =>
  e.dir === "out" && e.type === "client-message" && /mic/i.test(String((e.data as { t?: string })?.t ?? ""));

async function startCall(page: Page): Promise<number> {
  const launcher = page.locator("vql-widget vql-launcher").first();
  await launcher.waitFor();
  await launcher.click();
  const clicks = (await events(page)).filter((e) => e.type === "click");
  return clicks.at(-1)?.t ?? 0;
}

async function hangUp(page: Page): Promise<void> {
  await page.evaluate(() => (document.querySelector("vql-widget") as unknown as { end(): Promise<void> }).end());
}

async function shot(page: Page, name: string): Promise<void> {
  mkdirSync(env.out, { recursive: true });
  await page.screenshot({ path: join(env.out, `${name}.png`) });
}

test("denied: the call connects and greets, the widget asks for the mic and beeps; allowing it picks it up with no renegotiation", async () => {
  test.setTimeout(120_000);
  test.skip(!canSpeak, "the spoken turn needs macOS say");
  const { page } = await openPage(browser, { granted: false, attributes: { "alert-tone": "true" } });
  try {
    await startCall(page);
    await waitForEvent(page, (e) => e.dir === "mic" && e.type === "getusermedia-error");
    await waitForEvent(page, (e) => e.dir === "ui" && e.type === "vql-mic" && (e.data as { state: string }).state === "blocked");
    await waitForEvent(page, (e) => e.dir === "in" && e.type === "bot-ready");
    // The greeting plays: its words arrive.
    await waitForEvent(page, (e) => e.dir === "in" && e.type === "bot-started-speaking");
    await waitForEvent(page, (e) => botText(e).length > 0);
    // When it ends, the tone sounds.
    const stopped = await waitForEvent(page, (e) => e.dir === "in" && e.type === "bot-stopped-speaking", 30_000);
    const tone = await waitForEvent(page, isTone, 5_000, stopped.t);
    await expect(page.locator("vql-widget vql-coach")).toBeVisible();
    // The pill says what the mic needs, and the dock's polite region says it too.
    await expect(page.locator("vql-widget vql-mic-pill[kind=permission]")).toBeVisible();
    await expect(page.locator("vql-widget vql-mic-pill")).toContainText("Grant mic permission");
    await expect(page.locator("vql-widget .mic-said")).toHaveText("Grant mic permission");
    await shot(page, "denied-coach");

    // Allow it from the "address bar".
    const before = (await events(page)).filter((e) => e.dir === "pc" && (e.type === "create-offer" || e.type === "set-local"));
    const grantAt = await now(page);
    await grantMic(page);
    // WebKit tells the page nothing when the permission changes, and Safari
    // reads "prompt" after a refusal: the visitor taps the pill, which asks
    // again. Chromium picks the grant up by itself.
    if (engine === "webkit") await page.locator("vql-widget vql-mic-pill button").click();
    await waitForEvent(page, (e) => e.dir === "ui" && e.type === "vql-mic" && (e.data as { state: string }).state === "live", 15_000, grantAt);
    await expect(page.locator("vql-widget vql-coach")).toHaveCount(0);
    // Granted: the pill goes, and the region falls silent.
    await expect(page.locator("vql-widget vql-mic-pill[kind]")).toHaveCount(0);
    await expect(page.locator("vql-widget .mic-said")).toHaveText("");
    await shot(page, "granted-no-pill");

    // The agent hears a spoken turn.
    await page.waitForTimeout(1500);
    const spoke = await speak(page, "open_dubai");
    const heard = await waitForEvent(
      page,
      (e) => e.dir === "in" && e.type === "user-transcription" && Boolean((e.data as { final?: boolean }).final),
      20_000,
      spoke.startedAt,
    );
    expect(String((heard.data as { text: string }).text)).toMatch(/dubai/i);

    // No renegotiation: no new offer, no new m-line, no new offer request.
    const all = await events(page);
    const after = all.filter((e) => e.t >= grantAt);
    const offersAfter = after.filter((e) => e.dir === "pc" && (e.type === "create-offer" || e.type === "set-local"));
    const signalling = after.filter((e) => e.type.startsWith("signalling:"));
    const requests = after.filter((e) => e.dir === "net" && /offer/.test(String((e.data as { path: string }).path)));
    test.info().annotations.push(
      { type: "tone", description: `${tone.t - stopped.t} ms after the greeting ended` },
      { type: "offers before grant", description: JSON.stringify(before.map((e) => e.data)) },
      { type: "after grant", description: JSON.stringify({ offers: offersAfter.length, signalling: signalling.map((e) => e.type), requests: requests.length, replaceTrack: after.filter((e) => e.type === "replace-track").map((e) => e.data) }) },
    );
    expect(offersAfter, "allowing the mic renegotiated").toHaveLength(0);
    expect(requests, "allowing the mic sent an offer request").toHaveLength(0);
    expect(signalling.filter((e) => /offer|renegotiat/i.test(e.type)), "allowing the mic renegotiated over the channel").toHaveLength(0);

    // The mic stayed in the browser: nothing about it went to the agent.
    expect(all.filter(isMicMessage), "the widget sent a mic message").toEqual([]);
    // Live before the second tone was due: it never played.
    await page.waitForTimeout(Math.max(0, tone.t + 8_500 - (await now(page))));
    expect((await events(page)).filter(isTone), "the tone played again with the mic live").toHaveLength(1);

    const id = await sessionId(page);
    await hangUp(page);
    expect(id).toBeTruthy();
  } finally {
    await dump(page, "denied-then-granted").catch(() => {});
    await closePage(page);
  }
});

// ------------------------------------------------------------ connect time

interface Timing {
  instant: boolean;
  botReady: number;
  agentSpeaking: number;
  firstAudio: number;
}

const timings: Timing[] = [];

/** A call whose speech tier refused it, which is the stack's fault and not the widget's. */
class SpeechRefused extends Error {}

async function timeOneCall(instant: boolean): Promise<Timing> {
  const { page } = await openPage(browser, { granted: true, attributes: { "instant-start": String(instant) } });
  try {
    const clickAt = await startCall(page);
    const refused = waitForEvent(page, (e) => e.dir === "in" && e.type === "error" && /synth/.test(JSON.stringify(e.data)), 25_000)
      .then((e) => {
        throw new SpeechRefused(JSON.stringify(e.data));
      })
      .catch((e: unknown) => {
        if (e instanceof SpeechRefused) throw e;
        return new Promise<never>(() => {});
      });
    const ready = await waitForEvent(page, (e) => e.dir === "in" && e.type === "bot-ready", 20_000);
    const speaking = await Promise.race([
      waitForEvent(page, (e) => e.dir === "in" && e.type === "bot-started-speaking", 20_000),
      refused,
    ]);
    let firstAudio = -1;
    for (let i = 0; i < 50 && firstAudio < 0; i++) {
      const hit = (await stats(page)).find((s) => s.inEnergy > 1e-6);
      if (hit) firstAudio = hit.t;
      else await page.waitForTimeout(100);
    }
    await hangUp(page);
    return { instant, botReady: ready.t - clickAt, agentSpeaking: speaking.t - clickAt, firstAudio: firstAudio - clickAt };
  } finally {
    await closePage(page);
  }
}

test("granted: time from the click to the agent's first audio, instant start on and off", async () => {
  const rounds = Number(process.env.VQL_E2E_ROUNDS ?? 3);
  test.setTimeout(60_000 * rounds);
  for (let i = 0; i < rounds; i++) {
    // Alternate, so a slow minute on the stack falls on both.
    for (const instant of [true, false]) {
      try {
        timings.push(await timeOneCall(instant));
      } catch (error) {
        if (!(error instanceof SpeechRefused)) throw error;
        // Logged as a flake, then the call is made again: the shared speech tier said it was full.
        test.info().annotations.push({ type: "flake: speech tier refused the call", description: error.message });
        timings.push(await timeOneCall(instant));
      }
    }
  }
  mkdirSync(env.out, { recursive: true });
  writeFileSync(join(env.out, "connect-times.json"), JSON.stringify(timings, null, 1));
  const median = (xs: number[]) => [...xs].sort((a, b) => a - b)[Math.floor(xs.length / 2)] ?? -1;
  for (const instant of [true, false]) {
    const of = timings.filter((t) => t.instant === instant);
    test.info().annotations.push({
      type: `instant ${instant ? "on" : "off"}`,
      description: `median click→first audio ${median(of.map((t) => t.firstAudio))} ms, click→bot-started-speaking ${median(of.map((t) => t.agentSpeaking))} ms, click→bot-ready ${median(of.map((t) => t.botReady))} ms; runs ${JSON.stringify(of.map((t) => t.firstAudio))}`,
    });
  }
  for (const t of timings) expect(t.firstAudio, "no agent audio reached the browser").toBeGreaterThan(0);
});

// ---------------------------------------------------------------- captions

interface CaptionsView {
  visible: boolean;
  words: { text: string; spoken: boolean }[];
}

const readCaptions = (page: Page): Promise<CaptionsView> =>
  page.evaluate(() => {
    const host = document.querySelector("vql-widget")?.shadowRoot?.querySelector("vql-captions");
    const root = host?.shadowRoot;
    const block = root?.querySelector("[part=captions]");
    const words = [...(root?.querySelectorAll("span.word") ?? [])].map((w) => ({
      text: w.textContent ?? "",
      spoken: w.classList.contains("spoken"),
    }));
    return { visible: Boolean(block && !block.classList.contains("hidden")), words };
  });

test("captions: karaoke words light as the greeting plays, and clear after it", async () => {
  test.setTimeout(60_000);
  const { page } = await openPage(browser, { granted: true, attributes: { captions: "karaoke" } });
  try {
    await startCall(page);
    await waitForEvent(page, (e) => e.dir === "in" && e.type === "bot-started-speaking", 20_000);
    const samples: { t: number; spoken: number; total: number; visible: boolean }[] = [];
    for (;;) {
      const c = await readCaptions(page);
      samples.push({ t: await now(page), spoken: c.words.filter((w) => w.spoken).length, total: c.words.length, visible: c.visible });
      if ((await events(page)).some((e) => e.dir === "in" && e.type === "bot-stopped-speaking")) break;
      await page.waitForTimeout(150);
      if (samples.length > 200) break;
    }
    await shot(page, "captions-karaoke");
    const spokenCounts = samples.map((s) => s.spoken);
    const distinct = new Set(spokenCounts.filter((n) => n > 0));
    test.info().annotations.push({ type: "spoken words over time", description: JSON.stringify(spokenCounts) });
    expect(distinct.size, "the lit words never advanced").toBeGreaterThan(2);
    for (let i = 1; i < spokenCounts.length; i++) {
      // Lit words only go forward within a line; a line rolling off may drop the count.
      if ((spokenCounts[i] as number) < (spokenCounts[i - 1] as number)) {
        expect(samples[i]?.total ?? 0, "lit words went back on the same line").toBeLessThan(samples[i - 1]?.total ?? 0);
      }
    }
    // After the agent stops, the block clears once its linger (4 s) is over.
    await expect.poll(async () => (await readCaptions(page)).words.length, { timeout: 8_000 }).toBe(0);
    await hangUp(page);
    await dump(page, "captions-karaoke");
  } finally {
    await closePage(page);
  }
});

test("captions: a barge-in cuts the line where the agent stopped", async () => {
  test.setTimeout(60_000);
  test.skip(!canSpeak, "the barge-in needs macOS say");
  const { page } = await openPage(browser, { granted: true, attributes: { captions: "karaoke" } });
  try {
    await startCall(page);
    await waitForEvent(page, (e) => e.dir === "in" && e.type === "bot-started-speaking", 20_000);
    const greeting = String(((await waitForEvent(page, (e) => e.dir === "in" && e.type === "bot-transcription")).data as { text: string }).text);
    await waitForEvent(page, (e) => e.dir === "in" && e.type === "bot-tts-text", 10_000);
    await page.waitForTimeout(600);
    const before = await readCaptions(page);
    const said = speak(page, "hold_on");
    const cut = await waitForEvent(page, (e) => e.dir === "in" && (e.type === "bot-interrupted" || e.type === "bot-stopped-speaking"), 10_000);
    await page.waitForTimeout(200);
    const after = await readCaptions(page);
    await shot(page, "captions-barge-in");
    await said;
    test.info().annotations.push(
      { type: "greeting", description: greeting },
      { type: "before the cut", description: JSON.stringify(before) },
      { type: "after the cut", description: JSON.stringify(after) },
      { type: "cut by", description: cut.type },
    );
    expect(after.words.length, "captions vanished at the cut instead of lingering").toBeGreaterThan(0);
    expect(after.words.every((w) => w.spoken), "words the agent never spoke stayed on screen").toBe(true);
    expect(after.words.length, "the line was not cut").toBeLessThan(greeting.split(/\s+/).length);
    await hangUp(page);
    await dump(page, "captions-barge-in");
  } finally {
    await closePage(page);
  }
});

// ---------------------------------------------------------------------- UI

test("UI: collapse, expand, place and snap in a call", async () => {
  test.setTimeout(60_000);
  const { page } = await openPage(browser, { granted: true });
  try {
    await startCall(page);
    await waitForEvent(page, (e) => e.dir === "in" && e.type === "bot-started-speaking", 20_000);
    await shot(page, "ui-open");
    const widget = page.locator("vql-widget");
    await expect(widget).toHaveAttribute("view", "open");

    await widget.getByRole("button", { name: "Minimise" }).click();
    await expect(widget).toHaveAttribute("view", "collapsed");
    await shot(page, "ui-collapsed");
    await widget.locator(".expand").first().click();
    await expect(widget).toHaveAttribute("view", "open");

    await page.evaluate(() => (document.querySelector("vql-widget") as unknown as { place(a: string): void }).place("top-left"));
    await waitForEvent(page, (e) => e.dir === "ui" && e.type === "vql-place" && (e.data as { anchor: string }).anchor === "top-left");
    await shot(page, "ui-top-left");

    // Drag it by the face toward the right edge, middle height: snap picks middle-right.
    const face = widget.locator("vql-face").first();
    // The move to top-left animates: press where the face has come to rest.
    let box = await face.boundingBox();
    for (let i = 0; i < 30; i++) {
      await page.waitForTimeout(100);
      const next = await face.boundingBox();
      if (next && box && next.x === box.x && next.y === box.y) break;
      box = next;
    }
    if (!box) throw new Error("no face to drag");
    expect(box.x, "the widget did not move to the left").toBeLessThan(200);
    const vp = page.viewportSize() ?? { width: 1280, height: 800 };
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    for (let i = 1; i <= 10; i++) {
      await page.mouse.move(box.x + ((vp.width - 120 - box.x) * i) / 10, box.y + ((vp.height / 2 - box.y) * i) / 10);
    }
    await page.mouse.up();
    const placed = await waitForEvent(page, (e) => e.dir === "ui" && e.type === "vql-place" && (e.data as { anchor: string }).anchor !== "top-left");
    test.info().annotations.push({ type: "snapped to", description: JSON.stringify(placed.data) });
    expect((placed.data as { anchor: string }).anchor).toBe("middle-right");
    await shot(page, "ui-snapped");
    await hangUp(page);
    await expect(widget).toHaveAttribute("view", "ended");
    await shot(page, "ui-ended");
    await dump(page, "ui-desktop");
  } finally {
    await closePage(page);
  }
});

test("UI: a phone gets the sheet; the dark theme", async () => {
  test.setTimeout(60_000);
  const phone = await openPage(browser, { granted: true, viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  try {
    await startCall(phone.page);
    await waitForEvent(phone.page, (e) => e.dir === "in" && e.type === "bot-started-speaking", 20_000);
    await expect(phone.page.locator("vql-widget")).toHaveAttribute("form", "sheet");
    const overflow = await phone.page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, "the sheet scrolls the page sideways").toBeLessThanOrEqual(0);
    await shot(phone.page, "ui-phone-sheet");
    await hangUp(phone.page);
  } finally {
    await closePage(phone.page);
  }
  const dark = await openPage(browser, { granted: true, colorScheme: "dark" });
  try {
    await startCall(dark.page);
    await waitForEvent(dark.page, (e) => e.dir === "in" && e.type === "bot-started-speaking", 20_000);
    const bg = await dark.page.evaluate(() => {
      const card = document.querySelector("vql-widget")?.shadowRoot?.querySelector(".card");
      return card ? getComputedStyle(card).backgroundColor : "";
    });
    test.info().annotations.push({ type: "dark card background", description: bg });
    const [r, g, b] = (bg.match(/\d+/g) ?? []).map(Number);
    expect((r ?? 255) + (g ?? 255) + (b ?? 255), "the card is not dark under a dark scheme").toBeLessThan(3 * 100);
    await shot(dark.page, "ui-dark");
    await hangUp(dark.page);
  } finally {
    await closePage(dark.page);
  }
});

// ------------------------------------------------------------ mic_denied end

test("denied and never allowed: the agent's idle rule ends the call, and the widget says to allow the mic", async () => {
  test.skip(!process.env.VQL_E2E_SLOW, "waits out the agent's idle window; set VQL_E2E_SLOW=1");
  test.setTimeout(9 * 60_000);
  const { page } = await openPage(browser, { granted: false, attributes: { "alert-tone": "true" } });
  try {
    await startCall(page);
    await waitForEvent(page, (e) => e.dir === "ui" && e.type === "vql-mic" && (e.data as { state: string }).state === "blocked", 20_000);
    const end = await waitForEvent(page, (e) => e.dir === "ui" && e.type === "vql-end", 8 * 60_000);
    expect((end.data as { reason: string }).reason).toBe("mic_denied");
    await expect(page.locator("vql-widget")).toContainText("Allow your microphone and start again");
    // The first tone, and the one after it; never a third.
    expect((await events(page)).filter(isTone)).toHaveLength(2);
    await shot(page, "mic-denied-end");
    await dump(page, "mic-denied-end");
  } finally {
    await closePage(page);
  }
});
