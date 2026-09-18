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
      // The mark beside the title, not instead of it: the approved logo is a
      // tile with no lettering in it, so `replacesTitle` would leave the site
      // unnamed. Starlight's `light`/`dark` name the theme the file is USED in,
      // which is how the two masters are named too — the navy tile reads on a
      // light header, the teal one on a dark header.
      logo: {
        light: "./src/assets/logo-light.png",
        dark: "./src/assets/logo-dark.png",
        // Empty on purpose. The title beside it already reads "Voqalize", and
        // both sit inside the one link — alt text here makes a screen reader
        // announce the name twice for a single target.
        alt: "",
      },
      // Starlight emits this as the only `rel="icon"`. The .ico carries 16/32/48
      // rendered one per size; `head` below adds the PNG twin and the iOS icon,
      // which this option has no room for.
      favicon: "/favicon.ico",
      head: [
        {
          tag: "link",
          attrs: { rel: "icon", type: "image/png", sizes: "32x32", href: "/favicon-32.png" },
        },
        {
          tag: "link",
          attrs: { rel: "icon", type: "image/png", sizes: "16x16", href: "/favicon-16.png" },
        },
        { tag: "link", attrs: { rel: "apple-touch-icon", href: "/apple-touch-icon.png" } },
        // Starlight writes og:title, og:description, og:url and
        // `twitter:card: summary_large_image` on every page, and no image — so a
        // link to any docs page unfurled as a large card with an empty picture
        // in it. These two fill it. Absolute, because a crawler has no page to
        // resolve a path against, and hardcoded against `site` above for the
        // same reason that is hardcoded: this site is served from one origin.
        {
          tag: "meta",
          attrs: { property: "og:image", content: "https://docs.voqalize.com/og.png" },
        },
        { tag: "meta", attrs: { property: "og:image:width", content: "1200" } },
        { tag: "meta", attrs: { property: "og:image:height", content: "630" } },
        { tag: "meta", attrs: { property: "og:image:alt", content: "Voqalize" } },
        {
          tag: "meta",
          attrs: { name: "twitter:image", content: "https://docs.voqalize.com/og.png" },
        },
      ],
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
