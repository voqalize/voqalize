/**
 * The site adapter: drive the Universidad Alberto Hurtado's websites from the
 * outside, with no help from the university's developers.
 *
 * The brain sends a Voqalize `ui-command` ({command, payload}) and `run`
 * performs it on the page in front; the page reports back through `start`,
 * which calls `emit(event, payload)` for every page the visitor lands on and
 * for what the visitor does that the brain follows (the lead form, the
 * audiomalla, a press of "Enviar").
 *
 * What the site is, for a script like this: three WordPress themes on
 * Bootstrap 5 (admision.uahurtado.cl, postgrados.uahurtado.cl and
 * www.uahurtado.cl), rendered on the server, `window.bootstrap` global, every
 * move between pages a full page load and often a move to another origin.
 * Inside a page, tabs, pills and accordions are plain Bootstrap components with
 * stable ids, and every pane is in the document whether it is open or not. So:
 *
 *   - pages are named by their whole URL; a move that needs another page keeps
 *     itself for the next page of this tab (`hooks.pend`, the extension's hub,
 *     since `sessionStorage` does not cross hosts) and loads it; the next
 *     page's `content.ts` makes it once that page is up;
 *   - a career page (`admision…/carreras/<slug>/`) is read whole at load: its
 *     data table, its tabs, its PAES weights and its 2027 fees, the latter as
 *     the page writes them on screen, never from the `data-sheets-value`
 *     attributes beside them, which hold old figures;
 *   - what is reported is what is laid out at this width, or hidden only in a
 *     pane the adapter can open: never a mobile twin the layout hides;
 *   - the live reads the brain cannot make (it never fetches uahurtado.cl) are
 *     made here, and the site's REST record beside them by the service worker
 *     (`hooks.rest`), which may read across hosts;
 *   - the lead form `form#admisionForm` is filled, never sent: no `submit()`,
 *     no `requestSubmit()`, no press of "Enviar", never the RUT. The visitor
 *     presses "Enviar" and the lead goes to UAH's admissions, as it always does.
 */

import type {
  AppEvent, CareerSheet, FillLeadForm, LeadFormInfo, LeadFormState, Navigate, OpenCareerMenu, OpenFaq,
  PageChanged, PlayAudiomalla, ProgramSheet, Row, ShowAdmission, ShowProgram, ShowSection, ShowSignup, VisitCard,
} from "./actions.gen";
import {
  best, boxOf, clean, clearHighlight, headerHeight, highlight, inOrder, laidOut, loose, norm, scrollTo, setField, sleep,
  styleThePage, textOf, usable, visible, waitFor,
} from "./dom";
import { readRecord, type RestRecord, setPendingMove, type Then } from "./hub";


/** Whether this build stops the visitor's own press of "Enviar" (a preview). */

export interface RunResult {
  ok: boolean;
  error?: string;
  /** For a move the brain waits on: what is on screen now, in English. */
  detail?: string;
  /** The move goes on on another page, which reports it from there. */
  moved?: boolean;
  /** A read's answer: `admission_read`, `program_read`. */
  event?: AppEvent;
}

/** What the extension lends the adapter. Defaults work in the extension; the
 *  page test replaces them. */
export interface Hooks {
  /** The site's REST record of a career or programme, by the service worker. */
  rest(kind: "carrera" | "programa", slug: string): Promise<RestRecord | null>;
  /** Hold the visitor's microphone muted (`true`) while the audiomalla
   *  plays, so the call does not take the recording for the visitor. */
  holdMic(on: boolean): void;
  /** Keep a move for this tab's next page. */
  pend(then: Then): Promise<boolean>;
  /** Load another page in this tab. */
  load(url: string): void;
}

export interface Adapter {
  /** Perform one of the brain's page Actions. Never throws. */
  run(command: string, payload: unknown): Promise<RunResult>;
  /** What the visitor is looking at now, as a `page_changed` payload. */
  context(): PageChanged;
  /** Report the page, and what the visitor does on it, through `emit`, until
   *  the returned stop. The page as it stands is reported first. */
  start(emit: (event: string, payload: unknown) => void): () => void;
  /** The Actions `run` performs. */
  readonly commands: readonly string[];
  /** What on the page the widget should keep clear of now. */
  obstacles(): Element[];
  configure(hooks: Partial<Hooks>): void;
}

declare global {
  interface Window {
    voqalizeUah?: Adapter;
    bootstrap?: {
      Tab?: { getOrCreateInstance(el: Element): { show(): void } };
      Collapse?: { getOrCreateInstance(el: Element, config?: { toggle?: boolean }): { show(): void } };
    };
  }
}

const MAX_HEADINGS = 80;
const MAX_TOGGLES = 60;
const MAX_FAQS = 120;
const MAX_CARDS = 80;
/** How many labels a failure lists, so the model can try one that is there. */
const MAX_LISTED = 20;
const REST_DEADLINE_MS = 4500;
/** Where a move is kept for the next page when there is no hub (the console). */
export const PENDING_KEY = "voqalize.uahurtado.pending";
const PENDING_MAX_AGE_MS = 60_000;

const hooks: Hooks = {
  rest: (kind, slug) => readRecord(kind, slug),
  holdMic: () => {},
  pend: async (then) => {
    if (await setPendingMove(then)) return true;
    try {
      sessionStorage.setItem(PENDING_KEY, JSON.stringify({ then, at: Date.now() }));
      return true;
    } catch {
      return false;
    }
  },
  load: (url) => location.assign(url),
};

/** The move a page of this origin left without the hub, once. */
export function takeLocalPending(): Then | null {
  try {
    const raw = sessionStorage.getItem(PENDING_KEY);
    sessionStorage.removeItem(PENDING_KEY);
    if (!raw) return null;
    const kept = JSON.parse(raw) as { then?: Then; at?: number };
    return kept.then && typeof kept.at === "number" && Date.now() - kept.at < PENDING_MAX_AGE_MS ? kept.then : null;
  } catch {
    return null;
  }
}

const list = (items: string[]) => items.slice(0, MAX_LISTED).join(" | ") || "nothing";

// ─── Hosts and pages ──────────────────────────────────────────────────────

const UAH_HOST = /^((admision|postgrados|www)\.)?uahurtado\.cl$/i;
const ADMISION = "admision.uahurtado.cl";
const POSTGRADOS = "postgrados.uahurtado.cl";

/** `url` as a page of one of the three sites, or an error naming the rule. */
function siteUrl(url: unknown): URL {
  if (typeof url !== "string" || !url.trim()) throw new Error("say which page, as a full https URL on a uahurtado.cl site");
  let u: URL;
  try {
    u = new URL(url.trim(), location.href);
  } catch {
    throw new Error(`"${url}" is not a URL`);
  }
  if (u.protocol !== "https:" || !UAH_HOST.test(u.host)) {
    throw new Error(`${u.href} is not on admision., postgrados. or www.uahurtado.cl; only those pages open here`);
  }
  return u;
}

