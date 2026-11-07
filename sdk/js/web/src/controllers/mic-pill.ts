/**
 * Which mic pill shows, from the mic's state: the browser's own judgement of
 * the mic, put into words a visitor can act on.
 *
 * - `permission` — "Grant mic permission": the browser is asking, or the
 *   visitor or the browser refused. Its action shows the coach mark, which
 *   says where this browser keeps the prompt or the setting.
 * - `muted` — "You are muted": the visitor muted. Its action unmutes.
 * - `check` — "Is your mic working?": a live, unmuted mic that has heard
 *   nothing while the agent waits (the silence hint); a track the system
 *   muted or another app took (`trackMuted`); a track that ended or a device
 *   that left; or no mic at all. Its action opens the device menu, or where
 *   there is none (a phone), the coach mark with this platform's advice.
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
  if (!snap) return null;
  const { device } = snap;
  if (device === "blocked" || (snap.permission === "denied" && device !== "idle")) return "permission";
  if (device === "asking") return (options.askingSettled ?? true) && snap.permission !== "granted" ? "permission" : null;
  if (snap.muted && device !== "idle") return "muted";
  if (device === "missing") return "check";
  if (device === "live" && (snap.trackMuted || snap.hint)) return "check";
  return null;
}
