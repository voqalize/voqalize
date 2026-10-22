/**
 * What both of Clini's adapters do to a page they do not own: wait for it,
 * find words on it, scroll the window under the fixed header, draw the ring,
 * and fill a field the way a visitor's typing would.
 *
 * `clini-actions.ts` drives www.clini.cl (Webflow) and `agenda-actions.ts`
 * drives the booking on agenda-web.clini.cl (ASP.NET, Bootstrap); both scroll
 * the window, and neither page is ours, so the ring is drawn over the page and
 * never on Clini's own elements.
 */

/** CLINI's own accent: the pink of every "Reservar hora" and "¡Agendar
 *  evaluación!" button (`.w-button`, rgb(221, 52, 136)). The brand's purple
 *  (rgb(91, 57, 142)) is the colour of the headings and the hero, so a purple
 *  ring would vanish on half the site; the pink reads on white, lilac and
 *  purple alike, and is already the colour the site uses for "look here". */
export const RING = "rgb(221, 52, 136)";
const RING_MS = 5500;
export const WAIT_MS = 8000;

export const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
export const clean = (s: string | null | undefined) => (s ?? "").replace(/\s+/g, " ").trim();

/**
 * For matching what the brain said against what the page shows: lower case,
 * without accents (á → a, ñ → n), with straight quotes and dashes, and without
 * the opening "¿"/"¡" and closing punctuation either side may or may not have.
 */
