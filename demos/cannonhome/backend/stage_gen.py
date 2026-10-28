# Generated from cannonhome/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
#   voqalize stage gen cannonhome/scene.json --py cannonhome/backend/stage_gen.py --ts cannonhome/extension/src/scene.gen.ts
"""The moves of cannonhome, from its Stage Spec."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from voqalize.sdk.stage import Move, MoveClass, MoveSet, StageSpec, load_spec

#: The spec itself, carried here so the brain never reads the JSON at run
#: time (and a deploy that ships this file ships the spec with it).
SPEC: StageSpec = load_spec(
    '{"events":[{"doc":"A product page came up, read from the page.","id":"product.shown","note":"{by} opened the product {name}","op":"set","slice":"product"},{"doc":"The store\'s live read of the product in front: its price and stock now.","id":"product.checked","op":"set","slice":"product"},{"id":"search.suggested","note":"The search box shows suggestions for “{query}”","op":"set","slice":"search"},{"doc":"The delivery form on load and after each change; the brain writes its own line.","id":"checkout.changed","op":"set","slice":"checkout"},{"id":"listing.shown","note":"{by} opened the listing {title}: {count} products","op":"set","slice":"listing"},{"id":"listing.filtered","note":"{by} changed the listing\'s filters: {count} products","op":"set","slice":"listing"},{"id":"listing.sorted","note":"{by} sorted the listing","op":"set","slice":"listing"},{"id":"cart.changed","note":"{by} changed the cart: {count} items","op":"set","slice":"cart"}],"id":"cannonhome","kits":[{"id":"commerce","major":1,"moves":["commerce.filter","commerce.sort","commerce.search","commerce.cart_add","commerce.cart_update","commerce.cart_show"]}],"languages":["es","en"],"moves":[{"args":[{"name":"path"}],"class":"navigate","doc":"Open a page of the store, by its path.","id":"page.open","say":"{page: /path}","verb":"page"},{"args":[{"name":"target"},{"name":"path","optional":true}],"class":"look","doc":"Scroll to a heading on the page in front and ring it.","id":"page.show","say":"{show: Heading}","verb":"show"},{"args":[{"name":"question"},{"name":"path","optional":true}],"class":"look","doc":"Open a question\'s answer and ring it.","id":"page.faq","say":"{faq: Question}","verb":"faq"},{"args":[{"name":"category_path"},{"name":"size","optional":true,"type":"array"},{"name":"color","optional":true,"type":"array"},{"name":"threads","optional":true,"type":"array"},{"name":"material","optional":true,"type":"array"},{"enum":["price_asc","price_desc","relevance","newest"],"name":"sort","optional":true}],"class":"reversible","doc":"Go to the listing at ``category_path`` (a full load, if it is not the one in\\nfront), then apply each filter given with its quick-filter pill — the option\\nlabels exactly as the listing writes them (\\"2 Plazas\\", \\"Blanco\\", \\"300\\",\\n\\"100% Algodón\\") — one at a time, waiting for the grid; then the sort. Each\\nfilter takes one option or several (``[\\"Beige\\", \\"Blanco\\"]``: the listing shows\\neither), all active together, one address for them all. Reports\\nthe listing (``listing.shown``, ``listing.filtered``).","id":"filter_listing"},{"args":[{"doc":"``/x.html``.","name":"path"},{"enum":["descripcion","especificaciones","calificaciones","fotos"],"name":"tab","optional":true}],"class":"navigate","doc":"Open the product at ``path`` (a full load), then the tab named, or step\\nthrough its photos for ``fotos``. Reports ``product.shown``.","id":"open_product"},{"args":[{"enum":["descripcion","especificaciones","calificaciones","fotos"],"name":"tab"}],"class":"look","doc":"On the product page in front, open that tab, or step through its photos\\nfor ``fotos``.","id":"product_tab"},{"args":[{"name":"paths","type":"array"}],"class":"look","doc":"Read the live price and stock of these products (at most six), with one\\nsame-origin POST to the store\'s GraphQL. Moves nothing. Reports\\n``prices_read``.","id":"check_prices"},{"class":"confirmed","doc":"Take the visitor to the guest checkout\'s delivery form: on the bag\\n(/checkout/cart/, loaded first if it is not in front) press \\"Terminar\\npedido\\", then, in the window it opens, \\"Comprar como invitado\\" — never its\\nlogin, Google or \\"Crear Cuenta\\" — and wait for the form (/checkout). Reports\\n``checkout.changed``. Nothing past the form.","id":"start_checkout"},{"args":[{"name":"email","optional":true},{"name":"first_name","optional":true},{"name":"last_name","optional":true},{"doc":"Nine digits as said: a mobile starting with 9, or a Santiago landline\\nstarting with 2. The form\'s +56 9 / +56 2 prefix is chosen from the first\\ndigit and the other eight are typed.","name":"phone","optional":true},{"doc":"The site\'s name for the región: \\"Metropolitana\\", \\"Valparaíso\\".","name":"region","optional":true},{"name":"comuna","optional":true},{"name":"street","optional":true},{"name":"number","optional":true},{"doc":"Depto/Casa.","name":"apartment","optional":true}],"class":"confirmed","doc":"Fill the checkout\'s delivery form with what the visitor said (the guest\\ncheckout is opened first, as ``start_checkout``, if it is not in front).\\nOnly the fields given, each set as a finished edit: región and comuna picked\\nfrom the site\'s own lists (the comuna\'s list loads after the región). There\\nis no RUT, password or payment field here, and the page refuses every one of\\nthem. Never presses anything after the fields. Reports ``checkout.changed``.","id":"fill_checkout"},{"args":[{"doc":"The filter as the listing names it: Tamaño, Color.","name":"facet"},{"doc":"One option as the listing writes it, or several joined by commas.","name":"value","optional":true},{"doc":"The listing\'s path, when it is not the one in front; it is opened first.","name":"path","optional":true}],"claims":["filtering by","filtro por","filtrando por"],"class":"reversible","doc":"Apply one filter of the listing in front, one option or several of it, with the listing\'s own control.","id":"commerce.filter","objects":["filter","filtro"],"say":"{filter: Facet | Option} as you name a filter of the listing in front, one per sentence; {filter: Facet | Option, Option} for several options of one filter.","verb":"filter"},{"args":[{"enum":["price_asc","price_desc","relevance","newest"],"name":"order"},{"doc":"The listing\'s path, when it is not the one in front; it is opened first.","name":"path","optional":true}],"claims":["sorting by","ordenando por","ordeno por"],"class":"reversible","doc":"Order the listing in front.","id":"commerce.sort","say":"{sort: price_asc} as you say how the listing is ordered: price_asc, price_desc, relevance or newest.","verb":"sort"},{"args":[{"doc":"The words to type, in the store\'s language.","name":"query"},{"doc":"Open the suggestion at this place, 0 for the first.","name":"open_index","optional":true,"type":"integer"}],"claims":["searching for","buscando","busco"],"class":"reversible","doc":"Type into the store\'s own search box at a human pace and let its suggestions open; open one when asked.","id":"commerce.search","objects":["search","busqueda"]},{"args":[{"doc":"The item\'s path; it is opened first when it is not in front.","name":"path"},{"default":1,"name":"qty","type":"integer"}],"claims":["adding * to your cart","agrego * al carro","agregando * al carro"],"class":"confirmed","doc":"Add an item to the cart, once the visitor said yes. Never the checkout.","id":"commerce.cart_add","objects":["cart","carro","carrito"]},{"args":[{"name":"path"},{"doc":"0 takes it out.","name":"qty","type":"integer"}],"claims":["changing * in your cart","cambio * en el carro"],"class":"confirmed","doc":"Set how many of a cart line they have, or take it out, once the visitor said yes. Never the checkout.","id":"commerce.cart_update","objects":["cart","carro","carrito"]},{"args":[{"default":true,"name":"open","type":"boolean"}],"class":"look","doc":"Open the cart\'s drawer or page, or close it.","id":"commerce.cart_show"}],"slices":[{"doc":"the product page in front: its name, price, stock, specifications and rating","fields":[{"name":"path"},{"name":"sku","optional":true},{"name":"name"},{"name":"price","optional":true,"type":"number"},{"name":"regular_price","optional":true,"type":"number"},{"name":"in_stock","optional":true,"type":"boolean"},{"name":"qty","optional":true,"type":"integer"},{"doc":"The Especificaciones tab, in order.","fields":[{"name":"label"},{"name":"value"}],"name":"specs","type":"array"},{"name":"rating","optional":true,"type":"number"},{"name":"reviews","optional":true,"type":"integer"},{"doc":"page: read from the HTML, which may be hours old; graphql: the store\'s live read.","enum":["page","graphql"],"name":"source"}],"id":"product"},{"doc":"what the store\'s search box suggests for what was typed in it","fields":[{"name":"query"},{"fields":[{"name":"name"},{"name":"path"},{"name":"price","optional":true,"type":"number"}],"name":"items","type":"array"},{"name":"categories","type":"array"}],"id":"search"},{"doc":"the checkout\'s delivery form: which fields hold something, never what","fields":[{"name":"filled","type":"array"},{"name":"missing","type":"array"},{"fields":[{"name":"field"},{"name":"message"}],"name":"invalid","type":"array"},{"name":"region","optional":true},{"name":"comuna","optional":true},{"name":"email_has_account","optional":true,"type":"boolean"},{"name":"delivery_options","type":"array"},{"name":"delivery","optional":true},{"name":"payment_open","optional":true,"type":"boolean"}],"id":"checkout"},{"doc":"the listing in front: its title, how many it shows, the filters on and offered, the order, the first items","fields":[{"name":"path"},{"name":"title"},{"name":"count","optional":true,"type":"integer"},{"fields":[{"name":"facet"},{"name":"on","type":"array"},{"name":"options","type":"array"}],"name":"filters","type":"array"},{"name":"sort","optional":true},{"fields":[{"name":"path"},{"name":"name"},{"name":"price","optional":true,"type":"number"},{"doc":"The price before a discount.","name":"regular_price","optional":true,"type":"number"}],"name":"items","type":"array"}],"id":"listing"},{"doc":"what is in their cart: each line, how many, the subtotal","fields":[{"name":"count","type":"integer"},{"name":"subtotal","optional":true,"type":"number"},{"fields":[{"name":"path"},{"name":"name"},{"name":"qty","type":"integer"},{"name":"price","optional":true,"type":"number"}],"name":"items","type":"array"},{"doc":"What is left to spend for free shipping, when the store says.","name":"free_shipping_left","optional":true,"type":"number"}],"id":"cart"}],"stage":1}'
)
#: The spec's hash: a page reading another spec reports a different one.
SPEC_SHA256 = "6b46f675bf33dd95874ea7565fdc89837ac9e47784f727245b2f9dd6d2fed4fd"


class OpenArgs(BaseModel):
    """The arguments of ``page.open``."""

    path: str


class ShowArgs(BaseModel):
    """The arguments of ``page.show``."""

    target: str
    path: str | None = None


class FaqArgs(BaseModel):
    """The arguments of ``page.faq``."""

    question: str
    path: str | None = None


class FilterListingArgs(BaseModel):
    """The arguments of ``filter_listing``."""

    category_path: str
    size: list[str] | None = None
    color: list[str] | None = None
    threads: list[str] | None = None
    material: list[str] | None = None
    sort: Literal["price_asc", "price_desc", "relevance", "newest"] | None = None


class OpenProductArgs(BaseModel):
    """The arguments of ``open_product``."""

    path: str
    """``/x.html``."""
    tab: Literal["descripcion", "especificaciones", "calificaciones", "fotos"] | None = None


class ProductTabArgs(BaseModel):
    """The arguments of ``product_tab``."""

    tab: Literal["descripcion", "especificaciones", "calificaciones", "fotos"]


class CheckPricesArgs(BaseModel):
    """The arguments of ``check_prices``."""

    paths: list[str]


class StartCheckoutArgs(BaseModel):
    """``start_checkout`` takes none."""


class FillCheckoutArgs(BaseModel):
    """The arguments of ``fill_checkout``."""

    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    """Nine digits as said: a mobile starting with 9, or a Santiago landline
    starting with 2. The form's +56 9 / +56 2 prefix is chosen from the first
    digit and the other eight are typed.
    """
    region: str | None = None
    """The site's name for the región: "Metropolitana", "Valparaíso"."""
    comuna: str | None = None
    street: str | None = None
    number: str | None = None
    apartment: str | None = None
    """Depto/Casa."""


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
    say="{page: /path}",
)
"""Open a page of the store, by its path."""

