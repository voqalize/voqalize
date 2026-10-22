# Javier for Santander Arena — the extension

A Chrome extension that puts Javier, a voice guide, on
[santanderarena.cl](https://www.santanderarena.cl), the Santiago concert arena's
site. He talks a visitor through the arena in Spanish or English while he moves
their screen: he opens the page that answers them and scrolls to the exact
section, rings a show's card, a bar or a date, opens an FAQ, and, when they want
to buy, opens the Puntoticket page for those tickets, that parking or that VIP
experience in a new tab. One call follows the visitor across every Santander
Arena tab they have open and every page they move to. Everything he shows is a
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
  instead; when the visitor talks over him, the rest is dropped.
- `src/hub.ts`, `src/bridge.ts`, `src/background.ts` — the hub. A
  `BroadcastChannel` and a Web Lock reach one origin, and the site answers on
  two (with and without `www.`), so the call's relay runs through the
  extension's service worker instead: every tab's messages reach every other
  Santander Arena tab, the call's claim is held by browser tab, so the call's
  tab takes it back after each page load, and the tabs Javier opens are opened
  by the worker, since his move arrives over the call and a page may not open a
  tab without a click. The worker opens Santander Arena and Puntoticket
  addresses only.
- `src/tabs.ts` — Qween's one-call-every-tab relay, on the hub: the tab the
  call started in holds it; every other tab follows with his face, the mute and
  the call's state.
- `src/widget.ts` — the corner widget, in a shadow root, in the site's own
  pink, dark and Inter: the call and the Español/English toggle, its words in
  the toggle's language. Off a call the toggle picks the language the next
  call starts in; in a call it asks the brain to switch, from any tab. Javier
  also switches by himself when the visitor speaks the other language, and the
  toggle follows him.
- `src/content.ts` — the call: stock pipecat with `@voqalize/client-transport`
  as its media manager, one `sessions.connect`, the avatar, and the routing of
  each Action to the tab it belongs on.
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
open www.santanderarena.cl. The first call asks for the microphone.
`pnpm build:prod` builds the same extension against production into
`dist-prod/`, from `.env.prod`.

The publishable key's allowed origins must include
`https://www.santanderarena.cl` and `https://santanderarena.cl`, which are where
the session is minted from. The agent id and key are baked into the bundle at
build time and are never committed: this repo is public.

The call opens in Spanish, as the site does. A visitor who presses English on
the toggle before the call starts gets the call in English, and keeps it
whatever they speak, until they ask for the other.

Santander Arena's pages send a `Permissions-Policy` that turns the microphone
off (`microphone=()`), which forbids it to the page and to this script with it:
a call connects, the agent speaks, and hears nothing. `rules.json` rewrites that
header on the site's pages to `microphone=(self)` and leaves the rest of their
policy as it was, which is why the extension asks for `declarativeNetRequest`
on those hosts. A real embed on their site needs the same change made in their
own header. If the microphone still cannot open, the widget says so and ends
the call rather than showing "live".

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
// A narrated turn: cues as the brain sends them, then speech as the voice plays it.
const n = __voqalizeSantander.narration;
n.speaking();
n.add({ at: "hay varios bares", word: 0, path: "/bares", heading: null, text: "Bares", faq: null });
n.hear("Hay varios bares dentro del arena.");
```

A move that could not be made comes back as the `command_failed` the brain
would receive, with the reason in words the model can act on: a heading that is
not on the page lists the ones that are.

A `navigate` to another page loads it, so the console's next line runs on a
page that no longer exists; the section it names is shown on the new page.

## One call, every tab, every page load

The call belongs to the tab it started in. Every other Santander Arena tab
shows Javier's face and the call's state and can mute or end it; the tab in
front is the one he sees and moves. A move to another page while the visitor
is in a different tab goes to the site tab in front, or the one last in front,
brought to the front, or a new one. Closing the call's tab ends the call
everywhere.

Every move to another page is a full page load, often in the middle of his
sentence. The page going away is not the end of the call: the next page in the
same tab rejoins the same session, and Voqalize holds the rest of his speech
until it is back and plays it then, so the visitor hears the sentence finish on
the page it was about. The cues he had not reached yet go with it: the page
saves them to `sessionStorage` as it unloads, and the next one takes them up if
it rejoins within thirty seconds, so the screen keeps following his voice.

## Buying is Puntoticket's

Tickets, parking and VIP experiences are sold on puntoticket.com. When the
visitor wants to buy, Javier opens that link in a new tab, in front; the
Santander Arena tab and the call stay where they are. The extension does not
run on Puntoticket and does nothing there: the purchase is the visitor's.
