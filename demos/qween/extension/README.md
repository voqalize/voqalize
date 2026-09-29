# Trisha for Qween — the extension

A Chrome extension that puts Trisha, a voice jewellery consultant, on
[www.qween.com](https://www.qween.com). She finds pieces, opens them, switches
metals, and opens Qween's own price breakup, details and FAQs while she talks
about them. Everything she shows is a page, section or dialog Qween already has;
the extension adds nothing to their page except a corner widget and the gold ring
she draws around what she is pointing at.

Qween is a design partner. This extension is how we show them the agent on their
own shop before anything goes on it; it is not how a merchant would ship it.

## What is in it

- `src/qween-actions.js` — the site adapter. It performs each of the brain's
  Actions on Qween's page through their client-side router and their own stable
  attributes, and reports every route change and dialog back to the brain,
  whoever caused it. Its Action names mirror the Action classes in
  `../backend/brain.py`.
- `src/actions.gen.ts` — the Action and event unions, generated from the brain
  with `pnpm gen`. Regenerate after changing either.
- `src/widget.ts` — the corner widget, in a shadow root, in Qween's own
  typefaces and palette. Qween opens its drawers on the right edge, so while
  one is open — opened by the shopper or by Trisha — the widget glides to the
  left of it, or to a free corner, or shrinks to her face alone when there is no
  room. The shopper can drag it anywhere (the spot is remembered as the new
  home) and minimise it to that face with the call still live: the audio and
  the microphone are untouched.
- `src/dialogs.ts` — watches the page for open drawers and dialogs and reports
  where they will settle, not where they are mid-slide.
- `src/content.ts` — the call: stock pipecat, one `sessions.connect`, the
  avatar, and the glue between the adapter and the brain.

The brain is `../backend/`: the prompt, the tools, and the catalogue index built
from Qween's public product feed.

## Build and load

```sh
cp .env.example .env     # the agent id and a publishable key for www.qween.com
pnpm install --ignore-workspace
pnpm build               # → dist/
```

Then `chrome://extensions` → Developer mode → **Load unpacked** → `dist/`, and
open www.qween.com. The first call asks for the microphone.

The publishable key's allowed origins must be `https://www.qween.com`, which is
where the session is minted from. The agent id and key are baked into the
bundle at build time and are never committed.

## What survives a page load

A call is a WebRTC session in the page, so a full page load ends it. Qween's
navigation is client-side almost everywhere, which keeps the call, and the
adapter reroutes the "You may also like" cards, which otherwise reload. For
anything else, the widget remembers for the tab that a call was live and dials
again on the next page; Trisha's opener says the page reloaded, because the new
session does not have the old one's conversation.
