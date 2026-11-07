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
export {
  MicController,
  type MicControllerOptions,
  type MicDeviceState,
  type MicSnapshot,
  type MicState,
  SILENCE_HINT_AFTER_MS,
  SILENCE_HINT_FLOOR,
  SILENCE_HINT_MAX_GAP_MS,
  type WireMicState,
  micStateForError,
  watchMicPermission,
} from "./controllers/mic.js";
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
// Importing these registers nothing; call `defineElements()` once.

export { ELEMENTS, defineElements } from "./elements/define.js";
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
export { VqlStatus, statusOf } from "./elements/status.js";
export { VqlEnd } from "./elements/end.js";
export { ENGLISH, type Translate, pageLanguage, tagChain, translator } from "./elements/words.js";
export { type BrowserHints, type BrowserKind, coachKey, detectBrowser } from "./elements/browser.js";
export { type ThemeColours, MIN_TEXT_CONTRAST, contrast, themeColours } from "./elements/colour.js";
export { TOKENS } from "./elements/theme.js";
export { type CssProps, cssProps } from "./elements/css-props.js";
