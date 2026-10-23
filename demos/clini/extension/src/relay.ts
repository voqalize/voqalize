/**
 * The holder's relay: what the pages need of the call to draw his face.
 *
 * Sent as it happens, to every page (`follow.ts` is the other end):
 *   - every pipecat event the widget and the avatar listen to;
 *   - the avatar's `sync`/`end` from the unordered sync channel, which the
 *     holder opens and says hello on itself, as the avatar would
 *     (`syncchannel.ts` in the avatar);
 *   - the mouth clock: the audio receiver's newest RTP synchronization
 *     sample, in wall-clock time, which the pages share, and the
 *     playout-delay totals.
 */

import type { PipecatClient } from "@pipecat-ai/client-js";

import { EVENTS, type ToPage } from "./protocol";

/** The avatar server's sync channel: negotiated on both ends at this id. */
const SYNC_CHANNEL_ID = 200;
const SYNC_LABEL = "avatar-sync";
const HELLO_EVERY_MS = 1000;

export interface Relaying {
  stop(): void;
}

export function relayCall(client: PipecatClient, send: (msg: ToPage) => void): Relaying {
  let pc: RTCPeerConnection | null = null;
  let channel: RTCDataChannel | null = null;
  let heard = false;
  let lastHello = 0;
  let lastTs = 0;
  let stopped = false;

  const currentPc = () => (client.transport as unknown as { pc?: RTCPeerConnection | null }).pc ?? null;

  const sample = () => {
    const receiver = pc?.getReceivers().find((r) => r.track?.kind === "audio");
    if (!receiver) return;
    let latest: RTCRtpSynchronizationSource | null = null;
    for (const s of receiver.getSynchronizationSources()) {
      if (!latest || s.timestamp > latest.timestamp) latest = s;
    }
    if (!latest || latest.timestamp === lastTs) return;
    lastTs = latest.timestamp;
    // Epoch-based, whichever base the engine stamps: the page shares the wall clock.
    const ts = latest.timestamp > 1e11 ? latest.timestamp : performance.timeOrigin + latest.timestamp;
    send({ k: "ssrc", timestamp: ts, rtpTimestamp: latest.rtpTimestamp });
  };

  /** Follow the transport's peer connection (a reconnect replaces it), and
   *  keep saying hello on the sync channel until the server answers on it. */
  const poll = () => {
    const now = currentPc();
    if (now !== pc) {
      try {
        channel?.close();
      } catch {
        /* Gone with its connection. */
      }
      channel = null;
      heard = false;
      pc = now;
      if (pc) {
        try {
          const ch = pc.createDataChannel(SYNC_LABEL, { negotiated: true, id: SYNC_CHANNEL_ID, ordered: false, maxRetransmits: 0 });
          channel = ch;
          ch.onmessage = (e) => {
            if (channel !== ch) return;
            heard = true;
            let msg: { cmd?: unknown } | null = null;
            try {
              msg = JSON.parse(String(e.data));
            } catch {
              return;
            }
            if (msg?.cmd === "sync" || msg?.cmd === "end") send({ k: "sync", msg });
            sample();
          };
        } catch {
          // The ordered channel carries everything, as it always has.
          channel = null;
        }
      }
    }
    const t = Date.now();
    if (channel && !heard && channel.readyState === "open" && t - lastHello >= HELLO_EVERY_MS) {
      lastHello = t;
      try {
        channel.send(JSON.stringify({ type: "avatar", cmd: "hello" }));
      } catch {
        /* Closing under us. */
      }
    }
  };

  const offs: (() => void)[] = [];
  for (const name of EVENTS) {
    const fn = (...args: unknown[]) => {
      let data: unknown = args[0];
      try {
        data = structuredClone(data);
      } catch {
        data = JSON.parse(JSON.stringify(data ?? null));
      }
      send({ k: "ev", name, data });
      poll();
      sample();
    };
    client.on(name as never, fn as never);
    offs.push(() => client.off(name as never, fn as never));
  }

  const readPlayout = async () => {
    if (!pc) return;
    const stats = await pc.getStats();
    stats.forEach((s: { type?: string; kind?: string; totalPlayoutDelay?: number; totalSamplesCount?: number }) => {
      if (s.type === "media-playout" && s.kind === "audio") {
        send({ k: "playout", delay: s.totalPlayoutDelay ?? 0, samples: s.totalSamplesCount ?? 0 });
      }
    });
  };
  const timers = [
    setInterval(() => {
      poll();
      sample();
    }, 23),
    setInterval(() => void readPlayout().catch(() => {}), 1000),
  ];

  return {
    stop() {
      if (stopped) return;
      stopped = true;
      offs.forEach((off) => off());
      timers.forEach(clearInterval);
      try {
        channel?.close();
      } catch {
        /* Gone. */
      }
      channel = null;
      pc = null;
    },
  };
}
