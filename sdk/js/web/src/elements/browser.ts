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

/**
 * The operating system, for advice that lives in its settings rather than
 * the browser's (which mic is chosen, its input level).
 */
export type OSKind = "mac" | "windows" | "ios" | "android" | "other";

export function detectOS(hints: BrowserHints = readHints()): OSKind {
  const ua = hints.userAgent ?? "";
  const touch = (hints.maxTouchPoints ?? 0) > 1;
  if (/iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && touch)) return "ios";
  if (/Android/.test(ua)) return "android";
  if (/Macintosh|Mac OS X/.test(ua)) return "mac";
  if (/Windows/.test(ua)) return "windows";
  return "other";
}

/** A coach mark's subject: the three mic states, and `check` for a mic that is on but silent. */
export type CoachState = "asking" | "blocked" | "missing" | "check";

/**
 * The words key for a coach mark in this browser, e.g. `coach.blocked.safari`.
 * Edge reads as Chrome. `check` varies by operating system, not browser.
 */
export function coachKey(state: CoachState, browser: BrowserKind, os: OSKind = "other"): string {
  if (state === "missing") return "coach.missing";
  if (state === "check") return os === "other" ? "coach.check" : `coach.check.${os}`;
  const variant = browser === "chrome" || browser === "edge" || browser === "other" ? "" : `.${browser}`;
  return `coach.${state}${variant}`;
}
