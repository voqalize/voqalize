# Seeding OrderDesk in production

Agent management on the control plane is Google-OAuth only (session cookie or the
hosted MCP) — there is deliberately no headless key path for `agents.create`, so
this seed is a sequence of **Voqalize MCP tool calls**, executable by any agent
session with the MCP connected:

```bash
claude mcp add --transport http voqalize https://app.voqalize.com/mcp
```

## 1. Identify

```
whoami()                      # sanity: the authenticated developer
list_tenants()                # confirm membership of the demos tenant (slug: demo)
```

## 2. Create the agent (idempotent by name — check first)

```
list_agents(tenant="demo")    # if "OrderDesk" already exists, skip to update_agent
create_agent(
  tenant      = "demo",
  name        = "OrderDesk",
  description = "B2B order intake for a pharma distributor — Hindi voice, 20k-SKU catalog resolution on screen.",
  brain_url   = "wss://brain.voqalize.com/orderdesk",
)
# → {agent: {id: <AGENT_ID>, test_url: ...}, session_key: sk_... (shown once; not needed for the demo page)}
```

If the agent pre-exists or the brain URL changes:
`update_agent(tenant="demo", agent_id=<AGENT_ID>, brain_url="wss://brain.voqalize.com/orderdesk")`

### The language does NOT come from the agent record

`create_agent`/`update_agent` expose no STT/TTS fields, so the agent is created
with platform defaults — **English** STT (`stt.language_hint` unset ⇒ Parakeet)
and the English `omnivoice/gaurav` voice. That is fine and intentional: this demo
sets its pipeline **per session** from the browser
(`frontend/src/config.ts` → `pipeline`), which PyGato layers over the record
field by field.

Two things must therefore stay true, or the call breaks in a way that looks like
bad recognition rather than bad config:

- `stt.language_hint: "hi"` — PyGato reads `language_hint`, **not** `language`,
  when choosing the recognition engine. Sending only `language: "hi"` silently
  transcribes Hindi with an English model.
- `tts.voice: "omnivoice/gauri"` + `tts.language: "hi"` — both read from the
  override, so the record's English defaults never surface.

If someone later gains a way to set STT/TTS on the record, mirror the same values
there; the override is field-level, so agreeing config is harmless.

## 3. Mint the browser key

```
create_api_key(
  tenant          = "demo",
  label           = "orderdesk-web",
  kind            = "publishable",
  allowed_origins = ["https://voqalize.com", "https://www.voqalize.com"],
)
# → pk_...  (shown once — capture it)
```

Match `allowed_origins` to whatever origins serve the other demos' pk keys
(`list_api_keys(tenant="demo")` shows the labels; the demo UI calls same-origin
`/api`, so only the apex that serves `/demos/orderdesk` is needed).

## 4. Wire the web build (private repo trigger)

Set the two new substitutions on the `deploy-web` trigger in the private repo:

```
_ORDERDESK_AGENT = <AGENT_ID>
_ORDERDESK_PK    = <pk_...>
```

(`demos/cloudbuild.web.yaml` in this repo already declares the placeholders and
maps them to `VITE_ORDERDESK_AGENT` / `VITE_ORDERDESK_PK`; `build.mjs` folds them
into the app's `VITE_AGENT_ID` / `VITE_PUBLISHABLE_KEY`.)

## 5. Deploy + verify

1. Brains: run the brains-vm trigger. `_EXPECTED_DEMOS` is already bumped to 11 —
   the deploy's verify step fails unless `https://brain.voqalize.com/_healthz`
   lists `orderdesk`.
2. Web: the web trigger → Pub/Sub → marketing deploy lays `/demos/orderdesk`
   under the apex.
3. Smoke: open the agent's `test_url` (from `get_agent`) for a bare brain check,
   then `https://voqalize.com/demos/orderdesk` for the full flow.
4. If a call misbehaves: `list_meetings(tenant="demo")` → `get_meeting` →
   `query_logs(tenant="demo", meeting_id=...)`.

## Local dev

The local control plane (voqalcloud, `localhost:8274`) serves the same API; the
demo UI's vite proxy already points `/api` there. Provision a local agent the
same way against the local console (or local MCP if running), with
`brain_url = "ws://localhost:8080/orderdesk"` (`ws://` is allowed for loopback),
then put its id + pk in `demos/orderdesk/frontend/.env`.

```bash
# local brains umbrella
cd demos && uv run uvicorn voqalize_demos.umbrella:app --reload --port 8080
# local UI
cd demos/orderdesk/frontend && pnpm install --ignore-workspace && pnpm dev
# → http://localhost:5760/demos/orderdesk/
```
