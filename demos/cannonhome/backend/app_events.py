"""What the visitor's tabs report — the page→brain half of the screen contract.

The other direction is Stage's moves and the two Actions in ``brain.py``.
These are sent by the extension on cannonhome.cl, and they fire for the
visitor's own clicks as well as for Javier's moves, so his picture of their
screen is true whoever moved it. Each of his moves is answered by Stage's own
``stage_result``, parsed here beside the site's events.

**The state on their screen is Stage state.** The product page, the listing,
the search box's suggestions, the cart and the delivery form are slices of
``cannonhome/scene.json`` (the listing and the cart are the ``commerce`` kit's);
the page sends each change as a named ``stage_event`` (``listing.filtered``,
``cart.changed``), the brain folds it into its mirror, and the model hears one
line naming the act. The models below for those slices are the brain's typed
*views* of the mirror (``listing_view`` and the rest), never sent on the wire.

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

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, Field

from voqalize.sdk import AppEvent, AppEvents
from voqalize.sdk.stage import StageEvent, StageHello, StageProgress, StageResult

__all__ = [
    "CANNONHOME_EVENTS",
    "CannonHomeEvent",
    "CartItem",
    "CartState",
    "CheckoutInvalid",
    "CheckoutState",
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
    "cart_view",
    "listing_view",
    "product_view",
    "suggest_view",
]


PageKind = Literal["home", "category", "search", "product", "cart", "checkout", "page"]


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


class LanguageRequested(AppEvent):
    """The visitor pressed the other language on the widget's toggle."""

    language: Literal["en", "es"]


class ProductShown(BaseModel):
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


class ListingShown(BaseModel):
    """A category or search listing is in front, after a load or a filter."""

    path: str
    title: str = ""
    count: int | None = None
    filters: dict[str, str] = Field(default_factory=dict[str, str])
    """The filters applied: request var → label (``tamano`` → ``King``); several
    options of one filter, the labels joined by ", " (``color`` → ``Beige, Blanco``)."""
    sort: str = ""
    items: list[ListingItem] = Field(default_factory=list[ListingItem])
    """The cards on screen, in order (at most 30)."""


class SuggestItem(BaseModel):
    name: str
    path: str
    price: int | None = None


class SearchSuggest(BaseModel):
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


class CartState(BaseModel):
    """The visitor's cart, after an add (whoever made it) or when shown."""

    items: list[CartItem] = Field(default_factory=list[CartItem])
    count: int = 0
    subtotal: int | None = None
    free_shipping_left: int | None = None
    """What is left to spend for free shipping (Región Metropolitana only)."""


#: The checkout's delivery-form fields, by the names the brain fills them
#: with; ``rut`` and ``delivery`` are the visitor's own, reported by name only.
CheckoutFieldName = Literal[
    "email",
    "first_name",
    "last_name",
    "rut",
    "phone",
    "region",
    "comuna",
    "street",
    "number",
    "apartment",
    "delivery",
]


class CheckoutInvalid(BaseModel):
    field: str
    message: str = ""
    """The site's own validation text for the field, as it shows it."""


class CheckoutState(BaseModel):
    """The checkout's delivery form (/checkout, the guest's one-page checkout):
    on load and after each change, whoever made it (debounced by the page).

    **Names, not values.** What the visitor typed stays on their screen: the
    form reports which fields hold something, never what, apart from the
    región and comuna chosen (the site's own option names). The RUT, any
    password and anything of the payment step are never read at all; ``rut``
    is named in ``filled`` or ``missing`` only so he knows whether they have
    typed it."""

    filled: list[str] = Field(default_factory=list[str])
    """The fields that hold something (see :data:`CheckoutFieldName`)."""
    missing: list[str] = Field(default_factory=list[str])
    """The required fields still empty, in the form's order."""
    invalid: list[CheckoutInvalid] = Field(default_factory=list[CheckoutInvalid])
    """The fields the form flags, with its message."""
    region: str = ""
    comuna: str = ""
    email_has_account: bool = False
    """The email belongs to an account: the site shows a password field to sign
    in. That is a login, and it is the visitor's."""
    delivery_options: list[str] = Field(default_factory=list[str])
    """The delivery methods offered once a comuna is chosen ("Despacho a
    domicilio", "Retiro en Tienda")."""
    delivery: str = ""
    """The delivery method the visitor chose, if any."""
    payment_open: bool = False
    """Whether the payment step (Método de Pago) shows its options: past the
    form, and the visitor's alone."""


