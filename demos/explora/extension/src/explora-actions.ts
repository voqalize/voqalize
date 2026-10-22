/**
 * The www.explora.com adapter: drive Explora's WordPress site from the
 * outside, with no help from Explora's developers.
 *
 * The brain sends a Voqalize `ui-command` ({command, payload}) and `run`
 * performs it on the page in front; `start` reports the page as it stands
 * (`page_changed`) once the call is up on it.
 *
 * What the site is, for a script like this:
 *
 *   - Every move between pages is a full page load: no client-side router. So
 *     `navigate` stores the move for the next page with the hub (`loadThen`)
 *     and sets `location`; the next page's copy of this script makes it. The
 *     pacing of a load against Javier's voice (`after_words`) is the call's,
 *     in `content.ts`.
 *   - The window scrolls (no smooth-scroll library), under a fixed
 *     `header#masthead` and, on destination, lodge and expedition pages, a
 *     sticky `.explora-submenu` (`dom.ts` measures both).
 *   - jQuery 3.6, Bootstrap 4.6 collapse (the home map's accordion, every FAQ
 *     list, "READ MORE"), the theme's own `.tab-panels` (Why Explora), and Owl
 *     Carousel 2.3 for every row of cards. What is asked for inside a closed
 *     pane, a collapsed accordion or a carousel slide out of view is first
 *     brought out the way a visitor would: a click on its tab or trigger, or
 *     the carousel's own `to.owl.carousel`.
 *
 * The headings, questions and tab labels reported are read with the crawler's
 * own rules (`backend/knowledge/L3/build_main.py`), so the names the brain
 * knows from the crawl are the names this page finds.
 */

import {
  type Adapter,
  clean,
  clearHighlight,
  headerHeight,
  highlight,
  norm,
  type PageContext,
  pick,
  scrollTo,
  sleep,
  styleThePage,
  visible,
  waitFor,
} from "./dom";
import { loadThen, type Then } from "./hub";

const SITE_ORIGIN = "https://www.explora.com";
const MAX_HEADINGS = 80;
const MAX_FAQS = 120;
const MAX_TABS = 40;
const MAX_LINKS = 30;

const isExplora = (host: string) => /^(www\.)?explora\.com$/i.test(host);
/** Links that stay in the tab while a call is live: the call survives a
 *  same-tab load, and a new tab would be a tab with no call in it. */
const OURS = /^https:\/\/(www\.|reservations\.)?explora\.com(\/|$)/i;

/** The page's own content, as the crawler reads it. */
const root = (): HTMLElement =>
  document.querySelector<HTMLElement>("#content") ?? document.querySelector("main") ?? document.body;

/** The crawler's `visible`: laid out at all, whether or not on screen. */
const laidOut = (el: Element) =>
  !!((el as HTMLElement).offsetWidth || (el as HTMLElement).offsetHeight || el.getClientRects().length);

const SKIP = "header#masthead, footer, .modal, .mobile-menu, .nav-mobile, script, style, noscript, [data-voqalize]";
/** Menus too, for the `h4`s: a dropdown's or a sub-menu's titles are not sections. */
const SKIP_H4 = `${SKIP}, nav, .dropdown-menu, .explora-submenu, .owl-item.cloned`;
const HEAD_SEL = "h1,h2,h3,.h1,.h2,.h3,.explora-page-title";
const isQuestionLike = (s: string) => /read more|read less/i.test(s);

/** A pane the adapter can open: a closed theme tab, Bootstrap tab or collapse. */
const CLOSED = ".tab-panels-content .panel:not(.active), .tab-pane:not(.active), .collapse:not(.show)";

/** Hidden by the layout itself, not by a pane the adapter can open: inside a
 *  responsive copy that is `display: none` at this width (`d-none`,
 *  `d-md-none`, `d-lg-none`…), the mobile accordion beside a desktop row. */
function layoutHidden(el: Element): boolean {
  for (let p: Element | null = el; p && p !== document.body; p = p.parentElement) {
    if (laidOut(p)) return false;
    if (!p.matches(CLOSED) && getComputedStyle(p).display === "none") return true;
  }
  return false;
}

