"""Write ``hotel.json``: everything Hotel Belmonte's guest app and its concierge know.

Hotel Belmonte, Halcyon Bay, California, is invented, and so is every name,
menu, price, slot and policy here. The app (``frontend/src/data.ts``) and the
brain (``backend/hotel.py``) both read the generated file; the concierge states
only what is in it. Deterministic: the same file every run.

Run from ``demos/``: ``uv run python belmonte/data/build_data.py``
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

OUT = Path(__file__).resolve().parent / "hotel.json"

# ─── The demo's two scenarios ────────────────────────────────────────────────
# One guest, one reservation number; the demo opens on the day of arrival, or
# on the last morning of a stay (check-out). The frame's switch picks one.
SCENARIOS: dict[str, Any] = {
    "arrival": {
        "label": "Arriving today",
        "today": "2026-11-25",
        "now": "14:40",
        "arrive": "2026-11-25",
        "depart": "2026-11-28",
        "checked_in": False,
        "room": None,
        "folio": [
            {
                "id": "deposit",
                "date": "2026-11-02",
                "category": "payment",
                "label": "Advance deposit, Visa ending 4417",
                "amount": -389.00,
                "detail": "One night's deposit taken when the reservation was made on Mon, Nov 2.",
            }
        ],
    },
    "departure": {
        "label": "Check-out day",
        "today": "2026-11-25",
        "now": "08:15",
        "arrive": "2026-11-22",
        "depart": "2026-11-25",
        "checked_in": True,
        "room": "1412",
        "folio": [
            {
                "id": "deposit",
                "date": "2026-11-02",
                "category": "payment",
                "label": "Advance deposit, Visa ending 4417",
                "amount": -389.00,
                "detail": "One night's deposit taken when the reservation was made on Mon, Nov 2.",
            },
            {
                "id": "dinner-1122",
                "date": "2026-11-22",
                "category": "dining",
                "label": "Tidewater, dinner for two",
                "amount": 142.60,
                "detail": "Grilled halibut, short rib, a bottle of Halcyon Bay Pinot Noir and one shared dessert, at 7:48 PM. Includes 8.75% sales tax; the tip was added on the check.",
            },
            {
                "id": "spa-1123",
                "date": "2026-11-23",
                "category": "spa",
                "label": "Salt & Cypress Spa, deep tissue massage, 80 min",
                "amount": 306.00,
                "detail": "Deep tissue massage, 80 minutes, with Marcus at 10:00 AM: $255.00 plus the 20% spa service charge of $51.00.",
            },
            {
                "id": "poolbar-1123",
                "date": "2026-11-23",
                "category": "bar",
                "label": "Driftwood Pool Bar",
                "amount": 46.00,
                "detail": "Two Halcyon Spritz and one order of fish tacos at cabana 6, at 1:20 PM, including tax.",
            },
            {
                "id": "ird-1124",
                "date": "2026-11-24",
                "category": "dining",
                "label": "In-room dining, breakfast",
                "amount": 68.40,
                "detail": "Two Belmonte breakfasts delivered at 8:05 AM: $46.00, the 20% service charge of $9.20, the $5.00 delivery fee and sales tax.",
            },
            {
                "id": "minibar-1124",
                "date": "2026-11-24",
                "category": "minibar",
                "label": "Minibar",
                "amount": 24.00,
                "detail": "Two sparkling waters ($7.00 each) and one tin of macadamia nuts ($10.00), recorded by housekeeping at 4:30 PM.",
            },
        ],
    },
}


def _nights(dates: list[str]) -> list[dict[str, Any]]:
    """The room, resort fee, tax and valet posted each night of a stay."""
    out: list[dict[str, Any]] = []
    for d in dates:
        tag = d[5:].replace("-", "")
        tax = round((389.00 + 35.00) * 0.135 + 1e-9, 2)
        out += [
            {
                "id": f"room-{tag}",
                "date": d,
                "category": "room",
                "label": "Deluxe King, Ocean View",
                "amount": 389.00,
                "detail": "The nightly room rate for your reservation, Belmonte Circle rate.",
            },
            {
                "id": f"resort-{tag}",
                "date": d,
                "category": "fee",
                "label": "Resort fee",
                "amount": 35.00,
                "detail": "Daily resort fee: Wi-Fi, pool cabana towels, fitness classes, the house car and bikes.",
            },
            {
                "id": f"tax-{tag}",
                "date": d,
                "category": "tax",
                "label": "Room and occupancy tax, 13.5%",
                "amount": tax,
                "detail": "13.5% on the room rate and resort fee.",
            },
            {
                "id": f"valet-{tag}",
                "date": d,
                "category": "parking",
                "label": "Valet parking",
                "amount": 52.00,
                "detail": "Valet parking, $52 a night.",
            },
        ]
    return out


SCENARIOS["departure"]["folio"] += _nights(["2026-11-22", "2026-11-23", "2026-11-24"])
SCENARIOS["departure"]["folio"].sort(key=lambda line: (line["date"], line["category"] != "room"))

GUEST = {
    "first_name": "Maya",
    "last_name": "Thompson",
    "companions": ["Jordan Thompson"],
    "email": "maya.t@example.com",
    "phone": "(415) 555-0186",
    "member": "Belmonte Circle Gold",
    "card": "Visa ending 4417",
    "reservation": "BLM-48213",
    "room_type": "Deluxe King, Ocean View",
    "adults": 2,
    "rate": 389.00,
}

HOTEL = {
    "name": "Hotel Belmonte",
    "place": "Halcyon Bay, California",
    "address": "1200 Cliffside Drive, Halcyon Bay, California",
    "phone": "(805) 555-0140",
    "weather": {"temp_f": 68, "summary": "Sunny, light breeze off the bay", "sunset": "4:52 PM"},
    "check_in_time": "4:00 PM",
    "check_out_time": "11:00 AM",
    "resort_fee": 35.00,
    "room_tax_pct": 13.5,
    "sales_tax_pct": 8.75,
}

# ─── Check-in ────────────────────────────────────────────────────────────────
CHECKIN = {
    "arrival_times": [
        {"id": "now", "label": "I'm here now"},
        {"id": "15:00", "label": "3:00 PM"},
        {"id": "16:00", "label": "4:00 PM"},
        {"id": "17:00", "label": "5:00 to 7:00 PM"},
        {"id": "19:00", "label": "After 7:00 PM"},
    ],
    "floors": [
        {"id": "high", "label": "Higher floor (10 to 14)"},
        {"id": "low", "label": "Lower floor (2 to 6)"},
        {"id": "any", "label": "No preference"},
    ],
    "beds": [{"id": "king", "label": "One king"}, {"id": "queens", "label": "Two queens"}],
    "early": {
        "fee": 40.00,
        "before": "16:00",
        "rule": "Arriving before 4:00 PM, a room that is already clean can be yours now for a $40 early check-in fee. Otherwise it is ready by 4:00 PM at no charge.",
    },
    # Rooms of the reserved type the front office can give today, best first.
    # The app assigns the first that fits the guest's preferences.
    "rooms": [
        {
            "room": "1412",
            "floor": 14,
            "bed": "king",
            "quiet": True,
            "ready": "now",
            "note": "Corner room, end of the hall, ocean view",
        },
        {
            "room": "1108",
            "floor": 11,
            "bed": "king",
            "quiet": False,
            "ready": "15:30",
            "note": "Ocean view, near the elevators",
        },
        {
            "room": "0516",
            "floor": 5,
            "bed": "king",
            "quiet": True,
            "ready": "now",
            "note": "Ocean view over the gardens",
        },
        {
            "room": "0921",
            "floor": 9,
            "bed": "queens",
            "quiet": True,
            "ready": "16:00",
            "note": "Two queens, partial ocean view",
        },
        {
            "room": "0304",
            "floor": 3,
            "bed": "queens",
            "quiet": False,
            "ready": "now",
            "note": "Two queens, garden side",
        },
    ],
    "wifi": {"network": "Belmonte-Guest", "password": "saltcypress"},
}

LATE_CHECKOUT = {
    "standard": "11:00",
    "options": [
        {
            "id": "12:00",
            "label": "12:00 PM",
            "fee": 0.0,
            "available": True,
            "note": "Complimentary for Belmonte Circle Gold",
        },
        {"id": "13:00", "label": "1:00 PM", "fee": 40.0, "available": True, "note": None},
        {"id": "14:00", "label": "2:00 PM", "fee": 60.0, "available": True, "note": None},
        {
            "id": "16:00",
            "label": "4:00 PM",
            "fee": 95.0,
            "available": False,
            "note": "Fully booked for this date",
        },
    ],
    "rule": "Late check-out is confirmed by the front desk within about 15 minutes. Fees go on the room bill.",
}

DISPUTE_RULE = "A charge you question is held off the balance and reviewed by the front office within 24 hours; they reply in the app."


# ─── In-room dining and bars ─────────────────────────────────────────────────
def item(
    id: str,
    name: str,
    price: float,
    desc: str,
    *,
    allergens: tuple[str, ...] = (),
    diet: tuple[str, ...] = (),
    options: tuple[str, ...] = (),
    abv: bool = False,
    glass: float | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": id,
        "name": name,
        "price": price,
        "desc": desc,
        "allergens": list(allergens),
        "diet": list(diet),
        "options": list(options),
    }
    if abv:
        out["alcohol"] = True
    if glass is not None:
        out["bottle"] = price
        out["price"] = glass
    return out


# Option groups: `pick` = choose exactly one (the first is the default only
# once the guest has said nothing about it, and the app asks); `add` = any.
OPTION_GROUPS: dict[str, dict[str, Any]] = {
    "eggs": {
        "label": "Eggs",
        "pick": True,
        "choices": [
            ["scrambled", "Scrambled", 0],
            ["fried", "Fried", 0],
            ["poached", "Poached", 0],
            ["whites", "Egg whites", 2],
        ],
    },
    "toast": {
        "label": "Toast",
        "pick": True,
        "choices": [
            ["sourdough", "Sourdough", 0],
            ["wheat", "Whole wheat", 0],
            ["gf", "Gluten-free bread", 2],
        ],
    },
    "breakfast_side": {
        "label": "Side",
        "pick": True,
        "choices": [
            ["potatoes", "Breakfast potatoes", 0],
            ["fruit", "Fresh fruit", 0],
            ["bacon", "Applewood bacon", 0],
            ["sausage", "Chicken sausage", 0],
        ],
    },
    "side": {
        "label": "Side",
        "pick": True,
        "choices": [
            ["fries", "Fries", 0],
            ["salad", "Side salad", 0],
            ["sweet_fries", "Sweet potato fries", 2],
        ],
    },
    "burger_cook": {
        "label": "Cooked",
        "pick": True,
        "choices": [
            ["medium_rare", "Medium rare", 0],
            ["medium", "Medium", 0],
            ["well", "Well done", 0],
        ],
    },
    "burger_mods": {
        "label": "Changes",
        "pick": False,
        "choices": [
            ["no_onions", "No onions", 0],
            ["no_cheese", "No cheese", 0],
            ["gf_bun", "Gluten-free bun", 3],
            ["add_bacon", "Add bacon", 3],
            ["add_avocado", "Add avocado", 3],
        ],
    },
    "salad_protein": {
        "label": "Add protein",
        "pick": False,
        "choices": [
            ["chicken", "Grilled chicken", 8],
            ["shrimp", "Shrimp", 10],
            ["salmon", "Salmon", 12],
        ],
    },
    "salad_mods": {
        "label": "Changes",
        "pick": False,
        "choices": [
            ["no_onions", "No onions", 0],
            ["dressing_side", "Dressing on the side", 0],
            ["no_croutons", "No croutons", 0],
        ],
    },
    "pizza_mods": {
        "label": "Changes",
        "pick": False,
        "choices": [
            ["gf_crust", "Gluten-free crust", 4],
            ["no_onions", "No onions", 0],
            ["add_chili", "Add Calabrian chili", 0],
        ],
    },
    "steak_cook": {
        "label": "Cooked",
        "pick": True,
        "choices": [
            ["rare", "Rare", 0],
            ["medium_rare", "Medium rare", 0],
            ["medium", "Medium", 0],
            ["well", "Well done", 0],
        ],
    },
    "milk": {
        "label": "Milk",
        "pick": True,
        "choices": [
            ["whole", "Whole milk", 0],
            ["oat", "Oat milk", 1],
            ["almond", "Almond milk", 1],
        ],
    },
    "taco_mods": {
        "label": "Changes",
        "pick": False,
        "choices": [
            ["no_onions", "No onions", 0],
            ["corn", "Corn tortillas (gluten-free)", 0],
            ["no_cilantro", "No cilantro", 0],
        ],
    },
    "cocktail_mods": {
        "label": "Changes",
        "pick": False,
        "choices": [
            ["less_sweet", "Less sweet", 0],
            ["no_salt", "No salt rim", 0],
            ["double", "Make it a double", 7],
        ],
    },
}

DINING = {
    "outlet": "In-room dining",
    "service_charge_pct": 20.0,
    "delivery_fee": 5.00,
    "tips": [0, 10, 15, 20],
    "policy": "A 20% service charge and a $5.00 delivery fee are added to every in-room dining order; the service charge goes to the in-room dining team. An extra tip is up to you. Sales tax is 8.75%.",
    "periods": [
        {
            "id": "breakfast",
            "label": "Breakfast",
            "hours": "6:30 to 11:00 AM",
            "from": "06:30",
            "to": "11:00",
            "eta": "25 to 35 minutes",
            "items": [
                item(
                    "belmonte-breakfast",
                    "Belmonte breakfast",
                    23.00,
                    "Two eggs your way, a side, toast and coffee or juice.",
                    allergens=("egg", "gluten", "dairy"),
                    options=("eggs", "breakfast_side", "toast"),
                ),
                item(
                    "avocado-toast",
                    "Avocado toast",
                    18.00,
                    "Smashed avocado on sourdough, chili crisp, soft egg, pea shoots.",
                    allergens=("egg", "gluten", "sesame"),
                    diet=("vegetarian",),
                    options=("toast",),
                ),
                item(
                    "buttermilk-pancakes",
                    "Buttermilk pancakes",
                    17.00,
                    "Three pancakes, Meyer lemon butter, maple syrup, berries.",
                    allergens=("gluten", "dairy", "egg"),
                    diet=("vegetarian",),
                ),
                item(
                    "smoked-salmon-bagel",
                    "Smoked salmon bagel",
                    21.00,
                    "Everything bagel, smoked salmon, dill cream cheese, capers, red onion.",
                    allergens=("fish", "gluten", "dairy", "sesame"),
                ),
                item(
                    "acai-bowl",
                    "Açaí bowl",
                    15.00,
                    "Açaí, banana, granola, coconut, honey.",
                    allergens=("tree nuts",),
                    diet=("vegetarian", "gluten-free"),
                ),
                item(
                    "steel-cut-oats",
                    "Steel-cut oatmeal",
                    12.00,
                    "Brown sugar, golden raisins, toasted walnuts.",
                    allergens=("tree nuts",),
                    diet=("vegan",),
                    options=("milk",),
                ),
                item(
                    "latte",
                    "Latte",
                    6.50,
                    "Double shot, steamed milk.",
                    allergens=("dairy",),
                    diet=("vegetarian", "gluten-free"),
                    options=("milk",),
                ),
                item(
                    "fresh-oj",
                    "Fresh orange juice",
                    8.00,
                    "Squeezed to order, 12 oz.",
                    diet=("vegan", "gluten-free"),
                ),
            ],
        },
        {
            "id": "all_day",
            "label": "All day",
            "hours": "11:00 AM to 10:00 PM",
            "from": "11:00",
            "to": "22:00",
            "eta": "30 to 40 minutes",
            "items": [
                item(
                    "belmonte-burger",
                    "Belmonte burger",
                    26.00,
                    "Dry-aged beef, white cheddar, caramelized onions, house pickles, brioche bun, with a side.",
                    allergens=("gluten", "dairy", "egg"),
                    options=("burger_cook", "side", "burger_mods"),
                ),
                item(
                    "baja-fish-tacos",
                    "Baja fish tacos",
                    22.00,
                    "Three tacos, beer-battered rockfish, cabbage slaw, chipotle crema, lime.",
                    allergens=("fish", "gluten", "dairy"),
                    options=("taco_mods",),
                ),
                item(
                    "cobb-salad",
                    "Cliffside Cobb salad",
                    21.00,
                    "Romaine, avocado, egg, bacon, blue cheese, tomato, red onion, buttermilk dressing.",
                    allergens=("egg", "dairy"),
                    diet=("gluten-free",),
                    options=("salad_protein", "salad_mods"),
                ),
                item(
                    "kale-caesar",
                    "Kale Caesar",
                    18.00,
                    "Tuscan kale, parmesan, sourdough croutons, lemon-anchovy dressing.",
                    allergens=("fish", "dairy", "gluten", "egg"),
                    options=("salad_protein", "salad_mods"),
                ),
                item(
                    "margherita-pizza",
                    "Margherita pizza",
                    20.00,
                    "San Marzano tomato, fresh mozzarella, basil, 12 inch.",
                    allergens=("gluten", "dairy"),
                    diet=("vegetarian",),
                    options=("pizza_mods",),
                ),
                item(
                    "clam-chowder",
                    "New England clam chowder",
                    14.00,
                    "Littleneck clams, potato, bacon, oyster crackers.",
                    allergens=("shellfish", "dairy", "gluten"),
                ),
                item(
                    "grilled-salmon",
                    "Grilled king salmon",
                    38.00,
                    "Lemon beurre blanc, farro, charred broccolini.",
                    allergens=("fish", "dairy", "gluten"),
                ),
                item(
                    "ny-strip",
                    "New York strip, 12 oz",
                    52.00,
                    "Peppercorn butter, crispy potatoes, grilled asparagus.",
                    allergens=("dairy",),
                    diet=("gluten-free",),
                    options=("steak_cook",),
                ),
                item(
                    "veggie-bowl",
                    "Garden grain bowl",
                    19.00,
                    "Quinoa, roasted squash, chickpeas, avocado, tahini-lemon dressing.",
                    allergens=("sesame",),
                    diet=("vegan", "gluten-free"),
                ),
                item(
                    "kids-chicken",
                    "Kids chicken tenders",
                    13.00,
                    "With fries and ketchup. For guests 12 and under.",
                    allergens=("gluten", "egg"),
                    options=("side",),
                ),
                item(
                    "chocolate-cake",
                    "Dark chocolate cake",
                    13.00,
                    "Salted caramel, whipped cream.",
                    allergens=("gluten", "dairy", "egg"),
                    diet=("vegetarian",),
                ),
                item(
                    "sparkling-water",
                    "Sparkling water, 750 ml",
                    9.00,
                    "Chilled.",
                    diet=("vegan", "gluten-free"),
                ),
            ],
        },
        {
            "id": "late_night",
            "label": "Late night",
            "hours": "10:00 PM to 6:30 AM",
            "from": "22:00",
            "to": "06:30",
            "eta": "35 to 45 minutes",
            "items": [
                item(
                    "late-burger",
                    "Belmonte burger",
                    26.00,
                    "Dry-aged beef, white cheddar, caramelized onions, brioche bun, with fries.",
                    allergens=("gluten", "dairy", "egg"),
                    options=("burger_cook", "burger_mods"),
                ),
                item(
                    "late-quesadilla",
                    "Chicken quesadilla",
                    17.00,
                    "Jack cheese, pico de gallo, sour cream.",
                    allergens=("gluten", "dairy"),
                ),
                item(
                    "late-pizza",
                    "Margherita pizza",
                    20.00,
                    "San Marzano tomato, fresh mozzarella, basil.",
                    allergens=("gluten", "dairy"),
                    diet=("vegetarian",),
                    options=("pizza_mods",),
                ),
                item(
                    "late-cookies",
                    "Warm cookies and milk",
                    10.00,
                    "Three chocolate chip cookies, a glass of cold milk.",
                    allergens=("gluten", "dairy", "egg"),
                    diet=("vegetarian",),
                ),
            ],
        },
    ],
}

BAR = {
    "service_charge_pct": 20.0,
    "delivery_fee": 0.0,
    "tips": [0, 10, 15, 20],
    "age_rule": "Alcohol is served to guests 21 and over. Please have a photo ID ready; it is checked when the drinks arrive.",
    "policy": "A 20% service charge is added to drinks delivered to your room or cabana. An extra tip is up to you. Sales tax is 8.75%.",
    "deliver_to": [
        {"id": "room", "label": "My room"},
        {"id": "cabana", "label": "Pool cabana"},
    ],
    "cabanas": ["1", "2", "3", "4", "5", "6", "7", "8"],
    "eta": "15 to 20 minutes",
    "bars": [
        {
            "id": "pool",
            "name": "Driftwood Pool Bar",
            "hours": "11:00 AM to 6:00 PM",
            "from": "11:00",
            "to": "18:00",
        },
        {
            "id": "lobby",
            "name": "The Compass Room",
            "hours": "4:00 PM to midnight",
            "from": "16:00",
            "to": "24:00",
        },
    ],
    "sections": [
        {
            "id": "cocktails",
            "label": "Cocktails",
            "items": [
                item(
                    "halcyon-spritz",
                    "Halcyon Spritz",
                    16.00,
                    "Blood orange aperitivo, sparkling wine, soda.",
                    abv=True,
                    options=("cocktail_mods",),
                ),
                item(
                    "cliffside-margarita",
                    "Cliffside margarita",
                    17.00,
                    "Blanco tequila, lime, agave, salt rim.",
                    abv=True,
                    options=("cocktail_mods",),
                ),
                item(
                    "cypress-old-fashioned",
                    "Cypress old fashioned",
                    19.00,
                    "Rye, smoked cypress syrup, orange bitters.",
                    abv=True,
                    options=("cocktail_mods",),
                ),
                item(
                    "bay-mule",
                    "Bay mule",
                    16.00,
                    "Vodka, ginger beer, lime, mint.",
                    abv=True,
                    options=("cocktail_mods",),
                ),
                item(
                    "espresso-martini",
                    "Espresso martini",
                    18.00,
                    "Vodka, cold brew, coffee liqueur.",
                    abv=True,
                    options=("cocktail_mods",),
                ),
            ],
        },
        {
            "id": "beer",
            "label": "Beer",
            "items": [
                item(
                    "tide-pool-ipa",
                    "Tide Pool IPA",
                    10.00,
                    "Local West Coast IPA, 16 oz can.",
                    allergens=("gluten",),
                    abv=True,
                ),
                item(
                    "harbor-lager",
                    "Harbor lager",
                    9.00,
                    "Crisp pilsner, 12 oz bottle.",
                    allergens=("gluten",),
                    abv=True,
                ),
                item(
                    "dry-cider",
                    "Orchard dry cider",
                    10.00,
                    "Gluten-free, 12 oz can.",
                    diet=("gluten-free",),
                    abv=True,
                ),
            ],
        },
        {
            "id": "wine",
            "label": "Wine",
            "items": [
                item(
                    "pinot-noir",
                    "Halcyon Bay Pinot Noir",
                    62.00,
                    "Red, cherry and spice.",
                    abv=True,
                    glass=17.00,
                ),
                item(
                    "chardonnay",
                    "Coastal Ridge Chardonnay",
                    56.00,
                    "White, lightly oaked.",
                    abv=True,
                    glass=15.00,
                ),
                item(
                    "sauvignon-blanc",
                    "Sea Mist Sauvignon Blanc",
                    52.00,
                    "White, citrus and grass.",
                    abv=True,
                    glass=14.00,
                ),
                item(
                    "sparkling-rose",
                    "Belmonte sparkling rosé",
                    68.00,
                    "Dry, strawberry and brioche.",
                    abv=True,
                    glass=18.00,
                ),
            ],
        },
        {
            "id": "zero_proof",
            "label": "Zero proof",
            "items": [
                item(
                    "garden-cooler",
                    "Garden cooler",
                    11.00,
                    "Cucumber, basil, lime, soda.",
                    diet=("vegan", "gluten-free"),
                ),
                item(
                    "nojito",
                    "No-jito",
                    10.00,
                    "Mint, lime, cane sugar, soda.",
                    diet=("vegan", "gluten-free"),
                ),
                item(
                    "craft-soda",
                    "Craft root beer",
                    7.00,
                    "12 oz bottle.",
                    diet=("vegan", "gluten-free"),
                ),
                item(
                    "cold-brew",
                    "Cold brew",
                    7.00,
                    "Over ice.",
                    diet=("vegan", "gluten-free"),
                    options=("milk",),
                ),
            ],
        },
        {
            "id": "bites",
            "label": "Bar bites",
            "items": [
                item(
                    "truffle-fries",
                    "Truffle fries",
                    12.00,
                    "Parmesan, parsley, garlic aioli.",
                    allergens=("dairy", "egg"),
                    diet=("vegetarian", "gluten-free"),
                ),
                item(
                    "pool-tacos",
                    "Fish tacos",
                    18.00,
                    "Two tacos, rockfish, slaw, chipotle crema.",
                    allergens=("fish", "gluten", "dairy"),
                    options=("taco_mods",),
                ),
                item(
                    "guac-chips",
                    "Guacamole and chips",
                    14.00,
                    "Made to order.",
                    diet=("vegan", "gluten-free"),
                ),
            ],
        },
    ],
}

# ─── Spa ─────────────────────────────────────────────────────────────────────
SPA: dict[str, Any] = {
    "name": "Salt & Cypress Spa",
    "hours": "9:00 AM to 8:00 PM",
    "service_charge_pct": 20.0,
    "arrive": "Arrive 15 minutes early to use the steam room and relaxation lounge.",
    "cancellation": "Free cancellation up to 24 hours before your appointment. Within 24 hours, 50% of the treatment price is charged; a missed appointment is charged in full.",
    "therapists": [
        {
            "id": "elena",
            "name": "Elena",
            "gender": "female",
            "focus": "Swedish, hot stone, prenatal",
        },
        {"id": "marcus", "name": "Marcus", "gender": "male", "focus": "Deep tissue, sports"},
        {
            "id": "jasmine",
            "name": "Jasmine",
            "gender": "female",
            "focus": "Facials, couples, signature ritual",
        },
        {
            "id": "owen",
            "name": "Owen",
            "gender": "male",
            "focus": "Swedish, deep tissue, hot stone",
        },
    ],
    "treatments": [
        {
            "id": "swedish-50",
            "name": "Swedish massage",
            "category": "massage",
            "minutes": 50,
            "price": 165.00,
            "desc": "Long, flowing strokes with warm cypress oil.",
            "therapists": ["elena", "owen", "jasmine"],
        },
        {
            "id": "swedish-80",
            "name": "Swedish massage",
            "category": "massage",
            "minutes": 80,
            "price": 235.00,
            "desc": "The longer version, with a scalp massage.",
            "therapists": ["elena", "owen", "jasmine"],
        },
        {
            "id": "deep-50",
            "name": "Deep tissue massage",
            "category": "massage",
            "minutes": 50,
            "price": 185.00,
            "desc": "Firm pressure for knots and tired muscles.",
            "therapists": ["marcus", "owen"],
        },
        {
            "id": "deep-80",
            "name": "Deep tissue massage",
            "category": "massage",
            "minutes": 80,
            "price": 255.00,
            "desc": "Full-body deep work with a heated balm.",
            "therapists": ["marcus", "owen"],
        },
        {
            "id": "hot-stone-80",
            "name": "Hot stone massage",
            "category": "massage",
            "minutes": 80,
            "price": 265.00,
            "desc": "Warm basalt stones melt tension.",
            "therapists": ["elena", "owen"],
        },
        {
            "id": "ritual-110",
            "name": "Belmonte signature ritual",
            "category": "ritual",
            "minutes": 110,
            "price": 325.00,
            "desc": "Sea salt scrub, wrap and an 80 minute massage.",
            "therapists": ["jasmine", "elena"],
        },
        {
            "id": "couples-80",
            "name": "Couples massage",
            "category": "massage",
            "minutes": 80,
            "price": 480.00,
            "desc": "Side by side in the ocean suite, for two.",
            "therapists": ["jasmine", "elena", "owen"],
            "for_two": True,
        },
        {
            "id": "facial-50",
            "name": "Hydrating facial",
            "category": "facial",
            "minutes": 50,
            "price": 175.00,
            "desc": "Kelp mask and hyaluronic serum.",
            "therapists": ["jasmine"],
        },
        {
            "id": "mani-pedi-75",
            "name": "Manicure and pedicure",
            "category": "nails",
            "minutes": 75,
            "price": 110.00,
            "desc": "Shape, buff and polish, hands and feet.",
            "therapists": ["jasmine", "elena"],
        },
    ],
}

SLOT_TIMES = [
    "09:00",
    "10:00",
    "11:00",
    "12:00",
    "13:00",
    "14:00",
    "15:00",
    "16:00",
    "17:00",
    "18:00",
    "19:00",
]
SPA_DATES = ["2026-11-25", "2026-11-26", "2026-11-27", "2026-11-28"]


def spa_open(therapist: str, day: str, t: str) -> bool:
    """A therapist's free starts, deterministic: a fixed weekly pattern of
    booked hours, per therapist, shifted by the day."""
    booked = {
        "elena": {
            0: ["10:00", "11:00", "15:00"],
            1: ["09:00", "13:00", "14:00", "18:00"],
            2: ["12:00", "16:00", "17:00"],
            3: ["10:00", "19:00"],
        },
        "marcus": {
            0: ["09:00", "16:00", "17:00", "18:00"],
            1: ["11:00", "12:00", "15:00"],
            2: ["09:00", "10:00", "14:00"],
            3: ["13:00", "17:00"],
        },
        "jasmine": {
            0: ["12:00", "13:00", "14:00", "19:00"],
            1: ["10:00", "16:00"],
            2: ["11:00", "15:00", "18:00", "19:00"],
            3: ["09:00", "12:00", "14:00"],
        },
        "owen": {
            0: ["15:00", "16:00"],
            1: ["09:00", "10:00", "17:00", "19:00"],
            2: ["13:00", "18:00"],
            3: ["11:00", "15:00", "16:00"],
        },
    }
    off = {"owen": [3], "elena": [], "marcus": [], "jasmine": []}
    i = SPA_DATES.index(day)
    if i in off[therapist]:
        return False
    return t not in booked[therapist].get(i, [])


SPA["schedule"] = {
    day: {
        th["id"]: [t for t in SLOT_TIMES if spa_open(th["id"], day, t)] for th in SPA["therapists"]
    }
    for day in SPA_DATES
}

# ─── Activities and the resort map ───────────────────────────────────────────
PLACES = [
    {"id": "lobby", "name": "Lobby and front desk", "x": 50, "y": 46},
    {"id": "main-pool", "name": "Main pool", "x": 38, "y": 58},
    {"id": "cliff-pool", "name": "Cliff pool (adults only)", "x": 22, "y": 40},
    {"id": "spa", "name": "Salt & Cypress Spa", "x": 66, "y": 34},
    {"id": "kids-club", "name": "Little Gulls Kids Club", "x": 70, "y": 62},
    {"id": "tennis", "name": "Tennis courts", "x": 84, "y": 44},
    {"id": "golf", "name": "Halcyon Links clubhouse", "x": 86, "y": 20},
    {"id": "beach", "name": "Belmonte Cove beach", "x": 28, "y": 82},
    {"id": "compass-room", "name": "The Compass Room bar", "x": 56, "y": 52},
    {"id": "tidewater", "name": "Tidewater restaurant", "x": 44, "y": 38},
    {"id": "fitness", "name": "Fitness studio", "x": 62, "y": 22},
    {"id": "fire-pit", "name": "Fire pit lawn", "x": 34, "y": 70},
    {"id": "conference", "name": "Conference center", "x": 74, "y": 50},
    {"id": "dock", "name": "Kayak dock", "x": 14, "y": 66},
    {"id": "valet", "name": "Valet and motor court", "x": 52, "y": 12},
]

ACTIVITIES = [
    {
        "id": "main-pool",
        "name": "Main pool",
        "kind": "pools",
        "place": "main-pool",
        "desc": "Heated to 82°F, cabanas and the Driftwood Pool Bar.",
        "hours": "7:00 AM to 10:00 PM",
        "price": 0.0,
        "bookable": False,
        "times": [],
    },
    {
        "id": "cliff-pool",
        "name": "Cliff pool",
        "kind": "pools",
        "place": "cliff-pool",
        "desc": "Adults only (21+), infinity edge over the bay.",
        "hours": "9:00 AM to 7:00 PM",
        "price": 0.0,
        "bookable": False,
        "times": [],
    },
    {
        "id": "kids-club",
        "name": "Little Gulls Kids Club",
        "kind": "kids",
        "place": "kids-club",
        "desc": "Crafts, tide pool games and beach time for ages 4 to 12.",
        "hours": "9:00 AM to 4:00 PM",
        "price": 45.0,
        "per": "child, half day",
        "bookable": True,
        "times": ["09:00", "13:00"],
        "capacity": 16,
    },
    {
        "id": "golf",
        "name": "Halcyon Links, 18 holes",
        "kind": "golf",
        "place": "golf",
        "desc": "Clifftop links course; cart and range balls included.",
        "hours": "Tee times 7:00 AM to 3:00 PM",
        "price": 185.0,
        "per": "player",
        "bookable": True,
        "times": ["07:30", "09:10", "11:40", "13:20"],
        "capacity": 4,
    },
    {
        "id": "tennis",
        "name": "Tennis court",
        "kind": "sport",
        "place": "tennis",
        "desc": "Four hard courts; rackets and balls to borrow.",
        "hours": "7:00 AM to 9:00 PM",
        "price": 30.0,
        "per": "court, hour",
        "bookable": True,
        "times": ["08:00", "10:00", "15:00", "17:00", "19:00"],
        "capacity": 4,
    },
    {
        "id": "sunrise-yoga",
        "name": "Sunrise yoga",
        "kind": "fitness",
        "place": "fire-pit",
        "desc": "Gentle flow on the lawn; mats provided.",
        "hours": "7:30 to 8:30 AM daily",
        "price": 0.0,
        "bookable": True,
        "times": ["07:30"],
        "capacity": 20,
    },
    {
        "id": "hiit",
        "name": "Cliffside HIIT",
        "kind": "fitness",
        "place": "fitness",
        "desc": "45 minutes of intervals with a trainer.",
        "hours": "9:00 AM daily",
        "price": 0.0,
        "bookable": True,
        "times": ["09:00"],
        "capacity": 12,
    },
    {
        "id": "pilates",
        "name": "Sunset Pilates",
        "kind": "fitness",
        "place": "fitness",
        "desc": "Mat Pilates as the sun goes down.",
        "hours": "5:00 PM daily",
        "price": 0.0,
        "bookable": True,
        "times": ["17:00"],
        "capacity": 12,
    },
    {
        "id": "kayak-tour",
        "name": "Coastal kayak tour",
        "kind": "tours",
        "place": "dock",
        "desc": "Two hours past the sea caves with a guide; sea otters most days.",
        "hours": "10:00 AM and 2:00 PM",
        "price": 89.0,
        "per": "person",
        "bookable": True,
        "times": ["10:00", "14:00"],
        "capacity": 10,
    },
    {
        "id": "tide-pools",
        "name": "Tide pool walk",
        "kind": "tours",
        "place": "beach",
        "desc": "A naturalist leads you through the cove at low tide.",
        "hours": "3:30 PM",
        "price": 25.0,
        "per": "person",
        "bookable": True,
        "times": ["15:30"],
        "capacity": 14,
    },
    {
        "id": "wine-shuttle",
        "name": "Valley wine shuttle",
        "kind": "tours",
        "place": "valet",
        "desc": "Three tastings at small valley wineries, back by 6:00 PM.",
        "hours": "1:00 PM",
        "price": 129.0,
        "per": "person",
        "bookable": True,
        "times": ["13:00"],
        "capacity": 12,
        "min_age": 21,
    },
    {
        "id": "jazz-trio",
        "name": "Live jazz: the Marlowe Trio",
        "kind": "music",
        "place": "compass-room",
        "desc": "Standards and bossa nova by the fire. Tonight, no booking needed.",
        "hours": "Tonight 7:00 to 10:00 PM",
        "price": 0.0,
        "bookable": False,
        "times": [],
        "tonight": True,
    },
    {
        "id": "smores",
        "name": "S'mores at the fire pit",
        "kind": "music",
        "place": "fire-pit",
        "desc": "Fire pits lit at sunset, s'mores kits from the Compass Room.",
        "hours": "Tonight from 8:00 PM",
        "price": 0.0,
        "bookable": False,
        "times": [],
        "tonight": True,
    },
]

# ─── Conference halls and meeting rooms ──────────────────────────────────────
MEETINGS = {
    "blocks": [
        {
            "id": "morning",
            "label": "Half day, morning",
            "from": "08:00",
            "to": "12:00",
            "rate": "half",
        },
        {
            "id": "afternoon",
            "label": "Half day, afternoon",
            "from": "13:00",
            "to": "17:00",
            "rate": "half",
        },
        {"id": "full", "label": "Full day", "from": "08:00", "to": "17:00", "rate": "full"},
        {"id": "hours", "label": "By the hour", "rate": "hour"},
    ],
    "hours_from": "07:00",
    "hours_to": "21:00",
    "rooms": [
        {
            "id": "pelican",
            "name": "Pelican Studio",
            "sqft": 420,
            "layouts": {"boardroom": 10, "classroom": 12, "theatre": 20},
            "rates": {"hour": 95.0, "half": 320.0, "full": 560.0},
            "av": "65 inch screen, video conferencing, whiteboard",
            "desc": "A bright studio off the lobby for small meetings and interviews.",
        },
        {
            "id": "cypress",
            "name": "Cypress Boardroom",
            "sqft": 560,
            "layouts": {"boardroom": 14},
            "rates": {"hour": 150.0, "half": 520.0, "full": 900.0},
            "av": "85 inch screen, video conferencing, conference phone",
            "desc": "A walnut table for fourteen with a terrace over the gardens.",
        },
        {
            "id": "marina",
            "name": "Marina Room",
            "sqft": 1400,
            "layouts": {"boardroom": 24, "u_shape": 22, "classroom": 36, "theatre": 60},
            "rates": {"hour": 260.0, "half": 900.0, "full": 1600.0},
            "av": "Projector and screen, two wireless mics, sound system",
            "desc": "Bay views, natural light and blackout blinds.",
        },
        {
            "id": "grand",
            "name": "Grand Halcyon Ballroom",
            "sqft": 5200,
            "layouts": {"classroom": 180, "banquet": 220, "theatre": 300},
            "rates": {"hour": 850.0, "half": 3200.0, "full": 5800.0},
            "av": "Twin projectors, stage, four wireless mics, house sound",
            "desc": "Chandeliers, a stage and a pre-function terrace.",
        },
    ],
    "layout_labels": {
        "boardroom": "Boardroom",
        "u_shape": "U-shape",
        "classroom": "Classroom",
        "theatre": "Theatre",
        "banquet": "Banquet",
    },
    "catering": [
        {"id": "coffee", "name": "Coffee and tea break", "per_person": 18.0},
        {"id": "breakfast", "name": "Continental breakfast", "per_person": 32.0},
        {"id": "lunch", "name": "Working lunch", "per_person": 48.0},
        {"id": "snack", "name": "Afternoon snack break", "per_person": 22.0},
    ],
    "av_addons": [
        {"id": "mics", "name": "Two extra wireless mics", "price": 120.0},
        {"id": "recording", "name": "Session recording", "price": 350.0},
        {"id": "tech", "name": "AV technician on site", "price": 95.0, "per_hour": True},
    ],
    "fb_service_pct": 22.0,
    "policy": "Room rates include Wi-Fi, water, notepads and the room's built-in AV. A 22% service charge applies to food and beverage, and sales tax is 8.75% on food and beverage. Bookings are confirmed by our events team within two hours; free cancellation up to 72 hours before.",
    # Taken: room id -> date -> [from, to] pairs (24h).
    "taken": {
        "pelican": {"2026-11-26": [["09:00", "11:00"]], "2026-11-27": [["13:00", "17:00"]]},
        "cypress": {"2026-11-25": [["08:00", "17:00"]], "2026-11-26": [["13:00", "17:00"]]},
        "marina": {"2026-11-26": [["08:00", "12:00"]], "2026-11-27": [["08:00", "17:00"]]},
        "grand": {
            "2026-11-25": [["08:00", "21:00"]],
            "2026-11-26": [["08:00", "21:00"]],
            "2026-11-28": [["15:00", "21:00"]],
        },
    },
    "dates": ["2026-11-25", "2026-11-26", "2026-11-27", "2026-11-28", "2026-11-30", "2026-12-01"],
}

# ─── Visitors ────────────────────────────────────────────────────────────────
VISITORS = {
    "pending": [
        {
            "id": "v-rivera",
            "name": "Alex Rivera",
            "purpose": "Business meeting, says you're expecting him",
            "waiting_min": 9,
            "where": "Front desk",
            "status": "pending",
        },
        {
            "id": "v-florist",
            "name": "Courier, Coastline Florals",
            "purpose": "Flower delivery for Maya Thompson",
            "waiting_min": 4,
            "where": "Front desk",
            "status": "pending",
        },
        {
            "id": "v-chen",
            "name": "Priya Chen",
            "purpose": "Friend, dropping off a jacket",
            "waiting_min": 2,
            "where": "Lobby",
            "status": "pending",
        },
    ],
    "rule": "Visitors wait at the front desk until you approve. Approved visitors get directions to your room or wait in the lobby, as you choose. Visitors are welcome until 10:00 PM.",
    "meet": [
        {"id": "room", "label": "Send them up to my room"},
        {"id": "lobby", "label": "Ask them to wait in the lobby"},
    ],
    "until": "22:00",
}

# ─── Front desk requests ─────────────────────────────────────────────────────
REQUESTS = {
    "housekeeping": {
        "items": [
            {"id": "towels", "label": "Extra towels"},
            {"id": "pillows", "label": "Extra pillows"},
            {"id": "toiletries", "label": "Toiletries"},
            {"id": "robes", "label": "Extra robes"},
            {"id": "crib", "label": "Crib"},
            {"id": "turndown", "label": "Turndown service tonight"},
            {"id": "clean", "label": "Clean my room now"},
            {"id": "dnd", "label": "Do not disturb"},
        ],
        "eta": "about 20 minutes",
        "turndown": "Turndown runs 6:00 to 9:00 PM.",
    },
    "maintenance": {
        "issues": [
            {"id": "ac", "label": "Air conditioning or heating"},
            {"id": "tv", "label": "TV or Wi-Fi"},
            {"id": "plumbing", "label": "Plumbing or water"},
            {"id": "lights", "label": "Lights or power"},
            {"id": "door", "label": "Door, lock or key"},
            {"id": "other", "label": "Something else"},
        ],
        "eta": "an engineer within 30 minutes",
    },
    "wakeup": {
        "note": "A wake-up call rings your room phone; a second call follows five minutes later if there's no answer."
    },
    "valet": {
        "ticket": "V-2291",
        "eta": "about 10 minutes",
        "rate": "Valet parking is $52 a night, on your room bill; requesting the car is free.",
    },
    "transport": {
        "options": [
            {
                "id": "house-car",
                "label": "House car",
                "price": 0.0,
                "note": "Complimentary within 3 miles: the village, the marina, the farmers market.",
            },
            {
                "id": "airport",
                "label": "Airport sedan to Halcyon Bay Regional",
                "price": 68.0,
                "note": "Fixed fare, 25 minutes, up to 3 guests.",
            },
            {
                "id": "taxi",
                "label": "Taxi",
                "price": None,
                "note": "Metered, paid to the driver; usually 5 to 10 minutes to arrive.",
            },
        ]
    },
    "lost_found": {
        "note": "Found items are logged daily; the front desk calls you if anything matches. Items are kept 90 days."
    },
}

# ─── Hotel information ───────────────────────────────────────────────────────
INFO = [
    {
        "id": "checkin",
        "title": "Check-in and check-out",
        "facts": [
            "Check-in from 4:00 PM. Early check-in is $40 when a room is ready.",
            "Check-out by 11:00 AM. Late check-out to 12:00 PM is complimentary for Belmonte Circle Gold; 1:00 PM is $40, 2:00 PM is $60, on request.",
            "Express check-out in the app: the final bill is emailed to you.",
        ],
    },
    {
        "id": "house_rules",
        "title": "House rules",
        "facts": [
            "Registered guests 21 and over; up to 4 guests in a Deluxe room.",
            "Visitors are welcome until 10:00 PM and must be approved at the front desk.",
            "No parties or events in guest rooms.",
            "Please don't move hotel furniture onto balconies.",
        ],
    },
    {
        "id": "quiet",
        "title": "Quiet hours",
        "facts": ["Quiet hours are 10:00 PM to 7:00 AM.", "Pool music stops at 8:00 PM."],
    },
    {
        "id": "pets",
        "title": "Pet policy",
        "facts": [
            "Dogs are welcome: up to two per room, each up to 50 lb.",
            "The pet fee is $75 a night per room, plus a $150 refundable deposit.",
            "Dogs stay on a leash in public areas and are not allowed in the pools, restaurants, bars or spa.",
            "The Garden Lawn and the Bluff Trail are pet-friendly; waste bags are at both.",
            "Service animals are always welcome at no charge.",
        ],
    },
    {
        "id": "smoking",
        "title": "Smoking policy",
        "facts": [
            "Hotel Belmonte is smoke-free, including vaping and cannabis, in rooms and on balconies.",
            "Smoking in a room carries a $350 cleaning fee.",
            "The designated smoking area is beside the motor court, past the valet stand.",
        ],
    },
    {
        "id": "pools",
        "title": "Pools",
        "facts": [
            "Main pool: 7:00 AM to 10:00 PM, heated to 82°F, lifeguard 10:00 AM to 6:00 PM.",
            "Cliff pool: adults only (21+), 9:00 AM to 7:00 PM.",
            "Pool towels at the pool hut; cabanas bookable at the pool hut for $150 a day.",
        ],
    },
    {
        "id": "wifi",
        "title": "Wi-Fi",
        "facts": [
            "Network: Belmonte-Guest. Password: saltcypress.",
            "Free for every guest, up to 6 devices; streaming speed throughout the resort.",
        ],
    },
    {
        "id": "parking",
        "title": "Parking and valet",
        "facts": [
            "Valet parking is $52 a night; self-parking is $35 a night.",
            "Four EV chargers in the motor court, free for guests.",
            "Request your car in the app; it's ready in about 10 minutes.",
        ],
    },
    {
        "id": "dining_hours",
        "title": "Restaurants and bars",
        "facts": [
            "Tidewater restaurant: breakfast 6:30 to 11:00 AM, dinner 5:30 to 10:00 PM.",
            "Driftwood Pool Bar: 11:00 AM to 6:00 PM.",
            "The Compass Room: 4:00 PM to midnight, live music most nights.",
            "In-room dining: 24 hours.",
        ],
    },
    {
        "id": "fitness",
        "title": "Fitness and spa",
        "facts": [
            "Fitness studio: open 24 hours with your room key.",
            "Salt & Cypress Spa: 9:00 AM to 8:00 PM; steam room and lounge free with any treatment.",
        ],
    },
    {
        "id": "accessibility",
        "title": "Accessibility",
        "facts": [
            "Accessible rooms with roll-in showers on floors 2, 5 and 9.",
            "Pool lifts at both pools; step-free routes to every restaurant and the beach boardwalk.",
            "Hearing accessibility kits (visual alarms, TTY) on request at the front desk.",
            "Accessible parking spaces beside the main entrance.",
        ],
    },
    {
        "id": "contact",
        "title": "Contact",
        "facts": [
            "Front desk: dial 0 from your room, or (805) 555-0140, 24 hours.",
            "Concierge: dial 5, 7:00 AM to 11:00 PM.",
            "Hotel Belmonte, 1200 Cliffside Drive, Halcyon Bay, California.",
        ],
    },
]


def main() -> None:
    data = {
        "$comment": "Generated by data/build_data.py; edit that file, not this one. Everything here is invented for a demo.",
        "hotel": HOTEL,
        "guest": GUEST,
        "scenarios": SCENARIOS,
        "checkin": CHECKIN,
        "late_checkout": LATE_CHECKOUT,
        "dispute_rule": DISPUTE_RULE,
        "option_groups": OPTION_GROUPS,
        "dining": DINING,
        "bar": BAR,
        "spa": SPA,
        "places": PLACES,
        "activities": ACTIVITIES,
        "meetings": MEETINGS,
        "visitors": VISITORS,
        "requests": REQUESTS,
        "info": INFO,
    }
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
