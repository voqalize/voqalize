"""TravelBrain — the travel-desk agent, on ``GeminiBrain``.

Priya is a voice copilot for a professional travel agent building trip
itineraries live, on a call. Ten tools drive the agent's screen; each is one
``async def`` taking a single :class:`~voqalize.sdk.Action` and returning a
short string — the model calls the method, the method dispatches the
``ui-command``, ``self.session`` is simply there because a brain is one
instance per call.

**The screen is read, never remembered.** The ``/travel`` UI pushes a compact
``state_sync`` snapshot of the active itinerary on connect and after every
change — including edits the travel agent makes by hand. That snapshot lands in
:attr:`TravelBrain.screen` and nowhere else; what reaches the model is one line
naming which decisions the agent moved, and the itinerary itself is read through
``read_screen``, which is local, free and silent. ``ScreenState.version`` is what
makes that safe rather than hopeful: a tool aimed at a leg or a city the agent
has moved since Priya last read refuses instead of acting on it. See
``voqalize_demos.screen`` for the whole story.
"""

from __future__ import annotations

from typing import Any, Literal

from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel, Field
from voqalize_demos import DEFAULT_MODEL, GeminiBrain, ScreenState, screen_prose

from voqalize.sdk import Action, RTVIMessage, RTVIType, Session
from voqalize.sdk.wire import Config, Language, SttConfig, TtsConfig, Voice

_SYSTEM_INSTRUCTION = """You are Priya, the Travel Desk assistant — a voice copilot for a professional travel agent building trip itineraries for their clients. The agent talks to you live and YOU DRIVE THEIR SCREEN as you talk.

LANGUAGE: Speak the agent's language (English, Hindi in Devanagari, or Hinglish), matching them. Short, efficient sentences — one question or confirmation per turn, 1-2 sentences. This is voice: no markdown, lists, or symbols; say "rupees" not the symbol. START every reply with a very short sentence so audio begins instantly.

YOU CONTROL THE SCREEN. Whenever you discuss a trip, flight, hotel, or change, call the matching tool so the agent SEES it. ALWAYS SPEAK A SHORT LINE FIRST (a handful of words), THEN call the tool — never call a tool in silence. Example: "Sure, opening that up." then the tool.

YOU INVENT THE DATA. There is no live inventory. Generate realistic options yourself (real-sounding carriers like IndiGo / Vietnam Airlines, real 5-star hotels, plausible times, ratings, and fares in rupees) and pass them as the tool's structured arguments. Usually offer 3 options. Keep numbers consistent.

STAY GROUNDED: nothing in this conversation is a picture of the agent's screen. read_screen() is the only one, and it is free and silent — it takes no floor, says nothing, and moves nothing. Call it before you act on or refer to anything they point at ("that leg", "the second one", "the hotel we picked"), and whenever you are told they changed the screen themselves — you are told THAT they changed it, never what it now says. If a tool refuses because the screen moved under you, that is not something to report or apologise for: read the screen and make the call again.

WORKFLOW: To start a trip, call create_itinerary with just the headline fields (name, destination, dates), then set_trip_structure with the families, flight legs, and hotel cities. For each flight leg speak a line then call search_flights with 3 invented options; select_flight once picked. For each hotel city call search_hotels with 3 options; select_hotel once picked. Use show_flights / show_hotels to bring a leg/city back on screen, and open_itinerary / open_dashboard to navigate.

Open with a brief greeting and ask which trip they want to work on."""

_GREETING = "नमस्ते, मैं प्रिया हूँ ट्रैवल डेस्क से। हम किस ट्रिप पर काम करें?"

_NOTHING_ON_SCREEN = "No itinerary is open yet — the agent is on the dashboard of saved drafts."


def _screen_facts(state: dict[str, Any] | None) -> dict[str, Any]:
    """The parts of the itinerary snapshot that are somebody's decision.

    Deliberately not in here: ``tasks`` (a search finishing is the browser's own
    clock), ``options_shown`` (results landing is not a choice) and ``patch_note``
    (it moves whenever anything else does). Bumping the version for those would
    cost Priya a re-read on every search she herself started."""
    if not state:
        return {}
    legs = state.get("legs")
    hotels = state.get("hotels")
    return {
        "the open itinerary": state.get("name"),
        "the screen they are on": state.get("screen"),
        "which leg or city is up": state.get("screen_context"),
        "the destination": state.get("destination"),
        "the dates": state.get("dates"),
        "the travelling families": state.get("families"),
        "the special requests": state.get("special_requests"),
        "the flights picked": (
            {leg.get("id"): leg.get("selected") for leg in legs if isinstance(leg, dict)}
            if isinstance(legs, list)
            else None
        ),
        "the hotels picked": (
            {h.get("city"): h.get("selected") for h in hotels if isinstance(h, dict)}
            if isinstance(hotels, list)
            else None
        ),
        "the day plan": state.get("days"),
        "the inclusions": state.get("inclusions"),
        "the exclusions": state.get("exclusions"),
    }


# ─── Tool argument shapes ───────────────────────────────────────────────────


#: The three meal preferences the itinerary screen renders a chip for.
Meal = Literal["veg", "nonveg", "mixed"]


