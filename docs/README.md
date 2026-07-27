# docs — the Voqalize developer documentation site

The source for `voqalize.com/docs`. Built with **Astro Starlight** (same
framework as the marketing site), so it shares branding and outputs **pure
static** files — no runtime dependency. The built `dist/` is assembled into the
single Firebase Hosting site at the env apex and served under `/docs`
(alongside the marketing site at `/` and the demos at `/demos/<name>`), or by
any static host.

Covers the developer guides, the SDK references, and the **voice / model /
language catalog** (the vql-speech capability surface — a first-party Voqalize
microservice).

The Claude Code skill under [`../skill`](../skill) is an abridged, agent-friendly
condensation of these docs; this site is the full reference.
