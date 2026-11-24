import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/** A browser's storage, in memory (Node's own `localStorage` global is empty
 *  without a file, and shadows the DOM's in tests). The same map across
 *  re-imports, as a reload keeps the browser's storage. */
function memoryStorage() {
  const m = new Map<string, string>();
  return {
    getItem: (k: string) => m.get(k) ?? null,
    setItem: (k: string, v: string) => void m.set(k, String(v)),
    removeItem: (k: string) => void m.delete(k),
    clear: () => m.clear(),
  };
}

describe("English only (H2: persona.json lists one language)", () => {
  beforeEach(() => {
    vi.stubGlobal("localStorage", memoryStorage());
    vi.resetModules();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("a Hindi this browser remembered from before is not offered: the call starts in English", async () => {
    localStorage.setItem("wanderloom-lang", "hi");
    const { useLang } = await import("./lang");
    expect(useLang.getState().lang).toBe("en");
  });

  it("asking for Hindi changes nothing, on or off a call", async () => {
    const { chooseLang, languageChanged, useLang } = await import("./lang");
    chooseLang("hi");
    expect(useLang.getState().lang).toBe("en");
    const sent: string[] = [];
    useLang.setState({ sender: (l) => sent.push(l) });
    chooseLang("hi");
    languageChanged({ language: "hi" });
    expect(sent).toEqual([]);
    expect(useLang.getState().lang).toBe("en");
  });
});

/** The toggle's behaviour when persona.json offers two languages again. */
describe("with two languages, the call's language survives a reload", () => {
  beforeEach(() => {
    vi.stubGlobal("localStorage", memoryStorage());
    vi.resetModules();
    vi.doMock("../persona", () => ({
      PERSONA: {
        defaultLanguage: "en",
        languages: [
          { tag: "en", label: "EN", name: "English" },
          { tag: "hi", label: "हिंदी", name: "Hindi" },
        ],
      },
    }));
  });
  afterEach(() => {
    vi.doUnmock("../persona");
    vi.unstubAllGlobals();
  });

  it("a pick off a call is remembered, and the next page load starts on it", async () => {
    const a = await import("./lang");
    a.chooseLang("hi");
    expect(a.useLang.getState().lang).toBe("hi");
    vi.resetModules();
    const b = await import("./lang");
    expect(b.useLang.getState().lang).toBe("hi");
  });

  it("on a call a press only asks; the brain's language_changed moves and saves it", async () => {
    const { chooseLang, languageChanged, useLang, LANG_KEY } = await import("./lang");
    const sent: string[] = [];
    useLang.setState({ sender: (l) => sent.push(l) });
    chooseLang("hi");
    expect(sent).toEqual(["hi"]);
    expect(useLang.getState().lang).toBe("en");
    languageChanged({ language: "hi" });
    expect(useLang.getState().lang).toBe("hi");
    expect(localStorage.getItem(LANG_KEY)).toBe("hi");
    languageChanged({ language: "fr" });
    expect(useLang.getState().lang).toBe("hi");
  });
});
