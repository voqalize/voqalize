/**
 * The corner of a site's page that is the extension's: the button that
 * starts a call, the card that holds the character's face while it runs, and
 * the language toggle. Its words come in each language of the toggle; its
 * colours and type are the site's (`WidgetTheme`), and a site whose look needs
 * more replaces or extends the stylesheet (`styles`, `css`). The classes the
 * markup carries are the stylesheet's contract.
 *
 * It lives in a shadow root so that neither side's styles reach the other. It
 * takes a bottom corner; the visitor can drag it anywhere and minimise the
 * card to the face alone, and the call and its audio carry on. It keeps clear
 * of what the page pins over its corners (`avoid`), moving up above it or
 * minimising where nothing fits.
 *
 * It also holds the extension's microphone grant (a frame of `grant.html`) on
 * the first call, and the way to Chrome's setting when the microphone is
 * blocked. In a call it is mounted early by the shell on the next page of the
 * tab, as the last page left it, and stays put through the page load's view
 * transition.
 */

export type Status = "idle" | "connecting" | "live" | "error";
export type Activity = "listening" | "thinking" | "speaking";
/** A BCP-47 tag from the site's languages. */
export type Language = string;

/** A rectangle in viewport pixels. */
export interface Rect {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

/** The widget's own words, in one language. */
export interface WidgetWords {
  invite: string;
  role: string;
  inviteLabel: string;
  minimise: string;
  mute: string;
  unmute: string;
  muteLabel?: string;
  hang: string;
  credit: string;
  language: string;
  connecting: string;
  failed: string;
  grant: string;
  blocked: string;
  settings: string;
  activity: Record<Activity, string>;
}

export interface WidgetTheme {
  /** What the visitor presses: the solid button, the toggle's choice. */
  brand: string;
  brandHover?: string;
  onBrand?: string;
  /** The card and invite's background, their text, borders, quiet text. */
  card: string;
  ink: string;
  line: string;
  muted: string;
  /** The face's backdrop and the toggle's track. */
  raised: string;
  /** The live dot, the pulse and focus rings. */
  live?: string;
  font?: string;
  boldFont?: string;
  radius?: number;
}

export interface WidgetConfig {
  /** The character's name, on the card. */
  name: string;
  /** The toggle's languages, in order: code and label. */
  languages: readonly { code: Language; label: string }[];
  words: Record<Language, WidgetWords>;
  /** Its home corner (`right` by default). */
  corner?: "left" | "right";
  /** The last-resort top-left place keeps this far below the top (16 px):
   *  clear of a site's fixed bar. */
  topClear?: number;
  theme?: WidgetTheme;
  /** Replaces the default stylesheet entirely. */
  styles?: string;
  /** Appended to the stylesheet. */
  css?: string;
  /** The host's `view-transition-name` ("voqalize-widget"). */
  transitionName?: string;
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
  /** The language the call is in, or the next one starts in; the widget's own
   *  words follow it. */
  setLanguage(language: Language): void;
  /** A language asked for on the toggle and not yet confirmed; `null` for none. */
  setLanguagePending(language: Language | null): void;
  /** What on the page the widget must not cover; empty when nothing is open. */
  avoid(obstacles: readonly Rect[]): void;
  onCall(fn: () => void): void;
  /** The visitor is reaching for the invite: a pointer over it, or focus. */
  onReach(fn: () => void): void;
  onMute(fn: () => void): void;
  onLanguage(fn: (language: Language) => void): void;
  onHang(fn: () => void): void;
  /** Show the extension's microphone grant page in a frame; `null` takes it away. */
  grant(src: string | null): void;
  /** Say that Chrome blocks the extension's microphone, with the way to the setting. */
  blocked(): void;
  onSettings(fn: () => void): void;
  layout(): Layout;
  restore(layout: Layout): void;
  onLayout(fn: (layout: Layout) => void): void;
  /** The face's slot empty until the live face is drawn (`unveil`). */
  veil(): void;
  unveil(): void;
}

/** Where the widget sits, as the visitor left it. */
export interface Layout {
  /** Its home: the distance from the home corner's side edge, and from the bottom. */
  home: { side: number; bottom: number };
  minimised: boolean;
}

export const DEFAULT_TRANSITION_NAME = "voqalize-widget";

const CARD = 200;
const BUBBLE = 64;
const GAP = 16;
const DRAG_PX = 5;
const EASE = "cubic-bezier(0.32, 0.72, 0, 1)";

const NEUTRAL: WidgetTheme = {
  brand: "#111111",
  onBrand: "#ffffff",
  card: "#ffffff",
  ink: "#1a1a1a",
  line: "#e3e3e3",
  muted: "#6b6b6b",
  raised: "#f2f2f2",
  live: "#C2410C",
  font: `system-ui, "Helvetica Neue", Arial, sans-serif`,
  radius: 8,
};

/** The default stylesheet, coloured by `theme`. */
export function widgetStyles(theme: WidgetTheme = NEUTRAL, corner: "left" | "right" = "right"): string {
  const t = { ...NEUTRAL, ...theme };
  const live = t.live ?? t.brand;
  const r = t.radius ?? 8;
  const bold = t.boldFont ?? t.font;
  return `
:host { all: initial; }
* { box-sizing: border-box; }
.root {
  position: fixed; left: 0; top: 0; z-index: 2147483001; width: max-content; pointer-events: auto;
  display: flex; flex-direction: column; align-items: ${corner === "left" ? "flex-start" : "flex-end"}; gap: 10px;
  font-family: ${t.font}; color: ${t.ink}; font-size: 14px; -webkit-font-smoothing: antialiased;
  will-change: transform; touch-action: none;
}
.root.glide { transition: transform 500ms ${EASE}; }
.root.dragging { cursor: grabbing; }
button { font: inherit; cursor: pointer; }
.bold { font-family: ${bold}; font-weight: 700; }
.caps { text-transform: uppercase; letter-spacing: 0.1em; font-size: 11px; font-weight: 600; }
.invite {
  display: flex; align-items: center; gap: 12px; width: ${CARD + 20}px;
  background: ${t.card}; border: 1px solid ${t.line}; border-radius: ${r}px;
  padding: 10px 14px 10px 10px; text-align: left; color: ${t.ink};
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.16);
  transition: border-color 200ms ease, transform 200ms ease;
}
.invite:hover { border-color: ${t.brand}; transform: translateY(-1px); }
.invite:focus-visible { outline: 2px solid ${live}; outline-offset: 2px; }
.invite:disabled { opacity: 0.7; cursor: progress; }
.still { width: 52px; height: 52px; border-radius: 50%; flex: none; background: ${t.raised} center 20% / cover no-repeat;
  box-shadow: 0 0 0 2px ${t.card}, 0 0 0 3px ${t.line}; }
.invite-text { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.invite-name { font-size: 15px; color: ${t.ink}; line-height: 1.2; }
.invite-role { color: ${t.muted}; font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.card { width: ${CARD}px; background: ${t.card}; border: 1px solid ${t.line}; border-radius: ${r}px;
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.2);
  transition: width 300ms ${EASE}, border-radius 300ms ${EASE}, border-color 200ms; overflow: hidden; }
.frame { position: relative; overflow: hidden; cursor: grab; width: ${CARD - 2}px; height: ${CARD - 2}px;
  transition: width 300ms ${EASE}, height 300ms ${EASE}; }
.face { width: ${CARD - 2}px; height: ${CARD - 2}px; background: ${t.raised}; transform-origin: 0 0; transition: transform 300ms ${EASE}; }
.face > * { width: 100%; height: 100%; transition: opacity 250ms ease; }
.face.veiled > * { opacity: 0; }
.minimise { position: absolute; top: 8px; right: 8px; width: 28px; height: 28px; display: grid; place-items: center;
  padding: 0; border-radius: ${Math.min(r, 6)}px; background: ${t.card}; border: 1px solid ${t.line}; color: ${t.ink};
  opacity: 0; transition: opacity 200ms; }
.card:hover .minimise, .minimise:focus-visible { opacity: 1; }
.body { width: ${CARD - 2}px; padding: 12px 14px; display: flex; flex-direction: column; gap: 10px; }
.head { display: flex; align-items: center; justify-content: space-between; gap: 8px; cursor: grab; }
.name { font-size: 16px; color: ${t.ink}; }
.status { color: ${t.muted}; display: flex; align-items: center; gap: 6px; font-size: 10px; }
.dot { width: 7px; height: 7px; border-radius: 50%; background: ${live}; opacity: 0.35; transition: opacity 200ms; }
.root[data-activity="speaking"] .dot, .root[data-activity="listening"] .dot { opacity: 1; }
.buttons { display: flex; gap: 8px; }
.buttons button { flex: 1; height: 38px; border-radius: ${r}px; }
.buttons button:focus-visible { outline: 2px solid ${live}; outline-offset: 2px; }
.ghost { background: transparent; border: 1px solid ${t.line}; color: ${t.ink}; }
.ghost:hover { border-color: ${t.ink}; }
.ghost[aria-pressed="true"] { background: ${t.ink}; border-color: ${t.ink}; color: ${t.card}; }
.solid { background: ${t.brand}; border: 1px solid ${t.brand}; color: ${t.onBrand}; }
.solid:hover { background: ${t.brandHover ?? t.brand}; border-color: ${t.brandHover ?? t.brand}; }
.credit { color: ${t.muted}; font-size: 9px; text-align: center; }
.lang { display: flex; gap: 4px; padding: 3px; border-radius: ${r}px; background: ${t.raised}; width: ${CARD + 20}px; }
.card .lang { width: auto; }
.lang button { flex: 1; min-height: 30px; padding: 4px 10px; border: 0; border-radius: ${r}px;
  background: transparent; color: ${t.ink}; font-size: 12px; }
.lang button[aria-pressed="true"] { background: ${t.brand}; color: ${t.onBrand}; cursor: default; }
.lang button.pending { opacity: 0.55; outline: 1px dashed ${t.brand}; outline-offset: -3px; }
.lang button:focus-visible { outline: 2px solid ${live}; outline-offset: 2px; }
.error { color: ${t.ink}; background: ${t.card}; border: 1px solid ${live}; border-radius: ${r}px; padding: 8px 10px;
  font-size: 12px; line-height: 1.4; max-width: ${CARD + 20}px; margin: 0; box-shadow: 0 6px 18px rgba(0,0,0,0.12); }
.error-text { margin: 0; }
.settings { margin-top: 8px; display: block; height: 32px; padding: 0 12px; border-radius: ${r}px;
  background: transparent; border: 1px solid ${t.line}; color: ${t.ink}; }
.grant { width: ${CARD + 20}px; background: ${t.card}; border: 1px solid ${t.line}; border-radius: ${r}px;
  padding: 8px 10px 4px; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.14); }
.grant-note { margin: 0 0 6px; font-size: 12px; line-height: 1.4; color: ${t.muted}; }
.grant iframe { display: block; width: 100%; height: 84px; border: 0; background: #fff; }
.root[data-min] .card { width: ${BUBBLE}px; border-radius: 50%; border-color: ${t.brand}; cursor: pointer; }
.root[data-min] .frame { width: ${BUBBLE - 2}px; height: ${BUBBLE - 2}px; cursor: pointer; }
.root[data-min] .face { transform: scale(${(BUBBLE - 2) / (CARD - 2)}); }
.root[data-min] .body, .root[data-min] .minimise { display: none; }
.root[data-min][data-activity="speaking"] .card { animation: breathe 1.6s ease-in-out infinite; }
.root[data-min][data-muted] .card { border-color: ${t.muted}; }
@keyframes breathe {
  0%, 100% { box-shadow: 0 0 0 0 color-mix(in srgb, ${live} 50%, transparent), 0 16px 40px rgba(0, 0, 0, 0.16); }
  50% { box-shadow: 0 0 0 6px transparent, 0 16px 40px rgba(0, 0, 0, 0.16); }
}
@media (prefers-reduced-motion: reduce) {
  .root.glide, .card, .frame, .face, .face > * { transition: none; }
  .root[data-min][data-activity="speaking"] .card { animation: none; }
}
[hidden] { display: none !important; }
`;
}

function overlaps(a: Rect, b: Rect): boolean {
  return a.left < b.right + GAP && a.right + GAP > b.left && a.top < b.bottom + GAP && a.bottom + GAP > b.top;
}

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);

