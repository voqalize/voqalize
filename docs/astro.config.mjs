// @ts-check
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";

// Shared with `src/pages/llms.txt.ts`, which builds the agent-facing index from
// the same ordering. See src/sidebar.mjs.
import { sidebar } from "./src/sidebar.mjs";

// The docs site is served under voqalize.com/docs (see docs/README.md), so it is
// built with `base: "/docs"`. Output is pure static — no runtime dependency.
export default defineConfig({
  site: "https://voqalize.com",
  base: "/docs",
  trailingSlash: "ignore",
  // `client/react` documented `@voqalize/client-react`, deprecated 2026-08-24.
  // The page is gone rather than rewritten — a page recommending a deprecated
  // package is worse than a 404 — but the URL is linked from the MCP server's
  // instructions, from llms.txt copies already fetched, and from anywhere a
  // reader bookmarked it, so it lands on the page that replaced it.
  // The key is base-relative; the value is emitted verbatim, so it carries the
  // `/docs` base itself. Without it the meta-refresh points at voqalize.com/client/…,
  // which is the marketing site and a 404.
  redirects: { "/client/react": "/docs/client/handshake" },
  vite: { server: { allowedHosts: [".local.voqalize.com"] } },
  integrations: [
    starlight({
      title: "Voqalize",
      description:
        "A voice operator that lives inside your app. You write the brain — what to say and what to show; Voqalize runs the voice: WebRTC, STT, TTS, turn-taking, interruptions, and recording.",
      tagline: "A voice operator that lives inside your app. You write the brain — what to say and what to show; Voqalize runs the voice.",
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
