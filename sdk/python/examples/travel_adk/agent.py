"""The travel-desk agent — **100% client-authored** ADK code.

This is the whole surface a customer developer writes to put a voice agent on
Voqalize with Google ADK: a normal ``LlmAgent`` (model, instruction, tools) and
plain Python tool functions. There is **no Voqalize wire code here** — no frames,
no brackets, no run loop, no history management. The only Voqalize touch is
:func:`voice`, the one-line accessor a tool uses to drive the caller's screen.

Contrast with ``examples/travel/brain.py`` (the google-genai version): there the
client hand-writes JSON tool schemas *and* the entire function-calling loop. Here
ADK generates the schemas from type hints and executes the loop; the SDK drives
ADK. The client writes tools and a prompt — nothing else.

The tools return structured data to the model (so it can speak about it) and, as
a side-effect, call ``voice().action(...)`` to render that data on the agent's
screen — exactly the RTVI ``ui_command`` the ``/travel`` console consumes. Tools
are **async** so ``voice()`` resolves in the turn's context (see
``voqalize.google_adk.voice``).
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm

from voqalize.google_adk import voice

GREETING = "Hi, I'm Priya from the Travel Desk. Which trip are we working on?"

_INSTRUCTION = """You are Priya, the Travel Desk assistant — a voice copilot for a professional travel agent building trip itineraries. The agent talks to you live and YOU DRIVE THEIR SCREEN as you talk.

VOICE STYLE: Speak English. Short, efficient sentences — one question or confirmation per turn, 1-2 sentences. No markdown, lists, or symbols; say "rupees" not the symbol. Start every reply with a very short sentence so audio begins instantly.

YOU CONTROL THE SCREEN. Whenever you discuss a trip or flight, call the matching tool so the agent SEES it. ALWAYS SPEAK A SHORT LINE FIRST (a handful of words), THEN call the tool — never call a tool in silence. Example: "Sure, pulling up flights." then the tool.

YOU INVENT THE DATA. There is no live inventory. Generate realistic options yourself (real-sounding carriers like IndiGo or Vietnam Airlines, plausible times, and fares in rupees) and pass them as the tool's structured arguments. Offer 3 flight options.

WORKFLOW: To start a trip, call create_itinerary with the headline fields. For the flight, speak a line then call search_flights with 3 invented options. When the agent picks one, call select_flight. Keep numbers consistent across turns."""


async def create_itinerary(name: str, destination: str, start_date: str, end_date: str) -> dict:
    """Create a new itinerary shell and open its overview on screen.

    Args:
        name: Itinerary name, e.g. "Poddar Vietnam".
        destination: Primary destination + routing.
        start_date: Trip start date, e.g. "12 Aug 2026".
        end_date: Trip end date.
    """
    voice().action(
        "create_itinerary",
        {"name": name, "destination": destination, "start_date": start_date, "end_date": end_date},
    )
    return {"status": "created", "itinerary": name}


async def search_flights(leg: str, options: list[dict]) -> dict:
    """Show flight options for one leg on screen.

    Args:
        leg: Human label for the leg, e.g. "Bangalore to Hanoi".
        options: 3 invented flight options; each a dict with keys airline,
            flight_no, depart, arrive, duration, stops, price (rupees, integer).
    """
    voice().action("search_flights", {"leg": leg, "options": options})
    return {"status": "shown", "leg": leg, "count": len(options)}


async def select_flight(leg: str, flight_no: str) -> dict:
    """Pin the chosen flight for a leg to the itinerary.

    Args:
        leg: The leg label the flight belongs to.
        flight_no: The chosen flight's number, e.g. "VN-412".
    """
    voice().action("select_flight", {"leg": leg, "flight_no": flight_no})
    return {"status": "selected", "leg": leg, "flight_no": flight_no}


def build_travel_agent(model: str | BaseLlm) -> LlmAgent:
    """Build the travel-desk ``LlmAgent``. ``model`` is any ADK model — a model-id
    string like ``"gemini-3.1-flash-lite"`` in production, or a fake ``BaseLlm``
    (e.g. ``ScriptedLlm``) in tests."""
    return LlmAgent(
        name="travel_desk",
        model=model,
        instruction=_INSTRUCTION,
        tools=[create_itinerary, search_flights, select_flight],
    )
