"""The saintgeorge extension's page logic, against saved copies of the real pages.

The adapter (``saintgeorge/extension/src/saintgeorge-actions.ts``) is bundled
as the extension ships it and run in headless Chromium on copies of
saintgeorge.cl saved by ``saintgeorge/fixtures/fetch.py`` (scripts stripped),
served from disk at the site's own address: no network. What is checked is
what the brain relies on — the headings and accordions a page reports, an
accordion opened by its button's words (the ids repeat across pages), the fees
and admission lines read off the admission page, a move finished on the next
page after a full load, the calendar's feed parsed and its events reported,
and the contact card, which sends nothing.

The page has no Bootstrap here (its scripts are stripped), so an accordion is
opened by the adapter's own fallback; on the live site the page's Bootstrap
does it. Only Bootstrap's one rule that matters, a closed pane is hidden, is
added.

Needs Playwright and the extension's ``node_modules`` (for esbuild); skipped
without either, as in CI. Run it with:

    cd demos/saintgeorge/extension && pnpm install --ignore-workspace
    cd demos && uv run --with playwright pytest tests/test_saintgeorge_page.py -q
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

DEMO = Path(__file__).resolve().parents[1] / "saintgeorge"
EXTENSION = DEMO / "extension"
FIXTURES = DEMO / "fixtures"
ESBUILD = EXTENSION / "node_modules" / ".bin" / "esbuild"
SITE = "https://saintgeorge.cl"

PAGES = {
    "/": "home",
    "/unidad/infant/": "infant",
    "/unidad/elementary/": "elementary",
    "/unidad/junior/": "junior",
    "/unidad/senior/": "senior",
    "/admision/admision/": "admision",
    "/admision/admision-programa-moreau/": "moreau",
    "/familia/calendario/": "calendario",
    "/formacion-integral/direccion_de_estudios/": "estudios",
    "/formacion-integral/area-deportiva/": "deportiva",
    "/familia/musical-the-lion-king/": "musical",
}

#: Bootstrap's one rule the adapter's moves depend on.
_CSS = ".collapse:not(.show){display:none}"

#: Stands in for the extension's bridge and hub: answers the page's ask for
#: the calendar with the saved feed, parsed by the adapter's own parser, as if
#: today were the day it was saved.
_FAKE_HUB = """
window.addEventListener("message", (e) => {
  const out = e.data && e.data["voqalize:out"];
  if (!out || !out.ask || out.ask.op !== "calendar") return;
  const t = window.__voqalizeTest;
  const now = new Date(window.__saved + "T12:00:00Z");
  const events = t.upcoming(t.parseIcs(window.__ics), now, out.ask.count || 30);
  window.postMessage({ "voqalize:in": { re: out.id, result: { ok: true, today: t.todayIn(now), events } } }, location.origin);
});
"""


@pytest.fixture(scope="module")
def bundle(tmp_path_factory: pytest.TempPathFactory) -> str:
    if not ESBUILD.exists() or shutil.which("node") is None:
        pytest.skip("run `pnpm install --ignore-workspace` in saintgeorge/extension first")
    out = tmp_path_factory.mktemp("saintgeorge") / "page.js"
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
    context = browser.new_context(viewport={"width": 1280, "height": 900}, locale="es-CL")
    saved = (FIXTURES / "SAVED").read_text(encoding="utf-8").strip()
    ics = (FIXTURES / "calendar.ics").read_text(encoding="utf-8")

    def serve(route: Any) -> None:
        url = urlsplit(route.request.url)
        name = PAGES.get(url.path) if url.netloc == "saintgeorge.cl" else None
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
        f"window.__saved = {json.dumps(saved)}; window.__ics = {json.dumps(ics)};"
        + _FAKE_HUB
        + "document.addEventListener('DOMContentLoaded', () => {"
        + f"const s = document.createElement('style'); s.textContent = {json.dumps(_CSS)};"
        + "document.head.appendChild(s);"
        + "window.__events = [];"
        + bundle
        + "});"
    )
    pg = context.new_page()
    yield pg
    context.close()


def _open(page: Any, path: str) -> None:
    page.goto(SITE + path)
    page.wait_for_function("() => !!window.voqalizeSaintGeorge")


def _listen(page: Any) -> None:
    page.evaluate("() => window.voqalizeSaintGeorge.start((e, p) => window.__events.push([e, p]))")


def _run(page: Any, command: str, payload: dict[str, Any]) -> dict[str, Any]:
    return page.evaluate("([c, p]) => window.voqalizeSaintGeorge.run(c, p)", [command, payload])


def _events(page: Any, name: str) -> list[Any]:
    return [p for e, p in page.evaluate("() => window.__events") if e == name]


def _context(page: Any) -> dict[str, Any]:
    return page.evaluate("() => window.voqalizeSaintGeorge.context()")


def _open_panes(page: Any) -> list[str]:
    return page.evaluate(
        "() => [...document.querySelectorAll('.accordion-item')]"
        ".filter((i) => i.querySelector('.accordion-collapse.show'))"
        ".map((i) => i.querySelector('.accordion-button').textContent.replace(/\\s+/g, ' ').trim())"
    )


def _ringed(page: Any) -> bool:
    return page.evaluate("() => !!document.querySelector('[data-voqalize=highlight]')")


# ─── What a page reports ─────────────────────────────────────────────────────


def test_the_home_page_reports_its_three_sections(page: Any) -> None:
    _open(page, "/")
    ctx = _context(page)
    assert ctx["kind"] == "home"
    heads = " | ".join(ctx["headings"])
    for heading in ("Nuestra comunidad", "La misión que nos convoca", "Nuestros valores"):
        assert heading in heads
    assert {"Respeto", "Caridad"} <= set(ctx["headings"])
    assert {"Infant", "Elementary", "Junior", "Senior"} <= set(ctx["cards"])


def test_the_home_tour_rings_each_section(page: Any) -> None:
    _open(page, "/")
    for heading in ("Nuestra comunidad", "La misión que nos convoca", "Nuestros valores"):
        assert _run(page, "show_section", {"heading": heading, "text": None}) == {"ok": True}
        assert _ringed(page)
    assert _run(page, "show_section", {"heading": "Respeto", "text": None})["ok"]


def test_a_unit_page_reports_its_grades_as_accordions(page: Any) -> None:
    _open(page, "/unidad/elementary/")
    ctx = _context(page)
    assert ctx["kind"] == "unit"
    assert ctx["faqs"] == [
        "Dirección y equipo Elementary",
        "1º BÁSICO",
        "2º BÁSICO",
        "3º BÁSICO",
        "4º BÁSICO",
    ]
    # The accordions' headers are not headings.
    assert not any("BÁSICO" in h for h in ctx["headings"])


def test_a_grade_opens_by_its_words_whatever_the_ordinal_mark(page: Any) -> None:
    _open(page, "/unidad/elementary/")
    assert _open_panes(page) == []
    assert _run(page, "open_faq", {"question": "1° basico"}) == {"ok": True}
    assert _open_panes(page) == ["1º BÁSICO"]
    assert _ringed(page)


def test_senior_grades_open_by_number(page: Any) -> None:
    _open(page, "/unidad/senior/")
    assert _run(page, "open_faq", {"question": "9º"})["ok"]
    assert _open_panes(page) == ["9°"]


def test_an_accordion_that_is_not_there_names_the_ones_that_are(page: Any) -> None:
    _open(page, "/unidad/infant/")
    out = _run(page, "open_faq", {"question": "5º BÁSICO"})
    assert out["ok"] is False
    assert "PRE KINDER" in out["error"] and "KINDER" in out["error"]


# ─── A move across a full page load ──────────────────────────────────────────


def test_a_grade_on_another_page_opens_after_the_load(page: Any) -> None:
    _open(page, "/")
    with page.expect_navigation():
        _run(
            page,
            "navigate",
            {"path": "/unidad/infant", "heading": None, "text": None, "faq": "KINDER"},
        )
    page.wait_for_function("() => !!window.voqalizeSaintGeorge")
    page.wait_for_function(
        "() => [...document.querySelectorAll('.accordion-collapse.show')].length > 0", timeout=15000
    )
    assert page.url == f"{SITE}/unidad/infant/"
    assert _open_panes(page) == ["KINDER"]


# ─── The admission page, read live ───────────────────────────────────────────


def test_the_fees_and_the_admission_lines_are_read_as_written(page: Any) -> None:
    _open(page, "/admision/admision/")
    read = page.evaluate(
        "() => { const r = window.__voqalizeTest.readFees(); "
        "return {heading: r.heading, fees: r.fees, status: r.status}; }"
    )
    assert read["heading"] == "Valores referenciales año 2026"
    assert [f["value"] for f in read["fees"]] == ["UF 85", "UF 13,5", "UF 18"]
    assert read["fees"][0]["label"] == "Cuota de Incorporación por estudiante"
    assert "puede variar" in read["fees"][2]["note"]
    assert read["status"][0].startswith("Admisión 2027:")
    assert read["status"][1].startswith("Admisión Pre Kínder 2028:")


def test_show_fees_rings_them_and_reports_them(page: Any) -> None:
    _open(page, "/admision/admision/")
    _listen(page)
    assert _run(page, "show_fees", {"path": "/admision/admision", "about": "fees"}) == {"ok": True}
    assert _ringed(page)
    (fees,) = _events(page, "fees_read")
    assert [f["value"] for f in fees["fees"]] == ["UF 85", "UF 13,5", "UF 18"]
    assert len(fees["status"]) == 2


def test_show_fees_from_another_page_reads_them_after_the_load(page: Any) -> None:
    _open(page, "/unidad/junior/")
    with page.expect_navigation():
        _run(page, "show_fees", {"path": "/admision/admision", "about": "admission"})
    page.wait_for_function("() => !!window.voqalizeSaintGeorge")
    # The call rejoins after the load: what the move read waits for it.
    page.wait_for_timeout(3500)
    _listen(page)
    (fees,) = _events(page, "fees_read")
    assert fees["status"][0].startswith("Admisión 2027:")


def test_a_page_without_fees_fails_the_read_in_words(page: Any) -> None:
    _open(page, "/admision/admision-programa-moreau/")
    out = page.evaluate(
        "() => { const r = window.__voqalizeTest.readFees(); return r.fees.length + r.status.length; }"
    )
    assert out == 0


# ─── The calendar ────────────────────────────────────────────────────────────


def test_the_calendar_feed_parses_in_santiago_time(page: Any) -> None:
    _open(page, "/")
    events = page.evaluate(
        "() => { const t = window.__voqalizeTest; "
        "return t.upcoming(t.parseIcs(window.__ics), new Date(window.__saved + 'T12:00:00Z'), 200); }"
    )
    saved = (FIXTURES / "SAVED").read_text(encoding="utf-8").strip()
    assert events, "the saved feed has events from its day on"
    assert all(e["date"] >= saved for e in events)
    assert [e["date"] for e in events] == sorted(e["date"] for e in events)
    assert all(e["title"] and "\\" not in e["title"] for e in events)
    # A time given in UTC is on Santiago's clock: 11:15Z is 08:15 in October.
    timed = [e for e in events if e["time"]]
    assert timed and all(len(e["time"]) == 5 for e in timed)
    assert any(e["time"] == "08:15" for e in timed)


def test_show_events_opens_the_calendar_and_reports_the_next_events(page: Any) -> None:
    _open(page, "/")
    with page.expect_navigation():
        _run(page, "show_events", {"path": "/familia/calendario", "count": 12})
    page.wait_for_function("() => !!window.voqalizeSaintGeorge")
    page.wait_for_timeout(4000)
    _listen(page)
    (read,) = _events(page, "events_read")
    assert read["today"] == (FIXTURES / "SAVED").read_text(encoding="utf-8").strip()
    assert 0 < len(read["events"]) <= 12
    assert _ringed(page)
    assert "Calendario" in _context(page)["headings"]


# ─── Formation pages ─────────────────────────────────────────────────────────


def test_academics_shows_cambridge_and_opens_an_accordion(page: Any) -> None:
    _open(page, "/formacion-integral/direccion_de_estudios/")
    assert any("CAMBRIDGE ENGLISH" in h for h in _context(page)["headings"])
    assert _run(
        page, "show_section", {"heading": "Cambridge English Qualifications", "text": None}
    )["ok"]
    assert _run(page, "open_faq", {"question": "Centro de Información y Extensión (CIE)"})["ok"]
    assert _open_panes(page) == ["Centro de Información y Extensión (CIE)"]


def test_sports_opens_its_team_and_lists_the_schedule(page: Any) -> None:
    _open(page, "/formacion-integral/area-deportiva/")
    assert _run(page, "open_faq", {"question": "CONOCE AL EQUIPO"})["ok"]
    links = _context(page)["links"]
    schedule = [x for x in links if x["label"] == "HORARIOS DEPORTE 2026"]
    assert schedule and schedule[0]["url"].endswith("Horario-Deporte-2026.pdf")


def test_the_musical_reports_its_ticket_link(page: Any) -> None:
    _open(page, "/familia/musical-the-lion-king/")
    urls = [x["url"] for x in _context(page)["links"]]
    assert "https://ticketplus.cl/events/musical-the-lion-king" in urls


# ─── The contact card ────────────────────────────────────────────────────────


def test_the_contact_card_readies_an_email_and_sends_nothing(page: Any) -> None:
    _open(page, "/admision/admision/")
    _listen(page)
    card = {
        "to": "admisiones@saintgeorge.cl",
        "subject": "Consulta de admisión: Kínder 2027",
        "body": "Hola,\n\nMi nombre es Ana.",
        "phone": "+56 2 2355 6181",
        "language": "es",
    }
    assert _run(page, "show_contact_card", card) == {"ok": True}
    href = page.evaluate(
        "() => document.getElementById('voqalize-contact-card').shadowRoot"
        ".querySelector('a.mail').getAttribute('href')"
    )
    assert href.startswith("mailto:admisiones@saintgeorge.cl?subject=Consulta%20de%20admisi")
    assert "body=Hola%2C%0A%0AMi%20nombre%20es%20Ana." in href
    (done,) = _events(page, "command_done")
    assert done["command"] == "show_contact_card"
    assert not _events(page, "contact_used")


def test_the_contact_card_writes_only_to_the_school(page: Any) -> None:
    _open(page, "/")
    out = _run(
        page,
        "show_contact_card",
        {"to": "someone@example.com", "subject": "x", "body": "x", "phone": "1", "language": "en"},
    )
    assert out["ok"] is False
