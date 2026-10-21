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
 *     load**, so a move to another page stores what to do there in the hub
 *     (`setPendingMove`) and loads it; the next page's script makes the move.
 *     The call itself rejoins on the new page (`keepAcrossPageLoads`).
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
  price: string;
  status: string;
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
/** A typology label, spelled any way: "2D | 2B", "2d|2b", "2D-2B". */
const typ = (s: string | null | undefined) => norm(s).replace(/\s*[|/–-]\s*/g, "|").replace(/\s+/g, " ");
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

function heroPrice(): string {
  const text = clean(document.querySelector(".l3-hero")?.textContent);
  const m = text.match(/desde\s+([\d.,]+)\s*UF/i);
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
    price: k === "project" ? cotizadorPrice() || heroPrice() : "",
    status: clean(document.querySelector(".l3-project-status-section .status-item.active .title")?.textContent),
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

/** Load another page, first leaving the move to make there with the hub. */
async function load(url: URL, then?: { command: string; payload: unknown }): Promise<void> {
  if (then && !(await setPendingMove(then))) {
    // No hub (the extension reloaded under the page): the page still moves;
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
  const want = norm(text);
  if (!want) return null;
  let best: HTMLElement | null = null;
  let bestLen = Infinity;
  for (const el of root.querySelectorAll<HTMLElement>("*")) {
    if (el.closest("[data-voqalize], script, style, .modal") || !visible(el)) continue;
    const t = norm(el.textContent);
    if (!t.includes(want) || t.length >= bestLen) continue;
    best = el;
    bestLen = t.length;
  }
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
  return (
    all.find((li) => t(li) === want) ??
    all.find((li) => t(li).replace(/ /g, "") === want.replace(/ /g, "")) ??
    all.find((li) => t(li).startsWith(want)) ??
    all.find((li) => t(li).includes(want)) ??
    all.find((li) => want.includes(t(li))) ??
    null
  );
}

const fact = (id: string) => clean(document.querySelector(`[id^=${id}_cotizador]`)?.textContent);
const spinning = () => !!document.querySelector(".cotizador-spinner-overlay.active");

async function selectTypology({ label }: { label: string }): Promise<void> {
  if (kind() === "quote") return quoteTypology(label);
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
const cardName = (c: Element) =>
  clean([...c.querySelectorAll(".project-card__opp-condo-name")].map((e) => clean(e.textContent)).find(Boolean));

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
  return {
    count: Number(resultsMsg().match(/(\d+)\s+proyectos?/i)?.[1] ?? cards().length),
    region: selectedText(select("region")),
    property: selectedText(select("property")),
    communes: communeBoxes()
      .filter((c) => c.input.checked)
      .map((c) => c.label),
    projects: cards().map(cardName).filter(Boolean),
  };
}

/** The list's own select, set the way a visitor's choice sets it. */
async function choose(sel: HTMLSelectElement, value: string): Promise<void> {
  if (sel.value === value) return;
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
}

async function showProjects(order: ProjectsOrder): Promise<void> {
  const communes = (order.communes ?? []).filter(Boolean);
  // Communes are only offered under Región Metropolitana.
  const region = idFor(REGIONS, order.region || (communes.length ? "metropolitana" : null), "region");
  const property = idFor(PROPERTIES, order.property, "property type");
  if (!samePath(location.pathname, "/proyectos/")) {
    const url = new URL("/proyectos/", location.origin);
    if (region) url.searchParams.set("region", region);
    if (property) url.searchParams.set("property", property);
    await load(url, { command: "show_projects", payload: order });
    return;
  }
  listing = true;
  try {
    const regionSel = await waitFor(() => select("region"), WAIT_MS);
    if (!regionSel) throw new Error("the project list did not load");
    await waitFor(() => resultsMsg() && !loading(), WAIT_MS);
    await choose(regionSel, region);
    const propertySel = select("property");
    if (propertySel) await choose(propertySel, property);
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
    let found: HTMLElement[] = [];
    if (wantNames.length) {
      const match = () =>
        cards().filter((c) => {
          const n = norm(cardName(c));
          return n && wantNames.some((w) => n === norm(w) || n.includes(norm(w)) || norm(w).includes(n));
        });
      found = match();
      // Not on this page: the other pages, in order, until it is.
      if (!found.length) {
        const start = currentPage();
        for (const n of pageLinks().map((a) => clean(a.textContent))) {
          if (n === currentPage()) continue;
          const link = pageLinks().find((a) => clean(a.textContent) === n);
          if (!link) continue;
          await clickList(link);
          found = match();
          if (found.length) break;
        }
        if (!found.length && currentPage() !== start) {
          const back = pageLinks().find((a) => clean(a.textContent) === start);
          if (back) await clickList(back);
        }
      }
    }
    if (found.length) {
      await scrollTo(found[0], "center");
      const names = found.map(cardName);
      highlight(...names.map((n) => () => cards().filter((c) => cardName(c) === n)));
    } else if (results) {
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
    if (wantNames.length && !found.length) problems.push(`${wantNames.join(", ")} is not among these ${listed().count} projects`);
    if (problems.length) throw new Error(problems.join("; "));
  } finally {
    listing = false;
  }
}

// ─── Photos, the tour, overlays ───────────────────────────────────────────

async function showPhotos({ which, index }: { which?: string | null; index?: number | null }): Promise<void> {
  if (kind() !== "project") throw new Error("photos are on a project's page");
  const n = Math.max(1, Math.floor(Number(index) || 1));
  if (which === "amenities") {
    const section = document.querySelector<HTMLElement>(".alternate-images-section");
    const buttons = [...(section?.querySelectorAll<HTMLButtonElement>("button.aiLgSelector") ?? [])];
    if (!section || !buttons.length) throw new Error("this project shows no amenities photos");
    if (n > buttons.length) throw new Error(`the amenities have ${buttons.length} photos`);
    await scrollTo(section, "top");
    clearHighlight();
    buttons[n - 1].click();
    if (!(await waitFor(() => document.querySelector(".lg-outer.lg-visible, .lg-outer.lg-show-in"), 3000))) {
      throw new Error("the photo viewer did not open");
    }
    return;
  }
  const section = document.querySelector<HTMLElement>(".l3-numbered-slider-section");
  if (!section) throw new Error("this project has no photo gallery");
  const chips = [...section.querySelectorAll<HTMLElement>("span.slide-index")];
  await scrollTo(section, "top");
  if (index != null && chips.length) {
    if (n > chips.length) throw new Error(`the gallery has ${chips.length} photos`);
    const chip = chips.find((c) => c.getAttribute("data-slide") === String(n - 1)) ?? chips[n - 1];
    chip.click();
    await sleep(700);
  }
  highlight(section);
}

async function openTour(): Promise<void> {
  const btn = document.querySelector<HTMLElement>(".video-tour-section .tour-btn");
  if (!btn) throw new Error(`this page has no virtual tour${kind() === "project" ? "" : "; tours are on some project pages"}`);
  const section = btn.closest<HTMLElement>(".video-tour-section")!;
  await scrollTo(section, "top");
  clearHighlight();
  btn.click();
  if (!(await waitFor(() => document.querySelector(".modal.show"), 3000))) throw new Error("the tour did not open");
}

async function closeOverlay(): Promise<void> {
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
/** Events from before anyone listens — a move made on a page that loaded
 *  while the call was still rejoining — kept for a short while. */
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
  document.addEventListener(
    "click",
    (e) => {
      if (!e.isTrusted) return;
      const li = (e.target as Element | null)?.closest?.(".cotizador-l1 li.type-item");
      if (!li) return;
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
  window.voqalizeSsilva = { run, context, leaves, obstacles, start, commands: Object.keys(COMMANDS) };
}

export {};
