"""The figurella extension's page logic, against saved copies of the real pages.

The adapter (``figurella/extension/src/figurella-actions.ts``) is bundled as the
extension ships it, with its catalogue of places, and run in headless Chromium
on copies of figurella.cl saved by ``figurella/fixtures/fetch.py`` (the page as
rendered, scripts and styles stripped), served from disk at the site's own
address: no network. What is checked is what the brain relies on — the places a
page reports and rings by key, an FAQ question opened by its key or its words
(one open at a time), a move finished on the next page after a full load, the
testimonials and the agreements, the booking form filled field by field with
the privacy box untouched and nothing submitted, the branch a card's "Pedir
hora gratis" carries to the form, the franchise form, and the site's answer to
her own press.

The pages have no scripts here, so an FAQ question is opened by the adapter's
own fallback, and the site's answer to a press is played by the test; on the
live site Essential Addons and Elementor Pro do both.

Needs Playwright and the extension's ``node_modules`` (for esbuild); skipped
without either, as in CI. Run it with:

    cd demos/figurella/extension && pnpm install --ignore-workspace
    cd demos && uv run --with playwright pytest tests/test_figurella_page.py -q
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

DEMO = Path(__file__).resolve().parents[1] / "figurella"
EXTENSION = DEMO / "extension"
FIXTURES = DEMO / "fixtures"
ESBUILD = EXTENSION / "node_modules" / ".bin" / "esbuild"
SITE = "https://figurella.cl"

PAGES = {
    "/": "home",
    "/metodo-figurella/": "metodo",
    "/planes/": "planes",
    "/historias-de-exito/": "historias",
    "/convenios/": "convenios",
    "/franquicias/": "franquicias",
    "/preguntas-frecuentes/": "faq",
    "/capsula-termica-y-sus-beneficios/": "post",
}

#: Elementor's bottom bar is in the saved pages as the site renders it; with
#: no scripts its ✕ does nothing, so this gives it Elementor's one behaviour
#: the test needs: the ✕ (drawn by its stylesheet's icon) hides the bar.
_BAR = """
document.addEventListener('DOMContentLoaded', () => {
  const bar = document.getElementById('elementor-popup-modal-480');
  const x = bar?.querySelector('.dialog-close-button');
  if (!x) return;
  Object.assign(x.style, { display: 'block', width: '20px', height: '20px' });
  x.addEventListener('click', () => { bar.style.display = 'none'; });
});
"""


@pytest.fixture(scope="module")
def bundle(tmp_path_factory: pytest.TempPathFactory) -> str:
    if not ESBUILD.exists() or shutil.which("node") is None:
        pytest.skip("run `pnpm install --ignore-workspace` in figurella/extension first")
    out = tmp_path_factory.mktemp("figurella") / "page.js"
    subprocess.run(
        [
            str(ESBUILD),
            "test/entry.ts",
            "--bundle",
            "--format=iife",
            "--target=chrome120",
            f"--outfile={out}",
        ],
        cwd=EXTENSION,
        check=True,
        capture_output=True,
    )
    return out.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def browser() -> Iterator[Any]:
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch(headless=True)
        except Exception as exc:  # no browser installed
            pytest.skip(f"no headless Chromium: {exc}")
        yield b
        b.close()


@pytest.fixture
def page(browser: Any, bundle: str) -> Iterator[Any]:
    context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="es-CL")

    def serve(route: Any) -> None:
        url = urlsplit(route.request.url)
        name = PAGES.get(url.path) if url.netloc == "figurella.cl" else None
        if name is None or route.request.resource_type != "document":
            route.abort()
            return
        route.fulfill(
            status=200,
            content_type="text/html; charset=utf-8",
            body=(FIXTURES / f"{name}.html").read_text(encoding="utf-8"),
        )

    context.route("**/*", serve)
    context.add_init_script(
        _BAR
        + "window.__events = []; window.__submits = 0;"
        + "addEventListener('submit', () => { window.__submits++; }, true);"
        # The top frame only, as the extension's content scripts run: an
        # about:blank frame of the page shares its storage, and an adapter in it
        # would take the move the last page left.
        + "if (window.top === window) document.addEventListener('DOMContentLoaded', () => {"
        + bundle
        + "});"
    )
    pg = context.new_page()
    yield pg
    context.close()


def _open(page: Any, path: str) -> None:
    page.goto(SITE + path)
    page.wait_for_function("() => !!window.voqalizeFigurella")


def _listen(page: Any) -> None:
    page.evaluate("() => window.voqalizeFigurella.start((e, p) => window.__events.push([e, p]))")


def _run(page: Any, command: str, payload: dict[str, Any]) -> dict[str, Any]:
    return page.evaluate("([c, p]) => window.voqalizeFigurella.run(c, p)", [command, payload])


def _events(page: Any, name: str) -> list[Any]:
    return [p for e, p in page.evaluate("() => window.__events") if e == name]


def _context(page: Any) -> dict[str, Any]:
    return page.evaluate("() => window.voqalizeFigurella.context()")


def _ringed(page: Any) -> bool:
    return page.evaluate("() => !!document.querySelector('[data-voqalize=highlight]')")


def _ring_around(page: Any, selector: str) -> bool:
    """The ring is drawn around ``selector``'s element (within its margin)."""
    return page.evaluate(
        """(sel) => { const ring = document.querySelector('[data-voqalize=highlight]');
        const el = document.querySelector(sel); if (!ring || !el) return false;
        const a = ring.getBoundingClientRect(), b = el.getBoundingClientRect();
        return a.left <= b.left && a.top <= b.top + 1 && a.right >= b.right && a.bottom >= b.bottom - 1; }""",
        selector,
    )


