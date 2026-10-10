/**
 * The corner of Qween's page that is ours: the button that starts a call and
 * the card that holds Trisha's face while it runs.
 *
 * It lives in a shadow root so that neither side's styles reach the other, and
 * it is set in Qween's own typefaces, which their page has already loaded: the
 * sans of their labels and the display serif of their product names. The
 * palette is theirs too: ivory ground, black square-cornered buttons in tracked
 * capitals, and the gold of their hairlines.
 *
 * It keeps out of Qween's way. Their dialogs are drawers that slide in from the
 * right edge, where the widget sits, so whenever one is open the widget glides
 * to where it covers none of it (`avoid`), and back when it closes. The shopper
 * can also drag it anywhere, which becomes its place from then on, and
 * minimise the card to her face alone; the call and its audio carry on.
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

export interface Widget {
  /** Where the avatar mounts. */
  readonly face: HTMLElement;
  /** Where the bot's audio plays. */
  readonly audio: HTMLAudioElement;
  paint(status: Status, message?: string): void;
  setActivity(activity: Activity): void;
  setMuted(muted: boolean): void;
  setStill(url: string): void;
  /** What on the page the widget must not cover; empty when nothing is open. */
  avoid(obstacles: readonly Rect[]): void;
  onCall(fn: () => void): void;
  /** The shopper is reaching for the invite: a pointer over it, or focus. */
  onReach(fn: () => void): void;
  onMute(fn: () => void): void;
  onHang(fn: () => void): void;
}

const INK = "#111111";
const IVORY = "#fcf9f6";
const GOLD = "#b08d57";
const HAIRLINE = "#e7ded3";
const MUTED = "#6f6a64";
// Qween's own faces, by the names their stylesheet gives them. The serif is
// only on their product pages' headings, so it is named rather than read off
// the page, which may not have one yet.
const SANS = `"avenir-next-lt-pro", "Avenir Next", system-ui, sans-serif`;
const SERIF = `"richmond-display", Georgia, serif`;
// Their drawers' own easing, read off the drawer's transition: the widget moves
// out of the way on the same curve the drawer comes in on.
const EASE = "cubic-bezier(0.32, 0.72, 0, 1)";

/** The card's width, and so the face's: the face is square. */
const CARD = 256;
/** The minimised face's diameter. */
const BUBBLE = 76;
/** The gap kept from the viewport's edges and from anything it avoids. */
const GAP = 16;
/** Pointer travel below this is a click, above it a drag. */
const DRAG_PX = 5;
/** Where the widget used to be remembered across pages. It is not any more:
 *  a stray drag left the card mid-page on every page after. Cleared on load. */
const OLD_HOME_KEY = "voqalize.qween.home";

