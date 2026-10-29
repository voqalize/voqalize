"""The Stage Spec: one declaration of a move, read by the brain and the page."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from voqalize.sdk.cli import main
from voqalize.sdk.stage import MoveClass, MoveSet, StageSpec, load_spec, spec_schema
from voqalize.sdk.stage.gen import render_prompt, render_python, render_typescript

SCHEMA = Path(__file__).parents[4] / "js" / "stage" / "stage.schema.json"

SPEC: dict[str, Any] = {
    "$schema": "stage.schema.json",
    "stage": 1,
    "id": "shop",
    "languages": ["en", "es"],
    "moves": [
        {
            "id": "core.show",
            "verb": "show",
            "class": "look",
            "args": [{"name": "target", "doc": 'A heading, as the page writes it: "Rooms".'}],
            "say": "{show: Heading} scrolls to it.",
        },
        {
            "id": "shop.filter",
            "class": "reversible",
            "args": [
                {"name": "category_path"},
                {"name": "color", "type": "array", "optional": True},
                {"name": "sort", "enum": ["price_asc", "price_desc"], "optional": True},
                {"name": "qty", "type": "integer", "default": 1},
            ],
            "claims": ["filtering the * listing"],
            "objects": ["filter", "filtro"],
            "doc": "Filter a listing.",
            "notes": ["Dev call 1: why it is so."],
        },
        {"id": "shop.checkout", "class": "confirmed"},
    ],
}


def _spec(**changes: Any) -> dict[str, Any]:
    return {**SPEC, **changes}


def test_a_spec_becomes_the_moves_the_director_runs() -> None:
    spec = load_spec(SPEC)
    moves = spec.move_set()
    assert isinstance(moves, MoveSet)
    assert moves.verbs == frozenset({"show"})
    assert moves["shop.filter"].cls is MoveClass.REVERSIBLE
    assert moves["shop.filter"].args == ("category_path", "color", "sort", "qty")
    assert moves["shop.filter"].objects == ("filter", "filtro")
    assert spec.prompt_lines() == ("{show: Heading} scrolls to it.",)


def test_a_spec_loads_from_a_file_or_text(tmp_path: Path) -> None:
    path = tmp_path / "scene.json"
    path.write_text(json.dumps(SPEC))
    assert load_spec(path) == load_spec(str(path)) == load_spec(json.dumps(SPEC))


@pytest.mark.parametrize(
    ("change", "why"),
    [
        ({"verb": "Show"}, "one lowercase word"),
        ({"verb": "name"}, "names a function call"),
        ({"args": [{"name": x} for x in "abcde"]}, "a cue carries at most 4"),
        ({"args": [{"name": "a", "type": "array"}]}, "a cue's arguments are words"),
        ({"args": [{"name": "a"}, {"name": "a"}]}, "names an argument twice"),
        (
            {"args": [{"name": "a", "type": "integer", "enum": ["1"]}]},
            "only a string takes an enum",
        ),
        ({"args": [{"name": "a", "optional": True, "default": "x"}]}, "drop 'optional'"),
        ({"class": "confirmed"}, "only ever made by a tool"),
        ({"class": "commit"}, "class"),
        ({"surprise": 1}, "surprise"),
    ],
)
def test_a_bad_move_fails_when_the_spec_is_loaded(change: dict[str, Any], why: str) -> None:
    show = {**SPEC["moves"][0], **change}
    with pytest.raises(ValidationError, match=why):
        load_spec(_spec(moves=[show]))


def test_one_id_or_one_verb_twice_is_refused() -> None:
    show = SPEC["moves"][0]
    with pytest.raises(ValidationError, match="two moves have the id"):
        load_spec(_spec(moves=[show, show]))
    with pytest.raises(ValidationError, match="share the verb"):
        load_spec(_spec(moves=[show, {**show, "id": "core.show2"}]))


def test_the_hash_ignores_where_the_schema_is_and_follows_the_moves() -> None:
    a = load_spec(SPEC)
    assert a.sha256 == load_spec(_spec(**{"$schema": "elsewhere.json"})).sha256
    assert a.sha256 != load_spec(_spec(id="other")).sha256


def test_the_schema_on_disk_is_the_one_the_model_makes() -> None:
    """``stage.schema.json`` is generated, never edited: regenerate it with
    ``voqalize stage schema -o sdk/js/stage/stage.schema.json``."""
    assert json.loads(SCHEMA.read_text()) == spec_schema()


def test_the_generated_python_runs_and_types_the_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = load_spec(SPEC)
    text = render_python(spec, source="scene.json", command="voqalize stage gen scene.json")
    module = types.ModuleType("stage_gen_under_test")
    monkeypatch.setitem(sys.modules, module.__name__, module)
    exec(compile(text, "stage_gen.py", "exec"), module.__dict__)
    assert spec.sha256 == module.SPEC_SHA256
    assert [m.id for m in module.MOVES] == ["core.show", "shop.filter", "shop.checkout"]
    assert spec.get("shop.filter").move() == module.FILTER
    args = module.FilterArgs
    assert issubclass(args, BaseModel)
    assert args(category_path="/s").model_dump() == {
        "category_path": "/s",
        "color": None,
        "sort": None,
        "qty": 1,
    }
    with pytest.raises(ValidationError):
        args(category_path="/s", sort="cheapest")
    assert "# Dev call 1: why it is so." in text
    # A doc with double quotes in it is written in single quotes, as ruff would.
    assert "'A heading, as the page writes it: \"Rooms\".'" not in text
    assert '"""A heading, as the page writes it: "Rooms"."""' in text
    assert module.CheckoutArgs().model_dump() == {}


def test_the_typescript_keeps_only_what_the_page_reads() -> None:
    text = render_typescript(load_spec(SPEC), source="scene.json", command="c")
    body = json.loads(text.split("defineScene(", 1)[1].rsplit(");", 1)[0].split(");\n")[0])
    assert [m["id"] for m in body["moves"]] == ["core.show", "shop.filter", "shop.checkout"]
    for gone in ("claims", "objects", "say", "doc", "notes"):
        assert all(gone not in m for m in body["moves"]), gone
    assert "doc" not in body["moves"][0]["args"][0]
    assert "languages" not in body
    assert 'import { defineScene } from "@voqalize/stage";' in text


def test_the_prompt_lines_are_the_cues_say_lines() -> None:
    assert render_prompt(load_spec(SPEC)) == "{show: Heading} scrolls to it.\n"


def test_the_cli_writes_all_three_and_checks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    spec = tmp_path / "scene.json"
    spec.write_text(json.dumps(SPEC))
    py, ts, prompt = tmp_path / "gen.py", tmp_path / "scene.gen.ts", tmp_path / "cues.txt"
    assert (
        main(["stage", "gen", str(spec), "--py", str(py), "--ts", str(ts), "--prompt", str(prompt)])
        == 0
    )
    assert "MOVES = MoveSet(" in py.read_text()
    assert "defineScene(" in ts.read_text()
    assert prompt.read_text().startswith("{show:")
    assert main(["stage", "check", str(spec)]) == 0
    assert "3 moves, 1 cue" in capsys.readouterr().out
    assert main(["types", "--scene", str(spec), "-o", str(tmp_path / "t.py")]) == 0
    assert (tmp_path / "t.py").read_text() == py.read_text().replace(
        f"--py {py} --ts {ts} --prompt {prompt}", f"--py {tmp_path / 't.py'}"
    )
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(_spec(stage=2)))
    with pytest.raises(SystemExit, match="not a valid Stage Spec"):
        main(["stage", "check", str(bad)])


def test_the_spec_is_frozen() -> None:
    spec = StageSpec.model_validate(SPEC)
    with pytest.raises(ValidationError):
        spec.id = "x"  # type: ignore[misc]
