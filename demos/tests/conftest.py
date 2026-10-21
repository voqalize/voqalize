"""Every demo test runs under the tool budget; see ``_harness.tools_within_budget``.

And no demo test reaches a live site. KDEM's brain starts its knowledge keeper
from ``on_session_start``, which on a real host reads the site's sitemap; here it
is switched off and pointed at an empty directory, so a session opened by any
test (the voice-contract sweep included) answers from whatever the test primed.

And every test starts on a settled heap (``umbrella.settle_heap``), so the budget
times the tool and not a full collection over what earlier tests left behind.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from voqalize_demos.umbrella import settle_heap

from ._harness import tools_within_budget


@pytest.fixture(autouse=True)
def _settled_heap() -> None:
    """Each test starts on a settled heap, as a brain's sessions do: the umbrella
    freezes what startup loaded, and here everything earlier tests left alive is
    frozen the same way. Without it a full collection walks the whole suite's
    leftovers, and a tool it lands in is timed with that stop inside."""
    settle_heap()


@pytest.fixture(autouse=True)
def _tools_within_budget() -> Iterator[None]:
    with tools_within_budget():
        yield


@pytest.fixture(autouse=True)
def _no_live_site(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("KDEM_KNOWLEDGE_REFRESH", "off")
    monkeypatch.setenv("KDEM_KNOWLEDGE_DIR", str(tmp_path / "kdem-knowledge"))
