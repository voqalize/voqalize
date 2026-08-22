"""Wire reconnect behavior over real localhost websockets."""

from __future__ import annotations

import asyncio

import pytest
import websockets

from voqalize.sdk.wire import PermanentClose, Wire, WireConfig
from voqalize.sdk.wire.transport import CLOSE_AGENT_GONE, CLOSE_NO_AGENT


async def _start_server(handler):
    server = await websockets.serve(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    return f"ws://127.0.0.1:{port}", server


async def test_reconnect_on_transient_close_and_fires_callback() -> None:
    """First connection closes with 4001 mid-recv. Wire reconnects, on_reconnect
    fires once, send/recv resume on the new socket.
    """
    received: list[bytes] = []
    connection_count = 0
    reconnect_event = asyncio.Event()

    async def handler(ws):
        nonlocal connection_count
        connection_count += 1
        if connection_count == 1:
            # Push one frame, then close transient. Wire's recv will deliver
            # the frame, then see the close and reconnect.
            await ws.send(b"first-payload")
            await ws.close(code=CLOSE_AGENT_GONE, reason="agent_gone")
        else:
            # Reconnected socket: receive one frame, hold open until close.
            try:
                msg = await ws.recv()
                if isinstance(msg, bytes):
                    received.append(msg)
                # Keep open for test asserts.
                await asyncio.sleep(0.5)
            except websockets.exceptions.ConnectionClosed:
                pass

    url, server = await _start_server(handler)

    async def on_reconnect() -> None:
        reconnect_event.set()

    wire = Wire(
        WireConfig(url=url, initial_backoff_seconds=0.01, backoff_jitter=0),
        on_reconnect=on_reconnect,
    )
    try:
        await wire.start()
        # First recv delivers the payload from connection #1.
        assert await wire.recv() == b"first-payload"

        # Send must succeed — wire will detect the closed socket, reconnect,
        # fire on_reconnect, then send on the new socket.
        await wire.send(b"second")
        await asyncio.wait_for(reconnect_event.wait(), timeout=2.0)
        # Let the reconnected server drain the second frame.
        for _ in range(20):
            if received == [b"second"]:
                break
            await asyncio.sleep(0.05)
    finally:
        await wire.close()
        server.close()
        await server.wait_closed()

    assert connection_count == 2
    assert received == [b"second"]


async def test_permanent_close_on_4000() -> None:
    """Server closes with 4000 (NoAgent). Next recv must raise PermanentClose
    and the wire must not reconnect.
    """
    connection_count = 0

    async def handler(ws):
        nonlocal connection_count
        connection_count += 1
        await ws.close(code=CLOSE_NO_AGENT, reason="no_agent")

    url, server = await _start_server(handler)

    wire = Wire(WireConfig(url=url, initial_backoff_seconds=0.01, backoff_jitter=0))
    try:
        await wire.start()
        with pytest.raises(PermanentClose):
            await wire.recv()
        # And a subsequent send still raises PermanentClose — no retry.
        with pytest.raises(PermanentClose):
            await wire.send(b"x")
        # Give any (forbidden) reconnect a chance to slip through.
        await asyncio.sleep(0.2)
    finally:
        await wire.close()
        server.close()
        await server.wait_closed()

    assert connection_count == 1


async def test_backoff_grows_when_no_server() -> None:
    """No listener at the target port: connect retries with backoff. Cancel and
    verify the wire didn't tight-loop.
    """
    config = WireConfig(
        url="ws://127.0.0.1:1",  # port 1 is reserved, refused
        initial_backoff_seconds=0.05,
        max_backoff_seconds=0.2,
        backoff_multiplier=2.0,
        backoff_jitter=0,
        connect_timeout=0.2,
    )
    wire = Wire(config)
    start_task = asyncio.create_task(wire.start())
    await asyncio.sleep(0.5)
    assert not start_task.done(), "wire.start() should still be retrying"
    start_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await start_task
    await wire.close()
