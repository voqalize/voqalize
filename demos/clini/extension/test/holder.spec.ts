/**
 * The holder (the offscreen document the call lives in) and the pages that
 * follow it, end to end in the built extension (`VOQALIZE_TEST_BUILD=1`,
 * test/.build/ext): a stand-in call (test/fake-call-client.ts) and a stand-in
 * avatar, pages served at www.clini.cl's and agenda-web.clini.cl's addresses,
 * a made-up API. Headless, no network.
 *
 *   - the port protocol: hello, the call press, the state on every page, the
 *     page's events up the port, mute and End;
 *   - a full page load leaves the call alone, and a move sent while the tab is
 *     loading is made on its next page, once it says hello, on the same host
 *     and across hosts (www.clini.cl to the booking on agenda-web);
 *   - `open_agenda` with no booking tab opens one at the service's deep link,
 *     and the move is made there;
 *   - no Clini page for 15 s ends the call and closes the holder;
 *   - the microphone permission's branches (granted, denied, prompt answered
 *     in the frame, prompt that needs the tab), with the permission query
 *     stubbed;
 *   - his mouth clock: with his voice on a real WebRTC loopback in the holder,
 *     the face's reads of the relayed clock are fresh while he speaks, on a
 *     busy page too, and read as a stop soon after he stops;
 *   - a page load in the middle of a reply: the next page's face, which
 *     listens only a moment after it is made, gets the reply so far and what
 *     follows, in order, and nothing of a reply that is over or was cut;
 *   - his still on the next page, until its face draws: it moves (a talking
 *     head while he speaks, a breath while he listens), and holds still under
 *     reduced motion.
 */

import { type BrowserContext, chromium, expect, type Page, test as base, type Worker } from "@playwright/test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const EXT = join(here, ".build", "ext");
const ORIGIN = "https://www.clini.cl";
const AGENDA = "https://agenda-web.clini.cl";
const API = "https://api.voqalize.test";

const PAGES: Record<string, { body: string; title: string; delay?: number }> = {
  // A page whose parse is held 2 s by a script in its body: what is on
  // screen before DOMContentLoaded is the early shell's.
  "/lento": {
    title: "Laboratorio",
    body: `<body><section class="section-1"><h1>Laboratorio</h1>
      <h2>Toma de muestras</h2><p>Exámenes de sangre y orina, sin hora previa, en todos los centros.</p></section>
      <script src="/slow.js"></script><p>Fin.</p></body>`,
  },
  "/": {
    title: "CLINI",
    body: `<body><section class="section-1"><h1>CLINI</h1>
      <h2>Especialidades</h2><p>Oftalmología, dermatología, ginecología y más, en un solo lugar.</p></section>
      <section class="section-2"><h2>Laboratorio</h2><p>Exámenes de sangre y orina, sin hora previa.</p></section></body>`,
  },
  "/ubicaciones": {
    title: "Ubicaciones",
    delay: 2500,
    body: `<body><section class="section-1"><h1>Ubicaciones</h1>
      <h2>Centro de Salud Astra Alameda</h2><p>Av. Libertador Bernardo O'Higgins, de lunes a sábado.</p></section></body>`,
  },
};

/** The booking's one page, on agenda-web: the search form, held back as the
 *  real one is behind its login-less scripts. */