export const norm = (s: string | null | undefined) =>
  clean(s)
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[‘’´`]/g, "'")
    .replace(/[“”«»]/g, '"')
    .replace(/[‐-―]/g, "-")
    .replace(/\s*&\s*/g, " y ")
    .replace(/[¿¡]/g, "")
    .replace(/…/g, "")
    .replace(/^[\s"']+|[\s"'.:;,?!]+$/g, "")
    .trim();

export const visible = (el: Element | null | undefined): el is HTMLElement => {
  if (!el) return false;
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
};

/** `visible` as a plain answer, where a narrowing guard would narrow too far. */
export const shown = (el: Element): boolean => visible(el);

export async function waitFor<T>(fn: () => T | null | undefined | false, ms = WAIT_MS): Promise<T | null> {
  const until = Date.now() + ms;
  for (;;) {
    const v = fn();
    if (v) return v;
    if (Date.now() > until) return null;
    await sleep(100);
  }
}

/** Page order, for lists gathered from several selectors. */
export const inOrder = (a: Node, b: Node) =>
  a === b ? 0 : a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;

/** The best match for what the brain said among `items`: the same words, then
 *  one that starts with them, then one they start with, then one that holds
 *  them. */
export function best<T>(items: T[], text: (t: T) => string, said: string): T | null {
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

// ─── Scrolling ────────────────────────────────────────────────────────────

/** Bars that can be pinned to the top: Clini's marquee bar (35 px) with the
 *  Webflow navbar under it (61 px; 56 on a phone), and agenda-web's menu. */
const BARS = ".header-fixed-clini, .w-nav, header, .navbar, nav, #cliniMainMenu";

/**
 * The height of whatever is pinned to the top of the viewport. Clini stacks
 * two fixed bars (the navbar's top is the marquee's bottom), so a bar counts
 * when it starts where the bars above it end.
 */
export function headerHeight(): number {
  const bars = [...document.querySelectorAll<HTMLElement>(BARS)]
    .map((el) => ({ el, r: el.getBoundingClientRect() }))
    .filter(({ el, r }) => {
      if (r.height <= 0 || r.height > 220 || r.top < -2) return false;
      const pos = getComputedStyle(el).position;
      return pos === "fixed" || pos === "sticky";
    })
    .sort((a, b) => a.r.top - b.r.top);
  let h = 0;
  for (const { r } of bars) if (r.top <= h + 4) h = Math.max(h, r.bottom);
  return h;
}

/** How far `el` is from where it should sit: under the header (`top`) or in
 *  the middle of the screen. */
function distance(el: Element, align: "top" | "center"): number {
  const r = el.getBoundingClientRect();
  const top = headerHeight() + 8;
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
 * the screen, and check that it did. Images load and reveals play as they come
 * into view, so it measures again and corrects, up to twice. The page's
 * `scroll-behavior` is `auto` and there is no scroll library.
 */
export async function scrollTo(el: Element, align: "top" | "center" = "top"): Promise<void> {
  for (let pass = 0; pass < 3; pass++) {
    const delta = distance(el, align);
    if (Math.abs(delta) < 12) return;
    const max = document.documentElement.scrollHeight - window.innerHeight;
    const y = Math.min(Math.max(window.scrollY + delta, 0), max);
    if (Math.abs(y - window.scrollY) < 8) return;
    window.scrollBy({ top: y - window.scrollY, behavior: "smooth" });
    await scrollEnded();
  }
}

export async function scrollToTopOfPage(): Promise<void> {
  window.scrollTo({ top: 0, behavior: "smooth" });
  await scrollEnded();
}

// ─── The ring ─────────────────────────────────────────────────────────────
// Drawn over the page, never on Clini's own elements. Fixed, and moved with
// its target every frame, so it follows a scroll.

let rings: { el: HTMLElement; targets: Element[] }[] = [];
let ringFrame = 0;
let ringTimer: ReturnType<typeof setTimeout> | null = null;

export function boxOf(targets: Element[]) {
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
    ring.el.style.opacity = "1";
    Object.assign(ring.el.style, {
      transform: `translate(${b.left - 6}px, ${b.top - 6}px)`,
      width: `${b.right - b.left + 12}px`,
      height: `${b.bottom - b.top + 12}px`,
    });
  }
  ringFrame = requestAnimationFrame(follow);
}

/** Ring each group: one element, or several ringed as one box. */
export function highlight(...groups: (Element | Element[])[]): void {
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
      border: "3px solid var(--voqalize-ring)",
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
  ringTimer = setTimeout(clearHighlight, RING_MS);
}

export function clearHighlight(): void {
  if (ringTimer) clearTimeout(ringTimer);
  cancelAnimationFrame(ringFrame);
  rings.forEach((r) => r.el.remove());
  rings = [];
}

export function styleThePage(): void {
  if (document.querySelector("style[data-voqalize=clini]")) return;
  const style = document.createElement("style");
  style.setAttribute("data-voqalize", "clini");
  style.textContent = `
    :root { --voqalize-ring: ${RING}; }
    @keyframes voqalize-ring {
      0%, 100% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--voqalize-ring) 55%, transparent); }
      50% { box-shadow: 0 0 0 10px color-mix(in srgb, var(--voqalize-ring) 0%, transparent); }
    }
  `;
  (document.head ?? document.documentElement).appendChild(style);
}

// ─── Waiting for a page ───────────────────────────────────────────────────

/**
 * The page has settled: loaded (or near enough), its fonts in, and the DOM
 * quiet for a moment. Images that arrive later move the page under a scroll;
 * `scrollTo` measures again and corrects for that.
 */
export async function settled(): Promise<void> {
  if (document.readyState !== "complete") {
    await Promise.race([
      new Promise<void>((r) => window.addEventListener("load", () => r(), { once: true })),
      sleep(2500),
    ]);
  }
  await Promise.race([document.fonts?.ready, sleep(2000)]);
  await quiet(document.body, 450, 3000);
}

/** `root` has not changed for `ms`, or `cap` has passed. */
export function quiet(root: Node, ms = 350, cap = 3000): Promise<void> {
  return new Promise<void>((resolve) => {
    let timer = setTimeout(done, ms);
    const obs = new MutationObserver(() => {
      clearTimeout(timer);
      timer = setTimeout(done, ms);
    });
    obs.observe(root, { childList: true, subtree: true, attributes: true, characterData: true });
    const stop = setTimeout(done, cap);
    function done() {
      obs.disconnect();
      clearTimeout(timer);
      clearTimeout(stop);
      resolve();
    }
  });
}

// ─── Filling a field ──────────────────────────────────────────────────────

/**
 * Set a field the way typing does: through the prototype's own value setter
 * (so a framework that tracks the value sees the change), then `input`,
 * `change` and `blur`, which run the site's own formatters and checks (the
 * RUT hyphen, the "+56 9 XXXX XXXX" phone mask). Never a key event, so no
 * Enter ever reaches a form.
 */
export function setValue(el: HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement, value: string): void {
  const proto =
    el instanceof HTMLSelectElement
      ? HTMLSelectElement.prototype
      : el instanceof HTMLTextAreaElement
        ? HTMLTextAreaElement.prototype
        : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value")?.set?.call(el, value);
  for (const type of ["input", "change"]) el.dispatchEvent(new Event(type, { bubbles: true }));
  el.dispatchEvent(new Event("blur"));
  el.dispatchEvent(new FocusEvent("focusout", { bubbles: true }));
}

/** The option of `select` whose text (or value) best matches `said`, with
 *  `aliases` (normalized word → option text) tried first. */
export function pickOption(
  select: HTMLSelectElement,
  said: string,
  aliases: Record<string, string> = {},
): HTMLOptionElement | null {
  const options = [...select.options].filter((o) => o.value);
  const want = norm(said);
  for (const [word, text] of Object.entries(aliases)) {
    if (want.includes(word)) {
      // The alias names the option by its label or by its value, which on
      // the LASIK form differ ("Santiago - Metro los Leones" is "Santiago - Lyon").
      const hit = best(options, (o) => o.text, text) ?? best(options, (o) => o.value, text);
      if (hit) return hit;
    }
  }
  const squash = (s: string) => norm(s).replace(/[^a-z0-9]/g, "");
  return (
    best(options, (o) => o.text, said) ??
    best(options, (o) => o.value, said) ??
    options.find((o) => squash(o.text) === squash(said)) ??
    options.find((o) => squash(said).includes(squash(o.text)) && squash(o.text).length > 3) ??
    null
  );
}

/** Only the digits of a Chilean mobile, without +56: "+56 9 1234 5678" → "912345678". */
export function chileanMobile(said: string): string {
  let digits = said.replace(/\D/g, "");
  if (digits.length === 11 && digits.startsWith("56")) digits = digits.slice(2);
  return digits;
}

// ─── A move left for the next page ────────────────────────────────────────

/** Where a move that loads another page leaves the rest of itself. Per
 *  origin, as `sessionStorage` is, which is right: a page load never leaves
 *  its origin here (another host opens in a tab of its own). */
const THEN_KEY = "voqalize.clini.then";
/** A move left longer ago than this belongs to some other visit. */
const THEN_MAX_AGE_MS = 60_000;

export interface Leftover {
  command: string;
  payload: unknown;
}

/** Leave `move` for the next page of this tab (or forget any, with null). */
export function leave(move: Leftover | null): void {
  try {
    if (move) sessionStorage.setItem(THEN_KEY, JSON.stringify({ ...move, at: Date.now() }));
    else sessionStorage.removeItem(THEN_KEY);
  } catch {
    // Storage refused: the page still loads, at its top.
  }
}

/** What the last page left to do here, taken once. */
export function takeLeftover(): Leftover | null {
  try {
    const raw = sessionStorage.getItem(THEN_KEY);
    if (!raw) return null;
    sessionStorage.removeItem(THEN_KEY);
    const then = JSON.parse(raw) as Partial<Leftover> & { at?: number };
    if (typeof then.at === "number" && Date.now() - then.at > THEN_MAX_AGE_MS) return null;
    return typeof then.command === "string" ? { command: then.command, payload: then.payload ?? {} } : null;
  } catch {
    return null;
  }
}
