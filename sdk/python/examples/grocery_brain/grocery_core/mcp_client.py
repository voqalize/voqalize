"""The Swiggy Instamart MCP, wrapped so it is HIDDEN from the agent.

The agent never sees `search_products` / `update_cart`. Instead the resolver
(deterministic Python) calls these typed methods in the background.
``SwiggyMcp`` calls a live OpenAI-Agents-SDK ``MCPServerStreamableHttp`` via
``call_tool`` and parses the JSON into our models.
"""

from __future__ import annotations

import json
from typing import Protocol

from .models import Address, Product, Variant


class GroceryMcp(Protocol):
    async def get_addresses(self) -> list[Address]: ...
    async def search_products(self, address_id: str, query: str) -> list[Product]: ...
    async def add_to_cart(self, spin_id: str, quantity: int) -> bool: ...


def _parse_products(data: dict) -> list[Product]:
    out: list[Product] = []
    for p in data.get("products", []):
        variants = tuple(
            Variant(
                spin_id=v.get("spinId", ""),
                qty_desc=v.get("quantityDescription", ""),
                mrp=float((v.get("price") or {}).get("mrp", 0) or 0),
                offer_price=float((v.get("price") or {}).get("offerPrice", 0) or 0),
                image_url=v.get("imageUrl", ""),
                in_stock=bool(v.get("isInStockAndAvailable", True)),
            )
            for v in p.get("variations", [])
        )
        if not variants:
            continue
        out.append(
            Product(
                product_id=p.get("productId", ""),
                name=p.get("displayName", ""),
                brand=p.get("brand") or "",
                variants=variants,
                is_promoted=bool(p.get("isPromoted", False)),
                in_stock=bool(p.get("inStock", True)),
            )
        )
    return out


class SwiggyMcp:
    """Direct, agent-invisible access to the live Swiggy Instamart MCP."""

    def __init__(self, server, address_id: str = "") -> None:
        self._server = server  # agents.mcp.MCPServerStreamableHttp (already connected)
        self.address_id = address_id

    @staticmethod
    def _json(result) -> dict:
        if getattr(result, "structuredContent", None):
            sc = result.structuredContent
            if isinstance(sc, dict) and ("products" in sc or "addresses" in sc):
                return sc
        for block in getattr(result, "content", []) or []:
            text = getattr(block, "text", None)
            if text:
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    continue
        return {}

    async def get_addresses(self) -> list[Address]:
        res = await self._server.call_tool("get_addresses", {})
        data = self._json(res)
        return [
            Address(id=a.get("id", ""), line=a.get("addressLine", ""), tag=a.get("addressTag", ""))
            for a in data.get("addresses", [])
            if a.get("id")
        ]

    async def search_products(self, address_id: str, query: str) -> list[Product]:
        res = await self._server.call_tool(
            "search_products", {"addressId": address_id, "query": query}
        )
        return _parse_products(self._json(res))

    async def add_to_cart(self, spin_id: str, quantity: int) -> bool:
        # update_cart's exact param names are verified against the live schema
        # before real checkout is wired.
        res = await self._server.call_tool("update_cart", {"spinId": spin_id, "quantity": quantity})
        return not getattr(res, "isError", False)
