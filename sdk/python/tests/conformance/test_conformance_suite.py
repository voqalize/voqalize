"""The conformance harness, self-validated.

Runs the full scenario catalog (:mod:`voqalize.conformance`) against the
bundled cooperating reference brain (:class:`ConformanceBrain`), hosted over a
real ``DirectAgent`` WebSocket on an ephemeral port. Because the reference brain
is a *known-good* implementation of every protocol path, a green run proves the
driver + checks are internally consistent — which is the precondition for
pointing them at a real brain under test (the ADK / GenAI SDKs to come).

This mirrors ``tests/direct/test_direct_end_to_end.py``: real server stack, real
TCP, agent started inline in the async test (``asyncio_mode = auto``). The one
difference is who drives the socket — here it is the conformance ``VoiceDriver``
impersonating PyGato, not a hand-rolled per-test client.
"""

from __future__ import annotations

import pytest

from voqalize.conformance import generate_keypair, run_suite
from voqalize.conformance.reference import ConformanceBrain
from voqalize.conformance.scenarios import CATALOG
from voqalize.sdk import DirectAgent, brain_factory


async def _host_verified() -> tuple[DirectAgent, int, bytes]:
    """Host the reference brain verifying against a fresh keypair; return the
    private half so the driver can mint a matching pygato token."""
    keypair = generate_keypair()
    agent = DirectAgent(
        factory=brain_factory(ConformanceBrain),
        host="127.0.0.1",
        port=0,
        public_keys=keypair.public_pem,
    )
    port = await agent.start()
    return agent, port, keypair.private_pem


@pytest.mark.parametrize("name", [s.name for s in CATALOG])
async def test_scenario_conformant(name: str) -> None:
    """Each catalogued scenario passes against the reference brain."""
    agent, port, private_key_pem = await _host_verified()
    try:
        report = await run_suite(
            f"ws://127.0.0.1:{port}",
            private_key_pem=private_key_pem,
            only=[name],
        )
    finally:
        await agent.aclose()
    assert report.results, f"scenario {name!r} did not run"
    result = report.results[0]
    assert result.passed, result.traceback or result.error


async def test_full_suite_reports_conformant() -> None:
    """The whole catalog runs green and the report says CONFORMANT."""
    agent, port, private_key_pem = await _host_verified()
    try:
        report = await run_suite(
            f"ws://127.0.0.1:{port}",
            private_key_pem=private_key_pem,
        )
    finally:
        await agent.aclose()
    assert report.ok, "\n" + report.summary()
    assert report.failed == 0
    assert report.passed == len(CATALOG)


async def test_wire_level_subset_against_unverified_brain() -> None:
    """The wire-level tier (no reference grammar, no auth) passes against a brain
    running ``allow_unverified`` and no token — the surface a shipped brain like
    ``welcome`` would be pointed at."""
    agent = DirectAgent(
        factory=brain_factory(ConformanceBrain),
        host="127.0.0.1",
        port=0,
        allow_unverified=True,
    )
    port = await agent.start()
    try:
        report = await run_suite(
            f"ws://127.0.0.1:{port}",
            private_key_pem=None,
            include_reference=False,
            include_auth=False,
        )
    finally:
        await agent.aclose()
    assert report.ok, "\n" + report.summary()
    # It really did run a subset, not the whole thing.
    assert 0 < len(report.results) < len(CATALOG)


async def test_wrong_key_is_rejected_directly() -> None:
    """A token signed by the wrong key is rejected with close code 4000 — the
    auth MUST, asserted at the connection level (not just via the scenario)."""
    from voqalize.conformance import DirectConnection, VoiceDriver, mint_pygato_token

    _agent_kp = generate_keypair()  # what the brain verifies against
    wrong_kp = generate_keypair()  # what the driver (wrongly) signs with
    agent = DirectAgent(
        factory=brain_factory(ConformanceBrain),
        host="127.0.0.1",
        port=0,
        public_keys=_agent_kp.public_pem,
    )
    port = await agent.start()
    session_id = "conf-wrongkey"
    token = mint_pygato_token(
        private_key_pem=wrong_kp.private_pem,
        session_id=session_id,
        agent_id="a",
        tenant_id="t",
    )
    driver = VoiceDriver(
        DirectConnection(f"ws://127.0.0.1:{port}", session_id, token=token),
        session_id=session_id,
        agent_id="a",
    )
    try:
        await driver.open()
        code = await driver.wait_closed(timeout=3.0)
    finally:
        await driver.aclose()
        await agent.aclose()
    assert code == 4000
