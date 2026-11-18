# Generated from demos/fernhollow/frontend/src/stage/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
#   voqalize stage gen demos/fernhollow/frontend/src/stage/scene.json --py demos/fernhollow/backend/stage_gen.py --ts demos/fernhollow/frontend/src/stage/scene.gen.ts
"""The moves of fernhollow, from its Stage Spec."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from voqalize.sdk.stage import Move, MoveClass, MoveSet, StageSpec, load_spec

#: The spec itself, carried here so the brain never reads the JSON at run
#: time (and a deploy that ships this file ships the spec with it).
SPEC: StageSpec = load_spec(
    '{"events":[{"doc":"A field of the returns form was filled or changed.","id":"returns.field_filled","note":"{by} filled {field} on the returns form","slice":"returns_form"},{"doc":"The returns form moved to another step.","id":"returns.step_reached","note":"{by} is on step {step} of the returns form","slice":"returns_form"},{"ask":"thank them and say what happens next, in one line","doc":"The shopper pressed Submit return.","id":"returns.return_submitted","note":"{by} submitted the return {reference}","react":"speak","slice":"returns_form"},{"doc":"A size-finder question was answered (the size the guide picked rides along).","id":"size.answered","note":"{by} answered {question}: {value} on the size finder","slice":"size_finder"},{"doc":"A gift-edit control changed.","id":"gifts.changed","note":"{by} set the gift edit to {recipient}, {occasion}, up to {budget} dollars","slice":"gift_edit"},{"doc":"An order\'s tracking was opened.","id":"orders.opened","note":"{by} opened order {order_number}","slice":"orders"},{"doc":"An order\'s delivery day was changed and saved.","id":"orders.delivery_changed","note":"{by} moved the delivery of {order_number} to {slot}","slice":"orders"},{"doc":"The kiosk moved to another screen: attract, room, feel, budget or picks.","id":"kiosk.screen","note":"the kiosk is on {screen}","slice":"kiosk"},{"doc":"A kiosk question was answered.","id":"kiosk.answered","note":"{by} chose {value} for {question} on the kiosk","slice":"kiosk"},{"ask":"offer to fill it in, one short line","doc":"The visitor stayed on another part of the page.","id":"view.changed","note":"{by} is reading {label}","op":"set","react":"speak","slice":"view"},{"doc":"The visitor filled or emptied fields of a form, and then paused.","id":"form.changed","note":"{by} is filling in {form}: {left} required fields left","op":"set","slice":"form"}],"id":"fernhollow","kits":[{"events":{"view.changed":{"ask":"offer to fill it in, one short line","react":"speak"}},"id":"watch","major":1}],"languages":["en"],"moves":[{"args":[{"doc":"The order\'s number, FH-20418.","name":"order_number"},{"doc":"The email used for the order, as the shopper said it.","name":"email","optional":true}],"class":"reversible","doc":"Fill step 1 with the order number and email and look the order up exactly as the Find button does; on success the form moves to step 2. Refused with the reason: no such order, email mismatch, not delivered, outside the window.","id":"returns.find","say":"{find: FH-20418 | sam.rivera@example.com} fills step 1 and looks the order up, as the Find button does.","verb":"find"},{"class":"reversible","doc":"Validate the step in front like the Continue button and move to the next one. Refused, naming the missing fields.","id":"returns.next_step","say":"{next} moves the returns form on to its next step, as Continue does.","verb":"next"},{"args":[{"doc":"A step already reached, 1 to 6: 1 find your order, 2 items, 3 reason, 4 resolution, 5 collection, 6 review.","name":"step","type":"integer"}],"class":"look","doc":"Open a step of the returns form the form has already reached, and ring it.","id":"returns.open_step","say":"{step: 3} as you start talking about that step of the returns form; it opens, scrolls into view and is ringed.","verb":"step"},{"args":[{"doc":"A field of the returns form by its name: order_number, email, reason, condition, resolution, exchange_variant_<product_id>, collection, pickup_window.","name":"field"},{"doc":"One of the field\'s values as the form names them: doesnt_suit_room, unused_in_packaging, refund, pickup, weekday_morning. For order_number the order number, FH-20418; for email the address the shopper said.","name":"value"}],"claims":["putting down","filling in","i\'ll put"],"class":"reversible","doc":"Set one field of the returns form, as the voice says it. Refused, with the field\'s values, when the value is not one of them.","id":"returns.fill","objects":["form","field","return"],"say":"{fill: reason | doesnt_suit_room} at the start of the sentence that says it, one field per sentence: \\"Let\'s put down that it doesn\'t suit the room.\\"","verb":"fill"},{"args":[{"doc":"The order line\'s product id, as find_order gives it.","name":"product_id"},{"default":1,"doc":"How many to return, 1 up to the number ordered (a numeral, \\"1\\", is read as 1); 0 takes the item off the return.","name":"qty","type":"integer"}],"claims":["returning the","adding the"],"class":"reversible","doc":"Choose an item of the order to return, and how many.","id":"returns.select_item","objects":["item","return"],"say":"{item: product-id | 1} as you name an item of the order being returned.","verb":"item"},{"claims":["submitting your return","sending your return"],"class":"confirmed","doc":"Press Submit return, once the shopper has said yes. Refused, naming the step, while a step still needs something.","id":"returns.submit","objects":["return"]},{"args":[{"doc":"A size-finder question by its id.","enum":["kind","mattress","sleepers","room","place","layout","drop"],"name":"question"},{"doc":"One of the question\'s option values as content/size_guide.json names them: bed, queen, none, roomy, dining_table, front_legs, floor.","name":"value"}],"claims":["for your","in the size"],"class":"reversible","doc":"On the size guide, ring the finder\'s option and choose it, as a tap does. Choosing what is being sized (kind) clears the answers under it. Refused with the question\'s values when the value is not one of them.","id":"size.answer","objects":["size","guide"]},{"args":[{"doc":"Who it is for, by the gift edit\'s id.","enum":["partner","parent","sibling","friend","host","colleague"],"name":"recipient","optional":true},{"doc":"The occasion, by the gift edit\'s id.","enum":["housewarming","birthday","thank_you","wedding","just_because"],"name":"occasion","optional":true},{"doc":"A budget chip in dollars: 30, 50, 80, 100, 150, 250 or 500.","name":"budget","optional":true,"type":"integer"}],"class":"reversible","doc":"On the gift edit, ring each control given and set it, one after another, as taps do; the short list below follows. Refused with the chips when a budget is not one of them.","id":"gifts.set","objects":["gift","edit"]},{"args":[{"doc":"A sample order\'s number, FH-31207.","name":"order_number"}],"class":"look","doc":"On the orders page, open one order\'s tracking timeline and ring it.","id":"orders.open","objects":["order"]},{"args":[{"doc":"The order\'s number, FH-31207.","name":"order_number"},{"doc":"One of the order\'s authored delivery slots by id, d3-morning.","name":"slot"}],"claims":["moved your delivery","moving your delivery"],"class":"reversible","doc":"Open the order\'s delivery-day picker, ring the slot and choose it, as a tap and Save do. Refused when the order cannot move (it is on the van or delivered) or the slot is not one it offers, with the slots it does offer.","id":"orders.reschedule","objects":["delivery","order"]},{"class":"reversible","doc":"On the showroom kiosk, leave the attract screen for the first question, as a tap on it does.","id":"kiosk.start","objects":["kiosk"]},{"args":[{"doc":"A kiosk question by its id.","enum":["room","feel","budget"],"name":"question"},{"doc":"One of its option values as content/kiosk.json names them: living, warm_wood, 400.","name":"value"}],"class":"reversible","doc":"On the kiosk, ring an option tile and choose it; after the third answer the three picks and the QR code show. Refused with the options when the value is not one of them.","id":"kiosk.answer","objects":["kiosk"]},{"class":"reversible","doc":"Clear the kiosk\'s answers and go back to the attract screen, as Start over does.","id":"kiosk.restart","objects":["kiosk"]}],"slices":[{"doc":"the returns form: the step in front and which fields hold something, by name, never their values","fields":[{"doc":"The step in front, 1 to 6.","name":"step","optional":true,"type":"integer"},{"doc":"The field that just changed, by name.","name":"field","optional":true},{"doc":"The names of the fields that hold something.","name":"filled","type":"array"},{"doc":"The return\'s reference, once submitted: RT-20418-1.","name":"reference","optional":true}],"id":"returns_form"},{"doc":"the size guide\'s finder: the question just answered, its value and the size the guide picked, if any","fields":[{"name":"question","optional":true},{"name":"value","optional":true},{"name":"size","optional":true}],"id":"size_finder"},{"doc":"the gift edit\'s controls: who it is for, the occasion and the budget chip","fields":[{"name":"recipient","optional":true},{"name":"occasion","optional":true},{"name":"budget","optional":true,"type":"integer"}],"id":"gift_edit"},{"doc":"the orders page: the order open and its delivery slot by id","fields":[{"name":"order_number","optional":true},{"name":"slot","optional":true}],"id":"orders"},{"doc":"the showroom kiosk: the screen it is on (attract, room, feel, budget, picks) and the answer just given","fields":[{"name":"screen","optional":true},{"name":"question","optional":true},{"name":"value","optional":true}],"id":"kiosk"},{"doc":"the part of the page the visitor has stayed on, by its heading","fields":[{"name":"thing"},{"name":"label"}],"id":"view"},{"doc":"the form the visitor is filling in: which fields hold something and which required ones are still empty, by name, never their values","fields":[{"name":"form"},{"name":"filled","type":"array"},{"name":"missing","type":"array"},{"name":"left","type":"integer"},{"name":"done","type":"boolean"}],"id":"form"}],"stage":1}'
)
#: The spec's hash: a page reading another spec reports a different one.
SPEC_SHA256 = "64259e444f7dfb12086823142a08d0373ccab6e3ffaefb68c0e1fffee967cb06"


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


class SizeAnswerArgs(BaseModel):
    """The arguments of ``size.answer``."""

    question: Literal["kind", "mattress", "sleepers", "room", "place", "layout", "drop"]
    """A size-finder question by its id."""
    value: str
    """One of the question's option values as content/size_guide.json names them: bed, queen, none, roomy, dining_table, front_legs, floor."""


