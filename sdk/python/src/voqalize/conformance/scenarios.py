"""The scenario catalog — named wire exercises the driver runs against a brain.

Each :class:`Scenario` drives a fresh session (or two) via a
:class:`ScenarioContext` and asserts the relevant MUSTs from :mod:`.checks`. A
scenario that returns cleanly *passed*; a scenario that raises
:class:`~voqalize.conformance.checks.ConformanceError` (or any exception)
*failed* — the runner in :mod:`.report` turns that into a
:class:`~voqalize.conformance.report.ScenarioResult`.

Two tiers, per the depth decision (both, layered):

* **wire-level** (``requires_reference=False``) — greeting, turns, bracket
  integrity, auth. These work against *any* brain that speaks the wire, so they
  can be pointed at a shipped brain (``welcome`` / ``travel``).
* **deep-semantics** (``requires_reference=True``) — heard-truth reconciliation,
  barge-in, action-outcome round-trips, app-event delivery. These need a
  cooperating brain that echoes its committed state (see :mod:`.reference`), and
  speak the command grammar defined there. Barge-in belongs here despite being a
  wire concern: cutting a reply mid-flight needs a reply still in flight, which is
  what the grammar's ``count slowly`` guarantees and an ordinary brain does not.

The tier a brain can't run is **skipped and reported**, never failed and never
dropped — :func:`~voqalize.conformance.report.run_suite` probes for the grammar
and says in the verdict how much of the catalog it covered.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from . import checks
from .driver import VoiceDriver
from .reference import (
    BARGE_SENTINEL,
    COUNT_SLOWLY,
    DO_PREFIX,
    GREETING_TEXT,
    IDLE_NUDGE,
    RAISE,
    SAY_PREFIX,
    SILENT_PREFIX,
    SPEAK_RAISE_PREFIX,
    STORY_PREFIX,
    TWO,
    TWO_FIRST,
    TWO_SECOND,
    story_opening,
)
from .wire_voice import DirectConnection, mint_voice_token


class ScenarioContext:
    """Mints conformance drivers against one brain under test.

    A fresh context is used per scenario (see :func:`.report.run_suite`), so
    ``aclose`` tears down exactly that scenario's sessions."""

    def __init__(
        self,
        brain_url: str,
        *,
        private_key_pem: bytes | None,
        agent_id: str = "agent_conformance",
        tenant_id: str = "tenant_conformance",
        default_timeout: float = 5.0,
    ) -> None:
        self.brain_url = brain_url
        self.private_key_pem = private_key_pem
        self.agent_id = agent_id
        self.tenant_id = tenant_id
        self.default_timeout = default_timeout
        self._drivers: list[VoiceDriver] = []

    def new_session_id(self) -> str:
        return f"conf-{uuid.uuid4().hex[:12]}"

    async def connect(
        self,
        *,
        auth: str = "valid",
        session_id: str | None = None,
        sign_with: bytes | None = None,
    ) -> VoiceDriver:
        """Open a driver against the brain.

        ``auth``: ``"valid"`` mints a well-formed token signed by ``sign_with`` (or
        the context private key); ``"none"`` sends no ``Authorization`` header;
        any other value is used verbatim as the bearer token (for malformed-token
        cases)."""
        sid = session_id or self.new_session_id()
        if auth == "valid":
            key = sign_with or self.private_key_pem
            if key is None:
                token: str | None = None
            else:
                token = mint_voice_token(
                    private_key_pem=key,
                    session_id=sid,
                    agent_id=self.agent_id,
                    tenant_id=self.tenant_id,
                )
        elif auth == "none":
            token = None
        else:
            token = auth
        conn = DirectConnection(self.brain_url, sid, token=token)
        driver = VoiceDriver(
            conn,
            session_id=sid,
            default_timeout=self.default_timeout,
        )
        await driver.open()
        self._drivers.append(driver)
        return driver

    async def aclose(self) -> None:
        for driver in self._drivers:
            await driver.aclose()
        self._drivers.clear()


@dataclass
class Scenario:
    """One named wire exercise."""

    name: str
    description: str
    run: Callable[[ScenarioContext], Awaitable[None]]
    requires_reference: bool = False
    tags: tuple[str, ...] = field(default_factory=tuple)


# ─── wire-level scenarios (work against any brain) ────────────────────────────


async def scn_greeting(ctx: ScenarioContext) -> None:
    driver = await ctx.connect()
    greeting = await driver.start_session()
    checks.check_greeting(driver, greeting)