export function mountWidget(config: WidgetConfig): Widget {
  const corner = config.corner ?? "right";
  const left = corner === "left";
  const topClear = config.topClear ?? GAP;
  const transitionName = config.transitionName ?? DEFAULT_TRANSITION_NAME;
  const host = document.createElement("div");
  host.setAttribute("data-voqalize", "widget");
  // The widget speaks its languages itself; a page translator would rename
  // the character.
  host.setAttribute("translate", "no");
  host.classList.add("notranslate");
  const shadow = host.attachShadow({ mode: "open" });
  const styles = (config.styles ?? widgetStyles(config.theme, corner)) + (config.css ?? "");
  const langs = config.languages
    .map((l) => `<button type="button" data-lang="${esc(l.code)}" lang="${esc(l.code)}" aria-pressed="false">${esc(l.label)}</button>`)
    .join("");

  shadow.innerHTML = `
    <style>${styles}</style>
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
          <button class="minimise" type="button">
            <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M1 6h10" stroke="currentColor" stroke-width="1.4"/></svg>
          </button>
        </div>
        <div class="body">
          <div class="head">
            <span class="name bold">${esc(config.name)}</span>
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
      <div class="lang" role="group"${config.languages.length < 2 ? " hidden" : ""}>${langs}</div>
      <div class="grant" hidden><p class="grant-note"></p></div>
      <div class="error" hidden><p class="error-text"></p><button class="ghost caps settings" type="button" hidden></button></div>
      <audio autoplay></audio>
    </div>
  `;
  const root = shadow.querySelector<HTMLElement>(".root")!;
  // A fixed, see-through box over the viewport that holds the widget
  // (`contain` makes it the containing block of the fixed `.root`, so the
  // widget is painted, and captured for a view transition, as this one
  // element). It takes no pointer events; the widget does. Inline, so no rule
  // of the page's reaches it.
  host.style.cssText =
    "position:fixed;left:0;top:0;width:100vw;height:100vh;margin:0;padding:0;border:0;pointer-events:none;" +
    `z-index:2147483001;contain:layout style;view-transition-name:${transitionName}`;
  // <html>, not <body>: a site may zoom or transform <body>, and at
  // `document_start` (the shell) <html> is all there is.
  document.documentElement.appendChild(host);

  const $ = <T extends Element>(sel: string) => shadow.querySelector<T>(sel)!;
  const invite = $<HTMLButtonElement>(".invite");
  const card = $<HTMLElement>(".card");
  const statusText = $<HTMLElement>(".status-text");
  const error = $<HTMLElement>(".error");
  const errorText = $<HTMLElement>(".error-text");
  const settings = $<HTMLButtonElement>(".settings");
  const grant = $<HTMLElement>(".grant");
  const face = $<HTMLElement>(".face");
  const mute = $<HTMLButtonElement>(".mute");
  const hang = $<HTMLButtonElement>(".hang");
  const lang = $<HTMLElement>(".lang");
  const langSlot = $<HTMLElement>(".lang-slot");
  const langButtons = [...lang.querySelectorAll<HTMLButtonElement>("button")];

  // ─── Where it sits ────────────────────────────────────────────────────

  let home = { side: 24, bottom: 24 };
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

  /** The first place, in order, where a widget of this size covers nothing
   *  open: its home; the other bottom corner; the top-left under the site's
   *  bar. A place that would cover something moves up above it. */
  function fit(w: number, h: number): { x: number; y: number } | null {
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const clampX = (x: number) => Math.min(Math.max(x, GAP), vw - w - GAP);
    const clampY = (y: number) => Math.min(Math.max(y, GAP), vh - h - GAP);
    const candidates = [
      { x: clampX(left ? home.side : vw - home.side - w), y: clampY(vh - home.bottom - h) },
      { x: left ? vw - w - GAP : GAP, y: vh - h - GAP },
      { x: GAP, y: topClear },
    ];
    for (const c of candidates) {
      let y = c.y;
      for (let n = 0; n < 4; n++) {
        const box = { left: c.x, top: y, right: c.x + w, bottom: y + h };
        const hit = obstacles.find((o) => overlaps(box, o));
        if (!hit) break;
        y = hit.top - h - GAP;
      }
      if (c.x < GAP - 0.5 || y < GAP - 0.5) continue;
      const box = { left: c.x, top: y, right: c.x + w, bottom: y + h };
      if (!obstacles.some((o) => overlaps(box, o))) return { x: c.x, y };
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
      spot = { x: left ? GAP : window.innerWidth - w - GAP, y: window.innerHeight - h - GAP };
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
    if ((e.target as Element).closest(".mute, .hang, .minimise, .lang")) return;
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
    at = {
      x: Math.min(Math.max(e.clientX - drag.dx, 0), window.innerWidth - root.offsetWidth),
      y: Math.min(Math.max(e.clientY - drag.dy, 0), window.innerHeight - root.offsetHeight),
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
      side: left ? at.x : window.innerWidth - at.x - root.offsetWidth,
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
  for (const b of langButtons) b.addEventListener("click", () => languageFn?.(b.dataset.lang!));

  const first = config.languages[0]?.code ?? Object.keys(config.words)[0]!;
  let words: WidgetWords = config.words[first]!;
  let muted = false;

  function speak(language: Language): void {
    words = config.words[language] ?? config.words[first]!;
    root.lang = language;
    $<HTMLElement>(".invite-name").textContent = words.invite;
    $<HTMLElement>(".invite-role").textContent = words.role;
    invite.setAttribute("aria-label", words.inviteLabel);
    $<HTMLElement>(".minimise").setAttribute("aria-label", words.minimise);
    mute.textContent = muted ? words.unmute : words.mute;
    if (words.muteLabel) mute.setAttribute("aria-label", words.muteLabel);
    hang.textContent = words.hang;
    $<HTMLElement>(".credit").textContent = words.credit;
    $<HTMLElement>(".grant-note").textContent = words.grant;
    settings.textContent = words.settings;
    lang.setAttribute("aria-label", words.language);
    const activity = root.dataset.activity as Activity | undefined;
    if (activity) statusText.textContent = words.activity[activity];
  }
  speak(first);

  return {
    face,
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
      for (const b of langButtons) {
        b.setAttribute("aria-pressed", String(b.dataset.lang === language));
        b.classList.remove("pending");
      }
      speak(language);
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
      const h = layout.home as Partial<{ side: number; left: number; right: number; bottom: number }>;
      home = { side: h.side ?? h.left ?? h.right ?? 24, bottom: h.bottom ?? 24 };
      minimised = layout.minimised && !card.hidden;
      place(false);
    },
    onLayout(fn) {
      layoutFn = fn;
    },
    veil() {
      face.classList.add("veiled");
    },
    unveil() {
      face.classList.remove("veiled");
    },
  };
}

/** Keep the widget clear of what the page pins over its corners, read again
 *  every second and on resize. */
export function watchObstacles(
  widget: Widget,
  obstacles: readonly { selector: string; fixedOnly?: boolean }[],
): () => void {
  if (!obstacles.length) return () => {};
  let last = "";
  const read = () => {
    const rects = obstacles
      .flatMap(({ selector, fixedOnly }) =>
        [...document.querySelectorAll<HTMLElement>(selector)].filter((el) => {
          const style = getComputedStyle(el);
          if (style.display === "none" || style.visibility === "hidden") return false;
          return !fixedOnly || style.position === "fixed" || style.position === "sticky";
        }),
      )
      .map((el) => el.getBoundingClientRect())
      .filter((r) => r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < window.innerHeight)
      .map((r) => ({ left: r.left, top: r.top, right: r.right, bottom: r.bottom }));
    const key = JSON.stringify(rects.map((r) => [r.left, r.top, r.right, r.bottom].map(Math.round)));
    if (key === last) return;
    last = key;
    widget.avoid(rects);
  };
  read();
  const timer = setInterval(read, 1000);
  window.addEventListener("resize", read);
  return () => {
    clearInterval(timer);
    window.removeEventListener("resize", read);
  };
}
