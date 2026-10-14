/**
 * The corner of Saatvik's page that is ours: the button that starts a call,
 * the card that holds Tara's face while it runs, the language toggle, and the
 * lead brief — what Saatvik's sales team would receive about this caller.
 *
 * It lives in a shadow root so that neither side's styles reach the other, and
 * it is set in Saatvik's own typefaces, which their page has already loaded:
 * DM Sans for text and Syne for headings. The palette is theirs too: the navy
 * of their logo, the orange of their buttons, white cards.
 *
 * It takes the bottom-right corner their chat launcher used (the adapter hides
 * that launcher and moves their WhatsApp button to the other corner). The
 * person can drag it anywhere for the page and minimise the card to her face
 * alone; the call and its audio carry on.
 */

export type Status = "idle" | "connecting" | "live" | "error";
export type Activity = "listening" | "thinking" | "speaking";
export type Language = "en" | "hi";

/** A rectangle in viewport pixels. */
export interface Rect {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

export interface Widget {
  /** Where the avatar mounts. */
  readonly face: HTMLElement;
  /** Where the bot's audio plays. */
  readonly audio: HTMLAudioElement;
  paint(status: Status, message?: string): void;
  setActivity(activity: Activity): void;
  setMuted(muted: boolean): void;
  setStill(url: string): void;
  /** The language the call is in, or the next one starts in. */
  setLanguage(language: Language): void;
  /** A switch was asked for and not yet confirmed. */
  setLanguagePending(language: Language | null): void;
  /** Show or refresh the lead brief; any shape, rendered generically. */
  setBrief(brief: unknown): void;
  /** What on the page the widget must not cover; empty when nothing is open. */
  avoid(obstacles: readonly Rect[]): void;
  onCall(fn: () => void): void;
  /** The person is reaching for the invite: a pointer over it, or focus. */
  onReach(fn: () => void): void;
  onMute(fn: () => void): void;
  onHang(fn: () => void): void;
  onLanguage(fn: (language: Language) => void): void;
}

const NAVY = "#13306B";
const ORANGE = "#EA7124";
const INK = "#172033";
const LINE = "#e3e7ee";
const MUTED = "#5f6b7d";
const SANS = `"DM Sans", system-ui, sans-serif`;
const DISPLAY = `Syne, "DM Sans", system-ui, sans-serif`;
const EASE = "cubic-bezier(0.32, 0.72, 0, 1)";

/** The card's width, and so the face's: the face is square. */
const CARD = 264;
/** The minimised face's diameter. */
const BUBBLE = 76;
/** The gap kept from the viewport's edges and from anything it avoids. */
const GAP = 16;
/** Pointer travel below this is a click, above it a drag. */
const DRAG_PX = 5;

const STYLES = `
:host { all: initial; }
* { box-sizing: border-box; }
.root {
  position: fixed; left: 0; top: 0; z-index: 2147483001;
  display: flex; flex-direction: column; align-items: flex-end; gap: 10px;
  font-family: ${SANS}; color: ${INK}; font-size: 14px;
  -webkit-font-smoothing: antialiased;
  will-change: transform; touch-action: none;
}
.root.glide { transition: transform 500ms ${EASE}; }
.root.dragging { cursor: grabbing; }
button { font: inherit; cursor: pointer; }
.caps { text-transform: uppercase; letter-spacing: 0.08em; font-size: 11px; font-weight: 600; }

.invite {
  display: flex; align-items: center; gap: 12px; width: ${CARD}px;
  background: #fff; border: 1px solid ${LINE}; border-radius: 12px;
  padding: 10px 14px 10px 10px; text-align: left; color: ${INK};
  box-shadow: 0 10px 30px rgba(19, 48, 107, 0.14);
  transition: border-color 200ms ease, transform 200ms ease;
}
.invite:hover { border-color: ${ORANGE}; transform: translateY(-1px); }
.still {
  width: 52px; height: 52px; border-radius: 50%; flex: none;
  background: #e9edf5 center 20% / cover no-repeat;
  box-shadow: 0 0 0 2px #fff, 0 0 0 4px ${ORANGE};
}
.invite-text { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.invite-name { font-family: ${DISPLAY}; font-weight: 700; font-size: 18px; color: ${NAVY}; line-height: 1.1; }
.invite-role { color: ${MUTED}; font-size: 12px; }

.card {
  width: ${CARD}px; background: #fff; border: 1px solid ${LINE}; border-radius: 12px;
  box-shadow: 0 16px 40px rgba(19, 48, 107, 0.18);
  transition: width 300ms ${EASE}, border-radius 300ms ${EASE}, border-color 200ms;
  overflow: hidden;
}
.frame {
  position: relative; overflow: hidden; cursor: grab;
  width: ${CARD - 2}px; height: ${CARD - 2}px;
  transition: width 300ms ${EASE}, height 300ms ${EASE};
}
.face {
  width: ${CARD - 2}px; height: ${CARD - 2}px; background: #e9edf5;
  transform-origin: 0 0; transition: transform 300ms ${EASE};
}
.face > * { width: 100%; height: 100%; }
.minimise {
  position: absolute; top: 8px; right: 8px; width: 28px; height: 28px;
  display: grid; place-items: center; padding: 0; border-radius: 6px;
  background: rgba(255, 255, 255, 0.9); border: 1px solid ${LINE}; color: ${INK};
  opacity: 0; transition: opacity 200ms;
}
.card:hover .minimise, .minimise:focus-visible { opacity: 1; }
.body { width: ${CARD - 2}px; padding: 12px 14px 12px; display: flex; flex-direction: column; gap: 10px; }
.head { display: flex; align-items: center; justify-content: space-between; gap: 8px; cursor: grab; }
.name { font-family: ${DISPLAY}; font-weight: 700; font-size: 20px; color: ${NAVY}; }
.status { color: ${MUTED}; display: flex; align-items: center; gap: 6px; }
.dot { width: 7px; height: 7px; border-radius: 50%; background: ${ORANGE}; opacity: 0.35; transition: opacity 200ms; }
.root[data-activity="speaking"] .dot, .root[data-activity="listening"] .dot { opacity: 1; }
.buttons { display: flex; gap: 8px; }
.buttons button { flex: 1; height: 38px; border-radius: 6px; }
.ghost { background: #fff; border: 1px solid ${NAVY}; color: ${NAVY}; }
.solid { background: ${ORANGE}; border: 1px solid ${ORANGE}; color: #fff; }
.ghost[aria-pressed="true"] { background: ${NAVY}; color: #fff; }
.credit { color: ${MUTED}; font-size: 10px; letter-spacing: 0.08em; text-align: center; }
.error { color: #9b2c2c; background: #fff; border-radius: 8px; padding: 8px 10px; font-size: 12px; line-height: 1.4;
  max-width: ${CARD}px; margin: 0; box-shadow: 0 6px 18px rgba(0,0,0,0.1); }

.lang { display: flex; gap: 4px; padding: 3px; border-radius: 999px; background: #eef1f6; width: ${CARD}px; }
.card .lang { width: auto; }
.lang button { flex: 1; min-height: 30px; padding: 4px 10px; border: 0; border-radius: 999px;
  background: transparent; color: ${NAVY}; font-size: 13px; font-weight: 500; }
.lang button[aria-pressed="true"] { background: ${NAVY}; color: #fff; cursor: default; }
.lang button.pending { opacity: 0.55; outline: 1px dashed ${NAVY}; outline-offset: -3px; }
.lang button:focus-visible { outline: 2px solid ${ORANGE}; outline-offset: 2px; }

/* The lead brief: what Saatvik's sales team would receive. */
.brief { width: ${CARD + 56}px; background: #fff; border: 1px solid ${LINE}; border-radius: 12px;
  box-shadow: 0 16px 40px rgba(19, 48, 107, 0.18); overflow: hidden; }
.brief-head { display: flex; align-items: center; gap: 8px; width: 100%; padding: 10px 12px;
  background: ${NAVY}; color: #fff; border: 0; text-align: left; }
.brief-title { flex: 1; font-family: ${DISPLAY}; font-weight: 600; font-size: 13px; line-height: 1.2; }
.demo-tag { font-size: 9px; letter-spacing: 0.1em; text-transform: uppercase; padding: 2px 6px;
  border: 1px solid rgba(255,255,255,0.5); border-radius: 3px; white-space: nowrap; }
.chev { transition: transform 200ms; }
.brief[data-open] .chev { transform: rotate(180deg); }
.brief-body { display: none; padding: 10px 12px 12px; max-height: max(140px, calc(100vh - ${CARD + 260}px));
  overflow: auto; font-size: 12.5px; line-height: 1.45; }
.brief[data-open] .brief-body { display: block; }
.brief.flash { animation: flash 900ms ease-out; }
@keyframes flash { 0% { box-shadow: 0 0 0 0 rgba(234,113,36,0.6), 0 16px 40px rgba(19,48,107,0.18); }
  100% { box-shadow: 0 0 0 10px rgba(234,113,36,0), 0 16px 40px rgba(19,48,107,0.18); } }
.score { display: inline-flex; align-items: center; gap: 6px; padding: 3px 9px; border-radius: 999px;
  font-weight: 700; font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase; color: #fff; background: ${MUTED}; }
.score[data-score="hot"] { background: #d4380d; }
.score[data-score="warm"] { background: ${ORANGE}; }
.score[data-score="cold"] { background: #4a6fa5; }
.axes { margin-left: 8px; color: ${MUTED}; font-size: 11.5px; }
.row { display: grid; grid-template-columns: 92px 1fr; gap: 8px; padding: 4px 0; border-bottom: 1px solid #f0f2f6; }
.row:last-child { border-bottom: 0; }
.k { color: ${MUTED}; font-size: 11.5px; }
.v { word-break: break-word; }
.v.empty { color: #a0a8b6; }
.section { margin-top: 10px; }
.section-title { color: ${NAVY}; font-weight: 700; font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase; margin-bottom: 4px; }
.reasons { margin: 6px 0 0; padding-left: 18px; color: ${INK}; }
.reasons li { margin: 2px 0; }
.sent { display: inline-block; margin-left: 6px; font-size: 11px; color: #237a3b; font-weight: 600; }
.summary { margin: 0; }

.root[data-min] .card { width: ${BUBBLE}px; border-radius: 50%; border-color: ${ORANGE}; cursor: pointer; }
.root[data-min] .frame { width: ${BUBBLE - 2}px; height: ${BUBBLE - 2}px; cursor: pointer; }
.root[data-min] .face { transform: scale(${(BUBBLE - 2) / (CARD - 2)}); }
.root[data-min] .body, .root[data-min] .minimise, .root[data-min] .brief { display: none; }
.root[data-min][data-activity="speaking"] .card { animation: breathe 1.6s ease-in-out infinite; }
.root[data-min][data-muted] .card { border-color: ${MUTED}; }
@keyframes breathe {
  0%, 100% { box-shadow: 0 0 0 0 rgba(234, 113, 36, 0.45), 0 16px 40px rgba(19, 48, 107, 0.18); }
  50% { box-shadow: 0 0 0 6px rgba(234, 113, 36, 0), 0 16px 40px rgba(19, 48, 107, 0.18); }
}
@media (prefers-reduced-motion: reduce) {
  .root.glide, .card, .frame, .face { transition: none; }
  .root[data-min][data-activity="speaking"] .card, .brief.flash { animation: none; }
}
[hidden] { display: none !important; }
`;

const ACTIVITY: Record<Activity, string> = {
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
};

/** The brief's own keys, shown in their own places; anything else it carries
 *  is listed after them, so a field the brain adds shows without a change
 *  here. */
const BRIEF_KEYS = new Set(["fields", "observed", "score", "reasons", "routing", "summary", "submitted"]);

function overlaps(a: Rect, b: Rect): boolean {
  return a.left < b.right + GAP && a.right + GAP > b.left && a.top < b.bottom + GAP && a.bottom + GAP > b.top;
}

function humanKey(k: string): string {
  const s = k.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function text(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return value.map(text).filter(Boolean).join(", ");
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([k, v]) => (text(v) ? `${humanKey(k)}: ${text(v)}` : ""))
      .filter(Boolean)
      .join(" · ");
  }
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

function el(tag: string, cls?: string, content?: string): HTMLElement {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (content !== undefined) e.textContent = content;
  return e;
}

function row(k: string, v: unknown): HTMLElement {
  const r = el("div", "row");
  r.appendChild(el("span", "k", humanKey(k)));
  const t = text(v);
  r.appendChild(el("span", t ? "v" : "v empty", t || "—"));
  return r;
}

export function mountWidget(): Widget {
  const host = document.createElement("div");
  host.setAttribute("data-voqalize", "widget");
  const shadow = host.attachShadow({ mode: "open" });

  shadow.innerHTML = `
    <style>${STYLES}</style>
    <div class="root" data-status="idle">
      <div class="brief" hidden>
        <button class="brief-head" type="button" aria-expanded="false">
          <span class="brief-title">What Saatvik's sales team receives</span>
          <span class="demo-tag">Demo view</span>
          <svg class="chev" width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 4l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>
        </button>
        <div class="brief-body"></div>
      </div>
      <button class="invite" type="button" aria-label="Talk to Tara, Saatvik's solar advisor, by voice">
        <span class="still"></span>
        <span class="invite-text">
          <span class="invite-name">Talk to Tara</span>
          <span class="invite-role">Solar advisor · voice</span>
        </span>
      </button>
      <div class="card" hidden>
        <div class="frame">
          <div class="face"></div>
          <button class="minimise" type="button" aria-label="Minimise">
            <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M1 6h10" stroke="currentColor" stroke-width="1.4"/></svg>
          </button>
        </div>
        <div class="body">
          <div class="head">
            <span class="name">Tara</span>
            <span class="status caps"><span class="dot"></span><span class="status-text"></span></span>
          </div>
          <div class="lang-slot"></div>
          <div class="buttons">
            <button class="ghost caps mute" type="button" aria-pressed="false">Mute</button>
            <button class="solid caps hang" type="button">End call</button>
          </div>
          <div class="credit caps">Voice by Voqalize · preview</div>
        </div>
      </div>
      <div class="lang" role="group" aria-label="Language">
        <button type="button" data-lang="en" lang="en" aria-pressed="true">English</button>
        <button type="button" data-lang="hi" lang="hi" aria-pressed="false">हिंदी</button>
      </div>
      <p class="error" hidden></p>
      <audio autoplay></audio>
    </div>
  `;
  const root = shadow.querySelector<HTMLElement>(".root")!;
  document.body.appendChild(host);

  const $ = <T extends Element>(sel: string) => shadow.querySelector<T>(sel)!;
  const invite = $<HTMLButtonElement>(".invite");
  const card = $<HTMLElement>(".card");
  const statusText = $<HTMLElement>(".status-text");
  const error = $<HTMLElement>(".error");
  const mute = $<HTMLButtonElement>(".mute");
  const hang = $<HTMLButtonElement>(".hang");
  const lang = $<HTMLElement>(".lang");
  const langSlot = $<HTMLElement>(".lang-slot");
  const langButtons = [...lang.querySelectorAll<HTMLButtonElement>("button")];
  const brief = $<HTMLElement>(".brief");
  const briefHead = $<HTMLButtonElement>(".brief-head");
  const briefBody = $<HTMLElement>(".brief-body");

  // ─── Where it sits ────────────────────────────────────────────────────

  let home = { right: 24, bottom: 24 };
  let obstacles: readonly Rect[] = [];
  let minimised = false;
  let squeezed = false;
  let openedAnyway = false;
  let at = { x: 0, y: 0 };

  function showMinimised(): boolean {
    return !card.hidden && (minimised || (squeezed && !openedAnyway));
  }

  /** The widget's size, measured; the bubble's when minimised. */
  function sizeOf(bubble: boolean): { w: number; h: number } {
    if (bubble) return { w: BUBBLE, h: BUBBLE };
    // The card grows out of the bubble over a transition, so it is measured
    // from its parts: the frame is square and the body's width is fixed.
    let h = 0;
    let w = 0;
    for (const child of [brief, invite, card, lang, error]) {
      if (child.hidden) continue;
      const cw = child === card ? CARD : child.offsetWidth;
      const ch = child === card ? CARD + $<HTMLElement>(".body").offsetHeight : child.offsetHeight;
      w = Math.max(w, cw);
      h += ch + (h ? 10 : 0);
    }
    return { w: w || root.offsetWidth, h: h || root.offsetHeight };
  }

  /** The first place, in order of preference, where a widget of this size
   *  covers nothing that is open: its home; the bottom-left corner; the
   *  top-left corner. */
  function fit(w: number, h: number): { x: number; y: number } | null {
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const clampX = (x: number) => Math.min(Math.max(x, GAP), vw - w - GAP);
    const clampY = (y: number) => Math.min(Math.max(y, GAP), vh - h - GAP);
    const candidates = [
      { x: clampX(vw - home.right - w), y: clampY(vh - home.bottom - h) },
      { x: GAP, y: vh - h - GAP },
      { x: GAP, y: GAP },
    ];
    for (const c of candidates) {
      if (c.x < GAP - 0.5 || c.y < GAP - 0.5) continue;
      const box = { left: c.x, top: c.y, right: c.x + w, bottom: c.y + h };
      if (!obstacles.some((o) => overlaps(box, o))) return c;
    }
    return null;
  }

  function place(glide: boolean): void {
    let spot: { x: number; y: number } | null = null;
    squeezed = false;
    if (card.hidden || !minimised) {
      const { w, h } = sizeOf(false);
      spot = fit(w, h);
      squeezed = !spot && !card.hidden;
    }
    const bubble = showMinimised();
    if (bubble) spot = fit(BUBBLE, BUBBLE);
    if (!spot) {
      const { w, h } = sizeOf(bubble);
      spot = { x: window.innerWidth - w - GAP, y: window.innerHeight - h - GAP };
    }
    root.toggleAttribute("data-min", bubble);
    root.classList.toggle("glide", glide);
    at = spot;
    root.style.transform = `translate3d(${Math.round(spot.x)}px, ${Math.round(spot.y)}px, 0)`;
  }

  const settle = () => requestAnimationFrame(() => place(false));
  window.addEventListener("resize", () => place(false));
  place(false);

  // ─── Dragging, and the click that is not a drag ───────────────────────

  let drag: { id: number; dx: number; dy: number; sx: number; sy: number; moved: boolean } | null = null;
  let swallowClick = false;

  root.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    const target = e.target as Element;
    if (target.closest(".mute, .hang, .minimise, .lang, .brief")) return;
    drag = { id: e.pointerId, dx: e.clientX - at.x, dy: e.clientY - at.y, sx: e.clientX, sy: e.clientY, moved: false };
  });
  root.addEventListener("pointermove", (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    if (!drag.moved && Math.hypot(e.clientX - drag.sx, e.clientY - drag.sy) < DRAG_PX) return;
    if (!drag.moved) {
      drag.moved = true;
      root.setPointerCapture(e.pointerId);
      root.classList.add("dragging");
      root.classList.remove("glide");
    }
    const w = root.offsetWidth;
    const h = root.offsetHeight;
    at = {
      x: Math.min(Math.max(e.clientX - drag.dx, 0), window.innerWidth - w),
      y: Math.min(Math.max(e.clientY - drag.dy, 0), window.innerHeight - h),
    };
    root.style.transform = `translate3d(${at.x}px, ${at.y}px, 0)`;
  });
  const drop = (e: PointerEvent) => {
    if (!drag || e.pointerId !== drag.id) return;
    const moved = drag.moved;
    drag = null;
    root.classList.remove("dragging");
    if (!moved) return;
    swallowClick = true;
    home = {
      right: window.innerWidth - at.x - root.offsetWidth,
      bottom: window.innerHeight - at.y - root.offsetHeight,
    };
    openedAnyway = squeezed || openedAnyway;
    place(true);
  };
  root.addEventListener("pointerup", drop);
  root.addEventListener("pointercancel", drop);
  root.addEventListener(
    "click",
    (e) => {
      if (!swallowClick) return;
      swallowClick = false;
      e.stopImmediatePropagation();
      e.preventDefault();
    },
    true,
  );

  // ─── Minimising ───────────────────────────────────────────────────────

  $<HTMLButtonElement>(".minimise").addEventListener("click", (e) => {
    e.stopPropagation();
    minimised = true;
    place(true);
  });
  card.addEventListener("click", () => {
    if (!root.hasAttribute("data-min")) return;
    minimised = false;
    if (squeezed) openedAnyway = true;
    place(true);
    settle();
  });

  // ─── The lead brief ───────────────────────────────────────────────────

  function setBriefOpen(open: boolean): void {
    brief.toggleAttribute("data-open", open);
    briefHead.setAttribute("aria-expanded", String(open));
    settle();
  }
  briefHead.addEventListener("click", () => setBriefOpen(!brief.hasAttribute("data-open")));

  function renderBrief(raw: unknown): void {
    const b = (raw && typeof raw === "object" ? raw : { summary: raw }) as Record<string, unknown>;
    briefBody.replaceChildren();

    // `score` is `{grade, intent, fit, readiness, reasons}`; a bare string is
    // read as the grade, so an older brain still gets its badge.
    const sc = b.score && typeof b.score === "object" ? (b.score as Record<string, unknown>) : null;
    const grade = sc ? text(sc.grade) : text(b.score);
    const top = el("div");
    if (grade) {
      const badge = el("span", "score", grade);
      badge.dataset.score = grade.toLowerCase();
      top.appendChild(badge);
    }
    if (sc) {
      const axes = ["intent", "fit", "readiness"]
        .filter((k) => typeof sc[k] === "number")
        .map((k) => `${humanKey(k)} ${sc[k] as number}`);
      if (axes.length) top.appendChild(el("span", "axes", axes.join(" · ")));
    }
    if (b.submitted === true) top.appendChild(el("span", "sent", "✓ Enquiry submitted"));
    if (top.childElementCount) briefBody.appendChild(top);

    const reasons = sc && Array.isArray(sc.reasons) ? sc.reasons : b.reasons;
    if (Array.isArray(reasons) && reasons.length) {
      const ul = el("ul", "reasons");
      for (const r of reasons) ul.appendChild(el("li", undefined, text(r)));
      briefBody.appendChild(ul);
    }
    if (b.routing !== undefined && text(b.routing)) {
      const s = el("div", "section");
      s.appendChild(el("div", "section-title", "Routed to"));
      s.appendChild(el("div", undefined, text(b.routing)));
      briefBody.appendChild(s);
    }
    if (b.summary !== undefined && text(b.summary)) {
      const s = el("div", "section");
      s.appendChild(el("div", "section-title", "Summary"));
      s.appendChild(el("p", "summary", text(b.summary)));
      briefBody.appendChild(s);
    }
    // A brief is useful from its first fact, so only what is known is listed.
    const fields = b.fields && typeof b.fields === "object" ? (b.fields as Record<string, unknown>) : {};
    const extra = Object.entries(b).filter(([k]) => !BRIEF_KEYS.has(k));
    const known = [...Object.entries(fields), ...extra].filter(([, v]) => text(v));
    if (known.length) {
      const s = el("div", "section");
      s.appendChild(el("div", "section-title", "Captured"));
      for (const [k, v] of known) s.appendChild(row(k, v));
      briefBody.appendChild(s);
    }
    const seen = b.observed && typeof b.observed === "object" ? (b.observed as Record<string, unknown>) : {};
    const seenKnown = Object.entries(seen).filter(([, v]) => text(v));
    if (seenKnown.length) {
      const s = el("div", "section");
      s.appendChild(el("div", "section-title", "Seen on the site"));
      for (const [k, v] of seenKnown) s.appendChild(row(k, v));
      briefBody.appendChild(s);
    }
  }

  // ─── The language toggle ──────────────────────────────────────────────

  let languageFn: ((l: Language) => void) | null = null;
  for (const b of langButtons) {
    b.addEventListener("click", () => languageFn?.(b.dataset.lang as Language));
  }

  return {
    face: $<HTMLElement>(".face"),
    audio: $<HTMLAudioElement>("audio"),
    paint(status, message) {
      root.dataset.status = status;
      const wasHidden = card.hidden;
      card.hidden = status === "idle" || status === "error";
      invite.hidden = !card.hidden;
      invite.disabled = status === "connecting";
      // The toggle sits under the invite before a call and in the card during
      // one: the same buttons, so their state carries over.
      (card.hidden ? root : langSlot).insertBefore(lang, card.hidden ? error : null);
      lang.style.width = card.hidden ? "" : "auto";
      error.hidden = status !== "error";
      error.textContent = status === "error" ? (message ?? "Could not start the call.") : "";
      if (status === "connecting") statusText.textContent = message ?? "Connecting";
      if (status === "live" && !root.dataset.activity) statusText.textContent = ACTIVITY.listening;
      if (status !== "live") delete root.dataset.activity;
      if (card.hidden) minimised = false;
      if (wasHidden !== card.hidden) settle();
    },
    setActivity(activity) {
      root.dataset.activity = activity;
      statusText.textContent = ACTIVITY[activity];
    },
    setMuted(muted) {
      mute.setAttribute("aria-pressed", String(muted));
      mute.textContent = muted ? "Unmute" : "Mute";
      root.toggleAttribute("data-muted", muted);
    },
    setStill(url) {
      $<HTMLElement>(".still").style.backgroundImage = `url("${url}")`;
    },
    setLanguage(language) {
      for (const b of langButtons) {
        b.setAttribute("aria-pressed", String(b.dataset.lang === language));
        b.classList.remove("pending");
      }
    },
    setLanguagePending(language) {
      for (const b of langButtons) b.classList.toggle("pending", b.dataset.lang === language);
    },
    setBrief(raw) {
      const first = brief.hidden;
      renderBrief(raw);
      brief.hidden = false;
      // Open the first time it arrives; after that it stays as the person left it.
      if (first) setBriefOpen(true);
      brief.classList.remove("flash");
      void brief.offsetWidth;
      brief.classList.add("flash");
      settle();
    },
    avoid(next) {
      obstacles = next;
      if (!next.length) openedAnyway = false;
      if (!drag?.moved) place(true);
    },
    onCall: (fn) => invite.addEventListener("click", fn),
    onReach: (fn) => {
      invite.addEventListener("pointerenter", fn);
      invite.addEventListener("focus", fn);
    },
    onMute: (fn) => mute.addEventListener("click", fn),
    onHang: (fn) => hang.addEventListener("click", fn),
    onLanguage: (fn) => {
      languageFn = fn;
    },
  };
}
