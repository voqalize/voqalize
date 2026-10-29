/**
 * The site follows the call's language.
 *
 * www.explora.com is WordPress with WPML: English at `/…`, Spanish at
 * `/es/…`, under translated slugs (`/atacama-desert/` ↔
 * `/es/desierto-de-atacama/`), so a Spanish URL cannot be built from an
 * English one. Every page names its translations in its `<head>`
 * (`<link rel="alternate" hreflang="es">`, read by `hreflang.ts`), and its
 * language selector (`.language-selector`, WPML's `.wpml-ls-item-es a`) links
 * them too. The booking site takes `?language=ES|EN` instead.
 *
 * The brain knows the English site, so a `navigate` names an English path;
 * while the call is in Spanish the extension loads its Spanish twin, read off
 * the English page's `<head>` (fetched up to `</head>` only, and remembered
 * for the tab in `sessionStorage`). A page that has no Spanish twin loads in
 * English.
 */

import { askWorker } from "@voqalize/stage/extension";

import { fetchAlternates } from "./hreflang";

export type Lang = "en" | "es";

export const SITE = "https://www.explora.com";
export const BOOKING = "https://reservations.explora.com";
const CACHE_KEY = "voqalize.explora.alternates";

export const onSite = (host = location.host) => /^(www\.)?explora\.com$/i.test(host);
export const onBookingSite = (host = location.host) => /^reservations\.explora\.com$/i.test(host);

/** A www.explora.com path, folded for comparing two URLs of one page: no
 *  host, query or hash, no trailing slash, lower case. */
export const pagePath = (url: string | URL): string => {
  try {
    return new URL(url, SITE).pathname.replace(/\/+$/, "").toLowerCase() || "/";
  } catch {
    return String(url);
  }
};

/** The language a www.explora.com URL is in, by WPML's path prefix. */
export function pathLang(url: string | URL): string {
  const m = pagePath(url).match(/^\/(es|pt-br|fr|de)(\/|$)/);
  return m ? m[1] : "en";
}

/** The language the page in front is in, when it is English or Spanish:
 *  `<html lang>` on www.explora.com, `?language=` on the booking site. */
export function pageLanguage(): Lang | null {
  if (onSite()) {
    const l = (document.documentElement.lang || pathLang(location.href)).toLowerCase();
    return l.startsWith("es") ? "es" : l.startsWith("en") ? "en" : null;
  }
  if (onBookingSite()) {
    const l = new URLSearchParams(location.search).get("language")?.toUpperCase();
    return l === "ES" ? "es" : l === "EN" ? "en" : null;
  }
  return null;
}

/** This page's translations, as its `<head>` names them. */
function alternatesHere(): Record<string, string> {
  const out: Record<string, string> = {};
  for (const l of document.querySelectorAll<HTMLLinkElement>("link[rel~=alternate][hreflang][href]")) {
    out[l.hreflang.toLowerCase()] = l.href;
  }
  return out;
}

/** This page's own twin in `lang`: its `hreflang` link, else the language
 *  selector's link; `null` when it names none. */
export function twinHere(lang: Lang): string | null {
  const link = alternatesHere()[lang];
  if (link) return link;
  const wpml = document.querySelector<HTMLAnchorElement>(`.language-selector .wpml-ls-item-${lang} a[href], .wpml-ls-item-${lang} a[href]`);
  return wpml?.href || null;
}

/** This page in `lang`: its own twin, else that language's home page. */
export function alternateHere(lang: Lang): string {
  return twinHere(lang) ?? (lang === "es" ? `${SITE}/es/` : `${SITE}/`);
}

// ─── The cache: page → its twin, for this tab ───────────────────────────────

type Cache = Record<string, string>;

function readCache(): Cache {
  try {
    return JSON.parse(sessionStorage.getItem(CACHE_KEY) ?? "{}") as Cache;
  } catch {
    return {};
  }
}

function remember(lang: Lang, from: string, to: string): void {
  try {
    const c = readCache();
    c[`${lang} ${pagePath(from)}`] = to;
    sessionStorage.setItem(CACHE_KEY, JSON.stringify(c));
  } catch {
    /* Storage blocked: fetch again next time. */
  }
}

/** Remember this page's own translations both ways, for free: the English
 *  page's Spanish twin, and the Spanish page's English one. */
export function rememberHere(): void {
  if (!onSite()) return;
  const alts = alternatesHere();
  if (alts.en && alts.es) {
    remember("es", alts.en, alts.es);
    remember("en", alts.es, alts.en);
  }
}

