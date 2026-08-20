"""Host your brain over the CORTEX relay — your brain dials OUT, no tunnel needed.

Use this whenever the brain can't accept an inbound connection: **a laptop during
development**, serverless/FaaS, or a strict egress-only / air-gapped network. The
brain opens one outbound WebSocket to Cortex; many sessions multiplex over it, and
Cortex splices each one to the voice runtime. For production, where you already run
a web backend, prefer `inbound_app.py` — one less hop.

This is fully self-service. Get the credentials from the MCP server:

    create_agent_credentials(tenant, agent_id, label="")
      -> agent_secret  (sk_…, shown ONCE)    -> VOQAL_AGENT_SECRET
      -> cortex_url    (already ends /agent)  -> VOQAL_CORTEX_URL, pass verbatim
      -> brain_url     (the Cortex origin)    -> update_agent(..., brain_url=...)

Then wire the agent to Cortex — this is NOT automatic:

    update_agent(tenant, agent_id, brain_url="<the brain_url it returned>")

Run it:

    export VOQAL_AGENT_SECRET=sk_...
    export VOQAL_CORTEX_URL=wss://cortex.dev.voqalize.com/agent
    python run_cortex.py

Finally open the agent's `test_url` (from `create_agent` / `get_agent`) and talk.

The secret is shown once and never recoverable — only revocable (`revoke_api_key`)
and re-mintable (call `create_agent_credentials` again). Minting revokes nothing, so
rotation is: mint, redeploy with the new key, then revoke the old one.
"""

from __future__ import annotations

import asyncio
import os

from voqalize.sdk import serve

from brain import MyBrain  # your Brain subclass


async def main() -> None:
    # `serve` blocks until the relay closes permanently. The SDK reads no env vars of
    # its own — both below are conventions this script passes through as kwargs.
    await serve(
        MyBrain,
        api_key=os.environ["VOQAL_AGENT_SECRET"],  # sk_… for this agent
        cortex_url=os.environ["VOQAL_CORTEX_URL"],  # verbatim; it already ends in /agent
        version="1.0.0",
    )


if __name__ == "__main__":
    asyncio.run(main())
