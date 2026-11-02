# Generated from demos/fernhollow/frontend/src/stage/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
#   voqalize stage gen demos/fernhollow/frontend/src/stage/scene.json --py demos/fernhollow/backend/stage_gen.py --ts demos/fernhollow/frontend/src/stage/scene.gen.ts
"""The moves of fernhollow_returns, from its Stage Spec."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from voqalize.sdk.stage import Move, MoveClass, MoveSet, StageSpec, load_spec

#: The spec itself, carried here so the brain never reads the JSON at run
#: time (and a deploy that ships this file ships the spec with it).
SPEC: StageSpec = load_spec(
    '{"events":[{"doc":"A field of the returns form was filled or changed.","id":"returns.field_filled","note":"{by} filled {field} on the returns form","slice":"returns_form"},{"doc":"The returns form moved to another step.","id":"returns.step_reached","note":"{by} is on step {step} of the returns form","slice":"returns_form"},{"ask":"thank them and say what happens next, in one line","doc":"The shopper pressed Submit return.","id":"returns.return_submitted","note":"{by} submitted the return {reference}","react":"speak","slice":"returns_form"},{"ask":"offer to fill it in, one short line","doc":"The visitor stayed on another part of the page.","id":"view.changed","note":"{by} is reading {label}","op":"set","react":"speak","slice":"view"},{"doc":"The visitor filled or emptied fields of a form, and then paused.","id":"form.changed","note":"{by} is filling in {form}: {left} required fields left","op":"set","slice":"form"}],"id":"fernhollow_returns","kits":[{"events":{"view.changed":{"ask":"offer to fill it in, one short line","react":"speak"}},"id":"watch","major":1}],"languages":["en"],"moves":[{"args":[{"doc":"The order\'s number, FH-20418.","name":"order_number"},{"doc":"The email used for the order, as the shopper said it.","name":"email","optional":true}],"class":"reversible","doc":"Fill step 1 with the order number and email and look the order up exactly as the Find button does; on success the form moves to step 2. Refused with the reason: no such order, email mismatch, not delivered, outside the window.","id":"returns.find","say":"{find: FH-20418 | sam.rivera@example.com} fills step 1 and looks the order up, as the Find button does.","verb":"find"},{"class":"reversible","doc":"Validate the step in front like the Continue button and move to the next one. Refused, naming the missing fields.","id":"returns.next_step","say":"{next} moves the returns form on to its next step, as Continue does.","verb":"next"},{"args":[{"doc":"A step already reached, 1 to 6: 1 find your order, 2 items, 3 reason, 4 resolution, 5 collection, 6 review.","name":"step","type":"integer"}],"class":"look","doc":"Open a step of the returns form the form has already reached, and ring it.","id":"returns.open_step","say":"{step: 3} as you start talking about that step of the returns form; it opens, scrolls into view and is ringed.","verb":"step"},{"args":[{"doc":"A field of the returns form by its name: order_number, email, reason, condition, resolution, exchange_variant_<product_id>, collection, pickup_window.","name":"field"},{"doc":"One of the field\'s values as the form names them: doesnt_suit_room, unused_in_packaging, refund, pickup, weekday_morning. For order_number the order number, FH-20418; for email the address the shopper said.","name":"value"}],"claims":["putting down","filling in","i\'ll put"],"class":"reversible","doc":"Set one field of the returns form, as the voice says it. Refused, with the field\'s values, when the value is not one of them.","id":"returns.fill","objects":["form","field","return"],"say":"{fill: reason | doesnt_suit_room} at the start of the sentence that says it, one field per sentence: \\"Let\'s put down that it doesn\'t suit the room.\\"","verb":"fill"},{"args":[{"doc":"The order line\'s product id, as find_order gives it.","name":"product_id"},{"default":1,"doc":"How many to return, 1 up to the number ordered (a numeral, \\"1\\", is read as 1); 0 takes the item off the return.","name":"qty","type":"integer"}],"claims":["returning the","adding the"],"class":"reversible","doc":"Choose an item of the order to return, and how many.","id":"returns.select_item","objects":["item","return"],"say":"{item: product-id | 1} as you name an item of the order being returned.","verb":"item"},{"claims":["submitting your return","sending your return"],"class":"confirmed","doc":"Press Submit return, once the shopper has said yes. Refused, naming the step, while a step still needs something.","id":"returns.submit","objects":["return"]},{"args":[{"doc":"A facet of the rail, as listing_viewed names it: Material, Finish, Category, On sale, Price.","name":"facet"},{"doc":"One of that facet\'s values as the rail lists it: Ceramic, Walnut; for a bands facet, a band\'s label (Under $300); for a toggle, its name.","name":"value"}],"claims":["filtering by","filtering to","showing only"],"class":"reversible","doc":"Turn on one value of any options, toggle or bands facet on the listing in front, exactly as a click does: the grid, the count and the address update in place. Refused, with that facet\'s values, when this page does not offer it.","id":"listing.filter","objects":["filter"],"say":"{filter: Material | Ceramic} as you say it; the option is ringed and ticked on the page\'s own filter rail.","verb":"filter"},{"args":[{"doc":"The rail\'s filter: Material.","name":"facet"},{"doc":"The value to turn off; left out, the facet\'s value that is on (or its range).","name":"value","optional":true}],"class":"reversible","doc":"Untick one option that is on. Refused, with the options that are on, when it is not.","id":"listing.unfilter","say":"{unfilter: Material | Ceramic} as you take that filter off.","verb":"unfilter"},{"class":"reversible","doc":"Take every filter on the listing in front off.","id":"listing.clear_filters","say":"{clear} as you say the filters are off.","verb":"clear"},{"args":[{"doc":"A bands or range facet: Price.","name":"facet"},{"doc":"The lower bound.","name":"min","optional":true,"type":"integer"},{"doc":"The upper bound.","name":"max","optional":true,"type":"integer"}],"class":"reversible","doc":"Set a bands or range facet to [min, max]. On a bands facet a span that is exactly one band presses that band; a span across bands rings each band it takes in and sets the span; a span no band reaches is refused with the bands. Both left out takes the facet off.","id":"listing.range","say":"{range: Price | | 300} for up to 300, {range: Price | 300 | 400} for a span.","verb":"range"},{"args":[{"doc":"The lowest price in dollars.","name":"min","optional":true,"type":"integer"},{"doc":"The highest price in dollars.","name":"max","optional":true,"type":"integer"}],"class":"reversible","doc":"The same as listing.range on the page\'s Price facet; kept for the older name.","id":"listing.price","say":"{price: | 500} for up to $500, {price: 200 | 800} for a range.","verb":"price"},{"args":[{"doc":"The page\'s sort, as it names it: Featured, Price, low to high, Price, high to low, On sale first.","name":"by"}],"class":"reversible","doc":"Choose the listing\'s sort with its own control.","id":"listing.sort","say":"{sort: Price, low to high} as you say how the pieces are ordered.","verb":"sort"}],"slices":[{"doc":"the returns form: the step in front and which fields hold something, by name, never their values","fields":[{"doc":"The step in front, 1 to 6.","name":"step","optional":true,"type":"integer"},{"doc":"The field that just changed, by name.","name":"field","optional":true},{"doc":"The names of the fields that hold something.","name":"filled","type":"array"},{"doc":"The return\'s reference, once submitted: RT-20418-1.","name":"reference","optional":true}],"id":"returns_form"},{"doc":"the part of the page the visitor has stayed on, by its heading","fields":[{"name":"thing"},{"name":"label"}],"id":"view"},{"doc":"the form the visitor is filling in: which fields hold something and which required ones are still empty, by name, never their values","fields":[{"name":"form"},{"name":"filled","type":"array"},{"name":"missing","type":"array"},{"name":"left","type":"integer"},{"name":"done","type":"boolean"}],"id":"form"}],"stage":1}'
)
#: The spec's hash: a page reading another spec reports a different one.
SPEC_SHA256 = "fed4a1a6733f8d2b46df3c261445a3b4883fb1166811d5a40574aaabb3c76df1"


class FindArgs(BaseModel):
    """The arguments of ``returns.find``."""

    order_number: str
    """The order's number, FH-20418."""
    email: str | None = None
    """The email used for the order, as the shopper said it."""


