"""The character, read from ``demos/fashio/persona.json`` — the one place it lives.

The page reads the same file for the avatar, the name on the call button and the
language toggle; this module gives the brain the display name, the role label
per job, the voice per language, the languages offered and the default. Change the character there,
not here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from voqalize.sdk.wire import Language, Voice

PERSONA_FILE = Path(__file__).resolve().parents[1] / "persona.json"


@dataclass(frozen=True)
class Persona:
    character: str
    name: str
    role: str
    roles: dict[str, str]
    voices: dict[str, str]
    languages: tuple[str, ...]
    language_names: dict[str, str]
    default_language: str
    #: "female" or "male": how the character speaks of itself (Hindi verbs agree with it).
    gender: str = "female"

    def voice(self, tag: str) -> Voice | str:
        """The voice for ``tag``, as the catalog member when there is one."""
        voice_id = self.voices[tag]
        try:
            return Voice(voice_id)
        except ValueError:
            return voice_id

    def language(self, tag: str) -> Language | str:
        try:
            return Language(tag)
        except ValueError:
            return tag

    def tag(self, value: str | None) -> str:
        """A language tag the persona speaks, from a tag or a name; else the default."""
        v = (value or "").strip().lower()
        for tag in self.languages:
            if v in (tag, self.language_names[tag].lower()):
                return tag
        return self.default_language


def load(path: Path = PERSONA_FILE) -> Persona:
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    langs = raw["languages"]
    return Persona(
        character=raw["character"],
        name=raw["name"],
        role=raw["role"],
        roles=dict(raw.get("roles") or {}),
        voices=dict(raw["voices"]),
        languages=tuple(x["tag"] for x in langs),
        language_names={x["tag"]: x["name"] for x in langs},
        default_language=raw["default_language"],
        gender=str(raw.get("gender") or "female"),
    )


PERSONA = load()
