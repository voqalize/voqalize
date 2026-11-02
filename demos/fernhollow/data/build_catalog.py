"""Normalize the Fernhollow demo catalog.

Source: a subset of mock.shop's `home-large-catalog` (published there as "Havenly Nest"),
picked by havenly-data/scripts/select_subset.py (up to 25 varied products per category).
This script only reshapes and renames; it never invents product facts.

    python3 -I demos/fernhollow/data/build_catalog.py ~/Desktop/voqalize/havenly-data/catalog/products.json
"""
import html, json, pathlib, re, sys

SRC = pathlib.Path(sys.argv[1]).expanduser()
OUT = pathlib.Path(__file__).with_name("catalog.json")

ROOMS = {
    "living": ["Sofas", "Coffee Tables", "Entertainment Centers & TV Stands", "Rugs", "Throw Pillows",
               "Floor Lamps", "Artwork", "Mirrors", "Clocks"],
    "dining": ["Dining Tables", "Dining Chairs", "Chandeliers", "Dinnerware", "Serveware", "Barware"],
    "bedroom": ["Beds & Bed Frames", "Bed Sheets", "Quilts & Comforters", "Table Lamps", "Curtains & Drapes"],
    "home-office": ["Desks", "Office Chairs", "Shelving"],
    "bath": ["Bath Towels & Washcloths", "Bath Mats & Rugs"],
    "kitchen": ["Cookware", "Food Storage"],
    "decor": ["Vases", "Household Storage Baskets", "Artificial Flora", "Candle Holders", "Picture Frames"],
}
ROOM_OF = {c: r for r, cs in ROOMS.items() for c in cs}
# Real trademarks and non-English handles in the source, renamed for a fictional store.
RENAME = {
    "fauteuil-executif-eames-soft-pad-cuir-brun": ("soft-pad-executive-chair-brown-leather",
                                                   "Soft Pad Executive Chair in Brown Leather"),
}
slug = lambda s: re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
def split_html(h):
    """The source HTML as an intro paragraph plus its bullet points, text only."""
    text = lambda x: html.unescape(re.sub(r"<[^>]+>", "", x)).strip()
    paras = [text(x) for x in re.findall(r"<p[^>]*>(.*?)</p>", h, re.S)]
    bullets = [text(x) for x in re.findall(r"<li[^>]*>(.*?)</li>", h, re.S)]
    return " ".join(x for x in paras if x), [b for b in bullets if b]

money = lambda m: round(float(m["amount"]), 2) if m else None

products = []
for p in json.load(open(SRC)):
    handle, title = RENAME.get(p["handle"], (p["handle"], p["title"]))
    cat = p["_category"]
    variants = [{
        "id": v["id"].rsplit("/", 1)[-1],
        "title": v["title"],
        "options": {o["name"]: o["value"] for o in v["selectedOptions"]},
        "price": money(v["price"]),
        "compareAtPrice": money(v["compareAtPrice"]),
        "image": (v.get("image") or {}).get("url"),
    } for v in p["variants"]["nodes"]]
    prices = [v["price"] for v in variants]
    products.append({
        "id": handle,
        "sourceHandle": p["handle"],
        "title": title[:1].upper() + title[1:],
        "category": cat,
        "categorySlug": slug(cat),
        "room": ROOM_OF[cat],
        "collections": [c["handle"] for c in p["collections"]["nodes"]],
        "description": p["description"].strip(),
        "intro": split_html(p["descriptionHtml"])[0] or p["description"].strip(),
        "highlights": split_html(p["descriptionHtml"])[1],
        "tags": p["tags"],
        "priceMin": min(prices),
        "priceMax": max(prices),
        "onSale": any(v["compareAtPrice"] and v["compareAtPrice"] > v["price"] for v in variants),
        "options": [{"name": o["name"], "values": [x["name"] for x in o["optionValues"]]} for o in p["options"]],
        "variants": variants,
        "images": [{"src": i["url"], "alt": i["altText"] or title, "width": i["width"], "height": i["height"],
                    "file": f"{handle}/{n}"} for n, i in enumerate(p["images"]["nodes"])],
    })

categories = sorted({(p["category"], p["categorySlug"], p["room"]) for p in products})
OUT.write_text(json.dumps({
    "store": "Fernhollow",
    "source": "mock.shop home-large-catalog (Havenly Nest), subset; see demos/fernhollow/data/README.md",
    "rooms": list(ROOMS),
    "categories": [{"name": n, "slug": s, "room": r, "count": sum(p["category"] == n for p in products)}
                   for n, s, r in categories],
    "products": products,
}, indent=1, ensure_ascii=False))
print(len(products), "products,", len(categories), "categories ->", OUT)
