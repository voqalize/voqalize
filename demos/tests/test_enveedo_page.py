"""The enveedo extension's page logic, against saved copies of the real pages.

The adapter (``enveedo/extension/src/enveedo-actions.ts``) is bundled as the
extension ships it, with its catalogue of places, and run in headless Chromium
on copies of enveedo.com saved by ``enveedo/fixtures/fetch.py`` (the page as
rendered, scripts and styles stripped), served from disk at the site's own
address: no network. What is checked is what the brain relies on:

- a key resolves on the page in front, English or Spanish, and is rung;
- a place behind the site's own control (a "How Enveedo Works" tab, an FAQ
  accordion, the Without/With toggle, an About tab) is opened by that control
  first, and not clicked again when already open;
- the HubSpot forms are filled field by field (country by its exact option),
  the consent box never ticked and Submit never pressed, and the visitor's own
  typing and HubSpot's thank-you are reported;
- a move to another page loads the call language's twin and is finished there;
- during a call the site's same-site links lead to the call language's twin
  and stay in the tab;
- the scheduler's frame is made when HubSpot's loader has not made it.

The pages have no scripts here, so a small stand-in plays the site's own: a
click on a tab, an accordion's header or the toggle marks it open, as the live
page does. On the live site the page's own code does it.

Needs Playwright and the extension's ``node_modules`` (for esbuild); skipped
without either, as in CI. Run it with:

    cd demos/enveedo/extension && pnpm install --ignore-workspace
    cd demos && uv run --with playwright pytest tests/test_enveedo_page.py -q
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

DEMO = Path(__file__).resolve().parents[1] / "enveedo"
EXTENSION = DEMO / "extension"
FIXTURES = DEMO / "fixtures"
ESBUILD = EXTENSION / "node_modules" / ".bin" / "esbuild"
SITE = "https://enveedo.com"

PAGES = {
    "/": "home",
    "/enveedo_platform": "platform",
    "/security-performance-os": "spos",
    "/frameworks": "frameworks",
    "/partners": "partners",
    "/book-a-demo": "book-a-demo",
    "/contact": "contact",
    "/faq": "faq",
    "/trust-center": "trust-center",
    "/about-us": "about-us",
    "/es": "es-home",
    "/es/book-a-demo": "es-book-a-demo",
    "/es/contact": "es-contact",
}


def _event_models() -> dict[str, Any]:
    """The brain's event classes by wire name, from ``backend/app_events.py``:
    what the page reports must parse there (the events forbid unknown fields)."""
    spec = importlib.util.spec_from_file_location(
        "enveedo_app_events", DEMO / "backend" / "app_events.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # pydantic resolves the annotations through it
    spec.loader.exec_module(mod)
    return {
        re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower(): getattr(mod, name)
        for name in mod.__all__
        if name not in ("ENVEEDO_EVENTS", "EnveedoEvent", "DemoFields", "TabInfo")
    }


EVENTS = _event_models()


#: The site's own scripts, played: its tabs, accordions and toggle open on a
#: click, as the live page's do.
STAND_IN = """
window.__controls = 0;
document.addEventListener('click', (e) => {
  const t = e.target;
  const btn = t.closest && t.closest('.featshow__btn');
  if (btn) {
    window.__controls++;
    const root = btn.closest('[id^=featshow_]');
    const li = btn.closest('li');
    const n = [...li.parentElement.children].indexOf(li);
    root.querySelectorAll('.featshow__btn').forEach((b) => b.classList.remove('featshow__btn--active'));
    btn.classList.add('featshow__btn--active');
    root.querySelectorAll('.featshow__items > .featshow__item').forEach((it, i) =>
      it.classList.toggle('featshow__item--active', i === n));
  }
  const head = t.closest && t.closest('.accordion__header');
  if (head) {
    window.__controls++;
    const item = head.closest('.accordion__item');
    item.classList.add('accordion__item--expanded');
    item.querySelector('button[aria-controls]').setAttribute('aria-expanded', 'true');
  }
  if (t.closest && t.closest('#toggle-switch')) {
    window.__controls++;
    document.getElementById('without-label').classList.toggle('active');
    document.getElementById('with-label').classList.toggle('active');
  }
}, true);
"""


@pytest.fixture(scope="module")
def bundle(tmp_path_factory: pytest.TempPathFactory) -> str:
    if not ESBUILD.exists() or shutil.which("node") is None:
        pytest.skip("run `pnpm install --ignore-workspace` in enveedo/extension first")
    out = tmp_path_factory.mktemp("enveedo") / "page.js"
    subprocess.run(
        ["node", "test/bundle-page.mjs", str(out)],
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


def _fixture_for(path: str) -> str | None:
    p = path.rstrip("/") or "/"
    return PAGES.get(p)


@pytest.fixture
def page(browser: Any, bundle: str) -> Iterator[Any]:
    context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")

    def serve(route: Any) -> None:
        url = urlsplit(route.request.url)
        name = _fixture_for(url.path) if url.netloc == "enveedo.com" else None
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
        "window.__events = []; window.__submits = 0; window.__consentClicks = 0;"
        + "addEventListener('submit', () => { window.__submits++; }, true);"
        + "addEventListener('click', (e) => { if (e.target.matches && e.target.matches("
        + "'input[type=checkbox], input[type=submit]')) window.__consentClicks++; }, true);"
        # The top frame only, as the extension's content scripts run.
        + "if (window.top === window) document.addEventListener('DOMContentLoaded', () => {"
        + STAND_IN
        + bundle
        + "});"
    )
    pg = context.new_page()
    yield pg
    context.close()


def _open(page: Any, path: str) -> None:
    page.goto(SITE + path)
    page.wait_for_function("() => !!window.voqalizeEnveedo")


def _listen(page: Any) -> None:
    page.evaluate("() => window.voqalizeEnveedo.start((e, p) => window.__events.push([e, p]))")


def _run(page: Any, command: str, payload: dict[str, Any]) -> dict[str, Any]:
    return page.evaluate("([c, p]) => window.voqalizeEnveedo.run(c, p)", [command, payload])


def _context(page: Any) -> dict[str, Any]:
    return page.evaluate("() => window.voqalizeEnveedo.context()")


def _events(page: Any, name: str) -> list[dict[str, Any]]:
    got = page.evaluate("() => window.__events")
    for e, p in got:
        EVENTS[e].model_validate(p)  # the brain would take it
    return [p for e, p in got if e == name]


def _rings(page: Any) -> int:
    return page.locator("[data-voqalize=highlight]").count()


# ─── The pure helpers ────────────────────────────────────────────────────────


def test_twins_by_the_static_map(page: Any) -> None:
    _open(page, "/")
    got = page.evaluate(
        """() => { const t = window.__voqalizeTest; return {
          contact: t.twinPath('/contact', 'es'), home: t.twinPath('/', 'es'), back: t.twinPath('/es/', 'en'),
          grl: t.twinPath('/book-a-demo-grl', 'es'), rsa: t.twinPath('/es/book-a-demo-rsa', 'en'),
          library: t.twinPath('/webinars-and-ebooks', 'es'), pdf: t.twinPath('/hubfs/x.pdf', 'es'),
          demo: t.twinUrl('https://enveedo.com/book-a-demo?hsLang=es', 'es'),
          header: t.twinUrl('https://enveedo.com/es/enveedo_platform', 'en'),
          same: t.twinUrl('https://enveedo.com/faq', 'en'),
          blog: t.twinUrl('https://blog.enveedo.com/', 'es'),
          away: t.twinUrl('https://info.enveedo.com/x', 'es') }; }"""
    )
    assert got == {
        "contact": "/es/contact",
        "home": "/es/",
        "back": "/",
        "grl": "/es/book-a-demo-rsa",
        "rsa": "/book-a-demo-grl",
        "library": None,
        "pdf": None,
        "demo": "https://enveedo.com/es/book-a-demo",
        "header": "https://enveedo.com/enveedo_platform",
        "same": None,
        "blog": "https://blog.enveedo.com/es",
        "away": None,
    }


# ─── Places, English and Spanish ─────────────────────────────────────────────


def test_keys_resolve_on_the_english_and_the_spanish_home(page: Any) -> None:
    for path, lang in (("/", "en"), ("/es/", "es")):
        _open(page, path)
        ctx = _context(page)
        assert ctx["lang"] == lang
        assert ctx["kind"] == "home"
        assert ctx["form"] == "none"
        for key in (
            "hero",
            "problem",
            "timeline",
            "how_it_works",
            "how_integration",
            "toggle_with",
            "menu",
            "footer",
        ):
            assert key in ctx["anchors"], (path, key)
        for key in ("hero", "integrations", "final_cta"):
            assert _run(page, "show_section", {"anchor": key, "text": None})["ok"], (path, key)
            assert _rings(page) == 1


def test_an_unknown_key_fails_with_the_page_s_places(page: Any) -> None:
    _open(page, "/contact")
    got = _run(page, "show_section", {"anchor": "no_such_place", "text": None})
    assert not got["ok"]
    assert "contact_form" in got["error"]


def test_a_tab_is_opened_by_its_own_control_then_rung(page: Any) -> None:
    _open(page, "/")
    got = _run(page, "show_section", {"anchor": "how_integration", "text": None})
    assert got == {"ok": True, "detail": "opened and showed how_integration"}
    assert page.evaluate(
        "() => document.querySelector('#featshow_17458729551117 .featshow__nav li:nth-child(2) .featshow__btn')"
        ".classList.contains('featshow__btn--active')"
    )
    assert _rings(page) == 1
    # Already open: not clicked again.
    clicks = page.evaluate("() => window.__controls")
    assert _run(page, "show_section", {"anchor": "how_integration", "text": None}) == {"ok": True}
    assert page.evaluate("() => window.__controls") == clicks


def test_the_toggle_switches_both_ways_and_only_when_needed(page: Any) -> None:
    _open(page, "/")
    assert _run(page, "show_section", {"anchor": "toggle_without", "text": None}) == {"ok": True}
    assert page.evaluate("() => window.__controls") == 0
    assert _run(page, "show_section", {"anchor": "toggle_with", "text": None})["ok"]
    assert page.evaluate("() => document.querySelector('#with-label').classList.contains('active')")
    assert _run(page, "show_section", {"anchor": "toggle_without", "text": None})["ok"]
    assert page.evaluate(
        "() => document.querySelector('#without-label').classList.contains('active')"
    )
    assert page.evaluate("() => window.__controls") == 2


def test_an_faq_accordion_and_an_about_tab_open(page: Any) -> None:
    _open(page, "/faq")
    assert _run(page, "show_section", {"anchor": "faq_integrate", "text": None})["ok"]
    assert (
        page.locator(
            'button[aria-controls="accordion-panel-content_bucket-module-10-2"]'
        ).get_attribute("aria-expanded")
        == "true"
    )
    _open(page, "/about-us")
    assert _run(page, "show_section", {"anchor": "tab_vision", "text": None})["ok"]
    assert page.evaluate(
        "() => document.querySelector('#featshow_17170271512727 .featshow__nav li:nth-child(2) .featshow__btn')"
        ".classList.contains('featshow__btn--active')"
    )


# ─── Moving between pages, in the call's language ───────────────────────────


def test_navigate_in_a_spanish_call_loads_the_twin_and_finishes_there(page: Any) -> None:
    _open(page, "/")
    page.evaluate("() => window.voqalizeEnveedo.setCall(true, 'es')")
    with page.expect_navigation():
        _run(page, "navigate", {"path": "/contact", "anchor": "contact_info", "text": None})
    assert page.url == f"{SITE}/es/contact"
    page.wait_for_function("() => !!window.voqalizeEnveedo")
    page.wait_for_selector("[data-voqalize=highlight]", state="attached", timeout=15_000)
    _listen(page)
    assert _events(page, "page_changed")[0]["lang"] == "es"
    assert _events(page, "page_changed")[0]["path"] == "/es/contact"


def test_links_follow_the_call_and_stay_in_the_tab(page: Any) -> None:
    _open(page, "/")
    nav = page.locator("header nav a.nav__link").first
    assert nav.get_attribute("href") == f"{SITE}/es/enveedo_platform"
    page.evaluate("() => window.voqalizeEnveedo.setCall(true, 'en')")
    assert nav.get_attribute("href") == f"{SITE}/enveedo_platform"
    page.evaluate("() => window.voqalizeEnveedo.setCall(true, 'es')")
    assert nav.get_attribute("href") == f"{SITE}/es/enveedo_platform"
    demo = page.locator("a.btn--overlapping_header_buttons-1")
    assert demo.get_attribute("href") == f"{SITE}/es/book-a-demo"
    page.evaluate("() => window.voqalizeEnveedo.setCall(false, 'es')")
    assert nav.get_attribute("href") == f"{SITE}/es/enveedo_platform"
    assert demo.get_attribute("href") == f"{SITE}/book-a-demo?hsLang=en"

    _open(page, "/faq")
    page.evaluate("() => window.voqalizeEnveedo.setCall(true, 'en')")
    book = page.locator("a.quick-action__btn[href*='book-a-demo']")
    assert book.get_attribute("href") == f"{SITE}/book-a-demo"
    assert book.get_attribute("target") is None
    # A PDF still opens in a tab of its own.
    assert page.locator("a.quick-action__btn[href*='hubfs']").get_attribute("target") == "_blank"


# ─── The forms ──────────────────────────────────────────────────────────────


def test_the_contact_form_is_filled_never_consented_never_sent(page: Any) -> None:
    _open(page, "/contact")
    _listen(page)
    got = _run(
        page,
        "fill_form",
        {
            "form": "contact",
            "firstname": "Carolina",
            "lastname": "Rojas",
            "email": "carolina@acme.cl",
            "phone": "+56 9 1234 5678",
            "country": "Others",
            "company": "Acme",
            "message": "We need ISO 27001 and Chile's 21.719.",
        },
    )
    assert got["ok"], got
    assert "press Submit themselves" in got["detail"]
    form = page.locator('form[id^="hsForm_9ab169f1"]')
    assert form.locator('[name="firstname"]').input_value() == "Carolina"
    assert form.locator('[name="country"]').input_value() == "Others"
    assert form.locator('[name="message"]').input_value().endswith("21.719.")
    assert not form.locator('input[type="checkbox"]').first.is_checked()
    state = _events(page, "form_state")[-1]
    assert state["missing"] == ["consent"]
    assert state["invalid"] == []
    assert state["by"] == "javier"
    assert state["values"]["email"] == "carolina@acme.cl"
    assert _rings(page) == 1
    assert page.evaluate("() => [window.__submits, window.__consentClicks]") == [0, 0]


def test_a_country_not_listed_is_left_for_others(page: Any) -> None:
    _open(page, "/contact")
    country = page.locator('form[id^="hsForm_9ab169f1"] [name="country"]')
    before = country.input_value()
    got = _run(page, "fill_form", {"form": "contact", "firstname": "Ana", "country": "Spain"})
    assert got["ok"]
    assert 'no country option "Spain"' in got["detail"]
    assert country.input_value() == before


def test_the_visitor_s_typing_and_hubspot_s_thanks_are_reported(page: Any) -> None:
    _open(page, "/contact")
    _listen(page)
    page.locator('form[id^="hsForm_9ab169f1"] [name="company"]').fill("Globex")
    page.wait_for_function(
        "() => window.__events.some(([e, p]) => e === 'form_state' && p.by === 'visitor')",
        timeout=5000,
    )
    assert _events(page, "form_state")[-1]["values"]["company"] == "Globex"
    # Their press of Submit, and HubSpot's thank-you in the form's place.
    page.evaluate(
        """() => { const f = document.querySelector('form[id^="hsForm_9ab169f1"]');
          f.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
          const box = f.closest('.hbspt-form') || f.parentElement;
          const thanks = document.createElement('div'); thanks.className = 'submitted-message';
          thanks.textContent = 'Thanks for submitting the form.'; box.appendChild(thanks); }"""
    )
    page.wait_for_function("() => window.__events.some(([e]) => e === 'form_result')", timeout=5000)
    assert _events(page, "form_result")[-1] == {
        "form": "contact",
        "outcome": "sent",
        "message": "Thanks for submitting the form.",
        "fields": [],
    }


def test_the_soc2_request_from_another_page_opens_trust_center_and_fills_there(page: Any) -> None:
    _open(page, "/")
    with page.expect_navigation():
        _run(
            page,
            "fill_form",
            {
                "form": "soc2",
                "firstname": "Carolina",
                "lastname": "Rojas",
                "company": "Acme",
                "job_title": "CISO",
                "email": "carolina@acme.cl",
                "message": "For our vendor review.",
            },
        )
    assert page.url == f"{SITE}/trust-center"
    page.wait_for_function("() => !!window.voqalizeEnveedo")
    _listen(page)
    page.wait_for_function(
        "() => window.__events.some(([e]) => e === 'command_done')", timeout=20_000
    )
    form = page.locator('form[id^="hsForm_8e75d561"]')
    assert form.locator('[name="job_title"]').input_value() == "CISO"
    assert form.locator('[name="notes"]').input_value() == "For our vendor review."
    state = _events(page, "form_state")[-1]
    assert state["form"] == "soc2"
    assert state["missing"] == ["consent"]
    assert page.evaluate("() => [window.__submits, window.__consentClicks]") == [0, 0]


# ─── The scheduler ──────────────────────────────────────────────────────────


def test_book_demo_in_spanish_opens_the_spanish_page(page: Any) -> None:
    _open(page, "/faq")
    page.evaluate("() => window.voqalizeEnveedo.setCall(true, 'es')")
    with page.expect_navigation():
        page.evaluate("() => { void window.voqalizeEnveedo.run('book_demo', {}); }")
    assert page.url == f"{SITE}/es/book-a-demo"
    ctx = _context(page)
    assert ctx["form"] == "demo"
    assert ctx["kind"] == "demo"


def test_the_scheduler_frame_is_made_when_hubspot_s_loader_did_not(page: Any) -> None:
    _open(page, "/book-a-demo")
    assert page.locator(".meetings-iframe-container iframe").count() == 0
    page.evaluate("() => { void window.voqalizeEnveedo.run('book_demo', {}); }")
    frame = page.locator(".meetings-iframe-container iframe[data-voqalize-made]")
    frame.wait_for(state="attached", timeout=20_000)
    src = frame.get_attribute("src") or ""
    assert src.startswith("https://meetings.hubspot.com/elis-martinez?embed=true")
    assert "parentPageUrl=https%3A%2F%2Fenveedo.com%2Fbook-a-demo" in src
