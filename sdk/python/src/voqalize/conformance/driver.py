"""``VoiceDriver`` — a protocol-compliant impersonation of PyGato/Voice, seen
from a brain's point of view.

The driver *is* the "compliant voqalize": it dials a brain over the single
session ``/s/{session_id}`` leg, speaks the shipped protobuf wire, and plays out
the brain's responses the way real Voice does — auto-finalizing each inference
with a *heard-truth* transcript, honouring the barge-in drain barrier, and
acking nothing of its own (its outbound data frames carry ``request_id>0``; the
brain's outbound frames carry ``request_id=0`` and are never blocked on the
driver). Everything the brain sends back is decoded, timestamped, and recorded
so scenarios can assert the protocol MUSTs against a structured transcript.

Turns end the way they end on a real call: the wire carries no "the brain is
done" frame, so a turn is over when every inference bracket it opened has closed
and the brain has gone quiet. Real Voice has no more than that either.

What the driver deliberately does *not* do: audio, VAD, STT/TTS, WebRTC. Playout
is modelled as "the whole inference is heard unless barged in", which is all the
protocol conformance surface needs.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from dataclasses import dataclass, field

from websockets.exceptions import ConnectionClosed

from voqalize.sdk.wire import (
    CancelFrame,
    ClientMessageFrame,
    EndFrame,
    ErrorFrame,
    FinalizeReason,
    Frame,
    InferenceFinalizedFrame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    ServerMessageFrame,
    SessionStartFrame,
    UpdateIdleSettingsFrame,
    UpdateSTTSettingsFrame,
    UpdateTTSSettingsFrame,
    UserIdleFrame,
    UserMessageFrame,
)
from voqalize.sdk.wire.serializer import CortexFrameSerializer, DecodedMessage

from .wire_pygato import DirectConnection

# The greeting interaction: the brain speaks first on session start, with no
# user turn to attribute it to. Agent-initiated speech echoes no epoch, so it
# lands on 0.
GREETING_INTERACTION_ID = 0

# ─── the conformance backchannel ─────────────────────────────────────────────
#
# The wire deliberately never carries the brain's *committed* conversation — the
# brain only ever sends inference *output* frames, so heard-truth (what the brain
# recorded for the LLM) is not observable from the wire alone. There is no
# history-request frame, and we do not add one: the wire stays frozen.
#
# Instead the driver reuses the generic, schema-free client-message lane the
# protocol already has (browser→brain ``ClientMessage`` / brain→browser
# ``ServerMessage``, the same lane real UIs use for ``ui_command`` /
# ``action_result`` — opaque to Voice, which just relays it). A conformance-aware
# brain opts in by answering one namespaced client message with its committed state.
# Because the SDK *owns* ``session.conversation``, that answer can be produced by
# the framework once (see ``reference.conformance_state``) and every brain built
# on the SDK inherits it — the customer's brain code writes nothing.
CONFORMANCE_DUMP_EVENT = "__voqal.conformance.dump"
CONFORMANCE_STATE_ACTION = "__voqal.conformance.state"

# Frames the driver sends that carry request_id>0 (ack-gated data frames), vs.
# system/control frames it sends with request_id=0 (urgent, never ack-gated) —
# mirroring PyGato: only wire-vocab *data* frames are ack-gated.
_ACK_GATED = (
    UserMessageFrame,
    UserIdleFrame,
    ClientMessageFrame,
    InferenceFinalizedFrame,
)


@dataclass
class Recorded:
    """One brain→pygato frame, timestamped on the driver's monotonic clock."""

    frame: Frame
    t: float


@dataclass
class InferenceObs:
    """The driver's observation of a single inference bracket (brain output)."""

    inference_id: int
    started_t: float
    ended: bool = False
    ended_t: float | None = None
    texts: list[str] = field(default_factory=list)
    text_times: list[float] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "".join(self.texts)

    @property
    def spoke(self) -> bool:
        return bool(self.texts)


