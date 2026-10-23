/**
 * His face on a page, fed by the holder.
 *
 * The call (the peer connection, the microphone and his voice) lives in the
 * holder (`holder.ts`); every Santander Arena page draws the same, unchanged
 * avatar against a stand-in client fed from the holder's relay (`relay.ts`):
 * every pipecat event the avatar listens to, the avatar's `sync`/`end` from
 * the unordered sync channel, and the mouth clock (the audio receiver's newest
 * RTP synchronization sample, in wall-clock time, which the page shares with
 * the holder, and the playout-delay totals). The avatar's own reports go back
 * to the holder, which sends the front tab's on to the brain.
 */

import type { PipecatClient } from "@pipecat-ai/client-js";

import { onHolder, tell } from "./hub";

export interface Following {
  /** Enough of a `PipecatClient` for `createAvatar`: `on`, `off`, `tracks`,
   *  `state`, `sendClientMessage`, and a `transport.pc` that serves the
   *  relayed mouth clock. */
  readonly client: PipecatClient;
  /** Tell the face the call is up, as a call that has just connected would. */
  joined(): void;
  stop(): void;
}

export function followCall(): Following {
  const handlers = new Map<string, Set<(...a: unknown[]) => void>>();
  let latest: { timestamp: number; rtpTimestamp: number } | null = null;
  let playout: { delay: number; samples: number } | null = null;
  let syncSink: ((e: MessageEvent) => void) | null = null;

  const syncChannel = {
    readyState: "open",
    set onmessage(fn: ((e: MessageEvent) => void) | null) {
      syncSink = fn;
    },
    get onmessage() {
      return syncSink;
    },
    // The holder says hello on the real channel.
    send() {},
    close() {
      syncSink = null;
    },
  };
  const receiver = {
    track: { kind: "audio" },
    getSynchronizationSources: () => (latest ? [{ ...latest, source: 1, audioLevel: 0 }] : []),
  };
  const pc = {
    getReceivers: () => [receiver],
    getStats: async () => {
      const m = new Map<string, unknown>();
      if (playout) {
        m.set("p", {
          type: "media-playout", kind: "audio",
          totalPlayoutDelay: playout.delay, totalSamplesCount: playout.samples,
        });
      }
      return m;
    },
    createDataChannel: () => syncChannel,
  };
  const client = {
    transport: { pc },
    state: "ready",
    on(name: string, fn: (...a: unknown[]) => void) {
      (handlers.get(name) ?? handlers.set(name, new Set()).get(name)!).add(fn);
      return client;
    },
    off(name: string, fn: (...a: unknown[]) => void) {
      handlers.get(name)?.delete(fn);
      return client;
    },
    tracks: () => ({ local: {}, bot: {} }),
    sendClientMessage: (_type: string, data: unknown) => tell({ k: "report", data }),
  };
  const emit = (name: string, ...args: unknown[]) =>
    handlers.get(name)?.forEach((fn) => {
      try {
        fn(...args);
      } catch (error) {
        console.error(error);
      }
    });

  const off = onHolder((r) => {
    if (r.k === "ev") emit(r.name, r.data);
    else if (r.k === "sync") syncSink?.({ data: JSON.stringify(r.msg) } as MessageEvent);
    else if (r.k === "playout") playout = { delay: r.delay, samples: r.samples };
    else if (r.k === "ssrc") latest = { timestamp: r.timestamp, rtpTimestamp: r.rtpTimestamp };
  });

  return {
    client: client as unknown as PipecatClient,
    joined() {
      emit("connected");
      emit("botReady", {});
    },
    stop() {
      off();
      handlers.clear();
    },
  };
}
