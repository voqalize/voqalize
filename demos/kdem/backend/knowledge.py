"""What Aria may answer from: KDEM's approved pages, read the way a visitor sees
them, and the PDF documents those pages link to.

Six things live here, and each exists so the model never has to guess.

**The allowlist.** ``knowledge/approved_pages.json`` names every page Aria may
answer from, one canonical URL per topic, with the duplicates folded in as
aliases. KDEM reviews that file; this module only reads it, and refuses to start
on an entry that does not hold together (:class:`Allowlist`).

**The visible text.** A WordPress/Elementor page is mostly chrome: menus, a theme
header and footer, popups, per-breakpoint copies of each widget. :func:`extract`
keeps what a visitor reads in the page body and drops the rest, including any
element hidden or moved off-screen by its inline style, together with its whole
subtree. Text a visitor cannot see is not something Aria may say.

**Freshness.** :func:`refresh` reads ``wp-sitemap.xml`` and re-reads only what
changed: an approved page whose ``lastmod`` moved, a new page in a section that
is approved for automatic additions, nothing else. A new page anywhere else is
recorded in ``pending_review`` for a person, and a page gone from the sitemap, or
one the list no longer allows, is dropped.

**The documents.** Most of what KDEM publishes (policies, guidelines, reports,
newsletters) is a PDF, which the sitemap does not list. A PDF is found from the
links in the visible text of an approved page in a section that reads PDFs
(``read_pdfs``): on karnatakadigital.in, or over https on another site (a
government portal, say), and nothing past those links is followed. It is named
by its link text, streamed to disk, and read with :func:`read_pdf` in a child
process with a CPU, memory and wall-clock limit (:func:`read_pdf_isolated`),
page by page, so an answer can say "page 12". A page too heavy or too slow to
read is skipped and the rest are read; a long document is read a slice a night
from its first page, so its beginning is answerable first. A PDF is re-read only
when it changed (a conditional GET on its ETag and Last-Modified, and its
SHA-256), and dropped as soon as no approved page links to it. One that cannot
be read (encrypted, damaged, or scanned images with no text layer) is recorded
with the reason, not indexed; there is no OCR. One that failed is tried again
after a backoff, and all PDF text together is capped so a search stays inside
the tool budget.

**Search.** :class:`KnowledgeBase` is an in-memory BM25 index over the page and
PDF text, cut into passages; a PDF's passages keep their page number. It answers inside the tool budget because it never leaves
memory.

**The snapshot and its keeper.** The index is built from a snapshot on disk,
outside the repository (``KDEM_KNOWLEDGE_DIR``). :class:`KnowledgeService` loads
it in the background, refreshes it about once a day, keeps the last good copy
when a refresh fails, and never makes a session wait. With no snapshot and no
network the index is simply empty.

Run by hand (the urgent-change path), on each brains host, with the brain's own
``KDEM_KNOWLEDGE_DIR`` (or ``--cache-dir``) so the brain reads what it writes::

    uv run python demos/kdem/backend/knowledge.py refresh
    uv run python demos/kdem/backend/knowledge.py refresh --force https://karnatakadigital.in/policies/
    uv run python demos/kdem/backend/knowledge.py refresh --force https://karnatakadigital.in/wp-content/uploads/2026/01/policy.pdf
    uv run python demos/kdem/backend/knowledge.py search "seed fund for clusters"
    uv run python demos/kdem/backend/knowledge.py pending

This module imports nothing relative, so it runs as a script as well as inside
the brain package.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import heapq
import io
import ipaddress
import json
import logging
import math
import os
import random
import re
import shutil
import signal
import sys
import tempfile
import threading
import time
import unicodedata
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from array import array
from collections import Counter
from collections.abc import (
    Awaitable,
    Callable,
    Generator,
    Iterable,
    Iterator,
    Mapping,
    Sequence,
)
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import ClassVar, Literal, cast
from urllib.parse import quote, unquote, urljoin, urlsplit

import pypdf
from loguru import logger
from pypdf import PageObject, PdfReader, apply_configuration
from pypdf.errors import LimitReachedError
from pypdf.generic import ArrayObject, StreamObject

HOST = "karnatakadigital.in"
SITE = f"https://{HOST}"
USER_AGENT = "Mozilla/5.0 (compatible; VoqalizeKnowledge/1.0; +https://voqalize.com)"
FETCH_TIMEOUT_S = 45.0

ALLOWLIST_PATH = Path(__file__).resolve().parent / "knowledge" / "approved_pages.json"
SNAPSHOT_FILE = "snapshot.json"
SNAPSHOT_VERSION = 2
"""2 added PDFs. A version 1 snapshot still loads: its pages count as pages, and
the PDF links of each page that PDFs are found from are read on the next
refresh."""

ENV_DIR = "KDEM_KNOWLEDGE_DIR"
"""Where the snapshot lives. Defaults to :func:`default_cache_dir`."""
ENV_REFRESH = "KDEM_KNOWLEDGE_REFRESH"
"""``off`` keeps the background refresh from running; the snapshot is still read."""

REFRESH_EVERY_S = 24 * 3600
REFRESH_JITTER_S = 2 * 3600
RETRY_AFTER_S = 3600


def _fail(message: str) -> RuntimeError:
    return RuntimeError(f"kdem: {message}")


# ─── URLs ─────────────────────────────────────────────────────────────────────


def normalize(url: str, *, base: str = SITE) -> str | None:
    """The one spelling of a site URL: ``https://karnatakadigital.in/<path>/``.

    Relative URLs resolve against ``base``. The scheme becomes https, ``www.`` is
    dropped, the query and fragment go, and a path gets its trailing slash unless
    its last segment is a file (``.pdf``). The path keeps the escapes it arrived
    with, in upper case; a raw space or non-ASCII letter is escaped, an escaped
    dot is a dot, and ``.``/``..`` segments are resolved (RFC 3986), so no
    spelling of a path reaches outside the directory it names. ``None`` for
    anything off the site, and for a path with an escaped ``/`` or ``\\``."""
    try:
        # An escaped dot is a dot (RFC 3986: unreserved), before ".." is resolved.
        parts = urlsplit(urljoin(base, _unescape_unreserved(url.strip())))
    except ValueError:
        return None
    if parts.scheme not in ("http", "https"):
        return None
    host = (parts.hostname or "").lower().rstrip(".")
    host = host.removeprefix("www.")
    if host != HOST:
        return None
    path = _clean_path(parts.path or "/")
    if path is None:
        return None
    last = path.rsplit("/", 1)[-1]
    if last and "." not in last:
        path += "/"
    return f"{SITE}{path}"


def pdf_url(url: str, *, base: str = SITE) -> str | None:
    """The one spelling of a PDF's URL, on this site or on another.

    On karnatakadigital.in it is :func:`normalize`'s. On any other host only
    https is followed; the host is lower-cased, the query and fragment go, and
    the path is cleaned as :func:`normalize` cleans it. ``None`` for anything
    that is not a ``.pdf``, an off-site link over plain http, one with a user
    name or an unusual port, and a path with an escaped separator. Off-site HTML
    pages stay ``None`` in :func:`normalize`: only a PDF is ever read from
    another site."""
    here = normalize(url, base=base)
    if here is not None:
        return here if is_pdf(here) else None
    try:
        parts = urlsplit(urljoin(base, _unescape_unreserved(url.strip())))
        port = parts.port
    except ValueError:
        return None
    if parts.scheme != "https" or "@" in parts.netloc or port not in (None, 443):
        return None
    host = _public_host(
        parts.netloc.rsplit(":", 1)[0] if port or parts.netloc.endswith(":") else parts.netloc
    )
    path = _clean_path(parts.path or "/")
    if host is None or path is None or not path.lower().endswith(".pdf"):
        return None
    return f"https://{host}{path}"


_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")
_PRIVATE_SUFFIXES = frozenset(
    {"internal", "local", "localhost", "localdomain", "lan", "home", "intranet", "corp", "arpa"}
)


def _public_host(raw: str) -> str | None:
    """A host name that is plainly a public site, lower-cased and in punycode;
    ``None`` for anything that could reach the brain's own network: an IP
    address in any spelling (``127.0.0.1``, ``2130706433``, ``0x7f.1``,
    ``[::1]``), a single-label name (``localhost``), a private suffix
    (``.internal``, ``.local``), or a name that is not well formed."""
    host = raw.rstrip(".").lower()
    if not host or not host.isprintable() or any(c in host for c in "[]: \\%"):
        return None
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return None
    labels = host.split(".")
    if len(labels) < 2 or not all(_LABEL.match(label) for label in labels):
        return None
    tld = labels[-1]
    if tld in _PRIVATE_SUFFIXES or not (tld.isalpha() or tld.startswith("xn--")):
        return None  # a numeric last label is an IP address however it is spelled
    with contextlib.suppress(ValueError):
        ipaddress.ip_address(host)
        return None
    return host


def host_of(url: str) -> str:
    """``https://karnataka.gov.in/x.pdf`` → ``karnataka.gov.in``."""
    return (urlsplit(url).hostname or "").lower()


def off_site(url: str) -> bool:
    return host_of(url) != HOST


_ESCAPE = re.compile(r"%[0-9a-fA-F]{2}")
_UNRESERVED = re.compile(
    r"%(3[0-9]|4[1-9a-fA-F]|5[0-9aA]|6[1-9a-fA-F]|7[0-9aA]|2[dDeE]|5[fF]|7[eE])"
)


def _unescape_unreserved(url: str) -> str:
    """Decode the escapes of unreserved characters (letters, digits, ``-._~``):
    RFC 3986 says ``%77p%2Dcontent`` is ``wp-content``, so it is matched, and
    stored, as that. ``%2E%2E`` becomes ``..`` before dot segments are removed.
    Reserved characters (``%2F`` above all) stay escaped."""
    return _UNRESERVED.sub(lambda m: chr(int(m.group(1), 16)), url)


def _clean_path(raw: str) -> str | None:
    path = raw if raw.startswith("/") else "/" + raw
    # Escape what may not appear raw (a space, a non-ASCII letter, a stray %),
    # keep every escape as it came, and spell its hex one way.
    path = quote(path, safe="/%!$&'()*+,;=:@~")
    path = re.sub(r"%(?![0-9a-fA-F]{2})", "%25", path)
    path = _ESCAPE.sub(lambda m: m.group().upper(), path)
    if "%2F" in path or "%5C" in path or re.search(r"%[01][0-9A-F]|%7F", path):
        return None  # an escaped separator or control character: never a real name
    path = _remove_dot_segments(re.sub(r"/{2,}", "/", path))
    if ".." in path.split("/"):
        return None
    return path


def _remove_dot_segments(path: str) -> str:
    """RFC 3986 section 5.2.4, for an absolute path: ``/a/./b/../c`` → ``/a/c``.
    A ``..`` above the root stays at the root."""
    segments = path.split("/")[1:]
    out: list[str] = []
    for seg in segments:
        if seg == "..":
            if out:
                out.pop()
        elif seg != ".":
            out.append(seg)
    if segments and segments[-1] in (".", ".."):
        out.append("")
    return "/" + "/".join(out)


def path_of(url: str) -> str:
    """``https://karnatakadigital.in/a/b/`` → ``/a/b/``."""
    return url[len(SITE) :] if url.startswith(SITE) else urlsplit(url).path


# ─── The allowlist ────────────────────────────────────────────────────────────


Origin = Literal["approved", "auto"]
"""``approved``: a page on the allowlist. ``auto``: a page or PDF a refresh added."""

Kind = Literal["page", "pdf"]
"""``page``: an HTML page from the sitemap. ``pdf``: a PDF an approved page links to."""


def is_pdf(url: str) -> bool:
    return path_of(url).lower().endswith(".pdf")


@dataclass(frozen=True)
class Section:
    name: str
    approved: bool
    auto_add: bool
    post_types: tuple[str, ...]
    """The WordPress post types whose sitemaps list this section's pages."""
    notes: str = ""
    read_pdfs: bool = False
    """The PDFs its approved pages link to are read and answered from."""


@dataclass(frozen=True)
class ApprovedPage:
    url: str
    title: str
    section: str
    aliases: tuple[str, ...] = ()
    hub_for: str | None = None
    """A new page this page links to is added to that section, when the section
    is approved for automatic additions."""


@dataclass(frozen=True)
class _Rule:
    pattern: re.Pattern[str]
    why: str


