"""A one-word hello per demo language.

A greeting is a fixed line — the first thing the caller hears, before any model
has run — so it is written, not generated. This is the interjection half; a demo
composes the rest of its opener around it.
"""

from __future__ import annotations

_HELLO_BY_LANGUAGE = {
    "english": "Hi!",
    "hindi": "नमस्ते!",
    "telugu": "నమస్తే!",
    "tamil": "வணக்கம்!",
    "kannada": "ನಮಸ್ಕಾರ!",
    "marathi": "नमस्कार!",
    "bengali": "নমস্কার!",
}


def hello_for(language_name: str) -> str:
    """A short, language-appropriate opener; English default."""
    return _HELLO_BY_LANGUAGE.get((language_name or "").strip().lower(), "Hi!")


__all__ = ["hello_for"]
