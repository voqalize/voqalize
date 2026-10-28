/**
 * The site adapter: drive enveedo.com from the outside, with no help from
 * Enveedo's developers.
 *
 * The brain sends a Voqalize `ui-command` ({command, payload}) and `run`
 * performs it on the page in front; the page reports back through `start`,
 * which calls `emit(event, payload)` for every page the visitor lands on
 * (`page_changed`), for the site's HubSpot forms (`form_state` after a fill and
 * after the visitor's own typing, `form_result` once they pressed Submit and the
 * site answered), for the demo scheduler (`demo_state`, `demo_scheduled`, from
 * the meetings.hubspot.com frame's script, `meetings.ts`), and for a move left
 * from the last page that could not be finished (`command_failed`).
 *
 * What the site is, for a script like this: HubSpot CMS drag-and-drop, every
 * move between pages a full page load. A move to another page writes what is
 * left to do to `sessionStorage` and loads the page; the adapter on the next
 * page does it once the page has settled. The header is sticky (66 px once
 * scrolled), so a place is scrolled to 90 px under the window's top.
 *
 * English at `/…`, Spanish at `/es/…` (`site-language.ts`). The brain names
 * English paths and language-independent keys; in a Spanish call the Spanish
 * twin loads, and a key resolves on whichever page is in front, by that
 * page's own entry in the catalogue (`../backend/knowledge/L3/anchors.json`,
 * bundled in: every page under its English and its Spanish path, with the
 * same keys). A place hidden behind the site's own control (the home page's
 * "How Enveedo Works" tabs and Without/With toggle, the FAQ's accordions,
 * About's Mission/Vision/Philosophy tabs) carries `reveal: {click, open}`: the
 * control is clicked unless `open` already matches, then the place is rung.
 *
 * What it never does: tick a consent box, press Submit, submit a form, touch
 * the reCAPTCHA, press the scheduler's Confirm (the frame's script cannot
 * either, and blocks the visitor's press in this preview), or click the cookie
 * banner's buttons. There is no Action that could ask for any of it.
 */

import catalogue from "virtual:enveedo-anchors";

import { foldPath, hreflangHere, type Lang, onSite, pageLanguage, pathLang, twinPath, twinUrl } from "./site-language";

