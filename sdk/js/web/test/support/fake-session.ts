/**
 * A session with no network for the element tests and the component pages:
 * the widget sees the same stores and events a real one gives it, and the
 * test moves them by hand.
 */

import type { MicSnapshot } from "../../src/controllers/mic.js";
import { Store } from "../../src/controllers/store.js";
import type { WidgetSessionLike } from "../../src/elements/widget.js";
import type { SessionEvents, SessionSnapshot, SessionSource } from "../../src/session/adapter.js";

class Patchable<T> extends Store<T> {
  patch(p: Partial<T>): void {
    this.set(p);
  }
}

export const IDLE_SESSION: SessionSnapshot = {
  status: "idle",
  agent: "idle",
  devices: { mics: [], speakers: [], canPickSpeaker: false },
};

export const IDLE_MIC: MicSnapshot = {
  state: "idle",
  device: "idle",
  muted: false,
  hint: false,
  level: 0,
  everLive: false,
  trackMuted: false,
  permission: "unknown",
};

export class FakeSession extends Patchable<SessionSnapshot> implements WidgetSessionLike {
  readonly mic = new Patchable<MicSnapshot>(IDLE_MIC);
  readonly calls: string[] = [];
  readonly rawClient = { fake: true };
  private readonly listeners = new Map<string, Set<(...args: unknown[]) => void>>();
  /** What connect() does to the stores; by default it connects at once. */
  onConnect: (s: FakeSession) => void = (s) => {
    s.patch({ status: "connected", agent: "listening" });
    s.mic.patch({ state: "live", device: "live", everLive: true, permission: "granted" });
  };

  constructor(initial: Partial<SessionSnapshot> = {}) {
    super({ ...IDLE_SESSION, ...initial });
  }

  on<K extends keyof SessionEvents>(event: K, listener: SessionEvents[K]): () => void {
    const set = this.listeners.get(event) ?? new Set();
    set.add(listener as (...args: unknown[]) => void);
    this.listeners.set(event, set);
    return () => set.delete(listener as (...args: unknown[]) => void);
  }

  fire<K extends keyof SessionEvents>(event: K, ...args: Parameters<SessionEvents[K]>): void {
    for (const l of this.listeners.get(event) ?? []) l(...args);
  }

  async connect(_source: SessionSource): Promise<void> {
    this.calls.push("connect");
    this.patch({ status: "connecting", end: undefined });
    this.onConnect(this);
  }

  async disconnect(): Promise<void> {
    this.calls.push("disconnect");
    this.patch({ status: "ended", agent: "idle", end: { by: "user", reason: "hung_up" } });
    this.mic.patch({ state: "idle", device: "idle", level: 0 });
  }

  setMuted(muted: boolean): void {
    this.calls.push(`mute:${muted}`);
    this.mic.patch({ muted, state: muted ? "muted" : "live" });
  }

  selectMic(id: string): void {
    this.calls.push(`mic:${id}`);
  }

  selectSpeaker(id: string): void {
    this.calls.push(`speaker:${id}`);
  }
}
