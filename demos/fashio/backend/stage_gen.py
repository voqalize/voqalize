# Generated from demos/fashio/frontend/src/stage/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
#   voqalize stage gen demos/fashio/frontend/src/stage/scene.json --py demos/fashio/backend/stage_gen.py --ts demos/fashio/frontend/src/stage/scene.gen.ts
"""The moves of fashio, from its Stage Spec."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from voqalize.sdk.stage import Move, MoveClass, MoveSet, StageSpec, load_spec

#: The spec itself, carried here so the brain never reads the JSON at run
#: time (and a deploy that ships this file ships the spec with it).
SPEC: StageSpec = load_spec(
    '{"events":[{"id":"screen.viewed","note":"{by} opened {path}","op":"set","react":"silent","slice":"screen"},{"id":"shop.changed","note":"{by} changed the search: {summary}; {count} products match","op":"set","slice":"shop"},{"id":"product.size_picked","note":"{by} picked size {size} of product {product_id}","slice":"product"},{"id":"fit.changed","note":"{by} filled Find my size for {product_id}: height {height_cm}, usual size {usual_size}, fit {fit}","slice":"product"},{"id":"bag.changed","note":"{by} changed the bag: {count} items, total {total}","op":"set","slice":"bag"},{"id":"wishlist.changed","note":"{by} changed the wishlist: {count} products","op":"set","slice":"wishlist"},{"id":"checkout.changed","note":"{by} filled the checkout: contact {contact}, address {address}, payment {payment}; the details themselves stay on the page","slice":"checkout"},{"ask":"they placed the order themselves: thank them by first name in one line, say the order number and when it arrives","id":"order.placed","note":"{by} placed order {order_id} for {total} rupees","react":"speak","slice":"checkout"},{"id":"order.selected","note":"{by} opened order {order_id} ({status})","op":"set","slice":"order"},{"ask":"they cancelled the order themselves: confirm it in one line and say how the refund comes back","id":"order.cancelled","note":"{by} cancelled order {order_id}","op":"set","react":"speak","slice":"order"},{"id":"return.changed","note":"{by} changed the return for {order_id}: item {product_id}, reason {reason}, unused {unused}, tags {tags}","slice":"return"},{"ask":"they submitted the return themselves: confirm it in one line with the pickup and refund timing","id":"return.submitted","note":"{by} submitted a return for {order_id}, reference {reference}","react":"speak","slice":"return"},{"id":"gifts.changed","note":"{by} changed the gift brief: {recipient}, {occasion}, budget {budget_max}","op":"set","slice":"gifts"},{"id":"kiosk.changed","note":"{by} changed the kiosk: {summary}; {count} results","slice":"kiosk"}],"id":"fashio","languages":["en","hi"],"moves":[{"args":[{"doc":"A page: /, /shop, /shop/<dept>, /shop/<dept>/<type>, /p/<product id>, /compare?ids=a,b, /wishlist, /bag, /checkout, /orders, /returns, /gifts, /about. Not /kiosk.","name":"path"}],"claims":["opening the","taking you to"],"class":"navigate","doc":"Go to a page of the store, ringing the link, card or icon that leads there first.","id":"site.go","objects":["page","product","bag","wishlist","orders","returns","gifts","पेज"]},{"args":[{"doc":"The department: the gender scope (men and women include unisex; boys and girls are kids; all: every product).","enum":["men","women","kids","boys","girls","ethnic","footwear","accessories","all"],"name":"dept","optional":true},{"doc":"Article type ids from the catalogue (kurtas, heels, watches).","name":"types","optional":true,"type":"array"},{"name":"brands","optional":true,"type":"array"},{"doc":"Catalogue colour names (Navy Blue, Maroon).","name":"colours","optional":true,"type":"array"},{"doc":"Size labels: M, XL, 32, UK 7. A product matches when one of them is in stock.","name":"sizes","optional":true,"type":"array"},{"doc":"Rupees, the selling price.","name":"price_min","optional":true,"type":"integer"},{"doc":"Rupees, the selling price.","name":"price_max","optional":true,"type":"integer"},{"doc":"At least this percent off MRP.","name":"discount_min","optional":true,"type":"integer"},{"doc":"Occasion: Casual, Ethnic, Formal, Sports, Party, Smart Casual, Travel.","name":"usage","optional":true,"type":"array"},{"doc":"Summer, Fall, Winter, Spring.","name":"seasons","optional":true,"type":"array"},{"doc":"Words the product name must contain (silk, floral, chanderi).","name":"query","optional":true},{"enum":["popular","price_asc","price_desc","discount","new"],"name":"sort","optional":true}],"claims":["filtering","narrowing","showing you"],"class":"reversible","doc":"Set the listing\'s whole search (absent fields are cleared). On /shop each filter control that changes is ringed and set in turn, then the grid follows. Navigates to /shop first when elsewhere.","id":"shop.filter","objects":["filters","filter","results","products","kurtas","फ़िल्टर"]},{"args":[{"doc":"A product id on screen, 7421.","name":"product_id"}],"class":"look","doc":"Ring one product\'s card (listing, compare, wishlist, gifts or kiosk results), scrolling it into view. Changes nothing.","id":"shop.show","say":"{show: 7421} at the start of the sentence about one product on screen: its card is ringed.","verb":"show"},{"args":[{"doc":"Two to four product ids.","name":"ids","type":"array"}],"claims":["comparing them","side by side"],"class":"navigate","doc":"Open /compare with these products side by side; the rows are ringed in turn.","id":"compare.show","objects":["comparison","compare","तुलना"]},{"args":[{"name":"product_id"},{"doc":"A size label of the product: M, 32, UK 7, Onesize.","name":"size"}],"class":"reversible","doc":"On the product page: ring the size selector and select the size. Refused when the product has no such size; an out-of-stock size is refused with the sizes in stock.","id":"product.size"},{"args":[{"name":"product_id"},{"doc":"The row to ring.","name":"size","optional":true}],"claims":["opening the size chart"],"class":"look","doc":"Open the product\'s size chart drawer (right) and ring the row of the size, if given.","id":"size_chart.open","objects":["size chart","साइज़ चार्ट"]},{"args":[{"name":"product_id"},{"name":"height_cm","optional":true,"type":"integer"},{"doc":"The size they usually wear: S, M, 32, UK 7.","name":"usual_size","optional":true},{"enum":["snug","regular","relaxed"],"name":"fit","optional":true}],"class":"reversible","doc":"On the product page\'s Find my size panel: open it and fill what the shopper said, each field ringed. Recommends nothing by itself.","id":"fit.fill"},{"args":[{"name":"product_id"},{"doc":"The recommended size, in stock.","name":"size"},{"doc":"One short sentence: why this size.","name":"reason"},{"doc":"The size the rule chose when it is out of stock (the card says so).","name":"wanted","optional":true}],"class":"reversible","doc":"Show the fit pick on the Find my size panel (the size, the reason, and the out-of-stock size it replaces) and select the size.","id":"fit.recommend"},{"args":[{"name":"product_id"},{"default":true,"name":"on","type":"boolean"}],"claims":["saving it to your wishlist","adding it to your wishlist"],"class":"reversible","doc":"Ring the product\'s heart and add it to (or take it off) the wishlist.","id":"wishlist.set","objects":["wishlist","विशलिस्ट"]},{"args":[{"name":"product_id"},{"name":"size"},{"default":1,"name":"qty","type":"integer"}],"claims":["adding it to your bag","added it to your bag"],"class":"confirmed","doc":"Ring Add to bag and add the product in that size (the bag count pulses). Refused for a size not in stock.","id":"bag.add","objects":["bag","बैग"]},{"args":[{"name":"product_id"},{"name":"size"},{"default":true,"name":"on","type":"boolean"},{"doc":"The gift note as the shopper dictated it, up to 150 characters.","name":"note","optional":true}],"claims":["gift wrapping","adding the note"],"class":"reversible","doc":"On the bag: ring the line\'s Gift wrap toggle and set it (₹49 an item), and fill its note. Navigates to /bag first.","id":"bag.gift","objects":["gift wrap","note","गिफ्ट"]},{"args":[{"enum":["contact","address","payment","place"],"name":"field"}],"class":"look","doc":"On /checkout: ring a section the shopper fills themselves (name and phone, address, payment) or the Place order button. Fills nothing: personal details are typed by the shopper.","id":"checkout.focus"},{"args":[{"doc":"Her, Him, Mom, Dad, Sister, Brother, Friend, Partner, Kid.","name":"recipient","optional":true},{"name":"occasion","optional":true},{"doc":"Rupees; 0 for no limit.","name":"budget_max","optional":true,"type":"integer"},{"doc":"Their size, if clothes or shoes are welcome.","name":"size","optional":true},{"name":"colours","optional":true,"type":"array"},{"doc":"Solid, Printed, Striped, Checked, Embroidered.","name":"patterns","optional":true,"type":"array"},{"doc":"Cotton, Silk, Leather, Steel.","name":"material","optional":true}],"class":"reversible","doc":"On /gifts: fill the gift brief as the shopper says it (absent fields are left as they are), each field ringed. Shows nothing by itself.","id":"gifts.brief"},{"args":[{"doc":"Three to six product ids.","name":"ids","type":"array"},{"doc":"One short reason per product, same order.","name":"reasons","type":"array"}],"claims":["here are","showing you"],"class":"reversible","doc":"On /gifts: show the gift shortlist, each card with its reason, ringed one by one.","id":"gifts.show","objects":["gift","gifts","shortlist","तोहफ़े"]},{"args":[{"doc":"FSH-48602.","name":"order_id"}],"claims":["opening your order"],"class":"navigate","doc":"On /orders: select the order and open its tracking and items, ringed.","id":"orders.open","objects":["order","tracking","ऑर्डर"]},{"args":[{"name":"order_id"}],"class":"look","doc":"Open the cancel dialog for an order that is not yet dispatched (Placed or Packed), ringing its Cancel order button. Cancels nothing: the shopper presses it. Refused once shipped.","id":"orders.cancel_open"},{"args":[{"name":"order_id"},{"doc":"The item to return.","name":"product_id","optional":true},{"enum":["size_small","size_large","not_as_pictured","quality","changed_mind","damaged","wrong_item"],"name":"reason","optional":true},{"doc":"The shopper said it is unused (only after they said so).","name":"unused","optional":true,"type":"boolean"},{"doc":"The shopper said the tags are intact (only after they said so).","name":"tags","optional":true,"type":"boolean"}],"class":"reversible","doc":"On /returns: open the order\'s return form and fill what was said, each field ringed. Submits nothing: the shopper presses Submit return. Refused when the order is outside the 7-day window or not delivered.","id":"returns.fill"},{"args":[{"name":"query","optional":true},{"name":"genders","optional":true,"type":"array"},{"name":"types","optional":true,"type":"array"},{"name":"colours","optional":true,"type":"array"},{"name":"sizes","optional":true,"type":"array"},{"name":"price_max","optional":true,"type":"integer"},{"name":"usage","optional":true,"type":"array"}],"class":"reversible","doc":"On the kiosk: search the whole catalogue and show the results grid (absent fields are cleared).","id":"kiosk.search"},{"args":[{"name":"product_id"}],"class":"look","doc":"On the kiosk: open one product full screen with its sizes, price and the QR code to its page.","id":"kiosk.show"},{"args":[{"doc":"Absent: the shortlist\'s QR code.","name":"product_id","optional":true}],"class":"look","doc":"On the kiosk: show the big QR code that opens the product page (or the shortlist) on the shopper\'s phone.","id":"kiosk.qr"},{"args":[{"name":"product_id"},{"default":true,"name":"on","type":"boolean"}],"class":"reversible","doc":"On the kiosk: add the product to (or take it off) the kiosk shortlist.","id":"kiosk.shortlist"},{"class":"reversible","doc":"On the kiosk: call a floor assistant (a banner says one is on the way).","id":"kiosk.assist"}],"slices":[{"doc":"the page in front of the shopper","fields":[{"name":"path"},{"name":"page"},{"name":"product_id","optional":true},{"name":"order_id","optional":true},{"name":"title","optional":true}],"id":"screen"},{"doc":"the listing\'s search","fields":[{"name":"summary"},{"name":"count","type":"integer"},{"name":"dept","optional":true},{"name":"types","optional":true,"type":"array"},{"name":"brands","optional":true,"type":"array"},{"name":"colours","optional":true,"type":"array"},{"name":"sizes","optional":true,"type":"array"},{"name":"price_min","optional":true,"type":"integer"},{"name":"price_max","optional":true,"type":"integer"},{"name":"discount_min","optional":true,"type":"integer"},{"name":"usage","optional":true,"type":"array"},{"name":"seasons","optional":true,"type":"array"},{"name":"query","optional":true},{"name":"sort","optional":true},{"name":"ids","optional":true,"type":"array"}],"id":"shop"},{"doc":"the product page: the size picked and the Find my size panel","fields":[{"name":"product_id"},{"name":"size","optional":true},{"name":"height_cm","optional":true,"type":"integer"},{"name":"usual_size","optional":true},{"name":"fit","optional":true}],"id":"product"},{"doc":"the bag","fields":[{"name":"count","type":"integer"},{"name":"total","type":"integer"},{"doc":"Each line as \\"<product id>|<size>|<qty>|<gift: 0 or 1>\\".","name":"lines","type":"array"}],"id":"bag"},{"doc":"the wishlist","fields":[{"name":"count","type":"integer"},{"name":"ids","type":"array"}],"id":"wishlist"},{"doc":"the checkout form: only whether each section is filled, never what the shopper typed","fields":[{"name":"contact","type":"boolean"},{"name":"address","type":"boolean"},{"name":"payment","type":"boolean"},{"name":"order_id","optional":true},{"name":"total","optional":true,"type":"integer"}],"id":"checkout"},{"doc":"the order selected on /orders","fields":[{"name":"order_id"},{"name":"status","optional":true}],"id":"order"},{"doc":"the return form","fields":[{"name":"order_id"},{"name":"product_id","optional":true},{"name":"reason","optional":true},{"name":"unused","optional":true,"type":"boolean"},{"name":"tags","optional":true,"type":"boolean"},{"name":"reference","optional":true}],"id":"return"},{"doc":"the gift finder\'s brief and shortlist","fields":[{"name":"recipient","optional":true},{"name":"occasion","optional":true},{"name":"budget_max","optional":true,"type":"integer"},{"name":"size","optional":true},{"name":"colours","optional":true,"type":"array"},{"name":"patterns","optional":true,"type":"array"},{"name":"material","optional":true},{"name":"ids","optional":true,"type":"array"}],"id":"gifts"},{"doc":"the kiosk: its search, the product open and the shortlist","fields":[{"name":"summary","optional":true},{"name":"count","optional":true,"type":"integer"},{"name":"ids","optional":true,"type":"array"},{"name":"product_id","optional":true},{"name":"shortlist","optional":true,"type":"array"}],"id":"kiosk"}],"stage":1}'
)
#: The spec's hash: a page reading another spec reports a different one.
SPEC_SHA256 = "938847e045b8a2cb5118c13ef9adae63a58e44af319779e79070b5db1af98374"


class GoArgs(BaseModel):
    """The arguments of ``site.go``."""

    path: str
    """A page: /, /shop, /shop/<dept>, /shop/<dept>/<type>, /p/<product id>, /compare?ids=a,b, /wishlist, /bag, /checkout, /orders, /returns, /gifts, /about. Not /kiosk."""


class FilterArgs(BaseModel):
    """The arguments of ``shop.filter``."""

    dept: (
        Literal["men", "women", "kids", "boys", "girls", "ethnic", "footwear", "accessories", "all"]
        | None
    ) = None
    """The department: the gender scope (men and women include unisex; boys and girls are kids; all: every product)."""
    types: list[str] | None = None
    """Article type ids from the catalogue (kurtas, heels, watches)."""
    brands: list[str] | None = None
    colours: list[str] | None = None
    """Catalogue colour names (Navy Blue, Maroon)."""
    sizes: list[str] | None = None
    """Size labels: M, XL, 32, UK 7. A product matches when one of them is in stock."""
    price_min: int | None = None
    """Rupees, the selling price."""
    price_max: int | None = None
    """Rupees, the selling price."""
    discount_min: int | None = None
    """At least this percent off MRP."""
    usage: list[str] | None = None
    """Occasion: Casual, Ethnic, Formal, Sports, Party, Smart Casual, Travel."""
    seasons: list[str] | None = None
    """Summer, Fall, Winter, Spring."""
    query: str | None = None
    """Words the product name must contain (silk, floral, chanderi)."""
    sort: Literal["popular", "price_asc", "price_desc", "discount", "new"] | None = None


class ShopShowArgs(BaseModel):
    """The arguments of ``shop.show``."""

    product_id: str
    """A product id on screen, 7421."""


class CompareShowArgs(BaseModel):
    """The arguments of ``compare.show``."""

    ids: list[str]
    """Two to four product ids."""


class SizeArgs(BaseModel):
    """The arguments of ``product.size``."""

    product_id: str
    size: str
    """A size label of the product: M, 32, UK 7, Onesize."""


class SizeChartOpenArgs(BaseModel):
    """The arguments of ``size_chart.open``."""

    product_id: str
    size: str | None = None
    """The row to ring."""


class FitFillArgs(BaseModel):
    """The arguments of ``fit.fill``."""

    product_id: str
    height_cm: int | None = None
    usual_size: str | None = None
    """The size they usually wear: S, M, 32, UK 7."""
    fit: Literal["snug", "regular", "relaxed"] | None = None


class RecommendArgs(BaseModel):
    """The arguments of ``fit.recommend``."""

    product_id: str
    size: str
    """The recommended size, in stock."""
    reason: str
    """One short sentence: why this size."""
    wanted: str | None = None
    """The size the rule chose when it is out of stock (the card says so)."""


class SetArgs(BaseModel):
    """The arguments of ``wishlist.set``."""

    product_id: str
    on: bool = True


class AddArgs(BaseModel):
    """The arguments of ``bag.add``."""

    product_id: str
    size: str
    qty: int = 1


class GiftArgs(BaseModel):
    """The arguments of ``bag.gift``."""

    product_id: str
    size: str
    on: bool = True
    note: str | None = None
    """The gift note as the shopper dictated it, up to 150 characters."""


class FocusArgs(BaseModel):
    """The arguments of ``checkout.focus``."""

    field: Literal["contact", "address", "payment", "place"]


class BriefArgs(BaseModel):
    """The arguments of ``gifts.brief``."""

    recipient: str | None = None
    """Her, Him, Mom, Dad, Sister, Brother, Friend, Partner, Kid."""
    occasion: str | None = None
    budget_max: int | None = None
    """Rupees; 0 for no limit."""
    size: str | None = None
    """Their size, if clothes or shoes are welcome."""
    colours: list[str] | None = None
    patterns: list[str] | None = None
    """Solid, Printed, Striped, Checked, Embroidered."""
    material: str | None = None
    """Cotton, Silk, Leather, Steel."""


class GiftsShowArgs(BaseModel):
    """The arguments of ``gifts.show``."""

    ids: list[str]
    """Three to six product ids."""
    reasons: list[str]
    """One short reason per product, same order."""


class OrdersOpenArgs(BaseModel):
    """The arguments of ``orders.open``."""

    order_id: str
    """FSH-48602."""


class CancelOpenArgs(BaseModel):
    """The arguments of ``orders.cancel_open``."""

    order_id: str


class ReturnsFillArgs(BaseModel):
    """The arguments of ``returns.fill``."""

    order_id: str
    product_id: str | None = None
    """The item to return."""
    reason: (
        Literal[
            "size_small",
            "size_large",
            "not_as_pictured",
            "quality",
            "changed_mind",
            "damaged",
            "wrong_item",
        ]
        | None
    ) = None
    unused: bool | None = None
    """The shopper said it is unused (only after they said so)."""
    tags: bool | None = None
    """The shopper said the tags are intact (only after they said so)."""


class SearchArgs(BaseModel):
    """The arguments of ``kiosk.search``."""

    query: str | None = None
    genders: list[str] | None = None
    types: list[str] | None = None
    colours: list[str] | None = None
    sizes: list[str] | None = None
    price_max: int | None = None
    usage: list[str] | None = None


class KioskShowArgs(BaseModel):
    """The arguments of ``kiosk.show``."""

    product_id: str


class QrArgs(BaseModel):
    """The arguments of ``kiosk.qr``."""

    product_id: str | None = None
    """Absent: the shortlist's QR code."""


