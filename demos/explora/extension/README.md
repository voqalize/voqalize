# Javier for Explora — the extension

A Chrome extension that puts Javier, a voice guide with an animated face, on
[www.explora.com](https://www.explora.com) and its booking engine,
[reservations.explora.com](https://reservations.explora.com). He talks a
visitor through Explora's lodges and expeditions while he moves their screen:
he opens the page that answers them and scrolls to the exact section, rings a
lodge, a room or an exploration, opens the site's tabs and accordions, opens a
question in a lodge's FAQ, checks a lodge's availability with them on the
booking site and fills in an expedition's enquiry. Everything he shows is a
page, section or form Explora already has; the extension adds a corner widget
and the ring he draws around what he is pointing at.

This is how we show the agent to Explora on their own site, before anything
goes on it; it is not how a customer would ship it.

## What is in it

- `src/explora-actions.ts` — the www.explora.com adapter. It performs the
  brain's page Actions (`navigate`, `show_section`, `open_faq`) on the tab in
  front and reports the page (`page_changed`): its headings, its questions,
  its tabs and accordions, and its own sub-menu. The headings are read with
  the crawler's rules (`../backend/knowledge/L3/build_main.py`), so the names
  the brain knows from the crawl are the names the page finds. What is asked
  for inside a closed tab pane, a collapsed accordion or a carousel slide out
  of view is brought out first, the way a visitor would: a click on its tab or
  trigger, or the carousel's own `to.owl.carousel`.
- `src/reservations-actions.ts` — the reservations.explora.com adapter:
  `check_availability`, `choose_room`, `fill_enquiry`, `send_enquiry` (see
  below).
- `src/dom.ts` — what both adapters share: the ring, scrolling the window
  under Explora's fixed header and sticky sub-menu, and setting a form field
  the way the site's own scripts notice.
- `src/site-language.ts`, `src/hreflang.ts` — the site follows the call's
  language (see below).
- `src/narration.ts` — the screen follows his voice. The brain sends each
  section or question cue he wrote into his reply ahead of the speech, with
  the first words of the sentence it belongs to; this fires it when the call's
  spoken-text events (`bot-output`, released as the audio plays) reach those
  words, one move at a time. With no spoken text, it times cues from the start
  of the speech instead; when the visitor talks over him, the rest is dropped.
  It runs in the holder, so a load ends nothing.
- `src/holder.ts`, `src/call.html` — the holder: the call, his voice, the tab
  registry, the routing of each Action, the pacing of a page load against his
  voice, the site following the call's language, the moves kept for loading
  tabs, the 15 s rule (below); `src/call-client.ts` makes the pipecat client
  and reads the microphone permission.
- `src/relay.ts`, `src/follow.ts` — what crosses from the holder to the pages
  for his face, and the stand-in client the avatar draws against.
- `src/protocol.ts` — the messages between the pages, the holder and the
  service worker, and which Actions go where.
- `src/bridge.ts`, `src/hub.ts` — the page's port to the holder and its
  requests of the service worker: the move a page leaves for the next one
  (`loadThen`, which may be on the other host) and a www.explora.com page's
  translation for the booking site.
- `src/background.ts` — the service worker (below).
- `src/grant.ts`, `src/grant.html` — the extension's one-time microphone
  grant (below).
- `src/widget.ts` — the corner widget, in a shadow root, dressed in Explora's
  black, white and sand: the call, and the English/Español toggle. Off a call
  the toggle picks the language the next call starts in; in a call it asks the
  brain to switch, from any tab. Javier also switches by himself when the
  visitor speaks the other language, and the toggle follows him. The page's
  own TalkCenter chat launcher stands aside while the extension runs. It also
  holds the grant frame and the "microphone blocked" message.
- `src/shell.ts`, `src/persist.ts` — the early shell, what a page in a call
  leaves for the next one, and the view transition (below).
- `src/content.ts` — the page: the widget, his face, the adapter of its host,
  the moves the holder sends (loading the other host when a move belongs
  there), and on the call button the microphone check and `sessions.connect`
  (`surface: "explora-ext"`).
- `src/actions.gen.ts` — the Action and event unions, generated from the brain
  with `pnpm gen`. Regenerate after changing either.

The brain is `../backend/`: the prompt, the tools, and Explora's knowledge.

## Build and load

```sh
cp .env.example .env     # the agent id and a publishable key (see below)
pnpm install --ignore-workspace
pnpm build               # → dist/
```

Then `chrome://extensions` → Developer mode → **Load unpacked** → `dist/`, and
open www.explora.com. The first call asks for the microphone (below). `pnpm
build:prod` builds the same extension against production into `dist-prod/`,
from `.env.prod`.

The publishable key's allowed origins must include `https://www.explora.com`,
`https://explora.com` and `https://reservations.explora.com`: a call can start
on any of them, and the page mints the session. The agent id and key are
baked into the bundle at build time and are never committed: this repo is
public.

**The extension id is fixed.** `manifest.json` carries a `key` (an RSA public
key; it is not a secret), so the unpacked extension has the same id from any
folder and on any machine, and the microphone grant made once holds across
rebuilds and moves. The private key is not in the repo and is not needed to
load unpacked (only to pack a `.crx`). `dist/` and `dist-prod/` share the id:
load one of them at a time. Anyone with a build from before this key loads
it again once: the id changed with it.

The build works without them. With an empty `.env` it warns, and the extension
loads with everything but the call: the widget and every page Action still work
from the console (below).

## Driving it from the console

With the extension loaded, every page Action can be sent exactly as the brain
would send it, from the page's DevTools console, with no call:

```js
// On https://www.explora.com/lodge/atacama-lodge/
await __voqalizeExplora.perform("show_section", { heading: "Stargaze from Explora’s Observatory", text: null });
await __voqalizeExplora.perform("show_section", { heading: "Included with Your Stay", text: null });
// On the home page: a destination of the map's accordion, by its label.
await __voqalizeExplora.perform("show_section", { heading: "Sacred Valley of the Incas [Peru]", text: null });
// On https://www.explora.com/patagonia-travel-argentina-chile/: a Why Explora tab.
await __voqalizeExplora.perform("show_section", { heading: "Territory Expertise", text: null });
// On https://www.explora.com/atacama-travel-tips/
await __voqalizeExplora.perform("open_faq", { question: "How many days should I spend in the Atacama Desert?" });
// A page, and a heading on it once it has loaded.
await __voqalizeExplora.perform("navigate", {
  path: "/atacama-desert-explora-lodge/", after_words: 0, heading: "Scenic Spa, Pools & More", text: null, faq: null,
});
```

The narration (the cues fired as he speaks) runs in the holder with the call,
not in the page, so it is not on the console; `test/holder.spec.ts` drives it
through the stand-in call.

`__voqalizeExplora.perform` sends a move to this page's adapter, or, for a move
that belongs on the other host, loads that host with the move kept for it
(`check_availability` from www.explora.com opens the lodge's page on the
booking site). A move that could not be made comes back as the
`command_failed` the brain would receive, at once, with the reason in words the
model can act on: a heading that is not on the page lists the first twenty
labels that are showing; a question that is not there lists the page's
questions.

What the page reports is what shows at the window's width. Explora often
renders a block twice, a desktop row and a mobile accordion with one of them
`display: none` (`d-none d-md-block` / `d-md-none`); a heading, tab or
question inside the copy the layout hides is never reported or used, while
one inside a closed tab, accordion or carousel slide is, and is opened first.
Besides the crawler's headings, every laid-out `h4` that is not a menu entry,
an accordion trigger or a question is a heading too (the Sacred Valley's
exploration zones). A label asked for that is hidden gives way first to a
laid-out label of the same name, which is ringed with its block.

## Every move is a full page load

Neither host routes client-side: every link, on www.explora.com and on the
booking site, loads a new page, and a booking step loads the other host in the
same tab. The call does not mind (below); what follows from the loads is how
the moves are paced and carried.

- **Paced page cues.** A tool call moves the page once the model has written
  the whole reply, which the voice then takes many seconds to say. So the
  model writes `{page: …}` into its reply where the page should go, and the
  brain takes it out and sends `navigate` with `after_words`, the words of his
  that come before it. Those words have been sent but may not be playing yet,
  so the holder waits before it sends the move to the page: for his voice to
  start (up to four seconds), then to stop and stay quiet for 300 ms, within
  `after_words / 2.8` seconds plus six. With `after_words` 0 it only waits for
  him to be quiet, up to three seconds; a booking step from www.explora.com,
  which loads the booking site, waits the same way. His voice no longer stops
  at a load (it plays from the extension), so this is not what keeps a
  sentence whole any more; it is kept as the pacing the brain was written
  against, the page changing once he has said what leads to it. The brain says
  nothing more until the new page reports `page_changed`, which it does once
  the call is up on it; then his `{show: …}` cues for that page follow.
- **The move for the next page.** A move that needs the next page (a heading
  on it, the booking step after a load) is kept by the service worker for this
  browser tab (`loadThen`, in `chrome.storage.session`, since the next page
  may be the other origin) and made once the call is up there, 300 ms after
  the page has reported itself; with no call, 800 ms after the page knows there
  is none.
- **Links stay in the tab.** While a call is live, links to either Explora host
  lose `target="_blank"`, so the visitor's own clicks load in the tab Javier
  is moving rather than in a new one. A new tab would follow the call too; the
  brain moves the tab in front, and one tab is the walk it expects.

## How the call lives through page loads

The call does not live in a page: it lives in an **offscreen document of the
extension** (`call.html`, `src/holder.ts`, "the holder"), which no page load
touches, on either host or between them.

- **The holder** runs stock pipecat on `@voqalize/client-transport`, plays his
  voice, keeps every open Explora tab on both hosts (by browser tab id: its
  port, where it is, whether it is in front) and sends the brain
  `tabs_changed`, routes each brain Action to the tab it belongs on (the one
  in front, else the Explora tab last in front, brought forward, else a new
  one), paces page loads against his voice (above), has the site follow the
  call's language (below), fires his cues as he speaks (`src/narration.ts`)
  and relays to the pages what they need to draw his face (`src/relay.ts`:
  pipecat's events, the avatar's sync channel, which the holder opens and
  says hello on, and the mouth clock).
- **Every page is a follower** (`src/content.ts`): the widget, his face (the
  unchanged avatar against a stand-in client fed by the relay,
  `src/follow.ts`), the adapter of its host, and the moves the holder sends it.
  A move that belongs on the other host it makes by loading that host. It
  reports what it shows up the port. The stand-in carries the relayed mouth
  clock forward to each read of it, for at most 100 ms (`src/mouth-clock.ts`):
  a busy page reads the relay late, and the face takes a late reading for a
  stop and shuts his mouth over his voice. A face made in the middle of a
  reply (a page that loads while he speaks) asks the holder for the reply so
  far (`src/catch-up.ts`: its place on the stream, its cues, its end, and that
  he is speaking), since the reply's cues usually went out before the page
  existed; until that answer has come and the face is listening, the page
  holds what arrives and then hands it over in order. Each page keeps one port to the holder
  (`src/bridge.ts` in the isolated world, `src/hub.ts` in the page's world).
- **The service worker** (`src/background.ts`) makes the holder on the first
  press of the call button, with the reasons `USER_MEDIA` and `WEB_RTC` (they
  keep the document alive through any silence; `AUDIO_PLAYBACK` alone closes
  it after 30 s without sound), one at a time, and tells every Explora tab
  when it is up (`holder-up`): a port opened before the holder existed has no
  one at the other end, so pages open theirs on that word. It also opens and
  focuses tabs for his moves (an offscreen document has no `chrome.tabs`),
  keeps each tab's move for its next page, and reads www.explora.com's
  translations for the booking site.
- **The session is minted by the page.** On the call button the page calls
  `sessions.connect` with the publishable key (its fetch carries an Explora
  Origin, which the key allows; a `chrome-extension://` origin cannot be added
  to a publishable key) and hands the answer to the holder, which connects.
- **A move for a page that is loading waits for it.** When a page starts
  loading another document it tells the holder (`leaving`); a move sent to
  that tab meanwhile is kept and delivered when the next page says `hello`,
  whichever host that page is on.
- **The call ends** on End (any tab), when the call drops, or when no Explora
  page has been open for 15 s; the holder then closes. Reloading or updating
  the extension ends it too.

## The widget across a page load

The call outlives a page load, and in a call the widget does too, as near as a
page can: on a load within one host it is back the moment the next page shows,
not once the page has parsed and the site's scripts have run.

- **What the page leaves.** While a call is on, `content.js` keeps a picture of
  it in the tab's `sessionStorage` (`src/persist.ts`): live or connecting,
  muted or not, the status line, the language, where the visitor put the widget
  and whether it is minimised, the character's still, and the last frame his
  face drew (read from the avatar's canvas every 3 s and as the page leaves).
  It is taken away when the call ends, and is stale after 60 s.
- **The early shell.** `shell.js` (`src/shell.ts`) runs in the page's world at
  `document_start`, before any of the page's scripts. Off a call it reads that
  one key and does nothing else. In a call it mounts the widget on `<html>` at
  once, as the last page left it, with the last frame of his face as a still
  where his face goes. `content.js` (still at `document_idle`) adopts that
  widget instead of mounting another, asks the holder for the call's state as
  before, starts building his face at once (`preloadAvatar`), and fades the
  still out once the live face has drawn. The still is never a frozen face:
  from the page's first paint it moves in CSS alone (`.poster` in
  `src/widget.ts`), a slow breath while he listens and a talking head while
  he speaks, held still under reduced motion. Its lips do not move, and the
  half second or so in which Chrome swaps the documents shows the last page's
  last frame, where nothing can move. Should the holder be gone (no
  holder, or no word from it in 8 s), the carried widget goes back to the
  invite.
- **The view transition.** In a call both pages opt in to a cross-document
  view transition (`@view-transition { navigation: auto }`, Chrome 126+): the
  page that leaves (`content.js`, while a call is on) and the page that arrives
  (`shell.js`, from what was kept). The widget's host has its own
  `view-transition-name` (`voqalize-javier`), so the page fades under it in
  150 ms while it stays where it is. The host is a see-through, fixed box over
  the viewport that takes no pointer events (the widget inside it does), so it
  is captured whole and in place. Older Chrome ignores the rule and loads the
  page as before, with the widget still up early. Off a call no transition is
  asked for.
- **Across hosts there is neither.** `sessionStorage` and view transitions are
  both same-origin, and www.explora.com and reservations.explora.com are two
  origins: a load from one to the other has no early widget and no
  transition, and the widget comes back at `document_idle`. The call, and his
  voice, carry on through it all the same.

## The microphone, once

The microphone is the extension's, not Explora's: Chrome keeps the permission
against `chrome-extension://<id>`, `chrome.contentSettings` cannot set it for
that origin, and an offscreen document cannot show a prompt. (So the old
`contentSettings` permission, which allowed the microphone on both Explora
hosts for a call carried across them, is gone: the pages no longer use the
microphone.) On each press of the call button, the page asks the holder for
the extension's microphone permission state first:

- **granted**: the call starts.
- **prompt** (the first call): the widget shows the extension's own page
  `grant.html` in a frame (`<iframe allow="microphone">`), which asks at once.
  Chrome's prompt names the extension ("Javier for Explora wants to use your
  microphone"); the visitor chooses *Allow*. The holder then reads the state
  again: granted, the call starts. Should it still not be granted (the grant
  was stored for the site rather than the extension, or it was *Allow this
  time*), `grant.html` opens once in a tab of its own, asks the same way,
  closes itself once answered, and the call starts.
- **denied**: the widget says Chrome blocks the microphone for the extension,
  with a button that opens `chrome://settings/content/microphone`, where the
  visitor takes "Javier for Explora" off the blocked list.

Neither host sends a `Content-Security-Policy` or a `Permissions-Policy` (by
header or `<meta>`, checked 2026-10-23), so the grant frame (`frame-src`), the
still of his face as a `data:` URL (`img-src`) and the frame's
`allow="microphone"` are not blocked, and the extension needs no rule to
change them. Should either host start sending one, the grant tab still works.

## What the visitor sees

The first time: the press, then Chrome's microphone prompt naming the
extension under the widget (and, only if that grant does not hold, a short-
lived tab with the same prompt), then Javier. After that, the press and
Javier. Pages load as they always do; the widget comes back on each new page
already live, his voice carries on across the load, on either host, and the
moves he started finish on the page they land on.

**His voice plays from the extension, not from the tab.** Muting the tab
(right-click → Mute site) does not silence him; the widget's *Mute* mutes the
visitor's microphone, and *End call* ends the call. Chrome shows the
microphone in use for the extension rather than for the tab.

## The site follows the call's language

www.explora.com is WordPress with WPML: Spanish lives at `/es/…` under
translated slugs (`/lodge/atacama-lodge/` ↔
`/es/lodge/hotel-en-san-pedro-de-atacama/`), and every page names its
translations in its `<head>` (`<link rel="alternate" hreflang="es">`).

- **When the language moves** (the brain's `language_changed`: the visitor
  spoke Spanish, asked, or pressed the toggle), the page in front waits for
  Javier to finish confirming it aloud (up to 3 s) and loads its twin: the
  `hreflang` link, else the language selector's link, else `/es/` or `/`. A
  `navigate` that arrives meanwhile wins. The holder decides when (it hears
  his voice); the page in front makes the load, with its own translations. A page in Portuguese, French or
  German is left alone. On the booking site the step is loaded again with
  `?language=ES|EN` swapped in, only where that loses nothing: paso1 (with the
  lodge and day carried in the URL), paso2 when its URL carries the stay, and
  the expedition enquiry while nothing is filled in. Never paso3.
- **`navigate` names the English page**, because the brain knows the English
  site. While the call is in Spanish, the English page's `<head>` is fetched
  (same-origin, read only up to `</head>`; through the service worker from the
  booking site) and its Spanish twin is loaded, or the English page when it
  has none. The lookup runs on the page as the move arrives there; it takes
  60–150 ms when Explora's CDN has the page and about a second when it does
  not, and each answer is kept in the tab's `sessionStorage`. The page's own
  links answer for its translations at no cost.
- **A `navigate` to the page already in front** (by path; query, hash and a
  trailing slash aside, and any translation of it) does not load it again: the
  move is made on it and it reports `page_changed` once more, which the brain
  waits for.
- **On a translated page** a heading, words or question kept for it by a
  `navigate` are the brain's English names, which may not be there: one that
  is not found is skipped, not failed. A `show_section` or `open_faq` sent
  directly still fails with the page's own (Spanish) headings listed, which
  the brain can then use.
- **At the start**, `init.site_lang` (`"es"` or `"en"`) tells the brain the
  language the site is followed in: the visitor's toggle choice, else the
  language of the page they started on. `init.lang` is still sent only when
  the visitor chose on the toggle. Off a call the toggle shows the page's
  language until the visitor chooses one.
- **The call's language is the call's, not the page's.** It is recorded the
  moment the call starts (and again by the brain's `language_changed` with
  `site: "stay"`) and kept by the holder (`state.language`), which every page
  of the call, on either host, takes it from; no page reads it off itself. An
  English page that comes up in a Spanish call does not make the call English.
  Off a call the toggle is the visitor's own choice again.
- **The lookup never holds a load.** A `navigate` waits at most two seconds
  for the twin, then loads the English page as named. The lookup reads the
  page's head from the page, then from the extension's service worker (which
  no script of the page can wrap; `source: "hub"`) when that fails; a page that
  answers with no translations at all is not remembered as having none.
  Every lookup is reported to the brain as `twin_lookup`: the URL loaded,
  where it came from, how long it took, and why it failed.
- **A page that came up in the wrong language** is loaded again as its own
  twin when the brain asks (`language_changed` with `site: "twin"`), from the
  page's own `<head>`: never that language's home page. A page with no twin
  reports `command_failed` for `language_changed`, and one already in that
  language reports itself again. The brain asks when a page it opened in a
  Spanish call came up in English, and when the visitor asks to see the page
  in the call's language.
- **A `navigate` that never takes the page away** (eight seconds after its
  load began, and no `pagehide`) is reported as `command_failed`, by the page
  that started the load. The holder, which kept any move sent meanwhile for
  the next page, has that page say hello again after five seconds and sends
  them there.

From the console, with no call:

```js
await __voqalizeExplora.setLanguage("es");   // as if the call moved to Spanish; the page loads in Spanish
__voqalizeExplora.language();                // "es"
await __voqalizeExplora.mapPath("/lodge/atacama-lodge/");  // {url, source, ms}
await __voqalizeExplora.perform("navigate", { path: "/lodge/atacama-lodge/", after_words: 0, heading: null, text: null, faq: null });
```

## One call, every tab

The call belongs to no tab: it lives in the holder. Every Explora tab, on
either host, shows Javier's face and the call's state and can mute or end it;
the tab in front is the one he sees and moves. Closing a tab ends nothing
while another Explora tab is open; with none open for 15 s the call ends. The
usual case is one tab that loads between the two hosts.

## The booking site

On reservations.explora.com Javier works the booking engine with the visitor
(`src/reservations-actions.ts`):

- `check_availability` picks the lodge, reads the calendar's open days, and
  with a day and a number of nights goes on to the rooms and rates.
- `choose_room`, on the rooms and rates, sets a room's travellers and bed
  type (King or Twin) and presses that room's own "Add this room", which
  opens its summary in a popup. He rings the popup's "I'm ready. Go to
  check-out" for the visitor and never presses it: he never reaches
  check-out and never books. With no bed type he rings the room's bed
  select and asks. With `count`, or when a room's summary is still open, the
  next room goes through the popup's own "Add more rooms" (the rest of the
  move is kept for the next page, should that button load the rooms again).
- `fill_enquiry` opens an expedition's enquiry form and fills in what the
  visitor told him. `send_enquiry` presses Send Message only once the visitor
  has ticked the reCAPTCHA themselves; until then he asks them to.

## Tests

```sh
pnpm test:e2e
```

Playwright, headless, no network: `test/holder.spec.ts` loads the built
extension (`VOQALIZE_TEST_BUILD=1`, into `test/.build/ext`) with a stand-in
call in the holder (`test/fake-call-client.ts`), a stand-in avatar
(`test/fake-avatar.ts`) and a made-up API, against small pages served at
www.explora.com's and reservations.explora.com's addresses. It covers the
port protocol, a move kept across a load and made on the next page's hello
(on one host, and across hosts with the move the booking site's page leaves
for www.explora.com), the 15 s rule, the microphone's branches, and the widget
across a load. The brain's own tests are `demos/tests/test_explora_*.py`.
