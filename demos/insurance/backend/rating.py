"""The quote engine: ``data/products.json``'s ``method`` lines, in Python.

The page has the same engine in TypeScript (``frontend/src/quote/rating.ts``), so a
premium is the same whether a visitor clicks the form full or Ananya fills it by
voice. ``data/quote_cases.json`` holds golden cases written by this module and
checked by both test suites; regenerate them after changing a table::

    cd demos && uv run python insurance/backend/rating.py --cases

Answers are strings, as the form stores them (option values, digits). Every
breakdown line is rounded to the rupee, half up; the net is the sum of the
rounded lines, so the lines on screen always add up to what Ananya says.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"

Json = dict[str, Any]


def load_products() -> Json:
    return json.loads((DATA / "products.json").read_text(encoding="utf-8"))


PRODUCTS_FILE: Json = load_products()
PRODUCTS: dict[str, Json] = {p["id"]: p for p in PRODUCTS_FILE["products"]}
CITIES: dict[str, Json] = {c["value"]: c for c in PRODUCTS_FILE["cities"]}
RATING_YEAR: int = PRODUCTS_FILE["rating_year"]
NCB_BY_YEARS: list[int] = PRODUCTS_FILE["ncb"]["by_years"]


def rnd(x: float) -> int:
    """Half up, to the rupee — the same as the page's Math.round for positives."""
    return math.floor(x + 0.5 + 1e-9)


def inr(amount: float) -> str:
    """₹1,25,000 — Indian digit grouping."""
    n = rnd(abs(amount))
    s = str(n)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return ("-" if amount < 0 else "") + "₹" + s


@dataclass
class Line:
    id: str
    label: str
    amount: int

    def as_json(self) -> Json:
        return {"id": self.id, "label": self.label, "amount": self.amount}


@dataclass
class Quote:
    product: str
    complete: bool
    missing: list[str] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)
    net: int = 0
    gst_percent: int = 0
    gst: int = 0
    total: int = 0
    idv: int | None = None
    unavailable: dict[str, str] = field(default_factory=dict)
    error: str | None = None

    def as_json(self) -> Json:
        out: Json = {
            "complete": self.complete,
            "missing": self.missing,
            "lines": [ln.as_json() for ln in self.lines],
            "net": self.net,
            "gst_percent": self.gst_percent,
            "gst": self.gst,
            "total": self.total,
        }
        if self.idv is not None:
            out["idv"] = self.idv
        if self.unavailable:
            out["unavailable"] = self.unavailable
        if self.error:
            out["error"] = self.error
        return out


def required_fields(product: str) -> list[str]:
    return [f["id"] for f in PRODUCTS[product]["fields"] if not f.get("optional")]


def defaults(product: str) -> dict[str, str]:
    return {f["id"]: str(f["default"]) for f in PRODUCTS[product]["fields"] if "default" in f}


def default_addons(product: str) -> list[str]:
    return [a["id"] for a in PRODUCTS[product]["addons"] if a.get("default")]


def _addon(product: str, addon_id: str) -> Json:
    return next(a for a in PRODUCTS[product]["addons"] if a["id"] == addon_id)


def _first(rows: list[list[Any]], value: float) -> Any:
    """The second item of the first ``[upper, x]`` row with ``value <= upper``."""
    for upper, x in rows:
        if value <= upper:
            return x
    return rows[-1][1]


def _zone(answers: dict[str, str]) -> str:
    return CITIES.get(answers.get("city", ""), {"zone": "B"})["zone"]


def quote(product: str, answers: dict[str, str], addons: list[str] | None = None) -> Quote:
    """The premium for these answers and add-ons, or what is still missing."""
    spec = PRODUCTS[product]
    a = {**defaults(product), **{k: str(v) for k, v in answers.items() if v not in (None, "")}}
    on = list(default_addons(product) if addons is None else addons)
    missing = [f for f in required_fields(product) if f not in a]
    q = Quote(product=product, complete=False, missing=missing, gst_percent=spec["gst_percent"])
    if missing:
        return q
    try:
        engine = _ENGINES[product]
        base_lines, ctx = engine(spec, a)
    except _Refused as r:
        q.error = str(r)
        return q
    q.idv = ctx.get("idv")
    lines = list(base_lines)
    for addon_id in [x["id"] for x in spec["addons"]]:
        why = _unavailable(product, addon_id, a, ctx)
        if why:
            q.unavailable[addon_id] = why
            continue
        if addon_id in on:
            ad = _addon(product, addon_id)
            lines.append(Line(f"addon:{addon_id}", ad["label"], rnd(_addon_price(ad, a, ctx))))
    q.lines = [ln for ln in lines if ln.amount != 0 or not _is_discount(ln.id)]
    q.net = sum(ln.amount for ln in q.lines)
    q.gst = rnd(q.net * spec["gst_percent"] / 100)
    q.total = q.net + q.gst
    q.complete = True
    return q


