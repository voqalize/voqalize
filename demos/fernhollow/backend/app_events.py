"""What the shopper did on the page — the UI→brain half of ``CONTRACT.md``.

The store works by click and tap alone, so the shopper may browse, filter,
pick a finish or edit the room board while Emily is on the call. Each of those
is one small typed :class:`~voqalize.sdk.AppEvent`; the brain folds it into its
picture of the screen (so "this one" and "the second one" mean what is on
screen now) and leaves one line in the model's context. A tap is never a cue
to speak — except the shopper's answer on the Add-to-cart confirmation, which
the brain acts on (it puts the lines in the cart) and still does not talk over.

Every event carries ``by``: ``"visitor"`` when the shopper did it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from voqalize.sdk import AppEvent, AppEvents

__all__ = [
    "FERNHOLLOW_EVENTS",
    "CartChanged",
    "CartLineIn",
    "CheckoutChanged",
    "CheckoutStepReached",
    "ChoiceMade",
    "ConfirmResult",
    "FernhollowEvent",
    "FilterChanged",
    "FiltersIn",
    "LayoutIn",
    "ListingViewed",
    "OrderIn",
    "OrderLineIn",
    "OrdersKnown",
    "PageViewed",
    "Pointing",
    "PriceIn",
    "ProductViewed",
    "RoomBoardEdited",
    "Selection",
    "SelectionCleared",
    "ShortlistChanged",
    "ThingIn",
    "VariantSelected",
    "VisibleProducts",
]


class FiltersIn(BaseModel):
    """The filter chips as the page now holds them."""

    model_config = ConfigDict(extra="ignore")

    room: str | None = None
    category: str | None = None
    materials: list[str] = Field(default_factory=list[str])
    colours: list[str] = Field(default_factory=list[str])
    styles: list[str] = Field(default_factory=list[str])
    price_min: float | None = None
    price_max: float | None = None
    on_sale: bool | None = None


class CartLineIn(BaseModel):
    """One cart line as the page holds it."""

    model_config = ConfigDict(extra="ignore")

    product_id: str
    variant_id: str | None = None
    qty: int = 1


class PageViewed(AppEvent):
    """The shopper opened a page (``home``, ``room/<room>``, ``category/<slug>``,
    ``product/<id>``, ``journal``, ``cart``, ``policy/<topic>``…)."""

    path: str = ""
    by: str = "visitor"


class ProductViewed(AppEvent):
    """The shopper opened a product page."""

    product_id: str = ""
    variant_id: str | None = None
    by: str = "visitor"


class LayoutIn(BaseModel):
    """Where one visible product sits: row and column from the top left."""

    model_config = ConfigDict(extra="ignore")

    product_id: str
    row: int = 0
    col: int = 0


class VisibleProducts(AppEvent):
    """The products the grid or strip now shows, in screen order, with where
    each sits — so "the left one" and "the bottom row" resolve."""

    product_ids: list[str] = Field(default_factory=list[str])
    layout: list[LayoutIn] = Field(default_factory=list[LayoutIn])
    by: str = "visitor"


class Pointing(AppEvent):
    """The product card or page under the shopper's pointer, finger or keyboard
    focus (debounced). Kept for "this one"; never spoken about."""

    product_id: str = ""
    how: str = "hover"  # "hover" | "focus" | "tap"
    by: str = "visitor"


class ThingIn(BaseModel):
    """One thing the shopper circled: a product, category, room or article."""

    model_config = ConfigDict(extra="ignore")

    kind: str = "product"  # "product" | "category" | "room" | "article"
    id: str = ""


class OrderLineIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    product_id: str
    variant_id: str = ""
    title: str = ""
    variant: str = ""
    qty: int = 1
    unit_price: float = 0


class OrderIn(BaseModel):
    """One order the page holds (a placed order counts as delivered when placed)."""

    model_config = ConfigDict(extra="ignore")

    number: str = ""
    email: str = ""
    name: str = ""
    placed_at: str = ""
    lines: list[OrderLineIn] = Field(default_factory=list[OrderLineIn])
    total: float = 0
    status: str = "delivered"
    placed_days_ago: int = 0
    delivered_days_ago: int | None = 0


class OrdersKnown(AppEvent):
    """The orders the page holds — on connect and whenever the list changes. Silent."""

    orders: list[OrderIn] = Field(default_factory=list[OrderIn])
    by: str = "visitor"


class Selection(AppEvent):
    """The shopper circled things on screen (Show Emily: circle to ask). Kept
    until cleared, across pages; acted on only when they speak about it."""

    things: list[ThingIn] = Field(default_factory=list[ThingIn])
    gesture: str = "circle"
    page: str = ""
    by: str = "visitor"


class PriceIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    min: float | None = None
    max: float | None = None


class ListingViewed(AppEvent):
    """A listing page (room, category, sale, search) as it stands: its rail's
    facets and values (the rail's own labels), what is ticked, the price range,
    the sort and the count. Sent on arrival and on every change. Silent."""

    page: str = ""
    title: str = ""
    facets: dict[str, list[str]] = Field(default_factory=dict[str, list[str]])
    active: dict[str, list[str]] = Field(default_factory=dict[str, list[str]])
    price: PriceIn | None = None
    sort: str = "featured"
    count: int = 0
    by: str = "visitor"


class SelectionCleared(AppEvent):
    """The circled selection was cleared (its clear button, Esc, or a new circle)."""

    by: str = "visitor"


class ChoiceMade(AppEvent):
    """The shopper clicked one of the numbered products Emily asked between."""

    product_id: str = ""
    by: str = "visitor"


class CheckoutChanged(AppEvent):
    """The shopper filled or changed a checkout field — its name, never its value."""

    field: str = ""
    by: str = "visitor"


class CheckoutStepReached(AppEvent):
    """The checkout moved to a step: contact, shipping or review."""

    step: str = ""
    by: str = "visitor"


class VariantSelected(AppEvent):
    """The shopper picked an option value on a product."""

    product_id: str = ""
    variant_id: str = ""
    by: str = "visitor"


class FilterChanged(AppEvent):
    """The shopper changed the filter chips."""

    filters: FiltersIn = Field(default_factory=FiltersIn)
    by: str = "visitor"


class RoomBoardEdited(AppEvent):
    """The shopper removed or locked a tile on the room board."""

    slot: str = ""
    action: str = ""  # "remove" | "lock" | "unlock" | "restore"
    by: str = "visitor"


class CartChanged(AppEvent):
    """The cart as it now stands, after the shopper changed it."""

    lines: list[CartLineIn] = Field(default_factory=list[CartLineIn])
    total: float = 0
    by: str = "visitor"


class ConfirmResult(AppEvent):
    """The shopper's answer on a confirmation: Add to cart, or Place order —
    which carries the order number the page used."""

    confirmed: bool = False
    order_number: str | None = None
    by: str = "visitor"


class ShortlistChanged(AppEvent):
    """The shortlist tray as it now stands."""

    product_ids: list[str] = Field(default_factory=list[str])
    by: str = "visitor"


type FernhollowEvent = (
    PageViewed
    | ProductViewed
    | VisibleProducts
    | VariantSelected
    | FilterChanged
    | RoomBoardEdited
    | CartChanged
    | ConfirmResult
    | ShortlistChanged
    | Pointing
    | ChoiceMade
    | CheckoutChanged
    | CheckoutStepReached
    | Selection
    | SelectionCleared
    | OrdersKnown
    | ListingViewed
)

FERNHOLLOW_EVENTS = AppEvents[FernhollowEvent](
    PageViewed,
    ProductViewed,
    VisibleProducts,
    VariantSelected,
    FilterChanged,
    RoomBoardEdited,
    CartChanged,
    ConfirmResult,
    ShortlistChanged,
    Pointing,
    ChoiceMade,
    CheckoutChanged,
    CheckoutStepReached,
    Selection,
    SelectionCleared,
    OrdersKnown,
    ListingViewed,
)