declare global {
  interface Window {
    voqalizeEnveedo?: Adapter;
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
  /** The call is on (in `language`) or off: links follow its language. */
  setCall(live: boolean, language: Lang): void;
  /** What the widget must keep clear of: the cookie banner, HubSpot's chat
   *  launcher, a form while Javier fills it. */
  obstacles(): Element[];
  /** The Actions `run` performs. */
  readonly commands: readonly string[];
}

export type FormName = "contact" | "soc2";

export interface PageContext {
  url: string;
  path: string;
  lang: Lang;
  title: string;
  /** The catalogue's kind of page (home, platform, demo, contact, …), or page. */
  kind: string;
  /** The catalogue's places this page shows, by key. */
  anchors: string[];
  form: FormName | "demo" | "none";
}

interface Row {
  key: string;
  selector: string;
  label?: string;
  fallback?: string;
  reveal?: { click: string; open: string };
  hidden?: boolean;
  optional?: boolean;
}

interface PageEntry {
  kind?: string;
  lang?: string;
  twin?: string | null;
  header?: boolean;
  footer?: boolean;
  forms?: string[];
  anchors?: Row[];
}

interface Catalogue {
  pages?: Record<string, PageEntry>;
  header?: Row[];
  footer?: Row[];
}

const CATALOGUE = catalogue as unknown as Catalogue;
/** The catalogue's pages by folded path (`/es/` and `/es` are one page). */
const PAGES = new Map(Object.entries(CATALOGUE.pages ?? {}).map(([p, e]) => [foldPath(p), e]));

/** Enveedo's own accent violet (its buttons' `#7552e0`), on a white edge, so
 *  the ring reads on the white sections and the dark navy hero alike. */
const RING = "#7552E0";
const RING_MS = 6000;
const WAIT_MS = 8000;
/** The sticky header is 66 px once scrolled: a place sits this far down. */
const SCROLL_OFFSET = 90;
/** Where a move to another page leaves the rest of it for the next page. */
const THEN_KEY = "voqalize.enveedo.then";
const THEN_MAX_AGE_MS = 120_000;

const DEMO_PATH = "/book-a-demo";
const MEETINGS = "https://meetings.hubspot.com";
/** HubSpot's own embed, as the page's `data-src` names it. */
const MEETINGS_SRC = "https://meetings.hubspot.com/elis-martinez?embed=true";
/** How long after the page's load the scheduler's frame may take to appear
 *  before the adapter makes it itself (HubSpot's loader waits for `load`,
 *  which a slow tracker can hold back for a minute). */
const FRAME_GRACE_MS = 6000;

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const clean = (s: string | null | undefined) => (s ?? "").replace(/\s+/g, " ").trim();
/**
 * For matching what the brain said against what the page shows: lower case,
 * without accents, with straight quotes, and without the opening "¿"/"¡" and
 * closing punctuation.
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
  if (r.width <= 0 || r.height <= 0) return false;
  const cs = getComputedStyle(el);
  return cs.visibility !== "hidden" && cs.display !== "none";
};

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

/** The path as the catalogue keys it. */
export const canonical = foldPath;
const here = () => foldPath(location.pathname);
const entry = (): PageEntry | undefined => PAGES.get(here());

/** The call: whether one is on, and its language. */
let call: { live: boolean; language: Lang } = { live: false, language: "en" };

/** The language a move loads pages in: the call's, else the page's. */
const moveLang = (): Lang => (call.live ? call.language : pageLanguage());

/** The catalogue's places for the page in front: its own, then the header's
 *  and the footer's. */
function rows(): Row[] {
  const page = entry();
  const header = CATALOGUE.header ?? [];
  const footer = CATALOGUE.footer ?? [];
  if (page) return [...(page.anchors ?? []), ...(page.header !== false ? header : []), ...(page.footer !== false ? footer : [])];
  return [...header, ...footer];
}

function queryAll(selector: string | undefined): HTMLElement[] {
  if (!selector) return [];
  try {
    return [...document.querySelectorAll<HTMLElement>(selector)];
  } catch {
    return [];
  }
}

/** A place's element: its selector, else its row fallback; laid out first. */
function find(row: Row): HTMLElement | null {
  for (const sel of [row.selector, row.fallback]) {
    const all = queryAll(sel);
    const shown = all.find(visible);
    if (shown) return shown;
  }
  return queryAll(row.selector)[0] ?? queryAll(row.fallback)[0] ?? null;
}

const rowOf = (key: string) => rows().find((r) => r.key === key);

const CONTACT_FORM = 'form.hs-form[id^="hsForm_9ab169f1-2d40-4869-9f6f-943c71b98aa7"]';
const SOC2_FORM = 'form.hs-form[id^="hsForm_8e75d561-509b-4454-a003-d60115042fc9"]';

function formHere(): PageContext["form"] {
  if (document.querySelector(CONTACT_FORM)) return "contact";
  if (document.querySelector(SOC2_FORM)) return "soc2";
  if (document.querySelector(".meetings-iframe-container")) return "demo";
  const f = entry()?.forms?.[0];
  return f === "contact" || f === "soc2" || f === "demo" ? f : "none";
}

function context(): PageContext {
  const anchors = rows()
    .filter((r) => !r.hidden)
    .filter((r) => {
      const el = find(r);
      // A place behind a tab or an accordion is there to be opened.
      return r.reveal || r.optional ? Boolean(el) : visible(el);
    })
    .map((r) => r.key);
  return {
    url: location.href,
    path: location.pathname,
    lang: pageLanguage(),
    title: document.title,
    kind: entry()?.kind ?? "page",
    anchors: [...new Set(anchors)],
    form: formHere(),
  };
}

// ─── Scrolling ────────────────────────────────────────────────────────────

function distance(el: Element, align: "top" | "center"): number {
  const r = el.getBoundingClientRect();
  if (align === "center") {
    const room = window.innerHeight - SCROLL_OFFSET;
    return r.top - (SCROLL_OFFSET + Math.max(0, (room - r.height) / 2));
  }
  return r.top - SCROLL_OFFSET;
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
 *  measuring again as lazy images load. */
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
  const room = window.innerHeight - SCROLL_OFFSET - 24;
  await scrollTo(el, el.getBoundingClientRect().height <= room ? "center" : "top");
}

// ─── The ring ─────────────────────────────────────────────────────────────
// Drawn over the page, never on Enveedo's own elements: fixed, and moved with
// its target every frame, so it follows a scroll and a carousel under it.

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

function followRings(): void {
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
  ringFrame = requestAnimationFrame(followRings);
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
      boxShadow: "0 0 0 2px #fff",
      pointerEvents: "none",
      zIndex: "2147483000",
      opacity: "0",
      transition: "opacity 300ms ease",
      animation: "voqalize-ring 1.4s ease-in-out 3",
    });
    document.body.appendChild(el);
    rings.push({ el, targets });
  }
  followRings();
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
  if (document.querySelector("style[data-voqalize=enveedo]")) return;
  const style = document.createElement("style");
  style.setAttribute("data-voqalize", "enveedo");
  style.textContent = `
    @keyframes voqalize-ring {
      0%, 100% { box-shadow: 0 0 0 2px #fff, 0 0 0 3px rgba(117, 82, 224, 0.6); }
      50% { box-shadow: 0 0 0 2px #fff, 0 0 0 14px rgba(117, 82, 224, 0); }
    }
  `;
  (document.head ?? document.documentElement).appendChild(style);
}

