# pyright: basic
# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Build Cannon Home's L3 knowledge: cannonhome.cl (Magento 2.4, es-CL) as data.

The build runs offline on a dev machine; its output is committed and the brain
only ever reads the JSON (the brain never fetches cannonhome.cl). Network is
touched only by the fetching commands; every response is cached outside the
repository in ``$XDG_CACHE_HOME/voqalize-cannonhome`` (``~/.cache`` by
default), so a re-run is cheap and ``--offline`` / ``search`` never fetch.

**cannonhome.cl blocks Indian IP addresses.** Run the fetching commands through
a non-Indian connection (a VPN). A 403/405 on an HTML page, a timeout or "Not
allowed" means the connection is being blocked: stop, do not work around it.
Requests are paced to at most two a second. Nothing here logs in, submits a
form or touches the cart.

Run from ``voqalize/demos``; Playwright is not a demos dependency (``crawl``
needs it; install its Chromium once with ``playwright install chromium``)::

    uv run --with playwright python cannonhome/backend/knowledge/build.py crawl
    uv run --with playwright python cannonhome/backend/knowledge/build.py crawl --refresh
    uv run --with playwright python cannonhome/backend/knowledge/build.py crawl --only /preguntas-frecuentes
    uv run python cannonhome/backend/knowledge/build.py crawl --offline
    uv run python cannonhome/backend/knowledge/build.py catalogue
    uv run python cannonhome/backend/knowledge/build.py catalogue --refresh
    uv run python cannonhome/backend/knowledge/build.py catalogue --offline
    uv run python cannonhome/backend/knowledge/build.py maps          # L2/site-map.md, L2/catalogo.md
    uv run python cannonhome/backend/knowledge/build.py search "sabanas king 300 hilos"

``catalogue`` reads the shop through ``POST /graphql`` (``GET`` is 403 at the
edge) and the category pages' server-rendered layered navigation:

- ``L3/products.json`` — every product ``products()`` lists (it hides
  out-of-stock products, so this is the buyable catalogue on the crawl day),
  one JSON object a line inside ``[ ]``::

      {sku, name, path, brand, category, categories, type, size, color,
       material, threads, weight_gsm, attributes, summary, image, family,
       in_catalogue_at}

  ``path`` is ``/<url_key>.html``; ``category`` the product's main category as
  a name chain ("Ropa de Cama > Sábanas > Sábanas de algodón > Sábanas 2
  Plazas"); ``categories`` every category path the product is listed in;
  ``type`` the "Tipo de Producto" label; ``size`` the "Tamaño" label or null;
  ``threads`` the thread count ("hilos") as an int; ``weight_gsm`` the towel
  weight ("gramos", g/m²) as an int; ``attributes`` the "Especificaciones"
  labels the site shows (attribute label → value; options resolved to their
  labels); ``summary`` the first ≤300 characters of the description as plain
  text; ``family`` the SKU stem shared by the sizes of one line (see
  ``family_of``). **No price, discount or stock fields, ever**: those are read
  live in the browser during a call.
- ``L3/categories.json`` — the category tree as the site links it, one object a
  line: ``{id, path, name, parent, level, in_menu, products, filters,
  quick_filters, options}``. ``products`` counts the products of
  ``products.json`` in that category (GraphQL's ``product_count`` is
  inflated); ``filters`` the layered-navigation request variables in page order
  (``tamano``, ``color``, ``hilos``, ``material`` …); ``quick_filters`` the
  pills above the grid (``.qf__group[data-qf-request-var]``); ``options``
  ``{var: {label, values: [option labels]}}``. Price slider bounds are not kept.

``crawl`` renders the shop's information pages (policies, FAQ, stores, guides,
blog index and a set of guide posts, home and the top categories) in headless
Chromium and writes:

- ``L3/pages.json`` — one object a line: ``{path, url, type, title,
  description, h1, sections: [{heading, level, selector, text, items}], faqs:
  [{q, a, section}]}``; ``text`` is capped at 1500 characters.