/** What may be reported and used at this width: laid out, or hidden only
 *  by a closed pane the adapter can open. */
const usable = (el: Element) => laidOut(el) || !layoutHidden(el);

// ─── What the page shows ──────────────────────────────────────────────────

/** Section headings, in document order: the crawler's (`h1`–`h3`, the styled
 *  `.h1`–`.h3` divs, `.explora-page-title`; not in the header, footer or a
 *  modal; laid out; not wrapping another heading), plus the destination
 *  names `/destinations/` sets in `h4.explora-heading`, plus every other
 *  `h4` that is laid out (not in a menu, not an accordion's trigger, not a
 *  question): the desktop copy of a row whose mobile copy is an accordion,
 *  as the Sacred Valley's exploration zones. With `hidden`, also those in
 *  closed panes (never in a responsive copy hidden at this width), for a
 *  heading asked for that is not showing. */
function headingEls(hidden = false): HTMLElement[] {
  return [...root().querySelectorAll<HTMLElement>(`${HEAD_SEL}, h4`)].filter((h) => {
    if (h.closest(SKIP) || !headText(h)) return false;
    if (isPlainH4(h)) {
      return (
        laidOut(h) &&
        !h.closest(SKIP_H4) &&
        !h.matches("[data-toggle]") &&
        !h.querySelector("[data-toggle]") &&
        !headText(h).endsWith("?")
      );
    }
    return (laidOut(h) || (hidden && !layoutHidden(h))) && (h.matches("h4") || !h.querySelector(HEAD_SEL));
  });
}

/** An `h4` the crawler's rules do not take (not `.h3`-styled, not a destination name). */
const isPlainH4 = (h: Element) => h.matches("h4") && !h.matches(`${HEAD_SEL}, .explora-heading`);

/** A heading as the crawler read it: its rendered text (`innerText`, so
 *  `text-transform: uppercase` reads as capitals), at most 200 characters. */
const headText = (h: HTMLElement) => clean(h.innerText || h.textContent).slice(0, 200);

interface Trigger {
  el: HTMLElement;
  label: string;
  /** What it opens. */
  pane: HTMLElement;
  kind: "tabpanel" | "navtab" | "collapse";
}

const byId = (ref: string | null): HTMLElement | null => {
  if (!ref || !ref.startsWith("#") || ref.length < 2) return null;
  try {
    return document.querySelector<HTMLElement>(ref);
  } catch {
    return null;
  }
};

/** The theme's tabs (`.tab-panels-nav li[data-index]` over
 *  `.tab-panels-content .panel[data-index]`: Why Explora on a destination). */
function tabPanelTriggers(): Trigger[] {
  const out: Trigger[] = [];
  for (const tp of root().querySelectorAll<HTMLElement>(".tab-panels")) {
    for (const li of tp.querySelectorAll<HTMLElement>(".tab-panels-nav li")) {
      const pane = tp.querySelector<HTMLElement>(`.tab-panels-content .panel[data-index="${li.dataset.index}"]`);
      const label = clean(li.textContent);
      if (pane && label && usable(li)) out.push({ el: li, label, pane, kind: "tabpanel" });
    }
  }
  return out;
}

/** Bootstrap's own tabs, outside the theme's. */
function navTabTriggers(): Trigger[] {
  const out: Trigger[] = [];
  for (const nav of root().querySelectorAll<HTMLElement>(".nav-tabs, [role=tablist], .nav-pills")) {
    if (nav.closest(".tab-panels")) continue;
    for (const a of nav.querySelectorAll<HTMLElement>("a[href^='#'], [data-toggle=tab], [role=tab]")) {
      const pane = byId(a.getAttribute("data-target") ?? a.getAttribute("href"));
      const label = clean(a.textContent);
      if (pane && label && usable(a)) out.push({ el: a, label, pane, kind: "navtab" });
    }
  }
  return out;
}

/** Every Bootstrap collapse trigger with a pane it opens, that is laid out
 *  at this width or sits in a pane that can be opened: never one in a
 *  responsive copy the layout hides (`laidOut`/`layoutHidden`). */
