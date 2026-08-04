"""TravelBrain — the travel-desk agent, written on **Google ADK**.

The client-authored surface here is a normal ADK ``LlmAgent`` (a model, an
instruction, and plain async tool functions) plus a thin
:class:`voqalize.google_adk.AdkBrain` subclass whose only override is
:meth:`~voqalize.google_adk.AdkBrain.grounding` — the live screen state. Everything
between — the function-calling loop, the per-model-call speech brackets, history,
barge-in and heard-truth correction — is the SDK's, not ours.

Compare ``brain_gemini.py`` (the previous, still-readable version) to see what the
port deletes:

* **the JSON tool schemas.** ADK derives each tool's schema from its type hints,
  so a nested option shape is a small pydantic model instead of a hand-written
  ``{"type": "object", "properties": {...}}`` dict and a ``_to_schema`` walker.
* **the tool-dispatch chain.** ADK calls the tool function by name; the ``if
  name == ...`` ladder and the ``(name, description, properties, required)``
  tuple table both go away.
* **the run loop.** ``GeminiBrain.respond`` streamed inferences, collected
  function calls, appended ``role="tool"`` contents and looped up to
  ``max_tool_hops``. The SDK's adapter does all of that.

What we still write is exactly the domain: the prompt, ten tools that drive the
screen, and this session's itinerary state.

**Screen grounding.** The ``/travel`` UI pushes a compact snapshot of the active
itinerary (``state_sync``) on connect and after every change — including edits the
travel agent makes by hand. The SDK ingests that message convention itself and
parks the payload on ``self.browser_state`` (silently — a screen change never makes
the agent talk); :meth:`TravelBrain.grounding` folds it into **every** prompt. The
genai version exposed the same snapshot through a ``get_active_itinerary`` tool the
model had to remember to call, which is strictly worse for a screen-driving agent:
the model could answer "which flights are up?" from a stale turn, and it cost a
round-trip. ``get_active_itinerary`` is therefore gone — it fired no ``ui_command``,
so the browser contract is unchanged.

**The screen contract is declared, not assembled.** Each of the ten ``ui_command``s
is a :class:`voqalize.sdk.Action` subclass below, so the payload the ``/travel`` UI
receives is a *type* — checked here, and mirrored one-for-one by the TypeScript
interfaces in ``frontend/src/uiCommands.ts``. The wire is exactly what the old
``voice().action("search_flights", {...})`` dict form emitted; what changed is that
a renamed field is now a Python error and a TypeScript error instead of a key that
silently stops arriving.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Literal

from google.adk.agents import LlmAgent
from pydantic import BaseModel, Field
from voqalize_demos import DEFAULT_MODEL

from voqalize.google_adk import AdkBrain, voice
from voqalize.sdk import Action

if TYPE_CHECKING:
    from google.adk.models.base_llm import BaseLlm

_INSTRUCTION = """You are Priya, the Travel Desk assistant — a voice copilot for a professional travel agent building trip itineraries for their clients. The agent talks to you live and YOU DRIVE THEIR SCREEN as you talk.

LANGUAGE: Speak the agent's language (English, Hindi in Devanagari, or Hinglish), matching them. Short, efficient sentences — one question or confirmation per turn, 1-2 sentences. This is voice: no markdown, lists, or symbols; say "rupees" not the symbol. START every reply with a very short sentence so audio begins instantly.

YOU CONTROL THE SCREEN. Whenever you discuss a trip, flight, hotel, or change, call the matching tool so the agent SEES it. ALWAYS SPEAK A SHORT LINE FIRST (a handful of words), THEN call the tool — never call a tool in silence. Example: "Sure, opening that up." then the tool.

YOU INVENT THE DATA. There is no live inventory. Generate realistic options yourself (real-sounding carriers like IndiGo / Vietnam Airlines, real 5-star hotels, plausible times, ratings, and fares in rupees) and pass them as the tool's structured arguments. Usually offer 3 options. Keep numbers consistent.

