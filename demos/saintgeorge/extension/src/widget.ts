/**
 * The corner of the school's page that is ours: the button that starts a
 * call, the card that holds Javier's face while it runs, and the
 * Español/English toggle. Its own words are in the language of the toggle.
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
  /** The language the call is in, or the next one starts in; the widget's
   *  own words follow it. */
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
  /** Show the extension's microphone grant page in a frame; `null` takes it away. */
  grant(src: string | null): void;
  /** Say that Chrome blocks the extension's microphone, with the way to the setting. */
  blocked(): void;
  onSettings(fn: () => void): void;
  /** Where the visitor put it and whether it is minimised, for the next page. */
  layout(): Layout;
  /** Put it back where the last page had it. */
  restore(layout: Layout): void;
  /** The visitor moved it or minimised it. */
  onLayout(fn: (layout: Layout) => void): void;
  /** A still of his face over the face's slot, until the live face is drawn
   *  (`unveil`); `null` for none. */
  setPoster(url: string | null): void;
  /** The live face is drawn: the poster fades out. */
  unveil(): void;
  /** His mouth strip (`MOUTH_STRIP`: four frames side by side, closed to
   *  open) in place of the poster's still, which comes back on `null`. */
  setMouthStrip(url: string | null): void;
  /** The strip's frame to show, 0 (closed) to 3 (open). Without a strip it
   *  changes nothing that shows. */
  setMouth(shape: 0 | 1 | 2 | 3): void;
  /** Whether the poster is up (not handed over to the live face). */
  posterShowing(): boolean;
}

/** Where the widget sits, as the visitor left it. */
export interface Layout {
  /** Its home corner: the distance from the viewport's right and bottom edges. */
  home: { right: number; bottom: number };
  minimised: boolean;
}

/** The widget's `view-transition-name`: across a same-origin page load in a
 *  call, the page changes under it while it stays where it is (`persist.ts`). */
export const TRANSITION_NAME = "voqalize-javier";

// The school's own colours, the theme's `--yellow` (#FFD200, its "Leer más"
// buttons, with its blue on them) for what the visitor presses, on a deep shade
// of its `--blue` (#1C3E93) so white words read on it; and the site's own
// Roboto Condensed, which the page has already loaded.
const BRAND = "#FFD200";
const BRAND_HOVER = "#F2C500";
const ON_BRAND = "#1C3E93";
const CARD_BG = "#142D6B";
const RAISED = "#1C3E93";
const INK = "#ffffff";
const LINE = "rgba(255, 255, 255, 0.18)";
const MUTED = "rgba(255, 255, 255, 0.72)";
const SANS = `"Roboto Condensed", "Helvetica Neue", system-ui, sans-serif`;
const SANS_MEDIUM = SANS;
const SANS_BOLD = SANS;
const EASE = "cubic-bezier(0.32, 0.72, 0, 1)";

/** The card's width, and so the face's: the face is square. */
const CARD = 200;
/** The minimised face's diameter. */
const BUBBLE = 64;
/** The gap kept from the viewport's edges and from anything it avoids. */
const GAP = 16;
/** Pointer travel below this is a click, above it a drag. */
const DRAG_PX = 5;

/** The widget's own words, in each language of the toggle. */
const WORDS = {
  es: {
    invite: "Habla con Javier",
    role: "Guía del Saint George's · voz",
    inviteLabel: "Habla por voz con Javier, el guía del Saint George's College",
    minimise: "Minimizar",
    mute: "Silenciar",
    unmute: "Activar",
    hang: "Colgar",
    credit: "Voz de Voqalize · preview",
    language: "Idioma",
    connecting: "Conectando",
    failed: "No se pudo iniciar la llamada.",
    grant: "La primera vez, Chrome pide el micrófono para la extensión de Javier.",
    blocked:
      "Chrome bloquea el micrófono para la extensión «Javier for Saint George's College». En la configuración del micrófono, quítala de «No pueden usar el micrófono» y vuelve a llamar.",
    settings: "Abrir la configuración",
    activity: { listening: "Escuchando", thinking: "Pensando", speaking: "Hablando" },
  },
  en: {
    invite: "Talk to Javier",
    role: "Saint George's guide · voice",
    inviteLabel: "Talk to Javier, Saint George's College's guide, by voice",
    minimise: "Minimise",
    mute: "Mute",
    unmute: "Unmute",
    hang: "End call",
    credit: "Voice by Voqalize · preview",
    language: "Language",
    connecting: "Connecting",
    failed: "Could not start the call.",
    grant: "The first time, Chrome asks for the microphone for Javier's extension.",
    blocked:
      "Chrome blocks the microphone for the “Javier for Saint George's College” extension. In the microphone settings, take it off “Not allowed to use your microphone”, then call again.",
    settings: "Open the settings",
    activity: { listening: "Listening", thinking: "Thinking", speaking: "Speaking" },
  },
} satisfies Record<Language, unknown>;

