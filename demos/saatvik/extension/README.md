# Sunny for Saatvik — the extension

A Chrome extension that puts Sunny, a voice solar advisor, on
[www.saatvikgroup.com](https://www.saatvikgroup.com) in place of the site's chat
launcher. She talks a visitor through Saatvik's modules, inverters and rooftop
kits while she moves their pages: she opens a page, rings the section or the
table row she is talking about, opens the FAQ that answers the question, opens a
datasheet or policy PDF at the page and line she quotes, runs the savings
calculator, filters the dealer locator, and fills in the enquiry form with what
the visitor has told her. Everything she shows is a page, section or form Saatvik
already has; the extension adds a corner widget, a document tab, and the orange
ring she draws around what she is pointing at.

Behind the conversation the brain builds the brief Saatvik's sales team would
receive — a score, the reasons for it, where the lead would be routed, and what
was asked — from what the page and the enquiry form tell it, never from a tool
call inside a reply. The visitor does not see it: the widget shows it only when
the brain's `SHARE_BRIEF` is on, for a pitch that shows the other half of the
product.

This is how we show the agent to Saatvik on their own site, before anything goes
on it; it is not how a customer would ship it.

## What is in it

- `src/saatvik-actions.js` — the site adapter. It performs each of the brain's
  page Actions through the site's own router and its own form fields and
  controls, and reports every route change, calculator result, dealer list and
  enquiry SUBMIT back to the brain, whoever caused it. Its Action names mirror
  the Action classes in `../backend/brain.py`. It also hides the site's own chat
  launcher and moves the WhatsApp button to the bottom-left corner, so neither
  sits under the widget.
- `src/narration.ts` — the screen follows her voice. The brain sends each
  screen cue she wrote into her reply (`{page: …}`, `{show: …}`, `{tab: …}`,
  `{faq: …}`) ahead of the speech, with the first words of the sentence it
  belongs to; this fires it when the call's spoken-text events (`bot-output`,
  released as the audio plays) reach those words, one move at a time. Words
  are Latin letters and digits or Devanagari, so a Hindi reply's cues fire on
  its own words. With no spoken text, it times cues from the start of the
  speech instead; when the visitor talks over her, the rest is dropped. This
  is SendPotion's narration, unchanged but for the Hindi words.
- `src/actions.gen.ts` — the Action and event unions, generated from the brain
  with `pnpm gen`. Regenerate after changing either.
- `src/doc.html`, `src/doc.ts`, `src/pdf-viewer.ts` — the document tab. Sunny
  opens one of Saatvik's PDFs in a tab of its own, beside the Saatvik tab the
  call is in, at a page, with the quote she reads from it marked; the next
  document reuses that tab, and its "Back to Saatvik" button returns to the
  call's tab. The call stays in the Saatvik tab, which keeps playing her voice
  and hearing the visitor in the background; before any move on the site the
  page brings itself back to the front (`focus_me`), so the visitor sees it
  happen. Until 2026-10-28 the viewer was an overlay over the page, which the
  visitor had to close by hand before she could show anything else.
  The viewer renders with pdf.js and its own text layer, so the mark sits on the words.
  A quote is looked for on the asked page first, then on the pages either side
  of it, and a quote the model tidied up still lands on its opening or closing
  words. "Open full PDF" opens Saatvik's own file at the same page. Some of
  Saatvik's datasheets are drawn with their text as outlines; those open at the
  page but have nothing to mark.
- `src/background.ts`, `src/bridge.ts`, `src/tabs-protocol.ts` — the service
  worker, which opens, reuses, focuses and closes the document tab (a page
  cannot), and the isolated content script that carries the page's asks to it:
  the page script runs in the page's own world, which has no `chrome.runtime`.
- `src/widget.ts` — the corner widget, in a shadow root, in Saatvik's own navy,
  orange and typefaces: the call, an English | हिंदी toggle, and the lead
  brief when the brain sends it, which can be collapsed. The visitor can drag it anywhere and minimise
  it to Sunny's face with the call still live.
- `src/content.ts` — the call: stock pipecat with `@voqalize/client-transport`
  as its media manager, one `sessions.connect`, the avatar, and the glue
  between the adapter, the viewer, the widget and the brain.

The brain is `../backend/`: the prompt, the tools, the lead brief and Saatvik's
published knowledge.

## Build and load

```sh
cp .env.example .env     # the agent id and a publishable key for Saatvik's site
pnpm install --ignore-workspace
pnpm build               # → dist/
```

Then `chrome://extensions` → Developer mode → **Load unpacked** → `dist/`, and
open www.saatvikgroup.com. The first call asks for the microphone.
`pnpm build:prod` builds the same extension against production into
`dist-prod/`, from `.env.prod`.

The publishable key's allowed origins must include
`https://www.saatvikgroup.com` and `https://saatvikgroup.com`, which are where
the session is minted from. The agent id and key are baked into the bundle at
build time and are never committed: this repo is public.

