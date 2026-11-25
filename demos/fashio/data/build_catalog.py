"""Build Fashio's catalogue from the Fashion Product Images Dataset.

The products are real: the Fashion Product Images Dataset by Param Aggarwal
(Kaggle, MIT licence, scraped from Myntra),
https://www.kaggle.com/datasets/paramaggarwal/fashion-product-images-dataset .
Their names, brands, prices (INR), sizes and descriptions are used as they
are. Images never come from the dataset's Myntra URLs: the store serves its
own copies from the public bucket (``img/<id>/w400.webp`` and ``w1080.webp``),
made by a separate job.

This script reads the dataset zip directly (no extraction) and writes:

- ``demos/fashio/data/catalog.json`` — the index: taxonomy, brands, colours
  and one compact row per product. Committed: the brain reads it, and it is
  uploaded as ``catalog/v1/index.json`` for the page.
- ``<out>/p/<id>.json`` — one detail record per product (the description as
  sections, every attribute, the colour variants, similar items), uploaded as
  ``catalog/v1/p/<id>.json``.

Curation (decided here, documented in the README):

- Kept: apparel, footwear, bags, watches, eyewear, wallets, belts, jewellery,
  headwear, ties, cufflinks, scarves and stoles, fragrance and gift sets.
  Dropped: innerwear and nightwear, socks, personal care other than fragrance,
  free gifts, sporting goods, home, shoe accessories, and any record without a
  JSON, an image in the zip, a name, or a price of at least ₹149.
- At most ``CAPS[type]`` products per article type for adults and
  ``KIDS_CAP`` per type for kids, picked round-robin across brands (so no
  brand floods a listing), best first: a description, attributes, a discount,
  a newer year. Colour variants come along with the product picked.
- Colour variants: the same brand, gender, article type and price, and the
  same name once the brand, the gender words and the colour words are taken
  out (``Puma Men Grey Ferrari T-shirt`` and ``Puma Men Red Ferrari T-shirt``),
  when that name still says something beyond the article type. At most six.
- Sizes normalised per article type: letter sizes XS to 3XL (numeric chest,
  bust or collar sizes mapped to letters), waist 26 to 44 for jeans and
  trousers, UK sizes for footwear (EURO and US converted), age bands for kids,
  and "Onesize" for bags, watches, jewellery and the like.
- Stock: the dataset's snapshot marks almost every size unavailable, so
  Fashio's stock is generated here deterministically from the product id and
  size (about one size in seven out of stock, some "only a few left"), with at
  least one size in stock. The dataset's own availability wins where it says a
  size is available.

Run (from the repo root):

    uv run python demos/fashio/data/build_catalog.py --zip ~/workspace/fashion-product-images-dataset.zip \\
        --out /tmp/fashio-catalog [--upload]

``--upload`` copies the index and the detail files to
``gs://voqalize-fashio-assets/catalog/v1/`` with gcloud (project
voqal-cloud-prod) and a Cache-Control of an hour.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import re
import subprocess
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
INDEX = HERE / "catalog.json"
ROOT = "fashion-dataset/fashion-dataset"
BUCKET = "gs://voqalize-fashio-assets"
VERSION = "v1"

CREDIT = {
    "dataset": "Fashion Product Images Dataset",
    "author": "Param Aggarwal",
    "licence": "MIT",
    "source": "Myntra",
    "url": "https://www.kaggle.com/datasets/paramaggarwal/fashion-product-images-dataset",
}

# ─── What the store sells ─────────────────────────────────────────────────────

#: Article type → (store label, adults cap). Types not listed are dropped.
CAPS: dict[str, tuple[str, int]] = {
    # Topwear
    "Tshirts": ("T-shirts", 360),
    "Shirts": ("Shirts", 280),
    "Tops": ("Tops", 240),
    "Kurtas": ("Kurtas", 400),
    "Kurtis": ("Kurtis", 120),
    "Tunics": ("Tunics", 80),
    "Sweatshirts": ("Sweatshirts", 80),
    "Sweaters": ("Sweaters", 80),
    "Jackets": ("Jackets", 90),
    "Rain Jacket": ("Rain jackets", 12),
    "Waistcoat": ("Nehru jackets & waistcoats", 15),
    "Dupatta": ("Dupattas", 50),
    "Dresses": ("Dresses", 200),
    "Jumpsuit": ("Jumpsuits", 16),
    "Sarees": ("Sarees", 220),
    "Kurta Sets": ("Kurta sets", 100),
    # Bottomwear
    "Jeans": ("Jeans", 160),
    "Trousers": ("Trousers", 120),
    "Shorts": ("Shorts", 90),
    "Track Pants": ("Track pants", 60),
    "Skirts": ("Skirts", 60),
    "Leggings": ("Leggings", 50),
    "Capris": ("Capris", 30),
    "Jeggings": ("Jeggings", 20),
    "Patiala": ("Patialas", 20),
    "Salwar": ("Salwars", 20),
    "Churidar": ("Churidars", 20),
    # Footwear
    "Casual Shoes": ("Casual shoes", 220),
    "Sports Shoes": ("Sports shoes", 180),
    "Formal Shoes": ("Formal shoes", 90),
    "Heels": ("Heels", 180),
    "Flats": ("Flats", 110),
    "Sandals": ("Sandals", 100),
    "Sports Sandals": ("Sports sandals", 30),
    "Flip Flops": ("Flip flops", 60),
    # Accessories
    "Watches": ("Watches", 220),
    "Handbags": ("Handbags", 200),
    "Clutches": ("Clutches", 70),
    "Backpacks": ("Backpacks", 70),
    "Laptop Bag": ("Laptop bags", 30),
    "Duffel Bag": ("Duffel bags", 30),
    "Messenger Bag": ("Messenger bags", 20),
    "Sunglasses": ("Sunglasses", 100),
    "Wallets": ("Wallets", 90),
    "Belts": ("Belts", 70),
    "Caps": ("Caps", 40),
    "Ties": ("Ties", 40),
    "Cufflinks": ("Cufflinks", 30),
    "Scarves": ("Scarves", 40),
    "Stoles": ("Stoles", 40),
    "Mufflers": ("Mufflers", 15),
    "Earrings": ("Earrings", 120),
    "Pendant": ("Pendants", 50),
    "Necklace and Chains": ("Necklaces & chains", 50),
    "Ring": ("Rings", 40),
    "Bangle": ("Bangles", 40),
    "Bracelet": ("Bracelets", 30),
    "Jewellery Set": ("Jewellery sets", 40),
    "Accessory Gift Set": ("Gift sets", 40),
    # Fragrance
    "Perfume and Body Mist": ("Perfumes", 80),
    "Fragrance Gift Set": ("Fragrance gift sets", 30),
}
KIDS_CAP = 30
#: The whole store at about three quarters of the caps above: a rich listing,
#: an index the page and the brain load in one go (about 1.5 MB, 200 KB gzipped).
CAP_SCALE = 0.75
MIN_PRICE = 149

#: How a type is sized: letter, waist, footwear (UK), or one size.
ALPHA_TYPES = {
    "Tshirts", "Shirts", "Tops", "Kurtas", "Kurtis", "Tunics", "Sweatshirts", "Sweaters",
    "Jackets", "Rain Jacket", "Waistcoat", "Dresses", "Jumpsuit", "Kurta Sets", "Shorts",
    "Track Pants", "Skirts", "Leggings", "Capris", "Jeggings", "Patiala", "Salwar", "Churidar",
}  # fmt: skip
WAIST_TYPES = {"Jeans", "Trousers"}
FOOT_TYPES = {
    "Casual Shoes", "Sports Shoes", "Formal Shoes", "Heels", "Flats", "Sandals",
    "Sports Sandals", "Flip Flops",
}  # fmt: skip

#: Size charts (data/store.json `size_charts`) by article type and gender.
TOPS = {
    "Tshirts", "Shirts", "Tops", "Kurtas", "Kurtis", "Tunics", "Sweatshirts", "Sweaters",
    "Jackets", "Rain Jacket", "Waistcoat", "Dresses", "Jumpsuit", "Kurta Sets",
}  # fmt: skip


def chart_of(article: str, gender: str) -> str | None:
    kid = gender in ("boys", "girls")
    if kid and (article in ALPHA_TYPES or article in WAIST_TYPES):
        return "kids"
    if article in FOOT_TYPES:
        return "footwear-women" if gender == "women" else "footwear-men"
    if article in WAIST_TYPES or article in {"Shorts", "Track Pants", "Capris"}:
        return "bottoms-women" if gender == "women" else "bottoms-men"
    if article in {"Skirts", "Leggings", "Jeggings", "Patiala", "Salwar", "Churidar"}:
        return "bottoms-women"
    if article in TOPS:
        return "tops-women" if gender == "women" else "tops-men"
    return None


# ─── Departments: the mega menu ───────────────────────────────────────────────

#: department → [(section label, [article types])]. Gender filters apply per department.
DEPARTMENTS: list[dict[str, Any]] = [
    {
        "id": "men",
        "label": "Men",
        "genders": ["men", "unisex"],
        "sections": [
            ("Topwear", ["Tshirts", "Shirts", "Sweatshirts", "Sweaters", "Jackets", "Rain Jacket"]),
            ("Bottomwear", ["Jeans", "Trousers", "Shorts", "Track Pants"]),
            ("Ethnic wear", ["Kurtas", "Waistcoat"]),
            (
                "Footwear",
                [
                    "Casual Shoes",
                    "Sports Shoes",
                    "Formal Shoes",
                    "Sandals",
                    "Sports Sandals",
                    "Flip Flops",
                ],
            ),
            (
                "Accessories",
                [
                    "Watches",
                    "Wallets",
                    "Belts",
                    "Sunglasses",
                    "Caps",
                    "Ties",
                    "Cufflinks",
                    "Backpacks",
                    "Laptop Bag",
                    "Duffel Bag",
                    "Messenger Bag",
                    "Mufflers",
                    "Accessory Gift Set",
                ],
            ),
            ("Fragrance", ["Perfume and Body Mist", "Fragrance Gift Set"]),
        ],
    },
    {
        "id": "women",
        "label": "Women",
        "genders": ["women", "unisex"],
        "sections": [
            (
                "Ethnic wear",
                [
                    "Kurtas",
                    "Kurtis",
                    "Kurta Sets",
                    "Sarees",
                    "Dupatta",
                    "Salwar",
                    "Churidar",
                    "Patiala",
                    "Leggings",
                ],
            ),
            (
                "Western wear",
                [
                    "Tops",
                    "Dresses",
                    "Tunics",
                    "Tshirts",
                    "Shirts",
                    "Jumpsuit",
                    "Jeans",
                    "Jeggings",
                    "Trousers",
                    "Skirts",
                    "Capris",
                    "Shorts",
                    "Sweaters",
                    "Sweatshirts",
                    "Jackets",
                ],
            ),
            (
                "Footwear",
                ["Heels", "Flats", "Casual Shoes", "Sports Shoes", "Sandals", "Flip Flops"],
            ),
            ("Bags", ["Handbags", "Clutches", "Backpacks", "Laptop Bag"]),
            (
                "Jewellery",
                [
                    "Earrings",
                    "Pendant",
                    "Necklace and Chains",
                    "Bangle",
                    "Bracelet",
                    "Ring",
                    "Jewellery Set",
                ],
            ),
            (
                "Accessories",
                [
                    "Watches",
                    "Sunglasses",
                    "Wallets",
                    "Belts",
                    "Scarves",
                    "Stoles",
                    "Accessory Gift Set",
                ],
            ),
            ("Fragrance", ["Perfume and Body Mist", "Fragrance Gift Set"]),
        ],
    },
    {
        "id": "kids",
        "label": "Kids",
        "genders": ["boys", "girls"],
        "sections": [
            (
                "Boys clothing",
                ["Tshirts", "Shirts", "Shorts", "Jeans", "Track Pants", "Kurta Sets", "Kurtas"],
            ),
            ("Girls clothing", ["Tops", "Dresses", "Tshirts", "Skirts", "Capris", "Leggings"]),
            ("Footwear", ["Casual Shoes", "Sports Shoes", "Sandals", "Flip Flops", "Flats"]),
            ("Accessories", ["Watches", "Backpacks", "Caps"]),
        ],
    },
    {
        "id": "ethnic",
        "label": "Ethnic",
        "genders": ["men", "women", "unisex", "boys", "girls"],
        "usage": "Ethnic",
        "sections": [
            (
                "For her",
                [
                    "Kurtas",
                    "Kurtis",
                    "Kurta Sets",
                    "Sarees",
                    "Dupatta",
                    "Salwar",
                    "Churidar",
                    "Patiala",
                ],
            ),
            ("For him", ["Kurtas", "Waistcoat"]),
            (
                "Finish the look",
                ["Earrings", "Bangle", "Jewellery Set", "Clutches", "Heels", "Flats", "Stoles"],
            ),
        ],
    },
    {
        "id": "footwear",
        "label": "Footwear",
        "genders": ["men", "women", "unisex", "boys", "girls"],
        "sections": [
            ("Shoes", ["Casual Shoes", "Sports Shoes", "Formal Shoes"]),
            ("Heels and flats", ["Heels", "Flats"]),
            ("Sandals and flip flops", ["Sandals", "Sports Sandals", "Flip Flops"]),
        ],
    },
    {
        "id": "accessories",
        "label": "Accessories",
        "genders": ["men", "women", "unisex", "boys", "girls"],
        "sections": [
            ("Watches and eyewear", ["Watches", "Sunglasses"]),
            (
                "Bags",
                ["Handbags", "Clutches", "Backpacks", "Laptop Bag", "Duffel Bag", "Messenger Bag"],
            ),
            ("Small leather goods", ["Wallets", "Belts"]),
            (
                "Jewellery",
                [
                    "Earrings",
                    "Pendant",
                    "Necklace and Chains",
                    "Bangle",
                    "Bracelet",
                    "Ring",
                    "Jewellery Set",
                    "Cufflinks",
                ],
            ),
            ("More", ["Caps", "Ties", "Scarves", "Stoles", "Mufflers", "Accessory Gift Set"]),
            ("Fragrance", ["Perfume and Body Mist", "Fragrance Gift Set"]),
        ],
    },
]

#: Colour name → swatch hex, for the colour filter.
COLOURS: dict[str, str] = {
    "Black": "#1b1b1b", "White": "#f6f6f2", "Blue": "#2f5fb3", "Navy Blue": "#1f2f56",
    "Grey": "#8a8d91", "Red": "#c0292f", "Green": "#3c7a46", "Pink": "#ee8fb0",
    "Brown": "#7b4b2a", "Purple": "#6c3c8f", "Yellow": "#efc533", "Beige": "#dcc9a6",
    "Silver": "#c4c7cc", "Gold": "#c99a2e", "Orange": "#ea7a2b", "Maroon": "#7a1f2b",
    "Olive": "#6b6a2c", "Cream": "#f2e8cf", "Off White": "#efebe0", "Multi": "conic",
    "Teal": "#227c7c", "Magenta": "#b3247a", "Charcoal": "#3d3f43", "Khaki": "#b8a66f",
    "Peach": "#f3b393", "Turquoise Blue": "#2fb5b8", "Lavender": "#b9a6dc",
    "Mustard": "#cf9d22", "Copper": "#b16a3b", "Steel": "#7f8a96", "Rust": "#a94a25",
    "Coffee Brown": "#5a3a24", "Tan": "#c39a6b", "Sea Green": "#3a9a7a",
    "Burgundy": "#6d1a2e", "Grey Melange": "#a3a5a8", "Bronze": "#9b6a2f",
    "Skin": "#e6c2a3", "Nude": "#d9b39a", "Mauve": "#a77d9a", "Lime Green": "#8fc23b",
    "Rose": "#d6697c", "Metallic": "#a9a9ad", "Taupe": "#8b7d6b", "Fluorescent Green": "#5ce03a",
    "Mushroom Brown": "#98806a", "Lemon Yellow": "#f3e64a",
}  # fmt: skip

_COLOUR_WORDS = {w.lower() for c in COLOURS for w in c.split()} | {
    "melange", "dark", "light", "navy", "multi", "coloured", "multicoloured", "off",
}  # fmt: skip
_GENDER_WORDS = {"men", "mens", "men's", "women", "womens", "women's", "boys", "girls", "kids",
                 "unisex", "boy", "girl", "woman", "man"}  # fmt: skip

# ─── Helpers ──────────────────────────────────────────────────────────────────


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _hash(*parts: object) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:12], 16)


ALPHA = ["XS", "S", "M", "L", "XL", "XXL", "3XL", "4XL"]
_ALPHA_ALIASES = {"XXXL": "3XL", "2XL": "XXL", "XXXXL": "4XL", "3XS": "XS", "XXS": "XS"}
_WOMEN_NUM = {
    30: "XS",
    32: "XS",
    34: "S",
    36: "M",
    38: "L",
    40: "XL",
    42: "XXL",
    44: "3XL",
    46: "4XL",
}
_MEN_CHEST = {
    36: "S",
    37: "S",
    38: "M",
    39: "M",
    40: "L",
    42: "XL",
    44: "XXL",
    46: "3XL",
    48: "4XL",
}
_SHIRT_COLLAR = {38: "S", 39: "M", 40: "L", 42: "XL", 44: "XXL", 46: "3XL"}
_AGE = re.compile(r"^(\d+)(?:-(\d+))?\s*([YM])$", re.I)


def _age_label(value: str) -> str | None:
    m = _AGE.match(value.replace(" ", "").upper())
    if not m:
        return None
    a, b, unit = m.group(1), m.group(2), m.group(3).upper()
    return f"{a}-{b}{unit}" if b else f"{a}{unit}"


def _age_key(label: str) -> float:
    m = _AGE.match(label)
    if not m:
        return 99.0
    n = float(m.group(2) or m.group(1))
    return n / 12 if m.group(3).upper() == "M" else n


def normal_size(raw: str, article: str, gender: str) -> tuple[str, str] | None:
    """(scale, label) for one dataset size; None to drop it (junk)."""
    v = raw.strip().upper().replace(" ", "")
    if not v:
        return None
    if v in ("ONESIZE", "FREESIZE", "FREE", "NA", "STD", "STANDARD"):
        return ("one", "Onesize")
    if gender in ("boys", "girls") and (age := _age_label(v)):
        return ("age", age)
    if article in FOOT_TYPES:
        m = re.match(r"^(UK|EURO|EU|US)?(\d+(?:\.5)?)$", v)
        if not m:
            return None
        system, n = m.group(1) or "UK", float(m.group(2))
        if system in ("EURO", "EU"):
            n = n - (33 if gender in ("women", "girls") else 34)
        elif system == "US":
            n = n - (2 if gender in ("women", "girls") else 1)
        n = int(n)
        return ("uk", f"UK {n}") if 1 <= n <= 13 else None
    if article in WAIST_TYPES:
        if v.isdigit() and 24 <= int(v) <= 46:
            return ("waist", v)
        v = _ALPHA_ALIASES.get(v, v)
        return ("alpha", v) if v in ALPHA else None
    if article in ALPHA_TYPES:
        v = _ALPHA_ALIASES.get(v, v)
        if v in ALPHA:
            return ("alpha", v)
        if v.isdigit():
            n = int(v)
            if (
                article in WAIST_TYPES | {"Shorts", "Track Pants", "Capris", "Leggings"}
                and 26 <= n <= 44
            ):
                return ("waist", v)
            table = (
                _SHIRT_COLLAR
                if article == "Shirts" and gender == "men"
                else _WOMEN_NUM
                if gender in ("women", "girls")
                else _MEN_CHEST
            )
            return ("alpha", table[n]) if n in table else None
        return None
    return ("one", "Onesize")


def size_order(scale: str, label: str) -> float:
    if scale == "alpha":
        return ALPHA.index(label) if label in ALPHA else 50
    if scale in ("waist",):
        return float(label)
    if scale == "uk":
        return float(label.split()[1])
    if scale == "age":
        return _age_key(label)
    return 0


def stock_of(pid: int, label: str, dataset_available: bool) -> int:
    """Fashio's units of one size: deterministic from the id and the size."""
    if dataset_available:
        return 12
    h = _hash("stock", pid, label) % 100
    if h < 14:
        return 0
    if h < 26:
        return 1 + h % 3  # "only 1-3 left"
    return 6 + h % 20


