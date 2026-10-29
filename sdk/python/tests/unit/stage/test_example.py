"""The developer-mode example (``examples/stage_shop``) stays true: its
generated moves are current, its spec checks clean, and its brain imports."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from voqalize.sdk.stage import load_spec
from voqalize.sdk.stage.check import check_spec
from voqalize.sdk.stage.gen import render_json, render_python

ROOT = Path(__file__).parents[3]
SOURCE = "examples/stage_shop/scene.json"
OUT = "examples/stage_shop/stage_gen.py"
PAGE = "examples/stage_shop/scene.page.json"


def test_the_generated_moves_are_current() -> None:
    spec = load_spec(ROOT / SOURCE)
    command = f"voqalize stage gen {SOURCE} --py {OUT} --json {PAGE}"
    assert (ROOT / OUT).read_text() == render_python(spec, source=SOURCE, command=command), (
        f"stale: run `{command}` from sdk/python"
    )
    assert (ROOT / PAGE).read_text() == render_json(spec), f"stale: run `{command}`"
    assert check_spec(spec) == []


def test_the_brain_imports_with_its_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(ROOT))
    brain = importlib.import_module("examples.stage_shop.brain")
    try:
        assert {m.id for m in brain.MOVES} == {"core.show", "commerce.filter", "commerce.cart_add"}
        assert "- {show: Heading}" in brain.PROMPT
        assert "{filter: Facet | Option}" in brain.PROMPT
    finally:
        for name in [n for n in sys.modules if n.startswith("examples")]:
            del sys.modules[name]
