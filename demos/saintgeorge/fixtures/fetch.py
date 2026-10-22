"""Save copies of saintgeorge.cl's pages the extension acts on, for the page test.

The extension's page logic (``extension/src/site.ts``: sections, accordions,
the fees read off the admission page, the calendar's iCal feed) is checked in
``demos/tests/test_saintgeorge_page.py`` against these copies, in headless
Chromium, with no network. A copy is the page's HTML with its scripts taken
out (the test needs none of them; the adapter opens Bootstrap's accordions
itself when Bootstrap is absent) and its tables emptied (the accordions' staff
lists, which no test reads and this public repo need not carry), and the
calendar's feed cut to a few dozen events around the day it was saved.

Run from ``demos/`` on a machine the site answers (it refuses some countries):

    uv run python saintgeorge/fixtures/fetch.py

Nothing here runs at call time: the brain never fetches the site.
"""

from __future__ import annotations

import re
import sys
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).parent
SITE = "https://saintgeorge.cl"
PAGES = {
    "home": "/",
    "infant": "/unidad/infant/",
    "elementary": "/unidad/elementary/",
    "junior": "/unidad/junior/",
    "senior": "/unidad/senior/",
    "admision": "/admision/admision/",
    "moreau": "/admision/admision-programa-moreau/",
    "calendario": "/familia/calendario/",
    "estudios": "/formacion-integral/direccion_de_estudios/",
    "deportiva": "/formacion-integral/area-deportiva/",
    "musical": "/familia/musical-the-lion-king/",
}
ICAL = "https://calendar.google.com/calendar/ical/actividades%40saintgeorge.cl/public/basic.ics"
#: Events kept from the feed: the ones from this many days before the save on.
ICAL_BACK_DAYS = 7
ICAL_MAX_EVENTS = 90
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/141 Safari/537.36"

_SCRIPT = re.compile(r"<script\b[^>]*>.*?</script\s*>", re.IGNORECASE | re.DOTALL)
_NOSCRIPT = re.compile(r"<noscript\b[^>]*>.*?</noscript\s*>", re.IGNORECASE | re.DOTALL)
_TABLE = re.compile(r"(<table\b[^>]*>).*?(</table\s*>)", re.IGNORECASE | re.DOTALL)
_PRELOAD = re.compile(
    r"<link\b[^>]*rel=[\"']?(?:preload|prefetch|dns-prefetch|preconnect)[^>]*>", re.I
)


def get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "es-CL"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        if resp.status != 200:
            raise SystemExit(f"{url}: HTTP {resp.status} (VPN dropped?)")
        return resp.read().decode("utf-8", "replace")


def strip(html: str) -> str:
    html = _SCRIPT.sub("", html)
    html = _NOSCRIPT.sub("", html)
    html = _TABLE.sub(r"\1<tr><td>…</td></tr>\2", html)
    return _PRELOAD.sub("", html)


def trim_ical(text: str, today: datetime) -> str:
    """The feed's head and the events from a month before ``today`` on, at most
    :data:`ICAL_MAX_EVENTS` of them, soonest first, so the copy stays small."""
    text = text.replace("\r\n", "\n")
    head, _, rest = text.partition("BEGIN:VEVENT")
    events = re.findall(r"BEGIN:VEVENT\n.*?END:VEVENT\n", "BEGIN:VEVENT" + rest, re.DOTALL)
    since = (today - timedelta(days=ICAL_BACK_DAYS)).strftime("%Y%m%d")

    def start(ev: str) -> str:
        m = re.search(r"^DTSTART[^:]*:(\d{8})", ev, re.MULTILINE)
        return m.group(1) if m else ""

    kept = sorted((e for e in events if start(e) >= since), key=start)[:ICAL_MAX_EVENTS]
    return (head + "".join(kept) + "END:VCALENDAR\n").replace("\n", "\r\n")


def main() -> None:
    for name, path in PAGES.items():
        try:
            html = get(SITE + path)
        except Exception as exc:  # reported, then stop
            raise SystemExit(f"{path}: {exc} (VPN dropped?)") from exc
        (HERE / f"{name}.html").write_text(strip(html), encoding="utf-8")
        print(f"saved {name}.html ({len(html) // 1024} KB before stripping)")
    ics = get(ICAL)
    now = datetime.now(UTC)
    (HERE / "calendar.ics").write_text(trim_ical(ics, now), encoding="utf-8", newline="")
    (HERE / "SAVED").write_text(now.date().isoformat() + "\n", encoding="utf-8")
    print("saved calendar.ics")


if __name__ == "__main__":
    sys.exit(main())
