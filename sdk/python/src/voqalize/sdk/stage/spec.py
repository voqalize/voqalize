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
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .moves import MAX_ARGS, MAX_TOOL_ARGS, Move, MoveSet
from .policy import MoveClass

__all__ = [
    "KITS_DIR",
    "MAX_TOOL_ARGS",
    "PLUGIN_CLASSES",
    "PLUGIN_DEADLINES_MS",
    "SPEC_VERSION",
    "WINDOW",
    "ArgSpec",
    "EventSpec",
    "FieldSpec",
    "ItemSpec",
    "KitSpec",
    "KitUse",
    "MoveSpec",
    "PluginSpec",
    "SliceSpec",
    "StageSpec",
    "load_kit",
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


#: The most entries of a list a read gives by default; the rest are counted.
WINDOW = 20

_PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]*)\}")


def _placeholders(template: str) -> set[str]:
    return set(_PLACEHOLDER.findall(template))


class FieldSpec(_Strict):
    """One field of a slice. A field the brain must never see is ``private``:
    the page strips it before anything is sent."""

    name: str = Field(pattern=_IDENT)
    type: Scalar | Literal["array", "object"] = "string"
    items: ItemSpec | None = None
    """What an array of plain values holds; strings when it is not said."""
    fields: tuple[FieldSpec, ...] | None = None
    """An ``object``'s fields, or the fields of each entry of an ``array`` of objects."""
    enum: tuple[str, ...] | None = None
    optional: bool = False
    private: bool = False
    doc: str = ""

    @model_validator(mode="after")
    def _shape(self) -> Self:
        if self.type == "object" and not self.fields:
            raise ValueError(f"field {self.name!r}: an object needs its fields")
        if self.fields is not None and self.type not in ("object", "array"):
            raise ValueError(f"field {self.name!r}: only an object or an array has fields")
        if self.fields is not None and self.items is not None:
            raise ValueError(f"field {self.name!r}: an array holds items or fields, not both")
        if self.items is not None and self.type != "array":
            raise ValueError(f"field {self.name!r}: only an array has items")
        if self.enum is not None and self.type != "string":
            raise ValueError(f"field {self.name!r}: only a string takes an enum")
        if len({f.name for f in self.fields or ()}) != len(self.fields or ()):
            raise ValueError(f"field {self.name!r} names a field twice")
        return self

    @property
    def sayable(self) -> bool:
        """Whether a note may print it: a plain value nobody marked private."""
        return not self.private and self.type not in ("array", "object")


class SliceSpec(_Strict):
    """A named, typed piece of the page's state (``cart``, ``listing``), kept
    in the brain's mirror and read by the model on demand."""

    id: str = Field(pattern=_IDENT)
    fields: tuple[FieldSpec, ...]
    window: int = Field(default=WINDOW, ge=1, le=100)
    """How many entries of a list a read gives; the rest are counted."""
    doc: str = ""
    """What it holds, for the read tool's description."""

    @model_validator(mode="after")
    def _shape(self) -> Self:
        if len({f.name for f in self.fields}) != len(self.fields):
            raise ValueError(f"slice {self.id!r} names a field twice")
        return self


class EventSpec(_Strict):
    """A named act that changes one slice: ``cart.changed``."""

    id: str = Field(pattern=_MOVE_ID)
    slice: str
    op: Literal["set", "merge", "clear"] = "merge"
    """``set`` replaces the slice with the event's data, ``merge`` changes the
    fields it carries, ``clear`` empties it."""
    note: str = ""
    """The one line the model hears, a verb phrase: ``{by} added to the cart:
    {count} items``. ``{by}`` is who did it; any other placeholder must be a
    plain, public field of the slice, read after the event is folded. Empty:
    folded in silence."""
    doc: str = ""