const hostKey = (h: string) => (h.toLowerCase() === "uahurtado.cl" ? "www.uahurtado.cl" : h.toLowerCase());
const pathKey = (p: string) => (p || "/").replace(/\/+$/, "").toLowerCase() || "/";

/** Whether `u` is the page in front: same host (bare is www), path and query. */
export function samePage(u: URL): boolean {
  return (
    hostKey(u.host) === hostKey(location.host) &&
    pathKey(u.pathname) === pathKey(location.pathname) &&
    u.search === location.search
  );
}

/** Whether `url` names another page than the one in front. */
export function elsewhere(url: string): boolean {
  try {
    return !samePage(new URL(url, location.href));
  } catch {
    return false;
  }
}

/** This page, as the brain names pages: its whole URL without the hash. */
const here = () => location.href.split("#")[0];

/** A move that needs the page `url`: when another page is in front, keep the
 *  move for that page and load it; `null` when the page is this one. */
async function onPage(url: URL, command: string, payload: unknown): Promise<RunResult | null> {
  if (samePage(url)) return null;
  await hooks.pend({ command, payload });
  clearHighlight();
  hooks.load(url.href);
  return { ok: true, moved: true };
}

function kind(): PageChanged["kind"] {
  const host = hostKey(location.host);
  const path = location.pathname;
  if (host === ADMISION && /^\/carreras\/[^/]+\/?$/i.test(path)) return "career";
  if (host === POSTGRADOS && /^\/programa\/[^/]+\/?$/i.test(path)) return "program";
  if (pathKey(path) === "/") return "home";
  if (host === POSTGRADOS && /^\/(especialidad|areas_estudio|facultades|doctorados|magister-online)(\/|$)/i.test(path)) {
    return "listing";
  }
  return "page";
}

const slugOfPath = () => location.pathname.split("/").filter(Boolean)[1] ?? "";

/** Chrome translated the page: its words may not be the site's. */
function translated(): boolean {
  const html = document.documentElement;
  if (html.classList.contains("translated-ltr") || html.classList.contains("translated-rtl")) return true;
  const was = html.getAttribute("data-voqalize-lang");
  return was !== null && was !== "" && html.lang !== "" && norm(html.lang) !== norm(was);
}

// ─── What the page shows ──────────────────────────────────────────────────

/** Not the page's content: the header and its menus (the Carreras mega-menu
 *  is opened by `open_career_menu` only), the side menu, the footer, modals,
 *  breadcrumbs, UserWay, and our own. */
const CHROME = [
  "header", "footer", "nav", "#sideMenu", "#overlay", ".modal", "#MenuCarreras", "#breadcrumbs", ".menu-top",
  ".principal3", ".mobail", ".bandatop", ".info-footer", ".dropdown-menu", ".uwy", "[data-voqalize]",
].join(", ");
const inChrome = (el: Element) => Boolean(el.closest(CHROME));

const label = (el: Element) => clean((el as HTMLElement).innerText || el.textContent);

const byRef = (ref: string | null): HTMLElement | null => {
  if (!ref || !ref.startsWith("#") || ref.length < 2) return null;
  try {
    return document.querySelector<HTMLElement>(ref);
  } catch {
    return null;
  }
};

interface Head {
  el: HTMLElement;
  text: string;
}

/** What a landmark with no words of its own is called. */
function landmarkName(el: HTMLElement): string | null {
  if (el.tagName === "IFRAME") {
    const src = (el as HTMLIFrameElement).src || el.getAttribute("data-src") || "";
    if (/google\.[a-z.]+\/maps|maps\.google\./i.test(src)) return "Mapa";
    if (/vimeo|youtube|youtu\.be/i.test(src)) return "Video";
    return null;
  }
  if (el.matches("form#admisionForm")) return "Formulario";
  if (el.tagName === "AUDIO" && el.closest("#malla")) return "Audiomalla";
  return null;
}

/** Section headings, in page order: h1–h5 laid out at this width, or in a
 *  closed tab pane or collapse (opened when shown); not a card's title, not an
 *  accordion's own header (that is a toggle); then the landmarks. */
function headingEls(): Head[] {
  const found: Head[] = [];
  for (const h of document.body.querySelectorAll<HTMLElement>("h1, h2, h3, h4, h5")) {
    if (inChrome(h) || !usable(h)) continue;
    if (h.matches(".card-title, .accordion-header") || h.querySelector("[data-bs-toggle]")) continue;
    if (h.closest(".card") && h.closest(".card-body") && h.matches("h2, h5")) continue;
    if (h.parentElement?.closest("h1, h2, h3, h4, h5")) continue;
    const text = label(h);
    if (text.length > 1 && text.length <= 200) found.push({ el: h, text });
  }
  for (const el of document.body.querySelectorAll<HTMLElement>("iframe, form#admisionForm, #malla audio")) {
    if (inChrome(el) || !usable(el)) continue;
    const name = landmarkName(el);
    if (name) found.push({ el, text: name });
  }
  found.sort((a, b) => inOrder(a.el, b.el));
  return dedupe(found, (h) => h.text, (h) => h.el);
}

/** One per label, the laid-out copy over a hidden twin. */
function dedupe<T>(items: T[], text: (t: T) => string, el: (t: T) => Element): T[] {
  const byKey = new Map<string, T>();
  for (const i of items) {
    const k = norm(text(i));
    const had = byKey.get(k);
    if (!had || (!visible(el(had)) && visible(el(i)))) byKey.set(k, i);
  }
  return items.filter((i) => byKey.get(norm(text(i))) === i);
}

interface Toggle {
  el: HTMLElement;
  label: string;
  pane: HTMLElement;
  kind: "tab" | "collapse";
}

const TOGGLE_SEL = [
  "[data-bs-toggle=tab]", "[data-bs-toggle=pill]", "[data-bs-toggle=collapse]",
  "[data-toggle=tab]", "[data-toggle=pill]", "[data-toggle=collapse]",
].join(", ");

const isQuestion = (s: string) => /\?\s*$/.test(s) || /^\s*¿/.test(s);

function triggers(): Toggle[] {
  const out: Toggle[] = [];
  for (const el of document.body.querySelectorAll<HTMLElement>(TOGGLE_SEL)) {
    if (inChrome(el) || !usable(el)) continue;
    const pane = byRef(el.getAttribute("data-bs-target") ?? el.getAttribute("data-target") ?? el.getAttribute("href"));
    const text = label(el);
    if (!pane || !text) continue;
    const how = el.getAttribute("data-bs-toggle") ?? el.getAttribute("data-toggle");
    out.push({ el, label: text, pane, kind: how === "collapse" ? "collapse" : "tab" });
  }
  return out;
}

/** Tab, pill and accordion labels: a `show` on one opens it. Questions in an
 *  accordion are FAQs, not toggles. */
