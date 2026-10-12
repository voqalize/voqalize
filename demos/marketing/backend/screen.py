"""What is on the visitor's screen, as Tanvi reads it.

The browser sends :class:`Viewing` each time the screen settles after a scroll, a resize, a tab
or a page change: the device, how the page is laid out around her, what is open, what is in
view (top to bottom, side by side where it is), the block they are reading, and the tab and
animation step showing. Ids are the site's own: home blocks (``ways.pnp_demo``), targets
(``ways.plug_and_play.step2``) and page parts (``retail.scene2``), all in ``voice.json``.

:class:`Screen` keeps the latest report, the trail since her last turn, and what the visitor has
looked at this call. Before each of her turns, if the screen changed since the last, one note
goes into the context: where they went and what they see now. ``where_they_are`` returns the
same picture on demand. One note per turn, not one per scroll: a visitor scrolling a page
sends a report a second, and the model needs where they ended up, not every frame between.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from voqalize.sdk import AppEvent

from .site import PAGES_BY_ID, SECTIONS_BY_ID, describe

Device = Literal["phone", "tablet", "desktop"]
Layout = Literal["centre", "beside", "tile"]


class Viewing(AppEvent):
    """What is on the visitor's screen once it settles: device, layout, where they are, what is in view."""

    device: Device
    layout: Layout
    section: str | None = None
    page: str | None = None
    path: str | None = None
    title: str | None = None
    rows: list[list[str]] = Field(default_factory=list)
    focus: str | None = None
    heading: str | None = None
    progress: int = 0
    showing: list[str] = Field(default_factory=list)


_DEVICE = {"phone": "a phone", "tablet": "a tablet", "desktop": "a computer"}
_LAYOUT = {
    "beside": "You are in a column on the left of their screen, and the page is on the right, beside you.",
    "tile": (
        "You are a small tile in a corner, over the page, and the page fills the screen. Things on it sit "
        "above or below each other unless the list below puts them side by side, so do not say left or right."
    ),
    "centre": "You are in the middle of their screen, and nothing is open beside you.",
}


def short(id_: str) -> str | None:
    """A block's name without its detail: "Scene 2, Check out" for "Scene 2, Check out: Ship it to ..."."""
    text = describe(id_)
    if text is None:
        return None
    return text.split(":", 1)[0].rstrip(".")


def place(v: Viewing) -> str | None:
    if v.page in PAGES_BY_ID:
        return f"the {PAGES_BY_ID[v.page].title} page"
    if v.path:
        return f"the page {v.title or v.path}"
    if v.section in SECTIONS_BY_ID:
        return f"the {SECTIONS_BY_ID[v.section].title} section"
    return None


def depth(progress: int) -> str:
    if progress <= 12:
        return "at the top"
    if progress >= 88:
        return "at the bottom"
    return (
        "partway down"
        if 30 <= progress <= 70
        else ("near the top" if progress < 30 else "near the bottom")
    )


class Screen:
    def __init__(self) -> None:
        self.now: Viewing | None = None
        self._noted: Viewing | None = None
        self._trail: list[str] = []  # where they went since her last turn, in order
        self.places: list[str] = []  # every section or page they have had open this call
        self.read: list[str] = []  # every block they have stopped to read this call

    def update(self, v: Viewing) -> None:
        before = self.now
        self.now = v
        here = place(v)
        if here and here not in self.places:
            self.places.append(here)
        if v.focus and describe(v.focus) and v.focus not in self.read:
            self.read.append(v.focus)
        moved = before is None or place(before) != here
        step = here if moved else None
        if v.focus and (moved or before is None or before.focus != v.focus):
            name = short(v.focus)
            step = f"{here}, at {name}" if moved and here and name else (name or step)
        if step and (not self._trail or self._trail[-1] != step):
            self._trail.append(step)

    def note(self) -> str | None:
        """The note for her next turn, or None when nothing changed since her last."""
        if self.now is None or (self.now == self._noted and not self._trail):
            return None
        trail = self._trail if self._noted is not None else []
        moved = ""
        if trail:
            path = trail if len(trail) <= 5 else [*trail[:2], "...", *trail[-2:]]
            moved = f"Since your last turn they moved: {'; then '.join(path)}. "
        self._noted, self._trail = self.now, []
        return f"(THEIR SCREEN, as of now. {moved}{self.describe()})"

    def describe(self) -> str:
        v = self.now
        if v is None:
            return "Nothing is known yet about their screen."
        out = [f"They are on {_DEVICE[v.device]}. {_LAYOUT[v.layout]}"]
        here = place(v)
        if here:
            out.append(f"Open: {here}, scrolled {depth(v.progress)}.")
        showing = [s for s in (describe(x) for x in v.showing) if s]
        if showing:
            out.append(
                "Selected or playing now: " + "; ".join(s.rstrip(".") for s in showing) + "."
            )
        rows = [[d for x in row if (d := describe(x))] for row in v.rows]
        rows = [r for r in rows if r]
        if rows:
            lines = []
            for i, row in enumerate(rows):
                lead = "At the top" if i == 0 else "Below that"
                if len(row) == 1:
                    lines.append(f"{lead}: {row[0].rstrip('.')}.")
                else:
                    lines.append(
                        f"{lead}, side by side from left to right: "
                        + "; ".join(r.rstrip(".") for r in row)
                        + "."
                    )
            out.append("In view, from the top of the screen down. " + " ".join(lines))
        elif here:
            out.append("No part of it you have words for is in view.")
        if v.focus and describe(v.focus):
            out.append(f"What they are reading: {short(v.focus)}.")
        if v.heading:
            out.append(f'The heading above what they are reading says "{v.heading}".')
        earlier = [p for p in self.places if p != here]
        if earlier:
            out.append("Earlier in this call they looked at " + ", ".join(earlier) + ".")
        return " ".join(out)

    def history(self) -> str:
        """Every block they stopped to read this call, for where_they_are."""
        names = [n for n in (short(x) for x in self.read) if n]
        return (
            ("Blocks they have read this call, in order: " + "; ".join(names) + ".")
            if names
            else ""
        )
