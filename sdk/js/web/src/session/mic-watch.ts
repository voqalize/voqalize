/**
 * The mic's state and hint, read from what the stock client and transport
 * already say. Nothing here is sent anywhere.
 *
 * `MicState` is what the mic is doing:
 *
 * - `idle`: no call.
 * - `muted`: the visitor's mute, or a call that started muted and has not
 *   been unmuted yet. Nothing is asked of the browser.
 * - `asking`: the mic is wanted and nothing has answered yet: the browser's
 *   prompt is, or is about to be, on screen.
 * - `live`: a local audio track is running.
 * - `blocked`: the visitor or the browser refused it (`DeviceError` of type
 *   `permissions`).
 * - `missing`: no mic, one another app holds, one that could not be opened,
 *   or a live one the system has silenced (the track reads `muted`).
 *
 * `MicHint` is what the visitor should be told:
 *
 * - `grant`: the browser is asking and the permission is not yet refused.
 * - `blocked`: refused, or asking where the permission already reads denied.
 * - `missing`: as the state.
 * - `silent`: live, but nothing above a whisper has reached it for a while,
 *   at a time the agent was quiet and waiting. A quiet visitor is not a
 *   broken mic, so this is a hint to show, never a reason to act.
 * - `none`: nothing to say.
 *
 * Its inputs are the session's: whether a call is on, whether the mic is
 * wanted, the local track the transport announces (`onTrackStarted` /
 * `onTrackStopped` with a local participant), the client's `onDeviceError`,
 * the local level (`onLocalAudioLevel`), the agent's speaking events and the
 * browser's permission where the Permissions API can say.
 */

export type MicState = "idle" | "asking" | "live" | "blocked" | "missing" | "muted";
export type MicHint = "none" | "grant" | "blocked" | "missing" | "silent";
export type MicPermission = "granted" | "denied" | "prompt" | "unknown";

/** The `DeviceError` types pipecat reports, as strings. */
export type DeviceErrorKind = string;

/** What the session reads the mic from. `MicWatch` is the real one. */
export interface MicSource {
  readonly micState: MicState;
  readonly micHint: MicHint;
  onMicStateChange(listener: (state: MicState) => void): () => void;
  onMicHintChange(listener: (hint: MicHint) => void): () => void;
}

/**
 * Below this local level (0–1 peak amplitude, `onLocalAudioLevel`'s scale) a
 * sample counts as silence.
 *
 * TO BE TUNED FROM REAL CALLS: a placeholder.
 */
export const SILENCE_FLOOR = 0.003;

/**
 * How long, in ms, the local level must stay under the floor while the agent
 * waits before `silent` shows. Time the agent spends speaking does not count.
 *
 * TO BE TUNED FROM REAL CALLS, like the floor.
 */
export const SILENCE_AFTER_MS = 8000;

/**
 * The longest gap between two local level samples that counts as continuous
 * listening. The meter reports every 100 ms while the mic is live; a longer
 * gap means it stopped (a mute, a device change, a background tab), and that
 * time is no evidence of silence.
 */
export const SILENCE_MAX_GAP_MS = 500;

export interface SilenceWatchOptions {
  floor?: number;
  afterMs?: number;
  maxGapMs?: number;
}

/**
 * The `silent` half of the hint: a run of local silence while the agent is
 * quiet, after it has spoken at least once. Fed samples with the time they
 * were taken; owns no timers.
 */
export class SilenceWatch {
  private readonly floor: number;
  private readonly afterMs: number;
  private readonly maxGapMs: number;
  private quietMs = 0;
  private lastLocalAt: number | null = null;
  private agentSpoke = false;
  private agentSpeaking = false;

  constructor(options: SilenceWatchOptions = {}) {
    this.floor = options.floor ?? SILENCE_FLOOR;
    this.afterMs = options.afterMs ?? SILENCE_AFTER_MS;
    this.maxGapMs = options.maxGapMs ?? SILENCE_MAX_GAP_MS;
  }

  get silent(): boolean {
    return this.quietMs >= this.afterMs;
  }

