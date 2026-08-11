"""The conformance MUSTs — named, reusable assertions over a driven transcript.

Each check is a plain function that raises :class:`ConformanceError` (an
``AssertionError`` subclass, so it reads naturally under pytest *and* can be
caught by the scenario runner to build a report) with a message that names the
protocol rule it enforces. Scenarios compose these; the checks themselves make
no I/O and hold no state — they read the :class:`~voqalize.conformance.driver.VoiceDriver`
observation model and :class:`~voqalize.conformance.driver.Turn` results.

The rules come straight from ``docs/voice-protocol.md``:

* **one bracket per inference** — every inference the brain opens
  (``VqlLLMFullResponseStart``) must close (``…End``) exactly once, with a
  monotone, per-interaction ``inference_id`` sequence;
* **heard-truth** — the assistant text committed to the conversation is what the
  driver *heard* (played out), never brain-generated tail past a barge-in;
* **barge-in is a drain barrier** — the brain echoes the ``InterruptionFrame``
  and **skips** ``VqlInteractionCompleted`` for the cut interaction;
* **greeting rides interaction 0**; **no proactive brain speech** outside an
  interaction the driver opened.
"""

from __future__ import annotations

from .driver import GREETING_INTERACTION_ID, InteractionObs, Turn, VoiceDriver


class ConformanceError(AssertionError):
    """A protocol MUST was violated by the brain under test."""


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise ConformanceError(msg)


# ─── bracket integrity ────────────────────────────────────────────────────────


def check_brackets_closed(turn: Turn) -> None:
    """Every opened inference bracket closed exactly once (one bracket per inference)."""
    for inf in turn.inferences:
        require(
            inf.ended,
            f"interaction {turn.interaction_id} inference {inf.inference_id}: "
            "bracket opened (VqlLLMFullResponseStart) but never closed "
            "(VqlLLMFullResponseEnd) — one-bracket-per-inference violated",
        )


def check_inference_ids_monotonic(turn: Turn, *, start: int = 1) -> None:
    """Inference ids within an interaction are strictly increasing from ``start``."""
    ids = [inf.inference_id for inf in turn.inferences]
    require(
        ids == sorted(ids) and len(set(ids)) == len(ids),
        f"interaction {turn.interaction_id}: inference ids {ids} are not strictly "
        "increasing / unique",
    )
    if ids:
        require(
            ids[0] >= start,
            f"interaction {turn.interaction_id}: first inference id {ids[0]} < {start}",
        )


def check_stamped_with_interaction(driver: VoiceDriver, turn: Turn) -> None:
    """Every recorded LLM frame for this turn carries the interaction id the driver
    opened — the brain must echo Voice's ``interaction_id``, never invent one."""
    io = driver.interactions.get(turn.interaction_id)
    require(
        io is not None,
        f"no frames observed stamped with interaction {turn.interaction_id}",
    )


# ─── completion / greeting ────────────────────────────────────────────────────


def check_completed(turn: Turn) -> None:
    require(
        turn.completed,
        f"interaction {turn.interaction_id}: brain never sent "
        "VqlInteractionCompleted for a clean turn",
    )


def check_terminates(turn: Turn) -> None:
    """Liveness: every driven interaction MUST terminate — the brain sent
    ``VqlInteractionCompleted``, or it was a barge-in the driver finalized directly.

    A turn that neither completes nor is interrupted *hung the session*: Voice waits
    on completion to unmute and accept the next user turn, so a dropped completion
    is dead air for the entire rest of the call. This is the strongest form of the
    "no dead air" rule, and it MUST hold even when the brain's own logic raised —
    the SDK core completes the interaction regardless of a brain-side exception, so
    a buggy brain degrades one turn instead of bricking the session."""
    require(
        turn.completed or turn.interrupted,
        f"interaction {turn.interaction_id}: never terminated — no "
        "VqlInteractionCompleted and no barge-in finalize. The brain hung the "
        "session; Voice stays muted waiting to unmute.",
    )


def check_spoke(turn: Turn) -> None:
    require(
        any(inf.spoke for inf in turn.inferences),
        f"interaction {turn.interaction_id}: brain produced no LLM text",
    )


def check_greeting(driver: VoiceDriver, turn: Turn | None) -> None:
    """The greeting is agent-initiated speech stamped with interaction id 0.

    It is *not* a user interaction, so it MUST NOT carry ``VqlInteractionCompleted``
    (Voice never opened it) — the requirements are: it spoke, its bracket(s)
    closed, and it used interaction 0."""
    require(turn is not None, "brain did not greet on session start")
    assert turn is not None
    require(
        turn.interaction_id == GREETING_INTERACTION_ID,
        f"greeting used interaction id {turn.interaction_id}, must be {GREETING_INTERACTION_ID}",
    )
    check_spoke(turn)
    check_brackets_closed(turn)
    require(
        not turn.completed,
        "greeting (interaction 0) carried VqlInteractionCompleted — agent-initiated "
        "speech is not a user interaction and must not be completed",
    )


