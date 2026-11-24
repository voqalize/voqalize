"""The application, step by step, as the counsellor fills it with a family (U2).

The owner's call of 25 Nov: the counsellor asked for every field on its own
line, said "noted" without filling anything, asked twice to confirm an email
and never moved the form on. What fixes it lives here, as plain data and pure
functions the brain's ``fill_application`` tool uses:

- the form's fields in **groups**, each asked for in one natural question
  ("your full name, date of birth and gender?");
- the two fields the applicant **types** themselves (mobile and email, X9);
- a value **checked** against the form before it is sent, so a refusal is
  known in the same turn, not a turn late;
- what a value **implies** (a city's state, a programme's intake and only
  campus), filled with it instead of asked for;
- what a step still **needs**, so the form moves on only when it can.

Everything is read from ``data/application.json`` and ``data/catalogue.json``:
the field names are the contract (CONTRACT.md).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from .data import application, catalogue

#: Typed by the applicant on screen, never asked to be said (X9): personal,
#: and hard to dictate. Said anyway, they are filled once and never confirmed twice.
TYPED: tuple[str, ...] = ("mobile", "email")

#: Each step's fields in the groups asked together, one question a group.
GROUPS: dict[int, tuple[tuple[str, ...], ...]] = {
    1: (("full_name", "date_of_birth", "gender"), ("city", "state", "parent_name")),
    2: (
        (
            "class10_board",
            "class10_percent",
            "class12_board",
            "class12_stream",
            "class12_status",
            "class12_percent",
        ),
        ("graduation_degree", "graduation_percent"),
        ("entrance_exam", "entrance_score"),
    ),
    3: (("program", "campus", "intake", "hostel", "room_type", "scholarship"),),
    4: (
        (
            "doc_class10",
            "doc_class12",
            "doc_graduation",
            "doc_score",
            "doc_photo_id",
            "doc_photo",
            "doc_income",
        ),
    ),
    5: (("pay_method", "declaration"),),
}

#: How a field is said in a question or a summary.
SAID: dict[str, str] = {
    "full_name": "full name",
    "date_of_birth": "date of birth",
    "gender": "gender",
    "mobile": "mobile number",
    "email": "email",
    "city": "city",
    "state": "state",
    "parent_name": "a parent's or guardian's name",
    "class10_board": "Class 10 board",
    "class10_percent": "Class 10 percentage",
    "class12_board": "Class 12 board",
    "class12_stream": "Class 12 stream",
    "class12_status": "whether Class 12 is passed or still to come",
    "class12_percent": "Class 12 percentage",
    "graduation_degree": "graduation degree",
    "graduation_percent": "graduation percentage",
    "entrance_exam": "entrance exam (VUSAT, JEE Main or none)",
    "entrance_score": "entrance score",
    "program": "programme",
    "campus": "campus",
    "intake": "intake",
    "hostel": "whether they need a hostel room",
    "room_type": "room type",
    "scholarship": "scholarship",
    "doc_class10": "Class 10 marksheet",
    "doc_class12": "Class 12 marksheet",
    "doc_graduation": "graduation marksheet",
    "doc_score": "entrance scorecard",
    "doc_photo_id": "photo ID",
    "doc_photo": "photograph",
    "doc_income": "income certificate",
    "pay_method": "payment method",
    "declaration": "the declaration",
}

#: Cities families name, with the state the form lists them under: a city said
#: fills its state too, never asked for ("Bangalore" is Karnataka).
CITY_STATE: dict[str, str] = {
    **dict.fromkeys(("bengaluru", "bangalore", "mysuru", "mysore", "mangaluru", "mangalore", "hubli", "belgaum"), "karnataka"),
    **dict.fromkeys(("mumbai", "bombay", "pune", "nagpur", "nashik", "thane", "aurangabad", "navi mumbai"), "maharashtra"),
    **dict.fromkeys(("delhi", "new delhi"), "delhi"),
    **dict.fromkeys(("ahmedabad", "surat", "vadodara", "baroda", "rajkot", "gandhinagar"), "gujarat"),
    **dict.fromkeys(("indore", "bhopal", "jabalpur", "gwalior"), "madhya_pradesh"),
    **dict.fromkeys(("jaipur", "jodhpur", "udaipur", "kota", "ajmer"), "rajasthan"),
    **dict.fromkeys(("chennai", "madras", "coimbatore", "madurai", "trichy", "salem"), "tamil_nadu"),
    **dict.fromkeys(("hyderabad", "secunderabad", "warangal"), "telangana"),
    **dict.fromkeys(("lucknow", "kanpur", "noida", "varanasi", "agra", "prayagraj", "allahabad", "ghaziabad", "meerut"), "uttar_pradesh"),
    **dict.fromkeys(("kolkata", "calcutta", "howrah", "siliguri", "durgapur"), "west_bengal"),
    **dict.fromkeys(("patna", "gaya", "muzaffarpur", "bhagalpur"), "bihar"),
    **dict.fromkeys(("kochi", "cochin", "thiruvananthapuram", "trivandrum", "kozhikode", "calicut", "thrissur"), "kerala"),
    **dict.fromkeys(("ludhiana", "amritsar", "jalandhar", "patiala", "mohali"), "punjab"),
}  # fmt: skip

_EMAIL = re.compile(r"^\S+@\S+\.\S+$")
_PERCENT = re.compile(r"^\s*(\d{1,3}(?:\.\d+)?)\s*(?:%|percent|per ?cent)?\s*$", re.IGNORECASE)


def order(name: str) -> int:
    """A field's place in the form, for filling in the order the page checks."""
    names = [f.name for s in application().steps for f in s.fields]
    return names.index(name) if name in names else len(names)


