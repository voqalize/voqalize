/**
 * The screen follows Javier's voice: cues fire as he says their sentence.
 *
 * The brain takes the cues out of his reply before the voice reads it (see
 * `backend/cues.py`) and sends each one ahead of the speech, with `at`, the
 * first words of the sentence it belongs to. The call's spoken-text events
 * (pipecat's `bot-output`, and `bot-tts-text` where it is sent) are released
 * as the audio plays, so a cue fires when those words are heard: the page moves
 * as the sentence begins, not when the model finished writing the reply.
 *
 * Cues fire in order, one move at a time — a page has to arrive before the
 * section on it can be found. A cue with no words after it (it ended the
 * reply) fires when the voice stops. If no spoken text has arrived a second
 * and a half into the speech, cues are timed instead, from `word`, the number
 * of words before each, at a speaking pace. When the visitor talks over him,
 * what he had not reached yet is dropped: it was never said.
 *
 * Cannon Home's pages load in full, so a cue that opens another page ends
 * this script mid-sentence. The cues still to come are handed over (`pending`)
 * and taken up by the next page (`restore`), where the call rejoins and the
 * rest of his sentence plays.
 */

import type { Cue } from "./actions.gen";

/** A cue's parts, whichever shape the brain sends: clini's
 *  `{path, heading, text, faq}` (what the cannonhome brain sends), or
 *  `{kind: page|show|faq, value}` (the demo's first contract). */
export function cueParts(cue: Cue): { path: string | null; heading: string | null; text: string | null; faq: string | null } {
  const c = cue as unknown as Record<string, unknown>;
  const str = (v: unknown) => (typeof v === "string" && v.trim() ? v.trim() : null);
  if (typeof c.kind === "string") {
    const value = str(c.value);
    return {
      path: c.kind === "page" ? value : null,
      heading: c.kind === "show" ? value : null,
      text: null,
      faq: c.kind === "faq" ? value : null,
    };
  }
  return { path: str(c.path), heading: str(c.heading), text: str(c.text), faq: str(c.faq) };
}


/** Words a second, for cues timed by the clock. Javier's voice runs close to
 *  this; a little early is better than late. */
const WORDS_PER_S = 2.8;
/** How long into the speech with no spoken text before cues go by the clock. */
const NO_TEXT_MS = 1500;
/** After the voice stops, how long before the cues left are fired anyway. */
const AFTER_STOP_MS = 600;
/** A cue whose words never come is dropped after this. */
const STALE_MS = 45_000;

/** Lower case, accents folded ("Sábanas" is "sabanas"), as `backend/cues.py`
 *  folds the cue's words: the voice's text and the cue meet in one spelling. */
const words = (text: string) =>
  (
    text
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/’/g, "'")
      .match(/[a-z0-9']+/g) ?? []
  ).join(" ");

interface Waiting {
  cue: Cue;
  /** The cue's words, folded as the voice's are. */
  at: string;
  /** Where in `heard` its words may start: after the cues before it. */
  from: number;
  born: number;
}

/** Whether `path` is another page than the one this tab shows. */
function elsewhere(path: string): boolean {
  const strip = (p: string) => p.replace(/\/+$/, "").toLowerCase() || "/";
  return strip(new URL(path, location.origin).pathname) !== strip(location.pathname);
}

export class Narration {
  private heard = "";
  private queue: Waiting[] = [];
  /** Fired, and waiting their turn behind the move before them. */
  private firing: Cue[] = [];
  /** Set once the page is leaving: nothing more moves here. */
  private held = false;
  private chain: Promise<void> = Promise.resolve();
  private speakingSince = 0;
  private textSince = false;
  private stopTimer: ReturnType<typeof setTimeout> | null = null;
  private clock: ReturnType<typeof setInterval> | null = null;

  /** @param move performs one cue; resolves once the page has moved. */
  constructor(private readonly move: (cue: Cue) => Promise<void>) {}

  add(cue: Cue): void {
    // A reply that opens on another page moves there at once, before he
    // speaks: the page loads in full and the call rejoins, so a load started
    // on his first words cut them off for seconds (dev). Started now, the load
    // overlaps the reply being written, and he speaks on the new page.
    const path = cueParts(cue).path;
    if (path && cue.word === 0 && !this.queue.length && !this.firing.length && elsewhere(path)) {
      this.fire(cue);
      return;
    }
    this.queue.push({ cue, at: words(cue.at), from: Math.max(0, this.heard.length - 120), born: Date.now() });
    this.check();
    this.tick();
  }

  /** The cues not yet performed: fired and waiting, then queued. */
  pending(): Cue[] {
    return [...this.firing, ...this.queue.map((q) => q.cue)];
  }

  /** Take up the cues the last page left (`pending`), as though just sent:
   *  their words are still to be spoken. */
  restore(cues: readonly Cue[]): void {
    for (const cue of cues) this.add(cue);
  }

  /** The page is leaving: what has not moved yet stays pending, for the next. */
  hold(): void {
    this.held = true;
  }

  /** Spoken text, as the voice plays it. */
  hear(text: string): void {
    const w = words(text);
    if (!w) return;
    this.textSince = true;
    this.heard += ` ${w}`;
    if (this.heard.length > 6000) {
      const cut = this.heard.length - 3000;
      this.heard = this.heard.slice(cut);
      for (const q of this.queue) q.from = Math.max(0, q.from - cut);
    }
    this.check();
  }

  speaking(): void {
    if (this.stopTimer) clearTimeout(this.stopTimer);
    this.stopTimer = null;
    if (!this.speakingSince) {
      this.speakingSince = Date.now();
      this.textSince = false;
    }
    this.tick();
  }

  stopped(): void {
    if (this.stopTimer) clearTimeout(this.stopTimer);
    this.stopTimer = setTimeout(() => {
      this.speakingSince = 0;
      // What is left belonged to words already said: show it now.
      const left = this.queue;
      this.queue = [];
      for (const q of left) this.fire(q.cue);
    }, AFTER_STOP_MS);
  }

  /** The visitor talked over him: the rest was never said. */
  interrupted(): void {
    this.queue = [];
    this.speakingSince = 0;
  }

  private check(): void {
    while (this.queue.length) {
      const q = this.queue[0];
      if (Date.now() - q.born > STALE_MS) {
        this.queue.shift();
        continue;
      }
      if (!q.at) return; // waits for the voice to stop
      const at = this.heard.indexOf(q.at, q.from);
      if (at < 0) return;
      this.queue.shift();
      // Later cues are found from here on, not after these words: two cues on
      // one sentence ({page: /}{show: …}) share them and fire together.
      for (const later of this.queue) later.from = Math.max(later.from, at);
      this.fire(q.cue);
    }
  }

  /** The clock, for a voice that sends no spoken text. */
  private tick(): void {
    if (this.clock || !this.queue.length) return;
    this.clock = setInterval(() => {
      if (!this.queue.length) {
        clearInterval(this.clock!);
        this.clock = null;
        return;
      }
      if (!this.speakingSince || this.textSince) return;
      const elapsed = Date.now() - this.speakingSince;
      if (elapsed < NO_TEXT_MS) return;
      while (this.queue.length && this.queue[0].at && elapsed >= (this.queue[0].cue.word / WORDS_PER_S) * 1000) {
        this.fire(this.queue.shift()!.cue);
      }
    }, 200);
  }

  private fire(cue: Cue): void {
    this.firing.push(cue);
    this.chain = this.chain
      .then(() => {
        if (this.held) return;
        this.firing.splice(this.firing.indexOf(cue), 1);
        return this.move(cue);
      })
      .catch(() => {});
  }
}
