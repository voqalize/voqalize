/**
 * The theme every element shares: the public `--vql-*` tokens, their
 * defaults for light and dark, and the base rules.
 *
 * A token is read as `var(--vql-x, var(--_vql-cfg-x, default))`:
 *
 * - `--vql-x`, set by the page on the element or any ancestor, wins;
 * - `--_vql-cfg-x` is what the widget's configuration set (`theme.brand`
 *   and the rest), so a page's CSS can still override a configured colour;
 * - the default follows the colour scheme.
 *
 * `theme.tokens` in the configuration sets `--vql-*` on the element itself,
 * which is the same as the page setting them there.
 *
 * The scheme is `auto` (the visitor's `prefers-color-scheme`) unless the
 * element carries `scheme="light"` or `scheme="dark"`, which the widget
 * passes down to every part it renders. The widget itself marks the scheme
 * its configuration chose as `data-scheme`, so its own `scheme` attribute
 * stays the page's.
 */

import { css } from "lit";

/** The public tokens, by name. The README's token table is this list. */
export const TOKENS = [
  "--vql-brand",
  "--vql-on-brand",
  "--vql-surface",
  "--vql-ink",
  "--vql-muted",
  "--vql-line",
  "--vql-live",
  "--vql-danger",
  "--vql-warn",
  "--vql-radius",
  "--vql-font",
  "--vql-shadow",
  "--vql-caption-size",
  "--vql-face-background",
  "--vql-z",
  "--vql-listening",
  "--vql-thinking",
  "--vql-speaking",
] as const;

export const themeStyles = css`
  :host {
    --_d-surface: #ffffff;
    --_d-ink: #1c1917;
    --_d-muted: #6b6560;
    --_d-line: rgba(28, 25, 23, 0.14);
    --_d-shadow: 0 10px 30px rgba(28, 25, 23, 0.18), 0 2px 6px rgba(28, 25, 23, 0.12);
    --_d-raised: rgba(28, 25, 23, 0.06);

    --_brand: var(--vql-brand, var(--_vql-cfg-brand, #c2410c));
    --_on-brand: var(--vql-on-brand, var(--_vql-cfg-on-brand, #ffffff));
    --_surface: var(--vql-surface, var(--_vql-cfg-surface, var(--_d-surface)));
    --_ink: var(--vql-ink, var(--_vql-cfg-ink, var(--_d-ink)));
    --_muted: var(--vql-muted, var(--_d-muted));
    --_line: var(--vql-line, var(--_d-line));
    --_raised: var(--_d-raised);
    --_live: var(--vql-live, #16a34a);
    --_danger: var(--vql-danger, #dc2626);
    --_radius: var(--vql-radius, var(--_vql-cfg-radius, 16px));
    --_font: var(--vql-font, var(--_vql-cfg-font, inherit));
    --_shadow: var(--vql-shadow, var(--_d-shadow));
    --_caption-size: var(--vql-caption-size, 15px);
    --_listening: var(--vql-listening, var(--_live));
    --_thinking: var(--vql-thinking, #d97706);
    --_speaking: var(--vql-speaking, var(--_brand));

    font-family: var(--_font);
    color: var(--_ink);
    box-sizing: border-box;
  }
  @media (prefers-color-scheme: dark) {
    :host(:not([scheme="light"]):not([data-scheme="light"])) {
      --_d-surface: #1c1b1a;
      --_d-ink: #f5f3f0;
      --_d-muted: #a8a29e;
      --_d-line: rgba(245, 243, 240, 0.16);
      --_d-shadow: 0 10px 30px rgba(0, 0, 0, 0.5), 0 2px 6px rgba(0, 0, 0, 0.4);
      --_d-raised: rgba(245, 243, 240, 0.08);
    }
  }
  :host([scheme="dark"]),
  :host([data-scheme="dark"]) {
    --_d-surface: #1c1b1a;
    --_d-ink: #f5f3f0;
    --_d-muted: #a8a29e;
    --_d-line: rgba(245, 243, 240, 0.16);
    --_d-shadow: 0 10px 30px rgba(0, 0, 0, 0.5), 0 2px 6px rgba(0, 0, 0, 0.4);
    --_d-raised: rgba(245, 243, 240, 0.08);
  }
  :host([hidden]) {
    display: none;
  }
  *,
  *::before,
  *::after {
    box-sizing: border-box;
  }
  button {
    font: inherit;
    color: inherit;
    margin: 0;
  }
  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
    border: 0;
  }
  .round {
    display: inline-grid;
    place-items: center;
    width: 40px;
    height: 40px;
    padding: 0;
    border-radius: 999px;
    border: 1px solid var(--_line);
    background: var(--_surface);
    cursor: pointer;
    transition: background-color 120ms ease, transform 120ms ease;
  }
  .round:hover {
    background: var(--_raised);
  }
  .round:focus-visible,
  button:focus-visible,
  select:focus-visible {
    outline: 2px solid var(--_brand);
    outline-offset: 2px;
  }
  svg {
    width: 20px;
    height: 20px;
    fill: none;
    stroke: currentColor;
    stroke-width: 2;
    stroke-linecap: round;
    stroke-linejoin: round;
  }
  @media (prefers-reduced-motion: reduce) {
    *,
    *::before,
    *::after {
      transition-duration: 0ms;
      animation-duration: 0ms;
      animation-iteration-count: 1;
    }
  }
`;
