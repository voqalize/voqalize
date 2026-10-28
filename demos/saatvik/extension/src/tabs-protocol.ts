/**
 * What the Saatvik page and the document tab ask of the service worker.
 *
 * The page script runs in the page's own world (Saatvik's router lives there)
 * and has no `chrome.runtime`, so it asks through `bridge.ts`, an isolated
 * content script that posts the question on and the answer back.
 */

import type { OpenRequest } from "./pdf-viewer";

export type WorkerAsk =
  /** Open a document in the tab beside this one: the one this tab opened
   *  before, else a new one. */
  | { t: "open_doc"; req: OpenRequest }
  /** Close this tab's document tab, and come back here. */
  | { t: "close_doc" }
  /** Bring this tab to the front. */
  | { t: "focus_me" }
  /** From the document tab: bring back the Saatvik tab that opened it. */
  | { t: "back" };

export interface WorkerAnswer {
  ok: boolean;
  error?: string;
}

/** The window-message envelope between the page and the bridge. */
export const BRIDGE = "voqalize-saatvik-bridge";
