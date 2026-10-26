/**
 * His voice's loudness as a mouth shape, for the still on a page whose face
 * is not drawing yet (a full page load in a call; `shell.ts`).
 *
 * The holder measures his voice (`meter.ts`): the RMS of the newest ~20 ms
 * every relay tick, as the avatar's own level probe does, mapped to one of
 * four shapes with the same loudness thresholds. It sends a shape to the
 * pages when it changes, and again every `REPEAT_MS` while it is open, so a
 * page can tell an open mouth from a holder that went quiet (`LevelSender`).
 *
 * The page shows the shape on the still's mouth strip (`Mouth`): each shape
 * held at least `HOLD_MS`, so it does not flicker; closed `CLOSE_MS` after
 * the level drops to 0, so a gap between syllables does not snap it shut;
 * and closed when no level has come for `STALE_MS` (a busy page, or the
 * holder gone).
 *
 * Pure: no browser, unit-tested in `test/level.spec.ts`.
 */

/** A mouth shape, a frame of the strip: closed, small, medium, open. */
export type Shape = 0 | 1 | 2 | 3;

/** The avatar's loudness thresholds, on the RMS of a window of samples in
 *  [-1, 1]: at or under the first is closed. */
export const THRESHOLDS = [0.01, 0.04, 0.1] as const;

/** How long a window the RMS is taken over. */
export const WINDOW_MS = 20;
/** While open, the holder says the shape again this often. */
export const REPEAT_MS = 200;
/** A shape on the page is held at least this long. */
export const HOLD_MS = 60;
/** The level at 0 this long, the mouth closes. */
export const CLOSE_MS = 150;
/** No level for this long, the mouth closes. */
export const STALE_MS = 300;

/** The shape for an RMS. */
export function shapeOf(rms: number): Shape {
  if (!(rms > THRESHOLDS[0])) return 0;
  if (rms < THRESHOLDS[1]) return 1;
  if (rms < THRESHOLDS[2]) return 2;
  return 3;
}

/** The RMS of a window of samples. */
export function rmsOf(samples: ArrayLike<number>): number {
  if (!samples.length) return 0;
  let sum = 0;
  for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
  return Math.sqrt(sum / samples.length);
}

/** The analyser's window (a power of two, as an `AnalyserNode`'s `fftSize`
 *  must be) nearest `WINDOW_MS` at `sampleRate`. */
export function windowSize(sampleRate: number): number {
  const want = (sampleRate * WINDOW_MS) / 1000;
  const n = 2 ** Math.round(Math.log2(Math.max(32, want)));
  return Math.min(32768, n);
}

/** The holder's side: which shapes to send. */
export class LevelSender {
  private last: Shape = 0;
  private sentAt = -Infinity;

  /** The shape to send for this reading at `now` (ms), or `null` for none. */
  next(shape: Shape, now: number): Shape | null {
    if (shape === this.last && (shape === 0 || now - this.sentAt < REPEAT_MS)) return null;
    this.last = shape;
    this.sentAt = now;
    return shape;
  }
}

/** The page's side: the shape the still shows. */
export class Mouth {
  private shown: Shape = 0;
  private shownAt = -Infinity;
  private level: Shape = 0;
  private heardAt = -Infinity;
  private zeroSince: number | null = null;

  /** A level from the holder at `now` (ms). */
  hear(level: Shape, now: number): void {
    this.heardAt = now;
    if (level === 0) this.zeroSince ??= now;
    else this.zeroSince = null;
    this.level = level;
  }

  /** The shape to show at `now` (ms). */
  at(now: number): Shape {
    let want: Shape = this.level;
    if (now - this.heardAt > STALE_MS) want = 0;
    else if (want === 0 && this.zeroSince !== null && now - this.zeroSince < CLOSE_MS) want = this.shown;
    if (want !== this.shown && now - this.shownAt >= HOLD_MS) {
      this.shown = want;
      this.shownAt = now;
    }
    return this.shown;
  }

  /** Whether there is anything left to show: open, or a level still fresh. */
  busy(now: number): boolean {
    return this.shown !== 0 || now - this.heardAt <= STALE_MS;
  }
}
