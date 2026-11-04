---
title: HTTP API
description: The one route that takes an API key, sessions.connect, which starts a session. Its request body, its response, its errors and its rate limit. Management is on the MCP server.
---

One route accepts an API key, and it starts a session:

```
POST https://app.voqalize.com/api/v1/sessions.connect
Authorization: Bearer sk_…
Content-Type: application/json
```

Everything else (creating an agent, setting its `brain_url`, minting and
revoking keys, reading sessions, logs and usage) is on
[the MCP server](/reference/mcp/), authenticated with OAuth.

## The request body

The body is **strict**: an undeclared top-level key is a `422` naming it.

| Field | | |
|---|---|---|
| `agent_id` | required | Which agent answers. The key is scoped to it. |
| `init` | optional | An opaque JSON object your brain reads as `session.init`. It is stored on the session, so send identifiers, not personal data; see [Context and history](/build/brain/context/). |
| `config` | optional | This session's `tts`, `stt`, `idle` and `ack`, plus `record`. Parsed as canonical proto3 JSON; the values are in [the catalog](/reference/catalog/). |
| `display_name` | optional | A label for your own console and lists. |
| `metadata` | optional | A flat string map for correlating the session with your systems. At most **10 keys**, each value at most **256 characters**. |

Which key to hold, and what a `pk_` may and may not set, is in
[Connect your app](/build/connect/) and [Recordings](/operate/recordings/).

## The response

The pipecat client's connect params, and nothing else:

| Field | |
|---|---|
| `webrtc_request_params` | Where and how the transport sends its offer. |
| `session_id` | The session, the same id your brain is dialled with. |
| `ice_config` | The relay servers for this session, when there are any. |

Pass it to the client's `connect` with the one `Headers` line in
[Connect your app](/build/connect/#the-one-line-you-write-yourself), not to
`startBotAndConnect`, which leaves nowhere to add that line. To read the session
afterwards, use `get_session` on the MCP server.

## Errors and the rate limit

Every error is one envelope, `{error: {code, message, details}, info,
correlation_id}`. The codes `sessions.connect` returns are in
[Connect your app](/build/connect/#when-it-fails) and
[Error codes](/reference/errors/#refused-before-your-brain-is-dialled). Quote the
`correlation_id` when you ask us about one.

The route is rate limited per tenant. A refused request is a `429` with a
`Retry-After` header in seconds: wait that long and send it again.

## Management is on MCP, by design

Every API key names one agent, so no key can create an agent or mint another
key. Management therefore runs on [the MCP server](/reference/mcp/), where your
coding agent signs in with OAuth and no long-lived tenant-wide credential sits in
an environment variable.

If your integration cannot hold an OAuth client (a CI job that provisions
agents, or a product creating tenants for its own customers), **ask us**:
HTTP access to the operations you need can be enabled for your account.

## Read next

- [Connect your app](/build/connect/): the request, and which key to hold.
- [The MCP server](/reference/mcp/): the management surface, tool by tool.
- [Keys and authentication](/build/keys/): `sk_` and `pk_`, and rotation.
