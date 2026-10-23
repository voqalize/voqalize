/**
 * The holder (the offscreen document the call lives in) and the pages that
 * follow it, end to end in the built extension (`VOQALIZE_TEST_BUILD=1`,
 * test/.build/ext): a stand-in call (test/fake-call-client.ts) and a stand-in
 * avatar, pages served at saintgeorge.cl's address, a made-up API, and the
 * school's calendar feed. Headless, no network.
 *
 *   - the port protocol: hello, the call press, the state on every page, the
 *     page's events up the port, mute and End;
 *   - a full page load leaves the call alone, and a move sent while the tab is
 *     loading is made on its next page, once it says hello;
 *   - a link out opens in a tab of its own, through the service worker, and
 *     the calendar is read there, for the page;
 *   - no Saint George's page for 15 s ends the call and closes the holder;
 *   - the microphone permission's branches (granted, denied, prompt answered
 *     in the frame, prompt that needs the tab), with the permission query
 *     stubbed.
 */

import { type BrowserContext, chromium, expect, type Page, test as base, type Worker } from "@playwright/test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const EXT = join(here, ".build", "ext");
const ORIGIN = "https://saintgeorge.cl";
const CALENDAR = "https://calendar.google.com";
const TICKETS = "https://ticketplus.cl";
const API = "https://api.voqalize.test";

const PAGES: Record<string, { body: string; title: string; delay?: number }> = {
  // A page whose parse is held 2 s by a script in its body: what is on screen
  // before DOMContentLoaded is the early shell's.
  "/lento/": {
    title: "Senior",
    body: `<body><header class="single-page-header"><h1>Senior</h1></header><main>
      <h3>Bachillerato Internacional</h3><p>El programa del IB en III y IV medio.</p></main>
      <script src="/slow.js"></script><p>Fin.</p></body>`,
  },
  "/": {
    title: "Saint George's College",
    body: `<body><header class="home-header"><h1>Saint George's College</h1></header><main>
      <section id="comunidad"><h2>Nuestra comunidad</h2><p>Un colegio católico de Santiago.</p></section>
      <section id="valores"><h2>Nuestros valores</h2><p>Respeto, caridad, libertad.</p></section></main></body>`,
  },
  "/unidad/elementary/": {
    title: "Elementary",
    delay: 2500,
    body: `<body><header class="single-page-header"><h1>Elementary</h1></header><main>
      <h3>Nuestros profesores</h3><p>Profesoras y profesores de 1º a 4º básico.</p></main></body>`,
  },
  "/familia/calendario/": {
    title: "Calendario",
    body: `<body><header class="single-page-header"><h1>Calendario</h1></header><main>
      <h3>Calendario escolar</h3><p>Las actividades del año.</p></main></body>`,
  },
};

/** The calendar's feed: one event far ahead, so it is always to come. */
const ICS = [
  "BEGIN:VCALENDAR", "VERSION:2.0", "X-WR-TIMEZONE:America/Santiago",
  "BEGIN:VEVENT", "DTSTART;VALUE=DATE:20400310", "DTEND;VALUE=DATE:20400311", "SUMMARY:Primer día de clases", "END:VEVENT",
  "END:VCALENDAR", "",
].join("\r\n");

interface Status {
  state: { status: string; muted: boolean; ready: boolean };
  tabs: { url: string; ports: number; front: boolean }[];
  pending: number;
  log: string[];
  sent: { event: string; payload: Record<string, unknown> }[];
  session: { session_id?: string } | null;
  hungUp: boolean;
  micOn: boolean | null;
  micAsked: string[];
}

interface Ext {
  ctx: BrowserContext;
  sw: Worker;
  /** The requests made of the made-up API. */
  connects: { origin: string | undefined; body: unknown }[];
  open(path: string): Promise<Page>;
}

