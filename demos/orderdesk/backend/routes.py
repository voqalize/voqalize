"""MedSetu OrderDesk — the demo's own FastAPI brain route.

Voqalize dials `/orderdesk/s/{session_id}` once per session (the inbound path); the
shared `make_brain_router` owns the socket lifecycle and token verification, so this
file only names the demo and its per-session brain factory. This is the whole backend
surface a demo contributes — discovered and mounted by the umbrella.
"""

from __future__ import annotations

from voqalize_demos import GeminiProvider
from voqalize_demos.session import make_brain_router

from .brain import OrderDeskBrain

# The URL segment Voqalize dials; must equal this folder's name.
NAME = "orderdesk"


def build(_llm: GeminiProvider) -> OrderDeskBrain:
    """Build a fresh brain — and a fresh, empty order screen — for one session.

    OrderDesk runs on the **Google ADK** adapter, which builds its own Gemini client
    from the environment (``GOOGLE_API_KEY`` / ``GEMINI_API_KEY`` — the same key the
    umbrella reads into ``Settings``), so the shared ``GeminiProvider`` the discovery
    contract hands every demo is unused here."""
    return OrderDeskBrain()


router = make_brain_router(NAME, build)
