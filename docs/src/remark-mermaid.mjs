/**
 * ```mermaid fences become diagrams, and stay fences in the markdown twin.
 *
 * This runs at the *remark* stage, before Shiki ever sees the block, which is
 * the whole trick: Shiki has no `mermaid` grammar, so a highlighted mermaid
 * fence is either an error or a wall of unstyled text. Replacing the node with
 * raw HTML takes it out of the highlighting path entirely.
 *
 * Nothing is done to the source file, so `/docs/<page>.md` — the twin an agent
 * fetches, see `markdown-pages.ts` — still carries the fence verbatim. A
 * diagram is one of the few things that survives being read as text, and an
 * agent reading `A --> B` loses nothing a human with the SVG has.
 *
 * No `unist-util-visit`: it is a transitive dependency of astro rather than one
 * we declare, and a six-line walk is cheaper than a dependency that can move
 * out from under us.
 */

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;" };

function escapeHtml(text) {
  return text.replace(/[&<>]/g, (char) => ESCAPES[char]);
}

export function remarkMermaid() {
  return (tree) => {
    const walk = (node) => {
      if (!Array.isArray(node.children)) return;
      node.children = node.children.map((child) => {
        if (child.type === "code" && child.lang === "mermaid") {
          return {
            type: "html",
            // `pre` rather than `div`: if the script never runs — JS off, a
            // bundle that 404s — the reader sees the diagram source with its
            // line breaks intact instead of one long line of soup.
            value: `<pre class="mermaid">${escapeHtml(child.value)}</pre>`,
          };
        }
        walk(child);
        return child;
      });
    };
    walk(tree);
  };
}
