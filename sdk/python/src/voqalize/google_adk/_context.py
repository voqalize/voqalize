"""The ``voice()`` accessor for ADK tools — re-exported from the shared core.

The mechanism (a :class:`~contextvars.ContextVar` the adapter sets around
``Runner.run_async``, read by :func:`voice` inside a native tool) is framework-
agnostic and lives in :mod:`voqalize._framework.context`; the same surface backs
the raw-genai adapter. This module keeps the historical import path stable.
"""

from __future__ import annotations

from voqalize._framework.context import (
    _CURRENT,
    NoActiveVoice,
    Voice,
    _Turn,
    voice,
)

__all__ = ["_CURRENT", "NoActiveVoice", "Voice", "_Turn", "voice"]
