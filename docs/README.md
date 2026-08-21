# docs — the Voqalize developer documentation site

The source for `voqalize.com/docs`. Built with **Astro Starlight** (same
framework as the marketing site), so it shares branding and outputs **pure
static** files — no runtime dependency. The built `dist/` is assembled into the
single Firebase Hosting site at the env apex and served under `/docs`
(alongside the marketing site at `/` and the demos at `/demos/<name>`), or by
any static host.

Covers the developer guides, the SDK references, and the **voice / model /
language catalog** (the vql-speech capability surface — a first-party Voqalize
microservice).

## Every page is also markdown

`/docs/start/quickstart` is for a person; `/docs/start/quickstart.md` is the same
page as raw markdown, for an agent. `/docs/llms.txt` is the index it enters
through: every page in the site's own reading order, with the one-line
`description` each page already carries, linking to the `.md` twin.

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
