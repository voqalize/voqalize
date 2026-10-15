# KDEM: Aria on karnatakadigital.in

Aria is a voice assistant for the Karnataka Digital Economy Mission's website.
A visitor clicks "Talk to Aria" and asks about KDEM's programmes, policies,
events, reports or news. She answers in a sentence or two from KDEM's approved
pages and the PDFs they link to. When a page has the full answer she offers to
take the visitor there ("Shall I take you to the Seed Fund page?"), or points at
it if they are already on it. When the answer is in a PDF she says where, for
example "the Startup Policy, page 12", and shows the PDF as a link card. She speaks
English by default and switches to Kannada when the visitor asks for it or
speaks it.

Like `marketing` and `qween`, this demo has a `backend/` and no `frontend/`. The
page is karnatakadigital.in itself. It is not in `manifest.json`, so `build.mjs`
never looks for a frontend here and it is not a card on `/demos`.

| Path | What it is |
|---|---|
| `backend/brain.py` | Aria: the prompt, the greeting and the tools (`search_kdem`, `offer_page`, `go_to_page`, `point_at`, `show_document`, `set_language`) |
| `backend/app_events.py` | The events the snippet sends the brain: `page_viewed`, `language_requested`, `point_missed` |
| `backend/content.py` | The languages table and the page list in the prompt |
| `backend/knowledge.py` | The approved-page list, visible-text extraction, PDF text extraction, sitemap and PDF refresh, and in-memory search |
| `backend/knowledge/` | `approved_pages.json`, which KDEM reviews, and its README |
| `embed/voqalize-aria-kdem.js` | The snippet that is pasted into the site |

## The brain

For the pilot the brain is hosted on dev: the agent's `brain_url` is
`wss://brain.dev.voqalize.com/kdem`, and the script calls
`app.dev.voqalize.com`. Moving to production means `wss://brain.voqalize.com/kdem`
and changing `api` in the script to `app.voqalize.com`. Aria's voice is
`omnivoice/gauri` in both languages. The brain sets it on both legs in
`on_session_start`, before the greeting. The opening line is written in the
brain, not generated: "Hello, I'm Aria from KDEM. How can we help you grow your
business in Karnataka?" A call the visitor started with ಕನ್ನಡ picked on the
toggle opens with a written Kannada greeting instead.

English is the main language, and **Aria never says the name of the Kannada
language in English**: the English voice cannot say it. Asked which languages
she speaks, she says "I speak English, and Karnataka's own language too. Just
speak to me in it, or tap ಕನ್ನಡ at the top of my panel."

When the visitor asks for Kannada, or a turn looks like Kannada, she switches at
once, without asking. The model calls `set_language` and says nothing itself.
When its response has streamed, the brain moves both legs to Kannada in one
awaited request and only then says a written Kannada line, in the Kannada
voice, at the end of the same turn: "ಸರಿ, ಈಗ ಕನ್ನಡದಲ್ಲಿ ಮಾತಾಡೋಣ. ದಯವಿಟ್ಟು ನಿಮ್ಮ
ಪ್ರಶ್ನೆಯನ್ನು ಮತ್ತೊಮ್ಮೆ ಹೇಳಿ." (asking them to say it again, since the English
recognizer lost it). If she was wrong, the visitor speaks English, or taps
English, and she switches back the same way, saying "Sure, let's continue in
English." in the English voice. One borrowed English word inside a Kannada
sentence does not count as switching.

Recording audio is off, which is the agent default. The platform keeps the
transcripts.

## The snippet

`embed/voqalize-aria-kdem.js` is plain JavaScript, loaded by one tag that
names the agent and its publishable key:

```html
<script src="https://cdn.jsdelivr.net/gh/voqalize/voqalize@<commit>/demos/kdem/embed/voqalize-aria-kdem.js"
        data-agent="<agent id>" data-key="<publishable key>" defer></script>
```

The file itself names no agent and carries no key; both live in the site's own
tag, so nothing account-specific is committed here. Without them the script
starts nothing and says why in the browser console. The contents can also be
pasted into Elementor Pro → Custom Code inside a script tag, with the same two
`data-` attributes on that tag. Nothing downloads until a visitor clicks "Talk
to Aria", except Aria's picture for the button (her still image, from the
avatar's `listCharacters()`), fetched once the page has settled.

It sits at the bottom right at 1.3x (1.1x up to 768px wide), where KDEM placed
it on their site; on a short screen it shrinks just enough that the open
panel's top stays on screen. The panel ends with a small "Powered by Voqalize"
link to voqalize.com.

## Walking the site: she asks before she moves the page

Aria can take a visitor to another page of the site and point at part of the
page they are on.

- **Another page: she asks first.** She offers in one short line ("Shall I take
  you to the Seed Fund page?") and calls `offer_page` with it, which moves
  nothing. When they say yes, in their next turn, she calls `go_to_page` and the
  brain sends `navigate`. A visitor who asks to be taken somewhere ("take me to
  the events page", "open the policies page") has already said yes, and she
  goes at once. The rule is held in code, not only in the prompt:
  `go_to_page` is sent only for the page `offer_page` offered in her previous
  turn, or when the visitor's own words this turn ask to go (in English or
  Kannada). Otherwise it is refused with "ask first", and nothing moves.
- Only pages Aria may link are opened: the same approved-and-indexed rule as
  `show_document`, with a PDF on another site opening its KDEM page. A PDF opens
  beside her with `show_document` instead, so the call stays on this page; the
  page they are already on is pointed at, not opened again.
- **Part of this page: she just points.** `point_at` takes a short exact phrase
  (under 80 characters) that the brain checks is in the text of the page the
  visitor has open, ignoring case and spacing. A phrase from another page is
  refused. After she takes them to a page, `page_viewed` tells her they
  arrived, and she carries on the conversation there, pointing at what they
  need, without greeting them again.

**KDEM has to update the script tag on the site** to this version for any of
this to work: the same single file, now with the agent and key on the tag. An older script ignores `navigate` and `point_at`, so Aria's line
is heard and nothing moves.

The site has to allow the microphone for its own pages. If it sends a
`Permissions-Policy` header, that header must include `microphone=(self)`.
Otherwise the browser blocks the microphone and Aria cannot hear the visitor.

karnatakadigital.in sends no Content-Security-Policy today. If it adds one, it
has to allow:

```text
script-src  https://cdn.jsdelivr.net https://avatar.voqalize.com
connect-src https://app.dev.voqalize.com https://avatar.voqalize.com blob:
            and the media node each session names for its offer
img-src     https://avatar.voqalize.com blob:
```

The media node is chosen per session, so ask Voqalize for the hosts to list.
It does not need `c.daily.co` or `'unsafe-eval'`: those were for daily's call
machine, which pipecat's transport only starts when it is given no media
manager, and the snippet gives it ours. (The transport still imports daily's
library module, from jsDelivr like the rest; it never creates a call with it.)
The pipecat and transport bundles contain no `eval`, and the avatar's own
sources are the ones its documentation lists, above.

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
- it is read in a child process of its own: 384 MB of memory beyond the
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

The test files run without network access. The PDFs in the tests are built in
the test from a few neutral sentences. The e2e tests load a small, made-up
snapshot into the knowledge base, and `tests/conftest.py` turns the background
refresh off for every test.