function collapseTriggers(): Trigger[] {
  const out: Trigger[] = [];
  for (const t of root().querySelectorAll<HTMLElement>("[data-toggle=collapse]")) {
    if (t.closest(SKIP) || !usable(t)) continue;
    const pane = byId(t.getAttribute("data-target") ?? t.getAttribute("href"));
    const label = clean(t.textContent);
    if (pane && label) out.push({ el: t, label, pane, kind: "collapse" });
  }
  return out;
}

/** "READ MORE" reads as one label, whatever the hidden "READ LESS" beside it. */
const readMore = (t: Trigger) => t.el.matches(".collapse-control") || /^read more/i.test(t.label);

/** The labels the brain may open as `show`: the theme's and Bootstrap's tabs,
 *  the home map's destination accordion, and a READ MORE that is showing. */
function tabTriggers(): Trigger[] {
  return [
    ...tabPanelTriggers(),
    ...navTabTriggers(),
    ...collapseTriggers().filter((t) => t.el.closest(".component-tmap") || (readMore(t) && visible(t.el))),
  ];
}

const tabLabel = (t: Trigger) => (readMore(t) ? "READ MORE" : t.label);

function tabLabels(): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const t of tabTriggers()) {
    const l = tabLabel(t);
    if (seen.has(norm(l))) continue;
    seen.add(norm(l));
    out.push(l);
  }
  return out.slice(0, MAX_TABS);
}

/** A question set as a heading, not an accordion: the crawler's second rule. */
interface QuestionHeading {
  q: string;
  els: HTMLElement[];
}

function questionHeadings(seen: Set<string>): QuestionHeading[] {
  const out: QuestionHeading[] = [];
  for (const h of root().querySelectorAll<HTMLElement>("h2,h3,h4,h5,strong,b,.h3,.h4")) {
    const q = clean(h.textContent);
    if (!q.endsWith("?") || q.length > 200 || seen.has(q) || h.closest(SKIP)) continue;
    const n = h.matches("strong, b") ? (h.closest<HTMLElement>("p,h3,h4") ?? h) : h;
    const els = [n];
    let sib = n.nextElementSibling as HTMLElement | null;
    for (let guard = 0; sib && guard < 6; guard++) {
      if (sib.matches("h1,h2,h3,h4,h5")) break;
      if (sib.querySelector("strong,b") && clean(sib.textContent).endsWith("?")) break;
      els.push(sib);
      sib = sib.nextElementSibling as HTMLElement | null;
    }
    if (els.length < 2 || !clean(els.slice(1).map((e) => e.textContent).join(" "))) continue;
    seen.add(q);
    out.push({ q, els });
  }
  return out;
}

/** The questions, as the crawler takes them: every collapse trigger with a
 *  pane (not a READ MORE), then every question heading with an answer after
 *  it. The tabs' labels are the tabs', not questions. */
function faqs(): string[] {
  const tabs = new Set(tabTriggers().map((t) => t.label));
  const seen = new Set<string>();
  const out: string[] = [];
  for (const t of collapseTriggers()) {
    if (isQuestionLike(t.label) || seen.has(t.label)) continue;
    seen.add(t.label);
    if (!tabs.has(t.label)) out.push(t.label.slice(0, 300));
  }
  for (const q of questionHeadings(seen)) out.push(q.q);
  return out.slice(0, MAX_FAQS);
}

/** The page's own sub-menu, as site paths: a destination's or an
 *  expedition's `.explora-submenu`, a lodge's OVERVIEW / LODGE / EXPLORATIONS. */
function links(): string[] {
  const out = new Set<string>();
  const anchors = document.querySelectorAll<HTMLAnchorElement>(
    ".explora-submenu a[href], [id^='menu-item-'] > a[href]",
  );
  for (const a of anchors) {
    if (a.closest("header#masthead, footer, .mobile-menu, .nav-mobile, [data-voqalize]")) continue;
    let u: URL;
    try {
      u = new URL(a.href);
    } catch {
      continue;
    }
    if (!isExplora(u.host) || a.getAttribute("href")?.startsWith("#")) continue;
    out.add(u.pathname + u.search);
  }
  return [...out].slice(0, MAX_LINKS);
}

