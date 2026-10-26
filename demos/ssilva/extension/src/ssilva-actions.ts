/**
 * The site adapter: drive www.ssilva.cl from the outside, with no help from
 * Ssilva's developers.
 *
 * The brain sends a Voqalize `ui-command` ({command, payload}) and `run`
 * performs it on the page in front; the page reports back through `start`,
 * which calls `emit(event, payload)` for every page, typology, project list
 * and quote-form change, whoever caused it.
 *
 * What ssilva.cl is, for a script like this:
 *
 *   - WordPress pages with Vue components in them. **Every link is a full page
 *     load**, so a move to another page leaves what to do there with the
 *     extension's service worker (`setPendingMove`) and loads it; the next
 *     page's script makes the move. The call itself lives in the extension
 *     (`holder.ts`) and is untouched by the load.
 *   - The window scrolls, under a fixed 70px header.
 *   - A project page is a stack of "l3" sections, picked out by class (their
 *     ids carry a random suffix per load): the gallery, the typologies with
 *     their price and floor plan, the amenities, the tour, the build status,
 *     the brochure, the contact block. The quote form is a HubSpot form in a
 *     cross-origin frame inside the typology section, driven by `hsform.ts`
 *     inside it.
 *   - /proyectos/ is a Vue list with region and type selects, commune
 *     checkboxes and pages of eight cards.
 *
 * Every anchor below is one of their visible texts, their component classes,
 * or the HubSpot form's own field names.
 */

import { openTab, setPendingMove } from "./hub";

declare global {
  interface Window {
    voqalizeSsilva?: Adapter;
  }
}

export interface Adapter {
  /** Perform one of the brain's page Actions. Never throws. */
  run(command: string, payload: unknown): Promise<{ ok: boolean; error?: string }>;
  /** What the visitor is looking at now, as a `page_changed` payload. */
  context(): PageContext;
  /** Whether a move to `path` loads another page (and so ends this one). */
  leaves(path: string): boolean;
  /** What on the page the widget must not cover now: the quote form. */
  obstacles(): { left: number; top: number; right: number; bottom: number }[];
  /** Report the page's changes through `emit`, until the returned stop. The
   *  page as it stands is reported first. */
  start(emit: (event: string, payload: unknown) => void): () => void;
  /** The Actions `run` performs. */
  readonly commands: readonly string[];
}

export interface PageContext {
  url: string;
  path: string;
  title: string;
  kind: "home" | "projects" | "project" | "quote" | "page";
  project: string;
  headings: string[];
  sections: string[];
  typologies: string[];
  typology: string;
  /** The hero's price, the project's "desde", as the page shows it. */
  price: string;
  /** The selected typology's price, beside its plan. */
  typology_price: string;
  status: string;
  /** On a project page, what its gallery's photos and its amenities' photos
   *  show, in order, as their files name them. */
  photos: string[];
  amenity_photos: string[];
}

/** Ssilva's coral, off their "NUESTROS PROYECTOS" button. */
const RING = "#F07769";
const RING_RGB = "240, 119, 105";
const RING_MS = 5500;
const WAIT_MS = 8000;
const MAX_HEADINGS = 60;
const HEADER_FALLBACK = 70;
const GAP = 16;

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const clean = (s: string | null | undefined) => (s ?? "").replace(/\s+/g, " ").trim();
/** For matching what the brain said against what the page shows: case,
 *  accents and trailing punctuation aside. */
const norm = (s: string | null | undefined) =>
  clean(s)
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[‘’]/g, "'")
    .replace(/[“”]/g, '"')
    .replace(/[‐-―]/g, "-")
    .replace(/^[¿¡\s]+/, "")
    .replace(/[.:?!\s]+$/, "")
    .trim();
/** Chrome's own page translation rewrites what the visitor reads, and what
 *  this script reads too: "DISTRITO BARROSO" becomes "BARROSO DISTRICT",
 *  "Desde 2.582 UF" becomes "From 2,582 UF" and "2D | 2B MARIPOSA" becomes
 *  "2D | 2B BUTTERFLY" (dev call ec152777, where every cue that named page
 *  words missed). The brain writes Ssilva's Spanish; these put the usual
 *  English back into it before comparing. Projects are matched by their
 *  links, which no translation touches. */
const SPANISH: [RegExp, string][] = [
  [/\bbutterfly\b/g, "mariposa"],
  [/\b(?:studio|study)\b/g, "estudio"],
  [/\boffices?\b/g, "oficina"],
  [/\bliving(?: room)?\b/g, "estar"],
  [/\bfrom\b/g, "desde"],
];
const spanish = (s: string) => SPANISH.reduce((t, [re, w]) => t.replace(re, w), s);
/** For matching words and prices across a translation: "Desde 2.582 UF" is
 *  "From 2,582 UF". */
const loose = (s: string | null | undefined) => spanish(norm(s)).replace(/(\d)[.,](?=\d{3}\b)/g, "$1");
/** A typology label, spelled any way: "2D | 2B", "2d|2b", "2D-2B". */
const typ = (s: string | null | undefined) =>
  spanish(norm(s))
    .replace(/\s*[|/–-]\s*/g, "|")
    .replace(/\s+/g, " ");
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

const strip = (p: string) => (p || "/").replace(/\/+$/, "") || "/";
const samePath = (a: string, b: string) => strip(a).toLowerCase() === strip(b).toLowerCase();
const isSsilva = (host: string) => /^(www\.)?ssilva\.cl$/i.test(host);

function main(): HTMLElement {
  return document.querySelector<HTMLElement>(".site__content") ?? document.querySelector("main") ?? document.body;
}

/** The page's own sections, top level, in order. */
function sections(): HTMLElement[] {
  return [...main().querySelectorAll<HTMLElement>("section")].filter(
    (s) => !s.parentElement?.closest("section") && !s.closest("[data-voqalize], .modal"),
  );
}

// ─── Scrolling ────────────────────────────────────────────────────────────

/** The height of what is fixed to the top of the viewport: the 70px header. */
function headerHeight(): number {
  let h = 0;
  for (const el of document.querySelectorAll<HTMLElement>("header, .header, [class*='header--']")) {
    if (el.closest("[data-voqalize]")) continue;
    const r = el.getBoundingClientRect();
    if (getComputedStyle(el).position === "fixed" && r.top <= 1 && r.height > 0 && r.height < 200 && r.width > 300) {
      h = Math.max(h, r.bottom);
    }
  }
  return h || HEADER_FALLBACK;
}

/** Scroll the window so `el` sits under the header (`top`) or in the middle
 *  of what is left of the screen, and check it did: lazy images and the
 *  reveal animations move things as the page scrolls. */
async function scrollTo(el: Element, align: "top" | "center" = "top"): Promise<void> {
  for (let pass = 0; pass < 3; pass++) {
    const r = el.getBoundingClientRect();
    const head = headerHeight();
    const room = window.innerHeight - head;
    const want = align === "center" && r.height < room ? head + (room - r.height) / 2 : head + GAP;
    const delta = r.top - want;
    if (Math.abs(delta) < 8) return;
    const top = Math.max(0, Math.min(r.top + window.scrollY - want, document.documentElement.scrollHeight));
    const before = window.scrollY;
    window.scrollTo({ top, behavior: "smooth" });
    await waitFor(() => Math.abs(window.scrollY - top) < 2, 1400);
    await sleep(150);
    if (Math.abs(window.scrollY - before) < 2 && pass > 0) return; // at the end of the page
  }
}

async function scrollToTopOfPage(): Promise<void> {
  window.scrollTo({ top: 0, behavior: "smooth" });
  await waitFor(() => window.scrollY < 2, 1400);
}

// ─── The ring ─────────────────────────────────────────────────────────────
// Drawn over the page, never on Ssilva's own elements, and moved with its
// target every frame.

let rings: { el: HTMLElement; targets: Element[]; find?: () => Element[] }[] = [];
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
    // The site re-rendered what was ringed (the project list does): ring the
    // new copy.
    if (ring.find && !ring.targets.some((t) => t.isConnected)) ring.targets = ring.find();
    const b = boxOf(ring.targets);
    if (!b) {
      ring.el.style.opacity = "0";
      continue;
    }
    if (ring.el.dataset.shown) ring.el.style.opacity = "1";
    // Never under the fixed header, nor off the screen's edges.
    const top = Math.max(b.top - 6, headerHeight() + 2);
    const left = Math.max(b.left - 6, 2);
    const right = Math.min(b.right + 6, window.innerWidth - 2);
    Object.assign(ring.el.style, {
      transform: `translate(${left}px, ${top}px)`,
      width: `${Math.max(right - left, 0)}px`,
      height: `${Math.max(b.bottom + 6 - top, 0)}px`,
    });
  }
  ringFrame = requestAnimationFrame(follow);
}

/** Ring each group: one element, several ringed as one box, or a way to
 *  find them again. */
function highlight(...groups: (Element | Element[] | (() => Element[]))[]): void {
  clearHighlight();
  for (const group of groups) {
    const find = typeof group === "function" ? group : undefined;
    const targets = find ? find() : Array.isArray(group) ? group : [group as Element];
    if (!boxOf(targets)) continue;
    const el = document.createElement("div");
    el.setAttribute("data-voqalize", "highlight");
    Object.assign(el.style, {
      position: "fixed",
      left: "0",
      top: "0",
      border: `3px solid ${RING}`,
      borderRadius: "10px",
      pointerEvents: "none",
      zIndex: "2147483000",
      opacity: "0",
      transition: "opacity 300ms ease",
      animation: "voqalize-ring 1.4s ease-in-out 3",
    });
    document.body.appendChild(el);
    rings.push({ el, targets, find });
  }
  follow();
  requestAnimationFrame(() =>
    rings.forEach((r) => {
      r.el.dataset.shown = "1";
      r.el.style.opacity = "1";
    }),
  );
  ringTimer = setTimeout(clearHighlight, RING_MS);
}

