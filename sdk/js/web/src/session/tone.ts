/**
 * The attention tone: a short beep that tells a visitor who is not looking
 * at the widget that their mic needs them.
 *
 * It plays only while the mic is not reaching the call (the hint is
 * `grant`, `blocked` or `missing`), first when the agent finishes its first
 * speech, then once more after `TONE_AGAIN_MS`, and never again in that
 * call. Never for `silent`: a quiet visitor is not a problem to sound an
 * alarm over.
 *
 * The audio context is made in the click that starts the call, where every
 * browser lets a page make sound, and closed when the call ends.
 */

/** How long after the first tone the second one plays, if the mic is still off. */
export const TONE_AGAIN_MS = 8000;

/** Something that can make the beep. */
export interface TonePlayer {
  play(): void;
  close(): void;
}

type AudioContextCtor = new () => AudioContext;

/** A WebAudio beep: a soft two-note sine, about a third of a second long. */
export function createTonePlayer(
  Ctor: AudioContextCtor | undefined = (globalThis as { AudioContext?: AudioContextCtor }).AudioContext ??
    (globalThis as { webkitAudioContext?: AudioContextCtor }).webkitAudioContext,
): TonePlayer | null {
  if (!Ctor) return null;
  let ctx: AudioContext;
  try {
    ctx = new Ctor();
  } catch {
    return null;
  }
  const note = (frequency: number, start: number, length: number) => {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = frequency;
    gain.gain.setValueAtTime(0, start);
    gain.gain.linearRampToValueAtTime(0.12, start + 0.015);
    gain.gain.exponentialRampToValueAtTime(0.0001, start + length);
    osc.connect(gain).connect(ctx.destination);
    osc.start(start);
    osc.stop(start + length + 0.02);
  };
  return {
    play() {
      try {
        void ctx.resume?.().catch(() => {});
        const t = ctx.currentTime + 0.02;
        note(880, t, 0.14);
        note(660, t + 0.17, 0.16);
      } catch {
        // No sound is better than a broken call.
      }
    },
    close() {
      try {
        void ctx.close?.().catch(() => {});
      } catch {
        // Already closed.
      }
    },
  };
}
