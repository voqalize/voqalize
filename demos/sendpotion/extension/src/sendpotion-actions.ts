/**
 * The site adapter: drive sendpotion.com and blog.sendpotion.com from the
 * outside, with no help from SendPotion's developers.
 *
 * The brain sends a Voqalize `ui-command` ({command, payload}) and `run`
 * performs it on the page in front; the page reports back through `start`,
 * which calls `emit(event, payload)` for every route change, booking step and
 * result, whoever caused it. Opening blog posts in new tabs and the reading
 * list are the call's (`content.ts`), not the page's.
 *
 * What the two hosts are, for a script like this:
 *
 *   - **sendpotion.com** has its own client-side router: a click on a same-host
 *     link is taken by a listener on `document`, which fetches the next page and
 *     swaps its `#view-main`, so the call survives every move. A move is made
 *     the way a visitor makes it, by clicking a link. The page does not scroll
 *     the window: its content sits in a smooth-scrollbar container that GSAP's
 *     ScrollTrigger follows, which `early.ts` finds before the site starts. The
 *     demo booking form is a Calendly frame, driven by `calendly.ts` inside it.
 *   - **blog.sendpotion.com** is a Medium publication: client-side too, and it
 *     scrolls the window.
 *
 * Every anchor below is one of their visible texts (a heading, a question, a
 * plan name), their component classes (`pt-faq-*`, `pt-pricing-*`), or
 * Calendly's own `aria-label`s and `data-*`.
 */

declare global {
  interface Window {
    voqalizeSendPotion?: Adapter;
  }
}

export interface Adapter {
  /** Perform one of the brain's page Actions. Never throws. */
  run(command: string, payload: unknown): Promise<{ ok: boolean; error?: string }>;
  /** What the visitor is looking at now, as a `page_changed` payload. */
  context(): PageContext;
  /** Report route changes and the booking's steps through `emit`, until the
   *  returned stop. The page as it stands is reported first. */
  start(emit: (event: string, payload: unknown) => void): () => void;
  /** The Actions `run` performs. */
  readonly commands: readonly string[];
}

export interface PageContext {
  site: "site" | "blog";
  url: string;
  path: string;
  title: string;
  kind: "page" | "post" | "blog";
  headings: string[];
  faqs: string[];
  plans: string[];
}

const RING = "#832EC4";
const RING_MS = 5500;
const WAIT_MS = 8000;
const MAX_HEADINGS = 50;
const MAX_FAQS = 30;

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const clean = (s: string | null | undefined) => (s ?? "").replace(/\s+/g, " ").trim();
/** For matching what the brain said against what the page shows. */
const norm = (s: string | null | undefined) =>
  clean(s)
    .toLowerCase()
    .replace(/[‘’]/g, "'")
    .replace(/[“”]/g, '"')
    .replace(/[‐-―]/g, "-")
    .replace(/\s*&\s*/g, " and ")
    // The crawl writes "…" where the home headline types a word that cycles.
    .replace(/…/g, "")
    .replace(/[.:?!\s]+$/, "")
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

const BLOG = /(^|\.)blog\.sendpotion\.com$/i.test(location.host);
const SITE_ORIGIN = "https://sendpotion.com";

function main(): HTMLElement {
  if (BLOG) return document.querySelector<HTMLElement>("article") ?? document.querySelector("main") ?? document.body;
  return document.getElementById("view-main") ?? document.body;
}

// ─── Scrolling ────────────────────────────────────────────────────────────

function scroller() {
  const all = [...(window.__voqalizeScrollers ?? [])].filter((s) => s.containerEl.isConnected);
  return all[all.length - 1] ?? null;
}

/** The height of whatever is pinned to the top of the viewport. */
function headerHeight(): number {
  const candidates = [
    ...document.querySelectorAll<HTMLElement>(".pt-navbar, header, nav, [data-testid='headerContainer']"),
  ];
  let h = 0;
  for (const el of candidates) {
    if (el.closest("[data-voqalize]")) continue;
    const pos = getComputedStyle(el).position;
    const r = el.getBoundingClientRect();
    // SendPotion's navbar floats 30 px below the top edge.
    if ((pos === "fixed" || pos === "sticky") && r.top <= 60 && r.height < 160) h = Math.max(h, r.bottom);
  }
  return h;
}

