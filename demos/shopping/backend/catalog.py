"""Canonical mobile-phone catalog for the ``shopping`` managed brain.

This is the single source of truth the LLM reasons over: the full catalog is
rendered into the system prompt (so the agent knows every product cold) and the
search / lookup / sort tools return slices of it back to the model.

The console keeps a parallel TypeScript mirror at
``console/src/mobile/catalog.ts`` for *rendering*. The two files MUST
share product ``id`` values — the agent drives the UI by pushing those ids in
``ui_command`` RTVI messages, and the browser resolves them against its own
copy. When you add or rename a product here, mirror the id there.
"""

from __future__ import annotations

from typing import Any, TypedDict


class Phone(TypedDict):
    id: str
    brand: str
    name: str
    price: int  # USD
    category: str  # "flagship" | "mid-range" | "budget"
    tagline: str
    colors: list[str]
    display: str
    processor: str
    ram_gb: list[int]
    storage_gb: list[int]
    rear_camera: str
    front_camera: str
    battery_mah: int
    charging: str
    os: str
    weight_g: int
    water_resistance: str
    five_g: bool
    rating: float  # average customer rating out of 5
    review_count: int
    release_year: int
    highlights: list[str]
    pros: list[str]
    cons: list[str]
    best_for: str


# ── The catalog ─────────────────────────────────────────────────────────────
# Sixteen phones spanning budget → flagship, mixed brands. Prices in USD.
CATALOG: list[Phone] = [
    {
        "id": "galaxy-s24-ultra",
        "brand": "Samsung",
        "name": "Galaxy S24 Ultra",
        "price": 1299,
        "category": "flagship",
        "tagline": "The everything phone, with a built-in S Pen and AI everywhere.",
        "colors": ["Titanium Black", "Titanium Gray", "Titanium Violet", "Titanium Yellow"],
        "display": '6.8" QHD+ Dynamic AMOLED 2X, 120Hz, 2600 nits',
        "processor": "Snapdragon 8 Gen 3 for Galaxy",
        "ram_gb": [12],
        "storage_gb": [256, 512, 1024],
        "rear_camera": "200MP main + 50MP 5x periscope + 10MP 3x tele + 12MP ultrawide",
        "front_camera": "12MP",
        "battery_mah": 5000,
        "charging": "45W wired, 15W wireless",
        "os": "Android 14, One UI 6.1 — 7 years of updates",
        "weight_g": 232,
        "water_resistance": "IP68",
        "five_g": True,
        "rating": 4.8,
        "review_count": 4210,
        "release_year": 2024,
        "highlights": [
            "Built-in S Pen",
            "200MP camera",
            "5x optical zoom",
            "Titanium frame",
            "Galaxy AI",
        ],
        "pros": [
            "Best-in-class zoom camera",
            "S Pen productivity",
            "7 years of OS updates",
            "Huge bright display",
        ],
        "cons": ["Expensive", "Large and heavy", "Slower charging than rivals"],
        "best_for": "Power users who want the biggest camera reach and stylus productivity.",
    },
    {
        "id": "iphone-15-pro-max",
        "brand": "Apple",
        "name": "iPhone 15 Pro Max",
        "price": 1199,
        "category": "flagship",
        "tagline": "The biggest iPhone, with a 5x zoom and titanium build.",
        "colors": ["Natural Titanium", "Blue Titanium", "White Titanium", "Black Titanium"],
        "display": '6.7" Super Retina XDR OLED, 120Hz ProMotion, 2000 nits',
        "processor": "Apple A17 Pro",
        "ram_gb": [8],
        "storage_gb": [256, 512, 1024],
        "rear_camera": "48MP main + 12MP 5x periscope tele + 12MP ultrawide",
        "front_camera": "12MP TrueDepth",
        "battery_mah": 4441,
        "charging": "20W wired, 15W MagSafe, USB-C",
        "os": "iOS 17",
        "weight_g": 221,
        "water_resistance": "IP68",
        "five_g": True,
        "rating": 4.8,
        "review_count": 3120,
        "release_year": 2023,
        "highlights": [
            "Titanium design",
            "A17 Pro chip",
            "5x optical zoom",
            "Action button",
            "USB-C",
        ],
        "pros": [
            "Best big-screen iPhone",
            "5x periscope zoom",
            "Excellent video recording",
            "Long software support",
        ],
        "cons": ["Heavy", "Expensive", "Slow wired charging"],
        "best_for": "iOS users who want the biggest screen and longest camera zoom.",
    },
    {
        "id": "iphone-15-pro",
        "brand": "Apple",
        "name": "iPhone 15 Pro",
        "price": 999,
        "category": "flagship",
        "tagline": "Titanium, the A17 Pro chip, and a customizable Action button.",
        "colors": ["Natural Titanium", "Blue Titanium", "White Titanium", "Black Titanium"],
        "display": '6.1" Super Retina XDR OLED, 120Hz ProMotion, 2000 nits',
        "processor": "Apple A17 Pro",
        "ram_gb": [8],
        "storage_gb": [128, 256, 512, 1024],
        "rear_camera": "48MP main + 12MP 3x tele + 12MP ultrawide",
        "front_camera": "12MP TrueDepth",
        "battery_mah": 3274,
        "charging": "20W wired, 15W MagSafe, USB-C",
        "os": "iOS 17",
        "weight_g": 187,
        "water_resistance": "IP68",
        "five_g": True,
        "rating": 4.8,
        "review_count": 5300,
        "release_year": 2023,
        "highlights": [
            "Titanium design",
            "A17 Pro chip",
            "Action button",
            "USB-C",
            "Console-grade gaming",
        ],
        "pros": [
            "Top-tier performance",
            "Excellent video recording",
            "Compact and light",
            "Long software support",
        ],
        "cons": ["Only 3x zoom", "Pricey storage upgrades", "Slow wired charging"],
        "best_for": "iOS users who want a compact flagship with the best video and gaming.",
    },
    {
        "id": "pixel-8-pro",
        "brand": "Google",
        "name": "Pixel 8 Pro",
        "price": 999,
        "category": "flagship",
        "tagline": "The smartest camera phone, powered by Google AI.",
        "colors": ["Obsidian", "Porcelain", "Bay"],
        "display": '6.7" LTPO OLED, 120Hz, 2400 nits',
        "processor": "Google Tensor G3",
        "ram_gb": [12],
        "storage_gb": [128, 256, 512],
        "rear_camera": "50MP main + 48MP 5x tele + 48MP ultrawide",
        "front_camera": "10.5MP",
        "battery_mah": 5050,
        "charging": "30W wired, 23W wireless",
        "os": "Android 14 — 7 years of updates",
        "weight_g": 213,
        "water_resistance": "IP68",
        "five_g": True,
        "rating": 4.6,
        "review_count": 2150,
        "release_year": 2023,
        "highlights": [
            "Best-in-class AI photo editing",
            "Magic Editor",
            "Temperature sensor",
            "7 years of updates",
        ],
        "pros": [
            "Unmatched computational photography",
            "Clean software",
            "Helpful AI features",
            "Long update window",
        ],
        "cons": ["Tensor runs warm", "Average charging speed", "Big footprint"],
        "best_for": "Photographers who want the best point-and-shoot results and AI editing.",
    },
    {
        "id": "asus-rog-8-pro",
        "brand": "Asus",
        "name": "ROG Phone 8 Pro",
        "price": 1099,
        "category": "flagship",
        "tagline": "A gaming powerhouse with a 165Hz screen and huge battery.",
        "colors": ["Phantom Black"],
        "display": '6.78" LTPO AMOLED, 165Hz, 2500 nits',
        "processor": "Snapdragon 8 Gen 3",
        "ram_gb": [16, 24],
        "storage_gb": [512, 1024],
        "rear_camera": "50MP main + 32MP 3x tele + 13MP ultrawide",
        "front_camera": "32MP",
        "battery_mah": 5500,
        "charging": "65W wired, 15W wireless",
        "os": "Android 14 — 2 years of updates",
        "weight_g": 225,
        "water_resistance": "IP68",
        "five_g": True,
        "rating": 4.7,
        "review_count": 760,
        "release_year": 2024,
        "highlights": [
            "165Hz gaming display",
            "5500mAh battery",
            "AirTrigger shoulder buttons",
            "Active cooling",
        ],
        "pros": [
            "Best-in-class gaming",
            "Huge battery life",
            "Ultra-smooth 165Hz display",
            "Loud stereo speakers",
        ],
        "cons": ["Bulky and heavy", "Gamer styling not for everyone", "Shorter update window"],
        "best_for": "Mobile gamers who want the fastest display and the biggest battery.",
    },
    {
        "id": "oneplus-12",
        "brand": "OnePlus",
        "name": "OnePlus 12",
        "price": 799,
        "category": "flagship",
        "tagline": "Flagship power and absurdly fast charging for less.",
        "colors": ["Silky Black", "Flowy Emerald", "White"],
        "display": '6.82" QHD+ LTPO AMOLED, 120Hz, 4500 nits peak',
        "processor": "Snapdragon 8 Gen 3",
        "ram_gb": [12, 16],
        "storage_gb": [256, 512],
        "rear_camera": "50MP main + 64MP 3x periscope + 48MP ultrawide (Hasselblad)",
        "front_camera": "32MP",
        "battery_mah": 5400,
        "charging": "80W wired, 50W wireless",
        "os": "Android 14, OxygenOS 14 — 4 years of updates",
        "weight_g": 220,
        "water_resistance": "IP65",
        "five_g": True,
        "rating": 4.6,
        "review_count": 1730,
        "release_year": 2024,
        "highlights": [
            "80W fast charging",
            "5400mAh battery",
            "Hasselblad cameras",
            "Brightest display",
        ],
        "pros": [
            "Charges 0-100 in ~26 min",
            "Flagship chip at a lower price",
            "Great battery life",
            "Fluid display",
        ],
        "cons": [
            "Only IP65 water resistance",
            "Shorter update window than rivals",
            "No mmWave 5G in some regions",
        ],
        "best_for": "Buyers who want flagship speed and the fastest charging without paying flagship prices.",
    },
    {
        "id": "galaxy-s24",
        "brand": "Samsung",
        "name": "Galaxy S24",
        "price": 799,
        "category": "flagship",
        "tagline": "A pocketable flagship with Galaxy AI and seven years of updates.",
        "colors": ["Onyx Black", "Marble Gray", "Cobalt Violet", "Amber Yellow"],
        "display": '6.2" FHD+ Dynamic AMOLED 2X, 120Hz, 2600 nits',
        "processor": "Snapdragon 8 Gen 3 for Galaxy",
        "ram_gb": [8],
        "storage_gb": [128, 256],
        "rear_camera": "50MP main + 10MP 3x tele + 12MP ultrawide",
        "front_camera": "12MP",
        "battery_mah": 4000,
        "charging": "25W wired, 15W wireless",
        "os": "Android 14, One UI 6.1 — 7 years of updates",
        "weight_g": 167,
        "water_resistance": "IP68",
        "five_g": True,
        "rating": 4.6,
        "review_count": 1890,
        "release_year": 2024,
        "highlights": [
            "Compact flagship",
            "Galaxy AI",
            "7 years of updates",
            "120Hz display",
        ],
        "pros": [
            "Pocketable size",
            "Flagship performance",
            "Long update window",
            "Bright smooth display",
        ],
        "cons": ["Smaller battery", "25W charging is slow", "No periscope zoom"],
        "best_for": "People who want a small Samsung flagship with the latest AI features.",
    },
    {
        "id": "xiaomi-14",
        "brand": "Xiaomi",
        "name": "Xiaomi 14",
        "price": 869,
        "category": "flagship",
        "tagline": "A compact flagship with Leica optics.",
        "colors": ["Black", "White", "Jade Green"],
        "display": '6.36" LTPO AMOLED, 120Hz, 3000 nits',
        "processor": "Snapdragon 8 Gen 3",
        "ram_gb": [12],
        "storage_gb": [256, 512],
        "rear_camera": "50MP main + 50MP 3.2x tele + 50MP ultrawide (Leica)",
        "front_camera": "32MP",
        "battery_mah": 4610,
        "charging": "90W wired, 50W wireless",
        "os": "Android 14, HyperOS — 4 years of updates",
        "weight_g": 193,
        "water_resistance": "IP68",
        "five_g": True,
        "rating": 4.5,
        "review_count": 690,
        "release_year": 2024,
        "highlights": [
            "Leica triple 50MP cameras",
            "Compact body",
            "90W charging",
            "Very bright display",
        ],
        "pros": [
            "Pocketable flagship",
            "Versatile Leica cameras",
            "Fast charging",
            "Premium build",
        ],
        "cons": [
            "Software has bloatware",
            "Limited availability in some regions",
            "Smaller battery than rivals",
        ],
        "best_for": "People who want a small flagship with serious camera versatility.",
    },
    {
        "id": "pixel-8",
        "brand": "Google",
        "name": "Pixel 8",
        "price": 699,
        "category": "flagship",
        "tagline": "Pixel camera magic and Google AI in a smaller flagship.",
        "colors": ["Obsidian", "Hazel", "Rose"],
        "display": '6.2" OLED, 120Hz, 2000 nits',
        "processor": "Google Tensor G3",
        "ram_gb": [8],
        "storage_gb": [128, 256],
        "rear_camera": "50MP main + 12MP ultrawide",
        "front_camera": "10.5MP",
        "battery_mah": 4575,
        "charging": "27W wired, 18W wireless",
        "os": "Android 14 — 7 years of updates",
        "weight_g": 187,
        "water_resistance": "IP68",
        "five_g": True,
        "rating": 4.5,
        "review_count": 1450,
        "release_year": 2023,
        "highlights": [
            "Pixel camera magic",
            "Magic Editor",
            "7 years of updates",
            "Compact",
        ],
        "pros": [
            "Great cameras",
            "Clean software",
            "Long update window",
            "Compact and comfortable",
        ],
        "cons": ["No telephoto lens", "Tensor runs warm", "Average charging speed"],
        "best_for": "Buyers who want Pixel cameras and AI in a smaller flagship.",
    },
    {
        "id": "nothing-phone-2",
        "brand": "Nothing",
        "name": "Nothing Phone (2)",
        "price": 599,
        "category": "mid-range",
        "tagline": "Distinctive Glyph design with clean, fast software.",
        "colors": ["White", "Dark Gray"],
        "display": '6.7" LTPO OLED, 120Hz, 1600 nits',
        "processor": "Snapdragon 8+ Gen 1",
        "ram_gb": [8, 12],
        "storage_gb": [128, 256, 512],
        "rear_camera": "50MP main + 50MP ultrawide",
        "front_camera": "32MP",
        "battery_mah": 4700,
        "charging": "45W wired, 15W wireless",
        "os": "Android 13, Nothing OS 2 — 3 years of updates",
        "weight_g": 201,
        "water_resistance": "IP54",
        "five_g": True,
        "rating": 4.4,
        "review_count": 1120,
        "release_year": 2023,
        "highlights": [
            "Glyph LED interface",
            "Transparent design",
            "Clean near-stock software",
            "Wireless charging",
        ],
        "pros": ["Unique looks", "Snappy clean UI", "Good main camera", "Solid value"],
        "cons": ["Only IP54", "No telephoto lens", "Last-gen chip"],
        "best_for": "Buyers who want a stylish, clutter-free phone that stands out.",
    },
    {
        "id": "iphone-15",
        "brand": "Apple",
        "name": "iPhone 15",
        "price": 799,
        "category": "mid-range",
        "tagline": "The Dynamic Island and a 48MP camera, now with USB-C.",
        "colors": ["Blue", "Pink", "Yellow", "Green", "Black"],
        "display": '6.1" Super Retina XDR OLED, 60Hz, 2000 nits',
        "processor": "Apple A16 Bionic",
        "ram_gb": [6],
        "storage_gb": [128, 256, 512],
        "rear_camera": "48MP main + 12MP ultrawide",
        "front_camera": "12MP TrueDepth",
        "battery_mah": 3349,
        "charging": "20W wired, 15W MagSafe, USB-C",
        "os": "iOS 17",
        "weight_g": 171,
        "water_resistance": "IP68",
        "five_g": True,
        "rating": 4.7,
        "review_count": 4080,
        "release_year": 2023,
        "highlights": ["Dynamic Island", "48MP camera", "USB-C", "Lightweight"],
        "pros": [
            "Great value iPhone",
            "Reliable cameras",
            "Long software support",
            "Compact and light",
        ],
        "cons": ["Stuck at 60Hz", "No telephoto", "Slow charging"],
        "best_for": "iOS buyers who want a modern iPhone without paying Pro prices.",
    },
    {
        "id": "galaxy-a55",
        "brand": "Samsung",
        "name": "Galaxy A55",
        "price": 449,
        "category": "mid-range",
        "tagline": "Premium feel and a great screen at a mid-range price.",
        "colors": ["Awesome Iceblue", "Awesome Lilac", "Awesome Navy", "Awesome Lemon"],
        "display": '6.6" Super AMOLED, 120Hz, 1000 nits',
        "processor": "Exynos 1480",
        "ram_gb": [8, 12],
        "storage_gb": [128, 256],
        "rear_camera": "50MP main + 8MP ultrawide + 5MP macro",
        "front_camera": "32MP",
        "battery_mah": 5000,
        "charging": "25W wired",
        "os": "Android 14, One UI 6.1 — 4 years of updates",
        "weight_g": 213,
        "water_resistance": "IP67",
        "five_g": True,
        "rating": 4.4,
        "review_count": 1560,
        "release_year": 2024,
        "highlights": ["Metal frame", "120Hz AMOLED", "4 years of updates", "Big battery"],
        "pros": [
            "Premium build for the price",
            "Bright smooth display",
            "Long battery life",
            "Long update support",
        ],
        "cons": ["No wireless charging", "Slower charging", "Average low-light camera"],
        "best_for": "Value buyers who want a premium-feeling Samsung without flagship cost.",
    },
    {
        "id": "pixel-8a",
        "brand": "Google",
        "name": "Pixel 8a",
        "price": 499,
        "category": "mid-range",
        "tagline": "Flagship-grade Pixel cameras and AI on a budget.",
        "colors": ["Obsidian", "Porcelain", "Bay", "Aloe"],
        "display": '6.1" OLED, 120Hz, 2000 nits',
        "processor": "Google Tensor G3",
        "ram_gb": [8],
        "storage_gb": [128, 256],
        "rear_camera": "64MP main + 13MP ultrawide",
        "front_camera": "13MP",
        "battery_mah": 4492,
        "charging": "18W wired, 7.5W wireless",
        "os": "Android 14 — 7 years of updates",
        "weight_g": 188,
        "water_resistance": "IP67",
        "five_g": True,
        "rating": 4.6,
        "review_count": 1340,
        "release_year": 2024,
        "highlights": ["Pixel camera magic", "7 years of updates", "Google AI features", "Compact"],
        "pros": [
            "Excellent cameras for the price",
            "Longest update window in class",
            "Clean software",
            "Wireless charging",
        ],
        "cons": ["Slow charging", "Tensor runs warm", "Plastic back"],
        "best_for": "Buyers who want the best camera and longest support under $500.",
    },
    {
        "id": "motorola-edge-50-pro",
        "brand": "Motorola",
        "name": "Motorola Edge 50 Pro",
        "price": 599,
        "category": "mid-range",
        "tagline": "A curved display, fast charging, and a clean Moto experience.",
        "colors": ["Black Beauty", "Luxe Lavender", "Moonlight Pearl"],
        "display": '6.7" pOLED, 144Hz, 2000 nits',
        "processor": "Snapdragon 7 Gen 3",
        "ram_gb": [8, 12],
        "storage_gb": [256, 512],
        "rear_camera": "50MP main + 10MP 3x tele + 13MP ultrawide",
        "front_camera": "50MP",
        "battery_mah": 4500,
        "charging": "125W wired, 50W wireless",
        "os": "Android 14 — 3 years of updates",
        "weight_g": 186,
        "water_resistance": "IP68",
        "five_g": True,
        "rating": 4.3,
        "review_count": 540,
        "release_year": 2024,
        "highlights": [
            "125W ultra-fast charging",
            "144Hz curved display",
            "Telephoto camera",
            "Near-stock software",
        ],
        "pros": [
            "Fastest charging in class",
            "Has a real telephoto lens",
            "Clean light software",
            "Bright display",
        ],
        "cons": ["Shorter update window", "Mid-tier chip", "Curved screen not for everyone"],
        "best_for": "Buyers who want fast charging and a telephoto camera in the mid-range.",
    },
    {
        "id": "nothing-phone-2a",
        "brand": "Nothing",
        "name": "Nothing Phone (2a)",
        "price": 349,
        "category": "budget",
        "tagline": "Standout Glyph design and clean software on a budget.",
        "colors": ["Black", "Milk", "Blue"],
        "display": '6.7" AMOLED, 120Hz, 1300 nits',
        "processor": "MediaTek Dimensity 7200 Pro",
        "ram_gb": [8, 12],
        "storage_gb": [128, 256],
        "rear_camera": "50MP main + 50MP ultrawide",
        "front_camera": "32MP",
        "battery_mah": 5000,
        "charging": "45W wired",
        "os": "Android 14, Nothing OS 2.5 — 3 years of updates",
        "weight_g": 190,
        "water_resistance": "IP54",
        "five_g": True,
        "rating": 4.4,
        "review_count": 980,
        "release_year": 2024,
        "highlights": [
            "Glyph interface",
            "Big 5000mAh battery",
            "Clean fast software",
            "Bright AMOLED",
        ],
        "pros": ["Standout design", "Great value", "Clean fast UI", "Good main camera"],
        "cons": ["Only IP54", "No wireless charging", "No telephoto lens"],
        "best_for": "Budget buyers who want flair and clean software for under $400.",
    },
    {
        "id": "redmi-note-13-pro",
        "brand": "Xiaomi",
        "name": "Redmi Note 13 Pro",
        "price": 349,
        "category": "budget",
        "tagline": "A 200MP camera and 67W charging at a budget price.",
        "colors": ["Midnight Black", "Ocean Teal", "Aurora Purple"],
        "display": '6.67" AMOLED, 120Hz, 1300 nits',
        "processor": "Snapdragon 7s Gen 2",
        "ram_gb": [8, 12],
        "storage_gb": [128, 256],
        "rear_camera": "200MP main + 8MP ultrawide + 2MP macro",
        "front_camera": "16MP",
        "battery_mah": 5100,
        "charging": "67W wired",
        "os": "Android 13, HyperOS — 3 years of updates",
        "weight_g": 187,
        "water_resistance": "IP54",
        "five_g": True,
        "rating": 4.3,
        "review_count": 2240,
        "release_year": 2023,
        "highlights": [
            "200MP camera",
            "67W fast charging",
            "Big 5100mAh battery",
            "120Hz AMOLED",
        ],
        "pros": [
            "High-res 200MP camera",
            "Fast charging",
            "Great value",
            "Long battery life",
        ],
        "cons": ["Only IP54", "Some bloatware", "Plastic frame"],
        "best_for": "Value buyers who want a high-megapixel camera and fast charging for cheap.",
    },
]

