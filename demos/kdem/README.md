# KDEM: Aria on karnatakadigital.in

Aria is a voice assistant for the Karnataka Digital Economy Mission's website.
A visitor clicks "Talk to Aria" and asks about KDEM's programmes, policies,
events, reports or news. She answers in a sentence or two from KDEM's approved
pages and the PDFs they link to, then shows a link card to the page or PDF that
has the full answer. When the answer is in a PDF she says where, for example
"the Startup Policy, page 12". She speaks
English by default and switches to Kannada when the visitor asks for it or
speaks it.

Like `marketing` and `qween`, this demo has a `backend/` and no `frontend/`. The
page is karnatakadigital.in itself. It is not in `manifest.json`, so `build.mjs`
never looks for a frontend here and it is not a card on `/demos`.

| Path | What it is |
|---|---|
| `backend/brain.py` | Aria: the prompt, the greeting and three tools (`search_kdem`, `show_link`, `set_language`) |
| `backend/content.py` | The languages table and the page list in the prompt |
| `backend/knowledge.py` | The approved-page list, visible-text extraction, PDF text extraction, sitemap and PDF refresh, and in-memory search |
| `backend/knowledge/` | `approved_pages.json`, which KDEM reviews, and its README |
| `embed/voqalize-aria-kdem.html` | The snippet that is pasted into the site |

## The brain

The agent's `brain_url` is `wss://brain.voqalize.com/kdem`. Aria's voice is
`omnivoice/gauri` in both languages. The brain sets it on both legs in
`on_session_start`, before the greeting. The opening line is written in the
brain, not generated: "Hello, I'm Aria from KDEM. You can talk to me in English
or Kannada. How can we help you grow your business in Karnataka?"

English is the main language. When the visitor asks for Kannada, or a whole
sentence is plainly Kannada, Aria switches at once. When she is not sure (a few
words that may be Kannada, or a turn too short to tell), she answers in English
and asks once, in both languages, "ಕನ್ನಡದಲ್ಲಿ ಮಾತಾಡೋಣವೇ? Shall we continue in
Kannada?", and switches on a yes. One borrowed English word inside a Kannada
sentence does not count as switching.

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
  it out too. A PDF is sent only if the index holds it: an approved page links
  to it and the refresh read it. Before the first index exists, Contact Us is
  the only page sent. The snippet checks again that the host is
  karnatakadigital.in, then shows the link as a card that opens in a new tab.
  A PDF URL (`/wp-content/uploads/...pdf`) passes the same check and opens in
  the browser's PDF viewer; the snippet needs no change for it. A PDF on
  another site (a government portal an approved page links to) is cited by
  name and page, but its card is the approved KDEM page that links it, since
  the snippet shows only karnatakadigital.in.

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
first session starts. Until then she says she does not have the answer and
offers Contact Us. New news and event pages follow, then the PDFs those approved
pages link to: the news and events are answered from before the PDFs are
downloaded, and the PDFs once the refresh finishes. After that, a PDF is
downloaded again only when it changed, or while a long one is still being read.

PDFs are read with `pypdf`, page by page. The limits are on the work, not the
size of the file, so every PDF KDEM posts is read in the end and the brain stays
bounded:

- a PDF is streamed to a scratch file on disk, never held in memory. 150 MB is
  a safety ceiling, checked against Content-Length and again while downloading;
- it is read in a child process of its own: 768 MB of memory beyond the
  interpreter's own (an address-space limit; Linux only), 120 seconds of
  reading per PDF per run, and the brain kills the process a few seconds past
  that whatever it is doing;
- one bad page never costs the document. A page whose content decompresses past
  4 MB, or that takes more than 10 seconds, is skipped and the next one read;
  the site's heaviest real pages (text drawn as vector shapes, about 1.5 MB)
  read in under a second. A process killed on a page keeps every page before
  it, and the next run starts after it;
- a long document is read 150 pages a night from its first page, so its summary
  and contents are answerable after the first night. The refresh reports it as
  in progress until it is read through; if the file changes meanwhile, it is
  read again from the first page;
- one PDF holds at most 1,000,000 characters, and all PDF text together at most
  5,000,000, which keeps a search to a few milliseconds. What the total leaves
  out is reported.

PDFs are read from the links in the visible text of approved pages: on
karnatakadigital.in, or over https on another site, such as a state government
portal. The host is recorded, and nothing past those links is followed. A PDF
that is encrypted, damaged or scanned (images with no text layer) is not
answered from; `pending` lists them with the reason. There is no OCR. A dead
link or a failed read is tried again after a backoff that starts at a day and
doubles to a month.

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
cd demos && uv run pytest tests/test_kdem_e2e.py tests/test_kdem_knowledge.py tests/test_kdem_pdfs.py
```

All three files run without network access. The PDFs in the tests are built in
the test from a few neutral sentences. The e2e tests load a small, made-up
snapshot into the knowledge base, and `tests/conftest.py` turns the background
refresh off for every test.
