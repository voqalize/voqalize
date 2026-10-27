"""The colegioeverest extension's page logic, against saved copies of the real pages.

The adapter (``colegioeverest/extension/src/colegioeverest-actions.ts``) is
bundled as the extension ships it, with its catalogue of places, and run in
headless Chromium on copies of www.colegioeverest.cl saved by
``colegioeverest/fixtures/fetch.py`` (the page as rendered, scripts and styles
stripped), served from disk at the site's own address: no network. What is
checked is what the brain relies on — the places a page reports and rings by
key (the header's and footer's on every page), a move finished on the next
page after a full load, the sliders moved by their own arrows, the contact
form filled field by field with "Enviar" never pressed and the Cloudflare
check never touched, the visitor's own typing, and Contact Form 7's answers to
their press.

The pages have no scripts here, so slick does not move a slider and CF7 does
not answer a press: the test checks the arrow was clicked, and plays CF7's
events itself; on the live site the page's own jQuery and CF7 do both.

Needs Playwright and the extension's ``node_modules`` (for esbuild); skipped
without either, as in CI. Run it with:

    cd demos/colegioeverest/extension && pnpm install --ignore-workspace
    cd demos && uv run --with playwright pytest tests/test_colegioeverest_page.py -q
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

DEMO = Path(__file__).resolve().parents[1] / "colegioeverest"
EXTENSION = DEMO / "extension"
FIXTURES = DEMO / "fixtures"
ESBUILD = EXTENSION / "node_modules" / ".bin" / "esbuild"
SITE = "https://www.colegioeverest.cl"
ADM = "/bienvenidos-al-proceso-de-admision-del-colegio-everest/"
INFRA = "/nuestro-colegio/infraestructura/"

PAGES = {
    "/": "home",
    ADM: "admision",
    "/contacto/": "contacto",
    "/nuestro-modelo-educativo/ingles-intensivo/": "ingles",
    "/nuestro-modelo-educativo/ciclos/": "ciclos",
    "/nuestro-colegio/ambientes-seguros/": "ambientes",
    INFRA: "infraestructura",
    "/informacion-practica/": "informacion",
    "/nuestro-colegio/normativas/": "normativas",
    "/nuestro-colegio/historia/": "historia",
    "/hito-religioso-kinder/": "post",
}


@pytest.fixture(scope="module")
def bundle(tmp_path_factory: pytest.TempPathFactory) -> str:
    if not ESBUILD.exists() or shutil.which("node") is None:
        pytest.skip("run `pnpm install --ignore-workspace` in colegioeverest/extension first")
    out = tmp_path_factory.mktemp("colegioeverest") / "page.js"
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
        name = PAGES.get(url.path) if url.netloc == "www.colegioeverest.cl" else None
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
        "window.__events = []; window.__submits = 0;"
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
    page.wait_for_function("() => !!window.voqalizeColegioEverest")


def _listen(page: Any) -> None:
    page.evaluate(
        "() => window.voqalizeColegioEverest.start((e, p) => window.__events.push([e, p]))"
    )


def _run(page: Any, command: str, payload: dict[str, Any]) -> dict[str, Any]:
    return page.evaluate("([c, p]) => window.voqalizeColegioEverest.run(c, p)", [command, payload])


def _events(page: Any, name: str) -> list[Any]:
    return [p for e, p in page.evaluate("() => window.__events") if e == name]


def _context(page: Any) -> dict[str, Any]:
    return page.evaluate("() => window.voqalizeColegioEverest.context()")


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


def _value(page: Any, selector: str) -> str:
    return page.evaluate("(s) => document.querySelector(s).value", selector)


FORM = "#wpcf7-f1250-p1251-o1"
FULL = {
    "nombre": "Carolina Soto",
    "email": "caro.soto@example.com",
    "asunto": "Admisión 2027, Prekínder",
    "mensaje": "Hola, soy mamá de Sofía, de cuatro años. Nos interesa Prekínder 2027. "
    "Mi celular es +56 9 8765 4321.",
}

# ─── What a page reports ─────────────────────────────────────────────────────


def test_the_home_page_reports_its_places_and_the_header_and_footer(page: Any) -> None:
    _open(page, "/")
    ctx = _context(page)
    assert ctx["kind"] == "home" and ctx["form"] == "none"
    for key in (
        "hero",
        "atributos",
        "noticias",
        "noticias_carrusel",
        "destacados",
        "destacado_admision",
        "menu_principal",
        "menu_admision",
        "pie_contacto",
    ):
        assert key in ctx["anchors"], key
    # The footer's map is an iframe, which the saved copies leave out: its box
    # has nothing in it here, so it is not reported (on the live site it is).
    # The adapter's own handles (the slider's arrows) are not offered.
    assert "noticias_siguiente" not in ctx["anchors"]


@pytest.mark.parametrize(
    ("path", "kind", "keys"),
    [
        (
            ADM,
            "admission",
            [
                "fechas",
                "fecha_prekinder",
                "fecha_playgroup",
                "fecha_kinder_iv_medio",
                "fecha_bambolino",
                "pasos",
                "paso_2_prepara",
                "paso_4_visita",
                "paso_6_admission_day",
                "vacantes",
                "valores",
                "encargada_admision",
            ],
        ),
        (
            "/nuestro-modelo-educativo/ingles-intensivo/",
            "education",
            ["intro", "ruta", "certificaciones"],
        ),
        ("/nuestro-modelo-educativo/ciclos/", "education", ["ciclo_i", "ciclo_ii", "ciclo_iii"]),
        ("/nuestro-colegio/ambientes-seguros/", "safeguarding", ["etapa_deteccion", "ceprome"]),
        (INFRA, "school", ["galeria", "galeria_miniaturas"]),
        ("/informacion-practica/", "info", ["casino", "uniforme", "enfermeria", "bus_car"]),
        ("/nuestro-colegio/normativas/", "documents", ["pdf_pei", "pdf_rice", "pdf_nee"]),
        ("/nuestro-colegio/historia/", "school", ["fundacion_1995", "hoy"]),
        ("/hito-religioso-kinder/", "post", ["titulo", "contenido", "pie_contacto"]),
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


def test_a_card_is_rung_and_a_place_that_is_not_there_names_those_that_are(page: Any) -> None:
    _open(page, ADM)
    assert _run(page, "show_section", {"anchor": "fecha_prekinder", "text": None}) == {"ok": True}
    assert _ring_around(page, ".gb-container-db32d6d8")
    out = _run(page, "show_section", {"anchor": "nivel_inventado", "text": None})
    assert out["ok"] is False
    assert "fecha_prekinder" in out["error"] and "vacantes" in out["error"]


def test_a_key_of_another_page_is_not_looked_up_here(page: Any) -> None:
    """GenerateBlocks' classes repeat across pages: a key is only its own page's."""
    _open(page, "/")
    out = _run(page, "show_section", {"anchor": "fecha_prekinder", "text": None})
    assert out["ok"] is False


def test_words_on_a_page_are_rung_by_their_text(page: Any) -> None:
    _open(page, "/nuestro-colegio/historia/")
    assert _run(page, "show_section", {"anchor": None, "text": "1995"})["ok"]
    assert _ringed(page)


def test_a_place_is_scrolled_to_just_under_the_top(page: Any) -> None:
    """The header is not fixed: a tall place sits 20 px under the window's top."""
    _open(page, ADM)
    assert _run(page, "show_section", {"anchor": "pasos_grilla", "text": None})["ok"]
    top = page.evaluate(
        "() => document.querySelector('.gb-container-716a5e69').getBoundingClientRect().top"
    )
    assert top >= 0 and top < 400, top


