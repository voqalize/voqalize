"""What two live dev calls taught the director: a result after ``unknown``
corrects it, expiry runs on time, progress keeps a slow move alive, a cue the
resolver drops leaves its sentence to the backstop, and every decision is in
the log."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator

import pytest
from loguru import logger

from voqalize.sdk import Action
from voqalize.sdk.events import RTVIMessage, RTVIType, Speech, SpeechChunk, SpeechEnd, SpeechStart
from voqalize.sdk.stage import (
    CUE_WAIT_S,
    FINISHED_KEEP_S,
    HOLDING_LINE_S,
    Dropped,
    Move,
    MoveClass,
    RawCue,
    Stage,
    StageCue,
    StagePageEvents,
    StageProgress,
    StageResult,
)

MOVES = (
    Move(id="core.show", verb="show", cls=MoveClass.LOOK, args=("target",)),
    Move(id="core.page", verb="page", cls=MoveClass.NAVIGATE, args=("path",)),
    Move(id="shop.filter", verb="filter", cls=MoveClass.REVERSIBLE, args=("facet", "value")),
    Move(id="cart.add", verb=None, cls=MoveClass.CONFIRMED, args=("product",)),
)


class Clock:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


def _stage(**kw: object) -> tuple[Stage, list[Action], Clock]:
    sent: list[Action] = []
    clock = Clock()
    stage = Stage(dispatch=sent.append, moves=MOVES, clock=clock, **kw)  # type: ignore[arg-type]
    return stage, sent, clock


def _result(ref: str, move: str, outcome: str = "applied", **kw: object) -> StageResult:
    return StageResult(call_ref=ref, move=move, outcome=outcome, **kw)  # type: ignore[arg-type]


async def _turn(*events: Speech) -> AsyncGenerator[Speech, None]:
    for e in events:
        yield e


@pytest.fixture
def logs() -> Iterator[list[str]]:
    lines: list[str] = []
    sink = logger.add(lambda m: lines.append(str(m)), level="INFO", format="{message}")
    yield lines
    logger.remove(sink)


# ─── a result after unknown ────────────────────────────────────────────────


def test_a_result_after_unknown_comes_back_late_once() -> None:
    stage, _, clock = _stage()
    ref = stage.send("shop.filter", {"facet": "brand", "value": "King"})
    assert ref == "c1"
    clock.t += 21
    [unknown] = stage.expire()
    assert unknown.outcome == "unknown" and not unknown.late
    clock.t += 5
    late = stage.handle(_result("c1", "shop.filter", detail="King applied; 8 products"))
    assert late is not None and late.late and late.outcome == "applied"
    assert late.detail == "King applied; 8 products"
    assert stage.handle(_result("c1", "shop.filter")) is None


def test_an_interim_after_unknown_does_not_use_up_the_correction() -> None:
    stage, _, clock = _stage()
    stage.send("core.page", {"path": "/rooms"})
    clock.t += 26
    assert len(stage.expire()) == 1
    interim = stage.handle(_result("c1", "core.page", moved=True))
    assert interim is not None and interim.late and interim.moved
    final = stage.handle(_result("c1", "site.arrive", detail="opened /rooms"))
    assert final is not None and final.late and final.move == "core.page"


def test_a_result_for_a_move_already_answered_is_a_duplicate() -> None:
    stage, _, _ = _stage()
    stage.send("core.show", {"target": "Rooms"})
    assert stage.handle(_result("c1", "core.show")) is not None
    assert stage.handle(_result("c1", "core.show")) is None


def test_finished_moves_are_forgotten_after_a_minute() -> None:
    stage, _, clock = _stage()
    stage.send("core.show", {"target": "Rooms"})
    clock.t += 11
    assert len(stage.expire()) == 1
    clock.t += FINISHED_KEEP_S + 1
    assert stage.handle(_result("c1", "core.show")) is None


# ─── expiry on time ────────────────────────────────────────────────────────


def test_next_deadline_is_the_earliest_in_flight() -> None:
    stage, _, clock = _stage()
    assert stage.next_deadline() is None
    stage.send("core.page", {"path": "/rooms"})
    stage.send("core.show", {"target": "Rooms"})
    assert stage.next_deadline() == clock.t + 10.0
    stage.handle(_result("c2", "core.show"))
    assert stage.next_deadline() == clock.t + 25.0


async def test_watch_expires_each_move_as_it_falls_due() -> None:
    stage, _, clock = _stage()
    stage.send("core.show", {"target": "Rooms"})
    waits: list[float] = []
    expired: list[StageResult] = []

    async def sleep(s: float) -> None:
        waits.append(s)
        clock.t += s
        if expired:
            raise StopAsyncIteration

    async def on_expired(r: StageResult) -> None:
        expired.append(r)

    with pytest.raises(StopAsyncIteration):
        await stage.watch(on_expired, poll_s=0.25, sleep=sleep)
    assert [r.call_ref for r in expired] == ["c1"]
    # It looked every quarter second, never more than that late.
    assert max(waits) <= 0.25 and 40 <= len(waits) <= 41


async def test_watch_takes_a_plain_callback_too() -> None:
    stage, _, clock = _stage()
    stage.send("core.show", {"target": "Rooms"})
    expired: list[StageResult] = []

    async def sleep(s: float) -> None:
        clock.t += 10.0
        if expired:
            raise StopAsyncIteration

    with pytest.raises(StopAsyncIteration):
        await stage.watch(expired.append, sleep=sleep)
    assert len(expired) == 1


# ─── progress ──────────────────────────────────────────────────────────────


def test_progress_extends_the_deadline_and_comes_back() -> None:
    told: list[StageProgress] = []
    stage, _, clock = _stage(on_progress=told.append)
    stage.send("shop.filter", {"facet": "brand", "value": "King"})
    clock.t += 15
    p = stage.handle(
        StageProgress(call_ref="c1", move="shop.filter", phase="waiting_site", ms=15000)
    )
    assert p is not None and p.phase == "waiting_site" and told == [p]
    clock.t += 15
    assert stage.expire() == []
    [r] = stage.running()
    assert (r.call_ref, r.phase, r.seconds) == ("c1", "waiting_site", 30.0)
    clock.t += 6
    assert [x.outcome for x in stage.expire()] == ["unknown"]
    # A progress for a move no longer running is nothing.
    assert stage.handle(StageProgress(call_ref="c1", move="shop.filter", phase="acting")) is None


def test_progress_never_shortens_a_cue_deadline() -> None:
    stage, _, clock = _stage()
    raw = RawCue("show", ("Rooms",), "Our rooms", 0)
    assert stage.cue(raw) == "c1"
    stage.handle(StageProgress(call_ref="c1", move="core.show", phase="queued"))
    clock.t += CUE_WAIT_S
    assert stage.expire() == []


def test_holding_hands_out_slow_reversible_and_confirmed_moves_once() -> None:
    stage, _, clock = _stage()
    stage.send("core.show", {"target": "Rooms"})
    stage.send("cart.add", {"product": "p1"})
    clock.t += HOLDING_LINE_S - 1
    assert stage.holding() == []
    clock.t += 1.5
    [slow] = stage.holding()
    assert slow.move.id == "cart.add" and slow.seconds == pytest.approx(HOLDING_LINE_S + 0.5)
    assert stage.holding() == []


def test_the_page_events_parse_progress() -> None:
    msg = RTVIMessage(
        type=RTVIType.UI_EVENT,
        data={
            "event": "stage_progress",
            "payload": {"call_ref": "c1", "move": "core.page", "phase": "loading", "ms": 300},
        },
    )
    got = StagePageEvents.parse(msg)
    assert got == StageProgress(call_ref="c1", move="core.page", phase="loading", ms=300)


def test_an_old_page_result_without_telemetry_still_parses() -> None:
    r = StageResult.model_validate(
        {"call_ref": "c1", "move": "m", "outcome": "applied", "refused": [], "moved": False}
    )
    assert r.fired is None and r.lag_ms is None and not r.late


# ─── a cue the resolver drops leaves the sentence to the backstop ──────────


async def test_an_unresolved_model_cue_does_not_silence_the_backstop() -> None:
    offered: list[tuple[tuple[str, tuple[str, ...]], ...]] = []

    def backstop(
        sentence: str, index: int, placed: tuple[tuple[str, tuple[str, ...]], ...]
    ) -> list[tuple[str, list[str]]]:
        offered.append(placed)
        return [] if placed else [("show", ["Spa"])]

    resolved: list[list[str]] = []

    def resolve(move: Move, args: list[str]) -> list[str] | None:
        resolved.append(args)
        return None if args == ["Nowhere"] else [a.upper() for a in args]

    drops: list[tuple[str, Dropped]] = []

    def on_drop(raw: RawCue, why: Dropped) -> None:
        drops.append((raw.args[0], why))

    stage, sent, _ = _stage(backstop=backstop, resolve=resolve, on_drop=on_drop)
    text = "{show: Nowhere} The spa opens at nine. {show: Rooms} Rooms are upstairs."
    _ = [e async for e in stage.cued(_turn(SpeechStart(), SpeechChunk(text), SpeechEnd()))]
    assert offered == [(), (("show", ("ROOMS",)),)]
    assert drops == [("Nowhere", "unresolved")]
    assert [(c.args, c.at) for c in sent if isinstance(c, StageCue)] == [
        (["SPA"], "The spa opens at nine. Rooms are"),
        (["ROOMS"], "Rooms are upstairs."),
    ]
    # Each of the model's cues was resolved once; the backstop's once, when sent.
    assert sorted(resolved) == [["Nowhere"], ["Rooms"], ["Spa"]]


async def test_a_cue_resolved_at_its_sentence_end_keeps_what_the_model_wrote(
    logs: list[str],
) -> None:
    """The page gets the resolved arguments; the brain — which shows the model
    its own cue back in a note — and the log get the cue as the model wrote it,
    so the model keeps imitating its own grammar, never the page's ids."""

    def resolve(move: Move, args: list[str]) -> list[str] | None:
        return ["tamano", "King", "/12-sabanas"] if args == ["Tamaño", "king"] else args

    seen: list[RawCue] = []

    class Watching(Stage):
        def cue(self, raw: RawCue) -> str | None:
            seen.append(raw)
            return super().cue(raw)

    sent: list[Action] = []
    stage = Watching(
        dispatch=sent.append,
        moves=(
            *MOVES[:2],
            Move(
                id="shop.filter",
                verb="filter",
                cls=MoveClass.REVERSIBLE,
                args=("facet", "value", "path"),
            ),
        ),
        resolve=resolve,
        backstop=lambda sentence, index, placed: [],
    )
    text = "{filter: Tamaño | king} First, the king size ones. Then the rest."
    _ = [e async for e in stage.cued(_turn(SpeechStart(), SpeechChunk(text), SpeechEnd()))]
    [raw] = seen
    assert raw.args == ("Tamaño", "king")
    assert raw.resolved == ("tamano", "King", "/12-sabanas")
    [cue] = [c for c in sent if isinstance(c, StageCue)]
    assert cue.args == ["tamano", "King", "/12-sabanas"]
    assert "cue {filter: Tamaño | king} as shop.filter" in "\n".join(logs)


