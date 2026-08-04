"""The OrderDesk catalog core, against the real 20,148-SKU sqlite database.

No LLM, no network, no fixtures-of-convenience: these tests drive the shipping
``demos/orderdesk/backend/search.py`` over the shipping ``catalog.db`` and assert
on **real SKU codes** — the same ones the scenarios in
``frontend/src/data.ts`` name. That is deliberate. This search *is* the demo's
credibility: if "volini" stops being a ten-SKU choice or "telma 40" stops
landing on J0031270, the call falls apart on stage, and it should fall apart in
CI first.

The backend is loaded from source (like ``voqalize_demos.discovery`` does for
brains) rather than imported as a package, so this file does not depend on the
brain half of the demo existing yet.
"""

from __future__ import annotations

import importlib
import importlib.util
import re
import sys
import time
from pathlib import Path
from types import ModuleType

BACKEND = Path(__file__).resolve().parents[1] / "orderdesk" / "backend"
TYPES_TS = Path(__file__).resolve().parents[1] / "orderdesk" / "frontend" / "src" / "types.ts"
_PKG = "orderdesk_backend"


def _load_backend() -> ModuleType:
    """Import ``demos/orderdesk/backend/`` as a package, in place."""
    if _PKG not in sys.modules:
        pkg = ModuleType(_PKG)
        pkg.__path__ = [str(BACKEND)]  # type: ignore[attr-defined]
        sys.modules[_PKG] = pkg
    if not (BACKEND / "catalog.db").exists():  # pragma: no cover — first run
        importlib.import_module(f"{_PKG}.build_catalog").build().close()
    return importlib.import_module(f"{_PKG}.search")


search_mod = _load_backend()
normalize = importlib.import_module(f"{_PKG}.normalize")

resolve = search_mod.resolve
search = search_mod.search
sku_by_code = search_mod.sku_by_code
skus_in_family = search_mod.skus_in_family

#: The SKUs the Day-1 happy path depends on: spoken query → the row it must hit.
DAY_ONE = {
    "telma 40": ("J0031270", "TELMA 40 TABLET"),
    "shelcal 500": ("J0029359", "SHELCAL-500 TABLET"),
    "pan 40": ("J0024991", "PAN 40 TABLET"),
    "dolo 650": ("J0010291", "DOLO-650 TABLET"),
    "augmentin 625 duo": ("J0004502", "AUGMENTIN 625 DUO TABLET"),
    "glycomet 500": ("J0014899", "GLYCOMET 500 MG TABLET"),
    "thyronorm 50": ("J0038288", "THYRONORM 50 MCG TABLET"),
    "crocin 650": ("J0042294", "CROCIN 650 TABLET"),
    "pan mps syrup": ("J0050820", "PAN MPS SYRUP"),
}


# ─── the family model ─────────────────────────────────────────────────────────


def test_family_is_the_brand_root_not_the_name():
    """Naive "name minus form" fractures TELMA into 24 one-SKU families; the
    brand-root model keeps each brand whole. These counts are the acceptance
    check on the whole parsing model."""
    assert len(skus_in_family("TELMA")) == 26
    assert len(skus_in_family("VOLINI")) == 10
    assert len(skus_in_family("4 QUIN")) == 6
    assert len(skus_in_family("THYRONORM")) == 8
    assert len(skus_in_family("AUGMENTIN")) == 6
    # Multi-word roots survive as one family, and lookup is case-insensitive.
    assert [s.code for s in skus_in_family("4 quin")] == [s.code for s in skus_in_family("4 QUIN")]


def test_scenario_skus_exist_by_code():
    """``data.ts`` quotes real Product_Codes in every order history."""
    for query, (code, name) in DAY_ONE.items():
        sku = sku_by_code(code)
        assert sku is not None, f"{code} ({query}) vanished from the catalog"
        assert sku.name == name
        assert sku.ptr > 0 and sku.mrp >= sku.ptr
    assert sku_by_code("NOT-A-CODE") is None
    assert sku_by_code("j0031270") is not None  # spoken/typed case is irrelevant


# ─── the Day-1 happy path ─────────────────────────────────────────────────────


def test_day_one_queries_land_on_one_sku():
    for query, (code, name) in DAY_ONE.items():
        res = resolve(query)
        assert res.status == "matched", f"{query!r} → {res.status} (expected matched)"
        assert res.sku is not None
        assert res.sku.code == code, f"{query!r} → {res.sku.name}, expected {name}"
        assert res.family == res.sku.family
        assert res.variants == [] and res.families == []
        assert res.confidence >= 0.9


