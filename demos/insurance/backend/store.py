"""The demo's data, read once: the customer, their policy documents, the
network, the claim form and the authored content. Every fact Ananya states
comes from here or from :mod:`.rating`."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CONTENT = ROOT / "content"

Json = dict[str, Any]


def _load(path: Path, fallback: Any = None) -> Any:
    if not path.exists() and fallback is not None:
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


CUSTOMER: Json = _load(DATA / "customer.json")
POLICIES: dict[str, Json] = {
    pid: _load(DATA / "policies" / f"{pid}.json") for pid in CUSTOMER["policies"]
}
NETWORK: Json = _load(DATA / "network.json")
CLAIM_FORM: Json = _load(DATA / "claim_form.json")


def _copy() -> dict[str, Json]:
    raw: Any = _load(CONTENT / "products.json", {})
    if isinstance(raw, dict) and "products" in raw:
        raw = raw["products"]
    if isinstance(raw, list):
        return {str(p["id"]): p for p in raw}
    return {str(k): v for k, v in raw.items() if isinstance(v, dict)}


PRODUCT_COPY: dict[str, Json] = _copy()
CLAIMS_GUIDE: Json = _load(CONTENT / "claims_guide.json", {})

FIRST_NAME: str = CUSTOMER.get("first_name") or CUSTOMER["name"].split()[0]
PRODUCT_IDS = ("car", "bike", "health", "term", "home", "travel")


def clauses(policy_id: str) -> list[tuple[Json, Json]]:
    """(section, clause) for every clause of a policy, in document order."""
    doc = POLICIES[policy_id]
    return [(s, c) for s in doc["sections"] for c in s.get("clauses", [])]


def clause(policy_id: str, clause_id: str) -> tuple[Json, Json] | None:
    for s, c in clauses(policy_id):
        if c["id"] == clause_id:
            return s, c
    return None


def policies_for(products: list[str]) -> list[Json]:
    return [p for p in POLICIES.values() if p["product"] in products]


def member_ids(policy_id: str | None) -> list[str]:
    if policy_id and policy_id in POLICIES:
        return [m["id"] for m in POLICIES[policy_id].get("insured", []) if m.get("id")]
    return [m["id"] for m in CUSTOMER.get("family", [])]


def member_name(member_id: str) -> str:
    for m in CUSTOMER.get("family", []):
        if m["id"] == member_id:
            return m["name"]
    return member_id


def pages() -> list[str]:
    """Every page ``site.go`` may take the visitor to."""
    out = ["home", "quote", "my-policies", "claim"]
    out += [f"quote/{p}" for p in PRODUCT_IDS]
    out += [f"insurance/{p}" for p in PRODUCT_IDS]
    out += [f"my-policies/{pid}" for pid in POLICIES]
    return out


def mode_of(path: str) -> str:
    """The job a page belongs to: home | quote | policies | claim."""
    p = re.sub(r"^.*?/demos/insurance", "", path or "").strip("/")
    if p.startswith(("quote", "insurance")):
        return "quote"
    if p.startswith("my-policies"):
        return "policies"
    if p.startswith("claim"):
        return "claim"
    return "home"


def route_of(path: str) -> str:
    """A path without the origin and the demo's base: ``quote/car``."""
    return re.sub(r"^.*?/demos/insurance", "", path or "").strip("/") or "home"