const test = base.extend<{ ext: Ext }>({
  // eslint-disable-next-line no-empty-pattern
  ext: async ({}, use) => {
    const dir = mkdtempSync(join(tmpdir(), "saintgeorge-ext-"));
    const ctx = await chromium.launchPersistentContext(dir, {
      channel: "chromium",
      headless: true,
      viewport: { width: 1280, height: 800 },
      args: [
        `--disable-extensions-except=${EXT}`,
        `--load-extension=${EXT}`,
        "--use-fake-device-for-media-stream",
        "--use-fake-ui-for-media-stream",
      ],
    });
    const connects: Ext["connects"] = [];
    // Only the web: the extension's own pages load as they are.
    await ctx.route(/^https?:/, async (route, request) => {
      const url = new URL(request.url());
      if (url.origin === ORIGIN) {
        if (url.pathname === "/slow.js") {
          await new Promise((r) => setTimeout(r, 2000));
          return route.fulfill({ status: 200, contentType: "text/javascript", body: "window.__slow = 1;" });
        }
        const page = PAGES[url.pathname];
        if (!page || request.resourceType() !== "document") return route.fulfill({ status: 404, body: "" });
        if (page.delay) await new Promise((r) => setTimeout(r, page.delay));
        return route.fulfill({
          status: 200,
          contentType: "text/html; charset=utf-8",
          body: `<!doctype html><html lang="es"><head><title>${page.title}</title></head>${page.body}</html>`,
        });
      }
      if (url.origin === CALENDAR && url.pathname.startsWith("/calendar/ical/")) {
        return route.fulfill({ status: 200, contentType: "text/calendar; charset=utf-8", body: ICS });
      }
      if (url.origin === TICKETS) {
        return route.fulfill({ status: 200, contentType: "text/html; charset=utf-8", body: "<!doctype html><title>Entradas</title><p>Entradas</p>" });
      }
      if (url.origin === API) {
        const cors = {
          "access-control-allow-origin": request.headers().origin ?? "*",
          "access-control-allow-headers": "authorization, content-type",
          "access-control-allow-methods": "POST, OPTIONS",
        };
        if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers: cors });
        connects.push({ origin: request.headers().origin, body: request.postDataJSON() });
        return route.fulfill({
          status: 200,
          headers: cors,
          contentType: "application/json",
          body: JSON.stringify({ session_id: "s-test", webrtc_request_params: { endpoint: "https://rtc.voqalize.test/offer", headers: {} } }),
        });
      }
      return route.abort();
    });
    const sw = ctx.serviceWorkers()[0] ?? (await ctx.waitForEvent("serviceworker"));
    await use({
      ctx,
      sw,
      connects,
      async open(path) {
        const page = ctx.pages()[0] ?? (await ctx.newPage());
        await page.goto(ORIGIN + path, { waitUntil: "domcontentloaded" });
        await page.locator("[data-voqalize=widget] .invite").waitFor();
        return page;
      },
    });
    await ctx.close();
  },
});

const toHolder = (sw: Worker, msg: Record<string, unknown>) =>
  sw.evaluate((m) => chrome.runtime.sendMessage({ to: "holder", op: "test", ...m }), msg);
const status = (sw: Worker) => toHolder(sw, { what: "status" }) as Promise<Status>;
const holderUp = (sw: Worker) =>
  sw.evaluate(async () => (await chrome.runtime.getContexts({ contextTypes: [chrome.runtime.ContextType.OFFSCREEN_DOCUMENT] })).length > 0);

/** Make the holder ahead of the press, as the worker would, so the test can
 *  set its stubs first. */
async function makeHolder(sw: Worker): Promise<void> {
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
  await expect.poll(async () => (await status(sw).catch(() => null))?.state?.status ?? null).toBe("idle");
}

const widget = (page: Page) => page.locator("[data-voqalize=widget] .root");

async function callLive(ext: Ext, page: Page): Promise<void> {
  await page.locator("[data-voqalize=widget] .invite").click();
  await expect(widget(page)).toHaveAttribute("data-status", "live");
  await expect.poll(async () => (await status(ext.sw)).state.ready).toBe(true);
}

