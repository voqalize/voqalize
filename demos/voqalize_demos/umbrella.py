"""The umbrella app — one FastAPI process hosting every co-located demo backend.

Routing contract (see ``demos/README.md``):

- ``/{name}/s/{session_id}`` — a demo's brain WebSocket, contributed by its own
  ``demos/{name}/backend/routes.py`` and discovered at startup. Voqalize dials
  this per session; the SDK verifies Voqalize's RS256 brain token itself. Kept at
  the root, independent of where the UI is served.
- ``/api/{path}`` — optional reverse proxy to the control plane, so a demo UI
  served here can call ``sessions.create_and_start`` same-origin (no CORS, and the
  browser's ``Origin`` is forwarded for the publishable-key check). Enabled only
  when ``CONTROLPLANE_API_URL`` is set (deploys); local dev uses each demo's Vite
  proxy.
- ``/`` and ``/demos/{name}`` — the built demo UIs (an assembled multi-page app,
  one independent Vite build per demo under ``dist/demos/{name}``, plus the landing
  page at ``dist/index.html``). Served only when a built ``dist`` is present; in
  local dev each UI runs on its own Vite server and this app serves brains + proxy.
"""

from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from voqalize_demos.discovery import discover
from voqalize_demos.llm import GeminiProvider
from voqalize_demos.session import Settings, init_runtime

# Hop-by-hop headers that must not be forwarded through the /api proxy.
_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


def create_app() -> FastAPI:
    """Build the umbrella app: wire the shared runtime, discover and mount every
    co-located demo's brain router, then the optional API proxy and static UIs."""
    settings = Settings.from_env()
    llm = GeminiProvider(api_key=settings.gemini_api_key)
    init_runtime(settings, llm)

    demos = discover()
    demo_names = {d.name for d in demos}

    app = FastAPI(title="Voqalize demos")

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        return JSONResponse({"ok": True, "demos": sorted(demo_names)})

    # ─── Brain sockets (one router per co-located demo) ──────────────────
    for demo in demos:
        app.include_router(demo.router)
    logger.info("demos: mounted {} brains: {}", len(demos), sorted(demo_names))

    # ─── API reverse proxy (deploys) ────────────────────────────────────
    if settings.controlplane_api_url:
        _mount_api_proxy(app, settings.controlplane_api_url)
        logger.info("demos: /api → {}", settings.controlplane_api_url)

    # ─── Static UIs ─────────────────────────────────────────────────────
    if settings.frontend_dist.is_dir():
        _mount_static(app, demo_names, settings.frontend_dist)
        logger.info("demos: serving UIs from {}", settings.frontend_dist)
    else:
        logger.info("demos: no built UIs at {} — brains + proxy only", settings.frontend_dist)

    return app


def _mount_api_proxy(app: FastAPI, upstream: str) -> None:
    """Reverse-proxy ``/api/{path}`` to the control plane, forwarding method, body,
    query, and headers (incl. ``Origin`` for the publishable-key check)."""
    client = httpx.AsyncClient(base_url=upstream, timeout=30.0)

    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    async def api_proxy(path: str, request: Request) -> Response:
        headers = {k: v for k, v in request.headers.items() if k.lower() not in _HOP_BY_HOP}
        upstream_resp = await client.request(
            request.method,
            f"/api/{path}",
            content=await request.body(),
            params=request.query_params,
            headers=headers,
        )
        resp_headers = {
            k: v for k, v in upstream_resp.headers.items() if k.lower() not in _HOP_BY_HOP
        }
        return Response(
            content=upstream_resp.content,
            status_code=upstream_resp.status_code,
            headers=resp_headers,
        )


def _mount_static(app: FastAPI, demo_names: set[str], dist: Path) -> None:
    """Serve the assembled MPA. Each demo is an independent Vite build under
    ``dist/demos/{name}`` (built at base ``/demos/{name}/`` so its assets are
    self-referencing); the landing page is ``dist/index.html``.

    - ``/``                 → the landing page.
    - ``/demos/{name}``     → that demo's ``index.html``.
    - everything else       → a static file (assets, favicons) from ``dist``.
    """

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(dist / "index.html")

    @app.get("/demos/{name}")
    async def demo_page(name: str) -> Response:
        page = dist / "demos" / name / "index.html"
        if name in demo_names and page.is_file():
            return FileResponse(page)
        return JSONResponse({"error": "not found"}, status_code=404)

    # Static assets (JS/CSS/img) + the per-demo builds under /demos/{name}/assets.
    # Mounted last so the explicit routes above win; html=False so it doesn't
    # shadow ``/``.
    app.mount("/", StaticFiles(directory=dist, html=False), name="static")


# Uvicorn entrypoint: ``uvicorn voqalize_demos.umbrella:app``.
app = create_app()
