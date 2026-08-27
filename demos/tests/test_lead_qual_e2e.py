"""The Auric gold-loan advisor demo, end to end over the wire — no network, no key.

The real ``LeadQualBrain`` — the shipping ``demos/lead_qual/backend/brain.py``,
its real prompt, its real three tools, its real eligibility rules — hosted on a
real ``brain_server`` socket and driven by the conformance ``VoqalizeDriver``, with
only the *model* scripted. See ``tests/_harness.py`` for what every demo's e2e
proves.

Auric is the demo that most nearly proves why the language belongs in the brain:
**one** advisor answers callers in nine languages, chosen from the enquiry form's
state, which does not exist until the session opens. No agent-level setting could
hold that — it holds one value, and Tamil Nadu wants Tamil while Gujarat wants
Gujarati. So the resolution is tested here, on the frames, for both the state
route and the explicit override.

Run: ``cd demos && uv run pytest tests/test_lead_qual_e2e.py``
"""

from __future__ import annotations

from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, reply, reply_and_call

from ._harness import check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.lead_qual.brain import _GREETING  # noqa: E402

VOICE = "omnivoice/gauri"

TAMIL_LEAD = {"name": "Meera", "phone": "9840012345", "state": "Tamil Nadu", "city": "Coimbatore"}
HINDI_LEAD = {"name": "Rajesh", "phone": "9820012345", "state": "Rajasthan", "city": "Jaipur"}


def _llm() -> ScriptedGemini:
    return ScriptedGemini(
        {
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
            "Can we speak in Tamil?": [
                reply_and_call("ठीक है।", "switch_language", to={"language": "Tamil"}),
                reply("சரி, தமிழில் பேசலாம்."),
            ],
            "That's all, thanks.": [
                reply_and_call(
                    "धन्यवाद।",
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
                reply("आपका दिन शुभ हो।"),
            ],
        }
    )


async def test_greeting_and_voice_reach_the_wire() -> None:
    """A caller with no state match gets the Hindi default — the fixed opener,
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
    """The caller's own selection wins over the state's default — a Tamil Nadu
    customer who asked for Hindi is answered in Hindi."""
    async with demo("lead_qual", _llm()) as rig:
        await rig.driver.start_session(init={**TAMIL_LEAD, "language": "Hindi"})
        check_voice_pair(rig, voice=VOICE, language="hi")


async def test_switching_language_mid_call_moves_both_halves() -> None:
    """``switch_language`` is one ``session.configure`` call so it cannot
    half-apply: moving only the voice leaves the recognizer hearing Tamil as Hindi
    for the rest of the call, and every later reply is generated from that wrong
    transcript."""
    async with demo("lead_qual", _llm()) as rig:
        await rig.driver.start_session(init=HINDI_LEAD)
        check_voice_pair(rig, voice=VOICE, language="hi")

        turn = await rig.driver.user_says("Can we speak in Tamil?")
        check_turn(rig, turn, units=2)
        check_voice_pair(rig, voice=VOICE, language="ta")


async def test_eligibility_and_the_end_screen() -> None:
    """The two tools that carry the demo's outcome: eligibility is decided by the
    brain's own rules (not the model's arithmetic), and ``end_call`` hands the
    browser the lead it will render."""
    async with demo("lead_qual", _llm()) as rig:
        await rig.driver.start_session(init=HINDI_LEAD)

        t1 = await rig.driver.user_says("Forty grams of jewellery, I need two lakhs.")
        check_turn(rig, t1, units=2)
        # check_eligibility drives no screen — it only answers the model.
        assert rig.actions() == [], rig.actions()

        t2 = await rig.driver.user_says("That's all, thanks.")
        check_turn(rig, t2, units=2)

        assert rig.actions() == ["call_ended"], rig.actions()
        ended = rig.command("call_ended")
        assert ended["outcome"] == "qualified"
        # The enquiry-form identity comes from the payload the brain kept, not from
        # the model — which is what stops a hallucinated name reaching the CRM.
        assert ended["lead"]["name"] == "Rajesh"
        assert ended["lead"]["phone"] == "9820012345"
        assert ended["lead"]["loan_amount_inr"] == 200000
        assert rig.brain.ended is True
