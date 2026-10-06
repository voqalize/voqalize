"""KDEM's PDFs: found from the approved pages' links, read page by page, kept fresh.

No network: every PDF here is built in the test from a few neutral sentences,
and served by a fake file fetcher (one test serves files from a local directory
over loopback, to pin the real downloader's conditional and size handling).

What is worth pinning:

**Found from links, not from the sitemap.** A PDF is read when an approved page
in a PDF-reading section links to it on the site, and dropped as soon as none
does. Off-site, excluded and held PDFs are not read.

**Read only when it changed.** A PDF already held is asked for with its ETag and
Last-Modified; a 304, or a server that ignores the question but sends the same
Content-Length and Last-Modified, keeps the text already held.

**Never a crash.** A PDF that is too large, encrypted, damaged or scanned is
recorded with the reason and not indexed.

Run: ``cd demos && uv run pytest tests/test_kdem_pdfs.py``
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import io
import itertools
import json
import random
import sys
import threading
import time
import zlib
from collections.abc import Iterator, Mapping
from datetime import timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

from .test_kdem_knowledge import NOW, FakeSite, _days_ago, _page

from voqalize_demos._loaded.kdem import knowledge  # isort: skip
from voqalize_demos._loaded.kdem.knowledge import (  # isort: skip
    Allowlist,
    FetchResult,
    KnowledgeBase,
    KnowledgeService,
    PdfUnreadable,
    RefreshPolicy,
    Snapshot,
    StoredPage,
    TooLarge,
    _download_file,  # pyright: ignore[reportPrivateUsage]
    file_title,
    normalize,
    read_pdf,
    read_pdf_isolated,
    reader_signature,
    refresh,
)

SITE = "https://karnatakadigital.in"
UP = "/wp-content/uploads/2026/01"
POLICY = f"{UP}/sample-startup-policy.pdf"
GUIDE = f"{UP}/Sample_Guidelines-2026.pdf"

P1 = "The sample startup policy sets out how the state supports young companies in every district."
P2 = (
    "Chapter two describes an incu-\nbator grant for student founders working on hardware projects."
)
P3 = "Chapter three lists the documents an applicant keeps ready before the review meeting begins."


# ─── Building PDFs ────────────────────────────────────────────────────────────


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(pages: list[str | bytes], *, title: str = "") -> bytes:
    """A small, valid PDF: one Helvetica text block per page, a line per ``\\n``.
    An empty string is a page with a drawing and no text, as a scan would be;
    ``bytes`` are a page's raw content operators, stored compressed."""
    objects: list[bytes] = [b"<< /Type /Catalog /Pages 2 0 R >>"]
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(len(pages)))
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for i, text in enumerate(pages):
        flate = ""
        if isinstance(text, bytes):
            stream = zlib.compress(b"BT /F1 10 Tf 12 TL 40 760 Td " + text + b" ET", 9)
            flate = " /Filter /FlateDecode"
        else:
            if text:
                shown = " ".join(f"({_esc(line)}) Tj T*" for line in text.split("\n"))
                ops = f"BT /F1 10 Tf 12 TL 40 760 Td {shown} ET"
            else:
                ops = "0.5 g 40 40 500 700 re f"
            stream = ops.encode("latin-1")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * i} 0 R >>".encode()
        )
        objects.append(
            b"<< /Length %d%s >>\nstream\n%s\nendstream" % (len(stream), flate.encode(), stream)
        )
    info = ""
    if title:
        objects.append(f"<< /Title ({_esc(title)}) >>".encode())
        info = f" /Info {len(objects)} 0 R"
    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for n, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (n, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R{info} >>\n".encode()
    out += b"startxref\n%d\n%%%%EOF\n" % xref
    return bytes(out)


def encrypted(data: bytes, *, user: str, owner: str = "owner-secret") -> bytes:
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(data)))
    writer.encrypt(user_password=user, owner_password=owner, algorithm="RC4-128")
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# ─── Reading one ──────────────────────────────────────────────────────────────


def test_read_pdf_keeps_each_page_apart_and_mends_hyphenation() -> None:
    pdf = read_pdf(make_pdf([P1, P2, P3], title="Sample Startup Policy"))
    assert len(pdf.pages) == 3
    assert "young companies" in pdf.pages[0]
    assert "incubator grant" in pdf.pages[1]  # "incu-" + "bator" across a line end
    assert "review meeting" in pdf.pages[2]
    assert pdf.title == "Sample Startup Policy"
    assert pdf.done and pdf.page_count == 3 and not pdf.skipped and not pdf.stopped


def test_read_pdf_reads_a_slice_and_carries_on_from_where_it_stopped() -> None:
    data = make_pdf([P1 + "\n" + P2, P2 + "\n" + P3, P3 + "\n" + P1])
    first = read_pdf(data, max_pages=2)
    assert len(first.pages) == 2 and first.next_page == 3 and not first.done
    rest = read_pdf(data, start=first.next_page, max_pages=2)
    assert rest.start == 3 and len(rest.pages) == 1 and rest.done
    assert "review meeting" in rest.pages[0]
    capped = read_pdf(data, max_chars=len(P1) + len(P2) + 60)
    assert capped.stopped == "characters" and not capped.done
    assert len("".join(capped.pages)) <= len(P1) + len(P2) + 60


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (encrypted(make_pdf([P1]), user="visitor-secret"), "encrypted"),
        (make_pdf(["", "", ""]), "no text layer"),
        (make_pdf(["", "7", ""]), "no text layer"),
        (b"%PDF-1.4\n" + b"\x00garbled" * 50, "damaged"),
        (b"<html><body>Not a document</body></html>", "not a PDF"),
    ],
    ids=["password", "scanned", "page-number-only", "damaged", "html"],
)
def test_an_unreadable_pdf_says_why(data: bytes, reason: str) -> None:
    with pytest.raises(PdfUnreadable) as e:
        read_pdf(data)
    assert reason in e.value.reason