class KitSpec(_Strict):
    """A kit: moves, slices and events many apps share, as data
    (``kits/commerce.json``). An app takes it by naming it in ``kits``."""

    kit: Literal[1]
    id: str = Field(pattern=_IDENT)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    """Semver. A minor version only adds; lowering a class or renaming is a major."""
    doc: str = ""
    moves: tuple[MoveSpec, ...] = ()
    slices: tuple[SliceSpec, ...] = ()
    events: tuple[EventSpec, ...] = ()

    @model_validator(mode="after")
    def _own(self) -> Self:
        for m in self.moves:
            if not m.id.startswith(f"{self.id}."):
                raise ValueError(f"kit {self.id!r}: move {m.id!r} must be named {self.id}.…")
        return self


class KitUse(_Strict):
    """An app taking a kit: all of it, or the moves it names."""

    id: str = Field(pattern=_IDENT)
    major: int = Field(ge=1)
    """The kit's major version the app was written against."""
    moves: tuple[str, ...] | None = None
    """The kit's moves to take; all of them when left out. Its slices and
    events always come, since moves report into them."""


#: The kits this SDK ships, by id: ``kits/<id>.json`` beside this module.
KITS_DIR = Path(__file__).parent / "kits"


def load_kit(kit_id: str) -> KitSpec:
    """A kit this SDK ships; :class:`KeyError` when there is none by that id."""
    path = KITS_DIR / f"{kit_id}.json"
    if not path.is_file():
        raise KeyError(kit_id)
    return KitSpec.model_validate_json(path.read_text(encoding="utf-8"))


PluginSide = Literal["brain", "page"]

#: The most a plugin may change, by where it runs: a brain plugin only reads; a
#: page plugin at most makes a change that can be undone.
PLUGIN_CLASSES: dict[str, frozenset[MoveClass]] = {
    "brain": frozenset({MoveClass.LOOK}),
    "page": frozenset({MoveClass.LOOK, MoveClass.NAVIGATE, MoveClass.REVERSIBLE}),
}
#: The longest a plugin may run, by where it runs, in milliseconds.
PLUGIN_DEADLINES_MS: dict[str, int] = {"brain": 20, "page": 5_000}

_ORIGIN = r"^https://[a-z0-9.-]+(:\d+)?$"


class PluginSpec(_Strict):
    """A plugin: code of ours compiled into the runtime that does one typed
    thing the steps cannot (``magento.prices``: a same-origin read of live
    prices). Never fetched at run time; named here so a pack can require it and
    a review can see what it may reach."""

    name: str = Field(pattern=_MOVE_ID)
    major: int = Field(ge=1)
    side: PluginSide
    cls: MoveClass = Field(alias="class")
    args: tuple[ArgSpec, ...] = ()
    output: tuple[FieldSpec, ...] = ()
    """What it returns: only these fields leave it, private ones never."""
    egress: tuple[str, ...] = ()
    """The only origins it may request (``https://host``); empty: none."""
    deadline_ms: int = Field(ge=1)
    pii: bool = False
    """Whether what it reads may hold personal data: its output is then kept
    out of logs."""
    doc: str = ""

    @model_validator(mode="after")
    def _bounds(self) -> Self:
        if self.cls not in PLUGIN_CLASSES[self.side]:
            most = ", ".join(sorted(c.value for c in PLUGIN_CLASSES[self.side]))
            raise ValueError(
                f"plugin {self.name!r}: a {self.side} plugin may be {most}, not {self.cls.value}"
            )
        if self.deadline_ms > PLUGIN_DEADLINES_MS[self.side]:
            raise ValueError(
                f"plugin {self.name!r}: a {self.side} plugin answers within "
                f"{PLUGIN_DEADLINES_MS[self.side]} ms, not {self.deadline_ms}"
            )
        for origin in self.egress:
            if re.fullmatch(_ORIGIN, origin) is None:
                raise ValueError(
                    f"plugin {self.name!r}: egress {origin!r} must be an https origin, with no path"
                )
        if self.side == "brain" and self.egress:
            raise ValueError(
                f"plugin {self.name!r}: a brain plugin never reaches a customer's site; "
                "a read of the site runs on the page"
            )
        return self


