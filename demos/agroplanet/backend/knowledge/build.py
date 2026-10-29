"""Rebuild the generated parts of the Agroplanet knowledge from www.agroplanet.cl.

Run from ``voqalize/demos``::

    uv run python agroplanet/backend/knowledge/build.py api      # menu + listings + stores → L3/categories.json
    uv run python agroplanet/backend/knowledge/build.py crawl    # pages + store cards → L3/pages.json, L3/stores.json
    uv run python agroplanet/backend/knowledge/build.py maps     # L3/site.json, L2/site-map.md, L2/categorias.md, L2/tiendas.md
    uv run python agroplanet/backend/knowledge/build.py all      # the three, in that order

``--refresh`` refetches what the cache already holds; ``--offline`` never touches
the network and rebuilds from the cache alone.

Two sources, both public and read-only:

- **The site's own JSON API** (``api.agroplanet.cl/webapi``, no auth): the
  category tree the "Todas las categorías" menu is drawn from, each listing's
  filters and product count, and the stores. Paced to one request a second.
- **The pages, in a real browser** (``crawl.mjs`` beside this file, run with
  node): the site is an Angular SPA, so nothing is on a page until JS has drawn
  it. Headings recorded here are what ``{show:}`` cues name and accordion panel
  titles what ``{faq:}`` cues name, so they must be what a visitor sees.
  Playwright is not a demos dependency: set ``PLAYWRIGHT_MODULE`` to an
  installed copy's entry module, or let this script find one under
  ``demos/*/extension/node_modules`` (agroplanet's own has ``@playwright/test``).

Every response is cached under ``~/.cache/voqalize-agroplanet``
(``AGROPLANET_CACHE`` overrides it). Nothing here logs in or submits a form. The
one write is the crawler adding one product to its own throwaway anonymous cart,
because ``/cotizacion`` shows its form only when the cart holds something.
**No price and no stock level is written to any file**: listing results and
product cards are never read, and a peso amount in page text is dropped. The
"Precio" filter keeps its bucket labels ("$0 - $9.999"): they are the filter's
fixed options, the same on every listing, not a product's price.

The hand-written files (``L1.md`` and the other ``L2/*.md``) are not touched:
re-read them against a new crawl, since the home's monthly heading, campaigns and
store hours change.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, cast

HERE = Path(__file__).resolve().parent
L2 = HERE / "L2"
L3 = HERE / "L3"
CACHE = Path(os.environ.get("AGROPLANET_CACHE", Path.home() / ".cache" / "voqalize-agroplanet"))
SITE = "https://www.agroplanet.cl"
API = "https://api.agroplanet.cl/webapi"
MENU_URL = f"{API}/menu/getFullHierachyByID?id=AG_Ecommerce_CategoryNavComponent"
LISTING_URL = f"{API}/category/getCategory?code={{code}}&q=&page=0&sort=&pageSize=1"
STORES_URL = f"{API}/store/findStoreByRegionAndCommune?page={{page}}&regionCode=&CommuneCode="
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)
CRAWLED = time.strftime("%Y-%m-%d")

#: The pages the brain knows by heading and accordion panel.
PAGES = [
    "/",
    "/nuestras-tiendas",
    "/sobre-nosotros",
    "/politica-despacho",
    "/garantia-devoluciones",
    "/cambios-devoluciones",
    "/politica-proteccion-datos",
    "/politica-transparencia",
    "/bases-promociones-vigentes",
    "/derco-integro",
    "/carro",
    "/cotizacion",
]
POLICY = {
    "/politica-despacho",
    "/garantia-devoluciones",
    "/cambios-devoluciones",
    "/politica-proteccion-datos",
    "/politica-transparencia",
    "/bases-promociones-vigentes",
}
#: A route the router sends elsewhere, and the alias it also answers to.
REDIRECTS = {"/inicio": "/", "/productos": "/"}

#: The "Ver todo" entry of a flyout column: the same listing as its column.
VER_TODO = "Ver todo"
#: Not kept per category: "Categoría" is the sub-category list, which a category
#: page shows as links in its "categoria-box", not as a filter.
FACETS_DROPPED = {"category"}
#: The month's campaigns ("Agrofertas Octubre", C_AG_BUSQUEDA_PLP_AGROFERRETERIA
#: OCTUBRE) come back as facets, and the page draws each as an on/off switch
#: titled with the campaign above "Precio" (not a panel): kept as one facet,
#: "Campaña", its options the campaigns, as the adapter reports it.
FACETS_CAMPAIGN = re.compile(r"^C_AG_BUSQUEDA_")
CAMPAIGN = "Campaña"
MAX_OPTIONS = 8
#: An answer longer than this is cut at a sentence: the brain reads the topic
#: file for the whole text.
MAX_ANSWER = 700

_last_request = 0.0


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# ─── Network, cached and paced ─────────────────────────────────────────────────


def _cache_path(url: str) -> Path:
    key = re.sub(r"[^A-Za-z0-9]+", "_", url.split("://", 1)[-1]).strip("_")
    return CACHE / "api" / f"{key[:180]}.json"


def get_json(url: str, *, refresh: bool, offline: bool) -> Any:
    """``url``'s ``data``, from the cache when it has it; at most one request a second."""
    global _last_request
    path = _cache_path(url)
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    if offline:
        raise SystemExit(f"STOP: {url} is not cached and --offline was given")
    wait = 1.0 - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept": "application/json", "Origin": SITE, "Referer": SITE},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"STOP: {url} answered {exc.code}") from exc
    finally:
        _last_request = time.monotonic()
    envelope = json.loads(body)
    if not isinstance(envelope, dict) or not cast(dict[str, Any], envelope).get("isValid"):
        raise SystemExit(f"STOP: {url} answered {body[:200]}")
    data = cast(dict[str, Any], envelope).get("data")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def write_lines(path: Path, items: list[dict[str, Any]]) -> None:
    """A JSON list with one object a line: diffs stay readable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = ",\n".join(json.dumps(i, ensure_ascii=False, separators=(",", ":")) for i in items)
    path.write_text(f"[\n{body}\n]\n", encoding="utf-8")


def _clean(text: Any) -> str:
    return " ".join(str(text).split()) if isinstance(text, str | int | float) else ""


# ─── Categories ────────────────────────────────────────────────────────────────


def _code(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


def _menu(menu: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The red bar's shortcuts and the tree, from the menu component: its first
    child (``AG_NVL1_header_NavNode``) is the shortcuts, the rest the level-1 nodes.
    ``visible: false`` nodes are not in the flyout and are left out with their
    children."""
    shortcuts: list[dict[str, Any]] = []
    roots: list[dict[str, Any]] = []
    for comp in cast(list[dict[str, Any]], menu.get("component") or []):
        if not comp.get("visible"):
            continue
        if "_header_" in str(comp.get("codeMenuNav")):
            for c in cast(list[dict[str, Any]], comp.get("categories") or []):
                if c.get("visible") and c.get("url"):
                    shortcuts.append(
                        {
                            "code": _code(c["url"]),
                            "name": _clean(c["linkName"]),
                            "path": c["url"],
                        }
                    )
            continue
        roots.append(comp)
    return shortcuts, roots


