"""Host your brain over the CORTEX relay — the outbound fallback path.

Use this only when your brain **can't accept an inbound connection** (serverless /
FaaS, a laptop behind NAT, strict egress-only or air-gapped networks). The brain
dials *out* to Cortex over one multiplexed WebSocket; Cortex splices it to PyGato.
The primary path is `inbound_app.py` — prefer it whenever you can expose a route.

Run it:

    export VOQALIZE_AGENT_SECRET=ak_live_...     # from create_agent (shown once)
    export VOQALIZE_CORTEX_URL=wss://...         # the cortex_url from create_agent
    python run_cortex.py

Then set the agent's brain_url (via the `set_brain_url` MCP tool) to that same
`cortex_url` so PyGato routes sessions to this relay.
"""

from __future__ import annotations

import asyncio
import os

from voqalize.sdk import serve

from brain import MyBrain  # your Brain subclass


async def main() -> None:
    api_key = os.environ["VOQALIZE_AGENT_SECRET"]  # ak_… returned by create_agent
    cortex_url = os.environ["VOQALIZE_CORTEX_URL"]  # cortex_url returned by create_agent
    await serve(MyBrain, api_key=api_key, cortex_url=cortex_url, version="1")


if __name__ == "__main__":
    asyncio.run(main())
