# Javier para Colegio Everest — the extension

A Chrome extension that puts Javier, a voice guide, on
[colegioeverest.cl](https://www.colegioeverest.cl), the site of Colegio
Everest, a Catholic school of the Regnum Christi network in Lo Barnechea,
Santiago, from Mini Bambolino to IV Medio. He talks a family through the school
in Spanish or English while their screen follows his voice: he opens the page
that answers them, scrolls to the exact place and rings it, works out their
child's level for 2027 and shows its admission card, the vacancies and the
fees, moves the news carousel and the photo gallery, opens the online
application, the visit booking and the school's documents in a new tab, and
fills in the contact form as the visitor dictates it. The visitor presses
«Enviar» themselves. One call follows the visitor across every tab of the site
they have open and every page they move to, and his voice carries on through
each page load. Everything he shows is a page, place, slider, link or form the
site already has; the extension adds a corner widget and the ring he draws
around what he is pointing at.

This is how we show the agent to the school on its own site, before anything
goes on it; it is not how a customer would ship it.

## What is in it

- `src/colegioeverest-actions.ts` — the site adapter. It performs the brain's page
  Actions on the tab in front and reports every page the visitor lands on,
  whoever took them there: the places of the catalogue it shows, and whether
  it has the contact form. The site has no client router, so a move to
  another page is a full page load; the adapter keeps what is left of the move
  (the place, a slide, or a whole form fill) in `sessionStorage` and makes it
  once the next page is up. It moves the home page's news carousel and the
  Infraestructura gallery by clicking slick's own arrows. It also follows the
  visitor in the contact form: their typing, and Contact Form 7's answer when
  they press «Enviar» (its `wpcf7mailsent`, `wpcf7invalid`, `wpcf7spam` and
  `wpcf7mailfailed` events). The complaints and jobs forms are never touched.
- The catalogue of places, `../backend/knowledge/L3/anchors.json`, bundled in:
  every place a move targets, by key, with GenerateBlocks' `.gb-container-<hash>`
  selector (or its position in the page's content where a page has no blocks),
  each checked on the live site by `../backend/knowledge/build.py`. A hash is
  reused across pages, so a key is only looked up on its own page; the
  header's menus and the footer's address and map are on every page. The brain
  sends keys (`fecha_prekinder`, `vacantes`, `pie_mapa`); words are looked for
  only when the brain sends words (a line of a news post).
- `src/anchors.ts`, `src/anchor.ts` — what the adapter matches by its words
  (the headings and GenerateBlocks' headlines) is kept out of Chrome's
  translator from `document_start`, so a visitor reading the site in English
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
- `src/bridge.ts`, `src/hub.ts` — the page's port to the holder and its
  requests of the service worker.
- `src/background.ts` — the service worker: makes the holder, opens and
  focuses tabs for his moves (only the site and the hosts its pages send a
  family to: Alexia, Microsoft Bookings, the payment and families' portals),
  opens the microphone grant tab, keeps the language choice.
- `src/grant.ts`, `src/grant.html` — the extension's one-time microphone
  grant (below).
- `src/widget.ts` — the corner widget, in a shadow root, in the school's navy
  and amber: the call and the Español/English toggle, its words in the
  toggle's language. Javier also switches by himself when the visitor speaks
  the other language, and the toggle follows him. It sits bottom-right (the
  site has nothing fixed on the page) and moves out of the way of the contact
  form while he fills it. It also holds the grant frame and the "microphone
  blocked" message.
- `src/shell.ts`, `src/persist.ts` — the early shell, what a page in a call
  leaves for the next one, and the view transition (below).
- `src/content.ts` — the page: the widget, his face, the adapter, the moves
  the holder sends, and on the call button the microphone check and
  `sessions.connect` (`surface: "colegioeverest-ext"`).
- `src/actions.gen.ts` — the Action and event unions, generated from the brain
  with `pnpm gen`. Regenerate after changing either.
- `test/entry.ts` — the bundle `demos/tests/test_colegioeverest_page.py` runs in
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
open www.colegioeverest.cl. The first call asks for the extension's microphone
(below). `pnpm build:prod` builds the same extension against production into
`dist-prod/`, from `.env.prod`.

The publishable key's allowed origins must include
`https://www.colegioeverest.cl` and `https://colegioeverest.cl`, which are
where the session is minted from: the
page mints it, not the extension. The agent id and key are baked into the
bundle at build time and are never committed: this repo is public.

The call opens in Spanish, as the site does. A visitor who presses English on
the toggle before the call starts gets the call in English, and keeps it
whatever they speak, until they ask for the other.

The site sends no `Content-Security-Policy` and no `Permissions-Policy`
(checked on every page, 2026-10-27), so the grant frame's `allow="microphone"`
needs no header rule. If the microphone cannot open, the widget says so and
ends the call rather than showing "live".

**The extension id is fixed.** `manifest.json` carries a `key` (an RSA public
key; it is not a secret), so the unpacked extension has the same id from any
folder and on any machine, and the microphone grant made once holds across
rebuilds and moves. The private key is not in the repo and is not needed to
load unpacked (only to pack a `.crx`). `dist/` and `dist-prod/` share the id:
load one of them at a time.

The build works with no agent id or key. With an empty `.env` it warns, and
the extension loads with everything but the call: the widget and every page
Action still work from the console (below).

## Driving it from the console

With the extension loaded, every page Action can be sent exactly as the brain
would send it, from the page's DevTools console, with no call:

```js
// On the admission page: the Prekínder card, rung.
await __voqalizeColegioEverest.perform("show_section", { anchor: "fecha_prekinder", text: null });
// The vacancies, from any page: the admission page loads first.
await __voqalizeColegioEverest.perform("navigate", { path: "/bienvenidos-al-proceso-de-admision-del-colegio-everest/", anchor: "vacantes", text: null });
// The photo gallery, a step on (from any page: it goes there first).
await __voqalizeColegioEverest.perform("slide", { slider: "galeria", direction: "next" });
// The contact form, filled; nothing is sent: the visitor presses Enviar.
await __voqalizeColegioEverest.perform("fill_contact_form", {
  nombre: "Carolina", email: "caro@example.com", asunto: "Admisión 2027, Prekínder",
  mensaje: "Hola, nos interesa Prekínder 2027. Mi celular es +56 9 1234 5678.",
});
```

A move that could not be made comes back as the `command_failed` the brain
would receive, with the reason in words the model can act on: a place that is
not on the page lists the ones that are. A fill or a slide comes back as the
`command_done` the brain would receive, with what it did; what the form
reports goes to the brain as events once the call is on;
from the console, `window.voqalizeColegioEverest.start(console.log)` prints them.

## How the call lives through page loads

The site has no client router: every move to another page (the admission
page, the contact form, a cycle, a news post) loads a whole page, and slowly:
2 to 8 s, and some loads took 40 to 75 s (2026-10-27, from the US). The call therefore
does not live in a page: it lives in an **offscreen document of the
extension** (`call.html`, `src/holder.ts`, "the holder"), which no page load
touches.

- **The holder** runs stock pipecat on `@voqalize/client-transport`, plays his
  voice, keeps every open Colegio Everest tab (by browser tab id: its port, where it
  is, whether it is in front) and sends the brain `tabs_changed`, routes each
  brain Action to the tab it belongs on, fires his cues as he speaks
  (`src/narration.ts`) and relays to the pages what they need to draw his face
  (`src/relay.ts`: pipecat's events, the avatar's sync channel, which the
  holder opens and says hello on, and the mouth clock).
- **Where each Action goes.** A move on a page (a place) goes to the tab in
  front. A move that may open another page (a page, a slide, a form fill from
  a page without the form) goes to a site tab: the one in front, else the
  visitor's other site tab, brought to the front, else a new one, which makes
  the move once it is up. The application, the visit booking, a document or a
  portal opens in a tab of its own, through the service worker; the extension
  does nothing on that tab and it never joins the tab list.
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
  it after 30 s without sound), one at a time, and tells every Colegio Everest tab
  when it is up (`holder-up`): a port opened before the holder existed has no
  one at the other end, so pages open theirs on that word. It also opens and
  focuses tabs for his moves (an offscreen document has no `chrome.tabs`) and
  keeps the language choice.
- **The session is minted by the page.** On the call button the page calls
  `sessions.connect` with the publishable key (its fetch carries the site's
  Origin, which the key allows; a `chrome-extension://` origin cannot be added
  to a publishable key) and hands the answer to the holder, which connects.
- **A move for a page that is loading waits for it.** When a page starts
  loading another document it tells the holder (`leaving`); a move sent to
  that tab meanwhile is kept and delivered when the next page says `hello`, for
  up to 75 s (the site is slow). A move that itself loads a page finishes there
  (the adapter's `sessionStorage` leftover, as before).
- **The call ends** on End (any tab), when the call drops, or when no Figurella
  page has been open for 15 s; the holder then closes. A tab Javier opened off the site
  does not count: if the visitor closes every Colegio Everest tab, the call ends 15 s
  later. Reloading or updating the extension ends it too.

## The widget across a page load

The call outlives a page load, and in a call the widget does too, as near as a
page can: it is back the moment the next page shows, not once the page has
parsed and the site's scripts have run.

- **What the page leaves.** While a call is on, `content.js` keeps a picture of
  it in the tab's `sessionStorage` (`src/persist.ts`): live or connecting,
  muted or not, the status line, the language, where the visitor put the widget
  and whether it is minimised, and the character's still for the invite. No
  picture of his face is kept. It is taken away when the call ends, and is
  stale after 60 s.
- **The early shell.** `shell.js` (`src/shell.ts`) runs in the page's world at
  `document_start`, before any of the page's scripts. Off a call it reads that
  one key and does nothing else. In a call it mounts the widget on `<html>` at
  once, as the last page left it: the card, the status line and its buttons,
  so the visitor can always mute or end the call. Where his face goes there is
  nothing, no picture of him, while the page loads: his face returns when the
  live face has drawn, and his voice never stops. `content.js` (still at
  `document_idle`) adopts that widget instead of mounting another, asks the
  holder for the call's state as before, starts building his face at once
  (`preloadAvatar`), and fades the live face in once it has drawn, already
  moving with the reply he is in the middle of (the catch-up). A frozen or
  made-up face in the meantime was tried and dropped: an empty slot for a
  second reads better than a face that does not match his voice. Should the
  holder be gone (no holder, or no word from it in 8 s), the carried widget
  goes back to the invite.
- **The view transition.** In a call both pages opt in to a cross-document
  view transition (`@view-transition { navigation: auto }`, Chrome 126+): the
  page that leaves (`content.js`, while a call is on) and the page that arrives
  (`shell.js`, from what was kept). The widget's host has its own
  `view-transition-name` (`voqalize-javier`), so the page fades under it in
  150 ms while it stays where it is. Older Chrome ignores the rule and loads
  the page as before, with the widget still up early. Off a call no transition
  is asked for. `colegioeverest.cl` redirects to `www.colegioeverest.cl`, so
  the first page after that redirect gets no early widget (`sessionStorage` is
  per origin); the call is unaffected.

## The microphone, once

The microphone is the extension's, not colegioeverest.cl's: Chrome keeps the
permission against `chrome-extension://<id>`, `chrome.contentSettings` cannot
set it for that origin, and an offscreen document cannot show a prompt. So, on
each press of the call button, the page asks the holder for the extension's
microphone permission state first:

- **granted**: the call starts.
- **prompt** (the first call): the widget shows the extension's own page
  `grant.html` in a frame (`<iframe allow="microphone">`), which asks at once.
  Chrome's prompt names the extension ("Javier para Colegio Everest" wants to use your
  microphone); the visitor chooses *Allow*. The holder then reads the state
  again: granted, the call starts. Should it still not be granted (the grant
  was stored for the site rather than the extension, or it was *Allow this
  time*), `grant.html` opens once in a tab of its own, asks the same way,
  closes itself once answered, and the call starts.
- **denied**: the widget says Chrome blocks the microphone for the extension,
  with a button that opens `chrome://settings/content/microphone`, where the
  visitor takes the extension off the blocked list.

## What the visitor sees

The first time: the press, then Chrome's microphone prompt naming the
extension under the widget (and, only if that grant does not hold, a short-
lived tab with the same prompt), then Javier. After that, the press and
Javier. Pages load
as they always do; the widget comes back on each new page already live, his
voice carries on across the load, and the moves he started finish on the page
they land on.

**His voice plays from the extension, not from the tab.** Muting the tab
(right-click → Mute site) does not silence him; the widget's *Silenciar* mutes
the visitor's microphone, and *Colgar* ends the call. Chrome shows the
microphone in use for the extension rather than for the tab.

## What is never done

**The visitor presses «Enviar».** Javier fills the contact form (name, email,
a subject, and a short message he writes from the conversation, with the
visitor's phone in it, since the form has no phone field), field by field, as
the site's own fields take them. Nothing here can send a form: there is no
`submit()`, no `requestSubmit()` and no click on a form's button anywhere in
the source (`demos/tests/test_colegioeverest_page.py` checks), and no Action
that could ask for one. The Cloudflare check above «Enviar» is never touched:
it is the visitor's. Once every field is in, the button is rung for them to
press. The complaints form (Ambientes Seguros), the jobs form and the admission
results lookup are never filled. A RUT or RUN, a password and payment details
are never asked for or typed.

**The application and the visit only open.** «Postulación ONLINE» (Alexia) and
«Agenda AQUÍ» (Microsoft Bookings) leave the site and ask for the family's own
details: they open in a new tab, and the extension does nothing there.

## Tests

```sh
pnpm test:e2e
cd ../.. && uv run --with playwright pytest tests/test_colegioeverest_page.py -q
```

`pnpm test:e2e` builds a test copy of the extension (`VOQALIZE_TEST_BUILD=1`,
into `test/.build/ext`: a stand-in call in the holder, a stand-in avatar, a
made-up API) and runs `test/holder.spec.ts` in headless Chromium: the port
protocol, a full page load that leaves the call alone and a move made on the
next page, a form fill from a page without the form made on /contacto/ with
«Enviar» never pressed, the visit booking in its own tab, the 15 s rule, the
microphone's three branches, and the widget across a load. The page test runs
the site adapter against saved copies of the site's pages.
