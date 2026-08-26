import type { APIRoute } from "astro";
import { sidebar } from "../sidebar.mjs";
import { APEX, markdownPages, markdownUrl } from "../markdown-pages";

/**
 * The index an agent enters the docs through — https://docs.voqalize.com/llms.txt.
 * Since the site moved to its own origin on 2026-08-25 that is the conventional
 * host-root location, so nothing at the edge has to point at it any more.
 *
 * The apex of the pyramid is the MCP server's `instructions`: a few paragraphs
 * and a link to this file. This is the table of contents under it — every page,
 * in the site's own reading order, with the one-line description the page
 * already carries in its frontmatter, pointing at the `.md` twin rather than
 * the HTML. An agent reads one small file and then fetches only what the task
 * actually needs, which is the whole reason the docs no longer ship a second,
 * abridged copy of themselves as a skill.
 *
 * Ordering comes from `src/sidebar.mjs`, the same array Starlight renders, so
 * the two cannot disagree about what the docs contain. A page missing from the
 * sidebar still appears, under "Other" — a page an agent cannot find is worse
 * than a page in the wrong group, and the odd heading is a visible reminder to
 * put it where it belongs. Sub-groups are flattened into their section in
 * reading order: a nested item is a depth in the sidebar's tree, not a section
 * of its own, and before 2026-08-25 the six pages under Build's "Your first
 * brain" fell straight through to "Other".
 *
 * **The apex is named before the first section, not inside one.** It is L1 —
 * the whole model at low resolution — and an agent that reads a section hub
 * without it has the branch and not the tree. Starlight's sidebar has no entry
 * for a splash page, so nothing in the ordering can put it first; it is written
 * into the preamble here instead.
 */

// The same sentence the site's `description`, the apex's hero and the MCP
// server's `instructions` open with. Three surfaces, one claim.
const TAGLINE =
  "Voqalize adds voice to an existing web or mobile app. The user talks, the agent talks back and acts on the screen alongside them — and what they do in the app flows back as context.";

/** The sidebar is a tree; a section of `llms.txt` is a list. */
const slugs = (items: readonly any[]): string[] =>
  items.flatMap((item) => (item.slug ? [item.slug] : item.items ? slugs(item.items) : []));

export const GET: APIRoute = async () => {
  const pages = await markdownPages();
  const byId = new Map(pages.map((entry) => [entry.id, entry]));

  const listed = new Set<string>();
  const apex = byId.get(APEX);
  const lines: string[] = [
    "# Voqalize",
    "",
    `> ${TAGLINE}`,
    "",
    "Every page below is served as markdown. Drop the `.md` for the rendered page.",
    "",
    ...(apex
      ? [
          `Start at [${apex.data.title}](${markdownUrl(apex.id)}) — the whole model on one page, with a link out of every branch. The four sections below go one level deeper each.`,
          "",
        ]
      : []),
  ];
  if (apex) listed.add(apex.id);

  const section = (label: string, ids: string[]) => {
    const entries = ids.map((id) => byId.get(id)).filter((entry) => entry !== undefined);
    if (entries.length === 0) return;
    lines.push(`## ${label}`, "");
    for (const entry of entries) {
      listed.add(entry.id);
      const description = entry.data.description;
      lines.push(
        `- [${entry.data.title}](${markdownUrl(entry.id)})${description ? `: ${description}` : ""}`,
      );
    }
    lines.push("");
  };

  for (const group of sidebar) {
    section(group.label, slugs(group.items));
  }
  section(
    "Other",
    pages.map((entry) => entry.id).filter((id) => !listed.has(id)),
  );

  return new Response(lines.join("\n"), {
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
};
