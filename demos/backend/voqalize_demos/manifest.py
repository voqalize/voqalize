"""The demos registry — the backend half of the shared spine.

Reads ``demos/manifest.json`` (the single source of truth both trees share) and
binds each demo name to the ``Brain`` factory that serves it. The umbrella app
mounts one WebSocket route per entry; a name in the JSON with no bound brain here
(or vice versa) is a wiring error we fail loudly on at startup.

Adding a demo: an entry in ``manifest.json`` + its brain module + one line in
:data:`_BRAIN_FACTORIES`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from voqalize.sdk import Brain
from voqalize_demos.brains.aura import AuraBrain
from voqalize_demos.brains.interview_bot import InterviewBotBrain
from voqalize_demos.brains.lead_qual import LeadQualBrain
from voqalize_demos.brains.legal import LegalBrain
from voqalize_demos.brains.servicing import ServicingBrain
from voqalize_demos.brains.shopping import ShoppingBrain
from voqalize_demos.brains.sugar import SugarBrain
from voqalize_demos.brains.support import SupportBrain
from voqalize_demos.brains.travel import TravelBrain
from voqalize_demos.llm import GeminiProvider

# demos/backend/voqalize_demos/manifest.py → demos/manifest.json
_MANIFEST_PATH = Path(__file__).resolve().parents[2] / "manifest.json"

# name → build(provider) → Brain. The name is the URL segment Voqalize dials
# (``/{name}/s/{session_id}``). Each factory builds a fresh brain per session.
_BRAIN_FACTORIES: dict[str, Callable[[GeminiProvider], Brain]] = {
    "travel": lambda llm: TravelBrain(llm=llm),
    "shopping": lambda llm: ShoppingBrain(llm=llm),
    "support": lambda llm: SupportBrain(llm=llm),
    "servicing": lambda llm: ServicingBrain(llm=llm),
    "interview_bot": lambda llm: InterviewBotBrain(llm=llm),
    "sugar": lambda llm: SugarBrain(llm=llm),
    "legal": lambda llm: LegalBrain(llm=llm),
    "lead_qual": lambda llm: LeadQualBrain(llm=llm),
    "aura": lambda llm: AuraBrain(llm=llm),
}


@dataclass(frozen=True)
class Demo:
    """One demo's metadata, as declared in ``manifest.json``."""

    name: str
    title: str
    tagline: str
    stt: dict[str, Any]
    tts: dict[str, Any]


def load_demos() -> list[Demo]:
    """Parse ``manifest.json`` into :class:`Demo` records (declaration order)."""
    raw = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    return [
        Demo(
            name=d["name"],
            title=d["title"],
            tagline=d["tagline"],
            stt=d["stt"],
            tts=d["tts"],
        )
        for d in raw["demos"]
    ]


def brain_factory(name: str) -> Callable[[GeminiProvider], Brain]:
    """The ``Brain`` factory bound to ``name``. Raises if none is registered."""
    build = _BRAIN_FACTORIES.get(name)
    if build is None:
        raise KeyError(f"no brain registered for demo {name!r}")
    return build


def check_wiring() -> list[Demo]:
    """Load the manifest and assert every declared demo has a bound brain (and no
    brain is bound to an undeclared name). Returns the demos. Called at startup so
    a manifest/registry drift fails the process, not a live session."""
    demos = load_demos()
    declared = {d.name for d in demos}
    bound = set(_BRAIN_FACTORIES)
    if missing := declared - bound:
        raise RuntimeError(f"demos declared in manifest.json but no brain bound: {sorted(missing)}")
    if orphan := bound - declared:
        raise RuntimeError(f"brains bound but not declared in manifest.json: {sorted(orphan)}")
    return demos
