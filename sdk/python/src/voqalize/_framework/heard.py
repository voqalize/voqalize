"""Framework-neutral *readers* of the SDK-owned **heard-truth** ``session.conversation``.

The ADK adapter keeps the framework's own session as source of truth and corrects
its assembled contents in place; what survives here is the small, shared vocabulary
for *reading* heard text off a genai ``Content`` / a ``session.conversation``:
:func:`text_of`, :func:`spoken_text_of` (thought parts excluded), :func:`last_user_text`
(a fake model's script key), and :func:`heard_turns` (the ``(role, text)`` reading
with leading assistant turns dropped — used by the fakes and by any code that only
needs spoken history, not tool exchanges).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from voqalize.sdk.brain import Conversation


def text_of(content: Any) -> str:
    """Concatenated text of a genai ``Content``'s parts (ignores non-text parts)."""
    if content is None or not getattr(content, "parts", None):
        return ""
    return "".join(p.text for p in content.parts if getattr(p, "text", None))


def spoken_text_of(content: Any) -> str:
    """Concatenated text of a genai ``Content``'s parts, **excluding thinking parts**.

    A part with ``thought=True`` (emitted when ADK's model runs with thinking on) is
    the model's private reasoning — it must never be spoken to the user. This is the
    reader the driven run uses for speech; :func:`text_of` keeps the unfiltered
    reading for callers that want every part."""
    if content is None or not getattr(content, "parts", None):
        return ""
    return "".join(
        p.text
        for p in content.parts
        if getattr(p, "text", None) and not getattr(p, "thought", None)
    )


def last_user_text(contents: list[Any]) -> str:
    """The last user-authored text in a contents list — a fake model's script key.

    Skips function-response turns (role ``user`` but text-free), so a tool
    round-trip's second model call keys on the same utterance as the first."""
    for content in reversed(contents):
        if getattr(content, "role", None) == "user":
            text = "".join(p.text for p in (content.parts or []) if getattr(p, "text", None))
            if text:
                return text
    return ""


def heard_turns(conversation: Conversation) -> list[tuple[str, str]]:
    """The heard-truth history as ``(role, text)`` pairs — ``role`` is ``"user"`` or
    ``"assistant"``.

    The framework-neutral reading of ``session.conversation`` every integration
    needs: the committed heard text, with **leading assistant turns dropped** so the
    sequence opens on a user turn (real models — Gemini, OpenAI — require the first
    turn to be the user's; a fake model is indifferent). Each adapter maps these
    pairs into its own item shape."""
    turns: list[tuple[str, str]] = []
    seen_user = False
    for m in conversation.messages:
        if m.role == "user":
            seen_user = True
            turns.append(("user", m.content))
        elif seen_user:  # assistant
            turns.append(("assistant", m.content))
    return turns
