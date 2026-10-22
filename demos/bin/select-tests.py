#!/usr/bin/env python3
"""Which demo tests a change needs: the tests of the demos it touched, or all of them.

    bin/select-tests.py BASE [HEAD]

Prints ``all``, or the test files to run, one per line, relative to ``demos/``.
Prints nothing when the change cannot affect a demo test (docs only, say).
CI passes the last commit whose CI passed as BASE, so changes from a run that was
cancelled or failed are tested again by the next one. Locally:
``uv run pytest $(bin/select-tests.py origin/main)``, but check for ``all`` first.

The default is ``all``. A change selects less only when every path it touches is
one of these:

- ``demos/<name>/...`` for a demo (a folder with a ``backend/``, as discovery finds
  them). It selects that demo's tests, and the tests of every demo whose Python
  imports it, transitively (avatar is imported by many).
- ``demos/tests/test_*.py``. It selects that file.
- ``demos/tests/<x>_<name>/...``, a demo's own helper (``eval_saatvik``, an offline
  eval pytest never collects). It selects that demo's tests.
- Under ``IGNORED``, or Markdown anywhere: nothing a demo test reads. The web build's
  inputs are here (``demos/shared/``, ``build.mjs``, the pnpm files), which no Python
  test reads; a demo's own ``frontend/`` is not, because some tests read it.

A demo's tests are the files named ``test_<name>_*.py``, plus any test file whose
Python imports the demo or names its folder (``test_silent_turn`` drives servicing).
``ALWAYS`` runs whenever anything is selected: those files check every demo.
Nothing here is a list of demos or of who imports whom. It is read from the
tree each time, so a new demo or a new import is covered without editing this.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

DEMOS = Path(__file__).resolve().parents[1]
REPO = DEMOS.parent
TESTS = DEMOS / "tests"

# Paths no demo test reads (checked 2026-10-22: tests name some of these only in
# docstrings). Prefixes, so a folder ends in "/". ci.yml itself is not here: a change
# to the gate runs all of it.
IGNORED = (
    "docs/",
    "design/",
    "demos/shared/",
    "demos/landing/",
    "demos/public/",
    "demos/build.mjs",
    "demos/cloudbuild.web.yaml",
    ".github/workflows/ci-web.yml",
    ".github/workflows/voice-catalog.yml",
    ".gitignore",
    "package.json",
    "pnpm-lock.yaml",
    "pnpm-workspace.yaml",
    "ecosystem.config.cjs",
    "LICENSE",
)

# Test files that sweep every demo, so they run for any demo change.
ALWAYS = ("test_conformance.py", "test_demo_voice_contract.py")


def demo_names() -> list[str]:
    return sorted(p.parent.name for p in DEMOS.glob("*/backend") if p.is_dir())


def references(path: Path, names: list[str]) -> set[str]:
    """The demos a Python file imports or names as a folder."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return set(names)  # unreadable: assume it touches everything
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            found.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            for name in names:
                if node.value == name or re.search(rf"(^|[/\"']){name}($|[/\"'])", node.value):
                    found.add(name)
    return found & set(names)


def importers(names: list[str]) -> dict[str, set[str]]:
    """For each demo, the demos whose Python references it."""
    by: dict[str, set[str]] = {n: set() for n in names}
    for name in names:
        for py in (DEMOS / name).rglob("*.py"):
            if "node_modules" in py.parts:
                continue
            for dep in references(py, names) - {name}:
                by[dep].add(name)
    return by


def owner(test: str, names: list[str]) -> str | None:
    """The demo a ``test_<name>_*.py`` file belongs to; longest name wins."""
    for name in sorted(names, key=len, reverse=True):
        if test.startswith(f"test_{name}_"):
            return name
    return None


def helper(folder: str, names: list[str]) -> str | None:
    """The demo a ``demos/tests/<x>_<name>/`` folder belongs to; longest name wins."""
    for name in sorted(names, key=len, reverse=True):
        if folder.endswith(f"_{name}"):
            return name
    return None


def select(changed: list[str]) -> list[str] | None:
    """The test files to run, or None for all of them."""
    names = demo_names()
    touched: set[str] = set()
    tests: set[str] = set()
    for path in changed:
        if path.startswith(IGNORED) or path.endswith(".md"):
            continue
        parts = path.split("/")
        if len(parts) >= 3 and parts[0] == "demos" and parts[1] in names:
            touched.add(parts[1])
        elif (
            len(parts) >= 4 and parts[:2] == ["demos", "tests"] and (own := helper(parts[2], names))
        ):
            touched.add(own)
        elif (
            len(parts) == 3
            and parts[:2] == ["demos", "tests"]
            and re.fullmatch(r"test_\w+\.py", parts[2])
        ):
            tests.add(parts[2])
        else:
            return None

    affected = set(touched)
    by = importers(names)
    frontier = list(touched)
    while frontier:
        for user in by[frontier.pop()] - affected:
            affected.add(user)
            frontier.append(user)

    if affected:
        for test in TESTS.glob("test_*.py"):
            if owner(test.name, names) in affected or references(test, names) & affected:
                tests.add(test.name)
    if tests:
        tests.update(ALWAYS)
    return sorted(f"tests/{t}" for t in tests if (TESTS / t).exists())


def main() -> int:
    if not 2 <= len(sys.argv) <= 3:
        print(__doc__, file=sys.stderr)
        return 2
    base, head = sys.argv[1], sys.argv[2] if len(sys.argv) == 3 else "HEAD"
    diff = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    if diff.returncode != 0:
        print(f"cannot diff {base}...{head}; running all: {diff.stderr.strip()}", file=sys.stderr)
        print("all")
        return 0
    chosen = select(diff.stdout.split())
    print("all" if chosen is None else "\n".join(chosen))
    return 0


if __name__ == "__main__":
    sys.exit(main())