@dataclass(frozen=True)
class Allowlist:
    """The curated page list, its section policy, and the URL rules."""

    pages: tuple[ApprovedPage, ...]
    sections: dict[str, Section]
    excluded: tuple[_Rule, ...]
    held: tuple[_Rule, ...]
    sitemap_url: str
    contact_url: str
    by_url: dict[str, ApprovedPage] = field(init=False)
    _alias: dict[str, str] = field(init=False)
    _section_of_type: dict[str, str] = field(init=False)

    def __post_init__(self) -> None:
        by_url: dict[str, ApprovedPage] = {}
        alias: dict[str, str] = {}
        for page in self.pages:
            if page.url in by_url:
                raise _fail(f"{page.url} is listed twice")
            by_url[page.url] = page
        for page in self.pages:
            for a in page.aliases:
                if a in by_url or a in alias:
                    raise _fail(f"alias {a} is already a page or another page's alias")
                alias[a] = page.url
        type_section: dict[str, str] = {}
        for s in self.sections.values():
            for t in s.post_types:
                if t == "page":
                    continue
                if t in type_section:
                    raise _fail(f"post type {t!r} is in two sections")
                type_section[t] = s.name
        object.__setattr__(self, "by_url", by_url)
        object.__setattr__(self, "_alias", alias)
        object.__setattr__(self, "_section_of_type", type_section)
        self._check()

    def _check(self) -> None:
        for page in self.pages:
            if normalize(page.url) != page.url:
                raise _fail(f"{page.url} is not in canonical form ({normalize(page.url)})")
            section = self.sections.get(page.section)
            if section is None or not section.approved:
                raise _fail(f"{page.url} is in {page.section!r}, which is not an approved section")
            if self.is_excluded(page.url):
                raise _fail(f"{page.url} is approved and also matches an excluded pattern")
            for a in page.aliases:
                if normalize(a) != a:
                    raise _fail(f"alias {a} of {page.url} is not in canonical form")
            if page.hub_for is not None:
                target = self.sections.get(page.hub_for)
                if target is None or not (target.approved and target.auto_add):
                    raise _fail(
                        f"{page.url} is a hub for {page.hub_for!r}, not an auto-add section"
                    )
        for s in self.sections.values():
            if s.read_pdfs and not s.approved:
                raise _fail(f"section {s.name!r} reads PDFs but is not approved")
        if normalize(self.contact_url) not in self.by_url:
            raise _fail("the contact page must be an approved page")

    # ── Loading ──────────────────────────────────────────────────────────

    @classmethod
    def load(cls, path: Path = ALLOWLIST_PATH) -> Allowlist:
        try:
            raw: object = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise _fail(f"cannot read {path.name}: {e}") from e
        return cls.from_json(raw)

    @classmethod
    def from_json(cls, raw: object) -> Allowlist:
        doc = _obj(raw, "approved_pages.json")
        sections: dict[str, Section] = {}
        for name, value in _obj(doc.get("sections"), "sections").items():
            s = _obj(value, f"sections.{name}")
            sections[name] = Section(
                name=name,
                approved=_bool(s, "approved"),
                auto_add=_bool(s, "auto_add"),
                post_types=tuple(_strs(s.get("post_types"), f"sections.{name}.post_types")),
                notes=_str(s, "notes", default=""),
                read_pdfs=s.get("read_pdfs") is True,
            )
        pages: list[ApprovedPage] = []
        for i, value in enumerate(_list(doc.get("pages"), "pages")):
            p = _obj(value, f"pages[{i}]")
            hub = p.get("hub_for")
            pages.append(
                ApprovedPage(
                    url=_str(p, "url"),
                    title=_str(p, "title"),
                    section=_str(p, "section"),
                    aliases=tuple(_strs(p.get("aliases", []), f"pages[{i}].aliases")),
                    hub_for=hub if isinstance(hub, str) else None,
                )
            )
        return cls(
            pages=tuple(pages),
            sections=sections,
            excluded=_rules(doc.get("excluded_patterns", []), "excluded_patterns"),
            held=_rules(doc.get("held_patterns", []), "held_patterns"),
            sitemap_url=_str(doc, "sitemap"),
            contact_url=_str(doc, "contact_url"),
        )

    # ── Asking it ────────────────────────────────────────────────────────

    def canonical(self, url: str) -> str | None:
        """``url`` normalized, with an alias folded into its canonical page.
        ``None`` for anything off the site."""
        n = normalize(url)
        if n is None:
            return None
        return self._alias.get(n, n)

    def approved(self, url: str) -> ApprovedPage | None:
        """The approved page ``url`` (or one of its aliases) names, if any."""
        c = self.canonical(url)
        return self.by_url.get(c) if c is not None else None

    def locate(self, url: str) -> str | None:
        """The canonical URL of a page on the site (aliases folded), or of a PDF
        on any site (:func:`pdf_url`). ``None`` for anything else."""
        return self.canonical(url) or pdf_url(url)

    def is_alias(self, url: str) -> bool:
        n = normalize(url)
        return n is not None and n in self._alias

    def is_excluded(self, url: str) -> bool:
        return any(_matches(r, url) for r in self.excluded)

    def held_reason(self, url: str) -> str | None:
        """Why a new flat page or a PDF is held for a person even when a hub links
        to it."""
        return next((r.why for r in self.held if _matches(r, url)), None)

    def refusal(self, url: str, origin: Origin, section: str, kind: Kind = "page") -> str | None:
        """Why the list, as it stands now, no longer allows a stored page or PDF;
        ``None`` when it does. A snapshot is checked against this on every load and every
        refresh, so a change to the list takes effect without waiting for the
        site to change.

        An approved page must still be on the list. A page a refresh added must
        still be in a section that is approved for automatic additions, and a flat
        page must not have since matched a held pattern. A PDF must be in a
        section that still reads PDFs and match no held pattern; whether an
        approved page still links to it is the index's question
        (:func:`linked_pdfs`)."""
        if self.is_excluded(url):
            return "matches an excluded pattern"
        if self.is_alias(url):
            return "is an alias of an approved page"
        if kind == "pdf":
            s = self.sections.get(section)
            if s is None or not s.approved:
                return f"section {section!r} is not approved"
            if not s.read_pdfs:
                return f"section {section!r} does not read PDFs"
            return self.held_reason(url)
        if url in self.by_url:
            return None
        if origin != "auto":
            return "is no longer on the approved list"
        s = self.sections.get(section)
        if s is None or not s.approved:
            return f"section {section!r} is not approved"
        if not s.auto_add:
            return f"section {section!r} does not take new pages automatically"
        if "page" in s.post_types and (why := self.held_reason(url)):
            return why
        return None

    def permits(self, page: StoredPage) -> bool:
        """Whether Aria may still answer from, and link to, a stored page."""
        return self.refusal(page.url, page.origin, page.section, page.kind) is None

    def section_of_type(self, post_type: str) -> str | None:
        """The section a non-page post type belongs to. Pages are flat-slugged, so
        their section comes from the hub that links to them, not from here."""
        return self._section_of_type.get(post_type)

    @property
    def hubs(self) -> dict[str, str]:
        """Approved hub URL → the section its new links are added to."""
        return {p.url: p.hub_for for p in self.pages if p.hub_for is not None}

    @property
    def pdf_sources(self) -> tuple[ApprovedPage, ...]:
        """The approved pages whose PDF links are read, in list order: every
        approved page in a section that reads PDFs."""
        return tuple(p for p in self.pages if self.sections[p.section].read_pdfs)


def _matches(rule: _Rule, url: str) -> bool:
    """A rule matches the path as written or lower-cased: slugs are lower case,
    but an uploaded file keeps the capitals it was given (``Speaker-List.PDF``)."""
    path = path_of(url)
    return bool(rule.pattern.search(path) or rule.pattern.search(path.lower()))


def _obj(v: object, where: str) -> dict[str, object]:
    if not isinstance(v, dict):
        raise _fail(f"{where} must be an object")
    return cast("dict[str, object]", v)


def _list(v: object, where: str) -> list[object]:
    if not isinstance(v, list):
        raise _fail(f"{where} must be a list")
    return cast("list[object]", v)


def _strs(v: object, where: str) -> list[str]:
    items = _list(v, where)
    if not all(isinstance(x, str) for x in items):
        raise _fail(f"{where} must be a list of strings")
    return cast("list[str]", items)


def _str(d: dict[str, object], key: str, *, default: str | None = None) -> str:
    v = d.get(key, default)
    if not isinstance(v, str):
        raise _fail(f"{key!r} must be a string")
    return v


def _bool(d: dict[str, object], key: str) -> bool:
    v = d.get(key)
    if not isinstance(v, bool):
        raise _fail(f"{key!r} must be true or false")
    return v


def _int(d: dict[str, object], key: str) -> int:
    v = d.get(key, 0)
    return v if isinstance(v, int) and not isinstance(v, bool) else 0


def _pairs(v: object, where: str) -> tuple[tuple[str, str], ...]:
    out: list[tuple[str, str]] = []
    for item in _list(v, where):
        pair = _strs(item, where)
        if len(pair) != 2:
            raise _fail(f"{where} must be a list of [url, text] pairs")
        out.append((pair[0], pair[1]))
    return tuple(out)


def _rules(v: object, where: str) -> tuple[_Rule, ...]:
    rules: list[_Rule] = []
    for i, item in enumerate(_list(v, where)):
        r = _obj(item, f"{where}[{i}]")
        try:
            pattern = re.compile(_str(r, "pattern"))
        except re.error as e:
            raise _fail(f"{where}[{i}] is not a valid pattern: {e}") from e
        rules.append(_Rule(pattern, _str(r, "why", default="")))
    return tuple(rules)


# ─── Visible text ─────────────────────────────────────────────────────────────


def _words(s: str) -> frozenset[str]:
    return frozenset(s.split())


_VOID = _words("area base br col embed hr img input keygen link meta param source track wbr")
_DROP_TAGS = _words(
    "head title script style noscript template svg math iframe object embed canvas video "
    "audio form button select textarea option label link meta header footer nav aside "
    "dialog"
)
_DROP_CLASSES = _words(
    "elementor-location-header elementor-location-footer elementor-location-popup "
    "elementor-nav-menu elementor-nav-menu--dropdown elementor-menu-toggle "
    "screen-reader-text ast-breadcrumbs comments-area elementor-share-buttons "
    "post-navigation elementor-hidden-desktop skip-link"
)
_DROP_IDS = frozenset({"comments", "respond"})
_DROP_ELEMENTOR_TYPES = frozenset({"header", "footer", "popup"})
_BLOCK_TAGS = _words(
    "address article blockquote body br dd details div dl dt figcaption figure h1 h2 "
    "h3 h4 h5 h6 hr li main ol p pre section summary table tbody td tfoot th thead tr "
    "ul"
)
_CHROME_LINES = frozenset(
    s.casefold()
    for s in (
        "+ Add to Google Calendar",
        "+ iCal / Outlook export",
        "iCal / Outlook export",
        "Share this event",
        "Powered by Modern Events Calendar",
        "View Article",
        "Read More",
        "Read more",
        "Skip to content",
    )
)
_FAR_PX = 1000.0


class _Node:
    __slots__ = ("attrs", "children", "tag")

    def __init__(self, tag: str, attrs: dict[str, str]) -> None:
        self.tag = tag
        self.attrs = attrs
        self.children: list[_Node | str] = []

    def elements(self) -> Iterable[_Node]:
        return (c for c in self.children if isinstance(c, _Node))


class _TreeBuilder(HTMLParser):
    """A forgiving DOM, built the way a browser would build it: unmatched end tags
    are ignored, void elements never open, an open ``p``/``li``/cell is closed by
    the next one, and a whole document pasted into an HTML widget does not open a
    second ``html``/``head``/``body`` (its head's contents land in the body)."""

    _IMPLIED: ClassVar[dict[str, tuple[str, ...]]] = {
        "p": ("p",),
        "li": ("li",),
        "td": ("td", "th"),
        "th": ("td", "th"),
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("#document", {})
        self.stack: list[_Node] = [self.root]

    def _in(self, tag: str) -> bool:
        return any(n.tag == tag for n in self.stack)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("html", "head", "body") and self._in("body"):
            return
        if tag == "body" and self._in("head"):
            self.handle_endtag("head")
        closes = self._IMPLIED.get(tag)
        if closes and self.stack[-1].tag in closes:
            self.stack.pop()
        if tag == "tr":
            while len(self.stack) > 1 and self.stack[-1].tag in ("td", "th", "tr"):
                self.stack.pop()
        node = _Node(tag, {k.lower(): (v or "") for k, v in attrs})
        self.stack[-1].children.append(node)
        if tag not in _VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag, {k.lower(): (v or "") for k, v in attrs})
        self.stack[-1].children.append(node)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("html", "body") or (tag == "head" and self._in("body")):
            return
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def _style(value: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for decl in value.split(";"):
        name, sep, val = decl.partition(":")
        if sep:
            val = val.lower().replace("!important", "").strip()
            out[name.strip().lower()] = re.sub(r"\s+", " ", val)
    return out


def _length(value: str) -> float | None:
    """A CSS length in px, for the absolute units an offset is written in."""
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)(px|em|rem|pt)?", value.strip())
    if not m:
        return None
    n = float(m.group(1))
    return n * {"em": 16.0, "rem": 16.0, "pt": 4 / 3}.get(m.group(2) or "px", 1.0)


def _is_zero(value: str) -> bool:
    n = _length(value)
    return n is not None and n == 0


def _far(value: str, *, relative: bool = True) -> bool:
    """An offset that puts an element a screen or more away: 1000px or more either
    way, or a whole viewport (``vw``/``vh``) or a whole containing block (``%``,
    when ``relative`` — a translate's percentage is of the element itself, so it
    is not counted there)."""
    v = value.strip()
    if (n := _length(v)) is not None:
        return abs(n) >= _FAR_PX
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)(vw|vh|vmin|vmax|%)", v)
    if not m or (m.group(2) == "%" and not relative):
        return False
    return abs(float(m.group(1))) >= 100


def _transparent(color: str) -> bool:
    if color == "transparent":
        return True
    m = re.fullmatch(r"(?:rgba|hsla)\((.*)\)", color)
    if m is None:
        return False
    alpha = re.split(r"[,/\s]+", m.group(1).strip())[-1]
    with contextlib.suppress(ValueError):
        return float(alpha.rstrip("%")) == 0
    return False


_TRANSLATE = re.compile(r"translate(?:3d|x|y|z)?\(([^)]*)\)")


def _hidden_by_style(style: dict[str, str]) -> bool:
    """True when an inline style keeps the element from being seen: not displayed,
    invisible, transparent, zero-sized or clear text, clipped or collapsed away,
    or moved a screen or more away by position, margin or transform."""
    if style.get("display") == "none":
        return True
    if style.get("visibility") in ("hidden", "collapse"):
        return True
    opacity = style.get("opacity")
    if opacity is not None:
        with contextlib.suppress(ValueError):
            if float(opacity) == 0:
                return True
    if "font-size" in style and _is_zero(style["font-size"]):
        return True
    if _transparent(style.get("color", "")):
        return True
    clip = style.get("clip", "")
    if clip.startswith("rect("):
        sizes = [_length(x) for x in re.split(r"[,\s]+", clip[5:].rstrip(")").strip()) if x]
        if sizes and all(s is not None and abs(s) <= 1 for s in sizes):
            return True
    clipped = {style.get(k) for k in ("overflow", "overflow-x", "overflow-y")} & {"hidden", "clip"}
    if clipped and any(
        (n := _length(style.get(k, ""))) is not None and n <= 1
        for k in ("height", "width", "max-height", "max-width")
    ):
        return True
    # A margin moves the element whatever its position; only the pull up or to
    # the left takes it off the page.
    for k in ("margin-left", "margin-top", "margin"):
        if any((n := _length(v)) is not None and n <= -_FAR_PX for v in style.get(k, "").split()):
            return True
    if style.get("position") in ("absolute", "fixed"):
        sides = ("top", "left", "right", "bottom", "inset")
        if any(_far(v) for k in sides for v in style.get(k, "").split()):
            return True
    return any(
        _far(arg, relative=False)
        for m in _TRANSLATE.finditer(style.get("transform", ""))
        for arg in m.group(1).split(",")
    ) or ((n := _length(style.get("text-indent", ""))) is not None and n <= -_FAR_PX)


def _dropped(node: _Node) -> bool:
    if node.tag in _DROP_TAGS:
        return True
    a = node.attrs
    if "hidden" in a or a.get("aria-hidden", "").lower() == "true":
        return True
    if a.get("type", "").lower() == "hidden":
        return True
    if a.get("data-elementor-type", "").lower() in _DROP_ELEMENTOR_TYPES:
        return True
    if a.get("id", "") in _DROP_IDS:
        return True
    if _DROP_CLASSES.intersection(a.get("class", "").split()):
        return True
    style = a.get("style")
    return bool(style) and _hidden_by_style(_style(style or ""))


def _find(node: _Node, pred: Callable[[_Node], bool]) -> _Node | None:
    """The first element under ``node``, in document order, that ``pred`` accepts."""
    stack: list[_Node] = [node]
    while stack:
        n = stack.pop()
        if pred(n):
            return n
        stack.extend(reversed(list(n.elements())))
    return None


