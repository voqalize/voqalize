"""The brain's half of Stage: one director per session.

:class:`Stage` sends every move the brain makes to the page and folds every
answer back. Cues come out of the reply as the voice streams it
(:meth:`Stage.cued`); tool moves are sent by :meth:`Stage.send`, one at a time
when their class says so; each answer arrives at :meth:`Stage.handle`; and a
move the page never answered comes back from :meth:`Stage.expire` as
``unknown`` (run it on a timer with :meth:`Stage.watch`, or read
:meth:`Stage.next_deadline`). A page that answers after that is not ignored:
its result comes back marked ``late``, so the brain can correct what it said.
A move that is slow says so with :class:`~voqalize.sdk.stage.StageProgress`,
each of which gives it its time again. Every move has a ``call_ref`` this director mints, and gets exactly
one final :class:`~voqalize.sdk.stage.StageResult` — under that ``call_ref``
and its own move id, also when the page carried it on to the next page and
finished it there. A cue the director could not send is not silent either:
``on_drop`` hears of it, with why.

**A promise is checked too.** A move may name the phrases that claim it
(``Move.claims``: "opening the calendar") and the things it acts on
(``Move.objects``: "calendar", "nights"), so that "I'll open the calendar" or
"I'm selecting three nights" claims it with no phrase written for it. The
director knows what each turn said, as the parser released it to the voice,
and which moves it sent; at :meth:`Stage.end_turn` — after the model's tool
calls, which come at the end of its response — a claim for a move the turn neither sent nor has running is
reported, once, to ``on_unkept`` and in the return value, so the brain can ask
the model to keep it or to say it has not.

**A move that has landed is said at once.** The moment the page shows what a
move did — its result, or a site event the brain maps to the running move with
:meth:`Stage.landed` — ``on_landed`` may return a short written line. The
director keeps it for :meth:`Stage.take_lines`, and the brain says it as soon
as the floor is free, with no model request before it; the model may then add
one sentence (:func:`landed_ask`). A move whose effect was reported gets no
holding line, and its later result only matters if it failed or was partial.

The director decides nothing the brain should: what the model hears about a
result is the brain's to write, from what :meth:`Stage.handle` returns.
"""

from __future__ import annotations

import asyncio
import dataclasses
import inspect
import time
from collections.abc import AsyncGenerator, Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, overload

from loguru import logger

from ..actions import Action
from ..events import Speech, SpeechChunk, SpeechStart
from .cues import AutoCues, CueParser, RawCue, sentences
from .labels import tokens
from .moves import Move, MoveSet
from .policy import POLICY, MoveClass
from .promises import claim_in, promise_in
from .state import Folded, Mirror
from .wire import (
    STAGE_CONTRACT,
    Phase,
    StageCue,
    StageEvent,
    StageHello,
    StageMove,
    StageProgress,
    StageResult,
)

__all__ = [
    "CUE_WAIT_S",
    "FINISHED_KEEP_S",
    "HOLDING_LINE_S",
    "LANDED_AFTER_RESULT_S",
    "LANDING_FLOOR_MS",
    "LANDING_LINE_KEEP_S",
    "RESULT_TIMEOUTS",
    "ArgValue",
    "Dropped",
    "Landing",
    "OnDrop",
    "OnLanded",
    "OnProgress",
    "OnUnkept",
    "Refused",
    "Resolve",
    "Running",
    "Stage",
    "Unkept",
    "landed_ask",
]

#: How long the page waits for a cue's words before it drops the cue. A cue's
#: answer is due this long, plus the result timeout, after it is sent.
CUE_WAIT_S = 45.0

#: One value of a tool move's arguments.
ArgValue = str | int | float | bool | list[str] | None

#: ``(move, args)`` → the arguments to send, rewritten to what the page offers,
#: or ``None`` to drop the cue.
Resolve = Callable[[Move, list[str]], list[str] | None]

#: Why a cue was not sent: ``resolve`` returned ``None`` (``unresolved``), the
#: verb is no move of this brain (``unknown_verb``), or it gives more
#: arguments than its move takes (``too_many_args``).
Dropped = Literal["unresolved", "unknown_verb", "too_many_args"]

