/**
 * One call, every tab of the store.
 *
 * The tab the shopper started the call in holds it: the peer connection, the
 * mic and her voice. Every other open tab of the store follows it. The holder
 * relays what it hears on the call to them over a `BroadcastChannel`, so a
 * follower runs the same widget and the same, unchanged avatar against a
 * stand-in client fed from that relay. Mute and End in a follower go back to
 * the holder.
 *
 * What crosses, holder → followers, sent as it happens and never on a timer
 * alone (Safari all but stops a hidden tab's timers):
 *   - the call's state, muted, and what she is doing;
 *   - every pipecat event the widget and the avatar listen to;
 *   - the avatar's `sync`/`end` from the unordered sync channel;
 *   - the mouth clock: the audio receiver's newest RTP synchronization sample,
 *     in wall-clock time, which every tab shares, and the playout-delay totals;
 *   - the brain's Actions, addressed to the tab in front.
 *
 * Followers → holder: where each tab is and whether it is in front, the front
 * tab's page events for the brain, Mute, End, and the avatar's reports.
 *
 * This is the Qween prove-out of `apps/voqalize/multi-tab/DESIGN.md`. It lives
 * in the demo on purpose: nothing in `@voqalize/client-transport` or
 * `@voqalize/avatar` changes until we know what the libraries should offer.
 */

import type { PipecatClient } from "@pipecat-ai/client-js";

import type { Activity, Status } from "./widget";

/** The pipecat events relayed to followers: the avatar's (`RTVI_EVENTS` in
 *  the avatar's `AvatarClient.ts`, less `trackStarted`) and the widget's. */
const EVENTS = [
  "serverMessage", "connected", "disconnected", "botReady", "error",
  "userStartedSpeaking", "userStoppedSpeaking", "botStartedSpeaking", "botStoppedSpeaking",
  "userMuteStarted", "userMuteStopped", "botLlmStarted",
] as const;

const SYNC_LABEL = "avatar-sync";
const TAB_KEY = "voqalize.qween.tab";

export interface TabInfo {
  tab_id: string;
  url: string;
  title: string;
}

export type Relay =
  // Any tab, on load: is there a call, and is my id taken? (A tab opened from
  // a link can start with a copy of its opener's sessionStorage.)
  | { k: "hello"; from: string; instance: string }
  | { k: "dup"; id: string; instance: string }
  // The holder's state, on every change and in answer to a hello.
  | { k: "holder"; from: string; status: Status; muted: boolean; activity: Activity | null }
  // The holder's page is going away. `navigating` when the Navigation API saw
  // it leave for another document, which comes back and dials again; a
  // closed tab does not.
  | { k: "bye"; from: string; navigating: boolean }
  // A page that held the call before its load, dialling again.
  | { k: "coming"; from: string }
  | { k: "ev"; name: string; data: unknown }
  | { k: "sync"; msg: unknown }
  | { k: "ssrc"; timestamp: number; rtpTimestamp: number }
  | { k: "playout"; delay: number; samples: number }
  | { k: "perform"; to: string; command: string; payload: unknown }
  | { k: "tab"; tab: TabInfo; front: boolean }
  | { k: "gone"; from: string }
  | { k: "app"; from: string; event: string; payload: unknown }
  | { k: "report"; from: string; data: unknown }
  | { k: "mute" }
  | { k: "end" };

export const wall = (): number => performance.timeOrigin + performance.now();

export function openChannel(): BroadcastChannel {
  return new BroadcastChannel("voqalize.qween.call");
}

function freshId(): string {
  return Math.random().toString(36).slice(2, 10);
}

/** This tab's id: kept in sessionStorage so it survives a page load in this
 *  tab, and replaced when another live tab already uses it. */
