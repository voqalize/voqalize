/**
 * The browser-side probe for the live suite, injected with `addInitScript`
 * before the page's own bundle. It must be self-contained: Playwright
 * stringifies the function, so it cannot close over imports.
 *
 * - A microphone the test drives, that still respects the permission:
 *   `getUserMedia` calls the browser's own first, so a refused permission is
 *   refused, and only an allowed call gets the synthetic track. That track
 *   mixes the real (fake-device) input, a noise bed, with clips the test
 *   plays on command, so speech is an awaited step and not a race.
 * - A tap on the `chat` data channel, both directions: the RTVI wire.
 * - A count of offers and their m-lines, so a test can tell whether a change
 *   renegotiated the connection.
 * - `getStats()` samples every 100 ms: the first inbound audio energy is the
 *   moment the agent's audio reached the browser.
 * - Every oscillator started, with its pitch: the widget's attention tone is
 *   the only thing on the page that makes one.
 */

export interface ProbeEvent {
  /** Milliseconds since the probe was installed. */
  t: number;
  /** `in` from the runtime, `out` from the browser, `mic`, `pc`, `net` and `ui` local. */
  dir: "in" | "out" | "mic" | "pc" | "net" | "ui" | "tone";
  type: string;
  data?: unknown;
}

export interface ProbeStat {
  t: number;
  inEnergy: number;
  outEnergy: number;
  inBytes: number;
  outBytes: number;
}

export interface ProbeApi {
  events: ProbeEvent[];
  stats: ProbeStat[];
  now(): number;
  push(dir: ProbeEvent["dir"], type: string, data?: unknown): void;
  /** Play a base64 WAV into the synthetic mic; resolves when it has played. */
  speak(base64: string, label: string): Promise<{ startedAt: number; endedAt: number }>;
  /** The session id from the `sessions.connect` answer. */
  sessionId?: string;
}

declare global {
  interface Window {
    __vqlE2E: ProbeApi;
  }
}

