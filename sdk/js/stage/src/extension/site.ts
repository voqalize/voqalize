/**
 * What every part of a site extension shares: who the site is. One object,
 * written once by the site (`defineSite`) and handed to each entry point: the
 * content script, the early shell, the holder and the service worker.
 */

import type { Language, WidgetConfig } from "./widget.js";

export interface SiteConfig {
  /** Short and stable: storage keys and window flags are named after it
   *  ("acme" → `voqalize.acme.call`). */
  id: string;
  /** The manifest's match patterns: every page the extension runs on. */
  matches: string[];
  /** Whether a URL is one of the site's pages. Derived from `matches` unless
   *  given. */
  isSite?: (url: string) => boolean;
  /** The page a new tab opens on when nothing better is known. */
  home: string;
  /** The language a call opens in when the visitor chose none. */
  opening: Language;
  widget: WidgetConfig;
}

export function defineSite(config: SiteConfig): SiteConfig {
  return config;
}

/** A match pattern (`https://*.example.com/*`) as a test. */
export function matchPattern(pattern: string): RegExp {
  const m = /^(\*|https?):\/\/(\*|(?:\*\.)?[^/*]+)(\/.*)$/.exec(pattern);
  if (!m) throw new Error(`not a match pattern: ${pattern}`);
  const [, scheme, host, path] = m as unknown as [string, string, string, string];
  const sch = scheme === "*" ? "https?" : scheme;
  const h = host === "*" ? "[^/]+" : host.startsWith("*.") ? `(?:[^/]+\\.)?${reEsc(host.slice(2))}` : reEsc(host);
  const p = path.split("*").map(reEsc).join(".*");
  return new RegExp(`^${sch}://${h}${p}$`, "i");
}

const reEsc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

export function isSitePage(site: SiteConfig, url: string): boolean {
  if (site.isSite) return site.isSite(url);
  return site.matches.some((p) => matchPattern(p).test(url));
}

/** The window flag the early shell leaves its widget under. */
export const shellFlag = (site: SiteConfig) => `__voqalize_${site.id}_shell`;
/** The window flag that keeps a second content script from mounting. */
export const mountedFlag = (site: SiteConfig) => `__voqalize_${site.id}_mounted`;
