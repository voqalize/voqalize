/**
 * The site follows the call's language.
 *
 * enveedo.com is HubSpot CMS: English at `/…`, Spanish at `/es/…`, under the
 * SAME slugs, with two exceptions: `/book-a-demo-grl` ↔ `/es/book-a-demo-rsa`,
 * and `/webinars-and-ebooks`, which has no Spanish page. The blog is
 * blog.enveedo.com and blog.enveedo.com/es. So a twin is worked out from a
 * static map, with no fetch; a page the map does not know (one added since)
 * falls back to its own `<link rel="alternate" hreflang>` when it is the page
 * in front, and else loads as named.
 *
 * The brain names English paths. While the call is in Spanish the extension
 * loads the Spanish twin. The site's own links get this wrong both ways (the
 * English header's "Platform" and "Security Performance OS" lead to /es/
 * pages, and the Spanish CTAs to English pages, `?hsLang=es` included), so
 * during a call the adapter rewrites the page's same-site links to the call
 * language's twin (`twinUrl`).
 *
 * Pure but for `hreflangHere`: the holder imports the map too.
 */

export type Lang = "en" | "es";

export const SITE = "https://enveedo.com";

/** enveedo.com, with or without `www.`. */
export const onSite = (host: string) => /^(www\.)?enveedo\.com$/i.test(host);
const onBlog = (host: string) => /^blog\.enveedo\.com$/i.test(host);

/** A site path, folded for comparing and looking up: lower case, no trailing
 *  slash (the root stays `/`). `/es/` is `/es`. */
export function foldPath(path: string): string {
  const p = (path || "/").toLowerCase().replace(/\/{2,}/g, "/").replace(/\/+$/, "");
  return p.startsWith("/") ? p || "/" : `/${p}`;
}

/** The language a site path is in, by its prefix. */
export function pathLang(path: string): Lang {
  return /^\/es(\/|$)/i.test(foldPath(path)) ? "es" : "en";
}

/** English paths with a Spanish twin under a different slug, and the ones
 *  with none. Every other English path's twin is `/es` + the same path. */
const ODD_TWINS: Record<string, string> = { "/book-a-demo-grl": "/es/book-a-demo-rsa" };
const NO_SPANISH = new Set(["/webinars-and-ebooks"]);
/** Paths that are not pages of the site (files, the HubSpot folders). */
const NOT_A_PAGE = /^\/(hubfs|_hcms|hs|hs-fs)(\/|$)|\.[a-z0-9]{2,5}$/i;

/** The English path of a site path (`/es/faq` → `/faq`, `/es` → `/`). */
export function englishPath(path: string): string {
  const p = foldPath(path);
  if (pathLang(p) === "en") return p;
  for (const [en, es] of Object.entries(ODD_TWINS)) if (es === p) return en;
  return foldPath(p.replace(/^\/es/, "")) || "/";
}

/** The path of the page at `path` in `lang`, by the static map; `null` when
 *  the page has no such twin (or is not a page). */
export function twinPath(path: string, lang: Lang): string | null {
  const p = foldPath(path);
  if (NOT_A_PAGE.test(p)) return null;
  if (pathLang(p) === lang) return p;
  const en = englishPath(p);
  if (lang === "en") return en;
  if (NO_SPANISH.has(en)) return null;
  if (ODD_TWINS[en]) return ODD_TWINS[en];
  return en === "/" ? "/es/" : `/es${en}`;
}

/** The query a twin keeps: HubSpot's `hsLang` names the old page's language,
 *  so it goes. */
function keptQuery(url: URL): string {
  const q = new URLSearchParams(url.search);
  q.delete("hsLang");
  const s = q.toString();
  return s ? `?${s}` : "";
}

/**
 * The URL of the page at `href` in `lang`: a page of enveedo.com or of the
 * blog. `null` when it is not one of those, or has no twin in `lang` (the
 * caller keeps the link as it is). The hash is kept.
 */
export function twinUrl(href: string | URL, lang: Lang, base = SITE): string | null {
  let url: URL;
  try {
    url = new URL(href, base);
  } catch {
    return null;
  }
  if (onBlog(url.host)) {
    const p = foldPath(url.pathname);
    const isEs = /^\/es(\/|$)/.test(p);
    if (isEs === (lang === "es")) return null;
    // Only the blog's home has a known twin; a post is left as it is.
    if (p === "/" && lang === "es") return `https://${url.host}/es${url.hash}`;
    if (p === "/es" && lang === "en") return `https://${url.host}/${url.hash}`;
    return null;
  }
  if (!onSite(url.host)) return null;
  const twin = twinPath(url.pathname, lang);
  if (!twin) return null;
  const out = `${url.origin}${twin}${keptQuery(url)}${url.hash}`;
  return out === url.href ? null : out;
}

/** The page in front's own translation in `lang`, as its `<head>` names it. */
export function hreflangHere(lang: Lang): string | null {
  for (const l of document.querySelectorAll<HTMLLinkElement>("link[rel~=alternate][hreflang][href]")) {
    if (l.hreflang.toLowerCase().startsWith(lang)) return l.href;
  }
  return null;
}

/** The language the page in front is in: its `<html lang>`, else its path. */
export function pageLanguage(): Lang {
  const l = (document.documentElement.lang || "").toLowerCase();
  if (l.startsWith("es")) return "es";
  if (l.startsWith("en")) return "en";
  return pathLang(location.pathname);
}