async def test_a_backstop_rings_each_place_a_sentence_names_in_order() -> None:
    def backstop(
        sentence: str, index: int, placed: tuple[tuple[str, tuple[str, ...]], ...]
    ) -> list[tuple[str, list[str], int]]:
        names = ("Janca", "Quechua", "Suni", "Puna")
        return [("show", [n], sentence.index(n)) for n in names if n in sentence]

    stage, sent, _ = _stage(backstop=backstop)
    text = "The zones are Janca, then Quechua and Suni, and last of all Puna up high."
    _ = [e async for e in stage.cued(_turn(SpeechStart(), SpeechChunk(text), SpeechEnd()))]
    cues = [c for c in sent if isinstance(c, StageCue)]
    assert [c.args[0] for c in cues] == ["Janca", "Quechua", "Suni", "Puna"]
    assert [c.at.split()[0] for c in cues] == ["Janca,", "Quechua", "Suni,", "Puna"]
    assert [c.before for c in cues] == sorted(c.before for c in cues)


# ─── the log ───────────────────────────────────────────────────────────────


async def test_every_cue_drop_backstop_and_result_is_logged(logs: list[str]) -> None:
    def backstop(
        sentence: str, index: int, placed: tuple[tuple[str, tuple[str, ...]], ...]
    ) -> list[tuple[str, list[str]]]:
        return [] if placed or "spa" not in sentence else [("show", ["Spa"])]

    def resolve(move: Move, args: list[str]) -> list[str] | None:
        return None if args == ["Nowhere"] else args

    stage, _, _ = _stage(backstop=backstop, resolve=resolve)
    text = "{show: Rooms} Rooms are upstairs. {show: Nowhere} Hello there. The spa is open."
    _ = [e async for e in stage.cued(_turn(SpeechStart(), SpeechChunk(text), SpeechEnd()))]
    stage.handle(_result("c1", "core.show", fired="anchor", received_ms=900, lag_ms=120))
    joined = "\n".join(logs)
    assert "cue {show: Rooms} as core.show" in joined and "'Rooms are upstairs.'" in joined
    assert "dropped {show: Nowhere} (unresolved)" in joined
    assert "backstop sentence 0: none (the model placed show)" in joined
    assert "backstop sentence 1: none (nothing fits)" in joined
    assert "backstop sentence 2: added {show: Spa}" in joined
    assert "c1 core.show -> applied" in joined and "anchor" in joined and "lag 120" in joined
