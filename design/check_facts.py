#!/usr/bin/env python3
"""Hold ``facts.yaml`` and ``lexicon.yaml`` to the code, and prose to both.

A facts file that nobody checks is just another page that goes stale, which is
the exact failure it was written to stop. So this runs four checks, in the order
of how quietly each one fails:

1. **Drift.** Every fact carrying a ``derive:`` rule is re-read out of its source
   file. If ``facts.yaml`` says 0.3.0 and ``package.json`` says 0.4.0, the file
   is wrong and everything citing it is wrong with it. This is the check that
   makes the other three trustworthy.

2. **The mirror.** ``voice.md`` prints the lexicon as a table for people;
   ``lexicon.yaml`` holds it for the machine. They are one record rendered twice
   and are compared row by row, so neither can quietly gain a word.

3. **Contradicted prose.** Facts may carry ``forbid:`` — the sentences that are
   wrong *because* of the fact. "Not yet on npm" is not a typo; it is a true
   sentence that expired when 0.1.1 published.

4. **Retired vocabulary**, from ``lexicon.yaml``: the word for a concept that has
   two names, the outcome words, and the contrast grammar. Design notes are
   exempt by ``scope.reasoning_only`` — reasoning argues by contrast — except for
   ``platform``, which leaks.

Checks 1 and 2 are errors: the record disagrees with itself. Checks 3 and 4 are
findings against prose, and a finding is a sentence for a human to rewrite.

Facts whose source is a registry or one of the three sibling repos cannot be
derived from this tree. They carry ``reproduce:`` instead — the command that
re-earns the stamp — and are listed at the end as attested rather than checked,
with the age of the stamp, so nobody mistakes one for the other.

    python3 design/check_facts.py                 # drift + mirror + governed prose
    python3 design/check_facts.py --prose docs    # narrow the prose scan
    python3 design/check_facts.py --attested      # list what only a human can confirm

Needs pyyaml: ``uv run --with pyyaml python3 design/check_facts.py``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - environment, not logic
    sys.exit("check_facts needs pyyaml.\n  uv run --with pyyaml python3 design/check_facts.py")

DESIGN = Path(__file__).resolve().parent
ROOT = DESIGN.parent

# The table in voice.md this file mirrors. Matched on the header so a moved
# section still resolves, and so a *second* table cannot be mistaken for it.
LEXICON_TABLE_HEADING = "## Mechanics and lexicon"
TABLE_ROW = re.compile(
    r"^\|\s*(?P<concept>[^|]+?)\s*\|\s*(?P<word>[^|]+?)\s*\|\s*(?P<retired>[^|]*?)\s*\|\s*$"
)


def load(name: str) -> dict:
    return yaml.safe_load((DESIGN / name).read_text())


# --- 1. drift ---------------------------------------------------------------


def derived_value(rule: dict) -> str | list[str] | None:
    """Re-read one fact out of the tree. None means the rule found nothing."""
    if "glob" in rule:
        return str(len(list(ROOT.glob(rule["glob"]))))

    path = ROOT / rule["file"]
    if not path.is_file():
        return None
    text = path.read_text()

    if pluck := rule.get("json_pluck"):
        return [row[pluck["field"]] for row in json.loads(text)[pluck["key"]]]

    m = re.search(rule["pattern"], text, re.MULTILINE)
    return m.group(1) if m else None


def check_drift(facts: dict) -> list[str]:
    """Re-read every derivable fact out of its source.

    A list-valued fact is compared as a set, because the useful answer is which
    entry appeared or went missing rather than that two lengths differ. That is
    the whole argument for storing a roster instead of a count: a count can only
    tell you a number is wrong, and `demos.roster` has to tell you *orderdesk* is
    the one nothing links to.
    """
    errors = []
    for fid, fact in facts.items():
        rule = fact.get("derive")
        if not rule:
            continue
        got = derived_value(rule)
        want = fact["value"]
        src = rule.get("file", rule.get("glob"))

        if got is None:
            errors.append(f"{fid}: derive rule matched nothing in {src}")
        elif isinstance(want, list) and isinstance(got, list):
            for label, diff in (
                ("only in facts.yaml", set(want) - set(got)),
                (f"only in {src}", set(got) - set(want)),
            ):
                if diff:
                    errors.append(f"{fid}: {label}: {sorted(diff)}")
        elif str(got) != str(want):
            errors.append(f"{fid}: facts.yaml says {want!r}, {src} says {got!r}")
    return errors


# --- 2. the mirror ----------------------------------------------------------


def voice_table() -> list[tuple[str, str, str]]:
    lines = (DESIGN / "voice.md").read_text().splitlines()
    try:
        start = lines.index(LEXICON_TABLE_HEADING)
    except ValueError:
        return []
    rows = []
    for line in lines[start:]:
        if line.startswith("## ") and line != LEXICON_TABLE_HEADING:
            break
        m = TABLE_ROW.match(line)
        if not m:
            continue
        concept, word, retired = m.group("concept"), m.group("word"), m.group("retired")
        if concept in {"Concept", "---"} or set(concept) <= {"-"}:
            continue
        rows.append((concept, word.strip("*"), retired))
    return rows


def check_mirror(lexicon: dict) -> list[str]:
    table = voice_table()
    if not table:
        return [f"voice.md: no lexicon table found under {LEXICON_TABLE_HEADING!r}"]

    def norm(s: str) -> str:
        # voice.md uses typographic arrows; the yaml uses ascii.
        return s.replace("→", "->").replace("—", "-").strip().lower()

    errors = []
    yaml_rows = {norm(t["concept"]): t for t in lexicon["terms"]}
    md_rows = {norm(c): (w, r) for c, w, r in table}

    for only_in, missing in (
        ("lexicon.yaml", set(yaml_rows) - set(md_rows)),
        ("voice.md", set(md_rows) - set(yaml_rows)),
    ):
        for c in sorted(missing):
            errors.append(f"lexicon mirror: {c!r} is in {only_in} and not the other")

    for concept in sorted(set(yaml_rows) & set(md_rows)):
        y, (md_word, md_retired) = yaml_rows[concept], md_rows[concept]
        if norm(y["word"]) != norm(md_word):
            errors.append(
                f"lexicon mirror: {concept!r} word — yaml {y['word']!r}, voice.md {md_word!r}"
            )
        want = [norm(x) for x in y.get("retired", [])]
        got = [norm(x) for x in md_retired.split(",") if x.strip()]
        if want != got:
            errors.append(f"lexicon mirror: {concept!r} retired — yaml {want}, voice.md {got}")
    return errors


# --- 3 + 4. prose -----------------------------------------------------------


def governed_files(lexicon: dict, narrow: str | None) -> list[Path]:
    scope = lexicon["scope"]
    globs = scope["governed"] if narrow is None else [f"{narrow}/**/*.md*"]
    never = scope.get("never", [])
    seen: dict[Path, None] = {}
    for g in globs:
        for p in ROOT.glob(g):
            if not p.is_file() or p.suffix not in {".md", ".mdx", ".txt", ".astro"}:
                continue
            if exempt(p, never):
                continue
            seen[p] = None
    return sorted(seen)


def exempt(path: Path, patterns: list[str]) -> bool:
    rel = str(path.relative_to(ROOT))
    return any(fnmatch.fnmatch(rel, p) for p in patterns)


FENCE = re.compile(r"^\s*(```|~~~)")
CODE_SPAN = re.compile(r"`[^`]*`")


def prose_lines(text: str):
    """Yield (lineno, prose) with code removed.

    A lexicon rule is a rule about prose. `source="platform"` is an API literal
    and `serve_direct` is a symbol; neither is a writer choosing a word, and
    flagging them is how a checker teaches people to ignore it. Fenced blocks are
    skipped whole and inline spans are blanked, so a rule only ever sees the
    sentences a human wrote.
    """
    in_fence = False
    for n, line in enumerate(text.splitlines(), 1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        yield n, CODE_SPAN.sub("``", line)


def scan(files: list[Path], facts: dict, lexicon: dict, sweep: bool) -> tuple[list[str], list[str]]:
    rules: list[tuple[re.Pattern[str], str, list[str]]] = []

    for fid, fact in facts.items():
        for pat in fact.get("forbid", []):
            rules.append(
                (re.compile(pat), f"contradicts {fid} (= {fact['value']})", fact.get("except", []))
            )

    for word in lexicon["retired_words"]:
        rules.append((re.compile(rf"\b{re.escape(word)}\b", re.I), "retired word", []))

    for pr in lexicon.get("prohibited", []):
        rules.append(
            (re.compile(rf"\b{re.escape(pr['word'])}\b", re.I), "never used of Voqalize", [])
        )

    # Advisory: true often enough to print, not often enough to fail a build.
    # Contrast between two things inside our own system is allowed — that is how
    # an API gets described — and no regex can tell it from contrast against a
    # competitor. Same for the retired synonyms, which are ordinary English most
    # of the time. These are read by a person; they never set the exit code.
    advisory: list[tuple[re.Pattern[str], str, list[str]]] = []
    for c in lexicon.get("retired_constructions", []):
        if not c.get("manual") and "pattern" in c:
            advisory.append((re.compile(c["pattern"], re.I), c["name"], []))
    if sweep:
        for term in lexicon["terms"]:
            for old in term.get("retired", []):
                advisory.append(
                    (
                        re.compile(rf"\b{re.escape(old)}\b", re.I),
                        f"retired for {term['word']!r}",
                        [],
                    )
                )

    findings: list[str] = []
    advisories: list[str] = []
    for path in files:
        rel = path.relative_to(ROOT)
        for n, line in prose_lines(path.read_text()):
            for bucket, rs in ((findings, rules), (advisories, advisory)):
                for rx, why, exc in rs:
                    if exc and exempt(path, exc):
                        continue
                    if m := rx.search(line):
                        bucket.append(f"{rel}:{n}: {m.group(0)!r} — {why}")
    return findings, advisories


# --- attested ---------------------------------------------------------------


def attested(facts: dict, today: dt.date) -> list[str]:
    out = []
    for fid, fact in facts.items():
        if "derive" in fact:
            continue
        age = (today - fact["verified"]).days if isinstance(fact["verified"], dt.date) else None
        stamp = f"{fact['verified']} ({age}d)" if age is not None else str(fact["verified"])
        out.append(f"  {fid:34} {str(fact['value'])[:40]:42} {stamp}")
        if cmd := fact.get("reproduce"):
            out.append(f"  {'':34} $ {' '.join(cmd.split())[:90]}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prose", help="scan this subtree instead of lexicon.yaml's governed globs")
    ap.add_argument("--attested", action="store_true", help="list facts no local rule can check")
    ap.add_argument(
        "--sweep",
        action="store_true",
        help="also flag retired synonyms — advisory, mostly ordinary English",
    )
    ap.add_argument("--today", default=None, help="date to age stamps against (YYYY-MM-DD)")
    args = ap.parse_args()

    facts = load("facts.yaml")["facts"]
    lexicon = load("lexicon.yaml")

    if args.attested:
        today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
        print("Attested, not machine-checked — re-run the command to re-earn the stamp:\n")
        print("\n".join(attested(facts, today)))
        return 0

    errors = check_drift(facts) + check_mirror(lexicon)
    files = governed_files(lexicon, args.prose)
    findings, advisories = scan(files, facts, lexicon, args.sweep)

    if errors:
        print("The record disagrees with itself:\n")
        for e in errors:
            print(f"  {e}")
        print()

    if findings:
        print(f"Prose findings ({len(files)} files scanned):\n")
        for f in findings:
            print(f"  {f}")
        print()

    if advisories:
        print("Advisory — a person decides, and the exit code does not:\n")
        for a in advisories:
            print(f"  {a}")
        print()

    n_derived = sum(1 for f in facts.values() if "derive" in f)
    print(
        f"{len(facts)} facts ({n_derived} derived from source, "
        f"{len(facts) - n_derived} attested), {len(lexicon['terms'])} lexicon terms, "
        f"{len(files)} prose files — {len(errors)} error(s), {len(findings)} finding(s), "
        f"{len(advisories)} advisory"
    )
    return 1 if errors or findings else 0


if __name__ == "__main__":
    sys.exit(main())
