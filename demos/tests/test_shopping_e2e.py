"""The Mobile Expert demo, end to end over the wire — no network, no LLM key.

The real ``ShoppingBrain`` — the shipping ``demos/shopping/backend/brain.py``, its
real prompt, its real tools, its real catalog — hosted on a real
``brain_server`` socket and driven by the conformance ``VoqalizeDriver``, with only
the *model* scripted. Same rig as every other demo's e2e; see ``tests/_harness.py``
for what every demo's e2e is required to prove.

Run: ``cd demos && uv run pytest tests/test_shopping_e2e.py``
"""

from __future__ import annotations

from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, call, reply, reply_and_call

from voqalize.sdk.gemini import _needs_result_now

from ._harness import check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.shopping.brain import _GREETING, ShoppingBrain  # noqa: E402

VOICE = "omnivoice/gaurav"
LANGUAGE = "en"


def _llm() -> ScriptedGemini:
    return ScriptedGemini(
        {
            # `search_products` is marked `@needs_result_now`: which phones its loose
            # keyword match put on screen is something only the search knows, so the
            # model is asked again with the result and talks about it in the same turn.
            "Show me Samsung phones under sixty thousand.": [
                reply_and_call(
                    "Let me pull those up.",
                    "search_products",
                    query={"query": "Samsung", "brand": "Samsung", "max_price": 60000},
                ),
                reply("Two Samsungs fit that budget — the S24 leads."),
            ],
            # `add_to_cart` is not: the model already knows what it added, so the whole
            # line goes with the call and the turn ends with the stream.
            "Add the S24 to my cart.": reply_and_call(
                "The Galaxy S24 is in your cart.",
                "add_to_cart",
                request={"product_id": "galaxy-s24"},
            ),
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
    """A search and a cart add, and the exact ``ui_command`` payloads
    ``/mobile``'s store reads — the catalog ids the brain resolved, not the
    model's raw arguments.

    The two turns are the two shapes of the loop. The search speaks twice — the
    short line with the call, then what the search found. The cart add speaks
    once, the line said with the call, because nothing it returns changes what
    the shopper hears."""
    async with demo("shopping", _llm()) as rig:
        await rig.driver.start_session()

        t1 = await rig.driver.user_says("Show me Samsung phones under sixty thousand.")
        check_turn(rig, t1, units=2)

        t2 = await rig.driver.user_says("Add the S24 to my cart.")
        check_turn(rig, t2, units=1)

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
    it, in order, ahead of the second turn's own line. The second turn's cart add
    is not marked, so its turn is one request and the last one captured — the
    greeting rides in every prompt as the conversation's opening line."""
    llm = _llm()
    async with demo("shopping", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Show me Samsung phones under sixty thousand.")
        await rig.driver.user_says("Add the S24 to my cart.")

    # The last request is the one "Add the S24" rides into.
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


def test_only_the_search_holds_the_turn() -> None:
    """The mark, pinned tool by tool, so a change to it is a decision someone makes.

    Held: ``search_products``, whose loose keyword match decides which phones the
    screen shows — only the search knows, and the model talks about those results.
    Every other tool shows or saves what the model named from the catalog in its
    own prompt, so it says its line with the call and reads the result with the
    shopper's next words."""
    brain = ShoppingBrain(client=ScriptedGemini({}))  # pyright: ignore[reportArgumentType]
    held = {tool.__name__ for tool in brain.tools if _needs_result_now(tool)}
    assert held == {"search_products"}


async def test_a_product_opened_in_silence_is_still_said() -> None:
    """The prompt has the model speak with every call; this is the turn where it
    did not. The brain says the product's own line — one request, no second ask —
    and the line never reaches the model's context."""
    llm = ScriptedGemini(
        {
            "Open the Pixel 8 Pro.": call("open_product", action={"product_id": "pixel-8-pro"}),
            "Thanks.": reply("Anytime."),
        }
    )
    async with demo("shopping", llm) as rig:
        await rig.driver.start_session()
        turn = await rig.driver.user_says("Open the Pixel 8 Pro.")
        check_turn(rig, turn, units=1)
        (line,) = (u.text for u in turn.units)
        assert line in ("Here's the Pixel 8 Pro.", "The Pixel 8 Pro is open."), line
        assert rig.actions() == ["open_product"]
        assert len(llm.captured_contents) == 1, "a silent turn asked the model again"

        await rig.driver.user_says("Thanks.")
        spoken = " ".join(
            part.text or ""
            for content in llm.captured_contents[-1]
            if content.role == "model"
            for part in content.parts or []
        )
        assert line not in spoken, f"the brain's line {line!r} reached the context"
