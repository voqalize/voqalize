/**
 * The site adapter: drive figurella.cl from the outside, with no help from
 * Figurella's developers.
 *
 * The brain sends a Voqalize `ui-command` ({command, payload}) and `run`
 * performs it on the page in front; the page reports back through `start`,
 * which calls `emit(event, payload)` for every page the visitor lands on, and
 * for what happens to the forms: a fill (`form_state`, `command_done`), her own
 * typing or branch pick (`form_state`), the site's answer to her press of the
 * form's button (`form_result`), or a move left from the last page that could
 * not be finished (`command_failed`).
 *
 * What the site is, for a script like this: WordPress with the LaStudio
 * "lauriel" theme and Elementor, rendered on the server. Every move between
 * pages is a full page load, and a slow one, so a move to another page cannot
 * finish on the page that asked for it: `navigate` (and a form fill from a page
 * without the form) writes what is left to do to `sessionStorage` and loads the
 * page, and the adapter on the next page does it once that page has settled.
 * The window scrolls under a fixed header (130 px, 90 on a phone).
 *
 * Where the content is:
 *
 *   - Every place a move targets is in the catalogue, `anchors.json`, built
 *     from the live site by `backend/knowledge/build.py` and bundled here: a
 *     key per place, with Elementor's stable `.elementor-element-<id>`
 *     selector. The brain sends keys; the words of a section are only ever
 *     looked for when the brain sends words.
 *   - The FAQ is an Essential Addons accordion, one question open at a time,
 *     whose headers carry stable ids (`#cunto-cuesta-figurella`). A question is
 *     opened by clicking its header, as the visitor would (a `#hash` link opens
 *     the wrong one).
 *   - The booking form `#form_agendamiento_figurella` is in the footer of
 *     every page but /franquicias/ and /gracias/; its branch list's values are
 *     the branches' e-mail addresses. The franchise form is on /franquicias/.
 *     Both are Elementor Pro forms sent over AJAX when their button is pressed.
 *   - Elementor's popup 480, a "Agenda tu evaluación gratis aquí" bar, covers
 *     the bottom of the screen on every load: it is closed, as by its ✕.
 *
 * What it never does: press a form's button, submit a form (no `submit()`, no
 * `requestSubmit()`, no click on `#btn-send`), or touch the privacy box. The
 * button is rung once the form is complete, for her to press. There is no
 * Action that could ask for more.
 */

import catalogue from "../../backend/knowledge/L3/anchors.json";

