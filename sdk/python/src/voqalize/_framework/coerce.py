"""Coerce a model's raw tool arguments into the pydantic models the tool annotates.

A framework hands a tool function whatever JSON the model emitted: plain ``dict`` /
``list`` values, keyed by the property names in the schema it derived from the tool's
type hints. The annotation is a *schema declaration*, not a parse — so a tool written
as::

    async def set_trip_structure(legs: list[Leg]) -> dict: ...

is handed ``[{"from_": "BLR", "to": "SGN"}, ...]``, not ``[Leg(...), ...]``. Every tool
body then re-does the same defensive unpacking (``dict(raw) if isinstance(raw, dict)
else raw.model_dump()``) and the type hints lie.

This module makes the hints honest. :func:`coerce_arguments` reads the tool's own
annotations and builds the declared models before the tool is invoked:

* ``Model`` and ``list[Model]`` (also ``Sequence`` / ``tuple`` / ``set`` of a model, and
  ``Model | None``) are constructed; **every other annotation is passed through
  untouched** — a ``str`` stays a ``str``, an unannotated parameter is never guessed at.
* **Aliases work both ways.** A field declared ``from_: str = Field(alias="from")``
  validates from either key: the wire's ``from`` *and* the schema's ``from_`` (which is
  the name the framework actually puts in the JSON schema — aliases don't survive
  schema generation). So a tool body reads ``leg.from_`` and writes
  ``leg.model_dump(by_alias=True)`` for the browser, with no hand-rolled renames.
* A value that cannot be parsed raises :class:`CoercionError`, which the adapter turns
  into a tool *error result* the model can see and retry — never a dead turn.

:func:`coerce_result` closes the same loop on the way *out*. A tool may return its
own pydantic model — the natural thing to write once its arguments are models — and
the framework has to hand the model a JSON object. Left alone, ADK nests the live
instance under ``{"result": <Model>}`` and lets genai flatten it late with a bare
``model_dump()``: **aliases are dropped** (``from`` becomes ``from_``, silently
asymmetric with the input path above) and a non-JSON scalar like ``datetime.date``
only explodes at the HTTP boundary, as an opaque ``TypeError`` from ``json.dumps``.
So the SDK dumps it here instead — ``model_dump(by_alias=True, mode="json")``,
recursing into dicts and lists so a model nested inside a returned dict is dumped
too. A returned model becomes the function response *directly* (its fields are the
response object, not wrapped in ``result``); anything with no model in it is returned
unchanged, so plain dict/str/int returns keep their exact current behavior.

Framework-agnostic: nothing here imports ADK / genai (only pydantic, which every
framework already depends on).
"""

from __future__ import annotations

import inspect
import types as _pytypes
from collections.abc import Callable, Sequence, Set
from typing import Any, Union, get_args, get_origin, get_type_hints

from loguru import logger
from pydantic import BaseModel, ValidationError

__all__ = ["CoercionError", "coerce_arguments", "coerce_result"]

# pydantic ≥ 2.11 validates by field name *and* alias in a single pass, recursively
# through nested models — exactly the "populate_by_name both ways" semantics we want,
# without touching the client's own model config. Older pydantic gets the top-level
# key-normalizing fallback below.
_HAS_BY_NAME = "by_name" in inspect.signature(BaseModel.model_validate).parameters

# The container annotations whose *element* type we look through for a model.
_SEQUENCE_ORIGINS = (list, tuple, set, frozenset, Sequence, Set)


class CoercionError(Exception):
    """One tool argument could not be parsed into the model its parameter annotates.

    Carries the parameter name, the target model and pydantic's own complaint, so the
    message is usable both as a log line and as the tool-error result the model reads
    before retrying."""

    def __init__(self, param: str, model: type[BaseModel], detail: str) -> None:
        super().__init__(
            f"argument {param!r} is not a valid {model.__name__}: {detail}. "
            f"Re-call the tool with {param!r} shaped as described in the schema."
        )
        self.param = param
        self.model = model
        self.detail = detail


def coerce_arguments(func: Callable[..., Any], args: dict[str, Any]) -> dict[str, Any]:
    """The tool's arguments with every pydantic-annotated one constructed.

    Returns a new dict (the input is never mutated); values whose annotation is not a
    pydantic model — or that are already instances — are carried over unchanged. Raises
    :class:`CoercionError` if a declared model can't be built from what the model sent.

    Annotations that can't be resolved at all (an unresolvable ``from __future__``
    forward reference, a builtin without a signature) are treated as "nothing to
    coerce": the tool sees exactly what it would have seen without this module."""
    hints = _type_hints(func)
    if not hints:
        return args
    out = dict(args)
    for name, value in args.items():
        annotation = hints.get(name)
        if annotation is None:
            continue
        model, is_sequence = _model_target(annotation)
        if model is None:
            continue
        if not is_sequence:
            out[name] = _build(model, value, name)
        elif isinstance(value, list):
            out[name] = [_build(model, item, name) for item in value]
    return out


