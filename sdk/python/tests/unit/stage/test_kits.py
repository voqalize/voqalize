"""Kits and plugins: what many apps share, taken by name; what our own code
may do beyond the steps, declared and bounded."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from voqalize.sdk.stage import KITS_DIR, Mirror, StageEvent, load_kit, load_spec
from voqalize.sdk.stage.check import check_spec
from voqalize.sdk.stage.gen import render_typescript
from voqalize.sdk.stage.promises import claim_in, promise_in


def _spec(**more: Any) -> dict[str, Any]:
    return {"stage": 1, "id": "shop", **more}


def test_every_shipped_kit_loads_and_checks_clean() -> None:
    kits = sorted(p.stem for p in KITS_DIR.glob("*.json"))
    assert "commerce" in kits
    for kit_id in kits:
        kit = load_kit(kit_id)
        spec = load_spec(_spec(kits=[{"id": kit_id, "major": int(kit.version.split(".")[0])}]))
        assert [f for f in check_spec(spec) if f.level == "error"] == [], kit_id


def test_a_spec_takes_a_kit_whole_or_in_part() -> None:
    whole = load_spec(_spec(kits=[{"id": "commerce", "major": 1}]))
    assert "commerce.filter" in whole.move_set()
    assert {"filter", "sort"} <= whole.move_set().verbs
    assert {s.id for s in whole.slices} == {"listing", "cart"}
    part = load_spec(_spec(kits=[{"id": "commerce", "major": 1, "moves": ["commerce.sort"]}]))
    assert [m.id for m in part.moves] == ["commerce.sort"]
    assert {s.id for s in part.slices} == {"listing", "cart"}  # its moves report into them


def test_a_kit_merged_once_survives_a_dump_and_a_load() -> None:
    spec = load_spec(_spec(kits=[{"id": "commerce", "major": 1}]))
    again = load_spec(json.loads(spec.model_dump_json(by_alias=True)))
    assert again == spec
    assert again.sha256 == spec.sha256


def test_commerce_1_2_cues_compare_variant_and_cart() -> None:
    kit = load_kit("commerce")
    assert kit.version == "1.2.0"
    moves = {m.id: m for m in kit.moves}
    cues = {m.id: (m.verb, m.cls.value, [a.name for a in m.args]) for m in kit.moves if m.verb}
    assert cues == {
        "commerce.filter": ("filter", "reversible", ["facet", "value", "path"]),
        "commerce.sort": ("sort", "reversible", ["order", "path"]),
        "commerce.compare": ("compare", "look", ["first", "second", "third", "fourth"]),
        "commerce.variant": ("variant", "reversible", ["option", "value"]),
        "commerce.cart_show": ("cart", "look", ["open"]),
    }
    # Two cards at least: the third and fourth may be left out.
    assert [a.required for a in moves["commerce.compare"].args] == [True, True, False, False]
    assert {a.type for a in moves["commerce.compare"].args} == {"integer"}
    # The ones that change what the person owns stay tools.
    assert moves["commerce.cart_add"].verb is None and moves["commerce.cart_update"].verb is None
    spec = load_spec(_spec(kits=[{"id": "commerce", "major": 1}]))
    lines = spec.prompt_lines()
    for verb in ("compare", "variant", "cart"):
        assert spec.move_set().by_verb(verb) is not None
        assert any(line.startswith(f"{{{verb}") for line in lines), verb


@pytest.mark.parametrize(
    ("move_id", "sentence", "promised"),
    [
        ("commerce.compare", "Let me compare the first and the third.", True),
        ("commerce.compare", "Te comparo las dos sábanas.", True),
        ("commerce.compare", "The first is cheaper than the third.", False),
        ("commerce.variant", "I'm choosing the King size for you.", True),
        ("commerce.variant", "Elijo la talla M.", True),
        ("commerce.variant", "I'll pick the variant in blue.", True),
        ("commerce.variant", "It comes in Queen and King.", False),
        ("commerce.cart_show", "Te abro el carro.", True),
        ("commerce.cart_show", "I'm opening your cart now.", True),
        ("commerce.cart_show", "Your cart has two sheets.", False),
    ],
)
def test_commerce_claims_hear_their_promise(move_id: str, sentence: str, promised: bool) -> None:
    move = next(m for m in load_kit("commerce").moves if m.id == move_id).move()
    said = any(claim_in(c, sentence) for c in move.claims) or (
        promise_in(move.objects, sentence) is not None
    )
    assert said is promised


@pytest.mark.parametrize(
    ("kits", "moves", "why"),
    [
        ([{"id": "bank", "major": 1}], [], "no kit 'bank'"),
        ([{"id": "commerce", "major": 2}], [], "the spec wants 2.x"),
        ([{"id": "commerce", "major": 1, "moves": ["commerce.teleport"]}], [], "has no move"),
        (
            [{"id": "commerce", "major": 1}],
            [{"id": "commerce.sort", "verb": "sort", "class": "look"}],
            "is kit 'commerce''s",
        ),
        (
            [{"id": "commerce", "major": 1}],
            [{"id": "shop.sort", "verb": "sort", "class": "reversible"}],
            "share the verb",
        ),
    ],
)
def test_a_kit_taken_wrong_is_refused(kits: list[Any], moves: list[Any], why: str) -> None:
    with pytest.raises(ValidationError, match=why):
        load_spec(_spec(kits=kits, moves=moves))


def test_a_kit_event_folds_into_its_slice() -> None:
    mirror = Mirror(load_spec(_spec(kits=[{"id": "commerce", "major": 1}])))
    folded = mirror.fold(
        StageEvent(name="listing.filtered", data={"path": "/s", "title": "Sábanas", "count": 9})
    )
    assert (
        folded is not None
        and folded.note == "[The visitor changed the listing's filters: 9 products]"
    )


PRICES: dict[str, Any] = {
    "name": "magento.prices",
    "major": 1,
    "side": "page",
    "class": "look",
    "args": [{"name": "paths", "type": "array"}],
    "output": [{"name": "path"}, {"name": "price", "type": "number"}],
    "egress": ["https://www.cannonhome.cl"],
    "deadline_ms": 3000,
}


def test_a_plugin_is_declared_with_its_bounds() -> None:
    spec = load_spec(_spec(plugins=[PRICES]))
    assert spec.plugins[0].egress == ("https://www.cannonhome.cl",)
    ts = render_typescript(spec, source="s", command="c")
    assert '"egress"' in ts and '"magento.prices"' in ts


@pytest.mark.parametrize(
    ("change", "why"),
    [
        ({"class": "confirmed"}, "a page plugin may be look, navigate, reversible, not confirmed"),
        ({"side": "brain", "egress": []}, None),
        ({"side": "brain", "egress": [], "class": "reversible"}, "a brain plugin may be look"),
        ({"side": "brain", "deadline_ms": 20}, "never reaches a customer's site"),
        ({"deadline_ms": 9000}, "within 5000 ms"),
        ({"side": "brain", "egress": [], "deadline_ms": 50}, "within 20 ms"),
        ({"egress": ["http://www.cannonhome.cl"]}, "must be an https origin"),
        ({"egress": ["https://www.cannonhome.cl/graphql"]}, "must be an https origin"),
    ],
)
def test_a_plugin_out_of_bounds_is_refused(change: dict[str, Any], why: str | None) -> None:
    plugin = {**PRICES, **change}
    if why is None:
        brain = {**plugin, "deadline_ms": 20}
        assert load_spec(_spec(plugins=[brain])).plugins[0].side == "brain"
        return
    with pytest.raises(ValidationError, match=why):
        load_spec(_spec(plugins=[plugin]))