def _clean(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def _lines(node: _Node) -> list[str]:
    """The visible text under ``node``, a line per block, chrome lines dropped."""
    lines: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        text = _clean("".join(buf))
        buf.clear()
        if text and text.casefold() not in _CHROME_LINES:
            lines.append(text)

    def walk(n: _Node) -> None:
        for c in n.children:
            if isinstance(c, str):
                buf.append(c)
            elif _dropped(c):
                continue
            elif (to := c.attrs.get("data-to-value")) is not None:
                # An animated counter renders "0" until a script counts it up;
                # the number it stops at is the one a visitor reads.
                buf.append(f" {to} ")
            else:
                block = c.tag in _BLOCK_TAGS
                if block:
                    flush()
                walk(c)
                if block:
                    flush()
                elif c.tag in ("td", "th", "span", "a"):
                    buf.append(" ")

    walk(node)
    flush()
    return lines


_GENERIC_LINK_TEXT = frozenset(
    s.casefold()
    for s in (
        "Download",
        "Download PDF",
        "Download Now",
        "Download Here",
        "Click Here",
        "Click to Download",
        "Here",
        "View",
        "View PDF",
        "View More",
        "View Details",
        "PDF",
        "Open",
        "Read",
        "Read More",
        "Know More",
        "Learn More",
    )
)
"""Link text that names nothing: a PDF linked only like this is named by its own
metadata title or its file name instead."""


def _link_text(a: _Node) -> str:
    text = _clean(" ".join(_lines(a)))
    for candidate in (text, a.attrs.get("title", ""), a.attrs.get("aria-label", "")):
        candidate = _clean(candidate)
        if candidate and candidate.casefold().rstrip(" .:»>") not in _GENERIC_LINK_TEXT:
            return candidate[:_TITLE_CHARS]
    return ""


_HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})


def _links(node: _Node, base: str) -> tuple[list[str], list[tuple[str, str]]]:
    """Every on-site link in the visible body, normalized, and every on-site PDF
    link with the words that name it.

    A PDF is named by its link text. When that names nothing (an icon, "View
    More", "Download Now"), it is named by the heading just before it, the way a
    card shows a document's title above its button — but only when that heading
    leads to this one PDF and no other, so a section heading over a row of
    buttons names none of them. Otherwise the name is empty."""
    out: list[str] = []
    pdfs: dict[str, str] = {}
    heading = ""
    under: dict[str, list[str]] = {}  # heading text → the PDFs that follow it
    order: list[tuple[str, str]] = []  # (heading, PDF) in document order

    def walk(n: _Node) -> None:
        nonlocal heading
        for c in n.elements():
            if _dropped(c):
                continue
            if c.tag in _HEADINGS:
                heading = _clean(" ".join(_lines(c)))
                under.setdefault(heading, [])
            if c.tag == "a" and (href := c.attrs.get("href")):
                u = normalize(href, base=base)
                if u is not None:
                    out.append(u)
                else:
                    u = pdf_url(href, base=base)  # a PDF on another site: read, not crawled
                if u is not None and is_pdf(u):
                    if not pdfs.get(u):
                        pdfs[u] = _link_text(c)
                    if heading and u not in under[heading]:
                        under[heading].append(u)
                        order.append((heading, u))
            walk(c)

    walk(node)
    for h, u in order:
        if not pdfs[u] and under[h] == [u]:
            pdfs[u] = h
    return list(dict.fromkeys(out)), list(pdfs.items())


@dataclass(frozen=True)
class Extracted:
    """A page as a visitor reads it."""

    title: str
    blocks: tuple[str, ...]
    """The text of each top-level part of the page body, a line per paragraph.
    Kept apart so text repeated across pages (a shared footer band, a contact
    blurb) can be recognized and dropped when the index is built."""
    links: tuple[str, ...]
    """Every on-site link in the visible body, normalized."""
    pdf_links: tuple[tuple[str, str], ...] = ()
    """Every on-site PDF link in the visible body: its URL and its link text."""

    @property
    def text(self) -> str:
        return "\n".join(self.blocks)


def _title_from(doc: _Node, root: _Node) -> str:
    h1 = _find(root, lambda n: n.tag == "h1" and not _dropped(n))
    if h1 is not None and (t := " ".join(_lines(h1))):
        return t
    title = _find(doc, lambda n: n.tag == "title")
    if title is not None:
        text = _clean("".join(c for c in title.children if isinstance(c, str)))
        return re.split(r"\s+[-|\u2013\u2014]\s+", text)[0] if text else ""
    return ""


def extract(html: str, *, url: str = SITE + "/") -> Extracted:
    """The visible text of a WordPress/Elementor page.

    The body root is the first of ``main#main``, the Elementor page document
    (``[data-elementor-type=wp-page]``), ``#content`` and ``body``. Under it,
    every subtree that a visitor does not read is dropped: scripts and styles,
    forms, the theme header/footer/nav, popups, screen-reader-only text, the
    tablet and mobile copies of a widget, and any element that is hidden or moved
    off-screen by its inline style."""
    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()
    doc = builder.root

    def is_root(n: _Node) -> bool:
        return n.tag == "main" and n.attrs.get("id") == "main"

    root = (
        _find(doc, is_root)
        or _find(doc, lambda n: n.attrs.get("data-elementor-type") == "wp-page")
        or _find(doc, lambda n: n.attrs.get("id") == "content")
        or _find(doc, lambda n: n.tag == "body")
        or doc
    )
    if _dropped(root):
        return Extracted(title="", blocks=(), links=(), pdf_links=())
    # Wrappers with a single visible child say nothing; the parts are below them.
    while True:
        kids = [c for c in root.elements() if not _dropped(c)]
        own_text = any(isinstance(c, str) and c.strip() for c in root.children)
        if len(kids) != 1 or own_text:
            break
        root = kids[0]
    blocks: list[str] = []
    seen: set[str] = set()
    for c in root.children:
        if isinstance(c, str):
            lines = [t] if (t := _clean(c)) else []
        elif _dropped(c):
            continue
        else:
            wrapper = _Node("#part", {})
            wrapper.children.append(c)
            lines = _lines(wrapper)
        kept = [ln for ln in lines if ln not in seen]
        seen.update(kept)
        if kept:
            blocks.append("\n".join(kept))
    links, pdf_links = _links(root, url)
    return Extracted(
        title=_title_from(doc, root),
        blocks=tuple(blocks),
        links=tuple(links),
        pdf_links=tuple(pdf_links),
    )


# ─── The sitemap ──────────────────────────────────────────────────────────────

_SM = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
_SUB_SITEMAP = re.compile(r"/wp-sitemap-(posts|taxonomies|users)-([^/]+?)-\d+\.xml$")


@dataclass(frozen=True)
class SitemapEntry:
    url: str
    lastmod: str
    post_type: str


@dataclass(frozen=True)
class FetchResult:
    status: int
    url: str
    """Where the request ended up, after redirects."""
    body: str
    headers: Mapping[str, str] = field(default_factory=dict[str, str])
    """The response headers, names lower-cased. Only :data:`FetchFile` fills them."""
    size: int = 0
    """A file's body: how many bytes were written to its destination."""
    sha256: str = ""
    """A file's body: its SHA-256, hex. It tells a file that changed from one
    that did not when the server's own validators cannot."""


Fetch = Callable[[str], Awaitable[FetchResult]]
"""Fetch one URL. A 4xx/5xx answer is a result, not an exception; a network
failure raises."""

FetchFile = Callable[[str, Mapping[str, str], int, Path], Awaitable[FetchResult]]
"""Fetch one file: ``(url, request headers, max bytes, destination)``. A 200
answer's body is streamed to ``destination`` on disk, never held in memory, and
the result carries the response headers, the size and the SHA-256; any other
answer (a 304 to a conditional request, say) writes nothing. A file larger than
``max bytes`` raises :class:`TooLarge` (from its Content-Length when it gives
one, else once that many bytes have been read); a network failure raises."""


class TooLarge(Exception):
    """A file over the size limit. Carries the response headers, so the next run
    can ask whether it changed without downloading it again."""

    def __init__(self, size: int, headers: Mapping[str, str]) -> None:
        super().__init__(f"{size} bytes or more")
        self.size = size
        self.headers = dict(headers)


class SitemapError(RuntimeError):
    pass


REDIRECTS = frozenset({301, 302, 303, 307, 308})


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Redirects are not followed. The answer comes back as a result whose
    ``url`` is where it points, and the refresh decides: the same page or PDF
    under another spelling is asked for again; anything else is a page that
    moved, judged without its body ever being downloaded."""

    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _http_error(e: urllib.error.HTTPError, url: str) -> FetchResult:
    headers = {k.lower(): v for k, v in e.headers.items()}
    if e.code in REDIRECTS and (to := headers.get("location")):
        return FetchResult(e.code, urljoin(url, to), "", headers)
    return FetchResult(e.code, url, "", headers)


def _download(url: str) -> FetchResult:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with _OPENER.open(req, timeout=FETCH_TIMEOUT_S) as resp:
            raw: bytes = resp.read()
            charset = resp.headers.get_content_charset() or "utf-8"
            return FetchResult(resp.status, resp.geturl(), raw.decode(charset, "replace"))
    except urllib.error.HTTPError as e:
        if e.code in REDIRECTS:
            return _http_error(e, url)
        try:
            body = e.read().decode("utf-8", "replace")
        except OSError:
            body = ""
        return FetchResult(e.code, url, body)


async def http_fetch(url: str) -> FetchResult:
    """The real fetcher: stdlib, off the event loop."""
    return await asyncio.to_thread(_download, url)


_FILE_CHUNK = 256 * 1024
_FILE_DOWNLOAD_S = 600.0
"""The longest one file may take to download; the socket timeout bounds each read."""


def _download_file(
    url: str,
    headers: Mapping[str, str],
    max_bytes: int,
    dest: Path,
    stop: threading.Event | None = None,
) -> FetchResult:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **headers})
    try:
        with _OPENER.open(req, timeout=FETCH_TIMEOUT_S) as resp:
            got = {k.lower(): v for k, v in resp.headers.items()}
            length = got.get("content-length", "")
            if length.isdigit() and int(length) > max_bytes:
                raise TooLarge(int(length), got)
            deadline = time.monotonic() + _FILE_DOWNLOAD_S
            digest = hashlib.sha256()
            size = 0
            with dest.open("wb") as out:
                while chunk := resp.read(_FILE_CHUNK):
                    size += len(chunk)
                    if size > max_bytes:
                        raise TooLarge(size, got)
                    if time.monotonic() > deadline:
                        raise TimeoutError(f"{url} took too long to download")
                    if stop is not None and stop.is_set():
                        raise TimeoutError(f"{url}: the download was called off")
                    digest.update(chunk)
                    out.write(chunk)
            return FetchResult(resp.status, resp.geturl(), "", got, size, digest.hexdigest())
    except urllib.error.HTTPError as e:
        # urllib answers a 304, and a redirect it is not to follow, with an
        # HTTPError too: each is a result, not a failure.
        return _http_error(e, url)


async def http_fetch_file(
    url: str, headers: Mapping[str, str], max_bytes: int, dest: Path
) -> FetchResult:
    """The real file fetcher: stdlib, off the event loop, size-limited, streamed
    to disk. Called off (cancelled), it stops the download at the next chunk
    rather than leaving a thread writing on."""
    stop = threading.Event()
    try:
        return await asyncio.to_thread(_download_file, url, headers, max_bytes, dest, stop)
    finally:
        stop.set()


def _parse_xml(body: str, where: str) -> ET.Element:
    try:
        return ET.fromstring(body.encode("utf-8"))
    except ET.ParseError as e:
        raise SitemapError(f"{where} is not XML: {e}") from e


def _sitemap_xml(got: FetchResult, kind: str) -> ET.Element:
    """The sitemap document in ``got``. Some of the site's sitemap files answer
    404 with the full sitemap as the body, so the body decides, not the status:
    a document of the expected kind is accepted, anything else raises."""
    if got.status != 200 and not got.body.lstrip().startswith("<?xml"):
        raise SitemapError(f"{got.url} answered {got.status}")
    root = _parse_xml(got.body, got.url)
    if root.tag != f"{_SM}{kind}":
        raise SitemapError(f"{got.url} answered {got.status} without a {kind}")
    return root


async def read_sitemap(fetch: Fetch, index_url: str) -> dict[str, SitemapEntry]:
    """Every post-type URL the WordPress sitemap lists, with its ``lastmod``.

    Taxonomy and user sitemaps are skipped: archives carry no ``lastmod`` and are
    never read. Any failure raises, so a partial read can never look like a run of
    deleted pages."""

    def on_site(to: str) -> bool:
        return normalize(to) is not None

    index = await _follow(fetch, index_url, on_site)
    root = await asyncio.to_thread(_sitemap_xml, index, "sitemapindex")
    entries: dict[str, SitemapEntry] = {}
    for loc in root.iter(f"{_SM}loc"):
        sub = (loc.text or "").strip()
        m = _SUB_SITEMAP.search(sub)
        if not m or m.group(1) != "posts":
            continue
        post_type = m.group(2)
        urlset = await asyncio.to_thread(_sitemap_xml, await _follow(fetch, sub, on_site), "urlset")
        for item in urlset.iter(f"{_SM}url"):
            u = normalize((item.findtext(f"{_SM}loc") or "").strip())
            if u is not None:
                lastmod = (item.findtext(f"{_SM}lastmod") or "").strip()
                entries[u] = SitemapEntry(u, lastmod, post_type)
    if not entries:
        raise SitemapError(f"{index_url} listed no pages")
    return entries


# ─── PDF text ─────────────────────────────────────────────────────────────────

# pypdf reports every quirk of a malformed file on the logging module; a refresh
# records the files it could not read, and the rest is noise.
logging.getLogger("pypdf").setLevel(logging.ERROR)

_PDF_LINE_CHARS = 500
"""A PDF's text is cut into sentences, and a sentence longer than this is cut at
a space, so a passage never truncates one."""
_PDF_MIN_LETTERS_PER_PAGE = 20
"""Fewer letters than this per page, on average, is a scanned document: images
of pages, with at most a stamp or a page number as text."""
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[\"'(\[\u201c\u2018]?[A-Z0-9\u0c80-\u0cff])")
_HYPHENATED = re.compile(r"(?<=[a-z])-[ \t]*\n[ \t]*(?=[a-z])")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SURROGATE = re.compile("[\ud800-\udfff]")
"""A lone UTF-16 surrogate: what a font's ToUnicode map can hand back for a
glyph it maps to half a character. It is not text and cannot be written as
UTF-8, so it never leaves the reader."""
_TITLE_CHARS = 300


class PdfUnreadable(Exception):
    """A PDF that cannot be answered from, and why.

    ``lasting``: the verdict is about the file (encrypted, damaged, no text
    layer) and stands until the file or the reader changes. Otherwise it is
    about this attempt (the reader was stopped while opening it, say) and is
    tried again later."""

    def __init__(self, reason: str, *, lasting: bool = True) -> None:
        super().__init__(reason)
        self.reason = reason
        self.lasting = lasting


@dataclass(frozen=True)
class PdfPart:
    """What one read of a PDF got: its pages from ``start`` on, in order.

    A large document is read over several runs, a slice at a time from the
    first page, so its beginning (the summary, the contents) is answerable
    first; ``next_page`` is where the next run carries on."""

    title: str
    """The title in the file's own metadata; empty when it has none worth using."""
    page_count: int
    start: int
    pages: tuple[str, ...]
    """``pages[0]`` is page ``start``. A page that was skipped is empty."""
    skipped: Mapping[int, str] = field(default_factory=dict[int, str])
    """Pages left blank, by number → why: too large, too slow, too much memory."""
    stopped: str = ""
    """Why the read ended before its slice did: ``time`` (the run's time for
    this file), ``characters`` (the file's text limit), ``stopped`` (the reader
    was killed). Empty when it read its whole slice."""

    @property
    def next_page(self) -> int:
        return self.start + len(self.pages)

    @property
    def done(self) -> bool:
        return self.next_page > self.page_count


