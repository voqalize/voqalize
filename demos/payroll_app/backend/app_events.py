"""The page's typed events that are not Stage state events, and the one site
command the brain sends back. Everything else the page reports rides Stage
(``frontend/src/stage/scene.json``: ``screen.viewed``, ``leave.decided``…)."""

from __future__ import annotations

from typing import Literal

from voqalize.sdk import Action, AppEvent


class LanguageRequested(AppEvent):
    """The admin pressed the other language on the EN / हिंदी toggle mid-call."""

    language: Literal["en", "hi"] = "en"
    by: str = "visitor"


class LanguageChanged(Action):
    """The call's language moved (toggle, voice or ``set_language``): the
    toggle follows."""

    language: Literal["en", "hi"]


__all__ = ["LanguageChanged", "LanguageRequested"]
