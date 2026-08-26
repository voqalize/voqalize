import type { APIRoute, GetStaticPaths } from "astro";
import type { CollectionEntry } from "astro:content";
import { markdownLinks, markdownPages, markdownUrl, pageUrl } from "../markdown-pages";
import { redirects } from "../redirects.mjs";

/**
 * Every docs page, again, as raw markdown at the same URL plus `.md`.
 *
 * `/start/pipecat` is for a person; `/start/pipecat.md` is for an
 * agent. The MCP server's instructions link here, and an agent that follows a
 * link into rendered HTML has to strip a navigation tree, a search widget and a
 * theme toggle back off before it reaches a sentence. Same words, one source —
 * the page *is* the markdown file, so this cannot drift from what the site
 * shows the way a hand-maintained agent-facing condensation of the docs did.
 *
 * This route also answers for **retired URLs**, which is not obvious and is the
 * reason `src/redirects.mjs` exists as its own module. Astro implements a static
 * redirect as a meta-refresh HTML page, so the config's `redirects` map produces
 * `/deploy/inbound/index.html` and nothing at `/deploy/inbound.md` — the twin
 * route never runs for a path that has no collection entry. A human following a
 * stale link therefore lands correctly and an agent following the same link out
 * of an `llms.txt` it fetched last week gets a 404. So each retired path gets a
 * stub here saying where the page went, in the markdown an agent already knows
 * how to read.
 */

export const getStaticPaths: GetStaticPaths = async () => {
  const pages = await markdownPages();
  // Every page needs to know the whole set to rewrite links into it, and
  // `getStaticPaths` is the one place the collection is read.
  const ids = pages.map((entry) => entry.id);
  return [
    ...pages.map((entry) => ({
      params: { slug: entry.id },
      props: { entry, ids },
    })),
    ...Object.entries(redirects).map(([from, to]) => ({
      params: { slug: from.replace(/^\//, "") },
      props: { moved: to },
    })),
  ];
};

/** YAML with the characters that would break it escaped, and nothing else. */
function yamlString(value: string): string {
  return `"${value.replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\n/g, " ")}"`;
}

export const GET: APIRoute = ({ props }) => {
  const moved = props.moved as string | undefined;
  if (moved) {
    // Both URLs, because the agent that asked for markdown wants markdown and
    // whoever it is working for may want the page. `markdownUrl` takes an id,
    // not a path, so the leading slash comes off first.
    const id = moved.replace(/^\//, "");
    return markdown(
      [
        "---",
        `title: ${yamlString("Moved")}`,
        `source: ${pageUrl(id)}`,
        "---",
        "",
        `This page moved to [${moved}](${markdownUrl(id)}).`,
        "",
      ].join("\n"),
    );
  }

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

  return markdown(`${header}${body}`);
};

function markdown(text: string): Response {
  return new Response(text, {
    headers: {
      // Set here as well as in any hosting config so `astro dev` and the
      // deployed site answer identically — an agent testing against local
      // should not meet a different content type than it will in production.
      "Content-Type": "text/markdown; charset=utf-8",
    },
  });
}
