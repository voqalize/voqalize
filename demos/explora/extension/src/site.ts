/**
 * Who Explora is, for every part of the extension: its two hosts, the widget
 * dressed as Explora dresses its own pages, the moves Javier makes, and where
 * a booking step starts on reservations.explora.com.
 *
 * Every entry point starts the shared host from `@voqalize/stage/extension`
 * with this one `SiteConfig`; what is Explora's own is the adapters
 * (`explora-actions.ts`, `reservations-actions.ts`), the site's languages
 * (`site-language.ts`) and what is here.
 */

import type { ArgsOf, MoveId, SliceOf } from "@voqalize/stage";
import { defineSite, type WidgetWords } from "@voqalize/stage/extension";

import { scene } from "./scene.gen";
import { BOOKING, SITE } from "./site-language";

type Spec = typeof scene.spec;

/** The moves the brain sends, by id: declared in `explora/scene.json`. */
export const MOVE = {
  show: "core.show",
  faq: "core.faq",
  navigate: "explora.navigate",
  twin: "explora.twin",
  checkAvailability: "explora.check_availability",
  chooseRoom: "explora.choose_room",
  fillEnquiry: "explora.fill_enquiry",
  sendEnquiry: "explora.send_enquiry",
  focusTab: "explora.focus_tab",
} as const satisfies Record<string, MoveId<Spec>>;

// ─── The page's state, as Stage state events ──────────────────────────────

/** The `stay` slice: the booking calendar or the rooms and rates. */
export type StayState = SliceOf<Spec, "stay">;
export type NightsOption = NonNullable<StayState["nights"]>[number];
export type RoomOption = NonNullable<StayState["rooms"]>[number];
/** The `enquiry` slice: which fields are filled, never what they hold. */
export type EnquiryState = SliceOf<Spec, "enquiry">;
/** What the enquiry form holds, read on the page for its own checks; only
 *  the names of the filled fields leave it. */
export interface EnquiryFields {
  title?: string;
  first_name?: string;
  last_name?: string;
  email?: string;
  phone?: string;
  country?: string;
  message?: string;
}
/** The enquiry as the page reads it, before it is reported. */
export type EnquiryReport = Omit<EnquiryState, "filled"> & { filled: EnquiryFields };

type Emit = (event: string, payload: unknown) => void;

/** The adapters report the page's state under these names; each goes to the
 *  agent as the Stage state event for its slice, through `scene.event`, which
 *  sends only what the slice declares. */
const STATE: Record<string, "page.changed" | "stay.changed" | "enquiry.changed"> = {
  page_changed: "page.changed",
  stay_state: "stay.changed",
  enquiry_state: "enquiry.changed",
};

/** `emit`, with the page's state sent as Stage state events and every other
 *  report (an act: an enquiry sent, a language asked for) as it is. */
export function asStage(emit: Emit): Emit {
  return (event, payload) => {
    const name = STATE[event];
    if (!name) return emit(event, payload);
    let data = payload as Record<string, unknown>;
    if (name === "enquiry.changed") {
      const filled = (data.filled ?? {}) as Record<string, unknown>;
      data = { ...data, filled: Object.keys(filled).filter((k) => filled[k]) };
    }
    emit("stage_event", scene.event(name, data as never));
  };
}

/** The moves made on the booking site: from www.explora.com they load it first. */
export const BOOKING_MOVES = new Set<string>([
  MOVE.checkAvailability,
  MOVE.chooseRoom,
  MOVE.fillEnquiry,
  MOVE.sendEnquiry,
]);

/** The events the brain takes from any tab, not only the one in front: the
 *  toggle, an enquiry the visitor sent, and how a move found a page's twin. */
export const ANY_TAB = ["language_requested", "enquiry_sent", "twin_lookup"] as const;

// ─── The moves' arguments, as the brain sends them ────────────────────────

export type NavigateArgs = ArgsOf<Spec, typeof MOVE.navigate>;
export type CheckAvailabilityArgs = ArgsOf<Spec, typeof MOVE.checkAvailability>;
export type ChooseRoomArgs = ArgsOf<Spec, typeof MOVE.chooseRoom>;
export type FillEnquiryArgs = ArgsOf<Spec, typeof MOVE.fillEnquiry>;

/** The page of the booking site a booking move starts on, so the move lands
 *  where the booking adapter would load it itself: one load, not two. */
export function bookingUrl(move: string, args: unknown, language: string): string | null {
  const lang = language === "es" ? "ES" : "EN";
  if (move === MOVE.checkAvailability) {
    const p = args as CheckAvailabilityArgs;
    const q = new URLSearchParams({ hotel_code: p.hotel_code });
    if (p.date) q.set("check_in_date", p.date);
    q.set("language", p.language ?? lang);
    return `${BOOKING}/ibe/paso1?${q}`;
  }
  if (move === MOVE.fillEnquiry) {
    const p = args as FillEnquiryArgs;
    const code = encodeURIComponent(p.expedition_code.toUpperCase());
    return `${BOOKING}/ibe/expeditions?expedition_request=${code}&language=${p.language ?? lang}`;
  }
  return null;
}

// ─── The widget, dressed as Explora ───────────────────────────────────────

/** A warm terracotta, which reads on Explora's black-and-sand pages: the
 *  spotlight's ring and the live dot. */
export const RING = "#C2410C";

