"""The page, as Tanvi knows it.

The site's section registry (`src/data/sections.json`) and its voice map
(`src/data/voice.json`: every control and link she can work) are the single source
of truth: the browser renders them and this module reads them, so the ids Tanvi can
open, switch and point at are exactly the ids the page has. The ids become
``Literal`` types so the model cannot invent one, and so ``voqalize types`` emits a
closed TypeScript union.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

HERE = Path(__file__).resolve().parent
# Deployed, the brain runs from voqalize/demos/marketing/backend, where `pnpm brain:sync`
# copies the two files next to it; here it reads them straight from the site.
DATA = HERE / "site_data" if (HERE / "site_data").is_dir() else HERE.parents[1] / "src" / "data"
SECTIONS_JSON = DATA / "sections.json"
VOICE_JSON = DATA / "voice.json"
KNOWLEDGE = HERE / "knowledge"


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    line: str
    follow: str
    status: str
    ideas: tuple[str, ...]


@dataclass(frozen=True)
class Target:
    """One thing Tanvi can switch, open or point at: a control in a home section, or a part of one
    of the site's other pages (``page`` set, ``section`` empty), scrolled to beside her."""

    id: str
    section: str
    does: str
    page: str = ""


@dataclass(frozen=True)
class Page:
    """One of the site's other pages, shown beside Tanvi in Talk mode (the call carries on)."""

    id: str
    url: str
    title: str
    does: str


@dataclass(frozen=True)
class Link:
    """A page she can hand the visitor, shown as a link under her."""

    id: str
    url: str
    label: str
    does: str


SECTIONS: tuple[Section, ...] = tuple(
    Section(s["id"], s["title"], s["line"], s["follow"], s["status"], tuple(s["ideas"]))
    for s in json.loads(SECTIONS_JSON.read_text())
)
SECTIONS_BY_ID = {s.id: s for s in SECTIONS}

_VOICE = json.loads(VOICE_JSON.read_text())
TARGETS: tuple[Target, ...] = tuple(
    Target(t["id"], t["section"], t["does"]) for t in _VOICE["targets"]
) + tuple(Target(x["id"], "", x["does"], x["page"]) for x in _VOICE.get("parts", []))
TARGETS_BY_ID = {t.id: t for t in TARGETS}
LINKS: tuple[Link, ...] = tuple(
    Link(x["id"], x["url"], x["label"], x["does"]) for x in _VOICE["links"]
)
LINKS_BY_ID = {x.id: x for x in LINKS}
PAGES: tuple[Page, ...] = tuple(
    Page(x["id"], x["url"], x["title"], x["does"]) for x in _VOICE["pages"]
)
PAGES_BY_ID = {x.id: x for x in PAGES}
# Named blocks of the home sections (``ways.pnp_demo``): not things she can show, but how the
# browser says what is on the visitor's screen. Written by ``pnpm voice:parts``.
BLOCKS_BY_ID: dict[str, str] = {x["id"]: x["does"] for x in _VOICE.get("blocks", [])}


def describe(id_: str) -> str | None:
    """What a target, a page part or a home block is, in words, or None for an id the site no longer has."""
    t = TARGETS_BY_ID.get(id_)
    return t.does if t else BLOCKS_BY_ID.get(id_)


# Built from the registry at import. Literal[...] with a tuple subscript is the
# runtime spelling of Literal["shift", "action", ...].
# A type checker cannot read a Literal built at runtime, so it sees plain str.
if TYPE_CHECKING:
    SectionId = str
    TargetId = str
    LinkId = str
    PageId = str
else:
    SectionId = Literal[tuple(s.id for s in SECTIONS)]
    TargetId = Literal[tuple(t.id for t in TARGETS)]
    LinkId = Literal[tuple(x.id for x in LINKS)]
    PageId = Literal[tuple(x.id for x in PAGES)]
Mode = Literal["talk", "read"]


def page_digest() -> str:
    """One block per section: what it is, the line the site gives it, and whether it is finished."""
    rows = []
    for s in SECTIONS:
        state = (
            "finished"
            if s.status == "built"
            else "PLACEHOLDER (content is being written; say so if asked for detail)"
        )
        rows.append(f"- {s.id}: {s.title}. {state}. Gist: {s.line}")
    return "\n".join(rows)


def targets_digest() -> str:
    """Every target, grouped by section, then the page parts grouped by page, for the show tool."""
    rows = []
    for s in SECTIONS:
        own = [t for t in TARGETS if t.section == s.id]
        if own:
            rows.append(f"{s.id}:")
            rows.extend(f"  - {t.id}: {t.does}" for t in own)
    for p in PAGES:
        own = [t for t in TARGETS if t.page == p.id]
        if own:
            rows.append(f"{p.id} page:")
            rows.extend(f"  - {t.id}: {t.does}" for t in own)
    return "\n".join(rows)


def pages_digest() -> str:
    return "\n".join(f"- {x.id}: {x.title}. {x.does}" for x in PAGES)


def links_digest() -> str:
    return "\n".join(f"- {x.id}: {x.label}. {x.does}" for x in LINKS)


def core_knowledge() -> str:
    return (KNOWLEDGE / "core.md").read_text()


def screens() -> str:
    return (KNOWLEDGE / "screens.md").read_text()


def other_pages() -> str:
    """The site's pages beyond the home page (solutions, company), as Tanvi hands them over."""
    return (KNOWLEDGE / "pages.md").read_text()
