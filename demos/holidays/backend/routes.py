"""Wanderloom Holidays — the demo's own FastAPI brain route.

Voqalize dials ``/holidays?session_id=…`` once per session; the shared
``make_openai_brain_router`` owns the socket and token checks, so this file only
names the demo and builds its per-session brain.
"""

from __future__ import annotations

from openai import AsyncOpenAI
from voqalize_demos.session import make_openai_brain_router

from .brain import HolidaysBrain

# The URL segment Voqalize dials; must equal this folder's name.
NAME = "holidays"


def build(client: AsyncOpenAI) -> HolidaysBrain:
    """A fresh brain for one session, on the shared OpenAI client."""
    return HolidaysBrain(client=client)


router = make_openai_brain_router(NAME, build)
