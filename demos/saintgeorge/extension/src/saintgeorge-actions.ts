/**
 * The site adapter: drive saintgeorge.cl from the outside, with no help from
 * the school's developers.
 *
 * The brain sends a Voqalize `ui-command` ({command, payload}) and `run`
 * performs it on the page in front; the page reports back through `start`,
 * which calls `emit(event, payload)` for every page the visitor lands on, and
 * for what a move read or did: the fees (`fees_read`), the calendar
 * (`events_read`), the contact card (`command_done`, `contact_used`), or a move
 * left from the last page that could not be finished (`command_failed`).
 *
 * What the site is, for a script like this: WordPress with a hand-built theme
 * on Bootstrap 5, rendered on the server. Every move between pages is a full
 * page load, so a move to another page cannot finish on the page that asked
 * for it: `navigate` (and the fees and the calendar, which open their page
 * first) writes what is left to do to `sessionStorage` and loads the page, and
 * the adapter on the next page does it once that page has settled. The window
 * scrolls under a fixed header (`#navbar.fixed-top`).
 *
 * Where the content is:
 *
 *   - A page's title is the `h1` in `header.single-page-header` (the home
 *     page's is in `header.home-header`); its body is `main`, in
 *     `.texto-admision` columns with `h3` headings and paragraphs. The home
 *     page is three sections with ids: `#comunidad`, `#mision`, `#valores`.
 *   - Accordions are Bootstrap 5's: `.accordion-item` with a
 *     `button.accordion-button` and its `.accordion-collapse` pane. Their ids
 *     (`#collapse_2_1`) repeat from page to page, so an accordion is found by
 *     its button's words ("1º BÁSICO", "CONOCE AL EQUIPO"), and opened through
 *     the page's own Bootstrap, else by its button, else by hand.
 *   - The admission page's fees and admission status are paragraphs of text:
 *     "Valores referenciales año 2026:" over lines "…: UF 85". They change
 *     every year, so they are read off the page each time, never known.
 *   - The calendar page is a Google Calendar embed, which a page script cannot
 *     read; its events come from the calendar's public feed, fetched by the
 *     extension's service worker (`hub.ts`, `ical.ts`).
 *   - There is no contact form. The contact card is ours: an email to the
 *     admissions office written out, which the parent opens in their own mail
 *     app with a button and sends themselves.
 */

import { readCalendar } from "./hub";

declare global {
  interface Window {
    voqalizeSaintGeorge?: Adapter;
    /** The page's own Bootstrap 5 bundle. */
    bootstrap?: {
      Collapse?: { getOrCreateInstance(el: Element, options?: { toggle?: boolean }): { show(): void } };
    };
  }
}

export interface Adapter {
  /** Perform one of the brain's page Actions. Never throws. */
  run(command: string, payload: unknown): Promise<{ ok: boolean; error?: string }>;
  /** What the visitor is looking at now, as a `page_changed` payload. */
  context(): PageContext;
  /** Report the page, and what moves read or left over, through `emit`, until
   *  the returned stop. The page as it stands is reported first. */
  start(emit: (event: string, payload: unknown) => void): () => void;
  /** The Actions `run` performs. */
  readonly commands: readonly string[];
}

export interface PageLink {
  label: string;
  url: string;
  near: string;
}

export interface PageContext {
  url: string;
  path: string;
  title: string;
  kind: "home" | "unit" | "admission" | "page";
  /** Section headings a visitor can be taken to, in page order. */
  headings: string[];
  /** The accordions on the page, by their buttons' words. */
  faqs: string[];
  /** Titles of the cards on the page: the units, the newsletters. */
  cards: string[];
  /** The documents and links out on the page. */
  links: PageLink[];
}

export interface Fee {
  label: string;
  value: string;
  note: string;
}

/** The school's blue and yellow (the theme's `--blue` and `--yellow`). */
const BLUE = "#1C3E93";
const YELLOW = "#FFD200";
const RING_MS = 5500;
const WAIT_MS = 8000;
const MAX_HEADINGS = 80;
const MAX_FAQS = 60;
const MAX_CARDS = 40;
const MAX_LINKS = 40;
/** How many coming events the calendar read hands the brain. */
const EVENTS = 30;
/** Where a move to another page leaves the rest of it for the next page. */
const THEN_KEY = "voqalize.saintgeorge.then";
/** A move left longer ago than this belongs to some other visit. */
const THEN_MAX_AGE_MS = 60_000;