def _walk(
    nodes: list[dict[str, Any]],
    parent: dict[str, Any] | None,
    level: int,
    out: list[dict[str, Any]],
) -> None:
    for n in nodes:
        if not n.get("visible") or not n.get("url"):
            continue
        name = _clean(n.get("linkName"))
        if name == VER_TODO:
            # "Ver todo" opens the column's own listing under another slug.
            if parent is not None and n["url"] != parent["path"]:
                parent["aliases"].append(n["url"])
            continue
        node: dict[str, Any] = {
            "code": _code(n["url"]),
            "path": n["url"],
            "name": name,
            "parent": parent["path"] if parent else "",
            "parent_code": parent["code"] if parent else "",
            "level": level,
            "aliases": [],
        }
        out.append(node)
        _walk(cast(list[dict[str, Any]], n.get("categories") or []), node, level + 1, out)


def _bucket_floor(label: str) -> int:
    m = re.search(r"\$([\d.]+)", label)
    return int(m.group(1).replace(".", "")) if m else 0


def _facets(listing: dict[str, Any]) -> list[dict[str, Any]]:
    """The listing's filter panels as the page titles them and labels their
    checkboxes (the API's names, verbatim: the page shows them unchanged)."""
    groups: list[dict[str, Any]] = []
    campaigns: dict[str, str] = {}
    data = cast(dict[str, Any], listing.get("data") or {})
    for f in cast(list[dict[str, Any]], data.get("facets") or []):
        code = str(f.get("code") or "")
        if FACETS_CAMPAIGN.match(code):
            for v in cast(list[dict[str, Any]], f.get("values") or []):
                if _clean(v.get("name")):
                    campaigns.setdefault(_clean(v.get("name")), code)
            continue
        if code in FACETS_DROPPED or not f.get("visible", True):
            continue
        values = [
            (_clean(v.get("name")), int(v.get("count") or 0))
            for v in cast(list[dict[str, Any]], f.get("values") or [])
            if _clean(v.get("name"))
        ]
        if not values:
            continue
        if f.get("code") == "price":
            # The page lists the buckets low to high; all of them are kept.
            options = sorted((n for n, _ in values), key=_bucket_floor)
        else:
            top = sorted(values, key=lambda v: -v[1])[:MAX_OPTIONS]
            options = [n for n, _ in top]
        groups.append(
            {
                "name": _clean(f.get("name")),
                "param": _clean(f.get("code")),
                "options": options,
                "total": len(values),
            }
        )
    if campaigns:
        groups.insert(
            0,
            {
                "name": CAMPAIGN,
                "param": next(iter(campaigns.values())),
                "options": list(campaigns),
                "total": len(campaigns),
            },
        )
    return groups


