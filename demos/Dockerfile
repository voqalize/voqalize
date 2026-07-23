# syntax=docker/dockerfile:1
#
# The demos runtime — one image, every demo. Multi-stage: build + assemble the MPA
# (stage 1), then a Python runtime that runs the umbrella FastAPI app and serves
# the built UIs + brains (stage 2). Each demo and the landing page are independent
# Vite apps (demos/<name>/frontend, demos/landing/frontend); demos/build.mjs builds
# them all and assembles them into demos/dist. Build context is the **repo root**
# (the backend depends on in-repo sdk/python by path, each demo frontend on
# sdk/react by path):
#
#   docker build -f demos/Dockerfile -t <img> .
#
# The publishable VITE_* values are baked at build (browser-safe pk_ keys); the
# server-side secrets (GEMINI_API_KEY, brain pubkeys, control-plane URL) are
# runtime env set on deploy.

# ─── Stage 1: build + assemble the demo UIs (independent Vite apps) ──────────────
FROM node:20-slim AS frontend
RUN corepack enable && corepack prepare pnpm@10.32.1 --activate
WORKDIR /repo

# Publishable per-demo wiring. demos/build.mjs maps each demo's VITE_<NAME>_AGENT /
# VITE_<NAME>_PK (+ VITE_DEMO_TENANT) onto the app-local VITE_AGENT_ID /
# VITE_PUBLISHABLE_KEY / VITE_TENANT that each demo's src/config.ts reads.
ARG VITE_DEMO_TENANT
ARG VITE_TRAVEL_AGENT
ARG VITE_TRAVEL_PK
ARG VITE_SHOPPING_AGENT
ARG VITE_SHOPPING_PK
ARG VITE_SUPPORT_AGENT
ARG VITE_SUPPORT_PK
ARG VITE_SERVICING_AGENT
ARG VITE_SERVICING_PK
ARG VITE_INTERVIEW_BOT_AGENT
ARG VITE_INTERVIEW_BOT_PK
ARG VITE_SUGAR_AGENT
ARG VITE_SUGAR_PK
ARG VITE_LEGAL_AGENT
ARG VITE_LEGAL_PK
ARG VITE_LEAD_QUAL_AGENT
ARG VITE_LEAD_QUAL_PK
ARG VITE_AURA_AGENT
ARG VITE_AURA_PK
ENV VITE_DEMO_TENANT=$VITE_DEMO_TENANT \
    VITE_TRAVEL_AGENT=$VITE_TRAVEL_AGENT \
    VITE_TRAVEL_PK=$VITE_TRAVEL_PK \
    VITE_SHOPPING_AGENT=$VITE_SHOPPING_AGENT \
    VITE_SHOPPING_PK=$VITE_SHOPPING_PK \
    VITE_SUPPORT_AGENT=$VITE_SUPPORT_AGENT \
    VITE_SUPPORT_PK=$VITE_SUPPORT_PK \
    VITE_SERVICING_AGENT=$VITE_SERVICING_AGENT \
    VITE_SERVICING_PK=$VITE_SERVICING_PK \
    VITE_INTERVIEW_BOT_AGENT=$VITE_INTERVIEW_BOT_AGENT \
    VITE_INTERVIEW_BOT_PK=$VITE_INTERVIEW_BOT_PK \
    VITE_SUGAR_AGENT=$VITE_SUGAR_AGENT \
    VITE_SUGAR_PK=$VITE_SUGAR_PK \
    VITE_LEGAL_AGENT=$VITE_LEGAL_AGENT \
    VITE_LEGAL_PK=$VITE_LEGAL_PK \
    VITE_LEAD_QUAL_AGENT=$VITE_LEAD_QUAL_AGENT \
    VITE_LEAD_QUAL_PK=$VITE_LEAD_QUAL_PK \
    VITE_AURA_AGENT=$VITE_AURA_AGENT \
    VITE_AURA_PK=$VITE_AURA_PK

# The SDK each demo links by path (file:../../../sdk/react) + the demos tree, then
# build & assemble every UI into demos/dist. (node_modules/dist are .dockerignored,
# so each app installs fresh inside the image.)
COPY sdk/react ./sdk/react
COPY demos ./demos
RUN node demos/build.mjs

# ─── Stage 2: Python runtime (umbrella app) ─────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS runtime
WORKDIR /repo
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Workspace + member manifests for a cached dependency layer.
COPY pyproject.toml uv.lock ./
COPY sdk/python/pyproject.toml ./sdk/python/
COPY mcp/pyproject.toml ./mcp/
COPY demos/pyproject.toml ./demos/

# Path-dep source (sdk/python) + the demos tree: the shared backend package
# (voqalize_demos) plus each demo's backend/, which discovery loads from source.
COPY sdk/python ./sdk/python
COPY demos ./demos

# The assembled UIs from stage 1 (served by the umbrella at / and /demos/{name}).
COPY --from=frontend /repo/demos/dist ./demos/dist

# Install just the demos backend + its runtime deps.
RUN uv sync --package voqalize-demos --frozen --no-dev
ENV PATH="/repo/.venv/bin:$PATH"

EXPOSE 8080
CMD ["sh", "-c", "uvicorn voqalize_demos.umbrella:app --host 0.0.0.0 --port ${PORT:-8080}"]
