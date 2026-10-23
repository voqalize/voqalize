/**
 * Reading a www.explora.com page's translations out of its HTML, for the page
 * (`site-language.ts`) and for the service worker (`background.ts`), which fetches for
 * the booking site: a page there cannot read www.explora.com across origins.
 *
 * WPML puts every translation of a page in its `<head>` as
 * `<link rel="alternate" hreflang="es" href="…">`, with translated slugs
 * (`/lodge/atacama-lodge/` ↔ `/es/lodge/hotel-en-san-pedro-de-atacama/`). The
 * links sit in the first ~13 KB of a 150–500 KB page, so a reader stops at
 * `</head>`. Pure: no DOM, no `window`.
 */

const ATTR = /([a-zA-Z][\w-]*)\s*=\s*(?:"([^"]*)"|'([^']*)')/g;

const unescape = (s: string) =>
  s.replace(/&amp;/g, "&").replace(/&#0?38;/g, "&").replace(/&quot;/g, '"').replace(/&#0?39;/g, "'");

/** Every `hreflang` alternate in `html`, by language (`en`, `es`, `pt-br`…). */
export function alternatesIn(html: string, base: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const tag of html.match(/<link\b[^>]*>/gi) ?? []) {
    const attrs: Record<string, string> = {};
    for (const m of tag.matchAll(ATTR)) attrs[m[1].toLowerCase()] = unescape(m[2] ?? m[3] ?? "");
    if (!/\balternate\b/i.test(attrs.rel ?? "") || !attrs.hreflang || !attrs.href) continue;
    try {
      out[attrs.hreflang.toLowerCase()] = new URL(attrs.href, base).href;
    } catch {
      /* Not a URL: skip it. */
    }
  }
  return out;
}

/** The start of a page, up to its `</head>`: the response body is read only
 *  that far and the rest is cancelled. `finalUrl` follows redirects. */
export async function fetchHead(url: string, ms = 5000): Promise<{ html: string; finalUrl: string }> {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), ms);
  try {
    const res = await fetch(url, { credentials: "include", signal: ctl.signal, headers: { Accept: "text/html" } });
    if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let html = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      html += dec.decode(value, { stream: true });
      if (/<\/head>/i.test(html) || html.length > 400_000) break;
    }
    void reader.cancel().catch(() => {});
    return { html, finalUrl: res.url || url };
  } finally {
    clearTimeout(timer);
  }
}

/** The `lang` translation of the www.explora.com page at `url`, or `null`
 *  when the page has none (or could not be read). */
export async function fetchAlternate(url: string, lang: string): Promise<string | null> {
  const { html, finalUrl } = await fetchHead(url);
  return alternatesIn(html, finalUrl)[lang] ?? null;
}
