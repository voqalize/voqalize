"""State as named acts: the page sends events, the brain folds them into its
mirror, the model hears one line and reads the values on demand."""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest
from pydantic import ValidationError

from voqalize.sdk.events import RTVIMessage, RTVIType
from voqalize.sdk.stage import Mirror, Stage, StageEvent, StagePageEvents, load_spec
from voqalize.sdk.stage.gen import render_python, render_typescript

SPEC: dict[str, Any] = {
    "stage": 1,
    "id": "shop",
    "moves": [{"id": "cart.add", "class": "confirmed", "args": [{"name": "path"}]}],
    "slices": [
        {
            "id": "cart",
            "doc": "what is in their cart",
            "window": 2,
            "fields": [
                {"name": "count", "type": "integer"},
                {"name": "subtotal", "type": "number", "optional": True},
                {
                    "name": "items",
                    "type": "array",
                    "fields": [
                        {"name": "name"},
                        {"name": "qty", "type": "integer"},
                        {"name": "gift_note", "private": True},
                    ],
                },
                {"name": "email", "private": True},
            ],
        },
        {"id": "listing", "fields": [{"name": "title"}, {"name": "sort", "optional": True}]},
    ],
    "events": [
        {
            "id": "cart.changed",
            "slice": "cart",
            "op": "set",
            "note": "{by} changed the cart: {count} items",
        },
        {"id": "listing.sorted", "slice": "listing", "note": "{by} sorted the listing"},
        {"id": "cart.emptied", "slice": "cart", "op": "clear"},
    ],
}

CART = {
    "count": 3,
    "subtotal": 57980,
    "items": [
        {"name": "Sábana King", "qty": 1, "gift_note": "para mamá"},
        {"name": "Toalla", "qty": 1},
        {"name": "Plumón", "qty": 1},
    ],
    "email": "ana@example.com",
    "surprise": "not declared",
}


def test_a_slice_nothing_reported_reads_as_unknown_never_empty() -> None:
    mirror = Mirror(load_spec(SPEC))
    assert mirror.version("cart") == 0
    assert mirror.value("cart") is None
    assert "Nothing is known yet about the cart" in mirror.read("cart")


def test_an_event_is_folded_allowlisted_and_named_in_one_line() -> None:
    mirror = Mirror(load_spec(SPEC))
    folded = mirror.fold(StageEvent(name="cart.changed", by="visitor", data=CART))
    assert folded is not None
    assert (folded.slice, folded.version) == ("cart", 1)
    assert folded.note == "[The visitor changed the cart: 3 items]"
    value = mirror.value("cart")
    assert value is not None
    assert "email" not in value and "surprise" not in value
    assert all("gift_note" not in item for item in value["items"])


def test_a_read_gives_the_window_and_counts_the_rest() -> None:
    mirror = Mirror(load_spec(SPEC))
    mirror.fold(StageEvent(name="cart.changed", data=CART))
    text = mirror.read("cart")
    assert text.splitlines() == [
        "The cart, as the page last reported it (version 1):",
        "count: 3",
        "subtotal: 57980",
        "items (3):",
        "  - name: Sábana King; qty: 1",
        "  - name: Toalla; qty: 1",
        "  … and 1 more",
    ]
    assert "para mamá" not in text and "ana@" not in text


def test_merge_changes_only_what_it_carries_and_clear_empties() -> None:
    mirror = Mirror(load_spec(SPEC))
    mirror.fold(StageEvent(name="listing.sorted", by="agent", data={"title": "Sábanas"}))
    folded = mirror.fold(StageEvent(name="listing.sorted", by="agent", data={"sort": "price_asc"}))
    assert folded is not None and folded.note == "[You sorted the listing]"
    assert mirror.value("listing") == {"title": "Sábanas", "sort": "price_asc"}
    assert mirror.version("listing") == 2
    mirror.fold(StageEvent(name="cart.changed", data=CART))
    silent = mirror.fold(StageEvent(name="cart.emptied"))
    assert silent is not None and silent.note is None
    assert mirror.read("cart") == "The cart is empty."


def test_an_undeclared_event_or_slice_is_ignored_and_said() -> None:
    mirror = Mirror(load_spec(SPEC))
    assert mirror.fold(StageEvent(name="cart.exploded")) is None
    assert "there are: cart, listing" in mirror.read("wishlist")