def _open_faqs(page: Any) -> list[str]:
    return page.evaluate(
        "() => [...document.querySelectorAll('.eael-accordion-header.active')]"
        ".filter((h) => h.nextElementSibling && h.nextElementSibling.getBoundingClientRect().height > 0)"
        ".map((h) => h.id)"
    )


def _value(page: Any, selector: str) -> str:
    return page.evaluate("(s) => document.querySelector(s).value", selector)


FULL = {
    "nombre": "Ana Pérez",
    "telefono": "+56 9 8765 4321",
    "email": "ana.perez@example.com",
    "comuna": "Ñuñoa",
    "sucursal": "Costanera",
    "mensaje": "Quiero bajar de peso. Me interesa el Plan Intensivo.",
}

# ─── What a page reports ─────────────────────────────────────────────────────


def test_the_home_page_reports_its_places_and_its_form(page: Any) -> None:
    _open(page, "/")
    ctx = _context(page)
    assert ctx["kind"] == "home" and ctx["form"] == "booking"
    for key in (
        "intro",
        "counters",
        "metodo",
        "plan_novias",
        "garantia",
        "sucursales",
        "sucursal_vitacura",
        "sucursal_las_perdices",
        "contacto",
    ):
        assert key in ctx["anchors"], key
    # The adapter's own handles are not offered.
    assert not [a for a in ctx["anchors"] if a.endswith("_pedir_hora") or a.startswith("field_")]


@pytest.mark.parametrize(
    ("path", "kind", "keys"),
    [
        ("/metodo-figurella/", "method", ["paso_1", "paso_2", "paso_3", "paso_4"]),
        (
            "/planes/",
            "plans",
            [
                "plan_curvas_perfectas",
                "plan_novias",
                "plan_mama_reciente",
                "plan_rejuvenece",
                "plan_intensivo",
            ],
        ),
        (
            "/historias-de-exito/",
            "stories",
            ["testimonio_pamela", "testimonio_cuca", "testimonio_maria_jesus"],
        ),
        ("/convenios/", "convenios", ["convenio_banmedica", "convenio_colmena", "convenio_bice"]),
        ("/franquicias/", "franchise", ["beneficios", "socios"]),
        ("/capsula-termica-y-sus-beneficios/", "post", ["titulo", "contenido", "contacto"]),
    ],
)
def test_each_page_reports_and_rings_its_places(
    page: Any, path: str, kind: str, keys: list[str]
) -> None:
    _open(page, path)
    ctx = _context(page)
    assert ctx["kind"] == kind
    for key in keys:
        assert key in ctx["anchors"], key
        assert _run(page, "show_section", {"anchor": key, "text": None}) == {"ok": True}, key
        assert _ringed(page), key


