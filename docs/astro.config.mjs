// @ts-check
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";

// Shared with `src/pages/llms.txt.ts`, which builds the agent-facing index from
// the same ordering. See src/sidebar.mjs.
import { sidebar } from "./src/sidebar.mjs";
// ```mermaid fences, drawn. See src/remark-mermaid.mjs for why it is a
// remark plugin and not a rehype one.
import { remarkMermaid } from "./src/remark-mermaid.mjs";

// The docs site owns its origin — `docs.voqalize.com`, and `docs.dev.` /
// `docs.local.` one DNS label in front of each environment's apex, matching the
// console's `app.` (see docs/README.md). So it is served at the root and carries
// no `base`; the apex it used to sit under answers `/docs/**` with a permanent
// redirect here. Output is pure static — no runtime dependency.
export default defineConfig({
  site: "https://docs.voqalize.com",
  trailingSlash: "ignore",
  // `client/react` documented `@voqalize/client-react`, deprecated 2026-08-24.
  // The page is gone rather than rewritten — a page recommending a deprecated
  // package is worse than a 404 — but the URL is linked from the MCP server's
  // instructions, from llms.txt copies already fetched, and from anywhere a
  // reader bookmarked it, so it lands on the page that replaced it.
  redirects: { "/client/react": "/client/handshake" },
  markdown: { remarkPlugins: [remarkMermaid] },
  vite: { server: { allowedHosts: [".local.voqalize.com"] } },
  integrations: [
    starlight({
      title: "Voqalize",
      description:
        "A voice operator that lives inside your app. You write the brain — what to say and what to show; Voqalize runs the voice: WebRTC, STT, TTS, turn-taking, interruptions, and recording.",
      tagline: "A voice operator that lives inside your app. You write the brain — what to say and what to show; Voqalize runs the voice.",
      components: { Head: "./src/components/Head.astro" },
      customCss: ["./src/styles/theme.css"],
      social: [
        {
          icon: "github",
          label: "GitHub",
          href: "https://github.com/voqalize/voqalize",
        },
      ],
      editLink: {
        baseUrl: "https://github.com/voqalize/voqalize/edit/main/docs/",
      },
      sidebar,
    }),
  ],
});