# ─── ambiguity: the minimal-question engine ───────────────────────────────────


def test_volini_is_a_multi_variant_family():
    res = resolve("volini")
    assert res.status == "multi_variant"
    assert res.family == "VOLINI"
    assert 2 <= len(res.variants) <= 8  # the pill row is capped
    assert all(v.family == "VOLINI" for v in res.variants)
    # The question to ask is about what actually differs — never strength here,
    # because no VOLINI SKU carries one.
    assert "variant_label" in res.differing_axes
    assert "form" in res.differing_axes
    assert "strength" not in res.differing_axes
    assert set(res.differing_axes) <= set(search_mod.AXES)
    forms = {v.form for v in res.variants}
    assert {"GEL", "SPRAY"} <= forms


def test_four_quin_surfaces_the_drops_ointment_family():
    res = resolve("4 quin")
    assert res.status == "multi_variant"
    assert res.family == "4 QUIN"
    assert len(res.variants) == 6
    assert {v.form for v in res.variants} == {"EYE DROPS", "EYE OINTMENT"}
    # KT / LOT / BROM / D are the suffix lines a pharmacist distinguishes by.
    assert {"KT", "LOT", "BROM", "D"} <= {v.variant_label for v in res.variants}
    assert {v.manufacturer for v in res.variants} == {"ENTOD"}
    # The demo's key beat: the agent asks "drops or ointment?" — never "KT or
    # LOT?" and never about pack size. The brain reads differing_axes[0].
    assert res.differing_axes[0] == "form"
    assert res.differing_axes == ["form", "variant_label", "pack_size"]
    # The plain line leads the pill row; the suffix lines follow.
    assert res.variants[0].variant_label == ""


def test_axes_are_reported_in_question_priority():
    """Voice can ask "drops or ointment?" and "40 or 80?" crisply. It cannot ask
    "10s or 15s?" — that is what the pill row is for. So the order is fixed."""
    assert search_mod.AXES == ("form", "strength", "variant_label", "pack_size")
    mixed = [
        search_mod.SkuView(*args)
        for args in (
            ("A", "A", "F", "", "GEL", "10", "10 GM", 1.0, 1.0, 1, "M", ""),
            ("B", "B", "F", "X", "SPRAY", "20", "20 GM", 1.0, 1.0, 1, "M", ""),
        )
    ]
    assert search_mod.differing_axes(mixed) == list(search_mod.AXES)
    assert search_mod.differing_axes(mixed[:1]) == []


def test_thyronorm_asks_about_strength():
    res = resolve("thyronorm")
    assert res.status == "multi_variant"
    assert res.family == "THYRONORM"
    assert "strength" in res.differing_axes
    assert "form" not in res.differing_axes  # every THYRONORM SKU is a tablet
    assert len({v.strength for v in res.variants}) == len(res.variants)


def test_telma_40_is_decided_by_the_name_not_by_the_family():
    """TELMA is 26 SKUs and eight of them carry a 40; the whole-name prefix has
    to beat every partial match, or the happy path becomes a question."""
    res = resolve("telma 40")
    assert res.status == "matched"
    assert res.sku is not None and res.sku.code == "J0031270"
    bare = resolve("telma")
    assert bare.status == "multi_variant" and bare.family == "TELMA"


# ─── hints ────────────────────────────────────────────────────────────────────


def test_form_hint_narrows_to_one_sku():
    res = resolve("4 quin", form_hint="ointment")
    assert res.status == "matched"
    assert res.sku is not None and res.sku.code == "J0037800"
    assert res.sku.form == "EYE OINTMENT"


def test_form_hint_narrows_the_axis_away():
    res = resolve("4 quin", form_hint="drops")
    assert res.status == "multi_variant"
    assert all(v.form == "EYE DROPS" for v in res.variants)
    assert "form" not in res.differing_axes  # nothing left to ask about there
    assert "variant_label" in res.differing_axes


def test_strength_hint_narrows_to_one_sku():
    res = resolve("thyronorm", strength_hint="50 mcg")
    assert res.status == "matched"
    assert res.sku is not None and res.sku.code == "J0038288"


def test_a_hint_that_matches_nothing_is_ignored():
    """A wrong hint must never turn a good hit into ``not_found``."""
    res = resolve("volini gel", form_hint="tablet")
    assert res.status == "multi_variant"
    assert {v.code for v in res.variants} == {"J0034534", "J0034539"}


# ─── pack size ────────────────────────────────────────────────────────────────


