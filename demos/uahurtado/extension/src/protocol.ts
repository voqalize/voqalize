/**
 * What the pages and the holder say to each other.
 *
 * The call lives in the holder, an offscreen document of the extension
 * (`holder.ts`), so it outlives every page load on the university's sites,
 * including the loads from one host to another (admision., postgrados. and
 * www.uahurtado.cl). Each UAH page keeps one port to it (`bridge.ts` in the
 * page's isolated world, `hub.ts` in its own world) and follows the call: the
 * widget, his face, the site adapter. The extension's service worker
 * (`background.ts`) makes the holder, opens and focuses tabs, keeps the move a
 * page leaves for the next page of its tab, reads the site's REST records and
 * keeps the visitor's language.
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
  // The audiomalla plays (`on`) or stopped: the microphone is held muted
  // meanwhile, whatever the visitor's mute.
  | { k: "hold_mic"; on: boolean }
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
  | { op: "set_lang"; lang: Language }
  // What a page keeps for the next page of its tab, on any host
  // (`sessionStorage` does not cross hosts): taken once, within a minute.
  | { op: "stash"; key: string; value: unknown }
  | { op: "take"; key: string }
  // The site's own record of a career or a programme, read across hosts.
  | { op: "rest"; kind: "carrera" | "programa"; slug: string };

/** Holder → page, on the port. */
export type ToPage =
  | ({ k: "state" } & CallState)
  | { k: "ev"; name: string; data: unknown }
  | { k: "sync"; msg: unknown }
  | { k: "ssrc"; timestamp: number; rtpTimestamp: number }
  | { k: "playout"; delay: number; samples: number }
  | { k: "perform"; id: number; command: string; payload: unknown };

/** The Actions the holder performs itself rather than a page. Every other
 *  Action moves a page of the site, on the UAH tab in front, else the one
 *  last in front, else a new one. */
export const OURS = new Set(["focus_tab", "cue", "language_changed", "open_link"]);
/** Page events the brain takes from any tab, not only the one in front: a
 *  move's outcome, a read's answer, the toggle, the form, the audiomalla. */
export const ANY_TAB = new Set([
  "command_failed", "command_done", "language_requested", "admission_read", "program_read",
  "lead_form_state", "lead_submitted", "audiomalla_ended",
]);

/** A page of the three sites: admision., postgrados., www. or bare uahurtado.cl. */
export const isSite = (url: string) => /^https:\/\/((admision|postgrados|www)\.)?uahurtado\.cl(\/|$)/i.test(url);

/** Where a tab opened for a move with no UAH tab open starts. */
export const SITE = "https://admision.uahurtado.cl/";

/** The port's name. */
export const PORT = "voqalize";
