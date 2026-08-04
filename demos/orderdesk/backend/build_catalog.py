"""Build ``catalog.db`` from the Enterro CSV — stdlib only, offline, run once.

    uv run python demos/orderdesk/backend/build_catalog.py

The demo ships the built ``.db`` (committed) so nothing parses 20k CSV rows at
session time; this script is how that file is reproduced. It is deliberately
dumb: read the CSV, run every name through :mod:`normalize` (the *same* module
``search.py`` runs a query through, so index and query agree by construction),
write three tables, print a validation summary.

Schema (DESIGN.md §2):

* ``products`` — one row per SKU, the wire shape plus the parsed axes.
* ``tokens``   — ``(token, products.rowid)``, one row per distinct word of a
  product's searchable text: a plain inverted index. A prefix query is a range
  scan over its primary key (``token >= 'VOLIN' AND token < 'VOLIN\\uffff'``),
  which is what makes "thyro" mid-typing cost microseconds.
* ``phonetic`` — ``(token, key, family, alt)``, one row per distinct brand-root
  token *per key it can be heard under*: :func:`normalize.phonetic_keys` gives
  the canonical key plus the alternates of the confusions that are too
  destructive to fold into the key itself (B/V, soft C/G, epenthetic vowels).
  This is the misheard-brand recovery layer ("abeyvee" → ABEVIA, "vecosules" →
  BECOSULES).

DESIGN.md §2 specified fts5 for the middle table. It cannot be used: the
uv-managed CPython that runs the brain (and the Docker image) links a sqlite
built **without** the fts5 module, so ``CREATE VIRTUAL TABLE … USING fts5``
raises ``no such module: fts5`` there and every prefix query dies while whole-
word queries keep working — the worst possible failure shape for a search bar.
The ``tokens`` table is the same capability (prefix-AND over the same text) in
plain sqlite, portable to every interpreter, and about as fast; ranking never
depended on bm25 anyway, since :mod:`search` scores every candidate itself.

The summary at the end is the acceptance check for the *family model*: the
brand-root grouping is the one modelling decision the whole demo rests on, so
the anchor counts (TELMA ~26, VOLINI 10, 4 QUIN 6, THYRONORM 8, AUGMENTIN 6)
are printed every build rather than trusted.
"""

from __future__ import annotations

import csv
import sqlite3
import sys
import time
from pathlib import Path

try:  # package import (brain) vs script import (`python build_catalog.py`)
    from .normalize import (
        clean_product_name,
        fts_terms,
        normalize_pack_size,
        normalize_ws,
        parse_name,
        phonetic_keys,
        search_text,
    )
except ImportError:  # pragma: no cover — the `python build_catalog.py` path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from normalize import (  # type: ignore[no-redef]
        clean_product_name,
        fts_terms,
        normalize_pack_size,
        normalize_ws,
        parse_name,
        phonetic_keys,
        search_text,
    )

HERE = Path(__file__).resolve().parent
CSV_PATH = HERE.parent / "data" / "enterro_products.csv"
DB_PATH = HERE / "catalog.db"

SCHEMA = """
CREATE TABLE products (
    code          TEXT PRIMARY KEY,
    product_id    TEXT NOT NULL,
    name          TEXT NOT NULL,   -- display: clean, no trailing -CODE suffix
    name_clean    TEXT NOT NULL,   -- search key: uppercase, hyphens flattened
    family        TEXT NOT NULL,   -- brand root ("TELMA", "4 QUIN")
    variant_label TEXT NOT NULL,   -- suffix line ("MAXX", "CT", "JOINT XPERT")
    form          TEXT NOT NULL,   -- "TABLET", "EYE DROPS", ""
    strength      TEXT NOT NULL,   -- "40 MG", "40/6.25", "0.05%", ""
    pack_size     TEXT NOT NULL,   -- normalized ("10'S", "100 GM", "1 x 15")
    mrp           REAL NOT NULL,
    ptr           REAL NOT NULL,
    stock         INTEGER NOT NULL,
    manufacturer  TEXT NOT NULL,
    scheme        TEXT NOT NULL
);

CREATE TABLE tokens (
    token TEXT NOT NULL,      -- one word of name_clean / family / form
    ref   INTEGER NOT NULL,   -- products.rowid
    PRIMARY KEY (token, ref)  -- the whole table *is* the index
) WITHOUT ROWID;

CREATE TABLE phonetic (
    token  TEXT NOT NULL,
    key    TEXT NOT NULL,
    family TEXT NOT NULL,
    alt    INTEGER NOT NULL,   -- 0 canonical key, 1 an alternate (B/V, soft C/G, …)
    PRIMARY KEY (key, family, token)
) WITHOUT ROWID;

CREATE INDEX idx_products_family     ON products(family);
CREATE INDEX idx_products_form       ON products(form);
CREATE INDEX idx_products_name_clean ON products(name_clean);
CREATE INDEX idx_phonetic_key        ON phonetic(key);
"""

