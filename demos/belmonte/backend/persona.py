"""The concierge's character, read from ``persona.json`` — the one file the
app reads too. Nothing else in the brain names her, her voice or a language."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_RAW: dict[str, Any] = json.loads(
    (Path(__file__).resolve().parent.parent / "persona.json").read_text()
)


@dataclass(frozen=True)
class Speaking:
    """One language the concierge speaks: its tag, its voice and its lines."""

    tag: str
    name: str
    voice: str
    greeting: str
    greeting_checked_in: str
    switched: str


NAME: str = _RAW["name"]
ROLE: str = _RAW["role"]
CHARACTER: str = _RAW["character"]
DEFAULT: str = _RAW["default_language"]
LANGUAGES: dict[str, Speaking] = {
    tag: Speaking(
        tag=tag,
        name=v["name"],
        voice=v["voice"],
        greeting=v["greeting"],
        greeting_checked_in=v["greeting_checked_in"],
        switched=v["switched"],
    )
    for tag, v in _RAW["languages"].items()
}
assert DEFAULT in LANGUAGES, "persona.json: default_language is not one of its languages"


def speaking(tag: str | None) -> Speaking:
    """The language for a tag or a name ("en", "English"), else the default."""
    want = (tag or "").strip().lower()
    for s in LANGUAGES.values():
        if want in (s.tag, s.name.lower()):
            return s
    return LANGUAGES[DEFAULT]
