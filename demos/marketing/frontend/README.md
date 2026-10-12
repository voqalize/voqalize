# voqalize.com

The Voqalize marketing site, voice first: Tanvi runs the site by voice, and a normal Read mode is
always one click away. Her brain is `../backend`; this folder is her page. It is served at the apex,
voqalize.com, and the other demos sit under it at `/demos`.

## Stack

Astro (static output) + TypeScript, no framework. One DOM, two layouts: every section is static
HTML (SEO, Read mode); Talk mode shows the guide on the left and only the active section on the right.

- `src/data/sections.json` and `src/data/voice.json`: the sections, and every control, link and block
  Tanvi can open, switch or point at. **The brain reads the same two files** (`../backend/site.py`),
  so the ids she can name are exactly the ids the page has. Controls are marked `data-voice="<id>"`,
  blocks `data-part`.
- `src/scripts/shell.ts`: modes, sections, chips, ask box, dock. `src/scripts/live.ts`: the live call
  (pipecat + `@voqalize/client-transport` + `@voqalize/avatar`, character `tanvi`).
  `src/scripts/voice.ts`: the simulated voice, used when no keys are set.
- `src/scripts/actions.gen.ts`: **generated** from the brain (`pnpm brain:types`). Never edit by hand.
  A new action or event needs a case in `shell.ts` (`applyAction`), or the build fails.

## Run it

```sh
pnpm install --ignore-workspace
pnpm dev          # http://localhost:4321, /api proxied to app.dev.voqalize.com
pnpm dev:live     # the site plus a local brain (../local.py) through Cortex
pnpm check        # types
pnpm test:e2e     # every brain action applied to the built site, desktop and phone
pnpm brain:test   # the brain's tests (no network)
```

Copy `.env.example` to `.env.local` for live voice. With only the two `PUBLIC_` keys the browser
calls that agent and whatever brain it dials; add `VOQALIZE_AGENT_SECRET` (a cortex-mode agent) and
`pnpm dev:live` runs the brain from this checkout. Without keys the site falls back to the simulated
voice.

## Deploy

`demos/cloudbuild.web.yaml` builds this site into the web artifact (`marketing/`) with the
environment's homepage agent, and the apex build lays it at `/` with the demos under `/demos`.
The brain deploys with the other brains (`demos/cloudbuild.brains-vm.yaml`). They ship separately,
so a new action goes out in the brain before the page that relies on it.