export function installProbe(): void {
  const t0 = performance.now();
  const events: ProbeEvent[] = [];
  const stats: ProbeStat[] = [];
  const pcs: RTCPeerConnection[] = [];
  const now = () => Math.round(performance.now() - t0);
  const push = (dir: ProbeEvent["dir"], type: string, data?: unknown) => {
    events.push({ t: now(), dir, type, data });
  };

  let ctx: AudioContext | null = null;
  let dest: MediaStreamAudioDestinationNode | null = null;
  const ensureMix = (): MediaStreamAudioDestinationNode => {
    if (!ctx || !dest) {
      ctx = new AudioContext({ sampleRate: 48000 });
      dest = ctx.createMediaStreamDestination();
      const keepAlive = ctx.createConstantSource();
      keepAlive.offset.value = 0;
      keepAlive.connect(dest);
      keepAlive.start();
    }
    if (ctx.state === "suspended") void ctx.resume();
    return dest;
  };

  const realStart = OscillatorNode.prototype.start;
  OscillatorNode.prototype.start = function (this: OscillatorNode, when?: number) {
    push("tone", "oscillator-start", { frequency: this.frequency.value });
    return realStart.call(this, when);
  };

  const realGetUserMedia = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
  navigator.mediaDevices.getUserMedia = async (constraints?: MediaStreamConstraints) => {
    if (!constraints?.audio) return realGetUserMedia(constraints);
    push("mic", "getusermedia", { constraints: JSON.parse(JSON.stringify(constraints)) });
    let real: MediaStream;
    try {
      real = await realGetUserMedia(constraints);
    } catch (error) {
      push("mic", "getusermedia-error", { name: (error as Error).name, message: (error as Error).message });
      throw error;
    }
    const destination = ensureMix();
    const bed = (ctx as AudioContext).createMediaStreamSource(real);
    bed.connect(destination);
    push("mic", "getusermedia-ok", { label: real.getAudioTracks()[0]?.label });
    return new MediaStream(destination.stream.getAudioTracks().map((t) => t.clone()));
  };

  const speak = async (base64: string, label: string) => {
    const destination = ensureMix();
    const audioCtx = ctx as AudioContext;
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const buffer = await audioCtx.decodeAudioData(bytes.buffer);
    const source = audioCtx.createBufferSource();
    source.buffer = buffer;
    source.connect(destination);
    const startedAt = now();
    push("mic", "speak-start", { label, seconds: buffer.duration });
    source.start();
    return new Promise<{ startedAt: number; endedAt: number }>((resolve) => {
      source.onended = () => {
        source.disconnect();
        push("mic", "speak-end", { label });
        resolve({ startedAt, endedAt: now() });
      };
    });
  };

  const record = (dir: "in" | "out", data: unknown) => {
    if (typeof data !== "string" || data.startsWith("ping")) return;
    let message: Record<string, unknown>;
    try {
      message = JSON.parse(data) as Record<string, unknown>;
    } catch {
      return;
    }
    if (message["label"] !== "rtvi-ai") {
      push(dir, `signalling:${String(message["type"] ?? "?")}`, message);
      return;
    }
    push(dir, String(message["type"]), message["data"]);
  };

  const tap = (channel: RTCDataChannel) => {
    push("pc", "datachannel", { label: channel.label });
    channel.addEventListener("message", (e) => record("in", (e as MessageEvent).data));
    const send = channel.send.bind(channel);
    channel.send = ((payload: string) => {
      record("out", payload);
      return send(payload);
    }) as RTCDataChannel["send"];
  };

  const mLines = (sdp: string | undefined) => (sdp ?? "").split("\n").filter((l) => l.startsWith("m=")).map((l) => l.trim());
  const watch = (pc: RTCPeerConnection) => {
    if (pcs.includes(pc)) return;
    pcs.push(pc);
    push("pc", "peerconnection", { index: pcs.length - 1 });
    pc.addEventListener("connectionstatechange", () => push("pc", "connectionstate", pc.connectionState));
    pc.addEventListener("track", (e) => push("pc", "track", { kind: (e as RTCTrackEvent).track.kind }));
    pc.addEventListener("datachannel", (e) => tap((e as RTCDataChannelEvent).channel));
  };
  const proto = RTCPeerConnection.prototype;
  const createDataChannel = proto.createDataChannel;
  proto.createDataChannel = function (this: RTCPeerConnection, ...args: Parameters<RTCPeerConnection["createDataChannel"]>) {
    watch(this);
    const channel = createDataChannel.apply(this, args);
    tap(channel);
    return channel;
  };
  const createOffer = proto.createOffer as (this: RTCPeerConnection, ...a: unknown[]) => Promise<RTCSessionDescriptionInit>;
  (proto as unknown as { createOffer: unknown }).createOffer = async function (this: RTCPeerConnection, ...args: unknown[]) {
    watch(this);
    const offer = await createOffer.apply(this, args);
    push("pc", "create-offer", { mlines: mLines(offer.sdp) });
    return offer;
  };
  const setLocal = proto.setLocalDescription as (this: RTCPeerConnection, d?: RTCLocalSessionDescriptionInit) => Promise<void>;
  (proto as unknown as { setLocalDescription: unknown }).setLocalDescription = async function (
    this: RTCPeerConnection,
    d?: RTCLocalSessionDescriptionInit,
  ) {
    watch(this);
    await setLocal.call(this, d);
    const local = this.localDescription;
    push("pc", "set-local", { type: local?.type, mlines: mLines(local?.sdp) });
  };
  const setRemote = proto.setRemoteDescription as (this: RTCPeerConnection, d: RTCSessionDescriptionInit) => Promise<void>;
  proto.setRemoteDescription = async function (this: RTCPeerConnection, d: RTCSessionDescriptionInit) {
    await setRemote.call(this, d);
    push("pc", "set-remote", { type: d.type, mlines: mLines(d.sdp) });
  };
  const replaceTrack = RTCRtpSender.prototype.replaceTrack;
  RTCRtpSender.prototype.replaceTrack = async function (this: RTCRtpSender, track: MediaStreamTrack | null) {
    push("pc", "replace-track", { kind: track?.kind ?? null });
    return replaceTrack.call(this, track);
  };

  // The requests, by method and path only: never a header or a body.
  const realFetch = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const method = (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
    let path = url;
    try {
      path = new URL(url, location.href).pathname;
    } catch {
      // keep it as it came
    }
    let response: Response;
    try {
      response = await realFetch(input, init);
    } catch (error) {
      push("net", "fetch", { method, path, error: String(error) });
      throw error;
    }
    push("net", "fetch", { method, path, status: response.status });
    if (path.endsWith("/sessions.connect") && response.ok) {
      void response
        .clone()
        .json()
        .then((body: { session_id?: string }) => {
          if (body.session_id) api.sessionId = body.session_id;
        })
        .catch(() => {});
    }
    return response;
  };

  document.addEventListener("click", () => push("ui", "click"), { capture: true });
  void navigator.permissions
    ?.query({ name: "microphone" as PermissionName })
    .then((status) => {
      push("mic", "permission", status.state);
      status.addEventListener("change", () => push("mic", "permission", status.state));
    })
    .catch(() => {});

  setInterval(() => {
    for (const pc of pcs) {
      void pc
        .getStats()
        .then((report) => {
          const s: ProbeStat = { t: now(), inEnergy: 0, outEnergy: 0, inBytes: 0, outBytes: 0 };
          report.forEach((e: Record<string, unknown>) => {
            if (e["kind"] !== "audio") return;
            if (e["type"] === "media-source") s.outEnergy = Number(e["totalAudioEnergy"] ?? 0);
            else if (e["type"] === "inbound-rtp") {
              s.inEnergy = Number(e["totalAudioEnergy"] ?? 0);
              s.inBytes = Number(e["bytesReceived"] ?? 0);
            } else if (e["type"] === "outbound-rtp") s.outBytes = Number(e["bytesSent"] ?? 0);
          });
          stats.push(s);
        })
        .catch(() => undefined);
    }
  }, 100);

  const api: ProbeApi = { events, stats, now, push, speak };
  window.__vqlE2E = api;
}
