"""Chhatri Insurance — the demo's brain route.

Voqalize dials ``/insurance?session_id=…`` once per session; the shared
``make_openai_brain_router`` owns the socket and token verification, so this
file only names the demo and its per-session brain factory.
"""

from __future__ import annotations

from openai import AsyncOpenAI
from voqalize_demos.session import make_openai_brain_router

from .brain import InsuranceBrain

# The URL segment Voqalize dials; must equal this folder's name.
NAME = "insurance"


def build(client: AsyncOpenAI) -> InsuranceBrain:
    """A fresh brain for one session, on the shared OpenAI client."""
    return InsuranceBrain(client=client)


router = make_openai_brain_router(NAME, build)
