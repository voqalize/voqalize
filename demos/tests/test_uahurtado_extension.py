"""The uahurtado extension's page test, run from the demos suite.

The brain's e2e (``test_uahurtado_e2e.py``) checks what the brain does with the
events the page sends; this checks that the page sends them. It runs the
extension's own ``pnpm test:page`` (``uahurtado/extension/test/page.mjs``): the
site adapter in headless Chromium against trimmed copies of the university's
pages in ``tests/fixtures/uahurtado/``, with no network — tabs and pills, the
Carreras menu, the career sheet and its 2027 fees read from the visible text,
the lead form filled but never sent and the visitor's own press stopped, visit
cards, a programme's "Requisitos y Valores".

It needs Node, the extension's ``node_modules`` (``pnpm install
--ignore-workspace`` in the extension) and a Chromium that ``playwright-core``
can launch, already installed: it never downloads one. CI has none of these,
so there it skips, saying which is missing; the demos suite stays green.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

EXTENSION = Path(__file__).resolve().parents[1] / "uahurtado" / "extension"
RUNNER = EXTENSION / "test" / "page.mjs"
#: ``page.mjs`` exits with this when no Chromium could be launched.
NO_BROWSER = 3


def test_extension_page_adapter() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    modules = EXTENSION / "node_modules"
    if not (modules / "playwright-core").is_dir() or not (modules / "esbuild").is_dir():
        pytest.skip(f"no node_modules in {EXTENSION} (run `pnpm install --ignore-workspace` there)")
    done = subprocess.run(
        [node, str(RUNNER)],
        cwd=EXTENSION,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if done.returncode == NO_BROWSER:
        pytest.skip(done.stdout.strip() or "no Chromium could be launched")
    assert done.returncode == 0, f"page test failed:\n{done.stdout}\n{done.stderr}"
    assert "passed:" in done.stdout, done.stdout