- ``L3/site.json`` — crawl date, response headers per page type (CSP enforced,
  no Permissions-Policy), layout probes (fixed header px on desktop and mobile,
  promo bar, WhatsApp button, minicart drawer, mobile sticky add-to-cart bar)
  and the desktop navigation tree (``#ninjamenus7``).

``maps`` writes ``L2/site-map.md`` (pages, headings, FAQs, the menu) and
``L2/catalogo.md`` (per category: product types, sizes, colours, materials,
thread counts, weights, brands and counts; no prices).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import html as htmllib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
L2 = HERE / "L2"
L3 = HERE / "L3"
SITE = "https://cannonhome.cl"
#: ``https://www.cannonhome.cl`` 302-redirects to ``SITE``; only an alias.
ALIASES = ("https://www.cannonhome.cl",)
GRAPHQL = f"{SITE}/graphql"
CACHE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "voqalize-cannonhome"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)
#: Seconds between two requests (≤2 a second).
PACE = 0.55
TODAY = date.today().isoformat()
ROOT_CATEGORY = 5
#: Hidden or promotional trees: never a product's main category.
SIDE_TREES = {
    "sale",
    "marcas",
    "weekend-sale",
    "evento",
    "hoteleria",
    "plaza",
    "cyber",
    "black",
    "outlet",
}
PAGE_SIZE = 100
#: Filter groups every listing has; left out of L2/catalogo.md.
GENERIC_FILTERS = ("price", "descuento", "allowed_shipping_methods", "verificado_rating")
SUMMARY_CAP = 300
TEXT_CAP = 1500
#: Attributes never written to ``products.json``: price, discount, stock,
#: logistics, ratings and internal fields.
SKIP_ATTRS = {
    "name",
    "description",
    "short_description",
    "price",
    "special_price",
    "special_from_date",
    "special_to_date",
    "cost",
    "msrp",
    "descuento",
    "tier_price",
    "weight",
    "volumen",
    "status",
    "visibility",
    "url_key",
    "meta_title",
    "meta_keyword",
    "meta_description",
    "image",
    "small_image",
    "thumbnail",
    "swatch_image",
    "hover",
    "image_bestseller",
    "options_container",
    "msrp_display_actual_price_type",
    "tax_class_id",
    "gift_message_available",
    "gift_wrapping_available",
    "is_returnable",
    "shipping_type",
    "shipping_type_days",
    "shipping_type_de",
    "am_offer_item_condition",
    "send_to_facebook",
    "last_units_threshold",
    "is_restockable",
    "verificado_rating",
    "sku_producto",
    "gtin",
    "flags",
    "posicionar_ultima_page",
    "categoria",
    "brand",
    "n_hilos",
    "news_from_date",
    "news_to_date",
    "custom_design",
    "page_layout",
    "country_of_manufacture",
}
#: Information pages crawled by ``crawl`` (path → type).
PAGES = {
    "/": "home",
    "/politicas-de-despacho": "policy",
    "/politicas-de-cambios-y-devoluciones": "policy",
    "/preguntas-frecuentes": "faq",
    "/retiro-tiendas": "policy",
    "/stores": "stores",
    "/terminos-y-condiciones": "policy",
    "/fraudes": "policy",
    "/guia-de-compras": "guide",
    "/blog": "blog-index",
    "/contact": "contact",
    "/contacto-hoteleria": "contact",
    "/quienes-somos": "about",
    "/certificaciones-textiles-cannon-home": "about",
    "/catalogo-cannon-home": "about",
    "/inspiracion-cannon": "about",
    "/politica-medio-ambiente": "policy",
    "/marcas/cannon": "brand",
    "/marcas/royal-supreme": "brand",
    "/marcas/elements-co": "brand",
    "/marcas/american-family": "brand",
    "/marcas/nimbus": "brand",
}
#: Blog posts read for the buying guides (sheets, towels, duvets, pillows).
BLOG_POSTS = (
    "/blog/descubre-que-significan-los-hilos-de-las-sabanas.html",
    "/blog/como-elegir-sabanas-para-tu-cama.html",
    "/blog/en-que-fijarse-para-elegir-sabanas.html",
    "/blog/guia-de-compra-5-factores-a-considerar-al-elegir-sabanas.html",
    "/blog/5-consejos-para-elegir-sabanas-y-ropa-de-cama-de-calidad.html",
    "/blog/165_diferencias-ropa-cama.html",
    "/blog/cuales-son-las-medidas-de-cama-de-2-plazas-en-chile.html",
    "/blog/gramaje-de-toallas.html",
    "/blog/guia-de-compra-que-considerar-al-comprar-una-toalla-de-playa.html",
    "/blog/como-elegir-el-plumon-perfecto.html",
    "/blog/5-factores-a-tomar-en-cuenta-al-momento-de-elegir-el-plumon-adecuado.html",
    "/blog/funda-plumon-o-cubrecama-cual-elegir.html",
    "/blog/como-elegir-una-almohada-segun-tu-posicion-al-dormir.html",
    "/blog/almohadas-viscoelasticas-vs-almohadas-de-plumas-diferencias-y-beneficios.html",
    "/blog/almohada-firme-o-suave-cual-elegir.html",
    "/blog/cual-es-el-tamano-de-una-almohada-king-en-chile.html",
    "/blog/guia-de-compras-descubre-el-tipo-de-almohada-que-necesitas.html",
)
#: Top categories crawled as pages (their H1, intro text and sub-links).
CATEGORY_PAGES = (
    "/12-ropa-de-cama",
    "/12-ropa-de-cama/20-sabanas",
    "/12-ropa-de-cama/plumones",
    "/12-ropa-de-cama/almohadas",
    "/12-ropa-de-cama/fundas-plumon",
    "/12-ropa-de-cama/cubrecamas",
    "/dormitorio",
    "/bano",
    "/bano/toallas",
    "/toallas-de-playa",
    "/muebles",
    "/hoteleria",
    "/plaza",
    "/evento/nueva-coleccion",
)
#: A product page and a category for headers and the mobile layout probes.
PROBE_PRODUCT = "/sabanas-2-plazas-300-hilos-liso-fog.html"
PROBE_CATEGORY = "/12-ropa-de-cama/20-sabanas"
HEADERS_KEPT = (
    "content-security-policy",
    "content-security-policy-report-only",
    "permissions-policy",
    "x-frame-options",
    "strict-transport-security",
    "referrer-policy",
    "cache-control",
    "content-type",
    "vary",
    "x-cache",
    "age",
)
#: Third parties not needed to read a page; blocked in the crawl to keep it light.
BLOCK_HOSTS = (
    "google",
    "facebook",
    "doubleclick",
    "clarity.ms",
    "hotjar",
    "contentsquare",
    "tiktok",
    "pinterest",
    "bing",
    "newrelic",
    "nr-data",
    "visualwebsiteoptimizer",
    "survicate",
    "embluemail",
    "freshworks",
    "getblue",
    "gopersonal",
    "goshops",
    "verificado",
)


class Blocked(RuntimeError):
    """The site refused the connection (403/405/timeout): the VPN dropped."""


# --------------------------------------------------------------------------- utils


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def collapse(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\u00a0", " ")).strip()


def plain(html: str | None) -> str:
    """Visible text of an HTML fragment (styles, scripts and widget tags dropped)."""
    h = html or ""
    h = re.sub(r"(?is)<(style|script)\b.*?</\1>", " ", h)
    h = re.sub(r"\{\{[^}]*\}\}", " ", h)
    h = re.sub(r"(?i)<br\s*/?>|</(p|div|h\d|li)>", ". ", h)
    h = re.sub(r"<[^>]+>", " ", h)
    t = collapse(htmllib.unescape(h))
    t = re.sub(r"\s+([.,;:])", r"\1", t)
    t = re.sub(r"(\.\s*){2,}", ". ", t)
    return t.strip(" .")


def dedupe_sentences(text: str) -> str:
    """The shop's static blocks often repeat their first paragraph; keep each sentence once."""
    out: list[str] = []
    seen: set[str] = set()
    for s in re.split(r"(?<=[.!?])\s+", text):
        k = fold(s)
        if k and k not in seen:
            seen.add(k)
            out.append(s)
    return " ".join(out)


def clip(text: str, cap: int) -> str:
    if len(text) <= cap:
        return text
    cut = text[: cap - 1]
    sp = cut.rfind(" ")
    return (cut[:sp] if sp > cap * 0.6 else cut).rstrip(" ,.;:") + "…"


_last = [0.0]


def _pace() -> None:
    wait = _last[0] + PACE - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.monotonic()


def _cache_file(kind: str, key: str, ext: str = "json") -> Path:
    h = hashlib.sha1(key.encode()).hexdigest()[:16]
    slug = re.sub(r"[^a-z0-9]+", "-", fold(key))[:60].strip("-")
    return CACHE / kind / f"{slug}-{h}.{ext}"


def gql(query: str, *, offline: bool = False, refresh: bool = False) -> dict[str, Any]:
    """``POST /graphql`` (cached). Raises ``Blocked`` on 403/405 or a timeout."""
    f = _cache_file("gql", query)
    if f.exists() and not refresh:
        return json.loads(f.read_text())
    if offline:
        raise FileNotFoundError(f"not cached (offline): {query[:80]}")
    _pace()
    req = urllib.request.Request(
        GRAPHQL,
        data=json.dumps({"query": query}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": UA, "Origin": SITE},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code in (403, 405):
            raise Blocked(f"POST /graphql → {e.code}: is the VPN up?") from e
        raise
    except TimeoutError as e:
        raise Blocked("POST /graphql timed out: is the VPN up?") from e
    if data.get("errors") and not data.get("data"):
        raise RuntimeError(f"GraphQL error: {data['errors'][:2]}")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, ensure_ascii=False))
    return data


def get(
    path: str, *, offline: bool = False, refresh: bool = False
) -> tuple[int, dict[str, str], str]:
    """``GET`` a site page (cached): status, selected headers, body."""
    url = path if path.startswith("http") else SITE + path
    f = _cache_file("http", url)
    if f.exists() and not refresh:
        d = json.loads(f.read_text())
        return d["status"], d["headers"], d["body"]
    if offline:
        raise FileNotFoundError(f"not cached (offline): {url}")
    _pace()
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept-Language": "es-CL,es;q=0.9"}
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            status, hdrs, body = (
                r.status,
                dict(r.headers.items()),
                r.read().decode("utf-8", "replace"),
            )
    except urllib.error.HTTPError as e:
        if e.code in (403, 405):
            raise Blocked(f"GET {url} → {e.code}: is the VPN up?") from e
        status, hdrs, body = e.code, dict(e.headers.items()), ""
    except TimeoutError as e:
        raise Blocked(f"GET {url} timed out: is the VPN up?") from e
    if "Not allowed" in body[:2000]:
        raise Blocked(f"GET {url} → 'Not allowed': is the VPN up?")
    keep = {k.lower(): v for k, v in hdrs.items() if k.lower() in HEADERS_KEPT}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"status": status, "headers": keep, "body": body}, ensure_ascii=False))
    return status, keep, body