// Explora's own black and white, read off their buttons and headings, with
// the warm sand of their deserts and the ring's terracotta for what is live.
const BRAND = "#000000";
const INK = "#1a1a1a";
const LINE = "#e3ddd2";
const MUTED = "#6f6a62";
const SAND = "#f3eee5";
const SAND_DEEP = "#d9ccb6";
const SANS = `ObjektivMk1Regular, "Helvetica Neue", system-ui, sans-serif`;
const BOLD = `ObjektivMk1Bold, "Helvetica Neue", system-ui, sans-serif`;
const EASE = "cubic-bezier(0.32, 0.72, 0, 1)";
const CARD = 200;
const BUBBLE = 64;

/** The widget's stylesheet: white, black, a warm sand, Explora's Objektiv
 *  type (already loaded by the page), square-cornered black buttons in
 *  spaced capitals. Over the shared widget's markup. */
const STYLES = `
:host { all: initial; }
* { box-sizing: border-box; }
.root {
  position: fixed; left: 0; top: 0; z-index: 2147483001; width: max-content; pointer-events: auto;
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
  color: ${BRAND}; line-height: 1.2; }
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
.face > * { width: 100%; height: 100%; transition: opacity 250ms ease; }
.face.veiled > * { opacity: 0; }
.minimise {
  position: absolute; top: 8px; right: 8px; width: 28px; height: 28px;
  display: grid; place-items: center; padding: 0; border-radius: 2px;
  background: rgba(255, 255, 255, 0.9); border: 1px solid ${LINE}; color: ${INK};
  opacity: 0; transition: opacity 200ms;
}
.card:hover .minimise, .minimise:focus-visible { opacity: 1; }
.body { width: ${CARD - 2}px; padding: 12px 14px; display: flex; flex-direction: column; gap: 10px; }
.head { display: flex; align-items: center; justify-content: space-between; gap: 8px; cursor: grab; }
.name { font-family: ${BOLD}; font-size: 14px; letter-spacing: 0.16em; text-transform: uppercase; color: ${BRAND}; }
.status { color: ${MUTED}; display: flex; align-items: center; gap: 6px; letter-spacing: 0.1em; font-size: 10px; }
.dot { width: 7px; height: 7px; border-radius: 50%; background: ${RING}; opacity: 0.35; transition: opacity 200ms; }
.root[data-activity="speaking"] .dot, .root[data-activity="listening"] .dot { opacity: 1; }
.buttons { display: flex; gap: 8px; }
.buttons button { flex: 1; height: 38px; border-radius: 2px; }
.ghost { background: #fff; border: 1px solid ${BRAND}; color: ${BRAND}; }
.solid { background: ${BRAND}; border: 1px solid ${BRAND}; color: #fff; }
.ghost[aria-pressed="true"] { background: ${SAND}; color: ${BRAND}; }
.credit { color: ${MUTED}; font-size: 9px; text-align: center; }
.lang { display: flex; gap: 4px; padding: 3px; border-radius: 2px; background: ${SAND}; width: ${CARD + 20}px; }
.card .lang { width: auto; }
.lang button { flex: 1; min-height: 30px; padding: 4px 10px; border: 0; border-radius: 2px;
  background: transparent; color: ${BRAND}; font-size: 12px; letter-spacing: 0.04em; }
.lang button[aria-pressed="true"] { background: ${BRAND}; color: #fff; cursor: default; }
.lang button.pending { opacity: 0.55; outline: 1px dashed ${BRAND}; outline-offset: -3px; }
.lang button:focus-visible { outline: 2px solid ${RING}; outline-offset: 2px; }
.error { color: #8a2a0a; background: #fff; border-radius: 2px; padding: 8px 10px; font-size: 12px; line-height: 1.4;
  max-width: ${CARD + 20}px; margin: 0; box-shadow: 0 6px 18px rgba(0,0,0,0.1); }
.error-text { margin: 0; }
.settings { margin-top: 8px; display: block; height: 32px; padding: 0 12px; border-radius: 2px; }
.grant { width: ${CARD + 20}px; background: #fff; border: 1px solid ${LINE}; border-radius: 2px;
  padding: 8px 10px 4px; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.14); }
.grant-note { margin: 0 0 6px; font-size: 12px; line-height: 1.4; color: ${MUTED}; }
.grant iframe { display: block; width: 100%; height: 84px; border: 0; background: #fff; }

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
  .root.glide, .card, .frame, .face, .face > * { transition: none; }
  .root[data-min][data-activity="speaking"] .card { animation: none; }
}
[hidden] { display: none !important; }
`;

/** The widget's own words. They stay English in a Spanish call, as they
 *  always have; only Javier switches. */
const WORDS: WidgetWords = {
  invite: "Talk to Javier",
  role: "Explora guide · voice",
  inviteLabel: "Talk to Javier, Explora's guide, by voice",
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
    "Chrome blocks the microphone for the “Javier for Explora” extension. In the microphone settings, " +
    "take it off “Not allowed to use your microphone”, then call again.",
  settings: "Open the settings",
  activity: { listening: "Listening", thinking: "Thinking", speaking: "Speaking" },
};

export const EXPLORA = defineSite({
  id: "explora",
  matches: ["https://www.explora.com/*", "https://explora.com/*", "https://reservations.explora.com/*"],
  isSite: (url) => /^https:\/\/(www\.|reservations\.)?explora\.com(\/|$)/i.test(url),
  home: `${SITE}/`,
  opening: "en",
  widget: {
    name: "Javier",
    languages: [
      { code: "en", label: "English" },
      { code: "es", label: "Español" },
    ],
    words: { en: WORDS, es: WORDS },
    styles: STYLES,
    transitionName: "voqalize-javier",
  },
});
