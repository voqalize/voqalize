"""Saatvik's product catalogue against Saatvik's crawl — no network.

The playbooks in ``knowledge/products.json`` turn into screen cues: a story
heading that the page no longer has would ring nothing, or the wrong words, in
front of the visitor. A recrawl that renames a heading fails here, not on a
call.

Run: ``cd demos && uv run pytest tests/test_saatvik_catalogue.py``
"""

from __future__ import annotations

import typing

from voqalize_demos.discovery import discover

discover()

from voqalize_demos._loaded.saatvik import brain as saatvik  # noqa: E402
from voqalize_demos._loaded.saatvik.knowledge import KNOWLEDGE, REDIRECTS  # noqa: E402

SLUGS = set(typing.get_args(saatvik.ProductSlug))
CATEGORIES = set(typing.get_args(saatvik.Category))


def test_every_page_has_its_playbook() -> None:
    assert len(KNOWLEDGE.products) >= 30
    for p in KNOWLEDGE.products:
        assert KNOWLEDGE.page(p.path) is not None, p.path
        assert p.path not in REDIRECTS, p.path


def test_every_story_heading_is_on_its_page() -> None:
    missing = [
        (p.id, s.heading)
        for p in KNOWLEDGE.products
        for s in p.story
        if s.heading not in KNOWLEDGE.page(p.path).headings  # type: ignore[union-attr]
    ]
    assert missing == []


def test_every_tab_and_faq_is_on_its_page() -> None:
    for p in KNOWLEDGE.products:
        page = KNOWLEDGE.page(p.path)
        assert page is not None
        assert set(p.tabs) <= set(page.tabs), p.id
        assert set(p.faqs) <= {f.q for f in page.faqs}, p.id


def test_every_variant_shows_words_its_page_has() -> None:
    for p in KNOWLEDGE.products:
        page = KNOWLEDGE.page(p.path)
        assert page is not None
        text = " ".join([page.text, *page.headings])
        for v in p.variants:
            assert not v.show or v.show in text, (p.id, v.show)


def test_every_datasheet_and_next_line_exists() -> None:
    ids = {p.id for p in KNOWLEDGE.products}
    for p in KNOWLEDGE.products:
        for d in p.datasheets:
            assert d.document_id in KNOWLEDGE.documents, (p.id, d.document_id)
        assert set(p.next) <= ids, (p.id, set(p.next) - ids)


def test_every_call_to_action_is_one_the_tools_take() -> None:
    for p in KNOWLEDGE.products:
        assert p.cta, p.id
        for cta in (p.cta, *p.cta_more):
            if "book_product(" in cta:
                slug = cta.split("product=")[1].split(")")[0].split(",")[0].strip()
                assert slug in SLUGS, (p.id, slug)
            if "category=" in cta:
                category = cta.split("category=")[1].split(")")[0].split(", ")[0].strip()
                assert category in CATEGORIES, (p.id, category)


def test_every_state_has_a_typical_rate() -> None:
    states = set(typing.get_args(saatvik.CalculatorState))
    assert states <= set(KNOWLEDGE.tariffs)
    for t in KNOWLEDGE.tariffs.values():
        assert 2 < t.rate < 15 and t.low <= t.rate <= t.high, t
