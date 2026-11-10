import type { RTVIEventCallbacks } from "@pipecat-ai/client-js";
import type { MicHint, MicState } from "@voqalize/client-transport";
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
import { TONE_AGAIN_MS, type TonePlayer } from "../src/session/tone.js";

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


/** A media manager whose mic state and hint the test sets. */
class FakeMedia implements MediaManagerLike {
  micState: MicState = "idle";
  micHint: MicHint = "none";
  bindOutputElement = vi.fn((_el: HTMLAudioElement) => () => {});
  updateMic?: (id: string) => Promise<void>;
  updateSpeaker?: (id: string) => Promise<void>;
  private stateListeners = new Set<(s: MicState) => void>();
  private hintListeners = new Set<(h: MicHint) => void>();
  constructor(readonly waitForDevices: boolean) {}
  onMicStateChange(l: (s: MicState) => void) {
    this.stateListeners.add(l);
    return () => this.stateListeners.delete(l);
  }
  onMicHintChange(l: (h: MicHint) => void) {
    this.hintListeners.add(l);
    return () => this.hintListeners.delete(l);
  }
  get listening() {
    return this.stateListeners.size + this.hintListeners.size;
  }
  set(state: MicState, hint: MicHint = this.micHint) {
    if (state !== this.micState) {
      this.micState = state;
      for (const l of this.stateListeners) l(state);
    }
    if (hint !== this.micHint) {
      this.micHint = hint;
      for (const l of this.hintListeners) l(hint);
    }
  }
}

const SESSION = {
  webrtc_request_params: { endpoint: "https://example.com/offer", headers: { "X-Session": "s" } },
  session_id: "sess_example",
};

function setup(options: SessionOptions = {}) {
  let client!: FakeClient;
  let media!: FakeMedia;
  const session = new WidgetSession({
    createClient: ({ callbacks }) => (client = new FakeClient(callbacks)),
    createMediaManager: ({ waitForDevices }) => (media = new FakeMedia(waitForDevices)),
    canPickSpeaker: true,
    ...options,
  });
  return { session, client, media, cb: () => client.cb };
}

const tick = () => new Promise((r) => setTimeout(r, 0));

