/**
 * Keep `@daily-co/daily-js` out of the bundle.
 *
 * Two packages import it, and neither import does anything here:
 * - pipecat's `SmallWebRTCTransport` imports it for `DailyMediaManager`, its
 *   default media manager. Every demo hands the transport
 *   `@voqalize/client-transport`'s manager instead (`src/media.ts`), so the
 *   default is never built.
 * - voice-ui-kit imports it to print daily's version when the transport is
 *   Daily's own, which ours never is.
 *
 * A static import is kept by the bundler whether or not it runs, so every demo
 * shipped all of daily-js. This Vite plugin points the package at
 * `no-daily-stub.mjs`, which throws if anything reaches it. Copying a demo? Copy
 * this plugin with it, or your page carries daily-js too.
 */
import { fileURLToPath } from "node:url";

const STUB = fileURLToPath(new URL("./no-daily-stub.mjs", import.meta.url));

export function noDaily() {
  return {
    name: "voqalize:no-daily",
    config: () => ({ resolve: { alias: { "@daily-co/daily-js": STUB } } }),
  };
}

/** Strings only daily-js itself carries: in built output, the real package got in. */
export const DAILY_MARKER = /DailyIframe|c\.daily\.co/;
