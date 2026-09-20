"""Voqalize homepage agent — the demo's own FastAPI brain route.

Voqalize dials `/marketing?session_id=…` once per session (the inbound path); the
shared `make_brain_router` owns the socket lifecycle and token verification, so
this file only names the demo and its per-session brain factory. This is the whole
backend surface a demo contributes — discovered and mounted by the umbrella.

Unlike its neighbours this one has no frontend folder: its UI is the marketing
site itself, which lives in the platform repo and embeds the agent in the page.
"""

from __future__ import annotations

from google import genai
from voqalize_demos.session import make_brain_router

from .brain import MarketingBrain

# The URL segment Voqalize dials; must equal this folder's name.
NAME = "marketing"


def build(client: genai.Client) -> MarketingBrain:
    """Build a fresh brain for one session from the shared Gemini client."""
    return MarketingBrain(client=client)


router = make_brain_router(NAME, build)