class SetArgs(BaseModel):
    """The arguments of ``gifts.set``."""

    recipient: Literal["partner", "parent", "sibling", "friend", "host", "colleague"] | None = None
    """Who it is for, by the gift edit's id."""
    occasion: Literal["housewarming", "birthday", "thank_you", "wedding", "just_because"] | None = (
        None
    )
    """The occasion, by the gift edit's id."""
    budget: int | None = None
    """A budget chip in dollars: 30, 50, 80, 100, 150, 250 or 500."""


class OpenArgs(BaseModel):
    """The arguments of ``orders.open``."""

    order_number: str
    """A sample order's number, FH-31207."""


class RescheduleArgs(BaseModel):
    """The arguments of ``orders.reschedule``."""

    order_number: str
    """The order's number, FH-31207."""
    slot: str
    """One of the order's authored delivery slots by id, d3-morning."""


class StartArgs(BaseModel):
    """``kiosk.start`` takes none."""


class KioskAnswerArgs(BaseModel):
    """The arguments of ``kiosk.answer``."""

    question: Literal["room", "feel", "budget"]
    """A kiosk question by its id."""
    value: str
    """One of its option values as content/kiosk.json names them: living, warm_wood, 400."""


class RestartArgs(BaseModel):
    """``kiosk.restart`` takes none."""


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

