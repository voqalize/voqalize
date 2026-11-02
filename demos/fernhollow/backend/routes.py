"""Fernhollow — the demo's own FastAPI brain route.

Voqalize dials ``/fernhollow?session_id=…`` once per session (the inbound path);
the shared ``make_brain_router`` owns the socket lifecycle and token
verification, so this file only names the demo and its per-session brain
factory.
"""

from __future__ import annotations

from google import genai
from voqalize_demos.session import make_brain_router

from .brain import FernhollowBrain

# The URL segment Voqalize dials; must equal this folder's name.
NAME = "fernhollow"


def build(client: genai.Client) -> FernhollowBrain:
    """Build a fresh brain for one session from the shared Gemini client."""
    return FernhollowBrain(client=client)


router = make_brain_router(NAME, build)
