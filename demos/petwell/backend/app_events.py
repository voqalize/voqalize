"""What the visitor did on their own — the browser→brain half of the contract.

The Petwell site is a website first: people browse pages, read articles and
open the booking panel with their own hands while Tushar is on the call. Each of
those is a typed :class:`~voqalize.sdk.AppEvent`, so the desk hears about it and
carries on from where the screen now is rather than asking a question already
answered.

Browsing (a page, an article) is only noted — a visitor reading is not one to be
talked at. A booking step tapped, the booking panel opened, or Send Request owes
a reply, which ``on_user_idle`` pays once they are quiet.

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
    "BookingOpened",
    "BranchPicked",
    "CityPicked",
    "Page",
    "PagePicked",
    "PetwellEvent",
    "ServicePicked",
    "SlotPicked",
    "VisitTypePicked",
]

Page = Literal["home", "services", "locations", "health_hub", "at_home"]


class PagePicked(AppEvent):
    """The visitor opened a page from the site's navigation."""

    page: Page = "home"


class ArticleOpened(AppEvent):
    """The visitor opened a Health Hub article."""

    article_id: str = ""


class BookingOpened(AppEvent):
    """The visitor opened the booking panel — from the header, a service card or
    an article's call to action, which may name the service to book."""

    service_id: str = ""


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


class SlotPicked(AppEvent):
    """The visitor tapped a time on the slot grid."""

    date: str = ""
    time: str = ""


class AppointmentRequested(AppEvent):
    """The visitor tapped Send Request, and the browser minted the reference."""

    ref: str = ""
    owner_name: str = ""
    pet_name: str = ""
    phone: str = ""


type PetwellEvent = (
    PagePicked
    | ArticleOpened
    | BookingOpened
    | VisitTypePicked
    | CityPicked
    | BranchPicked
    | ServicePicked
    | SlotPicked
    | AppointmentRequested
)

PETWELL_EVENTS = AppEvents[PetwellEvent](
    PagePicked,
    ArticleOpened,
    BookingOpened,
    VisitTypePicked,
    CityPicked,
    BranchPicked,
    ServicePicked,
    SlotPicked,
    AppointmentRequested,
)
