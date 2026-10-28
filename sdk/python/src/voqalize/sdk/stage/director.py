"""The brain's half of Stage: one director per session.

:class:`Stage` sends every move the brain makes to the page and folds every
answer back. Cues come out of the reply as the voice streams it
(:meth:`Stage.cued`); tool moves are sent by :meth:`Stage.send`, one at a time
when their class says so; each answer arrives at :meth:`Stage.handle`; and a
move the page never answered comes back from :meth:`Stage.expire` as
``unknown``. Every move has a ``call_ref`` this director mints, and gets exactly
one final :class:`~voqalize.sdk.stage.StageResult`.

The director decides nothing the brain should: what the model hears about a
result is the brain's to write, from what :meth:`Stage.handle` returns.
"""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator, Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

from loguru import logger

from ..actions import Action
from ..events import Speech, SpeechChunk, SpeechStart
from .cues import AutoCues, CueParser, RawCue
from .moves import Move, MoveSet
from .policy import POLICY
from .wire import STAGE_CONTRACT, StageCue, StageHello, StageMove, StageResult

__all__ = ["CUE_WAIT_S", "ArgValue", "Refused", "Resolve", "Stage"]

#: How long the page waits for a cue's words before it drops the cue. A cue's
#: answer is due this long, plus the result timeout, after it is sent.
CUE_WAIT_S = 45.0

#: One value of a tool move's arguments.
ArgValue = str | int | float | bool | list[str] | None

#: ``(move, args)`` → the arguments to send, rewritten to what the page offers,
#: or ``None`` to drop the cue.
Resolve = Callable[[Move, list[str]], list[str] | None]

_LANDED = ("applied", "partial")


class Refused(Exception):
    """:meth:`Stage.send` was asked for exactly the move that is already
    running, or already queued: it is not sent twice. ``call_ref`` is the
    running move's, or ``None`` for a queued one, which has none yet."""

    def __init__(self, move: str, call_ref: str | None, why: Literal["running", "queued"]) -> None:
        self.move = move
        self.call_ref = call_ref
        self.why: Literal["running", "queued"] = why
        super().__init__(f"{move} is already {why}" + (f" ({call_ref})" if call_ref else ""))


@dataclass(slots=True)
class _Flight:
    call_ref: str
    move: Move
    args: dict[str, ArgValue] | None
    """A tool move's arguments; ``None`` for a cue."""
    deadline: float


@dataclass(slots=True)
class _Queued:
    move: Move
    args: dict[str, ArgValue]
    when: Literal["now", "quiet"]


