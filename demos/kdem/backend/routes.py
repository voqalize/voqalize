"""KDEM's Aria — the demo's own FastAPI brain route.

Voqalize dials `/kdem?session_id=…` once per session; the shared
`make_brain_router` owns the socket lifecycle and token verification, so this file
only names the demo and its per-session brain factory.

There is no frontend folder: the page is karnatakadigital.in itself, and Aria
reaches it through the snippet in `demos/kdem/embed/`, pasted into the site.
"""

from __future__ import annotations

from google import genai
from voqalize_demos.session import make_brain_router

from .brain import KdemBrain

# The URL segment Voqalize dials; must equal this folder's name.
NAME = "kdem"


def build(client: genai.Client) -> KdemBrain:
    """Build a fresh brain for one session from the shared Gemini client."""
    return KdemBrain(client=client)


router = make_brain_router(NAME, build)
