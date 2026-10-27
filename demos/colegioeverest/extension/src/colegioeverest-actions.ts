/**
 * The site adapter: drive www.colegioeverest.cl from the outside, with no help
 * from the school's developers.
 *
 * The brain sends a Voqalize `ui-command` ({command, payload}) and `run`
 * performs it on the page in front; the page reports back through `start`,
 * which calls `emit(event, payload)` for every page the visitor lands on, and
 * for what happens to the contact form: a fill (`form_state`, `command_done`),
 * the visitor's own typing (`form_state`), the site's answer to their press of
 * "Enviar" (`form_result`), or a move left from the last page that could not be
 * finished (`command_failed`).
 *
 * What the site is, for a script like this: WordPress with GeneratePress and
 * GenerateBlocks, rendered on the server. Every move between pages is a full
 * page load, and the school's server is slow (a few seconds, sometimes far
 * longer), so a move to another page cannot finish on the page that asked for
 * it: `navigate` (and a fill or a slide from a page without its form or slider)
 * writes what is left to do to `sessionStorage` and loads the page, and the
 * adapter on the next page does it once that page has settled. The header is
 * not fixed: a place is scrolled to 20 px under the top of the window.
 *
 * Where the content is:
 *
 *   - Every place a move targets is in the catalogue, `anchors.json`, built
 *     from the live site by `backend/knowledge/build.py` and bundled here: a
 *     key per place, with GenerateBlocks' `.gb-container-<hash>` selector (or
 *     a position in the page's content where a page has no blocks). A hash is
 *     reused across pages, so a key is only ever looked up on its own page.
 *     The header's menus and the footer's address and map are on every page.
 *   - The home page's news carousel and the Infraestructura photo gallery are
 *     slick sliders the page's own jQuery builds; they are moved by clicking
 *     slick's own arrows, as the visitor would.
 *   - The contact form is Contact Form 7 on /contacto/ (`#wpcf7-f1250-p1251-o1`:
 *     your-name, your-email, your-subject, your-message, a Cloudflare Turnstile
 *     check, "Enviar"), sent over AJAX when its button is pressed; CF7 answers
 *     with DOM events (`wpcf7mailsent`, `wpcf7invalid`, `wpcf7spam`,
 *     `wpcf7mailfailed`) and its own line in `.wpcf7-response-output`. The two
 *     other CF7 forms on the site (complaints, jobs) are never touched.
 *
 * What it never does: press "Enviar", submit a form (no `submit()`, no
 * `requestSubmit()`, no click on `.wpcf7-submit`), or touch the Turnstile
 * check. The button is rung once the form is complete, for the visitor to
 * press. There is no Action that could ask for more.
 */

import catalogue from "../../backend/knowledge/L3/anchors.json";

declare global {
  interface Window {
    voqalizeColegioEverest?: Adapter;
    /** The page's own jQuery, which drives its slick sliders. */
    jQuery?: (el: Element) => { slick?: (method: string, ...args: unknown[]) => unknown };
  }
}

export interface RunResult {
  ok: boolean;
  error?: string;
  /** What a move that the brain waits on did, for its `command_done`. */
  detail?: string;
}

export interface Adapter {
  /** Perform one of the brain's page Actions. Never throws. */
  run(command: string, payload: unknown): Promise<RunResult>;
  /** What the visitor is looking at now, as a `page_changed` payload. */
  context(): PageContext;
  /** Report the page, and what moves did or left over, through `emit`, until
   *  the returned stop. The page as it stands is reported first. */
  start(emit: (event: string, payload: unknown) => void): () => void;
  /** What the widget must keep clear of: the contact form while Javier fills it. */
  obstacles(): Element[];
  /** The Actions `run` performs. */
  readonly commands: readonly string[];
}

export interface PageContext {
  url: string;
  path: string;
  title: string;
  /** The catalogue's kind of page (home, admission, contact, …), or post / page. */
  kind: string;
  /** The catalogue's places this page shows, by key. */
  anchors: string[];
  form: "contact" | "none";
}

