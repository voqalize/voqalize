/**
 * The one segmenter. A cue's `at` and the words the voice is heard saying are
 * both cut into words here, the same way, so they meet in one spelling in any
 * script: Latin with or without its accents, Devanagari, CJK, Arabic.
 *
 * Text is normalised with NFKC and lower-cased for the call's locale; curly
 * apostrophes become straight ones; Latin combining marks (U+0300–U+036F) are
 * stripped for comparison only, so "Sábanas" and "sabanas" match, while the
 * marks of other scripts (Devanagari's vowel signs, Arabic's harakat) are kept.
 * Words are the word-like segments of `Intl.Segmenter`, which also cuts the
 * scripts written without spaces; where it is missing, runs of letters, marks,
 * digits and apostrophes stand in.
 */

const LATIN_MARKS = /[̀-ͯ]/g;
const FALLBACK = /[\p{L}\p{M}\p{N}']+/gu;

type Segmenter = { segment(text: string): Iterable<{ segment: string; isWordLike?: boolean }> };
const segmenters = new Map<string, Segmenter | null>();

function segmenterFor(lang: string | undefined): Segmenter | null {
  const key = lang ?? "";
  if (segmenters.has(key)) return segmenters.get(key)!;
  let made: Segmenter | null = null;
  const Ctor = (Intl as unknown as { Segmenter?: new (lang?: string, o?: { granularity: string }) => Segmenter }).Segmenter;
  if (Ctor) {
    try {
      made = new Ctor(lang || undefined, { granularity: "word" });
    } catch {
      // An unknown tag: the default locale's rules.
      made = new Ctor(undefined, { granularity: "word" });
    }
  }
  segmenters.set(key, made);
  return made;
}

/** Text folded for comparison, before it is cut into words. */
export function fold(text: string, lang?: string): string {
  let s = text.normalize("NFKC");
  try {
    s = s.toLocaleLowerCase(lang || undefined);
  } catch {
    s = s.toLowerCase();
  }
  s = s.replace(/[‘’ʼ]/g, "'");
  // Latin accents only: decompose, drop U+0300–U+036F, compose what is left.
  return s.normalize("NFD").replace(LATIN_MARKS, "").normalize("NFC");
}

/** Cut text into comparable words. `useSegmenter: false` forces the fallback
 *  (tests, and engines without `Intl.Segmenter`). */
export function words(text: string, lang?: string, useSegmenter = true): string[] {
  const folded = fold(text, lang);
  const seg = useSegmenter ? segmenterFor(lang) : null;
  if (!seg) return folded.match(FALLBACK) ?? [];
  const out: string[] = [];
  for (const s of seg.segment(folded)) {
    if (!s.isWordLike) continue;
    // Some engines leave edge apostrophes on a word-like segment: trimmed, as
    // the fallback never starts a word with one it did not see.
    const w = s.segment.replace(/^'+|'+$/g, "");
    if (w) out.push(w);
  }
  return out;
}
