"""``voqalize types`` — the TypeScript half of your actions, generated.

An :class:`~voqalize.sdk.actions.Action` is already a complete description of a
payload: field names, types, defaults, docstrings. Writing that description a
second time in TypeScript is not typing work, it is copying — and the copy has no
way to fail. Rename a field in Python and the hand-written interface goes on
compiling; add an action and the browser's ``switch`` drops it on ``default``. The
screen silently stops moving, and nothing anywhere says so.

So we generate::

    uv run voqalize types backend/brain.py -o frontend/src/actions.gen.ts

What comes out is a discriminated union over ``command`` plus an exhaustiveness
helper, which turns both of those silences into compile errors. It is a build-time
artifact and nothing else: no runtime, no npm package, no dependency. The browser
half of an action is stock pipecat — ``useUICommandHandler`` reads the message
already — so there is nothing to ship, only something to *know*, and a ``.ts``
file is how TypeScript is told.

## Why the shapes are total

``Action`` emits every declared field, ``None`` included, so the wire shape is a
function of the class rather than of one instance. That is what makes this sound:
``required`` is **ignored** — a field with a default is absent from ``required``
and still always present on the wire — and narrowing on ``command`` needs no
runtime validation, so nothing here emits zod.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

from pydantic.json_schema import models_json_schema

from .actions import Action, _snake_case

__all__ = ["main"]

_TS_IDENT = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")

_SCALARS = {
    "string": "string",
    "integer": "number",
    "number": "number",
    "boolean": "boolean",
    "null": "null",
    "object": "Record<string, unknown>",
    "array": "unknown[]",
}


# ── Loading ───────────────────────────────────────────────────────────────────


def _dotted(path: Path) -> tuple[Path, str]:
    """Where ``path``'s package starts, and the name it is imported by.

    Walks up while there is an ``__init__.py``, so ``backend/brain.py`` next to
    an ``__init__.py`` imports as ``backend.brain`` — which is what makes its
    ``from .content import ...`` resolve. A loose file is just its own stem."""
    parts = [path.stem]
    root = path.parent
    while (root / "__init__.py").is_file():
        parts.insert(0, root.name)
        root = root.parent
    return root, ".".join(parts)


def _load_module(target: str) -> Any:
    """Import ``target``, given either as a file path or as a dotted module.

    A path is imported under its real package name with the package's parent on
    ``sys.path``, so a brain loads here the way it does when it runs — relative
    imports and all."""
    if target.endswith(".py") or "/" in target or "\\" in target:
        path = Path(target).resolve()
        if not path.is_file():
            raise SystemExit(f"voqalize types: no such file: {target}")
        root, name = _dotted(path)
        sys.path.insert(0, str(root))
        target = name
    try:
        return importlib.import_module(target)
    except ImportError as exc:
        raise SystemExit(f"voqalize types: cannot import {target}: {exc}") from exc


def _collect(module: Any) -> list[type[Action]]:
    """The actions this module's namespace exposes, in declaration order.

    Scoped to ``vars(module)`` rather than ``Action.__subclasses__()``: importing
    one brain can drag in every other brain's actions, and the registry cannot
    tell them apart. What a module *names* is what its app can receive."""
    found: list[type[Action]] = []
    for value in vars(module).values():
        if (
            isinstance(value, type)
            and issubclass(value, Action)
            and value is not Action
            and value not in found
        ):
            found.append(value)
    return found


# ── Emitting ──────────────────────────────────────────────────────────────────


def _lit(value: Any) -> str:
    """A value as a TypeScript literal, single-quoted the way a frontend writes."""
    if isinstance(value, str) and "'" not in value and "\\" not in value:
        return f"'{value}'"
    return json.dumps(value)


def _ts_name(name: str) -> str:
    """A property name as TypeScript will accept it — quoted if it must be."""
    return name if _TS_IDENT.match(name) else json.dumps(name)


def _doc(text: str | None, indent: str) -> list[str]:
    """``description`` as JSDoc, one line or several."""
    if not text:
        return []
    body = text.replace("*/", "*​/").strip()
    lines = body.splitlines()
    if len(lines) == 1:
        return [f"{indent}/** {lines[0]} */"]
    out = [f"{indent}/**"]
    out += [f"{indent} * {line}".rstrip() for line in lines]
    out.append(f"{indent} */")
    return out


def _union(parts: list[str]) -> str:
    seen: list[str] = []
    for part in parts:
        if part not in seen:
            seen.append(part)
    return " | ".join(seen) if seen else "unknown"


def _ts_type(node: dict[str, Any]) -> str:
    """One JSON Schema node as a TypeScript type.

    The vocabulary pydantic actually emits for these models is small — scalars,
    arrays, ``$ref``, ``enum``, ``anyOf`` for nullability, open objects — and
    anything outside it becomes ``unknown`` rather than a crash, because a
    generator that refuses to run is worse than one that is vague about one
    field."""
    if ref := node.get("$ref"):
        return str(ref).rsplit("/", 1)[-1]
    if "const" in node:
        return _lit(node["const"])
    if values := node.get("enum"):
        return _union([_lit(v) for v in values])
    if members := node.get("anyOf") or node.get("oneOf"):
        return _union([_ts_type(m) for m in members])
    kind = node.get("type")
    if isinstance(kind, list):
        return _union([_ts_type({**node, "type": k}) for k in kind])
    if kind == "array":
        items = node.get("items")
        if not isinstance(items, dict):
            return "unknown[]"
        inner = _ts_type(items)
        return f"({inner})[]" if "|" in inner else f"{inner}[]"
    if kind == "object":
        extra = node.get("additionalProperties")
        if isinstance(extra, dict):
            return f"Record<string, {_ts_type(extra)}>"
        return "Record<string, unknown>"
    return _SCALARS.get(str(kind), "unknown")


def _declare(name: str, schema: dict[str, Any]) -> list[str]:
    """One ``$defs`` entry as an exported type.

    A model becomes an interface, an ``Enum`` becomes an alias. Every property is
    required — not an oversight about ``required`` but the guarantee ``Action``
    makes, which this module's docstring explains."""
    out = _doc(schema.get("description"), "")
    if "properties" not in schema:
        # An `Enum` field, or any other non-object referenced by name.
        rendered = "Record<string, never>" if schema.get("type") == "object" else _ts_type(schema)
        out.append(f"export type {name} = {rendered};")
        return out
    properties: dict[str, Any] = schema["properties"]
    if not properties:
        out.append(f"export type {name} = Record<string, never>;")
        return out
    out.append(f"export interface {name} {{")
    for i, (prop, spec) in enumerate(properties.items()):
        if i:
            out.append("")
        out += _doc(spec.get("description"), "  ")
        out.append(f"  {_ts_name(prop)}: {_ts_type(spec)};")
    out.append("}")
    return out