export async function tabId(chan: BroadcastChannel): Promise<{ id: string; instance: string }> {
  let id: string | null = null;
  try {
    id = sessionStorage.getItem(TAB_KEY);
  } catch {
    /* Storage blocked: a new id per page. */
  }
  const instance = freshId();
  if (id) {
    const asked = id;
    const taken = await new Promise<boolean>((resolve) => {
      const on = (e: MessageEvent) => {
        const r = e.data as Relay;
        if (r.k === "dup" && r.id === asked && r.instance === instance) done(true);
      };
      const done = (v: boolean) => {
        chan.removeEventListener("message", on);
        resolve(v);
      };
      chan.addEventListener("message", on);
      chan.postMessage({ k: "hello", from: asked, instance } satisfies Relay);
      setTimeout(() => done(false), 150);
    });
    if (taken) id = null;
  }
  if (!id) id = freshId();
  try {
    sessionStorage.setItem(TAB_KEY, id);
  } catch {
    /* As above. */
  }
  return { id, instance };
}

export function here(id: string): TabInfo {
  return { tab_id: id, url: location.href, title: document.title };
}

export function inFront(): boolean {
  return document.visibilityState === "visible" && document.hasFocus();
}

// ─── The holder ────────────────────────────────────────────────────────────

export interface Holding {
  /** The client to hand this tab's own avatar: the real one, with its sync
   *  channel tapped and its reports sent only while this tab is in front. */
  readonly avatarClient: PipecatClient;
  /** Start the AudioWorklet pulse; call from the click that starts the call,
   *  which is what lets an AudioContext run. */
  pulse(): Promise<void>;
  stop(): void;
}

/**
 * Relay one call to the other tabs.
 *
 * @param reportAllowed whether this tab's own avatar may report; only the tab
 *   in front does, so a turn is reported once.
 */
export function holdCall(
  client: PipecatClient,
  chan: BroadcastChannel,
  reportAllowed: () => boolean,
): Holding {
  const send = (r: Relay) => chan.postMessage(r);
  let pc: RTCPeerConnection | null = null;
  let lastTs = 0;
  let stopped = false;

  const sample = () => {
    const receiver = pc?.getReceivers().find((r) => r.track?.kind === "audio");
    if (!receiver) return;
    let latest: RTCRtpSynchronizationSource | null = null;
    for (const s of receiver.getSynchronizationSources()) {
      if (!latest || s.timestamp > latest.timestamp) latest = s;
    }
    if (!latest || latest.timestamp === lastTs) return;
    lastTs = latest.timestamp;
    // Epoch-based, whichever base the engine stamps: the follower shares the
    // wall clock.
    const ts = latest.timestamp > 1e11 ? latest.timestamp : performance.timeOrigin + latest.timestamp;
    send({ k: "ssrc", timestamp: ts, rtpTimestamp: latest.rtpTimestamp });
  };

  // The avatar opens the unordered sync channel itself; a second listener on
  // the same channel relays what it hears.
  const tapped = new WeakMap<RTCPeerConnection, RTCPeerConnection>();
  const tapPc = (real: RTCPeerConnection): RTCPeerConnection => {
    pc = real;
    let proxy = tapped.get(real);
    if (proxy) return proxy;
    proxy = new Proxy(real, {
      get(target, key) {
        if (key === "createDataChannel") {
          return (label: string, init?: RTCDataChannelInit) => {
            const ch = target.createDataChannel(label, init);
            if (label === SYNC_LABEL) {
              ch.addEventListener("message", (e) => {
                let msg: { cmd?: unknown } | null = null;
                try {
                  msg = JSON.parse(String(e.data));
                } catch {
                  return;
                }
                if (msg?.cmd === "sync" || msg?.cmd === "end") send({ k: "sync", msg });
                sample();
              });
            }
            return ch;
          };
        }
        const v = Reflect.get(target, key, target);
        return typeof v === "function" ? v.bind(target) : v;
      },
    });
    tapped.set(real, proxy);
    return proxy;
  };

  const transportProxy = new Proxy(client.transport as object, {
    get(target, key) {
      const v = Reflect.get(target, key);
      if (key === "pc") return v ? tapPc(v as RTCPeerConnection) : v;
      return typeof v === "function" ? v.bind(target) : v;
    },
  });
  const avatarClient = new Proxy(client, {
    get(target, key) {
      if (key === "transport") return transportProxy;
      if (key === "sendClientMessage") {
        return (type: string, data?: unknown) => {
          if (reportAllowed()) target.sendClientMessage(type, data as never);
        };
      }
      const v = Reflect.get(target, key);
      return typeof v === "function" ? v.bind(target) : v;
    },
  });

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
  // The timers are for Chrome; a hidden Safari tab barely runs them, and the
  // worklet pulse below carries the samples there.
  const timers = [setInterval(sample, 23), setInterval(() => void readPlayout(), 1000)];

  let ac: AudioContext | null = null;
  const resumeOnTap = () => void ac?.resume().catch(() => {});

  return {
    avatarClient,
    async pulse() {
      if (ac || stopped) return;
      try {
        ac = new AudioContext();
        await ac.resume().catch(() => {});
        // The audio thread runs while audio plays, hidden or not: a muted
        // worklet posting every eighth render quantum (about 21 ms) wakes the
        // page to take a sample.
        const code = `class P extends AudioWorkletProcessor{constructor(){super();this.n=0}process(){if(++this.n%8===0)this.port.postMessage(0);return true}}registerProcessor("vq-pulse",P)`;
        await ac.audioWorklet.addModule(URL.createObjectURL(new Blob([code], { type: "application/javascript" })));
        const node = new AudioWorkletNode(ac, "vq-pulse");
        const mute = ac.createGain();
        mute.gain.value = 0;
        node.connect(mute).connect(ac.destination);
        node.port.onmessage = sample;
        // A call dialled again after a page load had no click: the context may
        // be suspended until the shopper next touches the page.
        if (ac.state !== "running") document.addEventListener("pointerdown", resumeOnTap, { capture: true });
      } catch (error) {
        console.warn("voqalize: no worklet pulse; samples ride the timer and events", error);
      }
    },
    stop() {
      stopped = true;
      offs.forEach((off) => off());
      timers.forEach(clearInterval);
      document.removeEventListener("pointerdown", resumeOnTap, { capture: true });
      void ac?.close().catch(() => {});
      ac = null;
      pc = null;
    },
  };
}

