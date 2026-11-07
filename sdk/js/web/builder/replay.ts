/**
 * A session with no network for the builder's preview: it replays a recorded
 * turn (the agent's words as they would play, and the visitor's mic level)
 * into the widget, so every state is shown through the real widget without a
 * call. It speaks only through the widget's public session shape
 * (`WidgetSessionLike`) and the public `Store`, so the builder carries no
 * package internals when it moves to the marketing site.
 */

import type { SessionEvents, SessionSnapshot, SessionSource } from "@voqalize/web/internal";
import { type MicSnapshot, Store, type WidgetSessionLike } from "@voqalize/web/widgets";

class Patchable<T> extends Store<T> {
  patch(p: Partial<T>): void {
    this.set(p);
  }
}

/** One sentence of a recorded turn: its words and when each starts, in ms from the sentence's start. */
export interface RecordedSentence {
  words: readonly { text: string; at: number }[];
  /** How long the sentence plays, in ms. */
  ms: number;
}

/** A recorded exchange: the agent speaks, the visitor answers, the agent speaks again. */
export interface RecordedTurn {
  agent: readonly RecordedSentence[];
  /** What the visitor says between the agent's sentences, with the mic level every 100 ms. */
  user: { text: string; levels: readonly number[] };
  reply: readonly RecordedSentence[];
}

/** Words spaced at a speaking pace, as the transport's word timings would put them. */
export function sentence(text: string, msPerWord = 260): RecordedSentence {
  const words = text.split(/\s+/).filter(Boolean);
  return { words: words.map((w, i) => ({ text: w, at: i * msPerWord })), ms: words.length * msPerWord + 300 };
}

/** The level of a voice speaking for `ms`: syllable-like rises over a quiet floor. */
export function voiceLevels(ms: number): number[] {
  const out: number[] = [];
  for (let t = 0; t < ms; t += 100) {
    const syllable = Math.abs(Math.sin(t / 140)) * 0.22 + Math.abs(Math.sin(t / 53)) * 0.08;
    out.push(Math.min(1, 0.02 + syllable));
  }
  return out;
}

export function recordedTurn(name: string): RecordedTurn {
  return {
    agent: [sentence(`Hi, I'm ${name}. This is how I'd look on your site.`), sentence("What would you like to know?")],
    user: { text: "Can you help me pick a plan?", levels: voiceLevels(1800) },
    reply: [sentence("Of course. Tell me roughly how many people will use it.")],
  };
}

const IDLE_MIC: MicSnapshot = {
  state: "idle",
  device: "idle",
  muted: false,
  hint: false,
  level: 0,
  everLive: false,
  permission: "unknown",
};

const mic = (id: string, label: string) => ({ deviceId: id, label, kind: "audioinput", groupId: "" }) as MediaDeviceInfo;
const speaker = (id: string, label: string) => ({ deviceId: id, label, kind: "audiooutput", groupId: "" }) as MediaDeviceInfo;

/** How the replay starts a call: the mic the visitor has, and whether the turn plays. */
export interface ReplayScript {
  mic: "live" | "asking" | "blocked" | "missing" | "muted" | "silent";
  /** Play the recorded turn, on a loop, once connected. */
  play: boolean;
}

export class ReplaySession extends Patchable<SessionSnapshot> implements WidgetSessionLike {
  readonly mic = new Patchable<MicSnapshot>(IDLE_MIC);
  readonly rawClient = undefined;
  private readonly listeners = new Map<string, Set<(...args: unknown[]) => void>>();
  private timers: ReturnType<typeof setTimeout>[] = [];
  private stopped = false;

  constructor(
    private turn: RecordedTurn,
    private script: ReplayScript,
  ) {
    super({
      status: "idle",
      agent: "idle",
      devices: {
        mics: [mic("default", "Built-in Microphone"), mic("usb", "USB Headset")],
        speakers: [speaker("default", "Built-in Speakers"), speaker("usb", "USB Headset")],
        micId: "default",
        speakerId: "default",
        canPickSpeaker: true,
      },
    });
  }