def _pdf_lines(raw: str) -> list[str]:
    """One page's text as lines a passage can hold: ligatures and full-width forms
    folded (NFKC), soft hyphens and line-end hyphenation undone, the visual line
    breaks of the layout joined, and the result cut into sentences."""
    t = unicodedata.normalize("NFKC", _SURROGATE.sub("", raw)).replace("\u00ad", "")
    t = _HYPHENATED.sub("", _CONTROL.sub(" ", t))
    lines: list[str] = []
    for sentence in _SENTENCE_END.split(_clean(t)):
        while len(sentence) > _PDF_LINE_CHARS:
            cut = sentence.rfind(" ", 0, _PDF_LINE_CHARS)
            cut = cut if cut > 0 else _PDF_LINE_CHARS
            lines.append(sentence[:cut])
            sentence = sentence[cut:].lstrip()
        if sentence:
            lines.append(sentence)
    return lines


def _metadata_title(reader: PdfReader) -> str:
    try:
        title = _clean((reader.metadata.title or "") if reader.metadata else "")
    except Exception:
        return ""
    title = _SURROGATE.sub("", title)[:_TITLE_CHARS]
    # Authoring tools often write the source file's name here; that names nothing.
    if re.search(r"\.[a-z]{2,4}$|^microsoft |^untitled", title, re.I):
        return ""
    return title


def file_title(url: str) -> str:
    """A PDF named by its file name: ``Startup-Policy_2025.pdf`` → ``Startup Policy 2025``."""
    name = unquote(path_of(url).rsplit("/", 1)[-1])
    name = re.sub(r"\.pdf$", "", name, flags=re.I)
    return _clean(re.sub(r"[-_+]+", " ", name)) or name


_PDF_STREAM_BYTES = 4 * 1024 * 1024
"""A page whose content (or any stream decompressed on its way) is larger than
this is skipped. Real pages of drawn text on the site run to 1.5 MB and read in
under a second; a stream past this is a file built to keep a reader busy."""
_PDF_XFORMS = 500
"""Form XObjects a page may invoke while its text is read."""
_PDF_LIMITS = pypdf.Configuration(
    zlib_maximum_output_length=_PDF_STREAM_BYTES,
    lzw_maximum_output_length=_PDF_STREAM_BYTES,
    run_length_maximum_output_length=_PDF_STREAM_BYTES,
    array_based_stream_maximum_output_length=_PDF_STREAM_BYTES,
    xform_maximum_invocations_per_extraction=_PDF_XFORMS,
)


class _PageTimeout(BaseException):
    """Not an ``Exception``: pypdf catches ``Exception`` around each operator it
    reads, and would swallow the alarm and read on."""


@contextlib.contextmanager
def _page_timer(seconds: float) -> Generator[None]:
    """Interrupt the page being read after ``seconds``. pypdf is pure Python, so
    the alarm lands between two of its steps. Only in a process's main thread
    on a platform with ``setitimer``; elsewhere the run's own limits hold."""
    if (
        seconds <= 0
        or not hasattr(signal, "setitimer")
        or threading.current_thread() is not threading.main_thread()
    ):
        yield
        return

    armed = True

    def ring(_signum: int, _frame: object) -> None:
        if armed:
            raise _PageTimeout

    old = signal.signal(signal.SIGALRM, ring)
    # It rings again every half second until disarmed, should one be swallowed.
    signal.setitimer(signal.ITIMER_REAL, seconds, 0.5)
    try:
        yield
    finally:
        while True:  # disarm first, so a late ring cannot land in the cleanup
            try:
                armed = False
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, old)
                break
            except _PageTimeout:
                continue


def _content_bytes(page: PageObject) -> int:
    """The decompressed size of a page's content streams. Decompression stops at
    the stream limit, which raises."""
    contents = page.get("/Contents")
    if contents is None:
        return 0
    obj = contents.get_object()
    streams = list(obj) if isinstance(obj, ArrayObject) else [obj]
    total = 0
    for stream in streams:
        data = stream.get_object()
        if isinstance(data, StreamObject):
            total += len(data.get_data())
    return total


def _no_text(part: PdfPart) -> str | None:
    """Why a document read from its first page has nothing to answer from: its
    pages are scanned images, or too heavy to read. ``None`` when it has text."""
    letters = sum(c.isalpha() for p in part.pages for c in p)
    if letters >= max(100, _PDF_MIN_LETTERS_PER_PAGE * len(part.pages)):
        return None
    if part.pages and len(part.skipped) == len(part.pages):
        return "its pages are too large or too slow to read"
    return "no text layer: scanned pages, which are not read (no OCR)"


Emit = Callable[[dict[str, object]], None]


def read_pdf(
    source: bytes | Path,
    *,
    start: int = 1,
    max_pages: int = 150,
    max_chars: int = 1_000_000,
    page_timeout_s: float = 10.0,
    timeout_s: float = 120.0,
    emit: Emit | None = None,
) -> PdfPart:
    """The text of a PDF, page by page, from page ``start``: at most
    ``max_pages`` pages and ``max_chars`` characters, for at most ``timeout_s``.
    Blocking: a refresh runs it in a child process (:func:`read_pdf_isolated`),
    reading the file from disk.

    One page never costs the document: a page whose content decompresses past
    the stream limit, takes over ``page_timeout_s``, runs out of memory or will
    not parse is skipped, and the next is read. ``emit`` is handed each page as
    it is read, so a reader that is killed has still handed over the pages
    before the one it was on.

    A file that is not a PDF, needs a password, cannot be parsed at all, or
    (read from its first page) has no text layer raises :class:`PdfUnreadable`.
    A file with an owner password only, which opens without asking, is read."""
    with contextlib.ExitStack() as stack:
        f = (
            stack.enter_context(source.open("rb"))
            if isinstance(source, Path)
            else io.BytesIO(source)
        )
        if b"%PDF-" not in f.read(1024):
            raise PdfUnreadable("not a PDF file")
        f.seek(0)
        stack.enter_context(apply_configuration(_PDF_LIMITS))
        deadline = time.monotonic() + timeout_s
        try:
            reader = PdfReader(f, strict=False)
            if reader.is_encrypted:
                try:
                    opened = reader.decrypt("")
                except Exception:
                    opened = 0
                if not opened:
                    raise PdfUnreadable("encrypted: it needs a password to open")
            count = len(reader.pages)
        except (PdfUnreadable, MemoryError):
            raise
        except Exception as e:
            raise PdfUnreadable(f"damaged: could not be parsed ({type(e).__name__})") from e
        if count == 0:
            raise PdfUnreadable("damaged: it has no pages")
        title = _metadata_title(reader)
        if emit:
            emit({"meta": {"title": title, "page_count": count}})
        pages: list[str] = []
        skipped: dict[int, str] = {}
        chars = 0
        stopped = ""
        for number in range(start, min(count, start + max_pages - 1) + 1):
            if time.monotonic() > deadline:
                stopped = "time"
                break
            if chars >= max_chars:
                stopped = "characters"
                break
            why = ""
            text = ""
            try:
                with _page_timer(page_timeout_s):
                    page = reader.pages[number - 1]
                    if _content_bytes(page) > _PDF_STREAM_BYTES:
                        raise LimitReachedError("page content")
                    text = "\n".join(_pdf_lines(page.extract_text() or ""))
            except LimitReachedError:
                why = "too large to read"
            except _PageTimeout:
                why = f"took over {page_timeout_s:g} s to read"
            except MemoryError:
                why = "needs too much memory to read"
            except Exception:
                why = "could not be parsed"
            if why:
                text = ""
                skipped[number] = why
            cut = len(text) > max_chars - chars
            text = text[: max_chars - chars]
            chars += len(text)
            pages.append(text)
            if emit:
                emit({"page": number, "text": text, **({"skipped": why} if why else {})})
            if cut:
                stopped = "characters"
                break
        part = PdfPart(title, count, start, tuple(pages), skipped, stopped)
        if start == 1 and stopped != "characters" and (why := _no_text(part)):
            raise PdfUnreadable(why)
        return part


_WORKER_FLAG = "--read-pdf-worker"
_WORKER_GRACE_S = 3.0
"""Time a reader process has beyond its own limits: to start, and to hand the
text back. Past that it is killed."""
_WORKER_LINE_BYTES = 32 * 1024 * 1024
"""The longest line a reader may hand back: one page's text, as JSON."""


def _limit_self(cpu_s: float, memory_mb: int) -> None:
    """Cap this process: CPU seconds always (where the platform has them), and
    address space on Linux, counted from what the interpreter already holds."""
    try:
        import resource
    except ImportError:  # not on this platform: the parent's kill still holds
        return
    cpu = math.ceil(cpu_s)
    with contextlib.suppress(ValueError, OSError):
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
    if sys.platform != "linux":
        return
    with contextlib.suppress(ValueError, OSError):
        pages = int(Path("/proc/self/statm").read_text().split()[0])
        limit = pages * os.sysconf("SC_PAGE_SIZE") + memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))


def _pdf_worker(argv: Sequence[str]) -> int:
    """The child side of :func:`read_pdf_isolated`: reads the PDF at a path and
    writes a JSON line per page, then one that says how it ended."""
    path, start, max_pages, max_chars, page_timeout_s, timeout_s, memory_mb = argv
    _limit_self(float(timeout_s) + float(page_timeout_s) + 2, int(memory_mb))

    def emit(line: dict[str, object]) -> None:
        sys.stdout.write(json.dumps(line) + "\n")
        sys.stdout.flush()

    end: dict[str, object]
    try:
        part = read_pdf(
            Path(path),
            start=int(start),
            max_pages=int(max_pages),
            max_chars=int(max_chars),
            page_timeout_s=float(page_timeout_s),
            timeout_s=float(timeout_s),
            emit=emit,
        )
        end = {"stopped": part.stopped}
    except PdfUnreadable as e:
        end = {"unreadable": e.reason, "lasting": e.lasting}
    except MemoryError:
        end = {"unreadable": f"needs more than {memory_mb} MB to open", "lasting": False}
    emit({"end": end})
    return 0


async def read_pdf_isolated(
    path: Path,
    *,
    start: int = 1,
    max_pages: int = 150,
    max_chars: int = 1_000_000,
    page_timeout_s: float = 10.0,
    timeout_s: float = 120.0,
    memory_mb: int = 384,
) -> PdfPart:
    """:func:`read_pdf` in a child process, on the file at ``path``, so no PDF
    can stall the brain or take its memory.

    The child caps its own CPU time and, on Linux, its address space at
    ``memory_mb`` over the interpreter's own, and interrupts a page that runs
    past ``page_timeout_s``. The parent kills it once ``timeout_s`` plus one
    page's time and a short grace have passed. Pages arrive as they are read, so
    a killed or crashed reader still yields every page before the one it was on;
    that page is recorded as skipped and the next run starts after it. Nothing
    is left running when this returns or is cancelled."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        str(Path(__file__).resolve()),
        _WORKER_FLAG,
        str(path),
        str(start),
        str(max_pages),
        str(max_chars),
        repr(float(page_timeout_s)),
        repr(float(timeout_s)),
        str(memory_mb),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        limit=_WORKER_LINE_BYTES,
    )
    assert proc.stdout is not None
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s + page_timeout_s + _WORKER_GRACE_S
    meta: dict[str, object] | None = None
    pages: list[str] = []
    skipped: dict[int, str] = {}
    end: dict[str, object] | None = None
    try:
        while (left := deadline - loop.time()) > 0:
            line = await asyncio.wait_for(proc.stdout.readline(), left)
            if not line:
                break
            msg = _obj(json.loads(line), "reader line")
            if isinstance(m := msg.get("meta"), dict):
                meta = cast("dict[str, object]", m)
            elif isinstance(n := msg.get("page"), int):
                pages.append(_str(msg, "text", default=""))
                if isinstance(why := msg.get("skipped"), str):
                    skipped[n] = why
            elif isinstance(e := msg.get("end"), dict):
                end = cast("dict[str, object]", e)
                break
    except (TimeoutError, ValueError, RuntimeError, asyncio.LimitOverrunError):
        pass  # killed below; what arrived stands
    finally:
        if proc.returncode is None:
            proc.kill()
        await proc.wait()
    if end is not None and isinstance(reason := end.get("unreadable"), str):
        raise PdfUnreadable(reason, lasting=end.get("lasting") is not False)
    count = meta.get("page_count") if meta else None
    if not isinstance(count, int):
        raise PdfUnreadable(
            "the reader was stopped while opening it (too slow, or too much memory)",
            lasting=False,
        )
    stopped = _str(end, "stopped", default="") if end is not None else "stopped"
    if end is None:
        # Stopped on a page: that page is skipped, and the next run goes on after it.
        stuck = start + len(pages)
        if stuck <= min(count, start + max_pages - 1):
            pages.append("")
            skipped[stuck] = "the reader was stopped on it (too slow, or too much memory)"
    part = PdfPart(
        _str(meta or {}, "title", default=""), count, start, tuple(pages), skipped, stopped
    )
    # A reader that was stopped is not a verdict on the file: what it read
    # stands, and the next run goes on after the page it was stopped on.
    return part


# ─── The snapshot ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Validators:
    """What the server said about a file, so the next run can ask whether it
    changed instead of downloading it again."""

    etag: str = ""
    last_modified: str = ""
    length: str = ""
    """Content-Length, as sent."""
    sha256: str = ""
    """The file's own SHA-256, when it was downloaded: the same file whatever
    the server's validators say."""

    @classmethod
    def of(cls, headers: Mapping[str, str]) -> Validators:
        h = {k.lower(): v.strip() for k, v in headers.items()}
        return cls(h.get("etag", ""), h.get("last-modified", ""), h.get("content-length", ""))

    def conditional(self) -> dict[str, str]:
        """The request headers that ask for the file only if it changed."""
        out: dict[str, str] = {}
        if self.etag:
            out["If-None-Match"] = self.etag
        if self.last_modified:
            out["If-Modified-Since"] = self.last_modified
        return out

    def same_file(self, now: Validators) -> bool:
        """Whether a full answer is the file already held: the same ETag, or the
        same Content-Length and Last-Modified. For a server that ignores
        conditional requests."""
        if self.etag and self.etag == now.etag:
            return True
        return bool(self.length and self.last_modified) and (
            (self.length, self.last_modified) == (now.length, now.last_modified)
        )

    def to_json(self) -> dict[str, str]:
        return {
            "etag": self.etag,
            "last_modified": self.last_modified,
            "length": self.length,
            "sha256": self.sha256,
        }

    @classmethod
    def from_json(cls, raw: object) -> Validators:
        if not isinstance(raw, dict):
            return cls()
        d = cast("dict[str, object]", raw)

        def text(key: str) -> str:
            v = d.get(key)
            return v if isinstance(v, str) else ""

        return cls(text("etag"), text("last_modified"), text("length"), text("sha256"))