WORKFLOW: To start a trip, call create_itinerary with just the headline fields (name, destination, dates), then set_trip_structure with the families, flight legs, and hotel cities. For each flight leg speak a line then call search_flights with 3 invented options; select_flight once picked. For each hotel city call search_hotels with 3 options; select_hotel once picked. Use show_flights / show_hotels to bring a leg/city back on screen, and open_itinerary / open_dashboard to navigate.

Open with a brief greeting and ask which trip they want to work on."""

_GREETING = "नमस्ते, मैं प्रिया हूँ ट्रैवल डेस्क से। हम किस ट्रिप पर काम करें?"

# Prepended to the live snapshot `grounding()` appends on every model call.
_SCREEN_HEADER = "ON SCREEN RIGHT NOW (authoritative — this is what the agent is actually looking at, including any edits they made by hand; never contradict it):\n"

_NOTHING_ON_SCREEN = "No itinerary is open yet — the agent is on the dashboard of saved drafts."


# ─── Tool argument shapes ──────────────────────────────────────────────────────
#
# These pydantic models exist so ADK can build each tool's JSON schema from the
# type hints, and the SDK constructs them before the tool runs — a parameter typed
# `list[FlightOption]` really is a list of `FlightOption`s in the body. One thing
# to know, learned the hard way: only field NAMES, TYPES and required-ness survive
# into the generated schema. Pydantic `Field(description=...)` and docstring
# `Args:` text for nested fields are dropped — the model's only prose guidance is
# the tool docstring as a whole. So per-field hints (formats, examples) live in the
# docstrings below, not in `Field`.


class Family(BaseModel):
    """One travelling family on the itinerary."""

    label: str
    origin: str = ""
    adults: int = 0
    children: int = 0
    infants: int = 0
    meal: Literal["veg", "nonveg", "mixed"] = "mixed"
    assistance: str = ""


class Leg(BaseModel):
    """One flight leg of the trip."""

    id: str = ""
    label: str = ""
    # `from` is a Python keyword, so the field is `from_` and the browser's key is
    # the alias. The SDK validates from either spelling (the model sends `from_`,
    # the schema name); `model_dump(by_alias=True)` emits the `from` the UI reads.
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
    """The itinerary shell ``create_itinerary`` puts on screen, and this brain's own
    mirror of it. The UI's ``buildItinerary()`` reads exactly these keys."""

    name: str
    coordinator: str = ""
    destination: str = ""
    start_date: str = ""
    end_date: str = ""
    summary: str = ""
    families: list[Family] = []
    legs: list[Leg] = []
    hotel_cities: list[CityNights] = []


def _with_ids[T: BaseModel](items: Sequence[T], prefix: str) -> list[T]:
    """The same models, each guaranteed a stable string ``id``.

    The UI keys a leg, a flight option and a hotel option off ``id``, and the model
    routinely omits it. Filling it here (rather than in the browser) keeps one
    numbering authority: the same ids go on screen, into this brain's mirror, and
    back to the model as the tool result it will cite ("book f2")."""
    out: list[T] = []
    for i, item in enumerate(items):
        current = str(getattr(item, "id", "") or "").strip()
        out.append(item if current else item.model_copy(update={"id": f"{prefix}{i + 1}"}))
    return out


# ─── The screen contract: one Action per ui_command ────────────────────────────
#
# An `Action` is a pydantic model that knows its own wire name — `SearchFlights` →
# `"search_flights"` — and serializes `by_alias`, so a nested `Leg` still reaches
# the browser with the `from` key its store reads. The envelope is unchanged from
# the dict form these replace: `{"type": "ui_command", "action": <name>,
# "action_id": <int>, **fields}`.
#
# These are the source of truth for `frontend/src/uiCommands.ts`. Change a field
# here and the TypeScript interface must move with it.


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


# ─── The agent: tools + prompt ─────────────────────────────────────────────────