# ─── A move across a full page load ──────────────────────────────────────────


def test_a_place_on_another_page_is_rung_after_the_load(page: Any) -> None:
    _open(page, "/")
    with page.expect_navigation():
        _run(page, "navigate", {"path": ADM, "anchor": "fecha_prekinder", "text": None})
    page.wait_for_function("() => !!window.voqalizeColegioEverest")
    page.wait_for_function(
        "() => !!document.querySelector('[data-voqalize=highlight]')", timeout=15000
    )
    assert page.url == f"{SITE}{ADM}"
    assert _ring_around(page, ".gb-container-db32d6d8")


# ─── The sliders ─────────────────────────────────────────────────────────────


def _clicks(page: Any, selector: str) -> None:
    page.evaluate(
        "(s) => { window.__clicks = 0; document.querySelector(s).addEventListener('click', () => window.__clicks++); }",
        selector,
    )


def test_the_news_carousel_moves_by_its_own_arrow(page: Any) -> None:
    _open(page, "/")
    _clicks(page, ".slider-noticias .slick-next")
    out = _run(page, "slide", {"slider": "noticias", "direction": "next"})
    assert out["ok"], out
    assert page.evaluate("() => window.__clicks") == 1
    assert out["detail"].startswith("moved the news carousel on")
    assert _ring_around(page, ".slider-noticias")


