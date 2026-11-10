/**
 * The widget's configuration and its headless controllers: the logic without
 * our markup, for a page that draws its own.
 */

export type {
  Anchor,
  AvatarBackground,
  AvatarConfig,
  AvatarFraming,
  AvatarShape,
  CaptionsConfig,
  CaptionsMode,
  CollapsedConfig,
  ControlsConfig,
  LauncherConfig,
  MicConfig,
  MobileConfig,
  MoveMode,
  OpenConfig,
  PlacementConfig,
  PlacementMode,
  RememberMode,
  ThemeConfig,
  Warn,
  WidgetConfig,
  WidgetConfigInput,
  Words,
} from "./config/types.js";
export { WIDGET_CONFIG_SCHEMA, defaultWidgetConfig, parseDuration, parseWidgetConfig } from "./config/parse.js";
export {
  RETIRED_CHARACTERS,
  type FromSiteSettings,
  type SiteSettingsLike,
  siteSettingsToInput,
  widgetConfigFromSiteSettings,
} from "./config/site-settings.js";

export { type ReadableStore, Store } from "./controllers/store.js";
// The shapes a session gives the widget, for a page that implements
// `WidgetSessionLike` itself (a preview, a replay). Types only: the session
// that makes calls stays internal.
export type {
  AgentState,
  DeviceSnapshot,
  EndReason,
  SessionEvents,
  SessionSnapshot,
  SessionSource,
  SessionStatus,
} from "./session/adapter.js";
export {
  MicController,
  type MicControllerOptions,
  type MicHint,
  type MicSnapshot,
  type MicState,
  micIsOff,
} from "./controllers/mic.js";
export { type MicPillKind, type MicPillOptions, micPillOf } from "./controllers/mic-pill.js";
export {
  type CaptionLine,
  type CaptionWord,
  CaptionsController,
  type CaptionsOptions,
  type CaptionsSnapshot,
} from "./controllers/captions.js";
export {
  ANCHORS,
  BOTTOM_LIFT,
  type Margins,
  PlacementController,
  type PlacementOptions,
  type PlacementSnapshot,
  type Point,
  type Rect,
  type RememberedPlace,
  type Size,
  type Viewport,
  boxAt,
  clampPoint,
  clearPlace,
  fallbackOrder,
  marginsFrom,
  nearestAnchor,
  overlaps,
  rememberKey,
  rememberPlace,
  rememberedPlace,
} from "./controllers/placement.js";

// ---------------------------------------------------------------- elements
// Importing these registers nothing; call `defineElements()` once. The lazy
// ones register on first use, or all at once with `defineAllElements()`.

export { ELEMENTS, defineAllElements, defineElements } from "./elements/define.js";
export { LAZY_ELEMENTS, isLazyElement, loadElement } from "./elements/lazy.js";
export {
  CONFIG_ATTRIBUTES,
  VqlWidget,
  type WidgetForm,
  type WidgetSessionLike,
  type WidgetView,
  inputFromAttributes,
  neighbourAnchor,
} from "./elements/widget.js";
export { VqlLauncher, defineLauncher } from "./elements/launcher.js";
export {
  type AvatarLoader,
  type AvatarModuleLike,
  type ResolvedBackground,
  VqlFace,
  resolveBackground,
  setAvatarLoader,
} from "./elements/face.js";
export { VqlMic, meterLevel } from "./elements/mic.js";
export { VqlDevices } from "./elements/devices.js";
export { VqlCaptions } from "./elements/captions.js";
export { VqlCoach } from "./elements/coach.js";
export { type MicPillActionDetail, VqlMicPill } from "./elements/mic-pill.js";
export { VqlStatus, statusOf } from "./elements/status.js";
export { VqlEnd } from "./elements/end.js";
export { ENGLISH, type Translate, pageLanguage, tagChain, translator } from "./elements/words.js";
export {
  type BrowserHints,
  type BrowserKind,
  type CoachState,
  type OSKind,
  coachKey,
  detectBrowser,
  detectOS,
} from "./elements/browser.js";
export { type ThemeColours, MIN_TEXT_CONTRAST, contrast, themeColours } from "./elements/colour.js";
export { TOKENS } from "./elements/theme.js";
export { type CssProps, cssProps } from "./elements/css-props.js";
