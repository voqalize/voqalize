/**
 * The site adapter: drive santanderarena.cl from the outside, with no help
 * from Santander Arena's developers.
 *
 * The brain sends a Voqalize `ui-command` ({command, payload}) and `run`
 * performs it on the page in front; the page reports back through `start`,
 * which calls `emit(event, payload)` for every page the visitor lands on and
 * for a move that could not be finished after a page load.
 *
 * What the site is, for a script like this: a Prontus CMS site, rendered on
 * the server, with jQuery and Swiper carousels. Every move between pages is a
 * full page load, so a move to another page cannot finish on the page that
 * asked for it: `navigate` writes what is left to do (a heading, a text, a
 * question) to `sessionStorage` and loads the page, and the adapter on the
 * next page does it once that page has settled. The window scrolls normally,
 * under a header (`#header`) that turns `position: fixed` once the page has
 * scrolled.
 *
 * Where the content is, page by page:
 *
 *   - Most pages are one article: a title (`header.enc-main .enc-main__title`)
 *     over a body (`.CUERPO`) written in the CMS editor. Some bodies have real
 *     headings (`h1`–`h3`, the bars on /bares, the groups on
 *     /preguntas-frecuentes); others have none, and what reads as a heading
 *     there is a `span.titulos` (the terraces on /terrazas) or a paragraph that
 *     is nothing but bold text (`p > strong`, "BLESSD" on an event page).
 *     Under the body sit a photo carousel (`.swiper.mySwiper2`), a video or a
 *     map in an `iframe`, and on the form pages the form (`#formProntus`).
 *   - The home page and the list pages are cards (`article.card`, each titled
 *     by `.card__title`) under section heads (`.block-head__title`); on the
 *     home page most card rows are Swiper carousels, and some cards start off
 *     to the right of the screen.
 *   - /cartelera shows one month of events at a time. The site's own script
 *     (`window.buscador_eventos`) holds every event and puts only the month's
 *     cards in the page; "Anterior" and "Siguiente" (`.btn-month-nav`) move
 *     the month. An event in another month is reached the way a visitor
 *     reaches it, with those buttons.
 *   - The FAQ is not an accordion: each question is a bold paragraph,
 *     numbered ("3. ¿Qué documentos debo llevar para ingresar?"), and the
 *     answer is the paragraph under it.
 *
 * Tickets, parking and VIP experiences are sold on puntoticket.com; private
 * event bookings leave for reservas.movistararena.cl.
 */

declare global {
  interface Window {
    voqalizeSantander?: Adapter;
    /** The /cartelera page's own event browser (buscador_eventos.class.js). */
    buscador_eventos?: {
      vars?: { eventos?: ArrayLike<{ get?: (i: number) => HTMLElement | undefined; 0?: HTMLElement }> };
    };
  }
  interface HTMLElement {
    /** Swiper keeps its instance on the container element. */
    swiper?: {
      slideTo(index: number, speed?: number): void;
      slideToLoop?(index: number, speed?: number): void;
      slides?: ArrayLike<HTMLElement>;
      params?: { speed?: number; loop?: boolean };
      destroyed?: boolean;
    };
  }
}

export interface Adapter {
  /** Perform one of the brain's page Actions. Never throws. */
  run(command: string, payload: unknown): Promise<{ ok: boolean; error?: string }>;
  /** What the visitor is looking at now, as a `page_changed` payload. */
  context(): PageContext;
  /** Report the page, and a move left over from the last page that could not
   *  be made, through `emit`, until the returned stop. The page as it stands
   *  is reported first. */
  start(emit: (event: string, payload: unknown) => void): () => void;
  /** The Actions `run` performs. */
  readonly commands: readonly string[];
}

export interface PageContext {
  url: string;
  path: string;
  title: string;
  /** event = /nuestra-cartelera/…, news = /arena-news/<slug>. */
  kind: "home" | "event" | "news" | "page";
  /** Section headings a visitor can be taken to, in page order. */
  headings: string[];
  /** The FAQ questions on the page. */
  faqs: string[];
  /** Titles of the cards on the page: events, bars, experiences, news, spaces;
   *  the ones in carousels that are off screen too. */
  cards: string[];
  /** Every link out to a ticket or reservation site, with what it is for. */
  tickets: { label: string; url: string }[];
}