#: ``(cue, why)``: told of every cue the reply wrote that was not sent.
OnDrop = Callable[[RawCue, Dropped], None]

#: Told of every :class:`StageProgress` for a move still running.
OnProgress = Callable[[StageProgress], None]

#: ``(move, phrase, sentence)``: a turn said ``phrase``, a claim of ``move``,
#: in ``sentence``, and never sent the move.
OnUnkept = Callable[[Move, str, str], None]

#: How long a finished or expired ``call_ref`` is remembered: a result that
#: arrives within this after its move was reported ``unknown`` comes back
#: ``late``, and a duplicate is told from a stranger.
FINISHED_KEEP_S = 60.0

#: A confirmed or reversible move running this long is worth one written line
#: from the brain (:meth:`Stage.holding`), so the silence is not taken for a
#: failure.
HOLDING_LINE_S = 6.0

#: The quiet a brain should wait before it says a landing line: the idle
#: window to set once :meth:`Stage.take_lines` has one (milliseconds).
LANDING_FLOOR_MS = 300

#: How long a landing line waits to be said: past this, the screen has moved
#: on, and :meth:`Stage.take_lines` lets it go.
LANDING_LINE_KEEP_S = 8.0

#: A site event this soon after a move's ``applied`` result may still be its
#: landing: a page may send the result a moment before the event that shows it.
LANDED_AFTER_RESULT_S = 3.0

#: How often :meth:`Stage.watch` looks, at most, with nothing due sooner.
_WATCH_POLL_S = 0.25

#: How long the page has to answer a move, by its class, unless the brain says
#: otherwise: a look is quick, a page load is slow (a site's ``load`` can take
#: over 15 s), and a confirmed move may go through a cart or a form. A cue's
#: answer is due :data:`CUE_WAIT_S` later still.
RESULT_TIMEOUTS: MappingProxyType[MoveClass, float] = MappingProxyType(
    {
        MoveClass.LOOK: 10.0,
        MoveClass.NAVIGATE: 25.0,
        MoveClass.REVERSIBLE: 20.0,
        MoveClass.CONFIRMED: 30.0,
    }
)

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


@dataclass(frozen=True, slots=True)
class Running:
    """One move still waiting for its result, for the brain to describe."""

    move: Move
    call_ref: str
    phase: Phase | None
    """The last phase the page reported, or ``None`` before any."""
    seconds: float
    """How long since it was sent."""
    shown: bool = False
    """Whether the page already showed what it did (:meth:`Stage.landed`, or a
    landed result): it is not slow, only not answered yet."""


@dataclass(frozen=True, slots=True)
class Landing:
    """A move whose visible effect the page reported, handed to ``on_landed``
    for a written line. ``result`` is the page's result when that is what
    reported it; ``event`` the site event the brain mapped to the move with
    :meth:`Stage.landed`. At most one of them is set."""

    move: Move
    call_ref: str
    seconds: float
    """How long since the move was sent."""
    result: StageResult | None = None
    event: object | None = None
    args: Mapping[str, ArgValue] | None = None
    """A tool move's arguments, as sent; ``None`` for a cue."""
    cue_args: tuple[str, ...] = ()
    """A cue's arguments, as resolved and sent to the page."""


#: ``landing`` → a short written line to say as soon as the floor is free, or
#: ``None`` for none.
OnLanded = Callable[[Landing], str | None]


def landed_ask(line: str) -> str:
    """What to ask the model after a landing line was said: at most one more
    sentence, never the line again. Provider-neutral text for the brain's own
    note."""
    return (
        f'You have just said: "{line}". Never say that again. Add at most one short sentence '
        "about what is now on their screen, in the language you speak, or say nothing."
    )


@dataclass(frozen=True, slots=True)
class Unkept:
    """A promise a turn made and did not keep: it said ``phrase`` in
    ``sentence`` and never sent ``move``. ``phrase`` is one of ``move``'s
    claims, as written, or the folded words from the verb to the object of a
    promise about one of its objects ("opening the rooms")."""

    move: Move
    phrase: str
    sentence: str