Saatvik's pages send `Permissions-Policy: microphone=()`, which forbids the
microphone to the page and to this script with it: a call connects, the agent
speaks, and hears nothing. `rules.json` rewrites that header on Saatvik's pages to
`microphone=(self)` and leaves the rest of their policy as it was, which is why
the extension asks for `declarativeNetRequest` on those hosts. A real embed on
their site needs the same change made in their own header. If the microphone
still cannot open, the widget says so and ends the call rather than showing
"live".

The build works without them. With an empty `.env` it warns, and the extension
loads with everything but the call: the widget, the viewer and every page Action
still work from the console (below), which is how the page side is tested before
there is a brain to call.

## Driving it from the console

With the extension loaded, every Action can be sent exactly as the brain would
send it, from the page's DevTools console, with no call:

```js
await __voqalizeSaatvik.perform("navigate", { path: "/modules/n-topcon" });
// A page, and where to land on it once it is up: a heading or words, a tab, or an FAQ.
await __voqalizeSaatvik.perform("navigate", { path: "/modules/n-topcon", heading: null, text: null, tab: "WARRANTY", faq: null });
await __voqalizeSaatvik.perform("show_section", { heading: null, text: "Module Efficiency" });
await __voqalizeSaatvik.perform("show_section", { heading: "Compare Specifications", text: "Annual Degradation" });
await __voqalizeSaatvik.perform("open_faq", { question: "How is N-TOPCon better" });
await __voqalizeSaatvik.perform("open_document", {
  url: "https://www.saatvikgroup.com/docs/2024/11/Saatvik-Dividend-Distribution-Policy.pdf",
  title: "Dividend Distribution Policy", page: 2,
  quote: "the Company may transfer a portion of its profits to reserves",
});
await __voqalizeSaatvik.perform("close_document", {});
// A narrated turn: cues as the brain sends them, then speech as the voice plays it.
const n = __voqalizeSaatvik.narration;
n.speaking();
n.add({ at: "n topcon is", word: 0, path: "/modules/n-topcon", heading: null, text: null, tab: null, faq: null });
n.add({ at: "it carries a", word: 6, path: null, heading: null, text: null, tab: "WARRANTY", faq: null });
n.hear("N-TOPCon is my pick for a home.");
n.hear("It carries a thirty-year warranty.");
await __voqalizeSaatvik.perform("run_calculator", { units: 350, state: "Karnataka", rate: 8 });
await __voqalizeSaatvik.perform("find_dealer", { state: "Karnataka", query: "Bengaluru" });
await __voqalizeSaatvik.perform("open_enquiry", {
  kind: "domestic",
  prefill: { name: "Priya Sharma", company: null, email: "priya@example.com", mobile: null,
             category: "Solar EPC - Rooftop", state: "Karnataka", message: null },
});
```

Off a call, each event the page would send is logged as
`voqalize (no call): <event> <payload>`, and a move that could not be made comes
back as the `command_failed` the brain would receive, with the reason in words
the model can act on — a heading that is not on the page lists the ones that
are, a state the dealer locator does not cover lists the ones it does.

The enquiry form's selects take their own labels: `category` and `state` are
matched loosely against the options the tab offers, and a value no option
matches is left empty and reported in `enquiry_opened`'s `missing`. The tabs ask
for different things — the dealer tab has no company, category or message, and
asks for a city, a district and an investment instead; the export tab has no
state.

## The visitor sees every move

- **Forms fill where they can be seen.** The calculator, the enquiry form and
  the booking page are filled one field at a time: each is brought into view,
  ringed, and typed at a pace a person can follow (about half a second a
  field), then what is left for the visitor is ringed — the empty fields, the
  consent box and the button. The calculator's own button is ringed for a
  moment and then pressed; Submit and Confirm booking never are. On the
  owner's dev call of 2026-10-28 the calculator filled and ran in one frame,
  and the first thing on screen was the estimate.
- **What she talks about is in the middle of the screen.** A heading that
  heads a card (an icon, a title and a line: a kit component, a feature) is
  scrolled to the middle of the space under the site's fixed header and
  ringed whole; a section that fits on the screen is centred and ringed
  whole; only a section taller than the screen is scrolled to its heading.
  Every scroll waits for the page to stop moving and corrects for any shift
  on the way, since a long smooth scroll takes more than a second and the
  page's images and reveal animations move what is below them.

## Enquiries are never sent

`DEMO_BLOCK_SUBMIT`, at the top of `src/saatvik-actions.js`, is on. Sunny fills
in the enquiry form but never ticks the consent box and never presses SUBMIT;
that stays the visitor's. When the visitor does press it, on any of the enquiry
tabs, the page reads the form and sends the brain `enquiry_submitted` with what
it held, and then stops the real send — before Saatvik's own handlers see the
click or the submit — and shows "Demo: this enquiry was not sent to Saatvik."
by the button. A demo call never reaches Saatvik's sales inbox. Turning the flag
off lets the site's own handlers run after the event is sent.

## One call, on one tab

Moving between pages keeps the call: the site's own client-side router changes
the page under it, and a full page load rejoins the same session on the next
page. The call belongs to one tab: starting a call in a second tab while the first
holds one says "Sunny is already on a call in another tab." rather than opening a
second call.