def _with_kits(data: dict[str, Any]) -> dict[str, Any]:
    """``data`` with the moves, slices and events of the kits it names, each
    taken once: a part the document already holds as the kit has it is the
    same part (a spec dumped and loaded again), a different one is refused."""
    uses = data.get("kits") or ()
    if not uses:
        return data
    lists: dict[str, list[Any]] = {
        key: list(data.get(key, ())) for key in ("moves", "slices", "events")
    }
    out: dict[str, Any] = {**data, **lists}
    for raw in uses:
        use = KitUse.model_validate(raw)
        try:
            kit = load_kit(use.id)
        except KeyError:
            raise ValueError(f"no kit {use.id!r}") from None
        if int(kit.version.split(".")[0]) != use.major:
            raise ValueError(
                f"kit {use.id!r} is version {kit.version}; the spec wants {use.major}.x"
            )
        known = {m.id for m in kit.moves}
        wanted = set(use.moves) if use.moves is not None else known
        if unknown := wanted - known:
            raise ValueError(f"kit {use.id!r} has no move {', '.join(sorted(unknown))}")
        parts: list[tuple[str, BaseModel]] = [
            *(("moves", m) for m in kit.moves if m.id in wanted),
            *(("slices", s) for s in kit.slices),
            *(("events", e) for e in kit.events),
        ]
        for key, part in parts:
            mine = part.model_dump(mode="json", by_alias=True, exclude_defaults=True)
            got = [p for p in lists[key] if isinstance(p, Mapping) and p.get("id") == mine["id"]]
            if not got:
                lists[key].append(mine)
            elif any(type(part).model_validate(p) != part for p in got):
                raise ValueError(
                    f"{mine['id']!r} is kit {use.id!r}'s; the spec declares it otherwise"
                )
    return out


class StageSpec(_Strict):
    """An app's Stage Spec."""

    schema_: str | None = Field(default=None, alias="$schema")
    stage: Literal[1]
    """The spec format: :data:`SPEC_VERSION`."""
    id: str = Field(pattern=_IDENT)
    """The app, as one lowercase word."""
    languages: tuple[str, ...] = ()
    """The languages its labels and claims are written in (BCP-47)."""
    kits: tuple[KitUse, ...] = ()
    """The kits it takes: their moves, slices and events are merged in when it loads."""
    moves: tuple[MoveSpec, ...] = ()
    slices: tuple[SliceSpec, ...] = ()
    events: tuple[EventSpec, ...] = ()
    plugins: tuple[PluginSpec, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def _merge_kits(cls, data: Any) -> Any:
        return _with_kits(data) if isinstance(data, dict) else data  # pyright: ignore[reportUnknownArgumentType]

    @model_validator(mode="after")
    def _unique(self) -> Self:
        self.move_set()  # one id, one verb
        if len({p.name for p in self.plugins}) != len(self.plugins):
            raise ValueError("two plugins have one name")
        slices = {s.id: s for s in self.slices}
        if len(slices) != len(self.slices):
            raise ValueError("two slices have one id")
        if len({e.id for e in self.events}) != len(self.events):
            raise ValueError("two events have one id")
        for e in self.events:
            got = slices.get(e.slice)
            if got is None:
                raise ValueError(f"event {e.id!r} changes slice {e.slice!r}, which is not declared")
            sayable = {f.name for f in got.fields if f.sayable}
            for name in _placeholders(e.note) - {"by"}:
                if name not in sayable:
                    raise ValueError(
                        f"event {e.id!r}: its note names {{{name}}}, which is not one of "
                        f"{e.slice!r}'s plain, public fields ({', '.join(sorted(sayable)) or 'none'})"
                    )
        return self

    def slice(self, slice_id: str) -> SliceSpec:
        """The slice with this id; :class:`KeyError` when there is none."""
        for s in self.slices:
            if s.id == slice_id:
                return s
        raise KeyError(slice_id)

    def event(self, event_id: str) -> EventSpec:
        """The event with this id; :class:`KeyError` when there is none."""
        for e in self.events:
            if e.id == event_id:
                return e
        raise KeyError(event_id)

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
