/**
 * A Site Agent's settings, read as a widget configuration.
 *
 * The Site Agent stores its look in the site's `SiteSettings` (the control
 * plane's site bundle). That schema does not change for the widget: this is a
 * mapping in code, from the fields the Site Agent already has to the widget
 * fields that mean the same thing. Everything the settings do not say is left
 * to the widget's defaults, and the result goes through `parseWidgetConfig()`
 * like any other configuration, so a stored value the widget cannot use falls
 * back with a warning instead of failing.
 *
 * - `position` → `placement.anchor`
 * - `colours.accent`, `.background`, `.text` → `theme.brand`, `.background`, `.ink`
 * - `avatar.enabled: false` → `avatar: false`
 * - `avatar.character` → `avatar.character`, with the retired "ira" read as
 *   the Site Agent's own fallback character
 * - `assistant_name` → `name`
 * - `greeting` is spoken, not drawn, so it is returned beside the configuration
 *   for the session to send at connect, not inside it.
 */

import { parseWidgetConfig } from "./parse.js";
import type { Anchor, Warn, WidgetConfig, WidgetConfigInput } from "./types.js";

/** The fields of a Site Agent's settings this mapping reads. Everything is optional. */
export interface SiteSettingsLike {
  assistant_name?: string | null;
  avatar?: { enabled?: boolean | null; character?: string | null } | null;
  colours?: { accent?: string | null; background?: string | null; text?: string | null } | null;
  position?: string | null;
  greeting?: string | null;
}

/**
 * The character a stored "ira" is shown as. The avatar runtime has no "ira";
 * the Site Agent reads it as this one (sitekit's `AVATAR_FALLBACK`).
 */
export const RETIRED_CHARACTERS: Readonly<Record<string, string>> = { ira: "tara" };

export interface FromSiteSettings {
  config: WidgetConfig;
  /** The first line the agent says, for the session's init values. */
  greeting?: string;
}

/** The widget input the settings describe, before defaults. */
export function siteSettingsToInput(settings: SiteSettingsLike | null | undefined): WidgetConfigInput {
  const input: WidgetConfigInput = {};
  if (!settings || typeof settings !== "object") return input;

  // Passed through as stored: a position the widget does not know falls back
  // in the parser, with a warning, rather than being guessed at here.
  if (settings.position) input.placement = { anchor: settings.position as Anchor };

  const colours = settings.colours;
  if (colours) {
    const theme: NonNullable<WidgetConfigInput["theme"]> = {};
    if (colours.accent) theme.brand = colours.accent;
    if (colours.background) theme.background = colours.background;
    if (colours.text) theme.ink = colours.text;
    if (Object.keys(theme).length > 0) input.theme = theme;
  }

  const avatar = settings.avatar;
  if (avatar && avatar.enabled === false) {
    input.avatar = false;
  } else if (avatar?.character) {
    input.avatar = { character: RETIRED_CHARACTERS[avatar.character] ?? avatar.character };
  }

  if (settings.assistant_name) input.name = settings.assistant_name;
  return input;
}

/**
 * Read a Site Agent's settings into a widget configuration plus its greeting.
 * `overrides` is laid over the mapped settings field by field, for a page that
 * wants the Site Agent's look with one thing changed.
 */
export function widgetConfigFromSiteSettings(
  settings: SiteSettingsLike | null | undefined,
  overrides: WidgetConfigInput = {},
  warn?: Warn,
): FromSiteSettings {
  const mapped = siteSettingsToInput(settings);
  const config = parseWidgetConfig(mergeInput(mapped, overrides), warn);
  const greeting = settings?.greeting?.trim();
  return greeting ? { config, greeting } : { config };
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** `over` laid on `base`: objects merge, anything else replaces. */
export function mergeInput<T>(base: T, over: unknown): T {
  if (!isObject(base) || !isObject(over)) return (over === undefined ? base : over) as T;
  const out: Record<string, unknown> = { ...base };
  for (const [key, value] of Object.entries(over)) {
    out[key] = key in out ? mergeInput(out[key], value) : value;
  }
  return out as T;
}
