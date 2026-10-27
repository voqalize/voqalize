"""Uno Salud Dental guide — the demo's own FastAPI brain route.

Voqalize dials `/unosalud?session_id=…` once per session (the inbound path);
the shared `make_openai_brain_router` owns the socket lifecycle and token
verification, so this file only names the demo and its per-session brain
factory.

Like `clini`, this one has no frontend folder: its UI is Uno Salud Dental's own
site (www.unosalud.cl), with the widget injected by the extension in
`../extension/`.
"""

from __future__ import annotations

from openai import AsyncOpenAI
from voqalize_demos.session import make_openai_brain_router

from .brain import UnoSaludBrain

# The URL segment Voqalize dials; must equal this folder's name.
NAME = "unosalud"


def build(client: AsyncOpenAI) -> UnoSaludBrain:
    """Build a fresh brain for one session from the shared OpenAI client."""
    return UnoSaludBrain(client=client)


router = make_openai_brain_router(NAME, build)