class NextStepArgs(BaseModel):
    """``returns.next_step`` takes none."""


class OpenStepArgs(BaseModel):
    """The arguments of ``returns.open_step``."""

    step: int
    """A step already reached, 1 to 6: 1 find your order, 2 items, 3 reason, 4 resolution, 5 collection, 6 review."""


class FillArgs(BaseModel):
    """The arguments of ``returns.fill``."""

    field: str
    """A field of the returns form by its name: order_number, email, reason, condition, resolution, exchange_variant_<product_id>, collection, pickup_window."""
    value: str
    """One of the field's values as the form names them: doesnt_suit_room, unused_in_packaging, refund, pickup, weekday_morning. For order_number the order number, FH-20418; for email the address the shopper said."""


class SelectItemArgs(BaseModel):
    """The arguments of ``returns.select_item``."""

    product_id: str
    """The order line's product id, as find_order gives it."""
    qty: int = 1
    """How many to return, 1 up to the number ordered (a numeral, "1", is read as 1); 0 takes the item off the return."""


class SubmitArgs(BaseModel):
    """``returns.submit`` takes none."""


class FilterArgs(BaseModel):
    """The arguments of ``listing.filter``."""

    facet: str
    """A facet of the rail, as listing_viewed names it: Material, Finish, Category, On sale, Price."""
    value: str
    """One of that facet's values as the rail lists it: Ceramic, Walnut; for a bands facet, a band's label (Under $300); for a toggle, its name."""


