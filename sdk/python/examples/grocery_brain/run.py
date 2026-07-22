"""Run the GroceryBrain against the LOCAL Cortex relay.

    backend/.venv/bin/python backend/agent-sdk/examples/grocery_brain/run.py

Connects one outbound multiplexed WebSocket to ws://localhost:8480/agent,
authenticating as the *platform agent* pool `PLATFORM:voqal-grocery` — the pool
the seeded `demo-grocery` agent routes to. Auth is a short-lived RS256 JWT signed
with .dev-keys/platform.pem, which Cortex trusts via CORTEX_PLATFORM_PUBKEYS.

Needs OPENAI_API_KEY in the repo-root .env (the OpenAI Agents SDK reads it from
the environment). Pair with the `/grocery` console demo at
http://localhost:5740/grocery — paste a Swiggy token, then Start Call.
"""

import os
import time
from pathlib import Path

import jwt
from brain import GroceryBrain
from dotenv import load_dotenv
from loguru import logger

from voqalize.sdk import serve

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PLATFORM_KEY = _REPO_ROOT / ".dev-keys" / "platform.pem"
_POOL_KEY = "PLATFORM:voqal-grocery"  # == compute_pool_key("demo-tenant", "voqal-grocery")
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
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY not set — add it to the repo-root .env")
    logger.info("grocery brain: connecting to {} as pool {}", _CORTEX_URL, _POOL_KEY)
    await serve(
        GroceryBrain,
        version="grocery-brain/0.1",
        cortex_url=_CORTEX_URL,
        authorization_provider=_mint_token,
    )


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
