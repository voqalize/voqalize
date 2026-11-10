/**
 * The package's own `WidgetSession` with the network and the media manager
 * replaced: a client that connects at once, and a manager whose `micState`
 * and `micHint` the test moves, as `@voqalize/client-transport`'s manager
 * would from the track, the permission and the device list. So the mic pill
 * is driven through the real session and mic controller.
 *
 * Loaded only by the scenarios that use it, so the other pages never pull in
 * the session.
 */

import type { MicHint, MicState } from "@voqalize/client-transport";
import type { ClientLike, MediaManagerLike, WidgetSession } from "../../src/session/adapter.js";

class FakeManager implements MediaManagerLike {
  micState: MicState = "idle";
  micHint: MicHint = "none";
  private readonly stateListeners = new Set<(s: MicState) => void>();
  private readonly hintListeners = new Set<(h: MicHint) => void>();
  bindOutputElement() {
    return () => {};
  }
  onMicStateChange(l: (s: MicState) => void) {
    this.stateListeners.add(l);
    return () => void this.stateListeners.delete(l);
  }
  onMicHintChange(l: (h: MicHint) => void) {
    this.hintListeners.add(l);
    return () => void this.hintListeners.delete(l);
  }
  set(state: MicState, hint: MicHint) {
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

/** The handles a test moves, as `window.__vql`. */
export interface RealSessionControls {
  /** The mic went away, or the system silenced it. */
  lose(): void;
  /** The mic is back. */
  restore(): void;
  /** The permission was taken away mid-call. */
  revoke(): void;
  /** The permission was given back; the manager picks the mic up. */
  grant(): void;
  /** Every client message the session sent. */
  sent(): unknown[];
}

export async function realSession(): Promise<{ session: WidgetSession; controls: RealSessionControls }> {
  const { WidgetSession } = await import("../../src/session/adapter.js");
  const manager = new FakeManager();
  const sent: unknown[] = [];
  let callbacks: Record<string, ((...args: unknown[]) => void) | undefined> = {};
  const client: ClientLike = {
    initDevices: () => {
      manager.set("asking", "none");
      return Promise.resolve();
    },
    connect: () => {
      queueMicrotask(() => {
        callbacks.onBotReady?.({});
        manager.set("live", "none");
      });
      return Promise.resolve({});
    },
    disconnect: () => Promise.resolve(),
    enableMic: (on) => {
      if (on && manager.micState === "missing") manager.set("live", "none");
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
    canPickSpeaker: true,
  });
  const controls: RealSessionControls = {
    lose: () => manager.set("missing", "missing"),
    restore: () => manager.set("live", "none"),
    revoke: () => manager.set("blocked", "blocked"),
    grant: () => {
      manager.set("asking", "none");
      manager.set("live", "none");
    },
    sent: () => sent,
  };
  return { session, controls };
}