def test_pack_size_is_the_only_question_for_volini_gel():
    res = resolve("volini gel")
    assert res.status == "multi_variant"
    assert res.differing_axes == ["pack_size"]
    assert {v.code for v in res.variants} == {"J0034534", "J0034539"}
    assert {v.pack_size for v in res.variants} == {"100 GM", "75 GM"}


def test_spoken_pack_size_picks_the_sku():
    """The pack size lives in its own column, in no product name — resolving it
    is the scorer's job, not the index's."""
    assert resolve("volini gel 100 gm").sku.code == "J0034534"
    assert resolve("volini gel 75 gm").sku.code == "J0034539"
    assert resolve("volini gel 75").sku.code == "J0034539"


# ─── phonetics: the misheard brand ────────────────────────────────────────────


def test_phonetic_key_folds_transliteration_artifacts():
    key = normalize.phonetic_key
    assert key("VOLINI") == key("WOLINY") == key("VOLEENI")
    assert key("SHELCAL") == key("SHELKAL")
    assert key("THYRONORM") == key("THAIRONORM")
    assert key("GLYCOMET") == key("GLAIKOMET")
    # The confusable MANKIND pair the ambiguity-day scenario is built on: near,
    # but not equal — close enough to reach each other, far enough to rank.
    assert key("ABEVIA") != key("ABIWAYS")
    assert normalize.phonetic_bucket(key("ABEVIA")) == normalize.phonetic_bucket(key("ABEVIYA"))
    assert key("ABIWAYS").startswith(key("ABEVIA"))


def test_alternate_keys_carry_the_confusions_the_key_refuses_to_fold():
    """B/V, soft C/G and the epenthetic vowel of "isporlac" are real confusions
    that would wreck the key if folded into it (ABEVIA's ``ABV`` would become a
    two-letter ``AV``). They live as *alternate* keys instead — and the index
    and the query get them from the same function, so they cannot disagree."""
    keys = normalize.phonetic_keys
    assert keys("VOLINI") == ["VLN"]  # nothing confusable — one key
    assert keys("bolini") == ["BLN", "VLN"]  # …the same alternate both sides
    assert keys("BECOSULES")[1] == keys("vecosules")[0] == keys("wekosuls")[0]
    assert keys("OMNIGEL")[1] == keys("omnijel")[0]  # G goes soft before E
    assert keys("PLACENTREX")[1] == keys("plasenatrex")[0]  # …and so does C
    assert keys("isporlac") == ["ASPRLK", "SPRLK"]  # propped-up s-cluster
    assert normalize.phonetic_key("bevhon") == normalize.phonetic_key("BEVON")

    # The yardstick behind an alternate: alike in the folded alphabet, or not.
    shape = normalize.spoken_shape
    assert shape("bolini") == shape("VOLINI") == "VOLINI"
    assert shape("abivays") != shape("AVAS")


def test_a_fused_form_word_still_finds_the_brand():
    """Fast speech glues the form word on ("volnijel", "beplexfort"), and the
    fused key overruns the family's by too much for any prefix to bridge."""
    assert normalize.fused_stem("VOLNIJEL") == "VOLNI"
    assert normalize.fused_stem("BEPLEXFORTE") == "BEPLEX"
    assert normalize.fused_stem("VOLINI") == ""  # no form word glued on
    assert resolve("volnijel").family == "VOLINI"
    assert resolve("beplexfort").family == "BEPLEX"
    # A brand that genuinely ends in a form word is untouched: the fused token
    # is still probed, the stem is only an extra probe.
    assert resolve("omnigel").family == "OMNIGEL"


def test_the_b_v_brands_survive_the_phone_line():
    """व is written B as often as V/W once it has been through a phone line —
    the whole `vw-vowels-clusters` corpus bucket is this one confusion."""
    for query, family in (
        ("bolini", "VOLINI"),
        ("bertin", "VERTIN"),
        ("vecosules", "BECOSULES"),
        ("boberan", "VOVERAN"),
        ("isporlac", "SPORLAC"),
        ("moovh", "MOOV"),
    ):
        res = resolve(query)
        surfaced = {f.family for f in res.families} | ({res.family} if res.family else set())
        assert family in surfaced, f"{query!r} → {res.status} {surfaced}"


def test_misspelled_brand_is_recovered():
    for query in ("woliny", "voleeni", "wolini"):
        res = resolve(query)
        assert res.status == "multi_variant", f"{query!r} → {res.status}"
        assert res.family == "VOLINI", f"{query!r} → {res.family}"
    assert resolve("shelkal").family == "SHELCAL"
    assert resolve("glaikomet 500").sku.code == "J0014899"