def title(step: int) -> str:
    return next((s.title for s in application().steps if s.step == step), f"step {step}")


def last_step() -> int:
    return max(s.step for s in application().steps)


def shown(name: str, values: Mapping[str, str]) -> bool:
    """Whether the form asks for ``name`` with these answers (the page's ``shown``)."""
    if name == "room_type":
        return values.get("hostel") == "yes"
    if name == "entrance_score":
        return values.get("entrance_exam") not in (None, "", "none")
    return True


def _is_pg(values: Mapping[str, str], focus: str | None) -> bool:
    pid = values.get("program") or focus
    p = catalogue().program(pid) if pid else None
    return p is not None and p.level == "pg"


def needs(step: int, known: Iterable[str], values: Mapping[str, str]) -> list[str]:
    """The required fields of ``step`` not filled yet, in form order (the page's ``missingIn``)."""
    have = set(known)
    s = next((x for x in application().steps if x.step == step), None)
    if s is None:
        return []
    return [f.name for f in s.fields if f.required and shown(f.name, values) and f.name not in have]


def ask_next(
    step: int, known: Iterable[str], values: Mapping[str, str], focus: str | None
) -> list[str]:
    """The fields to ask for together in the next question on ``step``: the first
    group with anything still worth asking, without what they type themselves,
    what a filled value implies (a city's state) or what does not apply."""
    have = set(known)
    pg = _is_pg(values, focus)
    for group in GROUPS.get(step, ()):
        out: list[str] = []
        for name in group:
            if name in have or name in TYPED or not shown(name, values):
                continue
            f = application().field(name)
            if f is None:
                continue
            if name.startswith("graduation_") and not pg:
                continue
            if name == "class12_percent" and values.get("class12_status") == "appearing":
                continue
            if name == "state" and "city" not in have:
                continue  # comes with the city; asked only for a city it cannot place
            if name in ("intake", "scholarship", "doc_graduation", "doc_score", "doc_income"):
                continue  # filled with the programme, or optional: never a question of its own
            if not f.required and name not in ("class12_percent", "room_type") and not pg:
                continue
            out.append(name)
        if out:
            return out
    return []


#: What a programme's ``entrance`` says when it needs no entrance test to apply.
_NO_TEST = ("no entrance test", "merit", "profile review", "portfolio review", "optional")