def _render(actions: list[type[Action]], union: str, source: str, command: str) -> str:
    """The whole file: the shapes, then the union, then the two helpers."""
    keys, combined = models_json_schema(
        [(a, "serialization") for a in actions], ref_template="#/$defs/{model}"
    )
    defs: dict[str, Any] = combined.get("$defs") or {}
    named = {a: str(keys[(a, "serialization")]["$ref"]).rsplit("/", 1)[-1] for a in actions}
    nested = sorted(set(defs) - set(named.values()))

    plural = _snake_case(union).upper() + "_COMMANDS"
    lines = [
        f"// Generated from {source} by `voqalize types`. Do not edit — regenerate with:",
        f"//   {command}",
        "//",
        "// Every field is present on the wire, `null` included, so nothing here is",
        "// optional and no runtime validation is needed to narrow on `command`.",
        "",
    ]

    for action in actions:
        lines += _declare(named[action], defs[named[action]])
        lines.append("")

    if nested:
        lines += ["// ── Shapes used by the actions above ───────────────────────────────", ""]
        for name in nested:
            lines += _declare(name, defs[name])
            lines.append("")

    lines += [
        "/** Everything the brain can put on screen, discriminated by `command`. */",
        f"export type {union} =",
    ]
    lines += [
        f"  | {{ command: {_lit(a.__voqal_action__)}; payload: {named[a]} }}" for a in actions
    ]
    lines[-1] += ";"
    lines += [
        "",
        f"export type {union}Command = {union}['command'];",
        "",
        f"export const {plural}: readonly {union}Command[] = [",
    ]
    lines += [f"  {_lit(a.__voqal_action__)}," for a in actions]
    lines += [
        "];",
        "",
        f"const _known = new Set<string>({plural});",
        "",
        "/**",
        " * Narrow a `ui-command` off the wire. Returns null for a command this file",
        " * does not declare — a page and a brain ship separately, and an older page",
        " * receiving a newer action should ignore it, not throw.",
        " */",
        f"export function as{union}(command: string, payload: unknown): {union} | null {{",
        f"  return _known.has(command) ? ({{ command, payload }} as {union}) : null;",
        "}",
        "",
        "/**",
        " * Call this in a `switch`'s default arm. Adding an action then fails to",
        " * compile here until the new case is handled — which is the whole point of",
        " * generating this file.",
        " */",
        f"export function unhandled{union}(action: never): never {{",
        "  throw new Error(`Unhandled action: ${JSON.stringify(action)}`);",
        "}",
        "",
    ]
    return "\n".join(lines)


# ── Entry point ───────────────────────────────────────────────────────────────


def _types(args: argparse.Namespace) -> int:
    module = _load_module(args.module)
    actions = _collect(module)
    if not actions:
        raise SystemExit(f"voqalize types: no Action subclasses in {args.module}")
    command = f"voqalize types {args.module}" + (f" -o {args.out}" if args.out else "")
    text = _render(actions, args.union_name, args.module, command)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"{len(actions)} actions → {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="voqalize", description="Voqalize agent SDK developer tools."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    types = sub.add_parser("types", help="generate TypeScript action types from a brain module")
    types.add_argument(
        "module", help="path to the module declaring your actions, or its dotted name"
    )
    types.add_argument("-o", "--out", help="file to write; stdout when omitted")
    types.add_argument("--union-name", default="UiAction", help="name of the generated union")
    types.set_defaults(func=_types)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
