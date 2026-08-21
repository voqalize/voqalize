"""Session-scoped logging: the brain's own lines join the rest of the call.

Three things are worth pinning, and they are the three that would silently rot:

1. The context propagates into **tasks**. That is the whole mechanism — the
   customer's brain code runs in tasks the SDK spawns, and if the context did
   not copy into them the feature would look wired up and tag nothing.
2. The identity comes from the **verified claims**, never from anything the
   caller passed alongside them.
3. ``configure_logging`` actually *renders* the fields. Binding without a sink
   that prints them is the known failure mode this module exists to avoid, and
   it is invisible unless a test reads the output.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from loguru import logger

from voqalize.sdk import Brain, configure_logging, run_session, session_context
from voqalize.sdk.wire import CortexFrameSerializer, SessionStartFrame, SpeechChunkFrame

_TEARDOWN_ERRORS = (TimeoutError, asyncio.CancelledError, ConnectionError)


class _Capture:
    """A loguru sink that keeps every record's ``extra``, and removes itself."""

    def __init__(self) -> None:
        self.records: list[dict] = []
        self._id = logger.add(self._sink, level="DEBUG")

    def _sink(self, message) -> None:
        self.records.append(dict(message.record["extra"]))

    def close(self) -> None:
        logger.remove(self._id)

    def __enter__(self) -> _Capture:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


async def test_context_reaches_tasks_spawned_inside_it():
    """A task created inside the block inherits the identity; one outside doesn't."""
    with _Capture() as cap:
        with session_context("sid-1", tenant_id="t1", agent_id="a1"):
            await asyncio.create_task(_log_from_a_task())
        logger.info("outside")

    inside, outside = cap.records[0], cap.records[1]
    assert inside["session_id"] == "sid-1"
    assert inside["tenant_id"] == "t1"
    assert inside["agent_id"] == "a1"
    assert inside["service"] == "brain"
    assert "session_id" not in outside


async def _log_from_a_task() -> None:
    logger.info("from a task")


async def test_empty_identity_fields_are_omitted_not_blank():
    """A brain with no tenant claim logs no ``tenant_id`` key at all.

    An empty string is worse than an absent field: it indexes, and it matches
    other calls that also have nothing.
    """
    with _Capture() as cap:
        with session_context("sid-2"):
            logger.info("hello")

    assert cap.records[0]["session_id"] == "sid-2"
    assert "tenant_id" not in cap.records[0]
    assert "agent_id" not in cap.records[0]


class _LoggingBrain(Brain):
    async def on_session_start(self, session) -> None:
        logger.info("brain: session started")

    async def greet(self, session) -> str:
        return "hi there"


class _Endpoint:
    def __init__(self, out_q: asyncio.Queue, in_q: asyncio.Queue) -> None:
        self._out = out_q
        self._in = in_q

    async def send(self, data: bytes) -> None:
        await self._out.put(bytes(data))

    async def recv(self) -> bytes:
        item = await self._in.get()
        if item is None:
            raise ConnectionError("channel closed")
        return item

    async def close(self) -> None:
        await self._out.put(None)


def _pipe() -> tuple[_Endpoint, _Endpoint]:
    a2b: asyncio.Queue = asyncio.Queue()
    b2a: asyncio.Queue = asyncio.Queue()
    return _Endpoint(out_q=a2b, in_q=b2a), _Endpoint(out_q=b2a, in_q=a2b)


def _signed(session_id: str, **claims) -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    pub = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    token = jwt.encode(
        {
            "iss": "pygato",
            "aud": "brain",
            "sub": session_id,
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(seconds=60),
            **claims,
        },
        priv,
        algorithm="RS256",
    )
    return token, pub


async def test_brain_lines_carry_the_identity_from_the_verified_token():
    """The customer's own ``logger.info`` inside a callback is tagged for free."""
    sid = str(uuid.uuid4())
    token, pub = _signed(sid, tenant_id="tenant-7", agent_id="agent-9")
    server_ch, client_ch = _pipe()

    with _Capture() as cap:
        task = asyncio.create_task(
            run_session(
                server_ch,
                brain=_LoggingBrain,
                session_id=sid,
                token=f"Bearer {token}",
                public_keys=pub,
            )
        )
        ser = CortexFrameSerializer()
        try:
            await client_ch.send(b"\x01" + await ser.serialize(SessionStartFrame(session_id=sid)))

            async def _await_greeting() -> None:
                while True:
                    msg = await ser.deserialize_message((await client_ch.recv())[1:])
                    if isinstance(msg.frame, SpeechChunkFrame) and "hi there" in msg.frame.text:
                        return

            await asyncio.wait_for(_await_greeting(), timeout=3.0)
        finally:
            await client_ch.close()
            with contextlib.suppress(*_TEARDOWN_ERRORS):
                await asyncio.wait_for(task, timeout=2.0)

    tagged = [r for r in cap.records if r.get("session_id") == sid]
    assert tagged, "the brain's own log lines were not tagged with the session"
    assert all(r["tenant_id"] == "tenant-7" for r in tagged)
    assert all(r["agent_id"] == "agent-9" for r in tagged)


def test_json_sink_promotes_identity_and_keeps_custom_fields(capsys):
    """The shape a log shipper indexes: ids at top level, the rest under ``fields``."""
    try:
        configure_logging(json_logs=True)
        with session_context("sid-3", tenant_id="t3"):
            logger.bind(candidate="c-1").info("scored")
        line = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    finally:
        logger.remove()

    assert line["session_id"] == "sid-3"
    assert line["tenant_id"] == "t3"
    assert line["service"] == "brain"
    assert line["message"] == "scored"
    assert line["fields"] == {"candidate": "c-1"}
    assert "agent_id" not in line, "an absent claim must not become an empty key"


def test_console_sink_renders_a_line_logged_outside_any_session(capsys):
    """``{extra[session_id]}`` would raise on an un-tagged line — it must not."""
    try:
        configure_logging()
        logger.info("no session here")
        out = capsys.readouterr().err
    finally:
        logger.remove()

    assert "no session here" in out
