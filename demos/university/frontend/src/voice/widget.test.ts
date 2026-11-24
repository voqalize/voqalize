import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PERSONA, jobFor, roleFor } from "../data/persona";
import { stillUrl } from "./Face";
import { LANG_KEY, loadLang, saveLang } from "./language";

const other = PERSONA.languages.find((l) => l !== PERSONA.default_language)!;

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
    expect(() => saveLang(other)).not.toThrow();
    expect(loadLang()).toBe(PERSONA.default_language);
  });
});

describe("the dock's role label follows the page", () => {
  it("names the brain's job for each landing", () => {
    expect(jobFor("/")).toBe("advisor");
    expect(jobFor("/programs/mba")).toBe("advisor");
    expect(jobFor("/admissions")).toBe("counsellor");
    expect(jobFor("/apply")).toBe("counsellor");
    expect(roleFor("/programs")).toBe(PERSONA.roles?.advisor);
    expect(roleFor("/apply")).toBe(PERSONA.roles?.counsellor);
  });
});

it("ships the still photo of the persona's character", () => {
  expect(stillUrl).toBeTruthy();
});
