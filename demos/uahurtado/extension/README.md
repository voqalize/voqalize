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
  them, one move at a time. A reply whose first cue is another page goes there
  at once; cues still owed when the page unloads go with it to the next page,
  on whichever host.
- `src/hub.ts`, `src/bridge.ts`, `src/background.ts` — the hub, in the
  extension's service worker. The three hosts are three origins, and
  `sessionStorage`, a `BroadcastChannel` and a Web Lock each reach one; so the
  call's relay, its claim, the move kept for the next page, the cues still owed,
  the transport's saved call and the call's language are all kept here, per
  browser tab. The worker also reads the site's own REST record of a career
  (`acf.aranceles_carrera`) or a programme (application window, start, requisitos)
  by slug, four seconds at most — the site answers CORS only for
  www.uahurtado.cl — and opens tabs for Javier, uahurtado.cl addresses only.
- `src/anchor.ts`, `src/anchors.ts` — from `document_start`, the elements the
  adapter matches on (headings, tab and accordion labels, the Carreras menu, the
  data and fee tables, visit cards, the lead form, the widget) are kept out of
  Chrome's translation, so a visitor who translates the page still gets every
  move. A page translated anyway is reported as `translated`.
- `src/tabs.ts` — Qween's one-call-every-tab relay, on the hub.
- `src/widget.ts` — the corner widget, in a shadow root, in the site's own
  orange, black and Rubik, bottom-left, clear of UserWay's accessibility button
  (bottom-right) and of the lead form while Javier fills it.
- `src/content.ts` — the call: stock pipecat with `@voqalize/client-transport`
  as its media manager, one `sessions.connect`, the avatar, and the routing of
  each Action to the tab in front, one at a time.
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
open admision.uahurtado.cl. The first call asks for the microphone; once a call
is live the extension allows it on all three hosts, so Chrome does not ask
again as the visitor moves between them. `pnpm build:prod` builds the same
extension against production into `dist-prod/`, from `.env.prod`.

The publishable key's allowed origins must include
`https://admision.uahurtado.cl`, `https://postgrados.uahurtado.cl` and
`https://www.uahurtado.cl`: the session is minted, and rejoined after every page
load, from whichever of them the visitor is on. The agent id and key are baked
into the bundle at build time and are never committed: this repo is public.

The call opens in Spanish, as the site does. A visitor who presses English on
the toggle before the call starts gets the call in English, and keeps it
whatever they speak, until they ask for the other; the choice holds on all three
hosts.

All three hosts send `Permissions-Policy: geolocation=(), microphone=(),
camera=()`, which forbids the microphone to the page and to this script with
it: a call would connect, the agent would speak, and hear nothing. `rules.json`
rewrites that header on the university's pages to `microphone=(self)` and
leaves the rest as it was, which is why the extension asks for
`declarativeNetRequest`. If the microphone still cannot open, the widget says so
and ends the call rather than showing "live".

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
// A narrated turn: cues as the brain sends them, then speech as the voice plays it.
const n = u.narration;
n.speaking();
n.add({ at: "en requisitos y aranceles", word: 0, url: null, heading: "Requisitos y Aranceles", text: null, faq: null });
n.hear("En Requisitos y Aranceles ves el arancel de 2027.");
```

Each call returns the event the brain would receive: `command_done` with what
is on screen now, `admission_read` / `program_read` with what was read, or
`command_failed` with the reason in words the model can act on (a heading that
is not on the page lists the ones that are).

A move that needs another page (`navigate`, or `show_admission` on a career
that is not in front) keeps itself with the hub and loads that page, so the
console's next line runs on a page that no longer exists; the move is made on
the new page once it is up.

## Forms are filled, never sent

`fill_lead_form` types what the visitor dictated into the site's own lead form
(`form#admisionForm`, in the header of every career page and on most admision
pages), field by field, the way typing would, so the form's own scripts see it.
It never types the RUT (with `focus_rut` it rings and focuses the field for the
visitor), never calls `submit()` or `requestSubmit()`, never presses "Enviar"
or Enter: once everything but the RUT is in, it rings "Enviar" for the visitor.
That form is a real lead in the university's admissions pipeline.

So a demo never sends one, the build has a flag: `UAHURTADO_BLOCK_SUBMIT` (`1`
or `0`, from the environment or `.env`; anything else fails the build). Unset,
every build stops the visitor's own press of "Enviar" (and Enter in a field),
says "Vista previa: este formulario no se envió" under the form and reports
`lead_submitted {blocked: true}`. With `0` the press goes through and reports
`lead_submitted {blocked: false}`. The build prints which it did.

The PAES simulator (simula.uahurtado.cl) opens in a tab of its own when Javier
offers it; the extension does not run there, and fills nothing: its form is a
lead too. A visit's "Inscribirse aquí" is rung, never followed: the sign-up is a
Google or HubSpot form the visitor opens themselves.

## One call, every tab, every host

The call belongs to the tab it started in. Every other UAH tab shows Javier's
face and the call's state and can mute or end it; the tab in front is the one he
sees and moves. While a call is live, a link to another page of the three sites
that would open a new tab loads in the call's tab instead.

Every move between pages is a full page load, and often a move to another
origin, mid-sentence. The page going away is not the end of the call: the next
page in the same tab, on whichever host, takes the saved call back from the hub
and rejoins the same session, and Voqalize holds the rest of his speech until it
is back and plays it then. The move he was making and the cues he had not
reached go with it, and the toggle keeps the call's language.

## The page test

`pnpm test:page` drives the adapter in headless Chromium against trimmed copies
of the university's pages (`demos/tests/fixtures/uahurtado/`), with a small
stand-in for Bootstrap and no network: tabs, pills, collapses, the Carreras
menu, the career sheet and its fees, the lead form and its submit guard, visit
cards, a programme's requisitos. It needs Chromium for `playwright-core`
already installed (it never downloads one). `demos/tests/test_uahurtado_extension.py`
runs it from the demos suite, and skips where Node, the extension's
`node_modules` or Chromium is missing.