function clearHighlight(): void {
  if (ringTimer) clearTimeout(ringTimer);
  cancelAnimationFrame(ringFrame);
  rings.forEach((r) => r.el.remove());
  rings = [];
}

function styleThePage(): void {
  if (document.querySelector("style[data-voqalize=ssilva]")) return;
  const style = document.createElement("style");
  style.setAttribute("data-voqalize", "ssilva");
  // Javier takes the bottom-right corner, where a project page's floating
  // WhatsApp button sits; the button moves to the bottom-left while the
  // extension runs.
  style.textContent = `
    a.floating-quote-btn { right: auto !important; left: 24px !important; }
    @keyframes voqalize-ring {
      0%, 100% { box-shadow: 0 0 0 0 rgba(${RING_RGB}, 0.5); }
      50% { box-shadow: 0 0 0 10px rgba(${RING_RGB}, 0); }
    }
  `;
  document.head.appendChild(style);
}

// ─── What the page shows ──────────────────────────────────────────────────

function kind(): PageContext["kind"] {
  const p = location.pathname.toLowerCase();
  if (strip(p) === "/") return "home";
  if (p.startsWith("/proyectos/cotizar/")) return "quote";
  if (samePath(p, "/proyectos/") || samePath(p, "/oportunidades/")) return "projects";
  if (document.body.classList.contains("page-template-landing") || document.querySelector("section.l3-hero")) {
    return "project";
  }
  return "page";
}

/** The project's name, from the page title ("DISTRITO BARROSO | SSilva"),
 *  on its page and on its quote page alike. */
function projectName(): string {
  const k = kind();
  if (k !== "project" && k !== "quote") return "";
  return clean(document.title.split("|")[0]).replace(/^cotizar\s+/i, "");
}

const HEADING_SEL = "h1, h2, h3, .section-title, .projects-list__filters__title, .wide-image-scroller__title";

/** A heading as it reads; the site writes some of them across lines. */
const headText = (h: Element) => clean((h as HTMLElement).innerText || h.textContent);

/** The headings the visitor can be taken to, in page order: on a project page
 *  each section's own title, elsewhere every heading on the page. */
function headings(): HTMLElement[] {
  const ok = (h: HTMLElement) =>
    visible(h) && headText(h).length > 1 && !h.closest("header, footer, .modal, [data-voqalize], .header, .footer");
  if (kind() === "project") {
    const out: HTMLElement[] = [];
    for (const s of sections()) {
      const h = [...s.querySelectorAll<HTMLElement>("h1, h2, h3")].find(ok);
      if (h) out.push(h);
    }
    return out;
  }
  return [...main().querySelectorAll<HTMLElement>(HEADING_SEL)].filter(ok);
}

/** A project page's sections by the words a visitor uses for them. */
const SECTION_KEYS: { key: string; sel: string; words: string[] }[] = [
  { key: "galería", sel: ".l3-numbered-slider-section", words: ["galeria", "gallery", "fotos", "photos", "imagenes", "images"] },
  {
    key: "tipologías",
    sel: ".cotizador-l1-section",
    words: ["tipologias", "tipologia", "typologies", "typology", "plantas", "planos", "floor plans", "precios", "prices", "cotizador"],
  },
  { key: "amenidades", sel: ".alternate-images-section", words: ["amenidades", "amenities", "equipamiento", "areas comunes", "espacios comunes"] },
  { key: "tour", sel: ".video-tour-section", words: ["tour", "tour virtual", "virtual tour", "recorrido", "video"] },
  { key: "estado", sel: ".l3-project-status-section", words: ["estado", "status", "avance", "estado del proyecto", "estado de obra"] },
  { key: "brochure", sel: ".wbct-section, .l3-other-docs-section", words: ["brochure", "folleto"] },
  { key: "contacto", sel: ".project-actions-section", words: ["contacto", "contact", "ubicacion", "location", "mapa", "map", "direccion", "address", "horario", "hours"] },
  {
    key: "formulario",
    sel: ".cotizador-l1-section .hs-form-frame",
    words: ["formulario", "form", "cotizar", "cotiza", "cotizacion", "quote", "lead form", "formulario de contacto"],
  },
];

function sectionKeysHere(): string[] {
  if (kind() !== "project") return [];
  const found: { key: string; y: number }[] = [];
  for (const s of SECTION_KEYS) {
    const el = document.querySelector(s.sel);
    if (el) found.push({ key: s.key, y: el.getBoundingClientRect().top + window.scrollY });
  }
  return found.sort((a, b) => a.y - b.y).map((f) => f.key);
}

/** A section key the visitor's words name: "galería", "photos", "form". */
function sectionKey(said: string): (typeof SECTION_KEYS)[number] | null {
  const want = norm(said);
  return SECTION_KEYS.find((s) => norm(s.key) === want || s.words.includes(want)) ?? null;
}

/** The element a section key stands for on this page, if it has one. */
function sectionFor(said: string): HTMLElement | null {
  if (kind() !== "project") return null;
  const entry = sectionKey(said);
  if (!entry) return null;
  if (entry.key === "formulario") {
    const box = formBox();
    return box && !shown(box) ? (box.closest<HTMLElement>(".unit-info") ?? box) : box;
  }
  if (entry.key === "brochure") {
    return document.querySelector<HTMLElement>(".wbct-section") ?? document.querySelector(".l3-other-docs-section");
  }
  return document.querySelector<HTMLElement>(entry.sel);
}

const typologyItems = () => [...document.querySelectorAll<HTMLLIElement>(".cotizador-l1 li.type-item")];
const typologyLabel = (li: Element) => clean(li.querySelector("label")?.textContent ?? li.textContent);

/** The typology section's price: "Desde 2.582 UF". */
function cotizadorPrice(): string {
  const v = clean(document.querySelector("[id^=priceValue_cotizador]")?.textContent);
  return v ? `Desde ${v} UF` : "";
}

/** The hero's "DESDE 2.582 UF", or "FROM 2,582 UF" through Chrome's
 *  translation (dev call ce7b01c3): the project's desde, which is not the
 *  selected typology's price beside the plan. */
function heroPrice(): string {
  const text = clean(document.querySelector(".l3-hero")?.textContent);
  const m = text.match(/(?:desde|from)\s+([\d.,]+)\s*UF/i);
  return m ? `Desde ${m[1]} UF` : "";
}

/** What the widget must not cover: the quote form, while it is on screen. */
function obstacles(): { left: number; top: number; right: number; bottom: number }[] {
  const frame = formFrame();
  if (!frame || !visible(frame)) return [];
  const r = frame.getBoundingClientRect();
  if (r.bottom < 0 || r.top > window.innerHeight) return [];
  return [{ left: r.left, top: r.top, right: r.right, bottom: r.bottom }];
}

function context(): PageContext {
  const k = kind();
  const seen = new Set<string>();
  const hs: string[] = [];
  for (const h of headings()) {
    const t = headText(h);
    if (seen.has(norm(t))) continue;
    seen.add(norm(t));
    hs.push(t);
    if (hs.length >= MAX_HEADINGS) break;
  }
  const items = typologyItems();
  return {
    url: location.href,
    path: location.pathname,
    title: document.title,
    kind: k,
    project: projectName(),
    headings: hs,
    sections: sectionKeysHere(),
    typologies: items.map(typologyLabel),
    typology: items.length ? typologyLabel(items.find((li) => li.classList.contains("active")) ?? items[0]) : "",
    price: k === "project" ? heroPrice() : "",
    typology_price: k === "project" ? cotizadorPrice() : "",
    status: clean(document.querySelector(".l3-project-status-section .status-item.active .title")?.textContent),
    photos: k === "project" ? galleryShots().map((s) => s.caption) : [],
    amenity_photos: k === "project" ? amenityShots().map((s) => s.caption) : [],
  };
}

// ─── navigate ─────────────────────────────────────────────────────────────

function target(path: string): URL {
  if (typeof path !== "string" || !path.trim()) throw new Error(`not a path: ${path}`);
  const url = new URL(path.trim(), location.origin);
  if (!isSsilva(url.host)) throw new Error(`${url.href} is not on ssilva.cl`);
  // One host for the whole visit, so the call's tab and its storage stay put.
  url.host = location.host;
  return url;
}

/** Whether a move to `path` loads another page. */
function leaves(path: string): boolean {
  try {
    const url = target(path);
    return !samePath(url.pathname, location.pathname);
  } catch {
    return false;
  }
}

/** Load another page, first leaving the move to make there with the extension. */
async function load(url: URL, then?: { command: string; payload: unknown }): Promise<void> {
  if (then && !(await setPendingMove(then))) {
    // No extension to keep it (reloaded under the page): the page still moves;
    // the section on it is lost, and said so.
    location.assign(url.href);
    throw new Error(`opened ${url.pathname}, but could not keep the move to make on it`);
  }
  location.assign(url.href);
}

interface NavigateOrder {
  path: string;
  heading?: string | null;
  text?: string | null;
  typology?: string | null;
}

async function navigate(order: NavigateOrder): Promise<void> {
  const url = target(order.path);
  if (samePath(url.pathname, location.pathname)) {
    if (order.typology) return selectTypology({ label: order.typology });
    if (order.heading || order.text) return showSection({ heading: order.heading, text: order.text });
    await scrollToTopOfPage();
    return;
  }
  const wants = order.heading || order.text || order.typology;
  await load(url, wants ? { command: "navigate", payload: { ...order, path: url.pathname + url.search } } : undefined);
}

// ─── show_section ─────────────────────────────────────────────────────────

