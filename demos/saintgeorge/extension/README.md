# Javier for Saint George's College — the extension

A Chrome extension that puts Javier, a voice guide, on
[saintgeorge.cl](https://saintgeorge.cl), the site of Saint George's College in
Santiago. He talks a family through the school in Spanish or English while he
moves their screen: he opens the page that answers them and scrolls to the
exact section, opens the accordion of their child's grade, reads the fees and
the admission status off the admission page, reads what is coming up off the
school's public calendar, opens documents and the musical's tickets in a new
tab, and readies an email to the admissions office that the parent sends
themselves. One call follows the visitor across every tab of the site they have
open and every page they move to, and his voice carries on through each page
load. Everything he shows is a page, section,
accordion or link the site already has; the extension adds a corner widget, the
ring he draws around what he is pointing at, and the contact card.

This is how we show the agent to the school on its own site, before anything
goes on it; it is not how a customer would ship it.

## What is in it

- `src/saintgeorge-actions.ts` — the site adapter. It performs the brain's page
  Actions on the tab in front and reports every page the visitor lands on,
  whoever took them there: its headings, accordions, cards and links out. The
  site has no client router, so a move to another page is a full page load; the
  adapter keeps what is left of the move (the section, the accordion, or the
  whole read of the fees or the calendar) in `sessionStorage` and makes it once
  the next page is up. Accordions are found by their buttons' words, since
  their ids repeat from page to page, and opened through the page's own
  Bootstrap.
- `src/ical.ts` — the school's public calendar feed, parsed: each event's day,
  its time in Santiago, its title. The feed sends no CORS headers, so the
  extension's service worker fetches it (`background.ts`); the brain never
  does.
- `src/anchors.ts`, `src/anchor.ts` — what the adapter matches on (headings,
  accordion buttons, the fee and admission lines) is kept out of Chrome's
  translator from `document_start`, so a parent reading the site in English
  still gets every move.
- `src/narration.ts` — the screen follows his voice. The brain sends each
  screen cue he wrote into his reply ahead of the speech, with the first words
  of the sentence it belongs to; this fires it when the call's spoken-text
  events reach those words, one move at a time. A cue to another page fires at
  once, so the load overlaps his reply. It runs in the holder, so a load ends
  nothing.
- `src/holder.ts`, `src/call.html` — the holder: the call, his voice, the tab
  registry, the routing of each Action, the moves kept for loading tabs, the
  15 s rule (below); `src/call-client.ts` makes the pipecat client and reads
  the microphone permission.
- `src/relay.ts`, `src/follow.ts` — what crosses from the holder to the pages
  for his face, and the stand-in client the avatar draws against.
- `src/protocol.ts` — the messages between the pages, the holder and the
  service worker.
- `src/mouth.ts`, `src/level.ts`, `src/meter.ts` — his lips on the still the
  next page shows until its face draws, moving with his voice's loudness.
- `src/bridge.ts`, `src/hub.ts` — the page's port to the holder and its
  requests of the service worker (the calendar read among them).
- `src/background.ts` — the service worker: makes the holder, opens and
  focuses tabs for his moves (only on hosts the site itself links), opens the
  microphone grant tab, reads the school's calendar, keeps the language choice.
- `src/grant.ts`, `src/grant.html` — the extension's one-time microphone
  grant (below).
- `src/widget.ts` — the corner widget, in a shadow root, in the school's blue
  and yellow: the call and the Español/English toggle, its words in the
  toggle's language. Javier also switches by himself when the visitor speaks
  the other language, and the toggle follows him. It also holds the grant
  frame and the "microphone blocked" message.
- `src/shell.ts`, `src/persist.ts` — the early shell, what a page in a call
  leaves for the next one, and the view transition (below).
- `src/content.ts` — the page: the widget, his face, the adapter, the moves
  the holder sends, and on the call button the microphone check and
  `sessions.connect` (`surface: "saintgeorge-ext"`).
- `src/actions.gen.ts` — the Action and event unions, generated from the brain
  with `pnpm gen`. Regenerate after changing either.
- `test/entry.ts` — the bundle `demos/tests/test_saintgeorge_page.py` runs in
  headless Chromium against saved copies of the site's pages
  (`../fixtures/`). Never shipped.
- `test/holder.spec.ts` — the holder and its pages, end to end in a test build
  of the extension (below). Never shipped.

The brain is `../backend/`: the prompt, the tools, and the school's knowledge.

## Build and load

```sh
cp .env.example .env     # the agent id and a publishable key (see below)
pnpm install --ignore-workspace
pnpm gen                 # after any change to the brain's Actions or events
pnpm build               # → dist/
```

Then `chrome://extensions` → Developer mode → **Load unpacked** → `dist/`, and
open saintgeorge.cl. The first call asks for the extension's microphone
(below). `pnpm build:prod`
builds the same extension against production into `dist-prod/`, from
`.env.prod`.

The publishable key's allowed origins must include `https://saintgeorge.cl`
and `https://www.saintgeorge.cl`, which are where the session is minted from:
the page mints it, not the extension.
The agent id and key are baked into the bundle at build time and are never
committed: this repo is public.

The call opens in Spanish, as the site does. A visitor who presses English on
the toggle before the call starts gets the call in English, and keeps it
whatever they speak, until they ask for the other.

The site sends no `Permissions-Policy`, so the grant frame's
`allow="microphone"` needs no header rule. If the microphone cannot open, the
widget says so and ends the call rather than showing "live".

**The extension id is fixed.** `manifest.json` carries a `key` (an RSA public
key; it is not a secret), so the unpacked extension has the same id from any
folder and on any machine, and the microphone grant made once holds across
rebuilds and moves. The private key is not in the repo and is not needed to
load unpacked (only to pack a `.crx`). `dist/` and `dist-prod/` share the id:
load one of them at a time.

The build works with no agent id or key. With an empty `.env` it warns,
and the extension loads with everything but the call: the widget and every page
Action still work from the console (below).

## Driving it from the console

With the extension loaded, every page Action can be sent exactly as the brain
would send it, from the page's DevTools console, with no call:

```js
// On the home page: the tour.
await __voqalizeSaintGeorge.perform("show_section", { heading: "Nuestros valores", text: null });
// A grade on its unit's page, after the load.
await __voqalizeSaintGeorge.perform("navigate", { path: "/unidad/elementary", heading: null, text: null, faq: "1º BÁSICO" });
// The fees, read off the admission page (it goes there first).
await __voqalizeSaintGeorge.perform("show_fees", { path: "/admision/admision", about: "fees" });
// The contact card: nothing is sent; the parent presses its button.
await __voqalizeSaintGeorge.perform("show_contact_card", {
  to: "admisiones@saintgeorge.cl", subject: "Consulta de admisión", body: "Hola,\n\n…",
  phone: "+56 2 2355 6181", language: "es",
});
```

A move that could not be made comes back as the `command_failed` the brain
would receive, with the reason in words the model can act on: an accordion
that is not on the page lists the ones that are. What a move reads (the fees,
the calendar) goes to the brain as an event once the call is on; from the
console, `window.voqalizeSaintGeorge.start(console.log)` prints them.

## How the call lives through page loads

The site has no client router: every move to another page (a unit, the
admission page, the calendar) loads a whole page. The call therefore does not
live in a page: it lives in an **offscreen document of the extension**
(`call.html`, `src/holder.ts`, "the holder"), which no page load touches.

- **The holder** runs stock pipecat on `@voqalize/client-transport`, plays his
  voice, keeps every open Saint George's tab (by browser tab id: its port,
  where it is, whether it is in front) and sends the brain `tabs_changed`,
  routes each brain Action to the tab it belongs on, fires his cues as he
  speaks (`src/narration.ts`) and relays to the pages what they need to draw
  his face (`src/relay.ts`: pipecat's events, the avatar's sync channel, which
  the holder opens and says hello on, and the mouth clock).
