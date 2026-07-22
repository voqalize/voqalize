"""Run the cortex TravelBrain against the LOCAL Cortex relay (pm2 dev stack).

    cd backend/agent-sdk && uv run python examples/travel/run_local.py

Connects one outbound multiplexed WebSocket to ws://localhost:8480/agent,
authenticating as a *platform agent* for the pool the locally-seeded
``demo-travel`` agent routes to once flipped to ``deployment.mode = cortex``
(``t:demo-tenant:voqal-travel`` — voqal-travel is a tenant key, not a platform
key, so the pool is tenant-scoped; Cortex still accepts a platform-signed JWT
for any agent_id and routes by it). Auth is a short-lived RS256 JWT signed with
.dev-keys/platform.pem, which Cortex trusts via CORTEX_PLATFORM_PUBKEYS.

Pair with the ``/travel`` console demo at http://localhost:5740/travel after
flipping demo-travel to cortex (see scripts/flip_travel_cortex.py).
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import jwt
from brain import TravelBrain  # same-dir import when run as a script
from dotenv import load_dotenv
from loguru import logger

from voqalize.sdk import CortexAgent, brain_factory

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PLATFORM_KEY = _REPO_ROOT / ".dev-keys" / "platform.pem"
_POOL_KEY = "t:demo-tenant:voqal-travel"  # compute_pool_key("demo-tenant", "voqal-travel")
_CORTEX_URL = os.environ.get("CORTEX_AGENT_URL", "ws://localhost:8480/agent")


def _mint_token() -> str:
    """Fresh platform-agent JWT per connect (iss=platform, aud=cortex)."""
    priv = _PLATFORM_KEY.read_text()
    now = int(time.time())
    claims = {
        "iss": "platform",
        "aud": "cortex",
        "kind": "platform_agent",
        "agent_id": _POOL_KEY,
        "iat": now,
        "exp": now + 3600,
    }
    return "Bearer " + jwt.encode(claims, priv, algorithm="RS256")


async def main() -> None:
    load_dotenv(_REPO_ROOT / ".env")
    if not os.environ.get("GEMINI_API_KEY"):
        raise SystemExit("GEMINI_API_KEY not set (repo-root .env)")
    logger.info("travel-cortex: connecting to {} as pool {}", _CORTEX_URL, _POOL_KEY)
    agent = CortexAgent(
        version="travel-cortex/0.1",
        cortex_url=_CORTEX_URL,
        factory=brain_factory(TravelBrain),  # Brain → per-session adapter
        authorization_provider=_mint_token,
    )
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