interface Row {
  key: string;
  selector: string;
  label: string;
  hidden?: boolean;
  optional?: boolean;
}

interface Catalogue {
  pages: Record<string, { kind: string; header?: boolean; footer?: boolean; anchors: Row[] }>;
  header: Row[];
  footer: Row[];
  post: Row[];
}

const CATALOGUE = catalogue as unknown as Catalogue;

/** A burnt orange from the school's own palette (its attributes' colours), on
 *  a white edge, so the ring reads on the white pages and the navy banners alike. */
const RING = "#C35E1E";
const RING_MS = 6000;
const WAIT_MS = 8000;
/** The header is not fixed: a place sits this far under the window's top. */
const SCROLL_GAP = 20;
/** Where a move to another page leaves the rest of it for the next page. */
const THEN_KEY = "voqalize.colegioeverest.then";
/** A move left longer ago than this belongs to some other visit. The school's
 *  server has taken over a minute for a page. */
const THEN_MAX_AGE_MS = 120_000;

const CONTACT_PATH = "/contacto/";
const HOME = "/";
const INFRA_PATH = "/nuestro-colegio/infraestructura/";
/** The contact form's wrapper: the only CF7 form this adapter touches. */
const CONTACT_FORM = "#wpcf7-f1250-p1251-o1";

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const clean = (s: string | null | undefined) => (s ?? "").replace(/\s+/g, " ").trim();
/**
 * For matching what the brain said against what the page shows: lower case,
 * without accents (ó → o, ñ → n), with straight quotes, and without the
 * opening "¿"/"¡" and closing punctuation.
 */
