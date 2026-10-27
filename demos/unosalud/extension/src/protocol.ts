/**
 * What the pages and the holder say to each other.
 *
 * The call lives in the holder, an offscreen document of the extension
 * (`holder.ts`), so it outlives every page load on www.unosalud.cl, the
 * booking's included. Each Uno Salud page keeps one port to it (`bridge.ts` in the page's isolated world,
 * `hub.ts` in its own world) and follows the call: the widget, his face, the
 * site adapter. The extension's service worker (`background.ts`) makes the
 * holder, opens and focuses tabs, and keeps the visitor's language.
 */

import type { Activity, Language, Status } from "./widget";

/** The pipecat events relayed to the pages: the avatar's (`RTVI_EVENTS` in
 *  the avatar's `AvatarClient.ts`, less `trackStarted`) and the widget's. */
export const EVENTS = [
  "serverMessage", "connected", "disconnected", "botReady", "error",
  "userStartedSpeaking", "userStoppedSpeaking", "botStartedSpeaking", "botStoppedSpeaking",
  "userMuteStarted", "userMuteStopped", "botLlmStarted",
] as const;

/** The call's state, as every page shows it. */
export interface CallState {
  status: Status;
  muted: boolean;
  activity: Activity | null;
  language: Language;
  /** The brain hears the pages: they report what they show from now on. */
  ready: boolean;
  /** Why the call ended, when it ended in an error. */
  message?: string;
}

/** The microphone permission of the extension, as the holder reads it. */
export type MicState = "granted" | "prompt" | "denied";

/** A page's report of where it is. */
export interface Where {
  url: string;
  title: string;
  /** Visible and focused: the tab the visitor is looking at. */
  front: boolean;
}

/** Page → holder, on the port. */
export type FromPage =
  // The page is up: where it is. The holder answers with the state and any
  // moves it kept for this tab while it was loading.
  | ({ k: "hello" } & Where)
  | ({ k: "where" } & Where)
  // The page is going (a load of another document started): moves wait for
  // the next page's hello.
  | { k: "leaving" }
  | { k: "app"; event: string; payload: unknown }
  | { k: "report"; data: unknown }
  | { k: "done"; id: number; outcome: { event: string; payload: Record<string, unknown> } | null }
  | { k: "mute" }
  | { k: "end" }
  | { k: "lang"; language: Language }
  // A face was just made on this page: the reply so far, please.
  | { k: "catchup" };

/** Requests a page makes of the holder, answered with `re`. */
export type HolderAsk =
  | { op: "mic" }
  | { op: "call"; session: unknown; language: Language };

/** Requests a page makes of the service worker. */
export type WorkerAsk =
  | { op: "ensure" }
  | { op: "has_holder" }
  | { op: "grant_tab"; lang: Language }
  | { op: "grant_url" }
  | { op: "open_settings" }
  | { op: "get_lang" }
  | { op: "set_lang"; lang: Language };

/** Holder → page, on the port. */
export type ToPage =
  | ({ k: "state" } & CallState)
  | { k: "ev"; name: string; data: unknown }
  | { k: "sync"; msg: unknown }
  | { k: "ssrc"; timestamp: number; rtpTimestamp: number }
  | { k: "playout"; delay: number; samples: number }
  | { k: "perform"; id: number; command: string; payload: unknown }
  // A new face's catch-up on the reply in progress (`catch-up.ts`).
  | { k: "catchup"; msgs: ToPage[] };

/** The Actions that belong on a tab of the site (any page but the booking):
 *  a page of the site, and the two lead forms, which are pages of it too.
 *  Performed on a site tab: the one in front, else the one last in front,
 *  else a new one. */
export const SITE_COMMANDS = new Set(["navigate", "fill_callback_form", "fill_company_form"]);
/** The Actions that belong on the booking's tab, /agenda-tu-hora/ (the same
 *  origin, but a tab of its own, as the brain expects). */
export const BOOKING_COMMANDS = new Set(["open_booking", "fill_booking_patient", "booking_pick", "booking_scan"]);
/** The Actions the holder performs itself rather than a page. */
export const OURS = new Set(["focus_tab", "cue", "language_changed", "open_link"]);
/** Page events the brain takes from any tab, not only the one in front: a
 *  move's outcome, the toggle, and the state of a form Javier filled, which
 *  is the booking's even while the visitor looks at another tab. */
export const ANY_TAB = new Set([
  "command_failed", "command_done", "language_requested", "booking_state", "callback_form_state", "company_form_state",
]);

const ORIGIN = /^https:\/\/(www\.)?unosalud\.cl(\/|$)/i;
const BOOKING_PATH = /^\/agenda-tu-hora(\/|$)/i;
const pathOf = (url: string) => {
  try {
    return new URL(url).pathname;
  } catch {
    return "";
  }
};

/** The booking, /agenda-tu-hora/ on www.unosalud.cl. */
export const isBooking = (url: string) => ORIGIN.test(url) && BOOKING_PATH.test(pathOf(url));
/** www.unosalud.cl (or the bare unosalud.cl), any page but the booking. */
export const isSite = (url: string) => ORIGIN.test(url) && !BOOKING_PATH.test(pathOf(url));

export const SITE = "https://www.unosalud.cl";
export const BOOKING = "https://www.unosalud.cl/agenda-tu-hora/";

/** The port's name. */
export const PORT = "voqalize";
