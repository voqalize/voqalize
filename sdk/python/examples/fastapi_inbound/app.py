"""A runnable FastAPI inbound brain — the PRIMARY production path.

    cd sdk/python
    uv run uvicorn examples.fastapi_inbound.app:app --host 0.0.0.0 --port 8080

This is how a customer hosts a brain in production: your web framework owns the
WebSocket listener and the upgrade, and hands the SDK the connected socket. PyGato
dials your ``brain_url`` verbatim with ``?session_id=`` appended — one connection
per session, opened just-in-time, torn down when the call ends. No Cortex relay,
no SDK-owned server.

The three moving parts:

1. ``_WsChannel`` adapts Starlette/FastAPI's ``WebSocket`` to the SDK's ``Channel``
   protocol — just ``async send(bytes)`` / ``async recv() -> bytes``. (Modeled on
   the control plane's own ``routes/brains.py`` adapter, which hosts our demo
   brains over the exact same seam.)
2. The ``@app.websocket("/voice")`` route accepts the upgrade, pulls the
   ``session_id`` from the query string and the token from the ``Authorization``
   header, and calls :func:`run_session`.
3. Close-code discipline: a rejected token → close **4000** (permanent,
   non-retriable — PyGato gives up); an unexpected error → **1011** (retriable —
   PyGato reconnects); a clean end or peer close → normal close.

The brain here is the same ``EchoBrain`` from ``examples/echo`` (greet, then echo)
so the example stays dependency-free — swap it for your own ``Brain`` subclass.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import AsyncGenerator

from fastapi import FastAPI, WebSocket
from loguru import logger
from starlette.websockets import WebSocketDisconnect

from voqalize.sdk import (
    Brain,
    Chunk,
    Session,
    SessionRejected,
    Speech,
    SpeechEnd,
    SpeechStart,
    UserMessage,
    run_session,
)

# ─── The brain (same shape as examples/echo) ──────────────────────────────────


class EchoBrain(Brain):
    """Greets, then echoes each user turn."""

    async def greet(self, session: Session) -> str:
        return "Hi! I'm an echo bot. Say something and I'll repeat it back."

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[Speech, None]:
        yield SpeechStart()
        yield Chunk(f"You said: {msg.text}")
        yield SpeechEnd()


# ─── Transport: FastAPI WebSocket → SDK Channel ───────────────────────────────

# PyGato treats a 4000 close as permanent (non-retriable); 1011 as retriable.
_CLOSE_PERMANENT = 4000
_CLOSE_RETRIABLE = 1011

# Local dev signs brain tokens with a dev key, so skip verification locally.
# In production leave this unset/false: the SDK verifies PyGato's RS256 token
# against the embedded Voqalize public keys with zero config.
_ALLOW_UNVERIFIED = os.environ.get("VOQAL_ALLOW_UNVERIFIED", "").lower() in ("1", "true", "yes")

app = FastAPI()


class _WsChannel:
    """Adapts a Starlette/FastAPI ``WebSocket`` to the SDK ``Channel`` protocol.

    A closed socket surfaces as ``WebSocketDisconnect`` from ``recv``, which the
    SDK session loop treats as end-of-connection."""

    def __init__(self, ws: WebSocket) -> None:
        self._ws = ws

    async def send(self, data: bytes) -> None:
        await self._ws.send_bytes(data)

    async def recv(self) -> bytes:
        return await self._ws.receive_bytes()


@app.websocket("/voice")
async def voice(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    token = websocket.headers.get("Authorization")
    try:
        await run_session(
            _WsChannel(websocket),
            brain=EchoBrain,
            session_id=session_id,
            token=token,
            allow_unverified=_ALLOW_UNVERIFIED,
        )
    except SessionRejected:
        logger.warning("brain: rejected session {} (auth)", session_id)
        await websocket.close(code=_CLOSE_PERMANENT)
    except WebSocketDisconnect:
        pass  # peer closed mid-session — normal
    except Exception:
        logger.exception("brain: session {} failed", session_id)
        with contextlib.suppress(Exception):
            await websocket.close(code=_CLOSE_RETRIABLE)
    else:
        with contextlib.suppress(Exception):
            await websocket.close()  # session ended cleanly (End drained)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