export const norm = (s: string | null | undefined) =>
  clean(s)
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[‘’´`]/g, "'")
    .replace(/[“”«»]/g, '"')
    .replace(/[¿¡]/g, "")
    .replace(/^[\s"']+|[\s"'.:;,?!]+$/g, "")
    .replace(/\s+/g, " ")
    .trim();

/** Laid out on the page at all, whether or not it is on screen. */
const visible = (el: Element | null | undefined): el is HTMLElement => {
  if (!el) return false;
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
};

/** An element's own words, as the page had them before any translation. */
const textOf = (el: Element) =>
  clean(el.getAttribute("data-voqalize-text") ?? ((el as HTMLElement).innerText || el.textContent));

async function waitFor<T>(fn: () => T | null | undefined | false, ms = WAIT_MS): Promise<T | null> {
  const until = Date.now() + ms;
  for (;;) {
    const v = fn();
    if (v) return v;
    if (Date.now() > until) return null;
    await sleep(100);
  }
}

// ─── Where we are ───────────────────────────────────────────────────────────

/** The site's own path shape: lower case, with its trailing slash. */
export const canonical = (p: string) => {
  const path = (p || "/").toLowerCase().replace(/\/{2,}/g, "/").replace(/^\/+|\/+$/g, "");
  return path ? `/${path}/` : "/";
};
const here = () => canonical(location.pathname);

const contactForm = () => document.querySelector<HTMLFormElement>(`${CONTACT_FORM} form`);
const isPost = () => Boolean(document.body?.classList.contains("single-post"));

function kind(): string {
  const known = CATALOGUE.pages[here()]?.kind;
  if (known) return known;
  return isPost() ? "post" : "page";
}

/** The catalogue's places for the page in front: its own (the post template's
 *  on a news post), then the header's and the footer's. */
function rows(): Row[] {
  const page = CATALOGUE.pages[here()];
  if (page) {
    return [...page.anchors, ...(page.header !== false ? CATALOGUE.header : []), ...(page.footer !== false ? CATALOGUE.footer : [])];
  }
  return [...(isPost() ? CATALOGUE.post : []), ...CATALOGUE.header, ...CATALOGUE.footer];
}

function query(selector: string): HTMLElement | null {
  try {
    const all = [...document.querySelectorAll<HTMLElement>(selector)];
    return all.find(visible) ?? all[0] ?? null;
  } catch {
    return null;
  }
}

function place(key: string): HTMLElement | null {
  const row = rows().find((r) => r.key === key);
  return row ? query(row.selector) : null;
}

function context(): PageContext {
  const anchors = rows()
    .filter((r) => !r.hidden)
    .filter((r) => visible(query(r.selector)))
    .map((r) => r.key);
  return {
    url: location.href,
    path: here(),
    title: document.title,
    kind: kind(),
    anchors: [...new Set(anchors)],
    form: contactForm() ? "contact" : "none",
  };
}

// ─── Scrolling ────────────────────────────────────────────────────────────

/** The height of what is pinned to the top of the viewport: nothing on this
 *  site but the WordPress admin bar of a signed-in editor. */
function headerHeight(): number {
  const bar = document.getElementById("wpadminbar");
  const r = bar?.getBoundingClientRect();
  return r && r.height > 0 && r.top <= 0 && getComputedStyle(bar!).position === "fixed" ? r.bottom : 0;
}

function distance(el: Element, align: "top" | "center"): number {
  const r = el.getBoundingClientRect();
  const top = headerHeight() + SCROLL_GAP;
  if (align === "center") {
    const room = window.innerHeight - top;
    return r.top - (top + Math.max(0, (room - r.height) / 2));
  }
  return r.top - top;
}

async function scrollEnded(): Promise<void> {
  let last = -1;
  let still = 0;
  const until = Date.now() + 2500;
  while (Date.now() < until) {
    await sleep(80);
    if (Math.abs(window.scrollY - last) < 1) {
      if (++still >= 3) return;
    } else {
      still = 0;
    }
    last = window.scrollY;
  }
}

/** Scroll the window so `el` sits under the top (`top`) or in the middle,
 *  measuring again as images load. */
async function scrollTo(el: Element, align: "top" | "center" = "top"): Promise<void> {
  for (let pass = 0; pass < 3; pass++) {
    const delta = distance(el, align);
    if (Math.abs(delta) < 12) return;
    const max = document.documentElement.scrollHeight - window.innerHeight;
    const y = Math.min(Math.max(window.scrollY + delta, 0), max);
    if (Math.abs(y - window.scrollY) < 8) return;
    window.scrollTo({ top: y, behavior: "smooth" });
    await scrollEnded();
  }
}

/** Scroll so `el` shows: centred when it fits, else at its top. */
async function bringIntoView(el: Element): Promise<void> {
  const room = window.innerHeight - headerHeight() - SCROLL_GAP - 24;
  await scrollTo(el, el.getBoundingClientRect().height <= room ? "center" : "top");
}

// ─── The ring ─────────────────────────────────────────────────────────────
// Drawn over the page, never on the school's own elements: fixed, and moved
// with its target every frame, so it follows a scroll and a slider under it.

let rings: { el: HTMLElement; targets: Element[] }[] = [];
let ringFrame = 0;
let ringTimer: ReturnType<typeof setTimeout> | null = null;

function boxOf(targets: Element[]) {
  const rs = targets.filter(visible).map((el) => el.getBoundingClientRect());
  if (!rs.length) return null;
  return {
    left: Math.min(...rs.map((r) => r.left)),
    top: Math.min(...rs.map((r) => r.top)),
    right: Math.max(...rs.map((r) => r.right)),
    bottom: Math.max(...rs.map((r) => r.bottom)),
  };
}

function follow(): void {
  for (const ring of rings) {
    const b = boxOf(ring.targets);
    if (!b) {
      ring.el.style.opacity = "0";
      continue;
    }
    Object.assign(ring.el.style, {
      transform: `translate(${b.left - 6}px, ${b.top - 6}px)`,
      width: `${b.right - b.left + 12}px`,
      height: `${b.bottom - b.top + 12}px`,
    });
  }
  ringFrame = requestAnimationFrame(follow);
}

/** Ring each group: one element, or several ringed as one box. */
function highlight(...groups: (Element | Element[])[]): void {
  clearHighlight();
  for (const group of groups) {
    const targets = Array.isArray(group) ? group : [group];
    if (!boxOf(targets)) continue;
    const el = document.createElement("div");
    el.setAttribute("data-voqalize", "highlight");
    Object.assign(el.style, {
      position: "fixed",
      left: "0",
      top: "0",
      border: `3px solid ${RING}`,
      borderRadius: "12px",
      boxShadow: `0 0 0 2px #fff`,
      pointerEvents: "none",
      zIndex: "2147483000",
      opacity: "0",
      transition: "opacity 300ms ease",
      animation: "voqalize-ring 1.4s ease-in-out 3",
    });
    document.body.appendChild(el);
    rings.push({ el, targets });
  }
  follow();
  requestAnimationFrame(() => rings.forEach((r) => (r.el.style.opacity = "1")));
  ringTimer = setTimeout(clearHighlight, RING_MS);
}

