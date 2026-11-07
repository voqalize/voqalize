/**
 * The widget's session: one call, from the click to the end card.
 *
 * Internal. It is what the widget's elements read, and it is exported from
 * `@voqalize/web/internal` only so this package's own layers can share it;
 * the stable session API (`VoqalizeClient`) is designed separately and comes
 * later. Nothing here is a promise to an application.
 *
 * Over the client and our transport it adds what a widget needs and a raw
 * client does not say:
 *
 * - instant start (see `media.ts`): connect does not wait for the mic;
 * - the mic's state as a store (`mic.ts`), sent to gato as `mic_state`,
 *   including what the local track's `mute` and `ended` events and the
 *   device list's `devicechange` say about it;
 * - the agent's state, derived from the client's speaking and LLM events;
 * - the agent's words as they play and the visitor's transcript, as events;
 * - the devices, with the speaker picker only where `setSinkId` exists;
 * - why the call ended.
 *
 * gato tells the client nothing about why a call ended, so the end reason is
 * read here: the visitor hanging up is known locally; a close before the
 * agent was ever ready is a failed connect; a call the far end closed while
 * the mic never went live ended because nobody allowed the mic (gato's idle
 * rule, which it records as `mic_denied`); any other close is the agent
 * ending the call.
 */

import { PipecatClient, type RTVIEventCallbacks } from "@pipecat-ai/client-js";
import { createVoqalizeTransport } from "@voqalize/client-transport";
import { MicController, type MicSnapshot, type WireMicState, watchMicPermission } from "../controllers/mic.js";
import { Store } from "../controllers/store.js";
import { InstantStartMediaManager, isIOS } from "./media.js";

// ------------------------------------------------------------------- types

export type SessionStatus = "idle" | "connecting" | "connected" | "ended";
export type AgentState = "idle" | "listening" | "thinking" | "speaking";

export type EndReason =
  | { by: "user"; reason: "hung_up" }
  | { by: "agent"; reason: "ended" }
  | { by: "agent"; reason: "mic_denied" }
  | { by: "error"; reason: "connect_failed"; message: string };

export interface DeviceSnapshot {
  mics: MediaDeviceInfo[];
  speakers: MediaDeviceInfo[];
  micId?: string;
  speakerId?: string;
  /** Whether a speaker can be chosen: only where `HTMLMediaElement.setSinkId` exists. */
  canPickSpeaker: boolean;
}

export interface SessionSnapshot {
  status: SessionStatus;
  agent: AgentState;
  devices: DeviceSnapshot;
  /** What the visitor is saying, interim or final. */
  user?: { text: string; final: boolean };
  end?: EndReason;
  sessionId?: string;
}

export interface SessionEvents {
  /** A sentence as its first word starts to play. */
  agentSentence: (text: string) => void;
  /** One word as its audio plays. */
  agentWord: (text: string) => void;
  agentStarted: () => void;
  agentStopped: () => void;
  userTranscript: (text: string, final: boolean) => void;
}

/** The `sessions.connect` answer, as the API returns it. */
export interface SessionResponse {
  webrtc_request_params?: { endpoint?: string; headers?: Record<string, string> | Headers };
  session_id?: string;
  [key: string]: unknown;
}

/** What `connect()` starts a call from: the answer itself, or a function that fetches it. */
export type SessionSource = SessionResponse | (() => Promise<SessionResponse>);

/** The client methods the session uses. `PipecatClient` has them all. */
export interface ClientLike {
  initDevices(): Promise<void>;
  needsInit?(): boolean;
  connect(params?: unknown): Promise<unknown>;
  disconnect(): Promise<void>;
  enableMic(enable: boolean): void;
  sendClientMessage(type: string, data?: unknown): void;
  updateMic(id: string): void;
  updateSpeaker(id: string): void;
}

