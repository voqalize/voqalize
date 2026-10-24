# pyright: basic
# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Build Figurella Chile's L3 knowledge: the pages of figurella.cl, as data,
read from a real browser, and the catalogue of places on them Javier points at.

The build runs offline on a dev machine; its output is committed and the brain
only ever reads the JSON (the brain runs where the site does not answer: it is
geo-blocked outside a few countries). Network is touched only by ``crawl``;
every page's extraction is cached outside the repository, so ``--offline``
rebuilds from the cache.

figurella.cl is WordPress with the LaStudio "lauriel" theme and Elementor
(4.2) + Elementor Pro: server-rendered HTML, a full page load per navigation,
a fixed 130 px header, and Elementor's stable ``data-id``s on every widget
(``.elementor-element-<id>``), which is what the catalogue keys on. The
booking form ``#form_agendamiento_figurella`` is in the shared footer of every
page but ``/franquicias/`` and ``/gracias/``. The FAQ is an Essential Addons
accordion whose headers carry stable ids (``#cunto-cuesta-figurella``). Blog
posts ("Consejos") come from the open REST API (``/wp-json/wp/v2/posts``).

Run from ``voqalize/demos`` on a machine the site answers (Chromium installed
once with ``playwright install chromium``)::

    uv run --no-project --with playwright python figurella/backend/knowledge/build.py crawl
    uv run --no-project python figurella/backend/knowledge/build.py crawl --offline

It writes, next to this file:

- ``L3/anchors.json`` — the catalogue: for every page path, the places a move
  can target, ``{key, selector, label, hidden?}``, each selector checked on the
  live page to match exactly one laid-out element; the footer's anchors (the
  booking form and its fields), shared by every page that has the footer; and
  the blog post template's. The extension bundles this file (its site adapter
  turns a key into an element) and the brain checks every cue against it.
  ``hidden`` anchors are the adapter's own (a button it listens to, a field it
  fills), never offered to the model.
- ``L3/pages.json`` — one record per page, the keys the shared loader reads:
  ``{path, url, title, kind, sections: [{key, heading, text}], faqs: [{q, key,
  a}], text}``. A section is an anchor of the catalogue with the words the
  element shows (``innerText``, capped). Blog posts are pages too
  (``kind: "post"``), their text from the REST API.
- ``L3/branches.json`` — the seven branches as their cards on the home page
  give them (name, address, phone, hours, the "¿Cómo llegar?" map link) with
  the booking form's option value for each, and the WhatsApp widget's line
  where it differs (Montemar, Concón, is only in the widget).
- ``L3/convenios.json`` — the fourteen agreements on ``/convenios/``: partner,
  discount, and the card's text. Partner names that are only in a logo come
  from the logo's file name.

