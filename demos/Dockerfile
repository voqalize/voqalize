# syntax=docker/dockerfile:1
#
# The demos runtime — one image, every demo. Multi-stage: build the Vite MPA
# (stage 1), then a Python runtime that runs the umbrella FastAPI app and serves
# the built UIs (stage 2). Build context is the **repo root** (the backend depends
# on the in-repo `sdk/python` by path, the frontend on `sdk/react`):
#
#   docker build -f demos/Dockerfile -t <img> .
#
# The publishable `VITE_*` values are baked at build (browser-safe pk_ keys); the
# server-side secrets (GEMINI_API_KEY, brain pubkeys, control-plane URL) are
# runtime env set on deploy.

# ─── Stage 1: build the demo UIs (Vite MPA) ─────────────────────────────────────
FROM node:20-slim AS frontend
RUN corepack enable
WORKDIR /repo

# Workspace + member manifests first, for a cached install layer.
COPY pnpm-workspace.yaml pnpm-lock.yaml package.json ./
COPY sdk/react/package.json ./sdk/react/
COPY demos/frontend/package.json ./demos/frontend/
RUN pnpm install --frozen-lockfile

# Publishable demo wiring, inlined by Vite at build (see demos/frontend/src/config.ts).
ARG VITE_DEMO_TENANT
ARG VITE_TRAVEL_AGENT
ARG VITE_TRAVEL_PK
ENV VITE_DEMO_TENANT=$VITE_DEMO_TENANT \
    VITE_TRAVEL_AGENT=$VITE_TRAVEL_AGENT \
    VITE_TRAVEL_PK=$VITE_TRAVEL_PK

# Sources, then build the SDK and the demo UIs.
COPY sdk/react ./sdk/react
COPY demos/manifest.json ./demos/manifest.json
COPY demos/frontend ./demos/frontend
RUN pnpm --filter @voqalize/client-react build \
 && pnpm --filter @voqalize/demos-frontend build

# ─── Stage 2: Python runtime (umbrella app) ─────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS runtime
WORKDIR /repo
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Workspace + member manifests for a cached dependency layer.
COPY pyproject.toml uv.lock ./
COPY sdk/python/pyproject.toml ./sdk/python/
COPY mcp/pyproject.toml ./mcp/
COPY demos/backend/pyproject.toml ./demos/backend/

# Path-dep sources the demos backend builds against, then the backend itself.
COPY sdk/python ./sdk/python
COPY demos/manifest.json ./demos/manifest.json
COPY demos/backend ./demos/backend

# The built UIs from stage 1 (served by the umbrella at /{name}).
COPY --from=frontend /repo/demos/frontend/dist ./demos/frontend/dist

# Install just the demos backend + its runtime deps.
RUN uv sync --package voqalize-demos --frozen --no-dev
ENV PATH="/repo/.venv/bin:$PATH"

EXPOSE 8080
CMD ["sh", "-c", "uvicorn voqalize_demos.umbrella:app --host 0.0.0.0 --port ${PORT:-8080}"]
