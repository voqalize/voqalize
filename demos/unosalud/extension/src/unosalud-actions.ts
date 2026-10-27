/**
 * The site adapter: drive www.unosalud.cl (and, through `booking-actions.ts`,
 * the booking at /agenda-tu-hora/) from the outside, with no help from Uno
 * Salud's developers.
 *
 * The brain sends a Voqalize `ui-command` ({command, payload}) and `run`
 * performs it on the page in front; the page reports back through `start`,
 * which calls `emit(event, payload)` for every page the visitor lands on (with
 * a clinic's own facts on a clinic page), for the booking's state, for the
 * lead forms' state, and for a move that could not be finished after a page
 * load.
 *
 * What the site is, for a script like this: WordPress, a custom theme on
 * Bootstrap 4, jQuery and Flickity, rendered on the server, with no client
 * router: every move to another page is a full page load, so `navigate`
 * leaves what is left to do (a place, words, an FAQ, a form) in
 * `sessionStorage` and loads the page, and the adapter on the next page does
 * it once that page has settled. The /landing/ pages are Elementor documents
 * with a slimmer header. The window scrolls (`html { scroll-behavior: smooth }`)
 * under a header that turns fixed (121 px) once the page is scrolled; the
 * clinic list on /clinicas/ scrolls by itself.
 *
 * Places are the brain's catalogue's (`catalogue.ts`), by key. Hidden content
 * is revealed the way a visitor reveals it: a Bootstrap tab pane by its pill,
 * an FAQ by its question (Bootstrap collapse: open is `.show`, whatever
 * `aria-expanded` says), an Elementor accordion item by its summary, a
 * Flickity cell by pausing the carousel and selecting the cell.
 *
 * Forms are filled, never sent (`guards.ts`): no submit, no Enter, no press of
 * ENVIAR. The RUT is the visitor's to type; Javier only points at the field.
 */

import { type ClinicInfo, clinicInfo, isClinicPage } from "./anchors";
import { bookingCommands, bookingContext, lastMove as bookingMovedAt, watchBooking } from "./booking-actions";
import { canonical, onPage, type Row, row, rowsFor } from "./catalogue";
import { GuardError, press } from "./guards";
import {
  best, boxOf, chileanMobile, clean, clearHighlight, highlight, inOrder, leave, type Leftover, norm, pickOption,
  scrollTo, scrollToTopOfPage, setValue, settled, shown, sleep, styleThePage, takeLeftover, visible, waitFor,
} from "./page";

declare global {
  interface Window {
    voqalizeUnosalud?: Adapter;
  }
}

export interface Adapter {
  /** Perform one of the brain's page Actions. Never throws. */
  run(command: string, payload: unknown): Promise<RunResult>;
  /** What the visitor is looking at now, as a `page_changed` payload. */
  context(): PageContext;
  /** Report the page, and a move left over from the last page that could not
   *  be made, through `emit`, until the returned stop. The page as it stands
   *  is reported first. */
  start(emit: (event: string, payload: unknown) => void): () => void;
  /** What the widget must keep clear of now. */
  obstacles(): Element[];
  /** The Actions `run` performs. */
  readonly commands: readonly string[];
  /** The guards every press and fill goes through (`guards.ts`), for the
   *  console and the tests. */
  readonly guards: { press(el: HTMLElement): void; fill(el: HTMLInputElement, value: string): void };
}

/** How a move went. `detail`, for a move the brain waits on (`DONE_COMMANDS`),
 *  says in English what is now on screen; `moved` means it went on to another
 *  page, which reports it done or failed from there. */
export interface RunResult {
  ok: boolean;
  error?: string;
  detail?: string;
  moved?: boolean;
}

/** The moves the brain waits on, whose success is reported as `command_done`. */
export const DONE_COMMANDS = new Set([
  "open_booking", "fill_booking_patient", "booking_pick", "booking_scan", "fill_callback_form", "fill_company_form",
]);

export type Kind =
  | "home" | "specialties" | "specialty" | "clinics" | "clinic" | "promotions" | "promo_landing" | "convenios"
  | "convenio" | "benefits" | "plans" | "urgencias" | "about" | "why_us" | "contact" | "faq" | "company" | "callback"
  | "booking" | "blog" | "post" | "terms" | "page";

export type FormKind = "booking" | "callback" | "urgencias" | "company" | "none";

export interface PageContext {
  url: string;
  path: string;
  title: string;
  kind: Kind;
  /** The catalogue's places this page shows, by key. */
  anchors: string[];
  /** The catalogue's FAQ questions on this page, by key. */
  faqs: string[];
  form: FormKind;
  /** On a clinic's page, what it says of the clinic (its hours above all). */
  clinic: ClinicInfo | null;
}

const MAX_ANCHORS = 160;
const CALLBACK_PATH = "/landing/solicitar-diagnostico/";
const URGENCIAS_PATH = "/urgencias/";
const COMPANY_PATH = "/landing/convenio-empresa/";

export const onBooking = () => /^\/agenda-tu-hora(\/|$)/i.test(location.pathname);
const here = () => canonical(location.pathname);

/** Not the page's content: the header, the footer, the right-edge tab stack,
 *  modals, and our own. */