const STYLES = `
:host { all: initial; }
* { box-sizing: border-box; }
.root {
  position: fixed; left: 0; top: 0; z-index: 2147483001;
  font-family: ${SANS}; color: ${INK};
  -webkit-font-smoothing: antialiased;
  will-change: transform;
  touch-action: none;
}
.root.glide { transition: transform 600ms ${EASE}; }
.root.dragging { cursor: grabbing; }
button { font: inherit; cursor: pointer; }
.caps { text-transform: uppercase; letter-spacing: 0.16em; font-size: 12px; }

.invite {
  display: flex; align-items: center; gap: 14px;
  background: ${IVORY}; border: 1px solid ${HAIRLINE};
  padding: 10px 18px 10px 10px;
  box-shadow: 0 10px 30px rgba(17, 17, 17, 0.08);
  transition: border-color 200ms ease;
}
.invite:hover { border-color: ${GOLD}; }
.still {
  width: 52px; height: 52px; border-radius: 50%; flex: none;
  background: #efe7dd center 20% / cover no-repeat;
  outline: 1px solid ${GOLD}; outline-offset: 2px;
}
.invite-text { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; }
.invite-name { font-family: ${SERIF}; font-size: 20px; letter-spacing: -0.01em; line-height: 1.1; }
.invite-role { color: ${MUTED}; font-size: 11px; }

.card {
  width: ${CARD}px; background: ${IVORY}; border: 1px solid ${HAIRLINE};
  box-shadow: 0 16px 40px rgba(17, 17, 17, 0.12);
  transition: width 300ms ${EASE}, border-radius 300ms ${EASE}, border-color 200ms;
  overflow: hidden;
}
.frame {
  position: relative; overflow: hidden; cursor: grab;
  width: ${CARD - 2}px; height: ${CARD - 2}px;
  transition: width 300ms ${EASE}, height 300ms ${EASE};
}
/* The avatar's mount never changes size: minimising scales it, so the renderer
   inside is not asked to resize mid-call. */
.face {
  width: ${CARD - 2}px; height: ${CARD - 2}px; background: #f3ece4;
  transform-origin: 0 0; transition: transform 300ms ${EASE};
}
.face > * { width: 100%; height: 100%; }
.minimise {
  position: absolute; top: 8px; right: 8px; width: 28px; height: 28px;
  display: grid; place-items: center; padding: 0;
  background: rgba(252, 249, 246, 0.9); border: 1px solid ${HAIRLINE}; color: ${INK};
  opacity: 0; transition: opacity 200ms;
}
.card:hover .minimise, .minimise:focus-visible { opacity: 1; }
/* A fixed width, not the card's: while the card grows back out of the bubble
   the body would wrap at every width on the way and measure too tall. */
.body { width: ${CARD - 2}px; padding: 14px 16px 14px; display: flex; flex-direction: column; gap: 10px; }
.head { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; cursor: grab; }
.name { font-family: ${SERIF}; font-size: 22px; letter-spacing: -0.01em; }
.status { color: ${MUTED}; font-size: 11px; display: flex; align-items: center; gap: 6px; }
.dot { width: 6px; height: 6px; border-radius: 50%; background: ${GOLD}; opacity: 0.35; transition: opacity 200ms; }
.root[data-activity="speaking"] .dot, .root[data-activity="listening"] .dot { opacity: 1; }
.buttons { display: flex; gap: 10px; }
.buttons button { flex: 1; height: 40px; }
.ghost { background: transparent; border: 1px solid ${INK}; color: ${INK}; }
.solid { background: ${INK}; border: 1px solid ${INK}; color: #fff; }
.ghost[aria-pressed="true"] { background: ${INK}; color: #fff; }
.credit { color: ${MUTED}; font-size: 10px; letter-spacing: 0.12em; text-align: center; }
.error { color: #8a2d2d; font-size: 12px; line-height: 1.4; max-width: ${CARD}px; }

/* Minimised: her face alone, still live, in a gold ring that breathes while
   she speaks. A click brings the card back. */
.root[data-min] .card { width: ${BUBBLE}px; border-radius: 50%; border-color: ${GOLD}; cursor: pointer; }
.root[data-min] .frame { width: ${BUBBLE - 2}px; height: ${BUBBLE - 2}px; cursor: pointer; }
.root[data-min] .face { transform: scale(${(BUBBLE - 2) / (CARD - 2)}); }
.root[data-min] .body, .root[data-min] .minimise { display: none; }
.root[data-min][data-activity="speaking"] .card { animation: breathe 1.6s ease-in-out infinite; }
.root[data-min][data-muted] .card { border-color: ${MUTED}; }
@keyframes breathe {
  0%, 100% { box-shadow: 0 0 0 0 rgba(176, 141, 87, 0.45), 0 16px 40px rgba(17, 17, 17, 0.12); }
  50% { box-shadow: 0 0 0 6px rgba(176, 141, 87, 0), 0 16px 40px rgba(17, 17, 17, 0.12); }
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

interface Home {
  right: number;
  bottom: number;
}

/** Every page starts with the widget in the bottom-right corner. A drag moves
 *  it for this page only, as gaps from the right and bottom edges, so it keeps
 *  its corner when the window is resized. */
function startHome(): Home {
  try {
    localStorage.removeItem(OLD_HOME_KEY);
  } catch {
    /* Storage blocked: nothing was saved there either. */
  }
  return { right: 24, bottom: 24 };
}

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
      <button class="invite" type="button" aria-label="Talk to Trisha, Qween's jewellery consultant">
        <span class="still"></span>
        <span class="invite-text">
          <span class="invite-name">Talk to Trisha</span>
          <span class="invite-role caps">Jewellery consultant · voice</span>
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
            <span class="name">Trisha</span>
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
  const body = $<HTMLElement>(".body");

  // ─── Where it sits ────────────────────────────────────────────────────

  let home = startHome();
  let obstacles: readonly Rect[] = [];
  /** The shopper minimised it. */
  let minimised = false;
  /** Nowhere on screen fits the card beside what is open, so it is shown as
   *  the bubble until that closes, or until the shopper opens it anyway. */
  let squeezed = false;
  let openedAnyway = false;
  let at = { x: 0, y: 0 };
  /** The card's size when last seen open, for placing it while it is not. */
  let cardSize = { w: CARD, h: 380 };

  function showMinimised(): boolean {
    return !card.hidden && (minimised || (squeezed && !openedAnyway));
  }

  function sizeOf(bubble: boolean): { w: number; h: number } {
    if (bubble) return { w: BUBBLE, h: BUBBLE };
    if (!card.hidden && !root.hasAttribute("data-min")) {
      // Not the card's own box: straight after a restore it is still
      // growing out of the bubble. The frame is square and the card is
      // CARD wide with its border, so only the body is measured, and the
      // body's width is fixed so its height is final from the first frame.
      cardSize = { w: CARD, h: CARD + body.offsetHeight };
      return cardSize;
    }
    return card.hidden ? { w: root.offsetWidth, h: root.offsetHeight } : cardSize;
  }

  /** The first place, in order of preference, where a widget of this size
   *  covers nothing that is open: its home; its home moved left of what is in
   *  the way (their drawers come from the right edge); the bottom-left corner;
   *  the top-left corner. */
  function fit(w: number, h: number): { x: number; y: number } | null {
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const clampX = (x: number) => Math.min(Math.max(x, GAP), vw - w - GAP);
    const clampY = (y: number) => Math.min(Math.max(y, GAP), vh - h - GAP);
    const x0 = clampX(vw - home.right - w);
    const y0 = clampY(vh - home.bottom - h);
    const leftOf = Math.min(...obstacles.map((o) => o.left)) - GAP - w;
    const candidates = [
      { x: x0, y: y0 },
      { x: leftOf, y: y0 },
      { x: GAP, y: vh - h - GAP },
      { x: GAP, y: GAP },
    ];
    for (const c of candidates) {
      if (c.x < GAP || c.y < GAP || c.x + w > vw - GAP + 0.5 || c.y + h > vh - GAP + 0.5) continue;
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
      // Nothing fits even the bubble: the least-covering corner, bottom-left.
      const { w, h } = sizeOf(bubble);
      spot = { x: GAP, y: window.innerHeight - h - GAP };
    }
    root.toggleAttribute("data-min", bubble);
    root.classList.toggle("glide", glide);
    at = spot;
    root.style.transform = `translate3d(${Math.round(spot.x)}px, ${Math.round(spot.y)}px, 0)`;
  }

  // Once the card's size has settled after a change of state, place it again,
  // straight there: a glide is for moving out of the way, not for growing.
  const settle = () => requestAnimationFrame(() => place(false));
  window.addEventListener("resize", () => place(false));
  place(false);

  // ─── Dragging, and the click that is not a drag ───────────────────────

  let drag: { id: number; dx: number; dy: number; sx: number; sy: number; moved: boolean } | null =
    null;
  let swallowClick = false;

  root.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    const target = e.target as Element;
    if (target.closest(".mute, .hang, .minimise")) return;
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
    // Where she put it is its place now, even beside an open drawer.
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
  // A drag ends in a click on whatever it started on; that click is not one.
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
    // The card's own click restores; this one must not reach it.
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

  return {
    face: $<HTMLElement>(".face"),
    audio: $<HTMLAudioElement>("audio"),
    paint(status, message) {
      root.dataset.status = status;
      // The card appears on the press, not when the call goes live: the face
      // loads during call setup and "Connecting" is worth seeing.
      const wasHidden = card.hidden;
      card.hidden = status === "idle" || status === "error";
      invite.hidden = !card.hidden;
      invite.disabled = status === "connecting";
      error.hidden = status !== "error";
      error.textContent = status === "error" ? (message ?? "Could not start the call.") : "";
      if (status === "connecting") statusText.textContent = message ?? "Connecting";
      if (status === "live" && !root.dataset.activity) statusText.textContent = ACTIVITY.listening;
      if (status !== "live") delete root.dataset.activity;
      // A call that ends puts the card away; the next one opens full size.
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
  };
}
