# Generated from pcfactory/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
#   voqalize stage gen pcfactory/scene.json --py pcfactory/backend/stage_gen.py --ts pcfactory/extension/src/scene.gen.ts
"""The moves of pcfactory, from its Stage Spec."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from voqalize.sdk.stage import Move, MoveClass, MoveSet, StageSpec, load_spec

#: The spec itself, carried here so the brain never reads the JSON at run
#: time (and a deploy that ships this file ships the spec with it).
SPEC: StageSpec = load_spec(
    '{"events":[{"doc":"A product page came up, read from the page.","id":"product.shown","note":"{by} opened the product {name}","op":"set","slice":"product"},{"doc":"The store\'s live read of the product in front: its prices and stock now.","id":"product.checked","op":"set","slice":"product"},{"doc":"The checkout step on load and after a change; the brain writes its own line.","id":"checkout.changed","op":"set","slice":"checkout"},{"id":"listing.shown","note":"{by} opened the listing {title}: {count} products","op":"set","slice":"listing"},{"id":"listing.filtered","note":"{by} changed the listing\'s filters: {count} products","op":"set","slice":"listing"},{"id":"listing.sorted","note":"{by} sorted the listing","op":"set","slice":"listing"},{"id":"cart.changed","note":"{by} changed the cart: {count} items","op":"set","slice":"cart"}],"id":"pcfactory","kits":[{"id":"commerce","major":1,"moves":["commerce.filter","commerce.sort","commerce.search","commerce.cart_add","commerce.cart_update","commerce.cart_show"]}],"languages":["es","en"],"moves":[{"args":[{"doc":"A path on www.pcfactory.cl: /, /tiendas, /centro-de-ayuda/..., /categoria/..., /producto/<id>.","name":"path"}],"claims":["te llevo a","vamos a","abro la página","taking you to","opening the page"],"class":"navigate","doc":"Open a page of the store (a full load).","id":"page.open","objects":["page","página"],"say":"{page: /path} at the start of the sentence that takes them there.","verb":"page"},{"args":[{"doc":"A heading, section or card title exactly as the page writes it.","name":"target"},{"doc":"The page it is on, when it is not the one in front; it is opened first.","name":"path","optional":true}],"class":"look","doc":"Scroll to a heading, section or card on the page in front and ring it.","id":"page.show","say":"{show: Heading} as you start talking about a part of the page.","verb":"show"},{"args":[{"doc":"The question as the page writes it.","name":"question"},{"name":"path","optional":true}],"class":"look","doc":"Open one question of the page\'s FAQ (Centro de ayuda, Cyber, Gamer) and ring its answer.","id":"page.faq","say":"{faq: Question} as you answer one of the page\'s questions.","verb":"faq"},{"args":[{"enum":["about","specs","warranty","stock","photos"],"name":"tab"}],"class":"look","doc":"On the product page in front, open a tab (Sobre este producto, Especificaciones, Garantía), scroll to the stock by store (Disponibilidad), or step through the gallery, and ring it.","id":"product.tab","say":"{tab: specs} as you talk about the product\'s specifications; about, warranty, stock (by store) or photos likewise.","verb":"tab"},{"args":[{"doc":"/categoria/... from the category list, or /busqueda-avanzada?search=... for a search.","name":"category_path"},{"doc":"Each \\"Facet: Option\\" exactly as the listing writes them (\\"Marcas: Lenovo\\", \\"RAM: 16GB\\", \\"Tiendas: Costanera Center\\"); several options of one facet as separate entries.","name":"filters","optional":true,"type":"array"},{"doc":"Pesos, for Rango de precios.","name":"min_price","optional":true,"type":"integer"},{"doc":"Pesos, for Rango de precios.","name":"max_price","optional":true,"type":"integer"},{"enum":["price_asc","price_desc","relevance"],"name":"sort","optional":true}],"claims":["filtrando por","filtro por","filtering by"],"class":"reversible","doc":"Go to the listing at category_path (a full load, if it is not the one in front), then apply each filter with the listing\'s own checkbox, one at a time, waiting for the grid; then the price range and the sort. Reports listing.shown and listing.filtered.","id":"filter_listing","objects":["filter","filtro","filtros"]},{"args":[{"doc":"/producto/<id> or /producto/<id>-<slug>.","name":"path"},{"enum":["about","specs","warranty","stock","photos"],"name":"tab","optional":true}],"claims":["abro el producto","te muestro el","opening the","let me open"],"class":"navigate","doc":"Open the product at path (a full load), then the tab named. Reports product.shown, then product.checked from the store\'s live price and stock.","id":"open_product","objects":["product","producto"]},{"args":[{"doc":"Words to search the catalogue for, in Spanish: \\"notebook gamer rtx 4060\\".","name":"query","optional":true},{"doc":"A category id from the category list.","name":"category_id","optional":true,"type":"integer"},{"name":"brand","optional":true},{"name":"min_price","optional":true,"type":"integer"},{"name":"max_price","optional":true,"type":"integer"},{"enum":["price_asc","price_desc","relevance"],"name":"sort","optional":true}],"class":"look","doc":"Read the store\'s own catalogue search in the visitor\'s browser, without moving the page: up to eight products with their live prices and stock, and how many match. Reports products_found.","id":"find_products"},{"args":[{"doc":"Up to six /producto/<id> paths.","name":"paths","type":"array"}],"class":"look","doc":"Read the live price (transferencia, otros medios, referencia) and the online stock of these products in the visitor\'s browser. Moves nothing. Reports prices_read.","id":"check_prices"},{"args":[{"doc":"/producto/<id>.","name":"path"},{"doc":"A store\'s name as the store list writes it, or a comuna or city.","name":"store","optional":true}],"class":"look","doc":"Read the product\'s stock in every store (and Internet) in the visitor\'s browser; on its page, scroll to Disponibilidad and ring the store asked about. Reports stock_read.","id":"check_stock"},{"args":[{"doc":"A store\'s name as /tiendas writes it.","name":"name"}],"class":"look","doc":"On /tiendas (opened first if needed), find the store, scroll to it, ring it and open its map card (address and hours). Reports store_shown.","id":"stores.show","say":"{store: Name} as you talk about one of the stores.","verb":"store"},{"args":[{"doc":"Two to four /producto/<id> paths shown on the listing in front, or the product in front.","name":"paths","type":"array"}],"claims":["comparo","comparando","comparing"],"class":"reversible","doc":"Tick the store\'s own Comparar box on each product and bring up its comparator. Reports compare_shown.","id":"compare.add","objects":["comparador","comparator","comparison"]},{"args":[{"doc":"The coupon code as the site writes it (LEN50).","name":"code"}],"claims":["aplico el cupón","applying the coupon"],"class":"confirmed","doc":"On the cart (/carro, opened first), type the code into Cupón de descuento and press Aplicar, once the visitor said yes. Reports cart.changed and the store\'s message.","id":"apply_coupon","objects":["cupón","coupon"]},{"claims":["te llevo al checkout","vamos a pagar","taking you to checkout"],"class":"confirmed","doc":"From the cart (/carro, opened first) press Continuar, then Continuar como invitado (never a login or Crear nueva cuenta), and stop on Tipo de entrega, where the visitor chooses store pickup or delivery. Reports checkout.changed. Nothing past that step.","id":"start_checkout","objects":["checkout","pago"]},{"args":[{"doc":"The filter as the listing names it: Tamaño, Color.","name":"facet"},{"doc":"One option as the listing writes it, or several joined by commas.","name":"value","optional":true},{"doc":"The listing\'s path, when it is not the one in front; it is opened first.","name":"path","optional":true}],"claims":["filtering by","filtro por","filtrando por"],"class":"reversible","doc":"Apply one filter of the listing in front, one option or several of it, with the listing\'s own control.","id":"commerce.filter","objects":["filter","filtro"],"say":"{filter: Facet | Option} as you name a filter of the listing in front, one per sentence; {filter: Facet | Option, Option} for several options of one filter.","verb":"filter"},{"args":[{"enum":["price_asc","price_desc","relevance","newest"],"name":"order"},{"doc":"The listing\'s path, when it is not the one in front; it is opened first.","name":"path","optional":true}],"claims":["sorting by","ordenando por","ordeno por"],"class":"reversible","doc":"Order the listing in front.","id":"commerce.sort","say":"{sort: price_asc} as you say how the listing is ordered: price_asc, price_desc, relevance or newest.","verb":"sort"},{"args":[{"doc":"The words to type, in the store\'s language.","name":"query"},{"doc":"Open the suggestion at this place, 0 for the first.","name":"open_index","optional":true,"type":"integer"}],"claims":["searching for","buscando","busco"],"class":"reversible","doc":"Type into the store\'s own search box at a human pace and let its suggestions open; open one when asked.","id":"commerce.search","objects":["search","busqueda"]},{"args":[{"doc":"The item\'s path; it is opened first when it is not in front.","name":"path"},{"default":1,"name":"qty","type":"integer"}],"claims":["adding * to your cart","agrego * al carro","agregando * al carro"],"class":"confirmed","doc":"Add an item to the cart, once the visitor said yes. Never the checkout.","id":"commerce.cart_add","objects":["cart","carro","carrito"]},{"args":[{"name":"path"},{"doc":"0 takes it out.","name":"qty","type":"integer"}],"claims":["changing * in your cart","cambio * en el carro"],"class":"confirmed","doc":"Set how many of a cart line they have, or take it out, once the visitor said yes. Never the checkout.","id":"commerce.cart_update","objects":["cart","carro","carrito"]},{"args":[{"default":true,"name":"open","type":"boolean"}],"class":"look","doc":"Open the cart\'s drawer or page, or close it.","id":"commerce.cart_show"}],"slices":[{"doc":"the product page in front: its name, three prices, stock and specifications","fields":[{"name":"path"},{"name":"id","optional":true,"type":"integer"},{"name":"name"},{"name":"brand","optional":true},{"doc":"Transferencia / Débito, the headline price.","name":"price","optional":true,"type":"number"},{"doc":"Otros medios de pago (credit card).","name":"card_price","optional":true,"type":"number"},{"doc":"The struck reference price the discount is computed against.","name":"regular_price","optional":true,"type":"number"},{"doc":"Units for delivery, as the store writes them (\\"+100\\", \\"2\\").","name":"online_stock","optional":true},{"name":"stores_with_stock","optional":true,"type":"integer"},{"name":"warranty","optional":true},{"name":"promo_until","optional":true},{"doc":"The Especificaciones tab, in order.","fields":[{"name":"label"},{"name":"value"}],"name":"specs","type":"array"},{"doc":"page: read from the HTML; api: the store\'s live read.","enum":["page","api"],"name":"source"}],"id":"product"},{"doc":"where they are in the checkout: the step and the delivery options it offers","fields":[{"enum":["login","delivery","payment","other"],"name":"step"},{"name":"options","optional":true,"type":"array"},{"name":"chosen","optional":true}],"id":"checkout"},{"doc":"the listing in front: its title, how many it shows, the filters on and offered, the order, the first items","fields":[{"name":"path"},{"name":"title"},{"name":"count","optional":true,"type":"integer"},{"fields":[{"name":"facet"},{"name":"on","type":"array"},{"name":"options","type":"array"}],"name":"filters","type":"array"},{"name":"sort","optional":true},{"fields":[{"name":"path"},{"name":"name"},{"name":"price","optional":true,"type":"number"},{"doc":"The price before a discount.","name":"regular_price","optional":true,"type":"number"}],"name":"items","type":"array"}],"id":"listing"},{"doc":"what is in their cart: each line, how many, the subtotal","fields":[{"name":"count","type":"integer"},{"name":"subtotal","optional":true,"type":"number"},{"fields":[{"name":"path"},{"name":"name"},{"name":"qty","type":"integer"},{"name":"price","optional":true,"type":"number"}],"name":"items","type":"array"},{"doc":"What is left to spend for free shipping, when the store says.","name":"free_shipping_left","optional":true,"type":"number"}],"id":"cart"}],"stage":1}'
)
#: The spec's hash: a page reading another spec reports a different one.
SPEC_SHA256 = "093066655cac2c866735a8820205e12fb4822e59ecf761a7e974db6a2bcb975b"


class OpenArgs(BaseModel):
    """The arguments of ``page.open``."""

    path: str
    """A path on www.pcfactory.cl: /, /tiendas, /centro-de-ayuda/..., /categoria/..., /producto/<id>."""


class PageShowArgs(BaseModel):
    """The arguments of ``page.show``."""

    target: str
    """A heading, section or card title exactly as the page writes it."""
    path: str | None = None
    """The page it is on, when it is not the one in front; it is opened first."""


class FaqArgs(BaseModel):
    """The arguments of ``page.faq``."""

    question: str
    """The question as the page writes it."""
    path: str | None = None


class TabArgs(BaseModel):
    """The arguments of ``product.tab``."""

    tab: Literal["about", "specs", "warranty", "stock", "photos"]


class FilterListingArgs(BaseModel):
    """The arguments of ``filter_listing``."""

    category_path: str
    """/categoria/... from the category list, or /busqueda-avanzada?search=... for a search."""
    filters: list[str] | None = None
    """Each "Facet: Option" exactly as the listing writes them ("Marcas: Lenovo", "RAM: 16GB", "Tiendas: Costanera Center"); several options of one facet as separate entries."""
    min_price: int | None = None
    """Pesos, for Rango de precios."""
    max_price: int | None = None
    """Pesos, for Rango de precios."""
    sort: Literal["price_asc", "price_desc", "relevance"] | None = None


class OpenProductArgs(BaseModel):
    """The arguments of ``open_product``."""

    path: str
    """/producto/<id> or /producto/<id>-<slug>."""
    tab: Literal["about", "specs", "warranty", "stock", "photos"] | None = None


class FindProductsArgs(BaseModel):
    """The arguments of ``find_products``."""

    query: str | None = None
    """Words to search the catalogue for, in Spanish: "notebook gamer rtx 4060"."""
    category_id: int | None = None
    """A category id from the category list."""
    brand: str | None = None
    min_price: int | None = None
    max_price: int | None = None
    sort: Literal["price_asc", "price_desc", "relevance"] | None = None


class CheckPricesArgs(BaseModel):
    """The arguments of ``check_prices``."""

    paths: list[str]
    """Up to six /producto/<id> paths."""


class CheckStockArgs(BaseModel):
    """The arguments of ``check_stock``."""

    path: str
    """/producto/<id>."""
    store: str | None = None
    """A store's name as the store list writes it, or a comuna or city."""


