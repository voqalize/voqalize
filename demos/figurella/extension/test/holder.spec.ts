/**
 * The holder (the offscreen document the call lives in) and the pages that
 * follow it, end to end in the built extension (`VOQALIZE_TEST_BUILD=1`,
 * test/.build/ext): a stand-in call (test/fake-call-client.ts) and a stand-in
 * avatar, pages served at figurella.cl's address, and a made-up API.
 * Headless; the one request that leaves the machine is Google's redirect of
 * the branch map the map test opens.
 *
 *   - the port protocol: hello, the call press, the state on every page, the
 *     page's events up the port, mute and End;
 *   - a full page load leaves the call alone, and a move sent while the tab is
 *     loading is made on its next page, once it says hello;
 *   - a form fill from a page without the form loads the page that has it and
 *     fills it there, and nothing is ever submitted;
 *   - a branch's map opens in a tab of its own, through the service worker;
 *   - no Figurella page for 15 s ends the call and closes the holder;
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
const ORIGIN = "https://figurella.cl";
const MAPS = "https://goo.gl";
const API = "https://api.voqalize.test";

/** The booking form in the footer, as the site writes it (its fields' ids and
 *  required marks, its branch list's values, the ticked privacy box). */
const FOOTER = `<div id="contacto"><h2>Reserva tu Diagnóstico Corporal sin costo</h2>
  <form class="elementor-form" method="post" id="form_agendamiento_figurella">
    <div class="elementor-field-group"><input id="form-field-first_name" name="form_fields[first_name]" required></div>
    <div class="elementor-field-group"><input id="form-field-phone" type="tel" name="form_fields[phone]" required></div>
    <div class="elementor-field-group"><input id="form-field-email" type="email" name="form_fields[email]" required></div>
    <div class="elementor-field-group"><input id="form-field-comuna" name="form_fields[comuna]" required></div>
    <div class="elementor-field-group"><select id="form-field-sucursales" name="form_fields[sucursales]" required>
      <option value="">Selecciona tu sucursal</option><option value="vitacura@figurella.cl">Vitacura</option>
      <option value="colon@figurella.cl">Colón</option></select></div>
    <div class="elementor-field-group"><textarea id="form-field-message" name="form_fields[message]" required></textarea></div>
    <div class="elementor-field-group elementor-field-group-field_826580a"><input type="checkbox" id="form-field-field_826580a" checked>
      <label for="form-field-field_826580a">Acepto la Política de Privacidad y el contacto por WhatsApp.</label></div>
    <button type="submit" id="btn-send">Reservar mi diagnóstico</button>
  </form></div>`;