function clearHighlight(): void {
  if (ringTimer) clearTimeout(ringTimer);
  cancelAnimationFrame(ringFrame);
  rings.forEach((r) => r.el.remove());
  rings = [];
}

function styleThePage(): void {
  if (document.querySelector("style[data-voqalize=colegioeverest]")) return;
  const style = document.createElement("style");
  style.setAttribute("data-voqalize", "colegioeverest");
  style.textContent = `
    @keyframes voqalize-ring {
      0%, 100% { box-shadow: 0 0 0 2px #fff, 0 0 0 3px rgba(195, 94, 30, 0.6); }
      50% { box-shadow: 0 0 0 2px #fff, 0 0 0 14px rgba(195, 94, 30, 0); }
    }
  `;
  (document.head ?? document.documentElement).appendChild(style);
}

/** What to ring for a place: the place, or, when it is much taller than the
 *  screen, its heading. */
function ringTarget(el: HTMLElement): HTMLElement {
  if (el.getBoundingClientRect().height <= window.innerHeight * 0.8) return el;
  const heading = el.querySelector<HTMLElement>("h1, h2, h3, .gb-headline");
  return heading && visible(heading) ? heading : el;
}

// ─── navigate, and the move left for the next page ────────────────────────

/** What is left of a move for the page it opened: a place, words, or a whole
 *  command (a form fill, a slide). */
interface Then {
  anchor?: string | null;
  text?: string | null;
  command?: string;
  payload?: unknown;
}

/** The page has settled: loaded (or long enough), its fonts in, and the DOM
 *  quiet a moment. */
async function settled(): Promise<void> {
  if (document.readyState !== "complete") {
    await Promise.race([new Promise<void>((r) => window.addEventListener("load", () => r(), { once: true })), sleep(6000)]);
  }
  await Promise.race([document.fonts?.ready, sleep(2000)]);
  await new Promise<void>((resolve) => {
    let timer = setTimeout(done, 400);
    const obs = new MutationObserver(() => {
      clearTimeout(timer);
      timer = setTimeout(done, 400);
    });
    obs.observe(document.body, { childList: true, subtree: true });
    const cap = setTimeout(done, 2500);
    function done() {
      obs.disconnect();
      clearTimeout(timer);
      clearTimeout(cap);
      resolve();
    }
  });
}

/** A path of the site as WordPress serves it: with its trailing slash, so the
 *  load is not a redirect first, and without a hash. */
function sitePath(path: string): URL {
  const target = new URL(path.trim(), location.origin);
  target.hash = "";
  if (!target.pathname.endsWith("/") && !/\.[a-z0-9]{2,4}$/i.test(target.pathname)) target.pathname += "/";
  return target;
}

/** Load another page of the site, leaving `then` for it. */
function goTo(target: URL, then: Then): void {
  try {
    if (then.anchor || then.text || then.command) {
      sessionStorage.setItem(THEN_KEY, JSON.stringify({ ...then, at: Date.now() }));
    } else {
      sessionStorage.removeItem(THEN_KEY);
    }
  } catch {
    // Storage refused: the page still loads, at its top.
  }
  clearHighlight();
  location.assign(target.pathname + target.search);
}

const sameSite = (host: string) => host.replace(/^www\./, "") === location.host.replace(/^www\./, "");

