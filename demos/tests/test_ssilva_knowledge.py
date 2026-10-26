"""Ssilva's knowledge and the brain's pure helpers, without a session.

``find_projects`` filters the roster the way a visitor asks — in Spanish or
English, loosely spelled, by a nickname for a place — and says which wish it had
to drop when nothing fits. The rest: names matched loosely, typologies and
sections a sentence is about, a RUT checked, amounts mapped to the form's
ranges, and the committed crawl itself.

Run: ``cd demos && uv run pytest tests/test_ssilva_knowledge.py``
"""

from __future__ import annotations

import pytest
from voqalize_demos.discovery import discover

discover()

from voqalize_demos._loaded.ssilva import brain as ssilva  # noqa: E402
from voqalize_demos._loaded.ssilva import knowledge as kb  # noqa: E402

K = kb.KNOWLEDGE


def _names(**filters: object) -> list[str]:
    return [p.name for p in K.find_projects(**filters).projects]  # type: ignore[arg-type]


def test_the_committed_crawl_loads() -> None:
    listed = [p for p in K.projects.values() if p.listed]
    assert len(listed) >= 20
    assert K.project("Alto Quintay") is not None and not K.project("Alto Quintay").listed  # type: ignore[union-attr]
    for p in K.projects.values():
        if p.path:
            page = K.page(p.path)
            assert page is not None and page.kind == "project", p.path
            assert K.project_at(p.path) is p
            assert K.project_text(p).startswith(f"# {p.name}")
    assert set(kb.TOPIC_IDS) >= {"comprar-en-chile", "centro-de-negocios", "glosario"}
    # Every comuna the list filters by is a comuna of a project.
    assert set(kb.COMMUNE_IDS) <= {p.comuna for p in listed}


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        (
            {"comuna": "Viña", "dormitorios": 2},
            {"Isla Picton", "Vistamar", "Mira al Mar", "Canal Beagle"},
        ),
        ({"comuna": "vina del mar"}, {"Isla Picton", "Vistamar", "Mira al Mar", "Canal Beagle"}),
        ({"comuna": "Las Condes"}, {"Estocolmo", "Los Navegantes", "Oficinas Apoquindo Moro"}),
        ({"comuna": "las condes", "tipo": "apartment"}, {"Estocolmo", "Los Navegantes"}),
        (
            {"comuna": "Santiago centro", "perfil": "invest", "tipo": "departamento"},
            {"Distrito Barroso", "Edificio Rondizzoni", "Edificio Santa Victoria 155"},
        ),
        ({"tipo": "house"}, {"Mirador Piedra Roja", "Vista Golf"}),
        ({"tipo": "oficina"}, {"Oficinas Apoquindo Moro"}),
        # Mira al Mar went from 2.836 to 3.035 UF on the list (crawl of 2026-10-26).
        ({"region": "playa", "max_uf": 3000}, {"Isla Picton", "Vistamar"}),
        (
            {"region": "the coast", "estado": "ready", "dormitorios": 3},
            {"Mira al Mar", "Canal Beagle", "Playa Cochoa"},
        ),
        ({"comuna": "Macul"}, {"Edificio Limit"}),
        (
            {"comuna": "Las Condes, Vitacura", "perfil": "vivir", "min_uf": 10000},
            {"Estocolmo", "Los Navegantes", "Edificio Uniq"},
        ),
        (
            {"perfil": "segunda vivienda", "estado": "en blanco"},
            {"Lagunamar Brisas", "Aires de Quintay", "Vistamar"},
        ),
        ({"dormitorios": 0, "comuna": "La Florida"}, {"Edificio Millalongo 72"}),
    ],
)
def test_find_projects_reads_the_visitor_s_words(
    filters: dict[str, object], expected: set[str]
) -> None:
    found = K.find_projects(**filters)  # type: ignore[arg-type]
    assert {p.name for p in found.projects} == expected
    assert found.dropped == () and found.unknown == ()
    prices = [p.desde_uf or 0 for p in found.projects]
    assert prices == sorted(prices)


def test_a_wish_nothing_fits_is_dropped_and_named() -> None:
    found = K.find_projects(comuna="Las Condes", max_uf=3000, perfil="segunda vivienda")
    assert "perfil (Segunda vivienda)" in found.dropped
    assert [p.name for p in found.projects] == ["Oficinas Apoquindo Moro"]
    unknown = K.find_projects(comuna="Marte")
    assert unknown.unknown == ("Marte",)
    # Alto Quintay is not on the list: find_projects does not offer it.
    assert "Alto Quintay" not in _names(comuna="Quintay")


@pytest.mark.parametrize(
    ("said", "name"),
    [
        ("estocolmo", "Estocolmo"),
        ("Edificio Uniq", "Edificio Uniq"),
        ("el limit", "Edificio Limit"),
        ("Lagunamar Dunas", "Lagunamar Dunas"),
        ("arrayan", "Parque el Rodeo Arrayán"),
        ("la poza", "La Poza de Pucón"),
        ("/canalbeagle/", "Canal Beagle"),
        ("https://www.ssilva.cl/isla-picton/", "Isla Picton"),
        ("lagunamar", None),
        ("parque el rodeo", None),
        ("torre inventada", None),
    ],
)
def test_a_project_is_named_loosely(said: str, name: str | None) -> None:
    p = K.project(said)
    assert (p.name if p else None) == name


