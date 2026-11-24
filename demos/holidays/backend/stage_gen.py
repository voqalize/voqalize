# Generated from holidays/frontend/src/stage/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
#   voqalize stage gen holidays/frontend/src/stage/scene.json --py holidays/backend/stage_gen.py --ts holidays/frontend/src/stage/scene.gen.ts
"""The moves of wanderloom, from its Stage Spec."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from voqalize.sdk.stage import Move, MoveClass, MoveSet, StageSpec, load_spec

#: The spec itself, carried here so the brain never reads the JSON at run
#: time (and a deploy that ships this file ships the spec with it).
SPEC: StageSpec = load_spec(
    '{"events":[{"doc":"One field of the brief changed.","id":"trip.brief_changed","note":"{by} set the brief\'s {field} to {value}","slice":"trip"},{"id":"trip.flight_picked","note":"{by} picked the flight {label}","slice":"trip"},{"id":"trip.hotel_picked","note":"{by} picked {label}","slice":"trip"},{"id":"trip.nights_changed","note":"{by} changed the nights: {label}","slice":"trip"},{"id":"trip.activity_added","note":"{by} added {label}","slice":"trip"},{"id":"trip.activity_removed","note":"{by} removed {label}","slice":"trip"},{"id":"trip.step_changed","note":"{by} opened the {step} step","react":"silent","slice":"trip"},{"id":"trip.page_changed","note":"{by} is on the {page} page","react":"silent","slice":"trip"},{"ask":"congratulate them in one short line and read the booking reference","id":"trip.paid","note":"{by} paid; booking {reference}","react":"speak","slice":"trip"}],"id":"wanderloom","languages":["en","hi"],"moves":[{"args":[{"doc":"home: the landing page with the destinations; plan: the trip builder; checkout: review and pay.","enum":["home","plan","checkout"],"name":"page"}],"claims":["taking you to","opening the planner","le chalti hoon"],"class":"navigate","doc":"Go to one of the site\'s pages, ringing the link first.","id":"trip.go","objects":["planner","checkout","destinations"],"say":"{go: plan} at the start of the sentence that takes them to the trip builder; {go: home} for the destinations.","verb":"go"},{"args":[{"doc":"A step of the trip builder.","enum":["brief","flights","hotels","days","package"],"name":"step"}],"class":"navigate","doc":"Open a step of the trip builder and ring its tab. Refused while the brief is missing what that step needs.","id":"trip.step","say":"{step: flights} as you start talking about that step of the trip builder: brief, flights, hotels, days or package.","verb":"step"},{"args":[{"doc":"Something on screen by the name it shows: flight 2, Sayan Ridge Villas, day 3, total, price breakdown.","name":"target"}],"class":"look","doc":"Scroll to a named thing on the page and ring it. Changes nothing.","id":"trip.show","say":"{show: day 3} right before the sentence about it, to ring it on screen; {show: flight 1}, {show: total}.","verb":"show"},{"args":[{"doc":"Airport code of the city they fly from: DEL, BOM, BLR, MAA, CCU, HYD, AMD, PNQ.","name":"from_city","optional":true},{"doc":"Destination id: kerala, goa, rajasthan, bali, dubai, thailand, singapore, maldives, switzerland.","name":"destination","optional":true},{"doc":"Departure date from home, YYYY-MM-DD.","name":"start_date","optional":true},{"name":"nights","optional":true,"type":"integer"},{"name":"adults","optional":true,"type":"integer"},{"doc":"Each child\'s age, 0 to 11, as digits (\\"6\\"). Strings, because a move\'s array arguments travel as strings.","name":"kids","optional":true,"type":"array"},{"doc":"Total budget in rupees for everyone, 0 for none.","name":"budget","optional":true,"type":"integer"},{"enum":["relaxed","adventure","honeymoon","family"],"name":"style","optional":true}],"claims":["filling in your trip","putting in your dates"],"class":"reversible","doc":"Fill the trip brief\'s fields that are given, ringing each one; the page opens the brief step if it is not on it.","id":"trip.brief","objects":["brief","dates","travellers"]},{"args":[{"default":"recommended","enum":["recommended","price","duration","departure"],"name":"sort"}],"claims":["showing you the flights","pulling up flights"],"class":"navigate","doc":"Open the flights step with the options for the brief, sorted.","id":"trip.flights","objects":["flights","flight options","fares"]},{"args":[{"doc":"A flight option id from the inventory, DEL-bali-2.","name":"flight_id"}],"claims":["picking the","booking the flight"],"class":"reversible","doc":"Ring a flight option and select it.","id":"trip.flight","objects":["flight"]},{"args":[{"doc":"City id: ubud, seminyak, munnar…","name":"city"},{"doc":"A tag to filter by: beach, pool, budget, luxury, family, honeymoon, relaxed, adventure, culture.","name":"want","optional":true}],"claims":["showing you hotels","pulling up hotels"],"class":"navigate","doc":"Open the hotels step on one city\'s tab, optionally filtered by a tag.","id":"trip.hotels","objects":["hotels","hotel options","stays"]},{"args":[{"doc":"City id.","name":"city"},{"name":"hotel_id"},{"name":"room_id"}],"claims":["swapping the hotel","switching the hotel","booking the hotel"],"class":"reversible","doc":"Ring a hotel\'s room in a city and select it, replacing that city\'s hotel.","id":"trip.hotel","objects":["hotel","room"]},{"args":[{"doc":"Nights in each city of the destination, in route order, as digits (\\"2\\", \\"4\\"), summing to the trip\'s nights. Strings, because a move\'s array arguments travel as strings.","name":"split","type":"array"}],"claims":["moving a night","changing the nights"],"class":"reversible","doc":"Set how the nights are split across the destination\'s cities; activities on days that move city are dropped.","id":"trip.nights","objects":["nights"]},{"args":[{"name":"activity_id"},{"doc":"Day of the holiday, 1 = arrival day.","name":"day","type":"integer"}],"claims":["adding the","adding a"],"class":"reversible","doc":"Ring a day and add an activity to it.","id":"trip.add","objects":["activity","day","itinerary"]},{"args":[{"name":"activity_id"},{"name":"day","type":"integer"}],"claims":["removing the","taking out the","dropping the"],"class":"reversible","doc":"Ring an activity on a day and take it off.","id":"trip.remove","objects":["activity"]},{"args":[{"name":"flight_id"},{"doc":"One per city with nights, as city:hotel_id:room_id.","name":"hotels","type":"array"},{"doc":"As day:activity_id.","name":"activities","type":"array"}],"claims":["building your package","putting your package together","putting the package together"],"class":"reversible","doc":"Lay a whole package on the page: the flight, a hotel per city, the activities, then open the package step with the priced day-by-day plan.","id":"trip.build","objects":["package","holiday","itinerary"]}],"slices":[{"doc":"the last change made to the trip on screen, by ids, as the page reports it","fields":[{"name":"step","optional":true},{"name":"field","optional":true},{"name":"value","optional":true},{"name":"flight_id","optional":true},{"name":"city","optional":true},{"name":"hotel_id","optional":true},{"name":"room_id","optional":true},{"items":{"type":"integer"},"name":"split","optional":true,"type":"array"},{"name":"activity_id","optional":true},{"name":"day","optional":true,"type":"integer"},{"name":"label","optional":true},{"name":"total","optional":true,"type":"integer"},{"name":"reference","optional":true},{"name":"page","optional":true}],"id":"trip"}],"stage":1}'
)
#: The spec's hash: a page reading another spec reports a different one.
SPEC_SHA256 = "aad631e27d5f72b50d7c34911f0b1d742d3ab8da9c089caad7a473cf775d6998"


class GoArgs(BaseModel):
    """The arguments of ``trip.go``."""

    page: Literal["home", "plan", "checkout"]
    """home: the landing page with the destinations; plan: the trip builder; checkout: review and pay."""


class StepArgs(BaseModel):
    """The arguments of ``trip.step``."""

    step: Literal["brief", "flights", "hotels", "days", "package"]
    """A step of the trip builder."""


class ShowArgs(BaseModel):
    """The arguments of ``trip.show``."""

    target: str
    """Something on screen by the name it shows: flight 2, Sayan Ridge Villas, day 3, total, price breakdown."""


class BriefArgs(BaseModel):
    """The arguments of ``trip.brief``."""

    from_city: str | None = None
    """Airport code of the city they fly from: DEL, BOM, BLR, MAA, CCU, HYD, AMD, PNQ."""
    destination: str | None = None
    """Destination id: kerala, goa, rajasthan, bali, dubai, thailand, singapore, maldives, switzerland."""
    start_date: str | None = None
    """Departure date from home, YYYY-MM-DD."""
    nights: int | None = None
    adults: int | None = None
    kids: list[str] | None = None
    """Each child's age, 0 to 11, as digits ("6"). Strings, because a move's array arguments travel as strings."""
    budget: int | None = None
    """Total budget in rupees for everyone, 0 for none."""
    style: Literal["relaxed", "adventure", "honeymoon", "family"] | None = None


class FlightsArgs(BaseModel):
    """The arguments of ``trip.flights``."""

    sort: Literal["recommended", "price", "duration", "departure"] = "recommended"


class FlightArgs(BaseModel):
    """The arguments of ``trip.flight``."""

    flight_id: str
    """A flight option id from the inventory, DEL-bali-2."""


class HotelsArgs(BaseModel):
    """The arguments of ``trip.hotels``."""

    city: str
    """City id: ubud, seminyak, munnar…"""
    want: str | None = None
    """A tag to filter by: beach, pool, budget, luxury, family, honeymoon, relaxed, adventure, culture."""


class HotelArgs(BaseModel):
    """The arguments of ``trip.hotel``."""

    city: str
    """City id."""
    hotel_id: str
    room_id: str


class NightsArgs(BaseModel):
    """The arguments of ``trip.nights``."""

    split: list[str]
    """Nights in each city of the destination, in route order, as digits ("2", "4"), summing to the trip's nights. Strings, because a move's array arguments travel as strings."""


class AddArgs(BaseModel):
    """The arguments of ``trip.add``."""

    activity_id: str
    day: int
    """Day of the holiday, 1 = arrival day."""


class RemoveArgs(BaseModel):
    """The arguments of ``trip.remove``."""

    activity_id: str
    day: int


class BuildArgs(BaseModel):
    """The arguments of ``trip.build``."""

    flight_id: str
    hotels: list[str]
    """One per city with nights, as city:hotel_id:room_id."""
    activities: list[str]
    """As day:activity_id."""


GO = Move(
    id="trip.go",
    verb="go",
    cls=MoveClass.NAVIGATE,
    args=("page",),
    say="{go: plan} at the start of the sentence that takes them to the trip builder; {go: home} for the destinations.",
    claims=(
        "taking you to",
        "opening the planner",
        "le chalti hoon",
    ),
    objects=(
        "planner",
        "checkout",
        "destinations",
    ),
)
"""Go to one of the site's pages, ringing the link first."""

