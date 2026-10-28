"""The moves a brain knows, checked once when they are declared.

A :class:`Move` is something the agent can do on the page. One with a ``verb``
may be written inside a reply as a cue — ``{show: Rooms}`` — and fires as the
voice reaches its words; one without is made only when a tool sends it. Its
class (:class:`~voqalize.sdk.stage.MoveClass`) decides the rest.

Everything a reply could get wrong about a verb is refused here, at import
time, rather than in the middle of a call: a verb is one short lowercase word,
it is never a word that names a function call (a reply that opens ``{name: …``
is a call the model wrote out as text, not a move), and only a class that may
be cued has one.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from ..voice import _CALL_KEYS
from .policy import MoveClass, cueable

__all__ = ["MAX_ARGS", "Move", "MoveSet"]

#: The most arguments a move takes; a cue carries at most this many.
MAX_ARGS = 4

_VERB = re.compile(r"[a-z]{2,12}")


@dataclass(frozen=True, slots=True)
class Move:
    """One move the brain knows.

    ``id`` names it on the wire (``core.show``); ``verb`` is the word the model
    writes for it in a reply, or ``None`` for a move only a tool makes; ``args``
    names its arguments, in the order a cue gives them; ``say`` is the line the
    prompt teaches it with. Raises :class:`ValueError` when any of it breaks a
    rule, so a bad move fails where it is written.
    """

    id: str
    verb: str | None
    cls: MoveClass
    args: tuple[str, ...] = ()
    say: str = ""

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("a move needs an id")
        if len(self.args) > MAX_ARGS:
            raise ValueError(
                f"move {self.id!r} takes {len(self.args)} arguments; at most {MAX_ARGS}"
            )
        if self.verb is None:
            return
        if _VERB.fullmatch(self.verb) is None:
            raise ValueError(
                f"move {self.id!r}: verb {self.verb!r} must be one lowercase word of 2 to 12 "
                "letters, with no digit, underscore or dot"
            )
        if self.verb in _CALL_KEYS:
            raise ValueError(
                f"move {self.id!r}: {self.verb!r} names a function call, and a reply that "
                "writes it is held back as one; choose another verb"
            )
        if not cueable(self.cls):
            raise ValueError(
                f"move {self.id!r} is {self.cls.value}, which is only ever made by a tool; "
                "give it no verb"
            )


class MoveSet:
    """The brain's moves, by id and by verb. Refuses two moves with one id or
    one verb, since a reply's word must name exactly one move."""

    __slots__ = ("_by_id", "_by_verb")

    def __init__(self, moves: Iterable[Move] = ()) -> None:
        self._by_id: dict[str, Move] = {}
        self._by_verb: dict[str, Move] = {}
        for move in moves:
            self.add(move)

    def add(self, move: Move) -> None:
        """Register one more move."""
        if move.id in self._by_id:
            raise ValueError(f"two moves have the id {move.id!r}")
        if move.verb is not None and move.verb in self._by_verb:
            raise ValueError(
                f"moves {self._by_verb[move.verb].id!r} and {move.id!r} share the verb "
                f"{move.verb!r}"
            )
        self._by_id[move.id] = move
        if move.verb is not None:
            self._by_verb[move.verb] = move

    def get(self, move_id: str) -> Move | None:
        """The move with this id, if there is one."""
        return self._by_id.get(move_id)

    def by_verb(self, verb: str) -> Move | None:
        """The move a reply names with ``verb``, if there is one."""
        return self._by_verb.get(verb)

    @property
    def verbs(self) -> frozenset[str]:
        """Every verb a reply may use."""
        return frozenset(self._by_verb)

    def __getitem__(self, move_id: str) -> Move:
        return self._by_id[move_id]

    def __contains__(self, move_id: object) -> bool:
        return move_id in self._by_id

    def __iter__(self) -> Iterator[Move]:
        return iter(self._by_id.values())

    def __len__(self) -> int:
        return len(self._by_id)
