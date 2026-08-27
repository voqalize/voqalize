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

/**
 * The apex, whose id the content layer reports as `index`.
 *
 * It is the one page whose rendered URL is not its id: the site root serves it,
 * and `/index` is a 404. The markdown twin, on the other hand, *is* `/index.md`
 * — the root has no name to hang `.md` on. So the two halves disagree for
 * exactly this page, and every caller gets them from here rather than deciding.
 */
export const APEX = "index";

/** The rendered page a human reads. */
export function pageUrl(id: string): string {
  return id === APEX ? `${SITE}${BASE}/` : `${SITE}${BASE}/${id}`;
}

/** The same page as raw markdown — for every page but the apex, plus `.md`. */
export function markdownUrl(id: string): string {
  return `${SITE}${BASE}/${id}.md`;
}

/**
 * Markdown pages only, in a stable order.
 *
 * **The apex is one of them, and it was not until 2026-08-25.** It used to be
 * `index.mdx` — a Starlight splash page built out of JSX components, so its
 * source was not markdown anybody would want to read, and it was excluded here.
 * The cost of that only showed once the tree was built top-down from the MCP
 * handshake: the apex is L1, the whole model at low resolution, and it was the
 * single page an agent could not fetch. It had no twin and no `llms.txt` line,
 * so an agent's path skipped it entirely and landed straight in a section hub.
 *
 * The fix was to stop needing the JSX: the one component grid became a markdown
 * table and the page is a plain `.md` with splash frontmatter. One source, and
 * the apex now indexes itself like every other page.
 *
 * The filter stays `.mdx`-excluding rather than becoming a list, so the rule
 * holds for the next page somebody reaches for a component on: a page that
 * needs JSX to say what it means has no markdown twin, and should not be load-
 * bearing in the agent's path.
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
  // The apex first: every other page links it as a bare `/`, which the pattern
  // below cannot match because it needs at least one path character to name a
  // page. Left alone, the one link every hub carries back up to L1 is also the
  // one link that drops an agent out of markdown and into HTML.
  if (ids.has(APEX)) {
    body = body.replace(
      new RegExp(`\\]\\(${base}/(#[^)\\s]*)?\\)`, "g"),
      (_match, anchor: string | undefined) => `](${BASE}/${APEX}.md${anchor ?? ""})`,
    );
  }
  return body.replace(
    new RegExp(`\\]\\(${base}/([^)#\\s]+?)/?(#[^)\\s]*)?\\)`, "g"),
    (match, id: string, anchor: string | undefined) =>
      ids.has(id) ? `](${BASE}/${id}.md${anchor ?? ""})` : match,
  );
}