class StoresShowArgs(BaseModel):
    """The arguments of ``stores.show``."""

    name: str
    """A store's name as /tiendas writes it."""


class AddArgs(BaseModel):
    """The arguments of ``compare.add``."""

    paths: list[str]
    """Two to four /producto/<id> paths shown on the listing in front, or the product in front."""


class ApplyCouponArgs(BaseModel):
    """The arguments of ``apply_coupon``."""

    code: str
    """The coupon code as the site writes it (LEN50)."""


class StartCheckoutArgs(BaseModel):
    """``start_checkout`` takes none."""


class FilterArgs(BaseModel):
    """The arguments of ``commerce.filter``."""

    facet: str
    """The filter as the listing names it: Tamaño, Color."""
    value: str | None = None
    """One option as the listing writes it, or several joined by commas."""
    path: str | None = None
    """The listing's path, when it is not the one in front; it is opened first."""


class SortArgs(BaseModel):
    """The arguments of ``commerce.sort``."""

    order: Literal["price_asc", "price_desc", "relevance", "newest"]
    path: str | None = None
    """The listing's path, when it is not the one in front; it is opened first."""


class SearchArgs(BaseModel):
    """The arguments of ``commerce.search``."""

    query: str
    """The words to type, in the store's language."""
    open_index: int | None = None
    """Open the suggestion at this place, 0 for the first."""


