# pyright: basic
# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Save copies of figurella.cl's pages the extension acts on, for the page test.

The extension's page logic (``extension/src/figurella-actions.ts``: the
catalogue's places, the FAQ's accordion, the booking and franchise forms, the
testimonials' carousel) is checked in ``demos/tests/test_figurella_page.py``
against these copies, in headless Chromium, with no network.

A copy is the page as a browser has it once its scripts have run — the
testimonials are Slick slides and the FAQ an open accordion only then — with
the scripts, styles and stylesheets taken out (the test needs none of them,
and the adapter opens the FAQ itself when nothing on the page does) and the
WhatsApp widget's inline settings gone with the scripts. The bottom bar is
closed before the copy is taken, as the adapter closes it.

Run from ``demos/`` on a machine the site answers (it refuses some countries;
Chromium installed once with ``playwright install chromium``):

    uv run --no-project --with playwright python figurella/fixtures/fetch.py

Nothing here runs at call time: the brain never fetches the site.
"""

from __future__ import annotations

import re
import sys
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).parent
SITE = "https://figurella.cl"
PAGES = {
    "home": "/",
    "metodo": "/metodo-figurella/",
    "planes": "/planes/",
    "historias": "/historias-de-exito/",
    "convenios": "/convenios/",
    "franquicias": "/franquicias/",
    "faq": "/preguntas-frecuentes/",
    "post": "/capsula-termica-y-sus-beneficios/",
}

_DROP = (
    re.compile(r"<script\b[^>]*>.*?</script\s*>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<noscript\b[^>]*>.*?</noscript\s*>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<style\b[^>]*>.*?</style\s*>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<link\b[^>]*>", re.IGNORECASE),
    re.compile(r"<svg\b.*?</svg\s*>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<iframe\b[^>]*>.*?</iframe\s*>", re.IGNORECASE | re.DOTALL),
)


def strip(html: str) -> str:
    for rx in _DROP:
        html = rx.sub("", html)
    # Our own marks, should a copy be taken with the extension loaded.
    html = re.sub(r'\s(?:data-voqalize-text|translate)="[^"]*"', "", html)
    return re.sub(r"\n\s*\n+", "\n", html)


def main() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, locale="es-CL")
        for name, path in PAGES.items():
            resp = page.goto(SITE + path, wait_until="load", timeout=120_000)
            if resp is None or resp.status != 200:
                raise SystemExit(f"{path}: HTTP {resp.status if resp else '?'} (VPN dropped?)")
            page.wait_for_timeout(1500)
            page.evaluate(
                "document.querySelector('#elementor-popup-modal-480 .dialog-close-button')?.click()"
            )
            page.wait_for_timeout(400)
            html = page.content()
            (HERE / f"{name}.html").write_text(strip(html), encoding="utf-8")
            print(f"saved {name}.html ({len(html) // 1024} KB before stripping)")
        browser.close()
    (HERE / "SAVED").write_text(datetime.now(UTC).date().isoformat() + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
