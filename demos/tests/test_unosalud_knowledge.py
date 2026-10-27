"""Javier's knowledge of Uno Salud Dental, against the saved pages it was built from.

The extension bundles ``knowledge/L3/anchors.json`` and finds each place by its
selector, so every selector on a page we have a saved copy of must find exactly
one element there — the same check ``knowledge/build.py`` makes when it writes
the catalogue. The clinic table is what ``find_clinic`` and the booking picks
stand on, and the motivos are the booking's own.

Run: ``cd demos && uv run pytest tests/test_unosalud_knowledge.py``
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType

from voqalize_demos.discovery import discover

discover()

from voqalize_demos._loaded.unosalud import dom  # noqa: E402
from voqalize_demos._loaded.unosalud import knowledge as kb  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1] / "unosalud" / "backend"
FIXTURES = BACKEND.parent / "fixtures"
L3 = BACKEND / "knowledge" / "L3"


def _build() -> ModuleType:
    """``knowledge/build.py``, a script beside the ``knowledge`` module, loaded by path."""
    spec = importlib.util.spec_from_file_location(
        "unosalud_build", BACKEND / "knowledge" / "build.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Its dataclasses look their module up while they are made.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_every_anchor_on_a_saved_page_matches_exactly_one_element() -> None:
    build = _build()
    anchors = build.load_anchors()
    assert len(anchors) > 300
    assert build.check(anchors) == []
    checked = sum(a.verified for a in anchors)
    assert checked > 300, checked


def test_the_catalogue_has_the_places_the_extension_is_told_about() -> None:
    raw = json.loads((L3 / "anchors.json").read_text(encoding="utf-8"))
    for key in (
        "home_especialidades",
        "home_clinicas",
        "especialidades_card_ortodoncia",
        "ortodoncia_precios",
        "ortodoncia_tab_metalicos",
        "ortodoncia_precios_invisible",
        "implantes_precios",
        "clinicas_buscador",
        "clinicas_moneda",
        "clinica_horario",
        "clinica_mapa",
        "promo_ortodoncia_oct",
        "convenios_isapres",
        "convenio_fonasa",
        "beneficios_card_pad",
        "planes_precios",
        "faq_planes_5",
        "urgencias_horario",
        "porque_medios_pago",
        "porque_pago_cheques",
        "faq_urgencias",
        "faq_ortodoncia_3",
        "empresas_formulario",
        "tellamamos_formulario",
        "nosotros_mision",
        "contacto_ayuda",
    ):
        assert key in raw, key
        entry = raw[key]
        assert entry["path"].startswith("/") and entry["path"].endswith("/"), key
        assert entry["selector"] or entry["text"], key
        assert entry["label"]["es"] and entry["label"]["en"], key
    assert raw["faq_urgencias"]["faq"] == "14331"
    assert raw["clinica_horario"]["path"] == kb.CLINIC_PAGE
    keys = [k for k in raw if not k.startswith("_")]
    assert all(re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)+", k) for k in keys), keys


def test_the_faq_anchors_open_the_question_they_name() -> None:
    root = dom.parse_file(FIXTURES / "preguntas-frecuentes.html")
    for a in kb.KNOWLEDGE.anchors.values():
        if a.path != "/preguntas-frecuentes/" or not a.faq:
            continue
        (button,) = dom.select(root, f"#heading-faq-{a.faq}")
        assert a.es[:30] in button.text(), (a.key, button.text())


def test_every_clinic_has_a_place_an_address_and_a_comuna() -> None:
    clinics = kb.KNOWLEDGE.clinics
    assert len(clinics) == 103
    assert len({c.key for c in clinics}) == 103
    assert len({c.id for c in clinics}) == 103
    for c in clinics:
        assert c.comuna and c.region and c.address, c
        assert c.path.startswith("/clinicas/") and c.path.endswith("/"), c
        assert c.maps_url.startswith("https://www.google.com/maps/"), c
        assert f"clinicas_{c.key}" in kb.KNOWLEDGE.anchors, c
    joined = [c for c in clinics if c.booking_id]
    assert len(joined) >= 95, len(joined)
    moneda = kb.KNOWLEDGE.clinic("moneda")
    assert moneda is not None and moneda.booking_name == "MONEDA (PASEO AHUMADA)"
    assert "8:30 a 20:00" in moneda.hours


def test_the_booking_ids_are_the_bookings_own() -> None:
    html = (FIXTURES / "cta-agenda-tu-hora.html").read_text(encoding="utf-8")
    m = re.search(r'<script[^>]*id="jsonSucursales"[^>]*>(.*?)</script>', html, re.S)
    assert m is not None
    tree = json.loads(m.group(1))
    ids = {
        str(s["id"])
        for region in tree.values()
        for comuna in region["comunas"].values()
        for s in comuna["sucursales"]
    }
    assert len(ids) == 103
    used = [c.booking_id for c in kb.KNOWLEDGE.clinics if c.booking_id]
    assert set(used) <= ids and len(used) == len(set(used))


def test_the_motivos_are_the_bookings_fourteen_to_twenty_three() -> None:
    assert [m.id for m in kb.KNOWLEDGE.motivos] == list(range(14, 24))
    root = dom.parse_file(FIXTURES / "cta-agenda-tu-hora.html")
    options = {o.attrs.get("value", ""): o.text() for o in dom.select(root, "select#motivo option")}
    for m in kb.KNOWLEDGE.motivos:
        assert str(m.id) in options, m
        assert options[str(m.id)].split(" (")[0] in m.name, (m, options[str(m.id)])


def test_a_clinic_is_found_by_comuna_landmark_or_name() -> None:
    k = kb.KNOWLEDGE
    assert "Manuel Montt" in [c.name for c in k.find_clinics("Providencia")]
    assert k.find_clinics("metro Manuel Montt")[0].name == "Manuel Montt"
    assert all(c.comuna == "Temuco" for c in k.find_clinics("Temuco"))
    assert k.find_clinics("Moneda")[0].key == "moneda"
    assert k.find_clinics("xyzzy") == []


def test_the_knowledge_names_every_topic_and_the_l1_carries_the_basics() -> None:
    k = kb.KNOWLEDGE
    for topic in (
        "agendar",
        "ortodoncia",
        "implantes",
        "promociones",
        "convenios",
        "pagos",
        "planes",
        "urgencias",
        "preguntas_frecuentes",
        "mapa_del_sitio",
    ):
        assert topic in k.topics, topic
        assert k.topics[topic].text.splitlines()[2].startswith("Sources:"), topic
    for fact in ("600 707 1010", "$90.210", "$361.900", "No soy un robot", "Confirmar cita"):
        assert fact in k.l1, fact


def test_promotions_carry_their_end_date_and_known_codes() -> None:
    k = kb.KNOWLEDGE
    assert len(k.promotions) == 10
    ortho = k.promotion("ortodoncia_oct")
    assert ortho is not None and ortho.promo == "ortodonciaoctnov26"
    assert ortho.valid_until == "2026-10-31" and "$299.900" in ortho.summary
    for p in k.promotions:
        assert f"promo_{p.key}" in k.anchors, p