describe("instant start", () => {
  it("connects without waiting for the mic, and fetches the session meanwhile", async () => {
    const { session, client, media } = setup();
    expect(media.waitForDevices).toBe(false);
    const fetchSession = vi.fn(() => Promise.resolve(SESSION));
    const done = session.connect(fetchSession);
    media.set("asking", "grant");
    client.init.resolve();
    await tick();
    expect(fetchSession).toHaveBeenCalled();
    expect(client.connectedWith).toBeDefined();
    expect(session.mic.getSnapshot()).toMatchObject({ state: "asking", micHint: "grant" });
    client.connectResult.resolve({});
    await done;
    expect(session.getSnapshot()).toMatchObject({ status: "connected", sessionId: "sess_example" });
  });

  it("waits for the mic before fetching the session with instant start off", async () => {
    const { session, client, media } = setup({ instantStart: false });
    expect(media.waitForDevices).toBe(true);
    const fetchSession = vi.fn(() => Promise.resolve(SESSION));
    void session.connect(fetchSession);
    await tick();
    expect(fetchSession).not.toHaveBeenCalled();
    client.init.resolve();
    await tick();
    expect(fetchSession).toHaveBeenCalled();
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

describe("the mic, from the media manager", () => {
  it("mirrors the manager's state and hint, and sends nothing to the agent", async () => {
    const { session, client, media, cb } = setup();
    void session.connect(SESSION);
    client.init.resolve();
    cb().onBotReady?.({} as never);
    media.set("asking", "grant");
    media.set("blocked", "blocked");
    expect(session.mic.getSnapshot()).toMatchObject({ state: "blocked", micHint: "blocked", everLive: false });
    media.set("live", "none");
    expect(session.mic.getSnapshot()).toMatchObject({ state: "live", micHint: "none", everLive: true });
    media.set("live", "silent");
    expect(session.mic.getSnapshot()).toMatchObject({ micHint: "silent", hint: true });
    expect(client.sent).toEqual([]);
  });

  it("does not show the silence hint when the configuration turns it off", () => {
    const { session, media } = setup({ silenceHint: false });
    media.set("live", "silent");
    expect(session.mic.getSnapshot()).toMatchObject({ micHint: "silent", hint: false });
  });

  it("starts a call from what the manager says now", async () => {
    const { session, client, media } = setup();
    media.set("blocked", "blocked");
    void session.connect(SESSION);
    client.init.resolve();
    expect(session.mic.getSnapshot()).toMatchObject({ state: "blocked", micHint: "blocked" });
  });

  it("mutes through the client", () => {
    const { session, client } = setup();
    session.setMuted(true);
    session.setMuted(false);
    expect(client.micEnabled).toEqual([false, true]);
    expect(session.mic.getSnapshot().muted).toBe(false);
  });

  it("asks for the mic again from the pill's tap only while it is blocked or missing", async () => {
    const { session, client, media } = setup();
    void session.connect(SESSION);
    client.init.resolve();
    media.set("live", "none");
    session.askForMic();
    expect(client.micEnabled).toEqual([]);
    media.set("blocked", "blocked");
    session.askForMic();
    expect(client.micEnabled).toEqual([true]);
    media.set("missing", "missing");
    session.askForMic();
    expect(client.micEnabled).toEqual([true, true]);
    session.setMuted(true);
    session.askForMic();
    expect(client.micEnabled).toEqual([true, true, false]);
  });

  it("does not ask for the mic outside a call", () => {
    const { session, client, media } = setup();
    media.set("blocked", "blocked");
    session.askForMic();
    expect(client.micEnabled).toEqual([]);
  });

  it("stops following the manager when disposed", () => {
    const { session, media } = setup();
    expect(media.listening).toBe(2);
    session.dispose();
    expect(media.listening).toBe(0);
  });
});

describe("the attention tone", () => {
  function withTone(options: SessionOptions = {}) {
    const played: number[] = [];
    let closed = 0;
    let made = 0;
    const createTone = (): TonePlayer => {
      made++;
      return { play: () => played.push(Date.now()), close: () => void closed++ };
    };
    const rig = setup({ alertTone: true, createTone, ...options });
    return { ...rig, played, made: () => made, closed: () => closed };
  }

  async function call(rig: ReturnType<typeof withTone>) {
    void rig.session.connect(SESSION);
    rig.client.init.resolve();
    rig.cb().onBotReady?.({} as never);
    await tick();
  }

  it("beeps when the agent first stops speaking with the mic off, once more later, then never", async () => {
    vi.useFakeTimers();
    try {
      const rig = withTone();
      void rig.session.connect(SESSION);
      rig.client.init.resolve();
      expect(rig.made()).toBe(1);
      rig.media.set("asking", "grant");
      rig.cb().onBotStartedSpeaking?.();
      expect(rig.played).toHaveLength(0);
      rig.cb().onBotStoppedSpeaking?.();
      expect(rig.played).toHaveLength(1);
      rig.cb().onBotStoppedSpeaking?.();
      expect(rig.played).toHaveLength(1);
      vi.advanceTimersByTime(TONE_AGAIN_MS);
      expect(rig.played).toHaveLength(2);
      rig.cb().onBotStoppedSpeaking?.();
      vi.advanceTimersByTime(TONE_AGAIN_MS * 4);
      expect(rig.played).toHaveLength(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it("beeps for blocked and missing, never for silent or a live mic", async () => {
    for (const [state, hint, beeps] of [
      ["blocked", "blocked", 1],
      ["missing", "missing", 1],
      ["live", "silent", 0],
      ["live", "none", 0],
    ] as const) {
      const rig = withTone();
      await call(rig);
      rig.media.set(state, hint);
      rig.cb().onBotStoppedSpeaking?.();
      expect(rig.played, `${state}/${hint}`).toHaveLength(beeps);
      rig.session.dispose();
    }
  });

  it("skips the second beep once the mic is live", async () => {
    vi.useFakeTimers();
    try {
      const rig = withTone();
      void rig.session.connect(SESSION);
      rig.client.init.resolve();
      rig.media.set("blocked", "blocked");
      rig.cb().onBotStoppedSpeaking?.();
      rig.media.set("live", "none");
      vi.advanceTimersByTime(TONE_AGAIN_MS);
      expect(rig.played).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("stops when the call ends, and closes its audio", async () => {
    vi.useFakeTimers();
    try {
      const rig = withTone();
      void rig.session.connect(SESSION);
      rig.client.init.resolve();
      rig.media.set("blocked", "blocked");
      rig.cb().onBotStoppedSpeaking?.();
      await rig.session.disconnect();
      vi.advanceTimersByTime(TONE_AGAIN_MS);
      expect(rig.played).toHaveLength(1);
      expect(rig.closed()).toBe(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("is off unless the configuration turns it on", async () => {
    let made = 0;
    const rig = setup({ createTone: () => (made++, { play() {}, close() {} }) });
    void rig.session.connect(SESSION);
    rig.client.init.resolve();
    rig.media.set("blocked", "blocked");
    rig.cb().onBotStoppedSpeaking?.();
    expect(made).toBe(0);
  });

  it("starts afresh on the next call", async () => {
    const rig = withTone();
    await call(rig);
    rig.media.set("blocked", "blocked");
    rig.cb().onBotStoppedSpeaking?.();
    await rig.session.disconnect();
    await call(rig);
    rig.cb().onBotStoppedSpeaking?.();
    expect(rig.played).toHaveLength(2);
    expect(rig.made()).toBe(2);
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

  it("never leaves a refused device change as an unhandled rejection, and reverts the speaker", async () => {
    const refused = Promise.reject(new Error("NotFoundError"));
    refused.catch(() => {});
    const media = new FakeMedia(false);
    media.updateMic = vi.fn(() => Promise.reject(new Error("NotReadableError")));
    media.updateSpeaker = vi.fn(() => Promise.reject(new Error("NotFoundError")));
    const unhandled = vi.fn();
    process.on("unhandledRejection", unhandled);
    try {
      const { session, client, cb } = setup({ createMediaManager: () => media });
      cb().onSpeakerUpdated?.({ deviceId: "s0" } as MediaDeviceInfo);
      session.selectMic("m2");
      session.selectSpeaker("s1");
      await tick();
      await tick();
      expect(media.updateMic).toHaveBeenCalledWith("m2");
      expect(media.updateSpeaker).toHaveBeenCalledWith("s1");
      expect(client.updateMic).not.toHaveBeenCalled();
      expect(session.getSnapshot().devices.speakerId).toBe("s0");
      expect(unhandled).not.toHaveBeenCalled();
    } finally {
      process.off("unhandledRejection", unhandled);
    }
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
    const { session, client, media, cb } = setup();
    void session.connect(SESSION);
    client.init.resolve();
    cb().onBotReady?.({} as never);
    media.set("blocked", "blocked");
    cb().onDisconnected?.();
    expect(session.getSnapshot().end).toEqual({ by: "agent", reason: "mic_denied" });
  });

  it("is the agent ending the call otherwise, even if the mic was later lost", async () => {
    const { session, client, media, cb } = setup();
    void session.connect(SESSION);
    client.init.resolve();
    cb().onBotReady?.({} as never);
    media.set("live", "none");
    media.set("missing", "missing");
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
    const { session, client, media, cb } = setup();
    void session.connect(SESSION);
    client.init.resolve();
    media.set("blocked", "blocked");
    cb().onDisconnected?.();
    expect(session.getSnapshot().end).toMatchObject({ by: "error", reason: "connect_failed" });
  });

  it("does not let a connect the visitor hung up on carry on into the next call", async () => {
    const { session, client } = setup();
    const first = deferred<typeof SESSION>();
    const second = deferred<typeof SESSION>();
    client.init.resolve();
    const a = session.connect(() => first.promise);
    await session.disconnect();
    const b = session.connect(() => second.promise);
    first.resolve({ ...SESSION, session_id: "sess_first" });
    await tick();
    expect(client.connectedWith).toBeUndefined();
    second.resolve(SESSION);
    await tick();
    expect(client.connectedWith).toMatchObject({ session_id: "sess_example" });
    client.connectResult.resolve({});
    await Promise.all([a, b]);
    expect(session.getSnapshot()).toMatchObject({ status: "connected", sessionId: "sess_example" });
  });

  it("does not end the next call when a connect the visitor hung up on fails", async () => {
    const { session, client } = setup();
    const first = deferred<typeof SESSION>();
    client.init.resolve();
    const a = session.connect(() => first.promise);
    await session.disconnect();
    const b = session.connect(SESSION);
    first.reject(new Error("too late"));
    await a;
    expect(session.getSnapshot().status).toBe("connecting");
    client.connectResult.resolve({});
    await b;
    expect(session.getSnapshot().status).toBe("connected");
  });

  it("hangs up a call in progress when disposed", async () => {
    const { session, client } = setup();
    void session.connect(SESSION);
    client.init.resolve();
    session.dispose();
    expect(client.disconnect).toHaveBeenCalled();
    expect(session.getSnapshot().status).toBe("ended");
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
