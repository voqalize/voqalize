# docs — the Voqalize developer documentation site

The source for `voqalize.com/docs`. Built with **Astro Starlight** (same
framework as the marketing site), so it shares branding and outputs **pure
static** files — no runtime dependency. The built `dist/` is served under `/docs`
(e.g. by the control-plane container's static handler, alongside the marketing
site), or by any static host.

Covers the developer guides, the SDK references, and the **voice / model /
language catalog** (the vql-speech capability surface — a first-party Voqalize
microservice).

The Claude Code skill under [`../mcp`](../mcp) is an abridged, agent-friendly
condensation of these docs; this site is the full reference.

> Not scaffolded yet — build order step 5.
