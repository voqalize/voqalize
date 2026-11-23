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
        assert FEE_ASK in sent and "1 lakh 45 thousand" in sent, "the model's history came across"
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