def needs_test(pid: str | None) -> list[str]:
    """The entrance tests a programme asks for, or ``[]`` when it needs none."""
    p = catalogue().program(pid) if pid else None
    if p is None or any(any(w in e.lower() for w in _NO_TEST) for e in p.entrance):
        return []
    return list(p.entrance)


def check(name: str, value: str, values: Mapping[str, str], focus: str | None = None) -> str | None:
    """Why the page would refuse ``value`` for ``name`` (as ``performers.ts``
    ``valueFor`` and ``invalid`` do), or ``None``. ``value`` is already resolved
    to the form's ids (``resolve_fill``). ``focus`` is the programme the
    application is for when the form does not hold it yet: "none" for the
    entrance exam of a programme that needs one is refused, with its tests."""
    f = application().field(name)
    if f is None:
        return f"the application has no field {name!r}"
    v = value.strip()
    if not v:
        return f"nothing was said for the {SAID.get(name, name)}"
    if name == "email" and not _EMAIL.match(v):
        return f"{v!r} is not an email address like name@example.com"
    if name == "mobile" and len(re.sub(r"\D", "", v)) < 10:
        return f"{v!r} is not a 10-digit mobile number"
    if f.type == "percent":
        m = _PERCENT.match(v)
        if m is None or float(m.group(1)) > 100:
            return f"the {SAID[name]} takes a number from 0 to 100"
    if f.type == "choice" and name != "campus" and v not in {oid for oid, _ in f.options}:
        return f"the {SAID.get(name, name)} has no option {v!r}"
    if name == "room_type" and values.get("hostel") != "yes":
        return "a room type is only for a hostel room: hostel must be yes first"
    pid = values.get("program")
    p = catalogue().program(pid) if pid else None
    if f.type == "program" and catalogue().program(v) is None:
        return f"no programme {v!r} in the catalogue"
    if name == "campus":
        if p is None:
            return "choose the programme first: the campus comes with it"
        if v not in p.campuses:
            names = ", ".join(catalogue().campus_name(c) for c in p.campuses)
            return f"{p.name} is taught at {names}"
    if f.type == "intake" and p is None:
        return "choose the programme first: the intake comes with it"
    if f.type == "scholarship" and v != "none":
        if p is None:
            return "choose the programme first: the scholarship comes with it"
        if v not in p.scholarships:
            return f"{p.name} does not offer {v!r}"
    if name == "entrance_exam" and v == "none" and (tests := needs_test(pid or focus)):
        return (
            f"this programme needs {' or '.join(tests)}, so 'not needed' is wrong: if they have "
            "taken neither, they register for VUSAT with this application (vusat)"
        )
    if f.type == "document" and v not in ("uploaded", "later"):
        return 'documents are marked "later" here; they upload files themselves'
    return None


def implied(name: str, value: str, known: Iterable[str]) -> dict[str, str]:
    """What a filled value fills with it, when that is still empty: a city's
    state, a programme's intake and (with one campus) its campus."""
    have = set(known)
    out: dict[str, str] = {}
    if name == "city" and "state" not in have:
        state = CITY_STATE.get(value.strip().lower())
        if state is not None:
            out["state"] = state
    if name == "program" and (p := catalogue().program(value)) is not None:
        if "intake" not in have:
            intake = catalogue().intakes.get(p.intake)
            if intake is not None:
                out["intake"] = intake.label
        if "campus" not in have and len(p.campuses) == 1:
            out["campus"] = p.campuses[0]
    return out


def said_value(name: str, value: str) -> str:
    """A filled value as the model may repeat it: the option's label for a choice."""
    f = application().field(name)
    if f is not None and f.options:
        return next((label for oid, label in f.options if oid == value), value)
    if name == "program" and (p := catalogue().program(value)) is not None:
        return p.name
    if name == "campus":
        return catalogue().campus_name(value)
    if f is not None and f.type == "percent":
        return f"{value}%"
    return value
