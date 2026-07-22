"""ControlPlaneClient over a fake control plane (httpx.MockTransport).

The fake records every request and returns canned JSON, so we assert the wire
contract this client depends on: the ``/api/v1/{tenant}/operation.name`` path,
the ``Bearer mk_`` header, ``Idempotency-Key`` on agent mutations (and its
ABSENCE on api_keys routes), the read-modify-write in ``set_brain_url``, and
error-envelope unwrapping.
"""

from __future__ import annotations

import json

import httpx
import pytest
from voqalize_mcp.client import ControlPlaneClient, ControlPlaneError
from voqalize_mcp.config import Config

TENANT = "acme"
BASE = "http://cp.test"


class FakeControlPlane:
    """Routes (method, operation) -> handler(request) -> (status, body)."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self._routes: dict[tuple[str, str], object] = {}

    def on(self, method: str, operation: str, handler):
        self._routes[(method, operation)] = handler
        return self

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        operation = request.url.path.rsplit("/", 1)[-1]
        route = self._routes.get((request.method, operation))
        if route is None:
            return httpx.Response(404, json={"error": {"code": "not_found", "message": operation}})
        status, body = route(request)
        return httpx.Response(status, json=body)

    def last(self) -> httpx.Request:
        return self.requests[-1]


def _client(cp: FakeControlPlane) -> ControlPlaneClient:
    config = Config(api_base=BASE, tenant=TENANT, management_key="mk_live_secret")
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(cp.handler),
        headers={"Authorization": f"Bearer {config.management_key}"},
        base_url=BASE,
    )
    return ControlPlaneClient(config, http=http)


@pytest.fixture
def cp() -> FakeControlPlane:
    return FakeControlPlane()


async def test_list_agents_path_and_auth(cp):
    cp.on("GET", "agents.list", lambda r: (200, {"items": [{"id": "a1"}], "next_cursor": None}))
    client = _client(cp)
    page = await client.list_agents(limit=5)
    assert page["items"] == [{"id": "a1"}]
    req = cp.last()
    assert req.url.path == f"/api/v1/{TENANT}/agents.list"
    assert req.url.params["limit"] == "5"
    assert "status" not in req.url.params  # None dropped by _clean
    assert req.headers["Authorization"] == "Bearer mk_live_secret"
    await client.aclose()


async def test_create_agent_sends_idempotency_key_and_brain_url(cp):
    cp.on(
        "POST",
        "agents.create",
        lambda r: (200, {"agent": {"id": "a1"}, "agent_secret": "ak_x", "cortex_url": "wss://c"}),
    )
    client = _client(cp)
    resp = await client.create_agent(name="Bot", brain_url="wss://brain.example.com")
    assert resp["agent_secret"] == "ak_x"
    req = cp.last()
    assert req.headers.get("Idempotency-Key")  # mutation → key present
    body = json.loads(req.content)
    assert body == {
        "name": "Bot",
        "configuration": {"deployment": {"brain_url": "wss://brain.example.com"}},
    }
    await client.aclose()


async def test_set_brain_url_preserves_existing_config(cp):
    existing = {
        "schema_version": "1",
        "stt": {"provider": "vql-speech", "language": "fr"},
        "tts": {"voice": "omnivoice/gaurav"},
        "deployment": {"brain_url": "wss://old"},
    }
    cp.on("GET", "agents.get", lambda r: (200, {"id": "a1", "configuration": existing}))
    cp.on("POST", "agents.update", lambda r: (200, {"id": "a1"}))
    client = _client(cp)
    await client.set_brain_url("a1", "wss://new.example.com")
    body = json.loads(cp.last().content)
    assert body["agent_id"] == "a1"
    cfg = body["configuration"]
    assert cfg["deployment"]["brain_url"] == "wss://new.example.com"
    assert cfg["stt"]["language"] == "fr"  # untouched
    assert cfg["tts"]["voice"] == "omnivoice/gaurav"  # untouched
    await client.aclose()


async def test_set_brain_url_with_no_prior_config(cp):
    cp.on("GET", "agents.get", lambda r: (200, {"id": "a1", "configuration": None}))
    cp.on("POST", "agents.update", lambda r: (200, {"id": "a1"}))
    client = _client(cp)
    await client.set_brain_url("a1", "wss://new")
    body = json.loads(cp.last().content)
    assert body["configuration"] == {"deployment": {"brain_url": "wss://new"}}
    await client.aclose()


async def test_api_keys_create_has_no_idempotency_key(cp):
    cp.on(
        "POST", "api_keys.create", lambda r: (200, {"id": "k1", "raw": "pk_live_x", "role": None})
    )
    client = _client(cp)
    await client.create_api_key(kind="publishable", label="web", allowed_origins=["https://a.com"])
    req = cp.last()
    assert "Idempotency-Key" not in req.headers  # api_keys routes aren't mutations
    assert json.loads(req.content)["allowed_origins"] == ["https://a.com"]
    await client.aclose()


async def test_whoami_reports_tenant(cp):
    cp.on("GET", "agents.list", lambda r: (200, {"items": [{"id": "a1"}, {"id": "a2"}]}))
    client = _client(cp)
    who = await client.whoami()
    assert who["tenant"] == TENANT
    assert who["authenticated"] is True
    assert who["agent_count_hint"] == 2
    await client.aclose()


async def test_error_envelope_unwrapped(cp):
    cp.on(
        "POST",
        "api_keys.create",
        lambda r: (403, {"error": {"code": "not_authorized", "message": "member role"}}),
    )
    client = _client(cp)
    with pytest.raises(ControlPlaneError) as exc:
        await client.create_api_key(kind="secret", label="x")
    assert exc.value.status == 403
    assert exc.value.code == "not_authorized"
    assert "member role" in str(exc.value)
    await client.aclose()


async def test_fastapi_validation_detail_unwrapped(cp):
    detail = [{"loc": ["body", "kind"], "msg": "field required"}]
    cp.on("POST", "agents.create", lambda r: (422, {"detail": detail}))
    client = _client(cp)
    with pytest.raises(ControlPlaneError) as exc:
        await client.create_agent(name="x")
    assert exc.value.status == 422
    assert "body.kind: field required" in str(exc.value)
    await client.aclose()