function findHeading(heading: string): HTMLElement | null {
  const want = norm(heading);
  if (!want) return null;
  const all = headings();
  const t = (h: HTMLElement) => norm(headText(h));
  return (
    all.find((h) => t(h) === want) ??
    all.find((h) => t(h).startsWith(want)) ??
    all.find((h) => want.startsWith(t(h)) && t(h).length > 3) ??
    all.find((h) => t(h).includes(want)) ??
    null
  );
}

/** The block a heading heads: its top-level section, or the nearest ancestor
 *  that holds more than the heading itself. */
function sectionOf(h: HTMLElement): HTMLElement {
  const top = sections().find((s) => s.contains(h));
  if (top) return top;
  const s = h.closest<HTMLElement>("section");
  if (s && s !== main()) return s;
  let el = h.parentElement;
  while (el && el !== main() && clean(el.textContent).length <= clean(h.textContent).length + 20) {
    el = el.parentElement;
  }
  return el ?? h;
}

/** The smallest visible element in `root` whose text contains `text`; a
 *  project's name on /proyectos/ is its whole card. */
function smallestContaining(root: Element, text: string): HTMLElement | null {
  const want = loose(text);
  if (!want) return null;
  const find = (w: string) => {
    let best: HTMLElement | null = null;
    let bestLen = Infinity;
    for (const el of root.querySelectorAll<HTMLElement>("*")) {
      if (el.closest("[data-voqalize], script, style, .modal") || !visible(el)) continue;
      const t = loose(el.textContent);
      if (!t.includes(w) || t.length >= bestLen) continue;
      best = el;
      bestLen = t.length;
    }
    return best;
  };
  // "Desde 2.582 UF" where the page writes the price on a line of its own.
  const rest = want.replace(/^desde\s+/, "");
  const best = find(want) ?? (rest !== want && /\d/.test(rest) ? find(rest) : null);
  if (!best) return null;
  const card = best.closest<HTMLElement>(".project-card-wrapper, li.type-item, .status-item");
  return card && root.contains(card) ? card : best;
}

/** Ring a section: all of it when it fits the screen, else its top. */
function ringSection(section: HTMLElement, h?: HTMLElement | null): void {
  const r = section.getBoundingClientRect();
  highlight(r.height > window.innerHeight * 2 && h ? h : section);
}

async function showSection({ heading, text }: { heading?: string | null; text?: string | null }): Promise<void> {
  // Moving on to another part of the page closes what is full screen; the
  // photos' own sections leave it open.
  const photosPart = heading ? ["galería", "amenidades"].includes(sectionKey(heading)?.key ?? "") : false;
  if (!photosPart) closeViewer();
  if (heading && sectionKey(heading)?.key !== "brochure") closeDoc();
  const keyed = heading ? sectionFor(heading) : null;
  const h = keyed ? null : heading ? findHeading(heading) : null;
  const block = keyed ?? (h ? sectionOf(h) : null);
  if (heading && !block && !text) {
    const k = sectionKeysHere();
    const key = sectionKey(heading);
    if (key && kind() === "project") {
      throw new Error(`this project's page has no ${key.key} section; it has: ${k.join(", ")}`);
    }
    const known = context().headings.slice(0, 20).join(" | ");
    throw new Error(
      `no heading "${heading}" on ${location.pathname}; it has: ${known}${k.length ? `; sections: ${k.join(", ")}` : ""}`,
    );
  }
  if (text) {
    const el = (block && smallestContaining(block, text)) ?? smallestContaining(main(), text);
    if (!el) throw new Error(`"${text}" is not on ${location.pathname}`);
    const tall = el.getBoundingClientRect().height > window.innerHeight * 0.7;
    await scrollTo(el, tall ? "top" : "center");
    highlight(el);
    return;
  }
  if (!block) throw new Error("say which heading or text to show");
  if (keyed?.matches(".hs-form-frame, .unit-info")) {
    // The form sits low in the typology section: in the middle of the screen.
    await scrollTo(keyed, "center");
    highlight(keyed);
    return;
  }
  await scrollTo(block, "top");
  ringSection(block, h ?? block.querySelector<HTMLElement>("h1, h2, h3"));
}

// ─── select_typology ──────────────────────────────────────────────────────

function findTypology(label: string): HTMLLIElement | null {
  const want = typ(label);
  const all = typologyItems();
  const t = (li: HTMLLIElement) => typ(typologyLabel(li));
  // The longest label inside what was asked: "2D | 2B MARIPOSA" is not "2D | 2B".
  const longest = (lis: HTMLLIElement[]) => lis.sort((a, b) => t(b).length - t(a).length)[0];
  return (
    all.find((li) => t(li) === want) ??
    all.find((li) => t(li).replace(/ /g, "") === want.replace(/ /g, "")) ??
    all.find((li) => t(li).startsWith(want)) ??
    all.find((li) => t(li).includes(want)) ??
    longest(all.filter((li) => want.includes(t(li)))) ??
    null
  );
}

const fact = (id: string) => clean(document.querySelector(`[id^=${id}_cotizador]`)?.textContent);
const spinning = () => !!document.querySelector(".cotizador-spinner-overlay.active");

async function selectTypology({ label }: { label: string }, opts: { forPlan?: boolean } = {}): Promise<void> {
  if (kind() === "quote") return quoteTypology(label);
  // Over a plan he is showing full screen, the plan follows the typology he
  // moves to; photos full screen give way to it.
  const planOpen = viewer?.which === "plan" && !opts.forPlan;
  if (!planOpen && !opts.forPlan) closeViewer();
  const items = typologyItems();
  if (!items.length) throw new Error(`there are no typologies on ${location.pathname}`);
  const li = findTypology(label);
  if (!li) throw new Error(`no typology "${label}" here; it has: ${items.map(typologyLabel).join(" | ")}`);
  const section = li.closest<HTMLElement>(".cotizador-l1-section") ?? sectionOf(li);
  await scrollTo(section, "top");
  if (!li.classList.contains("active")) {
    const before = fact("priceValue");
    li.querySelector("label")?.click();
    await waitFor(spinning, 600);
    await waitFor(() => !spinning() && li.classList.contains("active"), 5000);
    await waitFor(() => fact("priceValue") !== before, 600);
    await sleep(150);
  }
  const value = document.querySelector<HTMLElement>("[id^=priceValue_cotizador]");
  const price = value?.closest<HTMLElement>(".price") ?? value;
  const plan = document.querySelector<HTMLElement>("[id^=floorPlanContainer_cotizador], [id^=floorPlanImage_cotizador]");
  highlight([li, ...(price ? [price] : []), ...(plan ? [plan] : [])]);
  if (planOpen) await showFloorPlan({ typology: null });
  const area = (v: string) => (v ? `${v} m²` : "");
  emit("typology_shown", {
    label: typologyLabel(li),
    price: cotizadorPrice(),
    total_area: area(fact("totalAreaValue")),
    useful_area: area(fact("usefulAreaValue")),
    bedrooms: fact("bedroomsValue"),
    bathrooms: fact("bathroomsValue"),
    orientation: fact("orientationValue"),
  });
}

/** On /proyectos/cotizar/: the typology tabs of step 1. */
async function quoteTypology(label: string): Promise<void> {
  const tabs = [...document.querySelectorAll<HTMLAnchorElement>("ul[id$=tabs] a.nav-link")].filter(visible);
  if (!tabs.length) throw new Error("this quote page has no typologies to choose from");
  const want = typ(label);
  const t = (a: HTMLAnchorElement) => typ(a.textContent);
  const tab =
    tabs.find((a) => t(a) === want) ??
    tabs.find((a) => t(a).replace(/ /g, "") === want.replace(/ /g, "")) ??
    tabs.find((a) => t(a).includes(want)) ??
    null;
  if (!tab) throw new Error(`no typology "${label}" here; it has: ${tabs.map((a) => clean(a.textContent)).join(" | ")}`);
  await scrollTo(tab, "top");
  tab.click();
  const pane = document.querySelector<HTMLElement>(tab.getAttribute("href") || "#none");
  await waitFor(() => visible(pane), 2000);
  highlight(pane ?? tab);
  const price = clean(pane?.textContent).match(/([\d.,]+)\s*UF/i);
  emit("typology_shown", { label: clean(tab.textContent), price: price ? `${price[1]} UF` : "" });
}

// ─── show_projects ────────────────────────────────────────────────────────

const REGIONS: Record<string, string> = { metropolitana: "17", rm: "17", santiago: "17", valparaiso: "557", "v region": "557", otros: "556" };
const PROPERTIES: Record<string, string> = {
  departamento: "34",
  departamentos: "34",
  depto: "34",
  casa: "193",
  casas: "193",
  oficina: "35",
  oficinas: "35",
  local: "36",
  "local comercial": "36",
  locales: "36",
};

function idFor(table: Record<string, string>, said: string | null | undefined, what: string): string {
  if (!said) return "";
  const want = norm(said).replace(/^region (de )?/, "");
  const id = table[want] ?? Object.entries(table).find(([k]) => want.includes(k))?.[1];
  if (!id) throw new Error(`no ${what} "${said}"; say one of: ${Object.keys(table).join(", ")}`);
  return id;
}

const select = (id: string) => document.querySelector<HTMLSelectElement>(`select#${id}`);
const loading = () => [...document.querySelectorAll(".loading-cloak.active")].some(visible);
const resultsMsg = () => clean(document.querySelector(".projects-list__results-msg")?.textContent);
const cards = () => [...document.querySelectorAll<HTMLElement>(".project-card-wrapper")].filter(visible);

/** What the site rendered a card from: the list's AJAX record, held by the
 *  card's Vue component (this script runs in the page's world). Spanish,
 *  untouched by any translation. */
