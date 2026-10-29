"""What the visitor's tabs report — the page→brain half of the screen contract.

The other direction is Stage's moves and the two Actions in ``brain.py``.
These are sent by the extension on www.agroplanet.cl, and they fire for the
visitor's own clicks as well as for Javier's moves, so his picture of their
screen is true whoever moved it. Each of his moves is answered by Stage's own
``stage_result``, parsed here beside the site's events.

**The state on their screen is Stage state.** The product page, the listing,
the cart and the quote form are slices of ``agroplanet/scene.json`` (the
listing and the cart are the ``commerce`` kit's); the page sends each change as
a named ``stage_event`` (``listing.filtered``, ``cart.changed``), the brain
folds it into its mirror, and the model hears one line naming the act. The
models below for those slices are the brain's typed *views* of the mirror
(``listing_view`` and the rest), never sent on the wire.

**Prices and stock come only from here.** The brain never fetches the store:
the extension reads a product's price and stock in the visitor's browser, from
the page and from the store's own public catalogue reads
(``api.agroplanet.cl/webapi``), and reports them. One price is shown per
product (``price``), with ``regular_price`` and ``discount`` when it is on
offer; some products show no price at all ("Confirmar precio en tienda"),
which is ``price_hidden``. The store hides its offers on the pages
(``hideDiscount``): the page shows the full price and the mini-cart's
subtotal applies the offer, which the API carries, reported as
``offer_price`` with its ``discount``. Prices are integers in CLP. Stock is the store's
status (``inStock``, ``lowStock``, ``outOfStock``) and a unit count. A
product's ``path`` is always ``/producto/<slug>/<sku>``; the slug is
decorative and the ``sku`` is what names it.

Agroplanet sells by quote: the cart's only action is Cotizar, which opens the
Formulario de cotización. Its slice carries field *names* only — which are
filled and which are missing — never what the visitor typed.

The site is Agroplanet's, not ours, and it changes without asking. So the
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
    "AGROPLANET_EVENTS",
    "AgroplanetEvent",
    "CartItem",
    "CartState",
    "FacetState",
    "FitBrand",
    "FitRead",
    "FoundItem",
    "LanguageRequested",
    "ListingItem",
    "ListingShown",
    "PageChanged",
    "PriceItem",
    "PricesRead",
    "ProductShown",
    "ProductsFound",
    "QuoteState",
    "RelatedItem",
    "StockRead",
    "StoreShown",
    "StoreStock",
    "TabInfo",
    "TabsChanged",
    "cart_view",
    "listing_view",
    "product_view",
    "quote_view",
]


PageKind = Literal[
    "home", "category", "search", "brand", "product", "cart", "quote", "stores", "policy", "page"
]

StockStatus = Literal["inStock", "lowStock", "outOfStock", ""]


class PageChanged(AppEvent):
    """The tab in front changed page, or came to the front: what is on it now.

    Agroplanet is one Angular app, so this fires on every route change inside
    it as well as on a load."""

    site: str = "site"
    url: str = ""
    path: str
    title: str = ""
    kind: PageKind = "page"
    """``category`` a category listing, ``search`` /busqueda/…, ``brand``
    /marca/…, ``product`` a product page, ``cart`` /carro, ``quote``
    /cotizacion, ``stores`` /nuestras-tiendas, ``policy`` a policy page
    (despacho, devoluciones, garantía…), ``page`` anything else."""
    headings: list[str] = Field(default_factory=list[str])
    """The page's headings, in order, as it renders them."""
    faqs: list[str] = Field(default_factory=list[str])
    """The accordion panel titles on the page."""


class TabInfo(BaseModel):
    tab_id: str
    url: str = ""
    title: str = ""


class TabsChanged(AppEvent):
    """Every Agroplanet tab the visitor has open, and the one in front."""

    tabs: list[TabInfo] = Field(default_factory=list[TabInfo])
    active: str = ""


class LanguageRequested(AppEvent):
    """The visitor pressed the other language on the widget's toggle."""

    language: Literal["en", "es"]


