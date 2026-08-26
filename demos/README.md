# demos — runnable Voqalize apps

Each demo is a complete voice app, **co-located in one folder** so a client
developer (or their coding agent) can read one demo end-to-end without hopping
across the tree:

```
demos/<name>/
  frontend/   # a self-contained Vite app — its own package.json, lockfile, build
  backend/    # a thin brain: brain.py (a voqalize.sdk.Brain) + a one-line routes.py
```

Every demo does triple duty — example code, the live demos on our site, and our
integration tests.

## Two builds: brains run on the voice-runtime node, UIs ship to the apex

A demo's two halves deploy to two different places, and that split is the whole
architecture:

- **The backend brains** build into **one container** and deploy onto the
  **pygato node**, fronted by Caddy at `brain.voqalize.com`
  (`brain.dev.voqalize.com` for dev). A single umbrella FastAPI app
  (`voqalize_demos/umbrella.py`) discovers every co-located backend and hosts
  its brain WebSocket at `/{name}?session_id=…`. That's *all* this container
  does — it's brains only. See `Dockerfile` + `cloudbuild.brains-vm.yaml`.
- **The frontend UIs** (plus the docs) build into a versioned **web artifact**
  (`cloudbuild.web.yaml`) that the private marketing repo downloads and lays under
  the **apex domain** (`voqalize.com` / `dev.voqalize.com`) at `/demos/{name}`.
  There the browser mints a session same-origin — the apex's Firebase Hosting
  rewrites `/api/*` to the control plane — so nothing about session bootstrap
  touches the brain container.

The **UI path** (`{apex}/demos/{name}`) and the **brain path**
(`wss://brain.voqalize.com/{name}`) are independent: the brain socket lives
on the pygato node because Voqalize dials it **server-side**, regardless of where
the browser loads the UI. So a demo's `brain_url` is `wss://brain.voqalize.com/{name}`
— and moving the UI to the apex needed no agent re-provisioning at all.

| Path | Serves | Where |
|---|---|---|
| `{apex}/demos/{name}` | the demo's UI (its own independent Vite build) | apex (Firebase Hosting) |
| `{apex}/api/*` | session bootstrap → control plane (Hosting rewrite) | apex |
| `wss://brain.<env>.voqalize.com/{name}` | the brain WebSocket (Voqalize dials here) | pygato node (brains container, behind Caddy) |

## Structure

```
demos/
  manifest.json          # the demo directory: name + title + tagline per demo;
                         #   shipped inside the web artifact so marketing renders /demos
  build.mjs              # builds every UI → assembles demos/dist/demos/<name>/
  Dockerfile                # brains-only Python image (no Node stage)
  cloudbuild.brains-vm.yaml # Build A: brains image → pygato node (public repo trigger)
  cloudbuild.web.yaml       # Build B: UIs + docs → versioned web artifact in GCS
  pyproject.toml         # ONE shared backend package (uv) for all demos
  voqalize_demos/        # the shared backend spine
    umbrella.py           # the single FastAPI app: discovers + mounts brain routers
    discovery.py          # scans demos/*/backend, loads each router from source
    session.py            # the shared per-session WebSocket handler (make_brain_router)
    _gemini.py            # GeminiBrain base (context, tool loop, greeting helpers)
  <name>/
    frontend/             # the demo UI — a standalone Vite app, built at base /demos/<name>/
      package.json         #   stock @pipecat-ai/client-react + @voqalize/demo-kit: "file:../../shared"
      vite.config.ts       #   base: "/demos/<name>/", dev proxy /api → control plane
      src/config.ts        #   this demo's wiring: tenant + agent id + pk (NO voice/language)
      src/…                #   the app
    backend/
      brain.py             # the demo's Brain (usually a GeminiBrain subclass)
      routes.py            # one line: router = make_brain_router("<name>", lambda llm: <Name>Brain(llm=llm))
      __init__.py          # re-exports NAME, build, router
```

Each **frontend** is fully self-contained (its own `package.json` + lockfile +
`node_modules`); it depends on stock `@pipecat-ai/client-react` plus
`@voqalize/demo-kit` (`demos/shared`, the pre-call gate and ambient ring shared
across the gallery) — there is no Voqalize-authored client wrapper any more.
Each **backend** is thin and
shares the one `voqalize_demos` package; the umbrella discovers routers by
scanning `demos/*/backend`, so nothing binds names in a central registry.

