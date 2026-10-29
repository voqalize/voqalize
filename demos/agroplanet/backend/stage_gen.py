# Generated from agroplanet/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
#   voqalize stage gen agroplanet/scene.json --py agroplanet/backend/stage_gen.py --ts agroplanet/extension/src/scene.gen.ts
"""The moves of agroplanet, from its Stage Spec."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from voqalize.sdk.stage import Move, MoveClass, MoveSet, StageSpec, load_spec

#: The spec itself, carried here so the brain never reads the JSON at run
#: time (and a deploy that ships this file ships the spec with it).
SPEC: StageSpec = load_spec(
    '{"events":[{"doc":"A product page came up, read from the page.","id":"product.shown","note":"{by} opened the product {name}","op":"set","slice":"product"},{"doc":"The store\'s live read of the product in front: its price and stock now.","id":"product.checked","op":"set","slice":"product"},{"doc":"The quote form on load and after a change; the brain writes its own line.","id":"quote.changed","op":"set","slice":"quote"},{"id":"listing.shown","note":"{by} opened the listing {title}: {count} products","op":"set","slice":"listing"},{"id":"listing.filtered","note":"{by} changed the listing\'s filters: {count} products","op":"set","slice":"listing"},{"id":"listing.sorted","note":"{by} sorted the listing","op":"set","slice":"listing"},{"id":"cart.changed","note":"{by} changed the cart: {count} items","op":"set","slice":"cart"}],"id":"agroplanet","kits":[{"id":"commerce","major":1,"moves":["commerce.filter","commerce.sort","commerce.search","commerce.cart_add","commerce.cart_update","commerce.cart_show"]}],"languages":["es","en"],"moves":[{"args":[{"doc":"A path on www.agroplanet.cl: /, /nuestras-tiendas, /politica-despacho, /categoria/<slug>/<code>, /marca/<brand>, /producto/<slug>/<sku>.","name":"path"}],"claims":["te llevo a","vamos a","abro la página","taking you to","opening the page"],"class":"navigate","doc":"Open a page of the store, inside the app (no reload).","id":"page.open","objects":["page","página"],"say":"{page: /path} at the start of the sentence that takes them there.","verb":"page"},{"args":[{"doc":"A heading, section or card title exactly as the page writes it.","name":"target"},{"doc":"The page it is on, when it is not the one in front; it is opened first.","name":"path","optional":true}],"class":"look","doc":"Scroll to a heading, section or card on the page in front and ring it.","id":"page.show","say":"{show: Heading} as you start talking about a part of the page.","verb":"show"},{"args":[{"doc":"The panel\'s title as the page writes it.","name":"question"},{"name":"path","optional":true}],"class":"look","doc":"Open one panel of a policy page\'s accordion (Cambios y devoluciones, Despacho, Garantía) and ring its answer.","id":"page.faq","say":"{faq: Question} as you answer from one of the page\'s panels.","verb":"faq"},{"args":[{"doc":"A top category as the menu writes it: Baterías, Rodamientos, Lubricantes Y Fluidos, Repuestos De Tractor…","name":"category"}],"class":"look","doc":"Open Todas las categorías and hover the category, so its flyout of subcategories shows, and ring it. Closes by itself on the next move.","id":"menu.open","say":"{menu: Category} as you walk them through what a top category holds.","verb":"menu"},{"args":[{"enum":["details","specs","photos","price"],"name":"tab"}],"class":"look","doc":"On the product page in front, scroll to Detalle del Producto or Especificaciones, step through the gallery, or ring the price and its buttons.","id":"product.tab","say":"{tab: specs} as you talk about the product\'s specifications; details (Detalle del Producto), photos or price likewise.","verb":"tab"},{"args":[{"doc":"/categoria/<slug>/<code> from the category list, or /busqueda/<words> for a search.","name":"category_path"},{"doc":"Each \\"Facet: Option\\" exactly as the listing writes them (\\"Marca: LUBRITEK\\", \\"Viscosidad: 15W40\\", \\"Precio: $10.000 - $49.999\\"); several options of one facet as separate entries.","name":"filters","optional":true,"type":"array"},{"enum":["price_asc","price_desc","relevance"],"name":"sort","optional":true}],"claims":["filtrando por","filtro por","filtering by"],"class":"reversible","doc":"Go to the listing at category_path (in the app, if it is not the one in front), then tick each filter with the listing\'s own checkbox, one at a time, waiting for the grid; then the sort. Reports listing.shown and listing.filtered.","id":"filter_listing","objects":["filter","filtro","filtros"]},{"args":[{"doc":"/producto/<slug>/<sku>.","name":"path"},{"enum":["details","specs","photos","price"],"name":"tab","optional":true}],"claims":["abro el producto","te muestro el","opening the","let me open"],"class":"navigate","doc":"Open the product at path (in the app), then the section named. Reports product.shown, then product.checked from the store\'s live read.","id":"open_product","objects":["product","producto"]},{"args":[{"doc":"Words to search the catalogue for, in Spanish: \\"batería 12v 100ah\\", \\"cuchilla rotofresa\\".","name":"query","optional":true},{"doc":"A category code from the category list (AG100, 1000902).","name":"category_code","optional":true},{"name":"brand","optional":true},{"enum":["price_asc","price_desc","relevance"],"name":"sort","optional":true}],"class":"look","doc":"Read the store\'s own catalogue search in the visitor\'s browser, without moving the page: up to eight products with their live prices and stock, and how many match. Reports products_found.","id":"find_products"},{"args":[{"doc":"Up to six /producto/<slug>/<sku> paths.","name":"paths","type":"array"}],"class":"look","doc":"Read the live price, discount and stock of these products in the visitor\'s browser. Moves nothing. Reports prices_read.","id":"check_prices"},{"args":[{"doc":"/producto/<slug>/<sku>.","name":"path"},{"doc":"A store\'s name as /nuestras-tiendas writes it, or a city.","name":"store","optional":true}],"class":"look","doc":"Read the product\'s stock online and in the stores that report it, in the visitor\'s browser. Moves nothing. Reports stock_read.","id":"check_stock"},{"args":[{"doc":"A store\'s name or city as /nuestras-tiendas writes it.","name":"name"}],"class":"look","doc":"On /nuestras-tiendas (opened first if needed), find the store\'s card, scroll to it and ring it. Reports store_shown.","id":"stores.show","say":"{store: Name} as you talk about one of the stores.","verb":"store"},{"claims":["te llevo a cotizar","vamos a cotizar","taking you to the quote"],"class":"confirmed","doc":"From the cart (/carro, opened first) press Cotizar and stop on the Formulario de cotización (/cotizacion). Agroplanet sells by quote: there is no online payment. Reports quote.changed.","id":"start_quote","objects":["cotización","quote"]},{"args":[{"doc":"Nombre Completo / Razón Social.","name":"name","optional":true},{"doc":"Teléfono, digits as they said them.","name":"phone","optional":true},{"name":"email","optional":true},{"doc":"A Chilean región as the form lists it (Metropolitana, Maule…).","name":"region","optional":true},{"doc":"A comuna of that región.","name":"commune","optional":true},{"name":"street","optional":true},{"name":"number","optional":true},{"doc":"Dpto / casa / Oficina.","name":"unit","optional":true},{"doc":"Notas sobre tu cotización.","name":"notes","optional":true}],"claims":["lo anoto en el formulario","completo el formulario","filling in the form"],"class":"confirmed","doc":"On the Formulario de cotización (/cotizacion), type each field given, once the visitor said yes. Never the RUT, never Crear cotización: those are the visitor\'s. Reports quote.changed.","id":"fill_quote","objects":["formulario","form"]},{"args":[{"doc":"The filter as the listing names it: Tamaño, Color.","name":"facet"},{"doc":"One option as the listing writes it, or several joined by commas.","name":"value","optional":true},{"doc":"The listing\'s path, when it is not the one in front; it is opened first.","name":"path","optional":true}],"claims":["filtering by","filtro por","filtrando por"],"class":"reversible","doc":"Apply one filter of the listing in front, one option or several of it, with the listing\'s own control.","id":"commerce.filter","objects":["filter","filtro"],"say":"{filter: Facet | Option} as you name a filter of the listing in front, one per sentence; {filter: Facet | Option, Option} for several options of one filter.","verb":"filter"},{"args":[{"enum":["price_asc","price_desc","relevance","newest"],"name":"order"},{"doc":"The listing\'s path, when it is not the one in front; it is opened first.","name":"path","optional":true}],"claims":["sorting by","ordenando por","ordeno por"],"class":"reversible","doc":"Order the listing in front.","id":"commerce.sort","say":"{sort: price_asc} as you say how the listing is ordered: price_asc, price_desc, relevance or newest.","verb":"sort"},{"args":[{"doc":"The words to type, in the store\'s language.","name":"query"},{"doc":"Open the suggestion at this place, 0 for the first.","name":"open_index","optional":true,"type":"integer"}],"claims":["searching for","buscando","busco"],"class":"reversible","doc":"Type into the store\'s own search box at a human pace and let its suggestions open; open one when asked.","id":"commerce.search","objects":["search","busqueda"]},{"args":[{"doc":"The item\'s path; it is opened first when it is not in front.","name":"path"},{"default":1,"name":"qty","type":"integer"}],"claims":["adding * to your cart","agrego * al carro","agregando * al carro"],"class":"confirmed","doc":"Add an item to the cart, once the visitor said yes. Never the checkout.","id":"commerce.cart_add","objects":["cart","carro","carrito"]},{"args":[{"name":"path"},{"doc":"0 takes it out.","name":"qty","type":"integer"}],"claims":["changing * in your cart","cambio * en el carro"],"class":"confirmed","doc":"Set how many of a cart line they have, or take it out, once the visitor said yes. Never the checkout.","id":"commerce.cart_update","objects":["cart","carro","carrito"]},{"args":[{"default":true,"name":"open","type":"boolean"}],"class":"look","doc":"Open the cart\'s drawer or page, or close it.","id":"commerce.cart_show"}],"slices":[{"doc":"the product page in front: its name, price, stock and specifications","fields":[{"name":"path"},{"name":"sku","optional":true},{"name":"name"},{"name":"brand","optional":true},{"doc":"Código Fabricante.","name":"maker_code","optional":true},{"doc":"The price the page shows, CLP.","name":"price","optional":true,"type":"number"},{"doc":"The struck price when there is a discount, CLP.","name":"regular_price","optional":true,"type":"number"},{"doc":"Percent off.","name":"discount","optional":true,"type":"integer"},{"doc":"The page says Confirmar precio en tienda instead of a price.","name":"price_hidden","optional":true,"type":"boolean"},{"doc":"inStock, lowStock or outOfStock.","name":"stock","optional":true},{"name":"stock_level","optional":true,"type":"integer"},{"doc":"Detalle del Producto, trimmed.","name":"description","optional":true},{"doc":"Especificaciones, in order.","fields":[{"name":"label"},{"name":"value"}],"name":"specs","type":"array"},{"doc":"page: read from the page; api: the store\'s live read.","enum":["page","api"],"name":"source"}],"id":"product"},{"doc":"the Formulario de cotización: which fields are filled and which are still missing (names only, never the values)","fields":[{"enum":["form","done","other"],"name":"step"},{"doc":"Field names: name, rut, phone, email, region, commune, street, number, unit, notes.","name":"filled","optional":true,"type":"array"},{"doc":"Required field names still empty.","name":"missing","optional":true,"type":"array"},{"doc":"Products in the Resumen del Pedido.","name":"items","optional":true,"type":"integer"},{"doc":"The Total the summary shows, CLP.","name":"total","optional":true,"type":"number"}],"id":"quote"},{"doc":"the listing in front: its title, how many it shows, the filters on and offered, the order, the first items","fields":[{"name":"path"},{"name":"title"},{"name":"count","optional":true,"type":"integer"},{"fields":[{"name":"facet"},{"name":"on","type":"array"},{"name":"options","type":"array"}],"name":"filters","type":"array"},{"name":"sort","optional":true},{"fields":[{"name":"path"},{"name":"name"},{"name":"price","optional":true,"type":"number"},{"doc":"The price before a discount.","name":"regular_price","optional":true,"type":"number"}],"name":"items","type":"array"}],"id":"listing"},{"doc":"what is in their cart: each line, how many, the subtotal","fields":[{"name":"count","type":"integer"},{"name":"subtotal","optional":true,"type":"number"},{"fields":[{"name":"path"},{"name":"name"},{"name":"qty","type":"integer"},{"name":"price","optional":true,"type":"number"}],"name":"items","type":"array"},{"doc":"What is left to spend for free shipping, when the store says.","name":"free_shipping_left","optional":true,"type":"number"}],"id":"cart"}],"stage":1}'
)
#: The spec's hash: a page reading another spec reports a different one.
SPEC_SHA256 = "d4a68fda7d48d2d1bb148580037b86fbaf051121913fe17c662548db18409a5a"


class PageOpenArgs(BaseModel):
    """The arguments of ``page.open``."""

    path: str
    """A path on www.agroplanet.cl: /, /nuestras-tiendas, /politica-despacho, /categoria/<slug>/<code>, /marca/<brand>, /producto/<slug>/<sku>."""


class PageShowArgs(BaseModel):
    """The arguments of ``page.show``."""

    target: str
    """A heading, section or card title exactly as the page writes it."""
    path: str | None = None
    """The page it is on, when it is not the one in front; it is opened first."""


class FaqArgs(BaseModel):
    """The arguments of ``page.faq``."""

    question: str
    """The panel's title as the page writes it."""
    path: str | None = None