_TAG = re.compile(r"<[^>]+>")
_HEADS = re.compile(r"<(?:strong|b)>\s*([^<]{2,40}?)\s*</(?:strong|b)>\s*(?:<br\s*/?>)?", re.I)


def _plain(fragment: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.I)
    text = re.sub(r"</p>|</li>", "\n", text, flags=re.I)
    text = html.unescape(_TAG.sub("", text))
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def description_sections(raw: str) -> list[dict[str, str]]:
    """The dataset's HTML description as [{heading, text}] sections (plain text)."""
    if not raw:
        return []
    parts = _HEADS.split(raw)
    out: list[dict[str, str]] = []
    lead = _plain(parts[0])
    if lead:
        out.append({"heading": "About", "text": lead})
    for i in range(1, len(parts) - 1, 2):
        head = html.unescape(parts[i]).strip().rstrip(":")
        body = _plain(parts[i + 1])
        if body:
            out.append({"heading": head[:1].upper() + head[1:], "text": body})
    return out[:8]


def _first_sentence(text: str, limit: int = 180) -> str:
    one = re.split(r"(?<=[.!?])\s", text.replace("\n", " "), maxsplit=1)[0].strip()
    return one if len(one) <= limit else one[: limit - 1].rsplit(" ", 1)[0] + "…"


