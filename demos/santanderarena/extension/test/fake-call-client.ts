/**
 * The call, as the extension the end-to-end tests load has it: a stand-in
 * pipecat client that connects at once and records what the holder sends it,
 * a microphone permission the test sets, and hooks the test drives through
 * the service worker (`chrome.runtime.sendMessage({to: "holder", op: "test", …})`).
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
}

let current: Fake | null = null;
/** The answers the permission query gives, in turn; the last one repeats. */
let micAnswers: MicState[] = ["granted"];
const micAsked: MicState[] = [];

export function makeClient(_output: HTMLAudioElement, callbacks: Callbacks): PipecatClient {
  const fake: Fake = {
    callbacks, handlers: new Map(), sent: [], avatarReports: 0, session: null, hungUp: false, micOn: true,
  };
  current = fake;
  const emit = (name: string, data?: unknown) => fake.handlers.get(name)?.forEach((fn) => fn(data));
  const client = {
    transport: { pc: null },
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
  what: "status" | "mic" | "emit" | "command";
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
      case "command":
        current?.callbacks.onUICommand?.({ command: msg.command!, payload: msg.payload } as never);
        reply({ ok: Boolean(current) });
        return;
    }
  });
}
