# Javier para Clini — the extension

A Chrome extension that puts Javier, a voice guide, on
[www.clini.cl](https://www.clini.cl) and its online booking,
[agenda-web.clini.cl](https://agenda-web.clini.cl). He talks a visitor through
the site in Spanish or English while he moves their screen: he opens the page
that answers them, scrolls to the exact section and rings it, and opens an FAQ.
One call follows the visitor across every Clini tab they have open and every
page load, on both hosts. Everything he shows is a page, section or FAQ Clini already has; the
extension adds a corner widget and the ring he draws around what he is pointing
at.

This is how we show the agent to Clini on their own site, before anything goes
on it; it is not how a customer would ship it.

He also does the parts of a visit that are forms, up to the last button and
never past it:

- **Booking on agenda-web.clini.cl** (labs, imaging, cardiology). He opens the
  booking for the right service in a tab of its own, picks the region, the
  prestación, the day, the centre and the time, presses *Continuar*, and fills
  the patient's fields the visitor says. The booking's state goes back to the
  brain as `agenda_state` after every step, whoever took it.
- **The free LASIK evaluation** on /cirugia-lasik: he fills name, email, phone,
  previsión and sede, and reports `lasik_form_state`.
- **Other services** the site links to (Reservo for consultations, the results
  portals, the cotizador, telemedicine, WhatsApp) open in a new tab.

## What he never does

These are rules of the adapters, not of the prompt, so no brain can lift them:

- He never submits a form: no `.submit()`, no Enter, no click on a submit
  button. On agenda-web he never presses **AGENDAR** (`#btnAgendar`). On the
  LASIK form he never presses **¡Agendar evaluación!**. He rings the button
  once the form is complete, and the visitor presses it.
- He never types a **RUT**. He focuses the RUT field and rings it, and the
  visitor types it. agenda-web opens the other patient fields only after it
  has looked that RUT up (`PacientePorDocumento`, which the page itself calls
  on the visitor's typing), so on step 2 he points at the RUT first.
- He never ticks the privacy consent (`#consentPrivacy`). That consent is the
  visitor's to give.
- The service worker opens tabs only on Clini's hosts and the services the site links:
  `*.clini.cl`, `agendamiento.reservo.cl`, `app.dalca.cl`,
  `patientportal.prod.clini.procloudhub.com`, `clini.medipasspro.com`,
  `wa.me` and `api.whatsapp.com`.

## How the call lives through page loads

www.clini.cl is Webflow, with no client router: every move to another page is a
full page load, and the booking is another host. The call therefore does not
live in a page: it lives in an **offscreen document of the extension**
(`call.html`, `src/holder.ts`, "the holder"), which no page load touches.

- **The holder** runs stock pipecat on `@voqalize/client-transport`, plays his
  voice, keeps every open Clini tab on both hosts (by browser tab id: its port,
  where it is, whether it is in front) and sends the brain `tabs_changed`,
  routes each brain Action to the tab it belongs on, fires his cues as he
  speaks (`src/narration.ts`) and relays to the pages what they need to draw
  his face (`src/relay.ts`: pipecat's events, the avatar's sync channel, which
  the holder opens and says hello on, and the mouth clock).
- **Where each Action goes.** `navigate` and `fill_lasik_form` go to a www
  tab: the one in front, else the one last in front, brought to the front,
  else a new one. The agenda Actions go to the booking's tab: an open one is
  reused, and it loads the other service's page itself when the servicio
  differs. If none is open, `open_agenda` opens one at
  `?servicio=S&prestacion=P` and the move is made there once its page is up.
  `open_link` opens its address in a new tab (that tab is not ours, so it is
  not in the registry). For 10 s after a move on the booking, a cue to another
  page of the site is dropped rather than pulling the visitor off it.
- **Every page is a follower** (`src/content.ts`): the widget, his face (the
  unchanged avatar against a stand-in client fed by the relay,
  `src/follow.ts`), the site adapter, and the moves the holder sends it. It
  reports what it shows up the port; a move's outcome (`command_done`,
  `command_failed`) and the forms' state reach the brain from any tab, the
  rest from the tab in front. The stand-in carries the relayed mouth clock
  forward to each read of it, for at most 100 ms (`src/mouth-clock.ts`): a
  busy page reads the relay late, and the face takes a late reading for a
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
  it after 30 s without sound), one at a time, and tells every Clini tab when
  it is up (`holder-up`): a port opened before the holder existed has no one
  at the other end, so pages open theirs on that word. It also opens and
  focuses tabs for his moves (an offscreen document has no `chrome.tabs`) and
  keeps the language choice for both hosts.
- **The session is minted by the page.** On the call button the page calls
  `sessions.connect` with the publishable key (its fetch carries the Clini
  host's Origin, which the key allows; a `chrome-extension://` origin cannot be
  added to a publishable key) and hands the answer to the holder, which
  connects. A call can start on agenda-web too.
- **A move for a page that is loading waits for it.** When a page starts
  loading another document it tells the holder (`leaving`); a move sent to
  that tab meanwhile is kept and delivered when the next page says `hello`,
  on the same host or the other one. A move that itself loads a page finishes
  there (the adapter's `sessionStorage` leftover, as before).
- **Links to another host, in a call.** A link that would load another host in
  the same tab (most of the site's "Reservar hora" links to agenda-web, or
  Reservo) opens a new tab instead, as `open_agenda` does: the brain expects
  the booking in a tab of its own beside the site. The call would carry
  through the load either way. Off a call the site behaves as it always does.
- **The call ends** on End (any tab), when the call drops, or when no Clini
  page has been open for 15 s; the holder then closes. A visitor who closes
  every Clini tab and keeps only a Reservo or WhatsApp tab ends it that way.
  Reloading or updating the extension ends it too.

## The widget across a page load

In a call the widget outlives a page load too, as near as a page can: it is
back the moment the next page shows, not once the page has loaded.

- **What the page leaves.** While a call is on, `content.js` keeps a picture of
  it in the tab's `sessionStorage` (`src/persist.ts`): live or connecting,
  muted or not, the status line, the language, where the visitor put the widget
  and whether it is minimised, the character's still, and the last frame his
  face drew (read from the avatar's canvas every 3 s and as the page leaves).
  It is taken away when the call ends, and is stale after 60 s.
- **The early shell.** `shell.js` (`src/shell.ts`) runs in the page's world at
  `document_start`. Off a call it reads that one key and does nothing else. In
  a call it mounts the widget on `<html>` at once, as the last page left it,
  with the last frame of his face as a still where his face goes. `content.js`
  adopts that widget instead of mounting another, asks the holder for the
  call's state, starts building his face at once, and fades the still out once
  the live face has drawn. The still is never a frozen face: from the page's
  first paint it moves in CSS alone (`.poster` in `src/widget.ts`), a slow
  breath while he listens and a talking head while he speaks, held still
  under reduced motion. Its lips do not move, and the half second or so in
  which Chrome swaps the documents shows the last page's last frame, where
  nothing can move. Should the holder be gone (no holder, or no word from it
  in 8 s), the carried widget goes back to the invite.
- **The view transition.** In a call both pages opt in to a cross-document
  view transition (`@view-transition { navigation: auto }`, Chrome 126+). The
  widget's host has its own `view-transition-name` (`voqalize-javier`), so the
  page fades under it in 150 ms while it stays where it is. Off a call no
  transition is asked for.
- **Across hosts.** `sessionStorage` and view transitions are per origin, so a
  load from www.clini.cl to agenda-web (or back) gets no early widget and no
  transition: the widget comes back when `content.js` mounts. The call is
  unaffected.

## The microphone, once

The microphone is the extension's, not the site's: Chrome keeps the permission
against `chrome-extension://<id>`, and an offscreen document cannot show a
prompt. So, on each press of the call button, the page asks the holder for the
extension's microphone permission state first:

- **granted**: the call starts.
- **prompt** (the first call): the widget shows the extension's own page
  `grant.html` in a frame (`<iframe allow="microphone">`), which asks at once.
  Chrome's prompt names the extension ("Javier para Clini — Voqalize preview");
  the visitor chooses *Allow*. Should the grant still not hold, `grant.html`
  opens once in a tab of its own, asks the same way, closes itself once
  answered, and the call starts. Neither host sends a `Permissions-Policy` or a
  CSP `frame-src` (www.clini.cl sends only `frame-ancestors 'self'`), so the
  frame is allowed.
- **denied**: the widget says Chrome blocks the microphone for the extension,
  with a button that opens `chrome://settings/content/microphone`.

**His voice plays from the extension, not from the tab.** Muting the tab does
not silence him; the widget's *Silenciar* mutes the visitor's microphone, and
*Colgar* ends the call. Chrome shows the microphone in use for the extension.

## What is in it

- `src/clini-actions.ts` — the site adapter for www.clini.cl: `navigate`,
  `show_section`, `open_faq` and `fill_lasik_form`. Every move to another page
  is a full page load, so the rest of a move (a heading, an FAQ, the LASIK
  form) is left in `sessionStorage` and made on the next page. Sections are
  found by their words. Tabs, dropdowns (the FAQs and a sede's "Ver
  horarios"), the newer `.faq-item` accordion and slider slides are revealed
  by the same click a visitor would make.
- `src/agenda-actions.ts` — the booking adapter for agenda-web.clini.cl:
  `open_agenda`, `agenda_pick`, `fill_agenda_patient`, and the `agenda_state`
  report.
- `src/anchors.ts`, `src/anchor.ts` — Chrome's translator kept off what the
  adapters match on. From `document_start` the headings, FAQ questions, tab
  links and dropdown toggles on www, and the calendar, centre titles, summary
  and document switch on agenda-web, get `translate="no"`; each day button is
  stamped with its date (`data-voqalize-date`) while its label is still
  Spanish. Days are read by class and stamp, centres by the name after "|",
  so a translated page still books.
- `src/page.ts` — what both adapters share: the waits, the window scroll under
  the fixed header (96 px, 91 on a phone), the ring in CLINI's pink, and the
  native-setter fill.
- `src/holder.ts`, `src/call.html` — the holder (above); `src/call-client.ts`
  makes the pipecat client and reads the microphone permission.
- `src/relay.ts`, `src/follow.ts` — what crosses from the holder to the pages
  for his face, and the stand-in client the avatar draws against.
- `src/narration.ts` — the screen follows his voice: each cue fires when the
  call's spoken text reaches the first words of its sentence. It runs in the
  holder, so a load ends nothing.
- `src/protocol.ts` — the messages between the pages, the holder and the
  service worker, and which Actions go where.
- `src/bridge.ts`, `src/hub.ts` — the page's port to the holder and its
  requests of the service worker.
- `src/background.ts` — the service worker (above).
- `src/grant.ts`, `src/grant.html` — the extension's one-time microphone
  grant (above).
- `src/widget.ts` — the widget, in a shadow root, in CLINI's purple and pink:
  the call and the Español/English toggle. It sits bottom-left, because
  Clinito's chat owns the bottom-right, and moves up above the phone's bottom
  bar and the chat wherever it would cover them. Off a call the toggle picks
  the language the next call starts in; in a call it asks the brain to switch.
  The widget is never translated ("Javier" stays Javier). It also holds the
  grant frame and the "microphone blocked" message.
- `src/shell.ts`, `src/persist.ts` — the early shell, what a page in a call
  leaves for the next one, and the view transition (above).
- `src/content.ts` — the page: the widget, his face, the adapter, the moves
  the holder sends, and on the call button the microphone check and
  `sessions.connect` (`surface: "clini-ext"`).
- `src/actions.gen.ts` — the Action and event unions, generated from the brain
  with `pnpm gen`. Regenerate after changing either.

The brain is `../backend/`: the prompt, the tools, and Clini's knowledge.

## Build and load

```sh
cp .env.example .env          # the agent id and a publishable key (never committed)
pnpm install --ignore-workspace
pnpm gen                      # after any change to the brain's Actions or events
pnpm build                    # → dist/, against dev; `pnpm build:prod` → dist-prod/
```

`pnpm build` reads `.env` (the dev agent and key, `app.dev.voqalize.com`) and
runs the dev avatar runtime. `pnpm build:prod` reads `.env.prod` into
`dist-prod/`, with the npm-pinned runtime. Neither env file is committed.

Load `dist/` unpacked in `chrome://extensions`. The publishable key's allowed
origins are the host pages' (`https://www.clini.cl`, `https://clini.cl`,
`https://agenda-web.clini.cl`), because the page mints the session.

**The extension id is fixed.** `manifest.json` carries a `key` (an RSA public
key; it is not a secret), so the unpacked extension has the same id from any
folder and on any machine, and the microphone grant made once holds across
rebuilds and moves. The private key is not in the repo and is not needed to
load unpacked (only to pack a `.crx`). `dist/` and `dist-prod/` share the id:
load one of them at a time. The id changed once, with this key, from the old
path-derived one: reload the unpacked build after upgrading, and allow the
microphone once more.

## Tests

```sh
pnpm test:e2e
```

Playwright, headless, no network (`test/holder.spec.ts`): the built extension
with a stand-in call (`test/fake-call-client.ts`) and a stand-in avatar, pages
served at www.clini.cl's and agenda-web's addresses, a made-up API. It covers
the port protocol, a full page load (and a load from www.clini.cl to the
booking) with a move made on the next page, `open_agenda` opening the
booking's tab, the 15 s rule, the microphone's branches, the widget across a
page load, his mouth clock on a busy page, a load in the middle of a reply and
the moving still; `test/mouth-clock.spec.ts` and `test/catch-up.spec.ts` cover
those two modules alone. The brain's own e2e is `demos/tests/test_clini_e2e.py`.

## Driving it from the console

With no call, on a Clini page:

```js
await voqalizeClini.run("show_section", { heading: "Conoce los servicios que en CLINI tenemos para ti" });
await voqalizeClini.run("navigate", { path: "/ubicaciones", heading: "Centro de Salud Astra Alameda" });
await voqalizeClini.run("open_faq", { question: "¿Es dolorosa?" });            // on /cirugia-lasik
await voqalizeClini.run("fill_lasik_form", { name: "Prueba Test", location: "Los Leones" });
// on https://agenda-web.clini.cl/?servicio=64&prestacion=804
await voqalizeClini.run("agenda_pick", { day: "2026-10-23", time: "08:00", centre: "Salvador" });
voqalizeClini.context();
```

When you test the booking by hand, use obviously fake data (the site's own
placeholder RUT is `12.345.678-5`), and never press AGENDAR.
