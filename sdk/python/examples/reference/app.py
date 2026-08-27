"""Host the reference brain on a real WebSocket — the production hosting path.

    cd sdk/python
    VOQALIZE_BRAIN_PUBKEYS="$(cat pygato.pub.pem)" \
      uv run uvicorn examples.reference.app:app --host 0.0.0.0 --port 8290

Your web framework owns the route; the SDK owns the session. PyGato dials your
``brain_url`` verbatim with ``?session_id=`` appended — one connection per
session, opened just-in-time, torn down when the call ends. Mounted at
``/reference`` so one host can serve several brains under one origin, which is
what ``brain_url = wss://host/reference`` means.

Verification is on by default against the embedded Voqalize platform keys. A
self-hosted or local runtime signs with its own key, so pass that key's PEM in
``VOQALIZE_BRAIN_PUBKEYS`` — a mismatch here is the classic "every session closes
4000". ``VOQALIZE_ALLOW_UNVERIFIED=1`` skips verification entirely; local dev only.
"""

from __future__ import annotations

import contextlib
import os

from fastapi import FastAPI, WebSocket
from loguru import logger
from starlette.websockets import WebSocketDisconnect

from voqalize.sdk import SessionRejected, configure_logging, run_session

from .brain import ReferenceBrain

# PyGato treats 4000 as permanent (it gives up); 1011 as retriable (it reconnects).
_CLOSE_PERMANENT = 4000
_CLOSE_RETRIABLE = 1011

_PUBKEYS = os.environ.get("VOQALIZE_BRAIN_PUBKEYS") or None
_ALLOW_UNVERIFIED = os.environ.get("VOQALIZE_ALLOW_UNVERIFIED", "").lower() in ("1", "true", "yes")

configure_logging(level=os.environ.get("VOQALIZE_LOG_LEVEL", "INFO"))
app = FastAPI()


class _WsChannel:
    """A Starlette ``WebSocket`` as the SDK's ``Channel`` — send/recv bytes."""

    def __init__(self, ws: WebSocket) -> None:
        self._ws = ws

    async def send(self, data: bytes) -> None:
        await self._ws.send_bytes(data)

    async def recv(self) -> bytes:
        return await self._ws.receive_bytes()


@app.websocket("/reference")
async def voice(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    logger.info("reference: session {} connected", session_id)
    try:
        await run_session(
            _WsChannel(websocket),
            brain=ReferenceBrain,
            session_id=session_id,
            token=websocket.headers.get("Authorization"),
            public_keys=_PUBKEYS,
            allow_unverified=_ALLOW_UNVERIFIED,
        )
    except SessionRejected:
        logger.warning("reference: rejected session {} (auth)", session_id)
        await websocket.close(code=_CLOSE_PERMANENT)
    except WebSocketDisconnect:
        logger.info("reference: session {} peer closed", session_id)
    except Exception:
        logger.exception("reference: session {} failed", session_id)
        with contextlib.suppress(Exception):
            await websocket.close(code=_CLOSE_RETRIABLE)
    else:
        with contextlib.suppress(Exception):
            await websocket.close()


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
