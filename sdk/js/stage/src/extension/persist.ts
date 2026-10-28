/**
 * What a page in a call leaves for the next page in the same tab, so the
 * widget is back the moment the next page shows (the shell), and the page
 * load itself is a view transition under a widget that stays put.
 *
 * Kept in the tab's `sessionStorage` (the origin's, which the page's world
 * and the extension's isolated world share, and which the next page reads
 * synchronously at `document_start`): the call's state as the widget shows
 * it, where the visitor put the widget, and the character's still for the
 * invite. It is only a picture of the call: the holder's state, which the
 * next page asks for on its port, is what holds.
 *
 * Both are same-origin: a load that crosses to another origin of the site
 * finds nothing kept, so the widget comes back at `document_idle` and the page
 * loads without a transition. The call itself is in the holder and does not
 * notice.
 */

import type { Activity, Language, Layout, Status } from "./widget.js";

/** The call as the last page showed it. */
export interface Kept extends Layout {
  /** When it was written: a page that leaves writes it again. */
  at: number;
  status: Status;
  muted: boolean;
  activity: Activity | null;
  language: Language;
  /** The character's still, a URL: the invite's picture off a call. */
  still: string | null;
}

/** Kept longer ago than this (a tab restored long after, say), it is stale. */
export const FRESH_MS = 60_000;

const STYLE_ID = "voqalize-transitions";

export const keptKey = (site: string) => `voqalize.${site}.call`;

/** The kept call, if a call was on when the last page of this tab left it. */
export function readKept(site: string, now = Date.now()): Kept | null {
  try {
    const kept = JSON.parse(sessionStorage.getItem(keptKey(site)) ?? "null") as Kept | null;
    if (!kept || (kept.status !== "live" && kept.status !== "connecting")) return null;
    return now - kept.at < FRESH_MS ? kept : null;
  } catch {
    return null;
  }
}

export function writeKept(site: string, kept: Omit<Kept, "at">): void {
  try {
    sessionStorage.setItem(keptKey(site), JSON.stringify({ ...kept, at: Date.now() }));
  } catch {
    /* Storage blocked or full: the next page mounts as it loads. */
  }
}

export function clearKept(site: string): void {
  try {
    sessionStorage.removeItem(keptKey(site));
  } catch {
    /* Nothing to clear. */
  }
}

/** Same-origin page loads as a view transition, or not. The page fades under
 *  the widget for 150 ms; the widget, named, stays where it is. */
export function transitions(on: boolean, name: string): void {
  const there = document.getElementById(STYLE_ID);
  if (!on) return there?.remove();
  if (there) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent =
    "@view-transition{navigation:auto}" +
    "::view-transition-old(root),::view-transition-new(root){animation-duration:150ms}" +
    `::view-transition-group(${name}),::view-transition-old(${name}),` +
    `::view-transition-new(${name}){animation-duration:150ms}`;
  (document.head ?? document.documentElement).appendChild(style);
}
