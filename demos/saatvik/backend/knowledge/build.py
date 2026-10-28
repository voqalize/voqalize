"""Build Saatvik's L3 knowledge: the site's pages and its product PDFs, as data.

The build runs offline on a dev machine; its output is committed and the brain
only ever reads the JSON. Network is touched only by ``crawl``, and every
download is cached outside the repository, so a re-run is cheap and ``search``
never fetches anything.

Run from ``voqalize/demos``. HTML is read with the standard library's parser and
PDFs with pypdf, which the demos already depend on; pages with no usable text
layer are OCR'd with poppler's ``pdftoppm`` and ``tesseract`` (Homebrew)::

    uv run python saatvik/backend/knowledge/build.py crawl
    uv run python saatvik/backend/knowledge/build.py crawl --refresh
    uv run python saatvik/backend/knowledge/build.py crawl --offline
    uv run python saatvik/backend/knowledge/build.py search "temperature coefficient"

``crawl`` reads the sitemap, fetches each page plus the blog and press-release
articles those pages link to, and writes, next to this file:

- ``L3/pages.json`` — ``[{path, title, description, headings, faqs: [{q, a}],
  stats: [{label, value}], tables: [{caption, header, rows}], text,
  documents}]``. ``text`` is the visible text of ``<main>`` with repeated lines
  collapsed (the home page repeats its carousels). ``sections`` is
  ``[{heading, text}]``: each ``h1``-``h3`` with the text under it up to the
  next one, which the brain scores a sentence against to ring the section it is
  about. ``tabs`` are the labels of a product page's spec tabs (ELECTRICAL,
  MECHANICAL, WARRANTY), the same buttons the extension's ``open_tab`` clicks. ``faqs`` are the accordion
  buttons; their answers ship in the server HTML (collapsed, not absent) and,
  failing that, are looked up in the Next.js flight data. ``stats`` and
  ``tables`` come from the flight data, because the server HTML renders the
  animated counters as 0 and shows only the first tab of a spec table; a
  counter's 0 is dropped from ``text``.
- ``L3/documents.json`` — every product PDF (``/docs/datasheets``, ``manuals``,
  ``guides``, ``product-documents``, ``esg``, ``brochures``), read page by page with pypdf:
  ``[{id, url, title, kind, pages: [{n, text}], linked_from}]``. ``text`` keeps
  pypdf's reading order with whitespace collapsed inside each line, which is
  what pdf.js puts in its text layer, so a quote taken from here can be found
  and highlighted in the browser. A page whose text layer gives fewer than
  ``OCR_BELOW`` characters (the datasheets draw their text as outlines), or a
  datasheet page OCR reads ``OCR_DATASHEET_GAIN`` times longer, is OCR'd instead and written ``{n, text, ocr: true, words: [[word, x0, y0, x1,
  y1]]}``: ``text`` is a line per tesseract line, and each word's box is a
  fraction of the page, top-left origin, so a highlight can be drawn without a
  text layer. OCR needs ``pdftoppm`` (poppler) and ``tesseract`` and runs only in
  ``crawl``; its results are cached by the PDF's hash beside the downloads, so
  ``--offline`` re-uses them and ``--refresh`` redoes them.
- ``L3/investor_documents.json`` — every other PDF (the investor and financial
  filings under ``/docs/<yyyy>/<mm>/`` and any other non-product file), listed
  ``[{title, url, linked_from}]`` and not downloaded.

``--offline`` builds from the cache only; ``--refresh`` re-downloads everything.
The cache is ``$XDG_CACHE_HOME/voqalize-saatvik`` (``~/.cache`` by default).

:func:`search` is a small BM25 over page and PDF-page passages; the brain may
copy it. It needs only the standard library.
"""

from __future__ import annotations

import argparse
import hashlib
import html as htmllib
import json
import logging
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Iterator
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, cast

HERE = Path(__file__).resolve().parent
L3 = HERE / "L3"
SITE = "https://www.saatvikgroup.com"
SITEMAP = "https://saatvikgroup.com/sitemap.xml"
CACHE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "voqalize-saatvik"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"

