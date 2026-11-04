---
title: Keys and authentication
description: The secret key (sk_) for your backend and the brain's Cortex connection, and the origin-locked publishable key (pk_) for a browser page. Both name one agent. How to mint, restrict, rotate and revoke them.
---

Every key names exactly one agent and starts sessions for that agent only. There
is no tenant-wide key. Keys never expire; you revoke them.

| Kind | Prefix | Held by | Used for |
|---|---|---|---|
| Secret | `sk_live_` | Your backend, your scripts, your brain | `sessions.connect` from your server; the brain's [Cortex](/build/hosting/#a-brain-that-dials-out) connection |
| Publishable | `pk_live_` | A browser page, in its source | `sessions.connect` from that page, and only from the origins you list |

## Secret keys (`sk_`)

Keep it on your server. Prefer this path: your server starts the session, so it
decides who gets one (a login, an entitlement, a rate limit).

A native or mobile app uses this path too. It sends no `Origin` header, so a
`pk_` cannot work from it: the app asks your backend, and your backend calls
`sessions.connect` with an `sk_` ([Connect your app](/build/connect/)).

The raw value is shown once, when it is minted. Voqalize stores only a hash, so a
lost key is replaced, not recovered.

### Rotating a key

Several keys can be live for one agent at once, and minting revokes nothing, so
rotation has no outage:

1. **Mint** a new key with `create_api_key` (or `create_agent_credentials`, for a
   Cortex brain).
2. **Redeploy** with the new key. Both keys work meanwhile.
3. **Revoke** the old one with `revoke_api_key`. Revocation is immediate for new
   connections and cannot be undone; a session already running finishes.

`list_api_keys` shows each key's `last_used_at`. A live key that is never used
usually means the deployed code holds a different one.

## Publishable keys (`pk_`)

For a browser page with no backend of its own: a demo, a marketing page, a
prototype. It ships in page source, so anyone can read it. What keeps it yours is
its **origin allowlist**: Voqalize compares the browser's `Origin` header with the
list, and refuses a request from an origin not on it, or with no `Origin` header
at all, with `403 origin_not_allowed`.

| Entry | Matches |
|---|---|
| `https://app.example.com` | Exactly that origin. Write `scheme://host[:port]` with no path. A default port (`:443`, `:80`) and a trailing slash are dropped when the key is saved. |
| `http://localhost:5173` | Exactly that local origin. `http://` is allowed. |
| `https://*.example.com` | Every subdomain of `example.com`, at any depth (`a.example.com`, `a.b.example.com`), with that scheme and port. **Not** `example.com` itself: list it separately. |
| `*`, `*.com`, `https://example.com/app` | Refused when the key is saved. The `*` must be the whole first label with a domain of at least two labels after it, and an entry has no path. |

A publishable key needs at least one origin: an empty list is refused when it is
minted.

A `pk_` may turn recording off for a session, never on; see
[Recordings](/operate/recordings/). Move to an `sk_` on your server as soon as
anything decides who may have a session.

## Minting and managing keys

Over the [MCP server](/reference/mcp/):

```text
create_api_key(tenant="acme", agent_id="06a2…", label="web", kind="secret")
create_api_key(tenant="acme", agent_id="06a2…", label="site", kind="publishable",
               allowed_origins=["https://app.example.com", "https://*.example.com"])
update_api_key_origins(tenant="acme", key_id="…",
                       allowed_origins=["https://app.example.com", "https://staging.example.com"])
list_api_keys(tenant="acme", agent_id="06a2…")
revoke_api_key(tenant="acme", key_id="…")
```

- `create_agent` returns the agent's first `sk_` as `session_key`. A tenant's
  starter agent has no key you were shown, so mint one with `create_api_key`.
- `update_api_key_origins` **replaces** the whole list. Read the current list from
  `list_api_keys`, change it, and send all of it back; an origin you leave out is
  refused from the next page load.
- `list_api_keys` returns metadata only: the prefix (`sk_live_AbC12…`), the agent
  it names, its origins and its status. `revoke_api_key` takes the key's `id`.

In the console, an agent's **Connect** tab mints an `sk_` beside the snippets that
use it, and **Settings → API keys** mints either kind.

Managing agents and keys uses neither kind of key: the MCP server and the console
sign you in with OAuth.

## Read next

- [Connect your app](/build/connect/): where each key goes in the connect request.
- [Deploy the brain](/build/hosting/): where the brain's `sk_` goes.
