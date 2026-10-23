/**
 * What the pages and the holder say to each other.
 *
 * The call lives in the holder, an offscreen document of the extension
 * (`holder.ts`), so it outlives every page load on both of Explora's hosts,
 * www.explora.com and reservations.explora.com, and every load from one to the
 * other. Each Explora page keeps one port to it (`bridge.ts` in the page's
 * isolated world, `hub.ts` in its own world) and follows the call: the widget,
 * his face, the site adapter. The extension's service worker (`background.ts`)
 * makes the holder, opens and focuses tabs, keeps each tab's move for its next
 * page (`pend`/`pending`) and reads www.explora.com's translations for the
 * booking site (`alternate`).
 */

import type { CheckAvailability, FillEnquiry } from "./actions.gen";
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
  | { k: "lang"; language: Language };

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
  // A move for this tab's own next page, which may be on the other host:
  // kept by the worker, per browser tab, until that page asks for it.
  | { op: "pend"; then: unknown }
  | { op: "pending" }
  // The `lang` translation of a www.explora.com page, for a page on the
  // booking site, which may not fetch www.explora.com across origins.
  | { op: "alternate"; url: string; lang: string };

/** Holder → page, on the port. */
export type ToPage =
  | ({ k: "state" } & CallState)
  | { k: "ev"; name: string; data: unknown }
  | { k: "sync"; msg: unknown }
  | { k: "ssrc"; timestamp: number; rtpTimestamp: number }
  | { k: "playout"; delay: number; samples: number }
  | { k: "perform"; id: number; command: string; payload: unknown };

/** The Actions that move a page, performed on an Explora tab: the one in
 *  front, else the one last in front, else a new one. The page decides
 *  whether a move needs the other host, and loads it (`content.ts`). */
export const SITE_COMMANDS = new Set([
  "navigate", "show_section", "open_faq", "check_availability", "choose_room", "fill_enquiry", "send_enquiry",
  // The extension's own, not the brain's: the call's language moved.
  "site_language",
]);
/** The Actions that are made on the booking site: from www.explora.com they
 *  load it first. */
export const BOOKING_COMMANDS = new Set(["check_availability", "choose_room", "fill_enquiry", "send_enquiry"]);
/** The Actions the holder performs itself rather than a page. */
export const OURS = new Set(["cue", "focus_tab", "language_changed"]);
/** Page events the brain takes from any tab, not only the one in front: a
 *  move's failure, the toggle, and an enquiry the visitor sent, which answer
 *  the brain whichever tab made them. */
export const ANY_TAB = new Set(["command_failed", "language_requested", "enquiry_sent"]);

/** www.explora.com, explora.com or reservations.explora.com. */
export const isSite = (url: string) => /^https:\/\/(www\.|reservations\.)?explora\.com(\/|$)/i.test(url);
/** The booking site. */
export const onBooking = (url: string) => /^https:\/\/reservations\.explora\.com(\/|$)/i.test(url);

export const SITE = "https://www.explora.com";
export const BOOKING = "https://reservations.explora.com";

/** The page of the booking site a booking step starts on, so the step lands
 *  where the booking adapter would load it itself: one load, not two. */
export function bookingUrl(command: string, payload: unknown, language: Language): string | null {
  const lang = language === "es" ? "ES" : "EN";
  if (command === "check_availability") {
    const p = payload as CheckAvailability;
    const q = new URLSearchParams({ hotel_code: p.hotel_code });
    if (p.date) q.set("check_in_date", p.date);
    q.set("language", lang);
    return `${BOOKING}/ibe/paso1?${q}`;
  }
  if (command === "fill_enquiry") {
    const p = payload as FillEnquiry;
    return `${BOOKING}/ibe/expeditions?expedition_request=${encodeURIComponent(p.expedition_code.toUpperCase())}&language=${lang}`;
  }
  return null;
}

/** The port's name. */
export const PORT = "voqalize";
