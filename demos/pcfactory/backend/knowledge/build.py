"""Rebuild the generated parts of the PC Factory knowledge from www.pcfactory.cl.

Run from ``voqalize/demos``::

    uv run python pcfactory/backend/knowledge/build.py api      # menu + facets → L3/categories.json
    uv run python pcfactory/backend/knowledge/build.py crawl    # pages + stores → L3/pages.json, L3/stores.json
    uv run python pcfactory/backend/knowledge/build.py maps     # L3/site.json, L2/site-map.md, L2/categorias.md
    uv run python pcfactory/backend/knowledge/build.py all      # the three, in that order

``--refresh`` refetches what the cache already holds; ``--offline`` never touches
the network and rebuilds from the cache alone.

Two sources, both public and read-only:

- **The catalogue API** (``api.pcfactory.cl``, no auth, CORS ``*``): the category
  tree the site's own menu is drawn from, and the filter groups each listing
  offers. Paced to one request a second.
- **The pages, in a real browser** (``crawl.mjs`` beside this file, run with
  node): the site is Modyo pages with Vue widgets mounted after load, and its
  coupon cards, product rails and FAQ accordions only exist after JS runs and the
  page is scrolled. Headings recorded here are what ``{show:}`` cues name and FAQ
  questions what ``{faq:}`` cues name, so they must be what a visitor sees.
  Playwright is not a demos dependency: set ``PLAYWRIGHT_MODULE`` to an
  installed copy's entry module (``.../node_modules/playwright/index.mjs`` or
  ``.../node_modules/@playwright/test/index.mjs``), or let this script find one
  under ``demos/*/extension/node_modules``.

Every response is cached under ``~/.cache/voqalize-pcfactory``. Nothing here logs
in, submits a form or touches the cart. **No price and no stock level is written
to any file**: the facet "Rango de precios" (a min/max price) is dropped, and
section text inside product cards is never read (``crawl.mjs`` skips them).

The hand-written files (``L1.md`` and the other ``L2/*.md``) are not touched:
re-read them against a new crawl, since campaigns, coupons and store hours change
every week.
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
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
L2 = HERE / "L2"
L3 = HERE / "L3"
CACHE = Path(os.environ.get("PCFACTORY_CACHE", Path.home() / ".cache" / "voqalize-pcfactory"))
SITE = "https://www.pcfactory.cl"
API = "https://api.pcfactory.cl"
MENU_URL = f"{API}/api-dex-catalog/v1/catalog/category/PCF/menu"
FACETS_URL = (
    f"{API}/pcfactory-services-catalogo/v1/catalogo/productos/query/facets?categorias={{id}}"
)
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)
CRAWLED = time.strftime("%Y-%m-%d")

#: The pages the brain knows by heading and FAQ. The Centro de ayuda topics are
#: found on its hub (every ``/centro-de-ayuda/<topic>`` link), so a new topic is
#: picked up without editing this list. Category landing pages are added from
#: the menu's top level.
PAGES = [
    "/",
    "/tiendas",
    "/categorias",
    "/centro-de-ayuda",
    "/empresas",
    "/arma-tu-pc",
    "/cyber",
    "/gamer",
    "/outlet-tecnologico",
    "/lenovo-week",
    "/black-days",
    "/estado-despacho",
    "/servicios/asesorate-online",
]

#: Facet groups the API names differently from the listing's checkboxes, and
#: the label the listing writes for an option the API leaves blank. Both read
#: off the notebooks and NVIDIA listings in a browser (``crawl.mjs facets``).
FACET_NAMES = {"Sucursales": "Tiendas"}
BLANK_OPTION = "Otros"
#: Not kept per category: a price range is a price, and the store list is the
#: same 28 stores (plus "Internet") on every listing; ``stores.json`` has them.
FACETS_DROPPED = {"Rango de precios", "Tiendas"}
MAX_OPTIONS = 25

_last_request = 0.0


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# ─── Network, cached and paced ─────────────────────────────────────────────────


def _cache_path(url: str) -> Path:
    key = re.sub(r"[^A-Za-z0-9]+", "_", url.split("://", 1)[-1]).strip("_")
    return CACHE / "api" / f"{key[:180]}.json"


def get_json(url: str, *, refresh: bool, offline: bool) -> Any:
    """``url``'s JSON, from the cache when it has it; at most one request a second."""
    global _last_request
    path = _cache_path(url)
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    if offline:
        raise SystemExit(f"STOP: {url} is not cached and --offline was given")
    wait = 1.0 - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"STOP: {url} answered {exc.code}") from exc
    finally:
        _last_request = time.monotonic()
    data = json.loads(body)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def page_status(path: str) -> tuple[int, str]:
    """A page's status and Location, without following the redirect: a category
    path the site does not know redirects to home with a 302."""
    global _last_request
    wait = 1.0 - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(SITE + path, headers={"User-Agent": UA})
    try:
        with opener.open(req, timeout=30) as resp:
            return resp.status, ""
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Location", "")
    finally:
        _last_request = time.monotonic()


