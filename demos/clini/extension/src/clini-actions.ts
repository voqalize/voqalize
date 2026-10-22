/**
 * The site adapter: drive www.clini.cl (and, through `agenda-actions.ts`, the
 * booking on agenda-web.clini.cl) from the outside, with no help from Clini's
 * developers.
 *
 * The brain sends a Voqalize `ui-command` ({command, payload}) and `run`
 * performs it on the page in front; the page reports back through `start`,
 * which calls `emit(event, payload)` for every page the visitor lands on, for
 * the booking's state on agenda-web, and for a move that could not be finished
 * after a page load.
 *
 * What the site is, for a script like this: Webflow, rendered on the server,
 * with no client router and no `<main>`: the sections are the body's own
 * children, between a fixed marquee bar (`.header-fixed-clini`, 35 px) and a
 * fixed navbar under it (`.w-nav`, 61 px; 96 px in all, 91 on a phone). Every
 * move between pages is a full page load, so a move to another page cannot
 * finish on the page that asked for it: `navigate` leaves what is left to do (a
 * heading, a text, a question, the LASIK form) in `sessionStorage` and loads
 * the page, and the adapter on the next page does it once that page has
 * settled. The window scrolls; there is no scroll library.
 *
 * Section classes (`section-403`, `section-266`…) are designer names, shared
 * between templates and renamed on a whim, so sections are found by the words
 * on them. Hidden content is revealed the way a visitor reveals it: a Webflow
 * tab pane (`.w-tab-pane`) by a click on its `.w-tab-link`, a dropdown (every
 * FAQ, and a sede's "Ver horarios") by a click on its toggle, a slider slide by
 * a click on its dot.
 *
 * Forms are filled, never sent: no submit, no Enter, no click on the submit
 * button. The RUT is the visitor's to type; Javier only points at the field.
 */

import { agendaCommands, agendaContext, watchAgenda } from "./agenda-actions";
import {
  best, boxOf, chileanMobile, clean, clearHighlight, headerHeight, highlight, inOrder, leave, type Leftover, norm,
  pickOption, scrollTo, scrollToTopOfPage, setValue, settled, shown, sleep, styleThePage, takeLeftover,
  visible, waitFor,
} from "./page";

