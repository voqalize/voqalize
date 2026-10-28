/**
 * What the pages, the holder and the service worker say to each other.
 *
 * The call lives in the holder, an offscreen document of the extension, so it
 * outlives every page load on every host the site has. Each page keeps one
 * port to it (the bridge in the page's isolated world, the hub in its own
 * world) and follows the call: the widget, the character's face, the site's
 * moves. The service worker makes the holder, opens and focuses tabs, keeps
 * each tab's move for its next page and the visitor's language choice.
 */

import type { Carried } from "../moves";
import type { StageResult } from "../wire.gen";
import type { Activity, Language, Status } from "./widget";

/** The port's name. */
export const PORT = "voqalize";

/** The pipecat events relayed to the pages: the avatar's (less
 *  `trackStarted`) and the widget's. */
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
  /** The agent hears the pages: they report what they show from now on. */
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

/** One thing a page is asked to do: a Stage move (with the call it answers),
 *  the rest of a move the last page of the tab carried here, or one of the
 *  site's own Actions. */
export type Job =
  | { kind: "stage"; move: string; args: unknown; call_ref: string }
  | Carried
  | { kind: "site"; command: string; payload: unknown };

/** Page → holder, on the port. */
export type FromPage =
  // The page is up: where it is. The holder answers with the state and any
  // jobs it kept for this tab while it was loading.
  | ({ k: "hello" } & Where)
  | ({ k: "where" } & Where)
  // A load of another document started: jobs wait for the next page's hello.
  | { k: "leaving" }
  // One of the site's own events, for the agent.
  | { k: "app"; event: string; payload: unknown }
  // The avatar's report, for the agent (the front tab's only).
  | { k: "report"; data: unknown }
  // A job's end. `result` for a Stage move; `deferred` when the move goes on
  // on the next page, which sends its result (`result` below).
  | { k: "done"; id: number; result: StageResult | null; deferred?: boolean }
  // A Stage result sent outside a job: a move finished on the page after a
  // load, or one that said it would load and did not.
  | { k: "result"; result: StageResult }
  // A move kept for this tab's next page (`loadThen`, `keep`): its final
  // result is owed from there once this page goes. `uncarried`: it ended
  // here after all.
  | { k: "carried"; call_ref: string; move: string }
  | { k: "uncarried"; call_ref: string }
  | { k: "mute" }
  | { k: "end" }
  | { k: "lang"; language: Language }
  // A face was just made on this page: the reply so far, please.
  | { k: "catchup" };

/** Requests a page makes of the holder, answered with `re`. */
export type HolderAsk = { op: "mic" } | { op: "call"; session: unknown; language: Language };

/** Requests a page makes of the service worker. A site may add its own ops
 *  (`startBackground`'s `ops`). */
export type WorkerAsk =
  | { op: "ensure" }
  | { op: "has_holder" }
  | { op: "grant_tab"; lang: Language }
  | { op: "grant_url" }
  | { op: "open_settings" }
  // A job for this tab's own next page, which may be on another host: kept
  // by the worker, per browser tab, until that page asks for it.
  | { op: "pend"; then: Job }
  | { op: "pending" }
  | { op: "unpend"; call_ref: string }
  // The visitor's language choice, for every host of the site.
  | { op: "get_lang" }
  | { op: "set_lang"; lang: Language }
  | { op: string; [key: string]: unknown };

/** Holder → page, on the port. */
export type ToPage =
  | ({ k: "state" } & CallState)
  | { k: "ev"; name: string; data: unknown }
  | { k: "sync"; msg: unknown }
  | { k: "ssrc"; timestamp: number; rtpTimestamp: number }
  | { k: "playout"; delay: number; samples: number }
  | { k: "perform"; id: number; job: Job }
  // A new face's catch-up on the reply in progress.
  | { k: "catchup"; msgs: ToPage[] };
