"""Voqalize + Google ADK — host a native ADK agent as a voice Brain.

The SDK drives ADK's run loop and owns the voice concerns (speech brackets,
heard-truth history, barge-in, the wire); the client writes a normal
``LlmAgent`` and native tools. See :func:`adk_brain`.

    from voqalize.google_adk import AdkBrain, adk_brain, voice
    from voqalize.sdk import run_session

Subclass :class:`AdkBrain` to react to Voqalize's other triggers (``on_user_idle`` /
``on_client_message``) or resume; :func:`adk_brain` is the no-override builder over
the same constructor.

Requires the ``adk`` extra (``pip install voqalize-agent-sdk[adk]``). Importing
this module (not ``voqalize.sdk``) is what pulls in ``google-adk``.
"""

from __future__ import annotations

from ._context import NoActiveVoice, Voice, voice
from .brain import AdkBrain, adk_brain

__all__ = ["AdkBrain", "NoActiveVoice", "Voice", "adk_brain", "voice"]