- **Where each Action goes.** A move on a page (a section, an accordion, the
  contact card) goes to the tab in front. A move to another page (a page, the
  fees, the calendar) goes to a site tab: the one in front, else the visitor's
  other site tab, brought to the front, else a new one, which makes the move
  once it is up. A document or a link out (a PDF, the musical's tickets, a
  families' portal) opens in a tab of its own, through the service worker; the
  extension does nothing on that tab and it never joins the tab list.
- **Every page is a follower** (`src/content.ts`): the widget, his face (the
  unchanged avatar against a stand-in client fed by the relay,
  `src/follow.ts`), the site adapter, and the moves the holder sends it. It
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
  it after 30 s without sound), one at a time, and tells every Saint George's
  tab when it is up (`holder-up`): a port opened before the holder existed has
  no one at the other end, so pages open theirs on that word. It also opens and
  focuses tabs for his moves (an offscreen document has no `chrome.tabs`),
  reads the school's calendar (its feed sends no CORS headers, so the page
  cannot, and the brain, far from Chile, must not) and keeps the language
  choice.
- **The session is minted by the page.** On the call button the page calls
  `sessions.connect` with the publishable key (its fetch carries
  saintgeorge.cl's Origin, which the key allows; a `chrome-extension://` origin
  cannot be added to a publishable key) and hands the answer to the holder,
  which connects.
