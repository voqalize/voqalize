# Generated from belmonte/frontend/src/stage/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
#   voqalize stage gen belmonte/frontend/src/stage/scene.json --py belmonte/backend/stage_gen.py --ts belmonte/frontend/src/stage/scene.gen.ts
"""The moves of belmonte, from its Stage Spec."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from voqalize.sdk.stage import Move, MoveClass, MoveSet, StageSpec, load_spec

#: The spec itself, carried here so the brain never reads the JSON at run
#: time (and a deploy that ships this file ships the spec with it).
SPEC: StageSpec = load_spec(
    '{"events":[{"id":"stay.page","note":"{by} is on the {page} screen","react":"silent","slice":"stay"},{"id":"stay.scenario","note":"{by} switched the demo to {label}","slice":"stay"},{"id":"checkin.step","note":"{by} is on the check-in step {step}","react":"silent","slice":"stay"},{"id":"checkin.confirmed","note":"{by} confirmed the reservation","slice":"stay"},{"id":"checkin.id_verified","note":"{by} scanned their ID and it is verified","slice":"stay"},{"id":"checkin.prefs","note":"{by} set {label}","slice":"stay"},{"id":"checkin.early","note":"{by} set early check-in to {value}","slice":"stay"},{"id":"checkin.done","note":"{by} completed check-in: room {room}","slice":"stay"},{"id":"cart.changed","note":"{by} changed the {outlet} order: {label}","slice":"stay"},{"id":"order.placed","note":"{by} placed the {outlet} order: {label}","slice":"stay"},{"id":"spa.picked","note":"{by} picked {label}","slice":"stay"},{"id":"spa.booked","note":"{by} booked {label}","slice":"stay"},{"id":"activity.picked","note":"{by} set up {label}","slice":"stay"},{"id":"activity.booked","note":"{by} booked {label}","slice":"stay"},{"id":"meeting.picked","note":"{by} set up {label}","slice":"stay"},{"id":"meeting.booked","note":"{by} requested {label}","slice":"stay"},{"id":"visitor.decided","note":"{by} {value} the visitor {label}","slice":"stay"},{"id":"visitor.added","note":"{by} added an expected visitor: {label}","slice":"stay"},{"id":"request.sent","note":"{by} sent a request: {label}","slice":"stay"},{"id":"folio.disputed","note":"{by} questioned the charge {label}","slice":"stay"},{"id":"late.picked","note":"{by} picked late check-out at {label}","slice":"stay"},{"id":"late.requested","note":"{by} requested late check-out at {label}","slice":"stay"},{"id":"checkout.done","note":"{by} checked out: {label}","slice":"stay"},{"id":"sheet.closed","note":"{by} closed the {kind} sheet","react":"silent","slice":"stay"}],"id":"belmonte","languages":["en"],"moves":[{"args":[{"doc":"A screen of the guest app: home, dining (in-room dining menu), bar (drinks menu), spa, activities (things to do and the resort map), meetings (meeting rooms), requests (front desk requests), visitors, stay (the reservation and room key), checkin, checkout, info (hotel information).","enum":["home","dining","bar","spa","activities","meetings","requests","visitors","stay","checkin","checkout","info"],"name":"page"}],"claims":["taking you to","opening the","pulling up the"],"class":"navigate","doc":"Go to a screen of the app, ringing its tab first.","id":"app.go","objects":["menu","spa","activities","meeting rooms","requests","visitors","folio","check-in"],"say":"{go: spa} at the start of the sentence that takes them to another screen: home, dining, bar, spa, activities, meetings, requests, visitors, stay, checkin, checkout or info.","verb":"go"},{"args":[{"doc":"Something on the screen by the name it shows: an item, a treatment, a room, a charge, the total, the key.","name":"target"}],"class":"look","doc":"Scroll to a named thing on the screen and ring it. Changes nothing.","id":"app.show","say":"{show: total} right before the sentence about something on screen, to ring it: an item or a charge by name, the total, a time slot, the key.","verb":"show"},{"claims":["closing that"],"class":"reversible","doc":"Close the sheet that is open over the screen.","id":"sheet.close","objects":["sheet"]},{"args":[{"enum":["checkin","house_rules","quiet","pets","smoking","pools","wifi","parking","dining_hours","fitness","accessibility","contact"],"name":"topic"}],"claims":["opening the policy"],"class":"navigate","doc":"Open hotel information at one section, expanded and ringed.","id":"info.open","objects":["policy","house rules","information"]},{"args":[{"default":"reservation","enum":["reservation","id","room","early","review"],"name":"step"}],"claims":["starting your check-in","opening check-in"],"class":"navigate","doc":"Open the check-in flow at a step it has reached (an earlier one is fine; a later one is refused with what is missing).","id":"checkin.open","objects":["check-in"]},{"claims":["confirming your reservation"],"class":"reversible","doc":"Ring and press \\"Yes, that\'s my reservation\\" on the first step, after the guest said it is theirs.","id":"checkin.confirm","objects":["reservation"]},{"args":[{"enum":["now","15:00","16:00","17:00","19:00"],"name":"arrival","optional":true},{"enum":["high","low","any"],"name":"floor","optional":true},{"enum":["king","queens"],"name":"bed","optional":true},{"enum":["yes","no"],"name":"quiet","optional":true}],"claims":["setting your arrival","noting your preferences"],"class":"reversible","doc":"On the room step, ring and set each preference that is given.","id":"checkin.prefs","objects":["arrival time","preferences","floor"]},{"args":[{"enum":["yes","no"],"name":"want"}],"claims":["adding early check-in"],"class":"reversible","doc":"On the early check-in step, ring and choose whether to take the room now for the fee.","id":"checkin.early","objects":["early check-in"]},{"args":[{"default":"folio","enum":["folio","late","express"],"name":"part"}],"claims":["opening your bill","pulling up your folio"],"class":"navigate","doc":"Open check-out at the folio, the late check-out options or the express check-out review.","id":"checkout.open","objects":["bill","folio","charges","late check-out","check-out"]},{"args":[{"doc":"A folio line id: minibar-1124, spa-1123.","name":"line_id"},{"doc":"What the guest says is wrong, in their words.","name":"reason"},{"default":false,"doc":"Press Send, only after the guest said yes to sending it.","name":"send","type":"boolean"}],"claims":["flagging that charge","questioning that charge"],"class":"reversible","doc":"Ring a folio line and open its question form with the reason filled; with send, press Send to the front desk.","id":"folio.dispute","objects":["charge","dispute"]},{"args":[{"enum":["12:00","13:00","14:00","16:00"],"name":"time"}],"claims":["picking the late check-out"],"class":"reversible","doc":"Ring and select a late check-out option. The guest presses Request.","id":"late.pick","objects":["late check-out"]},{"args":[{"enum":["dining","bar"],"name":"outlet"},{"doc":"dining: breakfast, all_day, late_night. bar: cocktails, beer, wine, zero_proof, bites.","name":"section","optional":true}],"claims":["opening the menu","pulling up the menu"],"class":"navigate","doc":"Open the in-room dining or drinks menu at a section, its tab ringed.","id":"menu.open","objects":["menu","drinks","breakfast","cocktails","wine"]},{"args":[{"enum":["dining","bar"],"name":"outlet"},{"name":"item_id"},{"default":1,"name":"qty","type":"integer"},{"doc":"Option choices as group:choice, side:salad, burger_mods:no_onions; a wine as size:bottle.","name":"choices","optional":true,"type":"array"},{"name":"note","optional":true},{"default":true,"doc":"Press Add to order once the choices are set.","name":"add","type":"boolean"}],"claims":["adding the","adding a","adding two"],"class":"reversible","doc":"Ring an item, open its sheet, set its choices and quantity (each ringed), and add it to the order.","id":"menu.item","objects":["order","item"]},{"args":[{"enum":["dining","bar"],"name":"outlet"},{"name":"item_id"}],"claims":["taking off the","removing the"],"class":"reversible","doc":"Ring an order line and take it off.","id":"cart.remove","objects":["order"]},{"args":[{"enum":["dining","bar"],"name":"outlet"},{"doc":"Extra tip percent: 0, 10, 15 or 20.","name":"tip","optional":true,"type":"integer"},{"enum":["room","cabana"],"name":"deliver_to","optional":true},{"doc":"Cabana number, 1 to 8.","name":"cabana","optional":true}],"claims":["opening your order"],"class":"navigate","doc":"Open the order sheet (lines, charges, delivery time) and set the tip and delivery place if given. The guest presses Place order.","id":"cart.open","objects":["order","cart","basket"]},{"args":[{"enum":["massage","facial","ritual","nails"],"name":"category","optional":true}],"claims":["opening the spa"],"class":"navigate","doc":"Open the spa menu, at a category.","id":"spa.open","objects":["spa","treatments"]},{"args":[{"name":"treatment_id"},{"doc":"YYYY-MM-DD.","name":"date","optional":true},{"doc":"any, female, male, or a therapist id.","name":"therapist","optional":true}],"claims":["checking the times","pulling up the times"],"class":"navigate","doc":"Open a treatment\'s booking sheet with its free times for a date and a therapist preference.","id":"spa.treatment","objects":["times","slots","availability"]},{"args":[{"name":"treatment_id"},{"name":"date"},{"doc":"HH:MM, 24 hour.","name":"time"},{"name":"therapist_id"}],"claims":["holding the","picking the"],"class":"reversible","doc":"Ring and pick a free time with a therapist on the treatment\'s sheet. The guest presses Book.","id":"spa.slot","objects":["slot","appointment","time"]},{"args":[{"name":"activity_id"},{"default":false,"name":"map","type":"boolean"}],"claims":["showing you on the map"],"class":"look","doc":"Ring an activity\'s card; with map, pin and ring its place on the resort map.","id":"activity.show","objects":["map"]},{"args":[{"name":"activity_id"},{"name":"date"},{"name":"time"},{"default":1,"name":"guests","type":"integer"}],"claims":["booking the","reserving the"],"class":"reversible","doc":"Open an activity\'s booking sheet with the date, time and guests set. The guest presses Book.","id":"activity.pick","objects":["booking","spot","tee time","court"]},{"args":[{"name":"headcount","optional":true,"type":"integer"},{"enum":["boardroom","u_shape","classroom","theatre","banquet"],"name":"layout","optional":true},{"name":"date","optional":true}],"claims":["finding a room"],"class":"navigate","doc":"Open meeting rooms with the rooms that fit a headcount and layout, and their availability on a date.","id":"meeting.filter","objects":["meeting rooms","rooms","halls"]},{"args":[{"name":"room_id"},{"name":"date"},{"enum":["morning","afternoon","full","hours"],"name":"block"},{"doc":"HH:MM, for block hours.","name":"start","optional":true},{"doc":"For block hours.","name":"hours","optional":true,"type":"integer"},{"name":"headcount","type":"integer"},{"enum":["boardroom","u_shape","classroom","theatre","banquet"],"name":"layout"},{"doc":"Catering ids: coffee, breakfast, lunch, snack.","name":"catering","optional":true,"type":"array"},{"doc":"AV add-on ids: mics, recording, tech.","name":"av","optional":true,"type":"array"}],"claims":["putting the booking together","setting up the booking"],"class":"reversible","doc":"Open a room\'s booking form with everything set, each field ringed, and the price. The guest presses Request booking.","id":"meeting.pick","objects":["booking","quote"]},{"args":[{"name":"visitor_id"},{"enum":["room","lobby"],"name":"meet","optional":true}],"claims":["opening the request"],"class":"reversible","doc":"Ring a pending visitor and open their request, with where to meet set. The guest presses Approve or Decline.","id":"visitor.open","objects":["visitor","request"]},{"args":[{"name":"name"},{"doc":"HH:MM, start of the arrival window.","name":"arrive_from"},{"doc":"HH:MM, end of the arrival window.","name":"arrive_to"},{"enum":["room","lobby"],"name":"meet","optional":true},{"name":"note","optional":true}],"claims":["adding your visitor"],"class":"reversible","doc":"Fill the expected visitor form. The guest presses Add visitor.","id":"visitor.expect","objects":["visitor","guest list"]},{"args":[{"enum":["housekeeping","maintenance","wakeup","valet","transport","lost_found"],"name":"kind"},{"doc":"housekeeping item ids: towels, pillows, toiletries, robes, crib, turndown, clean, dnd.","name":"items","optional":true,"type":"array"},{"doc":"maintenance issue id: ac, tv, plumbing, lights, door, other.","name":"issue","optional":true},{"doc":"transport option id: house-car, airport, taxi.","name":"option","optional":true},{"name":"date","optional":true},{"doc":"HH:MM.","name":"time","optional":true},{"doc":"Free text: what is wrong, where to, what was lost and where.","name":"details","optional":true},{"default":false,"doc":"Press Send, only after the guest said yes and when it costs nothing.","name":"send","type":"boolean"}],"claims":["sending that to","putting in the request","setting your wake-up call"],"class":"reversible","doc":"Open a front desk request with its fields filled, each ringed; with send, press Send.","id":"request.fill","objects":["request","wake-up call","towels","car"]}],"slices":[{"doc":"the last change on screen, by ids, as the app reports it","fields":[{"name":"page","optional":true},{"name":"scenario","optional":true},{"name":"step","optional":true},{"name":"field","optional":true},{"name":"value","optional":true},{"name":"id","optional":true},{"name":"outlet","optional":true},{"name":"qty","optional":true,"type":"integer"},{"name":"choices","optional":true,"type":"array"},{"name":"date","optional":true},{"name":"time","optional":true},{"name":"therapist","optional":true},{"name":"guests","optional":true,"type":"integer"},{"name":"room","optional":true},{"name":"kind","optional":true},{"name":"total","optional":true,"type":"number"},{"name":"label","optional":true}],"id":"stay"}],"stage":1}'
)
#: The spec's hash: a page reading another spec reports a different one.
SPEC_SHA256 = "eb0bd4926d2a85f340417c12d87d539967bcc51857462fde4a4b57e93dd6eb2a"


class GoArgs(BaseModel):
    """The arguments of ``app.go``."""

    page: Literal[
        "home",
        "dining",
        "bar",
        "spa",
        "activities",
        "meetings",
        "requests",
        "visitors",
        "stay",
        "checkin",
        "checkout",
        "info",
    ]
    """A screen of the guest app: home, dining (in-room dining menu), bar (drinks menu), spa, activities (things to do and the resort map), meetings (meeting rooms), requests (front desk requests), visitors, stay (the reservation and room key), checkin, checkout, info (hotel information)."""


class AppShowArgs(BaseModel):
    """The arguments of ``app.show``."""

    target: str
    """Something on the screen by the name it shows: an item, a treatment, a room, a charge, the total, the key."""


class CloseArgs(BaseModel):
    """``sheet.close`` takes none."""


class InfoOpenArgs(BaseModel):
    """The arguments of ``info.open``."""

    topic: Literal[
        "checkin",
        "house_rules",
        "quiet",
        "pets",
        "smoking",
        "pools",
        "wifi",
        "parking",
        "dining_hours",
        "fitness",
        "accessibility",
        "contact",
    ]


class CheckinOpenArgs(BaseModel):
    """The arguments of ``checkin.open``."""

    step: Literal["reservation", "id", "room", "early", "review"] = "reservation"


class ConfirmArgs(BaseModel):
    """``checkin.confirm`` takes none."""


class PrefsArgs(BaseModel):
    """The arguments of ``checkin.prefs``."""

    arrival: Literal["now", "15:00", "16:00", "17:00", "19:00"] | None = None
    floor: Literal["high", "low", "any"] | None = None
    bed: Literal["king", "queens"] | None = None
    quiet: Literal["yes", "no"] | None = None


class EarlyArgs(BaseModel):
    """The arguments of ``checkin.early``."""

    want: Literal["yes", "no"]


class CheckoutOpenArgs(BaseModel):
    """The arguments of ``checkout.open``."""

    part: Literal["folio", "late", "express"] = "folio"


class DisputeArgs(BaseModel):
    """The arguments of ``folio.dispute``."""

    line_id: str
    """A folio line id: minibar-1124, spa-1123."""
    reason: str
    """What the guest says is wrong, in their words."""
    send: bool = False
    """Press Send, only after the guest said yes to sending it."""


class LatePickArgs(BaseModel):
    """The arguments of ``late.pick``."""

    time: Literal["12:00", "13:00", "14:00", "16:00"]


class MenuOpenArgs(BaseModel):
    """The arguments of ``menu.open``."""

    outlet: Literal["dining", "bar"]
    section: str | None = None
    """dining: breakfast, all_day, late_night. bar: cocktails, beer, wine, zero_proof, bites."""


class ItemArgs(BaseModel):
    """The arguments of ``menu.item``."""

    outlet: Literal["dining", "bar"]
    item_id: str
    qty: int = 1
    choices: list[str] | None = None
    """Option choices as group:choice, side:salad, burger_mods:no_onions; a wine as size:bottle."""
    note: str | None = None
    add: bool = True
    """Press Add to order once the choices are set."""


class RemoveArgs(BaseModel):
    """The arguments of ``cart.remove``."""

    outlet: Literal["dining", "bar"]
    item_id: str


class CartOpenArgs(BaseModel):
    """The arguments of ``cart.open``."""

    outlet: Literal["dining", "bar"]
    tip: int | None = None
    """Extra tip percent: 0, 10, 15 or 20."""
    deliver_to: Literal["room", "cabana"] | None = None
    cabana: str | None = None
    """Cabana number, 1 to 8."""


class SpaOpenArgs(BaseModel):
    """The arguments of ``spa.open``."""

    category: Literal["massage", "facial", "ritual", "nails"] | None = None


class TreatmentArgs(BaseModel):
    """The arguments of ``spa.treatment``."""

    treatment_id: str
    date: str | None = None
    """YYYY-MM-DD."""
    therapist: str | None = None
    """any, female, male, or a therapist id."""


class SlotArgs(BaseModel):
    """The arguments of ``spa.slot``."""

    treatment_id: str
    date: str
    time: str
    """HH:MM, 24 hour."""
    therapist_id: str


class ActivityShowArgs(BaseModel):
    """The arguments of ``activity.show``."""

    activity_id: str
    map: bool = False


class ActivityPickArgs(BaseModel):
    """The arguments of ``activity.pick``."""

    activity_id: str
    date: str
    time: str
    guests: int = 1


class FilterArgs(BaseModel):
    """The arguments of ``meeting.filter``."""

    headcount: int | None = None
    layout: Literal["boardroom", "u_shape", "classroom", "theatre", "banquet"] | None = None
    date: str | None = None


class MeetingPickArgs(BaseModel):
    """The arguments of ``meeting.pick``."""

    room_id: str
    date: str
    block: Literal["morning", "afternoon", "full", "hours"]
    start: str | None = None
    """HH:MM, for block hours."""
    hours: int | None = None
    """For block hours."""
    headcount: int
    layout: Literal["boardroom", "u_shape", "classroom", "theatre", "banquet"]
    catering: list[str] | None = None
    """Catering ids: coffee, breakfast, lunch, snack."""
    av: list[str] | None = None
    """AV add-on ids: mics, recording, tech."""


class VisitorOpenArgs(BaseModel):
    """The arguments of ``visitor.open``."""

    visitor_id: str
    meet: Literal["room", "lobby"] | None = None


class ExpectArgs(BaseModel):
    """The arguments of ``visitor.expect``."""

    name: str
    arrive_from: str
    """HH:MM, start of the arrival window."""
    arrive_to: str
    """HH:MM, end of the arrival window."""
    meet: Literal["room", "lobby"] | None = None
    note: str | None = None


class FillArgs(BaseModel):
    """The arguments of ``request.fill``."""

    kind: Literal["housekeeping", "maintenance", "wakeup", "valet", "transport", "lost_found"]
    items: list[str] | None = None
    """housekeeping item ids: towels, pillows, toiletries, robes, crib, turndown, clean, dnd."""
    issue: str | None = None
    """maintenance issue id: ac, tv, plumbing, lights, door, other."""
    option: str | None = None
    """transport option id: house-car, airport, taxi."""
    date: str | None = None
    time: str | None = None
    """HH:MM."""
    details: str | None = None
    """Free text: what is wrong, where to, what was lost and where."""
    send: bool = False
    """Press Send, only after the guest said yes and when it costs nothing."""


GO = Move(
    id="app.go",
    verb="go",
    cls=MoveClass.NAVIGATE,
    args=("page",),
    say="{go: spa} at the start of the sentence that takes them to another screen: home, dining, bar, spa, activities, meetings, requests, visitors, stay, checkin, checkout or info.",
    claims=(
        "taking you to",
        "opening the",
        "pulling up the",
    ),
    objects=(
        "menu",
        "spa",
        "activities",
        "meeting rooms",
        "requests",
        "visitors",
        "folio",
        "check-in",
    ),
)
"""Go to a screen of the app, ringing its tab first."""

APP_SHOW = Move(
    id="app.show",
    verb="show",
    cls=MoveClass.LOOK,
    args=("target",),
    say="{show: total} right before the sentence about something on screen, to ring it: an item or a charge by name, the total, a time slot, the key.",
)
"""Scroll to a named thing on the screen and ring it. Changes nothing."""

CLOSE = Move(
    id="sheet.close",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    claims=("closing that",),
    objects=("sheet",),
)
"""Close the sheet that is open over the screen."""

INFO_OPEN = Move(
    id="info.open",
    verb=None,
    cls=MoveClass.NAVIGATE,
    args=("topic",),
    claims=("opening the policy",),
    objects=(
        "policy",
        "house rules",
        "information",
    ),
)
"""Open hotel information at one section, expanded and ringed."""

CHECKIN_OPEN = Move(
    id="checkin.open",
    verb=None,
    cls=MoveClass.NAVIGATE,
    args=("step",),
    claims=(
        "starting your check-in",
        "opening check-in",
    ),
    objects=("check-in",),
)
"""Open the check-in flow at a step it has reached (an earlier one is fine; a later one is refused with what is missing)."""

CONFIRM = Move(
    id="checkin.confirm",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    claims=("confirming your reservation",),
    objects=("reservation",),
)
"""Ring and press "Yes, that's my reservation" on the first step, after the guest said it is theirs."""

PREFS = Move(
    id="checkin.prefs",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "arrival",
        "floor",
        "bed",
        "quiet",
    ),
    claims=(
        "setting your arrival",
        "noting your preferences",
    ),
    objects=(
        "arrival time",
        "preferences",
        "floor",
    ),
)
"""On the room step, ring and set each preference that is given."""

EARLY = Move(
    id="checkin.early",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=("want",),
    claims=("adding early check-in",),
    objects=("early check-in",),
)
"""On the early check-in step, ring and choose whether to take the room now for the fee."""

CHECKOUT_OPEN = Move(
    id="checkout.open",
    verb=None,
    cls=MoveClass.NAVIGATE,
    args=("part",),
    claims=(
        "opening your bill",
        "pulling up your folio",
    ),
    objects=(
        "bill",
        "folio",
        "charges",
        "late check-out",
        "check-out",
    ),
)
"""Open check-out at the folio, the late check-out options or the express check-out review."""

DISPUTE = Move(
    id="folio.dispute",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "line_id",
        "reason",
        "send",
    ),
    claims=(
        "flagging that charge",
        "questioning that charge",
    ),
    objects=(
        "charge",
        "dispute",
    ),
)
"""Ring a folio line and open its question form with the reason filled; with send, press Send to the front desk."""

LATE_PICK = Move(
    id="late.pick",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=("time",),
    claims=("picking the late check-out",),
    objects=("late check-out",),
)
"""Ring and select a late check-out option. The guest presses Request."""

MENU_OPEN = Move(
    id="menu.open",
    verb=None,
    cls=MoveClass.NAVIGATE,
    args=(
        "outlet",
        "section",
    ),
    claims=(
        "opening the menu",
        "pulling up the menu",
    ),
    objects=(
        "menu",
        "drinks",
        "breakfast",
        "cocktails",
        "wine",
    ),
)
"""Open the in-room dining or drinks menu at a section, its tab ringed."""

ITEM = Move(
    id="menu.item",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "outlet",
        "item_id",
        "qty",
        "choices",
        "note",
        "add",
    ),
    claims=(
        "adding the",
        "adding a",
        "adding two",
    ),
    objects=(
        "order",
        "item",
    ),
)
"""Ring an item, open its sheet, set its choices and quantity (each ringed), and add it to the order."""

REMOVE = Move(
    id="cart.remove",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "outlet",
        "item_id",
    ),
    claims=(
        "taking off the",
        "removing the",
    ),
    objects=("order",),
)
"""Ring an order line and take it off."""

CART_OPEN = Move(
    id="cart.open",
    verb=None,
    cls=MoveClass.NAVIGATE,
    args=(
        "outlet",
        "tip",
        "deliver_to",
        "cabana",
    ),
    claims=("opening your order",),
    objects=(
        "order",
        "cart",
        "basket",
    ),
)
"""Open the order sheet (lines, charges, delivery time) and set the tip and delivery place if given. The guest presses Place order."""

SPA_OPEN = Move(
    id="spa.open",
    verb=None,
    cls=MoveClass.NAVIGATE,
    args=("category",),
    claims=("opening the spa",),
    objects=(
        "spa",
        "treatments",
    ),
)
"""Open the spa menu, at a category."""

TREATMENT = Move(
    id="spa.treatment",
    verb=None,
    cls=MoveClass.NAVIGATE,
    args=(
        "treatment_id",
        "date",
        "therapist",
    ),
    claims=(
        "checking the times",
        "pulling up the times",
    ),
    objects=(
        "times",
        "slots",
        "availability",
    ),
)
"""Open a treatment's booking sheet with its free times for a date and a therapist preference."""