def test_the_franchise_page_has_its_own_form_and_no_booking_form(page: Any) -> None:
    _open(page, "/franquicias/")
    ctx = _context(page)
    assert ctx["form"] == "franchise"
    assert "contacto" not in ctx["anchors"]


def test_a_branch_card_is_rung_and_a_place_that_is_not_there_names_those_that_are(
    page: Any,
) -> None:
    _open(page, "/")
    assert _run(page, "show_section", {"anchor": "sucursal_colon", "text": None}) == {"ok": True}
    assert _ring_around(page, ".elementor-element-a6eefa5")
    out = _run(page, "show_section", {"anchor": "plan_inventado", "text": None})
    assert out["ok"] is False
    assert "sucursal_colon" in out["error"] and "plan_novias" in out["error"]


def test_words_on_a_post_are_rung_by_their_text(page: Any) -> None:
    _open(page, "/capsula-termica-y-sus-beneficios/")
    assert _run(page, "show_section", {"anchor": None, "text": "37"})["ok"]
    assert _ringed(page)


def test_the_bottom_bar_is_closed_as_its_x_would(page: Any) -> None:
    _open(page, "/planes/")
    page.wait_for_function(
        "() => document.getElementById('elementor-popup-modal-480')?.style.display === 'none'",
        timeout=5000,
    )
    # Its ✕ is a link to "#": closing it never jumps the page.
    assert page.url == f"{SITE}/planes/"


# ─── The FAQ ─────────────────────────────────────────────────────────────────


def test_a_question_opens_by_its_key_and_only_one_is_open(page: Any) -> None:
    _open(page, "/preguntas-frecuentes/")
    ctx = _context(page)
    assert ctx["kind"] == "faq"
    assert set(ctx["faqs"]) >= {"faq_abdomen", "faq_precio", "faq_frecuencia"}
    assert _run(page, "open_faq", {"question": "faq_caderas"}) == {"ok": True}
    assert "cmo-puedo-perder-peso-en-mis-caderas" in _open_faqs(page)
    assert "cmo-puedo-obtener-un-abdomen-plano" not in _open_faqs(page)
    assert _ringed(page)


def test_a_question_opens_by_its_words_whatever_the_accents(page: Any) -> None:
    _open(page, "/preguntas-frecuentes/")
    assert _run(page, "open_faq", {"question": "cuanto cuesta figurella"}) == {"ok": True}
    assert "cunto-cuesta-figurella" in _open_faqs(page)


def test_a_question_that_is_not_there_names_the_ones_that_are(page: Any) -> None:
    _open(page, "/preguntas-frecuentes/")
    out = _run(page, "open_faq", {"question": "¿Tienen estacionamiento?"})
    assert out["ok"] is False and "faq_precio" in out["error"]


# ─── A move across a full page load ──────────────────────────────────────────


def test_a_question_asked_on_another_page_opens_after_the_load(page: Any) -> None:
    _open(page, "/")
    with page.expect_navigation():
        _run(page, "open_faq", {"question": "faq_precio"})
    page.wait_for_function("() => !!window.voqalizeFigurella")
    page.wait_for_function(
        "() => document.querySelector('#cunto-cuesta-figurella')?.classList.contains('active')",
        timeout=15000,
    )
    assert page.url == f"{SITE}/preguntas-frecuentes/"


def test_a_place_on_another_page_is_rung_after_the_load(page: Any) -> None:
    _open(page, "/")
    with page.expect_navigation():
        _run(
            page,
            "navigate",
            {"path": "/planes/", "anchor": "plan_novias", "text": None, "faq": None},
        )
    page.wait_for_function("() => !!window.voqalizeFigurella")
    page.wait_for_function(
        "() => !!document.querySelector('[data-voqalize=highlight]')", timeout=15000
    )
    assert page.url == f"{SITE}/planes/"
    assert _ring_around(page, ".elementor-element-341a556")


