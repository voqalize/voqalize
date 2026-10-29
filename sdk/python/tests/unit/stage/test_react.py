"""What the visitor does on the page, and how much the agent makes of it: as a
site declares, event by event — nothing, a line for the next turn, or a few
words of its own once they are quiet, now and then."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from voqalize.sdk.stage import REACT_GAP_S, Mirror, Stage, StageEvent, load_spec

SPEC: dict[str, Any] = {
    "stage": 1,
    "id": "shop",
    "moves": [],
    "slices": [
        {
            "id": "form",
            "fields": [{"name": "filled", "type": "array"}, {"name": "missing", "type": "integer"}],
        },
        {"id": "view", "fields": [{"name": "label"}]},
    ],
    "events": [
        {
            "id": "form.changed",
            "slice": "form",
            "op": "set",
            "note": "{by} filled part of the form; {missing} fields left",
            "react": "speak",
            "ask": "If they stopped with {missing} fields left, offer to help with them.",
        },
        {
            "id": "view.changed",
            "slice": "view",
            "op": "set",
            "note": "{by} is reading {label}",
            "react": "silent",
        },
    ],
}


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def _stage() -> tuple[Stage, Clock]:
    spec = load_spec(SPEC)
    clock = Clock()
    return Stage(
        dispatch=lambda _: None, moves=spec.move_set(), mirror=Mirror(spec), clock=clock
    ), clock


def _form(missing: int, by: str = "visitor") -> StageEvent:
    return StageEvent(name="form.changed", by=by, data={"filled": ["name"], "missing": missing})  # type: ignore[arg-type]


def test_a_silent_event_is_kept_and_never_said() -> None:
    stage, _ = _stage()
    folded = stage.handle(StageEvent(name="view.changed", data={"label": "Our rooms"}))
    assert folded is not None and folded.note is None and folded.ask is None
    assert stage.mirror is not None and stage.mirror.value("view") == {"label": "Our rooms"}
    assert stage.reaction() is None


def test_the_visitor_s_act_may_be_spoken_about_once_they_are_quiet_and_now_and_then() -> None:
    stage, clock = _stage()
    folded = stage.handle(_form(3))
    assert folded is not None
    assert folded.note == "[The visitor filled part of the form; 3 fields left]"
    assert folded.ask == "If they stopped with 3 fields left, offer to help with them."
    assert stage.take_reaction() == folded.ask
    assert stage.reaction() is None
    # Another act soon after: kept for later, not said yet.
    clock.t += 5
    stage.handle(_form(2))
    assert stage.reaction() is None
    clock.t += REACT_GAP_S
    assert stage.take_reaction() == "If they stopped with 2 fields left, offer to help with them."


def test_the_agent_s_own_act_and_the_visitor_s_words_are_never_spoken_about() -> None:
    stage, _ = _stage()
    stage.handle(_form(3, by="agent"))
    assert stage.reaction() is None
    stage.handle(_form(1))
    stage.visitor_spoke()
    assert stage.reaction() is None


def test_speak_needs_an_ask_and_only_speak_takes_one() -> None:
    form = SPEC["events"][0]
    with pytest.raises(ValidationError, match="say what about"):
        load_spec({**SPEC, "events": [{**form, "ask": ""}]})
    with pytest.raises(ValidationError, match="only for react 'speak'"):
        load_spec({**SPEC, "events": [{**form, "react": "note"}]})
    with pytest.raises(ValidationError, match=r"names \{email\}"):
        load_spec({**SPEC, "events": [{**form, "ask": "Read back {email}."}]})


def test_by_default_an_event_is_a_line_and_nothing_more() -> None:
    spec = load_spec(
        {**SPEC, "events": [{"id": "form.changed", "slice": "form", "note": "{by} typed"}]}
    )
    folded = Mirror(spec).fold(_form(1))
    assert folded is not None and folded.note == "[The visitor typed]" and folded.ask is None


def test_a_site_takes_the_watch_kit_and_chooses_what_speaks() -> None:
    spec = load_spec(
        {
            "stage": 1,
            "id": "lodge",
            "kits": [
                {
                    "id": "watch",
                    "major": 1,
                    "events": {
                        "form.changed": {
                            "react": "speak",
                            "ask": "If they paused with {left} fields left, offer to help.",
                        }
                    },
                }
            ],
        }
    )
    events = {e.id: e for e in spec.events}
    assert events["view.changed"].react == "silent"
    assert events["form.changed"].react == "speak"
    again = load_spec(spec.model_dump(mode="json", by_alias=True))
    assert again == spec
    stage = Stage(dispatch=lambda _: None, moves=spec.move_set(), mirror=Mirror(spec))
    folded = stage.handle(
        StageEvent(
            name="form.changed",
            data={
                "form": "Enquiry",
                "filled": ["name"],
                "missing": ["email"],
                "left": 1,
                "done": False,
            },
        )
    )
    assert folded is not None
    assert folded.note == "[The visitor is filling in Enquiry: 1 required fields left]"
    assert stage.take_reaction() == "If they paused with 1 fields left, offer to help."
    with pytest.raises(ValidationError, match="has no event"):
        load_spec(
            {
                "stage": 1,
                "id": "x",
                "kits": [{"id": "watch", "major": 1, "events": {"nope": {"react": "note"}}}],
            }
        )
