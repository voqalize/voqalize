/**
 * Which mic pill shows, from the media manager's `micHint` and the visitor's
 * mute, put into words a visitor can act on.
 *
 * - `permission` — "Grant mic permission": the hint is `grant` (the browser
 *   is asking) or `blocked` (the visitor or the browser refused). Its action
 *   asks again and shows the coach mark, which says where this browser keeps
 *   the prompt or the setting.
 * - `muted` — "You are muted": the visitor muted. Its action unmutes.
 * - `check` — "Is your mic working?": the hint is `missing` (no mic, one
 *   another app holds, one that went away or that the system silenced), or
 *   the silence hint shows. Its action opens the device menu, or where there
 *   is none (a phone), the coach mark with this platform's advice.
 *
 * First match wins, in that order: a refused mic cannot be fixed by
 * unmuting, and a muted one is not broken.
 *
 * No dependencies, so the widget can decide without loading the pill.
 */

import type { MicSnapshot } from "./mic.js";

export type MicPillKind = "permission" | "muted" | "check";

export interface MicPillOptions {
  /**
   * Whether a prompt that is still open counts yet. The widget waits a
   * moment before calling an open prompt a problem, so a browser that
   * answers at once from a remembered grant never flashes the pill.
   */
  askingSettled?: boolean;
}

/** The pill for a mic snapshot, or `null` when the mic needs nothing from the visitor. */
export function micPillOf(snap: MicSnapshot | undefined, options: MicPillOptions = {}): MicPillKind | null {
  if (!snap || snap.state === "idle") return null;
  if (snap.micHint === "blocked") return "permission";
  if (snap.micHint === "grant") return (options.askingSettled ?? true) ? "permission" : null;
  if (snap.muted || snap.state === "muted") return "muted";
  if (snap.micHint === "missing") return "check";
  if (snap.hint) return "check";
  return null;
}
