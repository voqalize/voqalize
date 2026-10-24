/**
 * The call, as the extension the end-to-end tests load has it: a stand-in
 * pipecat client that connects at once and records what the holder sends it,
 * a microphone permission the test sets, and hooks the test drives through
 * the service worker (`chrome.runtime.sendMessage({to: "holder", op: "test", …})`).
 *
 * His voice, when a test asks for it (`voice`): a tone over a real WebRTC
 * loopback in the holder, played as his voice is, so the relay reads the
 * delivery clock of a real receiver, as it does in a call.
 */

import type { PipecatClient, PipecatClientOptions } from "@pipecat-ai/client-js";

import type { MicState } from "../src/protocol";

type Callbacks = NonNullable<PipecatClientOptions["callbacks"]>;

interface Fake {
  callbacks: Callbacks;
  handlers: Map<string, Set<(...a: unknown[]) => void>>;
  sent: { event: string; payload: unknown }[];
  avatarReports: number;
  session: unknown;
  hungUp: boolean;
  micOn: boolean;
  transport: { pc: RTCPeerConnection | null };
}

/** The loopback that carries his voice: the receiving end is the call's. */
let voice: { pc: RTCPeerConnection; sender: RTCRtpSender; track: MediaStreamTrack } | null = null;

async function speak(on: boolean): Promise<void> {
  if (!voice) {
    const ac = new AudioContext();
    await ac.resume();
    const tone = ac.createOscillator();
    tone.frequency.value = 180;
    const out = ac.createMediaStreamDestination();
    tone.connect(out);
    tone.start();
    const track = out.stream.getAudioTracks()[0]!;
    const from = new RTCPeerConnection();
    const to = new RTCPeerConnection();
    from.onicecandidate = (e) => void (e.candidate && to.addIceCandidate(e.candidate));
    to.onicecandidate = (e) => void (e.candidate && from.addIceCandidate(e.candidate));
    const sender = from.addTrack(track, out.stream);
    to.ontrack = (e) => {
      const el = document.createElement("audio");
      el.srcObject = e.streams[0] ?? new MediaStream([e.track]);
      document.body.append(el);
      void el.play().catch(() => {});
    };
    await from.setLocalDescription();
    await to.setRemoteDescription(from.localDescription!);
    await to.setLocalDescription();
    await from.setRemoteDescription(to.localDescription!);
    voice = { pc: to, sender, track };
  }
  if (current) current.transport.pc = voice.pc;
  // Audio flows only while he speaks, as the voice runtime sends it.
  await voice.sender.replaceTrack(on ? voice.track : null);
}

let current: Fake | null = null;
/** The answers the permission query gives, in turn; the last one repeats. */
let micAnswers: MicState[] = ["granted"];
const micAsked: MicState[] = [];

export function makeClient(_output: HTMLAudioElement, callbacks: Callbacks): PipecatClient {
  const fake: Fake = {
    callbacks, handlers: new Map(), sent: [], avatarReports: 0, session: null, hungUp: false, micOn: true,
    transport: { pc: null },
  };
  current = fake;
  const emit = (name: string, data?: unknown) => fake.handlers.get(name)?.forEach((fn) => fn(data));
  const client = {
    transport: fake.transport,
    on(name: string, fn: (...a: unknown[]) => void) {
      (fake.handlers.get(name) ?? fake.handlers.set(name, new Set()).get(name)!).add(fn);
      return client;
    },
    off(name: string, fn: (...a: unknown[]) => void) {
      fake.handlers.get(name)?.delete(fn);
      return client;
    },
    async connect(session: unknown) {
      fake.session = session;
      callbacks.onTransportStateChanged?.("connected" as never);
      emit("connected");
      callbacks.onTransportStateChanged?.("ready" as never);
      setTimeout(() => {
        callbacks.onBotReady?.({} as never);
        emit("botReady", {});
      }, 50);
    },
    disconnectBot() {
      fake.hungUp = true;
    },
    async disconnect() {
      callbacks.onTransportStateChanged?.("disconnected" as never);
    },
    enableMic(on: boolean) {
      fake.micOn = on;
    },
    sendUIEvent(event: string, payload: unknown) {
      fake.sent.push({ event, payload });
    },
    sendClientMessage() {
      fake.avatarReports++;
    },
  };
  (fake as unknown as { emit: typeof emit }).emit = emit;
  return client as unknown as PipecatClient;
}

export async function micState(): Promise<MicState> {
  const answer = micAnswers.length > 1 ? micAnswers.shift()! : micAnswers[0];
  micAsked.push(answer);
  return answer;
}

interface Holder {
  state: unknown;
  tabs: Map<number, { url: string; ports: Set<unknown>; front: boolean }>;
  pending: Map<number, unknown[]>;
  log: string[];
}

interface TestAsk {
  to: "holder";
  op: "test";
  what: "status" | "mic" | "emit" | "command" | "voice";
  on?: boolean;
  answers?: MicState[];
  name?: string;
  data?: unknown;
  command?: string;
  payload?: unknown;
}

export function testHooks(holder: Holder): void {
  chrome.runtime.onMessage.addListener((msg: TestAsk, _sender, reply) => {
    if (msg?.to !== "holder" || msg.op !== "test") return;
    switch (msg.what) {
      case "status":
        reply({
          state: holder.state,
          tabs: [...holder.tabs.values()].map((t) => ({ url: t.url, ports: t.ports.size, front: t.front })),
          pending: [...holder.pending.values()].reduce((n, l) => n + l.length, 0),
          log: holder.log,
          sent: current?.sent ?? [],
          session: current?.session ?? null,
          hungUp: current?.hungUp ?? false,
          micOn: current?.micOn ?? null,
          micAsked,
        });
        return;
      case "mic":
        micAnswers = msg.answers?.length ? [...msg.answers] : ["granted"];
        micAsked.length = 0;
        reply({ ok: true });
        return;
      case "emit":
        (current as unknown as { emit?: (n: string, d?: unknown) => void })?.emit?.(msg.name!, msg.data);
        reply({ ok: Boolean(current) });
        return;
      case "voice":
        void speak(msg.on ?? true).then(
          () => reply({ ok: true }),
          (error: unknown) => reply({ ok: false, error: String(error) }),
        );
        return true;
      case "command":
        current?.callbacks.onUICommand?.({ command: msg.command!, payload: msg.payload } as never);
        reply({ ok: Boolean(current) });
        return;
    }
  });
}
