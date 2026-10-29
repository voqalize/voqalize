"""What the visitor's tabs report — the page→brain half of the screen contract.

The other direction is Stage's moves and the two Actions in ``brain.py``.
These are sent by the extension on www.pcfactory.cl, and they fire for the
visitor's own clicks as well as for Javier's moves, so his picture of their
screen is true whoever moved it. Each of his moves is answered by Stage's own
``stage_result``, parsed here beside the site's events.

**The state on their screen is Stage state.** The product page, the listing,
the cart and the checkout's step are slices of ``pcfactory/scene.json`` (the
listing and the cart are the ``commerce`` kit's); the page sends each change as
a named ``stage_event`` (``listing.filtered``, ``cart.changed``), the brain
folds it into its mirror, and the model hears one line naming the act. The
models below for those slices are the brain's typed *views* of the mirror
(``listing_view`` and the rest), never sent on the wire.

**Prices and stock come only from here.** The brain never fetches the store:
the extension reads a product's prices and stock in the visitor's browser, from
the page and from the store's own public catalogue reads, and reports them.
Three prices travel together: ``price`` (Transferencia / Débito, the headline),
``card_price`` (otros medios de pago) and ``regular_price`` (the struck
reference). All are integers in CLP; stock is the store's own string ("+100",
"5", "0"). A product's ``path`` is always ``/producto/<id>``.

The site is pcFactory's, not ours, and it changes without asking. So the
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
    "PCFACTORY_EVENTS",
    "CartItem",
    "CartState",
    "CheckoutState",
    "CompareItem",
    "CompareShown",
    "ComparisonItem",
    "ComparisonRow",
    "ComparisonShown",
    "FacetState",
    "FoundItem",
    "LanguageRequested",
    "ListingItem",
    "ListingShown",
    "PageChanged",
    "PcFactoryEvent",
    "PriceItem",
    "PricesRead",
    "ProductShown",
    "ProductsFound",
    "StockRead",
    "StoreShown",
    "StoreStock",
    "TabInfo",
    "TabsChanged",
    "cart_view",
    "checkout_view",
    "comparison_view",
    "listing_view",
    "product_view",
]


PageKind = Literal[
    "home", "category", "search", "product", "cart", "checkout", "stores", "help", "compare", "page"
]


class PageChanged(AppEvent):
    """The tab in front changed page, or came to the front: what is on it now."""

    site: str = "site"
    url: str = ""
    path: str
    title: str = ""
    kind: PageKind = "page"
    """``category`` a listing (a category, or a curated list
    ``/busqueda?productos=…``), ``search`` the search results, ``product`` a
    product page, ``cart`` /carro, ``checkout`` /checkout/…, ``stores``
    /tiendas, ``help`` the Centro de ayuda, ``compare`` the comparison page
    (/comparador), ``page`` anything else."""
    headings: list[str] = Field(default_factory=list[str])
    """The page's headings, in order, as it renders them."""
    faqs: list[str] = Field(default_factory=list[str])
    """The FAQ questions on the page."""


class TabInfo(BaseModel):
    tab_id: str
    url: str = ""
    title: str = ""


class TabsChanged(AppEvent):
    """Every PC Factory tab the visitor has open, and the one in front."""

    tabs: list[TabInfo] = Field(default_factory=list[TabInfo])
    active: str = ""


class LanguageRequested(AppEvent):
    """The visitor pressed the other language on the widget's toggle."""

    language: Literal["en", "es"]


class PriceItem(BaseModel):
    path: str
    id: int | None = None
    name: str = ""
    price: int | None = None
    """Transferencia / Débito, CLP."""
    card_price: int | None = None
    """Otros medios de pago (credit card), CLP."""
    regular_price: int | None = None
    """The struck reference price, CLP."""
    online_stock: str = ""


class PricesRead(AppEvent):
    """The live prices and online stock ``check_prices`` asked for. ``missing``
    are the paths the store could not price."""

    items: list[PriceItem] = Field(default_factory=list[PriceItem])
    missing: list[str] = Field(default_factory=list[str])


class FoundItem(BaseModel):
    path: str
    id: int | None = None
    name: str = ""
    brand: str = ""
    price: int | None = None
    card_price: int | None = None
    regular_price: int | None = None
    stock: str = ""


