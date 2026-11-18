# Generated from dental/frontend/src/stage/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
#   voqalize stage gen dental/frontend/src/stage/scene.json --py dental/backend/stage_gen.py --ts dental/frontend/src/stage/scene.gen.ts
"""The moves of dantika_front_desk, from its Stage Spec."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from voqalize.sdk.stage import Move, MoveClass, MoveSet, StageSpec, load_spec

#: The spec itself, carried here so the brain never reads the JSON at run
#: time (and a deploy that ships this file ships the spec with it).
SPEC: StageSpec = load_spec(
    '{"id":"dantika_front_desk","languages":["en","hi"],"moves":[{"args":[{"doc":"The page: home, book or my-appointments.","enum":["home","book","my-appointments"],"name":"page"}],"claims":["opening the booking page","taking you to","opening your appointments"],"class":"navigate","doc":"Open one of the clinic\'s pages, ringing its link in the header first.","id":"site.go","objects":["page","booking page","appointments page"],"say":"{go: book} as you start the sentence about that page: \\"Let\'s open the booking page.\\"","verb":"go"},{"args":[{"doc":"A part of the page by name: services, dentists, branches, visit-info, payment, insurance, parking, eating, aftercare, emergency, hours, policy, calendar, summary, appointments.","name":"thing"}],"class":"look","doc":"Scroll to a part of the page and ring it; nothing changes. Opens the home page first for a part only it has.","id":"site.show","say":"{show: parking} at the start of the sentence that talks about it; it scrolls into view and is ringed.","verb":"show"},{"args":[{"doc":"The service\'s id from clinic.json: consult, checkup, emergency, scaling, filling, rct, extraction, wisdom, aligner, whitening, implant, iopa, opg, cbct.","name":"service_id"},{"doc":"The day shown, YYYY-MM-DD.","name":"date"},{"doc":"indiranagar or hsr; none for both.","name":"branch_id","optional":true},{"doc":"The dentist\'s id; none for a scan or for any dentist.","name":"dentist_id","optional":true},{"default":"day","doc":"The calendar\'s view.","enum":["day","week"],"name":"view"}],"claims":["checking the calendar","looking at the slots","pulling up the slots"],"class":"reversible","doc":"On the booking page: pick the service, branch and dentist as the visitor would, put that dentist\'s (or the imaging room\'s) calendar on the day, and ring the free slots. Opens the booking page first.","id":"book.slots","objects":["slots","calendar","times","availability"]},{"args":[{"name":"service_id"},{"name":"branch_id"},{"doc":"YYYY-MM-DD.","name":"date"},{"doc":"HH:MM, 24-hour.","name":"time"},{"name":"dentist_id","optional":true},{"doc":"The chair the slot was computed on.","name":"chair_id","optional":true},{"doc":"The imaging room, for a scan.","name":"resource_id","optional":true},{"doc":"A root canal\'s later sittings, each \'YYYY-MM-DD HH:MM branch_id chair_id\'.","name":"sittings","optional":true,"type":"array"}],"claims":["holding the slot","picking that slot","selecting the slot"],"class":"reversible","doc":"Select one free slot on the calendar and show the booking summary (price, preparation, sittings) with its Confirm button. Nothing is booked yet. Refused when the slot is no longer free.","id":"book.hold","objects":["slot","time","appointment"]},{"args":[{"doc":"The id the brain minted, DT-24117.","name":"booking_id"},{"doc":"The verified patient, P-1001, or the new patient\'s id.","name":"patient_id"},{"name":"service_id"},{"name":"branch_id"},{"name":"date"},{"name":"time"},{"name":"dentist_id","optional":true},{"name":"chair_id","optional":true},{"name":"resource_id","optional":true},{"name":"sittings","optional":true,"type":"array"},{"doc":"The ids of the later sittings, in order.","name":"sitting_ids","optional":true,"type":"array"}],"claims":["booking it now","confirming your appointment","confirming the booking"],"class":"confirmed","doc":"Book the held slot, after the patient\'s spoken yes: the appointment goes on the calendar and the confirmation shows. Refused when nothing is held, the patient is not verified, or the slot was taken.","id":"book.confirm","objects":["booking","appointment"]},{"args":[{"doc":"The phone number as said; the page keeps the last ten digits.","name":"phone"}],"claims":["sending you a code","sending the code"],"class":"reversible","doc":"Fill the phone number in the sign-in panel and send the one-time code (a demo SMS shown on screen).","id":"patient.phone","objects":["code","otp","phone number"]},{"args":[{"doc":"The four digits the patient read out.","name":"code"}],"claims":["verifying the code","checking the code"],"class":"reversible","doc":"Fill the one-time code and verify it. Refused when it does not match.","id":"patient.otp","objects":["code","otp"]},{"args":[{"doc":"A new patient\'s full name, as said.","name":"name"}],"claims":["adding your name","registering you"],"class":"reversible","doc":"For a phone number with no record: fill the new patient\'s name and register them.","id":"patient.name","objects":["name","registration"]},{"args":[{"doc":"DT-24051.","name":"appointment_id"}],"class":"look","doc":"On My appointments: scroll to one appointment\'s card and ring it.","id":"appt.focus"},{"args":[{"name":"appointment_id"},{"enum":["reschedule","cancel"],"name":"action"},{"default":0,"doc":"The late-change fee in rupees, 0 when free.","name":"fee","type":"integer"},{"doc":"The new day, for a reschedule.","name":"date","optional":true},{"doc":"The new time, for a reschedule.","name":"time","optional":true},{"name":"branch_id","optional":true},{"name":"dentist_id","optional":true},{"name":"chair_id","optional":true},{"name":"resource_id","optional":true}],"claims":["moving it to","cancelling it"],"class":"reversible","doc":"On My appointments: open the change sheet on one card (old and new time, or the cancellation) with the policy line and fee, and its Confirm and Keep buttons. Nothing changes yet.","id":"appt.propose","objects":["appointment","reschedule","cancellation"]},{"args":[{"name":"appointment_id"},{"enum":["reschedule","cancel"],"name":"action"},{"default":0,"name":"fee","type":"integer"},{"name":"date","optional":true},{"name":"time","optional":true},{"name":"branch_id","optional":true},{"name":"dentist_id","optional":true},{"name":"chair_id","optional":true},{"name":"resource_id","optional":true}],"claims":["moving your appointment now","cancelling your appointment now"],"class":"confirmed","doc":"Make the change the sheet shows, after the patient\'s spoken yes. Refused when the new slot was taken.","id":"appt.apply","objects":["appointment"]},{"args":[{"doc":"CB-3107.","name":"callback_id"},{"doc":"One short line for the dentist, in English.","name":"reason"},{"enum":["urgent","today","routine"],"name":"urgency"},{"doc":"When the call comes, as authored: within 30 minutes.","name":"window"},{"doc":"The number to call, when known.","name":"phone","optional":true}],"claims":["asking a dentist to call","requesting a callback","arranging a callback"],"class":"reversible","doc":"Show the callback request card: what the dentist will call about, how soon, and its reference.","id":"callback.request","objects":["callback","call back"]},{"args":[{"doc":"YYYY-MM-DD.","name":"date"},{"name":"dentist_id","optional":true},{"name":"resource_id","optional":true},{"default":"week","enum":["day","week"],"name":"mode"}],"class":"look","doc":"Put one dentist\'s (or imaging room\'s) calendar on screen, on the day or its week, and ring it. Changes no selection.","id":"cal.view"}],"stage":1}'
)
#: The spec's hash: a page reading another spec reports a different one.
SPEC_SHA256 = "b6179d19ca39b7d99cfe526be40c428fc7e9031f3124c1c4eaec06c6eb653487"


class GoArgs(BaseModel):
    """The arguments of ``site.go``."""

    page: Literal["home", "book", "my-appointments"]
    """The page: home, book or my-appointments."""


class ShowArgs(BaseModel):
    """The arguments of ``site.show``."""

    thing: str
    """A part of the page by name: services, dentists, branches, visit-info, payment, insurance, parking, eating, aftercare, emergency, hours, policy, calendar, summary, appointments."""


class SlotsArgs(BaseModel):
    """The arguments of ``book.slots``."""

    service_id: str
    """The service's id from clinic.json: consult, checkup, emergency, scaling, filling, rct, extraction, wisdom, aligner, whitening, implant, iopa, opg, cbct."""
    date: str
    """The day shown, YYYY-MM-DD."""
    branch_id: str | None = None
    """indiranagar or hsr; none for both."""
    dentist_id: str | None = None
    """The dentist's id; none for a scan or for any dentist."""
    view: Literal["day", "week"] = "day"
    """The calendar's view."""


