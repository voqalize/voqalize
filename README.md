# Voqalize

**A voice operator that lives inside your app.** You write the *brain* — an agent
that receives text and speaks text back — and Voqalize runs the voice stack: WebRTC,
VAD, speech-to-text, text-to-speech, interruption handling, recording. Your code
never touches audio.

This repository is the **public developer surface** for Voqalize: the wire
contract, the SDKs you build a brain with, runnable demo applications, and the
developer documentation. The Voqalize platform itself (the hosted voice runtime)
is a managed service — everything you need to build against it is here.

> **Pre-release.** APIs and the wire protocol are still moving, and the packages
> below are not yet published to PyPI / npm. For now, depend on them from a clone
> of this repo (they are path-wired to resolve locally). Published packages will
> follow at beta.

## What's here

| Path | What it is |
|---|---|
| [`proto/`](proto/) | **The wire contract of record** — the `Vql*` frame set both sides speak. Everything else is generated from or written against this. |
| [`sdk/python/`](sdk/python/) | Python brain SDK — subclass `Brain`, implement a couple of callbacks. Pipecat-free. |
| [`sdk/go/`](sdk/go/) | Go brain SDK — native, pipecat-free, speaks the wire protocol directly. |
| [`sdk/react/`](sdk/react/) | React client SDK — embed a voice agent in a browser app. |
| [`skill/`](skill/) | The **`voqalize` Claude Code skill** (`skill/SKILL.md`) — point your editor's agent at it and it builds an agent end-to-end over the hosted, Google-OAuth MCP server. |
| [`demos/`](demos/) | Complete, runnable voice apps (a brain + a UI each). These are real example code, the live demos on our site, and our integration tests — all at once. |
| [`docs/`](docs/) | The developer documentation site (`voqalize.com/docs`). |

## Getting started

The fastest on-ramp is the **Claude Code skill** — point your editor's agent at
[`skill/SKILL.md`](skill/SKILL.md) and it will walk you from an empty
project to a running voice agent (write a brain → create an agent → get a
`brain_url` → wire a browser UI). Prefer to read code first? Start from
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
- **Go** (`sdk/go`) — its own module.
- **proto** (`proto/`) — `buf`; regenerates the Python and Go stubs the SDKs
  consume.

## License

[Apache License 2.0](LICENSE).