# ─── Categories ────────────────────────────────────────────────────────────────


def _walk(nodes: list[dict[str, Any]], parent: str, level: int, out: list[dict[str, Any]]) -> None:
    for n in nodes:
        path = "/categoria" + n["link"]
        out.append(
            {
                "id": n["id"],
                "path": path,
                "name": n["nombre"].strip(),
                "parent": parent,
                "level": level,
            }
        )
        _walk(n.get("childCategories") or [], path, level + 1, out)


def _facets(raw: dict[str, Any]) -> tuple[list[dict[str, Any]], int | None]:
    """The listing's filter groups as its checkboxes write them, and the number
    of products (the brand counts add up to it: every product has one brand)."""
    groups: list[dict[str, Any]] = []
    products: int | None = None
    for g in raw.get("items") or []:
        raw_name = str(g["nombre"]).strip()
        name = FACET_NAMES.get(raw_name, raw_name)
        if g.get("param") == "marcas":
            products = sum(int(i.get("count") or 0) for i in g.get("items") or [])
        if name in FACETS_DROPPED:
            continue
        options: list[str] = []
        for i in g.get("items") or []:
            label = str(i.get("valor") or "").strip() or BLANK_OPTION
            if label not in options:
                options.append(label)
        if options:
            groups.append(
                {"name": name, "param": g.get("param", ""), "options": options[:MAX_OPTIONS]}
            )
    return groups, products


def build_categories(*, refresh: bool, offline: bool) -> list[dict[str, Any]]:
    menu = get_json(MENU_URL, refresh=refresh, offline=offline)
    nodes: list[dict[str, Any]] = []
    _walk(menu, "", 1, nodes)
    paths_by_id: dict[int, list[str]] = {}
    for n in nodes:
        paths_by_id.setdefault(n["id"], []).append(n["path"])
    facet_cache: dict[int, tuple[list[dict[str, Any]], int | None]] = {}
    ids = list(dict.fromkeys(n["id"] for n in nodes))
    log(f"menu: {len(nodes)} nodes, {len(ids)} category ids")
    for i, cid in enumerate(ids, 1):
        raw = get_json(FACETS_URL.format(id=cid), refresh=refresh, offline=offline)
        facet_cache[cid] = _facets(raw)
        if i % 25 == 0:
            log(f"  facets {i}/{len(ids)}")
    out: list[dict[str, Any]] = []
    for n in nodes:
        groups, products = facet_cache[n["id"]]
        out.append(
            {
                **n,
                "aliases": [p for p in paths_by_id[n["id"]] if p != n["path"]],
                "products": products,
                # Level 1 is a landing page of sub-category tiles; its facets
                # are the union of everything under it and help nobody choose.
                "facets": groups if n["level"] >= 2 else [],
            }
        )
    return out


