"""GroceryService — the shopping list + background resolution orchestration.

The agent's tools call these fast, non-blocking methods. ``add_items`` creates
draft rows and returns immediately; the slow MCP search runs in a background
task per item, and every state change is pushed to the UI via ``notify``.
"""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import Callable

from . import resolver
from .mcp_client import GroceryMcp
from .models import CARTABLE, Item, ItemState

# A UI event sink: receives {"action": ..., ...} dicts. Fire-and-forget, sync.
Notify = Callable[[dict], None]


def _clarify_note(item: Item) -> str:
    opts = " or ".join(c.product.name for c in item.candidates[:3])
    return f"Which one — {opts}?"


class GroceryService:
    def __init__(self, mcp: GroceryMcp, address_id: str, notify: Notify | None = None) -> None:
        self._mcp = mcp
        self.address_id = address_id
        self._notify = notify or (lambda _e: None)
        self.items: dict[str, Item] = {}
        self._order: list[str] = []
        self._tasks: set[asyncio.Task] = set()

    # ── ordering helpers ──
    def ordered(self) -> list[Item]:
        return [self.items[i] for i in self._order if i in self.items]

    def _new_id(self) -> str:
        return "it_" + secrets.token_hex(3)

    # ── mutations the tools call (all fast / non-blocking) ──
    def add_items(self, texts: list[str]) -> list[Item]:
        """Note items as-is instantly; resolve each in the background."""
        created: list[Item] = []
        for text in texts:
            name = (text or "").strip()
            if not name:
                continue
            item = Item(id=self._new_id(), raw_text=name, state=ItemState.RESOLVING)
            self.items[item.id] = item
            self._order.append(item.id)
            created.append(item)
            self._push(item)
            self._spawn(self._resolve(item.id))
        return created

    async def _resolve(self, item_id: str) -> None:
        item = self.items.get(item_id)
        if item is None:
            return
        try:
            products = await self._mcp.search_products(self.address_id, item.raw_text)
        except Exception:
            item.state = ItemState.UNAVAILABLE
            item.note = "couldn't search right now"
            self._push(item)
            return
        if item.id not in self.items:  # removed mid-flight
            return
        candidates = resolver.rank(item.raw_text, products)
        state, chosen, shortlist = resolver.decide(candidates)
        item.state = state
        item.candidates = shortlist
        item.chosen = chosen
        if state == ItemState.NEEDS_CLARIFICATION:
            item.note = _clarify_note(item)
        elif state == ItemState.UNAVAILABLE:
            item.note = "not found nearby"
        else:
            item.note = ""
        self._push(item)

    def clarify(self, item_id: str, choice: str | int) -> Item | None:
        item = self.items.get(item_id)
        if item is None or not item.candidates:
            return None
        cand = resolver.pick(item.candidates, choice)
        if cand is None:
            return None
        item.chosen = cand
        item.state = ItemState.CONFIRMED
        item.candidates = []
        item.note = ""
        self._push(item)
        return item

    def confirm(self, item_id: str) -> Item | None:
        item = self.items.get(item_id)
        if item is None or item.chosen is None:
            return None
        item.state = ItemState.CONFIRMED
        item.note = ""
        self._push(item)
        return item

    def set_quantity(self, item_id: str, quantity: int) -> Item | None:
        item = self.items.get(item_id)
        if item is None:
            return None
        item.quantity = max(1, int(quantity))
        self._push(item)
        return item

    def remove(self, item_id: str) -> bool:
        if item_id not in self.items:
            return False
        del self.items[item_id]
        self._order = [i for i in self._order if i != item_id]
        self._notify({"action": "grocery_remove", "item_id": item_id})
        return True

    def pending_clarifications(self) -> list[Item]:
        return [i for i in self.ordered() if i.state == ItemState.NEEDS_CLARIFICATION]

    def cart_items(self) -> list[Item]:
        return [i for i in self.ordered() if i.state in CARTABLE and i.chosen]

    def total(self) -> float:
        return round(sum(i.line_total for i in self.cart_items()), 2)

    async def checkout(self) -> dict:
        """Push every cartable item to the Swiggy cart. Returns a summary."""
        added, failed = 0, 0
        for item in self.cart_items():
            assert item.chosen is not None
            try:
                ok = await self._mcp.add_to_cart(item.chosen.variant.spin_id, item.quantity)
            except Exception:
                ok = False
            added += 1 if ok else 0
            failed += 0 if ok else 1
        summary = {
            "action": "grocery_checkout",
            "added": added,
            "failed": failed,
            "total": self.total(),
        }
        self._notify(summary)
        return summary

    # ── snapshots / lifecycle ──
    def snapshot(self) -> list[dict]:
        return [i.to_ui() for i in self.ordered()]

    def _push(self, item: Item) -> None:
        self._notify({"action": "grocery_item", "item": item.to_ui()})

    def push_reset(self, address: str = "") -> None:
        self._notify({"action": "grocery_reset", "address": address})

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def aclose(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
