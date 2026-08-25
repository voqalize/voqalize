"""TravelBrain — the travel-desk agent, on ``GeminiBrain``.

Priya is a voice copilot for a professional travel agent building trip
itineraries live, on a call. Ten tools drive the agent's screen; each is one
``async def`` taking a single :class:`~voqalize.sdk.Action` and returning a
short string — the model calls the method, the method dispatches the
``ui-command``, ``self.session`` is simply there because a brain is one
instance per call.

**Screen grounding.** The ``/travel`` UI pushes a compact ``state_sync``
snapshot of the active itinerary on connect and after every change — including
edits the travel agent makes by hand. :meth:`TravelBrain.on_rtvi` folds a
changed snapshot into the context (silently — a screen change never makes
Priya talk), so "which flights are up?" is answered from what's actually on
screen rather than from a stale turn or a brain-owned mirror that could drift
from it. There is deliberately no ``get_active_itinerary`` tool: that round
trip is strictly worse than a fact already sitting in context.
"""

from __future__ import annotations

import json
from typing import Any

from google.genai import types
from loguru import logger
from pydantic import BaseModel, Field
from voqalize_demos import DEFAULT_MODEL, GeminiBrain, GeminiProvider

from voqalize.sdk import Action, RTVIMessage, RTVIType, Session
from voqalize.sdk.wire import Config, Language, SttConfig, TtsConfig, Voice

_SYSTEM_INSTRUCTION = """You are Priya, the Travel Desk assistant — a voice copilot for a professional travel agent building trip itineraries for their clients. The agent talks to you live and YOU DRIVE THEIR SCREEN as you talk.

LANGUAGE: Speak the agent's language (English, Hindi in Devanagari, or Hinglish), matching them. Short, efficient sentences — one question or confirmation per turn, 1-2 sentences. This is voice: no markdown, lists, or symbols; say "rupees" not the symbol. START every reply with a very short sentence so audio begins instantly.

YOU CONTROL THE SCREEN. Whenever you discuss a trip, flight, hotel, or change, call the matching tool so the agent SEES it. ALWAYS SPEAK A SHORT LINE FIRST (a handful of words), THEN call the tool — never call a tool in silence. Example: "Sure, opening that up." then the tool.

YOU INVENT THE DATA. There is no live inventory. Generate realistic options yourself (real-sounding carriers like IndiGo / Vietnam Airlines, real 5-star hotels, plausible times, ratings, and fares in rupees) and pass them as the tool's structured arguments. Usually offer 3 options. Keep numbers consistent.

WORKFLOW: To start a trip, call create_itinerary with just the headline fields (name, destination, dates), then set_trip_structure with the families, flight legs, and hotel cities. For each flight leg speak a line then call search_flights with 3 invented options; select_flight once picked. For each hotel city call search_hotels with 3 options; select_hotel once picked. Use show_flights / show_hotels to bring a leg/city back on screen, and open_itinerary / open_dashboard to navigate.

Open with a brief greeting and ask which trip they want to work on."""

_GREETING = "नमस्ते, मैं प्रिया हूँ ट्रैवल डेस्क से। हम किस ट्रिप पर काम करें?"

_SCREEN_HEADER = (
    "ON SCREEN RIGHT NOW (authoritative — this is what the agent is actually "
    "looking at, including any edits they made by hand; never contradict it): "
)
_NOTHING_ON_SCREEN = "No itinerary is open yet — the agent is on the dashboard of saved drafts."


# ─── Tool argument shapes ───────────────────────────────────────────────────


class Family(BaseModel):
    """One travelling family on the itinerary."""

    label: str
    origin: str = ""
    adults: int = 0
    children: int = 0
    infants: int = 0
    meal: str = "mixed"
    assistance: str = ""


class Leg(BaseModel):
    """One flight leg of the trip."""

    id: str = ""
    label: str = ""
    # `from` is a Python keyword, so the field is `from_` and the browser's key
    # is the alias — the model sends `from_`, the schema name; `to_payload()`
    # (by_alias) emits the `from` the UI reads.
    from_: str = Field(default="", alias="from")
    to: str = ""
    date: str = ""