function context(): PageContext {
  const seen = new Set<string>();
  const seenNorm = new Set<string>();
  const hs: string[] = [];
  for (const h of headingEls()) {
    const t = headText(h);
    // The crawler's headings by their exact text; an added `h4` also by its
    // folded one ("FAQs" beside "FAQS").
    if (seen.has(t) || (isPlainH4(h) && seenNorm.has(norm(t)))) continue;
    seen.add(t);
    seenNorm.add(norm(t));
    hs.push(t);
    if (hs.length >= MAX_HEADINGS) break;
  }
  return {
    site: "site",
    url: location.href,
    path: location.pathname,
    title: document.title,
    headings: hs,
    faqs: faqs(),
    tabs: tabLabels(),
    links: links(),
  };
}

// ─── Bringing out what is hidden ──────────────────────────────────────────

const jq = () => (window as unknown as { jQuery?: (el: Element) => { trigger(e: string, a?: unknown[]): void; collapse(a: string): void } }).jQuery;

/** `visible` as a plain answer, where a narrowing guard would narrow too far. */
const shown = (el: Element): boolean => visible(el);

/** Showing, and not a carousel slide off to the side. */
function onShow(el: Element): boolean {
  if (!visible(el)) return false;
  const item = el.closest(".owl-item");
  return !item || item.classList.contains("active");
}

const paneOpen = (pane: HTMLElement) => visible(pane) && !pane.classList.contains("collapsing");

/** Open what `t` opens, the way a visitor would: a click on it, or, when the
 *  trigger itself is not laid out (a mobile copy), Bootstrap's own call. */
async function openTrigger(t: Trigger): Promise<boolean> {
  if (t.kind === "collapse" && t.pane.classList.contains("show") && paneOpen(t.pane)) return true;
  if (t.kind !== "collapse" && paneOpen(t.pane)) return true;
  if (visible(t.el)) {
    await scrollTo(t.el, "center");
    t.el.click();
  } else if (t.kind === "collapse") {
    jq()?.(t.pane).collapse("show");
  } else {
    return false;
  }
  const ok = await waitFor(() => paneOpen(t.pane) && t.pane.getBoundingClientRect().height > 4, 2500);
  // Bootstrap's collapse animates its height for 350 ms.
  await sleep(400);
  return Boolean(ok);
}

/** Every closed thing `el` sits in, outermost first, as the trigger that
 *  opens it; `null` when one of them cannot be opened. */
function closedAround(el: HTMLElement): Trigger[] | null {
  const out: Trigger[] = [];
  const all = [...tabPanelTriggers(), ...navTabTriggers(), ...collapseTriggers()];
  for (let p: HTMLElement | null = el.parentElement; p && p !== document.body; p = p.parentElement) {
    if (shown(p)) break;
    const closed = p.matches(CLOSED);
    if (!closed) {
      // Hidden for some other reason (`d-none`, a mobile-only copy): not ours to open.
      if (getComputedStyle(p).display === "none") return null;
      continue;
    }
    const ts = all.filter((t) => t.pane === p);
    const t = ts.find((x) => visible(x.el)) ?? ts[0];
    if (!t) return null;
    out.unshift(t);
  }
  return out;
}

/** Whether `reveal` could bring `el` out: it is in closed panes that can be
 *  opened, or on a slide of a carousel that is showing. */
function revealable(el: HTMLElement): boolean {
  if (!shown(el)) return closedAround(el) !== null;
  const item = el.closest(".owl-item");
  return !!item && !item.classList.contains("cloned") && shown(item.closest(".owl-carousel") ?? item);
}

/** Where `el` sits under `from`, as child indexes. */
function pathTo(from: Element, el: Element): number[] {
  const path: number[] = [];
  for (let n: Element = el; n !== from && n.parentElement; n = n.parentElement) {
    path.unshift([...n.parentElement.children].indexOf(n));
  }
  return path;
}

