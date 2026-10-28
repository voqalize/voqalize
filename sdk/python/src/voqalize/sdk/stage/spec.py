"""The Stage Spec: an app's moves, written down once, as data.

A spec is one JSON document. The brain and the page both read it, so a move's
id, class and arguments have one author instead of a Python copy and a
TypeScript copy that drift::

    {
      "stage": 1,
      "id": "explora",
      "languages": ["en", "es"],
      "moves": [
        {"id": "core.show", "verb": "show", "class": "look",
         "args": [{"name": "target"}],
         "say": "{show: Heading} scrolls to a heading."},
        {"id": "explora.check_availability", "class": "reversible",
         "args": [{"name": "hotel_code"}, {"name": "nights", "type": "integer", "optional": true}]}
      ]
    }

:class:`StageSpec` is the one definition of that document: it validates it,
and ``stage.schema.json`` is generated from it (:func:`spec_schema`), never
written by hand. :meth:`StageSpec.move_set` turns a spec into the
:class:`~voqalize.sdk.stage.Move` set the director runs, at run time, which is
how a brain that loads its spec as data (a hosted brain reading a pack) uses
it; ``voqalize stage gen`` writes the same moves out as Python and TypeScript
for a brain and a page that want them typed (:mod:`~voqalize.sdk.stage.gen`).

Every rule a :class:`~voqalize.sdk.stage.Move` keeps is kept here too, because
a spec builds its moves through it: a bad verb fails when the spec is loaded,
not in the middle of a call.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .moves import MAX_ARGS, MAX_TOOL_ARGS, Move, MoveSet
from .policy import MoveClass

__all__ = [
    "MAX_TOOL_ARGS",
    "SPEC_VERSION",
    "ArgSpec",
    "ItemSpec",
    "MoveSpec",
    "StageSpec",
    "load_spec",
    "spec_schema",
]

#: The spec format this SDK reads and writes.
SPEC_VERSION = 1

Scalar = Literal["string", "integer", "number", "boolean"]
Value = str | int | float | bool | None

_IDENT = r"^[a-z][a-z0-9_]*$"
_MOVE_ID = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class ItemSpec(_Strict):
    """What an array argument holds."""

    type: Scalar = "string"
    enum: tuple[str, ...] | None = None
    """The only values it takes, when the set is fixed (a sort order, a tab)."""


class ArgSpec(_Strict):
    """One argument of a move, in the order a cue gives them."""

    name: str = Field(pattern=_IDENT)
    type: Scalar | Literal["array"] = "string"
    items: ItemSpec | None = None
    """What an ``array`` holds; strings when it is not said."""
    enum: tuple[str, ...] | None = None
    """The only values it takes, when the set is fixed."""
    optional: bool = False
    """May be left out, or ``null``."""
    default: Value = None
    """What it is when left out. An argument with a default is never ``null``."""
    doc: str = ""

    @model_validator(mode="after")
    def _shape(self) -> Self:
        if self.items is not None and self.type != "array":
            raise ValueError(f"argument {self.name!r}: only an array has items")
        if self.enum is not None and self.type != "string":
            raise ValueError(f"argument {self.name!r}: only a string takes an enum")
        if self.default is not None and self.optional:
            raise ValueError(
                f"argument {self.name!r}: a default already makes it optional; drop 'optional'"
            )
        return self

    @property
    def required(self) -> bool:
        """Whether every message carries it with a value."""
        return not self.optional and self.default is None


class MoveSpec(_Strict):
    """One move: what :class:`~voqalize.sdk.stage.Move` holds, plus its
    arguments' types and a line of documentation for each generated copy."""

    id: str = Field(pattern=_MOVE_ID)
    verb: str | None = None
    cls: MoveClass = Field(alias="class")
    args: tuple[ArgSpec, ...] = ()
    say: str = ""
    """The line the prompt teaches a cue with."""
    claims: tuple[str, ...] = ()
    objects: tuple[str, ...] = ()
    doc: str = ""
    """What the move does, for whoever writes its performer."""
    notes: tuple[str, ...] = ()
    """Why it is as it is (the calls that taught it), kept beside it."""

    @model_validator(mode="after")
    def _shape(self) -> Self:
        names = [a.name for a in self.args]
        if len(set(names)) != len(names):
            raise ValueError(f"move {self.id!r} names an argument twice")
        if self.verb is not None:
            if len(self.args) > MAX_ARGS:
                raise ValueError(
                    f"move {self.id!r} is a cue and takes {len(self.args)} arguments; "
                    f"a cue carries at most {MAX_ARGS}"
                )
            if any(a.type == "array" for a in self.args):
                raise ValueError(f"move {self.id!r} is a cue; a cue's arguments are words")
        elif len(self.args) > MAX_TOOL_ARGS:
            raise ValueError(
                f"move {self.id!r} takes {len(self.args)} arguments; at most {MAX_TOOL_ARGS}"
            )
        self.move()  # every rule a Move keeps
        return self

    def move(self) -> Move:
        """This move, as the director runs it."""
        return Move(
            id=self.id,
            verb=self.verb,
            cls=self.cls,
            args=tuple(a.name for a in self.args),
            say=self.say,
            claims=self.claims,
            objects=self.objects,
        )


class StageSpec(_Strict):
    """An app's Stage Spec."""

    schema_: str | None = Field(default=None, alias="$schema")
    stage: Literal[1]
    """The spec format: :data:`SPEC_VERSION`."""
    id: str = Field(pattern=_IDENT)
    """The app, as one lowercase word."""
    languages: tuple[str, ...] = ()
    """The languages its labels and claims are written in (BCP-47)."""
    moves: tuple[MoveSpec, ...]

    @model_validator(mode="after")
    def _unique(self) -> Self:
        self.move_set()  # one id, one verb
        return self

    def move_set(self) -> MoveSet:
        """Its moves, as the director runs them."""
        return MoveSet(m.move() for m in self.moves)

    def get(self, move_id: str) -> MoveSpec:
        """The move with this id; :class:`KeyError` when there is none."""
        for m in self.moves:
            if m.id == move_id:
                return m
        raise KeyError(move_id)

    def prompt_lines(self) -> tuple[str, ...]:
        """The line each cue is taught with, in the spec's order."""
        return tuple(m.say for m in self.moves if m.verb is not None and m.say)

    def canonical(self) -> str:
        """The spec as one stable JSON text: what is hashed and what is generated from."""
        data = self.model_dump(mode="json", by_alias=True, exclude_defaults=True)
        data.pop("$schema", None)
        return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @property
    def sha256(self) -> str:
        """The hash a page and a brain compare, to know they read one spec."""
        return hashlib.sha256(self.canonical().encode()).hexdigest()


def load_spec(source: str | Path | Mapping[str, Any]) -> StageSpec:
    """A spec from a JSON file, JSON text or an already parsed document.

    Raises :class:`pydantic.ValidationError` naming what is wrong and where."""
    if isinstance(source, Mapping):
        return StageSpec.model_validate(source)
    if isinstance(source, Path) or not source.lstrip().startswith("{"):
        source = Path(source).read_text(encoding="utf-8")
    return StageSpec.model_validate_json(source)


def spec_schema() -> dict[str, Any]:
    """``stage.schema.json``: the JSON Schema of a spec, generated from :class:`StageSpec`."""
    schema = StageSpec.model_json_schema(by_alias=True, mode="validation")
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Stage Spec",
        **{k: v for k, v in schema.items() if k != "title"},
    }
