"""Canonical past-orders catalog for the Voqal "Returns Assistant" demo.

Single source of truth for the support brain's prompt and tool returns — the
orders, items, and prompt helpers ``SupportBrain`` serves. The UI mirrors it in
``frontend/src/support/catalog.ts`` for rendering — the ``id`` values here MUST
stay in sync with that file.

Three delivered orders cover the demo: a phone order, a phone + case order, and
an accessories order that contains the **Bluetooth lavalier microphone**
(``bt-mic-pro``) the returns flow is built around.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

ItemKind = Literal["phone", "accessory"]


class Item(TypedDict):
    id: str
    name: str
    brand: str
    price: int  # USD
    kind: ItemKind
    # Short description with the keywords a shopper might say out loud, so the
    # model can map "my bluetooth mic" → the right line item.
    description: str


class OrderLine(TypedDict):
    item_id: str
    qty: int


class Order(TypedDict):
    id: str
    placed_on: str  # human date, e.g. "May 28, 2026"
    status: str  # "Delivered"
    delivered_on: str
    lines: list[OrderLine]


# ── Items (line items across all orders) ──────────────────────────────────────
ITEMS: list[Item] = [
    {
        "id": "bt-mic-pro",
        "name": "AudioPro Clip Wireless Lavalier Mic",
        "brand": "AudioPro",
        "price": 79,
        "kind": "accessory",
        "description": (
            "Bluetooth wireless clip-on lavalier microphone for phones and "
            "cameras. Pairs over Bluetooth; has a small LED that blinks blue "
            "while pairing and turns solid when connected. Charges in its case."
        ),
    },
    {
        "id": "buds-sonic",
        "name": "SonicBuds Pro Wireless Earbuds",
        "brand": "SonicBuds",
        "price": 129,
        "kind": "accessory",
        "description": "Active-noise-cancelling Bluetooth in-ear earbuds with a charging case.",
    },
    {
        "id": "charger-65w",
        "name": "VoltEdge 65W USB-C Fast Charger",
        "brand": "VoltEdge",
        "price": 39,
        "kind": "accessory",
        "description": "65W USB-C GaN wall charger / power adapter for fast charging phones and laptops.",
    },
    {
        "id": "pixel-8-pro",
        "name": "Google Pixel 8 Pro",
        "brand": "Google",
        "price": 999,
        "kind": "phone",
        "description": "Google's flagship phone with the Tensor G3 chip and AI camera.",
    },
    {
        "id": "case-pixel8pro",
        "name": "Pixel 8 Pro Armor Case",
        "brand": "Voqal",
        "price": 29,
        "kind": "accessory",
        "description": "Protective shockproof case / cover for the Pixel 8 Pro.",
    },
    {
        "id": "galaxy-a55",
        "name": "Samsung Galaxy A55",
        "brand": "Samsung",
        "price": 449,
        "kind": "phone",
        "description": "Mid-range Samsung phone with a 120Hz AMOLED screen.",
    },
]

_ITEMS_BY_ID: dict[str, Item] = {i["id"]: i for i in ITEMS}


# ── Orders (most recent first) ────────────────────────────────────────────────
ORDERS: list[Order] = [
    {
        "id": "VQ-10588",
        "placed_on": "May 28, 2026",
        "status": "Delivered",
        "delivered_on": "May 31, 2026",
        "lines": [
            {"item_id": "bt-mic-pro", "qty": 1},
            {"item_id": "buds-sonic", "qty": 1},
            {"item_id": "charger-65w", "qty": 1},
        ],
    },
    {
        "id": "VQ-10432",
        "placed_on": "May 12, 2026",
        "status": "Delivered",
        "delivered_on": "May 15, 2026",
        "lines": [
            {"item_id": "pixel-8-pro", "qty": 1},
            {"item_id": "case-pixel8pro", "qty": 1},
        ],
    },
    {
        "id": "VQ-10301",
        "placed_on": "April 21, 2026",
        "status": "Delivered",
        "delivered_on": "April 24, 2026",
        "lines": [
            {"item_id": "galaxy-a55", "qty": 1},
        ],
    },
]

_ORDERS_BY_ID: dict[str, Order] = {o["id"]: o for o in ORDERS}

VALID_ORDER_IDS: list[str] = [o["id"] for o in ORDERS]
VALID_ITEM_IDS: list[str] = [i["id"] for i in ITEMS]


# ── Lookups ───────────────────────────────────────────────────────────────────
def get_item(item_id: str) -> Item | None:
    return _ITEMS_BY_ID.get(item_id)


def get_order(order_id: str) -> Order | None:
    return _ORDERS_BY_ID.get(order_id)


def order_total(order: Order) -> int:
    total = 0
    for line in order["lines"]:
        item = get_item(line["item_id"])
        if item is not None:
            total += item["price"] * line["qty"]
    return total


def item_summary(item: Item) -> dict[str, Any]:
    return {"id": item["id"], "name": item["name"], "price": item["price"], "kind": item["kind"]}


def order_detail(order: Order) -> dict[str, Any]:
    """Full order shape for a tool return — items resolved, total computed."""
    return {
        "id": order["id"],
        "placed_on": order["placed_on"],
        "status": order["status"],
        "delivered_on": order["delivered_on"],
        "total": order_total(order),
        "items": [
            {**item_summary(item), "qty": line["qty"]}
            for line in order["lines"]
            if (item := get_item(line["item_id"])) is not None
        ],
    }


def orders_for_prompt() -> str:
    """A compact, model-readable listing of every order and its line items.

    Lets the model resolve a spoken reference ("my bluetooth mic") to the right
    order + item id for the tool arguments.
    """
    blocks: list[str] = []
    for order in ORDERS:
        lines = []
        for line in order["lines"]:
            item = get_item(line["item_id"])
            if item is None:
                continue
            lines.append(
                f"    - {item['name']} [{item['id']}] — ${item['price']}: {item['description']}"
            )
        items_text = "\n".join(lines)
        blocks.append(
            f"Order {order['id']} — placed {order['placed_on']}, "
            f"{order['status'].lower()} {order['delivered_on']}:\n{items_text}"
        )
    return "\n".join(blocks)
