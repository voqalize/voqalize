# docs — the Voqalize developer documentation site

The source for `docs.voqalize.com`. Built with **Astro Starlight** (same
framework as the marketing site), so it shares branding and outputs **pure
static** files — no runtime dependency. The built `dist/` is deployed to its own
Firebase Hosting site, one per environment — `docs.voqalize.com`,
`docs.dev.voqalize.com`, `docs.local.voqalize.com`, one DNS label in front of
each apex the way the console's `app.` is — or by any static host.

It moved off the apex on 2026-08-25. The site therefore carries **no `base`**:
it is served at the root, and the apex answers `/docs/**` with a permanent
redirect here. Keep it that way. A base path is not free in Astro — the dev
server strips it before vite sees the request, so vite mints its own dev URLs
root-relative regardless and the two halves of a page end up on different
prefixes.

Covers the developer guides, the SDK references, and the **voice / model /
language catalog** (the vql-speech capability surface — a first-party Voqalize
microservice).

## Every page is also markdown

`/start/pipecat` is for a person; `/start/pipecat.md` is the same page as raw
markdown, for an agent. `/llms.txt` is the index it enters through: every page in
the site's own reading order, with the one-line `description` each page already
carries, linking to the `.md` twin. On the site's own origin that index sits
where the convention puts it — at the host root — so nothing at the edge has to
point at it.

That is the body of the documentation pyramid whose apex is the MCP server's
`instructions` — a few paragraphs that orient an agent and then point here.
Nothing is written twice: the `.md` route serves the page's own source, so it
cannot drift from what the site renders the way a separately maintained,
abridged copy of the docs did. Links inside a `.md` page are rewritten to their
`.md` twins, so an agent that follows one stays in markdown.

Three files, and what each is for:

| File | What it owns |
|---|---|
| [`src/sidebar.mjs`](src/sidebar.mjs) | The reading order, once. Starlight's sidebar and `llms.txt` both import it, so they cannot disagree about what the docs contain. **Adding a page means adding it here.** |
| [`src/markdown-pages.ts`](src/markdown-pages.ts) | Which entries are markdown, the URL shapes, and the link rewriting |
| [`src/pages/`](src/pages) | The two routes: `[...slug].md.ts` and `llms.txt.ts` |

`index.mdx` is deliberately absent from both — it is a splash page built out of
JSX components, so its source is not markdown anyone would want to read.

The `Content-Type` the routes set is what `astro dev` answers with; the deployed
site's comes from the static host's own MIME table, so local and prod agree on
`text/markdown` by two separate mechanisms rather than one.
