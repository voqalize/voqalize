"""The lead brief — what Saatvik's sales team receives from one call.

Tushar is a product expert, and the model keeps no lead. The brain fills it from
what it already sees: the page's own events (the pages and documents opened, the
estimate run, the dealers shown, the form submitted), the visitor's questions,
and what the model passes when it opens the enquiry form — the visitor's kind of
building, bill, roof and timeline as far as the call told it. This module turns
that into one brief:

- **fields**, as the visitor gave them;
- **observed**, what they did on the site;
- **score**, a deterministic grade a salesperson can check by reading its
  reasons — never a model's opinion;
- **routing**, who should call them back;
- **summary**, the brief in a sentence or two.

Once the visitor submits the enquiry form the brief is posted to
``SAATVIK_LEAD_WEBHOOK`` when that is set — fire and forget, never in the way of
a turn — and again when the call ends. The widget shows it ("what Saatvik's
sales team receives") only in a pitch that turns it on.
"""

from __future__ import annotations

import asyncio
import json
import os
import urllib.request
from typing import Literal

from loguru import logger
from pydantic import BaseModel, Field

from voqalize.sdk import Action

Segment = Literal[
    "residential",
    "commercial",
    "industrial",
    "institutional",
    "agricultural",
    "utility",
    "dealer",
    "export",
    "investor",
    "job-seeker",
    "other",
]
Timeline = Literal[
    "immediately", "within 3 months", "3 to 6 months", "6 to 12 months", "over a year", "exploring"
]
Ownership = Literal["own", "rent", "shared"]
Grade = Literal["hot", "warm", "cold", "not sales"]

#: Segments that buy: everyone else is answered, and routed, but never scored.
BUYERS: frozenset[str] = frozenset(
    {"residential", "commercial", "industrial", "institutional", "agricultural", "utility",
     "dealer", "export"}
)  # fmt: skip


class LeadFields(BaseModel):
    """What the visitor told Tushar, or typed into the enquiry form. Every field is
    optional: a brief is useful from its first fact."""

    name: str | None = None
    company: str | None = None
    email: str | None = None
    mobile: str | None = None
    segment: Segment | None = None
    need: str | None = None
    system_size_kw: float | None = None
    monthly_units: float | None = None
    monthly_bill_inr: float | None = None
    state: str | None = None
    city: str | None = None
    roof_type: str | None = None
    roof_area: str | None = None
    ownership: Ownership | None = None
    timeline: Timeline | None = None
    budget: str | None = None
    financing_interest: bool | None = None
    subsidy_interest: bool | None = None
    products_interested: list[str] = Field(default_factory=list[str])
    decision_maker: bool | None = None
    callback_requested: bool | None = None
    preferred_time: str | None = None
    language: str | None = None
    objections: list[str] = Field(default_factory=list[str])
    enquiry_kind: str | None = None
    category: str | None = None
    message: str | None = None


class Estimate(BaseModel):
    units: float
    state: str
    rate: float
    result: str
    """The calculator's own result text, as the page read it."""


class Observed(BaseModel):
    """What the visitor did on the site during the call, from the page's events."""

    pages: list[str] = Field(default_factory=list[str])
    documents: list[str] = Field(default_factory=list[str])
    estimate: Estimate | None = None
    dealers_shown: list[str] = Field(default_factory=list[str])
    questions: list[str] = Field(default_factory=list[str])


class Score(BaseModel):
    """Points on three axes, each with the reason it was given."""

    grade: Grade
    intent: int
    fit: int
    readiness: int
    reasons: list[str]


class LeadBrief(Action):
    """The brief, whole, each time it changes: the widget's card replaces itself."""

    fields: LeadFields
    observed: Observed
    score: Score
    routing: str
    summary: str
    submitted: bool


# ─── Score ─────────────────────────────────────────────────────────────────────

#: Grades by total points out of the three axes' sum. A hot lead is one with a
#: clear need, the facts to size it and a near decision; warm has two of those.
_HOT, _WARM = 6, 3
_SOON: frozenset[str] = frozenset({"immediately", "within 3 months"})
_THIS_YEAR: frozenset[str] = frozenset({"3 to 6 months", "6 to 12 months"})


def score(f: LeadFields, o: Observed, *, submitted: bool) -> Score:
    """Intent (asking to be contacted), fit (a buyer whose system can be sized)
    and readiness (when, and who decides) — a point per reason, each written down."""
    reasons: list[str] = []
    if f.segment is not None and f.segment not in BUYERS:
        return Score(
            grade="not sales", intent=0, fit=0, readiness=0,
            reasons=[f"a {f.segment}, not a buyer: answered, not scored"],
        )  # fmt: skip

    intent = 0
    if submitted:
        intent += 2
        reasons.append("submitted the enquiry form")
    elif f.callback_requested:
        intent += 1
        reasons.append("asked for a call back")
    if o.estimate is not None:
        intent += 1
        reasons.append("ran the savings estimate")

    fit = 0
    if f.segment is not None:
        fit += 1
        reasons.append(f"{f.segment} buyer")
    if f.state:
        fit += 1
        reasons.append(f"in {f.state}")
    if f.system_size_kw or f.monthly_units or f.monthly_bill_inr or o.estimate is not None:
        fit += 1
        reasons.append("the system can be sized")

    readiness = 0
    if f.timeline in _SOON:
        readiness += 2
        reasons.append(f"timeline {f.timeline}")
    elif f.timeline in _THIS_YEAR:
        readiness += 1
        reasons.append(f"timeline {f.timeline}")
    if f.decision_maker:
        readiness += 1
        reasons.append("the decision maker")
    if f.ownership == "own":
        readiness += 1
        reasons.append("owns the roof")

    total = intent + fit + readiness
    grade: Grade = "hot" if total >= _HOT else "warm" if total >= _WARM else "cold"
    return Score(grade=grade, intent=intent, fit=fit, readiness=readiness, reasons=reasons)


