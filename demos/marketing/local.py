"""Run Tanvi on this machine, connected outbound to Voqalize through Cortex.

    cd demos/marketing/frontend && pnpm dev:live    # the site and this, both reloading
    cd demos && uv run python marketing/local.py    # this alone

For working on the site with a brain you can edit: a dev agent in cortex mode dials this
process instead of the deployed brain. Reads `frontend/.env.local` and the shell:
  GEMINI_API_KEY          the model
  VOQALIZE_AGENT_SECRET   that agent's sk_ key (cortex mode)
  VOQALIZE_CORTEX_URL     optional; defaults to the dev relay
"""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
from pathlib import Path

from google import genai
from loguru import logger
from voqalize_demos.discovery import discover

from voqalize.sdk import serve

ENV_FILE = Path(__file__).resolve().parent / "frontend" / ".env.local"
DEV_CORTEX = "wss://cortex.dev.voqalize.com/agent"


def _load_env_file() -> None:
    if not ENV_FILE.is_file():
        return
    for line in ENV_FILE.read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and not key.lstrip().startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        logger.error("{} is not set. Add it to {} (see .env.example).", name, ENV_FILE)
        sys.exit(1)
    return value


def main() -> None:
    _load_env_file()
    gemini_key = _require("GEMINI_API_KEY")
    secret = _require("VOQALIZE_AGENT_SECRET")
    cortex_url = os.environ.get("VOQALIZE_CORTEX_URL", "").strip() or DEV_CORTEX
    discover()  # loads demos/*/backend as voqalize_demos._loaded.<name>
    tanvi_brain = importlib.import_module("voqalize_demos._loaded.marketing.brain").TanviBrain

    client = genai.Client(api_key=gemini_key)
    logger.info("tanvi: connecting to {}", cortex_url)
    asyncio.run(
        serve(
            lambda: tanvi_brain(client=client), version="dev", cortex_url=cortex_url, api_key=secret
        )
    )


if __name__ == "__main__":
    main()