function toggles(): Toggle[] {
  return dedupe(
    triggers().filter((t) => t.kind === "tab" || !isQuestion(t.label)),
    (t) => t.label,
    (t) => t.el,
  );
}

interface Faq {
  question: string;
  block: HTMLElement;
  toggle: Toggle | null;
  isOpen: () => boolean;
  answer: () => HTMLElement[];
}

function faqItems(): Faq[] {
  const items: Faq[] = [];
  for (const t of triggers()) {
    if (t.kind !== "collapse" || !isQuestion(t.label)) continue;
    items.push({
      question: t.label,
      block: t.el.closest<HTMLElement>(".accordion-header, h2, h3, h4") ?? t.el,
      toggle: t,
      isOpen: () => t.pane.classList.contains("show"),
      answer: () => [t.pane],
    });
  }
  // A question set as a heading, its answer the blocks under it (/gratuidad-
  // universitaria/'s "¿Qué estudiantes pueden acceder…?").
  for (const h of document.body.querySelectorAll<HTMLElement>("h2, h3, h4")) {
    if (inChrome(h) || h.matches(".accordion-header") || h.querySelector("[data-bs-toggle]") || !usable(h)) continue;
    const q = label(h);
    if (!isQuestion(q) || q.length > 200) continue;
    const els: HTMLElement[] = [];
    for (let n = h.nextElementSibling; n && els.length < 6; n = n.nextElementSibling) {
      if (!(n instanceof HTMLElement) || /^H[1-4]$/.test(n.tagName) || n.matches(".accordion")) break;
      if (clean(n.textContent)) els.push(n);
    }
    if (!els.length) continue;
    items.push({ question: q, block: h, toggle: null, isOpen: () => true, answer: () => els });
  }
  for (const d of document.body.querySelectorAll<HTMLDetailsElement>("details")) {
    const summary = d.querySelector<HTMLElement>("summary");
    if (!summary || inChrome(d)) continue;
    items.push({ question: label(summary), block: d, toggle: null, isOpen: () => d.open, answer: () => [d] });
  }
  items.sort((a, b) => inOrder(a.block, b.block));
  return dedupe(
    items.filter((i) => i.question),
    (i) => i.question,
    (i) => i.block,
  );
}

const CARD_TITLE = ".card-title, .card .card-body > h2, .card .card-body > h3";

function cardTitles(): HTMLElement[] {
  return [...document.body.querySelectorAll<HTMLElement>(CARD_TITLE)].filter((el) => !inChrome(el) && usable(el));
}

function cards(): string[] {
  return dedupe(cardTitles(), label, (e) => e).map(label).filter(Boolean).slice(0, MAX_CARDS);
}

// ─── A career page ────────────────────────────────────────────────────────

/** Two-cell rows of a table, as `label → value`: `th`/`td` or `td`/`td`. */
function rows(table: Element | null | undefined, skipHeader = false): Row[] {
  if (!table) return [];
  const out: Row[] = [];
  for (const tr of table.querySelectorAll("tr")) {
    const cells = [...tr.querySelectorAll("th, td")];
    if (cells.length < 2) continue;
    const row = { label: clean(cells[0].textContent), value: clean(cells[1].textContent) };
    if (!row.label) continue;
    if (skipHeader && norm(row.label) === "criterio" && norm(row.value) === "porcentaje") continue;
    out.push(row);
  }
  return out;
}

interface AdmissionColumns {
  /** The "Aranceles" column, and the PAES requirements column. */
  fees: HTMLElement | null;
  requirements: HTMLElement | null;
}

function admissionColumns(): AdmissionColumns {
  const pane = document.getElementById("requisitos_carrera");
  const row = pane?.querySelector<HTMLElement>(".row");
  const cols = row ? ([...row.children].filter((c) => /\bcol/.test(c.className)) as HTMLElement[]) : [];
  const fees =
    cols.find((c) => [...c.querySelectorAll("h2, h3, h4")].some((h) => norm(h.textContent).startsWith("arancel"))) ??
    cols[1] ??
    null;
  return { fees, requirements: cols.find((c) => c !== fees) ?? null };
}

/** The Aranceles column's text, from its heading to the next heading (an
 *  "Admisión Directa" note follows it on some careers). */
function feesText(col: HTMLElement | null): string {
  if (!col) return "";
  const head = [...col.querySelectorAll<HTMLElement>("h2, h3, h4")].find((h) => norm(h.textContent).startsWith("arancel"));
  if (!head) return textOf(col);
  const parts: string[] = [];
  for (let n = head.nextElementSibling; n; n = n.nextElementSibling) {
    if (/^H[1-4]$/.test(n.tagName)) break;
    parts.push(textOf(n));
  }
  return parts.filter(Boolean).join("\n");
}

/** The requirements column as words, when it is a list rather than a table
 *  (online and continuity careers). */
function requirementsText(col: HTMLElement | null): string {
  if (!col || col.querySelector("table")) return "";
  return [...col.children]
    .filter((c) => !/^H[1-4]$/.test(c.tagName))
    .map((c) => textOf(c))
    .filter(Boolean)
    .join("\n");
}

interface Fees {
  year: string;
  matricula: string;
  arancel: string;
  titulacion_uf: string;
}

/** The page's own light parse of the fees, as written ("$277.456"); the brain
 *  parses `fees_text` itself and takes its own figures. */
export function parseFees(text: string): Fees {
  const money = (re: RegExp) => {
    const m = re.exec(text);
    return m ? `$${m[1].replace(/[.,]$/, "")}` : "";
  };
  return {
    year: /A[ñn]o\s*(20\d\d)/i.exec(text)?.[1] ?? "",
    matricula: money(/Matr[ií]cula[^$\d]*\$\s?([\d.]+)/i),
    arancel: money(/Arancel(?:\s+anual)?[^$\d]*\$\s?([\d.]+)/i),
    titulacion_uf: /Titulaci[oó]n\s*(\d+(?:[.,]\d+)?)\s*UF/i.exec(text)?.[1] ?? "",
  };
}

function careerTabs(): HTMLElement[] {
  const nav = document.querySelector("#ficha-carrera-tabs") ?? document.querySelector("#cuerpo-carrera .nav-pills");
  return nav ? [...nav.querySelectorAll<HTMLElement>("[role=tab], .nav-link")].filter((t) => usable(t)) : [];
}

function careerSheet(): CareerSheet {
  const audio = document.querySelector<HTMLAudioElement>("#malla audio");
  let audioLabel = "";
  if (audio) {
    for (let n = audio.previousElementSibling; n; n = n.previousElementSibling) {
      if (n.tagName === "P" && clean(n.textContent)) {
        audioLabel = clean(n.textContent);
        break;
      }
    }
  }
  const { fees, requirements } = admissionColumns();
  const table = requirements?.querySelector("table");
  return {
    slug: slugOfPath(),
    name: label(document.querySelector("#cabeza-carrera h1") ?? document.querySelector("h1") ?? document.body).slice(0, 160),
    facts: rows(document.querySelector("#malla table")),
    tabs: careerTabs().map(label).filter(Boolean),
    has_audiomalla: Boolean(audio),
    audiomalla_label: audioLabel,
    malla_pdf: document.querySelector<HTMLAnchorElement>("#malla a[href$='.pdf' i]")?.href ?? "",
    fees_text: feesText(fees),
    weights: rows(table, true),
    requirements_text: requirementsText(requirements),
  };
}

