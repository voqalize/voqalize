# Tushar for SendPotion — the extension

A Chrome extension that puts Tushar, a voice guide, on
[sendpotion.com](https://sendpotion.com) and its blog,
[blog.sendpotion.com](https://blog.sendpotion.com). He talks a visitor through
Potion while he moves their screen: he opens the page that answers them and
scrolls to the exact section, rings a plan or a feature, opens an FAQ, books a
demo with them on the calendar, and, when they describe their use case, puts the
blog posts that fit in a reading list and opens the best one in a new tab. One
call follows the visitor across every SendPotion tab they have open, on both
hosts. Everything he shows is a page, section, post or form SendPotion already
has; the extension adds a corner widget and the ring he draws around what he is
pointing at.

This is how we show the agent to SendPotion on their own site, before anything
goes on it; it is not how a customer would ship it.

## What is in it

- `src/sendpotion-actions.ts` — the site adapter. It performs the brain's page
  Actions on the tab in front and reports every route change and booking step
  back, whoever caused it. On sendpotion.com a move is a click on a link, which
  the site's own router takes, so the call survives every page; scrolling goes
  through the site's smooth-scrollbar, not the window. On the blog (a Medium
  publication) it scrolls the window.
- `src/early.ts` — runs before the site's own scripts and finds that scroller:
  the library keeps its instances in a private `Map`, so this notes the one
  `Map.prototype.set` that stores a scrollbar under its own element.
- `src/calendly.ts` — runs inside the Calendly frame on `/demo/`, only when
  SendPotion's page holds it. It reads the open days and times, picks the ones
  the visitor asked for, presses Next and fills in name, email and notes.
- `src/hub.ts`, `src/bridge.ts`, `src/background.ts` — the hub. A
  `BroadcastChannel` and a Web Lock reach one origin, and SendPotion is two, so
  the call's relay runs through the extension's service worker instead: every
  tab's messages reach every other SendPotion tab, the call's claim is held by
  browser tab, and the posts Tushar opens are opened by the worker, since his
  move arrives over the call and a page may not open a tab without a click.
- `src/tabs.ts` — Qween's one-call-every-tab relay, on the hub: the tab the
  call started in holds it; every other tab follows with his face, the mute and
  the call's state.
- `src/widget.ts` — the corner widget, in a shadow root: the call, and the
  reading list, which every tab shows.
- `src/content.ts` — the call: stock pipecat with `@voqalize/client-transport`
  as its media manager, one `sessions.connect`, the avatar, and the routing of
  each Action to the tab it belongs on.
- `src/actions.gen.ts` — the Action and event unions, generated from the brain
  with `pnpm gen`. Regenerate after changing either.

The brain is `../backend/`: the prompt, the tools, and SendPotion's knowledge.

## Build and load

```sh
cp .env.example .env     # the agent id and a publishable key (see below)
pnpm install --ignore-workspace
pnpm build               # → dist/
```

Then `chrome://extensions` → Developer mode → **Load unpacked** → `dist/`, and
open sendpotion.com. The first call asks for the microphone. `pnpm build:prod`
builds the same extension against production into `dist-prod/`, from
`.env.prod`.

The publishable key's allowed origins must include `https://sendpotion.com`,
`https://www.sendpotion.com` and `https://blog.sendpotion.com`: a call can start
on either host. The agent id and key are baked into the bundle at build time and
are never committed: this repo is public.

The build works without them. With an empty `.env` it warns, and the extension
loads with everything but the call: the widget and every page Action still work
from the console (below).

## Driving it from the console

With the extension loaded, every page Action can be sent exactly as the brain
would send it, from the page's DevTools console, with no call:

```js
await __voqalizeSendPotion.perform("navigate", { path: "/pricing/", heading: null, text: "Professional" });
await __voqalizeSendPotion.perform("show_section", { heading: "How Potion works", text: null });
await __voqalizeSendPotion.perform("open_faq", { question: "Are there any restrictions on the length" });
await __voqalizeSendPotion.perform("book_demo", {
  day: "Tuesday, October 20", time: "3:00pm", name: "Jane Doe", email: "jane@example.com",
  notes: "Agency of ten; wants outreach videos.",
});
__voqalizeSendPotion.reads("For agency outreach", [
  { url: "https://blog.sendpotion.com/…", title: "…", why: "How agencies win clients" },
]);
```

A move that could not be made comes back as the `command_failed` the brain
would receive, with the reason in words the model can act on: a heading that is
not on the page lists the ones that are; a day the calendar does not offer lists
the days it does.

## Demos are never booked

`DEMO_BLOCK_SUBMIT`, at the top of `src/calendly.ts`, is on. Tushar picks the
day and time and fills in the details, but never presses **Schedule Event**;
that stays the visitor's. When they press it, the frame reports
`demo_scheduled` to the brain and then stops the real booking, with "Demo: this
meeting was not booked in SendPotion's calendar." under the button. A demo call
never puts a meeting in SendPotion's calendar. Turn the flag off when SendPotion
wants the agent's bookings to reach them.

## One call, every tab

The call belongs to the tab it started in. Every other SendPotion tab, on either
host, shows Tushar's face and the call's state and can mute or end it; the tab
in front is the one he sees and moves. A move to a sendpotion.com page made
while the visitor is reading the blog goes to their sendpotion.com tab, brought
to the front, or a new one. Closing the call's tab ends the call everywhere.

Moving between pages keeps the call: both hosts route client-side. A full page
load in the call's tab rejoins the same session on the next page.

The blog sits behind Cloudflare, which turns away automated browsers; a person's
Chrome is let through, so the blog half is checked by hand.