def test_a_pdf_with_only_an_owner_password_is_read() -> None:
    pdf = read_pdf(encrypted(make_pdf([P1, P2]), user=""))
    assert "young companies" in pdf.pages[0]


def test_a_pdf_link_is_named_by_its_text_or_by_the_heading_of_its_own_card() -> None:
    html = _page(
        f"""<main id="main">
        <div class="card"><img src="a.jpg" alt=""><h4>Operational Guidelines for the Sample Policy</h4>
          <a href="{UP}/opg.pdf"><span>View More</span></a></div>
        <div class="card"><h4>Sample Annual Report</h4>
          <a href="{UP}/report.pdf" title="Annual report 2026">  </a></div>
        <h2>Monthly newsletters</h2>
        <div><a href="{UP}/news-may.pdf">Download Now</a></div>
        <div><a href="{UP}/news-june.pdf">Download Now</a></div>
        <p><a href="{UP}/plan.pdf">The Sample Plan</a> and
          <a href="https://example.org/docs/Other%20Plan.pdf?v=2">Another site's plan</a> and
          <a href="http://example.org/plain.pdf">Over plain http</a> and
          <a href="https://example.org/a-page/">An HTML page elsewhere</a></p>
        </main>"""
    )
    named = dict(knowledge.extract(html).pdf_links)
    assert named == {
        f"{SITE}{UP}/opg.pdf": "Operational Guidelines for the Sample Policy",
        f"{SITE}{UP}/report.pdf": "Annual report 2026",  # its own title attribute first
        # One heading over two buttons names neither: they fall back to the file.
        f"{SITE}{UP}/news-may.pdf": "",
        f"{SITE}{UP}/news-june.pdf": "",
        f"{SITE}{UP}/plan.pdf": "The Sample Plan",
        # A PDF on another site, over https, is read; plain http and HTML are not.
        "https://example.org/docs/Other%20Plan.pdf": "Another site's plan",
    }


def test_file_title() -> None:
    assert file_title(f"{SITE}{GUIDE}") == "Sample Guidelines 2026"
    assert file_title(f"{SITE}{UP}/A%20Plan.PDF") == "A Plan"


# ─── Finding and refreshing them ──────────────────────────────────────────────


def _allowlist_doc() -> dict[str, object]:
    return {
        "site": SITE,
        "sitemap": f"{SITE}/wp-sitemap.xml",
        "contact_url": f"{SITE}/contact-us/",
        "sections": {
            "core": {"approved": True, "auto_add": False, "post_types": ["page"]},
            "docs": {"approved": True, "auto_add": True, "post_types": ["page"], "read_pdfs": True},
        },
        "pages": [
            {"url": f"{SITE}/contact-us/", "title": "Contact Us", "section": "core"},
            {"url": f"{SITE}/policies/", "title": "Policies", "section": "docs", "hub_for": "docs"},
            {"url": f"{SITE}/reports/", "title": "Reports", "section": "docs"},
        ],
        "excluded_patterns": [
            {"pattern": "^/wp-(json|admin|includes)/", "why": "internals"},
            {"pattern": "^/wp-content/(?!uploads/.*\\.(?i:pdf)$)", "why": "internals"},
        ],
        "held_patterns": [{"pattern": "speaker", "why": "about individuals"}],
    }


def _anchors(*links: tuple[str, str]) -> str:
    return "".join(f'<p><a href="{href}">{text}</a></p>' for href, text in links)


def _hub(*links: tuple[str, str]) -> str:
    return _page(
        f'<main id="main"><article><p>Our documents.</p>{_anchors(*links)}</article></main>'
    )


class FakeFiles:
    """The uploads directory: files by path, with an ETag and Last-Modified each."""

    def __init__(self) -> None:
        self.files: dict[str, tuple[bytes, dict[str, str]]] = {}
        self.redirects: dict[str, str] = {}
        self.honours_conditionals = True
        self.requests: list[tuple[str, dict[str, str]]] = []

    def put(self, path: str, data: bytes, *, version: int = 1, etag: bool = True) -> None:
        headers = {"last-modified": f"Mon, 0{version} Jun 2026 10:00:00 GMT"}
        if etag:
            headers["etag"] = f'"v{version}"'
        self.files[path] = (data, headers)

    async def fetch(
        self, url: str, headers: Mapping[str, str], max_bytes: int, dest: Path
    ) -> FetchResult:
        path = url.removeprefix(SITE)
        self.requests.append((path, dict(headers)))
        if path not in self.files:
            return FetchResult(404, url, "")
        data, h = self.files[path]
        h = {**h, "content-length": str(len(data))}
        if self.honours_conditionals and (
            ("etag" in h and headers.get("If-None-Match") == h["etag"])
            or headers.get("If-Modified-Since") == h["last-modified"]
        ):
            return FetchResult(304, url, "", h)
        if len(data) > max_bytes:
            raise TooLarge(len(data), h)
        dest.write_bytes(data)
        landed = self.redirects.get(path, url)
        return FetchResult(200, landed, "", h, len(data), hashlib.sha256(data).hexdigest())

    def paths(self) -> list[str]:
        return [p for p, _ in self.requests]


@pytest.fixture
def allowlist() -> Allowlist:
    return Allowlist.from_json(_allowlist_doc())


@pytest.fixture
def site() -> FakeSite:
    s = FakeSite()
    s.sitemaps = {
        "page": {
            "/contact-us/": _days_ago(30),
            "/policies/": _days_ago(30),
            "/reports/": _days_ago(30),
        }
    }
    s.pages = {
        # The contact page is in a section that does not read PDFs.
        "/contact-us/": _hub((f"{UP}/contact-form.pdf", "Contact form")),
        "/policies/": _hub(
            (POLICY, "Sample Startup Policy"),
            ("http://example.org/wp-content/uploads/elsewhere.pdf", "Over plain http"),
            ("/wp-content/plugins/bundled.pdf", "A plugin's file"),
            (f"{UP}/speaker-list.pdf", "Speakers"),
        ),
        "/reports/": _hub((GUIDE, "Download"), (POLICY, "The policy again")),
    }
    return s


