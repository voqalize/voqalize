# Clini knowledge

What the Clini agent (Javier, in a Chrome extension on www.clini.cl and
agenda-web.clini.cl) knows, in three layers. Every fact is the site's own.
Nothing is filled in from general knowledge, and nothing medical beyond what the
site says.

- **`L1.md`**: always in the prompt, ~2.5k tokens, hand-written from the crawl:
  what CLINI is, services, price highlights ("desde"), Fonasa/Isapre/convenios,
  the sedes, the three booking paths, results, contact, the navigation and the
  L2 topic list. It is dated; where the site disagrees with itself (LASIK
  $381.250 vs $481.250 per eye) the disagreement is written down.
- **`L2/<topic>.md`**: a topic the agent reads on demand (`read_topic`). The file
  stem is the topic id. Each file opens with `# Title`, then a `Sources:` line.
  `site-map.md` and `blog-index.md` are generated from L3 (`build.py maps`);
  the others are hand-written from the crawl.
- **`L3/`**, built by `build.py` and committed:
  - `pages.json` — the 133 site pages (one object a line): sections with
    `heading` (as rendered), `level`, `selector`, `text` (visible + hidden tab
    and dropdown text, capped), `items` (sub-headings), `reveal`, `ctas`; `faqs`
    `{q, a, section}`; `tabs`; `sliders`; `forms`; booking `ctas`; `unlisted`.
  - `blog.json` — the 127 posts, light (title, description, date, headings, text).
  - `site.json` — crawl date, redirects, 404s, navigation, response headers and
    layout probes (fixed header 96 px desktop / 91 px mobile, overlays).
  - `branches.json` — the 20 sedes from /ubicaciones.
  - `prices.json` — the cotizador catalogue (~1,000 items, Fonasa and
    particular price, contraste, preparación): the offline fallback.
  - `agenda_services.json` — agenda-web `servicio` → name, prestaciones, regions,
    sectors and the site pages that link it.

Every one of these may be missing or empty: `knowledge.py` still imports, and
Javier runs on the fallback line.

## Rebuilding

Run from `voqalize/demos`. Playwright is not a demos dependency; install its
Chromium once with `uv run --with playwright playwright install chromium`.
Each page's extraction is cached in `~/.cache/voqalize-clini`.

```sh
uv run --with playwright python clini/backend/knowledge/build.py crawl            # sitemap + nav + links; cached pages reused
uv run --with playwright python clini/backend/knowledge/build.py crawl --refresh  # re-render every page (~10 min)
uv run --with playwright python clini/backend/knowledge/build.py crawl --only /laboratorio /cirugia-lasik
uv run python clini/backend/knowledge/build.py crawl --offline                    # rebuild L3 from the cache
uv run --with playwright python clini/backend/knowledge/build.py branches         # L3/branches.json
uv run --with playwright python clini/backend/knowledge/build.py agenda           # L3/agenda_services.json (after a crawl)
uv run python clini/backend/knowledge/build.py prices                             # full cotizador harvest, ~3k queries
uv run python clini/backend/knowledge/build.py prices --terms "resonancia rodilla,hemograma"
uv run python clini/backend/knowledge/build.py maps                               # L2/site-map.md, L2/blog-index.md
uv run python clini/backend/knowledge/build.py search "ayuno hemograma"
```

Nothing here submits a form, books a slot or looks up a patient: every browser
context route-blocks agenda-web's `AgendarCitaMedica` and `PacientePorDocumento`.
After a rebuild, re-read L1 and the L2 topics against the new crawl (prices and
sedes change).
