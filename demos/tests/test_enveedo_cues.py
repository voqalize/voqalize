"""The cue parser: cues out of the speech, each anchored to its sentence.

Run: ``cd demos && uv run pytest tests/test_enveedo_cues.py``
"""

from __future__ import annotations

import json

from voqalize_demos.discovery import discover

discover()

from voqalize_demos._loaded.enveedo import brain as ev  # noqa: E402
from voqalize_demos._loaded.enveedo import knowledge as kb  # noqa: E402
from voqalize_demos._loaded.enveedo.cues import (  # noqa: E402
    MAX_CUE,
    CueParser,
    RawCue,
    words,
)

PLATFORM = "/enveedo_platform"
MODULE_CARDS = (
    "mod_crown_jewel",
    "mod_risk_register",
    "mod_compliance",
    "mod_vendor_risk",
    "mod_incident_response",
    "mod_roadmap",
)


def _run(*chunks: str) -> tuple[str, list[RawCue]]:
    p = CueParser()
    spoken = ""
    cues: list[RawCue] = []
    for c in chunks:
        text, got = p.feed(c)
        spoken += text
        cues += got
    text, got = p.flush()
    return spoken + text, cues + got


def test_cues_leave_the_speech_and_anchor_to_their_sentence() -> None:
    spoken, cues = _run(
        "{page: /}{show: how_it_works} La plataforma parte por tu negocio. "
        "{show: how_integration} Después conecta tus herramientas."
    )
    assert "{" not in spoken and "}" not in spoken
    assert spoken == " La plataforma parte por tu negocio. Después conecta tus herramientas."
    assert [(c.kind, c.value, c.at, c.word) for c in cues] == [
        ("page", "/", "la plataforma parte", 0),
        ("show", "how_it_works", "la plataforma parte", 0),
        ("show", "how_integration", "despues conecta tus", 6),
    ]


def test_a_cue_split_across_chunks_still_parses() -> None:
    spoken, cues = _run("NIS2 está en la lista. {sh", "ow: fw_ni", "s2} Aquí está su tarj", "eta.")
    assert spoken == "NIS2 está en la lista. Aquí está su tarjeta."
    assert [(c.kind, c.value, c.at) for c in cues] == [("show", "fw_nis2", "aqui esta su")]


def test_a_cue_at_the_end_fires_when_the_voice_stops() -> None:
    spoken, cues = _run("Here is the footer. {show: footer}")
    assert spoken.strip() == "Here is the footer."
    assert [(c.kind, c.at) for c in cues] == [("show", "")]


def test_a_version_number_or_a_law_number_is_not_a_sentence_end() -> None:
    spoken, cues = _run("NIST CSF v2.0 and law 21.719 are listed. {show: fw_nist_csf} Look.")
    assert spoken == "NIST CSF v2.0 and law 21.719 are listed. Look."
    assert [(c.value, c.at) for c in cues] == [("fw_nist_csf", "look")]