@dataclass(slots=True)
class _Flight:
    call_ref: str
    move: Move
    args: dict[str, ArgValue] | None
    """A tool move's arguments; ``None`` for a cue."""
    deadline: float
    cue_args: tuple[str, ...] = ()
    """A cue's arguments, as resolved."""
    sent_at: float = 0.0
    phase: Phase | None = None
    held: bool = False
    """Whether :meth:`Stage.holding` already handed it out."""
    shown: bool = False
    """Whether the page already showed what it did."""


@dataclass(slots=True)
class _Finished:
    move: Move
    at: float
    expired: bool
    """Reported ``unknown`` by :meth:`Stage.expire`, rather than answered."""
    corrected: bool = False
    """A late result for it was already handed back."""
    shown: bool = False
    """The page showed what it did before its result came."""
    flight: _Flight | None = None
    """The move as it ran: a site event just behind its ``applied`` result
    may still be its landing (:data:`LANDED_AFTER_RESULT_S`)."""
    applied: bool = False


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
    :meth:`expire` as ``unknown``: one number for every move, or a mapping by
    class, whose missing classes keep :data:`RESULT_TIMEOUTS`. ``on_drop``
    is told of every cue the reply wrote that was not sent, with why — so a
    brain can say so rather than let the voice claim a move that never went.
    ``on_progress`` is told of every :class:`StageProgress` for a running move.
    ``on_unkept`` is told of every claim a turn made and did not keep
    (:meth:`end_turn`). ``on_landed`` is asked for a written line the moment
    a move's visible effect is reported (:meth:`landed`, or a landed result);
    the lines wait in :meth:`take_lines`.
    """

    def __init__(
        self,
        *,
        dispatch: Callable[[Action], None],
        moves: Iterable[Move],
        resolve: Resolve | None = None,
        backstop: AutoCues | None = None,
        result_timeout_s: float | Mapping[MoveClass, float] = RESULT_TIMEOUTS,
        on_drop: OnDrop | None = None,
        on_progress: OnProgress | None = None,
        on_unkept: OnUnkept | None = None,
        on_landed: OnLanded | None = None,
        mirror: Mirror | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._dispatch = dispatch
        self.mirror = mirror
        """The page's state as named acts folded it (:mod:`~voqalize.sdk.stage.state`),
        when the brain keeps one; a :class:`StageEvent` is folded into it."""
        self.moves = moves if isinstance(moves, MoveSet) else MoveSet(moves)
        self._resolve = resolve
        self._backstop = backstop
        if isinstance(result_timeout_s, Mapping):
            self._timeouts = {**RESULT_TIMEOUTS, **result_timeout_s}
        else:
            self._timeouts = dict.fromkeys(MoveClass, float(result_timeout_s))
        self._on_drop = on_drop
        self._on_progress = on_progress
        self._on_unkept = on_unkept
        self._on_landed = on_landed
        self._clock = clock
        #: Landing lines not said yet: (when, line).
        self._lines: list[tuple[float, str]] = []
        self._n = 0
        self._flights: dict[str, _Flight] = {}
        self._refs: dict[str, Move] = {}
        self._finished: dict[str, _Finished] = {}
        self._running: str | None = None
        self._queued: _Queued | None = None
        self.hello: StageHello | None = None
        """The last page that said hello, if any."""
        #: This turn: what it said, and the moves it sent or saw answered.
        self._turn_said: list[str] = []
        self._turn_sent: set[str] = set()
        #: The first words after each cue the model wrote this turn.
        self._turn_cued: list[list[str]] = []

    # ─── turns ─────────────────────────────────────────────────────────────

    def begin_turn(self) -> None:
        """Start a turn: forget what the last one said and sent. Optional —
        :meth:`end_turn` starts the next turn too — for a brain whose turn
        was cut off before it could end it."""
        self._turn_said = []
        self._turn_sent = set()
        self._turn_cued = []

    def end_turn(self) -> list[Unkept]:
        """End the turn, after its tool calls have run: every move the turn
        claimed in its speech and did not keep — not sent or cued this turn,
        not running or queued, not answered since the turn began — once per
        move, in the order it was said. Each is logged and told to
        ``on_unkept``. Then the next turn begins.

        A sentence claims a move by saying one of its :attr:`Move.claims`, or
        by promising to act on one of its :attr:`Move.objects` ("I'm opening
        the rooms"); a question is an offer, not a claim. A sentence is one
        promise: when it claims several moves ("the rooms" may be either the
        rates or a room), any of them made keeps it, and an unkept one is told
        as the first of them in the brain's order. A promise heard only by its
        shape is kept, too, by a cue the model wrote in its sentence: "{show:
        Rooms} I'll show you the rooms" promised the ring it made."""
        said = "".join(self._turn_said)
        kept = set(self._turn_sent) | {f.move.id for f in self._flights.values()}
        if self._queued is not None:
            kept.add(self._queued.move.id)
        out: list[Unkept] = []
        told: set[str] = set()
        for sentence in sentences(said):
            if sentence.endswith(("?", "\uff1f")):
                continue
            cued = self._cued_in(sentence)
            hits = [
                (m, hit[0])
                for m in self.moves
                if (hit := _claim_of(m, sentence)) is not None and (hit[1] or not cued)
            ]
            if not hits or any(m.id in kept for m, _ in hits):
                continue
            move, phrase = hits[0]
            if move.id in told:
                continue
            told.add(move.id)
            logger.info(
                "stage: unkept {}: the turn said {!r} and never sent it, in {!r}",
                move.id,
                phrase,
                sentence,
            )
            if self._on_unkept is not None:
                self._on_unkept(move, phrase, sentence)
            out.append(Unkept(move, phrase, sentence))
        self.begin_turn()
        return out

    def _cued_in(self, sentence: str) -> bool:
        """Whether a cue the model wrote this turn stands in ``sentence``: the
        words after it are said there."""
        words = tokens(sentence)
        return any(
            any(words[i : i + len(at)] == at for i in range(len(words))) for at in self._turn_cued
        )

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
                        self._turn_said.append("\n")
                    opened = True
                    parser = self._parser(unit)
                elif isinstance(event, SpeechChunk):
                    text, raw = parser.feed(event.text)
                    self._cue_all(raw)
                    if text:
                        self._turn_said.append(text)
                        yield SpeechChunk(text)
                    continue
                else:  # SpeechEnd
                    rest, raw = parser.flush()
                    self._cue_all(raw)
                    if rest:
                        self._turn_said.append(rest)
                        yield SpeechChunk(rest)
                yield event
        finally:
            await turn.aclose()

    def _parser(self, unit: int) -> CueParser:
        return CueParser(
            self.moves.verbs,
            self._backstop,
            unit=unit,
            on_unknown=self._unknown_verb,
            check=self._check,
        )

    def timeout(self, cls: MoveClass) -> float:
        """How long the page has to answer a move of class ``cls``."""
        return self._timeouts[cls]

    def _unknown_verb(self, raw: RawCue) -> None:
        self._drop(raw, "unknown_verb")

    def _drop(self, raw: RawCue, why: Dropped) -> None:
        logger.info(
            "stage: dropped {} ({}){} in {!r}",
            _written(raw),
            why,
            " (backstop)" if raw.auto else "",
            raw.sentence,
        )
        if self._on_drop is not None:
            self._on_drop(raw, why)

    def _admit(self, raw: RawCue) -> tuple[Move, list[str]] | None:
        """The move a cue names and its arguments resolved, or ``None`` when it
        is dropped (``on_drop`` told)."""
        move = self.moves.by_verb(raw.verb)
        if move is None:
            self._drop(raw, "unknown_verb")
            return None
        if len(raw.args) > len(move.args):
            self._drop(raw, "too_many_args")
            return None
        args: list[str] | None
        if raw.resolved is not None:
            args = list(raw.resolved)
        elif self._resolve is not None:
            args = self._resolve(move, list(raw.args))
        else:
            args = list(raw.args)
        if args is None:
            self._drop(raw, "unresolved")
            return None
        return move, args

    def _check(self, raw: RawCue) -> RawCue | None:
        """The parser's say on one of the model's cues once its sentence is
        done: resolved now, so that one the page will never get leaves the
        sentence to the backstop. Resolved once: not again when sent. The
        cue's ``args`` stay as written; the resolved ones ride in
        ``resolved``."""
        admitted = self._admit(raw)
        if admitted is None:
            return None
        # The arguments as the model wrote them stay on the cue: only the
        # page gets the resolved ones.
        return dataclasses.replace(raw, resolved=tuple(admitted[1]))

    def _cue_all(self, raw: list[RawCue]) -> None:
        for cue in raw:
            self.cue(cue)

    def cue(self, raw: RawCue) -> str | None:
        """Resolve one cue and send it; its ``call_ref``, or ``None`` when it
        was dropped. :meth:`cued` calls this for every cue it parses. A cue the
        parser already resolved (``raw.resolved``) is not resolved again. The
        page gets the resolved arguments; ``raw.args`` — what a brain shows the
        model of its own cue — stays as the model wrote it."""
        admitted = self._admit(raw)
        if admitted is None:
            return None
        move, args = admitted
        self._turn_sent.add(move.id)
        if not raw.auto and (at := tokens(raw.at)[:3]):
            self._turn_cued.append(at)
        ref = self._mint(move)
        now = self._clock()
        deadline = now + CUE_WAIT_S + self.timeout(move.cls)
        self._flights[ref] = _Flight(ref, move, None, deadline, tuple(args), sent_at=now)
        logger.info(
            "stage: {} cue {} as {} {} at {!r} before {}{} in {!r}",
            ref,
            _written(raw),
            move.id,
            args,
            raw.at,
            raw.before,
            " (backstop)" if raw.auto else "",
            raw.sentence,
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
        # Asked for, this turn: sent, queued, or already on its way.
        self._turn_sent.add(m.id)
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
        now = self._clock()
        self._flights[ref] = _Flight(ref, move, args, now + self.timeout(move.cls), sent_at=now)
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
        """The move a ``call_ref`` was minted for. A result names it too
        (``StageResult.move``), also for a move finished on another page."""
        return self._refs.get(call_ref)

    # ─── answers ───────────────────────────────────────────────────────────

    @overload
    def handle(self, event: StageResult) -> StageResult | None: ...
    @overload
    def handle(self, event: StageHello) -> None: ...
    @overload
    def handle(self, event: StageProgress) -> StageProgress | None: ...
    @overload
    def handle(self, event: StageEvent) -> Folded | None: ...
    @overload
    def handle(
        self, event: StageResult | StageHello | StageProgress | StageEvent
    ) -> StageResult | StageProgress | Folded | None: ...
    def handle(
        self, event: StageResult | StageHello | StageProgress | StageEvent
    ) -> StageResult | StageProgress | Folded | None:
        """Fold an answer from the page.

        A final result clears its move, sends the queued move if the running
        one landed (``applied`` or ``partial``), and comes back so the brain can
        write its note. When the running move did not land, the queued move is
        not sent, and the returned result's ``detail`` says so (its ``outcome``
        is as received). A result with ``moved`` set is interim — the next page
        finishes the move — and comes back without clearing it, its time
        started again. The result comes back under the move this ``call_ref``
        was minted for, whichever page answered it.

        A result for a move :meth:`expire` already reported ``unknown`` comes
        back once, with ``late`` set: what the page did after all, for the
        brain to correct itself ("King is applied after all"). A
        :class:`StageProgress` for a running move gives it its time again and
        comes back (``on_progress`` is told too). A duplicate, a stranger, a
        progress for a move no longer running, or a hello returns ``None``.

        A :class:`StageEvent` is folded into :attr:`mirror` and comes back as
        what it did (:class:`Folded`, with the line for the model); without a
        mirror, or for an event the spec does not declare, ``None``.
        """
        if isinstance(event, StageEvent):
            if self.mirror is None:
                logger.warning("stage: {} came with no mirror to fold it into", event.name)
                return None
            return self.mirror.fold(event)
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
        if isinstance(event, StageProgress):
            return self._progress(event)
        f = self._flights.get(event.call_ref)
        if f is None:
            return self._late(event)
        if event.move != f.move.id:
            logger.info(
                "stage: {} answered as {}, minted for {}", f.call_ref, event.move, f.move.id
            )
            event = event.model_copy(update={"move": f.move.id})
        if event.moved:
            f.deadline = max(f.deadline, self._clock() + self.timeout(f.move.cls))
            logger.info("stage: {} {} moved on to another page", f.call_ref, f.move.id)
            return event
        self._log_result(f.call_ref, f.move, event, self._clock() - f.sent_at)
        if event.outcome == "applied" and not f.shown:
            self._show(f, result=event)
        note = self._land(f, landed=event.outcome in _LANDED, applied=event.outcome == "applied")
        if note:
            detail = f"{event.detail} ({note})" if event.detail else note
            return event.model_copy(update={"detail": detail})
        return event

    def _late(self, event: StageResult) -> StageResult | None:
        """A result for a move no longer in flight: once, marked ``late``, when
        :meth:`expire` reported it ``unknown``; otherwise ``None``."""
        self._prune()
        done = self._finished.get(event.call_ref)
        if done is None:
            logger.info("stage: result for {} ({}) unknown; ignored", event.call_ref, event.move)
            return None
        if not done.expired or done.corrected:
            logger.info(
                "stage: result for {} ({}) after it was answered; ignored",
                event.call_ref,
                event.move,
            )
            return None
        event = event.model_copy(update={"move": done.move.id, "late": True})
        if event.moved:
            logger.info("stage: {} {} moved on, after it expired", event.call_ref, done.move.id)
            return event
        done.corrected = True
        self._log_result(event.call_ref, done.move, event, None)
        return event

    def _progress(self, event: StageProgress) -> StageProgress | None:
        f = self._flights.get(event.call_ref)
        if f is None:
            logger.debug("stage: progress for {} ({}) not running", event.call_ref, event.phase)
            return None
        f.phase = event.phase
        f.deadline = max(f.deadline, self._clock() + self.timeout(f.move.cls))
        if event.move != f.move.id:
            event = event.model_copy(update={"move": f.move.id})
        logger.info(
            "stage: {} {} {} at {} ms on the page", f.call_ref, f.move.id, event.phase, event.ms
        )
        if self._on_progress is not None:
            self._on_progress(event)
        return event

    @staticmethod
    def _log_result(ref: str, move: Move, r: StageResult, took: float | None) -> None:
        times = [
            f"{name} {value}"
            for name, value in (
                ("received", r.received_ms),
                ("queued", r.queued_ms),
                ("fired", r.fired_ms),
                ("ringed", r.ringed_ms),
                ("lag", r.lag_ms),
            )
            if value is not None
        ]
        logger.info(
            "stage: {} {} -> {}{}{}{} [{} ms acting{}{}{}]",
            ref,
            move.id,
            r.outcome,
            " (late)" if r.late else "",
            f": {r.detail}" if r.detail else "",
            f" refused {[x.arg for x in r.refused]}" if r.refused else "",
            r.ms,
            f"; {r.fired}" if r.fired else "",
            f"; {', '.join(times)} ms" if times else "",
            f"; sent to answered {took * 1000:.0f} ms" if took is not None else "",
        )

    def expire(self) -> list[StageResult]:
        """Every move whose answer is overdue, as an ``unknown`` result, oldest
        first. Call it often — :meth:`watch` does — or at the start of each
        turn: a move is reported no later than the gap between calls."""
        now = self._clock()
        out: list[StageResult] = []
        for f in [f for f in self._flights.values() if f.deadline <= now]:
            logger.warning(
                "stage: {} {} never answered (last phase {}); unknown",
                f.call_ref,
                f.move.id,
                f.phase or "none",
            )
            detail = "the page did not answer in time"
            if note := self._land(f, landed=False, expired=True):
                detail = f"{detail} ({note})"
            out.append(
                StageResult(call_ref=f.call_ref, move=f.move.id, outcome="unknown", detail=detail)
            )
        return out

    def next_deadline(self) -> float | None:
        """When, on this director's clock, the next move falls due for
        :meth:`expire`; ``None`` with nothing in flight."""
        return min((f.deadline for f in self._flights.values()), default=None)

    async def watch(
        self,
        on_expired: Callable[[StageResult], Awaitable[None] | None],
        *,
        poll_s: float = _WATCH_POLL_S,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        """Run :meth:`expire` as each deadline falls, for as long as the task
        lives, and hand each ``unknown`` result to ``on_expired``. Start it
        once per session (``asyncio.create_task(stage.watch(...))``) and cancel
        it at the end; nothing is reported more than ``poll_s`` late."""
        while True:
            due = self.next_deadline()
            wait = poll_s if due is None else min(poll_s, max(0.0, due - self._clock()))
            await sleep(wait)
            for result in self.expire():
                got = on_expired(result)
                if inspect.isawaitable(got):
                    await got

    def running(self) -> list[Running]:
        """Every move still waiting for its result, oldest first, with the
        phase the page last reported: what the brain can describe ("still
        loading the rooms page")."""
        now = self._clock()
        return [
            Running(f.move, f.call_ref, f.phase, now - f.sent_at, f.shown)
            for f in sorted(self._flights.values(), key=lambda f: f.sent_at)
        ]

    def holding(self, after_s: float = HOLDING_LINE_S) -> list[Running]:
        """The confirmed and reversible moves running longer than ``after_s``
        that this has not handed out before: each is worth one written holding
        line from the brain, once, so a slow move is not heard as a failed one.
        A move whose effect the page already showed is not slow: never one."""
        now = self._clock()
        out: list[Running] = []
        for f in sorted(self._flights.values(), key=lambda f: f.sent_at):
            if f.held or f.shown or f.move.cls not in (MoveClass.CONFIRMED, MoveClass.REVERSIBLE):
                continue
            if now - f.sent_at < after_s:
                continue
            f.held = True
            out.append(Running(f.move, f.call_ref, f.phase, now - f.sent_at))
        return out

    # ─── landings ──────────────────────────────────────────────────────────

    def landed(
        self,
        moves: str | Iterable[str],
        *,
        event: object | None = None,
        call_ref: str | None = None,
        fits: Callable[[Landing], bool] | None = None,
    ) -> str | None:
        """The page shows what a running move did: a site event the brain reads
        as its effect (a listing shown for a filter, the calendar for an
        availability check). ``moves`` names the move ids it can be the effect
        of; the newest running one of them not shown yet (or ``call_ref``'s),
        and that ``fits`` the event when given (the listing has the filter the
        move asked for, not the unfiltered one a load showed first), is marked
        shown: it gets no holding line from now, and ``on_landed`` is asked for
        its written line, kept for :meth:`take_lines`. Once per move: the line,
        or ``None`` when no such move is running, or the brain has none. A move
        whose ``applied`` result came in the last :data:`LANDED_AFTER_RESULT_S`
        with no line for it counts as running here: the page may answer a
        moment before the event that shows it."""
        ids = {moves} if isinstance(moves, str) else set(moves)
        now = self._clock()

        def ok(f: _Flight) -> bool:
            if f.move.id not in ids or f.shown:
                return False
            if call_ref is not None and f.call_ref != call_ref:
                return False
            return fits is None or fits(self._landing(f, now, event=event))

        just = [
            d.flight
            for d in self._finished.values()
            if d.flight is not None and d.applied and now - d.at <= LANDED_AFTER_RESULT_S
        ]
        candidates = [f for f in (*self._flights.values(), *just) if ok(f)]
        found = max(candidates, key=lambda f: f.sent_at, default=None)
        if found is None:
            return None
        line = self._show(found, event=event)
        if (done := self._finished.get(found.call_ref)) is not None:
            done.shown = True
        return line

    def shown(self, call_ref: str) -> bool:
        """Whether the page showed what ``call_ref``'s move did before (or
        with) its result: a later ``applied`` adds nothing for the voice."""
        f = self._flights.get(call_ref)
        if f is not None:
            return f.shown
        done = self._finished.get(call_ref)
        return done is not None and done.shown

    def take_lines(self) -> list[str]:
        """The landing lines waiting to be said, oldest first, and forgotten:
        say them in the next floor, with no model request before them. One
        older than :data:`LANDING_LINE_KEEP_S` is let go unsaid."""
        cut = self._clock() - LANDING_LINE_KEEP_S
        lines = [line for at, line in self._lines if at >= cut]
        if len(lines) < len(self._lines):
            logger.info("stage: {} landing line(s) too old to say", len(self._lines) - len(lines))
        self._lines = []
        return lines

    @property
    def lines_waiting(self) -> bool:
        """Whether a landing line is waiting for :meth:`take_lines`."""
        return bool(self._lines)

    @staticmethod
    def _landing(
        f: _Flight, now: float, *, result: StageResult | None = None, event: object | None = None
    ) -> Landing:
        return Landing(
            f.move,
            f.call_ref,
            now - f.sent_at,
            result=result,
            event=event,
            args=MappingProxyType(f.args) if f.args is not None else None,
            cue_args=f.cue_args,
        )

    def _show(
        self, f: _Flight, *, result: StageResult | None = None, event: object | None = None
    ) -> str | None:
        """``f``'s effect is on the page: shown, and its line asked for. A
        result shows it only when the brain has a line for it (an event that
        came first already did): with none, it is simply answered."""
        now = self._clock()
        if result is None:
            f.shown = True
            logger.info(
                "stage: {} {} shown on the page at {:.0f} ms ({})",
                f.call_ref,
                f.move.id,
                (now - f.sent_at) * 1000,
                type(event).__name__,
            )
        if self._on_landed is None:
            return None
        line = self._on_landed(self._landing(f, now, result=result, event=event))
        if line:
            f.shown = True
            logger.info("stage: {} {} landing line {!r}", f.call_ref, f.move.id, line)
            self._lines.append((now, line))
        return line or None

    def _land(
        self, f: _Flight, *, landed: bool, expired: bool = False, applied: bool = False
    ) -> str | None:
        """Retire ``f``; if it was the running move, send or drop the queued
        one. Returns a note when the queued move was dropped."""
        del self._flights[f.call_ref]
        if not expired:
            # Answered during this turn: a claim of it this turn is true.
            self._turn_sent.add(f.move.id)
        self._prune()
        self._finished[f.call_ref] = _Finished(
            f.move, self._clock(), expired, shown=f.shown, flight=f, applied=applied
        )
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

    def _prune(self) -> None:
        cut = self._clock() - FINISHED_KEEP_S
        for ref in [r for r, d in self._finished.items() if d.at < cut]:
            del self._finished[ref]

    def _mint(self, move: Move) -> str:
        self._n += 1
        ref = f"c{self._n}"
        self._refs[ref] = move
        return ref


def _claim_of(move: Move, sentence: str) -> tuple[str, bool] | None:
    """What in ``sentence`` claims ``move``, and whether it is one of its
    written claims: the first of its claims said, or else the words of a
    promise about one of its objects; ``None`` when nothing does."""
    for claim in move.claims:
        if claim_in(claim, sentence):
            return claim, True
    shaped = promise_in(move.objects, sentence) if move.objects else None
    return None if shaped is None else (shaped, False)


def _written(raw: RawCue) -> str:
    """A cue as the model wrote it, for the logs."""
    return f"{{{raw.verb}: {' | '.join(raw.args)}}}" if raw.args else f"{{{raw.verb}}}"
