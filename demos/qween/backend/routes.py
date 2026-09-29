"""Qween jewellery consultant — the demo's own FastAPI brain route.

Voqalize dials `/qween?session_id=…` once per session (the inbound path); the
shared `make_brain_router` owns the socket lifecycle and token verification, so
this file only names the demo and its per-session brain factory.

Like `marketing`, this one has no frontend folder: its UI is Qween's own site,
www.qween.com, with the widget injected by the extension in `../extension/`.
"""

from __future__ import annotations

from google import genai
from voqalize_demos.session import make_brain_router

from .brain import QweenBrain

# The URL segment Voqalize dials; must equal this folder's name.
NAME = "qween"


def build(client: genai.Client) -> QweenBrain:
    """Build a fresh brain for one session from the shared Gemini client."""
    return QweenBrain(client=client)


router = make_brain_router(NAME, build)
