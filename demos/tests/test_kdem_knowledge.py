"""KDEM's knowledge base: what Aria may answer from, and how it stays current.

No network: every page and sitemap here is synthetic, served by a fake fetcher.

What is worth pinning:

**Only what a visitor reads.** Theme chrome, popups, per-breakpoint copies, and
any element hidden or moved off-screen by its inline style are dropped with
their whole subtree.

**One URL per topic.** Spelling variants and the duplicate pages fold into the
canonical URL on the allowlist; test and placeholder pages are never pages.

**A refresh reads only what changed.** A moved ``lastmod`` is re-read, a new page
in an auto-add section is added, a new page anywhere else is held for review, a
page gone from the sitemap is dropped, and a failed sitemap read changes nothing.

Run: ``cd demos && uv run pytest tests/test_kdem_knowledge.py``
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from voqalize_demos.discovery import _demos_root, _load_backend_package, discover

discover()
if "voqalize_demos._loaded.kdem" not in sys.modules:  # no routes.py yet: load it directly
    _load_backend_package("kdem", _demos_root() / "kdem" / "backend")

from voqalize_demos._loaded.kdem.knowledge import (  # noqa: E402
    ALLOWLIST,
    Allowlist,
    FetchResult,
    KnowledgeBase,
    KnowledgeService,
    RefreshPolicy,
    SitemapError,
    Snapshot,
    StoredPage,
    extract,
    normalize,
    refresh,
    tokens,
)

SITE = "https://karnatakadigital.in"
NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
FILLER = "neutral filler text that no visitor can see"


# ─── Visible text ─────────────────────────────────────────────────────────────


def _page(body: str, *, title: str = "Sample | KDEM") -> str:
    return f"""<!doctype html><html lang="en-US"><head><title>{title}</title>
