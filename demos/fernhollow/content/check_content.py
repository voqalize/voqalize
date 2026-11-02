"""Validate Fernhollow editorial content against the catalog.

Run from anywhere with:  python3 -I demos/fernhollow/content/check_content.py
Standard library only. Exits non-zero on any failure.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATALOG = HERE.parent / "data" / "catalog.json"

JOURNAL_KEYS = ["title", "slug", "dek", "date", "room", "readMinutes", "hero", "products"]
PAGE_KEYS = ["title", "slug", "dek"]
PAGES = ["about", "returns", "delivery", "assembly", "care", "faq"]
DATE_MIN, DATE_MAX = date(2026, 9, 1), date(2026, 11, 1)
WORDS_MIN, WORDS_MAX = 700, 1100
PRODUCTS_MIN, PRODUCTS_MAX = 4, 8
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DIRECTIVE_RE = re.compile(r'^::product\{id="([^"]+)"\}$')
# Phrases and characters the editorial voice never uses.
BANNED = ["elevate your space", "elevate your", "must-have", "game-changer", "game changer"]
EMOJI_RE = re.compile("[\U0001f300-\U0001faff☀-➿]")

errors: list[str] = []


def fail(where: str, msg: str) -> None:
    errors.append(f"{where}: {msg}")


def unquote(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def parse_frontmatter(text: str, where: str) -> tuple[dict[str, object], list[str], str]:
    """Parse the small YAML subset we author: `key: scalar` and `key:` + `  - item` lists."""
    lines = text.split("\n")
    if not lines or lines[0] != "---":
        fail(where, "missing opening --- frontmatter fence")
        return {}, [], text
    try:
        end = lines.index("---", 1)
    except ValueError:
        fail(where, "missing closing --- frontmatter fence")
        return {}, [], text
    data: dict[str, object] = {}
    order: list[str] = []
    current: str | None = None
    for raw in lines[1:end]:
        if not raw.strip():
            continue
        if raw.startswith("  - ") and current is not None:
            lst = data[current]
            if not isinstance(lst, list):
                fail(where, f"list item under scalar key {current!r}")
                continue
            lst.append(unquote(raw[4:]))
            continue
        m = re.match(r"^([A-Za-z][A-Za-z0-9]*):(.*)$", raw)
        if not m:
            fail(where, f"unparseable frontmatter line: {raw!r}")
            continue
        key, val = m.group(1), m.group(2).strip()
        if key in data:
            fail(where, f"duplicate key {key!r}")
        order.append(key)
        if val == "":
            data[key] = []
            current = key
        else:
            data[key] = unquote(val)
            current = None
    return data, order, "\n".join(lines[end + 1 :])


def count_words(body: str) -> int:
    words = 0
    for line in body.split("\n"):
        s = line.strip()
        if not s or DIRECTIVE_RE.match(s):
            continue
        s = re.sub(r"^#+\s*", "", s)
        s = re.sub(r"^[-*]\s+", "", s)
        words += len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'\u2019-]*", s))
    return words


def check_voice(where: str, text: str) -> None:
    low = text.lower()
    for phrase in BANNED:
        if phrase in low:
            fail(where, f"banned phrase {phrase!r}")
    if EMOJI_RE.search(text):
        fail(where, "contains emoji")


def main() -> int:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    ids = {p["id"] for p in catalog["products"]}
    rooms = set(catalog["rooms"])
    cat_slugs = {c["slug"] for c in catalog["categories"]}

    # Journal articles
    journal = sorted(
        p for p in (HERE / "journal").glob("*.md") if not p.name.startswith("_")
    )  # `_` = dev-only samples
    if len(journal) != 9:
        fail("journal", f"expected 9 articles, found {len(journal)}")
    seen_dates: set[str] = set()
    report: list[tuple[str, int, int]] = []
    for path in journal:
        where = f"journal/{path.name}"
        text = path.read_text(encoding="utf-8")
        fm, order, body = parse_frontmatter(text, where)
        if order != JOURNAL_KEYS:
            fail(where, f"frontmatter keys must be exactly {JOURNAL_KEYS} in order, got {order}")
        slug = str(fm.get("slug", ""))
        if slug != path.stem:
            fail(where, f"slug {slug!r} != filename {path.stem!r}")
        if not SLUG_RE.match(slug):
            fail(where, f"slug {slug!r} is not kebab-case")
        for k in ("title", "dek"):
            if not isinstance(fm.get(k), str) or not str(fm.get(k)).strip():
                fail(where, f"{k} must be a non-empty string")
        try:
            d = date.fromisoformat(str(fm.get("date")))
            if not DATE_MIN <= d <= DATE_MAX:
                fail(where, f"date {d} outside {DATE_MIN}..{DATE_MAX}")
            if str(d) in seen_dates:
                fail(where, f"date {d} shared with another article")
            seen_dates.add(str(d))
        except ValueError:
            fail(where, f"bad date {fm.get('date')!r}")
        if fm.get("room") not in rooms:
            fail(where, f"room {fm.get('room')!r} not one of {sorted(rooms)}")
        if fm.get("hero") not in ids:
            fail(where, f"hero {fm.get('hero')!r} not in catalog")
        products = fm.get("products")
        if not isinstance(products, list):
            fail(where, "products must be a list")
            products = []
        if not PRODUCTS_MIN <= len(products) <= PRODUCTS_MAX:
            fail(where, f"{len(products)} products, need {PRODUCTS_MIN}-{PRODUCTS_MAX}")
        if len(set(products)) != len(products):
            fail(where, "duplicate product ids")
        for pid in products:
            if pid not in ids:
                fail(where, f"product {pid!r} not in catalog")
        placed: list[str] = []
        for line in body.split("\n"):
            s = line.strip()
            if s.startswith("::"):
                m = DIRECTIVE_RE.match(s)
                if not m or line != s:
                    fail(where, f"malformed directive line {line!r}")
                    continue
                placed.append(m.group(1))
        for pid in placed:
            if pid not in ids:
                fail(where, f"::product {pid!r} not in catalog")
        if len(set(placed)) != len(placed):
            fail(where, "a product is placed twice in the body")
        if set(placed) != set(products):
            fail(
                where,
                f"placed vs frontmatter products differ: only placed {sorted(set(placed) - set(products))},"
                f" never placed {sorted(set(products) - set(placed))}",
            )
        if not re.search(r"^## ", body, re.M):
            fail(where, "no ## subheads")
        words = count_words(body)
        if not WORDS_MIN <= words <= WORDS_MAX:
            fail(where, f"{words} words, need {WORDS_MIN}-{WORDS_MAX}")
        try:
            rm = int(str(fm.get("readMinutes")))
            expected = max(1, round(words / 200))
            if abs(rm - expected) > 1:
                fail(where, f"readMinutes {rm} but ~{expected} expected for {words} words")
        except ValueError:
            fail(where, "readMinutes must be an integer")
        check_voice(where, text)
        report.append((path.name, words, len(products)))

    # Pages
    for name in PAGES:
        path = HERE / "pages" / f"{name}.md"
        where = f"pages/{name}.md"
        if not path.exists():
            fail(where, "missing")
            continue
        text = path.read_text(encoding="utf-8")
        fm, order, body = parse_frontmatter(text, where)
        if order != PAGE_KEYS:
            fail(where, f"frontmatter keys must be exactly {PAGE_KEYS}, got {order}")
        if fm.get("slug") != name:
            fail(where, f"slug {fm.get('slug')!r} != filename {name!r}")
        if not body.strip():
            fail(where, "empty body")
        for m in re.finditer(r'::product\{id="([^"]+)"\}', body):
            if m.group(1) not in ids:
                fail(where, f"::product {m.group(1)!r} not in catalog")
        check_voice(where, text)
        report.append((f"pages/{name}.md", count_words(body), 0))

    # policies.json
    try:
        pol = json.loads((HERE / "policies.json").read_text(encoding="utf-8"))
        for k in ("returns", "delivery", "assembly", "care"):
            v = pol.get(k)
            if not isinstance(v, dict) or not v:
                fail("policies.json", f"{k} must be a non-empty object")
                continue
            for kk, vv in v.items():
                if not isinstance(vv, (str, int, float, list)):
                    fail("policies.json", f"{k}.{kk} has unsupported type")
    except (OSError, ValueError) as e:
        fail("policies.json", f"unreadable: {e}")

    # site.json
    try:
        site = json.loads((HERE / "site.json").read_text(encoding="utf-8"))
        hero = site.get("hero", {})
        for k in ("headline", "subline", "cta"):
            if not hero.get(k):
                fail("site.json", f"hero.{k} missing")
        cta = hero.get("cta", {})
        if not isinstance(cta, dict) or not cta.get("label") or not cta.get("href"):
            fail("site.json", "hero.cta needs label and href")
        if set(site.get("rooms", {})) != rooms:
            fail("site.json", f"rooms keys must be exactly {sorted(rooms)}")
        if set(site.get("categories", {})) != cat_slugs:
            missing = sorted(cat_slugs - set(site.get("categories", {})))
            extra = sorted(set(site.get("categories", {})) - cat_slugs)
            fail("site.json", f"categories mismatch: missing {missing}, extra {extra}")
        for section in ("rooms", "categories"):
            for k, v in site.get(section, {}).items():
                if not isinstance(v, str) or not v.strip():
                    fail("site.json", f"{section}.{k} blurb empty")
        if not 3 <= len(site.get("promises", [])) <= 4:
            fail("site.json", "promises must have 3-4 items")
        for k in ("newsletter", "footerTagline"):
            if not site.get(k):
                fail("site.json", f"{k} missing")
        check_voice("site.json", json.dumps(site, ensure_ascii=False))
    except (OSError, ValueError) as e:
        fail("site.json", f"unreadable: {e}")

    for name, words, n in report:
        extra = f", {n} products" if n else ""
        print(f"  {name}: {words} words{extra}")
    if errors:
        print(f"FAIL ({len(errors)} problems)")
        for e in errors:
            print("  - " + e)
        return 1
    print("OK: all content checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
