"""Enveedo guide — the demo's own FastAPI brain route.

Voqalize dials `/enveedo?session_id=…` once per session (the inbound
path); the shared `make_openai_brain_router` owns the socket lifecycle and token
verification, so this file only names the demo and its per-session brain
factory.

Like `colegioeverest`, this one has no frontend folder: its UI is Enveedo's own
site, enveedo.com, with the widget injected by the extension in
`../extension/`.
"""

from __future__ import annotations

from openai import AsyncOpenAI
from voqalize_demos.session import make_openai_brain_router

from .brain import EnveedoBrain

# The URL segment Voqalize dials; must equal this folder's name.
NAME = "enveedo"


def build(client: AsyncOpenAI) -> EnveedoBrain:
    """Build a fresh brain for one session from the shared OpenAI client."""
    return EnveedoBrain(client=client)


router = make_openai_brain_router(NAME, build)
