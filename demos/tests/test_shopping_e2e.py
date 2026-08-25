"""The Mobile Expert demo, end to end over the wire — no network, no LLM key.

The real ``ShoppingBrain`` — the shipping ``demos/shopping/backend/brain.py``, its
real prompt, its real eleven tools, its real catalog — hosted on a real
``brain_server`` socket and driven by the conformance ``VoqalizeDriver``, with only
the *model* scripted. Same rig as every other demo's e2e; see ``tests/_harness.py``
for what every demo's e2e is required to prove.

Run: ``cd demos && uv run pytest tests/test_shopping_e2e.py``
"""

from __future__ import annotations

from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, reply, reply_and_call

from ._harness import check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.shopping.brain import _GREETING  # noqa: E402

VOICE = "omnivoice/gaurav"
LANGUAGE = "en"


def _llm() -> ScriptedGemini:
    return ScriptedGemini(
        {
            "Show me Samsung phones under sixty thousand.": [
                reply_and_call(
                    "Let me pull those up.",
                    "search_products",
                    query={"query": "Samsung", "brand": "Samsung", "max_price": 60000},
                ),
                reply("Two Samsungs fit that budget — the S24 leads."),
            ],
            "Add the S24 to my cart.": [
                reply_and_call("Adding it.", "add_to_cart", request={"product_id": "galaxy-s24"}),
                reply("The Galaxy S24 is in your cart."),
            ],
        }
    )


async def test_greeting_and_voice_reach_the_wire() -> None:
    """The store greets, and its declared male English voice lands on **both** legs
    before the greeting audio does."""
    async with demo("shopping", _llm()) as rig:
        greeting = await rig.driver.start_session()
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text == _GREETING
        check_voice_pair(rig, voice=VOICE, language=LANGUAGE)


async def test_search_and_cart_drive_the_screen() -> None:
    """Two turns, each a tool round-trip: two inference brackets apiece, and the
    exact ``ui_command`` payloads ``/mobile``'s store reads — the catalog ids the
    brain resolved, not the model's raw arguments."""
    async with demo("shopping", _llm()) as rig:
        await rig.driver.start_session()

        t1 = await rig.driver.user_says("Show me Samsung phones under sixty thousand.")
        check_turn(rig, t1, units=2)

        t2 = await rig.driver.user_says("Add the S24 to my cart.")
        check_turn(rig, t2, units=2)

        assert rig.actions() == ["show_search", "add_to_cart"], rig.actions()

        search = rig.command("show_search")
        assert search["query"] == "Samsung"
        assert search["brand"] == "Samsung"
        assert search["max_price"] == 60000
        # The browser renders rows by id; the brain resolves them against the real
        # catalog, so an id that stops existing fails here and not on screen.
        assert search["result_ids"], "search returned no catalog rows"
        assert "galaxy-s24" in search["result_ids"]

        cart = rig.command("add_to_cart")
        assert cart["product_id"] == "galaxy-s24"
        assert cart["cart_count"] == 1
        assert rig.brain.cart == ["galaxy-s24"]


async def test_next_turn_is_prompted_with_heard_truth() -> None:
    """The second turn's prompt is the framework's heard transcript, not a
    brain-kept copy: the first turn's user line and both spoken replies are in
    it, in order, ahead of the second turn's own line. AFC resolves a tool
    round-trip inside one model call, so each user turn is exactly one call —
    the greeting rides in every prompt as the conversation's opening line."""
    llm = _llm()
    async with demo("shopping", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Show me Samsung phones under sixty thousand.")
        await rig.driver.user_says("Add the S24 to my cart.")

    # One call per turn — the second call is the one "Add the S24" rides into.
    turn_two = llm.captured_contents[-1]
    spoken = [
        (c.role, "".join(p.text or "" for p in (c.parts or []) if p.text))
        for c in turn_two
        if any(p.text for p in (c.parts or []))
    ]
    assert spoken == [
        ("model", _GREETING),
        ("user", "Show me Samsung phones under sixty thousand."),
        ("model", "Let me pull those up."),
        ("model", "Two Samsungs fit that budget — the S24 leads."),
        ("user", "Add the S24 to my cart."),
    ]