class CityNights(BaseModel):
    """One hotel city and how many nights the group stays there."""

    city: str
    nights: int = 0


class FlightOption(BaseModel):
    """One invented flight option for a leg."""

    id: str = ""
    airline: str
    flight_no: str = ""
    depart: str = ""
    arrive: str = ""
    duration: str = ""
    stops: str = ""
    cabin: str = ""
    baggage: str = ""
    price: int = 0
    note: str = ""


class HotelOption(BaseModel):
    """One invented hotel option for a city."""

    id: str = ""
    name: str
    area: str = ""
    stars: int = 5
    board: str = ""
    room_type: str = ""
    rating: float = 0.0
    amenities: list[str] = []
    price_per_night: int = 0
    note: str = ""


class Itinerary(BaseModel):
    """The itinerary shell ``create_itinerary`` puts on screen."""

    name: str
    coordinator: str = ""
    destination: str = ""
    start_date: str = ""
    end_date: str = ""
    summary: str = ""
    families: list[Family] = []
    legs: list[Leg] = []
    hotel_cities: list[CityNights] = []


def _with_ids[T: BaseModel](items: list[T], prefix: str) -> list[T]:
    """The same models, each guaranteed a stable string ``id``.

    The UI keys a leg, a flight option and a hotel option off ``id``, and the
    model routinely omits it. Filling it here (rather than in the browser)
    keeps one numbering authority: the same ids go on screen and back to the
    model as the tool result it will cite ("book f2")."""
    out: list[T] = []
    for i, item in enumerate(items):
        current = str(getattr(item, "id", "") or "").strip()
        out.append(item if current else item.model_copy(update={"id": f"{prefix}{i + 1}"}))
    return out


# ─── The screen contract: one Action per ui-command ─────────────────────────


class OpenDashboard(Action):
    """Show the dashboard of saved draft trips. No arguments."""


class OpenItinerary(Action):
    name: str


class CreateItinerary(Action):
    itinerary: Itinerary


class SetTripStructure(Action):
    families: list[Family]
    legs: list[Leg]
    hotel_cities: list[CityNights]


class SearchFlights(Action):
    leg_id: str
    options: list[FlightOption]


class ShowFlights(Action):
    leg_id: str


class SelectFlight(Action):
    leg_id: str
    option_id: str


class SearchHotels(Action):
    city: str
    options: list[HotelOption]


class ShowHotels(Action):
    city: str


class SelectHotel(Action):
    city: str
    option_id: str


# ─── The brain ───────────────────────────────────────────────────────────────