STEP = Move(
    id="trip.step",
    verb="step",
    cls=MoveClass.NAVIGATE,
    args=("step",),
    say="{step: flights} as you start talking about that step of the trip builder: brief, flights, hotels, days or package.",
)
"""Open a step of the trip builder and ring its tab. Refused while the brief is missing what that step needs."""

SHOW = Move(
    id="trip.show",
    verb="show",
    cls=MoveClass.LOOK,
    args=("target",),
    say="{show: day 3} right before the sentence about it, to ring it on screen; {show: flight 1}, {show: total}.",
)
"""Scroll to a named thing on the page and ring it. Changes nothing."""

BRIEF = Move(
    id="trip.brief",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "from_city",
        "destination",
        "start_date",
        "nights",
        "adults",
        "kids",
        "budget",
        "style",
    ),
    claims=(
        "filling in your trip",
        "putting in your dates",
    ),
    objects=(
        "brief",
        "dates",
        "travellers",
    ),
)
"""Fill the trip brief's fields that are given, ringing each one; the page opens the brief step if it is not on it."""

FLIGHTS = Move(
    id="trip.flights",
    verb=None,
    cls=MoveClass.NAVIGATE,
    args=("sort",),
    claims=(
        "showing you the flights",
        "pulling up flights",
    ),
    objects=(
        "flights",
        "flight options",
        "fares",
    ),
)
"""Open the flights step with the options for the brief, sorted."""