// ─── A postgraduate programme ─────────────────────────────────────────────

/** The sidebar's `h3` blocks: each heading, then the text under it to the
 *  next heading (Postulaciones → "Postulación desde: 01 octubre 2026; …"). */
function sidebarRows(): Row[] {
  const side =
    document.querySelector<HTMLElement>("#cuerpo-carrera > .row > .col-md-4") ??
    document.querySelector<HTMLElement>("#cuerpo-carrera .col-md-4");
  if (!side) return [];
  const out: Row[] = [];
  for (const h of side.querySelectorAll<HTMLElement>("h3")) {
    const parts: string[] = [];
    for (let n = h.nextElementSibling; n; n = n.nextElementSibling) {
      if (n.tagName === "H3" || n.querySelector("h3")) break;
      parts.push(textOf(n));
    }
    const value = parts.join("\n").split("\n").map(clean).filter(Boolean).join("; ");
    if (label(h)) out.push({ label: label(h), value });
  }
  return out;
}

function programSheet(): ProgramSheet {
  const req = document.getElementById("collapseRequisitos");
  return {
    slug: slugOfPath(),
    name: label(document.querySelector("#cabeza-carrera h1") ?? document.querySelector("h1") ?? document.body).slice(0, 160),
    requisitos_text: textOf(req?.querySelector(".accordion-body") ?? req),
    sidebar: sidebarRows(),
    accordion: [...document.querySelectorAll<HTMLElement>("#programaAccordion [data-bs-target]")].map(label).filter(Boolean),
  };
}

// ─── Visits ───────────────────────────────────────────────────────────────

interface Visit {
  card: HTMLElement;
  info: VisitCard;
  link: HTMLAnchorElement | null;
}

function visitCards(): Visit[] {
  const out: Visit[] = [];
  for (const card of document.body.querySelectorAll<HTMLElement>(".card")) {
    if (inChrome(card) || !usable(card)) continue;
    const titleEl = card.querySelector(".card-title");
    const foot = card.querySelector(".mt-auto");
    if (!titleEl || !foot) continue;
    const text = textOf(card.querySelector(".card-text")).split("\n").join(" ");
    const link =
      [...foot.querySelectorAll<HTMLAnchorElement>("a[href]")].find((a) => /inscrib/.test(norm(a.textContent))) ?? null;
    const closed = foot.querySelector("button");
    out.push({
      card,
      link,
      info: {
        title: label(titleEl),
        text,
        done: /\brealizad[oa]\b/.test(norm(text)),
        open: Boolean(link),
        signup_label: clean(link?.textContent ?? closed?.textContent),
        signup_url: link?.href ?? "",
      },
    });
  }
  return out;
}

// ─── The lead form ────────────────────────────────────────────────────────

type Key = "nombre" | "apellido" | "rut" | "email" | "fono" | "consulta" | "carrera" | "via";
const KEYS: Key[] = ["nombre", "apellido", "rut", "email", "fono", "consulta", "carrera", "via"];

/** The form's fields by the names it carries (Google Forms entry ids; the
 *  admision and the postgrados variants), else its `data-type`, else the
 *  words of its placeholder. */
const FIELDS: Record<Key, { names: string[]; placeholder: RegExp }> = {
  nombre: { names: ["entry.230062511", "entry.1144887674"], placeholder: /^nombre/ },
  apellido: { names: ["entry.721330585", "entry.109783613"], placeholder: /^apellido/ },
  rut: { names: ["entry.289307241", "entry.1588796281"], placeholder: /^rut\b/ },
  email: { names: ["entry.1559668481", "entry.67282623"], placeholder: /^(e-?mail|correo)/ },
  fono: { names: ["entry.916683147", "entry.180136099"], placeholder: /^(fono|telefono|celular)/ },
  consulta: { names: ["entry.699238472"], placeholder: /^consulta/ },
  carrera: { names: ["entry.229701830", "entry.1620538324"], placeholder: /^(carrera|programa)/ },
  via: { names: ["entry.12342908"], placeholder: /^via\b/ },
};

type Field = HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement;

function leadForm(): HTMLFormElement | null {
  const forms = [...document.querySelectorAll<HTMLFormElement>("form#admisionForm")];
  return forms.find((f) => visible(f)) ?? forms[0] ?? null;
}

function field(form: HTMLFormElement, key: Key): Field | null {
  for (const name of FIELDS[key].names) {
    const el = form.querySelector<Field>(`[name="${name}"]`);
    if (el) return el;
  }
  const typed = form.querySelector<Field>(`[data-type="${key}"]`);
  if (typed) return typed;
  for (const el of form.querySelectorAll<Field>("input, textarea")) {
    if (FIELDS[key].placeholder.test(norm(el.getAttribute("placeholder")))) return el;
  }
  return null;
}

/** A select's real choices: not its "Seleccione…" / "Vía de Admisión" prompt. */
function choices(select: HTMLSelectElement): HTMLOptionElement[] {
  return [...select.options].filter((o, i) => {
    const t = norm(o.text);
    if (!t || (o.hasAttribute("value") && o.value === "")) return false;
    return !(i === 0 && /^(seleccion|elige|via de admision|carrera$|programa$)/.test(t));
  });
}

const isPrompt = (select: HTMLSelectElement) => !choices(select).includes(select.options[select.selectedIndex]);

function filledValue(el: Field): string {
  if (el instanceof HTMLSelectElement) return isPrompt(el) ? "" : clean(el.options[el.selectedIndex]?.text);
  return clean(el.value);
}

const isRequired = (el: Field) => el.required || el.hasAttribute("required");

/** A Chilean RUT whose check digit is right ("12.345.678-5"). */
export function rutValid(raw: string): boolean {
  const s = raw.replace(/[.\s-]/g, "").toUpperCase();
  const m = /^(\d{6,8})([\dK])$/.exec(s);
  if (!m) return false;
  let sum = 0;
  let mul = 2;
  for (let i = m[1].length - 1; i >= 0; i--) {
    sum += Number(m[1][i]) * mul;
    mul = mul === 7 ? 2 : mul + 1;
  }
  const dv = 11 - (sum % 11);
  return m[2] === (dv === 11 ? "0" : dv === 10 ? "K" : String(dv));
}

