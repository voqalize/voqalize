"""``voqalize types`` — the generated TypeScript, pinned property by property.

What this file guards is not the formatting: it is the three claims the generator
makes about the file it writes. That the shapes are **total** (a Python default is
not a TypeScript ``?``, because the wire carries the field either way). That the
**union is closed** (an action added in Python fails the browser's build until it
is handled). And that it reads **one module's namespace**, not the process-wide
subclass registry, which after a few imports holds every other brain's actions
too.

``screen/`` next door is the module it is pointed at — a real package with a
relative import, because that is what a brain is.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from voqalize.sdk.cli import main

SCREEN = Path(__file__).parent / "screen"


@pytest.fixture
def ts(tmp_path: Path) -> str:
    """``screen/actions.py``, generated."""
    out = tmp_path / "actions.gen.ts"
    assert main(["types", str(SCREEN / "actions.py"), "-o", str(out)]) == 0
    return out.read_text()


def test_a_python_default_is_not_a_typescript_optional(ts: str) -> None:
    """The whole soundness argument, in one assertion.

    ``title: str = ""`` is absent from the schema's ``required``, and it is still
    on the wire on every dispatch, because ``Action`` dumps every declared field.
    A generator that read ``required`` would mark it ``title?`` and every reader
    would then have to handle an absence that cannot happen."""
    assert "  title: string;" in ts
    assert "?" not in ts.split("export type UiAction")[0]


def test_nullable_is_a_union_rather_than_an_absence(ts: str) -> None:
    """``str | None`` is a field that is always there and sometimes null."""
    assert "  caption: string | null;" in ts


def test_literals_and_enums_both_become_string_unions(ts: str) -> None:
    """A ``Literal`` inlines; an ``Enum`` is referenced by name and aliased once."""
    assert "  mode: 'compact' | 'full';" in ts
    assert "  urgency: Urgency;" in ts
    assert "export type Urgency = 'low' | 'high';" in ts


def test_a_nested_model_is_emitted_once_and_referenced(ts: str) -> None:
    assert "  rows: Row[];" in ts
    assert ts.count("export interface Row {") == 1
    assert "  amount: number;" in ts


def test_a_dict_field_keeps_its_value_type(ts: str) -> None:
    assert "  meta: Record<string, string>;" in ts


def test_the_wire_name_is_the_alias_not_the_attribute(ts: str) -> None:
    """``serialization_alias`` is what the browser receives, so it is what is
    declared — quoted, since a hyphen is not a TypeScript identifier."""
    assert '  "data-tag": string;' in ts
    assert "  tag:" not in ts


def test_an_action_with_no_fields_is_an_empty_object(ts: str) -> None:
    """``Record<string, never>`` rather than ``{}``, which in TypeScript means
    "anything but null" and would silently accept a payload."""
    assert "export type Dismiss = Record<string, never>;" in ts


def test_a_pinned_name_is_used_verbatim(ts: str) -> None:
    """``Action(name=...)`` is the wire name; the class name is not re-derived."""
    assert "{ command: 'close_it'; payload: Dismiss }" in ts
    assert "'dismiss'" not in ts


def test_the_union_closes_over_every_action(ts: str) -> None:
    assert "| { command: 'show_table'; payload: ShowTable }" in ts
    assert "export type UiActionCommand = UiAction['command'];" in ts
    assert "export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [" in ts
    assert "export function unhandledUiAction(action: never): never {" in ts


def test_docstrings_and_field_descriptions_carry_across(ts: str) -> None:
    assert "/** Put the table up. */" in ts
    assert "/** One line of the table. */" in ts


def test_only_this_module_s_actions_are_generated(tmp_path: Path) -> None:
    """Scoping, with the registry deliberately polluted first.

    ``other.py`` is imported before the run, so ``Action.__subclasses__()`` holds
    ``Unrelated`` by the time the generator looks. Reading the registry is the
    obvious implementation and it is wrong: importing one brain drags in whatever
    that brain imports, and the registry cannot say which app can receive what."""
    from .screen import other  # noqa: F401

    out = tmp_path / "a.ts"
    main(["types", str(SCREEN / "actions.py"), "-o", str(out)])
    assert "Unrelated" not in out.read_text()


def test_the_union_can_be_renamed_and_everything_derived_follows(tmp_path: Path) -> None:
    """Two brains' types can then live in one frontend without colliding."""
    out = tmp_path / "b.ts"
    main(["types", str(SCREEN / "actions.py"), "-o", str(out), "--union-name", "DeskAction"])
    text = out.read_text()
    assert "export type DeskAction =" in text
    assert "export const DESK_ACTION_COMMANDS: readonly DeskActionCommand[] = [" in text
    assert "export function asDeskAction(" in text
    assert "export function unhandledDeskAction(" in text
    assert "UiAction" not in text


def test_the_output_is_byte_identical_run_to_run(tmp_path: Path) -> None:
    """No timestamp, no set iteration. A generated file that churns turns the CI
    check that regenerates it into noise everyone learns to ignore."""
    out = tmp_path / "actions.gen.ts"
    argv = ["types", str(SCREEN / "actions.py"), "-o", str(out)]
    main(argv)
    first = out.read_bytes()
    main(argv)
    assert out.read_bytes() == first


def test_the_header_names_the_source_and_the_command(ts: str) -> None:
    assert ts.startswith("// Generated from ")
    assert "voqalize types" in ts.splitlines()[1]


def test_a_module_with_no_actions_is_an_error(tmp_path: Path) -> None:
    """Silence here would write an empty union, and an empty union makes every
    branch in the browser unreachable — a build that fails everywhere for a
    reason that is nowhere."""
    empty = tmp_path / "empty.py"
    empty.write_text("x = 1\n")
    with pytest.raises(SystemExit, match="no Action subclasses"):
        main(["types", str(empty)])


def test_a_missing_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="no such file"):
        main(["types", str(tmp_path / "nope.py")])
