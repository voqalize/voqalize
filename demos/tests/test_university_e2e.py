"""Varenya University — the course advisor and the admissions counsellor — end to
end over the wire, no network, no LLM key.

The real ``UniversityBrain`` (its prompt, tools, cue resolver and Stage
director) on a real ``brain_server`` socket, driven by the conformance
``VoqalizeDriver``, with only the model scripted by ``ScriptedOpenAI`` (flat
tool arguments). Each landing page's main flow:

- ``/programs``: the advisor hears a working graduate's limits, calls
  ``find_programs`` and narrates while the finder's filters tick
  (``catalogue.filter`` cues, resolved to the page's labels), marks two picks,
  then compares them.
- ``/apply``: the counsellor answers a fee question from the authored
  reference and fills the application with ``apply.fill`` cues (values resolved
  to the form's option ids); a refused cue reaches the model; the family
  presses Pay and the counsellor congratulates them in the next quiet spell.
- U2 (the owner's call of 25 Nov, replayed): an admission question leads to
  the admission process, not a comparison; ``fill_application`` fills a group
  of details at once, rings the mobile and email boxes for typing, tells a
  refusal, keeps a later step's details for it, and a yes or "next" moves the
  form on. U3: no offer of help while the visitor browses.
- A route change (Stage ``hello``) switches the job; Hindi heard, the toggle
  and ``set_language`` move both legs and the page's toggle follows.
- A dropped brain socket (redial, SDK 0.15.0): the next socket for the same
  session adopts the call as it was.

Run: ``cd demos && uv run pytest tests/test_university_e2e.py``
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from voqalize_demos.discovery import discover
from voqalize_demos.testing import (
    ScriptedOpenAI,
    call,
    input_texts,
    reply,
    reply_and_call,
    tool_results_of,
)

from voqalize.conformance import VoqalizeDriver
from voqalize.sdk.wire import ConfigureFrame

from ._harness import DemoRig, check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.university.brain import REJOIN, UniversityBrain  # noqa: E402
from voqalize_demos._loaded.university.data import catalogue, inr, persona  # noqa: E402
from voqalize_demos._loaded.university.prompt import greeting  # noqa: E402

VOICE_EN = persona().voices["en"]
VOICE_HI = persona().voices["hi"]


@pytest.fixture(autouse=True)
def _no_call_carried_between_tests() -> Iterator[None]:
    """Every test here opens the same session id, and a dropped call is held for
    a redial to rejoin (CONTRACT.md, redial): clear the store around each test,
    so no test rejoins the one before it. Real session ids never repeat."""
    REJOIN.clear()
    yield
    REJOIN.clear()


def _cues(rig: DemoRig) -> list[tuple[str, list[str]]]:
    return [
        (str(c["payload"]["move"]), list(c["payload"]["args"]))
        for c in rig.driver.ui_commands
        if c.get("command") == "stage_cue"
    ]


def _raw_cues(rig: DemoRig) -> list[dict[str, Any]]:
    return [dict(c["payload"]) for c in rig.driver.ui_commands if c.get("command") == "stage_cue"]


def _last_input(llm: ScriptedOpenAI) -> str:
    return input_texts(llm.captured_inputs[-1])


# ─── Greeting, voice and job by landing ─────────────────────────────────────


async def test_the_advisor_greets_in_english_on_programs() -> None:
    async with demo("university", ScriptedOpenAI()) as rig:
        hello = await rig.driver.start_session(
            init={"landing": "/programs", "lang": "en", "surface": "university-web"}
        )
        check_greeting(rig, hello)
        check_voice_pair(rig, voice=VOICE_EN, language="en")
        assert hello is not None and hello.text == greeting("advisor", "en")
        assert persona().name in hello.text
        brain = rig.brain
        assert isinstance(brain, UniversityBrain) and brain.job == "advisor"


async def test_the_counsellor_greets_in_hindi_on_apply() -> None:
    async with demo("university", ScriptedOpenAI()) as rig:
        hello = await rig.driver.start_session(init={"landing": "/apply", "lang": "hi"})
        check_greeting(rig, hello)
        check_voice_pair(rig, voice=VOICE_HI, language="hi")
        assert hello is not None and hello.text == greeting("counsellor", "hi")
        brain = rig.brain
        assert isinstance(brain, UniversityBrain) and brain.job == "counsellor"


# ─── /programs: the course advisor ──────────────────────────────────────────

ADVISOR_ASK = (
    "I did a B.Com, I work full time, I can give about 12 hours a week and "
    "1.5 lakh a year, and I want to move into data and business."
)
FOUND_SAY = (
    "{filter: Level | postgraduate} With a degree already, a postgraduate programme fits. "
    "{filter: Mode | online} Online, because you work full time. "
    "{filter: Fee | Under 1 lakh} {filter: Fee | ₹1-2 lakh} Both stay inside 1.5 lakh a year. "
    "{pick: online-mba | Online M.Com} The Online MBA and the Online M.Com fit best. "
    "Shall I compare them?"
)


def _advisor() -> ScriptedOpenAI:
    return ScriptedOpenAI(
        {
            ADVISOR_ASK: [
                call(
                    "find_programs",
                    level="pg",
                    interests="data, business, analytics",
                    mode="online",
                    max_fee_per_year=150000,
                    hours_per_week=12,
                ),
                reply(FOUND_SAY),
            ],
            "Yes, compare them.": [
                call("compare_programs", programs=["online-mba", "online-mcom"]),
                reply(
                    "{compare: online-mba | online-mcom} The MBA is 1 lakh 10 thousand a "
                    "year, the M.Com 50 thousand; both take about 10 to 12 hours a week."
                ),
            ],
        }
    )


async def test_the_advisor_ticks_the_finder_as_it_explains_and_compares() -> None:
    llm = _advisor()
    async with demo("university", llm) as rig:
        await rig.driver.start_session(init={"landing": "/programs", "lang": "en"})
        turn = await rig.driver.user_says(ADVISOR_ASK)
        check_turn(rig, turn, units=1)
        assert "{" not in turn.text, "a cue was spoken"
        assert "Online MBA" in turn.text

        # The read came back in the same turn, with the programmes and the cues to write.
        found = "".join(tool_results_of(llm.captured_inputs[1], "find_programs"))
        assert "online-mba" in found and "{filter: Level | Postgraduate}" in found
        assert inr(catalogue().program("online-mba").fee_per_year) in found  # type: ignore[union-attr]

        # Each cue reached the page with the page's own labels and ids, anchored to words.
        assert _cues(rig) == [
            ("catalogue.filter", ["Level", "Postgraduate"]),
            ("catalogue.filter", ["Mode", "Online"]),
            ("catalogue.filter", ["Fee", "Under ₹1 lakh"]),
            ("catalogue.filter", ["Fee", "₹1\u20132 lakh"]),
            ("catalogue.pick", ["online-mba", "online-mcom"]),
        ]
        assert all(c["at"] for c in _raw_cues(rig)), "a cue with no words to fire at"

        turn = await rig.driver.user_says("Yes, compare them.")
        check_turn(rig, turn, units=1)
        assert _cues(rig)[-1] == ("catalogue.compare", ["online-mba", "online-mcom"])
        compared = "".join(tool_results_of(llm.captured_inputs[-1], "compare_programs"))
        assert "Fee per year: ₹1,10,000 | ₹50,000" in compared


async def test_a_cue_naming_nothing_is_dropped_and_told() -> None:
    llm = ScriptedOpenAI(
        {"Show me robotics.": reply("{filter: Level | Doctorate} We have no doctorates.")}
    )
    async with demo("university", llm) as rig:
        await rig.driver.start_session(init={"landing": "/programs"})
        turn = await rig.driver.user_says("Show me robotics.")
        check_turn(rig, turn)
        assert _cues(rig) == []
        await rig.driver.user_says("ok")
        assert "named nothing the page has" in _last_input(llm)


async def test_the_visitor_moving_to_apply_switches_the_job() -> None:
    llm = ScriptedOpenAI()
    async with demo("university", llm) as rig:
        await rig.driver.start_session(init={"landing": "/programs"})
        await rig.driver.send_ui_event(
            "stage_hello",
            {
                "runtime": "@voqalize/stage",
                "contract": 1,
                "url": "https://dev.voqalize.com/demos/university/apply",
            },
        )
        await asyncio.sleep(0.1)
        brain = rig.brain
        assert isinstance(brain, UniversityBrain)
        assert brain.job == "counsellor" and brain.path == "/apply"
        await rig.driver.user_says("Hello?")
        assert "ADMISSIONS COUNSELLOR" in _last_input(llm)


# ─── /apply: the admissions counsellor ──────────────────────────────────────

FEE_ASK = "What are the hostel charges in Pune?"
FILL_SAY = (
    "{fill: program | B.Tech Computer Science & Engineering} B.Tech CSE it is. "
    "{fill: campus | Pune} At the Pune campus. "
    "{fill: class12_stream | Science (PCM)} Science with maths in Class 12, "
    "{fill: class12_percent | 92.4%} and 92.4 percent, noted. "
    "{fill: hostel | yes} I've marked that you need a room."
)


def _counsellor() -> ScriptedOpenAI:
    return ScriptedOpenAI(
        {
            FEE_ASK: reply(
                "{show: hostel} In Pune, a twin-sharing AC room is 1 lakh 45 thousand "
                "rupees a year, with all meals."
            ),
            "It's for B.Tech CSE in Pune": reply(FILL_SAY),
            "What scholarship would she get?": [
                call(
                    "check_eligibility",
                    program="btech-cse",
                    class12_stream="science_pcm",
                    class12_percent=92.4,
                    gender="female",
                ),
                reply("With 92.4 percent she gets 45 percent off tuition."),
            ],
            "submitted": reply("Congratulations, your application is in."),
        }
    )


async def test_the_counsellor_answers_from_the_reference_and_fills_the_form() -> None:
    llm = _counsellor()
    async with demo("university", llm) as rig:
        await rig.driver.start_session(init={"landing": "/apply", "lang": "en"})
        instructions = llm.captured_instructions
        turn = await rig.driver.user_says(FEE_ASK)
        check_turn(rig, turn, units=1)
        # The authored hostel charge is in the prompt the model answered from.
        assert "Pune Twin sharing, AC ₹1,45,000" in llm.captured_instructions[0]
        assert instructions is not None
        assert _cues(rig) == [("site.show", ["hostel"])]

        turn = await rig.driver.user_says(
            "It's for B.Tech CSE in Pune, she took science with maths and got 92.4% "
            "in Class 12, and she needs a hostel."
        )
        check_turn(rig, turn, units=1)
        assert "{" not in turn.text
        assert _cues(rig)[1:] == [
            ("apply.fill", ["program", "btech-cse"]),
            ("apply.fill", ["campus", "pune"]),
            ("apply.fill", ["class12_stream", "science_pcm"]),
            ("apply.fill", ["class12_percent", "92.4"]),
            ("apply.fill", ["hostel", "yes"]),
        ]

        # The page answers every cue; one is refused, and the model is told.
        for c in _raw_cues(rig)[:-1]:
            await rig.driver.send_ui_event(
                "stage_result",
                {"call_ref": c["call_ref"], "move": c["move"], "outcome": "applied"},
            )
        last = _raw_cues(rig)[-1]
        await rig.driver.send_ui_event(
            "stage_result",
            {
                "call_ref": last["call_ref"],
                "move": last["move"],
                "outcome": "refused",
                "detail": "the programme step is not reached yet",
                "refused": [{"arg": "field", "why": "finish step 2 first", "options": ["2"]}],
            },
        )
        await asyncio.sleep(0.1)

        turn = await rig.driver.user_says("What scholarship would she get?")
        check_turn(rig, turn, units=1)
        sent = _last_input(llm)
        assert "cue did not land" in sent and "finish step 2 first" in sent
        checked = "".join(tool_results_of(llm.captured_inputs[-1], "check_eligibility"))
        assert "45% of tuition" in checked and "₹1,87,000 a year" in checked

        # She presses Pay herself; the page reports it, and the next quiet spell is hers.
        await rig.driver.send_ui_event(
            "stage_event",
            {
                "name": "application.submitted",
                "by": "visitor",
                "data": {"reference": "VRN-27-48213", "filled": ["program"], "missing": []},
            },
        )
        await asyncio.sleep(0.1)
        brain = rig.brain
        assert isinstance(brain, UniversityBrain)
        assert brain._talk is not None  # pyright: ignore[reportPrivateUsage]
        idle = await rig.driver.user_idle()
        check_turn(rig, idle, units=1)
        sent = _last_input(llm)
        assert "submitted application VRN-27-48213" in sent and "congratulate" in sent


async def test_the_agents_own_form_changes_are_not_told_back() -> None:
    llm = ScriptedOpenAI()
    async with demo("university", llm) as rig:
        await rig.driver.start_session(init={"landing": "/apply"})
        await rig.driver.send_ui_event(
            "stage_event",
            {
                "name": "application.changed",
                "by": "agent",
                "data": {"field": "campus", "filled": ["campus"], "missing": [], "campus": "pune"},
            },
        )
        await rig.driver.send_ui_event(
            "stage_event",
            {
                "name": "application.changed",
                "by": "visitor",
                "data": {"field": "mobile", "filled": ["campus", "mobile"], "missing": []},
            },
        )
        await asyncio.sleep(0.1)
        await rig.driver.user_says("Done.")
        sent = _last_input(llm)
        assert "filled mobile" in sent
        assert "filled campus" not in sent


# ─── Languages ──────────────────────────────────────────────────────────────


async def test_hindi_heard_moves_both_legs_and_the_toggle() -> None:
    llm = ScriptedOpenAI({"fees": reply("बी.टेक सीएसई की फ़ीस 3 लाख 40 हज़ार रुपये प्रति वर्ष है।")})
    async with demo("university", llm) as rig:
        await rig.driver.start_session(init={"landing": "/admissions", "lang": "en"})
        check_voice_pair(rig, voice=VOICE_EN, language="en")
        turn = await rig.driver.user_says("beta ke liye B.Tech ki fees kya hai")
        check_turn(rig, turn, units=1)
        check_voice_pair(rig, voice=VOICE_HI, language="hi")
        assert rig.command("language_changed") == {"language": "hi"}


async def test_the_toggle_mid_call_switches_and_confirms() -> None:
    llm = ScriptedOpenAI()
    async with demo("university", llm) as rig:
        await rig.driver.start_session(init={"landing": "/programs", "lang": "hi"})
        await rig.driver.send_ui_event("language_requested", {"language": "en"})
        await asyncio.sleep(0.1)
        check_voice_pair(rig, voice=VOICE_EN, language="en")
        turn = await rig.driver.user_idle()
        check_turn(rig, turn)
        assert turn.units[0].text == "Sure, let's continue in English."


async def test_set_language_by_voice() -> None:
    llm = ScriptedOpenAI(
        {
            "Can we talk in Hindi?": reply_and_call(
                "ज़रूर, हिंदी में बात करते हैं।", "set_language", language="hi"
            )
        }
    )
    async with demo("university", llm) as rig:
        await rig.driver.start_session(init={"landing": "/programs", "lang": "en"})
        turn = await rig.driver.user_says("Can we talk in Hindi?")
        check_turn(rig, turn, units=1)
        check_voice_pair(rig, voice=VOICE_HI, language="hi")
        assert rig.command("language_changed") == {"language": "hi"}


# ─── The data the agent speaks from ─────────────────────────────────────────


def test_reads_are_marked_and_the_act_is_not() -> None:
    from voqalize.sdk.voice import _needs_result_now as is_needs_result_now

    marked = {
        "find_programs",
        "program_details",
        "compare_programs",
        "check_eligibility",
        "read_screen",
    }
    for name in [*marked, "set_language"]:
        tool = getattr(UniversityBrain, name)
        assert is_needs_result_now(tool) == (name in marked), name


def test_the_persona_is_named_only_in_its_file() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "university"
    name = persona().name
    for path in [*root.joinpath("backend").glob("*.py"), *root.joinpath("frontend/src").rglob("*")]:
        if path.is_file() and path.suffix in (".py", ".ts", ".tsx", ".css", ".json"):
            assert name not in path.read_text(encoding="utf-8"), f"{path} names {name}"


# ─── Redial: a call outlives a dropped brain socket ─────────────────────────


def _redials(driver: VoqalizeDriver) -> list[bool | None]:
    return [
        r.config.redial.enabled
        for r in driver.requests
        if isinstance(r, ConfigureFrame) and r.config.redial is not None
    ]


def _voices(driver: VoqalizeDriver) -> list[tuple[str | None, str | None]]:
    return [
        (r.config.tts.voice, r.config.stt.language if r.config.stt else None)
        for r in driver.requests
        if isinstance(r, ConfigureFrame) and r.config.tts is not None
    ]


async def test_a_dropped_socket_rejoins_the_call_where_it_was() -> None:
    """Mid-application on /apply: a fee answered, a field the family filled on
    the form, the toggle pressed to Hindi with its confirmation not yet said.
    Then the brain's socket drops without a hang-up. Redial is on; Voqalize
    dials again for the same session with the same init; the new socket's
    brain adopts the call (job, page, Hindi, the form mirror, the pending
    confirmation, the model's history) and the next turn carries on from it,
    with no second greeting and no second call-start note."""
    from voqalize_demos.discovery import build_for

    from voqalize.conformance import (
        BrainServer,
        DirectConnection,
        generate_keypair,
        mint_voqalize_token,
    )

    llm = _counsellor()
    build = build_for("university")
    built: list[UniversityBrain] = []

    def _build() -> Any:
        brain = build(llm)  # type: ignore[arg-type]
        built.append(brain)
        return brain

    keypair = generate_keypair()
    server = BrainServer(_build, host="127.0.0.1", port=0, public_keys=keypair.public_pem)
    port = await server.start()
    sid = "university-redial-e2e"
    init = {"landing": "/apply", "lang": "en"}

    def driver() -> VoqalizeDriver:
        token = mint_voqalize_token(
            private_key_pem=keypair.private_pem,
            session_id=sid,
            agent_id="university",
            tenant_id="demo",
        )
        return VoqalizeDriver(
            DirectConnection(f"ws://127.0.0.1:{port}", sid, token=token),
            session_id=sid,
            default_timeout=10.0,
        )

    first, second = driver(), driver()
    try:
        await first.open()
        await first.start_session(init=init)
        assert _redials(first) == [True], "redial is turned on with the voice, before the greeting"
        await first.user_says(FEE_ASK)
        await first.send_ui_event(
            "stage_event",
            {
                "name": "application.changed",
                "by": "visitor",
                "data": {"field": "mobile", "filled": ["mobile"], "missing": []},
            },
        )
        await first.send_ui_event("language_requested", {"language": "hi"})
        await asyncio.sleep(0.1)
        before = built[-1]
        assert before.lang == "hi" and before.job == "counsellor"
        assert before._confirm is not None  # pyright: ignore[reportPrivateUsage]
        assert before.stage.mirror is not None
        form = before.stage.mirror.read("application")
        history = len(before._history)  # pyright: ignore[reportPrivateUsage]

        # The socket drops: no End, no close code a hang-up would send.
        await first.aclose()
        for _ in range(50):
            if len(REJOIN) and REJOIN._held[sid][2] is not None:  # pyright: ignore[reportPrivateUsage]
                break
            await asyncio.sleep(0.02)

        # Voqalize redials: the same session id, the same init (still "en").
        await second.open()
        await second.start_session(init=init)
        after = built[-1]
        assert after is not before
        assert after.lang == "hi" and after.job == "counsellor" and after.path == "/apply"
        assert after.stage.mirror is not None and after.stage.mirror.read("application") == form
        assert _redials(second) == [True]
        assert _voices(second) == [(VOICE_HI, "hi")], "the new socket speaks the call's language"
        assert len(after._history) == history, "nothing added: no call-start note again"  # pyright: ignore[reportPrivateUsage]

        turn = await second.user_says("What scholarship would she get?")
        assert turn.units, "the call carried on after the drop"
        assert turn.units[0].text == "ज़रूर, अब हिंदी में बात करते हैं।", "the pending line"
        sent = input_texts(llm.captured_inputs[-1])
        assert sent.count("[The call starts on /apply.") == 1
        # The history holds the words as the voice was given them (amounts spelled, X8).
        assert FEE_ASK in sent and "one lakh 45 thousand" in sent, "the model's history came across"
        assert "filled mobile" in sent
        assert greeting("counsellor", "hi") not in sent, "no second greeting"
        assert "45% of tuition" in "".join(
            tool_results_of(llm.captured_inputs[-1], "check_eligibility")
        )
    finally:
        await second.aclose()
        await server.aclose()


async def test_a_redial_that_finds_nothing_starts_fresh_and_a_dropped_call_expires() -> None:
    """A redial reaching a process that never held the call (a deploy) carries
    on as a new conversation; a dropped call is let go two minutes after."""
    from voqalize_demos._loaded.university.rejoin import KEEP_AFTER_DROP_S, Rejoin

    now = [0.0]
    store: Rejoin[object] = Rejoin(clock=lambda: now[0])
    a, b = object(), object()
    store.hold("s1", a)
    store.dropped("s1", b)  # not the brain held: nothing changes
    now[0] = KEEP_AFTER_DROP_S + 1
    assert store.take("s1") is a, "a live call is kept however long it runs"
    store.hold("s1", a)
    store.dropped("s1", a)
    now[0] += KEEP_AFTER_DROP_S - 1
    assert len(store) == 1
    now[0] += 2
    assert store.take("s1") is None and len(store) == 0
    assert store.take("never-held") is None


async def test_an_expired_call_is_a_fresh_start_on_redial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A call dropped more than two minutes ago is gone: the brain a late
    redial starts on that session takes nothing, starts from init, notes the
    start and greets as a new call."""
    from voqalize_demos._loaded.university.rejoin import KEEP_AFTER_DROP_S

    now = [1000.0]
    monkeypatch.setattr(REJOIN, "_clock", lambda: now[0])
    stale = UniversityBrain.__new__(UniversityBrain)
    REJOIN.hold("university-e2e", stale)  # the session id the harness opens
    REJOIN.dropped("university-e2e", stale)
    now[0] += KEEP_AFTER_DROP_S + 1

    llm = ScriptedOpenAI()
    async with demo("university", llm) as rig:
        hello = await rig.driver.start_session(init={"landing": "/programs", "lang": "en"})
        check_greeting(rig, hello)
        brain = rig.brain
        assert isinstance(brain, UniversityBrain) and brain is not stale
        assert brain.job == "advisor" and brain.lang == "en"
        await rig.driver.user_says("Hello?")
        sent = _last_input(llm)
        assert "[The call starts on /programs." in sent
        assert greeting("advisor", "en") in sent, "a new call's greeting is heard"


async def test_no_redial_is_asked_of_a_voqalize_that_does_not_offer_it() -> None:
    """``configure`` raises for redial without the capability: the agent asks
    only where it is offered, and the call starts the same either way."""
    from voqalize.sdk.wire import Capability

    async with demo("university", ScriptedOpenAI()) as rig:
        rig.driver.capabilities.discard(Capability.REDIAL)
        hello = await rig.driver.start_session(init={"landing": "/apply", "lang": "en"})
        check_greeting(rig, hello)
        assert _redials(rig.driver) == []
        check_voice_pair(rig, voice=VOICE_EN, language="en")


# ─── Amounts in speech, both ways (X8) ──────────────────────────────────────

from voqalize_demos._loaded.university.spoken import (  # noqa: E402
    SpokenAmounts,
    amounts_note,
    implausible,
    parse_amounts,
    speak_text,
)


@pytest.mark.parametrize(
    ("written", "lang", "spoken"),
    [
        # A range with the scale said once is still read wrong by the TTS ("eight rupees to 12 lakh"): each end in full.
        ("Fees run ₹2 to 3.5 lakh.", "en", "Fees run two to three point five lakh rupees."),
        # Voqalize's TTS read a rupee amount with two decimals as rupees and paise even
        # before lakh ("one rupee and seventy five paisa lakh"); since speech 174bd6ef it
        # reads it right, so it goes as written.
        (
            "The B.Tech in AI is ₹1.75 lakh a year.",
            "en",
            None,
        ),
        ("That is ₹13.6 lakh in all.", "en", None),
        (
            "Fees run ₹1.75 lakh to ₹2.25 lakh.",
            "en",
            None,
        ),
        (
            "Both are in the ₹1\u20132 lakh band.",
            "en",
            "Both are in the one to two lakh rupees band.",
        ),
        (
            "Udaan gives 60% below ₹4 lakh a year.",
            "en",
            None,
        ),
        ("A median of 8.4 LPA.", "en", "A median of eight point four lakh a year."),
        (
            "A median salary of 12.5 lakh a year.",
            "en",
            "A median salary of twelve point five lakh a year.",
        ),
        (
            "Scholarship tiers: 90\u201394.99% gets 25%.",
            "en",
            "Scholarship tiers: 90% to 94.99% gets 25%.",
        ),
        # Plain amounts are left to the TTS, which reads them in lakh and thousand.
        ("₹3,40,000 a year, ₹13,60,000 in all; application fee ₹1,500.", "en", None),
        ("A seat is confirmed with ₹75,000; the guest house is ₹1,800 a night.", "en", None),
        # A cue is the page's label, never rewritten; the words after it are.
        (
            "{filter: Fee | ₹1\u20132 lakh} Under ₹2 lakh a year.",
            "en",
            None,
        ),
        # Hindi: the scale in Devanagari with ₹, so the TTS says डेढ़ / पौने दो; any
        # other decimal is whole rupees (तीन लाख चालीस हज़ार, not तीन दशमलव चार).
        ("फ़ीस ₹1.5 lakh सालाना है।", "hi", "फ़ीस ₹1.5 लाख सालाना है।"),
        ("फ़ीस ₹1.75 लाख है।", "hi", "फ़ीस ₹1.75 लाख है।"),
        ("फ़ीस ₹3.4 लाख सालाना, कुल ₹13.6 लाख।", "hi", "फ़ीस ₹3,40,000 सालाना, कुल ₹13,60,000।"),
        ("फ़ीस ₹1\u20132 लाख के बीच है।", "hi", "फ़ीस ₹1 लाख से ₹2 लाख के बीच है।"),
        ("बी.टेक सीएसई की फ़ीस 3 लाख 40 हज़ार रुपये प्रति वर्ष है।", "hi", None),
    ],
)
def test_amounts_are_written_the_way_the_voice_reads_them(
    written: str, lang: str, spoken: str | None
) -> None:
    assert speak_text(written, lang) == (written if spoken is None else spoken)


@pytest.mark.parametrize(
    ("heard", "values"),
    [
        ("about 1.5 lakh a year", [(150000, None)]),
        ("around 1 and half lakhs", [(150000, None)]),
        ("one and a half lakh", [(150000, None)]),
        ("my budget is 2 lakh 50 thousand", [(250000, None)]),
        ("three lakh forty thousand", [(340000, None)]),
        ("3,40,000 a year", [(340000, None)]),
        ("340000", [(340000, None)]),
        ("80k a year", [(80000, None)]),
        ("80 hazaar", [(80000, None)]),
        ("dedh lakh", [(150000, None)]),
        ("dhai lakh tak", [(250000, None)]),
        ("sava lakh", [(125000, None)]),
        ("paune do lakh", [(175000, None)]),
        ("साढ़े तीन लाख", [(350000, None)]),
        ("डेढ़ लाख सालाना", [(150000, None)]),
        ("लगभग ₹\u0967,\u096b\u0966,\u0966\u0966\u0966", [(150000, None)]),
        ("one point two crore", [(12000000, None)]),
        # Ranges: the top is the budget; the scale said once belongs to both ends.
        ("1 to 2 lakh a year", [(200000, 100000)]),
        ("between 1 and 2 lakh", [(200000, 100000)]),
        ("1-1.5 lakh", [(150000, 100000)]),
        ("एक से दो लाख", [(200000, 100000)]),
        # Two amounts in one breath: the budget and the family income.
        ("budget 1.5 lakh, family income 6 lakh", [(150000, None), (600000, None)]),
    ],
)
def test_spoken_amounts_parse_to_rupees(
    heard: str, values: list[tuple[float, float | None]]
) -> None:
    assert [(h.value, h.low) for h in parse_amounts(heard)] == values


async def test_an_amount_split_across_streamed_chunks_is_still_said_whole() -> None:
    """A model streams tokens: "₹1." then "75 la" then "kh". The rewrite waits for the
    amount (and for a cue to close), and the unit's start and end pass as they came."""
    from voqalize.sdk import SpeechChunk, SpeechEnd, SpeechStart

    async def stream() -> Any:
        yield SpeechStart()
        for piece in [
            "{filter: Fee | ₹1",
            "\u20132 lakh} It is ₹1.",
            "75 la",
            "kh a year; ₹2",
            "\u20133.5 lakh too.",
        ]:
            yield SpeechChunk(piece)
        yield SpeechEnd()

    out = [e async for e in SpokenAmounts(lambda: "en").wrap(stream())]
    assert isinstance(out[0], SpeechStart) and isinstance(out[-1], SpeechEnd)
    text = "".join(e.text for e in out if isinstance(e, SpeechChunk))
    assert text == (
        "{filter: Fee | ₹1\u20132 lakh} It is ₹1.75 lakh a year; "
        "two to three point five lakh rupees too."
    )


def test_an_implausible_amount_is_confirmed_back_never_used() -> None:
    """A budget of "around 1 and half lakhs" reaching the finder as ₹15, or an income
    in rupees where lakh was asked: neither is used; the model confirms it back."""
    why = implausible({"max_fee_per_year": 15}, ["around 1 and half lakhs a year"])
    assert why is not None and why.startswith("Not done")
    assert "₹1,50,000" in why and "₹1.5 lakh, right?" in why
    why = implausible({"family_income_lakh": 600000}, ["about six lakh"])
    assert why is not None and "₹6 lakh, right?" in why and "in lakh" in why
    assert implausible({"max_fee_per_year": 150000, "family_income_lakh": 6}, []) is None
    assert implausible({"max_fee_per_year": None}, []) is None
    note = amounts_note("I can spend 1 to 1.5 lakh a year")
    assert note == "[Amounts they said, in rupees: '1 to 1.5 lakh' = 100000 to 150000 rupees.]"
    assert amounts_note("We are from Pune.") is None


BUDGET_ASK = (
    "I finished Class 12, I like computers, and we can spend around 1 and half lakhs a year."
)


async def test_amounts_are_spoken_as_words_and_a_wrong_budget_is_confirmed() -> None:
    """Over the wire: the model is told the budget in rupees, a mis-read ₹15 never
    reaches the finder (the tool asks for a confirmation first), and "₹1.75 lakh" is
    given to the voice as written (the TTS reads it), with the cue in front of it
    anchored to those very words and still naming the page's label."""
    llm = ScriptedOpenAI(
        {
            BUDGET_ASK: [
                call("find_programs", level="ug", interests="computers", max_fee_per_year=15),
                reply("Just to check, ₹1.5 lakh a year, right?"),
            ],
            "Yes, one and a half lakh.": [
                call("find_programs", level="ug", interests="computers", max_fee_per_year=150000),
                reply(
                    "{filter: Fee | ₹1-2 lakh} Within ₹1.5 lakh a year, "
                    "{pick: btech-cse} the B.Tech CSE is ₹1.75 lakh, just above it."
                ),
            ],
        }
    )
    async with demo("university", llm) as rig:
        await rig.driver.start_session(init={"landing": "/programs", "lang": "en"})
        turn = await rig.driver.user_says(BUDGET_ASK)
        check_turn(rig, turn, units=1)
        told = _last_input(llm)
        assert "'1 and half lakhs' = about 150000 rupees" in told
        refused = "".join(tool_results_of(llm.captured_inputs[-1], "find_programs"))
        assert refused.startswith("Not done") and "₹1,50,000" in refused
        assert _cues(rig) == []
        assert "₹1.5 lakh a year, right?" in turn.text

        turn = await rig.driver.user_says("Yes, one and a half lakh.")
        check_turn(rig, turn, units=1)
        found = "".join(tool_results_of(llm.captured_inputs[-1], "find_programs"))
        assert "programmes meet the limits" in found
        assert "₹1.75 lakh" in turn.text
        cues = _raw_cues(rig)
        assert [(c["move"], c["args"]) for c in cues] == [
            ("catalogue.filter", ["Fee", "₹1\u20132 lakh"]),
            ("catalogue.pick", ["btech-cse"]),
        ]
        assert cues[0]["at"].startswith("Within ₹1.5 lakh a year")
        assert all(c["at"] in turn.text for c in cues)


# ─── Whitespace around a rewritten amount ─────────────────────────────────────

#: Amounts as a piece of streamed speech may start or end with them, with and without ₹.
_WS_AMOUNTS = [
    ("en", "7.2 lakh"),
    ("en", "₹7.2 lakh"),
    ("en", "1.14 crore"),
    ("en", "₹1.14 crore"),
    ("en", "₹8 to 12 lakh"),
    ("en", "Rs 5 lakh"),
    ("hi", "7.2 लाख"),
    ("hi", "₹7.2 लाख"),
    ("hi", "₹1.25 करोड़"),
    ("hi", "₹8 से 12 लाख"),
]


@pytest.mark.parametrize(("lang", "amount"), _WS_AMOUNTS)
@pytest.mark.parametrize(("before", "after"), [(" ", ""), ("", " "), (" ", " "), ("Fees: ", ", ")])
def test_a_rewritten_amount_keeps_the_whitespace_around_it(
    lang: str, amount: str, before: str, after: str
) -> None:
    """The stream is rewritten in pieces, and a piece may start or end with a space: a
    leading space eaten with the amount ran "It costs" into "seven point two lakh"."""
    assert speak_text(f"{before}{amount}{after}", lang) == (
        f"{before}{speak_text(amount, lang)}{after}"
    )


async def _ws_streamed(units: list[list[str]], lang: str) -> str:
    from voqalize.sdk import SpeechChunk, SpeechEnd, SpeechStart

    async def stream() -> Any:
        for unit in units:
            yield SpeechStart()
            for piece in unit:
                yield SpeechChunk(piece)
            yield SpeechEnd()

    out = [e async for e in SpokenAmounts(lambda: lang).wrap(stream())]
    return "".join(e.text for e in out if isinstance(e, SpeechChunk))


@pytest.mark.parametrize(
    ("lang", "sentence"),
    [
        ("en", "It costs 7.2 lakh a year."),
        ("en", "The flat is ₹1.14 crore now."),
        ("hi", "यह ₹7.2 लाख का है।"),
        ("en", "Fees: 7.2 lakh a year."),
        ("hi", "शुल्क: 7.2 लाख है।"),
    ],
)
async def test_every_two_chunk_split_speaks_like_the_whole_sentence(
    lang: str, sentence: str
) -> None:
    """However the model's tokens fall, the voice hears what the whole sentence rewrites to;
    so it does when the amount opens a second unit (" 7.2 lakh a year." after "It costs")."""
    whole = speak_text(sentence, lang)
    for i in range(1, len(sentence)):
        head, tail = sentence[:i], sentence[i:]
        assert await _ws_streamed([[head, tail]], lang) == whole, (head, tail)
        if tail[0] == " " and tail[1] in "₹0123456789":  # an amount starts the second unit
            assert await _ws_streamed([[head], [tail]], lang) == whole, (head, tail)


# ─── U1: the owner's call of 24 Nov, replayed ───────────────────────────────
#
# His words, exactly as the recognizer wrote them. The model is scripted, so
# these pin what the brain now does around it: what the reads return (lead,
# never pick from a bare area, skip ticks already on screen), the screen
# moving for "show me", a promise with no cue kept, a read never ending silent,
# a section talked about ringed. (Its seventh fix, one offer of help after the
# visitor opened a page by hand, was removed in U3: see below.)

U1_EXPLORE = "Uh I'm and wanted to explore few undergraduate programs. What else do you have?"
U1_ENGINEERING = "Engineering."
U1_SHOW_BTECH = "Uh can you show me your uh engineering uh uh in BTEC?"
U1_CSE = "I'm asking for computer science."
U1_CURRICULUM = (
    "Can you show me the curriculum of uh BTEC in Art Computer Science, Artificial "
    "Intelligence and Machine Learning?"
)
U1_ON_SCREEN = "Can you show me that on screen?"
U1_SEE_IT = "Yeah, I can see it now."
U1_FEES = "What is the fees for this?"


def _moves(rig: DemoRig) -> list[tuple[str, dict[str, Any]]]:
    return [
        (str(c["payload"]["move"]), dict(c["payload"]["args"]))
        for c in rig.driver.ui_commands
        if c.get("command") == "stage_move"
    ]


async def _hello(rig: DemoRig, route: str) -> None:
    await rig.driver.send_ui_event(
        "stage_hello",
        {
            "runtime": "@voqalize/stage",
            "contract": 1,
            "url": f"https://dev.voqalize.com/demos/university{route}",
        },
    )
    await asyncio.sleep(0.1)


async def _finder_shows(rig: DemoRig, filters: list[str], picks: list[str]) -> None:
    await rig.driver.send_ui_event(
        "stage_event",
        {
            "name": "catalogue.changed",
            "by": "agent",
            "data": {"filters": filters, "count": 6, "top": [], "picks": picks, "compared": []},
        },
    )
    await asyncio.sleep(0.1)


async def test_u1_a_level_alone_asks_for_the_area_and_an_area_alone_picks_nothing() -> None:
    """Turns 2-4: "explore undergraduate programmes" got a generic list with no
    screen change; "Engineering." picked civil, data science and EV and left
    computer science out; "show me your engineering B.Tech" re-ticked what was
    ticked and swapped the picks. Now a level alone ticks it and gets the
    areas to ask about; an area alone lists every programme of it, picks
    nothing and asks which branch; ticks already on screen are not asked for."""
    llm = ScriptedOpenAI(
        {
            U1_EXPLORE: [
                call("find_programs", level="ug", interests="undergraduate programs"),
                reply(
                    "{filter: Level | Undergraduate} We have undergraduate programmes in "
                    "engineering, business, design, law and health sciences. Which area "
                    "interests you?"
                ),
            ],
            U1_ENGINEERING: [
                call("find_programs", level="ug", school="engineering", interests="engineering"),
                reply(
                    "{filter: School | Engineering} All six engineering B.Techs are on your "
                    "screen now: computer science, AI and machine learning, data science, "
                    "electronics, mechanical with EVs, and civil. Which branch interests you?"
                ),
            ],
            U1_SHOW_BTECH: [
                call("find_programs", level="ug", school="engineering", interests="B.Tech"),
                reply("They're all here on your screen. Which branch shall we look at?"),
            ],
        }
    )
    async with demo("university", llm) as rig:
        await rig.driver.start_session(init={"landing": "/", "lang": "en"})

        turn = await rig.driver.user_says(U1_EXPLORE)
        check_turn(rig, turn, units=1)
        found = "".join(tool_results_of(llm.captured_inputs[1], "find_programs"))
        assert "by area" in found and "Engineering 6" in found and "Pick nothing yet" in found
        assert "{filter: Level | Undergraduate}" in found
        assert _cues(rig) == [("catalogue.filter", ["Level", "Undergraduate"])]

        await _finder_shows(rig, ["Level: Undergraduate"], [])
        turn = await rig.driver.user_says(U1_ENGINEERING)
        check_turn(rig, turn, units=1)
        found = tool_results_of(llm.captured_inputs[-1], "find_programs")[-1]
        assert "All 6 programmes" in found and "pick nothing yet" in found
        assert "B.Tech Computer Science & Engineering" in found
        # The level is ticked already: only the area is left to tick.
        assert "{filter: School | Engineering}" in found
        assert "{filter: Level | Undergraduate}" not in found.split("Already ticked")[0]
        assert "{pick:" not in found.split("\n")[-1]
        assert not any(m == "catalogue.pick" for m, _ in _cues(rig))

        await _finder_shows(rig, ["Level: Undergraduate", "School: Engineering"], [])
        turn = await rig.driver.user_says(U1_SHOW_BTECH)
        check_turn(rig, turn, units=1)
        found = tool_results_of(llm.captured_inputs[-1], "find_programs")[-1]
        assert "Every filter for this is already ticked" in found


async def test_u1_computer_science_ranks_computer_science_first() -> None:
    """Turn 6-7: "computer science" ranks the CSE programmes first, and the picks
    already on screen are named so they are kept unless the fit changes."""
    llm = ScriptedOpenAI(
        {
            U1_CSE: [
                call(
                    "find_programs", level="ug", school="engineering", interests="computer science"
                ),
                reply(
                    "{pick: btech-cse | btech-ai-ml | btech-ds} Computer science, then. B.Tech "
                    "CSE is the broad one, the AI and ML B.Tech goes deeper into machine "
                    "learning, and data science is about data. Shall I compare them?"
                ),
            ]
        }
    )
    async with demo("university", llm) as rig:
        await rig.driver.start_session(init={"landing": "/programs", "lang": "en"})
        await _finder_shows(rig, ["Level: Undergraduate", "School: Engineering"], ["btech-civil"])
        turn = await rig.driver.user_says(U1_CSE)
        check_turn(rig, turn, units=1)
        found = tool_results_of(llm.captured_inputs[-1], "find_programs")[-1]
        first = [line for line in found.splitlines() if line.startswith("- ")][:2]
        assert first[0].startswith("- btech-cse:") and first[1].startswith("- btech-ai-ml:")
        assert "Your picks on screen now: btech-civil" in found
        assert "Do not repeat back what they told you" in found


async def test_u1_show_me_the_curriculum_opens_the_page_at_the_curriculum() -> None:
    """Turn 8: the curriculum was spoken but the screen did not move. Now
    program_details opens the programme page at its curriculum, in the same
    turn, and returns the modules to answer from."""
    p = catalogue().program("btech-ai-ml")
    assert p is not None
    llm = ScriptedOpenAI(
        {
            U1_CURRICULUM: [
                call("program_details", program="btech-ai-ml", section="curriculum"),
                reply(
                    "Here's its curriculum on your screen: linear algebra for machine learning, "
                    "deep learning, natural language processing, computer vision and MLOps. "
                    "Shall I show you the fees and the scholarship you could get?"
                ),
            ]
        }
    )
    async with demo("university", llm) as rig:
        await rig.driver.start_session(init={"landing": "/programs", "lang": "en"})
        turn = await rig.driver.user_says(U1_CURRICULUM)
        check_turn(rig, turn, units=1)
        assert _moves(rig) == [("site.open", {"program": "btech-ai-ml", "section": "curriculum"})]
        result = tool_results_of(llm.captured_inputs[-1], "program_details")[-1]
        assert p.modules[0] in result and "write no open cue" in result
        # The model's "here's its curriculum on your screen" is not opened twice.
        assert not any(m == "site.open" for m, _ in _cues(rig))


async def test_u1_a_promise_to_show_with_no_cue_opens_the_page() -> None:
    """Turn 9: "I'll open the B.Tech CSE (AI & ML) page so you can see it on
    screen" with no cue, and nothing moved until he complained. The backstop
    now opens the programme the sentence names (or the one in focus)."""
    llm = ScriptedOpenAI(
        {
            "Tell me about the AI one.": [
                call("program_details", program="btech-ai-ml"),
                reply("It's a four-year B.Tech with a research track. Want to see the modules?"),
            ],
            U1_ON_SCREEN: reply(
                "I\u2019ll open the B.Tech CSE (Artificial Intelligence & Machine Learning) page so "
                "you can see it on screen."
            ),
            "And the data science one?": reply("Sure, I\u2019ll pull up its page for you."),
        }
    )
    async with demo("university", llm) as rig:
        await rig.driver.start_session(init={"landing": "/programs", "lang": "en"})
        await rig.driver.user_says("Tell me about the AI one.")
        before = len(_cues(rig))
        turn = await rig.driver.user_says(U1_ON_SCREEN)
        check_turn(rig, turn, units=1)
        assert _cues(rig)[before:] == [("site.open", ["btech-ai-ml"])]
        auto = _raw_cues(rig)[-1]
        assert auto["at"], "the backstop's cue has words to fire at"

        # A promise that names no programme opens the one in focus.
        brain = rig.brain
        assert isinstance(brain, UniversityBrain)
        brain.focus = "btech-ds"
        turn = await rig.driver.user_says("And the data science one?")
        check_turn(rig, turn, units=1)
        assert _cues(rig)[-1] == ("site.open", ["btech-ds"])


async def test_u1_a_read_followed_by_silence_is_answered_by_the_brain() -> None:
    """The silent-turn lesson (bank B1, insurance I1): the curriculum read ran
    and the model's second hop said nothing. The brain says the section's facts
    and the next step itself, never a promise and then silence."""
    p = catalogue().program("btech-ai-ml")
    assert p is not None
    llm = ScriptedOpenAI(
        {
            U1_CURRICULUM: [
                call("program_details", program="btech-ai-ml", section="curriculum"),
                reply(""),
            ]
        }
    )
    async with demo("university", llm) as rig:
        await rig.driver.start_session(init={"landing": "/programs", "lang": "en"})
        turn = await rig.driver.user_says(U1_CURRICULUM)
        check_turn(rig, turn, units=1)
        assert p.modules[0] in turn.text and p.name in turn.text
        assert turn.text.rstrip().endswith("?"), "the floor ends on the next step"


async def test_u1_a_section_talked_about_on_its_page_is_rung() -> None:
    """Turn 11: on the programme page he said "I can see it now" and the
    curriculum was read out with nothing pointed at. A sentence about a section
    of the page in front now rings that section; the fees question opens the
    fees (turn 14)."""
    llm = ScriptedOpenAI(
        {
            U1_SEE_IT: reply(
                "Great. The curriculum includes deep learning, natural language processing, "
                "computer vision and MLOps. Shall I show you the fees next?"
            ),
            U1_FEES: [
                call("program_details", program="btech-ai-ml", section="fees"),
                reply(
                    "It's ₹3,60,000 a year, ₹14,40,000 for all four years, with hostel and mess "
                    "separate. Shall I check which scholarship you could get with your Class 12 "
                    "marks?"
                ),
            ],
        }
    )
    async with demo("university", llm) as rig:
        await rig.driver.start_session(init={"landing": "/programs", "lang": "en"})
        await _hello(rig, "/programs/btech-ai-ml")
        turn = await rig.driver.user_says(U1_SEE_IT)
        check_turn(rig, turn, units=1)
        assert _cues(rig) == [("site.open", ["btech-ai-ml", "curriculum"])]

        turn = await rig.driver.user_says(U1_FEES)
        check_turn(rig, turn, units=1)
        assert _moves(rig)[-1] == ("site.open", {"program": "btech-ai-ml", "section": "fees"})
        result = tool_results_of(llm.captured_inputs[-1], "program_details")[-1]
        assert "₹3,60,000 a year" in result and "₹14,40,000" in result


async def test_u1_pointing_unasked_is_once_and_only_at_a_section_named() -> None:
    """The backstop rings a section of the page in front only when a sentence
    names it outright, once a turn, and never after the turn's tool already put
    a section of this page in view: a scholarship answer about "tuition" and
    "eligible women" rings neither the fees nor the eligibility (real-model run)."""
    llm = ScriptedOpenAI(
        {
            "All of them.": reply(
                "The Class 12 merit award is 10%, 25% or 50% of tuition. Women in STEM adds "
                "20% for eligible women. What did you score in Class 12?"
            ),
            "Show me the scholarships.": [
                call("program_details", program="btech-ai-ml", section="scholarships"),
                reply(
                    "The scholarships are on screen. The fees drop with a merit award. Shall I "
                    "check yours?"
                ),
            ],
        }
    )
    async with demo("university", llm) as rig:
        await rig.driver.start_session(init={"landing": "/programs", "lang": "en"})
        await _hello(rig, "/programs/btech-ai-ml")
        turn = await rig.driver.user_says("All of them.")
        check_turn(rig, turn, units=1)
        assert _cues(rig) == []
        turn = await rig.driver.user_says("Show me the scholarships.")
        check_turn(rig, turn, units=1)
        assert _cues(rig) == []
        assert _moves(rig) == [("site.open", {"program": "btech-ai-ml", "section": "scholarships"})]


async def test_the_form_note_lists_what_is_filled_so_nothing_is_asked_twice() -> None:
    """The insurance lesson (I1) on /apply: what the form holds reaches the model
    before its turn, with the rule to ask only for one thing still empty."""
    llm = ScriptedOpenAI()
    async with demo("university", llm) as rig:
        await rig.driver.start_session(init={"landing": "/apply"})
        await rig.driver.send_ui_event(
            "stage_event",
            {
                "name": "application.changed",
                "by": "agent",
                "data": {
                    "field": "class12_percent",
                    "filled": ["program", "campus", "class12_percent"],
                    "missing": ["class12_board"],
                    "step": 2,
                    "class12_percent": "92.4",
                },
            },
        )
        await asyncio.sleep(0.1)
        await rig.driver.user_says("What next?")
        sent = _last_input(llm)
        assert "class12_percent" in sent and "Never ask again for anything filled" in sent
        assert "step 2 of 5" in sent
        await rig.driver.user_says("Okay.")
        assert _last_input(llm).count("Never ask again for anything filled") == 1


def test_the_prompt_leads_and_keeps_screen_promises() -> None:
    from voqalize_demos._loaded.university.prompt import system_instruction

    text = system_instruction()
    assert "Every reply ends with ONE concrete next step" in text
    assert "Never repeat back what they told you" in text
    assert "without the cue or tool that does it in the same reply" in text
    assert "{open: mba | curriculum}" in text


def test_an_area_or_level_is_not_an_interest() -> None:
    from voqalize_demos._loaded.university.finder import interest_words

    assert interest_words("engineering") == set()
    assert interest_words("undergraduate programs B.Tech") == set()
    assert interest_words("computer science engineering") == {"computer", "science"}


# ─── U2: the owner's call of 25 Nov, replayed ───────────────────────────────
#
# "One of the most disastrous demos." Asking about admission led to a
# comparison; the application went one field per question, "noted" with
# nothing filled, the email confirmed twice, and the form never moved on. His
# words, as the recognizer wrote them, through the real brain.

U2_ADMISSION = (
    "I'm looking for an undergraduate admission into uh computer science and artificial "
    "intelligence uh program"
)
U2_NOT_COMPARE = (
    "Why do you want to compare? I I need exactly need to go to my uh process for admission "
    "for big tech CSC. in artificial intelligence and machine learning."
)
U2_START = "Yes, please."
U2_NAME = "S A M K E E T J A I N, twenty second October nineteen ninety six, and I'm male."
U2_CONTACT = "Mobile number is 8147-514179 and email is samkeit.jane 2210.gmail.com."
U2_CITY = "Bangalore. My father's name is Gathenja Kumara."
U2_TYPED = "I've typed the email in now."
U2_YES = "Yeah."
U2_ACADEMICS = (
    "State board for both, fifty four percent in class ten, physics chemistry maths, passed "
    "with ninety eight percent, and I'll take VUSAT."
)
U2_CAMPUS = "Banglaru, and yes I need a hostel, twin sharing AC."
U2_NEXT = "Next."


async def _form_reports(rig: DemoRig, by: str, step: int, filled: list[str], **shared: str) -> None:
    await rig.driver.send_ui_event(
        "stage_event",
        {
            "name": "application.changed",
            "by": by,
            "data": {"filled": filled, "missing": [], "step": step, **shared},
        },
    )
    await asyncio.sleep(0.1)


def _fills(rig: DemoRig) -> list[tuple[str, str]]:
    return [(a["field"], a["value"]) for m, a in _moves(rig) if m == "apply.fill"]


async def test_u2_an_admission_question_goes_to_admission_never_to_a_comparison() -> None:
    """Turns 1-2: "undergraduate admission into computer science and AI" picked
    three programmes and offered to compare them."""
    llm = ScriptedOpenAI(
        {
            U2_ADMISSION: [
                call(
                    "find_programs",
                    level="ug",
                    school="engineering",
                    interests="computer science and artificial intelligence",
                ),
                reply(
                    "{pick: btech-ai-ml} B.Tech CSE in AI and Machine Learning is the one. "
                    "{open: btech-ai-ml | selection} You apply online, then take VUSAT or send a "
                    "JEE Main score. Shall we start your application now?"
                ),
            ],
            U2_NOT_COMPARE: [
                call("program_details", program="btech-ai-ml", section="selection"),
                reply("Shall we start your application now?"),
            ],
        }
    )
    async with demo("university", llm) as rig:
        await rig.driver.start_session(init={"landing": "/", "lang": "en"})
        turn = await rig.driver.user_says(U2_ADMISSION)
        check_turn(rig, turn, units=1)
        sent = _last_input(llm)
        assert "They are asking about ADMISSION" in sent and "never to a comparison" in sent
        found = "".join(tool_results_of(llm.captured_inputs[-1], "find_programs"))
        assert "Do not offer a comparison" in found and "{open: id | selection}" in found
        assert ("site.open", ["btech-ai-ml", "selection"]) in _cues(rig)
        assert not [c for c in _cues(rig) if c[0] == "catalogue.compare"]

        turn = await rig.driver.user_says(U2_NOT_COMPARE)
        check_turn(rig, turn, units=1)
        assert "They are asking about ADMISSION" in _last_input(llm)


async def test_u2_the_application_goes_a_group_at_a_time_and_moves_on() -> None:
    """Turns 5-29: every detail filled the moment it is said, a group per
    question, mobile and email typed into ringed boxes, a refused value told,
    and a yes (or "next") moving the form on."""
    llm = ScriptedOpenAI(
        {
            U2_START: reply(
                "{go: apply} Let's start your application. Tell me your full name, date of birth "
                "and gender, and please type your mobile number and email in the two highlighted "
                "boxes."
            ),
            U2_NAME: [
                call(
                    "fill_application",
                    values=[
                        {"field": "full_name", "value": "Samkeet Jain"},
                        {"field": "date_of_birth", "value": "22 Oct 1996"},
                        {"field": "gender", "value": "male"},
                    ],
                ),
                reply("Done. Which city do you live in, and what is a parent's name?"),
            ],
            U2_CONTACT: [
                call(
                    "fill_application",
                    values=[
                        {"field": "mobile", "value": "8147-514179"},
                        {"field": "email", "value": "samkeit.jane2210.gmail.com"},
                    ],
                ),
                reply("Your mobile is in; the email needs an @, so please type it in its box."),
            ],
            U2_CITY: [
                call(
                    "fill_application",
                    values=[
                        {"field": "city", "value": "Bangalore"},
                        {"field": "parent_name", "value": "Gathenja Kumara"},
                    ],
                ),
                reply("Bangalore, Karnataka and your father's name are in."),
            ],
            U2_TYPED: reply("Thanks. If that looks right, shall we go to the next step?"),
            U2_YES: [
                reply("Which boards were your Class 10 and 12, and what did you score?"),
                reply("Bengaluru or Pune, and do you need a hostel room?"),
            ],
            U2_ACADEMICS: [
                call(
                    "fill_application",
                    values=[
                        {"field": "class10_board", "value": "State board"},
                        {"field": "class10_percent", "value": "54"},
                        {"field": "class12_board", "value": "state"},
                        {"field": "class12_stream", "value": "Science (PCM)"},
                        {"field": "class12_status", "value": "passed"},
                        {"field": "class12_percent", "value": "98%"},
                        {"field": "entrance_exam", "value": "vusat"},
                    ],
                ),
                reply("All filled. If that looks right, shall we go to the next step?"),
            ],
            U2_CAMPUS: [
                call(
                    "fill_application",
                    values=[
                        {"field": "campus", "value": "Bengaluru"},
                        {"field": "hostel", "value": "yes"},
                        {"field": "room_type", "value": "Twin sharing, AC"},
                    ],
                ),
                reply("Bengaluru with a twin AC room. Shall we go to the next step?"),
            ],
            U2_NEXT: reply("Will you upload your documents now, or later?"),
        }
    )
    async with demo("university", llm) as rig:
        await rig.driver.start_session(init={"landing": "/programs/btech-ai-ml", "lang": "en"})
        brain = rig.brain
        assert isinstance(brain, UniversityBrain) and brain.focus == "btech-ai-ml"

        # Starting: the form opens and the two boxes they type into are ringed.
        await rig.driver.user_says(U2_START)
        await _hello(rig, "/apply")
        assert ("site.show", {"target": "mobile"}) in _moves(rig)
        assert ("site.show", {"target": "email"}) in _moves(rig)

        # Three details in one answer: all three filled at once.
        turn = await rig.driver.user_says(U2_NAME)
        check_turn(rig, turn, units=1)
        assert _fills(rig) == [
            ("full_name", "Samkeet Jain"),
            ("date_of_birth", "22 Oct 1996"),
            ("gender", "male"),
        ]
        result = "".join(tool_results_of(llm.captured_inputs[-1], "fill_application"))
        assert "Filled on their screen now" in result
        assert "together in ONE natural question: city and a parent's or guardian's name" in result
        assert "mobile number and email: ask them to type it themselves" in result
        await _form_reports(rig, "agent", 1, ["full_name", "date_of_birth", "gender"])

        # Dictated anyway: the mobile goes in once, the email the form would
        # refuse is not sent and is told, never confirmed twice.
        turn = await rig.driver.user_says(U2_CONTACT)
        check_turn(rig, turn, units=1)
        assert _fills(rig)[-1] == ("mobile", "8147514179")
        assert "email" not in dict(_fills(rig))
        result = "".join(tool_results_of(llm.captured_inputs[-1], "fill_application"))
        assert "NOT filled" in result and "not an email address" in result
        assert "never ask them to confirm one" in result

        # A city fills its state: never "which state is Bangalore in?".
        await rig.driver.user_says(U2_CITY)
        assert _fills(rig)[-3:] == [
            ("city", "Bangalore"),
            ("state", "karnataka"),
            ("parent_name", "Gathenja Kumara"),
        ]
        step1 = ["full_name", "date_of_birth", "gender", "mobile", "city", "state", "parent_name"]
        await _form_reports(rig, "agent", 1, step1)
        await _form_reports(rig, "visitor", 1, [*step1, "email"])

        # Step 1 complete: the note says so and asks the confirm question.
        await rig.driver.user_says(U2_TYPED)
        sent = _last_input(llm)
        assert "Step 1 is complete" in sent and "shall we go to the next step?" in sent

        # "Yeah." moves the form on in the brain, before the model says a word.
        before = len(_moves(rig))
        turn = await rig.driver.user_says(U2_YES)
        check_turn(rig, turn, units=1)
        assert ("apply.next", {}) in _moves(rig)[before:]
        sent = _last_input(llm)
        assert "They said yes: the form moved on to step 2 of 5, Academics" in sent
        assert "Class 10 board, Class 10 percentage, Class 12 board" in sent

        # Step 2 in one answer, every value as the form names it.
        await rig.driver.user_says(U2_ACADEMICS)
        assert _fills(rig)[-7:] == [
            ("class10_board", "state"),
            ("class10_percent", "54"),
            ("class12_board", "state"),
            ("class12_stream", "science_pcm"),
            ("class12_status", "passed"),
            ("class12_percent", "98"),
            ("entrance_exam", "vusat"),
        ]
        result = "".join(tool_results_of(llm.captured_inputs[-1], "fill_application"))
        assert "Step 2 is complete" in result

        # Yes again: on to the programme step, with the programme they chose and
        # its only intake filled on arrival.
        before = len(_moves(rig))
        await rig.driver.user_says(U2_YES)
        assert ("apply.next", {}) in _moves(rig)[before:]
        assert _fills(rig)[-2:] == [("program", "btech-ai-ml"), ("intake", "July 2027")]
        sent = _last_input(llm)
        assert "step 3 of 5, Programme choice" in sent
        assert "campus and whether they need a hostel room" in sent

        await rig.driver.user_says(U2_CAMPUS)
        assert _fills(rig)[-3:] == [
            ("campus", "bengaluru"),
            ("hostel", "yes"),
            ("room_type", "twin_ac"),
        ]

        # "Next." moves it on too.
        before = len(_moves(rig))
        await rig.driver.user_says(U2_NEXT)
        assert ("apply.next", {}) in _moves(rig)[before:]
        assert "step 4 of 5, Documents" in _last_input(llm)


async def test_u2_a_fill_claimed_and_not_made_is_told_to_the_model() -> None:
    """Turns 15-19: "State board, noted." "Passed, noted." with an empty form."""
    llm = ScriptedOpenAI(
        {"Air past.": reply("Passed, noted. Have you taken VUSAT or JEE Main, or neither?")}
    )
    async with demo("university", llm) as rig:
        await rig.driver.start_session(init={"landing": "/apply", "lang": "en"})
        await rig.driver.user_says("Air past.")
        await rig.driver.user_says("Neither.")
        sent = _last_input(llm)
        assert 'You said "Passed, noted."' in sent and "it is NOT on their form" in sent


async def test_u2_a_step_with_something_empty_does_not_move_on() -> None:
    """A yes while the form still needs something: it stays, and the model is
    told what is missing, never that it moved."""
    llm = ScriptedOpenAI()
    async with demo("university", llm) as rig:
        await rig.driver.start_session(init={"landing": "/apply", "lang": "en"})
        await _form_reports(rig, "visitor", 1, ["full_name", "gender"])
        await rig.driver.user_says("Next.")
        assert ("apply.next", {}) not in _moves(rig)
        sent = _last_input(llm)
        assert "still needs" in sent and "date of birth" in sent


def test_u2_the_prompt_groups_questions_and_fills_with_the_tool() -> None:
    from voqalize_demos._loaded.university.prompt import system_instruction

    text = system_instruction()
    assert "ONE thing at a time" not in text
    assert "Ask for a GROUP of related details in ONE natural question" in text
    assert "{fill:" not in text and "{next}" not in text
    assert "ADMISSION is not a comparison" in text
    assert "they type them" in text


# ─── U3: quiet while the visitor browses ────────────────────────────────────


async def test_u3_a_page_opened_by_hand_gets_no_offer_of_help() -> None:
    """U1 added one offer of help seven seconds after the visitor opened a page
    by hand; it spoke into his quiet browsing, and is gone."""
    llm = ScriptedOpenAI()
    async with demo("university", llm) as rig:
        await rig.driver.start_session(init={"landing": "/programs", "lang": "en"})
        brain = rig.brain
        assert isinstance(brain, UniversityBrain)
        before = len(llm.captured_inputs)
        for route in ("/scholarships", "/campus-life", "/admissions"):
            await _hello(rig, route)
            assert brain._talk is None  # pyright: ignore[reportPrivateUsage]
        await rig.driver.user_idle()
        assert len(llm.captured_inputs) == before
        idles = [
            r.config.idle.timeout_ms
            for r in rig.driver.requests
            if isinstance(r, ConfigureFrame) and r.config.idle is not None
        ]
        assert 7000 not in idles


async def test_u2_details_for_a_later_step_wait_for_it_and_neither_exam_is_told() -> None:
    """The real-model check: with his name it also filled his Class 12 marks and
    the programme, and the form jumped to step 3 with step 1 half done. A detail
    for a later step now waits for that step. And turn 19: "Neither." went in
    as "not needed" for a B.Tech that needs VUSAT or JEE Main."""
    llm = ScriptedOpenAI(
        {
            U2_NAME: [
                call(
                    "fill_application",
                    values=[
                        {"field": "full_name", "value": "Samkeet Jain"},
                        {"field": "class12_percent", "value": "98"},
                        {"field": "program", "value": "btech-ai-ml"},
                    ],
                ),
                reply("Done. Your city and a parent's name?"),
            ],
            "Neither.": [
                call("fill_application", values=[{"field": "entrance_exam", "value": "none"}]),
                reply("This programme needs VUSAT or JEE Main: shall I put down VUSAT?"),
            ],
        }
    )
    async with demo("university", llm) as rig:
        await rig.driver.start_session(init={"landing": "/programs/btech-ai-ml", "lang": "en"})
        await _hello(rig, "/apply")
        await rig.driver.user_says(U2_NAME)
        assert _fills(rig) == [("full_name", "Samkeet Jain")]
        result = "".join(tool_results_of(llm.captured_inputs[-1], "fill_application"))
        assert "Kept for a later step" in result and "Class 12 percentage and programme" in result
        assert "step 1 of 5" in result

        # Step 1 done (the rest typed by them): "Next." moves on, and the kept
        # marks go in on arriving at step 2 (the programme waits for step 3).
        step1 = ["full_name", "date_of_birth", "gender", "mobile", "email", "city", "state"]
        await _form_reports(rig, "visitor", 1, [*step1, "parent_name"])
        await rig.driver.user_says(U2_NEXT)
        assert ("apply.next", {}) in _moves(rig)
        assert _fills(rig)[-1] == ("class12_percent", "98")
        assert ("program", "btech-ai-ml") not in _fills(rig)

        # "none" for the exam of a programme that needs one is refused, with its tests.
        await rig.driver.user_says("Neither.")
        result = "".join(tool_results_of(llm.captured_inputs[-1], "fill_application"))
        assert "NOT filled" in result and "VUSAT 2027 or JEE Main" in result
        assert ("entrance_exam", "none") not in _fills(rig)


async def test_u2_answering_the_next_steps_question_moves_the_form_on() -> None:
    """The real-model check: to "shall we go to the next step?" he answered the
    next step's question ("Banglaru, and a hostel"). With this step complete,
    that is a yes: the form moves on and the answers go in."""
    llm = ScriptedOpenAI(
        {
            U2_CAMPUS: [
                call(
                    "fill_application",
                    values=[
                        {"field": "campus", "value": "bengaluru"},
                        {"field": "hostel", "value": "yes"},
                    ],
                ),
                reply("Bengaluru with a hostel room, done."),
            ],
        }
    )
    async with demo("university", llm) as rig:
        await rig.driver.start_session(init={"landing": "/programs/btech-ai-ml", "lang": "en"})
        await _hello(rig, "/apply")
        step2 = ["class10_board", "class10_percent", "class12_board", "class12_stream"]
        done = ["full_name", "date_of_birth", "gender", "mobile", "email", "city", "state"]
        await _form_reports(
            rig, "visitor", 2, [*done, "parent_name", *step2, "class12_status", "entrance_exam"]
        )
        await rig.driver.user_says(U2_CAMPUS)
        assert ("apply.next", {}) in _moves(rig)
        assert _fills(rig) == [
            ("program", "btech-ai-ml"),
            ("campus", "bengaluru"),
            ("intake", "July 2027"),
            ("hostel", "yes"),
        ]
        result = "".join(tool_results_of(llm.captured_inputs[-1], "fill_application"))
        assert "the form moved on to step 3 of 5" in result


def test_u2_the_fill_tool_names_every_field_of_the_form() -> None:
    from typing import get_args

    from voqalize_demos._loaded.university.brain import FieldName
    from voqalize_demos._loaded.university.data import application
    from voqalize_demos._loaded.university.form import GROUPS, SAID

    names = [f.name for s in application().steps for f in s.fields]
    assert list(get_args(FieldName)) == names
    assert set(SAID) == set(names)
    assert {n for g in GROUPS.values() for grp in g for n in grp} | {"mobile", "email"} == set(
        names
    )