@dataclass
class InteractionObs:
    """The driver's observation of one interaction (0 = greeting, else a user turn)."""

    interaction_id: int
    inferences: list[InferenceObs] = field(default_factory=list)
    finalized: set[int] = field(default_factory=set)

    @property
    def completed(self) -> bool:
        """Every bracket the brain opened for this turn, it closed. The wire has
        no end-of-turn frame; this is what "the brain finished" means."""
        return bool(self.inferences) and all(inf.ended for inf in self.inferences)

    def inference(self, inference_id: int) -> InferenceObs | None:
        for inf in self.inferences:
            if inf.inference_id == inference_id:
                return inf
        return None


@dataclass
class Turn:
    """The result of one driven turn (a ``user_says`` or ``barge_in``)."""

    interaction_id: int
    inferences: list[InferenceObs]
    completed: bool
    interrupted: bool = False
    # For a barge-in: the partial heard-truth the driver finalized the cut
    # inference with (what the user actually heard before the interruption).
    # ``""`` means the barge landed before any audio played; ``None`` means the
    # turn was not a barge-in (or no inference was open to cut).
    heard: str | None = None

    @property
    def text(self) -> str:
        return " ".join(inf.text for inf in self.inferences if inf.spoke)


class VoiceDriver:
    """Drives a brain over one direct session, impersonating PyGato/Voice.

    Typical lifecycle::

        driver = VoiceDriver(conn, session_id=sid, agent_id=aid)
        await driver.open()
        await driver.start_session()          # brain greets
        turn = await driver.user_says("hi")   # a user turn, auto-finalized
        await driver.end_session()
        await driver.aclose()
    """

    def __init__(
        self,
        conn: DirectConnection,
        *,
        session_id: str,
        agent_id: str,
        default_timeout: float = 5.0,
        quiet_for: float = 0.25,
    ) -> None:
        self._conn = conn
        self.session_id = session_id
        self.agent_id = agent_id
        self.default_timeout = default_timeout
        self.quiet_for = quiet_for
        self._ser = CortexFrameSerializer()

        self._req = 0
        self._interaction_seq = 0

        # Recorded / decoded brain output.
        self.log: list[Recorded] = []
        self.acks: list[int] = []
        self.ui_commands: list[dict] = []
        self.errors: list[ErrorFrame] = []
        self.stt_settings: list[dict] = []
        self.tts_settings: list[dict] = []
        self.idle_settings: list[dict] = []
        self.interactions: dict[int, InteractionObs] = {}

        # Wakeups and lifecycle signalling.
        self._tick = asyncio.Event()
        self._interruption_seen = asyncio.Event()
        self._closed = asyncio.Event()
        self.close_code: int | None = None
        self._reader: asyncio.Task[None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    # ─── lifecycle ────────────────────────────────────────────────────────────

    async def open(self) -> None:
        self._loop = asyncio.get_running_loop()
        await self._conn.connect()
        self._reader = asyncio.create_task(self._read_loop())

    async def aclose(self) -> None:
        if self._reader is not None:
            self._reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader
        await self._conn.close()

    def _now(self) -> float:
        assert self._loop is not None
        return self._loop.time()

    # ─── reader ───────────────────────────────────────────────────────────────

    async def _read_loop(self) -> None:
        while True:
            try:
                payload = await self._conn.recv_payload()
            except ConnectionClosed as exc:
                self.close_code = exc.rcvd.code if exc.rcvd is not None else None
                self._closed.set()
                self._wake()
                return
            if not payload:
                continue
            decoded = await self._ser.deserialize_message(payload)
            if decoded.ack is not None:
                self.acks.append(decoded.ack)
            if decoded.frame is not None:
                self._route(decoded, self._now())
            self._wake()

    def _wake(self) -> None:
        self._tick.set()
        self._tick.clear()

    def _route(self, msg: DecodedMessage, t: float) -> None:
        frame = msg.frame
        assert frame is not None
        self.log.append(Recorded(frame, t))

        if isinstance(frame, LLMFullResponseStartFrame):
            io = self.interactions.setdefault(msg.epoch, InteractionObs(msg.epoch))
            io.inferences.append(InferenceObs(msg.inference_id, started_t=t))
        elif isinstance(frame, LLMTextFrame):
            inf = self._inf(msg.epoch, msg.inference_id)
            if inf is not None:
                inf.texts.append(frame.text)
                inf.text_times.append(t)
        elif isinstance(frame, LLMFullResponseEndFrame):
            inf = self._inf(msg.epoch, msg.inference_id)
            if inf is not None:
                inf.ended = True
                inf.ended_t = t
        elif isinstance(frame, InterruptionFrame):
            self._interruption_seen.set()
        elif isinstance(frame, ServerMessageFrame):
            self.ui_commands.append(frame.data)
        elif isinstance(frame, ErrorFrame):
            self.errors.append(frame)
        elif isinstance(frame, UpdateSTTSettingsFrame):
            self.stt_settings.append(frame.settings)
        elif isinstance(frame, UpdateTTSSettingsFrame):
            self.tts_settings.append(frame.settings)
        elif isinstance(frame, UpdateIdleSettingsFrame):
            self.idle_settings.append(frame.settings)

    def _inf(self, epoch: int, inference_id: int) -> InferenceObs | None:
        io = self.interactions.get(epoch)
        return io.inference(inference_id) if io is not None else None

    # ─── sending ───────────────────────────────────────────────────────────────

    async def _send(self, frame: Frame, *, epoch: int = 0, inference_id: int = 0) -> int:
        """Serialize and send a pygato→brain frame; returns the request_id used
        (>0 for ack-gated data frames, 0 for system/control frames)."""
        if isinstance(frame, _ACK_GATED):
            self._req += 1
            request_id = self._req
        else:
            request_id = 0
        payload = await self._ser.serialize(
            frame, request_id=request_id, epoch=epoch, inference_id=inference_id
        )
        await self._conn.send_payload(payload)
        return request_id

    def next_interaction_id(self) -> int:
        """Mint the next epoch — Voice stamps every stimulus it commits."""
        self._interaction_seq += 1
        return self._interaction_seq

    # ─── waiting ─────────────────────────────────────────────────────────────

    async def _wait_for(self, predicate, *, timeout: float | None = None) -> bool:
        """Wait until ``predicate()`` is true or the socket closes. Returns
        whether the predicate held (False on timeout / close)."""
        timeout = self.default_timeout if timeout is None else timeout
        deadline = self._now() + timeout
        while True:
            if predicate():
                return True
            if self._closed.is_set():
                return predicate()
            remaining = deadline - self._now()
            if remaining <= 0:
                return predicate()
            try:
                await asyncio.wait_for(self._tick.wait(), timeout=remaining)
            except TimeoutError:
                return predicate()

    async def _quiesce(self, quiet_for: float, *, timeout: float) -> None:
        """Wait until no brain frame arrives for ``quiet_for`` seconds (or timeout)."""
        deadline = self._now() + timeout
        while self._now() < deadline and not self._closed.is_set():
            n = len(self.log)
            try:
                await asyncio.wait_for(self._tick.wait(), timeout=quiet_for)
            except TimeoutError:
                if len(self.log) == n:
                    return

    # ─── high-level driver operations ──────────────────────────────────────────

    async def start_session(
        self,
        *,
        payload: dict | None = None,
        finalize_greeting: bool = True,
        greeting_timeout: float = 3.0,
        quiet_for: float | None = None,
    ) -> Turn | None:
        """Send ``SessionStart`` (system lane) and, if the brain greets, play out
        and finalize the greeting interaction (epoch 0). Returns the greeting turn,
        or ``None`` if the brain did not greet within the timeout.

        The greeting is *agent-initiated speech* — one unit, answering no
        stimulus: the driver waits for a closed bracket plus a short quiescence,
        then finalizes the greeting inference (heard-truth)."""
        await self._send(
            SessionStartFrame(
                session_id=self.session_id,
                agent_id=self.agent_id,
                payload=payload or {},
            )
        )
        got = await self._wait_for(
            lambda: (
                (io := self.interactions.get(GREETING_INTERACTION_ID)) is not None
                and any(inf.ended for inf in io.inferences)
            ),
            timeout=greeting_timeout,
        )
        if not got:
            return None
        # Quiesce before finalizing, so nothing is still in flight.
        await self._quiesce(self._quiet(quiet_for), timeout=greeting_timeout)
        io = self.interactions.get(GREETING_INTERACTION_ID)
        if io is None or not io.inferences:
            return None
        if finalize_greeting:
            await self._finalize_completed(io, FinalizeReason.COMPLETED)
        return Turn(
            interaction_id=GREETING_INTERACTION_ID,
            inferences=list(io.inferences),
            completed=io.completed,
        )

    async def user_says(
        self,
        text: str,
        *,
        timeout: float | None = None,
        finalize: bool = True,
        quiet_for: float | None = None,
    ) -> Turn:
        """Drive one user turn: send ``UserMessage``, play out the brain's response,
        and finalize each spoken inference with a heard-truth transcript. Returns
        the observed :class:`Turn`."""
        timeout = self.default_timeout if timeout is None else timeout
        iid = self.next_interaction_id()
        await self._send(UserMessageFrame(text=text), epoch=iid)
        return await self._play_out(iid, timeout=timeout, finalize=finalize, quiet_for=quiet_for)

    def _quiet(self, quiet_for: float | None) -> float:
        return self.quiet_for if quiet_for is None else quiet_for

    async def _play_out(
        self, iid: int, *, timeout: float, finalize: bool, quiet_for: float | None = None
    ) -> Turn:
        """Play out the brain's response to an already-opened turn, then finalize
        each spoken inference with a heard-truth transcript. Shared by ``user_says``
        / ``user_idle`` / ``client_message`` — every Voice-opened turn plays out
        identically.

        The wire carries no end-of-turn frame, so "the brain is done" is: every
        bracket it opened has closed, and it has then stayed quiet for ``quiet_for``
        (a multi-inference turn opens the next bracket immediately after closing the
        last, so a closed bracket alone is not enough). A brain with a watchdog that
        speaks late needs a window longer than that watchdog."""
        await self._wait_for(
            lambda: (io := self.interactions.get(iid)) is not None and io.completed,
            timeout=timeout,
        )
        await self._quiesce(self._quiet(quiet_for), timeout=timeout)
        io = self.interactions.setdefault(iid, InteractionObs(iid))
        if finalize:
            await self._finalize_completed(io, FinalizeReason.COMPLETED)
        return Turn(iid, list(io.inferences), completed=io.completed)

    async def user_idle(
        self,
        *,
        level: int = 1,
        idle_ms: int = 30000,
        timeout: float | None = None,
        finalize: bool = True,
        quiet_for: float | None = None,
    ) -> Turn:
        """Drive an idle trigger: Voice opened a fresh interaction because the user
        went silent past the idle timeout (``UserIdle``). The brain's
        ``on_user_idle`` may re-engage; play out its response exactly like a spoken
        turn (or observe an empty interaction if it chose to stay silent)."""
        timeout = self.default_timeout if timeout is None else timeout
        iid = self.next_interaction_id()
        await self._send(UserIdleFrame(level=level, idle_ms=idle_ms), epoch=iid)
        return await self._play_out(iid, timeout=timeout, finalize=finalize, quiet_for=quiet_for)

    async def barge_in(
        self,
        text: str,
        *,
        speak_delay: float = 0.15,
        wait_for_speech: bool = True,
        wait_for_complete: bool = False,
        heard_prefix: str | None = None,
        interrupts: int = 1,
        timeout: float | None = None,
    ) -> Turn:
        """Drive a user barge-in: start a turn, let the brain begin speaking, then
        send an ``InterruptionFrame`` and await the brain's drain echo. Finalize the
        cut inference with ``interrupted=True`` / ``USER_BARGE_IN`` and a partial
        heard-truth, and return it on :attr:`Turn.heard`.

        The driver *is* Voice here, so it dictates the finalized ``heard_text`` —
        which is exactly what removes the timing nondeterminism of a real barge-in
        and lets scenarios assert the recorded transcript against a known string.
        By default the heard-truth is *what actually arrived before the cut*
        (``cut.text``); pass ``heard_prefix`` to override it explicitly.

        Timing knobs, from earliest cut to latest:

        * ``wait_for_speech=False`` — barge after a fixed short ``speak_delay``,
          regardless of whether the brain has spoken. Models a barge *before any
          audio played* (heard-truth empty; a conformant brain then commits no
          assistant message at all) — or, with a model that pauses before its first
          token, a barge while the model is invoked but has produced nothing yet.
        * ``wait_for_speech=True`` (default) — wait for the brain to speak, then let
          it go quiet for ``speak_delay`` before barging, so the cut lands cleanly
          between a heard chunk and an un-heard tail (the mid-partial case).
        * ``wait_for_complete=True`` — wait until the cut inference's bracket has
          *closed* (the reply fully generated and, on the far side, persisted by the
          framework) before barging its playout. Models a barge during the playout of
          an already-complete reply: the framework has the whole generated turn, yet
          the user heard only ``heard_prefix``. Implies waiting past ``wait_for_speech``.

        ``interrupts`` (default 1) sends that many ``InterruptionFrame``s back-to-back
        before awaiting the echo — a rapid multi-barge that stresses the brain's
        cancel path (each must cancel cleanly; the teardown of the open bracket must
        still land its ``LLMFullResponseEnd``)."""
        timeout = self.default_timeout if timeout is None else timeout
        iid = self.next_interaction_id()
        self._interruption_seen.clear()
        await self._send(UserMessageFrame(text=text), epoch=iid)

        if wait_for_complete:
            # Let the reply fully generate — the bracket closes — then barge its
            # playout with a known heard prefix.
            await self._wait_for(
                lambda: (
                    (io := self.interactions.get(iid)) is not None
                    and any(inf.ended for inf in io.inferences)
                ),
                timeout=timeout,
            )
            await self._quiesce(speak_delay if speak_delay > 0 else 0.05, timeout=timeout)
        elif wait_for_speech:
            # Let the brain open a bracket and speak at least a little, then settle.
            await self._wait_for(
                lambda: any(
                    inf.spoke for inf in self.interactions.get(iid, InteractionObs(iid)).inferences
                ),
                timeout=timeout,
            )
            if speak_delay > 0:
                await self._quiesce(speak_delay, timeout=speak_delay * 2)
        else:
            # Barge before any audio can play: wait a fixed, short beat only.
            await asyncio.sleep(speak_delay)

        cut = self._cut_inference(iid)

        # Send the interruption(s) (system lane, request_id 0) and await the echo.
        # A rapid multi-barge sends several before the brain can echo the first.
        for _ in range(max(1, interrupts)):
            await self._send(InterruptionFrame())
        await self._wait_for(self._interruption_seen.is_set, timeout=timeout)

        io = self.interactions.setdefault(iid, InteractionObs(iid))
        heard: str | None = None
        if cut is not None:
            heard = heard_prefix if heard_prefix is not None else cut.text
            await self._send(
                InferenceFinalizedFrame(heard_text=heard, reason=FinalizeReason.USER_BARGE_IN),
                epoch=iid,
                inference_id=cut.inference_id,
            )
            io.finalized.add(cut.inference_id)
        return Turn(
            iid,
            list(io.inferences),
            completed=io.completed,
            interrupted=True,
            heard=heard,
        )

    def _cut_inference(self, epoch: int) -> InferenceObs | None:
        """The inference in flight when the barge-in lands: prefer the last one
        still open (no end), else the last one observed."""
        io = self.interactions.get(epoch)
        if io is None or not io.inferences:
            return None
        for inf in reversed(io.inferences):
            if not inf.ended:
                return inf
        return io.inferences[-1]

    async def _finalize_completed(self, io: InteractionObs, reason: FinalizeReason) -> None:
        """Finalize every spoken, ended, not-yet-finalized inference in ``io`` with
        heard-truth = exactly what the brain emitted (never generated)."""
        for inf in io.inferences:
            if inf.inference_id in io.finalized or not inf.spoke or not inf.ended:
                continue
            await self._send(
                InferenceFinalizedFrame(heard_text=inf.text, reason=reason),
                epoch=io.interaction_id,
                inference_id=inf.inference_id,
            )
            io.finalized.add(inf.inference_id)

    # ─── app / action lane ───────────────────────────────────────────────────

    async def send_client_message(self, type: str, data: dict | None = None) -> int:
        """Send a browser client message the brain is *not* expected to answer, and
        return the epoch Voice stamped it with.

        Voice delivers **every** browser message to the brain's
        ``on_client_message`` without interpreting it. This method does not wait for
        a reply; the responding case is :meth:`client_message`."""
        iid = self.next_interaction_id()
        await self._send(
            ClientMessageFrame(msg_id=str(uuid.uuid4()), type=type, data=data or {}),
            epoch=iid,
        )
        return iid

    async def send_action_result(
        self,
        action_id: int,
        *,
        status: str = "ok",
        result: dict | None = None,
    ) -> None:
        """Report the outcome of a UI action the brain requested (client→brain).

        Rides the same ``ClientMessage`` frame as any browser message, typed
        ``action_result`` — the SDK routes those to the pending ``action`` callback
        rather than ``on_client_message``. ``action_id`` is the integer the brain
        minted in its ``ui_command``; the adapter correlates the outcome by that int
        at session scope."""
        await self._send(
            ClientMessageFrame(
                msg_id=str(uuid.uuid4()),
                type="action_result",
                data={"action_id": action_id, "status": status, "result": result or {}},
            ),
            epoch=self.next_interaction_id(),
        )

    async def wait_closed(self, *, timeout: float | None = None) -> int | None:
        """Wait for the brain to close the socket; return the close code (or None)."""
        await self._wait_for(self._closed.is_set, timeout=timeout)
        return self.close_code

    async def collect_ui_commands(
        self, *, min_count: int = 1, timeout: float | None = None
    ) -> list[dict]:
        """Wait until at least ``min_count`` UI commands have arrived; return them all."""
        await self._wait_for(lambda: len(self.ui_commands) >= min_count, timeout=timeout)
        return list(self.ui_commands)

    async def dump_conversation(self, *, timeout: float | None = None) -> dict:
        """Ask a cooperating brain to echo its committed session state
        (conversation / app-events / outcomes) over the ordinary action lane, and
        return it.

        This is the conformance *backchannel* — the only way to observe the brain's
        heard-truth history, which the wire never carries (see
        :data:`CONFORMANCE_DUMP_EVENT`). The driver sends the namespaced
        ``__voqal.conformance.dump`` client message; a conformance-aware brain answers
        with a ``__voqal.conformance.state`` action carrying its committed
        ``session.conversation``. No protocol change — just a cooperation
        convention on the existing client-message lane."""
        before = len(self.ui_commands)
        await self.send_client_message(CONFORMANCE_DUMP_EVENT)
        await self._wait_for(
            lambda: any(
                c.get("action") == CONFORMANCE_STATE_ACTION for c in self.ui_commands[before:]
            ),
            timeout=timeout,
        )
        for c in reversed(self.ui_commands):
            if c.get("action") == CONFORMANCE_STATE_ACTION:
                return c
        raise TimeoutError(f"brain did not echo {CONFORMANCE_STATE_ACTION}")

    async def end_session(self, *, timeout: float | None = None) -> None:
        """Send ``End`` and wait for the brain to close the socket."""
        await self._send(EndFrame())
        await self._wait_for(self._closed.is_set, timeout=timeout)

    async def send_cancel(self, reason: str | None = None) -> None:
        await self._send(CancelFrame(reason=reason))
