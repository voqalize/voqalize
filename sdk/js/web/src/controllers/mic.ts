/**
 * The microphone's state, as the widget shows it and as gato hears it.
 *
 * The device side is a small machine:
 *
 *   idle ──ask──▶ asking ──track──▶ live
 *                   │                 │
 *                   └──error──▶ blocked | missing ◀── error
 *
 * and `muted` is a flag on top of it: the state is "muted" while the visitor
 * has muted a live mic, and the device state otherwise. A mic that is muted
 * before it ever went live reads as whatever the device is doing, because
 * what gato needs to know is whether it can hear the visitor, and it cannot.
 *
 * "idle" is before the widget has asked for anything. It is never sent: the
 * first `mic_state` goes out after connect, by which time the widget has
 * asked.
 *
 * The silence hint is the layer under "live": the track is live, nothing is
 * muted, the agent is waiting for the visitor, and the level has stayed under
 * a floor for a while. It is a hint and never an action — a quiet visitor is
 * not a broken mic.
 *
 * The track itself can stop carrying sound without the visitor choosing it:
 *
 * - its `mute` event: the system muted the input, or another app took it.
 *   The track comes back with `unmute`. While it lasts the state is
 *   "missing" over a device that is still "live" (`trackMuted`).
 * - its `ended` event, or the device leaving the list on `devicechange`: the
 *   track is gone for good. The device is "missing" (`failed("track-ended")`
 *   or `failed("device-gone")`) until a new track starts.
 *
 * Both go to gato as "missing", a state every gato build knows: the visitor
 * cannot be heard, for a reason that is not their choice, and the device
 * menu offers another mic. No new wire value is needed for them, and a gato
 * that predates them reads them as it always has.
 *
 * A refusal outranks everything else: while the browser reports the
 * permission as "denied", any failure reads as "blocked", because the menu
 * cannot fix it and the coach can.
 */

import { Store } from "./store.js";

/** What the device is doing. */
export type MicDeviceState = "idle" | "asking" | "live" | "blocked" | "missing";

/** The state the widget shows and gato is sent. */
export type MicState = MicDeviceState | "muted";

/** The states that go on the wire in `mic_state`. */
export type WireMicState = Exclude<MicState, "idle">;

/**
 * Below this local level (the transport's 0–1 peak amplitude) a sample counts
 * as silence.
 *
 * TO BE TUNED FROM REAL CALLS. A placeholder: the design says the floor is
 * measured on real calls before the hint ships, and this one was not.
 */
export const SILENCE_HINT_FLOOR = 0.003;

/**
 * How long, in ms of the agent waiting, the level must stay under the floor
 * before the hint shows. Time the agent spends speaking or thinking does not
 * count, and neither does time muted.
 *
 * TO BE TUNED FROM REAL CALLS. A placeholder, like the floor.
 */
export const SILENCE_HINT_AFTER_MS = 8000;

/**
 * The longest gap between two level samples that counts as continuous
 * listening. The transport reports the level every 100 ms while the mic is
 * live and enabled; a longer gap means the meter stopped (a mute, a device
 * change, a background tab), and that time is not evidence of silence. Five
 * times the meter's interval, so a late timer or two does not break the run.
 *
 * TO BE TUNED FROM REAL CALLS, with the floor and the wait.
 */
export const SILENCE_HINT_MAX_GAP_MS = 500;

/**
 * The pipecat `DeviceError` types, and which state each one means.
 *
 * `permissions` is the visitor or the browser saying no, and
 * `undefined-mediadevices` a page without a secure context, which no device
 * will fix: both are "blocked". The rest are about the hardware — none found,
 * one held by another app, constraints nothing satisfies, or something
 * unrecognised — and read as "missing", where the device menu offers another.
 */
export function micStateForError(type: string | undefined): "blocked" | "missing" {
  return type === "permissions" || type === "undefined-mediadevices" ? "blocked" : "missing";
}

export interface MicSnapshot {
  state: MicState;
  device: MicDeviceState;
  muted: boolean;
  /** Whether the silence hint is showing. */
  hint: boolean;
  /** The latest local level, 0–1. Zero when not live. */
  level: number;
  /** Whether the mic has been live at any point in this call. */
  everLive: boolean;
  /** The `DeviceError` type behind "blocked" or "missing". */
  errorType?: string;
  /** The browser's microphone permission, where it says. */
  permission: "granted" | "denied" | "prompt" | "unknown";
  /**
   * The live track's `muted`: the system or another app silenced it. Not the
   * visitor's mute, which is `muted`.
   */
  trackMuted: boolean;
}

export interface MicControllerOptions {
  /** `mic.silenceHint` from the configuration. Default true. */
  silenceHint?: boolean;
  floor?: number;
  afterMs?: number;
  maxGapMs?: number;
  /** A clock, for tests. */
  now?: () => number;
}

const INITIAL: MicSnapshot = {
  state: "idle",
  device: "idle",
  muted: false,
  hint: false,
  level: 0,
  everLive: false,
  permission: "unknown",
  trackMuted: false,
};

export class MicController extends Store<MicSnapshot> {
  private readonly hintEnabled: boolean;
  private readonly floor: number;
  private readonly afterMs: number;
  private readonly maxGapMs: number;
  private readonly now: () => number;
  private agentListening = false;
  private quietMs = 0;
  private lastSampleAt: number | null = null;

  constructor(options: MicControllerOptions = {}) {
    super(INITIAL);
    this.hintEnabled = options.silenceHint ?? true;
    this.floor = options.floor ?? SILENCE_HINT_FLOOR;
    this.afterMs = options.afterMs ?? SILENCE_HINT_AFTER_MS;
    this.maxGapMs = options.maxGapMs ?? SILENCE_HINT_MAX_GAP_MS;
    this.now = options.now ?? (() => Date.now());
  }

