"""``voqalize stage check``: what loads but would fail in a call."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from voqalize.sdk.cli import main
from voqalize.sdk.stage import check as check_module
from voqalize.sdk.stage import load_spec
from voqalize.sdk.stage.check import check_spec

GOOD: dict[str, Any] = {
    "stage": 1,
    "id": "shop",
    "moves": [
        {
            "id": "core.show",
            "verb": "show",
            "class": "look",
            "args": [{"name": "target"}],
            "say": "{show: Heading} rings it.",
        },
        {
            "id": "listing.sort",
            "verb": "sort",
            "class": "reversible",
            "args": [{"name": "order", "enum": ["price_asc"]}],
            "say": "{sort: price_asc} sorts it.",
        },
        {"id": "cart.add", "class": "confirmed", "args": [{"name": "path"}], "objects": ["cart"]},
    ],
    "slices": [{"id": "cart", "fields": [{"name": "count", "type": "integer"}]}],
    "events": [{"id": "cart.changed", "slice": "cart"}],
}


def _moves(*moves: dict[str, Any]) -> dict[str, Any]:
    return {**GOOD, "moves": list(moves)}


def _messages(spec: dict[str, Any]) -> list[str]:
    return [str(f) for f in check_spec(load_spec(spec))]


def test_a_good_spec_has_nothing_to_say() -> None:
    assert _messages(GOOD) == []


def test_the_real_guard_runs_on_every_cue(monkeypatch: pytest.MonkeyPatch) -> None:
    """A guard that took a cue for a call would hold the reply back: the check
    asks the SDK's own guard, so a change to it fails here, not in a call."""
    monkeypatch.setattr(check_module, "_looks_like_call", lambda text: "{sort" in text or None)
    found = _messages(GOOD)
    assert any("error: listing.sort: a reply opening with '{sort: price_asc}'" in m for m in found)
    assert any("core.show" in m and "held until more comes" in m for m in found)


def test_a_cue_nobody_is_taught_or_taught_wrong() -> None:
    show = {**GOOD["moves"][0]}
    untaught = _messages(_moves({**show, "say": ""}))
    assert untaught == ["warning: core.show: no say line: the model is never taught {show: …}"]
    elsewhere = _messages(_moves({**show, "say": "{ring: Heading} rings it."}))
    assert "warning: core.show: its say line never writes {show: …}" in elsewhere[0]
    assert (
        "error: core.show: its say line teaches {ring: …}, which no move declares" in elsewhere[1]
    )


def test_a_change_with_nothing_to_catch_its_promise() -> None:
    bare = {"id": "cart.add", "class": "confirmed"}
    assert _messages(_moves(bare)) == [
        "warning: cart.add: a move that changes the page with no claims or objects: a reply "
        "promising it and never sending it goes unnoticed"
    ]
    assert _messages(_moves({"id": "tab.focus", "class": "look"})) == []


def test_the_prompt_budget_and_an_unfilled_slice() -> None:
    long = {**GOOD["moves"][0], "say": "{show: Heading} " + "x" * 4000}
    spec = {**_moves(long), "events": []}
    found = [str(f) for f in check_spec(load_spec(spec), budget_tokens=500)]
    assert (
        "warning: spec: the cue lines take about 1004 tokens in every request; the budget is 500"
        in found
    )
    assert "warning: cart: no event changes this slice: it always reads unknown" in found


def test_the_cli_fails_on_an_error_and_on_a_warning_when_strict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    good, warned, bad = tmp_path / "good.json", tmp_path / "warned.json", tmp_path / "bad.json"
    good.write_text(json.dumps(GOOD))
    warned.write_text(json.dumps(_moves({"id": "cart.add", "class": "confirmed"})))
    bad.write_text(json.dumps(_moves({**GOOD["moves"][0], "say": "{ring: x}"})))
    assert main(["stage", "check", str(good)]) == 0
    assert main(["stage", "check", str(warned)]) == 0
    assert main(["stage", "check", "--strict", str(warned)]) == 1
    assert main(["stage", "check", str(bad)]) == 1
    assert "1 error, 1 warning" in capsys.readouterr().out
