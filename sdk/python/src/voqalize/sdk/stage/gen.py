"""``voqalize stage gen``: a Stage Spec, written out for the brain, the page and the prompt.

Three files come out of one spec, so the move ids, classes and arguments are
typed on both sides and written by nobody:

- **Python** (:func:`render_python`): a pydantic model per move with arguments
  (``CheckAvailabilityArgs``), a :class:`~voqalize.sdk.stage.Move` constant per
  move, ``MOVES`` and the spec's hash. A brain imports them instead of
  declaring its moves.
- **TypeScript** (:func:`render_typescript`): the spec's moves, handed to
  ``defineScene`` from ``@voqalize/stage``, which infers every move's argument
  type from them; nothing is written twice, so nothing can drift. What only
  the brain reads (claims, objects, the prompt's lines) stays out of it.
- **Prompt lines** (:func:`render_prompt`): the line each cue is taught with.

The output is formatted the way ``ruff format`` leaves it, so a regenerated
file diffs clean against the checked-in one; diffing them is how a stale copy
is caught.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .spec import ArgSpec, MoveSpec, StageSpec

__all__ = ["render_prompt", "render_python", "render_typescript"]

#: A move's fields only the brain reads.
_BRAIN_ONLY = {"say", "claims", "objects", "doc", "notes"}

_PY_SCALARS = {"string": "str", "integer": "int", "number": "float", "boolean": "bool"}


def _py_str(text: str) -> str:
    """``text`` as a Python literal in the quotes ``ruff format`` would choose."""
    body = json.dumps(text, ensure_ascii=False)[1:-1]
    if '"' in text and "'" not in text:
        return "'" + body.replace('\\"', '"') + "'"
    return '"' + body + '"'


def _py_value(value: str | int | float | bool | None) -> str:
    if isinstance(value, str):
        return _py_str(value)
    return repr(value)


def _docstring(text: str, indent: str) -> list[str]:
    text = text.strip().replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    if not text:
        return []
    lines = text.splitlines()
    if len(lines) == 1:
        return [f'{indent}"""{lines[0]}"""']
    rest = [f"{indent}{line}".rstrip() for line in lines[1:]]
    return [f'{indent}"""{lines[0]}', *rest, f'{indent}"""']


def _words(move_id: str) -> list[str]:
    return [w for w in re.split(r"[._]", move_id) if w]


def _names(spec: StageSpec) -> dict[str, str]:
    """Each move's name in generated code: its last part, or its whole id when
    two moves share a last part."""
    last = [m.id.rsplit(".", 1)[-1] for m in spec.moves]
    return {
        m.id: (tail if last.count(tail) == 1 else m.id.replace(".", "_"))
        for m, tail in zip(spec.moves, last, strict=True)
    }


def _camel(name: str) -> str:
    return "".join(w[:1].upper() + w[1:] for w in _words(name))


def _py_type(arg: ArgSpec) -> str:
    if arg.type == "array":
        item = arg.items
        inner = (
            "str"
            if item is None
            else (
                f"Literal[{', '.join(_py_str(v) for v in item.enum)}]"
                if item.enum
                else _PY_SCALARS[item.type]
            )
        )
        return f"list[{inner}]"
    if arg.enum:
        return f"Literal[{', '.join(_py_str(v) for v in arg.enum)}]"
    return _PY_SCALARS[arg.type]


def _py_field(arg: ArgSpec) -> list[str]:
    kind = _py_type(arg)
    if arg.required:
        line = f"    {arg.name}: {kind}"
    elif arg.default is not None:
        line = f"    {arg.name}: {kind} = {_py_value(arg.default)}"
    else:
        line = f"    {arg.name}: {kind} | None = None"
    return [line, *_docstring(arg.doc, "    ")]


def _py_strings(name: str, values: tuple[str, ...], indent: str) -> list[str]:
    if not values:
        return []
    if len(values) == 1:
        return [f"{indent}{name}=({_py_str(values[0])},),"]
    inner = indent + "    "
    return [f"{indent}{name}=(", *(f"{inner}{_py_str(v)}," for v in values), f"{indent}),"]


def _py_move(move: MoveSpec, const: str) -> list[str]:
    out = [f"{const} = Move("]
    out += [f"    id={_py_str(move.id)},"]
    out += [f"    verb={_py_str(move.verb) if move.verb else None},"]
    out += [f"    cls=MoveClass.{move.cls.name},"]
    if move.args:
        out += _py_strings("args", tuple(a.name for a in move.args), "    ")
    if move.say:
        out += [f"    say={_py_str(move.say)},"]
    out += _py_strings("claims", move.claims, "    ")
    out += _py_strings("objects", move.objects, "    ")
    out += [")"]
    out += _docstring(move.doc, "")
    return out


def render_python(spec: StageSpec, *, source: str, command: str) -> str:
    """The brain's half: argument models, one ``Move`` per move, ``MOVES``."""
    names = _names(spec)
    literal = any(
        a.enum or (a.items is not None and a.items.enum) for m in spec.moves for a in m.args
    )

    out = [
        f"# Generated from {source} by `voqalize stage gen`. Do not edit — regenerate with:",
        f"#   {command}",
        f'"""The moves of {spec.id}, from its Stage Spec."""',
        "",
        "from __future__ import annotations",
        "",
    ]
    if literal or spec.slices:
        out += ["from typing import Literal", ""]
    out += ["from pydantic import BaseModel" + (", Field" if spec.slices else ""), ""]
    out += [
        "from voqalize.sdk.stage import Move, MoveClass, MoveSet",
        "",
        "#: The spec's hash: a page reading another spec reports a different one.",
        f'SPEC_SHA256 = "{spec.sha256}"',
    ]
    for move in spec.moves:
        out += ["", "", f"class {_camel(names[move.id])}Args(BaseModel):"]
        out += _docstring(
            f"The arguments of ``{move.id}``." if move.args else f"``{move.id}`` takes none.",
            "    ",
        )
        if move.args:
            out += [""]
        for arg in move.args:
            out += _py_field(arg)
    out += [""]
    for move in spec.moves:
        out += ["", *(f"# {line}" for note in move.notes for line in note.splitlines())]
        out += _py_move(move, names[move.id].upper())
    out += ["", "MOVES = MoveSet(", "    ("]
    out += [f"        {names[m.id].upper()}," for m in spec.moves]
    out += ["    )", ")", ""]
    lines = spec.prompt_lines()
    out += ["#: The line each cue is taught with, in the spec's order."]
    if not lines:
        out += ["PROMPT_LINES: tuple[str, ...] = ()"]
    elif len(lines) == 1:
        out += [f"PROMPT_LINES: tuple[str, ...] = ({_py_str(lines[0])},)"]
    else:
        out += ["PROMPT_LINES: tuple[str, ...] = ("]
        out += [f"    {_py_str(line)}," for line in lines]
        out += [")"]
    out += [""]
    if spec.slices:
        ids = ", ".join(_py_str(s.id) for s in spec.slices)
        what = "; ".join(f"{s.id}: {s.doc}" if s.doc else s.id for s in spec.slices)
        out += [
            "#: The slices of the page's state a read may name.",
            f"SliceId = Literal[{ids}]",
            "",
            "",
            "class ReadRequest(BaseModel):",
            '    """What the read tool takes: the slice to read, from the brain\'s mirror."""',
            "",
            "    slice: SliceId = Field(",
            f"        description={_py_str('Which part of their screen to read. ' + what + '.')}",
            "    )",
            "",
        ]
    return "\n".join(_tidy(out))