def test_the_gallery_moves_back_by_its_own_arrow(page: Any) -> None:
    _open(page, INFRA)
    _clicks(page, ".slider-for .slick-prev")
    out = _run(page, "slide", {"slider": "galeria", "direction": "prev"})
    assert out["ok"], out
    assert page.evaluate("() => window.__clicks") == 1
    assert "moved the photo gallery back" in out["detail"]


def test_a_slide_off_its_page_opens_the_page_and_slides_there(page: Any) -> None:
    _open(page, "/contacto/")
    with page.expect_navigation():
        _run(page, "slide", {"slider": "galeria", "direction": "next"})
    page.wait_for_function("() => !!window.voqalizeColegioEverest")
    page.wait_for_function(
        "() => !!document.querySelector('[data-voqalize=highlight]')", timeout=15000
    )
    assert page.url == f"{SITE}{INFRA}"
    _listen(page)
    (done,) = _events(page, "command_done")
    assert done["command"] == "slide" and "photo gallery" in done["detail"]


# ─── The contact form ────────────────────────────────────────────────────────


def test_the_contact_form_is_filled_and_never_sent(page: Any) -> None:
    _open(page, "/contacto/")
    _listen(page)
    assert _context(page)["form"] == "contact"
    page.evaluate(
        "() => { window.__presses = 0; document.querySelector('.wpcf7-submit')"
        ".addEventListener('click', () => window.__presses++); }"
    )
    out = _run(page, "fill_contact_form", FULL)
    assert out["ok"], out
    assert "they press it themselves" in out["detail"]
    assert _value(page, f'{FORM} input[name="your-name"]') == "Carolina Soto"
    assert _value(page, f'{FORM} input[name="your-email"]') == "caro.soto@example.com"
    assert _value(page, f'{FORM} input[name="your-subject"]') == "Admisión 2027, Prekínder"
    assert "+56 9 8765 4321" in _value(page, f'{FORM} textarea[name="your-message"]')
    (state,) = _events(page, "form_state")
    assert state["ready"] is True and state["missing"] == [] and state["by"] == "javier"
    assert state["form"] == "contact" and state["values"]["nombre"] == "Carolina Soto"
    # "Enviar" and the check above it are rung for them; nothing was pressed or sent.
    assert _ringed(page)
    page.wait_for_timeout(500)
    assert page.evaluate("() => window.__submits") == 0
    assert page.evaluate("() => window.__presses") == 0


def test_a_partial_fill_says_what_is_still_empty_and_what_the_site_would_refuse(
    page: Any,
) -> None:
    _open(page, "/contacto/")
    _listen(page)
    out = _run(page, "fill_contact_form", {"email": "caro-at-example"})
    assert out["ok"]
    assert "still empty: nombre" in out["detail"]
    (state,) = _events(page, "form_state")
    assert state["invalid"] == ["email"] and state["ready"] is False


