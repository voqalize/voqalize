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
- `src/hub.ts`, `src/bridge.ts`, `src/background.ts` — the hub. A
  `BroadcastChannel` and a Web Lock reach one origin, and Explora is two, so
  the call's relay runs through the extension's service worker instead: every
  tab's messages reach every other Explora tab, the call's claim is held by
  browser tab, and the worker keeps each tab's move for its next page and its
  saved call (below).
- `src/tabs.ts` — Qween's one-call-every-tab relay, on the hub: the tab the
  call started in holds it; every other tab follows with his face, the mute and
  the call's state.
- `src/widget.ts` — the corner widget, in a shadow root, dressed in Explora's
  black, white and sand: the call, and the English/Español toggle. Off a call
  the toggle picks the language the next call starts in; in a call it asks the
  brain to switch, from any tab. Javier also switches by himself when the
  visitor speaks the other language, and the toggle follows him. The page's
  own TalkCenter chat launcher stands aside while the extension runs.
- `src/content.ts` — the call: stock pipecat with `@voqalize/client-transport`
  as its media manager, one `sessions.connect`, the avatar, and the routing of
  each Action to the tab in front.
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
open www.explora.com. The first call asks for the microphone. `pnpm build:prod`
builds the same extension against production into `dist-prod/`, from
`.env.prod`.

The publishable key's allowed origins must include `https://www.explora.com`,
`https://explora.com` and `https://reservations.explora.com`: a call can start
on any of them, and rejoins on each after a load. The agent id and key are
baked into the bundle at build time and are never committed: this repo is
public.

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
// A narrated turn: cues as the brain sends them, then speech as the voice plays it.
const n = __voqalizeExplora.narration;
n.speaking();
n.add({ at: "everything is included", word: 0, heading: "Included with Your Stay", text: null, faq: null });
n.add({ at: "at night you", word: 4, heading: "Stargaze from Explora’s Observatory", text: null, faq: null });
n.hear("Everything is included.");
n.hear("At night you can stargaze from our own observatory.");
```

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
booking site, loads a new page. The call survives it, and the design follows
from what that costs.

- **Ten seconds.** `@voqalize/client-transport` (`keepAcrossPageLoads`) saves
  the call in the page's `sessionStorage`, and Voqalize holds the session for
  ten seconds while the next page dials it again. So the script mounts at
  `document_idle` and dials at once, without waiting for `load`, which
  WordPress's trackers hold back for seconds.
- **Paced page cues.** A tool call moves the page once the model has written
  the whole reply, which the voice then takes many seconds to say. So the
  model writes `{page: …}` into its reply where the page should go, and the
  brain takes it out and sends `navigate` with `after_words`, the words of his
  that come before it. Those words have been sent but may not be playing yet,
  and a page load cuts the audio off, so the page waits: for his voice to
  start (up to four seconds), then to stop and stay quiet for 300 ms, within
  `after_words / 2.8` seconds plus six. With `after_words` 0 it only waits for
  him to be quiet, up to three seconds. The brain says nothing more until the
  new page reports `page_changed`, which it does once the call is back up on
  it; then his `{show: …}` cues for that page follow.
- **The move for the next page.** A move that needs the next page (a heading
  on it, the booking step after a load) is kept by the hub for this browser
  tab (`loadThen`) and made once the call has rejoined there, or 800 ms after
  the page mounts when there is no call.
- **Across hosts.** `sessionStorage` is per origin, and www.explora.com and
  reservations.explora.com are two. While a tab holds a call it stashes the
  transport's saved call with the hub, right after it connects and again on
  `pagehide`; a page on the other host takes it back before it asks the
  transport whether there is a call to rejoin. The stash belongs to the
  browser tab, so it never reaches another tab; ending the call forgets it.
- **Links stay in the tab.** While a call is live, links to either Explora host
  lose `target="_blank"`, so the visitor's own clicks load in the tab that
  holds the call rather than in a new one without it.

## The site follows the call's language

www.explora.com is WordPress with WPML: Spanish lives at `/es/…` under
translated slugs (`/lodge/atacama-lodge/` ↔
`/es/lodge/hotel-en-san-pedro-de-atacama/`), and every page names its
translations in its `<head>` (`<link rel="alternate" hreflang="es">`).

- **When the language moves** (the brain's `language_changed`: the visitor
  spoke Spanish, asked, or pressed the toggle), the page in front waits for
  Javier to finish confirming it aloud (up to 8 s) and loads its twin: the
  `hreflang` link, else the language selector's link, else `/es/` or `/`. A
  `navigate` that arrives meanwhile wins. A page in Portuguese, French or
  German is left alone. On the booking site the step is loaded again with
  `?language=ES|EN` swapped in, only where that loses nothing: paso1 (with the
  lodge and day carried in the URL), paso2 when its URL carries the stay, and
  the expedition enquiry while nothing is filled in. Never paso3.
- **`navigate` names the English page**, because the brain knows the English
  site. While the call is in Spanish, the English page's `<head>` is fetched
  (same-origin, read only up to `</head>`; through the hub from the booking
  site) and its Spanish twin is loaded, or the English page when it has none.
  The lookup starts as the `navigate` arrives and runs while his voice is
  still playing; it takes 60–150 ms when Explora's CDN has the page and about
  a second when it does not, and each answer is kept in the tab's
  `sessionStorage`. The page's own links answer for its translations at no
  cost.
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
  `site: "stay"`), in the page's `sessionStorage` and with the hub for the
  browser tab, so a page on either host rejoins in it. An English page that
  comes up in a Spanish call does not make the call English.
- **The lookup never holds a load.** A `navigate` waits at most two seconds
  for the twin, then loads the English page as named. The lookup reads the
  page's head from the page, then from the hub (the extension's service
  worker, which no script of the page can wrap) when that fails; a page that
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
  load began) is reported as `command_failed`.

From the console, with no call:

```js
await __voqalizeExplora.setLanguage("es");   // as language_changed; the page loads in Spanish
__voqalizeExplora.language();                // "es"
await __voqalizeExplora.mapPath("/lodge/atacama-lodge/");  // {url, source, ms}
await __voqalizeExplora.perform("navigate", { path: "/lodge/atacama-lodge/", after_words: 0, heading: null, text: null, faq: null });
```

## One call, every tab

The call belongs to the tab it started in. Every other Explora tab, on either
host, shows Javier's face and the call's state and can mute or end it; the tab
in front is the one he sees and moves. Closing the call's tab ends the call
everywhere. The usual case is one tab that loads between the two hosts.

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
