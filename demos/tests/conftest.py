"""Every demo test runs under the tool budget; see ``_harness.tools_within_budget``."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from ._harness import tools_within_budget


@pytest.fixture(autouse=True)
def _tools_within_budget() -> Iterator[None]:
    with tools_within_budget():
        yield