class ShortlistArgs(BaseModel):
    """The arguments of ``kiosk.shortlist``."""

    product_id: str
    on: bool = True


class AssistArgs(BaseModel):
    """``kiosk.assist`` takes none."""


GO = Move(
    id="site.go",
    verb=None,
    cls=MoveClass.NAVIGATE,
    args=("path",),
    claims=(
        "opening the",
        "taking you to",
    ),
    objects=(
        "page",
        "product",
        "bag",
        "wishlist",
        "orders",
        "returns",
        "gifts",
        "पेज",
    ),
)
"""Go to a page of the store, ringing the link, card or icon that leads there first."""

FILTER = Move(
    id="shop.filter",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "dept",
        "types",
        "brands",
        "colours",
        "sizes",
        "price_min",
        "price_max",
        "discount_min",
        "usage",
        "seasons",
        "query",
        "sort",
    ),
    claims=(
        "filtering",
        "narrowing",
        "showing you",
    ),
    objects=(
        "filters",
        "filter",
        "results",
        "products",
        "kurtas",
        "फ़िल्टर",
    ),
)
"""Set the listing's whole search (absent fields are cleared). On /shop each filter control that changes is ringed and set in turn, then the grid follows. Navigates to /shop first when elsewhere."""

SHOP_SHOW = Move(
    id="shop.show",
    verb="show",
    cls=MoveClass.LOOK,
    args=("product_id",),
    say="{show: 7421} at the start of the sentence about one product on screen: its card is ringed.",
)
"""Ring one product's card (listing, compare, wishlist, gifts or kiosk results), scrolling it into view. Changes nothing."""