function walk(from: Element, path: number[]): HTMLElement | null {
  let n: Element | undefined = from;
  for (const i of path) n = n?.children[i];
  return (n as HTMLElement | undefined) ?? null;
}

/** The copy of `el` the carousel is showing: `el` itself on an active
 *  slide, or the same place on an active clone of its slide (a looping Owl
 *  carousel shows clones at its ends). */
function showingCopy(el: HTMLElement, item: HTMLElement): HTMLElement | null {
  if (item.classList.contains("active")) return el;
  const carousel = item.closest(".owl-carousel");
  const path = pathTo(item, el);
  const twin = [...(carousel?.querySelectorAll<HTMLElement>(".owl-item.cloned.active") ?? [])].find(
    (c) => c.innerHTML === item.innerHTML,
  );
  return twin ? walk(twin, path) : null;
}

/** Bring `el` onto the screen: open the panes it is in, and slide its
 *  carousel to it. The element now showing it (on a looping carousel, a
 *  clone's), or `null` when it could not be brought out. */
async function reveal(el: HTMLElement): Promise<HTMLElement | null> {
  if (!visible(el)) {
    const chain = closedAround(el);
    if (!chain) return null;
    for (const t of chain) await openTrigger(t);
  }
  const item = el.closest<HTMLElement>(".owl-item");
  if (item && !item.classList.contains("active") && !item.classList.contains("cloned")) {
    const carousel = item.closest<HTMLElement>(".owl-carousel");
    const items = carousel ? [...carousel.querySelectorAll<HTMLElement>(".owl-item:not(.cloned)")] : [];
    const i = items.indexOf(item);
    const $ = jq();
    if (!carousel || i < 0 || !$ || !visible(carousel)) return null;
    await scrollTo(carousel, "center");
    $(carousel).trigger("to.owl.carousel", [i, 400]);
    const copy = await waitFor(() => showingCopy(el, item), 2000);
    await sleep(450);
    return copy && onShow(copy) ? copy : null;
  }
  return onShow(el) ? el : null;
}

// ─── show_section ─────────────────────────────────────────────────────────

function findHeading(heading: string): HTMLElement | null {
  const shown = headingEls();
  return (
    pick(heading, shown, headText) ??
    // The crawl's raw text, with a heading's line breaks run together.
    pick(heading, shown, (h) => clean(h.textContent)) ??
    pick(heading, headingEls(true).filter((h) => !shown.includes(h)), headText)
  );
}

/** The screen's height below what is pinned to its top once the page has
 *  scrolled: the header, and a sub-menu that sticks under it. */
function room(): number {
  const header = document.querySelector<HTMLElement>("header#masthead")?.offsetHeight ?? 0;
  const sub = document.querySelector<HTMLElement>(".explora-submenu.sticky-top")?.offsetHeight ?? 0;
  return window.innerHeight - Math.max(headerHeight(), header + sub) - 32;
}

/** The block a heading heads, as the crawler grouped its sections: the
 *  largest block around it that still fits the screen, going no further than
 *  its card, its pane or its component (`.component-*`, the theme's unit). */
function sectionOf(h: HTMLElement): HTMLElement {
  const max = room();
  let best: HTMLElement = h;
  for (let el = h.parentElement; el && el !== root() && el !== document.body; el = el.parentElement) {
    if (el.getBoundingClientRect().height > max) break;
    best = el;
    if (el.matches("[class*='component-'], .exp_component, .owl-item, .card, .panel, .tab-pane, li")) break;
  }
  return best;
}

const JUNK = "script, style, noscript, svg, svg *, template, select, option, header#masthead, .mobile-menu, .nav-mobile, [data-voqalize], .owl-item.cloned";

/** The elements under `scope` whose text contains `text`, smallest first. */
function containing(scope: Element, text: string): HTMLElement[] {
  const want = norm(text);
  if (!want) return [];
  const hits: [HTMLElement, number][] = [];
  for (const el of scope.querySelectorAll<HTMLElement>("*")) {
    if (el.closest(JUNK)) continue;
    const t = norm(el.textContent);
    if (t.includes(want)) hits.push([el, t.length]);
  }
  return hits.sort((a, b) => a[1] - b[1]).map(([el]) => el);
}

