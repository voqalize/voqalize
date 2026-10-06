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
import io
import json
import threading
from collections.abc import Iterator, Mapping
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
    read_pdf,
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


def make_pdf(pages: list[str], *, title: str = "") -> bytes:
    """A small, valid PDF: one Helvetica text block per page, a line per ``\\n``.
    An empty string is a page with a drawing and no text, as a scan would be."""
    objects: list[bytes] = [b"<< /Type /Catalog /Pages 2 0 R >>"]
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(len(pages)))
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for i, text in enumerate(pages):
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
        objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
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
    assert not pdf.truncated


def test_read_pdf_stops_at_its_limits_and_keeps_what_it_read() -> None:
    pdf = read_pdf(make_pdf([P1, P2, P3]), max_pages=2)
    assert len(pdf.pages) == 2 and pdf.truncated
    pdf = read_pdf(make_pdf([P1, P2, P3]), max_chars=len(P1) + 60)
    assert pdf.truncated and len("".join(pdf.pages)) <= len(P1) + 60


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
        <p><a href="{UP}/plan.pdf">The Sample Plan</a> and <a href="https://example.org/x.pdf">x</a></p>
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
        self.honours_conditionals = True
        self.requests: list[tuple[str, dict[str, str]]] = []

    def put(self, path: str, data: bytes, *, version: int = 1, etag: bool = True) -> None:
        headers = {"last-modified": f"Mon, 0{version} Jun 2026 10:00:00 GMT"}
        if etag:
            headers["etag"] = f'"v{version}"'
        self.files[path] = (data, headers)

    async def fetch(self, url: str, headers: Mapping[str, str], max_bytes: int) -> FetchResult:
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
        return FetchResult(200, url, "", h, data)

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
            ("https://example.org/wp-content/uploads/elsewhere.pdf", "Another site's PDF"),
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
    # Off the site, excluded, held, or linked from a section that does not read
    # PDFs: never asked for.
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


async def test_an_unchanged_pdf_is_asked_about_not_read_again(
    allowlist: Allowlist, site: FakeSite, files: FakeFiles, monkeypatch: pytest.MonkeyPatch
) -> None:
    snap, _ = await _refresh(Snapshot(), allowlist, site, files)
    files.requests.clear()

    def must_not_read(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("an unchanged PDF was read again")

    monkeypatch.setattr(knowledge, "read_pdf", must_not_read)
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

    async def flaky(url: str, headers: Mapping[str, str], max_bytes: int) -> FetchResult:
        if url.endswith(POLICY):
            raise OSError("timed out")
        return await files.fetch(url, headers, max_bytes)

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


async def test_the_downloader_asks_conditionally_and_stops_at_the_size_limit(
    tmp_path: Path, served: str
) -> None:
    data = make_pdf([P1])
    (tmp_path / "doc.pdf").write_bytes(data)
    got = await asyncio.to_thread(_download_file, f"{served}/doc.pdf", {}, 1 << 20)
    assert got.status == 200 and got.data == data
    assert got.headers["content-length"] == str(len(data))
    validators = knowledge.Validators.of(got.headers)

    again = await asyncio.to_thread(
        _download_file, f"{served}/doc.pdf", validators.conditional(), 1 << 20
    )
    assert again.status == 304 and again.data == b""

    with pytest.raises(TooLarge) as e:
        await asyncio.to_thread(_download_file, f"{served}/doc.pdf", {}, 100)
    assert e.value.size == len(data)

    missing = await asyncio.to_thread(_download_file, f"{served}/gone.pdf", {}, 1 << 20)
    assert missing.status == 404
