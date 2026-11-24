import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { persona, roleFor } from "./persona";
import { LANG_KEY, loadLang, saveLang } from "./savedLang";
import { stillUrl } from "./voice/Face";

const other = persona.languages.find((l) => l.code !== persona.default_language)!.code;

/** A browser's storage, in memory. */
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

describe("the visitor's language survives a reload", () => {
  it("starts on the persona's default when nothing was used here", () => {
    expect(loadLang()).toBe(persona.default_language);
  });

  it("comes back as the language last used", () => {
    saveLang(other);
    expect(localStorage.getItem(LANG_KEY)).toBe(other);
    expect(loadLang()).toBe(other);
  });

  it("takes back only a language persona.json offers", () => {
    localStorage.setItem(LANG_KEY, "fr");
    expect(loadLang()).toBe(persona.default_language);
    saveLang("fr");
    expect(localStorage.getItem(LANG_KEY)).toBe("fr");
  });

  it("falls back to the default when storage throws", () => {
    vi.stubGlobal("localStorage", {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
    });
    expect(loadLang()).toBe(persona.default_language);
    expect(() => saveLang(other)).not.toThrow();
  });
});

describe("the widget reads persona.json", () => {
  it("has a still photo for the character", () => {
    expect(stillUrl).toBeTruthy();
  });

  it("labels each page with its role", () => {
    expect(roleFor("/")).toBe(persona.roles?.home);
    expect(roleFor("/book")).toBe(persona.roles?.book);
    expect(roleFor("/my-appointments")).toBe(persona.roles?.["my-appointments"]);
  });
});