class Stage:
    """Composable director. A brain owns one per session.

    ``dispatch`` sends an action to the page (``session.dispatch``); ``moves``
    are the moves the brain knows; ``resolve`` may rewrite a cue's arguments
    to what the page offers, or drop it by returning ``None``; ``backstop``
    adds cues to sentences the model left without one (see
    :class:`~voqalize.sdk.stage.CueParser`). A move the page has not answered
    within ``result_timeout_s`` (cues: :data:`CUE_WAIT_S` more) is reported by
    :meth:`expire` as ``unknown``.
    """

    def __init__(
        self,
        *,
        dispatch: Callable[[Action], None],
        moves: Iterable[Move],
        resolve: Resolve | None = None,
        backstop: AutoCues | None = None,
        result_timeout_s: float = 20.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._dispatch = dispatch
        self.moves = moves if isinstance(moves, MoveSet) else MoveSet(moves)
        self._resolve = resolve
        self._backstop = backstop
        self._timeout = result_timeout_s
        self._clock = clock
        self._n = 0
        self._flights: dict[str, _Flight] = {}
        self._refs: dict[str, Move] = {}
        self._done: set[str] = set()
        self._running: str | None = None
        self._queued: _Queued | None = None
        self.hello: StageHello | None = None
        """The last page that said hello, if any."""

    # ─── cues ──────────────────────────────────────────────────────────────

    async def cued(self, turn: AsyncGenerator[Speech, None]) -> AsyncGenerator[Speech, None]:
        """``turn`` with every cue taken out of its text and sent to the page as
        a :class:`StageCue` with a fresh ``call_ref``. Each unit of speech gets
        a parser of its own; cues are released as their words stream."""
        unit = 0
        opened = False
        parser = self._parser(unit)
        try:
            async for event in turn:
                if isinstance(event, SpeechStart):
                    if opened:
                        unit += 1
                    opened = True
                    parser = self._parser(unit)
                elif isinstance(event, SpeechChunk):
                    text, raw = parser.feed(event.text)
                    self._cue_all(raw)
                    if text:
                        yield SpeechChunk(text)
                    continue
                else:  # SpeechEnd
                    rest, raw = parser.flush()
                    self._cue_all(raw)
                    if rest:
                        yield SpeechChunk(rest)
                yield event
        finally:
            await turn.aclose()

    def _parser(self, unit: int) -> CueParser:
        return CueParser(self.moves.verbs, self._backstop, unit=unit)

    def _cue_all(self, raw: list[RawCue]) -> None:
        for cue in raw:
            self.cue(cue)

    def cue(self, raw: RawCue) -> str | None:
        """Resolve one cue and send it; its ``call_ref``, or ``None`` when it
        was dropped. :meth:`cued` calls this for every cue it parses."""
        move = self.moves.by_verb(raw.verb)
        if move is None:
            logger.info("stage: cue {} is no move; dropped", raw.verb)
            return None
        if len(raw.args) > len(move.args):
            logger.info(
                "stage: cue {} has {} arguments, {} takes {}; dropped",
                raw.verb,
                len(raw.args),
                move.id,
                len(move.args),
            )
            return None
        args: list[str] | None = list(raw.args)
        if self._resolve is not None:
            args = self._resolve(move, args)
        if args is None:
            logger.info("stage: cue {} {} names nothing on the page; dropped", raw.verb, raw.args)
            return None
        ref = self._mint(move)
        self._flights[ref] = _Flight(ref, move, None, self._clock() + CUE_WAIT_S + self._timeout)
        logger.info(
            "stage: {} cue {} {} at {!r} before {}{}",
            ref,
            move.id,
            args,
            raw.at,
            raw.before,
            " (backstop)" if raw.auto else "",
        )
        self._dispatch(
            StageCue(
                call_ref=ref,
                move=move.id,
                verb=raw.verb,
                args=args,
                at=raw.at,
                before=raw.before,
                unit=raw.unit,
            )
        )
        return ref

    # ─── tool moves ────────────────────────────────────────────────────────

    def send(
        self,
        move: str,
        args: Mapping[str, ArgValue] | None = None,
        *,
        when: Literal["now", "quiet"] = "now",
    ) -> str | None:
        """Send a move because a tool asked for it.

        Returns its ``call_ref``; or ``None`` when its class is serial and
        another serial move is still running, in which case it is queued and
        sent once that one lands. A newer queued move replaces an older one.
        Raises :class:`Refused` for exactly the move already running or
        queued, and :class:`KeyError` for a move id the brain does not know.
        """
        m = self.moves.get(move)
        if m is None:
            raise KeyError(f"no move {move!r}")
        payload: dict[str, ArgValue] = dict(args or {})
        if not POLICY[m.cls].serial:
            return self._send(m, payload, when)
        running = self._live_running()
        if running is not None and running.move.id == m.id and running.args == payload:
            raise Refused(m.id, running.call_ref, "running")
        queued = self._queued
        if queued is not None and queued.move.id == m.id and queued.args == payload:
            raise Refused(m.id, None, "queued")
        if running is None:
            if queued is not None:
                logger.info(
                    "stage: {} replaces {}, queued behind a move that timed out",
                    m.id,
                    queued.move.id,
                )
            self._queued = None
            return self._send(m, payload, when)
        if queued is not None:
            logger.info("stage: {} replaces {} in the queue", m.id, queued.move.id)
        logger.info("stage: {} queued behind {} ({})", m.id, running.move.id, running.call_ref)
        self._queued = _Queued(m, payload, when)
        return None

    def _send(self, move: Move, args: dict[str, ArgValue], when: Literal["now", "quiet"]) -> str:
        ref = self._mint(move)
        self._flights[ref] = _Flight(ref, move, args, self._clock() + self._timeout)
        if POLICY[move.cls].serial:
            self._running = ref
        logger.info("stage: {} move {} {} ({})", ref, move.id, args, when)
        self._dispatch(StageMove(call_ref=ref, move=move.id, args=args, when=when))
        return ref

    def _live_running(self) -> _Flight | None:
        """The serial move in flight, unless its time is up."""
        if self._running is None:
            return None
        f = self._flights.get(self._running)
        # Past its time it blocks nothing, but stays the running move until
        # :meth:`expire` reports it, which also settles the queued one.
        if f is None or f.deadline <= self._clock():
            return None
        return f

    @property
    def busy(self) -> str | None:
        """The id of the serial move in flight, within its time; else ``None``."""
        f = self._live_running()
        return f.move.id if f is not None else None

    @property
    def queued(self) -> str | None:
        """The id of the move waiting for :attr:`busy` to land, if any."""
        return self._queued.move.id if self._queued is not None else None

    def move_of(self, call_ref: str) -> Move | None:
        """The move a ``call_ref`` was minted for, for logging."""
        return self._refs.get(call_ref)

    # ─── answers ───────────────────────────────────────────────────────────

    def handle(self, event: StageResult | StageHello) -> StageResult | None:
        """Fold an answer from the page.

        A final result clears its move, sends the queued move if the running
        one landed (``applied`` or ``partial``), and comes back so the brain can
        write its note. When the running move did not land, the queued move is
        not sent, and the returned result's ``detail`` says so (its ``outcome``
        is as received). A result with ``moved`` set is interim — the next page
        finishes the move — and comes back without clearing it. A duplicate, a
        result after its move expired, or a hello returns ``None``.
        """
        if isinstance(event, StageHello):
            self.hello = event
            if event.contract != STAGE_CONTRACT:
                logger.warning(
                    "stage: the page runs contract {} ({}), this brain {}",
                    event.contract,
                    event.runtime,
                    STAGE_CONTRACT,
                )
            else:
                logger.info("stage: hello from {} at {}", event.runtime, event.url)
            return None
        f = self._flights.get(event.call_ref)
        if f is None:
            why = "after it was answered or expired" if event.call_ref in self._done else "unknown"
            logger.info("stage: result for {} ({}) {}; ignored", event.call_ref, event.move, why)
            return None
        if event.moved:
            f.deadline = self._clock() + self._timeout
            logger.info("stage: {} {} moved on to another page", f.call_ref, f.move.id)
            return event
        logger.info(
            "stage: {} {} -> {}{}",
            f.call_ref,
            f.move.id,
            event.outcome,
            f": {event.detail}" if event.detail else "",
        )
        note = self._land(f, landed=event.outcome in _LANDED)
        if note:
            detail = f"{event.detail} ({note})" if event.detail else note
            return event.model_copy(update={"detail": detail})
        return event

    def expire(self) -> list[StageResult]:
        """Every move whose answer is overdue, as an ``unknown`` result, oldest
        first. Call it from a periodic tick, or at the start of each turn."""
        now = self._clock()
        out: list[StageResult] = []
        for f in [f for f in self._flights.values() if f.deadline <= now]:
            logger.warning("stage: {} {} never answered; unknown", f.call_ref, f.move.id)
            detail = "the page did not answer in time"
            if note := self._land(f, landed=False):
                detail = f"{detail} ({note})"
            out.append(
                StageResult(call_ref=f.call_ref, move=f.move.id, outcome="unknown", detail=detail)
            )
        return out

    def _land(self, f: _Flight, *, landed: bool) -> str | None:
        """Retire ``f``; if it was the running move, send or drop the queued
        one. Returns a note when the queued move was dropped."""
        del self._flights[f.call_ref]
        self._done.add(f.call_ref)
        if self._running != f.call_ref:
            return None
        self._running = None
        queued, self._queued = self._queued, None
        if queued is None:
            return None
        if landed:
            logger.info("stage: {} landed; sending the queued {}", f.move.id, queued.move.id)
            self._send(queued.move, queued.args, queued.when)
            return None
        logger.info("stage: {} did not land; the queued {} is dropped", f.move.id, queued.move.id)
        return f"so {queued.move.id}, asked for while it ran, was not sent"

    def _mint(self, move: Move) -> str:
        self._n += 1
        ref = f"c{self._n}"
        self._refs[ref] = move
        return ref