/** What to ring for an element that holds the words: its card, when the
 *  words are the card's title, else the element itself. */
function ringable(el: HTMLElement): HTMLElement {
  const card = el.closest<HTMLElement>(".card, .owl-item:not(.cloned) > *, li.list-group-item");
  if (card && card.getBoundingClientRect().height < window.innerHeight * 0.8 && el.matches("h2,h3,h4,h5,.h3,.h4,p,small,span,a,strong")) {
    if (clean(el.textContent).length < 80) return card;
  }
  return el;
}

/** Ring the smallest element under `scope` showing `text`; one in a closed
 *  pane or a carousel slide out of view is brought out first. */
async function ringText(text: string, scope: Element = root()): Promise<boolean> {
  // Smallest first: a visible wrapper also "contains" the words of the closed
  // pane or the carousel slide inside it, and the slide is what was meant.
  let el: HTMLElement | null = null;
  let tries = 0;
  for (const hit of containing(scope, text)) {
    if (onShow(hit)) {
      el = hit;
      break;
    }
    if (tries < 6 && revealable(hit)) {
      tries++;
      el = await reveal(hit);
      if (el) break;
    }
  }
  if (!el) {
    // A lodge's or a destination's name may be only in an image's `alt`.
    const want = norm(text);
    const img = [...scope.querySelectorAll<HTMLImageElement>("img[alt]")].find(
      (i) => onShow(i) && !i.closest(JUNK) && norm(i.alt).includes(want),
    );
    el = img ? (img.closest<HTMLElement>(".card, a, figure") ?? img) : null;
  }
  if (!el) return false;
  const target = ringable(el);
  const tall = target.getBoundingClientRect().height > window.innerHeight * 0.7;
  await scrollTo(target, tall ? "top" : "center");
  highlight(target);
  return true;
}

/** Open a tab or accordion by its label and ring it with what it opened. */
async function showTab(label: string): Promise<boolean> {
  const listed = tabTriggers();
  const all = [...listed, ...collapseTriggers().filter((t) => !listed.includes(t))];
  // A tab that is laid out first: the desktop row before its mobile copy.
  const t =
    pick(label, all.filter((x) => visible(x.el)), tabLabel) ?? pick(label, all, tabLabel);
  if (!t) return false;
  if (!(await openTrigger(t))) return false;
  const group: HTMLElement[] = visible(t.el) ? [t.el, t.pane] : [t.pane];
  // The home map's accordion: its row, from the destination's name down.
  const row = t.kind === "collapse" ? t.el.closest<HTMLElement>(".card, li, [id^=heading]")?.parentElement : null;
  const ring = row && row.contains(t.pane) && row.getBoundingClientRect().height < room() ? [row] : group;
  await scrollTo(ring[0], "top");
  highlight(ring);
  return true;
}

/** Scroll to a laid-out element's block and ring it. */
async function ringBlock(el: HTMLElement): Promise<void> {
  const section = sectionOf(el);
  await scrollTo(section, "top");
  highlight(section);
}

const TRIGGER = "[data-toggle], [role=tab], .tab-panels-nav li, .nav-link";

/** A laid-out label on the page that reads `label`: a heading, a title, a
 *  term, whose text equals it or starts with it (or, failing those, ends
 *  with it: "Suni" for "3. Suni"). For what a responsive copy hides: the
 *  desktop `h4` "3. Suni" beside the mobile accordion of the same name. */
function laidOutLabel(label: string): HTMLElement | null {
  const want = norm(label);
  if (!want) return null;
  const hits: [HTMLElement, number, number][] = [];
  for (const el of root().querySelectorAll<HTMLElement>("h1,h2,h3,h4,h5,h6,.h1,.h2,.h3,.h4,.h5,dt,strong,b,summary")) {
    // A tab's or an accordion's own label is opened, not ringed (`showTab`).
    if (el.closest(JUNK) || el.closest(SKIP) || el.closest(TRIGGER) || !onShow(el)) continue;
    const t = norm(el.innerText || el.textContent);
    if (!t || t.length > 200) continue;
    const rank = t === want ? 0 : t.startsWith(want) ? 1 : t.endsWith(want) && want.length > 2 ? 2 : -1;
    if (rank >= 0) hits.push([el, rank, t.length]);
  }
  hits.sort((a, b) => a[1] - b[1] || a[2] - b[2]);
  return hits[0]?.[0] ?? null;
}