class TravelBrain(GeminiBrain):
    """One per session. The travel-desk copilot: LLM + ten screen-driving tools.

    Priya's own voice — not the connecting page's to choose, since this is a
    professional tool the travel agent opens, not a caller-facing surface — so
    it is settled here rather than sent with the connect request."""

    def __init__(self, *, llm: GeminiProvider, model: str = DEFAULT_MODEL) -> None:
        super().__init__(client=llm.client, system_instruction=_SYSTEM_INSTRUCTION, model=model)
        # Latest browser-pushed itinerary snapshot, folded into context on
        # change. No brain-owned mirror of the itinerary: the ten tools below
        # are pure — dispatch and a short string back — because the browser's
        # own echo is the one place "what's on screen" can include the travel
        # agent's hand edits too.
        self._state_message: str | None = None

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        await session.configure(
            Config(
                stt=SttConfig(language=Language.HI),
                tts=TtsConfig(voice=Voice.OMNIVOICE_GAURI, language=Language.HI),
            )
        )

    async def greet(self, session: Session) -> str:
        return _GREETING

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Browser→brain message. ``state_sync`` carries a compact snapshot of
        the itinerary currently on screen — including edits the travel agent
        makes by hand. Ingested silently (no floor taken, no turn); the next
        turn carries it as a note, so Priya never answers from a stale turn."""
        if msg.type is not RTVIType.CLIENT_MESSAGE or not isinstance(msg.data, dict):
            return
        if msg.data.get("t") == "state_sync":
            self._ingest_state(msg.data.get("d") or {})

    def _ingest_state(self, data: dict[str, Any]) -> None:
        """Put the latest screen snapshot into the context, guarded against
        the near-duplicate re-sends every scroll or tap produces — an
        unguarded append would put a hundred near-identical screens in front
        of the model by the end of a call."""
        screen = data.get("itinerary")
        if screen:
            try:
                blob = json.dumps(screen, ensure_ascii=False, default=str)
            except (TypeError, ValueError):
                blob = str(screen)
            message = _SCREEN_HEADER + blob
        else:
            message = _SCREEN_HEADER + _NOTHING_ON_SCREEN
        if message == self._state_message:
            return
        self._state_message = message
        self.append_to_context(types.Content(role="user", parts=[types.Part(text=message)]))
        logger.info("travel: state_sync ingested (active={})", bool(screen))

    # ─── Tools ────────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        """The ten the travel desk may call. Every one drives the agent's
        screen through ``self.session``."""
        return [
            self.open_dashboard,
            self.open_itinerary,
            self.create_itinerary,
            self.set_trip_structure,
            self.search_flights,
            self.show_flights,
            self.select_flight,
            self.search_hotels,
            self.show_hotels,
            self.select_hotel,
        ]

    async def open_dashboard(self) -> str:
        """Open the dashboard of saved draft trips."""
        self.session.dispatch(OpenDashboard())
        return "dashboard open"

    async def open_itinerary(self, action: OpenItinerary) -> str:
        """Open a saved itinerary by name."""
        self.session.dispatch(action)
        return f"opened {action.name}"

    async def create_itinerary(self, action: CreateItinerary) -> str:
        """Create a new itinerary SHELL and open its overview. Just the
        headline fields (name, destination, dates); add travellers, flight
        legs and hotel cities with set_trip_structure next."""
        self.session.dispatch(action)
        return f"created '{action.itinerary.name}'"

    async def set_trip_structure(self, action: SetTripStructure) -> str:
        """Fill in the active itinerary's travelling families, flight legs
        and hotel cities. Give each leg a short stable id ("blr-out"), a
        human label ("Bangalore → Ho Chi Minh (Outbound)"), from/to cities and
        a date like "12 Aug 2026"."""
        action = action.model_copy(update={"legs": _with_ids(action.legs, "leg")})
        self.session.dispatch(action)
        return f"structure set ({len(action.families)} families, {len(action.legs)} legs)"

    async def search_flights(self, action: SearchFlights) -> str:
        """Search one flight leg (invent 3 realistic options) and show the
        option cards on screen. Times go in depart/arrive like "BLR 02:15" /
        "SGN 09:40"; stops reads "Non-stop" or "1 stop · KUL"; price is the
        per-person fare in rupees."""
        action = action.model_copy(update={"options": _with_ids(action.options, "f")})
        self.session.dispatch(action)
        return f"showing {len(action.options)} flights for {action.leg_id}"

    async def show_flights(self, action: ShowFlights) -> str:
        """Bring an already-searched leg's flight options back on screen."""
        self.session.dispatch(action)
        return "shown"

    async def select_flight(self, action: SelectFlight) -> str:
        """Select one flight option for a leg and pin it to the itinerary."""
        self.session.dispatch(action)
        return "flight selected"

    async def search_hotels(self, action: SearchHotels) -> str:
        """Search 5-star hotels for one city (invent 3 realistic properties)
        and show them on screen. stars is 1-5, rating is out of 10, board
        reads like "Breakfast included", and price_per_night is the group
        rate in rupees."""
        action = action.model_copy(update={"options": _with_ids(action.options, "h")})
        self.session.dispatch(action)
        return f"showing {len(action.options)} hotels in {action.city}"

    async def show_hotels(self, action: ShowHotels) -> str:
        """Bring an already-searched city's hotel options back on screen."""
        self.session.dispatch(action)
        return "shown"

    async def select_hotel(self, action: SelectHotel) -> str:
        """Select one hotel option for a city."""
        self.session.dispatch(action)
        return "hotel selected"