def write_lines(path: Path, items: list[dict[str, Any]]) -> None:
    """A JSON list with one object a line: diffs stay readable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = ",\n".join(json.dumps(i, ensure_ascii=False, separators=(",", ":")) for i in items)
    path.write_text(f"[\n{body}\n]\n", encoding="utf-8")


def cmd_api(args: argparse.Namespace) -> None:
    cats = build_categories(refresh=args.refresh, offline=args.offline)
    write_lines(L3 / "categories.json", cats)
    log(f"L3/categories.json: {len(cats)} categories")
    if not args.offline:
        checks = {}
        for path in (
            "/categoria/computadores-y-tablets/notebooks/notebooks",
            "/categoria/partes-y-piezas-componentes/tarjetas-graficas",
            "/categoria/monitores-y-proyectores/monitores",
            "/computadores-y-tablets/notebooks/notebooks",
        ):
            status, location = page_status(path)
            checks[path] = f"{status} {location}".strip()
            log(f"  {path}: {checks[path]}")
        cache = CACHE / "path-checks.json"
        cache.write_text(json.dumps(checks, ensure_ascii=False, indent=1), encoding="utf-8")


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
        have = json.loads(out.read_text(encoding="utf-8"))
        if all(u in have and "error" not in have[u] for u in urls):
            return have
    if offline:
        raise SystemExit(f"STOP: {out} lacks pages and --offline was given")
    out.parent.mkdir(parents=True, exist_ok=True)
    _node("pages", str(out), *urls)
    return json.loads(out.read_text(encoding="utf-8"))


def _kind(path: str) -> str:
    if path == "/":
        return "home"
    if path.startswith("/categoria"):
        return "category"
    if path.startswith("/centro-de-ayuda"):
        return "help"
    if path == "/tiendas":
        return "stores"
    if path in ("/cyber", "/gamer", "/lenovo-week", "/black-days", "/outlet-tecnologico"):
        return "event"
    return "page"


_MONEY = re.compile(r"\$\s?\d{1,3}(?:\.\d{3})+")
#: A peso amount may stay only beside the words of a coupon or a condition
#: ("$50.000 dcto.", "compra mínima"), never as a product's price.
_MONEY_OK = re.compile(r"dcto|descuento|cup[oó]n|m[ií]nim|sobre|desde|hasta|adicional", re.I)


def _scrub(text: str) -> str:
    parts = text.split(" · ")
    kept = []
    for i, part in enumerate(parts):
        if _MONEY.search(part):
            near = " ".join(parts[max(0, i - 2) : i + 3])
            if not _MONEY_OK.search(near):
                continue
        kept.append(part)
    return " · ".join(kept)


def _page_entry(path: str, raw: dict[str, Any]) -> dict[str, Any]:
    sections: list[dict[str, Any]] = []
    for s in raw.get("sections") or []:
        if path == "/tiendas" and s["level"] == 6 and sections and sections[-1]["level"] == 3:
            # A store card's "Ciudad - Región" line under its name: part of the card.
            prev = sections[-1]
            prev["text"] = " · ".join(t for t in (prev["text"], s["heading"]) if t)
            continue
        sections.append(
            {
                "heading": s["heading"],
                "level": s["level"],
                "selector": s.get("selector", ""),
                "text": _scrub(s.get("text", "")),
                "items": s.get("items", []),
            }
        )
    faqs = [
        {
            "q": f["q"],
            # The hub shows an answer's first lines and a "Ver más" link.
            "a": re.sub(r"\s*\.\.\.\s*Ver más$", "…", f["a"]),
            "section": f.get("section", ""),
            "selector": f.get("selector", ""),
            # Términos y condiciones shows one chapter at a time; the others
            # appear when their menu link is clicked.
            **({"hidden": True} if f.get("hidden") else {}),
        }
        for f in raw.get("faqs") or []
        if f.get("q")
    ]
    return {
        "path": path,
        "url": SITE + path,
        "type": _kind(path),
        "title": raw.get("title", ""),
        "description": raw.get("description", ""),
        "h1": raw.get("h1", ""),
        "sections": sections,
        "faqs": faqs,
    }


def build_pages(*, refresh: bool, offline: bool) -> list[dict[str, Any]]:
    menu = get_json(MENU_URL, refresh=False, offline=offline)
    first = [SITE + p for p in PAGES]
    got = _crawl_pages(first, CACHE / "pages-1.json", refresh=refresh, offline=offline)
    hub = got.get(SITE + "/centro-de-ayuda", {})
    topics = sorted(
        {
            re.sub(r"[?#].*", "", link).rstrip("/")
            for link in hub.get("links") or []
            if re.match(re.escape(SITE) + r"/centro-de-ayuda/[a-z0-9-]+/?(?:[?#].*)?$", link)
        }
    )
    tops = [SITE + "/categoria" + n["link"] for n in menu]
    more = _crawl_pages(topics + tops, CACHE / "pages-2.json", refresh=refresh, offline=offline)
    pages: list[dict[str, Any]] = []
    for url, raw in {**got, **more}.items():
        if "error" in raw:
            log(f"  skipped {url}: {raw['error'][:120]}")
            continue
        final = raw.get("final", url).split("?")[0].rstrip("/") or SITE
        asked = url.rstrip("/") or SITE
        if final != asked:
            # A campaign that has ended redirects (usually home): not a page.
            log(f"  skipped {url}: redirected to {final}")
            continue
        path = url[len(SITE) :] or "/"
        pages.append(_page_entry(path, raw))
    return pages


_TAGS = re.compile(r"<[^>]+>")


def _hours_from_card(card: str) -> str:
    """The "Horarios" lines of a store's map card, joined with "; "."""
    if "Horarios" not in card:
        return ""
    body = card.split("Horarios", 1)[1]
    body = re.split(r"\n\s*(?:Jefe de tienda|Ver en google maps|Teléfono)", body)[0]
    lines = [" ".join(line.split()) for line in body.splitlines()]
    return "; ".join(line for line in lines if line)