@dataclass(frozen=True)
class StoredPage:
    url: str
    title: str
    section: str
    origin: Origin
    """``approved``: on the allowlist. ``auto``: added by a refresh."""
    lastmod: str
    """A page's sitemap ``lastmod``; a PDF's Last-Modified header."""
    fetched_at: str
    digest: str
    blocks: tuple[str, ...]
    """A page's top-level parts; a PDF's pages, ``blocks[0]`` being page 1."""
    links: tuple[str, ...] = ()
    kind: Kind = "page"
    pdf_links: tuple[tuple[str, str], ...] | None = None
    """A page's PDF links and their link text. ``None``: not recorded (a page
    read before PDFs were), so a page PDFs are found from is read again."""
    validators: Validators = Validators()
    """A PDF's ETag, Last-Modified and Content-Length when it was read."""
    page_count: int = 0
    """A PDF's pages, all told."""
    next_page: int = 0
    """The first page of a PDF not read yet: past ``page_count`` once it is read
    through. A large PDF is read a slice a run, from the start, and carries on
    from here the next run as long as the file is the same."""
    limited: str = ""
    """Why a PDF is not read further under the limits it was read with: its
    own text limit (``characters``), or the limit on all PDF text (``cap``).
    Read on when the limits change."""
    read_with: str = ""
    """The reader and limits a PDF was read with (:func:`reader_signature`)."""
    host: str = ""
    """The host a PDF is served from: karnatakadigital.in, or the other site an
    approved page links it on."""

    @property
    def in_progress(self) -> bool:
        """A PDF with pages still to read under the limits it was read with."""
        return self.kind == "pdf" and self.next_page <= self.page_count and not self.limited


@dataclass(frozen=True)
class Unreadable:
    """A linked PDF that is not answered from, and why. Kept so the next run asks
    whether it changed rather than downloading it again."""

    url: str
    title: str
    section: str
    reason: str
    validators: Validators
    checked_at: str
    read_with: str = ""
    """The reader and limits the verdict was reached with. A verdict reached with
    other limits, or another version of the reader, is tried again."""
    lasting: bool = True
    """A verdict about the file itself (encrypted, scanned, damaged, too large):
    it stands until the file, the reader or the limits change. ``False``: it
    could be different next time (it timed out, ran out of memory, or could not
    be fetched), so it is tried again after ``retry_after``."""
    attempts: int = 1
    retry_after: str = ""
    """ISO time; empty for a lasting verdict."""


@dataclass(frozen=True)
class Pending:
    """A page held back for a person to review."""

    url: str
    section: str
    lastmod: str
    reason: str
    first_seen: str