class MenuOpenArgs(BaseModel):
    """The arguments of ``menu.open``."""

    category: str
    """A top category as the menu writes it: Baterías, Rodamientos, Lubricantes Y Fluidos, Repuestos De Tractor…"""


class TabArgs(BaseModel):
    """The arguments of ``product.tab``."""

    tab: Literal["details", "specs", "photos", "price"]


class FilterListingArgs(BaseModel):
    """The arguments of ``filter_listing``."""

    category_path: str
    """/categoria/<slug>/<code> from the category list, or /busqueda/<words> for a search."""
    filters: list[str] | None = None
    """Each "Facet: Option" exactly as the listing writes them ("Marca: LUBRITEK", "Viscosidad: 15W40", "Precio: $10.000 - $49.999"); several options of one facet as separate entries."""
    sort: Literal["price_asc", "price_desc", "relevance"] | None = None


class OpenProductArgs(BaseModel):
    """The arguments of ``open_product``."""

    path: str
    """/producto/<slug>/<sku>."""
    tab: Literal["details", "specs", "photos", "price"] | None = None


class FindProductsArgs(BaseModel):
    """The arguments of ``find_products``."""

    query: str | None = None
    """Words to search the catalogue for, in Spanish: "batería 12v 100ah", "cuchilla rotofresa"."""
    category_code: str | None = None
    """A category code from the category list (AG100, 1000902)."""
    brand: str | None = None
    sort: Literal["price_asc", "price_desc", "relevance"] | None = None