## Adding a demo

`manifest.json` is the demo directory (cards for the `/demos` index) — the runtime
discovers backends and each frontend declares its own connection wiring. To add
`demos/<name>/`:

1. **Backend** — `demos/<name>/backend/`:
   - `brain.py`: a `Brain` (usually a `GeminiBrain` subclass, importing its base
     from `voqalize_demos`).
   - `routes.py`: `NAME = "<name>"`, `def build(llm): return <Name>Brain(llm=llm)`,
     `router = make_brain_router(NAME, build)`.
   - `__init__.py`: `from .routes import NAME, build, router`.
   Discovery asserts `NAME` equals the folder name.
2. **Frontend** — `demos/<name>/frontend/`: a standalone Vite app. Copy an
   existing demo's `package.json` / `vite.config.ts` (set `base: "/demos/<name>/"`
   and a unique dev `port`) / `tsconfig.json` / `index.html` / `.env.example`, and
   a `src/config.ts` declaring only the connection wiring. **Voice and language do
   not live here** — the agent record carries the default and the brain overrides
   it per caller (`await session.configure(Config(stt=…, tts=…))`), because that is
   the only place the STT and TTS legs move together. Setting one leg from the page is the
   half-applied-pair bug, and it is silent: the words stay right and only the
   speaker is wrong.
3. **Env** — `VITE_AGENT_ID` / `VITE_PUBLISHABLE_KEY` (this app's
   `.env.example`). For a deploy, add the demo's `VITE_<NAME>_AGENT` /
   `VITE_<NAME>_PK` to `cloudbuild.web.yaml` substitutions (`build.mjs` maps them
   onto the app-local names).
4. **Card** — add an entry (`name`, `title`, `tagline`) to `manifest.json` so it
   shows on the `/demos` index.
5. **Provisioning** — create the agent and point its `brain_url` at
   `wss://{host}/<name>`.

## Running it

`pm2 start ecosystem.config.cjs` from the repo root is the supervised path: the
brains umbrella at `brain.local.voqalize.com` and every UI at
`local.voqalize.com/demos/<name>` — the same apex layout production serves, so a
demo mints its session same-origin exactly as it does deployed. Ports are
declared in that file and nowhere else.

Standalone, one demo at a time, no nginx: each demo UI runs on its own Vite dev
server; the backend runs once and serves every brain.

```bash
# Backend (umbrella FastAPI): brains only. No built UIs, no /api proxy in dev.
cd demos && uv run uvicorn voqalize_demos.umbrella:app --reload --port 8080

# A demo UI in dev — standalone, hot reload (proxies /api to the control plane):
cd demos/travel/frontend
cp .env.example .env          # fill in VITE_AGENT_ID / VITE_PUBLISHABLE_KEY
pnpm install --ignore-workspace
pnpm dev                      # open the URL it prints, at /demos/travel/
```

To build and assemble every UI the way the web artifact ships them:

```bash
node demos/build.mjs          # builds the SDK + every UI → demos/dist/demos/<name>/
```

In a deploy `cloudbuild.web.yaml` runs `build.mjs`, tars `demos/dist` + the built
docs + `manifest.json` into a versioned artifact, and the private marketing build
lays it under the apex. The brains image (`Dockerfile` / `cloudbuild.brains-vm.yaml`)
ships separately, onto the pygato node.

## Status

`travel` — the **Travel Advisor** — is the reference demo: a `voqalize.sdk.Brain`
(`demos/travel/backend/`) driven over the inbound path, and a standalone Vite UI
(`demos/travel/frontend/`) built on stock pipecat (`@pipecat-ai/client-react`) plus
`@voqalize/demo-kit`. The remaining demos follow this same shape.

**Every demo has an end-to-end test** (`demos/tests/test_<name>_e2e.py`): the real
brain on a real `brain_server` socket, driven by the conformance `VoqalizeDriver`,
with only the *model* faked — `ScriptedGemini` (`demos/voqalize_demos/testing.py`)
for all eleven demos; ADK and its `ScriptedLlm` are gone from the repo. Plus
`test_demo_voice_contract.py`, a cross-demo sweep that asserts every demo puts a
**matched** voice/language pair on both legs before its first audio — the one
defect no transcript, log or WER score can see.

```bash
cd demos && uv run pytest tests/
```
