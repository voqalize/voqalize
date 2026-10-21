"""Santander Arena guide — the demo's own FastAPI brain route.

Voqalize dials `/santanderarena?session_id=…` once per session (the inbound
path); the shared `make_brain_router` owns the socket lifecycle and token
verification, so this file only names the demo and its per-session brain
factory.

Like `sendpotion`, this one has no frontend folder: its UI is Santander Arena's
own site, with the widget injected by the extension in `../extension/`.
"""

from __future__ import annotations

from google import genai
from voqalize_demos.session import make_brain_router

from .brain import SantanderBrain

# The URL segment Voqalize dials; must equal this folder's name.
NAME = "santanderarena"


def build(client: genai.Client) -> SantanderBrain:
    """Build a fresh brain for one session from the shared Gemini client."""
    return SantanderBrain(client=client)


router = make_brain_router(NAME, build)