interface CardData {
  condo_name?: string;
  cost?: string;
  commune?: string;
  region?: string;
  category?: string;
  bedrooms?: string;
  bathrooms?: string;
  square_area?: string;
  name?: string;
  condo_phrase?: string;
  project_btn?: { url?: string };
}
type WithVue = { __vue__?: { $props?: { data?: CardData }; $parent?: { $data?: { totalResults?: number } } } };
const cardData = (c: Element): CardData | null => (c as unknown as WithVue).__vue__?.$props?.data ?? null;
/** The list's own count of results, from its Vue data. */
const listTotal = (): number | null => {
  const c = document.querySelector(".project-card-wrapper");
  const n = c ? (c as unknown as WithVue).__vue__?.$parent?.$data?.totalResults : undefined;
  return typeof n === "number" ? n : null;
};
const cardName = (c: Element) =>
  clean(cardData(c)?.condo_name) ||
  clean([...c.querySelectorAll(".project-card__opp-condo-name")].map((e) => clean(e.textContent)).find(Boolean));
const pathOf = (href: string) => {
  try {
    return new URL(href, location.href).pathname;
  } catch {
    return "";
  }
};
/** The project page a card links to: the one thing on it no translation
 *  rewrites. */
const cardPaths = (c: Element) => {
  const own = cardData(c)?.project_btn?.url;
  const links = [...c.querySelectorAll<HTMLAnchorElement>("a[href]")].map((a) => pathOf(a.href));
  return own ? [pathOf(own), ...links] : links;
};

// ─── The list through Chrome's translation ────────────────────────────────
// Chrome's page translation swaps each text node for its translation. The
// list is Vue, and when it re-renders (every filter, every page, and twice
// as /proyectos/ loads with the order shuffled) it reuses each card and
// writes the new project into the text nodes it made, which translation has
// taken off the page: the links and pictures change, the words do not. On
// dev calls 334b108c and ce7b01c3 the card linking /edificiocarrera/ still
// read "EL RODEO ARRAYAN PARK", "From 9,786 UF" while Javier said "Edificio
// Carrera, one thousand seven hundred fifty-three UF". So on a translated
// page, each card's words are written again from its own data, which
// translation then translates again.

const translated = () =>
  /\btranslated-(?:ltr|rtl)\b/.test(document.documentElement.className) ||
  !!document.querySelector(".project-card-wrapper font");

/** What each card's words were last written from. */
const written = new WeakMap<Element, string>();

/** `el`'s words, written as `text`, its icons kept. */
function writeText(el: Element | null, text: string | undefined): void {
  if (!el || text === undefined) return;
  for (const n of [...el.childNodes]) {
    if (n instanceof Element && n.matches("i.material-icons, img")) continue;
    if (n.nodeType === Node.COMMENT_NODE) continue;
    n.remove();
  }
  el.append(document.createTextNode(` ${clean(text)} `));
}

function rewriteCard(c: Element, d: CardData): void {
  for (const el of c.querySelectorAll(".project-card__opp-condo-name")) writeText(el, d.condo_name);
  for (const el of c.querySelectorAll(".project-card__opp-condo-phrase")) writeText(el, d.condo_phrase ?? "");
  for (const el of c.querySelectorAll(".project-card__opp-name")) writeText(el, d.name ?? "");
  writeText(c.querySelector(".project-card__category"), d.category);
  writeText(c.querySelector(".project-card__bottom__heading__commune"), d.commune);
  writeText(c.querySelector(".project-card__bottom__heading__region"), d.region);
  writeText(c.querySelector(".project-card__bottom__heading__price"), d.cost);
  const props = c.querySelectorAll(".project-card__bottom__body__property");
  [d.bedrooms, d.bathrooms, d.square_area].forEach((t, i) => writeText(props[i] ?? null, t));
}

/** On a translated page, every card whose words may be another project's is
 *  written again from its data; and the count of results the same way. */
function repairList(): void {
  if (!translated()) return;
  for (const c of document.querySelectorAll(".project-card-wrapper")) {
    const d = cardData(c);
    if (!d) continue;
    const key = `${d.project_btn?.url ?? ""}|${d.condo_name ?? ""}|${d.cost ?? ""}`;
    if (written.get(c) === key) continue;
    written.set(c, key);
    rewriteCard(c, d);
  }
  const total = listTotal();
  const msg = document.querySelector(".projects-list__results-msg");
  const shownCount = clean(msg?.textContent).match(/\d+/)?.[0];
  if (msg && total !== null && shownCount !== String(total)) {
    // The words' own element, not the translation's <font> inside it, which
    // translation does not translate again.
    let at = [...msg.querySelectorAll("*")].find((e) => /\d/.test(e.textContent ?? "") && !e.children.length) ?? msg;
    while (at !== msg && at.tagName === "FONT" && at.parentElement) at = at.parentElement;
    writeText(at, `${total} proyectos encontrados para tu búsqueda.`);
  }
}

function watchTranslatedList(): void {
  let queued = false;
  new MutationObserver(() => {
    if (queued || !document.querySelector(".project-card-wrapper")) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      repairList();
    });
  }).observe(document.documentElement, {
    subtree: true,
    childList: true,
    characterData: true,
    attributes: true,
    attributeFilter: ["href", "src", "class"],
  });
}

/** The cards on screen of the projects at `paths`, or named `names`. */
function cardsFor(paths: string[], names: string[]): HTMLElement[] {
  const ps = paths.filter(Boolean);
  const ns = names.map(norm).filter(Boolean);
  return cards().filter((c) => {
    if (ps.length && cardPaths(c).some((h) => ps.some((p) => samePath(h, p)))) return true;
    const n = norm(cardName(c));
    return !!n && ns.some((w) => n === w || n.includes(w) || w.includes(n));
  });
}

/** What the list shows, to tell that it changed. */
const listKey = () => `${location.search}|${resultsMsg()}|${cards().map(cardName).join(",")}`;

/** Wait out the list's reload after a filter or a page: its cloak shows, or
 *  what it shows changes, then the cloak goes. */
async function listSettled(before?: string): Promise<void> {
  await waitFor(() => loading() || (before !== undefined && listKey() !== before), before === undefined ? 900 : 3000);
  await waitFor(() => !loading(), WAIT_MS);
  await sleep(300);
}

/** Click a filter or a page of the list, and wait for the list it gives. */
async function clickList(el: HTMLElement): Promise<void> {
  const before = listKey();
  el.click();
  await listSettled(before);
}

function selectedText(sel: HTMLSelectElement | null): string {
  if (!sel || !sel.value) return "";
  return clean(sel.selectedOptions[0]?.text);
}

function communeBoxes(): { input: HTMLInputElement; label: string }[] {
  return [...document.querySelectorAll<HTMLInputElement>("input[id^=commune]")].map((input) => ({
    input,
    label: clean(document.querySelector(`label[for="${input.id}"]`)?.textContent),
  }));
}

function listed() {
  repairList();
  const shown = cards().filter((c) => cardName(c));
  return {
    // The list's own count; else "29 proyectos encontrados…", or "29 projects
    // found…" through a translation.
    count: listTotal() ?? Number(resultsMsg().match(/(\d+)\s+(?:proyectos?|projects?)/i)?.[1] ?? cards().length),
    region: selectedText(select("region")),
    property: selectedText(select("property")),
    communes: communeBoxes()
      .filter((c) => c.input.checked)
      .map((c) => c.label),
    // The site's own names, from the cards' data: no translation reaches them.
    projects: shown.map(cardName),
    paths: shown.map((c) => cardPaths(c)[0] ?? ""),
    // What each card shows, from what the site rendered it from.
    cards: shown.map((c) => {
      const d = cardData(c);
      const text = (sel: string) => clean(c.querySelector(sel)?.textContent);
      return {
        path: cardPaths(c)[0] ?? "",
        name: cardName(c),
        price: clean(d?.cost) || text(".project-card__bottom__heading__price"),
        commune: clean(d?.commune) || text(".project-card__bottom__heading__commune"),
        bedrooms: clean(d?.bedrooms),
        status: clean(d?.category) || text(".project-card__category"),
      };
    }),
  };
}

/** The list's own select, set the way a visitor's choice sets it. */
async function choose(sel: HTMLSelectElement, value: string, what: string): Promise<void> {
  if (sel.value === value) return;
  if (![...sel.options].some((o) => o.value === value)) {
    throw new Error(`the list here has no such ${what} to choose`);
  }
  const before = listKey();
  sel.value = value;
  sel.dispatchEvent(new Event("change", { bubbles: true }));
  await listSettled(before);
}

const pageLinks = () =>
  [...document.querySelectorAll<HTMLAnchorElement>("ul.custom-pagination li a.class-icon-scroll-page")].filter((a) =>
    /^\d+$/.test(clean(a.textContent)),
  );
const currentPage = () => clean(document.querySelector("ul.custom-pagination li.active a")?.textContent) || "1";

/** The cards `match` finds: on this page of the list, else on the others, in
 *  order, until one has them. With none anywhere, the list goes back to the
 *  page it was on. */
async function findOnPages(match: () => HTMLElement[]): Promise<HTMLElement[]> {
  let found = match();
  if (found.length) return found;
  const start = currentPage();
  for (const n of pageLinks().map((a) => clean(a.textContent))) {
    if (n === currentPage()) continue;
    const link = pageLinks().find((a) => clean(a.textContent) === n);
    if (!link) continue;
    await clickList(link);
    found = match();
    if (found.length) return found;
  }
  if (currentPage() !== start) {
    const back = pageLinks().find((a) => clean(a.textContent) === start);
    if (back) await clickList(back);
  }
  return [];
}

