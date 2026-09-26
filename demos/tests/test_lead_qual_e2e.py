"""The Auric gold-loan advisor demo, end to end over the wire — no network, no key.

The real ``LeadQualBrain`` — the shipping ``demos/lead_qual/backend/brain.py``,
its real prompt, its real tools, its real eligibility rules — hosted on a
real ``brain_server`` socket and driven by the conformance ``VoqalizeDriver``, with
only the *model* scripted. See ``tests/_harness.py`` for what every demo's e2e
proves.

Auric is the demo that most nearly proves why the language belongs in the brain:
**one** advisor answers users in many languages, chosen from the enquiry form's
state, which does not exist until the session opens. No agent-level setting could
hold that — it holds one value, and Tamil Nadu wants Tamil while Gujarat wants
Gujarati. So the resolution is tested here, on the frames, for both the state
route and the explicit override.

**Only ``check_eligibility`` carries the mark.** Its verdict comes from rules the
model does not hold, so a turn that calls it is asked again at once with the
result. ``switch_language`` and ``end_call`` act on the call, so the line and the
call share one response and the turn ends with it — the switch line in the
language the call is in now, the goodbye before the call ends it.

Run: ``cd demos && uv run pytest tests/test_lead_qual_e2e.py``
"""

from __future__ import annotations

from google.genai import types
from voqalize_demos import PHRASES
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, call, reply, reply_and_call

from voqalize.sdk.wire import Language

from ._harness import check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.lead_qual.brain import _GREETING  # noqa: E402

VOICE = "omnivoice/gauri"

TAMIL_LEAD = {"name": "Meera", "phone": "9840012345", "state": "Tamil Nadu", "city": "Coimbatore"}
HINDI_LEAD = {"name": "Rajesh", "phone": "9820012345", "state": "Rajasthan", "city": "Jaipur"}


def _results(contents: list[types.Content]) -> dict[str, str]:
    """Every tool result one request carried, by tool name."""
    return {
        p.function_response.name or "": str((p.function_response.response or {})["result"])
        for c in contents
        for p in (c.parts or [])
        if p.function_response is not None
    }


def _llm() -> ScriptedGemini:
    return ScriptedGemini(
        {
            # `check_eligibility` is marked: the holding line and the call in one
            # response, then a second request that carries the verdict.
            "Forty grams of jewellery, I need two lakhs.": [
                reply_and_call(
                    "एक मिनट देखती हूँ।",
                    "check_eligibility",
                    details={
                        "is_jewellery": True,
                        "gold_weight_grams": 40,
                        "loan_amount_thousands": 200,
                        "tenure_months": 6,
                    },
                ),
                reply("आप एलिजिबल हैं।"),
            ],
            # The switch line is said in the language the call is in *now*: it is
            # spoken before the new voice is configured. Tamil starts with the
            # user's next turn.
            "Can we speak in Tamil?": [
                reply_and_call(
                    "ठीक है, अब तमिल में बात करते हैं।",
                    "switch_language",
                    to={"language": "Tamil"},
                ),
            ],
            "சரி, சொல்லுங்கள்.": reply("உங்களிடம் எத்தனை கிராம் நகை இருக்கிறது?"),
            # The goodbye and the call in one response: nothing is said after
            # `end_call`, so the goodbye has to come before it.
            "That's all, thanks.": [
                reply_and_call(
                    "धन्यवाद, आपका दिन शुभ हो।",
                    "end_call",
                    record={
                        "outcome": "qualified",
                        "gold_form": "jewelry",
                        "gold_weight_grams": 40,
                        "loan_amount_inr": 200000,
                        "loan_purpose": "business",
                        "timeline": "within_week",
                        "preferred_next_step": "branch_visit",
                    },
                ),
            ],
        }
    )


async def test_greeting_and_voice_reach_the_wire() -> None:
    """A user with no state match gets the Hindi default — the fixed opener,
    voice and recognizer hint all landing before that audio, with no model call
    on the start path."""
    async with demo("lead_qual", _llm()) as rig:
        greeting = await rig.driver.start_session(init=HINDI_LEAD)
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text == _GREETING["Hindi"]
        check_voice_pair(rig, voice=VOICE, language="hi")


async def test_the_enquiry_state_picks_the_language_for_the_greeting() -> None:
    """Tamil Nadu ⇒ Tamil, on the *greeting*, not the turn after it.

    The settings frame is emitted on the same ordered lane as the speech that
    follows, which is what makes this land on the first audio of the call. When the
    resolved pair was thrown away and only the display name kept, the Tamil
    customer got a Tamil hello read by the Hindi voice and transcribed by the Hindi
    recognizer — on every single call, invisibly."""
    async with demo("lead_qual", _llm()) as rig:
        greeting = await rig.driver.start_session(init=TAMIL_LEAD)
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text == _GREETING["Tamil"]
        check_voice_pair(rig, voice=VOICE, language="ta")