const AGENDA_PAGE = {
  title: "Agenda Web CLINI",
  delay: 2500,
  body: `<body><main><h1>Agenda tu hora</h1>
    <h2>Busca disponibilidad</h2><p>Elige el servicio, la región y la prestación para ver las horas.</p>
    <button id="btnBuscar" type="button">Buscar</button></main></body>`,
};

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
    const dir = mkdtempSync(join(tmpdir(), "clini-ext-"));
    const ctx = await chromium.launchPersistentContext(dir, {
      channel: "chromium",
      headless: true,
      viewport: { width: 1280, height: 800 },
      args: [
        `--disable-extensions-except=${EXT}`,
        `--load-extension=${EXT}`,
        "--use-fake-device-for-media-stream",
        "--use-fake-ui-for-media-stream",
        // His voice in the voice tests is a tone the holder plays unprompted.
        "--autoplay-policy=no-user-gesture-required",
      ],
    });
    const connects: Ext["connects"] = [];
    // Only the web: the extension's own pages load as they are.
    await ctx.route(/^https?:/, async (route, request) => {
      const url = new URL(request.url());
      if (url.origin === AGENDA) {
        if (url.pathname !== "/" || request.resourceType() !== "document") return route.fulfill({ status: 404, body: "" });
        await new Promise((r) => setTimeout(r, AGENDA_PAGE.delay));
        return route.fulfill({
          status: 200,
          contentType: "text/html; charset=utf-8",
          body: `<!doctype html><html lang="es"><head><title>${AGENDA_PAGE.title}</title></head>${AGENDA_PAGE.body}</html>`,
        });
      }
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
    expect((ext.connects[0].body as { init: { surface: string; path: string } }).init).toMatchObject({ surface: "clini-ext", path: "/" });
    let s = await status(ext.sw);
    expect(s.session?.session_id).toBe("s-test");
    expect(s.tabs).toHaveLength(1);
    expect(s.tabs[0]).toMatchObject({ url: `${ORIGIN}/`, ports: 1 });

    // The brain hears where the visitor is, from the page, through the holder.
    await expect.poll(async () => (await status(ext.sw)).sent.map((e) => e.event)).toContain("page_changed");
    s = await status(ext.sw);
    expect(s.sent.find((e) => e.event === "page_changed")!.payload).toMatchObject({ site: "site", path: "/", kind: "page" });
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
      location.href = "/ubicaciones";
    });
    await expect.poll(async () => (await status(ext.sw)).log.some((l) => l.includes("leaving"))).toBe(true);

    // A cue for a heading on the next page arrives meanwhile: kept for the tab.
    await toHolder(ext.sw, { what: "command", command: "cue", payload: { at: "", word: 0, path: null, heading: "Centro de Salud Astra Alameda", text: null, faq: null } });
    await toHolder(ext.sw, { what: "emit", name: "botStoppedSpeaking" });
    await expect.poll(async () => (await status(ext.sw)).pending, { timeout: 5000 }).toBe(1);

    // The next page says hello, gets it, and makes it.
    await page.waitForURL(`${ORIGIN}/ubicaciones`);
    await expect.poll(async () => (await status(ext.sw)).log.some((l) => l.includes("done show_section"))).toBe(true);
    let s = await status(ext.sw);
    expect(s.pending).toBe(0);
    expect(s.log.filter((l) => l.includes("failed"))).toEqual([]);

    // The same call all along: one connect, still live, and the new page follows it.
    expect(s.log.filter((l) => l.includes("connected "))).toHaveLength(1);
    expect(s.state.status).toBe("live");
    await expect(widget(page)).toHaveAttribute("data-status", "live");
    await expect.poll(async () => (await status(ext.sw)).sent.filter((e) => e.event === "page_changed").map((e) => e.payload.path)).toContain("/ubicaciones");

    // A heading the page lacks fails, and the brain is told.
    await toHolder(ext.sw, { what: "command", command: "cue", payload: { at: "", word: 0, path: null, heading: "No existe", text: null, faq: null } });
    await toHolder(ext.sw, { what: "emit", name: "botStoppedSpeaking" });
    await expect.poll(async () => (await status(ext.sw)).log.some((l) => l.includes("failed show_section"))).toBe(true);
    await expect.poll(async () => (await status(ext.sw)).sent.some((e) => e.event === "command_failed")).toBe(true);
    s = await status(ext.sw);
    expect(ext.connects).toHaveLength(1);
  });

  test("a load from www.clini.cl to the booking on agenda-web leaves the call alone, and a move sent meanwhile is made on the booking's page", async ({ ext }) => {
    const page = await ext.open("/");
    await callLive(ext, page);

    // The tab loads the booking (another host, held back 2.5 s).
    void page.evaluate((to) => {
      location.href = to;
    }, `${AGENDA}/?servicio=1`);
    await expect.poll(async () => (await status(ext.sw)).log.some((l) => l.includes("leaving"))).toBe(true);

    // A cue for a heading on the booking's page arrives meanwhile: kept for the tab.
    await toHolder(ext.sw, { what: "command", command: "cue", payload: { at: "", word: 0, path: null, heading: "Busca disponibilidad", text: null, faq: null } });
    await toHolder(ext.sw, { what: "emit", name: "botStoppedSpeaking" });
    await expect.poll(async () => (await status(ext.sw)).pending, { timeout: 5000 }).toBe(1);

    // The booking's page says hello on the same port name, gets it, and makes it.
    await page.waitForURL(`${AGENDA}/?servicio=1`);
    await expect.poll(async () => (await status(ext.sw)).log.some((l) => l.includes("done show_section")), { timeout: 15_000 }).toBe(true);
    const s = await status(ext.sw);
    expect(s.pending).toBe(0);
    expect(s.log.filter((l) => l.includes("failed"))).toEqual([]);
    expect(s.log.filter((l) => l.includes("connected "))).toHaveLength(1);
    expect(s.state.status).toBe("live");
    expect(s.tabs).toHaveLength(1);
    expect(s.tabs[0].url).toBe(`${AGENDA}/?servicio=1`);
    await expect(widget(page)).toHaveAttribute("data-status", "live");
    await expect.poll(async () => (await status(ext.sw)).sent.filter((e) => e.event === "page_changed").map((e) => e.payload.site)).toContain("agenda");
    expect(ext.connects).toHaveLength(1);
  });

  test("open_agenda with no booking tab opens one at the service's deep link, and the move is made there", async ({ ext }) => {
    const page = await ext.open("/");
    await callLive(ext, page);
    const opened = ext.ctx.waitForEvent("page", (p) => p.url().startsWith(AGENDA));
    await toHolder(ext.sw, { what: "command", command: "open_agenda", payload: { servicio: 7, prestacion: null } });
    const agenda = await opened;
    expect(agenda.url()).toBe(`${AGENDA}/?servicio=7`);
    // Kept for the new tab until its page says hello, then sent to it.
    await expect.poll(async () => (await status(ext.sw)).log.some((l) => /perform open_agenda → tab \d+/.test(l)), { timeout: 15_000 }).toBe(true);
    await expect(widget(agenda)).toHaveAttribute("data-status", "live");
    const s = await status(ext.sw);
    expect(s.tabs.map((t) => t.url).sort()).toEqual([`${AGENDA}/?servicio=7`, `${ORIGIN}/`]);
    expect(s.log.filter((l) => l.includes("connected "))).toHaveLength(1);
    // The site's tab is still there, still following the same call.
    await expect(widget(page)).toHaveAttribute("data-status", "live");
  });

  test("with no Clini page for 15 s the call ends and the holder closes", async ({ ext }) => {
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
const kept = (page: Page) => page.evaluate(() => sessionStorage.getItem("voqalize.clini.call"));

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
    await expect.poll(() => page.evaluate(() => sessionStorage.getItem("voqalize.clini.face")?.slice(0, 15) ?? null), { timeout: 8000 }).toBe("data:image/webp");

    await page.evaluate(() => {
      location.href = "/lento";
    });
    await page.waitForURL(`${ORIGIN}/lento`, { waitUntil: "commit" });
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
    await page.goto(`${ORIGIN}/lento`, { waitUntil: "domcontentloaded" });
    const after = await early(page);
    expect(after.host === undefined || after.host >= after.dcl!).toBe(true);
    expect(after.vt).toBe(false);
  });

  test("off a call, nothing mounts early and no transition is asked for", async ({ ext }) => {
    await watchEarly(ext.ctx);
    const page = await ext.open("/");
    expect(await kept(page)).toBeNull();
    await page.evaluate(() => {
      location.href = "/lento";
    });
    await page.waitForURL(`${ORIGIN}/lento`, { waitUntil: "commit" });
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
      sessionStorage.setItem("voqalize.clini.call", JSON.stringify({
        at: Date.now(), status: "live", muted: false, activity: "listening", language: "en", still: null,
        home: { left: 24, bottom: 24 }, minimised: false,
      })),
    );
    await page.goto(`${ORIGIN}/lento`, { waitUntil: "commit" });
    await expect(widget(page)).toHaveAttribute("data-status", "live");
    await expect(widget(page)).toHaveAttribute("data-status", "idle", { timeout: 10_000 });
    await expect(page.locator("[data-voqalize=widget] .invite")).toBeVisible();
    expect(await kept(page)).toBeNull();
    expect(await page.evaluate(() => Boolean(document.getElementById("voqalize-transitions")))).toBe(false);
    expect(await holderUp(ext.sw)).toBe(false);
  });
});

