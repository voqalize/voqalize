"""The OrderDesk demo, end to end over the wire — no network, no LLM key.

The real ``OrderDeskBrain`` — the shipping ``demos/orderdesk/backend/brain.py``,
its real prompt, its real tools — hosted on a real ``brain_server`` socket
and driven by the conformance ``VoqalizeDriver``, with only the *model* scripted.
See ``tests/_harness.py`` for what every demo's e2e proves.

OrderDesk is the demo where the English-clip-under-Hindi-speech bug actually
shipped, so its voice-pair check matters more than most (see ``test_
demo_voice_contract.py``). It is also the one demo whose tools resolve against a
**real** catalog (``backend/catalog.db``, via ``backend/search.py``) rather than
handing back whatever the script says — ``add_items`` here really looks
"telma 40" up and really locks it to one SKU, so the assertions below are pinned
to a query ``tests/test_orderdesk_search.py`` already proves is deterministic.

Run: ``cd demos && uv run pytest tests/test_orderdesk_e2e.py``
"""

from __future__ import annotations

from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, call, reply, reply_and_call

from voqalize.sdk.gemini import _needs_result_now

from ._harness import check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.orderdesk.brain import (  # noqa: E402
    _FALLBACK_OPENER,
    _HELLO,
    _LINES,
    OrderDesk,
    RemoveItems,
)

VOICE = "omnivoice/gauri"
LANGUAGE = "hi"

# One `row_added` payload, exactly as the browser sends it when the pharmacist
# picks a medicine out of the search panel himself: the browser mints the `m*` id
# and the desk has never seen the row, which is what makes it an edit the model
# must be told about.
_MANUAL_ROW = {
    "item_id": "m1",
    "sku_code": "J0029363",
    "sku_name": "SHELCAL HD TABLET",
    "query": "shelcal",
    "quantity": 5,
}


def _llm() -> ScriptedGemini:
    return ScriptedGemini(
        {
            # `add_items` is marked `@needs_result_now`: whether the row matched is
            # something only the catalog knows, so the model is asked again with the
            # result and says it in the same turn.
            "Telma 40 ki do strip de do.": [
                reply_and_call(
                    "Theek hai.",
                    "add_items",
                    items=[{"text": "telma 40", "quantity": 2}],
                ),
                reply("Telma 40 jud gaya, do strip."),
            ],
            # `remove_items` is not: the model already knows what it asked for, so the
            # whole line goes with the call and the turn ends with the stream.
            "Ab Telma hata do.": reply_and_call(
                "Telma hata diya.", "remove_items", item_ids=["li1"]
            ),
            "Screen par kya hai?": reply("Aapke screen par Telma 40mg hai."),
        }
    )


async def test_greeting_and_voice_reach_the_wire() -> None:
    """OrderDesk opens with a fixed Hindi hello plus fallback line — no model call
    on the start path — and its declared female Hindi voice lands on **both**
    legs before that audio. This is the exact pair that shipped mismatched in
    production once; the demo's whole reason for a dedicated e2e."""
    async with demo("orderdesk", _llm()) as rig:
        greeting = await rig.driver.start_session()
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text == f"{_HELLO} {_FALLBACK_OPENER}"
        check_voice_pair(rig, voice=VOICE, language=LANGUAGE)


async def test_adding_and_removing_an_item_drive_the_screen() -> None:
    """One tool round-trip resolves a spoken product against the real catalog and
    locks it to a SKU, and the screen hears about it twice: ``row_opened`` the
    instant he says it, greyed, then ``row_matched`` when the catalog answers. Two
    actions, not one row pushed twice — the second carries the SKU and nothing
    else. A second turn then removes it by the id the first turn minted.

    The two turns are the two shapes of the loop. Adding speaks twice — the short
    line with the call, then what the catalog answered. Removing speaks once, the
    line said with the call, because nothing it returns changes what he hears."""
    async with demo("orderdesk", _llm()) as rig:
        await rig.driver.start_session()

        t1 = await rig.driver.user_says("Telma 40 ki do strip de do.")
        check_turn(rig, t1, units=2)

        opened = rig.command("row_opened")
        assert opened["spoken_text"] == "telma 40"
        assert opened["quantity"] == 2

        matched = rig.command("row_matched")
        assert matched["id"] == opened["id"]
        assert matched["sku"]["code"] == "J0031270"
        assert "quantity" not in matched, "the match is carrying the whole row again"

        t2 = await rig.driver.user_says("Ab Telma hata do.")
        check_turn(rig, t2, units=1)

        removed = rig.command("remove_items")
        assert removed["ids"] == [opened["id"]]


