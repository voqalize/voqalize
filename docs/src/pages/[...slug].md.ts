import type { APIRoute, GetStaticPaths } from "astro";
import type { CollectionEntry } from "astro:content";
import { markdownLinks, markdownPages, pageUrl } from "../markdown-pages";

/**
 * Every docs page, again, as raw markdown at the same URL plus `.md`.
 *
 * `/docs/start/quickstart` is for a person; `/docs/start/quickstart.md` is for an
 * agent. The MCP server's instructions link here, and an agent that follows a
 * link into rendered HTML has to strip a navigation tree, a search widget and a
 * theme toggle back off before it reaches a sentence. Same words, one source —
 * the page *is* the markdown file, so this cannot drift from what the site
 * shows the way a hand-maintained agent-facing condensation of the docs did.
 */

export const getStaticPaths: GetStaticPaths = async () => {
  const pages = await markdownPages();
  // Every page needs to know the whole set to rewrite links into it, and
  // `getStaticPaths` is the one place the collection is read.
  const ids = pages.map((entry) => entry.id);
  return pages.map((entry) => ({ params: { slug: entry.id }, props: { entry, ids } }));
};

/** YAML with the characters that would break it escaped, and nothing else. */
function yamlString(value: string): string {
  return `"${value.replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\n/g, " ")}"`;
}

export const GET: APIRoute = ({ props }) => {
  const entry = props.entry as CollectionEntry<"docs">;
  const { title, description } = entry.data;
  const header = [
    "---",
    `title: ${yamlString(title)}`,
    ...(description ? [`description: ${yamlString(description)}`] : []),
    `source: ${pageUrl(entry.id)}`,
    "---",
    "",
    "",
  ].join("\n");

  const body = markdownLinks(entry.body ?? "", new Set(props.ids as string[]));

  return new Response(`${header}${body}`, {
    headers: {
      // Set here as well as in any hosting config so `astro dev` and the
      // deployed site answer identically — an agent testing against local
      // should not meet a different content type than it will in production.
      "Content-Type": "text/markdown; charset=utf-8",
    },
  });
};
