"""What the travel agent did, named — the browser→brain half of the screen contract.

The other direction is the :class:`~voqalize.sdk.Action` classes in
``brain_gemini.py``: each a declared shape whose wire name comes off the class
name, whose payload is validated at the call site, and whose TypeScript twin is
generated rather than written. :class:`~voqalize.sdk.AppEvent` is that, mirrored
— so ``on_rtvi`` narrows on a *type* instead of reading ``msg.data["t"]`` and
hoping about ``msg.data["d"]``. Both halves of ``actions.gen.ts`` come out of
this one union and that one, together.

What this replaced re-sent the whole itinerary on every change, and the brain
diffed the new picture against the old one to work out which decision had moved.
The best it could then say was that *something* changed — never what — and every
diff was a place the two pictures could part company. ``picked IndiGo 6E-1043 for
the outbound leg`` needs no diff and no inference.

:class:`TripOpened` is the one event that carries a whole itinerary, and it is
not the old push wearing a new name: these drafts live in the browser's
localStorage, so opening one is the moment the brain first learns the trip exists
— the handover, once, not a snapshot on every change. Everything after it is a
patch to a mirror the brain owns.

Nothing here decides what the brain *does* with an event; declaring is this
module's whole job.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from voqalize.sdk import AppEvent, AppEvents

__all__ = [
    "TRAVEL_EVENTS",
    "DashboardOpened",
    "FlightSelected",
    "FlightsViewed",
    "HotelSelected",
    "HotelsViewed",
    "ItineraryNotFound",
    "LegLine",
    "OverviewViewed",
    "QuoteShared",
    "StayLine",
    "TravelEvent",
    "TripOpened",
]


class LegLine(BaseModel):
    """One flight leg as the overview lists it — the pick, never the options."""

    id: str
    label: str = ""
    date: str = ""
    options_shown: int = 0
    selected: str = ""


class StayLine(BaseModel):
    """One hotel city as the overview lists it."""

    city: str
    options_shown: int = 0
    selected: str = ""


class TripOpened(AppEvent):
    """The agent opened a saved draft, or started a blank one.

    The drafts live in the browser, so this is the brain's first sight of the
    trip: it carries the itinerary as the overview shows it, and the mirror is
    built from it. Every later change is a patch."""

    id: str = Field(
        "",
        description="The draft's id — what open_itinerary names it by. Empty from an older page.",
    )
    name: str
    coordinator: str = ""
    destination: str = ""
    dates: str = ""
    pax: str = ""
    families: list[str] = Field(default_factory=list)
    special_requests: list[str] = Field(default_factory=list)
    legs: list[LegLine] = Field(default_factory=list)
    hotels: list[StayLine] = Field(default_factory=list)
    days: list[str] = Field(default_factory=list)
    inclusions: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    terms_set: bool = False
    whatsapp_sent: bool = False


class ItineraryNotFound(AppEvent):
    """An ``open_itinerary`` named a draft this browser does not hold, by id or by
    name, so the screen did not move.

    Nobody's gesture — the page's answer to a command, and the only place it
    exists: the drafts live in this browser, and a command the page cannot resolve
    otherwise leaves the brain's mirror on an overview the screen never showed."""

    id: str = ""
    name: str = ""


class DashboardOpened(AppEvent):
    """The agent closed the trip and went back to the list of drafts. Nothing is
    open, so nothing on screen has an id worth holding."""


class OverviewViewed(AppEvent):
    """The agent came back to the itinerary overview from a flights or hotels
    screen."""


class FlightsViewed(AppEvent):
    """The agent opened one leg's flight options."""

    leg_id: str
    leg_label: str = ""


class HotelsViewed(AppEvent):
    """The agent opened one city's hotel options."""

    city: str


class FlightSelected(AppEvent):
    """The agent picked a flight himself, off the option cards. ``summary`` is
    what the overview will now show for the leg, so the mirror needs no lookup."""

    leg_id: str
    option_id: str
    summary: str = ""


class HotelSelected(AppEvent):
    """The agent picked a hotel himself, off the option cards."""

    city: str
    option_id: str
    summary: str = ""


class QuoteShared(AppEvent):
    """The agent sent the quote on WhatsApp from the share sheet."""

    to: str = ""
    recipient: str = ""


#: One thing the travel agent did. A union rather than a base class, so a
#: ``match`` over it is checked for exhaustiveness — a gesture added here and not
#: handled in :meth:`TravelBrain.apply_event` fails pyright rather than the call.
type TravelEvent = (
    TripOpened
    | ItineraryNotFound
    | DashboardOpened
    | OverviewViewed
    | FlightsViewed
    | HotelsViewed
    | FlightSelected
    | HotelSelected
    | QuoteShared
)

#: The vocabulary this brain speaks, and the only thing that reads it. Scoped
#: rather than global because the demos umbrella runs every brain in one process,
#: and another one is entitled to its own ``TripOpened``.
TRAVEL_EVENTS = AppEvents[TravelEvent](
    TripOpened,
    ItineraryNotFound,
    DashboardOpened,
    OverviewViewed,
    FlightsViewed,
    HotelsViewed,
    FlightSelected,
    HotelSelected,
    QuoteShared,
)