def coerce_result(result: Any) -> Any | None:
    """A tool's return value with every pydantic model in it dumped for the wire.

    ``model_dump(by_alias=True, mode="json")`` — the same rules a typed
    :class:`~voqalize.sdk.actions.Action` serializes by, so a model that crosses to
    the *browser* and the same model that goes back to the *LLM* have one spelling.
    Recurses through ``dict`` values and ``list`` / ``tuple`` items, so a model nested
    inside a returned dict is dumped too.

    Returns ``None`` when there was no model anywhere in ``result`` — the caller's
    signal to leave the framework's own handling completely alone. That keeps plain
    ``dict`` / ``str`` / ``int`` returns byte-for-byte on their existing path.
    """
    converted, changed = _dump_models(result)
    return converted if changed else None


def _dump_models(value: Any) -> tuple[Any, bool]:
    """``(converted, changed)`` — ``changed`` is False when nothing was a model."""
    if isinstance(value, BaseModel):
        return value.model_dump(by_alias=True, mode="json"), True
    if isinstance(value, dict):
        out: dict[Any, Any] = {}
        changed = False
        for key, item in value.items():  # pyright: ignore[reportUnknownVariableType]
            out[key], item_changed = _dump_models(item)
            changed = changed or item_changed
        return out, changed
    if isinstance(value, (list, tuple)):
        items = [_dump_models(item) for item in value]  # pyright: ignore[reportUnknownVariableType]
        changed = any(item_changed for _, item_changed in items)
        return type(value)(item for item, _ in items), changed
    return value, False


def _type_hints(func: Callable[..., Any]) -> dict[str, Any]:
    """The function's resolved annotations, or ``{}`` when they can't be resolved.

    ``get_type_hints`` evaluates string annotations against the function's own module
    globals; a tool defined with a ``TYPE_CHECKING``-only import raises ``NameError``
    there. That's the client's own (harmless) style choice, not an error worth failing a
    call over — we simply coerce nothing for that tool."""
    try:
        return get_type_hints(func)
    except Exception as exc:  # any resolution failure means "nothing to coerce"
        logger.debug("tool-arg coercion: annotations of {} unresolvable: {}", func, exc)
        return {}


def _unwrap_optional(annotation: Any) -> Any:
    """``T`` for ``T | None`` / ``Optional[T]``; the annotation unchanged otherwise."""
    if get_origin(annotation) in (Union, _pytypes.UnionType):
        non_none = [a for a in get_args(annotation) if a is not type(None)]
        if len(non_none) == 1:
            return non_none[0]
    return annotation


def _model_target(annotation: Any) -> tuple[type[BaseModel] | None, bool]:
    """``(model, is_sequence)`` for an annotation that declares a pydantic model —
    directly (``Model``) or as a sequence element (``list[Model]``). ``(None, False)``
    for everything else, which is what leaves non-model annotations untouched."""
    annotation = _unwrap_optional(annotation)
    if inspect.isclass(annotation) and issubclass(annotation, BaseModel):
        return annotation, False
    if get_origin(annotation) in _SEQUENCE_ORIGINS:
        args = get_args(annotation)
        if args:
            element = _unwrap_optional(args[0])
            if inspect.isclass(element) and issubclass(element, BaseModel):
                return element, True
    return None, False


def _build(model: type[BaseModel], raw: Any, param: str) -> Any:
    """One value as ``model``. Already-constructed instances pass through; a mapping is
    validated by alias *and* by field name; anything else is a :class:`CoercionError`."""
    if isinstance(raw, model):
        return raw
    if not isinstance(raw, dict):
        raise CoercionError(param, model, f"expected an object, got {type(raw).__name__}")
    try:
        if _HAS_BY_NAME:
            return model.model_validate(raw, by_alias=True, by_name=True)
        return model.model_validate(_alias_normalized(model, raw))
    except ValidationError as exc:
        raise CoercionError(param, model, _brief(exc)) from exc


def _alias_normalized(model: type[BaseModel], raw: dict[str, Any]) -> dict[str, Any]:
    """The fallback for pydantic < 2.11: rename each field-name key to the alias the
    model validates by, so ``{"from_": ...}`` still populates ``from_ =
    Field(alias="from")``. Top-level only — the native ``by_name`` path above handles
    nested models."""
    out = dict(raw)
    for name, field in model.model_fields.items():
        alias = field.alias
        if alias and alias != name and name in out and alias not in out:
            out[alias] = out.pop(name)
    return out


def _brief(exc: ValidationError) -> str:
    """A one-line summary of pydantic's errors — short enough to hand a model as a tool
    error result, specific enough to name the offending fields."""
    parts = [
        f"{'.'.join(str(loc) for loc in err['loc']) or '<root>'}: {err['msg']}"
        for err in exc.errors()[:3]
    ]
    return "; ".join(parts) or str(exc)