_DISCOUNTS = {"ncb", "vd", "copay", "high_cover", "security", "group", "ped"}


def _is_discount(line_id: str) -> bool:
    return line_id in _DISCOUNTS


class _Refused(Exception):
    pass


def _age(a: dict[str, str]) -> int:
    return max(0, RATING_YEAR - int(a["registration_year"]))


def _idv(spec: Json, a: dict[str, str], age: int) -> int:
    dep = spec["tables"]["idv_depreciation_by_age"][min(age, 5)]
    raw = int(a["ex_showroom"]) * (1 - dep / 100)
    return rnd(raw / 100) * 100


def _motor(spec: Json, a: dict[str, str], od_rate: float, tp: float) -> tuple[list[Line], Json]:
    t = spec["tables"]
    age = _age(a)
    idv = _idv(spec, a, age)
    od = idv * od_rate / 100 * t["fuel_factor"][a.get("fuel", "petrol")]
    years = min(int(a["claim_free_years"]), 5)
    ncb_pct = NCB_BY_YEARS[years]
    ncb = od * ncb_pct / 100
    vd_pct = t.get("voluntary_deductible_discount_percent", {}).get(
        a.get("voluntary_deductible", "0"), 0
    )
    vd = (od - ncb) * vd_pct / 100
    if a.get("fuel") == "electric":
        tp *= t["third_party_electric_factor"]
    lines = [
        Line("od", f"Own damage (IDV {inr(idv)})", rnd(od)),
        Line("ncb", f"No Claim Bonus ({ncb_pct}%)", -rnd(ncb)),
        Line("vd", f"Voluntary deductible discount ({vd_pct}%)", -rnd(vd)),
        Line("tp", "Third-party cover", rnd(tp)),
    ]
    return lines, {"idv": idv, "age": age, "ncb_pct": ncb_pct}


def _car(spec: Json, a: dict[str, str]) -> tuple[list[Line], Json]:
    t = spec["tables"]
    age = _age(a)
    band = 0 if age <= 4 else 1 if age <= 9 else 2
    rate = t["od_rate_percent"][a["vehicle_class"]][_zone(a)][band]
    return _motor(spec, a, rate, t["third_party"][a["vehicle_class"]])


def _bike(spec: Json, a: dict[str, str]) -> tuple[list[Line], Json]:
    t = spec["tables"]
    rate = t["od_rate_percent"][a["engine_cc"]][_zone(a)]
    return _motor(spec, a, rate, t["third_party"][a["engine_cc"]])


def _health(spec: Json, a: dict[str, str]) -> tuple[list[Line], Json]:
    t = spec["tables"]
    adults, children = int(a["adults"]), int(a.get("children", "0"))
    if a["cover_type"] == "individual" and (adults != 1 or children != 0):
        raise _Refused(
            "an individual policy covers one adult and no children; choose a family floater"
        )
    eldest = int(a["eldest_age"])
    band = next(i for i, (upper, _) in enumerate(t["age_bands"]) if eldest <= upper)
    one = t["base_by_band"][a["sum_insured"]][band]
    base = (
        one
        * (1 + t["second_adult_factor"] * (adults - 1) + t["child_factor"] * children)
        * t["zone_factor"][_zone(a)]
    )
    ped = base * t["pre_existing_loading_percent"] / 100 if a["pre_existing"] == "yes" else 0
    copay_pct = t["copay_discount_percent"][a.get("voluntary_copay", "0")]
    copay = (base + ped) * copay_pct / 100
    lines = [
        Line("base", "Base premium", rnd(base)),
        Line("ped", "Pre-existing illness loading (10%)", rnd(ped)),
        Line("copay", f"Voluntary co-pay discount ({copay_pct}%)", -rnd(copay)),
    ]
    return lines, {"base": base, "adults": adults}


def _term(spec: Json, a: dict[str, str]) -> tuple[list[Line], Json]:
    t = spec["tables"]
    age = int(a["age"])
    till = int(a["cover_till_age"])
    if till - age < t["min_term_years"]:
        raise _Refused(
            f"cover must run at least {t['min_term_years']} years; choose a later end age"
        )
    cover = int(a["cover_amount"])
    rate = _first(t["rate_per_thousand"]["bands"], age)
    base = cover / 1000 * rate * t["term_factor"][a["cover_till_age"]]
    if a["smoker"] == "yes":
        base *= t["smoker_factor"]
    if a["gender"] == "female":
        base *= t["female_factor"]
    pct = next(p for threshold, p in t["high_cover_discount_percent"] if cover >= threshold)
    lines = [
        Line("base", "Base premium", rnd(base)),
        Line("high_cover", f"High-cover discount ({pct}%)", -rnd(base * pct / 100)),
    ]
    return lines, {"base": base, "age": age}


