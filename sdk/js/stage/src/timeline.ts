/**
 * The screen follows the voice: each cue fires as the voice reaches the words
 * it was written before.
 *
 * The agent's reply carries its cues inline; they are taken out before the
 * voice reads the reply and arrive here ahead of the speech, each with `at`,
 * the spoken text that follows it, and `before`, how many characters of its
 * unit were said before it. The call's spoken-text events are released as the
 * audio plays, so a cue fires when the first words of its `at` are heard: the
 * page moves as the sentence starts, not when the model finished writing.
 *
 *   - Anchor: the first three words of `at` (fewer when `at` has fewer), cut
 *     by `words()`, found in order in the heard words at or after the cue's
 *     search cursor. Once 1.5 s have passed since the anchor was due, two of
 *     the three are enough (`fuzzy`).
 *   - Clock: with no spoken text 1.5 s into the speech, a cue fires `before /
 *     cps` seconds after the speech started. `cps` starts at 14 and is
 *     recalibrated from this call's own spoken-text rate.
 *   - End: a cue with an empty `at` ended its reply and fires 600 ms after the
 *     voice stops, as does any cue whose words were due by then.
 *   - Stale: a cue whose words never come is dropped after 45 s.
 *   - Interrupted: when the person talks over the voice, every cue not yet
 *     performed is dropped and handed back, so each can be reported.
 *
 * Cues fire in order, one move at a time: a page must arrive before a section
 * on it can be found. `clear()` ends everything, including a move already
 * waiting its turn.
 */

import type { StageCue, StageResult } from "./wire.gen";
import { words } from "./words";

/** Characters a second, before this call's own rate is known. */
export const START_CPS = 14;
/** With no spoken text this long into the speech, cues go by the clock. */
export const NO_TEXT_MS = 1500;
/** How long past its due time before an anchor may match two words of three. */
export const FUZZY_AFTER_MS = 1500;
/** After the voice stops, how long before a reply's last cues fire. */
export const AFTER_STOP_MS = 600;
/** A cue whose words never come is dropped after this. */
export const STALE_MS = 45_000;
/** How many heard words before a new cue its search may start, for a cue that
 *  arrives a moment after its words began to play. */
const LOOKBACK_WORDS = 12;
const ANCHOR_WORDS = 3;
const MAX_HEARD = 4000;

export type Fired = "anchor" | "fuzzy" | "clock" | "end";
export type Dropped = "interrupted" | "stale";

export interface TimelineOptions {
  /** The call's language, for the segmenter and lower-casing. */
  lang?: string;
  /** Epoch milliseconds; injectable for tests. */
  now?: () => number;
  /** A cue was dropped without firing (stale). Interrupted cues are returned
   *  by `interrupted()` instead. */
  onDrop?: (cue: StageCue, why: Dropped) => void;
  /** A cue fired, and how it was matched: for telemetry. */
  onFire?: (cue: StageCue, how: Fired) => void;
}

interface Waiting {
  cue: StageCue;
  anchor: string[];
  /** Index into `heard` where its words may start. */
  from: number;
  born: number;
}

export interface TimelineStats {
  anchor: number;
  fuzzy: number;
  clock: number;
  end: number;
  stale: number;
  interrupted: number;
}

export class Timeline {
  private heard: string[] = [];
  private queue: Waiting[] = [];
  /** Fired, and waiting their turn behind the move before them. */
  private firing: StageCue[] = [];
  private chain: Promise<unknown> = Promise.resolve();
  private speakingSince = 0;
  private textSince = false;
  /** Characters of spoken text heard in this run of speech, for the rate. */
  private runChars = 0;
  private cps = START_CPS;
  private stopTimer: ReturnType<typeof setTimeout> | null = null;
  private ticker: ReturnType<typeof setInterval> | null = null;
  /** Moves on each `clear`: a cue queued before it is never performed after. */
  private epoch = 0;
  private readonly now: () => number;
  readonly stats: TimelineStats = { anchor: 0, fuzzy: 0, clock: 0, end: 0, stale: 0, interrupted: 0 };

  /** @param fire performs one cue; the next waits until it settles. */
  constructor(
    private readonly fire: (cue: StageCue) => Promise<StageResult | void>,
    private readonly opts: TimelineOptions = {},
  ) {
    this.now = opts.now ?? Date.now;
  }

  /** The call's language moved: words are cut its way from now on. */
  setLang(lang: string): void {
    this.opts.lang = lang;
  }

  /** The characters-per-second the clock fallback uses now. */
  get rate(): number {
    return this.cps;
  }

  add(cue: StageCue): void {
    const anchor = words(cue.at ?? "", this.opts.lang).slice(0, ANCHOR_WORDS);
    this.queue.push({ cue, anchor, from: Math.max(0, this.heard.length - LOOKBACK_WORDS), born: this.now() });
    this.check();
    this.tick();
  }

  /** Spoken text, as the voice plays it. */
  hear(text: string): void {
    const w = words(text, this.opts.lang);
    if (!w.length) return;
    this.textSince = true;
    this.runChars += text.trim().length;
    this.heard.push(...w);
    if (this.heard.length > MAX_HEARD) {
      const cut = this.heard.length - MAX_HEARD / 2;
      this.heard = this.heard.slice(cut);
      for (const q of this.queue) q.from = Math.max(0, q.from - cut);
    }
    this.check();
  }

  speaking(): void {
    if (this.stopTimer) clearTimeout(this.stopTimer);
    this.stopTimer = null;
    if (!this.speakingSince) {
      this.speakingSince = this.now();
      this.textSince = false;
      this.runChars = 0;
    }
    this.tick();
  }

