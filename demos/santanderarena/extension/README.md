# Javier for Santander Arena — the extension

A Chrome extension that puts Javier, a voice guide, on
[santanderarena.cl](https://www.santanderarena.cl), the Santiago concert arena's
site. He talks a visitor through the arena in Spanish or English while he moves
their screen: he opens the page that answers them and scrolls to the exact
section, rings a show's card, a bar or a date, opens an FAQ, and, when they want
to buy, opens the Puntoticket page for those tickets, that parking or that VIP
experience in a new tab. One call follows the visitor across every Santander
Arena tab they have open, and through every full page load, without
reconnecting. Everything he shows is a
page, section, card or link the site already has; the extension adds a corner
widget and the ring he draws around what he is pointing at.

This is how we show the agent to Santander Arena on their own site, before
anything goes on it; it is not how a customer would ship it.

## What is in it

- `src/santander-actions.ts` — the site adapter. It performs the brain's page
  Actions on the tab in front and reports every page the visitor lands on,
  whoever took them there: its sections, cards, FAQs and ticket links. The site
  has no client router, so a move to another page is a full page load; the
  adapter keeps what is left of the move (the section, card or FAQ on that
  page) in `sessionStorage` and makes it once the next page is up.
- `src/narration.ts` — the screen follows his voice. The brain sends each
  screen cue he wrote into his reply ahead of the speech, with the first words
  of the sentence it belongs to; this fires it when the call's spoken-text
  events (`bot-output`, released as the audio plays) reach those words, one
  move at a time. Words are matched with their accents folded, as the brain
  folds them. With no spoken text, it times cues from the start of the speech
  instead; when the visitor talks over him, the rest is dropped. It runs in
  the holder, with the call.
- `src/holder.ts`, `src/call.html`, `src/call-client.ts`, `src/relay.ts` — the
  holder: the call, in an offscreen document of the extension (see "How the
  call lives through page loads").
- `src/content.ts`, `src/follow.ts` — each page's half: the widget, his face
  against a stand-in client fed by the holder, the site adapter, the moves the
  holder sends it; on the call button, the microphone check and
  `sessions.connect`.
- `src/shell.ts`, `src/persist.ts` — in a call, the widget back at once on the
  next page, and the page load as a view transition under it.
- `src/bridge.ts`, `src/hub.ts`, `src/protocol.ts` — the page's port to the
  holder and its requests of the service worker, and what they say.
- `src/background.ts` — the service worker: makes the holder, opens and
  focuses tabs (Santander Arena, Puntoticket and reservas.movistararena.cl
  addresses only), opens the microphone grant tab, keeps the language choice.
- `src/grant.ts`, `src/grant.html` — the extension's one-time microphone grant.
- `src/widget.ts` — the corner widget, in a shadow root, in the site's own
  pink, dark and Inter: the call and the Español/English toggle, its words in
  the toggle's language. Off a call the toggle picks the language the next
  call starts in; in a call it asks the brain to switch, from any tab. Javier
  also switches by himself when the visitor speaks the other language, and the
  toggle follows him.
- `src/actions.gen.ts` — the Action and event unions, generated from the brain
  with `pnpm gen`. Regenerate after changing either.

The brain is `../backend/`: the prompt, the tools, and Santander Arena's
knowledge.

## Build and load

```sh
cp .env.example .env     # the agent id and a publishable key (see below)
pnpm install --ignore-workspace
pnpm build               # → dist/
```

Then `chrome://extensions` → Developer mode → **Load unpacked** → `dist/`, and
open www.santanderarena.cl. The first call asks for the microphone (see "The
microphone, once"). `pnpm build:prod` builds the same extension against
production into `dist-prod/`, from `.env.prod`.

**The extension id is fixed.** `manifest.json` carries a `key` (an RSA public
key; it is not a secret), so the unpacked extension has the same id from any
folder and on any machine, and the microphone grant made once holds across
rebuilds and moves. The private key is not in the repo and is not needed to
load unpacked (only to pack a `.crx`). `dist/` and `dist-prod/` share the id:
load one of them at a time. Anyone who loaded an earlier build (whose id came
from its folder) reloads it once.

The publishable key's allowed origins must include
`https://www.santanderarena.cl` and `https://santanderarena.cl`, which are where
the session is minted from. The agent id and key are baked into the bundle at
build time and are never committed: this repo is public.

The call opens in Spanish, as the site does. A visitor who presses English on
the toggle before the call starts gets the call in English, and keeps it
whatever they speak, until they ask for the other.

Santander Arena's pages send a `Permissions-Policy` that turns the microphone
off (`microphone=()`). The pages no longer open the microphone (the holder
does, as the extension), but the extension's grant page asks for it in a frame
on the site's page, and a frame may not use what its page's policy forbids.
`rules.json` rewrites that header on the site's pages to
`microphone=(self "chrome-extension://<this extension's id>")`, which lets the
grant frame ask, and leaves the rest of their policy as it was; that is why
the extension asks for `declarativeNetRequest` on those hosts. Without the
rule, or with the earlier `microphone=(self)`, the frame's `getUserMedia` is
refused by the policy and only the grant tab could ask.

The build works without them. With an empty `.env` it warns, and the extension
loads with everything but the call: the widget and every page Action still work
from the console (below).

## Driving it from the console

With the extension loaded, every page Action can be sent exactly as the brain
would send it, from the page's DevTools console, with no call:

```js
await __voqalizeSantander.perform("navigate", { path: "/bares", heading: null, text: "Bares", faq: null });
// On the home page:
await __voqalizeSantander.perform("show_section", { heading: "Completa tu noche en Santander Arena", text: null });
await __voqalizeSantander.perform("show_section", { heading: null, text: "DEF LEPPARD" });
// On /preguntas-frecuentes:
await __voqalizeSantander.perform("open_faq", { question: "¿Los niños deben pagar entrada?" });
```

A move that could not be made comes back as the `command_failed` the brain
would receive, with the reason in words the model can act on: a heading that is
not on the page lists the ones that are.

A `navigate` to another page loads it, so the console's next line runs on a
page that no longer exists; the section it names is shown on the new page.

## How the call lives through page loads

The site has no client router: every move to another page (a show, the bars,
the FAQ) is a full page load, often in the middle of his sentence. The call
therefore does not live in a page: it lives in an **offscreen document of the
extension** (`call.html`, `src/holder.ts`, "the holder"), which no page load
touches.

- **The holder** runs stock pipecat on `@voqalize/client-transport`, plays his
  voice, keeps every open Santander Arena tab (by browser tab id: its port,
  where it is, whether it is in front) and sends the brain `tabs_changed`,
  routes each brain Action to the tab it belongs on, fires his cues as he
  speaks (`src/narration.ts`) and relays to the pages what they need to draw
  his face (`src/relay.ts`: pipecat's events, the avatar's sync channel, which
  the holder opens and says hello on, and the mouth clock).
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
  it after 30 s without sound), one at a time, and tells every Santander Arena
  tab when it is up (`holder-up`): a port opened before the holder existed has
  no one at the other end, so pages open theirs on that word. It also opens and
  focuses tabs for his moves (an offscreen document has no `chrome.tabs`) and
  keeps the language choice.
- **The session is minted by the page.** On the call button the page calls
  `sessions.connect` with the publishable key (its fetch carries
  santanderarena.cl's Origin, which the key allows; a `chrome-extension://`
  origin cannot be added to a publishable key) and hands the answer to the
  holder, which connects.
- **Where each Action goes.** A move on a page (a section, a card, an FAQ)
  goes to the tab in front. A move to another page goes to a site tab: the
  one in front, else the one last in front, brought to the front, else a new
  one, which makes the move once it is up. A ticket, parking or VIP link
  opens Puntoticket (or reservas.movistararena.cl) in a tab of its own.
- **A move for a page that is loading waits for it.** When a page starts
  loading another document it tells the holder (`leaving`); a move sent to
  that tab meanwhile is kept and delivered when the next page says `hello`. A
  `navigate` that itself loads a page finishes there (the adapter's
  `sessionStorage` leftover, as before), and a leftover that could not be made
  is reported once the next page reports to the brain.
- **The call ends** on End (any tab), when the call drops, or when no Santander
  Arena page has been open for 15 s; the holder then closes. Reloading or
  updating the extension ends it too. Puntoticket and reservas.movistararena.cl
  tabs have no content script, so they do not count: a visitor who closes
  every Santander Arena tab and keeps only Puntoticket open loses the call 15 s
  later.

## The widget across a page load

The call outlives a page load, and in a call the widget does too, as near as a
page can: it is back the moment the next page shows, not once the page has
loaded and the content script has run.

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
  150 ms while it stays where it is. The host is a see-through, fixed box over
  the viewport that takes no pointer events (the widget inside it does), so it
  is captured whole and in place. Older Chrome ignores the rule and loads the
  page as before, with the widget still up early. Off a call no transition is
  asked for. `sessionStorage` and view transitions are per origin, so a load
  between `www.santanderarena.cl` and `santanderarena.cl` brings the widget
  back at `document_idle` instead; the call is unaffected.

## The microphone, once

The microphone is the extension's, not santanderarena.cl's: Chrome keeps the
permission against `chrome-extension://<id>`, and an offscreen document cannot
show a prompt. So, on each press of the call button, the page asks the holder
for the extension's microphone permission state first:

- **granted**: the call starts.
- **prompt** (the first call): the widget shows the extension's own page
  `grant.html` in a frame (`<iframe allow="microphone">`), which asks at once.
  Chrome's prompt names the extension; the visitor chooses *Allow*. The holder
  then reads the state again: granted, the call starts. Should it still not be
  granted (the grant was stored for the site rather than the extension, or it
  was *Allow this time*), `grant.html` opens once in a tab of its own, asks the
  same way, closes itself once answered, and the call starts.
- **denied**: the widget says Chrome blocks the microphone for the extension,
  with a button that opens `chrome://settings/content/microphone`, where the
  visitor takes "Javier for Santander Arena" off the blocked list.

**His voice plays from the extension, not from the tab.** Muting the tab does
not silence him; the widget's *Silenciar* mutes the visitor's microphone, and
*Colgar* ends the call. Chrome shows the microphone in use for the extension
rather than for the tab.

## Tests

```sh
pnpm test:e2e
```

Playwright, headless, no network. `test/holder.spec.ts` loads the built
extension (`VOQALIZE_TEST_BUILD=1` builds it into `test/.build/ext` with a
stand-in call, `test/fake-call-client.ts`, a stand-in avatar and a made-up API)
on pages served at santanderarena.cl's address, and checks the port protocol
(the press, the session minted with the page's Origin and handed over, the
state on the page, its events reaching the brain, mute and End), a move sent
while the tab loads made on its next page's hello, a ticket link opened in a
tab of its own that never joins the tab list, the 15 s rule, the widget across
a page load, and the microphone's branches with the permission query stubbed.

## Buying is Puntoticket's

Tickets, parking and VIP experiences are sold on puntoticket.com. When the
visitor wants to buy, Javier opens that link in a new tab, in front; the
Santander Arena tab and the call stay where they are (see "The call ends"
above for what happens if every Santander Arena tab is then closed). The extension does not
run on Puntoticket and does nothing there: the purchase is the visitor's.
