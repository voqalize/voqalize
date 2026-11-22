# Generated from fernhollow/frontend/src/stage/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
#   voqalize stage gen fernhollow/frontend/src/stage/scene.json --py fernhollow/backend/stage_gen.py --ts fernhollow/frontend/src/stage/scene.gen.ts
"""The moves of fernhollow, from its Stage Spec."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from voqalize.sdk.stage import Move, MoveClass, MoveSet, StageSpec, load_spec

#: The spec itself, carried here so the brain never reads the JSON at run
#: time (and a deploy that ships this file ships the spec with it).
SPEC: StageSpec = load_spec(
    '{"events":[{"doc":"A field of the return form was chosen, changed or cleared.","id":"returns.field_filled","note":"{by} set {field} to {value} on the return form","slice":"returns_form"},{"doc":"The return form moved to another step.","id":"returns.step_reached","note":"{by} is on step {step} of the return form","slice":"returns_form"},{"ask":"thank them and say what happens next, in one line","doc":"The shopper pressed Submit return.","id":"returns.return_submitted","note":"{by} submitted the return {reference}","react":"speak","slice":"returns_form"},{"doc":"A gift-edit control changed.","id":"gifts.changed","note":"{by} set the gift edit to {recipient}, {occasion}, budget {budget} dollars (0 is no limit)","slice":"gift_edit"},{"doc":"An order was selected on the orders page.","id":"orders.opened","note":"{by} selected order {order_number}","slice":"orders"},{"doc":"An order\'s delivery day was changed and saved.","id":"orders.delivery_changed","note":"{by} moved the delivery of {order_number} to {slot}","slice":"orders"},{"doc":"A packed order was cancelled.","id":"orders.cancelled","note":"{by} cancelled order {order_number}","slice":"orders"},{"doc":"An earlier delivery was requested for an order on the way.","id":"orders.earlier_requested","note":"{by} asked for an earlier delivery of {order_number}","slice":"orders"},{"doc":"A delivered order\'s return form was opened.","id":"orders.return_started","note":"{by} started a return for order {order_number}","slice":"returns_form"},{"doc":"The kiosk moved to another screen: attract, room, feel, budget or picks.","id":"kiosk.screen","note":"the kiosk is on {screen}","slice":"kiosk"},{"doc":"A kiosk question was answered.","id":"kiosk.answered","note":"{by} chose {value} for {question} on the kiosk","slice":"kiosk"},{"ask":"offer to fill it in, one short line","doc":"The visitor stayed on another part of the page.","id":"view.changed","note":"{by} is reading {label}","op":"set","react":"speak","slice":"view"},{"doc":"The visitor filled or emptied fields of a form, and then paused.","id":"form.changed","note":"{by} is filling in {form}: {left} required fields left","op":"set","slice":"form"}],"id":"fernhollow","kits":[{"events":{"view.changed":{"ask":"offer to fill it in, one short line","react":"speak"}},"id":"watch","major":1}],"languages":["en"],"moves":[{"args":[{"doc":"The order line\'s product id, as start_return gives it.","name":"product_id"},{"default":1,"doc":"How many to return, 1 up to the number ordered (a numeral, \\"1\\", is read as 1); 0 takes the item off the return.","name":"qty","type":"integer"}],"class":"reversible","doc":"On an order\'s return form, tick an item of the order and set how many go back; opens the items step first when the form is on another one. 0 takes the item off. Refused with the order\'s items when the product is not on it.","id":"returns.select_item","objects":["item","return"]},{"args":[{"doc":"A field of the return form by its name: reason, condition, resolution, exchange_variant_<product_id>, collection, pickup_window.","name":"field"},{"doc":"One of the field\'s values as the form names them: doesnt_suit_room, unused_in_packaging, refund, pickup, weekday_morning; for exchange_variant_<product_id> the option value, Walnut.","name":"value"}],"class":"reversible","doc":"On an order\'s return form, ring one choice and choose it, as a tap does; the step that holds the field opens first (once the steps before it are complete). Nothing on the form is chosen before the shopper says it. Refused, with the field\'s values, when the value is not one of them, or naming what an earlier step still needs.","id":"returns.fill","objects":["form","field","return"]},{"args":[{"doc":"A step already reached, 1 to 5: 1 items, 2 reason, 3 resolution, 4 collection, 5 review.","name":"step","type":"integer"}],"class":"look","doc":"Open a step of the return form the form has already reached, and ring it.","id":"returns.open_step"},{"class":"reversible","doc":"Validate the step in front like the Continue button and move to the next one. Refused, naming the missing fields.","id":"returns.next_step","objects":["step","return"]},{"claims":["submitting your return","sending your return"],"class":"confirmed","doc":"Press Submit return, once the shopper has said yes. Refused, naming the step, while a step still needs something.","id":"returns.submit","objects":["return"]},{"args":[{"doc":"An order\'s number, FH-31207.","name":"order_number"}],"class":"look","doc":"On the orders page, select one order: its status, items and the actions its status allows show, ringed.","id":"orders.open","objects":["order"]},{"args":[{"doc":"The order\'s number, FH-31207.","name":"order_number"}],"class":"look","doc":"On a packed order, press Change delivery day: the picker opens with the days it can move to, ringed. Refused when the order cannot move.","id":"orders.show_slots","objects":["delivery","order"]},{"args":[{"doc":"The order\'s number, FH-31207.","name":"order_number"},{"doc":"One of the order\'s authored delivery slots by id, d3-morning.","name":"slot"}],"claims":["moved your delivery","moving your delivery"],"class":"reversible","doc":"Open the order\'s delivery-day picker, ring the day and choose it, as a tap and Save do. Refused when the order cannot move (it is on the way or delivered) or the slot is not one it offers, with the slots it does offer.","id":"orders.reschedule","objects":["delivery","order"]},{"args":[{"doc":"The order\'s number, FH-31207.","name":"order_number"}],"claims":["cancelling your order","cancelled your order"],"class":"confirmed","doc":"Cancel a packed order, as Cancel order and its confirmation do, once the shopper has said yes. Refused once the order is on the way or delivered.","id":"orders.cancel","objects":["order"]},{"args":[{"doc":"The order\'s number, FH-31188.","name":"order_number"}],"class":"reversible","doc":"On an order that is on the way, press Request an earlier delivery: a request to the driver, never a promise. Refused when the order is not on the way.","id":"orders.request_earlier","objects":["delivery","order"]},{"args":[{"doc":"The order\'s number, FH-31042.","name":"order_number"}],"class":"navigate","doc":"On a delivered order, press Start a return: that order\'s return form opens on its first step, nothing chosen. Refused when the order is not delivered yet or is outside the 30-day window.","id":"orders.start_return","objects":["return","order"]},{"args":[{"doc":"Who it is for, by the gift edit\'s id.","enum":["partner","parent","sibling","friend","host","colleague"],"name":"recipient","optional":true},{"doc":"The occasion, by the gift edit\'s id.","enum":["housewarming","birthday","thank_you","wedding","just_because"],"name":"occasion","optional":true},{"doc":"A budget chip in dollars: 30, 50, 80, 100, 150, 250 or 500; 0 is No limit.","name":"budget","optional":true,"type":"integer"}],"class":"reversible","doc":"On the gift edit, ring each control given and set it, one after another, as taps do; the short list shows once who, the occasion and the budget (or No limit) are all set. Refused with the chips when a budget is not one of them.","id":"gifts.set","objects":["gift","edit"]},{"class":"reversible","doc":"On the showroom kiosk, leave the attract screen for the first question, as a tap on it does.","id":"kiosk.start","objects":["kiosk"]},{"args":[{"doc":"A kiosk question by its id.","enum":["room","feel","budget"],"name":"question"},{"doc":"One of its option values as content/kiosk.json names them: living, warm_wood, 400.","name":"value"}],"class":"reversible","doc":"On the kiosk, ring an option tile and choose it; after the third answer the three picks and the QR code show. Refused with the options when the value is not one of them.","id":"kiosk.answer","objects":["kiosk"]},{"class":"reversible","doc":"Clear the kiosk\'s answers and go back to the attract screen, as Start over does.","id":"kiosk.restart","objects":["kiosk"]}],"slices":[{"doc":"an order\'s return form: the order, the step in front, the field that just changed and its value (choices only, never personal data), and which fields hold something","fields":[{"doc":"The order the return is for, FH-31042.","name":"order_number","optional":true},{"doc":"The step in front, 1 to 5: 1 items, 2 reason, 3 resolution, 4 collection, 5 review.","name":"step","optional":true,"type":"integer"},{"doc":"The field that just changed, by name.","name":"field","optional":true},{"doc":"Its value as the form names it (refund, doesnt_suit_room, a qty), or empty when cleared.","name":"value","optional":true},{"doc":"The names of the fields that hold something.","name":"filled","type":"array"},{"doc":"The return\'s reference, once submitted: RT-31042-1.","name":"reference","optional":true}],"id":"returns_form"},{"doc":"the gift edit\'s controls: who it is for, the occasion and the budget chip","fields":[{"name":"recipient","optional":true},{"name":"occasion","optional":true},{"name":"budget","optional":true,"type":"integer"}],"id":"gift_edit"},{"doc":"the orders page: the order selected, its delivery slot by id, and what was just done to it","fields":[{"name":"order_number","optional":true},{"name":"slot","optional":true},{"doc":"packed, on_the_way, delivered or cancelled","name":"status","optional":true}],"id":"orders"},{"doc":"the showroom kiosk: the screen it is on (attract, room, feel, budget, picks) and the answer just given","fields":[{"name":"screen","optional":true},{"name":"question","optional":true},{"name":"value","optional":true}],"id":"kiosk"},{"doc":"the part of the page the visitor has stayed on, by its heading","fields":[{"name":"thing"},{"name":"label"}],"id":"view"},{"doc":"the form the visitor is filling in: which fields hold something and which required ones are still empty, by name, never their values","fields":[{"name":"form"},{"name":"filled","type":"array"},{"name":"missing","type":"array"},{"name":"left","type":"integer"},{"name":"done","type":"boolean"}],"id":"form"}],"stage":1}'
)
#: The spec's hash: a page reading another spec reports a different one.
SPEC_SHA256 = "2864fe8c248c896b581c51d359f8c41b136b2717f06b60fbb33c13391055b359"


class SelectItemArgs(BaseModel):
    """The arguments of ``returns.select_item``."""

    product_id: str
    """The order line's product id, as start_return gives it."""
    qty: int = 1
    """How many to return, 1 up to the number ordered (a numeral, "1", is read as 1); 0 takes the item off the return."""