async function navigate({ path, anchor, text }: { path: string; anchor?: string | null; text?: string | null }) {
  if (typeof path !== "string" || !path.trim()) throw new Error("say which page to go to, as a path like /contacto/");
  const target = sitePath(path);
  if (!sameSite(target.host)) {
    throw new Error(`${target.href} is not on colegioeverest.cl; only the site's own pages can be opened here`);
  }
  if (canonical(target.pathname) !== here() || target.search !== location.search) {
    return goTo(target, { anchor: anchor ?? null, text: text ?? null });
  }
  if (anchor || text) return showSection({ anchor, text });
  window.scrollTo({ top: 0, behavior: "smooth" });
  await scrollEnded();
}

/** What the last page's move left to do here, taken once. */
function takeThen(): Then | null {
  try {
    const raw = sessionStorage.getItem(THEN_KEY);
    if (!raw) return null;
    sessionStorage.removeItem(THEN_KEY);
    const then = JSON.parse(raw) as Then & { at?: number };
    if (typeof then.at === "number" && Date.now() - then.at > THEN_MAX_AGE_MS) return null;
    return then.anchor || then.text || then.command ? then : null;
  } catch {
    return null;
  }
}

/** Finish the move the last page started, once this page has settled; a
 *  failure is reported as that move's (a cue's, a fill's, a slide's). */
async function finishThen(): Promise<void> {
  const then = takeThen();
  if (!then) return;
  await settled();
  const command = then.command && then.command in COMMANDS ? then.command : "cue";
  try {
    if (command !== "cue") {
      const detail = await COMMANDS[command]((then.payload ?? {}) as never);
      if (detail) emit("command_done", { command, detail });
    } else await showSection({ anchor: then.anchor, text: then.text });
  } catch (error) {
    emit("command_failed", { command, reason: error instanceof Error ? error.message : String(error) });
  }
}

// ─── show_section ─────────────────────────────────────────────────────────

/** The best match for what the brain said among `items`: the same words, then
 *  one that starts with them, then one they start with, then one that holds
 *  them. */
function best<T>(items: T[], text: (t: T) => string, said: string): T | null {
  const want = norm(said);
  if (!want) return null;
  const t = (i: T) => norm(text(i));
  return (
    items.find((i) => t(i) === want) ??
    items.find((i) => t(i).startsWith(want)) ??
    items.find((i) => want.startsWith(t(i)) && t(i).length > 3) ??
    items.find((i) => t(i).includes(want)) ??
    null
  );
}

/** Not the page's content: the header and its menus, and ours. */
const CHROME = "#masthead, #secondary-navigation, #site-navigation, [data-voqalize]";

/** The smallest laid-out element whose text holds `text`; a word inside a
 *  paragraph is read with its paragraph. */
function smallestContaining(text: string): HTMLElement | null {
  const want = norm(text);
  if (!want) return null;
  let found: HTMLElement | null = null;
  let bestLen = Infinity;
  for (const el of document.body.querySelectorAll<HTMLElement>("*")) {
    if (/^(SCRIPT|STYLE|NOSCRIPT|svg|OPTION|SELECT)$/i.test(el.tagName) || !visible(el) || el.closest(CHROME)) continue;
    const t = norm(el.getAttribute("data-voqalize-text") ?? el.textContent);
    if (!t.includes(want) || t.length >= bestLen) continue;
    found = el;
    bestLen = t.length;
  }
  if (found && /^(STRONG|B|EM|I|SPAN|A|BR)$/.test(found.tagName)) {
    const p = found.closest<HTMLElement>("p, li, h1, h2, h3, h4, h5");
    if (p && clean(p.textContent).length < 600) return p;
  }
  return found;
}

async function showSection({ anchor, text }: { anchor?: string | null; text?: string | null }) {
  if (anchor) {
    const el = place(anchor);
    if (!el || !visible(el)) {
      const known = context().anchors.join(", ");
      if (!text) throw new Error(`no place "${anchor}" on ${here()}; it has: ${known || "none"}`);
    } else {
      await bringIntoView(el);
      highlight(ringTarget(el));
      return;
    }
  }
  if (!text) throw new Error("say which place or words to show");
  const el = smallestContaining(text);
  if (!el) throw new Error(`"${text}" is not on ${here()}; its places are: ${context().anchors.join(", ")}`);
  await bringIntoView(el);
  highlight(ringTarget(el));
}

