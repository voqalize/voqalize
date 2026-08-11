/**
 * VoqalWebRTCTransport — WebSocket-signaled WebRTC transport for Pipecat.
 *
 * Signals directly to PyGato at `wss://.../signal/{session_id}`. JSON frames:
 *   browser → server:  { type: "handshake", token: "...", intent: "start" }
 *   server  → browser: { type: "handshake_ok" }
 *   browser → server:  { type: "offer", sdp: "..." }
 *   server  → browser: { type: "answer", sdp: "...", pc_id?: "..." }
 *   both directions:   { type: "ice_candidate", candidate: { candidate, sdpMid, sdpMLineIndex } }
 *
 * After WebRTC P2P is established the signaling WS may close with code 1000 —
 * this is NORMAL and does not affect the ongoing call. Media stays alive over
 * the peer connection; RTVI events ride the data channel labelled "chat".
 *
 * RTVI messages travel over the WebRTC data channel ("chat").
 */

import {
  type PipecatClientOptions,
  type TransportState,
  type Tracks,
  type Participant,
  RTVIMessage,
  Transport,
  TransportStartError,
} from "@pipecat-ai/client-js";
import { MicrophoneError, requestMicrophone } from "./microphone";

// ─── Internal types ────────────────────────────────────────────────────────

interface IceCandidate {
  candidate: string;
  sdpMid: string | null;
  sdpMLineIndex: number | null;
}

interface WsMessage {
  type: string;
  sdp?: string;
  pc_id?: string;
  candidate?: IceCandidate;
}

// Transceiver indices must match PyGato's server-side order in
// `pygato/src/pygato/webrtc.py`. Audio is index 0; video (index 1) is
// reserved sendrecv so a future revision can send video from PyGato.
const AUDIO_TRANSCEIVER_IDX = 0;

const KEEP_ALIVE_INTERVAL_MS = 1000;
const HANDSHAKE_TIMEOUT_MS = 10000;

function botParticipant(pcId: string | null): Participant {
  return { id: pcId ?? "bot", name: "bot", local: false };
}

// ─── Transport ─────────────────────────────────────────────────────────────

export interface VoqalWebRTCTransportOptions {
  iceServers?: RTCIceServer[];
  /**
   * Called once if the microphone permission prompt is still open after a
   * moment. Render something — a caller who missed the dialog otherwise sees
   * only "Connecting…" and has no reason to think the browser is waiting on
   * them.
   */
  onMicrophoneWaiting?: () => void;
  /** Override the permission-prompt deadline. Testing seam. */
  micPromptTimeoutMs?: number;
}

export interface VoqalConnectParams {
  /** WebSocket URL for the signaling endpoint (wss://...) */
  connection_url: string;
  /** RS256 JWT for the voice-runtime handshake (issued by controlplane). If omitted,
   *  token is extracted from the connection_url query string (?token=...). */
  token?: string;
}

export class VoqalWebRTCTransport extends Transport {
  private _iceServers: RTCIceServer[];
  private _onMicrophoneWaiting?: () => void;
  private _micPromptTimeoutMs?: number;
  private _micError: MicrophoneError | null = null;

  private _ws: WebSocket | null = null;
  private _pc: RTCPeerConnection | null = null;
  private _dc: RTCDataChannel | null = null;
  private _pcId: string | null = null;

  private _localStream: MediaStream | null = null;
  private _audioTrack: MediaStreamTrack | null = null;
  private _botAudioTrack: MediaStreamTrack | null = null;
  private _micEnabled = true;

  private _selectedMic: MediaDeviceInfo | Record<string, never> = {};
  private _selectedSpeaker: MediaDeviceInfo | Record<string, never> = {};
  private _deviceChangeListener: (() => void) | null = null;

  private _keepAliveTimer: ReturnType<typeof setInterval> | null = null;

  // Resolved when the data channel opens (= fully connected)
  private _connectResolve: (() => void) | null = null;
  private _connectReject: ((e: Error) => void) | null = null;