class CheckPricesArgs(BaseModel):
    """The arguments of ``check_prices``."""

    paths: list[str]
    """Up to six /producto/<slug>/<sku> paths."""


class CheckStockArgs(BaseModel):
    """The arguments of ``check_stock``."""

    path: str
    """/producto/<slug>/<sku>."""
    store: str | None = None
    """A store's name as /nuestras-tiendas writes it, or a city."""


class StoresShowArgs(BaseModel):
    """The arguments of ``stores.show``."""

    name: str
    """A store's name or city as /nuestras-tiendas writes it."""


class StartQuoteArgs(BaseModel):
    """``start_quote`` takes none."""


class FillQuoteArgs(BaseModel):
    """The arguments of ``fill_quote``."""

    name: str | None = None
    """Nombre Completo / Razón Social."""
    phone: str | None = None
    """Teléfono, digits as they said them."""
    email: str | None = None
    region: str | None = None
    """A Chilean región as the form lists it (Metropolitana, Maule…)."""
    commune: str | None = None
    """A comuna of that región."""
    street: str | None = None
    number: str | None = None
    unit: str | None = None
    """Dpto / casa / Oficina."""
    notes: str | None = None
    """Notas sobre tu cotización."""


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


PAGE_OPEN = Move(
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
"""Open a page of the store, inside the app (no reload)."""

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
    say="{faq: Question} as you answer from one of the page's panels.",
)
"""Open one panel of a policy page's accordion (Cambios y devoluciones, Despacho, Garantía) and ring its answer."""