@pytest.fixture
def files() -> FakeFiles:
    f = FakeFiles()
    f.put(POLICY, make_pdf([P1, P2, P3]))
    f.put(GUIDE, make_pdf([P3 + " Guidelines for the review panel."], title="Sample Guidelines"))
    f.put(f"{UP}/contact-form.pdf", make_pdf([P1]))
    f.put(f"{UP}/speaker-list.pdf", make_pdf([P1]))
    return f


async def _refresh(
    snap: Snapshot, al: Allowlist, site: FakeSite, files: FakeFiles, **policy: object
) -> tuple[Snapshot, knowledge.RefreshReport]:
    return await refresh(
        snap,
        al,
        site.fetch,
        fetch_file=files.fetch,
        policy=RefreshPolicy(pause_s=0, **policy),  # type: ignore[arg-type]
        now=NOW,
    )


async def test_pdfs_are_found_from_the_approved_pages_links(
    allowlist: Allowlist, site: FakeSite, files: FakeFiles
) -> None:
    snap, report = await _refresh(Snapshot(), allowlist, site, files)
    pdfs = {u: p for u, p in snap.pages.items() if p.kind == "pdf"}
    assert set(pdfs) == {f"{SITE}{POLICY}", f"{SITE}{GUIDE}"}
    assert sorted(report.pdf_added) == sorted(pdfs)
    policy = pdfs[f"{SITE}{POLICY}"]
    assert (
        policy.title == "Sample Startup Policy"
    )  # the link text, from the first page that links it
    assert policy.section == "docs"
    assert len(policy.blocks) == 3
    assert policy.validators.etag == '"v1"'
    # "Download" names nothing: the file's own metadata title does.
    assert pdfs[f"{SITE}{GUIDE}"].title == "Sample Guidelines"
    # Off the site over plain http, excluded, held, or linked from a section
    # that does not read PDFs: never asked for.
    assert sorted(files.paths()) == sorted([POLICY, GUIDE])
    assert f"{SITE}{UP}/speaker-list.pdf" in snap.pending_review
    assert f"{SITE}{UP}/speaker-list.pdf" in report.held

    kb = KnowledgeBase(snap.pages.values(), allowlist)
    (hit,) = kb.search("incubator grant for student founders", k=1)
    assert (hit.url, hit.page, hit.kind) == (f"{SITE}{POLICY}", 2, "pdf")
    assert hit.title == "Sample Startup Policy"
    assert "incubator grant" in hit.snippet
    hub = kb.page(f"{SITE}/policies/")
    assert hub is not None and hub.kind == "page"


OTHER = "https://portal.example.gov/docs/Sample-State-Scheme.pdf"


async def test_a_pdf_on_another_site_is_read_and_remembers_where_it_is(
    allowlist: Allowlist, site: FakeSite, files: FakeFiles
) -> None:
    """Linked from an approved page, over https: read like any other, with its
    host recorded and the approved page that links it known to the index."""
    site.pages["/policies/"] = _hub(
        (POLICY, "Sample Startup Policy"),
        ("https://portal.example.gov/docs/Sample-State-Scheme.pdf#page=2", "Sample State Scheme"),
    )
    files.put(
        OTHER, make_pdf([P1 + "\n" + P2, "A state scheme for lantern makers in every district."])
    )
    snap, report = await _refresh(Snapshot(), allowlist, site, files)
    assert OTHER in report.pdf_added
    stored = snap.pages[OTHER]
    assert stored.host == "portal.example.gov" and stored.title == "Sample State Scheme"
    kb = KnowledgeBase(snap.pages.values(), allowlist)
    indexed = kb.page(OTHER)
    assert indexed is not None and indexed.via == f"{SITE}/policies/"
    assert indexed.host == "portal.example.gov"
    (hit,) = kb.search("lantern makers", k=1)
    assert (hit.url, hit.page) == (OTHER, 2)
    assert OTHER in files.paths()  # one request, for the PDF; nothing past it

    # The same document redirecting to yet another host is not followed.
    files.redirects[OTHER] = "https://mirror.example.net/Sample-State-Scheme.pdf"
    files.put(OTHER, make_pdf([P1 + "\n" + P2]), version=2)
    snap2, report2 = await _refresh(snap, allowlist, site, files)
    assert OTHER not in snap2.pages and report2.offsite == [OTHER]


