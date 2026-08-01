// @ts-check
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";

// The docs site is served under voqalize.com/docs (see docs/README.md), so it is
// built with `base: "/docs"`. Output is pure static — no runtime dependency.
export default defineConfig({
  site: "https://voqalize.com",
  base: "/docs",
  trailingSlash: "ignore",
  integrations: [
    starlight({
      title: "Voqalize",
      description:
        "A voice operator that lives inside your app. You write the brain; Voqalize runs the voice — WebRTC, STT, TTS, turn-taking, interruptions, and recording.",
      tagline: "A voice operator that lives inside your app. You write the brain; Voqalize runs the voice.",
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
      sidebar: [
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
            { label: "MCP server & Claude Code skill", slug: "reference/mcp" },
          ],
        },
        {
          label: "Demos",
          items: [{ label: "Demo gallery", slug: "demos/gallery" }],
        },
      ],
    }),
  ],
});
