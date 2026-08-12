---
name: voqalize
description: >-
  Build a voice agent on Voqalize end-to-end. Use when the developer wants to add
  voice/phone/talk-to-my-app capability, build a voice agent or voice bot, or
  mentions Voqalize. Guides you to scaffold a "brain" (a WebSocket the SDK runs),
  create the agent over the Voqalize MCP server, run it (locally over Cortex or
  deployed inbound), test it unattended with the conformance harness, mint a
  browser key, and embed the React widget. Requires the hosted `voqalize` MCP
  server (Google-OAuth HTTP).
---

# Build a voice agent on Voqalize

Voqalize is a **voice operator that lives inside the app** — it drives the UI, reads
live state, and does the work. You write the **brain**: a `Brain` subclass that gets
transcribed user turns and speaks replies. Voqalize runs WebRTC, VAD, STT, TTS,
interruption, and recording; brain and runtime talk over **one WebSocket per
session**, carrying text — the brain never touches audio.

## Prerequisites

The **`voqalize` MCP server** must be connected — a hosted HTTP endpoint, no key to
configure:

```bash
claude mcp add --transport http voqalize https://app.voqalize.com/mcp
```

(or copy this skill's `.mcp.json` into the repo). First use opens a browser Google
sign-in. Then run `whoami`, then `list_tenants` to get the **`tenant` slug** — every
scoped tool takes a required `tenant`. No tenant? `create_tenant` makes one. **Do not
proceed until `whoami` succeeds.** Also needed: Python ≥ 3.12; Node + React for the
browser embed.

The SDK is **not on PyPI yet.** Install it from a clone of
[github.com/voqalize/voqalize](https://github.com/voqalize/voqalize):
`uv pip install -e voqalize/sdk/python` (published name will be
`voqalize-agent-sdk`).

## The happy path

Work these in order. Each step names the reference to open **when you reach it** —
don't preload them.

1. **Understand the use case.** Ask what the agent does, what data/tools it needs,
   and what it says first. Keep v1 tiny (greet + one reply) so you prove the pipe
   before adding an LLM.
2. **Scaffold the brain** from `templates/brain.py` — `on_session_start` (greeting),
   `on_interaction` (a user turn), `on_client_message` (the browser sent something
   up), `on_user_idle` (silence). Its docstring is the callback reference.
3. **Create the agent:** `create_agent(tenant, name, description="")` →
   `{agent, session_key}`. Keep `agent.id`; the `sk_…` `session_key` is shown once
   (server-side session minting — never commit it, never ship it to a browser).
4. **Run the brain and point the agent at it.** → **`references/transport.md`**
   Local laptop: `create_agent_credentials` + dial out over Cortex (**no tunnel
   needed**). Production: an inbound `wss://` route in your own web framework.
   Either way you finish with `update_agent(tenant, agent_id, brain_url=…)`.
5. **Test it unattended, before any human talks to it.** →
   **`references/testing.md`** The `voqalize.conformance` harness drives your brain
   over a real socket in text mode — no audio, no browser, no human. Keep a scenario
   file per use case in the repo and run it in CI.
6. **Talk to it live.** Open the agent's `test_url` (returned by `create_agent` /
   `get_agent`) — the hosted Playground, pre-selected on your agent.
7. **Embed it in the app.** → **`references/frontend.md`**
   `create_api_key(tenant, agent_id, label, kind="publishable", allowed_origins=[…])` → `pk_…`,
   then `@voqalize/client-react` (`templates/react_embed.tsx`). **The page does not
   set the voice or the language** — the brain does, via its `voice`/`language`
   class attributes or `session.configure_language(...)`. There are no `stt`/`tts`
   fields on the agent record either. One owner, because a language split across
   two owners fails silently.
8. **Make it drive the screen** (only if the agent touches UI). →
   **`references/ui-actions.md`** The two-way contract: `interaction.action(...)` out,
   `sendMessage(...)` → `on_client_message` back.
9. **Instrument it and prove it works.** → **`references/instrumentation.md`**
   What to log from the brain (`on_inference_finalized`, `on_error`), how to
   correlate with `query_logs` / meeting events, and the numbers that show business
   value.

## MCP tools (16)

Identity: `whoami` · `list_tenants` · `create_tenant`. Agents: `create_agent` ·
`create_agent_credentials` · `get_agent` · `list_agents` · `update_agent` ·
`archive_agent`. Keys: `create_api_key` · `list_api_keys` · `revoke_api_key`.
Observability: `list_meetings` · `get_meeting` · `list_meeting_events` ·
`query_logs`. Every tool returns the control plane's raw JSON; every scoped tool
takes a required `tenant`. `not_authorized` = you're not a member of that tenant (or
your role is too low); `validation_error` = bad input (e.g. a non-`wss://`
`brain_url` on a non-loopback host).

## Files in this skill

| Path | Use |
|---|---|
| `.mcp.json` | MCP server config to copy into the developer's repo. |
| `templates/brain.py` | Starter `Brain` — greet + reply + a UI action. Transport-agnostic. |
| `templates/run_cortex.py` | Outbound Cortex runner — the local-dev path. |
| `templates/inbound_app.py` | FastAPI inbound host — the production path. |
| `templates/test_brain.py` | Conformance scenario file (pytest) — the CI loop. |
| `templates/react_embed.tsx` | Browser embed via `@voqalize/client-react`. |
| `references/transport.md` | Where the brain runs; local Cortex flow; production inbound. |
| `references/testing.md` | The conformance harness + live-call inspection. |
| `references/ui-actions.md` | The brain ↔ browser message contract. |
| `references/frontend.md` | React embed, `pk_` keys, ambient UI, and why voice/language aren't set here. |
| `references/instrumentation.md` | Logging, correlation, and value metrics. |
