"""The claim form's rules, from ``data/claim_form.json``: which fields a claim
of each type shows given the answers so far, what each field accepts, and what
is still missing. The page applies the same file, so a field the brain thinks
is hidden is hidden on screen too."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from voqalize.sdk.stage import match_label

from . import amounts
from .store import CLAIM_FORM, CUSTOMER, NETWORK, POLICIES, member_ids, member_name, policies_for

Json = dict[str, Any]

TYPES: dict[str, Json] = {t["id"]: t for t in CLAIM_FORM["types"]}
SECTIONS: list[Json] = CLAIM_FORM["sections"]
FIELDS: dict[str, Json] = {f["id"]: f for s in SECTIONS for f in s["fields"]}
SECTION_OF: dict[str, str] = {f["id"]: s["id"] for s in SECTIONS for f in s["fields"]}
DOCUMENTS: list[Json] = CLAIM_FORM["documents"]


def sections_for(claim_type: str) -> list[Json]:
    return [s for s in SECTIONS if claim_type in s["types"]]


def _shown(rule: Json | None, values: dict[str, str]) -> bool:
    if not rule:
        return True
    return all(values.get(k) in allowed for k, allowed in rule.items())


def visible(field_id: str, values: dict[str, str]) -> bool:
    return _shown(FIELDS[field_id].get("show_if"), values)


def options(field_id: str, claim_type: str, values: dict[str, str]) -> list[tuple[str, str]]:
    """(value, label) a select field takes now; empty for a free field."""
    f = FIELDS[field_id]
    if "options" in f:
        return [(o["value"], o["label"]) for o in f["options"]]
    match f.get("options_from"):
        case "policies":
            ps = policies_for(TYPES[claim_type]["products"])
            return [(p["id"], f"{p['plan']} — {p.get('policy_number', '')}") for p in ps]
        case "members":
            return [(m, member_name(m)) for m in member_ids(values.get("policy_id"))]
        case "garages":
            return [(g["id"], g["name"]) for g in NETWORK.get("garages", [])] + [
                ("other", "Other garage")
            ]
        case "hospitals":
            return [(h["id"], h["name"]) for h in NETWORK.get("hospitals", [])] + [
                ("other", "Other hospital")
            ]
        case _:
            return []


@dataclass
class ClaimState:
    """The claim form as the brain knows it: the values it set, the names the
    page says hold something, and what the page last said is missing."""

    claim_type: str | None = None
    values: dict[str, str] = field(default_factory=dict)
    filled_on_page: set[str] = field(default_factory=lambda: set())
    page_missing: list[str] | None = None
    documents: set[str] = field(default_factory=lambda: set())
    reference: str | None = None

    def start(self, claim_type: str, policy_id: str | None) -> None:
        if claim_type != self.claim_type:
            self.values = {}
            self.filled_on_page = set()
            self.page_missing = None
            self.documents = set()
            self.reference = None
        self.claim_type = claim_type
        self.values.setdefault("contact_phone", CUSTOMER.get("phone", ""))
        self.values.setdefault("contact_email", CUSTOMER.get("email", ""))
        if policy_id:
            self.values["policy_id"] = policy_id

    def filled(self, field_id: str) -> bool:
        return bool(self.values.get(field_id)) or field_id in self.filled_on_page

    def missing(self) -> list[str]:
        """Required, visible fields still empty, in form order."""
        if self.claim_type is None:
            return []
        out: list[str] = []
        for s in sections_for(self.claim_type):
            for f in s["fields"]:
                if f.get("optional") or not visible(f["id"], self.values):
                    continue
                if not self.filled(f["id"]):
                    out.append(f["id"])
        return out

    def documents_needed(self) -> list[Json]:
        if self.claim_type is None:
            return []
        return [
            d
            for d in DOCUMENTS
            if self.claim_type in d["types"]
            and not d.get("optional")
            and _shown(d.get("show_if"), self.values)
            and d["id"] not in self.documents
        ]


_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")


def normalise(field_id: str, raw: str, state: ClaimState, today: date) -> tuple[str | None, str]:
    """The value the form stores, or None and why it was not taken."""
    if field_id not in FIELDS:
        return None, "no such field on the claim form"
    claim_type = state.claim_type or "motor"
    if SECTION_OF[field_id] not in {s["id"] for s in sections_for(claim_type)}:
        return None, f"not a field of a {claim_type} claim"
    if not visible(field_id, {**state.values}):
        rule = FIELDS[field_id].get("show_if") or {}
        why = ", ".join(f"{k} is {' or '.join(v)}" for k, v in rule.items())
        return None, f"only asked when {why}"
    f = FIELDS[field_id]
    value = str(raw).strip()
    if not value:
        return None, "empty"
    kind = f["type"]
    if kind == "select":
        opts = options(field_id, claim_type, state.values)
        by_value = {v.lower(): v for v, _ in opts}
        if value.lower() in by_value:
            return by_value[value.lower()], ""
        label = match_label(value, [lbl for _, lbl in opts])
        if label is not None:
            return next(v for v, lbl in opts if lbl == label), ""
        return None, "options: " + "; ".join(f"{v} ({lbl})" for v, lbl in opts)
    if kind == "date":
        if not _DATE.match(value):
            return None, "a date as YYYY-MM-DD"
        try:
            d = date.fromisoformat(value)
        except ValueError:
            return None, "not a real date"
        if d > today:
            return None, f"a date in the future (today is {today.isoformat()})"
        return value, ""
    if kind == "time":
        if not _TIME.match(value):
            return None, "a time as HH:MM, 24-hour"
        h, m = value.split(":")
        return f"{int(h):02d}:{m}", ""
    if kind == "money":
        return money(field_id, value)
    if pattern := f.get("pattern"):
        value = value.upper().replace(" ", "")
        if not re.match(pattern, value):
            return None, f"does not look like an {f['label']}"
    return value, ""


#: The least an amount can plausibly be: below it the unit was surely lost
#: ("1.5 lakh" read as 15), so it is confirmed with the customer, never stored.
MONEY_FLOOR = {"claim_amount": 1_000, "estimate_amount": 500}
MONEY_CEILING = 10_00_00_000


def money(field_id: str, said: str) -> tuple[str | None, str]:
    """Rupees from what the customer said ("around 1 and half lakhs" → 150000).
    Taken: the digits and a note to say it back. Not taken: why, to ask again."""
    heard = amounts.parse(said)
    if heard is None:
        return None, "no amount heard: ask how much, in rupees"
    n = heard.rupees
    if n < MONEY_FLOOR.get(field_id, 1):
        return None, (
            f"{amounts.inr(n)} is too small to be right (a unit like lakh was probably lost): "
            "ask the customer to confirm the amount"
        )
    if n > MONEY_CEILING:
        return (
            None,
            f"{amounts.inr(n)} is too large to be right: ask the customer to confirm the amount",
        )
    note = ""
    if heard.low is not None:
        note = f"a range ({amounts.inr(heard.low)} to {amounts.inr(n)}): the higher end was taken; check it"
    elif heard.approx:
        note = "an estimate: fine for the form"
    return str(n), note


def display(field_id: str, value: str, state: ClaimState) -> str:
    """A filled value as the customer would read it on the form."""
    f = FIELDS[field_id]
    match f["type"]:
        case "money":
            return amounts.inr(int(value)) if value.isdigit() else value
        case "date":
            try:
                return date.fromisoformat(value).strftime("%d %b %Y")
            except ValueError:
                return value
        case "select":
            opts = dict(options(field_id, state.claim_type or "motor", state.values))
            return opts.get(value, value)
        case _:
            return value


def outline(claim_type: str, state: ClaimState) -> str:
    """The form as a list a model can work through."""
    lines: list[str] = []
    for s in sections_for(claim_type):
        if not s["fields"]:
            continue
        parts: list[str] = []
        for f in s["fields"]:
            if not visible(f["id"], state.values):
                continue
            tag = f["id"] + ("" if not f.get("optional") else " (optional)")
            if state.filled(f["id"]):
                tag += " ✓"
            opts = options(f["id"], claim_type, state.values)
            if opts and len(opts) <= 9:
                tag += " [" + ", ".join(v for v, _ in opts) + "]"
            parts.append(tag)
        if parts:
            lines.append(f"- {s['id']} ({s['title']}): " + "; ".join(parts))
    return "\n".join(lines)


def outline_for_prompt() -> str:
    """Every section and field of both claim types, with their show_if rules."""
    out: list[str] = []
    for t in TYPES.values():
        out.append(f"{t['id']} claim ({t['hint']}):")
        for s in sections_for(t["id"]):
            if not s["fields"]:
                continue
            parts: list[str] = []
            for f in s["fields"]:
                tag = f["id"]
                if "options" in f:
                    tag += " [" + ", ".join(o["value"] for o in f["options"]) + "]"
                elif f.get("options_from"):
                    tag += f" [{f['options_from']} id]"
                elif f["type"] in ("date", "time", "money"):
                    tag += f" ({f['type']})"
                if f.get("optional"):
                    tag += " optional"
                if rule := f.get("show_if"):
                    tag += " only if " + ", ".join(f"{k}={'/'.join(v)}" for k, v in rule.items())
                parts.append(tag)
            out.append(f"  {s['id']}: " + "; ".join(parts))
    docs = "; ".join(f"{d['id']} ({'/'.join(d['types'])})" for d in DOCUMENTS)
    out.append(f"Documents (the customer uploads them): {docs}.")
    return "\n".join(out)


def policy_options_line(claim_type: str) -> str:
    ps = policies_for(TYPES[claim_type]["products"])
    return "; ".join(f"{p['id']} ({p['plan']}, {p.get('summary', '')[:90]})" for p in ps)


__all__ = [
    "DOCUMENTS",
    "FIELDS",
    "POLICIES",
    "SECTION_OF",
    "TYPES",
    "ClaimState",
    "normalise",
    "options",
    "outline",
    "sections_for",
    "visible",
]
