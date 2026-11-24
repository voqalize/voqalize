"""The front-desk character, read from ``persona.json`` (one file, both halves).

Changing the character, a voice or a language is an edit to ``persona.json``
only: the prompt, the greetings, the written lines and the session's voice all
read it from here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

Lang = Literal["en", "hi"]


class LanguageOffer(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    code: Lang
    label: str
    short: str


class Persona(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    character: str
    names: dict[Lang, str]
    role: str
    voices: dict[Lang, str]
    languages: list[LanguageOffer]
    default_language: Lang

    def name(self, lang: Lang = "en") -> str:
        return self.names.get(lang) or self.names[self.default_language]

    def voice(self, lang: Lang) -> str:
        return self.voices.get(lang) or self.voices[self.default_language]

    @property
    def codes(self) -> tuple[Lang, ...]:
        return tuple(o.code for o in self.languages)

    def pick(self, asked: object) -> Lang:
        """The language a page asked for, if offered; else the default."""
        for c in self.codes:
            if c == asked:
                return c
        return self.default_language


PERSONA = Persona.model_validate(
    json.loads((Path(__file__).resolve().parent.parent / "persona.json").read_text())
)