async def scn_single_turn(ctx: ScenarioContext) -> None:
    driver = await ctx.connect()
    await driver.start_session()
    turn = await driver.user_says("hello there")
    checks.check_spoke(turn)
    checks.check_completed(turn)
    checks.check_brackets_closed(turn)
    checks.check_speech_ids_monotonic(turn)
    checks.check_stamped_with_epoch(driver, turn)


async def scn_multi_turn(ctx: ScenarioContext) -> None:
    driver = await ctx.connect()
    await driver.start_session()
    first = await driver.user_says("first question")
    second = await driver.user_says("second question")
    for turn in (first, second):
        checks.check_completed(turn)
        checks.check_brackets_closed(turn)
    # Epochs are session-monotonic and distinct across turns.
    checks.require(
        second.epoch > first.epoch,
        f"second epoch {second.epoch} not greater than first "
        f"{first.epoch} — epochs must be session-monotonic",
    )
    checks.check_no_unsolicited_epochs(driver, opened={first.epoch, second.epoch})


async def scn_two_units_one_turn(ctx: ScenarioContext) -> None:
    """One epoch, two speech units — one-bracket-per-unit and
    per-epoch monotone speech ids. (Reference grammar: ``two``.)"""
    driver = await ctx.connect()
    await driver.start_session()
    turn = await driver.user_says(TWO)
    checks.check_completed(turn)
    checks.check_brackets_closed(turn)
    checks.check_speech_ids_monotonic(turn)
    checks.require(
        len(turn.units) == 2,
        f"expected 2 units for a two-unit turn, saw {len(turn.units)}",
    )
    texts = [unit.text for unit in turn.units]
    checks.require(
        texts == [TWO_FIRST, TWO_SECOND],
        f"two-unit texts {texts} != {[TWO_FIRST, TWO_SECOND]}",
    )


async def scn_barge_in(ctx: ScenarioContext) -> None:
    """Barge-in mid-response: the brain echoes the InterruptionFrame drain barrier
    and stops emitting the cut tail.
    (Reference grammar: ``count slowly`` — a long response with a cuttable tail.)"""
    driver = await ctx.connect()
    await driver.start_session()
    turn = await driver.barge_in(COUNT_SLOWLY)
    checks.check_interruption_echoed(driver)
    checks.check_no_speech_after_barge_in(driver, turn, forbidden=BARGE_SENTINEL)


async def scn_brain_error_isolated(ctx: ScenarioContext) -> None:
    """A brain fault costs exactly one turn. ``on_user_message`` raises before
    speaking a word: that turn is silent — the honest outcome, nothing was
    generated — but it MUST leave no bracket open and MUST NOT take the session
    with it, so the very next user turn answers normally. (Reference grammar:
    ``raise``.)

    This is a *core* guarantee, so every brain built on the SDK inherits it; the
    reference brain just gives us a deterministic way to trigger the fault."""
    driver = await ctx.connect()
    await driver.start_session()
    faulted = await driver.user_says(RAISE, timeout=3.0)
    checks.check_brackets_closed(faulted)

    recovered = await driver.user_says("are you still there")
    checks.check_spoke(recovered)
    checks.check_completed(recovered)
    checks.check_brackets_closed(recovered)
    checks.check_no_unsolicited_epochs(driver, opened={faulted.epoch, recovered.epoch})


async def scn_brain_error_after_speech_keeps_heard(ctx: ScenarioContext) -> None:
    """A brain that speaks and *then* raises: the bracket still closes, and the
    heard-truth spoken before the fault is committed to the conversation (the fault
    truncates the turn, it does not erase what the user already heard).
    (Reference grammar: ``speak then raise <text>``.)"""
    driver = await ctx.connect()
    await driver.start_session()
    turn = await driver.user_says(f"{SPEAK_RAISE_PREFIX}acknowledged", timeout=3.0)
    checks.check_completed(turn)
    checks.check_spoke(turn)
    checks.check_brackets_closed(turn)
    state = await driver.dump_conversation()
    checks.check_conversation_heard(
        state,
        expected_tail=[
            {"role": "user", "content": f"{SPEAK_RAISE_PREFIX}acknowledged"},
            {"role": "assistant", "content": "acknowledged"},
        ],
    )