  /** The agent started or stopped speaking. */
  agent(speaking: boolean): void {
    this.agentSpeaking = speaking;
    if (speaking) {
      this.agentSpoke = true;
      this.breakRun();
    }
  }

  /** A local level sample, 0–1. */
  local(level: number, at: number): void {
    if (!this.agentSpoke || this.agentSpeaking) {
      this.lastLocalAt = null;
      return;
    }
    if (!(level < this.floor)) {
      this.quietMs = 0;
      this.lastLocalAt = at;
      return;
    }
    if (this.lastLocalAt !== null) {
      const gap = at - this.lastLocalAt;
      if (gap >= 0 && gap <= this.maxGapMs) this.quietMs += gap;
    }
    this.lastLocalAt = at;
  }

  /** The run so far no longer counts: the mic changed state. */
  breakRun(): void {
    this.quietMs = 0;
    this.lastLocalAt = null;
  }

  /** A new call: the agent has not spoken in it yet. */
  reset(): void {
    this.breakRun();
    this.agentSpoke = false;
    this.agentSpeaking = false;
  }
}

/**
 * Follow the browser's mic permission, where the Permissions API can say
 * (some embedded views cannot). Calls `onChange` with the current answer and
 * again on each change, or once with "unknown" where the browser cannot say.
 * Never throws; returns a function that stops.
 *
 * WebKit fires no `change` on a status it has handed out: a page that was
 * refused keeps reading "prompt" there, and only a fresh query sees the
 * grant. So the permission is asked again when the page regains focus or is
 * shown, and on a tap or key press, and a different answer is reported.
 */