class FillArgs(BaseModel):
    """The arguments of ``returns.fill``."""

    field: str
    """A field of the return form by its name: reason, condition, resolution, exchange_variant_<product_id>, collection, pickup_window."""
    value: str
    """One of the field's values as the form names them: doesnt_suit_room, unused_in_packaging, refund, pickup, weekday_morning; for exchange_variant_<product_id> the option value, Walnut."""


class OpenStepArgs(BaseModel):
    """The arguments of ``returns.open_step``."""

    step: int
    """A step already reached, 1 to 5: 1 items, 2 reason, 3 resolution, 4 collection, 5 review."""


class NextStepArgs(BaseModel):
    """``returns.next_step`` takes none."""


class SubmitArgs(BaseModel):
    """``returns.submit`` takes none."""


class OpenArgs(BaseModel):
    """The arguments of ``orders.open``."""

    order_number: str
    """An order's number, FH-31207."""


class ShowSlotsArgs(BaseModel):
    """The arguments of ``orders.show_slots``."""

    order_number: str
    """The order's number, FH-31207."""


class RescheduleArgs(BaseModel):
    """The arguments of ``orders.reschedule``."""

    order_number: str
    """The order's number, FH-31207."""
    slot: str
    """One of the order's authored delivery slots by id, d3-morning."""


