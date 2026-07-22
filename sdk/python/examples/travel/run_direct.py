"""Run the Python TravelBrain as an inbound DIRECT server (no Cortex relay).

    cd sdk/python && uv run python examples/travel/run_direct.py

Hosts ``TravelBrain`` on ``ws://localhost:8788/s/{session_id}``. Point an agent's
``brain_url`` at this address (via the Voqalize MCP ``set_brain_url`` tool or the
console) and the voice runtime dials in — one connection per session, just-in-time,
with no relay in the path.

Auth is disabled here (``allow_unverified=True``) for local dev only: the local
PyGato signs its brain token with the dev key, while the SDK's embedded default
keys are prod. A real customer passes no such flag and gets zero-config prod
verification. This is the Python peer of the Go ``cmd/travel-direct`` (which uses
``AllowUnverified: true`` for the same reason).
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

from voqalize.sdk import serve_direct

from .brain import TravelBrain

_REPO_ROOT = Path(__file__).resolve().parents[4]
_HOST = os.environ.get("TRAVEL_DIRECT_HOST", "127.0.0.1")
_PORT = int(os.environ.get("TRAVEL_DIRECT_PORT", "8788"))


async def main() -> None:
    load_dotenv(_REPO_ROOT / ".env")
    if not os.environ.get("GEMINI_API_KEY"):
        raise SystemExit("GEMINI_API_KEY not set (repo-root .env)")
    logger.info("travel-direct (python): serving on ws://{}:{}/s/{{session_id}}", _HOST, _PORT)
    await serve_direct(TravelBrain, host=_HOST, port=_PORT, allow_unverified=True)


if __name__ == "__main__":
    asyncio.run(main())
