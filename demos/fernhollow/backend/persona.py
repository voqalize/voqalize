"""The character, read from ``persona.json`` at the demo's root — the one place
it lives. The page reads the same file (``frontend/src/persona.ts``), so
changing the character or adding a language is an edit there, not here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .catalog import DEMO

__all__ = ["PERSONA", "Persona", "agent_text"]


@dataclass(frozen=True)
class Persona:
    character: str
    name: str
    role: str
    voices: dict[str, str]
    languages: tuple[str, ...]
    default_language: str
    roles: dict[str, str]
    """The role label per job ("Returns adviser" on a return form)."""

    def language(self, asked: object) -> str:
        """The language for this call: the one the page asked for when it is
        offered, else the default."""
        code = str(asked or "").strip().lower()
        return code if code in self.languages else self.default_language

    def voice(self, language: str) -> str:
        return self.voices[language]


def _load() -> Persona:
    raw: dict[str, Any] = json.loads((DEMO / "persona.json").read_text())
    p = Persona(
        character=str(raw["character"]),
        name=str(raw["name"]),
        role=str(raw["role"]),
        voices={str(k): str(v) for k, v in raw["voices"].items()},
        languages=tuple(str(x) for x in raw["languages"]),
        default_language=str(raw["default_language"]),
        roles={str(k): str(v) for k, v in (raw.get("roles") or {}).items()},
    )
    missing = [lang for lang in p.languages if lang not in p.voices]
    if p.default_language not in p.languages or missing:
        raise ValueError(f"persona.json: every language needs a voice ({missing or 'default'})")
    return p


PERSONA = _load()


def agent_text(text: str) -> str:
    """Authored copy with ``{{agent}}`` standing for the character's name."""
    return text.replace("{{agent}}", PERSONA.name)