def _address_from_card(card: str) -> str:
    """The "Dirección" line of a store's map card, without its "pc Factory - " prefix."""
    m = re.search(r"Dirección\s*\n\s*(.+)", card)
    return re.sub(r"^pc Factory\s*-\s*", "", m.group(1).strip()) if m else ""


def _hours_from_field(html: str) -> str:
    text = _TAGS.sub("\n", re.sub(r"<!--.*?-->", "", html or "", flags=re.S)).replace("&nbsp;", " ")
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "; ".join(line for line in lines if line)


def build_stores(*, refresh: bool, offline: bool) -> list[dict[str, Any]]:
    out = CACHE / "stores.json"
    if refresh or not out.exists():
        if offline:
            raise SystemExit("STOP: stores are not cached and --offline was given")
        _node("stores", str(out))
    data = json.loads(out.read_text(encoding="utf-8"))
    cards: dict[str, str] = data.get("cards") or {}
    # The stock API names some stores differently ("Copiapó" for "Mall Plaza
    # Copiapó"); its ids match the store entries' own ``id``. Any product's
    # stock lists every store, so one product id is enough.
    stock_names: dict[str, tuple[str, str]] = {}
    for pid in (57233, 57695):
        try:
            stock = get_json(
                f"{API}/pcfactory-services-catalogo/v1/catalogo/productos/{pid}/stock",
                refresh=False,
                offline=offline,
            )
        except SystemExit:
            continue
        for zone in stock.get("disponibilidad") or []:
            for s in zone.get("sucursales") or []:
                stock_names[str(s["id"])] = (s["nombre"], zone["zona"])
        if stock_names:
            break
    stores = []
    for s in data.get("stores") or []:
        meta, f = s["meta"], s["fields"]
        addr = (f.get("Direccion") or [{}])[0]
        name = meta["name"].strip()
        card = cards.get(name, "")
        hours = _hours_from_card(card)
        stock_name, stock_zone = stock_names.get(str(f.get("id")), ("", ""))
        stores.append(
            {
                "id": str(f.get("id") or ""),
                "name": name,
                "zone": meta.get("category") or "",
                "address": _address_from_card(card) or (addr.get("location_street") or "").strip(),
                "local": (f.get("Local") or "").strip(),
                "city": (addr.get("administrative_area_level_3") or f.get("Comuna") or "").strip(),
                "region": (addr.get("administrative_area_level_1") or "").strip(),
                "hours": hours,
                "hours_source": "card" if hours else "",
                "entry_hours": _hours_from_field(f.get("Horario", "")),
                "notice": (f.get("Disclaimer") or "").strip(),
                "stock_name": stock_name,
                "stock_zone": stock_zone,
                "phone": (f.get("Telefono") or "").strip(),
            }
        )
    return stores


