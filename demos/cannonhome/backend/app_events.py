"""What the visitor's tabs report — the page→brain half of the screen contract.

The other direction is the :class:`~voqalize.sdk.Action` classes in
``brain.py``. These are sent by the extension on cannonhome.cl, and they fire
for the visitor's own clicks as well as for Javier's moves, so his picture of
their screen is true whoever moved it.

**Prices and stock come only from here.** The brain never fetches the store
(its servers cannot reach it, and the HTML it serves is cached for hours): the
extension reads a product's price and stock in the visitor's browser, from the
page and then from the store's own uncached GraphQL, and reports both. A
``graphql`` read wins over a ``page`` read of the same product.

The site is Cannon Home's, not ours, and it changes without asking. So the
nested shapes are plain models that ignore a field they do not know, while the
events themselves are strict: a new field on a page report is harmless, a new
event is a change we want to hear about.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from voqalize.sdk import AppEvent, AppEvents

__all__ = [
    "CANNONHOME_EVENTS",
    "CannonHomeEvent",
    "CartItem",
    "CartState",
    "CommandDone",
    "CommandFailed",
    "LanguageRequested",
    "ListingItem",
    "ListingShown",
    "PageChanged",
    "PriceItem",
    "PricesRead",
    "ProductShown",
    "SearchSuggest",
    "SuggestItem",
    "TabInfo",
    "TabsChanged",
]


PageKind = Literal["home", "category", "search", "product", "cart", "page"]


class PageChanged(AppEvent):
    """The tab in front changed page, or came to the front: what is on it now."""

    site: str = "site"
    url: str = ""
    path: str
    title: str = ""
    kind: PageKind = "page"
    """``category`` a listing, ``search`` a search result, ``product`` a product
    page, ``cart`` /checkout/cart, ``page`` anything else."""
    headings: list[str] = Field(default_factory=list[str])
    """The page's headings, in order (at most 80)."""
    faqs: list[str] = Field(default_factory=list[str])
    """The FAQ questions on the page (at most 120)."""
    plans: list[str] = Field(default_factory=list[str])
    """Named things on the page to ring by name (kept for the brain's matcher)."""


class TabInfo(BaseModel):
    tab_id: str
    url: str = ""
    title: str = ""


class TabsChanged(AppEvent):
    """Every Cannon Home tab the visitor has open, and the one in front."""

    tabs: list[TabInfo] = Field(default_factory=list[TabInfo])
    active: str = ""


class CommandFailed(AppEvent):
    """A move Javier sent could not be carried out on the page."""

    command: str
    error: str = ""
    reason: str = ""
    """The same as ``error``: the sibling extensions name it ``reason``."""

    @property
    def why(self) -> str:
        return self.error or self.reason or "failed"


class CommandDone(AppEvent):
    """A move Javier sent was carried out: the page now shows what he asked."""

    command: str
    detail: str = ""
    """What is on screen now, in a few English words."""


class LanguageRequested(AppEvent):
    """The visitor pressed the other language on the widget's toggle."""

    language: Literal["en", "es"]


class ProductShown(AppEvent):
    """A product page is in front: what it shows, read in the visitor's
    browser. Sent on load from the page (``source`` ``page``: the HTML may be
    hours old) and again once the store's GraphQL confirms it (``graphql``,
    live): the second one wins."""

    path: str
    sku: str = ""
    name: str = ""
    price: int | None = None
    """The final price, CLP."""
    regular_price: int | None = None
    """The price before a discount, CLP, when there is one."""
    in_stock: bool | None = None
    qty: int | None = None
    specs: dict[str, str] = Field(default_factory=dict[str, str])
    """The Especificaciones tab: label → value."""
    rating: float | None = None
    reviews: int | None = None
    source: Literal["page", "graphql"] = "page"


class ListingItem(BaseModel):
    name: str
    path: str
    price: int | None = None
    regular_price: int | None = None


class ListingShown(AppEvent):
    """A category or search listing is in front, after a load or a filter."""

    path: str
    title: str = ""
    count: int | None = None
    filters: dict[str, str] = Field(default_factory=dict[str, str])
    """The filters applied: request var → label (``tamano`` → ``King``)."""
    sort: str = ""
    items: list[ListingItem] = Field(default_factory=list[ListingItem])
    """The cards on screen, in order (at most 30)."""


class SuggestItem(BaseModel):
    name: str
    path: str
    price: int | None = None


class SearchSuggest(AppEvent):
    """The search box's suggestions for what was typed in it."""

    query: str
    items: list[SuggestItem] = Field(default_factory=list[SuggestItem])
    categories: list[str] = Field(default_factory=list[str])


class PriceItem(BaseModel):
    path: str
    sku: str = ""
    name: str = ""
    price: int | None = None
    regular_price: int | None = None
    in_stock: bool | None = None
    qty: int | None = None


class PricesRead(AppEvent):
    """The live prices and stock ``check_prices`` asked for, from the store's
    GraphQL. ``missing`` are the paths it could not find."""

    items: list[PriceItem] = Field(default_factory=list[PriceItem])
    missing: list[str] = Field(default_factory=list[str])


class CartItem(BaseModel):
    name: str
    path: str = ""
    qty: int = 1
    price: int | None = None


class CartState(AppEvent):
    """The visitor's cart, after an add (whoever made it) or when shown."""

    items: list[CartItem] = Field(default_factory=list[CartItem])
    count: int = 0
    subtotal: int | None = None
    free_shipping_left: int | None = None
    """What is left to spend for free shipping (Región Metropolitana only)."""


type CannonHomeEvent = (
    PageChanged
    | TabsChanged
    | CommandDone
    | CommandFailed
    | LanguageRequested
    | ProductShown
    | ListingShown
    | SearchSuggest
    | PricesRead
    | CartState
)

CANNONHOME_EVENTS = AppEvents[CannonHomeEvent](
    PageChanged,
    TabsChanged,
    CommandDone,
    CommandFailed,
    LanguageRequested,
    ProductShown,
    ListingShown,
    SearchSuggest,
    PricesRead,
    CartState,
)
