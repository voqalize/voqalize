"""Universidad Alberto Hurtado guide — the demo's own FastAPI brain route.

Voqalize dials `/uahurtado?session_id=…` once per session (the inbound path);
the shared `make_openai_brain_router` owns the socket lifecycle and token
verification, so this file only names the demo and its per-session brain
factory.

Like its siblings for the same customer, this one has no frontend folder: its
UI is the university's own sites, with the widget injected by the extension in
`../extension/`.
"""

from __future__ import annotations

from openai import AsyncOpenAI
from voqalize_demos.session import make_openai_brain_router

from .brain import UahurtadoBrain

# The URL segment Voqalize dials; must equal this folder's name.
NAME = "uahurtado"


def build(client: AsyncOpenAI) -> UahurtadoBrain:
    """Build a fresh brain for one session from the shared OpenAI client."""
    return UahurtadoBrain(client=client)


router = make_openai_brain_router(NAME, build)
