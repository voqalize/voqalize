"""What the visitor did on their own — the browser→brain half of the contract.

The Petwell site is a website first: people browse pages, read articles, open
the booking panel and fill it in with their own hands while Tushar is on the
call. Every one of those is a typed :class:`~voqalize.sdk.AppEvent`, small and
specific — a field typed, a day picked, a step reopened — so the desk always
knows what the visitor has done and carries on from where the screen now is.

**A click is never a cue to speak.** A visitor driving the page is getting on
with it; the desk records what they did and says nothing until they talk to it.
Each event updates the desk's picture of the screen and leaves one line in the
model's context, ahead of whatever the visitor says next.

There is no language event: nobody picks a language on the page. The desk hears
which one the visitor is speaking and moves to it (see ``brain.py``).
"""

from __future__ import annotations

from typing import Literal

from voqalize.sdk import AppEvent, AppEvents

__all__ = [
    "PETWELL_EVENTS",
    "AppointmentRequested",
    "ArticleOpened",
    "BookingClosed",
    "BookingOpened",
    "BookingRestarted",
    "BranchPicked",
    "BranchesBrowsed",
    "CityPicked",
    "DatePicked",
    "DetailEdited",
    "DetailField",
    "EmergencyClosed",
    "EmergencyOpened",
    "Page",
    "PagePicked",
    "PetwellEvent",
    "ReviewOpened",
    "ServicePicked",
    "SlotPicked",
    "StepOpened",
    "VisitTypePicked",
]

Page = Literal["home", "services", "locations", "health_hub", "at_home"]

DetailField = Literal["owner_name", "pet_name", "pet_type", "phone", "email", "address", "notes"]

BookingStep = Literal["visit", "location", "service", "slot", "details", "review"]


class PagePicked(AppEvent):
    """The visitor opened a page from the site's navigation."""

    page: Page = "home"


class ArticleOpened(AppEvent):
    """The visitor opened a Health Hub article."""

    article_id: str = ""


class BranchesBrowsed(AppEvent):
    """The visitor picked a city on the locations finder; empty for all cities."""

    city: str = ""


class BookingOpened(AppEvent):
    """The visitor opened the booking panel — from the header, a service card or
    an article's call to action, which may name the service to book."""

    service_id: str = ""


class BookingClosed(AppEvent):
    """The visitor closed the booking panel. What they chose is kept."""


class BookingRestarted(AppEvent):
    """The visitor tapped "Book another appointment": the panel starts over."""


class VisitTypePicked(AppEvent):
    """The visitor tapped Clinic visit or Vet at home."""

    visit_type: Literal["clinic", "home"] = "clinic"


class CityPicked(AppEvent):
    """The visitor tapped a city in the booking panel."""

    city: str = ""


class BranchPicked(AppEvent):
    """The visitor tapped a branch in the booking panel."""

    branch_id: str = ""


class ServicePicked(AppEvent):
    """The visitor tapped a reason for the visit."""

    service_id: str = ""


class DatePicked(AppEvent):
    """The visitor tapped a day on the date strip; no time is chosen yet."""

    date: str = ""


class SlotPicked(AppEvent):
    """The visitor tapped a time on the slot grid."""

    date: str = ""
    time: str = ""


class StepOpened(AppEvent):
    """The visitor went back to a step — the Back link, the stepper, or a chip."""

    step: BookingStep = "visit"


class DetailEdited(AppEvent):
    """The visitor typed in a form field — sent once they pause or leave it, with
    the whole value as it now stands."""

    field: DetailField = "owner_name"
    value: str = ""


class ReviewOpened(AppEvent):
    """The visitor tapped Continue on their details and is checking the summary."""


class AppointmentRequested(AppEvent):
    """The visitor tapped Send Request, and the browser minted the reference."""

    ref: str = ""
    owner_name: str = ""
    pet_name: str = ""
    phone: str = ""


class EmergencyOpened(AppEvent):
    """The visitor opened the 24x7 emergency sheet."""


class EmergencyClosed(AppEvent):
    """The visitor closed the emergency sheet."""


type PetwellEvent = (
    PagePicked
    | ArticleOpened
    | BranchesBrowsed
    | BookingOpened
    | BookingClosed
    | BookingRestarted
    | VisitTypePicked
    | CityPicked
    | BranchPicked
    | ServicePicked
    | DatePicked
    | SlotPicked
    | StepOpened
    | DetailEdited
    | ReviewOpened
    | AppointmentRequested
    | EmergencyOpened
    | EmergencyClosed
)

PETWELL_EVENTS = AppEvents[PetwellEvent](
    PagePicked,
    ArticleOpened,
    BranchesBrowsed,
    BookingOpened,
    BookingClosed,
    BookingRestarted,
    VisitTypePicked,
    CityPicked,
    BranchPicked,
    ServicePicked,
    DatePicked,
    SlotPicked,
    StepOpened,
    DetailEdited,
    ReviewOpened,
    AppointmentRequested,
    EmergencyOpened,
    EmergencyClosed,
)
