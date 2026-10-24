/**
 * The holder (the offscreen document the call lives in) and the pages that
 * follow it, end to end in the built extension (`VOQALIZE_TEST_BUILD=1`,
 * test/.build/ext): a stand-in call (test/fake-call-client.ts) and a stand-in
 * avatar, pages served at ssilva.cl's address, a made-up API. Headless,
 * no network.
 *
 *   - the port protocol: hello, the call press, the state on every page, the
 *     page's events up the port, mute and End;
 *   - a full page load leaves the call alone, and a move sent while the tab is
 *     loading is made on its next page, once it says hello;
 *   - no Ssilva page for 15 s ends the call and closes the holder;
 *   - the adapter's own move for the next page (`navigate` to a section of
 *     another page) is kept by the service worker and made there once the
 *     brain can hear the page;
 *   - a project's WhatsApp opens in a tab of its own, which never joins the
 *     tab list, and the HubSpot quote-form frame never joins it either;
 *   - the microphone permission's branches (granted, denied, prompt answered
 *     in the frame, prompt that needs the tab), with the permission query
 *     stubbed;
 *   - his mouth clock: with his voice on a real WebRTC loopback in the holder,
 *     the face's reads of the relayed clock are fresh while he speaks, on a
 *     busy page too, and read as a stop soon after he stops;
 *   - a page load in the middle of a reply: the next page's face, which
 *     listens only a moment after it is made, gets the reply so far and what
 *     follows, in order, and nothing of a reply that is over or was cut.
 */

import { type BrowserContext, chromium, expect, type Page, test as base, type Worker } from "@playwright/test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const EXT = join(here, ".build", "ext");
const ORIGIN = "https://www.ssilva.cl";
const WHATSAPP = "https://wa.me";
const HSFORMS = "https://js.hsforms.net";
/** A project page, as ssilva.cl lays one out: a hero, sections, the quote
 *  form's frame and the floating WhatsApp button. */
const PROJECT = (name: string) => `<body><div class="site__content">
      <section class="l3-hero"><h1>${name}</h1><p>Desde 2.500 UF</p></section>
      <section class="l3-numbered-slider-section"><h2>Galería</h2><div style="height:1400px"></div></section>
      <section class="project-actions-section"><h2>Ubicación</h2><p>Av. Siempre Viva 742, Ñuñoa.</p>
        <div style="height:1400px"></div></section>
      <iframe class="hs-form-frame" src="${HSFORMS}/form" style="width:300px;height:200px"></iframe>
      <a class="floating-quote-btn" href="${WHATSAPP}/56900000000">WhatsApp</a>
    </div></body>`;
const API = "https://api.voqalize.test";

const card = (name: string, path: string) =>
  `<div class="project-card-wrapper" style="height:420px;margin:12px;border:1px solid #ccc">
    <span class="project-card__opp-condo-name">${name}</span><a href="${ORIGIN}${path}">Ver proyecto</a></div>`;
const LIST = `<body><main class="site__content"><section class="projects-list">
    <h2>FIND YOUR NEW HOME</h2>
    <select id="region"><option value="">Todas</option><option value="17" selected>Región Metropolitana</option><option value="557">Región de Valparaíso</option></select>
    <select id="property"><option value="">Todos</option><option value="34" selected>Departamento</option></select>
    <p class="projects-list__results-msg">4 projects found for your search.</p>
    <div id="cards"></div>
    <ul class="custom-pagination"><li class="active"><a class="class-icon-scroll-page" href="#" data-p="1">1</a></li><li><a class="class-icon-scroll-page" href="#" data-p="2">2</a></li></ul>
  </section></main>
  <script>
    const pages = {
      1: ${JSON.stringify(card("ESTOCOLMO", "/estocolmo/") + card("RONDIZZONI BUILDING", "/rondizzoni/"))},
      2: ${JSON.stringify(card("CARRERA BUILDING", "/edificiocarrera/") + card("BARROSO DISTRICT", "/distrito-barroso/"))},
    };
    const show = (n) => {
      document.getElementById("cards").innerHTML = pages[n];
      for (const li of document.querySelectorAll(".custom-pagination li")) li.classList.toggle("active", li.textContent.trim() === String(n));
    };
    document.querySelector(".custom-pagination").addEventListener("click", (e) => {
      e.preventDefault();
      const a = e.target.closest("a");
      if (a) setTimeout(() => show(a.dataset.p), 150);
    });
    show(1);
  </script></body>`;