SLOT = Move(
    id="spa.slot",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "treatment_id",
        "date",
        "time",
        "therapist_id",
    ),
    claims=(
        "holding the",
        "picking the",
    ),
    objects=(
        "slot",
        "appointment",
        "time",
    ),
)
"""Ring and pick a free time with a therapist on the treatment's sheet. The guest presses Book."""

ACTIVITY_SHOW = Move(
    id="activity.show",
    verb=None,
    cls=MoveClass.LOOK,
    args=(
        "activity_id",
        "map",
    ),
    claims=("showing you on the map",),
    objects=("map",),
)
"""Ring an activity's card; with map, pin and ring its place on the resort map."""

ACTIVITY_PICK = Move(
    id="activity.pick",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "activity_id",
        "date",
        "time",
        "guests",
    ),
    claims=(
        "booking the",
        "reserving the",
    ),
    objects=(
        "booking",
        "spot",
        "tee time",
        "court",
    ),
)
"""Open an activity's booking sheet with the date, time and guests set. The guest presses Book."""

FILTER = Move(
    id="meeting.filter",
    verb=None,
    cls=MoveClass.NAVIGATE,
    args=(
        "headcount",
        "layout",
        "date",
    ),
    claims=("finding a room",),
    objects=(
        "meeting rooms",
        "rooms",
        "halls",
    ),
)
"""Open meeting rooms with the rooms that fit a headcount and layout, and their availability on a date."""

