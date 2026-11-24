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

describe("the call's language survives a reload", () => {
  beforeEach(() => {
    vi.stubGlobal("localStorage", memoryStorage());
    vi.resetModules();
  });
  afterEach(() => vi.unstubAllGlobals());

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
