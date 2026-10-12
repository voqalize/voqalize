"""voqalize_demos — the shared runtime every co-located demo backend builds on.

Each demo lives in its own folder (``demos/<name>/`` with a ``frontend/`` and a
``backend/`` beside each other). The demo *backends* are thin: a ``Brain`` plus a
one-line ``routes.py``. Everything shared — the Gemini client seam, the
per-session WebSocket handler, and the umbrella app that discovers and mounts
every demo's router — lives here.

The names a demo brain needs are re-exported at the package root so a co-located
``demos/<name>/backend/brain.py`` imports them from one obvious place::

    from voqalize_demos import DEFAULT_MODEL, GeminiBrain, needs_result_now

``GeminiBrain`` is the SDK's own — ``voqalize.sdk.gemini`` — not a demo-local
base. The demos dogfood the article a customer installs.

See ``demos/README.md`` for the routing contract and the add-a-demo checklist.
"""

import sys

from voqalize.sdk import voice_helpers
from voqalize.sdk.gemini import DEFAULT_MODEL, VOICE_THINKING, GeminiBrain, needs_result_now
from voqalize.sdk.voice_helpers import PHRASES, FallbackLine, landed, phrase, say_line
from voqalize_demos.configure import PATIENCE, configure_soon
from voqalize_demos.greeting import hello_for
from voqalize_demos.screen import ScreenState, screen_prose

# The floor under a silent turn moved into the SDK as ``voqalize.sdk.voice_helpers``.
# The names stay importable from here, and the old module path still resolves to
# the SDK's module, so a brain written against either keeps working.
sys.modules.setdefault(f"{__name__}.silent_turn", voice_helpers)

__all__ = [
    "DEFAULT_MODEL",
    "PATIENCE",
    "PHRASES",
    "VOICE_THINKING",
    "FallbackLine",
    "GeminiBrain",
    "ScreenState",
    "configure_soon",
    "hello_for",
    "landed",
    "needs_result_now",
    "phrase",
    "say_line",
    "screen_prose",
]
