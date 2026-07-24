"""The umbrella app — one FastAPI process hosting every co-located demo brain.

This image is **brains only**. It exposes one thing:

- ``/{name}/s/{session_id}`` — a demo's brain WebSocket, contributed by its own
  ``demos/{name}/backend/routes.py`` and discovered at startup. Voqalize dials
  this per session; the SDK verifies Voqalize's RS256 brain token itself.

The demo UIs and the ``/api`` control-plane call are **not** served here anymore.
The assembled MPA (marketing + docs + every demo UI) is built elsewhere and served
under the apex domain (``dev.voqalize.com`` / ``voqalize.com``), where the browser
mints a session same-origin (Firebase Hosting rewrites ``/api`` → control plane).
So this runtime carries no static files and no reverse proxy — just the brain
sockets Voqalize dials server-side. Its URL (``demos.<env>.voqalize.com``) is the
``brain_url`` each demo agent stores; the browser never touches it.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from loguru import logger

from voqalize_demos.discovery import discover
from voqalize_demos.llm import GeminiProvider
from voqalize_demos.session import Settings, init_runtime


def create_app() -> FastAPI:
    """Build the umbrella app: wire the shared runtime, then discover and mount
    every co-located demo's brain router."""
    settings = Settings.from_env()
    llm = GeminiProvider(api_key=settings.gemini_api_key)
    init_runtime(settings, llm)

    demos = discover()
    demo_names = {d.name for d in demos}

    app = FastAPI(title="Voqalize demos")

    # Not ``/healthz``: on *.run.app the Google Frontend swallows the exact path
    # ``/healthz`` before it reaches the app. ``/_healthz`` is reachable.
    @app.get("/_healthz")
    async def healthz() -> JSONResponse:
        return JSONResponse({"ok": True, "demos": sorted(demo_names)})

    # ─── Brain sockets (one router per co-located demo) ──────────────────
    for demo in demos:
        app.include_router(demo.router)
    logger.info("demos: mounted {} brains: {}", len(demos), sorted(demo_names))

    return app


# Uvicorn entrypoint: ``uvicorn voqalize_demos.umbrella:app``.
app = create_app()