export function watchMicPermission(
  onChange: (state: MicPermission) => void,
  permissions: Pick<Permissions, "query"> | undefined = globalThis.navigator?.permissions,
  events:
    Pick<EventTarget, "addEventListener" | "removeEventListener"> | undefined = globalThis.window,
): () => void {
  let stopped = false;
  let status: PermissionStatus | null = null;
  let last: MicPermission | null = null;
  const report = (state: MicPermission) => {
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
  const unknown = () => {
    // Asynchronously, as an answer would be, so a caller sees one order.
    void Promise.resolve().then(() => report("unknown"));
  };
  try {
    if (!permissions?.query) {
      unknown();
      return () => {
        stopped = true;
      };
    }
    ask()
      .then((result) => {
        if (stopped) return;
        status = result;
        result.addEventListener?.("change", listener);
        for (const type of RECHECK) {
          events?.addEventListener(type, recheck, { capture: true, passive: true });
        }
      })
      .catch(unknown);
  } catch {
    unknown();
    return () => {
      stopped = true;
    };
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

export interface MicWatchOptions {
  /** For tests: where the permission comes from. Default `watchMicPermission`. */
  watchPermission?: (onChange: (state: MicPermission) => void) => () => void;
  /** For tests: the clock the silence run is measured on. */
  now?: () => number;
  silence?: SilenceWatchOptions;
}

type Failure = "blocked" | "missing";

/** The mic, derived from the session's events. */
export class MicWatch implements MicSource {
  private readonly stateListeners = new Set<(state: MicState) => void>();
  private readonly hintListeners = new Set<(hint: MicHint) => void>();
  private readonly silence: SilenceWatch;
  private readonly now: () => number;
  private readonly watchPermission: (onChange: (state: MicPermission) => void) => () => void;
  private stopPermission: (() => void) | null = null;
  private permission: MicPermission | "pending" = "pending";
  private active = false;
  private desired = false;
  private failure: Failure | null = null;
  private track: MediaStreamTrack | null = null;
  private trackMuted = false;
  private untrack: (() => void) | null = null;
  private state: MicState = "idle";
  private hint: MicHint = "none";

  constructor(options: MicWatchOptions = {}) {
    this.silence = new SilenceWatch(options.silence);
    this.now = options.now ?? (() => (globalThis.performance ?? Date).now());
    this.watchPermission = options.watchPermission ?? ((onChange) => watchMicPermission(onChange));
  }

  get micState(): MicState {
    return this.state;
  }

  get micHint(): MicHint {
    return this.hint;
  }

  onMicStateChange(listener: (state: MicState) => void): () => void {
    this.stateListeners.add(listener);
    return () => this.stateListeners.delete(listener);
  }

  onMicHintChange(listener: (hint: MicHint) => void): () => void {
    this.hintListeners.add(listener);
    return () => this.hintListeners.delete(listener);
  }

  /** A call starts, with the mic wanted or not. */
  start(desired: boolean): void {
    this.active = true;
    this.desired = desired;
    this.failure = null;
    this.silence.reset();
    if (!this.stopPermission) {
      this.stopPermission = this.watchPermission((state) => {
        this.permission = state;
        this.update();
      });
    }
    this.update();
  }

  /** The call ended. */
  stop(): void {
    this.active = false;
    this.stopPermission?.();
    this.stopPermission = null;
    this.permission = "pending";
    this.setTrack(null);
    this.failure = null;
    this.silence.reset();
    this.update();
  }

  /** The mic was asked for (unmute, or a tap to ask again) or put down (mute). */
  setDesired(desired: boolean): void {
    this.desired = desired;
    // A new ask starts from no answer; a refusal comes back as a new error.
    if (desired) this.failure = null;
    this.silence.breakRun();
    this.update();
  }

  /** The transport started (a track) or stopped (null) the local audio track. */
  setTrack(track: MediaStreamTrack | null): void {
    if (track === this.track) return;
    this.untrack?.();
    this.untrack = null;
    this.track = track;
    this.trackMuted = Boolean(track?.muted);
    if (track) {
      this.failure = null;
      const onMute = () => {
        this.trackMuted = true;
        this.silence.breakRun();
        this.update();
      };
      const onUnmute = () => {
        this.trackMuted = false;
        this.update();
      };
      const onEnded = () => {
        if (this.track === track) this.setTrack(null);
      };
      try {
        track.addEventListener?.("mute", onMute);
        track.addEventListener?.("unmute", onUnmute);
        track.addEventListener?.("ended", onEnded);
        this.untrack = () => {
          track.removeEventListener?.("mute", onMute);
          track.removeEventListener?.("unmute", onUnmute);
          track.removeEventListener?.("ended", onEnded);
        };
      } catch {
        // A track that cannot be listened to is taken as it reads now.
      }
    }
    this.silence.breakRun();
    this.update();
  }

  /** The client's `onDeviceError`, for the mic. */
  deviceError(kind: DeviceErrorKind): void {
    if (!this.active) return;
    this.failure = kind === "permissions" ? "blocked" : "missing";
    this.update();
  }

  /** The local level, 0–1. */
  level(value: number): void {
    this.silence.local(value, this.now());
    this.updateHint();
  }

  /** The agent started or stopped speaking. */
  agentSpeaking(speaking: boolean): void {
    this.silence.agent(speaking);
    this.updateHint();
  }

  dispose(): void {
    this.stop();
    this.stateListeners.clear();
    this.hintListeners.clear();
  }

  private computeState(): MicState {
    if (!this.active) return "idle";
    if (!this.desired) return "muted";
    if (this.track && this.track.readyState !== "ended") return this.trackMuted ? "missing" : "live";
    if (this.failure) return this.failure;
    return "asking";
  }

  private computeHint(): MicHint {
    switch (this.state) {
      case "asking":
        if (this.permission === "denied") return "blocked";
        return this.permission === "prompt" || this.permission === "unknown" ? "grant" : "none";
      case "blocked":
        return "blocked";
      case "missing":
        return "missing";
      case "live":
        return this.silence.silent ? "silent" : "none";
      default:
        return "none";
    }
  }

  private update(): void {
    const state = this.computeState();
    if (state !== this.state) {
      this.state = state;
      if (state !== "live") this.silence.breakRun();
      for (const listener of [...this.stateListeners]) listener(state);
    }
    this.updateHint();
  }

  private updateHint(): void {
    const hint = this.computeHint();
    if (hint === this.hint) return;
    this.hint = hint;
    for (const listener of [...this.hintListeners]) listener(hint);
  }
}
