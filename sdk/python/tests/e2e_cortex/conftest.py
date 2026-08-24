"""Shared fixtures for the end-to-end cortex suite.

Pipecat-free. The agent side is hosted via the SDK's own runtime
(``CortexAgent`` + a ``Brain`` or a test ``SessionAdapter``);
the pygato side is simulated by the SDK's single-session ``Wire`` client speaking
the same bare ``[direction][protobuf]`` framing and frame vocabulary PyGato
uses against Cortex. Both legs meet over a real TCP ``FakeCortex`` relay, so this
exercises the multiplexed wire (session-id prefixing), the per-session engine,
and reconnect — end to end — without importing pygato or pipecat.
"""

from __future__ import annotations

import asyncio

from voqalize.sdk.wire import (
    Frame,
    MalformedFrameError,
    RTVIFrame,
    RTVIType,
    Wire,
    WireConfig,
    WireSerializer,
)


class PygatoClient:
    """PyGato-side driver: a single-session ``Wire`` + the shared serializer,
    connected to FakeCortex's ``?session_id=`` leg."""

    def __init__(self, wire: Wire) -> None:
        self._wire = wire
        self._ser = WireSerializer()

    async def send(self, frame: Frame) -> None:
        await self._wire.send(await self._ser.serialize(frame))

    async def close(self) -> None:
        await self._wire.close()

    async def collect_until(self, predicate, timeout: float = 5.0) -> list[Frame]:
        """Drain inbound messages until ``predicate(frames)`` is true."""
        frames: list[Frame] = []

        async def pump() -> None:
            while not predicate(frames):
                payload = await self._wire.recv()
                try:
                    frame = await self._ser.deserialize_message(payload)
                except MalformedFrameError:
                    continue
                if frame is not None:
                    frames.append(frame)

        await asyncio.wait_for(pump(), timeout=timeout)
        return frames

    async def collect_ui_commands(self, min_count: int, timeout: float = 5.0) -> list[dict]:
        """Drain inbound messages until at least ``min_count`` ui-commands seen."""
        cmds: list[dict] = []

        async def pump() -> None:
            while len(cmds) < min_count:
                payload = await self._wire.recv()
                try:
                    frame = await self._ser.deserialize_message(payload)
                except MalformedFrameError:
                    continue
                if (
                    isinstance(frame, RTVIFrame)
                    and frame.type is RTVIType.UI_COMMAND
                    and isinstance(frame.data, dict)
                ):
                    cmds.append(frame.data)

        await asyncio.wait_for(pump(), timeout=timeout)
        return cmds


async def connect_pygato(cortex, session_id: str, agent_id: str = "welcome") -> PygatoClient:
    """Open a pygato-leg Wire against FakeCortex and wrap it in a PygatoClient."""
    wire = Wire(WireConfig(url=cortex.pygato_url(session_id, agent_id)))
    await wire.start()
    return PygatoClient(wire)


async def wait_until(predicate, timeout: float = 3.0, interval: float = 0.02) -> None:
    """Tiny polling helper for predicates without backing events."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(interval)
    raise AssertionError(f"timeout waiting for {predicate}")
