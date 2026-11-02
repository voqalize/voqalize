"""Fernhollow's store policies, read from the authored ``content/policies.json``.

The same file the store's policy pages are written from, so what Emily says and
what the page shows cannot drift. Nothing here adds a fact: a topic is its
authored sentences, in the file's order, and the page it lives on.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from .catalog import POLICIES_PATH

__all__ = ["POLICIES", "Topic", "policy_numbers", "policy_page", "policy_text"]

Topic = Literal["returns", "delivery", "assembly", "care"]
TOPICS: tuple[Topic, ...] = ("returns", "delivery", "assembly", "care")

POLICIES: dict[str, dict[str, Any]] = json.loads(POLICIES_PATH.read_text())

_SKIP = {"page", "currency"}


def policy_text(topic: Topic) -> list[str]:
    """The topic's authored sentences — every text field but the page link."""
    entry = POLICIES.get(topic, {})
    out: list[str] = []
    for key, value in entry.items():
        if key in _SKIP or not isinstance(value, str):
            continue
        label = "" if key in ("summary", "general") else f"{_label(key)}: "
        text = value.strip()
        out.append(f"{label}{text}" + ("" if text.endswith((".", "!", "?")) else "."))
    return out


def policy_page(topic: Topic) -> str:
    return str(POLICIES.get(topic, {}).get("page") or f"policy/{topic}")


def policy_numbers() -> set[float]:
    """Every number the policies state — the only ones Emily may say about them."""
    out: set[float] = set()
    for entry in POLICIES.values():
        for value in entry.values():
            if isinstance(value, int | float) and not isinstance(value, bool):
                out.add(float(value))
            elif isinstance(value, str):
                out |= {float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", value)}
    return out


def _label(key: str) -> str:
    if key == "diy":
        return "Self-assembly"
    spaced = "".join(" " + c.lower() if c.isupper() else c for c in key)
    return spaced[:1].upper() + spaced[1:]
