import type { RTVIEventCallbacks } from "@pipecat-ai/client-js";
import { describe, expect, it, vi } from "vitest";
import { CaptionsController } from "../src/controllers/captions.js";
import { bindCaptions } from "../src/internal.js";
import {
  type ClientLike,
  type MediaManagerLike,
  type SessionOptions,
  WidgetSession,
  mintSession,
  withRealHeaders,
} from "../src/session/adapter.js";

type Callbacks = Partial<RTVIEventCallbacks>;

function deferred<T = void>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

class FakeClient implements ClientLike {
  sent: { type: string; data: unknown }[] = [];
  connectedWith: unknown;
  micEnabled: boolean[] = [];
  init = deferred();
  connectResult = deferred<unknown>();
  disconnect = vi.fn(() => Promise.resolve());
  updateMic = vi.fn();
  updateSpeaker = vi.fn();
  constructor(readonly cb: Callbacks) {}
  initDevices() {
    return this.init.promise;
  }
  connect(params?: unknown) {
    this.connectedWith = params;
    return this.connectResult.promise;
  }
  enableMic(enable: boolean) {
    this.micEnabled.push(enable);
  }
  sendClientMessage(type: string, data?: unknown) {
    this.sent.push({ type, data });
  }
}

const SESSION = {
  webrtc_request_params: { endpoint: "https://example.com/offer", headers: { "X-Session": "s" } },
  session_id: "sess_example",
};

function setup(options: SessionOptions = {}) {
  let client!: FakeClient;
  const media: MediaManagerLike = { instant: false, bindOutputElement: vi.fn(() => () => {}) };
  const session = new WidgetSession({
    createClient: ({ callbacks }) => (client = new FakeClient(callbacks)),
    createMediaManager: () => media,
    isIOS: false,
    canPickSpeaker: true,
    permissions: { query: () => new Promise(() => {}) },
    ...options,
  });
  return { session, client, media, cb: () => client.cb };
}

const micStates = (c: FakeClient) => c.sent.filter((m) => m.type === "mic_state").map((m) => m.data);
const tick = () => new Promise((r) => setTimeout(r, 0));

describe("instant start", () => {
  it("connects without waiting for the mic, and fetches the session meanwhile", async () => {
    const { session, client, media } = setup();
    const fetchSession = vi.fn(() => Promise.resolve(SESSION));
    const done = session.connect(fetchSession);
    expect(media.instant).toBe(true);
    expect(fetchSession).toHaveBeenCalled();
    client.init.resolve();
    await tick();
    expect(client.connectedWith).toBeDefined();
    expect(session.mic.getSnapshot().state).toBe("asking");
    client.connectResult.resolve({});
    await done;
    expect(session.getSnapshot()).toMatchObject({ status: "connected", sessionId: "sess_example" });
  });

  it("waits for the mic before fetching the session with instant start off", async () => {
    const { session, client, media } = setup({ instantStart: false });
    const fetchSession = vi.fn(() => Promise.resolve(SESSION));
    void session.connect(fetchSession);
    expect(media.instant).toBe(false);
    await tick();
    expect(fetchSession).not.toHaveBeenCalled();
    client.init.resolve();
    await tick();
    expect(fetchSession).toHaveBeenCalled();
  });

  it("is off on iOS unless the library flag allows it", () => {
    expect(setup({ isIOS: true }).session.instant).toBe(false);
    expect(setup({ isIOS: true, instantStartOnIOS: true }).session.instant).toBe(true);
    expect(setup({ isIOS: false }).session.instant).toBe(true);
  });

  it("hands the transport real Headers", async () => {
    const { session, client } = setup();
    void session.connect(SESSION);
    client.init.resolve();
    await tick();
    const params = client.connectedWith as typeof SESSION & { webrtc_request_params: { headers: Headers } };
    expect(params.webrtc_request_params.headers).toBeInstanceOf(Headers);
    expect(params.webrtc_request_params.headers.get("x-session")).toBe("s");
  });
});