COMPARE_SHOW = Move(
    id="compare.show",
    verb=None,
    cls=MoveClass.NAVIGATE,
    args=("ids",),
    claims=(
        "comparing them",
        "side by side",
    ),
    objects=(
        "comparison",
        "compare",
        "तुलना",
    ),
)
"""Open /compare with these products side by side; the rows are ringed in turn."""

SIZE = Move(
    id="product.size",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "product_id",
        "size",
    ),
)
"""On the product page: ring the size selector and select the size. Refused when the product has no such size; an out-of-stock size is refused with the sizes in stock."""

SIZE_CHART_OPEN = Move(
    id="size_chart.open",
    verb=None,
    cls=MoveClass.LOOK,
    args=(
        "product_id",
        "size",
    ),
    claims=("opening the size chart",),
    objects=(
        "size chart",
        "साइज़ चार्ट",
    ),
)
"""Open the product's size chart drawer (right) and ring the row of the size, if given."""

FIT_FILL = Move(
    id="fit.fill",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "product_id",
        "height_cm",
        "usual_size",
        "fit",
    ),
)
"""On the product page's Find my size panel: open it and fill what the shopper said, each field ringed. Recommends nothing by itself."""

RECOMMEND = Move(
    id="fit.recommend",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "product_id",
        "size",
        "reason",
        "wanted",
    ),
)
"""Show the fit pick on the Find my size panel (the size, the reason, and the out-of-stock size it replaces) and select the size."""