/** What is showing, for an error the model can act on. */
function shownLabels(n = 20): string {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const l of [...context().headings, ...tabLabels(), ...faqs()]) {
    if (seen.has(norm(l))) continue;
    seen.add(norm(l));
    out.push(l);
  }
  return out.slice(0, n).join(" | ");
}

async function showSection({ heading, text }: { heading?: string | null; text?: string | null }) {
  if (!heading && !text) throw new Error("say which heading or text to show");
  if (heading) {
    const found = findHeading(heading);
    // A heading that is not laid out gives way to a laid-out label of the
    // same name before any pane is opened for it.
    const twin = found && !onShow(found) && !text ? laidOutLabel(heading) : null;
    if (twin) {
      await ringBlock(twin);
      return;
    }
    const h = found && (onShow(found) ? found : await reveal(found));
    if (found && !h && !text) {
      throw new Error(`"${heading}" is in a part of ${location.pathname} that cannot be opened; it shows: ${shownLabels()}`);
    }
    if (h) {
      if (text && (await ringText(text, sectionOf(h)))) return;
      if (text && (await ringText(text))) return;
      // The block from its top, which may be above the heading (a picture).
      const section = sectionOf(h);
      await scrollTo(section, "top");
      highlight(section);
      return;
    }
    if (await showTab(heading)) {
      if (text) await ringText(text);
      return;
    }
    if (!text) {
      const label = laidOutLabel(heading);
      if (label) {
        await ringBlock(label);
        return;
      }
      if (await ringText(heading)) return;
      throw new Error(`no heading "${heading}" on ${location.pathname}; it shows: ${shownLabels()}`);
    }
  }
  if (text && (await ringText(text))) return;
  throw new Error(`"${text}" is not on ${location.pathname}`);
}

// ─── open_faq ─────────────────────────────────────────────────────────────

async function openFaq({ question }: { question: string }) {
  if (!clean(question)) throw new Error("say which question to open");
  // Only triggers laid out at this width, or in a pane that can be opened.
  const triggers = collapseTriggers().filter((t) => !isQuestionLike(t.label));
  let t = pick(question, triggers.filter((x) => visible(x.el)), (x) => x.label);
  if (!t) {
    // Not an accordion that is showing: a question set as a heading, or a
    // laid-out label of that name (the desktop row a mobile accordion
    // copies), before any closed pane is opened for it.
    const q = pick(question, questionHeadings(new Set()).filter((x) => onShow(x.els[0])), (x) => x.q);
    if (q) {
      await scrollTo(q.els[0], "top");
      highlight(q.els);
      return;
    }
    const label = laidOutLabel(question);
    if (label) {
      await ringBlock(label);
      return;
    }
    t = pick(question, triggers, (x) => x.label);
  }
  if (t) {
    // A trigger in a closed pane: open the pane first; one that cannot be
    // opened gives way to a tab of the same name.
    if (!visible(t.el) && !(await reveal(t.el)) && (await showTab(t.label))) return;
    await openTrigger(t);
    const item = t.el.closest<HTMLElement>("li.list-group-item, .card") ?? null;
    const ring: HTMLElement[] = item && item.contains(t.pane) ? [item] : [t.el, t.pane].filter(visible);
    if (ring.length) {
      const tall = ring[0].getBoundingClientRect().height > window.innerHeight * 0.7;
      await scrollTo(ring[0], tall ? "top" : "center");
      highlight(ring);
      return;
    }
  }
  const q = pick(question, questionHeadings(new Set()), (x) => x.q);
  if (q) {
    await scrollTo(q.els[0], "top");
    highlight(q.els);
    return;
  }
  const known = faqs().slice(0, 15).join(" | ");
  throw new Error(
    `no question "${question}" on ${location.pathname}; ` +
      (known ? `its questions: ${known}` : `it has no questions; it shows: ${shownLabels()}`),
  );
}