class ProductsFound(AppEvent):
    """What ``find_products`` read from the store's own catalogue search: up to
    eight products with their live prices and stock, and how many match."""

    query: str | None = None
    category_id: int | None = None
    brand: str | None = None
    min_price: int | None = None
    max_price: int | None = None
    total: int | None = None
    items: list[FoundItem] = Field(default_factory=list[FoundItem])


class StoreStock(BaseModel):
    name: str
    zone: str = ""
    qty: str = ""
    pickup: bool | None = None


class StockRead(AppEvent):
    """One product's stock in every store (only those with units) and online,
    as ``check_stock`` read it; ``asked`` is the store the visitor asked about,
    ``matched`` the store's name it matched, if any."""

    path: str
    id: int | None = None
    name: str = ""
    online: str = ""
    stores: list[StoreStock] = Field(default_factory=list[StoreStock])
    asked: str | None = None
    matched: str | None = None


class StoreShown(AppEvent):
    """A store's card on /tiendas, opened by ``stores.show``."""

    name: str
    address: str = ""
    city: str = ""
    region: str = ""
    zone: str = ""
    hours: str = ""
    """As the map card writes them; empty when it showed none."""


class CompareItem(BaseModel):
    path: str
    name: str = ""


class CompareShown(AppEvent):
    """The store's comparator bar ("Comparador (n/3)"), with the products in
    it; the comparison page itself is the ``compare`` slice."""

    items: list[CompareItem] = Field(default_factory=list[CompareItem])


# ─── The brain's views of the mirror ───────────────────────────────────────────


class ProductShown(BaseModel):
    """A product page is in front: what it shows. Sent on load from the page
    (``source`` ``page``) and again from the store's live read (``api``):
    the second one wins."""

    path: str
    id: int | None = None
    name: str = ""
    brand: str = ""
    price: int | None = None
    card_price: int | None = None
    regular_price: int | None = None
    online_stock: str = ""
    stores_with_stock: int | None = None
    warranty: str = ""
    promo_until: str = ""
    specs: dict[str, str] = Field(default_factory=dict[str, str])
    """The Especificaciones tab: label → value, in order."""
    source: Literal["page", "api"] = "page"


class ListingItem(BaseModel):
    name: str
    path: str
    price: int | None = None
    regular_price: int | None = None


class FacetState(BaseModel):
    """One facet group of the listing: the options checked, and those offered."""

    facet: str
    on: list[str] = Field(default_factory=list[str])
    options: list[str] = Field(default_factory=list[str])


class ListingShown(BaseModel):
    """A category or search listing is in front, after a load, a filter or a sort."""

    path: str
    title: str = ""
    count: int | None = None
    facets: list[FacetState] = Field(default_factory=list[FacetState])
    sort: str = ""
    items: list[ListingItem] = Field(default_factory=list[ListingItem])
    """The cards on screen, in grid order (at most 12)."""

    @property
    def filters(self) -> dict[str, str]:
        """The filters on: facet → its checked options joined by ", "."""
        return {f.facet: ", ".join(f.on) for f in self.facets if f.on}


class ComparisonItem(BaseModel):
    path: str
    name: str = ""
    brand: str = ""
    price: int | None = None
    """Transferencia, CLP."""
    card_price: int | None = None
    regular_price: int | None = None


class ComparisonRow(BaseModel):
    group: str = ""
    label: str
    values: list[str] = Field(default_factory=list[str])
    """Left to right, as the products; ``""`` where one has none."""


class ComparisonShown(BaseModel):
    """The comparison page (/comparador) is in front: its products and the
    specification rows with a value, in the table's order."""

    path: str = "/comparador"
    category: str = ""
    items: list[ComparisonItem] = Field(default_factory=list[ComparisonItem])
    rows: list[ComparisonRow] = Field(default_factory=list[ComparisonRow])
    differs: list[str] = Field(default_factory=list[str])
    """The labels of the rows whose values differ."""
    highlighted: bool = False
    """Whether Destacar diferencias is on."""

    def row(self, label: str) -> ComparisonRow | None:
        return next((r for r in self.rows if r.label == label), None)


class CartItem(BaseModel):
    name: str
    path: str = ""
    qty: int = 1
    price: int | None = None


