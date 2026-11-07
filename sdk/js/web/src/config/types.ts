/**
 * The widget configuration, as TypeScript.
 *
 * `widget-config.schema.json` is the source of truth: it holds every default
 * and every limit, and `parseWidgetConfig()` reads it at run time. These types
 * are its mirror for the compiler. `test/config.test.ts` holds the schema
 * and these types together — a full defaults literal of type `WidgetConfig` must equal what
 * the parser makes of `{}`, and a configuration that sets every field must
 * parse with no warning — so a field added to one and not the other fails a
 * test rather than drifting.
 */

export type Anchor =
  | "bottom-right"
  | "bottom-left"
  | "bottom-center"
  | "top-right"
  | "top-left"
  | "middle-right"
  | "middle-left";

export type AvatarShape = "circle" | "rounded" | "square";
export type AvatarFraming = "face" | "shoulders";
export type AvatarBackground = string | { url: string; fit: "cover" | "contain" };

export interface AvatarConfig {
  character?: string;
  shape: AvatarShape;
  framing: AvatarFraming;
  background: AvatarBackground;
  still?: string;
}

export type PlacementMode = "corner" | "inline" | "fullscreen";
export type MoveMode = "snap" | "free" | "fixed";
export type RememberMode = "tab" | "site" | "off";

export interface PlacementConfig {
  mode: PlacementMode;
  anchor: Anchor;
  move: MoveMode;
  remember: RememberMode;
  offset: number | { x: number; y: number };
  avoid: string[];
  topClear: number;
}

export interface LauncherConfig {
  style: "pill" | "face" | "card" | "none";
  label?: string;
  tagline?: string;
}

export interface OpenConfig {
  style: "card" | "hero";
  size: "small" | "medium" | "large";
}

export interface CollapsedConfig {
  style: "bubble" | "pill" | "none";
  autoCollapse: boolean;
}

export interface MobileConfig {
  open: "sheet" | "card" | "hero";
  launcher: "face" | "pill";
  breakpoint: number;
}

export interface ControlsConfig {
  mute: boolean;
  end: boolean;
  minimise: boolean;
  devices: boolean;
  language: boolean;
}

export interface MicConfig {
  level: "ring" | "bars" | "off";
  instantStart: boolean;
  silenceHint: boolean;
}

export type CaptionsMode = "off" | "karaoke" | "rolling";

export interface CaptionsConfig {
  mode: CaptionsMode;
  lines: number;
  /** A duration string ("4s", "800ms") or milliseconds. `parseDuration()` reads either. */
  linger: string | number;
  showUser: boolean;
  position: "card" | "under" | "page";
}

export interface ThemeConfig {
  brand?: string;
  background?: string;
  ink?: string;
  scheme: "auto" | "light" | "dark";
  radius?: number;
  font: string;
  tokens: Record<string, string>;
}

/** The widget's words: BCP-47 tag → key → text. */
export type Words = Record<string, Record<string, string>>;

/** A configuration with every default filled in: what the widget runs on. */
export interface WidgetConfig {
  agent?: string;
  key?: string;
  name?: string;
  avatar: false | AvatarConfig;
  placement: PlacementConfig;
  launcher: LauncherConfig;
  open: OpenConfig;
  collapsed: CollapsedConfig;
  mobile: MobileConfig;
  controls: ControlsConfig;
  mic: MicConfig;
  captions: CaptionsConfig;
  theme: ThemeConfig;
  words: Words;
  dir: "auto" | "ltr" | "rtl";
}

type DeepPartial<T> = T extends readonly (infer U)[]
  ? U[]
  : T extends object
    ? { [K in keyof T]?: DeepPartial<T[K]> }
    : T;

/** What a page writes: any subset of `WidgetConfig`, at any depth. */
export type WidgetConfigInput = {
  [K in keyof WidgetConfig]?: K extends "avatar"
    ? false | DeepPartial<AvatarConfig>
    : K extends "placement"
      ? Omit<DeepPartial<PlacementConfig>, "offset"> & { offset?: number | { x?: number; y?: number } }
      : K extends "theme"
        ? Omit<DeepPartial<ThemeConfig>, "tokens"> & { tokens?: Record<string, string> }
        : K extends "words"
          ? Words
          : DeepPartial<WidgetConfig[K]>;
};

/** Where a warning goes. Defaults to `console.warn`. */
export type Warn = (message: string) => void;