// ─── navigate ─────────────────────────────────────────────────────────────

const strip = (p: string) => (p || "/").replace(/\/+$/, "").toLowerCase() || "/";

/**
 * Load one of www.explora.com's pages in this tab. The move to make on it
 * (a heading, words, a question) is kept by the hub for the next page, which
 * makes it once it is up (`pendingMove` in `content.ts`). The wait for his
 * voice before the load is the call's, not this.
 */
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
  if (typeof path !== "string" || !path) throw new Error(`not a path: ${path}`);
  const target = new URL(path, SITE_ORIGIN);
  if (!isExplora(target.host)) throw new Error(`${target.href} is not on www.explora.com`);
  if (strip(target.pathname) === strip(location.pathname) && target.search === location.search) {
    if (faq) return openFaq({ question: faq });
    if (heading || text) return showSection({ heading, text });
    window.scrollTo({ top: 0, behavior: "smooth" });
    return;
  }
  const then: Then | undefined = faq
    ? { command: "open_faq", payload: { question: faq } }
    : heading || text
      ? { command: "show_section", payload: { heading: heading ?? null, text: text ?? null } }
      : undefined;
  clearHighlight();
  await loadThen(target.href, then);
}

// ─── Links stay in the tab while a call is live ───────────────────────────

const BLANK = "data-voqalize-target";

function keepInTab(a: HTMLAnchorElement): void {
  if (a.target !== "_blank" || !OURS.test(a.href)) return;
  a.setAttribute(BLANK, a.target);
  a.removeAttribute("target");
}

function keepLinksInTab(): () => void {
  document.querySelectorAll<HTMLAnchorElement>("a[target=_blank]").forEach(keepInTab);
  const obs = new MutationObserver((records) => {
    for (const r of records) {
      if (r.type === "attributes" && r.target instanceof HTMLAnchorElement) keepInTab(r.target);
      for (const n of r.addedNodes) {
        if (!(n instanceof Element)) continue;
        if (n instanceof HTMLAnchorElement) keepInTab(n);
        n.querySelectorAll?.<HTMLAnchorElement>("a[target=_blank]").forEach(keepInTab);
      }
    }
  });
  obs.observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ["target", "href"] });
  return () => {
    obs.disconnect();
    document.querySelectorAll<HTMLAnchorElement>(`a[${BLANK}]`).forEach((a) => {
      a.target = a.getAttribute(BLANK) ?? "_blank";
      a.removeAttribute(BLANK);
    });
  };
}

// ─── Reporting ────────────────────────────────────────────────────────────

/**
 * Report the page, once the call is up on it. Every page is a fresh load, so
 * there are no route changes to watch: this page is reported once, and again
 * if its headings grow as late parts of it render (a carousel, the reviews).
 */
function start(emit: (event: string, payload: unknown) => void): () => void {
  const restore = keepLinksInTab();
  let last = JSON.stringify(context());
  emit("page_changed", JSON.parse(last));
  let timer: ReturnType<typeof setTimeout> | null = null;
  const obs = new MutationObserver(() => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      const now = context();
      const s = JSON.stringify(now);
      if (s === last) return;
      const before = JSON.parse(last) as PageContext;
      last = s;
      // Only what the brain can act on: a new heading, question or tab.
      const grew =
        now.headings.length !== before.headings.length ||
        now.faqs.length !== before.faqs.length ||
        now.tabs.length !== before.tabs.length;
      if (grew) emit("page_changed", now);
    }, 1200);
  });
  obs.observe(root(), { childList: true, subtree: true });
  const stopWatching = setTimeout(() => obs.disconnect(), 20_000);
  return () => {
    obs.disconnect();
    clearTimeout(stopWatching);
    if (timer) clearTimeout(timer);
    restore();
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

if (isExplora(location.host) && !window.voqalizeExplora) {
  styleThePage();
  window.voqalizeExplora = { run, context, start, commands: Object.keys(COMMANDS) } satisfies Adapter;
}

export {};