@pytest.mark.parametrize(
    ("text", "path"),
    [
        ("Háblame de Estocolmo", "/estocolmo"),
        ("tell me about canal beagle please", "/canalbeagle"),
        ("¿Y el Uniq?", "/uniq"),
        ("¿Qué es el centro de negocios?", "/centro-de-negocios"),
        ("Who is Ssilva? Tell me about the company.", "/sobre-nosotros"),
        ("¿Estocolmo o Uniq?", None),
        ("Distrito Barroso", "/distrito-barroso"),
        ("¿Puedes hablar en inglés?", None),
        ("Vuelve a la otra pestaña", None),
        ("Busco algo con vista al mar", None),
    ],
)
def test_the_page_for_what_they_asked_about(text: str, path: str | None) -> None:
    assert ssilva.asked_page(text, K) == path


@pytest.mark.parametrize(
    ("sentence", "typology"),
    [
        ("Este es el 2D | 2B, con terraza.", "2D | 2B"),
        ("El de dos dormitorios y dos baños es el más pedido.", "2D | 2B"),
        ("The three bedroom one is the largest.", "3D | 2B"),
        ("El de un dormitorio parte más bajo.", "1D | 1B"),
        ("Hay de dos y de tres dormitorios.", None),
        ("¿Te muestro el de dos dormitorios?", None),
    ],
)
def test_the_typology_a_sentence_is_about(sentence: str, typology: str | None) -> None:
    assert ssilva.typology_in(sentence, ("1D | 1B", "2D | 2B", "3D | 2B")) == typology


def test_a_dos_dormitorios_with_two_layouts_needs_the_baths() -> None:
    options = ("2D | 1B", "2D | 2B")
    assert ssilva.typology_in("Este de dos dormitorios es luminoso.", options) is None
    assert ssilva.typology_in("Dos dormitorios y un baño, muy eficiente.", options) == "2D | 1B"


@pytest.mark.parametrize(
    ("sentence", "key"),
    [
        ("Tiene piscina, gimnasio y quincho.", "amenidades"),
        ("The pool and the gym are on the top floor.", "amenidades"),
        ("Aquí ves las fotos del edificio.", "galería"),
        ("La sala de ventas abre de lunes a viernes.", "contacto"),
        ("Está en obra gruesa, según el estado del proyecto.", "estado"),
        ("Es un buen proyecto.", None),
        ("¿Quieres ver la piscina?", None),
    ],
)
def test_the_section_a_sentence_is_about(sentence: str, key: str | None) -> None:
    keys = ("galería", "tipologías", "amenidades", "estado", "contacto", "formulario")
    assert ssilva.section_in(sentence, keys) == key


def test_a_rut_is_checked_and_written_as_chile_writes_it() -> None:
    assert ssilva.rut_is_valid("12.345.678-5")
    assert ssilva.rut_is_valid("123456785")
    assert not ssilva.rut_is_valid("12.345.678-9")
    assert ssilva.rut_is_valid("11.111.111-1")
    assert ssilva.format_rut("123456785") == "12.345.678-5"


INGRESOS = [
    "Menos de $1.000.000",
    "Entre $1.000.000 a $1.200.000",
    "Entre $1.200.000 a $1.500.000",
    "Entre $1.500.000 a $1.800.000",
    "Entre $5.000.000 a $7.000.000",
    "Más de $7.000.000",
]


@pytest.mark.parametrize(
    ("said", "option"),
    [
        ("Entre $1.200.000 a $1.500.000", "Entre $1.200.000 a $1.500.000"),
        ("1500000", "Entre $1.500.000 a $1.800.000"),
        ("$1.100.000", "Entre $1.000.000 a $1.200.000"),
        ("un millón y medio", "Entre $1.500.000 a $1.800.000"),
        ("1,6 millones", "Entre $1.500.000 a $1.800.000"),
        ("800 mil", "Menos de $1.000.000"),
        ("8 millones", "Más de $7.000.000"),
        ("one and a half million", "Entre $1.500.000 a $1.800.000"),
        ("no sé", None),
    ],
)
def test_an_amount_lands_on_the_form_s_range(said: str, option: str | None) -> None:
    assert ssilva.option_for(said, INGRESOS) == option


def test_no_savings_is_its_own_option() -> None:
    pies = ["No tengo ahorro", "Menos de $2.000.000"]
    assert ssilva.option_for("no tengo nada ahorrado", pies) == "No tengo ahorro"
    assert ssilva.option_for("un millón", pies) == "Menos de $2.000.000"


def test_place_names_do_not_make_english_spanish() -> None:
    assert ssilva.language_of("Show me what you have in Las Condes, please.") == "en"
    assert ssilva.language_of("There are four in Viña del Mar.", sure=False) == "en"
    assert ssilva.language_of("Busco algo en Las Condes, por favor.") == "es"