#: Brands whose SKU count is the acceptance check on the family model.
ANCHORS = {"TELMA": 26, "VOLINI": 10, "4 QUIN": 6, "THYRONORM": 8, "AUGMENTIN": 6}

#: Scenario SKUs (frontend/src/data.ts) — every one must survive the build.
SCENARIO_CODES = (
    "J0031270",
    "J0029359",
    "J0024991",
    "J0010291",
    "J0004502",
    "J0014899",
    "J0038288",
    "J0042294",
    "J0034539",
    "J0034534",
    "J0006463",
    "J0016849",
    "J0018841",
    "J0009625",
    "PROD1750",
    "PROD4392",
    "J0050820",
    "J0002080",
    "J0037800",
    "PROD5666",
    "J0002149",
)


def _num(text: str, *, default: float = 0.0) -> float:
    try:
        return float((text or "").strip())
    except ValueError:
        return default


def read_rows(csv_path: Path) -> list[tuple[object, ...]]:
    """CSV → the ``products`` tuples, parsed and normalized."""
    out: list[tuple[object, ...]] = []
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            code = normalize_ws(raw.get("Product_Code") or "")
            if not code:
                continue
            name = clean_product_name(raw.get("Product_Name") or "")
            if not name:
                continue
            parsed = parse_name(name)
            out.append(
                (
                    code,
                    normalize_ws(raw.get("Product_ID") or ""),
                    name,
                    search_text(name),
                    parsed.family,
                    parsed.variant_label,
                    parsed.form,
                    parsed.strength,
                    normalize_pack_size(raw.get("Pack_Size") or ""),
                    _num(raw.get("MRP") or ""),
                    _num(raw.get("PTR") or ""),
                    int(_num(raw.get("Available_Stock") or "")),
                    normalize_ws(raw.get("manufacture") or ""),
                    normalize_ws(raw.get("Scheme") or ""),
                )
            )
    return out