  /** The widget asked the browser for the mic. */
  asking(): void {
    const { device } = this.getSnapshot();
    if (device === "live") return;
    this.setDevice("asking", undefined);
  }

  /** A mic track is live. */
  live(): void {
    this.setDevice("live", undefined);
  }

  /**
   * Acquiring or keeping the mic failed, with pipecat's `DeviceError` type,
   * or `track-ended` / `device-gone` for a track lost mid-call. While the
   * browser says the permission is denied, every failure is "blocked".
   */
  failed(errorType: string | undefined): void {
    const denied = this.getSnapshot().permission === "denied";
    this.setDevice(denied ? "blocked" : micStateForError(errorType), denied ? "permissions" : (errorType ?? "unknown"));
  }

  /** The live track's `mute` / `unmute` events. */
  setTrackMuted(trackMuted: boolean): void {
    if (trackMuted === this.getSnapshot().trackMuted) return;
    this.resetQuiet();
    this.update({ trackMuted });
  }

  setMuted(muted: boolean): void {
    this.resetQuiet();
    this.update({ muted });
  }

  /** Whether the agent is waiting for the visitor; the hint counts only then. */
  setAgentListening(listening: boolean): void {
    if (listening === this.agentListening) return;
    this.agentListening = listening;
    this.lastSampleAt = null;
    this.update({});
  }

  /** The browser's permission changed. */
  setPermission(permission: MicSnapshot["permission"]): void {
    this.update({ permission });
  }

  /** A local level sample, 0–1. */
  level(value: number): void {
    const snap = this.getSnapshot();
    const level = Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 0;
    const at = this.now();
    if (snap.device !== "live" || snap.muted || snap.trackMuted || !this.agentListening) {
      this.lastSampleAt = null;
      this.update({ level });
      return;
    }
    if (level >= this.floor) {
      this.resetQuiet();
    } else {
      if (this.lastSampleAt !== null) {
        const gap = at - this.lastSampleAt;
        if (gap >= 0 && gap <= this.maxGapMs) this.quietMs += gap;
      }
      this.lastSampleAt = at;
    }
    this.update({ level });
  }

  /** Back to before the call, keeping the permission the browser reported. */
  reset(): void {
    this.agentListening = false;
    this.resetQuiet();
    this.set({ ...INITIAL, permission: this.getSnapshot().permission });
  }

  private resetQuiet(): void {
    this.quietMs = 0;
    this.lastSampleAt = null;
  }

  private setDevice(device: MicDeviceState, errorType: string | undefined): void {
    this.resetQuiet();
    const everLive = this.getSnapshot().everLive || device === "live";
    // A new track, or none: whatever muted the old one is over.
    this.update({ device, errorType, everLive, trackMuted: false, level: device === "live" ? this.getSnapshot().level : 0 });
  }

  /** Apply a patch and recompute the derived fields, `state` and `hint`. */
  private update(patch: Partial<MicSnapshot>): void {
    const next = { ...this.getSnapshot(), ...patch };
    let state: MicState = next.device;
    if (next.device === "live" && next.muted) state = "muted";
    else if (next.device === "live" && next.trackMuted) state = "missing";
    const hint =
      this.hintEnabled &&
      next.device === "live" &&
      !next.muted &&
      !next.trackMuted &&
      this.agentListening &&
      this.quietMs >= this.afterMs;
    this.set({ ...patch, state, hint });
  }
}

/**
 * Follow the browser's microphone permission, where the Permissions API can
 * say (Safari before 16 and some embedded views cannot). Calls `onChange`
 * with the current answer and again on each change. Never throws; returns a
 * function that stops following.
 *
 * The widget uses this to pick the mic up with no reload when a visitor
 * allows it from the address bar after blocking it.
 *
 * WebKit fires no `change` on a status it has handed out: a page that was
 * refused keeps reading "prompt" there, and only a fresh query sees the
 * grant. So the permission is also asked again when the page regains focus
 * or is shown, and on a tap or key press, and a different answer is
 * reported as a change. `events` is where those are heard (the window by
 * default).
 */
export function watchMicPermission(
  onChange: (state: "granted" | "denied" | "prompt") => void,
  permissions: Pick<Permissions, "query"> | undefined = globalThis.navigator?.permissions,
  events: Pick<EventTarget, "addEventListener" | "removeEventListener"> | undefined = globalThis.window,
): () => void {
  let stopped = false;
  let status: PermissionStatus | null = null;
  let last: PermissionState | null = null;
  const report = (state: PermissionState) => {
    if (stopped || state === last) return;
    last = state;
    onChange(state);
  };
  const listener = () => {
    if (status) report(status.state);
  };
  const ask = () =>
    permissions!.query({ name: "microphone" as PermissionName }).then((result) => {
      report(result.state);
      return result;
    });
  let asking = false;
  const recheck = () => {
    if (stopped || asking || !status) return;
    asking = true;
    try {
      void ask()
        .catch(() => {})
        .finally(() => {
          asking = false;
        });
    } catch {
      asking = false;
    }
  };
  const RECHECK = ["focus", "visibilitychange", "pointerdown", "keydown"] as const;
  try {
    if (!permissions?.query) return () => {};
    ask()
      .then((result) => {
        if (stopped) return;
        status = result;
        result.addEventListener?.("change", listener);
        for (const type of RECHECK) events?.addEventListener(type, recheck, { capture: true, passive: true });
      })
      .catch(() => {});
  } catch {
    return () => {};
  }
  return () => {
    stopped = true;
    try {
      status?.removeEventListener?.("change", listener);
      for (const type of RECHECK) events?.removeEventListener(type, recheck, { capture: true });
    } catch {
      // Nothing to undo.
    }
  };
}