SHOW = Move(
    id="page.show",
    verb="show",
    cls=MoveClass.LOOK,
    args=(
        "target",
        "path",
    ),
    say="{show: Heading}",
)
"""Scroll to a heading on the page in front and ring it."""

FAQ = Move(
    id="page.faq",
    verb="faq",
    cls=MoveClass.LOOK,
    args=(
        "question",
        "path",
    ),
    say="{faq: Question}",
)
"""Open a question's answer and ring it."""

FILTER_LISTING = Move(
    id="filter_listing",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "category_path",
        "size",
        "color",
        "threads",
        "material",
        "sort",
    ),
)
"""Go to the listing at ``category_path`` (a full load, if it is not the one in
front), then apply each filter given with its quick-filter pill — the option
labels exactly as the listing writes them ("2 Plazas", "Blanco", "300",
"100% Algodón") — one at a time, waiting for the grid; then the sort. Each
filter takes one option or several (``["Beige", "Blanco"]``: the listing shows
either), all active together, one address for them all. Reports
the listing (``listing.shown``, ``listing.filtered``).
"""

OPEN_PRODUCT = Move(
    id="open_product",
    verb=None,
    cls=MoveClass.NAVIGATE,
    args=(
        "path",
        "tab",
    ),
)
"""Open the product at ``path`` (a full load), then the tab named, or step
through its photos for ``fotos``. Reports ``product.shown``.
"""

