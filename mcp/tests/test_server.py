"""Server wiring: the expected tools register and dispatch to the client.

We inject a client backed by a fake control plane (httpx.MockTransport) and
drive tools through FastMCP's ``call_tool`` so the whole path — tool arg schema
→ client method → wire — is exercised, not just the client in isolation.
"""

from __future__ import annotations

import httpx
import pytest
from voqalize_mcp.client import ControlPlaneClient
from voqalize_mcp.config import Config
from voqalize_mcp.server import build_server

from tests.test_client import BASE, TENANT, FakeControlPlane

EXPECTED_TOOLS = {
    "whoami",
    "list_agents",
    "get_agent",
    "create_agent",
    "set_brain_url",
    "update_agent",
    "archive_agent",
    "create_api_key",
    "list_api_keys",
    "revoke_api_key",
}


def _server(cp: FakeControlPlane):
    config = Config(api_base=BASE, tenant=TENANT, management_key="mk_live_secret")
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(cp.handler),
        headers={"Authorization": f"Bearer {config.management_key}"},
        base_url=BASE,
    )
    return build_server(config, client=ControlPlaneClient(config, http=http))


@pytest.fixture
def cp() -> FakeControlPlane:
    return FakeControlPlane()


async def test_all_expected_tools_registered(cp):
    tools = await _server(cp).list_tools()
    assert {t.name for t in tools} == EXPECTED_TOOLS


async def test_no_observability_tools_registered(cp):
    """tail_logs / get_metrics belong to a separate track — must not leak in here."""
    names = {t.name for t in await _server(cp).list_tools()}
    assert not (names & {"tail_logs", "get_metrics", "query_logs"})


async def test_create_agent_tool_dispatches(cp):
    cp.on(
        "POST",
        "agents.create",
        lambda r: (200, {"agent": {"id": "a1"}, "agent_secret": "ak_x", "cortex_url": "wss://c"}),
    )
    result = await _server(cp).call_tool("create_agent", {"name": "Bot"})
    # FastMCP returns (content, structured) or a content list depending on version;
    # the fake control plane recording is the ground truth for dispatch.
    assert cp.requests, "create_agent tool did not reach the control plane"
    assert cp.last().url.path == f"/api/v1/{TENANT}/agents.create"
    assert result is not None


async def test_set_brain_url_tool_round_trips(cp):
    cp.on("GET", "agents.get", lambda r: (200, {"id": "a1", "configuration": None}))
    cp.on("POST", "agents.update", lambda r: (200, {"id": "a1"}))
    await _server(cp).call_tool("set_brain_url", {"agent_id": "a1", "brain_url": "wss://b"})
    ops = [r.url.path.rsplit("/", 1)[-1] for r in cp.requests]
    assert ops == ["agents.get", "agents.update"]  # read-modify-write