/** Scroll so `el` sits under the header (`top`) or in the middle of the screen. */
async function scrollTo(el: Element, align: "top" | "center" = "top"): Promise<void> {
  const sb = scroller();
  for (let pass = 0; pass < 2; pass++) {
    const r = el.getBoundingClientRect();
    if (sb) {
      const c = sb.containerEl.getBoundingClientRect();
      const offset = align === "center" ? (c.height - Math.min(r.height, c.height)) / 2 : headerHeight() + 24;
      const y = Math.min(Math.max(sb.offset.y + r.top - c.top - offset, 0), sb.limit.y);
      if (Math.abs(y - sb.offset.y) < 8) return;
      sb.scrollTo(sb.offset.x, y, 900);
      await sleep(1000);
    } else {
      const offset =
        align === "center" ? (window.innerHeight - Math.min(r.height, window.innerHeight)) / 2 : headerHeight() + 24;
      const y = Math.max(r.top + window.scrollY - offset, 0);
      if (Math.abs(y - window.scrollY) < 8) return;
      window.scrollTo({ top: y, behavior: "smooth" });
      await sleep(900);
    }
    // Pinned sections and reveal animations move things as the page scrolls:
    // one correction, then it stands.
  }
}

async function scrollToTopOfPage(): Promise<void> {
  const sb = scroller();
  if (sb) sb.scrollTo(sb.offset.x, 0, 700);
  else window.scrollTo({ top: 0, behavior: "smooth" });
  await sleep(750);
}

// ─── The ring ─────────────────────────────────────────────────────────────
// Drawn over the page, never on SendPotion's own elements. Fixed, and moved
// with its target every frame, because the content is translated by the
// scroller rather than scrolled.

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
      border: `2px solid ${RING}`,
      borderRadius: "10px",
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
  if (document.querySelector("style[data-voqalize=sendpotion]")) return;
  const style = document.createElement("style");
  style.setAttribute("data-voqalize", "sendpotion");
  // Tushar takes the corner SendPotion's Intercom launcher sits in, and the
  // blog's reCAPTCHA badge; both stand aside while the extension runs.
  style.textContent = `
    .intercom-lightweight-app, #intercom-container, .intercom-launcher,
    .intercom-launcher-frame, .intercom-namespace { display: none !important; }
    .grecaptcha-badge { visibility: hidden !important; }
    @keyframes voqalize-ring {
      0%, 100% { box-shadow: 0 0 0 0 rgba(131, 46, 196, 0.45); }
      50% { box-shadow: 0 0 0 9px rgba(131, 46, 196, 0); }
    }
  `;
  document.head.appendChild(style);
}

// ─── What the page shows ──────────────────────────────────────────────────

function faqItems(): HTMLElement[] {
  if (BLOG) return [];
  return [...main().querySelectorAll<HTMLElement>(".pt-faq-item")].filter((i) => i.querySelector(".pt-faq-title"));
}

const faqQuestion = (item: Element) => clean(item.querySelector(".pt-faq-title")?.textContent);

function plans(): HTMLElement[] {
  return BLOG ? [] : [...main().querySelectorAll<HTMLElement>(".pt-pricing-item")];
}

/** Headings the visitor can be taken to: not the FAQ questions, which are
 *  `open_faq`'s, and not the site's footer. */
function headings(): HTMLElement[] {
  const root = main();
  return [...root.querySelectorAll<HTMLElement>("h1, h2, h3, h4")].filter(
    (h) => !h.closest(".pt-faq-item, footer, .pt-footer, [data-voqalize]") && headText(h).length > 1,
  );
}

/** A heading as it reads: the site splits its headings into lines and letters
 *  and breaks them with `<br>`, so the rendered text, where a break is a space
 *  and a word the heading cycles through but hides is not there. */
function headText(h: HTMLElement): string {
  // The home headline types a word that cycles (sales, marketing, support):
  // it reads up to that word, then "…", as the crawl recorded it.
  const typed = h.querySelector("#typed");
  if (typed) {
    const before = document.createRange();
    before.setStart(h, 0);
    before.setEndBefore(typed);
    return `${clean(before.toString())} …`;
  }
  return clean(h.innerText || h.textContent);
}

function kind(): PageContext["kind"] {
  if (!BLOG) return "page";
  return document.querySelector("article h1, h1[data-testid='storyTitle']") ? "post" : "blog";
}

function context(): PageContext {
  const seen = new Set<string>();
  const hs: string[] = [];
  for (const h of headings()) {
    const t = headText(h);
    if (seen.has(norm(t))) continue;
    seen.add(norm(t));
    hs.push(t);
    if (hs.length >= MAX_HEADINGS) break;
  }
  return {
    site: BLOG ? "blog" : "site",
    url: location.href,
    path: location.pathname,
    title: document.title,
    kind: kind(),
    headings: hs,
    faqs: faqItems().map(faqQuestion).slice(0, MAX_FAQS),
    plans: plans().map((p) => clean(p.querySelector(".pt-pricing-plan")?.textContent)).filter(Boolean),
  };
}