async def test_an_unchanged_pdf_is_asked_about_not_read_again(
    allowlist: Allowlist, site: FakeSite, files: FakeFiles, monkeypatch: pytest.MonkeyPatch
) -> None:
    snap, _ = await _refresh(Snapshot(), allowlist, site, files)
    files.requests.clear()

    async def must_not_read(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("an unchanged PDF was read again")

    monkeypatch.setattr(knowledge, "read_pdf_isolated", must_not_read)
    snap2, report = await _refresh(snap, allowlist, site, files)
    asked = dict(files.requests)
    assert asked[POLICY] == {
        "If-None-Match": '"v1"',
        "If-Modified-Since": files.files[POLICY][1]["last-modified"],
    }
    assert sorted(report.pdf_unchanged) == [f"{SITE}{GUIDE}", f"{SITE}{POLICY}"]
    assert snap2.pages[f"{SITE}{POLICY}"].blocks == snap.pages[f"{SITE}{POLICY}"].blocks

    # A server that ignores the question but sends the same length and date: kept.
    files.honours_conditionals = False
    snap3, report = await _refresh(snap2, allowlist, site, files)
    assert sorted(report.pdf_unchanged) == [f"{SITE}{GUIDE}", f"{SITE}{POLICY}"]
    assert snap3.pages[f"{SITE}{POLICY}"].blocks == snap.pages[f"{SITE}{POLICY}"].blocks


async def test_a_changed_pdf_is_read_again(
    allowlist: Allowlist, site: FakeSite, files: FakeFiles
) -> None:
    snap, _ = await _refresh(Snapshot(), allowlist, site, files)
    files.put(
        POLICY,
        make_pdf([P1, "Chapter two now covers a lantern workshop for every district."]),
        version=2,
    )
    snap2, report = await _refresh(snap, allowlist, site, files)
    assert report.pdf_updated == [f"{SITE}{POLICY}"]
    assert len(snap2.pages[f"{SITE}{POLICY}"].blocks) == 2
    kb = KnowledgeBase(snap2.pages.values(), allowlist)
    assert kb.search("lantern workshop")[0].page == 2
    assert kb.search("review meeting")[0].url == f"{SITE}{GUIDE}"  # page 3 of the policy is gone


async def test_a_forced_pdf_is_downloaded_whatever_its_validators(
    allowlist: Allowlist, site: FakeSite, files: FakeFiles
) -> None:
    snap, _ = await _refresh(Snapshot(), allowlist, site, files)
    files.requests.clear()
    _, report = await _refresh(snap, allowlist, site, files, force=frozenset({f"{SITE}{POLICY}"}))
    assert dict(files.requests)[POLICY] == {}
    assert report.pdf_unchanged.count(f"{SITE}{POLICY}") == 1  # read, and the same text


async def test_a_pdf_no_page_links_to_any_more_is_dropped(
    allowlist: Allowlist, site: FakeSite, files: FakeFiles
) -> None:
    snap, _ = await _refresh(Snapshot(), allowlist, site, files)
    site.pages["/reports/"] = _hub((POLICY, "Sample Startup Policy"))
    site.sitemaps["page"]["/reports/"] = _days_ago(0)
    snap2, report = await _refresh(snap, allowlist, site, files)
    assert report.pdf_dropped == [f"{SITE}{GUIDE}"]
    assert f"{SITE}{GUIDE}" not in snap2.pages
    assert f"{SITE}{POLICY}" in snap2.pages

    # And the index never answers from a PDF the pages it holds do not link to,
    # whatever an older snapshot carried.
    stale = dict(snap2.pages) | {f"{SITE}{GUIDE}": snap.pages[f"{SITE}{GUIDE}"]}
    kb = KnowledgeBase(stale.values(), allowlist)
    assert kb.page(f"{SITE}{GUIDE}") is None
    assert kb.page(f"{SITE}{POLICY}") is not None


async def test_a_pdf_that_is_gone_is_dropped_and_one_that_fails_is_kept(
    allowlist: Allowlist, site: FakeSite, files: FakeFiles
) -> None:
    snap, _ = await _refresh(Snapshot(), allowlist, site, files)
    del files.files[GUIDE]

    async def flaky(
        url: str, headers: Mapping[str, str], max_bytes: int, dest: Path
    ) -> FetchResult:
        if url.endswith(POLICY):
            raise OSError("timed out")
        return await files.fetch(url, headers, max_bytes, dest)

    snap2, report = await refresh(
        snap, allowlist, site.fetch, fetch_file=flaky, policy=RefreshPolicy(pause_s=0), now=NOW
    )
    assert report.pdf_dropped == [f"{SITE}{GUIDE}"]
    assert report.failed == [f"{SITE}{POLICY}"]
    assert snap2.pages[f"{SITE}{POLICY}"].blocks == snap.pages[f"{SITE}{POLICY}"].blocks


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (b"%PDF-1.4\n" + b"x" * 5000, "larger than"),
        (encrypted(make_pdf([P1]), user="visitor-secret"), "encrypted"),
        (make_pdf(["", ""]), "no text layer"),
    ],
    ids=["oversized", "encrypted", "scanned"],
)
async def test_an_unreadable_pdf_is_reported_and_not_indexed(
    allowlist: Allowlist, site: FakeSite, files: FakeFiles, data: bytes, reason: str
) -> None:
    files.put(GUIDE, data)
    limit = 4000 if reason == "larger than" else 25 * 1024 * 1024
    snap, report = await _refresh(Snapshot(), allowlist, site, files, max_pdf_bytes=limit)
    url = f"{SITE}{GUIDE}"
    assert reason in report.pdf_unreadable[url]
    assert url not in snap.pages
    assert reason in snap.unreadable[url].reason
    assert KnowledgeBase(snap.pages.values(), allowlist).page(url) is None
    assert f"{SITE}{POLICY}" in snap.pages  # the run went on

    # Next run: asked about with its validators, not downloaded again.
    files.requests.clear()
    snap2, report2 = await _refresh(snap, allowlist, site, files, max_pdf_bytes=limit)
    assert dict(files.requests)[GUIDE]["If-None-Match"] == '"v1"'
    assert url in snap2.unreadable and url not in report2.pdf_unreadable


async def test_new_pdfs_beyond_the_cap_wait_and_the_pages_are_handed_over_first(
    allowlist: Allowlist, site: FakeSite, files: FakeFiles
) -> None:
    extra = [(f"{UP}/note-{i}.pdf", f"Note {i}") for i in range(3)]
    for path, _ in extra:
        files.put(path, make_pdf([P3 + "\n" + P1]))
    site.pages["/policies/"] = _hub((POLICY, "Sample Startup Policy"), *extra)
    seen: list[set[str]] = []

    async def progress(partial: Snapshot) -> None:
        seen.append({u for u, p in partial.pages.items() if p.kind == "page"})

    snap, report = await refresh(
        Snapshot(),
        allowlist,
        site.fetch,
        fetch_file=files.fetch,
        policy=RefreshPolicy(pause_s=0, max_new_pdfs=2),
        now=NOW,
        on_progress=progress,
    )
    assert report.pdf_deferred == 3  # policy, three notes and the guidelines: five new
    assert sum(p.kind == "pdf" for p in snap.pages.values()) == 2
    assert len(seen) == 2 and seen[-1] == {
        f"{SITE}/contact-us/",
        f"{SITE}/policies/",
        f"{SITE}/reports/",
    }
    _, report2 = await _refresh(snap, allowlist, site, files, max_new_pdfs=10)
    assert len(report2.pdf_added) == 3 and report2.pdf_deferred == 0


