"""The character, read from ``demos/payroll_site/persona.json``: the one place it lives.

The page reads the same file for the avatar, the name on the call button and the
EN / हिंदी toggle; this module gives the brain the display name, the voice per
language, the languages offered and the default. To change the character or add
a language, edit ``persona.json`` (and add the language's row to ``lines.py``,
which ``brain.py`` checks at import).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PERSONA_FILE = Path(__file__).resolve().parents[1] / "persona.json"


@dataclass(frozen=True)
class Persona:
    id: str
    name: str
    role: str
    character: str
    voices: dict[str, str]
    languages: tuple[str, ...]
    language_names: dict[str, str]
    default_language: str
    hindi_forms: str = "masculine"
    """The gender of the first-person forms the character uses in Hindi."""

    def tag(self, value: str | None) -> str:
        """A language this persona speaks, from a tag ("hi") or a name ("Hindi");
        anything else is the default (a stale page must still get a call)."""
        v = (value or "").strip().lower()
        for tag in self.languages:
            if v in (tag, self.language_names[tag].lower()):
                return tag
        return self.default_language


def load(path: Path = PERSONA_FILE) -> Persona:
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    langs: list[dict[str, str]] = raw["languages"]
    return Persona(
        id=raw["id"],
        name=raw["display_name"],
        role=raw["role"],
        character=raw["avatar_character"],
        voices=dict(raw["voices"]),
        languages=tuple(x["code"] for x in langs),
        language_names={x["code"]: x["label"] for x in langs},
        default_language=raw["default_language"],
        hindi_forms=str(raw.get("hindi_forms", "masculine")),
    )


PERSONA = load()
