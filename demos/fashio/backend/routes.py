"""Fashio — the demo's own FastAPI brain route.

Voqalize dials ``/fashio?session_id=…`` once per session; the shared
``make_openai_brain_router`` owns the socket lifecycle and token verification,
so this file only names the demo and its per-session brain factory.
"""

from __future__ import annotations

from openai import AsyncOpenAI
from voqalize_demos.session import make_openai_brain_router

from .brain import FashioBrain

# The URL segment Voqalize dials; must equal this folder's name.
NAME = "fashio"


def build(client: AsyncOpenAI) -> FashioBrain:
    """Build a fresh brain for one session from the shared OpenAI client."""
    return FashioBrain(client=client)


router = make_openai_brain_router(NAME, build)
