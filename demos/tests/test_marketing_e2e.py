"""Tanya, the homepage agent, end to end over the wire — no network, no LLM key.

The real ``MarketingBrain`` — the shipping ``demos/marketing/backend/brain.py``,
its real prompt, its real knowledge base, its real tools — hosted on a real
``brain_server`` socket and driven by the conformance ``VoqalizeDriver``, with only
the *model* scripted. See ``tests/_harness.py`` for what every demo's e2e proves.

Marketing earns two checks no other demo needs.

**The page lives in another repo.** Tanya points at elements in the marketing
site's Astro components, and the model names only a target — the brain derives
which band to scroll to. So the assertion worth making here is that the section
crossing the wire is the one that target actually belongs to, because a target and
an anchor that disagree scroll the visitor away from the thing being lit up.

**She is the only demo that changes language mid-call.** Both legs have to move
together, the voice has to follow to a persona that speaks the new language, and
for a language the recognizer understands but no reference clip speaks, the two
legs must deliberately *differ* — heard in the visitor's language, spoken with the
Hindi clip. That substitution is stated, never silent, and a table that quietly
drifted would sound fine in every transcript.

Run: ``cd demos && uv run pytest tests/test_marketing_e2e.py``
"""

from __future__ import annotations

from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, reply, reply_and_call

from ._harness import _configs, _last, check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.marketing.brain import (  # noqa: E402
    _GREETING,
    LanguageRequest,
    MarketingBrain,
)

VOICE = "kokoro/ava"
LANGUAGE = "en"

# `how.diagram` sits in the `how` band. ``TargetId`` is a Literal over the page's
# own `data-vq` vocabulary, so a target the site does not carry cannot reach a
# tool body at all — this test fails at validation if the homepage is re-cut.
TARGET = "how.diagram"
SECTION = "how"


def _llm() -> ScriptedGemini:
    return ScriptedGemini(
        {
            "How does this integrate?": [
                reply_and_call(
                    "Here.",
                    "point_at",
                    # One tool, one model, one parameter — the argument is the
                    # ``PointRequest``, nested under the name the method gives it.
                    # That name is part of the schema Gemini reads, so a script
                    # writes what the model would write. Note what is *not* here:
                    # the section. The model names the element; the brain knows
                    # which band holds it.
                    request={"target": TARGET, "reason": "one WebSocket per session"},
                ),
                reply("One route in your backend. We dial it."),
            ],
            "What would that cost me?": [
                reply_and_call(
                    "One moment.",
                    "look_up",
                    request={"topic": "pricing-and-preview"},
                ),
                reply_and_call(
                    "Free while it is in preview.",
                    "show_note",
                    note={
                        "title": "Pricing shape",
                        "markdown": "- Preview is free\n- Then: per session minute",
                    },
                ),
                reply("Rates land before charges do."),
            ],
            # No `layout`. The page has to be told one, so the brain defaults it
            # rather than refusing the call — a note that does not render because
            # the model did not pick a shape is the worse of the two outcomes.
            "How do I get started?": [
                reply_and_call(
                    "Three moves.",
                    "show_note",
                    note={
                        "title": "Getting started",
                        "layout": "steps",
                        "markdown": "1. Write the brain\n2. Point the agent at it\n3. Call it",
                    },
                ),
                reply("That is the whole path."),
            ],
            "क्या आप हिंदी बोल सकते हैं?": [
                reply_and_call("हाँ.", "set_language", request={"language": "hindi"}),
                reply("बिलकुल. पूछिए."),
            ],
            "Can we do this in Odia?": [
                reply_and_call("Switching.", "set_language", request={"language": "odia"}),
                reply("Odia has no voice of its own — I will speak Hindi."),
            ],
            "What is this?": reply("The integration. One socket, once per session."),
        }
    )


async def test_greeting_and_voice_reach_the_wire() -> None:
    """Tanya opens with a fixed written line — no model call on the start path — and
    the English checkpoint she speaks with lands on **both** legs before that audio.

    She is the only demo here not on a cloned persona: the visitor could be
    anywhere, so the call opens in English and moves from there."""
    async with demo("marketing", _llm()) as rig:
        greeting = await rig.driver.start_session()
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text == _GREETING
        check_voice_pair(rig, voice=VOICE, language=LANGUAGE)


async def test_the_brain_resolves_the_band_the_target_sits_in() -> None:
    """The model names an element; the anchor crossing the wire is derived from it.

    This is the cross-repo seam in one assertion. If ``content.py`` and the
    marketing site's ``data-vq`` attributes ever disagree, the model cannot name
    the target at all and validation fails here; if the target-to-section map
    drifts, the page scrolls somewhere other than the thing it lights up."""
    async with demo("marketing", _llm()) as rig:
        await rig.driver.start_session()

        turn = await rig.driver.user_says("How does this integrate?")
        check_turn(rig, turn, units=2)

        assert rig.actions() == ["point_at"], rig.actions()
        pointed = rig.command("point_at")
        assert pointed["target"] == TARGET
        assert pointed["section"] == SECTION
        assert pointed["reason"] == "one WebSocket per session"


