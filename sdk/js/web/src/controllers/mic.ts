/**
 * The microphone, as the widget shows it.
 *
 * The media manager in `@voqalize/client-transport` owns everything the
 * browser can say about the mic: whether it is asked for, live, refused,
 * gone or silenced (`micState`), and what the visitor should be told about
 * it (`micHint`), read from the permission, the track and the levels. This
 * store only mirrors the two, adds the visitor's own mute and the level for
 * the meter, and remembers whether the mic was live at any point in the
 * call. Nothing here is sent to the agent.
 */

import type { MicHint, MicState } from "@voqalize/client-transport";
import { Store } from "./store.js";

export type { MicHint, MicState };

export interface MicSnapshot {
  /** The manager's `micState`. */
  state: MicState;
  /** The manager's `micHint`. */
  micHint: MicHint;
  /** Whether the visitor muted. */
  muted: boolean;
  /** Whether the silence hint is showing: `micHint` is `silent` and the configuration allows it. */
  hint: boolean;
  /** The latest local level, 0–1. Zero when not live. */
  level: number;
  /** Whether the mic has been live at any point in this call. */
  everLive: boolean;
}

export interface MicControllerOptions {
  /** `mic.silenceHint` from the configuration. Default true. */
  silenceHint?: boolean;
}

const INITIAL: MicSnapshot = {
  state: "idle",
  micHint: "none",
  muted: false,
  hint: false,
  level: 0,
  everLive: false,
};

/** The hints that mean the mic is not reaching the call. */
export function micIsOff(hint: MicHint): boolean {
  return hint === "grant" || hint === "blocked" || hint === "missing";
}

export class MicController extends Store<MicSnapshot> {
  private readonly hintEnabled: boolean;

  constructor(options: MicControllerOptions = {}) {
    super(INITIAL);
    this.hintEnabled = options.silenceHint ?? true;
  }

  /** The manager's `micState` changed. */
  setState(state: MicState): void {
    const snap = this.getSnapshot();
    this.set({
      state,
      everLive: snap.everLive || state === "live",
      level: state === "live" ? snap.level : 0,
    });
  }

  /** The manager's `micHint` changed. */
  setHint(micHint: MicHint): void {
    this.set({ micHint, hint: this.hintEnabled && micHint === "silent" });
  }

  setMuted(muted: boolean): void {
    this.set({ muted });
  }

  /** A local level sample, 0–1. */
  level(value: number): void {
    const level = Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 0;
    this.set({ level });
  }

  /** A new call: back to before it, keeping what the manager says now. */
  reset(state: MicState, micHint: MicHint): void {
    this.set({ ...INITIAL, state, everLive: state === "live" });
    this.setHint(micHint);
  }
}
