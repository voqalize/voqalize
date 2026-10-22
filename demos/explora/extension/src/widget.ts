/**
 * The corner of Explora's page that is ours: the button that starts a call,
 * the card that holds Javier's face while it runs, and the language toggle.
 * Dressed as Explora dresses its own pages: white, black, a warm sand, their
 * Objektiv type (already loaded by the page), square-cornered black buttons
 * in spaced capitals.
 *
 * It lives in a shadow root so that neither side's styles reach the other. It
 * takes the bottom-right corner; the visitor can drag it anywhere and minimise
 * the card to his face alone, and the call and its audio carry on.
 */

export type Status = "idle" | "connecting" | "live" | "error";
export type Activity = "listening" | "thinking" | "speaking";
export type Language = "en" | "es";

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
  /** A language asked for on the toggle and not yet confirmed; `null` for none. */
  setLanguagePending(language: Language | null): void;
  /** What on the page the widget must not cover; empty when nothing is open. */
  avoid(obstacles: readonly Rect[]): void;
  onCall(fn: () => void): void;
  /** The visitor is reaching for the invite: a pointer over it, or focus. */
  onReach(fn: () => void): void;
  onMute(fn: () => void): void;
  /** The visitor pressed a language on the toggle. */
  onLanguage(fn: (language: Language) => void): void;
  onHang(fn: () => void): void;
}

// Explora's own black and white, read off their buttons and headings, with
// the warm sand of their deserts and the ring's terracotta for what is live.
const BRAND = "#000000";
const BRAND_DARK = "#000000";
const INK = "#1a1a1a";
const LINE = "#e3ddd2";
const MUTED = "#6f6a62";
const SAND = "#f3eee5";
const SAND_DEEP = "#d9ccb6";
const LIVE = "#C2410C";
const SANS = `ObjektivMk1Regular, "Helvetica Neue", system-ui, sans-serif`;
const BOLD = `ObjektivMk1Bold, "Helvetica Neue", system-ui, sans-serif`;
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
.caps { font-family: ${BOLD}; text-transform: uppercase; letter-spacing: 0.14em; font-size: 11px; font-weight: 400; }

