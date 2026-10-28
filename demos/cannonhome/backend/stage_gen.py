# Generated from cannonhome/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
#   voqalize stage gen cannonhome/scene.json --py cannonhome/backend/stage_gen.py --ts cannonhome/extension/src/scene.gen.ts
"""The moves of cannonhome, from its Stage Spec."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from voqalize.sdk.stage import Move, MoveClass, MoveSet

#: The spec's hash: a page reading another spec reports a different one.
SPEC_SHA256 = "997a4a5ac83c4619c97d573bb3104050e1a1b112e5c298850f27b29edb99defe"


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


class FilterArgs(BaseModel):
    """The arguments of ``listing.filter``."""

    facet: str
    value: str | None = None
    path: str | None = None


class SortArgs(BaseModel):
    """The arguments of ``listing.sort``."""

    order: str
    path: str | None = None


class SearchProductsArgs(BaseModel):
    """The arguments of ``search_products``."""

    query: str
    open_index: int | None = None
    """0-based: 0 is the first suggested product."""


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


class ShowCartArgs(BaseModel):
    """The arguments of ``show_cart``."""

    open: bool = True


class AddToCartArgs(BaseModel):
    """The arguments of ``add_to_cart``."""

    path: str
    qty: int = 1


class UpdateCartItemArgs(BaseModel):
    """The arguments of ``update_cart_item``."""

    path: str
    qty: int


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

FILTER = Move(
    id="listing.filter",
    verb="filter",
    cls=MoveClass.REVERSIBLE,
    args=(
        "facet",
        "value",
        "path",
    ),
    say="{filter: Tamaño | King}",
)
"""Apply one filter of the listing in front with its quick-filter pill."""

SORT = Move(
    id="listing.sort",
    verb="sort",
    cls=MoveClass.REVERSIBLE,
    args=(
        "order",
        "path",
    ),
    say="{sort: price_asc}",
)
"""Sort the listing in front."""

SEARCH_PRODUCTS = Move(
    id="search_products",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "query",
        "open_index",
    ),
)
"""Type ``query`` into the store's search box (``input.amsearch-input``) at a
human pace and let its suggestions open; report ``search_suggest``. With
``open_index``, open that product: the page then reports ``product_shown``.
"""

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
``listing_shown``.
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
through its photos for ``fotos``. Reports ``product_shown``.
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

SHOW_CART = Move(
    id="show_cart",
    verb=None,
    cls=MoveClass.LOOK,
    args=("open",),
)
"""Open the cart drawer (``open``), or close it. Never the checkout."""

ADD_TO_CART = Move(
    id="add_to_cart",
    verb=None,
    cls=MoveClass.CONFIRMED,
    args=(
        "path",
        "qty",
    ),
)
"""On the product page at ``path`` (opened first if it is not in front), set
the quantity to ``qty`` and press Agregar; wait for the cart drawer. Reports
``cart_state``. Never the checkout.
"""

UPDATE_CART_ITEM = Move(
    id="update_cart_item",
    verb=None,
    cls=MoveClass.CONFIRMED,
    args=(
        "path",
        "qty",
    ),
)
"""Set the cart line of the product at ``path`` to ``qty``, or take it out
with 0: in the cart drawer with its own minus and plus, or its bin and
"Aceptar"; on the cart page (/checkout/cart) with the request those send,
then the reload the page's own controls make, the move checked on the page
it loads. Reports ``cart_state``. Never the checkout.
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
``checkout_state``. Nothing past the form.
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
them. Never presses anything after the fields. Reports ``checkout_state``.
"""

MOVES = MoveSet(
    (
        OPEN,
        SHOW,
        FAQ,
        FILTER,
        SORT,
        SEARCH_PRODUCTS,
        FILTER_LISTING,
        OPEN_PRODUCT,
        PRODUCT_TAB,
        CHECK_PRICES,
        SHOW_CART,
        ADD_TO_CART,
        UPDATE_CART_ITEM,
        START_CHECKOUT,
        FILL_CHECKOUT,
    )
)

#: The line each cue is taught with, in the spec's order.
PROMPT_LINES: tuple[str, ...] = (
    "{page: /path}",
    "{show: Heading}",
    "{faq: Question}",
    "{filter: Tamaño | King}",
    "{sort: price_asc}",
)
