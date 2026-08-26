"""The umbrella, over HTTP, on the route Voqalize actually dials.

Every other demo test builds a brain by hand and hosts it on a bare socket. This
one starts the whole umbrella app under uvicorn and dials
``ws://…/sugar?session_id=…`` — the same URL shape, the same query parameter, the
same ``Authorization`` header a production session carries. The route is the one
piece nothing else covers, and the one that stayed on a retired path shape
(``/{name}/s/{session_id}``) long after the wire had moved, because a harness that
calls ``run_session`` directly never dials a URL at all.

Plus the discovery/wiring checks that keep a malformed backend out of startup.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
from collections.abc import AsyncIterator

import pytest
import uvicorn
from voqalize_demos.discovery import build_for, discover
from voqalize_demos.umbrella import create_app
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

from voqalize.conformance import (
    DirectConnection,
    VoqalizeDriver,
    checks,
    generate_keypair,
    mint_voqalize_token,
)

SESSION_ID = "route-conformance"


@contextlib.asynccontextmanager
async def umbrella(monkeypatch: pytest.MonkeyPatch, public_pem: str) -> AsyncIterator[int]:
    """The real umbrella app on an ephemeral port, trusting ``public_pem``.

    ``GEMINI_API_KEY`` is set because a brain builds its client at construction;
    nothing here reaches the model — the greeting is a written line."""
    monkeypatch.setenv("GEMINI_API_KEY", "not-used-no-model-call-here")
    monkeypatch.setenv("VOQALIZE_BRAIN_PUBKEYS", public_pem)
    server = uvicorn.Server(
        uvicorn.Config(create_app(), host="127.0.0.1", port=0, log_level="warning")
    )
    task = asyncio.create_task(server.serve())
    try:
        while not server.started:
            await asyncio.sleep(0.01)
        yield server.servers[0].sockets[0].getsockname()[1]
    finally:
        server.should_exit = True
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(task, timeout=5.0)


async def test_a_demo_greets_over_its_own_route(monkeypatch: pytest.MonkeyPatch) -> None:
    """A session dialled at ``/sugar?session_id=…`` greets.

    ``DirectConnection`` appends the query parameter itself, exactly as Voqalize
    does, so the URL under test is the deployed one and not a tidier equivalent."""
    keypair = generate_keypair()
    async with umbrella(monkeypatch, keypair.public_pem) as port:
        driver = VoqalizeDriver(
            DirectConnection(
                f"ws://127.0.0.1:{port}/sugar",
                SESSION_ID,
                token=mint_voqalize_token(
                    private_key_pem=keypair.private_pem,
                    session_id=SESSION_ID,
                    agent_id="sugar",
                    tenant_id="demo",
                ),
            ),
            session_id=SESSION_ID,
            default_timeout=10.0,
        )
        await driver.open()
        try:
            greeting = await driver.start_session(init={"scenario": {"patient": {"name": "Asha"}}})
            checks.check_greeting(driver, greeting)
            assert greeting is not None
            assert greeting.text == "Hi there! Your evening check-in — how did today go?"
        finally:
            await driver.aclose()


async def test_a_dial_without_a_session_id_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """The session is the query parameter, and it is required.

    Without it the route has no session to run, so the handshake is refused rather
    than opening a socket that can never be finished."""
    keypair = generate_keypair()
    async with umbrella(monkeypatch, keypair.public_pem) as port:
        with pytest.raises(InvalidStatus) as refused:
            await connect(f"ws://127.0.0.1:{port}/sugar")
    assert refused.value.response.status_code == 403


async def test_the_retired_path_shape_is_gone(monkeypatch: pytest.MonkeyPatch) -> None:
    """``/{name}/s/{session_id}`` was the shape before the session moved to the
    query string. Nothing answers there — a brain is one ordinary route now."""
    keypair = generate_keypair()
    async with umbrella(monkeypatch, keypair.public_pem) as port:
        with pytest.raises(InvalidStatus) as refused:
            await connect(f"ws://127.0.0.1:{port}/sugar/s/{SESSION_ID}?session_id={SESSION_ID}")
    assert refused.value.response.status_code == 403


# ─── Discovery / wiring ────────────────────────────────────────────────────────


def test_discovery_finds_co_located_backends():
    """Every ``demos/<name>/backend/`` is discovered with a name, router, factory."""
    demos = discover()
    assert demos, "at least one demo backend must be discovered"
    for demo in demos:
        assert demo.name and demo.router is not None and demo.build is not None


def test_travel_is_discovered():
    names = {d.name for d in discover()}
    assert "travel" in names


def test_umbrella_app_builds():
    """The umbrella constructs and mounts a brain route per discovered demo.

    FastAPI mounts each included router lazily, so assert on the built health
    payload (which lists the mounted demos) rather than the raw route table."""
    from starlette.testclient import TestClient

    app = create_app()
    with TestClient(app) as client:
        body = client.get("/_healthz").json()
    assert body["ok"] is True
    assert "travel" in body["demos"]


def test_healthz_reports_the_build_commit(monkeypatch: pytest.MonkeyPatch):
    """``/_healthz`` carries the commit the image was built from.

    The post-deploy gate asserts this equals the tag it just pushed, which is the
    only thing separating a real gate from a liveness ping: an old container that
    was never replaced answers ``/_healthz`` perfectly well. Outside a built image
    there is no build-arg, and the field reads ``"unknown"`` rather than being
    absent — an absent field would compare equal to nothing and quietly disarm the
    gate."""
    from starlette.testclient import TestClient
    from voqalize_demos import umbrella

    with TestClient(create_app()) as client:
        assert client.get("/_healthz").json()["git_sha"] == "unknown"

    # The SHA is read once at import, the way a baked-in build-arg is, so the
    # populated path only exists after a reload under the env var — and a reload
    # back afterwards, or every later test in this process sees a fake commit.
    monkeypatch.setenv("VOQALIZE_GIT_SHA", "deadbee")
    try:
        importlib.reload(umbrella)
        with TestClient(umbrella.create_app()) as client:
            assert client.get("/_healthz").json()["git_sha"] == "deadbee"
    finally:
        monkeypatch.undo()
        importlib.reload(umbrella)


def test_unknown_demo_has_no_backend():
    """An unknown name has no discovered backend — ``build_for`` raises KeyError."""
    with pytest.raises(KeyError):
        build_for("does-not-exist")