class UnfilterArgs(BaseModel):
    """The arguments of ``listing.unfilter``."""

    facet: str
    """The rail's filter: Material."""
    value: str | None = None
    """The value to turn off; left out, the facet's value that is on (or its range)."""


class ClearFiltersArgs(BaseModel):
    """``listing.clear_filters`` takes none."""


class RangeArgs(BaseModel):
    """The arguments of ``listing.range``."""

    facet: str
    """A bands or range facet: Price."""
    min: int | None = None
    """The lower bound."""
    max: int | None = None
    """The upper bound."""


class PriceArgs(BaseModel):
    """The arguments of ``listing.price``."""

    min: int | None = None
    """The lowest price in dollars."""
    max: int | None = None
    """The highest price in dollars."""


class SortArgs(BaseModel):
    """The arguments of ``listing.sort``."""

    by: str
    """The page's sort, as it names it: Featured, Price, low to high, Price, high to low, On sale first."""


FIND = Move(
    id="returns.find",
    verb="find",
    cls=MoveClass.REVERSIBLE,
    args=(
        "order_number",
        "email",
    ),
    say="{find: FH-20418 | sam.rivera@example.com} fills step 1 and looks the order up, as the Find button does.",
)
"""Fill step 1 with the order number and email and look the order up exactly as the Find button does; on success the form moves to step 2. Refused with the reason: no such order, email mismatch, not delivered, outside the window."""

NEXT_STEP = Move(
    id="returns.next_step",
    verb="next",
    cls=MoveClass.REVERSIBLE,
    say="{next} moves the returns form on to its next step, as Continue does.",
)
"""Validate the step in front like the Continue button and move to the next one. Refused, naming the missing fields."""

OPEN_STEP = Move(
    id="returns.open_step",
    verb="step",
    cls=MoveClass.LOOK,
    args=("step",),
    say="{step: 3} as you start talking about that step of the returns form; it opens, scrolls into view and is ringed.",
)
"""Open a step of the returns form the form has already reached, and ring it."""

FILL = Move(
    id="returns.fill",
    verb="fill",
    cls=MoveClass.REVERSIBLE,
    args=(
        "field",
        "value",
    ),
    say="{fill: reason | doesnt_suit_room} at the start of the sentence that says it, one field per sentence: \"Let's put down that it doesn't suit the room.\"",
    claims=(
        "putting down",
        "filling in",
        "i'll put",
    ),
    objects=(
        "form",
        "field",
        "return",
    ),
)
"""Set one field of the returns form, as the voice says it. Refused, with the field's values, when the value is not one of them."""

SELECT_ITEM = Move(
    id="returns.select_item",
    verb="item",
    cls=MoveClass.REVERSIBLE,
    args=(
        "product_id",
        "qty",
    ),
    say="{item: product-id | 1} as you name an item of the order being returned.",
    claims=(
        "returning the",
        "adding the",
    ),
    objects=(
        "item",
        "return",
    ),
)
"""Choose an item of the order to return, and how many."""

