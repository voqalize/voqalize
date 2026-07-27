"""Host your brain over an INBOUND WebSocket route — the primary production path.

Your web framework owns the listener and the upgrade; it hands the SDK the
connected socket. PyGato dials `{brain_url}/s/{session_id}`, one connection per
session, opened just-in-time and torn down when the call ends. No relay.

Run it:

    uvicorn inbound_app:app --host 0.0.0.0 --port 8080

Then set the agent's brain_url (via the `set_brain_url` MCP tool) to where this is
reachable — `wss://your-host` in production, or `ws://127.0.0.1:8080` for local
loopback. PyGato appends `/s/{session_id}`.

Auth: in production the SDK verifies PyGato's RS256 token against Voqalize's
embedded public keys with zero config. For LOCAL dev only, set
`VOQAL_ALLOW_UNVERIFIED=true` (local PyGato signs with a dev key the embedded prod
keys don't match). Never set it in production.
"""

from __future__ import annotations

import contextlib
import os

from fastapi import FastAPI, WebSocket
from starlette.websockets import WebSocketDisconnect

from voqalize.sdk import SessionRejected, run_session

from brain import MyBrain  # your Brain subclass

app = FastAPI()

# PyGato treats a 4000 close as permanent (don't retry); 1011 as retriable.
_CLOSE_PERMANENT = 4000
_CLOSE_RETRIABLE = 1011
_ALLOW_UNVERIFIED = os.environ.get("VOQAL_ALLOW_UNVERIFIED", "").lower() in ("1", "true", "yes")


class _WsChannel:
    """Adapts a FastAPI/Starlette WebSocket to the SDK's Channel protocol."""

    def __init__(self, ws: WebSocket) -> None:
        self._ws = ws

    async def send(self, data: bytes) -> None:
        await self._ws.send_bytes(data)

    async def recv(self) -> bytes:
        return await self._ws.receive_bytes()


@app.websocket("/s/{session_id}")
async def voice(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    token = websocket.headers.get("Authorization")
    try:
        await run_session(
            _WsChannel(websocket),
            brain=MyBrain,
            session_id=session_id,
            token=token,
            allow_unverified=_ALLOW_UNVERIFIED,
        )
    except SessionRejected:
        await websocket.close(code=_CLOSE_PERMANENT)  # bad token — don't retry
    except WebSocketDisconnect:
        pass  # peer closed mid-session — normal
    except Exception:
        with contextlib.suppress(Exception):
            await websocket.close(code=_CLOSE_RETRIABLE)  # transient — PyGato reconnects
    else:
        with contextlib.suppress(Exception):
            await websocket.close()  # clean end


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
