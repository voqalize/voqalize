"""Cannon Home: several options of one filter ("beige y blanco"), end to end.

Dev, 2026-10-28: "beige y blanco" filtered by Beige alone — the colour reader
kept the first colour word, the page's fuzzy match took Beige, the result said
``applied``, and the landing check passed on a prefix. Every option named is
now put on, or the ones that were not are said; nothing is ever matched by
prefix. The invented store, the script and the helpers are the e2e suite's.

Run: ``cd demos && uv run pytest tests/test_cannonhome_filters.py``
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from ._harness import check_turn, demo
from .test_cannonhome_e2e import (
    _DONE_MS,
    _IDLE_MS,
    _TALK_THROUGH_MS,
    SHEETS,
    STORE,
    _answer,
    _cues,
    _every,
    _idle_windows,
    _listing,
    _llm,
    _move,
    _moves,
    _page,
    _store,  # noqa: F401 — the autouse fixture: every session reads the invented store
    _texts,
    ch,
)

_SHEETS_CAT = STORE.categories[SHEETS]


def _values(said: str | list[str]) -> tuple[list[str] | None, list[str]]:
    refused: list[str] = []
    return ch._filter_values(_SHEETS_CAT, "color", said, refused), refused


def test_several_options_of_one_filter_are_each_labelled_never_the_first_for_all() -> None:
    assert _values("blanco y gris") == (["Blanco", "Gris"], [])
    assert _values("Gris, blancas") == (["Gris", "Blanco"], [])
    assert _values("white and grey") == (["Blanco", "Gris"], [])
    assert _values("blanco & azul") == (["Blanco", "Azul"], [])
    assert _values("blanco e gris") == (["Blanco", "Gris"], [])
    assert _values(["blanco", "azules"]) == (["Blanco", "Azul"], [])
    # Two colours with no "y" between them are two, not the first.
    assert _values("blanco gris") == (["Blanco", "Gris"], [])
    # Said twice is one option.
    assert _values("blanco y blancas") == (["Blanco"], [])
    # One the listing lacks: refused by name, with what it lists.
    got, refused = _values("blanco y fucsia")
    assert got is None
    assert refused == [
        "color 'fucsia' is not an option of this listing (it lists: Blanco, Gris, Azul)"
    ]
    got, refused = _values("fucsia, morado y blanco")
    assert got is None and "'fucsia' and 'morado' are not options" in refused[0]
    # A size's own "y" and comma are not two options.
    sizes: list[str] = []
    assert ch._filter_values(_SHEETS_CAT, "tamano", "plaza y media", sizes) == ["1.5 Plazas"]
    assert ch._filter_values(_SHEETS_CAT, "tamano", "1,5 plazas", sizes) == ["1.5 Plazas"]
    assert ch._filter_values(_SHEETS_CAT, "tamano", "king o súper king", sizes) == [
        "King",
        "Súper King",
    ]
    assert sizes == []


def test_a_filter_request_takes_a_list_or_a_plain_string() -> None:
    assert ch.FilterRequest(category_path=SHEETS, color="blanco").color == ["blanco"]  # type: ignore[arg-type]
    assert ch.FilterRequest(category_path=SHEETS, color=["a", "b"]).color == ["a", "b"]
    assert ch.FilterRequest(category_path=SHEETS).color is None


@pytest.mark.parametrize(
    "said", ["Muéstrame las blancas y grises.", "Las blancas y las grises, por favor."]
)
async def test_a_filter_cue_takes_several_options(said: str) -> None:
    async with demo("cannonhome", _llm()) as rig:
        await rig.driver.start_session(init={"path": SHEETS})
        await rig.driver.user_says(said)
        (cue,) = _cues(rig)
        assert (cue["move"], cue["args"]) == ("listing.filter", ["color", "Blanco, Gris", SHEETS])


async def test_one_filter_cue_per_option_each_adds_and_the_last_line_names_both() -> None:
    async with demo("cannonhome", _llm()) as rig:
        await rig.driver.start_session(init={"path": SHEETS})
        await rig.driver.user_says("Primero las blancas, después las grises.")
        white, grey = _cues(rig)
        assert white["args"] == ["color", "Blanco", SHEETS]
        assert grey["args"] == ["color", "Gris", SHEETS]
        # The first lands; then the second, with the first kept on.
        await _page(rig, "listing_shown", _listing(5, filters={"color": "Blanco"}, sort=""))
        await _page(rig, "listing_shown", _listing(9, filters={"color": "Blanco, Gris"}, sort=""))
        turn = await rig.driver.user_idle(level=1, idle_ms=_DONE_MS)
        check_turn(rig, turn)
        assert turn.text.startswith("Aquí hay 9 en Blanco y Gris; el primero es Liso Menta")


async def test_a_cue_option_the_listing_lacks_is_never_sent_and_is_said_by_name() -> None:
    llm = _llm()
    async with demo("cannonhome", llm) as rig:
        await rig.driver.start_session(init={"path": SHEETS})
        await rig.driver.user_says("¿Blancas y fucsias?")
        assert not _cues(rig)
        await asyncio.sleep(0.1)
        await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        assert "color 'fucsia' is not an option of this listing" in _texts(llm.captured_inputs[-1])


async def test_filter_listing_sends_every_option_and_lands_only_on_all_of_them() -> None:
    async with demo("cannonhome", _llm()) as rig:
        await rig.driver.start_session(init={"path": SHEETS})
        await rig.driver.user_says("Filtra las blancas y grises.")
        assert _move(rig, "filter_listing")["color"] == ["Blanco", "Gris"]
        # One of the two on screen is not its effect: no line for it.
        await _page(rig, "listing_shown", _listing(5, filters={"color": "Blanco"}, sort=""))
        assert _idle_windows(rig)[-1] == _IDLE_MS
        # Both, in the page's order: its effect, and the line names both.
        await _page(rig, "listing_shown", _listing(9, filters={"color": "Gris, Blanco"}, sort=""))
        assert _idle_windows(rig)[-1] == _DONE_MS
        turn = await rig.driver.user_idle(level=1, idle_ms=_DONE_MS)
        assert turn.text.startswith("Aquí hay 9 en Gris y Blanco; el primero es Liso Menta")


async def test_filter_listing_with_lists_across_filters() -> None:
    async with demo("cannonhome", _llm()) as rig:
        await rig.driver.start_session(init={"path": SHEETS})
        await rig.driver.user_says("Filtra las blancas y azules en king.")
        sent = _move(rig, "filter_listing")
        assert (sent["size"], sent["color"]) == (["King"], ["Blanco", "Azul"])


async def test_filter_listing_with_an_option_the_listing_lacks_sends_nothing() -> None:
    llm = _llm()
    async with demo("cannonhome", llm) as rig:
        await rig.driver.start_session(init={"path": SHEETS})
        await rig.driver.user_says("Filtra las blancas y fucsias.")
        await rig.driver.user_says("Sigamos.")
        refused = _every(llm.captured_inputs[-1], "filter_listing")[-1]
        assert refused == (
            "Not done: color 'fucsia' is not an option of this listing "
            "(it lists: Blanco, Gris, Azul)."
        )
        assert not _moves(rig, "filter_listing")


async def test_a_cue_of_several_options_that_lands_in_part_is_talked_through() -> None:
    llm = _llm()
    async with demo("cannonhome", llm) as rig:
        await rig.driver.start_session(init={"path": SHEETS})
        await rig.driver.user_says("Muéstrame las blancas y grises.")
        await _answer(
            rig,
            "listing.filter",
            "partial",
            "Color Blanco applied; Sábanas: 5 products",
            refused=[{"arg": "value", "why": "Color Gris is not on after choosing it"}],
        )
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        seen = _texts(llm.captured_inputs[-1])
        assert (
            "[On the page, only part of {filter: Color | Blanco, Gris}: Color Blanco applied; "
            "Sábanas: 5 products; not done: Color Gris is not on after choosing it." in seen
        )


def _landing(move: str, **kw: Any) -> ch.Landing:
    return ch.Landing(next(m for m in ch.MOVES if m.id == move), "c1", 0.5, **kw)


def _shown(filters: dict[str, str]) -> ch.ListingShown:
    return ch.ListingShown.model_validate(_listing(9, filters=filters, sort=""))


def _colors(colors: str) -> ch.ListingShown:
    return _shown({"color": colors})


def test_lands_compares_the_options_as_sets_never_as_prefixes() -> None:
    both = _landing("filter_listing", args={"category_path": SHEETS, "color": ["Beige", "Blanco"]})
    assert ch.lands(both, _colors("Blanco, Beige"))
    assert not ch.lands(both, _colors("Beige"))
    assert not ch.lands(both, _colors("Beige, Blanco, Gris"))
    # An older move's plain string is one option.
    one = _landing("filter_listing", args={"category_path": SHEETS, "color": "Beige"})
    assert ch.lands(one, _colors("Beige"))
    assert not ch.lands(one, _colors("Beige, Blanco"))
    # A cue adds: its options on, whatever else stays on; never a prefix.
    cue = _landing("listing.filter", cue_args=("color", "Beige", SHEETS))
    assert ch.lands(cue, _colors("Blanco, Beige"))
    assert not ch.lands(cue, _colors("Blanco"))
    prefix = _landing("listing.filter", cue_args=("color", "Bei", SHEETS))
    assert not ch.lands(prefix, _colors("Beige"))
    two = _landing("listing.filter", cue_args=("color", "Blanco, Beige", SHEETS))
    assert ch.lands(two, _colors("Beige, Blanco"))
    assert not ch.lands(two, _colors("Beige"))
    # "300" is the option "300 hilos".
    threads = _landing("filter_listing", args={"category_path": SHEETS, "threads": ["300"]})
    assert ch.lands(threads, _shown({"hilos": "300 hilos"}))


def test_the_landing_line_names_the_options() -> None:
    e = _colors("Beige, Blanco")
    assert ch.listing_line(e, "en", ["Beige", "Blanco"]).startswith(
        "Here are 9 in Beige and Blanco; the first is Liso Menta at"
    )
    assert ch.listing_line(e, "es", ["Beige", "Blanco", "Gris"]).startswith(
        "Aquí hay 9 en Beige, Blanco y Gris; el primero es Liso Menta, a"
    )
    # A sort names none.
    assert ch.listing_line(e, "en").startswith("Here are 9; the first is")
    empty = ch.ListingShown.model_validate(_listing(0, items=[], filters={"color": "Beige"}))
    assert ch.listing_line(empty, "en", ["Beige"]) == "No products show in Beige."
    # What it names is what the listing has on, in the filters the move asked for.
    asked = _landing("filter_listing", args={"category_path": SHEETS, "color": ["x"]})
    assert ch.landed_options(asked, _shown({"color": "Beige, Blanco", "tamano": "King"})) == [
        "Beige",
        "Blanco",
    ]


def test_the_hold_line_promises_a_check_only_for_a_question() -> None:
    ack = ch.Acknowledger(ch._ACK_LINES, ch._ACK_HOLD, ch._ACK_SORRY)
    for kind in ("request", "statement", None):
        floor = ch._LateFloor(ack, None, 1, 2, kind)
        assert floor.hold("en") == "Just a moment."
        assert floor.hold("es") == "Dame un momento mientras lo busco."
    question = ch._LateFloor(ack, None, 1, 2, "question")
    assert {question.hold("en") for _ in range(20)} <= set(ch._ACK_HOLD["en"])
    # A late nod, when there is one, is the hold line.
    assert ch._LateFloor(ack, "Sure thing.", 1, 2, "request").hold("en") == "Sure thing."


def test_the_prompt_teaches_several_options_of_one_filter() -> None:
    prompt = ch._prompt(STORE, ch.date(2030, 3, 4))
    assert "{filter: Color | Blanco, Beige}" in prompt
    assert "never ask which one first" in prompt
