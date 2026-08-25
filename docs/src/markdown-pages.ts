import { getCollection, type CollectionEntry } from "astro:content";

/**
 * What "the docs, as markdown" means — shared by the `.md` routes and `llms.txt`.
 *
 * The site URL and base path come from `astro.config.mjs` through `import.meta.env`
 * rather than being written down again here: an absolute URL that disagrees with
 * where the site is actually served is a link that 404s in exactly one
 * environment, which is the kind of thing nobody notices until an agent follows it.
 *
 * `BASE` has been the empty string since the site moved to its own origin on
 * 2026-08-25, and the composition is kept anyway — it is what made that move a
 * config change rather than a rewrite of every URL in this file.
 */

const SITE = (import.meta.env.SITE ?? "https://docs.voqalize.com").replace(/\/$/, "");
const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

/** The rendered page a human reads. */
export function pageUrl(id: string): string {
  return `${SITE}${BASE}/${id}`;
}

/** The same page as raw markdown — the rendered URL plus `.md`. */
export function markdownUrl(id: string): string {
  return `${pageUrl(id)}.md`;
}

/**
 * Markdown pages only, in a stable order.
 *
 * `index.mdx` is deliberately excluded: it is a Starlight splash page built out
 * of JSX components, so its source is not markdown anybody would want to read.
 * `llms.txt` is the entry point for an agent instead.
 */
export async function markdownPages(): Promise<CollectionEntry<"docs">[]> {
  const entries = await getCollection("docs");
  return entries
    .filter((entry) => entry.filePath?.endsWith(".md"))
    .sort((a, b) => a.id.localeCompare(b.id));
}

/**
 * Rewrite in-page links to the markdown twin: `/deploy/inbound/#tls` →
 * `/deploy/inbound.md#tls`.
 *
 * Without this, an agent handed markdown follows the first link back into HTML
 * and has to know to bolt `.md` on itself. Only links whose target is a page we
 * actually publish as markdown are touched, so the site index, an anchor, an
 * asset or an external URL is left exactly as written — a rewrite that guesses
 * produces a 404 in the one place there was previously a working link.
 */
export function markdownLinks(body: string, ids: Set<string>): string {
  const base = BASE.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return body.replace(
    new RegExp(`\\]\\(${base}/([^)#\\s]+?)/?(#[^)\\s]*)?\\)`, "g"),
    (match, id: string, anchor: string | undefined) =>
      ids.has(id) ? `](${BASE}/${id}.md${anchor ?? ""})` : match,
  );
}