const inFlight = new Map<string, Promise<Mapped>>();

export interface Mapped {
  /** The URL to load. */
  url: string;
  /** Where it came from: already in that language, this page, the cache, a
   *  fetch from the page, a fetch from the service worker (`hub`), or the English page because
   *  none was found. */
  source: "as-is" | "here" | "cache" | "fetch" | "hub" | "fallback";
  ms: number;
  /** Why the page's head could not be read, when it could not. */
  error?: string;
}

const why = (error: unknown) => (error instanceof Error ? `${error.name}: ${error.message}` : String(error));

/** The page's translations as the extension's service worker reads them
 *  (still `source: "hub"` for the brain), which no script of the page can
 *  wrap or block. */
async function alternatesFromHub(url: string, lang: Lang): Promise<{ url: string | null; read: boolean; error?: string }> {
  const got = await askWorker<{ url: string | null; read?: boolean; error?: string }>({ op: "alternate", url, lang }, 6000);
  if (!got) return { url: null, read: false, error: "the service worker did not answer" };
  return { url: got.url, read: got.read ?? Boolean(got.url), error: got.error };
}

/**
 * The URL of the www.explora.com page at `path` (an English path, as the
 * brain names them) in `lang`. Never throws: a page with no translation, or
 * one that could not be read in time, is the page as named.
 */
export function siteUrlIn(lang: Lang, path: string): Promise<Mapped> {
  const t0 = performance.now();
  let target: URL;
  try {
    target = new URL(path, SITE);
  } catch {
    return Promise.resolve({ url: path, source: "as-is", ms: 0 });
  }
  if (!onSite(target.host)) return Promise.resolve({ url: target.href, source: "as-is", ms: 0 });
  if (pathLang(target) === lang) return Promise.resolve({ url: target.href, source: "as-is", ms: 0 });
  const done = (url: string, source: Mapped["source"]): Mapped => {
    // Keep what the brain asked for beyond the page itself (a hash, a query).
    const out = new URL(url);
    if (target.hash && !out.hash) out.hash = target.hash;
    return { url: out.href, source, ms: Math.round(performance.now() - t0) };
  };

  // The page in front is one of the target's translations: its own links.
  if (onSite()) {
    const alts = alternatesHere();
    if (Object.values(alts).some((u) => pagePath(u) === pagePath(target))) {
      return Promise.resolve(done(alts[lang] ?? target.href, alts[lang] ? "here" : "fallback"));
    }
  }
  const key = `${lang} ${pagePath(target)}`;
  const cached = readCache()[key];
  if (cached) return Promise.resolve(done(cached, "cache"));
  const running = inFlight.get(key);
  if (running) return running;

  const job = (async (): Promise<Mapped> => {
    let found: string | null = null;
    let source: Mapped["source"] = "fallback";
    /** Whether the page was read: a page that lists its translations but not
     *  this one is remembered as having none; one that could not be read, or
     *  answered with a page that names no translations at all (a consent or
     *  bot-check page, a script's stand-in), is tried again next time. Before,
     *  any answer was remembered, so one bad answer sent every later lookup of
     *  that page to English for the rest of the tab's visit. */
    let read = false;
    const errors: string[] = [];
    if (onSite()) {
      // Same origin: the page's own fetch, with the visitor's cookies.
      try {
        const alts = await fetchAlternates(target.href);
        read = Object.keys(alts).length > 0;
        found = alts[lang] ?? null;
        if (found) source = "fetch";
        else if (!read) errors.push("the page named no translations");
      } catch (error) {
        errors.push(why(error));
      }
    }
    // The booking site may not read www.explora.com, and a script of the page
    // may wrap its fetch: the service worker reads it from the extension instead.
    if (!found && !read) {
      const got = await alternatesFromHub(target.href, lang);
      found = got.url;
      read = got.read;
      if (found) source = "hub";
      else if (got.error) errors.push(`hub: ${got.error}`);
    }
    inFlight.delete(key);
    if (read) remember(lang, target.href, found ?? target.href);
    const m: Mapped = { ...done(found ?? target.href, source), ...(errors.length ? { error: errors.join("; ") } : {}) };
    console.info(`voqalize: ${pagePath(target)} in ${lang} → ${m.url} (${m.source}, ${m.ms} ms${m.error ? `, ${m.error}` : ""})`);
    return m;
  })();
  inFlight.set(key, job);
  return job;
}