def test_the_director_folds_a_state_event_into_its_mirror() -> None:
    spec = load_spec(SPEC)
    sent: list[object] = []
    stage = Stage(dispatch=sent.append, moves=spec.move_set(), mirror=Mirror(spec))
    folded = stage.handle(StageEvent(name="cart.changed", by="agent", data=CART))
    assert folded is not None and folded.note == "[You changed the cart: 3 items]"
    assert stage.mirror is not None and stage.mirror.version("cart") == 1
    assert sent == []
    bare = Stage(dispatch=sent.append, moves=spec.move_set())
    assert bare.handle(StageEvent(name="cart.changed", data=CART)) is None


def test_the_page_events_parse_a_state_event() -> None:
    msg = RTVIMessage(
        type=RTVIType.UI_EVENT,
        data={"event": "stage_event", "payload": {"name": "cart.changed", "data": {"count": 1}}},
    )
    parsed = StagePageEvents.parse(msg)
    assert isinstance(parsed, StageEvent) and parsed.by == "visitor"


@pytest.mark.parametrize(
    ("change", "why"),
    [
        ({"events": [{"id": "cart.changed", "slice": "basket"}]}, "not declared"),
        (
            {"events": [{"id": "cart.changed", "slice": "cart", "note": "{email} changed"}]},
            "plain, public",
        ),
        (
            {"events": [{"id": "cart.changed", "slice": "cart", "note": "{items} changed"}]},
            "plain, public",
        ),
        (
            {"slices": [{"id": "cart", "fields": [{"name": "a", "type": "object"}]}]},
            "needs its fields",
        ),
        (
            {"slices": [{"id": "cart", "fields": [{"name": "a"}, {"name": "a"}]}]},
            "names a field twice",
        ),
    ],
)
def test_a_bad_slice_or_event_fails_when_the_spec_is_loaded(
    change: dict[str, Any], why: str
) -> None:
    with pytest.raises(ValidationError, match=why):
        load_spec({**SPEC, **change})


def test_the_generated_python_gives_the_read_tool_its_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = render_python(load_spec(SPEC), source="s.json", command="c")
    module = types.ModuleType("stage_gen_slices")
    monkeypatch.setitem(sys.modules, module.__name__, module)
    exec(compile(text, "stage_gen.py", "exec"), module.__dict__)
    assert module.ReadRequest(slice="cart").slice == "cart"
    with pytest.raises(ValidationError):
        module.ReadRequest(slice="wishlist")
    schema = module.ReadRequest.model_json_schema()
    assert "cart: what is in their cart" in schema["properties"]["slice"]["description"]


def test_the_typescript_keeps_private_marks_and_drops_notes() -> None:
    text = render_typescript(load_spec(SPEC), source="s.json", command="c")
    assert '"private": true' in text
    assert "changed the cart" not in text
    assert "what is in their cart" not in text


def test_a_value_of_another_shape_is_dropped_whatever_it_holds() -> None:
    """A page that sends an object where names were declared keeps nothing of it."""
    mirror = Mirror(load_spec(SPEC))
    leaky = {
        "count": "3",
        "subtotal": True,
        "items": [{"name": "Toalla", "qty": 1}, "not an item"],
        "email": "a@b.c",
    }
    mirror.fold(StageEvent(name="cart.changed", data=leaky))
    assert mirror.value("cart") == {"items": [{"name": "Toalla", "qty": 1}]}
    mirror.fold(StageEvent(name="listing.sorted", data={"title": {"secret": "x"}, "sort": None}))
    assert mirror.value("listing") == {"sort": None}


def test_the_same_state_reported_again_changes_nothing() -> None:
    """Dev call 84c62a64: the cart, unchanged, came again with every page load
    the agent's moves made, and the model was told three times it had changed
    the cart."""
    mirror = Mirror(load_spec(SPEC))
    first = mirror.fold(StageEvent(name="cart.changed", by="agent", data=CART))
    again = mirror.fold(StageEvent(name="cart.changed", by="agent", data=CART))
    assert first is not None and first.changed and first.note
    assert again is not None and not again.changed and again.note is None
    assert again.version == first.version == 1
    mirror.fold(StageEvent(name="listing.sorted", data={"sort": "price_asc"}))
    same = mirror.fold(StageEvent(name="listing.sorted", data={"sort": "price_asc"}))
    assert same is not None and not same.changed