const CHROME = ["#main-header", "#main-footer", "footer", ".fixed-contact", ".modal", "[data-voqalize]"].join(", ");
const inChrome = (el: Element) => Boolean(el.closest(CHROME));
const main = (): HTMLElement => document.querySelector<HTMLElement>("main") ?? document.body;

// ─── What sort of page ────────────────────────────────────────────────────

export function kindOf(path: string): Kind {
  const p = canonical(path);
  if (p === "/") return "home";
  if (/^\/agenda-tu-hora\//.test(p)) return "booking";
  if (p === "/especialidades/") return "specialties";
  if (/^\/especialidades\/[^/]+\/$/.test(p)) return "specialty";
  if (p === "/clinicas/") return "clinics";
  if (/^\/clinicas\/[^/]+\/$/.test(p)) return "clinic";
  if (p === "/promociones/") return "promotions";
  if (p === CALLBACK_PATH) return "callback";
  if (p === COMPANY_PATH) return "company";
  if (p === "/landing/planes-sonrisa-protegida/") return "plans";
  if (/^\/landing\/[^/]+\/$/.test(p)) return "promo_landing";
  if (p === "/convenio/" || p === "/convenios/") return "convenios";
  if (/^\/(convenio|categoria-convenio)\/[^/]+\/$/.test(p)) return "convenio";
  if (/^\/beneficios-y-reembolso\//.test(p)) return "benefits";
  if (p === URGENCIAS_PATH) return "urgencias";
  if (p === "/quienes-somos/") return "about";
  if (p === "/por-que-elegirnos/") return "why_us";
  if (/^\/contactanos\//.test(p)) return "contact";
  if (/^\/preguntas-frecuentes\//.test(p)) return "faq";
  if (/^\/(terminos-y-condiciones|politica-de-privacidad)/.test(p)) return "terms";
  if (p === "/blog/") return "blog";
  if (document.body?.classList.contains("single-post")) return "post";
  return "page";
}

const brevo = () => document.querySelector<HTMLFormElement>("form#sib-form");

export function formKind(): FormKind {
  if (onBooking()) return document.getElementById("dentalsoft-form") ? "booking" : "none";
  const form = brevo();
  if (!form) return "none";
  if (form.querySelector("#EMPRESA")) return "company";
  if (here() === URGENCIAS_PATH) return "urgencias";
  if (form.querySelector("#RUT")) return "callback";
  return "none";
}

// ─── The catalogue's places on this page ──────────────────────────────────

function all(selector: string): HTMLElement[] {
  try {
    return [...document.querySelectorAll<HTMLElement>(selector)];
  } catch {
    return [];
  }
}

/** The smallest element in `root` whose own words contain `text`: one laid
 *  out, else one `reveal` can show. Headings first. */
function smallestContaining(root: Element, text: string): HTMLElement | null {
  const want = norm(text);
  if (!want) return null;
  const words = (el: Element) => norm(el.getAttribute("data-voqalize-text") ?? el.textContent);
  const heads = [...root.querySelectorAll<HTMLElement>("h1, h2, h3, h4, h5")].filter((h) => !inChrome(h) && words(h).includes(want));
  const head = heads.find(visible) ?? heads.find(revealable);
  if (head) return head;
  let found: HTMLElement | null = null;
  let bestLen = Infinity;
  let hidden: HTMLElement | null = null;
  let hiddenLen = Infinity;
  for (const el of root.querySelectorAll<HTMLElement>("*")) {
    if (inChrome(el) || /^(SCRIPT|STYLE|NOSCRIPT|svg|IFRAME|OPTION|SELECT)$/i.test(el.tagName)) continue;
    const t = norm(el.textContent);
    if (!t.includes(want)) continue;
    if (visible(el)) {
      if (t.length < bestLen) [found, bestLen] = [el, t.length];
    } else if (t.length < hiddenLen && revealable(el)) {
      [hidden, hiddenLen] = [el, t.length];
    }
  }
  if (hidden && hiddenLen < bestLen) found = hidden;
  if (found && /^(STRONG|B|EM|I|SPAN|A)$/.test(found.tagName)) {
    const p = found.closest<HTMLElement>("p, li, h1, h2, h3, h4, td, tr");
    if (p && clean(p.textContent).length < 400) return p;
  }
  return found;
}

/** A heading's block: its `<section>`, or the smallest card around it that
 *  holds more than the heading and fits on the screen. */
function blockOf(h: HTMLElement): HTMLElement {
  if (!/^H[1-5]$/.test(h.tagName)) return h;
  const fits = (el: HTMLElement) => {
    const b = boxOf([el]);
    return !b || b.bottom - b.top < window.innerHeight * 1.3;
  };
  const more = (el: HTMLElement) => clean(el.textContent).length > clean(h.textContent).length + 20;
  for (let el = h.parentElement; el && el !== main() && el !== document.body; el = el.parentElement) {
    if (el.matches("section, header, article")) return fits(el) ? el : h;
    if (more(el) && fits(el) && el.matches(".card, [class*=card], .col-lg-6, .col-md-6, .tab-pane, .flickity-cell, li")) return el;
  }
  return h;
}

/** Where the catalogue's `r` is on this page: its selector when it matches
 *  one element, else the block of the smallest element with its words. */
function locate(r: Row): HTMLElement | null {
  const hits = r.selector ? all(r.selector).filter((el) => !el.closest("[data-voqalize]")) : [];
  if (hits.length === 1) return hits[0];
  if (r.text) {
    const byWords = smallestContaining(main(), r.text) ?? smallestContaining(document.body, r.text);
    if (byWords) return blockOf(byWords);
  }
  return hits.find(visible) ?? hits[0] ?? null;
}

/** The catalogue's places that this page has, by key. */
function placesHere(): string[] {
  return rowsFor(location.pathname)
    .filter((r) => !r.faq)
    .filter((r) => locate(r))
    .map((r) => r.key)
    .slice(0, MAX_ANCHORS);
}

// ─── FAQs ──────────────────────────────────────────────────────────────────

interface Faq {
  key: string | null;
  question: string;
  /** The block that holds the question. */
  block: HTMLElement;
  toggle: HTMLElement;
  answer: HTMLElement | null;
  isOpen: () => boolean;
}

/** The page's FAQs: the theme's Bootstrap collapses (`#heading-faq-N` →
 *  `#collapse-faq-N`, open when `.show`) and the landings' Elementor
 *  accordion (`details.e-n-accordion-item`), with their catalogue keys. */
function faqItems(): Faq[] {
  const keys = new Map<string, string>();
  for (const r of rowsFor(location.pathname)) if (r.faq) keys.set(r.faq, r.key);
  const out: Faq[] = [];
  for (const toggle of all("[id^=heading-faq-]")) {
    const n = toggle.id.replace(/^heading-faq-/, "");
    const answer = document.getElementById(`collapse-faq-${n}`);
    out.push({
      key: keys.get(n) ?? null,
      question: clean(toggle.getAttribute("data-voqalize-text") ?? toggle.textContent),
      block: toggle.closest<HTMLElement>("article.card-faq, .card") ?? toggle,
      toggle,
      answer,
      isOpen: () => Boolean(answer?.classList.contains("show")),
    });
  }
  for (const d of all("details")) {
    const summary = d.querySelector<HTMLElement>(":scope > summary");
    if (!summary || inChrome(d)) continue;
    const details = d as HTMLDetailsElement;
    out.push({
      key: (d.id && keys.get(d.id)) || null,
      question: clean(summary.getAttribute("data-voqalize-text") ?? summary.textContent),
      block: d,
      toggle: summary,
      answer: d.querySelector<HTMLElement>(":scope > :not(summary)"),
      isOpen: () => details.open,
    });
  }
  return out.filter((f) => f.question).sort((a, b) => inOrder(a.block, b.block));
}

/** The FAQ the brain named: by catalogue key, by its number or id, or by the
 *  words of its question. */
function findFaq(said: string): Faq | null {
  const items = faqItems();
  const r = row(said);
  const id = r?.faq || said.trim();
  return (
    items.find((f) => f.key === said.trim()) ??
    items.find((f) => f.toggle.id === `heading-faq-${id}` || f.block.id === id) ??
    best(items, (f) => f.question, said)
  );
}

async function openOne(item: Faq): Promise<void> {
  if (item.isOpen()) return;
  const jq = (window as unknown as { jQuery?: (el: Element) => { collapse?: (a: string) => void } }).jQuery;
  if (item.block instanceof HTMLDetailsElement) {
    press(item.toggle);
    if (!(await waitFor(item.isOpen, 800))) item.block.open = true;
    return;
  }
  press(item.toggle);
  if (await waitFor(item.isOpen, 1200)) return;
  // Bootstrap's script is not (yet) there: its own API, else the class it sets.
  if (item.answer && jq) {
    try {
      jq(item.answer).collapse?.("show");
    } catch {
      /* No collapse plugin. */
    }
    if (await waitFor(item.isOpen, 800)) return;
  }
  item.answer?.classList.add("show");
}

async function openFaq({ faq }: { faq: string }): Promise<string> {
  const said = typeof faq === "string" ? faq.trim() : "";
  if (!said) throw new Error("say which FAQ to open, by its key");
  const r = row(said);
  if (r && r.path !== "/clinicas/*/" && !onPage(r, location.pathname)) {
    throw new Error(`the FAQ ${said} is on ${r.path}, not on ${here()}: navigate there with faq="${said}"`);
  }
  const item = findFaq(said);
  if (!item) {
    const known = faqItems().map((f) => f.key ?? f.question).slice(0, 15).join(" | ");
    throw new Error(`no FAQ "${said}" on ${here()}${known ? `; it has: ${known}` : ""}`);
  }
  // Opening one closes the others on the theme's pages (data-parent); on the
  // landings at most one is open too.
  for (const other of faqItems()) {
    if (other.toggle === item.toggle || !other.isOpen()) continue;
    if (other.block instanceof HTMLDetailsElement) other.block.open = false;
  }
  await scrollTo(item.block, "center");
  await openOne(item);
  await sleep(400);
  const group = [item.block, ...(item.answer ? [item.answer] : [])];
  const box = boxOf(group);
  const tall = box ? box.bottom - box.top > window.innerHeight * 0.7 : false;
  await scrollTo(item.block, tall ? "top" : "center");
  highlight(group);
  return `opened the FAQ "${item.question}"`;
}

// ─── Hidden content ───────────────────────────────────────────────────────

/** Hidden now, but `reveal` can show it. */
function revealable(el: Element): boolean {
  if (el.closest(".tab-pane:not(.active)")) return true;
  if (el.closest(".collapse:not(.show)")) return true;
  if (el.closest("details:not([open])")) return true;
  return Boolean(el.closest(".flickity-slider"));
}

type JQ = (el: Element) => { tab?: (a: string) => void; flickity?: (a: string, b?: unknown) => unknown; data?: (k: string) => unknown };
const jQ = () => (window as unknown as { jQuery?: JQ }).jQuery ?? null;

interface FlickityLike {
  stopPlayer?: () => void;
  select?: (i: number, wrap?: boolean, instant?: boolean) => void;
}

function flickityOf(carousel: HTMLElement): FlickityLike | null {
  const F = (window as unknown as { Flickity?: { data(el: Element): FlickityLike | undefined } }).Flickity;
  const inst = F?.data?.(carousel);
  if (inst) return inst;
  try {
    const viaJq = jQ()?.(carousel).data?.("flickity") as FlickityLike | undefined;
    return viaJq ?? null;
  } catch {
    return null;
  }
}

/** Show a tab pane by its pill (the orthodontics prices' `#buttab0..2`, "Por
 *  qué elegirnos"'s technology tabs). */
async function showPane(pane: HTMLElement): Promise<void> {
  if (pane.classList.contains("active")) return;
  const pill = all(`[data-target="#${pane.id}"], a[href="#${pane.id}"], #buttab${pane.id.replace(/^tab/, "")}`)[0];
  if (!pill) return;
  try {
    jQ()?.(pill).tab?.("show");
  } catch {
    /* No tab plugin. */
  }
  if (!pane.classList.contains("active")) {
    // A press, with the page's own `href="#"` jump held back.
    const hold = (e: Event) => e.preventDefault();
    pill.addEventListener("click", hold, { once: true });
    press(pill);
    await waitFor(() => pane.classList.contains("active"), 800);
  }
  if (!pane.classList.contains("active")) {
    // As Bootstrap would leave it.
    for (const sib of pane.parentElement?.querySelectorAll<HTMLElement>(":scope > .tab-pane") ?? []) sib.classList.remove("active", "show");
    pane.classList.add("active", "show");
    for (const p of pill.closest("ul, .nav")?.querySelectorAll(".nav-link, a") ?? []) p.classList.remove("active");
    pill.classList.add("active");
  }
  await sleep(250);
}

/** A Flickity carousel holding `el`: paused (its autoplay would carry the
 *  ring away) and turned to `el`'s cell. */
async function showCell(el: HTMLElement): Promise<void> {
  const carousel = el.closest<HTMLElement>(".flickity-enabled") ?? (el.matches(".flickity-enabled") ? el : null);
  if (!carousel) return;
  const f = flickityOf(carousel);
  f?.stopPlayer?.();
  const slider = carousel.querySelector(".flickity-slider");
  const cell = slider ? [...slider.children].find((c) => c.contains(el)) : null;
  if (!cell || !slider) return;
  const i = [...slider.children].indexOf(cell);
  if (f?.select) f.select(i, false, false);
  else {
    try {
      jQ()?.(carousel).flickity?.("select", i);
    } catch {
      /* No Flickity: the cell is shown as it lies. */
    }
  }
  await sleep(450);
}

async function reveal(el: HTMLElement): Promise<void> {
  const pane = el.closest<HTMLElement>(".tab-pane") ?? (el.matches(".tab-pane") ? el : null);
  if (pane) await showPane(pane);
  // A pill itself: its pane is what it shows.
  if (el.matches("[data-toggle=tab], [data-toggle=pill]")) {
    const target = el.getAttribute("data-target") ?? el.getAttribute("href");
    const p = target && target.startsWith("#") && target.length > 1 ? document.querySelector<HTMLElement>(target) : null;
    if (p) await showPane(p);
  }
  const faq = el.closest<HTMLElement>(".collapse:not(.show)");
  if (faq?.id.startsWith("collapse-faq-")) {
    const item = faqItems().find((f) => f.answer === faq);
    if (item) await openOne(item);
  }
  const details = el.closest<HTMLDetailsElement>("details:not([open])");
  if (details) details.open = true;
  await showCell(el);
}

// ─── show_section ─────────────────────────────────────────────────────────

async function showSection({ anchor, text }: { anchor?: string | null; text?: string | null }): Promise<string> {
  const key = (anchor ?? "").trim();
  const words = (text ?? "").trim();
  if (!key && !words) throw new Error("say which place (anchor) or words (text) to show");
  let el: HTMLElement | null = null;
  if (key) {
    const r = row(key);
    if (!r) throw new Error(`no place "${key}" in the catalogue`);
    if (!onPage(r, location.pathname)) {
      throw new Error(`"${key}" is on ${r.path}, not on ${here()}: navigate there with anchor="${key}"`);
    }
    if (r.faq) return openFaq({ faq: key });
    el = locate(r);
    if (el && words) el = smallestContaining(el, words) ?? el;
    if (!el) throw new Error(`"${key}" is not on this page as built now`);
  } else {
    el = smallestContaining(main(), words) ?? smallestContaining(document.body, words);
    if (!el) throw new Error(`"${words}" is not on ${here()}`);
  }
  await reveal(el);
  // A pill shows its pane: ring the pane with it.
  const pane = el.matches("[data-toggle=tab], [data-toggle=pill]")
    ? document.querySelector<HTMLElement>(el.getAttribute("data-target") ?? "#none")
    : null;
  const group = pane ? [el, pane] : [el];
  const box = boxOf(group);
  const tall = box ? box.bottom - box.top > window.innerHeight * 0.7 : true;
  await scrollTo(el, tall ? "top" : "center");
  highlight(group);
  return `showed ${key || `"${words}"`}`;
}

// ─── navigate ─────────────────────────────────────────────────────────────

const siteHost = (h: string) => h.replace(/^www\./i, "").toLowerCase();

/** Load another page of this site, leaving `then` for it to make. */
function loadPage(target: URL, then: Leftover | null): void {
  leave(then);
  clearHighlight();
  location.assign(target.pathname + target.search + target.hash);
}

async function navigate({ path, anchor, text, faq }: { path: string; anchor?: string | null; text?: string | null; faq?: string | null }) {
  if (typeof path !== "string" || !path.trim()) throw new Error("say which page to go to, as a path like /clinicas/");
  const target = new URL(path.trim(), location.origin);
  if (siteHost(target.host) !== siteHost(location.host)) {
    throw new Error(`${target.href} is not on ${location.host}; only this site's own pages can be opened here`);
  }
  if (/^\/agenda-tu-hora(\/|$)/i.test(target.pathname)) {
    throw new Error("the booking opens in a tab of its own: use open_booking");
  }
  const rest: Leftover | null = faq
    ? { command: "open_faq", payload: { faq } }
    : anchor || text
      ? { command: "show_section", payload: { anchor: anchor ?? "", text: text ?? "" } }
      : null;
  // The same page (whatever query it was opened with) is not loaded again.
  if (canonical(location.pathname) !== canonical(target.pathname) || (target.search && target.search !== location.search)) {
    loadPage(target, rest);
    return null;
  }
  if (rest) {
    const r = await run(rest.command, rest.payload);
    if (!r.ok) throw new Error(r.error);
    return r.detail ?? "";
  }
  await scrollToTopOfPage();
  return `on ${here()}`;
}

/** Finish the move a page of this tab started before it loaded this one, once
 *  this page has settled; a failure is reported as the brain's cue that did
 *  not land. */
async function finishLeftover(): Promise<void> {
  const then = takeLeftover();
  if (!then) return;
  await settled();
  const result = await run(then.command, then.payload);
  if (!result.ok) {
    const command = then.command === "show_section" || then.command === "open_faq" ? "cue" : then.command;
    emit("command_failed", { command, reason: result.error });
  } else if (!result.moved && DONE_COMMANDS.has(then.command)) {
    emit("command_done", { command: then.command, detail: result.detail ?? "" });
  }
}

// ─── The lead forms (Brevo) ───────────────────────────────────────────────

/** LiteSpeed holds the site's delayed scripts (Brevo's `cargarComunas`,
 *  `validarRut`) until the first mouse move, key or touch: one is made, and
 *  the helpers are waited for. */
async function wakeDelayedScripts(): Promise<void> {
  for (const target of [window, document]) {
    target.dispatchEvent(new MouseEvent("mousemove", { bubbles: true, clientX: 2, clientY: 2 }));
  }
  window.dispatchEvent(new Event("touchstart"));
  await waitFor(() => typeof (window as unknown as { cargarComunas?: unknown }).cargarComunas === "function", 4000);
}

/** The words a visitor says for each of Brevo's regions (`#REGION_2`, 1–16). */
const REGIONS: Record<string, string> = {
  metropolitana: "7", santiago: "7", rm: "7", "region metropolitana": "7",
  arica: "1", parinacota: "1", tarapaca: "2", iquique: "2", antofagasta: "3", atacama: "4", copiapo: "4",
  coquimbo: "5", "la serena": "5", valparaiso: "6", vina: "6", "o'higgins": "8", ohiggins: "8", rancagua: "8",
  libertador: "8", maule: "9", talca: "9", nuble: "10", chillan: "10", biobio: "11", "bio bio": "11",
  concepcion: "11", araucania: "12", temuco: "12", "los rios": "13", valdivia: "13", "los lagos": "14",
  "puerto montt": "14", osorno: "14", aysen: "15", coyhaique: "15", magallanes: "16", "punta arenas": "16",
};

function regionOption(select: HTMLSelectElement, said: string): HTMLOptionElement | null {
  const want = norm(said).replace(/^region (de |del )?/, "");
  const options = [...select.options].filter((o) => o.value && !o.disabled);
  if (/^\d{1,2}$/.test(want)) return options.find((o) => o.value === want) ?? null;
  const byText = pickOption(select, said);
  if (byText) return byText;
  for (const [word, value] of Object.entries(REGIONS)) {
    if (want === word || want.includes(word)) return options.find((o) => o.value === value) ?? null;
  }
  return null;
}

/** A field of the Brevo form, by its name. */
const brevoField = <T extends HTMLElement>(form: HTMLFormElement, name: string) =>
  form.querySelector<T>(`#${name}, [name=${name}]`);

interface BrevoState {
  filled: string[];
  missing: string[];
  result: "none" | "success" | "error";
  message: string;
}

/** Brevo's answer to the visitor's press: its success or error panel. */
function brevoResult(): { result: "none" | "success" | "error"; message: string } {
  const shownPanel = (id: string) => {
    const p = document.getElementById(id);
    // Brevo's script marks the panel it shows; its stylesheet hides the rest.
    return p?.classList.contains("sib-form-message-panel--active") ? p : null;
  };
  const ok = shownPanel("success-message");
  if (ok) return { result: "success", message: clean(ok.textContent) };
  const bad = shownPanel("error-message");
  if (bad) return { result: "error", message: clean(bad.textContent) };
  return { result: "none", message: clean(document.getElementById("mensaje")?.textContent) };
}

/** What a Brevo form holds now, field by field (by the brain's names). The
 *  RUT is reported as typed or not: its value never leaves the page. */
function brevoState(fields: Record<string, string>): BrevoState & { rut_typed: boolean } {
  const form = brevo();
  const filled: string[] = [];
  const missing: string[] = [];
  let rut = false;
  if (form) {
    for (const [name, sel] of Object.entries(fields)) {
      const el = brevoField<HTMLInputElement | HTMLSelectElement>(form, sel);
      if (!el) continue;
      const value = el.value.trim();
      const empty = !value || value === "*";
      if (name === "rut") rut = !empty;
      const optional = sel === "COMENTARIOS";
      if (empty) {
        if (!optional) missing.push(name);
      } else filled.push(name);
    }
  }
  return { filled, missing, rut_typed: rut, ...brevoResult() };
}

const CALLBACK_FIELDS = {
  nombre: "NOMBRE", apellidos: "APELLIDOS", rut: "RUT", email: "EMAIL", phone: "SMS", region: "REGION_2", comuna: "COMUNA_2",
};
const COMPANY_FIELDS = {
  nombre: "NOMBRE", phone: "SMS", email: "EMAIL", empresa: "EMPRESA", region: "REGION_2", comuna: "COMUNA_2", cargo: "CARGO",
  trabajadores: "NUMERO_DE_TRABAJADORES", comentarios: "COMENTARIOS",
};

export function callbackFormState() {
  const form = formKind() === "urgencias" ? "urgencias" : "te_llamamos";
  return { form, ...brevoState(CALLBACK_FIELDS) };
}

export function companyFormState() {
  const { rut_typed: _ignored, ...state } = brevoState(COMPANY_FIELDS);
  return state;
}

/** When Javier last filled a form here: the widget keeps clear of it a while. */
let lastFill = 0;

/** Fill the Brevo form's text fields that `values` names. */
function fillText(form: HTMLFormElement, values: [string, string | null | undefined][], touched: HTMLElement[], problems: string[]): void {
  for (const [name, value] of values) {
    if (!value || !value.trim()) continue;
    const el = brevoField<HTMLInputElement>(form, name);
    if (!el) continue;
    try {
      setValue(el, value.trim().slice(0, Number(el.getAttribute("maxlength")) || 200));
      touched.push(el);
    } catch (error) {
      problems.push(error instanceof Error ? error.message : String(error));
    }
  }
}

function fillPhone(form: HTMLFormElement, said: string | null | undefined, touched: HTMLElement[], problems: string[], strict: boolean): void {
  if (!said) return;
  const el = brevoField<HTMLInputElement>(form, "SMS");
  if (!el) return;
  const digits = chileanMobile(said);
  const ok = strict ? /^9\d{8}$/.test(digits) : /^\d{8,9}$/.test(digits);
  if (!ok) {
    problems.push(`phone "${said}" refused: the form takes ${strict ? "a Chilean mobile (9 digits starting with 9)" : "8 or 9 digits"}, without +56; nothing was typed there: ask for it again, never change the digits`);
    return;
  }
  setValue(el, digits);
  touched.push(el);
}

async function fillRegion(form: HTMLFormElement, region: string | null | undefined, comuna: string | null | undefined, touched: HTMLElement[], problems: string[]): Promise<void> {
  const select = brevoField<HTMLSelectElement>(form, "REGION_2");
  if (!region || !select) return;
  const option = regionOption(select, region);
  if (!option) {
    problems.push(`no region "${region}"; the form offers: ${[...select.options].filter((o) => o.value).map((o) => clean(o.text)).join(" | ")}`);
    return;
  }
  setValue(select, option.value);
  touched.push(select);
  const comunas = brevoField<HTMLSelectElement>(form, "COMUNA_2");
  if (!comunas) return;
  // The comunas load on the region's click (`cargarComunas`), not its change.
  select.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  const loaded = await waitFor(() => [...comunas.options].filter((o) => o.value && o.value !== "*").length > 0, 4000);
  if (!loaded) {
    problems.push("the comunas did not load for that region");
    return;
  }
  if (!comuna) return;
  const pick = pickOption(comunas, comuna);
  if (!pick || pick.value === "*") {
    problems.push(`no comuna "${comuna}" in ${clean(option.text)}`);
    return;
  }
  setValue(comunas, pick.value);
  touched.push(comunas);
}

/** The payload's value for one of `names`, whichever the brain uses. */
function pick(p: Record<string, unknown>, ...names: string[]): string {
  for (const n of names) {
    const v = p[n];
    if (typeof v === "string" && v.trim()) return v.trim();
    if (typeof v === "number") return String(v);
  }
  return "";
}

/** Go to the form's page first, if this is not it; the next page fills it. */
function goToForm(path: string, command: string, payload: unknown): boolean {
  if (here() === path) return false;
  loadPage(new URL(path, location.origin), { command, payload });
  return true;
}

/**
 * Te llamamos (/landing/solicitar-diagnostico/) or the urgencias page's form
 * (/urgencias/): a call-back request on Brevo, which needs the visitor's RUT.
 * Javier fills what the visitor said, then focuses and rings the RUT for them
 * to type, and rings ENVIAR once the form is complete. He never sends it.
 */
async function fillCallbackForm(payload: Record<string, unknown>): Promise<string | null> {
  const which = pick(payload, "form") === "urgencias" ? "urgencias" : "te_llamamos";
  if (goToForm(which === "urgencias" ? URGENCIAS_PATH : CALLBACK_PATH, "fill_callback_form", payload)) return null;
  await wakeDelayedScripts();
  const form = await waitFor(brevo);
  if (!form) throw new Error("the call-back form is not on this page");
  lastFill = Date.now();
  await scrollTo(form, "top");
  const touched: HTMLElement[] = [];
  const problems: string[] = [];
  const nombre = pick(payload, "nombre", "name");
  const apellidos = pick(payload, "apellidos", "last_name", "surname");
  const hasSurname = Boolean(brevoField(form, "APELLIDOS"));
  fillText(form, [
    ["NOMBRE", hasSurname ? nombre : [nombre, apellidos].filter(Boolean).join(" ")],
    ["APELLIDOS", apellidos],
    ["EMAIL", pick(payload, "email")],
  ], touched, problems);
  fillPhone(form, pick(payload, "phone", "telefono"), touched, problems, true);
  await fillRegion(form, pick(payload, "region"), pick(payload, "comuna"), touched, problems);
  await sleep(150);
  lastFill = Date.now();
  const state = callbackFormState();
  emit("callback_form_state", state);
  const rut = brevoField<HTMLInputElement>(form, "RUT");
  const submit = form.querySelector<HTMLElement>("button[type=submit], .sib-form-block__button");
  if (rut && !state.rut_typed) {
    await scrollTo(rut, "center");
    rut.focus({ preventScroll: true });
    highlight(rut);
  } else if (!state.missing.length && submit) {
    await scrollTo(submit, "center");
    highlight(submit);
  } else if (touched.length) highlight(touched);
  if (problems.length && !touched.length) throw new Error(problems.join("; "));
  return [
    state.filled.length ? `filled ${state.filled.filter((f) => f !== "rut").join(", ")}` : "nothing filled",
    ...problems,
    state.rut_typed ? "the RUT is typed" : "the RUT box is focused and ringed for the visitor to type",
    state.missing.length ? `still missing: ${state.missing.join(", ")}` : "the form is complete; ENVIAR is ringed for the visitor to press",
  ].join("; ");
}

/** The words a visitor says for the company's size (`#NUMERO_DE_TRABAJADORES`). */
function sizeOption(select: HTMLSelectElement, said: string): HTMLOptionElement | null {
  const options = [...select.options].filter((o) => o.value);
  const n = Number((said.match(/\d[\d.]*/)?.[0] ?? "").replace(/\./g, ""));
  const value = (v: string) => options.find((o) => o.value === v) ?? null;
  if (/^[2-5]$/.test(said.trim())) return value(said.trim());
  const t = norm(said);
  if (/mas de|more than|over|\+/.test(t) && n >= 1000) return value("5");
  if (/menos|less|under|fewer|small|pequen/.test(t) || (n > 0 && n < 50)) return value("2");
  if (n >= 1000) return value("5");
  if (n >= 500) return value("4");
  // There is no 50–200 option on the form; "Entre 200 a 500" is the nearest.
  if (n >= 50) return value("3");
  return pickOption(select, said);
}

/** Convenio Empresas (/landing/convenio-empresa/): a company's request on
 *  Brevo, with no RUT. Javier fills all of it; the visitor presses ENVIAR. */
async function fillCompanyForm(payload: Record<string, unknown>): Promise<string | null> {
  if (goToForm(COMPANY_PATH, "fill_company_form", payload)) return null;
  await wakeDelayedScripts();
  const form = await waitFor(brevo);
  if (!form || !brevoField(form, "EMPRESA")) throw new Error("the company form is not on this page");
  lastFill = Date.now();
  await scrollTo(form, "top");
  const touched: HTMLElement[] = [];
  const problems: string[] = [];
  fillText(form, [
    ["NOMBRE", pick(payload, "nombre", "contact_name", "contact", "name")],
    ["EMAIL", pick(payload, "email")],
    ["EMPRESA", pick(payload, "empresa", "company", "company_name")],
    ["CARGO", pick(payload, "cargo", "role", "position", "job_title")],
    ["COMENTARIOS", pick(payload, "comentarios", "message", "mensaje", "comments")],
  ], touched, problems);
  fillPhone(form, pick(payload, "phone", "telefono"), touched, problems, false);
  await fillRegion(form, pick(payload, "region"), pick(payload, "comuna"), touched, problems);
  const size = pick(payload, "trabajadores", "size", "company_size", "workers", "employees");
  const sizes = brevoField<HTMLSelectElement>(form, "NUMERO_DE_TRABAJADORES");
  if (size && sizes) {
    const o = sizeOption(sizes, size);
    if (o) {
      setValue(sizes, o.value);
      touched.push(sizes);
    } else problems.push(`no company size "${size}"; the form offers: ${[...sizes.options].filter((x) => x.value).map((x) => clean(x.text)).join(" | ")}`);
  }
  await sleep(150);
  lastFill = Date.now();
  const state = companyFormState();
  emit("company_form_state", state);
  const submit = form.querySelector<HTMLElement>("button[type=submit], .sib-form-block__button");
  if (!state.missing.length && submit) {
    await scrollTo(submit, "center");
    highlight(submit);
  } else if (touched.length) highlight(touched);
  if (problems.length && !touched.length) throw new Error(problems.join("; "));
  return [
    state.filled.length ? `filled ${state.filled.join(", ")}` : "nothing filled",
    ...problems,
    state.missing.length ? `still missing: ${state.missing.join(", ")}` : "the form is complete; ENVIAR is ringed for the visitor to press",
  ].join("; ");
}

/** The lead form's state after every change the visitor makes, and Brevo's
 *  answer once they press ENVIAR. */
function watchForms(emit: (event: string, payload: unknown) => void): () => void {
  const kind = formKind();
  const form = brevo();
  if (!form || kind === "none" || kind === "booking") return () => {};
  const read = () => (kind === "company" ? ["company_form_state", companyFormState()] : ["callback_form_state", callbackFormState()]) as [string, unknown];
  let last = JSON.stringify(read()[1]);
  let timer: ReturnType<typeof setTimeout> | null = null;
  const send = () => {
    timer = null;
    const [event, state] = read();
    const key = JSON.stringify(state);
    if (key === last) return;
    last = key;
    emit(event, state);
  };
  const soon = () => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(send, 600);
  };
  form.addEventListener("input", soon, true);
  form.addEventListener("change", soon, true);
  const obs = new MutationObserver(soon);
  for (const id of ["success-message", "error-message", "mensaje"]) {
    const el = document.getElementById(id);
    if (el) obs.observe(el, { attributes: true, childList: true, subtree: true, characterData: true });
  }
  return () => {
    form.removeEventListener("input", soon, true);
    form.removeEventListener("change", soon, true);
    obs.disconnect();
    if (timer) clearTimeout(timer);
  };
}

// ─── Reporting ────────────────────────────────────────────────────────────

function context(): PageContext {
  if (onBooking()) return bookingContext();
  return {
    url: location.href,
    path: here(),
    title: document.title,
    kind: kindOf(location.pathname),
    anchors: placesHere(),
    faqs: faqItems().map((f) => f.key).filter((k): k is string => Boolean(k)),
    form: formKind(),
    clinic: isClinicPage() ? clinicInfo() : null,
  };
}

let emitter: ((event: string, payload: unknown) => void) | null = null;
/** What happened before anyone listened: a move left from the last page that
 *  failed before the brain could hear this one. */
const backlog: [string, unknown][] = [];
function emit(event: string, payload: unknown): void {
  if (emitter) emitter(event, payload);
  else backlog.push([event, payload]);
}

let lastUrl: string | null = null;
/** The site loads a whole page for every move, so this only sees a change of
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
  const stopBooking = onBooking() ? watchBooking(next) : null;
  const stopForms = watchForms(next);
  for (const [event, payload] of backlog.splice(0)) next(event, payload);
  return () => {
    stopBooking?.();
    stopForms();
    if (emitter === next) emitter = null;
  };
}

/** What the widget keeps clear of: the right edge's tab stack, and a form
 *  Javier is filling (for a while after his last fill). */
function obstacles(): Element[] {
  const out: Element[] = [...document.querySelectorAll(".fixed-contact")];
  const form = brevo() ?? (onBooking() ? document.getElementById("dentalsoft-form") : null);
  if (form && Date.now() - Math.max(lastFill, bookingMovedAt) < 90_000) out.push(form);
  return out.filter((el) => shown(el));
}

type Command = (payload: never) => Promise<string | null | void>;

const SITE_COMMANDS: Record<string, Command> = {
  navigate: navigate as Command,
  show_section: showSection as Command,
  open_faq: openFaq as Command,
  fill_callback_form: fillCallbackForm as Command,
  fill_company_form: fillCompanyForm as Command,
};

const COMMANDS: Record<string, Command> = onBooking()
  ? { show_section: showSection as Command, ...bookingCommands() }
  : SITE_COMMANDS;

async function run(command: string, payload: unknown): Promise<RunResult> {
  const fn = COMMANDS[command];
  if (!fn) return { ok: false, error: `the page ${here()} cannot ${command}` };
  try {
    const detail = await fn((payload ?? {}) as never);
    // `null`: the move went on to another page, which finishes it.
    if (detail === null) return { ok: true, moved: true };
    return { ok: true, detail: detail ?? undefined };
  } catch (error) {
    const why = error instanceof Error ? error.message : String(error);
    return { ok: false, error: error instanceof GuardError ? `refused: ${why}` : why };
  }
}

if (!window.voqalizeUnosalud) {
  styleThePage();
  window.addEventListener("popstate", routeChanged);
  window.addEventListener("hashchange", routeChanged);
  void finishLeftover();
  window.voqalizeUnosalud = { run, context, start, obstacles, commands: Object.keys(COMMANDS), guards: { press, fill: setValue } };
}