test.describe("the holder and its pages", () => {
  test("a page follows the call: the press, the state, the page's events up the port, mute and End", async ({ ext }) => {
    const page = await ext.open("/");
    await callLive(ext, page);

    // The session was minted by the page, with the page's Origin, and handed over.
    expect(ext.connects).toHaveLength(1);
    expect(ext.connects[0].origin).toBe(ORIGIN);
    expect((ext.connects[0].body as { init: { surface: string; path: string } }).init).toMatchObject({ surface: "saintgeorge-ext", path: "/" });
    let s = await status(ext.sw);
    expect(s.session?.session_id).toBe("s-test");
    expect(s.tabs).toHaveLength(1);
    expect(s.tabs[0]).toMatchObject({ url: `${ORIGIN}/`, ports: 1 });

    // The brain hears where the visitor is, from the page, through the holder.
    await expect.poll(async () => (await status(ext.sw)).sent.map((e) => e.event)).toContain("page_changed");
    s = await status(ext.sw);
    expect(s.sent.find((e) => e.event === "page_changed")!.payload).toMatchObject({ path: "/", kind: "home" });
    expect(s.sent.find((e) => e.event === "tabs_changed")!.payload).toMatchObject({ tabs: [{ url: `${ORIGIN}/` }] });

    // What happens on the call reaches the widget and his face.
    await toHolder(ext.sw, { what: "emit", name: "botStartedSpeaking" });
    await expect(widget(page)).toHaveAttribute("data-activity", "speaking");
    await expect(page.locator("[data-fake-avatar]")).toHaveAttribute("data-seen", /botStartedSpeaking/);

    // Mute and End go back to the holder.
    await page.locator("[data-voqalize=widget] .mute").click();
    await expect.poll(async () => (await status(ext.sw)).micOn).toBe(false);
    await expect(widget(page)).toHaveAttribute("data-muted", "");
    await page.locator("[data-voqalize=widget] .hang").click();
    await expect(widget(page)).toHaveAttribute("data-status", "idle");
    s = await status(ext.sw);
    expect(s.hungUp).toBe(true);
    expect(s.state.status).toBe("idle");
  });

  test("a full page load leaves the call alone, and a move sent while the tab loads is made on its next page", async ({ ext }) => {
    const page = await ext.open("/");
    await callLive(ext, page);

    // The visitor's tab starts loading the next page (held back 2.5 s): the
    // page says it is leaving, and nothing more is sent to it.
    void page.evaluate(() => {
      location.href = "/unidad/elementary/";
    });
    await expect.poll(async () => (await status(ext.sw)).log.some((l) => l.includes("leaving"))).toBe(true);

    // A cue for a heading on the next page arrives meanwhile: kept for the tab.
    await toHolder(ext.sw, { what: "command", command: "cue", payload: { at: "", word: 0, path: null, heading: "Nuestros profesores", text: null, faq: null } });
    await toHolder(ext.sw, { what: "emit", name: "botStoppedSpeaking" });
    await expect.poll(async () => (await status(ext.sw)).pending, { timeout: 5000 }).toBe(1);

    // The next page says hello, gets it, and makes it.
    await page.waitForURL(`${ORIGIN}/unidad/elementary/`);
    await expect.poll(async () => (await status(ext.sw)).log.some((l) => l.includes("done show_section"))).toBe(true);
    let s = await status(ext.sw);
    expect(s.pending).toBe(0);
    expect(s.log.filter((l) => l.includes("failed"))).toEqual([]);

    // The same call all along: one connect, still live, and the new page follows it.
    expect(s.log.filter((l) => l.includes("connected "))).toHaveLength(1);
    expect(s.state.status).toBe("live");
    await expect(widget(page)).toHaveAttribute("data-status", "live");
    await expect.poll(async () => (await status(ext.sw)).sent.filter((e) => e.event === "page_changed").map((e) => e.payload.path)).toContain("/unidad/elementary/");

    // A heading the page lacks fails, and the brain is told.
    await toHolder(ext.sw, { what: "command", command: "cue", payload: { at: "", word: 0, path: null, heading: "No existe", text: null, faq: null } });
    await toHolder(ext.sw, { what: "emit", name: "botStoppedSpeaking" });
    await expect.poll(async () => (await status(ext.sw)).log.some((l) => l.includes("failed show_section"))).toBe(true);
    await expect.poll(async () => (await status(ext.sw)).sent.some((e) => e.event === "command_failed")).toBe(true);
    s = await status(ext.sw);
    expect(ext.connects).toHaveLength(1);
  });

  test("a link out opens in a tab of its own and stays off the tab list; an address the site does not link is refused", async ({ ext }) => {
    const page = await ext.open("/");
    await callLive(ext, page);
    await toHolder(ext.sw, { what: "command", command: "open_link", payload: { url: `${TICKETS}/evento/musical`, label: "Entradas" } });
    await expect.poll(() => ext.ctx.pages().map((p) => p.url())).toContain(`${TICKETS}/evento/musical`);
    // The extension does nothing on that tab: the brain's list is the site's tabs.
    await new Promise((r) => setTimeout(r, 500));
    let s = await status(ext.sw);
    expect(s.tabs.map((t) => t.url)).toEqual([`${ORIGIN}/`]);
    expect(s.sent.filter((e) => e.event === "command_failed")).toEqual([]);

    await toHolder(ext.sw, { what: "command", command: "open_link", payload: { url: "https://example.com/", label: "x" } });
    await expect.poll(async () => (await status(ext.sw)).sent.filter((e) => e.event === "command_failed").map((e) => e.payload.reason)).toEqual([
      expect.stringContaining("not an address Javier opens"),
    ]);
    s = await status(ext.sw);
    expect(s.state.status).toBe("live");
  });

  test("the calendar is read by the service worker, and the page reports it", async ({ ext }) => {
    const page = await ext.open("/familia/calendario/");
    await callLive(ext, page);
    await toHolder(ext.sw, { what: "command", command: "show_events", payload: { path: "/familia/calendario/", count: 5 } });
    await expect.poll(async () => (await status(ext.sw)).sent.find((e) => e.event === "events_read")?.payload ?? null, { timeout: 15_000 }).toMatchObject({
      events: [{ date: "2040-03-10", title: "Primer día de clases" }],
    });
  });

  test("with no Saint George's page for 15 s the call ends and the holder closes", async ({ ext }) => {
    test.setTimeout(60_000);
    const page = await ext.open("/");
    await callLive(ext, page);
    await page.goto("about:blank");
    await new Promise((r) => setTimeout(r, 9000));
    expect(await holderUp(ext.sw)).toBe(true);
    expect((await status(ext.sw)).state.status).toBe("live");
    await expect.poll(() => holderUp(ext.sw), { timeout: 15_000 }).toBe(false);
  });
});