  // Tracks whether P2P is established — WS close after this is normal
  private _webrtcEstablished = false;

  // Pending handshake promise callbacks
  private _handshakeResolve: (() => void) | null = null;
  private _handshakeReject: ((e: Error) => void) | null = null;

  constructor(opts: VoqalWebRTCTransportOptions = {}) {
    super();
    this._iceServers = opts.iceServers ?? [];
    this._onMicrophoneWaiting = opts.onMicrophoneWaiting;
    this._micPromptTimeoutMs = opts.micPromptTimeoutMs;
  }

  /** Why there is no microphone, or `null` if there is one. */
  get microphoneError(): MicrophoneError | null {
    return this._micError;
  }

  // ─── Transport interface ─────────────────────────────────────────────────

  initialize(
    options: PipecatClientOptions,
    messageHandler: (ev: RTVIMessage) => void
  ): void {
    this._options = options;
    this._callbacks = options.callbacks ?? {};
    this._onMessage = messageHandler;
    this.state = "disconnected";
  }

  /**
   * Acquire the microphone and enumerate devices.
   *
   * **Deliberately never rejects**, and that is not politeness — it is the
   * difference between an error and a hang. `PipecatClient.connect()` awaits
   * this call *outside* its own try/catch, so a rejection here escapes as an
   * unhandled promise rejection and the promise `connect()` returned never
   * settles: the caller sits on "Connecting…" forever with nothing thrown to
   * catch. A microphone failure is stashed instead and raised from
   * {@link _connect}, which pipecat does guard, so `connect()` rejects with it.
   */
  async initDevices(): Promise<void> {
    this.state = "initializing";
    // Acquire mic first so enumerateDevices returns labeled device names.
    await this._acquireMic();
    await this._enumerateAndNotifyDevices();

    this._deviceChangeListener = () => {
      this._enumerateAndNotifyDevices().catch(console.warn);
    };
    navigator.mediaDevices.addEventListener("devicechange", this._deviceChangeListener);

    this.state = "initialized";
  }

  get state() {
    return this._state;
  }

  set state(s: TransportState) {
    if (this._state === s) return;
    this._state = s;
    this._callbacks?.onTransportStateChanged?.(s);
  }

  _validateConnectionParams(
    connectParams?: unknown
  ): VoqalConnectParams | undefined {
    if (!connectParams || typeof connectParams !== "object") return undefined;
    const p = connectParams as Record<string, unknown>;
    const url = (p["connection_url"] ?? p["connectionUrl"]) as
      | string
      | undefined;
    if (!url || typeof url !== "string") return undefined;
    const token = typeof p["token"] === "string" ? p["token"] : undefined;
    return { connection_url: url, token };
  }

