# Javier para Clini — the extension

A Chrome extension that puts Javier, a voice guide, on
[www.clini.cl](https://www.clini.cl) and its online booking,
[agenda-web.clini.cl](https://agenda-web.clini.cl). He talks a visitor through
the site in Spanish or English while he moves their screen: he opens the page
that answers them, scrolls to the exact section and rings it, and opens an FAQ.
One call follows the visitor across every Clini tab they have open, on both
hosts. Everything he shows is a page, section or FAQ Clini already has; the
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
- The hub opens tabs only on Clini's hosts and the services the site links:
  `*.clini.cl`, `agendamiento.reservo.cl`, `app.dalca.cl`,
  `patientportal.prod.clini.procloudhub.com`, `clini.medipasspro.com`,
  `wa.me` and `api.whatsapp.com`.

## What is in it

- `src/clini-actions.ts` — the site adapter for www.clini.cl: `navigate`,
  `show_section`, `open_faq` and `fill_lasik_form`. The site is Webflow, and
  every move to another page is a full page load, so the rest of a move (a
  heading, an FAQ, the LASIK form) is left in `sessionStorage` and made on the
  next page. Sections are found by their words. Tabs, dropdowns (the FAQs and
  a sede's "Ver horarios"), the newer `.faq-item` accordion and slider slides
  are revealed by the same click a visitor would make.
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
- `src/narration.ts` — the screen follows his voice: each cue fires when the
  call's spoken text reaches the first words of its sentence. A cue that loads
  another page hands the cues still to come to the next page.
- `src/hub.ts`, `src/bridge.ts`, `src/background.ts` — the hub. A
  `BroadcastChannel` and a Web Lock reach one origin, and Clini is two, so the
  call's relay runs through the extension's service worker: every tab's
  messages reach every other Clini tab, the call's claim is held by browser
  tab, and tabs Javier opens are opened by the worker.
- `src/tabs.ts` — Qween's one-call-every-tab relay, on the hub.
- `src/widget.ts` — the widget, in a shadow root, in CLINI's purple and pink:
  the call and the Español/English toggle. It sits bottom-left, because
  Clinito's chat owns the bottom-right. It moves up above the phone's bottom
  bar and above the chat wherever it would cover them. Off a call the toggle picks the language the next
  call starts in; in a call it asks the brain to switch. The choice is kept in
  the extension's storage, so it holds on both hosts. The widget is never
  translated ("Javier" stays Javier).
- `src/content.ts` — the call: stock pipecat with `@voqalize/client-transport`
  as its media manager, one `sessions.connect`, the avatar, and the routing of
  each Action to the tab it belongs on. `navigate` and `fill_lasik_form` go to
  a www tab. The agenda Actions go to the booking's tab: an open one is reused,
  and it loads the other service's page itself when the servicio differs. If
  none is open, the hub opens one at `?servicio=S&prestacion=P`, with the rest
  of the move made there. `open_link` goes to a new tab. The call stays with
  the tab it started in, and every other tab follows it. A call can start on
  agenda-web too. During a call, a link to another host that would load in the
  same tab opens a new one instead, because a load to another origin cannot
  carry the call.
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
`https://agenda-web.clini.cl`), because `content.js` runs in the page's world.

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