def _home(spec: Json, a: dict[str, str]) -> tuple[list[Line], Json]:
    t = spec["tables"]
    building_value = int(a["building_value"])
    if a["ownership"] == "tenant" and building_value:
        raise _Refused("a tenant insures contents only; set the building value to zero")
    zone = t["zone_factor"][_zone(a)]
    building = building_value / 1000 * t["building_rate_per_thousand"][a["property_type"]] * zone
    if int(a["building_age"]) > t["old_building_years"]:
        building *= 1 + t["old_building_loading_percent"] / 100
    contents = int(a["contents_value"]) / 1000 * t["contents_rate_per_thousand"] * zone
    security = (
        (building + contents) * t["security_discount_percent"] / 100
        if a.get("security_system") == "yes"
        else 0
    )
    lines = [
        Line("building", "Building", rnd(building)),
        Line("contents", "Contents", rnd(contents)),
        Line("security", f"Security discount ({t['security_discount_percent']}%)", -rnd(security)),
    ]
    return lines, {"building_value": building_value}


def _travel(spec: Json, a: dict[str, str]) -> tuple[list[Line], Json]:
    t = spec["tables"]
    travellers = int(a["travellers"])
    per = t["per_day_per_traveller"][a["region"]][a.get("plan", "essential")] * int(a["trip_days"])
    base = (
        max(per, t["min_per_traveller"])
        * travellers
        * _first(t["age_loading"], int(a["eldest_age"]))
    )
    group = base * t["group_discount_percent"] / 100 if travellers >= t["group_size"] else 0
    lines = [
        Line("base", "Base premium", rnd(base)),
        Line("group", f"Group discount ({t['group_discount_percent']}%)", -rnd(group)),
    ]
    return lines, {"base": base, "travellers": travellers}


_ENGINES = {
    "car": _car,
    "bike": _bike,
    "health": _health,
    "term": _term,
    "home": _home,
    "travel": _travel,
}


def _unavailable(product: str, addon_id: str, a: dict[str, str], ctx: Json) -> str | None:
    ad = _addon(product, addon_id)
    if "max_age" in ad and ctx.get("age", 0) > ad["max_age"]:
        return f"only for vehicles up to {ad['max_age']} years old"
    if "min_ncb" in ad and ctx.get("ncb_pct", 0) < ad["min_ncb"]:
        return f"needs a No Claim Bonus of at least {ad['min_ncb']}%"
    if (
        product == "health"
        and addon_id == "maternity"
        and (
            a["cover_type"] != "family_floater"
            or int(a["adults"]) != 2
            or int(a["eldest_age"]) > 45
        )
    ):
        return "only on a family floater with two adults, the eldest 45 or younger"
    if product == "home" and addon_id == "rent_loss" and a["ownership"] != "owner":
        return "only for owners"
    if product == "home" and addon_id == "earthquake" and int(a["building_value"]) <= 0:
        return "needs a building value"
    return None


def _addon_price(ad: Json, a: dict[str, str], ctx: Json) -> float:
    p = ad["price"]
    if "flat" in p:
        return p["flat"]
    if "idv_percent" in p:
        return ctx["idv"] * p["idv_percent"] / 100
    if "idv_percent_by_age" in p:
        return ctx["idv"] * _first(p["idv_percent_by_age"], ctx["age"]) / 100
    if "base_percent" in p:
        return ctx["base"] * p["base_percent"] / 100
    if "flat_per_adult" in p:
        return p["flat_per_adult"] * ctx["adults"]
    if "flat_per_traveller" in p:
        return p["flat_per_traveller"] * ctx["travellers"]
    if "flat_by_age" in p:
        return _first(p["flat_by_age"], ctx["age"])
    if "per_thousand_of" in p:
        return int(a[p["per_thousand_of"]]) / 1000 * p["rate"]
    raise ValueError(f"unknown price shape {p}")


# ─── Golden cases ─────────────────────────────────────────────────────────────