class TravelDesk:
    """One session's screen: the itinerary state and the ten screen-driving tools.

    The tools are ordinary async methods — ADK drops the bound ``self`` when it
    builds their schemas, so holding session state on the instance costs nothing.
    Each one mutates this mirror **and** fires ``voice().action(...)``, the RTVI
    ``ui_command`` the ``/travel`` UI renders; the value it returns goes back to
    the model as the tool result. Tools must be ``async`` — a sync tool would be
    dispatched on a thread pool, where the ``voice()`` context var is unset, and
    the SDK refuses one at startup."""

    def __init__(self) -> None:
        # What this brain believes it put on screen. Used for grounding until the
        # browser's own snapshot arrives, and as the fallback if it never does.
        self.itinerary: Itinerary | None = None
        self.flights: dict[str, list[FlightOption]] = {}
        self.hotels: dict[str, list[HotelOption]] = {}
        self.selected: dict[str, str] = {}

    def mirror(self) -> dict[str, Any] | None:
        """This brain's own picture of the screen — the grounding fallback before
        (or without) a browser snapshot. ``None`` when nothing is open."""
        if not self.itinerary:
            return None
        return {"itinerary": self.itinerary.model_dump(by_alias=True), "selected": self.selected}

    # ─── tools ──────────────────────────────────────────────────────────

    async def open_dashboard(self) -> dict[str, Any]:
        """Open the dashboard of saved draft trips."""
        voice().action(OpenDashboard())
        return {"status": "dashboard open"}

    async def open_itinerary(self, name: str) -> dict[str, Any]:
        """Open a saved itinerary by name.

        Args:
            name: The itinerary's name, e.g. "Poddar Vietnam".
        """
        voice().action(OpenItinerary(name=name))
        return {"status": "opened", "name": name}

    async def create_itinerary(
        self,
        name: str,
        destination: str,
        start_date: str,
        end_date: str,
        coordinator: str = "",
        summary: str = "",
    ) -> dict[str, Any]:
        """Create a new itinerary SHELL and open its overview.

        Just the headline fields — add travellers, flight legs and hotel cities
        with set_trip_structure next.

        Args:
            name: Itinerary name, e.g. "Poddar Vietnam".
            destination: Primary destination and routing.
            start_date: Trip start, e.g. "12 Aug 2026".
            end_date: Trip end, e.g. "18 Aug 2026".
            coordinator: The travel agent handling the trip.
            summary: One-line summary of the trip.
        """
        itinerary = Itinerary(
            name=name,
            coordinator=coordinator,
            destination=destination,
            start_date=start_date,
            end_date=end_date,
            summary=summary,
        )
        self.itinerary = itinerary
        voice().action(CreateItinerary(itinerary=itinerary))
        return {"status": "created", "name": name}

    async def set_trip_structure(
        self,
        families: list[Family],
        legs: list[Leg],
        hotel_cities: list[CityNights],
    ) -> dict[str, Any]:
        """Fill in the active itinerary's travelling families, flight legs and hotel cities.

        Args:
            families: The travelling families; label each like "Poddar family (Bangalore)".
            legs: The flight legs. Give each a short stable id ("blr-out"), a human
                label ("Bangalore → Ho Chi Minh (Outbound)"), from/to cities and a
                date like "12 Aug 2026".
            hotel_cities: Each city the group sleeps in, with the number of nights.
        """
        legs = _with_ids(legs, "leg")
        if self.itinerary is not None:
            self.itinerary.families = families
            self.itinerary.legs = legs
            self.itinerary.hotel_cities = hotel_cities
        voice().action(SetTripStructure(families=families, legs=legs, hotel_cities=hotel_cities))
        return {"status": "structure set", "families": len(families), "legs": len(legs)}

    async def search_flights(self, leg_id: str, options: list[FlightOption]) -> dict[str, Any]:
        """Search one flight leg and show the option cards on screen.

        Invent 3 realistic options. Times go in depart/arrive like "BLR 02:15" /
        "SGN 09:40"; stops reads "Non-stop" or "1 stop · KUL"; price is the
        per-person fare in rupees.

        Args:
            leg_id: The leg's id, as given to set_trip_structure.
            options: The 3 invented flight options.
        """
        rows = _with_ids(options, "f")
        self.flights[leg_id] = rows
        voice().action(SearchFlights(leg_id=leg_id, options=rows))
        return {"status": "showing", "leg_id": leg_id, "count": len(rows)}

    async def show_flights(self, leg_id: str) -> dict[str, Any]:
        """Bring an already-searched leg's flight options back on screen.

        Args:
            leg_id: The leg's id.
        """
        voice().action(ShowFlights(leg_id=leg_id))
        return {"status": "shown", "leg_id": leg_id}

    async def select_flight(self, leg_id: str, option_id: str) -> dict[str, Any]:
        """Select one flight option for a leg and pin it to the itinerary.

        Args:
            leg_id: The leg's id.
            option_id: The chosen option's id, e.g. "f2".
        """
        self.selected[f"flight:{leg_id}"] = option_id
        voice().action(SelectFlight(leg_id=leg_id, option_id=option_id))
        return {"status": "flight selected", "leg_id": leg_id, "option_id": option_id}

    async def search_hotels(self, city: str, options: list[HotelOption]) -> dict[str, Any]:
        """Search 5-star hotels for one city and show them on screen.

        Invent 3 realistic properties. stars is 1-5, rating is out of 10, board
        reads like "Breakfast included", and price_per_night is the group rate in
        rupees.

        Args:
            city: The city being searched.
            options: The 3 invented hotel options.
        """
        rows = _with_ids(options, "h")
        self.hotels[city] = rows
        voice().action(SearchHotels(city=city, options=rows))
        return {"status": "showing", "city": city, "count": len(rows)}

    async def show_hotels(self, city: str) -> dict[str, Any]:
        """Bring an already-searched city's hotel options back on screen.

        Args:
            city: The city whose options to re-show.
        """
        voice().action(ShowHotels(city=city))
        return {"status": "shown", "city": city}

    async def select_hotel(self, city: str, option_id: str) -> dict[str, Any]:
        """Select one hotel option for a city.

        Args:
            city: The city.
            option_id: The chosen option's id, e.g. "h1".
        """
        self.selected[f"hotel:{city}"] = option_id
        voice().action(SelectHotel(city=city, option_id=option_id))
        return {"status": "hotel selected", "city": city, "option_id": option_id}

    def tools(self) -> list[Any]:
        """The ten bound methods handed to ``LlmAgent(tools=...)``."""
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


