"""Each demo's Stage Spec and the files generated from it agree.

A demo on Stage declares its moves once, in ``<demo>/scene.json``; the brain
imports them from ``backend/stage_gen.py`` and the extension from
``extension/src/scene.gen.ts``. A spec edited without regenerating would leave
the brain and the page each believing a different move, so the files are
generated again here and compared. Regenerate with the command on each file's
second line, from ``demos/``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from voqalize.sdk.stage import load_spec
from voqalize.sdk.stage.gen import render_python, render_typescript

DEMOS = Path(__file__).resolve().parent.parent
SPECS = sorted(p.parent.name for p in DEMOS.glob("*/scene.json"))


def test_the_ported_demos_have_a_spec() -> None:
    assert {"cannonhome", "explora"} <= set(SPECS)


@pytest.mark.parametrize("demo", SPECS)
def test_the_generated_files_are_current(demo: str) -> None:
    spec = load_spec(DEMOS / demo / "scene.json")
    source = f"{demo}/scene.json"
    py, ts = f"{demo}/backend/stage_gen.py", f"{demo}/extension/src/scene.gen.ts"
    command = f"voqalize stage gen {source} --py {py} --ts {ts}"
    assert (DEMOS / py).read_text() == render_python(spec, source=source, command=command), (
        f"{py} is stale: run `{command}` from demos/"
    )
    assert (DEMOS / ts).read_text() == render_typescript(spec, source=source, command=command), (
        f"{ts} is stale: run `{command}` from demos/"
    )