class CancelArgs(BaseModel):
    """The arguments of ``orders.cancel``."""

    order_number: str
    """The order's number, FH-31207."""


class RequestEarlierArgs(BaseModel):
    """The arguments of ``orders.request_earlier``."""

    order_number: str
    """The order's number, FH-31188."""


class StartReturnArgs(BaseModel):
    """The arguments of ``orders.start_return``."""

    order_number: str
    """The order's number, FH-31042."""


class SetArgs(BaseModel):
    """The arguments of ``gifts.set``."""

    recipient: Literal["partner", "parent", "sibling", "friend", "host", "colleague"] | None = None
    """Who it is for, by the gift edit's id."""
    occasion: Literal["housewarming", "birthday", "thank_you", "wedding", "just_because"] | None = (
        None
    )
    """The occasion, by the gift edit's id."""
    budget: int | None = None
    """A budget chip in dollars: 30, 50, 80, 100, 150, 250 or 500; 0 is No limit."""


class StartArgs(BaseModel):
    """``kiosk.start`` takes none."""


class AnswerArgs(BaseModel):
    """The arguments of ``kiosk.answer``."""

    question: Literal["room", "feel", "budget"]
    """A kiosk question by its id."""
    value: str
    """One of its option values as content/kiosk.json names them: living, warm_wood, 400."""


class RestartArgs(BaseModel):
    """``kiosk.restart`` takes none."""


