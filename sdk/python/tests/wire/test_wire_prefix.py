"""Wire framing test — 1-byte direction prefix over a real localhost websocket."""

from __future__ import annotations

import asyncio
import contextlib

import websockets

from voqalize.sdk.wire import FrameDirection, Wire, WireConfig


@contextlib.asynccontextmanager
async def _echo_server(received: list[bytes]):
    """Accepts one connection, captures every incoming binary message, and
    echoes nothing back (for send-side tests).
    """

    async def handler(ws):
        try:
            async for msg in ws:
                if isinstance(msg, bytes):
                    received.append(msg)
        except websockets.exceptions.ConnectionClosed:
            pass

    async with websockets.serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        yield f"ws://127.0.0.1:{port}"


@contextlib.asynccontextmanager
async def _sending_server(items: list[tuple[int, bytes]]):
    """Accepts one connection and sends a sequence of [direction_byte | payload]
    messages, then closes normally.
    """

    async def handler(ws):
        for direction, payload in items:
            await ws.send(bytes([direction]) + payload)
        await ws.close()

    async with websockets.serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        yield f"ws://127.0.0.1:{port}"


async def test_send_writes_direction_byte_then_payload() -> None:
    received: list[bytes] = []
    async with _echo_server(received) as url:
        wire = Wire(WireConfig(url=url))
        await wire.start()
        await wire.send(FrameDirection.DOWNSTREAM, b"abc")
        await wire.send(FrameDirection.UPSTREAM, b"\x00\x01\x02")
        # Give the server a beat to drain.
        await asyncio.sleep(0.05)
        await wire.close()

    # FrameDirection: DOWNSTREAM=1, UPSTREAM=2.
    assert received == [b"\x01abc", b"\x02\x00\x01\x02"]


async def test_recv_parses_direction_and_payload() -> None:
    items = [
        (FrameDirection.DOWNSTREAM.value, b"hello"),
        (FrameDirection.UPSTREAM.value, b"\xff\xfe"),
    ]
    async with _sending_server(items) as url:
        wire = Wire(WireConfig(url=url))
        await wire.start()
        d1, p1 = await wire.recv()
        d2, p2 = await wire.recv()
        await wire.close()

    assert (d1, p1) == (FrameDirection.DOWNSTREAM, b"hello")
    assert (d2, p2) == (FrameDirection.UPSTREAM, b"\xff\xfe")