# ─── The booking form ────────────────────────────────────────────────────────


def test_the_booking_form_is_filled_and_never_sent(page: Any) -> None:
    _open(page, "/")
    _listen(page)
    out = _run(page, "fill_booking_form", FULL)
    assert out["ok"], out
    assert "she presses it herself" in out["detail"]
    assert _value(page, "#form-field-first_name") == "Ana Pérez"
    # Digits and the leading +: what the site's server takes.
    assert _value(page, "#form-field-phone") == "+56987654321"
    assert _value(page, "#form-field-email") == "ana.perez@example.com"
    assert _value(page, "#form-field-sucursales") == "costanera@figurella.cl"
    assert _value(page, "#form-field-message").startswith("Quiero bajar de peso.")
    # The privacy box is hers: still as the site ticked it.
    assert page.evaluate("() => document.querySelector('#form-field-field_826580a').checked")
    (state,) = _events(page, "form_state")
    assert state["ready"] is True and state["missing"] == [] and state["by"] == "javier"
    assert state["values"]["sucursal"] == "Costanera" and state["consent"] is True
    # The button is rung for her; nothing was submitted.
    assert _ringed(page)
    page.wait_for_timeout(500)
    assert page.evaluate("() => window.__submits") == 0


def test_a_partial_fill_says_what_is_still_empty_and_what_the_site_would_refuse(
    page: Any,
) -> None:
    _open(page, "/planes/")
    _listen(page)
    out = _run(page, "fill_booking_form", {"nombre": "Ana", "email": "ana-at-example"})
    assert out["ok"]
    assert "still empty: telefono, comuna, sucursal, mensaje" in out["detail"]
    (state,) = _events(page, "form_state")
    assert state["invalid"] == ["email"] and state["ready"] is False


def test_a_branch_not_in_the_list_is_said(page: Any) -> None:
    _open(page, "/")
    out = _run(page, "fill_booking_form", {"sucursal": "Montemar"})
    assert out["ok"] and 'no sucursal "Montemar"' in out["detail"]
    assert _value(page, "#form-field-sucursales") == ""


def test_a_fill_from_the_franchise_page_opens_the_home_page_and_fills_there(page: Any) -> None:
    _open(page, "/franquicias/")
    with page.expect_navigation():
        _run(page, "fill_booking_form", {"nombre": "Ana", "comuna": "Vitacura"})
    page.wait_for_function("() => !!window.voqalizeFigurella")
    page.wait_for_function(
        "() => document.querySelector('#form-field-first_name')?.value === 'Ana'", timeout=15000
    )
    _listen(page)
    (done,) = _events(page, "command_done")
    assert done["command"] == "fill_booking_form" and "filled nombre, comuna" in done["detail"]
    assert _events(page, "form_state")[0]["filled"] == ["nombre", "comuna"]
    assert page.evaluate("() => window.__submits") == 0


def test_a_cards_pedir_hora_carries_its_branch_to_the_form(page: Any) -> None:
    _open(page, "/")
    _listen(page)
    page.click(".elementor-element-842e43b a, .elementor-element-842e43b")
    page.wait_for_function(
        "() => document.querySelector('#form-field-sucursales').value === 'vitacura@figurella.cl'",
        timeout=3000,
    )
    state = _events(page, "form_state")[-1]
    assert state["by"] == "visitor" and state["values"]["sucursal"] == "Vitacura"


def test_her_own_typing_is_followed(page: Any) -> None:
    _open(page, "/")
    _listen(page)
    page.fill("#form-field-comuna", "La Reina")
    page.wait_for_timeout(1300)
    state = _events(page, "form_state")[-1]
    assert state["by"] == "visitor" and state["values"]["comuna"] == "La Reina"


