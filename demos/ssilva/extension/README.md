# Javier for Ssilva — the extension

A Chrome extension that puts Javier, a voice guide, on
[ssilva.cl](https://www.ssilva.cl), the site of SSILVA Gestión Inmobiliaria. He
talks a visitor through Ssilva's projects while he moves their screen: he
lists the projects that fit on /proyectos/ and rings each project's card as he
names it, opens a project's page and scrolls to the section that answers them
(the gallery, the typologies, the amenities, the tour, the build status, the
brochure, the contact block), selects a typology to show its price and floor
plan, opens a floor plan or the photos full screen one at a time or as a
slideshow, opens the virtual tour, and fills in the project's quote form with
them as they speak. One call follows the visitor across every Ssilva tab they have
open, and through every full page load, without reconnecting. Everything he
shows is a page, section, photo or form Ssilva already has; the extension adds a
corner widget, the ring he draws around what he is pointing at, and a
full-screen view for photos and plans (the site's own lightbox does not open
for a script, and its "Agrandar imagen" replaces the page with the bare PNG).

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
  section, the typology, the project list's filters) with the extension's
  service worker and loads the page; the next page's script makes it once the
  brain can hear that page. The window scrolls, under Ssilva's fixed 70px
  header. Visitors who read the site through Chrome's translation see
  "BARROSO DISTRICT" and "From 2,582 UF": the adapter finds a project's card
  by the page it links to, matches prices whatever their separators, and
  reads "BUTTERFLY" as "MARIPOSA" in a typology's label.
- `src/hsform.ts` — runs inside the HubSpot quote-form frame (js.hsforms.net),
  only when Ssilva's page holds it. It fills the form the way typing does, so
  HubSpot's React state takes it; picks dropdown options by their text; keeps a
  step-2 answer until step 2 shows; presses "Siguiente" when asked and step 1
  is complete; and reports the form — its step, what is filled, what is
  missing, this project's dropdown options and its errors — on every change,
  the visitor's typing included. It never presses "Enviar". It talks to the
  page by `postMessage`; the frame is not a Ssilva tab and has no port to the
  holder.
- `src/narration.ts` — the screen follows his voice. The brain sends each
  screen cue he wrote into his reply ahead of the speech, with the first words
  of the sentence it belongs to; this fires it when the call's spoken-text
  events reach those words, one move at a time. It runs in the holder, with
  the call, so a cue that loads another page ends nothing: the cues after it
  wait for the next page.
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
  focuses tabs (Ssilva and WhatsApp addresses only), keeps the adapter's move
  for a tab's next page, opens the microphone grant tab, keeps the language
  choice.
- `src/grant.ts`, `src/grant.html` — the extension's one-time microphone grant.
- `src/widget.ts` — the corner widget, in a shadow root: the call and the
  Español/English toggle, which also sets the widget's own words. Off a call
  the toggle picks the language the next call starts in; in a call it asks the
  brain to switch, from any tab. It moves off the quote form while the form is
  on screen.
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
open www.ssilva.cl. The first call asks for the microphone (see "The
microphone, once"). `pnpm build:prod` builds the same extension against
production into `dist-prod/`, from `.env.prod`.

**The extension id is fixed.** `manifest.json` carries a `key` (an RSA public
key; it is not a secret), so the unpacked extension has the same id from any
folder and on any machine, and the microphone grant made once holds across
rebuilds and moves. The private key is not in the repo and is not needed to
load unpacked (only to pack a `.crx`). `dist/` and `dist-prod/` share the id:
load one of them at a time. Anyone who loaded an earlier build (whose id came
from its folder) reloads it once.

The publishable key's allowed origins must include `https://www.ssilva.cl` and
`https://ssilva.cl`, which are where the session is minted from. The agent id and key are baked into the bundle at build
time and are never committed: this repo is public.

ssilva.cl sends no `Permissions-Policy` and its only CSP is
`frame-ancestors *`, so the grant frame may ask for the microphone and the
early widget's still (a `data:` image) shows; the extension rewrites no
header.

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
await __voqalizeSsilva.perform("show_card", { path: "/distrito-barroso/", name: "DISTRITO BARROSO" }); // on /proyectos/
await __voqalizeSsilva.perform("show_photos", { which: "gallery", index: 2, fullscreen: true });
await __voqalizeSsilva.perform("step_photo", { back: false });
await __voqalizeSsilva.perform("slideshow", { play: true, which: null, seconds: 5 });
await __voqalizeSsilva.perform("slideshow", { play: false, which: null, seconds: null });
await __voqalizeSsilva.perform("show_photos", { which: "amenities", index: 2, fullscreen: true });
await __voqalizeSsilva.perform("show_floor_plan", { typology: "2D | 2B MARIPOSA" });
await __voqalizeSsilva.perform("close_overlay", {});
await __voqalizeSsilva.perform("fill_lead_form", {
  firstname: "Ana", lastname: "Pérez", rut: "12.345.678-5", email: "ana@example.cl", phone: "987654321",
  motivo: "Habitar", tipologia: null, ingreso: null, pie: null, next_step: true,
});
// What the page reports, as the brain would receive it:
window.voqalizeSsilva.start((event, payload) => console.log(event, payload));
```

A move that could not be made comes back as the `command_failed` the brain
would receive, with the reason in words the model can act on: a heading that is
not on the page lists the ones that are; a typology lists the page's
typologies; a dropdown answer the form does not offer lists its options.

A `navigate` to another page loads it, so the console's next line runs on a
page that no longer exists; the section it names is shown on the new page.
Cues are narrated in the holder now, with the call, so there is no console
handle for them.

## How the call lives through page loads

Every link on ssilva.cl is a full page load (a project, the project list, the
quote page), often in the middle of his sentence. The call therefore does not
live in a page: it lives in an **offscreen document of the extension**
(`call.html`, `src/holder.ts`, "the holder"), which no page load touches.

- **The holder** runs stock pipecat on `@voqalize/client-transport`, plays his
  voice, keeps every open Ssilva tab (by browser tab id: its port, where it
  is, whether it is in front) and sends the brain `tabs_changed`, routes each
  brain Action to the tab it belongs on, fires his cues as he speaks
  (`src/narration.ts`) and relays to the pages what they need to draw his face
  (`src/relay.ts`: pipecat's events, the avatar's sync channel, which the
  holder opens and says hello on, and the mouth clock).
- **Every page is a follower** (`src/content.ts`): the widget, his face (the
  unchanged avatar against a stand-in client fed by the relay,
  `src/follow.ts`), the site adapter, and the moves the holder sends it. It
  reports what it shows up the port. Each page keeps one port to the holder
  (`src/bridge.ts` in the isolated world, `src/hub.ts` in the page's world).
  The HubSpot form's frame has none: it is part of its page.
- **The service worker** (`src/background.ts`) makes the holder on the first
  press of the call button, with the reasons `USER_MEDIA` and `WEB_RTC` (they
  keep the document alive through any silence; `AUDIO_PLAYBACK` alone closes
  it after 30 s without sound), one at a time, and tells every Ssilva tab when
  it is up (`holder-up`): a port opened before the holder existed has no one
  at the other end, so pages open theirs on that word. It also opens and
  focuses tabs for his moves (an offscreen document has no `chrome.tabs`),
  keeps the adapter's move for a tab's next page, and keeps the language
  choice.
- **The session is minted by the page.** On the call button the page calls
  `sessions.connect` with the publishable key (its fetch carries ssilva.cl's
  Origin, which the key allows; a `chrome-extension://` origin cannot be added
  to a publishable key) and hands the answer to the holder, which connects.
- **Where each Action goes.** A move on a page (a section, a typology, the
  project list, the photos, the quote form) goes to the tab in front. A
  `navigate` goes to a Ssilva tab: the one in front, else the one last in
  front, brought to the front, else a new one, which makes the move once it is
  up. A project's WhatsApp opens in a tab of its own, through the service
  worker.
- **A move for a page that is loading waits for it.** When a page starts
  loading another document it tells the holder (`leaving`); a move sent to
  that tab meanwhile is kept and delivered when the next page says `hello`. A
  `navigate` (or `show_projects` from another page) that itself loads a page
  leaves the rest of its move with the service worker (`pend`); the next page
  takes it (`pending`, once, and only within 60 s) and makes it once the brain
  can hear that page, and a failure there is reported as any move's would be.
- **The call ends** on End (any tab), when the call drops, or when no Ssilva
  page has been open for 15 s; the holder then closes. Reloading or updating
  the extension ends it too. WhatsApp tabs have no content script, so they do
  not count: a visitor who closes every Ssilva tab and keeps only the WhatsApp
  chat open loses the call 15 s later.

## The widget across a page load

The call outlives a page load, and in a call the widget does too, as near as a
page can: it is back the moment the next page shows, not once the page has
loaded and the content script has run.

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
  where his face goes. `content.js` adopts that widget instead of mounting
  another, asks the holder for the call's state, starts building his face at
  once (`preloadAvatar`), and fades the still out once the live face has
  drawn. Should the holder be gone (no holder, or no word from it in 8 s), the
  carried widget goes back to the invite.
- **The view transition.** In a call both pages opt in to a cross-document
  view transition (`@view-transition { navigation: auto }`, Chrome 126+): the
  page that leaves (`content.js`, while a call is on) and the page that arrives
  (`shell.js`, from what was kept). The widget's host has its own
  `view-transition-name` (`voqalize-javier`), so the page fades under it in
  150 ms while it stays where it is. The host is a see-through, fixed box over
  the viewport that takes no pointer events (the widget inside it does), so it
  is captured whole and in place. Older Chrome ignores the rule and loads the
  page as before, with the widget still up early. Off a call no transition is
  asked for. `sessionStorage` and view transitions are per origin; ssilva.cl
  redirects to www.ssilva.cl, and the adapter keeps every move on the host the
  visitor is on, so in practice every load is same-origin.

## The microphone, once

The microphone is the extension's, not ssilva.cl's: Chrome keeps the
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
  visitor takes "Javier for Ssilva" off the blocked list.

**His voice plays from the extension, not from the tab.** Muting the tab does
not silence him; the widget's *Silenciar* mutes the visitor's microphone, and
*Colgar* ends the call. Chrome shows the microphone in use for the extension
rather than for the tab.

## Tests

```sh
pnpm test:e2e
```

Playwright, headless. `test/holder.spec.ts` loads the built extension
(`VOQALIZE_TEST_BUILD=1` builds it into `test/.build/ext` with a stand-in
call, `test/fake-call-client.ts`, a stand-in avatar and a made-up API) on
pages served at ssilva.cl's address, and checks the port protocol (the press,
the session minted with the page's Origin and handed over, the state on the
page, its events reaching the brain, mute and End), a move sent while the tab
loads made on its next page's hello, the adapter's `navigate` to a section of
another project made there (and its failure reported), a project's WhatsApp
opened in a tab of its own that never joins the tab list (nor does the quote
form's frame), the 15 s rule, the widget across a page load, and the
microphone's branches with the permission query stubbed. The WhatsApp tab is
opened by the extension before the test's routes reach it, so that one test
loads wa.me for real. Its last two tests drive the screen through the
holder on a project list and a project page as Chrome's translation leaves
them: a card he names rung by its link and paged to, the list's own ring by
the projects' pages, photos full screen one at a time, a slideshow the
visitor's voice stops, a photo cue, a floor plan by its Spanish label, and a
price cue written "Desde 2.582 UF" on a page that says "FROM 2,582 UF".