def cmd_crawl(args: argparse.Namespace) -> None:
    pages = build_pages(refresh=args.refresh, offline=args.offline)
    write_lines(L3 / "pages.json", pages)
    log(
        f"L3/pages.json: {len(pages)} pages, {sum(len(p['sections']) for p in pages)} sections, "
        f"{sum(len(p['faqs']) for p in pages)} FAQs"
    )
    stores = build_stores(refresh=args.refresh, offline=args.offline)
    write_lines(L3 / "stores.json", stores)
    log(
        f"L3/stores.json: {len(stores)} stores, {sum(1 for s in stores if s['hours'])} with card hours"
    )


# ─── Maps: site.json and the generated L2 topics ───────────────────────────────

#: What the crawl showed about the site, for whoever drives it: hand-kept,
#: re-checked on each crawl.
NOTES = [
    "Modyo DXP pages (Rails, Bootstrap, jQuery) with Vue 2 widgets mounted after load; "
    "catalogue, prices and stock come from api.pcfactory.cl (public GET, CORS *).",
    "Every navigation between page types is a full document load: category, product, search "
    "(/busqueda-avanzada?search=a+b), pagination (&page=N, 1-based), /carro, /checkout. "
    "Filters, sort, add to cart and cart quantity stay in the page (replaceState).",
    "Category URL = /categoria + the menu's link; the bare link without /categoria redirects "
    "(302) to home. The same category id can sit under several parents (aliases).",
    "Listing facets: the API's 'Sucursales' is written 'Tiendas' on the page, and an option the "
    "API leaves blank is written 'Otros'. The Tiendas list shows 'Internet' and the 28 stores "
    "(with a 'Santiago' group label among them). Category listings filter brands by id "
    "(marcas=299), search results by name (marcas=Acer).",
    "There is no search autocomplete: typing fires no request; Enter or the magnifier loads "
    "/busqueda-avanzada.",
    "Three prices on every card and product: 'Transferencia / Débito' (efectivo, the headline), "
    "'Otros medios de pago' (normal, credit card) and the struck precio de referencia the "
    "-N% badge is computed against. The PDP JSON-LD offers.price is the 'Otros medios' price.",
    "Product pages note 'Stock desfasado 20 minutos'. Stock reads 'N disponibles' / '+100 Unid.'.",
    "The cart lives in localStorage.cartProducts; the delivery cost is never shown before "
    "checkout ('El valor del despacho se calculará cuando se seleccione el tipo de entrega').",
    "Store zones disagree: /tiendas files the stores under Norte (5), Santiago (13) and Sur (10), "
    "with Viña del Mar in Norte; the stock API groups them Norte, Santiago, Centro and Sur.",
    "Some store names differ between /tiendas and the stock API and listing filter "
    "(stores.json keeps both: name, stock_name).",
    "A store's map card ('Ver tienda') shows the schedule of the store's group (Mall Plaza, "
    "calle, Cenco …) when it has one, which can differ from the store entry's own text "
    "(stores.json: hours = the card, entry_hours = the entry).",
    "No cookie banner, no first-visit modal, no CSP. pcFactory's own assistance button "
    "(#pcfAssistanceWrapper: Ocular video advisors and TalkCenter chat) sits bottom-right.",
]


