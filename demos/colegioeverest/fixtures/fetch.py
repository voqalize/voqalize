# pyright: basic
# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Save copies of colegioeverest.cl's pages the extension acts on, for the page test.

The extension's page logic (the catalogue's places, the menu's dropdowns, the
home news carousel and the Infraestructura gallery, the contact form filled
field by field and never sent) is checked against these copies in headless
Chromium, with no network, the way ``demos/tests/test_figurella_page.py``
checks figurella's.

A copy is the page as a browser has it once its scripts have run — the news
carousel and the gallery are slick sliders, built only then — with the
scripts, styles, stylesheets, SVGs and iframes taken out (the test needs none
of them). The contact form keeps its fields and its Turnstile box, empty.

Run from ``demos/`` on a connection the site answers (it refuses some
countries; Chromium installed once with ``playwright install chromium``):

    uv run --no-project --with playwright python colegioeverest/fixtures/fetch.py

The server is slow and sometimes stalls: each page waits for the DOM only,
with three attempts. Nothing here runs at call time: the brain never fetches
the site.
"""

from __future__ import annotations

import contextlib
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).parent
SITE = "https://www.colegioeverest.cl"
ADM = "/bienvenidos-al-proceso-de-admision-del-colegio-everest/"
PAGES = {
    "home": "/",
    "admision": ADM,
    "contacto": "/contacto/",
    "ingles": "/nuestro-modelo-educativo/ingles-intensivo/",
    "ciclos": "/nuestro-modelo-educativo/ciclos/",
    "ambientes": "/nuestro-colegio/ambientes-seguros/",
    "infraestructura": "/nuestro-colegio/infraestructura/",
    "informacion": "/informacion-practica/",
    "normativas": "/nuestro-colegio/normativas/",
    "historia": "/nuestro-colegio/historia/",
    "post": "/hito-religioso-kinder/",
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
    # Our own marks, should a copy be taken with the extension loaded; and
    # the form's one-time tokens.
    html = re.sub(r'\s(?:data-voqalize-text|translate)="[^"]*"', "", html)
    html = re.sub(r'(name="_wpcf7_[a-z_]*"\s+value=")[^"]*"', r'\1"', html)
    return re.sub(r"\n\s*\n+", "\n", html)


def load(page, url: str) -> None:
    last: Exception | None = None
    for attempt in range(3):
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=180_000)
            if resp is None or resp.status != 200:
                raise SystemExit(f"{url}: HTTP {resp.status if resp else '?'} (VPN dropped?)")
            break
        except SystemExit:
            raise
        except Exception as exc:
            last = exc
            time.sleep(10 * (attempt + 1))
    else:
        raise SystemExit(f"{url}: {last}")
    with contextlib.suppress(Exception):
        page.wait_for_load_state("load", timeout=45_000)
    page.wait_for_timeout(1500)


def main() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, locale="es-CL")
        for name, path in PAGES.items():
            load(page, SITE + path)
            html = page.content()
            (HERE / f"{name}.html").write_text(strip(html), encoding="utf-8")
            print(f"saved {name}.html ({len(html) // 1024} KB before stripping)", flush=True)
        browser.close()
    (HERE / "SAVED").write_text(datetime.now(UTC).date().isoformat() + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