async def scn_reject_bad_token(ctx: ScenarioContext) -> None:
    """A token signed by the wrong key is rejected with close code 4000, before
    any session work — the brain verifies ``aud=brain`` against its configured key."""
    from .wire_voice import generate_keypair

    wrong = generate_keypair()
    driver = await ctx.connect(auth="valid", sign_with=wrong.private_pem)
    code = await driver.wait_closed(timeout=3.0)
    checks.require(
        code == 4000,
        f"brain accepted a wrong-key token (close code {code!r}, expected 4000) — "
        "auth MUST reject a token it can't verify",
    )


# ─── deep-semantics scenarios (need a cooperating reference brain) ─────────────


async def scn_heard_truth_conversation(ctx: ScenarioContext) -> None:
    """The committed conversation records HEARD assistant text, in order:
    greeting, then the user turn, then the assistant's heard reply."""
    driver = await ctx.connect()
    await driver.start_session()
    await driver.user_says(f"{SAY_PREFIX}banana")
    state = await driver.dump_conversation()
    checks.check_conversation_heard(
        state,
        expected_tail=[
            {"role": "assistant", "content": GREETING_TEXT},
            {"role": "user", "content": f"{SAY_PREFIX}banana"},
            {"role": "assistant", "content": "banana"},
        ],
    )


async def scn_heard_truth_barge_in(ctx: ScenarioContext) -> None:
    """After a barge-in, the committed assistant message is the partial HEARD
    text — never the generated tail past the cut."""
    driver = await ctx.connect()
    await driver.start_session()
    turn = await driver.barge_in(COUNT_SLOWLY)
    checks.check_interruption_echoed(driver)
    state = await driver.dump_conversation()
    messages = state.get("messages", [])
    assistant = [m for m in messages if m.get("role") == "assistant"]
    checks.require(
        bool(assistant) and BARGE_SENTINEL not in assistant[-1].get("content", ""),
        f"barged-in assistant message committed the un-heard tail: {assistant[-1:]}",
    )
    # And the heard prefix the driver finalized is what got recorded.
    heard = turn.units[-1].text if turn.units else ""
    checks.require(
        assistant[-1].get("content", "") == heard,
        f"committed heard {assistant[-1].get('content')!r} != driver-finalized "
        f"heard-truth {heard!r}",
    )


async def scn_heard_truth_multi_interruption(ctx: ScenarioContext) -> None:
    """The manual barge-in stress test, mechanized: ask for a story, interrupt it
    with a correction, interrupt *that* with another correction, then let the last
    one finish. Assert — via the backchannel — that the conversation the brain
    would send to the LLM interleaves each user correction with the PARTIAL HEARD
    text of the assistant turn it cut: never the generated-but-unheard tail, never
    a dropped turn, never mis-ordered.

    This is the single place implementations most often go wrong. A brain that
    appends what the model *generated* (the full story) instead of what actually
    *played* (the opening, cut mid-sentence) hands the LLM a transcript that
    disagrees with what the human heard — and every subsequent turn compounds the
    divergence."""
    driver = await ctx.connect()
    await driver.start_session()

    # "Tell me the Beanstalk story" → interrupt: "no, Jack and Jill" → interrupt:
    # "no, the Giant Killer" → let it finish.
    a = await driver.barge_in(f"{STORY_PREFIX}beanstalk")
    b = await driver.barge_in(f"{STORY_PREFIX}jack and jill")
    c = await driver.user_says(f"{STORY_PREFIX}giant killer")

    # Each interruption was a proper drain barrier: echoed by the brain.
    checks.check_interruption_echoed(driver)

    # The two cut turns committed exactly the deterministic heard opening — the
    # driver dictated the heard-truth, so this is an exact-string assertion.
    checks.require(
        a.heard == story_opening("beanstalk"),
        f"first cut turn heard-truth {a.heard!r} != {story_opening('beanstalk')!r}",
    )
    checks.require(
        b.heard == story_opening("jack and jill"),
        f"second cut turn heard-truth {b.heard!r} != {story_opening('jack and jill')!r}",
    )
    for turn in (a, b):
        checks.require(
            BARGE_SENTINEL not in (turn.heard or ""),
            f"cut turn committed the un-heard tail: {turn.heard!r}",
        )
    # The final, un-interrupted answer WAS fully heard (tail present).
    checks.require(
        BARGE_SENTINEL in c.text,
        f"final un-interrupted turn dropped its tail: {c.text!r}",
    )

    # The whole committed history, in order — the exact transcript the LLM sees.
    state = await driver.dump_conversation()
    checks.check_conversation_sequence(
        state,
        expected=[
            {"role": "assistant", "content": GREETING_TEXT},
            {"role": "user", "content": f"{STORY_PREFIX}beanstalk"},
            {"role": "assistant", "content": a.heard},
            {"role": "user", "content": f"{STORY_PREFIX}jack and jill"},
            {"role": "assistant", "content": b.heard},
            {"role": "user", "content": f"{STORY_PREFIX}giant killer"},
            {"role": "assistant", "content": c.text},
        ],
    )