/** /proyectos/ itself, not /oportunidades/: the same list component with
 *  other filters, which also writes /proyectos/ into the address (dev call
 *  87691fcb filtered that one and showed nothing). */
const theProjectList = () => !!document.querySelector('select#region option[value="17"]');

/** One move on the list at a time: a card he names while the list is still
 *  being filtered waits for the filter. */
let listQueue: Promise<unknown> = Promise.resolve();
function onTheList<T>(fn: () => Promise<T>): Promise<T> {
  const run = listQueue.then(fn, fn);
  listQueue = run.catch(() => {});
  return run;
}
/** When a card was last rung as he named it: the list's own ring of several
 *  stays off it for a while. */
let cardRungAt = 0;
const CARD_HOLDS_MS = 8000;

let listing = false;
let lastListed = "";

/** Report the list as it stands, once per change. */
function report(force = true): void {
  const now = listed();
  const key = JSON.stringify(now);
  if (!force && key === lastListed) return;
  lastListed = key;
  emit("projects_listed", now);
}

interface ProjectsOrder {
  region?: string | null;
  property?: string | null;
  communes?: string[] | null;
  highlight?: string[] | null;
  paths?: string[] | null;
}

async function showProjects(order: ProjectsOrder): Promise<void> {
  const communes = (order.communes ?? []).filter(Boolean);
  // Communes are only offered under Región Metropolitana.
  const region = idFor(REGIONS, order.region || (communes.length ? "metropolitana" : null), "region");
  const property = idFor(PROPERTIES, order.property, "property type");
  const url = new URL("/proyectos/", location.origin);
  if (region) url.searchParams.set("region", region);
  if (property) url.searchParams.set("property", property);
  if (!samePath(location.pathname, "/proyectos/")) {
    await load(url, { command: "show_projects", payload: order });
    return;
  }
  return onTheList(async () => {
    const regionSel = await waitFor(() => select("region"), WAIT_MS);
    if (!regionSel) throw new Error("the project list did not load");
    // The opportunities list under /proyectos/'s address: the real list loads.
    await waitFor(() => regionSel.options.length > 1, 3000);
    if (!theProjectList() && /oportunidad|opportunit/i.test(document.title)) {
      return load(url, { command: "show_projects", payload: order });
    }
    return filterAndRing(regionSel, order, communes, region, property);
  });
}

async function filterAndRing(
  regionSel: HTMLSelectElement,
  order: ProjectsOrder,
  communes: string[],
  region: string,
  property: string,
): Promise<void> {
  listing = true;
  try {
    await waitFor(() => resultsMsg() && !loading(), WAIT_MS);
    await choose(regionSel, region, "region");
    const propertySel = select("property");
    if (propertySel) await choose(propertySel, property, "property type");
    // The list filters by one commune at a time: once one is ticked, it is
    // the only one offered. The first the brain named is ticked; the rest
    // are said back to it.
    let skipped: string[] = [];
    if (region === "17") {
      const findBox = (said: string) => {
        const want = norm(said);
        const boxes = communeBoxes();
        return (
          boxes.find((b) => norm(b.label) === want) ??
          boxes.find((b) => norm(b.label).includes(want) || want.includes(norm(b.label))) ??
          null
        );
      };
      const ticked = communeBoxes().filter((b) => b.input.checked);
      const keep = communes.length ? findBox(communes[0]) : null;
      for (const b of ticked) {
        if (keep && b.input === keep.input) continue;
        await clickList(b.input);
      }
      if (communes.length) {
        await waitFor(() => communeBoxes().length > 1 || communeBoxes().some((b) => b.input.checked), 3000);
        const box = findBox(communes[0]);
        if (!box) {
          throw new Error(
            `no commune ${communes[0]} in the filter; it has: ${communeBoxes()
              .map((b) => b.label)
              .join(", ")}`,
          );
        }
        if (!box.input.checked) await clickList(box.input);
        skipped = communes.slice(1);
      }
    } else if (communes.length) {
      skipped = communes;
    }
    const results = document.querySelector<HTMLElement>(".projects-list__results-msg") ?? document.querySelector(".projects-list");
    const wantNames = (order.highlight ?? []).filter(Boolean);
    const wantPaths = (order.paths ?? []).filter(Boolean);
    const wanted = wantNames.length || wantPaths.length;
    // He is ringing the cards one by one as he names them: the list leaves
    // the one he is on alone.
    const narrated = Date.now() - cardRungAt < CARD_HOLDS_MS;
    let found: HTMLElement[] = [];
    if (wanted && !narrated) {
      found = await findOnPages(() => cardsFor(wantPaths, wantNames));
      if (found.length) {
        await scrollTo(found[0], "center");
        highlight(
          ...found.map((c) => {
            const key = cardPaths(c)[0] ?? "";
            const name = cardName(c);
            return () => cardsFor(key ? [key] : [], key ? [] : [name]);
          }),
        );
      }
    }
    if (!found.length && !narrated && results) {
      await scrollTo(results, "top");
      highlight(results);
    }
    report();
    const problems: string[] = [];
    if (skipped.length) {
      problems.push(
        region === "17"
          ? `the list filters one commune at a time; it shows ${listed().communes.join(", ")}, not ${skipped.join(", ")}`
          : `communes can only be chosen in Región Metropolitana; ${skipped.join(", ")} not applied`,
      );
    }
    if (wanted && !narrated && !found.length) {
      problems.push(`${(wantNames.length ? wantNames : wantPaths).join(", ")} is not among these ${listed().count} projects`);
    }
    if (problems.length) throw new Error(problems.join("; "));
  } finally {
    listing = false;
  }
}

// ─── A project's card, as he names it ─────────────────────────────────────

/** Ring the card of the project whose page is at `path` (paging the list to
 *  it), as Javier names that project. Off the list, a card or link to it on
 *  the page in front. */
async function showCard({ path, name }: { path: string; name?: string | null }): Promise<void> {
  if (!path) throw new Error("say which project's card to show");
  const label = name || path;
  if (kind() !== "projects") {
    const a = [...document.querySelectorAll<HTMLAnchorElement>("a[href]")].find(
      (x) => visible(x) && samePath(pathOf(x.href), path) && !x.closest("header, footer, .modal, [data-voqalize], .header, .footer"),
    );
    if (!a) throw new Error(`${label} has no card on ${location.pathname}`);
    const card = a.closest<HTMLElement>(".project-card-wrapper, .project-card, article, li, .slick-slide") ?? a;
    await scrollTo(card, "center");
    highlight(card);
    return;
  }
  return onTheList(async () => {
    await waitFor(() => select("region") && resultsMsg() && !loading(), WAIT_MS);
    const match = () => cardsFor([path], name ? [name] : []);
    const found = await findOnPages(match);
    if (!found.length) throw new Error(`${label} is not among the ${listed().count} projects the list shows`);
    cardRungAt = Date.now();
    await scrollTo(found[0], "center");
    highlight(match);
    report(false);
  });
}

// ─── Photos, plans, the tour, overlays ────────────────────────────────────
// The site's own lightbox (lightGallery) does not open for a script's click,
// and its "Agrandar imagen" loads the bare PNG in place of the page. So the
// photos and the plans open in a viewer of the extension's own, over the
// page: one picture at a time, with its caption and its place in the set,
// next and previous, and a slideshow. The visitor can use it too.

interface Shot {
  src: string;
  caption: string;
  /** Whose photo, in a slideshow of all of them. */
  which?: "gallery" | "amenities";
}
/** "photos": the gallery's and then the amenities', one show. */
type Which = "gallery" | "amenities" | "plan" | "photos";
const SLIDE_MS = 5000;
const SLIDESHOW_MAX_MS = 180_000;

/** What a photo shows, from its file's name where the site gives no alt:
 *  "2.-depto-grande-scaled.jpg" is "depto grande", "3-piscina-1.jpg" is
 *  "piscina". */
function captionOf(src: string): string {
  let file = (src.split("/").pop() ?? "").split("?")[0];
  try {
    file = decodeURIComponent(file);
  } catch {
    // Not encoded: as it is.
  }
  return clean(
    file
      .replace(/\.[a-z0-9]+$/i, "")
      .replace(/-scaled$/i, "")
      .replace(/-\d+x\d+$/, "")
      .replace(/[-_.]+/g, " ")
      .replace(/^\s*\d+\s+/, "")
      .replace(/\s+\d+$/, "")
      .replace(/\s+[a-z]$/i, ""),
  );
}

function shotsOf(buttons: Element[]): Shot[] {
  const seen = new Set<string>();
  const out: Shot[] = [];
  for (const b of buttons) {
    const raw = b.getAttribute("data-src") || b.querySelector("img")?.getAttribute("src") || "";
    if (!raw) continue;
    const src = new URL(raw, location.href).href;
    if (seen.has(src)) continue;
    seen.add(src);
    out.push({ src, caption: clean(b.querySelector("img")?.getAttribute("alt")) || captionOf(src) });
  }
  return out;
}

/** The gallery's photos, in order: the slider's own slides, not the copies it
 *  makes to loop. */
function galleryShots(): Shot[] {
  const g = document.querySelector(".l3-numbered-slider-section");
  if (!g) return [];
  const real = [...g.querySelectorAll(".slick-slide:not(.slick-cloned) button.nsLgSelector")];
  return shotsOf(real.length ? real : [...g.querySelectorAll("button.nsLgSelector")]);
}

function amenityShots(): Shot[] {
  return shotsOf([...document.querySelectorAll(".alternate-images-section button.aiLgSelector")]);
}

/** The gallery slider's photo in front, from 1. */
function sliderIndex(): number {
  const g = document.querySelector(".l3-numbered-slider-section");
  const i = Number(g?.querySelector(".slick-slide.slick-current")?.getAttribute("data-slick-index"));
  const n = galleryShots().length;
  return Number.isFinite(i) && n ? (((i % n) + n) % n) + 1 : 1;
}

