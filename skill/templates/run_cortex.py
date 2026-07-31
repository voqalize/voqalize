"""Host your brain over the CORTEX relay — the outbound fallback path.

Use this only when your brain **can't accept an inbound connection** (serverless /
FaaS, a laptop behind NAT, strict egress-only or air-gapped networks). The brain
dials *out* to Cortex over one multiplexed WebSocket; Cortex splices it to PyGato.
The primary path is `inbound_app.py` — prefer it whenever you can expose a route.

Run it:

    export VOQALIZE_AGENT_SECRET=ak_live_...     # an ak_ agent credential (see below)
    export VOQALIZE_CORTEX_URL=wss://...         # the platform's Cortex URL (see below)
    python run_cortex.py

Then set the agent's brain_url (via `update_agent(tenant, agent_id, brain_url=...)`)
to that same Cortex URL so PyGato routes sessions to this relay.

Neither VOQALIZE_AGENT_SECRET nor VOQALIZE_CORTEX_URL is mintable through the
`voqalize` MCP tool surface today — `create_agent` returns a session `sk_` key,
not an `ak_` agent credential, and there's no MCP tool for the latter. Get both
from whoever provisions Cortex credentials for your tenant; this template
assumes you already have them.
"""

from __future__ import annotations

import asyncio
import os

from voqalize.sdk import serve

from brain import MyBrain  # your Brain subclass


async def main() -> None:
    api_key = os.environ["VOQALIZE_AGENT_SECRET"]  # ak_… agent credential (see module docstring)
    cortex_url = os.environ["VOQALIZE_CORTEX_URL"]  # the platform's Cortex URL (see module docstring)
    await serve(MyBrain, api_key=api_key, cortex_url=cortex_url, version="1")


if __name__ == "__main__":
    asyncio.run(main())
