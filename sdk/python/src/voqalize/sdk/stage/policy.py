"""What a move's class decides, written down once.

Every move an agent can make on a screen has a class, and the class — not the
move's author — decides how it is delivered, when it fires, how it is checked
and what the model hears about it. A move picks its class; it inherits the rest.

``commit`` is not a class a move can have. It is the answer for anything only
the person in front of the screen may do — pay, submit personal data, consent —
and a move that would need it is refused rather than declared.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Literal

__all__ = ["POLICY", "Delivery", "MoveClass", "Policy", "cueable"]


class MoveClass(StrEnum):
    """How much a move changes, from nothing to something the person owns."""

    LOOK = "look"
    """Changes only what is in view: scroll to, ring, open a tab or a question."""
    NAVIGATE = "navigate"
    """Opens another page or item."""
    REVERSIBLE = "reversible"
    """Changes the page's state, and can be undone: filter, sort, search, pick."""
    CONFIRMED = "confirmed"
    """Changes something the person owns, after they said yes: add to cart, fill, book."""


Delivery = Literal["cue", "tool"]
"""A cue is written inside the reply and fires as its words are spoken; a tool
is called after the reply's words and acts when it is called."""


@dataclass(frozen=True, slots=True)
class Policy:
    deliveries: tuple[Delivery, ...]
    """How a move of this class may reach the page, the first being the default."""
    retries: int
    """How many times a failed move is sent again on its own."""
    needs_effect: bool
    """Whether the move must say how to check it worked."""
    needs_undo: bool
    """Whether the move must say how it is undone."""
    tells_model: Literal["on_failure", "always", "talk_through"]
    """What reaches the model after it fires: nothing unless it failed, one line
    naming the act, or a turn of its own to say what happened."""
    serial: bool
    """Whether it waits for the move before it to finish."""


POLICY: MappingProxyType[MoveClass, Policy] = MappingProxyType(
    {
        MoveClass.LOOK: Policy(("cue", "tool"), 0, False, False, "on_failure", False),
        MoveClass.NAVIGATE: Policy(("cue", "tool"), 1, False, False, "always", True),
        MoveClass.REVERSIBLE: Policy(("cue", "tool"), 1, True, True, "always", True),
        MoveClass.CONFIRMED: Policy(("tool",), 0, True, False, "talk_through", True),
    }
)

assert set(POLICY) == set(MoveClass), "every class has a row"


def cueable(cls: MoveClass) -> bool:
    """Whether a move of this class may be written inside a reply."""
    return "cue" in POLICY[cls].deliveries
