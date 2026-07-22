"""Domain models for the voice shopping list.

These are provider-neutral: the Swiggy MCP JSON is parsed into ``Product`` /
``Variant`` (see ``mcp_client``), and the shopping list is a list of ``Item``
each moving through a small state machine as background resolution runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


@dataclass(frozen=True)
class Variant:
    """One purchasable pack size of a product (the unit the cart speaks in)."""

    spin_id: str  # the id update_cart needs
    qty_desc: str  # "1 kg", "500 ml x 4"
    mrp: float
    offer_price: float
    image_url: str = ""
    in_stock: bool = True

    @property
    def discount_pct(self) -> int:
        if self.mrp <= 0 or self.offer_price >= self.mrp:
            return 0
        return round((self.mrp - self.offer_price) / self.mrp * 100)

    @property
    def is_multipack(self) -> bool:
        return " x " in f" {self.qty_desc.lower()} "


@dataclass(frozen=True)
class Product:
    """A catalog product with one or more pack-size variants."""

    product_id: str
    name: str
    brand: str
    variants: tuple[Variant, ...]
    is_promoted: bool = False
    in_stock: bool = True

    @property
    def default_variant(self) -> Variant | None:
        """A sensible single pack to propose: cheapest non-multipack in stock."""
        avail = [v for v in self.variants if v.in_stock]
        if not avail:
            return None
        singles = [v for v in avail if not v.is_multipack]
        return min(singles or avail, key=lambda v: v.offer_price)


@dataclass(frozen=True)
class Address:
    id: str
    line: str
    tag: str = ""

    @property
    def short(self) -> str:
        """A speakable label, e.g. 'Home' or the first chunk of the line."""
        return self.tag or self.line.split(",")[0].strip()


class ItemState(StrEnum):
    DRAFT = "draft"  # noted, not yet searched
    RESOLVING = "resolving"  # background search in flight
    NEEDS_CLARIFICATION = "needs_clarification"  # several plausible matches
    MATCHED = "matched"  # one confident SKU picked automatically
    CONFIRMED = "confirmed"  # user (or clarification) locked the SKU
    UNAVAILABLE = "unavailable"  # nothing found


# States that carry a chosen SKU and count toward checkout.
CARTABLE = (ItemState.MATCHED, ItemState.CONFIRMED)


@dataclass
class Candidate:
    """A ranked product+variant option for an item."""

    product: Product
    variant: Variant
    score: float = 0.0

    @property
    def label(self) -> str:
        return f"{self.product.name} ({self.variant.qty_desc})"

    @property
    def price(self) -> float:
        return self.variant.offer_price

    def to_ui(self) -> dict:
        return {
            "product_id": self.product.product_id,
            "spin_id": self.variant.spin_id,
            "name": self.product.name,
            "brand": self.product.brand,
            "qty_desc": self.variant.qty_desc,
            "price": self.variant.offer_price,
            "mrp": self.variant.mrp,
            "discount_pct": self.variant.discount_pct,
            "image_url": self.variant.image_url,
            "promoted": self.product.is_promoted,
        }


@dataclass
class Item:
    """One line on the shopping list, noted as-is then resolved in the background."""

    id: str
    raw_text: str  # what the customer said: "atta", "2 packs of dahi"
    quantity: int = 1
    state: ItemState = ItemState.DRAFT
    candidates: list[Candidate] = field(default_factory=list)
    chosen: Candidate | None = None
    note: str = ""  # clarification question or status line

    @property
    def line_total(self) -> float:
        return round(self.chosen.price * self.quantity, 2) if self.chosen else 0.0

    def to_ui(self) -> dict:
        return {
            "id": self.id,
            "raw_text": self.raw_text,
            "quantity": self.quantity,
            "state": self.state.value,
            "note": self.note,
            "chosen": self.chosen.to_ui() if self.chosen else None,
            "candidates": [c.to_ui() for c in self.candidates],
            "line_total": self.line_total,
        }
