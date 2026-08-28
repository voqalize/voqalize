# Voqalize

**A voice operator that lives inside your app.** You write the *brain* — an agent
that receives the caller's words and drives two channels back, **speech** and
**actions that drive the screen** — and Voqalize runs the voice stack: WebRTC, VAD,
speech-to-text, text-to-speech, interruption handling, recording. Your code never
touches audio.

This repository is the **public developer surface** for Voqalize: the wire
contract, the SDKs you build a brain with, runnable demo applications, and the
developer documentation. Voqalize itself — the hosted voice runtime — is a
managed service, and everything you need to build against it is here.

> **Developer preview.** The SDK surfaces and the wire are still moving.
> `voqalize-agent-sdk` 0.2.0 is published on PyPI as an alpha with the `Brain`,
> `run_session`, and `serve` API documented here. **Pin the version you build
> against**, because pre-1.0 releases may change the brain callbacks.
>
> **`@voqalize/client-react` is deprecated (2026-08-24), takes no replacement,
> and its source is no longer in this repo.** The browser half of a call is stock
> [pipecat](https://docs.pipecat.ai) plus one `fetch`, and the server now answers
> in the shape pipecat's transport connects with — so there is nothing left for a
> package of ours to do. The published 0.1.x remains installable for anything
> already built against it. See
> [Connections and the handshake](https://docs.voqalize.com/build/connect/).

## What's here

| Path | What it is |
|---|---|
| [`proto/`](proto/) | **The wire contract of record** — the message set both sides speak. Everything else is generated from or written against this. |
| [`sdk/python/`](sdk/python/) | Python brain SDK — subclass `Brain`, implement a couple of callbacks. Pipecat-free. |
| [`demos/`](demos/) | Complete, runnable voice apps (a brain + a UI each). These are real example code, the live demos on our site, and our integration tests — all at once. |
| [`docs/`](docs/) | The developer documentation site (`docs.voqalize.com`). |

> The Go SDK was removed while the Python surface is moving fast, and will
> return once it stabilizes. The wire itself stays language-neutral —
> [`proto/`](proto/) is the contract a future Go (or any other language) SDK
> would build against, and [the wire](docs/src/content/docs/reference/wire.md)
> documents it in full.

## Getting started

The fastest on-ramp is the **hosted MCP server**. Connect it
(`claude mcp add --transport http voqalize https://app.voqalize.com/mcp`) and your
editor's agent is handed the model on the first call plus links into
[the docs](https://docs.voqalize.com), every page of which is also served as raw
markdown at the same URL plus `.md`, indexed at
[`/llms.txt`](https://docs.voqalize.com/llms.txt). It walks from an empty
project to a running voice agent: write a brain → create an agent → get a
`brain_url` → wire a browser UI. Prefer to read code first? Start from
[`sdk/python/examples/echo`](sdk/python/examples/echo) (the smallest complete
brain) or [`sdk/python/examples/travel`](sdk/python/examples/travel) (a fuller
one), and [Connections and the handshake](docs/src/content/docs/build/connect.md)
for the browser side.

## The shape of a Voqalize app

A brain is a single WebSocket URL. Voqalize dials `{brain_url}?session_id={session_id}`,
one connection per session, opened when a call starts and torn down when it ends.
Where that URL points is up to you:

- **Your own inbound server** — you expose one authenticated WebSocket route
  (the same way you already run REST APIs). This is the path to build toward.
- **A Cortex relay** — for brains that can't accept inbound connections
  (serverless, laptops behind NAT, egress-only networks): your brain dials *out*.

Same brain code either way; you only pick who dials whom.

## Layout & tooling

A polyglot monorepo, split by toolchain:

- **Python** (`sdk/python`, `demos`) — one `uv` workspace; the demos'
  shared backend depends on the SDK by path.
- **JS/TS** (`docs`) — one `pnpm` workspace, one member. Each demo UI
  (`demos/<name>/frontend`) is a self-contained app *outside* the workspace, built
  standalone.
- **proto** (`proto/`) — `buf`; regenerates the Python stub the SDK consumes.

## License

[Apache License 2.0](LICENSE).