def test_braces_that_are_not_cues_are_not_spoken_and_a_stray_one_is_dropped() -> None:
    spoken, cues = _run("Hola {mood: happy} a todas.")
    assert spoken == "Hola a todas." and cues == []
    long = "palabra " * (MAX_CUE // 4)
    spoken, cues = _run("Abre { " + long, "y sigue.")
    assert "{" not in spoken and spoken.startswith("Abre ") and cues == []


def test_each_sentence_is_offered_for_the_moves_it_did_not_bring() -> None:
    seen: list[tuple[str, int, tuple[tuple[str, str], ...]]] = []

    def auto(
        sentence: str, index: int, placed: tuple[tuple[str, str], ...]
    ) -> list[tuple[str, str]]:
        seen.append((sentence, index, placed))
        return [("show", "control_performance")] if "Control Performance" in sentence else []

    p = CueParser(auto)  # type: ignore[arg-type]
    cues: list[RawCue] = []
    for chunk in (
        "{page: /security-performance-os} Hello. Then comes Control",
        " Performance. Shall I go on?",
    ):
        cues += p.feed(chunk)[1]
    cues += p.flush()[1]
    assert seen == [
        ("Hello.", 0, (("page", "/security-performance-os"),)),
        ("Then comes Control Performance.", 1, ()),
        ("Shall I go on?", 2, ()),
    ]
    assert [(c.kind, c.value, c.at, c.word) for c in cues] == [
        ("page", "/security-performance-os", "hello", 0),
        ("show", "control_performance", "then comes control", 1),
    ]


def test_anchors_fold_accents_as_the_page_does() -> None:
    assert words("Está en Miami, ¿sí?") == ["esta", "en", "miami", "si"]
    spoken, cues = _run("{show: faq_start} Cómo empezar está aquí.")
    assert spoken == " Cómo empezar está aquí."
    assert [(c.kind, c.value, c.at) for c in cues] == [("show", "faq_start", "como empezar esta")]


# ─── Card grids, against the real catalogue ───────────────────────────────────


def _example(prompt: str, start: str) -> str:
    """The prompt's example reply that starts with ``start``, as he would say it."""
    at = prompt.index(start)
    return prompt[at : prompt.index('"\n', at)]


def test_the_prompt_s_modules_walkthrough_cues_each_card_on_both_languages_pages() -> None:
    k = kb.load()
    prompt = ev._prompt(k)
    assert "A question about one card, such as one module, starts with that card's cue." in prompt
    _, cues = _run(_example(prompt, "{page: /enveedo_platform}{show: modules}"))
    shown = [c.value for c in cues if c.kind == "show"]
    assert shown == ["modules", *MODULE_CARDS]
    # Each sentence of the walkthrough carries its own card.
    assert len({c.at for c in cues if c.kind == "show"}) == len(shown)
    for path in (PLATFORM, "/es/enveedo_platform"):
        offered = {a.key for a in k.anchors_on(path) if not a.hidden}
        assert set(shown) <= offered, (path, set(shown) - offered)


def test_the_modules_place_is_the_whole_section_and_each_card_its_own() -> None:
    catalogue = json.loads((kb.ROOT / "L3" / "anchors.json").read_text(encoding="utf-8"))
    for path in (PLATFORM, "/es/enveedo_platform"):
        rows = {a["key"]: a for a in catalogue["pages"][path]["anchors"]}
        assert rows["modules"]["selector"].startswith("#main-content .dnd-section:has(")
        cards = [rows[key]["selector"] for key in MODULE_CARDS]
        assert len(set(cards)) == 6
        assert all(".cyber-card:nth-child(" in c for c in cards), cards


def test_a_sentence_about_one_module_finds_its_card() -> None:
    page = kb.load().page(PLATFORM)
    assert page is not None
    sections = [(s.key, s.heading, s.text) for s in page.sections]
    for sentence, key in (
        ("Crown Jewel Analysis finds what matters most.", "mod_crown_jewel"),
        ("Risk Register brings every risk into one place.", "mod_risk_register"),
        ("Vendor Risk Management scores your suppliers.", "mod_vendor_risk"),
        ("Incident Response Manager runs your response plans.", "mod_incident_response"),
        ("Evidence collection gathers compliance evidence automatically.", "auto_evidence"),
    ):
        assert ev.best_section(sentence, sections) == key, sentence


def test_every_page_s_card_grids_have_a_key_per_card_in_both_languages() -> None:
    catalogue = kb.load().anchors
    grids = {
        "/": ("impact_risk_assessment", "impact_efficiency", "impact_focus", "testimonial_cto"),
        PLATFORM: (*MODULE_CARDS, "int_api", "auto_evidence", "dash_vendor"),
        "/security-performance-os": ("stall_fragmentation", "stall_audits", "result_sustained"),
        "/partners": ("partner_vciso", "benefit_multitenancy", "benefit_api"),
        "/book-a-demo": ("start_risk_assessment", "start_concierge"),
        "/about-us": ("principle_build_to_win", "principle_honesty"),
        "/cyber-insurance": ("mitigate_risk", "decrease_premium", "feature_cja"),
        "/trust-center": ("ctrl_grc", "ctrl_it_change"),
    }
    for en, keys in grids.items():
        es = "/es/" if en == "/" else "/es" + en
        for path in (en, es):
            have = {a.key for a in catalogue[path]}
            assert set(keys) <= have, (path, set(keys) - have)
