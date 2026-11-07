/**
 * Captions timed to what the visitor hears.
 *
 * The session drives it with these inputs, and each follows playout rather
 * than the text stream:
 *
 * - `agentSentence(text)` — a sentence as its first word starts to play
 *   (the client's `onBotOutput` with `spoken_status: "new"`). It lays out the
 *   words still to come, unlit.
 * - `agentWord(text)` — one word as its audio plays (`onBotTtsText`). It
 *   lights the next matching word.
 *
 * Karaoke shows the line being spoken with its spoken words lit and the rest
 * waiting; when the text reaches `lines`, the oldest line goes. Rolling shows
 * spoken words only, the docs style. When the agent stops, words it never
 * spoke are dropped — on a barge-in the line ends where the agent was cut
 * off — and the whole block clears `linger` after.
 *
 * Screen readers get each finished sentence once, as `announcement`, for a
 * polite live region: not each word, which would be read as a stutter.
 */

import type { CaptionsMode } from "../config/types.js";
import { Store } from "./store.js";

export interface CaptionWord {
  text: string;
  spoken: boolean;
  /** The word playing now. */
  current: boolean;
}

export interface CaptionLine {
  words: CaptionWord[];
}

export interface CaptionsSnapshot {
  visible: boolean;
  lines: CaptionLine[];
  /** What the visitor said last, when `showUser` is on. */
  user?: string;
  /** The latest finished sentence, for a polite live region. `id` changes per sentence. */
  announcement?: { id: number; text: string };
}

export interface CaptionsOptions {
  mode?: CaptionsMode;
  /** Lines shown at once. Default 2. */
  lines?: number;
  /** ms the captions stay after the agent stops. Default 4000. */
  lingerMs?: number;
  showUser?: boolean;
  /**
   * Characters that fit on a line. The element measures its own width and
   * sets this with `setCharsPerLine()`; the default suits a medium card.
   */
  charsPerLine?: number;
  setTimeout?: (fn: () => void, ms: number) => unknown;
  clearTimeout?: (handle: unknown) => void;
}

interface Sentence {
  words: string[];
  /** How many of `words` have played. */
  spoken: number;
  announced: boolean;
}

/** How far ahead an arriving word may match, past words the TTS skipped or merged. */
const MATCH_LOOKAHEAD = 3;

function normalise(word: string): string {
  return word.toLocaleLowerCase().replace(/[^\p{L}\p{N}]+/gu, "");
}

function splitWords(text: string): string[] {
  return text.split(/\s+/u).filter((w) => w.length > 0);
}

const EMPTY: CaptionsSnapshot = { visible: false, lines: [] };

export class CaptionsController extends Store<CaptionsSnapshot> {
  private mode: CaptionsMode;
  private maxLines: number;
  private lingerMs: number;
  private showUser: boolean;
  private charsPerLine: number;
  private readonly schedule: (fn: () => void, ms: number) => unknown;
  private readonly cancel: (handle: unknown) => void;

  private sentences: Sentence[] = [];
  /** The agent stopped; the next sentence starts a new block. */
  private stopped = true;
  private lingerTimer: unknown = null;
  private announceId = 0;
  private user: string | undefined;

  constructor(options: CaptionsOptions = {}) {
    super(EMPTY);
    this.mode = options.mode ?? "karaoke";
    this.maxLines = Math.max(1, Math.floor(options.lines ?? 2));
    this.lingerMs = Math.max(0, options.lingerMs ?? 4000);
    this.showUser = options.showUser ?? false;
    this.charsPerLine = Math.max(8, Math.floor(options.charsPerLine ?? 42));
    this.schedule = options.setTimeout ?? ((fn, ms) => setTimeout(fn, ms));
    this.cancel = options.clearTimeout ?? ((h) => clearTimeout(h as ReturnType<typeof setTimeout>));
  }

  setMode(mode: CaptionsMode): void {
    this.mode = mode;
    this.render();
  }

  /** Change the line count, the linger and `showUser` on a running controller, as a configuration change does. */
  configure(options: Pick<CaptionsOptions, "lines" | "lingerMs" | "showUser">): void {
    if (options.lines !== undefined) this.maxLines = Math.max(1, Math.floor(options.lines));
    if (options.lingerMs !== undefined) this.lingerMs = Math.max(0, options.lingerMs);
    if (options.showUser !== undefined) {
      this.showUser = options.showUser;
      if (!this.showUser) this.user = undefined;
    }
    this.render();
  }

  setCharsPerLine(chars: number): void {
    const next = Math.max(8, Math.floor(chars));
    if (next === this.charsPerLine) return;
    this.charsPerLine = next;
    this.render();
  }

  /** A sentence whose first word is starting to play. */
  agentSentence(text: string): void {
    const words = splitWords(text);
    if (words.length === 0) return;
    this.beginIfStopped();
    // A sentence the word stream already started (a word arrived first) is
    // this one: replace the provisional words, keep what has played.
    const last = this.sentences.at(-1);
    if (last && last.words.length === last.spoken && !last.announced && last.spoken > 0 && this.provisional) {
      this.provisional = false;
      last.words = words;
      last.spoken = Math.min(last.spoken, words.length);
      this.render();
      return;
    }
    this.provisional = false;
    // A sentence starts to play only once the ones before it have: any word
    // of theirs still unlit was one the voice said differently ("$5" read
    // as "five dollars"), so they are done. Otherwise their cursor would
    // hold every later word back.
    for (const earlier of this.sentences) earlier.spoken = earlier.words.length;
    this.finishSentences();
    this.sentences.push({ words, spoken: 0, announced: false });
    this.render();
  }