/** The face shuts the mouth on a delivery older than this when it reads one:
 *  a frame, and the gap it closes over. */
const STALE_MS = 60;

interface FaceRead {
  at: number;
  timestamp: number | null;
}
const faceReads = (page: Page) =>
  page.evaluate(() => (window as unknown as { __faceReads?: FaceRead[] }).__faceReads ?? []) as Promise<FaceRead[]>;
const pageNow = (page: Page) => page.evaluate(() => performance.timeOrigin + performance.now());
const staleShare = (reads: FaceRead[]) =>
  reads.filter((r) => r.timestamp === null || r.at - r.timestamp > STALE_MS).length / reads.length;

/** Speak, and wait until his voice reaches the face's reads. */
async function speaking(ext: Ext, page: Page): Promise<void> {
  expect(await toHolder(ext.sw, { what: "voice", on: true })).toEqual({ ok: true });
  await expect
    .poll(async () => (await faceReads(page)).slice(-5).filter((r) => r.timestamp !== null && r.at - r.timestamp <= STALE_MS).length)
    .toBeGreaterThan(0);
}

test.describe("his mouth clock on a page", () => {
  test("while he speaks the face reads a fresh delivery, on a quiet page and on a busy one", async ({ ext }) => {
    const page = await ext.open("/");
    await callLive(ext, page);
    await speaking(ext, page);

    let from = await pageNow(page);
    await page.waitForTimeout(3000);
    const quiet = (await faceReads(page)).filter((r) => r.at >= from);

    // A busy page, as a gallery, a scroll or the next page parsing makes one:
    // 60 ms of work every 120 ms.
    from = await page.evaluate(() => {
      (window as unknown as { __busy?: number }).__busy = window.setInterval(() => {
        const t = performance.now();
        while (performance.now() - t < 60);
      }, 120);
      return performance.timeOrigin + performance.now();
    });
    await page.waitForTimeout(4000);
    const until = await page.evaluate(() => {
      clearInterval((window as unknown as { __busy?: number }).__busy);
      return performance.timeOrigin + performance.now();
    });
    const busy = (await faceReads(page)).filter((r) => r.at >= from && r.at <= until);

    expect(quiet.length).toBeGreaterThan(50);
    expect(busy.length).toBeGreaterThan(20);
    expect(staleShare(quiet)).toBeLessThan(0.05);
    expect(staleShare(busy)).toBeLessThan(0.05);
  });

  test("when he stops, the face reads the stop within a moment", async ({ ext }) => {
    const page = await ext.open("/");
    await callLive(ext, page);
    await speaking(ext, page);
    await page.waitForTimeout(1500);

    expect(await toHolder(ext.sw, { what: "voice", on: false })).toEqual({ ok: true });
    const stopped = await pageNow(page);
    await page.waitForTimeout(1000);
    const after = (await faceReads(page)).filter((r) => r.at >= stopped);

    // The last delivery the face is shown is at most the hold past the real
    // stop (plus the receiver draining its buffer), and from then on every
    // read is a stop.
    const last = Math.max(...after.map((r) => r.timestamp ?? 0));
    expect(last).toBeLessThan(stopped + 300);
    const settled = after.filter((r) => r.at >= stopped + 400);
    expect(settled.length).toBeGreaterThan(10);
    expect(staleShare(settled)).toBe(1);
  });
});

