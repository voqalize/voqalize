"""What the visitor did on the page, and what the page tells the brain it holds.

The clinic site works by click alone, so a patient may sign in, pick a slot,
book, move or cancel by hand while Meera is on the call. Each of those is one
small typed :class:`~voqalize.sdk.AppEvent`. The brain folds it into its own
calendar (so the slots it offers are the ones the screen shows) and leaves one
line in the model's context. Only the sign-in speaks back: the visitor types the
mobile number and the code themselves (FEEDBACK X9), so the page tells the brain
how that went (:class:`SignInStep`, :class:`PatientSignedIn`) and Meera answers
in the next quiet moment. No event carries the number or the code.

Every event carries ``by``: ``"visitor"`` when the patient did it, ``"agent"``
when the page reports a move Meera made.

``LanguageChanged`` is the one brain → page :class:`~voqalize.sdk.Action`
outside Stage: it moves the EN / हिंदी toggle when the call's language moves.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from voqalize.sdk import Action, AppEvent, AppEvents

__all__ = [
    "DENTAL_EVENTS",
    "AppointmentChanged",
    "AppointmentIn",
    "Booked",
    "CallbackRequested",
    "DentalEvent",
    "LanguageChanged",
    "LanguageRequested",
    "PageViewed",
    "PatientSignedIn",
    "PatientSignedOut",
    "ScheduleChanged",
    "SelectionChanged",
    "SignInStep",
]

By = Literal["visitor", "agent"]


class AppointmentIn(BaseModel):
    """One appointment this browser made or changed, with its real date."""

    model_config = ConfigDict(extra="ignore")

    id: str
    patient_id: str | None = None
    service: str
    branch: str
    date: str
    time: str
    duration_min: int
    dentist: str | None = None
    chair: str | None = None
    resource: str | None = None
    sitting: int | None = None
    changes: int = 0
    status: Literal["booked", "cancelled"] = "booked"


class PageViewed(AppEvent):
    """The page in front: ``home``, ``book`` or ``my-appointments``."""

    page: str = "home"
    path: str = "/"
    by: By = "visitor"


class ScheduleChanged(AppEvent):
    """Every appointment this browser has made or changed so far (new
    bookings, moves, cancellations), whole: sent when the call connects and
    after each change. The brain lays it over the authored calendar."""

    appointments: list[AppointmentIn] = Field(default_factory=list[AppointmentIn])
    by: By = "visitor"


class PatientSignedIn(AppEvent):
    """The visitor typed their mobile number and its code and they matched (or a
    new patient registered). The patient's record, never the number: the brain
    looks a known patient up by id."""

    patient_id: str
    name: str = ""
    first_name: str = ""
    is_new: bool = False
    #: Signed in on this browser before the call connected: nothing to welcome.
    restored: bool = False
    by: By = "visitor"


class SignInStep(AppEvent):
    """A step of the sign-in the visitor is typing: ``code_sent`` (the number
    was accepted and the demo SMS is on screen), ``bad_phone`` (not a ten-digit
    mobile number), ``wrong_code`` (the code did not match) or ``name_needed``
    (verified, new to the clinic). Never the number or the code."""

    step: Literal["code_sent", "bad_phone", "wrong_code", "name_needed"]
    by: By = "visitor"


class PatientSignedOut(AppEvent):
    """The patient signed out."""

    by: By = "visitor"


class SelectionChanged(AppEvent):
    """The visitor picked something on the booking page by hand."""

    service_id: str | None = None
    branch_id: str | None = None
    dentist_id: str | None = None
    date: str | None = None
    time: str | None = None
    by: By = "visitor"


class Booked(AppEvent):
    """An appointment was booked (the visitor pressed Confirm, or a move did)."""

    booking_id: str
    service_id: str
    date: str
    time: str
    dentist_id: str | None = None
    branch_id: str = ""
    by: By = "visitor"


class AppointmentChanged(AppEvent):
    """An appointment was moved or cancelled on My appointments."""

    appointment_id: str
    action: Literal["reschedule", "cancel"]
    date: str | None = None
    time: str | None = None
    fee: int = 0
    by: By = "visitor"


class CallbackRequested(AppEvent):
    """The visitor asked for a dentist to call back, by hand."""

    callback_id: str
    reason: str = ""
    urgency: str = "today"
    by: By = "visitor"


class LanguageRequested(AppEvent):
    """The visitor pressed the other language on the toggle during the call."""

    language: Literal["en", "hi"]
    by: By = "visitor"


DentalEvent = (
    PageViewed
    | ScheduleChanged
    | PatientSignedIn
    | PatientSignedOut
    | SignInStep
    | SelectionChanged
    | Booked
    | AppointmentChanged
    | CallbackRequested
    | LanguageRequested
)

DENTAL_EVENTS = AppEvents(
    PageViewed,
    ScheduleChanged,
    PatientSignedIn,
    PatientSignedOut,
    SignInStep,
    SelectionChanged,
    Booked,
    AppointmentChanged,
    CallbackRequested,
    LanguageRequested,
)


class LanguageChanged(Action):
    """The call now speaks ``language``: the page moves its EN / हिंदी toggle."""

    language: Literal["en", "hi"]