interface Viewer {
  host: HTMLElement;
  img: HTMLImageElement;
  caption: HTMLElement;
  count: HTMLElement;
  playing: HTMLElement;
  which: Which;
  shots: Shot[];
  index: number;
  timer: ReturnType<typeof setInterval> | null;
  until: number;
}
let viewer: Viewer | null = null;

const VIEWER_CSS = `
  .v { position: fixed; inset: 0; background: rgba(12, 12, 14, 0.92); display: flex; align-items: center;
       justify-content: center; font: 15px/1.4 system-ui, sans-serif; color: #fff; }
  figure { margin: 0; display: flex; flex-direction: column; align-items: center; gap: 12px; max-width: 88vw; }
  img { max-width: 88vw; max-height: 78vh; object-fit: contain; background: #fff; border-radius: 6px;
        box-shadow: 0 10px 40px rgba(0, 0, 0, 0.5); transition: opacity 250ms ease; }
  figcaption { display: flex; gap: 14px; align-items: baseline; }
  .c { font-weight: 600; }
  .c::first-letter { text-transform: uppercase; }
  .n { opacity: 0.75; font-variant-numeric: tabular-nums; }
  .play { color: ${RING}; font-weight: 600; }
  .play[hidden] { display: none; }
  button { position: absolute; border: 0; background: rgba(255, 255, 255, 0.12); color: #fff; cursor: pointer;
           width: 52px; height: 52px; border-radius: 50%; font-size: 30px; line-height: 52px; padding: 0; }
  button:hover { background: rgba(255, 255, 255, 0.24); }
  .x { top: 84px; right: 28px; font-size: 26px; }
  .p { left: 28px; top: calc(50% - 26px); }
  .nx { right: 28px; top: calc(50% - 26px); }
  .p[hidden], .nx[hidden] { display: none; }
`;

function shownNow(by: "javier" | "visitor", ended = false): void {
  if (!viewer) return;
  const v = viewer;
  const shot = v.shots[v.index];
  v.img.style.opacity = "0";
  v.img.onload = () => (v.img.style.opacity = "1");
  v.img.src = shot.src;
  v.img.alt = shot.caption;
  if (v.img.complete) v.img.style.opacity = "1";
  v.caption.textContent = shot.caption;
  v.count.textContent = v.shots.length > 1 ? `${v.index + 1} / ${v.shots.length}` : "";
  v.playing.hidden = !v.timer;
  for (const b of v.host.shadowRoot!.querySelectorAll<HTMLElement>(".p, .nx")) b.hidden = v.shots.length < 2;
  emit("photo_shown", {
    which: shot.which ?? (v.which === "photos" ? "gallery" : v.which),
    index: v.index + 1,
    total: v.shots.length,
    caption: shot.caption,
    playing: Boolean(v.timer),
    fullscreen: true,
    ended,
    by,
  });
}

function openViewer(which: Which, shots: Shot[], index: number): void {
  if (viewer && viewer.which === which && viewer.shots.map((s) => s.src).join() === shots.map((s) => s.src).join()) {
    viewer.index = Math.max(0, Math.min(index, shots.length - 1));
    shownNow("javier");
    return;
  }
  closeViewer();
  clearHighlight();
  const host = document.createElement("div");
  host.setAttribute("data-voqalize", "viewer");
  Object.assign(host.style, { position: "fixed", inset: "0", zIndex: "2147482500" });
  const root = host.attachShadow({ mode: "open" });
  root.innerHTML = `<style>${VIEWER_CSS}</style><div class="v" part="viewer">
    <figure><img alt=""><figcaption><span class="c"></span><span class="n"></span>
    <span class="play" hidden>▶ Presentación</span></figcaption></figure>
    <button class="p" aria-label="Anterior">‹</button><button class="nx" aria-label="Siguiente">›</button>
    <button class="x" aria-label="Cerrar">✕</button></div>`;
  const $ = <T extends HTMLElement>(sel: string) => root.querySelector<T>(sel)!;
  viewer = {
    host,
    img: $("img"),
    caption: $(".c"),
    count: $(".n"),
    playing: $(".play"),
    which,
    shots,
    index: Math.max(0, Math.min(index, shots.length - 1)),
    timer: null,
    until: 0,
  };
  // The visitor's own hands on it.
  $(".p").addEventListener("click", (e) => (e.stopPropagation(), stepViewer(-1, "visitor")));
  $(".nx").addEventListener("click", (e) => (e.stopPropagation(), stepViewer(1, "visitor")));
  $(".x").addEventListener("click", (e) => (e.stopPropagation(), closeViewer("visitor")));
  $(".v").addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closeViewer("visitor");
  });
  document.documentElement.appendChild(host);
  shownNow("javier");
}

function stepViewer(by: number, who: "javier" | "visitor"): void {
  if (!viewer) return;
  const n = viewer.shots.length;
  viewer.index = (((viewer.index + by) % n) + n) % n;
  shownNow(who);
}

function stopShow(): void {
  if (!viewer?.timer) return;
  clearInterval(viewer.timer);
  viewer.timer = null;
}

/** Close the viewer; the gallery's slider is left on the photo it showed. */
function closeViewer(by: "javier" | "visitor" = "javier"): void {
  if (!viewer) return;
  const v = viewer;
  viewer = null;
  if (v.timer) clearInterval(v.timer);
  v.host.remove();
  const shot = v.shots[v.index];
  if (shot && (v.which === "gallery" || shot.which === "gallery")) {
    const chip = document.querySelector<HTMLElement>(`.l3-numbered-slider-section span.slide-index[data-slide="${v.index}"]`);
    chip?.click();
  }
  emit("viewer_closed", { which: v.which === "photos" ? (shot?.which ?? "gallery") : v.which, by });
}

window.addEventListener(
  "keydown",
  (e) => {
    if (!viewer || !e.isTrusted) return;
    if (e.key === "Escape") closeViewer("visitor");
    else if (e.key === "ArrowRight") stepViewer(1, "visitor");
    else if (e.key === "ArrowLeft") stepViewer(-1, "visitor");
    else return;
    e.preventDefault();
  },
  true,
);

async function showPhotos({
  which,
  index,
  fullscreen,
}: {
  which?: string | null;
  index?: number | null;
  fullscreen?: boolean | null;
}): Promise<void> {
  if (kind() !== "project") throw new Error("photos are on a project's page");
  const asked = index == null ? null : Math.max(1, Math.floor(Number(index) || 1));
  if (which === "amenities") {
    const shots = amenityShots();
    if (!shots.length) throw new Error("this project shows no amenities photos");
    if (asked && asked > shots.length) throw new Error(`the amenities have ${shots.length} photos`);
    openViewer("amenities", shots, (asked ?? 1) - 1);
    return;
  }
  const section = document.querySelector<HTMLElement>(".l3-numbered-slider-section");
  if (!section) throw new Error("this project has no photo gallery");
  const shots = galleryShots();
  if (asked && shots.length && asked > shots.length) throw new Error(`the gallery has ${shots.length} photos`);
  if (fullscreen || viewer?.which === "gallery") {
    if (!shots.length) throw new Error("this project's gallery has no photos to open");
    openViewer("gallery", shots, (asked ?? sliderIndex()) - 1);
    return;
  }
  closeViewer();
  const chips = [...section.querySelectorAll<HTMLElement>("span.slide-index")];
  await scrollTo(section, "top");
  if (asked && chips.length) {
    const chip = chips.find((c) => c.getAttribute("data-slide") === String(asked - 1)) ?? chips[asked - 1];
    chip.click();
    await sleep(700);
  }
  highlight(section);
  if (shots.length) {
    const i = asked ?? sliderIndex();
    emit("photo_shown", { which: "gallery", index: i, total: shots.length, caption: shots[i - 1]?.caption ?? "", playing: false, fullscreen: false, by: "javier" });
  }
}

/** The next photo (or with `back`, the one before): in the viewer when it is
 *  open, else on the gallery's slider. */
async function stepPhoto({ back }: { back?: boolean | null }): Promise<void> {
  if (viewer) {
    stopShow();
    stepViewer(back ? -1 : 1, "javier");
    return;
  }
  if (kind() !== "project") throw new Error("photos are on a project's page");
  const n = galleryShots().length;
  if (!n) throw new Error("no photos are open, and this page has no gallery");
  const next = ((sliderIndex() - 1 + (back ? -1 : 1) + n) % n) + 1;
  await showPhotos({ which: "gallery", index: next, fullscreen: false });
}

/** Every photo, full screen, one after another every few seconds, by
 *  itself: the gallery's and then the amenities' (or only the ones asked
 *  for), from the one in front, to the last, where it stops. The visitor
 *  stops it by speaking (the holder sends the stop), by closing it, or by
 *  asking him; it never runs more than three minutes. */
