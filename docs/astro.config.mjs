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
