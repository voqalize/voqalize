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
language catalog** exposed by the speech tier.

## Every page is also markdown

`/build/pipecat` is for a person; `/build/pipecat.md` is the same page as raw
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

Five files, and what each is for:

| File | What it owns |
|---|---|
| [`src/sidebar.mjs`](src/sidebar.mjs) | The reading order, once. Starlight's sidebar and `llms.txt` both import it, so they cannot disagree about what the docs contain. **Adding a page means adding it here.** |
| [`src/redirects.mjs`](src/redirects.mjs) | Every URL this site has retired, and where it went. **Moving a page means adding it here.** |
| [`src/markdown-pages.ts`](src/markdown-pages.ts) | Which entries are markdown, the URL shapes, and the link rewriting |
| [`src/pages/`](src/pages) | The two routes: `[...slug].md.ts` and `llms.txt.ts` |
| [`check_navigation.py`](check_navigation.py) | The gate: walks the built graph the way an agent does and fails if it gets stuck |

**The apex is a `.md`, and that is load-bearing.** It was `index.mdx` until
2026-08-25 — a splash page built out of JSX components, excluded from both
routes on the grounds that its source was not markdown anyone would want to
read. That reasoning held right up until the tree was rebuilt top-down from the
MCP handshake, at which point the apex became L1, the whole model at low
resolution, and it was the single page an agent could not fetch: no twin, no
`llms.txt` line, so the path ran from the handshake straight into a section hub.
The fix was to stop needing the JSX — one component grid became a markdown
table. The `.mdx` exclusion stays as a rule for the next page somebody reaches
for a component on: a page that needs JSX to say what it means should not be
load-bearing in the agent's path.

**A moved page needs an entry in `src/redirects.mjs`, and that is not just for
the browser.** Astro implements a static redirect as meta-refresh HTML, so the
config's map alone gives a human a working link and an agent a 404 —
`[...slug].md.ts` reads the same map and emits a markdown stub at each retired
path saying where the page went. `check_navigation.py` fails the build if either
half is missing.

Run the gate against a built tree:

```sh
pnpm build && python3 check_navigation.py
```

It asserts what an agent's path depends on and the HTML link checker cannot see:
`llms.txt` names every page exactly once and the apex first, no page is in the
build that nothing links to, no markdown link drops out of markdown, and every
retired URL answers in both formats. `check_links.py` in the private product repo is
the other half — it reads rendered HTML across the marketing/docs seam. Neither
is a superset of the other, and every defect the gate exists for was invisible
to a check that read one format and not the other.

The `Content-Type` the routes set is what `astro dev` answers with; the deployed
site's comes from the static host's own MIME table, so local and prod agree on
`text/markdown` by two separate mechanisms rather than one.
