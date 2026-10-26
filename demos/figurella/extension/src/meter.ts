/**
 * The holder's ear on his voice: how loud it is now, as a mouth shape, for
 * the still a page shows while its face is not drawing yet (`level.ts`).
 *
 * An `AnalyserNode` on the bot's remote audio track, read every relay tick
 * (23 ms) over the newest ~20 ms of samples. Nothing is played through the
 * context: his voice plays from the `<audio>` element as before, which is
 * also what keeps a remote WebRTC track flowing into Web Audio in Chrome.
 */

import { LevelSender, rmsOf, type Shape, shapeOf, windowSize } from "./level";

/** The relay's tick. */
const TICK_MS = 23;

export interface Metering {
  stop(): void;
}

/** Measure `track` and hand `send` each shape worth sending to the pages. */
export function meterVoice(track: MediaStreamTrack, send: (shape: Shape) => void): Metering {
  let ctx: AudioContext | null = null;
  let timer: ReturnType<typeof setInterval> | null = null;
  const sender = new LevelSender();
  try {
    ctx = new AudioContext();
    void ctx.resume().catch(() => {});
    const source = ctx.createMediaStreamSource(new MediaStream([track]));
    const analyser = ctx.createAnalyser();
    analyser.fftSize = windowSize(ctx.sampleRate);
    source.connect(analyser);
    const samples = new Float32Array(analyser.fftSize);
    timer = setInterval(() => {
      analyser.getFloatTimeDomainData(samples);
      const shape = sender.next(track.readyState === "live" ? shapeOf(rmsOf(samples)) : 0, performance.now());
      if (shape !== null) send(shape);
    }, TICK_MS);
  } catch {
    // No Web Audio here: the still keeps its mouth shut.
  }
  return {
    stop() {
      if (timer) clearInterval(timer);
      timer = null;
      void ctx?.close().catch(() => {});
      ctx = null;
      send(0);
    },
  };
}
