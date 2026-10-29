/**
 * `@voqalize/stage`: the page half of Stage.
 *
 * The agent names moves inside its reply (cues) or through its tools; the page
 * makes them as the voice reaches them, rings what it points at, and reports
 * one `StageResult` per move. It works on a pipecat client the page already
 * has, and never makes, connects or wraps one.
 */

export * from "./wire.gen.js";
export { fold, words } from "./words.js";
export {
  AFTER_STOP_MS, type Dropped, type Fired, FUZZY_AFTER_MS, NO_TEXT_MS, STALE_MS, START_CPS, Timeline,
  type TimelineOptions, type TimelineStats,
} from "./timeline.js";
export { type RingOptions, Spotlight, type SpotlightTheme } from "./spotlight.js";
export {
  accessibleName, clean, domSettled, FIXED_DEFAULT, locate, type Locator, pinnedHeight, press, quiet, reveal, scrollToEl, setValue,
  SETTLE_MAX_MS, SETTLE_QUIET_MS, sleep, type Strategy, visible, waitFor,
} from "./dom.js";
export {
  AGENT_WINDOW_MS, arrived, type Carried, type Carrier, Deferred, type MoveClass, type MoveContext, Moves, type MovesOptions,
  type PerformResult, type Performer, Refused, type Then,
} from "./moves.js";
export {
  type Attached, attachStage, type AttachOptions, type ClientHandler, interruptedResult, STAGE_CONTRACT, STAGE_RUNTIME, type StageClient,
  staleResult,
} from "./attach.js";
export { type StagePage, stagePage } from "./page.js";
export {
  type ArgSpec, type ArgsOf, defineScene, type ItemSpec, type MoveId, type MoveSpec, type Performers, type Scene,
  type SceneSpec, type EventData, type EventId, type EventSpec, type FieldSpec, type SliceOf, type SliceSpec,
} from "./scene.js";
export { type PluginContext, PluginError, type PluginImpl, Plugins, type PluginSpec } from "./plugins.js";
export { ATTR, findPart, findThing, partsOf, place, pressParts, showThing, type Thing, things } from "./markup.js";
export { type FormState, formState, type Viewed, watchForms, type WatchOptions, watchThings } from "./watch.js";