@dataclass(frozen=True)
class Snapshot:
    built_at: str = ""
    """ISO time of the last successful refresh; empty for a snapshot never built."""
    known: dict[str, str] = field(default_factory=dict[str, str])
    """Every sitemap URL a refresh has decided about → its ``lastmod`` then. A URL
    not in here is new."""
    pages: dict[str, StoredPage] = field(default_factory=dict[str, StoredPage])
    pending_review: dict[str, Pending] = field(default_factory=dict[str, Pending])
    unreadable: dict[str, Unreadable] = field(default_factory=dict[str, Unreadable])
    """Linked PDFs that could not be read, by URL."""

    def to_json(self) -> dict[str, object]:
        return {
            "version": SNAPSHOT_VERSION,
            "built_at": self.built_at,
            "known": self.known,
            "pages": [
                {
                    "url": p.url,
                    "title": p.title,
                    "section": p.section,
                    "origin": p.origin,
                    "lastmod": p.lastmod,
                    "fetched_at": p.fetched_at,
                    "digest": p.digest,
                    "blocks": list(p.blocks),
                    "links": list(p.links),
                    "kind": p.kind,
                    **(
                        {"pdf_links": [list(x) for x in p.pdf_links]}
                        if p.pdf_links is not None
                        else {}
                    ),
                    **(
                        {
                            "validators": p.validators.to_json(),
                            "page_count": p.page_count,
                            "next_page": p.next_page,
                            "limited": p.limited,
                            "read_with": p.read_with,
                            "host": p.host,
                        }
                        if p.kind == "pdf"
                        else {}
                    ),
                }
                for p in self.pages.values()
            ],
            "pending_review": [vars(p) for p in self.pending_review.values()],
            "unreadable": [
                {**vars(u), "validators": u.validators.to_json()} for u in self.unreadable.values()
            ],
        }

    @classmethod
    def from_json(cls, raw: object) -> Snapshot:
        doc = _obj(raw, "snapshot")
        if doc.get("version") not in (1, SNAPSHOT_VERSION):
            raise _fail(f"snapshot version {doc.get('version')!r} is not {SNAPSHOT_VERSION}")
        # Every URL is spelled again the way normalize() spells it now, so a
        # snapshot written under an older spelling keeps its pages under the
        # same keys a refresh will look them up by. One that no longer passes
        # (an escaped separator, say) is left out.
        known = {
            n: v
            for k, v in _obj(doc.get("known", {}), "known").items()
            if isinstance(v, str) and (n := normalize(k)) is not None
        }
        pages: dict[str, StoredPage] = {}
        for i, item in enumerate(_list(doc.get("pages", []), "pages")):
            p = _obj(item, f"pages[{i}]")
            origin = _str(p, "origin")
            spell = pdf_url if p.get("kind") == "pdf" else normalize
            if (url := spell(_str(p, "url"))) is None:
                continue
            if url in pages and pages[url].origin == "approved" and origin != "approved":
                continue  # two old spellings of one page: the approved one wins
            pages[url] = StoredPage(
                url=url,
                title=_str(p, "title"),
                section=_str(p, "section"),
                origin="approved" if origin == "approved" else "auto",
                lastmod=_str(p, "lastmod"),
                fetched_at=_str(p, "fetched_at"),
                digest=_str(p, "digest"),
                blocks=tuple(_strs(p.get("blocks", []), "blocks")),
                links=tuple(_strs(p.get("links", []), "links")),
                kind="pdf" if p.get("kind") == "pdf" else "page",
                pdf_links=_pairs(p["pdf_links"], "pdf_links") if "pdf_links" in p else None,
                validators=Validators.from_json(p.get("validators")),
                page_count=_int(p, "page_count"),
                next_page=_int(p, "next_page"),
                limited=_str(p, "limited", default=""),
                read_with=_str(p, "read_with", default=""),
                host=_str(p, "host", default=""),
            )
        pending: dict[str, Pending] = {}
        for i, item in enumerate(_list(doc.get("pending_review", []), "pending_review")):
            p = _obj(item, f"pending_review[{i}]")
            if (url := normalize(_str(p, "url")) or pdf_url(_str(p, "url"))) is None:
                continue
            pending[url] = Pending(
                url=url,
                section=_str(p, "section"),
                lastmod=_str(p, "lastmod"),
                reason=_str(p, "reason"),
                first_seen=_str(p, "first_seen"),
            )
        unreadable: dict[str, Unreadable] = {}
        for i, item in enumerate(_list(doc.get("unreadable", []), "unreadable")):
            u = _obj(item, f"unreadable[{i}]")
            if (url := pdf_url(_str(u, "url"))) is None:
                continue
            attempts = u.get("attempts", 1)
            unreadable[url] = Unreadable(
                url=url,
                title=_str(u, "title", default=""),
                section=_str(u, "section"),
                reason=_str(u, "reason"),
                validators=Validators.from_json(u.get("validators")),
                checked_at=_str(u, "checked_at", default=""),
                read_with=_str(u, "read_with", default=""),
                lasting=u.get("lasting", True) is not False,
                attempts=attempts if isinstance(attempts, int) else 1,
                retry_after=_str(u, "retry_after", default=""),
            )
        return cls(_str(doc, "built_at"), known, pages, pending, unreadable)

    def save(self, path: Path) -> None:
        """Write atomically: a reader sees the old snapshot or the new one. The
        file is written under a name of its own and moved into place, under an
        advisory lock, so the CLI and a running brain never write over each
        other halfway."""
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(self.to_json(), ensure_ascii=False)
        with _locked(path.with_suffix(".lock")):
            fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8", errors="replace") as f:
                    f.write(text)
                Path(tmp).replace(path)
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise

    @classmethod
    def load(cls, path: Path) -> Snapshot | None:
        """The snapshot at ``path``; ``None`` when there is none or it is unreadable."""
        try:
            return cls.from_json(json.loads(path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            return None
        except (OSError, ValueError, RuntimeError) as e:
            logger.warning("kdem: ignoring unreadable snapshot {}: {}", path, e)
            return None


@contextlib.contextmanager
def _locked(lock: Path) -> Generator[None]:
    """An exclusive advisory lock on ``lock`` (fcntl; where there is none, no lock)."""
    try:
        import fcntl
    except ImportError:
        yield
        return
    with lock.open("a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def default_cache_dir() -> Path:
    """``$KDEM_KNOWLEDGE_DIR``, else ``$XDG_CACHE_HOME/voqalize-kdem``, else a
    directory under the system temp dir. Never inside the repository."""
    if d := os.environ.get(ENV_DIR):
        return Path(d)
    if xdg := os.environ.get("XDG_CACHE_HOME"):
        return Path(xdg) / "voqalize-kdem"
    return Path(tempfile.gettempdir()) / "voqalize-kdem"


def _digest(title: str, blocks: Sequence[str]) -> str:
    h = hashlib.sha256(title.encode("utf-8", "replace"))
    for b in blocks:
        h.update(b"\x00" + b.encode("utf-8", "replace"))
    return h.hexdigest()[:16]


# ─── Refresh ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RefreshPolicy:
    seed_days: int = 90
    """On the first build, a news or event page older than this is noted but not
    read: the archive runs to thousands of items."""
    max_new: int = 150
    """At most this many new pages are read per run, newest first; the rest wait
    for the next run."""
    pause_s: float = 0.5
    """Between page reads, to stay gentle on the site."""
    force: frozenset[str] = frozenset()
    """URLs to re-read whatever their ``lastmod`` says (the urgent-change path).
    A PDF URL is downloaded and read again without a conditional request."""
    max_new_pdfs: int = 40
    """At most this many PDFs not seen before are read per run, in the order the
    approved pages list them; the rest wait for the next run. A PDF already held
    is asked about with a conditional request every run and does not count."""
    max_pdf_bytes: int = 150 * 1024 * 1024
    """A safety ceiling, not a working limit: a PDF is streamed to disk and read
    from there, so size costs time, not memory. Past this it is not downloaded
    (checked against its Content-Length, and again while it downloads)."""
    pdf_pages_per_run: int = 150
    """A PDF is read this many pages a run, from its first page; a longer one
    carries on where it stopped on the next run, as long as the file is the same."""
    max_pdf_chars: int = 1_000_000
    """One PDF's text, at most: so no one document takes the whole cap."""
    pdf_page_timeout_s: float = 10.0
    """A page that takes longer is skipped, and the next one read."""
    pdf_timeout_s: float = 120.0
    """Reading one PDF stops after this long a run, keeping what it read and
    carrying on next run; the process is killed a few seconds past it."""
    pdf_memory_mb: int = 384
    """The memory the process reading one PDF may take beyond the interpreter's
    own (Linux; elsewhere only the time limit holds)."""
    max_pdf_chars_total: int = 5_000_000
    """All PDFs together hold at most this much text, so a search over them stays
    inside the tool budget. PDFs past it, in the order the pages link them, are
    not read; ``report.pdf_capped`` names them."""


@dataclass
class RefreshReport:
    updated: list[str] = field(default_factory=list[str])
    unchanged: list[str] = field(default_factory=list[str])
    added: list[str] = field(default_factory=list[str])
    held: list[str] = field(default_factory=list[str])
    dropped: list[str] = field(default_factory=list[str])
    failed: list[str] = field(default_factory=list[str])
    offsite: list[str] = field(default_factory=list[str])
    """Pages that now redirect to another site: not indexed."""
    moved: list[str] = field(default_factory=list[str])
    """Pages that now redirect to another page on the site: not indexed under the
    old URL. The page they land on is judged by its own sitemap entry."""
    deferred: int = 0
    pdf_added: list[str] = field(default_factory=list[str])
    pdf_updated: list[str] = field(default_factory=list[str])
    pdf_unchanged: list[str] = field(default_factory=list[str])
    pdf_dropped: list[str] = field(default_factory=list[str])
    """PDFs no approved page links to any more, or that answered 404/410."""
    pdf_unreadable: dict[str, str] = field(default_factory=dict[str, str])
    """PDFs read this run that cannot be answered from → why. Not indexed."""
    pdf_truncated: list[str] = field(default_factory=list[str])
    """PDFs indexed only up to the page, character or time limit."""
    pdf_deferred: int = 0
    pdf_in_progress: list[str] = field(default_factory=list[str])
    """PDFs read in part so far, carried on next run."""
    pdf_skipped_pages: dict[str, list[int]] = field(default_factory=dict[str, list[int]])
    """PDFs read this run with pages left blank (too heavy or too slow) → which."""
    pdf_waiting: int = 0
    """PDFs that failed recently and wait for their retry time."""
    pdf_capped: list[str] = field(default_factory=list[str])
    """PDFs not indexed because all PDFs together reached ``max_pdf_chars_total``."""

    def summary(self) -> str:
        return (
            f"updated {len(self.updated)}, unchanged {len(self.unchanged)}, "
            f"added {len(self.added)}, held {len(self.held)}, dropped {len(self.dropped)}, "
            f"failed {len(self.failed)}, off-site {len(self.offsite)}, "
            f"moved {len(self.moved)}, deferred {self.deferred}; PDFs: "
            f"added {len(self.pdf_added)}, updated {len(self.pdf_updated)}, "
            f"unchanged {len(self.pdf_unchanged)}, dropped {len(self.pdf_dropped)}, "
            f"unreadable {len(self.pdf_unreadable)}, deferred {self.pdf_deferred}, "
            f"in progress {len(self.pdf_in_progress)}, waiting {self.pdf_waiting}, "
            f"over the cap {len(self.pdf_capped)}"
        )


def _iso(t: datetime) -> str:
    return t.astimezone(UTC).isoformat(timespec="seconds")


def _parse_time(s: str) -> datetime | None:
    try:
        t = datetime.fromisoformat(s)
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=UTC)


_HOPS = 3
"""Redirects to the same page under another spelling followed, at most."""


async def _follow(
    ask: Callable[[str], Awaitable[FetchResult]], url: str, same: Callable[[str], bool]
) -> FetchResult:
    """``ask`` for ``url``, following a redirect only to the same page or file
    under another spelling (``same``), over https, a few hops at most. Any other
    redirect comes back as it is, its ``url`` where it points, its body unread."""
    target = url
    got = await ask(target)
    for _ in range(_HOPS):
        if got.status not in REDIRECTS or got.url == target:
            break
        if not (got.url.startswith("https://") and same(got.url)):
            break
        target = got.url
        got = await ask(target)
    return got


async def _read_page(
    fetch: Fetch, url: str, allowlist: Allowlist
) -> tuple[FetchResult, Extracted | None]:
    got = await _follow(fetch, url, lambda to: allowlist.canonical(to) == url)
    if got.status != 200:
        return got, None
    return got, await asyncio.to_thread(extract, got.body, url=got.url or url)


async def refresh(
    snapshot: Snapshot,
    allowlist: Allowlist,
    fetch: Fetch,
    *,
    fetch_file: FetchFile | None = None,
    policy: RefreshPolicy | None = None,
    now: datetime | None = None,
    on_progress: Callable[[Snapshot], Awaitable[None]] | None = None,
) -> tuple[Snapshot, RefreshReport]:
    """One pass over the sitemap. Returns the next snapshot and what changed.

    - An approved page is read when it is new to the snapshot, its ``lastmod``
      moved, or it is forced. A 404/410 drops it, and so does a redirect to
      another page or another site; any other failure keeps the copy already
      held.
    - A page that is gone from the sitemap, or that the list no longer allows
      (:meth:`Allowlist.refusal`), is dropped. A page a refresh added whose
      section has since been closed, or which now matches a held pattern, is
      held in ``pending_review`` instead.
    - A new URL is added when its section is approved for automatic additions:
      news and events by post type, a flat page when an approved hub links to it.
      A URL in any other section is held in ``pending_review``. Excluded URLs
      and aliases are noted and otherwise ignored. A new URL that redirects is
      not added: the page it lands on has a sitemap entry of its own.
    - PDFs come last (:func:`_refresh_pdfs`): the ones the approved pages in a
      PDF-reading section link to now are read with ``fetch_file``, and the rest
      are dropped. Without ``fetch_file`` the PDFs still linked are kept as held
      and none is downloaded.

    ``on_progress`` is handed the snapshot as it stands once the pages already
    known have been re-read, before any new page is: on a first build that is
    every approved page, so the caller can answer from them while the rest are
    read. When there are PDFs to download it is handed the snapshot once more,
    with the new pages, before they are.

    The sitemap is read first and in full; if that fails this raises and the
    caller keeps the snapshot it has."""
    policy = policy or RefreshPolicy()
    now = now or datetime.now(UTC)
    stamp = _iso(now)
    report = RefreshReport()
    sitemap = await read_sitemap(fetch, allowlist.sitemap_url)
    first_build = not snapshot.known
    forced = {c for u in policy.force if (c := allowlist.locate(u)) is not None}

    pages: dict[str, StoredPage] = {}
    revoked: dict[str, Pending] = {}
    held_pdfs = {u: p for u, p in snapshot.pages.items() if p.kind == "pdf"}
    for url, page in snapshot.pages.items():
        if page.kind == "pdf":
            continue
        why = allowlist.refusal(url, page.origin, page.section)
        if url in sitemap and why is None:
            pages[url] = page
            continue
        report.dropped.append(url)
        if url in sitemap and page.origin == "auto" and _for_review(allowlist, url):
            # A section closed, or a held pattern added, after the page went in:
            # it waits for a person like any other page outside the list.
            revoked[url] = Pending(url, page.section, sitemap[url].lastmod, why or "", stamp)

    async def reread(url: str, lastmod: str, make: Callable[[Extracted], StoredPage]) -> None:
        old = pages.get(url)
        try:
            got, ex = await _read_page(fetch, url, allowlist)
        except Exception as e:  # a page that will not load keeps its last copy
            logger.warning("kdem: could not read {}: {}", url, e)
            report.failed.append(url)
            return
        if ex is None and got.status not in REDIRECTS:
            if got.status in (404, 410):
                if pages.pop(url, None) is not None:
                    report.dropped.append(url)
            else:
                report.failed.append(url)
            return
        landed = allowlist.canonical(got.url) if got.url else url
        if landed is None:
            # Another site's text is not KDEM's page, whatever URL led to it.
            logger.warning("kdem: {} redirects off the site, to {}", url, got.url)
            pages.pop(url, None)
            report.offsite.append(url)
            return
        if landed != url:
            # Another page's text is not this page's, and the page it lands on
            # is judged by its own entry, not let in under this one.
            logger.warning("kdem: {} now redirects to {}; not indexed", url, got.url)
            pages.pop(url, None)
            report.moved.append(url)
            return
        if ex is None:  # a redirect back to itself, round and round
            report.failed.append(url)
            return
        new = make(ex)
        if old is not None and old.digest == new.digest:
            pages[url] = replace(
                old, lastmod=lastmod, fetched_at=stamp, links=new.links, pdf_links=new.pdf_links
            )
            report.unchanged.append(url)
        else:
            pages[url] = new
            report.updated.append(url)
        if policy.pause_s:
            await asyncio.sleep(policy.pause_s)

    # Approved pages, then auto-added pages, re-read where their lastmod moved.
    # A page PDFs are found from whose PDF links were never recorded (a snapshot
    # from before PDFs were read) is read again too.
    sources = {p.url for p in allowlist.pdf_sources}
    for ap in allowlist.pages:
        entry = sitemap.get(ap.url)
        if entry is None:
            continue
        held = pages.get(ap.url)
        if (
            held is None
            or held.lastmod != entry.lastmod
            or ap.url in forced
            or (ap.url in sources and held.pdf_links is None)
        ):

            def approved_page(
                ex: Extracted, ap: ApprovedPage = ap, lm: str = entry.lastmod
            ) -> StoredPage:
                return StoredPage(
                    ap.url,
                    ap.title,
                    ap.section,
                    "approved",
                    lm,
                    stamp,
                    _digest(ap.title, ex.blocks),
                    ex.blocks,
                    ex.links,
                    pdf_links=ex.pdf_links,
                )

            await reread(ap.url, entry.lastmod, approved_page)
    for url, page in list(pages.items()):
        if page.origin != "auto":
            continue
        lastmod = sitemap[url].lastmod
        if page.lastmod != lastmod or url in forced:

            def auto_page(ex: Extracted, page: StoredPage = page, lm: str = lastmod) -> StoredPage:
                title = ex.title or page.title
                return replace(
                    page,
                    title=title,
                    lastmod=lm,
                    fetched_at=stamp,
                    digest=_digest(title, ex.blocks),
                    blocks=ex.blocks,
                    links=ex.links,
                    pdf_links=ex.pdf_links,
                )

            await reread(url, lastmod, auto_page)

    def so_far() -> Snapshot:
        # The PDFs already held stay answerable while the run goes on; the index
        # keeps only the ones an approved page still links to.
        return Snapshot(
            snapshot.built_at,
            snapshot.known,
            dict(pages) | held_pdfs,
            snapshot.pending_review,
            snapshot.unreadable,
        )

    if on_progress is not None:
        await on_progress(so_far())

    # New URLs: added, held or ignored.
    hubs = allowlist.hubs
    linked: dict[str, str] = {}
    for hub_url, target in hubs.items():
        hub = pages.get(hub_url)
        for link in hub.links if hub is not None else ():
            linked.setdefault(link, target)

    known: dict[str, str] = {}
    pending: dict[str, Pending] = {}
    to_add: list[tuple[SitemapEntry, str]] = []
    for url, entry in sitemap.items():
        if url in pages or url in allowlist.by_url:
            known[url] = entry.lastmod
            continue
        if allowlist.is_alias(url) or allowlist.is_excluded(url):
            known[url] = entry.lastmod
            continue
        if (was := revoked.get(url)) is not None:
            known[url] = entry.lastmod
            pending[url] = was
            report.held.append(url)
            continue
        was_pending = snapshot.pending_review.get(url)
        if url in snapshot.known and was_pending is None:
            known[url] = entry.lastmod
            continue
        section, reason = _place(allowlist, entry, linked)
        if reason is None:
            if first_build and entry.post_type != "page" and _older(entry, now, policy.seed_days):
                known[url] = entry.lastmod
                continue
            to_add.append((entry, section))
            continue
        known[url] = entry.lastmod
        pending[url] = Pending(
            url,
            section,
            entry.lastmod,
            reason,
            was_pending.first_seen if was_pending else stamp,
        )
        if was_pending is None:
            report.held.append(url)

    to_add.sort(key=lambda es: es[0].lastmod, reverse=True)
    report.deferred = max(0, len(to_add) - policy.max_new)
    for entry, section in to_add[: policy.max_new]:
        try:
            got, ex = await _read_page(fetch, entry.url, allowlist)
        except Exception as e:
            logger.warning("kdem: could not read new page {}: {}", entry.url, e)
            report.failed.append(entry.url)
            continue
        known[entry.url] = entry.lastmod
        if ex is None and got.status not in REDIRECTS:
            if got.status not in (404, 410):
                known.pop(entry.url)
                report.failed.append(entry.url)
            continue
        landed = allowlist.canonical(got.url) if got.url else entry.url
        if landed is None:
            logger.warning("kdem: new page {} redirects off the site", entry.url)
            report.offsite.append(entry.url)
            continue
        if landed != entry.url:
            # The page it lands on was placed (or held) by its own entry; it is
            # not let in under this one's section.
            logger.info("kdem: new page {} redirects to {}; not added", entry.url, got.url)
            report.moved.append(entry.url)
            continue
        if ex is None:
            known.pop(entry.url)
            report.failed.append(entry.url)
            continue
        title = ex.title or path_of(entry.url).strip("/").replace("-", " ")
        pages[entry.url] = StoredPage(
            entry.url,
            title,
            section,
            "auto",
            entry.lastmod,
            stamp,
            _digest(title, ex.blocks),
            ex.blocks,
            ex.links,
            pdf_links=ex.pdf_links,
        )
        report.added.append(entry.url)
        if policy.pause_s:
            await asyncio.sleep(policy.pause_s)

    async def handover() -> None:
        if on_progress is not None:
            await on_progress(so_far())

    run = _PdfRun(
        snapshot, allowlist, pages, held_pdfs, pending, report, policy, forced, stamp, now
    )
    unreadable = await _refresh_pdfs(run, fetch_file, handover)
    return Snapshot(stamp, known, pages, pending, unreadable), report


@dataclass(frozen=True)
class PdfLink:
    """How an approved page links a PDF."""

    text: str
    """The words that name it (:func:`_links`); empty when nothing does."""
    section: str
    via: str
    """The approved page that links it: the link card offered for a PDF on
    another site, which the browser snippet does not show."""


def linked_pdfs(allowlist: Allowlist, pages: Mapping[str, StoredPage]) -> dict[str, PdfLink]:
    """Every PDF, on this site or another, the approved pages in a PDF-reading
    section link to, as ``pages`` holds them now. The first page in list order
    that links a PDF places it; a later page's text names it when the first's
    is empty. Nothing past these links is followed."""
    out: dict[str, PdfLink] = {}
    for ap in allowlist.pdf_sources:
        page = pages.get(ap.url)
        if page is None:
            continue
        for link, text in page.pdf_links or ():
            url = pdf_url(link)
            if url is None:
                continue
            had = out.get(url)
            if had is None:
                out[url] = PdfLink(text, ap.section, ap.url)
            elif not had.text and text:
                out[url] = replace(had, text=text)
    return out


def reader_signature(policy: RefreshPolicy) -> str:
    """The reader and the limits a PDF is read with. A PDF found unreadable, or
    stopped at a limit, under another signature is read again."""
    return (
        f"pypdf {pypdf.__version__}; {policy.max_pdf_bytes} bytes, "
        f"{policy.pdf_pages_per_run} pages a run, {policy.max_pdf_chars} chars, "
        f"{policy.pdf_page_timeout_s:g} s a page, {policy.pdf_timeout_s:g} s, "
        f"{policy.pdf_memory_mb} MB, {policy.max_pdf_chars_total} chars in all"
    )


_RETRY_FIRST = timedelta(hours=20)
_RETRY_MOST = timedelta(days=30)


def _retry_after(now: datetime, attempts: int) -> str:
    """When a PDF that failed ``attempts`` times running is tried again: the next
    daily run, then every other, doubling to a month."""
    return _iso(now + min(_RETRY_FIRST * 2 ** (attempts - 1), _RETRY_MOST))


def _chars(page: StoredPage | None) -> int:
    return sum(map(len, page.blocks)) if page is not None else 0


@dataclass(frozen=True)
class _Ask:
    """One PDF to ask for this run."""

    url: str
    link: PdfLink
    fresh: bool = False
    """Download it whatever its validators say: forced, being read a slice a
    run, or a verdict reached under other limits."""


@dataclass
class _PdfRun:
    """The PDF half of one refresh: what is held going in, and where it goes."""

    snapshot: Snapshot
    allowlist: Allowlist
    pages: dict[str, StoredPage]
    """The next snapshot's pages; the PDFs that stay or arrive are put here."""
    held: dict[str, StoredPage]
    """The PDFs the previous snapshot held."""
    pending: dict[str, Pending]
    report: RefreshReport
    policy: RefreshPolicy
    forced: set[str]
    stamp: str
    now: datetime
    unreadable: dict[str, Unreadable] = field(default_factory=dict[str, Unreadable])
    chars: int = 0
    """The PDF text the next snapshot holds so far."""

    @property
    def signature(self) -> str:
        return reader_signature(self.policy)

    def plan(self) -> list[_Ask]:
        """The PDFs to ask for this run, in order. Notes the ones dropped, held for
        review, waiting for a retry and deferred on the way.

        Held PDFs come first (a PDF being read a slice a run among them); then
        PDFs not seen before, in link order; then the ones whose last failure is
        due for a retry, at the back. Only the last two count toward
        ``max_new_pdfs``, and a PDF waiting for its retry time is not asked for
        at all."""
        linked = linked_pdfs(self.allowlist, self.pages)
        self.report.pdf_dropped.extend(u for u in self.held if u not in linked)
        sig = self.signature
        known: list[_Ask] = []
        new: list[_Ask] = []
        retry: list[_Ask] = []
        for url, link in linked.items():
            why = self.allowlist.refusal(url, "auto", link.section, "pdf")
            if why is not None:
                if url in self.held:
                    self.report.pdf_dropped.append(url)
                if _for_review(self.allowlist, url):
                    was = self.snapshot.pending_review.get(url)
                    first = was.first_seen if was else self.stamp
                    self.pending[url] = Pending(url, link.section, "", why, first)
                    if was is None:
                        self.report.held.append(url)
                continue
            old = self.held.get(url)
            bad = self.snapshot.unreadable.get(url)
            if url in self.forced:
                known.append(_Ask(url, link, fresh=True))
            elif old is not None:
                self.chars += _chars(old)
                again = old.in_progress or (bool(old.limited) and old.read_with != sig)
                known.append(_Ask(url, link, fresh=again))
            elif bad is None:
                new.append(_Ask(url, link))
            elif bad.read_with != sig:
                retry.append(_Ask(url, link, fresh=True))
            elif bad.lasting:
                known.append(_Ask(url, link))  # a 304 keeps the verdict
            elif bad.retry_after <= self.stamp:
                retry.append(_Ask(url, link, fresh=True))
            else:
                self.keep(url, link)
                self.report.pdf_waiting += 1
        queue = new + retry
        if self.chars >= self.policy.max_pdf_chars_total:
            for later in queue:
                self.keep(later.url, later.link)
                self.report.pdf_capped.append(later.url)
            return known
        cap = self.policy.max_new_pdfs
        self.report.pdf_deferred = max(0, len(queue) - cap)
        for later in queue[cap:]:
            self.keep(later.url, later.link)  # a failure's record waits too
        return known + queue[:cap]

    def keep(self, url: str, link: PdfLink, **changes: str | Validators) -> None:
        """What is held for ``url`` stays, under the title it is linked by now."""
        if (old := self.held.get(url)) is not None:
            title = link.text or old.title
            self.pages[url] = replace(
                old,
                title=title,
                section=link.section,
                digest=_digest(title, old.blocks),
                **changes,
            )
            if old.in_progress:
                self.report.pdf_in_progress.append(url)
        elif (bad := self.snapshot.unreadable.get(url)) is not None:
            self.unreadable[url] = replace(bad, title=link.text or bad.title, section=link.section)

    def cannot_read(
        self, ask: _Ask, reason: str, v: Validators, *, lasting: bool, report: bool = True
    ) -> None:
        """Record that ``ask`` is not answered from, and why. A verdict that may be
        different next time is tried again after a backoff that doubles with each
        failure in a row."""
        bad = self.snapshot.unreadable.get(ask.url)
        attempts = bad.attempts + 1 if bad is not None and not bad.lasting and not lasting else 1
        logger.info("kdem: PDF {} is not indexed: {}", ask.url, reason)
        self.unreadable[ask.url] = Unreadable(
            ask.url,
            ask.link.text or (bad.title if bad else "") or file_title(ask.url),
            ask.link.section,
            reason,
            v,
            self.stamp,
            read_with=self.signature,
            lasting=lasting,
            attempts=attempts,
            retry_after="" if lasting else _retry_after(self.now, attempts),
        )
        if report:
            self.report.pdf_unreadable[ask.url] = reason

    def failed(self, ask: _Ask, reason: str, *, gone: bool = False) -> None:
        """The request for ``ask`` failed. A copy held stays (or, when ``gone``,
        goes); a PDF with no copy is recorded, so it waits for its retry time
        instead of taking a new PDF's place every run."""
        old = self.held.get(ask.url)
        if old is not None and not gone:
            self.keep(ask.url, ask.link)
            return
        if old is not None:
            self.chars -= _chars(old)
            self.report.pdf_dropped.append(ask.url)
        bad = self.snapshot.unreadable.get(ask.url)
        prior = old.validators if old else bad.validators if bad else Validators()
        self.cannot_read(ask, reason, prior, lasting=False, report=False)

    async def read(self, fetch_file: FetchFile, ask: _Ask, scratch: Path) -> None:
        """Ask for one PDF and settle what its answer means for the index."""
        url, link = ask.url, ask.link
        old = self.held.get(url)
        bad = self.snapshot.unreadable.get(url)
        prior = old.validators if old else bad.validators if bad else Validators()
        policy = self.policy
        dest = scratch / "file.pdf"
        headers = {} if ask.fresh else prior.conditional()

        async def get(target: str) -> FetchResult:
            return await fetch_file(target, headers, policy.max_pdf_bytes, dest)

        try:
            got = await _follow(get, url, lambda to: pdf_url(to) == url)
        except TooLarge as e:
            if old is not None:
                self.chars -= _chars(old)
            ceiling = f"{policy.max_pdf_bytes / 2**20:.3g} MB"
            self.cannot_read(
                ask, f"larger than the {ceiling} ceiling", Validators.of(e.headers), lasting=True
            )
            return
        except Exception as e:  # a PDF that will not load keeps its last copy
            logger.warning("kdem: could not read PDF {}: {}", url, e)
            self.report.failed.append(url)
            self.failed(ask, f"could not be fetched ({type(e).__name__})")
            return
        if got.status == 304 and (old is not None or bad is not None):
            self.keep(url, link, fetched_at=self.stamp)
            if old is not None:
                self.report.pdf_unchanged.append(url)
            return
        if got.status in (404, 410):
            self.failed(ask, f"not found ({got.status})", gone=True)
            return
        if got.status != 200 and got.status not in REDIRECTS:
            self.report.failed.append(url)
            self.failed(ask, f"answered {got.status}")
            return
        landed = pdf_url(got.url) if got.url else url
        if landed != url:
            # Nothing past the link is followed: a PDF that now lives at another
            # address is judged when a page links that address.
            if landed is None or host_of(landed) != host_of(url):
                logger.warning("kdem: PDF {} redirects to another site, {}", url, got.url)
                self.report.offsite.append(url)
            else:
                logger.warning("kdem: PDF {} now redirects to {}; not indexed", url, got.url)
                self.report.moved.append(url)
            self.failed(ask, f"redirects to {got.url}", gone=True)
            return
        if got.status != 200:  # a redirect back to itself, round and round
            self.report.failed.append(url)
            self.failed(ask, f"answered {got.status}")
            return
        now = replace(Validators.of(got.headers), sha256=got.sha256)
        same = (bool(prior.sha256) and prior.sha256 == now.sha256) or prior.same_file(now)
        settled = old is not None and not old.in_progress and url not in self.forced
        stale = old is not None and bool(old.limited) and old.read_with != self.signature
        if old is not None and same and settled and not stale:
            # The server ignored the conditional request; it is the same file.
            self.keep(url, link, fetched_at=self.stamp, validators=now)
            self.report.pdf_unchanged.append(url)
            return
        if bad is not None and bad.lasting and same and bad.read_with == self.signature:
            self.keep(url, link)
            return
        # Carry on where the last run stopped, if it is the same file; else from
        # the first page.
        carry = old is not None and same and url not in self.forced and old.next_page > 1
        first = old.next_page if carry and old is not None else 1
        kept = old.blocks if carry and old is not None else ()
        if old is not None:
            self.chars -= _chars(old)
        room = policy.max_pdf_chars_total - self.chars
        own = policy.max_pdf_chars - sum(map(len, kept))
        try:
            part = await read_pdf_isolated(
                dest,
                start=first,
                max_pages=policy.pdf_pages_per_run,
                max_chars=max(0, min(own, room)),
                page_timeout_s=policy.pdf_page_timeout_s,
                timeout_s=policy.pdf_timeout_s,
                memory_mb=policy.pdf_memory_mb,
            )
        except PdfUnreadable as e:
            self.cannot_read(ask, e.reason, now, lasting=e.lasting)
            return
        blocks = kept + part.pages
        limited = ""
        if part.stopped == "characters" or (not part.done and min(own, room) <= 0):
            limited = "characters" if own <= room else "cap"
        if limited == "cap":
            self.report.pdf_capped.append(url)
        if limited == "cap" and not any(blocks):
            return  # nothing read yet, and no room for it
        size = sum(map(len, blocks))
        self.chars += size
        title = link.text or part.title or (old.title if old else "") or file_title(url)
        digest = _digest(title, blocks)
        stored = StoredPage(
            url,
            title,
            link.section,
            "auto",
            now.last_modified,
            self.stamp,
            digest,
            blocks,
            kind="pdf",
            pdf_links=(),
            validators=now,
            page_count=part.page_count,
            next_page=part.next_page,
            limited=limited,
            read_with=self.signature,
            host=host_of(url),
        )
        self.pages[url] = stored
        if part.skipped:
            self.report.pdf_skipped_pages[url] = sorted(part.skipped)
        if limited == "characters":
            self.report.pdf_truncated.append(url)
        if stored.in_progress:
            self.report.pdf_in_progress.append(url)
        if old is None:
            self.report.pdf_added.append(url)
        elif old.digest == digest:
            self.report.pdf_unchanged.append(url)
        else:
            self.report.pdf_updated.append(url)


_SCRATCH_PREFIX = "kdem-pdf-"
_SCRATCH_STALE_S = 3600.0


def sweep_scratch(root: Path | None = None, *, older_than_s: float = _SCRATCH_STALE_S) -> int:
    """Remove scratch directories a reader left behind (a process killed
    mid-download, say): ``kdem-pdf-*`` in the temp directory, untouched for
    ``older_than_s``. Returns how many went."""
    root = root or Path(tempfile.gettempdir())
    cutoff = time.time() - older_than_s
    gone = 0
    for d in root.glob(_SCRATCH_PREFIX + "*"):
        with contextlib.suppress(OSError):
            if d.is_dir() and not d.is_symlink() and d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)
                gone += 1
    return gone


async def _refresh_pdfs(
    run: _PdfRun,
    fetch_file: FetchFile | None,
    before_downloads: Callable[[], Awaitable[None]],
) -> dict[str, Unreadable]:
    """The PDF half of a refresh. Adds the PDFs to ``run.pages`` and returns the
    ones that are not answered from, with why.

    - A PDF is read when an approved page in a PDF-reading section links to it,
      on this site or, over https, on another; it is dropped when none does. An
      excluded PDF is ignored; a PDF in a held pattern goes to ``pending_review``.
      Nothing past those links is followed.
    - A PDF is streamed to a scratch file on disk and read from there in a child
      process, a slice of pages a run from its first page, so a document of any
      length is read over a few nights and its beginning is answerable first. A
      page that is too heavy or too slow is skipped; the rest are read.
    - A PDF already read is asked for with its ETag and Last-Modified. A 304, or
      the same file (the same SHA-256, ETag, or Content-Length and
      Last-Modified), keeps what is held. A PDF being read a slice a run is
      downloaded each run and carried on from where it stopped if it is the same
      file, or read again from the first page if it changed.
    - A 404/410 or a redirect drops a PDF; any other failure keeps what is held.
      A PDF that failed is recorded and tried again after a backoff (a day, then
      doubling to a month), so it never takes a new PDF's place in the meantime.
    - New PDFs count toward ``max_new_pdfs``, and all PDFs together toward
      ``max_pdf_chars_total``; what the latter leaves out is reported.
    - A PDF that is encrypted, damaged, has no text, or is past the safety
      ceiling is recorded with why, and not indexed. A verdict reached under
      other limits or another reader version is reached again."""
    asks = run.plan()
    if fetch_file is None:
        for ask in asks:
            run.keep(ask.url, ask.link)
        return run.unreadable
    if asks:
        await before_downloads()
    for ask in asks:
        with tempfile.TemporaryDirectory(prefix=_SCRATCH_PREFIX, ignore_cleanup_errors=True) as d:
            try:
                await run.read(fetch_file, ask, Path(d))
            except Exception as e:  # one PDF never costs the run its pages
                logger.exception("kdem: reading PDF {} failed", ask.url)
                run.report.failed.append(ask.url)
                run.failed(ask, f"could not be read ({type(e).__name__})")
        if run.policy.pause_s:
            await asyncio.sleep(run.policy.pause_s)
    return run.unreadable


def _place(
    allowlist: Allowlist, entry: SitemapEntry, linked: dict[str, str]
) -> tuple[str, str | None]:
    """The section a new URL belongs to, and why it is held (``None``: add it)."""
    if entry.post_type == "page":
        if why := allowlist.held_reason(entry.url):
            return "unsorted", why
        if section := linked.get(entry.url):
            return section, None
        return "unsorted", "a new page no approved hub links to"
    section = allowlist.section_of_type(entry.post_type)
    if section is None:
        return f"type:{entry.post_type}", f"post type {entry.post_type!r} is in no section"
    s = allowlist.sections[section]
    if not s.approved:
        return section, f"section {section!r} is not approved"
    if not s.auto_add:
        return section, f"section {section!r} does not take new pages automatically"
    return section, None


def _for_review(allowlist: Allowlist, url: str) -> bool:
    """Whether a page the list stopped allowing is one a person might put back:
    anything but an excluded URL or an alias, which never become pages."""
    return not (allowlist.is_excluded(url) or allowlist.is_alias(url))


def _older(entry: SitemapEntry, now: datetime, days: int) -> bool:
    t = _parse_time(entry.lastmod)
    return t is None or now - t > timedelta(days=days)


# ─── Search ───────────────────────────────────────────────────────────────────

_TOKEN = re.compile("[\\w\u0300-\u036f\u0900-\u0dff]+")
"""Letters and digits in any script, with the Indic vowel signs kept inside the
word they belong to."""
_STOP = _words(
    "a an and are as at be by can do does for from has have how i in is it its me my "
    "of on or our so that the their them there they this to was we what when where "
    "which who why will with you your about tell"
)
_BOILERPLATE_PAGES = 3
_PASSAGE_CHARS = 700


def tokens(text: str) -> list[str]:
    """Language-agnostic words, case-folded; English plurals folded to the
    singular so "startups" finds "startup"."""
    out: list[str] = []
    for t in _TOKEN.findall(text.casefold()):
        if t in _STOP or t == "_":
            continue
        if t.isascii() and len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        out.append(t)
    return out


@dataclass(frozen=True)
class Passage:
    url: str
    title: str
    snippet: str
    score: float
    page: int | None = None
    """The PDF page the passage is on, from 1; ``None`` for a web page."""
    kind: Kind = "page"


@dataclass(frozen=True)
class PageText:
    url: str
    title: str
    section: str
    lastmod: str
    text: str
    kind: Kind = "page"
    host: str = HOST
    """Where it is served from; another site for a PDF linked from one."""
    via: str = ""
    """A PDF's approved page: the one that links it, offered as the link card
    when the PDF is on another site."""


_K1, _B = 1.2, 0.75


class KnowledgeBase:
    """The pages and PDFs, cleaned and cut into passages, under a BM25 index. In
    memory. A PDF's passages never span two of its pages, so each one has a page
    number."""

    def __init__(self, pages: Iterable[StoredPage], allowlist: Allowlist) -> None:
        self.allowlist = allowlist
        # Checked against the list as it is now, not as it was when the snapshot
        # was written: a page KDEM has taken off it is gone from the next session.
        stored = [p for p in pages if allowlist.permits(p)]
        # And a PDF only while an approved page that is indexed links to it.
        linked = linked_pdfs(allowlist, {p.url: p for p in stored if p.kind == "page"})
        stored = [p for p in stored if p.kind == "page" or p.url in linked]
        # A block that appears on several pages is the site talking about itself
        # (a footer band, a contact blurb, an in-page menu), not the page.
        seen_on: Counter[str] = Counter()
        for p in stored:
            seen_on.update({_clean(b).casefold() for b in p.blocks})
        self._pages: dict[str, PageText] = {}
        self._passages: list[tuple[str, int | None, str]] = []  # (url, PDF page, text)
        for p in stored:
            lines: list[str] = []
            seen: set[str] = set()
            for number, b in enumerate(p.blocks, 1):
                if seen_on[_clean(b).casefold()] >= _BOILERPLATE_PAGES:
                    continue
                kept: list[str] = []
                for ln in b.split("\n"):
                    if ln and ln not in seen:
                        seen.add(ln)
                        kept.append(ln)
                lines += kept
                if p.kind == "pdf":
                    self._passages += ((p.url, number, c) for c in _chunks(kept))
            via = linked[p.url].via if p.kind == "pdf" else ""
            self._pages[p.url] = PageText(
                p.url,
                p.title,
                p.section,
                p.lastmod,
                "\n".join(lines),
                p.kind,
                host_of(p.url),
                via,
            )
            if p.kind == "page":
                self._passages += ((p.url, None, c) for c in _chunks(lines))
        counts: list[Counter[str]] = []
        lengths: list[int] = []
        for url, _, chunk in self._passages:
            toks = tokens(self._pages[url].title) + tokens(chunk)
            counts.append(Counter(toks))
            lengths.append(len(toks))
        n = len(lengths)
        avg = (sum(lengths) / n) if n else 0.0
        df: Counter[str] = Counter()
        for c in counts:
            df.update(c.keys())
        idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}
        # Each posting carries its passage's BM25 weight for the term, worked out
        # here once, so a search only adds them up. Two flat arrays per term:
        # passage numbers, ascending, and weights.
        self._postings: dict[str, tuple[array[int], array[float]]] = {}
        for i, c in enumerate(counts):
            norm = _K1 * (1 - _B + _B * lengths[i] / avg)
            for term, tf in c.items():
                if (posting := self._postings.get(term)) is None:
                    posting = self._postings[term] = (array("i"), array("d"))
                posting[0].append(i)
                posting[1].append(idf[term] * tf * (_K1 + 1) / (tf + norm))
        self._n = n

    @classmethod
    def empty(cls, allowlist: Allowlist) -> KnowledgeBase:
        return cls((), allowlist)

    def __len__(self) -> int:
        return len(self._pages)

    @property
    def pages(self) -> list[PageText]:
        return list(self._pages.values())

    def page(self, url: str) -> PageText | None:
        """The page or PDF ``url`` names, aliases and spelling variants included."""
        c = self.allowlist.locate(url)
        return self._pages.get(c) if c is not None else None

    def search(self, query: str, k: int = 3, *, per_page: int = 2) -> list[Passage]:
        """The ``k`` passages that best answer ``query``, at most ``per_page``
        from any one page or PDF. Empty when nothing matches."""
        postings = [p for t in dict.fromkeys(tokens(query)) if (p := self._postings.get(t))]
        if not postings:
            return []
        acc = [0.0] * self._n
        for ids, weights in postings:
            for i, w in zip(ids, weights, strict=True):
                acc[i] += w
        matched = set[int]().union(*(ids for ids, _ in postings))
        # Best first, without sorting every passage that matched: the few
        # needed come off a heap; only when one page or PDF fills them all is
        # the rest sorted and looked at.
        top = heapq.nlargest(k * per_page * 4, matched, key=acc.__getitem__)

        def ranked() -> Iterator[int]:
            yield from top
            if len(top) < len(matched):
                yield from sorted(matched.difference(top), key=acc.__getitem__, reverse=True)

        out: list[Passage] = []
        per: Counter[str] = Counter()
        for i in ranked():
            score = acc[i]
            url, number, chunk = self._passages[i]
            if per[url] >= per_page:
                continue
            per[url] += 1
            page = self._pages[url]
            out.append(Passage(url, page.title, chunk, round(score, 3), number, page.kind))
            if len(out) >= k:
                break
        return out