SIZE_ANSWER = Move(
    id="size.answer",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "question",
        "value",
    ),
    claims=(
        "for your",
        "in the size",
    ),
    objects=(
        "size",
        "guide",
    ),
)
"""On the size guide, ring the finder's option and choose it, as a tap does. Choosing what is being sized (kind) clears the answers under it. Refused with the question's values when the value is not one of them."""

SET = Move(
    id="gifts.set",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "recipient",
        "occasion",
        "budget",
    ),
    objects=(
        "gift",
        "edit",
    ),
)
"""On the gift edit, ring each control given and set it, one after another, as taps do; the short list below follows. Refused with the chips when a budget is not one of them."""

OPEN = Move(
    id="orders.open",
    verb=None,
    cls=MoveClass.LOOK,
    args=("order_number",),
    objects=("order",),
)
"""On the orders page, open one order's tracking timeline and ring it."""

RESCHEDULE = Move(
    id="orders.reschedule",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "order_number",
        "slot",
    ),
    claims=(
        "moved your delivery",
        "moving your delivery",
    ),
    objects=(
        "delivery",
        "order",
    ),
)
"""Open the order's delivery-day picker, ring the slot and choose it, as a tap and Save do. Refused when the order cannot move (it is on the van or delivered) or the slot is not one it offers, with the slots it does offer."""

