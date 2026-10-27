"""SendPotion guide — the demo's own FastAPI brain route.

Voqalize dials `/sendpotion?session_id=…` once per session (the inbound path);
the shared `make_openai_brain_router` owns the socket lifecycle and token
verification, so this file only names the demo and its per-session brain
factory.

Like `saatvik` and `qween`, this one has no frontend folder: its UI is
SendPotion's own site and blog, with the widget injected by the extension in
`../extension/`.
"""

from __future__ import annotations

from openai import AsyncOpenAI
from voqalize_demos.session import make_openai_brain_router

from .brain import SendPotionBrain

# The URL segment Voqalize dials; must equal this folder's name.
NAME = "sendpotion"


def build(client: AsyncOpenAI) -> SendPotionBrain:
    """Build a fresh brain for one session from the shared OpenAI client."""
    return SendPotionBrain(client=client)


router = make_openai_brain_router(NAME, build)