// ─── slide: the news carousel and the photo gallery ───────────────────────

type SliderName = "noticias" | "galeria";

/** Each slider: its page, the place it is, and its own arrows' places. */
const SLIDERS: Record<SliderName, { page: string; place: string; prev: string; next: string; words: string }> = {
  noticias: { page: HOME, place: "noticias_carrusel", prev: "noticias_anterior", next: "noticias_siguiente", words: "the news carousel" },
  galeria: { page: INFRA_PATH, place: "galeria", prev: "galeria_anterior", next: "galeria_siguiente", words: "the photo gallery" },
};

/** What the slider shows first: slick marks it `slick-current`. */
function currentSlide(slider: HTMLElement): { index: string; words: string } {
  const cur = slider.querySelector<HTMLElement>(".slick-current") ?? slider.querySelector<HTMLElement>(".slick-active");
  if (!cur) return { index: "", words: "" };
  const title = cur.querySelector<HTMLElement>("h2, h3, h4, .titulo, a[title]");
  const img = cur.querySelector<HTMLImageElement>("img[alt]");
  return {
    index: cur.getAttribute("data-slick-index") ?? "",
    words: clean(title ? textOf(title) : (img?.alt ?? textOf(cur))).slice(0, 120),
  };
}

async function slide({ slider, direction }: { slider: SliderName; direction?: "next" | "prev" }): Promise<string> {
  const spec = SLIDERS[slider];
  if (!spec) throw new Error(`no slider "${slider}"; there are: ${Object.keys(SLIDERS).join(", ")}`);
  const box = place(spec.place);
  if (!box) {
    if (here() === spec.page) throw new Error(`${spec.words} is not on ${here()} right now`);
    // The slider is on another page: it opens, and the slide is made there.
    goTo(sitePath(spec.page), { command: "slide", payload: { slider, direction } });
    return "";
  }
  const dir = direction === "prev" ? "prev" : "next";
  await bringIntoView(box);
  const before = currentSlide(box);
  const arrow = place(dir === "prev" ? spec.prev : spec.next);
  if (arrow) arrow.click();
  // slick moves on the arrow's click; with no slick on the page (or an arrow
  // hidden at this width), its jQuery API does the same.
  if (!(await waitFor(() => currentSlide(box).index !== before.index, 1200))) {
    try {
      window.jQuery?.(box).slick?.(dir === "prev" ? "slickPrev" : "slickNext");
    } catch {
      /* No slick here: the click was all there was. */
    }
    await waitFor(() => currentSlide(box).index !== before.index, 800);
  }
  highlight(box);
  const now = currentSlide(box);
  if (!arrow && now.index === before.index) throw new Error(`${spec.words} has no ${dir} arrow on this page`);
  return `moved ${spec.words} ${dir === "prev" ? "back" : "on"}` + (now.words ? `; it now shows: ${now.words}` : "");
}

// ─── The contact form ─────────────────────────────────────────────────────

type Field = HTMLInputElement | HTMLTextAreaElement;

/** The contact form's fields, by the name the brain gives them. */
const FIELDS: Record<string, string> = {
  nombre: 'input[name="your-name"]',
  email: 'input[name="your-email"]',
  asunto: 'input[name="your-subject"]',
  mensaje: 'textarea[name="your-message"]',
};
/** The site's own button: rung for the visitor, never pressed here. */
const BUTTON = ".wpcf7-submit";
/** The Cloudflare check beside it: rung with the button, never touched. */
const CAPTCHA = ".wpcf7-turnstile, .cf-turnstile";

function field(form: HTMLFormElement, selector: string): Field | null {
  return form.querySelector<Field>(selector);
}

/** Set a field as typing would: the native setter (so nothing the page wraps
 *  around `value` is skipped), then the events its listeners wait for. */
function setField(el: Field, value: string): void {
  const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value")?.set?.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
  el.dispatchEvent(new Event("blur", { bubbles: true }));
}

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

