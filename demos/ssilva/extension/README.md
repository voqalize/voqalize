# Javier for Ssilva — the extension

A Chrome extension that puts Javier, a voice guide, on
[ssilva.cl](https://www.ssilva.cl), the site of SSILVA Gestión Inmobiliaria. He
talks a visitor through Ssilva's projects while he moves their screen: he
lists the projects that fit on /proyectos/ and rings the ones he means, opens a
project's page and scrolls to the section that answers them (the gallery, the
typologies, the amenities, the tour, the build status, the brochure, the
contact block), selects a typology to show its price and floor plan, opens the
photos and the virtual tour, and fills in the project's quote form with them as
they speak. Everything he shows is a page, section or form Ssilva already has;
the extension adds a corner widget and the ring he draws around what he is
pointing at.

The site is in Spanish, and so is Javier by default; the widget's toggle (and
speaking English to him) switches him to English, and he explains the Spanish
page in English.

This is how we show the agent to Ssilva on their own site, before anything goes
on it; it is not how a customer would ship it.

## What is in it

- `src/ssilva-actions.ts` — the site adapter. It performs the brain's page
  Actions on the tab in front and reports every page, typology, project list
  and quote-form change back, whoever caused it. Every link on ssilva.cl is a
  full page load, so a move to another page leaves the move to make there (the
  section, the typology, the project list's filters) with the hub and loads the
  page; the next page's script makes it. The window scrolls, under Ssilva's
  fixed 70px header.
- `src/hsform.ts` — runs inside the HubSpot quote-form frame (js.hsforms.net),
  only when Ssilva's page holds it. It fills the form the way typing does, so
  HubSpot's React state takes it; picks dropdown options by their text; keeps a
  step-2 answer until step 2 shows; presses "Siguiente" when asked and step 1
  is complete; and reports the form — its step, what is filled, what is
  missing, this project's dropdown options and its errors — on every change,
  the visitor's typing included. It never presses "Enviar".
- `src/narration.ts` — the screen follows his voice. The brain sends each
  screen cue he wrote into his reply ahead of the speech, with the first words
  of the sentence it belongs to; this fires it when the call's spoken-text
  events reach those words, one move at a time. A cue that loads another page
  takes the cues after it along (through the hub), and the next page makes
  them as his voice gets there.
- `src/hub.ts`, `src/bridge.ts`, `src/background.ts` — the hub. The extension's
  service worker relays the call between every Ssilva tab (www.ssilva.cl and
  ssilva.cl are two origins), holds the call's claim by browser tab, keeps
  what a page leaves for its tab's next page, and opens a project's WhatsApp
  chat in a new tab, since his move arrives over the call and a page may not
  open a tab without a click.
- `src/tabs.ts` — Qween's one-call-every-tab relay, on the hub: the tab the
  call started in holds it; every other tab follows with his face, the mute and
  the call's state.
- `src/widget.ts` — the corner widget, in a shadow root: the call and the
  Español/English toggle, which also sets the widget's own words. Off a call
  the toggle picks the language the next call starts in; in a call it asks the
  brain to switch, from any tab.
- `src/content.ts` — the call: stock pipecat with `@voqalize/client-transport`
  as its media manager, one `sessions.connect`, the avatar, and the routing of
  each Action to the tab in front. A page load rejoins the same call on the
  next page (`keepAcrossPageLoads`).
- `src/actions.gen.ts` — the Action and event unions, generated from the brain
  with `pnpm gen`. Regenerate after changing either.

The brain is `../backend/`: the prompt, the tools, and Ssilva's knowledge.

## Build and load

```sh
cp .env.example .env     # the agent id and a publishable key (see below)
pnpm install --ignore-workspace
pnpm build               # → dist/
```

Then `chrome://extensions` → Developer mode → **Load unpacked** → `dist/`, and
open www.ssilva.cl. The first call asks for the microphone. `pnpm build:prod`
builds the same extension against production into `dist-prod/`, from
`.env.prod`.

The publishable key's allowed origins must include `https://www.ssilva.cl` and
`https://ssilva.cl`. The agent id and key are baked into the bundle at build
time and are never committed: this repo is public.

The build works without them. With an empty `.env` it warns, and the extension
loads with everything but the call: the widget and every page Action still work
from the console (below).

## Quote requests are not sent from a preview

`SSILVA_BLOCK_SUBMIT` decides what happens when the visitor presses the quote
form's **Enviar**. Javier never presses it; the visitor does. With the flag on,
the press is reported to the brain as `lead_submitted` with `blocked: true` and
then stopped before HubSpot sees it, with "Vista previa: este formulario no se
envió a Ssilva." under the form. With it off, the press is reported with
`blocked: false` and the form is sent to Ssilva as usual.

Unset, the dev build (`pnpm build`) stops it and the production build
(`pnpm build:prod`) sends it. Set `SSILVA_BLOCK_SUBMIT=1` or `0` in the
environment or the `.env` file to choose either way.

## Driving it from the console

With the extension loaded, every page Action can be sent exactly as the brain
would send it, from the page's DevTools console, with no call:

```js
await __voqalizeSsilva.perform("navigate", { path: "/canalbeagle/", heading: "amenidades", text: null, typology: null });
await __voqalizeSsilva.perform("show_section", { heading: "tipologías", text: null });
await __voqalizeSsilva.perform("select_typology", { label: "2D | 2B" });
await __voqalizeSsilva.perform("show_projects", {
  region: "metropolitana", property: "departamento", communes: ["Las Condes"], highlight: ["Estocolmo"],
});
await __voqalizeSsilva.perform("show_photos", { which: "amenities", index: 2 });
await __voqalizeSsilva.perform("close_overlay", {});
await __voqalizeSsilva.perform("fill_lead_form", {
  firstname: "Ana", lastname: "Pérez", rut: "12.345.678-5", email: "ana@example.cl", phone: "987654321",
  motivo: "Habitar", tipologia: null, ingreso: null, pie: null, next_step: true,
});
// A narrated turn: cues as the brain sends them, then speech as the voice plays it.
const n = __voqalizeSsilva.narration;
n.speaking();
n.add({ at: "vamos a ver canal beagle", word: 0, path: "/canalbeagle/", heading: null, text: null, typology: null });
n.add({ at: "mira la galeria", word: 5, path: null, heading: "galería", text: null, typology: null });
n.hear("Vamos a ver Canal Beagle.");
// What the page reports, as the brain would receive it:
window.voqalizeSsilva.start((event, payload) => console.log(event, payload));
```

A move that could not be made comes back as the `command_failed` the brain
would receive, with the reason in words the model can act on: a heading that is
not on the page lists the ones that are; a typology lists the page's
typologies; a dropdown answer the form does not offer lists its options.

## One call, every tab

The call belongs to the tab it started in. Every other Ssilva tab shows
Javier's face and the call's state and can mute or end it; the tab in front is
the one he sees and moves. Closing the call's tab ends the call everywhere.
