"""Fashio's data and its shared rules, the brain's half (CONTRACT.md, "Shared rules").

``data/catalog.json`` (the catalogue index built from the Fashion Product Images
Dataset), ``data/store.json`` (our policies, size charts, the fit rule's words,
gift options) and ``data/orders.json`` (the signed-in customer's orders, dated by
offsets from today) are read once at import. Every rule here is implemented a
second time in the page (``frontend/src/data/catalog.ts``, ``fit.ts``,
``gifts.ts``, ``shop.ts``) and the two give the same answer: the search and its
order, the discount, stock, the size advisor's ``recommend``, the gift finder's
``pick_gifts``, IST dates, orders resolved from offsets, the cancel rule, return
eligibility, bag totals and the return reference. Nothing is invented at run time.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, fields
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

DATA = Path(__file__).resolve().parents[1] / "data"


def _load(name: str) -> dict[str, Any]:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


CATALOG: dict[str, Any] = _load("catalog.json")
STORE: dict[str, Any] = _load("store.json")
_ORDERS: dict[str, Any] = _load("orders.json")

PRODUCTS: list[dict[str, Any]] = CATALOG["products"]
BY_ID: dict[int, dict[str, Any]] = {int(p["id"]): p for p in PRODUCTS}
TYPES: dict[str, dict[str, Any]] = CATALOG["types"]
DEPARTMENTS: list[dict[str, Any]] = CATALOG["departments"]
BRANDS: list[str] = CATALOG["brands"]
COLOURS: list[str] = list(CATALOG["colours"])
POLICY: dict[str, Any] = STORE["policies"]
CUSTOMER: dict[str, str] = _ORDERS["customer"]
TZ = ZoneInfo(STORE.get("timezone", "Asia/Kolkata"))

# ─── Products ─────────────────────────────────────────────────────────────────


def product(ref: int | str | None) -> dict[str, Any] | None:
    """The catalogue row for an id (a number or its string), else None."""
    if ref is None:
        return None
    try:
        return BY_ID.get(int(str(ref).strip().lstrip("#")))
    except ValueError:
        return None


def type_label(t: str) -> str:
    return str(TYPES.get(t, {}).get("label", t))


def department(dept_id: str | None) -> dict[str, Any] | None:
    return next((d for d in DEPARTMENTS if d["id"] == dept_id), None)


def discount_pct(p: dict[str, Any]) -> int:
    """round((mrp - price) * 100 / mrp), 0 when there is no markdown."""
    mrp, price = p["mrp"], p["price"]
    return round((mrp - price) * 100 / mrp) if mrp > price else 0


def stock_of(p: dict[str, Any], size: str) -> int:
    return next((int(n) for label, n in p["sizes"] if label == size), 0)


def in_stock(p: dict[str, Any], size: str) -> bool:
    return stock_of(p, size) > 0


def any_stock(p: dict[str, Any]) -> bool:
    return any(n > 0 for _, n in p["sizes"])


def sizes_in_stock(p: dict[str, Any]) -> list[str]:
    return [label for label, n in p["sizes"] if n > 0]


def size_label(p: dict[str, Any], said: str) -> str | None:
    """The product's own size label for what was said ("m" → "M", "7" → "UK 7",
    "onesize"), or None when it has no such size."""
    s = said.strip().upper().replace("XXXL", "3XL", 1).replace("2XL", "XXL", 1)
    for label, _ in p["sizes"]:
        if label.upper() == s:
            return label
    if p["scale"] == "uk":
        n = re.search(r"\d+", s)
        if n:
            return next((lb for lb, _ in p["sizes"] if lb == f"UK {n[0]}"), None)
    if p["scale"] == "one":
        return p["sizes"][0][0] if p["sizes"] else None
    return None


def inr(n: float) -> str:
    """₹1,25,999: Indian grouping."""
    v = round(n)
    sign = "-" if v < 0 else ""
    s = str(abs(v))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return f"₹{sign}{s}"


_GENDER_WORDS = re.compile(
    r"\b(?:men's|women's|mens|womens|men|women|woman|boys|girls|boy's|girl's|unisex|kids)\b\s*",
    re.IGNORECASE,
)


def short_name(p: dict[str, Any]) -> str:
    """The product's name as said aloud: the dataset's name without its gender words."""
    name = _GENDER_WORDS.sub("", p["name"]).strip()
    return re.sub(r"\s{2,}", " ", name) or p["name"]


# ─── Search ───────────────────────────────────────────────────────────────────

Sort = Literal["popular", "price_asc", "price_desc", "discount", "new"]
_DEPT_GENDERS: dict[str, tuple[str, ...]] = {
    "men": ("men", "unisex"),
    "women": ("women", "unisex"),
    "kids": ("boys", "girls"),
    "boys": ("boys",),
    "girls": ("girls",),
}


def _dept_types(dept_id: str) -> set[str]:
    d = department(dept_id)
    return {t for s in (d or {}).get("sections", []) for t in s["types"]}


@dataclass
class Search:
    """The listing's search: what the shopper asked for, which is what the screen shows."""

    dept: str | None = None
    types: list[str] = field(default_factory=list)
    brands: list[str] = field(default_factory=list)
    colours: list[str] = field(default_factory=list)
    sizes: list[str] = field(default_factory=list)
    price_min: int | None = None
    price_max: int | None = None
    discount_min: int | None = None
    usage: list[str] = field(default_factory=list)
    seasons: list[str] = field(default_factory=list)
    query: str | None = None
    sort: str | None = None

    @classmethod
    def of(cls, data: dict[str, Any]) -> Search:
        """From a ``shop.changed`` event or a ``shop.filter`` args dict."""

        def strs(v: Any) -> list[str]:
            return [str(i) for i in v or []]

        def num(v: Any) -> int | None:
            return None if v is None or v == "" else int(v)

        dept = data.get("dept") or None
        sort = data.get("sort") or None
        return cls(
            dept=None if dept == "all" else str(dept) if dept else None,
            types=strs(data.get("types")),
            brands=strs(data.get("brands")),
            colours=strs(data.get("colours")),
            sizes=strs(data.get("sizes")),
            price_min=num(data.get("price_min")),
            price_max=num(data.get("price_max")),
            discount_min=num(data.get("discount_min")),
            usage=strs(data.get("usage")),
            seasons=strs(data.get("seasons")),
            query=str(data.get("query")) if data.get("query") else None,
            sort=None if sort == "popular" else str(sort) if sort else None,
        )

    def args(self) -> dict[str, Any]:
        """As ``shop.filter`` takes it: the whole search, unset fields null."""
        return {
            f.name: (list(v) or None) if isinstance(v := getattr(self, f.name), list) else v
            for f in fields(self)
        }

    def empty(self) -> bool:
        return all(v in (None, []) for v in (getattr(self, f.name) for f in fields(self)))

    def summary(self) -> str:
        return summarise(self)


