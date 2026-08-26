"""Travel Advisor — the demo's own FastAPI brain route.

Voqalize dials `/travel?session_id=…` once per session (the inbound path); the
shared `make_brain_router` owns the socket lifecycle and token verification, so
this file only names the demo and its per-session brain factory. This is the whole
backend surface a demo contributes — discovered and mounted by the umbrella.
"""

from __future__ import annotations

from google import genai
from voqalize_demos.session import make_brain_router

from .brain_gemini import TravelBrain

# The URL segment Voqalize dials; must equal this folder's name.
NAME = "travel"


def build(client: genai.Client) -> TravelBrain:
    """Build a fresh brain for one session from the shared Gemini client."""
    return TravelBrain(client=client)


router = make_brain_router(NAME, build)