interface FaceSaw {
  what: string;
  ctx?: string;
  from_ms?: number;
}
const faceSaw = (page: Page) =>
  page.evaluate(() => (window as unknown as { __faceSaw?: FaceSaw[] }).__faceSaw ?? []) as Promise<FaceSaw[]>;
const toFace = async (ext: Ext, msg: Record<string, unknown>) =>
  expect(await toHolder(ext.sw, { what: "avatar", msg })).toEqual({ ok: true });
const label = (s: FaceSaw) => (s.ctx ? `${s.what} ${s.ctx}${s.from_ms === undefined ? "" : `@${s.from_ms}`}` : s.what);

/** A full page load in a call, and the new page's face up. */
async function load(page: Page, path: string): Promise<void> {
  await page.goto(ORIGIN + path, { waitUntil: "domcontentloaded" });
  await expect(widget(page)).toHaveAttribute("data-status", "live");
}

test.describe("a page load in the middle of a reply", () => {
  test("the next page's face gets the reply so far (its place on the stream, its cues) and that he is speaking, then what follows, in order", async ({ ext }) => {
    const page = await ext.open("/");
    await callLive(ext, page);
    await speaking(ext, page);

    // A reply whose cues have all been sent before the load, as a sentence's
    // phones are, seconds ahead of its audio.
    await toHolder(ext.sw, { what: "emit", name: "botStartedSpeaking" });
    await toFace(ext, { cmd: "sync", ctx: "r1", at_ms: 0, rtp: 48000, rate: 48000 });
    await toFace(ext, { cmd: "cues", ctx: "r1", from_ms: 0, cues: [{ t: 0, v: "B" }] });
    await toFace(ext, { cmd: "cues", ctx: "r1", from_ms: 900, cues: [{ t: 900, v: "C" }] });
    await expect.poll(async () => (await faceSaw(page)).map(label)).toEqual(["botStartedSpeaking", "sync r1", "cues r1@0", "cues r1@900"]);

    await load(page, "/ubicaciones");
    await expect.poll(async () => (await faceSaw(page)).map(label)).toEqual(["sync r1", "cues r1@0", "cues r1@900", "botStartedSpeaking"]);

    // What the reply sends next reaches the new face after what it caught up on.
    await toFace(ext, { cmd: "cues", ctx: "r1", from_ms: 1800, cues: [{ t: 1800, v: "D" }] });
    await expect.poll(async () => (await faceSaw(page)).map(label).at(-1)).toBe("cues r1@1800");
  });

  test("a reply that is over, or was cut, is not carried to the next page", async ({ ext }) => {
    const page = await ext.open("/");
    await callLive(ext, page);
    await speaking(ext, page);

    // Heard to its end.
    await toHolder(ext.sw, { what: "emit", name: "botStartedSpeaking" });
    await toFace(ext, { cmd: "sync", ctx: "done", at_ms: 0, rtp: 48000, rate: 48000 });
    await toFace(ext, { cmd: "cues", ctx: "done", from_ms: 0, cues: [{ t: 0, v: "B" }] });
    await toFace(ext, { cmd: "end", ctx: "done", at_ms: 1200 });
    await toHolder(ext.sw, { what: "emit", name: "botStoppedSpeaking" });
    // Cut while he spoke.
    await toHolder(ext.sw, { what: "emit", name: "botStartedSpeaking" });
    await toFace(ext, { cmd: "sync", ctx: "cut", at_ms: 0, rtp: 96000, rate: 48000 });
    await toFace(ext, { cmd: "cues", ctx: "cut", from_ms: 0, cues: [{ t: 0, v: "B" }] });
    await toFace(ext, { cmd: "action", id: "RESPONSE_INTERRUPTED" });
    await toHolder(ext.sw, { what: "emit", name: "botStoppedSpeaking" });
    await expect.poll(async () => (await faceSaw(page)).length).toBe(10);

    await load(page, "/ubicaciones");
    await page.waitForTimeout(800);
    expect((await faceSaw(page)).map(label)).toEqual([]);
  });
});

