/**
 * `no-daily.mjs`: alias `@daily-co/daily-js` to a stub. Typed structurally
 * rather than as vite's `Plugin` because `shared/` does not install vite.
 */
export function noDaily(): { name: string };
/** Matches only daily-js's own code, for checking built output. */
export const DAILY_MARKER: RegExp;
