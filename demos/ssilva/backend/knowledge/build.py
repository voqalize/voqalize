# pyright: basic
# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Build Javier's knowledge of ssilva.cl: crawl the site, then render the layers.

Two steps, so the knowledge can be rebuilt without the network and re-crawled
without touching the hand-written parts:

``crawl`` (Playwright and the site's own public endpoints) writes raw dumps to a
directory, by default ``~/.cache/voqalize-ssilva``:

- ``all-projects.json``: every project card from the list's AJAX endpoint
  (``POST /cms/wp-admin/admin-ajax.php``, ``action=projects``), all pages.
- ``property-<id>.json``: the slugs the same endpoint lists for each property
  type, which is how a house or an office is told from a flat (the cards'
  ``project_type`` says "Departamentos" for the houses of Mirador Piedra Roja).
- ``communes.json``: the commune filter, with its ids.
- ``projects.json`` and ``type_projects.json``: ``/wp-json/wp/v2/``, for each
  project's profile (Para vivir, Para invertir, Segunda vivienda).
- ``project-details.json``: each project page rendered and read: its section
  modules in order, hero, intro, tagline, typologies, gallery, amenities title,
  status, contact block, WhatsApp, brochure, lead form ids, tour links.
- ``quote/<slug>.json``: the unit price list a cotizar page carries in its
  ``<quote :data="…">`` attribute, read from the HTML before Vue replaces it.
- ``pages/<name>.json``: the other pages' headings and text.

``render`` turns a raw directory into the committed layers:

- ``L3/projects.json``: the roster, one record per project.
- ``L3/pages.json``: every page Javier may open, with its sections in order.
- ``L3/site.json``: the filters' ids, the navigation, the lead form.
- ``L2/proyectos/<slug>.md``: every fact of one project, for ``read_project``.
- The roster table in ``L1.md``, between its ``roster`` markers. The rest of L1
  and the guides in ``L2/*.md`` are written by hand from the same dumps.

From ``voqalize/demos`` (Playwright is not a demos dependency; its Chromium must
be installed once with ``uv run --with playwright playwright install chromium``)::

    uv run --with playwright python ssilva/backend/knowledge/build.py crawl
    uv run python ssilva/backend/knowledge/build.py render
    uv run python ssilva/backend/knowledge/build.py render --raw /path/to/dumps

Nothing here is filled in from general knowledge: a fact the site does not show
is left out. Where the crawl cannot see something the notes record (Alto Quintay
is a landing page outside the list; the info pages' headings), it is written
down below, with where it came from.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

BASE = "https://www.ssilva.cl"
AJAX = f"{BASE}/cms/wp-admin/admin-ajax.php"
HERE = Path(__file__).parent
RAW = Path.home() / ".cache" / "voqalize-ssilva"

#: The list filter's ids (``select#region``, ``select#property``).
REGION_IDS = {"metropolitana": 17, "valparaiso": 557, "otros": 556}
PROPERTY_IDS = {"departamento": 34, "casa": 193, "oficina": 35, "local": 36}
REGION_LABELS = {
    "metropolitana": "Región Metropolitana",
    "valparaiso": "Región de Valparaíso",
    "otros": "Otros",
}
PROPERTY_LABELS = {
    "departamento": "Departamentos",
    "casa": "Casas",
    "oficina": "Oficinas",
    "local": "Locales comerciales",
}

#: What each page module is, by its first class: the canonical key the page
#: scrolls to (``{show: tipologías}``), and the heading it shows when the crawl
#: did not read one. The tagline and amenities title come from the page.
MODULES: dict[str, tuple[str, str]] = {
    "l3-hero": ("", ""),
    "main-slider-section": ("", ""),
    "l3-numbered-slider-section": ("galería", "Galería"),
    "cotizador-l1-section": ("tipologías", "Tipologías que se adaptan a tus necesidades"),
    "video-tour-section": ("tour", "Recorre los espacios desde donde estés"),
    "alternate-images-section": ("amenidades", ""),
    "l3-project-status-section": ("estado", "Estado del proyecto"),
    "wbct-section": ("brochure", "Brochure"),
    "l3-other-docs-section": ("brochure", "Brochure"),
    "project-actions-section": ("contacto", "¿Te interesó este proyecto?"),
    "map-section": ("", "Ubicación"),
}
#: The project status bar's steps, in order (``.l3-project-status``).
STATUS_STEPS = (
    "En blanco",
    "Inicio de obra",
    "En verde",
    "Obra gruesa",
    "Término de obra",
    "Próxima entrega",
    "Entrega inmediata",
)

#: The pages other than projects, with their headings as the 2026-10-21
#: exploration read them off the screen (site notes §1a and the page outlines).
#: A crawl that reads headings replaces these.
INFO_PAGES: dict[str, dict[str, Any]] = {
    "/": {
        "name": "home",
        "kind": "home",
        "title": "Inicio",
        "headings": [
            "Conoce NUESTROS PROYECTOS",
            "Descubre OPORTUNIDADES DE INVERSIÓN",
            "Compra hoy CON TASA SUBSIDIADA",
            "Somos Ssilva",
            "Te recomendamos",
            "Oportunidades",
            "Destacados",
            "Invierte tranquilo, nosotros nos ocupamos",
        ],
        "text": "Hero slider: Conoce NUESTROS PROYECTOS; Descubre OPORTUNIDADES DE INVERSIÓN; "
        "Compra hoy CON TASA SUBSIDIADA; each with COTIZA CON NOSOTROS. Somos Ssilva, "
        "Conócenos: más de 30 años. Proyectos, Te recomendamos: tabs Oportunidades and "
        "Destacados. Invierte tranquilo, nosotros nos ocupamos: Centro de Negocios.",
    },
    "/proyectos": {
        "name": "proyectos",
        "kind": "projects",
        "title": "Proyectos",
        "headings": ["ENCUENTRA TU NUEVA VIVIENDA"],
        "text": "Every project, 8 per page, with filters: Tipo de propiedad, Región and, for "
        "Región Metropolitana, Sector / Comuna. N proyectos encontrados para tu búsqueda. "
        "Limpiar filtros.",
    },
    "/oportunidades": {
        "name": "oportunidades",
        "kind": "projects",
        "title": "Oportunidades",
        "headings": [
            "ENCUENTRA LA MEJOR OPORTUNIDAD",
            "Calculadora de UF",
            "Conoce proyectos de Segunda vivienda",
            "¡Asesórate aquí para tu búsqueda!",
        ],
    },
    "/centro-de-negocios": {
        "name": "centro-de-negocios",
        "kind": "page",
        "title": "Centro de Negocios",
        "headings": [
            "Centro de Negocios",
            "Más de 40 años impulsando inversiones inmobiliarias",
            "Nuestro Proceso",
            "Buscas Invertir",
            "¿Buscas tu primer hogar?",
            "¡Beneficios y promociones!",
            "Nuestra experiencia nos respalda",
        ],
    },
    "/sobre-nosotros": {
        "name": "sobre-nosotros",
        "kind": "page",
        "title": "Sobre nosotros",
        "headings": [
            "Descubre qué nos inspira",
            "Mucho más que gestión inmobiliaria",
            "Cumplir el sueño de hogar propio",
            "Observa nuestro recorrido",
            "Lo que nos mueve",
            "Visita nuestro Centro de Negocios",
        ],
    },
    "/descubre-inversionistas": {
        "name": "descubre-inversionistas",
        "kind": "page",
        "title": "Descubre",
        "headings": [
            "ENCUENTRA INFORMACIÓN PARA TUS INVERSIONES",
            "INVERSIONISTAS",
            "PRIMERA VIVIENDA",
            "SEGUNDA VIVIENDA",
        ],
    },
    "/ayuda-llamanos": {
        "name": "ayuda-llamanos",
        "kind": "page",
        "title": "Centro de Ayuda",
        "headings": ["Centro de Ayuda", "Tiene alguna duda? Contáctanos"],
    },
    "/vende-tu-terreno": {
        "name": "vende-tu-terreno",
        "kind": "page",
        "title": "Vende tu terreno",
        "headings": ["¿Quieres vender un Terreno?"],
    },
}

#: Alto Quintay has a landing page (``/alto-quintay/``) and a card in the home
#: page's "Destacados" tab, but is not one of the listed projects, so the AJAX
#: list and the cotizar pages do not have it. From the site notes (§1a, §1b)
#: and its page outline.
ALTO_QUINTAY: dict[str, Any] = {
    "slug": "alto-quintay",
    "name": "Alto Quintay",
    "site_name": "ALTO QUINTAY",
    "listed": False,
    "path": "/alto-quintay/",
    "quote_path": "",
    "comuna": "Quintay",
    "region": "valparaiso",
    "tipos": ["departamento"],
    "desde_uf": 9950,
    "dormitorios": [2, 3],
    "banos": "",
    "superficie_m2": None,
    "estado": "",
    "perfil": [],
    "address": "Club de Golf Santa Augusta, Quintay",
    "hero_tags": "",
    "tagline": "¡BIENVENIDOS A ALTO QUINTAY!",
    "intro": "¡BIENVENIDOS A ALTO QUINTAY! Un verdadero refugio en donde encontrarás la "
    "tranquilidad y seguridad que tú y tu familia están buscando. Disfruta de dos "
    "increíbles piscinas con arena y vive una experiencia como si estuvieras en la playa.",
    "typologies": [],
    "status": "",
    "gallery_slides": 6,
    "amenities_title": "DISFRUTA ESPACIOS INCREÍBLES",
    "outline": [
        {"key": "", "heading": "¡BIENVENIDOS A ALTO QUINTAY!", "module": "main-slider-section"},
        {
            "key": "galería",
            "heading": "DEPARTAMENTOS SORPRENDENTES",
            "module": "l3-numbered-slider-section",
        },
        {
            "key": "amenidades",
            "heading": "DISFRUTA ESPACIOS INCREÍBLES",
            "module": "alternate-images-section",
        },
        {"key": "estado", "heading": "ESTADO DEL PROYECTO", "module": "l3-project-status-section"},
        {"key": "brochure", "heading": "BROCHURE", "module": "wbct-section"},
        {"key": "contacto", "heading": "CONTÁCTANOS", "module": "project-actions-section"},
    ],
    "hours": "LUNES DE 15:00 A 19:00 - MARTES A SÁBADO DE 10:45 A 14:00 Y DE 15:00 A 19:00 - "
    "MIÉRCOLES CERRADO, DOMINGO CONSULTE POR ATENCIÓN.",
    "phone": "+569 5756 0036",
    "email": "altoquintay@ssilva.cl",
    "contact_address": "Av. El Estero con Santa Augusta, Club de Golf Santa Augusta, Quintay",
    "whatsapp": True,
    "brochure": True,
    "tour": False,
    "lead_form": False,
    "units": [],
    "notes": "Not in the project list or its filters; shown in the home page's Destacados "
    "tab. Its contact block offers AGENDAR VISITA A PILOTO (WhatsApp). There is no "
    "typology section and no quote form on its page.",
}

#: Words of a project's name the site writes without their accent.
_NAME_FIXES = {"pucon": "Pucón", "arrayan": "Arrayán"}
_SMALL = frozenset({"de", "del", "la", "el", "al", "y", "en", "las", "los"})


# ─── Text helpers ──────────────────────────────────────────────────────────────


def fold(text: str) -> str:
    """Lower case, accents off, spaces folded."""
    nfkd = unicodedata.normalize("NFKD", text)
    return " ".join("".join(c for c in nfkd if not unicodedata.combining(c)).lower().split())


def squash(text: Any) -> str:
    return " ".join(str(text or "").split())


def display_name(site_name: str) -> str:
    """``EDIFICIO MILLALONGO 72`` → ``Edificio Millalongo 72``."""
    if any(c.islower() for c in site_name):
        return squash(site_name)
    out: list[str] = []
    for i, word in enumerate(site_name.split()):
        low = word.lower()
        if low in _NAME_FIXES:
            out.append(_NAME_FIXES[low])
        elif i > 0 and low in _SMALL:
            out.append(low)
        else:
            out.append(word[:1].upper() + word[1:].lower())
    return " ".join(out)


def uf(text: str) -> int | None:
    """``Desde 2.372 UF`` → 2372."""
    m = re.search(r"(\d{1,3}(?:\.\d{3})+|\d+)", text or "")
    return int(m.group(1).replace(".", "")) if m else None


def path_of(url: str) -> str:
    m = re.match(r"https?://[^/]+(/.*)?$", url or "")
    path = (m.group(1) if m else url) or "/"
    return path if path.endswith("/") else f"{path}/"


def region_key(label: str) -> str:
    f = fold(label)
    return "metropolitana" if "metropolitana" in f else "valparaiso" if "valpara" in f else "otros"


def _between(text: str, start: str, ends: tuple[str, ...]) -> str:
    i = text.find(start)
    if i < 0:
        return ""
    rest = text[i + len(start) :]
    cut = min((j for e in ends if (j := rest.find(e)) >= 0), default=len(rest))
    return rest[:cut].strip(" .,-")


def tagline_of(intro: str) -> str:
    """The intro's heading: its opening words in capitals."""
    out: list[str] = []
    for word in intro.split():
        letters = [c for c in word if c.isalpha()]
        if letters and not all(c.isupper() for c in letters):
            break
        out.append(word)
    return " ".join(out).strip()


# ─── Crawl ─────────────────────────────────────────────────────────────────────

DETAIL_JS = r"""() => {
  const t = s => document.querySelector(s)?.innerText.replace(/\s+/g, ' ').trim();
  const mods = [...document.querySelectorAll('.site__content section[class*=-section], .site__content section.l3-hero')]
    .filter(s => !s.parentElement.closest('section[class*=-section]'));
  return {
    finalUrl: location.href, title: document.title,
    template: document.body.className.match(/page-template-\S+/)?.[0],
    sections: mods.map(s => s.className.split(' ')[0]),
    headings: mods.map(s => ({module: s.className.split(' ')[0],
      heading: (s.querySelector('h1, h2')?.innerText || '').replace(/\s+/g, ' ').trim()})),
    hero: t('.l3-hero__info') || t('.l3-hero'),
    intro: t('.main-slider .left'),
    tagline: t('.main-slider .left h2') || t('.main-slider .left h1'),
    typologies: [...document.querySelectorAll('.cotizador-l1 li.type-item')].map(l => l.innerText.trim()),
    gallerySlides: document.querySelectorAll('.numbered-slider .slick-slide:not(.slick-cloned)').length,
    amenitiesTitle: t('.alternate-images-section h2'),
    status: t('.l3-project-status .status-item.active .title'),
    contact: t('.project-actions .left') || t('.project-actions'),
    whatsapp: document.querySelector('.floating-quote-btn')?.href || '',
    brochure: [...document.querySelectorAll('.wbct a, .l3-other-docs a')].map(a => a.href).filter(Boolean),
    hsForms: [...document.querySelectorAll('.cotizador-l1 .hs-form-frame')].map(f => f.dataset.formId),
    tour: !!document.querySelector('.video-tour-section .tour-btn'),
  };
}"""

PAGE_JS = r"""() => ({
  title: document.title,
  headings: [...document.querySelectorAll('.site__content h1, .site__content h2, [class*=title-box]')]
    .filter(e => e.getBoundingClientRect().height > 0)
    .map(e => e.innerText.replace(/\s+/g, ' ').trim()).filter(Boolean),
  text: (document.querySelector('.site__content') || document.body).innerText.replace(/\s+/g, ' ').trim().slice(0, 6000),
})"""


def crawl(raw: Path) -> None:
    from playwright.sync_api import sync_playwright

    raw.mkdir(parents=True, exist_ok=True)
    (raw / "quote").mkdir(exist_ok=True)
    (raw / "pages").mkdir(exist_ok=True)

    def dump(name: str, data: Any) -> None:
        (raw / name).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="es-CL")
        req = ctx.request

        def listing(prop: str = "") -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
            posts: list[dict[str, Any]] = []
            communes: list[dict[str, Any]] = []
            page = 1
            while True:
                form = {
                    "action": "projects",
                    "card_type": "quote",
                    "project_type": "highlight",
                    "property": prop,
                    "region": "",
                    "communes": "",
                    "page": str(page),
                }
                data = req.post(AJAX, multipart=form).json()
                posts += data.get("posts") or []
                communes = (data.get("filters") or {}).get("communes") or communes
                if page >= int(data.get("pages") or 1):
                    return posts, communes
                page += 1

        posts, _ = listing()
        dump("all-projects.json", posts)
        print(f"{len(posts)} projects listed", file=sys.stderr)
        for key, pid in PROPERTY_IDS.items():
            got, _ = listing(str(pid))
            dump(f"property-{pid}.json", sorted({p["project_term_slug"] for p in got}))
            print(f"  {key}: {len(got)}", file=sys.stderr)
        # The commune filter answers only with a region chosen.
        form = {"action": "projects", "card_type": "quote", "project_type": "highlight"}
        form |= {"property": "", "region": "17", "communes": "", "page": "1"}
        dump(
            "communes.json",
            (req.post(AJAX, multipart=form).json().get("filters") or {}).get("communes") or [],
        )
        dump("projects.json", req.get(f"{BASE}/wp-json/wp/v2/projects?per_page=100").json())
        dump(
            "type_projects.json", req.get(f"{BASE}/wp-json/wp/v2/type_projects?per_page=100").json()
        )

        page = ctx.new_page()
        details: dict[str, Any] = {}
        for p in posts:
            slug = p["project_term_slug"]
            url = (p.get("project_btn") or {}).get("url") or ""
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(4000)
                details[slug] = page.evaluate(DETAIL_JS)
            except Exception as exc:
                details[slug] = {"error": str(exc)[:200]}
            quote_url = (p.get("quote_price_btn") or {}).get("url") or ""
            if quote_url:
                body = req.get(quote_url).text()
                m = re.search(r'<quote[^>]*\s:data="([^"]*)"', body)
                data = json.loads(html.unescape(m.group(1))) if m else {}
                dump(f"quote/{slug}.json", data)
            print(f"  {slug}", file=sys.stderr)
        try:
            page.goto(f"{BASE}/alto-quintay/", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(4000)
            details["alto-quintay"] = page.evaluate(DETAIL_JS)
        except Exception as exc:
            details["alto-quintay"] = {"error": str(exc)[:200]}
        dump("project-details.json", details)
        for path, info in INFO_PAGES.items():
            page.goto(BASE + path + ("" if path == "/" else "/"), wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            dump(f"pages/{info['name']}.json", page.evaluate(PAGE_JS))
        browser.close()


# ─── Render ────────────────────────────────────────────────────────────────────


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _quote(raw: Path, slug: str) -> list[dict[str, Any]]:
    """One cotizar page's typologies and units: ``quote/<slug>.json`` from the
    crawl, or the exploration's ``quote/<slug>.attrs.json``."""
    data = _load(raw / "quote" / f"{slug}.json", None)
    if data is None:
        attrs = _load(raw / "quote" / f"{slug}.attrs.json", {})
        text = (attrs.get("attrs") or {}).get("data") if isinstance(attrs, dict) else None
        data = json.loads(text) if isinstance(text, str) and text.strip() else {}
    out: list[dict[str, Any]] = []
    for option in (data or {}).get("options") or []:
        units: list[dict[str, Any]] = []
        for u in option.get("units") or []:
            facts = {
                squash(a.get("name")): squash(a.get("value")) for a in u.get("attributes") or []
            }
            price = u.get("final_price") or u.get("price") or 0
            units.append(
                {
                    "unit": squash(u.get("name")),
                    "uf": round(float(price)) if price else None,
                    "interior": facts.get("Superficie interior", ""),
                    "terraza": facts.get("Superficie terraza", ""),
                    "total": facts.get("Superficie total", ""),
                    "orientation": facts.get("Orientación", ""),
                }
            )
        out.append({"typology": squash(option.get("name")), "units": units})
    return out


def _m2(text: str) -> float | None:
    m = re.search(r"(\d+(?:[.,]\d+)?)", text or "")
    return float(m.group(1).replace(",", ".")) if m else None


def _unit_summary(units: list[dict[str, Any]]) -> dict[str, Any]:
    prices = [u["uf"] for u in units if u.get("uf")]
    totals = [t for u in units if (t := _m2(u.get("total", "")))]
    orient = sorted({u["orientation"] for u in units if u.get("orientation")})
    return {
        "count": len(units),
        "desde_uf": min(prices) if prices else None,
        "hasta_uf": max(prices) if prices else None,
        "total_m2": [min(totals), max(totals)] if totals else [],
        "orientations": orient,
    }


def _tipos(slug: str, site_name: str, membership: dict[str, set[str]]) -> list[str]:
    if membership:
        found = [k for k, slugs in membership.items() if slug in slugs]
        if found:
            return found
    # Without the crawl's per-type lists: the site notes' reading (§1b).
    name = fold(site_name)
    if "oficina" in name:
        return ["oficina"]
    if "locales" in name:
        return ["local"]
    if slug == "piedra-roja":
        return ["casa"]
    if slug == "vista-golf":
        return ["departamento", "casa"]
    return ["departamento"]


def _outline(detail: dict[str, Any], tagline: str) -> list[dict[str, str]]:
    read = {h.get("module"): h.get("heading", "") for h in detail.get("headings") or []}
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for module in detail.get("sections") or []:
        module = module.split("#")[0]
        key, default = MODULES.get(module, ("", ""))
        if module == "main-slider-section":
            heading = tagline
        elif module == "alternate-images-section":
            heading = squash(detail.get("amenitiesTitle")) or "Amenidades"
        else:
            heading = squash(read.get(module)) or default
        if not heading and not key:
            continue
        if key and key in seen:
            continue
        seen.add(key or heading)
        out.append({"key": key, "heading": heading, "module": module})
    return out


def _project(
    card: dict[str, Any],
    detail: dict[str, Any],
    rest: dict[str, Any] | None,
    types: dict[int, str],
    units: list[dict[str, Any]],
    membership: dict[str, set[str]],
) -> dict[str, Any]:
    slug = card["project_term_slug"]
    site_name = squash(card.get("condo_name"))
    hero = squash(detail.get("hero")).replace("location_on ", "")
    intro = squash(detail.get("intro"))
    tagline = squash(detail.get("tagline")) or tagline_of(intro)
    contact = squash(detail.get("contact"))
    status = squash(detail.get("status"))
    sections = [s.split("#")[0] for s in detail.get("sections") or []]
    page_url = squash(detail.get("finalUrl")) or (card.get("project_btn") or {}).get("url", "")
    has_page = "page-template-landing" in squash(detail.get("template")) or bool(sections)
    rooms = [int(n) for n in re.findall(r"\d", card.get("bedrooms") or "")]
    whatsapp = squash(detail.get("whatsapp"))
    tour = detail.get("tour")
    return {
        "slug": slug,
        "name": display_name(site_name),
        "site_name": site_name,
        "listed": True,
        "path": path_of(page_url) if has_page else "",
        "quote_path": path_of((card.get("quote_price_btn") or {}).get("url", "")),
        "comuna": squash(card.get("commune")),
        "region": region_key(card.get("region", "")),
        "tipos": _tipos(slug, site_name, membership),
        "desde_uf": uf(card.get("cost", "")),
        "dormitorios": sorted(set(rooms)),
        "banos": squash(card.get("bathrooms")),
        "superficie_m2": uf(card.get("square_area", "")),
        "estado": squash(card.get("category")),
        "perfil": [types[t] for t in (rest or {}).get("type_projects") or [] if t in types],
        "address": _between(hero, "", (" DESDE", " Desde")) if hero else "",
        "hero_tags": re.sub(r"^.*?DESDE [\d.]+ UF\s*", "", hero) if "DESDE" in hero else "",
        "tagline": tagline,
        "intro": intro,
        "typologies": [squash(t) for t in detail.get("typologies") or []],
        "status": status.capitalize() if status else "",
        "gallery_slides": int(detail.get("gallerySlides") or 0),
        "amenities_title": squash(detail.get("amenitiesTitle")),
        "outline": _outline(detail, tagline) if has_page else [],
        "hours": _between(contact, "HORARIO DE ATENCIÓN", (" phone",)).lstrip(": "),
        "phone": _between(contact, "phone ", (" email",)),
        "email": _between(contact, "email ", (" location_on",)),
        "contact_address": _between(
            contact, "location_on ", (" CONTACTAR", " AGENDA", " CONOCE", " Ejecutiv")
        ),
        "whatsapp": whatsapp.startswith("https://wa.me/") or "whatsapp" in whatsapp,
        "brochure": any(
            "flip-book" in b or b.endswith(".pdf") for b in detail.get("brochure") or []
        ),
        # The brochure itself: the PDF Javier shows and downloads, and the
        # 3D flip-book page that holds the same pages.
        "brochure_pdf": next(
            (b for b in detail.get("brochure") or [] if b.lower().endswith(".pdf")), ""
        ),
        "brochure_flipbook": next(
            (b for b in detail.get("brochure") or [] if "flip-book" in b), ""
        ),
        "tour": bool(tour) if isinstance(tour, bool) else "video-tour-section" in sections,
        "lead_form": "cotizador-l1-section" in sections,
        "units": [
            {"typology": q["typology"], **_unit_summary(q["units"])} for q in units if q["units"]
        ],
        "notes": ""
        if has_page
        else "Its page redirects to /proyectos/: it has no page of its own.",
    }


def _uf_text(n: int | None) -> str:
    return "" if n is None else f"{n:,}".replace(",", ".")


def project_markdown(p: dict[str, Any]) -> str:
    """Every fact of one project, as ``read_project`` hands it to Javier."""
    lines = [f"# {p['name']}"]
    lines.append(
        "Sources: ssilva.cl project page"
        + (f" {p['path']}" if p["path"] else "")
        + (f", cotizar page {p['quote_path']}" if p["quote_path"] else "")
        + ", the project list."
    )
    lines.append("")
    region = REGION_LABELS.get(p["region"], p["region"])
    kinds = ", ".join(PROPERTY_LABELS[t] for t in p["tipos"])
    lines.append(f"- Name on the site: {p['site_name']}")
    lines.append(f"- Comuna: {p['comuna']} ({region}). Type: {kinds}.")
    if p["address"]:
        lines.append(f"- Address (hero): {p['address']}")
    if p["desde_uf"]:
        lines.append(f"- Desde {_uf_text(p['desde_uf'])} UF (the list's starting price).")
    if p["dormitorios"]:
        rooms = ", ".join(str(n) for n in p["dormitorios"])
        lines.append(f"- Dormitorios: {rooms}. Baños: {p['banos'] or '-'}.")
    if p["superficie_m2"]:
        lines.append(f"- Desde {p['superficie_m2']} m².")
    if p["estado"]:
        lines.append(f"- Estado (list): {p['estado']}.")
    if p["status"]:
        lines.append(f"- Status bar on the page: {p['status']}.")
    if p["perfil"]:
        lines.append(f"- Profile: {', '.join(p['perfil'])}.")
    if p["hero_tags"]:
        lines.append(f"- Hero also says: {p['hero_tags']}")
    if p["intro"]:
        lines.append(f"- Description ({p['tagline'] or 'intro'}): {p['intro']}")
    if p["typologies"]:
        lines.append(f"- Tipologías on the page: {' / '.join(p['typologies'])}")
    if p["units"]:
        lines.append("- Units on the cotizar page (by typology):")
        for u in p["units"]:
            price = (
                f"desde {_uf_text(u['desde_uf'])} UF"
                + (f" hasta {_uf_text(u['hasta_uf'])} UF" if u["hasta_uf"] != u["desde_uf"] else "")
                if u["desde_uf"]
                else "no price published"
            )
            area = (
                f", total {u['total_m2'][0]:g} to {u['total_m2'][1]:g} m²"
                if u["total_m2"] and u["total_m2"][0] != u["total_m2"][1]
                else f", total {u['total_m2'][0]:g} m²"
                if u["total_m2"]
                else ""
            )
            orient = f", orientación {', '.join(u['orientations'])}" if u["orientations"] else ""
            lines.append(f"  - {u['typology']}: {u['count']} unidades, {price}{area}{orient}")
    elif p["listed"]:
        lines.append(
            "- The cotizar page lists no units: quote from the typology section's price on the "
            "project page."
        )
    if p["amenities_title"]:
        lines.append(f"- Amenities section title: {p['amenities_title']}")
    if p["gallery_slides"]:
        lines.append(f"- Gallery: {p['gallery_slides']} photos.")
    lines.append(f"- Virtual tour on the page: {'yes' if p['tour'] else 'no'}.")
    lines.append(f"- Quote form on the page: {'yes' if p['lead_form'] else 'no'}.")
    if p["outline"]:
        order = "; ".join(
            f"{o['heading']}" + (f" [{o['key']}]" if o["key"] else "") for o in p["outline"]
        )
        lines.append(f"- Sections, top to bottom: {order}")
    if p["hours"]:
        lines.append(f"- Horario de atención: {p['hours']}")
    if p["phone"]:
        lines.append(f"- Phone: {p['phone']}. Email: {p['email']}.")
    if p["contact_address"]:
        lines.append(f"- Sala de ventas / contact address: {p['contact_address']}")
    lines.append(f"- WhatsApp button: {'yes' if p['whatsapp'] else 'no'}.")
    if p["notes"]:
        lines.append(f"- Note: {p['notes']}")
    return "\n".join(lines) + "\n"


def _roster_table(projects: list[dict[str, Any]]) -> str:
    rows = [
        "| Proyecto | Comuna | Región | Tipo | Desde UF | Dorm. | Estado | Perfil | Página |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for p in projects:
        rows.append(
            "| "
            + " | ".join(
                [
                    p["name"],
                    p["comuna"],
                    {"metropolitana": "RM", "valparaiso": "Valparaíso", "otros": "Otros"}[
                        p["region"]
                    ],
                    "/".join("depto" if t == "departamento" else t for t in p["tipos"]),
                    _uf_text(p["desde_uf"]),
                    ",".join(str(n) for n in p["dormitorios"]) or "-",
                    p["estado"] or "-",
                    ", ".join(
                        x.replace("Para ", "").replace("Segunda vivienda", "2ª vivienda")
                        for x in p["perfil"]
                    )
                    or "-",
                    p["path"] or "(sin página)",
                ]
            )
            + " |"
        )
    return "\n".join(rows)


def render(raw: Path) -> None:
    cards: list[dict[str, Any]] = _load(raw / "all-projects.json", [])
    if not cards:
        raise SystemExit(f"no all-projects.json in {raw}: run `crawl` first, or pass --raw")
    details: dict[str, Any] = _load(raw / "project-details.json", {})
    rest_list: list[dict[str, Any]] = _load(raw / "projects.json", [])
    rest = {r.get("link"): r for r in rest_list}
    types = {t["id"]: t["name"] for t in _load(raw / "type_projects.json", [])}
    membership = {
        key: set(_load(raw / f"property-{pid}.json", []))
        for key, pid in PROPERTY_IDS.items()
        if (raw / f"property-{pid}.json").exists()
    }
    projects: list[dict[str, Any]] = []
    for card in cards:
        slug = card["project_term_slug"]
        quote_url = (card.get("quote_price_btn") or {}).get("url")
        projects.append(
            _project(
                card,
                details.get(slug) or {},
                rest.get(quote_url),
                types,
                _quote(raw, slug),
                membership,
            )
        )
    if "alto-quintay" not in {p["slug"] for p in projects}:
        projects.append(dict(ALTO_QUINTAY))
    order = {"metropolitana": 0, "valparaiso": 1, "otros": 2}
    projects.sort(
        key=lambda p: (not p["listed"], order[p["region"]], fold(p["comuna"]), fold(p["name"]))
    )

    l3 = HERE / "L3"
    l3.mkdir(exist_ok=True)
    (l3 / "projects.json").write_text(
        json.dumps(projects, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    pages: list[dict[str, Any]] = []
    for path, info in INFO_PAGES.items():
        crawled = _load(raw / "pages" / f"{info['name']}.json", {})
        heads = crawled.get("headings") if isinstance(crawled, dict) else None
        pages.append(
            {
                "path": path,
                "kind": info["kind"],
                "title": info["title"],
                "sections": [{"heading": h, "key": ""} for h in (heads or info["headings"])],
                "text": squash((crawled or {}).get("text") if isinstance(crawled, dict) else "")
                or info.get("text", ""),
            }
        )
    for p in projects:
        if p["path"]:
            pages.append(
                {
                    "path": p["path"].rstrip("/"),
                    "kind": "project",
                    "title": p["name"],
                    "project": p["slug"],
                    "sections": [{"heading": o["heading"], "key": o["key"]} for o in p["outline"]],
                    "text": p["intro"],
                }
            )
        if p["quote_path"]:
            pages.append(
                {
                    "path": p["quote_path"].rstrip("/"),
                    "kind": "quote",
                    "title": f"Cotizar {p['name']}",
                    "project": p["slug"],
                    "sections": [
                        {"heading": "SELECCIONA LAS TIPOLOGÍAS DE INTERÉS", "key": ""},
                        {"heading": "INGRESA TUS DATOS PERSONALES", "key": ""},
                    ],
                    "text": "",
                }
            )
    (l3 / "pages.json").write_text(
        json.dumps(pages, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    communes = _load(raw / "communes.json", None)
    if not communes:
        bodies = _load(raw / "ajax-bodies.json", [])
        for b in bodies:
            try:
                found = (json.loads(b.get("body") or "{}").get("filters") or {}).get("communes")
            except ValueError:
                found = None
            if found:
                communes = found
                break
    site = {
        "base": BASE,
        "list": "/proyectos/?region=<id>&property=<id> (communes are checkboxes, #commune<id>)",
        "regions": {k: {"id": v, "label": REGION_LABELS[k]} for k, v in REGION_IDS.items()},
        "properties": {k: {"id": v, "label": PROPERTY_LABELS[k]} for k, v in PROPERTY_IDS.items()},
        "communes": [{"name": c["name"], "id": c["id"]} for c in communes or []],
        "menu": [
            "Portal propietario",
            "Nuestros proyectos",
            "Oportunidades",
            "Centro de negocios",
            "Sobre Ssilva",
            "Descubre",
            "Vende tu terreno",
            "Centro de ayuda",
        ],
        "status_steps": list(STATUS_STEPS),
        "lead_form": {
            "step 1": [
                "Nombre",
                "Apellidos",
                "N° de Rut",
                "Tu mejor correo",
                "Teléfono",
                "¿Qué te motiva a realizar la compra? (Invertir / Habitar)",
            ],
            "step 2": [
                "¿Qué tipo de departamento estas buscando?",
                "¿Cuál es tu ingreso líquido mensual?",
                "¿Cuánto ahorro puedes destinar para un pie?",
            ],
            "buttons": ["Siguiente", "Anterior", "Enviar"],
        },
    }
    (l3 / "site.json").write_text(
        json.dumps(site, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    l2 = HERE / "L2" / "proyectos"
    l2.mkdir(parents=True, exist_ok=True)
    for old in l2.glob("*.md"):
        old.unlink()
    for p in projects:
        (l2 / f"{p['slug']}.md").write_text(project_markdown(p), encoding="utf-8")

    l1 = HERE / "L1.md"
    text = l1.read_text(encoding="utf-8") if l1.exists() else ""
    start, end = "<!-- roster:start -->", "<!-- roster:end -->"
    listed = [p for p in projects if p["listed"]]
    table = f"{start}\n{_roster_table(listed)}\n{end}"
    if start in text and end in text:
        text = text[: text.index(start)] + table + text[text.index(end) + len(end) :]
    else:
        text = f"{text.rstrip()}\n\n{table}\n"
    l1.write_text(text, encoding="utf-8")
    print(f"rendered {len(projects)} projects and {len(pages)} pages", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("crawl", help="fetch the site into a raw directory")
    c.add_argument("--raw", type=Path, default=RAW)
    r = sub.add_parser("render", help="render a raw directory into L1, L2 and L3")
    r.add_argument("--raw", type=Path, default=RAW)
    args = parser.parse_args()
    if args.cmd == "crawl":
        crawl(args.raw)
    else:
        render(args.raw)


if __name__ == "__main__":
    main()