.invite {
  display: flex; align-items: center; gap: 12px; width: ${CARD + 20}px;
  background: #fff; border: 1px solid ${LINE}; border-radius: 2px;
  padding: 10px 14px 10px 10px; text-align: left; color: ${INK};
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.14);
  transition: border-color 200ms ease, transform 200ms ease;
}
.invite:hover { border-color: ${BRAND}; transform: translateY(-1px); }
.invite:disabled { opacity: 0.7; cursor: progress; }
.still {
  width: 52px; height: 52px; border-radius: 50%; flex: none;
  background: ${SAND} center 20% / cover no-repeat;
  box-shadow: 0 0 0 2px #fff, 0 0 0 3px ${SAND_DEEP};
}
.invite-text { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.invite-name { font-family: ${BOLD}; font-size: 13px; letter-spacing: 0.16em; text-transform: uppercase;
  color: ${BRAND_DARK}; line-height: 1.2; }
.invite-role { color: ${MUTED}; font-size: 12px; }

.card {
  width: ${CARD}px; background: #fff; border: 1px solid ${LINE}; border-radius: 2px;
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.18);
  transition: width 300ms ${EASE}, border-radius 300ms ${EASE}, border-color 200ms;
  overflow: hidden;
}
.frame {
  position: relative; overflow: hidden; cursor: grab;
  width: ${CARD - 2}px; height: ${CARD - 2}px;
  transition: width 300ms ${EASE}, height 300ms ${EASE};
}
.face {
  width: ${CARD - 2}px; height: ${CARD - 2}px; background: ${SAND};
  transform-origin: 0 0; transition: transform 300ms ${EASE};
}
.face > * { width: 100%; height: 100%; }
.minimise {
  position: absolute; top: 8px; right: 8px; width: 28px; height: 28px;
  display: grid; place-items: center; padding: 0; border-radius: 2px;
  background: rgba(255, 255, 255, 0.9); border: 1px solid ${LINE}; color: ${INK};
  opacity: 0; transition: opacity 200ms;
}
.card:hover .minimise, .minimise:focus-visible { opacity: 1; }
.body { width: ${CARD - 2}px; padding: 12px 14px; display: flex; flex-direction: column; gap: 10px; }
.head { display: flex; align-items: center; justify-content: space-between; gap: 8px; cursor: grab; }
.name { font-family: ${BOLD}; font-size: 14px; letter-spacing: 0.16em; text-transform: uppercase; color: ${BRAND_DARK}; }
.status { color: ${MUTED}; display: flex; align-items: center; gap: 6px; letter-spacing: 0.1em; font-size: 10px; }
.dot { width: 7px; height: 7px; border-radius: 50%; background: ${LIVE}; opacity: 0.35; transition: opacity 200ms; }
.root[data-activity="speaking"] .dot, .root[data-activity="listening"] .dot { opacity: 1; }
.buttons { display: flex; gap: 8px; }
.buttons button { flex: 1; height: 38px; border-radius: 2px; }
.ghost { background: #fff; border: 1px solid ${BRAND_DARK}; color: ${BRAND_DARK}; }
.solid { background: ${BRAND}; border: 1px solid ${BRAND}; color: #fff; }
.ghost[aria-pressed="true"] { background: ${SAND}; color: ${BRAND_DARK}; }
.credit { color: ${MUTED}; font-size: 9px; text-align: center; }
.lang { display: flex; gap: 4px; padding: 3px; border-radius: 2px; background: ${SAND}; width: ${CARD + 20}px; }
.card .lang { width: auto; }
.lang button { flex: 1; min-height: 30px; padding: 4px 10px; border: 0; border-radius: 2px;
  background: transparent; color: ${BRAND_DARK}; font-size: 12px; letter-spacing: 0.04em; }
.lang button[aria-pressed="true"] { background: ${BRAND}; color: #fff; cursor: default; }
.lang button.pending { opacity: 0.55; outline: 1px dashed ${BRAND}; outline-offset: -3px; }
.lang button:focus-visible { outline: 2px solid ${LIVE}; outline-offset: 2px; }
.error { color: #8a2a0a; background: #fff; border-radius: 2px; padding: 8px 10px; font-size: 12px; line-height: 1.4;
  max-width: ${CARD + 20}px; margin: 0; box-shadow: 0 6px 18px rgba(0,0,0,0.1); }

.root[data-min] .card { width: ${BUBBLE}px; border-radius: 50%; border-color: ${BRAND}; cursor: pointer; }
.root[data-min] .frame { width: ${BUBBLE - 2}px; height: ${BUBBLE - 2}px; cursor: pointer; }
.root[data-min] .face { transform: scale(${(BUBBLE - 2) / (CARD - 2)}); }
.root[data-min] .body, .root[data-min] .minimise { display: none; }
.root[data-min][data-activity="speaking"] .card { animation: breathe 1.6s ease-in-out infinite; }
.root[data-min][data-muted] .card { border-color: ${MUTED}; }
@keyframes breathe {
  0%, 100% { box-shadow: 0 0 0 0 rgba(194, 65, 12, 0.45), 0 16px 40px rgba(0, 0, 0, 0.16); }
  50% { box-shadow: 0 0 0 6px rgba(194, 65, 12, 0), 0 16px 40px rgba(0, 0, 0, 0.16); }
}
@media (prefers-reduced-motion: reduce) {
  .root.glide, .card, .frame, .face { transition: none; }
  .root[data-min][data-activity="speaking"] .card { animation: none; }
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

export function mountWidget(): Widget {
  const host = document.createElement("div");
  host.setAttribute("data-voqalize", "widget");
  const shadow = host.attachShadow({ mode: "open" });

  shadow.innerHTML = `
    <style>${STYLES}</style>
    <div class="root" data-status="idle">
      <button class="invite" type="button" aria-label="Talk to Javier, Explora's guide, by voice">
        <span class="still"></span>
        <span class="invite-text">
          <span class="invite-name">Talk to Javier</span>
          <span class="invite-role">Explora guide · voice</span>
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
            <span class="name">Javier</span>
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
        <button type="button" data-lang="es" lang="es" aria-pressed="false">Español</button>
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
    for (const child of [invite, card, lang, error]) {
      if (child.hidden || (child === lang && !card.hidden)) continue;
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
    if (target.closest(".mute, .hang, .minimise, .lang")) return;
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

  // ─── The language toggle ──────────────────────────────────────────────

  let languageFn: ((language: Language) => void) | null = null;
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
      // Under the invite it picks the next call's language; in the card, the call's.
      (card.hidden ? root : langSlot).insertBefore(lang, card.hidden ? error : null);
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
    onLanguage: (fn) => {
      languageFn = fn;
    },
    onHang: (fn) => hang.addEventListener("click", fn),
  };
}