def _tidy(lines: list[str]) -> list[str]:
    """No more than two blank lines in a row, and none where a comment block
    was empty."""
    out: list[str] = []
    for line in lines:
        if line == "" and len(out) >= 2 and out[-1] == "" and out[-2] == "":
            continue
        out.append(line)
    return out


def _drop_docs(fields: list[dict[str, Any]]) -> None:
    for f in fields:
        f.pop("doc", None)
        _drop_docs(f.get("fields", []))


def render_typescript(spec: StageSpec, *, source: str, command: str) -> str:
    """The page's half: the spec, handed to ``defineScene``."""
    data = spec.model_dump(mode="json", by_alias=True, exclude_defaults=True)
    data.pop("$schema", None)
    data.pop("languages", None)
    # What only the brain reads stays out of the page's bundle.
    for move in data["moves"]:
        for field in _BRAIN_ONLY:
            move.pop(field, None)
        for arg in move.get("args", ()):
            arg.pop("doc", None)
    for sl in data.get("slices", ()):
        sl.pop("doc", None)
        sl.pop("window", None)
        _drop_docs(sl["fields"])
    for event in data.get("events", ()):
        event.pop("note", None)
        event.pop("doc", None)
    body = json.dumps(data, ensure_ascii=False, indent=2)
    return "\n".join(
        [
            f"// Generated from {source} by `voqalize stage gen`. Do not edit — regenerate with:",
            f"//   {command}",
            'import { defineScene } from "@voqalize/stage";',
            "",
            f"/** The moves of {spec.id}, from its Stage Spec. */",
            f"export const scene = defineScene({body});",
            "",
            f'export const SPEC_SHA256 = "{spec.sha256}";',
            "",
        ]
    )


def render_prompt(spec: StageSpec) -> str:
    """The line each cue is taught with, one per line."""
    lines = spec.prompt_lines()
    return "\n".join(lines) + ("\n" if lines else "")
