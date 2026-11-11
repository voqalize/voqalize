/**
 * The package's own `WidgetSession` with the network and the transport
 * replaced: a client that connects at once and reports the local track and
 * device errors through the stock callbacks, as the transport would. So the
 * mic pill is driven through the real session, mic watch and mic controller.
 *
 * Loaded only by the scenarios that use it, so the other pages never pull in
 * the session.
 */

import type { ClientLike, MediaManagerLike, WidgetSession } from "../../src/session/adapter.js";

/** A local audio track whose `muted` the test moves. */
class FakeTrack extends EventTarget {
  readonly kind = "audio";
  readyState: MediaStreamTrackState = "live";
  muted = false;
  setMuted(muted: boolean) {
    this.muted = muted;
    this.dispatchEvent(new Event(muted ? "mute" : "unmute"));
  }
}

const LOCAL = { id: "local", name: "", local: true };

/** The handles a test moves, as `window.__vql`. */
export interface RealSessionControls {
  /** The mic went away, or the system silenced it. */
  lose(): void;
  /** The mic is back. */
  restore(): void;
  /** The permission was taken away mid-call. */
  revoke(): void;
  /** The permission was given back; the transport picks the mic up. */
  grant(): void;
  /** Every client message the session sent. */
  sent(): unknown[];
}

export async function realSession(): Promise<{ session: WidgetSession; controls: RealSessionControls }> {
  const { WidgetSession } = await import("../../src/session/adapter.js");
  const manager: MediaManagerLike = { bindOutputElement: () => () => {} };
  const sent: unknown[] = [];
  let callbacks: Record<string, ((...args: unknown[]) => void) | undefined> = {};
  let track: FakeTrack | null = null;
  let micEnabled = true;
  const start = () => {
    track = new FakeTrack();
    callbacks.onTrackStarted?.(track, LOCAL);
  };
  const stop = () => {
    if (!track) return;
    const t = track;
    track = null;
    t.readyState = "ended";
    callbacks.onTrackStopped?.(t, LOCAL);
  };
  const client: ClientLike = {
    initDevices: () => {
      if (micEnabled) start();
      return Promise.resolve();
    },
    connect: () => {
      queueMicrotask(() => callbacks.onBotReady?.({}));
      return Promise.resolve({});
    },
    disconnect: () => Promise.resolve(),
    enableMic: (on) => {
      micEnabled = on;
      if (on && !track) start();
      if (on && track?.muted) track.setMuted(false);
    },
    get isMicEnabled() {
      return micEnabled;
    },
    sendClientMessage: (type, data) => sent.push({ type, data }),
    updateMic: () => {},
    updateSpeaker: () => {},
  };
  const session = new WidgetSession({
    createClient: (args) => {
      callbacks = args.callbacks as typeof callbacks;
      return client;
    },
    createMediaManager: () => manager,
    // These scenarios start with a live mic: the call asks for it first.
    instantStart: false,
    micWatch: { watchPermission: () => () => {} },
    canPickSpeaker: true,
  });
  const controls: RealSessionControls = {
    lose: () => track?.setMuted(true),
    restore: () => track?.setMuted(false),
    revoke: () => {
      stop();
      callbacks.onDeviceError?.({ devices: ["mic"], type: "permissions" });
    },
    grant: () => start(),
    sent: () => sent,
  };
  return { session, controls };
}
