import { describe, expect, it } from "vitest";

import { words } from "../src/words";

describe("words", () => {
  for (const useSegmenter of [true, false]) {
    const w = (text: string, lang?: string) => words(text, lang, useSegmenter);
    describe(useSegmenter ? "Intl.Segmenter" : "fallback", () => {
      it("English: lower case, punctuation gone, apostrophes straight", () => {
        expect(w("Here’s the Observatory, at night.", "en")).toEqual(["here's", "the", "observatory", "at", "night"]);
      });

      it("Spanish: Latin accents folded for comparison, ñ too", () => {
        expect(w("Sábanas de algodón, ¡qué maravilla!", "es")).toEqual(["sabanas", "de", "algodon", "que", "maravilla"]);
        expect(w("Sabanas de ALGODON", "es")).toEqual(w("Sábanas de algodón", "es"));
        expect(w("El señor", "es")).toEqual(["el", "senor"]);
      });

      it("Hindi: Devanagari marks kept, the danda is not a word", () => {
        const out = w("यह कमरा बहुत सुंदर है। देखिए॥", "hi");
        expect(out).toEqual(["यह", "कमरा", "बहुत", "सुंदर", "है", "देखिए"]);
        // The vowel signs stay: "कमरा" is not "कमर".
        expect(out[1]).not.toBe("कमर");
      });

      it("Arabic: words, punctuation gone", () => {
        expect(w("مرحبا بكم، في الفندق!", "ar")).toEqual(["مرحبا", "بكم", "في", "الفندق"]);
      });

      it("NFKC: full-width Latin and compatibility forms meet their plain spelling", () => {
        expect(w("ＡＴＡＣＡＭＡ ﬁne", "en")).toEqual(["atacama", "fine"]);
      });
    });
  }

  it("Japanese: the segmenter cuts text written without spaces", () => {
    const out = words("東京の空はとても綺麗です。", "ja");
    expect(out.length).toBeGreaterThan(2);
    expect(out.join("")).toBe("東京の空はとても綺麗です");
    // The same text heard in two chunks cuts the same way at the joint's words.
    expect(words("東京の空は", "ja").slice(0, 2)).toEqual(out.slice(0, 2));
  });

  it("Japanese: the fallback keeps a run of script as one word", () => {
    expect(words("東京の空。綺麗", "ja", false)).toEqual(["東京の空", "綺麗"]);
  });
});
