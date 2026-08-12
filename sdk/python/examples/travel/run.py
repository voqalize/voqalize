"""Run the cortex TravelBrain against a Cortex relay.

    GEMINI_API_KEY=...  python -m examples.travel.run \
        --api-key sk_...  --cortex-url wss://cortex.voqalize.com/agent

One ``CortexAgent`` process; a fresh ``TravelBrain`` per session.
"""

from __future__ import annotations

import argparse
import asyncio

from voqalize.sdk import serve

from .brain import TravelBrain


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-key", required=True, help="the agent's secret (sk_…) from agents.create")
    ap.add_argument("--version", default="1.0.0")
    ap.add_argument("--cortex-url", required=True, help="wss://…/agent")
    args = ap.parse_args()
    asyncio.run(
        serve(TravelBrain, api_key=args.api_key, version=args.version, cortex_url=args.cortex_url)
    )


if __name__ == "__main__":
    main()
