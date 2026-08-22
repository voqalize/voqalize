"""``VoiceDriver`` — a wire-compliant stand-in for Voice, seen from a brain's
point of view.

The driver *is* the "compliant voqalize": it dials a brain over the single
session ``/s/{session_id}`` leg, speaks the shipped protobuf wire, and plays out
the brain's responses the way real Voice does — auto-finalizing each speech unit
with a *heard-truth* transcript and honouring the barge-in drain barrier.
Everything the brain sends back is decoded, timestamped, and recorded so
scenarios can assert the wire's MUSTs against a structured transcript.

Turns end the way they end on a real call: the wire carries no "the brain is
done" frame, so a turn is over when every speech unit it opened has closed
and the brain has gone quiet. Real Voice has no more than that either.

What the driver deliberately does *not* do: audio, VAD, STT/TTS, WebRTC. Playout
is modelled as "the whole unit is heard unless barged in", which is all the
conformance surface of the wire needs.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field

from websockets.exceptions import ConnectionClosed

from voqalize.sdk.wire import (
    WIRE_VERSION,
    BrowserCommandFrame,
    BrowserMessageFrame,
    CancelFrame,
    ConfigureIdleFrame,
    ConfigureRequest,
    ConfigureSttFrame,
    ConfigureTtsFrame,
    EndFrame,
    ErrorFrame,
    FinalizeFrame,
    FinalizeReason,
    Frame,
    InterruptionFrame,
    ResponseFrame,
    SessionStartFrame,
    SpeechChunkFrame,
    SpeechEndFrame,
    SpeechStartFrame,
    UserIdleFrame,
    UserMessageFrame,
)
from voqalize.sdk.wire.serializer import DecodedMessage, WireSerializer

from .wire_voice import DirectConnection

# The greeting epoch: the brain speaks first on session start, with no
# user turn to attribute it to. Agent-initiated speech echoes no epoch, so it
# lands on 0.
GREETING_EPOCH = 0

# The control leg's ops, by the frame that carries each. The driver answers every
# one, because Voice does — a brain awaiting an answer that never comes is the
# one failure the wire promises cannot happen.
REQUEST_OPS: dict[type[Frame], str] = {
    ConfigureTtsFrame: "configure_tts",
    ConfigureSttFrame: "configure_stt",
    ConfigureIdleFrame: "configure_idle",
}

# ─── the conformance backchannel ─────────────────────────────────────────────
#
# The wire deliberately never carries the brain's *committed* conversation — the
# brain only ever sends speech *output* frames, so heard-truth (what the brain
# recorded for the LLM) is not observable from the wire alone. There is no
# history-request frame, and we do not add one: the wire stays frozen.
#
# Instead the driver reuses the generic, schema-free browser lane the wire
# already has (browser→brain ``BrowserMessage`` / brain→browser
# ``BrowserCommand``, the same lane real UIs use for ``ui_command`` /
# ``action_result`` — opaque to Voice, which just relays it). A conformance-aware
# brain opts in by answering one namespaced browser message with its committed state.
# Because the SDK *owns* ``session.conversation``, that answer can be produced by
# the framework once (see ``reference.conformance_state``) and every brain built
# on the SDK inherits it — the customer's brain code writes nothing.
CONFORMANCE_DUMP_EVENT = "__voqal.conformance.dump"
CONFORMANCE_STATE_ACTION = "__voqal.conformance.state"


@dataclass
class Recorded:
    """One brain→voice frame, timestamped on the driver's monotonic clock."""

    frame: Frame
    t: float


@dataclass
class SpeechObs:
    """The driver's observation of a single speech unit (brain output)."""

    speech_id: int
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
class EpochObs:
    """The driver's observation of one epoch (0 = greeting, else a user turn)."""

    epoch: int
    units: list[SpeechObs] = field(default_factory=list)
    finalized: set[int] = field(default_factory=set)

    @property
    def completed(self) -> bool:
        """Every bracket the brain opened for this turn, it closed. The wire has
        no end-of-turn frame; this is what "the brain finished" means."""
        return bool(self.units) and all(unit.ended for unit in self.units)

    def unit(self, speech_id: int) -> SpeechObs | None:
        for unit in self.units:
            if unit.speech_id == speech_id:
                return unit
        return None


