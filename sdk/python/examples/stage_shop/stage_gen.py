# Generated from examples/stage_shop/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
#   voqalize stage gen examples/stage_shop/scene.json --py examples/stage_shop/stage_gen.py --json examples/stage_shop/scene.page.json
"""The moves of shop, from its Stage Spec."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from voqalize.sdk.stage import Move, MoveClass, MoveSet

#: The spec's hash: a page reading another spec reports a different one.
SPEC_SHA256 = "18ff4de400cf0581951307a2d1aa4379afdace9c5bb569711703af47b531fd61"


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