const ADMISSION_PATH = "/admision/admision/";
const CALENDAR_PATH = "/familia/calendario/";

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const clean = (s: string | null | undefined) => (s ?? "").replace(/\s+/g, " ").trim();
/**
 * For matching what the brain said against what the page shows: lower case,
 * without accents (á → a, ñ → n) or ordinal marks ("1º" → "1"), with straight
 * quotes and dashes, and without the opening "¿"/"¡" and closing punctuation.
 */
export const norm = (s: string | null | undefined) =>
  clean(s)
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[º°ª]/g, "")
    .toLowerCase()
    .replace(/[‘’´`]/g, "'")
    .replace(/[“”«»]/g, '"')
    .replace(/[‐-―]/g, "-")
    .replace(/[¿¡]/g, "")
    .replace(/…/g, "")
    .replace(/^[\s"']+|[\s"'.:;,?!]+$/g, "")
    .replace(/\s+/g, " ")
    .trim();

/** Laid out on the page at all, whether or not it is on screen. */
const visible = (el: Element | null | undefined): el is HTMLElement => {
  if (!el) return false;
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
};
const shown = (el: Element): boolean => visible(el);

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

/** Page order, for lists gathered from several selectors. */
const inOrder = (a: Node, b: Node) =>
  a === b ? 0 : a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;

/** Not the page's content: the header and its menus, the footer, and ours. */
const CHROME = "#navbar, nav.navbar, .offcanvas, footer, .footer, .modal, [data-voqalize]";
const inChrome = (el: Element) => Boolean(el.closest(CHROME));

/** The page's content: its title header and its `main`. */
function contentRoots(): HTMLElement[] {
  const roots = [
    ...document.querySelectorAll<HTMLElement>("header.home-header, header.single-page-header"),
    document.querySelector<HTMLElement>("main") ?? document.body,
  ];
  return roots.filter((r, i) => !roots.some((o, j) => j !== i && o.contains(r) && o !== r));
}

function all<T extends Element>(selector: string): T[] {
  const out = contentRoots().flatMap((r) => [...r.querySelectorAll<T>(selector)]);
  return [...new Set(out)].filter((el) => !inChrome(el)).sort(inOrder);
}

// ─── Scrolling ────────────────────────────────────────────────────────────

/** The height of what is pinned to the top of the viewport: the navbar. */
function headerHeight(): number {
  let h = 0;
  for (const el of document.querySelectorAll<HTMLElement>("#navbar, nav.navbar.fixed-top")) {
    const r = el.getBoundingClientRect();
    if (r.height <= 0 || r.height > 260) continue;
    const pos = getComputedStyle(el).position;
    h = Math.max(h, pos === "fixed" || pos === "sticky" ? r.bottom : 0);
  }
  return h;
}

function distance(el: Element, align: "top" | "center"): number {
  const r = el.getBoundingClientRect();
  const top = headerHeight() + 16;
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
 *  measuring again as images load and fade in. */
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

async function scrollToTopOfPage(): Promise<void> {
  window.scrollTo({ top: 0, behavior: "smooth" });
  await scrollEnded();
}

// ─── The ring ─────────────────────────────────────────────────────────────
// Drawn over the page, never on the school's own elements: fixed, and moved
// with its target every frame, so it follows a scroll and an accordion that
// opens under it. Yellow on a blue edge, so it reads on the white pages and
// on the blue sections alike.

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
      border: `3px solid ${YELLOW}`,
      borderRadius: "12px",
      boxShadow: `0 0 0 2px ${BLUE}`,
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
  if (document.querySelector("style[data-voqalize=saintgeorge]")) return;
  const style = document.createElement("style");
  style.setAttribute("data-voqalize", "saintgeorge");
  style.textContent = `
    @keyframes voqalize-ring {
      0%, 100% { box-shadow: 0 0 0 2px ${BLUE}, 0 0 0 2px rgba(255, 210, 0, 0.6); }
      50% { box-shadow: 0 0 0 2px ${BLUE}, 0 0 0 12px rgba(255, 210, 0, 0); }
    }
  `;
  (document.head ?? document.documentElement).appendChild(style);
}

// ─── What the page shows ──────────────────────────────────────────────────

interface Head {
  el: HTMLElement;
  text: string;
}

/** What a landmark with no words of its own is called. */
function landmarkName(el: HTMLElement): string | null {
  if (el.tagName !== "IFRAME") return null;
  const src = (el as HTMLIFrameElement).src;
  if (/calendar\.google\.com/.test(src)) return "Calendario";
  if (/youtube|vimeo/.test(src)) return "Video";
  if (/google\.[a-z.]+\/maps/.test(src)) return "Mapa";
  return null;
}

/**
 * Headings the visitor can be taken to, in page order: the page title, the
 * real headings (`h1`–`h5`, the cards' titles among them), and the landmarks
 * with no text (the calendar, a video). Not the accordions' headers, which
 * are `faqs`, nor anything inside an accordion's pane.
 */
function headings(): Head[] {
  const found: Head[] = [];
  for (const h of all<HTMLElement>("h1, h2, h3, h4, h5")) {
    if (h.matches(".accordion-header") || h.closest(".accordion-body, .accordion-header")) continue;
    if (h.parentElement?.closest("h1, h2, h3, h4, h5")) continue;
    const text = textOf(h);
    if (text.length > 1 && shown(h)) found.push({ el: h, text });
  }
  for (const el of all<HTMLElement>("iframe")) {
    const name = landmarkName(el);
    if (name && shown(el)) found.push({ el, text: name });
  }
  found.sort((a, b) => inOrder(a.el, b.el));
  const seen = new Set<string>();
  return found.filter((h) => !seen.has(norm(h.text)) && seen.add(norm(h.text)));
}

interface Accordion {
  label: string;
  item: HTMLElement;
  button: HTMLElement;
  pane: HTMLElement;
  isOpen: () => boolean;
}

/** The pane a button opens: its `data-bs-target`, else its `aria-controls`,
 *  looked for inside its own item first, as ids repeat across groups. */
function paneOf(button: HTMLElement, item: HTMLElement): HTMLElement | null {
  const inItem = item.querySelector<HTMLElement>(".accordion-collapse, .collapse");
  if (inItem) return inItem;
  const ref = button.getAttribute("data-bs-target") ?? `#${button.getAttribute("aria-controls") ?? ""}`;
  try {
    return ref.length > 1 ? document.querySelector<HTMLElement>(ref) : null;
  } catch {
    return null;
  }
}

/** Every accordion on the page that is laid out at this width (Explora's
 *  lesson: never one in a copy the layout hides). */
function accordions(): Accordion[] {
  const out: Accordion[] = [];
  for (const item of all<HTMLElement>(".accordion-item")) {
    const button = item.querySelector<HTMLElement>(".accordion-button, [data-bs-toggle=collapse]");
    if (!button || !shown(button)) continue;
    const pane = paneOf(button, item);
    const label = textOf(button);
    if (!pane || !label) continue;
    out.push({
      label,
      item,
      button,
      pane,
      isOpen: () => pane.classList.contains("show") && !pane.classList.contains("collapsing"),
    });
  }
  return out;
}

function cardEls(): HTMLElement[] {
  return all<HTMLElement>("a.card, .card").filter((c) => !c.parentElement?.closest(".card"));
}

function cardTitle(card: HTMLElement): string {
  const t = card.querySelector<HTMLElement>(".card-title");
  return t ? textOf(t) : clean(card.getAttribute("title") ?? card.querySelector("img")?.alt);
}

function cards(): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const c of cardEls()) {
    const t = cardTitle(c);
    if (!t || seen.has(norm(t))) continue;
    seen.add(norm(t));
    out.push(t);
    if (out.length >= MAX_CARDS) break;
  }
  return out;
}

