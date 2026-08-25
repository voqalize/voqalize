import type { APIRoute } from "astro";
import { sidebar } from "../sidebar.mjs";
import { markdownPages, markdownUrl } from "../markdown-pages";

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
 * put it where it belongs.
 */

const TAGLINE =
  "A voice operator that lives inside your app. You write the brain — what to say and what to show; Voqalize runs the voice: WebRTC, STT, TTS, turn-taking, interruptions, and recording.";

export const GET: APIRoute = async () => {
  const pages = await markdownPages();
  const byId = new Map(pages.map((entry) => [entry.id, entry]));

  const lines: string[] = [
    "# Voqalize",
    "",
    `> ${TAGLINE}`,
    "",
    "Every page below is served as markdown. Drop the `.md` for the rendered page.",
    "",
  ];

  const listed = new Set<string>();
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
    section(
      group.label,
      group.items.map((item) => item.slug),
    );
  }
  section(
    "Other",
    pages.map((entry) => entry.id).filter((id) => !listed.has(id)),
  );

  return new Response(lines.join("\n"), {
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
};
