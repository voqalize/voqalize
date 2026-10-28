"""The landing line: the moment the page shows what a move did, the brain gets
one written line to say at once, and the move is no longer taken for a slow
one."""

from __future__ import annotations

from voqalize.sdk import Action
from voqalize.sdk.stage import (
    LANDED_AFTER_RESULT_S,
    LANDING_LINE_KEEP_S,
    Landing,
    Move,
    MoveClass,
    RawCue,
    Stage,
    StageResult,
    landed_ask,
)

FILTER = Move(id="shop.filter", verb=None, cls=MoveClass.REVERSIBLE, args=("size",))
CUE = Move(id="shop.cue", verb="filter", cls=MoveClass.REVERSIBLE, args=("facet", "value"))
ADD = Move(id="shop.add", verb=None, cls=MoveClass.CONFIRMED, args=("path",))


def _cue(verb: str, *args: str) -> RawCue:
    return RawCue(verb=verb, args=args, at="", before=0)


class Clock:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


def _stage(line: str | None = "Here are 16.") -> tuple[Stage, list[Landing], Clock]:
    asked: list[Landing] = []
    clock = Clock()
    sent: list[Action] = []

    def on_landed(landing: Landing) -> str | None:
        asked.append(landing)
        return line

    stage = Stage(dispatch=sent.append, moves=(FILTER, CUE, ADD), on_landed=on_landed, clock=clock)
    return stage, asked, clock


def test_a_site_event_for_the_running_move_gives_its_line_once() -> None:
    stage, asked, clock = _stage()
    ref = stage.send("shop.filter", {"size": "king"})
    assert ref is not None
    clock.t += 4.3
    shown = object()
    assert stage.landed(("shop.filter", "shop.cue"), event=shown) == "Here are 16."
    [landing] = asked
    assert landing.move is FILTER
    assert landing.call_ref == ref
    assert landing.event is shown
    assert landing.result is None
    assert round(landing.seconds, 1) == 4.3
    # Once a move: the same event again says nothing more.
    assert stage.landed("shop.filter", event=shown) is None
    assert len(asked) == 1
    # Waiting for the brain's next floor, then gone.
    assert stage.lines_waiting
    assert stage.take_lines() == ["Here are 16."]
    assert stage.take_lines() == []


def test_no_line_for_a_move_not_running() -> None:
    stage, asked, _ = _stage()
    # The visitor filtered by themselves: nothing of his is running.
    assert stage.landed("shop.filter", event=object()) is None
    assert asked == []


def test_a_shown_move_gets_no_holding_line_and_its_result_adds_nothing() -> None:
    stage, asked, clock = _stage()
    ref = stage.send("shop.filter", {"size": "king"})
    assert ref is not None
    stage.landed("shop.filter", event=object())
    clock.t += 15.0  # past the holding time, within the result's
    assert stage.holding(after_s=6.0) == []
    [running] = stage.running()
    assert running.shown
    got = stage.handle(StageResult(call_ref=ref, move="shop.filter", outcome="applied"))
    assert got is not None
    assert stage.shown(ref)
    # Not asked again by the result.
    assert len(asked) == 1


def test_an_event_that_does_not_fit_the_move_is_not_its_landing() -> None:
    stage, asked, _ = _stage()
    ref = stage.send("shop.filter", {"size": "king"})
    # A load shows the listing unfiltered first: not the filter's effect.
    unfiltered = {"size": None}
    filtered = {"size": "King"}

    def fits(landing: Landing, shown: dict[str, str | None]) -> bool:
        assert landing.args is not None
        return shown["size"] is not None and shown["size"].lower() == landing.args["size"]

    assert stage.landed("shop.filter", event=unfiltered, fits=lambda x: fits(x, unfiltered)) is None
    assert asked == []
    assert not stage.running()[0].shown
    assert stage.landed("shop.filter", event=filtered, fits=lambda x: fits(x, filtered)) == (
        "Here are 16."
    )
    assert asked[0].call_ref == ref
    # A cue's landing carries its arguments as sent.
    cue = stage.cue(_cue("filter", "tamano", "King"))
    stage.landed("shop.cue", event=filtered, fits=lambda x: x.cue_args == ("tamano", "King"))
    assert asked[-1].call_ref == cue


