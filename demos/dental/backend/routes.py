"""Dantika Dental's brain route.

Voqalize dials ``/dental?session_id=…`` once per session; the shared
``make_openai_brain_router`` owns the socket and token checks, so this file only
names the demo and builds one brain per session.
"""

from __future__ import annotations

from openai import AsyncOpenAI
from voqalize_demos.session import make_openai_brain_router

from .brain import DentalBrain

# The URL segment Voqalize dials; must equal this folder's name.
NAME = "dental"


def build(client: AsyncOpenAI) -> DentalBrain:
    """A fresh brain for one session, on the shared OpenAI client."""
    return DentalBrain(client=client)


router = make_openai_brain_router(NAME, build)