_BY_ID: dict[str, Phone] = {p["id"]: p for p in CATALOG}

VALID_IDS: list[str] = [p["id"] for p in CATALOG]
VALID_BRANDS: list[str] = sorted({p["brand"] for p in CATALOG})
VALID_CATEGORIES: list[str] = ["flagship", "mid-range", "budget"]

# Sort keys the agent (and console) can order results by. Mirror in
# ``console/src/mobile/catalog.ts``.
VALID_SORTS: list[str] = ["price_low", "price_high", "rating", "newest"]


# ── Lookups ─────────────────────────────────────────────────────────────────
def get_product(product_id: str) -> Phone | None:
    return _BY_ID.get(product_id)


def summary(p: Phone) -> dict[str, Any]:
    """Compact slice for tool returns — enough for the model to talk about a
    result list without dumping every spec."""
    return {
        "id": p["id"],
        "brand": p["brand"],
        "name": p["name"],
        "price_usd": p["price"],
        "category": p["category"],
        "tagline": p["tagline"],
        "rating": p["rating"],
        "review_count": p["review_count"],
        "highlights": p["highlights"],
    }


def sort_catalog(phones: list[Phone], sort_by: str | None) -> list[Phone]:
    """Order a list of phones by one of :data:`VALID_SORTS` (stable, returns a
    new list). Unknown / missing keys leave the order untouched."""
    if sort_by == "price_low":
        return sorted(phones, key=lambda p: p["price"])
    if sort_by == "price_high":
        return sorted(phones, key=lambda p: p["price"], reverse=True)
    if sort_by == "rating":
        return sorted(phones, key=lambda p: (p["rating"], p["review_count"]), reverse=True)
    if sort_by == "newest":
        return sorted(phones, key=lambda p: p["release_year"], reverse=True)
    return list(phones)