/** What to ring for a place: the place, or, when it is much taller than the
 *  screen, its heading. A whole section (the catalogue's `.dnd-section:has(…)`
 *  places: a heading with its cards) is rung whole, its content box, even past
 *  the screen's foot: its heading alone is not what was named. */
function ringTarget(el: HTMLElement, whole = false): HTMLElement {
  if (whole) return el.querySelector<HTMLElement>(":scope > .row-fluid") ?? el;
  if (el.getBoundingClientRect().height <= window.innerHeight * 0.8) return el;
  // HubSpot's heroes write their title in a styled rich-text div as often as
  // in an h1.
  const heading = [...el.querySelectorAll<HTMLElement>("h1, h2, h3, h4, [class*=title], [class*=heading], .rtext__content")].find(
    (h) => visible(h) && h.getBoundingClientRect().height <= window.innerHeight * 0.6,
  );
  return heading ?? el;
}

// ─── navigate, and the move left for the next page ────────────────────────

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
  location.assign(target.pathname + target.search + target.hash);
}

/** The page at `path` (an English path, as the brain names them) in `lang`:
 *  its twin by the static map, else, when it is the page in front, its own
 *  hreflang link; else as named. */
export function pageIn(path: string, lang: Lang): URL {
  const target = new URL(path.trim() || "/", location.origin);
  if (!onSite(target.host)) return target;
  const twin = twinPath(target.pathname, lang);
  if (twin) {
    const q = new URLSearchParams(target.search);
    q.delete("hsLang");
    const qs = q.toString();
    return new URL(`${twin}${qs ? `?${qs}` : ""}${target.hash}`, location.origin);
  }
  if (foldPath(target.pathname) === here() && pageLanguage() !== lang) {
    const alt = hreflangHere(lang);
    if (alt) return new URL(alt);
  }
  return target;
}

async function navigate({ path, anchor, text }: { path: string; anchor?: string | null; text?: string | null }) {
  if (typeof path !== "string" || !path.trim()) throw new Error("say which page to go to, as a path like /contact");
  const target = pageIn(path, moveLang());
  if (!onSite(target.host)) {
    throw new Error(`${target.href} is not on enveedo.com; open it with open_link instead`);
  }
  if (foldPath(target.pathname) !== here()) return goTo(target, { anchor: anchor ?? null, text: text ?? null });
  // Already here: the move is made on this page, which reports itself again.
  try {
    if (anchor || text) await showSection({ anchor, text });
    else {
      window.scrollTo({ top: 0, behavior: "smooth" });
      await scrollEnded();
    }
  } finally {
    emit("page_changed", context());
  }
}

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
 *  failure is reported as that move's. */
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

// ─── show_section, and the places behind a tab, an accordion or the toggle ─

/** Open a place the site hides behind its own control: click the control
 *  unless the place is already open, and wait for it to open. */
async function reveal(row: Row): Promise<boolean> {
  const spec = row.reveal;
  if (!spec) return false;
  if (queryAll(spec.open).length) return false;
  const control = queryAll(spec.click).find(visible) ?? queryAll(spec.click)[0];
  if (!control) throw new Error(`the control that opens "${row.key}" is not on ${location.pathname}`);
  control.click();
  await waitFor(() => queryAll(spec.open).length > 0, 2000);
  // The panel's own transition (an accordion grows from 0).
  await sleep(350);
  return true;
}

/** Not the page's content: the header, the footer, the cookie banner, ours. */
const CHROME = "header.header, footer#footer, #hs-eu-cookie-confirmation, [data-voqalize]";

