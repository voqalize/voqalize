/**
 * The corner of SendPotion's page that is ours: the button that starts a call,
 * the card that holds Tushar's face while it runs, and the reading list — the
 * blog posts he picked for this visitor, which stay in the card on every tab.
 *
 * It lives in a shadow root so that neither side's styles reach the other. It
 * takes the bottom-right corner; the visitor can drag it anywhere and minimise
 * the card to his face alone, and the call and its audio carry on.
 */

export type Status = "idle" | "connecting" | "live" | "error";
export type Activity = "listening" | "thinking" | "speaking";

/** A rectangle in viewport pixels. */
export interface Rect {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

export interface Read {
  url: string;
  title: string;
  why: string | null;
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
  /** The posts he recommended, newest list first; empty hides the card. */
  setReads(heading: string, reads: readonly Read[]): void;
  /** What on the page the widget must not cover; empty when nothing is open. */
  avoid(obstacles: readonly Rect[]): void;
  onCall(fn: () => void): void;
  /** The visitor is reaching for the invite: a pointer over it, or focus. */
  onReach(fn: () => void): void;
  onMute(fn: () => void): void;
  onHang(fn: () => void): void;
  /** A post in the reading list was clicked. */
  onRead(fn: (url: string) => void): void;
}

// SendPotion's own purple, read off their buttons, and a deep shade of it.
const BRAND = "#832EC4";
const BRAND_DARK = "#2A1650";
const INK = "#16132B";
const LINE = "#e6e3f2";
const MUTED = "#6a6580";
const SANS = `Inter, "Helvetica Neue", system-ui, sans-serif`;
const EASE = "cubic-bezier(0.32, 0.72, 0, 1)";

/** The card's width, and so the face's: the face is square. */
const CARD = 200;
/** The minimised face's diameter. */
const BUBBLE = 64;
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
  display: flex; align-items: center; gap: 12px; width: ${CARD + 20}px;
  background: #fff; border: 1px solid ${LINE}; border-radius: 14px;
  padding: 10px 14px 10px 10px; text-align: left; color: ${INK};
  box-shadow: 0 10px 30px rgba(42, 22, 80, 0.16);
  transition: border-color 200ms ease, transform 200ms ease;
}
.invite:hover { border-color: ${BRAND}; transform: translateY(-1px); }
.invite:disabled { opacity: 0.7; cursor: progress; }
.still {
  width: 52px; height: 52px; border-radius: 50%; flex: none;
  background: #f0e8f8 center 20% / cover no-repeat;
  box-shadow: 0 0 0 2px #fff, 0 0 0 4px ${BRAND};
}
.invite-text { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.invite-name { font-weight: 700; font-size: 17px; color: ${BRAND_DARK}; line-height: 1.1; }
.invite-role { color: ${MUTED}; font-size: 12px; }

.card {
  width: ${CARD}px; background: #fff; border: 1px solid ${LINE}; border-radius: 14px;
  box-shadow: 0 16px 40px rgba(42, 22, 80, 0.2);
  transition: width 300ms ${EASE}, border-radius 300ms ${EASE}, border-color 200ms;
  overflow: hidden;
}
.frame {
  position: relative; overflow: hidden; cursor: grab;
  width: ${CARD - 2}px; height: ${CARD - 2}px;
  transition: width 300ms ${EASE}, height 300ms ${EASE};
}
.face {
  width: ${CARD - 2}px; height: ${CARD - 2}px; background: #f0e8f8;
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
.body { width: ${CARD - 2}px; padding: 12px 14px; display: flex; flex-direction: column; gap: 10px; }
.head { display: flex; align-items: center; justify-content: space-between; gap: 8px; cursor: grab; }
.name { font-weight: 700; font-size: 19px; color: ${BRAND_DARK}; }
.status { color: ${MUTED}; display: flex; align-items: center; gap: 6px; }
.dot { width: 7px; height: 7px; border-radius: 50%; background: ${BRAND}; opacity: 0.35; transition: opacity 200ms; }
.root[data-activity="speaking"] .dot, .root[data-activity="listening"] .dot { opacity: 1; }
.buttons { display: flex; gap: 8px; }
.buttons button { flex: 1; height: 38px; border-radius: 8px; }
.ghost { background: #fff; border: 1px solid ${BRAND_DARK}; color: ${BRAND_DARK}; }
.solid { background: ${BRAND}; border: 1px solid ${BRAND}; color: #fff; }
.ghost[aria-pressed="true"] { background: ${BRAND_DARK}; color: #fff; }
.credit { color: ${MUTED}; font-size: 10px; letter-spacing: 0.08em; text-align: center; }
.error { color: #9b2c2c; background: #fff; border-radius: 8px; padding: 8px 10px; font-size: 12px; line-height: 1.4;
  max-width: ${CARD + 20}px; margin: 0; box-shadow: 0 6px 18px rgba(0,0,0,0.1); }

/* The reading list: blog posts Tushar picked for this visitor. */
.reads { width: ${CARD + 64}px; background: #fff; border: 1px solid ${LINE}; border-radius: 14px;
  box-shadow: 0 16px 40px rgba(42, 22, 80, 0.18); overflow: hidden; }
.reads-head { display: flex; align-items: center; gap: 8px; width: 100%; padding: 10px 12px;
  background: ${BRAND_DARK}; color: #fff; border: 0; text-align: left; }
.reads-title { flex: 1; font-weight: 600; font-size: 13px; line-height: 1.25; }
.chev { transition: transform 200ms; }
.reads[data-open] .chev { transform: rotate(180deg); }
.reads-list { display: none; margin: 0; padding: 6px; list-style: none;
  max-height: max(140px, calc(100vh - ${CARD + 280}px)); overflow: auto; }
.reads[data-open] .reads-list { display: block; }
.reads-list a { display: block; padding: 8px 8px; border-radius: 8px; color: ${INK}; text-decoration: none; }
.reads-list a:hover, .reads-list a:focus-visible { background: #f5effb; outline: none; }
.read-title { display: block; font-weight: 600; font-size: 13px; line-height: 1.3; color: ${BRAND_DARK}; }
.read-why { display: block; margin-top: 2px; font-size: 12px; line-height: 1.35; color: ${MUTED}; }
.reads.flash { animation: flash 900ms ease-out; }
@keyframes flash { 0% { box-shadow: 0 0 0 0 rgba(131,46,196,0.55), 0 16px 40px rgba(42,22,80,0.18); }
  100% { box-shadow: 0 0 0 10px rgba(131,46,196,0), 0 16px 40px rgba(42,22,80,0.18); } }

.root[data-min] .card { width: ${BUBBLE}px; border-radius: 50%; border-color: ${BRAND}; cursor: pointer; }
.root[data-min] .frame { width: ${BUBBLE - 2}px; height: ${BUBBLE - 2}px; cursor: pointer; }
.root[data-min] .face { transform: scale(${(BUBBLE - 2) / (CARD - 2)}); }
.root[data-min] .body, .root[data-min] .minimise, .root[data-min] .reads { display: none; }
.root[data-min][data-activity="speaking"] .card { animation: breathe 1.6s ease-in-out infinite; }
.root[data-min][data-muted] .card { border-color: ${MUTED}; }
@keyframes breathe {
  0%, 100% { box-shadow: 0 0 0 0 rgba(131, 46, 196, 0.45), 0 16px 40px rgba(42, 22, 80, 0.18); }
  50% { box-shadow: 0 0 0 6px rgba(131, 46, 196, 0), 0 16px 40px rgba(42, 22, 80, 0.18); }
}
@media (prefers-reduced-motion: reduce) {
  .root.glide, .card, .frame, .face { transition: none; }
  .root[data-min][data-activity="speaking"] .card, .reads.flash { animation: none; }
}
[hidden] { display: none !important; }
`;

const ACTIVITY: Record<Activity, string> = {
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
};

function overlaps(a: Rect, b: Rect): boolean {
  return a.left < b.right + GAP && a.right + GAP > b.left && a.top < b.bottom + GAP && a.bottom + GAP > b.top;
}

function el(tag: string, cls?: string, content?: string): HTMLElement {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (content !== undefined) e.textContent = content;
  return e;
}

export function mountWidget(): Widget {
  const host = document.createElement("div");
  host.setAttribute("data-voqalize", "widget");
  const shadow = host.attachShadow({ mode: "open" });

  shadow.innerHTML = `
    <style>${STYLES}</style>
    <div class="root" data-status="idle">
      <div class="reads" hidden>
        <button class="reads-head" type="button" aria-expanded="false">
          <span class="reads-title">Reads picked for you</span>
          <svg class="chev" width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 4l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>
        </button>
        <ul class="reads-list"></ul>
      </div>
      <button class="invite" type="button" aria-label="Talk to Tushar, SendPotion's guide, by voice">
        <span class="still"></span>
        <span class="invite-text">
          <span class="invite-name">Talk to Tushar</span>
          <span class="invite-role">SendPotion guide · voice</span>
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
            <span class="name">Tushar</span>
            <span class="status caps"><span class="dot"></span><span class="status-text"></span></span>
          </div>
          <div class="buttons">
            <button class="ghost caps mute" type="button" aria-pressed="false">Mute</button>
            <button class="solid caps hang" type="button">End call</button>
          </div>
          <div class="credit caps">Voice by Voqalize · preview</div>
        </div>
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
  const reads = $<HTMLElement>(".reads");
  const readsHead = $<HTMLButtonElement>(".reads-head");
  const readsTitle = $<HTMLElement>(".reads-title");
  const readsList = $<HTMLElement>(".reads-list");

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
    let h = 0;
    let w = 0;
    for (const child of [reads, invite, card, error]) {
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
    if (target.closest(".mute, .hang, .minimise, .reads")) return;
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

  // ─── The reading list ─────────────────────────────────────────────────

  let readFn: ((url: string) => void) | null = null;

  function setReadsOpen(open: boolean): void {
    reads.toggleAttribute("data-open", open);
    readsHead.setAttribute("aria-expanded", String(open));
    settle();
  }
  readsHead.addEventListener("click", () => setReadsOpen(!reads.hasAttribute("data-open")));

  return {
    face: $<HTMLElement>(".face"),
    audio: $<HTMLAudioElement>("audio"),
    paint(status, message) {
      root.dataset.status = status;
      const wasHidden = card.hidden;
      card.hidden = status === "idle" || status === "error";
      invite.hidden = !card.hidden;
      invite.disabled = status === "connecting";
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
    setReads(heading, list) {
      readsList.replaceChildren();
      if (!list.length) {
        reads.hidden = true;
        settle();
        return;
      }
      readsTitle.textContent = heading || "Reads picked for you";
      for (const r of list) {
        const li = el("li");
        const a = el("a") as HTMLAnchorElement;
        a.href = r.url;
        a.target = "_blank";
        a.rel = "noopener";
        a.appendChild(el("span", "read-title", r.title));
        if (r.why) a.appendChild(el("span", "read-why", r.why));
        a.addEventListener("click", (e) => {
          if (!readFn) return;
          e.preventDefault();
          readFn(r.url);
        });
        li.appendChild(a);
        readsList.appendChild(li);
      }
      reads.hidden = false;
      setReadsOpen(true);
      reads.classList.remove("flash");
      void reads.offsetWidth;
      reads.classList.add("flash");
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
    onRead: (fn) => {
      readFn = fn;
    },
  };
}