/** Their own accent, read off their "Comprar tickets" button when it is there. */
const RING_FALLBACK = "rgb(255, 153, 161)";
const RING_MS = 5500;
const WAIT_MS = 8000;
const MAX_HEADINGS = 80;
const MAX_FAQS = 120;
const MAX_CARDS = 80;
const MAX_TICKETS = 40;
/** Where `navigate` leaves the rest of a move for the next page. */
const THEN_KEY = "voqalize.santander.then";
/** A move left longer ago than this belongs to some other visit. */
const THEN_MAX_AGE_MS = 60_000;

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const clean = (s: string | null | undefined) => (s ?? "").replace(/\s+/g, " ").trim();
/**
 * For matching what the brain said against what the page shows: lower case,
 * without accents (á → a, ñ → n), with straight quotes and dashes, and without
 * the opening "¿"/"¡" and closing punctuation either side may or may not have.
 */
const norm = (s: string | null | undefined) =>
  clean(s)
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[‘’´`]/g, "'")
    .replace(/[“”«»]/g, '"')
    .replace(/[‐-―]/g, "-")
    .replace(/\s*&\s*/g, " y ")
    .replace(/[¿¡]/g, "")
    // A paragraph's lead is reported cut short, with "…".
    .replace(/…/g, "")
    .replace(/^[\s"']+|[\s"'.:;,?!]+$/g, "")
    .trim();

const visible = (el: Element | null | undefined): el is HTMLElement => {
  if (!el) return false;
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
};

/** `visible` as a plain answer, where a narrowing guard would narrow too far. */
const shown = (el: Element): boolean => visible(el);

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

function main(): HTMLElement {
  return document.querySelector<HTMLElement>("div.main") ?? document.querySelector("main") ?? document.body;
}

/** Not the page's content: the header and its menus, the footer, the social
 *  bar on the right, breadcrumbs, the photo-download dialogs, and our own. */
const CHROME =
  "#header, header.header, footer, .footer, .lateral_bar, .breadcrumbs, .menu-responsive, nav.menu, .modal, [data-voqalize]";
const inChrome = (el: Element) => Boolean(el.closest(CHROME));

// ─── Scrolling ────────────────────────────────────────────────────────────

/** The height of whatever is pinned to the top of the viewport. The header is
 *  in the flow at the top of the page and fixed once it has scrolled, so
 *  before a scroll its own height is the best guess. */
function headerHeight(): number {
  let h = 0;
  for (const el of document.querySelectorAll<HTMLElement>("#header, header.header")) {
    const r = el.getBoundingClientRect();
    if (r.height <= 0 || r.height > 220) continue;
    const pos = getComputedStyle(el).position;
    h = Math.max(h, pos === "fixed" || pos === "sticky" ? r.bottom : r.height);
  }
  return h;
}

/** How far `el` is from where it should sit: under the header (`top`) or in
 *  the middle of the screen. */
function distance(el: Element, align: "top" | "center"): number {
  const r = el.getBoundingClientRect();
  const top = headerHeight() + 16;
  if (align === "center") {
    const room = window.innerHeight - top;
    return r.top - (top + Math.max(0, (room - r.height) / 2));
  }
  return r.top - top;
}

/** The window has stopped scrolling. */
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

/**
 * Scroll the window so `el` sits under the header (`top`) or in the middle of
 * the screen, and check that it did. The header turns fixed as the page
 * scrolls and images load as they come into view, so it measures again and
 * corrects, up to twice.
 */
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
// Drawn over the page, never on Santander Arena's own elements. Fixed, and
// moved with its target every frame, so it follows a scroll and a carousel
// that slides under it.

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
      border: "2px solid var(--voqalize-ring)",
      borderRadius: "12px",
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

/** The site's accent: the fill of its primary ("fucsia") buttons. */
function accent(): string {
  const btn = document.querySelector(".btn__primary--fucsia");
  const bg = btn ? getComputedStyle(btn).backgroundColor : "";
  return /^rgba?\(/.test(bg) && !/,\s*0\)$/.test(bg) ? bg : RING_FALLBACK;
}

function styleThePage(): void {
  if (document.querySelector("style[data-voqalize=santander]")) return;
  const style = document.createElement("style");
  style.setAttribute("data-voqalize", "santander");
  // Javier takes the bottom-right corner, where the forms' reCAPTCHA badge
  // sits; it stands aside while the extension runs. The social bar on the
  // right edge sits higher up and stays.
  style.textContent = `
    :root { --voqalize-ring: ${RING_FALLBACK}; }
    .grecaptcha-badge { visibility: hidden !important; }
    @keyframes voqalize-ring {
      0%, 100% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--voqalize-ring) 55%, transparent); }
      50% { box-shadow: 0 0 0 10px color-mix(in srgb, var(--voqalize-ring) 0%, transparent); }
    }
  `;
  (document.head ?? document.documentElement).appendChild(style);
  const paint = () => document.documentElement.style.setProperty("--voqalize-ring", accent());
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", paint, { once: true });
  else paint();
}

// ─── What the page shows ──────────────────────────────────────────────────

/** A paragraph that is a question, set in bold: "3. ¿Qué documentos debo
 *  llevar para ingresar?". Its number is not part of the question. */
function questionText(el: Element): string | null {
  const t = clean((el as HTMLElement).innerText || el.textContent);
  if (t.length < 6 || t.length > 200 || !/\?\s*$/.test(t)) return null;
  const bold = clean([...el.querySelectorAll("strong, b")].map((b) => b.textContent).join(" "));
  if (bold.length < t.replace(/^\d+\s*[.)-]+\s*/, "").length * 0.6) return null;
  return t.replace(/^\d+\s*[.)\-–]+\s*/, "");
}

interface Faq {
  question: string;
  /** The block that holds the question: its paragraph, or its list. */
  block: HTMLElement;
  /** What to click to open it, when it is a real accordion. */
  toggle: HTMLElement | null;
  isOpen: () => boolean;
  /** The answer's blocks. */
  answer: () => HTMLElement[];
}

/** The block a paragraph stands for among its siblings: an `<ol>` holding one
 *  question is the question. */
function blockOf(el: HTMLElement): HTMLElement {
  const list = el.parentElement;
  if (el.tagName === "LI" && list && /^(OL|UL)$/.test(list.tagName) && list.children.length === 1) return list;
  return el;
}

function faqItems(): Faq[] {
  const items: Faq[] = [];
  const root = main();
  // The site's FAQ: bold questions in the article body, each answered by the
  // paragraphs under it.
  for (const el of root.querySelectorAll<HTMLElement>(".CUERPO p, .CUERPO li")) {
    if (inChrome(el) || !shown(el)) continue;
    const question = questionText(el);
    if (!question) continue;
    const block = blockOf(el);
    items.push({
      question,
      block,
      toggle: null,
      isOpen: () => true,
      answer: () => {
        const out: HTMLElement[] = [];
        for (let n = block.nextElementSibling; n && out.length < 4; n = n.nextElementSibling) {
          if (!(n instanceof HTMLElement)) continue;
          if (isBreak(n) || [n, ...n.querySelectorAll<HTMLElement>("p, li")].some((p) => questionText(p))) break;
          if (shown(n)) out.push(n);
        }
        return out;
      },
    });
  }
  // A real accordion, should a page grow one: `<details>`, or a button that
  // says whether it is expanded.
  for (const d of root.querySelectorAll<HTMLDetailsElement>("details")) {
    const summary = d.querySelector<HTMLElement>("summary");
    if (!summary || inChrome(d)) continue;
    items.push({
      question: clean(summary.innerText),
      block: d,
      toggle: summary,
      isOpen: () => d.open,
      answer: () => [d],
    });
  }
  for (const t of root.querySelectorAll<HTMLElement>("[aria-expanded][aria-controls]")) {
    if (inChrome(t)) continue;
    const panel = document.getElementById(t.getAttribute("aria-controls") ?? "");
    if (!panel) continue;
    items.push({
      question: clean(t.innerText),
      block: t.parentElement ?? t,
      toggle: t,
      isOpen: () => t.getAttribute("aria-expanded") === "true",
      answer: () => [panel],
    });
  }
  return items.filter((i) => i.question).sort((a, b) => inOrder(a.block, b.block));
}

/** A rule or a heading ends the block above it. */
function isBreak(el: Element): boolean {
  if (el.tagName === "HR" || /^H[1-4]$/.test(el.tagName)) return true;
  // A terrace's name is a `span.titulos`; so, on /terrazas, is its photo's.
  return [...el.querySelectorAll("span.titulos")].some((t) => clean(t.textContent));
}

/** Where a block of the article body stops: an element that is, or holds, a
 *  heading-like line, or a rule. */
function startsSection(el: Element): boolean {
  if (isBreak(el)) return Boolean(clean(el.textContent)) || el.tagName === "HR";
  return el instanceof HTMLElement && (isBoldLine(el) || Boolean(questionText(el)));
}

/** A paragraph that is nothing but a short bold line: what reads as a
 *  heading in an article body written without headings ("BLESSD",
 *  "2 de octubre – Santander Arena"). */
function isBoldLine(p: HTMLElement): boolean {
  if (!/^(P|LI)$/.test(p.tagName)) return false;
  const t = clean(p.innerText || p.textContent);
  if (t.length < 2 || t.length > 90 || /\?\s*$/.test(t)) return false;
  if (p.querySelector("img, iframe, a[href]")) return false;
  const bold = clean([...p.querySelectorAll("strong, b, span.titulos")].map((b) => b.textContent).join(" "));
  return norm(bold) === norm(t);
}

/** What a landmark with no words of its own is called. */
function landmarkName(el: HTMLElement): string | null {
  if (el.matches(".swiper.mySwiper2")) return "Galería de fotos";
  if (el.matches("form#formProntus")) return "Formulario";
  if (el.matches("nav.filter")) return "Filtros de eventos";
  if (el.tagName === "IFRAME") {
    const src = (el as HTMLIFrameElement).src;
    if (/google\.[a-z.]+\/maps/.test(src)) return "Mapa";
    if (/youtube|vimeo|\/player\/video/.test(src)) return "Video";
  }
  return null;
}

/** Paragraphs that stand in for headings, which head only themselves. */
const leads = new WeakSet<Element>();

/** What a paragraph is called when it stands in for a heading: its first
 *  bold words, when they say something, or its first words. */
function paragraphLead(p: HTMLElement): string | null {
  const t = clean(p.innerText);
  if (t.length < 60 || !shown(p)) return null;
  const bold = clean(p.querySelector("strong, b")?.textContent);
  const cut = (s: string, n: number) => {
    const words = s.split(" ");
    return words.length > n ? `${words.slice(0, n).join(" ").replace(/[,.;:]$/, "")}…` : s;
  };
  if (bold.length >= 16 && norm(bold) !== "santander arena") return cut(bold, 10);
  return cut(t, 8);
}

interface Head {
  el: HTMLElement;
  text: string;
}

/**
 * Headings the visitor can be taken to, in page order: the page title, the
 * real headings, and on article bodies without them the lines that act as
 * headings (`span.titulos`, a paragraph of bold text). Then the landmarks with
 * no text: the photo carousel, a video, a map, a form. Not the FAQ questions,
 * which are `open_faq`'s, nor card titles, which are `cards`.
 */
function headings(): Head[] {
  const root = main();
  const found: Head[] = [];
  const add = (el: HTMLElement, text: string | null) => {
    if (text && text.length > 1 && !inChrome(el) && shown(el)) found.push({ el, text });
  };
  for (const h of root.querySelectorAll<HTMLElement>(
    "h1, h2, h3, h4, .block-hor__title, .CUERPO span.titulos",
  )) {
    if (h.closest(".card, .downloads__item") && h.matches(".card__title, .card__subtitle, .download__title")) continue;
    if (h.parentElement?.closest(".CUERPO span.titulos, h1, h2, h3, h4")) continue;
    add(h, clean(h.innerText || h.textContent));
  }
  for (const p of root.querySelectorAll<HTMLElement>(".CUERPO p, .CUERPO li")) {
    if (isBoldLine(p) && !p.querySelector("span.titulos")) add(p, clean(p.innerText));
  }
  // A body with nothing that reads as a heading (/santander-suites,
  // /paseo-de-las-estrellas, /muro-de-momentos-en-vivo, /estacionamientos):
  // each paragraph is a stop, called by its first bold words or its opening.
  for (const body of root.querySelectorAll<HTMLElement>(".CUERPO")) {
    if (found.some((h) => body.contains(h.el)) || faqItems().some((f) => body.contains(f.block))) continue;
    for (const p of body.querySelectorAll<HTMLElement>(":scope > p, :scope > div > p")) {
      const lead = paragraphLead(p);
      if (!lead) continue;
      leads.add(p);
      add(p, lead);
    }
  }
  for (const el of root.querySelectorAll<HTMLElement>(".swiper.mySwiper2, form#formProntus, nav.filter, iframe")) {
    add(el, landmarkName(el));
  }
  found.sort((a, b) => inOrder(a.el, b.el));
  const seen = new Set<string>();
  return found.filter((h) => !seen.has(norm(h.text)) && seen.add(norm(h.text)));
}

const CARD = "article.card, aside.card, .downloads__item";
const CARD_TITLE = ".card__title, .download__title";

function cardEls(): HTMLElement[] {
  return [...main().querySelectorAll<HTMLElement>(CARD)].filter((c) => !inChrome(c) && c.querySelector(CARD_TITLE));
}
const cardTitle = (card: Element) => clean(card.querySelector<HTMLElement>(CARD_TITLE)?.textContent);

/** /cartelera's events that are not in the page because they are in another
 *  month: the site's script holds them. */
function offPageEvents(): HTMLElement[] {
  if (!/^\/cartelera\/?$/i.test(location.pathname)) return [];
  const all = window.buscador_eventos?.vars?.eventos;
  if (!all) return [];
  const out: HTMLElement[] = [];
  for (let i = 0; i < all.length; i++) {
    const $c = all[i];
    const el = $c?.[0] ?? $c?.get?.(0);
    if (el instanceof HTMLElement && !el.isConnected) out.push(el);
  }
  return out;
}

/** An event card's date, from its `data-fecha` (dd/mm/yyyy). */
function eventDate(card: Element): Date | null {
  const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(card.getAttribute("data-fecha") ?? "");
  return m ? new Date(Number(m[3]), Number(m[2]) - 1, Number(m[1])) : null;
}

/** Events still to come, soonest first. */
function upcoming(cards: HTMLElement[]): HTMLElement[] {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return cards.filter((c) => (eventDate(c) ?? today) >= today);
}

function cards(): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const c of [...cardEls(), ...upcoming(offPageEvents())]) {
    const t = cardTitle(c);
    if (!t || seen.has(norm(t))) continue;
    seen.add(norm(t));
    out.push(t);
    if (out.length >= MAX_CARDS) break;
  }
  return out;
}

const TICKET_HOST = /(^|\.)(puntoticket\.com|ticketmaster\.[a-z.]+|passline\.com|eventbrite\.[a-z.]+)$|^reservas?\./i;

/** What a ticket link is for: its words (or its icon's), after the title of
 *  the card or event it belongs to. */
function ticketLabel(a: HTMLAnchorElement): string {
  const own =
    clean(a.innerText || a.textContent) ||
    clean(a.querySelector(".tooltip-text")?.textContent) ||
    clean(a.querySelector("img")?.alt) ||
    clean(a.getAttribute("aria-label") || a.title) ||
    (a.querySelector("img") ? "Banner" : "");
  const holder = a.closest<HTMLElement>(`${CARD}, .block-hor, .card__event--sidebar`);
  const title = clean(
    holder?.querySelector<HTMLElement>(`${CARD_TITLE}, .block-hor__title`)?.textContent ??
      (holder ? "" : document.querySelector(".enc-main__title, .block-hor__title")?.textContent),
  );
  if (!own) return title ? `${title} – Banner` : "Banner";
  return title && !norm(own).includes(norm(title)) ? `${title} – ${own}` : own;
}

function tickets(): { label: string; url: string }[] {
  const seen = new Set<string>();
  const out: { label: string; url: string }[] = [];
  const links = [
    ...main().querySelectorAll<HTMLAnchorElement>("a[href]"),
    ...upcoming(offPageEvents()).flatMap((c) => [...c.querySelectorAll<HTMLAnchorElement>("a[href]")]),
  ];
  for (const a of links) {
    let host = "";
    try {
      host = new URL(a.href).host;
    } catch {
      continue;
    }
    if (!TICKET_HOST.test(host) || (a.isConnected && inChrome(a))) continue;
    const label = ticketLabel(a);
    const key = `${a.href}|${norm(label)}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ label, url: a.href });
    if (out.length >= MAX_TICKETS) break;
  }
  return out;
}