test.describe("the extension's microphone", () => {
  test("denied: the widget says how to allow it, and no session is minted", async ({ ext }) => {
    const page = await ext.open("/");
    await makeHolder(ext.sw);
    await toHolder(ext.sw, { what: "mic", answers: ["denied"] });
    await page.locator("[data-voqalize=widget] .invite").click();
    await expect(widget(page)).toHaveAttribute("data-status", "error");
    await expect(page.locator("[data-voqalize=widget] .error-text")).toContainText("bloquea el micrófono");
    await expect(page.locator("[data-voqalize=widget] .settings")).toBeVisible();
    expect(ext.connects).toHaveLength(0);
    expect((await status(ext.sw)).session).toBeNull();
  });

  test("prompt, answered in the widget's frame: the call starts", async ({ ext }) => {
    const page = await ext.open("/");
    await makeHolder(ext.sw);
    await toHolder(ext.sw, { what: "mic", answers: ["prompt", "granted"] });
    const framed = page.waitForEvent("frameattached");
    await callLive(ext, page);
    expect((await framed).url()).toMatch(/^chrome-extension:\/\/[a-p]{32}\/grant\.html\?lang=es$/);
    expect((await status(ext.sw)).micAsked).toEqual(["prompt", "granted"]);
    // No tab was needed.
    expect(ext.ctx.pages().filter((p) => p.url().includes("grant.html"))).toHaveLength(0);
    await expect(page.locator("[data-voqalize=widget] .grant")).toBeHidden();
  });


  test("prompt that the frame's grant did not settle: the grant tab asks once, closes, and the call starts", async ({ ext }) => {
    const page = await ext.open("/");
    await makeHolder(ext.sw);
    await toHolder(ext.sw, { what: "mic", answers: ["prompt", "prompt", "granted"] });
    const tab = ext.ctx.waitForEvent("page", (p) => p.url().includes("grant.html"));
    await page.locator("[data-voqalize=widget] .invite").click();
    const grantTab = await tab;
    expect(grantTab.url()).toMatch(/grant\.html\?tab=1&lang=es$/);
    await grantTab.waitForEvent("close");
    await expect(widget(page)).toHaveAttribute("data-status", "live");
    expect((await status(ext.sw)).micAsked).toEqual(["prompt", "prompt", "granted"]);
    expect(ext.connects).toHaveLength(1);
  });
});

