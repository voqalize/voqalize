# demos — runnable Voqalize apps

Each demo is a complete voice app: a **brain** (`backend/<name>/`, its own
FastAPI app) and a **UI** (`frontend/`, one entrypoint per demo). Every demo
does triple duty — example code, the live demos on our site, and our integration
tests.

## One service, one domain, path-separated

All demos build into **one container** and deploy as **one Cloud Run service** at
`demos.voqalize.com` (`demos.dev.voqalize.com` for dev). Routing is by path — an
umbrella FastAPI app mounts each demo and serves the built UI:

| Path | Serves |
|---|---|
| `/{name}` | the demo's UI (a static entrypoint) |
| `/{name}/s/{session_id}` | the brain WebSocket (Voqalize dials here) |
| `/{name}/api/*` | optional demo-specific REST |

So a demo's `brain_url` is `wss://demos.voqalize.com/{name}`.

## Structure

```
demos/
  backend/        # shared pyproject (uv); each demo = a FastAPI module
    <name>/
    umbrella.py   # mounts every demo + serves the static build
    manifest.py   # the single registry: drives mounts, UI entrypoints, provisioning
  frontend/       # shared package.json (pnpm), Vite MPA — one .html per demo
  Dockerfile
  cloudbuild.yaml
```

The shared Python/JS config across demos is deliberate — these apps exist to
show *how an interactive voice+screen app works*, not to be independently
packaged.

> Skeleton not built yet — build order step 3. `travel` lands first as the
> reference demo.