class CartAddArgs(BaseModel):
    """The arguments of ``commerce.cart_add``."""

    path: str
    """The item's path; it is opened first when it is not in front."""
    qty: int = 1


class CartUpdateArgs(BaseModel):
    """The arguments of ``commerce.cart_update``."""

    path: str
    qty: int
    """0 takes it out."""


class CartShowArgs(BaseModel):
    """The arguments of ``commerce.cart_show``."""

    open: bool = True


OPEN = Move(
    id="page.open",
    verb="page",
    cls=MoveClass.NAVIGATE,
    args=("path",),
    say="{page: /path} at the start of the sentence that takes them there.",
    claims=(
        "te llevo a",
        "vamos a",
        "abro la página",
        "taking you to",
        "opening the page",
    ),
    objects=(
        "page",
        "página",
    ),
)
"""Open a page of the store (a full load)."""

PAGE_SHOW = Move(
    id="page.show",
    verb="show",
    cls=MoveClass.LOOK,
    args=(
        "target",
        "path",
    ),
    say="{show: Heading} as you start talking about a part of the page.",
)
"""Scroll to a heading, section or card on the page in front and ring it."""

FAQ = Move(
    id="page.faq",
    verb="faq",
    cls=MoveClass.LOOK,
    args=(
        "question",
        "path",
    ),
    say="{faq: Question} as you answer one of the page's questions.",
)
"""Open one question of the page's FAQ (Centro de ayuda, Cyber, Gamer) and ring its answer."""