# ─── barge-in / drain barrier ─────────────────────────────────────────────────


def check_interruption_echoed(driver: VoiceDriver) -> None:
    """The brain echoed an ``InterruptionFrame`` — the drain barrier that lets
    Voice resume forwarding brain output."""
    require(
        driver._interruption_seen.is_set(),
        "brain did not echo InterruptionFrame after barge-in — no drain barrier, "
        "Voice would stay muted until the fallback timeout",
    )


def check_barge_in_skips_completion(driver: VoiceDriver, turn: Turn) -> None:
    """An interaction cut *mid-generation* MUST NOT then receive
    ``VqlInteractionCompleted`` — Voice finalizes the cut inference directly instead.

    Conditional on the cut landing mid-flight, because the other barge-in is just
    as legal and far more common: generation outruns playout, so a brain routinely
    finishes a reply — and correctly completes the interaction — while the user is
    still listening to it. Interrupt that and there is no in-flight task to cancel
    and no completion to withhold; the frame is already on the wire. Asserting the
    MUST unconditionally called that a protocol violation, which is how an
    ordinary brain that emits its reply in one go was told it was non-conformant
    for behaving exactly as designed.
    """
    if turn.completed_before_cut:
        return
    io = driver.interactions.get(turn.interaction_id)
    require(
        io is not None and not io.completed,
        f"interaction {turn.interaction_id}: brain sent VqlInteractionCompleted for "
        "an interaction that was still generating when the barge-in landed — a cut "
        "interaction is finalized by Voice, not completed by the brain",
    )


def check_no_speech_after_barge_in(driver: VoiceDriver, turn: Turn, *, forbidden: str) -> None:
    """No inference in the cut interaction emitted the post-barge-in tail — the
    brain must stop generating once cancelled (heard-truth has no unheard tail)."""
    io = driver.interactions.get(turn.interaction_id)
    if io is None:
        return
    for inf in io.inferences:
        require(
            forbidden not in inf.text,
            f"interaction {turn.interaction_id} inference {inf.inference_id}: emitted "
            f"post-barge-in text {forbidden!r} — brain kept speaking after cancel",
        )


# ─── no proactive speech ──────────────────────────────────────────────────────


def check_no_unsolicited_interactions(driver: VoiceDriver, *, opened: set[int]) -> None:
    """The brain only ever stamped interactions the driver actually opened (plus the
    greeting) — no proactive/unsolicited brain-initiated interaction."""
    allowed = opened | {GREETING_INTERACTION_ID}
    seen = set(driver.interactions)
    extra = seen - allowed
    require(
        not extra,
        f"brain produced output for interaction ids {sorted(extra)} that Voice never "
        f"opened (opened={sorted(allowed)}) — no proactive brain speech allowed",
    )


# ─── deep semantics (needs a cooperating reference brain) ─────────────────────


def all_messages(state: dict) -> list[dict]:
    """The committed conversation from a backchannel dump, as ``{role, content}``
    dicts — normalized so scenarios can compare against literals."""
    messages = state.get("messages")
    require(
        isinstance(messages, list),
        "reference brain state has no 'messages' list to inspect",
    )
    assert isinstance(messages, list)
    return [{"role": m.get("role"), "content": m.get("content")} for m in messages]


def check_conversation_sequence(state: dict, *, expected: list[dict]) -> None:
    """The brain's *entire* committed conversation equals ``expected``, in order.

    This is the strongest heard-truth assertion: it pins not just the content of
    each message but the exact interleaving of user turns and assistant turns —
    the thing multi-interruption implementations most often get wrong (recording
    generated text instead of heard text, dropping a barged turn, or committing
    turns out of order)."""
    got = all_messages(state)
    require(
        got == expected,
        "committed conversation does not match heard-truth\n"
        f"  got:      {got}\n"
        f"  expected: {expected}",
    )


def check_conversation_heard(state: dict, *, expected_tail: list[dict]) -> None:
    """The brain's committed conversation ends with the expected (role, content)
    messages — proving it recorded HEARD assistant text, not generated text.

    ``expected_tail`` is a list of ``{"role": ..., "content": ...}`` the committed
    conversation must end with (exact match on the last N messages)."""
    messages = state.get("messages")
    require(
        isinstance(messages, list),
        "reference brain state has no 'messages' list to inspect",
    )
    assert isinstance(messages, list)
    n = len(expected_tail)
    tail = messages[-n:] if n else []
    require(
        tail == expected_tail,
        f"committed conversation tail {tail} != expected {expected_tail} — heard-truth "
        "not recorded correctly",
    )


def messages_of(io: InteractionObs) -> list[str]:
    """Convenience: the per-inference heard text of an interaction, in order."""
    return [inf.text for inf in io.inferences]
