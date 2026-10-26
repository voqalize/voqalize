/**
 * What the pages and the holder say to each other.
 *
 * The call lives in the holder, an offscreen document of the extension
 * (`holder.ts`), so it outlives every page load on cannonhome.cl. Each Cannon
 * Home page keeps one port to it (`bridge.ts` in the page's isolated world,
 * `hub.ts` in its own world) and follows the call: the widget, his face, the
 * site adapter. The extension's service worker (`background.ts`) makes the
 * holder, opens and focuses tabs, and keeps the visitor's language.
 */

import type { Shape } from "./level";
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
  | { k: "catchup"; msgs: ToPage[] }
  // How loud his voice is now, as a mouth shape for the still a page shows
  // until its face draws (`level.ts`): on a change, and every 200 ms while open.
  | { k: "level"; m: Shape };

/** The Actions that move a page of the shop, performed on a shop tab: the
 *  one in front, else the one last in front, else a new one. */
export const SITE_COMMANDS = new Set([
  "search_products", "filter_listing", "open_product", "check_prices", "add_to_cart", "show_cart",
  "update_cart_item", "start_checkout", "fill_checkout", "navigate", "show_section", "open_faq",
]);
/** The Actions the holder performs itself rather than a page. */
export const OURS = new Set(["focus_tab", "cue", "language_changed"]);
/** Page events the brain takes from any tab, not only the one in front: a
 *  move's outcome, the toggle, and what a move read (prices, the bag), which
 *  answer the brain whichever tab made them. */
export const ANY_TAB = new Set(["command_failed", "command_done", "language_requested", "prices_read", "cart_state"]);

/** cannonhome.cl, with or without `www.`. */
export const isSite = (url: string) => /^https:\/\/(www\.)?cannonhome\.cl(\/|$)/i.test(url);

export const SITE = "https://cannonhome.cl";

/** The port's name. */
export const PORT = "voqalize";