/** What a page saw of the widget from its very start (an init script, in
 *  every document): when the host appeared and how it looked then, against
 *  DOMContentLoaded, and the view transition that revealed the page. */
interface Early {
  host?: number;
  dcl?: number;
  first?: { status?: string; min: boolean; muted: boolean; poster: string; text: string; lang: string; transitions: boolean };
  vt?: boolean;
  vtWidth?: number;
}

async function watchEarly(ctx: BrowserContext): Promise<void> {
  await ctx.addInitScript(() => {
    const t: Record<string, unknown> = {};
    (window as unknown as { __early: unknown }).__early = t;
    const look = () => {
      const root = document.querySelector("[data-voqalize=widget]")?.shadowRoot?.querySelector<HTMLElement>(".root");
      if (!root || t.host !== undefined) return;
      t.host = performance.now();
      const poster = root.querySelector<HTMLElement>(".poster")!;
      t.first = {
        status: root.dataset.status,
        min: root.hasAttribute("data-min"),
        muted: root.hasAttribute("data-muted"),
        poster: poster.hidden ? "" : poster.style.backgroundImage,
        text: root.querySelector(".status-text")?.textContent ?? "",
        lang: root.lang,
        transitions: Boolean(document.getElementById("voqalize-transitions")),
      };
    };
    new MutationObserver(look).observe(document.documentElement ?? document, { childList: true, subtree: true });
    look();
    document.addEventListener("DOMContentLoaded", () => {
      look();
      t.dcl = performance.now();
    });
    addEventListener("pagereveal", (e) => {
      const vt = (e as Event & { viewTransition?: { ready: Promise<void> } | null }).viewTransition;
      t.vt = Boolean(vt);
      void vt?.ready.then(() => {
        t.vtWidth = parseFloat(getComputedStyle(document.documentElement, "::view-transition-group(voqalize-javier)").width) || 0;
      }).catch(() => {});
    });
  });
}

const early = (page: Page) => page.evaluate(() => (window as unknown as { __early: Early }).__early);
const kept = (page: Page) => page.evaluate(() => sessionStorage.getItem("voqalize.saintgeorge.call"));

