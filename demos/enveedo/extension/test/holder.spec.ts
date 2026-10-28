/**
 * The holder (the offscreen document the call lives in) and the pages that
 * follow it, end to end in the built extension (`VOQALIZE_TEST_BUILD=1`,
 * test/.build/ext): a stand-in call (test/fake-call-client.ts) and a stand-in
 * avatar, pages served at enveedo.com's address, and a made-up
 * API. Headless, and nothing leaves the machine.
 *
 *   - the port protocol: hello, the call press, the state on every page, the
 *     page's events up the port, mute and End;
 *   - a full page load leaves the call alone, and a move sent while the tab is
 *     loading is made on its next page, once it says hello;
 *   - in a call the site's own cross-language links lead to the call
 *     language's twins, and the session carries `site_lang` and `tz`;
 *   - a contact form fill from a page without the form loads /contact and
 *     fills it there; the consent box is never ticked, Submit never pressed;
 *   - a gated eBook opens in a tab of its own, through the service worker,
 *     and an address the site does not link is refused;
 *   - no Enveedo page for 15 s ends the call and closes the holder;
 *   - the microphone permission's branches (granted, denied, prompt answered
 *     in the frame, prompt that needs the tab), with the permission query
 *     stubbed;
 *   - his mouth clock: with his voice on a real WebRTC loopback in the holder,
 *     the face's reads of the relayed clock are fresh while he speaks, on a
 *     busy page too, and read as a stop soon after he stops;
 *   - a page load in the middle of a reply: the next page's face, which
 *     listens only a moment after it is made, gets the reply so far and what
 *     follows, in order, and nothing of a reply that is over or was cut;
 *   - his face's slot on the next page, until its face draws: the card and
 *     its buttons are there, and no picture of him at all, then the live face
 *     fades in.
 */

import { type BrowserContext, chromium, expect, type Page, test as base, type Worker } from "@playwright/test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const EXT = join(here, ".build", "ext");
const ORIGIN = "https://enveedo.com";
const INFO = "https://info.enveedo.com";
const API = "https://api.voqalize.test";
const ADM = "/faq";

/** The header and footer every page has, as HubSpot's theme writes them (the
 *  catalogue's selectors). */
const HEADER = `<header class="header"><nav class="nav"><a class="nav__link" href="https://enveedo.com/es/enveedo_platform">Platform</a>
  <a class="nav__link" href="https://enveedo.com/contact">Contact</a><a class="nav__link" href="https://enveedo.com/book-a-demo?hsLang=en">Book a Demo</a></nav>
  <div class="hs-language-switcher"><a lang="es" href="/es/">Español</a></div></header>`;
const FOOTER = `<footer id="footer"><p>Enveedo · Miami, Florida</p><a href="/frameworks">Frameworks</a></footer>`;

/** The contact form, as HubSpot's React form writes it (its id, its fields'
 *  names, the consent box, Submit). A stand-in for HubSpot's validation marks
 *  an empty required field after a blur. */
const CONTACT = `<div class="hbspt-form"><form class="hs-form" id="hsForm_9ab169f1-2d40-4869-9f6f-943c71b98aa7_1" novalidate>
    <div class="hs_firstname hs-form-field"><input name="firstname" required></div>
    <div class="hs_lastname hs-form-field"><input name="lastname" required></div>
    <div class="hs_phone hs-form-field"><input name="phone" type="tel"></div>
    <div class="hs_country hs-form-field"><select name="country" required><option value="">Please Select</option>
      <option value="Chile">Chile</option><option value="Others">Others</option><option value="United States">United States</option></select></div>
    <div class="hs_email hs-form-field"><input name="email" type="email" required></div>
    <div class="hs_company hs-form-field"><input name="company"></div>
    <div class="hs_message hs-form-field"><textarea name="message"></textarea></div>
    <div class="legal-consent-container"><input type="checkbox" name="LEGAL_CONSENT.subscription_type_44788633" required> I consent</div>
    <input type="submit" class="hs-button" value="Submit">
  </form></div>`;

