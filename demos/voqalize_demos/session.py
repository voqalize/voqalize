"""The shared per-session plumbing every demo brain route reuses.

A demo backend never writes WebSocket boilerplate. Its ``routes.py`` is one line::

    router = make_brain_router("travel", lambda llm: TravelBrain(llm=llm))

which returns a FastAPI ``APIRouter`` exposing ``/{name}/s/{session_id}`` — the
**inbound** brain socket Voqalize dials once per session. This module owns the
socket lifecycle: accept, adapt it to the SDK ``Channel``, verify Voqalize's RS256
brain token inside ``run_session``, and map the outcome to the right close code.

The process-wide dependencies the handler needs — the injected ``GeminiProvider``
and the verification settings — are set once at startup by the umbrella via
:func:`init_runtime`, so a per-demo router carries no configuration of its own.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, WebSocket
from loguru import logger
from starlette.websockets import WebSocketDisconnect

from voqalize.sdk import Brain, SessionRejected, run_session
from voqalize_demos.llm import GeminiProvider

# Voqalize's Wire treats a 4000 close as permanent (non-retriable) — used for a
# rejected token; 1011 is retriable (a transient fault).
_CLOSE_PERMANENT = 4000
_CLOSE_INTERNAL = 1011

_PEM_END = "-----END PUBLIC KEY-----"

# A demo's brain builder: given the shared LLM, build a fresh brain for one session.
BrainFactory = Callable[[GeminiProvider], Brain]


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
    # Built demo UIs directory (the assembled MPA); served when present.
    frontend_dist: Path

    @classmethod
    def from_env(cls) -> Settings:
        # demos/voqalize_demos/session.py → demos/dist
        default_dist = Path(__file__).resolve().parents[1] / "dist"
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


@dataclass(frozen=True)
class _Runtime:
    settings: Settings
    llm: GeminiProvider


_runtime_singleton: _Runtime | None = None


def init_runtime(settings: Settings, llm: GeminiProvider) -> None:
    """Set the process-wide dependencies every brain socket reads. Called once by
    the umbrella at startup, before any router serves a session."""
    global _runtime_singleton
    _runtime_singleton = _Runtime(settings=settings, llm=llm)


def _runtime() -> _Runtime:
    if _runtime_singleton is None:  # pragma: no cover — a wiring bug, not a runtime path
        raise RuntimeError("session runtime not initialized — call init_runtime() first")
    return _runtime_singleton


def make_brain_router(name: str, factory: BrainFactory) -> APIRouter:
    """Build the ``/{name}/s/{session_id}`` inbound brain route for one demo.

    ``factory(llm)`` builds a fresh brain per session from the shared provider.
    ``name`` is the URL segment Voqalize dials — kept at the root (``/travel/s/…``)
    independent of where the UI is served (``/demos/travel``)."""
    router = APIRouter()

    @router.websocket("/" + name + "/s/{session_id}")
    async def brain_socket(websocket: WebSocket, session_id: str) -> None:
        rt = _runtime()
        await websocket.accept()
        token = websocket.headers.get("Authorization")
        try:
            await run_session(
                _WsChannel(websocket),
                brain_builder=lambda: factory(rt.llm),
                session_id=session_id,
                token=token,
                # Verify Voqalize's RS256 brain token. Prefer configured pubkeys
                # (dev PyGato's signer); with none, fall back to the SDK's embedded
                # platform keys — the prod signer only, never fail open.
                public_keys=list(rt.settings.brain_pubkeys) or None,
                allow_unverified=rt.settings.allow_unverified,
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

    return router
