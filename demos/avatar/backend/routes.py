"""The avatar demo's own FastAPI brain route.

Voqalize dials `/avatar?session_id=…` once per session (the inbound path); the
shared `make_brain_router` owns the socket lifecycle and token verification, so
this file only names the demo and its per-session brain factory.
"""

from __future__ import annotations

from google import genai
from voqalize_demos.session import make_brain_router

from .brain import AvatarBrain

# The URL segment Voqalize dials; must equal this folder's name.
NAME = "avatar"


def build(client: genai.Client) -> AvatarBrain:
    """Build a fresh brain for one session from the shared Gemini client."""
    return AvatarBrain(client=client)


router = make_brain_router(NAME, build)