FLIGHT = Move(
    id="trip.flight",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=("flight_id",),
    claims=(
        "picking the",
        "booking the flight",
    ),
    objects=("flight",),
)
"""Ring a flight option and select it."""

HOTELS = Move(
    id="trip.hotels",
    verb=None,
    cls=MoveClass.NAVIGATE,
    args=(
        "city",
        "want",
    ),
    claims=(
        "showing you hotels",
        "pulling up hotels",
    ),
    objects=(
        "hotels",
        "hotel options",
        "stays",
    ),
)
"""Open the hotels step on one city's tab, optionally filtered by a tag."""

HOTEL = Move(
    id="trip.hotel",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "city",
        "hotel_id",
        "room_id",
    ),
    claims=(
        "swapping the hotel",
        "switching the hotel",
        "booking the hotel",
    ),
    objects=(
        "hotel",
        "room",
    ),
)
"""Ring a hotel's room in a city and select it, replacing that city's hotel."""

NIGHTS = Move(
    id="trip.nights",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=("split",),
    claims=(
        "moving a night",
        "changing the nights",
    ),
    objects=("nights",),
)
"""Set how the nights are split across the destination's cities; activities on days that move city are dropped."""

ADD = Move(
    id="trip.add",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "activity_id",
        "day",
    ),
    claims=(
        "adding the",
        "adding a",
    ),
    objects=(
        "activity",
        "day",
        "itinerary",
    ),
)
"""Ring a day and add an activity to it."""