describe("mic_state to gato", () => {
  it("sends once when the agent is ready, then on every change, never twice the same", async () => {
    const { session, client, cb } = setup({ now: () => 0 });
    void session.connect(SESSION);
    client.init.resolve();
    await tick();
    expect(micStates(client)).toEqual([]);
    cb().onBotReady?.({} as never);
    expect(micStates(client)).toEqual([{ state: "asking", hint: false }]);
    cb().onTrackStarted?.({ kind: "audio" } as MediaStreamTrack, { id: "local", name: "", local: true });
    session.setMuted(true);
    session.setMuted(true);
    session.setMuted(false);
    expect(micStates(client)).toEqual([
      { state: "asking", hint: false },
      { state: "live", hint: false },
      { state: "muted", hint: false },
      { state: "live", hint: false },
    ]);
    expect(client.micEnabled).toEqual([false, false, true]);
  });

  it("sends the device errors as blocked and missing", async () => {
    const { session, client, cb } = setup();
    void session.connect(SESSION);
    client.init.resolve();
    cb().onBotReady?.({} as never);
    cb().onDeviceError?.({ devices: ["mic"], type: "permissions" } as never);
    cb().onDeviceError?.({ devices: ["cam"], type: "not-found" } as never);
    cb().onDeviceError?.({ devices: ["mic"], type: "in-use" } as never);
    expect(micStates(client)).toEqual([
      { state: "asking", hint: false },
      { state: "blocked", hint: false },
      { state: "missing", hint: false },
    ]);
  });

  it("sends the silence hint as it shows", async () => {
    let t = 0;
    const { session, client, cb } = setup({ now: () => t });
    void session.connect(SESSION);
    client.init.resolve();
    cb().onBotReady?.({} as never);
    cb().onTrackStarted?.({ kind: "audio" } as MediaStreamTrack, { id: "local", name: "", local: true });
    for (let i = 0; i < 200; i++) {
      cb().onLocalAudioLevel?.(0);
      t += 100;
    }
    expect(micStates(client).at(-1)).toEqual({ state: "live", hint: true });
  });

  it("picks the mic up when the visitor allows it after blocking it", async () => {
    let fire!: () => void;
    const status = {
      state: "denied" as PermissionState,
      addEventListener: (_: string, l: () => void) => (fire = l),
      removeEventListener() {},
    };
    const { session, client, cb } = setup({
      permissions: { query: () => Promise.resolve(status as unknown as PermissionStatus) },
    });
    void session.connect(SESSION);
    client.init.resolve();
    cb().onDeviceError?.({ devices: ["mic"], type: "permissions" } as never);
    await tick();
    status.state = "granted";
    fire();
    expect(session.mic.getSnapshot().state).toBe("asking");
    expect(client.micEnabled).toEqual([true]);
  });
});

describe("agent state and words", () => {
  it("derives the agent's state from the client's events", async () => {
    const { session, client, cb } = setup();
    void session.connect(SESSION);
    client.init.resolve();
    cb().onBotReady?.({} as never);
    expect(session.getSnapshot().agent).toBe("listening");
    cb().onBotLlmStarted?.();
    expect(session.getSnapshot().agent).toBe("thinking");
    cb().onBotStartedSpeaking?.();
    expect(session.getSnapshot().agent).toBe("speaking");
    cb().onUserStartedSpeaking?.();
    expect(session.getSnapshot().agent).toBe("listening");
    cb().onBotStoppedSpeaking?.();
    expect(session.getSnapshot().agent).toBe("listening");
  });

  it("feeds captions from sentences and words as they play", () => {
    const { session, cb } = setup();
    const captions = new CaptionsController({ showUser: true, setTimeout: () => 0, clearTimeout: () => {} });
    const unbind = bindCaptions(session, captions);
    cb().onBotStartedSpeaking?.();
    cb().onBotOutput?.({ text: "Hello there.", spoken_status: "new", aggregated_by: "sentence" });
    cb().onBotOutput?.({ text: "Hello", spoken_status: "in-progress", aggregated_by: "word" });
    cb().onBotTtsText?.({ text: "Hello" });
    const words = captions.getSnapshot().lines[0]?.words ?? [];
    expect(words.map((w) => [w.text, w.spoken])).toEqual([
      ["Hello", true],
      ["there.", false],
    ]);
    cb().onUserTranscript?.({ text: "hi", final: true, timestamp: "", user_id: "" });
    expect(session.getSnapshot().user).toEqual({ text: "hi", final: true });
    expect(captions.getSnapshot().user).toBe("hi");
    unbind();
    cb().onBotTtsText?.({ text: "there." });
    expect(captions.getSnapshot().lines[0]?.words[1]?.spoken).toBe(false);
  });

  it("plays the agent's track on the bound element", async () => {
    const audio = document.createElement("audio");
    // The test DOM keeps only its own MediaStream in srcObject; a plain slot will do.
    let src: unknown = null;
    Object.defineProperty(audio, "srcObject", { get: () => src, set: (v) => (src = v), configurable: true });
    const play = vi.spyOn(audio, "play").mockImplementation(() => Promise.resolve());
    const { session, client, cb, media } = setup({ audioElement: audio });
    const MS = globalThis.MediaStream;
    globalThis.MediaStream = class {
      constructor(readonly tracks: unknown[]) {}
    } as unknown as typeof MediaStream;
    try {
      void session.connect(SESSION);
      client.init.resolve();
      expect(media.bindOutputElement).toHaveBeenCalledWith(audio);
      cb().onTrackStarted?.({ kind: "audio" } as MediaStreamTrack, { id: "bot", name: "", local: false });
      expect(audio.srcObject).toBeTruthy();
      expect(play).toHaveBeenCalled();
      expect(session.mic.getSnapshot().state).toBe("asking");
    } finally {
      globalThis.MediaStream = MS;
    }
  });
});