def build_categories(
    *, refresh: bool, offline: bool
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    menu = get_json(MENU_URL, refresh=refresh, offline=offline)
    shortcuts, roots = _menu(menu)
    nodes: list[dict[str, Any]] = []
    _walk(roots, None, 1, nodes)
    # The same code under several paths: a red-bar shortcut's slug differs from
    # the flyout's ("lubricantes" for "lubricantes_y_fluidos"), and a code can sit
    # in two columns. The router resolves any of them by code.
    paths_by_code: dict[str, list[str]] = {}
    for n in nodes:
        paths_by_code.setdefault(n["code"], []).append(n["path"])
    for s in shortcuts:
        paths_by_code.setdefault(s["code"], []).append(s["path"])
    for n in nodes:
        n["aliases"] += [p for p in paths_by_code[n["code"]] if p != n["path"]]
    codes = list(dict.fromkeys(n["code"] for n in nodes))
    log(f"menu: {len(nodes)} nodes, {len(codes)} codes, {len(shortcuts)} shortcuts")
    listings: dict[str, dict[str, Any]] = {}
    for i, code in enumerate(codes, 1):
        listings[code] = get_json(LISTING_URL.format(code=code), refresh=refresh, offline=offline)
        if i % 25 == 0:
            log(f"  listings {i}/{len(codes)}")
    out: list[dict[str, Any]] = []
    for n in nodes:
        listing = listings[n["code"]]
        data = cast(dict[str, Any], listing.get("data") or {})
        pagination = cast(dict[str, Any], data.get("pagination") or {})
        out.append(
            {
                **n,
                "aliases": list(dict.fromkeys(n["aliases"])),
                # What the listing page itself titles the category (the
                # breadcrumb and "categoria-box"): "Lubricantes y Grasas" for
                # the flyout's "Lubricantes Y Fluidos".
                "page_name": _clean(listing.get("name")),
                # countProducts answers 1 whatever the listing holds; the
                # pagination's total is the number of products listed that day.
                "products": pagination.get("totalNumberOfResults"),
                "facets": _facets(listing) if n["level"] <= 2 else [],
            }
        )
    return out, shortcuts


def build_api_stores(*, refresh: bool, offline: bool) -> list[dict[str, Any]]:
    """Every store the store finder pages through (10 a page)."""
    out: list[dict[str, Any]] = []
    page = 0
    while True:
        data = get_json(STORES_URL.format(page=page), refresh=refresh, offline=offline)
        out.extend(cast(list[dict[str, Any]], data.get("results") or []))
        pages = int(cast(dict[str, Any], data.get("pagination") or {}).get("numberOfPages") or 1)
        page += 1
        if page >= pages:
            return out


def cmd_api(args: argparse.Namespace) -> None:
    cats, shortcuts = build_categories(refresh=args.refresh, offline=args.offline)
    write_lines(L3 / "categories.json", cats)
    (CACHE / "shortcuts.json").write_text(json.dumps(shortcuts, ensure_ascii=False), "utf-8")
    log(f"L3/categories.json: {len(cats)} categories")
    stores = build_api_stores(refresh=args.refresh, offline=args.offline)
    log(f"stores API: {len(stores)} stores")


# ─── Pages and stores, in the browser ─────────────────────────────────────────


def _playwright_module() -> str:
    if env := os.environ.get("PLAYWRIGHT_MODULE"):
        return env
    demos = HERE.parents[2]
    for base in sorted(demos.glob("*/extension/node_modules")):
        for rel in ("playwright/index.mjs", "@playwright/test/index.mjs"):
            if (base / rel).exists():
                return str(base / rel)
    raise SystemExit(
        "STOP: no Playwright found. Set PLAYWRIGHT_MODULE to node_modules/playwright/index.mjs "
        "(npm i playwright && npx playwright install chromium)"
    )


def _node(*args: str) -> None:
    if shutil.which("node") is None:
        raise SystemExit("STOP: node is not on PATH")
    env = {**os.environ, "PLAYWRIGHT_MODULE": _playwright_module()}
    subprocess.run(["node", str(HERE / "crawl.mjs"), *args], check=True, env=env)


def _crawl_pages(urls: list[str], out: Path, *, refresh: bool, offline: bool) -> dict[str, Any]:
    if out.exists() and not refresh:
        have = cast(dict[str, Any], json.loads(out.read_text(encoding="utf-8")))
        if all(u in have and "error" not in have[u] for u in urls):
            return have
    if offline:
        raise SystemExit(f"STOP: {out} lacks pages and --offline was given")
    out.parent.mkdir(parents=True, exist_ok=True)
    _node("pages", str(out), *urls)
    return cast(dict[str, Any], json.loads(out.read_text(encoding="utf-8")))


def _kind(path: str) -> str:
    """The page kinds ``PageChanged`` reports."""
    if path == "/":
        return "home"
    if path == "/nuestras-tiendas":
        return "stores"
    if path == "/carro":
        return "cart"
    if path == "/cotizacion":
        return "quote"
    if path in POLICY:
        return "policy"
    return "page"


_MONEY = re.compile(r"\$\s?\d{1,3}(?:\.\d{3})+|\$\s?\d+")


def _scrub(text: str) -> str:
    """Page text without a peso amount: a sentence that names one is dropped."""
    if not _MONEY.search(text):
        return text
    parts = re.split(r"(?<=[.!?·])\s+", text)
    return " ".join(p for p in parts if not _MONEY.search(p)).strip()


#: A contest winner's name and masked RUT ("Álvaro … 16.747.XXX-X"): a private
#: person, never copied into a public file.
_PERSON = re.compile(r"\d{1,2}\.\d{3}\.X{3}-X")


def _short(text: str, limit: int = MAX_ANSWER) -> str:
    if _PERSON.search(text):
        return ""
    text = _scrub(text)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind(": "))
    return (cut[: end + 1] if end > limit // 2 else cut.rsplit(" ", 1)[0]) + " …"


def _mentions_autoplanet(raw: dict[str, Any]) -> bool:
    blob = json.dumps([raw.get("sections"), raw.get("faqs")], ensure_ascii=False)
    return "autoplanet" in blob.lower()


#: The home's blocks with no title of their own: what the visitor sees there.
#: Tiles and banners are images with the words baked in, so they are named by the
#: categories they link to.
_BLOCK_LABELS = {
    "hero": "Carrusel principal",
    "brands": "Marcas",
}


def _home_sections(
    raw: dict[str, Any], names: dict[str, str], *, refresh: bool, offline: bool
) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for b in cast(list[dict[str, Any]], raw.get("blocks") or []):
        label = str(b["label"])
        links = [str(h) for h in b.get("links") or []]
        cats: list[str] = []
        for h in links:
            if h.startswith("/categoria/"):
                code = _code(h)
                if code not in names:
                    listing = get_json(
                        LISTING_URL.format(code=code), refresh=refresh, offline=offline
                    )
                    names[code] = _clean(listing.get("name")) or code
                cats.append(names[code])
        brands = [
            urllib.parse.unquote(urllib.parse.unquote(h.rsplit("/", 1)[-1]))
            for h in links
            if h.startswith("/marca/")
        ]
        tiles = [str(t) for t in b.get("tiles") or []]
        heading = str(b.get("heading") or "")
        products = int(b.get("products") or 0)
        if label in _BLOCK_LABELS:
            name = _BLOCK_LABELS[label]
        elif tiles:
            name = "Categorías destacadas"
        elif products and not heading:
            name = "Productos destacados"
        else:
            name = "Banners de categorías"
        text_bits: list[str] = []
        if products:
            text_bits.append(f"{products} productos en carrusel")
        if cats:
            text_bits.append("Enlaces a: " + ", ".join(dict.fromkeys(cats)))
        if brands:
            text_bits.append("Marcas: " + ", ".join(brands))
        section: dict[str, Any] = {
            "heading": heading or f"[{name}]",
            "level": 2,
            "selector": b.get("selector") or "",
            "text": " · ".join(text_bits),
            "items": tiles or list(dict.fromkeys(cats)),
        }
        if heading and re.search(
            r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)",
            heading,
            re.I,
        ):
            # The featured carousel's title names the month and changes with it.
            section["volatile"] = True
        sections.append(section)
    return sections