async function slideshow({
  play,
  which,
  seconds,
}: {
  play?: boolean | null;
  which?: string | null;
  seconds?: number | null;
}): Promise<void> {
  if (play === false) {
    if (!viewer?.timer) return;
    stopShow();
    shownNow("javier");
    return;
  }
  if (kind() !== "project") throw new Error("photos are on a project's page");
  const want: Which = which === "amenities" ? "amenities" : which === "gallery" ? "gallery" : "photos";
  const gallery = galleryShots().map((x) => ({ ...x, which: "gallery" as const }));
  const amenities = amenityShots().map((x) => ({ ...x, which: "amenities" as const }));
  const shots = want === "gallery" ? gallery : want === "amenities" ? amenities : [...gallery, ...amenities];
  if (shots.length < 2) throw new Error(shots.length ? "there is only one photo here" : "this project shows no photos");
  // From the photo in front, if it is one of these; else from the first.
  let from = 0;
  if (viewer && viewer.which !== "plan") {
    const here = viewer.shots[viewer.index]?.src;
    from = Math.max(0, shots.findIndex((x) => x.src === here));
  } else if (want !== "amenities") {
    from = sliderIndex() - 1;
  }
  openViewer(want, shots, from);
  const v = viewer as Viewer | null;
  if (!v) throw new Error("no photos to show");
  stopShow();
  const every = Math.max(3, Math.min(15, Number(seconds) || SLIDE_MS / 1000)) * 1000;
  v.until = Date.now() + SLIDESHOW_MAX_MS;
  v.timer = setInterval(() => {
    if (viewer !== v) return clearInterval(v.timer ?? 0);
    if (Date.now() > v.until || v.index >= v.shots.length - 1) {
      // The last photo, or long enough: it stays on screen, stopped.
      stopShow();
      return shownNow("javier", true);
    }
    stepViewer(1, "javier");
  }, every);
  shownNow("javier");
}

/** A typology's floor plan, full screen: on a project page the plan the
 *  typology section shows; on /proyectos/cotizar/ the unit's plan and where
 *  it sits on the floor. */
async function showFloorPlan({ typology }: { typology?: string | null }): Promise<void> {
  if (kind() === "quote") {
    if (typology) await quoteTypology(typology);
    const tab =
      document.querySelector<HTMLAnchorElement>("ul[id$=tabs] a.nav-link.active") ??
      [...document.querySelectorAll<HTMLAnchorElement>("ul[id$=tabs] a.nav-link")].find(visible);
    const pane = tab?.getAttribute("href") ? document.querySelector(tab.getAttribute("href")!) : null;
    const imgs = [...(pane ?? document).querySelectorAll<HTMLImageElement>(".quote__option-floor-img img")];
    const label = clean(tab?.textContent);
    const shots = shotsOf(imgs.map((i) => i.closest("a") ?? i)).map((s) => ({
      src: s.src,
      caption: /esq/i.test(s.src) ? `${label}: ubicación en la planta del piso` : `${label}: planta`,
    }));
    if (!shots.length) throw new Error(`${label || "this typology"} shows no plan here`);
    openViewer("plan", shots, 0);
    return;
  }
  if (kind() !== "project") throw new Error("floor plans are on a project's page or its cotizar page");
  if (!typologyItems().length) throw new Error(`there are no typologies on ${location.pathname}`);
  if (typology) await selectTypology({ label: typology }, { forPlan: true });
  const img = await waitFor(() => {
    const i = document.querySelector<HTMLImageElement>("[id^=floorPlanImage_cotizador]");
    return i?.getAttribute("src") ? i : null;
  }, 3000);
  if (!img) throw new Error("this typology shows no floor plan");
  const items = typologyItems();
  const li = items.find((x) => x.classList.contains("active")) ?? items[0];
  const total = fact("totalAreaValue");
  openViewer("plan", [{ src: img.src, caption: `${typologyLabel(li)}${total ? ` · ${total} m² totales` : ""}` }], 0);
}

async function openTour(): Promise<void> {
  const btn = document.querySelector<HTMLElement>(".video-tour-section .tour-btn");
  if (!btn) throw new Error(`this page has no virtual tour${kind() === "project" ? "" : "; tours are on some project pages"}`);
  const section = btn.closest<HTMLElement>(".video-tour-section")!;
  closeViewer();
  await scrollTo(section, "top");
  clearHighlight();
  btn.click();
  if (!(await waitFor(() => document.querySelector(".modal.show"), 3000))) throw new Error("the tour did not open");
}

// ─── The brochure ─────────────────────────────────────────────────────────
// A project's brochure is a PDF on ssilva.cl (under "Descargar Brochure"),
// and the same pages as a 3D flip-book page that is slow to start and leaves
// the site. He shows the PDF over the page, in Chrome's own PDF view (the
// site allows framing it), at the page he names, and downloads it.

let doc: { host: HTMLElement; frame: HTMLIFrameElement; url: string; page: number } | null = null;

/** The project's brochure PDF: the one he names, if it is on ssilva.cl, else
 *  the page's own "Descargar Brochure". */
function brochureUrl(asked?: string | null): string {
  const pdf = (href: string) => {
    try {
      const u = new URL(href, location.href);
      return isSsilva(u.host) && /\.pdf$/i.test(u.pathname) ? ((u.host = location.host), u.href) : "";
    } catch {
      return "";
    }
  };
  if (asked && pdf(asked)) return pdf(asked);
  const links = [
    ...document.querySelectorAll<HTMLAnchorElement>(".l3-other-docs-section a[href], .files-block-section a[href], a[href$='.pdf']"),
  ];
  const own = links.map((a) => pdf(a.href)).find(Boolean);
  if (own) return own;
  throw new Error(`there is no brochure to show on ${location.pathname}`);
}

function closeDoc(by: "javier" | "visitor" = "javier"): void {
  if (!doc) return;
  doc.host.remove();
  doc = null;
  emit("viewer_closed", { which: "brochure", by });
}

const DOC_CSS = `
  .v { position: fixed; inset: 0; background: rgba(12, 12, 14, 0.92); display: flex; flex-direction: column;
       align-items: center; justify-content: center; gap: 12px; font: 15px/1.4 system-ui, sans-serif; color: #fff; }
  iframe { width: min(1100px, 88vw); height: 78vh; border: 0; border-radius: 6px; background: #fff;
           box-shadow: 0 10px 40px rgba(0, 0, 0, 0.5); }
  .bar { display: flex; gap: 18px; align-items: center; }
  .bar a { color: #fff; font-weight: 600; text-decoration: none; padding: 8px 14px; border-radius: 18px;
           background: rgba(255, 255, 255, 0.14); }
  .bar a.dl { background: ${RING}; }
  .x { position: absolute; top: 84px; right: 28px; border: 0; background: rgba(255, 255, 255, 0.12); color: #fff;
       cursor: pointer; width: 52px; height: 52px; border-radius: 50%; font-size: 26px; }
`;

async function showBrochure({ url, page }: { url?: string | null; page?: number | null }): Promise<void> {
  const pdf = brochureUrl(url);
  const n = Math.max(1, Math.floor(Number(page) || 1));
  closeViewer();
  clearHighlight();
  if (doc && doc.url === pdf) {
    // Another page of the same brochure. Chrome's PDF view ignores a new
    // #page on the frame it has, so a fresh frame opens it there (the file
    // is cached).
    doc.page = n;
    const fresh = document.createElement("iframe");
    fresh.title = "Brochure";
    fresh.src = `${pdf}#page=${n}`;
    doc.frame.replaceWith(fresh);
    doc.frame = fresh;
    emit("brochure_shown", { url: pdf, page: n });
    return;
  }
  closeDoc();
  const host = document.createElement("div");
  host.setAttribute("data-voqalize", "brochure");
  Object.assign(host.style, { position: "fixed", inset: "0", zIndex: "2147482500" });
  const root = host.attachShadow({ mode: "open" });
  const name = decodeURIComponent(pdf.split("/").pop() ?? "brochure.pdf");
  root.innerHTML = `<style>${DOC_CSS}</style><div class="v">
    <iframe title="Brochure"></iframe>
    <div class="bar"><a class="dl" download="${name.replace(/"/g, "")}">Descargar brochure</a>
    <a class="tab" target="_blank" rel="noopener">Abrir en otra pestaña</a></div>
    <button class="x" aria-label="Cerrar">✕</button></div>`;
  const frame = root.querySelector("iframe")!;
  frame.src = `${pdf}#page=${n}`;
  root.querySelector<HTMLAnchorElement>(".dl")!.href = pdf;
  root.querySelector<HTMLAnchorElement>(".tab")!.href = pdf;
  root.querySelector(".x")!.addEventListener("click", () => closeDoc("visitor"));
  root.querySelector(".v")!.addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closeDoc("visitor");
  });
  document.documentElement.appendChild(host);
  doc = { host, frame, url: pdf, page: n };
  emit("brochure_shown", { url: pdf, page: n });
}

/** Download the brochure to the visitor's computer, as the site's own
 *  "Descargar Brochure" would if it opened as a file. */
async function downloadBrochure({ url }: { url?: string | null }): Promise<void> {
  const pdf = brochureUrl(url);
  const a = document.createElement("a");
  a.href = pdf;
  a.download = decodeURIComponent(pdf.split("/").pop() ?? "brochure.pdf");
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  a.remove();
  emit("brochure_downloaded", { url: pdf });
}

window.addEventListener(
  "keydown",
  (e) => {
    if (doc && e.isTrusted && e.key === "Escape") closeDoc("visitor");
  },
  true,
);

// The site's "Agrandar imagen" loads the bare plan PNG in place of the page
// (dev call 280b2561: the visitor pressed it, came back, and the brain lost
// the page). The press opens the plan full screen over the page instead.
document.addEventListener(
  "click",
  (e) => {
    const btn = (e.target as Element | null)?.closest?.("[id^=enlargeImageBtn_cotizador]");
    if (!btn || !e.isTrusted) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    void showFloorPlan({ typology: null }).catch(() => {});
  },
  true,
);

async function closeOverlay(): Promise<void> {
  closeViewer();
  closeDoc();
  const lg = document.querySelector<HTMLElement>(".lg-outer.lg-visible, .lg-outer.lg-show-in");
  if (lg) {
    lg.querySelector<HTMLElement>(".lg-close")?.click();
    await waitFor(() => !document.querySelector(".lg-outer.lg-visible"), 2000);
  }
  for (const modal of document.querySelectorAll<HTMLElement>(".modal.show")) {
    modal.querySelector<HTMLElement>("[data-dismiss=modal], .close")?.click();
  }
  await waitFor(() => !document.querySelector(".modal.show"), 2000);
}