def dump_lines(path: Path, items: list[dict[str, Any]]) -> None:
    """A JSON array with one object a line, so diffs stay readable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = ",\n".join(json.dumps(i, ensure_ascii=False, separators=(",", ":")) for i in items)
    path.write_text("[\n" + body + "\n]\n" if items else "[]\n")


def load_json(name: str) -> Any:
    f = L3 / name
    return json.loads(f.read_text()) if f.exists() else []


def site_path(url: str) -> str:
    for host in (SITE, *ALIASES):
        if url.startswith(host):
            url = url[len(host) :]
    url = url.split("#")[0].split("?")[0]
    return url.rstrip("/") or "/"


# --------------------------------------------------------------------------- catalogue

PRODUCT_FIELDS = """
  sku name url_key
  description { html }
  short_description { html }
  image { url }
  categories { id }
  custom_attributesV2 { items { code
    ... on AttributeValue { value }
    ... on AttributeSelectedOptions { selected_options { label value } } } }
"""

CATEGORY_FIELDS = "id name url_path include_in_menu level position"


def category_tree(offline: bool, refresh: bool) -> list[dict[str, Any]]:
    """Every category under the root, flattened, with its parent id."""
    nest = CATEGORY_FIELDS
    for _ in range(5):
        nest = f"{CATEGORY_FIELDS} children {{ {nest} }}"
    q = f'{{ categoryList(filters: {{ ids: {{ eq: "{ROOT_CATEGORY}" }} }}) {{ {nest} }} }}'
    root = gql(q, offline=offline, refresh=refresh)["data"]["categoryList"][0]
    out: list[dict[str, Any]] = []

    def walk(node: dict[str, Any], parent: int | None, names: list[str]) -> None:
        for c in sorted(node.get("children") or [], key=lambda c: c.get("position") or 0):
            chain = [*names, collapse(c["name"])]
            out.append(
                {
                    "id": c["id"],
                    "path": "/" + (c.get("url_path") or "").strip("/"),
                    "name": collapse(c["name"]),
                    "chain": chain,
                    "parent": parent,
                    "level": len(chain),
                    "in_menu": bool(c.get("include_in_menu")),
                }
            )
            walk(c, c["id"], chain)

    walk(root, None, [])
    return out


def attribute_meta(codes: list[str], offline: bool, refresh: bool) -> dict[str, dict[str, Any]]:
    """Storefront label and flags of each attribute code."""
    meta: dict[str, dict[str, Any]] = {}
    for i in range(0, len(codes), 40):
        part = ",".join(
            f'{{attribute_code: "{c}", entity_type: "catalog_product"}}' for c in codes[i : i + 40]
        )
        q = (
            f"{{ customAttributeMetadataV2(attributes: [{part}]) {{ items {{ code label frontend_input"
            " ... on CatalogAttributeMetadata { is_visible_on_front is_filterable } } } }"
        )
        for it in gql(q, offline=offline, refresh=refresh)["data"]["customAttributeMetadataV2"][
            "items"
        ]:
            meta[it["code"]] = it
    return meta


def fetch_products(offline: bool, refresh: bool) -> list[dict[str, Any]]:
    """Every product ``products()`` lists, paged; gaps filled per top category."""
    seen: dict[str, dict[str, Any]] = {}

    def page_all(filt: str) -> int:
        total, page = 0, 1
        while True:
            q = (
                f"{{ products(filter: {filt}, sort: {{ name: ASC }}, pageSize: {PAGE_SIZE}, currentPage: {page})"
                f" {{ total_count page_info {{ total_pages }} items {{ {PRODUCT_FIELDS} }} }} }}"
            )
            d = gql(q, offline=offline, refresh=refresh)["data"]["products"]
            total = d["total_count"]
            for it in d["items"]:
                seen.setdefault(it["sku"], it)
            print(
                f"  {filt} page {page}/{d['page_info']['total_pages']} → {len(seen)} products",
                file=sys.stderr,
            )
            if page >= (d["page_info"]["total_pages"] or 1):
                return total
            page += 1

    total = page_all('{ price: { from: "0" } }')
    if len(seen) < total:
        print(
            f"  {total - len(seen)} missing after paging; filling per top category", file=sys.stderr
        )
        for cid in (6, 9, 18, 5766, 26, 4502, 2660, 592, 3737):
            page_all(f'{{ category_id: {{ eq: "{cid}" }} }}')
    return list(seen.values())


#: Two-digit size codes (1 Plaza, 1.5 Plazas, 2 Plazas, King, Súper King).
SIZE_DIGITS = {"10", "15", "20", "25", "30"}


def family_of(sku: str) -> str:
    """The SKU stem one product line shares across its sizes (13-character SKUs).

    The shop uses three SKU layouts; the size code is cut out of each:

    - newer collections end in a season letter and a 2-digit year (``A26``,
      ``S27``, ``W26``): ``JSRSB05B30A26`` = stem ``JSRSB05B`` + size ``30`` +
      ``A26`` → ``JSRSB05B·A26``;
    - beds, mattresses and bases put a 2-digit size after a digit:
      ``CACNBG001925X`` = ``CACNBG0019`` + ``25`` + ``X`` → ``CACNBG0019·X``;
    - everything else has a 3-character size code at positions 10-12 and a
      final letter: ``JSCNAE143P20Z`` → ``JSCNAE143·Z`` (``P10`` 1 Plaza,
      ``P15`` 1.5 Plazas, ``P20`` 2 Plazas, ``P25`` King, ``P30`` Súper King;
      pillows and pillowcases ``A57``/``A59``; towels ``BAN`` baño, ``MAN``
      mano, ``VIS`` visita, ``SBA`` sábana de baño, ``PIS`` piso; rugs
      ``A02``/``A05``/``A08``).

    Colours are different designs, so different stems. ``catalogue`` then
    splits a family whose members are not told apart by size, type,
    measurements or weight (designs numbered where the size would be) back
    into one family per SKU.
    """
    if len(sku) != 13:
        return sku
    if re.fullmatch(r"[A-Z]\d\d", sku[10:13]):
        return f"{sku[:8]}·{sku[10:]}"
    if sku[9].isdigit() and sku[10:12] in SIZE_DIGITS:
        return f"{sku[:10]}·{sku[12]}"
    return f"{sku[:9]}·{sku[12]}"


def _split_families(products: list[dict[str, Any]]) -> int:
    """Give each product its own family where siblings are not distinct sizes."""

    def key(p: dict[str, Any]) -> tuple[Any, ...]:
        a = p["attributes"]
        return (p["size"], p["type"], p["weight_gsm"], a.get("Medidas"), a.get("Talla"))

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in products:
        groups[p["family"]].append(p)
    n = 0
    for members in groups.values():
        keys = Counter(key(p) for p in members)
        for p in members:
            if len(members) > 1 and keys[key(p)] > 1:
                p["family"] = p["sku"]
                n += 1
    return n


def _label(attr: dict[str, Any]) -> str:
    if "selected_options" in attr:
        return ", ".join(
            collapse(o["label"]) for o in attr["selected_options"] or [] if collapse(o["label"])
        )
    v = attr.get("value")
    v = collapse(str(v)) if v is not None else ""
    return "" if v in ("0", "0.000000") else v


def _int(label: str) -> int | None:
    m = re.search(r"\d+", (label or "").replace(".", ""))
    return int(m.group()) if m else None


def _side(path: str) -> bool:
    """A promotional, brand or by-size tree (``/67-sale``, ``/weekend-sale``, ``/plaza`` …)."""
    top = re.sub(r"^\d+-", "", path.strip("/").split("/")[0])
    return top in SIDE_TREES or any(
        top.startswith(t) for t in ("sale", "cyber", "black", "dia-", "evento")
    )


def product_record(
    it: dict[str, Any], cats: dict[int, dict[str, Any]], meta: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    attrs = {a["code"]: a for a in (it.get("custom_attributesV2") or {}).get("items") or []}
    lab = {c: _label(a) for c, a in attrs.items()}
    shown: dict[str, str] = {}
    for code, value in lab.items():
        if not value or code in SKIP_ATTRS:
            continue
        m = meta.get(code) or {}
        if not m.get("is_visible_on_front"):
            continue
        label = collapse(m.get("label") or code)
        if label in shown and shown[label] != value:
            label = f"{label} ({code})"
        shown[label] = value
    in_cats = [cats[c["id"]] for c in it.get("categories") or [] if c["id"] in cats]
    paths = sorted({c["path"] for c in in_cats})
    main = [c for c in in_cats if not _side(c["path"]) and c["in_menu"]]
    main = main or [c for c in in_cats if not _side(c["path"])] or in_cats
    best = max(main, key=lambda c: (c["level"], c["in_menu"]), default=None)
    desc = dedupe_sentences(plain((it.get("description") or {}).get("html")))
    if len(desc) < 40:
        desc = dedupe_sentences(plain((it.get("short_description") or {}).get("html"))) or desc
    image = ((it.get("image") or {}).get("url") or "").split("?")[0]
    if "placeholder" in image:
        image = ""
    brand = lab.get("marca") or lab.get("brand") or ""
    return {
        "sku": it["sku"],
        "name": collapse(it["name"]),
        "path": f"/{it['url_key']}.html",
        "brand": brand or None,
        "category": " > ".join(best["chain"]) if best else None,
        "categories": paths,
        "type": lab.get("tipo_producto") or None,
        "size": lab.get("tamano") or None,
        "color": lab.get("color") or None,
        "material": lab.get("material") or None,
        "threads": _int(lab.get("hilos", "")),
        "weight_gsm": _int(lab.get("gramos", "")),
        "attributes": shown,
        "summary": clip(desc, SUMMARY_CAP),
        "image": image or None,
        "family": family_of(it["sku"]),
        "in_catalogue_at": TODAY,
    }


def _filters_of(page: str) -> tuple[list[str], list[str], dict[str, dict[str, Any]]]:
    """Layered navigation (``#narrow-by-list``) and quick-filter pills of a category page."""
    quick: list[str] = []
    for v in re.findall(r'class="qf__group[^"]*"[^>]*data-qf-request-var="([^"]+)"', page):
        if v not in quick:
            quick.append(v)
    if not quick:
        for v in re.findall(r'data-qf-request-var="([^"]+)"', page):
            if v not in quick:
                quick.append(v)
    i = page.find('id="narrow-by-list"')
    filters: list[str] = []
    options: dict[str, dict[str, Any]] = {}
    if i < 0:
        return filters, quick, options
    block = page[i:]
    end = block.find('id="amasty-shopby-product-list"')
    block = block[: end if end > 0 else 400000]
    parts = re.split(r'class="filter-options-item', block)[1:]
    for part in parts:
        t = re.search(r'filter-options-title">\s*([^<]+?)\s*<', part)
        v = re.search(r'data-amshopby-filter="([^"]+)"', part)
        if not t or not v:
            continue
        var = v.group(1)
        title = collapse(htmllib.unescape(t.group(1)))
        vals: list[str] = []
        if var != "price":
            for lbl in re.findall(r'data-label="([^"]*)"', part):
                lbl = collapse(htmllib.unescape(lbl))
                if lbl and lbl not in vals:
                    vals.append(lbl)
        filters.append(var)
        options[var] = {"label": title, "values": vals}
    return filters, quick, options


def catalogue(offline: bool, refresh: bool) -> None:
    print("categories…", file=sys.stderr)
    tree = category_tree(offline, refresh)
    cats = {c["id"]: c for c in tree}
    print(f"  {len(tree)} categories", file=sys.stderr)
    print("products…", file=sys.stderr)
    items = fetch_products(offline, refresh)
    codes = sorted(
        {
            a["code"]
            for it in items
            for a in (it.get("custom_attributesV2") or {}).get("items") or []
        }
    )
    meta = attribute_meta(codes, offline, refresh)
    products = [product_record(it, cats, meta) for it in items]
    print(f"  {_split_families(products)} products split out of a shared stem", file=sys.stderr)
    products.sort(key=lambda p: (p["category"] or "~", p["family"], p["name"]))
    dump_lines(L3 / "products.json", products)
    print(f"  wrote {len(products)} products", file=sys.stderr)

    count: Counter[str] = Counter(path for p in products for path in p["categories"])
    out: list[dict[str, Any]] = []
    for c in tree:
        rec: dict[str, Any] = {
            "id": c["id"],
            "path": c["path"],
            "name": c["name"],
            "parent": cats[c["parent"]]["path"] if c["parent"] in cats else None,
            "level": c["level"],
            "in_menu": c["in_menu"],
            "products": count.get(c["path"], 0),
            "filters": [],
            "quick_filters": [],
            "options": {},
        }
        # Only listings a visitor can reach and that list something are read.
        if c["in_menu"] and rec["products"]:
            try:
                status, _, body = get(c["path"], offline=offline, refresh=refresh)
            except FileNotFoundError:
                status, body = 0, ""
            if status == 200:
                rec["filters"], rec["quick_filters"], rec["options"] = _filters_of(body)
            else:
                rec["status"] = status
            print(f"  {c['path']} {status} {rec['filters']}", file=sys.stderr)
        out.append(rec)
    dump_lines(L3 / "categories.json", out)
    print(f"  wrote {len(out)} categories", file=sys.stderr)


# --------------------------------------------------------------------------- crawl

SCROLL_JS = r"""
async () => {
  const se = document.scrollingElement;
  let y = 0, h = se.scrollHeight;
  while (y < h && y < 30000) {
    y += 800; window.scrollTo(0, y);
    await new Promise(r => setTimeout(r, 100));
    h = se.scrollHeight;
  }
  window.scrollTo(0, 0);
  await new Promise(r => setTimeout(r, 400));
  return h;
}
"""

# Sections split at h1/h2 inside the main column; h3/h4 are the section's items;
# FAQs are headings that ask a question (or accordion titles) with the text up
# to the next heading. Hidden text (collapsed accordions, "Ver más") is read
# from text nodes.
PAGE_JS = r"""
() => {
  const clean = s => (s || '').replace(/[\u00a0\u200b\u200d]/g, ' ').replace(/[ \t]+/g, ' ')
    .replace(/\n\s*\n+/g, '\n').trim();
  const deep = el => { const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, {acceptNode: n =>
      n.parentElement && n.parentElement.closest('script,style,noscript') ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT});
    const out = []; for (let n = w.nextNode(); n; n = w.nextNode()) { const t = n.textContent.trim(); if (t) out.push(t); }
    return clean(out.join(' ')); };
  const uniq = el => {
    if (el.id && document.querySelectorAll('#' + CSS.escape(el.id)).length === 1) return '#' + CSS.escape(el.id);
    const tag = el.tagName.toLowerCase();
    const same = [...document.querySelectorAll('.column.main ' + tag + ', #maincontent ' + tag)];
    const i = same.indexOf(el);
    return (document.querySelector('.column.main') ? '.column.main ' : '#maincontent ') + tag + ':nth-of-type-in-main(' + (i + 1) + ')';
  };
  const main = document.querySelector('.column.main') || document.querySelector('#maincontent') || document.body;
  const H = 'h1,h2,h3,h4';
  // Walk block-level leaves in document order.
  const blocks = [];
  // A category's grid is in .column.main; its title, intro and SEO text are around it.
  const isCat = document.body.classList.contains('catalog-category-view');
  const roots = isCat ? [...document.querySelectorAll('#maincontent, .category-cms')] : [main];
  for (const root of roots) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, {acceptNode: el => {
    if (el.matches('script,style,noscript,form,.products-grid,.product-items,#layered-filter-block,.toolbar,.toolbar-products-plp,.qf,.block.filter,.filter-options,.block-search,.sidebar,[id^=gopersonal]')) return NodeFilter.FILTER_REJECT;
    return NodeFilter.FILTER_ACCEPT; }});
  for (let el = walker.nextNode(); el; el = walker.nextNode()) {
    if (el.matches(H)) { blocks.push({h: el}); continue; }
    if (el.matches('p,li,td,th,dt,dd,blockquote,figcaption') || (el.matches('div,span,strong') && !el.querySelector('p,li,div,h1,h2,h3,h4,table,ul,ol'))) {
      if (el.closest(H)) continue;
      if (el.parentElement && el.parentElement.closest('p,li,td,th,dt,dd,blockquote')) continue;
      const t = deep(el); if (t) blocks.push({t});
    }
  }
  }
  const sections = []; const faqs = []; let sec = null; let q = null;
  const push = () => { if (q) { faqs.push(q); q = null; } };
  for (const b of blocks) {
    if (b.h) {
      const level = +b.h.tagName[1]; const text = clean(b.h.innerText || deep(b.h)).split('\n')[0];
      if (!text) continue;
      push();
      if (level <= 2 || !sec) {
        sec = {heading: text, level, selector: uniq(b.h), text: [], items: []}; sections.push(sec);
      } else {
        sec.items.push(text); sec.text.push(text);
      }
      if (level >= 2 && (/\?\s*$/.test(text) || /^¿/.test(text.replace(/^\d+[.)]\s*/, '')))) q = {q: text.replace(/^\d+[.)]\s*/, ''), a: [], section: sec.heading};
      continue;
    }
    if (!sec) { sec = {heading: '', level: 0, selector: '', text: [], items: []}; sections.push(sec); }
    if (sec.text[sec.text.length - 1] !== b.t) sec.text.push(b.t);
    if (q) q.a.push(b.t);
  }
  push();
  if (isCat && sections.length) {
    const subs = [...document.querySelectorAll('.plp-category-carousel__item')].map(a => clean(a.innerText || deep(a))).filter(Boolean);
    sections[0].items.push(...subs.filter(x => !sections[0].items.includes(x)));
  }
  // Accordions (Page Builder / custom) that hold a question in a title element.
  for (const t of main.querySelectorAll('[data-role=title], .accordion-title, details > summary')) {
    const qq = clean(t.innerText || deep(t)); if (!/\?/.test(qq)) continue;
    const c = t.nextElementSibling; const a = c ? deep(c) : '';
    if (a && !faqs.some(f => f.q === qq)) faqs.push({q: qq, a: [a], section: ''});
  }
  const h1 = document.querySelector('h1');
  const meta = n => (document.querySelector('meta[name="' + n + '"]') || {}).content || '';
  const links = [...main.querySelectorAll('a[href]')].map(a => ({href: a.href, text: clean(a.innerText)})).filter(l => l.text);
  return {title: document.title, description: meta('description'), h1: h1 ? clean(h1.innerText) : '',
    sections: sections.map(s => ({...s, text: s.text.join('\n')})),
    faqs: faqs.map(f => ({...f, a: f.a.join('\n')})), links,
    count: (document.querySelector('.toolbar-amount .toolbar-number:last-child, #toolbar-amount .toolbar-number:last-child') || {}).textContent || ''};
}
"""

# The desktop mega menu: top items, column headings and leaf links.
NAV_JS = r"""
() => {
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const root = document.querySelector('#ninjamenus7'); if (!root) return [];
  const txt = el => clean(el.textContent);
  return [...root.querySelectorAll('.nav-item.level0')].map(li => {
    const a = li.querySelector(':scope > a');
    const links = [...li.querySelectorAll('.item-submenu a[href]')].map(x => ({text: txt(x), href: x.href}))
      .filter(x => x.text && !x.href.endsWith('#'));
    return {text: a ? txt(a) : '', href: a ? a.href : '', links};
  });
}
"""

# Fixed and sticky things that cover the page, and the header height.
PROBE_JS = r"""
() => {
  const r = el => { if (!el) return null; const b = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    return {top: Math.round(b.top), left: Math.round(b.left), width: Math.round(b.width), height: Math.round(b.height),
      position: cs.position, z: cs.zIndex, display: cs.display, visible: b.width > 0 && b.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'}; };
  const q = s => document.querySelector(s);
  const fixed = [];
  for (const el of document.querySelectorAll('body *')) {
    const cs = getComputedStyle(el);
    if ((cs.position === 'fixed' || cs.position === 'sticky') && el.getBoundingClientRect().height > 0) {
      const b = el.getBoundingClientRect();
      if (b.width < 20 || b.height < 20) continue;
      let sel = el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + [...el.classList].slice(0, 3).map(c => '.' + c).join('');
      fixed.push({selector: sel, position: cs.position, top: Math.round(b.top), bottom: Math.round(innerHeight - b.bottom),
        left: Math.round(b.left), right: Math.round(innerWidth - b.right), width: Math.round(b.width), height: Math.round(b.height), z: cs.zIndex});
    }
  }
  let header = 0;
  // The promo bar plus any full-width fixed/sticky bar stacked under it.
  for (const f of [...fixed].sort((a, b) => a.top - b.top))
    if (f.top <= header + 4 && f.top > -5 && f.width > innerWidth * 0.8 && f.height < 260) header = Math.max(header, f.top + f.height);
  return {viewport: [innerWidth, innerHeight], fixed_header_px: header,
    topbar: r(q('#topbarCannonBar')), header: r(q('header.page-header')),
    whatsapp: ['a#whatsapp-link', '.new-whatsapp-mobile', '.whatsapp-link-mobile'].map(s => r(q(s))).find(x => x && x.visible) || null,
    sticky_addtocart: ['#sticky-addtocart-bar', '.box-tocart'].map(s => r(q(s))).find(x => x && x.visible) || null,
    minicart: r(q('aside.content-minicart-modal')), fixed: fixed.slice(0, 25),
    permissions_policy_microphone: document.featurePolicy ? document.featurePolicy.allowsFeature('microphone') : null};
}
"""


async def _context(browser: Any, mobile: bool = False) -> Any:
    opts: dict[str, Any] = {"locale": "es-CL", "user_agent": UA}
    if mobile:
        opts.update(
            viewport={"width": 390, "height": 844},
            device_scale_factor=2,
            is_mobile=True,
            has_touch=True,
        )
    else:
        opts.update(viewport={"width": 1440, "height": 900})
    ctx = await browser.new_context(**opts)

    async def route(r: Any) -> None:
        u = r.request.url
        if r.request.resource_type in ("image", "media", "font") or any(
            h in u for h in BLOCK_HOSTS
        ):
            await r.abort()
        elif r.request.method != "GET" and "/graphql" not in u:
            await r.abort()  # never submit anything
        else:
            await r.continue_()

    await ctx.route("**/*", route)
    return ctx


async def _open(page: Any, path: str) -> int:
    _pace()
    resp = await page.goto(SITE + path, wait_until="domcontentloaded", timeout=60000)
    status = resp.status if resp else 0
    if status in (403, 405):
        raise Blocked(f"{path} → {status}: is the VPN up?")
    body = await page.content()
    if "Not allowed" in body[:3000]:
        raise Blocked(f"{path} → 'Not allowed': is the VPN up?")
    await page.wait_for_timeout(2500)
    return status


async def crawl_async(offline: bool, refresh: bool, only: list[str]) -> None:
    targets = {
        **PAGES,
        **dict.fromkeys(BLOG_POSTS, "blog"),
        **dict.fromkeys(CATEGORY_PAGES, "category"),
    }
    if only:
        targets = {p: targets.get(p, "page") for p in only}
    todo = [p for p in targets if refresh or not _cache_file("page", p).exists()]
    need_probe = refresh or not _cache_file("probe", "site").exists()
    if offline:
        todo, need_probe = [], False
    if todo or need_probe:
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            ctx = await _context(browser)
            page = await ctx.new_page()
            for path in todo:
                status = await _open(page, path)
                await page.evaluate(SCROLL_JS)
                rec = await page.evaluate(PAGE_JS)
                rec.update(path=path, status=status, final=page.url)
                f = _cache_file("page", path)
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(json.dumps(rec, ensure_ascii=False))
                print(
                    f"  {path} {status} {len(rec['sections'])} sections {len(rec['faqs'])} faqs",
                    file=sys.stderr,
                )
            if need_probe:
                await _open(page, "/")
                nav = await page.evaluate(NAV_JS)
                desktop = {"home": await page.evaluate(PROBE_JS)}
                await _open(page, PROBE_PRODUCT)
                desktop["product"] = await page.evaluate(PROBE_JS)
                await ctx.close()
                # A context with images and the WhatsApp/minicart widgets left in.
                mctx = await browser.new_context(
                    locale="es-CL",
                    user_agent=UA,
                    viewport={"width": 390, "height": 844},
                    is_mobile=True,
                    has_touch=True,
                    device_scale_factor=2,
                )
                await mctx.route(
                    "**/*",
                    lambda r: (
                        r.abort()
                        if r.request.method != "GET" and "/graphql" not in r.request.url
                        else r.continue_()
                    ),
                )
                mpage = await mctx.new_page()
                await _open(mpage, "/")
                mobile = {"home": await mpage.evaluate(PROBE_JS)}
                await _open(mpage, PROBE_PRODUCT)
                await mpage.evaluate("window.scrollTo(0, 900)")
                await mpage.wait_for_timeout(800)
                mobile["product"] = await mpage.evaluate(PROBE_JS)
                await mctx.close()
                f = _cache_file("probe", "site")
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(
                    json.dumps(
                        {"nav": nav, "desktop": desktop, "mobile": mobile}, ensure_ascii=False
                    )
                )
            await browser.close()
    write_pages(targets)


def page_record(rec: dict[str, Any], kind: str) -> dict[str, Any]:
    sections = []
    seen: set[tuple[str, str]] = set()
    for s in rec.get("sections") or []:
        text = clip(collapse(s["text"].replace("\n", " · ")), TEXT_CAP)
        if not s["heading"] and not text:
            continue
        # Page Builder pages often carry a desktop and a mobile copy of a block.
        if (s["heading"], text) in seen:
            continue
        seen.add((s["heading"], text))
        sel = s.get("selector") or ""
        if ":nth-of-type-in-main(" in sel:
            sel = ""  # no stable selector; match by heading
        sections.append(
            {
                "heading": s["heading"] or f"[block] {' '.join(text.split()[:6])}",
                "level": s["level"],
                "selector": sel,
                "text": text,
                "items": s["items"][:40],
            }
        )
    faqs: list[dict[str, str]] = []
    for f in rec.get("faqs") or []:
        q = re.sub(r"^\d+\s*[.)]\s*", "", collapse(f["q"]))
        a = clip(collapse(f["a"].replace("\n", " ")), TEXT_CAP)
        if a and not any(fold(x["q"]) == fold(q) for x in faqs):
            faqs.append({"q": q, "a": a, "section": f["section"]})
    out = {
        "path": rec["path"],
        "url": SITE + rec["path"],
        "type": kind,
        "title": collapse(rec.get("title")),
        "description": collapse(rec.get("description")),
        "h1": collapse(rec.get("h1")),
        "sections": sections,
        "faqs": faqs,
    }
    final = site_path(rec.get("final") or "")
    if final and final != rec["path"]:
        out["redirected_to"] = final
    if rec.get("status") and rec["status"] != 200:
        out["status"] = rec["status"]
    if kind == "category" and rec.get("count"):
        out["count"] = collapse(rec["count"])
    return out


def write_pages(targets: dict[str, str]) -> None:
    pages = []
    all_targets = {
        **PAGES,
        **dict.fromkeys(BLOG_POSTS, "blog"),
        **dict.fromkeys(CATEGORY_PAGES, "category"),
        **targets,
    }
    for path, kind in all_targets.items():
        f = _cache_file("page", path)
        if f.exists():
            rec = json.loads(f.read_text())
            if rec.get("status") == 404:
                continue
            pages.append(page_record(rec, kind))
    dump_lines(L3 / "pages.json", pages)
    print(f"  wrote {len(pages)} pages", file=sys.stderr)

    probe_f = _cache_file("probe", "site")
    probe = json.loads(probe_f.read_text()) if probe_f.exists() else {}
    headers: dict[str, Any] = {}
    samples = {
        "home": "/",
        "category": PROBE_CATEGORY,
        "product": PROBE_PRODUCT,
        "cms": "/preguntas-frecuentes",
    }
    for kind, path in samples.items():
        try:
            status, h, _ = get(path, offline=not probe_f.exists())
        except (FileNotFoundError, Blocked):
            continue
        csp = h.get("content-security-policy", "")
        directives = {}
        for d in csp.split(";"):
            d = d.strip()
            if d:
                name, _, rest = d.partition(" ")
                directives[name] = rest.split()
        headers[kind] = {
            "status": status,
            "csp_enforced": bool(csp),
            "csp_report_only": bool(h.get("content-security-policy-report-only")),
            "permissions_policy": h.get("permissions-policy"),
            "x_frame_options": h.get("x-frame-options"),
            "cache": {k: h[k] for k in ("cache-control", "x-cache", "age") if k in h},
            "csp_directives": {
                k: v if len(v) <= 12 else [*v[:12], f"… {len(v) - 12} more"]
                for k, v in directives.items()
            },
            "csp_connect_src_count": len(directives.get("connect-src", [])),
            "csp_allows_voqalize": "voqalize" in csp,
        }
    dsk = probe.get("desktop", {})
    mob = probe.get("mobile", {})
    site = {
        "site": SITE,
        "aliases": list(ALIASES),
        "crawled": TODAY,
        "pages": len(pages),
        "headers": headers,
        "notes": [
            "CSP is enforced (not report-only) and identical on home, category and product pages; no voqalize host is allowed.",
            "No Permissions-Policy header on any response: the microphone is not restricted by the site.",
            "HTML is Fastly-cached for hours (x-cache HIT, large age); POST /graphql is never cached. GET /graphql is 403.",
        ],
        "layout": {
            "fixed_header_px": {
                "desktop": (dsk.get("home") or {}).get("fixed_header_px"),
                "mobile": (mob.get("home") or {}).get("fixed_header_px"),
            },
            "desktop": dsk,
            "mobile": mob,
            "overlays": [
                {
                    "name": "promo bar",
                    "selector": "#topbarCannonBar",
                    "where": "fixed top",
                    "height_px": 32,
                    "z": 120,
                },
                {
                    "name": "WhatsApp button",
                    "selector": "a#whatsapp-link (desktop) / .whatsapp-link-mobile (mobile)",
                    "where": "bottom-right on desktop; a left-edge tab on mobile",
                    "href": "https://api.whatsapp.com/send?phone=56961069132",
                },
                {
                    "name": "minicart drawer",
                    "selector": "aside.content-minicart-modal._show",
                    "where": "right drawer ~400 px, full height, dims the page; opens by itself after every add",
                    "close": ".mc-header__close",
                },
                {
                    "name": "mobile sticky add-to-cart bar",
                    "selector": "#sticky-addtocart-bar / .box-tocart",
                    "where": "fixed bottom on mobile product pages, ~80 px, z 850",
                },
                {
                    "name": "filters drawer",
                    "selector": "#layered-filter-block.active",
                    "where": "left 380 px",
                },
                {
                    "name": "quick-filter panel",
                    "selector": ".qf__group.-open",
                    "close": ".qf__panel-close",
                },
            ],
        },
        "nav": probe.get("nav", []),
    }
    (L3 / "site.json").write_text(json.dumps(site, ensure_ascii=False, indent=1) + "\n")
    print("  wrote site.json", file=sys.stderr)


# --------------------------------------------------------------------------- maps


def _top(c: Counter[str], n: int = 8) -> str:
    return ", ".join(f"{k} ({v})" for k, v in c.most_common(n))


def maps() -> None:
    pages = load_json("pages.json")
    site = json.loads((L3 / "site.json").read_text()) if (L3 / "site.json").exists() else {}
    lines = [
        "# Mapa del sitio",
        "",
        f"Sources: {SITE} (crawl {site.get('crawled', '?')}; generated by build.py maps)",
        "",
        "## Menú principal (#ninjamenus7)",
        "",
    ]
    for item in site.get("nav", []):
        lines.append(f"- **{item['text']}** {site_path(item['href']) if item['href'] else ''}")
        leaves = [f"{x['text']} {site_path(x['href'])}" for x in item["links"]]
        if leaves:
            lines.append("  - " + "; ".join(dict.fromkeys(leaves)))
    lines += ["", "## Páginas", ""]
    for p in pages:
        lines.append(f"### {p['h1'] or p['title']} — {p['path']}")
        if p.get("redirected_to"):
            lines.append(f"(redirige a {p['redirected_to']})")
        heads = list(
            dict.fromkeys(
                s["heading"] for s in p["sections"] if not s["heading"].startswith("[block]")
            )
        )
        if heads:
            lines.append("Secciones: " + "; ".join(heads[:25]))
        if p["faqs"]:
            lines.append("Preguntas: " + " | ".join(f["q"] for f in p["faqs"][:40]))
        lines.append("")
    (L2 / "site-map.md").write_text("\n".join(lines).rstrip() + "\n")

    products = load_json("products.json")
    cats = load_json("categories.json")
    by_path: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in products:
        for c in p["categories"]:
            by_path[c].append(p)
    out = [
        "# Catálogo (índice)",
        "",
        f"Sources: POST {SITE}/graphql products() and the category pages' filters, "
        f"{TODAY} ({len(products)} products listed; out-of-stock products are not listed by the site). "
        "No prices: they are read live on the page.",
        "",
        "Each line: product types, sizes (Tamaño), colours, materials, thread counts (hilos), "
        "towel weights (g/m²), brands, with counts. `filters` = the listing's filter groups "
        "(request variables) in page order.",
        "",
    ]
    for c in cats:
        if not c["in_menu"] or not c["products"] or c["level"] > 2:
            continue
        ps = by_path.get(c["path"], [])
        if not ps:
            continue
        out.append(f"## {c['name']} — {c['path']} ({len(ps)})")
        for label, key in (
            ("Tipos", "type"),
            ("Tamaños", "size"),
            ("Colores", "color"),
            ("Materiales", "material"),
            ("Marcas", "brand"),
        ):
            cnt = Counter(p[key] for p in ps if p[key])
            if cnt:
                out.append(f"- {label}: {_top(cnt)}")
        th = sorted({p["threads"] for p in ps if p["threads"]})
        if th:
            out.append(f"- Hilos: {', '.join(map(str, th))}")
        gs = sorted({p["weight_gsm"] for p in ps if p["weight_gsm"]})
        if gs:
            out.append(f"- Gramaje (g/m²): {', '.join(map(str, gs))}")
        shown = [f for f in c["filters"] if f not in GENERIC_FILTERS]
        if shown:
            out.append(
                "- Filtros: "
                + ", ".join(f"{c['options'][f]['label']} `{f}`" for f in shown)
                + (f" (pills: {', '.join(c['quick_filters'])})" if c["quick_filters"] else "")
            )
        out.append("")
    (L2 / "catalogo.md").write_text("\n".join(out).rstrip() + "\n")
    print("wrote L2/site-map.md, L2/catalogo.md", file=sys.stderr)


# --------------------------------------------------------------------------- search


def search(query: str, limit: int = 8) -> None:
    words = [w for w in re.findall(r"\w+", fold(query)) if len(w) > 1]
    hits: list[tuple[int, str]] = []
    for p in load_json("pages.json"):
        for s in p["sections"]:
            hay = fold(f"{s['heading']} {s['text']}")
            n = sum(w in hay for w in words)
            if n:
                hits.append((n, f"page {p['path']} § {s['heading']}: {s['text'][:160]}"))
        for f in p["faqs"]:
            n = sum(w in fold(f["q"] + " " + f["a"]) for w in words)
            if n:
                hits.append((n + 1, f"faq {p['path']}: {f['q']} → {f['a'][:160]}"))
    for p in load_json("products.json"):
        hay = fold(
            " ".join(
                str(v)
                for v in (p["name"], p["category"], p["type"], p["size"], p["color"], p["material"])
            )
        )
        n = sum(w in hay for w in words)
        if n:
            hits.append((n, f"product {p['path']} [{p['family']}] {p['name']} · {p['category']}"))
    for n, line in sorted(hits, key=lambda h: -h[0])[:limit]:
        print(f"{n} {line}")


# --------------------------------------------------------------------------- main


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("crawl", "catalogue"):
        p = sub.add_parser(name)
        p.add_argument("--offline", action="store_true", help="build from the cache only")
        p.add_argument("--refresh", action="store_true", help="re-fetch everything")
        if name == "crawl":
            p.add_argument("--only", nargs="*", default=[], help="paths to (re)render")
    sub.add_parser("maps")
    s = sub.add_parser("search")
    s.add_argument("query")
    a = ap.parse_args()
    try:
        if a.cmd == "crawl":
            asyncio.run(crawl_async(a.offline, a.refresh, a.only))
        elif a.cmd == "catalogue":
            catalogue(a.offline, a.refresh)
        elif a.cmd == "maps":
            maps()
        else:
            search(a.query)
    except Blocked as e:
        sys.exit(f"STOP: {e}")


if __name__ == "__main__":
    main()
