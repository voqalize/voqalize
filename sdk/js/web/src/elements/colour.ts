/**
 * Contrast repair for the theme's colours, after the Site Agent snippet's
 * look: text on the brand colour, and ink on the background, are kept
 * readable whatever a configuration asks for.
 *
 * Only colours this file can read (hex and rgb()) are repaired. Anything else
 * (a named colour, a `var()`, a gradient) is used as given, because guessing
 * its luminance is worse than trusting the page.
 */

export type RGB = [number, number, number];

export function parseColour(value: string | undefined): RGB | null {
  if (!value) return null;
  const v = value.trim().toLowerCase();
  let m = /^#([0-9a-f]{3,4})$/.exec(v);
  if (m) {
    const h = m[1] as string;
    return [0, 1, 2].map((i) => parseInt(h.charAt(i) + h.charAt(i), 16)) as RGB;
  }
  m = /^#([0-9a-f]{6})([0-9a-f]{2})?$/.exec(v);
  if (m) {
    const h = m[1] as string;
    return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)) as RGB;
  }
  m = /^rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)/.exec(v);
  if (m) return [Number(m[1]), Number(m[2]), Number(m[3])].map((n) => Math.min(255, n)) as RGB;
  return null;
}

/** WCAG relative luminance. */
export function luminance([r, g, b]: RGB): number {
  const lin = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

export function contrast(a: RGB, b: RGB): number {
  const la = luminance(a);
  const lb = luminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

const BLACK: RGB = [17, 17, 17];
const WHITE: RGB = [255, 255, 255];

/** Black or white, whichever reads better on `background`. */
export function readableOn(background: RGB): "#111111" | "#ffffff" {
  return contrast(BLACK, background) >= contrast(WHITE, background) ? "#111111" : "#ffffff";
}

/** Body text needs 4.5:1 (WCAG AA). */
export const MIN_TEXT_CONTRAST = 4.5;

export interface ThemeColours {
  brand?: string;
  onBrand?: string;
  surface?: string;
  ink?: string;
}

/** The colours a theme configuration resolves to, repaired where they can be read. */
export function themeColours(theme: { brand?: string; background?: string; ink?: string }): ThemeColours {
  const out: ThemeColours = {};
  if (theme.brand) {
    out.brand = theme.brand;
    const rgb = parseColour(theme.brand);
    if (rgb) out.onBrand = readableOn(rgb);
  }
  if (theme.background) out.surface = theme.background;
  if (theme.ink) out.ink = theme.ink;
  const bg = parseColour(theme.background);
  if (bg) {
    const ink = parseColour(theme.ink);
    if (!ink || contrast(ink, bg) < MIN_TEXT_CONTRAST) out.ink = readableOn(bg);
  }
  return out;
}