# The sitemap names the blog and press-release lists but not their articles, and
# misses pages the navigation links to (/products, /inverters/hybrid,
# /solar-cell-technology, ...): follow every site link any page carries, except
# into the asset trees.
SKIP_PREFIXES = ("/_next", "/docs/", "/api/", "/cdn-cgi/")
PRODUCT_DIRS = ("datasheets", "manuals", "guides", "product-documents", "esg", "brochures")

PDF_RE = re.compile(
    r"""(?:https?:)?(?:\\?/\\?/(?:www\.)?saatvikgroup\.com)?\\?/docs\\?/[^"'<>\s\\]*?(?:\\/[^"'<>\s\\]*?)*\.pdf""",
    re.I,
)


# --------------------------------------------------------------------------- fetch


class Fetcher:
    def __init__(self, *, offline: bool, refresh: bool) -> None:
        self.offline = offline
        self.refresh = refresh
        self.misses: list[str] = []

    def _path(self, url: str, kind: str) -> Path:
        name = hashlib.sha1(url.encode()).hexdigest()[:16]
        tail = urllib.parse.urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1] or "index"
        tail = re.sub(r"[^A-Za-z0-9._-]", "_", tail)[-60:]
        return CACHE / kind / f"{name}-{tail}"

    def get(self, url: str, kind: str) -> bytes | None:
        p = self._path(url, kind)
        if p.exists() and not self.refresh:
            return p.read_bytes()
        if self.offline:
            self.misses.append(url)
            return None
        quoted = urllib.parse.quote(url, safe=":/?=&%#")
        for attempt in range(3):
            try:
                req = urllib.request.Request(quoted, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = r.read()
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
                time.sleep(0.2)
                return data
            except Exception as e:
                if getattr(e, "code", None) == 404 or attempt == 2:
                    print(f"  ! {url}: {e}", file=sys.stderr)
                    self.misses.append(url)
                    return None
                time.sleep(2 * (attempt + 1))
        return None


# --------------------------------------------------------------------------- pages


def norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def site_path(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    return parts.path.rstrip("/") or "/"


def flight_text(raw: str) -> str:
    """The Next.js flight payloads (``self.__next_f.push([1,"..."])``), decoded and joined."""
    out = []
    for m in re.finditer(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', raw):
        try:
            out.append(json.loads(m.group(1)))
        except json.JSONDecodeError:
            continue
    return "".join(out)


def find_pdfs(raw: str) -> list[str]:
    """Every /docs/…pdf referenced in the HTML or the flight data, as a site path."""
    found: list[str] = []
    for blob in (raw, flight_text(raw)):
        for m in PDF_RE.finditer(blob):
            s = m.group(0).replace("\\/", "/")
            s = htmllib.unescape(s)
            i = s.find("/docs/")
            p = urllib.parse.unquote(s[i:])
            if p not in found:
                found.append(p)
    return found


def flight_objects(flight: str, key: str) -> list[dict[str, Any]]:
    """Every JSON object in the flight data that carries ``key``, decoded.

    The flight data is React's serialised props, so the spec tabs a visitor
    clicks through, the comparison tables and the animated counters are all in
    it as plain JSON even where the server HTML shows only the first tab, or a 0.
    """
    dec = json.JSONDecoder()
    out: list[dict[str, Any]] = []
    end_of_last = -1
    for m in re.finditer(f'"{re.escape(key)}":', flight):
        if m.start() < end_of_last:
            continue
        start = m.start()
        for _ in range(40):
            start = flight.rfind("{", 0, start)
            if start < 0:
                break
            try:
                obj, end = dec.raw_decode(flight, start)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and key in obj and start + end > m.start():
                out.append(cast(dict[str, Any], obj))
                end_of_last = end
                break
    return out


def flight_tables(flight: str) -> list[dict[str, Any]]:
    """Spec tabs and comparison tables: ``[{caption, header, rows}]``."""
    tables: list[dict[str, Any]] = []
    for obj in flight_objects(flight, "groups"):
        title = norm_ws(str(obj.get("title", "")))
        for g in obj.get("groups") or []:
            if not isinstance(g, dict) or not isinstance(g.get("specs"), list):
                continue
            rows = [
                [norm_ws(str(r.get("label", ""))), norm_ws(str(r.get("value", "")))]
                for r in g["specs"]
                if isinstance(r, dict)
            ]
            caption = " — ".join(x for x in (title, norm_ws(str(g.get("name", "")))) if x)
            tables.append({"caption": caption, "header": ["Specification", "Value"], "rows": rows})
    for obj in flight_objects(flight, "headers"):
        if not isinstance(obj.get("rows"), list):
            continue
        header = ["", *(norm_ws(str(h)) for h in obj["headers"])]
        rows = [
            [norm_ws(str(r.get("label", ""))), *(norm_ws(str(v)) for v in r.get("values", []))]
            for r in obj["rows"]
            if isinstance(r, dict)
        ]
        tables.append(
            {"caption": norm_ws(str(obj.get("title", ""))), "header": header, "rows": rows}
        )
    return tables


def _number(v: object, decimals: object) -> str:
    if not isinstance(v, int | float):
        return str(v)
    d = decimals if isinstance(decimals, int) else 0
    return f"{v:,.{d}f}"


def flight_stats(flight: str) -> list[dict[str, str]]:
    """The animated counters (rendered as 0 on the server): ``[{label, value}]``."""
    stats: list[dict[str, str]] = []
    for obj in flight_objects(flight, "stats"):
        for st in obj.get("stats") or []:
            if isinstance(st, dict) and "label" in st:
                value = f"{st.get('prefix', '')}{_number(st.get('value'), st.get('decimals'))}{st.get('suffix', '')}"
                stats.append({"label": norm_ws(str(st["label"])), "value": value.strip()})
    # Inline counters sit in an element React keyed by its label; a comparison
    # row holds one counter per column, in column order.
    dec = json.JSONDecoder()
    for m in re.finditer(r'\["\$","div","([^"$][^"]*)",\{', flight):
        try:
            el, _ = dec.raw_decode(flight, m.start())
        except json.JSONDecodeError:
            continue
        counters = [c for c in _walk(el) if "end" in c and "decimals" in c]
        if not counters:
            continue
        values = [
            f"{c.get('prefix', '')}{_number(c.get('end'), c.get('decimals'))}{c.get('suffix', '')}".strip()
            for c in counters
        ]
        item = {"label": norm_ws(m.group(1)), "value": " | ".join(values)}
        if item not in stats:
            stats.append(item)
    return stats


def _walk(node: object) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        d = cast(dict[str, Any], node)
        yield d
        for v in d.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in cast(list[object], node):
            yield from _walk(v)


ZERO_COUNTER = re.compile(
    r"^(?:<\s*|[\u2212+-]|Avg\.\s*|\+)?0(?:\.0+)?\s*(?:%|yr|Wp|GW|MW|kW|\+|x|\u00d7)?\S{0,8}$"
)


def faq_answer_from_flight(flight: str, q: str) -> str:
    """An answer the server HTML did not carry, looked up next to its question."""
    i = flight.find(json.dumps(q)[1:-1])
    if i < 0:
        return ""
    window = flight[i : i + 4000]
    m = re.search(r'"(?:a|answer|content|text|description)"\s*:\s*"((?:[^"\\]|\\.)*)"', window)
    if not m:
        return ""
    try:
        return norm_ws(json.loads(f'"{m.group(1)}"'))
    except json.JSONDecodeError:
        return ""


VOID = frozenset(
    [
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    ]
)
INLINE = frozenset(
    [
        "a",
        "abbr",
        "b",
        "bdi",
        "bdo",
        "cite",
        "code",
        "data",
        "dfn",
        "em",
        "i",
        "kbd",
        "mark",
        "q",
        "s",
        "samp",
        "small",
        "span",
        "strong",
        "sub",
        "sup",
        "time",
        "u",
        "var",
    ]
)
SKIP = frozenset(["script", "style", "noscript", "svg", "template"])


class Node:
    """An element of a small DOM, enough to read a server-rendered Next.js page."""

    def __init__(self, tag: str, attrs: dict[str, str], parent: Node | None) -> None:
        self.tag = tag
        self.attrs = attrs
        self.parent = parent
        self.children: list[Node | str] = []

    def iter(self, *tags: str) -> Iterator[Node]:
        for c in self.children:
            if isinstance(c, Node):
                if not tags or c.tag in tags:
                    yield c
                yield from c.iter(*tags)

    def find(self, tag: str) -> Node | None:
        return next(self.iter(tag), None)

    def text(self) -> str:
        """Visible text; block elements break lines, inline ones do not."""
        out: list[str] = []
        self._text(out)
        return "".join(out)

    def _text(self, out: list[str]) -> None:
        if self.tag in SKIP:
            return
        block = self.tag not in INLINE
        if block:
            out.append("\n")
        for c in self.children:
            if isinstance(c, str):
                out.append(c)
            else:
                c._text(out)
        if block:
            out.append("\n")

    def strings(self) -> list[str]:
        """Each text node on its own, the way a card's title and caption stay apart."""
        out: list[str] = []
        for c in self.children:
            if isinstance(c, str):
                if c.strip():
                    out.append(norm_ws(c))
            elif c.tag not in SKIP:
                out.extend(c.strings())
        return out

    def next_element_sibling(self) -> Node | None:
        if self.parent is None:
            return None
        sibs = [c for c in self.parent.children if isinstance(c, Node)]
        i = sibs.index(self)
        return sibs[i + 1] if i + 1 < len(sibs) else None


class TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {}, None)
        self.cur = self.root

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag, {k: v or "" for k, v in attrs}, self.cur)
        self.cur.children.append(node)
        if tag not in VOID:
            self.cur = node

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.cur.children.append(Node(tag, {k: v or "" for k, v in attrs}, self.cur))

    def handle_endtag(self, tag: str) -> None:
        n: Node | None = self.cur
        while n is not None and n.tag != tag:
            n = n.parent
        if n is not None and n.parent is not None:
            self.cur = n.parent

    def handle_data(self, data: str) -> None:
        self.cur.children.append(data)


def in_chrome(n: Node) -> bool:
    """True inside the site's own header or nav, whose menus are also expandable buttons."""
    p = n.parent
    while p is not None:
        if p.tag in ("nav", "header"):
            return True
        p = p.parent
    return False


def parse(raw: str) -> Node:
    b = TreeBuilder()
    b.feed(raw)
    b.close()
    return b.root


#: How much of a section's text is kept: enough to tell it from its neighbours.
SECTION_CHARS = 600


def sections_of(main: Node) -> list[dict[str, str]]:
    """Each ``h1``-``h3`` of ``main`` and the visible text under it, in page order."""
    out: list[dict[str, str]] = []
    cur: dict[str, Any] | None = None

    def walk(n: Node) -> None:
        nonlocal cur
        if n.tag in SKIP or in_chrome(n):
            return
        if n.tag in ("h1", "h2", "h3"):
            heading = norm_ws(n.text())
            if heading:
                cur = {"heading": heading, "parts": []}
                out.append(cur)
            return
        for c in n.children:
            if isinstance(c, str):
                if cur is not None and (t := norm_ws(c)) and not ZERO_COUNTER.match(t):
                    cur["parts"].append(t)
            else:
                walk(c)

    walk(main)
    merged: dict[str, dict[str, str]] = {}
    for sec in out:
        text = " ".join(cast(list[str], sec["parts"]))[:SECTION_CHARS]
        heading = cast(str, sec["heading"])
        if heading in merged:
            continue
        merged[heading] = {"heading": heading, "text": text}
    return list(merged.values())


def _classes(n: Node) -> set[str]:
    return set(n.attrs.get("class", "").split())


def tabs_of(main: Node) -> list[str]:
    """The spec tabs' labels: buttons inside ``#specifications``, with
    ``role=tab``, or styled as the site's spec tabs; never an accordion."""
    out: list[str] = []
    for b in main.iter("button"):
        if "aria-expanded" in b.attrs or in_chrome(b):
            continue
        inside_specs = False
        p = b.parent
        while p is not None:
            if p.attrs.get("id") == "specifications":
                inside_specs = True
                break
            p = p.parent
        styled = {"text-xs", "font-medium", "tracking-widest"} <= _classes(b)
        if not (inside_specs or b.attrs.get("role") == "tab" or styled):
            continue
        label = norm_ws(b.text())
        if label and len(label) <= 40 and label not in out:
            out.append(label)
    return out


def extract_page(path: str, raw: str) -> tuple[dict[str, Any], dict[str, str], list[str]]:
    """The page record, the PDF link texts it carries, and the site links it holds."""
    root = parse(raw)
    t = root.find("title")
    title = norm_ws(t.text()) if t else ""
    description = ""
    for m in root.iter("meta"):
        if m.attrs.get("name") == "description":
            description = norm_ws(m.attrs.get("content", ""))
            break

    link_text: dict[str, str] = {}
    links: list[str] = []
    for a in root.iter("a"):
        href = a.attrs.get("href", "")
        if href.startswith((SITE, "https://saatvikgroup.com")):
            href = urllib.parse.urlsplit(href).path
        if not href.startswith("/"):
            continue
        href = urllib.parse.unquote(href.split("#")[0].split("?")[0])
        if href.lower().endswith(".pdf"):
            label = clean_link_title(next(iter(a.strings()), ""))
            if label and href not in link_text:
                link_text[href] = label
        elif not href.startswith("/_next"):
            links.append(href.rstrip("/") or "/")

    main = root.find("main") or root.find("body") or root

    headings: list[str] = []
    for h in main.iter("h1", "h2", "h3"):
        ht = norm_ws(h.text())
        if ht and ht not in headings:
            headings.append(ht)

    flight = flight_text(raw)
    faqs: list[dict[str, str]] = []
    seen_q: set[str] = set()
    for b in main.iter("button"):
        if "aria-expanded" not in b.attrs or in_chrome(b):
            continue
        q = norm_ws(b.text()).rstrip("+\u2212- ").strip()
        if len(q) < 8 or q in seen_q:
            continue
        panel = b.next_element_sibling()
        a = norm_ws(panel.text()) if panel else ""
        if not a:
            a = faq_answer_from_flight(flight, q)
        if not a:  # a sub-menu toggle (Melcon's "Products"), not a question
            continue
        seen_q.add(q)
        faqs.append({"q": q, "a": a})

    lines: list[str] = []
    seen: set[str] = set()
    for line in main.text().split("\n"):
        line = norm_ws(line)
        if not line or line in seen or ZERO_COUNTER.match(line):
            continue
        seen.add(line)
        lines.append(line)

    page: dict[str, Any] = {
        "path": path,
        "title": title,
        "description": description,
        "headings": headings,
        "faqs": faqs,
        "stats": flight_stats(flight),
        "tables": flight_tables(flight),
        "text": "\n".join(lines),
        "sections": sections_of(main),
        "tabs": tabs_of(main),
        "documents": [],
    }
    return page, link_text, links


# --------------------------------------------------------------------------- documents


def is_product_pdf(p: str) -> bool:
    parts = p.split("/")
    return len(parts) > 2 and parts[2] in PRODUCT_DIRS


def doc_kind(p: str) -> str:
    low = p.lower()
    d = p.split("/")[2]
    if "epd" in low.rsplit("/", 1)[-1]:
        return "epd"
    if "warranty" in low:
        return "warranty"
    if d == "datasheets":
        return "datasheet"
    if d == "guides":
        return "guide"
    if d == "brochures":
        return "brochure"
    if d == "esg":
        return "policy"
    return "manual"


def title_from_filename(p: str) -> str:
    stem = p.rsplit("/", 1)[-1][:-4]
    stem = re.sub(r"[-_]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem[:1].upper() + stem[1:]


def clean_link_title(t: str) -> str:
    """A link's text as a title: the site appends "PDF · <note>" and uses "Download …" labels."""
    t = norm_ws(re.split(r"PDF(?:\s*·|$)", t)[0])
    if len(t) < 12 or "download" in t.lower():
        return ""
    return t


def slug(p: str) -> str:
    stem = p.rsplit("/", 1)[-1][:-4]
    return re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")


#: A page whose text layer yields fewer characters than this is OCR'd instead:
#: the outlined datasheets give 0 and the near-empty pages a stray label.
OCR_BELOW = 80
#: A datasheet page is also OCR'd, and the OCR kept, when it reads at least this
#: many times longer than the text layer: the G12R datasheet's layer carries its
#: numbers but draws every label as outlines (316 and 573 characters against
#: OCR's 1631 and 3252, measured 2026-10-14).
OCR_DATASHEET_GAIN = 2
OCR_DPI = 250
OCR_MIN_CONF = 30
POPPLER = shutil.which("pdftoppm") or "/opt/homebrew/bin/pdftoppm"
TESSERACT = shutil.which("tesseract") or "/opt/homebrew/bin/tesseract"


def ocr_page(data: bytes, n: int, *, refresh: bool) -> dict[str, Any] | None:
    """OCR page ``n`` of a PDF: ``{n, text, ocr: True, words: [[w, x0, y0, x1, y1]]}``.

    Coordinates are fractions of the rendered page, top-left origin. The result
    is cached by the PDF's hash, so a re-run is free; ``None`` when the tools are
    missing or the page reads as nothing.
    """
    key = hashlib.sha256(data).hexdigest()[:16]
    cached = CACHE / "ocr" / f"{key}-p{n}-{OCR_DPI}.json"
    if cached.exists() and not refresh:
        return json.loads(cached.read_text()) or None
    if not (Path(POPPLER).exists() and Path(TESSERACT).exists()):
        print(f"    page {n}: pdftoppm or tesseract missing, not OCR'd", file=sys.stderr)
        return None
    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "doc.pdf"
        pdf.write_bytes(data)
        prefix = Path(tmp) / "page"
        subprocess.run(
            [
                POPPLER,
                "-r",
                str(OCR_DPI),
                "-png",
                "-f",
                str(n),
                "-l",
                str(n),
                "-singlefile",
                pdf,
                prefix,
            ],
            check=True,
            capture_output=True,
        )
        tsv = subprocess.run(
            [TESSERACT, f"{prefix}.png", "-", "-l", "eng", "--psm", "3", "tsv"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    rows = [r.split("\t") for r in tsv.splitlines()[1:]]
    page_w = page_h = 0.0
    lines: dict[tuple[str, str, str], list[str]] = {}
    words: list[list[Any]] = []
    for r in rows:
        if len(r) < 12:
            continue
        level, _, block, par, line, _, left, top, width, height, conf, text = r[:12]
        if level == "1":
            page_w, page_h = float(width), float(height)
            continue
        if level != "5" or not text.strip() or float(conf) < OCR_MIN_CONF or not page_w:
            continue
        x0, y0 = float(left), float(top)
        words.append(
            [
                text.strip(),
                round(x0 / page_w, 4),
                round(y0 / page_h, 4),
                round((x0 + float(width)) / page_w, 4),
                round((y0 + float(height)) / page_h, 4),
            ]
        )
        lines.setdefault((block, par, line), []).append(text.strip())
    result = {
        "n": n,
        "text": "\n".join(" ".join(ws) for ws in lines.values()),
        "ocr": True,
        "words": words,
    }
    out = result if words else {}
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(out, ensure_ascii=False))
    return out or None


def read_pdf(
    data: bytes, *, refresh: bool = False, datasheet: bool = False
) -> tuple[list[dict], str]:
    """Each page's text in reading order, OCR for pages whose text layer is (near) empty."""
    import io

    from pypdf import PdfReader

    logging.getLogger("pypdf").setLevel(logging.ERROR)

    reader = PdfReader(io.BytesIO(data))
    pages: list[dict[str, Any]] = []
    for i, pg in enumerate(reader.pages, start=1):
        try:
            raw = pg.extract_text() or ""
        except Exception as e:
            raw = ""
            print(f"    page {i}: {e}", file=sys.stderr)
        lines = [norm_ws(x) for x in raw.split("\n")]
        text = "\n".join(x for x in lines if x)
        page: dict[str, Any] = {"n": i, "text": text}
        if len(text) < OCR_BELOW:
            page = ocr_page(data, i, refresh=refresh) or page
        elif datasheet:
            ocr = ocr_page(data, i, refresh=refresh)
            if ocr and len(ocr["text"]) >= OCR_DATASHEET_GAIN * len(text):
                page = ocr
        pages.append(page)
    ocred = [p["n"] for p in pages if p.get("ocr")]
    total = "".join(p["text"] for p in pages if not p.get("ocr"))
    notes = []
    if ocred:
        notes.append(f"OCR on pages {ocred}")
    if total.count("\ufffd") > 20 or len(re.findall(r"\(cid:\d+\)", total)) > 20:
        notes.append("text layer garbled (unmapped glyphs)")
    empty = [p["n"] for p in pages if not p["text"]]
    if empty:
        notes.append(f"pages without text: {empty}")
    return pages, "; ".join(notes)


# --------------------------------------------------------------------------- crawl


def crawl(offline: bool, refresh: bool) -> None:
    f = Fetcher(offline=offline, refresh=refresh)
    sm = f.get(SITEMAP, "sitemap")
    if sm is None:
        sys.exit("no sitemap (offline with an empty cache?)")
    paths = [site_path(u) for u in re.findall(r"<loc>([^<]+)</loc>", sm.decode())]

    pages: list[dict] = []
    raw_by_path: dict[str, str] = {}
    pdf_link_text: dict[str, str] = {}
    queue = list(dict.fromkeys(paths))
    done: set[str] = set()
    while queue:
        path = queue.pop(0)
        if path in done:
            continue
        done.add(path)
        data = f.get(SITE + (path if path != "/" else "/"), "pages")
        if data is None:
            continue
        raw = data.decode("utf-8", "replace")
        page, ltext, links = extract_page(path, raw)
        for k, v in ltext.items():
            pdf_link_text.setdefault(k, v)
        raw_by_path[path] = raw
        pages.append(page)
        print(f"page {path}: {len(page['headings'])}h {len(page['faqs'])}faq {len(page['text'])}ch")
        for link in links:
            if not link.startswith(SKIP_PREFIXES) and link not in done and link not in queue:
                queue.append(link)

    linked: dict[str, list[str]] = {}
    for page in pages:
        pdfs = find_pdfs(raw_by_path[page["path"]])
        page["documents"] = [SITE + urllib.parse.quote(p) for p in pdfs]
        for p in pdfs:
            linked.setdefault(p, []).append(page["path"])

    documents, investor = [], []
    notes: list[str] = []
    for p in sorted(linked):
        url = SITE + urllib.parse.quote(p)
        title = pdf_link_text.get(p) or title_from_filename(p)
        if not is_product_pdf(p):
            investor.append({"title": title, "url": url, "linked_from": linked[p]})
            continue
        data = f.get(url, "pdf")
        if data is None:
            notes.append(f"{p}: could not download")
            continue
        try:
            doc_pages, note = read_pdf(data, refresh=refresh, datasheet=doc_kind(p) == "datasheet")
        except Exception as e:
            notes.append(f"{p}: unreadable ({e})")
            continue
        if note:
            notes.append(f"{p}: {note}")
        print(f"pdf  {p}: {len(doc_pages)}pp {note}")
        documents.append(
            {
                "id": slug(p),
                "url": url,
                "title": title,
                "kind": doc_kind(p),
                "pages": doc_pages,
                "linked_from": linked[p],
            }
        )

    L3.mkdir(exist_ok=True)
    pages.sort(key=lambda x: x["path"])
    for name, obj in (("pages", pages), ("documents", documents), ("investor_documents", investor)):
        (L3 / f"{name}.json").write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n")
    print(f"\nwrote {L3}/pages.json, documents.json, investor_documents.json")
    for n in notes:
        print("note:", n)
    if f.misses:
        print("missing:", *f.misses, sep="\n  ")


# --------------------------------------------------------------------------- search

TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")
STOP = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "how",
        "i",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "the",
        "to",
        "what",
        "which",
        "with",
        "you",
        "your",
    ]
)


def tokens(s: str) -> list[str]:
    return [t for t in TOKEN.findall(s.lower()) if t not in STOP]


def search(query: str, pages: list[dict], documents: list[dict], limit: int = 8) -> list[dict]:
    """BM25 over passages: each page's FAQs, each page body, each PDF page.

    Returns ``[{score, kind: "page"|"faq"|"document", path|url, title, page?, snippet}]``.
    """
    units: list[tuple[dict, str]] = []
    for p in pages:
        head = f"{p['title']} {' '.join(p['headings'])}"
        units.append(
            ({"kind": "page", "path": p["path"], "title": p["title"]}, f"{head}\n{p['text']}")
        )
        for faq in p["faqs"]:
            units.append(
                ({"kind": "faq", "path": p["path"], "title": faq["q"]}, f"{faq['q']}\n{faq['a']}")
            )
    for d in documents:
        for pg in d["pages"]:
            meta = {"kind": "document", "url": d["url"], "title": d["title"], "page": pg["n"]}
            units.append((meta, f"{d['title']}\n{pg['text']}"))

    toks = [tokens(t) for _, t in units]
    n = len(units) or 1
    avg = sum(len(t) for t in toks) / n or 1
    df: Counter[str] = Counter()
    for t in toks:
        df.update(set(t))
    q = tokens(query)
    phrase = norm_ws(query.lower())
    k1, b = 1.4, 0.75
    scored = []
    for (meta, text), t in zip(units, toks, strict=False):
        if not t:
            continue
        tf = Counter(t)
        s = 0.0
        for w in q:
            if w in tf:
                idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
                s += idf * tf[w] * (k1 + 1) / (tf[w] + k1 * (1 - b + b * len(t) / avg))
        if s <= 0:
            continue
        flat = norm_ws(text)
        low = flat.lower()
        if phrase and phrase in low:
            s *= 1.5
        i = (
            low.find(phrase)
            if phrase in low
            else min((low.find(w) for w in q if w in low), default=0)
        )
        snippet = flat[max(0, i - 80) : i + 220]
        scored.append({"score": round(s, 2), **meta, "snippet": snippet})
    scored.sort(key=lambda r: -r["score"])
    return scored[:limit]


def load() -> tuple[list[dict], list[dict]]:
    pages = json.loads((L3 / "pages.json").read_text())
    documents = json.loads((L3 / "documents.json").read_text())
    return pages, documents


def main() -> None:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("crawl", help="fetch (or read from cache) and write L3/*.json")
    c.add_argument("--offline", action="store_true", help="cache only, no network")
    c.add_argument("--refresh", action="store_true", help="re-download everything")
    s = sub.add_parser("search", help="search L3 (no network)")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=8)
    args = ap.parse_args()
    if args.cmd == "crawl":
        crawl(args.offline, args.refresh)
    else:
        pages, documents = load()
        for r in search(args.query, pages, documents, args.limit):
            where = r.get("path") or f"{r['url']} p.{r['page']}"
            print(
                f"{r['score']:6.2f}  {r['kind']:8}  {where}\n        {r['title']}\n        {r['snippet']}\n"
            )


if __name__ == "__main__":
    main()
