---
title: Keys and authentication
description: Two kinds of key, both scoped to one agent. Which one your backend holds, which one ships in page source, and what the origin allowlist is actually doing.
---

Every Voqalize credential names one agent. There is no workspace-wide key, and
there is no key that can mint a session for an agent it does not name — a
credential whose blast radius can only be discovered by reading code is a
credential nobody can reason about.

There are two kinds.

## `sk_` — the secret key, and the primary path

Held by your backend. It starts sessions for its own agent, and it is what that
agent's brain presents when it dials out over [Cortex](/deploy/cortex/).

This is the path to prefer. Your server mints the session, so it decides who is
allowed to have one — a login, a rate limit, a paywall, a check that this
customer is entitled to talk to this agent. None of that is expressible in a key.

Several `sk_` keys can be live for one agent at once, which is what makes rotation
a three-step with no outage:

1. **Mint** a new key. Minting revokes nothing.
2. **Deploy** it. Both keys work.
3. **Revoke** the old one. Revocation is irreversible.

The raw key is shown once, at creation. Only its SHA-256 hash is stored, so a lost
key is re-minted rather than recovered.

## `pk_` — the publishable key, for a page with no backend

Ships inside a browser or mobile bundle, and is public by construction. Anyone who
reads view-source has it.

The only thing separating "our page using our key" from "anyone who copied it" is
the **origin allowlist**, which every `pk_` key carries and which the API enforces
against the request's `Origin` header. The list must be non-empty — an empty list
is rejected at creation rather than treated as "any origin," because the version
of that rule that silently meant *any* is the version that was shipping.

A `pk_` key is the lesser path on purpose. Reach for it for a demo, a marketing
page, or a prototype; move to an `sk_` on your own server the moment there is
anything to decide about who gets a session.

One asymmetry follows from where the key lives, and it is worth knowing before it
surprises you: **a `pk_` key may turn recording off, and may not turn it on.**
See [recordings](/operate/recordings/).

## Minting them

Over [the MCP server](/reference/mcp/), from your editor:

```
create_api_key(tenant, agent_id, label, kind="secret")
create_api_key(tenant, agent_id, label, kind="publishable",
               allowed_origins=["https://app.example.com"])
```

Or in the console, under Settings → API keys. `list_api_keys` returns prefixes
only (`sk_live_AbC12…`), each with the agent it names; `revoke_api_key` takes the
key id.

## The management API takes neither

Creating agents, minting keys, reading calls — none of it is driven by an API key.
Developer tooling authenticates interactively over OAuth, which is what the MCP
server does when you connect it. There is no third key kind to manage, and no
long-lived admin credential to leak.

## Read next

- [Connections and the handshake](/client/handshake/) — where a `pk_` key is used, and the one line pipecat needs.
- [Where the brain runs](/deploy/brain-url/) — where the `sk_` key is used.