def test_phonetic_recovery_still_honours_the_rest_of_the_query():
    res = resolve("woliny spray")
    assert res.status == "multi_variant"
    assert res.family == "VOLINI"
    assert all(v.form == "SPRAY" for v in res.variants)
    assert "form" not in res.differing_axes


def test_the_confusable_pair_stays_apart():
    """ABEVIA and ABIWAYS are two different MANKIND brands that sound alike on a
    phone line. Each spelling must reach its own brand — the agent asks *which*
    only because the scenario tells it to, never because search guessed."""
    abevia = resolve("abeviya")
    assert abevia.status in {"matched", "multi_variant"}
    assert abevia.family == "ABEVIA"
    assert {v.code for v in abevia.variants} == {"PROD5666", "PROD3323"}

    abiways = resolve("abivays")
    assert abiways.family == "ABIWAYS"
    assert {v.code for v in abiways.variants} == {"J0002149", "J0038036", "J0050079"}


# ─── spoken numbers ───────────────────────────────────────────────────────────


def test_numbers_spoken_as_words_resolve_too():
    """The brain transliterates Hindi: "डोलो सिक्स फिफ्टी" can arrive either way."""
    assert normalize.spoken_numbers("dolo six fifty") == "DOLO 650"
    assert normalize.spoken_numbers("shelcal five hundred") == "SHELCAL 500"
    assert resolve("dolo six fifty").sku.code == "J0010291"
    assert resolve("telma forty").sku.code == "J0031270"
    assert resolve("four quin eye drops").sku.code == "J0002080"
    # …and the digits still win when the words were the real spelling.
    assert resolve("shelcal 500").sku.code == "J0029359"


# ─── nothing there ────────────────────────────────────────────────────────────


def test_absent_brand_is_not_found():
    """COLDACT is a real brand this distributor does not carry — the Day-3
    scenario leans on it resolving to nothing rather than to a lookalike."""
    assert resolve("coldact").status == "not_found"
    assert resolve("zylotron").status == "not_found"
    for garbage in ("", "   ", "!!!", "..."):
        res = resolve(garbage)
        assert res.status == "not_found"
        assert res.sku is None and res.variants == [] and res.confidence == 0.0


# ─── grouping across families ─────────────────────────────────────────────────


def test_multi_family_carries_readable_option_cards():
    res = resolve("thairo norm")  # one brand heard as two words
    assert res.status == "multi_family"
    assert 2 <= len(res.families) <= 5
    assert res.families[0].family == "THYRONORM"
    assert res.sku is None and res.variants == []
    for fam in res.families:
        assert fam.sku_count >= 1
        assert fam.hint and "·" in fam.hint
        assert fam.manufacturers and fam.forms
    assert "8 SKUs" in res.families[0].hint


# ─── the manual search bar ────────────────────────────────────────────────────


def test_search_is_ranked_and_bounded():
    hits = search("volini gel")
    assert [s.code for s in hits[:2]] == ["J0034539", "J0034534"]
    assert all(s.family == "VOLINI" for s in hits)

    telma = search("telma", limit=5)
    assert len(telma) == 5
    assert all(s.family == "TELMA" for s in telma)
    assert "J0031270" in {s.code for s in telma}

    lotion = search("cetaphil lotion")
    assert lotion and all("LOTION" in s.name for s in lotion)
    assert all(s.family == "CETAPHIL" for s in lotion)

    assert search("shelcal 500")[0].code == "J0029359"
    assert search("zylotron") == []
    assert search("") == []


# ─── the wire contract ────────────────────────────────────────────────────────


def _ts_interface_fields(name: str) -> list[str]:
    body = re.search(
        rf"export interface {name} \{{(.*?)\n\}}", TYPES_TS.read_text(encoding="utf-8"), re.S
    )
    assert body, f"{name} is gone from types.ts"
    return re.findall(r"^\s{2}(\w+)\??:", body.group(1), re.M)


