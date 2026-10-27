"""A small HTML tree and CSS matcher, for checking the anchor catalogue offline.

The extension finds every place Javier names by the selector in
``knowledge/L3/anchors.json``, on the visitor's live page. The catalogue is built
from saved copies of the site's pages (``demos/unosalud/fixtures``), and every
selector in it must find exactly one element there: ``knowledge/build.py`` and
``tests/test_unosalud_knowledge.py`` hold it to that with this module.

It is the standard library's parser and the slice of CSS the catalogue uses —
tag, ``#id``, ``.class``, ``[attr]``, ``[attr="v"]``, ``[attr$="v"]``,
``[attr^="v"]``, ``[attr*="v"]``, ``:nth-of-type(n)``, ``:has(…)``, and the
descendant and ``>`` combinators — so the demos backend takes on no HTML
dependency for a check that runs at build and test time only. A selector it
cannot read raises ``ValueError``: the catalogue must stay inside that slice,
which the browser reads the same way.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

__all__ = ["Element", "count", "parse", "parse_file", "select"]

_VOID = frozenset(
    "area base br col embed hr img input link meta param source track wbr".split()  # noqa: SIM905
)
#: Elements whose content is text, never markup.
_RAW = frozenset({"script", "style"})


@dataclass(eq=False)
class Element:
    tag: str
    attrs: dict[str, str]
    parent: Element | None = None
    children: list[Element] = field(default_factory=list["Element"])
    texts: list[str] = field(default_factory=list[str])
    """The text directly inside it, in order (not its children's)."""

    @property
    def id(self) -> str:
        return self.attrs.get("id", "")

    @property
    def classes(self) -> set[str]:
        return set(self.attrs.get("class", "").split())

    def iter(self) -> list[Element]:
        """It and every element under it, in document order."""
        out: list[Element] = []
        stack: list[Element] = [self]
        while stack:
            el = stack.pop()
            out.append(el)
            stack.extend(el.children[::-1])
        return out

    def text(self) -> str:
        """Its text and its children's, whitespace folded."""
        parts: list[str] = []

        def walk(el: Element) -> None:
            if el.tag in _RAW:
                return
            parts.extend(el.texts)
            for child in el.children:
                walk(child)

        walk(self)
        return " ".join(" ".join(parts).split())


class _Builder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Element("#document", {})
        self._stack: list[Element] = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        parent = self._stack[-1]
        el = Element(tag, {k: v or "" for k, v in attrs}, parent)
        parent.children.append(el)
        if tag not in _VOID:
            self._stack.append(el)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        parent = self._stack[-1]
        parent.children.append(Element(tag, {k: v or "" for k, v in attrs}, parent))

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self._stack) - 1, 0, -1):
            if self._stack[i].tag == tag:
                del self._stack[i:]
                return

    def handle_data(self, data: str) -> None:
        if data.strip():
            self._stack[-1].texts.append(data)


def parse(html: str) -> Element:
    builder = _Builder()
    builder.feed(html)
    builder.close()
    return builder.root


def parse_file(path: Path) -> Element:
    return parse(path.read_text(encoding="utf-8"))


# ─── Selectors ─────────────────────────────────────────────────────────────────

_ATTR = re.compile(r"""\[\s*([\w:-]+)\s*(?:([$^*]?=)\s*(?:"([^"]*)"|'([^']*)'|([^\]\s]+))\s*)?\]""")
_SIMPLE = re.compile(r"[#.]?[\w-]+|\*")


@dataclass
class _Compound:
    tag: str | None = None
    ids: list[str] = field(default_factory=list[str])
    classes: list[str] = field(default_factory=list[str])
    attrs: list[tuple[str, str, str]] = field(default_factory=list[tuple[str, str, str]])
    nth_of_type: int | None = None
    has: list[list[tuple[str, _Compound]]] = field(
        default_factory=list[list[tuple[str, "_Compound"]]]
    )


def _split_has(text: str, start: int) -> tuple[str, int]:
    """The argument of ``:has(`` opened at ``start``, and the index after its ``)``."""
    depth = 0
    quote = ""
    for i in range(start, len(text)):
        c = text[i]
        if quote:
            if c == quote:
                quote = ""
        elif c in "\"'":
            quote = c
        elif c == "(":
            depth += 1
        elif c == ")":
            if depth == 0:
                return text[start:i], i + 1
            depth -= 1
    raise ValueError(f"unclosed :has( in {text!r}")


