# Swiggy Instamart MCP — OAuth spike

A derisk spike for the **voice-grocery demo** (Swiggy/Zepto pitch). It proves the
single hardest unknown — *can we authenticate to Swiggy's MCP and make a real
call, headless, without Swiggy whitelisting anything for us* — on a laptop, end
to end:

```
DCR → PKCE authorize (Swiggy-hosted phone+OTP) → loopback capture
    → token exchange → persist → refresh → one real get_addresses call
```

## The headline finding (why there's no MITM)

The original worry was: *"our callback URL isn't whitelisted, so we have to be a
man-in-the-middle."* The live endpoints say otherwise. Probed 2026-06-28 against
`https://mcp.swiggy.com/.well-known/oauth-authorization-server`:

| Capability | Value | Consequence |
|---|---|---|
| `registration_endpoint` | `/auth/register` | **Dynamic Client Registration** — we self-register, no Swiggy approval |
| `token_endpoint_auth_methods` | includes `"none"` | **Public PKCE client** — no client secret |
| `grant_types` | `authorization_code`, **`refresh_token`** | Auth once, reuse for days |
| `code_challenge_methods` | `S256` | Standard PKCE |
| whitelisted redirects | include `http://localhost/callback`, `http://127.0.0.1/callback` | **our loopback is a legitimate redirect target** |

The phone+OTP runs entirely on **Swiggy's hosted `/auth/authorize` page** — this
spike never sees a phone number, an OTP, or a password. It only ever holds the
authorization code, then the issued token. That is plain OAuth 2.1 with a
loopback client (RFC 8252), the same trust model as Claude.ai's own connector —
*not* an interception. Pitch it that way to security-minded stakeholders.

## Run it

Stdlib only — no venv, no new deps, any Python 3.12+. **Token generation is
decoupled from token use**, which is the whole point: one privileged person runs
`generate` once; everyone else just `run`s.

```bash
cd backend/agent-sdk/examples/swiggy_oauth_spike

# 1. Account owner, once: phone+OTP OAuth -> caches ~/.swiggy/tokens.json (chmod 600)
python3 run.py generate

# 2. Anyone, thereafter: reuse the cached token, refresh if expired, NO browser
python3 run.py

# list the tool surface and exit (no order data)
python3 run.py run --tools
```

- **`generate`** pops a browser → enter phone + OTP on swiggy.com → the loopback
  catches the redirect → tokens cached to `~/.swiggy/tokens.json` → it verifies
  by listing tools and calling `get_addresses` with the real account.
- **`run`** is silent and headless: loads the cached token, does a
  `refresh_token` exchange if expired, and **never opens a browser**. If there's
  no token (and refresh fails), it tells you to ask the owner to re-`generate`.
  This is exactly the unattended token-lifecycle the demo backend runs per user.

**Sharing:** the token lives in `~/.swiggy/tokens.json` as a single portable
artifact. Hand someone that file (or this script + the file) and `run` works for
them with no OTP. The demo backend reads the same file and passes
`tokens["access_token"]` as the voice session's initial data.

## What it confirms for the demo

- **Auth is solved for the laptop demo today** — zero asks of Swiggy.
- **Refresh tokens** mean a gated user authenticates once; the brain reuses the
  session unattended across the pitch.
- **`your_go_to_items` / `get_addresses` / `get_orders` return the real user's
  data**, so the pre-built prompt context (addresses, reorder history) is real
  per user, not faked.

## The one real fork: localhost vs. hosted callback

- **Laptop demo (this spike):** `http://localhost:8765/callback` — works now.
- **Hosted demo** (`app.dev.voqalize.com`): a user's browser can't redirect to
  *our server's* localhost, so a hosted deploy needs our real callback URL
  whitelisted. The manifest says *"Contact us if you need additional URIs
  whitelisted."* Since Swiggy stakeholders are the audience, **that request is
  part of the pitch, not a blocker** — and localhost covers every live demo
  until then.

## Limits (it's a spike)

- Tokens live in a flat JSON file at `~/.swiggy/tokens.json` — fine for one user
  on one laptop, **not** the per-tenant token store the real demo needs.
- No Cortex/brain wiring, no SKU-match loop, no UI — just the auth mechanic and
  one proof-of-life MCP call.
- Speaks the minimum Streamable-HTTP MCP needed (`initialize` →
  `notifications/initialized` → `tools/list` → one `tools/call`); handles both
  JSON and single-event SSE replies, nothing fancier.