/** The media manager methods the session uses. */
export interface MediaManagerLike {
  instant: boolean;
  bindOutputElement(element: HTMLMediaElement): () => void;
  /**
   * Choose the mic. Optional: when present the session calls it directly,
   * because the client forwards the choice and drops the promise, so a
   * refusal would surface as an unhandled rejection.
   */
  updateMic?(id: string): Promise<void> | void;
  /** Choose the speaker, likewise. */
  updateSpeaker?(id: string): Promise<void> | void;
}

export interface ClientFactoryArgs {
  mediaManager: MediaManagerLike;
  callbacks: Partial<RTVIEventCallbacks>;
}

export interface SessionOptions {
  /** `mic.instantStart`. Default true. */
  instantStart?: boolean;
  /**
   * Allow instant start on iPhone and iPad. Default false: capture switches
   * iOS's audio session mid-greeting, and that waits on a test on real
   * devices. A library flag, not a widget setting.
   */
  instantStartOnIOS?: boolean;
  /** `mic.silenceHint`. Default true. */
  silenceHint?: boolean;
  /** Where the agent plays. Default: an `<audio>` element the session makes. */
  audioElement?: HTMLMediaElement;
  /** For tests. */
  createMediaManager?: () => MediaManagerLike;
  /** For tests. */
  createClient?: (args: ClientFactoryArgs) => ClientLike;
  /** For tests. */
  isIOS?: boolean;
  /** For tests. */
  canPickSpeaker?: boolean;
  /** For tests: the Permissions API. */
  permissions?: Pick<Permissions, "query">;
  /** For tests: where `devicechange` and the device list come from. */
  mediaDevices?: Pick<MediaDevices, "addEventListener" | "removeEventListener" | "enumerateDevices">;
  /** For tests: the mic controller's clock. */
  now?: () => number;
}

// ------------------------------------------------------------------ helpers

/** The `sessions.connect` answer with its headers as a real `Headers`, which the transport needs. */
export function withRealHeaders(response: SessionResponse): SessionResponse {
  const params = response.webrtc_request_params;
  if (!params) return response;
  const headers = params.headers instanceof Headers ? params.headers : new Headers(params.headers ?? {});
  return { ...response, webrtc_request_params: { ...params, headers } };
}

export const DEFAULT_API_BASE = "https://app.voqalize.com/api/v1";

export interface MintOptions {
  agent: string;
  /** A publishable key. */
  key: string;
  apiBase?: string;
  /** The session's init values, such as a Site Agent's greeting. */
  init?: Record<string, unknown>;
  fetch?: typeof fetch;
}