declare global {
  interface Window {
    voqalizeFigurella?: Adapter;
    /** The page's own jQuery, which drives its Slick carousels. */
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
  /** What the widget must keep clear of: the WhatsApp button, the bottom bar,
   *  and a form Javier is filling. */
  obstacles(): Element[];
  /** The Actions `run` performs. */
  readonly commands: readonly string[];
}

type Kind = "home" | "method" | "plans" | "stories" | "convenios" | "franchise" | "faq" | "blog" | "post" | "thanks" | "privacy" | "page";

export interface PageContext {
  url: string;
  path: string;
  title: string;
  kind: Kind;
  /** The catalogue's places this page shows, by key. */
  anchors: string[];
  /** The FAQ's questions on this page, by key. */
  faqs: string[];
  form: "booking" | "franchise" | "none";
}

interface Row {
  key: string;
  selector: string;
  label: string;
  hidden?: boolean;
}

interface Catalogue {
  pages: Record<string, { kind: string; footer: boolean; anchors: Row[] }>;
  footer: Row[];
  post: Row[];
  faqs: Row[];
}

const CATALOGUE = catalogue as unknown as Catalogue;

/** A deep shade of Figurella's pink on a white edge, so the ring reads on the
 *  white pages, the pink hero and the teal form alike. */
const RING = "#B8325C";
const RING_MS = 6000;
const WAIT_MS = 8000;
/** Where a move to another page leaves the rest of it for the next page. */
const THEN_KEY = "voqalize.figurella.then";
/** A move left longer ago than this belongs to some other visit. The home page
 *  can take 15 s to load. */
const THEN_MAX_AGE_MS = 90_000;
/** Her press of a form's button, kept for the thank-you page it may load. */
const SENT_KEY = "voqalize.figurella.sent";
const SENT_MAX_AGE_MS = 120_000;
/** How long the site has to answer her press. */
const ANSWER_WAIT_MS = 30_000;

const FAQ_PATH = "/preguntas-frecuentes/";
const FRANCHISE_PATH = "/franquicias/";
const THANKS_PATH = "/gracias/";

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

const bookingForm = () => document.querySelector<HTMLFormElement>("form#form_agendamiento_figurella");
const franchiseForm = () => document.querySelector<HTMLFormElement>(".elementor-element-5a9d90a7 form");
const isPost = () => Boolean(document.querySelector("h1.entry-title-single"));

function kind(): Kind {
  const path = here();
  const known = CATALOGUE.pages[path]?.kind;
  if (known) return known as Kind;
  if (path === THANKS_PATH) return "thanks";
  if (isPost()) return "post";
  return "page";
}

/** The catalogue's places for the page in front: its own, the post template's
 *  on a post, the footer's where the booking form is, and the FAQ's questions. */
function rows(): Row[] {
  const page = CATALOGUE.pages[here()];
  const out = [...(page?.anchors ?? []), ...(!page && isPost() ? CATALOGUE.post : [])];
  if (bookingForm()) out.push(...CATALOGUE.footer);
  return out;
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

function faqHeaders(): { key: string; header: HTMLElement; label: string }[] {
  const keys = new Map(CATALOGUE.faqs.map((f) => [f.selector.replace(/^#/, ""), f.key]));
  return [...document.querySelectorAll<HTMLElement>(".eael-accordion-header[id]")].map((h) => ({
    key: keys.get(h.id) ?? h.id,
    header: h,
    label: textOf(h.querySelector(".eael-accordion-tab-title") ?? h),
  }));
}

function context(): PageContext {
  const anchors = rows()
    .filter((r) => !r.hidden || r.key === "contacto")
    .filter((r) => visible(query(r.selector)))
    .map((r) => r.key);
  return {
    url: location.href,
    path: here(),
    title: document.title,
    kind: kind(),
    anchors: [...new Set(anchors)],
    faqs: faqHeaders().map((f) => f.key),
    form: bookingForm() ? "booking" : franchiseForm() ? "franchise" : "none",
  };
}

// ─── Scrolling ────────────────────────────────────────────────────────────

/** The height of what is pinned to the top of the viewport: the site's header. */
function headerHeight(): number {
  let h = 0;
  for (const el of document.querySelectorAll<HTMLElement>("#lastudio-header-builder .lahbhinner, .lahb-wrap .lahbhinner, #wpadminbar")) {
    const r = el.getBoundingClientRect();
    if (r.height <= 0 || r.height > 260 || r.top > 40) continue;
    const pos = getComputedStyle(el).position;
    if (pos === "fixed" || pos === "sticky") h = Math.max(h, r.bottom);
  }
  return h || (window.innerWidth >= 1025 ? 130 : 90);
}

function distance(el: Element, align: "top" | "center"): number {
  const r = el.getBoundingClientRect();
  const top = headerHeight() + 12;
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

/** Scroll the window so `el` sits under the header (`top`) or in the middle,
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

/** Scroll so `el` shows: centred when it fits under the header, else at its top. */
async function bringIntoView(el: Element): Promise<void> {
  const room = window.innerHeight - headerHeight() - 24;
  await scrollTo(el, el.getBoundingClientRect().height <= room ? "center" : "top");
}

// ─── The ring ─────────────────────────────────────────────────────────────
// Drawn over the page, never on Figurella's own elements: fixed, and moved
// with its target every frame, so it follows a scroll and an accordion that
// opens under it.

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
      borderRadius: "14px",
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
  if (document.querySelector("style[data-voqalize=figurella]")) return;
  const style = document.createElement("style");
  style.setAttribute("data-voqalize", "figurella");
  style.textContent = `
    @keyframes voqalize-ring {
      0%, 100% { box-shadow: 0 0 0 2px #fff, 0 0 0 3px rgba(184, 50, 92, 0.6); }
      50% { box-shadow: 0 0 0 2px #fff, 0 0 0 14px rgba(184, 50, 92, 0); }
    }
  `;
  (document.head ?? document.documentElement).appendChild(style);
}

/** What to ring for a place: the place, or, when it is much taller than the
 *  screen, its heading's widget. */
function ringTarget(el: HTMLElement): HTMLElement {
  if (el.getBoundingClientRect().height <= window.innerHeight * 0.8) return el;
  const heading = el.querySelector<HTMLElement>(".elementor-widget-heading, .elementor-heading-title, h1, h2, h3");
  return heading?.closest<HTMLElement>(".elementor-widget") ?? heading ?? el;
}

// ─── The bottom bar ────────────────────────────────────────────────────────

const BAR = "#elementor-popup-modal-480";

/** Close the "Agenda tu evaluación gratis aquí" bar as its ✕ would, when it
 *  comes up (Elementor opens it on load, on every page). */
async function closeBottomBar(): Promise<void> {
  const close = await waitFor(() => {
    const x = document.querySelector<HTMLElement>(`${BAR} .dialog-close-button`);
    return x && visible(x) ? x : null;
  }, 20_000);
  if (!close) return;
  // The ✕ is an `<a href="#">`: its handler closes the bar, and the link must
  // not then jump the page to its top under a move.
  close.addEventListener("click", (e) => e.preventDefault(), { capture: true, once: true });
  close.click();
}

// ─── navigate, and the move left for the next page ────────────────────────

/** What is left of a move for the page it opened: a place, words, an FAQ
 *  question, or a whole command (a form fill). */
interface Then {
  anchor?: string | null;
  text?: string | null;
  faq?: string | null;
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
 *  load is not a redirect first. Never a hash: the site's scroll plugin acts on
 *  one and then strips it. */
function sitePath(path: string): URL {
  const target = new URL(path.trim(), location.origin);
  target.hash = "";
  if (!target.pathname.endsWith("/") && !/\.[a-z0-9]{2,4}$/i.test(target.pathname)) target.pathname += "/";
  return target;
}

/** Load another page of the site, leaving `then` for it. */
function goTo(target: URL, then: Then): void {
  try {
    if (then.anchor || then.text || then.faq || then.command) {
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

async function navigate({ path, anchor, text, faq }: { path: string; anchor?: string | null; text?: string | null; faq?: string | null }) {
  if (typeof path !== "string" || !path.trim()) throw new Error("say which page to go to, as a path like /planes/");
  const target = sitePath(path);
  if (target.host.replace(/^www\./, "") !== location.host.replace(/^www\./, "")) {
    throw new Error(`${target.href} is not on figurella.cl; only the site's own pages can be opened here`);
  }
  if (canonical(target.pathname) !== here() || target.search !== location.search) {
    return goTo(target, { anchor: anchor ?? null, text: text ?? null, faq: faq ?? null });
  }
  if (faq) return openFaq({ question: faq });
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
    return then.anchor || then.text || then.faq || then.command ? then : null;
  } catch {
    return null;
  }
}

/** Finish the move the last page started, once this page has settled; a
 *  failure is reported as that move's (a cue's, a fill's). */
async function finishThen(): Promise<void> {
  const then = takeThen();
  if (!then) return;
  await settled();
  const command = then.command && then.command in COMMANDS ? then.command : "cue";
  try {
    if (command !== "cue") {
      const detail = await COMMANDS[command]((then.payload ?? {}) as never);
      if (detail) emit("command_done", { command, detail });
    } else if (then.faq) await openFaq({ question: then.faq });
    else await showSection({ anchor: then.anchor, text: then.text });
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

/** Not the page's content: the header and its menus, the WhatsApp widget, the
 *  bottom bar, and ours. */
const CHROME = "#lastudio-header-builder, .lahb-wrap, .hamburger-menu-wrap, #wa, .wa__btn_popup, #elementor-popup-modal-480, [data-voqalize]";

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

/** A testimonial is a Slick slide: brought into the carousel's view first
 *  (on a narrow screen it shows one at a time), through the page's own Slick. */
async function intoCarousel(el: HTMLElement): Promise<void> {
  if (!el.matches(".slick-slide")) return;
  const slider = el.closest<HTMLElement>(".slick-slider");
  const index = Number(el.getAttribute("data-slick-index"));
  if (!slider || !Number.isFinite(index)) return;
  const shown = () => {
    const s = slider.getBoundingClientRect();
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.left >= s.left - 2 && r.right <= s.right + 2;
  };
  if (shown()) return;
  try {
    window.jQuery?.(slider).slick?.("slickGoTo", index);
  } catch {
    return;
  }
  await waitFor(shown, 1500);
}

async function showSection({ anchor, text }: { anchor?: string | null; text?: string | null }) {
  if (anchor) {
    const el = place(anchor);
    if (!el || !visible(el)) {
      const known = context().anchors.join(", ");
      if (!text) throw new Error(`no place "${anchor}" on ${here()}; it has: ${known || "none"}`);
    } else {
      await bringIntoView(el);
      await intoCarousel(el);
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

// ─── open_faq: one question of the accordion ──────────────────────────────

const isOpen = (header: HTMLElement) => {
  const pane = header.nextElementSibling as HTMLElement | null;
  return header.classList.contains("active") && Boolean(pane && visible(pane));
};

/** Open a question as the page itself would: by clicking its header (Essential
 *  Addons toggles it and closes the one open beside it), else, with no script
 *  on the page, by setting what it sets. */
async function openAccordion(header: HTMLElement): Promise<void> {
  if (isOpen(header)) return;
  header.click();
  if (await waitFor(() => isOpen(header), 1500)) return;
  const list = header.closest(".eael-adv-accordion");
  for (const other of list?.querySelectorAll<HTMLElement>(".eael-accordion-header.active") ?? []) {
    other.classList.remove("active", "show-this");
    const pane = other.nextElementSibling as HTMLElement | null;
    if (pane) pane.style.display = "none";
  }
  header.classList.add("active", "show-this");
  const pane = header.nextElementSibling as HTMLElement | null;
  if (pane) {
    pane.classList.add("active");
    pane.style.display = "block";
  }
}

async function openFaq({ question }: { question: string }) {
  if (!question?.trim()) throw new Error("say which question to open");
  const items = faqHeaders();
  if (!items.length) {
    if (here() !== FAQ_PATH) return goTo(sitePath(FAQ_PATH), { faq: question });
    throw new Error(`the FAQ page shows no questions right now`);
  }
  const item = items.find((i) => i.key === question || i.header.id === question) ?? best(items, (i) => i.label, question);
  if (!item) {
    throw new Error(`no question "${question}" on ${here()}; it has: ${items.map((i) => `${i.key} (${i.label})`).join(" | ")}`);
  }
  await scrollTo(item.header, "top");
  await openAccordion(item.header);
  await sleep(350);
  const pane = item.header.nextElementSibling as HTMLElement | null;
  const group = pane && visible(pane) ? [item.header, pane] : [item.header];
  const box = boxOf(group);
  const tall = box ? box.bottom - box.top > window.innerHeight * 0.7 : false;
  await scrollTo(item.header, tall ? "top" : "center");
  highlight(tall ? item.header : group);
}

// ─── The forms ────────────────────────────────────────────────────────────

type Field = HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement;
type FormName = "booking" | "franchise";

/** Each form's fields, by the name the brain gives them. */
const FIELDS: Record<FormName, Record<string, string>> = {
  booking: {
    nombre: "#form-field-first_name",
    telefono: "#form-field-phone",
    email: "#form-field-email",
    comuna: "#form-field-comuna",
    sucursal: "#form-field-sucursales",
    mensaje: "#form-field-message",
  },
  franchise: {
    nombre: "#form-field-nombre",
    telefono: "#form-field-telefono",
    email: "#form-field-email",
  },
};
const CONSENT = "#form-field-field_826580a";
/** The site's own button on each form: rung for her, never pressed here. */
const BUTTON = "button[type=submit], #btn-send";

const formOf = (name: FormName) => (name === "booking" ? bookingForm() : franchiseForm());

function field(form: HTMLFormElement, selector: string): Field | null {
  return form.querySelector<Field>(selector);
}

/** A select's real choices: not its "Selecciona tu sucursal" prompt. */
const choices = (select: HTMLSelectElement) => [...select.options].filter((o) => o.value !== "");

function valueOf(el: Field): string {
  if (el instanceof HTMLSelectElement) return el.value ? clean(el.options[el.selectedIndex]?.text) : "";
  return clean(el.value);
}

/** Set a field as typing would: the native setter (so nothing the page wraps
 *  around `value` is skipped), then the events its listeners wait for. */
function setField(el: Field, value: string): void {
  const proto =
    el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value")?.set?.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
  el.dispatchEvent(new Event("blur", { bubbles: true }));
}

/** What the site's server takes for a phone: digits, a leading + if given.
 *  Spaces, dashes, dots and brackets go; nothing else changes. */
export const phoneValue = (said: string) => (said.trim().startsWith("+") ? "+" : "") + said.replace(/\D/g, "");

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
/** The server's own check for a phone field (Elementor Pro's `tel`). */
const PHONE = /^[0-9()#&+*\-=.]+$/;

export interface FormStateOut {
  form: FormName;
  filled: string[];
  missing: string[];
  invalid: string[];
  values: Record<string, string>;
  consent: boolean;
  ready: boolean;
  by: "javier" | "visitor";
}

function formState(name: FormName, by: "javier" | "visitor"): FormStateOut | null {
  const form = formOf(name);
  if (!form) return null;
  const filled: string[] = [];
  const missing: string[] = [];
  const invalid: string[] = [];
  const values: Record<string, string> = {};
  for (const [key, selector] of Object.entries(FIELDS[name])) {
    const el = field(form, selector);
    if (!el) continue;
    const v = valueOf(el);
    if (v) {
      filled.push(key);
      values[key] = v;
    } else if (el.required || el.hasAttribute("required")) {
      missing.push(key);
    }
    if (!v) continue;
    if (key === "email" && !EMAIL.test(v)) invalid.push(key);
    if (key === "telefono" && (!PHONE.test(v) || v.replace(/\D/g, "").length < 8)) invalid.push(key);
  }
  const consent = name === "booking" ? Boolean(form.querySelector<HTMLInputElement>(CONSENT)?.checked ?? true) : true;
  return { form: name, filled, missing, invalid, values, consent, ready: !missing.length && !invalid.length, by };
}

/** When Javier last filled a form, for the widget to keep clear of it. */
let lastFill = 0;
/** Set while Javier types, so his own events are not taken for hers. */
let filling = false;

async function fill(name: FormName, p: Record<string, string | null | undefined>): Promise<string> {
  const form = formOf(name);
  const page = name === "booking" ? "/" : FRANCHISE_PATH;
  if (!form) {
    if (here() === canonical(page)) throw new Error(`the ${name} form is not on ${here()} right now`);
    // The form is on another page: it opens, and the fill is made there.
    goTo(sitePath(page), { command: name === "booking" ? "fill_booking_form" : "fill_franchise_form", payload: p });
    return "";
  }
  filling = true;
  lastFill = Date.now();
  const done: string[] = [];
  const notes: string[] = [];
  try {
    await scrollTo(form, form.getBoundingClientRect().height <= window.innerHeight - headerHeight() - 24 ? "center" : "top");
    for (const [key, selector] of Object.entries(FIELDS[name])) {
      const said = p[key];
      if (said === null || said === undefined || !String(said).trim()) continue;
      const el = field(form, selector);
      if (!el) {
        notes.push(`this form has no ${key} field`);
        continue;
      }
      if (el instanceof HTMLSelectElement) {
        const opts = choices(el);
        const opt = opts.find((o) => norm(o.value) === norm(said)) ?? best(opts, (o) => o.text, said);
        if (!opt) {
          notes.push(`no ${key} "${said}" in the form's list; it has: ${opts.map((o) => clean(o.text)).join(", ")}`);
          continue;
        }
        setField(el, opt.value);
        done.push(`${key} (${clean(opt.text)})`);
        continue;
      }
      setField(el, key === "telefono" ? phoneValue(String(said)) : String(said).trim());
      done.push(key);
    }
    const state = formState(name, "javier")!;
    emit("form_state", state);
    const button = form.querySelector<HTMLElement>(BUTTON);
    if (state.ready && button) {
      // Everything is in: the button is hers to press, and the privacy box hers to read.
      const consent = form.querySelector<HTMLElement>(".elementor-field-group-field_826580a");
      await bringIntoView(form);
      highlight(consent ? [consent, button] : [button]);
    } else {
      const next = [...state.invalid, ...state.missing].map((k) => field(form, FIELDS[name][k])).find((el) => el && visible(el));
      const last = done.length ? field(form, FIELDS[name][done[done.length - 1].split(" ")[0]]) : null;
      const ring = (next ?? last)?.closest<HTMLElement>(".elementor-field-group") ?? next ?? form;
      highlight(ring);
    }
    return [
      done.length ? `filled ${done.join(", ")}` : "filled nothing",
      state.missing.length ? `still empty: ${state.missing.join(", ")}` : "every field is filled",
      state.invalid.length ? `the site would refuse: ${state.invalid.join(", ")}` : "",
      ...notes,
      state.ready ? `the button is rung for her to press; she presses it herself` : "",
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

const fillBookingForm = (p: Record<string, string | null | undefined>) => fill("booking", p);
const fillFranchiseForm = (p: Record<string, string | null | undefined>) => fill("franchise", p);

/** The branch each card's "Pedir hora gratis" is for, by the form's option. */
const BRANCH_NAMES: Record<string, string> = {
  huerfanos: "Huérfanos",
  costanera: "Costanera",
  colon: "Colón",
  chicureo: "Chicureo",
  tabancura: "Tabancura",
  vitacura: "Vitacura",
  las_perdices: "Las Perdices",
};

/** Follow her in the forms: her typing, her pick of a branch on a card (which
 *  the site's own "Pedir hora gratis" does not carry to the form; here it
 *  does), her press of a form's button and the site's answer. */
function watchForms(): void {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let last = "";
  const which = (target: EventTarget | null): FormName | null => {
    if (!(target instanceof Element)) return null;
    if (target.closest("form#form_agendamiento_figurella")) return "booking";
    if (target.closest(".elementor-element-5a9d90a7 form")) return "franchise";
    return null;
  };
  const report = (name: FormName) => {
    const state = formState(name, "visitor");
    const key = JSON.stringify(state);
    if (!state || key === last) return;
    last = key;
    emit("form_state", state);
  };
  const typed = (e: Event) => {
    const name = which(e.target);
    if (filling || !name) return;
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => report(name), 900);
  };
  document.addEventListener("input", typed, true);
  document.addEventListener("change", typed, true);

  // A card's "Pedir hora gratis": the site scrolls to the form; the branch
  // goes in with it.
  document.addEventListener(
    "click",
    (e) => {
      if (!(e.target instanceof Element) || here() !== "/") return;
      for (const [key, name] of Object.entries(BRANCH_NAMES)) {
        const row = CATALOGUE.pages["/"]?.anchors.find((r) => r.key === `sucursal_${key}_pedir_hora`);
        if (!row || !e.target.closest(row.selector)) continue;
        const select = bookingForm()?.querySelector<HTMLSelectElement>(FIELDS.booking.sucursal);
        const opt = select && best(choices(select), (o) => o.text, name);
        if (select && opt) {
          setField(select, opt.value);
          report("booking");
        }
        return;
      }
    },
    true,
  );

  // Her press of a form's button. The site checks the fields first (the
  // browser's own check stops the press at the first empty one), then sends
  // the form and shows its answer inside it, or loads its thank-you page.
  let invalidAt = 0;
  document.addEventListener(
    "invalid",
    (e) => {
      const name = which(e.target);
      if (!name || filling || Date.now() - invalidAt < 500) return;
      invalidAt = Date.now();
      const state = formState(name, "visitor");
      emit("form_result", {
        form: name,
        outcome: "error",
        message: "the browser stopped the press: a required field is empty or not valid",
        fields: state ? [...state.missing, ...state.invalid] : [],
      });
    },
    true,
  );
  window.addEventListener(
    "submit",
    (e) => {
      const name = which(e.target);
      if (!name) return;
      try {
        sessionStorage.setItem(SENT_KEY, JSON.stringify({ form: name, at: Date.now() }));
      } catch {
        /* The answer is still read on this page. */
      }
      void awaitAnswer(name, e.target as HTMLFormElement);
    },
    true,
  );
}

let answered = false;

/** The site's answer to her press, read off the form: its success message or
 *  its error, with the fields it marked. */
async function awaitAnswer(name: FormName, form: HTMLFormElement): Promise<void> {
  answered = false;
  const fieldsOf = (): string[] =>
    Object.entries(FIELDS[name])
      .filter(([, sel]) => form.querySelector(sel)?.closest(".elementor-error, [aria-invalid=true]") || form.querySelector(`${sel}[aria-invalid=true]`))
      .map(([key]) => key);
  // An answer already in the form is the last press's: only a new one counts.
  const before = new Set(form.querySelectorAll(".elementor-message"));
  const got = await waitFor(
    () => [...form.querySelectorAll<HTMLElement>(".elementor-message-success, .elementor-message-danger")].find((m) => !before.has(m)),
    ANSWER_WAIT_MS,
  );
  if (!got || answered) return;
  answered = true;
  if (got.matches(".elementor-message-success")) {
    clearSent();
    emit("form_result", { form: name, outcome: "sent", message: textOf(got), fields: [] });
  } else {
    clearSent();
    emit("form_result", { form: name, outcome: "error", message: textOf(got), fields: fieldsOf() });
  }
}

function clearSent(): void {
  try {
    sessionStorage.removeItem(SENT_KEY);
  } catch {
    /* Nothing kept. */
  }
}

/** The thank-you page the site may load after her press: the press went. */
function thankYou(): void {
  if (here() !== THANKS_PATH) return;
  try {
    const raw = sessionStorage.getItem(SENT_KEY);
    if (!raw) return;
    clearSent();
    const sent = JSON.parse(raw) as { form?: FormName; at?: number };
    if (typeof sent.at === "number" && Date.now() - sent.at > SENT_MAX_AGE_MS) return;
    const words = textOf(document.querySelector("h1, h2, .elementor-heading-title") ?? document.body).slice(0, 160);
    emit("form_result", { form: sent.form ?? "booking", outcome: "sent", message: words, fields: [] });
  } catch {
    /* Storage refused: nothing to say. */
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
  open_faq: openFaq,
  fill_booking_form: fillBookingForm,
  fill_franchise_form: fillFranchiseForm,
};

/** How long a move waits for the page in front to finish loading. A move kept
 *  for a loading tab reaches the page once it has parsed, and figurella.cl is
 *  still painting then (its home page loads in 13 s cold): rung that early, a
 *  place is scrolled to before the images above it have pushed it down, and on
 *  a blank page. */
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

/** The WhatsApp button and its chat box (bottom-right, over everything), the
 *  bottom bar while it is up, the back-to-top button, and a form for a minute
 *  and a half after Javier filled it. */
function obstacles(): Element[] {
  const out = [...document.querySelectorAll(`#wa .wa__btn_popup, .wa__popup_chat_box.wa__active, .btn-backtotop, ${BAR} .dialog-widget-content`)];
  const form = bookingForm() ?? franchiseForm();
  if (form && Date.now() - lastFill < 90_000) out.push(form);
  return out.filter((el) => visible(el));
}

if (!window.voqalizeFigurella) {
  styleThePage();
  window.addEventListener("popstate", routeChanged);
  window.addEventListener("hashchange", routeChanged);
  watchForms();
  thankYou();
  void closeBottomBar();
  void finishThen();
  window.voqalizeFigurella = { run, context, start, obstacles, commands: Object.keys(COMMANDS) };
}