def _chunks(lines: Sequence[str]) -> list[str]:
    out: list[str] = []
    buf: list[str] = []
    size = 0
    for ln in lines:
        if len(ln) > _PASSAGE_CHARS:
            ln = ln[:_PASSAGE_CHARS].rsplit(" ", 1)[0] + " ..."
        if buf and size + len(ln) > _PASSAGE_CHARS:
            out.append("\n".join(buf))
            buf, size = [], 0
        buf.append(ln)
        size += len(ln) + 1
    if buf:
        out.append("\n".join(buf))
    return out


# ─── The keeper ───────────────────────────────────────────────────────────────


class KnowledgeService:
    """One per process: holds the current :class:`KnowledgeBase` and keeps it fresh.

    ``start()`` from ``on_session_start``: it returns at once, and on the first
    call starts a background task that loads the snapshot from disk, then
    refreshes it whenever it is about a day old (immediately, when there is none),
    jittered so a fleet does not arrive together. A failed refresh is logged and
    retried within the hour; the last good index stays in use. ``kb`` is safe to
    read from a tool at any moment."""

    def __init__(
        self,
        allowlist: Allowlist,
        *,
        cache_dir: Path | None = None,
        fetch: Fetch = http_fetch,
        fetch_file: FetchFile = http_fetch_file,
        policy: RefreshPolicy | None = None,
        every_s: float = REFRESH_EVERY_S,
        jitter_s: float = REFRESH_JITTER_S,
    ) -> None:
        self.allowlist = allowlist
        self._cache_dir = cache_dir
        self._fetch = fetch
        self._fetch_file = fetch_file
        self._policy = policy or RefreshPolicy()
        self._every_s = every_s
        self._jitter_s = jitter_s
        self._snapshot = Snapshot()
        self._kb = KnowledgeBase.empty(allowlist)
        self._loaded_mtime: float | None = None
        self._task: asyncio.Task[None] | None = None
        self._refreshing = False
        self._primed = False
        self._retry_at: float | None = None

    @property
    def path(self) -> Path:
        return (self._cache_dir or default_cache_dir()) / SNAPSHOT_FILE

    @property
    def kb(self) -> KnowledgeBase:
        return self._kb

    @property
    def snapshot(self) -> Snapshot:
        return self._snapshot

    def prime(self, snapshot: Snapshot) -> None:
        """Install ``snapshot`` and turn the background task off. For tests and
        fixtures: nothing touches the disk or the network afterwards."""
        self._install(snapshot)
        self._primed = True

    def _install(self, snapshot: Snapshot, kb: KnowledgeBase | None = None) -> None:
        self._kb = kb or KnowledgeBase(snapshot.pages.values(), self.allowlist)
        self._snapshot = snapshot

    def start(self) -> None:
        """Make sure the background keeper is running on this event loop. Cheap
        and idempotent: call it from every ``on_session_start``."""
        if self._primed or os.environ.get(ENV_REFRESH, "").lower() in ("off", "0", "false"):
            if not self._primed:
                self._reload_if_changed()
            return
        loop = asyncio.get_running_loop()
        task = self._task
        if task is not None and not task.done() and task.get_loop() is loop:
            self._reload_if_changed()
            return
        self._task = loop.create_task(self._run(), name="kdem-knowledge")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def _mtime(self) -> float | None:
        try:
            return self.path.stat().st_mtime
        except OSError:
            return None

    def _reload_if_changed(self) -> None:
        """A snapshot written by hand (the CLI) is picked up by the next session."""
        if self._refreshing:
            return
        m = self._mtime()
        if m is not None and m != self._loaded_mtime:
            self._loaded_mtime = m
            with contextlib.suppress(RuntimeError):
                asyncio.get_running_loop().create_task(self._load())

    async def _load(self) -> None:
        m = self._mtime()
        snap = await asyncio.to_thread(Snapshot.load, self.path)
        if snap is not None and snap.built_at >= self._snapshot.built_at:
            kb = await asyncio.to_thread(KnowledgeBase, snap.pages.values(), self.allowlist)
            self._install(snap, kb)
            self._loaded_mtime = m
            logger.info("kdem: knowledge loaded, {} pages from {}", len(kb), self.path)

    def _due_in(self) -> float:
        if self._retry_at is not None:
            return max(0.0, self._retry_at - time.time())
        built = _parse_time(self._snapshot.built_at)
        if built is None:
            return 0.0
        age = (datetime.now(UTC) - built).total_seconds()
        jitter = random.uniform(-self._jitter_s, self._jitter_s)
        return max(0.0, self._every_s + jitter - age)

    async def _run(self) -> None:
        with contextlib.suppress(Exception):
            if swept := await asyncio.to_thread(sweep_scratch):
                logger.info("kdem: removed {} stale PDF scratch directories", swept)
        try:
            await self._load()
        except Exception as e:
            logger.warning("kdem: could not load the knowledge snapshot: {}", e)
        while True:
            await asyncio.sleep(self._due_in())
            try:
                await self.refresh_now()
            except Exception as e:
                self._retry_at = time.time() + RETRY_AFTER_S + random.uniform(0, 600)
                logger.warning("kdem: knowledge refresh failed, keeping the last copy: {}", e)

    async def refresh_now(self, *, policy: RefreshPolicy | None = None) -> RefreshReport:
        """One refresh, start to finish: read, rebuild the index, swap it in, save.
        Raises on failure, leaving the current index in place."""
        if self._refreshing:
            raise _fail("a refresh is already running")
        self._refreshing = True

        async def progress(partial: Snapshot) -> None:
            # Answer from the pages already read while the new ones are fetched —
            # on a fresh host that is every approved page, minutes sooner. Not
            # saved: only a finished refresh is written to disk.
            kb = await asyncio.to_thread(KnowledgeBase, partial.pages.values(), self.allowlist)
            self._install(partial, kb)
            logger.info("kdem: knowledge in use, {} pages, while the rest are read", len(kb))

        try:
            snap, report = await refresh(
                self._snapshot,
                self.allowlist,
                self._fetch,
                fetch_file=self._fetch_file,
                policy=policy or self._policy,
                on_progress=progress,
            )
            kb = await asyncio.to_thread(KnowledgeBase, snap.pages.values(), self.allowlist)
            self._install(snap, kb)
            self._retry_at = None
            try:
                await asyncio.to_thread(snap.save, self.path)
                self._loaded_mtime = self._mtime()
            except OSError as e:
                logger.warning("kdem: could not save the knowledge snapshot: {}", e)
            logger.info("kdem: knowledge refreshed, {} pages: {}", len(kb), report.summary())
            return report
        finally:
            self._refreshing = False