async def test_a_manual_edit_is_announced_but_never_dumped() -> None:
    """A desk event is the one client message that must not speak — and, since the
    screen moved out of the context, the one that must not describe either.

    A production call put twenty-one full carts in front of the model in 113
    seconds, each labelled authoritative and none of them dated, and the model
    reasoned from whichever it noticed. So the event lands in the desk and stops:
    the context gets one line naming the row he touched and what it now says, with
    nothing about any other row in it. Both halves are asserted — a note carrying the
    row's SKU *code* would be the old dump again, one line at a time.

    It also does not send the model to ``read_screen``. It used to, in its own footer,
    and that cost a hop to be told what the line had just said."""
    llm = _llm()
    async with demo("orderdesk", llm) as rig:
        await rig.driver.start_session()
        before = len(rig.driver.ui_commands)

        await rig.driver.send_ui_event("row_added", _MANUAL_ROW)
        # The floor is untaken: no speech, no screen command. Frames on one
        # connection are ordered, so the event is already applied by the time the
        # next turn is served — which is what the assertion below proves.
        turn = await rig.driver.user_says("Screen par kya hai?")
        check_turn(rig, turn, units=1)
        assert len(rig.driver.ui_commands) == before, "a desk event drove the screen"

    grounded = "".join(
        p.text or "" for c in llm.captured_contents[-1] for p in (c.parts or []) if c.role == "user"
    )
    assert "m1" in grounded and "added by hand" in grounded
    assert "read_screen" not in grounded, "the note is spending a hop on what it just said"
    assert "J0029363" not in grounded, "the change note is carrying the row"
    assert "CURRENT ORDER SCREEN" not in grounded, "the screen dump is back"