// ─── A follower ────────────────────────────────────────────────────────────

export interface Following {
  /** Enough of a `PipecatClient` for `createAvatar`, and for the widget's own
   *  listeners: `on`, `off`, `tracks`, `state`, `sendClientMessage`, and a
   *  `transport.pc` that serves the relayed mouth clock. */
  readonly client: PipecatClient;
  /** Tell the face the call is up, as a call that has just connected would. */
  joined(): void;
  /** The holder went away: the face is told the call dropped. */
  dropped(): void;
  stop(): void;
}

export function followCall(chan: BroadcastChannel, from: string): Following {
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
    // The holder's own avatar says hello on the real channel.
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
    sendClientMessage: (_type: string, data: unknown) => {
      chan.postMessage({ k: "report", from, data } satisfies Relay);
    },
  };
  const emit = (name: string, ...args: unknown[]) =>
    handlers.get(name)?.forEach((fn) => {
      try {
        fn(...args);
      } catch (error) {
        console.error(error);
      }
    });

  const on = (e: MessageEvent) => {
    const r = e.data as Relay;
    if (r.k === "ev") emit(r.name, r.data);
    else if (r.k === "sync") syncSink?.({ data: JSON.stringify(r.msg) } as MessageEvent);
    else if (r.k === "playout") playout = { delay: r.delay, samples: r.samples };
    else if (r.k === "ssrc") latest = { timestamp: r.timestamp, rtpTimestamp: r.rtpTimestamp };
  };
  chan.addEventListener("message", on);

  return {
    client: client as unknown as PipecatClient,
    joined() {
      emit("connected");
      emit("botReady", {});
    },
    dropped() {
      latest = null;
      playout = null;
      emit("disconnected");
    },
    stop() {
      chan.removeEventListener("message", on);
      handlers.clear();
    },
  };
}