const slide = (src: string) =>
  `<div class="slick-slide"><button class="img-wrap nsLgSelector" data-src="/content/uploads/${src}"><img src="/content/uploads/${src}" alt=""></button></div>`;
const GALLERY_PROJECT = `<body class="page-template-landing"><div class="site__content">
    <section class="l3-hero"><h1>Distrito Barroso</h1><p>FROM 2,582 UF</p></section>
    <section class="l3-numbered-slider-section"><h2>Galería</h2><div class="numbered-slider">
      <div class="slick-slide slick-cloned"><button class="nsLgSelector" data-src="/content/uploads/3-salon.jpg"></button></div>
      ${slide("2.-depto-grande-scaled.jpg").replace("slick-slide", "slick-slide slick-current")}${slide("2-cowork-b.jpg")}${slide("3-salon.jpg")}${slide("4-quincho.jpg")}
    </div><span class="slide-index" data-slide="0">01</span><span class="slide-index" data-slide="1">02</span></section>
    <section class="cotizador-l1-section"><h2>Types that adapt to your needs</h2>
      <ul class="cotizador-l1"><li class="type-item active"><label>2D | 2B</label></li><li class="type-item"><label>2D | 2B BUTTERFLY</label></li></ul>
      <div id="floorPlanContainer_cotizador_x"><span id="priceValue_cotizador_x">3,453</span>
        <img id="floorPlanImage_cotizador_x" src="/content/uploads/DB-203-803.png" alt="2D | 2B"></div>
      <span id="totalAreaValue_cotizador_x">56.65</span></section>
    <section class="alternate-images-section"><h2>Amenities</h2>
      <button class="img-wrap aiLgSelector" data-src="/content/uploads/3-piscina-1.jpg"><img src="/content/uploads/3-piscina-1.jpg" alt=""></button>
      <button class="img-wrap aiLgSelector" data-src="/content/uploads/3-gourmet.jpg"><img src="/content/uploads/3-gourmet.jpg" alt=""></button></section>
    <div style="height:1200px"></div>
  </div>
  <script>
    for (const li of document.querySelectorAll("li.type-item")) li.querySelector("label").addEventListener("click", () => {
      for (const x of document.querySelectorAll("li.type-item")) x.classList.toggle("active", x === li);
      const mariposa = /BUTTERFLY/.test(li.textContent);
      document.querySelector("[id^=priceValue_cotizador]").textContent = mariposa ? "3,177" : "3,453";
      document.querySelector("[id^=floorPlanImage_cotizador]").src = mariposa ? "/content/uploads/DB-204-804.png" : "/content/uploads/DB-203-803.png";
    });
  </script></body>`;

