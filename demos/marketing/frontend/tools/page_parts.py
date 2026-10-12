"""List the parts of the site's other pages that Tanvi can scroll to, from the built site.

    pnpm voice:parts      # builds the site, then runs this on the build

Every page in ``src/data/voice.json`` ("pages") is read from the build; every element
marked ``data-part`` becomes a part, named after its heading (and, for a solution page's
story scenes, the scene's number and kicker). The result replaces ``parts`` in
``voice.json``, which the brain turns into ``show`` targets (``retail.scene2``) and the
browser scrolls to inside the page beside Tanvi. Run it after changing a page's copy or
sections; ``pnpm test:e2e`` fails if a listed part is missing from its page.

The home page's sections are read too: a ``data-part`` inside a ``data-section`` becomes a
block (``ways.pnp_demo``), described by its ``data-part-label`` (or, for a heading block, its
heading). Blocks replace ``blocks`` in ``voice.json``; they are how the browser tells the brain
what is on the visitor's screen, so Tanvi can name what they are looking at.
"""

from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOICE = ROOT / "src" / "data" / "voice.json"
VOID = {
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
    "source",
    "track",
    "wbr",
}
HEADINGS = {"h1", "h2", "h3"}


class Parts(HTMLParser):
    """Collects, per data-part, its first heading's text and a scene kicker if it has one."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.open: list[dict] = []  # parts being read: {part, depth, heading, kicker, grab}
        self.found: list[dict] = []
        self.sections: list[tuple[str, int]] = []  # home sections being read: (id, depth)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag in VOID:
            return
        self.depth += 1
        if section := a.get("data-section"):
            self.sections.append((section, self.depth))
        if a.get("data-part"):
            self.open.append(
                {
                    "part": a["data-part"],
                    "depth": self.depth,
                    "heading": "",
                    "kicker": "",
                    "grab": None,
                    "label": a.get("aria-label") or "",
                    "says": a.get("data-part-label") or "",
                    "section": self.sections[-1][0] if self.sections else "",
                }
            )
        if not self.open:
            return
        cur = self.open[-1]
        cls = a.get("class") or ""
        if cur["grab"] is None:
            if (tag in HEADINGS or "demo__title" in cls) and not cur["heading"]:
                cur["grab"] = ("heading", self.depth)
            elif ("sol-scene__kicker" in cls or "demo__tag" in cls) and not cur["kicker"]:
                cur["grab"] = ("kicker", self.depth)

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID:
            return
        for cur in self.open:
            if cur["grab"] and cur["grab"][1] == self.depth:
                cur["grab"] = None
        if self.open and self.open[-1]["depth"] == self.depth:
            self.found.append(self.open.pop())
        if self.sections and self.sections[-1][1] == self.depth:
            self.sections.pop()
        self.depth -= 1

    def handle_data(self, data: str) -> None:
        for cur in self.open:
            if cur["grab"]:
                cur[cur["grab"][0]] += data


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def describe(part: str, heading: str, kicker: str) -> str:
    heading = clean(heading).rstrip(".")
    kicker = re.sub(r"^\d+\s*", "", clean(kicker))
    end = "" if heading.endswith("?") else "."
    if part.startswith("scene"):
        return f"Scene {part[5:]}, {kicker}: {heading}{end}"
    if part.startswith("demo-"):
        return f"The {kicker} demo: {heading}{end}" if kicker else f"Demo: {heading}{end}"
    return f"{heading}{end}"


def page_file(build: Path, url: str) -> Path:
    for f in (build / url.strip("/") / "index.html", build / f"{url.strip('/')}.html"):
        if f.exists():
            return f
    raise SystemExit(f"{url}: not in the build at {build}")


def main(build: Path) -> None:
    voice = json.loads(VOICE.read_text())
    parts = []
    for page in voice["pages"]:
        text = page_file(build, page["url"]).read_text()
        p = Parts()
        p.feed(text)
        first: dict[str, dict] = {}
        for f in p.found:
            first.setdefault(f["part"], f)
        # Document order: a part is recorded when it closes, so sort by where it opens.
        order = sorted(first.values(), key=lambda f: text.find(f'data-part="{f["part"]}"'))
        for f in order:
            parts.append(
                {
                    "id": f"{page['id']}.{f['part']}",
                    "page": page["id"],
                    "part": f["part"],
                    "does": describe(f["part"], f["heading"] or f["label"], f["kicker"]),
                }
            )
    voice["parts"] = parts
    voice["blocks"] = home_blocks(build)
    VOICE.write_text(json.dumps(voice, indent=2, ensure_ascii=False) + "\n")
    print(
        f"{len(parts)} parts on {len(voice['pages'])} pages, {len(voice['blocks'])} blocks on the home page"
    )


def home_blocks(build: Path) -> list[dict]:
    text = (build / "index.html").read_text()
    p = Parts()
    p.feed(text)
    seen: dict[str, dict] = {}
    for f in p.found:
        if f["section"] and f["section"] != "page":
            seen.setdefault(f"{f['section']}.{f['part']}", f)
    order = sorted(seen.items(), key=lambda kv: text.find(f'data-part="{kv[1]["part"]}"'))
    blocks = []
    for id_, f in order:
        does = clean(f["says"]) or f"The section heading: {clean(f['heading']).rstrip('.')}."
        blocks.append({"id": id_, "section": f["section"], "part": f["part"], "does": does})
    return blocks


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist")
