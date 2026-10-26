# Javier for the Universidad Alberto Hurtado — the extension

A Chrome extension that puts Javier, a voice guide for prospective students, on
the Universidad Alberto Hurtado's own sites:
[admision.uahurtado.cl](https://admision.uahurtado.cl) (undergraduate
admission), [postgrados.uahurtado.cl](https://postgrados.uahurtado.cl) and
[www.uahurtado.cl](https://www.uahurtado.cl). He talks a visitor through the
university in Spanish or English while he moves their screen: he opens the
Carreras menu at a faculty, takes them to a career and switches its tabs as he
talks, plays the director's audiomalla, opens "Requisitos y Aranceles" and reads
the 2027 fees and the PAES weights straight off the page, switches the becas
pills, opens a gratuidad FAQ, shows the campus map, rings a visit's sign-up
link, opens a postgraduate programme's "Requisitos y Valores", and fills the
site's own lead form as the visitor dictates it, stopping before "Enviar". One
call follows the visitor across every UAH tab, every page load and all three
hosts. Everything he shows is something the site already has; the extension adds
a corner widget and the ring he draws around what he is pointing at.

This is how we show the agent to the university on its own sites, before
anything goes on them; it is not how a customer would ship it.

## What is in it

- `src/uah-actions.ts` — the site adapter. It performs the brain's page
  Actions on the tab in front and reports every page the visitor lands on as
  `page_changed`: its headings, its tab, pill and accordion labels, its FAQs and
  cards, and on a career page the whole career sheet (data table, tabs,
  audiomalla, fees text, PAES weights), on a programme page its "Requisitos y
  Valores" and sidebar, on /ven-y-conocenos/ its visit cards, and the lead
  form's fields. Only what is laid out at this width is reported, or hidden in
  a pane it can open; a mobile twin the layout hides gives way to the copy on
  screen. The fees are read from the text the page shows, never from the
  `data-sheets-value` attributes beside them, which hold old figures.
- `src/dom.ts` — matching, scrolling under the sticky header, the ring,
  reading text as the page shows it, setting a form field.
- `src/narration.ts` — the screen follows his voice: each cue fires when the
  call's spoken text (`bot-output`) reaches its words, folded as the brain folds
  them, one move at a time. It runs in the holder, with the call, so a cue that
  loads another page ends nothing: the cues after it wait for that tab's next
  page, on whichever host. A reply whose first cue is another page (than the
  one the visitor's UAH tab shows) goes there at once.
- `src/holder.ts`, `src/call.html`, `src/call-client.ts`, `src/relay.ts` — the
  call, in an offscreen document of the extension (below).
- `src/hub.ts`, `src/bridge.ts`, `src/follow.ts`, `src/protocol.ts` — each
  page's port to the holder, its requests of the service worker, and his face
  fed from the holder's relay.
- `src/background.ts` — the service worker: it makes the holder, opens and
  focuses tabs for Javier (uahurtado.cl addresses only), keeps the move a page
  leaves for the next page of its tab (`sessionStorage` does not cross from one
  host to another), and reads the site's own REST record of a career
  (`acf.aranceles_carrera`) or a programme (application window, start,
  requisitos) by slug, four seconds at most — the site answers CORS only for
  www.uahurtado.cl.
- `src/shell.ts`, `src/persist.ts` — in a call, the widget back at once on the
  next page of the same host, and the load as a view transition under it.
- `src/grant.ts`, `src/grant.html` — the extension's one-time microphone grant.
- `src/anchor.ts`, `src/anchors.ts` — from `document_start`, the elements the
  adapter matches on (headings, tab and accordion labels, the Carreras menu, the
  data and fee tables, visit cards, the lead form, the widget) are kept out of
  Chrome's translation, so a visitor who translates the page still gets every
  move. A page translated anyway is reported as `translated`.
- `src/widget.ts` — the corner widget, in a shadow root, in the site's own
  orange, black and Rubik, bottom-left, clear of UserWay's accessibility button
  (bottom-right) and of the lead form while Javier fills it.
- `src/content.ts` — the page's half: the widget, his face, the adapter, the
  moves the holder sends this page (one at a time), and on the call button the
  microphone grant and the one `sessions.connect`.
- `src/actions.gen.ts` — the Action and event unions, generated from
  `../backend/protocol.py` with `pnpm gen`. Never edit it by hand.

The brain is `../backend/`: the prompt, the tools, and the university's
knowledge. The brain never fetches uahurtado.cl; every live figure Javier says
was read here, in the visitor's browser, and reported.

## Build and load

```sh
cp .env.example .env     # the agent id and a publishable key (see below)
pnpm install --ignore-workspace
pnpm build               # → dist/
```

Then `chrome://extensions` → Developer mode → **Load unpacked** → `dist/`, and
open admision.uahurtado.cl. The first call asks once for the microphone, for
the extension (see below), on whichever host. `pnpm build:prod` builds the same
extension against production into `dist-prod/`, from `.env.prod`.

**The extension id is fixed.** `manifest.json` carries a `key` (an RSA public
key; it is not a secret), so the unpacked extension has the same id
(`ologapiamebjfhnlbgemfkhmdnmijjpk`) from any folder and on any machine, and
the microphone grant made once holds across rebuilds and moves. The private key
is not in the repo and is not needed to load unpacked (only to pack a `.crx`).
`dist/` and `dist-prod/` share the id: load one of them at a time.

The publishable key's allowed origins must include
`https://admision.uahurtado.cl`, `https://postgrados.uahurtado.cl` and
`https://www.uahurtado.cl`: the session is minted from whichever of them the
visitor is on when they press the call button. The agent id and key are baked
into the bundle at build time and are never committed: this repo is public.

The call opens in Spanish, as the site does. A visitor who presses English on
the toggle before the call starts gets the call in English, and keeps it
whatever they speak, until they ask for the other; the choice holds on all three
hosts.

All three hosts send `Permissions-Policy: geolocation=(), microphone=(),
camera=()`, which forbids the microphone to the page and to every frame in it,
the extension's grant frame included. `rules.json` rewrites that header on the
university's pages to `microphone=(self "chrome-extension://<this id>")` and
leaves the rest as it was, so the grant page in the widget's frame may ask for
it; that is why the extension asks for `declarativeNetRequest`. The pages
themselves no longer open the microphone. Should the frame not get it, the
grant page opens in a tab of its own instead (below).

The build works without the id and key. With an empty `.env` it warns, and the
extension loads with everything but the call: the widget and every page Action
still work from the console (below).

## Driving it from the console

With the extension loaded, every page Action can be sent exactly as the brain
would send it, from the page's DevTools console, with no call:

```js
const u = __voqalizeUah;
u.context(); // what page_changed would say about this page
// On any admision page:
await u.perform("open_career_menu", { faculty: "Ingeniería", url: "https://admision.uahurtado.cl/" });
// On https://admision.uahurtado.cl/carreras/psicologia/:
await u.perform("show_section", { heading: "Requisitos y Aranceles", text: null });
await u.perform("show_admission", { url: location.href, slug: "psicologia", focus: "fees" });
await u.perform("play_audiomalla", { url: location.href });
await u.perform("fill_lead_form", {
  nombre: "Ana", apellido: "Pérez", email: "ana@example.com", fono: "+56912345678",
  consulta: "Consulta por arancel 2027", carrera: null, via: null, focus_rut: false,
});
// On /becas-y-beneficios/ and /gratuidad-universitaria/:
await u.perform("show_section", { heading: "Beca Alberto Hurtado", text: null });
await u.perform("open_faq", { question: "¿Puedo optar a la gratuidad si ya cursé una carrera?" });
// On /ven-y-conocenos/:
await u.perform("show_signup", { title: "Talleres de Primavera" });
// On a postgrados programme:
await u.perform("show_program", { url: location.href, slug: location.pathname.split("/")[2] });
```

Each call returns the event the brain would receive: `command_done` with what
is on screen now, `admission_read` / `program_read` with what was read, or
`command_failed` with the reason in words the model can act on (a heading that
is not on the page lists the ones that are).

A move that needs another page (`navigate`, or `show_admission` on a career
that is not in front) keeps itself with the service worker and loads that page,
so the console's next line runs on a page that no longer exists; the move is
made on the new page once it is up.

## Forms are filled, never sent

`fill_lead_form` types what the visitor dictated into the site's own lead form
(`form#admisionForm`, in the header of every career page and on most admision
pages), field by field, the way typing would, so the form's own scripts see it.
It never types the RUT (with `focus_rut` it rings and focuses the field for the
visitor), never calls `submit()` or `requestSubmit()`, never presses "Enviar"
or Enter: once everything but the RUT is in, it rings "Enviar" for the visitor.
That form is a real lead in the university's admissions pipeline: the visitor
reviews it and presses "Enviar" themselves, the post goes to UAH as it always
does, and the extension only reports the press (`lead_submitted`) so Javier can
thank them.

The PAES simulator (simula.uahurtado.cl) opens in a tab of its own when Javier
offers it; the extension does not run there, and fills nothing: its form is a
lead too. A visit's "Inscribirse aquí" is rung, never followed: the sign-up is a
Google or HubSpot form the visitor opens themselves.

## How the call lives through page loads, on every host

Every move between the university's pages is a full page load, and a move from
admision to postgrados or www is a load to another origin. The call therefore
does not live in a page: it lives in an **offscreen document of the extension**
(`call.html`, `src/holder.ts`, "the holder"), which no page load touches, on any
host.

- **The holder** runs stock pipecat on `@voqalize/client-transport`, plays his
  voice, keeps every open UAH tab (by browser tab id, which a load to another
  host keeps: its port, where it is, whether it is in front) and sends the
  brain `tabs_changed`, routes each brain Action to the UAH tab in front (else
  the one last in front, else a new one), fires his cues as he speaks
  (`src/narration.ts`), holds the microphone muted while the audiomalla plays,
  and relays to the pages what they need to draw his face (`src/relay.ts`:
  pipecat's events, the avatar's sync channel, which the holder opens and says
  hello on, and the mouth clock).
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
  it after 30 s without sound), one at a time, and tells every UAH tab when it
  is up (`holder-up`): a port opened before the holder existed has no one at
  the other end, so pages open theirs on that word.
- **The session is minted by the page.** On the call button the page calls
  `sessions.connect` with the publishable key (its fetch carries the UAH
  host's Origin, which the key allows; a `chrome-extension://` origin cannot be
  added to a publishable key) and hands the answer to the holder, which
  connects.
- **A move for a page that is loading waits for it.** When a page starts
  loading another document it tells the holder (`leaving`); a move sent to
  that tab meanwhile is kept and delivered when the next page says `hello`, on
  whichever host. A move that itself loads a page (a career, the fees there)
  keeps itself with the service worker and is made on the page it loads, once
  the brain hears that page.
- **The call ends** on End (any tab), when the call drops, or when no UAH page
  has been open for 15 s; the holder then closes. Reloading or updating the
  extension ends it too. The PAES simulator and a malla PDF open in tabs of
  their own, where the extension does not run: a visitor who closes every UAH
  tab and stays there ends the call 15 s later.

Every UAH tab shows Javier's face and the call's state and can mute or end it;
the tab in front is the one he sees and moves. While a call is live, a link to
another page of the three sites that would open a new tab loads in the
visitor's tab instead. The call no longer needs that (it follows any UAH tab),
but it keeps the visitor, the widget and his face in one tab rather than a new
tab per career card.

## The widget across a page load

In a call the widget outlives a page load too, as near as a page can: on a load
within one host it is back the moment the next page shows, not once the page
has parsed and the site's scripts have run.

- **What the page leaves.** While a call is on, `content.js` keeps a picture of
  it in the tab's `sessionStorage` (`src/persist.ts`): live or connecting,
  muted or not, the status line, the language, where the visitor put the widget
  and whether it is minimised, the character's still, and the last frame his
  face drew (read from the avatar's canvas every 3 s and as the page leaves).
  It is taken away when the call ends, and is stale after 60 s.
- **The early shell.** `shell.js` (`src/shell.ts`) runs in the page's world at
  `document_start`. Off a call it reads that one key and does nothing else. In
  a call it mounts the widget on `<html>` at once, as the last page left it,
  with the last frame of his face as a still. `content.js` adopts that widget,
  asks the holder for the call's state, and fades the still out once the live
  face has drawn. The still is a plain still: it holds, unmoving, until the
  live face draws. Should the holder be gone (no holder, or no word from it in
  8 s), the carried widget goes back to the invite.
- **The view transition.** In a call both pages opt in to a cross-document
  view transition (`@view-transition { navigation: auto }`, Chrome 126+). The
  widget's host has its own `view-transition-name` (`voqalize-javier`), so the
  page fades under it in 150 ms while it stays where it is.
- **Across hosts.** `sessionStorage` and view transitions are per origin, so a
  load from admision to postgrados or www has no early widget and no
  transition: the widget comes back at `document_idle`, live, from the
  holder's state. The call and his voice carry on either way.

## The microphone, once

The microphone is the extension's, not the university's: Chrome keeps the
permission against `chrome-extension://<id>`, `chrome.contentSettings` cannot
set it for that origin, and an offscreen document cannot show a prompt. So, on
each press of the call button, the page asks the holder for the extension's
microphone permission state first:

- **granted**: the call starts.
- **prompt** (the first call): the widget shows the extension's own page
  `grant.html` in a frame (`<iframe allow="microphone">`), which asks at once.
  Chrome's prompt names the extension; the visitor chooses *Allow*. Should it
  still not be granted, `grant.html` opens once in a tab of its own, asks the
  same way, closes itself once answered, and the call starts.
- **denied**: the widget says Chrome blocks the microphone for the extension,
  with a button that opens `chrome://settings/content/microphone`.

One grant covers all three hosts: it is the extension's, so Chrome never asks
again as the visitor moves between them.

**His voice plays from the extension, not from the tab.** Muting the tab does
not silence him; the widget's *Silenciar* mutes the visitor's microphone, and
*Colgar* ends the call. Chrome shows the microphone in use for the extension
rather than for the tab.

## The page test

`pnpm test:page` drives the adapter in headless Chromium against trimmed copies
of the university's pages (`demos/tests/fixtures/uahurtado/`), with a small
stand-in for Bootstrap and no network: tabs, pills, collapses, the Carreras
menu, the career sheet and its fees, the lead form and its submit guard, visit
cards, a programme's requisitos. It needs Chromium for `playwright-core`
already installed (it never downloads one). `demos/tests/test_uahurtado_extension.py`
runs it from the demos suite, and skips where Node, the extension's
`node_modules` or Chromium is missing.

## The end-to-end tests

`pnpm test:e2e` builds the extension with a stand-in call in the holder
(`test/fake-call-client.ts`), a stand-in avatar and a made-up API
(`VOQALIZE_TEST_BUILD=1`, into `test/.build/ext`), loads it in headless
Chromium with pages served at admision.'s and postgrados.'s addresses, and runs
`test/holder.spec.ts`: the port protocol, mute, the audiomalla's hold and End;
a page load and a load to postgrados that leave the call alone, with the moves
sent meanwhile made on the next page; the 15 s rule; the microphone's three
branches; and the widget across a load (early shell, view transition, a stale
carried widget). No network.