START = Move(
    id="kiosk.start",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    objects=("kiosk",),
)
"""On the showroom kiosk, leave the attract screen for the first question, as a tap on it does."""

KIOSK_ANSWER = Move(
    id="kiosk.answer",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "question",
        "value",
    ),
    objects=("kiosk",),
)
"""On the kiosk, ring an option tile and choose it; after the third answer the three picks and the QR code show. Refused with the options when the value is not one of them."""

RESTART = Move(
    id="kiosk.restart",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    objects=("kiosk",),
)
"""Clear the kiosk's answers and go back to the attract screen, as Start over does."""

MOVES = MoveSet(
    (
        FIND,
        NEXT_STEP,
        OPEN_STEP,
        FILL,
        SELECT_ITEM,
        SUBMIT,
        SIZE_ANSWER,
        SET,
        OPEN,
        RESCHEDULE,
        START,
        KIOSK_ANSWER,
        RESTART,
    )
)

#: The line each cue is taught with, in the spec's order.
PROMPT_LINES: tuple[str, ...] = (
    "{find: FH-20418 | sam.rivera@example.com} fills step 1 and looks the order up, as the Find button does.",
    "{next} moves the returns form on to its next step, as Continue does.",
    "{step: 3} as you start talking about that step of the returns form; it opens, scrolls into view and is ringed.",
    "{fill: reason | doesnt_suit_room} at the start of the sentence that says it, one field per sentence: \"Let's put down that it doesn't suit the room.\"",
    "{item: product-id | 1} as you name an item of the order being returned.",
)

#: The slices of the page's state a read may name.
SliceId = Literal["returns_form", "size_finder", "gift_edit", "orders", "kiosk", "view", "form"]


class ReadRequest(BaseModel):
    """What the read tool takes: the slice to read, from the brain's mirror."""

    slice: SliceId = Field(
        description="Which part of their screen to read. returns_form: the returns form: the step in front and which fields hold something, by name, never their values; size_finder: the size guide's finder: the question just answered, its value and the size the guide picked, if any; gift_edit: the gift edit's controls: who it is for, the occasion and the budget chip; orders: the orders page: the order open and its delivery slot by id; kiosk: the showroom kiosk: the screen it is on (attract, room, feel, budget, picks) and the answer just given; view: the part of the page the visitor has stayed on, by its heading; form: the form the visitor is filling in: which fields hold something and which required ones are still empty, by name, never their values."
    )
