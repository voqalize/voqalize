/**
 * The corner of Qween's page that is ours: the button that starts a call and
 * the card that holds Trisha's face while it runs.
 *
 * It lives in a shadow root so that neither side's styles reach the other, and
 * it is set in Qween's own typefaces, which their page has already loaded: the
 * sans of their labels and the display serif of their product names. The
 * palette is theirs too: ivory ground, black square-cornered buttons in tracked
 * capitals, and the gold of their hairlines.
 */

export type Status = "idle" | "connecting" | "live" | "error";
export type Activity = "listening" | "thinking" | "speaking";

export interface Widget {
  /** Where the avatar mounts. */
  readonly face: HTMLElement;
  /** Where the bot's audio plays. */
  readonly audio: HTMLAudioElement;
  paint(status: Status, message?: string): void;
  setActivity(activity: Activity): void;
  setMuted(muted: boolean): void;
  setStill(url: string): void;
  onCall(fn: () => void): void;
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

const STYLES = `
:host { all: initial; }
* { box-sizing: border-box; }
.root {
  position: fixed; right: 24px; bottom: 24px; z-index: 2147483001;
  font-family: ${SANS}; color: ${INK};
  -webkit-font-smoothing: antialiased;
}
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
  width: 256px; background: ${IVORY}; border: 1px solid ${HAIRLINE};
  box-shadow: 0 16px 40px rgba(17, 17, 17, 0.12);
}
.face { width: 100%; aspect-ratio: 1 / 1; background: #f3ece4; position: relative; overflow: hidden; }
.face > * { width: 100%; height: 100%; }
.body { padding: 14px 16px 14px; display: flex; flex-direction: column; gap: 10px; }
.head { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
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
.error { color: #8a2d2d; font-size: 12px; line-height: 1.4; max-width: 256px; }

[hidden] { display: none !important; }
`;

const ACTIVITY: Record<Activity, string> = {
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
};

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
        <div class="face"></div>
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

  return {
    face: $<HTMLElement>(".face"),
    audio: $<HTMLAudioElement>("audio"),
    paint(status, message) {
      root.dataset.status = status;
      // The card appears on the press, not when the call goes live: the face
      // loads during call setup and "Connecting" is worth seeing.
      card.hidden = status === "idle" || status === "error";
      invite.hidden = !card.hidden;
      invite.disabled = status === "connecting";
      error.hidden = status !== "error";
      error.textContent = status === "error" ? (message ?? "Could not start the call.") : "";
      if (status === "connecting") statusText.textContent = message ?? "Connecting";
      if (status === "live" && !root.dataset.activity) statusText.textContent = ACTIVITY.listening;
      if (status !== "live") delete root.dataset.activity;
    },
    setActivity(activity) {
      root.dataset.activity = activity;
      statusText.textContent = ACTIVITY[activity];
    },
    setMuted(muted) {
      mute.setAttribute("aria-pressed", String(muted));
      mute.textContent = muted ? "Unmute" : "Mute";
    },
    setStill(url) {
      $<HTMLElement>(".still").style.backgroundImage = `url("${url}")`;
    },
    onCall: (fn) => invite.addEventListener("click", fn),
    onMute: (fn) => mute.addEventListener("click", fn),
    onHang: (fn) => hang.addEventListener("click", fn),
  };
}