const SITE_HOST = /(^|\.)saintgeorge\.cl$/i;

/** The heading a link sits under: the last one before it on the page. */
function nearOf(el: Element, heads: Head[]): string {
  let near = "";
  for (const h of heads) {
    if (h.el.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) near = h.text;
    else break;
  }
  return near;
}

/** The documents and links out on the page: PDFs, and links to another host. */
function linkEls(): { a: HTMLAnchorElement; url: URL }[] {
  const out: { a: HTMLAnchorElement; url: URL }[] = [];
  for (const a of all<HTMLAnchorElement>("a[href]")) {
    let url: URL;
    try {
      url = new URL(a.href);
    } catch {
      continue;
    }
    if (url.protocol !== "https:") continue;
    const isDocument = /\.pdf$/i.test(url.pathname) || /\/wp-content\/uploads\//i.test(url.pathname);
    if (isDocument || !SITE_HOST.test(url.host)) out.push({ a, url });
  }
  return out;
}

function linkLabel(a: HTMLAnchorElement): string {
  return (
    textOf(a) ||
    clean(a.getAttribute("title")) ||
    clean(a.querySelector("img")?.alt) ||
    clean(a.getAttribute("aria-label"))
  );
}

function links(): PageLink[] {
  const heads = headings();
  const seen = new Set<string>();
  const out: PageLink[] = [];
  for (const { a, url } of linkEls()) {
    if (seen.has(url.href)) continue;
    seen.add(url.href);
    out.push({ label: linkLabel(a), url: url.href, near: nearOf(a, heads) });
    if (out.length >= MAX_LINKS) break;
  }
  return out;
}