async def test_an_explicit_language_beats_the_state() -> None:
    """The user's own selection wins over the state's default — a Tamil Nadu
    customer who asked for Hindi is answered in Hindi."""
    async with demo("lead_qual", _llm()) as rig:
        await rig.driver.start_session(init={**TAMIL_LEAD, "language": "Hindi"})
        check_voice_pair(rig, voice=VOICE, language="hi")


async def test_switching_language_mid_call_moves_both_halves() -> None:
    """``switch_language`` is one ``session.configure`` request so it cannot
    half-apply: moving only the voice leaves the recognizer hearing Tamil as Hindi
    for the rest of the call, and every later reply is generated from that wrong
    transcript.

    It is sent without waiting and the tool is not marked, so the turn is one
    request and one unit of speech — the switch line, said in Hindi — and the
    result reaches the model with the user's next turn."""
    llm = _llm()
    async with demo("lead_qual", llm) as rig:
        await rig.driver.start_session(init=HINDI_LEAD)
        check_voice_pair(rig, voice=VOICE, language="hi")

        before = len(llm.captured_contents)
        turn = await rig.driver.user_says("Can we speak in Tamil?")
        check_turn(rig, turn, units=1)
        assert len(llm.captured_contents) - before == 1, "an unmarked tool took a second request"
        check_voice_pair(rig, voice=VOICE, language="ta")

        turn = await rig.driver.user_says("சரி, சொல்லுங்கள்.")
        check_turn(rig, turn, units=1)
        assert "Tamil" in _results(llm.captured_contents[-1])["switch_language"]


async def test_eligibility_and_the_end_screen() -> None:
    """The two tools that carry the demo's outcome: eligibility is decided by the
    brain's own rules (not the model's arithmetic), and ``end_call`` hands the
    browser the lead it will render.

    ``check_eligibility`` is marked, so the verdict is read in a second request of
    the same turn — the holding line, then the answer. ``end_call`` is not, so the
    goodbye and the call are one response and one unit, and nothing follows."""
    llm = _llm()
    async with demo("lead_qual", llm) as rig:
        await rig.driver.start_session(init=HINDI_LEAD)

        before = len(llm.captured_contents)
        t1 = await rig.driver.user_says("Forty grams of jewellery, I need two lakhs.")
        check_turn(rig, t1, units=2)
        assert len(llm.captured_contents) - before == 2
        verdict = _results(llm.captured_contents[-1])["check_eligibility"]
        assert "'eligible': True" in verdict, verdict
        # check_eligibility drives no screen — it only answers the model.
        assert rig.actions() == [], rig.actions()

        before = len(llm.captured_contents)
        t2 = await rig.driver.user_says("That's all, thanks.")
        check_turn(rig, t2, units=1)
        assert len(llm.captured_contents) - before == 1, "end_call took a second request"
        assert t2.units[0].text == "धन्यवाद, आपका दिन शुभ हो।"

        assert rig.actions() == ["call_ended"], rig.actions()
        ended = rig.command("call_ended")
        assert ended["outcome"] == "qualified"
        # The enquiry-form identity comes from the payload the brain kept, not from
        # the model — which is what stops a hallucinated name reaching the CRM.
        assert ended["lead"]["name"] == "Rajesh"
        assert ended["lead"]["phone"] == "9820012345"
        assert ended["lead"]["loan_amount_inr"] == 200000
        assert rig.brain.ended is True


async def test_an_end_call_made_in_silence_gets_the_goodbye_in_the_calls_language() -> None:
    """The model called ``end_call`` with no goodbye. The end screen still renders,
    and what the Tamil customer hears is the brain's own thanks, in Tamil — with no
    second request, and the line never reaches the context."""
    llm = ScriptedGemini(
        {
            "வேண்டாம், நன்றி.": call("end_call", record={"outcome": "not_interested"}),
            "சரி.": reply("நன்றி."),
        }
    )
    async with demo("lead_qual", llm) as rig:
        await rig.driver.start_session(init=TAMIL_LEAD)

        before = len(llm.captured_contents)
        turn = await rig.driver.user_says("வேண்டாம், நன்றி.")
        check_turn(rig, turn, units=1)
        (line,) = (u.text for u in turn.units)
        assert line in PHRASES[Language.TA]["thanks"], line
        assert rig.actions() == ["call_ended"], rig.actions()
        assert len(llm.captured_contents) - before == 1, "a silent turn asked the model again"

        await rig.driver.user_says("சரி.")
        spoken = " ".join(
            part.text or ""
            for content in llm.captured_contents[-1]
            if content.role == "model"
            for part in content.parts or []
        )
        assert line not in spoken, f"the brain's line {line!r} reached the context"