TAB = Move(
    id="product.tab",
    verb="tab",
    cls=MoveClass.LOOK,
    args=("tab",),
    say="{tab: specs} as you talk about the product's specifications; about, warranty, stock (by store) or photos likewise.",
)
"""On the product page in front, open a tab (Sobre este producto, Especificaciones, Garantía), scroll to the stock by store (Disponibilidad), or step through the gallery, and ring it."""

FILTER_LISTING = Move(
    id="filter_listing",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "category_path",
        "filters",
        "min_price",
        "max_price",
        "sort",
    ),
    claims=(
        "filtrando por",
        "filtro por",
        "filtering by",
    ),
    objects=(
        "filter",
        "filtro",
        "filtros",
    ),
)
"""Go to the listing at category_path (a full load, if it is not the one in front), then apply each filter with the listing's own checkbox, one at a time, waiting for the grid; then the price range and the sort. Reports listing.shown and listing.filtered."""

OPEN_PRODUCT = Move(
    id="open_product",
    verb=None,
    cls=MoveClass.NAVIGATE,
    args=(
        "path",
        "tab",
    ),
    claims=(
        "abro el producto",
        "te muestro el",
        "opening the",
        "let me open",
    ),
    objects=(
        "product",
        "producto",
    ),
)
"""Open the product at path (a full load), then the tab named. Reports product.shown, then product.checked from the store's live price and stock."""