test.describe("the widget across a page load", () => {
  test("in a call, the next page has the widget before it has parsed, as the last page left it, and loads as a view transition", async ({ ext }) => {
    await watchEarly(ext.ctx);
    const page = await ext.open("/");
    await callLive(ext, page);
    expect(await page.evaluate(() => Boolean(document.getElementById("voqalize-transitions")))).toBe(true);
    await toHolder(ext.sw, { what: "emit", name: "botStartedSpeaking" });
    await page.locator("[data-voqalize=widget] .mute").click();
    await expect(widget(page)).toHaveAttribute("data-muted", "");
    await page.locator("[data-voqalize=widget] .minimise").click({ force: true });
    await expect(widget(page)).toHaveAttribute("data-min", "");
    // The last frame of his face is kept for the next page.
    await expect.poll(() => page.evaluate(() => sessionStorage.getItem("voqalize.saintgeorge.face")?.slice(0, 15) ?? null), { timeout: 8000 }).toBe("data:image/webp");

    await page.evaluate(() => {
      location.href = "/lento/";
    });
    await page.waitForURL(`${ORIGIN}/lento/`, { waitUntil: "commit" });
    await page.waitForFunction(() => (window as unknown as { __early?: { dcl?: number } }).__early?.dcl !== undefined, null, { timeout: 10_000 });
    const e = await early(page);
    // Up at document_start, two seconds ahead of the parse it used to wait for.
    expect(e.host).toBeDefined();
    expect(e.dcl! - e.host!).toBeGreaterThan(1500);
    expect(e.first).toMatchObject({ status: "live", min: true, muted: true, text: "Hablando", lang: "es", transitions: true });
    expect(e.first!.poster).toContain("data:image/webp");
    // A cross-document view transition revealed it, with the widget as its own group.
    expect(e.vt).toBe(true);
    await expect.poll(async () => (await early(page)).vtWidth ?? 0).toBe(1280);

    // The page adopts the widget (one of it), and his face takes over from the still.
    await expect(page.locator("[data-voqalize=widget]")).toHaveCount(1);
    await expect(page.locator("[data-fake-avatar]")).toHaveCount(1);
    await expect.poll(() => page.evaluate(() =>
      document.querySelector("[data-voqalize=widget]")!.shadowRoot!.querySelector(".poster")!.classList.contains("gone"),
    )).toBe(true);
    await expect(widget(page)).toHaveAttribute("data-status", "live");
    await expect(widget(page)).toHaveAttribute("data-min", "");
    await expect(widget(page)).toHaveAttribute("data-muted", "");
    const s = await status(ext.sw);
    expect(s.log.filter((l) => l.includes("connected "))).toHaveLength(1);
    expect(ext.connects).toHaveLength(1);

    // End: nothing is kept, and the next page loads as it always has.
    await page.locator("[data-voqalize=widget] .card").click();
    await page.locator("[data-voqalize=widget] .hang").click();
    await expect(widget(page)).toHaveAttribute("data-status", "idle");
    expect(await kept(page)).toBeNull();
    expect(await page.evaluate(() => Boolean(document.getElementById("voqalize-transitions")))).toBe(false);
    await page.goto(`${ORIGIN}/lento/`, { waitUntil: "domcontentloaded" });
    const after = await early(page);
    expect(after.host === undefined || after.host >= after.dcl!).toBe(true);
    expect(after.vt).toBe(false);
  });

  test("off a call, nothing mounts early and no transition is asked for", async ({ ext }) => {
    await watchEarly(ext.ctx);
    const page = await ext.open("/");
    expect(await kept(page)).toBeNull();
    await page.evaluate(() => {
      location.href = "/lento/";
    });
    await page.waitForURL(`${ORIGIN}/lento/`, { waitUntil: "commit" });
    await page.waitForFunction(() => (window as unknown as { __early?: { dcl?: number } }).__early?.dcl !== undefined, null, { timeout: 10_000 });
    await page.locator("[data-voqalize=widget] .invite").waitFor();
    const e = await early(page);
    expect(e.host! >= e.dcl!).toBe(true);
    expect(e.first?.transitions).toBe(false);
    expect(e.vt).toBe(false);
    expect(await page.evaluate(() => Boolean(document.getElementById("voqalize-transitions")))).toBe(false);
  });

  test("a call kept from the last page that the holder no longer has: the carried widget goes back to the invite", async ({ ext }) => {
    const page = await ext.open("/");
    await page.evaluate(() =>
      sessionStorage.setItem("voqalize.saintgeorge.call", JSON.stringify({
        at: Date.now(), status: "live", muted: false, activity: "listening", language: "en", still: null,
        home: { right: 24, bottom: 24 }, minimised: false,
      })),
    );
    await page.goto(`${ORIGIN}/lento/`, { waitUntil: "commit" });
    await expect(widget(page)).toHaveAttribute("data-status", "live");
    await expect(widget(page)).toHaveAttribute("data-status", "idle", { timeout: 10_000 });
    await expect(page.locator("[data-voqalize=widget] .invite")).toBeVisible();
    expect(await kept(page)).toBeNull();
    expect(await page.evaluate(() => Boolean(document.getElementById("voqalize-transitions")))).toBe(false);
    expect(await holderUp(ext.sw)).toBe(false);
  });
});
