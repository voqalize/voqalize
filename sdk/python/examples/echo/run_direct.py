"""Run EchoBrain as an inbound DIRECT server (no Cortex relay, no LLM keys).

    cd backend/agent-sdk && uv run python -m examples.echo.run_direct

Hosts ``EchoBrain`` on ``ws://127.0.0.1:8789/s/{session_id}``. PyGato opens one
connection per session just-in-time; there is no relay. Point a local demo
agent's ``brain_url`` at ``ws://127.0.0.1:8789`` (PyGato appends
``/s/{session_id}``), open the console, and start a call — you should hear the
greeting, then your own words echoed back.

Auth is disabled here (``allow_unverified=True``) for local dev ONLY: the local
PyGato signs its brain token with the dev key, while the SDK's embedded default
keys are prod, so a real signature check would reject every local session with a
4000 close. A deployed brain passes no such flag and gets zero-config prod
verification against the embedded Voqalize public keys.
"""

from __future__ import annotations

import asyncio
import os

from loguru import logger

from voqalize.sdk import serve_direct

from .brain import EchoBrain

_HOST = os.environ.get("ECHO_DIRECT_HOST", "127.0.0.1")
_PORT = int(os.environ.get("ECHO_DIRECT_PORT", "8789"))


async def main() -> None:
    logger.info("echo-direct: serving on ws://{}:{}/s/{{session_id}}", _HOST, _PORT)
    await serve_direct(EchoBrain, host=_HOST, port=_PORT, allow_unverified=True)


if __name__ == "__main__":
    asyncio.run(main())
