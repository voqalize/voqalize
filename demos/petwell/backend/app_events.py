"""What the pet owner did on their own — the browser→brain half of the contract.

The booking screen is tappable as well as speakable: a caller can pick a branch,
a service or a time with a finger while the assistant is talking. Each tap is a
typed :class:`~voqalize.sdk.AppEvent`, so the assistant hears about it and carries
on from where the screen now is rather than asking a question already answered.

The ids ride in the payload because they are the answer — a branch tapped is that
branch — and the final submission carries the reference the browser minted,
which exists nowhere else.
"""

from __future__ import annotations

from typing import Literal

from voqalize.sdk import AppEvent, AppEvents

__all__ = [
    "PETWELL_EVENTS",
    "AppointmentRequested",
    "BranchPicked",
    "CityPicked",
    "PetwellEvent",
    "ServicePicked",
    "SlotPicked",
    "VisitTypePicked",
]


class VisitTypePicked(AppEvent):
    """The caller tapped Clinic visit or Vet at home."""

    visit_type: Literal["clinic", "home"] = "clinic"


class CityPicked(AppEvent):
    """The caller tapped a city chip."""

    city: str = ""


class BranchPicked(AppEvent):
    """The caller tapped a branch card."""

    branch_id: str = ""


class ServicePicked(AppEvent):
    """The caller tapped a reason for the visit."""

    service_id: str = ""


class SlotPicked(AppEvent):
    """The caller tapped a time on the slot grid."""

    date: str = ""
    time: str = ""


class AppointmentRequested(AppEvent):
    """The caller tapped Send Request, and the browser minted the reference."""

    ref: str = ""
    owner_name: str = ""
    pet_name: str = ""
    phone: str = ""


type PetwellEvent = (
    VisitTypePicked | CityPicked | BranchPicked | ServicePicked | SlotPicked | AppointmentRequested
)

PETWELL_EVENTS = AppEvents[PetwellEvent](
    VisitTypePicked, CityPicked, BranchPicked, ServicePicked, SlotPicked, AppointmentRequested
)