# ─── Routing and summary ───────────────────────────────────────────────────────


def routing(f: LeadFields, o: Observed) -> str:
    """Who calls back: the team for the segment, else the state's distributors."""
    match f.segment:
        case "investor":
            return "Investor relations, not sales"
        case "job-seeker":
            return "Careers, not sales"
        case "dealer":
            return "Channel partner team"
        case "export":
            return "Export sales"
        case "utility" | "industrial":
            return "Module and project sales"
        case _:
            pass
    if not f.state:
        return "Sales desk: state not yet known"
    route = f"Route to the {f.state} distributors"
    if o.dealers_shown:
        route += f": {', '.join(o.dealers_shown[:_DEALERS_NAMED])}"
    return route


#: Dealers named in the routing line: the nearest few the visitor saw, not the list.
_DEALERS_NAMED = 3


def summary(f: LeadFields, o: Observed) -> str:
    who = f.name or "A visitor"
    what = f.segment or "solar"
    where = ", ".join(x for x in (f.city, f.state) if x)
    first = f"{who}{f' ({f.company})' if f.company else ''}: {what} enquiry"
    if where:
        first += f" from {where}"
    facts: list[str] = []
    if f.need:
        facts.append(f.need)
    if f.system_size_kw:
        facts.append(f"about {f.system_size_kw:g} kW")
    if f.monthly_units:
        facts.append(f"{f.monthly_units:g} units a month")
    if f.monthly_bill_inr:
        facts.append(f"bill ₹{f.monthly_bill_inr:,.0f} a month")
    if f.timeline:
        facts.append(f"timeline {f.timeline}")
    if f.financing_interest:
        facts.append("wants financing")
    if f.subsidy_interest:
        facts.append("asked about the subsidy")
    if f.callback_requested:
        facts.append(f"wants a call back{f' ({f.preferred_time})' if f.preferred_time else ''}")
    if o.estimate is not None:
        facts.append("ran the savings estimate")
    return f"{first}." + (f" {'; '.join(facts).capitalize()}." if facts else "")


# ─── The lead ──────────────────────────────────────────────────────────────────

#: Visitor questions kept for the brief: the latest, clipped, enough to show
#: what they cared about without a transcript.
_QUESTIONS = 6
_QUESTION_CHARS = 140


class Lead:
    """One call's lead: the fields, what was observed, and whether it is submitted."""

    def __init__(self) -> None:
        self.fields = LeadFields()
        self.observed = Observed()
        self.submitted = False

    def update(self, **values: object) -> list[str]:
        """Merge every value that is set; lists are added to, not replaced.
        Returns the names that changed."""
        changed: list[str] = []
        current = self.fields.model_dump()
        for key, value in values.items():
            if value is None or key not in current:
                continue
            if isinstance(value, list):
                old: list[str] = current[key]
                new = old + [str(v) for v in value if str(v) not in old]  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
                if new != old:
                    current[key] = new
                    changed.append(key)
            elif current[key] != value:
                current[key] = value
                changed.append(key)
        if changed:
            self.fields = LeadFields.model_validate(current)
        return changed

    def asked(self, text: str) -> None:
        text = " ".join(text.split())
        if text:
            q = self.observed.questions
            q.append(text[:_QUESTION_CHARS])
            del q[:-_QUESTIONS]

    def saw_page(self, path: str) -> None:
        if path not in self.observed.pages:
            self.observed.pages.append(path)

    def saw_document(self, title: str) -> None:
        if title not in self.observed.documents:
            self.observed.documents.append(title)

    def brief(self) -> LeadBrief:
        f, o = self.fields, self.observed
        return LeadBrief(
            fields=f,
            observed=o.model_copy(deep=True),
            score=score(f, o, submitted=self.submitted),
            routing=routing(f, o),
            summary=summary(f, o),
            submitted=self.submitted,
        )


# ─── The webhook ───────────────────────────────────────────────────────────────

WEBHOOK_ENV = "SAATVIK_LEAD_WEBHOOK"
_WEBHOOK_TIMEOUT_S = 5.0
_in_flight: set[asyncio.Task[None]] = set()


def post_brief(brief: LeadBrief) -> None:
    """POST the brief as JSON to ``$SAATVIK_LEAD_WEBHOOK``, if set, and return at
    once. A failure is logged and dropped: the call never waits on a CRM."""
    url = os.environ.get(WEBHOOK_ENV)
    if not url:
        return
    body = json.dumps(brief.model_dump(mode="json")).encode()

    def send() -> None:
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=_WEBHOOK_TIMEOUT_S) as resp:
            resp.read()

    async def run() -> None:
        try:
            await asyncio.to_thread(send)
        except Exception as exc:  # any failure of a third party's endpoint
            logger.warning("saatvik: lead webhook failed: {}", exc)

    task = asyncio.get_running_loop().create_task(run())
    _in_flight.add(task)
    task.add_done_callback(_in_flight.discard)


__all__ = [
    "BUYERS",
    "WEBHOOK_ENV",
    "Estimate",
    "Lead",
    "LeadBrief",
    "LeadFields",
    "Observed",
    "Score",
    "post_brief",
    "routing",
    "score",
    "summary",
]
