"""Build Javier's L3 data for Uno Salud Dental, offline, and check every anchor.

Nothing here touches www.unosalud.cl: the site blocks crawlers (Radware) and is
not reachable from where the brain runs. Everything comes from two places:

- the research notes written while the site was read in a browser (``content.md``,
  every page's sections, verbatim facts and the 103 clinics; ``cta.md``, the
  booking and the lead forms), passed with ``--research DIR``;
- the saved pages in ``demos/unosalud/fixtures`` (the DOM as rendered, scripts
  stripped), which are the ground truth for selectors, and the booking page's
  own clinic tree (``#jsonSucursales`` in ``cta-agenda-tu-hora.html``).

It writes, under ``knowledge/L3``:

- ``anchors.json`` — the keyed catalogue of places a move can ring: key →
  ``{path, selector, text, label: {es, en}}`` (and ``faq`` for an FAQ). The
  extension bundles it. A selector on a page that has a fixture must match
  exactly one element there, or the build fails; a page with no fixture keeps
  its selector only when it is an id the research saw as unique, else the
  ``text`` (heading words) is the extension's way to find it.
- ``pages.json`` — every page, its sections (with their anchor keys) and FAQs:
  what ``search_site`` searches and what the brain checks a cue against.
- ``clinics.json`` — the 103 clinics of ``/clinicas/``, joined to the booking's
  sucursal ids by comuna and street.
- ``faqs.json``, ``promotions.json``, ``motivos.json``.

Run it from ``demos``::

    uv run python unosalud/backend/knowledge/build.py --research /path/to/research

``--check`` only re-checks the committed ``anchors.json`` against the fixtures
(what the test does too).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
# Run as a script from anywhere: the demos folder is where ``unosalud`` imports from.
sys.path.insert(0, str(HERE.parents[2]))

from unosalud.backend import dom  # noqa: E402

L3 = HERE / "L3"
FIXTURES = HERE.parents[1] / "fixtures"
SITE = "https://www.unosalud.cl"

#: Each page with a saved copy, by path.
FIXTURE_FOR: dict[str, str] = {
    "/": "home",
    "/especialidades/": "especialidades",
    "/especialidades/ortodoncia/": "ortodoncia",
    "/clinicas/": "clinicas",
    "/clinicas/moneda/": "clinica-moneda",
    "/promociones/": "promociones",
    "/convenio/": "convenios",
    "/beneficios-y-reembolso/": "beneficios-y-reembolso",
    "/landing/planes-sonrisa-protegida/": "planes-sonrisa-protegida",
    "/urgencias/": "urgencias",
    "/quienes-somos/": "nosotros",
    "/por-que-elegirnos/": "por-que-elegirnos",
    "/contactanos/": "contacto",
    "/preguntas-frecuentes/": "preguntas-frecuentes",
    "/landing/convenio-empresa/": "convenio-empresas",
    "/landing/solicitar-diagnostico/": "cta-te-llamamos",
    "/agenda-tu-hora/": "cta-agenda-tu-hora",
}
#: The clinic page anchors hold on every ``/clinicas/<slug>/`` page; Moneda's is the saved one.
CLINIC_PAGE = "/clinicas/*/"
CLINIC_FIXTURE = "/clinicas/moneda/"

#: The short name of each page, the first part of its anchor keys.
PAGE_KEYS: dict[str, str] = {
    "/": "home",
    "/especialidades/": "especialidades",
    "/especialidades/limpieza-dental/": "limpieza",
    "/especialidades/ortodoncia/": "ortodoncia",
    "/especialidades/implantes-dentales/": "implantes",
    "/especialidades/tratamiento-de-conducto-endodoncia/": "endodoncia",
    "/especialidades/periodoncia/": "periodoncia",
    "/especialidades/odontopediatria/": "odontopediatria",
    "/especialidades/blanqueamiento-dental/": "blanqueamiento",
    "/especialidades/radiologia/": "radiografias",
    "/especialidades/cirugia-oral/": "cirugia",
    "/especialidades/rehabilitacion-oral/": "rehabilitacion",
    "/especialidades/planos-de-relajacion-bruxismo/": "bruxismo",
    "/clinicas/": "clinicas",
    "/clinicas/moneda/": "clinica",
    "/promociones/": "promociones",
    "/convenio/": "convenios",
    "/categoria-convenio/fonasa-e-isapres/": "conv_isapres",
    "/categoria-convenio/cajas-de-compensacion/": "conv_cajas",
    "/categoria-convenio/aseguradoras/": "conv_aseguradoras",
    "/categoria-convenio/cooperativas/": "conv_cooperativas",
    "/categoria-convenio/otros-beneficios/": "conv_otros",
    "/beneficios-y-reembolso/": "beneficios",
    "/beneficios-y-reembolso/pad/": "pad",
    "/beneficios-y-reembolso/ges/": "ges",
    "/beneficios-y-reembolso/seguro-complementario/": "seguro",
    "/beneficios-y-reembolso/excedentes/": "excedentes",
    "/landing/planes-sonrisa-protegida/": "planes",
    "/urgencias/": "urgencias",
    "/quienes-somos/": "nosotros",
    "/por-que-elegirnos/": "porque",
    "/contactanos/": "contacto",
    "/preguntas-frecuentes/": "faq",
    "/landing/convenio-empresa/": "empresas",
    "/landing/solicitar-diagnostico/": "tellamamos",
    "/landing/ortodoncia-oct-2026-org/": "landing_ortodoncia",
    "/landing/caja-los-andes-implantes-org/": "landing_cla",
    "/landing/terminos-y-condiciones-de-campanas/": "tyc_campanas",
}

#: The page kind the extension reports, as the brain's notes name it.
PAGE_KINDS: dict[str, str] = {
    "/": "home",
    "/especialidades/": "specialties",
    "/clinicas/": "clinics",
    "/promociones/": "promotions",
    "/convenio/": "convenios",
    "/beneficios-y-reembolso/": "benefits",
    "/landing/planes-sonrisa-protegida/": "plans",
    "/urgencias/": "urgencias",
    "/quienes-somos/": "about",
    "/por-que-elegirnos/": "why_us",
    "/contactanos/": "contact",
    "/preguntas-frecuentes/": "faq",
    "/landing/convenio-empresa/": "company",
    "/landing/solicitar-diagnostico/": "callback",
    "/agenda-tu-hora/": "booking",
}

#: The skeleton's blocks, named the same on every page by their id.
_SKELETON: dict[str, tuple[str, str]] = {
    "header": ("hero", "Top of the page"),
    "#metodologia": ("preguntas", "Frequently asked questions"),
    "#how": ("proceso", "How the treatment goes"),
    "#cta": ("contactanos", "Contact box"),
    "#cta-2": ("agenda", "Book an appointment strip"),
    "#testimonios": ("testimonios", "Patient reviews"),
    "#related": ("relacionadas", "Related"),
    "#authors": ("comite", "Reviewed by the clinical committee"),
    "related-others": ("articulos", "Related blog posts"),
    "#cta-primary": ("cta", "Book your first diagnosis box"),
}
#: Blocks with nothing to say: pictures, carousels of banners, links back home.
_SKIP_TITLES = re.compile(r"^\(image/visual\)$|^Ir al Inicio$|^QUIERO |^Agenda (?:aquí|tu hora)$")

_STOP = frozenset(
    """a al de del el la las los un una unos unas y o en por para con que se su sus es tu tus
    mi lo como mas nuestro nuestra nuestros nuestras uno salud dental the of and""".split()  # noqa: SIM905
)


def fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def slug(text: str, most: int = 3) -> str:
    words = [w for w in re.findall(r"[a-z0-9]+", fold(text)) if w not in _STOP]
    return "_".join(words[:most]) or "seccion"


# ─── content.md ────────────────────────────────────────────────────────────────


@dataclass
class Faq:
    n: str
    q: str
    a: str = ""


@dataclass
class Section:
    title: str
    raw_selector: str
    note: str
    text: str = ""
    faqs: list[Faq] = field(default_factory=list[Faq])


@dataclass
class PageMap:
    title: str
    path: str
    sections: list[Section] = field(default_factory=list[Section])


_PAGE_HEAD = re.compile(r"^### (.+)$")
_URL = re.compile(r"^- URL: https://www\.unosalud\.cl(/\S*)")
_SECTION = re.compile(r"^\*\*\d+\. (.+?)\*\* — `([^`]+)`(.*)$")
_FAQ = re.compile(r"^  - Q \(`#heading-faq-(\d+)`[^)]*\): \*\*(.+?)\*\*")


def page_maps(content: str) -> list[PageMap]:
    """Section 6 of content.md: every page, its blocks top to bottom, their text and FAQs."""
    start = content.index("## 6. Page-by-page section maps")
    end = content.index("## 7. FAQ page")
    lines = content[start:end].splitlines()
    pages: list[PageMap] = []
    i = 0
    in_text = False
    buf: list[str] = []
    while i < len(lines):
        line = lines[i]
        if in_text:
            if line.startswith("```"):
                in_text = False
                if pages and pages[-1].sections:
                    pages[-1].sections[-1].text += "\n".join(buf)
                buf = []
            else:
                buf.append(line)
            i += 1
            continue
        if line.startswith("```text"):
            in_text = True
            i += 1
            continue
        if (m := _PAGE_HEAD.match(line)) is not None:
            pages.append(PageMap(m.group(1).strip(), ""))
        elif (m := _URL.match(line)) is not None and pages:
            pages[-1].path = m.group(1)
        elif line.startswith("**") and pages:
            # A heading may run over lines: "**12. Señales de alerta:\ncuándo …** — `#content`".
            joined = line
            j = i
            while "** — `" not in joined and j + 1 < len(lines) and j - i < 4:
                j += 1
                joined += " " + lines[j].strip()
            if (m := _SECTION.match(joined)) is not None:
                pages[-1].sections.append(
                    Section(" ".join(m.group(1).split()), m.group(2), m.group(3))
                )
                i = j
        elif (m := _FAQ.match(line)) is not None and pages and pages[-1].sections:
            answer = lines[i + 1].strip() if i + 1 < len(lines) else ""
            pages[-1].sections[-1].faqs.append(
                Faq(m.group(1), m.group(2).strip(), answer.removeprefix("A:").strip())
            )
        i += 1
    return [p for p in pages if p.path]


def faq_page(content: str) -> list[Faq]:
    """Section 7: the /preguntas-frecuentes/ items, verbatim."""
    start = content.index("## 7. FAQ page")
    end = content.index("## 8. Shared blocks")
    out: list[Faq] = []
    lines = content[start:end].splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^- \*\*(.+?)\*\* — `#heading-faq-(\d+)`", line)
        if m is None:
            continue
        answer: list[str] = []
        for nxt in lines[i + 1 :]:
            if nxt.startswith(("- **", "Note:")) or not nxt.strip():
                break
            answer.append(nxt.strip())
        out.append(Faq(m.group(2), m.group(1), " ".join(answer)))
    return out


# ─── Anchors ───────────────────────────────────────────────────────────────────


@dataclass
class Anchor:
    key: str
    path: str
    selector: str
    text: str
    es: str
    en: str
    faq: str = ""
    verified: bool = False

    def record(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "path": self.path,
            "selector": self.selector,
            "text": self.text,
            "label": {"es": self.es, "en": self.en},
        }
        if self.faq:
            out["faq"] = self.faq
        return out


def _selector(section: Section, index: int) -> tuple[str, str]:
    """(selector, skeleton id) for a block of content.md, by what the research saw.

    A theme page's blocks are ``main``'s ``<section>`` children, in order, so a
    block whose id is repeated (``#features`` five times) or missing is
    ``main > section:nth-of-type(i)``; a unique id is itself."""
    raw = section.raw_selector
    if raw.startswith("main#site-main > header"):
        return "main > header", "header"
    if "related-others" in raw:
        return f"main > section:nth-of-type({index})", "related-others"
    if raw.startswith(".elementor-element-"):
        return raw, ""
    if raw.startswith("#") and "occurrence" not in section.note:
        return raw, raw
    return f"main > section:nth-of-type({index})", raw if raw.startswith("#") else ""


#: English for the site's headings Javier is most likely to point at; the rest
#: keep the site's words, which is what the page shows in either language.
_EN: dict[str, str] = {
    "¿Cuánto cuesta el tratamiento de ortodoncia?": "Orthodontics prices",
    "Tipos de ortodoncia y frenillos": "Types of orthodontics and braces",
    "Ortodoncia interceptiva": "Interceptive orthodontics (children)",
    "¿Tienes beneficios o convenios?": "Benefits and agreements",
    "¿Cuánto cuesta un implante dental en Chile? Precios 2026": "Implant prices",
    "Implantes dentales con Fonasa, Isapre y convenios": "Implants with Fonasa, Isapre and agreements",
    "Atención Clínicas Uno Salud Dental": "Clinic opening hours and callback form",
    "Medios de pago": "Payment methods",
    "Garantías": "Guarantees",
    "Deberes y Derechos": "Patient rights and duties",
    "Tecnología": "Technology",
    "Ventajas": "Advantages",
    "Calidad en Insumos": "Quality supplies",
    "Nuestra Misión": "Our mission",
    "Nuestra Promesa": "Our promise",
    "Nuestros Valores": "Our values",
    "Área Clínica": "Clinical team",
    "Seguros y Convenios": "Insurers and agreements",
    "Nuestras Clínicas": "Our clinics",
    "Servicios y especialidades": "Services and specialties",
    "El cuidado que tu sonrisa necesita en un solo plan": "Dental plans",
    "Bienvenido a Clínicas Uno Salud Dental": "Shortcuts",
    "Beneficios y Reembolsos Dentales": "Benefits and reimbursements",
}


#: Keys a reader would not guess from the heading's first words.
_RENAME: dict[str, str] = {
    "home_bienvenido_clinicas": "home_atajos",
    "home_servicios_especialidades": "home_especialidades",
    "home_cuidado_sonrisa_necesita": "home_planes",
    "home_seguros_convenios": "home_convenios",
    "home_seccion": "home_nosotros",
    "home_elegir": "home_por_que",
    "especialidades_especialidades_odontologicas_dentales": "especialidades_lista",
    "ortodoncia_cuanto_cuesta_tratamiento": "ortodoncia_precios",
    "ortodoncia_elegir": "ortodoncia_por_que",
    "implantes_cuanto_cuesta_implante": "implantes_precios",
    "implantes_elegir_implante": "implantes_por_que",
    "implantes_implantes_dentales_fonasa": "implantes_convenios",
    "ortodoncia_tienes_beneficios_convenios": "ortodoncia_convenios",
    "promociones_promociones_dentales": "promociones_lista",
    "convenios_convenios_dentales": "convenios_lista",
    "convenios_beneficios_reembolsos_dentales": "convenios_beneficios",
    "conv_isapres_fonasa_e_isapres": "conv_isapres_lista",
    "conv_cajas_cajas_compensacion": "conv_cajas_lista",
    "conv_aseguradoras_aseguradoras": "conv_aseguradoras_lista",
    "conv_cooperativas_cooperativas": "conv_cooperativas_lista",
    "conv_otros_otros_beneficios": "conv_otros_lista",
    "beneficios_beneficios_reembolsos_dentales": "beneficios_lista",
    "pad_pad": "pad_texto",
    "ges_ges": "ges_texto",
    "seguro_seguro_complementario": "seguro_texto",
    "excedentes_excedentes": "excedentes_texto",
    "planes_sonrisa_familia_estan": "planes_tabla_titulo",
    "planes_hago_uso_plan": "planes_preguntas",
    "urgencias_atencion_clinicas": "urgencias_horario",
    "porque_elegirnos": "porque_hero",
    "contacto_telefono_contacto_centro": "contacto_ayuda",
    "empresas_cuida_sonrisa_colaboradores": "empresas_contacto",
    "tellamamos_te_llamamos_2": "tellamamos_bloque",
    "tellamamos_seccion": "tellamamos_formulario_bloque",
    "tellamamos_agenda_aqui_hora_2": "tellamamos_agenda_2",
}


def section_anchors(pages: list[PageMap]) -> list[Anchor]:
    out: list[Anchor] = []
    taken: set[str] = set()
    for page in pages:
        if page.path.startswith("/clinicas/") and page.path != "/clinicas/":
            path, pkey = CLINIC_PAGE, "clinica"
        elif page.path in PAGE_KEYS:
            path, pkey = page.path, PAGE_KEYS[page.path]
        else:
            continue
        index = 0
        for s in page.sections:
            if not s.raw_selector.startswith(("main#site-main > header", ".elementor")):
                index += 1
            if _SKIP_TITLES.search(s.title) or s.raw_selector.startswith("#banners"):
                continue
            if s.raw_selector.startswith("#gallery") or s.raw_selector.startswith("#breadcrumbs"):
                continue
            selector, skeleton = _selector(s, index)
            name, en = _SKELETON.get(skeleton, ("", ""))
            if skeleton == "header":
                en = f"Top of the page: {s.title}"
            name = name or slug(s.title)
            if name.endswith("recuerda_estamos_aqui"):
                name = "dudas"
            key = _RENAME.get(f"{pkey}_{name}", f"{pkey}_{name}")
            n = 2
            while key in taken:
                key = f"{pkey}_{name}_{n}"
                n += 1
            taken.add(key)
            title = s.title.strip("​ ").rstrip(":")
            out.append(Anchor(key, path, selector, title, title, en or _EN.get(title, title)))
    return out


_SPECIALTIES: list[tuple[str, str, str, str]] = [
    # slug, key, es, en
    ("limpieza-dental", "limpieza", "Limpieza Dental", "Dental cleaning"),
    ("ortodoncia", "ortodoncia", "Ortodoncia", "Orthodontics"),
    ("implantes-dentales", "implantes", "Implantes Dentales", "Dental implants"),
    (
        "tratamiento-de-conducto-endodoncia",
        "endodoncia",
        "Endodoncia \u2013 Tratamiento Conducto",
        "Root canal (endodontics)",
    ),
    ("periodoncia", "periodoncia", "Periodoncia", "Gum treatment (periodontics)"),
    ("odontopediatria", "odontopediatria", "Odontopediatría", "Children's dentistry"),
    ("blanqueamiento-dental", "blanqueamiento", "Blanqueamiento Dental", "Teeth whitening"),
    ("radiologia", "radiografias", "Radiografías Dentales", "Dental X-rays"),
    ("cirugia-oral", "cirugia", "Cirugía Dental Oral", "Oral surgery"),
    ("rehabilitacion-oral", "rehabilitacion", "Rehabilitación Oral", "Oral rehabilitation"),
    (
        "planos-de-relajacion-bruxismo",
        "bruxismo",
        "Plano de Relajación Bruxismo",
        "Bruxism night guard",
    ),
]

#: The promotion cards on /promociones/: WordPress post id, key, card title, English.
PROMOS: list[tuple[str, str, str, str]] = [
    ("46509", "cla_implante", "CLA IOI 2026", "Caja Los Andes implant + crown"),
    ("42398", "ortodoncia_oct", "Ortodoncia OCT", "October orthodontics offer"),
    ("47114", "limpieza_blanqueamiento", "Limpieza OCT BLANQ", "Cleaning + whitening offer"),
    ("47556", "credito_cla", "Credito CLA", "Caja Los Andes health credit"),
    ("42393", "mes_implante", "Mes del Implante AGO26", "Implant month credit"),
    ("37208", "planes", "Planes Sonrisa Protegida", "Sonrisa Protegida plans"),
    ("46105", "hualpen", "Apertura Hualpen", "Hualpén opening offer"),
    ("44237", "puerto_montt", "GEO Zona Pto Montt", "Puerto Montt and Puerto Varas offer"),
    ("40992", "machali", "GEO Zona Rancagua Machali", "Machalí offer"),
    ("40506", "chiguayante", "GEO Chiguayante", "Chiguayante offer"),
]

#: /convenio/ index groups and their cards: category key, the group's heading,
#: English, one card's slug (to find the group), and every card (slug, name).
CONVENIOS: list[tuple[str, str, str, list[tuple[str, str]]]] = [
    (
        "cajas",
        "Cajas de compensación",
        "Compensation funds (cajas)",
        [
            ("la-araucana", "La Araucana"),
            ("caja-los-andes", "Caja Los Andes"),
            ("los-heroes", "Los Héroes"),
            ("caja-18", "Caja 18"),
        ],
    ),
    (
        "isapres",
        "Fonasa e isapres",
        "Fonasa and isapres",
        [
            ("fonasa", "Fonasa"),
            ("consalud", "Consalud"),
            ("isapre-nuevamasvida", "Nueva Masvida"),
            ("cruzblanca", "Cruz Blanca"),
            ("isapre-vidatres", "Vida Tres"),
            ("isapre-banmedica", "Banmédica"),
            ("isapre-colmena", "Colmena"),
        ],
    ),
    (
        "aseguradoras",
        "Aseguradoras",
        "Insurers",
        [
            ("vida-security", "Vida Security"),
            ("help-seguros", "Help Seguros"),
            ("sura", "Sura"),
            ("bice-vida", "Bice Vida"),
            ("consorcio", "Consorcio"),
            ("vidacamara", "Vida Cámara"),
            ("bci-seguros", "BCI Seguros"),
            ("con-futuro", "Confuturo"),
            ("bupa-seguros", "Bupa Seguros"),
            ("zurich", "Zurich"),
        ],
    ),
    ("cooperativas", "Cooperativas", "Cooperatives", [("coopeuch", "Coopeuch")]),
    (
        "otros",
        "Otros beneficios",
        "Other benefits",
        [("banco-falabella", "Banco Falabella"), ("tarjeta-unionsalud", "Tarjeta UniónSalud")],
    ),
]

#: The /preguntas-frecuentes/ items, by the post id in ``#heading-faq-<id>``.
FAQ_KEYS: dict[str, tuple[str, str]] = {
    "14421": ("faq_pad", "How to use PAD"),
    "14417": ("faq_isapre_clinica", "Nearest clinic with an Isapre agreement"),
    "14415": ("faq_ges_dentales", "Which dental GES exist"),
    "14413": ("faq_isapre", "How to be seen through your Isapre"),
    "14402": ("faq_ges", "What GES is"),
    "14410": ("faq_reembolso", "How to get reimbursed"),
    "28633": ("faq_sancionados", "Register of sanctioned professionals"),
    "14408": ("faq_seguro_cubre", "What supplementary insurance covers"),
    "14396": ("faq_tengo_excedentes", "How to know if you have excedentes"),
    "14391": ("faq_excedentes", "What excedentes are"),
    "14339": ("faq_limpieza", "How often to get a cleaning"),
    "14337": ("faq_radiografias", "Digital X-rays"),
    "14333": ("faq_ninos", "Children: from what age"),
    "14331": ("faq_urgencias", "Emergencies: do you see them"),
    "14329": ("faq_muelas_juicio", "Wisdom tooth extraction"),
    "14324": ("faq_colores_frenillos", "Brace colours"),
    "14322": ("faq_duracion_frenillos", "How long braces take"),
    "14320": ("faq_extraccion", "Tooth extraction"),
    "14318": ("faq_conducto_precio", "Root canal price"),
    "14313": ("faq_regiones", "Outside Santiago"),
    "14308": ("faq_precio_frenillos", "Price of braces"),
    "12883": ("faq_seguro", "What supplementary insurance is"),
}


def hand_anchors(clinics: list[dict[str, Any]]) -> list[Anchor]:
    """The cards, tabs, rows and boxes inside the blocks: the places a sentence names."""
    out: list[Anchor] = []
    for slug_, key, es, en in _SPECIALTIES:
        href = f'a[href$="/especialidades/{slug_}/"]'
        out.append(
            Anchor(
                f"especialidades_card_{key}",
                "/especialidades/",
                f"article.card-servicio-2:has({href})",
                es,
                f"Tarjeta {es}",
                f"{en} card",
            )
        )
        out.append(
            Anchor(
                f"home_card_{key}",
                "/",
                f"#services article.card-servicio-2:has({href})",
                es,
                f"Tarjeta {es}",
                f"{en} card",
            )
        )
    tabs = [
        ("metalicos", "Precios Ortodoncia metálica", "Metal braces prices"),
        ("ceramicos", "Precios Ortodoncia cerámica (estética)", "Ceramic braces prices"),
        ("invisible", "Precios Ortodoncia invisible", "Invisible aligners prices"),
    ]
    for i, (key, es, en) in enumerate(tabs):
        out.append(
            Anchor(
                f"ortodoncia_tab_{key}", "/especialidades/ortodoncia/", f"#buttab{i}", es, es, en
            )
        )
        out.append(
            Anchor(
                f"ortodoncia_precios_{key}", "/especialidades/ortodoncia/", f"#tab{i}", es, es, en
            )
        )
    for post, key, es, en in PROMOS:
        out.append(
            Anchor(
                f"promo_{key}", "/promociones/", f"article.card-promociones.post-{post}", es, es, en
            )
        )
    for cat, es, en, cards in CONVENIOS:
        first = cards[0][0]
        out.append(
            Anchor(
                f"convenios_{cat}",
                "/convenio/",
                f'div.container:has(> h2):has(a[href$="/convenio/{first}/"])',
                es,
                es,
                en,
            )
        )
        for card, name in cards:
            ckey = slug(card.replace("isapre-", ""), 2)
            out.append(
                Anchor(
                    f"convenio_{ckey}",
                    "/convenio/",
                    f'div.card:has(> a[href$="/convenio/{card}/"])',
                    "",
                    f"Logo {name}",
                    f"{name} logo",
                )
            )
    for slug_, key, es, en in [
        ("pad", "pad", "PAD", "PAD (diagnosis-linked payment)"),
        ("ges", "ges", "GES", "GES (guaranteed coverage)"),
        ("seguro-complementario", "seguro", "Seguro Complementario", "Supplementary insurance"),
        ("excedentes", "excedentes", "Excedentes", "Isapre surplus (excedentes)"),
    ]:
        sel = f'article:has(a[href$="/beneficios-y-reembolso/{slug_}/"])'
        out.append(Anchor(f"beneficios_card_{key}", "/beneficios-y-reembolso/", sel, es, es, en))
        out.append(
            Anchor(f"convenios_beneficio_{key}", "/convenio/", f"#beneficios {sel}", es, es, en)
        )
    payments = [
        ("efectivo", "Efectivo o tarjeta de débito", "Cash or debit card"),
        ("cheques", "Cheques", "Cheques"),
        ("excedentes", "Excedentes Isapre", "Isapre surplus"),
        ("seguro", "Seguro Complementario", "Supplementary insurance"),
        ("tarjetas", "Tarjetas Bancarias", "Bank cards"),
    ]
    for i, (key, es, en) in enumerate(payments, 1):
        out.append(
            Anchor(
                f"porque_pago_{key}",
                "/por-que-elegirnos/",
                f"main > section:nth-of-type(7) div.row.justify-content-center > div:nth-of-type({i})",
                es,
                es,
                en,
            )
        )
    out += [
        Anchor(
            "porque_tab_cerec",
            "/por-que-elegirnos/",
            "#buttab3",
            "Tecnología 3D Cerec",
            "Tecnología 3D Cerec",
            "3D Cerec technology",
        ),
        Anchor(
            "porque_tab_sedacion",
            "/por-que-elegirnos/",
            "#buttab5",
            "Sedación consciente con oxido nitroso",
            "Sedación consciente",
            "Conscious sedation",
        ),
        Anchor(
            "planes_precios",
            "/landing/planes-sonrisa-protegida/",
            "#miseccion",
            "",
            "Tabla de precios de los planes",
            "Plans price table",
        ),
        Anchor(
            "clinica_horario",
            CLINIC_PAGE,
            "main > header div.shadow-sm div.col-lg-6:nth-of-type(1)",
            "Horario de atención",
            "Horario de atención",
            "Opening hours",
        ),
        Anchor(
            "clinica_referencias",
            CLINIC_PAGE,
            "main > header div.shadow-sm div.col-lg-6:nth-of-type(2)",
            "Referencias",
            "Referencias",
            "How to find it (landmarks)",
        ),
        Anchor(
            "clinica_mapa",
            CLINIC_PAGE,
            "#mapa-single",
            "¿Cómo llegar?",
            "Mapa",
            "Map and directions",
        ),
        Anchor(
            "clinicas_buscador",
            "/clinicas/",
            "#sucursales",
            "Sucursales y Horarios de Atención",
            "Buscador de clínicas",
            "Clinic finder",
        ),
        Anchor(
            "clinicas_lista", "/clinicas/", "#mapa-list", "", "Lista de clínicas", "Clinic list"
        ),
        Anchor("clinicas_mapa", "/clinicas/", "#mapa", "", "Mapa de clínicas", "Clinic map"),
        Anchor(
            "urgencias_formulario",
            "/urgencias/",
            "#form-side form#sib-form",
            "",
            "Formulario: un ejecutivo te contacta",
            "Callback form",
        ),
        Anchor(
            "tellamamos_formulario",
            "/landing/solicitar-diagnostico/",
            "form#sib-form",
            "TE LLAMAMOS",
            "Formulario Te llamamos",
            "Callback form",
        ),
        Anchor(
            "empresas_formulario",
            "/landing/convenio-empresa/",
            "form#sib-form",
            "",
            "Formulario Convenio Empresas",
            "Company agreement form",
        ),
        Anchor(
            "faq_lista",
            "/preguntas-frecuentes/",
            "#accordionFaqs",
            "",
            "Preguntas frecuentes",
            "Frequently asked questions",
        ),
    ]
    for c in clinics:
        out.append(
            Anchor(
                f"clinicas_{c['key']}",
                "/clinicas/",
                f'#mapa-list [data-target="{c["id"]}"]',
                "",
                f"Clínica {c['name']}",
                f"{c['name']} clinic",
            )
        )
    return out


def faq_anchors(pages: list[PageMap], faqs: list[Faq]) -> list[Anchor]:
    out: list[Anchor] = []
    for f in faqs:
        key, en = FAQ_KEYS.get(f.n, (f"faq_{f.n}", f.q))
        out.append(
            Anchor(key, "/preguntas-frecuentes/", f"#heading-faq-{f.n}", f.q, f.q, en, faq=f.n)
        )
    for page in pages:
        pkey = PAGE_KEYS.get(page.path)
        if pkey is None or page.path == "/preguntas-frecuentes/":
            continue
        for s in page.sections:
            for f in s.faqs:
                key = f"faq_{pkey}_{f.n}"
                out.append(Anchor(key, page.path, f"#heading-faq-{f.n}", f.q, f.q, f.q, faq=f.n))
    return out


def plan_faqs(root: dom.Element) -> list[Anchor]:
    """The Planes Sonrisa Protegida FAQ: Elementor ``<details>``, opened by their summary."""
    out: list[Anchor] = []
    for i, d in enumerate(dom.select(root, "details.e-n-accordion-item"), 1):
        q = next((c.text() for c in d.children if c.tag == "summary"), "")
        out.append(
            Anchor(
                f"faq_planes_{i}",
                "/landing/planes-sonrisa-protegida/",
                f"#{d.id} > summary",
                q,
                q,
                q,
                faq=d.id,
            )
        )
    return out


def check(anchors: list[Anchor]) -> list[str]:
    """Every anchor on a saved page must find exactly one element there."""
    roots: dict[str, dom.Element] = {}
    problems: list[str] = []
    for a in anchors:
        page = CLINIC_FIXTURE if a.path == CLINIC_PAGE else a.path
        name = FIXTURE_FOR.get(page)
        if name is None or not a.selector:
            continue
        if name not in roots:
            roots[name] = dom.parse_file(FIXTURES / f"{name}.html")
        n = dom.count(roots[name], a.selector)
        if n == 1:
            a.verified = True
        else:
            problems.append(f"{a.key}: {a.selector!r} matches {n} on {name}.html")
    return problems


# ─── Clinics ───────────────────────────────────────────────────────────────────

_ROW = re.compile(r"^\| (\d+) \| (.+)$")


def clinic_rows(content: str) -> list[dict[str, Any]]:
    start = content.index("## 4. Clinics")
    end = content.index("## 5. Convenio detail pages")
    rows: list[dict[str, Any]] = []
    for line in content[start:end].splitlines():
        if _ROW.match(line) is None:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 10:
            continue
        _, name, address, comuna, region, hours, refs, url, row, maps = cells[:10]
        cid = re.search(r'data-target="(\d+)"', row)
        link = re.search(r"\((https://www\.google\.com/maps/[^)]+)\)", maps)
        path = url.strip("`")
        rows.append(
            {
                "key": slug(path.strip("/").split("/")[-1].replace("-", " "), 6),
                "id": cid.group(1) if cid else "",
                "name": name,
                "address": address,
                "comuna": comuna,
                "region": region,
                "hours": "" if hours.startswith("(") else hours,
                "references": refs,
                "path": path,
                "url": SITE + path,
                "maps_url": link.group(1) if link else "",
            }
        )
    return rows


def sucursales() -> list[dict[str, str]]:
    html = (FIXTURES / "cta-agenda-tu-hora.html").read_text(encoding="utf-8")
    m = re.search(r'<script[^>]*id="jsonSucursales"[^>]*>(.*?)</script>', html, re.S)
    if m is None:
        raise SystemExit("no #jsonSucursales in cta-agenda-tu-hora.html")
    tree: dict[str, Any] = json.loads(m.group(1))
    out: list[dict[str, str]] = []
    for region in sorted(tree.values(), key=lambda r: int(r.get("prioridad") or 99)):
        for comuna in region["comunas"].values():
            for s in comuna["sucursales"]:
                out.append(
                    {
                        "id": str(s["id"]),
                        "name": " ".join(str(s["descripcion"]).split()),
                        "region_id": str(region["id"]),
                        "region": str(region["descripcion"]),
                        "comuna_id": str(comuna["id"]),
                        "comuna": str(comuna["descripcion"]),
                    }
                )
    return out


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", fold(text)) if len(w) > 2 and w not in _STOP}


def join_clinics(rows: list[dict[str, Any]], booking: list[dict[str, str]]) -> None:
    """Give each clinic its booking sucursal: same comuna, then the most shared
    words of name, address and references; one sucursal per clinic."""
    used: set[str] = set()
    scored: list[tuple[float, int, str]] = []
    for i, r in enumerate(rows):
        theirs = _words(f"{r['name']} {r['address']} {r['references']}")
        for s in booking:
            if fold(s["comuna"]) != fold(r["comuna"]):
                continue
            ours = _words(s["name"])
            score = len(theirs & ours) + 0.01
            scored.append((score, i, s["id"]))
    by_id = {s["id"]: s for s in booking}
    done: set[int] = set()
    for score, i, sid in sorted(scored, key=lambda t: -t[0]):
        if i in done or sid in used:
            continue
        # A lone sucursal in a lone clinic's comuna is a match without shared words.
        same = [s for s in booking if fold(s["comuna"]) == fold(rows[i]["comuna"])]
        if score < 1 and len(same) > 1:
            continue
        done.add(i)
        used.add(sid)
        s = by_id[sid]
        rows[i].update(
            booking_id=sid,
            booking_name=s["name"],
            booking_region=s["region"],
            booking_comuna=s["comuna"],
        )
    for i, r in enumerate(rows):
        if i not in done:
            same = [s for s in booking if fold(s["comuna"]) == fold(r["comuna"])]
            r.update(
                booking_id="",
                booking_name="",
                booking_region=same[0]["region"] if same else "",
                booking_comuna=same[0]["comuna"] if same else "",
            )


# ─── The rest ──────────────────────────────────────────────────────────────────

MOTIVOS: list[dict[str, Any]] = [
    {"id": 14, "name": "Limpieza Dental", "en": "Dental cleaning"},
    {
        "id": 15,
        "name": "Urgencia (De ortodoncia, dolor agudo o fractura dental)",
        "en": "Emergency (orthodontic, acute pain or a broken tooth)",
    },
    {
        "id": 16,
        "name": "Instalación de frenillos o alineadores invisibles",
        "en": "Braces or invisible aligners",
    },
    {"id": 17, "name": "Implantes dentales (solución fija)", "en": "Dental implants (fixed)"},
    {"id": 18, "name": "Prótesis dental (solución removible)", "en": "Dentures (removable)"},
    {
        "id": 19,
        "name": "Estética dental (blanqueamiento o carillas)",
        "en": "Cosmetic (whitening or veneers)",
    },
    {"id": 20, "name": "Atención infantil (odontopediatría)", "en": "Children's care"},
    {"id": 21, "name": "Sangrado de encías o mal aliento", "en": "Bleeding gums or bad breath"},
    {"id": 22, "name": "Chequeo y diagnóstico general", "en": "General check-up and diagnosis"},
    {"id": 23, "name": "No estoy seguro", "en": "Not sure"},
]

#: The promotions with what the research read off each card and landing; the
#: ``promo`` code is the one the landing's booking link carries, where it was seen.
PROMOTIONS: list[dict[str, Any]] = [
    {
        "key": "cla_implante",
        "card": "CLA IOI 2026",
        "landing": "/landing/caja-los-andes-implantes-org/",
        "valid_until": "2026-12-31",
        "promo": "",
        "summary": "Implante + corona por $279.000 (precio referencial $838.800), BioHorizons, "
        "garantía de por vida en el implante. Exclusivo para afiliados titulares de Caja Los "
        "Andes mayores de 50 años. Válido para agendar, asistir y pagar desde el 28 de "
        "septiembre hasta el 31 de diciembre de 2026 o hasta agotar 2.500 cupos. Se paga "
        "aparte, si el caso lo requiere: pack de diagnóstico y radiografías, tratamiento "
        "periodontal, cirugías complementarias, diente provisorio.",
    },
    {
        "key": "ortodoncia_oct",
        "card": "Ortodoncia OCT",
        "landing": "/landing/ortodoncia-oct-2026-org/",
        "valid_until": "2026-10-31",
        "promo": "ortodonciaoctnov26",
        "summary": "Estudio de ortodoncia + instalación de brackets metálicos por $299.900, "
        "exclusivo al contratar el Plan Sonrisa Protegida Plus o Full; sin esos planes, el "
        "estudio + instalación es $349.900. Válido hasta el 31 de octubre de 2026.",
    },
    {
        "key": "limpieza_blanqueamiento",
        "card": "Limpieza OCT BLANQ",
        "landing": "/landing/limpieza-oct-26-blanqueamiento-org/",
        "valid_until": "2026-10-31",
        "promo": "",
        "summary": "Limpieza dental + radiografías y diagnóstico por $12.900; agrega una sesión de "
        "blanqueamiento por $34.900 (antes $79.000). Válido para agendar, asistir y pagar del 1 "
        "al 31 de octubre de 2026, agendando desde esa publicación. No aplica para pacientes "
        "con enfermedad periodontal.",
    },
    {
        "key": "credito_cla",
        "card": "Credito CLA",
        "landing": "/landing/caja-los-andes-credito300-org/",
        "valid_until": "",
        "promo": "",
        "summary": "Usa tu Crédito de Salud Caja Los Andes, hasta $300.000, en hasta 6 cuotas, "
        "presentando tu carnet.",
    },
    {
        "key": "mes_implante",
        "card": "Mes del Implante AGO26",
        "landing": "/landing/implantes-agosto-26-org/",
        "valid_until": "2026-10-31",
        "promo": "",
        "summary": "Abono de hasta $150.000 en cada implante dental, con insumos BioHorizons y "
        "garantía de por vida en el implante (asistiendo a los controles). El abono máximo es "
        "exclusivo al contratar el Plan Sonrisa Protegida Plus o Full. Válido para pagar hasta "
        "el 31 de octubre de 2026.",
    },
    {
        "key": "planes",
        "card": "Planes Sonrisa Protegida",
        "landing": "/landing/planes-sonrisa-protegida/",
        "valid_until": "",
        "promo": "Membresia_Feb_2025",
        "summary": "Planes Lite, Plus y Full: descuentos en tratamientos, limpiezas, flúor y "
        "cobertura de urgencias (ver el tema planes).",
    },
    {
        "key": "hualpen",
        "card": "Apertura Hualpen",
        "landing": "/landing/campana-geo-hualpen-organico/",
        "valid_until": "2026-10-31",
        "promo": "",
        "summary": "Nueva clínica Hualpén (Av. Colón 7948, strip center): limpieza dental $9.900 "
        "+ radiografías y diagnóstico, y $30.000 de bonificación en tu tratamiento pagando desde "
        "$180.000. Del 1 de septiembre al 31 de octubre de 2026 o hasta agotar cupos. No aplica "
        "con enfermedad periodontal.",
    },
    {
        "key": "puerto_montt",
        "card": "GEO Zona Pto Montt",
        "landing": "/landing/campana-geo-zona-pto-montt-org/",
        "valid_until": "2026-10-31",
        "promo": "",
        "summary": "Puerto Montt y Puerto Varas: limpieza dental $9.900 con diagnóstico y "
        "radiografías, y $30.000 de bonificación pagando desde $180.000 en un tratamiento. Hasta "
        "el 31 de octubre de 2026 o hasta agotar cupos, agendando desde esa publicación. No "
        "aplica con enfermedad periodontal.",
    },
    {
        "key": "machali",
        "card": "GEO Zona Rancagua Machali",
        "landing": "/landing/campana-geo-machali-organica/",
        "valid_until": "2026-10-31",
        "promo": "",
        "summary": "Machalí: diagnóstico + radiografías y limpieza dental $9.900, y un abono de "
        "$30.000 pagando desde $180.000. Hasta el 31 de octubre de 2026 o hasta agotar cupos, "
        "agendando desde esa publicación. No aplica con enfermedad periodontal.",
    },
    {
        "key": "chiguayante",
        "card": "GEO Chiguayante",
        "landing": "/landing/campana-geo-chiguayante-organico/",
        "valid_until": "2026-10-31",
        "promo": "",
        "summary": "Chiguayante (Av. 8 Oriente N°720): limpieza dental $9.900 + radiografías y "
        "diagnóstico, y $30.000 de bonificación desde $180.000. Del 1 de septiembre al 31 de "
        "octubre de 2026 o hasta agotar cupos, agendando desde esa publicación. Sujeto a "
        "evaluación clínica; no aplica con enfermedad periodontal.",
    },
]


def pages_record(pages: list[PageMap], anchors: list[Anchor]) -> list[dict[str, Any]]:
    by_text: dict[tuple[str, str], str] = {(a.path, a.es): a.key for a in anchors}
    out: list[dict[str, Any]] = []
    for p in pages:
        path = CLINIC_PAGE if p.path.startswith("/clinicas/") and p.path != "/clinicas/" else p.path
        if path not in PAGE_KEYS and path != CLINIC_PAGE:
            continue
        kind = PAGE_KINDS.get(p.path) or (
            "specialty"
            if p.path.startswith("/especialidades/")
            else "clinic"
            if path == CLINIC_PAGE
            else "convenio"
            if p.path.startswith("/categoria-convenio/")
            else "benefits"
            if p.path.startswith("/beneficios-y-reembolso/")
            else "promo_landing"
            if p.path.startswith("/landing/")
            else "page"
        )
        sections: list[dict[str, Any]] = []
        faqs: list[dict[str, str]] = []
        for s in p.sections:
            title = s.title.strip("​ ").rstrip(":")
            if _SKIP_TITLES.search(s.title):
                continue
            sections.append(
                {
                    "heading": title,
                    "anchor": by_text.get((path, title), ""),
                    "text": " ".join(s.text.split())[:1500],
                }
            )
            faqs += [{"n": f.n, "q": f.q, "a": f.a} for f in s.faqs]
        out.append(
            {
                "path": p.path if path != CLINIC_PAGE else CLINIC_PAGE,
                "title": p.title,
                "kind": kind,
                "sections": sections,
                "faqs": faqs,
            }
        )
    return out


#: The pages written out whole as L2 topics, verbatim from the research: topic id, title.
L2_PAGES: dict[str, tuple[str, str]] = {
    "/especialidades/limpieza-dental/": ("limpieza", "Limpieza dental (destartraje)"),
    "/especialidades/ortodoncia/": ("ortodoncia", "Ortodoncia: brackets, alineadores y precios"),
    "/especialidades/implantes-dentales/": ("implantes", "Implantes dentales y precios"),
    "/especialidades/tratamiento-de-conducto-endodoncia/": ("endodoncia", "Endodoncia"),
    "/especialidades/periodoncia/": ("periodoncia", "Periodoncia (encías)"),
    "/especialidades/odontopediatria/": ("odontopediatria", "Odontopediatría (niños)"),
    "/especialidades/blanqueamiento-dental/": ("blanqueamiento", "Blanqueamiento dental"),
    "/especialidades/radiologia/": ("radiografias", "Radiografías dentales"),
    "/especialidades/cirugia-oral/": ("cirugia", "Cirugía oral (extracciones)"),
    "/especialidades/rehabilitacion-oral/": ("rehabilitacion", "Rehabilitación oral (prótesis)"),
    "/especialidades/planos-de-relajacion-bruxismo/": (
        "bruxismo",
        "Plano de relajación (bruxismo)",
    ),
    "/landing/planes-sonrisa-protegida/": ("planes_pagina", "Planes Sonrisa Protegida: la página"),
    "/urgencias/": ("urgencias", "Urgencias dentales"),
    "/quienes-somos/": ("nosotros", "Quiénes somos"),
    "/por-que-elegirnos/": ("por_que_elegirnos", "Por qué elegirnos, garantías y tecnología"),
    "/beneficios-y-reembolso/pad/": ("pad", "PAD dental"),
    "/beneficios-y-reembolso/ges/": ("ges", "GES dental"),
    "/beneficios-y-reembolso/seguro-complementario/": (
        "seguro_complementario",
        "Seguro complementario",
    ),
    "/beneficios-y-reembolso/excedentes/": ("excedentes", "Excedentes de Isapre"),
    "/landing/convenio-empresa/": ("convenio_empresas", "Convenio Empresas"),
    "/landing/ortodoncia-oct-2026-org/": (
        "landing_ortodoncia",
        "Promoción Ortodoncia OCT: la página",
    ),
    "/landing/caja-los-andes-implantes-org/": (
        "landing_cla",
        "Promoción Caja Los Andes implantes: la página",
    ),
}
#: Blocks every page repeats, which a topic does not need.
_BOILERPLATE = re.compile(
    r"^(?:Lo que (?:opinan|dicen) nuestros pacientes|Especialidades relacionadas|"
    r"Artículos relacionados|Agenda tu hora con nosotros|Recuerda que estamos|"
    r"Contenido revisado|Testimonios de pacientes)"
)


def write_l2(pages: list[PageMap]) -> int:
    """One topic per page of L2_PAGES: its blocks' text and its FAQs, verbatim."""
    (HERE / "L2").mkdir(exist_ok=True)
    n = 0
    for page in pages:
        if page.path not in L2_PAGES:
            continue
        topic, title = L2_PAGES[page.path]
        out = [
            f"# {title}",
            "",
            f"Sources: {SITE}{page.path} (texto del sitio, copiado tal cual por "
            "knowledge/build.py; no editar a mano).",
            "",
        ]
        for s in page.sections:
            if _SKIP_TITLES.search(s.title) or _BOILERPLATE.search(s.title) or not s.text.strip():
                continue
            out += [f"## {s.title.rstrip(':')}", "", " ".join(s.text.split())[:2500], ""]
            for f in s.faqs:
                out += [f"- **{f.q}** {f.a}"]
            if s.faqs:
                out.append("")
        (HERE / "L2" / f"{topic}.md").write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
        n += 1
    return n


def write_generated_topics(faqs: list[Faq], anchors: list[Anchor]) -> None:
    """The topics made from the L3 data: promotions, the FAQ page, the site map."""
    out = [
        "# Promociones vigentes y sus condiciones",
        "",
        f"Sources: {SITE}/promociones/ (cada tarjeta y su página; condiciones leídas de las "
        "imágenes y las páginas). Generado por knowledge/build.py.",
        "",
        "Los valores pueden cambiar según los beneficios de cada paciente. Una promoción se "
        "menciona solo con su fecha de término; pasada esa fecha, ya no se ofrece.",
        "",
    ]
    for p in PROMOTIONS:
        until = (
            f" Válida hasta el {p['valid_until']}." if p["valid_until"] else " Sin fecha publicada."
        )
        out.append(
            f"- **{p['card']}** (lugar promo_{p['key']}; página {p['landing']}).{until} {p['summary']}"
        )
    (HERE / "L2" / "promociones.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    out = [
        "# Preguntas frecuentes del sitio (textuales)",
        "",
        f"Sources: {SITE}/preguntas-frecuentes/. Generado por knowledge/build.py; cada una "
        "con la clave para abrirla.",
        "",
    ]
    for f in faqs:
        key = FAQ_KEYS.get(f.n, (f"faq_{f.n}", ""))[0]
        out.append(f"- **{f.q}** ({key}) {f.a}")
    (HERE / "L2" / "preguntas_frecuentes.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    out = [
        "# Mapa del sitio: páginas y lugares",
        "",
        "Sources: knowledge/L3/anchors.json (generado por knowledge/build.py). Cada lugar con "
        "su clave, para {show: clave}.",
        "",
    ]
    by_path: dict[str, list[Anchor]] = {}
    for a in anchors:
        if a.key.startswith(("clinicas_", "convenio_")) and a.key not in (
            "clinicas_buscador",
            "clinicas_lista",
            "clinicas_mapa",
        ):
            continue
        by_path.setdefault(a.path, []).append(a)
    for path, items in by_path.items():
        out.append(f"- {path}")
        out += [f"  - {a.key}: {a.es}" for a in items]
    (HERE / "L2" / "mapa_del_sitio.md").write_text("\n".join(out) + "\n", encoding="utf-8")


def dump(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def load_anchors() -> list[Anchor]:
    raw: dict[str, Any] = json.loads((L3 / "anchors.json").read_text(encoding="utf-8"))
    return [
        Anchor(
            k,
            v["path"],
            v["selector"],
            v.get("text", ""),
            v["label"]["es"],
            v["label"]["en"],
            v.get("faq", ""),
        )
        for k, v in raw.items()
        if not k.startswith("_")
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--research", type=Path, help="the folder with content.md and cta.md")
    parser.add_argument("--check", action="store_true", help="only check anchors.json")
    args = parser.parse_args(argv)
    if args.check:
        problems = check(load_anchors())
        print("\n".join(problems) or "anchors: every selector on a saved page matches once")
        return 1 if problems else 0
    if args.research is None:
        parser.error("--research is required to build")
    content = (args.research / "content.md").read_text(encoding="utf-8")
    pages = page_maps(content)
    clinics = clinic_rows(content)
    join_clinics(clinics, sucursales())
    anchors = section_anchors(pages) + hand_anchors(clinics) + faq_anchors(pages, faq_page(content))
    anchors += plan_faqs(dom.parse_file(FIXTURES / "planes-sonrisa-protegida.html"))
    seen: set[str] = set()
    for a in anchors:
        if a.key in seen:
            raise SystemExit(f"duplicate anchor key {a.key}")
        seen.add(a.key)
    problems = check(anchors)
    # A block the research placed by order that the saved page shows elsewhere:
    # its words still find it.
    for line in problems:
        print("anchor:", line, file=sys.stderr)
    if problems:
        return 1
    catalogue: dict[str, Any] = {
        "_meta": {
            "site": SITE,
            "clinic_page": CLINIC_PAGE,
            "note": "Built by knowledge/build.py from saved pages; every selector on a page "
            "with a fixture matches exactly one element there. 'text' is the heading words to "
            "fall back on. 'faq' opens #heading-faq-<faq> (Bootstrap), or the <details id=faq>.",
        }
    }
    catalogue |= {a.key: a.record() for a in anchors}
    dump(L3 / "anchors.json", catalogue)
    dump(L3 / "pages.json", pages_record(pages, anchors))
    dump(L3 / "clinics.json", clinics)
    dump(L3 / "motivos.json", MOTIVOS)
    dump(L3 / "promotions.json", PROMOTIONS)
    faqs = [
        {"key": FAQ_KEYS.get(f.n, (f"faq_{f.n}", ""))[0], "n": f.n, "q": f.q, "a": f.a}
        for f in faq_page(content)
    ]
    dump(L3 / "faqs.json", faqs)
    topics = write_l2(pages)
    write_generated_topics(faq_page(content), anchors)
    print(f"L2: {topics} page topics written")
    verified = sum(a.verified for a in anchors)
    joined = sum(1 for c in clinics if c["booking_id"])
    print(
        f"anchors: {len(anchors)} ({verified} checked on saved pages); pages: {len(pages)}; "
        f"clinics: {len(clinics)} ({joined} joined to a booking sucursal)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
