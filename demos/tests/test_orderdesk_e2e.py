"""The OrderDesk demo, end to end over the wire — no network, no LLM key.

The real ``OrderDeskBrain`` — the shipping ``demos/orderdesk/backend/brain.py``,
its real prompt, its real nine tools — hosted on a real ``brain_server`` socket
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
from voqalize_demos.testing import ScriptedGemini, reply, reply_and_call

from ._harness import check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.orderdesk.brain import _FALLBACK_OPENER, _HELLO  # noqa: E402

VOICE = "omnivoice/gauri"
LANGUAGE = "hi"


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


async def test_the_browsers_screen_lands_silently_and_grounds_the_next_answer() -> None:
    """``state_sync`` is the one client message that must **not** speak.

    The pharmacist's own taps only reach the desk through this echo, so it has to
    fold into context without taking the floor — a brain that answered every
    re-send would talk over him mid-order, and one that ignored it would answer
    "what's on screen?" from a stale or absent turn. Both halves are asserted
    here because either one alone passes for the wrong reason."""
    llm = _llm()
    async with demo("orderdesk", llm) as rig:
        await rig.driver.start_session()
        before = len(rig.driver.ui_commands)

        await rig.driver.send_client_message(
            "state_sync",
            {"screen": {"items": [{"id": "m1", "status": "matched", "name": "Telma 40mg 15s"}]}},
        )
        # The floor is untaken: no speech, no screen command. Frames on one
        # connection are ordered, so the sync is already ingested by the time the
        # next turn is served — which is what the assertion below proves.
        turn = await rig.driver.user_says("Screen par kya hai?")
        check_turn(rig, turn, units=1)
        assert len(rig.driver.ui_commands) == before, "state_sync drove the screen"

    grounded = "".join(
        p.text or "" for c in llm.captured_contents[-1] for p in (c.parts or []) if c.role == "user"
    )
    assert "CURRENT ORDER SCREEN" in grounded
    assert "Telma 40mg 15s" in grounded
