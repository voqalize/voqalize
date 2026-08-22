"""``_FrameworkBrain`` — the shared :class:`Brain` base every framework adapter extends.

A framework adapter (``google_adk``) wraps a
*native* agent and drives its run loop. This base owns the machinery all three share,
so the integrations can't drift and a customer subclasses one concrete adapter and
overrides ordinary methods:

* **``run_inference`` — the one primitive that invokes the underlying model.** Voqalize
  is the sole initiator: it opens an interaction and hands the brain the floor via a
  callback. ``run_inference`` is how a brain *spends* that floor — it drives one real
  model turn, bracketed under the interaction, with the no-dead-air guarantee and the
  turn watchdog (see :func:`~voqalize._framework.turn.run_turn`). It **requires** a
  live, floor-owning interaction, which is the whole discipline: you invoke the model
  only when Voqalize has handed you the floor, never out of turn.
* **``on_interaction`` = ``run_inference`` over the user's utterance.** The user
  stopped speaking, so the default response is to run the model on what they said.
* **``on_user_idle`` / ``on_client_message`` default to nothing.** Voqalize mints an
  interaction, hands over the idle escalation as *data* (idle) or delivers the raw
  client message with a pre-minted id (client message), and the brain decides — at
  its own discretion — whether to respond. Doing nothing is a valid choice; to
  respond, override the method and call ``run_inference(interaction, message)`` with
  whatever stimulus you choose to feed the model (on a client message, take the floor
  via ``message.interaction``). The SDK never synthesizes a prompt or drives the model
  on your behalf — it only delivers the data and a floor-owning interaction id.

It also owns the two adapter-internal behaviours once — the conformance-dump
backchannel answer (``answer_conformance_dump``) and the error-frame warning log
(keyed by the adapter's ``name``). Subclasses implement :meth:`_drive` (run one native
model turn from ``message`` + prior history) and their own ``on_session_start`` /
``on_inference_finalized``; every other Brain seam is inherited here and overridable as
an ordinary method (``on_client_message`` / ``on_session_end`` / ``on_error`` /
``on_resume`` / ``on_user_idle``).

Framework-agnostic: nothing here imports ADK / genai / openai.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

from ..sdk.brain import Brain, Session
from ..sdk.wire import ErrorFrame
from .turn import DEFAULT_ERROR_FALLBACK, DEFAULT_TURN_TIMEOUT, run_turn

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ..sdk.brain import ClientMessage, Interaction, Message, SessionStart

__all__ = ["STATE_SYNC", "_FrameworkBrain"]

# The client-message type a browser uses to push its own state to the brain. A
# convention, not protocol: Voqalize never interprets a client message, and a UI is free to
# use another name (handle it in your own ``on_client_message``). Every Voqalize
# screen-driving demo sends this one, so the adapters handle it out of the box.
STATE_SYNC = "state_sync"


def _answer_conformance_dump(session: Session, message: ClientMessage) -> bool:
    """Answer the conformance harness's backchannel dump with the framework-owned
    committed conversation (a pure function of ``Session``). Returns ``True`` if it
    handled the message, so the caller can stop. Real UIs never send this message, so
    answering it is harmless in production; the imports stay lazy so the conformance
    package never loads on the hot path."""
    from voqalize.conformance.driver import (
        CONFORMANCE_DUMP_EVENT,
        CONFORMANCE_STATE_ACTION,
    )
    from voqalize.conformance.reference import conformance_state

    if message.type == CONFORMANCE_DUMP_EVENT:
        session.action(CONFORMANCE_STATE_ACTION, conformance_state(session))
        return True
    return False


class _FrameworkBrain(Brain):
    """Base for the framework adapters (extend a concrete subclass, not this).

    Owns ``run_inference`` (the gated model-invocation primitive), the default
    ``on_interaction`` (run the model on the user's utterance), and the two
    adapter-internal seams (the conformance-dump answer; the error log). Subclasses
    call ``super().__init__(name=..., answer_conformance_dump=..., error_fallback=...,
    turn_timeout=...)`` and implement :meth:`_drive` + ``on_session_start`` +
    ``on_inference_finalized`` to drive their native runner."""

    def __init__(
        self,
        *,
        name: str,
        answer_conformance_dump: bool = False,
        error_fallback: str | None = DEFAULT_ERROR_FALLBACK,
        turn_timeout: float | None = DEFAULT_TURN_TIMEOUT,
    ) -> None:
        self._name = name
        self._answer_conformance_dump = answer_conformance_dump
        # The browser's own latest snapshot of what the user is looking at — see
        # ``on_client_message`` / the ``state_sync`` convention.
        self.browser_state: dict[str, Any] | None = None
        # Shared by run_inference on every trigger (user / idle / app event): the
        # no-dead-air fallback line and the whole-turn watchdog.
        self._error_fallback = error_fallback
        self._turn_timeout = turn_timeout

    # ─── invoking the model ────────────────────────────────────────────────────

    async def run_inference(self, interaction: Interaction, message: str | None = None) -> None:
        """Invoke the underlying model as this interaction's response — the one
        primitive that spends the floor.

        Drives exactly one native model turn (streamed speech, one inference bracket
        per model call, tool round-trips) bracketed under ``interaction``, inside the
        turn's ``voice()`` context, under the no-dead-air guarantee and the
        ``turn_timeout`` watchdog.

        ``message`` is the input fed to the model for *this* turn: the user's utterance
        on ``on_interaction``, or whatever stimulus you choose to bundle on idle / a
        client message (the escalation level, the message payload — your wording). It
        reaches the *model* only; it is **not** recorded into ``session.conversation``
        as a heard-truth user turn (on idle / a client message nothing was actually
        said aloud). ``message=None`` re-runs the model over the existing history with
        no new input.

        Best practice is to call it only while you hold a **live, floor-owning**
        interaction — the exact one a floor-owning callback (``on_interaction`` /
        ``on_user_idle``, or ``message.interaction`` inside ``on_client_message``) was
        just handed. Calling it with a stale or foreign interaction logs a warning and
        proceeds anyway (talking out of turn is discouraged, not forbidden — the brain
        owns that decision)."""
        # The floor-owning interactions are exactly those the adapter is still running
        # (registered before its callback runs, popped when it returns). An id absent
        # from that set is stale (its turn finished) or foreign — invoking the model
        # from it is talking out of turn. That's a best-practice violation, not a hard
        # error: the brain may legitimately choose to respond to a client message it
        # never materialized into a floor. Warn loudly and proceed.
        if interaction.id not in interaction._proc._pending:
            logger.warning(
                "{}: run_inference called outside a live, floor-owning interaction "
                "({}) — talking out of turn. Prefer responding only from the "
                "interaction handed to on_interaction / on_user_idle / "
                "on_client_message.",
                self._name,
                interaction.id,
            )
        await run_turn(
            interaction,
            lambda: self._drive(interaction, message),
            error_fallback=self._error_fallback,
            turn_timeout=self._turn_timeout,
        )

    async def _drive(self, interaction: Interaction, message: str | None) -> None:
        """Run one native model turn: feed ``message`` (when not ``None``) as this
        turn's input, render the model's history, stream its reply as speech (one
        ``interaction.say()`` bracket per model call), and dispatch its tools. Each
        adapter implements this against its own framework."""
        raise NotImplementedError

    async def on_interaction(self, interaction: Interaction) -> None:
        # The user stopped speaking: respond by running the model on what they said.
        await self.run_inference(interaction, interaction.transcript)

    # ─── resume (overridable; default = a fresh conversation) ──────────────────

    async def on_resume(self, session: Session, start: SessionStart) -> Sequence[Message]:
        """Resume a **logical conversation onto this new WebSocket session**.

        A voice session is one socket, but a logical conversation may span several (a
        dropped call reconnects, a caller phones back). Read your **own** stable
        identifier from ``start.init`` (the opaque ``SessionStart`` payload), load that
        conversation from your **own** store, and return its messages; the adapter
        seeds them as heard-truth history so the first prompt already carries prior
        context, and skips the cold greeting (a resumed call is a continuation).

        Default: return nothing — a genuinely fresh conversation. The SDK persists
        nothing and interprets no identifier; only spoken text crosses the boundary
        (reload domain state your tools need from your own store)."""
        return []

    # ─── the two adapter-internal seams (overridable) ──────────────────────────

    async def on_client_message(self, session: Session, message: ClientMessage) -> None:
        """A browser-originated client message (Voqalize never interprets it).

        Two things are handled by default:

        * **``state_sync`` — the browser-snapshot convention.** A screen-driving UI
          pushes its own state on connect and after every change (including edits the
          *user* made by hand); the payload is kept on :attr:`browser_state`, replacing
          the previous one. **No floor is taken** — ``message.interaction`` is left
          untouched, so a screen change never makes the agent talk. Read it from a tool,
          or fold it into every prompt by returning it from
          :meth:`~voqalize.google_adk.AdkBrain.grounding`.
        * the conformance backchannel (test/CI only, when ``answer_conformance_dump``
          is on).

        Override to react to your own message types — update state / append to history
        with ``session.action(...)``, or spend the floor and respond by calling
        ``run_inference(message.interaction, ...)``. Call
        ``super().on_client_message(...)`` to keep the two defaults above."""
        if message.type == STATE_SYNC:
            # Replace, don't merge: the browser sends a complete snapshot, and a merge
            # would resurrect rows the user just deleted.
            self.browser_state = dict(message.data) if message.data else None
            return
        if self._answer_conformance_dump and _answer_conformance_dump(session, message):
            return

    async def on_error(self, session: Session, error: ErrorFrame) -> None:
        """Non-fatal runtime signal (e.g. a backpressure drop). Default: log it.
        Override for your own handling; call ``super().on_error(...)`` to keep the
        log."""
        logger.warning("{}: runtime error frame: {}", self._name, error)