FIND_PRODUCTS = Move(
    id="find_products",
    verb=None,
    cls=MoveClass.LOOK,
    args=(
        "query",
        "category_id",
        "brand",
        "min_price",
        "max_price",
        "sort",
    ),
)
"""Read the store's own catalogue search in the visitor's browser, without moving the page: up to eight products with their live prices and stock, and how many match. Reports products_found."""

CHECK_PRICES = Move(
    id="check_prices",
    verb=None,
    cls=MoveClass.LOOK,
    args=("paths",),
)
"""Read the live price (transferencia, otros medios, referencia) and the online stock of these products in the visitor's browser. Moves nothing. Reports prices_read."""

CHECK_STOCK = Move(
    id="check_stock",
    verb=None,
    cls=MoveClass.LOOK,
    args=(
        "path",
        "store",
    ),
)
"""Read the product's stock in every store (and Internet) in the visitor's browser; on its page, scroll to Disponibilidad and ring the store asked about. Reports stock_read."""

STORES_SHOW = Move(
    id="stores.show",
    verb="store",
    cls=MoveClass.LOOK,
    args=("name",),
    say="{store: Name} as you talk about one of the stores.",
)
"""On /tiendas (opened first if needed), find the store, scroll to it, ring it and open its map card (address and hours). Reports store_shown."""

ADD = Move(
    id="compare.add",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=("paths",),
    claims=(
        "comparo",
        "comparando",
        "comparing",
    ),
    objects=(
        "comparador",
        "comparator",
        "comparison",
    ),
)
"""Tick the store's own Comparar box on each product and bring up its comparator. Reports compare_shown."""

APPLY_COUPON = Move(
    id="apply_coupon",
    verb=None,
    cls=MoveClass.CONFIRMED,
    args=("code",),
    claims=(
        "aplico el cupón",
        "applying the coupon",
    ),
    objects=(
        "cupón",
        "coupon",
    ),
)
"""On the cart (/carro, opened first), type the code into Cupón de descuento and press Aplicar, once the visitor said yes. Reports cart.changed and the store's message."""

START_CHECKOUT = Move(
    id="start_checkout",
    verb=None,
    cls=MoveClass.CONFIRMED,
    claims=(
        "te llevo al checkout",
        "vamos a pagar",
        "taking you to checkout",
    ),
    objects=(
        "checkout",
        "pago",
    ),
)
"""From the cart (/carro, opened first) press Continuar, then Continuar como invitado (never a login or Crear nueva cuenta), and stop on Tipo de entrega, where the visitor chooses store pickup or delivery. Reports checkout.changed. Nothing past that step."""

