"""The director: cues out of a streaming turn, tool moves one at a time, and
exactly one final result per ``call_ref``."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest

from voqalize.sdk import Action
from voqalize.sdk.events import RTVIMessage, RTVIType, Speech, SpeechChunk, SpeechEnd, SpeechStart
from voqalize.sdk.stage import (
    CUE_WAIT_S,
    RESULT_TIMEOUTS,
    STAGE_CONTRACT,
    Dropped,
    Move,
    MoveClass,
    RawCue,
    Refused,
    Stage,
    StageCue,
    StageHello,
    StageMove,
    StagePageEvents,
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


# ─── tool moves ─────────────────────────────────────────────────────────────


def test_a_look_move_is_sent_at_once_and_never_blocks() -> None:
    stage, sent, _ = _stage()
    assert stage.send("core.show", {"target": "Rooms"}) == "c1"
    assert stage.send("core.show", {"target": "Rooms"}) == "c2"
    assert stage.busy is None
    assert sent == [
        StageMove(call_ref="c1", move="core.show", args={"target": "Rooms"}),
        StageMove(call_ref="c2", move="core.show", args={"target": "Rooms"}),
    ]


def test_serial_moves_go_one_at_a_time_and_the_queued_one_follows() -> None:
    stage, sent, _ = _stage()
    assert stage.send("core.page", {"path": "/rooms"}) == "c1"
    assert stage.busy == "core.page"
    assert stage.send("cart.add", {"product": "p1"}, when="quiet") is None
    assert stage.queued == "cart.add" and len(sent) == 1
    # A newer move replaces the queued one.
    assert stage.send("shop.filter", {"facet": "size", "value": "L"}) is None
    assert stage.queued == "shop.filter"
    got = stage.handle(_result("c1", "core.page", detail="Rooms open"))
    assert got is not None and got.detail == "Rooms open"
    assert sent[-1] == StageMove(
        call_ref="c2", move="shop.filter", args={"facet": "size", "value": "L"}
    )
    assert stage.busy == "shop.filter" and stage.queued is None


def test_an_identical_repeat_is_refused() -> None:
    stage, _, _ = _stage()
    stage.send("core.page", {"path": "/rooms"})
    with pytest.raises(Refused) as running:
        stage.send("core.page", {"path": "/rooms"})
    assert (running.value.why, running.value.call_ref) == ("running", "c1")
    stage.send("cart.add", {"product": "p1"})
    with pytest.raises(Refused) as queued:
        stage.send("cart.add", {"product": "p1"})
    assert (queued.value.why, queued.value.call_ref) == ("queued", None)
    # Different arguments are a different move.
    assert stage.send("core.page", {"path": "/spa"}) is None


def test_an_unknown_move_raises() -> None:
    stage, _, _ = _stage()
    with pytest.raises(KeyError):
        stage.send("core.nope", {})


def test_the_queued_move_is_dropped_when_the_running_one_did_not_land() -> None:
    stage, sent, _ = _stage()
    stage.send("core.page", {"path": "/rooms"})
    stage.send("cart.add", {"product": "p1"})
    got = stage.handle(_result("c1", "core.page", "failed", detail="no such page"))
    assert got is not None and got.outcome == "failed"
    assert got.detail == "no such page (so cart.add, asked for while it ran, was not sent)"
    assert len(sent) == 1 and stage.busy is None and stage.queued is None


def test_results_are_deduplicated() -> None:
    stage, _, _ = _stage()
    stage.send("core.show", {"target": "Rooms"})
    assert stage.handle(_result("c1", "core.show")) is not None
    assert stage.handle(_result("c1", "core.show")) is None
    assert stage.handle(_result("c99", "core.show")) is None
    assert stage.move_of("c1") == MOVES[0]


def test_a_moved_result_is_interim() -> None:
    stage, _, clock = _stage()
    stage.send("core.page", {"path": "/rooms"})
    clock.t += 15
    interim = stage.handle(_result("c1", "core.page", moved=True))
    assert interim is not None and interim.moved
    assert stage.busy == "core.page"
    clock.t += 15  # 30 s after sending, 15 after it moved: still in time.
    assert stage.expire() == []
    final = stage.handle(_result("c1", "core.page"))
    assert final is not None and not final.moved and stage.busy is None


def test_expire_reports_unknown_and_frees_the_queue() -> None:
    stage, sent, clock = _stage(result_timeout_s=20.0)
    stage.send("core.page", {"path": "/rooms"})
    stage.send("cart.add", {"product": "p1"})
    clock.t += 19.9
    assert stage.expire() == []
    clock.t += 0.2
    assert stage.busy is None
    [late] = stage.expire()
    assert (late.call_ref, late.move, late.outcome) == ("c1", "core.page", "unknown")
    assert late.detail is not None and "cart.add" in late.detail
    assert stage.queued is None and len(sent) == 1
    # Its answer, arriving after, corrects the unknown once, marked late, and
    # sends nothing that was dropped; a second copy is a duplicate.
    corrected = stage.handle(_result("c1", "core.page", detail="Rooms open"))
    assert corrected is not None and corrected.late and corrected.outcome == "applied"
    assert len(sent) == 1
    assert stage.handle(_result("c1", "core.page")) is None


# ─── an app's own action runner: queue=False and abandon ─────────────────────


def test_unqueued_moves_are_sent_now_even_behind_a_running_serial_move() -> None:
    stage, sent, _ = _stage()
    assert stage.send("core.page", {"path": "/rooms"}) == "c1"
    # Serial, with a serial move running: sent anyway, never queued.
    assert stage.send("cart.add", {"product": "p1"}, queue=False) == "c2"
    # The exact move already running: sent again, never refused.
    assert stage.send("cart.add", {"product": "p1"}, queue=False) == "c3"
    assert stage.queued is None
    assert [a.call_ref for a in sent if isinstance(a, StageMove)] == ["c1", "c2", "c3"]
    assert [r.call_ref for r in stage.running()] == ["c1", "c2", "c3"]


def test_an_unqueued_serial_move_holds_the_queue_like_any_running_move() -> None:
    stage, sent, _ = _stage()
    stage.send("core.page", {"path": "/rooms"})
    stage.send("cart.add", {"product": "p1"}, queue=False)
    assert stage.busy == "cart.add"
    # A queued send waits behind the newest serial move, the unqueued one,
    # and is refused for exactly it.
    with pytest.raises(Refused):
        stage.send("cart.add", {"product": "p1"})
    assert stage.send("shop.filter", {"facet": "size", "value": "L"}) is None
    assert stage.queued == "shop.filter"
    # The overtaken move lands: still answered, but it no longer holds the queue.
    got = stage.handle(_result("c1", "core.page"))
    assert got is not None and got.outcome == "applied" and len(sent) == 2
    assert stage.queued == "shop.filter"
    assert stage.handle(_result("c2", "cart.add")) is not None
    assert sent[-1] == StageMove(
        call_ref="c3", move="shop.filter", args={"facet": "size", "value": "L"}
    )


def test_an_unqueued_move_is_timed_and_answered_like_any_other() -> None:
    stage, _, clock = _stage(result_timeout_s=20.0)
    ref = stage.send("shop.filter", {"facet": "size", "value": "L"}, queue=False)
    got = stage.handle(_result(ref, "shop.filter", detail="8 products"))
    assert got is not None and got.detail == "8 products" and stage.running() == []
    ref = stage.send("shop.filter", {"facet": "size", "value": "M"}, queue=False)
    clock.t += 20.1
    [unknown] = stage.expire()
    assert (unknown.call_ref, unknown.outcome) == (ref, "unknown")


async def test_an_unqueued_move_keeps_the_turn_s_promise() -> None:
    told: list[str] = []
    claimed = Move(
        id="cart.add", verb=None, cls=MoveClass.CONFIRMED, args=("product",), claims=("adding it",)
    )
    stage = Stage(
        dispatch=lambda _: None,
        moves=(*MOVES[:3], claimed),
        on_unkept=lambda move, phrase, sentence: told.append(move.id),
    )
    said = "I'm adding it to your cart."
    [_ async for _ in stage.cued(_turn(SpeechStart(), SpeechChunk(said), SpeechEnd()))]
    ref = stage.send("cart.add", {"product": "p1"}, queue=False)
    stage.handle(_result(ref, "cart.add"))
    assert stage.end_turn() == [] and told == []
    # The same words in a turn that sends nothing are a promise not kept.
    [_ async for _ in stage.cued(_turn(SpeechStart(), SpeechChunk(said), SpeechEnd()))]
    assert [u.move.id for u in stage.end_turn()] == ["cart.add"] and told == ["cart.add"]


def test_abandon_reports_unknown_now_and_the_answer_after_comes_back_late() -> None:
    stage, sent, _ = _stage()
    ref = stage.send("core.page", {"path": "/rooms"}, queue=False)
    stage.send("cart.add", {"product": "p1"})
    assert stage.queued == "cart.add"
    got = stage.abandon(ref, "the app's runner timed out")
    assert got is not None and (got.call_ref, got.move, got.outcome) == (
        ref,
        "core.page",
        "unknown",
    )
    # Settled as an expiry settles it: the queued move behind it is dropped.
    assert got.detail == (
        "the app's runner timed out (so cart.add, asked for while it ran, was not sent)"
    )
    assert stage.busy is None and stage.queued is None and len(sent) == 1
    late = stage.handle(_result(ref, "core.page", detail="Rooms open"))
    assert late is not None and late.late and late.outcome == "applied"
    assert stage.handle(_result(ref, "core.page")) is None


def test_abandon_without_a_detail_says_the_app_stopped_waiting() -> None:
    stage, _, _ = _stage()
    ref = stage.send("core.show", {"target": "Rooms"})
    assert ref is not None
    got = stage.abandon(ref)
    assert got is not None and got.detail == "the app stopped waiting for it"


def test_abandon_of_a_move_not_in_flight_is_none() -> None:
    stage, _, clock = _stage(result_timeout_s=20.0)
    assert stage.abandon("c99") is None
    answered = stage.send("core.show", {"target": "Rooms"}, queue=False)
    stage.handle(_result(answered, "core.show"))
    assert stage.abandon(answered) is None
    expired = stage.send("core.show", {"target": "Spa"}, queue=False)
    clock.t += 20.1
    assert len(stage.expire()) == 1
    assert stage.abandon(expired) is None
    abandoned = stage.send("core.show", {"target": "Bar"}, queue=False)
    assert stage.abandon(abandoned) is not None
    assert stage.abandon(abandoned) is None


def test_abandon_leaves_every_other_move_in_flight() -> None:
    stage, _, clock = _stage(result_timeout_s=20.0)
    a = stage.send("core.show", {"target": "Rooms"}, queue=False)
    b = stage.send("core.page", {"path": "/rooms"}, queue=False)
    clock.t += 25  # both overdue; abandon reports only the one it names
    got = stage.abandon(a)
    assert got is not None and got.call_ref == a
    assert [r.call_ref for r in stage.running()] == [b]
    assert stage.busy is None  # past its time, but still for expire to report
    [expired] = stage.expire()
    assert expired.call_ref == b and expired.detail == "the page did not answer in time"


def test_a_hello_is_kept_and_not_a_result() -> None:
    stage, _, _ = _stage()
    hello = StageHello(runtime="test", contract=STAGE_CONTRACT, url="https://x.test/")
    assert stage.handle(hello) is None and stage.hello == hello


def test_a_hello_with_no_title_and_no_query_parses_and_is_kept() -> None:
    # What @voqalize/stage sends by default: origin and path, no title.
    msg = RTVIMessage(
        type=RTVIType.UI_EVENT,
        data={
            "event": "stage_hello",
            "payload": {
                "runtime": "@voqalize/stage",
                "contract": STAGE_CONTRACT,
                "url": "https://x.test/orders",
            },
        },
    )
    hello = StagePageEvents.parse(msg)
    assert isinstance(hello, StageHello) and hello.title == ""
    stage, _, _ = _stage()
    assert stage.handle(hello) is None and stage.hello == hello
    bare = StageHello.model_validate({"runtime": "x", "contract": STAGE_CONTRACT})
    assert bare.url == "" and bare.title == ""


# ─── cues ───────────────────────────────────────────────────────────────────


async def _turn(*events: Speech) -> AsyncGenerator[Speech, None]:
    for e in events:
        yield e


async def test_cued_strips_cues_and_dispatches_them_with_fresh_call_refs() -> None:
    def resolve(move: Move, args: list[str]) -> list[str] | None:
        if args == ["Nowhere"]:
            return None
        return [a.upper() for a in args]

    stage, sent, _ = _stage(resolve=resolve)
    turn = _turn(
        SpeechStart(),
        SpeechChunk("{show: Rooms} Our rooms look "),
        SpeechChunk("out on the bay. {show: Nowhere} Truly. {filter: size|L}"),
        SpeechEnd(),
        SpeechStart(),
        SpeechChunk("{page: /spa} The spa is next door."),
        SpeechEnd(),
    )
    out = [e async for e in stage.cued(turn)]
    spoken = "".join(e.text for e in out if isinstance(e, SpeechChunk))
    assert spoken == " Our rooms look out on the bay. Truly.  The spa is next door."
    assert [type(e) for e in out if not isinstance(e, SpeechChunk)] == [
        SpeechStart,
        SpeechEnd,
        SpeechStart,
        SpeechEnd,
    ]
    assert sent == [
        StageCue(
            call_ref="c1",
            move="core.show",
            verb="show",
            args=["ROOMS"],
            at="Our rooms look",
            before=0,
        ),
        StageCue(
            call_ref="c2", move="shop.filter", verb="filter", args=["SIZE", "L"], at="", before=39
        ),
        StageCue(
            call_ref="c3",
            move="core.page",
            verb="page",
            args=["/SPA"],
            at="The spa is next",
            before=0,
            unit=1,
        ),
    ]
    # Cues are in flight, and answered like any move, but never block a tool.
    assert stage.busy is None
    assert stage.handle(_result("c1", "core.show")) is not None


async def test_a_cue_with_more_args_than_its_move_is_dropped() -> None:
    stage, sent, _ = _stage()
    out = [
        e
        async for e in stage.cued(_turn(SpeechStart(), SpeechChunk("{show: a|b} Hi."), SpeechEnd()))
    ]
    assert sent == [] and "".join(e.text for e in out if isinstance(e, SpeechChunk)) == " Hi."


async def test_a_cue_expires_after_the_page_wait_and_the_timeout() -> None:
    stage, _, clock = _stage(result_timeout_s=20.0)
    _ = [
        e
        async for e in stage.cued(
            _turn(SpeechStart(), SpeechChunk("{show: Rooms} Hi."), SpeechEnd())
        )
    ]
    clock.t += CUE_WAIT_S + 19
    assert stage.expire() == []
    clock.t += 2
    assert [r.outcome for r in stage.expire()] == ["unknown"]


async def test_the_backstop_reaches_the_parser() -> None:
    def backstop(
        sentence: str, index: int, placed: tuple[tuple[str, tuple[str, ...]], ...]
    ) -> list[tuple[str, list[str]]]:
        return [] if placed else [("show", ["Spa"])]

    stage, sent, _ = _stage(backstop=backstop)
    _ = [
        e
        async for e in stage.cued(
            _turn(SpeechStart(), SpeechChunk("The spa opens at nine."), SpeechEnd())
        )
    ]
    assert [(c.args, c.at) for c in sent if isinstance(c, StageCue)] == [
        (["Spa"], "The spa opens at nine.")
    ]


# ─── timeouts by class, drops, carried moves ────────────────────────────────


def test_the_default_timeouts_go_by_class() -> None:
    stage, _, clock = _stage()
    stage.send("core.show", {"target": "Rooms"})
    stage.send("core.page", {"path": "/rooms"})
    clock.t += RESULT_TIMEOUTS[MoveClass.LOOK] + 0.1
    assert [r.move for r in stage.expire()] == ["core.show"]
    clock.t += RESULT_TIMEOUTS[MoveClass.NAVIGATE] - RESULT_TIMEOUTS[MoveClass.LOOK]
    assert [r.move for r in stage.expire()] == ["core.page"]
    assert RESULT_TIMEOUTS[MoveClass.NAVIGATE] > RESULT_TIMEOUTS[MoveClass.LOOK]


def test_a_timeout_mapping_overrides_some_classes_and_keeps_the_rest() -> None:
    stage, _, _ = _stage(result_timeout_s={MoveClass.CONFIRMED: 45.0})
    assert stage.timeout(MoveClass.CONFIRMED) == 45.0
    assert stage.timeout(MoveClass.NAVIGATE) == RESULT_TIMEOUTS[MoveClass.NAVIGATE]
    flat, _, _ = _stage(result_timeout_s=12.0)
    assert {flat.timeout(c) for c in MoveClass} == {12.0}


async def test_every_dropped_cue_is_told_with_why() -> None:
    drops: list[tuple[str, tuple[str, ...], str]] = []

    def on_drop(raw: RawCue, why: Dropped) -> None:
        drops.append((raw.verb, raw.args, why))

    def resolve(move: Move, args: list[str]) -> list[str] | None:
        return None if args == ["Nowhere"] else args

    stage, sent, _ = _stage(resolve=resolve, on_drop=on_drop)
    text = "{show: Nowhere} One. {dance: now} Two. {show: a|b} Three. {show: Rooms} Four."
    out = [e async for e in stage.cued(_turn(SpeechStart(), SpeechChunk(text), SpeechEnd()))]
    assert "dance" not in "".join(e.text for e in out if isinstance(e, SpeechChunk))
    assert sorted(drops) == sorted(
        [
            ("show", ("Nowhere",), "unresolved"),
            ("dance", ("now",), "unknown_verb"),
            ("show", ("a", "b"), "too_many_args"),
        ]
    )
    assert [c.args for c in sent if isinstance(c, StageCue)] == [["Rooms"]]


def test_a_carried_move_is_answered_under_its_own_id() -> None:
    stage, _, clock = _stage()
    assert stage.send("core.page", {"path": "/rooms"}) == "c1"
    # The page went on to the next one: interim, its time started again.
    clock.t += 20
    assert stage.handle(_result("c1", "core.page", moved=True)) is not None
    clock.t += 20
    assert stage.expire() == []
    # The next page finished it with a performer of its own: still core.page.
    final = stage.handle(_result("c1", "site.arrive", detail="opened /rooms"))
    assert final is not None and final.move == "core.page" and stage.busy is None