declare global {
  interface Window {
    voqalizeClini?: Adapter;
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
  /** `site` is www.clini.cl; `agenda` is agenda-web.clini.cl, the booking. */
  site: "site" | "agenda";
  url: string;
  path: string;
  title: string;
  kind: string;
  /** Section headings a visitor can be taken to, in page order. */
  headings: string[];
  /** The FAQ questions on the page. */
  faqs: string[];
  /** Named plans or offers on the page; Clini lists none by name. */
  plans: string[];
}

const MAX_HEADINGS = 80;
const MAX_FAQS = 120;
const LASIK_PATH = "/cirugia-lasik";

const onAgenda = () => /^agenda-web\.clini\.cl$/i.test(location.host);

/** The page's content. Clini's Webflow pages have no wrapper around their
 *  sections, so it is the body, less `CHROME`. */
const main = (): HTMLElement => document.body;

/**
 * Not the page's content: the marquee bar and navbar, the footer, Clinito's
 * chat (`#clinitoEmbed`, an iframe pinned bottom-right), the phone's bottom
 * bar (`.div-block-475`: cotizar, llamar, chat, reservar), the holiday and
 * other popups, and our own.
 */
const CHROME = [
  ".header-fixed-clini",
  ".w-nav",
  "nav:not(.w-dropdown-list)",
  "footer",
  ".footer-nuevo",
  "#clinitoEmbed",
  ".div-block-475",
  ".modal-feriados",
  ".modal-feriados-clini",
  ".pop-up-modal",
  "[data-voqalize]",
].join(", ");
const inChrome = (el: Element) => Boolean(el.closest(CHROME));

// ─── Hidden content: tabs, dropdowns, slider slides ───────────────────────

/** A Webflow dropdown is open: Webflow puts `w--open` on its list. */
const dropdownOpen = (d: Element) => Boolean(d.querySelector(":scope > .w-dropdown-list.w--open"));

/**
 * Open a Webflow dropdown as a visitor's press does. Some of Clini's open on a
 * `click` (the FAQs), others only on the press's mouse events (a sede's "Ver
 * horarios"), so it tries the click, then the press without one, so that
 * neither undoes the other.
 */
async function openDropdown(d: HTMLElement): Promise<void> {
  if (dropdownOpen(d)) return;
  const toggle = d.querySelector<HTMLElement>(":scope > .w-dropdown-toggle");
  if (!toggle) return;
  toggle.click();
  if (!(await waitFor(() => dropdownOpen(d), 500))) {
    for (const type of ["pointerdown", "mousedown", "pointerup", "mouseup"]) {
      const init = { bubbles: true, cancelable: true, view: window, button: 0 };
      toggle.dispatchEvent(type.startsWith("pointer") ? new PointerEvent(type, init) : new MouseEvent(type, init));
    }
    await waitFor(() => dropdownOpen(d), 1200);
  }
  await sleep(250);
}

async function closeDropdown(d: HTMLElement): Promise<void> {
  if (!dropdownOpen(d)) return;
  d.querySelector<HTMLElement>(":scope > .w-dropdown-toggle")?.click();
  await waitFor(() => !dropdownOpen(d), 1000);
}

/** The slide `el` is on is the one in view: else press its dot (or the arrow
 *  until it is). Webflow keeps every slide laid out, off to the side. */
async function revealSlide(el: HTMLElement): Promise<void> {
  const slide = el.closest<HTMLElement>(".w-slide");
  const slider = slide?.closest<HTMLElement>(".w-slider");
  const mask = slider?.querySelector<HTMLElement>(".w-slider-mask");
  if (!slide || !slider || !mask) return;
  const inView = () => {
    const s = slide.getBoundingClientRect();
    const m = mask.getBoundingClientRect();
    return s.left >= m.left - 4 && s.right <= m.right + 4;
  };
  const slides = [...slider.querySelectorAll<HTMLElement>(".w-slide")];
  const dots = [...slider.querySelectorAll<HTMLElement>(".w-slider-dot")];
  const i = slides.indexOf(slide);
  const dot = dots.length === slides.length ? dots[i] : undefined;
  // The home's hero turns every 3 s by itself: while he points at a slide it
  // is brought back each time it turns away, for as long as the ring shows.
  if (dot && slider.getAttribute("data-autoplay") === "true") holdSlide(inView, dot);
  if (inView()) return;
  if (dot) {
    dot.click();
    await waitFor(inView, 1500);
  } else {
    const right = slider.querySelector<HTMLElement>(".w-slider-arrow-right");
    for (let n = 0; n < slides.length && !inView(); n++) {
      right?.click();
      await sleep(600);
    }
  }
  await sleep(300);
}

let held: ReturnType<typeof setInterval> | null = null;
function holdSlide(inView: () => boolean, dot: HTMLElement): void {
  if (held) clearInterval(held);
  const until = Date.now() + 6000;
  held = setInterval(() => {
    if (Date.now() > until) {
      if (held) clearInterval(held);
      held = null;
    } else if (!inView()) dot.click();
  }, 250);
}

/** Show whatever hides `el`: the Webflow tab pane it is in (by its tab), the
 *  dropdown it is in (by its toggle), the slider slide it is on (by its dot). */
async function reveal(el: HTMLElement): Promise<void> {
  for (let pane = el.closest<HTMLElement>(".w-tab-pane"); pane; ) {
    if (!pane.classList.contains("w--tab-active")) {
      const name = pane.getAttribute("data-w-tab");
      const tabs = pane.closest<HTMLElement>(".w-tabs");
      const link = [...(tabs?.querySelectorAll<HTMLElement>(".w-tab-link") ?? [])].find(
        (l) => l.getAttribute("data-w-tab") === name,
      );
      if (link) {
        link.click();
        await waitFor(() => pane?.classList.contains("w--tab-active") && shown(el), 2000);
        await sleep(250);
      }
    }
    pane = pane.parentElement?.closest<HTMLElement>(".w-tab-pane") ?? null;
  }
  const list = el.closest<HTMLElement>(".w-dropdown-list");
  const dropdown = list?.parentElement?.closest<HTMLElement>(".w-dropdown");
  if (dropdown && !inChrome(dropdown)) await openDropdown(dropdown);
  const faq = el.closest<HTMLElement>(".faq-item");
  if (faq && !faq.classList.contains("active") && el.closest(".faq-answer")) {
    faq.querySelector<HTMLElement>(".faq-question")?.click();
    await waitFor(() => faq.classList.contains("active") && shown(el), 1500);
    await sleep(300);
  }
  await revealSlide(el);
}

/** Hidden now, but `reveal` can show it: in a tab pane not showing, or in a
 *  closed dropdown. */
const revealable = (el: Element) => {
  const pane = el.closest(".w-tab-pane");
  if (pane && !pane.classList.contains("w--tab-active")) return true;
  const answer = el.closest(".faq-item:not(.active) .faq-answer");
  if (answer) return true;
  const list = el.closest(".w-dropdown-list");
  return Boolean(list && !list.classList.contains("w--open") && !inChrome(list));
};

/** A popup over the page (the holiday notice, when it shows) is closed by its
 *  own close button before Javier points at anything under it. */
async function closePopups(): Promise<void> {
  for (const pop of document.querySelectorAll<HTMLElement>(".modal-feriados, .modal-feriados-clini, .pop-up-modal")) {
    const r = pop.getBoundingClientRect();
    if (r.width < window.innerWidth * 0.5 || r.height < window.innerHeight * 0.3) continue;
    const close = [...pop.querySelectorAll<HTMLElement>("a, button, div, img")].find(
      (b) => /close|cerrar|x-?button/i.test(`${b.className} ${b.id} ${b.getAttribute("aria-label") ?? ""}`) && visible(b),
    );
    close?.click();
    await sleep(300);
  }
}

// ─── What the page shows ──────────────────────────────────────────────────

interface Faq {
  question: string;
  /** The block that holds the question. */
  block: HTMLElement;
  /** What to click to open it. */
  toggle: HTMLElement | null;
  isOpen: () => boolean;
  /** The answer's blocks. */
  answer: () => HTMLElement[];
}

/** Clini's FAQs are Webflow dropdowns whose toggle asks a question ("¿Es
 *  dolorosa?", `.dropdown-26` on /cirugia-lasik, `.dropdown-10` in the home's
 *  `section-266`); the navbar's and "Reservar hora" dropdowns ask none. */
function faqItems(): Faq[] {
  const items: Faq[] = [];
  const root = main();
  for (const d of root.querySelectorAll<HTMLElement>(".w-dropdown")) {
    const toggle = d.querySelector<HTMLElement>(":scope > .w-dropdown-toggle");
    const list = d.querySelector<HTMLElement>(":scope > .w-dropdown-list");
    if (!toggle || !list || inChrome(d)) continue;
    const question = clean(toggle.innerText || toggle.textContent);
    if (!/\?\s*$/.test(question)) continue;
    if (!shown(d) && !revealable(d)) continue;
    items.push({
      question,
      block: d,
      toggle,
      isOpen: () => list.classList.contains("w--open"),
      answer: () => [list],
    });
  }
  // The newer exam pages' own accordion (`.faq-clini`): `.faq-item` holds a
  // `button.faq-question` and a `.faq-answer`; the open one is `.active`.
  for (const d of root.querySelectorAll<HTMLElement>(".faq-item")) {
    const toggle = d.querySelector<HTMLElement>("button.faq-question, .faq-question");
    const answer = d.querySelector<HTMLElement>(".faq-answer");
    if (!toggle || !answer || inChrome(d)) continue;
    const label = toggle.cloneNode(true) as HTMLElement;
    label.querySelectorAll("span, svg, img").forEach((x) => x.remove());
    items.push({
      question: clean(label.textContent),
      block: d,
      toggle,
      isOpen: () => d.classList.contains("active"),
      answer: () => [answer],
    });
  }
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
  return items.filter((i) => i.question).sort((a, b) => inOrder(a.block, b.block));
}

interface Head {
  el: HTMLElement;
  text: string;
}

/** Headings the visitor can be taken to, in page order; those in a tab pane
 *  not showing or on a slide off to the side too, since `reveal` shows them.
 *  Not the FAQ questions, and not the labels inside a card ("Centro de
 *  Salud:", "Toma de muestras:" on /ubicaciones), which head nothing. */
function headings(): Head[] {
  const root = main();
  const found: Head[] = [];
  const faqBlocks = faqItems().map((f) => f.block);
  for (const h of root.querySelectorAll<HTMLElement>("h1, h2, h3, h4")) {
    if (inChrome(h) || faqBlocks.some((b) => b.contains(h))) continue;
    if (!shown(h) && !revealable(h)) continue;
    const text = clean(h.innerText || h.textContent);
    if (text.length <= 1 || /:\s*$/.test(text)) continue;
    found.push({ el: h, text });
  }
  found.sort((a, b) => inOrder(a.el, b.el));
  const seen = new Set<string>();
  return found.filter((h) => !seen.has(norm(h.text)) && seen.add(norm(h.text)));
}

/** What sort of page this is, in the brain's words (`PageChanged.kind`): a
 *  blog post (/blog/<slug>, /blog-mujer/<slug>) or any other page. */
function kindOf(path: string): "page" | "post" {
  return /^\/blog(-mujer)?\/[^/]+/i.test(path) ? "post" : "page";
}

function context(): PageContext {
  if (onAgenda()) return agendaContext();
  return {
    site: "site",
    url: location.href,
    path: location.pathname,
    title: document.title,
    kind: kindOf(location.pathname),
    headings: headings()
      .map((h) => h.text)
      .slice(0, MAX_HEADINGS),
    faqs: faqItems()
      .map((f) => f.question)
      .slice(0, MAX_FAQS),
    plans: [],
  };
}

// ─── navigate ─────────────────────────────────────────────────────────────

const strip = (p: string) => (p || "/").replace(/\/+$/, "") || "/";
const samePath = (a: string, b: string) => strip(a).toLowerCase() === strip(b).toLowerCase();
const siteHost = (h: string) => h.replace(/^www\./i, "").toLowerCase();

/** Load another page of this host, leaving `then` for it to make. */
function loadPage(target: URL, then: Leftover | null): void {
  leave(then);
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
  if (typeof path !== "string" || !path.trim()) throw new Error("say which page to go to, as a path like /ubicaciones");
  const target = new URL(path.trim(), location.origin);
  if (siteHost(target.host) !== siteHost(location.host)) {
    throw new Error(`${target.href} is not on ${location.host}; only this site's own pages can be opened here`);
  }
  const rest: Leftover | null = faq
    ? { command: "open_faq", payload: { question: faq } }
    : heading || text
      ? { command: "show_section", payload: { heading: heading ?? null, text: text ?? null } }
      : null;
  if (!samePath(location.pathname, target.pathname) || target.search !== location.search) {
    // A full page load: what is left is done by the adapter on the next page.
    loadPage(target, rest);
    return;
  }
  if (rest) return run(rest.command, rest.payload).then((r) => { if (!r.ok) throw new Error(r.error); });
  await scrollToTopOfPage();
}

/** Finish the move a page of this tab started before it loaded this one, once
 *  this page has settled; a failure is reported as the brain's cue that did
 *  not land. */
async function finishLeftover(): Promise<void> {
  const then = takeLeftover();
  if (!then) return;
  await settled();
  const result = await run(then.command, then.payload);
  if (!result.ok) emit("command_failed", { command: then.command === "show_section" || then.command === "open_faq" ? "cue" : then.command, reason: result.error });
}

// ─── show_section ─────────────────────────────────────────────────────────

function findHeading(heading: string): HTMLElement | null {
  return best(headings(), (x) => x.text, heading)?.el ?? null;
}

/** A card: a CMS item (a sede on /ubicaciones, a blog card), a slide, a tab
 *  pane, or a block Clini's designers named as a card or a box. */
const CARDS = ".w-dyn-item, .caja-ubicaciones, .w-slide, .w-tab-pane, [class*='card'], [class*='caja'], [class*='box']";
const SECTIONS = "section, .section, [class^='section-'], [class*=' section-']";

/** What a heading heads: the smallest card around it that holds more than the
 *  heading and fits on the screen, else its section when that fits, else the
 *  smallest ancestor that holds more than the heading itself. */
function sectionOf(h: HTMLElement): HTMLElement[] {
  const fits = (el: HTMLElement) => {
    const b = boxOf([el]);
    return !b || b.bottom - b.top < window.innerHeight * 1.3;
  };
  const more = (el: HTMLElement) => clean(el.textContent).length > clean(h.textContent).length + 20;
  for (let el = h.parentElement; el && el !== main(); el = el.parentElement) {
    if (el.matches(SECTIONS)) break;
    if (el.matches(CARDS) && more(el) && fits(el)) return [el];
  }
  const s = h.closest<HTMLElement>(SECTIONS);
  if (s && s !== main() && fits(s)) return [s];
  let el = h.parentElement;
  while (el && el !== main() && !more(el)) el = el.parentElement;
  return [el ?? h];
}

/** The smallest element in `root` whose text contains `text`: one on screen,
 *  else one `reveal` can show. */
function smallestContaining(root: Element, text: string): HTMLElement | null {
  const want = norm(text);
  if (!want) return null;
  let found: HTMLElement | null = null;
  let bestLen = Infinity;
  let hidden: HTMLElement | null = null;
  let hiddenLen = Infinity;
  for (const el of root.querySelectorAll<HTMLElement>("*")) {
    if (inChrome(el) || /^(SCRIPT|STYLE|NOSCRIPT|svg|IFRAME)$/i.test(el.tagName)) continue;
    const t = norm(el.textContent);
    if (!t.includes(want)) continue;
    if (visible(el)) {
      if (t.length < bestLen) [found, bestLen] = [el, t.length];
    } else if (t.length < hiddenLen && revealable(el)) {
      [hidden, hiddenLen] = [el, t.length];
    }
  }
  // A pane or dropdown not showing holds the words more closely than the
  // visible block around it, whose text includes the hidden pane's.
  if (hidden && hiddenLen < bestLen) found = hidden;
  if (!found) {
    // A banner says what it is only in its `alt`.
    const img = [...root.querySelectorAll<HTMLImageElement>("img[alt], img[title]")].find(
      (i) => !inChrome(i) && visible(i) && norm(i.alt || i.title).includes(want),
    );
    return img ? (img.closest<HTMLElement>("a, figure, p") ?? img) : null;
  }
  // A word inside a paragraph is read with its paragraph.
  if (/^(STRONG|B|EM|I|SPAN|A)$/.test(found.tagName)) {
    const p = found.closest<HTMLElement>("p, li, h1, h2, h3, h4");
    if (p && clean(p.innerText).length < 400) return p;
  }
  return found;
}

/** A sede's card on /ubicaciones keeps its hours in a "Ver horarios"
 *  dropdown: showing the sede opens them. */
async function openHours(card: HTMLElement): Promise<HTMLElement[]> {
  const d = [...card.querySelectorAll<HTMLElement>(".w-dropdown")].find((x) =>
    /horario/i.test(x.querySelector(":scope > .w-dropdown-toggle")?.textContent ?? ""),
  );
  if (!d) return [];
  await openDropdown(d);
  const list = d.querySelector<HTMLElement>(":scope > .w-dropdown-list");
  return list && visible(list) ? [list] : [];
}

async function showSection({ heading, text }: { heading?: string | null; text?: string | null }) {
  await closePopups();
  const h = heading ? findHeading(heading) : null;
  if (heading && !h && !text) {
    const known = context().headings.slice(0, 25).join(" | ");
    throw new Error(`no heading "${heading}" on ${location.pathname}; it has: ${known || "no headings"}`);
  }
  if (text) {
    const within = h ? sectionOf(h) : [];
    let el: HTMLElement | null = null;
    for (const s of within) if ((el = smallestContaining(s, text))) break;
    el ??= smallestContaining(main(), text);
    if (!el) throw new Error(`"${text}" is not on ${location.pathname}`);
    await reveal(el);
    const tall = el.getBoundingClientRect().height > window.innerHeight * 0.7;
    await scrollTo(el, tall ? "top" : "center");
    highlight(el);
    return;
  }
  if (!h) throw new Error("say which heading or text to show");
  await reveal(h);
  const section = sectionOf(h);
  const hours = await Promise.all(section.map(openHours)).then((x) => x.flat());
  const group = [...section, ...hours];
  const box = boxOf(group);
  const height = box ? box.bottom - box.top : Infinity;
  // A block that fits under the header is shown from its top; a longer one
  // from its heading.
  const top = section.filter(shown).sort((x, y) => x.getBoundingClientRect().top - y.getBoundingClientRect().top)[0];
  const room = window.innerHeight - headerHeight() - 32;
  await scrollTo(top && height <= room ? top : h, height <= room ? "center" : "top");
  highlight(height > window.innerHeight * 1.3 ? h : group);
}

// ─── open_faq ─────────────────────────────────────────────────────────────

async function openFaq({ question }: { question: string }) {
  await closePopups();
  const all = faqItems();
  const item = best(all, (f) => f.question, question ?? "");
  if (!item) {
    const known = all.map((f) => f.question).slice(0, 15).join(" | ");
    throw new Error(`no FAQ "${question}" on ${location.pathname}${known ? `; it has: ${known}` : ""}`);
  }
  // An open answer pushes the page about and can sit over the next question;
  // the others close first, as a visitor would close them.
  for (const other of all) {
    if (other === item || !other.isOpen()) continue;
    if (other.block.classList.contains("w-dropdown")) await closeDropdown(other.block);
    else if (other.block.classList.contains("faq-item")) other.toggle?.click();
  }
  await reveal(item.block);
  await scrollTo(item.block, "center");
  if (!item.isOpen() && item.toggle) {
    if (item.block.classList.contains("w-dropdown")) await openDropdown(item.block);
    else item.toggle.click();
    await waitFor(item.isOpen, 2000);
    await sleep(400);
  }
  const group = [item.block, ...item.answer()];
  const box = boxOf(group);
  const tall = box ? box.bottom - box.top > window.innerHeight * 0.7 : false;
  await scrollTo(item.block, tall ? "top" : "center");
  highlight(group);
}

// ─── fill_lasik_form ──────────────────────────────────────────────────────

interface LasikForm {
  name?: string | null;
  email?: string | null;
  phone?: string | null;
  prevision?: string | null;
  location?: string | null;
  focus_rut?: boolean | null;
}

/** The words a visitor says for each of the form's "Ubicación" options. */
const LASIK_PLACES: Record<string, string> = {
  tobalaba: "Santiago - LTO",
  lto: "Santiago - LTO",
  "luis thayer": "Santiago - LTO",
  lyon: "Santiago - Lyon",
  "los leones": "Santiago - Lyon",
  leones: "Santiago - Lyon",
  "santa lucia": "Santiago - Metro Santa Lucía",
  miraflores: "Santiago - Metro Santa Lucía",
  antofagasta: "Antofagasta",
  sucre: "Antofagasta",
  temuco: "Temuco",
  alemania: "Temuco",
};

/** The words a visitor says for a previsión that the list spells otherwise. */
const PREVISIONS: Record<string, string> = {
  "cruz blanca": "CruzBlanca",
  "mas vida": "Nueva Más Vida",
  "nueva mas vida": "Nueva Más Vida",
  "vida 3": "Vida Tres",
  "isalud": "iSalud",
  "ninguna": "Particular",
};

/**
 * The free LASIK evaluation's form on /cirugia-lasik (`#nuevo_lasik_junio`,
 * in section `#form`). It is a call-back request, not a booking: a coordinator
 * calls to pick the day. Javier fills what the visitor said, points at the RUT
 * for them to type, and rings "¡Agendar evaluación!" for them to press once
 * the form is complete. He never submits it.
 */
async function fillLasikForm(payload: LasikForm) {
  if (!samePath(location.pathname, LASIK_PATH)) {
    loadPage(new URL(LASIK_PATH, location.origin), { command: "fill_lasik_form", payload });
    return;
  }
  await closePopups();
  const form = await waitFor(() => document.querySelector<HTMLFormElement>("#nuevo_lasik_junio, #form form"));
  if (!form) throw new Error("the LASIK evaluation form is not on this page");
  const $ = <T extends HTMLElement>(sel: string) => form.querySelector<T>(sel);
  const fields = {
    name: $<HTMLInputElement>("#name"),
    rut: $<HTMLInputElement>("#rutInput"),
    email: $<HTMLInputElement>("#correo"),
    phone: $<HTMLInputElement>("#telefonoInput"),
    prevision: $<HTMLSelectElement>("#Prevision-4, select[name=Prevision]"),
    location: $<HTMLSelectElement>("#Ubicaci-n-2, select[data-name^=Ubicaci]"),
  };
  const section = form.closest<HTMLElement>("#form, section") ?? form;
  await scrollTo(section, "top");

  const touched: HTMLElement[] = [];
  const problems: string[] = [];
  const text = (key: "name" | "email", value: string | null | undefined) => {
    const el = fields[key];
    if (!value || !el) return;
    setValue(el, value.trim());
    touched.push(el);
  };
  text("name", payload.name);
  text("email", payload.email);
  if (payload.phone && fields.phone) {
    const digits = chileanMobile(payload.phone);
    if (!/^9\d{8}$/.test(digits)) problems.push(`the phone "${payload.phone}" is not a Chilean mobile (9 digits, starting with 9)`);
    else {
      setValue(fields.phone, digits);
      touched.push(fields.phone);
    }
  }
  const choose = (key: "prevision" | "location", said: string | null | undefined, aliases: Record<string, string>) => {
    const el = fields[key];
    if (!said || !el) return;
    const option = pickOption(el, said, aliases);
    if (!option) {
      const known = [...el.options].filter((o) => o.value).map((o) => o.text.trim());
      problems.push(`no ${key === "prevision" ? "previsión" : "ubicación"} "${said}"; the form offers: ${known.join(" | ")}`);
      return;
    }
    setValue(el, option.value);
    touched.push(el);
  };
  choose("prevision", payload.prevision, PREVISIONS);
  choose("location", payload.location, LASIK_PLACES);
  await sleep(150);

  const state = lasikState(form, fields);
  emit("lasik_form_state", state);
  const submit = form.querySelector<HTMLElement>("input.submit-button-42, [type=submit]");
  if (payload.focus_rut && fields.rut) {
    await scrollTo(fields.rut, "center");
    fields.rut.focus({ preventScroll: true });
    highlight(fields.rut);
  } else if (state.valid && submit) {
    await scrollTo(submit, "center");
    highlight(submit);
  } else if (touched.length) {
    highlight(touched);
  } else {
    highlight(section);
  }
  if (problems.length) throw new Error(problems.join("; "));
}

function lasikState(
  form: HTMLFormElement,
  fields: Record<string, HTMLInputElement | HTMLSelectElement | null>,
): { filled: string[]; missing: string[]; valid: boolean } {
  const filled: string[] = [];
  const missing: string[] = [];
  for (const [key, el] of Object.entries(fields)) {
    if (!el) continue;
    const value = el.value.trim();
    // The phone keeps its "+56 9 " prefix, which is not a number yet.
    const empty = key === "phone" ? value.replace(/\D/g, "").length < 11 : !value;
    (empty || !el.checkValidity() ? missing : filled).push(key);
  }
  return { filled, missing, valid: form.checkValidity() };
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
  // The booking's state, on load and after every change, on agenda-web.
  const stopAgenda = onAgenda() ? watchAgenda(next) : null;
  for (const [event, payload] of backlog.splice(0)) next(event, payload);
  return () => {
    stopAgenda?.();
    if (emitter === next) emitter = null;
  };
}

const SITE_COMMANDS: Record<string, (payload: never) => Promise<void>> = {
  navigate,
  show_section: showSection,
  open_faq: openFaq,
  fill_lasik_form: fillLasikForm,
};

const COMMANDS: Record<string, (payload: never) => Promise<void>> = onAgenda()
  ? { show_section: showSection, ...agendaCommands() }
  : SITE_COMMANDS;

async function run(command: string, payload: unknown): Promise<{ ok: boolean; error?: string }> {
  const fn = COMMANDS[command];
  if (!fn) return { ok: false, error: `the page on ${location.host} cannot ${command}` };
  try {
    await fn((payload ?? {}) as never);
    return { ok: true };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
}

if (!window.voqalizeClini) {
  styleThePage();
  watchRoutes();
  void finishLeftover();
  window.voqalizeClini = { run, context, start, commands: Object.keys(COMMANDS) };
}

