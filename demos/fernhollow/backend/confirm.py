"""Every confirmation Emily asks for, handled one way.

Placing an order, submitting a return, adding to the cart — and any confirmed
action added later — go through the same four steps:

1. **Ask.** A tool that needs the shopper's yes records one pending
   confirmation: what it is (``kind``), what exactly (``key``: the action and
   its arguments), and the turn it was asked on. There is one at a time; a new
   ask replaces the old one.
2. **Answer.** The shopper's next words are classified before the model runs:
   a plain yes acts, a plain no clears, anything else is left to the model.
   A yes on the same turn the question was asked is not an answer.
3. **Act, once.** The act says one line as it is sent. An act whose key has
   already been applied this session is not sent again; it says so instead,
   so a duplicate still produces words.
4. **Outcome, once.** An act the page answers (a Stage move) gets one outcome
   line when its result arrives: applied, refused with the page's reason, or
   unknown — never "done" before the page says so, and never twice.

Nothing here knows what an order or a return is: the brain registers what each
kind does when it is acted on.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

__all__ = ["NO", "YES", "Acted", "Confirmations", "Pending", "classify"]

#: A plain yes, as people say one to "Shall I …?".
YES = re.compile(
    r"^\s*(yes|yeah|yep|yup|ya|sure|ok|okay|alright|all right|go ahead|go for it|do it|please do"
    r"|that's right|correct|absolutely|definitely|of course"
    r"|(?:(?:can|could|would) you\s+)?(?:please\s+)?(?:go ahead and\s+)?"
    r"(?:submit|place|send|add|confirm) (?:it|that|them|the \w+))\b",
    re.IGNORECASE,
)
#: Words that turn a yes into something else ("yes but…", "no, wait").
_HEDGE = re.compile(r"\b(no|not|don't|do not|wait|hold on|actually|change|but)\b", re.IGNORECASE)
#: A plain no.
NO = re.compile(
    r"^\s*(no|nope|nah|not yet|not now|don't|do not|cancel|stop|hold on|wait)\b", re.IGNORECASE
)


def classify(text: str) -> str | None:
    """``"yes"``, ``"no"``, or ``None`` for anything that is not a plain answer."""
    if YES.match(text) and not _HEDGE.search(text):
        return "yes"
    if NO.match(text):
        return "no"
    return None


@dataclass
class Pending:
    kind: str
    key: tuple[Any, ...]
    label: str
    asked_turn: int
    data: dict[str, Any] = field(default_factory=dict[str, Any])


@dataclass
class Acted:
    """What acting on a confirmation did."""

    line: str
    """Said the moment it is sent."""
    note: str
    """What the model is told."""
    ref: str | None = None
    """A page move whose result is the outcome; ``None`` when the act is
    complete as sent (its line is the outcome)."""
    on_applied: Callable[[str | None], str] | None = None
    """The outcome line for an applied result, given the page's own answer."""


@dataclass
class _Flight:
    key: tuple[Any, ...]
    on_applied: Callable[[str | None], str] | None


class Confirmations:
    """The one pending confirmation, what has been done, and what is in flight."""

    def __init__(self) -> None:
        self.pending: Pending | None = None
        self.done: dict[tuple[Any, ...], str] = {}
        self._flights: dict[str, _Flight] = {}
        self._acts: dict[str, Callable[[Pending], Acted]] = {}

    def register(self, kind: str, act: Callable[[Pending], Acted]) -> None:
        self._acts[kind] = act

    # ── ask ──────────────────────────────────────────────────────────────

    def already(self, key: tuple[Any, ...]) -> str | None:
        """The words for a duplicate: done, or on its way."""
        if key in self.done:
            said = re.sub(r"^(Done|It's done)\s*[—.,-]\s*", "", self.done[key])
            return f"That's already done — {said[:1].lower()}{said[1:]}"
        if any(f.key == key for f in self._flights.values()):
            return "That's already on its way through."
        return None

    def already_kind(self, kind: str) -> str | None:
        """The duplicate words for the latest act of ``kind`` done or in flight."""
        keys = [f.key for f in self._flights.values()] + list(self.done)
        for key in reversed(keys):
            if key[0] == kind:
                return self.already(key)
        return None

    def ask(
        self, kind: str, key: tuple[Any, ...], label: str, turn: int, **data: Any
    ) -> str | None:
        """Record the question. Returns the duplicate line instead when this
        exact act was already done or is in flight."""
        dup = self.already(key)
        if dup is not None:
            return dup
        self.pending = Pending(kind, key, label, turn, dict(data))
        return None

    def due(self, turn: int, kind: str | None = None) -> Pending | None:
        """The pending confirmation, if it was asked before ``turn``."""
        p = self.pending
        if p is None or p.asked_turn >= turn or (kind is not None and p.kind != kind):
            return None
        return p

    def clear(self) -> Pending | None:
        p, self.pending = self.pending, None
        return p

    # ── act ──────────────────────────────────────────────────────────────

    def act(self, pending: Pending) -> Acted:
        """Act on ``pending`` — once. A duplicate says so and sends nothing."""
        if self.pending is pending:
            self.pending = None
        dup = self.already(pending.key)
        if dup is not None:
            return Acted(dup, f"[Already done, not sent again: {pending.label}.]")
        acted = self._acts[pending.kind](pending)
        if acted.ref is None:
            self.done[pending.key] = acted.line
        else:
            self._flights[acted.ref] = _Flight(pending.key, acted.on_applied)
        return acted

    # ── outcome ──────────────────────────────────────────────────────────

    def is_flight(self, ref: str) -> bool:
        return ref in self._flights

    def outcome(
        self, ref: str, outcome: str, detail: str | None, reason: str | None
    ) -> Callable[[], str]:
        """The one line for the page's answer to an act in flight — rendered
        when it is said, so an answer the page completes a moment later (a
        reference in a following state event) is in it."""
        flight = self._flights.pop(ref)
        if outcome in ("applied", "partial"):
            self.done[flight.key] = "it went through."

            def applied() -> str:
                line = flight.on_applied(detail) if flight.on_applied else (detail or "Done.")
                self.done[flight.key] = line
                return line

            return applied
        if outcome == "unknown":
            return lambda: (
                "I can't confirm that went through — the page didn't answer. "
                "Please check it on screen."
            )
        why = "; ".join(x for x in (detail, reason) if x) or outcome
        return lambda: f"That didn't go through — the page says: {why}."
