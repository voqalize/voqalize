# Seeding OrderDesk in production

Agent management on the control plane is Google-OAuth only (session cookie or the
hosted MCP) — there is deliberately no headless key path for `agents.create`, so
this seed is a sequence of **Voqalize MCP tool calls**, executable by any agent
session with the MCP connected:

```bash
claude mcp add --transport http voqalize https://app.voqalize.com/mcp/
```

`/mcp/` is the streamable endpoint and the URL to configure; `/mcp` redirects to
it. The OAuth is interactive, so if you are
already signed in to the console it is usually faster to just drive the console
UI (`https://app.voqalize.com/{tenant}`) — it exposes every field this runbook
needs, including the STT/TTS ones the MCP `create_agent` does not.

## 1. Identify

```
whoami()                      # sanity: the authenticated developer
list_tenants()                # confirm membership of the demos tenant (slug: aCxzYVYr)
```

The demos tenant is `aCxzYVYr` in **both** environments — dev and prod hold
tenant docs with the same id, and most demo agents carry the same agent id in
both, because prod was seeded by copying the dev data on 2026-07-15. Two
consequences worth knowing before you debug anything here:

- The two are still separate databases. A few agents diverge (`forge`, `sugar`
  have distinct prod ids) because they were re-created per environment to carry a
  different `brain_url`. Never assume a dev agent id resolves in prod — check.
- That copy did **not** bring the tenant's `members` subcollection across, so
  until 2026-08-04 no console account could administer the prod demos tenant
  (`agents.list` → `401 not_authenticated: "Not a member of this tenant"`). It
  was repaired by writing one owner member doc into
  `tenants/06a210d7-76ce-7aa5-8000-d527fbd51277/members` in `voqal-cloud-prod`
  Firestore, mirroring the dev doc's shape. If a fresh migration ever re-creates
  the tenant, expect to redo that.

## 2. Create the agent (idempotent by name — check first)

```
list_agents(tenant="aCxzYVYr")   # if "OrderDesk" already exists, skip to update_agent
create_agent(
  tenant      = "aCxzYVYr",
  name        = "OrderDesk",
  description = "B2B order intake for a pharma distributor — Hindi voice, 20k-SKU catalog resolution on screen.",
  brain_url   = "wss://brain.voqalize.com/orderdesk",   # dev: wss://brain.dev.voqalize.com/orderdesk
)
# → {agent: {id: <AGENT_ID>, test_url: ...}, session_key: sk_... (shown once; not needed for the demo page)}
```

If the agent pre-exists or the brain URL changes:
`update_agent(tenant="aCxzYVYr", agent_id=<AGENT_ID>, brain_url="wss://brain.voqalize.com/orderdesk")`

Already seeded (2026-08-04) — dev `06a718d5-5146-72ee-8000-a21174efbf9a`,
prod `06a71907-1d6a-7bab-8000-9812748d2673`. They differ, as they must: the
`brain_url` is what separates the two environments.

### The language does not have to come from the agent record

`create_agent`/`update_agent` expose no STT/TTS fields, so an agent seeded over
MCP is created with platform defaults — **English** STT (`stt.language_hint`
unset ⇒ Parakeet) and the English `omnivoice/gaurav` voice. That is survivable:
this demo sets its pipeline **per session** from the browser
(`frontend/src/config.ts` → `pipeline`), which PyGato layers over the record
field by field.

The **console UI does expose them**, though — an agent's Configuration panel has
Brain URL, STT model/language/language hint, and TTS model/voice/language. Both
the dev and prod OrderDesk records were seeded through it, so both carry
`stt.language = hi`, `stt.language_hint = hi`, `tts.voice = omnivoice/gauri`,
`tts.language = hi` on the record as well as in the per-session override. Prefer
that: agreeing config is harmless (the override is field-level) and it means a
session that forgets to send a pipeline still opens in Hindi.

A freshly created agent shows `draft` until a brain first connects; the demo
works from `draft`, so don't chase it.

Two things must stay true either way, or the call breaks in a way that looks like
bad recognition rather than bad config:

- `stt.language_hint: "hi"` — PyGato reads `language_hint`, **not** `language`,
  when choosing the recognition engine. Sending only `language: "hi"` silently
  transcribes Hindi with an English model.
- `tts.voice: "omnivoice/gauri"` + `tts.language: "hi"` — both read from the
  override, so the record's English defaults never surface.

## 3. Mint the browser key