def test_her_press_and_the_sites_answer_are_reported(page: Any) -> None:
    _open(page, "/")
    _listen(page)
    assert _run(page, "fill_booking_form", FULL)["ok"]
    # The site's handler, as Elementor Pro's: it takes the press, sends the
    # form over AJAX and writes its answer into the form.
    page.evaluate(
        """() => document.querySelector('#form_agendamiento_figurella').addEventListener('submit', (e) => {
          e.preventDefault();
          setTimeout(() => e.target.insertAdjacentHTML('beforeend',
            '<div class="elementor-message elementor-message-success" role="alert">El formulario fue enviado.</div>'), 300);
        })"""
    )
    page.click("#btn-send")
    page.wait_for_function("() => window.__events.some(([e]) => e === 'form_result')", timeout=5000)
    (result,) = _events(page, "form_result")
    assert result == {
        "form": "booking",
        "outcome": "sent",
        "message": "El formulario fue enviado.",
        "fields": [],
    }


def test_the_sites_refusal_names_the_field(page: Any) -> None:
    _open(page, "/")
    _listen(page)
    assert _run(page, "fill_booking_form", FULL)["ok"]
    page.evaluate(
        """() => document.querySelector('#form_agendamiento_figurella').addEventListener('submit', (e) => {
          e.preventDefault();
          const f = e.target;
          setTimeout(() => {
            f.querySelector('#form-field-phone').closest('.elementor-field-group').classList.add('elementor-error');
            f.insertAdjacentHTML('beforeend', '<div class="elementor-message elementor-message-danger">Hay un error.</div>');
          }, 300);
        })"""
    )
    page.click("#btn-send")
    page.wait_for_function("() => window.__events.some(([e]) => e === 'form_result')", timeout=5000)
    (result,) = _events(page, "form_result")
    assert result["outcome"] == "error" and result["fields"] == ["telefono"]


def test_a_press_with_a_field_empty_is_stopped_and_said(page: Any) -> None:
    _open(page, "/")
    _listen(page)
    page.click("#btn-send")
    page.wait_for_function("() => window.__events.some(([e]) => e === 'form_result')", timeout=5000)
    result = _events(page, "form_result")[0]
    assert result["outcome"] == "error" and "nombre" in result["fields"]
    assert page.evaluate("() => window.__submits") == 0


# ─── The franchise form ──────────────────────────────────────────────────────


def test_the_franchise_form_is_filled_and_never_sent(page: Any) -> None:
    _open(page, "/franquicias/")
    _listen(page)
    out = _run(
        page,
        "fill_franchise_form",
        {"nombre": "Carla Soto", "telefono": "987654321", "email": "carla@example.com"},
    )
    assert out["ok"] and "she presses it herself" in out["detail"]
    form = ".elementor-element-5a9d90a7 form"
    assert _value(page, f"{form} #form-field-nombre") == "Carla Soto"
    assert _value(page, f"{form} #form-field-telefono") == "987654321"
    (state,) = _events(page, "form_state")
    assert state["form"] == "franchise" and state["ready"] is True
    assert page.evaluate("() => window.__submits") == 0


# ─── What it can never do ────────────────────────────────────────────────────


def test_the_adapter_has_no_way_to_send_a_form() -> None:
    """No `submit()`, no `requestSubmit()`, and no click on a form's button
    anywhere in the extension's source: the button is hers."""
    for source in (EXTENSION / "src").glob("*.ts"):
        text = source.read_text(encoding="utf-8")
        assert not re.search(r"\.(?:request)?[sS]ubmit\s*\(", text), source.name
        assert not re.search(r"(?:btn-send|BUTTON|button)[^;\n]*\.click\(\)", text), source.name


def test_a_phone_keeps_its_digits_and_its_plus_and_nothing_else(page: Any) -> None:
    _open(page, "/")
    got = page.evaluate(
        "() => ['+56 9 8765-4321', '9 8765 4321', '(2) 3358.5099'].map(window.__voqalizeTest.phoneValue)"
    )
    assert got == ["+56987654321", "987654321", "233585099"]
