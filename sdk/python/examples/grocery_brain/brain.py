"""GroceryBrain — voice shopping list over the Swiggy Instamart MCP.

The cortex-mode brain for the Swiggy/Zepto demo, on the ergonomic Brain SDK +
the OpenAI Agents SDK. The MCP is HIDDEN from the agent: the agent only sees our
fast tools (``grocery_core.tools``), which note items instantly and resolve them
to real SKUs in the BACKGROUND, pushing live updates to the on-screen shopping
list. See grocery_core/ for the core.

The browser pastes a real Swiggy access token, ferried in
``session.init["swiggy_token"]`` → the live Swiggy Instamart MCP.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from agents import Agent, Runner
from agents.mcp import MCPServerStreamableHttp
from grocery_core import (
    ALL_TOOLS,
    GroceryService,
    SwiggyMcp,
    build_system_prompt,
)
from loguru import logger
from openai.types.responses import ResponseTextDeltaEvent

from voqalize.sdk import AppEvent, Brain, Interaction, Session, SessionStart

SWIGGY_MCP_URL = "https://mcp.swiggy.com/im"
MODEL = os.environ.get("GROCERY_MODEL", "gpt-5.4-mini")
MCP_TIMEOUT_S = 30.0


def _extract_token(init: dict) -> str | None:
    raw = init.get("swiggy_token")
    if not isinstance(raw, str) or not raw.strip():
        return None
    raw = raw.strip()
    if raw.startswith("{"):
        try:
            return json.loads(raw).get("access_token")
        except (ValueError, AttributeError):
            return None
    if raw.lower().startswith("bearer "):
        return raw[7:].strip()
    return raw


def _pick_address(addresses):
    for a in addresses:
        if (a.tag or "").lower() == "home":
            return a
    return addresses[0] if addresses else None


@dataclass
class _Live:
    """The fully-wired session: built once, only after the MCP, address, and
    agent are all in hand. Every field is non-null by construction, so the
    handlers never re-check for None — a live session simply *exists* or it
    doesn't (``GroceryBrain._live``)."""

    mcp_server: MCPServerStreamableHttp
    service: GroceryService
    agent: Agent

    async def respond(self, bracket, history: list[Any]) -> None:
        """Run the agent and stream its text into one bot-speech inference."""
        async with bracket as inf:
            result = Runner.run_streamed(self.agent, input=history, context=self.service)
            async for event in result.stream_events():
                data = getattr(event, "data", None)
                if event.type == "raw_response_event" and isinstance(data, ResponseTextDeltaEvent):
                    await inf.speak(data.delta)

    async def aclose(self) -> None:
        await self.service.aclose()
        await _close_server(self.mcp_server)


class GroceryBrain(Brain):
    """One instance per session (built fresh by the SDK's brain_factory).

    ``_live`` is ``None`` only while we're still connecting (or if startup
    failed); once set it is a fully-initialized :class:`_Live`."""

    def __init__(self) -> None:
        self._live: _Live | None = None

    # ── session lifecycle ──
    async def on_session_start(self, session: Session, start: SessionStart) -> None:
        token = _extract_token(start.init)
        if not token:
            await _say(
                session, "I couldn't find your Swiggy token — paste it on the page and start again."
            )
            return

        try:
            server = await _connect_mcp(token)
        except Exception:
            logger.exception("grocery: MCP connect failed")
            await _say(session, _TOKEN_ERROR)
            return

        mcp = SwiggyMcp(server)
        try:
            addresses = await mcp.get_addresses()
        except Exception:
            logger.exception("grocery: get_addresses failed")
            await _close_server(server)
            await _say(session, _TOKEN_ERROR)
            return

        address = _pick_address(addresses)
        if address is None:
            await _close_server(server)
            await _say(
                session,
                "You don't have a saved delivery address on Swiggy yet — add one and come back.",
            )
            return

        service = GroceryService(mcp, address.id, notify=lambda e: _emit_ui(session, e))
        service.push_reset(address.short)
        agent = Agent(
            name="Grocery Guide",
            instructions=build_system_prompt(address.short),
            model=MODEL,
            tools=ALL_TOOLS,
        )
        self._live = _Live(mcp_server=server, service=service, agent=agent)
        logger.info("grocery: session {} ready (address={})", session.id, address.short)
        await _say(
            session,
            f"Hi! I'm your Grocery Guide, delivering to {address.short}. "
            "Just tell me what you need and I'll build your list.",
        )

    async def on_interaction(self, interaction: Interaction) -> None:
        live = self._live
        if live is None:
            async with interaction.inference() as inf:
                await inf.speak("One moment — I'm still connecting to your account.")
            return
        history = [
            {"role": m.role, "content": m.content} for m in interaction.conversation.messages
        ]
        await live.respond(interaction.inference(), history)

    async def on_app_event(self, session: Session, event: AppEvent) -> None:
        """Browser → brain taps: clarify / remove / quantity / checkout."""
        logger.info("grocery: app_event name={} data={}", event.name, event.data)
        live = self._live
        if live is None or event.name != "grocery_action":
            return
        svc = live.service
        action = event.data.get("action")
        item_id = str(event.data.get("item_id", ""))
        if action == "clarify":
            svc.clarify(item_id, str(event.data.get("choice", "")))
        elif action == "remove":
            svc.remove(item_id)
        elif action == "set_quantity":
            svc.set_quantity(item_id, int(event.data.get("quantity", 1)))
        elif action == "checkout":
            await svc.checkout()

    async def on_session_end(self, session: Session) -> None:
        if self._live is not None:
            await self._live.aclose()
            self._live = None


# ── module helpers (no per-call state — capability arrives via `session`) ──

_TOKEN_ERROR = (
    "I couldn't reach your Swiggy account — your token may have expired. "
    "Please generate a fresh one and try again."
)


async def _connect_mcp(token: str) -> MCPServerStreamableHttp:
    server = MCPServerStreamableHttp(
        name="swiggy-instamart",
        params={
            "url": SWIGGY_MCP_URL,
            "headers": {"Authorization": f"Bearer {token}"},
            "timeout": MCP_TIMEOUT_S,
        },
        cache_tools_list=True,
        client_session_timeout_seconds=MCP_TIMEOUT_S,
    )
    await server.connect()
    return server


async def _close_server(server: MCPServerStreamableHttp) -> None:
    try:
        await server.cleanup()
    except Exception:
        logger.exception("grocery: MCP cleanup failed")


async def _say(session: Session, text: str) -> None:
    async with session.inference() as inf:
        await inf.speak(text)


def _emit_ui(session: Session, event: dict) -> None:
    """Push a ui_command to the browser via the session-scoped action primitive.

    Works from tools AND out-of-interaction background tasks (the resolver
    finishes after the triggering interaction has ended) — actions are
    session-scoped and floor-free. ``event`` is ``{"action": name, **args}``."""
    data = dict(event)
    name = str(data.pop("action", ""))
    session.action(name, data)