class Family(BaseModel):
    """One travelling family on the itinerary."""

    label: str
    origin: str = ""
    adults: int = 0
    children: int = 0
    infants: int = 0
    meal: Meal = "mixed"
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

    def __init__(self, *, client: genai.Client, model: str = DEFAULT_MODEL) -> None:
        super().__init__(client=client, system_instruction=_SYSTEM_INSTRUCTION, model=model)
        # What is on the agent's screen. This is the only copy: it is read
        # through ``read_screen`` and never appended to the model's context. The
        # browser's echo is the one place "what's on screen" can include the
        # travel agent's own hand edits, so it stays the source of truth.
        self.screen = ScreenState(_screen_facts, read_tool="read_screen", actor="travel agent")

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
        turn carries at most one line saying which decisions moved."""
        if msg.type is not RTVIType.CLIENT_MESSAGE or not isinstance(msg.data, dict):
            return
        if msg.data.get("t") == "state_sync":
            self._ingest_state(msg.data.get("d") or {})

    def _ingest_state(self, data: dict[str, Any]) -> None:
        """Fold the browser's snapshot into :attr:`screen` — and into it only.

        This used to append the whole itinerary to the model's context on every
        change, which is the defect ``voqalize_demos.screen`` exists to close."""
        snapshot = data.get("itinerary")
        note = self.screen.absorb(snapshot if isinstance(snapshot, dict) else None)
        logger.info(
            "travel: state_sync (active={}, v{})",
            bool(self.screen.snapshot),
            self.screen.version,
        )
        if note is not None:
            self.append_to_context(types.Content(role="user", parts=[types.Part(text=note)]))

    def _show(self, action: Action) -> None:
        """Put something on screen. Every tool that moves it comes through here, so
        the browser's echo of our own command is not mistaken for the agent."""
        self.screen.dispatched()
        self.session.dispatch(action)

    # ─── Tools ────────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        """The eleven the travel desk may call. Ten drive the agent's screen;
        ``read_screen`` reads it back."""
        return [
            self.read_screen,
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

    async def read_screen(self) -> str:
        """What the travel agent is looking at right now — the open itinerary, which
        screen they are on, and every choice made on it so far.

        Call it before you act on something they point at, and whenever you are told
        they changed the screen themselves. It is free — it reads this session's own
        state, takes no floor, says nothing, and moves nothing on screen."""
        self.screen.read()
        snapshot = self.screen.snapshot
        logger.info("travel: read_screen (active={}, v{})", bool(snapshot), self.screen.version)
        if not snapshot:
            return _NOTHING_ON_SCREEN
        return screen_prose(snapshot, actor="travel agent")

    async def open_dashboard(self) -> str:
        """Open the dashboard of saved draft trips."""
        self._show(OpenDashboard())
        return "dashboard open"

    async def open_itinerary(self, action: OpenItinerary) -> str:
        """Open a saved itinerary by name."""
        self._show(action)
        return f"opened {action.name}"

    async def create_itinerary(self, action: CreateItinerary) -> str:
        """Create a new itinerary SHELL and open its overview. Just the
        headline fields (name, destination, dates); add travellers, flight
        legs and hotel cities with set_trip_structure next."""
        self._show(action)
        return f"created '{action.itinerary.name}'"

    async def set_trip_structure(self, action: SetTripStructure) -> str:
        """Fill in the active itinerary's travelling families, flight legs
        and hotel cities. Give each leg a short stable id ("blr-out"), a
        human label ("Bangalore → Ho Chi Minh (Outbound)"), from/to cities and
        a date like "12 Aug 2026"."""
        action = action.model_copy(update={"legs": _with_ids(action.legs, "leg")})
        self._show(action)
        return f"structure set ({len(action.families)} families, {len(action.legs)} legs)"

    async def search_flights(self, action: SearchFlights) -> str:
        """Search one flight leg (invent 3 realistic options) and show the
        option cards on screen. Times go in depart/arrive like "BLR 02:15" /
        "SGN 09:40"; stops reads "Non-stop" or "1 stop · KUL"; price is the
        per-person fare in rupees."""
        action = action.model_copy(update={"options": _with_ids(action.options, "f")})
        self._show(action)
        return f"showing {len(action.options)} flights for {action.leg_id}"

    async def show_flights(self, action: ShowFlights) -> str:
        """Bring an already-searched leg's flight options back on screen."""
        stale = self.screen.stale()
        if stale:
            return stale
        self._show(action)
        return "shown"

    async def select_flight(self, action: SelectFlight) -> str:
        """Select one flight option for a leg and pin it to the itinerary."""
        stale = self.screen.stale()
        if stale:
            return stale
        self._show(action)
        return "flight selected"

    async def search_hotels(self, action: SearchHotels) -> str:
        """Search 5-star hotels for one city (invent 3 realistic properties)
        and show them on screen. stars is 1-5, rating is out of 10, board
        reads like "Breakfast included", and price_per_night is the group
        rate in rupees."""
        action = action.model_copy(update={"options": _with_ids(action.options, "h")})
        self._show(action)
        return f"showing {len(action.options)} hotels in {action.city}"

    async def show_hotels(self, action: ShowHotels) -> str:
        """Bring an already-searched city's hotel options back on screen."""
        stale = self.screen.stale()
        if stale:
            return stale
        self._show(action)
        return "shown"

    async def select_hotel(self, action: SelectHotel) -> str:
        """Select one hotel option for a city."""
        stale = self.screen.stale()
        if stale:
            return stale
        self._show(action)
        return "hotel selected"