SUBMIT = Move(
    id="returns.submit",
    verb=None,
    cls=MoveClass.CONFIRMED,
    claims=(
        "submitting your return",
        "sending your return",
    ),
    objects=("return",),
)
"""Press Submit return, once the shopper has said yes. Refused, naming the step, while a step still needs something."""

FILTER = Move(
    id="listing.filter",
    verb="filter",
    cls=MoveClass.REVERSIBLE,
    args=(
        "facet",
        "value",
    ),
    say="{filter: Material | Ceramic} as you say it; the option is ringed and ticked on the page's own filter rail.",
    claims=(
        "filtering by",
        "filtering to",
        "showing only",
    ),
    objects=("filter",),
)
"""Turn on one value of any options, toggle or bands facet on the listing in front, exactly as a click does: the grid, the count and the address update in place. Refused, with that facet's values, when this page does not offer it."""

UNFILTER = Move(
    id="listing.unfilter",
    verb="unfilter",
    cls=MoveClass.REVERSIBLE,
    args=(
        "facet",
        "value",
    ),
    say="{unfilter: Material | Ceramic} as you take that filter off.",
)
"""Untick one option that is on. Refused, with the options that are on, when it is not."""

CLEAR_FILTERS = Move(
    id="listing.clear_filters",
    verb="clear",
    cls=MoveClass.REVERSIBLE,
    say="{clear} as you say the filters are off.",
)
"""Take every filter on the listing in front off."""

RANGE = Move(
    id="listing.range",
    verb="range",
    cls=MoveClass.REVERSIBLE,
    args=(
        "facet",
        "min",
        "max",
    ),
    say="{range: Price | | 300} for up to 300, {range: Price | 300 | 400} for a span.",
)
"""Set a bands or range facet to [min, max]. On a bands facet a span that is exactly one band presses that band; a span across bands rings each band it takes in and sets the span; a span no band reaches is refused with the bands. Both left out takes the facet off."""

PRICE = Move(
    id="listing.price",
    verb="price",
    cls=MoveClass.REVERSIBLE,
    args=(
        "min",
        "max",
    ),
    say="{price: | 500} for up to $500, {price: 200 | 800} for a range.",
)
"""The same as listing.range on the page's Price facet; kept for the older name."""

SORT = Move(
    id="listing.sort",
    verb="sort",
    cls=MoveClass.REVERSIBLE,
    args=("by",),
    say="{sort: Price, low to high} as you say how the pieces are ordered.",
)
"""Choose the listing's sort with its own control."""

MOVES = MoveSet(
    (
        FIND,
        NEXT_STEP,
        OPEN_STEP,
        FILL,
        SELECT_ITEM,
        SUBMIT,
        FILTER,
        UNFILTER,
        CLEAR_FILTERS,
        RANGE,
        PRICE,
        SORT,
    )
)

#: The line each cue is taught with, in the spec's order.
PROMPT_LINES: tuple[str, ...] = (
    "{find: FH-20418 | sam.rivera@example.com} fills step 1 and looks the order up, as the Find button does.",
    "{next} moves the returns form on to its next step, as Continue does.",
    "{step: 3} as you start talking about that step of the returns form; it opens, scrolls into view and is ringed.",
    "{fill: reason | doesnt_suit_room} at the start of the sentence that says it, one field per sentence: \"Let's put down that it doesn't suit the room.\"",
    "{item: product-id | 1} as you name an item of the order being returned.",
    "{filter: Material | Ceramic} as you say it; the option is ringed and ticked on the page's own filter rail.",
    "{unfilter: Material | Ceramic} as you take that filter off.",
    "{clear} as you say the filters are off.",
    "{range: Price | | 300} for up to 300, {range: Price | 300 | 400} for a span.",
    "{price: | 500} for up to $500, {price: 200 | 800} for a range.",
    "{sort: Price, low to high} as you say how the pieces are ordered.",
)

#: The slices of the page's state a read may name.
SliceId = Literal["returns_form", "view", "form"]


class ReadRequest(BaseModel):
    """What the read tool takes: the slice to read, from the brain's mirror."""

    slice: SliceId = Field(
        description="Which part of their screen to read. returns_form: the returns form: the step in front and which fields hold something, by name, never their values; view: the part of the page the visitor has stayed on, by its heading; form: the form the visitor is filling in: which fields hold something and which required ones are still empty, by name, never their values."
    )
