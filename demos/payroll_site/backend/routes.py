"""Paynora's marketing site: the demo's own FastAPI brain route.

Voqalize dials ``/payroll_site?session_id=…`` once per session; the shared
``make_openai_brain_router`` owns the socket lifecycle and token verification,
so this file only names the demo and its per-session brain factory.
"""

from __future__ import annotations

from openai import AsyncOpenAI
from voqalize_demos.session import make_openai_brain_router

from .brain import PaynoraSiteBrain

# The URL segment Voqalize dials; must equal this folder's name.
NAME = "payroll_site"


def build(client: AsyncOpenAI) -> PaynoraSiteBrain:
    """A fresh brain for one session from the shared OpenAI client."""
    return PaynoraSiteBrain(client=client)


router = make_openai_brain_router(NAME, build)