interface PosterNow {
  name: string;
  transform: string;
  gone: boolean;
}
const posterNow = (page: Page) =>
  page.evaluate(() => {
    const p = document.querySelector("[data-voqalize=widget]")?.shadowRoot?.querySelector<HTMLElement>(".poster");
    if (!p || p.hidden) return null;
    const style = getComputedStyle(p);
    return { name: style.animationName, transform: style.transform, gone: p.classList.contains("gone") };
  }) as Promise<PosterNow | null>;

/** In a call, a full load of a page whose parse a script holds for 2 s: the
 *  early shell's still is what shows his face meanwhile. */
async function toSlowPage(ext: Ext, page: Page, speaking: boolean): Promise<void> {
  await callLive(ext, page);
  if (speaking) {
    await toHolder(ext.sw, { what: "emit", name: "botStartedSpeaking" });
    await expect(widget(page)).toHaveAttribute("data-activity", "speaking");
  }
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem("voqalize.clini.face")?.slice(0, 15) ?? null), { timeout: 8000 }).toBe("data:image/webp");
  await page.evaluate(() => {
    location.href = "/lento";
  });
  await page.waitForURL(`${ORIGIN}/lento`, { waitUntil: "commit" });
  await expect.poll(async () => (await posterNow(page)) !== null).toBe(true);
}

test.describe("his still while the next page's face is not drawing yet", () => {
  test("it moves as a talking head while he speaks, and keeps moving", async ({ ext }) => {
    const page = await ext.open("/");
    await toSlowPage(ext, page, true);
    await expect.poll(async () => (await posterNow(page))?.name).toBe("poster-talk");
    const a = (await posterNow(page))!;
    await page.waitForTimeout(300);
    const b = (await posterNow(page))!;
    expect(b.gone).toBe(false);
    expect(b.transform).not.toBe(a.transform);
    expect(b.transform).not.toBe("none");
  });

  test("it breathes, slowly, while he listens", async ({ ext }) => {
    const page = await ext.open("/");
    await toSlowPage(ext, page, false);
    await expect.poll(async () => (await posterNow(page))?.name).toBe("poster-rest");
    const a = (await posterNow(page))!;
    await page.waitForTimeout(400);
    expect((await posterNow(page))!.transform).not.toBe(a.transform);
  });

  test("it holds still for a visitor who asks for reduced motion", async ({ ext }) => {
    const page = await ext.open("/");
    await page.emulateMedia({ reducedMotion: "reduce" });
    await toSlowPage(ext, page, true);
    expect(await posterNow(page)).toMatchObject({ name: "none", transform: "none" });
  });
});