function formInfo(): LeadFormInfo | null {
  const form = leadForm();
  if (!form) return null;
  const present = KEYS.filter((k) => field(form, k));
  const career = field(form, "carrera");
  const via = field(form, "via");
  return {
    fields: present,
    career_options: career instanceof HTMLSelectElement ? choices(career).map((o) => clean(o.text)) : [],
    via_options: via instanceof HTMLSelectElement ? choices(via).map((o) => clean(o.text)) : [],
    career: career ? filledValue(career) : "",
    filled: present.filter((k) => filledValue(field(form, k)!)),
  };
}

function formState(): Required<LeadFormState> | null {
  const form = leadForm();
  if (!form) return null;
  const filled: string[] = [];
  const missing: string[] = [];
  const invalid: string[] = [];
  for (const k of KEYS) {
    const el = field(form, k);
    if (!el) continue;
    const v = filledValue(el);
    if (v) filled.push(k);
    else if (isRequired(el) || k === "rut") missing.push(k);
    if (!v) continue;
    if (k === "email" && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v)) invalid.push(k);
    if (k === "fono" && v.replace(/\D/g, "").length < 8) invalid.push(k);
    if (k === "rut" && !rutValid(v)) invalid.push(k);
  }
  const career = field(form, "carrera");
  return {
    filled,
    missing,
    invalid,
    career: career ? filledValue(career) : "",
    ready: !missing.length && !invalid.length,
  };
}

/** When Javier last filled the form, for the widget to keep clear of it. */
let lastFill = 0;
/** Set while Javier types, so his own events are not taken for the visitor's. */
let filling = false;

async function fillLeadForm(p: FillLeadForm): Promise<RunResult> {
  const form = leadForm();
  if (!form) {
    throw new Error(
      "this page has no lead form (#admisionForm); every career page has one in its header, and so do the admision home and most admision pages",
    );
  }
  filling = true;
  lastFill = Date.now();
  const done: string[] = [];
  const notes: string[] = [];
  try {
    await scrollTo(form, "center");
    for (const k of ["nombre", "apellido", "email", "fono", "consulta"] as const) {
      const value = p[k];
      if (value === null || value === undefined || !String(value).trim()) continue;
      const el = field(form, k);
      if (!el) {
        notes.push(`this form has no ${k} field`);
        continue;
      }
      setField(el, String(value).trim());
      done.push(k);
    }
    for (const k of ["carrera", "via"] as const) {
      const said = p[k];
      if (!said || !said.trim()) continue;
      const el = field(form, k);
      if (!el) {
        notes.push(`this form has no ${k === "via" ? "vía de admisión" : "career"} field`);
        continue;
      }
      if (el instanceof HTMLSelectElement) {
        const opts = choices(el);
        const opt = best(opts, (o) => o.text, said) ?? best(opts, (o) => loose(o.text), loose(said));
        if (!opt) {
          notes.push(`no ${k} "${said}" in the form's list; it has: ${list(opts.map((o) => clean(o.text)))}`);
          continue;
        }
        setField(el, opt.value);
        done.push(`${k} (${clean(opt.text)})`);
      } else if (norm(el.value) !== norm(said)) {
        // A career page's form is for that career: its hidden field says so.
        notes.push(`this form is for ${el.value || "this page's career"}; it has no ${k} to choose`);
      }
    }
    const state = formState()!;
    emitNow("lead_form_state", state);
    const rut = field(form, "rut");
    const send = form.querySelector<HTMLElement>("button[type=submit], input[type=submit]");
    if (p.focus_rut && rut) {
      await scrollTo(rut, "center");
      highlight(rut);
      rut.focus({ preventScroll: true });
    } else if (state.missing.every((k) => k === "rut") && !state.invalid.length && send) {
      // Everything but the RUT is in: "Enviar" is the visitor's to press.
      highlight(rut && state.missing.includes("rut") ? [rut] : [], send);
    } else {
      const first = state.missing.map((k) => field(form, k as Key)).find((el) => el && visible(el));
      highlight(first ?? form);
    }
    const parts = [
      done.length ? `filled ${done.join(", ")}` : "filled nothing",
      state.missing.length ? `still empty: ${state.missing.join(", ")}` : "every field is filled",
      state.invalid.length ? `looks wrong: ${state.invalid.join(", ")}` : "",
      ...notes,
      p.focus_rut ? "the RUT field is rung and focused for the visitor to type" : "",
      state.missing.every((k) => k === "rut") && !state.invalid.length ? '"Enviar" is the visitor\'s to press' : "",
    ];
    return { ok: true, detail: parts.filter(Boolean).join("; ") };
  } finally {
    // The page's own handlers run on the events just sent; let them pass.
    setTimeout(() => {
      filling = false;
    }, 50);
  }
}

/** Follow the visitor typing in the form, and their press of "Enviar". */
function watchForm(): void {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let last = "";
  const typed = (e: Event) => {
    if (filling || !(e.target instanceof Element) || !e.target.closest("form#admisionForm")) return;
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      const state = formState();
      const key = JSON.stringify(state);
      if (!state || key === last) return;
      last = key;
      emitNow("lead_form_state", state);
    }, 900);
  };
  document.addEventListener("input", typed, true);
  document.addEventListener("change", typed, true);

  // "Enviar" is the visitor's: their press goes to the university as it
  // always does, and is only reported. The submit event covers Enter too. It
  // is reported once the site's own handlers have run, and only if none of
  // them stopped it (the RUT check digit is validated on submit).
  let pressedAt = 0;
  window.addEventListener(
    "submit",
    (e) => {
      if ((e.target as HTMLFormElement | null)?.id !== "admisionForm") return;
      setTimeout(() => {
        const now = Date.now();
        if (e.defaultPrevented || now - pressedAt < 800) return;
        pressedAt = now;
        emitNow("lead_submitted", {});
      }, 0);
    },
    true,
  );
}

// ─── Opening what is closed ───────────────────────────────────────────────

const isOpenPane = (pane: Element) =>
  pane.matches(".tab-pane") ? pane.classList.contains("active") : pane.classList.contains("show");

const triggerFor = (pane: HTMLElement) =>
  pane.id
    ? document.querySelector<HTMLElement>(
        `[data-bs-target="#${CSS.escape(pane.id)}"], [data-target="#${CSS.escape(pane.id)}"], [href="#${CSS.escape(pane.id)}"][data-bs-toggle]`,
      )
    : null;

/** Open a tab pane or a collapse the way the site's Bootstrap does, and wait
 *  for it to show (its fade or slide included). */
async function openPane(pane: HTMLElement, trigger: HTMLElement | null = triggerFor(pane)): Promise<boolean> {
  if (isOpenPane(pane) && !pane.classList.contains("collapsing")) return true;
  const bs = window.bootstrap;
  if (pane.matches(".tab-pane")) {
    if (!trigger) return false;
    if (bs?.Tab) bs.Tab.getOrCreateInstance(trigger).show();
    else trigger.click();
    const ok = await waitFor(() => pane.classList.contains("active") && laidOut(pane), 2500);
    await waitFor(() => !pane.classList.contains("fade") || pane.classList.contains("show"), 600);
    return Boolean(ok);
  }
  if (bs?.Collapse) bs.Collapse.getOrCreateInstance(pane, { toggle: false }).show();
  else if (trigger) trigger.click();
  else return false;
  const ok = await waitFor(() => pane.classList.contains("show") && !pane.classList.contains("collapsing"), 3000);
  return Boolean(ok);
}