MEETING_PICK = Move(
    id="meeting.pick",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "room_id",
        "date",
        "block",
        "start",
        "hours",
        "headcount",
        "layout",
        "catering",
        "av",
    ),
    claims=(
        "putting the booking together",
        "setting up the booking",
    ),
    objects=(
        "booking",
        "quote",
    ),
)
"""Open a room's booking form with everything set, each field ringed, and the price. The guest presses Request booking."""

VISITOR_OPEN = Move(
    id="visitor.open",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "visitor_id",
        "meet",
    ),
    claims=("opening the request",),
    objects=(
        "visitor",
        "request",
    ),
)
"""Ring a pending visitor and open their request, with where to meet set. The guest presses Approve or Decline."""

EXPECT = Move(
    id="visitor.expect",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "name",
        "arrive_from",
        "arrive_to",
        "meet",
        "note",
    ),
    claims=("adding your visitor",),
    objects=(
        "visitor",
        "guest list",
    ),
)
"""Fill the expected visitor form. The guest presses Add visitor."""

FILL = Move(
    id="request.fill",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "kind",
        "items",
        "issue",
        "option",
        "date",
        "time",
        "details",
        "send",
    ),
    claims=(
        "sending that to",
        "putting in the request",
        "setting your wake-up call",
    ),
    objects=(
        "request",
        "wake-up call",
        "towels",
        "car",
    ),
)
"""Open a front desk request with its fields filled, each ringed; with send, press Send."""

