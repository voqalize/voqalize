"""The OrderDesk demo, end to end over the wire — no network, no LLM key.

The real ``OrderDeskBrain`` — the shipping ``demos/orderdesk/backend/brain.py``,
its real prompt, its real ten tools — hosted on a real ``brain_server`` socket
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

from ._harness import check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.orderdesk.brain import _FALLBACK_OPENER, _HELLO  # noqa: E402

VOICE = "omnivoice/gauri"
LANGUAGE = "hi"

# Two rows in the browser's own OrderSnapshot shape. `m1` is one the pharmacist
# added himself out of the search panel — the browser mints the `m*` id, and the
# desk has never seen it — which is what makes it an edit the model must be told
# about. `li1` is the row the scripted turn below puts there.
_MANUAL_ROW = {
    "id": "m1",
    "status": "matched",
    "spoken_text": "shelcal hd",
    "sku_code": "J0029363",
    "sku_name": "SHELCAL HD TABLET",
    "quantity": 5,
}
_TELMA_ROW = {
    "id": "li1",
    "status": "matched",
    "spoken_text": "telma 40",
    "sku_code": "J0031270",
    "sku_name": "TELMA 40MG TABLET",
    "quantity": 2,
}


def _llm() -> ScriptedGemini:
    return ScriptedGemini(
        {
            "Telma 40 ki do strip de do.": [
                reply_and_call(
                    "Theek hai, jod rahi hoon.",
                    "add_items",
                    items=[{"text": "telma 40", "quantity": 2}],
                ),
                reply("Telma 40 jud gaya, do strip."),
            ],
            "Ab Telma hata do.": [
                reply_and_call("Theek hai, hata rahi hoon.", "remove_items", item_ids=["li1"]),
                reply("Telma hata diya."),
            ],
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
    locks it to a SKU — the row lands twice (greyed, then matched), both as
    ``upsert_items`` — and a second turn removes it by the id the first turn
    minted."""
    async with demo("orderdesk", _llm()) as rig:
        await rig.driver.start_session()

        t1 = await rig.driver.user_says("Telma 40 ki do strip de do.")
        check_turn(rig, t1, units=2)

        upserts = [c for c in rig.driver.ui_commands if c.get("command") == "upsert_items"]
        assert len(upserts) == 2, rig.actions()
        added = upserts[-1]["payload"]["items"][0]
        assert added["status"] == "matched"
        assert added["quantity"] == 2
        assert added["sku"]["code"] == "J0031270"

        t2 = await rig.driver.user_says("Ab Telma hata do.")
        check_turn(rig, t2, units=2)

        removed = rig.command("remove_items")
        assert removed["ids"] == [added["id"]]


async def test_a_manual_edit_is_announced_but_never_dumped() -> None:
    """``state_sync`` is the one client message that must not speak — and, since the
    screen moved out of the context, the one that must not describe either.

    A production call put twenty-one full carts in front of the model in 113
    seconds, each labelled authoritative and none of them dated, and the model
    reasoned from whichever it noticed. So the snapshot now lands in the desk and
    stops: the context gets one line saying *he changed something* and pointing at
    ``read_screen``, with none of the cart's contents in it. Both halves are
    asserted — a note carrying the row's SKU would be the old dump again, one line
    at a time."""
    llm = _llm()
    async with demo("orderdesk", llm) as rig:
        await rig.driver.start_session()
        before = len(rig.driver.ui_commands)

        await rig.driver.send_client_message("state_sync", {"screen": {"items": [_MANUAL_ROW]}})
        # The floor is untaken: no speech, no screen command. Frames on one
        # connection are ordered, so the sync is already ingested by the time the
        # next turn is served — which is what the assertion below proves.
        turn = await rig.driver.user_says("Screen par kya hai?")
        check_turn(rig, turn, units=1)
        assert len(rig.driver.ui_commands) == before, "state_sync drove the screen"

    grounded = "".join(
        p.text or "" for c in llm.captured_contents[-1] for p in (c.parts or []) if c.role == "user"
    )
    assert "m1" in grounded and "added by hand" in grounded
    assert "read_screen" in grounded
    assert "J0029363" not in grounded, "the change note is carrying the cart"
    assert "CURRENT ORDER SCREEN" not in grounded, "the screen dump is back"


async def test_a_tool_aimed_at_a_screen_he_changed_is_refused_until_it_is_read() -> None:
    """The version gate, which is what makes read-don't-remember enforceable.

    A model that skips the read is holding row ids from before his edit — and on
    this screen a stale id is a different medicine, not a stale label. So the
    desk refuses instead of acting, and the refusal is retriable: read, then act.
    The scripted model here does exactly the wrong thing first."""
    llm = ScriptedGemini(
        {
            "Telma 40 ki do strip de do.": [
                reply_and_call(
                    "Theek hai, jod rahi hoon.",
                    "add_items",
                    items=[{"text": "telma 40", "quantity": 2}],
                ),
                reply("Telma 40 jud gaya."),
            ],
            "Ab Telma hata do.": [
                call("remove_items", item_ids=["li1"]),  # stale — he has edited since
                call("read_screen"),
                reply_and_call("Theek hai.", "remove_items", item_ids=["li1"]),
                reply("Telma hata diya."),
            ],
            "Bas itna hi.": reply("Theek hai, confirm kar dijiye."),
        }
    )
    async with demo("orderdesk", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Telma 40 ki do strip de do.")

        await rig.driver.send_client_message(
            "state_sync", {"screen": {"items": [_TELMA_ROW, _MANUAL_ROW]}}
        )
        await rig.driver.user_says("Ab Telma hata do.")

        removed = rig.command("remove_items")
        assert removed["ids"] == ["li1"]

        # One more turn, so the turn above's hops are in the context being asserted:
        # under automatic function calling a whole turn is one request, and its tool
        # results are only visible to the request that follows it.
        await rig.driver.user_says("Bas itna hi.")

    results = "".join(
        str(p.function_response.response)
        for c in llm.captured_contents[-1]
        for p in (c.parts or [])
        if p.function_response is not None
    )
    assert "changed the screen since you last read it" in results


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
                reply_and_call("Kaunsa Volini?", "add_items", items=[{"text": "volini"}]),
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
            "Bas itna hi.": reply("Theek hai."),
        }
    )
    async with demo("orderdesk", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Volini de do.")
        await rig.driver.user_says("Volini do strip.")
        await rig.driver.user_says("Nahin, teen strip.")
        # The flush turn: under automatic function calling a turn's tool results
        # only reach the request that follows it.
        await rig.driver.user_says("Bas itna hi.")

    rows = [
        row
        for c in rig.driver.ui_commands
        if c.get("command") == "upsert_items"
        for row in (c.get("payload") or {}).get("items", [])
    ]
    assert {r["id"] for r in rows} == {"li1"}, "a repeat minted a second row"
    assert rows[-1]["quantity"] == 3
    assert rows[-1]["status"] == "multi_variant", "the open question was answered by the repeat"

    results = "".join(
        str(p.function_response.response)
        for c in llm.captured_contents[-1]
        for p in (c.parts or [])
        if p.function_response is not None
    )
    assert "already_on_order" in results
    assert "he already had 2 of this" in results, "the overwrite was silent"