def search_catalog(
    query: str = "",
    brand: str | None = None,
    max_price: int | None = None,
    min_price: int | None = None,
    category: str | None = None,
    sort_by: str | None = None,
) -> list[Phone]:
    """Filter the catalog. ``query`` is a loose keyword match over name, brand,
    tagline and highlights; the rest are exact/range filters. ``sort_by`` orders
    the matches by one of :data:`VALID_SORTS`."""
    q = query.lower().strip()
    results: list[Phone] = []
    for p in CATALOG:
        if brand and p["brand"].lower() != brand.lower():
            continue
        if category and p["category"].lower() != category.lower():
            continue
        if max_price is not None and p["price"] > max_price:
            continue
        if min_price is not None and p["price"] < min_price:
            continue
        if q:
            haystack = " ".join(
                [p["name"], p["brand"], p["tagline"], p["best_for"], " ".join(p["highlights"])]
            ).lower()
            if q not in haystack and not any(word in haystack for word in q.split()):
                continue
        results.append(p)
    return sort_catalog(results, sort_by)


def catalog_for_prompt() -> str:
    """Render the whole catalog as compact text for the system instruction."""
    lines: list[str] = []
    for p in CATALOG:
        ram = "/".join(str(r) for r in p["ram_gb"])
        storage = "/".join(str(s) for s in p["storage_gb"])
        lines.append(
            f"- [{p['id']}] {p['brand']} {p['name']} — ${p['price']} ({p['category']}), "
            f"rated {p['rating']}/5 from {p['review_count']} reviews. "
            f"{p['display']}; {p['processor']}; {ram}GB RAM; {storage}GB; "
            f"cameras: {p['rear_camera']}; {p['battery_mah']}mAh, {p['charging']}; "
            f"{p['os']}; {p['water_resistance']}. "
            f"Highlights: {', '.join(p['highlights'])}. "
            f"Best for: {p['best_for']}"
        )
    return "\n".join(lines)