  /** Whether the last sentence was made up from words with no sentence yet. */
  private provisional = false;

  /** One word as its audio plays. */
  agentWord(text: string): void {
    const key = normalise(text);
    this.beginIfStopped();
    for (const sentence of this.sentences) {
      if (sentence.spoken >= sentence.words.length) continue;
      const limit = Math.min(sentence.words.length, sentence.spoken + MATCH_LOOKAHEAD);
      for (let i = sentence.spoken; i < limit; i++) {
        const word = sentence.words[i] as string;
        if (normalise(word) === key || (key.length > 0 && normalise(word).startsWith(key))) {
          sentence.spoken = i + 1;
          this.finishSentences();
          this.render();
          return;
        }
      }
      // The next unfinished sentence is the one playing. A word that matches
      // nothing near its cursor (a number the voice expanded, say) is
      // skipped: the cursor moves on at the next word that does match, and
      // the sentence is never lit out of order.
      return;
    }
    // A word with no sentence laid out for it: show it anyway.
    if (splitWords(text).length === 0) return;
    const last = this.sentences.at(-1);
    if (last && this.provisional) {
      last.words.push(text.trim());
      last.spoken = last.words.length;
    } else {
      this.sentences.push({ words: [text.trim()], spoken: 1, announced: false });
      this.provisional = true;
    }
    this.render();
  }

  /** The agent started speaking: hold the captions. */
  agentStarted(): void {
    this.clearLinger();
  }

  /**
   * The agent stopped, finished or cut off. Words it never spoke are
   * dropped, the cut sentence is announced as far as it got, and the block
   * clears after `linger`.
   */
  agentStopped(): void {
    for (const sentence of this.sentences) {
      if (sentence.spoken < sentence.words.length) sentence.words = sentence.words.slice(0, sentence.spoken);
    }
    this.sentences = this.sentences.filter((s) => s.words.length > 0);
    this.finishSentences();
    this.stopped = true;
    this.provisional = false;
    this.render();
    this.clearLinger();
    this.lingerTimer = this.schedule(() => {
      this.lingerTimer = null;
      this.sentences = [];
      this.render();
    }, this.lingerMs);
  }

  /** What the visitor said. Shown only with `showUser`, and only once final. */
  userTranscript(text: string, final: boolean): void {
    if (!this.showUser || !final) return;
    const trimmed = text.trim();
    if (!trimmed) return;
    this.user = trimmed;
    this.render();
  }

  /** Clear everything, as at the end of a call. */
  reset(): void {
    this.clearLinger();
    this.sentences = [];
    this.stopped = true;
    this.provisional = false;
    this.user = undefined;
    this.set({ visible: false, lines: [], user: undefined });
  }

  private beginIfStopped(): void {
    if (!this.stopped) return;
    this.stopped = false;
    this.clearLinger();
    this.sentences = [];
    this.provisional = false;
  }

  private clearLinger(): void {
    if (this.lingerTimer !== null) this.cancel(this.lingerTimer);
    this.lingerTimer = null;
  }

  private finishSentences(): void {
    for (const sentence of this.sentences) {
      if (sentence.announced || sentence.spoken === 0) continue;
      if (sentence.spoken < sentence.words.length) continue;
      if (this.provisional && sentence === this.sentences.at(-1) && !this.stopped) continue;
      sentence.announced = true;
      this.announceId += 1;
      this.set({ announcement: { id: this.announceId, text: sentence.words.join(" ") } });
    }
  }

  private render(): void {
    const rolling = this.mode === "rolling";
    const all: CaptionWord[] = [];
    let currentIndex = -1;
    for (const sentence of this.sentences) {
      sentence.words.forEach((text, i) => {
        const spoken = i < sentence.spoken;
        if (rolling && !spoken) return;
        if (spoken) currentIndex = all.length;
        all.push({ text, spoken, current: false });
      });
    }
    if (currentIndex >= 0 && !this.stopped) (all[currentIndex] as CaptionWord).current = true;

    const lines = this.wrap(all);
    // The line holding the current word is the last one shown: the words
    // after it have not been reached.
    let end = lines.length;
    if (currentIndex >= 0) {
      let seen = 0;
      for (let i = 0; i < lines.length; i++) {
        seen += (lines[i] as CaptionLine).words.length;
        if (seen > currentIndex) {
          end = i + 1;
          break;
        }
      }
    } else {
      end = Math.min(lines.length, 1);
    }
    const shown = lines.slice(Math.max(0, end - this.maxLines), end);
    const visible = this.mode !== "off" && (shown.length > 0 || this.user !== undefined);
    this.set({ visible, lines: this.mode === "off" ? [] : shown, user: this.user });
  }

  private wrap(words: CaptionWord[]): CaptionLine[] {
    const lines: CaptionLine[] = [];
    let line: CaptionWord[] = [];
    let length = 0;
    for (const word of words) {
      const add = (line.length > 0 ? 1 : 0) + word.text.length;
      if (line.length > 0 && length + add > this.charsPerLine) {
        lines.push({ words: line });
        line = [];
        length = 0;
      }
      length += (line.length > 0 ? 1 : 0) + word.text.length;
      line.push(word);
    }
    if (line.length > 0) lines.push({ words: line });
    return lines;
  }
}
