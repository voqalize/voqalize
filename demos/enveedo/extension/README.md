# Javier for Enveedo — the extension

A Chrome extension that puts Javier, a voice guide, on
[enveedo.com](https://enveedo.com), the site of Enveedo, a security program
management platform (risk, compliance, audit and reporting in one place, for
CISOs, IT and security teams, and the MSPs and MSSPs who serve them). He talks
a security leader through Enveedo in English or Spanish while their screen
follows his voice: he opens the page that answers them, scrolls to the exact
place and rings it, opens the site's own tabs, accordions and Without/With
toggle to show what they hide, finds a framework among the 39 on /frameworks,
opens gated eBooks, webinars, blog posts and the platform PDF in a new tab,
drives the demo scheduler on /book-a-demo (length, day, time, name and email),
and fills in the contact form or the SOC 2 report request as the visitor
dictates it. The visitor ticks the consent box and presses Submit, or Confirm,
themselves. One call follows the visitor across every tab of the site they
have open and every page they move to, and his voice carries on through each
page load. Everything he shows is a page, place, link, form or scheduler the
site already has; the extension adds a corner widget and the ring he draws
around what he is pointing at.

This is how we show the agent to Enveedo on its own site, before anything goes
on it; it is not how a customer would ship it.

## What is in it

- `src/enveedo-actions.ts` — the site adapter. It performs the brain's page
  Actions on the tab in front (`navigate`, `show_section`, `fill_form`,
  `book_demo`, and the holder's `site_language`) and reports every page the
  visitor lands on, whoever took them there (`page_changed`: its path, its
  language, its kind, the places of the catalogue it shows, the form or
  scheduler it holds). The site is HubSpot CMS with no client router, so a
  move to another page is a full page load; the adapter keeps what is left of
  the move (the place, a whole form fill, a booking) in `sessionStorage` and
  makes it once the next page is up. A place the site hides behind its own
  control carries `reveal: {click, open}` in the catalogue: the control is
  clicked unless the place is already open, then the place is rung. It scrolls
  with a 90 px offset for the sticky header. It also follows the visitor in
  the HubSpot forms (their typing, and HubSpot's thank-you or its errors once
  they press Submit) and relays the scheduler frame's reports.
- `src/meetings.ts` (`meetings.js`) — inside the HubSpot Meetings frame on
  /book-a-demo (`meetings.hubspot.com`, `all_frames`), and only when the page
  holding it is enveedo.com. It reports where the booking is (`demo_state`:
  loading, the calendar's open days as ISO dates, the chosen day's times as
  "10:30am", the lengths, the timezone, the details filled and missing) on
  every change, and takes `book` orders from the page over `postMessage`
  (length, day, time, first name, last name, email). The frame's language
  follows the visitor's browser, not the page, so it matches HubSpot's test
  ids, ARIA state, `data-timestamp` and i18n keys, never visible words. It
  never presses Confirm, and while `DEMO_BLOCK_SUBMIT` is on it stops the
  visitor's own press and reports it (`demo_scheduled`, `blocked: true`).
- `src/site-language.ts` — the site follows the call's language. English at
  `/…`, Spanish at `/es/…` under the same slugs (except `/book-a-demo-grl` ↔
  `/es/book-a-demo-rsa`; `/webinars-and-ebooks` has no Spanish page): a static
  map, with the page's own `hreflang` link as the fallback. The brain names
  English paths; in a Spanish call the Spanish twin loads. During a call the
  page's same-site links are pointed at the call language's twin (the site's
  own cross languages: the English header's "Platform" leads to /es/, the
  Spanish "Agenda una Demo" to the English page) and a same-site link that
  would open a new tab stays in the tab. The site's own language switcher is
  left alone.
- The catalogue of places, `../backend/knowledge/L3/anchors.json`, bundled in
  (`catalogue.mjs`; `src/anchors.stub.json`, the same shape, stands in while
  it is missing): every page under its English and its Spanish path with the
  same keys, a HubSpot module id per place with the section's row as
  `fallback`, each checked on the live site by
  `../backend/knowledge/build.py`. A key resolves on the page in front, by
  that page's own entry.
- `src/anchors.ts`, `src/anchor.ts` — headings are kept out of Chrome's
  translator from `document_start`, so a `text` move still matches for a
  visitor reading the site translated.
- `src/narration.ts` — the screen follows his voice. The brain sends each
  screen cue he wrote into his reply ahead of the speech, with the first words
  of the sentence it belongs to; this fires it when the call's spoken-text
  events reach those words (or their first words, when an acronym is spelled
  differently in the two), one move at a time. A cue to another page fires at
  once, so the load overlaps his reply. It runs in the holder, so a load ends
  nothing.
- `src/holder.ts`, `src/call.html` — the holder: the call, his voice, the tab
  registry, the routing of each Action, the moves kept for loading tabs, the
  language switch of the page in front, the 15 s rule (below);
  `src/call-client.ts` makes the pipecat client and reads the microphone
  permission.
- `src/relay.ts`, `src/follow.ts` — what crosses from the holder to the pages
  for his face, and the stand-in client the avatar draws against.
- `src/protocol.ts` — the messages between the pages, the holder and the
  service worker.
- `src/bridge.ts`, `src/hub.ts` — the page's port to the holder and its
  requests of the service worker.
- `src/background.ts` — the service worker: makes the holder, opens and
  focuses tabs for his moves (only the site, its PDFs, and the hosts its pages
  send a visitor to: info.enveedo.com, blog.enveedo.com, app.enveedo.com,
  meetings.hubspot.com and YouTube), opens the microphone grant tab, keeps the
  language choice.
- `src/grant.ts`, `src/grant.html` — the extension's one-time microphone
  grant (below).
- `src/widget.ts` — the corner widget, in a shadow root, in Enveedo's navy and
  violet: the call and the English/Español toggle, its words in the toggle's
  language. Javier also switches by himself when the visitor speaks the other
  language, and the toggle follows him. It sits bottom-left (HubSpot's chat
  launcher holds the bottom-right) and moves out of the way of the cookie
  banner, the chat launcher and a form while he fills it. It also holds the
  grant frame and the "microphone blocked" message.
- `src/shell.ts`, `src/persist.ts` — the early shell, what a page in a call
  leaves for the next one, and the view transition (below).
- `src/content.ts` — the page: the widget, his face, the adapter, the moves
  the holder sends, and on the call button the microphone check and
  `sessions.connect` (`surface: "enveedo-ext"`, with `site_lang`, `lang` when
  the visitor chose one on the toggle, and `tz`, the browser's time zone, the
  one the scheduler shows its times in).
- `src/actions.gen.ts` — the Action and event unions, generated from the brain
  with `pnpm gen`. Regenerate after changing either.
- `test/entry.ts`, `test/bundle-page.mjs` — the bundle
  `demos/tests/test_enveedo_page.py` runs in headless Chromium against saved
  copies of the site's pages (`../fixtures/`). Never shipped.
- `test/holder.spec.ts`, `test/meetings.spec.ts` — the holder and its pages,
  and the scheduler's frame script, end to end in a test build of the
  extension (below). Never shipped.

The brain is `../backend/`: the prompt, the tools, and Enveedo's knowledge.

## Build and load

```sh
cp .env.example .env     # the agent id and a publishable key (see below)
pnpm install --ignore-workspace
pnpm gen                 # after any change to the brain's Actions or events
pnpm build               # → dist/
```

Then `chrome://extensions` → Developer mode → **Load unpacked** → `dist/`, and
open enveedo.com. The first call asks for the extension's microphone (below).
`pnpm build:prod` builds the same extension against production into
`dist-prod/`, from `.env.prod`.

The publishable key's allowed origins must include `https://enveedo.com` and
`https://www.enveedo.com`, which are where the session is minted from: the
page mints it, not the extension. The agent id and key are baked into the
bundle at build time and are never committed: this repo is public.

The call opens in English, or in Spanish when it starts on an /es/ page. A
visitor who presses Español on the toggle before the call starts gets the call
in Spanish, and keeps it whatever they speak, until they ask for the other.

The site sends no `Content-Security-Policy` beyond `upgrade-insecure-requests`
and no `Permissions-Policy` (checked on every page, 2026-10-28), so the grant
frame's `allow="microphone"` needs no header rule. If the microphone cannot
open, the widget says so and ends the call rather than showing "live".

**The extension id is fixed.** `manifest.json` carries a `key` (an RSA public
key; it is not a secret), so the unpacked extension has the same id from any
folder and on any machine, and the microphone grant made once holds across
rebuilds and moves. The private key is not in the repo and is not needed to
load unpacked (only to pack a `.crx`). `dist/` and `dist-prod/` share the id:
load one of them at a time.

The build works with no agent id or key. With an empty `.env` it warns, and
the extension loads with everything but the call: the widget and every page
Action still work from the console (below).

## Driving it from the console

With the extension loaded, every page Action can be sent exactly as the brain
would send it, from the page's DevTools console, with no call:

```js
// On the home page: the "How Enveedo Works" tab on automation, opened and rung.
await __voqalizeEnveedo.perform("show_section", { anchor: "how_automation", text: null });
// A framework card, from any page: /frameworks loads first.
await __voqalizeEnveedo.perform("navigate", { path: "/frameworks", anchor: "fw_nis2", text: null });
// The contact form, filled; nothing is sent: the visitor ticks consent and presses Submit.
await __voqalizeEnveedo.perform("fill_form", {
  form: "contact", firstname: "Carolina", lastname: "Rojas", email: "carolina@acme.com",
  phone: "+56 9 1234 5678", country: "Chile", company: "Acme", job_title: null,
  message: "We need ISO 27001 and Chile's 21.719.",
});
// The scheduler: /book-a-demo loads, then a day, a time and the details.
await __voqalizeEnveedo.perform("book_demo", {
  duration: "30 mins", day: "2026-11-04", time: "10:30am",
  first_name: "Carolina", last_name: "Rojas", email: "carolina@acme.com",
});
```

A move that could not be made comes back as the `command_failed` the brain
would receive, with the reason in words the model can act on: a place that is
not on the page lists the ones that are, a time the scheduler does not offer
lists the ones it does. A fill or a reveal comes back as the `command_done`
the brain would receive, with what it did; what the forms and the scheduler
report goes to the brain as events once the call is on; from the console,
`window.voqalizeEnveedo.start(console.log)` prints them, and
`window.voqalizeEnveedo.setCall(true, "es")` plays a Spanish call (links and
moves go to the Spanish twins).

## How the call lives through page loads

The site has no client router: every move to another page (the platform, the
frameworks, the contact form, the scheduler) loads a whole page. The call
therefore does not live in a page: it lives in an **offscreen document of the
extension** (`call.html`, `src/holder.ts`, "the holder"), which no page load
touches.

- **The holder** runs stock pipecat on `@voqalize/client-transport`, plays his
  voice, keeps every open Enveedo tab (by browser tab id: its port, where it
  is, whether it is in front) and sends the brain `tabs_changed`, routes each
  brain Action to the tab it belongs on, fires his cues as he speaks
  (`src/narration.ts`) and relays to the pages what they need to draw his face
  (`src/relay.ts`: pipecat's events, the avatar's sync channel, which the
  holder opens and says hello on, and the mouth clock).
- **Where each Action goes.** A move on a page (a place) goes to the tab in
  front. A move that may open another page (a page, a form fill from a page
  without the form, a booking) goes to a site tab: the one in front, else the
  visitor's other site tab, brought to the front, else a new one (in the
  call's language), which makes the move once it is up. A gated eBook, a
  webinar, a blog post or the PDF opens in a tab of its own, through the
  service worker; the extension does nothing on that tab and it never joins
  the tab list.
- **The language.** `language_changed` moves the toggle on every tab; with
  `site: "follow"` the page in front loads its twin once he has said the
  switch (else that language's home page), with `"twin"` its own twin only (a
  failure is reported), with `"stay"` nothing moves.
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
  holds what arrives and then hands it over in order. Each page keeps one port
  to the holder (`src/bridge.ts` in the isolated world, `src/hub.ts` in the
  page's world).
- **The service worker** (`src/background.ts`) makes the holder on the first
  press of the call button, with the reasons `USER_MEDIA` and `WEB_RTC` (they
  keep the document alive through any silence; `AUDIO_PLAYBACK` alone closes
  it after 30 s without sound), one at a time, and tells every Enveedo tab
  when it is up (`holder-up`): a port opened before the holder existed has no
  one at the other end, so pages open theirs on that word. It also opens and
  focuses tabs for his moves (an offscreen document has no `chrome.tabs`) and
  keeps the language choice.
- **The session is minted by the page.** On the call button the page calls
  `sessions.connect` with the publishable key (its fetch carries the site's
  Origin, which the key allows; a `chrome-extension://` origin cannot be added
  to a publishable key) and hands the answer to the holder, which connects.
- **A move for a page that is loading waits for it.** When a page starts
  loading another document it tells the holder (`leaving`); a move sent to
  that tab meanwhile is kept and delivered when the next page says `hello`, for
  up to 75 s. A move that itself loads a page finishes there (the adapter's
  `sessionStorage` leftover, as before).
- **The scheduler's frame.** HubSpot's loader makes the meetings frame only
  after the page's `load` event, which a slow third-party tag can hold back
  for a minute. When the frame has not appeared about 6 s after the load, the
  adapter makes it itself in `.meetings-iframe-container`, with HubSpot's own
  embed address and the page's address, so a booking never hangs.
- **The call ends** on End (any tab), when the call drops, or when no Enveedo
  page has been open for 15 s; the holder then closes. A tab Javier opened off
  the site does not count: if the visitor closes every Enveedo tab, the call
  ends 15 s later. Reloading or updating the extension ends it too.

## The widget across a page load

The call outlives a page load, and in a call the widget does too, as near as a
page can: it is back the moment the next page shows, not once the page has
parsed and the site's scripts have run.

- **What the page leaves.** While a call is on, `content.js` keeps a picture of
  it in the tab's `sessionStorage` (`src/persist.ts`): live or connecting,
  muted or not, the status line, the language, where the visitor put the widget
  and whether it is minimised, and the character's still for the invite. No
  picture of his face is kept. It is taken away when the call ends, and is
  stale after 60 s.
- **The early shell.** `shell.js` (`src/shell.ts`) runs in the page's world at
  `document_start`, before any of the page's scripts. Off a call it reads that
  one key and does nothing else. In a call it mounts the widget on `<html>` at
  once, as the last page left it: the card, the status line and its buttons,
  so the visitor can always mute or end the call. Where his face goes there is
  nothing, no picture of him, while the page loads: his face returns when the
  live face has drawn, and his voice never stops. `content.js` (still at
  `document_idle`) adopts that widget instead of mounting another, asks the
  holder for the call's state as before, starts building his face at once
  (`preloadAvatar`), and fades the live face in once it has drawn, already
  moving with the reply he is in the middle of (the catch-up). Should the
  holder be gone (no holder, or no word from it in 8 s), the carried widget
  goes back to the invite.
- **The view transition.** In a call both pages opt in to a cross-document
  view transition (`@view-transition { navigation: auto }`, Chrome 126+): the
  page that leaves (`content.js`, while a call is on) and the page that arrives
  (`shell.js`, from what was kept). The widget's host has its own
  `view-transition-name` (`voqalize-javier`), so the page fades under it in
  150 ms while it stays where it is. Older Chrome ignores the rule and loads
  the page as before, with the widget still up early. Off a call no transition
  is asked for. `www.enveedo.com` and `enveedo.com` are two origins, so the
  first page after a move between them gets no early widget
  (`sessionStorage` is per origin); the call is unaffected.

## The microphone, once

The microphone is the extension's, not enveedo.com's: Chrome keeps the
permission against `chrome-extension://<id>`, `chrome.contentSettings` cannot
set it for that origin, and an offscreen document cannot show a prompt. So, on
each press of the call button, the page asks the holder for the extension's
microphone permission state first:

- **granted**: the call starts.
- **prompt** (the first call): the widget shows the extension's own page
  `grant.html` in a frame (`<iframe allow="microphone">`), which asks at once.
  Chrome's prompt names the extension ("Javier for Enveedo" wants to use your
  microphone); the visitor chooses *Allow*. The holder then reads the state
  again: granted, the call starts. Should it still not be granted (the grant
  was stored for the site rather than the extension, or it was *Allow this
  time*), `grant.html` opens once in a tab of its own, asks the same way,
  closes itself once answered, and the call starts.
- **denied**: the widget says Chrome blocks the microphone for the extension,
  with a button that opens `chrome://settings/content/microphone`, where the
  visitor takes the extension off the blocked list.

## What the visitor sees

The first time: the press, then Chrome's microphone prompt naming the
extension under the widget (and, only if that grant does not hold, a short-
lived tab with the same prompt), then Javier. After that, the press and
Javier. Pages load as they always do; the widget comes back on each new page
already live, his voice carries on across the load, and the moves he started
finish on the page they land on.

**His voice plays from the extension, not from the tab.** Muting the tab
(right-click → Mute site) does not silence him; the widget's *Mute* mutes the
visitor's microphone, and *End call* ends the call. Chrome shows the
microphone in use for the extension rather than for the tab.

## What is never done

**The visitor ticks consent and presses Submit.** Javier fills the contact
form (name, last name, business email, phone, the country by its exact
option, "Others" when theirs is not listed, the organization, and a short
message he writes from the conversation) or the SOC 2 report request (name,
company, job title, corporate email, a description), field by field, with the
native value setter and the events HubSpot's React form listens for. Nothing
here can send a form or tick a box: there is no `submit()`, no
`requestSubmit()` and no click on a form's button or checkbox anywhere in the
source (`demos/tests/test_enveedo_page.py` checks), and no Action that could
ask for one. The invisible reCAPTCHA runs on the visitor's own press. Once
every field Javier may type is in, the consent box and Submit are rung for the
visitor. The newsletter and eBook forms are never filled.

**The visitor presses Confirm, and in this preview it books nothing.** Javier
chooses the length, the day and the time the scheduler lists and fills in the
first name, last name and email; the frame script never presses Confirm, and
while `DEMO_BLOCK_SUBMIT` is on (it is, in `src/meetings.ts`) the visitor's own
press is stopped before HubSpot sees it and reported to the brain, so no real
meeting reaches Enveedo's calendar.

**The cookie banner is the visitor's.** Its Accept and Decline are never
pressed. Sign In (app.enveedo.com) only opens, for a customer who asks. A
password and payment details are never asked for or typed.

## Tests

```sh
pnpm test:e2e
cd ../.. && uv run --with playwright pytest tests/test_enveedo_page.py -q
```

`pnpm test:e2e` builds a test copy of the extension (`VOQALIZE_TEST_BUILD=1`,
into `test/.build/ext`: a stand-in call in the holder, a stand-in avatar, a
made-up API) and runs in headless Chromium `test/holder.spec.ts` (the port
protocol, a full page load that leaves the call alone and a move made on the
next page, the links pointed at the call language's twins, a form fill from a
page without the form made on /contact with consent and Submit untouched, a
gated eBook in its own tab, the 15 s rule, the microphone's three branches,
and the widget across a load) and `test/meetings.spec.ts` (the scheduler's
frame script against the saved frame in `../fixtures/meetings/`: its reports,
a booking through the adapter, a time it does not list, the visitor's Confirm
stopped, and nothing done off enveedo.com). The page test runs the site
adapter against saved copies of the site's pages, English and Spanish
(`../fixtures/fetch.py` saves them, gently), and checks every event it sends
parses as the brain's.