def token_rows(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    """Every searchable word of every product, paired with its rowid.

    Indexed text is ``name_clean`` plus ``family`` and ``form`` — the last two
    are almost always words of the name already, but a canonicalized form
    ("SUSP." → "SUSPENSION") is not, and a query says the canonical one.

    Splitting goes through :func:`normalize.fts_terms`, the *same* function
    ``search.py`` splits a query with, so "TELMA 40/6.25" is stored as 40, 6 and
    25 and a caller asking for "6.25" asks for tokens that can exist.
    """
    rows: set[tuple[str, int]] = set()
    for ref, name_clean, family, form in conn.execute(
        "SELECT rowid, name_clean, family, form FROM products"
    ):
        for text in (name_clean, family, form):
            for token in fts_terms(str(text)):
                rows.add((token, ref))
    return sorted(rows)


def phonetic_rows(families: set[str]) -> list[tuple[str, str, str, int]]:
    """One ``(token, key, family, alt)`` row per alphabetic brand-root token *per
    key it can be heard under*.

    Multi-word roots also get a squashed row ("4 QUIN" → token ``4QUIN``) so a
    caller who runs the words together still lands on the family.

    Keys come from :func:`normalize.phonetic_keys` — the canonical key (``alt``
    0) plus the alternates that a confusion the coder deliberately does not fold
    would produce (``alt`` 1): BECOSULES is also stored under V, OMNIGEL under
    the soft-G "omnijel" key. ``search.py`` probes with the *same* function, so
    the two sides agree by construction rather than by review.
    """
    seen: dict[tuple[str, str, str], int] = {}
    for family in families:
        tokens = family.split()
        squashed = ["".join(tokens)] if len(tokens) > 1 else []
        for token in [*tokens, *squashed]:
            if len(token) < 2:
                continue
            for rank, key in enumerate(phonetic_keys(token)):
                row = (token, key, family)
                seen[row] = min(seen.get(row, 1), 1 if rank else 0)
    return sorted((t, k, f, alt) for (t, k, f), alt in seen.items())


def build(csv_path: Path = CSV_PATH, db_path: Path = DB_PATH) -> sqlite3.Connection:
    """(Re)build ``catalog.db`` from scratch and return the open connection."""
    rows = read_rows(csv_path)
    if not rows:
        raise RuntimeError(f"build_catalog: no usable rows in {csv_path}")

    db_path.unlink(missing_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.executemany(
        "INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.executemany("INSERT INTO tokens(token, ref) VALUES (?,?)", token_rows(conn))
    conn.executemany(
        "INSERT INTO phonetic(token, key, family, alt) VALUES (?,?,?,?)",
        phonetic_rows({str(row[4]) for row in rows}),
    )
    conn.commit()
    conn.execute("VACUUM")
    conn.execute("ANALYZE")
    conn.commit()
    return conn


def summarize(conn: sqlite3.Connection, db_path: Path = DB_PATH) -> bool:
    """Print the build report; return False if an acceptance check failed."""
    ok = True
    skus = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    fams = conn.execute("SELECT COUNT(DISTINCT family) FROM products").fetchone()[0]
    phon = conn.execute("SELECT COUNT(*) FROM phonetic").fetchone()[0]
    toks = conn.execute("SELECT COUNT(DISTINCT token) FROM tokens").fetchone()[0]
    posts = conn.execute("SELECT COUNT(*) FROM tokens").fetchone()[0]
    print(f"catalog.db   {db_path}  ({db_path.stat().st_size / 1e6:.1f} MB)")
    print(f"  products   {skus:,}   families {fams:,}   phonetic keys {phon:,}")
    print(f"  index      {toks:,} distinct tokens, {posts:,} postings (no fts5 — see docstring)")

    print("  family model (brand root):")
    counts = dict(
        conn.execute(
            "SELECT family, COUNT(*) FROM products GROUP BY family "
            f"HAVING family IN ({','.join('?' * len(ANCHORS))})",
            tuple(ANCHORS),
        ).fetchall()
    )
    for family, expected in ANCHORS.items():
        got = counts.get(family, 0)
        flag = "ok " if got == expected else "!! "
        ok = ok and got == expected
        print(f"    {flag}{family:<12} {got:>3} SKUs (expected {expected})")

    singles = conn.execute(
        "SELECT COUNT(*) FROM (SELECT family FROM products GROUP BY family HAVING COUNT(*) = 1)"
    ).fetchone()[0]
    print(f"    one-SKU families: {singles:,} / {fams:,} — fracturing check")

    missing = [
        code
        for code in SCENARIO_CODES
        if conn.execute("SELECT 1 FROM products WHERE code = ?", (code,)).fetchone() is None
    ]
    ok = ok and not missing
    print(
        f"  scenario SKUs: {len(SCENARIO_CODES) - len(missing)}/{len(SCENARIO_CODES)} present"
        + (f"  MISSING {missing}" if missing else "")
    )

    top = conn.execute(
        "SELECT family, COUNT(*) c FROM products GROUP BY family ORDER BY c DESC, family LIMIT 8"
    ).fetchall()
    print("  widest families: " + ", ".join(f"{f} ({c})" for f, c in top))
    return ok


def main() -> int:
    started = time.perf_counter()
    conn = build()
    ok = summarize(conn)
    conn.close()
    print(f"  built in {time.perf_counter() - started:.1f}s")
    if not ok:
        print("BUILD FAILED an acceptance check", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