/** Open every closed pane `el` sits in, outermost first. */
async function reveal(el: Element): Promise<void> {
  const closed: HTMLElement[] = [];
  for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
    if (p.matches(".tab-pane:not(.active), .collapse:not(.show)")) closed.unshift(p);
  }
  for (const pane of closed) await openPane(pane);
}

// ─── navigate, show_section, open_faq ─────────────────────────────────────

/** What a heading heads, to ring together: a landmark itself; a card's title,
 *  its card; else it and the blocks under it to the next heading. */
function sectionOf(h: HTMLElement): HTMLElement[] {
  if (landmarkName(h)) return [h];
  const card = h.closest<HTMLElement>(".card");
  if (card && h.matches(CARD_TITLE)) return [card];
  const level = /^H(\d)$/.exec(h.tagName)?.[1];
  const out = [h];
  for (let n = h.nextElementSibling; n && out.length < 10; n = n.nextElementSibling) {
    if (!(n instanceof HTMLElement)) continue;
    const l = /^H(\d)$/.exec(n.tagName)?.[1];
    if (l && level && Number(l) <= Number(level)) break;
    if (l && !level) break;
    if (visible(n)) out.push(n);
  }
  if (out.length > 1) return out;
  const parent = h.parentElement;
  return parent && parent !== document.body && clean(parent.textContent).length < 2000 ? [parent] : [h];
}

/** The smallest element in `root` whose text holds `text`, laid out or in a
 *  pane the adapter can open. */
function smallestContaining(root: Element, text: string): HTMLElement | null {
  const want = norm(text);
  if (!want) return null;
  let found: HTMLElement | null = null;
  let bestLen = Infinity;
  for (const el of root.querySelectorAll<HTMLElement>("*")) {
    if (inChrome(el) || /^(SCRIPT|STYLE|NOSCRIPT|svg|path)$/i.test(el.tagName) || !usable(el)) continue;
    const t = norm(el.textContent);
    if (!t.includes(want) || t.length >= bestLen) continue;
    found = el;
    bestLen = t.length;
  }
  if (found && /^(STRONG|B|EM|I|SPAN|A)$/.test(found.tagName)) {
    const p = found.closest<HTMLElement>("p, li, td, h1, h2, h3, h4, h5");
    if (p && clean(p.textContent).length < 400) return p;
  }
  return found;
}

/** Ring a block, or its heading when it is taller than most of the screen. */
function ringBlock(block: HTMLElement[], head: HTMLElement): void {
  const box = boxOf(block);
  highlight(box && box.bottom - box.top > window.innerHeight * 0.75 ? head : block);
}

async function showToggle(t: Toggle): Promise<void> {
  await reveal(t.el);
  await openPane(t.pane, t.el);
  if (t.kind === "tab") {
    await scrollTo(t.pane, "top");
    const first = t.pane.querySelector<HTMLElement>("h1, h2, h3, h4");
    ringBlock([t.pane], first ?? t.el);
  } else {
    const item = t.el.closest<HTMLElement>(".accordion-item") ?? t.el;
    await scrollTo(item, "top");
    ringBlock([item], t.el);
  }
}

async function showSection({ heading, text }: Partial<ShowSection>): Promise<void> {
  if (!heading && !text) throw new Error("say which heading, tab or text to show");
  let scope: HTMLElement[] = [];
  if (heading) {
    const tog = best(toggles(), (t) => t.label, heading, (t) => t.el);
    const head = best(headingEls(), (h) => h.text, heading, (h) => h.el);
    const card = best(cardTitles(), label, heading, (e) => e);
    const exact = (s: string) => norm(s) === norm(heading);
    const useToggle = tog && (exact(tog.label) || !head || !exact(head.text));
    if (useToggle && tog) {
      if (!text) return showToggle(tog);
      await showToggle(tog);
      scope = [tog.pane];
    } else if (head) {
      await reveal(head.el);
      await scrollTo(head.el, "top");
      const section = sectionOf(head.el);
      if (!text) {
        const top = section.filter(visible).sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top)[0];
        const box = boxOf(section);
        if (top && box && box.bottom - box.top <= window.innerHeight - headerHeight() - 32) await scrollTo(top, "top");
        return ringBlock(section, head.el);
      }
      scope = section;
    } else if (card) {
      const box = card.closest<HTMLElement>(".card") ?? card;
      await reveal(box);
      await scrollTo(box, "center");
      if (!text) return highlight(box);
      scope = [box];
    } else if (!text) {
      const known = [...toggles().map((t) => t.label), ...headingEls().map((h) => h.text)];
      throw new Error(`no heading or tab "${heading}" on ${location.pathname}; it has: ${list(known)}`);
    }
  }
  const find = () => {
    for (const s of scope) {
      const el = smallestContaining(s, text!);
      if (el) return el;
    }
    return smallestContaining(document.body, text!);
  };
  const el = find();
  if (!el) throw new Error(`"${text}" is not on ${location.pathname}`);
  await reveal(el);
  const tall = el.getBoundingClientRect().height > window.innerHeight * 0.7;
  await scrollTo(el, tall ? "top" : "center");
  highlight(el);
}

async function openFaq({ question }: Partial<OpenFaq>): Promise<void> {
  const all = faqItems();
  const item = best(all, (f) => f.question, question ?? "", (f) => f.block);
  if (!item) throw new Error(`no FAQ "${question}" on ${location.pathname}; it has: ${list(all.map((f) => f.question))}`);
  await reveal(item.block);
  await scrollTo(item.block, "center");
  if (!item.isOpen() && item.toggle) await openPane(item.toggle.pane, item.toggle.el);
  await sleep(150);
  const group = [item.block, ...item.answer()];
  const box = boxOf(group);
  const tall = box ? box.bottom - box.top > window.innerHeight * 0.7 : false;
  await scrollTo(item.block, tall ? "top" : "center");
  highlight(group);
}

async function navigate(p: Partial<Navigate> & { via_cue?: boolean }): Promise<RunResult> {
  const url = siteUrl(p.url);
  if (!samePage(url)) {
    if (p.heading || p.text || p.faq) {
      // `via_cue`: a cue's move, whose miss on the next page is the cue's.
      const rest = { url: url.href, heading: p.heading ?? null, text: p.text ?? null, faq: p.faq ?? null };
      return (await onPage(url, "navigate", p.via_cue ? { ...rest, via_cue: true } : rest))!;
    }
    clearHighlight();
    hooks.load(url.href);
    return { ok: true, moved: true };
  }
  try {
    if (p.faq) await openFaq({ question: p.faq });
    else if (p.heading || p.text) await showSection({ heading: p.heading, text: p.text });
    else {
      window.scrollTo({ top: 0, behavior: "smooth" });
      await sleep(300);
    }
  } catch (error) {
    // On a page Chrome translated, the site's words may be gone: the page is
    // in front, which is the move; the section is skipped, not failed.
    if (!translated()) throw error;
  }
  emitNow("page_changed", context());
  return { ok: true };
}

