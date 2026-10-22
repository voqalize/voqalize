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
open and every page they move to. Everything he shows is a page, section,
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
  events reach those words, one move at a time.
- `src/hub.ts`, `src/bridge.ts`, `src/background.ts` — the hub: the call's
  relay across tabs, the call's claim held by browser tab so the call's tab
  takes it back after each page load, new tabs opened for his moves (only on
  hosts the site itself links), and the calendar read.
- `src/tabs.ts` — Qween's one-call-every-tab relay, on the hub.
- `src/widget.ts` — the corner widget, in a shadow root, in the school's blue
  and yellow: the call and the Español/English toggle, its words in the
  toggle's language. Javier also switches by himself when the visitor speaks
  the other language, and the toggle follows him.
- `src/content.ts` — the call: stock pipecat with `@voqalize/client-transport`
  as its media manager, one `sessions.connect`, the avatar, and the routing of
  each Action to the tab it belongs on.
- `src/actions.gen.ts` — the Action and event unions, generated from the brain
  with `pnpm gen`. Regenerate after changing either.
- `test/entry.ts` — the bundle `demos/tests/test_saintgeorge_page.py` runs in
  headless Chromium against saved copies of the site's pages
  (`../fixtures/`). Never shipped.

The brain is `../backend/`: the prompt, the tools, and the school's knowledge.

## Build and load

```sh
cp .env.example .env     # the agent id and a publishable key (see below)
pnpm install --ignore-workspace
pnpm build               # → dist/
```

Then `chrome://extensions` → Developer mode → **Load unpacked** → `dist/`, and
open saintgeorge.cl. The first call asks for the microphone. `pnpm build:prod`
builds the same extension against production into `dist-prod/`, from
`.env.prod`.

The publishable key's allowed origins must include `https://saintgeorge.cl`
and `https://www.saintgeorge.cl`, which are where the session is minted from.
The agent id and key are baked into the bundle at build time and are never
committed: this repo is public.

The call opens in Spanish, as the site does. A visitor who presses English on
the toggle before the call starts gets the call in English, and keeps it
whatever they speak, until they ask for the other.

The site sends no `Permissions-Policy`, so the microphone needs no header
rule. If the microphone cannot open, the widget says so and ends the call
rather than showing "live".

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

## One call, every tab, every page load

The call belongs to the tab it started in. Every other tab of the site shows
Javier's face and the call's state and can mute or end it; the tab in front is
the one he sees and moves. Closing the call's tab ends the call everywhere.

Every move to another page is a full page load, often in the middle of his
sentence. The next page in the same tab rejoins the same session, and Voqalize
holds the rest of his speech until it is back and plays it then. The cues he
had not reached yet go with it, in `sessionStorage`, if the next page rejoins
within thirty seconds.

## What is never done

There is no form on the site, and nothing is submitted, paid or logged into.
The contact card's button is a plain `mailto:` link the parent presses; their
own mail app opens the email and they send it. A RUT is never written anywhere.
Schoolnet, Pago Colegiatura and LIRMI are logins for families already at the
school: Javier opens them in a new tab only when asked, and the extension does
nothing there.
