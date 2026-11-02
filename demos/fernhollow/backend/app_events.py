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
    "ConfirmResult",
    "FernhollowEvent",
    "FilterChanged",
    "FiltersIn",
    "PageViewed",
    "ProductViewed",
    "RoomBoardEdited",
    "ShortlistChanged",
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


class VisibleProducts(AppEvent):
    """The products the grid or strip now shows, in screen order."""

    product_ids: list[str] = Field(default_factory=list[str])
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
    """The shopper's answer on the Add-to-cart confirmation."""

    confirmed: bool = False
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
)