MENU_OPEN = Move(
    id="menu.open",
    verb="menu",
    cls=MoveClass.LOOK,
    args=("category",),
    say="{menu: Category} as you walk them through what a top category holds.",
)
"""Open Todas las categorías and hover the category, so its flyout of subcategories shows, and ring it. Closes by itself on the next move."""

TAB = Move(
    id="product.tab",
    verb="tab",
    cls=MoveClass.LOOK,
    args=("tab",),
    say="{tab: specs} as you talk about the product's specifications; details (Detalle del Producto), photos or price likewise.",
)
"""On the product page in front, scroll to Detalle del Producto or Especificaciones, step through the gallery, or ring the price and its buttons."""

FILTER_LISTING = Move(
    id="filter_listing",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "category_path",
        "filters",
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
"""Go to the listing at category_path (in the app, if it is not the one in front), then tick each filter with the listing's own checkbox, one at a time, waiting for the grid; then the sort. Reports listing.shown and listing.filtered."""

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
"""Open the product at path (in the app), then the section named. Reports product.shown, then product.checked from the store's live read."""

FIND_PRODUCTS = Move(
    id="find_products",
    verb=None,
    cls=MoveClass.LOOK,
    args=(
        "query",
        "category_code",
        "brand",
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
"""Read the live price, discount and stock of these products in the visitor's browser. Moves nothing. Reports prices_read."""

CHECK_STOCK = Move(
    id="check_stock",
    verb=None,
    cls=MoveClass.LOOK,
    args=(
        "path",
        "store",
    ),
)
"""Read the product's stock online and in the stores that report it, in the visitor's browser. Moves nothing. Reports stock_read."""

STORES_SHOW = Move(
    id="stores.show",
    verb="store",
    cls=MoveClass.LOOK,
    args=("name",),
    say="{store: Name} as you talk about one of the stores.",
)
"""On /nuestras-tiendas (opened first if needed), find the store's card, scroll to it and ring it. Reports store_shown."""

START_QUOTE = Move(
    id="start_quote",
    verb=None,
    cls=MoveClass.CONFIRMED,
    claims=(
        "te llevo a cotizar",
        "vamos a cotizar",
        "taking you to the quote",
    ),
    objects=(
        "cotización",
        "quote",
    ),
)
"""From the cart (/carro, opened first) press Cotizar and stop on the Formulario de cotización (/cotizacion). Agroplanet sells by quote: there is no online payment. Reports quote.changed."""

FILL_QUOTE = Move(
    id="fill_quote",
    verb=None,
    cls=MoveClass.CONFIRMED,
    args=(
        "name",
        "phone",
        "email",
        "region",
        "commune",
        "street",
        "number",
        "unit",
        "notes",
    ),
    claims=(
        "lo anoto en el formulario",
        "completo el formulario",
        "filling in the form",
    ),
    objects=(
        "formulario",
        "form",
    ),
)
"""On the Formulario de cotización (/cotizacion), type each field given, once the visitor said yes. Never the RUT, never Crear cotización: those are the visitor's. Reports quote.changed."""

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
        PAGE_OPEN,
        PAGE_SHOW,
        FAQ,
        MENU_OPEN,
        TAB,
        FILTER_LISTING,
        OPEN_PRODUCT,
        FIND_PRODUCTS,
        CHECK_PRICES,
        CHECK_STOCK,
        STORES_SHOW,
        START_QUOTE,
        FILL_QUOTE,
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
    "{faq: Question} as you answer from one of the page's panels.",
    "{menu: Category} as you walk them through what a top category holds.",
    "{tab: specs} as you talk about the product's specifications; details (Detalle del Producto), photos or price likewise.",
    "{store: Name} as you talk about one of the stores.",
    "{filter: Facet | Option} as you name a filter of the listing in front, one per sentence; {filter: Facet | Option, Option} for several options of one filter.",
    "{sort: price_asc} as you say how the listing is ordered: price_asc, price_desc, relevance or newest.",
)

#: The slices of the page's state a read may name.
SliceId = Literal["product", "quote", "listing", "cart"]


class ReadRequest(BaseModel):
    """What the read tool takes: the slice to read, from the brain's mirror."""

    slice: SliceId = Field(
        description="Which part of their screen to read. product: the product page in front: its name, price, stock and specifications; quote: the Formulario de cotización: which fields are filled and which are still missing (names only, never the values); listing: the listing in front: its title, how many it shows, the filters on and offered, the order, the first items; cart: what is in their cart: each line, how many, the subtotal."
    )