def _page_entry(
    path: str,
    raw: dict[str, Any],
    names: dict[str, str],
    cards: list[dict[str, Any]],
    *,
    refresh: bool,
    offline: bool,
) -> dict[str, Any]:
    if path == "/":
        sections = _home_sections(raw, names, refresh=refresh, offline=offline)
    else:
        sections = [
            {
                "heading": s["heading"],
                "level": s["level"],
                "selector": s.get("selector", ""),
                "text": _scrub(s.get("text", "")),
                "items": s.get("items", []),
            }
            for s in cast(list[dict[str, Any]], raw.get("sections") or [])
        ]
    if path == "/nuestras-tiendas":
        sections.append(
            {
                "heading": "[Tiendas]",
                "level": 2,
                "selector": ".listStoreFinder",
                "text": "Filtro 'Seleccionar región*' y botón 'Limpiar'; 10 tiendas por página, "
                "paginación 'Anterior' / 'Continuar'.",
                "items": [c["name"] for c in cards],
            }
        )
    if path == "/cotizacion":
        labels = [str(x) for x in raw.get("labels") or []]
        for s in sections:
            if s["heading"] == "Formulario de cotización":
                s["items"] = [x for x in labels if x != s["heading"]]
                s["text"] = ""
    faqs = [
        {
            "q": f["q"],
            "a": _short(f.get("a", "")),
            "section": f.get("section", ""),
            "selector": f.get("selector", ""),
        }
        for f in cast(list[dict[str, Any]], raw.get("faqs") or [])
        if f.get("q")
    ]
    entry: dict[str, Any] = {
        "path": path,
        "url": SITE + path,
        "type": _kind(path),
        "title": raw.get("title", ""),
        "description": raw.get("description", ""),
        "h1": raw.get("h1", ""),
        "sections": sections,
        "faqs": faqs,
    }
    if _mentions_autoplanet(raw):
        # The text is shared with the sister site and names Autoplanet / autoplanet.cl.
        entry["autoplanet_text"] = True
    return entry