SET = Move(
    id="wishlist.set",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "product_id",
        "on",
    ),
    claims=(
        "saving it to your wishlist",
        "adding it to your wishlist",
    ),
    objects=(
        "wishlist",
        "विशलिस्ट",
    ),
)
"""Ring the product's heart and add it to (or take it off) the wishlist."""

ADD = Move(
    id="bag.add",
    verb=None,
    cls=MoveClass.CONFIRMED,
    args=(
        "product_id",
        "size",
        "qty",
    ),
    claims=(
        "adding it to your bag",
        "added it to your bag",
    ),
    objects=(
        "bag",
        "बैग",
    ),
)
"""Ring Add to bag and add the product in that size (the bag count pulses). Refused for a size not in stock."""

GIFT = Move(
    id="bag.gift",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "product_id",
        "size",
        "on",
        "note",
    ),
    claims=(
        "gift wrapping",
        "adding the note",
    ),
    objects=(
        "gift wrap",
        "note",
        "गिफ्ट",
    ),
)
"""On the bag: ring the line's Gift wrap toggle and set it (₹49 an item), and fill its note. Navigates to /bag first."""

FOCUS = Move(
    id="checkout.focus",
    verb=None,
    cls=MoveClass.LOOK,
    args=("field",),
)
"""On /checkout: ring a section the shopper fills themselves (name and phone, address, payment) or the Place order button. Fills nothing: personal details are typed by the shopper."""

