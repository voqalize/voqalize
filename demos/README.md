# demos — runnable Voqalize apps

Each demo is a complete voice app: a **brain** (a `voqalize.sdk.Brain` in
`backend/voqalize_demos/brains/<name>/`) and a **UI** (`frontend/src/<name>/`, one
entrypoint per demo). Every demo does triple duty — example code, the live demos
on our site, and our integration tests.

## One service, one domain, path-separated

All demos build into **one container** and deploy as **one Cloud Run service** at
`demos.voqalize.com` (`demos.dev.voqalize.com` for dev). A single umbrella
FastAPI app (`backend/voqalize_demos/umbrella.py`) hosts every brain and serves
the built UI; routing is by path:

| Path | Serves |
|---|---|
| `/{name}` | the demo's UI (a static entrypoint) |
| `/{name}/s/{session_id}` | the brain WebSocket (Voqalize dials here) |
| `/api/*` | reverse proxy to the control plane (session bootstrap) |

So a demo's `brain_url` is `wss://demos.voqalize.com/{name}`.

## Structure

```
demos/
  manifest.json         # the single registry both trees read (the spine)
  backend/              # shared pyproject (uv) — one FastAPI app, one Brain per demo
    voqalize_demos/
      umbrella.py        # the single FastAPI app: mounts every brain + /api proxy + static
      manifest.py        # backend half of the spine: name → Brain registry + check_wiring()
      llm.py             # GeminiProvider (the LLM the brains run on)
      brains/
        _gemini.py       # GeminiBrain base (context, tool loop, greeting helpers)
        <name>/brain.py  # one Brain subclass per demo
  frontend/             # shared package.json (pnpm), Vite MPA — one .html per demo
    <name>.html
    src/
      config.ts          # frontend half of the spine: per-demo wiring + manifest pipeline
      index/main.tsx     # landing page (manifest-driven)
      <name>/main.tsx    # the demo's UI entrypoint
  Dockerfile
  cloudbuild.yaml
```

The shared Python/JS config across demos is deliberate — these apps exist to
show *how an interactive voice+screen app works*, not to be independently
packaged.

## Adding a demo

A demo spans both trees, so `manifest.json` alone isn't enough. `check_wiring()`
validates the manifest↔brain-registry link at startup, and `config.ts` logs a
dev-console error if a manifest demo has no frontend entry — but the full set of
touch points is:

1. **`manifest.json`** — add an entry (`name`, `title`, `tagline`, `stt`, `tts`).
2. **Brain** — `backend/voqalize_demos/brains/<name>/brain.py` (a `Brain`, usually
   a `GeminiBrain` subclass) and register it in `manifest.py`'s `_BRAIN_FACTORIES`.
3. **UI entrypoint** — `frontend/<name>.html` + `frontend/src/<name>/main.tsx`.
   Vite picks the `.html` up automatically (its inputs are derived from the
   manifest).
4. **Frontend wiring** — a `DEMOS` entry in `frontend/src/config.ts`
   (`<name>: demo("<name>", import.meta.env.VITE_<NAME>_AGENT, import.meta.env.VITE_<NAME>_PK)`).
   This is manual because Vite inlines `import.meta.env.*` only from static
   literals, so it can't be generated from the manifest at build.
5. **Env** — `VITE_<NAME>_AGENT` / `VITE_<NAME>_PK` (add to `.env.example`, and to
   `cloudbuild.yaml` substitutions + build args for a deploy).
6. **Provisioning** — create the agent (Phase-4 step) and point its `brain_url` at
   `wss://{host}/<name>`.

## Running it

```bash
# Backend (umbrella FastAPI): brains + /api proxy + serves the built UIs.
cd demos/backend && uv run uvicorn voqalize_demos.umbrella:app --reload

# Frontend (Vite MPA) in dev — one entrypoint per demo, hot reload:
cd demos/frontend && cp .env.example .env   # fill in VITE_TRAVEL_AGENT / VITE_TRAVEL_PK
pnpm --filter @voqalize/demos-frontend dev   # http://localhost:5750
```

In a deploy the UIs are prebuilt into `frontend/dist` and the umbrella serves
them directly (one origin, path-separated); see `Dockerfile` / `cloudbuild.yaml`.

## Status

`travel` — the **Travel Advisor** — is built as the reference demo: a
`voqalize.sdk.Brain` (`backend/voqalize_demos/brains/travel/`) driven over the
inbound path, and a Vite UI (`frontend/src/travel/`) embedded via the public
`@voqalize/client-react` SDK. Its conformance test drives the real brain over the
`Vql*` wire. The remaining demos follow this same shape.