async def test_a_row_he_took_away_answers_with_the_rows_that_are_left() -> None:
    """What stands where the version gate stood.

    The gate refused *every* tool after *any* hand edit, so a model that had just been
    told "li1 removed by hand" still paid a hop to read that back. It was standing in
    for one real hazard: a name the model heard, translated into an id it remembered,
    aimed at a row that is no longer the medicine it was.

    The tool signatures already retire that hazard. Every row tool resolves its
    reference here, against the cart as it stands — so the translation the model could
    get wrong is one it never performs, and a reference that no longer names a row
    comes back saying which rows there are. That is a better answer than a refusal: it
    names the way forward instead of only naming the problem, and it costs the model
    nothing on the far more common turn where he has changed nothing at all."""
    llm = ScriptedGemini(
        {
            "Telma 40 ki do strip de do.": [
                reply_and_call(
                    "Theek hai.",
                    "add_items",
                    items=[{"text": "telma 40", "quantity": 2}],
                ),
                reply("Telma 40 jud gaya."),
            ],
            # He deleted it with his thumb between the two turns, so this id is from
            # before. The desk does not refuse it — it says what is there, and the
            # model reads that with his next words.
            "Ab Telma hata do.": reply_and_call("Hata diya.", "remove_items", item_ids=["li1"]),
            "Bas itna hi.": reply("Woh aapne khud hata diya tha. Confirm kar dijiye."),
        }
    )
    async with demo("orderdesk", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Telma 40 ki do strip de do.")

        await rig.driver.send_ui_event("row_added", _MANUAL_ROW)
        await rig.driver.send_ui_event("row_removed", {"item_id": "li1"})
        await rig.driver.user_says("Ab Telma hata do.")

        # One more turn, so the turn above's result is in the context being asserted:
        # `remove_items` is not marked, so its result is only visible to the request
        # that follows the turn that called it.
        await rig.driver.user_says("Bas itna hi.")

    results = "".join(
        str(p.function_response.response)
        for c in llm.captured_contents[-1]
        for p in (c.parts or [])
        if p.function_response is not None
    )
    assert "none of those ids are on the order" in results
    assert "'known_ids': ['m1']" in results, "the error did not name the row that is there"
    assert "changed the screen since you last read it" not in results, "the gate is back"


async def test_naming_something_already_on_the_order_lands_on_that_row() -> None:
    """He repeats himself while a question about the row is still open — because
    the answer has not come yet, which is exactly when a person repeats himself.

    Every repeat used to mint a fresh row, and an unresolved row keeps
    ``quantity=None`` forever, so the row he was actually looking at sat
    permanently un-orderable while the disambiguation moved to a sibling. He
    tracks products, not row ids: a quantity that never fills in reads as the
    medicine having been deleted.

    So all three turns here land on ``li1``: the second fills its quantity in
    place, the third overwrites that quantity and says so, and there is never an
    ``li2``. VOLINI is the real ten-SKU family, so the row stays unresolved
    throughout — which is the case a SKU-keyed check could not have caught."""
    llm = ScriptedGemini(
        {
            "Volini de do.": [
                reply_and_call("Theek hai.", "add_items", items=[{"text": "volini"}]),
                reply("Volini gel ya spray?"),
            ],
            "Volini do strip.": [
                reply_and_call(
                    "Theek hai.", "add_items", items=[{"text": "volini", "quantity": 2}]
                ),
                reply("Do strip likh liya — gel ya spray?"),
            ],
            "Nahin, teen strip.": [
                reply_and_call(
                    "Theek hai.", "add_items", items=[{"text": "volini", "quantity": 3}]
                ),
                reply("Do se teen kar diya."),
            ],
        }
    )
    async with demo("orderdesk", llm) as rig:
        await rig.driver.start_session()
        first = await rig.driver.user_says("Volini de do.")
        # The question is asked in the turn that added the row: `add_items` is marked,
        # so the model reads what the catalog said before the turn ends.
        check_turn(rig, first, units=2)
        await rig.driver.user_says("Volini do strip.")
        # No flush turn: the last turn's result reached its own second request, which
        # is the one asserted on below.
        await rig.driver.user_says("Nahin, teen strip.")

    drawn = [
        (c["command"], c.get("payload") or {})
        for c in rig.driver.ui_commands
        if str(c.get("command", "")).startswith("row_")
    ]
    assert {payload["id"] for _, payload in drawn} == {"li1"}, "a repeat minted a second row"
    assert [command for command, _ in drawn] == [
        "row_opened",
        "row_variants",
        "row_quantity",
        "row_quantity",
    ], drawn
    # The repeats say one thing each — how many he wants. Neither touches the open
    # question, which is why the row he is looking at is still the row being settled.
    assert drawn[-1][1]["quantity"] == 3

    results = "".join(
        str(p.function_response.response)
        for c in llm.captured_contents[-1]
        for p in (c.parts or [])
        if p.function_response is not None
    )
    assert "already_on_order" in results
    assert "he already had 2 of this" in results, "the overwrite was silent"


def test_only_the_tools_whose_answer_he_hears_now_hold_the_turn() -> None:
    """The mark, pinned tool by tool, so a change to it is a decision someone makes.

    Held: the screen read, and the tools that resolve a spoken name against the
    catalog — matched, a question to ask, or not in the catalog is something only the
    catalog knows, and the model's next words depend on which. Everything else acts on
    an outcome the model already knows, says its line with the call, and reads the
    result with his next words."""
    desk = OrderDesk()
    held = {tool.__name__ for tool in desk.tools if _needs_result_now(tool)}
    assert held == {"read_screen", "add_items", "refine_item", "change_variant"}


async def test_a_removal_made_in_silence_gets_the_desks_own_line() -> None:
    """The model called ``remove_items`` alone. The row goes, and what the
    pharmacist hears is the desk's own Hindi line for a removal — with no second
    request, and the line never reaches the context."""
    llm = ScriptedGemini(
        {
            "Telma 40 ki do strip de do.": [
                reply_and_call(
                    "Theek hai.", "add_items", items=[{"text": "telma 40", "quantity": 2}]
                ),
                reply("Lag gaya."),
            ],
            "Telma nahi chahiye.": call("remove_items", item_ids=["li1"]),
            "Screen par kya hai?": reply("Khaali hai."),
        }
    )
    async with demo("orderdesk", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Telma 40 ki do strip de do.")

        before = len(llm.captured_contents)
        turn = await rig.driver.user_says("Telma nahi chahiye.")
        check_turn(rig, turn, units=1)
        (line,) = (u.text for u in turn.units)
        assert line in _LINES[RemoveItems], line
        assert rig.command("remove_items")["ids"] == ["li1"]
        assert len(llm.captured_contents) - before == 1, "a silent turn asked the model again"

        await rig.driver.user_says("Screen par kya hai?")
        spoken = " ".join(
            part.text or ""
            for content in llm.captured_contents[-1]
            if content.role == "model"
            for part in content.parts or []
        )
        assert line not in spoken, f"the brain's line {line!r} reached the context"