function kind(): PageContext["kind"] {
  const p = location.pathname.replace(/\/+$/, "");
  if (p === "") return "home";
  if (/^\/unidad\//i.test(p)) return "unit";
  if (/^\/admision\//i.test(p)) return "admission";
  return "page";
}

function context(): PageContext {
  return {
    url: location.href,
    path: location.pathname,
    title: document.title,
    kind: kind(),
    headings: headings()
      .map((h) => h.text)
      .slice(0, MAX_HEADINGS),
    faqs: accordions()
      .map((a) => a.label)
      .slice(0, MAX_FAQS),
    cards: cards(),
    links: links(),
  };
}

// ─── The admission page's fees and status ─────────────────────────────────

/** A paragraph's lines, as its `<br>`s break it, whether or not it is laid out. */
function linesOf(el: Element): string[] {
  const copy = el.cloneNode(true) as Element;
  for (const br of copy.querySelectorAll("br")) br.replaceWith("\n");
  return (copy.textContent ?? "")
    .split("\n")
    .map(clean)
    .filter(Boolean);
}

const UF = /\bUF\s*\d/i;
const FEE_LINE = /^(.*?)\s*[:：]\s*(UF\s*[\d.,]+)\s*(.*)$/i;

export interface FeesOnPage {
  heading: string;
  fees: Fee[];
  status: string[];
  /** The fees' paragraph, and the admission lines', to ring. */
  feesEl: HTMLElement | null;
  statusEls: HTMLElement[];
}

/** The reference fees and the admission lines, as the admission page writes
 *  them: the paragraph that names its "valores referenciales", else the one
 *  with the most UF values; and the paragraphs that open "Admisión …". */
export function readFees(root: ParentNode = document): FeesOnPage {
  const paragraphs = [...root.querySelectorAll<HTMLElement>("main p")].filter((p) => !inChrome(p));
  const said = (p: HTMLElement) => p.getAttribute("data-voqalize-text") ?? p.textContent ?? "";
  const ufCount = (p: HTMLElement) => (said(p).match(/\bUF\s*\d/gi) ?? []).length;
  const feesEl =
    paragraphs.find((p) => /valores referenciales/.test(norm(said(p))) && UF.test(said(p))) ??
    paragraphs.filter((p) => ufCount(p) >= 2).sort((a, b) => ufCount(b) - ufCount(a))[0] ??
    null;
  let heading = "";
  const fees: Fee[] = [];
  for (const line of feesEl ? linesOf(feesEl) : []) {
    const m = FEE_LINE.exec(line);
    if (m) fees.push({ label: clean(m[1]), value: clean(m[2]).replace(/^UF\s*/i, "UF "), note: clean(m[3]) });
    else if (!fees.length && !heading) heading = line.replace(/[:：]\s*$/, "");
  }
  const statusEls = paragraphs.filter((p) => {
    const lead = clean(p.querySelector("strong, b")?.textContent);
    return p !== feesEl && /^admision\b/.test(norm(lead)) && !UF.test(said(p));
  });
  return { heading, fees, status: statusEls.map((p) => linesOf(p).join(" ")), feesEl, statusEls };
}

// ─── navigate, and the move left for the next page ────────────────────────

const strip = (p: string) => (p || "/").replace(/\/+$/, "") || "/";
const samePath = (a: string, b: string) => strip(a).toLowerCase() === strip(b).toLowerCase();
const siteHost = (h: string) => h.replace(/^www\./i, "").toLowerCase();

/** What is left of a move for the page it opened: a section, an accordion,
 *  or a whole command (the fees, the calendar). */
interface Then {
  heading?: string | null;
  text?: string | null;
  faq?: string | null;
  command?: string;
  payload?: unknown;
}

/** The page has settled: loaded, its fonts in, and the DOM quiet a moment. */
async function settled(): Promise<void> {
  if (document.readyState !== "complete") {
    await Promise.race([
      new Promise<void>((r) => window.addEventListener("load", () => r(), { once: true })),
      sleep(2500),
    ]);
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

/** A path of the site as WordPress serves it: with its trailing slash, so
 *  the load is not a redirect first. */
function sitePath(path: string): URL {
  const target = new URL(path.trim(), location.origin);
  if (!target.pathname.endsWith("/") && !/\.[a-z0-9]{2,4}$/i.test(target.pathname)) target.pathname += "/";
  return target;
}

/** Load another page of the site, leaving `then` for it. */
function goTo(target: URL, then: Then): void {
  try {
    if (then.heading || then.text || then.faq || then.command) {
      sessionStorage.setItem(THEN_KEY, JSON.stringify({ ...then, at: Date.now() }));
    } else {
      sessionStorage.removeItem(THEN_KEY);
    }
  } catch {
    // Storage refused: the page still loads, at its top.
  }
  clearHighlight();
  location.assign(target.pathname + target.search + target.hash);
}

async function navigate({
  path,
  heading,
  text,
  faq,
}: {
  path: string;
  heading?: string | null;
  text?: string | null;
  faq?: string | null;
}) {
  if (typeof path !== "string" || !path.trim()) throw new Error("say which page to go to, as a path like /unidad/infant");
  const target = sitePath(path);
  if (siteHost(target.host) !== siteHost(location.host)) {
    throw new Error(`${target.href} is not on saintgeorge.cl; only the site's own pages can be opened here`);
  }
  if (!samePath(location.pathname, target.pathname) || target.search !== location.search) {
    return goTo(target, { heading: heading ?? null, text: text ?? null, faq: faq ?? null });
  }
  if (faq) return openFaq({ question: faq });
  if (heading || text) return showSection({ heading, text });
  await scrollToTopOfPage();
}

/** What the last page's move left to do here, taken once. */
function takeThen(): Then | null {
  try {
    const raw = sessionStorage.getItem(THEN_KEY);
    if (!raw) return null;
    sessionStorage.removeItem(THEN_KEY);
    const then = JSON.parse(raw) as Then & { at?: number };
    if (typeof then.at === "number" && Date.now() - then.at > THEN_MAX_AGE_MS) return null;
    return then.heading || then.text || then.faq || then.command ? then : null;
  } catch {
    return null;
  }
}

/** Finish the move the last page started, once this page has settled; a
 *  failure is reported as that move's (a cue's, the fees', the calendar's). */
async function finishThen(): Promise<void> {
  const then = takeThen();
  if (!then) return;
  await settled();
  const command = then.command && then.command in COMMANDS ? then.command : "cue";
  try {
    if (command !== "cue") await COMMANDS[command]((then.payload ?? {}) as never);
    else if (then.faq) await openFaq({ question: then.faq });
    else await showSection({ heading: then.heading, text: then.text });
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

const HEADING = /^H[1-5]$/;

/**
 * What a heading heads, to ring together: the page title, its header; a
 * section's title on the home page, its `<section>`; a card's title, its card;
 * a heading in a page's body, it and what follows it up to the next heading.
 */
function sectionOf(h: HTMLElement): HTMLElement[] {
  if (h.tagName === "IFRAME") return [h];
  const header = h.closest<HTMLElement>("header.single-page-header, header.home-header");
  if (header) return [header];
  const card = h.closest<HTMLElement>(".card");
  if (card && h.matches(".card-title")) return [card];
  const section = h.closest<HTMLElement>("section[id]");
  if (section) {
    // A value on the home page (an `h3` with its line) is its own stop.
    if (h.tagName === "H3" && h.nextElementSibling?.tagName === "P") return [h, h.nextElementSibling as HTMLElement];
    return [section];
  }
  // A heading inside a wrapper of its own (an `h2 > strong > p`) heads from there.
  let start: HTMLElement = h;
  while (start.parentElement && start.parentElement.children.length === 1 && !start.parentElement.matches("main, section, .container, .row")) {
    start = start.parentElement;
  }
  const out = [start];
  for (let n = start.nextElementSibling; n && out.length < 10; n = n.nextElementSibling) {
    if (!(n instanceof HTMLElement)) continue;
    if (HEADING.test(n.tagName) || n.querySelector("h1, h2, h3, h4, h5")) break;
    if (shown(n) && (clean(n.textContent) || n.querySelector("img, iframe"))) out.push(n);
  }
  return out;
}

/** The smallest laid-out element in the content whose text holds `text`; a
 *  word inside a paragraph is read with its paragraph. */
function smallestContaining(text: string, within: Element[] = contentRoots()): HTMLElement | null {
  const want = norm(text);
  if (!want) return null;
  let found: HTMLElement | null = null;
  let bestLen = Infinity;
  for (const root of within) {
    for (const el of [root, ...root.querySelectorAll<HTMLElement>("*")] as HTMLElement[]) {
      if (inChrome(el) || /^(SCRIPT|STYLE|NOSCRIPT|svg)$/i.test(el.tagName) || !visible(el)) continue;
      const t = norm(el.getAttribute("data-voqalize-text") ?? el.textContent);
      if (!t.includes(want) || t.length >= bestLen) continue;
      found = el;
      bestLen = t.length;
    }
  }
  if (!found) {
    const img = within
      .flatMap((r) => [...r.querySelectorAll<HTMLImageElement>("img[alt]")])
      .find((i) => !inChrome(i) && visible(i) && norm(i.alt).includes(want));
    return img ? (img.closest<HTMLElement>("a, figure, p") ?? img) : null;
  }
  if (/^(STRONG|B|EM|I|SPAN|A|BR)$/.test(found.tagName)) {
    const p = found.closest<HTMLElement>("p, li, h1, h2, h3, h4, h5");
    if (p && clean(p.textContent).length < 500) return p;
  }
  return found;
}

function findHeading(heading: string): HTMLElement | null {
  const h = best(headings(), (x) => x.text, heading);
  if (h) return h.el;
  const card = best(cardEls(), cardTitle, heading);
  return card?.querySelector<HTMLElement>(".card-title") ?? card ?? null;
}

async function showSection({ heading, text }: { heading?: string | null; text?: string | null }) {
  const h = heading ? findHeading(heading) : null;
  if (heading && !h && !text) {
    const known = context().headings.slice(0, 20).join(" | ");
    throw new Error(`no heading "${heading}" on ${location.pathname}; it has: ${known || "no headings"}`);
  }
  if (text) {
    const el = (h && smallestContaining(text, sectionOf(h))) ?? smallestContaining(text);
    if (!el) {
      const known = context().headings.slice(0, 15).join(" | ");
      throw new Error(`"${text}" is not on ${location.pathname}${known ? `; its headings are: ${known}` : ""}`);
    }
    const tall = el.getBoundingClientRect().height > window.innerHeight * 0.7;
    await scrollTo(el, tall ? "top" : "center");
    highlight(el);
    return;
  }
  if (!h) throw new Error("say which heading or text to show");
  const section = sectionOf(h);
  const box = boxOf(section);
  const height = box ? box.bottom - box.top : Infinity;
  const top = section.filter(shown).sort((x, y) => x.getBoundingClientRect().top - y.getBoundingClientRect().top)[0];
  await scrollTo(top && height <= window.innerHeight - headerHeight() - 32 ? top : h, "top");
  // A block taller than most of the screen is rung at its heading.
  highlight(height > window.innerHeight * 0.75 ? h : section);
}

// ─── open_faq: an accordion, by its button's words ────────────────────────

/** Open an accordion as the page itself would: through its Bootstrap, else
 *  by its button, else (no script at all) by setting what Bootstrap sets. */
export async function openAccordion(a: Accordion): Promise<void> {
  if (a.isOpen()) return;
  try {
    const Collapse = window.bootstrap?.Collapse;
    if (Collapse) Collapse.getOrCreateInstance(a.pane, { toggle: false }).show();
    else a.button.click();
  } catch {
    a.button.click();
  }
  if (await waitFor(a.isOpen, 1500)) return;
  a.pane.classList.remove("collapsing");
  a.pane.classList.add("collapse", "show");
  a.pane.style.height = "";
  a.button.classList.remove("collapsed");
  a.button.setAttribute("aria-expanded", "true");
}

async function openFaq({ question }: { question: string }) {
  const items = accordions();
  const item = best(items, (a) => a.label, question ?? "");
  if (!item) {
    const known = items.map((a) => a.label).slice(0, 20).join(" | ");
    throw new Error(`no accordion "${question}" on ${location.pathname}${known ? `; it has: ${known}` : "; it has none"}`);
  }
  await scrollTo(item.item, "top");
  await openAccordion(item);
  await sleep(350);
  const box = boxOf([item.item]);
  const tall = box ? box.bottom - box.top > window.innerHeight * 0.7 : false;
  await scrollTo(item.item, tall ? "top" : "center");
  highlight(tall ? item.button : item.item);
}

// ─── show_fees, show_events ───────────────────────────────────────────────

async function showFees({ path, about }: { path?: string; about?: "fees" | "admission" }) {
  const target = sitePath(path || ADMISSION_PATH);
  if (!samePath(location.pathname, target.pathname)) {
    return goTo(target, { command: "show_fees", payload: { path, about } });
  }
  const read = readFees();
  if (!read.fees.length && !read.status.length) {
    throw new Error(`the admission page (${location.pathname}) shows no fees and no admission lines right now`);
  }
  const ring = about === "admission" && read.statusEls.length ? read.statusEls : read.feesEl ? [read.feesEl] : read.statusEls;
  if (ring.length) {
    await scrollTo(ring[0], "center");
    highlight(ring);
  }
  emit("fees_read", { url: location.href, heading: read.heading, fees: read.fees, status: read.status });
}

async function showEvents({ path, count }: { path?: string; count?: number }) {
  const target = sitePath(path || CALENDAR_PATH);
  if (!samePath(location.pathname, target.pathname)) {
    return goTo(target, { command: "show_events", payload: { path, count } });
  }
  const frame = all<HTMLElement>("iframe").find((f) => /calendar\.google\.com/.test((f as HTMLIFrameElement).src) && shown(f));
  if (frame) {
    await scrollTo(frame, "top");
    highlight(frame);
  }
  const read = await readCalendar(count ?? EVENTS);
  if (!read) throw new Error("the school's calendar could not be read here: the extension did not answer");
  if (!read.ok) throw new Error(read.error ?? "the school's calendar could not be read");
  emit("events_read", { today: read.today ?? "", events: read.events ?? [] });
}

// ─── show_contact_card ────────────────────────────────────────────────────

const CARD_WORDS = {
  es: { title: "Escribir a Admisión", to: "Para", subject: "Asunto", open: "Abrir en mi correo", call: "Llamar", close: "Cerrar", note: "Se abre en tu correo para que lo revises y lo envíes tú." },
  en: { title: "Write to Admissions", to: "To", subject: "Subject", open: "Open in my email", call: "Call", close: "Close", note: "It opens in your email for you to review and send." },
} as const;

interface CardPayload {
  to: string;
  subject: string;
  body: string;
  phone: string;
  language: "en" | "es";
}

const CARD_ID = "voqalize-contact-card";

/** The card: ours, over the page, in a shadow root. Its button is a plain
 *  `mailto:` link the parent presses; nothing is ever sent from here. */
async function showContactCard(p: CardPayload) {
  if (!p?.to || !/^[^@\s]+@saintgeorge\.cl$/i.test(p.to)) throw new Error("the card only writes to the school's own address");
  document.getElementById(CARD_ID)?.remove();
  const w = CARD_WORDS[p.language === "en" ? "en" : "es"];
  const host = document.createElement("div");
  host.id = CARD_ID;
  host.setAttribute("data-voqalize", "contact-card");
  host.setAttribute("translate", "no");
  host.classList.add("notranslate");
  Object.assign(host.style, { position: "fixed", zIndex: "2147483001", left: "50%", top: "50%", transform: "translate(-50%, -50%)" });
  const root = host.attachShadow({ mode: "open" });
  const style = document.createElement("style");
  style.textContent = `
    :host { all: initial; }
    .card { box-sizing: border-box; width: min(440px, calc(100vw - 32px)); max-height: calc(100vh - 160px); overflow: auto;
      background: #fff; color: #1b2440; border-radius: 16px; box-shadow: 0 24px 60px rgba(10, 20, 60, 0.35);
      font: 15px/1.45 "Roboto Condensed", system-ui, sans-serif; border-top: 6px solid ${YELLOW}; }
    header { display: flex; justify-content: space-between; align-items: center; padding: 14px 18px; background: ${BLUE}; color: #fff; }
    h2 { margin: 0; font: 600 18px/1.2 "Montserrat Alternates", system-ui, sans-serif; }
    .x { all: unset; cursor: pointer; font-size: 22px; line-height: 1; padding: 2px 6px; color: #fff; }
    .body { padding: 14px 18px 18px; }
    dl { margin: 0 0 10px; display: grid; grid-template-columns: auto 1fr; gap: 4px 10px; }
    dt { color: #5b6480; } dd { margin: 0; font-weight: 600; word-break: break-word; }
    pre { white-space: pre-wrap; font: inherit; background: #f4f6fb; border-radius: 10px; padding: 10px 12px; margin: 0 0 12px; }
    .actions { display: flex; gap: 10px; flex-wrap: wrap; }
    a.btn { text-decoration: none; padding: 10px 16px; border-radius: 999px; font-weight: 700; }
    a.mail { background: ${YELLOW}; color: ${BLUE}; } a.tel { border: 2px solid ${BLUE}; color: ${BLUE}; }
    p.note { margin: 10px 0 0; color: #5b6480; font-size: 13px; }
  `;
  const card = document.createElement("div");
  card.className = "card";
  card.setAttribute("role", "dialog");
  card.setAttribute("aria-label", w.title);
  const header = document.createElement("header");
  const h2 = document.createElement("h2");
  h2.textContent = w.title;
  const close = document.createElement("button");
  close.className = "x";
  close.textContent = "×";
  close.setAttribute("aria-label", w.close);
  header.append(h2, close);
  const body = document.createElement("div");
  body.className = "body";
  const dl = document.createElement("dl");
  for (const [k, v] of [
    [w.to, p.to],
    [w.subject, p.subject],
  ]) {
    const dt = document.createElement("dt");
    dt.textContent = k;
    const dd = document.createElement("dd");
    dd.textContent = v;
    dl.append(dt, dd);
  }
  const pre = document.createElement("pre");
  pre.textContent = p.body;
  const actions = document.createElement("div");
  actions.className = "actions";
  const mail = document.createElement("a");
  mail.className = "btn mail";
  mail.href = `mailto:${p.to}?subject=${encodeURIComponent(p.subject)}&body=${encodeURIComponent(p.body)}`;
  mail.textContent = w.open;
  const tel = document.createElement("a");
  tel.className = "btn tel";
  tel.href = `tel:${p.phone.replace(/[^\d+]/g, "")}`;
  tel.textContent = `${w.call} ${p.phone}`;
  actions.append(mail, tel);
  const note = document.createElement("p");
  note.className = "note";
  note.textContent = w.note;
  body.append(dl, pre, actions, note);
  card.append(header, body);
  root.append(style, card);
  mail.addEventListener("click", () => emit("contact_used", { via: "email" }));
  tel.addEventListener("click", () => emit("contact_used", { via: "phone" }));
  close.addEventListener("click", () => {
    host.remove();
    emit("contact_used", { via: "closed" });
  });
  document.body.appendChild(host);
  emit("command_done", {
    command: "show_contact_card",
    detail: `the card is on screen with the email to ${p.to} ready to open, and the phone ${p.phone}`,
  });
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
  const here = location.origin + location.pathname + location.search;
  if (here === lastUrl) return;
  lastUrl = here;
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

const COMMANDS: Record<string, (payload: never) => Promise<void>> = {
  navigate,
  show_section: showSection,
  open_faq: openFaq,
  show_fees: showFees,
  show_events: showEvents,
  show_contact_card: showContactCard,
};

async function run(command: string, payload: unknown): Promise<{ ok: boolean; error?: string }> {
  const fn = COMMANDS[command];
  if (!fn) return { ok: false, error: `the page cannot ${command}` };
  try {
    await fn((payload ?? {}) as never);
    return { ok: true };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
}

if (!window.voqalizeSaintGeorge) {
  styleThePage();
  window.addEventListener("popstate", routeChanged);
  window.addEventListener("hashchange", routeChanged);
  void finishThen();
  window.voqalizeSaintGeorge = { run, context, start, commands: Object.keys(COMMANDS) };
}