  stopped(): void {
    if (this.stopTimer) clearTimeout(this.stopTimer);
    this.recalibrate();
    this.stopTimer = setTimeout(() => {
      this.stopTimer = null;
      const since = this.speakingSince;
      const elapsed = since ? this.now() - since : 0;
      this.speakingSince = 0;
      // A reply's last cues, and any whose words were due by now: those words
      // were said.
      const keep: Waiting[] = [];
      for (const q of this.queue) {
        if (!q.anchor.length || (since && this.due(q) <= elapsed)) this.release(q.cue, "end");
        else keep.push(q);
      }
      this.queue = keep;
    }, AFTER_STOP_MS);
  }

  /** The person talked over the voice: every cue not yet performed is
   *  dropped, and returned so each can be reported. */
  interrupted(): StageCue[] {
    const dropped = [...this.firing, ...this.queue.map((q) => q.cue)];
    this.firing = [];
    this.queue = [];
    this.speakingSince = 0;
    if (this.stopTimer) clearTimeout(this.stopTimer);
    this.stopTimer = null;
    this.stats.interrupted += dropped.length;
    return dropped;
  }

  /** The cues not yet performed: fired and waiting their turn, then queued. */
  pending(): StageCue[] {
    return [...this.firing, ...this.queue.map((q) => q.cue)];
  }

  /** The call ended: nothing more moves. */
  clear(): void {
    this.queue = [];
    this.firing = [];
    this.heard = [];
    this.speakingSince = 0;
    this.epoch++;
    if (this.stopTimer) clearTimeout(this.stopTimer);
    this.stopTimer = null;
    if (this.ticker) clearInterval(this.ticker);
    this.ticker = null;
  }

  /** Milliseconds after the speech started that a cue is due by the clock. */
  private due(q: Waiting): number {
    return ((q.cue.before ?? 0) / this.cps) * 1000;
  }

  private recalibrate(): void {
    if (!this.speakingSince || !this.textSince) return;
    const secs = (this.now() - this.speakingSince) / 1000;
    if (secs < 1 || this.runChars < 40) return;
    const measured = Math.min(30, Math.max(6, this.runChars / secs));
    this.cps = this.cps * 0.6 + measured * 0.4;
  }

  private check(): void {
    while (this.queue.length) {
      const q = this.queue[0]!;
      if (this.now() - q.born > STALE_MS) {
        this.queue.shift();
        this.stats.stale++;
        this.opts.onDrop?.(q.cue, "stale");
        continue;
      }
      if (!q.anchor.length) return; // waits for the voice to stop
      let found = indexOf(this.heard, q.anchor, q.from);
      let how: Fired = "anchor";
      if (found < 0 && q.anchor.length === ANCHOR_WORDS && this.late(q)) {
        found = fuzzyIndexOf(this.heard, q.anchor, q.from);
        how = "fuzzy";
      }
      if (found < 0) return;
      this.queue.shift();
      // Later cues are searched for from here on, not after these words: two
      // cues before one sentence share its anchor and fire together, in order.
      for (const later of this.queue) later.from = Math.max(later.from, found);
      this.release(q.cue, how);
    }
  }

  /** Past its due time by more than the fuzzy grace. */
  private late(q: Waiting): boolean {
    const start = this.speakingSince || q.born;
    return this.now() > Math.max(start + this.due(q), q.born) + FUZZY_AFTER_MS;
  }

  /** The clock, for a voice with no spoken text; and a re-check, since a
   *  fuzzy match and staleness depend on time passing too. */
  private tick(): void {
    if (this.ticker || !this.queue.length) return;
    this.ticker = setInterval(() => {
      if (!this.queue.length) {
        clearInterval(this.ticker!);
        this.ticker = null;
        return;
      }
      this.check();
      if (!this.speakingSince || this.textSince) return;
      const elapsed = this.now() - this.speakingSince;
      if (elapsed < NO_TEXT_MS) return;
      while (this.queue.length && this.queue[0]!.anchor.length && elapsed >= this.due(this.queue[0]!)) {
        this.release(this.queue.shift()!.cue, "clock");
      }
    }, 100);
  }

  private release(cue: StageCue, how: Fired): void {
    this.stats[how]++;
    this.opts.onFire?.(cue, how);
    const epoch = this.epoch;
    this.firing.push(cue);
    this.chain = this.chain
      .then(() => {
        if (epoch !== this.epoch) return;
        const i = this.firing.indexOf(cue);
        if (i < 0) return; // dropped meanwhile
        this.firing.splice(i, 1);
        return this.fire(cue);
      })
      .catch(() => {});
  }
}

function indexOf(heard: string[], anchor: string[], from: number): number {
  outer: for (let i = Math.max(0, from); i + anchor.length <= heard.length; i++) {
    for (let k = 0; k < anchor.length; k++) if (heard[i + k] !== anchor[k]) continue outer;
    return i;
  }
  return -1;
}

/** Two of the three anchor words: a window of three with two in place (one
 *  word misheard), or two of them side by side (one dropped). */
function fuzzyIndexOf(heard: string[], anchor: string[], from: number): number {
  const [a, b, c] = anchor as [string, string, string];
  for (let i = Math.max(0, from); i < heard.length; i++) {
    const w = heard.slice(i, i + 3);
    const inPlace = (w[0] === a ? 1 : 0) + (w[1] === b ? 1 : 0) + (w[2] === c ? 1 : 0);
    if (w.length === 3 && inPlace >= 2) return i;
    const [x, y] = w;
    if (y !== undefined && ((x === a && y === b) || (x === b && y === c) || (x === a && y === c))) return i;
  }
  return -1;
}