const required = (el: Field) =>
  el.required || el.getAttribute("aria-required") === "true" || el.classList.contains("wpcf7-validates-as-required");

export interface FormStateOut {
  form: "contact";
  filled: string[];
  missing: string[];
  invalid: string[];
  values: Record<string, string>;
  ready: boolean;
  by: "javier" | "visitor";
}

function formState(by: "javier" | "visitor"): FormStateOut | null {
  const form = contactForm();
  if (!form) return null;
  const filled: string[] = [];
  const missing: string[] = [];
  const invalid: string[] = [];
  const values: Record<string, string> = {};
  for (const [key, selector] of Object.entries(FIELDS)) {
    const el = field(form, selector);
    if (!el) continue;
    const v = clean(el.value);
    if (v) {
      filled.push(key);
      values[key] = v;
    } else if (required(el)) {
      missing.push(key);
    }
    if (v && key === "email" && !EMAIL.test(v)) invalid.push(key);
  }
  return { form: "contact", filled, missing, invalid, values, ready: !missing.length && !invalid.length, by };
}

/** When Javier last filled the form, for the widget to keep clear of it. */
let lastFill = 0;
/** Set while Javier types, so his own events are not taken for the visitor's. */
let filling = false;

async function fillContactForm(p: Record<string, string | null | undefined>): Promise<string> {
  const form = contactForm();
  if (!form) {
    if (here() === CONTACT_PATH) throw new Error(`the contact form is not on ${here()} right now`);
    // The form is on the contact page: it opens, and the fill is made there.
    goTo(sitePath(CONTACT_PATH), { command: "fill_contact_form", payload: p });
    return "";
  }
  filling = true;
  lastFill = Date.now();
  const done: string[] = [];
  const notes: string[] = [];
  try {
    await bringIntoView(form);
    for (const [key, selector] of Object.entries(FIELDS)) {
      const said = p[key];
      if (said === null || said === undefined || !String(said).trim()) continue;
      const el = field(form, selector);
      if (!el) {
        notes.push(`this form has no ${key} field`);
        continue;
      }
      setField(el, key === "mensaje" ? String(said).trim() : clean(String(said)));
      done.push(key);
    }
    const state = formState("javier")!;
    emit("form_state", state);
    const button = form.querySelector<HTMLElement>(BUTTON);
    if (state.ready && button) {
      // Everything is in: the button, and the check above it, are the visitor's.
      const check = form.querySelector<HTMLElement>(CAPTCHA);
      await bringIntoView(button);
      highlight(check && visible(check) ? [check, button] : [button]);
    } else {
      const next = [...state.invalid, ...state.missing].map((k) => field(form, FIELDS[k])).find((el) => el && visible(el));
      const last = done.length ? field(form, FIELDS[done[done.length - 1]]) : null;
      const ring = (next ?? last)?.closest<HTMLElement>("p, .wpcf7-form-control-wrap") ?? next ?? form;
      highlight(ring);
    }
    return [
      done.length ? `filled ${done.join(", ")}` : "filled nothing",
      state.missing.length ? `still empty: ${state.missing.join(", ")}` : "every required field is filled",
      state.invalid.length ? `the site would refuse: ${state.invalid.join(", ")}` : "",
      ...notes,
      state.ready ? `«Enviar» is rung for the visitor to press, after the site's security check; they press it themselves` : "",
    ]
      .filter(Boolean)
      .join("; ");
  } finally {
    // The page's own handlers run on the events just sent; let them pass.
    setTimeout(() => {
      filling = false;
    }, 50);
  }
}

/** CF7's answers to the visitor's press, by its DOM event. */
const CF7: Record<string, "sent" | "invalid" | "spam" | "failed"> = {
  wpcf7mailsent: "sent",
  wpcf7invalid: "invalid",
  wpcf7spam: "spam",
  wpcf7mailfailed: "failed",
};

/** Follow the visitor in the contact form: their typing, and the site's
 *  answer to their press of "Enviar". The complaints and jobs forms are not
 *  followed: Javier has nothing to do with them. */