def cmd_maps(args: argparse.Namespace) -> None:
    cats = json.loads((L3 / "categories.json").read_text(encoding="utf-8"))
    pages = json.loads((L3 / "pages.json").read_text(encoding="utf-8"))
    checks_path = CACHE / "path-checks.json"
    checks = json.loads(checks_path.read_text(encoding="utf-8")) if checks_path.exists() else {}
    nav = [{"id": c["id"], "name": c["name"], "path": c["path"]} for c in cats if c["level"] == 1]
    site = {
        "site": "www.pcfactory.cl",
        "crawled": CRAWLED,
        "nav": nav,
        "path_checks": checks,
        "notes": NOTES,
    }
    (L3 / "site.json").write_text(
        json.dumps(site, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    lines = [
        "# Mapa del sitio",
        "",
        f"Sources: www.pcfactory.cl, read in a headless browser after scrolling each page — crawled {CRAWLED}. "
        "Generated by build.py maps; the headings and FAQ questions are the ones `{show:}` and "
        "`{faq:}` cues name.",
        "",
    ]
    for p in pages:
        lines.append(f"## {p['title'] or p['path']}")
        lines.append(f"`{p['path']}` ({p['type']})")
        heads = [s["heading"] for s in p["sections"]]
        if heads:
            lines.append("- Secciones: " + " · ".join(heads))
        if p["faqs"]:
            lines.append("- Preguntas: " + " · ".join(f["q"] for f in p["faqs"]))
        lines.append("")
    L2.mkdir(parents=True, exist_ok=True)
    (L2 / "site-map.md").write_text("\n".join(lines), encoding="utf-8")

    by_parent: dict[str, list[dict[str, Any]]] = {}
    for c in cats:
        by_parent.setdefault(c["parent"], []).append(c)
    out = [
        "# Categorías",
        "",
        f"Sources: {MENU_URL} (the site's own menu) and the listing filters of each category "
        f"from api.pcfactory.cl — read {CRAWLED}. Generated by build.py maps. Paths open with "
        "/categoria/. Counts are the products listed that day, for scale only.",
        "",
    ]

    def facet_line(c: dict[str, Any]) -> str:
        bits = []
        for f in c["facets"]:
            if f["name"] == "Marcas":
                bits.append("Marcas: " + ", ".join(f["options"][:12]))
            else:
                bits.append(f"{f['name']}: " + ", ".join(f["options"][:8]))
        return "; ".join(bits)

    for top in by_parent.get("", []):
        out.append(f"## {top['name']} (id {top['id']}) `{top['path']}`")
        for c2 in by_parent.get(top["path"], []):
            n = f", {c2['products']} productos" if c2["products"] is not None else ""
            out.append(f"- **{c2['name']}** (id {c2['id']}{n}) `{c2['path']}`")
            kids = by_parent.get(c2["path"], [])
            for c3 in kids:
                n3 = f", {c3['products']}" if c3["products"] is not None else ""
                out.append(f"  - {c3['name']} (id {c3['id']}{n3}) `{c3['path']}`")
                if c3["facets"]:
                    out.append(f"    - Filtros — {facet_line(c3)}")
            if not kids and c2["facets"]:
                out.append(f"  - Filtros — {facet_line(c2)}")
        out.append("")
    (L2 / "categorias.md").write_text("\n".join(out), encoding="utf-8")
    log("L3/site.json, L2/site-map.md, L2/categorias.md written")


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
