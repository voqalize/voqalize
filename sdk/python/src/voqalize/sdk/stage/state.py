"""State without a screen dump: the brain's mirror of the page.

The page never sends its state whole. It sends named acts —
:class:`~voqalize.sdk.stage.StageEvent` ``cart.changed`` — and the brain folds
each into a **slice** of its :class:`Mirror`, versioned, so the mirror is what
the page shows without the page ever pushing it. The model hears one short line
naming the act (the event's ``note``), never the values, and reads the values
when it needs them through one tool that answers from the mirror within the
tool budget (:meth:`Mirror.read`).

What a slice holds is an allowlist: only the fields its spec declares are kept,
whatever the page sent, and a field marked ``private`` is dropped here even if
a page sent it, as well as on the page.

A session starts from first principles, not from a screen: a slice nothing has
reported yet reads as unknown, never as empty.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from loguru import logger

from .spec import FieldSpec, SliceSpec, StageSpec
from .wire import StageEvent

__all__ = ["Folded", "Mirror"]

_WHO = {"visitor": "The visitor", "agent": "You"}


@dataclass(frozen=True, slots=True)
class Folded:
    """What one event did to the mirror."""

    slice: str
    version: int
    note: str | None
    """The line for the model, in square brackets; ``None`` when the event is
    folded in silence."""
    changed: bool = True
    """Whether the slice is different for it. A page that reports the same
    state again (a cart re-read on every page load) changed nothing: no new
    version, and no line, since nobody did anything."""


_SCALARS: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
}


def _plain(kind: str, value: Any) -> bool:
    """Whether ``value`` is a plain value of ``kind`` (a bool is not a number)."""
    if isinstance(value, bool) and kind != "boolean":
        return False
    return isinstance(value, _SCALARS[kind])


def _keep(fields: Sequence[FieldSpec], data: Mapping[str, Any]) -> dict[str, Any]:
    """``data`` with only the declared, public fields, nested ones too, each
    of the type its spec declares: a value of another shape (an object where
    names were declared, say) is dropped, whatever it holds, never kept."""
    out: dict[str, Any] = {}
    for f in fields:
        if f.private or f.name not in data:
            continue
        value: Any = data[f.name]
        if value is None:
            if f.optional:
                out[f.name] = None
            continue
        if f.type == "object":
            if f.fields is None or not isinstance(value, Mapping):
                continue
            value = _keep(f.fields, value)  # pyright: ignore[reportUnknownArgumentType]
        elif f.type == "array":
            if not isinstance(value, list):
                continue
            items: list[Any] = value  # pyright: ignore[reportUnknownVariableType]
            if f.fields is not None:
                value = [_keep(f.fields, v) for v in items if isinstance(v, Mapping)]
            else:
                kind = f.items.type if f.items is not None else "string"
                value = [v for v in items if _plain(kind, v)]
        elif not _plain(f.type, value):
            continue
        out[f.name] = value
    return out


def _say(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if value is None:
        return "none"
    return str(value)


def _render(
    fields: Sequence[FieldSpec], data: Mapping[str, Any], window: int, indent: str
) -> list[str]:
    lines: list[str] = []
    for f in fields:
        if f.name not in data:
            continue
        value = data[f.name]
        if isinstance(value, list):
            items: list[Any] = value  # pyright: ignore[reportUnknownVariableType]
            lines.append(f"{indent}{f.name} ({len(items)}):")
            for item in items[:window]:
                if f.fields is not None and isinstance(item, Mapping):
                    entry: Mapping[str, Any] = item  # pyright: ignore[reportUnknownVariableType]
                    parts = [
                        f"{g.name}: {_say(entry[g.name])}"
                        for g in f.fields
                        if g.name in entry and not isinstance(entry[g.name], (list, dict))
                    ]
                    lines.append(f"{indent}  - {'; '.join(parts)}")
                else:
                    lines.append(f"{indent}  - {_say(item)}")
            if len(items) > window:
                lines.append(f"{indent}  … and {len(items) - window} more")
        elif f.fields is not None and isinstance(value, Mapping):
            lines.append(f"{indent}{f.name}:")
            lines += _render(f.fields, value, window, indent + "  ")  # pyright: ignore[reportUnknownArgumentType]
        else:
            lines.append(f"{indent}{f.name}: {_say(value)}")
    return lines


class Mirror:
    """The page's state as the brain knows it, one versioned slice at a time."""

    def __init__(self, spec: StageSpec) -> None:
        self._spec = spec
        self._slices: dict[str, SliceSpec] = {s.id: s for s in spec.slices}
        self._values: dict[str, dict[str, Any]] = {}
        self._versions: dict[str, int] = dict.fromkeys(self._slices, 0)

    @property
    def slices(self) -> tuple[str, ...]:
        """The slice ids the spec declares."""
        return tuple(self._slices)

    def version(self, slice_id: str) -> int:
        """How many events have changed this slice: 0 before the first."""
        return self._versions[slice_id]

    def value(self, slice_id: str) -> Mapping[str, Any] | None:
        """The slice as the page last reported it; ``None`` when nothing has."""
        return self._values.get(slice_id)

    def fold(self, event: StageEvent) -> Folded | None:
        """Fold one event into its slice. An event the spec does not declare is
        logged and ignored: it is ``None``."""
        try:
            spec = self._spec.event(event.name)
        except KeyError:
            logger.warning("stage: no event {!r} in the spec; ignored", event.name)
            return None
        sl = self._slices[spec.slice]
        kept = _keep(sl.fields, event.data)
        before = self._values.get(sl.id)
        if spec.op == "set":
            after = kept
        elif spec.op == "merge":
            after = {**(before or {}), **kept}
        else:
            after = {}
        if after == before:
            logger.info("stage: {} by {} -> {} unchanged", event.name, event.by, sl.id)
            return Folded(sl.id, self._versions[sl.id], None, changed=False)
        self._values[sl.id] = after
        self._versions[sl.id] += 1
        version = self._versions[sl.id]
        note = None
        if spec.note:
            values = {**self._values[sl.id], "by": _WHO[event.by]}
            text = spec.note.format_map(_Blank({k: _say(v) for k, v in values.items()}))
            note = f"[{text[:1].upper()}{text[1:]}]"
        logger.info("stage: {} by {} -> {} v{}", event.name, event.by, sl.id, version)
        return Folded(sl.id, version, note)

    def read(self, slice_id: str) -> str:
        """The slice in plain lines, for the model: at most the slice's window
        of any list, the rest counted. A slice nothing has reported reads as
        unknown."""
        sl = self._slices.get(slice_id)
        if sl is None:
            return f"There is no {slice_id!r} to read; there are: {', '.join(self._slices)}."
        value = self._values.get(slice_id)
        if value is None:
            return f"Nothing is known yet about the {slice_id}: the page has not reported it."
        lines = _render(sl.fields, value, sl.window, "")
        head = f"The {slice_id}, as the page last reported it (version {self._versions[slice_id]}):"
        return "\n".join([head, *lines]) if lines else f"The {slice_id} is empty."


class _Blank(dict[str, str]):
    """Leaves a placeholder the slice has no value for empty, never raising."""

    def __missing__(self, key: str) -> str:
        return ""