_MODEL = re.compile(r"(?:model|Model)[^\n]*?(?:size|Size)\s+([A-Z0-9]{1,4})[^\n]*")

#: Attributes the index carries (the brain answers from these); details carry all.
KEY_ATTRS = ["Fit", "Pattern", "Fabric", "Sleeve Length", "Neck", "Length", "Shape", "Occasion",
             "Top Fabric", "Ornamentation", "Saree Fabric", "Material", "Type", "Closure",
             "Strap Material", "Dial Shape", "Heel Height", "Heel Type", "Waist Rise"]  # fmt: skip


def name_stem(name: str, brand: str) -> str:
    words = [w for w in re.split(r"\s+", name) if w]
    bwords = {w.lower() for w in brand.split()}
    keep = [
        w
        for w in words
        if w.lower() not in bwords
        and w.lower().strip("'s") not in _GENDER_WORDS
        and w.lower() not in _GENDER_WORDS
        and w.lower() not in _COLOUR_WORDS
    ]
    return " ".join(keep).lower()


# ─── Build ────────────────────────────────────────────────────────────────────


def load_rows(z: zipfile.ZipFile) -> list[dict[str, str]]:
    raw = z.read(f"{ROOT}/styles.csv").decode("utf-8", "replace")
    return list(csv.DictReader(io.StringIO(raw)))


