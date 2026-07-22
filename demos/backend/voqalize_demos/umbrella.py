"""The umbrella app — one FastAPI process hosting every demo, path-separated.

Routing contract (see ``demos/README.md``):

- ``/{name}/s/{session_id}`` — the brain WebSocket. Voqalize dials this per
  session; we adapt the FastAPI socket to the SDK ``Channel`` and hand it to
  ``run_session`` with the brain bound to ``{name}`` in the manifest. This is the
  **inbound** path — the SDK verifies Voqalize's RS256 brain token itself.
- ``/api/{path}`` — optional reverse proxy to the control plane, so a demo UI
  served here can call ``sessions.create_and_start`` same-origin (no CORS, and the
  browser's ``Origin`` is forwarded for the publishable-key check). Enabled only
  when ``CONTROLPLANE_API_URL`` is set (deploys); local dev uses the Vite proxy.
- ``/`` and ``/{name}`` — the built demo UIs (a static Vite MPA). Served only when
  a built ``frontend/dist`` is present; in local dev the UIs run on their own Vite
  server and this app serves brains + proxy only.
"""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Response, WebSocket
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from starlette.websockets import WebSocketDisconnect

from voqalize.sdk import SessionRejected, run_session
from voqalize_demos.llm import GeminiProvider
from voqalize_demos.manifest import brain_factory, check_wiring

# Voqalize's Wire treats a 4000 close as permanent (non-retriable) — used for both
# an unknown demo and a rejected token; 1011 is retriable (a transient fault).
_CLOSE_PERMANENT = 4000
_CLOSE_INTERNAL = 1011

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


_PEM_END = "-----END PUBLIC KEY-----"


def _split_pem_bundle(raw: str) -> tuple[str, ...]:
    """Split a PEM bundle — one or more concatenated public keys in one env value —
    into individual PEMs. The SDK's ``public_keys=`` accepts a list and tries each
    in turn, so a bundle lets one deploy trust several signers at once (e.g. during
    a key rotation). A single key yields a one-element tuple; empty input, empty."""
    keys: list[str] = []
    for chunk in raw.split(_PEM_END):
        block = chunk.strip()
        if block:
            keys.append(f"{block}\n{_PEM_END}")
    return tuple(keys)


@dataclass(frozen=True)
class Settings:
    """Process configuration, all from the environment."""

    gemini_api_key: str
    # PEM public key(s) to verify Voqalize's brain token against; empty → the SDK's
    # embedded platform keys (prod signer only). A dev deploy MUST set this to dev
    # PyGato's signer — dev and prod sign with different keys, so the embedded prod
    # key rejects every dev session. Accepts a multi-key PEM bundle (rotation).
    brain_pubkeys: tuple[str, ...]
    # Local dev escape hatch: skip token verification entirely.
    allow_unverified: bool
    # Control-plane API origin for the /api reverse proxy (deploys only).
    controlplane_api_url: str
    # Built frontend directory; served when present.
    frontend_dist: Path

    @classmethod
    def from_env(cls) -> Settings:
        default_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
        return cls(
            gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
            brain_pubkeys=_split_pem_bundle(os.environ.get("VOQALIZE_BRAIN_PUBKEYS", "")),
            allow_unverified=os.environ.get("VOQALIZE_ALLOW_UNVERIFIED", "") == "1",
            controlplane_api_url=os.environ.get("CONTROLPLANE_API_URL", "").rstrip("/"),
            frontend_dist=Path(os.environ.get("VOQALIZE_FRONTEND_DIST", str(default_dist))),
        )


class _WsChannel:
    """Adapts a Starlette/FastAPI ``WebSocket`` to the SDK ``Channel`` protocol
    (``async send(bytes)`` / ``async recv() -> bytes``). A closed socket surfaces
    as ``WebSocketDisconnect``, which the SDK session loop treats as
    end-of-connection."""

    def __init__(self, ws: WebSocket) -> None:
        self._ws = ws

    async def send(self, data: bytes) -> None:
        await self._ws.send_bytes(data)

    async def recv(self) -> bytes:
        return await self._ws.receive_bytes()


def create_app() -> FastAPI:
    """Build the umbrella app: validate the manifest↔registry wiring, then mount
    the brain sockets, the optional API proxy, and the static UIs."""
    settings = Settings.from_env()
    demos = check_wiring()
    demo_names = {d.name for d in demos}
    llm = GeminiProvider(api_key=settings.gemini_api_key)

    app = FastAPI(title="Voqalize demos")

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        return JSONResponse({"ok": True, "demos": sorted(demo_names)})

    # ─── Brain sockets ──────────────────────────────────────────────────
    @app.websocket("/{name}/s/{session_id}")
    async def brain_socket(websocket: WebSocket, name: str, session_id: str) -> None:
        await websocket.accept()
        try:
            build = brain_factory(name)
        except KeyError:
            logger.warning("demos: unknown brain {!r}", name)
            await websocket.close(code=_CLOSE_PERMANENT)
            return
        token = websocket.headers.get("Authorization")
        try:
            await run_session(
                _WsChannel(websocket),
                brain_builder=lambda: build(llm),
                session_id=session_id,
                token=token,
                # Verify Voqalize's RS256 brain token. Prefer configured pubkeys
                # (dev PyGato's signer); with none, fall back to the SDK's embedded
                # platform keys — the prod signer only, never fail open.
                public_keys=list(settings.brain_pubkeys) or None,
                allow_unverified=settings.allow_unverified,
            )
        except SessionRejected:
            logger.warning("demos: rejected session {} for {!r} (auth)", session_id, name)
            await websocket.close(code=_CLOSE_PERMANENT)
        except WebSocketDisconnect:
            pass  # peer closed mid-session — normal
        except Exception:
            logger.exception("demos: session {} for {!r} failed", session_id, name)
            with contextlib.suppress(Exception):
                await websocket.close(code=_CLOSE_INTERNAL)
        else:
            with contextlib.suppress(Exception):
                await websocket.close()  # session ended cleanly (End drained)

    # ─── API reverse proxy (deploys) ────────────────────────────────────
    if settings.controlplane_api_url:
        _mount_api_proxy(app, settings.controlplane_api_url)
        logger.info("demos: /api → {}", settings.controlplane_api_url)

    # ─── Static UIs ─────────────────────────────────────────────────────
    if settings.frontend_dist.is_dir():
        _mount_static(app, demo_names, settings.frontend_dist)
        logger.info("demos: serving UIs from {}", settings.frontend_dist)
    else:
        logger.info("demos: no built frontend at {} — brains + proxy only", settings.frontend_dist)

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
    """Serve the built MPA: ``/`` → index, ``/{name}`` → ``{name}.html``, everything
    else (``/assets/*``, favicons) from the static build."""

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(dist / "index.html")

    @app.get("/{name}")
    async def demo_page(name: str) -> Response:
        # A demo name → its built page. Otherwise a top-level static file (favicon,
        # vite.svg, …) if it exists. Else 404.
        page = dist / f"{name}.html"
        if name in demo_names and page.is_file():
            return FileResponse(page)
        top_level = dist / name
        if top_level.is_file():
            return FileResponse(top_level)
        return JSONResponse({"error": "not found"}, status_code=404)

    # Static assets (JS/CSS/img) + any other files (favicon, etc.). Mounted last so
    # the explicit routes above win; html=False so it doesn't shadow ``/``.
    app.mount("/", StaticFiles(directory=dist, html=False), name="static")


# Uvicorn entrypoint: ``uvicorn voqalize_demos.umbrella:app``.
app = create_app()
