"""Wire framing — one binary websocket message carries one envelope, verbatim."""

from __future__ import annotations

import asyncio
import contextlib

import pytest
import websockets

from voqalize.sdk.wire import Wire, WireConfig


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
async def _sending_server(items: list[str | bytes]):
    """Accepts one connection, sends a sequence of messages, then closes."""

    async def handler(ws):
        for msg in items:
            await ws.send(msg)
        await ws.close()

    async with websockets.serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        yield f"ws://127.0.0.1:{port}"


async def test_send_writes_the_payload_and_nothing_else() -> None:
    received: list[bytes] = []
    async with _echo_server(received) as url:
        wire = Wire(WireConfig(url=url))
        await wire.start()
        await wire.send(b"abc")
        await wire.send(b"\x00\x01\x02")
        # Give the server a beat to drain.
        await asyncio.sleep(0.05)
        await wire.close()

    assert received == [b"abc", b"\x00\x01\x02"]


async def test_recv_returns_the_payload_verbatim() -> None:
    async with _sending_server([b"hello", b"\xff\xfe"]) as url:
        wire = Wire(WireConfig(url=url))
        await wire.start()
        assert await wire.recv() == b"hello"
        assert await wire.recv() == b"\xff\xfe"
        await wire.close()


async def test_a_text_message_is_an_error() -> None:
    async with _sending_server(["hello"]) as url:
        wire = Wire(WireConfig(url=url))
        await wire.start()
        with pytest.raises(ValueError, match="TEXT"):
            await wire.recv()
        await wire.close()
