/**
 * Which browser's help text the coach mark shows. A web page cannot point at
 * the browser's own permission prompt, so the coach mark says where it is,
 * and that differs by browser and device.
 *
 * No dependencies; used by the launcher's page as well as the elements.
 */

export type BrowserKind = "chrome" | "edge" | "firefox" | "safari" | "ios" | "android" | "other";

export interface BrowserHints {
  userAgent?: string;
  /** `navigator.maxTouchPoints`: iPadOS reports a Mac user agent with touch. */
  maxTouchPoints?: number;
}

export function detectBrowser(hints: BrowserHints = readHints()): BrowserKind {
  const ua = hints.userAgent ?? "";
  const touch = (hints.maxTouchPoints ?? 0) > 1;
  if (/iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && touch)) return "ios";
  if (/Android/.test(ua)) return "android";
  if (/Edg\//.test(ua)) return "edge";
  if (/Firefox\//.test(ua)) return "firefox";
  if (/Chrome\/|Chromium\//.test(ua)) return "chrome";
  if (/Safari\//.test(ua)) return "safari";
  return "other";
}

function readHints(): BrowserHints {
  try {
    return { userAgent: globalThis.navigator?.userAgent, maxTouchPoints: globalThis.navigator?.maxTouchPoints };
  } catch {
    return {};
  }
}

/** The words key for a coach mark in this browser, e.g. `coach.blocked.safari`. Edge reads as Chrome. */
export function coachKey(state: "asking" | "blocked" | "missing", browser: BrowserKind): string {
  if (state === "missing") return "coach.missing";
  const variant = browser === "chrome" || browser === "edge" || browser === "other" ? "" : `.${browser}`;
  return `coach.${state}${variant}`;
}
