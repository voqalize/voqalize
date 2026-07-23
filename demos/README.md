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

## One service, one domain, path-separated

All demos build into **one container** and deploy as **one Cloud Run service** at
`demos.voqalize.com` (`demos.dev.voqalize.com` for dev). A single umbrella
FastAPI app (`voqalize_demos/umbrella.py`) discovers every co-located backend,
hosts its brain, reverse-proxies the API, and serves the assembled UIs. Routing
is by path:

| Path | Serves |
|---|---|
| `/` | the landing page (the demo directory) |
| `/demos/{name}` | the demo's UI (its own independent Vite build) |
| `/{name}/s/{session_id}` | the brain WebSocket (Voqalize dials here) |
| `/api/*` | reverse proxy to the control plane (session bootstrap) |

The **UI path** (`/demos/{name}`) and the **brain path** (`/{name}/s/{id}`) are
independent: the brain socket stays at the root because Voqalize dials it
server-side regardless of where the browser loads the UI. So a demo's `brain_url`
is `wss://demos.voqalize.com/{name}`.

## Structure

```
demos/
  manifest.json          # the landing directory: title + tagline per demo (cards only)
  build.mjs              # builds every UI + the landing page → assembles demos/dist
  pyproject.toml         # ONE shared backend package (uv) for all demos
  voqalize_demos/        # the shared backend spine
    umbrella.py           # the single FastAPI app: discovers + mounts brains, /api proxy, static
    discovery.py          # scans demos/*/backend, loads each router from source
    session.py            # the shared per-session WebSocket handler (make_brain_router)
    _gemini.py            # GeminiBrain base (context, tool loop, greeting helpers)
    llm.py                # GeminiProvider (the LLM the brains run on)
  landing/
    frontend/             # the landing page — a standalone Vite app, built at base /
  <name>/
    frontend/             # the demo UI — a standalone Vite app, built at base /demos/<name>/
      package.json         #   links the SDK by path: "@voqalize/client-react": "file:../../../sdk/react"
      vite.config.ts       #   base: "/demos/<name>/", dev proxy /api → control plane
      src/config.ts        #   this demo's wiring: tenant + agent id + pk + pipeline
      src/…                #   the app
    backend/
      brain.py             # the demo's Brain (usually a GeminiBrain subclass)
      routes.py            # one line: router = make_brain_router("<name>", lambda llm: <Name>Brain(llm=llm))
      __init__.py          # re-exports NAME, build, router
  Dockerfile
  cloudbuild.yaml
```

Each **frontend** is fully self-contained (its own `package.json` + lockfile +
`node_modules`); it depends on the published `@voqalize/client-react` SDK — until
that's on npm, by path via `file:../../../sdk/react`. Each **backend** is thin and
shares the one `voqalize_demos` package; the umbrella discovers routers by
scanning `demos/*/backend`, so nothing binds names in a central registry.

## Adding a demo

`manifest.json` is only the landing-page card now — the runtime discovers
backends and each frontend declares its own wiring. To add `demos/<name>/`:

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
   a `src/config.ts` declaring this demo's `pipeline` (stt/tts).
3. **Env** — `VITE_TENANT` / `VITE_AGENT_ID` / `VITE_PUBLISHABLE_KEY` (this app's
   `.env.example`). For a deploy, add the demo's `VITE_<NAME>_AGENT` /
   `VITE_<NAME>_PK` to `cloudbuild.yaml` substitutions + `Dockerfile` build args
   (`build.mjs` maps them onto the app-local names).
4. **Card** — add an entry (`name`, `title`, `tagline`) to `manifest.json` so it
   shows on the landing page.
5. **Provisioning** — create the agent and point its `brain_url` at
   `wss://{host}/<name>`.

## Running it

Each demo UI runs on its own Vite dev server; the backend runs once and serves
every brain + the `/api` proxy.

```bash
# Backend (umbrella FastAPI): brains + /api proxy. No built UIs in dev.
cd demos && uv run uvicorn voqalize_demos.umbrella:app --reload --port 8080

# A demo UI in dev — standalone, hot reload (proxies /api to the control plane):
cd demos/travel/frontend
cp .env.example .env          # fill in VITE_AGENT_ID / VITE_PUBLISHABLE_KEY
pnpm install --ignore-workspace
pnpm dev                      # http://localhost:5751/demos/travel/
```

To build and assemble every UI the way the container serves them:

```bash
node demos/build.mjs          # builds the SDK + every UI + landing → demos/dist/
```

In a deploy `build.mjs` runs in the image's build stage and the umbrella serves
`demos/dist` directly (one origin, path-separated); see `Dockerfile` /
`cloudbuild.yaml`.

## Status

`travel` — the **Travel Advisor** — is the reference demo: a `voqalize.sdk.Brain`
(`demos/travel/backend/`) driven over the inbound path, and a standalone Vite UI
(`demos/travel/frontend/`) embedded via the public `@voqalize/client-react` SDK.
Its conformance test (`demos/tests/`) drives the real brain over the `Vql*` wire.
The remaining demos follow this same shape.