```
create_api_key(
  tenant          = "aCxzYVYr",
  label           = "orderdesk-demos-prod",           # dev: orderdesk-demos-dev
  kind            = "publishable",
  allowed_origins = ["https://voqalize.com"],         # dev: https://dev.voqalize.com
)
# → pk_...  (shown once — capture it)
```

The label convention is `<demo>-demos-{dev,prod}`, and the origin is the one
apex that serves the demo — one per environment, because a demo page calls
`/api/v1` same-origin (Hosting rewrites it to Cloud Run), so the `Origin` the
browser sends on `sessions.connect` is the apex itself.

**An empty list is refused**, and it used to be the instruction here: every demo
key was minted origin-unrestricted until `backfill_pk_origins.py` pinned each one
to its apex. `resolve_allowed_origins` now raises
`PUBLISHABLE_KEY_REQUIRES_ORIGINS` rather than mint a key that every request
would reject anyway — so a runbook that still says "leave it empty" fails at
step 3 rather than in production.

Note that a demo bundle inlines *every* `VITE_*` value, not just its own — so
all the demo publishable keys ship in each app's JS. That is what the origin
pin is for: a key lifted out of one bundle is still only usable from the apex it
names. It also means the keys travel together, so a key minted against the wrong
apex is served from twelve pages, not one.

## 4. Wire the web build

Set the two new substitutions on the `build-demos-web` trigger — **once per
project**, `voqal-cloud-dev` and `voqal-cloud-prod`, both in region
`asia-south1` (they are not global; `gcloud builds triggers list` without
`--region` returns empty):

```
_ORDERDESK_AGENT = <AGENT_ID>
_ORDERDESK_PK    = <pk_...>
```

`gcloud builds triggers update` cannot add substitutions here. Use the beta
export/import round-trip instead — note `beta`, the non-beta `export` verb does
not exist:

```bash
gcloud beta builds triggers export build-demos-web \
  --project=voqal-cloud-prod --region=asia-south1 --destination=t.yaml
# edit t.yaml, adding the two keys under substitutions:
gcloud beta builds triggers import \
  --project=voqal-cloud-prod --region=asia-south1 --source=t.yaml
rm -f t.yaml   # it contains every demo's pk in cleartext
```

(`demos/cloudbuild.web.yaml` in this repo already declares the placeholders and
maps them to `VITE_ORDERDESK_AGENT` / `VITE_ORDERDESK_PK`; `build.mjs` folds them
into the app's `VITE_AGENT_ID` / `VITE_PUBLISHABLE_KEY`.)

## 5. Deploy + verify

1. Brains: **both** environments deploy off the same `^main$` push — the dev and
   prod brains triggers watch the same public repo, so one push builds both.
   `_EXPECTED_DEMOS` in `cloudbuild.brains-vm.yaml` counts the demos, so a new
   one bumps it — but the yaml default is **overridden by a trigger substitution
   of the same name**, on `deploy-brains-vm` (dev) and `deploy-brains-vm-prod`.
   Bump all three, or the container deploys fine and the verify step still fails
   with `expected 11 demos, got 12`. `gcloud builds triggers update` cannot reach
   a substitution either; use the same export/import round-trip as step 4.
2. Web: the web trigger → Pub/Sub (`web-artifact-built`) → marketing deploy lays
   `/demos/orderdesk` under the apex. A web build that started *before* the
   substitutions were written bakes empty values, so re-run the trigger after
   step 4 rather than trusting the push-triggered one.
3. Smoke: open the agent's `test_url` (from `get_agent`) for a bare brain check,
   then `https://voqalize.com/demos/orderdesk` for the full flow.
4. If a call misbehaves: `list_sessions(tenant="aCxzYVYr")` → `get_session_events` →
   `get_session_logs(tenant="aCxzYVYr", session_id=...)`.

## Local dev

The local control plane (voqalcloud) serves the same API on the same host as the
local console, `app.local.voqalize.com` — the deployed convention with one DNS
label changed. Provision a local agent the same way there (or over local MCP if
it is running), with `brain_url = "wss://brain.local.voqalize.com/orderdesk"`,
then put its id + pk in `demos/orderdesk/frontend/.env`.

```bash
# both halves, supervised — ports live in ecosystem.config.cjs and nowhere else
pm2 start ecosystem.config.cjs
# → https://local.voqalize.com/demos/orderdesk/ , brain at brain.local.voqalize.com
```

Standalone still works if you want one demo and no nginx — `cd demos && uv run
uvicorn voqalize_demos.umbrella:app --reload --port 8080` plus `cd
demos/orderdesk/frontend && pnpm dev` — with `brain_url = "ws://localhost:8080/orderdesk"`
(`ws://` is allowed for loopback).
