/**
 * The site's own ordering, in one place.
 *
 * Two things need it and they must not drift: Starlight's sidebar (the human
 * reading the site) and `llms.txt` (the agent reading the tree). It lives here
 * rather than inline in `astro.config.mjs` so that adding a page is one edit,
 * not two — a second copy of a table of contents is a second thing to forget.
 *
 * Plain `.mjs` on purpose: `astro.config.mjs` and a `src/pages/` endpoint both
 * import it, and neither has to think about how the other's toolchain handles
 * TypeScript.
 */
export const sidebar = [
  {
    label: "Build a brain",
    items: [{ label: "Testing a brain", slug: "brain/testing" }],
  },
  {
    label: "Connect a client",
    items: [{ label: "Connections and the handshake", slug: "client/handshake" }],
  },
  {
    label: "Deploy your brain",
    items: [
      { label: "Where the brain runs", slug: "deploy/brain-url" },
      { label: "Inbound server", slug: "deploy/inbound" },
      { label: "Cortex relay", slug: "deploy/cortex" },
    ],
  },
  {
    label: "Reference",
    items: [
      { label: "The wire", slug: "reference/wire" },
      { label: "Voice & language catalog", slug: "reference/catalog" },
      { label: "MCP server", slug: "reference/mcp" },
    ],
  },
];