// ─── navigate ─────────────────────────────────────────────────────────────

const strip = (p: string) => (p || "/").replace(/\/+$/, "") || "/";
const samePath = (a: string, b: string) => strip(a).toLowerCase() === strip(b).toLowerCase();

/** The new page has rendered: its content is in and the DOM has stopped
 *  changing for a moment. */
async function settled(): Promise<void> {
  await waitFor(() => main().querySelector("h1, h2"), 4000);
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

async function goTo(path: string): Promise<void> {
  if (typeof path !== "string") throw new Error(`not a path: ${path}`);
  const target = new URL(path, BLOG ? location.origin : SITE_ORIGIN);
  if (target.host !== location.host) throw new Error(`${target.href} is not on this tab's site`);
  if (samePath(location.pathname, target.pathname)) return;
  const from = location.pathname;
  const title = document.title;
  // A link like any other, so the site's own router takes it.
  const a = document.createElement("a");
  a.href = target.href;
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  a.remove();
  const arrived = await waitFor(() => !samePath(location.pathname, from), WAIT_MS);
  if (!arrived) throw new Error(`the page did not move to ${path}`);
  await waitFor(() => document.title !== title, 3000);
  await transitioned();
  await settled();
}

/** The site's page transition has finished: its overlay (`.pt-loader`, shown
 *  `-visible` while the next page comes in) is gone. A scroll or a click made
 *  under it stalls the transition, and the overlay then stays over the page. */
async function transitioned(): Promise<void> {
  if (BLOG) return;
  await sleep(150);
  await waitFor(() => !document.querySelector(".pt-loader.-visible"), 6000);
  await sleep(250);
}

async function navigate({ path, heading, text }: { path: string; heading?: string | null; text?: string | null }) {
  const here = samePath(location.pathname, new URL(path, location.origin).pathname);
  await goTo(path);
  if (heading || text) return showSection({ heading, text });
  if (here) await scrollToTopOfPage();
}

// ─── show_section ─────────────────────────────────────────────────────────

function findHeading(heading: string): HTMLElement | null {
  const want = norm(heading);
  if (!want) return null;
  const all = headings();
  const t = (h: HTMLElement) => norm(headText(h));
  // The crawl may have read a heading's raw text, with its line breaks run
  // together: that spelling finds it too.
  const raw = (h: HTMLElement) => norm(h.textContent);
  return (
    all.find((h) => t(h) === want || raw(h) === want) ??
    all.find((h) => t(h).startsWith(want)) ??
    all.find((h) => want.startsWith(t(h)) && t(h).length > 3) ??
    all.find((h) => t(h).includes(want)) ??
    null
  );
}

/** The block a heading heads: its `<section>`, or the nearest ancestor that
 *  holds more than the heading itself. */
function sectionOf(h: HTMLElement): HTMLElement {
  // A heading on a card is the card's: a tab's pane, a feature, a plan.
  const card = h.closest<HTMLElement>(
    ".pt-program-item, .pt-explore-detail, .pt-pricing-item, .pt-faq-item, .pt-review-item",
  );
  if (card) return card;
  const s = h.closest<HTMLElement>("section");
  if (s && s !== main()) return s;
  let el = h.parentElement;
  while (el && el !== main() && clean(el.textContent).length <= clean(h.textContent).length + 20) {
    el = el.parentElement;
  }
  return el ?? h;
}

/** The smallest visible element in `root` whose text contains `text`; a plan
 *  name is its whole plan card. */
function smallestContaining(root: Element, text: string): HTMLElement | null {
  const want = norm(text);
  if (!want) return null;
  let best: HTMLElement | null = null;
  let bestLen = Infinity;
  for (const el of root.querySelectorAll<HTMLElement>("*")) {
    if (el.closest("[data-voqalize]") || !visible(el)) continue;
    const t = norm(el.textContent);
    if (!t.includes(want) || t.length >= bestLen) continue;
    best = el;
    bestLen = t.length;
  }
  if (!best) {
    // A logo says its name only in its `alt`: the integrations wall, the
    // customers strip.
    const img = [...root.querySelectorAll<HTMLImageElement>("img[alt], img[title]")].find(
      (i) => visible(i) && norm(i.alt || i.title).includes(want),
    );
    return img ? (img.closest<HTMLElement>("a, li, figure") ?? img) : null;
  }
  const card = best.closest<HTMLElement>(".pt-pricing-item, .pt-faq-item, li, tr");
  if (card && root.contains(card) && best.closest(".pt-pricing-plan, .pt-faq-title")) return card;
  return best;
}

// ─── Content behind a tab or a "Load more" ────────────────────────────────
// The use-case pages group their content under tabs (`.pt-program-nav`
// buttons over `.pt-program-item` panes, the inactive ones `display: none`),
// and the reviews page keeps most reviews behind "Load more". What is asked
// for there is first brought out the way a visitor would, by a click.

/** If `el` sits in a tab pane that is not showing, click its tab. */
async function reveal(el: HTMLElement): Promise<void> {
  const pane = el.closest<HTMLElement>(".pt-program-item");
  if (!pane || shown(pane)) return;
  // A tab and its panes share `data-program` (each tab shows two panes).
  const box = pane.closest(".pt-program-content") ?? pane.parentElement?.parentElement ?? main();
  const program = pane.getAttribute("data-program");
  const nav = [...box.querySelectorAll<HTMLElement>("button.pt-program-nav")].find(
    (b) => b.getAttribute("data-program") === program,
  );
  if (!nav) return;
  await scrollTo(nav, "top");
  nav.click();
  await waitFor(() => visible(el), 2000);
  await sleep(350);
}

/** An element with this text in a tab pane that is not showing. */
function inHiddenPane(text: string): HTMLElement | null {
  const want = norm(text);
  let best: HTMLElement | null = null;
  for (const pane of main().querySelectorAll<HTMLElement>(".pt-program-item")) {
    if (shown(pane)) continue;
    for (const el of pane.querySelectorAll<HTMLElement>("h2, h3, h4, p, li, span")) {
      const t = norm(el.textContent);
      if (t.includes(want) && (!best || t.length < norm(best.textContent).length)) best = el;
    }
  }
  return best;
}

async function loadMore(): Promise<boolean> {
  const more = main().querySelector<HTMLElement>(".pt-review-more");
  if (!more || !visible(more)) return false;
  more.click();
  await sleep(800);
  return true;
}

async function showSection({ heading, text }: { heading?: string | null; text?: string | null }) {
  const h = heading ? findHeading(heading) : null;
  if (heading && !h && !text) {
    const known = context().headings.slice(0, 20).join(" | ");
    throw new Error(`no heading "${heading}" on ${location.pathname}; it has: ${known}`);
  }
  if (h) await reveal(h);
  if (text) {
    const find = () => (h && smallestContaining(sectionOf(h), text)) ?? smallestContaining(main(), text);
    let el = find();
    if (!el) {
      const hidden = inHiddenPane(text);
      if (hidden) {
        await reveal(hidden);
        el = find();
      } else if (await loadMore()) {
        el = find();
      }
    }
    if (!el) throw new Error(`"${text}" is not on ${location.pathname}`);
    // A card taller than most of the screen is read from its top.
    const tall = el.getBoundingClientRect().height > window.innerHeight * 0.7;
    await scrollTo(el, tall ? "top" : "center");
    highlight(el);
    return;
  }
  if (!h) throw new Error("say which heading or text to show");
  await scrollTo(h, "top");
  const section = sectionOf(h);
  const r = section.getBoundingClientRect();
  highlight(r.height > window.innerHeight * 1.3 ? h : section);
}

// ─── open_faq ─────────────────────────────────────────────────────────────

async function openFaq({ question }: { question: string }) {
  const want = norm(question);
  const all = faqItems();
  const q = (i: Element) => norm(faqQuestion(i));
  const item =
    all.find((i) => q(i) === want) ??
    all.find((i) => q(i).startsWith(want)) ??
    all.find((i) => want.startsWith(q(i))) ??
    all.find((i) => q(i).includes(want));
  if (!item) {
    const known = all.map(faqQuestion).slice(0, 15).join(" | ");
    throw new Error(`no FAQ "${question}" on ${location.pathname}${known ? `; it has: ${known}` : ""}`);
  }
  const info = item.querySelector<HTMLElement>(".pt-faq-info");
  const open = () => (info ? info.getBoundingClientRect().height > 8 : item.classList.contains("-active"));
  await scrollTo(item, "center");
  if (!open()) {
    item.querySelector<HTMLElement>(".pt-faq-toggle")?.click();
    await waitFor(open, 2000);
    await sleep(450);
  }
  await scrollTo(item, "center");
  highlight(item);
}

// ─── book_demo: the Calendly frame on /demo/ ──────────────────────────────

interface BookOrder {
  day?: string | null;
  time?: string | null;
  name?: string | null;
  email?: string | null;
  notes?: string | null;
}

const CALENDLY = "https://calendly.com";
let calls = 0;

function calendlyFrame(): HTMLIFrameElement | null {
  return document.querySelector<HTMLIFrameElement>("iframe[src*='calendly.com']");
}

/** One order to the frame (`calendly.ts`), answered with its state. */
function toFrame(frame: HTMLIFrameElement, cmd: string, order?: unknown, ms = 15000) {
  const id = ++calls;
  return new Promise<{ error: string | null; state: unknown } | null>((resolve) => {
    const timer = setTimeout(() => done(null), ms);
    const on = (e: MessageEvent) => {
      if (e.origin !== CALENDLY) return;
      const reply = (e.data as { voqalizeCalendlyDone?: { id: number; error: string | null; state: unknown } })
        ?.voqalizeCalendlyDone;
      if (reply?.id === id) done(reply);
    };
    function done(v: { error: string | null; state: unknown } | null) {
      clearTimeout(timer);
      window.removeEventListener("message", on);
      resolve(v);
    }
    window.addEventListener("message", on);
    frame.contentWindow?.postMessage({ voqalizeCalendlyCmd: { id, cmd, order } }, CALENDLY);
  });
}

async function bookDemo(order: BookOrder) {
  if (BLOG) throw new Error("the demo booking is on sendpotion.com/demo/");
  await goTo("/demo/");
  const frame = await waitFor(calendlyFrame, WAIT_MS);
  if (!frame) throw new Error("the booking calendar is not on /demo/");
  await scrollTo(frame, "top");
  highlight(frame);
  // The frame's script answers once Calendly has drawn the calendar.
  let answered = null as Awaited<ReturnType<typeof toFrame>>;
  for (let i = 0; i < 12 && !answered; i++) answered = await toFrame(frame, "state", undefined, 1000);
  if (!answered) throw new Error("the booking calendar did not load");
  const wants = order.day || order.time || order.name || order.email || order.notes;
  if (!wants) {
    emit("demo_state", answered.state);
    return;
  }
  const done = await toFrame(frame, "book", {
    day: order.day,
    time: order.time,
    fill: { name: order.name, email: order.email, notes: order.notes },
  });
  if (!done) throw new Error("the booking calendar did not answer");
  emit("demo_state", done.state);
  highlight(frame);
  if (done.error) throw new Error(done.error);
}

/** What the frame reports by itself: the visitor's own clicks in it, and
 *  their press of Schedule Event. */
function watchCalendly(): void {
  window.addEventListener("message", (e: MessageEvent) => {
    if (e.origin !== CALENDLY) return;
    const data = e.data as { voqalizeCalendly?: unknown; voqalizeCalendlyScheduled?: unknown };
    if (data?.voqalizeCalendly) emit("demo_state", data.voqalizeCalendly);
    const s = data?.voqalizeCalendlyScheduled as
      | { date?: string; time?: string; filled?: unknown; blocked?: boolean }
      | undefined;
    if (s) {
      emit("demo_scheduled", { date: s.date ?? "", time: s.time ?? "", filled: s.filled ?? {}, blocked: Boolean(s.blocked) });
    }
  });
}

// ─── Reporting ────────────────────────────────────────────────────────────

let emitter: ((event: string, payload: unknown) => void) | null = null;
function emit(event: string, payload: unknown): void {
  emitter?.(event, payload);
}

let lastUrl: string | null = null;
let reportTimer: ReturnType<typeof setTimeout> | null = null;
function routeChanged(): void {
  if (reportTimer) clearTimeout(reportTimer);
  reportTimer = setTimeout(async () => {
    const here = location.origin + location.pathname;
    if (here === lastUrl) return;
    lastUrl = here;
    clearHighlight();
    await settled();
    emit("page_changed", context());
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

function start(next: (event: string, payload: unknown) => void): () => void {
  emitter = next;
  lastUrl = location.origin + location.pathname;
  emit("page_changed", context());
  return () => {
    if (emitter === next) emitter = null;
  };
}

const COMMANDS: Record<string, (payload: never) => Promise<void>> = {
  navigate,
  show_section: showSection,
  open_faq: openFaq,
  book_demo: bookDemo,
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

if (!window.voqalizeSendPotion) {
  styleThePage();
  watchRoutes();
  watchCalendly();
  window.voqalizeSendPotion = { run, context, start, commands: Object.keys(COMMANDS) };
}

export {};
