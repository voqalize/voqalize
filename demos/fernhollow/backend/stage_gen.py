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
    '{"events":[{"doc":"A field of the returns form was filled or changed.","id":"returns.field_filled","note":"{by} filled {field} on the returns form","slice":"returns_form"},{"doc":"The returns form moved to another step.","id":"returns.step_reached","note":"{by} is on step {step} of the returns form","slice":"returns_form"},{"ask":"thank them and say what happens next, in one line","doc":"The shopper pressed Submit return.","id":"returns.return_submitted","note":"{by} submitted the return {reference}","react":"speak","slice":"returns_form"},{"ask":"offer to fill it in, one short line","doc":"The visitor stayed on another part of the page.","id":"view.changed","note":"{by} is reading {label}","op":"set","react":"speak","slice":"view"},{"doc":"The visitor filled or emptied fields of a form, and then paused.","id":"form.changed","note":"{by} is filling in {form}: {left} required fields left","op":"set","slice":"form"}],"id":"fernhollow_returns","kits":[{"events":{"view.changed":{"ask":"offer to fill it in, one short line","react":"speak"}},"id":"watch","major":1}],"languages":["en"],"moves":[{"args":[{"doc":"The step of the returns form, 1 to 6: 1 find your order, 2 items, 3 reason, 4 resolution, 5 collection, 6 review.","name":"step","type":"integer"}],"class":"look","doc":"Open one step of the returns form and ring it.","id":"returns.open_step","say":"{step: 3} as you start talking about that step of the returns form; it opens, scrolls into view and is ringed.","verb":"step"},{"args":[{"doc":"A field of the returns form by its name: order_number, email, reason, condition, resolution, exchange_variant_<product_id>, collection, pickup_window.","name":"field"},{"doc":"One of the field\'s values as the form names them: doesnt_suit_room, unused_in_packaging, refund, pickup, weekday_morning. For order_number the order number, FH-20418; for email the address the shopper said.","name":"value"}],"claims":["putting down","filling in","i\'ll put"],"class":"reversible","doc":"Set one field of the returns form, as the voice says it. Refused, with the field\'s values, when the value is not one of them.","id":"returns.fill","objects":["form","field","return"],"say":"{fill: reason | doesnt_suit_room} at the start of the sentence that says it, one field per sentence: \\"Let\'s put down that it doesn\'t suit the room.\\"","verb":"fill"},{"args":[{"doc":"The order line\'s product id, as find_order gives it.","name":"product_id"},{"default":1,"doc":"How many to return, 1 up to the number ordered; 0 takes the item off the return.","name":"qty","type":"integer"}],"claims":["returning the","adding the"],"class":"reversible","doc":"Choose an item of the order to return, and how many.","id":"returns.select_item","objects":["item","return"],"say":"{item: product-id | 1} as you name an item of the order being returned.","verb":"item"},{"claims":["submitting your return","sending your return"],"class":"confirmed","doc":"Press Submit return, once the shopper has said yes. Refused, naming the step, while a step still needs something.","id":"returns.submit","objects":["return"]}],"slices":[{"doc":"the returns form: the step in front and which fields hold something, by name, never their values","fields":[{"doc":"The step in front, 1 to 6.","name":"step","optional":true,"type":"integer"},{"doc":"The field that just changed, by name.","name":"field","optional":true},{"doc":"The names of the fields that hold something.","name":"filled","type":"array"},{"doc":"The return\'s reference, once submitted: RT-20418-1.","name":"reference","optional":true}],"id":"returns_form"},{"doc":"the part of the page the visitor has stayed on, by its heading","fields":[{"name":"thing"},{"name":"label"}],"id":"view"},{"doc":"the form the visitor is filling in: which fields hold something and which required ones are still empty, by name, never their values","fields":[{"name":"form"},{"name":"filled","type":"array"},{"name":"missing","type":"array"},{"name":"left","type":"integer"},{"name":"done","type":"boolean"}],"id":"form"}],"stage":1}'
)
#: The spec's hash: a page reading another spec reports a different one.
SPEC_SHA256 = "d20742ebb0b1f56be29b4ae78f9809149d87b9f1fbb57e312b768805f0dbcce3"


class OpenStepArgs(BaseModel):
    """The arguments of ``returns.open_step``."""

    step: int
    """The step of the returns form, 1 to 6: 1 find your order, 2 items, 3 reason, 4 resolution, 5 collection, 6 review."""


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
    """How many to return, 1 up to the number ordered; 0 takes the item off the return."""


class SubmitArgs(BaseModel):
    """``returns.submit`` takes none."""


OPEN_STEP = Move(
    id="returns.open_step",
    verb="step",
    cls=MoveClass.LOOK,
    args=("step",),
    say="{step: 3} as you start talking about that step of the returns form; it opens, scrolls into view and is ringed.",
)
"""Open one step of the returns form and ring it."""

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

MOVES = MoveSet(
    (
        OPEN_STEP,
        FILL,
        SELECT_ITEM,
        SUBMIT,
    )
)

#: The line each cue is taught with, in the spec's order.
PROMPT_LINES: tuple[str, ...] = (
    "{step: 3} as you start talking about that step of the returns form; it opens, scrolls into view and is ringed.",
    "{fill: reason | doesnt_suit_room} at the start of the sentence that says it, one field per sentence: \"Let's put down that it doesn't suit the room.\"",
    "{item: product-id | 1} as you name an item of the order being returned.",
)

#: The slices of the page's state a read may name.
SliceId = Literal["returns_form", "view", "form"]


class ReadRequest(BaseModel):
    """What the read tool takes: the slice to read, from the brain's mirror."""

    slice: SliceId = Field(
        description="Which part of their screen to read. returns_form: the returns form: the step in front and which fields hold something, by name, never their values; view: the part of the page the visitor has stayed on, by its heading; form: the form the visitor is filling in: which fields hold something and which required ones are still empty, by name, never their values."
    )
