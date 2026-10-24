/**
 * What the pages and the holder say to each other.
 *
 * The call lives in the holder, an offscreen document of the extension
 * (`holder.ts`), so it outlives every page load on figurella.cl. Each Figurella
 * page keeps one port to it (`bridge.ts` in the page's isolated world, `hub.ts`
 * in its own world) and follows the call: the widget, his face, the site
 * adapter. The extension's service worker (`background.ts`) makes the holder,
 * opens and focuses tabs and keeps the visitor's language.
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
  | { op: "get_lang" }
  | { op: "set_lang"; lang: Language };

/** Holder → page, on the port. */
export type ToPage =
  | ({ k: "state" } & CallState)
  | { k: "ev"; name: string; data: unknown }
  | { k: "sync"; msg: unknown }
  | { k: "ssrc"; timestamp: number; rtpTimestamp: number }
  | { k: "playout"; delay: number; samples: number }
  | { k: "perform"; id: number; command: string; payload: unknown };

/** The Actions that may open a page of the site, on a site tab: a page, and
 *  the forms, which open the page that has them when the one in front does
 *  not. The one in front, else the one last in front, else a new one. */
export const SITE_COMMANDS = new Set(["navigate", "fill_booking_form", "fill_franchise_form"]);
/** The Actions the holder performs itself rather than a page. */
export const OURS = new Set(["open_link", "focus_tab", "cue", "language_changed"]);
/** Page events the brain takes from any tab, not only the one in front: a
 *  move's answer belongs to the move, wherever the visitor looks now. */
export const ANY_TAB = new Set(["command_failed", "command_done", "language_requested", "form_state", "form_result"]);

/** figurella.cl, with or without `www.`. */
export const isSite = (url: string) => /^https:\/\/(www\.)?figurella\.cl(\/|$)/i.test(url);

export const SITE = "https://figurella.cl";

/** The port's name. */
export const PORT = "voqalize";