describe("devices", () => {
  it("tracks the lists and the selection", () => {
    const { session, client, cb } = setup();
    const mic = { deviceId: "m1", kind: "audioinput", label: "Mic", groupId: "" } as MediaDeviceInfo;
    cb().onAvailableMicsUpdated?.([mic]);
    cb().onMicUpdated?.(mic);
    expect(session.getSnapshot().devices).toMatchObject({ mics: [mic], micId: "m1", canPickSpeaker: true });
    session.selectMic("m2");
    expect(client.updateMic).toHaveBeenCalledWith("m2");
    session.selectSpeaker("s1");
    expect(client.updateSpeaker).toHaveBeenCalledWith("s1");
  });

  it("offers no speaker picker where setSinkId is missing", () => {
    const { session, client } = setup({ canPickSpeaker: false });
    expect(session.getSnapshot().devices.canPickSpeaker).toBe(false);
    session.selectSpeaker("s1");
    expect(client.updateSpeaker).not.toHaveBeenCalled();
  });
});

describe("end reason", () => {
  it("is the visitor hanging up", async () => {
    const { session, client } = setup();
    void session.connect(SESSION);
    client.init.resolve();
    await session.disconnect();
    client.cb.onDisconnected?.();
    expect(session.getSnapshot()).toMatchObject({ status: "ended", end: { by: "user", reason: "hung_up" } });
    expect(client.disconnect).toHaveBeenCalled();
  });

  it("is mic_denied when the far end closes a call whose mic never went live", async () => {
    const { session, client, cb } = setup();
    void session.connect(SESSION);
    client.init.resolve();
    cb().onBotReady?.({} as never);
    cb().onDeviceError?.({ devices: ["mic"], type: "permissions" } as never);
    cb().onDisconnected?.();
    expect(session.getSnapshot().end).toEqual({ by: "agent", reason: "mic_denied" });
  });

  it("is the agent ending the call otherwise", async () => {
    const { session, client, cb } = setup();
    void session.connect(SESSION);
    client.init.resolve();
    cb().onBotReady?.({} as never);
    cb().onTrackStarted?.({ kind: "audio" } as MediaStreamTrack, { id: "local", name: "", local: true });
    cb().onDisconnected?.();
    expect(session.getSnapshot().end).toEqual({ by: "agent", reason: "ended" });
  });

  it("is an error when the connect fails", async () => {
    const { session, client } = setup();
    const done = session.connect(() => Promise.reject(new Error("sessions.connect answered 403")));
    client.init.resolve();
    await done;
    expect(session.getSnapshot()).toMatchObject({
      status: "ended",
      end: { by: "error", reason: "connect_failed", message: "sessions.connect answered 403" },
    });
    expect(client.disconnect).toHaveBeenCalled();
  });

  it("is a failed connect, not mic_denied, when the transport gives up before the agent is ready", async () => {
    // Seen live: a blocked mic and an offer the browser could not send; the
    // transport retried, closed, and the card said nobody allowed the mic.
    const { session, client, cb } = setup();
    void session.connect(SESSION);
    client.init.resolve();
    cb().onDeviceError?.({ devices: ["mic"], type: "permissions" } as never);
    cb().onDisconnected?.();
    expect(session.getSnapshot().end).toMatchObject({ by: "error", reason: "connect_failed" });
  });

  it("starts clean on the next call", async () => {
    const { session, client, cb } = setup();
    void session.connect(SESSION);
    client.init.resolve();
    cb().onBotReady?.({} as never);
    await session.disconnect();
    void session.connect(SESSION);
    expect(session.getSnapshot()).toMatchObject({ status: "connecting", end: undefined });
    expect(session.mic.getSnapshot().everLive).toBe(false);
  });
});

describe("mintSession", () => {
  it("posts the agent and init with the publishable key", async () => {
    const fetch = vi.fn(async () => new Response(JSON.stringify(SESSION), { status: 200 }));
    const out = await mintSession({
      agent: "agent_example",
      key: "pk_example",
      init: { greeting: "Hi" },
      apiBase: "https://api.example.com/v1",
      fetch: fetch as unknown as typeof globalThis.fetch,
    });
    expect(out).toEqual(SESSION);
    const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("https://api.example.com/v1/sessions.connect");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer pk_example");
    expect(JSON.parse(init.body as string)).toEqual({ agent_id: "agent_example", init: { greeting: "Hi" } });
  });

  it("throws with the status when the API refuses", async () => {
    const fetch = vi.fn(async () => new Response("nope", { status: 403 }));
    await expect(
      mintSession({ agent: "a", key: "pk_x", fetch: fetch as unknown as typeof globalThis.fetch }),
    ).rejects.toThrow("403");
  });
});

describe("withRealHeaders", () => {
  it("leaves an answer without request params alone", () => {
    const r = { session_id: "x" };
    expect(withRealHeaders(r)).toBe(r);
  });
});