def test_a_fill_from_another_page_opens_the_contact_page_and_fills_there(page: Any) -> None:
    _open(page, ADM)
    with page.expect_navigation():
        _run(page, "fill_contact_form", {"nombre": "Carolina", "asunto": "Visita"})
    page.wait_for_function("() => !!window.voqalizeColegioEverest")
    page.wait_for_function(
        """() => document.querySelector('#wpcf7-f1250-p1251-o1 input[name="your-name"]')?.value === 'Carolina'""",
        timeout=15000,
    )
    _listen(page)
    (done,) = _events(page, "command_done")
    assert done["command"] == "fill_contact_form" and "filled nombre, asunto" in done["detail"]
    assert _events(page, "form_state")[0]["filled"] == ["nombre", "asunto"]
    assert page.evaluate("() => window.__submits") == 0


def test_their_own_typing_is_followed(page: Any) -> None:
    _open(page, "/contacto/")
    _listen(page)
    page.fill(f'{FORM} input[name="your-subject"]', "Consulta")
    page.wait_for_timeout(1300)
    state = _events(page, "form_state")[-1]
    assert state["by"] == "visitor" and state["values"]["asunto"] == "Consulta"


@pytest.mark.parametrize(
    ("event", "outcome"),
    [
        ("wpcf7mailsent", "sent"),
        ("wpcf7invalid", "invalid"),
        ("wpcf7spam", "spam"),
        ("wpcf7mailfailed", "failed"),
    ],
)
def test_cf7s_answer_to_their_press_is_reported(page: Any, event: str, outcome: str) -> None:
    _open(page, "/contacto/")
    _listen(page)
    assert _run(page, "fill_contact_form", FULL)["ok"]
    # CF7's own answer, as it gives it: its line in the form, then its event.
    page.evaluate(
        """([ev]) => {
          const wrap = document.querySelector('#wpcf7-f1250-p1251-o1');
          wrap.querySelector('.wpcf7-response-output').textContent = 'Respuesta del sitio.';
          if (ev === 'wpcf7invalid') wrap.querySelector('input[name="your-email"]').classList.add('wpcf7-not-valid');
          wrap.dispatchEvent(new CustomEvent(ev, { bubbles: true }));
        }""",
        [event],
    )
    page.wait_for_function("() => window.__events.some(([e]) => e === 'form_result')", timeout=5000)
    (result,) = _events(page, "form_result")
    assert result["form"] == "contact" and result["outcome"] == outcome
    assert result["message"] == "Respuesta del sitio."
    assert result["fields"] == (["email"] if outcome == "invalid" else [])


def test_another_cf7_form_is_never_followed(page: Any) -> None:
    """The complaints and jobs forms are CF7 too: their answers are not ours."""
    _open(page, "/nuestro-colegio/ambientes-seguros/")
    _listen(page)
    page.evaluate(
        "() => document.body.dispatchEvent(new CustomEvent('wpcf7mailsent', { bubbles: true }))"
    )
    page.wait_for_timeout(400)
    assert _events(page, "form_result") == []
    out = _run(page, "fill_contact_form", {"nombre": "X"})
    # Not this page's form: the contact page opens instead (nothing typed here).
    assert out["ok"]


# ─── What it can never do ────────────────────────────────────────────────────


def test_the_adapter_has_no_way_to_send_a_form() -> None:
    """No `submit()`, no `requestSubmit()`, and no click on a form's button
    anywhere in the extension's source: "Enviar" is the visitor's."""
    for source in (EXTENSION / "src").glob("*.ts"):
        text = source.read_text(encoding="utf-8")
        assert not re.search(r"\.(?:request)?[sS]ubmit\s*\(", text), source.name
        assert not re.search(
            r"(?:wpcf7-submit|BUTTON|button|turnstile|CAPTCHA)[^;\n]*\.click\(\)", text
        ), source.name


def test_paths_are_the_sites_own_shape(page: Any) -> None:
    _open(page, "/")
    got = page.evaluate(
        "() => ['/Contacto', '//contacto//', '/', ''].map(window.__voqalizeTest.canonical)"
    )
    assert got == ["/contacto/", "/contacto/", "/", "/"]