const PAGES: Record<string, { body: string; title: string; delay?: number; lang?: string }> = {
  // A page whose parse is held 2 s by a script in its body: what is on screen
  // before DOMContentLoaded is the early shell's.
  "/lento": {
    title: "Privacy Policy",
    body: `<body>${HEADER}<main id="main-content"><h1>Privacy Policy</h1><p>Enveedo.</p></main>
      <script src="/slow.js"></script><p>End.</p>${FOOTER}</body>`,
  },
  "/": {
    title: "Enveedo | Prove Your Security Program Is Improving",
    body: `<body>${HEADER}<main id="main-content">
      <div id="hs_cos_wrapper_widget_1752815223713"><h1>Security Program Management. Simplified.</h1><a href="/book-a-demo?hsLang=en">Book a Demo</a></div>
      <div id="hs_cos_wrapper_module_17512825985702" style="margin-top:600px"><h2>Trusted by Security Leaders</h2></div>
      </main>${FOOTER}</body>`,
  },
  [ADM]: {
    title: "FAQ",
    delay: 2500,
    body: `<body>${HEADER}<main id="main-content"><div id="hs_cos_wrapper_module_1716931732754"><h1>Enveedopedia FAQ</h1></div>
      <div id="hs_cos_wrapper_content_bucket-module-7" style="margin-top:900px"><div class="accordion__item"><div class="accordion__header">What is Enveedo?
        <button class="accordion__chevron" aria-controls="accordion-panel-content_bucket-module-7-1" aria-expanded="false"></button></div>
        <div class="accordion__details" id="accordion-panel-content_bucket-module-7-1" style="height:0;overflow:hidden"><p>A platform.</p></div></div></div>
      <script>document.querySelector(".accordion__header").addEventListener("click", function () {
        this.querySelector("button").setAttribute("aria-expanded", "true");
        document.getElementById("accordion-panel-content_bucket-module-7-1").style.height = "80px"; });</script>
      </main>${FOOTER}</body>`,
  },
  "/contact": {
    title: "Contact",
    body: `<body>${HEADER}<main id="main-content"><div id="hs_cos_wrapper_widget_1716878052199"><h2>How can we help?</h2>${CONTACT}</div></main>${FOOTER}</body>`,
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
    const dir = mkdtempSync(join(tmpdir(), "enveedo-ext-"));
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
          body: `<!doctype html><html lang="${page.lang ?? "en"}"><head><title>${page.title}</title></head>${page.body}</html>`,
        });
      }
      if (url.origin === INFO) {
        return route.fulfill({ status: 200, contentType: "text/html; charset=utf-8", body: "<!doctype html><title>eBook</title><p>Download</p>" });
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
    expect((ext.connects[0].body as { init: { surface: string; path: string } }).init).toMatchObject({ surface: "enveedo-ext", path: "/" });
    let s = await status(ext.sw);
    expect(s.session?.session_id).toBe("s-test");
    expect(s.tabs).toHaveLength(1);
    expect(s.tabs[0]).toMatchObject({ url: `${ORIGIN}/`, ports: 1 });

    // The brain hears where the visitor is, from the page, through the holder.
    await expect.poll(async () => (await status(ext.sw)).sent.map((e) => e.event)).toContain("page_changed");
    s = await status(ext.sw);
    expect(s.sent.find((e) => e.event === "page_changed")!.payload).toMatchObject({ path: "/", lang: "en", kind: "home", form: "none" });
    expect((s.sent.find((e) => e.event === "page_changed")!.payload as { anchors: string[] }).anchors).toEqual(
      expect.arrayContaining(["hero", "customers", "menu", "footer"]),
    );
    // The session knows the language the call opens in and the visitor's time zone.
    expect((ext.connects[0].body as { init: Record<string, unknown> }).init).toMatchObject({ site_lang: "en", tz: expect.any(String) });
    // In the call the site's own cross-language links lead to the English twins.
    expect(await page.locator("header nav a").first().getAttribute("href")).toBe("https://enveedo.com/enveedo_platform");
    expect(await page.locator('header nav a[href*="book-a-demo"]').getAttribute("href")).toBe("https://enveedo.com/book-a-demo");
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

  test("a page that loads without focus still reports itself: focus elsewhere is not another tab", async ({ ext }) => {
    const page = await ext.open("/");
    await callLive(ext, page);
    // On screen, never focused: focus is in another window, the address bar or
    // devtools. On a prod call such a page never said it was up, and the brain
    // told the visitor it was taking a while.
    await page.addInitScript(() => {
      Document.prototype.hasFocus = () => false;
    });
    void page.evaluate(() => {
      location.href = "/faq";
    });
    await page.waitForURL((url) => url.pathname.replace(/\/$/, "") === "/faq");
    await expect
      .poll(async () => (await status(ext.sw)).sent.filter((e) => e.event === "page_changed").map((e) => String(e.payload.path).replace(/\/$/, "")))
      .toContain("/faq");
  });

  test("a full page load leaves the call alone, and a move sent while the tab loads is made on its next page", async ({ ext }) => {
    const page = await ext.open("/");
    await callLive(ext, page);

    // The visitor's tab starts loading the next page (held back 2.5 s): the
    // page says it is leaving, and nothing more is sent to it.
    void page.evaluate(() => {
      location.href = "/faq";
    });
    await expect.poll(async () => (await status(ext.sw)).log.some((l) => l.includes("leaving"))).toBe(true);

    // A cue for a place on the next page arrives meanwhile: kept for the tab.
    await toHolder(ext.sw, { what: "command", command: "cue", payload: { at: "", word: 0, path: null, anchor: "faq_what_is", text: null } });
    await toHolder(ext.sw, { what: "emit", name: "botStoppedSpeaking" });
    await expect.poll(async () => (await status(ext.sw)).pending, { timeout: 5000 }).toBe(1);

    // The next page says hello, gets it, and makes it.
    await page.waitForURL(`${ORIGIN}${ADM}`);
    await expect.poll(async () => (await status(ext.sw)).log.some((l) => l.includes("done show_section"))).toBe(true);
    let s = await status(ext.sw);
    expect(s.pending).toBe(0);
    expect(s.log.filter((l) => l.includes("failed"))).toEqual([]);

    // The same call all along: one connect, still live, and the new page follows it.
    expect(s.log.filter((l) => l.includes("connected "))).toHaveLength(1);
    expect(s.state.status).toBe("live");
    await expect(widget(page)).toHaveAttribute("data-status", "live");
    await expect.poll(async () => (await status(ext.sw)).sent.filter((e) => e.event === "page_changed").map((e) => e.payload.path)).toContain(ADM);
    await expect(page.locator("[data-voqalize=highlight]")).toHaveCount(1);

    // A place the page lacks fails, and the brain is told.
    await toHolder(ext.sw, { what: "command", command: "cue", payload: { at: "", word: 0, path: null, anchor: "no_existe", text: null } });
    await toHolder(ext.sw, { what: "emit", name: "botStoppedSpeaking" });
    await expect.poll(async () => (await status(ext.sw)).log.some((l) => l.includes("failed show_section"))).toBe(true);
    await expect.poll(async () => (await status(ext.sw)).sent.some((e) => e.event === "command_failed")).toBe(true);
    s = await status(ext.sw);
    expect(ext.connects).toHaveLength(1);
  });

  test("a gated eBook opens in a tab of its own and stays off the tab list; an address the site does not link is refused", async ({ ext }) => {
    const page = await ext.open("/");
    await callLive(ext, page);
    await toHolder(ext.sw, { what: "command", command: "open_link", payload: { url: `${INFO}/gold-standard-ebook`, label: "The Gold Standard eBook" } });
    await expect.poll(() => ext.ctx.pages().some((p) => p.url().startsWith(`${INFO}/gold-standard`))).toBe(true);
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

  test("a fill from a page without the form opens the contact page and fills it there; consent and Submit stay the visitor's", async ({ ext }) => {
    await ext.ctx.addInitScript(() => {
      const w = window as unknown as { __submits: number; __presses: number };
      w.__submits = 0;
      w.__presses = 0;
      addEventListener("submit", () => w.__submits++, true);
      addEventListener("click", (e) => (e.target as Element)?.matches?.(".hs-button, [type=checkbox]") && w.__presses++, true);
    });
    const page = await ext.open("/");
    await callLive(ext, page);
    await toHolder(ext.sw, {
      what: "command",
      command: "fill_form",
      payload: {
        form: "contact", firstname: "Carolina", lastname: "Rojas", email: "caro@example.com", phone: "+56 9 1234 5678",
        country: "chile", company: "Acme", job_title: null, message: "We need ISO 27001 and Chile's 21.719.",
      },
    });
    await page.waitForURL(`${ORIGIN}/contact`);
    await expect.poll(async () => (await status(ext.sw)).sent.find((e) => e.event === "form_state")?.payload ?? null, { timeout: 15_000 }).toMatchObject({
      form: "contact",
      ready: false,
      missing: ["consent"],
      invalid: [],
      values: { firstname: "Carolina", email: "caro@example.com", country: "Chile" },
      by: "javier",
    });
    await expect.poll(async () => (await status(ext.sw)).sent.find((e) => e.event === "command_done")?.payload ?? null).toMatchObject({
      command: "fill_form",
      detail: expect.stringContaining("press Submit themselves"),
    });
    expect(await page.locator('textarea[name="message"]').inputValue()).toContain("21.719");
    expect(await page.locator('input[type="checkbox"]').isChecked()).toBe(false);
    await new Promise((r) => setTimeout(r, 1000));
    expect(await page.evaluate(() => (window as unknown as { __submits: number }).__submits)).toBe(0);
    expect(await page.evaluate(() => (window as unknown as { __presses: number }).__presses)).toBe(0);
    expect(ext.connects).toHaveLength(1);
  });

  test("with no Enveedo page for 15 s the call ends and the holder closes", async ({ ext }) => {
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
    await expect(page.locator("[data-voqalize=widget] .error-text")).toContainText("blocks the microphone");
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
    expect((await framed).url()).toMatch(/^chrome-extension:\/\/[a-p]{32}\/grant\.html\?lang=en$/);
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
    expect(grantTab.url()).toMatch(/grant\.html\?tab=1&lang=en$/);
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
  first?: { status?: string; min: boolean; muted: boolean; veiled: boolean; pictures: number; text: string; lang: string; transitions: boolean };
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
      const frame = root.querySelector<HTMLElement>(".frame")!;
      t.first = {
        status: root.dataset.status,
        min: root.hasAttribute("data-min"),
        muted: root.hasAttribute("data-muted"),
        veiled: Boolean(root.querySelector(".face.veiled")),
        pictures: [...frame.querySelectorAll<HTMLElement>("*")].filter(
          (el) => el.matches("img, canvas, video") || getComputedStyle(el).backgroundImage !== "none",
        ).length,
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
const kept = (page: Page) => page.evaluate(() => sessionStorage.getItem("voqalize.enveedo.call"));

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
    // No picture of his face is kept for the next page.
    expect(await page.evaluate(() => Object.keys(sessionStorage))).toEqual(["voqalize.enveedo.call"]);

    await page.evaluate(() => {
      location.href = "/lento";
    });
    await page.waitForURL(`${ORIGIN}/lento`, { waitUntil: "commit" });
    await page.waitForFunction(() => (window as unknown as { __early?: { dcl?: number } }).__early?.dcl !== undefined, null, { timeout: 10_000 });
    const e = await early(page);
    // Up at document_start, two seconds ahead of the parse it used to wait for.
    expect(e.host).toBeDefined();
    expect(e.dcl! - e.host!).toBeGreaterThan(1500);
    expect(e.first).toMatchObject({ status: "live", min: true, muted: true, text: "Speaking", lang: "en", transitions: true });
    // His face's slot is empty: no picture of him while the page loads.
    expect(e.first).toMatchObject({ veiled: true, pictures: 0 });
    // A cross-document view transition revealed it, with the widget as its own group.
    expect(e.vt).toBe(true);
    await expect.poll(async () => (await early(page)).vtWidth ?? 0).toBe(1280);

    // The page adopts the widget (one of it), and his live face fades in.
    await expect(page.locator("[data-voqalize=widget]")).toHaveCount(1);
    await expect(page.locator("[data-fake-avatar]")).toHaveCount(1);
    await expect(page.locator("[data-voqalize=widget] .face")).not.toHaveClass(/veiled/);
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
      sessionStorage.setItem("voqalize.enveedo.call", JSON.stringify({
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
  at_ms?: number;
}
const faceSaw = (page: Page) =>
  page.evaluate(() => (window as unknown as { __faceSaw?: FaceSaw[] }).__faceSaw ?? []) as Promise<FaceSaw[]>;
const toFace = async (ext: Ext, msg: Record<string, unknown>) =>
  expect(await toHolder(ext.sw, { what: "avatar", msg })).toEqual({ ok: true });
const label = (s: FaceSaw) => {
  if (!s.ctx) return s.what;
  const at = s.what === "sync" ? s.at_ms : s.from_ms;
  return `${s.what} ${s.ctx}${at === undefined ? "" : `@${at}`}`;
};

/** A full page load in a call, and the new page's face up. */
async function load(page: Page, path: string): Promise<void> {
  await page.goto(ORIGIN + path, { waitUntil: "domcontentloaded" });
  await expect(widget(page)).toHaveAttribute("data-status", "live");
}

test.describe("a page load in the middle of a reply", () => {
  test("the next page's face gets the reply so far (its place on the stream, its cues) and that he is speaking, then what follows, in order, and never the reply's start", async ({ ext }) => {
    const page = await ext.open("/");
    await callLive(ext, page);
    await speaking(ext, page);

    // A reply whose cues have all been sent before the load, as a sentence's
    // phones are, seconds ahead of its audio.
    await toHolder(ext.sw, { what: "emit", name: "botStartedSpeaking" });
    await toFace(ext, { cmd: "sync", ctx: "r1", at_ms: 0, rtp: 48000, rate: 48000 });
    await toFace(ext, { cmd: "cues", ctx: "r1", from_ms: 0, cues: [{ t: 0, v: "B" }] });
    await toFace(ext, { cmd: "cues", ctx: "r1", from_ms: 900, cues: [{ t: 900, v: "C" }] });
    await toFace(ext, { cmd: "sync", ctx: "r1", at_ms: 1000, rtp: 96000, rate: 48000 });
    await expect
      .poll(async () => (await faceSaw(page)).map(label))
      .toEqual(["botStartedSpeaking", "sync r1@0", "cues r1@0", "cues r1@900", "sync r1@1000"]);

    // The reply's start (a sync at 0 ms) is not handed over: a face made
    // mid-reply that hears it thinks it heard the reply begin, and plays the
    // mouth from the first word, behind the voice. The resync places it.

    await load(page, ADM);
    await expect.poll(async () => (await faceSaw(page)).map(label)).toEqual(["cues r1@0", "cues r1@900", "sync r1@1000", "botStartedSpeaking"]);
    expect((await faceSaw(page)).filter((s) => s.what === "sync" && s.at_ms === 0)).toEqual([]);

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

    await load(page, "/contact");
    await page.waitForTimeout(800);
    expect((await faceSaw(page)).map(label)).toEqual([]);
  });
});

/** One look at his face's slot, taken every animation frame of a page from
 *  its very start (an init script): when (ms since the page began), whether
 *  the card and its Mute and End buttons are on screen, whether the slot is
 *  veiled, how many pictures in it can be seen (an image, a canvas or a video
 *  not faded to nothing, or any background image), whether the live face is
 *  in it, and that face's opacity. */
interface FaceLook {
  t: number;
  card: boolean;
  mute: boolean;
  hang: boolean;
  veiled: boolean;
  pictures: number;
  live: boolean;
  opacity: number;
}

async function watchFace(ctx: BrowserContext): Promise<void> {
  await ctx.addInitScript(() => {
    const looks: unknown[] = [];
    const w = window as unknown as { __looks: unknown[]; __dcl?: number };
    w.__looks = looks;
    document.addEventListener("DOMContentLoaded", () => (w.__dcl = performance.now()));
    const shown = (el: Element | null) => Boolean(el && (el as HTMLElement).getClientRects().length);
    /** The opacity it is painted with, up to the card's frame. */
    const seen = (el: Element, frame: Element) => {
      let o = 1;
      for (let at: Element | null = el; at && at !== frame; at = at.parentElement) o *= Number(getComputedStyle(at).opacity);
      return o;
    };
    let until = Infinity;
    const look = () => {
      const root = document.querySelector("[data-voqalize=widget]")?.shadowRoot?.querySelector<HTMLElement>(".root");
      const frame = root?.querySelector(".frame");
      const face = root?.querySelector(".face");
      if (root && frame && face) {
        const live = face.querySelector("[data-fake-avatar]");
        looks.push({
          t: performance.now(),
          card: shown(root.querySelector(".card")),
          mute: shown(root.querySelector(".mute")),
          hang: shown(root.querySelector(".hang")),
          veiled: face.classList.contains("veiled"),
          pictures: [...frame.querySelectorAll("*")].filter((el) =>
            el.matches("img, canvas, video") ? shown(el) && seen(el, frame) > 0 : getComputedStyle(el).backgroundImage !== "none",
          ).length,
          live: Boolean(live),
          opacity: live ? seen(live, frame) : 0,
        });
        if (live && !face.classList.contains("veiled") && until === Infinity) until = performance.now() + 1000;
      }
      if (performance.now() < until) requestAnimationFrame(look);
    };
    requestAnimationFrame(look);
  });
}

const looks = (page: Page) =>
  page.evaluate(() => {
    const w = window as unknown as { __looks: FaceLook[]; __dcl?: number };
    return { looks: w.__looks, dcl: w.__dcl ?? null };
  }) as Promise<{ looks: FaceLook[]; dcl: number | null }>;

test.describe("his face's slot while the next page's face is not drawing yet", () => {
  for (const speaking of [true, false]) {
    test(`in a call (${speaking ? "he speaks" : "he listens"}), the card and its buttons are there at once, no picture of him until the live face draws, then it fades in`, async ({ ext }) => {
      await watchFace(ext.ctx);
      const page = await ext.open("/");
      await callLive(ext, page);
      if (speaking) {
        await toHolder(ext.sw, { what: "emit", name: "botStartedSpeaking" });
        await expect(widget(page)).toHaveAttribute("data-activity", "speaking");
      }
      // A page whose parse a script holds for 2 s: the early shell's widget is
      // all there is of the call meanwhile.
      await page.evaluate(() => {
        location.href = "/lento";
      });
      await page.waitForURL(`${ORIGIN}/lento`, { waitUntil: "commit" });
      await expect(page.locator("[data-voqalize=widget] .face")).not.toHaveClass(/veiled/, { timeout: 15_000 });
      await expect.poll(async () => (await looks(page)).looks.at(-1)?.opacity ?? 0).toBe(1);
      const { looks: all, dcl } = await looks(page);

      // (1) The card, Mute and End are on screen from the first look, well
      // before the page has parsed (and so before the live face exists).
      const loading = all.filter((l) => dcl !== null && l.t < dcl);
      expect(loading.length).toBeGreaterThan(10);
      expect(all[0]).toMatchObject({ card: true, mute: true, hang: true, live: false });
      expect(loading.every((l) => l.card && l.mute && l.hang && !l.live)).toBe(true);

      // (2) No picture of him in the slot while the page loads, nor at any
      // later look until the live face unveils.
      expect(loading.map((l) => l.pictures)).toEqual(loading.map(() => 0));
      const unveiled = all.findIndex((l) => !l.veiled);
      expect(unveiled).toBeGreaterThan(0);
      expect(all.slice(0, unveiled).map((l) => l.pictures)).toEqual(all.slice(0, unveiled).map(() => 0));

      // (3) Then the live face fades in: there, part-way, then whole.
      const after = all.slice(unveiled);
      expect(after.every((l) => l.live && l.card && l.mute && l.hang)).toBe(true);
      expect(after.some((l) => l.opacity > 0 && l.opacity < 1)).toBe(true);
      expect(after.at(-1)!.opacity).toBe(1);
      await expect(widget(page)).toHaveAttribute("data-status", "live");
    });
  }
});