def build_travel_agent(model: str | BaseLlm, desk: TravelDesk) -> LlmAgent:
    """Build the travel-desk ``LlmAgent`` over one session's :class:`TravelDesk`.

    ``model`` is any ADK model — a model-id string in production, or a fake
    ``BaseLlm`` (``voqalize.google_adk.testing.ScriptedLlm``) in tests."""
    return LlmAgent(
        name="travel_desk",
        model=model,
        instruction=_INSTRUCTION,
        tools=desk.tools(),
    )


# ─── The brain ─────────────────────────────────────────────────────────────────


class TravelBrain(AdkBrain):
    """One per session. Hosts the ADK agent above and adds the one voice seam the
    demo needs: what's on screen, in front of the model on every call."""

    # Priya speaks Hindi to every caller, so the agent says so itself rather than
    # depending on the connecting page to remember. `language` sets both the
    # recognizer's hint and the TTS reference clip — get it wrong and the model
    # still writes Devanagari, but an en-IN voice reads it aloud.
    voice = "omnivoice/gauri"
    language = "hi"

    def __init__(
        self,
        *,
        model: str | BaseLlm = DEFAULT_MODEL,
        answer_conformance_dump: bool = False,
    ) -> None:
        super().__init__(
            lambda: build_travel_agent(model, self.desk),
            greeting=_GREETING,
            streaming=True,
            answer_conformance_dump=answer_conformance_dump,
        )
        # The agent is built lazily, on session start — so the factory above sees
        # this even though it's assigned after super().__init__.
        self.desk = TravelDesk()

    def grounding(self) -> str:
        """Appended to the system instruction on every model call, so the model can
        never answer "which flights are up?" from a stale turn.

        Prefers the browser's own ``state_sync`` snapshot — the SDK keeps the latest
        on ``browser_state`` — because it also carries the travel agent's hand edits;
        falls back to this brain's own mirror of what its tools put on screen."""
        screen = (self.browser_state or {}).get("itinerary") or self.desk.mirror()
        if not screen:
            return _SCREEN_HEADER + _NOTHING_ON_SCREEN
        return _SCREEN_HEADER + json.dumps(screen, ensure_ascii=False, default=str)
