"""Normalize the Fernhollow demo catalog.

Source: a subset of mock.shop's `home-large-catalog` (published there as "Havenly Nest"),
picked by havenly-data/scripts/select_subset.py (up to 25 varied products per category).
This script only reshapes and renames; it never invents product facts.

    python3 -I demos/fernhollow/data/build_catalog.py ~/Desktop/voqalize/havenly-data/catalog/products.json
"""

from __future__ import annotations

import html
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, cast

OUT = Path(__file__).with_name("catalog.json")

ROOMS: dict[str, list[str]] = {
    "living": [
        "Sofas",
        "Coffee Tables",
        "Entertainment Centers & TV Stands",
        "Rugs",
        "Throw Pillows",
        "Floor Lamps",
        "Artwork",
        "Mirrors",
        "Clocks",
    ],
    "dining": [
        "Dining Tables",
        "Dining Chairs",
        "Chandeliers",
        "Dinnerware",
        "Serveware",
        "Barware",
    ],
    "bedroom": [
        "Beds & Bed Frames",
        "Bed Sheets",
        "Quilts & Comforters",
        "Table Lamps",
        "Curtains & Drapes",
    ],
    "home-office": ["Desks", "Office Chairs", "Shelving"],
    "bath": ["Bath Towels & Washcloths", "Bath Mats & Rugs"],
    "kitchen": ["Cookware", "Food Storage"],
    "decor": [
        "Vases",
        "Household Storage Baskets",
        "Artificial Flora",
        "Candle Holders",
        "Picture Frames",
    ],
}
ROOM_OF = {c: r for r, cs in ROOMS.items() for c in cs}

# Real trademarks in the source, renamed for a fictional store.
RENAME = {
    "fauteuil-executif-eames-soft-pad-cuir-brun": (
        "soft-pad-executive-chair-brown-leather",
        "Soft Pad Executive Chair in Brown Leather",
    ),
}

# The source files some products in the wrong category. Where the right one is plain
# (a throw blanket under Clocks, a carafe under Table Lamps) the product is re-filed;
# what is not furniture or homeware at all (a digital download, UI "grid modules")
# is dropped. No product fact changes either way.
REFILE = {
    "linen-throw-blanket": "Quilts & Comforters",
    "linen-throw-blanket-in-sandstone": "Quilts & Comforters",
    "linen-throw-with-fringe-edges": "Quilts & Comforters",
    "wool-throw-blanket-in-muted-ochre-plaid": "Quilts & Comforters",
    "muted-taupe-bedsheet": "Bed Sheets",
    "natural-linen-duvet-set": "Bed Sheets",
    "sand-linen-sofa-with-deep-seat": "Sofas",
    "polished-stainless-steel-cutlery-set": "Serveware",
    "linen-cotton-blend-napkins-set-of-four-undyed": "Serveware",
    "glass-carafe-with-walnut-lid": "Barware",
    "twin-plush-mattress-with-multi-layer-design": "Beds & Bed Frames",
}
NOT_HOMEWARE = frozenset(
    {
        "digital-downloadmuted-riverbank-reflections",
        "product-grid-module-with-subtle-animations",
        "sanded-taupe-product-grid-module",
        "borosilicate-glass-water-bottle-with-sleeve",
        "linen-altar-cloth-handwoven-in-natural-dyes",
        "handwoven-linen-textile",
    }
)

Json = dict[str, Any]


def slug(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-")


def money(m: Json | None) -> float | None:
    return round(float(m["amount"]), 2) if m else None


def plain(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def split_html(source: str) -> tuple[str, list[str]]:
    """The source HTML as an intro paragraph plus its bullet points, text only."""
    paras = [plain(x) for x in re.findall(r"<p[^>]*>(.*?)</p>", source, re.S)]
    bullets = [plain(x) for x in re.findall(r"<li[^>]*>(.*?)</li>", source, re.S)]
    return " ".join(x for x in paras if x), [b for b in bullets if b]


def variant(v: Json) -> Json:
    return {
        "id": str(v["id"]).rsplit("/", 1)[-1],
        "title": v["title"],
        "options": {o["name"]: o["value"] for o in v["selectedOptions"]},
        "price": money(v["price"]),
        "compareAtPrice": money(v["compareAtPrice"]),
        "image": (v.get("image") or {}).get("url"),
    }


def product(p: Json) -> Json:
    _, title = RENAME.get(p["handle"], (p["handle"], p["title"]))
    cat: str = p["_category"]
    variants = [variant(v) for v in p["variants"]["nodes"]]
    prices = [cast(float, v["price"]) for v in variants]
    intro, highlights = split_html(p["descriptionHtml"])
    description = str(p["description"]).strip()
    return {
        "id": slug(title),
        "sourceHandle": p["handle"],
        "title": title[:1].upper() + title[1:],
        "category": cat,
        "categorySlug": slug(cat),
        "room": ROOM_OF[cat],
        "collections": [c["handle"] for c in p["collections"]["nodes"]],
        "description": description,
        "intro": intro or description,
        "highlights": highlights,
        "tags": p["tags"],
        "priceMin": min(prices),
        "priceMax": max(prices),
        "onSale": any(v["compareAtPrice"] and v["compareAtPrice"] > v["price"] for v in variants),
        "options": [
            {"name": o["name"], "values": [x["name"] for x in o["optionValues"]]}
            for o in p["options"]
        ],
        "variants": variants,
        "images": [
            {
                "src": i["url"],
                "alt": i["altText"] or title,
                "width": i["width"],
                "height": i["height"],
                "file": f"{slug(title)}/{n}",
            }
            for n, i in enumerate(p["images"]["nodes"])
        ],
    }


def main(src: Path) -> None:
    raw = cast(list[Json], json.loads(src.read_text()))
    products = [product(p) for p in raw]
    # Ids are the English title's slug (the source mixes Spanish, German, French and
    # Dutch handles); a repeated title gets -2, -3 in source order.
    seen: dict[str, int] = {}
    for p in products:
        base = p["id"]
        seen[base] = seen.get(base, 0) + 1
        if seen[base] > 1:
            p["id"] = f"{base}-{seen[base]}"
            for i in p["images"]:
                i["file"] = f"{p['id']}/{i['file'].rsplit('/', 1)[1]}"
    products = [p for p in products if p["id"] not in NOT_HOMEWARE]
    for p in products:
        if p["id"] in REFILE:
            p["category"] = REFILE[p["id"]]
            p["categorySlug"] = slug(p["category"])
            p["room"] = ROOM_OF[p["category"]]
    categories = sorted({(p["category"], p["categorySlug"], p["room"]) for p in products})
    OUT.write_text(
        json.dumps(
            {
                "store": "Fernhollow",
                "source": "mock.shop home-large-catalog (Havenly Nest), subset; see demos/fernhollow/data/README.md",
                "rooms": list(ROOMS),
                "categories": [
                    {
                        "name": n,
                        "slug": s,
                        "room": r,
                        "count": sum(p["category"] == n for p in products),
                    }
                    for n, s, r in categories
                ],
                "products": products,
            },
            indent=1,
            ensure_ascii=False,
        )
    )
    print(len(products), "products,", len(categories), "categories ->", OUT)


if __name__ == "__main__":
    main(Path(sys.argv[1]).expanduser())