function watchForm(): void {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let last = "";
  const ours = (target: EventTarget | null) => target instanceof Element && Boolean(target.closest(CONTACT_FORM));
  const report = () => {
    const state = formState("visitor");
    const key = JSON.stringify(state);
    if (!state || key === last) return;
    last = key;
    emit("form_state", state);
  };
  const typed = (e: Event) => {
    if (filling || !ours(e.target)) return;
    if (timer) clearTimeout(timer);
    timer = setTimeout(report, 900);
  };
  document.addEventListener("input", typed, true);
  document.addEventListener("change", typed, true);

  for (const [name, outcome] of Object.entries(CF7)) {
    document.addEventListener(
      name,
      (e) => {
        if (!ours(e.target)) return;
        // CF7 writes its line into the form a moment after its event.
        setTimeout(() => {
          const form = contactForm();
          const line = form?.querySelector(".wpcf7-response-output");
          const fields = form
            ? Object.entries(FIELDS)
                .filter(([, sel]) => form.querySelector(sel)?.matches(".wpcf7-not-valid, [aria-invalid=true]"))
                .map(([key]) => key)
            : [];
          emit("form_result", { form: "contact", outcome, message: line ? textOf(line) : "", fields });
        }, 150);
      },
      true,
    );
  }
}

// ─── Reporting ────────────────────────────────────────────────────────────

let emitter: ((event: string, payload: unknown) => void) | null = null;
/** What happened before anyone listened: a move left from the last page that
 *  finished, or failed, before the call reconnected on this one. */
const backlog: [string, unknown][] = [];
function emit(event: string, payload: unknown): void {
  if (emitter) emitter(event, payload);
  else backlog.push([event, payload]);
}

let lastUrl: string | null = null;
/** Every move between pages loads a whole page, so this only sees a change of
 *  hash or a history step the page made without loading. */
function routeChanged(): void {
  const now = location.origin + location.pathname + location.search;
  if (now === lastUrl) return;
  lastUrl = now;
  clearHighlight();
  if (emitter) emitter("page_changed", context());
}

function start(next: (event: string, payload: unknown) => void): () => void {
  emitter = next;
  lastUrl = location.origin + location.pathname + location.search;
  next("page_changed", context());
  for (const [event, payload] of backlog.splice(0)) next(event, payload);
  return () => {
    if (emitter === next) emitter = null;
  };
}

/** The page's Actions. Each returns what it did when the brain waits on it. */
const COMMANDS: Record<string, (payload: never) => Promise<string | void>> = {
  navigate,
  show_section: showSection,
  slide,
  fill_contact_form: fillContactForm,
};

/** How long a move waits for the page in front to finish loading. A move kept
 *  for a loading tab reaches the page once it has parsed, and the school's
 *  pages are still painting then: rung that early, a place is scrolled to
 *  before the images above it have pushed it down. */
const LOADED_WAIT_MS = 8000;

async function loaded(): Promise<void> {
  if (document.readyState === "complete") return;
  await Promise.race([new Promise<void>((r) => window.addEventListener("load", () => r(), { once: true })), sleep(LOADED_WAIT_MS)]);
  await sleep(300);
}

async function run(command: string, payload: unknown): Promise<RunResult> {
  const fn = COMMANDS[command];
  if (!fn) return { ok: false, error: `the page cannot ${command}` };
  await loaded();
  try {
    const detail = await fn((payload ?? {}) as never);
    return detail ? { ok: true, detail } : { ok: true };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
}

/** The contact form, for a minute and a half after Javier filled it: nothing
 *  else on this site sits in a corner. */
function obstacles(): Element[] {
  const form = contactForm();
  return form && Date.now() - lastFill < 90_000 && visible(form) ? [form] : [];
}

if (!window.voqalizeColegioEverest) {
  styleThePage();
  window.addEventListener("popstate", routeChanged);
  window.addEventListener("hashchange", routeChanged);
  watchForm();
  void finishThen();
  window.voqalizeColegioEverest = { run, context, start, obstacles, commands: Object.keys(COMMANDS) };
}
