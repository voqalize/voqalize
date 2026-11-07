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
