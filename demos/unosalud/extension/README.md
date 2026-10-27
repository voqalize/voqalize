# Javier para Uno Salud Dental — the extension

A Chrome extension that puts Javier, a voice guide, on
[www.unosalud.cl](https://www.unosalud.cl), the site of Uno Salud Dental's 103
dental clinics, and its online booking, `/agenda-tu-hora/`. He talks a visitor
through the site in Spanish or English while he moves their screen: he opens
the page that answers them, scrolls to the exact place and rings it, opens an
FAQ, and shows a clinic's hours and how to get there. One call follows the
visitor across every Uno Salud tab they have open and every page load.
Everything he shows is a page, place or FAQ Uno Salud already has; the
extension adds a corner widget and the ring he draws around what he is
pointing at.

This is how we show the agent to Uno Salud on their own site, before anything
goes on it; it is not how a customer would ship it.

He also does the parts of a visit that are forms, up to the last button and
never past it:

- **Booking** (`/agenda-tu-hora/`, Dentalsoft's wizard, in a tab of its own,
  with a promotion's `promo=` code when there is one). The first step is the
  visitor's alone: the RUT, the terms box and the captcha. After it he fills a
  new patient's details as dictated (ringing *Registrarse* for the visitor),
  confirms an existing patient's, picks the motivo, the región, comuna and
  clínica, reads several days' hours (`booking_scan`), picks a day and an
  hour, and reads the review back, ringing *Confirmar cita*. The booking's
  state goes back to the brain as `booking_state` after every step, whoever
  took it.
- **Te llamamos** (`/landing/solicitar-diagnostico/`) and the **urgencias**
  page's form: he fills name, surname, email, phone, región and comuna; the
  visitor types the RUT and presses ENVIAR. `callback_form_state` reports it,
  Brevo's answer included.
- **Convenio Empresas** (`/landing/convenio-empresa/`): he fills it all; the
  visitor presses ENVIAR. `company_form_state` reports it.
- **A clinic's "¿Cómo llegar?"** on Google Maps opens in a new tab.

## What he never does

These are rules of the adapters (`src/guards.ts`), not of the prompt, so no
brain can lift them, and `test/guards.spec.ts` holds them:

- He never sends anything: no form's `.submit()` or `requestSubmit()`, no key
  event (so no Enter), and no press of the buttons that send or commit: the
  booking's *Continuar* after the RUT (`#ingresar-rut`), *Registrarse*
  (`#registro-paciente`, which creates a patient record), *Confirmar cita*
  (`#confirma-cita`), Brevo's ENVIAR, Contact Form 7's submit, the help desk's.
  He rings the button; the visitor presses it.
- He never types a **RUT** (the booking's `#rut`, Brevo's `#RUT`, any field
  named so), never ticks a box (the booking's terms `#conditions`, any
  consent), and never touches the captcha. He rings the field and asks.
- He never follows the payment link the booking may show at the end
  (`#container_link_pago`).
- The presses he may make on the booking only move it on: an existing
  patient's *Continuar* (`#actualiza-datos`, which only sends optional contact
  details), the motivo's and the clinic's *Continuar*, a day of the calendar,
  and an hour (which moves on to the review by itself).
- The service worker opens tabs only on `www.unosalud.cl`/`unosalud.cl` and
  Google Maps (`www.google.com/maps`).

## How the call lives through page loads

www.unosalud.cl is WordPress, with no client router: every move to another
page is a full page load (the booking's steps aside: they change in place).
The call therefore does not live in a page: it lives in an **offscreen
document of the extension** (`call.html`, `src/holder.ts`, "the holder"),
which no page load touches. This is the design of Clini's and the other
TargetGrid demos' extensions, copied with only the names changed.

- **The holder** runs stock pipecat on `@voqalize/client-transport`, plays his
  voice, keeps every open Uno Salud tab (by browser tab id: its port, where it
  is, whether it is in front) and sends the brain `tabs_changed`, routes each
  brain Action to the tab it belongs on, fires his cues as he speaks
  (`src/narration.ts`) and relays to the pages what they need to draw his face
  (`src/relay.ts`: pipecat's events, the avatar's sync channel, which the
  holder opens and says hello on, and the mouth clock).
- **Where each Action goes.** `navigate`, `fill_callback_form` and
  `fill_company_form` go to a tab of the site (any page but the booking): the
  one in front, else the one last in front, brought to the front, else a new
  one at the form's page. The booking Actions go to the booking's tab; if none
  is open, `open_booking` opens one at `/agenda-tu-hora/?promo=<code>` and the
  move is made there once its page is up. `show_section` and `open_faq` go to
  the tab in front. `open_link` opens its address in a new tab (Maps is not
  ours, so it is not in the registry). For 10 s after a move on the booking, a
  cue to another page of the site is dropped rather than pulling the visitor
  off it.
- **Every page is a follower** (`src/content.ts`): the widget, his face (the
  unchanged avatar against a stand-in client fed by the relay,
  `src/follow.ts`), the site adapter, and the moves the holder sends it. It
  reports what it shows up the port; a move's outcome and the forms' state
  reach the brain from any tab, the rest from the tab in front. The stand-in
  carries the relayed mouth clock forward to each read of it, for at most
  100 ms (`src/mouth-clock.ts`), and a face made in the middle of a reply asks
  the holder for the reply so far (`src/catch-up.ts`), never its start
  (`at_ms` 0). Each page keeps one port to the holder (`src/bridge.ts` in the
  isolated world, `src/hub.ts` in the page's world).
- **The service worker** (`src/background.ts`) makes the holder on the first
  press of the call button, with the reasons `USER_MEDIA` and `WEB_RTC`, one at
  a time, tells every Uno Salud tab when it is up (`holder-up`), opens and
  focuses tabs for his moves, and keeps the language choice.
- **The session is minted by the page.** On the call button the page calls
  `sessions.connect` with the publishable key (its fetch carries the site's
  Origin, which the key allows) and hands the answer to the holder.
- **A move for a page that is loading waits for it**, and a move that itself
  loads a page finishes there (the adapter's `sessionStorage` leftover).
- **Links to the booking, in a call.** An in-page "Agenda tu hora" link that
  would load the booking in the same tab opens a new tab instead, as
  `open_booking` does: the brain expects the booking in a tab of its own.
  Off a call the site behaves as it always does.
- **The call ends** on End (any tab), when the call drops, or when no Uno Salud
  page has been open for 15 s (a visitor who keeps only a Maps tab ends it
  that way). Reloading or updating the extension ends it too.

## The widget across a page load

As on Clini: while a call is on, the page keeps the widget's picture in the
tab's `sessionStorage` (`src/persist.ts`, `voqalize.unosalud.call`), and
`shell.js` (`src/shell.ts`, the page's world, `document_start`) mounts it again
at once on the next page, with its card, status and buttons, and an empty slot
where his face goes until the live face has drawn and fades in, already moving
with the reply. Both pages opt in to a cross-document view transition
(Chrome 126+), under which the widget stays where it is. Every page of the
site is one origin, so every load in a call gets the early widget (a hop
between `www.` and the bare `unosalud.cl` would not).

## The site's headers (`rules.json`)

The site's pages send an enforced `Content-Security-Policy` whose allow-lists
(`script-src`, `connect-src`, `frame-src`) name none of our hosts, and a
`Permissions-Policy` with `microphone=(self)`. The booking sends a loose CSP
(`default-src 'self' https: data: 'unsafe-inline' 'unsafe-eval'`) and
`microphone=()`. `content.js` runs in the page's own world, so the page's
policy binds it:

- its mint of the session (`connect-src`), and his face's runtime, imported
  from the avatar's host (`script-src`), and that runtime's own fetches, would
  be refused on every page but the booking;
- the extension's grant frame could not use the microphone on any page.

`rules.json` is a `declarativeNetRequest` rule set, for the visitor who
installed this preview, on this site only, on its documents only
(`main_frame`):

1. On every page of `unosalud.cl`: it **removes** the CSP (and any
   report-only one), and **sets** the Permissions-Policy to the site's own
   list with the extension added to `microphone`
   (`microphone=(self "chrome-extension://<id>")`).
2. On the booking, ahead of rule 1: it **keeps** the booking's own CSP (it
   allows any `https:` host already) and sets
   `geolocation=(), camera=(), microphone=("chrome-extension://<id>")`: the
   page itself still has no microphone, the extension's frame does.

Where a page's policy keeps the frame from the microphone anyway, the frame's
ask fails at once and the grant opens in a tab of its own (below).
`test/headers.spec.ts` serves the saved pages over HTTPS with the live site's
headers and checks all of it, with a negative control (the rules switched
off: the mint, the face's runtime and the frame are refused, and the grant
tab takes over). The `<id>` in `rules.json` is this extension's fixed id.

## The microphone, once

The microphone is the extension's, not the site's: Chrome keeps the permission
against `chrome-extension://<id>`, and an offscreen document cannot show a
prompt. On each press of the call button the page asks the holder for the
extension's permission state:

- **granted**: the call starts.
- **prompt** (the first call): the widget shows the extension's own page
  `grant.html` in a frame (`<iframe allow="microphone">`), which asks at once;
  Chrome's prompt names the extension ("Javier para Uno Salud Dental — Voqalize
  preview"). Should the grant still not hold, `grant.html` opens once in a tab
  of its own, asks the same way, and closes itself once answered.
- **denied**: the widget says Chrome blocks the microphone for the extension,
  with a button that opens `chrome://settings/content/microphone`.

For a headless live run, seed the grant before launch by writing
`<profile>/Default/Preferences` =
`{"profile":{"content_settings":{"exceptions":{"media_stream_mic":{"chrome-extension://ohogdknmaklhlnkbcemmhhejadjlfibd,*":{"last_modified":"13400000000000000","setting":1}}}}}}`.

**His voice plays from the extension, not from the tab.** Muting the tab does
not silence him; the widget's *Silenciar* mutes the visitor's microphone, and
*Colgar* ends the call.

## What is in it

- `src/unosalud-actions.ts` — the site adapter: `navigate`, `show_section`,
  `open_faq`, `fill_callback_form`, `fill_company_form`, and the reports
  (`page_changed` with the page's kind, the catalogue's places and FAQs on it,
  its form, and on `/clinicas/<slug>/` the clinic's name, address, hours,
  references and "¿Cómo llegar?" link read from the page;
  `callback_form_state`, `company_form_state`). Places are found by the
  catalogue's selector, and by their heading words where it matches none or
  several (the theme repeats ids). A price pane is shown by its pill, an FAQ
  by its question (Bootstrap collapse: open is `.show`; its `aria-expanded` is
  wrong), a landing's accordion by its summary, a Flickity cell by pausing the
  carousel and selecting it, a clinic in `/clinicas/`'s list by scrolling the
  list. The Brevo forms' helpers wait for LiteSpeed's delayed scripts, which
  one `mousemove` wakes; the región's comunas load on its click.
- `src/booking-actions.ts` — the booking adapter (`open_booking`,
  `fill_booking_patient`, `booking_pick`, `booking_scan`, and `booking_state`):
  the step read off the fieldset showing (else `#step`), values set with
  native events (jQuery listens to those), the phones typed digit by digit
  into IMask's `+{56}0 0000 0000`, the calendar turned by its header arrows and
  a day pressed by its cell, an hour by its `.option_hora`.
- `src/catalogue.ts` — the brain's catalogue of places,
  `../backend/knowledge/L3/anchors.json`, bundled in by `build.mjs` (keys,
  their page, selector, heading words and FAQ ids).
- `src/guards.ts` — what he never presses or fills (above).
- `src/anchors.ts`, `src/anchor.ts` — Chrome's translator kept off what the
  adapters match on (headings, FAQ questions, the booking's lists, calendar,
  hours and review, the forms' region lists), and a clinic page's facts read
  before any translation. The owner tests with Chrome's translation on.
- `src/page.ts` — what both adapters share: the waits, the scroll under the
  header (121 px once fixed; 73 px on the landings), inside a list that
  scrolls by itself, the ring in Uno Salud's orange, the native-setter fill
  and the masked typing.
- `src/holder.ts`, `src/call.html`, `src/call-client.ts`, `src/relay.ts`,
  `src/follow.ts`, `src/mouth-clock.ts`, `src/catch-up.ts`, `src/narration.ts`,
  `src/protocol.ts`, `src/bridge.ts`, `src/hub.ts`, `src/background.ts`,
  `src/grant.ts`, `src/grant.html`, `src/shell.ts`, `src/persist.ts` — the call
  across page loads (above), as on Clini.
- `src/widget.ts` — the widget, in a shadow root, in Uno Salud's cyan and deep
  blue: bottom-left (the right edge has the site's tab stack), moving clear of
  that stack and of a form he is filling. The widget is never translated.
- `src/content.ts` — the page: the widget, his face, the adapter, the moves
  the holder sends, and on the call button the microphone check and
  `sessions.connect` (`surface: "unosalud-ext"`).
- `src/actions.gen.ts` — the Action and event unions, generated from the brain
  with `pnpm gen`. Regenerate after changing either.
- `rules.json` — the header rules (above).

The brain is `../backend/`: the prompt, the tools, and Uno Salud's knowledge.

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
origins are the site's (`https://www.unosalud.cl`, `https://unosalud.cl`),
because the page mints the session.

**The extension id is fixed: `ohogdknmaklhlnkbcemmhhejadjlfibd`.**
`manifest.json` carries a `key` (an RSA public key; it is not a secret), so the
unpacked extension has the same id from any folder and on any machine, the
microphone grant made once holds across rebuilds, and `rules.json` can name
it. The private key is not in the repo and is not needed to load unpacked.
`dist/` and `dist-prod/` share the id: load one of them at a time.

## Tests

```sh
pnpm test:e2e
```

Playwright, headless, and nothing leaves the machine (the browser resolves
every other name to nothing):

- `test/holder.spec.ts` — the call across page loads, with a stand-in call
  (`test/fake-call-client.ts`) and a stand-in avatar, pages served by
  Playwright's routes: the port protocol, a full page load (to the booking
  too) with a move made on the next page, `open_booking` opening the booking's
  tab with its promotion, the 15 s rule, the microphone's branches, the widget
  across a load, his mouth clock on a busy page, a load in the middle of a
  reply, and his face's slot during a held load. `test/mouth-clock.spec.ts`
  and `test/catch-up.spec.ts` cover those modules alone.
- `test/headers.spec.ts`, `test/site.spec.ts`, `test/booking.spec.ts`,
  `test/forms.spec.ts`, `test/guards.spec.ts` — the saved pages
  (`demos/unosalud/fixtures/`) over HTTPS at the site's address from a local
  server (`test/server.ts`) with the live site's headers, so the header rules
  act on them; stand-ins for the site scripts the saved pages lack
  (`test/fake-dentalsoft.js` with the real IMask, `test/fake-brevo.js`) and for
  the stylesheet rules the adapters see (`test/site.css`).

The brain's own e2e is `demos/tests/test_unosalud_e2e.py`.

## What only a live run can show

The live site was not reachable while this was built, so these were checked
against the saved pages and stand-ins only: the booking's real server answers
after the RUT (regions, hours, `promosDiarias`, the review), the real
Bootstrap, Flickity and LiteSpeed scripts, Brevo's real panels, and the real
layout (the header's height, the clinic list's scroller). Run a call through
it on dev with the owner's VPN before showing it, and never submit anything.

## Driving it from the console

With no call, on a Uno Salud page:

```js
await __voqalizeUnosalud.perform("show_section", { anchor: "home_testimonios", text: "" });
await __voqalizeUnosalud.perform("navigate", { path: "/clinicas/moneda/", anchor: "clinica_horario", text: "", faq: "" });
await __voqalizeUnosalud.perform("open_faq", { faq: "faq_pad" });          // on /preguntas-frecuentes/
// on /agenda-tu-hora/, after the visitor's RUT step
await __voqalizeUnosalud.perform("booking_pick", { motivo: 22, region: "", comuna: "", sucursal: "52", date: "", time: "" });
voqalizeUnosalud.context();
```

When you test the booking by hand, use obviously fake data, and never press
*Registrarse*, *Confirmar cita* or ENVIAR.
