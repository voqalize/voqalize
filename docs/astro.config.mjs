// @ts-check
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";

// Shared with `src/pages/llms.txt.ts`, which builds the agent-facing index from
// the same ordering. See src/sidebar.mjs.
import { sidebar } from "./src/sidebar.mjs";
// ```mermaid fences, drawn. See src/remark-mermaid.mjs for why it is a
// remark plugin and not a rehype one.
import { remarkMermaid } from "./src/remark-mermaid.mjs";
// Every URL we have ever published and retired. Shared with the `.md` twin
// route, which has to emit a stub at each old path — see src/redirects.mjs.
import { redirects } from "./src/redirects.mjs";

// The docs site owns its origin — `docs.voqalize.com`, and `docs.dev.` /
// `docs.local.` one DNS label in front of each environment's apex, matching the
// console's `app.` (see docs/README.md). So it is served at the root and carries
// no `base`; the apex it used to sit under answers `/docs/**` with a permanent
// redirect here. Output is pure static — no runtime dependency.
export default defineConfig({
  site: "https://docs.voqalize.com",
  trailingSlash: "ignore",
  redirects,
  markdown: { remarkPlugins: [remarkMermaid] },
  vite: { server: { allowedHosts: [".local.voqalize.com"] } },
  integrations: [
    starlight({
      title: "Voqalize",
      // One sentence, and it is the same sentence the MCP server opens with and
      // the apex's hero carries. A reader who meets us three ways meets one
      // claim. Capability first, mechanism second — the mechanism is the half
      // they do not have to build.
      description: "Voqalize adds voice to an existing web or mobile app. The user talks, the agent talks back and acts on the screen alongside them — and what they do in the app flows back as context.",
      tagline: "Add voice to an existing web or mobile app. The user talks, the agent talks back and acts on the screen alongside them.",
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