FILTER = Move(
    id="commerce.filter",
    verb="filter",
    cls=MoveClass.REVERSIBLE,
    args=(
        "facet",
        "value",
        "path",
    ),
    say="{filter: Facet | Option} as you name a filter of the listing in front, one per sentence; {filter: Facet | Option, Option} for several options of one filter.",
    claims=(
        "filtering by",
        "filtro por",
        "filtrando por",
    ),
    objects=(
        "filter",
        "filtro",
    ),
)
"""Apply one filter of the listing in front, one option or several of it, with the listing's own control."""

SORT = Move(
    id="commerce.sort",
    verb="sort",
    cls=MoveClass.REVERSIBLE,
    args=(
        "order",
        "path",
    ),
    say="{sort: price_asc} as you say how the listing is ordered: price_asc, price_desc, relevance or newest.",
    claims=(
        "sorting by",
        "ordenando por",
        "ordeno por",
    ),
)
"""Order the listing in front."""

SEARCH = Move(
    id="commerce.search",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "query",
        "open_index",
    ),
    claims=(
        "searching for",
        "buscando",
        "busco",
    ),
    objects=(
        "search",
        "busqueda",
    ),
)
"""Type into the store's own search box at a human pace and let its suggestions open; open one when asked."""

CART_ADD = Move(
    id="commerce.cart_add",
    verb=None,
    cls=MoveClass.CONFIRMED,
    args=(
        "path",
        "qty",
    ),
    claims=(
        "adding * to your cart",
        "agrego * al carro",
        "agregando * al carro",
    ),
    objects=(
        "cart",
        "carro",
        "carrito",
    ),
)
"""Add an item to the cart, once the visitor said yes. Never the checkout."""

CART_UPDATE = Move(
    id="commerce.cart_update",
    verb=None,
    cls=MoveClass.CONFIRMED,
    args=(
        "path",
        "qty",
    ),
    claims=(
        "changing * in your cart",
        "cambio * en el carro",
    ),
    objects=(
        "cart",
        "carro",
        "carrito",
    ),
)
"""Set how many of a cart line they have, or take it out, once the visitor said yes. Never the checkout."""

CART_SHOW = Move(
    id="commerce.cart_show",
    verb=None,
    cls=MoveClass.LOOK,
    args=("open",),
)
"""Open the cart's drawer or page, or close it."""

MOVES = MoveSet(
    (
        OPEN,
        PAGE_SHOW,
        FAQ,
        TAB,
        FILTER_LISTING,
        OPEN_PRODUCT,
        FIND_PRODUCTS,
        CHECK_PRICES,
        CHECK_STOCK,
        STORES_SHOW,
        ADD,
        APPLY_COUPON,
        START_CHECKOUT,
        FILTER,
        SORT,
        SEARCH,
        CART_ADD,
        CART_UPDATE,
        CART_SHOW,
    )
)

#: The line each cue is taught with, in the spec's order.
PROMPT_LINES: tuple[str, ...] = (
    "{page: /path} at the start of the sentence that takes them there.",
    "{show: Heading} as you start talking about a part of the page.",
    "{faq: Question} as you answer one of the page's questions.",
    "{tab: specs} as you talk about the product's specifications; about, warranty, stock (by store) or photos likewise.",
    "{store: Name} as you talk about one of the stores.",
    "{filter: Facet | Option} as you name a filter of the listing in front, one per sentence; {filter: Facet | Option, Option} for several options of one filter.",
    "{sort: price_asc} as you say how the listing is ordered: price_asc, price_desc, relevance or newest.",
)

#: The slices of the page's state a read may name.
SliceId = Literal["product", "checkout", "listing", "cart"]


class ReadRequest(BaseModel):
    """What the read tool takes: the slice to read, from the brain's mirror."""

    slice: SliceId = Field(
        description="Which part of their screen to read. product: the product page in front: its name, three prices, stock and specifications; checkout: where they are in the checkout: the step and the delivery options it offers; listing: the listing in front: its title, how many it shows, the filters on and offered, the order, the first items; cart: what is in their cart: each line, how many, the subtotal."
    )