ALLOWLIST = Allowlist.load()
"""Read once at import; a malformed allowlist stops the brain from starting."""

KNOWLEDGE = KnowledgeService(ALLOWLIST)
"""The process-wide keeper. The brain calls ``KNOWLEDGE.start()`` per session and
reads ``KNOWLEDGE.kb`` from its tools."""


# ─── By hand ──────────────────────────────────────────────────────────────────


def _cite(p: Passage) -> str:
    if p.kind != "pdf":
        return p.title
    where = "PDF" if not off_site(p.url) else f"PDF on {host_of(p.url)}"
    return f"{p.title} ({where}, page {p.page})" if p.page else f"{p.title} ({where})"


def main(argv: Sequence[str] | None = None) -> int:
    """``refresh`` (re-read what changed and save), ``search QUERY``, ``pending``."""
    parser = argparse.ArgumentParser(prog="knowledge.py", description=main.__doc__)
    parser.add_argument("--cache-dir", type=Path, default=None, help=f"default: ${ENV_DIR}")
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("refresh", help="read the sitemap and re-read what changed")
    r.add_argument(
        "--force", action="append", default=[], metavar="URL", help="re-read this page or PDF"
    )
    r.add_argument("--rebuild", action="store_true", help="start from an empty snapshot")
    r.add_argument("--max-new", type=int, default=RefreshPolicy.max_new)
    r.add_argument("--max-new-pdfs", type=int, default=RefreshPolicy.max_new_pdfs)
    s = sub.add_parser("search", help="search the saved snapshot")
    s.add_argument("query")
    s.add_argument("-k", type=int, default=5)
    sub.add_parser("pending", help="list pages held for review and PDFs that cannot be read")
    args = parser.parse_args(argv)

    service = KnowledgeService(ALLOWLIST, cache_dir=args.cache_dir)
    snap = Snapshot.load(service.path)
    if snap is not None and not (args.command == "refresh" and args.rebuild):
        service.prime(snap)
    if args.command == "refresh":
        policy = RefreshPolicy(
            max_new=args.max_new, max_new_pdfs=args.max_new_pdfs, force=frozenset(args.force)
        )
        report = asyncio.run(service.refresh_now(policy=policy))
        pdfs = sum(p.kind == "pdf" for p in service.kb.pages)
        print(f"{service.path}: {len(service.kb) - pdfs} pages, {pdfs} PDFs; {report.summary()}")
        for label, urls in (
            ("updated", report.updated),
            ("added", report.added),
            ("held", report.held),
            ("dropped", report.dropped),
            ("failed", report.failed),
            ("off-site", report.offsite),
            ("moved", report.moved),
            ("pdf added", report.pdf_added),
            ("pdf updated", report.pdf_updated),
            ("pdf dropped", report.pdf_dropped),
            ("truncated", report.pdf_truncated),
            ("over cap", report.pdf_capped),
            ("in progress", report.pdf_in_progress),
        ):
            for u in urls:
                print(f"  {label:11} {u}")
        for u, why in report.pdf_unreadable.items():
            print(f"  {'unreadable':11} {u}  ({why})")
        for u, numbers in report.pdf_skipped_pages.items():
            print(f"  {'skipped':11} {u}  (pages {', '.join(map(str, numbers))})")
        return 1 if report.failed else 0
    if args.command == "search":
        for p in service.kb.search(args.query, args.k):
            print(f"[{p.score}] {_cite(p)} <{p.url}>\n  {p.snippet.replace(chr(10), ' / ')[:300]}")
        return 0
    for p in sorted(service.snapshot.pending_review.values(), key=lambda p: p.url):
        print(f"{p.section:24} {p.url}  ({p.reason})")
    for u in sorted(service.snapshot.unreadable.values(), key=lambda u: u.url):
        retry = f"; tried again after {u.retry_after}" if u.retry_after else ""
        print(f"{'unreadable PDF':24} {u.url}  ({u.reason}{retry})")
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == [_WORKER_FLAG]:
        sys.exit(_pdf_worker(sys.argv[2:]))
    sys.exit(main())