const PAGES: Record<string, { body: string; title: string; delay?: number }> = {
  // A page whose parse is held 2 s by a script in its body: what is on screen
  // before DOMContentLoaded is the early shell's.
  "/lento/": {
    title: "Consejos – Figurella",
    body: `<body><main><h1 class="entry-title-single">Cápsula térmica y sus beneficios</h1>
      <div class="single-post-article"><div class="entry"><p>La cápsula mantiene tu cuerpo a 37 grados.</p></div></div></main>
      <script src="/slow.js"></script><p>Fin.</p></body>`,
  },
  "/": {
    title: "Figurella – Centro de Modelamiento Corporal",
    body: `<body><main>
      <div class="elementor-element elementor-element-a82a4e5"><h2>Sé quien quieras ser</h2><p>15 años en Chile.</p></div>
      <div id="sucursales"><h2>Sucursales Figurella</h2>
        <div class="elementor-element elementor-element-0ef47cd"><h3>Vitacura</h3><p>Juan XXIII 6370, Vitacura.</p></div></div>
      </main>${FOOTER}</body>`,
  },
  "/planes/": {
    title: "Planes – Figurella",
    delay: 2500,
    body: `<body><main><div class="elementor-element elementor-element-41c3b402"><h1>Planes</h1></div>
      <div class="elementor-element elementor-element-341a556"><h3>Novias</h3><p>Rediseña tu silueta.</p></div></main>${FOOTER}</body>`,
  },
  "/franquicias/": {
    title: "Franquicias – Figurella",
    body: `<body><main><div class="elementor-element elementor-element-76a4a3bb"><h1>Franquicias</h1></div></main></body>`,
  },
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
    const dir = mkdtempSync(join(tmpdir(), "figurella-ext-"));
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
      if (url.origin === MAPS) {
        return route.fulfill({ status: 200, contentType: "text/html; charset=utf-8", body: "<!doctype html><title>Mapa</title><p>Mapa</p>" });
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
    expect((ext.connects[0].body as { init: { surface: string; path: string } }).init).toMatchObject({ surface: "figurella-ext", path: "/" });
    let s = await status(ext.sw);
    expect(s.session?.session_id).toBe("s-test");
    expect(s.tabs).toHaveLength(1);
    expect(s.tabs[0]).toMatchObject({ url: `${ORIGIN}/`, ports: 1 });

    // The brain hears where the visitor is, from the page, through the holder.
    await expect.poll(async () => (await status(ext.sw)).sent.map((e) => e.event)).toContain("page_changed");
    s = await status(ext.sw);
    expect(s.sent.find((e) => e.event === "page_changed")!.payload).toMatchObject({ path: "/", kind: "home", form: "booking" });
    expect((s.sent.find((e) => e.event === "page_changed")!.payload as { anchors: string[] }).anchors).toEqual(
      expect.arrayContaining(["intro", "sucursales", "sucursal_vitacura", "contacto"]),
    );
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
      location.href = "/planes/";
    });
    await expect.poll(async () => (await status(ext.sw)).log.some((l) => l.includes("leaving"))).toBe(true);

    // A cue for a place on the next page arrives meanwhile: kept for the tab.
    await toHolder(ext.sw, { what: "command", command: "cue", payload: { at: "", word: 0, path: null, anchor: "plan_novias", text: null, faq: null } });
    await toHolder(ext.sw, { what: "emit", name: "botStoppedSpeaking" });
    await expect.poll(async () => (await status(ext.sw)).pending, { timeout: 5000 }).toBe(1);

    // The next page says hello, gets it, and makes it.
    await page.waitForURL(`${ORIGIN}/planes/`);
    await expect.poll(async () => (await status(ext.sw)).log.some((l) => l.includes("done show_section"))).toBe(true);
    let s = await status(ext.sw);
    expect(s.pending).toBe(0);
    expect(s.log.filter((l) => l.includes("failed"))).toEqual([]);

    // The same call all along: one connect, still live, and the new page follows it.
    expect(s.log.filter((l) => l.includes("connected "))).toHaveLength(1);
    expect(s.state.status).toBe("live");
    await expect(widget(page)).toHaveAttribute("data-status", "live");
    await expect.poll(async () => (await status(ext.sw)).sent.filter((e) => e.event === "page_changed").map((e) => e.payload.path)).toContain("/planes/");
    await expect(page.locator("[data-voqalize=highlight]")).toHaveCount(1);

    // A place the page lacks fails, and the brain is told.
    await toHolder(ext.sw, { what: "command", command: "cue", payload: { at: "", word: 0, path: null, anchor: "no_existe", text: null, faq: null } });
    await toHolder(ext.sw, { what: "emit", name: "botStoppedSpeaking" });
    await expect.poll(async () => (await status(ext.sw)).log.some((l) => l.includes("failed show_section"))).toBe(true);
    await expect.poll(async () => (await status(ext.sw)).sent.some((e) => e.event === "command_failed")).toBe(true);
    s = await status(ext.sw);
    expect(ext.connects).toHaveLength(1);
  });

  test("a branch's map opens in a tab of its own and stays off the tab list; an address the site does not link is refused", async ({ ext }) => {
    const page = await ext.open("/");
    await callLive(ext, page);
    await toHolder(ext.sw, { what: "command", command: "open_link", payload: { url: `${MAPS}/maps/59M2H8SUbz1CEhU76`, label: "Cómo llegar a Vitacura" } });
    // Google's short link redirects to the map itself.
    await expect.poll(() => ext.ctx.pages().some((p) => /^https:\/\/(goo\.gl\/maps|www\.google\.[a-z.]+\/maps)/.test(p.url()))).toBe(true);
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

  test("a fill from a page without the form opens the home page and fills it there; nothing is submitted", async ({ ext }) => {
    await ext.ctx.addInitScript(() => {
      (window as unknown as { __submits: number }).__submits = 0;
      addEventListener("submit", () => (window as unknown as { __submits: number }).__submits++, true);
    });
    const page = await ext.open("/franquicias/");
    await callLive(ext, page);
    await toHolder(ext.sw, {
      what: "command",
      command: "fill_booking_form",
      payload: { nombre: "Ana", telefono: "+56 9 1234 5678", email: "ana@example.com", comuna: "Vitacura", sucursal: "Vitacura", mensaje: "Quiero mi diagnóstico." },
    });
    await page.waitForURL(`${ORIGIN}/`);
    await expect.poll(async () => (await status(ext.sw)).sent.find((e) => e.event === "form_state")?.payload ?? null, { timeout: 15_000 }).toMatchObject({
      form: "booking",
      ready: true,
      missing: [],
      values: { telefono: "+56912345678", sucursal: "Vitacura" },
      consent: true,
      by: "javier",
    });
    await expect.poll(async () => (await status(ext.sw)).sent.find((e) => e.event === "command_done")?.payload ?? null).toMatchObject({
      command: "fill_booking_form",
      detail: expect.stringContaining("she presses it herself"),
    });
    expect(await page.locator("#form-field-sucursales").inputValue()).toBe("vitacura@figurella.cl");
    expect(await page.locator("#form-field-field_826580a").isChecked()).toBe(true);
    await new Promise((r) => setTimeout(r, 1000));
    expect(await page.evaluate(() => (window as unknown as { __submits: number }).__submits)).toBe(0);
    expect(ext.connects).toHaveLength(1);
  });

  test("with no Figurella page for 15 s the call ends and the holder closes", async ({ ext }) => {
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
const kept = (page: Page) => page.evaluate(() => sessionStorage.getItem("voqalize.figurella.call"));

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
    await expect.poll(() => page.evaluate(() => sessionStorage.getItem("voqalize.figurella.face")?.slice(0, 15) ?? null), { timeout: 8000 }).toBe("data:image/webp");

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
      sessionStorage.setItem("voqalize.figurella.call", JSON.stringify({
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

    await load(page, "/planes/");
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

    await load(page, "/franquicias/");
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
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem("voqalize.figurella.face")?.slice(0, 15) ?? null), { timeout: 8000 }).toBe("data:image/webp");
  await page.evaluate(() => {
    location.href = "/lento/";
  });
  await page.waitForURL(`${ORIGIN}/lento/`, { waitUntil: "commit" });
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