<style>.x{{color:red}}</style><script>var hidden = "script text";</script></head>
<body class="page-template-default">
<header class="site-header"><nav><a href="/about-us/">About</a> Menu text</nav></header>
<div data-elementor-type="popup" class="elementor-location-popup"><p>Popup text</p></div>
{body}
<footer class="elementor-location-footer"><p>Footer text</p></footer>
</body></html>"""


def test_extract_keeps_the_body_and_drops_the_chrome() -> None:
    html = _page(
        """<main id="main" class="site-main"><article>
        <h1>Talent Accelerator</h1>
        <p>The programme trains <a href="/k-vlsi/">VLSI</a> designers.<br>Second line.</p>
        <form><label>Your name</label><input name="n"></form>
        <noscript>Enable scripts</noscript>
        <div class="elementor-hidden-desktop"><p>Mobile copy</p></div>
        <p class="screen-reader-text">Reader-only text</p>
        <aside>Sidebar text</aside>
        <div class="mec-event-export-module">+ Add to Google Calendar</div>
        <p>Share this event</p>
        <span class="elementor-counter-number" data-to-value="19000">0</span> Startups
        </article></main>"""
    )
    ex = extract(html, url=f"{SITE}/talent-accelerator/")
    assert ex.title == "Talent Accelerator"
    assert "The programme trains VLSI designers." in ex.text
    assert "Second line." in ex.text
    assert "19000" in ex.text
    for gone in (
        "Menu text",
        "Popup text",
        "Footer text",
        "script text",
        "color:red",
        "Your name",
        "Enable scripts",
        "Mobile copy",
        "Reader-only text",
        "Sidebar text",
        "Add to Google Calendar",
        "Share this event",
    ):
        assert gone not in ex.text, gone
    assert f"{SITE}/k-vlsi/" in ex.links
    assert f"{SITE}/about-us/" not in ex.links  # only in the nav


@pytest.mark.parametrize(
    "attrs",
    [
        'style="position:absolute;left:-9999px"',
        'style="position: fixed; top: -4500px; left: -4500px;"',
        'style="position:absolute; right:-80em"',
        'style="text-indent:-10000px"',
        'style="display:none"',
        'style="DISPLAY: none !important"',
        'style="visibility:hidden"',
        'style="opacity:0"',
        'style="font-size:0px"',
        'style="clip:rect(0,0,0,0);position:absolute"',
        'style="height:0;overflow:hidden"',
        'style="width:1px;height:1px;overflow:hidden"',
        "hidden",
        'aria-hidden="true"',
    ],
)
def test_hidden_and_offscreen_subtrees_are_dropped(attrs: str) -> None:
    html = _page(
        f"""<main id="main"><article>
        <p>Visible paragraph about the seed fund.</p>
        <div {attrs}><p>{FILLER}</p><div><a href="/elsewhere/">{FILLER}</a></div></div>
        <p>Another visible paragraph.</p>
        </article></main>"""
    )
    ex = extract(html)
    assert FILLER not in ex.text
    assert f"{SITE}/elsewhere/" not in ex.links
    assert "Visible paragraph about the seed fund." in ex.text
    assert "Another visible paragraph." in ex.text


def test_a_small_negative_offset_is_still_visible() -> None:
    html = _page(
        '<main id="main"><div style="position:relative;left:-20px">Nudged text</div></main>'
    )
    assert "Nudged text" in extract(html).text


def test_canvas_pages_root_at_the_elementor_document() -> None:
    html = f"""<html><head><title>Beyond Bengaluru - KDEM</title></head><body
    class="page-template-elementor_canvas">
    <div style="position: fixed; top: -3000px; left: -3000px;"><p>{FILLER}</p></div>
    <div data-elementor-type="wp-page" class="elementor elementor-12">
      <section class="elementor-top-section"><h2>Clusters</h2><p>Mysuru and Mangaluru.</p></section>
      <section class="elementor-top-section"><p>Cluster seed fund details.</p></section>
    </div>
    <p>Outside the document</p>
    </body></html>"""
    ex = extract(html)
    assert ex.blocks == ("Clusters\nMysuru and Mangaluru.", "Cluster seed fund details.")
    assert ex.title == "Beyond Bengaluru"  # no h1: the <title>, minus the site name


def test_void_and_unclosed_tags_keep_the_tree_balanced() -> None:
    html = _page(
        """<main id="main"><div><p>One<br>two<img src="a.png"><hr>
        <p>Three<input type="text"><wbr>four
        <ul><li>Alpha<li>Beta</ul>
        <div style="display:none"><meta charset="x"><br><p>{x}</div>
        <p>Five</p></div></main>""".replace("{x}", FILLER)
    )
    ex = extract(html)
    for kept in ("One", "two", "Three", "four", "Alpha", "Beta", "Five"):
        assert kept in ex.text, kept
    assert FILLER not in ex.text


def test_a_document_pasted_into_a_widget_is_read_as_part_of_the_page() -> None:
    html = _page(
        """<div id="content"><div data-elementor-type="wp-page">
        <section><div class="elementor-widget-html"><!DOCTYPE html>
        <html lang="en"><head><meta charset="UTF-8"><title>Widget title</title>
        <style>body{margin:0}</style></head>
        <body><h2>Cohort startups</h2><p>Twelve startups in fintech.</p></body></html>
        </div></section>
        <section><p>After the widget.</p></section>
        </div></div>"""
    )
    ex = extract(html)
    assert "Cohort startups" in ex.text
    assert "Twelve startups in fintech." in ex.text
    assert "After the widget." in ex.text
    assert "Widget title" not in ex.text
    assert "Footer text" not in ex.text


# ─── URLs and the allowlist ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("https://karnatakadigital.in/resource/", f"{SITE}/resource/"),
        ("http://www.karnatakadigital.in/resource", f"{SITE}/resource/"),
        ("https://KarnatakaDigital.in/resource/?utm=x#top", f"{SITE}/resource/"),
        ("/resource", f"{SITE}/resource/"),
        ("https://karnatakadigital.in", f"{SITE}/"),
        ("/wp-content/uploads/2026/01/policy.pdf", f"{SITE}/wp-content/uploads/2026/01/policy.pdf"),
        ("https://example.com/resource/", None),
        ("mailto:someone@example.com", None),
    ],
)
def test_normalize(given: str, expected: str | None) -> None:
    assert normalize(given) == expected


@pytest.mark.parametrize(
    ("given", "canonical"),
    [
        ("https://karnatakadigital.in/resources/", "/resource/"),
        ("https://karnatakadigital.in/reports", "/resource/"),
        ("https://www.karnatakadigital.in/news-updates1/", "/news-updates/"),
        ("https://karnatakadigital.in/news-updates-2/", "/news-updates/"),
        ("https://karnatakadigital.in/newupdates/", "/news-updates/"),
        ("https://karnatakadigital.in/news/", "/news-updates/"),
        ("https://karnatakadigital.in/innovation-and-startups/", "/innovation-and-startup/"),
        ("https://karnatakadigital.in/innovation-and-startups-old/", "/innovation-and-startup/"),
        ("https://karnatakadigital.in/ourpolicies/?x=1", "/policies/"),
        ("https://karnatakadigital.in/beyond-bengaluru-1/", "/beyond-bengaluru/"),
        ("https://karnatakadigital.in/cohort-1/", "/cohort-1/"),
    ],
)
def test_aliases_fold_into_one_canonical_url(given: str, canonical: str) -> None:
    page = ALLOWLIST.approved(given)
    assert page is not None
    assert page.url == SITE + canonical


@pytest.mark.parametrize(
    "path",
    [
        "/sample-page/",
        "/demo-home/",
        "/demo-page/",
        "/home-1/",
        "/home-2/",
        "/coming-soon/",
        "/design-old/",
        "/apply-now/",
        "/corporate-registration/",
        "/category/esdm/",
        "/2025/03/01/",
    ],
)
def test_test_and_placeholder_pages_are_excluded(path: str) -> None:
    assert ALLOWLIST.approved(SITE + path) is None
    assert ALLOWLIST.is_excluded(SITE + path)


def test_the_allowlist_holds_together() -> None:
    urls = [p.url for p in ALLOWLIST.pages]
    assert len(urls) == len(set(urls))
    assert all(normalize(u) == u for u in urls)
    assert ALLOWLIST.approved(ALLOWLIST.contact_url) is not None
    for p in ALLOWLIST.pages:
        assert ALLOWLIST.sections[p.section].approved
        assert not ALLOWLIST.is_excluded(p.url)
    assert ALLOWLIST.section_of_type("news") == "news"
    assert ALLOWLIST.section_of_type("mec-events") == "events"
    assert ALLOWLIST.section_of_type("post") == "blog-posts"


def test_a_malformed_allowlist_refuses_to_load() -> None:
    doc = _allowlist_doc()
    pages = doc["pages"]
    assert isinstance(pages, list)
    pages.append({"url": f"{SITE}/sample-page/", "title": "x", "section": "core", "aliases": []})
    with pytest.raises(RuntimeError, match=r"kdem: .*excluded"):
        Allowlist.from_json(doc)


# ─── Refresh ──────────────────────────────────────────────────────────────────


def _allowlist_doc() -> dict[str, object]:
    return {
        "site": SITE,
        "sitemap": f"{SITE}/wp-sitemap.xml",
        "contact_url": f"{SITE}/contact-us/",
        "sections": {
            "core": {"approved": True, "auto_add": False, "post_types": ["page"]},
            "programmes": {"approved": True, "auto_add": True, "post_types": ["page"]},
            "news": {"approved": True, "auto_add": True, "post_types": ["news"]},
            "blog": {"approved": False, "auto_add": False, "post_types": ["post"]},
        },
        "pages": [
            {"url": f"{SITE}/contact-us/", "title": "Contact Us", "section": "core"},
            {"url": f"{SITE}/about-us/", "title": "About KDEM", "section": "core"},
            {
                "url": f"{SITE}/programmes/",
                "title": "Programmes",
                "section": "programmes",
                "aliases": [f"{SITE}/our-programmes/"],
                "hub_for": "programmes",
            },
        ],
        "excluded_patterns": [{"pattern": "^/sample-page/$", "why": "test page"}],
        "held_patterns": [{"pattern": "speaker", "why": "about individuals"}],
    }


def _sitemap(entries: dict[str, str]) -> str:
    urls = "".join(
        f"<url><loc>{SITE}{p}</loc><lastmod>{lm}</lastmod></url>" for p, lm in entries.items()
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    )


def _body(*paragraphs: str, links: tuple[str, ...] = ()) -> str:
    ps = "".join(f"<p>{p}</p>" for p in paragraphs)
    anchors = "".join(f'<p><a href="{href}">Link</a></p>' for href in links)
    return _page(f'<main id="main"><article>{ps}{anchors}</article></main>')


class FakeSite:
    """A WordPress site in a dict: the sitemap by post type, pages by path."""

    def __init__(self) -> None:
        self.sitemaps: dict[str, dict[str, str]] = {}
        self.pages: dict[str, str] = {}
        self.status: dict[str, int] = {}
        self.broken: set[str] = set()
        self.redirects: dict[str, str] = {}
        self.fetched: list[str] = []

    def index(self) -> str:
        subs = "".join(
            f"<sitemap><loc>{SITE}/wp-sitemap-posts-{t}-1.xml</loc></sitemap>"
            for t in self.sitemaps
        )
        tax = f"<sitemap><loc>{SITE}/wp-sitemap-taxonomies-category-1.xml</loc></sitemap>"
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{subs}{tax}'
            "</sitemapindex>"
        )

    async def fetch(self, url: str) -> FetchResult:
        path = url.removeprefix(SITE)
        self.fetched.append(path)
        if path in self.broken:
            raise OSError("timed out")
        if path == "/wp-sitemap.xml":
            return FetchResult(200, url, self.index())
        for t, entries in self.sitemaps.items():
            if path == f"/wp-sitemap-posts-{t}-1.xml":
                return FetchResult(200, url, _sitemap(entries))
        if path in self.redirects:
            return FetchResult(200, self.redirects[path], _body("Another site's page."))
        if path in self.status:
            return FetchResult(self.status[path], url, "")
        if path in self.pages:
            return FetchResult(200, url, self.pages[path])
        return FetchResult(404, url, "")

    def page_reads(self) -> list[str]:
        return [p for p in self.fetched if not p.startswith("/wp-sitemap")]


def _days_ago(n: int) -> str:
    return (NOW - timedelta(days=n)).isoformat(timespec="seconds")


@pytest.fixture
def allowlist() -> Allowlist:
    return Allowlist.from_json(_allowlist_doc())


@pytest.fixture
def site() -> FakeSite:
    s = FakeSite()
    s.sitemaps = {
        "page": {
            "/contact-us/": _days_ago(30),
            "/about-us/": _days_ago(30),
            "/programmes/": _days_ago(30),
            "/our-programmes/": _days_ago(30),  # an alias: never a page of its own
            "/new-programme/": _days_ago(2),  # linked from the hub: added
            "/orphan/": _days_ago(2),  # linked from nowhere: held
            "/event-speakers/": _days_ago(2),  # linked, but a held pattern
            "/sample-page/": _days_ago(2),  # excluded
        },
        "news": {"/news/fresh/": _days_ago(5), "/news/ancient/": _days_ago(400)},
        "post": {"/some-post/": _days_ago(10)},
    }
    s.pages = {
        "/contact-us/": _body("Write to the KDEM team."),
        "/about-us/": _body("KDEM is the knowledge bridge between government and industry."),
        "/programmes/": _body(
            "Our programmes.", links=("/new-programme/", "/event-speakers/", "/sample-page/")
        ),
        "/new-programme/": _page('<main id="main"><h1>New Programme</h1><p>Grants.</p></main>'),
        "/news/fresh/": _page('<main id="main"><h1>Fresh headline</h1><p>May 1</p></main>'),
    }
    return s


async def _refresh(snap: Snapshot, al: Allowlist, site: FakeSite, **policy: object):
    return await refresh(
        snap,
        al,
        site.fetch,
        policy=RefreshPolicy(pause_s=0, **policy),  # type: ignore[arg-type]
        now=NOW,
    )


async def test_first_build_adds_approved_and_auto_sections_and_holds_the_rest(
    allowlist: Allowlist, site: FakeSite
) -> None:
    snap, report = await _refresh(Snapshot(), allowlist, site)
    assert set(snap.pages) == {
        f"{SITE}/contact-us/",
        f"{SITE}/about-us/",
        f"{SITE}/programmes/",
        f"{SITE}/new-programme/",
        f"{SITE}/news/fresh/",
    }
    assert snap.pages[f"{SITE}/about-us/"].title == "About KDEM"  # the allowlist's title
    assert snap.pages[f"{SITE}/new-programme/"].title == "New Programme"
    assert snap.pages[f"{SITE}/new-programme/"].section == "programmes"
    assert snap.pages[f"{SITE}/news/fresh/"].section == "news"
    assert set(snap.pending_review) == {
        f"{SITE}/orphan/",
        f"{SITE}/event-speakers/",
        f"{SITE}/some-post/",
    }
    assert snap.pending_review[f"{SITE}/some-post/"].section == "blog"
    assert sorted(report.held) == sorted(snap.pending_review)
    # Old news is noted, not read; aliases and excluded pages are never read.
    assert f"{SITE}/news/ancient/" in snap.known
    for never in ("/news/ancient/", "/our-programmes/", "/sample-page/", "/orphan/"):
        assert never not in site.page_reads(), never
    assert snap.built_at == NOW.isoformat()


async def test_second_run_reads_only_what_changed(allowlist: Allowlist, site: FakeSite) -> None:
    snap, _ = await _refresh(Snapshot(), allowlist, site)
    site.fetched.clear()

    pages = site.sitemaps["page"]
    news = site.sitemaps["news"]
    pages["/about-us/"] = _days_ago(0)  # changed: re-read
    site.pages["/about-us/"] = _body("KDEM now also runs the cluster seed fund.")
    pages["/contact-us/"] = _days_ago(0)  # bumped, same text: unchanged
    del news["/news/fresh/"]  # gone from the sitemap: dropped
    news["/news/next/"] = _days_ago(400)  # new after the first build: added, however old
    site.pages["/news/next/"] = _page('<main id="main"><h1>Next headline</h1></main>')
    site.sitemaps["post"]["/another-post/"] = _days_ago(1)  # new, unapproved: held
    site.pages["/programmes/"] = _body("Our programmes.", links=("/orphan/",))
    pages["/programmes/"] = _days_ago(0)  # the hub now links to the orphan: added
    site.pages["/orphan/"] = _body("A programme page, now linked.")

    snap2, report = await _refresh(snap, allowlist, site)

    assert sorted(site.page_reads()) == sorted(
        ["/about-us/", "/contact-us/", "/programmes/", "/news/next/", "/orphan/"]
    )
    assert report.updated == [f"{SITE}/about-us/"]
    # Same text, new links: unchanged as text, but the links it now carries count.
    assert report.unchanged == [f"{SITE}/contact-us/", f"{SITE}/programmes/"]
    assert report.dropped == [f"{SITE}/news/fresh/"]
    assert sorted(report.added) == [f"{SITE}/news/next/", f"{SITE}/orphan/"]
    assert report.held == [f"{SITE}/another-post/"]
    assert "cluster seed fund" in "\n".join(snap2.pages[f"{SITE}/about-us/"].blocks)
    assert f"{SITE}/orphan/" not in snap2.pending_review
    assert snap2.pending_review[f"{SITE}/some-post/"].first_seen == NOW.isoformat()
    assert snap2.pages[f"{SITE}/contact-us/"].lastmod == _days_ago(0)


async def test_a_page_that_is_gone_or_now_excluded_is_dropped(
    allowlist: Allowlist, site: FakeSite
) -> None:
    snap, _ = await _refresh(Snapshot(), allowlist, site)
    site.sitemaps["page"]["/about-us/"] = _days_ago(0)
    site.status["/about-us/"] = 410
    del site.sitemaps["page"]["/new-programme/"]
    snap2, report = await _refresh(snap, allowlist, site)
    assert f"{SITE}/about-us/" not in snap2.pages
    assert f"{SITE}/new-programme/" not in snap2.pages
    assert sorted(report.dropped) == [f"{SITE}/about-us/", f"{SITE}/new-programme/"]


async def test_a_page_that_fails_to_load_keeps_its_last_copy(
    allowlist: Allowlist, site: FakeSite
) -> None:
    snap, _ = await _refresh(Snapshot(), allowlist, site)
    site.sitemaps["page"]["/about-us/"] = _days_ago(0)
    site.broken.add("/about-us/")
    snap2, report = await _refresh(snap, allowlist, site)
    assert snap2.pages[f"{SITE}/about-us/"] == snap.pages[f"{SITE}/about-us/"]
    assert report.failed == [f"{SITE}/about-us/"]


async def test_a_failed_sitemap_read_raises_and_changes_nothing(
    allowlist: Allowlist, site: FakeSite
) -> None:
    snap, _ = await _refresh(Snapshot(), allowlist, site)
    site.broken.add("/wp-sitemap-posts-news-1.xml")
    with pytest.raises(OSError):
        await _refresh(snap, allowlist, site)
    site.broken.clear()
    site.sitemaps = {}
    with pytest.raises(SitemapError):
        await _refresh(snap, allowlist, site)


async def test_new_pages_beyond_the_cap_wait_for_the_next_run(
    allowlist: Allowlist, site: FakeSite
) -> None:
    for i in range(4):
        site.sitemaps["news"][f"/news/item-{i}/"] = _days_ago(i + 1)
        site.pages[f"/news/item-{i}/"] = _page(f'<main id="main"><h1>Item {i}</h1></main>')
    snap, report = await _refresh(Snapshot(), allowlist, site, max_new=3)
    assert report.deferred == 3  # new-programme, fresh and four items: six candidates
    assert f"{SITE}/news/item-0/" in snap.pages  # newest first
    _, report2 = await _refresh(snap, allowlist, site, max_new=10)
    assert report2.deferred == 0
    assert len(report2.added) == 3


async def test_force_rereads_an_unchanged_page(allowlist: Allowlist, site: FakeSite) -> None:
    snap, _ = await _refresh(Snapshot(), allowlist, site)
    site.fetched.clear()
    await _refresh(snap, allowlist, site, force=frozenset({f"{SITE}/about-us"}))
    assert site.page_reads() == ["/about-us/"]


# ─── Search ───────────────────────────────────────────────────────────────────


def _stored(path: str, title: str, *blocks: str) -> StoredPage:
    return StoredPage(f"{SITE}{path}", title, "core", "approved", "", "", "", blocks)


SHARED = "Quick links\nConnect with us\nGet in Touch, fill in the form"


def _kb(al: Allowlist = ALLOWLIST) -> KnowledgeBase:
    return KnowledgeBase(
        [
            _stored(
                "/beyond-bengaluru-cluster-seed-fund/",
                "Beyond Bengaluru Cluster Seed Fund",
                "The cluster seed fund supports early-stage startups in Mysuru and Mangaluru.",
                SHARED,
            ),
            _stored(
                "/k-vlsi/",
                "K-VLSI Design Skill Program",
                "A six to nine month VLSI design skill programme with IIIT Bangalore.",
                SHARED,
            ),
            _stored("/contact-us/", "Contact Us", "Write to the KDEM team.", SHARED),
            _stored("/about-us/", "About KDEM", "ಕರ್ನಾಟಕ ಡಿಜಿಟಲ್ ಆರ್ಥಿಕ ಮಿಷನ್ ಬಗ್ಗೆ."),
        ],
        al,
    )


def test_search_finds_the_page_that_answers() -> None:
    hits = _kb().search("Is there a seed fund for startups in Mysuru?", k=2)
    assert hits
    assert hits[0].url == f"{SITE}/beyond-bengaluru-cluster-seed-fund/"
    assert hits[0].title == "Beyond Bengaluru Cluster Seed Fund"
    assert "seed fund" in hits[0].snippet
    assert _kb().search("VLSI training")[0].url == f"{SITE}/k-vlsi/"
    assert _kb().search("quantum teleportation") == []


def test_text_repeated_across_pages_is_not_page_text() -> None:
    kb = _kb()
    page = kb.page(f"{SITE}/k-vlsi")
    assert page is not None
    assert "Quick links" not in page.text
    assert kb.search("fill in the form") == []


def test_search_and_lookup_work_in_any_script_and_through_aliases() -> None:
    assert tokens("ಕರ್ನಾಟಕ ಡಿಜಿಟಲ್") == ["ಕರ್ನಾಟಕ", "ಡಿಜಿಟಲ್"]
    assert tokens("Startups and incubators") == ["startup", "incubator"]
    assert _kb().search("ಡಿಜಿಟಲ್")[0].url == f"{SITE}/about-us/"
    kb = KnowledgeBase([_stored("/resource/", "Resources", "Reports and newsletters.")], ALLOWLIST)
    found = kb.page("https://www.karnatakadigital.in/resources/?ref=menu")
    assert found is not None
    assert found.url == f"{SITE}/resource/"


def test_an_empty_knowledge_base_answers_nothing() -> None:
    kb = KnowledgeBase.empty(ALLOWLIST)
    assert len(kb) == 0
    assert kb.search("seed fund") == []
    assert kb.page(f"{SITE}/about-us/") is None


# ─── The snapshot and the keeper ──────────────────────────────────────────────


async def test_snapshot_round_trips_and_a_new_process_loads_it(
    tmp_path: Path, allowlist: Allowlist, site: FakeSite
) -> None:
    service = KnowledgeService(allowlist, cache_dir=tmp_path, fetch=site.fetch)
    report = await service.refresh_now(policy=RefreshPolicy(pause_s=0))
    assert len(report.added) == 2
    assert service.path.parent == tmp_path
    loaded = Snapshot.load(service.path)
    assert loaded is not None
    assert loaded.pages == service.snapshot.pages
    assert loaded.pending_review == service.snapshot.pending_review

    def failing() -> Callable[[str], object]:
        async def fetch(url: str) -> FetchResult:
            raise OSError("offline")

        return fetch

    fresh = KnowledgeService(allowlist, cache_dir=tmp_path, fetch=failing())  # type: ignore[arg-type]
    fresh.start()
    for _ in range(50):
        if len(fresh.kb):
            break
        await asyncio.sleep(0.02)
    assert len(fresh.kb) == len(loaded.pages)
    assert fresh.kb.search("knowledge bridge")[0].url == f"{SITE}/about-us/"
    await fresh.stop()


async def test_no_snapshot_and_no_network_is_an_empty_knowledge_base(
    tmp_path: Path, allowlist: Allowlist
) -> None:
    async def offline(url: str) -> FetchResult:
        raise OSError("offline")

    service = KnowledgeService(allowlist, cache_dir=tmp_path, fetch=offline)
    service.start()
    await asyncio.sleep(0.05)
    assert len(service.kb) == 0
    assert service.kb.search("seed fund") == []
    with pytest.raises(OSError):
        await service.refresh_now()
    assert not service.path.exists()
    await service.stop()


def test_prime_installs_a_snapshot_and_keeps_the_keeper_off(allowlist: Allowlist) -> None:
    service = KnowledgeService(allowlist)
    service.prime(
        Snapshot("2026-10-06T00:00:00+00:00", pages={p.url: p for p in [_stored("/x/", "X", "y")]})
    )
    service.start()  # outside a loop, and a no-op once primed
    assert len(service.kb) == 1


async def test_a_page_that_redirects_off_the_site_is_not_indexed(
    allowlist: Allowlist, site: FakeSite
) -> None:
    snap, _ = await _refresh(Snapshot(), allowlist, site)
    site.sitemaps["page"]["/about-us/"] = _days_ago(0)
    site.redirects["/about-us/"] = "https://example.org/landing/"
    site.sitemaps["news"]["/news/moved/"] = _days_ago(1)
    site.redirects["/news/moved/"] = "https://example.org/story/"
    snap2, report = await _refresh(snap, allowlist, site)
    assert f"{SITE}/about-us/" not in snap2.pages
    assert f"{SITE}/news/moved/" not in snap2.pages
    assert sorted(report.offsite) == [f"{SITE}/about-us/", f"{SITE}/news/moved/"]


async def test_held_patterns_apply_to_flat_pages_not_to_news(
    allowlist: Allowlist, site: FakeSite
) -> None:
    site.sitemaps["news"]["/news/keynote-speaker-named/"] = _days_ago(1)
    site.pages["/news/keynote-speaker-named/"] = _page('<main id="main"><h1>Named</h1></main>')
    snap, _ = await _refresh(Snapshot(), allowlist, site)
    assert f"{SITE}/news/keynote-speaker-named/" in snap.pages
    assert f"{SITE}/event-speakers/" in snap.pending_review