async def test_without_a_file_fetcher_the_linked_pdfs_are_kept_as_held(
    allowlist: Allowlist, site: FakeSite, files: FakeFiles
) -> None:
    snap, _ = await _refresh(Snapshot(), allowlist, site, files)
    snap2, _ = await refresh(snap, allowlist, site.fetch, policy=RefreshPolicy(pause_s=0), now=NOW)
    assert snap2.pages[f"{SITE}{POLICY}"] == snap.pages[f"{SITE}{POLICY}"]


# ─── The snapshot ─────────────────────────────────────────────────────────────


async def test_pdfs_and_unreadable_files_round_trip_through_the_snapshot(
    tmp_path: Path, allowlist: Allowlist, site: FakeSite, files: FakeFiles
) -> None:
    files.put(f"{UP}/scan.pdf", make_pdf(["", ""]))
    site.pages["/reports/"] = _hub((GUIDE, "Download"), (f"{UP}/scan.pdf", "A scanned notice"))
    service = KnowledgeService(
        allowlist, cache_dir=tmp_path, fetch=site.fetch, fetch_file=files.fetch
    )
    await service.refresh_now(policy=RefreshPolicy(pause_s=0))
    loaded = Snapshot.load(service.path)
    assert loaded is not None
    assert loaded.pages == service.snapshot.pages
    assert loaded.unreadable == service.snapshot.unreadable
    assert loaded.unreadable[f"{SITE}{UP}/scan.pdf"].title == "A scanned notice"
    assert service.kb.search("incubator grant")[0].page == 2


async def test_a_version_1_snapshot_loads_and_its_pages_pdf_links_are_read(
    tmp_path: Path, allowlist: Allowlist, site: FakeSite, files: FakeFiles
) -> None:
    """Written before PDFs were read: no ``kind``, no ``pdf_links``. It loads as
    pages, and a page PDFs are found from is read again though its ``lastmod``
    has not moved, so its PDFs are found on the first refresh after the upgrade."""
    old = {
        "version": 1,
        "built_at": "2026-10-01T00:00:00+00:00",
        "known": {f"{SITE}{p}": lm for p, lm in site.sitemaps["page"].items()},
        "pages": [
            {
                "url": f"{SITE}{path}",
                "title": title,
                "section": section,
                "origin": "approved",
                "lastmod": site.sitemaps["page"][path],
                "fetched_at": "2026-10-01T00:00:00+00:00",
                "digest": "0",
                "blocks": ["Our documents."],
                "links": [],
            }
            for path, title, section in (
                ("/contact-us/", "Contact Us", "core"),
                ("/policies/", "Policies", "docs"),
                ("/reports/", "Reports", "docs"),
            )
        ],
        "pending_review": [],
    }
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(old), encoding="utf-8")
    snap = Snapshot.load(path)
    assert snap is not None
    assert all(p.kind == "page" and p.pdf_links is None for p in snap.pages.values())
    assert snap.unreadable == {}
    assert len(KnowledgeBase(snap.pages.values(), allowlist)) == 3

    _, report = await _refresh(snap, allowlist, site, files)
    assert sorted(site.page_reads()) == ["/policies/", "/reports/"]  # not the contact page
    assert f"{SITE}{POLICY}" in report.pdf_added


def test_a_stored_pdf_needs_a_section_that_still_reads_pdfs() -> None:
    doc = _allowlist_doc()
    sections = doc["sections"]
    assert isinstance(sections, dict)
    sections["docs"]["read_pdfs"] = False
    closed = Allowlist.from_json(doc)
    hub = StoredPage(
        f"{SITE}/policies/", "Policies", "docs", "approved", "", "", "", ("Docs.",),
        pdf_links=((f"{SITE}{POLICY}", "Policy"),),
    )  # fmt: skip
    pdf = StoredPage(f"{SITE}{POLICY}", "Policy", "docs", "auto", "", "", "", (P1,), kind="pdf")
    assert (
        KnowledgeBase([hub, pdf], Allowlist.from_json(_allowlist_doc())).page(pdf.url) is not None
    )
    assert KnowledgeBase([hub, pdf], closed).page(pdf.url) is None


# ─── The real downloader, over loopback ───────────────────────────────────────