def build(zip_path: Path, out: Path) -> dict[str, Any]:
    z = zipfile.ZipFile(zip_path)
    names = set(z.namelist())
    rows = load_rows(z)
    cands: dict[int, dict[str, Any]] = {}
    for r in rows:
        article = r["articleType"]
        if article not in CAPS:
            continue
        pid = int(r["id"])
        jname = f"{ROOT}/styles/{pid}.json"
        if jname not in names or f"{ROOT}/images/{pid}.jpg" not in names:
            continue
        d = json.loads(z.read(jname))["data"]
        name = (d.get("productDisplayName") or "").strip()
        price = int(d.get("price") or 0)
        if not name or price < MIN_PRICE or "free" in name.lower():
            continue
        cands[pid] = d
    print(f"candidates: {len(cands)}")

    def gender_of(d: dict[str, Any]) -> str:
        return str(d.get("gender") or "Unisex").lower()

    # Colour-variant groups over every candidate.
    by_key: dict[tuple[Any, ...], list[int]] = defaultdict(list)
    for pid, d in cands.items():
        article = d["articleType"]["typeName"]
        stem = name_stem(d["productDisplayName"], d.get("brandName") or "")
        generic = {w.lower() for w in re.split(r"[\s-]+", article + " " + CAPS[article][0])} | {
            "t-shirt",
            "tshirt",
            "shirt",
            "kurta",
            "shoes",
            "watch",
            "handbag",
            "sunglasses",
            "wallet",
            "belt",
            "printed",
            "solid",
            "striped",
            "checked",
            "casual",
            "sports",
            "formal",
            "polo",
        }
        meaningful = [w for w in re.split(r"[\s-]+", stem) if w and w not in generic]
        if not meaningful:
            continue
        key = (
            d.get("brandName"),
            gender_of(d),
            article,
            int(d["price"]),
            stem,
        )
        by_key[key].append(pid)
    group_of: dict[int, list[int]] = {}
    for members in by_key.values():
        colours = {cands[m].get("baseColour") for m in members}
        if len(members) >= 2 and len(colours) >= 2:
            # One per colour, at most six.
            seen: dict[str, int] = {}
            for m in sorted(members):
                seen.setdefault(str(cands[m].get("baseColour")), m)
            picked = sorted(seen.values())[:6]
            if len(picked) >= 2:
                for m in picked:
                    group_of[m] = picked

    def score(pid: int) -> tuple[Any, ...]:
        d = cands[pid]
        desc = bool(((d.get("productDescriptors") or {}).get("description") or {}).get("value"))
        attrs = len(d.get("articleAttributes") or {})
        disc = int(d.get("discountedPrice") or d["price"]) < int(d["price"])
        year = int(d.get("year") or 0)
        return (
            -int(desc),
            -int(pid in group_of),
            -min(attrs, 8),
            -int(disc),
            -year,
            _hash("pick", pid),
        )

    # Round-robin across brands within each (type, adult|kids) bucket.
    buckets: dict[tuple[str, bool], list[int]] = defaultdict(list)
    for pid, d in cands.items():
        buckets[(d["articleType"]["typeName"], gender_of(d) in ("boys", "girls"))].append(pid)
    chosen: set[int] = set()
    for (article, kids), pids in sorted(buckets.items()):
        cap = KIDS_CAP if kids else round(CAPS[article][1] * CAP_SCALE)
        by_brand: dict[str, list[int]] = defaultdict(list)
        for pid in sorted(pids, key=score):
            by_brand[str(cands[pid].get("brandName"))].append(pid)
        queues = sorted(by_brand.values(), key=lambda q: score(q[0]))
        taken = 0
        while taken < cap and any(queues):
            for q in queues:
                if not q or taken >= cap:
                    continue
                pid = q.pop(0)
                if pid in chosen:
                    continue
                for m in group_of.get(pid, [pid]):
                    if m not in chosen:
                        chosen.add(m)
                        taken += 1
            queues = [q for q in queues if q]
    print(f"chosen: {len(chosen)}")

    # Rows.
    products: list[dict[str, Any]] = []
    details: dict[int, dict[str, Any]] = {}
    for pid in sorted(chosen):
        d = cands[pid]
        article = d["articleType"]["typeName"]
        gender = gender_of(d)
        sizes: list[dict[str, Any]] = []
        seen_labels: set[str] = set()
        for o in d.get("styleOptions") or []:
            norm = normal_size(str(o.get("value") or ""), article, gender)
            if norm is None or norm[1] in seen_labels:
                continue
            seen_labels.add(norm[1])
            sizes.append(
                {
                    "scale": norm[0],
                    "label": norm[1],
                    "stock": stock_of(pid, norm[1], bool(o.get("available"))),
                }
            )
        if not sizes:
            sizes = [{"scale": "one", "label": "Onesize", "stock": stock_of(pid, "Onesize", False)}]
        scales = {s["scale"] for s in sizes}
        if len(scales) > 1:  # mixed scales: keep the most common one
            top = max(scales, key=lambda sc: sum(1 for s in sizes if s["scale"] == sc))
            sizes = [s for s in sizes if s["scale"] == top]
        sizes.sort(key=lambda s: size_order(s["scale"], s["label"]))
        if all(s["stock"] == 0 for s in sizes):
            sizes[len(sizes) // 2]["stock"] = 4
        price = int(d["price"])
        sale = int(d.get("discountedPrice") or price)
        if sale <= 0 or sale > price:
            sale = price
        attrs_all = {
            k: str(v).strip()
            for k, v in (d.get("articleAttributes") or {}).items()
            if str(v).strip() and str(v).strip().upper() != "NA" and k != "Body or Garment Size"
        }
        desc_raw = ((d.get("productDescriptors") or {}).get("description") or {}).get("value") or ""
        sections = description_sections(desc_raw)
        about = next(
            (s["text"] for s in sections if s["heading"].lower() in ("about", "composition")),
            "",
        )
        model_m = _MODEL.search(_plain(desc_raw))
        usage = (d.get("usage") or "Casual").strip() or "Casual"
        if usage in ("NA", "Home"):
            usage = "Casual"
        row: dict[str, Any] = {
            "id": pid,
            "name": d["productDisplayName"].strip(),
            "brand": (d.get("brandName") or "").strip(),
            "gender": gender,
            "type": slug(article),
            "colour": (d.get("baseColour") or "").strip() or "Multi",
            "price": sale,
            "mrp": price,
            "usage": usage,
            "season": (d.get("season") or "").strip() or "Summer",
            "year": int(d.get("year") or 0),
            "sizes": [[s["label"], s["stock"]] for s in sizes],
            "scale": sizes[0]["scale"],
        }
        if pid in group_of:
            row["group"] = min(group_of[pid])
        key_attrs = {k: attrs_all[k] for k in KEY_ATTRS if k in attrs_all}
        if key_attrs:
            row["attrs"] = key_attrs
        if model_m:
            row["model"] = re.sub(r"\s+", " ", model_m.group(0)).strip()[:120]
        products.append(row)
        details[pid] = {
            "id": pid,
            "article_number": d.get("articleNumber") or "",
            "variant_name": d.get("variantName") or "",
            "age_group": d.get("ageGroup") or "",
            "colours": [c for c in (d.get("colour1"), d.get("colour2")) if c and c != "NA"],
            "display_categories": d.get("displayCategories") or "",
            "attributes": attrs_all,
            "description": sections,
            **({"blurb": _first_sentence(about)} if about else {}),
        }

    # Similar items: same type and gender, nearest price, other colours first.
    by_type: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for p in products:
        by_type[(p["type"], p["gender"])].append(p)
    for p in products:
        pool = [q for q in by_type[(p["type"], p["gender"])] if q["id"] != p["id"]]
        if p.get("group"):
            pool = [q for q in pool if q.get("group") != p["group"]]
        pool.sort(key=lambda q: (abs(q["price"] - p["price"]), q["id"]))
        details[p["id"]]["similar"] = [q["id"] for q in pool[:12]]
        if p.get("group"):
            details[p["id"]]["variants"] = [
                q["id"]
                for q in products
                if q.get("group") == p["group"]  # small: groups are few
            ]

    # Popularity: the store's default order ("Popular"), best first by the same
    # score the curation picked with. 1 is the top.
    by_id = {p["id"]: p for p in products}
    for n, pid in enumerate(sorted(chosen, key=score), 1):
        by_id[pid]["rank"] = n

    used_types = {p["type"] for p in products}
    types: dict[str, dict[str, Any]] = {
        slug(a): {"label": label, "article": a, "chart": None}
        for a, (label, _) in CAPS.items()
        if slug(a) in used_types
    }
    charts: dict[str, dict[str, str]] = defaultdict(dict)
    for p in products:
        c = chart_of(str(types[p["type"]]["article"]), p["gender"])
        if c:
            charts[p["type"]][p["gender"]] = c
    for t, by_gender in charts.items():
        types[t]["chart"] = by_gender

    departments = []
    for dep in DEPARTMENTS:
        sections = []
        for label, arts in dep["sections"]:
            ids = [slug(a) for a in arts if slug(a) in used_types]
            # A type shows in a department only when it has products for it.
            ids = [
                t
                for t in ids
                if any(
                    p["type"] == t
                    and p["gender"] in dep["genders"]
                    and (not dep.get("usage") or p["usage"] == dep["usage"])
                    for p in products
                )
            ]
            if ids:
                sections.append({"label": label, "types": ids})
        departments.append(
            {
                "id": dep["id"],
                "label": dep["label"],
                "genders": dep["genders"],
                **({"usage": dep["usage"]} if dep.get("usage") else {}),
                "sections": sections,
            }
        )

    brands = sorted({p["brand"] for p in products if p["brand"]})
    colours = sorted({p["colour"] for p in products})
    index = {
        "version": VERSION,
        "credit": CREDIT,
        "count": len(products),
        "types": types,
        "departments": departments,
        "brands": brands,
        "colours": {c: COLOURS.get(c, "#9a9a9a") for c in colours},
        "products": products,
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "p").mkdir(exist_ok=True)
    for pid, det in details.items():
        (out / "p" / f"{pid}.json").write_text(
            json.dumps(det, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
    text = json.dumps(index, ensure_ascii=False, separators=(",", ":"))
    # One product a line: diffable, still compact.
    text = text.replace(',{"id":', ',\n{"id":')
    INDEX.write_text(text + "\n", encoding="utf-8")
    (out / "index.json").write_text(text + "\n", encoding="utf-8")
    return index


def upload(out: Path) -> None:
    dest = f"{BUCKET}/catalog/{VERSION}"
    common = ["gcloud", "storage", "cp", "--project=voqal-cloud-prod"]
    subprocess.run(
        [
            *common,
            "--gzip-local-all",
            "--cache-control=public, max-age=3600",
            "--content-type=application/json",
            str(out / "index.json"),
            f"{dest}/index.json",
        ],
        check=True,
    )
    subprocess.run(
        [
            *common,
            "--recursive",
            "--gzip-local-all",
            "--cache-control=public, max-age=3600",
            "--content-type=application/json",
            str(out / "p"),
            f"{dest}/",
        ],
        check=True,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    ap.add_argument("--zip", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--upload", action="store_true")
    args = ap.parse_args()
    index = build(args.zip.expanduser(), args.out)
    by_type: dict[str, int] = defaultdict(int)
    for p in index["products"]:
        by_type[p["type"]] += 1
    groups = {p["group"] for p in index["products"] if p.get("group")}
    print(
        f"{index['count']} products, {len(index['types'])} types, {len(index['brands'])} brands, "
        f"{len(groups)} colour groups; index {INDEX.stat().st_size // 1024} KB"
    )
    for t, n in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"  {n:4} {t}")
    if args.upload:
        upload(args.out)


if __name__ == "__main__":
    main()
