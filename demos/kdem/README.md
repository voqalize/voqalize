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
| `backend/brain.py` | Aria: the prompt, the greeting and the tools (`search_kdem`, `show_link`, `set_language`) |
| `backend/app_events.py` | `page_viewed`, the one event the snippet sends the brain |
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

`embed/voqalize-aria-kdem.js` is plain JavaScript. It goes into any "Custom
JavaScript" box as it is, or, inside a `<script>` tag, into Elementor Pro →
Custom Code with the location set to the end of `</body>`. Nothing downloads
until a visitor clicks "Talk to Aria", except Aria's picture for the button
(her still image, from the avatar's `listCharacters()`), fetched once the page
has settled. The agent id and the publishable key are placeholders
(`REPLACE_WITH_...`). They are filled in when the snippet is handed over, and
never committed.

It sits at the bottom left, clear of the site's own chat button on the right;
on a phone it sits higher, above the site's chat strip.

It loads these libraries from jsDelivr, each pinned to an exact version in the
script: pipecat's `@pipecat-ai/client-js`, `@voqalize/client-transport` 0.3.1
and the `@voqalize/avatar` the other demos use. The call is pipecat's client on our transport, whose
media manager is ours rather than daily's, so daily's call machine is never
loaded from `c.daily.co`.

**A call carries on across page loads.** The transport is created with
`createVoqalizeTransport({ mediaManager, keepAcrossPageLoads: true })`. It keeps
the call's connection request in `sessionStorage`, per tab, and the next page
of the site rejoins the same call with a bare `connect()`: no new session, and
the conversation goes on where it was. Voqalize holds a dropped call for a few
seconds for exactly this. The snippet never hangs up on `pagehide`, since the
page going away is what the call has to survive; a page restored from the
back/forward cache is reloaded so it rejoins properly. A visitor who leaves the
site lets the call end on its own. **End** sends `disconnectBot()`, which ends
the call at once, so the next page does not dial back. A visitor who muted
stays muted on the next page.

At the top of the panel is an **English | ಕನ್ನಡ** toggle: two buttons with
`aria-pressed`, usable from the keyboard. It always shows the language the call
is actually in. Pressing the other side sends `language_requested`, and the
toggle moves only when the brain answers `language_changed`, so a switch made by
voice moves it too and a switch Voqalize refused leaves it where it was. The
choice is remembered for the tab (`sessionStorage`, `vq-aria:lang`); pressed
with no call, it picks the language the next call starts in.

The snippet and the brain share these:

- **`init`**: the snippet sends `{surface: "kdem-web", page: location.pathname,
  lang: "en" | "kn"}` with `sessions.connect`. `lang` is the toggle's choice:
  `"kn"` opens the call in Kannada, with both legs on Kannada and a written
  Kannada greeting; anything else opens in English. A rejoin after a page load
  sends no `init`, and the call keeps the language it is in. The brain reads
  `page` so it knows which page the visitor started on. When `page` is a page
  Aria may link right now, the prompt names it by its own title and path.
  Anything else, including an excluded page or a path the index does not hold,
  is left out of the prompt: the brain never quotes what the browser sent.
  `surface` and `lang` are logged.
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
- **`page_viewed`**: on every connect and rejoin, the snippet sends the RTVI UI
  event `page_viewed` with `{path, title}`. Since the call follows the visitor
  around the site, this is how Aria learns they moved. The brain takes it in
  silently: Aria does not speak because a page changed, and her next turn knows
  where they are. The page is named by its own title only when it is one Aria
  may link now; any other page is "a page of the site", and the title the
  browser sent is never quoted. A rejoin on the same page, and any event that
  does not fit, change nothing.
- **`language_requested`** (page → brain, `{language: "en" | "kn"}`): the
  visitor pressed the toggle. The brain switches both legs in code, not through
  the model, in one awaited request, and tells the model with a line in its
  context. Aria confirms with a written line in the new language, read by the
  new voice ("Sure, let's continue in English." or "ಸರಿ, ಈಗ ಕನ್ನಡದಲ್ಲಿ
  ಮಾತಾಡೋಣ."). A brain has no floor outside a turn, so the line opens her next
  turn, before her reply, and never talks over anyone. Asking for the language the call is already in, or a value
  that is not `"en"` or `"kn"`, does nothing.
- **`language_changed`** (brain → page, `{language: "en" | "kn"}`): the language
  the call is in now, sent after every switch, by the toggle or by voice. It is
  the toggle's only source of truth. A switch Voqalize refuses sends the
  language that still holds, so the toggle goes back.

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
