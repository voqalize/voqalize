"""TravelBrain — the travel-desk agent, migrated from the managed
``pygato.managed.travel`` brain to a **cortex** Brain on the ergonomic SDK.

The mature-agent migration: real Gemini, the real travel system prompt, and
screen-driving tools — expressed entirely in the ``Brain`` surface (no ``Vql*``
frames). One ``on_interaction`` runs a manual google-genai function-calling loop;
**each LLM call is one ``interaction.say()`` bracket** (1:1 with the wire),
so a tool round-trip is naturally multi-inference: speak a short line → call the
screen tool → speak the result. Each tool body drives the browser via
``interaction.action(name, {...})`` — which the SDK relays as the RTVI
``ui_command`` the ``/travel`` console renders.

The conversation record is framework-owned: the SDK keeps the faithful,
heard-text transcript in ``interaction.conversation`` (user committed at
interaction start, assistant ``heard`` per inference at finalize). We hold no
parallel history — each turn we rebuild Gemini's working context from that
transcript, so past turns are the heard truth, never the generated tail of a
barged-in reply. The per-turn working context additionally carries the in-flight
generated text + tool round-trips, which aren't part of the durable record.

Tool schemas + ui_command payloads match what the Travel Desk demo's screens
expect, so the same UI drives. (Day-plan / inclusions / terms / whatsapp tools
aren't ported here — the itinerary + flights + hotels flow is.)

Run it against the local relay: ``examples/travel/run_local.py``.
"""

from __future__ import annotations

import os
from typing import Any

from google import genai
from google.genai import types
from loguru import logger

from voqalize.sdk import Brain

GEMINI_MODEL = "gemini-3.1-flash-lite"

_SYSTEM_INSTRUCTION = """You are Priya, the Travel Desk assistant — a voice copilot for a professional travel agent building trip itineraries for their clients. The agent talks to you live and YOU DRIVE THEIR SCREEN as you talk.

LANGUAGE: Speak the agent's language (English, Hindi in Devanagari, or Hinglish), matching them. Short, efficient sentences — one question or confirmation per turn, 1-2 sentences. This is voice: no markdown, lists, or symbols; say "rupees" not the symbol. START every reply with a very short sentence so audio begins instantly.

YOU CONTROL THE SCREEN. Whenever you discuss a trip, flight, hotel, or change, call the matching tool so the agent SEES it. ALWAYS SPEAK A SHORT LINE FIRST (a handful of words), THEN call the tool — never call a tool in silence. Example: "Sure, opening that up." then the tool.

YOU INVENT THE DATA. There is no live inventory. Generate realistic options yourself (real-sounding carriers like IndiGo / Vietnam Airlines, real 5-star hotels, plausible times, ratings, and fares in rupees) and pass them as the tool's structured arguments. Usually offer 3 options. Keep numbers consistent.

WORKFLOW: To start a trip, call create_itinerary with just the headline fields (name, destination, dates), then set_trip_structure with the families, flight legs, and hotel cities. For each flight leg speak a line then call search_flights with 3 invented options; select_flight once picked. For each hotel city call search_hotels with 3 options; select_hotel once picked. Use show_flights / show_hotels to bring a leg/city back on screen, open_itinerary / open_dashboard to navigate, and get_active_itinerary to ground yourself.

Open with a brief greeting and ask which trip they want to work on."""

_GREETING = "नमस्ते, मैं प्रिया हूँ ट्रैवल डेस्क से। हम किस ट्रिप पर काम करें?"


# ─── Tool schemas (JSON-schema dicts, mirrored from the managed travel bot) ────

