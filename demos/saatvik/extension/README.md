# Tushar for Saatvik — the extension

A Chrome extension that puts Tushar, a voice solar advisor, on
[www.saatvikgroup.com](https://www.saatvikgroup.com) in place of the site's chat
launcher. He talks a visitor through Saatvik's modules, inverters and rooftop
kits while he moves their pages: he opens a page, rings the section or the
table row he is talking about, opens the FAQ that answers the question, opens a
datasheet or policy PDF at the page and line he quotes, runs the savings
calculator, filters the dealer locator, and fills in the enquiry form with what
the visitor has told him. Everything he shows is a page, section or form Saatvik
already has; the extension adds a corner widget, a PDF viewer, and the orange
ring he draws around what he is pointing at.

While he talks, the widget builds the brief Saatvik's sales team would receive —
a score, the reasons for it, where the lead would be routed, and what was said —
so the people watching see the other half of the product.

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
- `src/actions.gen.ts` — the Action and event unions, generated from the brain
  with `pnpm gen`. Regenerate after changing either.
- `src/pdf-viewer.ts` — the document viewer: a panel beside the widget that
  opens one of Saatvik's PDFs at a page and marks the quote Tushar reads from it.
  It renders with pdf.js and its own text layer, so the mark sits on the words.
  A quote is looked for on the asked page first, then on the pages either side
  of it, and a quote the model tidied up still lands on its opening or closing
  words. "Open full PDF" opens Saatvik's own file at the same page. Some of
  Saatvik's datasheets are drawn with their text as outlines; those open at the
  page but have nothing to mark.
- `src/widget.ts` — the corner widget, in a shadow root, in Saatvik's own navy,
  orange and typefaces: the call, an English | हिंदी toggle, and the lead
  brief, which can be collapsed. The visitor can drag it anywhere and minimise
  it to Tushar's face with the call still live.
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

The build works without them. With an empty `.env` it warns, and the extension
loads with everything but the call: the widget, the viewer and every page Action
still work from the console (below), which is how the page side is tested before
there is a brain to call.

## Driving it from the console

With the extension loaded, every Action can be sent exactly as the brain would
send it, from the page's DevTools console, with no call:

```js
await __voqalizeSaatvik.perform("navigate", { path: "/modules/n-topcon" });
await __voqalizeSaatvik.perform("show_section", { heading: "Compare Specifications", text: "Annual Degradation" });
await __voqalizeSaatvik.perform("open_faq", { question: "How is N-TOPCon better" });
await __voqalizeSaatvik.perform("open_document", {
  url: "https://www.saatvikgroup.com/docs/2024/11/Saatvik-Dividend-Distribution-Policy.pdf",
  title: "Dividend Distribution Policy", page: 2,
  quote: "the Company may transfer a portion of its profits to reserves",
});
await __voqalizeSaatvik.perform("close_document", {});
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

## Enquiries are never sent

`DEMO_BLOCK_SUBMIT`, at the top of `src/saatvik-actions.js`, is on. Tushar fills
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
holds one says "Tushar is already on a call in another tab." rather than opening a
second call.