const STYLES = `
:host { all: initial; }
* { box-sizing: border-box; }
.root {
  position: fixed; left: 0; top: 0; z-index: 2147483001; width: max-content; pointer-events: auto;
  display: flex; flex-direction: column; align-items: flex-end; gap: 10px;
  font-family: ${SANS}; color: ${INK}; font-size: 14px; font-synthesis: none;
  -webkit-font-smoothing: antialiased;
  will-change: transform; touch-action: none;
}
.root.glide { transition: transform 500ms ${EASE}; }
.root.dragging { cursor: grabbing; }
button { font: inherit; cursor: pointer; }
.bold { font-family: ${SANS_BOLD}; font-weight: 700; }
.caps { text-transform: uppercase; letter-spacing: 0.08em; font-size: 11px;
  font-family: ${SANS_MEDIUM}; font-weight: 500; }

.invite {
  display: flex; align-items: center; gap: 12px; width: ${CARD + 20}px;
  background: ${CARD_BG}; border: 1px solid ${LINE}; border-radius: 14px;
  padding: 10px 14px 10px 10px; text-align: left; color: ${INK};
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
  transition: border-color 200ms ease, transform 200ms ease;
}
.invite:hover { border-color: ${BRAND}; transform: translateY(-1px); }
.invite:focus-visible { outline: 2px solid ${BRAND}; outline-offset: 2px; }
.invite:disabled { opacity: 0.7; cursor: progress; }
.still {
  width: 52px; height: 52px; border-radius: 50%; flex: none;
  background: ${RAISED} center 20% / cover no-repeat;
  box-shadow: 0 0 0 2px ${CARD_BG}, 0 0 0 4px ${BRAND};
}
.invite-text { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.invite-name { font-size: 17px; color: ${INK}; line-height: 1.1; }
.invite-role { color: ${MUTED}; font-size: 12px; }

.card {
  width: ${CARD}px; background: ${CARD_BG}; border: 1px solid ${LINE}; border-radius: 14px;
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.4);
  transition: width 300ms ${EASE}, border-radius 300ms ${EASE}, border-color 200ms;
  overflow: hidden;
}
.frame {
  position: relative; overflow: hidden; cursor: grab;
  width: ${CARD - 2}px; height: ${CARD - 2}px;
  transition: width 300ms ${EASE}, height 300ms ${EASE};
}
.face {
  width: ${CARD - 2}px; height: ${CARD - 2}px; background: ${RAISED};
  transform-origin: 0 0; transition: transform 300ms ${EASE};
}
.face > * { width: 100%; height: 100%; }
.poster {
  position: absolute; inset: 0; background: ${RAISED} center / cover no-repeat;
  transition: opacity 250ms ease; pointer-events: none;
}
.poster.gone { opacity: 0; }
/* His mouth strip: four frames of the face's box side by side, identical but
   for the mouth; the frame shown follows his voice's loudness. No transform,
   no animation: only the lips change. */
.poster[data-strip] { background-size: 400% 100%; background-position: 0% 0; }
.poster[data-strip][data-mouth="1"] { background-position-x: 33.333%; }
.poster[data-strip][data-mouth="2"] { background-position-x: 66.667%; }
.poster[data-strip][data-mouth="3"] { background-position-x: 100%; }
.minimise {
  position: absolute; top: 8px; right: 8px; width: 28px; height: 28px;
  display: grid; place-items: center; padding: 0; border-radius: 6px;
  background: rgba(34, 34, 34, 0.85); border: 1px solid ${LINE}; color: ${INK};
  opacity: 0; transition: opacity 200ms;
}
.card:hover .minimise, .minimise:focus-visible { opacity: 1; }
.body { width: ${CARD - 2}px; padding: 12px 14px; display: flex; flex-direction: column; gap: 10px; }
.head { display: flex; align-items: center; justify-content: space-between; gap: 8px; cursor: grab; }
.name { font-size: 19px; color: ${INK}; }
.status { color: ${MUTED}; display: flex; align-items: center; gap: 6px; }
.dot { width: 7px; height: 7px; border-radius: 50%; background: ${BRAND}; opacity: 0.35; transition: opacity 200ms; }
.root[data-activity="speaking"] .dot, .root[data-activity="listening"] .dot { opacity: 1; }
.buttons { display: flex; gap: 8px; }
.buttons button { flex: 1; height: 38px; border-radius: 8px; }
.ghost { background: transparent; border: 1px solid ${LINE}; color: ${INK}; }
.ghost:hover { border-color: ${INK}; }
.solid { background: ${BRAND}; border: 1px solid ${BRAND}; color: ${ON_BRAND}; }
.solid:hover { background: ${BRAND_HOVER}; border-color: ${BRAND_HOVER}; }
.ghost[aria-pressed="true"] { background: ${INK}; border-color: ${INK}; color: ${ON_BRAND}; }
.buttons button:focus-visible { outline: 2px solid ${BRAND}; outline-offset: 2px; }
.credit { color: ${MUTED}; font-size: 10px; letter-spacing: 0.08em; text-align: center; }
.lang { display: flex; gap: 4px; padding: 3px; border-radius: 999px; background: ${CARD_BG};
  border: 1px solid ${LINE}; width: ${CARD + 20}px; }
.card .lang { width: auto; background: ${RAISED}; }
.lang button { flex: 1; min-height: 30px; padding: 4px 10px; border: 0; border-radius: 999px;
  background: transparent; color: ${INK}; font-size: 13px; font-family: ${SANS_MEDIUM}; font-weight: 500; }
.lang button[aria-pressed="true"] { background: ${BRAND}; color: ${ON_BRAND}; cursor: default; }
.lang button.pending { opacity: 0.55; outline: 1px dashed ${BRAND}; outline-offset: -3px; }
.lang button:focus-visible { outline: 2px solid ${INK}; outline-offset: 2px; }
.grant { width: ${CARD + 20}px; background: ${CARD_BG}; border: 1px solid ${BRAND}; border-radius: 14px;
  padding: 8px 10px 4px; box-shadow: 0 6px 18px rgba(0,0,0,0.3); }
.grant-note { margin: 0 0 6px; font-size: 12px; line-height: 1.4; color: ${MUTED}; }
.grant iframe { display: block; width: 100%; height: 76px; border: 0; border-radius: 8px; background: #fff; }
.settings { margin-top: 8px; display: block; background: ${BRAND}; border: 1px solid ${BRAND}; color: ${ON_BRAND};
  border-radius: 8px; padding: 6px 10px; font-size: 12px; font-weight: 700; }
.settings:hover { background: ${BRAND_HOVER}; border-color: ${BRAND_HOVER}; }
.error { color: ${INK}; background: ${CARD_BG}; border: 1px solid #EC0000; border-radius: 8px; padding: 8px 10px;
  font-size: 12px; line-height: 1.4; max-width: ${CARD + 20}px; margin: 0; box-shadow: 0 6px 18px rgba(0,0,0,0.3); }
.error-text { margin: 0; }

.root[data-min] .card { width: ${BUBBLE}px; border-radius: 50%; border-color: ${BRAND}; cursor: pointer; }
.root[data-min] .frame { width: ${BUBBLE - 2}px; height: ${BUBBLE - 2}px; cursor: pointer; }
.root[data-min] .face { transform: scale(${(BUBBLE - 2) / (CARD - 2)}); }
.root[data-min] .body, .root[data-min] .minimise { display: none; }
.root[data-min][data-activity="speaking"] .card { animation: breathe 1.6s ease-in-out infinite; }
.root[data-min][data-muted] .card { border-color: ${MUTED}; }
@keyframes breathe {
  0%, 100% { box-shadow: 0 0 0 0 rgba(255, 210, 0, 0.55), 0 16px 40px rgba(0, 0, 0, 0.4); }
  50% { box-shadow: 0 0 0 6px rgba(255, 210, 0, 0), 0 16px 40px rgba(0, 0, 0, 0.4); }
}
@media (prefers-reduced-motion: reduce) {
  .root.glide, .card, .frame, .face { transition: none; }
  .root[data-min][data-activity="speaking"] .card { animation: none; }
}
[hidden] { display: none !important; }
`;