_FAMILY = {
    "type": "object",
    "properties": {
        "label": {
            "type": "string",
            "description": "Family label, e.g. 'Poddar family (Bangalore)'.",
        },
        "origin": {"type": "string", "description": "Origin city."},
        "adults": {"type": "integer"},
        "children": {"type": "integer"},
        "infants": {"type": "integer"},
        "meal": {"type": "string", "enum": ["veg", "nonveg", "mixed"]},
        "assistance": {"type": "string", "description": "Special assistance note, or '' if none."},
    },
}
_LEG = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "description": "Short stable leg id, e.g. 'blr-out'."},
        "label": {
            "type": "string",
            "description": "Human label, e.g. 'Bangalore → Ho Chi Minh (Outbound)'.",
        },
        "from": {"type": "string"},
        "to": {"type": "string"},
        "date": {"type": "string", "description": "Date of travel, e.g. '12 Aug 2026'."},
    },
}
_CITY_NIGHTS = {
    "type": "object",
    "properties": {
        "city": {"type": "string"},
        "nights": {"type": "integer"},
    },
}
_FLIGHT_OPTION = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "description": "Short id, e.g. 'f1'."},
        "airline": {"type": "string"},
        "flight_no": {"type": "string"},
        "depart": {"type": "string", "description": "Departure airport + time, e.g. 'BLR 02:15'."},
        "arrive": {"type": "string", "description": "Arrival airport + time, e.g. 'SGN 09:40'."},
        "duration": {"type": "string"},
        "stops": {"type": "string", "description": "e.g. 'Non-stop' or '1 stop · KUL'."},
        "cabin": {"type": "string"},
        "baggage": {"type": "string"},
        "price": {"type": "integer", "description": "Per-person fare in rupees."},
        "note": {"type": "string"},
    },
}
_HOTEL_OPTION = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "description": "Short id, e.g. 'h1'."},
        "name": {"type": "string"},
        "area": {"type": "string"},
        "stars": {"type": "integer", "description": "Star rating 1-5."},
        "board": {"type": "string", "description": "e.g. 'Breakfast included'."},
        "room": {"type": "string"},
        "rating": {"type": "number", "description": "Guest rating out of 10."},
        "amenities": {"type": "array", "items": {"type": "string"}},
        "price": {"type": "integer", "description": "Per-night group rate in rupees."},
        "note": {"type": "string"},
    },
}


