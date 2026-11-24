"""Where the plan goes next, and the planner's own words for it (H1).

The owner's call (24 Nov) stalled twice: "I'll add Banyan Air to your trip." and
"I'll add Azure Atoll Resort & Spa to your trip." were the whole turn, the screen
moved, and nothing came next until he said "go ahead" / "continue". So every step
that lands hands the model the next one, and the brain keeps a written line of
it as the floor (``owe`` in brain.py): the plan always moves on.

The order is the trip builder's: brief, flights, a hotel per city, activities,
the package, checkout. :func:`next_step` reads it off the trip, so a visitor who
skipped ahead by hand, or changed something, is led from where they are.

The lines are what the brain says when the model said nothing after a tool ran.
They carry one concrete detail from the inventory (a hotel's blurb, an
activity's), never an invented one. English only (H2, 25 Nov): the planner
speaks the languages ``persona.json`` lists, and each one needs its lines here
(``_ASK``, ``_LINES`` and the f-strings below take ``lang`` for that); a
language with none is said in English.

H3 (25 Nov): a pick (flight, hotel, nights, activity) no longer waits for a
second model request. The model is told before the pick what opens after it
(:meth:`HolidaysBrain.ahead`), says it in the same response as the call, and the
line here is the floor when it did not: the whole line if it said nothing, the
next choice alone if it only acknowledged the pick.
"""

from __future__ import annotations

from typing import Any, Literal

from . import engine as eng
from .engine import Trip

Step = Literal["brief", "flights", "hotels", "days", "package"]


def next_step(t: Trip) -> tuple[Step, str | None]:
    """The first unfilled step of the trip, and the city for a hotel step."""
    if t.missing():
        return "brief", None
    if not t.flight_id:
        return "flights", None
    for city, _ in eng.stops(t):
        if city not in t.hotels:
            return "hotels", city
    if not t.activities:
        return "days", None
    return "package", None


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:] if s else s


def _blurb(s: str) -> str:
    return _lower_first(s.strip().rstrip("."))


def who(t: Trip, lang: str) -> str:
    """The group, as said: "both of you", "the four of you"."""
    n = t.pax
    if n == 1:
        return "you"
    if n == 2:
        return "both of you"
    words = {3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"}
    return f"the {words.get(n, str(n))} of you"


_ASK = {
    "en": {
        "from_city": "which city you'll fly from",
        "destination": "where you'd love to go",
        "start_date": "when you'd like to travel",
        "nights": "how many nights",
    },
}


def ask_missing(t: Trip, lang: str) -> str:
    items = [_ASK.get(lang, _ASK["en"])[m] for m in t.missing()]
    said = items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]
    return f"Just tell me {said}."


def flight_line(t: Trip, lang: str) -> str:
    """The suggested flight, said: airline, stops, time, price for the group."""
    f = eng.recommended_flight(t)
    if f is None:
        return ""
    _, total = eng.flight_price(t, f)
    time = f["out"]["legs"][0]["depart"]
    stops = "nonstop" if not f["stops"] else f"{f['stops']} stop"
    return (
        f"My pick is {f['airline_name']}, {stops}, leaving at {time}, "
        f"{eng.money(total)} for {who(t, lang)}."
    )


def hotels_line(city: str, hotels: list[dict[str, Any]], lang: str) -> str:
    """Two hotels of a city with a detail each, and the question."""
    name = eng.CITIES[city]["name"]
    top = hotels[:2]
    if not top:
        return ""
    if len(top) == 1:
        return (
            f"Now the fun part, where you'll stay in {name}: {top[0]['name']}, "
            f"{_blurb(top[0]['blurb'])}. Shall I add it?"
        )
    a, b = top
    return (
        f"Now the fun part, where you'll stay in {name}: {a['name']}, {_blurb(a['blurb'])}, "
        f"or {b['name']}, {_blurb(b['blurb'])}. Which one catches your eye?"
    )


def activity_line(t: Trip, day: int, a: dict[str, Any], lang: str) -> str:
    """One activity that fits, with its detail and price, and the question."""
    price = eng.money(eng.activity_price(t, a["id"]))
    return (
        f"On day {day} there's the {a['name']}, {_blurb(a['blurb'])}, {price} for "
        f"{who(t, lang)}. Shall I add it, or hear another idea?"
    )


_LINES: dict[str, dict[str, str]] = {
    "en": {
        "brief_done": "Wonderful, {dest} it is, {tagline}! Shall I pull up the flights from {origin} first, or build the whole package in one go?",
        "brief_more": "Lovely, that's in. {ask}",
        "flights": "Here are the flights from {origin}. {pick} Which one shall I add?",
        "flight_in": "Lovely, {airline} is in.",
        "hotel_in": "{hotel} is in, gorgeous choice.",
        "nights_in": "Done, the nights are now {split}.",
        "activity_in": "{activity} is on day {day}.",
        "removed": "{activity} is off the plan.",
        "days": "Now let's fill your days.",
        "days_none": "Your days are as full as they can be.",
        "package": "Your holiday comes to {total} all in. Shall I open the whole package for a look, or are you ready to review and book?",
        "built": "Here's your whole holiday, {total} all in, with {highlight}. Happy with it, or shall we change anything before you book?",
        "offer_flights": "Shall I pull up the flights?",
        "offer_hotels": "Shall I show you where to stay in {city}?",
        "offer_days": "Shall I line up a few things to do?",
        "offer_package": "Shall I show you the whole package, or are you ready to book?",
    },
}


def line(lang: str, key: str, **kw: str) -> str:
    return _LINES.get(lang, _LINES["en"])[key].format(**kw)


def split_words(t: Trip) -> str:
    return ", ".join(f"{eng.CITIES[c]['name']} {n}" for c, n in eng.stops(t))


def brief_line(t: Trip, lang: str) -> str:
    """After the brief changed: the next question, or the two ways forward."""
    if t.missing():
        return line(lang, "brief_more", ask=ask_missing(t, lang))
    d = t.dest
    assert d is not None
    return line(
        lang,
        "brief_done",
        dest=d["name"],
        tagline=_lower_first(d["tagline"]),
        origin=eng.ORIGINS[t.from_city or "DEL"],
    )


def offer(t: Trip, lang: str) -> str:
    """The next step as a question, with no screen change: after a click."""
    kind, city = next_step(t)
    if kind == "brief":
        return ask_missing(t, lang)
    if kind == "flights":
        return line(lang, "offer_flights")
    if kind == "hotels" and city:
        return line(lang, "offer_hotels", city=eng.CITIES[city]["name"])
    if kind == "days":
        return line(lang, "offer_days")
    return line(lang, "offer_package")
