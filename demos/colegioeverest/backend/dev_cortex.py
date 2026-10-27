"""Run Javier's brain on your own machine against a deployed Voqalize, over Cortex.

The deployed demos are served from `brain.<env>.voqalize.com/colegioeverest`, which
is only as new as the last merge to `main`. To try a change first, put a dev
agent on the Cortex relay (the MCP tool `create_agent_credentials`, which hands
back an `sk_` and the relay's URL) and run this: dev's voice runtime then
reaches the brain in this process, and the extension's calls are answered by
the code in your working tree.

    cd demos
    VOQALIZE_AGENT_SECRET=sk_... VOQALIZE_CORTEX_URL=wss://... \\
        uv run python -m colegioeverest.backend.dev_cortex

`OPENAI_API_KEY` must be set, as for the demos server. Point the agent back at
`wss://brain.dev.voqalize.com/colegioeverest` (`update_agent` with `brain_url`)
once the change is merged and deployed.
"""

from __future__ import annotations

import asyncio
import os

from openai import AsyncOpenAI

from voqalize.sdk import serve

from .brain import ColegioEverestBrain


def main() -> None:
    secret = os.environ.get("VOQALIZE_AGENT_SECRET", "")
    url = os.environ.get("VOQALIZE_CORTEX_URL", "")
    key = os.environ.get("OPENAI_API_KEY", "")
    if not (secret and url and key):
        raise SystemExit("set VOQALIZE_AGENT_SECRET, VOQALIZE_CORTEX_URL and OPENAI_API_KEY")
    client = AsyncOpenAI(api_key=key)
    asyncio.run(
        serve(
            lambda: ColegioEverestBrain(client=client),
            api_key=secret,
            cortex_url=url,
            version="dev",
        )
    )


if __name__ == "__main__":
    main()