def _compile(selector: str) -> list[tuple[str, _Compound]]:
    """``selector`` as (combinator, compound) steps; the first combinator is ``" "``."""
    steps: list[tuple[str, _Compound]] = []
    i = 0
    s = selector.strip()
    if s.startswith(">"):
        # A relative selector inside :has(> …).
        s = s[1:].strip()
        combinator = ">"
    else:
        combinator = " "
    while i < len(s):
        comp = _Compound()
        started = False
        while i < len(s) and s[i] not in " >":
            if s[i] == "[":
                m = _ATTR.match(s, i)
                if m is None:
                    raise ValueError(f"cannot read the attribute at {s[i:]!r}")
                op = m.group(2) or ""
                value = next((g for g in m.group(3, 4, 5) if g is not None), "")
                comp.attrs.append((m.group(1), op, value))
                i = m.end()
            elif s.startswith(":has(", i):
                inner, i = _split_has(s, i + 5)
                comp.has.append(_compile(inner))
            elif s.startswith(":nth-of-type(", i):
                end = s.index(")", i)
                comp.nth_of_type = int(s[i + 13 : end])
                i = end + 1
            else:
                m = _SIMPLE.match(s, i)
                if m is None:
                    raise ValueError(f"cannot read the selector at {s[i:]!r} in {selector!r}")
                tok = m.group()
                if tok.startswith("#"):
                    comp.ids.append(tok[1:])
                elif tok.startswith("."):
                    comp.classes.append(tok[1:])
                elif tok != "*":
                    comp.tag = tok.lower()
                i = m.end()
            started = True
        if not started:
            raise ValueError(f"empty compound in {selector!r}")
        steps.append((combinator, comp))
        j = i
        while j < len(s) and s[j] == " ":
            j += 1
        if j < len(s) and s[j] == ">":
            combinator = ">"
            j += 1
            while j < len(s) and s[j] == " ":
                j += 1
        else:
            combinator = " "
        i = j
    return steps


def _matches(el: Element, comp: _Compound) -> bool:
    if el.tag.startswith("#"):
        return False
    if comp.tag is not None and el.tag != comp.tag:
        return False
    if any(el.id != i for i in comp.ids):
        return False
    if comp.classes and not set(comp.classes) <= el.classes:
        return False
    for name, op, value in comp.attrs:
        if name not in el.attrs:
            return False
        have = el.attrs[name]
        if (
            (op == "=" and have != value)
            or (op == "$=" and not have.endswith(value))
            or (op == "^=" and not have.startswith(value))
            or (op == "*=" and value not in have)
        ):
            return False
    if comp.nth_of_type is not None:
        parent = el.parent
        same = [c for c in parent.children if c.tag == el.tag] if parent else [el]
        if comp.nth_of_type < 1 or comp.nth_of_type > len(same):
            return False
        if same[comp.nth_of_type - 1] is not el:
            return False
    return all(_has(el, rel) for rel in comp.has)


def _has(el: Element, rel: list[tuple[str, _Compound]]) -> bool:
    """Whether a relative selector matches something under ``el``."""
    first_comb, _ = rel[0]
    scope = el.children if first_comb == ">" else el.iter()[1:]
    return any(_matches_steps(c, rel, anchor=el) for c in scope)


def _matches_steps(
    el: Element, steps: list[tuple[str, _Compound]], anchor: Element | None = None
) -> bool:
    """Whether ``el`` is matched by the last step, with the steps before it
    matched by its ancestors (and, for a relative selector, under ``anchor``)."""
    comb, comp = steps[-1]
    if not _matches(el, comp):
        return False
    rest = steps[:-1]
    if not rest:
        if anchor is None:
            return True
        return el.parent is anchor if comb == ">" else _under(el, anchor)
    parent = el.parent
    if comb == ">":
        return parent is not None and parent is not anchor and _matches_steps(parent, rest, anchor)
    while parent is not None and parent is not anchor:
        if _matches_steps(parent, rest, anchor):
            return True
        parent = parent.parent
    return False


def _under(el: Element, anchor: Element) -> bool:
    p = el.parent
    while p is not None:
        if p is anchor:
            return True
        p = p.parent
    return False


def select(root: Element, selector: str) -> list[Element]:
    """Every element under ``root`` that ``selector`` matches, in document order."""
    steps = _compile(selector)
    return [el for el in root.iter() if _matches_steps(el, steps)]


def count(root: Element, selector: str) -> int:
    return len(select(root, selector))
