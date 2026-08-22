"""The conformance MUSTs — named, reusable assertions over a driven transcript.

Each check is a plain function that raises :class:`ConformanceError` (an
``AssertionError`` subclass, so it reads naturally under pytest *and* can be
caught by the scenario runner to build a report) with a message that names the
wire rule it enforces. Scenarios compose these; the checks themselves make
no I/O and hold no state — they read the :class:`~voqalize.conformance.driver.VoqalizeDriver`
observation model and :class:`~voqalize.conformance.driver.Turn` results.

The rules come straight from the wire contract — `docs/reference/wire`, and
`proto/voqalize/frames/frames.proto` under it:

* **one bracket per speech unit** — every unit the brain opens
  (``SpeechStart``) must close (``…End``) exactly once, with a monotone
  ``speech_id`` sequence;
* **heard-truth** — the assistant text committed to the conversation is what the
  driver *heard* (played out), never brain-generated tail past a barge-in;
* **barge-in is a drain barrier** — the brain echoes the ``InterruptionFrame``
  and stops generating the cut tail;
* **the greeting rides epoch 0**; **no proactive brain speech** outside a
  stimulus the driver opened.
"""

from __future__ import annotations

from .driver import GREETING_EPOCH, EpochObs, Turn, VoqalizeDriver


class ConformanceError(AssertionError):
    """A MUST of the wire was violated by the brain under test."""


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise ConformanceError(msg)


# ─── bracket integrity ────────────────────────────────────────────────────────


def check_brackets_closed(turn: Turn) -> None:
    """Every opened speech unit closed exactly once (one bracket per unit)."""
    for unit in turn.units:
        require(
            unit.ended,
            f"epoch {turn.epoch} unit {unit.speech_id}: "
            "bracket opened (SpeechStart) but never closed "
            "(SpeechEnd) — one-bracket-per-unit violated",
        )


def check_speech_ids_monotonic(turn: Turn, *, start: int = 1) -> None:
    """Speech ids within a turn are strictly increasing from ``start``. Ids are
    session-monotonic, so a later turn legitimately starts well above 1."""
    ids = [unit.speech_id for unit in turn.units]
    require(
        ids == sorted(ids) and len(set(ids)) == len(ids),
        f"epoch {turn.epoch}: speech ids {ids} are not strictly increasing / unique",
    )
    if ids:
        require(
            ids[0] >= start,
            f"epoch {turn.epoch}: first speech id {ids[0]} < {start}",
        )


def check_stamped_with_epoch(driver: VoqalizeDriver, turn: Turn) -> None:
    """Every recorded LLM frame for this turn carries the epoch the driver stamped
    the stimulus with — the brain must echo it, never invent one."""
    io = driver.epochs.get(turn.epoch)
    require(
        io is not None,
        f"no frames observed stamped with epoch {turn.epoch}",
    )


# ─── completion / greeting ────────────────────────────────────────────────────


def check_completed(turn: Turn) -> None:
    """A clean turn answered and closed every bracket it opened."""
    require(
        turn.completed,
        f"epoch {turn.epoch}: the brain opened no bracket, or left "
        "one open — a clean turn answers and closes what it opened",
    )


def check_spoke(turn: Turn) -> None:
    require(
        any(unit.spoke for unit in turn.units),
        f"epoch {turn.epoch}: brain produced no LLM text",
    )


def check_greeting(driver: VoqalizeDriver, turn: Turn | None) -> None:
    """The greeting is agent-initiated speech, and answers no stimulus — so it
    echoes epoch 0. The requirements are: it spoke, its bracket(s) closed, and it
    rode epoch 0."""
    require(turn is not None, "brain did not greet on session start")
    assert turn is not None
    require(
        turn.epoch == GREETING_EPOCH,
        f"greeting used epoch {turn.epoch}, must be {GREETING_EPOCH}",
    )
    check_spoke(turn)
    check_brackets_closed(turn)


# ─── barge-in / drain barrier ─────────────────────────────────────────────────


def check_interruption_echoed(driver: VoqalizeDriver) -> None:
    """The brain echoed an ``InterruptionFrame`` — the drain barrier that lets
    Voqalize resume forwarding brain output."""
    require(
        driver._interruption_seen.is_set(),
        "brain did not echo InterruptionFrame after barge-in — no drain barrier, "
        "Voqalize would stay muted until the fallback timeout",
    )


def check_no_speech_after_barge_in(driver: VoqalizeDriver, turn: Turn, *, forbidden: str) -> None:
    """No unit in the cut epoch emitted the post-barge-in tail — the
    brain must stop generating once cancelled (heard-truth has no unheard tail)."""
    io = driver.epochs.get(turn.epoch)
    if io is None:
        return
    for unit in io.units:
        require(
            forbidden not in unit.text,
            f"epoch {turn.epoch} unit {unit.speech_id}: emitted "
            f"post-barge-in text {forbidden!r} — brain kept speaking after cancel",
        )


# ─── no proactive speech ──────────────────────────────────────────────────────


def check_no_unsolicited_epochs(driver: VoqalizeDriver, *, opened: set[int]) -> None:
    """The brain only ever stamped epochs the driver actually opened (plus the
    greeting) — no proactive/unsolicited brain-initiated speech."""
    allowed = opened | {GREETING_EPOCH}
    seen = set(driver.epochs)
    extra = seen - allowed
    require(
        not extra,
        f"brain produced output for epochs {sorted(extra)} that Voqalize never "
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


def messages_of(io: EpochObs) -> list[str]:
    """Convenience: the per-unit heard text of one epoch, in order."""
    return [unit.text for unit in io.units]