async function openWhatsApp(): Promise<void> {
  const a =
    document.querySelector<HTMLAnchorElement>("a.floating-quote-btn[href]") ??
    document.querySelector<HTMLAnchorElement>(".project-actions-section a[href*='whatsapp'], .project-actions-section a[href*='wa.me']");
  if (!a) throw new Error("this page has no WhatsApp contact; each project page has its own");
  highlight(a);
  const failed = await openTab(a.href);
  if (failed) throw new Error(failed);
}

// ─── fill_lead_form: the HubSpot frame ────────────────────────────────────

const HSFORMS = "https://js.hsforms.net";
let calls = 0;

/** The quote form's frame box on this page: in the typology section on a
 *  project page, in step 2 (`#data`) on /proyectos/cotizar/. */
function formBox(): HTMLElement | null {
  return (
    document.querySelector<HTMLElement>(".cotizador-l1-section .unit-info .hs-form-frame") ??
    document.querySelector<HTMLElement>(".cotizador-l1-section .hs-form-frame") ??
    document.querySelector<HTMLElement>("#data .hs-form-frame")
  );
}

function formFrame(): HTMLIFrameElement | null {
  return formBox()?.querySelector<HTMLIFrameElement>("iframe[src^='https://js.hsforms.net']") ?? null;
}

/** One order to the frame (`hsform.ts`), answered with its state. */
function toFrame(frame: HTMLIFrameElement, cmd: string, fill?: unknown, ms = 15000) {
  const id = ++calls;
  return new Promise<{ error: string | null; state: unknown } | null>((resolve) => {
    const timer = setTimeout(() => done(null), ms);
    const on = (e: MessageEvent) => {
      if (e.origin !== HSFORMS) return;
      const reply = (e.data as { voqalizeHsDone?: { id: number; error: string | null; state: unknown } })?.voqalizeHsDone;
      if (reply?.id === id) done(reply);
    };
    function done(v: { error: string | null; state: unknown } | null) {
      clearTimeout(timer);
      window.removeEventListener("message", on);
      resolve(v);
    }
    window.addEventListener("message", on);
    frame.contentWindow?.postMessage({ voqalizeHsCmd: { id, cmd, fill } }, HSFORMS);
  });
}

/** On /proyectos/cotizar/ the form is step 2, behind "CONTINUAR", once a
 *  unit is chosen in step 1. */
async function reachQuoteForm(): Promise<void> {
  if (kind() !== "quote" || visible(formBox())) return;
  const pane = [...document.querySelectorAll<HTMLElement>(".tab-pane")].find(visible);
  const unit = pane?.querySelector<HTMLSelectElement>("select");
  if (unit && !unit.value) {
    await scrollTo(unit, "center");
    highlight(unit);
    throw new Error('choose a unit first: "Selecciona la unidad para cotizar" in step 1, then the form opens');
  }
  const next = [...document.querySelectorAll<HTMLElement>("button, a")].find(
    (b) => visible(b) && /^continuar/i.test(clean(b.textContent)),
  );
  if (!next) throw new Error("step 1 of the quote has no CONTINUAR button showing");
  next.click();
  if (!(await waitFor(() => visible(formBox()), 4000))) throw new Error("the quote's step 2 did not open");
}

type LeadOrder = Record<string, string | boolean | null | undefined>;

async function fillLeadForm(order: LeadOrder): Promise<void> {
  if (kind() !== "project" && kind() !== "quote") throw new Error("the quote form is on a project's page");
  await reachQuoteForm();
  const box = formBox();
  if (!box) throw new Error("this page has no quote form");
  await scrollTo(box, "center");
  const frame = await waitFor(formFrame, WAIT_MS);
  if (!frame) throw new Error("the quote form did not load");
  highlight(frame);
  // The frame's script answers once HubSpot has drawn the form.
  let answered = null as Awaited<ReturnType<typeof toFrame>>;
  for (let i = 0; i < 15 && !(answered && !answered.error); i++) {
    answered = await toFrame(frame, "state", undefined, 1000);
    if (!answered || answered.error) await sleep(400);
  }
  if (!answered || answered.error) throw new Error("the quote form did not load");
  const fill: LeadOrder = {};
  for (const k of ["firstname", "lastname", "rut", "email", "phone", "motivo", "tipologia", "ingreso", "pie"]) {
    if (typeof order[k] === "string" && order[k]) fill[k] = order[k];
  }
  fill.next_step = Boolean(order.next_step);
  const done = await toFrame(frame, "fill", fill);
  if (!done) throw new Error("the quote form did not answer");
  emit("lead_form", leadState(done.state));
  await scrollTo(box, "center");
  highlight(frame);
  if (done.error) throw new Error(done.error);
}

function leadState(s: unknown) {
  const { initial: _, ...rest } = (s ?? {}) as Record<string, unknown>;
  return rest;
}

/** What the frame reports by itself: the visitor's typing, their steps, and
 *  their press of "Enviar". */
function watchLeadForm(): void {
  window.addEventListener("message", (e: MessageEvent) => {
    if (e.origin !== HSFORMS) return;
    const data = e.data as { voqalizeHs?: Record<string, unknown>; voqalizeHsSubmitted?: { blocked?: boolean } };
    const s = data?.voqalizeHs;
    if (s) {
      // The form as it first loads, empty, is no news.
      const filled = s.filled as Record<string, string> | undefined;
      if (!s.initial || (filled && Object.keys(filled).length)) emit("lead_form", leadState(s));
    }
    if (data?.voqalizeHsSubmitted) emit("lead_submitted", { blocked: Boolean(data.voqalizeHsSubmitted.blocked) });
  });
}

// ─── Reporting ────────────────────────────────────────────────────────────

let emitter: ((event: string, payload: unknown) => void) | null = null;
/** Events from before anyone listens — the quote form's, on a page that
 *  loaded before the brain could hear it — kept for a short while. */
let early: { at: number; event: string; payload: unknown }[] = [];
const EARLY_MS = 30_000;

function emit(event: string, payload: unknown): void {
  if (emitter) return emitter(event, payload);
  early.push({ at: Date.now(), event, payload });
  if (early.length > 20) early.shift();
}

let lastUrl: string | null = null;

/** /proyectos/ changes its address as the visitor filters (`pushState`); a
 *  change of the list is reported, the same page is not. */
function routeChanged(): void {
  setTimeout(async () => {
    const here = location.origin + location.pathname;
    // Before anyone listens, `start` reports the page as it is then.
    if (!emitter) return;
    if (here !== lastUrl) {
      lastUrl = here;
      clearHighlight();
      emit("page_changed", context());
      return;
    }
    if (kind() === "projects" && !listing) {
      await listSettled();
      if (!listing) report(false);
    }
  }, 60);
}

function watchRoutes(): void {
  for (const name of ["pushState", "replaceState"] as const) {
    const real = history[name];
    history[name] = function (this: History, ...args: Parameters<History["pushState"]>) {
      const out = real.apply(this, args);
      routeChanged();
      return out;
    } as History["pushState"];
  }
  window.addEventListener("popstate", routeChanged);
}

/** A typology the visitor clicked themselves is reported as one Javier chose. */
function watchTypologies(): void {
  // A press on a typology's label also clicks its input: one press, one report
  // (dev call ec152777 reported each of the visitor's presses twice).
  let last: { li: Element; at: number } | null = null;
  document.addEventListener(
    "click",
    (e) => {
      if (!e.isTrusted) return;
      const li = (e.target as Element | null)?.closest?.(".cotizador-l1 li.type-item");
      if (!li) return;
      if (last && last.li === li && Date.now() - last.at < 600) return;
      last = { li, at: Date.now() };
      void (async () => {
        await waitFor(spinning, 600);
        await waitFor(() => !spinning(), 5000);
        await sleep(150);
        emit("typology_shown", {
          label: typologyLabel(li),
          price: cotizadorPrice(),
          total_area: fact("totalAreaValue") ? `${fact("totalAreaValue")} m²` : "",
          useful_area: fact("usefulAreaValue") ? `${fact("usefulAreaValue")} m²` : "",
          bedrooms: fact("bedroomsValue"),
          bathrooms: fact("bathroomsValue"),
          orientation: fact("orientationValue"),
        });
      })();
    },
    true,
  );
}

function start(next: (event: string, payload: unknown) => void): () => void {
  emitter = next;
  lastUrl = location.origin + location.pathname;
  emit("page_changed", context());
  const kept = early.filter((e) => Date.now() - e.at < EARLY_MS && e.event !== "page_changed");
  early = [];
  for (const e of kept) emit(e.event, e.payload);
  return () => {
    if (emitter === next) emitter = null;
  };
}

const COMMANDS: Record<string, (payload: never) => Promise<void>> = {
  navigate,
  show_section: showSection,
  select_typology: selectTypology,
  show_projects: showProjects,
  show_photos: showPhotos,
  show_card: showCard,
  step_photo: stepPhoto,
  slideshow,
  show_floor_plan: showFloorPlan,
  show_brochure: showBrochure,
  download_brochure: downloadBrochure,
  open_tour: openTour,
  close_overlay: closeOverlay,
  fill_lead_form: fillLeadForm,
  // The SDK names `OpenWhatsApp` `open_whats_app`; either spelling is taken.
  open_whats_app: openWhatsApp,
  open_whatsapp: openWhatsApp,
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

if (!window.voqalizeSsilva) {
  styleThePage();
  watchRoutes();
  watchTypologies();
  watchLeadForm();
  watchTranslatedList();
  window.voqalizeSsilva = { run, context, leaves, obstacles, start, commands: Object.keys(COMMANDS) };
}

export {};
