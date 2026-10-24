/**
 * His face on a page, fed by the holder.
 *
 * The call (the peer connection, the microphone and his voice) lives in the
 * holder (`holder.ts`); every UAH page draws the same, unchanged
 * avatar against a stand-in client fed from the holder's relay (`relay.ts`):
 * every pipecat event the avatar listens to, the avatar's `sync`/`end` from
 * the unordered sync channel, and the mouth clock (the audio receiver's newest
 * RTP synchronization sample, in wall-clock time, which the page shares with
 * the holder, and the playout-delay totals). The avatar's own reports go back
 * to the holder, which sends the front tab's on to the brain.
 *
 * The stand-in receiver answers the face's read with that sample carried
 * forward to the moment of the read (`mouth-clock.ts`), as a receiver in the
 * page would: a busy page reads the relay's messages late, and a late answer
 * is a stop to the face, which shuts his mouth over his voice.
 *
 * A face made in the middle of a reply (a page that loads while he speaks)
 * would hear only what comes after it. So each new face asks the holder for
 * the reply so far (`catch-up.ts`). It listens only once the avatar's runtime
 * has loaded, so from the moment it is made everything waits here: what
 * arrives before the catch-up is in it and is dropped for it, and the
 * catch-up and everything after it reach the face, in order, once it listens.
 * A cue chunk delivered ahead of the one before it would be undone by it.
 */

import type { PipecatClient } from "@pipecat-ai/client-js";

import { onHolder, tell } from "./hub";
import type { ToPage } from "./protocol";
import { carriedForward, type Delivery } from "./mouth-clock";

export interface Following {
  /** Enough of a `PipecatClient` for `createAvatar`: `on`, `off`, `tracks`,
   *  `state`, `sendClientMessage`, and a `transport.pc` that serves the
   *  relayed mouth clock. */
  readonly client: PipecatClient;
  /** Tell the face the call is up, as a call that has just connected would. */
  joined(): void;
  stop(): void;
}

/** Messages held for a face that has not started listening; a face that
 *  never does is not owed the whole call. */
const MAX_HELD = 2000;
/** How long a new face waits for the holder's catch-up. */
const CATCH_UP_WAIT_MS = 2000;

export function followCall(): Following {
  const handlers = new Map<string, Set<(...a: unknown[]) => void>>();
  let latest: Delivery | null = null;
  let playout: { delay: number; samples: number } | null = null;
  let syncSink: ((e: MessageEvent) => void) | null = null;
  /** What waits for the face: from its making, until the catch-up has come
   *  and the face listens. */
  let held: ToPage[] | null = [];
  let caughtUp = false;

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
    getSynchronizationSources: () => {
      const now = carriedForward(latest, performance.timeOrigin + performance.now());
      return now ? [{ ...now, source: 1, audioLevel: 0 }] : [];
    },
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
      // The face has started listening: what was held for it goes now.
      if (name === "serverMessage" && held && caughtUp) flushSoon();
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

  const deliver = (r: ToPage) => {
    if (r.k === "ev") emit(r.name, r.data);
    else if (r.k === "sync") syncSink?.({ data: JSON.stringify(r.msg) } as MessageEvent);
  };
  const listening = () => (handlers.get("serverMessage")?.size ?? 0) > 0;
  // After the face's own setup has finished, which opens its sync channel.
  const flushSoon = () =>
    setTimeout(() => {
      if (!held || !caughtUp || !listening()) return;
      const due = held;
      held = null;
      due.forEach(deliver);
    }, 0);

  // A holder that never answers (one from before the catch-up) does not hold
  // the face back for long: what came is then what it gets.
  const noCatchUp = setTimeout(() => {
    caughtUp = true;
    flushSoon();
  }, CATCH_UP_WAIT_MS);
  const off = onHolder((r) => {
    if (r.k === "catchup") {
      if (caughtUp) return;
      caughtUp = true;
      clearTimeout(noCatchUp);
      if (held) held = [...r.msgs];
      flushSoon();
    } else if (r.k === "ev" || r.k === "sync") {
      if (held) {
        if (held.length < MAX_HELD) held.push(r);
      } else {
        deliver(r);
      }
    } else if (r.k === "playout") playout = { delay: r.delay, samples: r.samples };
    else if (r.k === "ssrc") latest = { timestamp: r.timestamp, rtpTimestamp: r.rtpTimestamp };
  });
  // Listening first, so the answer cannot pass us.
  tell({ k: "catchup" });

  return {
    client: client as unknown as PipecatClient,
    joined() {
      emit("connected");
      emit("botReady", {});
    },
    stop() {
      clearTimeout(noCatchUp);
      off();
      handlers.clear();
    },
  };
}
