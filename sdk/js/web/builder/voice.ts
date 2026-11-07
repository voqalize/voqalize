/**
 * The agent's voice in the builder's preview, and the client its face follows.
 *
 * The replayed turn is real speech: clips the Voqalize speech tier made in the
 * voice each offered character speaks in (`fixtures/make.mjs`), with the speech
 * tier's word timings and the mouth cues a call sends for that audio. This
 * module plays them on a genuine audio track and raises the events a pipecat
 * client raises in a call, so `@voqalize/avatar` mounts on it exactly as it
 * mounts on a call's client: it reads the agent's audio from `tracks()` and
 * the cues and speaking events from `on`.
 *
 * The track always carries the voice, so the face moves its lips whether or
 * not the speakers do. Whether it is heard is a separate gain, so only one
 * frame of the builder plays aloud.
 */

import voicesJson from "./fixtures/voices.json";

/** One context of the agent's speech: one clip, its sentences and its mouth cues. */
export interface SpokenClip {
  audio: string;
  /** The clip's length, in ms. */
  ms: number;
  sentences: readonly { text: string; words: readonly { text: string; at: number }[] }[];
  cues?: readonly { t: number; v: string; i?: number; p?: number }[];
}

export interface SpokenTurn {
  open: SpokenClip;
  reply: SpokenClip;
}

interface Voices {
  language: string;
  characters: Record<string, string>;
  voices: Record<string, SpokenTurn>;
}

const VOICES = voicesJson as unknown as Voices;

/** The characters the preview has a voice for, by name. */
export const VOICED_CHARACTERS: readonly string[] = Object.keys(VOICES.characters);

/** The turn a character speaks, or `undefined` where the preview has no clips in its voice. */
export function spokenTurn(character: string): SpokenTurn | undefined {
  const voice = VOICES.characters[character];
  return voice ? VOICES.voices[voice] : undefined;
}

type Handler = (...args: unknown[]) => void;

/** The bot as a pipecat client names it in `trackStarted`. */
const BOT = { id: "preview-bot", name: "preview", local: false };

/** How far ahead of its audio a context's cues are sent, as a call sends them. */
const CUES_AHEAD_MS = 40;

export class PreviewVoice {
  readonly audio = new AudioContext();
  private readonly out = this.audio.createMediaStreamDestination();
  private readonly speakers = this.audio.createGain();
  /** Measures what the track carries, for the builder's own checks. */
  readonly analyser = this.audio.createAnalyser();
  private readonly handlers = new Map<string, Set<Handler>>();
  private readonly buffers = new Map<string, Promise<AudioBuffer>>();
  private readonly playing = new Set<AudioBufferSourceNode>();
  private timers: ReturnType<typeof setTimeout>[] = [];
  private connected = false;
  private contexts = 0;

  constructor() {
    this.speakers.gain.value = 0;
    this.speakers.connect(this.audio.destination);
    this.analyser.fftSize = 512;
  }

  // ------------------------------------------------------- the client's face

  on(event: string, handler: Handler): void {
    const set = this.handlers.get(event) ?? new Set();
    set.add(handler);
    this.handlers.set(event, set);
    // The avatar subscribes when its runtime has arrived, after the call came
    // up: tell it what it missed, as a client that was already connected would
    // have told it in time.
    if (!this.connected) return;
    queueMicrotask(() => {
      if (!this.connected || !set.has(handler)) return;
      if (event === "connected" || event === "botReady") handler();
      else if (event === "trackStarted") handler(this.track, BOT);
    });
  }

  off(event: string, handler: Handler): void {
    this.handlers.get(event)?.delete(handler);
  }

  tracks(): { local: object; bot?: { audio?: MediaStreamTrack } } {
    return { local: {}, bot: this.connected ? { audio: this.track } : undefined };
  }

  /** The avatar's reports go nowhere: there is no far end. */
  sendClientMessage(): void {}

  private emit(event: string, ...args: unknown[]): void {
    for (const h of [...(this.handlers.get(event) ?? [])]) {
      try {
        h(...args);
      } catch (e) {
        console.warn(`preview voice: a ${event} handler threw`, e);
      }
    }
  }

  get track(): MediaStreamTrack {
    return this.out.stream.getAudioTracks()[0]!;
  }

  // ------------------------------------------------------------ the call

