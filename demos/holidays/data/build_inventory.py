"""Write ``inventory.json``: Wanderloom's whole, fictional holiday inventory.

Everything a trip is built from: the cities a visitor flies from, nine
destinations and the cities within them, round-trip flight options on made-up
airlines, hotels with room types, activities, transfers and the tax rule. The
brain (``backend/``) and the page (``frontend/``) both read the file this writes,
so the agent and the screen quote the same fares, hotels and prices, and the
agent never invents one.

Nothing here is real: the airlines, hotels and experiences are invented, and
every price is made up for the demo. Place names (Munnar, Ubud, Lucerne) and the
airports' codes are ordinary geography.

Run from ``demos/``: ``uv run python holidays/data/build_inventory.py``. The
output is deterministic, and ``tests/test_holidays_engine.py`` fails when the
committed file is stale.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

OUT = Path(__file__).with_name("inventory.json")

# ─── Where a visitor flies from ───────────────────────────────────────────────

ORIGINS = [
    {"id": "DEL", "city": "Delhi"},
    {"id": "BOM", "city": "Mumbai"},
    {"id": "BLR", "city": "Bengaluru"},
    {"id": "MAA", "city": "Chennai"},
    {"id": "CCU", "city": "Kolkata"},
    {"id": "HYD", "city": "Hyderabad"},
    {"id": "AMD", "city": "Ahmedabad"},
    {"id": "PNQ", "city": "Pune"},
]

#: Airports a trip lands at or leaves from, with their clock against IST in
#: minutes (fixed: the demo shows times, it does not track daylight saving).
AIRPORTS: dict[str, dict[str, Any]] = {
    "DEL": {"city": "Delhi", "offset": 0},
    "BOM": {"city": "Mumbai", "offset": 0},
    "BLR": {"city": "Bengaluru", "offset": 0},
    "MAA": {"city": "Chennai", "offset": 0},
    "CCU": {"city": "Kolkata", "offset": 0},
    "HYD": {"city": "Hyderabad", "offset": 0},
    "AMD": {"city": "Ahmedabad", "offset": 0},
    "PNQ": {"city": "Pune", "offset": 0},
    "COK": {"city": "Kochi", "offset": 0},
    "GOI": {"city": "Goa", "offset": 0},
    "JAI": {"city": "Jaipur", "offset": 0},
    "UDR": {"city": "Udaipur", "offset": 0},
    "DPS": {"city": "Bali (Denpasar)", "offset": 150},
    "DXB": {"city": "Dubai", "offset": -90},
    "HKT": {"city": "Phuket", "offset": 90},
    "BKK": {"city": "Bangkok", "offset": 90},
    "SIN": {"city": "Singapore", "offset": 150},
    "MLE": {"city": "Malé", "offset": -30},
    "ZRH": {"city": "Zurich", "offset": -270},
}

#: Nonstop block times in minutes, one way, where a nonstop is sold. Anything
#: missing connects through a hub.
NONSTOP: dict[tuple[str, str], int] = {}
for origin, row in {
    "DEL": {
        "COK": 200,
        "GOI": 150,
        "JAI": 60,
        "UDR": 85,
        "DXB": 220,
        "HKT": 300,
        "BKK": 270,
        "SIN": 340,
        "ZRH": 540,
    },
    "BOM": {
        "COK": 115,
        "GOI": 70,
        "JAI": 105,
        "UDR": 85,
        "DXB": 190,
        "HKT": 280,
        "BKK": 270,
        "SIN": 330,
        "MLE": 200,
        "ZRH": 540,
    },
    "BLR": {
        "COK": 70,
        "GOI": 75,
        "JAI": 165,
        "DXB": 240,
        "HKT": 250,
        "BKK": 245,
        "SIN": 260,
        "MLE": 110,
    },
    "MAA": {"COK": 75, "GOI": 90, "DXB": 255, "HKT": 200, "BKK": 215, "SIN": 235, "MLE": 105},
    "CCU": {"GOI": 150, "JAI": 140, "DXB": 300, "HKT": 185, "BKK": 155, "SIN": 230},
    "HYD": {"COK": 95, "GOI": 75, "JAI": 130, "DXB": 230, "BKK": 240, "SIN": 255},
    "AMD": {"GOI": 95, "JAI": 85, "UDR": 55, "DXB": 185},
    "PNQ": {"GOI": 60, "JAI": 120, "DXB": 205},
    # Legs out of the hubs, for connections.
    "SIN": {"DPS": 160},
}.items():
    for dest, minutes in row.items():
        NONSTOP[(origin, dest)] = minutes
# Domestic legs into the two hubs, so every city can connect.
for origin, row in {
    "DEL": {"BOM": 130, "BLR": 165, "MAA": 170, "CCU": 130, "HYD": 135, "AMD": 95, "PNQ": 130},
    "BOM": {"BLR": 95, "MAA": 115, "CCU": 160, "HYD": 85, "AMD": 75, "PNQ": 50},
}.items():
    for dest, minutes in row.items():
        NONSTOP[(origin, dest)] = minutes

AIRLINES = {
    "banyan": {
        "name": "Banyan Air",
        "kind": "full-service",
        "baggage": "25 kg check-in · 7 kg cabin",
        "intl_baggage": "30 kg check-in · 7 kg cabin",
        "meal": "Meal included",
    },
    "saffron": {
        "name": "Saffron Air",
        "kind": "low-cost",
        "baggage": "15 kg check-in · 7 kg cabin",
        "intl_baggage": "20 kg check-in · 7 kg cabin",
        "meal": "Meals to buy on board",
    },
    "monsoon": {
        "name": "Monsoon Air",
        "kind": "low-cost",
        "baggage": "15 kg check-in · 7 kg cabin",
        "intl_baggage": "20 kg check-in · 7 kg cabin",
        "meal": "Meals to buy on board",
    },
    "kestrel": {
        "name": "Kestrel Airways",
        "kind": "full-service",
        "baggage": "25 kg check-in · 7 kg cabin",
        "intl_baggage": "30 kg check-in · 7 kg cabin",
        "meal": "Meal included",
    },
    "lagoon": {
        "name": "Lagoon Air",
        "kind": "low-cost",
        "baggage": "15 kg check-in · 7 kg cabin",
        "intl_baggage": "20 kg check-in · 7 kg cabin",
        "meal": "Meals to buy on board",
    },
    "alpenstar": {
        "name": "Alpenstar",
        "kind": "full-service",
        "baggage": "25 kg check-in · 7 kg cabin",
        "intl_baggage": "2 x 23 kg check-in · 8 kg cabin",
        "meal": "Meal included",
    },
}

# ─── Destinations ─────────────────────────────────────────────────────────────

# Each destination: where it lands and leaves, its cities in route order, how a
# stay of n nights is split across them, transfers, hotels and activities.
# `splits` is the authored default for each length of stay; a city with 0
# nights is skipped.


def hotel(
    id: str,
    name: str,
    stars: int,
    area: str,
    rooms: list[tuple[str, str, int]],
    inclusions: list[str],
    tags: list[str],
    blurb: str,
) -> dict[str, Any]:
    return {
        "id": id,
        "name": name,
        "stars": stars,
        "area": area,
        "rooms": [{"id": rid, "name": rname, "price": price} for rid, rname, price in rooms],
        "inclusions": inclusions,
        "tags": tags,
        "blurb": blurb,
    }


def act(
    id: str,
    name: str,
    duration: str,
    slot: str,
    adult: int,
    child: int,
    tags: list[str],
    blurb: str,
    *,
    min_age: int = 0,
    closed: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": id,
        "name": name,
        "duration": duration,
        "slot": slot,
        "price_adult": adult,
        "price_child": child,
        "min_age": min_age,
        "closed": closed or [],
        "tags": tags,
        "blurb": blurb,
    }


DESTINATIONS: list[dict[str, Any]] = [
    {
        "id": "kerala",
        "name": "Kerala",
        "country": "India",
        "domestic": True,
        "tagline": "Tea hills, backwater houseboats and Fort Kochi's old lanes",
        "best_months": [10, 11, 12, 1, 2, 3],
        "arrive": "COK",
        "depart": "COK",
        "nights": [3, 8],
        "default_nights": 5,
        "hue": "#2f7d5b",
        "splits": {
            "3": [2, 1, 0],
            "4": [2, 1, 1],
            "5": [2, 2, 1],
            "6": [3, 2, 1],
            "7": [3, 2, 2],
            "8": [3, 3, 2],
        },
        "cities": [
            {
                "id": "munnar",
                "name": "Munnar",
                "blurb": "Misty tea estates in the Western Ghats",
                "hotels": [
                    hotel(
                        "tea-terrace",
                        "Tea Terrace Retreat",
                        4,
                        "Chithirapuram",
                        [
                            ("valley", "Valley View Room", 6800),
                            ("cottage", "Plantation Cottage", 9400),
                        ],
                        ["Breakfast", "Guided tea-estate walk"],
                        ["relaxed", "honeymoon", "family"],
                        "Cottages stepped down a working tea estate.",
                    ),
                    hotel(
                        "mistvale",
                        "Mistvale Resort & Spa",
                        5,
                        "Pallivasal",
                        [("deluxe", "Deluxe Room", 11200), ("pool-villa", "Pool Villa", 18500)],
                        ["Breakfast and dinner", "Spa credit ₹2,000 per stay"],
                        ["honeymoon", "relaxed"],
                        "Private pool villas facing the valley.",
                    ),
                    hotel(
                        "cardamom-hills",
                        "Cardamom Hills Inn",
                        3,
                        "Munnar town",
                        [("standard", "Standard Room", 3600), ("family", "Family Room", 5200)],
                        ["Breakfast"],
                        ["family", "budget"],
                        "Simple and central, a walk from the market.",
                    ),
                    hotel(
                        "highrange-camp",
                        "Highrange Base Camp",
                        3,
                        "Kolukkumalai road",
                        [("tent", "Luxury Tent", 4900)],
                        ["All meals", "Guided sunrise trek"],
                        ["adventure"],
                        "Tents on a ridge, for early starts and long walks.",
                    ),
                ],
                "activities": [
                    act(
                        "munnar-tea-museum",
                        "Tea factory and museum tour",
                        "2 hrs",
                        "morning",
                        1200,
                        600,
                        ["culture", "family", "relaxed"],
                        "See leaf become tea, then taste five grades.",
                    ),
                    act(
                        "munnar-eravikulam",
                        "Eravikulam hills nature drive",
                        "3 hrs",
                        "morning",
                        1800,
                        900,
                        ["family", "relaxed", "honeymoon"],
                        "Grasslands and shola forest with a naturalist.",
                    ),
                    act(
                        "munnar-jeep-sunrise",
                        "Kolukkumalai sunrise jeep safari",
                        "5 hrs",
                        "morning",
                        3500,
                        2000,
                        ["adventure", "honeymoon"],
                        "Off-road climb to a sunrise above the clouds.",
                        min_age=8,
                    ),
                    act(
                        "munnar-zipline",
                        "Valley zipline and rope course",
                        "2 hrs",
                        "afternoon",
                        1500,
                        1200,
                        ["adventure", "family"],
                        "Six lines over a cardamom valley.",
                        min_age=10,
                    ),
                    act(
                        "munnar-top-station",
                        "Top Station scenic drive",
                        "4 hrs",
                        "afternoon",
                        2400,
                        1200,
                        ["relaxed", "honeymoon", "family"],
                        "A slow drive to the ghats' best lookout.",
                    ),
                    act(
                        "munnar-spice-dinner",
                        "Plantation bonfire dinner",
                        "2 hrs",
                        "evening",
                        1600,
                        800,
                        ["relaxed", "honeymoon", "family"],
                        "Kerala dinner around a fire on the estate.",
                    ),
                ],
            },
            {
                "id": "alleppey",
                "name": "Alleppey",
                "blurb": "Backwaters, houseboats and Marari's quiet beach",
                "hotels": [
                    hotel(
                        "vembanad-palace",
                        "Vembanad Lake Palace",
                        5,
                        "Punnamada",
                        [("lake", "Lake View Room", 12800), ("suite", "Heritage Suite", 19000)],
                        ["Breakfast", "Sunset lake cruise"],
                        ["honeymoon", "relaxed"],
                        "A restored lakeside mansion with its own jetty.",
                    ),
                    hotel(
                        "kettuvallam",
                        "Kettuvallam Premium Houseboat",
                        4,
                        "Finishing Point jetty",
                        [
                            ("1bhk", "One-bedroom Houseboat", 14500),
                            ("2bhk", "Two-bedroom Houseboat", 22000),
                        ],
                        ["All meals on board", "Overnight backwater cruise"],
                        ["honeymoon", "family", "relaxed"],
                        "Your own boat and crew for the night.",
                    ),
                    hotel(
                        "coir-coast",
                        "Coir Coast Homestay",
                        3,
                        "Marari Beach",
                        [("garden", "Garden Room", 4200), ("beach-cottage", "Beach Cottage", 6300)],
                        ["Breakfast", "Bicycles"],
                        ["beach", "family", "budget", "relaxed"],
                        "Cottages under palms, steps from the sand.",
                    ),
                ],
                "activities": [
                    act(
                        "alleppey-kayak",
                        "Village canal kayak trail",
                        "3 hrs",
                        "morning",
                        1900,
                        1200,
                        ["adventure", "family"],
                        "Paddle the narrow canals the houseboats can't reach.",
                        min_age=8,
                    ),
                    act(
                        "alleppey-shikara",
                        "Sunset shikara ride",
                        "2 hrs",
                        "evening",
                        2200,
                        1100,
                        ["honeymoon", "relaxed", "family"],
                        "A slow canopy boat as the light goes gold.",
                    ),
                    act(
                        "alleppey-ayurveda",
                        "Ayurvedic couple's massage",
                        "90 min",
                        "afternoon",
                        4500,
                        0,
                        ["honeymoon", "relaxed"],
                        "Side by side, in a garden treatment room.",
                        min_age=18,
                    ),
                    act(
                        "alleppey-cooking",
                        "Backwater home cooking class",
                        "3 hrs",
                        "morning",
                        2100,
                        1000,
                        ["culture", "family"],
                        "Cook fish curry and appam with a village family.",
                        closed=["Sun"],
                    ),
                ],
            },
            {
                "id": "kochi",
                "name": "Kochi",
                "blurb": "Fort Kochi's lanes, nets and spice markets",
                "hotels": [
                    hotel(
                        "spice-route",
                        "Spice Route Heritage Hotel",
                        4,
                        "Fort Kochi",
                        [
                            ("heritage", "Heritage Room", 7200),
                            ("courtyard", "Courtyard Suite", 10500),
                        ],
                        ["Breakfast", "Heritage walk"],
                        ["culture", "honeymoon", "relaxed"],
                        "A merchant's house round a frangipani courtyard.",
                    ),
                    hotel(
                        "marine-grand",
                        "Marine Drive Grand",
                        5,
                        "Marine Drive",
                        [("seaview", "Deluxe Sea View", 9800), ("club", "Club Room", 13400)],
                        ["Breakfast", "Airport transfer"],
                        ["family", "relaxed"],
                        "Big rooms over the harbour, with a pool.",
                    ),
                    hotel(
                        "jew-town-lodge",
                        "Mattancherry Lodge",
                        3,
                        "Mattancherry",
                        [("standard", "Standard Room", 3400)],
                        ["Breakfast"],
                        ["budget", "culture"],
                        "Small and friendly, in the old spice quarter.",
                    ),
                ],
                "activities": [
                    act(
                        "kochi-heritage-walk",
                        "Fort Kochi heritage walk",
                        "2.5 hrs",
                        "morning",
                        900,
                        450,
                        ["culture", "family"],
                        "Churches, Chinese nets and Dutch houses on foot.",
                    ),
                    act(
                        "kochi-kathakali",
                        "Kathakali performance with make-up viewing",
                        "1.5 hrs",
                        "evening",
                        700,
                        400,
                        ["culture", "family", "honeymoon"],
                        "Watch the make-up go on, then the dance-drama.",
                    ),
                    act(
                        "kochi-spice-kitchen",
                        "Spice market and kitchen class",
                        "3 hrs",
                        "afternoon",
                        2300,
                        1100,
                        ["culture", "relaxed"],
                        "Shop the spice market, then cook with what you bought.",
                        closed=["Sun"],
                    ),
                    act(
                        "kochi-harbour-cruise",
                        "Harbour sunset cruise",
                        "1.5 hrs",
                        "evening",
                        1200,
                        600,
                        ["relaxed", "family", "honeymoon"],
                        "Dolphins, ships and the nets from the water.",
                    ),
                ],
            },
        ],
        "transfers": [
            {
                "id": "kerala-arrive",
                "from": "COK airport",
                "to": "munnar",
                "mode": "car",
                "duration": "4 hrs",
                "pricing": "per_vehicle",
                "prices": {"sedan": 4200, "suv": 5600, "van": 7800},
            },
            {
                "id": "kerala-munnar-alleppey",
                "from": "munnar",
                "to": "alleppey",
                "mode": "car",
                "duration": "5 hrs",
                "pricing": "per_vehicle",
                "prices": {"sedan": 4800, "suv": 6200, "van": 8600},
            },
            {
                "id": "kerala-alleppey-kochi",
                "from": "alleppey",
                "to": "kochi",
                "mode": "car",
                "duration": "1.5 hrs",
                "pricing": "per_vehicle",
                "prices": {"sedan": 1900, "suv": 2600, "van": 3800},
            },
            {
                "id": "kerala-munnar-kochi",
                "from": "munnar",
                "to": "kochi",
                "mode": "car",
                "duration": "4 hrs",
                "pricing": "per_vehicle",
                "prices": {"sedan": 4000, "suv": 5400, "van": 7600},
            },
            {
                "id": "kerala-depart",
                "from": "last",
                "to": "COK airport",
                "mode": "car",
                "duration": "1-2 hrs",
                "pricing": "per_vehicle",
                "prices": {"sedan": 1800, "suv": 2400, "van": 3600},
            },
        ],
    },
    {
        "id": "goa",
        "name": "Goa",
        "country": "India",
        "domestic": True,
        "tagline": "Beach shacks up north, quiet coves down south",
        "best_months": [11, 12, 1, 2, 3],
        "arrive": "GOI",
        "depart": "GOI",
        "nights": [3, 7],
        "default_nights": 4,
        "hue": "#e07a3f",
        "splits": {"3": [3, 0], "4": [2, 2], "5": [3, 2], "6": [3, 3], "7": [4, 3]},
        "cities": [
            {
                "id": "north-goa",
                "name": "North Goa",
                "blurb": "Busy beaches, cafés and nightlife",
                "hotels": [
                    hotel(
                        "candolim-sands",
                        "Candolim Sands Resort",
                        4,
                        "Candolim",
                        [("pool", "Pool View Room", 7400), ("beach", "Beach Facing Room", 9900)],
                        ["Breakfast", "Beach loungers"],
                        ["beach", "family", "relaxed"],
                        "Two minutes from the sand, with a lagoon pool.",
                    ),
                    hotel(
                        "vagator-cliff",
                        "Vagator Cliff Villas",
                        5,
                        "Vagator",
                        [
                            ("villa", "Cliff Villa", 16800),
                            ("pool-villa", "Plunge Pool Villa", 21500),
                        ],
                        ["Breakfast", "Sunset drinks"],
                        ["beach", "honeymoon"],
                        "Villas on the red cliffs above the sea.",
                    ),
                    hotel(
                        "anjuna-hostel",
                        "Anjuna Courtyard Hotel",
                        3,
                        "Anjuna",
                        [("standard", "Courtyard Room", 3900)],
                        ["Breakfast", "Scooter hire desk"],
                        ["budget", "adventure"],
                        "A friendly base near the flea market.",
                    ),
                ],
                "activities": [
                    act(
                        "goa-watersports",
                        "Calangute water sports pack",
                        "3 hrs",
                        "morning",
                        2600,
                        1800,
                        ["adventure", "family"],
                        "Parasailing, jet ski and a banana boat.",
                        min_age=10,
                    ),
                    act(
                        "goa-fort-sunset",
                        "Aguada fort and sunset cruise",
                        "3 hrs",
                        "evening",
                        1800,
                        900,
                        ["relaxed", "family", "honeymoon"],
                        "The old fort, then the river at sundown.",
                    ),
                    act(
                        "goa-scuba",
                        "Grande Island try-dive",
                        "Full day",
                        "full_day",
                        5200,
                        0,
                        ["adventure", "honeymoon"],
                        "A first dive with an instructor, lunch on the boat.",
                        min_age=12,
                    ),
                    act(
                        "goa-spice-farm",
                        "Spice plantation lunch",
                        "4 hrs",
                        "morning",
                        1500,
                        750,
                        ["culture", "family", "relaxed"],
                        "A guided walk and a Goan thali on banana leaf.",
                    ),
                    act(
                        "goa-night-market",
                        "Saturday night market",
                        "3 hrs",
                        "evening",
                        600,
                        300,
                        ["culture", "family"],
                        "Food stalls, music and crafts.",
                        closed=["Sun", "Mon", "Tue", "Wed", "Thu", "Fri"],
                    ),
                ],
            },
            {
                "id": "south-goa",
                "name": "South Goa",
                "blurb": "Long, quiet beaches and old Portuguese villages",
                "hotels": [
                    hotel(
                        "palolem-palms",
                        "Palolem Palms Cottages",
                        3,
                        "Palolem",
                        [("cottage", "Beach Cottage", 4600)],
                        ["Breakfast", "Kayak use"],
                        ["beach", "budget", "relaxed"],
                        "Wooden cottages along a crescent bay.",
                    ),
                    hotel(
                        "cavelossim-grand",
                        "Cavelossim Grand Resort",
                        5,
                        "Cavelossim",
                        [("deluxe", "Deluxe Room", 12400), ("family", "Family Suite", 17800)],
                        ["Breakfast and dinner", "Kids' club"],
                        ["beach", "family", "relaxed"],
                        "A big resort between the river and the sea.",
                    ),
                    hotel(
                        "agonda-retreat",
                        "Agonda Bay Retreat",
                        4,
                        "Agonda",
                        [("sea", "Sea View Room", 8900), ("villa", "Garden Villa", 11600)],
                        ["Breakfast", "Daily yoga"],
                        ["beach", "honeymoon", "relaxed"],
                        "Twelve rooms on Goa's quietest beach.",
                    ),
                ],
                "activities": [
                    act(
                        "goa-dolphins",
                        "Dolphin-spotting boat trip",
                        "2 hrs",
                        "morning",
                        1100,
                        600,
                        ["family", "relaxed"],
                        "Early boat out of Palolem bay.",
                    ),
                    act(
                        "goa-old-goa",
                        "Old Goa churches and Fontainhas walk",
                        "4 hrs",
                        "morning",
                        1700,
                        850,
                        ["culture", "family"],
                        "Baroque churches and the Latin quarter's lanes.",
                    ),
                    act(
                        "goa-kayak",
                        "Mangrove kayaking",
                        "3 hrs",
                        "afternoon",
                        2000,
                        1300,
                        ["adventure", "family"],
                        "Paddle the Sal river's mangroves.",
                        min_age=8,
                    ),
                    act(
                        "goa-beach-dinner",
                        "Private candlelit beach dinner",
                        "2 hrs",
                        "evening",
                        4800,
                        0,
                        ["honeymoon"],
                        "A table on the sand for two.",
                        min_age=18,
                    ),
                ],
            },
        ],
        "transfers": [
            {
                "id": "goa-arrive",
                "from": "GOI airport",
                "to": "first",
                "mode": "car",
                "duration": "1-1.5 hrs",
                "pricing": "per_vehicle",
                "prices": {"sedan": 1900, "suv": 2600, "van": 3800},
            },
            {
                "id": "goa-north-south",
                "from": "north-goa",
                "to": "south-goa",
                "mode": "car",
                "duration": "1.5 hrs",
                "pricing": "per_vehicle",
                "prices": {"sedan": 2200, "suv": 3000, "van": 4200},
            },
            {
                "id": "goa-depart",
                "from": "last",
                "to": "GOI airport",
                "mode": "car",
                "duration": "1 hr",
                "pricing": "per_vehicle",
                "prices": {"sedan": 1700, "suv": 2300, "van": 3400},
            },
        ],
    },
    {
        "id": "rajasthan",
        "name": "Rajasthan",
        "country": "India",
        "domestic": True,
        "tagline": "Pink-city forts and Udaipur's lake palaces",
        "best_months": [10, 11, 12, 1, 2, 3],
        "arrive": "JAI",
        "depart": "UDR",
        "nights": [4, 8],
        "default_nights": 5,
        "hue": "#c2563a",
        "splits": {"4": [2, 0, 2], "5": [2, 1, 2], "6": [2, 2, 2], "7": [3, 2, 2], "8": [3, 2, 3]},
        "cities": [
            {
                "id": "jaipur",
                "name": "Jaipur",
                "blurb": "Forts, bazaars and block-printed everything",
                "hotels": [
                    hotel(
                        "amber-haveli",
                        "Amber Haveli Hotel",
                        4,
                        "Old City",
                        [("heritage", "Heritage Room", 6900), ("suite", "Jharokha Suite", 9800)],
                        ["Breakfast", "Rooftop folk music evenings"],
                        ["culture", "honeymoon", "relaxed"],
                        "A painted haveli inside the walled city.",
                    ),
                    hotel(
                        "rambagh-court",
                        "Rambagh Court Resort",
                        5,
                        "Bhawani Singh Road",
                        [("palace", "Palace Room", 14200), ("family", "Family Suite", 21000)],
                        ["Breakfast", "Pool and spa"],
                        ["family", "relaxed", "honeymoon"],
                        "Gardens, peacocks and a big pool.",
                    ),
                    hotel(
                        "pinkcity-inn",
                        "Pink City Inn",
                        3,
                        "MI Road",
                        [("standard", "Standard Room", 3200), ("family", "Family Room", 4800)],
                        ["Breakfast"],
                        ["budget", "family"],
                        "Clean, central and near the bazaars.",
                    ),
                ],
                "activities": [
                    act(
                        "jaipur-amber-fort",
                        "Amber Fort and stepwell morning",
                        "4 hrs",
                        "morning",
                        1600,
                        800,
                        ["culture", "family"],
                        "The hill fort with a guide, then Panna Meena stepwell.",
                    ),
                    act(
                        "jaipur-balloon",
                        "Hot-air balloon at dawn",
                        "3 hrs",
                        "morning",
                        13500,
                        11000,
                        ["adventure", "honeymoon"],
                        "Float over villages and forts at sunrise.",
                        min_age=8,
                    ),
                    act(
                        "jaipur-block-print",
                        "Block-printing workshop",
                        "2 hrs",
                        "afternoon",
                        1400,
                        900,
                        ["culture", "family", "relaxed"],
                        "Print your own scarf with a master printer.",
                        closed=["Sun"],
                    ),
                    act(
                        "jaipur-food-walk",
                        "Old City food walk",
                        "3 hrs",
                        "evening",
                        1900,
                        1000,
                        ["culture", "family"],
                        "Kachori, lassi and ghewar with a local cook.",
                    ),
                    act(
                        "jaipur-cycle",
                        "Bazaar cycle tour at dawn",
                        "3 hrs",
                        "morning",
                        2200,
                        1500,
                        ["adventure", "culture"],
                        "The walled city before the traffic wakes.",
                        min_age=12,
                    ),
                ],
            },
            {
                "id": "jodhpur",
                "name": "Jodhpur",
                "blurb": "The blue city under Mehrangarh",
                "hotels": [
                    hotel(
                        "blue-lane",
                        "Blue Lane Haveli",
                        3,
                        "Navchokiya",
                        [("standard", "Haveli Room", 3800)],
                        ["Breakfast", "Fort-view rooftop"],
                        ["budget", "culture"],
                        "A blue house below the fort walls.",
                    ),
                    hotel(
                        "umaid-gardens",
                        "Umaid Gardens Hotel",
                        5,
                        "Ratanada",
                        [("deluxe", "Garden Room", 12600), ("suite", "Royal Suite", 18800)],
                        ["Breakfast and dinner", "Vintage-car airport pick-up"],
                        ["honeymoon", "family", "relaxed"],
                        "Sandstone wings round a formal garden.",
                    ),
                ],
                "activities": [
                    act(
                        "jodhpur-mehrangarh",
                        "Mehrangarh fort with a historian",
                        "3 hrs",
                        "morning",
                        1500,
                        750,
                        ["culture", "family"],
                        "The fort's galleries and ramparts.",
                    ),
                    act(
                        "jodhpur-zipline",
                        "Fort ramparts zipline",
                        "1.5 hrs",
                        "afternoon",
                        2400,
                        2000,
                        ["adventure", "family"],
                        "Six lines across the fort's lakes and walls.",
                        min_age=10,
                    ),
                    act(
                        "jodhpur-village-safari",
                        "Bishnoi village jeep safari",
                        "4 hrs",
                        "afternoon",
                        2600,
                        1300,
                        ["culture", "adventure", "family"],
                        "Potters, weavers and blackbuck country.",
                    ),
                ],
            },
            {
                "id": "udaipur",
                "name": "Udaipur",
                "blurb": "Lakes, palaces and rooftop sunsets",
                "hotels": [
                    hotel(
                        "lake-pichola",
                        "Lake Pichola Palace Hotel",
                        5,
                        "Lake Pichola",
                        [("lake", "Lake View Room", 16400), ("suite", "Lake Suite", 26000)],
                        ["Breakfast", "Boat transfer to the old city"],
                        ["honeymoon", "relaxed"],
                        "Rooms on the water facing the City Palace.",
                    ),
                    hotel(
                        "gangaur-ghat",
                        "Gangaur Ghat Haveli",
                        4,
                        "Gangaur Ghat",
                        [("heritage", "Heritage Room", 7600), ("terrace", "Terrace Room", 9200)],
                        ["Breakfast", "Rooftop restaurant"],
                        ["culture", "honeymoon", "family"],
                        "A haveli on the ghats with a rooftop view.",
                    ),
                    hotel(
                        "fatehsagar-stay",
                        "Fateh Sagar Stay",
                        3,
                        "Fateh Sagar",
                        [("standard", "Standard Room", 3500), ("family", "Family Room", 5000)],
                        ["Breakfast"],
                        ["budget", "family"],
                        "By the quieter lake, with easy parking.",
                    ),
                ],
                "activities": [
                    act(
                        "udaipur-city-palace",
                        "City Palace guided visit",
                        "3 hrs",
                        "morning",
                        1700,
                        850,
                        ["culture", "family"],
                        "Courtyards, mirror rooms and the lake views.",
                    ),
                    act(
                        "udaipur-sunset-boat",
                        "Lake Pichola sunset boat",
                        "1 hr",
                        "evening",
                        1300,
                        650,
                        ["relaxed", "honeymoon", "family"],
                        "Out to the island palace as the sun sets.",
                    ),
                    act(
                        "udaipur-cooking",
                        "Rajasthani cooking class",
                        "3 hrs",
                        "afternoon",
                        1800,
                        900,
                        ["culture", "family", "relaxed"],
                        "Dal baati and gatte in a family kitchen.",
                    ),
                    act(
                        "udaipur-horse-ride",
                        "Aravalli horse trail",
                        "3 hrs",
                        "morning",
                        3800,
                        3000,
                        ["adventure"],
                        "Marwari horses through hill villages.",
                        min_age=12,
                    ),
                    act(
                        "udaipur-dance",
                        "Dharohar folk dance evening",
                        "1 hr",
                        "evening",
                        600,
                        300,
                        ["culture", "family"],
                        "Puppets and folk dance in an old haveli.",
                    ),
                ],
            },
        ],
        "transfers": [
            {
                "id": "raj-arrive",
                "from": "JAI airport",
                "to": "jaipur",
                "mode": "car",
                "duration": "30 min",
                "pricing": "per_vehicle",
                "prices": {"sedan": 1100, "suv": 1600, "van": 2400},
            },
            {
                "id": "raj-jaipur-jodhpur",
                "from": "jaipur",
                "to": "jodhpur",
                "mode": "car",
                "duration": "6 hrs",
                "pricing": "per_vehicle",
                "prices": {"sedan": 6200, "suv": 8200, "van": 11400},
            },
            {
                "id": "raj-jodhpur-udaipur",
                "from": "jodhpur",
                "to": "udaipur",
                "mode": "car",
                "duration": "5 hrs",
                "pricing": "per_vehicle",
                "prices": {"sedan": 5600, "suv": 7400, "van": 10200},
            },
            {
                "id": "raj-jaipur-udaipur",
                "from": "jaipur",
                "to": "udaipur",
                "mode": "car",
                "duration": "7 hrs",
                "pricing": "per_vehicle",
                "prices": {"sedan": 7400, "suv": 9600, "van": 13200},
            },
            {
                "id": "raj-depart",
                "from": "last",
                "to": "UDR airport",
                "mode": "car",
                "duration": "40 min",
                "pricing": "per_vehicle",
                "prices": {"sedan": 1200, "suv": 1700, "van": 2500},
            },
        ],
    },
    {
        "id": "bali",
        "name": "Bali",
        "country": "Indonesia",
        "domestic": False,
        "tagline": "Ubud's rice terraces, then Seminyak's beach",
        "best_months": [4, 5, 6, 7, 8, 9, 10],
        "arrive": "DPS",
        "depart": "DPS",
        "nights": [4, 9],
        "default_nights": 6,
        "hue": "#3a8f7a",
        "splits": {"4": [2, 2], "5": [2, 3], "6": [3, 3], "7": [3, 4], "8": [4, 4], "9": [4, 5]},
        "cities": [
            {
                "id": "ubud",
                "name": "Ubud",
                "blurb": "Jungle valleys and rice terraces, inland",
                "inland": True,
                "hotels": [
                    hotel(
                        "sayan-ridge",
                        "Sayan Ridge Villas",
                        5,
                        "Sayan valley",
                        [
                            ("pool-villa", "Private Pool Villa", 17800),
                            ("river-villa", "River Valley Villa", 22400),
                        ],
                        ["Breakfast", "Floating breakfast once", "Daily afternoon tea"],
                        ["honeymoon", "relaxed"],
                        "Pool villas hanging over the Ayung river gorge.",
                    ),
                    hotel(
                        "terrace-lodge",
                        "Rice Terrace Lodge",
                        4,
                        "Tegallalang",
                        [
                            ("deluxe", "Terrace View Room", 8200),
                            ("family", "Two-bedroom Family Villa", 14600),
                        ],
                        ["Breakfast", "Ubud shuttle"],
                        ["family", "relaxed", "honeymoon"],
                        "Rooms looking straight over the terraces.",
                    ),
                    hotel(
                        "monkey-forest-inn",
                        "Forest Road Guesthouse",
                        3,
                        "Monkey Forest Road",
                        [("standard", "Garden Room", 3900)],
                        ["Breakfast"],
                        ["budget", "adventure", "family"],
                        "Walk to the market, cafés and the forest.",
                    ),
                ],
                "activities": [
                    act(
                        "ubud-batur-trek",
                        "Mount Batur sunrise trek",
                        "8 hrs",
                        "full_day",
                        4800,
                        3600,
                        ["adventure"],
                        "Start at 2 am, coffee on the crater rim at dawn.",
                        min_age=10,
                    ),
                    act(
                        "ubud-rafting",
                        "Ayung river white-water rafting",
                        "4 hrs",
                        "morning",
                        3600,
                        2400,
                        ["adventure", "family"],
                        "Grade 2-3 rapids through the gorge, lunch after.",
                        min_age=7,
                    ),
                    act(
                        "ubud-terraces",
                        "Rice terraces and swing",
                        "3 hrs",
                        "morning",
                        2200,
                        1400,
                        ["family", "honeymoon", "relaxed"],
                        "Tegallalang's terraces, coffee tasting, the jungle swing.",
                    ),
                    act(
                        "ubud-temples",
                        "Water temple and holy spring tour",
                        "5 hrs",
                        "afternoon",
                        2600,
                        1300,
                        ["culture", "family", "relaxed"],
                        "Tirta Empul's spring and the royal palace.",
                    ),
                    act(
                        "ubud-cooking",
                        "Balinese cooking class in a family compound",
                        "4 hrs",
                        "morning",
                        2900,
                        1500,
                        ["culture", "family", "honeymoon"],
                        "Market at dawn, then cook eight dishes.",
                    ),
                    act(
                        "ubud-spa",
                        "Balinese massage and flower bath",
                        "2 hrs",
                        "afternoon",
                        3900,
                        0,
                        ["honeymoon", "relaxed"],
                        "Two hours in a valley spa.",
                        min_age=16,
                    ),
                    act(
                        "ubud-kecak",
                        "Kecak fire dance at sunset",
                        "1.5 hrs",
                        "evening",
                        1300,
                        700,
                        ["culture", "family", "honeymoon"],
                        "Chanting circle and fire, on a cliff temple stage.",
                    ),
                ],
            },
            {
                "id": "seminyak",
                "name": "Seminyak",
                "blurb": "Beach clubs, sunsets and boutique shopping",
                "hotels": [
                    hotel(
                        "seminyak-shore",
                        "Seminyak Shore Resort",
                        5,
                        "Seminyak beachfront",
                        [
                            ("ocean", "Ocean View Room", 14900),
                            ("pool-villa", "Beachfront Pool Villa", 24800),
                        ],
                        ["Breakfast", "Sunset cocktails"],
                        ["beach", "honeymoon", "relaxed", "family"],
                        "On the sand, with three pools and a spa.",
                    ),
                    hotel(
                        "petitenget-villas",
                        "Petitenget Pool Villas",
                        4,
                        "Petitenget",
                        [
                            ("one-bed", "One-bedroom Pool Villa", 11200),
                            ("two-bed", "Two-bedroom Pool Villa", 16900),
                        ],
                        ["Breakfast", "Beach-club shuttle"],
                        ["beach", "honeymoon", "family"],
                        "Walled villas, five minutes' walk to the beach.",
                    ),
                    hotel(
                        "legian-lane",
                        "Legian Lane Hotel",
                        3,
                        "Legian",
                        [("standard", "Superior Room", 4100), ("family", "Family Room", 5900)],
                        ["Breakfast"],
                        ["beach", "budget", "family"],
                        "Ten minutes' walk to Legian beach.",
                    ),
                ],
                "activities": [
                    act(
                        "seminyak-surf",
                        "Beginner surf lesson",
                        "2 hrs",
                        "morning",
                        2700,
                        2200,
                        ["adventure", "family"],
                        "Small waves and a patient coach.",
                        min_age=8,
                    ),
                    act(
                        "seminyak-tanah-lot",
                        "Tanah Lot sunset temple",
                        "4 hrs",
                        "evening",
                        1900,
                        950,
                        ["culture", "honeymoon", "family", "relaxed"],
                        "The sea temple on its rock at sunset.",
                    ),
                    act(
                        "seminyak-nusa-penida",
                        "Nusa Penida island day trip",
                        "Full day",
                        "full_day",
                        6400,
                        4800,
                        ["adventure", "honeymoon", "family"],
                        "Speedboat to Kelingking cliffs and Crystal Bay.",
                        min_age=5,
                    ),
                    act(
                        "seminyak-snorkel",
                        "Blue Lagoon snorkelling",
                        "4 hrs",
                        "morning",
                        3100,
                        2300,
                        ["adventure", "family"],
                        "Reef fish in calm water, gear included.",
                        min_age=6,
                    ),
                    act(
                        "seminyak-dinner-cruise",
                        "Sunset dinner cruise",
                        "3 hrs",
                        "evening",
                        4200,
                        2100,
                        ["honeymoon", "relaxed", "family"],
                        "Dinner and music on Benoa bay.",
                    ),
                ],
            },
        ],
        "transfers": [
            {
                "id": "bali-arrive",
                "from": "DPS airport",
                "to": "first",
                "mode": "car",
                "duration": "1.5 hrs",
                "pricing": "per_vehicle",
                "prices": {"sedan": 2400, "suv": 3200, "van": 4600},
            },
            {
                "id": "bali-ubud-seminyak",
                "from": "ubud",
                "to": "seminyak",
                "mode": "car",
                "duration": "1.5 hrs",
                "pricing": "per_vehicle",
                "prices": {"sedan": 2200, "suv": 3000, "van": 4300},
            },
            {
                "id": "bali-depart",
                "from": "last",
                "to": "DPS airport",
                "mode": "car",
                "duration": "30-90 min",
                "pricing": "per_vehicle",
                "prices": {"sedan": 1600, "suv": 2200, "van": 3200},
            },
        ],
    },
    {
        "id": "dubai",
        "name": "Dubai",
        "country": "United Arab Emirates",
        "domestic": False,
        "tagline": "Desert dunes, the creek souks and skyline views",
        "best_months": [11, 12, 1, 2, 3],
        "arrive": "DXB",
        "depart": "DXB",
        "nights": [3, 7],
        "default_nights": 4,
        "hue": "#c48a3a",
        "splits": {"3": [3], "4": [4], "5": [5], "6": [6], "7": [7]},
        "cities": [
            {
                "id": "dubai",
                "name": "Dubai",
                "blurb": "Marina towers, old creek and the open desert",
                "hotels": [
                    hotel(
                        "marina-sail",
                        "Marina Sail Hotel",
                        5,
                        "Dubai Marina",
                        [
                            ("city", "City View Room", 13600),
                            ("marina", "Marina View Room", 16200),
                            ("family", "Family Suite", 24800),
                        ],
                        ["Breakfast", "Beach-club access"],
                        ["family", "honeymoon", "relaxed", "beach"],
                        "Tower rooms over the marina, a walk to JBR beach.",
                    ),
                    hotel(
                        "creek-heritage",
                        "Al Fahidi Creek Hotel",
                        4,
                        "Al Fahidi, Bur Dubai",
                        [("courtyard", "Courtyard Room", 7900)],
                        ["Breakfast", "Abra ride across the creek"],
                        ["culture", "relaxed"],
                        "Wind-tower rooms in the old quarter.",
                    ),
                    hotel(
                        "palm-lagoon",
                        "Palm Lagoon Resort",
                        5,
                        "Palm Jumeirah",
                        [("lagoon", "Lagoon Room", 19800), ("villa", "Beach Villa", 34000)],
                        ["Breakfast and dinner", "Waterpark passes"],
                        ["beach", "family", "honeymoon"],
                        "Private beach and a lazy river on the Palm.",
                    ),
                    hotel(
                        "deira-city",
                        "Deira City Inn",
                        3,
                        "Deira",
                        [("standard", "Standard Room", 4600), ("family", "Family Room", 6400)],
                        ["Breakfast", "Metro two minutes away"],
                        ["budget", "family"],
                        "Near the gold souk and the metro.",
                    ),
                ],
                "activities": [
                    act(
                        "dubai-desert-safari",
                        "Evening desert safari with dinner",
                        "6 hrs",
                        "evening",
                        4200,
                        3100,
                        ["adventure", "family", "honeymoon"],
                        "Dune drive, camel ride, BBQ and a show.",
                        min_age=3,
                    ),
                    act(
                        "dubai-skyline",
                        "Observation deck at sunset, level 124",
                        "1.5 hrs",
                        "evening",
                        3800,
                        2900,
                        ["family", "honeymoon", "relaxed"],
                        "The city from the top of the tallest tower.",
                    ),
                    act(
                        "dubai-old-dubai",
                        "Old Dubai, abra and souks walk",
                        "3 hrs",
                        "morning",
                        1900,
                        900,
                        ["culture", "family"],
                        "Al Fahidi lanes, the spice and gold souks.",
                    ),
                    act(
                        "dubai-waterpark",
                        "Waterpark day",
                        "Full day",
                        "full_day",
                        6200,
                        5200,
                        ["family", "adventure"],
                        "Slides, lazy river and the wave pool.",
                    ),
                    act(
                        "dubai-dhow-cruise",
                        "Marina dhow dinner cruise",
                        "2 hrs",
                        "evening",
                        3300,
                        2200,
                        ["honeymoon", "relaxed", "family"],
                        "Dinner on a wooden dhow under the towers.",
                    ),
                    act(
                        "dubai-abu-dhabi",
                        "Abu Dhabi day trip: grand mosque and museum",
                        "Full day",
                        "full_day",
                        5600,
                        3800,
                        ["culture", "family"],
                        "The white mosque and the domed museum, with lunch.",
                    ),
                    act(
                        "dubai-skydive-sim",
                        "Indoor skydiving session",
                        "1 hr",
                        "afternoon",
                        5400,
                        5400,
                        ["adventure"],
                        "Two flights in a wind tunnel.",
                        min_age=12,
                    ),
                ],
            }
        ],
        "transfers": [
            {
                "id": "dubai-arrive",
                "from": "DXB airport",
                "to": "dubai",
                "mode": "car",
                "duration": "30 min",
                "pricing": "per_vehicle",
                "prices": {"sedan": 2600, "suv": 3400, "van": 4800},
            },
            {
                "id": "dubai-depart",
                "from": "last",
                "to": "DXB airport",
                "mode": "car",
                "duration": "30 min",
                "pricing": "per_vehicle",
                "prices": {"sedan": 2600, "suv": 3400, "van": 4800},
            },
        ],
    },
    {
        "id": "thailand",
        "name": "Thailand",
        "country": "Thailand",
        "domestic": False,
        "tagline": "Phuket and Krabi's islands, then Bangkok",
        "best_months": [11, 12, 1, 2, 3, 4],
        "arrive": "HKT",
        "depart": "BKK",
        "nights": [4, 9],
        "default_nights": 6,
        "hue": "#d4664a",
        "splits": {
            "4": [2, 0, 2],
            "5": [3, 0, 2],
            "6": [2, 2, 2],
            "7": [3, 2, 2],
            "8": [3, 2, 3],
            "9": [3, 3, 3],
        },
        "cities": [
            {
                "id": "phuket",
                "name": "Phuket",
                "blurb": "Beaches, island hops and Old Town",
                "hotels": [
                    hotel(
                        "kata-cove",
                        "Kata Cove Resort",
                        4,
                        "Kata Beach",
                        [("deluxe", "Deluxe Sea View", 8800), ("family", "Family Room", 12400)],
                        ["Breakfast", "Kids' club"],
                        ["beach", "family", "relaxed"],
                        "On the hill above Kata's bay.",
                    ),
                    hotel(
                        "kamala-pool-villas",
                        "Kamala Pool Villas",
                        5,
                        "Kamala",
                        [("pool-villa", "Ocean Pool Villa", 18600)],
                        ["Breakfast", "Airport transfer"],
                        ["beach", "honeymoon", "relaxed"],
                        "Every villa with its own pool and sea view.",
                    ),
                    hotel(
                        "patong-central",
                        "Patong Central Hotel",
                        3,
                        "Patong",
                        [("standard", "Superior Room", 3900)],
                        ["Breakfast"],
                        ["budget", "adventure", "beach"],
                        "Close to the beach and the night markets.",
                    ),
                ],
                "activities": [
                    act(
                        "phuket-phi-phi",
                        "Phi Phi islands speedboat day",
                        "Full day",
                        "full_day",
                        5600,
                        3900,
                        ["adventure", "family", "honeymoon"],
                        "Maya Bay, snorkelling and lunch on the island.",
                        min_age=4,
                    ),
                    act(
                        "phuket-old-town",
                        "Old Town and Big Buddha tour",
                        "4 hrs",
                        "afternoon",
                        1800,
                        900,
                        ["culture", "family", "relaxed"],
                        "Shophouse streets, then the hilltop Buddha.",
                    ),
                    act(
                        "phuket-elephant",
                        "Ethical elephant sanctuary morning",
                        "4 hrs",
                        "morning",
                        4600,
                        3200,
                        ["family", "culture"],
                        "Feed and walk with rescued elephants, no riding.",
                    ),
                    act(
                        "phuket-fantasea",
                        "Cultural theme-park night show",
                        "4 hrs",
                        "evening",
                        3900,
                        3300,
                        ["family", "culture"],
                        "A big-stage show with dinner.",
                        closed=["Thu"],
                    ),
                    act(
                        "phuket-sunset-sail",
                        "Catamaran sunset sail",
                        "4 hrs",
                        "evening",
                        4400,
                        2800,
                        ["honeymoon", "relaxed"],
                        "Sail out to Promthep cape at sunset.",
                    ),
                ],
            },
            {
                "id": "krabi",
                "name": "Krabi",
                "blurb": "Limestone cliffs and the four islands",
                "hotels": [
                    hotel(
                        "railay-cliff",
                        "Railay Cliff Lodge",
                        4,
                        "Railay",
                        [("garden", "Garden Bungalow", 7600), ("sea", "Sea View Bungalow", 10200)],
                        ["Breakfast", "Longtail boat transfer"],
                        ["beach", "adventure", "honeymoon"],
                        "Bungalows between the cliffs, reached by boat.",
                    ),
                    hotel(
                        "aonang-bay",
                        "Ao Nang Bay Resort",
                        3,
                        "Ao Nang",
                        [("standard", "Superior Room", 4200), ("family", "Family Room", 5800)],
                        ["Breakfast"],
                        ["beach", "family", "budget"],
                        "Across the road from Ao Nang beach.",
                    ),
                ],
                "activities": [
                    act(
                        "krabi-four-islands",
                        "Four islands longtail tour",
                        "Full day",
                        "full_day",
                        3400,
                        2400,
                        ["family", "adventure", "relaxed"],
                        "Poda, Chicken island and Phra Nang cave beach.",
                    ),
                    act(
                        "krabi-climb",
                        "Railay rock-climbing taster",
                        "4 hrs",
                        "morning",
                        3800,
                        3000,
                        ["adventure"],
                        "Your first limestone climb, with a guide.",
                        min_age=10,
                    ),
                    act(
                        "krabi-kayak",
                        "Ao Thalane mangrove kayak",
                        "3 hrs",
                        "afternoon",
                        2100,
                        1400,
                        ["adventure", "family"],
                        "Paddle through limestone channels.",
                        min_age=6,
                    ),
                ],
            },
            {
                "id": "bangkok",
                "name": "Bangkok",
                "blurb": "Temples, river and street food",
                "hotels": [
                    hotel(
                        "riverside-grand",
                        "Chao Phraya Riverside Grand",
                        5,
                        "Riverside",
                        [("river", "River View Room", 10400), ("suite", "River Suite", 16800)],
                        ["Breakfast", "Hotel ferry"],
                        ["honeymoon", "relaxed", "family"],
                        "A tower on the river with its own ferry.",
                    ),
                    hotel(
                        "sukhumvit-urban",
                        "Sukhumvit Urban Hotel",
                        4,
                        "Sukhumvit",
                        [("deluxe", "Deluxe Room", 6200), ("family", "Family Room", 8600)],
                        ["Breakfast", "Skytrain at the door"],
                        ["family", "budget", "adventure"],
                        "Above the skytrain, near the malls.",
                    ),
                ],
                "activities": [
                    act(
                        "bkk-grand-palace",
                        "Grand Palace and Wat Pho",
                        "4 hrs",
                        "morning",
                        2100,
                        1000,
                        ["culture", "family"],
                        "The palace, the reclining Buddha and a river crossing.",
                    ),
                    act(
                        "bkk-floating-market",
                        "Floating market and train market",
                        "6 hrs",
                        "morning",
                        2800,
                        1700,
                        ["culture", "family"],
                        "Boats of fruit, then the market on the railway line.",
                    ),
                    act(
                        "bkk-food-tuk-tuk",
                        "Night food tour by tuk-tuk",
                        "4 hrs",
                        "evening",
                        3200,
                        2000,
                        ["adventure", "culture", "family"],
                        "Eight stops of street food across Chinatown.",
                    ),
                    act(
                        "bkk-dinner-cruise",
                        "River dinner cruise",
                        "2 hrs",
                        "evening",
                        3600,
                        2200,
                        ["honeymoon", "relaxed", "family"],
                        "Buffet dinner past the lit temples.",
                    ),
                ],
            },
        ],
        "transfers": [
            {
                "id": "th-arrive",
                "from": "HKT airport",
                "to": "first",
                "mode": "car",
                "duration": "1 hr",
                "pricing": "per_vehicle",
                "prices": {"sedan": 1900, "suv": 2600, "van": 3700},
            },
            {
                "id": "th-phuket-krabi",
                "from": "phuket",
                "to": "krabi",
                "mode": "ferry",
                "duration": "2 hrs",
                "pricing": "per_person",
                "prices": {"adult": 1600, "child": 900},
            },
            {
                "id": "th-phuket-bangkok",
                "from": "phuket",
                "to": "bangkok",
                "mode": "flight",
                "duration": "1.5 hrs",
                "pricing": "per_person",
                "prices": {"adult": 5400, "child": 4300},
            },
            {
                "id": "th-krabi-bangkok",
                "from": "krabi",
                "to": "bangkok",
                "mode": "flight",
                "duration": "1.5 hrs",
                "pricing": "per_person",
                "prices": {"adult": 5200, "child": 4100},
            },
            {
                "id": "th-depart",
                "from": "last",
                "to": "BKK airport",
                "mode": "car",
                "duration": "45 min",
                "pricing": "per_vehicle",
                "prices": {"sedan": 1800, "suv": 2400, "van": 3400},
            },
        ],
    },
    {
        "id": "singapore",
        "name": "Singapore",
        "country": "Singapore",
        "domestic": False,
        "tagline": "Gardens, Sentosa's beaches and hawker food",
        "best_months": [2, 3, 4, 5, 6, 7, 8, 9],
        "arrive": "SIN",
        "depart": "SIN",
        "nights": [3, 6],
        "default_nights": 4,
        "hue": "#3d6fb0",
        "splits": {"3": [3, 0], "4": [2, 2], "5": [3, 2], "6": [4, 2]},
        "cities": [
            {
                "id": "singapore-city",
                "name": "Singapore city",
                "blurb": "Marina Bay, Chinatown and Little India",
                "hotels": [
                    hotel(
                        "marina-orchid",
                        "Marina Orchid Hotel",
                        5,
                        "Marina Bay",
                        [("bay", "Bay View Room", 19800), ("club", "Club Room", 26400)],
                        ["Breakfast", "Rooftop pool"],
                        ["honeymoon", "family", "relaxed"],
                        "Floor-to-ceiling windows over the bay.",
                    ),
                    hotel(
                        "bugis-loft",
                        "Bugis Loft Hotel",
                        4,
                        "Bugis",
                        [("deluxe", "Deluxe Room", 9600), ("family", "Family Loft", 13800)],
                        ["Breakfast"],
                        ["family", "budget", "culture"],
                        "Between Kampong Glam and the MRT.",
                    ),
                    hotel(
                        "chinatown-shophouse",
                        "Chinatown Shophouse Hotel",
                        3,
                        "Chinatown",
                        [("standard", "Shophouse Room", 6400)],
                        ["Breakfast"],
                        ["budget", "culture"],
                        "Small rooms in a restored shophouse row.",
                    ),
                ],
                "activities": [
                    act(
                        "sg-gardens",
                        "Gardens by the Bay domes and light show",
                        "3 hrs",
                        "evening",
                        2900,
                        1900,
                        ["family", "honeymoon", "relaxed"],
                        "The cloud forest dome, then the supertree lights.",
                    ),
                    act(
                        "sg-night-safari",
                        "Night safari with tram",
                        "4 hrs",
                        "evening",
                        4200,
                        2900,
                        ["family", "adventure"],
                        "Leopards and tapirs after dark.",
                    ),
                    act(
                        "sg-hawker",
                        "Hawker food trail",
                        "3 hrs",
                        "evening",
                        2400,
                        1300,
                        ["culture", "family"],
                        "Chicken rice, laksa and chilli crab with a guide.",
                    ),
                    act(
                        "sg-studios",
                        "Movie theme park day",
                        "Full day",
                        "full_day",
                        6900,
                        5200,
                        ["family", "adventure"],
                        "Rides and shows all day.",
                    ),
                    act(
                        "sg-city-walk",
                        "Chinatown and Little India walk",
                        "3 hrs",
                        "morning",
                        1600,
                        800,
                        ["culture", "family"],
                        "Temples, spice shops and kopi.",
                    ),
                ],
            },
            {
                "id": "sentosa",
                "name": "Sentosa",
                "blurb": "The island of beaches, rides and the aquarium",
                "hotels": [
                    hotel(
                        "siloso-beach",
                        "Siloso Beach Resort",
                        4,
                        "Siloso Beach",
                        [("garden", "Garden Room", 12800), ("family", "Family Room", 17600)],
                        ["Breakfast", "Island shuttle"],
                        ["beach", "family", "relaxed"],
                        "On Sentosa's busiest beach, with a big pool.",
                    ),
                    hotel(
                        "tanjong-villas",
                        "Tanjong Cove Villas",
                        5,
                        "Tanjong Beach",
                        [("villa", "Garden Pool Villa", 28600)],
                        ["Breakfast", "Afternoon tea"],
                        ["beach", "honeymoon"],
                        "Quiet villas by the island's calmest beach.",
                    ),
                ],
                "activities": [
                    act(
                        "sentosa-aquarium",
                        "Aquarium and ocean dome",
                        "3 hrs",
                        "morning",
                        3100,
                        2300,
                        ["family", "relaxed"],
                        "Sharks, rays and a floor-to-ceiling ocean window.",
                    ),
                    act(
                        "sentosa-luge",
                        "Luge and skyline ride",
                        "2 hrs",
                        "afternoon",
                        1900,
                        1500,
                        ["family", "adventure"],
                        "Race downhill, ride back up.",
                        min_age=6,
                    ),
                    act(
                        "sentosa-wings",
                        "Wings of Time night show",
                        "1 hr",
                        "evening",
                        1500,
                        1200,
                        ["family", "honeymoon"],
                        "Water, fire and lasers on the beach.",
                    ),
                ],
            },
        ],
        "transfers": [
            {
                "id": "sg-arrive",
                "from": "SIN airport",
                "to": "first",
                "mode": "car",
                "duration": "30 min",
                "pricing": "per_vehicle",
                "prices": {"sedan": 2900, "suv": 3800, "van": 5200},
            },
            {
                "id": "sg-city-sentosa",
                "from": "singapore-city",
                "to": "sentosa",
                "mode": "car",
                "duration": "20 min",
                "pricing": "per_vehicle",
                "prices": {"sedan": 2200, "suv": 2900, "van": 4000},
            },
            {
                "id": "sg-depart",
                "from": "last",
                "to": "SIN airport",
                "mode": "car",
                "duration": "30 min",
                "pricing": "per_vehicle",
                "prices": {"sedan": 2900, "suv": 3800, "van": 5200},
            },
        ],
    },
    {
        "id": "maldives",
        "name": "Maldives",
        "country": "Maldives",
        "domestic": False,
        "tagline": "Overwater villas on a lagoon of your own",
        "best_months": [11, 12, 1, 2, 3, 4],
        "arrive": "MLE",
        "depart": "MLE",
        "nights": [3, 7],
        "default_nights": 4,
        "hue": "#1f8fa6",
        "splits": {"3": [3], "4": [4], "5": [5], "6": [6], "7": [7]},
        "cities": [
            {
                "id": "maldives-atoll",
                "name": "Maldives resort island",
                "blurb": "One island, one resort, the lagoon all round",
                "hotels": [
                    hotel(
                        "coral-veli",
                        "Coral Veli Island Resort",
                        4,
                        "South Malé atoll, 30 min by speedboat",
                        [
                            ("beach-villa", "Beach Villa", 21800),
                            ("water-villa", "Water Villa", 29600),
                        ],
                        ["Breakfast and dinner", "Speedboat transfer included", "Snorkel gear"],
                        ["beach", "family", "honeymoon", "relaxed"],
                        "A friendly island with a house reef off the beach.",
                    ),
                    hotel(
                        "azure-atoll",
                        "Azure Atoll Resort & Spa",
                        5,
                        "Baa atoll, 40 min by seaplane",
                        [
                            ("overwater", "Overwater Villa", 46800),
                            ("pool-overwater", "Overwater Pool Villa", 61200),
                        ],
                        ["All meals", "Sunset dolphin cruise once"],
                        ["beach", "honeymoon", "relaxed"],
                        "Villas on stilts with a ladder into the lagoon.",
                    ),
                    hotel(
                        "sandbank-retreat",
                        "Sandbank Retreat",
                        3,
                        "Maafushi island, 30 min by ferry",
                        [("standard", "Sea View Room", 7800)],
                        ["Breakfast", "Bikini-beach access"],
                        ["beach", "budget", "adventure"],
                        "A guesthouse on a local island, the cheaper way in.",
                    ),
                ],
                "activities": [
                    act(
                        "mv-snorkel-turtles",
                        "Turtle reef snorkel trip",
                        "3 hrs",
                        "morning",
                        4600,
                        3400,
                        ["adventure", "family", "honeymoon"],
                        "Two reef stops where turtles feed.",
                        min_age=6,
                    ),
                    act(
                        "mv-dive",
                        "Discover scuba dive",
                        "3 hrs",
                        "morning",
                        9800,
                        0,
                        ["adventure", "honeymoon"],
                        "One shallow dive with an instructor.",
                        min_age=12,
                    ),
                    act(
                        "mv-sandbank-picnic",
                        "Private sandbank picnic",
                        "3 hrs",
                        "afternoon",
                        8600,
                        4300,
                        ["honeymoon", "relaxed", "family"],
                        "A strip of sand, a parasol and lunch.",
                    ),
                    act(
                        "mv-dolphin-cruise",
                        "Sunset dolphin cruise",
                        "2 hrs",
                        "evening",
                        3800,
                        1900,
                        ["family", "relaxed", "honeymoon"],
                        "Spinner dolphins at dusk.",
                    ),
                    act(
                        "mv-spa",
                        "Overwater spa ritual",
                        "2 hrs",
                        "afternoon",
                        11200,
                        0,
                        ["honeymoon", "relaxed"],
                        "A treatment room with a glass floor.",
                        min_age=16,
                    ),
                ],
            }
        ],
        "transfers": [
            {
                "id": "mv-arrive",
                "from": "MLE airport",
                "to": "maldives-atoll",
                "mode": "boat_or_seaplane",
                "duration": "30-40 min",
                "pricing": "per_person",
                "prices": {"adult": 0, "child": 0},
                "by_hotel": {
                    "azure-atoll": {"adult": 32000, "child": 16000, "mode": "seaplane"},
                    "coral-veli": {"adult": 0, "child": 0, "mode": "speedboat"},
                    "sandbank-retreat": {
                        "adult": 2400,
                        "child": 1200,
                        "mode": "public ferry and speedboat",
                    },
                },
            },
            {
                "id": "mv-depart",
                "from": "last",
                "to": "MLE airport",
                "mode": "boat_or_seaplane",
                "duration": "30-40 min",
                "pricing": "per_person",
                "prices": {"adult": 0, "child": 0},
                "by_hotel": {
                    "azure-atoll": {"adult": 32000, "child": 16000, "mode": "seaplane"},
                    "coral-veli": {"adult": 0, "child": 0, "mode": "speedboat"},
                    "sandbank-retreat": {
                        "adult": 2400,
                        "child": 1200,
                        "mode": "public ferry and speedboat",
                    },
                },
            },
        ],
    },
    {
        "id": "switzerland",
        "name": "Switzerland",
        "country": "Switzerland",
        "domestic": False,
        "tagline": "Lake Lucerne, then the Jungfrau peaks from Interlaken",
        "best_months": [5, 6, 7, 8, 9, 12, 1],
        "arrive": "ZRH",
        "depart": "ZRH",
        "nights": [5, 9],
        "default_nights": 7,
        "hue": "#b8433b",
        "splits": {"5": [2, 3], "6": [3, 3], "7": [3, 4], "8": [4, 4], "9": [4, 5]},
        "cities": [
            {
                "id": "lucerne",
                "name": "Lucerne",
                "blurb": "The old town, the lake and its mountains",
                "hotels": [
                    hotel(
                        "lakeside-lucerne",
                        "Seeblick Lakeside Hotel",
                        4,
                        "Lakefront promenade",
                        [("lake", "Lake View Room", 24800), ("family", "Family Room", 32400)],
                        ["Breakfast", "City travel card"],
                        ["honeymoon", "family", "relaxed"],
                        "Balconies over the lake, a walk to the old bridge.",
                    ),
                    hotel(
                        "altstadt-inn",
                        "Altstadt Inn",
                        3,
                        "Old Town",
                        [("standard", "Standard Room", 15600)],
                        ["Breakfast"],
                        ["budget", "culture", "family"],
                        "A painted house in the car-free old town.",
                    ),
                ],
                "activities": [
                    act(
                        "lucerne-pilatus",
                        "Mount Pilatus golden round trip",
                        "Full day",
                        "full_day",
                        14600,
                        7300,
                        ["family", "honeymoon", "relaxed"],
                        "Boat, cogwheel railway up, cable car down.",
                    ),
                    act(
                        "lucerne-titlis",
                        "Mount Titlis glacier and rotating cable car",
                        "Full day",
                        "full_day",
                        16800,
                        8400,
                        ["adventure", "family", "honeymoon"],
                        "Snow all year, the cliff walk and the ice cave.",
                    ),
                    act(
                        "lucerne-lake-cruise",
                        "Lake Lucerne cruise",
                        "2 hrs",
                        "afternoon",
                        6200,
                        3100,
                        ["relaxed", "honeymoon", "family"],
                        "Round the lake's bays on a paddle steamer.",
                    ),
                    act(
                        "lucerne-chocolate",
                        "Chocolate-making workshop",
                        "2 hrs",
                        "afternoon",
                        7400,
                        5400,
                        ["family", "culture"],
                        "Make and wrap your own bars.",
                        closed=["Sun"],
                    ),
                ],
            },
            {
                "id": "interlaken",
                "name": "Interlaken",
                "blurb": "Between two lakes, under the Jungfrau",
                "hotels": [
                    hotel(
                        "jungfrau-view",
                        "Jungfrau View Hotel",
                        4,
                        "Höheweg",
                        [
                            ("mountain", "Mountain View Room", 22600),
                            ("suite", "Junior Suite", 30800),
                        ],
                        ["Breakfast", "Regional travel card"],
                        ["honeymoon", "family", "relaxed"],
                        "Rooms facing the Jungfrau across the meadow.",
                    ),
                    hotel(
                        "chalet-brienz",
                        "Chalet am See",
                        3,
                        "Bönigen, Lake Brienz",
                        [("standard", "Chalet Room", 13800), ("family", "Family Apartment", 19600)],
                        ["Breakfast", "Kitchenette"],
                        ["family", "budget", "relaxed"],
                        "A wooden chalet by the lake, five minutes by bus.",
                    ),
                    hotel(
                        "grindelwald-lodge",
                        "Eiger Base Lodge",
                        4,
                        "Grindelwald",
                        [("alpine", "Alpine Room", 21400)],
                        ["Breakfast and dinner"],
                        ["adventure", "honeymoon"],
                        "Up the valley under the Eiger's north face.",
                    ),
                ],
                "activities": [
                    act(
                        "ilk-jungfraujoch",
                        "Jungfraujoch, Top of Europe",
                        "Full day",
                        "full_day",
                        22800,
                        11400,
                        ["family", "honeymoon", "adventure"],
                        "The railway to 3,454 m, the ice palace and the glacier.",
                    ),
                    act(
                        "ilk-paraglide",
                        "Tandem paraglide over Interlaken",
                        "2 hrs",
                        "morning",
                        17600,
                        0,
                        ["adventure", "honeymoon"],
                        "Fly from Beatenberg down to the meadow.",
                        min_age=14,
                    ),
                    act(
                        "ilk-first",
                        "Grindelwald First cliff walk and trottibike",
                        "Full day",
                        "full_day",
                        9800,
                        4900,
                        ["adventure", "family"],
                        "The cliff walk, then scooters down the mountain.",
                        min_age=8,
                    ),
                    act(
                        "ilk-brienz-boat",
                        "Lake Brienz boat to Giessbach falls",
                        "3 hrs",
                        "afternoon",
                        5600,
                        2800,
                        ["relaxed", "honeymoon", "family"],
                        "Turquoise water and a waterfall hotel's terrace.",
                    ),
                    act(
                        "ilk-fondue",
                        "Swiss fondue evening",
                        "2 hrs",
                        "evening",
                        5200,
                        2600,
                        ["culture", "family", "honeymoon"],
                        "Cheese fondue and alphorn music.",
                    ),
                ],
            },
        ],
        "transfers": [
            {
                "id": "ch-arrive",
                "from": "ZRH airport",
                "to": "lucerne",
                "mode": "train",
                "duration": "1 hr 10 min",
                "pricing": "per_person",
                "prices": {"adult": 4600, "child": 0},
            },
            {
                "id": "ch-lucerne-interlaken",
                "from": "lucerne",
                "to": "interlaken",
                "mode": "train",
                "duration": "2 hrs, scenic line",
                "pricing": "per_person",
                "prices": {"adult": 3900, "child": 0},
            },
            {
                "id": "ch-depart",
                "from": "last",
                "to": "ZRH airport",
                "mode": "train",
                "duration": "2 hrs 15 min",
                "pricing": "per_person",
                "prices": {"adult": 6400, "child": 0},
            },
        ],
    },
]

#: International destinations' hubs for a connection when no nonstop is sold,
#: in the order tried.
HUBS = ["DEL", "BOM"]


def _seed(*parts: str) -> int:
    return int(hashlib.sha256("|".join(parts).encode()).hexdigest()[:8], 16)


def _clock(minutes: int) -> str:
    m = minutes % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def _leg(frm: str, to: str, t: int, minutes: int, airline: str, number: int) -> dict[str, Any]:
    """One leg leaving at ``t``, minutes on IST from midnight of the journey's
    first day; times are shown in each airport's own clock, with the day (0 =
    the day the journey starts, in that clock) beside them."""
    dep_local = t + AIRPORTS[frm]["offset"]
    arr_local = t + minutes + AIRPORTS[to]["offset"]
    return {
        "from": frm,
        "to": to,
        "depart": _clock(dep_local),
        "depart_day": dep_local // (24 * 60),
        "arrive": _clock(arr_local),
        "arrive_day": arr_local // (24 * 60),
        "minutes": minutes,
        "airline": airline,
        "number": f"{AIRLINES[airline]['name'].split()[0]} {number}",
    }


def _route(frm: str, to: str) -> list[tuple[str, str, int]] | None:
    """The legs (from, to, minutes) of the shortest way from ``frm`` to ``to``."""
    if (frm, to) in NONSTOP:
        return [(frm, to, NONSTOP[(frm, to)])]
    if (to, frm) in NONSTOP:
        return [(frm, to, NONSTOP[(to, frm)])]
    best: list[tuple[str, str, int]] | None = None
    for hub in [*HUBS, "SIN"]:
        if hub in (frm, to):
            continue
        a = NONSTOP.get((frm, hub)) or NONSTOP.get((hub, frm))
        b = NONSTOP.get((hub, to)) or NONSTOP.get((to, hub))
        if a and b and (best is None or a + b < sum(m for *_, m in best)):
            best = [(frm, hub, a), (hub, to, b)]
    if best is None and frm not in HUBS:
        # Two connections: into an Indian hub first (Ahmedabad to Bali).
        for hub in HUBS:
            a = NONSTOP.get((frm, hub)) or NONSTOP.get((hub, frm))
            rest = _route(hub, to) if a else None
            if a and rest and len(rest) == 2:
                return [(frm, hub, a), *rest]
    if best is None and to not in HUBS:
        for hub in HUBS:
            b = NONSTOP.get((hub, to)) or NONSTOP.get((to, hub))
            first = _route(frm, hub) if b else None
            if b and first and len(first) == 2:
                return [*first, (hub, to, b)]
    return best


def _journey(
    legs_spec: list[tuple[str, str, int]], dep: int, airline: str, seed: int
) -> dict[str, Any]:
    """``dep`` is the local departure clock at the first airport."""
    legs = []
    layover = 95 + (seed % 4) * 25
    t = dep - AIRPORTS[legs_spec[0][0]]["offset"]
    for i, (a, b, minutes) in enumerate(legs_spec):
        legs.append(_leg(a, b, t, minutes, airline, 100 + (seed + i * 37) % 800))
        t = t + minutes + layover
    total = sum(m for *_, m in legs_spec) + (len(legs_spec) - 1) * layover
    return {
        "legs": legs,
        "minutes": total,
        "stops": len(legs_spec) - 1,
        "arrive_day": legs[-1]["arrive_day"],
    }


def _fare(minutes: int, domestic: bool, kind: str, stops: int) -> int:
    base = (
        2600 + 26 * minutes if domestic else 9000 + 52 * minutes + (16000 if minutes > 420 else 0)
    )
    if kind == "full-service":
        base *= 1.16
    else:
        base *= 0.93
    if stops:
        base *= 0.88
    return int(round(base / 10.0) * 10)


def flights_for(origin: str, dest: dict[str, Any]) -> list[dict[str, Any]]:
    out_route = _route(origin, dest["arrive"])
    back_route = _route(dest["depart"], origin)
    if out_route is None or back_route is None:
        return []
    domestic = bool(dest["domestic"])
    nonstop = len(out_route) == 1 and len(back_route) == 1
    if dest["id"] == "switzerland":
        plans = (
            [("alpenstar", 0), ("kestrel", 1)] if nonstop else [("kestrel", 1), ("alpenstar", 1)]
        )
    elif domestic:
        plans = (
            [("banyan", 0), ("saffron", 0), ("monsoon", 1)]
            if nonstop
            else [("saffron", 1), ("banyan", 1)]
        )
    else:
        plans = (
            [("banyan", 0), ("lagoon", 0), ("kestrel", 1)]
            if nonstop
            else [("kestrel", 1), ("lagoon", 1)]
        )
    departures = [6 * 60 + 10, 18 * 60 + 45, 10 * 60 + 25]
    options = []
    for i, (airline, connecting) in enumerate(plans):
        seed = _seed(origin, dest["id"], str(i))
        out_spec = out_route
        back_spec = back_route
        if connecting and len(out_spec) == 1:
            # A cheaper one-stop through a hub, when the nonstop exists too.
            hub = next(
                (
                    h
                    for h in HUBS
                    if h not in (origin, dest["arrive"])
                    and _route(origin, h)
                    and _route(h, dest["arrive"])
                ),
                None,
            )
            if hub is None:
                continue
            out_spec = [*_route(origin, hub), *_route(hub, dest["arrive"])]  # type: ignore[misc]
            back_spec = [*_route(dest["depart"], hub), *_route(hub, origin)]  # type: ignore[misc]
        dep = departures[i % len(departures)] + (seed % 7) * 5
        back_dep = [14 * 60 + 20, 21 * 60 + 35, 9 * 60 + 5][i % 3] + (seed % 5) * 5
        out = _journey(out_spec, dep, airline, seed)
        back = _journey(back_spec, back_dep, airline, seed + 11)
        kind = AIRLINES[airline]["kind"]
        stops = max(out["stops"], back["stops"])
        fare = _fare((out["minutes"] + back["minutes"]) // 2, domestic, kind, stops)
        options.append(
            {
                "id": f"{origin}-{dest['id']}-{len(options) + 1}",
                "origin": origin,
                "destination": dest["id"],
                "airline": airline,
                "airline_name": AIRLINES[airline]["name"],
                "kind": kind,
                "baggage": AIRLINES[airline]["baggage" if domestic else "intl_baggage"],
                "meal": AIRLINES[airline]["meal"],
                "out": out,
                "back": back,
                "stops": stops,
                "fare_adult": fare,
            }
        )
    return options


def build() -> dict[str, Any]:
    flights = [f for o in ORIGINS for d in DESTINATIONS for f in flights_for(o["id"], d)]
    for d in DESTINATIONS:
        lo, hi = d["nights"]
        assert set(d["splits"]) == {str(n) for n in range(lo, hi + 1)}, d["id"]
        for n, split in d["splits"].items():
            assert sum(split) == int(n), (d["id"], n)
            assert len(split) == len(d["cities"]), (d["id"], n)
        for o in ORIGINS:
            assert [f for f in flights if f["origin"] == o["id"] and f["destination"] == d["id"]], (
                o,
                d["id"],
            )
    return {
        "brand": "Wanderloom Holidays",
        "fictional": True,
        "note": "Every airline, hotel, experience and price here is invented for a demo.",
        "currency": "INR",
        "rules": {
            "child_max_age": 11,
            "infant_max_age": 1,
            "child_fare_pct": 75,
            "infant_fare": 3500,
            "adults_per_room": 2,
            "gst_pct": 5,
            "gst_on": "land",
            "season": {"12": 118, "1": 108, "5": 110, "6": 110, "10": 104},
            "vehicles": [["sedan", 3], ["suv", 6], ["van", 12]],
            "min_days_ahead": 7,
            "max_travellers": 9,
            "month_default_day": "first Friday on or after the 10th",
        },
        "styles": [
            {"id": "relaxed", "label": "Relaxed"},
            {"id": "adventure", "label": "Adventure"},
            {"id": "honeymoon", "label": "Honeymoon"},
            {"id": "family", "label": "Family"},
        ],
        "origins": ORIGINS,
        "airports": AIRPORTS,
        "airlines": AIRLINES,
        "destinations": DESTINATIONS,
        "flights": flights,
    }


def main() -> None:
    OUT.write_text(json.dumps(build(), ensure_ascii=False, indent=1) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
