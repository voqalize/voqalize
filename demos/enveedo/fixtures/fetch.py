# pyright: basic
# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Save copies of enveedo.com's pages the extension acts on, for the page test.

The extension's page logic (the catalogue's places on the English and the
Spanish pages, the tabs, accordions and Without/With toggle it opens, the
HubSpot forms it fills and never sends, the links it points at the call
language's twin) is checked against these copies in headless Chromium, with no
network, by ``demos/tests/test_enveedo_page.py``.

A copy is the page as a browser has it once its scripts have run (HubSpot
draws its forms and the scheduler's container then), with the scripts,
styles, stylesheets, SVGs and iframes taken out, and HubSpot's per-visitor
tokens emptied. The cookie banner is never pressed and no form is touched.

With ``--meetings`` it also saves the demo scheduler's frame on /book-a-demo
(``meetings/calendar.html``, ``times.html``, ``details.html``, for
``extension/test/meetings.spec.ts``): the calendar, then a click on the first
open day (its times), then a click on its first time (the details step).
Confirm is never pressed, and nothing is typed.

Run from ``demos/`` (Chromium installed once with ``playwright install
chromium``; always headless). The site is a real company's: one page at a
time, :data:`PAUSE_S` seconds apart::

    uv run --no-project --with playwright python enveedo/fixtures/fetch.py
    uv run --no-project --with playwright python enveedo/fixtures/fetch.py --meetings

Nothing here runs at call time: the brain never fetches the site.
"""

from __future__ import annotations

import argparse
import contextlib
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).parent
SITE = "https://enveedo.com"
PAUSE_S = 4.0
#: Saved name → path. English, then the Spanish twins the test needs.
PAGES = {
    "home": "/",
    "platform": "/enveedo_platform",
    "spos": "/security-performance-os",
    "frameworks": "/frameworks",
    "partners": "/partners",
    "book-a-demo": "/book-a-demo",
    "contact": "/contact",
    "faq": "/faq",
    "trust-center": "/trust-center",
    "about-us": "/about-us",
    "es-home": "/es/",
    "es-book-a-demo": "/es/book-a-demo",
    "es-contact": "/es/contact",
}

_DROP = (
    re.compile(r"<script\b[^>]*>.*?</script\s*>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<noscript\b[^>]*>.*?</noscript\s*>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<style\b[^>]*>.*?</style\s*>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<link\b(?![^>]*\bhreflang=)[^>]*>", re.IGNORECASE),
    re.compile(r"<svg\b.*?</svg\s*>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<iframe\b[^>]*>.*?</iframe\s*>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<video\b.*?</video\s*>", re.IGNORECASE | re.DOTALL),
)


def strip(html: str) -> str:
    for rx in _DROP:
        html = rx.sub("", html)
    # Our own marks, should a copy be taken with the extension loaded; and
    # HubSpot's per-visitor values (the form's context, the visitor token).
    html = re.sub(r'\s(?:data-voqalize-[a-z]+|translate)="[^"]*"', "", html)
    html = re.sub(r'(<input\b[^>]*type="hidden"[^>]*\bvalue=")[^"]*"', r'\1"', html)
    html = re.sub(r"(hubspotutk|parentHubspotUtk|hsutk)=[0-9a-f]+", r"\1=", html)
    html = re.sub(r'\s(?:srcset|sizes)="[^"]*"', "", html)
    return re.sub(r"\n\s*\n+", "\n", html)


def load(page, url: str) -> None:
    last: Exception | None = None
    for attempt in range(3):
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=90_000)
            if resp is None or resp.status != 200:
                raise SystemExit(f"{url}: HTTP {resp.status if resp else '?'}")
            break
        except SystemExit:
            raise
        except Exception as exc:
            last = exc
            time.sleep(10 * (attempt + 1))
    else:
        raise SystemExit(f"{url}: {last}")
    with contextlib.suppress(Exception):
        page.wait_for_load_state("load", timeout=30_000)
    # HubSpot draws its forms after the load.
    with contextlib.suppress(Exception):
        page.wait_for_selector("form.hs-form", timeout=6000)
    page.wait_for_timeout(1500)


def save_pages(page) -> None:
    for i, (name, path) in enumerate(PAGES.items()):
        if i:
            time.sleep(PAUSE_S)
        load(page, SITE + path)
        html = page.content()
        (HERE / f"{name}.html").write_text(strip(html), encoding="utf-8")
        print(f"saved {name}.html ({len(html) // 1024} KB before stripping)", flush=True)


def save_meetings(page) -> None:
    """The scheduler's frame, three steps; never Confirm, nothing typed."""
    out = HERE / "meetings"
    out.mkdir(exist_ok=True)
    load(page, SITE + "/book-a-demo")
    frame = None
    for _ in range(60):
        frame = next(
            (f for f in page.frames if f.url.startswith("https://meetings.hubspot.com/")), None
        )
        if frame:
            break
        page.wait_for_timeout(500)
    if frame is None:
        raise SystemExit("the scheduler's frame did not appear")
    frame.wait_for_selector("[data-test-id=available-date]", state="attached", timeout=30_000)
    frame.wait_for_timeout(1500)
    note = "<!-- HubSpot Meetings in the enveedo.com/book-a-demo frame, {} ({}); scripts and SVGs stripped. -->\n"
    stamp = datetime.now(UTC).date().isoformat()

    def keep(step: str) -> None:
        (out / f"{step}.html").write_text(
            note.format(stamp, step) + strip(frame.content()), encoding="utf-8"
        )
        print(f"saved meetings/{step}.html", flush=True)

    keep("calendar")
    frame.locator("[data-test-id=available-date][aria-disabled=false]").first.click()
    frame.wait_for_selector("[data-test-id=time-picker-btn]", timeout=15_000)
    frame.wait_for_timeout(1000)
    keep("times")
    frame.locator("[data-test-id=time-picker-btn]").first.click()
    frame.wait_for_selector("[data-test-id=confirm-firstName-field]", timeout=15_000)
    frame.wait_for_timeout(1000)
    keep("details")


def main() -> None:
    from playwright.sync_api import sync_playwright

    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--meetings", action="store_true", help="also save the scheduler's frame")
    args = ap.parse_args()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, locale="en-US")
        save_pages(page)
        if args.meetings:
            time.sleep(PAUSE_S)
            save_meetings(page)
        browser.close()
    (HERE / "SAVED").write_text(datetime.now(UTC).date().isoformat() + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
