"""Explore the live Swiggy Instamart catalog and emit a system-prompt tree.

A separate offline program (the agent never runs this). It runs one search per
seed category against the real MCP, aggregates the leading brands and ₹ price
bands, and prints a compact catalog tree sized for the system-prompt budget.
Paste the output into grocery_core/catalog.py (CATALOG_TREE) to refresh it with
current, address-specific data.

    # uses ~/.swiggy/tokens.json (see swiggy_oauth_spike); pick an address:
    backend/.venv/bin/python backend/agent-sdk/examples/grocery_brain/build_catalog_prompt.py
"""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from pathlib import Path

from agents.mcp import MCPServerStreamableHttp
from grocery_core import SwiggyMcp
from grocery_core.models import Product

SWIGGY_MCP_URL = "https://mcp.swiggy.com/im"
TOKENS_PATH = Path.home() / ".swiggy" / "tokens.json"

# Seed queries grouped by the category line they feed in the tree.
SEEDS: dict[str, list[str]] = {
    "Staples": ["atta", "basmati rice", "toor dal", "sugar"],
    "Dairy & Eggs": ["milk", "curd", "paneer", "eggs"],
    "Fruits & Vegetables": ["onion", "tomato", "banana"],
    "Snacks & Munchies": ["chips", "biscuits", "namkeen"],
    "Cold Drinks & Juices": ["soft drink", "juice", "water"],
    "Instant & Packaged": ["noodles", "sauce"],
    "Frozen & Sweet": ["ice cream", "chocolate"],
    "Home & Personal Care": ["detergent", "dishwash"],
}


def _band(products: list[Product]) -> str:
    prices = [v.offer_price for p in products for v in p.variants if v.in_stock and v.offer_price]
    if not prices:
        return ""
    return f"₹{int(min(prices))}-{int(max(prices))}"


async def main() -> None:
    if not TOKENS_PATH.exists():
        raise SystemExit(
            f"No token at {TOKENS_PATH} — run swiggy_oauth_spike/run.py generate first."
        )
    token = json.loads(TOKENS_PATH.read_text())["access_token"]

    server = MCPServerStreamableHttp(
        name="swiggy",
        params={
            "url": SWIGGY_MCP_URL,
            "headers": {"Authorization": f"Bearer {token}"},
            "timeout": 30,
        },
        client_session_timeout_seconds=30,
    )
    await server.connect()
    try:
        mcp = SwiggyMcp(server)
        addresses = await mcp.get_addresses()
        if not addresses:
            raise SystemExit("No saved addresses on this account.")
        addr = addresses[0]
        print(f"# Catalog tree from live Swiggy data — delivering to {addr.short}\n")
        print("SWIGGY INSTAMART CATALOG — top brands and ₹ bands:\n")
        for category, queries in SEEDS.items():
            lines: list[str] = []
            for q in queries:
                products = await mcp.search_products(addr.id, q)
                brands = [
                    b for b, _ in Counter(p.brand for p in products if p.brand).most_common(4)
                ]
                if brands:
                    lines.append(f"{q}: {', '.join(brands)} {_band(products)}".rstrip())
            print(f"• {category}")
            for line in lines:
                print(f"  - {line}")
    finally:
        await server.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
