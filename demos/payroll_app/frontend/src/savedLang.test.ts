import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PERSONA } from "./persona";
import { LANG_KEY, loadLang, saveLang } from "./savedLang";
import { stillUrl } from "./voice/Face";

const other = PERSONA.languages.find((l) => l.code !== PERSONA.default_language)!.code;

/** A browser's storage, in memory (Node's own `localStorage` global is empty
 *  without a file, and shadows the DOM's in tests). */
function memoryStorage() {
  const m = new Map<string, string>();
  return {
    getItem: (k: string) => m.get(k) ?? null,
    setItem: (k: string, v: string) => void m.set(k, String(v)),
    removeItem: (k: string) => void m.delete(k),
    clear: () => m.clear(),
  };
}
beforeEach(() => vi.stubGlobal("localStorage", memoryStorage()));
afterEach(() => vi.unstubAllGlobals());

describe("the visitor's language survives a reload (round 2, R7)", () => {

  it("starts on the persona's default when nothing was used here", () => {
    expect(loadLang()).toBe(PERSONA.default_language);
  });

  it("comes back as the language last used", () => {
    saveLang(other);
    expect(localStorage.getItem(LANG_KEY)).toBe(other);
    expect(loadLang()).toBe(other);
  });

  it("takes back only a language persona.json offers", () => {
    localStorage.setItem(LANG_KEY, "fr");
    expect(loadLang()).toBe(PERSONA.default_language);
    saveLang("fr");
    expect(localStorage.getItem(LANG_KEY)).toBe("fr");
  });

  it("works with storage blocked", () => {
    const blocked = () => {
      throw new Error("blocked");
    };
    vi.stubGlobal("localStorage", { getItem: blocked, setItem: blocked });
    expect(() => saveLang(other)).not.toThrow();
    expect(loadLang()).toBe(PERSONA.default_language);
  });
});

describe("the idle dock shows the character's still photo (round 2, R5)", () => {
  it("has a photo for the character persona.json names", () => {
    expect(stillUrl).toBeTruthy();
    expect(stillUrl).toContain(PERSONA.avatar_character);
  });
});

describe("the toggle remembers", () => {
  it("a press or the brain's language_changed is saved, and the next page load starts on it", async () => {
    const { languageChanged, requestLanguage } = await import("./voice/lang");
    requestLanguage(other);
    expect(localStorage.getItem(LANG_KEY)).toBe(other);
    languageChanged({ language: PERSONA.default_language });
    expect(localStorage.getItem(LANG_KEY)).toBe(PERSONA.default_language);
    languageChanged({ language: other });
    vi.resetModules();
    const fresh = await import("./voice/lang");
    expect(fresh.useLang.getState().lang).toBe(other);
  });
});