  on<K extends keyof SessionEvents>(event: K, listener: SessionEvents[K]): () => void {
    const set = this.listeners.get(event) ?? new Set();
    set.add(listener as (...args: unknown[]) => void);
    this.listeners.set(event, set);
    return () => set.delete(listener as (...args: unknown[]) => void);
  }

  private fire<K extends keyof SessionEvents>(event: K, ...args: Parameters<SessionEvents[K]>): void {
    for (const l of this.listeners.get(event) ?? []) l(...args);
  }

  private after(ms: number, fn: () => void): void {
    this.timers.push(setTimeout(() => !this.stopped && fn(), ms));
  }

  async connect(_source: SessionSource): Promise<void> {
    this.stopped = false;
    this.patch({ status: "connecting", end: undefined });
    const m = this.script.mic;
    if (m === "asking") this.mic.patch({ state: "asking", device: "asking", permission: "prompt" });
    else if (m === "blocked") this.mic.patch({ state: "blocked", device: "blocked", permission: "denied" });
    else if (m === "missing") this.mic.patch({ state: "missing", device: "missing", permission: "granted" });
    else this.mic.patch({ state: "live", device: "live", everLive: true, permission: "granted" });
    if (m === "muted") this.mic.patch({ muted: true, state: "muted" });
    if (m === "silent") this.mic.patch({ hint: true, level: 0.005 });
    this.patch({ status: "connected", agent: "listening", sessionId: "preview" });
    if (this.script.play) this.loop(0);
  }

  /** Play the turn from `start` ms, then again, until the call ends. */
  private loop(start: number): void {
    let t = start;
    const speak = (sentences: readonly RecordedSentence[]) => {
      this.after(t, () => {
        this.patch({ agent: "speaking" });
        this.fire("agentStarted");
      });
      for (const s of sentences) {
        const text = s.words.map((w) => w.text).join(" ");
        this.after(t, () => this.fire("agentSentence", text));
        for (const w of s.words) this.after(t + w.at, () => this.fire("agentWord", w.text));
        t += s.ms;
      }
      this.after(t, () => {
        this.fire("agentStopped");
        this.patch({ agent: "listening" });
      });
    };
    speak(this.turn.agent);
    // The visitor answers (only where the mic hears them).
    const hears = this.script.mic === "live";
    t += 600;
    if (hears) {
      const { text, levels } = this.turn.user;
      const words = text.split(" ");
      levels.forEach((level, i) => {
        this.after(t + i * 100, () => {
          this.mic.patch({ level });
          const said = words.slice(0, Math.ceil(((i + 1) / levels.length) * words.length)).join(" ");
          this.patch({ user: { text: said, final: false } });
          this.fire("userTranscript", said, false);
        });
      });
      t += levels.length * 100;
      this.after(t, () => {
        this.mic.patch({ level: 0.01 });
        this.patch({ user: { text, final: true }, agent: "thinking" });
        this.fire("userTranscript", text, true);
      });
      t += 700;
      speak(this.turn.reply);
    }
    t += 4500;
    this.after(t, () => this.loop(0));
  }

  async disconnect(): Promise<void> {
    this.halt();
    this.patch({ status: "ended", agent: "idle", end: { by: "user", reason: "hung_up" } });
    this.mic.patch({ ...IDLE_MIC });
  }

  /** End as the far end would: the agent hanging up, or the mic never arriving. */
  endFromAgent(reason: "ended" | "mic_denied"): void {
    this.halt();
    this.patch({ status: "ended", agent: "idle", end: { by: "agent", reason } });
    this.mic.patch({ state: "idle", device: "idle", level: 0 });
  }

  setMuted(muted: boolean): void {
    this.mic.patch({ muted, state: muted ? "muted" : "live" });
  }

  selectMic(id: string): void {
    this.patch({ devices: { ...this.getSnapshot().devices, micId: id } });
  }

  selectSpeaker(id: string): void {
    this.patch({ devices: { ...this.getSnapshot().devices, speakerId: id } });
  }

  private halt(): void {
    this.stopped = true;
    for (const t of this.timers) clearTimeout(t);
    this.timers = [];
  }

  dispose(): void {
    this.halt();
  }
}
