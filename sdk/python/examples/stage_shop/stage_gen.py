# Generated from examples/stage_shop/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
#   voqalize stage gen examples/stage_shop/scene.json --py examples/stage_shop/stage_gen.py --json examples/stage_shop/scene.page.json
"""The moves of shop, from its Stage Spec."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from voqalize.sdk.stage import Move, MoveClass, MoveSet, StageSpec, load_spec

#: The spec itself, carried here so the brain never reads the JSON at run
#: time (and a deploy that ships this file ships the spec with it).
SPEC: StageSpec = load_spec(
    '{"events":[{"id":"listing.shown","note":"{by} opened the listing {title}: {count} products","op":"set","slice":"listing"},{"id":"listing.filtered","note":"{by} changed the listing\'s filters: {count} products","op":"set","slice":"listing"},{"id":"listing.sorted","note":"{by} sorted the listing","op":"set","slice":"listing"},{"id":"cart.changed","note":"{by} changed the cart: {count} items","op":"set","slice":"cart"}],"id":"shop","kits":[{"id":"commerce","major":1,"moves":["commerce.filter","commerce.cart_add"]}],"languages":["en"],"moves":[{"args":[{"doc":"A part of the page, by the heading the visitor sees.","name":"target"}],"class":"look","doc":"Scroll to a part of the page and ring it.","id":"core.show","say":"{show: Heading} scrolls to that part of the page and rings it.","verb":"show"},{"args":[{"doc":"The filter as the listing names it: Tamaño, Color.","name":"facet"},{"doc":"One option as the listing writes it, or several joined by commas.","name":"value","optional":true},{"doc":"The listing\'s path, when it is not the one in front; it is opened first.","name":"path","optional":true}],"claims":["filtering by","filtro por","filtrando por"],"class":"reversible","doc":"Apply one filter of the listing in front, one option or several of it, with the listing\'s own control.","id":"commerce.filter","objects":["filter","filtro"],"say":"{filter: Facet | Option} as you name a filter of the listing in front, one per sentence; {filter: Facet | Option, Option} for several options of one filter.","verb":"filter"},{"args":[{"doc":"The item\'s path; it is opened first when it is not in front.","name":"path"},{"default":1,"name":"qty","type":"integer"}],"claims":["adding * to your cart","agrego * al carro","agregando * al carro"],"class":"confirmed","doc":"Add an item to the cart, once the visitor said yes. Never the checkout.","id":"commerce.cart_add","objects":["cart","carro","carrito"]}],"slices":[{"doc":"the listing in front: its title, how many it shows, the filters on and offered, the order, the first items","fields":[{"name":"path"},{"name":"title"},{"name":"count","optional":true,"type":"integer"},{"fields":[{"name":"facet"},{"name":"on","type":"array"},{"name":"options","type":"array"}],"name":"filters","type":"array"},{"name":"sort","optional":true},{"fields":[{"name":"path"},{"name":"name"},{"name":"price","optional":true,"type":"number"},{"doc":"The price before a discount.","name":"regular_price","optional":true,"type":"number"}],"name":"items","type":"array"}],"id":"listing"},{"doc":"what is in their cart: each line, how many, the subtotal","fields":[{"name":"count","type":"integer"},{"name":"subtotal","optional":true,"type":"number"},{"fields":[{"name":"path"},{"name":"name"},{"name":"qty","type":"integer"},{"name":"price","optional":true,"type":"number"}],"name":"items","type":"array"},{"doc":"What is left to spend for free shipping, when the store says.","name":"free_shipping_left","optional":true,"type":"number"}],"id":"cart"}],"stage":1}'
)
#: The spec's hash: a page reading another spec reports a different one.
SPEC_SHA256 = "a6cec2f59743668a0918f952f811a72fe1864fc3b2cc29a1381f6d51bb00f3a1"


class ShowArgs(BaseModel):
    """The arguments of ``core.show``."""

    target: str
    """A part of the page, by the heading the visitor sees."""


class FilterArgs(BaseModel):
    """The arguments of ``commerce.filter``."""

    facet: str
    """The filter as the listing names it: Tamaño, Color."""
    value: str | None = None
    """One option as the listing writes it, or several joined by commas."""
    path: str | None = None
    """The listing's path, when it is not the one in front; it is opened first."""


class CartAddArgs(BaseModel):
    """The arguments of ``commerce.cart_add``."""

    path: str
    """The item's path; it is opened first when it is not in front."""
    qty: int = 1


SHOW = Move(
    id="core.show",
    verb="show",
    cls=MoveClass.LOOK,
    args=("target",),
    say="{show: Heading} scrolls to that part of the page and rings it.",
)
"""Scroll to a part of the page and ring it."""

FILTER = Move(
    id="commerce.filter",
    verb="filter",
    cls=MoveClass.REVERSIBLE,
    args=(
        "facet",
        "value",
        "path",
    ),
    say="{filter: Facet | Option} as you name a filter of the listing in front, one per sentence; {filter: Facet | Option, Option} for several options of one filter.",
    claims=(
        "filtering by",
        "filtro por",
        "filtrando por",
    ),
    objects=(
        "filter",
        "filtro",
    ),
)
"""Apply one filter of the listing in front, one option or several of it, with the listing's own control."""

CART_ADD = Move(
    id="commerce.cart_add",
    verb=None,
    cls=MoveClass.CONFIRMED,
    args=(
        "path",
        "qty",
    ),
    claims=(
        "adding * to your cart",
        "agrego * al carro",
        "agregando * al carro",
    ),
    objects=(
        "cart",
        "carro",
        "carrito",
    ),
)
"""Add an item to the cart, once the visitor said yes. Never the checkout."""

MOVES = MoveSet(
    (
        SHOW,
        FILTER,
        CART_ADD,
    )
)

#: The line each cue is taught with, in the spec's order.
PROMPT_LINES: tuple[str, ...] = (
    "{show: Heading} scrolls to that part of the page and rings it.",
    "{filter: Facet | Option} as you name a filter of the listing in front, one per sentence; {filter: Facet | Option, Option} for several options of one filter.",
)

#: The slices of the page's state a read may name.
SliceId = Literal["listing", "cart"]


class ReadRequest(BaseModel):
    """What the read tool takes: the slice to read, from the brain's mirror."""

    slice: SliceId = Field(
        description="Which part of their screen to read. listing: the listing in front: its title, how many it shows, the filters on and offered, the order, the first items; cart: what is in their cart: each line, how many, the subtotal."
    )