def test_a_result_with_no_line_from_the_brain_is_only_answered() -> None:
    stage, asked, _ = _stage(None)
    ref = stage.send("shop.add", {"path": "/x.html"})
    assert ref is not None
    stage.handle(StageResult(call_ref=ref, move="shop.add", outcome="applied"))
    assert len(asked) == 1
    # Nothing was said for it: its result is the brain's to talk through.
    assert not stage.shown(ref)


def test_an_applied_result_is_a_landing_when_no_event_came_first() -> None:
    stage, asked, _ = _stage("Done.")
    ref = stage.send("shop.add", {"path": "/x.html"})
    assert ref is not None
    stage.handle(StageResult(call_ref=ref, move="shop.add", outcome="applied", detail="added"))
    [landing] = asked
    assert landing.result is not None
    assert landing.result.detail == "added"
    assert stage.take_lines() == ["Done."]


def test_a_failed_or_partial_result_is_no_landing() -> None:
    stage, asked, _ = _stage()
    ref = stage.send("shop.filter", {"size": "king"})
    assert ref is not None
    stage.handle(StageResult(call_ref=ref, move="shop.filter", outcome="failed"))
    ref = stage.send("shop.filter", {"size": "queen"})
    assert ref is not None
    stage.handle(StageResult(call_ref=ref, move="shop.filter", outcome="partial"))
    assert asked == []
    assert not stage.shown(ref)


def test_a_cue_lands_too() -> None:
    stage, asked, _ = _stage()
    ref = stage.cue(_cue("filter", "Tamaño", "King"))
    assert ref is not None
    assert stage.landed(("shop.filter", "shop.cue"), event=object()) == "Here are 16."
    assert asked[0].move is CUE


def test_no_line_from_the_brain_keeps_nothing() -> None:
    stage, asked, _ = _stage(None)
    stage.send("shop.filter", {"size": "king"})
    assert stage.landed("shop.filter", event=object()) is None
    assert len(asked) == 1
    assert stage.take_lines() == []
    # Still shown: no holding line for it.
    assert stage.running()[0].shown


def test_an_old_line_is_let_go() -> None:
    stage, _, clock = _stage()
    stage.send("shop.filter", {"size": "king"})
    stage.landed("shop.filter", event=object())
    clock.t += LANDING_LINE_KEEP_S + 1
    assert stage.take_lines() == []


def test_the_newest_running_move_is_the_one_shown() -> None:
    stage, asked, clock = _stage()
    first = stage.cue(_cue("filter", "Tamaño", "King"))
    clock.t += 1
    second = stage.cue(_cue("filter", "Color", "Blanco"))
    stage.landed("shop.cue", event=object())
    assert asked[0].call_ref == second
    # By its call_ref, the other.
    stage.landed("shop.cue", event=object(), call_ref=first)
    assert asked[1].call_ref == first


def test_the_ask_after_a_landing_line_never_repeats_it() -> None:
    ask = landed_ask("Here are 16.")
    assert '"Here are 16."' in ask
    assert "at most one short sentence" in ask


def test_an_event_just_behind_its_applied_result_is_still_its_landing() -> None:
    stage, asked, clock = _stage()
    ref = stage.send("shop.filter", {"size": "king"})
    assert ref is not None
    # The page answered a moment before the event that shows it.
    asked_line = "Here are 16."
    stage._on_landed = lambda landing: None if landing.result is not None else asked_line  # type: ignore[attr-defined]
    stage.handle(StageResult(call_ref=ref, move="shop.filter", outcome="applied"))
    assert not stage.shown(ref)
    clock.t += 1.0
    assert stage.landed("shop.filter", event=object()) == "Here are 16."
    assert stage.shown(ref)
    # Once.
    assert stage.landed("shop.filter", event=object()) is None
    # Long after its result, an event is the visitor's, not this move's.
    ref = stage.send("shop.filter", {"size": "queen"})
    assert ref is not None
    stage.handle(StageResult(call_ref=ref, move="shop.filter", outcome="applied"))
    clock.t += LANDED_AFTER_RESULT_S + 1
    assert stage.landed("shop.filter", event=object()) is None
    assert asked == []