@dataclass
class Turn:
    """The result of one driven turn (a ``user_says`` or ``barge_in``)."""

    epoch: int
    units: list[SpeechObs]
    completed: bool
    interrupted: bool = False
    # For a barge-in: the partial heard-truth the driver finalized the cut
    # unit with (what the user actually heard before the interruption).
    # ``""`` means the barge landed before any audio played; ``None`` means the
    # turn was not a barge-in (or no unit was open to cut).
    heard: str | None = None

    @property
    def text(self) -> str:
        return " ".join(unit.text for unit in self.units if unit.spoke)


class VoiceDriver:
    """Drives a brain over one direct session, standing in for Voice.

    Typical lifecycle::

        driver = VoiceDriver(conn, session_id=sid)
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
        default_timeout: float = 5.0,
        quiet_for: float = 0.25,
    ) -> None:
        self._conn = conn
        self.session_id = session_id
        self.default_timeout = default_timeout
        self.quiet_for = quiet_for
        self._ser = WireSerializer()

        self._epoch_seq = 0

        # Recorded / decoded brain output.
        self.log: list[Recorded] = []
        self.ui_commands: list[dict] = []
        self.errors: list[ErrorFrame] = []
        # Every configure request the brain made, in wire order.
        self.requests: list[ConfigureRequest] = []
        # Ops to refuse, op name → the reason Voice gives. A scenario sets one to
        # exercise the path where a brain asks for something Voice will not do.
        self.reject: dict[str, str] = {}
        # Ops to leave unanswered, for the one case the wire cannot promise
        # away: a Voice that stopped answering mid-call.
        self.withhold: set[str] = set()
        self.epochs: dict[int, EpochObs] = {}

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
            if decoded.frame is not None:
                await self._route(decoded, self._now())
            self._wake()

    def _wake(self) -> None:
        self._tick.set()
        self._tick.clear()

    async def _route(self, msg: DecodedMessage, t: float) -> None:
        frame = msg.frame
        assert frame is not None
        self.log.append(Recorded(frame, t))

        if isinstance(frame, SpeechStartFrame):
            io = self.epochs.setdefault(msg.epoch, EpochObs(msg.epoch))
            io.units.append(SpeechObs(msg.speech_id, started_t=t))
        elif isinstance(frame, SpeechChunkFrame):
            unit = self._unit_obs(msg.epoch, msg.speech_id)
            if unit is not None:
                unit.texts.append(frame.text)
                unit.text_times.append(t)
        elif isinstance(frame, SpeechEndFrame):
            unit = self._unit_obs(msg.epoch, msg.speech_id)
            if unit is not None:
                unit.ended = True
                unit.ended_t = t
        elif isinstance(frame, InterruptionFrame):
            self._interruption_seen.set()
        elif isinstance(frame, BrowserCommandFrame):
            self.ui_commands.append(frame.data)
        elif isinstance(frame, ErrorFrame):
            self.errors.append(frame)
        elif isinstance(frame, ConfigureTtsFrame | ConfigureSttFrame | ConfigureIdleFrame):
            self.requests.append(frame)
            op = REQUEST_OPS[type(frame)]
            if op in self.withhold:
                return
            detail = self.reject.get(op, "")
            await self._send(
                ResponseFrame(request_id=frame.request_id, accepted=not detail, detail=detail)
            )

    def _unit_obs(self, epoch: int, speech_id: int) -> SpeechObs | None:
        io = self.epochs.get(epoch)
        return io.unit(speech_id) if io is not None else None

    # ─── sending ───────────────────────────────────────────────────────────────

    async def _send(self, frame: Frame, *, epoch: int = 0, speech_id: int = 0) -> None:
        """Serialize and send one voice→brain frame."""
        payload = await self._ser.serialize(frame, epoch=epoch, speech_id=speech_id)
        await self._conn.send_payload(payload)

    def next_epoch(self) -> int:
        """Mint the next epoch — Voice stamps every stimulus it commits."""
        self._epoch_seq += 1
        return self._epoch_seq

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
        init: dict | None = None,
        finalize_greeting: bool = True,
        greeting_timeout: float = 3.0,
        quiet_for: float | None = None,
    ) -> Turn | None:
        """Send ``SessionStart`` (system lane) and, if the brain greets, play out
        and finalize the greeting epoch (0). Returns the greeting turn,
        or ``None`` if the brain did not greet within the timeout.

        The greeting is *agent-initiated speech* — one unit, answering no
        stimulus: the driver waits for a closed bracket plus a short quiescence,
        then finalizes the greeting unit (heard-truth)."""
        await self._send(
            SessionStartFrame(
                session_id=self.session_id,
                init=init or {},
                wire_version=WIRE_VERSION,
            )
        )
        got = await self._wait_for(
            lambda: (
                (io := self.epochs.get(GREETING_EPOCH)) is not None
                and any(unit.ended for unit in io.units)
            ),
            timeout=greeting_timeout,
        )
        if not got:
            return None
        # Quiesce before finalizing, so nothing is still in flight.
        await self._quiesce(self._quiet(quiet_for), timeout=greeting_timeout)
        io = self.epochs.get(GREETING_EPOCH)
        if io is None or not io.units:
            return None
        if finalize_greeting:
            await self._finalize_completed(io, FinalizeReason.COMPLETED)
        return Turn(
            epoch=GREETING_EPOCH,
            units=list(io.units),
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
        and finalize each spoken unit with a heard-truth transcript. Returns
        the observed :class:`Turn`."""
        timeout = self.default_timeout if timeout is None else timeout
        epoch = self.next_epoch()
        await self._send(UserMessageFrame(text=text), epoch=epoch)
        return await self._play_out(epoch, timeout=timeout, finalize=finalize, quiet_for=quiet_for)

    def _quiet(self, quiet_for: float | None) -> float:
        return self.quiet_for if quiet_for is None else quiet_for

    async def _play_out(
        self, epoch: int, *, timeout: float, finalize: bool, quiet_for: float | None = None
    ) -> Turn:
        """Play out the brain's response to an already-opened turn, then finalize
        each spoken unit with a heard-truth transcript. Shared by ``user_says``
        / ``user_idle`` / ``barge_in`` — every Voice-opened turn plays out
        identically.

        The wire carries no end-of-turn frame, so "the brain is done" is: every
        bracket it opened has closed, and it has then stayed quiet for ``quiet_for``
        (a multi-unit turn opens the next bracket immediately after closing the
        last, so a closed bracket alone is not enough). A brain with a watchdog that
        speaks late needs a window longer than that watchdog."""
        await self._wait_for(
            lambda: (io := self.epochs.get(epoch)) is not None and io.completed,
            timeout=timeout,
        )
        await self._quiesce(self._quiet(quiet_for), timeout=timeout)
        io = self.epochs.setdefault(epoch, EpochObs(epoch))
        if finalize:
            await self._finalize_completed(io, FinalizeReason.COMPLETED)
        return Turn(epoch, list(io.units), completed=io.completed)

    async def user_idle(
        self,
        *,
        level: int = 1,
        idle_ms: int = 30000,
        timeout: float | None = None,
        finalize: bool = True,
        quiet_for: float | None = None,
    ) -> Turn:
        """Drive an idle trigger: Voice opened a fresh epoch because the user
        went silent past the idle timeout (``UserIdle``). The brain's
        ``on_user_idle`` may re-engage; play out its response exactly like a spoken
        turn (or observe an empty epoch if it chose to stay silent)."""
        timeout = self.default_timeout if timeout is None else timeout
        epoch = self.next_epoch()
        await self._send(UserIdleFrame(level=level, idle_ms=idle_ms), epoch=epoch)
        return await self._play_out(epoch, timeout=timeout, finalize=finalize, quiet_for=quiet_for)

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
        cut unit with ``interrupted=True`` / ``USER_BARGE_IN`` and a partial
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
        * ``wait_for_complete=True`` — wait until the cut unit's bracket has
          *closed* (the reply fully generated and, on the far side, persisted by the
          framework) before barging its playout. Models a barge during the playout of
          an already-complete reply: the framework has the whole generated turn, yet
          the user heard only ``heard_prefix``. Implies waiting past ``wait_for_speech``.

        ``interrupts`` (default 1) sends that many ``InterruptionFrame``s back-to-back
        before awaiting the echo — a rapid multi-barge that stresses the brain's
        cancel path (each must cancel cleanly; the teardown of the open bracket must
        still land its ``SpeechEnd``)."""
        timeout = self.default_timeout if timeout is None else timeout
        epoch = self.next_epoch()
        self._interruption_seen.clear()
        await self._send(UserMessageFrame(text=text), epoch=epoch)

        if wait_for_complete:
            # Let the reply fully generate — the bracket closes — then barge its
            # playout with a known heard prefix.
            await self._wait_for(
                lambda: (
                    (io := self.epochs.get(epoch)) is not None
                    and any(unit.ended for unit in io.units)
                ),
                timeout=timeout,
            )
            await self._quiesce(speak_delay if speak_delay > 0 else 0.05, timeout=timeout)
        elif wait_for_speech:
            # Let the brain open a bracket and speak at least a little, then settle.
            await self._wait_for(
                lambda: any(unit.spoke for unit in self.epochs.get(epoch, EpochObs(epoch)).units),
                timeout=timeout,
            )
            if speak_delay > 0:
                await self._quiesce(speak_delay, timeout=speak_delay * 2)
        else:
            # Barge before any audio can play: wait a fixed, short beat only.
            await asyncio.sleep(speak_delay)

        cut = self._cut_unit(epoch)

        # Send the interruption(s) and await the echo. A rapid multi-barge sends
        # several before the brain can echo the first.
        for _ in range(max(1, interrupts)):
            await self._send(InterruptionFrame())
        await self._wait_for(self._interruption_seen.is_set, timeout=timeout)

        io = self.epochs.setdefault(epoch, EpochObs(epoch))
        heard: str | None = None
        if cut is not None:
            heard = heard_prefix if heard_prefix is not None else cut.text
            await self._send(
                FinalizeFrame(heard_text=heard, reason=FinalizeReason.USER_BARGE_IN),
                epoch=epoch,
                speech_id=cut.speech_id,
            )
            io.finalized.add(cut.speech_id)
        return Turn(
            epoch,
            list(io.units),
            completed=io.completed,
            interrupted=True,
            heard=heard,
        )

    def _cut_unit(self, epoch: int) -> SpeechObs | None:
        """The unit in flight when the barge-in lands: prefer the last one
        still open (no end), else the last one observed."""
        io = self.epochs.get(epoch)
        if io is None or not io.units:
            return None
        for unit in reversed(io.units):
            if not unit.ended:
                return unit
        return io.units[-1]

    async def _finalize_completed(self, io: EpochObs, reason: FinalizeReason) -> None:
        """Finalize every spoken, ended, not-yet-finalized unit in ``io`` with
        heard-truth = exactly what the brain emitted (never generated)."""
        for unit in io.units:
            if unit.speech_id in io.finalized or not unit.spoke or not unit.ended:
                continue
            await self._send(
                FinalizeFrame(heard_text=unit.text, reason=reason),
                epoch=io.epoch,
                speech_id=unit.speech_id,
            )
            io.finalized.add(unit.speech_id)

    # ─── app / action lane ───────────────────────────────────────────────────

    async def send_browser_message(self, type: str, data: dict | None = None) -> int:
        """Send a browser message and return the epoch Voice stamped it with.

        Voice delivers **every** browser message to the brain's
        ``on_browser_message`` without interpreting it, and that callback cannot
        speak — so there is nothing to wait for here."""
        epoch = self.next_epoch()
        await self._send(BrowserMessageFrame(type=type, data=data or {}), epoch=epoch)
        return epoch

    async def send_action_result(
        self,
        action_id: int,
        *,
        status: str = "ok",
        result: dict | None = None,
    ) -> None:
        """Report the outcome of a UI action the brain requested (client→brain).

        Rides the same ``BrowserMessage`` frame as any browser message, typed
        ``action_result`` — the SDK routes those to the pending ``action`` callback
        rather than ``on_browser_message``. ``action_id`` is the integer the brain
        minted in its ``ui_command``; the adapter correlates the outcome by that int
        at session scope."""
        await self._send(
            BrowserMessageFrame(
                type="action_result",
                data={"action_id": action_id, "status": status, "result": result or {}},
            ),
            epoch=self.next_epoch(),
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
        ``session.conversation``. No change to the wire — just a cooperation
        convention on the existing client-message lane."""
        before = len(self.ui_commands)
        await self.send_browser_message(CONFORMANCE_DUMP_EVENT)
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