CASES: list[tuple[str, dict[str, str], list[str] | None]] = [
    (
        "car",
        {
            "vehicle_class": "suv",
            "fuel": "diesel",
            "registration_year": "2022",
            "ex_showroom": "1450000",
            "city": "pune",
            "claim_free_years": "2",
        },
        ["pa_owner", "zero_dep", "engine_protect", "rsa"],
    ),
    (
        "car",
        {
            "vehicle_class": "hatchback",
            "fuel": "petrol",
            "make_model": "Tarang Vega VX",
            "registration_year": "2023",
            "ex_showroom": "700000",
            "city": "pune",
            "claim_free_years": "1",
            "voluntary_deductible": "5000",
        },
        None,
    ),
    (
        "car",
        {
            "vehicle_class": "sedan",
            "fuel": "electric",
            "registration_year": "2016",
            "ex_showroom": "1800000",
            "city": "jaipur",
            "claim_free_years": "5",
        },
        ["pa_owner", "zero_dep", "ncb_protect", "key_replacement"],
    ),
    ("car", {"vehicle_class": "suv", "fuel": "petrol", "city": "delhi"}, None),
    (
        "bike",
        {
            "bike_type": "scooter",
            "engine_cc": "upto_150",
            "registration_year": "2026",
            "ex_showroom": "95000",
            "city": "pune",
            "claim_free_years": "0",
        },
        ["pa_owner", "zero_dep", "rsa"],
    ),
    (
        "bike",
        {
            "bike_type": "motorcycle",
            "engine_cc": "above_350",
            "fuel": "petrol",
            "registration_year": "2019",
            "ex_showroom": "320000",
            "city": "kochi",
            "claim_free_years": "3",
        },
        None,
    ),
    (
        "health",
        {
            "cover_type": "family_floater",
            "adults": "2",
            "children": "1",
            "eldest_age": "38",
            "sum_insured": "1000000",
            "city": "pune",
            "pre_existing": "yes",
        },
        ["room_rent_waiver"],
    ),
    (
        "health",
        {
            "cover_type": "individual",
            "adults": "1",
            "children": "0",
            "eldest_age": "52",
            "sum_insured": "2500000",
            "city": "lucknow",
            "pre_existing": "no",
            "voluntary_copay": "20",
        },
        ["opd_cover", "critical_illness", "maternity"],
    ),
    (
        "health",
        {
            "cover_type": "individual",
            "adults": "2",
            "eldest_age": "30",
            "sum_insured": "500000",
            "city": "pune",
            "pre_existing": "no",
        },
        None,
    ),
    (
        "term",
        {
            "age": "38",
            "gender": "male",
            "smoker": "no",
            "cover_amount": "15000000",
            "cover_till_age": "65",
        },
        ["accidental_death"],
    ),
    (
        "term",
        {
            "age": "29",
            "gender": "female",
            "smoker": "yes",
            "cover_amount": "10000000",
            "cover_till_age": "70",
        },
        ["critical_illness_rider", "waiver_of_premium"],
    ),
    (
        "term",
        {
            "age": "58",
            "gender": "male",
            "smoker": "no",
            "cover_amount": "5000000",
            "cover_till_age": "65",
        },
        None,
    ),
    (
        "home",
        {
            "ownership": "owner",
            "property_type": "apartment",
            "building_value": "6500000",
            "contents_value": "800000",
            "building_age": "8",
            "city": "pune",
            "security_system": "yes",
        },
        ["earthquake", "electronics"],
    ),
    (
        "home",
        {
            "ownership": "tenant",
            "property_type": "independent_house",
            "building_value": "0",
            "contents_value": "450000",
            "building_age": "30",
            "city": "indore",
        },
        ["rent_loss", "valuables", "earthquake"],
    ),
    (
        "travel",
        {"region": "asia", "trip_days": "9", "travellers": "3", "eldest_age": "38", "plan": "plus"},
        ["trip_cancellation"],
    ),
    (
        "travel",
        {"region": "usa_canada", "trip_days": "21", "travellers": "2", "eldest_age": "64"},
        ["baggage_plus", "adventure_sports"],
    ),
    (
        "travel",
        {"region": "schengen", "trip_days": "4", "travellers": "1", "eldest_age": "25"},
        None,
    ),
]


def golden() -> list[Json]:
    return [
        {"product": p, "answers": ans, "addons": ons, "expected": quote(p, ans, ons).as_json()}
        for p, ans, ons in CASES
    ]


if __name__ == "__main__":
    if "--cases" in sys.argv:
        out = DATA / "quote_cases.json"
        out.write_text(
            json.dumps({"cases": golden()}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"{len(CASES)} cases → {out}")
    else:
        for c in golden():
            print(
                c["product"],
                c["expected"]["total"],
                c["expected"].get("error") or c["expected"]["missing"],
            )