PRODUCT_TAB = Move(
    id="product_tab",
    verb=None,
    cls=MoveClass.LOOK,
    args=("tab",),
)
"""On the product page in front, open that tab, or step through its photos
for ``fotos``.
"""

CHECK_PRICES = Move(
    id="check_prices",
    verb=None,
    cls=MoveClass.LOOK,
    args=("paths",),
)
"""Read the live price and stock of these products (at most six), with one
same-origin POST to the store's GraphQL. Moves nothing. Reports
``prices_read``.
"""

START_CHECKOUT = Move(
    id="start_checkout",
    verb=None,
    cls=MoveClass.CONFIRMED,
)
"""Take the visitor to the guest checkout's delivery form: on the bag
(/checkout/cart/, loaded first if it is not in front) press "Terminar
pedido", then, in the window it opens, "Comprar como invitado" — never its
login, Google or "Crear Cuenta" — and wait for the form (/checkout). Reports
``checkout.changed``. Nothing past the form.
"""

FILL_CHECKOUT = Move(
    id="fill_checkout",
    verb=None,
    cls=MoveClass.CONFIRMED,
    args=(
        "email",
        "first_name",
        "last_name",
        "phone",
        "region",
        "comuna",
        "street",
        "number",
        "apartment",
    ),
)
"""Fill the checkout's delivery form with what the visitor said (the guest
checkout is opened first, as ``start_checkout``, if it is not in front).
Only the fields given, each set as a finished edit: región and comuna picked
from the site's own lists (the comuna's list loads after the región). There
is no RUT, password or payment field here, and the page refuses every one of
them. Never presses anything after the fields. Reports ``checkout.changed``.
"""

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
        SHOW,
        FAQ,
        FILTER_LISTING,
        OPEN_PRODUCT,
        PRODUCT_TAB,
        CHECK_PRICES,
        START_CHECKOUT,
        FILL_CHECKOUT,
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
    "{page: /path}",
    "{show: Heading}",
    "{faq: Question}",
    "{filter: Facet | Option} as you name a filter of the listing in front, one per sentence; {filter: Facet | Option, Option} for several options of one filter.",
    "{sort: price_asc} as you say how the listing is ordered: price_asc, price_desc, relevance or newest.",
)

#: The slices of the page's state a read may name.
SliceId = Literal["product", "search", "checkout", "listing", "cart"]


class ReadRequest(BaseModel):
    """What the read tool takes: the slice to read, from the brain's mirror."""

    slice: SliceId = Field(
        description="Which part of their screen to read. product: the product page in front: its name, price, stock, specifications and rating; search: what the store's search box suggests for what was typed in it; checkout: the checkout's delivery form: which fields hold something, never what; listing: the listing in front: its title, how many it shows, the filters on and offered, the order, the first items; cart: what is in their cart: each line, how many, the subtotal."
    )