function kind(): PageContext["kind"] {
  const p = location.pathname.replace(/\/+$/, "");
  if (p === "" || /^\/index\.html?$/i.test(p)) return "home";
  if (/^\/nuestra-cartelera\//i.test(p)) return "event";
  if (/^\/arena-news\/[^/]+/i.test(p)) return "news";
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
    faqs: faqItems()
      .map((f) => f.question)
      .slice(0, MAX_FAQS),
    cards: cards(),
    tickets: tickets(),
  };
}

// ─── navigate ─────────────────────────────────────────────────────────────

const strip = (p: string) => (p || "/").replace(/\/+$/, "") || "/";
const samePath = (a: string, b: string) => strip(a).toLowerCase() === strip(b).toLowerCase();
const siteHost = (h: string) => h.replace(/^www\./i, "").toLowerCase();

interface Then {
  heading?: string | null;
  text?: string | null;
  faq?: string | null;
}

/**
 * The page has settled: loaded (or near enough: /cartelera's trackers hold
 * its `load` back by seconds), its fonts in, its carousels built (Swiper
 * keeps its instance on each container), and the DOM quiet for a moment.
 * Images that arrive later move the page under a scroll; `scrollTo` measures
 * again and corrects for that.
 */
async function settled(): Promise<void> {
  if (document.readyState !== "complete") {
    await Promise.race([
      new Promise<void>((r) => window.addEventListener("load", () => r(), { once: true })),
      sleep(2500),
    ]);
  }
  await Promise.race([document.fonts?.ready, sleep(2000)]);
  await waitFor(
    () =>
      [...document.querySelectorAll(".swiper-wrapper")].every((w) => {
        const box = w.parentElement;
        return !box || Boolean(box.swiper) || !box.querySelector(".swiper-slide + .swiper-slide");
      }),
    2500,
  );
  await new Promise<void>((resolve) => {
    let timer = setTimeout(done, 450);
    const obs = new MutationObserver(() => {
      clearTimeout(timer);
      timer = setTimeout(done, 450);
    });
    obs.observe(document.body, { childList: true, subtree: true });
    const cap = setTimeout(done, 3000);
    function done() {
      obs.disconnect();
      clearTimeout(timer);
      clearTimeout(cap);
      resolve();
    }
  });
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
  if (typeof path !== "string" || !path.trim()) throw new Error("say which page to go to, as a path like /bares");
  const target = new URL(path.trim(), location.origin);
  if (siteHost(target.host) !== siteHost(location.host)) {
    throw new Error(`${target.href} is not on santanderarena.cl; only the site's own pages can be opened here`);
  }
  if (!samePath(location.pathname, target.pathname) || target.search !== location.search) {
    // A full page load: what is left is done by the adapter on the next page.
    const then = { heading: heading ?? null, text: text ?? null, faq: faq ?? null, at: Date.now() };
    try {
      if (then.heading || then.text || then.faq) sessionStorage.setItem(THEN_KEY, JSON.stringify(then));
      else sessionStorage.removeItem(THEN_KEY);
    } catch {
      // Storage refused: the page still loads, at its top.
    }
    clearHighlight();
    location.assign(target.pathname + target.search + target.hash);
    return;
  }
  if (faq) return openFaq({ question: faq });
  if (heading || text) return showSection({ heading, text });
  await scrollToTopOfPage();
}