def matches(p: dict[str, Any], s: Search) -> bool:
    if s.dept and s.dept != "all":
        genders = _DEPT_GENDERS.get(s.dept)
        if genders and p["gender"] not in genders:
            return False
        if s.dept == "ethnic" and p["usage"] != "Ethnic":
            return False
        if s.dept in ("footwear", "accessories") and p["type"] not in _dept_types(s.dept):
            return False
    if s.types and p["type"] not in s.types:
        return False
    if s.brands and p["brand"].lower() not in {b.lower() for b in s.brands}:
        return False
    if s.colours and p["colour"].lower() not in {c.lower() for c in s.colours}:
        return False
    if s.sizes and not any(n > 0 and label in s.sizes for label, n in p["sizes"]):
        return False
    if s.price_min is not None and p["price"] < s.price_min:
        return False
    if s.price_max is not None and p["price"] > s.price_max:
        return False
    if s.discount_min is not None and discount_pct(p) < s.discount_min:
        return False
    if s.usage and p["usage"] not in s.usage:
        return False
    if s.seasons and p["season"] not in s.seasons:
        return False
    if s.query:
        hay = f"{p['name']} {p['brand']} {p['colour']} {type_label(p['type'])}".lower()
        words = [w for w in re.split(r"[\W_]+", s.query.lower()) if len(w) >= 2]
        if not all(w in hay for w in words):
            return False
    return True