/** Start a session from the page with a publishable key: the one `fetch` of `build/connect`. */
export async function mintSession(options: MintOptions): Promise<SessionResponse> {
  const doFetch = options.fetch ?? globalThis.fetch.bind(globalThis);
  const body: Record<string, unknown> = { agent_id: options.agent };
  if (options.init) body.init = options.init;
  const response = await doFetch(`${options.apiBase ?? DEFAULT_API_BASE}/sessions.connect`, {
    method: "POST",
    headers: { Authorization: `Bearer ${options.key}`, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    let detail = "";
    try {
      detail = (await response.text()).slice(0, 200);
    } catch {
      // No body to show.
    }
    throw new Error(`sessions.connect answered ${response.status}${detail ? `: ${detail}` : ""}`);
  }
  return (await response.json()) as SessionResponse;
}

function speakerPickable(): boolean {
  try {
    return typeof globalThis.HTMLMediaElement?.prototype.setSinkId === "function";
  } catch {
    return false;
  }
}

function defaultClient({ mediaManager, callbacks }: ClientFactoryArgs): ClientLike {
  const transport = createVoqalizeTransport({ mediaManager: mediaManager as InstantStartMediaManager });
  return new PipecatClient({ transport, enableMic: true, enableCam: false, callbacks });
}

type Listeners = { [K in keyof SessionEvents]: Set<SessionEvents[K]> };

// ----------------------------------------------------------------- session

export class WidgetSession extends Store<SessionSnapshot> {
  readonly mic: MicController;
  private readonly options: SessionOptions;
  private readonly mediaManager: MediaManagerLike;
  private readonly client: ClientLike;
  private readonly handlers: Listeners = {
    agentSentence: new Set(),
    agentWord: new Set(),
    agentStarted: new Set(),
    agentStopped: new Set(),
    userTranscript: new Set(),
  };
  private audio: HTMLMediaElement | null = null;
  private unbindAudio: (() => void) | null = null;
  private stopPermissionWatch: (() => void) | null = null;
  /** Stops following the local track's events. */
  private stopTrackWatch: (() => void) | null = null;
  private stopDeviceWatch: (() => void) | null = null;
  private ready = false;
  /** Whether the agent was ever ready on this call: a close before that is a failed connect. */
  private wasReady = false;
  private hangingUp = false;
  /** Bumped by every connect and hang-up: an older connect that resumes after either stops. */
  private generation = 0;
  private lastSent: string | null = null;
  private localTrack: MediaStreamTrack | null = null;

  constructor(options: SessionOptions = {}) {
    const canPickSpeaker = options.canPickSpeaker ?? speakerPickable();
    super({ status: "idle", agent: "idle", devices: { mics: [], speakers: [], canPickSpeaker } });
    this.options = options;
    this.mic = new MicController({ silenceHint: options.silenceHint ?? true, now: options.now });
    this.mediaManager = options.createMediaManager?.() ?? new InstantStartMediaManager();
    this.client = (options.createClient ?? defaultClient)({
      mediaManager: this.mediaManager,
      callbacks: this.callbacks(),
    });
    this.mic.subscribe(() => this.sendMicState());
  }

  /**
   * The underlying client, for a layer that must hold it itself — the
   * avatar follows the call from it. Internal, like everything here.
   */
  get rawClient(): ClientLike {
    return this.client;
  }

  /** Whether this call connects without waiting for the mic. */
  get instant(): boolean {
    if (!(this.options.instantStart ?? true)) return false;
    const ios = this.options.isIOS ?? isIOS();
    return !ios || (this.options.instantStartOnIOS ?? false);
  }

  on<K extends keyof SessionEvents>(event: K, listener: SessionEvents[K]): () => void {
    this.handlers[event].add(listener);
    return () => {
      this.handlers[event].delete(listener);
    };
  }

  /**
   * Start the call. In instant mode the mic is asked for and the session
   * fetched at the same time, and the call connects without waiting for the
   * visitor to answer the prompt. Call it from the click, so the greeting's
   * audio is allowed to play.
   */
  async connect(source: SessionSource): Promise<void> {
    const status = this.getSnapshot().status;
    if (status === "connecting" || status === "connected") return;
    const generation = ++this.generation;
    const stale = () => generation !== this.generation || this.hangingUp;
    this.ready = false;
    this.wasReady = false;
    this.hangingUp = false;
    this.lastSent = null;
    this.mic.reset();
    this.set({ status: "connecting", agent: "idle", end: undefined, user: undefined, sessionId: undefined });
    this.bindAudio();
    this.watchPermission();
    this.watchDevices();

    const instant = this.instant;
    this.mediaManager.instant = instant;
    this.mic.asking();
    try {
      const devices = this.client.needsInit?.() === false ? Promise.resolve() : this.client.initDevices();
      const fetchSession = () => (typeof source === "function" ? source() : Promise.resolve(source));
      let response: SessionResponse;
      if (instant) {
        [, response] = await Promise.all([devices, fetchSession()]);
      } else {
        // The stock order: the mic first, then the session, so a session is
        // never minted for a visitor who is still reading the prompt.
        await devices;
        response = await fetchSession();
      }
      if (stale()) return;
      this.set({ sessionId: typeof response.session_id === "string" ? response.session_id : undefined });
      await this.client.connect(withRealHeaders(response));
      if (stale()) return;
      if (this.getSnapshot().status === "connecting") this.set({ status: "connected" });
    } catch (error) {
      if (stale()) return;
      const message = error instanceof Error ? error.message : String(error);
      this.finish({ by: "error", reason: "connect_failed", message });
      await this.client.disconnect().catch(() => {});
    }
  }

  /** The visitor hung up. */
  async disconnect(): Promise<void> {
    const status = this.getSnapshot().status;
    if (status === "idle" || status === "ended") return;
    this.hangingUp = true;
    this.generation++;
    this.finish({ by: "user", reason: "hung_up" });
    await this.client.disconnect().catch(() => {});
  }

  setMuted(muted: boolean): void {
    this.mic.setMuted(muted);
    try {
      this.client.enableMic(!muted);
    } catch {
      // Before the client has devices there is nothing to enable.
    }
  }

  /**
   * Ask for the mic again, from the visitor's tap on "Grant mic permission".
   * Only while it is blocked and the browser does not say the permission is
   * denied: Safari reads "prompt" after a refusal, and asking again from a
   * tap is how it is allowed there. A denied permission is changed in the
   * browser, not by asking, and the coach says where.
   */
  askForMic(): void {
    const mic = this.mic.getSnapshot();
    if (mic.device !== "blocked" || mic.permission === "denied" || mic.muted) return;
    const status = this.getSnapshot().status;
    if (status !== "connecting" && status !== "connected") return;
    this.mic.asking();
    try {
      this.client.enableMic(true);
    } catch {
      // Before the client has devices there is nothing to enable.
    }
  }

  /** Choose the mic. A device that cannot be opened is reported as a device error. */
  selectMic(id: string): void {
    // The old track ends when the new one replaces it; that end is the
    // switch, not a lost mic. The new track is followed when it starts.
    this.unwatchTrack();
    this.settle(this.mediaManager.updateMic ? this.mediaManager.updateMic(id) : this.client.updateMic(id));
  }

  /**
   * Choose where the agent plays. Does nothing where the browser cannot
   * route audio. If the browser refuses the device, the menu goes back to
   * the speaker that is still playing.
   */
  selectSpeaker(id: string): void {
    if (!this.getSnapshot().devices.canPickSpeaker) return;
    const before = this.getSnapshot().devices.speakerId;
    const revert = () => this.setDevices({ speakerId: before });
    try {
      this.settle(
        this.mediaManager.updateSpeaker ? this.mediaManager.updateSpeaker(id) : this.client.updateSpeaker(id),
        revert,
      );
    } catch {
      revert();
    }
  }

  /** Swallow a device change's rejection, which the caller has no promise to catch. */
  private settle(result: unknown, onError?: () => void): void {
    if (result && typeof (result as Promise<void>).then === "function") {
      (result as Promise<void>).then(undefined, () => onError?.());
    }
  }

  // ------------------------------------------------------------- internals

  private emit<K extends keyof SessionEvents>(event: K, ...args: Parameters<SessionEvents[K]>): void {
    for (const listener of [...this.handlers[event]]) {
      try {
        (listener as (...a: Parameters<SessionEvents[K]>) => void)(...args);
      } catch {
        // One broken listener must not stop the others or the call.
      }
    }
  }

  private setAgent(agent: AgentState): void {
    this.set({ agent });
    this.mic.setAgentListening(agent === "listening");
  }

  private setDevices(patch: Partial<DeviceSnapshot>): void {
    this.set({ devices: { ...this.getSnapshot().devices, ...patch } });
  }

  /** `mic_state` to gato: once when the agent is ready, then on every change. */
  private sendMicState(): void {
    if (!this.ready) return;
    const snap: MicSnapshot = this.mic.getSnapshot();
    if (snap.state === "idle") return;
    const state: WireMicState = snap.state;
    const key = `${state}:${snap.hint}`;
    if (key === this.lastSent) return;
    try {
      this.client.sendClientMessage("mic_state", { state, hint: snap.hint });
      this.lastSent = key;
    } catch {
      // Not ready to send; the next change tries again.
    }
  }

  private finish(end: EndReason): void {
    if (this.getSnapshot().status === "ended") return;
    this.ready = false;
    this.set({ status: "ended", agent: "idle", end });
    this.mic.setAgentListening(false);
    this.stopPermissionWatch?.();
    this.stopPermissionWatch = null;
    // Hanging up stops the track; that end is not news.
    this.unwatchTrack();
    this.stopDeviceWatch?.();
    this.stopDeviceWatch = null;
    if (this.audio) this.audio.srcObject = null;
  }

  /**
   * Follow the local mic track: `mute` and `unmute` when the system or
   * another app silences it, `ended` when it is gone for good.
   */
  private watchTrack(track: MediaStreamTrack): void {
    this.unwatchTrack();
    const onMute = () => this.mic.setTrackMuted(true);
    const onUnmute = () => this.mic.setTrackMuted(false);
    const onEnded = () => {
      this.unwatchTrack();
      if (this.getSnapshot().status !== "ended") this.mic.failed("track-ended");
    };
    try {
      track.addEventListener("mute", onMute);
      track.addEventListener("unmute", onUnmute);
      track.addEventListener("ended", onEnded);
    } catch {
      return; // not a real track: nothing to follow
    }
    this.localTrack = track;
    this.stopTrackWatch = () => {
      track.removeEventListener("mute", onMute);
      track.removeEventListener("unmute", onUnmute);
      track.removeEventListener("ended", onEnded);
      if (this.localTrack === track) this.localTrack = null;
    };
    if (track.readyState === "ended") onEnded();
    else if (track.muted) onMute();
  }

  private unwatchTrack(): void {
    this.stopTrackWatch?.();
    this.stopTrackWatch = null;
  }

  /**
   * On `devicechange`, the device the live track reads from may have left
   * (unplugged, switched off). Most browsers end the track too; this catches
   * the ones that leave a silent track behind.
   */
  private watchDevices(): void {
    this.stopDeviceWatch?.();
    this.stopDeviceWatch = null;
    const media = this.options.mediaDevices ?? globalThis.navigator?.mediaDevices;
    if (!media?.addEventListener) return;
    const onChange = () => {
      const track = this.localTrack;
      if (!track || this.getSnapshot().status === "ended") return;
      let id: string | undefined;
      try {
        id = track.getSettings?.().deviceId;
      } catch {
        id = undefined;
      }
      media
        .enumerateDevices()
        .then((devices) => {
          if (this.localTrack !== track || this.getSnapshot().status === "ended") return;
          const mics = devices.filter((d) => d.kind === "audioinput");
          const gone = track.readyState === "ended" || mics.length === 0 || (id !== undefined && id !== "" && !mics.some((d) => d.deviceId === id));
          if (gone) {
            this.unwatchTrack();
            this.mic.failed("device-gone");
          }
        })
        .catch(() => {});
    };
    try {
      media.addEventListener("devicechange", onChange);
      this.stopDeviceWatch = () => media.removeEventListener("devicechange", onChange);
    } catch {
      // No device events here.
    }
  }

  private bindAudio(): void {
    if (this.audio) return;
    const element =
      this.options.audioElement ??
      (typeof document !== "undefined" ? document.createElement("audio") : null);
    if (!element) return;
    element.autoplay = true;
    this.audio = element;
    try {
      this.unbindAudio = this.mediaManager.bindOutputElement(element);
    } catch {
      this.unbindAudio = null;
    }
  }

  private watchPermission(): void {
    this.stopPermissionWatch?.();
    this.stopPermissionWatch = watchMicPermission((state) => {
      const before = this.mic.getSnapshot();
      this.mic.setPermission(state);
      const live = this.getSnapshot().status !== "ended";
      // Revoked mid-call, from the address bar or the site's settings: the
      // track stops, and the coach can say how to undo it.
      if (state === "denied" && live && before.device !== "blocked" && before.device !== "idle") {
        this.mic.failed("permissions");
        return;
      }
      // Allowed from the address bar after a refusal: pick the mic up with
      // no reload.
      if (state === "granted" && before.device === "blocked" && live) {
        this.mic.asking();
        if (!before.muted) {
          try {
            this.client.enableMic(true);
          } catch {
            // Picked up on the next attempt.
          }
        }
      }
    }, this.options.permissions);
  }

  /**
   * Hang up a call still in progress, stop listening for permission changes
   * and unbind the audio element.
   */
  dispose(): void {
    const status = this.getSnapshot().status;
    if (status === "connecting" || status === "connected") void this.disconnect();
    this.stopPermissionWatch?.();
    this.stopPermissionWatch = null;
    this.unwatchTrack();
    this.stopDeviceWatch?.();
    this.stopDeviceWatch = null;
    this.unbindAudio?.();
    this.unbindAudio = null;
  }

  private callbacks(): Partial<RTVIEventCallbacks> {
    return {
      onBotReady: () => {
        this.ready = true;
        this.wasReady = true;
        this.set({ status: "connected" });
        this.setAgent("listening");
        this.sendMicState();
      },
      onDisconnected: () => {
        if (this.hangingUp || this.getSnapshot().status === "ended") return;
        if (this.getSnapshot().status === "idle") return;
        // The transport gave up before the agent was ready: the connect
        // failed, whatever the mic did.
        if (!this.wasReady) {
          this.finish({ by: "error", reason: "connect_failed", message: "disconnected before the agent was ready" });
          return;
        }
        this.finish(
          this.mic.getSnapshot().everLive ? { by: "agent", reason: "ended" } : { by: "agent", reason: "mic_denied" },
        );
      },
      onUserStartedSpeaking: () => this.setAgent("listening"),
      onBotLlmStarted: () => this.setAgent("thinking"),
      onBotStartedSpeaking: () => {
        this.setAgent("speaking");
        this.emit("agentStarted");
      },
      onBotStoppedSpeaking: () => {
        this.setAgent("listening");
        this.emit("agentStopped");
      },
      onBotOutput: (data) => {
        if (data.spoken_status !== "new" || data.aggregated_by === "word") return;
        if (data.text) this.emit("agentSentence", data.text);
      },
      onBotTtsText: (data) => {
        if (data.text) this.emit("agentWord", data.text);
      },
      onUserTranscript: (data) => {
        this.set({ user: { text: data.text, final: Boolean(data.final) } });
        this.emit("userTranscript", data.text, Boolean(data.final));
      },
      onLocalAudioLevel: (level) => this.mic.level(level),
      onTrackStarted: (track, participant) => {
        if (track.kind !== "audio") return;
        if (participant?.local) {
          this.mic.live();
          this.watchTrack(track);
          return;
        }
        if (this.audio) {
          try {
            this.audio.srcObject = new MediaStream([track]);
            void this.audio.play?.()?.catch(() => {});
          } catch {
            // The playout guard re-attaches it.
          }
        }
      },
      onDeviceError: (error) => {
        const devices = (error as { devices?: string[] }).devices ?? [];
        if (devices.includes("mic")) this.mic.failed((error as { type?: string }).type);
      },
      onAvailableMicsUpdated: (mics) => this.setDevices({ mics }),
      onAvailableSpeakersUpdated: (speakers) => this.setDevices({ speakers }),
      onMicUpdated: (mic) => this.setDevices({ micId: mic.deviceId }),
      onSpeakerUpdated: (speaker) => this.setDevices({ speakerId: speaker.deviceId }),
    };
  }
}
