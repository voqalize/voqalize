"""Anvaya University's authored data, read once: the catalogue, the admissions
content, the application form and the persona.

The page reads the same files (``demos/university/data/*.json`` and
``persona.json``), so what the agent says and what the screen shows are one
truth. Everything here is fictional.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

Level = Literal["ug", "pg", "diploma", "certificate"]
Mode = Literal["full_time", "online", "weekend", "hybrid"]
SchoolId = Literal["engineering", "business", "design", "law", "health", "liberal-arts", "online"]
CampusId = Literal["pune", "bengaluru", "online"]
Stream = Literal["science_pcm", "science_pcb", "commerce", "humanities", "other"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class Persona(_Model):
    """``persona.json``: the one place the character lives."""

    character: str
    name: str
    gender: Literal["male", "female"]
    role: str
    languages: tuple[str, ...]
    default_language: str
    voices: dict[str, str]
    language_names: dict[str, str]


class Eligibility(_Model):
    requires: Literal["class12", "graduation"]
    min_percent: float
    needs: str
    streams: tuple[str, ...] = ()
    min_experience_years: int = 0


class Outcomes(_Model):
    placement_pct: int | None = None
    median_ctc_lpa: float | None = None
    highest_ctc_lpa: float | None = None
    note: str | None = None
    roles: tuple[str, ...] = ()


class Program(_Model):
    id: str
    name: str
    award: str
    school: str
    level: Level
    mode: Mode
    campuses: tuple[str, ...]
    duration_months: int
    duration_label: str
    hours_per_week: int
    fee_per_year: int
    fee_total: int
    application_fee: int
    seats: int
    intake: str
    eligibility: Eligibility
    entrance: tuple[str, ...]
    selection: tuple[str, ...]
    scholarships: tuple[str, ...]
    outcomes: Outcomes
    highlights: tuple[str, ...]
    modules: tuple[str, ...]
    interests: tuple[str, ...]
    specialisations: tuple[str, ...]


class School(_Model):
    id: str
    name: str
    short: str
    campuses: tuple[str, ...]
    blurb: str


class Labelled(_Model):
    id: str
    label: str


class Campus(_Model):
    id: str
    name: str
    label: str


class Band(_Model):
    id: str
    label: str
    min: int
    max: int


class Round(_Model):
    name: str
    deadline: str
    note: str | None = None


class Intake(_Model):
    label: str
    starts: str
    rounds: tuple[Round, ...]


class Tier(_Model):
    rule: str
    waiver: int


class Scholarship(_Model):
    id: str
    name: str
    basis: str
    tiers: tuple[Tier, ...]
    # ``for`` is a Python keyword: read it under another name.
    applies_to: str = ""


class Catalogue(_Model):
    schools: tuple[School, ...]
    campuses: tuple[Campus, ...]
    levels: tuple[Labelled, ...]
    modes: tuple[Labelled, ...]
    fee_bands: tuple[Band, ...]
    hour_bands: tuple[Band, ...]
    intakes: dict[str, Intake]
    scholarships: tuple[Scholarship, ...]
    programs: tuple[Program, ...]

    def program(self, pid: str) -> Program | None:
        return next((p for p in self.programs if p.id == pid), None)

    def school(self, sid: str) -> School:
        return next(s for s in self.schools if s.id == sid)

    def scholarship(self, sid: str) -> Scholarship | None:
        return next((s for s in self.scholarships if s.id == sid), None)

    def campus_name(self, cid: str) -> str:
        return next((c.name for c in self.campuses if c.id == cid), cid)

    def level_label(self, lid: str) -> str:
        return next((x.label for x in self.levels if x.id == lid), lid)

    def mode_label(self, mid: str) -> str:
        return next((x.label for x in self.modes if x.id == mid), mid)


class FormField(_Model):
    name: str
    label: str
    type: str
    required: bool = False
    private: bool = False
    options: tuple[tuple[str, str], ...] = ()


class FormStep(_Model):
    step: int
    id: str
    title: str
    fields: tuple[FormField, ...]


class Application(_Model):
    steps: tuple[FormStep, ...]
    document_values: tuple[tuple[str, str], ...]

    def field(self, name: str) -> FormField | None:
        return next((f for s in self.steps for f in s.fields if f.name == name), None)

    def step_of(self, name: str) -> int | None:
        return next((s.step for s in self.steps for f in s.fields if f.name == name), None)


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@cache
def persona() -> Persona:
    return Persona.model_validate(_read(ROOT / "persona.json"))


@cache
def catalogue() -> Catalogue:
    raw = _read(DATA / "catalogue.json")
    for s in raw["scholarships"]:
        s["applies_to"] = s.get("for", "")
    return Catalogue.model_validate(raw)


@cache
def application() -> Application:
    return Application.model_validate(_read(DATA / "application.json"))


@cache
def admissions() -> dict[str, Any]:
    return _read(DATA / "admissions.json")


def inr(amount: float) -> str:
    """₹ with Indian digit grouping: 340000 → ₹3,40,000."""
    n = round(amount)
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return ("-" if n < 0 else "") + "₹" + s