class HoldArgs(BaseModel):
    """The arguments of ``book.hold``."""

    service_id: str
    branch_id: str
    date: str
    """YYYY-MM-DD."""
    time: str
    """HH:MM, 24-hour."""
    dentist_id: str | None = None
    chair_id: str | None = None
    """The chair the slot was computed on."""
    resource_id: str | None = None
    """The imaging room, for a scan."""
    sittings: list[str] | None = None
    """A root canal's later sittings, each 'YYYY-MM-DD HH:MM branch_id chair_id'."""


class ConfirmArgs(BaseModel):
    """The arguments of ``book.confirm``."""

    booking_id: str
    """The id the brain minted, DT-24117."""
    patient_id: str
    """The verified patient, P-1001, or the new patient's id."""
    service_id: str
    branch_id: str
    date: str
    time: str
    dentist_id: str | None = None
    chair_id: str | None = None
    resource_id: str | None = None
    sittings: list[str] | None = None
    sitting_ids: list[str] | None = None
    """The ids of the later sittings, in order."""


class PhoneArgs(BaseModel):
    """The arguments of ``patient.phone``."""

    phone: str
    """The phone number as said; the page keeps the last ten digits."""


class OtpArgs(BaseModel):
    """The arguments of ``patient.otp``."""

    code: str
    """The four digits the patient read out."""


