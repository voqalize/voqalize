#!/usr/bin/env python3
"""Walk the docs the way a coding agent walks them, and fail if it gets stuck.

A human enters the docs through the sidebar, which Starlight renders on every
page — so a page that nothing links to is still one click away and nobody
notices it is orphaned. **An agent has no sidebar.** It is handed one paragraph
by the MCP server, follows that to `llms.txt`, and from there it has only the
links inside the markdown. That is a graph, and a graph can be disconnected.

This walks that graph over the built site and asserts the properties the agent's
path actually depends on. `infra/scripts/check_links.py` in the platform repo
checks the *other* half — that every `href` in the rendered HTML resolves,
across the marketing/docs seam — and deliberately reads HTML only. Neither is a
superset of the other: the `.md` twins are not HTML and the sidebar is not
markdown, and the defects this file exists for were all invisible to a check
that reads one and not the other.

Three of them were live on 2026-08-25, all found by hand:

  * **The apex had no twin and no index entry.** It was `index.mdx`, a JSX splash
    page, and `markdownPages()` filtered `.mdx` out. So L1 — the whole model at
    low resolution — was the single page an agent could not fetch, and its path
    ran from the handshake straight into a section hub.
  * **Redirects emitted no markdown.** Astro implements a static redirect as
    meta-refresh HTML, so a retired URL answered for a human and 404'd for an
    agent following the same link out of an `llms.txt` fetched last week.
  * **A "Next" list named the same page twice.** Two retired slugs were relinked
    to one page, and the two bullets that had been distinct became a bullet and
    its copy — a wasted decision point for a reader whose whole navigation is
    that list. Found by a reviewer, not by this file, which is why the
    same-target-twice rule below now exists.
  * **Sub-groups fell out of their section.** `llms.txt` read `item.slug` one
    level deep, so the six pages nested under Build's "Your first brain" landed
    in the trailing "Other" catch-all instead.

Run against a built tree:

    pnpm build && python3 check_navigation.py

CI runs it in `.github/workflows/ci-web.yml`, right after the docs build.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SITE = "https://docs.voqalize.com"

# `](/build/session.md)`, `](/index.md#the-boundary)` — the root-relative links
# a twin carries. An external URL, a bare anchor and an asset are all left to
# check_links.py, which resolves them against both assembled trees.
LINK = re.compile(r"\]\((/[^)\s]*)\)")
LLMS_LINK = re.compile(r"\]\((https?://[^)\s]+)\)")
LIST_ITEM = re.compile(r"^\s*(?:[-*]|\d+\.)\s")
# The keys of `src/redirects.mjs`, read rather than restated: this file has to
# know which paths are stubs, and a second copy of that list is a second thing
# to forget.
RETIRED = re.compile(r'^\s*"(/[^"]+)":\s*"(/[^"]*)"', re.M)


def fail(problems: list[str]) -> None:
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dist", default=Path(__file__).parent / "dist", type=Path)
    args = ap.parse_args()
    dist: Path = args.dist

    if not (dist / "llms.txt").is_file():
        print(f"no built site at {dist} — run `pnpm build` first", file=sys.stderr)
        return 1

    twins = {p.relative_to(dist).as_posix() for p in dist.rglob("*.md")}
    redirects = dict(RETIRED.findall((Path(__file__).parent / "src" / "redirects.mjs").read_text()))
    stubs = {f"{old.lstrip('/')}.md" for old in redirects}
    problems: list[str] = []

    # ── llms.txt is the entry point, so it is checked hardest ────────────────
    llms = (dist / "llms.txt").read_text()
    if not llms.startswith("# Voqalize\n"):
        problems.append("llms.txt does not open with `# Voqalize`")
    if "\n> " not in llms:
        problems.append("llms.txt carries no `>` tagline — the one line an agent reads first")
    if "\n## Other\n" in llms:
        problems.append(
            "llms.txt has an `Other` section: a page is missing from src/sidebar.mjs, "
            "or a sub-group is not being flattened into its section"
        )

    indexed: list[str] = []
    for url in LLMS_LINK.findall(llms):
        if not url.startswith(f"{SITE}/"):
            problems.append(f"llms.txt links off-site: {url}")
            continue
        path = url[len(SITE) + 1 :]
        if not path.endswith(".md"):
            problems.append(f"llms.txt links rendered HTML, not markdown: {url}")
        elif path not in twins:
            problems.append(f"llms.txt links a file the build did not emit: {url}")
        else:
            indexed.append(path)

    for path, count in ((p, indexed.count(p)) for p in set(indexed)):
        if count > 1:
            problems.append(f"llms.txt lists {path} {count} times")

    # The apex is L1. An agent that reads a section hub without it has the
    # branch and not the tree, so it has to be named, and named first.
    if "index.md" not in indexed:
        problems.append("llms.txt never names the apex (index.md) — an agent enters below L1")
    elif indexed[0] != "index.md":
        problems.append(f"llms.txt names {indexed[0]} before the apex; L1 goes first")

    # ── every twin is well-formed, and its links land ────────────────────────
    reachable = {"index.md"} | set(indexed)
    for path in sorted(twins):
        body = (dist / path).read_text()
        if not body.startswith("---\n"):
            problems.append(f"{path} has no frontmatter")
            continue
        front, _, rest = body[4:].partition("\n---\n")
        for key in ("title", "source"):
            if not re.search(rf"^{key}: ", front, re.M):
                problems.append(f"{path} frontmatter has no `{key}`")
        # A list that names the same page twice is a relink that collided: two
        # bullets that used to point at different pages now point at one, and a
        # reader whose entire navigation is that list spends a decision on a
        # copy. Checked per contiguous run of list items, so a page may
        # legitimately link the same target from prose and from its "Next".
        run: list[str] = []
        for line in [*rest.splitlines(), ""]:
            if LIST_ITEM.match(line):
                run.extend(LINK.findall(line))
                continue
            for href in {h for h in run if run.count(h) > 1}:
                problems.append(f"{path} names {href} twice in one list")
            run = []

        for href in LINK.findall(rest):
            target = href.split("#", 1)[0].lstrip("/")
            if target.endswith(".md"):
                if target in twins:
                    reachable.add(target)
                else:
                    problems.append(f"{path} links a file the build did not emit: {href}")
            elif not (dist / target).is_file():
                # `/llms.txt` and an asset are files and are fine. A directory is
                # rendered HTML — a link into it from inside markdown drops the
                # agent out of the format it asked for. `markdownLinks()` rewrites
                # the ones it can; anything left is a page we do not publish.
                problems.append(f"{path} links out of markdown: {href}")
            if target in stubs:
                problems.append(f"{path} links a retired URL: {href} — relink it")

    # ── a retired URL answers in both formats ────────────────────────────────
    # Reached from outside — an old bookmark, an `llms.txt` fetched last week —
    # so they are deliberately unreachable from inside the graph, and excluded
    # from the orphan check below rather than being linked from anywhere.
    for old, new in sorted(redirects.items()):
        if f"{old.lstrip('/')}.md" not in twins:
            problems.append(f"{old} redirects for a human but 404s as markdown")
        if not (dist / old.lstrip("/") / "index.html").is_file():
            problems.append(f"{old} has a markdown stub but no redirect for a browser")
        target = "index.md" if new == "/" else f"{new.lstrip('/')}.md"
        if target not in twins:
            problems.append(f"{old} redirects to {new}, which does not exist")

    # ── nothing is orphaned ──────────────────────────────────────────────────
    for path in sorted(twins - reachable - stubs):
        problems.append(f"{path} is in the build but nothing links to it")

    if problems:
        print(f"{len(problems)} navigation problem(s):", file=sys.stderr)
        fail(problems)
        return 1

    print(
        f"{len(twins) - len(stubs)} markdown pages, {len(indexed)} indexed in llms.txt, "
        f"{len(stubs)} retired URLs answering in both formats, 0 unreachable"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