async def scn_heard_truth_barge_in_before_audio(ctx: ScenarioContext) -> None:
    """Barge-in *before any audio plays*: nothing was heard, so a conformant brain
    commits NO assistant message for that epoch — not an empty one, not the
    generated text. The user turn is still recorded. (A brain that records an
    empty or generated assistant turn here corrupts the transcript just as badly
    as the mid-story case.)"""
    driver = await ctx.connect()
    await driver.start_session()
    turn = await driver.barge_in(f"{SILENT_PREFIX}nothing", wait_for_speech=False, speak_delay=0.15)
    checks.check_interruption_echoed(driver)
    checks.require(
        turn.heard in (None, ""),
        f"expected empty heard-truth for a pre-audio barge-in, got {turn.heard!r}",
    )
    state = await driver.dump_conversation()
    checks.check_conversation_sequence(
        state,
        expected=[
            {"role": "assistant", "content": GREETING_TEXT},
            {"role": "user", "content": f"{SILENT_PREFIX}nothing"},
        ],
    )


async def scn_action_result_roundtrip(ctx: ScenarioContext) -> None:
    """The brain fires a UI action; the driver reports its outcome; the brain
    correlates it by action_id at session scope. (Reference grammar: ``do X``.)"""
    driver = await ctx.connect()
    await driver.start_session()
    turn = await driver.user_says(f"{DO_PREFIX}open_panel")
    checks.check_completed(turn)
    commands = await driver.collect_ui_commands(min_count=1)
    fired = [c for c in commands if c.get("action") == "open_panel"]
    checks.require(
        len(fired) == 1,
        f"expected exactly one 'open_panel' ui_command, saw {len(fired)}",
    )
    action_id = fired[0].get("action_id")
    checks.require(
        isinstance(action_id, int),
        f"ui_command action_id {action_id!r} is not an int",
    )
    assert isinstance(action_id, int)  # narrowed by the check above
    await driver.send_action_result(action_id, status="ok", result={"done": True})
    state = await driver.dump_conversation()
    outcomes = state.get("outcomes", [])
    matched = [o for o in outcomes if o.get("action_id") == action_id]
    checks.require(
        len(matched) == 1 and matched[0].get("status") == "ok",
        f"brain did not correlate the action outcome for action_id {action_id}: {outcomes}",
    )


async def scn_browser_message_delivery(ctx: ScenarioContext) -> None:
    """A browser message the brain does not respond to still reaches
    ``on_browser_message`` (the update-internal-state path)."""
    driver = await ctx.connect()
    await driver.start_session()
    await driver.send_browser_message("state_sync", {"page": "checkout"})
    state = await driver.dump_conversation()
    events = state.get("browser_messages", [])
    matched = [e for e in events if e.get("name") == "state_sync"]
    checks.require(
        len(matched) == 1 and matched[0].get("data") == {"page": "checkout"},
        f"browser message 'state_sync' not delivered to the brain: {events}",
    )


async def scn_user_idle(ctx: ScenarioContext) -> None:
    """The idle trigger: Voice opens an epoch because the user went silent
    (``UserIdle``), the brain's ``on_user_idle`` re-engages, and the epoch
    plays out and completes exactly like a spoken turn — with the escalation level
    carried through. Crucially, the committed conversation records the assistant
    nudge but **no user turn** (nothing was said), so idle re-engagement never
    pollutes the faithful transcript with a phantom utterance."""
    driver = await ctx.connect()
    await driver.start_session()
    turn = await driver.user_idle(level=2, idle_ms=30000)
    checks.check_spoke(turn)
    checks.check_completed(turn)
    checks.check_brackets_closed(turn)
    checks.require(
        turn.text == f"{IDLE_NUDGE} 2",
        f"idle nudge {turn.text!r} != {f'{IDLE_NUDGE} 2'!r} (escalation level not carried?)",
    )
    state = await driver.dump_conversation()
    checks.check_conversation_sequence(
        state,
        expected=[
            {"role": "assistant", "content": GREETING_TEXT},
            {"role": "assistant", "content": f"{IDLE_NUDGE} 2"},
        ],
    )


