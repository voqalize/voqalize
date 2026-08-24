"""voqalize_demos — the shared runtime every co-located demo backend builds on.

Each demo lives in its own folder (``demos/<name>/`` with a ``frontend/`` and a
``backend/`` beside each other). The demo *backends* are thin: a ``Brain`` plus a
one-line ``routes.py``. Everything shared — the Gemini client seam, the
per-session WebSocket handler, and the umbrella app that discovers and mounts
every demo's router — lives here.

The names a demo brain needs are re-exported at the package root so a co-located
``demos/<name>/backend/brain.py`` imports them from one obvious place::

    from voqalize_demos import DEFAULT_MODEL, GeminiBrain, GeminiProvider

``GeminiBrain`` is the SDK's own — ``voqalize.sdk.gemini`` — not a demo-local
base. The demos dogfood the article a customer installs.

See ``demos/README.md`` for the routing contract and the add-a-demo checklist.
"""

from voqalize.sdk.gemini import DEFAULT_MODEL, VOICE_THINKING, GeminiBrain
from voqalize_demos.greeting import hello_for
from voqalize_demos.llm import GeminiProvider

__all__ = ["DEFAULT_MODEL", "VOICE_THINKING", "GeminiBrain", "GeminiProvider", "hello_for"]
