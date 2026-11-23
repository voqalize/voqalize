"""The character, read from ``../persona.json`` — the one place it lives.

The brain takes the display name for its prompt and greetings, the voice for
each language, the languages offered and the default from here; the page reads
the same file (``frontend/src/persona.ts``). To change the character, edit
``persona.json`` (an avatar character, and a voice that speaks every language
listed). To add a language, add it there and give it a row in
:data:`.prompt.GREETINGS`, :data:`.prompt.TOGGLE_CONFIRM` and :data:`.brain.HELD`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / "persona.json"


@dataclass(frozen=True)
class Persona:
    id: str
    name: str
    role: str
    avatar: str
    voices: dict[str, str]
    languages: tuple[str, ...]
    labels: dict[str, str]
    default_language: str
    hindi_forms: str = "feminine"
    """The gender of the first-person forms the character uses in Hindi."""

    def voice(self, language: str) -> str:
        return self.voices[language]


def load(path: Path = PATH) -> Persona:
    raw = json.loads(path.read_text(encoding="utf-8"))
    langs = tuple(str(x["code"]) for x in raw["languages"])
    persona = Persona(
        id=raw["id"],
        name=raw["display_name"],
        role=raw["role"],
        avatar=raw["avatar_character"],
        voices=dict(raw["voices"]),
        languages=langs,
        labels={str(x["code"]): str(x["label"]) for x in raw["languages"]},
        default_language=raw["default_language"],
        hindi_forms=str(raw.get("hindi_forms", "feminine")),
    )
    assert persona.default_language in langs, "persona.json: default_language is not offered"
    assert set(langs) <= set(persona.voices), "persona.json: a language has no voice"
    return persona


PERSONA = load()