BRIEF = Move(
    id="gifts.brief",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "recipient",
        "occasion",
        "budget_max",
        "size",
        "colours",
        "patterns",
        "material",
    ),
)
"""On /gifts: fill the gift brief as the shopper says it (absent fields are left as they are), each field ringed. Shows nothing by itself."""

GIFTS_SHOW = Move(
    id="gifts.show",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "ids",
        "reasons",
    ),
    claims=(
        "here are",
        "showing you",
    ),
    objects=(
        "gift",
        "gifts",
        "shortlist",
        "तोहफ़े",
    ),
)
"""On /gifts: show the gift shortlist, each card with its reason, ringed one by one."""

ORDERS_OPEN = Move(
    id="orders.open",
    verb=None,
    cls=MoveClass.NAVIGATE,
    args=("order_id",),
    claims=("opening your order",),
    objects=(
        "order",
        "tracking",
        "ऑर्डर",
    ),
)
"""On /orders: select the order and open its tracking and items, ringed."""

CANCEL_OPEN = Move(
    id="orders.cancel_open",
    verb=None,
    cls=MoveClass.LOOK,
    args=("order_id",),
)
"""Open the cancel dialog for an order that is not yet dispatched (Placed or Packed), ringing its Cancel order button. Cancels nothing: the shopper presses it. Refused once shipped."""