function overlaps(a: Rect, b: Rect): boolean {
  return a.left < b.right + GAP && a.right + GAP > b.left && a.top < b.bottom + GAP && a.bottom + GAP > b.top;
}

export function mountWidget(): Widget {
  const host = document.createElement("div");
  host.setAttribute("data-voqalize", "widget");
  // The widget speaks both languages itself, and Chrome's translator would
  // otherwise make "Javier" "Xavier" (the Clini guide, on a live call).
  host.setAttribute("translate", "no");
  host.classList.add("notranslate");
  const shadow = host.attachShadow({ mode: "open" });

  shadow.innerHTML = `
    <style>${STYLES}</style>
    <div class="root notranslate" translate="no" data-status="idle">
      <button class="invite" type="button">
        <span class="still"></span>
        <span class="invite-text">
          <span class="invite-name bold"></span>
          <span class="invite-role"></span>
        </span>
      </button>
      <div class="card" hidden>
        <div class="frame">
          <div class="face"></div>
          <div class="poster" data-mouth="0" hidden></div>
          <button class="minimise" type="button">
            <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M1 6h10" stroke="currentColor" stroke-width="1.4"/></svg>
          </button>
        </div>
        <div class="body">
          <div class="head">
            <span class="name bold">Javier</span>
            <span class="status caps"><span class="dot"></span><span class="status-text"></span></span>
          </div>
          <div class="lang-slot"></div>
          <div class="buttons">
            <button class="ghost caps mute" type="button" aria-pressed="false"></button>
            <button class="solid caps hang" type="button"></button>
          </div>
          <div class="credit caps"></div>
        </div>
      </div>
      <div class="lang" role="group">
        <button type="button" data-lang="es" lang="es" aria-pressed="true">Español</button>
        <button type="button" data-lang="en" lang="en" aria-pressed="false">English</button>
      </div>
      <div class="grant" hidden><p class="grant-note"></p></div>
      <div class="error" hidden><p class="error-text"></p><button class="settings" type="button" hidden></button></div>
      <audio autoplay></audio>
    </div>
  `;
  const root = shadow.querySelector<HTMLElement>(".root")!;
  // A fixed, see-through box over the viewport that holds the widget
  // (`contain` makes it the containing block of the fixed `.root`, so the
  // widget is painted, and captured for a view transition, as this one
  // element, which keeps its place across the page load). It takes no pointer
  // events; the widget does. Set inline, so no rule of the page's reaches it.
  host.style.cssText =
    "position:fixed;left:0;top:0;width:100vw;height:100vh;margin:0;padding:0;border:0;pointer-events:none;" +
    `z-index:2147483001;contain:layout style;view-transition-name:${TRANSITION_NAME}`;
  // <html>, not <body>: at `document_start` (a call carried over from the
  // last page, `shell.ts`) <html> is all there is.
  document.documentElement.appendChild(host);

  const $ = <T extends Element>(sel: string) => shadow.querySelector<T>(sel)!;
  const invite = $<HTMLButtonElement>(".invite");
  const card = $<HTMLElement>(".card");
  const statusText = $<HTMLElement>(".status-text");
  const error = $<HTMLElement>(".error");
  const errorText = $<HTMLElement>(".error-text");
  const settings = $<HTMLButtonElement>(".settings");
  const grant = $<HTMLElement>(".grant");
  const mute = $<HTMLButtonElement>(".mute");
  const hang = $<HTMLButtonElement>(".hang");
  const lang = $<HTMLElement>(".lang");
  const langSlot = $<HTMLElement>(".lang-slot");
  const langButtons = [...lang.querySelectorAll<HTMLButtonElement>("button")];
  const poster = $<HTMLElement>(".poster");
  let posterUrl: string | null = null;
  let stripUrl: string | null = null;
  const drawPoster = () => {
    const url = stripUrl ?? posterUrl;
    poster.toggleAttribute("data-strip", Boolean(stripUrl));
    poster.style.backgroundImage = url ? `url("${url}")` : "";
  };

  // ─── Where it sits ────────────────────────────────────────────────────

  let home = { right: 24, bottom: 24 };
  let obstacles: readonly Rect[] = [];
  let minimised = false;
  let squeezed = false;
  let openedAnyway = false;
  let at = { x: 0, y: 0 };
  let layoutFn: ((layout: Layout) => void) | null = null;
  const layoutNow = (): Layout => ({ home: { ...home }, minimised });

  function showMinimised(): boolean {
    return !card.hidden && (minimised || (squeezed && !openedAnyway));
  }

  /** The widget's size, measured; the bubble's when minimised. */
  function sizeOf(bubble: boolean): { w: number; h: number } {
    if (bubble) return { w: BUBBLE, h: BUBBLE };
    let h = 0;
    let w = 0;
    for (const child of [invite, card, lang, grant, error]) {
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
    layoutFn?.(layoutNow());
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
    layoutFn?.(layoutNow());
  });
  card.addEventListener("click", () => {
    if (!root.hasAttribute("data-min")) return;
    minimised = false;
    if (squeezed) openedAnyway = true;
    place(true);
    settle();
    layoutFn?.(layoutNow());
  });

  // ─── The language toggle, and the widget's own words ──────────────────

  let languageFn: ((language: Language) => void) | null = null;
  for (const b of langButtons) {
    b.addEventListener("click", () => languageFn?.(b.dataset.lang as Language));
  }

  let words: (typeof WORDS)[Language] = WORDS.es;
  let muted = false;

  /** Write the widget's own words in `language`, the status line included
   *  when it shows what he is doing. */
  function speak(language: Language): void {
    words = WORDS[language];
    root.lang = language;
    $<HTMLElement>(".invite-name").textContent = words.invite;
    $<HTMLElement>(".invite-role").textContent = words.role;
    invite.setAttribute("aria-label", words.inviteLabel);
    $<HTMLElement>(".minimise").setAttribute("aria-label", words.minimise);
    mute.textContent = muted ? words.unmute : words.mute;
    hang.textContent = words.hang;
    $<HTMLElement>(".credit").textContent = words.credit;
    $<HTMLElement>(".grant-note").textContent = words.grant;
    settings.textContent = words.settings;
    lang.setAttribute("aria-label", words.language);
    const activity = root.dataset.activity as Activity | undefined;
    if (activity) statusText.textContent = words.activity[activity];
  }
  speak("es");

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
      errorText.textContent = status === "error" ? (message ?? words.failed) : "";
      settings.hidden = true;
      if (status === "connecting") statusText.textContent = message ?? words.connecting;
      if (status === "live" && !root.dataset.activity) statusText.textContent = words.activity.listening;
      if (status !== "live") delete root.dataset.activity;
      if (card.hidden) minimised = false;
      if (wasHidden !== card.hidden) settle();
    },
    setActivity(activity) {
      root.dataset.activity = activity;
      statusText.textContent = words.activity[activity];
    },
    setMuted(next) {
      muted = next;
      mute.setAttribute("aria-pressed", String(next));
      mute.textContent = next ? words.unmute : words.mute;
      root.toggleAttribute("data-muted", next);
    },
    setStill(url) {
      $<HTMLElement>(".still").style.backgroundImage = `url("${url}")`;
    },
    setLanguage(language) {
      speak(language);
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
    grant(src) {
      grant.querySelector("iframe")?.remove();
      grant.hidden = !src;
      if (src) {
        const frame = document.createElement("iframe");
        // The extension's page asks for the microphone itself: the prompt
        // names the extension, and the grant is the extension's.
        frame.allow = "microphone";
        frame.src = src;
        grant.appendChild(frame);
      }
      settle();
    },
    blocked() {
      this.paint("error", words.blocked);
      settings.hidden = false;
      settle();
    },
    onSettings: (fn) => settings.addEventListener("click", fn),
    layout: layoutNow,
    restore(layout) {
      home = { right: layout.home.right, bottom: layout.home.bottom };
      minimised = layout.minimised && !card.hidden;
      place(false);
    },
    onLayout(fn) {
      layoutFn = fn;
    },
    setPoster(url) {
      posterUrl = url;
      poster.hidden = !url;
      poster.classList.remove("gone");
      if (!url) stripUrl = null;
      drawPoster();
    },
    unveil() {
      poster.classList.add("gone");
      setTimeout(() => {
        if (poster.classList.contains("gone")) poster.hidden = true;
      }, 300);
    },
    setMouthStrip(url) {
      stripUrl = url;
      drawPoster();
    },
    setMouth(shape) {
      if (poster.dataset.mouth !== String(shape)) poster.dataset.mouth = String(shape);
    },
    posterShowing: () => !poster.hidden && !poster.classList.contains("gone"),
  };
}