REMOVE = Move(
    id="trip.remove",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "activity_id",
        "day",
    ),
    claims=(
        "removing the",
        "taking out the",
        "dropping the",
    ),
    objects=("activity",),
)
"""Ring an activity on a day and take it off."""

BUILD = Move(
    id="trip.build",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "flight_id",
        "hotels",
        "activities",
    ),
    claims=(
        "building your package",
        "putting your package together",
        "putting the package together",
    ),
    objects=(
        "package",
        "holiday",
        "itinerary",
    ),
)
"""Lay a whole package on the page: the flight, a hotel per city, the activities, then open the package step with the priced day-by-day plan."""

MOVES = MoveSet(
    (
        GO,
        STEP,
        SHOW,
        BRIEF,
        FLIGHTS,
        FLIGHT,
        HOTELS,
        HOTEL,
        NIGHTS,
        ADD,
        REMOVE,
        BUILD,
    )
)

#: The line each cue is taught with, in the spec's order.
PROMPT_LINES: tuple[str, ...] = (
    "{go: plan} at the start of the sentence that takes them to the trip builder; {go: home} for the destinations.",
    "{step: flights} as you start talking about that step of the trip builder: brief, flights, hotels, days or package.",
    "{show: day 3} right before the sentence about it, to ring it on screen; {show: flight 1}, {show: total}.",
)

#: The slices of the page's state a read may name.
SliceId = Literal["trip"]


class ReadRequest(BaseModel):
    """What the read tool takes: the slice to read, from the brain's mirror."""

    slice: SliceId = Field(
        description="Which part of their screen to read. trip: the last change made to the trip on screen, by ids, as the page reports it."
    )