// ─── The Carreras mega-menu ───────────────────────────────────────────────

/** A faculty's name as the visitor or the brain may say it: no "Facultad de". */
const faculty = (s: string) => norm(s).replace(/^(facultad|escuela)\s+(de\s+)?(la\s+|las\s+|los\s+|el\s+)?/, "");

async function openCareerMenu(p: Partial<OpenCareerMenu>): Promise<RunResult> {
  if (hostKey(location.host) !== ADMISION) {
    const url = siteUrl(p.url || "https://admision.uahurtado.cl/");
    if (hostKey(url.host) !== ADMISION) throw new Error(`the Carreras menu is on admision.uahurtado.cl, not ${url.host}`);
    await hooks.pend({ command: "open_career_menu", payload: { faculty: p.faculty ?? null, url: url.href } });
    clearHighlight();
    hooks.load(url.href);
    return { ok: true, moved: true };
  }
  const menu = document.getElementById("collapseCarreras");
  if (!menu) throw new Error("this admision page has no Carreras menu (#collapseCarreras)");
  if (!menu.classList.contains("show")) {
    const link = document.querySelector<HTMLElement>("#menu-menu-principal-1 > li.boton-carrera > a");
    if (window.bootstrap?.Collapse) window.bootstrap.Collapse.getOrCreateInstance(menu, { toggle: false }).show();
    else if (link) link.click();
    await waitFor(() => menu.classList.contains("show") && !menu.classList.contains("collapsing"), 3000);
  }
  if (!menu.classList.contains("show")) throw new Error("the Carreras menu did not open");
  const groups = [...menu.querySelectorAll<HTMLElement>("p")]
    .map((title) => {
      const next = title.nextElementSibling;
      const careers = next?.tagName === "UL" ? [...next.querySelectorAll("a")].map(label).filter(Boolean) : [];
      return { title, list: next as HTMLElement | null, name: label(title), careers };
    })
    .filter((g) => g.name && g.careers.length);
  await scrollTo(menu, "top");
  if (!p.faculty) {
    highlight(menu.querySelector<HTMLElement>(".accordion-body") ?? menu);
    return {
      ok: true,
      detail: `the Carreras menu is open, by faculty: ${groups.map((g) => `${g.name} (${g.careers.length})`).join("; ")}`,
    };
  }
  const g = best(groups, (x) => faculty(x.name), faculty(p.faculty), (x) => x.title);
  if (!g) {
    throw new Error(
      `the Carreras menu is open, but it has no group for "${p.faculty}"; its groups are: ${list(groups.map((x) => x.name))}`,
    );
  }
  const block = [g.title, ...(g.list ? [g.list] : [])];
  await scrollTo(g.title, "center");
  highlight(block);
  return { ok: true, detail: `the Carreras menu is open at ${g.name}, which lists: ${g.careers.join(" | ")}` };
}

// ─── The audiomalla ───────────────────────────────────────────────────────

/** While the audiomalla plays, the visitor's microphone is held muted; when it
 *  stops (it ended, or someone paused it) it is given back and the brain is
 *  told. A play the visitor starts themselves is held the same way. */
function watchAudio(): void {
  const audio = document.querySelector<HTMLAudioElement>("#malla audio");
  if (!audio) return;
  let playing = false;
  audio.addEventListener("play", () => {
    if (playing) return;
    playing = true;
    hooks.holdMic(true);
  });
  const stop = () => {
    // The end of the file fires `pause` and then `ended`: one report.
    setTimeout(() => {
      if (!playing || !audio.paused) return;
      playing = false;
      hooks.holdMic(false);
      emitNow("audiomalla_ended", { finished: audio.ended });
    }, 60);
  };
  audio.addEventListener("pause", stop);
  audio.addEventListener("ended", stop);
}

async function playAudiomalla(p: Partial<PlayAudiomalla>): Promise<RunResult> {
  const moved = await onPage(siteUrl(p.url), "play_audiomalla", { url: p.url });
  if (moved) return moved;
  const audio = await waitFor(() => document.querySelector<HTMLAudioElement>("#malla audio"), 2000);
  if (!audio) throw new Error("this career page has no audiomalla; it is on the Malla Curricular tab of careers that have one");
  await reveal(audio);
  const tab = document.getElementById("malla");
  if (tab) await openPane(tab);
  await scrollTo(audio, "center");
  highlight(audio);
  const who = careerSheet().audiomalla_label;
  try {
    await Promise.race([
      audio.play(),
      sleep(4000).then(() => {
        throw new Error("it did not start within 4 s");
      }),
    ]);
  } catch (error) {
    highlight(audio);
    const why = error instanceof Error ? error.message : String(error);
    throw new Error(`the browser did not let the audiomalla start (${why}); its play button is rung for the visitor to press`);
  }
  return {
    ok: true,
    detail: `the audiomalla is playing${who ? ` (${who})` : ""}; the visitor's microphone is muted until it ends`,
  };
}

// ─── The live reads ───────────────────────────────────────────────────────

async function record(kind: "carrera" | "programa", slug: string): Promise<RestRecord | null> {
  if (!slug) return null;
  try {
    return await Promise.race([hooks.rest(kind, slug), sleep(REST_DEADLINE_MS).then(() => null)]);
  } catch {
    return null;
  }
}

async function showAdmission(p: Partial<ShowAdmission>): Promise<RunResult> {
  const url = siteUrl(p.url);
  const moved = await onPage(url, "show_admission", { url: url.href, slug: p.slug, focus: p.focus ?? "fees" });
  if (moved) return moved;
  const tab = await waitFor(() => document.getElementById("requisitos_carrera-tab"), 2500);
  const pane = document.getElementById("requisitos_carrera");
  if (!tab || !pane) {
    throw new Error(
      `this page has no "Requisitos y Aranceles" tab; its tabs are: ${list(careerTabs().map(label))}`,
    );
  }
  if (!(await openPane(pane, tab))) throw new Error('the "Requisitos y Aranceles" tab did not open');
  const { fees, requirements } = admissionColumns();
  const target =
    p.focus === "requirements" ? (requirements?.querySelector<HTMLElement>("table") ?? requirements) : fees;
  if (target) {
    await scrollTo(target, "top");
    ringBlock([target], target.querySelector<HTMLElement>("h3") ?? target);
  }
  const slug = p.slug || slugOfPath();
  const sheet = careerSheet();
  const rec = await record("carrera", slug);
  return {
    ok: true,
    event: {
      event: "admission_read",
      payload: {
        slug,
        url: here(),
        fees_text: sheet.fees_text ?? "",
        ...parseFees(sheet.fees_text ?? ""),
        weights: sheet.weights ?? [],
        requirements_text: sheet.requirements_text ?? "",
        api_fees_text: rec?.fees_text ?? "",
        error: fees ? "" : "no Aranceles column on the tab",
      },
    },
  };
}