  connect(): void {
    if (this.connected) return;
    this.connected = true;
    this.emit("connected");
    this.emit("trackStarted", this.track, BOT);
    this.emit("botReady", {});
  }

  disconnect(): void {
    this.stop();
    if (!this.connected) return;
    this.connected = false;
    this.emit("trackStopped", this.track, BOT);
    this.emit("disconnected");
  }

  /** Whether this frame is heard. The face follows the voice either way. */
  setAudible(audible: boolean): void {
    this.speakers.gain.setTargetAtTime(audible ? 1 : 0, this.audio.currentTime, 0.02);
  }

  /** Start the audio clock. Works only during, or after, a click somewhere in the builder. */
  resume(): Promise<void> {
    return this.audio.state === "running" ? Promise.resolve() : this.audio.resume().catch(() => undefined);
  }

  /** Fetch and decode a clip, once. */
  load(clip: SpokenClip): Promise<AudioBuffer> {
    let b = this.buffers.get(clip.audio);
    if (!b) {
      b = fetch(new URL(`fixtures/${clip.audio}`, location.href))
        .then((r) => (r.ok ? r.arrayBuffer() : Promise.reject(new Error(`${clip.audio}: ${r.status}`))))
        .then((bytes) => this.audio.decodeAudioData(bytes));
      this.buffers.set(clip.audio, b);
    }
    return b;
  }

  /**
   * Speak a clip now, as a call would: its mouth cues just ahead of the audio,
   * the speaking events around it, and each sentence and word as it is said.
   * `onWord` and `onSentence` fire on the same clock, for the widget's captions.
   */
  async speak(clip: SpokenClip, hooks: { onSentence?(text: string): void; onWord?(text: string): void; onEnd?(): void } = {}): Promise<void> {
    const buffer = await this.load(clip);
    if (!this.connected) return;
    const ctx = `preview-${++this.contexts}`;
    if (clip.cues?.length) {
      this.emit("serverMessage", { type: "avatar", cmd: "cues", ctx, from_ms: 0, cues: clip.cues, final: true });
    }
    this.later(clip.cues?.length ? CUES_AHEAD_MS : 0, () => {
      // A clock that has not started (no click yet) would hold the clip and
      // play it late, over the next one: the words go by without it instead.
      if (this.audio.state === "running") {
        const source = this.audio.createBufferSource();
        source.buffer = buffer;
        source.connect(this.out);
        source.connect(this.speakers);
        source.connect(this.analyser);
        source.onended = () => this.playing.delete(source);
        this.playing.add(source);
        source.start();
      }
      this.emit("botStartedSpeaking");
      for (const s of clip.sentences) {
        this.later(s.words[0]?.at ?? 0, () => {
          this.emit("botOutput", { text: s.text, aggregated_by: "sentence", spoken_status: "new" });
          hooks.onSentence?.(s.text);
        });
        for (const w of s.words) {
          this.later(w.at, () => {
            this.emit("botTtsText", { text: w.text });
            hooks.onWord?.(w.text);
          });
        }
      }
      this.later(Math.max(buffer.duration * 1000, clip.ms), () => {
        this.emit("botStoppedSpeaking");
        hooks.onEnd?.();
      });
    });
  }

  /** The visitor's turn, as the client reports it: their mic level and when they spoke. */
  userSpeaking(on: boolean): void {
    this.emit(on ? "userStartedSpeaking" : "userStoppedSpeaking");
  }

  userLevel(level: number): void {
    this.emit("localAudioLevel", level);
  }

  /** The level on the track now, 0..1: the loudest sample of the last few ms. */
  level(): number {
    const data = new Float32Array(this.analyser.fftSize);
    this.analyser.getFloatTimeDomainData(data);
    let peak = 0;
    for (const v of data) peak = Math.max(peak, Math.abs(v));
    return peak;
  }

  private later(ms: number, run: () => void): void {
    const timer = setTimeout(() => {
      this.timers = this.timers.filter((t) => t !== timer);
      run();
    }, Math.max(0, ms));
    this.timers.push(timer);
  }

  /** Cut the voice and drop everything scheduled. The call stays up. */
  stop(): void {
    for (const t of this.timers) clearTimeout(t);
    this.timers = [];
    for (const s of this.playing) {
      try {
        s.stop();
      } catch {
        // Already stopped.
      }
    }
    this.playing.clear();
  }
}