def sort_products(xs: list[dict[str, Any]], sort: str | None = "popular") -> list[dict[str, Any]]:
    keys: dict[str, Any] = {
        "price_asc": lambda p: (p["price"], p["rank"]),
        "price_desc": lambda p: (-p["price"], p["rank"]),
        "discount": lambda p: (-discount_pct(p), p["rank"]),
        "new": lambda p: (-p["year"], p["rank"]),
    }
    return sorted(xs, key=keys.get(sort or "popular", lambda p: p["rank"]))


def search(s: Search, products: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    return sort_products([p for p in (products or PRODUCTS) if matches(p, s)], s.sort)


_SORT_LABEL = {
    "popular": "popular first",
    "price_asc": "price low to high",
    "price_desc": "price high to low",
    "discount": "biggest discount first",
    "new": "newest first",
}


def summarise(s: Search) -> str:
    """One line saying the search (the page's ``summarise``, word for word)."""
    parts: list[str] = []
    if s.dept and s.dept != "all":
        parts.append(str((department(s.dept) or {}).get("label", s.dept)))
    if s.types:
        parts.append(" or ".join(type_label(t) for t in s.types))
    if s.colours:
        parts.append(" or ".join(s.colours))
    if s.brands:
        parts.append(f"by {' or '.join(s.brands)}")
    if s.sizes:
        parts.append(f"size {' or '.join(s.sizes)} in stock")
    if s.usage:
        parts.append(" or ".join(s.usage))
    if s.seasons:
        parts.append(" or ".join(s.seasons))
    if s.price_min is not None and s.price_max is not None:
        parts.append(f"{inr(s.price_min)} to {inr(s.price_max)}")
    elif s.price_max is not None:
        parts.append(f"under {inr(s.price_max)}")
    elif s.price_min is not None:
        parts.append(f"over {inr(s.price_min)}")
    if s.discount_min is not None:
        parts.append(f"{s.discount_min}% off or more")
    if s.query:
        parts.append(f'"{s.query}"')
    what = ", ".join(parts) if parts else "everything"
    return f"{what}; {_SORT_LABEL[s.sort]}" if s.sort and s.sort != "popular" else what


def match_type(said: str) -> str | None:
    """A type id for a type id or label as said ("kurta", "T-shirts", "heels")."""
    t = said.strip().lower()
    if t in TYPES:
        return t
    norm = re.sub(r"[^a-z0-9]", "", t)
    for tid, info in TYPES.items():
        label = re.sub(r"[^a-z0-9]", "", str(info["label"]).lower())
        art = re.sub(r"[^a-z0-9]", "", str(info["article"]).lower())
        bare = re.sub(r"[^a-z0-9]", "", tid)
        if norm in (label, art, bare) or norm + "s" in (label, art, bare):
            return tid
        if norm.endswith("es") and norm[:-2] in (label, art, bare):
            return tid
    return None


def match_brand(said: str) -> str | None:
    s = said.strip().lower()
    return next((b for b in BRANDS if b.lower() == s), None)


def match_colour(said: str) -> str | None:
    s = re.sub(r"\s+", " ", said.strip().lower())
    return next((c for c in COLOURS if c.lower() == s), None)


# ─── Fit (Find my size) ───────────────────────────────────────────────────────

ALPHA = ["XS", "S", "M", "L", "XL", "XXL", "3XL", "4XL"]
WAIST: dict[str, dict[str, int]] = {
    "women": {"XS": 26, "S": 28, "M": 30, "L": 32, "XL": 34, "XXL": 36, "3XL": 38},
    "men": {"XS": 28, "S": 30, "M": 32, "L": 34, "XL": 36, "XXL": 38, "3XL": 40},
}
FIT = STORE["fit"]
Why = Literal["same", "slim_up", "loose_down", "tall_up"]
Cut = Literal["slim", "loose", "regular"]


@dataclass(frozen=True)
class FitAnswer:
    size: str
    """The size to buy, in stock."""
    wanted: str | None
    """The size the rule chose, when it is out of stock and ``size`` replaces it."""
    steps: int
    why: Why
    cut: Cut
    base: str


def _order(scale: str, label: str) -> float:
    if scale == "alpha":
        return ALPHA.index(label) if label in ALPHA else -1
    if scale == "waist":
        return float(label) if label.isdigit() else 0
    if scale == "uk":
        digits = re.sub(r"\D+", "", label)
        return float(digits) if digits else 0
    if scale == "age":
        m = re.match(r"^(\d+)(?:-(\d+))?([YM])$", label)
        if not m:
            return 99
        n = float(m[2] or m[1])
        return n / 12 if m[3] == "M" else n
    return 0


def base_size(p: dict[str, Any], usual: str) -> str | None:
    """The shopper's usual size in the product's scale, or None when it does not convert."""
    u = re.sub(r"^UK\s*", "UK ", usual.strip().upper())
    u = u.replace("XXXL", "3XL", 1).replace("2XL", "XXL", 1)
    side = "women" if p["gender"] in ("women", "girls") else "men"
    scale = p["scale"]
    if scale == "uk":
        n = re.search(r"(\d+)", u)
        return f"UK {n[1]}" if n else None
    if scale == "alpha":
        if u in ALPHA:
            return u
        if u.isdigit():
            return next((k for k, w in WAIST[side].items() if w == int(u)), None)
        return None
    if scale == "waist":
        if u.isdigit():
            return u
        w = WAIST[side].get(u)
        return str(w) if w else None
    if scale == "age":
        return u if re.match(r"^\d+(-\d+)?[YM]$", u) else None
    return None


def cut_of(p: dict[str, Any]) -> Cut:
    fit = str((p.get("attrs") or {}).get("Fit", "")).lower()
    if any(w in fit for w in FIT["slim_words"]):
        return "slim"
    if any(w in fit for w in FIT["loose_words"]):
        return "loose"
    return "regular"


def recommend(
    p: dict[str, Any],
    usual_size: str | None,
    fit: str | None = None,
    height_cm: int | None = None,
) -> FitAnswer | None:
    """The size advisor's rule (CONTRACT.md, "Fit"); None for a one-size product,
    with no usual size, or when the usual size does not convert."""
    if p["scale"] == "one" or not usual_size:
        return None
    base = base_size(p, usual_size)
    if not base:
        return None
    pref = fit or "regular"
    cut = cut_of(p)
    steps, why = 0, "same"
    if pref == "relaxed" and cut == "slim":
        steps, why = 1, "slim_up"
    elif pref == "snug" and cut == "loose":
        steps, why = -1, "loose_down"
    elif (
        (height_cm or 0) >= FIT["tall_cm"]
        and p["type"] in FIT["length_types"]
        and p["scale"] in ("alpha", "waist")
    ):
        steps, why = 1, "tall_up"
    labels = [label for label, _ in p["sizes"]]
    scale = p["scale"]
    b = _order(scale, base)
    at = labels.index(base) if base in labels else -1
    if at < 0:
        best = float("inf")
        for i, label in enumerate(labels):
            d = abs(_order(scale, label) - b)
            if d < best or (
                d == best and at >= 0 and _order(scale, label) > _order(scale, labels[at])
            ):
                best, at = d, i
    wanted_at = min(max(at + steps, 0), len(labels) - 1)
    wanted = labels[wanted_at]

    def stock(i: int) -> int:
        return int(p["sizes"][i][1]) if 0 <= i < len(labels) else 0

    w: Why = why  # pyright: ignore[reportAssignmentType]
    if stock(wanted_at) > 0:
        return FitAnswer(wanted, None, steps, w, cut, base)
    pick = -1
    for d in range(1, len(labels)):
        if stock(wanted_at + d) > 0:
            pick = wanted_at + d
        elif stock(wanted_at - d) > 0:
            pick = wanted_at - d
        if pick >= 0:
            break
    if pick < 0:
        return None
    return FitAnswer(labels[pick], wanted, steps, w, cut, base)


def nearest_in_stock(p: dict[str, Any], size: str) -> str | None:
    """The nearest in-stock size to ``size`` by position in the product's size list;
    a tie goes to the larger (the fit rule's step 5)."""
    labels = [label for label, _ in p["sizes"]]
    if size not in labels:
        return None
    at = labels.index(size)
    for d in range(1, len(labels)):
        for i in (at + d, at - d):
            if 0 <= i < len(labels) and p["sizes"][i][1] > 0:
                return labels[i]
    return None


def chart_of(p: dict[str, Any]) -> dict[str, Any] | None:
    """The product's size chart from store.json, by its type and gender."""
    chart = (TYPES.get(p["type"]) or {}).get("chart") or {}
    cid = chart.get(p["gender"])
    return STORE["size_charts"].get(cid) if cid else None


def chart_row(p: dict[str, Any], size: str) -> list[str] | None:
    chart = chart_of(p)
    if chart is None:
        return None
    return next((r for r in chart["rows"] if r[0] == size), None)


def length_type(p: dict[str, Any]) -> bool:
    return p["type"] in FIT["length_types"] and p["scale"] in ("alpha", "waist")


# ─── Gifts ────────────────────────────────────────────────────────────────────

GIFTS: dict[str, Any] = STORE["gifts"]
_SIDE_GENDERS: dict[str, tuple[str, ...]] = {
    "women": ("women", "unisex"),
    "men": ("men", "unisex"),
    "kids": ("boys", "girls"),
}


@dataclass
class GiftBrief:
    recipient: str | None = None
    occasion: str | None = None
    budget_max: int | None = None
    """Rupees; 0: no limit; None: not said yet."""
    size: str | None = None
    colours: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    material: str | None = None


def recipient_of(said: str | None) -> str | None:
    """The gift finder's recipient for what was said ("sister" → Sister)."""
    if not said:
        return None
    s = said.strip().lower()
    aliases = {
        "wife": "Partner",
        "husband": "Partner",
        "girlfriend": "Partner",
        "boyfriend": "Partner",
        "mother": "Mom",
        "mum": "Mom",
        "father": "Dad",
        "son": "Kid",
        "daughter": "Kid",
        "child": "Kid",
        "kids": "Kid",
    }
    if s in aliases:
        return aliases[s]
    return next((r for r in GIFTS["recipients"] if r.lower() == s), None)


def occasion_of(said: str | None) -> str | None:
    if not said:
        return None
    s = re.sub(r"[^a-z ]", "", said.strip().lower())
    aliases = {"rakhi": "Raksha Bandhan", "bday": "Birthday", "marriage": "Wedding"}
    if s in aliases:
        return aliases[s]
    return next((o for o in GIFTS["occasions"] if o.lower() == s), None)


def side_of(recipient: str | None) -> str | None:
    if not recipient:
        return None
    key = next((k for k in GIFTS["recipient_gender"] if k.lower() == recipient.lower()), None)
    return GIFTS["recipient_gender"][key] if key else None


def _gift_words(p: dict[str, Any]) -> str:
    return f"{p['name']} {' '.join(str(v) for v in (p.get('attrs') or {}).values())}".lower()


def festive(occasion: str | None) -> bool:
    return bool(occasion) and occasion in GIFTS["festive_occasions"]


def gift_score(p: dict[str, Any], b: GiftBrief) -> int:
    s = 0
    if any(c.lower() == p["colour"].lower() for c in b.colours):
        s += 3
    words = _gift_words(p)
    if any(x and x.lower() in words for x in [*b.patterns, *([b.material] if b.material else [])]):
        s += 2
    if festive(b.occasion) and p["usage"] == "Ethnic":
        s += 2
    return s


def pick_gifts(b: GiftBrief, n: int = 6) -> list[dict[str, Any]]:
    """The gift shortlist (CONTRACT.md, "Gifts"): the best per type, at most one per
    type, ``n`` in all, best first."""
    side = side_of(b.recipient)
    types = GIFTS["ideas"].get(side or "any", [])
    genders = _SIDE_GENDERS.get(side) if side else None
    pool: list[dict[str, Any]] = []
    for p in PRODUCTS:
        if p["type"] not in types:
            continue
        if genders and p["gender"] not in genders:
            continue
        if b.budget_max and p["price"] > b.budget_max:
            continue
        if p["scale"] == "one":
            if not any_stock(p):
                continue
        elif not (b.size and any(k > 0 and lb.upper() == b.size.upper() for lb, k in p["sizes"])):
            continue
        pool.append(p)
    pool.sort(key=lambda p: (-gift_score(p, b), p["rank"]))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for p in pool:
        if p["type"] in seen:
            continue
        seen.add(p["type"])
        out.append(p)
        if len(out) >= n:
            break
    return out


# ─── Dates (IST) ──────────────────────────────────────────────────────────────

#: Tests fix "today" here (``set_today``); None: the date in Asia/Kolkata now.
_today: date | None = None


def set_today(d: date | None) -> None:
    """Fix today's date (tests); None goes back to the clock."""
    global _today
    _today = d


def today() -> date:
    return _today if _today is not None else datetime.now(TZ).date()


def add_days(d: date, n: int) -> date:
    return d + timedelta(days=n)


def days_between(a: date, b: date) -> int:
    return (b - a).days


_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def fmt_date(d: date) -> str:
    """27 Nov 2026"""
    return f"{d.day} {_MONTHS[d.month - 1]} {d.year}"


def spoken_day(d: date) -> str:
    """Friday, 27 November"""
    return f"{d.strftime('%A')}, {d.day} {d.strftime('%B')}"


# ─── Orders ───────────────────────────────────────────────────────────────────


def resolve_orders(on: date | None = None) -> list[dict[str, Any]]:
    """The sample orders, dated from today (IST): ``placed``, ``eta``, ``delivered``
    and each event's ``date`` become dates."""
    t = on or today()
    out: list[dict[str, Any]] = []
    for raw in _ORDERS["orders"]:
        o = dict(raw)
        o["placed"] = add_days(t, raw["placed"])
        o["eta"] = add_days(t, raw["eta"]) if raw.get("eta") is not None else None
        o["delivered"] = add_days(t, raw["delivered"]) if raw.get("delivered") is not None else None
        o["events"] = [
            {
                "date": add_days(t, e["day"]),
                "time": e["time"],
                "status": e["status"],
                "text": e["text"],
            }
            for e in raw["events"]
        ]
        out.append(o)
    return out


def order_ids() -> list[str]:
    return [o["id"] for o in _ORDERS["orders"]]


def status_label(s: str) -> str:
    return str(STORE["statuses"].get(s, s))


def can_cancel(status: str) -> bool:
    return status in POLICY["cancel_statuses"]


def order_total(o: dict[str, Any]) -> int:
    return sum(int(i["price"]) * int(i["qty"]) for i in o["items"])


Refusal = Literal["not_delivered", "window", "fragrance", "already"]


@dataclass(frozen=True)
class ReturnCheck:
    ok: bool
    why: Refusal | None = None
    days_left: int | None = None
    delivered: date | None = None
    closed_on: date | None = None


def return_check(
    o: dict[str, Any],
    product_id: int | None,
    returned: set[str],
    on: date | None = None,
    status: str | None = None,
) -> ReturnCheck:
    """Whether ``product_id`` of order ``o`` can be returned today (CONTRACT.md,
    Returns). ``status`` overrides the data's (an order changed in this browser)."""
    t = on or today()
    delivered: date | None = o.get("delivered")
    if (status or o["status"]) != "delivered" or delivered is None:
        return ReturnCheck(False, "not_delivered")
    window = int(POLICY["returns"]["window_days"])
    left = window - days_between(delivered, t)
    closed = add_days(delivered, window)
    if left < 0:
        return ReturnCheck(False, "window", None, delivered, closed)
    if product_id is not None:
        p = product(product_id)
        if p and p["type"] in POLICY["returns"]["not_returnable_types"]:
            return ReturnCheck(False, "fragrance", left, delivered, closed)
        if f"{o['id']}|{product_id}" in returned:
            return ReturnCheck(False, "already", left, delivered, closed)
    return ReturnCheck(True, None, left, delivered, closed)


def return_ref(order_id: str, product_id: int) -> str:
    return f"RTN-{re.sub(r'\D', '', order_id)}-{product_id}"


# ─── Bag ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BagTotals:
    count: int
    subtotal: int
    mrp: int
    delivery: int
    wrap: int
    total: int


def bag_totals(lines: list[tuple[int, str, int, bool]]) -> BagTotals:
    """Lines as (product id, size, qty, gift)."""
    subtotal = mrp = count = wrap = 0
    for pid, _size, qty, gift in lines:
        p = product(pid)
        if p is None:
            continue
        subtotal += p["price"] * qty
        mrp += p["mrp"] * qty
        count += qty
        if gift:
            wrap += int(POLICY["gift_wrap"]["price"]) * qty
    d = POLICY["delivery"]
    delivery = 0 if count == 0 or subtotal >= d["free_over"] else int(d["fee"])
    return BagTotals(count, subtotal, mrp, delivery, wrap, subtotal + delivery + wrap)


def parse_bag_line(line: str) -> tuple[int, str, int, bool] | None:
    """A ``bag.changed`` line, "<product id>|<size>|<qty>|<gift: 0 or 1>"."""
    parts = str(line).split("|")
    if len(parts) < 2:
        return None
    try:
        pid = int(parts[0])
        qty = int(parts[2]) if len(parts) > 2 and parts[2] else 1
    except ValueError:
        return None
    gift = len(parts) > 3 and parts[3] in ("1", "true", "True")
    return pid, parts[1], qty, gift


def catalogue_summary() -> str:
    """The departments, their types and the biggest brands, for the prompt."""
    lines: list[str] = []
    for d in DEPARTMENTS:
        secs = "; ".join(
            f"{s['label']}: {', '.join(f'{type_label(t)} ({t})' for t in s['types'])}"
            for s in d["sections"]
        )
        lines.append(f"- {d['label']} (dept {d['id']}): {secs}.")
    counts: dict[str, int] = {}
    for p in PRODUCTS:
        counts[p["brand"]] = counts.get(p["brand"], 0) + 1
    top = sorted(counts, key=lambda b: -counts[b])[:40]
    lines.append(
        f"- Brands with the most products: {', '.join(top)} ({len(BRANDS)} brands in all)."
    )
    lines.append(f"- Colours: {', '.join(c for c in COLOURS if c != 'NA')}.")
    prices = sorted(p["price"] for p in PRODUCTS)
    lines.append(
        f"- {len(PRODUCTS)} products from {inr(prices[0])} to {inr(prices[-1])}; occasions "
        "(usage): Casual, Ethnic, Formal, Sports, Party, Smart Casual, Travel."
    )
    return "\n".join(lines)