async function showProgram(p: Partial<ShowProgram>): Promise<RunResult> {
  const url = siteUrl(p.url);
  const moved = await onPage(url, "show_program", { url: url.href, slug: p.slug });
  if (moved) return moved;
  const pane = await waitFor(() => document.getElementById("collapseRequisitos"), 2500);
  if (!pane) {
    throw new Error(`this page has no "Requisitos y Valores" section; its sections are: ${list(programSheet().accordion ?? [])}`);
  }
  const trigger = document.querySelector<HTMLElement>('[data-bs-target="#collapseRequisitos"]');
  if (!(await openPane(pane, trigger))) throw new Error('"Requisitos y Valores" did not open');
  const item = pane.closest<HTMLElement>(".accordion-item") ?? pane;
  await scrollTo(item, "top");
  ringBlock([item], trigger ?? item);
  const slug = p.slug || slugOfPath();
  const sheet = programSheet();
  const rec = await record("programa", slug);
  return {
    ok: true,
    event: {
      event: "program_read",
      payload: {
        slug,
        url: here(),
        requisitos_text: sheet.requisitos_text ?? "",
        sidebar: sheet.sidebar ?? [],
        postulacion_desde: rec?.postulacion_desde ?? "",
        postulacion_hasta: rec?.postulacion_hasta ?? "",
        inicio_programa: rec?.inicio_programa ?? "",
        api_requisitos_text: rec?.requisitos_text ?? "",
        error: "",
      },
    },
  };
}

// ─── Visits ───────────────────────────────────────────────────────────────

async function showSignup({ title }: Partial<ShowSignup>): Promise<RunResult> {
  const all = visitCards();
  if (!all.length) throw new Error("this page has no visit cards; they are on admision.uahurtado.cl/ven-y-conocenos/");
  const want = norm(title);
  const tests = [
    (v: Visit) => norm(v.info.title) === want,
    (v: Visit) => norm(v.info.title).startsWith(want),
    (v: Visit) => want.startsWith(norm(v.info.title)) && norm(v.info.title).length > 3,
    (v: Visit) => norm(v.info.title).includes(want),
  ];
  let hits: Visit[] = [];
  for (const test of tests) {
    hits = want ? all.filter(test) : [];
    if (hits.length) break;
  }
  if (!hits.length) throw new Error(`no visit "${title}" on this page; it has: ${list(all.map((v) => v.info.title))}`);
  // Two cards may share a title ("UAH VIRTUAL" in June and in September): the
  // one still open wins.
  const v = hits.find((h) => h.info.open && !h.info.done) ?? hits[0];
  if (v.info.done) throw new Error(`"${v.info.title}" is marked REALIZADO: it already happened`);
  if (!v.link) throw new Error(`"${v.info.title}" has its sign-ups closed ("${v.info.signup_label || "Inscripciones cerradas"}")`);
  await scrollTo(v.card, "center");
  // Rung, never clicked: the sign-up is a Google or HubSpot form the visitor opens.
  highlight(v.link);
  let host = "";
  try {
    host = new URL(v.link.href).host;
  } catch {
    /* A relative link: the site's own. */
  }
  return {
    ok: true,
    detail: `the "${clean(v.link.textContent)}" link of ${v.info.title} is rung for the visitor to open${host ? ` (it opens ${host})` : ""}`,
  };
}

// ─── context ──────────────────────────────────────────────────────────────

function context(): PageChanged {
  const k = kind();
  const visits = visitCards().map((v) => v.info);
  return {
    url: here(),
    title: document.title,
    kind: k,
    headings: headingEls()
      .map((h) => h.text)
      .slice(0, MAX_HEADINGS),
    toggles: toggles()
      .map((t) => t.label)
      .slice(0, MAX_TOGGLES),
    faqs: faqItems()
      .map((f) => f.question)
      .slice(0, MAX_FAQS),
    cards: cards(),
    career: k === "career" ? careerSheet() : null,
    program: k === "program" ? programSheet() : null,
    visits,
    form: formInfo(),
    translated: translated(),
  };
}

// ─── Reporting ────────────────────────────────────────────────────────────

let emitter: ((event: string, payload: unknown) => void) | null = null;

/** What only matters while someone listens: the visitor's typing, a press. */
function emitNow(event: string, payload: unknown): void {
  emitter?.(event, payload);
}

let lastUrl: string | null = null;
let lastTranslated = false;

/** The site loads a whole page for every move, so this only sees a change of
 *  hash or a history step the page made without loading, and Chrome
 *  translating the page under the visitor. */
function changed(): void {
  const now = here();
  const tr = translated();
  if (now === lastUrl && tr === lastTranslated) return;
  lastUrl = now;
  lastTranslated = tr;
  clearHighlight();
  emitter?.("page_changed", context());
}

function watchRoutes(): void {
  window.addEventListener("popstate", changed);
  window.addEventListener("hashchange", changed);
  new MutationObserver(changed).observe(document.documentElement, { attributes: true, attributeFilter: ["class", "lang"] });
}

function start(next: (event: string, payload: unknown) => void): () => void {
  emitter = next;
  lastUrl = here();
  lastTranslated = translated();
  next("page_changed", context());
  return () => {
    if (emitter === next) emitter = null;
  };
}

const COMMANDS: Record<string, (payload: never) => Promise<RunResult | void>> = {
  navigate,
  show_section: showSection,
  open_faq: openFaq,
  open_career_menu: openCareerMenu,
  play_audiomalla: playAudiomalla,
  show_admission: showAdmission,
  show_program: showProgram,
  fill_lead_form: fillLeadForm,
  show_signup: showSignup,
};

async function run(command: string, payload: unknown): Promise<RunResult> {
  const fn = COMMANDS[command];
  if (!fn) return { ok: false, error: `the page cannot ${command}` };
  try {
    return (await fn((payload ?? {}) as never)) ?? { ok: true };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
}

/** UserWay's button (bottom-right on every host), and the lead form for a
 *  minute and a half after Javier filled it. */
function obstacles(): Element[] {
  const out = [...document.querySelectorAll("#userwayAccessibilityIcon, .uwy .uai, .uwy .userway_buttons_wrapper")];
  const form = leadForm();
  if (form && Date.now() - lastFill < 90_000) out.push(form);
  return out.filter((el) => visible(el));
}

if (!window.voqalizeUah) {
  styleThePage();
  watchRoutes();
  watchForm();
  watchAudio();
  window.voqalizeUah = {
    run,
    context,
    start,
    commands: Object.keys(COMMANDS),
    obstacles,
    configure: (next) => Object.assign(hooks, next),
  };
}
