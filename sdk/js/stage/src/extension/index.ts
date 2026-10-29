/**
 * `@voqalize/stage/extension`: the Chrome MV3 host every site extension
 * shares. One call lives in an offscreen document (the holder) across every
 * page load on every host of the site; each page follows it, draws the
 * widget and the character's face, and makes the moves Stage sends it.
 *
 * A site extension writes its `SiteConfig` once and starts each entry point
 * with it:
 *
 *   content.ts     defineSiteExtension({ site, api, adapters, spotlight, … })
 *   shell.ts       startShell(site)                  (MAIN, document_start)
 *   bridge.ts      startBridge()                     (isolated, document_start)
 *   holder.ts      startHolder(site, { makeClient }) (call.html)
 *   background.ts  startBackground(site, { openable, justification })
 *   grant.ts       startGrant(words, site.opening)   (grant.html)
 */

export { type BackgroundConfig, startBackground } from "./background.js";
export { startBridge } from "./bridge.js";
export { CatchUp } from "./catch-up.js";
export {
  type Adapter, type AvatarClient, type AvatarHooks, defineSiteExtension, type PageKit, type SiteExtensionConfig, type SiteHooks,
} from "./content.js";
export { type FollowedClient, followCall, type Following } from "./follow.js";
export { type GrantWords, startGrant } from "./grant.js";
export {
  type HolderApi, type HolderCallbacks, type HolderClient, type HolderConfig, NO_PAGES_MS, QUIET_WAIT_MS, startHolder,
} from "./holder.js";
export {
  askHolder, askWorker, type FromBridge, loadsStarted, loadThen, onHolder, shareLanguage, sharedLanguage, tell,
} from "./hub.js";
export { carriedForward, type Delivery, HOLD_MS } from "./mouth-clock.js";
export { clearKept, FRESH_MS, type Kept, keptKey, readKept, transitions, writeKept } from "./persist.js";
export {
  type CallState, EVENTS, type FromPage, type HolderAsk, type Job, type MicState, PORT, type ToPage, type Where,
  type WorkerAsk,
} from "./protocol.js";
export { type RelayedClient, type Relaying, relayCall } from "./relay.js";
export { startShell } from "./shell.js";
export { defineSite, isSitePage, matchPattern, mountedFlag, type SiteConfig, shellFlag } from "./site.js";
export {
  type Activity, DEFAULT_TRANSITION_NAME, type Language, type Layout, mountWidget, type Rect, type Status,
  watchObstacles, type Widget, type WidgetConfig, widgetStyles, type WidgetTheme, type WidgetWords,
} from "./widget.js";
