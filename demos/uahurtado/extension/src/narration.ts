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
 * Every move between the university's pages is a full page load, often to
 * another host. A reply whose first cue goes to another page moves there at
 * once, before he speaks, so the load overlaps the reply being written. A cue
 * that leaves the page takes the cues after it (`drain`), and the page it
 * loads makes the ones already due on arrival and waits for his voice to reach
 * the others (`restore`). A load the visitor made themselves stops the moves
 * (`hold`) and leaves what was owed (`pending`) for the next page.
 */

import type { Cue } from "./actions.gen";

/** Words a second, for cues timed by the clock. Javier's voice runs close to
 *  this; a little early is better than late. */
const WORDS_PER_S = 2.8;
/** How long into the speech with no spoken text before cues go by the clock. */
const NO_TEXT_MS = 1500;
/** After the voice stops, how long before the cues left are fired anyway. */
const AFTER_STOP_MS = 600;
/** A cue whose words never come is dropped after this. */
const STALE_MS = 45_000;
/** A restored cue whose words never come (the voice finished during the page
 *  load) is made after this anyway. */
const RESTORED_MS = 9000;

/** Words as the voice and the brain both spell them (`backend/cues.py`): lower
 *  case, accents folded ("Música" is "musica", "año" is "ano"), odd
 *  apostrophes straightened, punctuation gone. */
export const words = (text: string) =>
  (
    text
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[’‘´`]/g, "'")
      .match(/[a-z0-9']+/g) ?? []
  ).join(" ");

/** The cues a page left for the next: due now, and still waiting for words. */
export interface Rest {
  ready: Cue[];
  waiting: Cue[];
}

interface Waiting {
  cue: Cue;
  /** The cue's words, folded as the voice's are. */
  at: string;
  /** Where in `heard` its words may start: after the cues before it. */
  from: number;
  born: number;
}

export class Narration {
  private heard = "";
  private queue: Waiting[] = [];
  /** Cues due, in order, not yet made: each waits for the move before it. */
  private due: Cue[] = [];
  /** Set once the page is leaving: nothing more moves here. */
  private held = false;
  private chain: Promise<void> = Promise.resolve();
  private speakingSince = 0;
  private textSince = false;
  private stopTimer: ReturnType<typeof setTimeout> | null = null;
  private clock: ReturnType<typeof setInterval> | null = null;

  /**
   * @param move performs one cue; resolves once the page has moved.
   * @param elsewhere whether a cue's `url` is another page than this one.
   */
  constructor(
    private readonly move: (cue: Cue) => Promise<void>,
    private readonly elsewhere: (url: string) => boolean,
  ) {}

  add(cue: Cue): void {
    // A reply that opens on another page moves there at once, before he
    // speaks: the page loads in full and the call rejoins, so a load started
    // on his first words cut them off for seconds (dev). Started now, the load
    // overlaps the reply being written, and he speaks on the new page.
    if (cue.url && cue.word === 0 && !this.queue.length && !this.due.length && this.elsewhere(cue.url)) {
      this.fire(cue);
      return;
    }
    this.queue.push({ cue, at: words(cue.at), from: Math.max(0, this.heard.length - 120), born: Date.now() });
    this.check();
    this.tick();
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

  /** Take every cue not made yet — due, and waiting for its words — for the
   *  page this one is about to load. */
  drain(): Rest {
    const rest = { ready: this.due, waiting: this.queue.map((q) => q.cue) };
    this.due = [];
    this.queue = [];
    return rest;
  }

  /** The page is leaving: what has not moved yet stays, for the next page. */
  hold(): void {
    this.held = true;
  }

  /** What is still owed, without taking it (the page is leaving anyway). */
  pending(): Rest {
    return { ready: [...this.due], waiting: this.queue.map((q) => q.cue) };
  }

  /** What the page before left: the due cues are made now, the others when
   *  the voice reaches their words, or shortly anyway. */
  restore(rest: Rest): void {
    for (const cue of rest.ready) this.fire(cue);
    if (!rest.waiting.length) return;
    const restored = rest.waiting.map((cue) => ({ cue, at: words(cue.at), from: 0, born: Date.now() }));
    this.queue.push(...restored);
    this.check();
    this.tick();
    setTimeout(() => {
      const left = this.queue.filter((q) => restored.includes(q));
      if (!left.length) return;
      this.queue = this.queue.filter((q) => !left.includes(q));
      for (const q of left) this.fire(q.cue);
    }, RESTORED_MS);
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
      // one sentence ({page: …}{show: …}) share them and fire together.
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
    this.due.push(cue);
    this.chain = this.chain
      .then(() => {
        // Leaving, or drained for the next page meanwhile: nothing to make here.
        if (this.held) return;
        const next = this.due.shift();
        return next ? this.move(next) : undefined;
      })
      .catch(() => {});
  }
}
