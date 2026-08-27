"""Meridian Servicing Desk — the demo's own FastAPI brain route.

Voqalize dials `/servicing?session_id=…` once per session (the inbound path); the
shared `make_brain_router` owns the socket lifecycle and token verification, so
this file only names the demo and its per-session brain factory. This is the whole
backend surface a demo contributes — discovered and mounted by the umbrella.
"""

from __future__ import annotations

from google import genai
from voqalize_demos.session import make_brain_router

from .brain import ServicingBrain

# The URL segment Voqalize dials; must equal this folder's name.
NAME = "servicing"


def build(client: genai.Client) -> ServicingBrain:
    """Build a fresh brain for one session from the shared Gemini client."""
    return ServicingBrain(client=client)


router = make_brain_router(NAME, build)