/** The smallest laid-out element whose text holds `text`. */
function smallestContaining(text: string): HTMLElement | null {
  const want = norm(text);
  if (!want) return null;
  let found: HTMLElement | null = null;
  let bestLen = Infinity;
  for (const el of document.body.querySelectorAll<HTMLElement>("*")) {
    if (/^(SCRIPT|STYLE|NOSCRIPT|svg|OPTION|SELECT|IFRAME)$/i.test(el.tagName) || !visible(el) || el.closest(CHROME)) continue;
    const t = norm(el.textContent);
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

async function showSection({ anchor, text }: { anchor?: string | null; text?: string | null }): Promise<string | void> {
  if (anchor) {
    const row = rowOf(anchor);
    if (row) {
      const opened = await reveal(row);
      const el = (await waitFor(() => {
        const e = find(row);
        return visible(e) ? e : null;
      }, opened ? 2000 : 300)) ?? null;
      if (el) {
        await bringIntoView(el);
        // The toggle's cards: the switch above them is rung with them.
        const toggle = row.reveal?.click === "#toggle-switch" ? document.querySelector("#toggle-switch") : null;
        const target = ringTarget(el, el.matches(".dnd-section") && row.selector.includes(".dnd-section:has("));
        highlight(toggle && visible(toggle) ? [target, toggle] : target);
        return opened ? `opened and showed ${row.key}` : undefined;
      }
    }
    if (!text) {
      const known = context().anchors.join(", ");
      throw new Error(`no place "${anchor}" on ${location.pathname}; it has: ${known || "none"}`);
    }
  }
  if (!text) throw new Error("say which place or words to show");
  const el = smallestContaining(text);
  if (!el) throw new Error(`"${text}" is not on ${location.pathname}; its places are: ${context().anchors.join(", ")}`);
  await bringIntoView(el);
  highlight(ringTarget(el));
}

// ─── The forms ────────────────────────────────────────────────────────────

type Field = HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;

interface FormSpec {
  selector: string;
  /** HubSpot's form id, in its `hsFormCallback` messages. */
  guid: string;
  /** The page that holds it (English). */
  page: string;
  /** The brain's name → the form's own field name. */
  fields: Record<string, string>;
  required: string[];
}

const FORMS: Record<FormName, FormSpec> = {
  contact: {
    selector: CONTACT_FORM,
    guid: "9ab169f1-2d40-4869-9f6f-943c71b98aa7",
    page: "/contact",
    fields: {
      firstname: "firstname",
      lastname: "lastname",
      email: "email",
      phone: "phone",
      country: "country",
      company: "company",
      message: "message",
    },
    required: ["firstname", "lastname", "country", "email"],
  },
  soc2: {
    selector: SOC2_FORM,
    guid: "8e75d561-509b-4454-a003-d60115042fc9",
    page: "/trust-center",
    fields: {
      firstname: "firstname",
      lastname: "lastname",
      company: "company",
      job_title: "jobtitle",
      message: "notes",
      email: "email",
    },
    required: ["firstname", "lastname", "company", "job_title", "email"],
  },
};

const formEl = (name: FormName) => document.querySelector<HTMLFormElement>(FORMS[name].selector);

function field(form: HTMLFormElement, spec: FormSpec, key: string): Field | null {
  const name = spec.fields[key];
  if (!name) return null;
  // HubSpot names the SOC 2 form's job title `jobtitle` or `job_title`.
  const names = key === "job_title" ? ["jobtitle", "job_title"] : [name];
  for (const n of names) {
    const el = form.querySelector<Field>(`[name="${n}"]`);
    if (el) return el;
  }
  return null;
}

const consentBox = (form: HTMLFormElement) =>
  form.querySelector<HTMLInputElement>('input[type=checkbox][name^="LEGAL_CONSENT"]');
const submitButton = (form: HTMLFormElement) =>
  form.querySelector<HTMLElement>("input.hs-button[type=submit], button[type=submit], input[type=submit]");

/** Set a field as typing would: the native setter (HubSpot's forms are React,
 *  which ignores a plain `value =`), then the events its listeners wait for. */
function setField(el: Field, value: string): void {
  const proto =
    el instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : el instanceof HTMLSelectElement
        ? HTMLSelectElement.prototype
        : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value")?.set?.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
  el.dispatchEvent(new FocusEvent("blur", { bubbles: false }));
  el.dispatchEvent(new FocusEvent("focusout", { bubbles: true }));
}

/** The select's option the brain named: by its value or its words, exactly
 *  (folding case and accents only). */
function option(select: HTMLSelectElement, said: string): HTMLOptionElement | null {
  const want = norm(said);
  const opts = [...select.options].filter((o) => o.value);
  return opts.find((o) => o.value === said || clean(o.textContent) === clean(said)) ??
    opts.find((o) => norm(o.value) === want || norm(o.textContent) === want) ??
    null;
}

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/** The field's wrapper, as HubSpot classes it (`.hs_email`), for ringing it
 *  and for reading its error line. */
const wrapOf = (el: Element) => el.closest<HTMLElement>(".hs-form-field") ?? el.parentElement;

function hasError(el: Field): boolean {
  if (el.classList.contains("invalid") || el.classList.contains("error") || el.getAttribute("aria-invalid") === "true") return true;
  const errs = wrapOf(el)?.querySelector(".hs-error-msgs, .hs-error-msg");
  return Boolean(errs && clean(errs.textContent));
}

export interface FormStateOut {
  form: FormName;
  filled: string[];
  missing: string[];
  invalid: string[];
  values: Record<string, string>;
  ready: boolean;
  by: "javier" | "visitor";
}

function formState(name: FormName, by: "javier" | "visitor"): FormStateOut | null {
  const form = formEl(name);
  if (!form) return null;
  const spec = FORMS[name];
  const filled: string[] = [];
  const missing: string[] = [];
  const invalid: string[] = [];
  const values: Record<string, string> = {};
  for (const key of Object.keys(spec.fields)) {
    const el = field(form, spec, key);
    if (!el) continue;
    const v = el instanceof HTMLSelectElement ? clean(el.value) : clean(el.value);
    if (v) {
      filled.push(key);
      values[key] = el instanceof HTMLSelectElement ? clean(el.selectedOptions[0]?.textContent) || v : v;
      if ((key === "email" && !EMAIL.test(v)) || hasError(el)) invalid.push(key);
    } else if (spec.required.includes(key) || el.required) {
      missing.push(key);
    }
  }
  const consent = consentBox(form);
  if (consent && !consent.checked) missing.push("consent");
  return { form: name, filled, missing, invalid, values, ready: !missing.length && !invalid.length, by };
}

/** When Javier last filled a form, for the widget to keep clear of it. */
let lastFill = 0;
let lastFilled: FormName | null = null;
/** Set while Javier types, so his own events are not taken for the visitor's. */
let filling = false;

type FillOrder = { form?: FormName } & Record<string, string | null | undefined>;

async function fillForm(p: FillOrder): Promise<string> {
  const name = p.form;
  if (name !== "contact" && name !== "soc2") throw new Error(`no form "${String(name)}"; there are: contact, soc2`);
  const spec = FORMS[name];
  let form = formEl(name);
  // HubSpot draws its forms after the page: on a page that holds this one, wait.
  if (!form && entry()?.forms?.includes(name)) form = await waitFor(() => formEl(name), 10_000);
  if (!form) {
    const page = pageIn(spec.page, moveLang());
    if (foldPath(page.pathname) === here()) throw new Error(`the ${name} form did not load on ${location.pathname}`);
    goTo(page, { command: "fill_form", payload: p });
    return "";
  }
  filling = true;
  lastFill = Date.now();
  lastFilled = name;
  const done: string[] = [];
  const notes: string[] = [];
  try {
    await bringIntoView(form);
    for (const key of Object.keys(spec.fields)) {
      const said = p[key];
      if (said === null || said === undefined || !String(said).trim()) continue;
      const el = field(form, spec, key);
      if (!el) {
        notes.push(`this form has no ${key} field`);
        continue;
      }
      if (el instanceof HTMLSelectElement) {
        const opt = option(el, String(said));
        if (!opt) {
          notes.push(`no ${key} option "${said}" (pick one the form lists, "Others" when theirs is not there)`);
          continue;
        }
        setField(el, opt.value);
      } else {
        setField(el, key === "message" ? String(said).trim() : clean(String(said)));
      }
      done.push(key);
      await sleep(40);
    }
    // HubSpot validates on its own clock after the blur.
    await sleep(400);
    const state = formState(name, "javier")!;
    emit("form_state", state);
    const consent = consentBox(form);
    const button = submitButton(form);
    const onlyConsent = !state.invalid.length && state.missing.every((k) => k === "consent");
    if (onlyConsent && button) {
      // Everything Javier may type is in: the box and the button are the visitor's.
      const box = consent ? (consent.closest<HTMLElement>(".legal-consent-container, .hs-form-field") ?? consent) : null;
      await bringIntoView(button);
      highlight(box && visible(box) && !consent?.checked ? [box, button] : [button]);
    } else {
      const nextKey = [...state.invalid, ...state.missing].find((k) => k !== "consent");
      const next = nextKey ? field(form, spec, nextKey) : null;
      const last = done.length ? field(form, spec, done[done.length - 1]) : null;
      const target = next ?? last;
      highlight((target && wrapOf(target)) ?? form);
    }
    return [
      done.length ? `filled ${done.join(", ")}` : "filled nothing",
      state.missing.length ? `still empty: ${state.missing.join(", ")}` : "every required field is filled",
      state.invalid.length ? `the site would refuse: ${state.invalid.join(", ")}` : "",
      ...notes,
      onlyConsent
        ? "the consent box and Submit are rung for the visitor: they tick it and press Submit themselves"
        : "",
    ]
      .filter(Boolean)
      .join("; ");
  } finally {
    setTimeout(() => {
      filling = false;
    }, 50);
  }
}

/** Which of our forms an element is in. */
function formOf(target: EventTarget | null): FormName | null {
  if (!(target instanceof Element)) return null;
  for (const name of Object.keys(FORMS) as FormName[]) if (target.closest(FORMS[name].selector)) return name;
  return null;
}

/** Follow the visitor in the forms: their typing, and the site's answer to
 *  their press of Submit. The newsletter and eBook forms are not followed. */
function watchForms(): void {
  const timers: Partial<Record<FormName, ReturnType<typeof setTimeout>>> = {};
  const last: Partial<Record<FormName, string>> = {};
  const report = (name: FormName) => {
    const state = formState(name, "visitor");
    const key = JSON.stringify(state);
    if (!state || key === last[name]) return;
    last[name] = key;
    emit("form_state", state);
  };
  const typed = (e: Event) => {
    const name = formOf(e.target);
    if (!name || filling) return;
    if (timers[name]) clearTimeout(timers[name]);
    timers[name] = setTimeout(() => report(name), 900);
  };
  document.addEventListener("input", typed, true);
  document.addEventListener("change", typed, true);

  // The visitor pressed Submit: HubSpot validates, runs its invisible
  // reCAPTCHA and posts, then swaps the form for its thank-you message.
  const pressed: Partial<Record<FormName, boolean>> = {};
  const onSubmit = (e: Event) => {
    const name = formOf(e.target);
    if (!name || pressed[name]) return;
    pressed[name] = true;
    void followResult(name).finally(() => {
      pressed[name] = false;
    });
  };
  document.addEventListener("submit", onSubmit, true);
  document.addEventListener(
    "click",
    (e) => {
      const t = e.target as Element | null;
      if (t?.closest?.("input[type=submit], button[type=submit]")) onSubmit(e);
    },
    true,
  );
  window.addEventListener("message", (e: MessageEvent) => {
    const d = e.data as { type?: string; eventName?: string; id?: string } | null;
    if (d?.type !== "hsFormCallback" || d.eventName !== "onFormSubmitted") return;
    for (const name of Object.keys(FORMS) as FormName[]) if (FORMS[name].guid === d.id) sentBy[name] = Date.now();
  });
}

/** When HubSpot said a form was sent, by its callback message. */
const sentBy: Partial<Record<FormName, number>> = {};

async function followResult(name: FormName): Promise<void> {
  const since = Date.now();
  const form = formEl(name);
  const box = form?.closest(".hbspt-form") ?? form?.parentElement ?? document.body;
  const thanks = () => box.querySelector(".submitted-message") ?? (!formEl(name) && document.querySelector(".submitted-message"));
  const errors = () => {
    const f = formEl(name);
    if (!f) return null;
    const spec = FORMS[name];
    const bad = Object.keys(spec.fields).filter((k) => {
      const el = field(f, spec, k);
      return el ? hasError(el) : false;
    });
    const consent = consentBox(f);
    if (consent && !consent.checked && wrapOf(consent)?.querySelector(".hs-error-msgs")) bad.push("consent");
    const rollup = f.querySelector(".hs_error_rollup");
    return bad.length || (rollup && clean(rollup.textContent)) ? { bad, message: clean(rollup?.textContent) } : null;
  };
  for (;;) {
    await sleep(250);
    if (thanks() || (sentBy[name] ?? 0) >= since) {
      const msg = document.querySelector(".submitted-message");
      emit("form_result", { form: name, outcome: "sent", message: clean(msg?.textContent).slice(0, 300), fields: [] });
      return;
    }
    const wrong = Date.now() - since > 1200 ? errors() : null;
    if (wrong) {
      emit("form_result", { form: name, outcome: "invalid", message: wrong.message, fields: wrong.bad });
      return;
    }
    if (Date.now() - since > 20_000) {
      emit("form_result", { form: name, outcome: "failed", message: "", fields: [] });
      return;
    }
  }
}

// ─── book_demo: the HubSpot Meetings frame on /book-a-demo ────────────────

interface BookOrder {
  duration?: string | null;
  day?: string | null;
  time?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  email?: string | null;
}

let frameCalls = 0;

const isDemoPage = () => englishOf(here()) === DEMO_PATH;
const englishOf = (p: string) => (pathLang(p) === "es" ? foldPath(p.replace(/^\/es/, "")) : p);

const meetingsFrame = () =>
  document.querySelector<HTMLIFrameElement>(".meetings-iframe-container iframe, iframe[src*='meetings.hubspot.com']");

/** The scheduler's frame: HubSpot's own, or, when its loader has not made it
 *  within a few seconds of the page's load, one made here the way its embed
 *  code would (the same `src`, the parent page's address). */
async function ensureFrame(): Promise<HTMLIFrameElement | null> {
  const box = await waitFor(() => document.querySelector<HTMLElement>(".meetings-iframe-container"), WAIT_MS);
  if (!box) return meetingsFrame();
  const existing = meetingsFrame();
  if (existing) return existing;
  await Promise.race([
    document.readyState === "complete" ? Promise.resolve() : new Promise<void>((r) => window.addEventListener("load", () => r(), { once: true })),
    sleep(FRAME_GRACE_MS),
  ]);
  const late = await waitFor(meetingsFrame, FRAME_GRACE_MS);
  if (late) return late;
  const src = new URL(box.getAttribute("data-src") || MEETINGS_SRC);
  if (!src.searchParams.has("embed")) src.searchParams.set("embed", "true");
  src.searchParams.set("parentPageUrl", location.origin + location.pathname);
  const utk = document.cookie.match(/(?:^|;\s*)hubspotutk=([^;]+)/)?.[1];
  if (utk) src.searchParams.set("parentHubspotUtk", utk);
  const frame = document.createElement("iframe");
  frame.src = src.href;
  frame.setAttribute("data-voqalize-made", "");
  frame.title = "Meetings";
  Object.assign(frame.style, { width: "100%", minWidth: "312px", height: "756px", border: "none" });
  box.appendChild(frame);
  console.info("voqalize: the scheduler's frame was late; made it from", src.href);
  return frame;
}

type FrameReply = { error: string | null; state: Record<string, unknown> } | null;

/** One order to the frame (`meetings.ts`), answered with its state. */
function toFrame(frame: HTMLIFrameElement, cmd: string, order?: unknown, ms = 15_000): Promise<FrameReply> {
  const id = ++frameCalls;
  return new Promise((resolve) => {
    const timer = setTimeout(() => done(null), ms);
    const on = (e: MessageEvent) => {
      if (e.origin !== MEETINGS) return;
      const reply = (e.data as { voqalizeMeetingsDone?: FrameReply & { id: number } })?.voqalizeMeetingsDone;
      if (reply?.id === id) done(reply);
    };
    function done(v: FrameReply) {
      clearTimeout(timer);
      window.removeEventListener("message", on);
      resolve(v);
    }
    window.addEventListener("message", on);
    frame.contentWindow?.postMessage({ voqalizeMeetingsCmd: { id, cmd, order } }, MEETINGS);
  });
}

/** The scheduler before its frame has drawn (or answered at all). */
const LOADING = {
  step: "loading", duration: "", durations: [], month: "", days: [], date: "", times: [], time: "", timezone: "",
  filled: { first_name: "", last_name: "", email: "" }, missing: [],
};

let lastDemo = "";
function emitDemo(state: unknown): void {
  const key = JSON.stringify(state);
  if (key === lastDemo) return;
  lastDemo = key;
  emit("demo_state", state);
}

async function bookDemo(order: BookOrder): Promise<string | void> {
  if (!isDemoPage()) {
    goTo(pageIn(DEMO_PATH, moveLang()), { command: "book_demo", payload: order });
    return;
  }
  const frame = await ensureFrame();
  const box = frame?.closest(".meetings-iframe-container") ?? frame;
  if (!frame || !box) throw new Error(`the demo scheduler is not on ${location.pathname}`);
  await scrollTo(box, "top");
  highlight(box);
  // The frame's script answers once it runs, which can be before the
  // scheduler has drawn its calendar: ask until it has.
  // Meanwhile the brain hears it is loading, once.
  let answered: FrameReply = null;
  let told = false;
  for (let i = 0; i < 24; i++) {
    const reply = await toFrame(frame, "state", undefined, 1000);
    if (reply) {
      answered = reply;
      if (reply.state.step !== "loading") break;
    }
    if (!told) {
      told = true;
      emitDemo(LOADING);
    }
    await sleep(500);
  }
  if (!answered) throw new Error("the demo scheduler did not load");
  if (answered.state.step === "loading") throw new Error("the demo scheduler is still loading");
  const wants = order.duration || order.day || order.time || order.first_name || order.last_name || order.email;
  if (!wants) {
    lastDemo = "";
    emitDemo(answered.state);
    return;
  }
  const done = await toFrame(frame, "book", order, 30_000);
  if (!done) throw new Error("the demo scheduler did not answer");
  lastDemo = "";
  emitDemo(done.state);
  highlight(box);
  if (done.error) throw new Error(done.error);
}

/** What the frame reports by itself: the visitor's own clicks in it, and
 *  their press of Confirm. */
function watchMeetings(): void {
  window.addEventListener("message", (e: MessageEvent) => {
    if (e.origin !== MEETINGS) return;
    const data = e.data as {
      voqalizeMeetings?: unknown;
      voqalizeMeetingsScheduled?: { date?: string; time?: string; filled?: unknown; blocked?: boolean };
      meetingBookSucceeded?: boolean;
    } | null;
    if (!data || typeof data !== "object") return;
    if (data.voqalizeMeetings) emitDemo(data.voqalizeMeetings);
    const s = data.voqalizeMeetingsScheduled;
    if (s) emit("demo_scheduled", { date: s.date ?? "", time: s.time ?? "", filled: s.filled ?? {}, blocked: Boolean(s.blocked) });
    // HubSpot's own word that a meeting was booked (only with the block off).
    if (data.meetingBookSucceeded) {
      const last = (lastDemo ? JSON.parse(lastDemo) : {}) as { date?: string; time?: string; filled?: unknown };
      emit("demo_scheduled", { date: last.date ?? "", time: last.time ?? "", filled: last.filled ?? {}, blocked: false });
    }
  });
}

// ─── site_language: the page in front follows the call's language ─────────

/** Load this page in `language` when it is in the other one. `twin`: only
 *  its own twin, and an error when it has none; else that language's home
 *  page when it has none. */
async function siteLanguage({ language, twin }: { language: Lang; twin?: boolean }): Promise<void> {
  if (language !== "en" && language !== "es") throw new Error(`not a site language: ${String(language)}`);
  if (pageLanguage() === language) {
    if (twin) emit("page_changed", context());
    return;
  }
  const there = twinUrl(location.href, language) ?? hreflangHere(language);
  if (!there) {
    if (twin) throw new Error(`${location.pathname} has no ${language === "es" ? "Spanish" : "English"} version`);
    goTo(new URL(language === "es" ? "/es/" : "/", location.origin), {});
    return;
  }
  goTo(new URL(there, location.origin), {});
}

// ─── Links follow the call's language, and stay in the tab ────────────────

const ORIGINAL_HREF = "data-voqalize-href";
const ORIGINAL_TARGET = "data-voqalize-target";
/** The site's own language switcher is the visitor's choice: left alone. */
const LEAVE = ".hs-language-switcher, [data-voqalize]";

function rewriteLink(a: HTMLAnchorElement, lang: Lang | null): void {
  if (a.closest(LEAVE)) return;
  const original = a.getAttribute(ORIGINAL_HREF) ?? a.getAttribute("href");
  if (!original || /^(#|mailto:|tel:|javascript:)/i.test(original)) return;
  let url: URL;
  try {
    url = new URL(original, location.href);
  } catch {
    return;
  }
  if (!onSite(url.host)) return;
  if (!lang) {
    if (a.hasAttribute(ORIGINAL_HREF)) {
      a.setAttribute("href", a.getAttribute(ORIGINAL_HREF)!);
      a.removeAttribute(ORIGINAL_HREF);
    }
    if (a.hasAttribute(ORIGINAL_TARGET)) {
      a.setAttribute("target", a.getAttribute(ORIGINAL_TARGET)!);
      a.removeAttribute(ORIGINAL_TARGET);
    }
    return;
  }
  const twin = twinUrl(url, lang);
  const want = twin ?? original;
  if (want !== a.getAttribute("href")) {
    if (!a.hasAttribute(ORIGINAL_HREF)) a.setAttribute(ORIGINAL_HREF, original);
    a.setAttribute("href", want);
  }
  // A same-site page opened in a new tab would leave the call's tab behind.
  const target = a.getAttribute("target");
  if (target && target !== "_self" && !NOT_A_PAGE.test(url.pathname)) {
    a.setAttribute(ORIGINAL_TARGET, target);
    a.removeAttribute("target");
  }
}

const NOT_A_PAGE = /^\/(hubfs|_hcms|hs-fs)(\/|$)|\.[a-z0-9]{2,5}$/i;

let linkObserver: MutationObserver | null = null;

function rewriteLinks(lang: Lang | null): void {
  for (const a of document.querySelectorAll<HTMLAnchorElement>("a[href]")) rewriteLink(a, lang);
  linkObserver?.disconnect();
  linkObserver = null;
  if (!lang) return;
  linkObserver = new MutationObserver((records) => {
    for (const r of records) {
      for (const n of r.addedNodes) {
        if (!(n instanceof Element)) continue;
        if (n instanceof HTMLAnchorElement) rewriteLink(n, lang);
        for (const a of n.querySelectorAll<HTMLAnchorElement>("a[href]")) rewriteLink(a, lang);
      }
    }
  });
  linkObserver.observe(document.documentElement, { childList: true, subtree: true });
}

function setCall(live: boolean, language: Lang): void {
  const was = call;
  call = { live, language: language === "es" ? "es" : "en" };
  if (was.live === call.live && was.language === call.language && (live || !linkObserver)) return;
  const apply = () => rewriteLinks(live ? call.language : null);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", apply, { once: true });
  else apply();
}

// ─── Reporting ────────────────────────────────────────────────────────────

let emitter: ((event: string, payload: unknown) => void) | null = null;
const backlog: [string, unknown][] = [];
function emit(event: string, payload: unknown): void {
  if (emitter) emitter(event, payload);
  else backlog.push([event, payload]);
}

let lastUrl: string | null = null;
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
  fill_form: fillForm,
  book_demo: bookDemo,
  site_language: siteLanguage,
};

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

/** What the widget keeps clear of: the cookie banner's box (its buttons are
 *  the visitor's), HubSpot's chat launcher, the demo scheduler on
 *  /book-a-demo (at 1440 px its calendar reaches the bottom-left corner), and
 *  a form for a minute and a half after Javier filled it. */
function obstacles(): Element[] {
  const out: Element[] = [];
  const banner =
    document.querySelector("#hs-eu-cookie-confirmation-inner") ?? document.querySelector("#hs-eu-cookie-confirmation");
  if (visible(banner)) out.push(banner);
  const chat = document.querySelector("#hubspot-messages-iframe-container");
  if (visible(chat)) out.push(chat);
  const scheduler = meetingsFrame();
  if (scheduler && visible(scheduler)) out.push(scheduler);
  const form = lastFilled ? formEl(lastFilled) : null;
  if (form && Date.now() - lastFill < 90_000 && visible(form)) out.push(form);
  return out;
}

if (!window.voqalizeEnveedo) {
  styleThePage();
  window.addEventListener("popstate", routeChanged);
  window.addEventListener("hashchange", routeChanged);
  watchForms();
  watchMeetings();
  void finishThen();
  window.voqalizeEnveedo = { run, context, start, setCall, obstacles, commands: Object.keys(COMMANDS) };
}