RETURNS_FILL = Move(
    id="returns.fill",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "order_id",
        "product_id",
        "reason",
        "unused",
        "tags",
    ),
)
"""On /returns: open the order's return form and fill what was said, each field ringed. Submits nothing: the shopper presses Submit return. Refused when the order is outside the 7-day window or not delivered."""

SEARCH = Move(
    id="kiosk.search",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "query",
        "genders",
        "types",
        "colours",
        "sizes",
        "price_max",
        "usage",
    ),
)
"""On the kiosk: search the whole catalogue and show the results grid (absent fields are cleared)."""

KIOSK_SHOW = Move(
    id="kiosk.show",
    verb=None,
    cls=MoveClass.LOOK,
    args=("product_id",),
)
"""On the kiosk: open one product full screen with its sizes, price and the QR code to its page."""

QR = Move(
    id="kiosk.qr",
    verb=None,
    cls=MoveClass.LOOK,
    args=("product_id",),
)
"""On the kiosk: show the big QR code that opens the product page (or the shortlist) on the shopper's phone."""

SHORTLIST = Move(
    id="kiosk.shortlist",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "product_id",
        "on",
    ),
)
"""On the kiosk: add the product to (or take it off) the kiosk shortlist."""

ASSIST = Move(
    id="kiosk.assist",
    verb=None,
    cls=MoveClass.REVERSIBLE,
)
"""On the kiosk: call a floor assistant (a banner says one is on the way)."""