def test_wire_dicts_match_types_ts():
    """``SkuWire``/``FamilyWire`` are declared once, in TypeScript. The Python
    side is checked against that declaration rather than against a copy of it."""
    sku = sku_by_code("J0031270")
    assert sku is not None
    assert list(sku.wire()) == _ts_interface_fields("SkuWire")
    assert sku.wire() == {
        "code": "J0031270",
        "name": "TELMA 40 TABLET",
        "family": "TELMA",
        "variant_label": "",
        "form": "TABLET",
        "strength": "40",
        "pack_size": "15'S",
        "mrp": sku.mrp,
        "ptr": sku.ptr,
        "stock": sku.stock,
        "manufacturer": "GLENMARK",
        "scheme": "",
    }

    family = resolve("thairo norm").families[0]
    assert list(family.wire()) == _ts_interface_fields("FamilyWire")
    assert family.wire()["family"] == "THYRONORM"
    assert isinstance(family.wire()["forms"], list)


def test_wire_values_are_json_primitives():
    for sku in skus_in_family("VOLINI"):
        wire = sku.wire()
        assert isinstance(wire["mrp"], float) and isinstance(wire["ptr"], float)
        assert isinstance(wire["stock"], int)
        assert all(isinstance(wire[k], str) for k in ("code", "name", "family", "pack_size"))
        assert "\xa0" not in wire["name"] and not wire["name"].endswith(sku.code)


# ─── the invariant the brain codes against ────────────────────────────────────

PROBES = [
    "volini",
    "woliny spray",
    "volini gel",
    "volini gel 100 gm",
    "4 quin",
    "telma 40",
    "telma",
    "shelcal",
    "shelcal 500",
    "shelkal five hundred",
    "pan 40",
    "pan d",
    "dolo 650",
    "augmentin 625 duo",
    "glycomet 500",
    "thyronorm",
    "thyronorm 50",
    "abeviya",
    "abivays",
    "coldact",
    "crocin 650",
    "candid cream",
    "cetaphil lotion",
    "itch guard plus cream",
]


def test_every_resolution_is_internally_consistent():
    for query in PROBES:
        res = resolve(query)
        assert res.status in {"matched", "multi_variant", "multi_family", "not_found"}
        assert 0.0 <= res.confidence <= 1.0
        if res.status == "matched":
            assert res.sku is not None and res.family == res.sku.family
            assert not res.variants and not res.families and not res.differing_axes
        elif res.status == "multi_variant":
            assert res.family and len(res.variants) > 1
            assert len({v.code for v in res.variants}) == len(res.variants)
            assert all(v.family == res.family for v in res.variants)
            assert res.differing_axes and set(res.differing_axes) <= set(search_mod.AXES)
            for axis in res.differing_axes:
                assert len({getattr(v, axis) for v in res.variants}) > 1
        elif res.status == "multi_family":
            assert 2 <= len(res.families) <= 5
            assert len({f.family for f in res.families}) == len(res.families)
            assert res.sku is None and not res.variants
        else:
            assert res.sku is None and not res.variants and not res.families


def test_the_catalog_needs_no_fts5():
    """The uv-managed CPython that runs this demo (and the Docker image) links a
    sqlite with **no fts5 module**: a virtual table there raises "no such module"
    the moment it is touched, which would kill prefix queries — the search bar
    working for whole words and dying mid-typing. The index is plain sqlite, and
    this test is the guard against anyone reintroducing the dependency."""
    conn = search_mod.connection()
    kinds = dict(conn.execute("SELECT name, type FROM sqlite_master WHERE type='table'"))
    assert "products_fts" not in kinds
    assert not [n for n in kinds if n.startswith(("products_fts", "fts"))]
    assert conn.execute("SELECT COUNT(*) FROM tokens").fetchone()[0] > 60_000

    for partial in ("cold", "thyro", "volin", "aug", "4 qu", "cetaph"):
        assert search(partial), f"{partial!r} found nothing mid-typing"
    assert all("THYRO" in s.name for s in search("thyro"))


def test_the_build_is_reproducible_on_this_interpreter(tmp_path):
    """``build_catalog.py`` has to run wherever the demo runs — it is the only
    way to regenerate the shipped .db."""
    build_catalog = importlib.import_module(f"{_PKG}.build_catalog")
    conn = build_catalog.build(db_path=tmp_path / "catalog.db")
    try:
        assert build_catalog.summarize(conn, tmp_path / "catalog.db")  # anchors + scenarios
        fresh = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    finally:
        conn.close()
    assert fresh == search_mod.connection().execute("SELECT COUNT(*) FROM products").fetchone()[0]


def test_resolve_is_fast_when_warm():
    resolve("warm the connection")
    started = time.perf_counter()
    for query in PROBES:
        resolve(query)
    average_ms = (time.perf_counter() - started) / len(PROBES) * 1000
    assert average_ms < 50, f"resolve() averaged {average_ms:.1f} ms — the call cannot wait"