def _arr(item: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": item}


# (tool_name, description, properties, required)
_TOOLSPECS: list[tuple[str, str, dict[str, Any], list[str]]] = [
    ("open_dashboard", "Open the dashboard of saved draft trips.", {}, []),
    ("open_itinerary", "Open a saved itinerary by name.", {"name": {"type": "string"}}, ["name"]),
    (
        "create_itinerary",
        "Create a new itinerary SHELL and open its overview. Just the headline fields; add "
        "travellers/legs/cities with set_trip_structure next.",
        {
            "name": {"type": "string", "description": "Itinerary name, e.g. 'Poddar Vietnam'."},
            "coordinator": {"type": "string"},
            "destination": {"type": "string", "description": "Primary destination + routing."},
            "start_date": {"type": "string"},
            "end_date": {"type": "string"},
            "summary": {"type": "string", "description": "One-line summary."},
        },
        ["name", "destination", "start_date", "end_date"],
    ),
    (
        "set_trip_structure",
        "Fill in the active itinerary's travelling families, flight legs, and hotel cities.",
        {
            "families": _arr(_FAMILY),
            "legs": _arr(_LEG),
            "hotel_cities": _arr(_CITY_NIGHTS),
        },
        [],
    ),
    (
        "search_flights",
        "Search one flight leg (invent 3 realistic options) and show the option cards on screen.",
        {"leg_id": {"type": "string"}, "options": _arr(_FLIGHT_OPTION)},
        ["leg_id", "options"],
    ),
    (
        "show_flights",
        "Bring an already-searched leg's flight options back on screen.",
        {"leg_id": {"type": "string"}},
        ["leg_id"],
    ),
    (
        "select_flight",
        "Select one flight option for a leg and pin it to the itinerary.",
        {"leg_id": {"type": "string"}, "option_id": {"type": "string"}},
        ["leg_id", "option_id"],
    ),
    (
        "search_hotels",
        "Search 5-star hotels for one city (invent 3 realistic properties) and show them on screen.",
        {"city": {"type": "string"}, "options": _arr(_HOTEL_OPTION)},
        ["city", "options"],
    ),
    (
        "show_hotels",
        "Bring an already-searched city's hotel options back on screen.",
        {"city": {"type": "string"}},
        ["city"],
    ),
    (
        "select_hotel",
        "Select one hotel option for a city.",
        {"city": {"type": "string"}, "option_id": {"type": "string"}},
        ["city", "option_id"],
    ),
    ("get_active_itinerary", "Read back the trip + selections currently on screen.", {}, []),
]

_JSON_TO_GENAI = {
    "string": types.Type.STRING,
    "integer": types.Type.INTEGER,
    "number": types.Type.NUMBER,
    "boolean": types.Type.BOOLEAN,
    "object": types.Type.OBJECT,
    "array": types.Type.ARRAY,
}


def _to_schema(d: dict[str, Any]) -> types.Schema:
    """Convert a JSON-schema dict to a google-genai Schema (recursive)."""
    kw: dict[str, Any] = {"type": _JSON_TO_GENAI[d["type"]]}
    if d.get("description"):
        kw["description"] = d["description"]
    if d.get("enum"):
        kw["enum"] = d["enum"]
    if d["type"] == "object":
        props = d.get("properties") or {}
        kw["properties"] = {k: _to_schema(v) for k, v in props.items()}
        if d.get("required"):
            kw["required"] = d["required"]
    if d["type"] == "array":
        kw["items"] = _to_schema(d["items"])
    return types.Schema(**kw)


def _tools() -> types.ToolListUnion:
    decls = [
        types.FunctionDeclaration(
            name=name,
            description=desc,
            parameters=_to_schema({"type": "object", "properties": props, "required": req}),
        )
        for name, desc, props, req in _TOOLSPECS
    ]
    tools: types.ToolListUnion = [types.Tool(function_declarations=decls)]
    return tools


def _normalize_ids(items: list[Any], prefix: str) -> list[dict[str, Any]]:
    """Ensure every option/leg dict has a stable string id."""
    out: list[dict[str, Any]] = []
    for i, raw in enumerate(items):
        item = dict(raw) if isinstance(raw, dict) else {}
        item["id"] = str(item["id"]) if str(item.get("id") or "").strip() else f"{prefix}{i + 1}"
        out.append(item)
    return out


class TravelBrain(Brain):
    """One per session. Owns this session's conversation + itinerary state."""

    def __init__(self, *, api_key: str | None = None, model: str = GEMINI_MODEL) -> None:
        self._client = genai.Client(api_key=api_key or os.environ["GEMINI_API_KEY"])
        self._model = model
        self._config = types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            tools=_tools(),
            thinking_config=types.ThinkingConfig(thinking_budget=0),  # low latency for voice
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        # Brain-owned domain state only. The conversation record is NOT ours to
        # keep: the SDK maintains the faithful, heard-text transcript in
        # `interaction.conversation` (user committed at interaction start,
        # assistant `heard` committed per inference at finalize). We rebuild the
        # LLM's working context from it each turn — so past turns are always the
        # heard truth, never the generated tail of a barged-in reply.
        self.state: dict[str, Any] = {
            "itinerary": None,
            "flights": {},
            "hotels": {},
            "selected": {},
        }
        # Latest browser-pushed snapshot (state_sync via on_client_message) — what's
        # actually on screen, including the agent's hand edits. Grounds
        # get_active_itinerary so Priya stays in sync with manual changes.
        self.browser_state: Any = None

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session, start) -> None:
        async with session.say() as inf:
            await inf.speak(_GREETING)

    async def on_interaction(self, interaction) -> None:
        # Working context for this turn: the framework's faithful (heard) transcript
        # — which already includes this user utterance. Within the turn we append
        # *generated* text + tool results transiently (heard isn't known until the
        # inference finalizes post-playout); the SDK records the heard truth back
        # into the transcript for the next turn to read.
        contents = self._working_context(interaction)
        for _ in range(6):  # cap tool round-trips
            fcalls, model_parts = await self._one_inference(interaction, contents)
            if model_parts:
                contents.append(types.Content(role="model", parts=model_parts))
            if not fcalls:
                return
            for fc in fcalls:
                result = self._dispatch_tool(interaction, fc.name, dict(fc.args or {}))
                contents.append(
                    types.Content(
                        role="tool",
                        parts=[
                            types.Part.from_function_response(
                                name=fc.name, response={"result": result}
                            )
                        ],
                    )
                )

    async def on_client_message(self, session, message) -> None:
        # Browser→Brain feedback. The /travel console pushes a state_sync snapshot
        # on connect and after every change (incl. hand edits) — keep the latest so
        # get_active_itinerary reflects what's actually on screen. This is the
        # update-internal-state path: record it, don't spend the floor.
        if message.type == "state_sync":
            self.browser_state = message.data
            logger.info("travel: state_sync from browser ({} keys)", len(message.data or {}))

    # ─── Internals ──────────────────────────────────────────────────────

    def _working_context(self, interaction) -> list[types.Content]:
        """Build genai contents from the framework's heard transcript. Skips any
        assistant turns before the first user turn (e.g. the opening greeting) so
        the contents always start with a user turn, as Gemini expects."""
        out: list[types.Content] = []
        seen_user = False
        for m in interaction.conversation.messages:
            if m.role == "user":
                seen_user = True
                out.append(types.Content(role="user", parts=[types.Part(text=m.content)]))
            elif seen_user:
                out.append(types.Content(role="model", parts=[types.Part(text=m.content)]))
        return out

    async def _one_inference(
        self, interaction, contents: list[types.Content]
    ) -> tuple[list[Any], list[types.Part]]:
        fcalls: list[Any] = []
        model_parts: list[types.Part] = []
        async with interaction.say() as inf:
            stream = await self._client.aio.models.generate_content_stream(
                model=self._model,
                contents=contents,  # type: ignore[arg-type]
                config=self._config,
            )
            async for chunk in stream:
                for cand in chunk.candidates or []:
                    if not cand.content:
                        continue
                    for part in cand.content.parts or []:
                        model_parts.append(part)
                        if part.text:
                            await inf.speak(part.text)
                        if part.function_call:
                            fcalls.append(part.function_call)
        return fcalls, model_parts

    def _dispatch_tool(self, interaction, name: str, args: dict[str, Any]) -> str:
        """Mutate Brain state + drive the browser via interaction.action(...) — the
        SDK relays it as the RTVI ui_command the /travel console renders."""
        logger.info("travel: tool {} {}", name, {k: v for k, v in args.items() if k != "options"})
        act = interaction.action
        if name == "open_dashboard":
            act("open_dashboard")
            return "dashboard open"
        if name == "open_itinerary":
            act("open_itinerary", {"name": args.get("name", "")})
            return f"opened {args.get('name')}"
        if name == "create_itinerary":
            itinerary = {
                "name": args.get("name", ""),
                "coordinator": args.get("coordinator", ""),
                "destination": args.get("destination", ""),
                "start_date": args.get("start_date", ""),
                "end_date": args.get("end_date", ""),
                "summary": args.get("summary", ""),
                "families": [],
                "legs": [],
                "hotel_cities": [],
            }
            self.state["itinerary"] = itinerary
            act("create_itinerary", {"itinerary": itinerary})
            return f"created '{args.get('name')}'"
        if name == "set_trip_structure":
            families = list(args.get("families") or [])
            legs = _normalize_ids(list(args.get("legs") or []), "leg")
            cities = list(args.get("hotel_cities") or [])
            if self.state["itinerary"]:
                self.state["itinerary"].update(
                    {"families": families, "legs": legs, "hotel_cities": cities}
                )
            act("set_trip_structure", {"families": families, "legs": legs, "hotel_cities": cities})
            return f"structure set ({len(families)} families, {len(legs)} legs)"
        if name == "search_flights":
            leg_id = str(args.get("leg_id", ""))
            options = _normalize_ids(list(args.get("options") or []), "f")
            self.state["flights"][leg_id] = options
            act("search_flights", {"leg_id": leg_id, "options": options})
            return f"showing {len(options)} flights for {leg_id}"
        if name == "show_flights":
            act("show_flights", {"leg_id": args.get("leg_id", "")})
            return "shown"
        if name == "select_flight":
            self.state["selected"][f"flight:{args.get('leg_id')}"] = args.get("option_id")
            act(
                "select_flight",
                {"leg_id": args.get("leg_id", ""), "option_id": args.get("option_id", "")},
            )
            return "flight selected"
        if name == "search_hotels":
            city = str(args.get("city", ""))
            options = _normalize_ids(list(args.get("options") or []), "h")
            self.state["hotels"][city] = options
            act("search_hotels", {"city": city, "options": options})
            return f"showing {len(options)} hotels in {city}"
        if name == "show_hotels":
            act("show_hotels", {"city": args.get("city", "")})
            return "shown"
        if name == "select_hotel":
            self.state["selected"][f"hotel:{args.get('city')}"] = args.get("option_id")
            act(
                "select_hotel",
                {"city": args.get("city", ""), "option_id": args.get("option_id", "")},
            )
            return "hotel selected"
        if name == "get_active_itinerary":
            # Prefer the live browser snapshot (reflects the agent's hand edits);
            # fall back to what the brain itself set.
            if self.browser_state:
                return str(self.browser_state)
            it = self.state["itinerary"]
            return (
                str({"itinerary": it, "selected": self.state["selected"]})
                if it
                else "no itinerary open"
            )
        return "unknown tool"