class CartState(BaseModel):
    """The visitor's cart, after a change (whoever made it) or when shown."""

    items: list[CartItem] = Field(default_factory=list[CartItem])
    count: int = 0
    subtotal: int | None = None
    """The Transferencia / Débito total."""


class CheckoutState(BaseModel):
    """Where they are in the checkout. Javier goes as far as Tipo de entrega
    (``delivery``); choosing there, and everything after, is the visitor's."""

    step: Literal["login", "delivery", "payment", "other"] = "other"
    options: list[str] = Field(default_factory=list[str])
    chosen: str = ""


type PcFactoryEvent = (
    PageChanged
    | TabsChanged
    | LanguageRequested
    | PricesRead
    | ProductsFound
    | StockRead
    | StoreShown
    | CompareShown
    | StageResult
    | StageHello
    | StageProgress
    | StageEvent
)

PCFACTORY_EVENTS = AppEvents[PcFactoryEvent](
    PageChanged,
    TabsChanged,
    LanguageRequested,
    PricesRead,
    ProductsFound,
    StockRead,
    StoreShown,
    CompareShown,
    StageResult,
    StageHello,
    StageProgress,
    StageEvent,
)


def _num(value: Any) -> int | None:
    return round(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _rows(value: Any) -> list[Mapping[str, Any]]:
    return [v for v in value if isinstance(v, Mapping)] if isinstance(value, list) else []  # pyright: ignore[reportUnknownVariableType]


def _strings(value: Any) -> list[str]:
    return [str(v) for v in value] if isinstance(value, list) else []  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]


def _text(value: Any) -> str:
    return (
        str(value) if isinstance(value, str | int | float) and not isinstance(value, bool) else ""
    )


def product_view(value: Mapping[str, Any]) -> ProductShown:
    """The ``product`` slice, as the brain's rules read it."""
    return ProductShown(
        path=str(value.get("path") or ""),
        id=_num(value.get("id")),
        name=str(value.get("name") or ""),
        brand=_text(value.get("brand")),
        price=_num(value.get("price")),
        card_price=_num(value.get("card_price")),
        regular_price=_num(value.get("regular_price")),
        online_stock=_text(value.get("online_stock")),
        stores_with_stock=_num(value.get("stores_with_stock")),
        warranty=_text(value.get("warranty")),
        promo_until=_text(value.get("promo_until")),
        specs={
            str(r.get("label", "")): str(r.get("value", ""))
            for r in _rows(value.get("specs"))
            if r.get("label")
        },
        source="api" if value.get("source") == "api" else "page",
    )


def listing_view(value: Mapping[str, Any]) -> ListingShown:
    """The kit's ``listing`` slice, as the brain's rules read it."""
    return ListingShown(
        path=str(value.get("path") or ""),
        title=str(value.get("title") or ""),
        count=_num(value.get("count")),
        facets=[
            FacetState(
                facet=str(f.get("facet", "")),
                on=_strings(f.get("on")),
                options=_strings(f.get("options")),
            )
            for f in _rows(value.get("filters"))
            if f.get("facet")
        ],
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
    )


def checkout_view(value: Mapping[str, Any]) -> CheckoutState:
    """The ``checkout`` slice, as the brain's rules read it."""
    step = value.get("step")
    return CheckoutState(
        step=step if step in ("login", "delivery", "payment", "other") else "other",
        options=_strings(value.get("options")),
        chosen=_text(value.get("chosen")),
    )


def comparison_view(value: Mapping[str, Any]) -> ComparisonShown:
    """The ``compare`` slice, as the brain's rules read it."""
    return ComparisonShown(
        path=str(value.get("path") or "/comparador"),
        category=_text(value.get("category")),
        items=[
            ComparisonItem(
                path=str(i.get("path") or ""),
                name=str(i.get("name") or ""),
                brand=_text(i.get("brand")),
                price=_num(i.get("price")),
                card_price=_num(i.get("card_price")),
                regular_price=_num(i.get("regular_price")),
            )
            for i in _rows(value.get("items"))
        ],
        rows=[
            ComparisonRow(
                group=_text(r.get("group")),
                label=str(r.get("label")),
                values=_strings(r.get("values")),
            )
            for r in _rows(value.get("rows"))
            if r.get("label")
        ],
        differs=_strings(value.get("differs")),
        highlighted=value.get("highlighted") is True,
    )