SELECT_ITEM = Move(
    id="returns.select_item",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "product_id",
        "qty",
    ),
    objects=(
        "item",
        "return",
    ),
)
"""On an order's return form, tick an item of the order and set how many go back; opens the items step first when the form is on another one. 0 takes the item off. Refused with the order's items when the product is not on it."""

FILL = Move(
    id="returns.fill",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "field",
        "value",
    ),
    objects=(
        "form",
        "field",
        "return",
    ),
)
"""On an order's return form, ring one choice and choose it, as a tap does; the step that holds the field opens first (once the steps before it are complete). Nothing on the form is chosen before the shopper says it. Refused, with the field's values, when the value is not one of them, or naming what an earlier step still needs."""

OPEN_STEP = Move(
    id="returns.open_step",
    verb=None,
    cls=MoveClass.LOOK,
    args=("step",),
)
"""Open a step of the return form the form has already reached, and ring it."""

NEXT_STEP = Move(
    id="returns.next_step",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    objects=(
        "step",
        "return",
    ),
)
"""Validate the step in front like the Continue button and move to the next one. Refused, naming the missing fields."""

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

OPEN = Move(
    id="orders.open",
    verb=None,
    cls=MoveClass.LOOK,
    args=("order_number",),
    objects=("order",),
)
"""On the orders page, select one order: its status, items and the actions its status allows show, ringed."""

SHOW_SLOTS = Move(
    id="orders.show_slots",
    verb=None,
    cls=MoveClass.LOOK,
    args=("order_number",),
    objects=(
        "delivery",
        "order",
    ),
)
"""On a packed order, press Change delivery day: the picker opens with the days it can move to, ringed. Refused when the order cannot move."""

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
"""Open the order's delivery-day picker, ring the day and choose it, as a tap and Save do. Refused when the order cannot move (it is on the way or delivered) or the slot is not one it offers, with the slots it does offer."""

CANCEL = Move(
    id="orders.cancel",
    verb=None,
    cls=MoveClass.CONFIRMED,
    args=("order_number",),
    claims=(
        "cancelling your order",
        "cancelled your order",
    ),
    objects=("order",),
)
"""Cancel a packed order, as Cancel order and its confirmation do, once the shopper has said yes. Refused once the order is on the way or delivered."""

REQUEST_EARLIER = Move(
    id="orders.request_earlier",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=("order_number",),
    objects=(
        "delivery",
        "order",
    ),
)
"""On an order that is on the way, press Request an earlier delivery: a request to the driver, never a promise. Refused when the order is not on the way."""

START_RETURN = Move(
    id="orders.start_return",
    verb=None,
    cls=MoveClass.NAVIGATE,
    args=("order_number",),
    objects=(
        "return",
        "order",
    ),
)
"""On a delivered order, press Start a return: that order's return form opens on its first step, nothing chosen. Refused when the order is not delivered yet or is outside the 30-day window."""

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
"""On the gift edit, ring each control given and set it, one after another, as taps do; the short list shows once who, the occasion and the budget (or No limit) are all set. Refused with the chips when a budget is not one of them."""

START = Move(
    id="kiosk.start",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    objects=("kiosk",),
)
"""On the showroom kiosk, leave the attract screen for the first question, as a tap on it does."""

ANSWER = Move(
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
        SELECT_ITEM,
        FILL,
        OPEN_STEP,
        NEXT_STEP,
        SUBMIT,
        OPEN,
        SHOW_SLOTS,
        RESCHEDULE,
        CANCEL,
        REQUEST_EARLIER,
        START_RETURN,
        SET,
        START,
        ANSWER,
        RESTART,
    )
)

#: The line each cue is taught with, in the spec's order.
PROMPT_LINES: tuple[str, ...] = ()

#: The slices of the page's state a read may name.
SliceId = Literal["returns_form", "gift_edit", "orders", "kiosk", "view", "form"]


class ReadRequest(BaseModel):
    """What the read tool takes: the slice to read, from the brain's mirror."""

    slice: SliceId = Field(
        description="Which part of their screen to read. returns_form: an order's return form: the order, the step in front, the field that just changed and its value (choices only, never personal data), and which fields hold something; gift_edit: the gift edit's controls: who it is for, the occasion and the budget chip; orders: the orders page: the order selected, its delivery slot by id, and what was just done to it; kiosk: the showroom kiosk: the screen it is on (attract, room, feel, budget, picks) and the answer just given; view: the part of the page the visitor has stayed on, by its heading; form: the form the visitor is filling in: which fields hold something and which required ones are still empty, by name, never their values."
    )
