"""Mobile Expert — the demo's own FastAPI brain route.

Voqalize dials `/shopping/s/{session_id}` once per session (the inbound path); the
shared `make_brain_router` owns the socket lifecycle and token verification, so
this file only names the demo and its per-session brain factory. This is the whole
backend surface a demo contributes — discovered and mounted by the umbrella.
"""

from __future__ import annotations

from voqalize_demos import GeminiProvider
from voqalize_demos.session import make_brain_router

from .brain import ShoppingBrain

# The URL segment Voqalize dials; must equal this folder's name.
NAME = "shopping"


def build(llm: GeminiProvider) -> ShoppingBrain:
    """Build a fresh brain for one session from the shared LLM provider."""
    return ShoppingBrain(llm=llm)


router = make_brain_router(NAME, build)
