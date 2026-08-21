# Voqalize

**A voice operator that lives inside your app.** You write the *brain* — an agent
that receives the caller's words and drives two channels back, **speech** and
**actions that drive the screen** — and Voqalize runs the voice stack: WebRTC, VAD,
speech-to-text, text-to-speech, interruption handling, recording. Your code never
touches audio.

This repository is the **public developer surface** for Voqalize: the wire
contract, the SDKs you build a brain with, runnable demo applications, and the
developer documentation. The Voqalize platform itself (the hosted voice runtime)
is a managed service — everything you need to build against it is here.

> **Pre-release.** APIs and the wire protocol are still moving. `voqalize-agent-sdk`
> (PyPI) and `@voqalize/client-react` (npm) are published, but the surface they
> carry is the previous one — **pin the version you build against**, and expect the
> next release to change the brain callbacks.

## What's here

| Path | What it is |
|---|---|
| [`proto/`](proto/) | **The wire contract of record** — the `Vql*` frame set both sides speak. Everything else is generated from or written against this. |
| [`sdk/python/`](sdk/python/) | Python brain SDK — subclass `Brain`, implement a couple of callbacks. Pipecat-free. |
| [`sdk/react/`](sdk/react/) | React client SDK — embed a voice agent in a browser app. |
| [`demos/`](demos/) | Complete, runnable voice apps (a brain + a UI each). These are real example code, the live demos on our site, and our integration tests — all at once. |
| [`docs/`](docs/) | The developer documentation site (`voqalize.com/docs`). |

> The Go SDK was removed while the platform surface is moving fast on the
> Python/ADK track, and will return once that surface stabilizes. The wire
> protocol itself stays language-neutral — [`proto/`](proto/) is the contract
> a future Go (or any other language) SDK would build against.

## Getting started

The fastest on-ramp is the **hosted MCP server**. Connect it
(`claude mcp add --transport http voqalize https://app.voqalize.com/mcp`) and your
editor's agent is handed the model on the first call plus links into
[the docs](https://voqalize.com/docs), every page of which is also served as raw
markdown at the same URL plus `.md`, indexed at
[`/docs/llms.txt`](https://voqalize.com/docs/llms.txt). It walks from an empty
project to a running voice agent: write a brain → create an agent → get a
`brain_url` → wire a browser UI. Prefer to read code first? Start from
[`sdk/python/examples/echo`](sdk/python/examples/echo) (the smallest complete
brain) or [`sdk/python/examples/travel`](sdk/python/examples/travel) (a fuller
one), and [`sdk/react`](sdk/react) for the browser side.

## The shape of a Voqalize app

A brain is a single WebSocket URL. Voqalize dials `{brain_url}/s/{session_id}`,
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
- **JS/TS** (`sdk/react`, `docs`) — one `pnpm` workspace. Each demo UI
  (`demos/<name>/frontend`) is a self-contained app *outside* the workspace, built
  standalone and linking the client SDK by path.
- **proto** (`proto/`) — `buf`; regenerates the Python stub the SDK consumes.

## License

[Apache License 2.0](LICENSE).