/** What the last page's `navigate` left to do here, taken once. */
function takeThen(): Then | null {
  try {
    const raw = sessionStorage.getItem(THEN_KEY);
    if (!raw) return null;
    sessionStorage.removeItem(THEN_KEY);
    const then = JSON.parse(raw) as Then & { at?: number };
    if (typeof then.at === "number" && Date.now() - then.at > THEN_MAX_AGE_MS) return null;
    return then.heading || then.text || then.faq ? then : null;
  } catch {
    return null;
  }
}

/** Finish the move a `navigate` on the last page started, once this page has
 *  settled; a failure is reported as the brain's cue that did not land. */
async function finishThen(): Promise<void> {
  const then = takeThen();
  if (!then) return;
  await settled();
  try {
    if (then.faq) await openFaq({ question: then.faq });
    else await showSection({ heading: then.heading, text: then.text });
  } catch (error) {
    emit("command_failed", { command: "cue", reason: error instanceof Error ? error.message : String(error) });
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

/** A heading on the page, or a card by its title (the home page's "Bares" is
 *  a card in a carousel, and so is every event). */
function findHeading(heading: string): HTMLElement | null {
  const h = best(headings(), (x) => x.text, heading);
  if (h) return h.el;
  const card = best(cardEls(), cardTitle, heading);
  return card?.querySelector<HTMLElement>(CARD_TITLE) ?? null;
}

/** The direct child of the article body that holds `el`, if it is in one. */
function bodyBlock(el: HTMLElement): HTMLElement | null {
  const body = el.closest<HTMLElement>(".CUERPO");
  if (!body || el === body) return null;
  let b: HTMLElement = el;
  while (b.parentElement && b.parentElement !== body) b = b.parentElement;
  return b;
}

/**
 * What a heading heads, as one or more elements to ring together: a card's
 * title, its card; a section head, its `<section>`; the page title, the page's
 * banner; a heading in an article body, it and the blocks under it up to the
 * next heading-like line or rule.
 */
function sectionOf(h: HTMLElement): HTMLElement[] {
  const card = h.closest<HTMLElement>(CARD);
  if (card && h.matches(CARD_TITLE)) return [card];
  if (h.matches(".enc-main__title")) return [h.closest<HTMLElement>("header.enc-main") ?? h];
  if (landmarkName(h) || leads.has(h)) return [h];
  const block = bodyBlock(h);
  if (block) {
    const out = [block];
    for (let n = block.nextElementSibling; n && out.length < 10; n = n.nextElementSibling) {
      if (!(n instanceof HTMLElement)) continue;
      if (startsSection(n)) break;
      if (shown(n) && (clean(n.innerText) || n.querySelector("img, iframe"))) out.push(n);
    }
    return out;
  }
  const s = h.closest<HTMLElement>("section, header.enc-main, article.block-hor, nav.filter");
  if (s && s !== main()) return [s];
  let el = h.parentElement;
  while (el && el !== main() && clean(el.textContent).length <= clean(h.textContent).length + 20) {
    el = el.parentElement;
  }
  return [el ?? h];
}

/** The smallest visible element in `root` whose text contains `text`; an
 *  event's, bar's or news item's title is its whole card. */
function smallestContaining(root: Element, text: string): HTMLElement | null {
  const want = norm(text);
  if (!want) return null;
  let found: HTMLElement | null = null;
  let bestLen = Infinity;
  for (const el of root.querySelectorAll<HTMLElement>("*")) {
    if (inChrome(el) || /^(SCRIPT|STYLE|NOSCRIPT|svg)$/i.test(el.tagName) || !visible(el)) continue;
    const t = norm(el.textContent);
    if (!t.includes(want) || t.length >= bestLen) continue;
    found = el;
    bestLen = t.length;
  }
  if (!found) {
    // A banner says what it is only in its `alt`: "EXPERIENCIAS VIP".
    const img = [...root.querySelectorAll<HTMLImageElement>("img[alt], img[title]")].find(
      (i) => !inChrome(i) && visible(i) && norm(i.alt || i.title).includes(want),
    );
    return img ? (img.closest<HTMLElement>(`${CARD}, a, figure, p`) ?? img) : null;
  }
  const card = found.closest<HTMLElement>(CARD);
  if (card && root.contains(card) && found.closest(CARD_TITLE)) return card;
  // A word inside a paragraph is read with its paragraph.
  if (/^(STRONG|B|EM|I|SPAN|A)$/.test(found.tagName) && found.closest(".CUERPO")) {
    const p = found.closest<HTMLElement>("p, li, h1, h2, h3, h4");
    if (p && clean(p.innerText).length < 400) return p;
  }
  return found;
}

// ─── Content in a carousel, or in another month ───────────────────────────
// Carousels (Swiper) keep their slides side by side and show some: a slide to
// the right of its carousel is out of sight even when the page is scrolled to
// it. /cartelera keeps the other months' events out of the page.

/** The carousel a slide sits in: the element Swiper was built on. */
function carouselOf(slide: HTMLElement): HTMLElement | null {
  return slide.parentElement?.parentElement ?? null;
}

/** If `el` is in a carousel slide that is off its carousel's edge, slide the
 *  carousel to it: through the Swiper instance the site built, else with its
 *  own next and previous buttons. */
async function reveal(el: HTMLElement): Promise<void> {
  for (let slide = el.closest<HTMLElement>(".swiper-slide"); slide; ) {
    const box = carouselOf(slide);
    if (!box) break;
    await slideInto(box, slide);
    slide = box.parentElement?.closest<HTMLElement>(".swiper-slide") ?? null;
  }
}

function inside(slide: HTMLElement, box: HTMLElement): boolean {
  const s = slide.getBoundingClientRect();
  const b = box.getBoundingClientRect();
  const left = Math.max(b.left, 0);
  const right = Math.min(b.right, window.innerWidth);
  return s.left >= left - 2 && s.right <= right + 2;
}

async function slideInto(box: HTMLElement, slide: HTMLElement): Promise<void> {
  if (inside(slide, box)) return;
  const sw = box.swiper;
  const slides = [...(box.querySelector(".swiper-wrapper")?.children ?? [])] as HTMLElement[];
  const index = slides.indexOf(slide);
  if (sw && !sw.destroyed && index >= 0) {
    // In a looping carousel Swiper's own index is `data-swiper-slide-index`.
    const real = Number(slide.getAttribute("data-swiper-slide-index") ?? index);
    if (sw.params?.loop && sw.slideToLoop) sw.slideToLoop(real);
    else sw.slideTo(index);
    await waitFor(() => inside(slide, box), (sw.params?.speed ?? 300) + 1500);
    await sleep(150);
    return;
  }
  // No instance: press the carousel's arrows, the way a visitor would.
  const scope = box.parentElement ?? box;
  for (let i = 0; i < slides.length && !inside(slide, box); i++) {
    const right = slide.getBoundingClientRect().left > box.getBoundingClientRect().left;
    const btn = scope.querySelector<HTMLElement>(right ? ".swiper-button-next" : ".swiper-button-prev");
    if (!btn || btn.classList.contains("swiper-button-disabled")) break;
    btn.click();
    await sleep(450);
  }
}

/** On /cartelera, the event called `text` in another month: move the month
 *  with "Anterior"/"Siguiente" until its card is in the page. */
async function showOtherMonth(text: string): Promise<boolean> {
  const hits = offPageEvents().filter((c) => norm(cardTitle(c)).includes(norm(text)));
  if (!hits.length) return false;
  const card = upcoming(hits)[0] ?? hits[hits.length - 1];
  const when = eventDate(card);
  const heading = document.getElementById("title-filter");
  const shownMonth = parseMonth(clean(heading?.textContent));
  if (!when || !shownMonth) return false;
  let steps = (when.getFullYear() - shownMonth.getFullYear()) * 12 + (when.getMonth() - shownMonth.getMonth());
  const dir = steps > 0 ? "1" : "-1";
  const btn = document.querySelector<HTMLElement>(`.btn-month-nav[data-direction="${dir}"]`);
  if (!btn || !steps) return false;
  for (steps = Math.abs(steps); steps > 0; steps--) {
    btn.click();
    await sleep(250);
  }
  return waitFor(() => card.isConnected, 2000).then(Boolean);
}

const MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
/** "Octubre 2026", the month /cartelera is showing. */
function parseMonth(s: string): Date | null {
  const m = /^([a-z]+)\s+(\d{4})$/.exec(norm(s));
  const i = m ? MONTHS.indexOf(m[1]) : -1;
  return m && i >= 0 ? new Date(Number(m[2]), i, 1) : null;
}

async function showSection({ heading, text }: { heading?: string | null; text?: string | null }) {
  const h = heading ? findHeading(heading) : null;
  if (heading && !h && !text) {
    const known = [...context().headings.slice(0, 20), ...cards().slice(0, 10)].join(" | ");
    throw new Error(`no heading "${heading}" on ${location.pathname}; it has: ${known || "no headings"}`);
  }
  if (text) {
    const within = h ? sectionOf(h) : [];
    const find = () => {
      for (const s of within) {
        const el = smallestContaining(s, text);
        if (el) return el;
      }
      return smallestContaining(main(), text);
    };
    let el = find();
    if (!el && (await showOtherMonth(text))) el = find();
    if (!el) {
      const known = cards().slice(0, 15).join(" | ");
      throw new Error(`"${text}" is not on ${location.pathname}${known ? `; its cards are: ${known}` : ""}`);
    }
    // A card in a carousel: bring the page to the carousel, then the card in.
    await scrollTo(el, el.getBoundingClientRect().height > window.innerHeight * 0.7 ? "top" : "center");
    await reveal(el);
    const tall = el.getBoundingClientRect().height > window.innerHeight * 0.7;
    await scrollTo(el, tall ? "top" : "center");
    highlight(el);
    return;
  }
  if (!h) throw new Error("say which heading or text to show");
  await scrollTo(h, "top");
  await reveal(h);
  const section = sectionOf(h);
  const box = boxOf(section);
  const height = box ? box.bottom - box.top : Infinity;
  // A block that fits under the header is shown from its top (a card's title
  // sits at its foot); a longer one from its heading.
  const top = section.filter(shown).sort((x, y) => x.getBoundingClientRect().top - y.getBoundingClientRect().top)[0];
  await scrollTo(top && height <= window.innerHeight - headerHeight() - 32 ? top : h, "top");
  // A block taller than most of the screen is rung at its heading: on /bares a
  // whole bar (heading, text and photo) made a ring a thousand pixels tall.
  highlight(height > window.innerHeight * 0.75 ? h : section);
}

// ─── open_faq ─────────────────────────────────────────────────────────────

async function openFaq({ question }: { question: string }) {
  const all = faqItems();
  const item = best(all, (f) => f.question, question ?? "");
  if (!item) {
    const known = all.map((f) => f.question).slice(0, 15).join(" | ");
    throw new Error(
      `no FAQ "${question}" on ${location.pathname}${known ? `; it has: ${known}` : "; the questions are on /preguntas-frecuentes"}`,
    );
  }
  await scrollTo(item.block, "center");
  if (!item.isOpen() && item.toggle) {
    item.toggle.click();
    await waitFor(item.isOpen, 2000);
    await sleep(400);
  }
  const group = [item.block, ...item.answer()];
  const box = boxOf(group);
  const tall = box ? box.bottom - box.top > window.innerHeight * 0.7 : false;
  await scrollTo(item.block, tall ? "top" : "center");
  highlight(group);
}

// ─── Reporting ────────────────────────────────────────────────────────────

let emitter: ((event: string, payload: unknown) => void) | null = null;
/** What happened before anyone listened: a move left from the last page that
 *  failed before the call reconnected on this one. */
const backlog: [string, unknown][] = [];
function emit(event: string, payload: unknown): void {
  if (emitter) emitter(event, payload);
  else backlog.push([event, payload]);
}

let lastUrl: string | null = null;
/** The site loads a whole page for every move, so this only sees a change of
 *  hash or a history step the page made without loading. */
function routeChanged(): void {
  const here = location.origin + location.pathname + location.search;
  if (here === lastUrl) return;
  lastUrl = here;
  clearHighlight();
  if (emitter) emitter("page_changed", context());
}

function watchRoutes(): void {
  window.addEventListener("popstate", routeChanged);
  window.addEventListener("hashchange", routeChanged);
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

if (!window.voqalizeSantander) {
  styleThePage();
  watchRoutes();
  void finishThen();
  window.voqalizeSantander = { run, context, start, commands: Object.keys(COMMANDS) };
}

export {};