async def scn_browser_message_never_speaks(ctx: ScenarioContext) -> None:
    """A browser message never takes the floor. Voice delivers it to
    ``on_browser_message``, which may render but not speak — so no matter what the
    brain does with it, the committed transcript gains nothing. Nothing about a
    click means the human stopped talking, and a brain that answered one would be
    talking over them."""
    driver = await ctx.connect()
    await driver.start_session()
    before = await driver.dump_conversation()
    await driver.send_browser_message("form_submitted", {"field": "email"})
    after = await driver.dump_conversation()
    checks.require(
        after.get("messages") == before.get("messages"),
        f"a browser message changed the transcript: {before.get('messages')} → "
        f"{after.get('messages')}",
    )


# ─── the catalog ──────────────────────────────────────────────────────────────

CATALOG: list[Scenario] = [
    Scenario("greeting", "Brain greets on session start (epoch 0).", scn_greeting),
    Scenario(
        "single_turn", "One user turn: spoken, completed, one closed bracket.", scn_single_turn
    ),
    Scenario(
        "multi_turn",
        "Two turns with monotone epochs, no proactive speech.",
        scn_multi_turn,
    ),
    Scenario(
        "two_units_one_turn",
        "One turn, two speech units with monotone speech ids.",
        scn_two_units_one_turn,
        requires_reference=True,
    ),
    Scenario(
        "barge_in",
        "Barge-in drain barrier: echo, skip completion, cut the tail.",
        scn_barge_in,
        requires_reference=True,
    ),
    Scenario(
        "brain_error_isolated",
        "A raising brain costs one turn; the next turn answers normally.",
        scn_brain_error_isolated,
        requires_reference=True,
        tags=("fault",),
    ),
    Scenario(
        "brain_error_after_speech_keeps_heard",
        "Speak-then-raise: the bracket closes and heard text is committed.",
        scn_brain_error_after_speech_keeps_heard,
        requires_reference=True,
        tags=("fault",),
    ),
    Scenario(
        "reject_bad_token",
        "Wrong-key token is rejected with close code 4000.",
        scn_reject_bad_token,
        tags=("auth",),
    ),
    Scenario(
        "heard_truth_conversation",
        "Committed conversation is HEARD text, in order.",
        scn_heard_truth_conversation,
        requires_reference=True,
    ),
    Scenario(
        "heard_truth_barge_in",
        "Barged-in assistant message is the partial heard text, not the tail.",
        scn_heard_truth_barge_in,
        requires_reference=True,
    ),
    Scenario(
        "heard_truth_multi_interruption",
        "Story → interrupt → interrupt → finish: history interleaves partial "
        "heard turns in order (the classic implementation trap).",
        scn_heard_truth_multi_interruption,
        requires_reference=True,
        tags=("interruption",),
    ),
    Scenario(
        "heard_truth_barge_in_before_audio",
        "Barge-in before any audio: no assistant message committed, user turn kept.",
        scn_heard_truth_barge_in_before_audio,
        requires_reference=True,
        tags=("interruption",),
    ),
    Scenario(
        "action_result_roundtrip",
        "UI action fired by the brain; outcome correlated by action_id.",
        scn_action_result_roundtrip,
        requires_reference=True,
    ),
    Scenario(
        "browser_message_delivery",
        "A non-responding browser message reaches on_browser_message.",
        scn_browser_message_delivery,
        requires_reference=True,
    ),
    Scenario(
        "user_idle",
        "Idle trigger opens an epoch; on_user_idle re-engages, no phantom user turn recorded.",
        scn_user_idle,
        requires_reference=True,
        tags=("initiation",),
    ),
    Scenario(
        "browser_message_never_speaks",
        "A browser message is delivered but never takes the floor.",
        scn_browser_message_never_speaks,
        requires_reference=True,
        tags=("initiation",),
    ),
]


# There is deliberately no `catalog(include_reference=…)` that returns a filtered
# copy. Answering "this brain can't run the deep tier" by handing back a shorter
# list is how a run of four scenarios comes to print a bare CONFORMANT. Selection
# belongs inside `run_suite`, which records what it left out: a filtered catalog
# is the one shape that must not exist next to a report that refuses to shrink
# silently.