The hand-written layers (``L1.md``, ``L2/*.md``) are not touched, except
``L2/site-map.md``, which is generated from the catalogue.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
L3 = HERE / "L3"
SITE = "https://figurella.cl"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/141 Safari/537.36"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "voqalize-figurella"
#: The fixed header (desktop), and the gap kept under it: how the adapter scrolls.
HEADER_PX = 130
TEXT_CAP = 1400


def el(i: str) -> str:
    return f".elementor-element-{i}"


# ─── The catalogue ──────────────────────────────────────────────────────────
# (key, selector, label, hidden). Labels are what the model reads; keys are
# what it writes in a cue. Verified on the live site by `crawl`.

FOOTER: list[tuple[str, str, str, bool]] = [
    (
        "contacto",
        "#contacto",
        "Formulario «Reserva tu Diagnóstico Corporal sin costo» (pie de página)",
        False,
    ),
    ("form", "#form_agendamiento_figurella", "El formulario de reserva", True),
    ("field_first_name", "#form-field-first_name", "Campo Nombre", True),
    ("field_phone", "#form-field-phone", "Campo Teléfono", True),
    ("field_email", "#form-field-email", "Campo Email", True),
    ("field_comuna", "#form-field-comuna", "Campo Comuna", True),
    ("field_sucursales", "#form-field-sucursales", "Selector de sucursal", True),
    ("field_message", "#form-field-message", "Campo Mensaje", True),
    (
        "field_consent",
        ".elementor-field-group-field_826580a",
        "Casilla de privacidad y WhatsApp",
        True,
    ),
    ("submit", "#btn-send", "Botón «Reservar mi diagnóstico»", True),
]

BRANCHES = [
    # key, name, card column id, (como llegar button id, pedir hora button id), form value
    ("huerfanos", "Huérfanos", "613612d", ("cda1cdc", "c4d3eab"), "huerfanos@figurella.cl"),
    ("costanera", "Costanera", "345047a", ("ad61a55", "cd6ab7b"), "costanera@figurella.cl"),
    ("colon", "Colón", "a6eefa5", ("9ee9db3", "fad3b81"), "colon@figurella.cl"),
    ("chicureo", "Chicureo", "25efdf9", ("f8ef90c", "8fd1bcb"), "chicureo@figurella.cl"),
    ("tabancura", "Tabancura", "cc62c82", ("981e614", "047c94e"), "tabancura@figurella.cl"),
    ("vitacura", "Vitacura", "0ef47cd", ("5881821", "842e43b"), "vitacura@figurella.cl"),
    ("las_perdices", "Las Perdices", "6b7aedc", ("5c3bb5e", "3b01fa0"), "lasperdices@figurella.cl"),
]

HOME: list[tuple[str, str, str, bool]] = [
    ("hero", el("1d63aae"), "Carrusel de portada", False),
    ("hero_cta", el("807c743"), "Botón «Reserva tu Diagnóstico Corporal sin costo»", False),
    ("intro", el("a82a4e5"), "«Sé quien quieras ser»: 15 años en Chile, con los contadores", False),
    ("counters", el("1117078"), "Contadores: 40 años, +500 centros, +5000 mujeres", False),
    (
        "resultados",
        el("326eb7b"),
        "«¡Figurella sí funciona! ¡Resultados garantizados!» y sus tres beneficios",
        False,
    ),
    ("benefit_pierde_peso", el("9e1606a"), "Beneficio «Pierde peso»", False),
    ("benefit_tonifica", el("f8e5d65"), "Beneficio «Tonifica»", False),
    ("benefit_sientete_bien", el("93e3a79"), "Beneficio «Siéntete bien»", False),
    (
        "cuerpo_perfecto",
        el("8963f1f"),
        "«Cuerpo perfecto sin centímetros de más»: 30 minutos, 2 o 3 veces por semana",
        False,
    ),
    ("feature_garantia", el("60a5329"), "«Resultados garantizados» (por escrito)", False),
    ("feature_remodela", el("87c6e05"), "«Remodela y tonifica» (cápsula térmica)", False),
    ("feature_vida_sana", el("8dde143"), "«Vida sana» (alimentación)", False),
    (
        "feature_optimiza",
        el("bcf2d85"),
        "«Optimiza tu tiempo» (30 minutos = 1,5 horas de gimnasio)",
        False,
    ),
    ("metodo", el("2c3543a"), "«¿Cómo lo hacemos? Método Figurella» con sus cuatro pasos", False),
    ("metodo_movimientos", el("f40c516"), "Paso: movimientos localizados", False),
    ("metodo_oxigenoterapia", el("547918a"), "Paso: oxigenoterapia", False),
    ("metodo_presoterapia", el("98fff1f"), "Paso: presoterapia", False),
    ("metodo_nutricion", el("10b262b"), "Paso: asesoramiento nutricional", False),
    ("planes", el("fbd04af"), "Los planes (resumen)", False),
    ("plan_curvas_perfectas", el("be5843c"), "Plan Curvas perfectas (resumen)", False),
    ("plan_novias", el("2b02c2b"), "Plan Novias (resumen)", False),
    ("plan_mama_reciente", el("3a212c0"), "Plan Mamá reciente (resumen)", False),
    ("plan_rejuvenece", el("2328b7a"), "Plan Rejuvenece (resumen)", False),
    ("plan_intensivo", el("cf6556e"), "Plan Intensivo (resumen)", False),
    (
        "historias",
        el("5f763e7"),
        "«¡Más de 5.000 mujeres lo comprobaron!» (botón a las historias)",
        False,
    ),
    ("blog", el("b9bb001"), "«Consejos para tu cuidado»: cuatro artículos del blog", False),
    (
        "garantia",
        el("967257c"),
        "«¿Estás lista para redescubrirte?»: grasa localizada garantizada por escrito",
        False,
    ),
    ("sucursales", "#sucursales", "«Estamos donde tú estás»: las siete sucursales", False),
]
for _key, _name, _col, (_map, _book), _value in BRANCHES:
    HOME.append((f"sucursal_{_key}", el(_col), f"Sucursal {_name} (tarjeta)", False))
    HOME.append((f"sucursal_{_key}_mapa", el(_map), f"{_name}: botón «¿Cómo llegar?»", True))
    HOME.append(
        (f"sucursal_{_key}_pedir_hora", el(_book), f"{_name}: botón «Pedir hora gratis»", True)
    )
HOME.append(("sucursales_cta", el("19d6193"), "Botón «Agenda tu visita»", True))

METODO = [
    ("hero", el("4007f996"), "Portada «Método Figurella»", False),
    ("como_funciona", el("818794"), "«¿Cómo funciona?»: tres veces a la semana, tres pasos", False),
    ("paso_1", el("6414c91"), "Paso uno: movimientos localizados en cápsula térmica", False),
    ("paso_1_video", el("564141c"), "Video del paso uno", True),
    ("paso_2", el("6d50dd2"), "Paso dos: oxigenoterapia", False),
    ("paso_2_video", el("96b454c"), "Video del paso dos", True),
    ("paso_3", el("ab1e4d4"), "Paso tres: presoterapia", False),
    ("paso_3_video", el("6e4c7c2"), "Video del paso tres", True),
    ("paso_4", el("0aa21e9"), "Paso cuatro: asesoramiento nutricional", False),
    ("cta", el("d7c8743"), "Botón «Agenda tu evaluación gratis aquí»", True),
]

PLANES = [
    ("hero", el("41c3b402"), "Portada «Planes 100% personalizados para ti»", False),
    ("plan_curvas_perfectas", el("fee7108"), "Plan Curvas perfectas", False),
    ("plan_curvas_perfectas_cta", el("ca122d1"), "Curvas perfectas: «Reserva tu evaluación»", True),
    ("plan_novias", el("341a556"), "Plan Novias", False),
    ("plan_novias_cta", el("3dfae26"), "Novias: «Reserva tu evaluación»", True),
    ("plan_mama_reciente", el("2730018"), "Plan Mamá reciente", False),
    ("plan_mama_reciente_cta", el("762cb96"), "Mamá reciente: «Reserva tu evaluación»", True),
    ("plan_rejuvenece", el("cfbf6f4"), "Plan Rejuvenece", False),
    ("plan_rejuvenece_cta", el("b7b8a00"), "Rejuvenece: «Reserva tu evaluación»", True),
    ("plan_intensivo", el("93339e2"), "Plan Intensivo", False),
    ("plan_intensivo_cta", el("d368290"), "Intensivo: «Reserva tu evaluación»", True),
]

_SLIDES = el("7f9091f1") + ' .slick-slide[data-slick-index="{}"]'
HISTORIAS = [
    ("hero", el("18980286"), "Portada «Historias de éxito»", False),
    ("testimonios", el("69dc5d0b"), "Los testimonios", False),
    (
        "testimonio_pamela",
        _SLIDES.format(0),
        "Pamela Rodríguez (Plan Novias, antes de su matrimonio)",
        False,
    ),
    (
        "testimonio_cuca",
        _SLIDES.format(1),
        "María Elia Valdés «Cuca» (66 años, artritis, bajó 10 kilos)",
        False,
    ),
    (
        "testimonio_maria_jesus",
        _SLIDES.format(2),
        "María Jesús Amigoz (el «ambiente Figurella»)",
        False,
    ),
]

CONVENIOS = [
    # key, partner, element id
    ("santander", "Banco Santander", "a3bfaf5"),
    ("security", "Banco Security", "b913d1e"),
    ("bice", "Banco BICE", "0bbb8ff"),
    ("itau", "Banco Itaú", "2165d6d"),
    ("colmena", "Isapre Colmena", "2ccf9f3"),
    ("banmedica", "Isapre Banmédica", "0340c15"),
    ("vida_tres", "Isapre Vida Tres", "e0c6b45"),
    ("club_mama_ripley", "Club Mamá Ripley", "a537651"),
    ("club_novios_ripley", "Club Novios Ripley", "169119d"),
    ("santiago_college", "Colegio Santiago College", "3401bbd"),
    ("wenlock", "Colegio Wenlock", "8f85a54"),
    ("cencosud_scotiabank", "Cencosud Scotiabank", "6ecb455"),
    ("colegio_aleman", "Colegio Alemán de Santiago", "6fff74d"),
    ("banco_ripley", "Banco Ripley", "bb5c079"),
]
CONVENIOS_PAGE = [
    ("hero", el("2510a7d8"), "Portada «Convenios»: promociones y descuentos", False),
    ("grid", el("2fa7fbd0"), "Los convenios (primera fila)", False),
] + [(f"convenio_{k}", el(i), f"Convenio {name}", False) for k, name, i in CONVENIOS]

FRANQUICIAS = [
    ("hero", el("76a4a3bb"), "Portada «Franquicias»: más de 500 centros en el mundo", False),
    (
        "beneficios",
        el("4d7e4b1e"),
        "«Franquicias Figurella»: los ocho beneficios para socios",
        False,
    ),
    ("socios", "#socios", "«Comunícate con nosotras»: el formulario de franquicias", False),
    ("form_franquicias", el("5a9d90a7") + " form", "El formulario de franquicias", True),
    ("franq_nombre", "#form-field-nombre", "Campo Nombre (franquicias)", True),
    ("franq_telefono", "#form-field-telefono", "Campo Teléfono (franquicias)", True),
    ("franq_email", "#form-field-email", "Campo Correo (franquicias)", True),
    ("franq_submit", "#btn-send", "Botón «Contáctame ahora»", True),
]

FAQ_ITEMS = [
    ("faq_abdomen", "cmo-puedo-obtener-un-abdomen-plano"),
    ("faq_caderas", "cmo-puedo-perder-peso-en-mis-caderas"),
    ("faq_muslos_gluteos", "puede-figurella-ayudar-a-mis-muslos-y-glteos"),
    ("faq_perder_mucho_peso", "quiero-perder-mucho-peso-puedo"),
    ("faq_precio", "cunto-cuesta-figurella"),
    ("faq_frecuencia", "cuntas-veces-a-la-semana-debo-asistir-figurella-qu-pasa-si-falto"),
]
FAQ = [
    ("hero", el("7e5a9b3"), "Portada «Preguntas frecuentes» con su introducción", False),
    (
        "accordion_1",
        el("123e1c92"),
        "Primer grupo de preguntas (abdomen, caderas, muslos, mucho peso)",
        False,
    ),
    ("accordion_2", el("addfc3b"), "Segundo grupo de preguntas (precio, frecuencia)", False),
]

CONSEJOS = [
    ("lista", ".lastudio-posts__list, .la-loop", "La lista de artículos", False),
    ("paginacion", ".la-pagination", "Paginación del blog", True),
]
POST = [
    ("titulo", "h1.entry-title-single", "Título del artículo", False),
    ("contenido", ".single-post-article .entry", "El artículo", False),
    ("relacionados", ".section-related-posts", "Artículos relacionados", False),
]
PRIVACY = [("contenido", "#main", "La política de privacidad", False)]

#: path → (kind, anchors, has the booking footer)
PAGES: dict[str, tuple[str, list[tuple[str, str, str, bool]], bool]] = {
    "/": ("home", HOME, True),
    "/metodo-figurella/": ("method", METODO, True),
    "/planes/": ("plans", PLANES, True),
    "/historias-de-exito/": ("stories", HISTORIAS, True),
    "/convenios/": ("convenios", CONVENIOS_PAGE, True),
    "/franquicias/": ("franchise", FRANQUICIAS, False),
    "/preguntas-frecuentes/": ("faq", FAQ, True),
    "/consejos/": ("blog", CONSEJOS, True),
    "/politica-de-privacidad/": ("privacy", PRIVACY, True),
}

# ─── Fetching ────────────────────────────────────────────────────────────────


def cache_file(url: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    return CACHE / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".json")


def get_json(url: str, offline: bool) -> Any:
    path = cache_file(url)
    if offline:
        if not path.exists():
            raise SystemExit(f"{url}: not in the cache; run without --offline first")
        return json.loads(path.read_text(encoding="utf-8"))
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "es-CL"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


#: In the page: for each anchor, how many match, how many are laid out, its
#: words, and whether, scrolled under the header, its top shows unobscured.
_READ = """([anchors, header]) => {
  const vis = (e) => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
  const out = [];
  for (const [key, sel] of anchors) {
    let all = [];
    try { all = [...document.querySelectorAll(sel)]; } catch (e) { out.push({key, count: -1}); continue; }
    const shown = all.filter(vis);
    const el = shown[0] || all[0];
    if (!el) { out.push({key, count: 0, visible: 0}); continue; }
    el.scrollIntoView({block: 'start', behavior: 'instant'});
    window.scrollBy(0, -(header + 10));
    const r = el.getBoundingClientRect();
    const text = (el.innerText || el.value || '').replace(/[ \\t]+/g, ' ').replace(/\\n\\s*\\n+/g, '\\n').trim();
    const maps = [...el.querySelectorAll('a[href*="goo.gl/maps"], a[href*="maps.app.goo.gl"], a[href*="google.com/maps"]')].map(a => a.href);
    const tel = [...el.querySelectorAll('a[href^="tel:"]')].map(a => a.getAttribute('href'));
    const img = [...el.querySelectorAll('img')].map(i => i.currentSrc || i.src).filter(Boolean);
    out.push({key, count: all.length, visible: shown.length, inView: r.top >= header - 2 && r.top < innerHeight, text, maps, tel, img});
  }
  return out;
}"""

_FAQ = """() => [...document.querySelectorAll('.eael-accordion-header[id]')].map(h => ({
  id: h.id,
  q: (h.querySelector('.eael-accordion-tab-title') || h).textContent.replace(/\\s+/g, ' ').trim(),
  a: (h.nextElementSibling ? h.nextElementSibling.textContent : '').replace(/\\s+/g, ' ').trim(),
}))"""


def whatsapp_accounts(html: str) -> list[dict[str, str]]:
    """The WhatsApp widget's accounts, as the page's inline settings list them
    (the widget draws them only once opened): name, number, address line."""
    at = html.find('"accounts":')
    if at < 0:
        return []
    try:
        accounts, _ = json.JSONDecoder().raw_decode(html[at + len('"accounts":') :])
    except ValueError:
        return []
    return [
        {
            "name": a.get("accountName", ""),
            "number": a.get("number", ""),
            "title": a.get("title", ""),
        }
        for a in accounts
        if isinstance(a, dict)
    ]


_POSTS = """() => [...document.querySelectorAll('article[id^="post-"]')].map(a => ({
  id: a.id, title: (a.querySelector('.entry-title, h2, h3') || a).innerText.trim(),
  href: (a.querySelector('a[href]') || {}).href || '',
}))"""


def render(page: Any, url: str, anchors: list[tuple[str, str, str, bool]]) -> dict[str, Any]:
    """Load ``url``, close the bottom bar, read every anchor."""
    page.goto(url, wait_until="load", timeout=120_000)
    page.wait_for_timeout(1500)
    height = page.evaluate("document.body.scrollHeight")
    y = 0
    while y < height:
        page.evaluate(f"scrollTo(0, {y})")
        page.wait_for_timeout(120)
        y += 800
        height = page.evaluate("document.body.scrollHeight")
    page.evaluate("scrollTo(0, 0)")
    page.evaluate(
        "document.querySelector('#elementor-popup-modal-480 .dialog-close-button')?.click()"
    )
    page.wait_for_timeout(400)
    reads = page.evaluate(_READ, [[(k, s) for k, s, _, _ in anchors], HEADER_PX])
    return {
        "url": url,
        "title": page.title(),
        "reads": reads,
        "faqs": page.evaluate(_FAQ),
        "whatsapp": whatsapp_accounts(page.content()),
        "posts": page.evaluate(_POSTS),
    }


def crawl(offline: bool) -> dict[str, Any]:
    """Every page of the catalogue, rendered (or from the cache)."""
    posts = get_json(
        f"{SITE}/wp-json/wp/v2/posts?per_page=100&_fields=id,date,link,title,content", offline
    )
    rendered: dict[str, Any] = {}
    todo = [
        (path, anchors + (FOOTER if footer else [])) for path, (_, anchors, footer) in PAGES.items()
    ]
    post_paths = [site_path(p["link"]) for p in posts]
    todo += [(p, POST + FOOTER) for p in post_paths if p]
    if offline:
        for path, _ in todo:
            f = cache_file(SITE + path + "#rendered")
            if not f.exists():
                raise SystemExit(f"{path}: not rendered in the cache; run without --offline first")
            rendered[path] = json.loads(f.read_text(encoding="utf-8"))
        return {"posts": posts, "rendered": rendered}
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="es-CL")
        page = ctx.new_page()
        for path, anchors in todo:
            t0 = time.time()
            got = render(page, SITE + path, anchors)
            bad = [r["key"] for r in got["reads"] if r.get("count") != 1 or r.get("visible") != 1]
            print(
                f"{path}: {len(got['reads'])} anchors in {time.time() - t0:.1f}s; off: {bad}",
                flush=True,
            )
            cache_file(SITE + path + "#rendered").write_text(
                json.dumps(got, ensure_ascii=False), encoding="utf-8"
            )
            rendered[path] = got
        browser.close()
    return {"posts": posts, "rendered": rendered}


# ─── Records ────────────────────────────────────────────────────────────────


def site_path(url: str) -> str | None:
    m = re.match(r"^https?://(?:www\.)?figurella\.cl(/[^?#]*)?", url)
    if not m:
        return None
    path = m.group(1) or "/"
    return path if path.endswith("/") else path + "/"


def fold(text: str) -> str:
    import unicodedata

    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def clean(text: str) -> str:
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", text or "")).strip()


def html_text(html: str) -> str:
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>|</p>|</h\d>|</li>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    for a, b in (
        ("&nbsp;", " "),
        ("&amp;", "&"),
        ("&#8211;", "\u2013"),
        ("&#8220;", "\u201c"),
        ("&#8221;", "\u201d"),
        ("&#8230;", "\u2026"),
        ("&#8217;", "\u2019"),
        ("&#8216;", "\u2018"),
        ("&lt;", "<"),
        ("&gt;", ">"),
        ("&quot;", '"'),
        ("&#038;", "&"),
    ):
        text = text.replace(a, b)
    text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
    return clean(text)


def anchors_record(rendered: dict[str, Any]) -> dict[str, Any]:
    """The catalogue: every anchor the live page showed exactly once."""

    def keep(path: str, rows: list[tuple[str, str, str, bool]]) -> list[dict[str, Any]]:
        reads = {r["key"]: r for r in rendered.get(path, {}).get("reads", [])}
        out = []
        for key, sel, label, hidden in rows:
            r = reads.get(key)
            if r is not None and (r.get("count") != 1 or r.get("visible") != 1):
                print(f"  dropped {path} {key}: count {r.get('count')}, visible {r.get('visible')}")
                continue
            row: dict[str, Any] = {"key": key, "selector": sel, "label": label}
            if hidden:
                row["hidden"] = True
            out.append(row)
        return out

    pages = {
        path: {"kind": kind, "footer": footer, "anchors": keep(path, rows)}
        for path, (kind, rows, footer) in PAGES.items()
    }
    some_post = next((p for p in rendered if p not in PAGES), None)
    faq_ids = {f["id"] for f in rendered.get("/preguntas-frecuentes/", {}).get("faqs", [])}
    faqs = [
        {"key": key, "selector": f"#{fid}", "label": label}
        for key, fid in FAQ_ITEMS
        if fid in faq_ids
        for label in [
            next(f["q"] for f in rendered["/preguntas-frecuentes/"]["faqs"] if f["id"] == fid)
        ]
    ]
    return {
        "_meta": {
            "site": SITE,
            "header_px": HEADER_PX,
            "note": "Built by build.py; every selector matched exactly one laid-out element on the live page.",
        },
        "pages": pages,
        "footer": keep("/", FOOTER),
        "post": keep(some_post, POST) if some_post else [],
        "faqs": faqs,
    }


def pages_record(crawled: dict[str, Any]) -> list[dict[str, Any]]:
    rendered = crawled["rendered"]
    out: list[dict[str, Any]] = []
    for path, (kind, rows, _footer) in PAGES.items():
        got = rendered[path]
        reads = {r["key"]: r for r in got["reads"]}
        sections = []
        for key, _sel, label, hidden in rows:
            r = reads.get(key)
            if hidden or r is None or r.get("count") != 1:
                continue
            sections.append(
                {"key": key, "heading": label, "text": clean(r.get("text", ""))[:TEXT_CAP]}
            )
        rec: dict[str, Any] = {
            "path": path,
            "url": SITE + path,
            "title": got["title"],
            "kind": kind,
            "sections": sections,
        }
        if path == "/preguntas-frecuentes/":
            keys = {fid: key for key, fid in FAQ_ITEMS}
            rec["faqs"] = [
                {"q": f["q"], "key": keys.get(f["id"], f["id"]), "a": f["a"][:TEXT_CAP]}
                for f in got["faqs"]
            ]
        if path == "/consejos/":
            rec["text"] = "Artículos: " + "; ".join(p["title"] for p in got.get("posts", []))
        out.append(rec)
    for post in crawled["posts"]:
        path = site_path(post["link"])
        if not path:
            continue
        title = html_text(post["title"]["rendered"])
        body = html_text(post["content"]["rendered"])
        out.append(
            {
                "path": path,
                "url": post["link"],
                "title": title,
                "kind": "post",
                "date": post["date"][:10],
                "sections": [
                    {"key": "titulo", "heading": title, "text": ""},
                    {
                        "key": "contenido",
                        "heading": f"El artículo «{title}»",
                        "text": body[: TEXT_CAP * 3],
                    },
                ],
            }
        )
    return out


_HOURS = re.compile(r"^(Lunes|Sábados?|Domingos?)\b", re.I)
_PHONE = re.compile(r"^\+?\d[\d ]{7,}$")


def branches_record(rendered: dict[str, Any]) -> list[dict[str, Any]]:
    home = rendered["/"]
    reads = {r["key"]: r for r in home["reads"]}
    widget = home.get("whatsapp", [])
    out = []
    for key, name, _col, (_map, _book), value in BRANCHES:
        r = reads.get(f"sucursal_{key}", {})
        lines = [ln.strip() for ln in (r.get("text") or "").split("\n") if ln.strip()]
        address = next(
            (
                ln
                for ln in lines[1:]
                if not _PHONE.match(ln)
                and not _HOURS.match(ln)
                and "?" not in ln
                and ln.upper() != ln
            ),
            "",
        )
        phone = next((ln for ln in lines if _PHONE.match(ln)), "")
        hours = [ln for ln in lines if _HOURS.match(ln)]
        maps = (reads.get(f"sucursal_{key}_mapa", {}).get("maps") or r.get("maps") or [""])[0]
        wa = next((w for w in widget if fold(name) in fold(w["name"])), None)
        out.append(
            {
                "key": key,
                "name": name,
                "address": address,
                "phone": phone,
                "hours": hours,
                "maps": maps,
                "form_value": value,
                "anchor": f"sucursal_{key}",
                "whatsapp": wa["number"] if wa else "",
            }
        )
    extra = [w for w in widget if "montemar" in fold(w["name"])]
    if extra:
        out.append(
            {
                "key": "montemar",
                "name": "Montemar",
                "address": extra[0]["title"],
                "phone": "",
                "hours": [],
                "maps": "",
                "form_value": "",
                "anchor": "",
                "whatsapp": extra[0]["number"],
                "note": "Only in the WhatsApp widget: not on the home page's cards, and not an option of the booking form.",
            }
        )
    return out


def convenios_record(rendered: dict[str, Any]) -> list[dict[str, Any]]:
    reads = {r["key"]: r for r in rendered["/convenios/"]["reads"]}
    out = []
    for key, partner, _ in CONVENIOS:
        r = reads.get(f"convenio_{key}", {})
        text = clean(r.get("text", ""))
        lines = [ln for ln in text.split("\n") if ln.strip()]
        out.append(
            {
                "key": key,
                "partner": partner,
                "anchor": f"convenio_{key}",
                "discount": lines[0] if lines else "",
                "text": " ".join(lines[1:]),
                "logo": (r.get("img") or [""])[0],
            }
        )
    return out


def write_site_map(anchors: dict[str, Any], pages: list[dict[str, Any]]) -> None:
    lines = [
        "# Mapa del sitio y lugares que Javier puede mostrar",
        "",
        "Sources: figurella.cl, generado por build.py desde L3/anchors.json (cada selector verificado en el sitio).",
        "",
        "Cada página con sus anclas (la clave va en un cue `{show: clave}`). El formulario de reserva",
        "(`contacto`) está al pie de todas las páginas salvo /franquicias/ y /gracias/.",
        "",
    ]
    titles = {p["path"]: p["title"] for p in pages}
    for path, page in anchors["pages"].items():
        lines.append(f"## {path} — {titles.get(path, '')}")
        for a in page["anchors"]:
            if not a.get("hidden"):
                lines.append(f"- `{a['key']}`: {a['label']}")
        if page["footer"]:
            lines.append("- `contacto`: el formulario de reserva (pie de página)")
        if path == "/preguntas-frecuentes/":
            for f in anchors["faqs"]:
                lines.append(f"- pregunta `{f['key']}`: {f['label']}")
        lines.append("")
    lines.append("## Artículos del blog (cada uno en su propia página)")
    for p in pages:
        if p["kind"] == "post":
            lines.append(f"- {p['path']} — {p['title']} ({p.get('date', '')})")
    (HERE / "L2" / "site-map.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("command", choices=["crawl"])
    ap.add_argument("--offline", action="store_true", help="build from the cache only")
    args = ap.parse_args()
    crawled = crawl(args.offline)
    anchors = anchors_record(crawled["rendered"])
    pages = pages_record(crawled)
    dump(L3 / "anchors.json", anchors)
    dump(L3 / "pages.json", pages)
    dump(L3 / "branches.json", branches_record(crawled["rendered"]))
    dump(L3 / "convenios.json", convenios_record(crawled["rendered"]))
    write_site_map(anchors, pages)
    print(f"wrote {L3} ({len(pages)} pages)")


if __name__ == "__main__":
    sys.exit(main())
