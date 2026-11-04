---
title: Work with a coding agent
description: Connect your coding agent to the Voqalize MCP server, see what it reads, and let it take a project from empty to a working voice agent. The end-to-end flow, a prompt that works, and the Stage skills.
---

Your coding agent (Claude Code, or any MCP client) can do every step of a
Voqalize integration from your editor: create the agent, mint its keys, run the
brain, and read back what a session did. It does this through the hosted
Voqalize MCP server, and it learns the product from these docs.

## Connect the MCP server

The server is hosted at `https://app.voqalize.com/mcp/`. There is nothing to
install. In Claude Code:

```bash
claude mcp add --transport http voqalize https://app.voqalize.com/mcp/
```

Or, for everyone working in a repository, add `.mcp.json` at its root:

```json
{
  "mcpServers": {
    "voqalize": {
      "type": "http",
      "url": "https://app.voqalize.com/mcp/"
    }
  }
}
```

Any other MCP client takes the same two things: a name and that URL over HTTP.
On first use the client opens a browser for a Google sign-in, the same login as
the console. There is no API key or client secret to configure.

## What your agent reads

- **The handshake.** On connect, the server gives your agent one paragraph that
  explains brain, agent and session, and links to the docs.
- **The docs as markdown.** Every page on this site is also served as raw
  markdown at its URL plus `.md` (for example
  `https://docs.voqalize.com/build/quickstart.md`), and
  [`/llms.txt`](https://docs.voqalize.com/llms.txt) indexes them, one line each.
- **The tools.** Each tool describes itself, and a refused call comes back with
  a message saying why. [MCP server](/reference/mcp/) lists every tool and its
  arguments.

Every tool but `whoami`, `list_tenants` and `create_tenant` takes a `tenant`
slug. Calls are limited to 120 a minute per tenant.

## The flow, end to end

This is the order an agent with these tools takes a project from empty to a
running voice agent:

1. **Find the tenant.** `whoami`, then `list_tenants`. Choose the tenant by its
   `name` and pass its `slug` as `tenant` to every other tool. An empty list means
   there is no tenant yet: call `create_tenant`.
2. **Write the brain.** A `Brain` subclass with `greet` and `on_user_message`,
   then the callbacks it needs. See [Build the brain](/build/brain/).
3. **Test it unattended.** The [conformance harness](/build/testing/) drives the
   brain over the real wire, with no audio, no model and no person.
4. **Create the agent.** `create_agent(tenant, name)` returns the agent (with its
   `test_url`) and a `session_key`: an `sk_` key, shown once, for your server.
5. **Say how Voqalize reaches the brain.** Locally,
   `create_agent_credentials(tenant, agent_id)` puts the agent on the Cortex relay
   and returns `agent_secret` and `cortex_url` for `serve(...)`; no tunnel. In
   production, `update_agent(tenant, agent_id, brain_url="wss://…")` points it at
   an inbound route. Until one of these is done, every session is refused with
   `agent_not_configured`. See [Deploy the brain](/build/hosting/).
6. **Talk to it.** Run the brain and open the agent's `test_url`, the console
   Playground.
7. **Put it in the app.** A server route that calls `sessions.connect` with the
   `sk_` key, and your client on `@voqalize/client-transport` in the page. For
   a public page with no login, mint a browser key with
   `create_api_key(tenant, agent_id, label, kind="publishable", allowed_origins=[…])`.
   See [Connect your app](/build/connect/).
8. **Read sessions back.** `list_sessions`, then `get_call_record` for what was
   said and heard, and `get_session_logs` for Voqalize's side. See
   [Reading a call back](/operate/reading-a-call/).

## A prompt that works

Name the outcome, where it goes in your app, and how you will check it:

```text
Add a Voqalize voice agent to this app. Read https://docs.voqalize.com/llms.txt
first. Put the brain in backend/voice/brain.py using OpenAIBrain, with a tool
that reads the current order. Run it locally over Cortex, give me the test_url,
and once I confirm it answers, add a "Talk to us" button to the order page that
starts a session through a new /api/voice/start route.
```

Ask for the harness tests in the same request if you want them written before
the agent goes live.

## Stage skills

If your app uses [Stage](/build/stage/), the public repository ships five Claude
Code skills for it in
[`.claude/skills/`](https://github.com/voqalize/voqalize/tree/main/.claude/skills):

| Skill | Use it to |
|---|---|
| `stage-author` | Add Stage to your web app: the spec, the page's performers and the state events. |
| `stage-move` | Add or change one move in your Stage Spec, then regenerate and check it. |
| `stage-debug` | Turn a session into a timeline of speech against screen, to find why the page did not move. |
| `stage-review` | Review a diff that touches Stage against Stage's rules. |
| `stage-explorer` | Study a live website you do not control and write its Stage Spec. |

Copy them into your project, where Claude Code loads project skills from. They
cite the Stage contract and example in the public repository, so keep a clone
beside your project:

```bash
git clone --depth 1 https://github.com/voqalize/voqalize ../voqalize
mkdir -p .claude/skills
cp -r ../voqalize/.claude/skills/stage-* .claude/skills/
```

## Read next

- [Quickstart](/build/quickstart/): the same flow, by hand.
- [MCP server](/reference/mcp/): every tool, argument and return value.
- [Reading a call back](/operate/reading-a-call/): debugging a session from your editor.