MOVES = MoveSet(
    (
        GO,
        FILTER,
        SHOP_SHOW,
        COMPARE_SHOW,
        SIZE,
        SIZE_CHART_OPEN,
        FIT_FILL,
        RECOMMEND,
        SET,
        ADD,
        GIFT,
        FOCUS,
        BRIEF,
        GIFTS_SHOW,
        ORDERS_OPEN,
        CANCEL_OPEN,
        RETURNS_FILL,
        SEARCH,
        KIOSK_SHOW,
        QR,
        SHORTLIST,
        ASSIST,
    )
)

#: The line each cue is taught with, in the spec's order.
PROMPT_LINES: tuple[str, ...] = (
    "{show: 7421} at the start of the sentence about one product on screen: its card is ringed.",
)

#: The slices of the page's state a read may name.
SliceId = Literal[
    "screen", "shop", "product", "bag", "wishlist", "checkout", "order", "return", "gifts", "kiosk"
]


class ReadRequest(BaseModel):
    """What the read tool takes: the slice to read, from the brain's mirror."""

    slice: SliceId = Field(
        description="Which part of their screen to read. screen: the page in front of the shopper; shop: the listing's search; product: the product page: the size picked and the Find my size panel; bag: the bag; wishlist: the wishlist; checkout: the checkout form: only whether each section is filled, never what the shopper typed; order: the order selected on /orders; return: the return form; gifts: the gift finder's brief and shortlist; kiosk: the kiosk: its search, the product open and the shortlist."
    )