class NameArgs(BaseModel):
    """The arguments of ``patient.name``."""

    name: str
    """A new patient's full name, as said."""


class FocusArgs(BaseModel):
    """The arguments of ``appt.focus``."""

    appointment_id: str
    """DT-24051."""


class ProposeArgs(BaseModel):
    """The arguments of ``appt.propose``."""

    appointment_id: str
    action: Literal["reschedule", "cancel"]
    fee: int = 0
    """The late-change fee in rupees, 0 when free."""
    date: str | None = None
    """The new day, for a reschedule."""
    time: str | None = None
    """The new time, for a reschedule."""
    branch_id: str | None = None
    dentist_id: str | None = None
    chair_id: str | None = None
    resource_id: str | None = None


class ApplyArgs(BaseModel):
    """The arguments of ``appt.apply``."""

    appointment_id: str
    action: Literal["reschedule", "cancel"]
    fee: int = 0
    date: str | None = None
    time: str | None = None
    branch_id: str | None = None
    dentist_id: str | None = None
    chair_id: str | None = None
    resource_id: str | None = None


class RequestArgs(BaseModel):
    """The arguments of ``callback.request``."""

    callback_id: str
    """CB-3107."""
    reason: str
    """One short line for the dentist, in English."""
    urgency: Literal["urgent", "today", "routine"]
    window: str
    """When the call comes, as authored: within 30 minutes."""
    phone: str | None = None
    """The number to call, when known."""


class ViewArgs(BaseModel):
    """The arguments of ``cal.view``."""

    date: str
    """YYYY-MM-DD."""
    dentist_id: str | None = None
    resource_id: str | None = None
    mode: Literal["day", "week"] = "week"


GO = Move(
    id="site.go",
    verb="go",
    cls=MoveClass.NAVIGATE,
    args=("page",),
    say='{go: book} as you start the sentence about that page: "Let\'s open the booking page."',
    claims=(
        "opening the booking page",
        "taking you to",
        "opening your appointments",
    ),
    objects=(
        "page",
        "booking page",
        "appointments page",
    ),
)
"""Open one of the clinic's pages, ringing its link in the header first."""

SHOW = Move(
    id="site.show",
    verb="show",
    cls=MoveClass.LOOK,
    args=("thing",),
    say="{show: parking} at the start of the sentence that talks about it; it scrolls into view and is ringed.",
)
"""Scroll to a part of the page and ring it; nothing changes. Opens the home page first for a part only it has."""

SLOTS = Move(
    id="book.slots",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "service_id",
        "date",
        "branch_id",
        "dentist_id",
        "view",
    ),
    claims=(
        "checking the calendar",
        "looking at the slots",
        "pulling up the slots",
    ),
    objects=(
        "slots",
        "calendar",
        "times",
        "availability",
    ),
)
"""On the booking page: pick the service, branch and dentist as the visitor would, put that dentist's (or the imaging room's) calendar on the day, and ring the free slots. Opens the booking page first."""

