# syntax=docker/dockerfile:1
#
# The demos brains runtime — one image, every demo brain. This image is **brains
# only**: it runs the umbrella FastAPI app that hosts each demo's inbound brain
# WebSocket (dialed by Voqalize at /{name}/s/{session_id}). The demo UIs, docs, and
# marketing are built and served separately under the apex domain — no static files
# or Node toolchain here. Build context is the **repo root** (the backend depends on
# in-repo sdk/python by path):
#
#   docker build -f demos/Dockerfile -t <img> .
#
# All configuration is runtime env set on deploy (GEMINI_API_KEY, brain pubkeys) —
# nothing is baked at build.

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

# Install just the demos backend + its runtime deps.
RUN uv sync --package voqalize-demos --frozen --no-dev
ENV PATH="/repo/.venv/bin:$PATH"

EXPOSE 8080
CMD ["sh", "-c", "uvicorn voqalize_demos.umbrella:app --host 0.0.0.0 --port ${PORT:-8080}"]
