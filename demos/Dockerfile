# syntax=docker/dockerfile:1
#
# The demos brains runtime — one image, every demo brain. This image is **brains
# only**: it runs the umbrella FastAPI app that hosts each demo's inbound brain
# WebSocket (dialed by Voqalize at /{name}?session_id=…). The demo UIs, docs, and
# marketing are built and served separately under the apex domain — no static files
# or Node toolchain here. Build context is the **repo root** (the backend depends on
# in-repo sdk/python by path):
#
#   docker build -f demos/Dockerfile -t <img> .
#
# All *configuration* is runtime env set on deploy (GEMINI_API_KEY, brain pubkeys).
# The one thing baked at build is the commit (`GIT_SHA`), because a deployed
# container that cannot say what it is forces an SSH to find out — see the ARG at
# the bottom, deliberately placed after every COPY so it busts no cached layer.
# Secrets arrive either natively (Cloud Run) or
# base64-encoded and single-line (the VM deploy, whose `--env-file` cannot carry a
# multi-line PEM) — see demos/docker-entrypoint.sh, which decodes `FOO_B64` → `FOO`
# and is a no-op when no such var is set.

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS runtime
WORKDIR /repo
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Workspace + member manifests for a cached dependency layer.
COPY pyproject.toml uv.lock ./
COPY sdk/python/pyproject.toml ./sdk/python/
COPY demos/pyproject.toml ./demos/

# Path-dep source (sdk/python) + the demos tree: the shared backend package
# (voqalize_demos) plus each demo's backend/, which discovery loads from source.
COPY sdk/python ./sdk/python
COPY demos ./demos

# Install just the demos backend + its runtime deps.
RUN uv sync --package voqalize-demos --frozen --no-dev
ENV PATH="/repo/.venv/bin:$PATH"

RUN chmod +x /repo/demos/docker-entrypoint.sh

# The commit this image was built from, surfaced at GET /_healthz. Last, so a
# new SHA invalidates nothing above it — the whole dependency install stays
# cached. Empty on a plain `docker build` with no --build-arg, which reads as
# "unknown" rather than lying.
ARG GIT_SHA=""
ENV VOQALIZE_GIT_SHA=$GIT_SHA

EXPOSE 8080
ENTRYPOINT ["/repo/demos/docker-entrypoint.sh"]
CMD ["sh", "-c", "uvicorn voqalize_demos.umbrella:app --host 0.0.0.0 --port ${PORT:-8080}"]
