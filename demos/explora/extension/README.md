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

The extension is built on Stage (`@voqalize/stage`, linked from
`../../../sdk/js/stage`). Its `./extension` host does everything every site
extension shares: the holder (the call, in an offscreen document, across every
page load on both hosts), the timeline that fires his cues as his voice
reaches them, the relay that draws his face on every page, the bridge, the
early shell, the widget, the grant and the service worker. What is here is
Explora's own:

- `src/site.ts` — who Explora is: its hosts, the moves Javier makes (by id,
  with their arguments), where a booking move starts, and the widget dressed
  in Explora's black, white and sand.
- `src/explora-actions.ts` — the www.explora.com adapter. It registers his
  moves with Stage's `Moves`: `core.show` (a heading, a tab or accordion by
  its label, or words to ring), `core.faq` (a question's accordion),
  `explora.navigate` (a page), `explora.twin` (this page in the call's
  language) and `explora.arrive` (the half of a move that finishes on the page
  it loaded). It reports the page (`page_changed`): its headings, its
  questions, its tabs and accordions, and its own sub-menu, read with the
  crawler's rules (`../backend/knowledge/L3/build_main.py`), so the names the
  brain knows from the crawl are the names the page finds. What is asked for
  inside a closed pane, a collapsed accordion or a carousel slide out of view
  is brought out first, the way a visitor would.
- `src/reservations-actions.ts` — the reservations.explora.com adapter:
  `explora.check_availability`, `explora.choose_room`,
  `explora.fill_enquiry`, `explora.send_enquiry` (below).
- `src/dom.ts` — what both adapters share: scrolling the window under
  Explora's fixed header and sticky sub-menu, matching a name against what the
  page shows, and setting a form field the way the site's own scripts notice.
- `src/site-language.ts`, `src/hreflang.ts` — the site follows the call's
  language (below).
- `src/content.ts` — the page: the shared page host with Explora's adapters,
  its spotlight colour, his face and the session's `init`
  (`surface: "explora-ext"`).
- `src/holder.ts`, `src/call.html`, `src/call-client.ts` — the holder with
  Explora's pacing of a page load against his voice and the site following the
  call's language; `call-client.ts` makes the pipecat client.
- `src/background.ts`, `src/shell.ts`, `src/bridge.ts`, `src/grant.ts` and
  `src/grant.html` — the shared service worker (plus reading a
  www.explora.com page's translations for the booking site), early shell,
  bridge and microphone grant, each started with Explora's config.
- `src/actions.gen.ts` — the brain's one site Action (`language_changed`) and
  Explora's events, generated from the brain with `pnpm gen`. Regenerate after
  changing either.

The brain is `../backend/`: the prompt, the tools, and Explora's knowledge.

## Every move is rung and answered

Every move Javier makes, a cue in his reply or a tool's, rings what it points
at with Stage's spotlight (a terracotta ring drawn over the page, never on
Explora's own elements) before it acts: the heading he is about to describe,
the tab before it opens, the calendar before a day is picked, the nights
before they are set, the room before it is chosen, the form's rows before
they are filled, Send Message before it is pressed. A ring that the next one
replaces at once stays 0.7 s; one that ends a move stays 1.5 s, and is up for
5.5 s unless another replaces it. Each move then answers with one
`stage_result`: `applied` with what it did, `refused` with the name the page
did not have and what it offers instead, `failed` with why. A move that goes
on to another page answers from the page it lands on.

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
rebuilds and moves. `dist/` and `dist-prod/` share the id: load one of them at
a time.

The build works without them. With an empty `.env` it warns, and the extension
loads with everything but the call: the widget and every move still work from
the console (below).

## Driving it from the console

With the extension loaded, every move can be made exactly as Stage makes it,
from the page's DevTools console, with no call; each resolves to its
`stage_result`:

```js
// On https://www.explora.com/lodge/atacama-lodge/
await __voqalizeExplora.move("core.show", ["Stargaze from Explora’s Observatory"]);
// On the home page: a destination of the map's accordion, by its label.
await __voqalizeExplora.move("core.show", ["Sacred Valley of the Incas [Peru]"]);
// On https://www.explora.com/atacama-travel-tips/
await __voqalizeExplora.move("core.faq", ["How many days should I spend in the Atacama Desert?"]);
// A page; the move finishes on the page it loads.
await __voqalizeExplora.move("explora.navigate", { path: "/atacama-desert-explora-lodge/", after_words: 0 });
// As if the call had moved to Spanish: the page loads its Spanish twin.
await __voqalizeExplora.command("site_language", { language: "es" });
__voqalizeExplora.moves();   // the moves this page makes
```

A move that belongs on the other host loads it, with the move kept for it
(`explora.check_availability` from www.explora.com opens the lodge's page on
the booking site). A name the page does not have is refused with what it
shows instead: a heading lists the first twenty labels showing; a question
lists the page's questions.

What the page reports is what shows at the window's width. Explora often
renders a block twice, a desktop row and a mobile accordion with one of them
`display: none`; a heading, tab or question inside the copy the layout hides
is never reported or used, while one inside a closed tab, accordion or
carousel slide is, and is opened first.

## Every page is a full page load

Neither host routes client-side: every link loads a new page, and a booking
step loads the other host in the same tab.

- **Paced page cues.** The model writes `{page: …}` into its reply where the
  page should go; the brain takes it out and sends `explora.navigate` with
  `after_words`, the words of his that come before it. The holder waits before
  it sends the move to the page: for his voice to start (up to four seconds),
  then to stop and stay quiet for 300 ms, within `after_words / 2.8` seconds
  plus six. A booking move from www.explora.com, which loads the booking site,
  waits for him to be quiet the same way. The brain says nothing more until
  the new page reports `page_changed`; then his `{show: …}` cues for that page
  follow, fired as his voice reaches their words.
- **The rest of a move, on the next page.** A move that needs the next page is
  kept by the service worker for this browser tab (the next page may be the
  other origin) and made once the call is up there, with the same
  `call_ref`, which answers for it.
- **A move that never takes the page away** (eight seconds after its load
  began) is answered `failed`: the screen has not moved.
- **Links stay in the tab.** While a call is live, links to either Explora
  host lose `target="_blank"`, so the visitor's clicks load in the tab Javier
  is moving.

## The call, the widget and the microphone

The call lives in the holder, not in a page: a load on either host, or between
them, changes nothing on it; his voice plays from the extension and never
stops; every page shows his face and the call's state and can mute or end it;
the tab in front is the one he moves; with no Explora page open for 15 s the
call ends. In a call the widget is back the moment the next page on the same
host shows, as the last page left it, with the load as a view transition
under it (across hosts it comes back once the page has parsed). The
microphone is the extension's: the first call asks for it in a frame of the
extension's own `grant.html` (and, only if that grant does not hold, in a
short-lived tab), and a blocked microphone gets a button to Chrome's setting.
All of this is the shared host's; `@voqalize/stage/extension` documents it.

## The site follows the call's language

www.explora.com is WordPress with WPML: Spanish lives at `/es/…` under
translated slugs, and every page names its translations in its `<head>`
(`<link rel="alternate" hreflang="es">`).

- **When the language moves** (the brain's `language_changed`: the visitor
  spoke Spanish, asked, or pressed the toggle), the page in front waits for
  Javier to finish confirming it aloud (up to 3 s) and loads its twin. A
  `navigate` that arrives meanwhile wins. On the booking site the step is
  loaded again with `?language=ES|EN`, only where that loses nothing.
- **`explora.navigate` names the English page**, because the brain knows the
  English site. While the call is in Spanish the page's Spanish twin is
  loaded, read off the English page's `<head>` (through the service worker
  from the booking site), within two seconds, else the English page. Every
  lookup is reported to the brain as `twin_lookup`.
