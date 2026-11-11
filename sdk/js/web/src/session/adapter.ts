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
 * - instant start: the call starts muted (the client's `enableMic: false`),
 *   so it connects and the greeting plays without the browser asking for
 *   anything; the browser is first asked when the visitor unmutes;
 * - the mic as a store (`mic.ts`), mirroring `micState` and `micHint`, which
 *   `mic-watch.ts` derives from the stock client's and transport's events,
 *   and the attention tone (`tone.ts`) while the mic is off;
 * - the agent's state, derived from the client's speaking and LLM events;
 * - the agent's words as they play and the visitor's transcript, as events;
 * - the devices, with the speaker picker only where `setSinkId` exists;
 * - why the call ended.
 *
 * The far end tells the client nothing about why a call ended, so the end
 * reason is read here: the visitor hanging up is known locally; a close
 * before the agent was ever ready is a failed connect; a call the far end
 * closed while the mic never went live ended because nobody allowed the mic
 * (the agent's idle timeout, recorded as `mic_denied`); any other close is
 * the agent ending the call.
 */

import { PipecatClient, type RTVIEventCallbacks } from "@pipecat-ai/client-js";
import { createVoqalizeTransport, VoqalizeMediaManager } from "@voqalize/client-transport";
import { MicController, micIsOff } from "../controllers/mic.js";
import { Store } from "../controllers/store.js";
import { MicWatch, type MicWatchOptions } from "./mic-watch.js";
import { createTonePlayer, TONE_AGAIN_MS, type TonePlayer } from "./tone.js";

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
  /** Whether the client wants the mic; read before asking again after a refusal. */
  readonly isMicEnabled?: boolean;
  sendClientMessage(type: string, data?: unknown): void;
  updateMic(id: string): void;
  updateSpeaker(id: string): void;
}

/** The media manager methods the session uses. */
export interface MediaManagerLike {
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
  /** Whether the call asks for the mic as it starts; false for instant start. */
  enableMic: boolean;
}

export interface SessionOptions {
  /**
   * `mic.instantStart`. Default true: the call starts muted and connects at
   * once, and the browser is asked for the mic when the visitor unmutes.
   * False asks for the mic first and connects once the visitor has answered.
   */
  instantStart?: boolean;
  /** `mic.silenceHint`. Default true. */
  silenceHint?: boolean;
  /** `mic.alertTone`: the attention tone while the mic is off. Default false. */
  alertTone?: boolean;
  /** Where the agent plays. Default: an `<audio>` element the session makes. */
  audioElement?: HTMLMediaElement;
  /** For tests. */
  createMediaManager?: () => MediaManagerLike;
  /** For tests: the mic watch's permission source and clock. */
  micWatch?: MicWatchOptions;
  /** For tests. */
  createClient?: (args: ClientFactoryArgs) => ClientLike;
  /** For tests. */
  canPickSpeaker?: boolean;
  /** For tests: what makes the attention tone. */
  createTone?: () => TonePlayer | null;
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

function defaultClient({ mediaManager, callbacks, enableMic }: ClientFactoryArgs): ClientLike {
  const transport = createVoqalizeTransport({ mediaManager: mediaManager as VoqalizeMediaManager });
  return new PipecatClient({ transport, enableMic, enableCam: false, callbacks });
}

type Listeners = { [K in keyof SessionEvents]: Set<SessionEvents[K]> };

// ----------------------------------------------------------------- session

export class WidgetSession extends Store<SessionSnapshot> {
  readonly mic: MicController;
  private readonly micWatch: MicWatch;
  private readonly instantStart: boolean;
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
  private readonly unsubscribeMic: Array<() => void>;
  /** Whether the agent was ever ready on this call: a close before that is a failed connect. */
  private wasReady = false;
  private hangingUp = false;
  /** Bumped by every connect and hang-up: an older connect that resumes after either stops. */
  private generation = 0;
  private tone: TonePlayer | null = null;
  /** Whether this call's attention tone has been scheduled; it is, once, at the agent's first stop. */
  private toneScheduled = false;
  private toneTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(options: SessionOptions = {}) {
    const canPickSpeaker = options.canPickSpeaker ?? speakerPickable();
    super({ status: "idle", agent: "idle", devices: { mics: [], speakers: [], canPickSpeaker } });
    this.options = options;
    this.mic = new MicController({ silenceHint: options.silenceHint ?? true });
    this.instantStart = options.instantStart ?? true;
    this.micWatch = new MicWatch(options.micWatch);
    // One manager per session, and one client per session: the manager keeps
    // the first client's callbacks it is given, so it is never shared.
    this.mediaManager = options.createMediaManager?.() ?? new VoqalizeMediaManager();
    this.client = (options.createClient ?? defaultClient)({
      mediaManager: this.mediaManager,
      callbacks: this.callbacks(),
      enableMic: !this.instantStart,
    });
    this.unsubscribeMic = [
      this.micWatch.onMicStateChange((state) => this.mic.setState(state)),
      this.micWatch.onMicHintChange((hint) => this.mic.setHint(hint)),
    ];
  }

  /**
   * The underlying client, for a layer that must hold it itself — the
   * avatar follows the call from it. Internal, like everything here.
   */
  get rawClient(): ClientLike {
    return this.client;
  }

  on<K extends keyof SessionEvents>(event: K, listener: SessionEvents[K]): () => void {
    this.handlers[event].add(listener);
    return () => {
      this.handlers[event].delete(listener);
    };
  }

  /**
   * Start the call. In instant mode the call starts muted: nothing is asked
   * of the browser, and the call connects at once. Otherwise the mic is
   * asked for first. Call it from the click, so the greeting's audio, and
   * the attention tone, are allowed to play.
   */
  async connect(source: SessionSource): Promise<void> {
    const status = this.getSnapshot().status;
    if (status === "connecting" || status === "connected") return;
    const generation = ++this.generation;
    const stale = () => generation !== this.generation || this.hangingUp;
    this.wasReady = false;
    this.hangingUp = false;
    this.micWatch.stop();
    this.mic.reset(this.micWatch.micState, this.micWatch.micHint);
    this.mic.setMuted(this.instantStart);
    this.micWatch.start(!this.instantStart);
    this.set({ status: "connecting", agent: "idle", end: undefined, user: undefined, sessionId: undefined });
    this.bindAudio();
    this.startTone();
    try {
      // In instant mode the mic is not wanted yet and this returns at once;
      // otherwise it waits for the visitor to answer the prompt, so a
      // session is never minted for a visitor who is still reading it.
      if (this.client.needsInit?.() !== false) await this.client.initDevices();
      if (stale()) return;
      const response = await (typeof source === "function" ? source() : Promise.resolve(source));
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
    this.micWatch.setDesired(!muted);
    try {
      this.client.enableMic(!muted);
    } catch {
      // Before the client has devices there is nothing to enable.
    }
  }

  /**
   * Ask for the mic again, from the visitor's tap on "Grant mic permission".
   * Only while it is refused or missing: Safari reads "prompt" after a
   * refusal, and asking again from a tap is how it is allowed there. Where
   * the browser remembers the refusal, asking fails at once and the coach
   * says where the setting is.
   */
  askForMic(): void {
    const mic = this.mic.getSnapshot();
    if ((mic.state !== "blocked" && mic.state !== "missing") || mic.muted) return;
    const status = this.getSnapshot().status;
    if (status !== "connecting" && status !== "connected") return;
    this.micWatch.setDesired(true);
    try {
      // The client still wants the mic after a refusal, and wanting it again
      // is no change: put it down first, so the transport asks once more.
      if (this.client.isMicEnabled) this.client.enableMic(false);
      this.client.enableMic(true);
    } catch {
      // Before the client has devices there is nothing to enable.
    }
  }

  /** Choose the mic. A device that cannot be opened is reported as a device error. */
  selectMic(id: string): void {
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
  }

  private setDevices(patch: Partial<DeviceSnapshot>): void {
    this.set({ devices: { ...this.getSnapshot().devices, ...patch } });
  }

  private finish(end: EndReason): void {
    if (this.getSnapshot().status === "ended") return;
    this.set({ status: "ended", agent: "idle", end });
    this.micWatch.stop();
    this.stopTone();
    if (this.audio) this.audio.srcObject = null;
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

  /** Make the tone's audio context now, in the click that starts the call. */
  private startTone(): void {
    this.stopTone();
    this.toneScheduled = false;
    if (!this.options.alertTone) return;
    this.tone = (this.options.createTone ?? createTonePlayer)();
  }

  /**
   * The agent finished speaking. The first time in a call, the tone plays if
   * the mic is off, and once more after `TONE_AGAIN_MS` if it still is.
   */
  private agentStoppedForTone(): void {
    if (!this.tone || this.toneScheduled) return;
    this.toneScheduled = true;
    const beep = () => {
      if (this.getSnapshot().status === "ended") return;
      const mic = this.mic.getSnapshot();
      // Off, or still muted from an instant start: the visitor has not been heard yet.
      if (micIsOff(mic.micHint) || (mic.state === "muted" && !mic.everLive)) this.tone?.play();
    };
    beep();
    this.toneTimer = setTimeout(() => {
      this.toneTimer = null;
      beep();
    }, TONE_AGAIN_MS);
  }

  private stopTone(): void {
    if (this.toneTimer) clearTimeout(this.toneTimer);
    this.toneTimer = null;
    this.tone?.close();
    this.tone = null;
  }

  /**
   * Hang up a call still in progress, stop following the mic and unbind the
   * audio element.
   */
  dispose(): void {
    const status = this.getSnapshot().status;
    if (status === "connecting" || status === "connected") void this.disconnect();
    this.stopTone();
    for (const off of this.unsubscribeMic.splice(0)) off();
    this.micWatch.dispose();
    this.unbindAudio?.();
    this.unbindAudio = null;
  }

  private callbacks(): Partial<RTVIEventCallbacks> {
    return {
      onBotReady: () => {
        this.wasReady = true;
        this.set({ status: "connected" });
        this.setAgent("listening");
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
        this.micWatch.agentSpeaking(true);
        this.setAgent("speaking");
        this.emit("agentStarted");
      },
      onBotStoppedSpeaking: () => {
        this.micWatch.agentSpeaking(false);
        this.setAgent("listening");
        this.emit("agentStopped");
        this.agentStoppedForTone();
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
      onLocalAudioLevel: (level) => {
        this.mic.level(level);
        this.micWatch.level(level);
      },
      onDeviceError: (error) => {
        if (error.devices?.includes("mic")) this.micWatch.deviceError(error.type);
      },
      onTrackStopped: (track, participant) => {
        if (track.kind === "audio" && participant?.local) this.micWatch.setTrack(null);
      },
      onTrackStarted: (track, participant) => {
        if (track.kind !== "audio") return;
        if (participant?.local) {
          this.micWatch.setTrack(track);
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
      onAvailableMicsUpdated: (mics) => this.setDevices({ mics }),
      onAvailableSpeakersUpdated: (speakers) => this.setDevices({ speakers }),
      onMicUpdated: (mic) => this.setDevices({ micId: mic.deviceId }),
      onSpeakerUpdated: (speaker) => this.setDevices({ speakerId: speaker.deviceId }),
    };
  }
}