- **A move for a page that is loading waits for it.** When a page starts
  loading another document it tells the holder (`leaving`); a move sent to
  that tab meanwhile is kept and delivered when the next page says `hello`.
  A move that itself loads a page finishes there (the adapter's
  `sessionStorage` leftover, as before).
- **The call ends** on End (any tab), when the call drops, or when no Saint
  George's page has been open for 15 s; the holder then closes. A tab Javier
  opened on another host (the musical's tickets, a portal) does not count: if
  the visitor closes every Saint George's tab, the call ends 15 s later.
  Reloading or updating the extension ends it too.

## The widget across a page load

The call outlives a page load, and in a call the widget does too, as near as a
page can: it is back the moment the next page shows, not once the page has
parsed and the school's scripts have run.

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
  still out once the live face has drawn. Should the holder be gone (no
  holder, or no word from it in 8 s), the carried widget goes back to the
  invite.
- **His lips on the still.** His voice carries on from the holder while the
  next page parses, so the still is his mouth strip (`src/mouth.ts`): four
  frames of his face in the widget's box, identical but for the mouth (closed,
  small, medium, open), served by the avatar host the build's runtime comes
  from (`build.mjs`: the dev host for `pnpm build`, the host the npm shim pins
  for `pnpm build:prod`). The holder measures his voice (`src/meter.ts`: an
  `AnalyserNode` on the bot's track, the RMS of the newest ~20 ms every 23 ms,
  at the avatar's loudness thresholds, `src/level.ts`) and sends the shape to
  every page when it changes, and every 200 ms while his mouth is open. The
  bridge passes it on from `document_start`, so the lips move before
  `content.js` has loaded; each shape is held at least 60 ms, the mouth closes
  150 ms after he goes quiet, and closes when no level has come for 300 ms.
  Nothing else moves: no transform, no animation, and the lips move with
  reduced motion too, since they are the conversation. The live face,
  lip-syncing from the catch-up, takes over through the 250 ms fade. The
  strip is loaded into the cache while a call is on, so the next page's still
  is the strip from its first paint; should it not load, the still is the last
  frame his face drew (else the character's still), and it holds, unmoving,
  until the live face draws.
- **The view transition.** In a call both pages opt in to a cross-document
  view transition (`@view-transition { navigation: auto }`, Chrome 126+): the
  page that leaves (`content.js`, while a call is on) and the page that arrives
  (`shell.js`, from what was kept). The widget's host has its own
  `view-transition-name` (`voqalize-javier`), so the page fades under it in
  150 ms while it stays where it is. The host is a see-through, fixed box over
  the viewport that takes no pointer events (the widget inside it does), so it
  is captured whole and in place. Older Chrome ignores the rule and loads the
  page as before, with the widget still up early. Off a call no transition is
  asked for. `www.saintgeorge.cl` redirects to `saintgeorge.cl`, so the first
  page after that redirect gets no early widget (`sessionStorage` is per
  origin); the call is unaffected.

## The microphone, once

The microphone is the extension's, not saintgeorge.cl's: Chrome keeps the
permission against `chrome-extension://<id>`, `chrome.contentSettings` cannot
set it for that origin, and an offscreen document cannot show a prompt. So, on
each press of the call button, the page asks the holder for the extension's
microphone permission state first:

- **granted**: the call starts.
- **prompt** (the first call): the widget shows the extension's own page
  `grant.html` in a frame (`<iframe allow="microphone">`), which asks at once.
  Chrome's prompt names the extension ("Javier for Saint George's College"
  wants to use your microphone); the visitor chooses *Allow*. The holder then
  reads the state again: granted, the call starts. Should it still not be
  granted (the grant was stored for the site rather than the extension, or it
  was *Allow this time*), `grant.html` opens once in a tab of its own, asks the
  same way, closes itself once answered, and the call starts.
- **denied**: the widget says Chrome blocks the microphone for the extension,
  with a button that opens `chrome://settings/content/microphone`, where the
  visitor takes the extension off the blocked list.

## What the visitor sees

The first time: the press, then Chrome's microphone prompt naming the
extension under the widget (and, only if that grant does not hold, a short-
lived tab with the same prompt), then Javier. After that, the press and
Javier. Pages load as they always do; the widget comes back on each new page
already live, his voice carries on across the load, and the moves he started
finish on the page they land on.

**His voice plays from the extension, not from the tab.** Muting the tab
(right-click → Mute site) does not silence him; the widget's *Silenciar* mutes
the visitor's microphone, and *Colgar* ends the call. Chrome shows the
microphone in use for the extension rather than for the tab.

## What is never done

There is no form on the site, and nothing is submitted, paid or logged into.
The contact card's button is a plain `mailto:` link the parent presses; their
own mail app opens the email and they send it. A RUT is never written anywhere.
Schoolnet, Pago Colegiatura and LIRMI are logins for families already at the
school: Javier opens them in a new tab only when asked, and the extension does
nothing there.

## Tests

```sh
pnpm test:e2e
cd ../.. && uv run --with playwright pytest tests/test_saintgeorge_page.py -q
```

`pnpm test:e2e` builds a test copy of the extension (`VOQALIZE_TEST_BUILD=1`,
into `test/.build/ext`: a stand-in call in the holder, a stand-in avatar, a
made-up API) and runs `test/holder.spec.ts` in headless Chromium with no
network: the port protocol, a full page load that leaves the call alone and a
move made on the next page, a link out in its own tab, the calendar read by
the service worker, the 15 s rule, the microphone's three branches, and the
widget across a load. The page test runs the site adapter against saved copies
of the site's pages.

His lips on the still are checked with a stand-in strip (four flat colours,
served by the tests' own avatar host; no picture of him is in this repo) and
his voice as a tone whose loudness swells four times a second, handed to the
holder as the bot's track: on a page whose parse is held 6 s, the still is the
strip, at least two open shapes show within a second while nothing has a
transform or an animation, and it closes within about 400 ms of his voice
stopping and stays closed; with the strip unavailable, the still is the last
frame of his face and his voice changes nothing that shows.
`test/level.spec.ts` checks the thresholds and the timing without a browser.