- **A page that came up in the wrong language** is loaded again as its own
  twin when the brain asks (`explora.twin`, once his voice is quiet): never
  that language's home page. A page with no twin refuses the move.
- **At the start**, `init.site_lang` tells the brain the language the site is
  followed in; `init.lang` is sent only when the visitor chose on the toggle.
  The call's language is then the holder's, on every page of both hosts.

## The booking site

On reservations.explora.com Javier works the booking engine with the visitor
(`src/reservations-actions.ts`):

- `explora.check_availability` picks the lodge, turns the calendar to a month,
  picks a day and the nights, and goes on to the rooms and rates. A day the
  calendar does not open, or nights it does not offer, are refused with the
  ones it does.
- `explora.choose_room`, on the rooms and rates, sets a room's travellers and
  bed type and presses that room's own "Add this room", which opens its
  summary. He rings its check-out button for the visitor and never presses it:
  he never books. With no bed type he rings the room's bed select and asks.
  More rooms go through the popup's own "Add more rooms".
- `explora.fill_enquiry` opens an expedition's enquiry form and fills in what
  the visitor told him. `explora.send_enquiry` sends the visitor's own
  details, so it is a confirmed move: the brain sends it only once the visitor
  has ticked the reCAPTCHA themselves, and the page presses Send Message only
  when every field is valid.

## Tests

```sh
pnpm test:e2e
```

Playwright, headless, no network: `test/holder.spec.ts` loads the built
extension (`VOQALIZE_TEST_BUILD=1`, into `test/.build/ext`) with a stand-in
call in the holder (`test/fake-call-client.ts`), a stand-in avatar
(`test/fake-avatar.ts`) and a made-up API, against small pages served at
www.explora.com's and reservations.explora.com's addresses. It covers the
port protocol, a cue fired while the tab loads and made, ringed and answered
on the next page, a move carried across hosts and answered from the page it
lands on, a page's twin, the 15 s rule, the microphone's branches, and the
widget across a load. `test/catch-up.spec.ts` and `test/mouth-clock.spec.ts`
cover the shared host's catch-up and mouth clock. The brain's own tests are
`demos/tests/test_explora_*.py`.