HOLD = Move(
    id="book.hold",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "service_id",
        "branch_id",
        "date",
        "time",
        "dentist_id",
        "chair_id",
        "resource_id",
        "sittings",
    ),
    claims=(
        "holding the slot",
        "picking that slot",
        "selecting the slot",
    ),
    objects=(
        "slot",
        "time",
        "appointment",
    ),
)
"""Select one free slot on the calendar and show the booking summary (price, preparation, sittings) with its Confirm button. Nothing is booked yet. Refused when the slot is no longer free."""

CONFIRM = Move(
    id="book.confirm",
    verb=None,
    cls=MoveClass.CONFIRMED,
    args=(
        "booking_id",
        "patient_id",
        "service_id",
        "branch_id",
        "date",
        "time",
        "dentist_id",
        "chair_id",
        "resource_id",
        "sittings",
        "sitting_ids",
    ),
    claims=(
        "booking it now",
        "confirming your appointment",
        "confirming the booking",
    ),
    objects=(
        "booking",
        "appointment",
    ),
)
"""Book the held slot, after the patient's spoken yes: the appointment goes on the calendar and the confirmation shows. Refused when nothing is held, the patient is not verified, or the slot was taken."""

PHONE = Move(
    id="patient.phone",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=("phone",),
    claims=(
        "sending you a code",
        "sending the code",
    ),
    objects=(
        "code",
        "otp",
        "phone number",
    ),
)
"""Fill the phone number in the sign-in panel and send the one-time code (a demo SMS shown on screen)."""

OTP = Move(
    id="patient.otp",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=("code",),
    claims=(
        "verifying the code",
        "checking the code",
    ),
    objects=(
        "code",
        "otp",
    ),
)
"""Fill the one-time code and verify it. Refused when it does not match."""

NAME = Move(
    id="patient.name",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=("name",),
    claims=(
        "adding your name",
        "registering you",
    ),
    objects=(
        "name",
        "registration",
    ),
)
"""For a phone number with no record: fill the new patient's name and register them."""

FOCUS = Move(
    id="appt.focus",
    verb=None,
    cls=MoveClass.LOOK,
    args=("appointment_id",),
)
"""On My appointments: scroll to one appointment's card and ring it."""

PROPOSE = Move(
    id="appt.propose",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "appointment_id",
        "action",
        "fee",
        "date",
        "time",
        "branch_id",
        "dentist_id",
        "chair_id",
        "resource_id",
    ),
    claims=(
        "moving it to",
        "cancelling it",
    ),
    objects=(
        "appointment",
        "reschedule",
        "cancellation",
    ),
)
"""On My appointments: open the change sheet on one card (old and new time, or the cancellation) with the policy line and fee, and its Confirm and Keep buttons. Nothing changes yet."""

APPLY = Move(
    id="appt.apply",
    verb=None,
    cls=MoveClass.CONFIRMED,
    args=(
        "appointment_id",
        "action",
        "fee",
        "date",
        "time",
        "branch_id",
        "dentist_id",
        "chair_id",
        "resource_id",
    ),
    claims=(
        "moving your appointment now",
        "cancelling your appointment now",
    ),
    objects=("appointment",),
)
"""Make the change the sheet shows, after the patient's spoken yes. Refused when the new slot was taken."""

REQUEST = Move(
    id="callback.request",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "callback_id",
        "reason",
        "urgency",
        "window",
        "phone",
    ),
    claims=(
        "asking a dentist to call",
        "requesting a callback",
        "arranging a callback",
    ),
    objects=(
        "callback",
        "call back",
    ),
)
"""Show the callback request card: what the dentist will call about, how soon, and its reference."""

VIEW = Move(
    id="cal.view",
    verb=None,
    cls=MoveClass.LOOK,
    args=(
        "date",
        "dentist_id",
        "resource_id",
        "mode",
    ),
)
"""Put one dentist's (or imaging room's) calendar on screen, on the day or its week, and ring it. Changes no selection."""

MOVES = MoveSet(
    (
        GO,
        SHOW,
        SLOTS,
        HOLD,
        CONFIRM,
        PHONE,
        OTP,
        NAME,
        FOCUS,
        PROPOSE,
        APPLY,
        REQUEST,
        VIEW,
    )
)

#: The line each cue is taught with, in the spec's order.
PROMPT_LINES: tuple[str, ...] = (
    '{go: book} as you start the sentence about that page: "Let\'s open the booking page."',
    "{show: parking} at the start of the sentence that talks about it; it scrolls into view and is ringed.",
)