class PriceItem(BaseModel):
    path: str
    sku: str = ""
    name: str = ""
    price: int | None = None
    """What the store charges now, CLP."""
    regular_price: int | None = None
    """The price before the discount, CLP, when there is one."""
    discount: int | None = None
    """Percent off: the struck price's, or the store's offer's."""
    offer_price: int | None = None
    """The store's offer, CLP, when it has one: the page shows ``price``, and
    the cart's subtotal applies this."""
    price_hidden: bool = False
    """The store shows "Confirmar precio en tienda" instead of a price."""
    stock: StockStatus = ""
    stock_level: int | None = None


class PricesRead(AppEvent):
    """The live prices and stock ``check_prices`` asked for. ``missing``
    are the paths the store could not read."""

    items: list[PriceItem] = Field(default_factory=list[PriceItem])
    missing: list[str] = Field(default_factory=list[str])


class FoundItem(BaseModel):
    path: str
    sku: str = ""
    name: str = ""
    brand: str = ""
    price: int | None = None
    regular_price: int | None = None
    discount: int | None = None
    offer_price: int | None = None
    price_hidden: bool = False
    stock: StockStatus = ""
    stock_level: int | None = None


class ProductsFound(AppEvent):
    """What ``find_products`` read from the store's own catalogue search: up to
    eight products with their live prices and stock, and how many match."""

    query: str | None = None
    category_code: str | None = None
    brand: str | None = None
    total: int | None = None
    suggestion: str | None = None
    """The store's own spelling suggestion ("batería"), when it made one."""
    retried_with: str | None = None
    """The words searched instead, when ``query`` found nothing and the store
    suggested a spelling: ``items`` and ``total`` are that search's."""
    items: list[FoundItem] = Field(default_factory=list[FoundItem])


class StoreStock(BaseModel):
    name: str
    city: str = ""
    qty: int | None = None
    status: StockStatus = ""


class StockRead(AppEvent):
    """One product's stock online and in the stores that report it, as
    ``check_stock`` read it; ``asked`` is the store the visitor asked about,
    ``matched`` the store's name it matched, if any."""

    path: str
    sku: str = ""
    name: str = ""
    online: StockStatus = ""
    online_level: int | None = None
    stores: list[StoreStock] = Field(default_factory=list[StoreStock])
    asked: str | None = None
    matched: str | None = None


class FitBrand(BaseModel):
    """One make the part is listed for, with as much below it as was read."""

    brand: str
    count: int | None = None
    """How many machines of that make the catalogue lists it for."""
    models: list[str] = Field(default_factory=list[str])
    years: list[str] = Field(default_factory=list[str])
    engines: list[str] = Field(default_factory=list[str])


class FitRead(AppEvent):
    """Which tractors the store's catalogue lists a part for, as
    ``check_fit`` read it (``product/getPartAppRecords``): the product page
    shows none of it. ``universal`` when the catalogue lists it as UNIVERSAL
    (a generic part, for no one machine); no ``brands`` when it lists no
    machine at all. With a machine asked (``brand``, ``model``, ``year``),
    ``matched`` says whether the catalogue lists it, ``match`` what it
    matched and ``missing`` what it did not."""

    path: str
    sku: str = ""
    name: str = ""
    universal: bool = False
    brands: list[FitBrand] = Field(default_factory=list[FitBrand])
    total: int | None = None
    """How many machines the catalogue lists it for, all makes."""
    brand: str | None = None
    model: str | None = None
    year: str | None = None
    matched: bool | None = None
    match: str | None = None
    missing: str | None = None


class StoreShown(AppEvent):
    """A store's card on /nuestras-tiendas, rung by ``stores.show``."""

    name: str
    address: str = ""
    city: str = ""
    phone: str = ""
    hours: str = ""
    """As the card writes them; empty when it showed none."""


# ─── The brain's views of the mirror ───────────────────────────────────────────


class RelatedItem(BaseModel):
    name: str
    path: str = ""
    price: int | None = None


