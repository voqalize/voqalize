"""Javier's cues: the moves a reply may write, as Stage parses them.

The parser is Stage's (``voqalize.sdk.stage``); what is Cannon Home's is which
moves exist, their verbs and classes, and that every cue the prompt teaches
parses into the move it names. The resolving against the site is the brain's,
covered end to end in ``test_cannonhome_e2e.py``.

Run: ``cd demos && uv run pytest tests/test_cannonhome_cues.py``
"""

from __future__ import annotations

from voqalize_demos.discovery import discover

from voqalize.sdk.stage import CueParser, MoveClass, MoveSet, RawCue

discover()

from voqalize_demos._loaded.cannonhome.brain import MOVES  # noqa: E402

VERBS = MoveSet(MOVES).verbs


def _run(*chunks: str) -> tuple[str, list[RawCue]]:
    p = CueParser(VERBS)
    spoken = ""
    cues: list[RawCue] = []
    for c in chunks:
        text, got = p.feed(c)
        spoken += text
        cues += got
    text, got = p.flush()
    return spoken + text, cues + got


def test_the_moves_and_their_classes() -> None:
    by_id = {m.id: m for m in MOVES}
    assert {m.verb: m.cls for m in MOVES if m.verb} == {
        "page": MoveClass.NAVIGATE,
        "show": MoveClass.LOOK,
        "faq": MoveClass.LOOK,
        "filter": MoveClass.REVERSIBLE,
        "sort": MoveClass.REVERSIBLE,
    }
    # What the visitor owns changes only by a tool, after they said yes.
    for move in ("add_to_cart", "update_cart_item", "start_checkout", "fill_checkout"):
        assert by_id[move].cls is MoveClass.CONFIRMED and by_id[move].verb is None
    assert by_id["open_product"].cls is MoveClass.NAVIGATE
    assert by_id["filter_listing"].cls is MoveClass.REVERSIBLE
    assert by_id["check_prices"].cls is MoveClass.LOOK


def test_cues_leave_the_speech_with_their_arguments_and_the_words_after_them() -> None:
    spoken, cues = _run(
        "{page: /12-ropa-de-cama/20-sabanas} Estas son las sábanas. "
        "{filter: Tamaño | King} Primero, las king. {filter: Material|100% Algodón} "
        "Y de algodón."
    )
    assert "{" not in spoken and "}" not in spoken
    assert spoken == " Estas son las sábanas. Primero, las king. Y de algodón."
    assert [(c.verb, c.args) for c in cues] == [
        ("page", ("/12-ropa-de-cama/20-sabanas",)),
        ("filter", ("Tamaño", "King")),
        ("filter", ("Material", "100% Algodón")),
    ]
    # The anchor is the spoken text as written, accents and all: the page
    # segments it as it segments what it hears.
    assert cues[1].at.startswith("Primero, las king.")
    assert cues[2].at == "Y de algodón."


def test_a_cue_split_across_chunks_still_parses() -> None:
    spoken, cues = _run("Las ordeno. {so", "rt: price_", "asc} De la más barata", " a la más cara.")
    assert spoken == "Las ordeno. De la más barata a la más cara."
    assert [(c.verb, c.args) for c in cues] == [("sort", ("price_asc",))]


def test_braces_that_are_no_move_of_his_are_not_spoken() -> None:
    spoken, cues = _run("Hola {mood: happy} {cart: open} aquí.")
    assert spoken == "Hola aquí." and cues == []
