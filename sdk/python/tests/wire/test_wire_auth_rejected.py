"""A credential cortex refuses fails loudly, immediately, once.

Cortex answers a bad key with a `401` on the HTTP upgrade — before any
websocket exists, so there is no close code to read. Until this test existed
the transport read `exc.rcvd` (absent on a handshake rejection), concluded
"transient", and retried forever behind exponential backoff: the only evidence
a customer ever saw was `wire: connect attempt N failed ... retrying`, with the
word "401" nowhere in it.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from websockets.asyncio.server import Server, ServerConnection, serve

from tests.cortex.conftest import RecordingAdapter
from voqalize.sdk.outbound import CortexAgent
from voqalize.sdk.wire import AuthRejected, MultiplexedWire, PermanentClose, WireConfig


@asynccontextmanager
async def _refusing_server(status: int) -> AsyncIterator[str]:
    """A websocket server that rejects every upgrade with `status`."""

    def reject(connection: ServerConnection, request):
        return connection.respond(status, "no\n")

    async def never_reached(connection: ServerConnection) -> None:  # pragma: no cover
        raise AssertionError("handshake should never have completed")

    server: Server = await serve(never_reached, "127.0.0.1", 0, process_request=reject)
    port = next(iter(server.sockets)).getsockname()[1]
    try:
        yield f"ws://127.0.0.1:{port}/agent"
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.parametrize("status", [401, 403])
async def test_start_raises_instead_of_retrying(status: int) -> None:
    async with _refusing_server(status) as url:
        wire = MultiplexedWire(WireConfig(url=url, headers={"Authorization": "Bearer sk_wrong"}))
        with pytest.raises(AuthRejected) as caught:
            await asyncio.wait_for(wire.start(), timeout=3.0)

    assert caught.value.status == status
    # The message has to name the thing the operator can act on.
    assert str(status) in str(caught.value)
    assert "sk_" in str(caught.value)
    # Existing callers catch PermanentClose; that must keep working.
    assert isinstance(caught.value, PermanentClose)


async def test_agent_run_surfaces_the_rejection() -> None:
    async with _refusing_server(401) as url:
        agent = CortexAgent(
            api_key="sk_revoked",
            version="1.0.0",
            cortex_url=url,
            factory=lambda emitter: RecordingAdapter(emitter),
        )
        with pytest.raises(AuthRejected):
            await asyncio.wait_for(agent.run(), timeout=3.0)


async def test_a_server_that_is_merely_down_still_retries() -> None:
    """The narrow fix must not turn every connect failure terminal."""
    wire = MultiplexedWire(
        WireConfig(
            url="ws://127.0.0.1:1/agent",  # nothing listens on port 1
            initial_backoff_seconds=0.01,
            max_backoff_seconds=0.01,
        )
    )
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(wire.start(), timeout=0.3)
    await wire.close()