class ProductShown(BaseModel):
    """A product page is in front: what it shows. Sent on load from the page
    (``source`` ``page``) and again from the store's live read (``api``):
    the second one wins."""

    path: str
    sku: str = ""
    name: str = ""
    brand: str = ""
    maker_code: str = ""
    price: int | None = None
    regular_price: int | None = None
    discount: int | None = None
    price_hidden: bool = False
    stock: str = ""
    stock_level: int | None = None
    offer_price: int | None = None
    """The store's offer, which the cart's subtotal applies; the page shows
    ``price``."""
    description: str = ""
    label: str = ""
    """The badge over the brand ("Venta en Verde")."""
    category: str = ""
    """The breadcrumb: "Maquinaria > Tractor para Venta > 25 HP"."""
    specs: dict[str, str] = Field(default_factory=dict[str, str])
    """Especificaciones: label → value, in order."""
    equivalents: dict[str, str] = Field(default_factory=dict[str, str])
    """Equivalencias: "Equivalencia OEM" → its codes."""
    docs: list[str] = Field(default_factory=list[str])
    """Its data sheets: "Hoja de Seguridad", "Ficha Técnica"."""
    related: list[RelatedItem] = Field(default_factory=list[RelatedItem])
    """Complemente su compra."""
    source: Literal["page", "api"] = "page"


class ListingItem(BaseModel):
    name: str
    path: str
    price: int | None = None
    """None when the card shows "Confirmar precio en tienda"."""
    regular_price: int | None = None


class FacetState(BaseModel):
    """One facet group of the listing: the options checked, and those offered."""

    facet: str
    on: list[str] = Field(default_factory=list[str])
    options: list[str] = Field(default_factory=list[str])


class ListingShown(BaseModel):
    """A category, search or brand listing is in front, after a load, a filter,
    a sort or a page turn."""

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
    """The Total the cart shows."""


QuoteStep = Literal["form", "done", "other"]


class QuoteState(BaseModel):
    """The Formulario de cotización. Javier may fill everything on it except
    the RUT, and never presses Crear cotización; ``done`` is the
    confirmation page after the visitor did."""

    step: QuoteStep = "other"
    filled: list[str] = Field(default_factory=list[str])
    missing: list[str] = Field(default_factory=list[str])
    items: int | None = None
    total: int | None = None


type AgroplanetEvent = (
    PageChanged
    | TabsChanged
    | LanguageRequested
    | PricesRead
    | ProductsFound
    | StockRead
    | FitRead
    | StoreShown
    | StageResult
    | StageHello
    | StageProgress
    | StageEvent
)

AGROPLANET_EVENTS = AppEvents[AgroplanetEvent](
    PageChanged,
    TabsChanged,
    LanguageRequested,
    PricesRead,
    ProductsFound,
    StockRead,
    FitRead,
    StoreShown,
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
        sku=_text(value.get("sku")),
        name=str(value.get("name") or ""),
        brand=_text(value.get("brand")),
        maker_code=_text(value.get("maker_code")),
        price=_num(value.get("price")),
        regular_price=_num(value.get("regular_price")),
        discount=_num(value.get("discount")),
        offer_price=_num(value.get("offer_price")),
        price_hidden=value.get("price_hidden") is True,
        stock=_text(value.get("stock")),
        stock_level=_num(value.get("stock_level")),
        description=_text(value.get("description")),
        label=_text(value.get("label")),
        category=_text(value.get("category")),
        specs={
            str(r.get("label", "")): str(r.get("value", ""))
            for r in _rows(value.get("specs"))
            if r.get("label")
        },
        equivalents={
            str(r.get("label", "")): str(r.get("value", ""))
            for r in _rows(value.get("equivalents"))
            if r.get("label")
        },
        docs=[d for d in _strings(value.get("docs")) if d],
        related=[
            RelatedItem(
                name=str(r.get("name", "")),
                path=str(r.get("path") or ""),
                price=_num(r.get("price")),
            )
            for r in _rows(value.get("related"))
            if r.get("name")
        ],
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


def quote_view(value: Mapping[str, Any]) -> QuoteState:
    """The ``quote`` slice, as the brain's rules read it."""
    step = value.get("step")
    return QuoteState(
        step=step if step in ("form", "done", "other") else "other",
        filled=_strings(value.get("filled")),
        missing=_strings(value.get("missing")),
        items=_num(value.get("items")),
        total=_num(value.get("total")),
    )