  async _connect(
    connectParams?: VoqalConnectParams
  ): Promise<void> {
    const rawUrl = connectParams?.connection_url;
    if (!rawUrl) {
      this.state = "error";
      throw new TransportStartError();
    }

    // Ensure WebSocket scheme regardless of what the API returns
    const signalingUrl = rawUrl
      .replace(/^https:\/\//, "wss://")
      .replace(/^http:\/\//, "ws://");

    // Extract token — prefer explicit param, fall back to ?token= query string
    let token = connectParams?.token ?? "";
    if (!token) {
      try {
        const parsed = new URL(signalingUrl.replace(/^wss?:\/\//, "https://"));
        token = parsed.searchParams.get("token") ?? "";
      } catch {
        // ignore parse errors
      }
    }

    this.state = "connecting";

    if (!this._audioTrack) {
      // Last chance, synchronously this time: `initDevices` may have been
      // skipped (the transport was already past "disconnected"), and a
      // connect that proceeds without a microphone is a call the caller
      // cannot speak into.
      await this._acquireMic();
    }
    if (this._micError) {
      // The one place a microphone failure can be thrown and actually be
      // caught — pipecat guards `transport.connect()` but not `initDevices()`.
      this.state = "error";
      throw this._micError;
    }

    // 1. Open WebSocket signaling channel
    await this._openWebSocket(signalingUrl);

    // 2. JWT handshake before any WebRTC work
    await this._performHandshake(token);

    // 3. Create RTCPeerConnection + transceivers + data channel
    this._pc = new RTCPeerConnection({ iceServers: this._iceServers });
    this._setupPeerConnection();

    // 4. Attach local audio track
    if (this._audioTrack) {
      const txr = this._pc.getTransceivers()[AUDIO_TRANSCEIVER_IDX];
      await txr.sender.replaceTrack(this._audioTrack);
    }

    // 5. Create data channel (before offer so it's in the SDP)
    this._dc = this._pc.createDataChannel("chat", { ordered: true });
    this._setupDataChannel();

    // 6. Create SDP offer and send over WebSocket
    const offer = await this._pc.createOffer();
    await this._pc.setLocalDescription(offer);
    this._wsSend({ type: "offer", sdp: this._pc.localDescription!.sdp });

    // 7. Wait for data channel open (triggered after answer + ICE complete)
    await new Promise<void>((resolve, reject) => {
      this._connectResolve = resolve;
      this._connectReject = reject;
    });

    this._webrtcEstablished = true;
    this.state = "connected";
    this._callbacks?.onConnected?.();
    this._callbacks?.onBotConnected?.(botParticipant(this._pcId));
  }

  async _disconnect(): Promise<void> {
    this.state = "disconnecting";
    this._teardown();
    this.state = "disconnected";
    this._callbacks?.onDisconnected?.();
  }

  sendReadyMessage(): void {
    this.state = "ready";
    this.sendMessage(RTVIMessage.clientReady());
  }

  sendMessage(message: RTVIMessage): void {
    if (!this._dc || this._dc.readyState !== "open") return;
    this._dc.send(JSON.stringify(message));
  }

  // ─── Device management ───────────────────────────────────────────────────

  async getAllMics(): Promise<MediaDeviceInfo[]> {
    const devices = await navigator.mediaDevices.enumerateDevices();
    return devices.filter((d) => d.kind === "audioinput");
  }

  async getAllCams(): Promise<MediaDeviceInfo[]> {
    return [];
  }

  async getAllSpeakers(): Promise<MediaDeviceInfo[]> {
    const devices = await navigator.mediaDevices.enumerateDevices();
    return devices.filter((d) => d.kind === "audiooutput");
  }

  updateMic(micId: string): void {
    navigator.mediaDevices
      .getUserMedia({ audio: { deviceId: { exact: micId } } })
      .then(async (stream) => {
        const track = stream.getAudioTracks()[0];
        if (!track) return;
        if (this._pc) {
          const txr = this._pc.getTransceivers()[AUDIO_TRANSCEIVER_IDX];
          await txr.sender.replaceTrack(track);
        }
        this._audioTrack?.stop();
        this._audioTrack = track;

        const devices = await navigator.mediaDevices.enumerateDevices();
        const mic = devices.find(d => d.kind === "audioinput" && d.deviceId === micId);
        if (mic) {
          this._selectedMic = mic;
          this._callbacks?.onMicUpdated?.(mic);
        }
      })
      .catch(console.error);
  }

  updateCam(_camId: string): void {
    /* no video */
  }

  updateSpeaker(speakerId: string): void {
    navigator.mediaDevices.enumerateDevices().then(devices => {
      const speaker = devices.find(d => d.kind === "audiooutput" && d.deviceId === speakerId);
      if (speaker) {
        this._selectedSpeaker = speaker;
        this._callbacks?.onSpeakerUpdated?.(speaker);
      }
    }).catch(console.error);
  }

  get selectedMic(): MediaDeviceInfo | Record<string, never> {
    return this._selectedMic;
  }

  get selectedCam(): MediaDeviceInfo | Record<string, never> {
    return {};
  }

  get selectedSpeaker(): MediaDeviceInfo | Record<string, never> {
    return this._selectedSpeaker;
  }

  enableMic(enable: boolean): void {
    this._micEnabled = enable;
    if (this._audioTrack) this._audioTrack.enabled = enable;
    this._sendSignalling({
      type: "trackStatus",
      receiver_index: AUDIO_TRANSCEIVER_IDX,
      enabled: enable,
    });
  }

  enableCam(_enable: boolean): void {
    /* no video */
  }

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  enableScreenShare(_enable: boolean): void {
    /* not supported */
  }

  get isCamEnabled(): boolean {
    return false;
  }

  get isMicEnabled(): boolean {
    return this._micEnabled;
  }

  get isSharingScreen(): boolean {
    return false;
  }

  tracks(): Tracks {
    return {
      local: {
        audio: this._audioTrack ?? undefined,
      },
      bot: {
        audio: this._botAudioTrack ?? undefined,
      },
    };
  }

  // ─── Private helpers ─────────────────────────────────────────────────────

  private async _enumerateAndNotifyDevices(): Promise<void> {
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const mics = devices.filter(d => d.kind === "audioinput");
      const speakers = devices.filter(d => d.kind === "audiooutput");

      this._callbacks?.onAvailableMicsUpdated?.(mics);
      this._callbacks?.onAvailableSpeakersUpdated?.(speakers);

      // Set initial mic if not yet chosen
      if (!("deviceId" in this._selectedMic)) {
        const defaultMic = mics.find(m => m.deviceId === "default") ?? mics[0];
        if (defaultMic) {
          this._selectedMic = defaultMic;
          this._callbacks?.onMicUpdated?.(defaultMic);
        }
      }

      // Set initial speaker if not yet chosen
      if (!("deviceId" in this._selectedSpeaker)) {
        const defaultSpeaker = speakers.find(s => s.deviceId === "default") ?? speakers[0];
        if (defaultSpeaker) {
          this._selectedSpeaker = defaultSpeaker;
          this._callbacks?.onSpeakerUpdated?.(defaultSpeaker);
        }
      }
    } catch (err) {
      console.warn("[VoqalWebRTCTransport] Device enumeration failed:", err);
    }
  }

  private async _acquireMic(): Promise<void> {
    const result = await requestMicrophone({
      onWaiting: this._onMicrophoneWaiting,
      timeoutMs: this._micPromptTimeoutMs,
    });

    if (result instanceof MicrophoneError) {
      // Recorded, not thrown — see `initDevices`. Recorded rather than logged,
      // which is what it used to be: a `console.warn` meant the call went on to
      // connect with no audio track at all, so the agent greeted a caller whose
      // every word went nowhere and the UI said "Listening…".
      this._micError = result;
      this._audioTrack = null;
      return;
    }

    this._micError = null;
    this._localStream = result;
    this._audioTrack = result.getAudioTracks()[0] ?? null;
  }

  private _openWebSocket(url: string): Promise<void> {
    return new Promise<void>((resolve, reject) => {
      const ws = new WebSocket(url);
      this._ws = ws;

      const onOpen = () => {
        ws.removeEventListener("error", onError);
        resolve();
      };
      const onError = () => {
        reject(new Error("signaling WebSocket failed to open"));
      };

      ws.addEventListener("open", onOpen, { once: true });
      ws.addEventListener("error", onError, { once: true });
      ws.onmessage = (evt) => this._handleWsMessage(evt.data as string);
      ws.onclose = (evt) => this._handleWsClose(evt.code, evt.reason);
    });
  }

  /** Send the JWT handshake frame and wait for handshake_ok. */
  private _performHandshake(token: string, intent: "start" | "resume" = "start"): Promise<void> {
    return new Promise<void>((resolve, reject) => {
      this._handshakeResolve = resolve;
      this._handshakeReject = reject;

      const timer = setTimeout(() => {
        this._handshakeResolve = null;
        this._handshakeReject = null;
        reject(new Error("handshake timeout"));
      }, HANDSHAKE_TIMEOUT_MS);

      const originalResolve = resolve;
      this._handshakeResolve = () => {
        clearTimeout(timer);
        this._handshakeResolve = null;
        this._handshakeReject = null;
        originalResolve();
      };
      this._handshakeReject = (e: Error) => {
        clearTimeout(timer);
        this._handshakeResolve = null;
        this._handshakeReject = null;
        reject(e);
      };

      this._wsSend({ type: "handshake", token, intent });
    });
  }

  private _setupPeerConnection(): void {
    if (!this._pc) return;

    this._pc.addTransceiver("audio", { direction: "sendrecv" });
    this._pc.addTransceiver("video", { direction: "sendrecv" });

    this._pc.onicecandidate = (evt) => {
      if (!evt.candidate) return;
      this._wsSend({
        type: "ice_candidate",
        candidate: {
          candidate: evt.candidate.candidate,
          sdpMid: evt.candidate.sdpMid,
          sdpMLineIndex: evt.candidate.sdpMLineIndex,
        },
      });
    };

    this._pc.addEventListener("track", (evt: RTCTrackEvent) => {
      const track = evt.track;
      if (track.kind !== "audio") return;
      this._botAudioTrack = track;
      track.addEventListener("unmute", () => {
        this._callbacks?.onTrackStarted?.(track);
      });
      track.addEventListener("mute", () => {
        this._callbacks?.onTrackStopped?.(track);
      });
      track.addEventListener("ended", () => {
        this._callbacks?.onTrackStopped?.(track);
        this._botAudioTrack = null;
      });
    });

    this._pc.addEventListener("iceconnectionstatechange", () => {
      if (!this._pc) return;
      const s = this._pc.iceConnectionState;
      if (s === "failed") {
        if (this._connectReject) {
          this.state = "error";
          this._connectReject(new Error("ICE connection failed"));
          this._connectReject = null;
          this._connectResolve = null;
        } else if (this._state !== "disconnected" && this._state !== "disconnecting") {
          this.state = "disconnected";
          this._callbacks?.onDisconnected?.();
        }
      }
    });
  }

  private _setupDataChannel(): void {
    if (!this._dc) return;

    this._dc.addEventListener("open", () => {
      this._maxMessageSize = this._pc?.sctp?.maxMessageSize ?? 64 * 1024;

      this._sendSignalling({
        type: "trackStatus",
        receiver_index: AUDIO_TRANSCEIVER_IDX,
        enabled: this._micEnabled,
      });

      this._keepAliveTimer = setInterval(() => {
        if (this._dc?.readyState === "open") {
          this._dc.send("ping: " + Date.now());
        }
      }, KEEP_ALIVE_INTERVAL_MS);

      // Mark P2P established BEFORE resolving the connect promise so that
      // any WS close event (code 1000) fired on the same tick is handled
      // correctly in _handleWsClose instead of being treated as a drop.
      this._webrtcEstablished = true;
      this._connectResolve?.();
      this._connectResolve = null;
      this._connectReject = null;
    });

    this._dc.addEventListener("message", (evt: MessageEvent) => {
      this._handleDataChannelMessage(evt.data as string);
    });

    this._dc.addEventListener("close", () => {
      if (this._keepAliveTimer !== null) {
        clearInterval(this._keepAliveTimer);
        this._keepAliveTimer = null;
      }
      if (!this._connectReject && this._state !== "disconnected" && this._state !== "disconnecting") {
        this.state = "disconnected";
        this._callbacks?.onDisconnected?.();
      }
    });

    this._dc.addEventListener("error", () => {
      if (this._connectReject) {
        this.state = "error";
        this._connectReject(new Error("data channel error"));
        this._connectReject = null;
        this._connectResolve = null;
      }
    });
  }

  private _handleWsMessage(data: string): void {
    let msg: WsMessage;
    try {
      msg = JSON.parse(data) as WsMessage;
    } catch {
      return;
    }

    if (msg.type === "handshake_ok") {
      this._handshakeResolve?.();
      return;
    }

    // Handshake error responses arrive as close events, not messages.
    // Any unexpected message during handshake phase is ignored.
    if (this._handshakeResolve) return;

    if (msg.type === "answer" && msg.sdp) {
      this._pcId = msg.pc_id ?? null;
      this._pc
        ?.setRemoteDescription({ type: "answer", sdp: msg.sdp })
        .catch(console.error);
    } else if (msg.type === "ice_candidate" && msg.candidate) {
      this._pc
        ?.addIceCandidate(
          new RTCIceCandidate({
            candidate: msg.candidate.candidate,
            sdpMid: msg.candidate.sdpMid,
            sdpMLineIndex: msg.candidate.sdpMLineIndex,
          })
        )
        .catch(console.error);
    }
  }

  private _handleDataChannelMessage(data: string): void {
    if (typeof data === "string" && data.startsWith("ping:")) return;

    let msg: Record<string, unknown>;
    try {
      msg = JSON.parse(data) as Record<string, unknown>;
    } catch {
      return;
    }

    if (msg["type"] === "signalling") {
      const inner = (msg["message"] as Record<string, unknown>)?.["type"];
      if (inner === "peerLeft") {
        this._callbacks?.onBotDisconnected?.(botParticipant(this._pcId));
        if (this._state !== "disconnected" && this._state !== "disconnecting") {
          this.state = "disconnected";
          this._callbacks?.onDisconnected?.();
        }
      }
    } else if (msg["label"] === "rtvi-ai") {
      this._onMessage({
        id: msg["id"],
        type: msg["type"],
        data: msg["data"],
      } as RTVIMessage);
    }
  }

  private _handleWsClose(code: number, reason: string): void {
    // During handshake phase, a close means the session was rejected.
    if (this._handshakeReject) {
      const msg = code === 4001
        ? "jwt-expired: token has expired"
        : code === 4003
          ? "jwt-invalid: token is invalid"
          : code === 4404
            ? "session not found"
            : code === 4409
              ? "session already in progress"
              : `signaling WebSocket closed (${code}: ${reason})`;
      this._handshakeReject(new Error(msg));
      return;
    }

    this._ws = null;

    // After the handshake, code 1000 is the normal "webrtc-established" close.
    // Any other close code before the data channel opens means the session failed
    // (e.g. 4503 = webrtc-failed-retry from PyGato) — reject the connect promise.
    if (code !== 1000 && code !== 1006 && this._connectReject) {
      const msg = `signaling WebSocket closed (${code}: ${reason})`;
      this.state = "error";
      this._connectReject(new Error(msg));
      this._connectReject = null;
      this._connectResolve = null;
    }
  }

  private _wsSend(msg: object): void {
    if (this._ws?.readyState === WebSocket.OPEN) {
      this._ws.send(JSON.stringify(msg));
    }
  }

  private _sendSignalling(message: object): void {
    if (!this._dc || this._dc.readyState !== "open") return;
    this._dc.send(JSON.stringify({ type: "signalling", message }));
  }

  private _teardown(): void {
    if (this._deviceChangeListener) {
      navigator.mediaDevices.removeEventListener("devicechange", this._deviceChangeListener);
      this._deviceChangeListener = null;
    }
    this._selectedMic = {};
    this._selectedSpeaker = {};
    if (this._keepAliveTimer !== null) {
      clearInterval(this._keepAliveTimer);
      this._keepAliveTimer = null;
    }
    this._handshakeResolve = null;
    this._handshakeReject = null;
    this._webrtcEstablished = false;
    try {
      this._dc?.close();
    } catch {
      /* ignore */
    }
    this._dc = null;
    try {
      this._pc?.close();
    } catch {
      /* ignore */
    }
    this._pc = null;
    try {
      this._ws?.close();
    } catch {
      /* ignore */
    }
    this._ws = null;
    this._localStream?.getTracks().forEach((t) => t.stop());
    this._localStream = null;
    this._audioTrack = null;
    this._botAudioTrack = null;
    this._connectResolve = null;
    this._connectReject = null;
  }
}