@pytest.fixture
def served(tmp_path: Path) -> Iterator[str]:
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

    handler = functools.partial(Quiet, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


async def test_the_downloader_streams_to_disk_asks_conditionally_and_stops_at_the_ceiling(
    tmp_path: Path, served: str
) -> None:
    data = make_pdf([P1])
    (tmp_path / "doc.pdf").write_bytes(data)
    dest = tmp_path / "down" / "file.pdf"
    dest.parent.mkdir()
    got = await asyncio.to_thread(_download_file, f"{served}/doc.pdf", {}, 1 << 20, dest)
    assert got.status == 200 and dest.read_bytes() == data
    assert got.size == len(data) and got.sha256 == hashlib.sha256(data).hexdigest()
    assert got.headers["content-length"] == str(len(data))
    validators = knowledge.Validators.of(got.headers)

    dest.unlink()
    again = await asyncio.to_thread(
        _download_file, f"{served}/doc.pdf", validators.conditional(), 1 << 20, dest
    )
    assert again.status == 304 and not dest.exists()

    with pytest.raises(TooLarge) as e:
        await asyncio.to_thread(_download_file, f"{served}/doc.pdf", {}, 100, dest)
    assert e.value.size == len(data)

    missing = await asyncio.to_thread(_download_file, f"{served}/gone.pdf", {}, 1 << 20, dest)
    assert missing.status == 404


# ─── Files built to keep a reader busy ───────────────────────────────────────

BUSY = b"(abc def) Tj T* "
"""Neutral text-showing operators, repeated to make a page heavy."""


def stream_bomb(stream_bytes: int) -> bytes:
    """A one-page PDF of a few kilobytes whose content stream inflates to
    ``stream_bytes``."""
    return make_pdf([BUSY * (stream_bytes // len(BUSY))])


def _on_disk(tmp_path: Path, data: bytes, name: str = "doc.pdf") -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


@pytest.mark.parametrize("inflated", [5_000_000, 70_000_000], ids=["5MB", "70MB"])
async def test_a_small_file_with_a_huge_stream_is_refused_fast_and_in_little_memory(
    tmp_path: Path, inflated: int
) -> None:
    """The page's content is refused at the stream limit, before its text is
    read: in well under a second, inside a 128 MB memory cap."""
    data = stream_bomb(inflated)
    assert len(data) < 200_000
    started = time.monotonic()
    with pytest.raises(PdfUnreadable) as e:
        await read_pdf_isolated(_on_disk(tmp_path, data), timeout_s=10, memory_mb=128)
    assert "too large or too slow" in e.value.reason
    assert e.value.lasting
    assert time.monotonic() - started < 5


def test_one_heavy_or_slow_page_is_skipped_and_the_rest_are_read() -> None:
    data = make_pdf(
        [
            P1 + "\n" + P2,
            BUSY * (5_000_000 // len(BUSY)),
            BUSY * (2_000_000 // len(BUSY)),
            P3 + "\n" + P1,
        ]
    )
    started = time.monotonic()
    part = read_pdf(data, page_timeout_s=0.3)
    assert part.skipped == {2: "too large to read", 3: "took over 0.3 s to read"}
    assert part.done and part.pages[1] == part.pages[2] == ""
    assert "incubator grant" in part.pages[0] and "review meeting" in part.pages[3]
    assert time.monotonic() - started < 5


async def test_a_reader_stopped_on_a_page_keeps_the_pages_before_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no page timer, the second page outlasts the whole read: the reader
    is killed, the first page stands, the second is skipped, and the next read
    starts at the third."""
    monkeypatch.setattr(knowledge, "_WORKER_GRACE_S", 0.0)
    path = _on_disk(
        tmp_path,
        make_pdf([P1 + "\n" + P2, BUSY * (3_000_000 // len(BUSY)), P3 + "\n" + P1]),
    )
    started = time.monotonic()
    part = await read_pdf_isolated(path, page_timeout_s=0, timeout_s=1.5)
    assert time.monotonic() - started < 4
    assert part.stopped == "stopped" and part.next_page == 3 and not part.done
    assert "incubator grant" in part.pages[0]
    assert 2 in part.skipped
    rest = await read_pdf_isolated(path, start=3)
    assert rest.done and "review meeting" in rest.pages[0]


async def test_the_reader_process_is_killed_at_its_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(knowledge, "_WORKER_GRACE_S", 0.0)
    started = time.monotonic()
    with pytest.raises(PdfUnreadable) as e:
        await read_pdf_isolated(
            _on_disk(tmp_path, make_pdf([P1, P2, P3])), page_timeout_s=0, timeout_s=0.05
        )
    assert "stopped while opening" in e.value.reason
    assert not e.value.lasting  # tried again after a backoff
    assert time.monotonic() - started < 2


@pytest.mark.skipif(sys.platform != "linux", reason="the address-space cap is Linux only")
async def test_the_reader_process_runs_inside_its_memory_cap(tmp_path: Path) -> None:
    with pytest.raises(PdfUnreadable) as e:
        await read_pdf_isolated(_on_disk(tmp_path, stream_bomb(1_000_000)), memory_mb=5)
    assert "memory" in e.value.reason or "too large or too slow" in e.value.reason
    pdf = await read_pdf_isolated(_on_disk(tmp_path, make_pdf([P1, P2, P3]), "ok.pdf"))
    assert "incubator grant" in pdf.pages[1]  # the same reader, a normal file


async def test_a_400_page_document_is_read_a_slice_at_a_time(tmp_path: Path) -> None:
    path = _on_disk(tmp_path, make_pdf([f"Page {n}. " + P1 + "\n" + P3 for n in range(1, 401)]))
    started = time.monotonic()
    part = await read_pdf_isolated(path, max_pages=150)
    assert (part.page_count, part.next_page) == (400, 151)
    assert part.pages[0].startswith("Page 1.")
    assert time.monotonic() - started < 15


# ─── Failures, retries, limits and long documents ─────────────────────────────


async def test_dead_links_wait_for_a_retry_instead_of_taking_new_pdfs_places(
    allowlist: Allowlist, site: FakeSite, files: FakeFiles
) -> None:
    """Three dead links ahead of three good PDFs, three new PDFs a run: the
    first run spends its places on the dead links; after that the good ones
    are read first, and the dead links wait for their retry time."""
    dead = [(f"{UP}/gone-{i}.pdf", f"Gone {i}") for i in range(3)]
    good = [(f"{UP}/good-{i}.pdf", f"Good {i}") for i in range(3)]
    for path, _ in good:
        files.put(path, make_pdf([P1 + "\n" + P3]))
    site.pages["/policies/"] = _hub(*dead, *good)
    site.pages["/reports/"] = _hub()

    async def run(snap: Snapshot, days: float) -> tuple[Snapshot, knowledge.RefreshReport]:
        return await refresh(
            snap,
            allowlist,
            site.fetch,
            fetch_file=files.fetch,
            policy=RefreshPolicy(pause_s=0, max_new_pdfs=3),
            now=NOW + timedelta(days=days),
        )

    snap, report = await run(Snapshot(), 0)
    assert report.pdf_deferred == 3
    assert set(snap.unreadable) == {f"{SITE}{p}" for p, _ in dead}
    assert all(not u.lasting and u.attempts == 1 for u in snap.unreadable.values())

    files.requests.clear()
    snap, report = await run(snap, 1)  # due again, but at the back: the good PDFs first
    assert sorted(report.pdf_added) == sorted(f"{SITE}{p}" for p, _ in good)
    assert report.pdf_deferred == 3
    assert not any(p.startswith(f"{UP}/gone") for p in files.paths())
    assert set(snap.unreadable) == {f"{SITE}{p}" for p, _ in dead}  # still recorded

    snap, report = await run(snap, 2)  # nothing new ahead of them: tried again
    assert all(u.attempts == 2 for u in snap.unreadable.values())
    assert report.pdf_deferred == 0

    files.requests.clear()
    snap, report = await run(snap, 3)  # a second failure waits 40 hours
    assert report.pdf_waiting == 3
    assert not any(p.startswith(f"{UP}/gone") for p in files.paths())
    assert all(f"{SITE}{p}" in snap.pages for p, _ in good)
    assert set(snap.unreadable) == {f"{SITE}{p}" for p, _ in dead}


async def test_a_long_document_is_read_over_several_runs_first_pages_first(
    allowlist: Allowlist, site: FakeSite, files: FakeFiles
) -> None:
    places = ["Ambala", "Bidar", "Chamba", "Dhule", "Etawah"]
    pages = [f"Section {n} covers lantern workshops in {p}. " + P1 for n, p in enumerate(places, 1)]
    files.put(POLICY, make_pdf(pages))
    url = f"{SITE}{POLICY}"

    async def run(snap: Snapshot) -> tuple[Snapshot, knowledge.RefreshReport]:
        return await _refresh(snap, allowlist, site, files, pdf_pages_per_run=2)

    snap, report = await run(Snapshot())
    held = snap.pages[url]
    assert (held.page_count, held.next_page, len(held.blocks)) == (5, 3, 2)
    assert url in report.pdf_in_progress
    kb = KnowledgeBase(snap.pages.values(), allowlist)
    assert kb.search("Ambala")[0].page == 1  # the beginning answers already
    assert kb.search("Etawah") == []

    files.requests.clear()
    snap, report = await run(snap)
    assert dict(files.requests)[POLICY] == {}  # downloaded again, to carry on
    assert snap.pages[url].next_page == 5 and len(snap.pages[url].blocks) == 4

    # The file changed on the server: read again from the first page.
    files.put(
        POLICY, make_pdf(["A new first page about harbour grants. " + P1, *pages[1:]]), version=2
    )
    snap, report = await run(snap)
    assert snap.pages[url].next_page == 3 and "harbour grants" in snap.pages[url].blocks[0]

    snap, _ = await run(snap)
    snap, report = await run(snap)
    assert snap.pages[url].next_page == 6 and not snap.pages[url].in_progress
    assert url not in report.pdf_in_progress and len(snap.pages[url].blocks) == 5


async def test_a_pdf_stopped_at_a_limit_is_read_on_when_the_limits_change(
    allowlist: Allowlist, site: FakeSite, files: FakeFiles
) -> None:
    files.put(POLICY, make_pdf([P1 + "\n" + P2, P2 + "\n" + P3, P3 + "\n" + P1]))
    url = f"{SITE}{POLICY}"
    small = len(P1) + len(P2) + 40
    snap, report = await _refresh(Snapshot(), allowlist, site, files, max_pdf_chars=small)
    assert snap.pages[url].limited == "characters" and report.pdf_truncated == [url]

    files.requests.clear()
    snap, _ = await _refresh(snap, allowlist, site, files, max_pdf_chars=small)
    assert "If-None-Match" in dict(files.requests)[POLICY]  # same limits: asked, kept
    assert snap.pages[url].limited == "characters"

    files.requests.clear()
    snap, _ = await _refresh(snap, allowlist, site, files)
    assert dict(files.requests)[POLICY] == {}  # other limits: downloaded and read on
    stored = snap.pages[url]
    assert not stored.limited and not stored.in_progress and len(stored.blocks) == 3
    assert stored.read_with == reader_signature(RefreshPolicy(pause_s=0))


async def test_an_unreadable_verdict_is_reached_again_under_other_limits(
    allowlist: Allowlist, site: FakeSite, files: FakeFiles
) -> None:
    files.put(GUIDE, make_pdf([P3 + "\n" + P1] * 3))
    snap, report = await _refresh(Snapshot(), allowlist, site, files, max_pdf_bytes=1500)
    assert "larger than the" in report.pdf_unreadable[f"{SITE}{GUIDE}"]
    snap, report = await _refresh(snap, allowlist, site, files)  # the ceiling was raised
    assert f"{SITE}{GUIDE}" in report.pdf_added
    assert f"{SITE}{GUIDE}" not in snap.unreadable


async def test_a_read_that_may_go_better_next_time_is_retried_after_a_backoff(
    allowlist: Allowlist, site: FakeSite, files: FakeFiles, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = knowledge.read_pdf_isolated

    async def stopped(path: Path, **limits: object) -> knowledge.PdfPart:
        raise PdfUnreadable("the reader was stopped while opening it", lasting=False)

    monkeypatch.setattr(knowledge, "read_pdf_isolated", stopped)
    snap, _ = await _refresh(Snapshot(), allowlist, site, files)
    bad = snap.unreadable[f"{SITE}{POLICY}"]
    assert not bad.lasting and bad.retry_after == (NOW + timedelta(hours=20)).isoformat()

    monkeypatch.setattr(knowledge, "read_pdf_isolated", real)
    files.requests.clear()
    snap2, report = await _refresh(snap, allowlist, site, files)  # same day: waits
    assert POLICY not in files.paths() and report.pdf_waiting == 2
    later, report = await refresh(
        snap2,
        allowlist,
        site.fetch,
        fetch_file=files.fetch,
        policy=RefreshPolicy(pause_s=0),
        now=NOW + timedelta(days=1),
    )
    assert f"{SITE}{POLICY}" in later.pages and f"{SITE}{POLICY}" not in later.unreadable


async def test_all_pdf_text_together_stays_under_its_cap(
    allowlist: Allowlist, site: FakeSite, files: FakeFiles
) -> None:
    policy_chars = sum(map(len, read_pdf(make_pdf([P1, P2, P3])).pages))
    cap = policy_chars + 30
    snap, report = await _refresh(Snapshot(), allowlist, site, files, max_pdf_chars_total=cap)
    assert f"{SITE}{POLICY}" in snap.pages  # first in link order
    assert report.pdf_capped == [f"{SITE}{GUIDE}"]  # reported, read only as far as fits
    held = sum(sum(map(len, p.blocks)) for p in snap.pages.values() if p.kind == "pdf")
    assert held <= cap


_VOCAB = [f"term{i}" for i in range(20_000)]
_CUMULATIVE = list(itertools.accumulate(1 / (i + 1) for i in range(len(_VOCAB))))
_COMMON = ["state", "policy", "government", "digital", "startup", "scheme", "incentive", "district"]


def _prose(rng: random.Random, chars: int) -> str:
    """Synthetic text with a word-frequency curve like a policy's: a long tail of
    rare words, and a few words in a good share of every page."""
    words = rng.choices(_VOCAB, cum_weights=_CUMULATIVE, k=chars // 7)
    words += rng.choices(_COMMON, k=chars // 70)
    rng.shuffle(words)
    return "\n".join(" ".join(words[i : i + 14]) + "." for i in range(0, len(words), 14))


def test_search_at_the_pdf_text_cap_stays_inside_the_tool_budget() -> None:
    from voqalize.sdk.gemini import TOOL_BUDGET_MS

    rng = random.Random(41)
    cap = RefreshPolicy().max_pdf_chars_total
    al = Allowlist.from_json(_allowlist_doc())
    per_pdf = 250_000
    urls = [f"{SITE}{UP}/bench-{i}.pdf" for i in range(cap // per_pdf)]
    hub = StoredPage(
        f"{SITE}/policies/", "Policies", "docs", "approved", "", "", "", ("Docs.",),
        pdf_links=tuple((u, f"Bench {i}") for i, u in enumerate(urls)),
    )  # fmt: skip
    pdfs = [
        StoredPage(
            u,
            f"Bench {i}",
            "docs",
            "auto",
            "",
            "",
            "",
            tuple(_prose(rng, 2500) for _ in range(per_pdf // 2500)),
            kind="pdf",
        )
        for i, u in enumerate(urls)
    ]
    kb = KnowledgeBase([hub, *pdfs], al)
    assert sum(len(p.text) for p in kb.pages) >= cap * 0.9
    worst = 0.0
    for query in (
        "state digital policy incentive for a startup in my district",
        "government scheme",
        "term1 term2 term3 policy",
        "what is the policy",
        "term5000 state",
    ):
        best = min(_timed(kb, query) for _ in range(3))
        worst = max(worst, best)
    assert worst < TOOL_BUDGET_MS / 2, f"{worst:.1f} ms"  # half: the rest of the tool's work


def _timed(kb: KnowledgeBase, query: str) -> float:
    started = time.perf_counter()
    assert kb.search(query, 3)
    return (time.perf_counter() - started) * 1000


# ─── URLs ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (f"{UP}/../../../plugins/x.pdf", f"{SITE}/wp-content/plugins/x.pdf"),
        (f"{UP}/%2e%2e/%2E%2E/../plugins/x.pdf", f"{SITE}/wp-content/plugins/x.pdf"),
        ("/a/./b/../c/", f"{SITE}/a/c/"),
        ("/../../outside/", f"{SITE}/outside/"),
        (f"{UP}/a%2fb.pdf", None),
        (f"{UP}/a%5Cb.pdf", None),
        (f"{UP}/%2e%2e%2Fplugins/x.pdf", None),
        (f"{UP}/A Plan.pdf", f"{SITE}{UP}/A%20Plan.pdf"),
        (f"{UP}/A%20Plan.pdf", f"{SITE}{UP}/A%20Plan.pdf"),
        ("/x/%e0%b2%95/", f"{SITE}/x/%E0%B2%95/"),
        ("/x/%ff/", f"{SITE}/x/%FF/"),  # kept as it came, not turned into U+FFFD
        ("/100%/", f"{SITE}/100%25/"),
    ],
)
def test_normalize_resolves_dot_segments_and_keeps_escapes(
    given: str, expected: str | None
) -> None:
    assert normalize(given) == expected


def test_no_spelling_of_a_path_escapes_the_uploads_rule() -> None:
    al = Allowlist.from_json(_allowlist_doc())
    for sneaky in (
        f"{UP}/../../../plugins/x.pdf",
        f"{UP}/%2e%2e/%2e%2e/%2e%2e/plugins/x.pdf",
        "/wp-content/uploads/./../themes/x.pdf",
    ):
        url = normalize(sneaky)
        assert url is not None and al.is_excluded(url), sneaky
    assert normalize(f"{UP}/%2e%2e%2fplugins/x.pdf") is None


def test_an_older_snapshot_is_read_under_the_current_spelling(tmp_path: Path) -> None:
    old = {
        "version": 1,
        "built_at": "2026-10-01T00:00:00+00:00",
        "known": {f"{SITE}/x/%e0%b2%95/": "2026-09-01"},
        "pages": [
            {
                "url": f"{SITE}/x/%e0%b2%95/",
                "title": "Lower-case escapes",
                "section": "core",
                "origin": "approved",
                "lastmod": "2026-09-01",
                "fetched_at": "",
                "digest": "0",
                "blocks": ["Text."],
            }
        ],
        "pending_review": [],
    }
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(old), encoding="utf-8")
    snap = Snapshot.load(path)
    assert snap is not None
    assert list(snap.pages) == [f"{SITE}/x/%E0%B2%95/"]
    assert snap.pages[f"{SITE}/x/%E0%B2%95/"].url == f"{SITE}/x/%E0%B2%95/"
    assert list(snap.known) == [f"{SITE}/x/%E0%B2%95/"]
