"""The three forms the assistant fills (CONTRACT.md, "Forms"): their fields, the
step each lives on, and the checks a value must pass before it goes on screen.
The page runs the same checks; a value refused here never reaches it."""

from __future__ import annotations

import re
from datetime import date

from .bank import CARD_IDS, LOAN_IDS, PRODUCTS, today

FormName = str  # "open_account" | "card_apply" | "loan_apply"

_OPEN = PRODUCTS["account_opening"]
OPEN_STEPS: list[tuple[int, str, list[str]]] = [
    (s["n"], s["title"], list(s["fields"])) for s in _OPEN["steps"]
]
STEP_OF: dict[str, int] = {f: n for n, _, fields in OPEN_STEPS for f in fields}

CHOICES: dict[str, dict[str, list[str]]] = {
    "open_account": dict(_OPEN["choices"]),
    "card_apply": {**PRODUCTS["card_application"]["choices"], "card_id": list(CARD_IDS)},
    "loan_apply": {**PRODUCTS["loan_application"]["choices"], "loan_type": list(LOAN_IDS)},
}

FIELDS: dict[str, list[str]] = {
    "open_account": [f for _, _, fields in OPEN_STEPS for f in fields],
    "card_apply": list(PRODUCTS["card_application"]["fields"]),
    "loan_apply": list(PRODUCTS["loan_application"]["fields"]),
}

_LOAN_EXTRA = {"home": "property_value", "gold": "gold_grams", "car": "car_price"}
_LOAN_OPTIONAL = {"employer", "existing_emis", "property_value", "gold_grams", "car_price"}


def required(form: str, values: dict[str, str]) -> list[str]:
    """The fields a form needs before it can be submitted, in form order."""
    if form == "loan_apply":
        need = [f for f in FIELDS[form] if f not in _LOAN_OPTIONAL]
        extra = _LOAN_EXTRA.get(values.get("loan_type", ""))
        return [*need, extra] if extra else need
    return list(FIELDS[form])


def missing(form: str, values: dict[str, str]) -> list[str]:
    return [f for f in required(form, values) if not values.get(f)]


_NAME = re.compile(r"^[A-Za-zऀ-ॿ][A-Za-zऀ-ॿ .'-]{1,60}$")
_PAN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")


def _digits(v: str) -> str:
    return re.sub(r"\D", "", v)


def check(form: str, field: str, raw: str) -> tuple[str | None, str | None]:
    """``(value, None)`` as the form takes it, or ``(None, why)``."""
    v = str(raw).strip()
    if field not in FIELDS.get(form, []):
        return None, f"the form has no field {field}"
    if not v:
        return None, "it is empty"
    choices = CHOICES[form].get(field)
    if choices is not None:
        low = v.lower().replace(" ", "_").replace("-", "_")
        if low not in choices:
            return None, f"choose one of {', '.join(choices)}"
        return low, None
    if field in ("full_name", "nominee_name"):
        return (v, None) if _NAME.match(v) else (None, "a name, in letters")
    if field in ("date_of_birth", "nominee_dob"):
        try:
            d = date.fromisoformat(v)
        except ValueError:
            return None, "a date as YYYY-MM-DD"
        age = (today() - d).days // 365
        if d >= today():
            return None, "a date in the past"
        if field == "date_of_birth" and age < 18:
            return None, "the applicant must be 18 or older"
        return d.isoformat(), None
    if field == "mobile":
        d = _digits(v)
        d = d[-10:] if len(d) > 10 and d.startswith("91") else d
        return (
            (d, None)
            if re.fullmatch(r"[6-9]\d{9}", d)
            else (None, "a 10-digit Indian mobile number")
        )
    if field == "email":
        return (
            (v.lower(), None)
            if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v)
            else (None, "an email address")
        )
    if field == "pincode":
        d = _digits(v)
        return (d, None) if re.fullmatch(r"[1-9]\d{5}", d) else (None, "a 6-digit PIN code")
    if field == "pan":
        p = re.sub(r"\s", "", v).upper()
        return (
            (p, None)
            if _PAN.match(p)
            else (None, "a PAN like ABCDE1234F: five letters, four digits, a letter")
        )
    if field == "aadhaar":
        d = _digits(v)
        return (d, None) if re.fullmatch(r"[2-9]\d{11}", d) else (None, "a 12-digit Aadhaar number")
    if field in (
        "monthly_income",
        "existing_emis",
        "amount",
        "property_value",
        "car_price",
        "gold_grams",
    ):
        try:
            n = float(v.replace(",", "").replace("₹", ""))
        except ValueError:
            return None, "a number"
        if n < 0 or (n == 0 and field not in ("existing_emis",)):
            return None, "a positive number"
        return (str(int(n)) if n.is_integer() else str(n)), None
    if field == "tenure_months":
        d = _digits(v)
        return (d, None) if d and 1 <= int(d) <= 360 else (None, "a number of months")
    return v, None