const PAGES: Record<string, { body: string; title: string; delay?: number }> = {
  // A page whose load is held 2 s by a script in its body: what is on screen
  // before DOMContentLoaded is the early shell's.
  "/lento": {
    title: "Nosotros | SSilva",
    body: `<body><main><h1>Nosotros</h1>
      <h2>Nuestra historia</h2><p>Más de 50 años construyendo.</p></main>
      <script src="/slow.js"></script><p>Fin.</p></body>`,
  },
  "/": {
    title: "SSilva | Inmobiliaria",
    body: `<body><main><h1>SSilva</h1>
      <h2>Nuestros proyectos</h2><p>Departamentos en Santiago.</p>
      <h2>Oportunidades</h2><p>Unidades con descuento.</p></main></body>`,
  },
  "/nosotros/": {
    title: "Nosotros | SSilva",
    delay: 2500,
    body: `<body><main><h1>Nosotros</h1>
      <h2>Nuestra historia</h2><p>Más de 50 años construyendo.</p></main></body>`,
  },
  "/proyectos/edificio-norte/": { title: "EDIFICIO NORTE | SSilva", delay: 1500, body: PROJECT("Edificio Norte") },
  "/proyectos/edificio-sur/": { title: "EDIFICIO SUR | SSilva", body: PROJECT("Edificio Sur") },
  // The project list as Chrome's translation leaves it: card names and the
  // results line in English, two pages of cards, the card he names on the
  // second.
  "/proyectos/": { title: "Projects | SSilva", body: LIST },
  // A project page with its gallery, amenities and typologies, a typology
  // label translated ("BUTTERFLY" for "MARIPOSA").
  "/distrito-barroso/": { title: "BARROSO DISTRICT | SSilva", body: GALLERY_PROJECT },
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
    const dir = mkdtempSync(join(tmpdir(), "ssilva-ext-"));
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
      if (url.origin === WHATSAPP) {
        return route.fulfill({ status: 200, contentType: "text/html; charset=utf-8", body: "<!doctype html><title>WhatsApp</title><p>Chat</p>" });
      }
      if (url.origin === HSFORMS) {
        return route.fulfill({ status: 200, contentType: "text/html; charset=utf-8", body: "<!doctype html><title>Form</title><form><input name=email></form>" });
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
    expect((ext.connects[0].body as { init: { surface: string; path: string } }).init).toMatchObject({ surface: "ssilva-ext", path: "/" });
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
      location.href = "/nosotros/";
    });
    await expect.poll(async () => (await status(ext.sw)).log.some((l) => l.includes("leaving"))).toBe(true);

    // A cue for a heading on the next page arrives meanwhile: kept for the tab.
    await toHolder(ext.sw, { what: "command", command: "cue", payload: { at: "", word: 0, path: null, heading: "Nuestra historia", text: null, typology: null } });
    await toHolder(ext.sw, { what: "emit", name: "botStoppedSpeaking" });
    await expect.poll(async () => (await status(ext.sw)).pending, { timeout: 5000 }).toBe(1);

    // The next page says hello, gets it, and makes it.
    await page.waitForURL(`${ORIGIN}/nosotros/`);
    await expect.poll(async () => (await status(ext.sw)).log.some((l) => l.includes("done show_section"))).toBe(true);
    let s = await status(ext.sw);
    expect(s.pending).toBe(0);
    expect(s.log.filter((l) => l.includes("failed"))).toEqual([]);

    // The same call all along: one connect, still live, and the new page follows it.
    expect(s.log.filter((l) => l.includes("connected "))).toHaveLength(1);
    expect(s.state.status).toBe("live");
    await expect(widget(page)).toHaveAttribute("data-status", "live");
    await expect.poll(async () => (await status(ext.sw)).sent.filter((e) => e.event === "page_changed").map((e) => e.payload.path)).toContain("/nosotros/");

    // A heading the page lacks fails, and the brain is told.
    await toHolder(ext.sw, { what: "command", command: "cue", payload: { at: "", word: 0, path: null, heading: "No existe", text: null, typology: null } });
    await toHolder(ext.sw, { what: "emit", name: "botStoppedSpeaking" });
    await expect.poll(async () => (await status(ext.sw)).log.some((l) => l.includes("failed show_section"))).toBe(true);
    await expect.poll(async () => (await status(ext.sw)).sent.some((e) => e.event === "command_failed")).toBe(true);
    s = await status(ext.sw);
    expect(ext.connects).toHaveLength(1);
  });

  test("the adapter's navigate to a section of another page: the move is kept and made there", async ({ ext }) => {
    const page = await ext.open("/");
    await callLive(ext, page);

    // To a section of a project: the page loads, and the section is shown there.
    await toHolder(ext.sw, { what: "command", command: "navigate", payload: { path: "/proyectos/edificio-norte/", heading: "Ubicación" } });
    await page.waitForURL(`${ORIGIN}/proyectos/edificio-norte/`);
    await expect.poll(() => page.evaluate(() => window.scrollY), { timeout: 10_000 }).toBeGreaterThan(1000);
    await expect(page.locator("[data-voqalize=highlight]")).not.toHaveCount(0);
    await expect.poll(async () => (await status(ext.sw)).sent.filter((e) => e.event === "page_changed").map((e) => e.payload.path)).toContain("/proyectos/edificio-norte/");
    let s = await status(ext.sw);
    expect(s.sent.filter((e) => e.event === "command_failed")).toEqual([]);
    expect(s.sent.find((e) => e.event === "page_changed" && e.payload.path === "/proyectos/edificio-norte/")!.payload).toMatchObject({ kind: "project" });

    // To a section another project lacks: it fails there, and the brain is told.
    await toHolder(ext.sw, { what: "command", command: "navigate", payload: { path: "/proyectos/edificio-sur/", heading: "No existe" } });
    await page.waitForURL(`${ORIGIN}/proyectos/edificio-sur/`);
    await expect.poll(async () => (await status(ext.sw)).sent.filter((e) => e.event === "command_failed").map((e) => String(e.payload.reason))).toContainEqual(expect.stringContaining("No existe"));

    // One call all along, on one tab, with one port: the quote form's frame never joined.
    s = await status(ext.sw);
    expect(s.log.filter((l) => l.includes("connected "))).toHaveLength(1);
    expect(ext.connects).toHaveLength(1);
    expect(s.tabs).toEqual([expect.objectContaining({ url: `${ORIGIN}/proyectos/edificio-sur/`, ports: 1 })]);
    expect(s.state.status).toBe("live");
  });

  test("a project's WhatsApp opens in a tab of its own, which never joins the tab list", async ({ ext }) => {
    const page = await ext.open("/proyectos/edificio-sur/");
    await callLive(ext, page);
    await toHolder(ext.sw, { what: "command", command: "open_whatsapp", payload: {} });
    await expect.poll(async () => (await status(ext.sw)).log.filter((l) => l.includes("open_whatsapp")), { timeout: 10_000 }).toContainEqual(expect.stringContaining("done open_whatsapp"));
    // (A tab the extension opens may load before the context's routes reach
    // it: wa.me's own redirect to api.whatsapp.com counts.)
    await expect.poll(() => ext.ctx.pages().some((p) => /^https:\/\/(wa\.me|api\.whatsapp\.com)\//.test(p.url()))).toBe(true);
    const s = await status(ext.sw);
    expect(s.tabs.map((t) => t.url)).toEqual([`${ORIGIN}/proyectos/edificio-sur/`]);
    expect(s.sent.filter((e) => e.event === "command_failed")).toEqual([]);
    expect(s.state.status).toBe("live");
    // A page with no WhatsApp contact: it fails, and the brain is told.
    await page.bringToFront();
    await page.goto(`${ORIGIN}/`);
    await expect.poll(async () => (await status(ext.sw)).tabs.map((t) => t.url)).toContain(`${ORIGIN}/`);
    await toHolder(ext.sw, { what: "command", command: "open_whatsapp", payload: {} });
    await expect.poll(async () => (await status(ext.sw)).sent.some((e) => e.event === "command_failed")).toBe(true);
  });

  test("with no Ssilva page for 15 s the call ends and the holder closes", async ({ ext }) => {
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
const kept = (page: Page) => page.evaluate(() => sessionStorage.getItem("voqalize.ssilva.call"));

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
    await expect.poll(() => page.evaluate(() => sessionStorage.getItem("voqalize.ssilva.face")?.slice(0, 15) ?? null), { timeout: 8000 }).toBe("data:image/webp");

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
      sessionStorage.setItem("voqalize.ssilva.call", JSON.stringify({
        at: Date.now(), status: "live", muted: false, activity: "listening", language: "en", still: null,
        home: { right: 24, bottom: 24 }, minimised: false,
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

test.describe("the screen follows his words", () => {
  const CUE = { at: "", word: 0, path: null, heading: null, text: null, typology: null, card: null, photo: null, photos: null };
  const sentOf = async (ext: Ext, event: string) => (await status(ext.sw)).sent.filter((e) => e.event === event).map((e) => e.payload);

  test("a project he names is rung on the list, found by its link through a translated page, paging to it", async ({ ext }) => {
    const page = await ext.open("/proyectos/");
    await callLive(ext, page);
    await toHolder(ext.sw, { what: "command", command: "cue", payload: { ...CUE, card: "/edificiocarrera/", text: "EDIFICIO CARRERA" } });
    await toHolder(ext.sw, { what: "emit", name: "botStoppedSpeaking" });
    await expect.poll(async () => (await status(ext.sw)).log.some((l) => l.includes("done show_card")), { timeout: 10_000 }).toBe(true);
    await expect(page.locator(".custom-pagination li.active")).toHaveText("2");
    await expect(page.locator("[data-voqalize=highlight]")).toHaveCount(1);
    // The list's own ring, by the projects' pages: the translated names do not matter.
    await page.waitForTimeout(8200);
    await toHolder(ext.sw, {
      what: "command",
      command: "show_projects",
      payload: { region: "metropolitana", property: "departamento", communes: [], highlight: ["DISTRITO BARROSO", "ESTOCOLMO"], paths: ["/distrito-barroso/", "/estocolmo/"] },
    });
    await expect.poll(async () => (await sentOf(ext, "projects_listed")).length, { timeout: 10_000 }).toBeGreaterThan(0);
    expect((await sentOf(ext, "projects_listed")).at(-1)).toMatchObject({ count: 4 });
    expect(await sentOf(ext, "command_failed")).toEqual([]);
    // A project the list does not have fails, in words.
    await toHolder(ext.sw, { what: "command", command: "cue", payload: { ...CUE, card: "/no-existe/", text: "NO EXISTE" } });
    await toHolder(ext.sw, { what: "emit", name: "botStoppedSpeaking" });
    await expect.poll(async () => (await sentOf(ext, "command_failed")).map((p) => String(p.reason)), { timeout: 10_000 }).toContainEqual(expect.stringContaining("NO EXISTE is not among"));
  });

  test("photos full screen one at a time, a slideshow the visitor's voice stops, and a floor plan", async ({ ext }) => {
    const page = await ext.open("/distrito-barroso/");
    await callLive(ext, page);
    const viewer = page.locator("[data-voqalize=viewer]");
    const shown = async () => (await sentOf(ext, "photo_shown")).at(-1) as Record<string, unknown> | undefined;

    // The page says what its photos show, from their file names.
    await expect.poll(async () => (await sentOf(ext, "page_changed")).at(-1)).toMatchObject({
      photos: ["depto grande", "cowork", "salon", "quincho"],
      amenity_photos: ["piscina", "gourmet"],
    });

    await toHolder(ext.sw, { what: "command", command: "show_photos", payload: { which: "gallery", index: 2, fullscreen: true } });
    await expect(viewer).toHaveCount(1);
    await expect.poll(shown).toMatchObject({ which: "gallery", index: 2, total: 4, caption: "cowork", playing: false });
    await toHolder(ext.sw, { what: "command", command: "step_photo", payload: { back: false } });
    await expect.poll(shown).toMatchObject({ index: 3, caption: "salon" });

    // A slideshow moves on by itself, and stops when the visitor speaks.
    await toHolder(ext.sw, { what: "command", command: "slideshow", payload: { play: true, which: null, seconds: 3 } });
    await expect.poll(shown).toMatchObject({ index: 3, playing: true });
    await expect.poll(shown, { timeout: 5000 }).toMatchObject({ index: 4, playing: true });
    await toHolder(ext.sw, { what: "emit", name: "userStartedSpeaking" });
    await expect.poll(shown).toMatchObject({ playing: false });
    const stopped = (await shown())!.index;
    await page.waitForTimeout(3500);
    expect((await shown())!.index).toBe(stopped);

    // A photo cue, as his voice reaches it: that photo of the amenities.
    await toHolder(ext.sw, { what: "command", command: "cue", payload: { ...CUE, photo: 2, photos: "amenities" } });
    await toHolder(ext.sw, { what: "emit", name: "botStoppedSpeaking" });
    await expect.poll(shown).toMatchObject({ which: "amenities", index: 2, caption: "gourmet" });

    // A floor plan, by its Spanish label on a page translated to English.
    await toHolder(ext.sw, { what: "command", command: "show_floor_plan", payload: { typology: "2D | 2B MARIPOSA" } });
    await expect.poll(shown, { timeout: 8000 }).toMatchObject({ which: "plan", total: 1 });
    expect(String((await shown())!.caption)).toContain("2D | 2B BUTTERFLY");
    await expect.poll(() => viewer.evaluate((h) => h.shadowRoot!.querySelector("img")!.getAttribute("src"))).toContain("DB-204-804.png");
    expect((await sentOf(ext, "typology_shown")).at(-1)).toMatchObject({ label: "2D | 2B BUTTERFLY" });

    await toHolder(ext.sw, { what: "command", command: "close_overlay", payload: {} });
    await expect(viewer).toHaveCount(0);
    expect(await sentOf(ext, "command_failed")).toEqual([]);

    // A price as the translation writes it: "Desde 2.582 UF" is "FROM 2,582 UF".
    await toHolder(ext.sw, { what: "command", command: "show_section", payload: { heading: null, text: "Desde 2.582 UF" } });
    await expect.poll(async () => (await status(ext.sw)).log.some((l) => l.includes("done show_section"))).toBe(true);
    expect(await sentOf(ext, "command_failed")).toEqual([]);
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

    await load(page, "/proyectos/edificio-sur/");
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

    await load(page, "/nosotros/");
    await page.waitForTimeout(800);
    expect((await faceSaw(page)).map(label)).toEqual([]);
  });
});