type CannonHomeEvent = (
    PageChanged
    | TabsChanged
    | LanguageRequested
    | PricesRead
    | StageResult
    | StageHello
    | StageProgress
    | StageEvent
)

CANNONHOME_EVENTS = AppEvents[CannonHomeEvent](
    PageChanged,
    TabsChanged,
    LanguageRequested,
    PricesRead,
    StageResult,
    StageHello,
    StageProgress,
    StageEvent,
)


# ─── The brain's views of the mirror ───────────────────────────────────────────


def _num(value: Any) -> int | None:
    return round(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _rows(value: Any) -> list[Mapping[str, Any]]:
    return [v for v in value if isinstance(v, Mapping)] if isinstance(value, list) else []  # pyright: ignore[reportUnknownVariableType]


def _strings(value: Any) -> list[str]:
    return [str(v) for v in value] if isinstance(value, list) else []  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]


def product_view(value: Mapping[str, Any]) -> ProductShown:
    """The ``product`` slice, as the brain's rules read it."""
    return ProductShown(
        path=str(value.get("path") or ""),
        sku=str(value.get("sku") or ""),
        name=str(value.get("name") or ""),
        price=_num(value.get("price")),
        regular_price=_num(value.get("regular_price")),
        in_stock=value.get("in_stock") if isinstance(value.get("in_stock"), bool) else None,
        qty=_num(value.get("qty")),
        specs={str(r.get("label", "")): str(r.get("value", "")) for r in _rows(value.get("specs"))},
        rating=float(value["rating"]) if isinstance(value.get("rating"), int | float) else None,
        reviews=_num(value.get("reviews")),
        source="graphql" if value.get("source") == "graphql" else "page",
    )


def listing_view(value: Mapping[str, Any]) -> ListingShown:
    """The kit's ``listing`` slice, as the brain's rules read it: each filter
    on, by its request variable, its options joined as the store writes them."""
    return ListingShown(
        path=str(value.get("path") or ""),
        title=str(value.get("title") or ""),
        count=_num(value.get("count")),
        filters={
            str(f.get("facet", "")): ", ".join(_strings(f.get("on")))
            for f in _rows(value.get("filters"))
            if _strings(f.get("on"))
        },
        sort=str(value.get("sort") or ""),
        items=[
            ListingItem(
                name=str(i.get("name", "")),
                path=str(i.get("path", "")),
                price=_num(i.get("price")),
                regular_price=_num(i.get("regular_price")),
            )
            for i in _rows(value.get("items"))
        ],
    )


def suggest_view(value: Mapping[str, Any]) -> SearchSuggest:
    """The ``search`` slice, as the brain's rules read it."""
    return SearchSuggest(
        query=str(value.get("query") or ""),
        items=[
            SuggestItem(
                name=str(i.get("name", "")), path=str(i.get("path", "")), price=_num(i.get("price"))
            )
            for i in _rows(value.get("items"))
        ],
        categories=_strings(value.get("categories")),
    )


def cart_view(value: Mapping[str, Any]) -> CartState:
    """The kit's ``cart`` slice, as the brain's rules read it."""
    return CartState(
        items=[
            CartItem(
                name=str(i.get("name", "")),
                path=str(i.get("path") or ""),
                qty=_num(i.get("qty")) or 1,
                price=_num(i.get("price")),
            )
            for i in _rows(value.get("items"))
        ],
        count=_num(value.get("count")) or 0,
        subtotal=_num(value.get("subtotal")),
        free_shipping_left=_num(value.get("free_shipping_left")),
    )