def build_pages(
    names: dict[str, str], cards: list[dict[str, Any]], *, refresh: bool, offline: bool
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    urls = [SITE + p for p in PAGES]
    got = _crawl_pages(urls, CACHE / "pages.json", refresh=refresh, offline=offline)
    pages: list[dict[str, Any]] = []
    chrome: dict[str, Any] = {}
    for url in urls:
        raw = cast(dict[str, Any], got.get(url) or {})
        if not raw or "error" in raw:
            log(f"  skipped {url}: {str(raw.get('error', 'missing'))[:120]}")
            continue
        final = str(raw.get("final", url)).split("?")[0].rstrip("/") or SITE
        if final != (url.rstrip("/") or SITE):
            log(f"  skipped {url}: redirected to {final}")
            continue
        path = url[len(SITE) :] or "/"
        if raw.get("chrome"):
            chrome = cast(dict[str, Any], raw["chrome"])
        pages.append(_page_entry(path, raw, names, cards, refresh=refresh, offline=offline))
    return pages, chrome


def build_stores(*, refresh: bool, offline: bool) -> list[dict[str, Any]]:
    out = CACHE / "stores.json"
    if refresh or not out.exists():
        if offline:
            raise SystemExit("STOP: store cards are not cached and --offline was given")
        _node("stores", str(out))
    cards = cast(list[dict[str, Any]], json.loads(out.read_text(encoding="utf-8"))["cards"])
    api = {
        _clean(s.get("displayName")): s for s in build_api_stores(refresh=False, offline=offline)
    }
    stores: list[dict[str, Any]] = []
    for c in cards:
        s = api.get(c["name"])
        if s is None:
            log(f"  store card {c['name']!r} has no API entry")
            s = {}
        addr = cast(dict[str, Any], s.get("address") or {})
        commune = cast(dict[str, Any], addr.get("commune") or {})
        region = cast(dict[str, Any], addr.get("region") or {})
        geo = cast(dict[str, Any], s.get("geoPoint") or {})
        hours = [str(h) for h in c.get("hours") or []]
        stores.append(
            {
                "id": str(s.get("name") or ""),
                "name": c["name"],
                "address": c["address"],
                "city": _clean(commune.get("name")),
                "town": _clean(addr.get("town")),
                "region": _clean(region.get("name")),
                "region_code": _clean(region.get("isocode")),
                "phone": c.get("phone") or _clean(addr.get("phone")),
                "hours": "; ".join(hours),
                "hours_lines": hours,
                "lat": geo.get("latitude"),
                "lng": geo.get("longitude"),
                "maps": c.get("maps", ""),
            }
        )
    return stores


def cmd_crawl(args: argparse.Namespace) -> None:
    stores = build_stores(refresh=args.refresh, offline=args.offline)
    write_lines(L3 / "stores.json", stores)
    log(f"L3/stores.json: {len(stores)} stores")
    cats = json.loads((L3 / "categories.json").read_text(encoding="utf-8"))
    names = {c["code"]: c["page_name"] or c["name"] for c in cats}
    cards = [{"name": s["name"]} for s in stores]
    pages, chrome = build_pages(names, cards, refresh=args.refresh, offline=args.offline)
    write_lines(L3 / "pages.json", pages)
    (CACHE / "chrome.json").write_text(json.dumps(chrome, ensure_ascii=False), "utf-8")
    log(
        f"L3/pages.json: {len(pages)} pages, {sum(len(p['sections']) for p in pages)} sections, "
        f"{sum(len(p['faqs']) for p in pages)} panels"
    )


# ─── Maps: site.json and the generated L2 topics ───────────────────────────────

#: What the crawl showed about the site, for whoever drives it: hand-kept,
#: re-checked on each crawl.
NOTES = [
    "Angular SPA (Angular Material) on Firebase Hosting; data from api.agroplanet.cl/webapi "
    "(SAP Hybris behind a JSON facade; public GET; the cart is the JSESSIONID cookie, so "
    "fetch(url, {credentials: 'include'}) from the page shares the visitor's cart).",
    "Every in-site navigation is client-side: category, product, search (/busqueda/<text>), "
    "listing state (?q=<hybris query>&page=<0-based>&sort=), /carro, /cotizacion. Only a reload "
    "or a typed URL loads the document. Menu entries are <a> without href (router clicks); "
    "product cards, breadcrumbs, sub-category links and footer links have real hrefs.",
    "Category URL = /categoria/<any slug>/<code>: the router resolves by code, so the flyout's "
    "and the red bar's different slugs (lubricantes_y_fluidos vs lubricantes, both AG01) are the "
    "same page. Codes: level 1 AGnn, level 2 AGnnn, level 3 numeric.",
    "The flyout names a category one way and its listing another ('Lubricantes Y Fluidos' is "
    "titled 'Lubricantes y Grasas' on its page): categories.json keeps both, name and page_name.",
    "Listing filters are mat-expansion panels titled as the API names them ('Precio', 'Marca', "
    "'Viscosidad', 'Cca (-18 Grados)'…); only 'Precio' is open by default; option labels are the "
    "API's names without counts. A category page shows its sub-categories as links, not as a "
    "'Categoría' filter (search results do show 'Categoría'). Sort: 'Relevancia', 'Menor precio', "
    "'Mayor precio'. No result count is printed on the page.",
    "No checkout and no online payment: the cart's only action is 'Cotizar' → /cotizacion, the "
    "'Formulario de cotización', ending in 'Crear cotización' (needs RUT). Payment for a quote is "
    "off-site, through the Webpay link in the top bar and footer.",
    "Some products show 'Confirmar precio en tienda' instead of a price (hidePriceByCategory). "
    "Every product page says the price may change with another pickup store or delivery mode.",
    "A full load of / opens an empty dialog (app-generic-dialog) that blocks scrolling until closed. "
    "Cookie bar 'Entendido' at the bottom. After scrollY ≈150 a 64 px sticky header appears.",
    "The home's titled blocks are 'Aprovecha estas oportunidades en <Mes>' (changes monthly) and "
    "'CATEGORÍAS'; the other blocks are image banners and carousels with no text heading.",
    "Much of the policy text is shared with the sister site Autoplanet and names Autoplanet / "
    "autoplanet.cl; pages.json marks those pages autoplanet_text.",
    "ayuda.agroplanet.cl (help centre, T&C) opens in a new tab and did not answer from India; its "
    "2023 copies on the Wayback Machine are the source of the 'terminos' topic.",
]


def cmd_maps(args: argparse.Namespace) -> None:
    cats = json.loads((L3 / "categories.json").read_text(encoding="utf-8"))
    pages = json.loads((L3 / "pages.json").read_text(encoding="utf-8"))
    stores = json.loads((L3 / "stores.json").read_text(encoding="utf-8"))
    shortcuts_path = CACHE / "shortcuts.json"
    shortcuts = (
        json.loads(shortcuts_path.read_text(encoding="utf-8")) if shortcuts_path.exists() else []
    )
    chrome_path = CACHE / "chrome.json"
    chrome = json.loads(chrome_path.read_text(encoding="utf-8")) if chrome_path.exists() else {}

    def link(x: dict[str, Any]) -> dict[str, Any]:
        text = x.get("text") or ("webpay" if "webpay" in x.get("href", "") else "")
        href = x.get("href", "")
        if text == "Tiendas" and not href:
            # The top bar's "Tiendas" is a router click with no href.
            href = "/nuestras-tiendas"
        return {"text": text, "href": href, "new_tab": bool(x.get("new_tab"))}

    footer_links = [link(x) for x in chrome.get("footer_links") or []]
    site = {
        "site": "www.agroplanet.cl",
        "crawled": CRAWLED,
        # "Todas las categorías", in the flyout's order.
        "nav": [
            {"code": c["code"], "name": c["name"], "path": c["path"]}
            for c in cats
            if c["level"] == 1
        ],
        "shortcuts": shortcuts,
        "top_bar": [link(x) for x in chrome.get("top_bar") or []],
        "footer": footer_links,
        "footer_text": chrome.get("footer_text") or [],
        "whatsapp": chrome.get("whatsapp", ""),
        "redirects": REDIRECTS,
        "notes": NOTES,
    }
    (L3 / "site.json").write_text(
        json.dumps(site, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    lines = [
        "# Mapa del sitio",
        "",
        f"Sources: www.agroplanet.cl, read in a headless browser after scrolling each page — "
        f"crawled {CRAWLED}. Generated by build.py maps; the headings and accordion panel titles "
        "are the ones `{show:}` and `{faq:}` cues name. A heading in [brackets] is a block with "
        "no text heading on the page.",
        "",
    ]
    for p in pages:
        # Every title ends "| Agroplanet | Más de 10.000 productos…": keep the page's part.
        lines.append(f"## {p['title'].split(' | ')[0] or p['path']}")
        flag = ", texto compartido con Autoplanet" if p.get("autoplanet_text") else ""
        lines.append(f"`{p['path']}` ({p['type']}{flag})")
        heads = [
            s["heading"] + (" (cambia cada mes)" if s.get("volatile") else "")
            for s in p["sections"]
        ]
        if heads:
            lines.append("- Secciones: " + " · ".join(heads))
        if p["faqs"]:
            lines.append("- Paneles: " + " · ".join(f["q"] for f in p["faqs"]))
        lines.append("")
    L2.mkdir(parents=True, exist_ok=True)
    (L2 / "site-map.md").write_text("\n".join(lines), encoding="utf-8")

    by_parent: dict[str, list[dict[str, Any]]] = {}
    for c in cats:
        by_parent.setdefault(c["parent"], []).append(c)
    out = [
        "# Categorías",
        "",
        f"Sources: {MENU_URL} (the site's own 'Todas las categorías' menu) and each listing's "
        f"filters from api.agroplanet.cl — read {CRAWLED}. Generated by build.py maps. Any slug "
        "works before the code (/categoria/<slug>/<code>). Counts are the products listed that "
        "day, for scale only. Names are the menu's; the page's own title follows in quotes where "
        "it differs.",
        "",
        "Barra roja (atajos): " + " · ".join(f"{s['name']} `{s['path']}`" for s in shortcuts),
        "",
    ]

    def facet_line(c: dict[str, Any]) -> str:
        bits: list[str] = []
        for f in c["facets"]:
            if f["param"] == "price":
                bits.append("Precio (rangos)")
                continue
            more = "…" if f["total"] > len(f["options"]) else ""
            bits.append(f"{f['name']}: " + ", ".join(f["options"]) + more)
        return "; ".join(bits)

    def label(c: dict[str, Any]) -> str:
        page = f' "{c["page_name"]}"' if c["page_name"] and c["page_name"] != c["name"] else ""
        n = f", {c['products']} productos" if c["products"] is not None else ""
        return f"{c['name']}{page} ({c['code']}{n}) `{c['path']}`"

    for top in by_parent.get("", []):
        out.append(f"## {label(top)}")
        if top["facets"]:
            out.append(f"- Filtros — {facet_line(top)}")
        for c2 in by_parent.get(top["path"], []):
            out.append(f"- **{label(c2)}**")
            if c2["facets"]:
                out.append(f"  - Filtros — {facet_line(c2)}")
            for c3 in by_parent.get(c2["path"], []):
                out.append(f"  - {label(c3)}")
        out.append("")
    (L2 / "categorias.md").write_text("\n".join(out), encoding="utf-8")

    footer_text = [str(x) for x in chrome.get("footer_text") or []]
    footer_hours = ""
    if "HORARIOS DE TIENDAS" in footer_text:
        rest = footer_text[footer_text.index("HORARIOS DE TIENDAS") + 1 :]
        block = rest[: next((i for i, x in enumerate(rest) if x.isupper()), len(rest))]
        footer_hours = ", ".join(" ".join(block[i : i + 2]) for i in range(0, len(block), 2))
    t = [
        "# Tiendas Agroplanet",
        "",
        f"Sources: www.agroplanet.cl/nuestras-tiendas (the cards as the page writes them, all "
        f"pages) and api.agroplanet.cl store finder (code, comuna, región, coordinates) — read "
        f"{CRAWLED}. Generated by build.py maps. {len(stores)} tiendas, in the page's order. "
        f"The footer's general hours are '{footer_hours}'; each store's own hours below are "
        "the ones to give. The page shows "
        "ABIERTO / CERRADO beside each store at the moment it is read (not kept here).",
        "",
    ]
    by_region: dict[str, list[dict[str, Any]]] = {}
    for s in stores:
        by_region.setdefault(s["region"] or "—", []).append(s)
    t.append(
        "Por región: "
        + "; ".join(f"{r}: {', '.join(x['name'] for x in xs)}" for r, xs in by_region.items())
    )
    t.append("")
    for s in stores:
        t.append(f"## {s['name']} ({s['id']})")
        t.append(f"- Dirección: {s['address']}")
        t.append(f"- Comuna: {s['city']} · Región: {s['region']}")
        t.append(f"- Teléfono: {s['phone']}")
        t.append("- Horarios de Atención: " + "; ".join(s["hours_lines"]))
        t.append("")
    (L2 / "tiendas.md").write_text("\n".join(t), encoding="utf-8")
    log("L3/site.json, L2/site-map.md, L2/categorias.md, L2/tiendas.md written")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("command", choices=["api", "crawl", "maps", "all"])
    ap.add_argument("--refresh", action="store_true", help="refetch what the cache holds")
    ap.add_argument("--offline", action="store_true", help="never touch the network")
    args = ap.parse_args()
    if args.command in ("api", "all"):
        cmd_api(args)
    if args.command in ("crawl", "all"):
        cmd_crawl(args)
    if args.command in ("maps", "all"):
        cmd_maps(args)


if __name__ == "__main__":
    main()
