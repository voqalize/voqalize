# KDEM: Aria on karnatakadigital.in

Aria is a voice assistant for the Karnataka Digital Economy Mission's website.
A visitor clicks "Talk to Aria" and asks about KDEM's programmes, policies,
events, reports or news. She answers in a sentence or two from KDEM's approved
pages, then shows a link card to the page that has the full answer. She speaks
English by default and switches to Kannada when the visitor asks for it or
speaks it.

Like `marketing` and `qween`, this demo has a `backend/` and no `frontend/`. The
page is karnatakadigital.in itself. It is not in `manifest.json`, so `build.mjs`
never looks for a frontend here and it is not a card on `/demos`.

| Path | What it is |
|---|---|
| `backend/brain.py` | Aria: the prompt, the greeting and three tools (`search_kdem`, `show_link`, `set_language`) |
| `backend/content.py` | The languages table and the page list in the prompt |
| `backend/knowledge.py` | The approved-page list, visible-text extraction, sitemap refresh and in-memory search |
| `backend/knowledge/` | `approved_pages.json`, which KDEM reviews, and its README |
| `embed/voqalize-aria-kdem.html` | The snippet that is pasted into the site |

## The brain

The agent's `brain_url` is `wss://brain.voqalize.com/kdem`. Aria's voice is
`omnivoice/gauri` in both languages. The brain sets it on both legs in
`on_session_start`, before the greeting. The opening line is written in the
brain, not generated: "Hello, I'm Aria from KDEM. How can we help you grow your
business in Karnataka?"

Recording audio is off, which is the agent default. The platform keeps the
transcripts.

## The snippet

`embed/voqalize-aria-kdem.html` goes into Elementor Pro → Custom Code, with the
location set to the end of `</body>`. Nothing loads until a visitor clicks. The
agent id and the publishable key are placeholders (`REPLACE_WITH_...`). They are
filled in when the snippet is handed over, and never committed.

The snippet and the brain share two things:

- **`init`**: the snippet sends `{surface: "kdem-web", page: location.pathname,
  lang: <html lang>}` with `sessions.connect`. The brain reads `page` so it knows
  which page the visitor started on. When `page` is a page Aria may link right
  now, the prompt names it by its own title and path. Anything else, including
  an excluded page or a path the index does not hold, is left out of the
  prompt: the brain never quotes what the browser sent. `surface` and `lang`
  are logged.
- **`show_link`**: the only command the snippet renders. Its payload is
  `{url, title}`. The brain fills it in itself: it canonicalises the page the
  model names and sends it only if the current index holds that page, using the
  page's own title. An approved page the refresh dropped (deleted, unpublished,
  or now redirecting elsewhere) is not sent, and the prompt's page list leaves
  it out too. Before the first index exists, Contact Us is the only page sent.
  The snippet checks again that the host is karnatakadigital.in, then shows the
  link as a card that opens in a new tab.

The site has to allow the microphone for its own pages. If it sends a
`Permissions-Policy` header, that header must include `microphone=(self)`.
Otherwise the browser blocks the microphone and Aria cannot hear the visitor.

## Keeping the pages fresh

Each brains host keeps its own snapshot of the approved pages, in
`KDEM_KNOWLEDGE_DIR`. The first session starts a background task that refreshes
the snapshot about once a day from `wp-sitemap.xml`. Sessions are never kept
waiting for it.

On a host with no snapshot, the first refresh reads the approved pages first
and Aria answers from them as soon as they are read, a minute or two after the
first session starts. New news and event pages follow when the refresh
finishes. Until the approved pages are in, Aria says she does not have the
answer and offers Contact Us.

The brains container is started with no volume today
(`demos/bin/brains-node-deploy.sh`), so every redeploy starts from no snapshot
and goes through those first minutes again. To keep the snapshot across
redeploys, mount a volume and point `KDEM_KNOWLEDGE_DIR` at it in the deploy
script. That is a deploy change and is not made here.

To refresh by hand after an urgent change on the site, run the command where
the brain runs, against the brain's own snapshot directory. In the brains
container that is a `docker exec`. Each brains host keeps its own snapshot, so
run it on every host:

```sh
KDEM_KNOWLEDGE_DIR=<the brain's snapshot dir> uv run python demos/kdem/backend/knowledge.py refresh --force https://karnatakadigital.in/policies/
KDEM_KNOWLEDGE_DIR=<the brain's snapshot dir> uv run python demos/kdem/backend/knowledge.py search "cluster seed fund"
KDEM_KNOWLEDGE_DIR=<the brain's snapshot dir> uv run python demos/kdem/backend/knowledge.py pending
```

`--cache-dir <dir>` does the same as the variable. Without either, the command
reads and writes `$XDG_CACHE_HOME/voqalize-kdem` (or the system temp
directory), which a brain with `KDEM_KNOWLEDGE_DIR` set never reads. A running
brain picks up a new snapshot in its own directory when the next session
starts.
`backend/knowledge/README.md` explains what is approved, what is held for
review and why.

## Tests

```sh
cd demos && uv run pytest tests/test_kdem_e2e.py tests/test_kdem_knowledge.py
```

Both files run without network access. The e2e tests load a small, made-up
snapshot into the knowledge base, and `tests/conftest.py` turns the background
refresh off for every test.
