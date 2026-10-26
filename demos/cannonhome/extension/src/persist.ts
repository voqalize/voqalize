/**
 * What a page in a call leaves for the next page in the same tab, so the
 * widget is back the moment the next page shows (`shell.ts`), and the page
 * load itself is a view transition under a widget that stays put.
 *
 * Kept in the tab's `sessionStorage` (cannonhome.cl's, which the page's world
 * and the extension's isolated world share, and which the next page of the
 * tab reads synchronously at `document_start`): the call's state as the widget
 * shows it, where the visitor put the widget, and a still of his face (the
 * last frame the avatar drew, `FACE_KEY`, else the character's still). Written
 * by `content.ts` while a call is on, and taken away when it ends. It is only a
 * picture of the call: the holder's state, which the next page asks for on its
 * port as before, is what holds.
 *
 * The cross-document view transition (Chrome 126+; older Chrome ignores the
 * rule and loads the page as before) needs both pages to opt in: the page
 * that is leaving (`content.ts`, while a call is on) and the page that arrives
 * (`shell.ts`, from what was kept here).
 */

import { type Activity, type Language, type Layout, type Status, TRANSITION_NAME } from "./widget";

/** The call as the last page showed it. */
export interface Kept extends Layout {
  /** When it was written: a page that leaves writes it again. */
  at: number;
  status: Status;
  muted: boolean;
  activity: Activity | null;
  language: Language;
  /** The character's still, a URL. */
  still: string | null;
  /** His mouth strip (`mouth.ts`), once it has loaded on a page of this
   *  tab: in the cache, so the next page's still is the strip at once. */
  strip?: string | null;
}

const KEPT_KEY = "voqalize.cannonhome.call";
/** The last frame of his face, a data URL, apart: it is the large one. */
const FACE_KEY = "voqalize.cannonhome.face";
/** Kept longer ago than this (a tab restored long after, say), it is stale. */
export const FRESH_MS = 60_000;

const STYLE_ID = "voqalize-transitions";

/** The kept call, if a call was on when the last page of this tab left it. */
export function readKept(now = Date.now()): Kept | null {
  try {
    const kept = JSON.parse(sessionStorage.getItem(KEPT_KEY) ?? "null") as Kept | null;
    if (!kept || (kept.status !== "live" && kept.status !== "connecting")) return null;
    return now - kept.at < FRESH_MS ? kept : null;
  } catch {
    return null;
  }
}

export function writeKept(kept: Omit<Kept, "at">): void {
  try {
    sessionStorage.setItem(KEPT_KEY, JSON.stringify({ ...kept, at: Date.now() }));
  } catch {
    /* Storage blocked or full: the next page mounts as it loads. */
  }
}

export function clearKept(): void {
  try {
    sessionStorage.removeItem(KEPT_KEY);
    sessionStorage.removeItem(FACE_KEY);
  } catch {
    /* Nothing to clear. */
  }
}

export function readFace(): string | null {
  try {
    return sessionStorage.getItem(FACE_KEY);
  } catch {
    return null;
  }
}

export function writeFace(url: string): void {
  try {
    sessionStorage.setItem(FACE_KEY, url);
  } catch {
    /* Full: the character's still stands in. */
  }
}

/** Same-origin page loads as a view transition, or not. The page fades under
 *  the widget for 150 ms; the widget, named, stays where it is. */
export function transitions(on: boolean): void {
  const there = document.getElementById(STYLE_ID);
  if (!on) return there?.remove();
  if (there) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent =
    "@view-transition{navigation:auto}" +
    "::view-transition-old(root),::view-transition-new(root){animation-duration:150ms}" +
    `::view-transition-group(${TRANSITION_NAME}),::view-transition-old(${TRANSITION_NAME}),` +
    `::view-transition-new(${TRANSITION_NAME}){animation-duration:150ms}`;
  (document.head ?? document.documentElement).appendChild(style);
}
