"""Run Emily's brain on your own machine against a deployed Voqalize, over Cortex.

The deployed demos are served from `brain.<env>.voqalize.com/fernhollow`, which
is only as new as the last merge to `main`. To try a change first, put a dev
agent on the Cortex relay (the MCP tool `create_agent_credentials`, which hands
back an `sk_` and the relay's URL) and run this: dev's voice runtime then
reaches the brain in this process, and the store's calls are answered by the
code in your working tree.

    cd demos
    VOQALIZE_AGENT_SECRET=sk_... VOQALIZE_CORTEX_URL=wss://... \\
        uv run python -m fernhollow.backend.dev_cortex

`GEMINI_API_KEY` must be set, as for the demos server. Use an agent of its own
for this rather than the one dev.voqalize.com/demos/fernhollow uses: the tool
moves the agent onto the relay, and the deployed page would follow it here.
"""

from __future__ import annotations

import asyncio
import os

from google import genai

from voqalize.sdk import serve

from .brain import FernhollowBrain


def main() -> None:
    secret = os.environ.get("VOQALIZE_AGENT_SECRET", "")
    url = os.environ.get("VOQALIZE_CORTEX_URL", "")
    key = os.environ.get("GEMINI_API_KEY", "")
    if not (secret and url and key):
        raise SystemExit("set VOQALIZE_AGENT_SECRET, VOQALIZE_CORTEX_URL and GEMINI_API_KEY")
    client = genai.Client(api_key=key)
    asyncio.run(
        serve(lambda: FernhollowBrain(client=client), api_key=secret, cortex_url=url, version="dev")
    )


if __name__ == "__main__":
    main()