async def test_a_deeper_question_reads_one_file_and_answers_in_the_panel() -> None:
    """The two-tier knowledge base, end to end: L1 did not settle it, one deep dive
    was read, and the answer came back as markdown rather than a paragraph of
    speech. ``look_up`` drives no screen — it is a read — so the only command on the
    wire is the panel."""
    async with demo("marketing", _llm()) as rig:
        await rig.driver.start_session()

        turn = await rig.driver.user_says("What would that cost me?")
        check_turn(rig, turn, units=3)

        assert rig.actions() == ["show_note"], rig.actions()
        note = rig.command("show_note")
        assert note["title"] == "Pricing shape"
        assert "per session minute" in note["markdown"]
        # The model named no layout and the page still gets one.
        assert note["layout"] == "note"


async def test_a_layout_the_model_chose_reaches_the_page() -> None:
    """``layout`` says how the panel is laid out, and the page owns the rendering — so
    the only thing to prove on this side is that the word the model chose is the word
    that crosses the wire. A layout that does not suit the writing it was given falls
    back to prose in the browser; it cannot break a call."""
    async with demo("marketing", _llm()) as rig:
        await rig.driver.start_session()

        turn = await rig.driver.user_says("How do I get started?")
        check_turn(rig, turn, units=2)

        assert rig.actions() == ["show_note"], rig.actions()
        assert rig.command("show_note")["layout"] == "steps"


async def test_switching_to_hindi_moves_both_legs_and_the_voice_follows() -> None:
    """A voice that cannot speak the new language is a 403 at the speech tier, so the
    persona moves with the language rather than after it. Both legs are stated in
    one request — the SDK refuses to build a half-stated one — and the page is told,
    so the panel renders in the right script."""
    async with demo("marketing", _llm()) as rig:
        await rig.driver.start_session()

        turn = await rig.driver.user_says("क्या आप हिंदी बोल सकते हैं?")
        check_turn(rig, turn, units=2)

        check_voice_pair(rig, voice="omnivoice/gauri", language="hi")
        assert rig.actions() == ["language_changed"], rig.actions()
        assert rig.command("language_changed") == {"language": "hindi", "code": "hi"}


async def test_a_language_with_no_clip_is_heard_in_itself_and_spoken_in_hindi() -> None:
    """The two legs deliberately differ, and that is what reaches the wire.

    Odia is recognized and has no reference clip. The speech tier rejects that
    pairing outright rather than substituting behind anyone's back, so the table
    states the substitution — recognizer in Odia, voice reading the Hindi clip."""
    async with demo("marketing", _llm()) as rig:
        await rig.driver.start_session()

        turn = await rig.driver.user_says("Can we do this in Odia?")
        check_turn(rig, turn, units=2)

        configs = _configs(rig)
        assert _last(configs, lambda c: c.stt.language if c.stt else None) == "or"
        assert _last(configs, lambda c: c.tts.language if c.tts else None) == "hi"
        assert _last(configs, lambda c: c.tts.voice if c.tts else None) == "omnivoice/gauri"
        # The page is told the language the visitor is *speaking*, not the clip —
        # it is what the panel renders in.
        assert rig.command("language_changed") == {"language": "odia", "code": "or"}


async def test_the_substitution_is_handed_back_for_tanya_to_say() -> None:
    """A tool returns "ok" and nothing more, except where it knows something the
    model does not. This is that exception: the visitor is about to hear a Hindi
    speaker answer their Odia, and the only place that fact exists is the table —
    so the tool hands back the sentence rather than leaving Tanya to discover it.

    Asserted against the tool directly because the scripted model answers a turn in
    one hop, so a tool result never reaches a captured request."""
    async with demo("marketing", _llm()) as rig:
        await rig.driver.start_session()
        brain = rig.brain
        assert isinstance(brain, MarketingBrain)

        spoken = await brain.set_language(LanguageRequest(language="odia"))
        assert "no odia voice" in spoken.lower()
        assert "hindi" in spoken.lower()

        # A language with a clip of its own says nothing extra — there is nothing
        # for Tanya to explain.
        assert await brain.set_language(LanguageRequest(language="tamil")) == "ok"


async def test_the_scroll_position_lands_silently_and_grounds_the_next_answer() -> None:
    """``section_viewed`` is the one app event that must **not** speak.

    A visitor scrolling is not a question: the brain records where they are and
    stays quiet, and only the next spoken turn shows it took — one line saying they
    moved, pointing at the tool that reads back *where*. Both halves are asserted
    because either alone passes for the wrong reason: a brain that ignored the
    event is also silent, and the band is nowhere in the context as a blob, which
    is the whole point of the read tool."""
    llm = _llm()
    async with demo("marketing", llm) as rig:
        await rig.driver.start_session()
        before = len(rig.driver.ui_commands)

        await rig.driver.send_ui_event("section_viewed", {"section": SECTION})
        # The floor is untaken: no speech, no screen command. Frames on one
        # connection are ordered, so the scroll is already ingested by the time the
        # next turn is served — which is what the assertion below proves.
        turn = await rig.driver.user_says("What is this?")
        check_turn(rig, turn, units=1)
        assert len(rig.driver.ui_commands) == before, "section_viewed drove the screen"

    grounded = "".join(
        p.text or "" for c in llm.captured_contents[-1] for p in (c.parts or []) if c.role == "user"
    )
    assert "scrolled to a different part of the page" in grounded
    assert "where_they_are" in grounded