MOVES = MoveSet(
    (
        GO,
        APP_SHOW,
        CLOSE,
        INFO_OPEN,
        CHECKIN_OPEN,
        CONFIRM,
        PREFS,
        EARLY,
        CHECKOUT_OPEN,
        DISPUTE,
        LATE_PICK,
        MENU_OPEN,
        ITEM,
        REMOVE,
        CART_OPEN,
        SPA_OPEN,
        TREATMENT,
        SLOT,
        ACTIVITY_SHOW,
        ACTIVITY_PICK,
        FILTER,
        MEETING_PICK,
        VISITOR_OPEN,
        EXPECT,
        FILL,
    )
)

#: The line each cue is taught with, in the spec's order.
PROMPT_LINES: tuple[str, ...] = (
    "{go: spa} at the start of the sentence that takes them to another screen: home, dining, bar, spa, activities, meetings, requests, visitors, stay, checkin, checkout or info.",
    "{show: total} right before the sentence about something on screen, to ring it: an item or a charge by name, the total, a time slot, the key.",
)

#: The slices of the page's state a read may name.
SliceId = Literal["stay"]


class ReadRequest(BaseModel):
    """What the read tool takes: the slice to read, from the brain's mirror."""

    slice: SliceId = Field(
        description="Which part of their screen to read. stay: the last change on screen, by ids, as the app reports it."
    )
