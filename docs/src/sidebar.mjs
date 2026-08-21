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
    label: "Getting started",
    items: [
      { label: "What is Voqalize?", slug: "start/overview" },
      { label: "Quickstart", slug: "start/quickstart" },
      { label: "Core concepts", slug: "start/concepts" },
    ],
  },
  {
    label: "Build a brain",
    items: [
      { label: "Python SDK", slug: "brain/python" },
      { label: "Handling a conversation", slug: "brain/conversation" },
      { label: "Testing a brain", slug: "brain/testing" },
      { label: "Instrumenting a brain", slug: "brain/instrumentation" },
    ],
  },
  {
    label: "Connect a client",
    items: [{ label: "React client SDK", slug: "client/react" }],
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
      { label: "Voice protocol (Vql frames)", slug: "reference/voice-protocol" },
      { label: "Voice & language catalog", slug: "reference/catalog" },
      { label: "MCP server", slug: "reference/mcp" },
    ],
  },
  {
    label: "Demos",
    items: [{ label: "Demo gallery", slug: "demos/gallery" }],
  },
];
