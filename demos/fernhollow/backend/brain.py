"""FernhollowBrain — Emily, the design adviser of a home and furniture store.

A :class:`voqalize_demos.GeminiBrain`. Voqalize dials this brain's WebSocket per
session; the inherited tool loop runs Gemini's calls as they arrive. Emily asks
about the room one question at a time, puts a whole room on the shopper's
screen for their brief and budget, swaps pieces, compares, finds look-alikes
and things that go with a piece, stretches the budget with real sale prices,
and adds the room to the cart once the shopper says yes.

**Speed.** The catalog is local and small, so everything that can be computed
offline is (:mod:`.build_index`): the attribute words, a word index, look-alike
lists from image embeddings, goes-with lists, room candidates. Every tool is a
handful of dict reads plus a small search (:mod:`.engine`) and answers in a few
milliseconds, well inside the SDK's budget. After each turn the brain
precomputes what the shopper is likely to ask next for what is on screen —
the cheaper look-alikes of the piece in view, the comparison of the top two in a
list, what goes with the pinned piece — so those are cache hits.

**What is marked ``@needs_result_now``.** The tools whose answer only the
engine knows and the model must speak from: the brief's next question, the
room it built, the swap, the strips, the comparison, the filtered count and its
assumption, the savings, the product facts ``show`` returns, the finishing
touch. The rest — remove a filter, undo, the shortlist, the cart, a policy
already in the prompt — say their line with the call.

**The screen is the brain's own mirror.** Every dispatch updates it, and every
typed event the page sends (:mod:`.app_events`) folds into it, so "this one"
and "the second one" resolve to what is on screen now. A ``[SCREEN NOW]`` note
goes in front of each thing the shopper says.

**No invented facts.** Tool results carry catalog titles and prices, reasons
built from the words the catalog itself uses, and authored policies. Nothing
states a dimension, a stock level or a delivery date.
"""

from __future__ import annotations

import re
import time
from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel, Field
from voqalize_demos import (
    PATIENCE,
    FallbackLine,
    GeminiBrain,
    configure_soon,
    landed,
    needs_result_now,
)

from voqalize.sdk import (
    Action,
    AppEvents,
    RTVIMessage,
    Session,
    Speech,
    SpeechChunk,
    UserIdle,
    UserMessage,
)
from voqalize.sdk.stage import Mirror, Stage
from voqalize.sdk.stage.wire import StageEvent, StageHello, StageProgress, StageResult
from voqalize.sdk.voice import ToolChoice
from voqalize.sdk.wire import Config, IdleConfig, SttConfig, TtsConfig

from . import engine as eng
from .app_events import (
    FERNHOLLOW_EVENTS,
    CartChanged,
    CheckoutChanged,
    CheckoutStepReached,
    ChoiceMade,
    ConfirmResult,
    FernhollowEvent,
    FilterChanged,
    OrdersKnown,
    PageViewed,
    Pointing,
    ProductViewed,
    RoomBoardEdited,
    Selection,
    SelectionCleared,
    ShortlistChanged,
    VariantSelected,
    VisibleProducts,
)
from .catalog import CATALOG, JOURNAL_DIR, Product, money
from .checkout import (
    FIELDS,
    PRIVATE,
    REQUIRED,
    STEPS,
    CheckoutField,
    CheckoutStepName,
    check,
    delivery_fee,
)
from .confirm import Acted, Confirmations, Pending, classify
from .edits import KIOSK, budget_chip, gift_key, kiosk_key
from .edits import stored as stored_edits
from .persona import PERSONA
from .policies import Topic, policy_page, policy_text
from .prompt import GREETINGS, Job, job_for, system_instruction
from .recipes import FINISHING, RECIPES
from .resolve import SELECTED, Layout, Resolution
from .resolve import resolve as resolve_reference
from .returns import WINDOW_DAYS, Order, exchange_options, order_from
from .returns import find_order as find_any_order
from .stage_gen import MOVES, SPEC
from .tracking import (
    TRACKED,
    Slot,
    Tracked,
    day_words,
    find_tracked,
    group_of,
    plain_status,
    tracked_from_known,
)

#: Every event the page sends: the store's own typed events and Stage's.
_EVENTS = AppEvents(*FERNHOLLOW_EVENTS, StageResult, StageHello, StageProgress, StageEvent)

#: The ``by`` the page puts on changes Emily made herself. "mira" is the name a
#: page built before the persona was renamed still sends; drop it next release.
AGENT_BY = frozenset({"emily", "mira"})

#: How long a quiet spell is before Emily may speak up of her own accord, and
#: how short it gets while she has something the page asked her to say (the
#: shopper pressed Submit return).
_IDLE_MS = 12000
_REACT_IDLE_MS = 1500
#: A line the brain already knows (a return's outcome): said as soon as the voice is free.
_SAY_NOW_MS = 400
#: Once the address is filled: one line, nothing read back (owner, 2026-11-03 —
#: reading the address field by field made checkout drag).
CHECK_ON_SCREEN = (
    "I've filled in your details on screen — please check them and click Review order."
)
#: Once the grid follows a taste: the offer to plan the whole room (owner, 2026-11-03).
ROOM_OFFER = "Would you like me to help set up the entire room?"

# ─── Actions: brain → UI (CONTRACT.md) ────────────────────────────────────────


class Navigate(Action):
    """Route change: home | room/<room> | category/<slug> | product/<id> |
    journal | journal/<slug> | cart | policy/<topic>."""

    page: str


class ShowProducts(Action):
    """A listing grid with these products."""

    title: str
    query: str
    product_ids: list[str]
    count: int


class FiltersOut(BaseModel):
    """The filter chips."""

    room: str | None = None
    category: str | None = None
    materials: list[str] = Field(default_factory=list[str])
    colours: list[str] = Field(default_factory=list[str])
    styles: list[str] = Field(default_factory=list[str])
    price_min: float | None = None
    price_max: float | None = None
    on_sale: bool | None = None


class ApplyFilters(Action):
    """Filter chips + grid; ``assumption`` is what a broad word was read as."""

    filters: FiltersOut
    product_ids: list[str]
    count: int
    assumption: str | None = None


class RemoveFilter(Action):
    """One chip removed: ``key`` is a filter key, or ``key:value`` for one value
    of a list filter (``materials:oak``)."""

    key: str
    product_ids: list[str]
    count: int


class OpenProduct(Action):
    """The product page, with its focus section ringed."""

    product_id: str
    variant_id: str | None = None
    focus: Literal["options", "highlights", "price"] | None = None


class SelectVariant(Action):
    """The variant picker set and ringed."""

    product_id: str
    variant_id: str


class Highlight(Action):
    """A 300 ms spotlight ring: product:<id> | filter:<key> | slot:<slot> |
    button:add-to-cart | section:<name>."""

    target: str


class BriefOut(BaseModel):
    room: str | None = None
    uses: list[str] = Field(default_factory=list[str])
    materials: list[str] = Field(default_factory=list[str])
    colours: list[str] = Field(default_factory=list[str])
    styles: list[str] = Field(default_factory=list[str])
    budget: float | None = None


class AskOut(BaseModel):
    """The question Emily asks next, so the page can show what she is asking."""

    dim: str
    options: list[str]


class UpdateBrief(Action):
    """The brief, and the question Emily asks next (the page points at its options)."""

    brief: BriefOut
    products_left: int
    asking: AskOut | None = None


class PieceOut(BaseModel):
    """One room-board tile."""

    slot: str
    product_id: str
    variant_id: str
    title: str
    price: float
    compare_at: float | None = None
    image: str
    reason: str


class ShowRoomSet(Action):
    """The room board; pieces appear one by one."""

    room: str
    budget: float | None
    total: float
    pieces: list[PieceOut]


class SwapPiece(Action):
    """One room-board tile changes."""

    slot: str
    old_product_id: str
    piece: PieceOut
    total: float


class RemovePieces(Action):
    """Room-board tiles taken off; the rest stay as they are."""

    slots: list[str]
    total: float


class CompareRow(BaseModel):
    label: str
    values: list[str]
    winner: int | None = None


class ShowCompare(Action):
    """The compare board."""

    product_ids: list[str]
    rows: list[CompareRow]
    summary: str


class GoesWithItem(BaseModel):
    product_id: str
    reason: str


class ShowGoesWith(Action):
    """The goes-with strip."""

    anchor_id: str
    items: list[GoesWithItem]


class MoreLikeItem(BaseModel):
    product_id: str
    differences: list[str]


class ShowMoreLike(Action):
    """The look-alike strip, with difference badges."""

    anchor_id: str
    items: list[MoreLikeItem]


class SavingSwap(BaseModel):
    slot: str
    from_id: str
    to_id: str
    was: float
    now: float


class ShowSavings(Action):
    """Savings badges on the room board; ``moved_to`` is the slot the saving
    went to."""

    swaps: list[SavingSwap]
    saved: float
    moved_to: str | None = None


class UpdateShortlist(Action):
    """The shortlist tray."""

    product_ids: list[str]


class ShowSaved(Action):
    """The shopper's saved picks, together on one page (``/saved``): how they
    look side by side, not a feature table and not the cart."""

    product_ids: list[str]
    title: str
    note: str = ""


class ConfirmLine(BaseModel):
    product_id: str
    variant_id: str
    qty: int


class ConfirmAdd(Action):
    """The confirm prompt on the Add button."""

    lines: list[ConfirmLine]
    label: str


class CartLine(BaseModel):
    product_id: str
    variant_id: str
    qty: int
    title: str
    price: float
    image: str


class CartUpdated(Action):
    """The cart drawer opens with these lines."""

    lines: list[CartLine]
    total: float
    saved: float


class SuggestFinish(Action):
    """A suggestion card in the cart."""

    product_id: str
    reason: str


class OpenPolicy(Action):
    """The policy panel."""

    topic: Topic


class CheckoutFill(Action):
    """Ring a checkout input and set it."""

    field: CheckoutField
    value: str


class CheckoutStep(Action):
    """Move the checkout to a step."""

    step: CheckoutStepName


class ConfirmPlaceOrder(Action):
    """The confirm prompt on Place order."""

    total: float
    label: str


class OrderPlaced(Action):
    """The confirmation page, with the demo order's number."""

    order_number: str
    total: float


class ShowChoices(Action):
    """Numbered badges 1..n on these product cards (2-4, all on screen)."""

    product_ids: list[str]
    label: str


class ClearChoices(Action):
    """The choice badges removed."""


class ClearSelection(Action):
    """The circled selection's badges and chip removed."""


class Undo(Action):
    """Revert the last screen-changing action."""


# ─── Tool parameters (what the model asks for) ────────────────────────────────

Room = Literal["living", "dining", "bedroom", "home-office", "bath", "kitchen", "decor"]


class BriefUpdate(BaseModel):
    """Everything the shopper has said about the room so far."""

    room: Room | None = Field(default=None, description="The room, once known.")
    uses: list[str] = Field(
        default_factory=list[str],
        description="How they use it, e.g. 'long hours' when they sit there for long hours.",
    )
    materials: list[str] = Field(
        default_factory=list[str], description="Materials they want, in their words."
    )
    colours: list[str] = Field(
        default_factory=list[str], description="Colours they want, in their words."
    )
    styles: list[str] = Field(
        default_factory=list[str], description="The feel they want, in their words."
    )
    budget: float | None = Field(default=None, description="Budget for the whole room, dollars.")
    pieces: list[str] = Field(
        default_factory=list[str],
        description=(
            "Every kind of piece they said they want, in their words and in the order said "
            "(sofa, rug, cushions). The brain keeps this list for the whole call."
        ),
    )
    no_preference: list[Literal["styles", "materials", "colours", "budget", "uses"]] = Field(
        default_factory=list[Literal["styles", "materials", "colours", "budget", "uses"]],
        description="Questions they answered with no preference.",
    )


class BuildRoom(BaseModel):
    room: Room | None = Field(default=None, description="Defaults to the brief's room.")
    budget: float | None = Field(default=None, description="Defaults to the brief's budget.")


class SwapRequest(BaseModel):
    slot: str = Field(description="The room-board slot: desk, chair, lamp, shelving, rug, sofa…")
    want: list[str] = Field(
        default_factory=list[str],
        description="Words the new piece should carry: a material, colour or style.",
    )
    cheaper: bool = Field(default=False, description="True for a cheaper piece.")
    product: str | None = Field(
        default=None, description="A specific product to put in: id, ordinal on screen, or 'this'."
    )


class PieceOptionsRequest(BaseModel):
    slot: str = Field(description="The board piece to see options for: desk, chair, lamp, rug…")
    want: list[str] = Field(
        default_factory=list[str],
        description="Words the options should carry, as said: a material, colour or style.",
    )


class RemoveRequest(BaseModel):
    pieces: list[str] = Field(
        description="The pieces to take off the board: slot names (desk, lamp, rug…), ordinals on screen, 'this', or ids."
    )


class GoesWithRequest(BaseModel):
    anchor: str = Field(description="The piece: slot name, ordinal on screen, 'this', or id.")
    category: str | None = Field(
        default=None, description="One category slug, e.g. 'artwork', 'vases', 'rugs'."
    )


class MoreLikeRequest(BaseModel):
    anchor: str = Field(description="The piece: slot name, ordinal on screen, 'this', or id.")
    change: eng.Change = Field(description="The one thing to change.")
    value: str | None = Field(
        default=None,
        description="For option: the option value (e.g. 'Walnut'); for material/colour/style: the word.",
    )


class CompareRequest(BaseModel):
    products: list[str] = Field(
        description="Two or three products: slot names, ordinals on screen, or ids."
    )


class EditCompare(BaseModel):
    add: list[str] = Field(default_factory=list[str])
    remove: list[str] = Field(default_factory=list[str])


class FilterRequest(BaseModel):
    room: Room | None = None
    category: str | None = Field(default=None, description="A category slug.")
    materials: list[str] = Field(default_factory=list[str], description="In the shopper's words.")
    colours: list[str] = Field(default_factory=list[str], description="In the shopper's words.")
    styles: list[str] = Field(default_factory=list[str], description="In the shopper's words.")
    price_min: float | None = None
    price_max: float | None = None
    on_sale: bool | None = None


class RemoveFilterRequest(BaseModel):
    key: Literal[
        "room", "category", "materials", "colours", "styles", "price_min", "price_max", "on_sale"
    ]
    value: str | None = Field(default=None, description="One value of a list filter, or empty.")


class StretchRequest(BaseModel):
    priority: str | None = Field(
        default=None, description="The slot the shopper cares most about, if they said."
    )


class ShowRequest(BaseModel):
    product: str | None = Field(
        default=None, description="A product: id, ordinal on screen, slot name, or 'this'."
    )
    option: str | None = Field(default=None, description="An option value to select, e.g. 'Oak'.")
    focus: Literal["options", "highlights", "price"] | None = None
    page: str | None = Field(
        default=None,
        description="home, room/<room>, category/<slug>, journal, journal/<slug>, cart, saved, policy/<topic>, gifts, orders, kiosk.",
    )
    query: str | None = Field(default=None, description="Search words, for a results grid.")


class ShortlistRequest(BaseModel):
    add: list[str] = Field(default_factory=list[str])
    remove: list[str] = Field(default_factory=list[str])


class AddToCartRequest(BaseModel):
    what: Literal["saved", "room", "product"] = Field(
        default="product",
        description=(
            "saved: every pick on their saved list, in one go (what they chose); room: the "
            "room board; product: the products named."
        ),
    )
    product: str | None = Field(default=None, description="For one product: the reference.")
    products: list[str] = Field(
        default_factory=list[str],
        description="Several products at once: references as for product.",
    )
    option: str | None = Field(default=None, description="Option value, if they chose one.")


class PolicyRequest(BaseModel):
    topic: Topic


class ReturnItem(BaseModel):
    product: str = Field(description="An item of the order: its product id or its name.")
    qty: int | None = Field(
        default=None, description="How many go back; empty when they have not said (asked)."
    )


class ReturnAnswers(BaseModel):
    """What the shopper just said for their return; leave the rest empty."""

    items: list[ReturnItem] = Field(
        default_factory=list[ReturnItem], description="Items they named, with how many."
    )
    reason: (
        Literal[
            "changed_mind", "doesnt_suit_room", "arrived_damaged", "wrong_item", "not_as_expected"
        ]
        | None
    ) = None
    condition: Literal["unused_in_packaging", "unused_unpacked", "damaged_on_arrival"] | None = None
    resolution: Literal["refund", "exchange", "store_credit"] | None = None
    exchange_option: str | None = Field(
        default=None, description="For an exchange: the option value they want instead (Walnut)."
    )
    collection: Literal["pickup", "drop_off"] | None = None
    pickup_window: Literal["weekday_morning", "weekday_afternoon", "saturday"] | None = None


class ResolveRequest(BaseModel):
    spoken: str = Field(description="The shopper's words for the product, as heard.")
    scope: Literal["auto", "screen", "catalog"] = Field(
        default="auto",
        description="auto: the screen first, then the catalog; screen: only what is on screen.",
    )


class CheckoutFields(BaseModel):
    """Checkout fields the shopper just gave, in their words; leave the rest empty.
    Email and phone are not here: the shopper types those themselves."""

    first_name: str | None = None
    last_name: str | None = None
    address1: str | None = None
    address2: str | None = None
    city: str | None = None
    region: str | None = None
    postcode: str | None = None
    country: str | None = None
    delivery: str | None = Field(default=None, description="Delivery notes for the driver, if any.")


class CheckoutStepRequest(BaseModel):
    step: CheckoutStepName


class PlaceOrderRequest(BaseModel):
    confirmed_by_voice: bool = Field(
        default=False,
        description="True only when the shopper said yes to the Place order confirmation on screen.",
    )


class SubmitReturnRequest(BaseModel):
    confirmed_by_voice: bool = Field(
        default=False,
        description="True only when the shopper said yes to submitting the return.",
    )


class ExchangeRequest(BaseModel):
    product: str = Field(description="A line of the order: its product id, or its title.")


class GiftRequest(BaseModel):
    recipient: Literal["partner", "parent", "sibling", "friend", "host", "colleague"] | None = None
    occasion: Literal["housewarming", "birthday", "thank_you", "wedding", "just_because"] | None = (
        None
    )
    budget: float | None = Field(
        default=None, description="The most they want to spend, in dollars, as they said it."
    )
    no_budget: bool = Field(
        default=False, description="True when they said not to worry about a budget."
    )


class KioskRequest(BaseModel):
    """The kiosk's answers so far."""

    room: Literal["living", "bedroom", "dining", "home-office"] | None = None
    feel: Literal["warm_wood", "soft_neutrals", "clean_lines", "natural_texture"] | None = None
    budget: Literal["150", "400", "1000", "any"] | None = Field(
        default=None,
        description="Spend per piece: up to 150, 400 or 1000 dollars, or any for no limit.",
    )


# ─── The screen mirror ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Screen:
    """What the shopper's screen shows, as the brain last made it or was told."""

    page: str = "home"
    product: str | None = None
    variant: str | None = None
    listing: tuple[str, ...] = ()  # the products in the latest grid or strip, in order
    listing_kind: str = ""
    filters: eng.Filters = field(default_factory=eng.Filters)
    room: eng.RoomSet | None = None
    compare: tuple[str, ...] = ()
    strip_anchor: str | None = None


_ORDINALS = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
}


def _prose(head: str, **fields: Any) -> str:
    """A tool result as a sentence and an indented outline, never a dict repr."""
    lines = [head]
    for key, value in fields.items():
        if value is None or value == [] or value == "":
            continue
        label = key.replace("_", " ")
        if isinstance(value, list):
            lines.append(f"{label}:")
            lines.extend(f"  - {v}" for v in value)  # pyright: ignore[reportUnknownVariableType]
        else:
            lines.append(f"{label}: {value}")
    return "\n".join(lines)


def _line(p: Product, extra: str = "") -> str:
    tail = f" — {extra}" if extra else ""
    return f"{p.title} — {p.price_text()}{tail} [id {p.id}]"


#: The turn's floor line is an exact outcome the brain knows (a refusal, a
#: duplicate): said as written, never re-asked of the model, which could
#: misstate it. Per turn, like the landed lines.
_EXACT: ContextVar[list[bool] | None] = ContextVar("fernhollow_exact_floor", default=None)


def _exact(line: str) -> None:
    landed(line)
    # A box, not a value: a tool runs in a copy of the turn's context, and a
    # copy shares the box.
    if (box := _EXACT.get()) is not None:
        box[0] = True


async def _nothing() -> AsyncGenerator[Speech, None]:
    return
    yield  # an async generator that yields nothing


def _not_done(why: str, what_to_do: str) -> str:
    # The floor, if the model then says nothing: never a claim it went through.
    _exact("That didn't go through yet.")
    return _prose(f"NOT DONE: {why}.", next=what_to_do)


# Emily's model and thinking level (owner, 2026-11-02): gemini-3.6-flash at LOW. Both are
# model-specific (see VOICE_THINKING in voqalize.sdk.gemini); measured on one short prompt,
# LOW spent ~480 thought tokens and ~3 s more than MINIMAL before the first word.
MODEL = "gemini-3.6-flash"
THINKING = types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)


class FernhollowBrain(GeminiBrain):
    """One per session: the brief, the screen mirror, the shortlist and the cart."""

    def __init__(self, *, client: genai.Client, model: str = MODEL) -> None:
        super().__init__(
            client=client, system_instruction=system_instruction(), model=model, thinking=THINKING
        )
        self.brief = eng.Brief()
        self.screen = Screen()
        self.history: list[Screen] = []
        self.shortlisted: list[str] = []
        # Every kind of piece the shopper asked for, as category slugs, in the
        # order said (owner, round 1: "sofa, a rug and cushions" is the brief
        # for the whole call, walked through in order, never forgotten).
        self.wants: list[str] = []
        self.want_words: dict[str, str] = {}  # slug → the shopper's own word
        self.cart: dict[tuple[str, str], int] = {}
        # Emily offered to set up the whole room, once the grid followed a taste.
        self.room_offered = False
        # What add_to_cart put in, by its lines, and on which turn.
        self.added: dict[tuple[tuple[str, str, int], ...], int] = {}
        # Every confirmation Emily asks for, one mechanism (confirm.py).
        self.confirms = Confirmations()
        self.confirms.register("add_to_cart", self._act_add)
        self.confirms.register("place_order", self._act_place)
        self.confirms.register("submit_return", self._act_submit)
        self.confirms.register("cancel_order", self._act_cancel)
        self.turns = 0
        self.seen: dict[str, list[str]] = {}  # slot → products shown there
        self.ahead: dict[tuple[Any, ...], Any] = {}
        self.hits = 0
        self.order: Order | None = None  # the order the returns desk is working on
        # What is under the shopper's pointer, and when; the visible grid's layout;
        # the numbered choices Emily asked between.
        self.pointing: tuple[str, float] | None = None
        self.layout: tuple[Layout, ...] = ()
        self.choices: tuple[str, ...] = ()
        # Checkout as Emily filled it (values) and as the page reports it (names).
        self.checkout: dict[str, str] = {}
        self.checkout_filled: set[str] = set()
        self.checkout_step_now: str | None = None
        self.orders_placed = 0
        # What the shopper last circled, as (kind, id): kept across pages until
        # cleared, and acted on only when they speak about it.
        self.selection: tuple[tuple[str, str], ...] = ()
        # Orders this session placed, and the ones the page says it holds: both
        # come before the demo orders when the shopper names one.
        self.placed_orders: list[Order] = []
        self.known_orders: list[Order] = []
        # The open return form as the brain set it or was told (choices only).
        self.form: dict[str, str] = {}
        self.form_items: dict[str, int] = {}
        self.return_collection: str | None = None
        self.last_reference: str = ""  # the latest return reference the page reported
        # A line of the brain's own for the next quiet spell (an outcome), and
        # when the last one was said: a page "speak" reaction just after an
        # outcome Emily said would be the same news twice.
        self._say_next: Callable[[], str] | None = None
        self._outcome_at = float("-inf")
        # The returns form is driven by Stage: cues in Emily's words fill it as
        # she says them — this is a demo, so the email too (CONTRACT.md, v2).
        self.stage = Stage(
            dispatch=lambda a: self.session.dispatch(a),
            moves=MOVES,
            mirror=Mirror(SPEC),
        )
        self._talk: str | None = None  # an ask the page left for the next quiet spell
        # The job (CONTRACT.md, v5): picked by the landing page, switched when
        # the shopper lands on another job's page.
        self.job: Job = "shop"
        self.language = PERSONA.default_language
        # The gift edit's controls (budget 0 is no limit, None not asked yet), the
        # kiosk's answers and screen, and what was done to orders this session:
        # delivery days moved (order → slot), cancelled, earlier delivery asked.
        self.gift: tuple[str | None, str | None, int | None] = (None, None, None)
        self.kiosk: dict[str, str] = {}
        self.kiosk_screen = "attract"
        self.delivery: dict[str, str] = {}
        self.cancelled: set[str] = set()
        self.earlier: set[str] = set()
        # Orders placed in this browser, as the orders page shows them (packed).
        self.known_tracked: dict[str, Tracked] = {}
        # The return form: the step in front, and an item named without how many.
        self.form_step = 1
        self.form_pending: str | None = None
        self.form_later: dict[str, str] = {}  # answers given before their step
        self._fallback = FallbackLine()

    # ─── Session ────────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        """The persona's voice for the language the page asked for (English
        is the only one offered today), on both legs before the greeting; and
        the job, from the page the call started on (CONTRACT.md, v5)."""
        init = session.init or {}
        self.language = PERSONA.language(init.get("lang"))
        self.job = job_for(str(init.get("landing") or "/")) or "shop"
        await session.configure(
            Config(
                tts=TtsConfig(voice=PERSONA.voice(self.language), language=self.language),
                stt=SttConfig(language=self.language, patience=PATIENCE),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
            )
        )

    async def greet(self, session: Session) -> str:
        """Fixed — no model call — so the agent speaks the instant the call
        connects, with the greeting of the job the page started. On the kiosk
        the screen moves to question 1 as she asks it (the page also starts
        itself when the call goes live; a second start is a no-op)."""
        if self.job == "kiosk" and self.kiosk_screen == "attract":
            self._send("kiosk.start", {})
            self.kiosk_screen = "room"
        return GREETINGS[self.job]

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[Speech, None]:
        """The screen as it is goes in front of the shopper's words, so "this
        one" resolves against now."""
        self.turns += 1
        self.stage.visitor_spoke()
        self._talk = None
        self._settle_expired()
        pending = self.confirms.due(self.turns)
        answer = classify(msg.text) if pending is not None else None
        if pending is not None and pending.kind == "cancel_order" and _CANCEL_YES.match(msg.text):
            answer = "yes"  # "cancel it" answers "Shall I cancel order…?" with a yes
        self.append_note(self.screen_now())
        self.append_note(msg.text)
        if pending is not None and answer == "yes":
            # The yes is acted on here, and its line is the brain's own: the
            # model does not run, so this turn cannot be a silent tool call.
            acted = self.confirms.act(pending)
            self.append_note(acted.note)
            async for speech in self.say_line(acted.line, remember=True):
                yield speech
            return
        if pending is not None and answer == "no":
            self.confirms.clear()
            self.append_note(f"[The shopper said no to: {pending.label}. Nothing was done.]")
        async for speech in self._unjargoned(self.respond(session)):
            yield speech

    async def _unjargoned(
        self, speech: AsyncGenerator[Speech, None]
    ) -> AsyncGenerator[Speech, None]:
        """Speech with this brain's tool names taken out. On a prod call the
        model said "update_brief helps set up the brief for your space": the
        SDK stops a call written as text, not a tool's name used as a word."""
        names = {t.__name__ for t in self.tools}
        pattern = re.compile(r"\s*\b(?:" + "|".join(map(re.escape, sorted(names))) + r")\b")
        async for s in speech:
            if isinstance(s, SpeechChunk) and pattern.search(s.text):
                text = pattern.sub("", s.text)
                if not text.strip():
                    continue
                s = SpeechChunk(text)
            yield s

    async def _invoke_tool(
        self, tool: Callable[..., Any] | None, name: str, run: Callable[[], Awaitable[Any]]
    ) -> dict[str, Any]:
        """Every call — one that lands, one refused, a duplicate — records a
        floor line first, so a turn that only called tools is never silent; a
        tool's own landed line comes after and is the one said."""
        landed("Here's where that stands.")
        return await super()._invoke_tool(tool, name, run)

    def _confirmed_by_tool(self, kind: str) -> str:
        """The model calling a confirmed tool with ``confirmed_by_voice``: the
        same act as a spoken yes, once. Already done, or not yet answered,
        still says something."""
        pending = self.confirms.due(self.turns, kind)
        if pending is not None:
            acted = self.confirms.act(pending)
            landed(acted.line)
            return _prose(acted.note, said=acted.line)
        if (line := self.confirms.already_kind(kind)) is not None:
            _exact(line)
            return _prose(f"Already done, not sent again. {line}")
        return _not_done(
            "the shopper has not said yes to it yet", "Ask first, then wait for their yes."
        )

    # ─── What each confirmation does when the shopper says yes ─────────

    def _act_add(self, pending: Pending) -> Acted:
        lines: list[ConfirmLine] = pending.data["lines"]
        self._commit_cart(lines)
        return Acted(
            "Added to your cart.",
            f"[{pending.label}: in the cart, which now totals {money(self._cart_total())}. "
            "Do not call add_to_cart again.]",
        )

    def _act_place(self, pending: Pending) -> Acted:
        number = self._place(float(pending.data["total"]), pending.data.get("order_number"))
        return Acted(
            f"It's placed — your order number is {number}.",
            f"[The order {number} is placed, {money(float(pending.data['total']))}. "
            "Do not call place_order again.]",
        )

    def _act_submit(self, pending: Pending) -> Acted:
        ref = self.stage.send("returns.submit", {}, queue=False)
        return Acted(
            "Submitting it now.",
            "[The return is being submitted; you tell them the page's answer when it comes. "
            "Do not call submit_return again.]",
            ref=ref,
            on_applied=lambda detail: self._submitted_line(
                _reference(detail) or self.last_reference
            ),
        )

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The model's turn; if it acted and said nothing, one more request with
        tools off so she talks about what she just did and leads to the next
        step (owner, round 1: the written floor alone — "Filtered.", "It's on
        the shortlist." — made her sound like "a dumb agent"); the landed line
        stays the floor under a second silence. Then the look-ahead."""
        exact = [False]
        _EXACT.set(exact)
        turn = self.stage.cued(super().respond(session))
        async for event in self._fallback.speak_if_silent(
            self,
            turn,
            again=lambda: _nothing() if exact[0] else self.stage.cued(self._talk_now(session)),
        ):
            yield event
        self.stage.end_turn()
        self.look_ahead()

    def _talk_now(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The one extra request a silent move gets: tools declared, none callable."""
        self.append_note(
            "[You acted on screen and said nothing. Say now, in one or two full sentences, "
            "what is on screen from the result, and lead to the next step.]"
        )
        return self.respond_with(session, tools=ToolChoice.NONE)

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Something the shopper did on the page. The mirror follows it and the
        model gets one line; nothing is spoken."""
        event = _EVENTS.parse(msg)
        if event is None:
            return
        if isinstance(event, StageResult | StageHello | StageProgress | StageEvent):
            staged = self._staged(event)
            if staged is not None:
                logger.info("fernhollow: stage {}", staged)
                self.append_note(staged)
            return
        note = self.apply_event(event)
        # The page also reports what Emily herself just did (``by: "emily"``, and
        # ``"mira"`` from a page one release behind): the mirror follows it, but
        # the model already knows, so no note. Only the shopper's own acts are told.
        if note is not None and event.by not in AGENT_BY:
            logger.info("fernhollow: shopper {}", note)
            self.append_note(note)

    def on_user_idle(self, session: Session, idle: UserIdle) -> AsyncGenerator[Speech, None]:
        """A quiet spell. If the page left something for Emily to say — the
        shopper pressed Submit return — she says it now, in one line; otherwise
        she stays quiet: a shopper browsing is not nudged."""
        return self._idle(session)

    async def _idle(self, session: Session) -> AsyncGenerator[Speech, None]:
        self._settle_expired()
        say, self._say_next = self._say_next, None
        ask, self._talk = self._talk, None
        configure_soon(session, Config(idle=IdleConfig(timeout_ms=_IDLE_MS)))
        if say is not None:
            # An outcome the brain knows exactly (applied, refused, unknown):
            # its own written line, once, with no model turn — rendered now, so
            # a reference the page reported since is in it.
            self._outcome_at = time.monotonic()
            async for event in self.say_line(say(), remember=True):
                yield event
            return
        if ask is None:
            return
        self.append_note(f"[{ask}]")
        async for event in self._unjargoned(self.respond(session)):
            yield event

    def _staged(self, event: StageResult | StageHello | StageProgress | StageEvent) -> str | None:
        """One answer from the Stage page, folded in; the line the model reads,
        if any. A cue that landed was spoken past and needs no line; one that
        did not is said plainly, with what the page offers instead."""
        if isinstance(event, StageEvent):
            extra = self._fold_store_event(event)
            folded = self.stage.handle(event)
            if extra is not None and event.by == "visitor":
                return extra
            if folded is None:
                return None
            if ref := str(event.data.get("reference") or ""):
                self.last_reference = ref
            if self._say_next is not None or time.monotonic() - self._outcome_at < _OUTCOME_GAP_S:
                # An outcome of Emily's own is said, or about to be: the page's
                # "speak" reaction to the same act would be the news twice.
                self.stage.take_reaction()
                return None
            if event.by == "visitor" and (ask := self.stage.take_reaction()):
                self._talk = ask
                configure_soon(self.session, Config(idle=IdleConfig(timeout_ms=_REACT_IDLE_MS)))
            return folded.note if event.by == "visitor" else None
        if not isinstance(event, StageResult):
            self.stage.handle(event)
            return None
        result = self.stage.handle(event)
        return None if result is None else self._settle(result)

    def _settle_expired(self) -> None:
        """Moves the page never answered come back ``unknown`` and are told."""
        for result in self.stage.expire():
            note = self._settle(result)
            if note is not None:
                self.append_note(note)

    def _settle(self, result: StageResult) -> str | None:
        """Every result, one way: a confirmed act's outcome is said once; a
        form run's is told with the step; a cue that did not land is said."""
        if self.confirms.is_flight(result.call_ref):
            why = "; ".join(r.why for r in result.refused)
            line = self.confirms.outcome(result.call_ref, result.outcome, result.detail, why)
            self._say_line_soon(line)
            return f"[The page answered: {result.outcome} — {result.detail or why or 'no detail'}.]"
        if result.moved or result.outcome in ("applied", "partial", "undone"):
            return None
        move = self.stage.move_of(result.call_ref)
        offers = "; ".join(
            f"{r.arg}: {r.why}" + (f" (options: {', '.join(r.options)})" if r.options else "")
            for r in result.refused
        )
        what = move.id if move else result.move
        self._say_line_soon(
            lambda: (
                f"That didn't take — the page says: {result.detail or offers or result.outcome}."
            )
        )
        return (
            f"[Your {what} cue did not land ({result.detail or result.outcome}"
            + (f"; {offers}" if offers else "")
            + "). Never say it did; use one of the options, or ask.]"
        )

    def _submitted_line(self, reference: str) -> str:
        how = "the pickup" if self.return_collection == "pickup" else "the drop-off"
        ref = f", reference {reference}" if reference else ""
        return f"Done — your return is in{ref}. We'll be in touch about {how}."

    def _say_line_soon(self, line: str | Callable[[], str]) -> None:
        """A written line for the next quiet spell, made short so it comes now."""
        self._say_next = line if callable(line) else (lambda: line)
        configure_soon(self.session, Config(idle=IdleConfig(timeout_ms=_SAY_NOW_MS)))

    # ─── The screen ─────────────────────────────────────────────────────

    def screen_now(self) -> str:
        s = self.screen
        parts = [f"job: {self.job}", f"page: {s.page}"]
        if s.product is not None and (p := CATALOG.get(s.product)) is not None:
            variant = p.variant_for(None)
            if s.variant:
                variant = next((v for v in p.variants if v.id == s.variant), variant)
            parts.append(f"product open: {p.title} ({variant.value}) [id {p.id}]")
        if s.room is not None:
            tiles = ", ".join(
                f"{pc.slot}: {pc.product.title} {money(pc.product.price)} [id {pc.product_id}]"
                for pc in s.room.pieces
            )
            budget = f" of {money(s.room.budget)}" if s.room.budget else ""
            parts.append(
                f"room board ({s.room.room}, total {money(s.room.total)}{budget}): {tiles}"
            )
        if s.compare:
            parts.append(
                "compare board: "
                + ", ".join(
                    f"{n}. {CATALOG.products[i].title} [id {i}]" for n, i in enumerate(s.compare, 1)
                )
            )
        if s.listing:
            parts.append(
                f"{s.listing_kind or 'list'} in order: "
                + ", ".join(
                    f"{n}. {CATALOG.products[i].title} [id {i}]"
                    for n, i in enumerate(s.listing[:8], 1)
                )
            )
        if self.wants:
            parts.append(f"the shopper's list: {self._wants_line()}")
        elif self.shortlisted:
            parts.append(
                "saved picks: "
                + ", ".join(f"{CATALOG.products[i].title} [id {i}]" for i in self.shortlisted)
            )
        if self.cart:
            parts.append(
                f"cart ({sum(self.cart.values())} items, {money(self._cart_total())}): "
                + ", ".join(CATALOG.products[pid].title for pid, _ in self.cart)
            )
        else:
            parts.append("cart: empty")
        if self.confirms.pending is not None:
            parts.append(f"waiting for the shopper's yes on: {self.confirms.pending.label}")
        if self.selection:
            parts.append(f"circled: {self._selection_line()}")
        if self.choices:
            parts.append(
                "numbered choices: "
                + ", ".join(
                    f"{n}. {CATALOG.products[i].title} [id {i}]"
                    for n, i in enumerate(self.choices, 1)
                )
            )
        if self.checkout_step_now or self.checkout:
            filled = sorted(set(self.checkout) | self.checkout_filled)
            missing = [f for f in REQUIRED if f not in filled]
            parts.append(
                f"checkout at {self.checkout_step_now or 'contact'}: filled {', '.join(filled) or 'nothing'}"
                + (f"; still needed {', '.join(missing)}" if missing else "")
            )
        return "[SCREEN NOW — " + " · ".join(parts) + "]"

    # ─── The shopper's list: what they asked for, walked through in order ─

    def _picked(self, slug: str) -> str | None:
        """The saved pick for one kind of piece on the list, if any."""
        return next(
            (i for i in reversed(self.shortlisted) if CATALOG.products[i].category_slug == slug),
            None,
        )

    def _wants_line(self) -> str:
        out: list[str] = []
        for slug in self.wants:
            name = self.want_words.get(slug) or CATALOG.categories[slug].name.lower()
            pick = self._picked(slug)
            out.append(
                f"{name} — saved: {CATALOG.products[pick].title} [id {pick}]"
                if pick
                else f"{name} — not chosen yet"
            )
        return "; ".join(out)

    def _lead(self) -> str | None:
        """The next step to offer, as a choice of two, from the shopper's list."""
        if not self.wants:
            return None
        left = [w for w in self.wants if self._picked(w) is None]
        done = [w for w in self.wants if self._picked(w) is not None]
        names = {
            w: self.want_words.get(w) or CATALOG.categories[w].name.lower() for w in self.wants
        }
        if not left:
            return (
                "every piece on their list is saved: offer to show their picks together "
                "(show_saved) or to add them all to the cart (add_to_cart what=saved)"
            )
        nxt = left[0]
        if done:
            last = names[done[0]]  # the first piece chosen anchors the rest
            if len(left) > 1:
                return (
                    f'ask: "Shall we move on to the {names[nxt]} now, or see {names[left[1]]} '
                    f'that go with the {last}?"'
                )
            return f'ask: "Shall I show you {names[nxt]} that go with the {last}?"'
        return f"show {names[nxt]} first (their list: {', '.join(names[w] for w in self.wants)})"

    def _move(self, **changes: Any) -> None:
        """Change the mirror, keeping the old one for undo."""
        self.history.append(self.screen)
        del self.history[:-20]
        self.screen = replace(self.screen, **changes)

    def resolve(self, ref: str | None) -> Product | None:
        """A product reference as the model passes it: an id, a room-board slot,
        an ordinal into the latest list on screen, or "this"."""
        if not ref:
            return None
        r = ref.strip().lower()
        if (p := CATALOG.get(ref.strip())) is not None:
            return p
        s = self.screen
        if s.room is not None and (pc := s.room.piece(r.replace(" ", "_"))) is not None:
            return pc.product
        if s.room is not None:
            for pc in s.room.pieces:
                slot = RECIPES[s.room.room].slot(pc.slot)
                if slot is not None and r in (slot.label, slot.name, slot.label.split()[-1]):
                    return pc.product
        res = self.reference(ref)
        if res.kind == "one" and res.product_id is not None:
            if res.source == "choices":
                self._clear_choices()
            return CATALOG.products[res.product_id]
        return None

    def reference(
        self, spoken: str, scope: Literal["auto", "screen", "catalog"] = "auto"
    ) -> Resolution:
        """The resolver, given everything the brain knows about the screen."""
        s = self.screen
        seq = s.compare if s.listing_kind == "compare" else s.listing
        layout = self.layout if {x.product_id for x in self.layout} == set(seq) else ()
        pointing, age = (
            (self.pointing[0], time.monotonic() - self.pointing[1])
            if self.pointing
            else (None, None)
        )
        saved = [*self.shortlisted, *(pc.product_id for pc in (s.room.pieces if s.room else ()))]
        return resolve_reference(
            spoken,
            pointing=pointing,
            pointing_age_s=age,
            choices=self.choices,
            visible=seq,
            layout=layout,
            saved=saved,
            open_product=s.product,
            scope=scope,
            selection=self.selected_products(),
        )

    def _adopt_page_numbers(self) -> None:
        """The number the confirmation page shows is the one the shopper will
        read back: an order Emily placed takes the page's number when the page
        holds the same order (same lines and total) under another one."""
        for n, mine in enumerate(self.placed_orders):
            key = (round(mine.total, 2), sorted((x.product_id, x.qty) for x in mine.lines))
            for theirs in self.known_orders:
                if theirs.number == mine.number:
                    break
                if (
                    round(theirs.total, 2),
                    sorted((x.product_id, x.qty) for x in theirs.lines),
                ) == key:
                    adopted = replace(mine, number=theirs.number)
                    self.placed_orders[n] = adopted
                    if self.order is not None and self.order.number == mine.number:
                        self.order = adopted
                    break

    def lookup_order(self, text: str) -> Order | None:
        return find_any_order(text, placed=self.placed_orders, known=self.known_orders)

    def selected_products(self) -> list[str]:
        return [i for k, i in self.selection if k == "product" and i in CATALOG.products]

    def _selection_line(self) -> str:
        """What is circled, in one line the model can say from."""
        out: list[str] = []
        for kind, ident in self.selection:
            if kind == "product" and (p := CATALOG.get(ident)) is not None:
                out.append(f"{p.title} — {p.price_text()} [id {p.id}]")
            elif kind == "room" and ident in RECIPES:
                out.append(f"the {RECIPES[ident].label} room [room {ident}]")
            elif kind == "category" and (c := CATALOG.categories.get(ident)) is not None:
                out.append(f"the {c.name.lower()} category [category {ident}]")
            elif kind == "article":
                out.append(f"the journal article '{ident.replace('-', ' ')}' [article {ident}]")
        return "; ".join(out)

    def expand(self, refs: Sequence[str]) -> tuple[list[str], str | None]:
        """Product references, with "these" / "the circled ones" expanded to
        the selection. The second value says why it cannot be used as is: a
        selection that holds things other than products."""
        ids: list[str] = []
        for ref in refs:
            if SELECTED.match(ref.strip().lower()) and self.selection:
                if any(k != "product" for k, _ in self.selection):
                    return [], "the circled selection mixes products with rooms or categories"
                ids += self.selected_products()
                continue
            p = self.resolve(ref)
            if p is not None:
                ids.append(p.id)
        return list(dict.fromkeys(ids)), None

    def _clear_choices(self) -> None:
        if self.choices:
            self.choices = ()
            self.session.dispatch(ClearChoices())

    def _memo(self, key: tuple[Any, ...], make: Callable[[], Any]) -> Any:
        if key in self.ahead:
            self.hits += 1
            return self.ahead[key]
        value = make()
        self.ahead[key] = value
        return value

    def look_ahead(self) -> None:
        """Precompute the likely next answers for what is on screen now: the
        cheaper look-alikes of the piece in view, the comparison of the top two
        in a list, and what goes with the pinned piece."""
        s = self.screen
        brief_key = self.brief.key()
        if len(self.ahead) > 400:
            self.ahead.clear()
        anchors: list[str] = []
        if s.product:
            anchors.append(s.product)
        if s.room is not None:
            anchors += [pc.product_id for pc in s.room.pieces]
        exclude = tuple(pc.product_id for pc in s.room.pieces) if s.room else ()
        for a in dict.fromkeys(anchors):
            self._memo(("more_like", a, "cheaper", None), lambda a=a: eng.more_like(a, "cheaper"))
            self._memo(
                ("goes_with", a, None, exclude), lambda a=a: eng.goes_with(a, exclude=exclude)
            )
        if len(s.listing) >= 2:
            pair = tuple(s.listing[:2])
            self._memo(("compare", pair, brief_key), lambda: eng.compare(pair, self.brief))
        if s.room is None and self.brief.room and self.brief.budget:
            # The brief has a room and a budget: "put it together" is next.
            brief = self.brief
            self._memo(("room", brief_key), lambda: eng.build_room(brief))
        if s.room is not None:
            room = s.room
            self._memo(
                ("stretch", room, brief_key, None),
                lambda: eng.stretch_budget(room, self.brief, None),
            )

    # ─── Pieces as the UI and the model see them ───────────────────────

    def _piece_out(self, pc: eng.Piece) -> PieceOut:
        p = pc.product
        return PieceOut(
            slot=pc.slot,
            product_id=p.id,
            variant_id=pc.variant_id,
            title=p.title,
            price=p.price,
            compare_at=p.compare_at if p.on_sale else None,
            image=p.image,
            reason=pc.reason,
        )

    def _brief_out(self) -> BriefOut:
        b = self.brief
        return BriefOut(
            room=b.room,
            uses=list(b.uses),
            materials=list(b.materials),
            colours=list(b.colours),
            styles=list(b.styles),
            budget=b.budget,
        )

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        return [
            self.update_brief,
            self.build_room,
            self.swap_piece,
            self.remove_pieces,
            self.piece_options,
            self.goes_with,
            self.more_like,
            self.compare,
            self.edit_compare,
            self.set_filters,
            self.remove_filter,
            self.undo,
            self.stretch_budget,
            self.show,
            self.shortlist,
            self.show_saved,
            self.add_to_cart,
            self.suggest_finish,
            self.store_policy,
            self.start_return,
            self.fill_return,
            self.check_exchange,
            self.submit_return,
            self.resolve_product,
            self.fill_checkout,
            self.checkout_step,
            self.place_order,
            self.clear_selection,
            self.gift_edit,
            self.track_order,
            self.change_delivery,
            self.cancel_order,
            self.request_earlier,
            self.kiosk_answer,
            self.kiosk_restart,
        ]

    @needs_result_now
    async def update_brief(self, update: BriefUpdate) -> str:
        """Merge what the shopper said about the room into the brief and show it.
        Returns how many products are left and the ONE next question to ask —
        ask exactly that one."""
        b = self.brief
        assumptions: list[str] = []
        unmatched: list[str] = []

        def merge(
            kind: Literal["materials", "colours", "styles"], terms: list[str]
        ) -> tuple[str, ...]:
            if not terms:
                return getattr(b, kind)
            mapped = eng.map_terms(kind, terms)
            assumptions.extend(mapped.assumptions)
            unmatched.extend(mapped.unmatched)
            return tuple(dict.fromkeys((*getattr(b, kind), *mapped.words)))

        for word in update.pieces:
            slug = _category(word)
            if slug is None:
                unmatched.append(word)
            elif slug not in self.wants:
                self.wants.append(slug)
                self.want_words[slug] = word.strip().lower()
        uses = tuple(dict.fromkeys((*b.uses, *(_use(u) for u in update.uses))))
        self.brief = eng.Brief(
            room=update.room or b.room,
            uses=uses,
            materials=merge("materials", update.materials),
            colours=merge("colours", update.colours),
            styles=merge("styles", update.styles),
            budget=update.budget if update.budget is not None else b.budget,
            skipped=tuple(dict.fromkeys((*b.skipped, *update.no_preference))),
        )
        left = eng.products_left(self.brief)
        question = eng.next_question(self.brief)
        asking = (
            AskOut(dim=question.dim, options=list(question.options))
            if question.dim in eng.TASTE_DIMS and question.options
            else None
        )
        self.session.dispatch(
            UpdateBrief(brief=self._brief_out(), products_left=len(left), asking=asking)
        )
        # The grid follows the brief: once a taste is known it is applied, so
        # the shopper sees what Emily is choosing from rather than being sent
        # to the sidebar. The budget is for the whole room, not a price cap.
        b = self.brief
        brief_filters = eng.Filters(
            room=b.room, materials=b.materials, colours=b.colours, styles=b.styles
        )
        on_grid: str | None = None
        focus = next((w for w in self.wants if self._picked(w) is None), None)
        if self.screen.room is None and focus is not None:
            # Their list leads: the first piece not yet chosen, in their taste.
            want = eng.Filters(
                category=focus, materials=b.materials, colours=b.colours, styles=b.styles
            )
            if not want.results():
                want = eng.Filters(category=focus)
            if want != self.screen.filters:
                ids, _ = self._apply(want, None)
                tastes = ", ".join((*want.colours, *want.styles, *want.materials))
                on_grid = (
                    f"the {self.want_words.get(focus, focus)} listing is open"
                    + (f", filtered to {tastes}" if tastes else "")
                    + f": {len(ids)} to choose from, first "
                    + "; ".join(_line(CATALOG.products[i]) for i in ids[:3])
                )
        elif (
            self.screen.room is None
            and (b.materials or b.colours or b.styles)
            and brief_filters != self.screen.filters
            and (fits := brief_filters.results())
        ):
            self._apply(brief_filters, None)
            on_grid = (
                f"the listing's own filters are being ticked for "
                f"{', '.join((*b.colours, *b.styles, *b.materials))}, one by one, and the grid "
                f"narrows to the {len(fits)} that fit; say what you are filtering as it happens"
            )
        elif (
            self.brief.room
            and self.screen.page != f"room/{self.brief.room}"
            and self.screen.room is None
        ):
            self._move(page=f"room/{self.brief.room}")
            self.session.dispatch(Navigate(page=f"room/{self.brief.room}"))
        # Once the grid follows a taste: offer the whole room, then on a yes
        # and a budget, build it (owner, 2026-11-03).
        ask = question.text
        lead = self._lead()
        if self.wants:
            # They named the pieces they want: no whole-room offer, walk the list.
            ask = (
                "name one or two of these in a sentence and ask which they like"
                if on_grid
                else (lead or question.text)
            )
        elif self.screen.room is None and on_grid and not self.room_offered:
            self.room_offered = True
            ask = ROOM_OFFER
        elif self.screen.room is None and self.room_offered and b.budget:
            ask = "they asked for the whole room and gave the budget: call build_room now"
        landed(
            ask
            if ask == ROOM_OFFER
            else "Here are some to choose from. Which one catches your eye?"
            if self.wants and on_grid
            else question.text
        )
        logger.info(
            "fernhollow: brief {} → {} left, ask {}", self.brief.key(), len(left), question.dim
        )
        return _prose(
            f"The brief is noted. {len(left)} products in the store fit it so far.",
            their_list=self._wants_line() or None,
            grid=on_grid,
            ask_next=ask,
            assumptions=assumptions,
            not_matched=[
                f"'{u}' is not a word the catalog uses; ask what they mean" for u in unmatched
            ],
        )

    @needs_result_now
    async def build_room(self, request: BuildRoom) -> str:
        """Put a whole room on the screen for the brief and budget: one piece per
        slot, sharing materials and colours, within budget. Returns the pieces
        with reasons and the total — present it as a whole."""
        if request.room or request.budget is not None:
            self.brief = replace(
                self.brief,
                room=request.room or self.brief.room,
                budget=request.budget if request.budget is not None else self.brief.budget,
            )
        brief = self.brief
        result = self._memo(("room", brief.key()), lambda: eng.build_room(brief))
        if isinstance(result, eng.RoomError):
            if result.lowest_total is not None:
                return _not_done(
                    f"no {RECIPES[brief.room or 'living'].label} set fits that budget",
                    f"The lowest this room can go is {money(result.lowest_total)}; ask whether to stretch the budget or drop a piece.",
                )
            return _not_done(result.reason, "Ask which room first.")
        self._move(room=result, page=f"room/{result.room}", product=None)
        self.seen = {pc.slot: [pc.product_id] for pc in result.pieces}
        self.session.dispatch(
            ShowRoomSet(
                room=result.room,
                budget=result.budget,
                total=result.total,
                pieces=[self._piece_out(pc) for pc in result.pieces],
            )
        )
        landed("Here's the room.", "There's your room.")
        budget = f" against a budget of {money(result.budget)}" if result.budget else ""
        return _prose(
            f"The {RECIPES[result.room].label} is on the room board: total {money(result.total)}{budget}.",
            pieces=[f"{pc.slot}: {_line(pc.product, pc.reason)}" for pc in result.pieces],
        )

    @needs_result_now
    async def swap_piece(self, request: SwapRequest) -> str:
        """Replace one slot on the room board — cheaper, carrying wanted words, or
        a named product — with the rest of the room held still."""
        room = self.screen.room
        if room is None:
            return _not_done("there is no room on the board", "Build the room first.")
        slot = request.slot.strip().lower().replace(" ", "_")
        if room.piece(slot) is None:
            match = self.resolve(slot)
            found = next(
                (pc.slot for pc in room.pieces if match and pc.product_id == match.id), None
            )
            if found is None:
                return _not_done(
                    f"there is no {request.slot} on the board", "Use one of the slots on the board."
                )
            slot = found
        named = self.resolve(request.product) if request.product else None
        if request.product and named is None:
            return _not_done(
                f"I cannot tell which product '{request.product}' is", "Ask which one."
            )
        want: list[str] = []
        for kind in ("materials", "colours", "styles"):
            want += eng.map_terms(kind, request.want).words
        new = eng.swap_piece(
            room,
            self.brief,
            slot,
            want=want,
            cheaper=request.cheaper,
            product_id=named.id if named else None,
            seen=self.seen.get(slot, []),
        )
        if isinstance(new, eng.RoomError):
            return _not_done(
                new.reason, "Say so, and offer to look beyond the budget or another slot."
            )
        old = room.piece(slot)
        assert old is not None
        updated = room.with_piece(new)
        self._move(room=updated)
        self.seen.setdefault(slot, []).append(new.product_id)
        self.session.dispatch(
            SwapPiece(
                slot=slot,
                old_product_id=old.product_id,
                piece=self._piece_out(new),
                total=updated.total,
            )
        )
        landed(f"Here's another {slot.replace('_', ' ')}.", "Swapped.")
        return _prose(
            f"The {slot.replace('_', ' ')} is swapped on the board. Room total now {money(updated.total)}.",
            was=_line(old.product),
            now=_line(new.product, new.reason),
        )

    @needs_result_now
    async def piece_options(self, request: PieceOptionsRequest) -> str:
        """Show the store's other options for one piece — "show me other desks" —
        as a grid to choose from: that piece's category, carrying any wanted
        words. Nothing on the board changes until they pick one (swap_piece)."""
        room = self.screen.room
        slot = request.slot.strip().lower().replace(" ", "_")
        piece = room.piece(slot) if room else None
        category = piece.product.category_slug if piece else _category(request.slot)
        if category is None:
            return _not_done(
                f"I cannot tell which kind of piece '{request.slot}' is", "Ask which piece."
            )
        filters = eng.Filters(
            category=category,
            materials=eng.map_terms("materials", request.want).words,
            colours=eng.map_terms("colours", request.want).words,
            styles=eng.map_terms("styles", request.want).words,
        )
        widened = None
        if not filters.results():
            # Nothing carries those words: show the whole category and say so.
            filters = eng.Filters(category=category)
            widened = f"nothing in {', '.join(request.want)}; showing every one instead"
        ids, _ = self._apply(filters, None)
        current = piece.product_id if piece else None
        name = CATALOG.categories[category].name.lower()
        landed(f"Here are some other {name}.", "Here are the options.")
        return _prose(
            f"The grid shows {len(ids)} {name} to choose from.",
            note=widened,
            on_screen=[
                f"{n}. {_line(CATALOG.products[i])}{' (the one on the board)' if i == current else ''}"
                for n, i in enumerate(ids[:6], 1)
            ],
            next="name two or three in a line and ask which one; when they pick, swap_piece with that product",
        )

    async def remove_pieces(self, request: RemoveRequest) -> str:
        """Take pieces off the room board — the shopper does not need them —
        with the rest of the room held still."""
        room = self.screen.room
        if room is None:
            return _not_done("there is no room on the board", "Build the room first.")
        slots: list[str] = []
        unknown: list[str] = []
        for ref in request.pieces:
            slot = ref.strip().lower().replace(" ", "_")
            if room.piece(slot) is None:
                match = self.resolve(ref)
                slot = next(
                    (pc.slot for pc in room.pieces if match and pc.product_id == match.id), ""
                )
            if slot and slot not in slots:
                slots.append(slot)
            elif not slot:
                unknown.append(ref)
        if not slots:
            return _not_done(
                f"there is no {', '.join(request.pieces)} on the board",
                "Use one of the slots on the board.",
            )
        gone = [pc for pc in room.pieces if pc.slot in slots]
        updated = replace(room, pieces=tuple(pc for pc in room.pieces if pc.slot not in slots))
        self._move(room=updated)
        self.session.dispatch(RemovePieces(slots=slots, total=updated.total))
        names = " and ".join(s.replace("_", " ") for s in slots)
        landed(f"I've taken off the {names}.", "Taken off the board.")
        return _prose(
            f"Taken off the board: {names}. Room total now {money(updated.total)}.",
            removed=[_line(pc.product) for pc in gone],
            left=[pc.slot.replace("_", " ") for pc in updated.pieces],
            not_on_board=unknown,
        )

    @needs_result_now
    async def goes_with(self, request: GoesWithRequest) -> str:
        """Show pieces that sit beside one anchor piece, optionally from one
        category (artwork, vases, rugs…)."""
        anchor = self.resolve(request.anchor)
        if anchor is None:
            return _not_done(f"I cannot tell which piece '{request.anchor}' is", "Ask which one.")
        category = request.category
        if category is not None and category not in CATALOG.categories:
            category = _category(category)
        exclude = tuple(pc.product_id for pc in self.screen.room.pieces) if self.screen.room else ()
        items = self._memo(
            ("goes_with", anchor.id, category, exclude),
            lambda: eng.goes_with(anchor.id, category=category, exclude=exclude),
        )
        if not items:
            return _not_done(
                "nothing in that category is paired with it", "Offer another category."
            )
        ids = tuple(i.product_id for i in items)
        self._move(listing=ids, listing_kind="goes-with strip", strip_anchor=anchor.id)
        self.session.dispatch(
            ShowGoesWith(
                anchor_id=anchor.id,
                items=[GoesWithItem(product_id=i.product_id, reason=i.reason) for i in items],
            )
        )
        landed("These go with it.", "Here's what sits well beside it.")
        return _prose(
            f"Pieces to go with {anchor.title} are on screen, in this order.",
            items=[_line(CATALOG.products[i.product_id], i.reason) for i in items],
        )

    @needs_result_now
    async def more_like(self, request: MoreLikeRequest) -> str:
        """Show look-alikes of one piece with one change: cheaper, on sale, an
        option value, or a material / colour / style word."""
        anchor = self.resolve(request.anchor)
        if anchor is None:
            return _not_done(f"I cannot tell which piece '{request.anchor}' is", "Ask which one.")
        items, own = self._memo(
            ("more_like", anchor.id, request.change, request.value),
            lambda: eng.more_like(anchor.id, request.change, request.value),
        )
        note = None
        if own is not None:
            note = f"{anchor.title} itself also comes in {request.value}."
        if not items:
            return _not_done(
                f"no look-alike of {anchor.title} is {request.change.replace('_', ' ')}",
                note or "Say so and offer another change.",
            )
        ids = tuple(i.product_id for i in items)
        self._move(listing=ids, listing_kind="look-alike strip", strip_anchor=anchor.id)
        self.session.dispatch(
            ShowMoreLike(
                anchor_id=anchor.id,
                items=[
                    MoreLikeItem(product_id=i.product_id, differences=list(i.differences))
                    for i in items
                ],
            )
        )
        landed("Here are some look-alikes.", "A few like it.")
        return _prose(
            f"Look-alikes of {anchor.title} ({anchor.price_text()}) are on screen, in this order.",
            items=[
                f"{CATALOG.products[i.product_id].title} — {'; '.join(i.differences)} [id {i.product_id}]"
                for i in items
            ],
            note=note,
        )

    def _show_compare(self, ids: Sequence[str]) -> str:
        brief = self.brief
        key = tuple(ids)
        result: eng.Comparison = self._memo(
            ("compare", key, brief.key()), lambda: eng.compare(key, brief)
        )
        self._move(compare=result.product_ids, listing=result.product_ids, listing_kind="compare")
        self.session.dispatch(
            ShowCompare(
                product_ids=list(result.product_ids),
                rows=[
                    CompareRow(label=r.label, values=list(r.values), winner=r.winner)
                    for r in result.rows
                ],
                summary=result.summary,
            )
        )
        landed("Here they are side by side.", "The comparison is up.")
        names = [CATALOG.products[i].title for i in result.product_ids]
        return _prose(
            "The comparison is on screen, in this column order: "
            + "; ".join(f"{n}. {t}" for n, t in enumerate(names, 1))
            + ".",
            rows=[
                f"{r.label}: "
                + " | ".join(r.values)
                + (f" (winner: {names[r.winner]})" if r.winner is not None else "")
                for r in result.rows
            ],
            summary=result.summary,
        )

    @needs_result_now
    async def compare(self, request: CompareRequest) -> str:
        """Compare two to four products side by side; each row names its winner.
        "these" compares what the shopper circled."""
        ids, why = self.expand(request.products)
        if why is not None or len(ids) > 4:
            what = self._selection_line() if self.selection else ""
            return _not_done(
                why or f"{len(ids)} products are circled, and a comparison holds two to four",
                f"Say what is circled in one line ({what}) and ask which to compare.",
            )
        if len(ids) < 2:
            return _not_done(
                "a comparison needs two to four products I can tell apart", "Ask which ones."
            )
        kinds = {CATALOG.products[i].category_slug for i in ids}
        if len(kinds) > 1:
            # A sofa against a rug compares nothing (owner, round 1): they want
            # to see them together.
            return _not_done(
                "these are different kinds of piece, and a comparison only makes sense within one kind",
                "Call show_saved to put their picks side by side on one page instead.",
            )
        return self._show_compare(ids)

    @needs_result_now
    async def edit_compare(self, request: EditCompare) -> str:
        """Add a product to, or drop one from, the comparison on screen."""
        current = list(self.screen.compare)
        for r in request.remove:
            p = self.resolve(r)
            if p is not None and p.id in current:
                current.remove(p.id)
        for r in request.add:
            p = self.resolve(r)
            if p is not None and p.id not in current:
                current.append(p.id)
        if len(current) < 2 or len(current) > 4:
            return _not_done("a comparison holds two to four products", "Ask which to keep.")
        return self._show_compare(current)

    def _apply(self, filters: eng.Filters, assumption: str | None) -> tuple[list[str], str]:
        ids = filters.results()
        self._move(
            filters=filters,
            listing=tuple(ids[:24]),
            listing_kind="grid",
            # The page filters the listing itself now, in its sidebar.
            page=(
                f"category/{filters.category}"
                if filters.category
                else f"room/{filters.room}"
                if filters.room
                else "shop"
            ),
            product=None,
        )
        self.session.dispatch(
            ApplyFilters(
                filters=FiltersOut(
                    room=filters.room,
                    category=filters.category,
                    materials=list(filters.materials),
                    colours=list(filters.colours),
                    styles=list(filters.styles),
                    price_min=filters.price_min,
                    price_max=filters.price_max,
                    on_sale=filters.on_sale,
                ),
                product_ids=ids[:48],
                count=len(ids),
                assumption=assumption,
            )
        )
        return ids, assumption or ""

    @needs_result_now
    async def set_filters(self, request: FilterRequest) -> str:
        """Filter the store's grid. Pass the shopper's own words; the result says
        how they were read — say that assumption aloud."""
        assumptions: list[str] = []
        unmatched: list[str] = []
        lists: dict[str, tuple[str, ...]] = {}
        for kind in ("materials", "colours", "styles"):
            terms: list[str] = getattr(request, kind)
            mapped = eng.map_terms(kind, terms)
            assumptions += mapped.assumptions
            unmatched += mapped.unmatched
            lists[kind] = mapped.words
        category = request.category
        if category is not None and category not in CATALOG.categories:
            guess = _category(category)
            if guess is None:
                unmatched.append(category)
            else:
                assumptions.append(
                    f"I took '{category}' as {CATALOG.categories[guess].name.lower()}"
                )
            category = guess
        filters = eng.Filters(
            room=request.room,
            category=category,
            materials=lists["materials"],
            colours=lists["colours"],
            styles=lists["styles"],
            price_min=request.price_min,
            price_max=request.price_max,
            on_sale=request.on_sale,
        )
        if request.price_max is not None:
            assumptions.append(f"up to {money(request.price_max)} including that price")
        assumption = "; ".join(assumptions) or None
        ids, _ = self._apply(filters, assumption)
        landed(f"{len(ids)} pieces fit.", "Filtered.")
        return _prose(
            f"The grid shows {len(ids)} products.",
            assumption=assumption,
            not_matched=[f"'{u}' is not a word the catalog uses" for u in unmatched],
            first=[_line(CATALOG.products[i]) for i in ids[:4]],
        )

    async def remove_filter(self, request: RemoveFilterRequest) -> str:
        """Take one filter (or one value of it) off the grid."""
        f = self.screen.filters
        key = request.key
        if key in ("materials", "colours", "styles"):
            values: tuple[str, ...] = getattr(f, key)
            if request.value:
                drop = set(eng.map_terms(key, [request.value]).words) | {request.value.lower()}
                values = tuple(v for v in values if v not in drop)
            else:
                values = ()
            f = replace(f, **{key: values})
        else:
            f = replace(f, **{key: None})
        ids = f.results()
        self._move(filters=f, listing=tuple(ids[:24]), listing_kind="grid")
        wire_key = f"{key}:{request.value}" if request.value else key
        self.session.dispatch(RemoveFilter(key=wire_key, product_ids=ids[:48], count=len(ids)))
        landed("Filter off.", "Done.")
        return _prose(f"Removed. The grid shows {len(ids)} products.")

    async def undo(self) -> str:
        """Put the screen back one step."""
        if not self.history:
            return _not_done("there is nothing to undo", "Say so.")
        self.screen = self.history.pop()
        self.session.dispatch(Undo())
        landed("Back as it was.", "Undone.")
        return _prose("The last change is undone.", screen=self.screen_now())

    @needs_result_now
    async def stretch_budget(self, request: StretchRequest) -> str:
        """Swap room pieces for on-sale look-alikes at their real sale prices, and
        move the saving to the shopper's priority piece."""
        room = self.screen.room
        if room is None:
            return _not_done("there is no room on the board", "Build the room first.")
        priority = request.priority.strip().lower().replace(" ", "_") if request.priority else None
        if priority is not None and room.piece(priority) is None:
            priority = None
        brief = self.brief
        result: eng.Stretch = self._memo(
            ("stretch", room, brief.key(), priority),
            lambda: eng.stretch_budget(room, brief, priority),
        )
        if not result.swaps:
            return _not_done("no piece on the board has an on-sale look-alike", "Say so honestly.")
        self._move(room=result.room)
        for s in (*result.swaps, *((result.upgrade,) if result.upgrade else ())):
            pc = result.room.piece(s.slot)
            assert pc is not None
            self.seen.setdefault(s.slot, []).append(s.to_id)
            self.session.dispatch(
                SwapPiece(
                    slot=s.slot,
                    old_product_id=s.from_id,
                    piece=self._piece_out(pc),
                    total=result.room.total,
                )
            )
        self.session.dispatch(
            ShowSavings(
                swaps=[
                    SavingSwap(slot=s.slot, from_id=s.from_id, to_id=s.to_id, was=s.was, now=s.now)
                    for s in result.swaps
                ],
                saved=result.saved,
                moved_to=result.moved_to,
            )
        )
        landed("Here's where the savings are.", "The savings are on the board.")
        lines = [
            f"{s.slot}: {CATALOG.products[s.from_id].title} {money(s.was)} → {_line(CATALOG.products[s.to_id])}"
            for s in result.swaps
        ]
        upgrade = None
        if result.upgrade is not None:
            u = result.upgrade
            upgrade = f"{u.slot}: {CATALOG.products[u.from_id].title} {money(u.was)} → {_line(CATALOG.products[u.to_id], result.room.piece(u.slot).reason if result.room.piece(u.slot) else '')}"  # type: ignore[union-attr]
        return _prose(
            f"Savings are on the board: {money(result.saved)} saved on look-alikes. Room total now {money(result.room.total)}.",
            swaps=lines,
            saving_moved_to=upgrade,
        )

    @needs_result_now
    async def show(self, request: ShowRequest) -> str:
        """Open a product (optionally with an option value selected, or a section
        in focus), a page, or search results. A product returns its facts —
        answer from those."""
        target = request.product or request.page or ""
        if self.selection and (SELECTED.match(target.lower()) or target.lower() in _THIS):
            shown = self._show_selection()
            if shown is not None:
                return shown
        if request.product:
            p = self.resolve(request.product)
            if p is None:
                return _not_done(
                    f"I cannot tell which product '{request.product}' is", "Ask which one."
                )
            variant = p.variant_for(request.option) if request.option else None
            self._move(
                page=f"product/{p.id}", product=p.id, variant=variant.id if variant else None
            )
            self.session.dispatch(
                OpenProduct(
                    product_id=p.id, variant_id=variant.id if variant else None, focus=request.focus
                )
            )
            landed(f"Here's the {p.title}.", "Here it is.")
            return self._facts(p)
        if request.query:
            ids = self._search(request.query)
            self._move(page="search", listing=tuple(ids[:24]), listing_kind="results", product=None)
            self.session.dispatch(
                ShowProducts(
                    title=request.query, query=request.query, product_ids=ids[:48], count=len(ids)
                )
            )
            landed("Here's what we have.", "Here are the results.")
            return _prose(
                f"{len(ids)} results for '{request.query}' are on screen.",
                first=[_line(CATALOG.products[i]) for i in ids[:5]],
            )
        page = (request.page or "home").strip().strip("/")
        if not _valid_page(page):
            return _not_done(
                f"there is no page '{page}'",
                "Use home, room/<room>, category/<slug>, journal, cart, saved, policy/<topic>, gifts, orders or kiosk.",
            )
        self._move(page=page, product=None)
        self.session.dispatch(Navigate(page=page))
        landed("Here you go.", "Here it is.")
        return _prose(f"The {page} page is open.")

    def _show_selection(self) -> str | None:
        """The circled selection, shown: a room, category or article opens its
        page; several products open as a grid. ``None`` when it is one product,
        which the ordinary product path opens."""
        kinds = {k for k, _ in self.selection}
        if len(self.selection) == 1 and kinds != {"product"}:
            kind, ident = self.selection[0]
            page = {
                "room": f"room/{ident}",
                "category": f"category/{ident}",
                "article": f"journal/{ident}",
            }.get(kind)
            if page is None or not _valid_page(page):
                return _not_done(f"there is no page for the circled {kind}", "Say so.")
            self._move(page=page, product=None)
            self.session.dispatch(Navigate(page=page))
            landed("Here it is.", "Here you go.")
            return _prose(f"The {page} page is open.")
        ids = self.selected_products()
        if len(ids) >= 2 and kinds == {"product"}:
            self._move(page="search", listing=tuple(ids), listing_kind="results", product=None)
            self.layout = ()
            self.session.dispatch(
                ShowProducts(title="Your selection", query="", product_ids=ids, count=len(ids))
            )
            landed("Here they are.", "Your picks are up.")
            return _prose(
                "The circled products are on screen.",
                items=[_line(CATALOG.products[i]) for i in ids],
            )
        if kinds != {"product"}:
            return _not_done(
                "the circled selection mixes several kinds of thing",
                f"Say what is circled in one line ({self._selection_line()}) and ask which they mean.",
            )
        return None

    async def clear_selection(self) -> str:
        """Clear what the shopper circled, when they ask to."""
        self.selection = ()
        self.session.dispatch(ClearSelection())
        landed("Cleared.", "Done.")
        return _prose("The selection is cleared.")

    def _facts(self, p: Product) -> str:
        words = [f'{w} ("{p.sources.get(w, "")}")' for w in (*p.materials, *p.colours, *p.styles)]
        return _prose(
            f"{p.title} is open: {p.category}, {p.price_text()}.",
            options=f"{p.option_name}: {', '.join(p.option_values)}",
            intro=p.intro,
            highlights=list(p.highlights),
            described_as=words,
            not_known="sizes, stock and delivery dates — the product page and checkout show them",
        )

    def _search(self, query: str) -> list[str]:
        tokens = [t for t in re.findall(r"[a-z]+", query.lower()) if len(t) > 2]
        scores: dict[str, int] = {}
        for t in tokens:
            for key in (t, t.rstrip("s")):
                for pid in CATALOG.search.get(key, []):
                    scores[pid] = scores.get(pid, 0) + 1
                if key in CATALOG.search:
                    break
        return [
            pid
            for pid, _ in sorted(
                scores.items(), key=lambda kv: (-kv[1], CATALOG.products[kv[0]].price)
            )
        ]

    @needs_result_now
    async def shortlist(self, request: ShortlistRequest) -> str:
        """Save the piece they like (or drop one) on their saved picks: "I like
        this one", "I'll take the sandstone sofa". Returns the saved picks, the
        shopper's list and the next step to offer — offer it."""
        added, _ = self.expand(request.add)
        for pid in added:
            if pid not in self.shortlisted:
                self.shortlisted.append(pid)
        for r in request.remove:
            p = self.resolve(r)
            if p is not None and p.id in self.shortlisted:
                self.shortlisted.remove(p.id)
        if not added and not request.remove:
            return _not_done("I cannot tell which piece they mean", "Ask which one.")
        self.session.dispatch(UpdateShortlist(product_ids=list(self.shortlisted)))
        lead = self._lead()
        saved = CATALOG.products[added[-1]].title if added else None
        landed(
            f"I've saved the {saved} to your picks."
            + (" " + _lead_line(lead) if lead and _lead_line(lead) else "")
            if saved
            else "Your saved picks are updated."
        )
        return _prose(
            f"Saved picks now: {len(self.shortlisted)}.",
            items=[_line(CATALOG.products[i]) for i in self.shortlisted],
            their_list=self._wants_line() or None,
            next=(
                f"say in a short sentence that it is saved, then lead — {lead}"
                if lead
                else "say it is saved in a short sentence, then offer the next step: more pieces "
                "that go with it, or to see their picks together"
            ),
        )

    @needs_result_now
    async def show_saved(self) -> str:
        """Their saved picks together on one page, to see how they go together:
        "show me what I've selected", "show me all three", "let me see my picks".
        Never a comparison (pieces of different kinds do not compare) and not
        the cart."""
        ids = [i for i in self.shortlisted if i in CATALOG.products]
        if not ids:
            return _not_done(
                "nothing is saved yet", "Say so, and offer to save the piece they like."
            )
        note = _together(ids)
        self._move(page="saved", product=None, listing=tuple(ids), listing_kind="saved picks")
        self.layout = ()
        title = "Your picks"
        if self.brief.room and (recipe := RECIPES.get(self.brief.room)) is not None:
            title = f"Your picks for the {recipe.label.lower()}"
        self.session.dispatch(ShowSaved(product_ids=ids, title=title, note=note))
        total = sum(CATALOG.products[i].price for i in ids)
        landed(f"Here are your {len(ids)} picks together. {note}")
        return _prose(
            f"Their {len(ids)} saved picks are on screen together, {money(total)} in all.",
            items=[_line(CATALOG.products[i]) for i in ids],
            together=note,
            their_list=self._wants_line() or None,
            next=(
                "say how they go together in one sentence, from 'together', then offer to add "
                "them all to the cart" + (f" — or {self._lead()}" if self._lead() else "")
            ),
        )

    async def add_to_cart(self, request: AddToCartRequest) -> str:
        """Add the room on the board, or one product, to the cart — at once, no
        confirmation: the cart shows you added it, and it is one tap to undo."""
        lines: list[ConfirmLine]
        if request.what == "saved" or (request.what == "product" and len(request.products) > 1):
            refs = request.products if request.what == "product" else []
            ids, _ = self.expand(refs) if refs else (list(self.shortlisted), None)
            ids = [i for i in ids if i in CATALOG.products]
            if not ids:
                return _not_done(
                    "nothing is saved yet" if not refs else "I cannot tell which products",
                    "Ask which pieces to add.",
                )
            lines = []
            for i in ids:
                p = CATALOG.products[i]
                lines.append(ConfirmLine(product_id=i, variant_id=p.variant_for(None).id, qty=1))
            label = f"Add {len(lines)} pieces — " + ", ".join(
                CATALOG.products[x.product_id].title for x in lines
            )
        elif request.what == "room":
            room = self.screen.room
            if room is None:
                return _not_done(
                    "there is no room on the board", "Build the room first, or add one product."
                )
            lines = [
                ConfirmLine(product_id=pc.product_id, variant_id=pc.variant_id, qty=1)
                for pc in room.pieces
            ]
            label = f"Add {len(lines)} pieces — {money(room.total)}"
        else:
            p = self.resolve(request.product or "this")
            if p is None:
                return _not_done("I cannot tell which product to add", "Ask which one.")
            variant = p.variant_for(request.option or None)
            if not request.option and self.screen.product == p.id and self.screen.variant:
                variant = next((v for v in p.variants if v.id == self.screen.variant), variant)
            lines = [ConfirmLine(product_id=p.id, variant_id=variant.id, qty=1)]
            label = f"Add {p.title} ({variant.value}) — {money(variant.price)}"
        key = tuple((x.product_id, x.variant_id, x.qty) for x in lines)
        # Once per turn: a model that calls twice for one request would
        # otherwise put everything in twice. A later turn can add more.
        if self.added.get(key) == self.turns:
            _exact("That's in your cart.")
            return _prose(f"Already added this turn, not again: {label}.")
        self.added[key] = self.turns
        self._commit_cart(lines)
        names = [CATALOG.products[x.product_id].title for x in lines]
        said = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
        landed(
            f"I've added the {said} to your cart; it comes to {money(self._cart_total())}. "
            "Shall we check out, or keep looking?"
        )
        return _prose(
            f"Added to the cart, now on screen: {label}.",
            cart_now=[
                f"{line.title}, qty {line.qty} — {money(line.price)}" for line in self._cart_lines()
            ],
            cart_total=money(self._cart_total()),
            next="say exactly what was added, from this result, then offer checkout or more shopping",
        )

    def _commit_cart(self, lines: Sequence[ConfirmLine]) -> None:
        for line in lines:
            key = (line.product_id, line.variant_id)
            self.cart[key] = self.cart.get(key, 0) + line.qty
        self.session.dispatch(
            CartUpdated(
                lines=self._cart_lines(), total=self._cart_total(), saved=self._cart_saved()
            )
        )

    def _cart_lines(self) -> list[CartLine]:
        out: list[CartLine] = []
        for (pid, vid), qty in self.cart.items():
            p = CATALOG.products[pid]
            v = next((x for x in p.variants if x.id == vid), p.variants[0])
            out.append(
                CartLine(
                    product_id=pid,
                    variant_id=v.id,
                    qty=qty,
                    title=p.title,
                    price=v.price,
                    image=p.image,
                )
            )
        return out

    def _cart_total(self) -> float:
        return round(sum(line.price * line.qty for line in self._cart_lines()), 2)

    def _cart_saved(self) -> float:
        saved = 0.0
        for (pid, _), qty in self.cart.items():
            p = CATALOG.products[pid]
            if p.on_sale and p.compare_at:
                saved += (p.compare_at - p.price) * qty
        return round(saved, 2)

    @needs_result_now
    async def suggest_finish(self) -> str:
        """Once things are in the cart: one finishing touch that goes with them."""
        if not self.cart:
            return _not_done("the cart is empty", "Add something first.")
        in_cart = {pid for pid, _ in self.cart}
        anchors = sorted(in_cart, key=lambda i: -CATALOG.products[i].price)
        best: tuple[int, str, str, str] | None = None
        for a in anchors:
            for cat, items in CATALOG.goes_with.get(a, {}).items():
                if cat not in FINISHING:
                    continue
                for pid, score, reason in items:
                    if pid in in_cart:
                        continue
                    if best is None or score > best[0] or (score == best[0] and pid < best[1]):
                        best = (score, pid, reason, a)
        if best is None:
            return _not_done(
                "nothing finishing is paired with these pieces", "Skip the suggestion."
            )
        _, pid, code, anchor_id = best
        reason = eng._reason_text(code, CATALOG.products[anchor_id])  # pyright: ignore[reportPrivateUsage]
        self.session.dispatch(SuggestFinish(product_id=pid, reason=reason))
        landed("One finishing touch, if you like.", "Here's a finishing touch.")
        return _prose(
            "A finishing touch is suggested in the cart.",
            suggestion=_line(CATALOG.products[pid], reason),
            goes_with=CATALOG.products[anchor_id].title,
        )

    async def store_policy(self, request: PolicyRequest) -> str:
        """Open the returns, delivery, assembly or care policy, and answer from
        the policy in your instructions in the same reply."""
        self._move(page=policy_page(request.topic))
        self.session.dispatch(OpenPolicy(topic=request.topic))
        landed("The policy is on screen.", "Here's the policy.")
        return _prose(f"The {request.topic} policy is open.", policy=policy_text(request.topic))

    # ─── Returns desk ───────────────────────────────────────────────────

    @needs_result_now
    async def check_exchange(self, request: ExchangeRequest) -> str:
        """For an exchange: the other real option values of a product on the order."""
        order = self.order
        line = None
        if order is not None:
            ref = request.product.strip().lower()
            line = next(
                (x for x in order.lines if ref == x.product_id or ref in x.title.lower()),
                None,
            )
        product_id = line.product_id if line else request.product.strip()
        p = CATALOG.get(product_id)
        if p is None:
            return _not_done(
                f"I cannot tell which product '{request.product}' is",
                "Ask which line of the order.",
            )
        options = exchange_options(p.id, line.variant_id if line else None)
        if not options:
            return _not_done(
                f"{p.title} comes in no other {p.option_name.lower()}",
                "Offer a refund or store credit.",
            )
        return _prose(
            f"{p.title} also comes in: "
            + ", ".join(v for _, v in options)
            + f" ({p.option_name.lower()}).",
            variants=[f"{v} [variant {vid}]" for vid, v in options],
        )

    @needs_result_now
    async def resolve_product(self, request: ResolveRequest) -> str:
        """Which product the shopper means, from their words: what they point
        at, what is on screen (and where), the shortlist and room, then the
        catalog. One clear match is returned. Two to four close ones are
        numbered on screen: ask the ONE question the result gives, then pass
        their answer ("the second one", "the oak one") to this tool again."""
        res = self.reference(request.spoken, request.scope)
        match res.kind:
            case "one":
                assert res.product_id is not None
                if res.source == "choices":
                    self._clear_choices()
                p = CATALOG.products[res.product_id]
                return _prose(f"They mean {p.title}.", product=_line(p), found_on=res.source)
            case "choose":
                ids = list(res.candidates)
                on_screen = set(self.screen.listing) | set(self.screen.compare)
                if not set(ids) <= on_screen:
                    self._move(
                        listing=tuple(ids), listing_kind="results", page="search", product=None
                    )
                    self.layout = ()
                    self.session.dispatch(
                        ShowProducts(
                            title="Which one?",
                            query=request.spoken,
                            product_ids=ids,
                            count=len(ids),
                        )
                    )
                self.choices = tuple(ids)
                self.session.dispatch(ShowChoices(product_ids=ids, label=res.question))
                landed(res.question)
                return _prose(
                    "Close matches are numbered on screen. Ask exactly this, and nothing else:",
                    ask=res.question,
                    choices=[f"{n}. {_line(CATALOG.products[i])}" for n, i in enumerate(ids, 1)],
                )
            case "many":
                ids = list(res.candidates)
                return _prose(
                    f"They mean the {len(ids)} things they circled.",
                    products=[_line(CATALOG.products[i]) for i in ids],
                )
            case "none":
                return _not_done(
                    f"nothing on screen or in the catalog clearly matches '{request.spoken}'",
                    "Ask them to say a bit more — the kind of piece, its colour or material.",
                )

    @needs_result_now
    async def fill_checkout(self, fields: CheckoutFields) -> str:
        """Fill checkout fields from what the shopper just said; it says what
        is still needed. Nothing filled is read back aloud: the shopper checks
        it on screen (owner, 2026-11-03)."""
        if not self.cart:
            return _not_done("the cart is empty", "Add something to the cart first.")
        if not self.screen.page.startswith("checkout"):
            self._move(page="checkout", product=None)
            self.session.dispatch(Navigate(page="checkout"))
            self.checkout_step_now = self.checkout_step_now or "contact"
        refused: list[str] = []
        for name in FIELDS:
            raw = getattr(fields, name, None)
            if raw is None or not str(raw).strip():
                continue
            if name in PRIVATE:
                refused.append(f"{name}: the shopper types it on the page — never fill it")
                continue
            value, why = check(name, str(raw))
            if why is not None:
                refused.append(f"{name}: {why}")
                continue
            self.checkout[name] = value
            self.session.dispatch(CheckoutFill(field=name, value=value))
        missing = self._still_needed(REQUIRED)
        moved = self._advance_checkout()
        complete = self.checkout_step_now == "shipping" and not self._missing(STEPS["shipping"])
        if complete:
            landed(CHECK_ON_SCREEN)
        else:
            landed(f"That's in — on to {moved}." if moved else "That's in.", "Filled in.")
        return _prose(
            "The checkout fields are filled.",
            not_filled=refused,
            moved_on=f"the step was complete, so the checkout is now on {moved}" if moved else None,
            address_done=(
                f'say only: "{CHECK_ON_SCREEN}" Read none of it aloud. The shopper presses '
                "Review order; the page then tells you the checkout is on review."
                if complete
                else None
            ),
            still_needed=", ".join(missing) or None,
        )

    def _still_needed(self, among: Sequence[CheckoutField]) -> list[str]:
        """The required fields of ``among`` nobody has filled yet; email and
        phone are marked as the shopper's to type, so they are never asked aloud."""
        return [
            f"{f} (the shopper types it themselves: ask them to type it, never to say it)"
            if f in PRIVATE
            else f
            for f in self._missing(among)
        ]

    @needs_result_now
    async def checkout_step(self, request: CheckoutStepRequest) -> str:
        """Move the checkout to contact, shipping or review. Marked as a read
        because what to say next depends on it: on contact, that the shopper
        types their own email and phone — said in the same breath as the page
        opens, not a turn later."""
        if not self.cart:
            return _not_done("the cart is empty", "Add something to the cart first.")
        self.checkout_step_now = request.step
        self._move(page="checkout", product=None)
        self.session.dispatch(CheckoutStep(step=request.step))
        need = self._still_needed(STEPS[request.step])
        if request.step == "contact" and any(f in PRIVATE for f in self._missing(STEPS["contact"])):
            landed(
                "Here's checkout. Type your email and phone in yourself, and tell me when you're done."
            )
        else:
            landed("Here's that step.", "On to that step.")
        names = list(STEPS)
        earlier = [
            f for s in names[: names.index(request.step)] for f in self._still_needed(STEPS[s])
        ]
        return _prose(
            f"The checkout is on {request.step}.",
            still_needed=", ".join(need) or None,
            earlier_steps_still_need=", ".join(earlier) or None,
        )

    def _missing(self, among: Sequence[CheckoutField]) -> list[CheckoutField]:
        """The required fields of ``among`` nobody has filled yet."""
        return [
            f
            for f in among
            if f in REQUIRED and f not in self.checkout and f not in self.checkout_filled
        ]

    def _advance_checkout(self) -> CheckoutStepName | None:
        """After Emily fills fields: move on past a contact step that is now
        complete, as the page's own Continue would. Never on the shopper's
        typing alone — they may still be typing (the phone is optional) — and
        never past shipping: the address is read back and the shopper says it
        is right before the review (owner, 2026-11-03)."""
        names: list[CheckoutStepName] = list(STEPS)
        moved: CheckoutStepName | None = None
        while (
            self.cart
            and self.checkout_step_now == "contact"
            and not self._missing(STEPS[self.checkout_step_now])
        ):
            nxt = names[names.index(self.checkout_step_now) + 1]
            self.checkout_step_now = nxt
            self.session.dispatch(CheckoutStep(step=nxt))
            moved = nxt
        return moved

    def _order_total(self) -> float:
        subtotal = self._cart_total()
        return round(subtotal + delivery_fee(subtotal), 2)

    async def place_order(self, request: PlaceOrderRequest) -> str:
        """Place the order — only with the shopper's spoken yes. The first call
        puts the confirmation on Place order and you ask; when they say yes on
        their next turn, call again with confirmed_by_voice true."""
        if request.confirmed_by_voice:
            return self._confirmed_by_tool("place_order")
        if not self.cart:
            return _not_done("the cart is empty", "Add something to the cart first.")
        missing = self._still_needed(REQUIRED)
        if missing:
            return _not_done(
                f"checkout still needs {', '.join(missing)}",
                "Ask for the rest one at a time; email and phone they type themselves.",
            )
        total = self._order_total()
        label = f"Place order — {money(total)}"
        key = ("place_order", tuple(sorted(self.cart.items())), total)
        if (
            dup := self.confirms.ask("place_order", key, label, self.turns, total=total)
        ) is not None:
            _exact(dup)
            return _prose(f"Not asked again: {dup}")
        self.checkout_step_now = "review"
        self.session.dispatch(CheckoutStep(step="review"))
        self.session.dispatch(ConfirmPlaceOrder(total=total, label=label))
        landed(f"That's {money(total)} with delivery. Shall I place the order?")
        subtotal = self._cart_total()
        return _prose(
            f"The confirmation is on Place order: {money(total)}. Nothing is ordered until they say yes.",
            items=f"{money(subtotal)}",
            delivery="free" if delivery_fee(subtotal) == 0 else money(delivery_fee(subtotal)),
        )

    def _place(self, total: float, page_number: str | None = None) -> str:
        """Place the order. The number is the brain's own, unless the page
        already gave it one (a tap on its confirm prompt): then the page's,
        which is the number the shopper reads on the confirmation."""
        self.orders_placed += 1
        number = page_number or f"FH-{30000 + self.orders_placed}"
        self._remember_order(number, total)
        self.cart = {}
        self.checkout_step_now = None
        self._move(page="checkout/confirmation", product=None)
        self.session.dispatch(OrderPlaced(order_number=number, total=total))
        landed(f"Your order {number} is placed.", "The order is placed.")
        return number

    def _remember_order(self, number: str, total: float) -> None:
        """An order Emily placed, with its lines. It is packed now, as the
        orders page shows it (CONTRACT.md, v6): its day can move to the
        authored template slots, and it can be cancelled."""
        lines: list[dict[str, Any]] = []
        for line in self._cart_lines():
            p = CATALOG.products[line.product_id]
            value = next((v.value for v in p.variants if v.id == line.variant_id), "")
            lines.append(
                {
                    "product_id": line.product_id,
                    "variant_id": line.variant_id,
                    "title": line.title,
                    "variant": value,
                    "qty": line.qty,
                    "unit_price": line.price,
                }
            )
        name = " ".join(
            x for x in (self.checkout.get("first_name"), self.checkout.get("last_name")) if x
        )
        self.placed_orders.append(
            order_from(
                {
                    "number": number,
                    "name": name,
                    "status": "packed",
                    "placed_days_ago": 0,
                    "delivered_days_ago": None,
                    "total": total,
                    "lines": lines,
                },
                "placed",
            )
        )
        self.known_tracked[number] = tracked_from_known(number, lines, total, 0)

    async def submit_return(self, request: SubmitReturnRequest) -> str:
        """Submit the returns form — only with the shopper's yes. The first call
        asks; their plain yes on the next turn submits it for you."""
        if self.order is None:
            return _not_done("no return is open", "Find the order first.")
        if self.stage.moves.get("returns.submit") is None:
            return _not_done(
                "this page cannot submit the return by voice", "Ask them to press Submit return."
            )
        if request.confirmed_by_voice:
            return self._confirmed_by_tool("submit_return")
        key = ("submit_return", self.order.number)
        label = f"Submit the return for {self.order.number}"
        if (dup := self.confirms.ask("submit_return", key, label, self.turns)) is not None:
            _exact(dup)
            return _prose(f"Not asked again: {dup}")
        landed("Shall I submit the return?")
        return _prose("Ask for their yes before submitting. Nothing is submitted yet.")

    # ─── Front of house: gift edit, orders and returns, kiosk (CONTRACT v5, v6) ──

    def _send(self, move: str, args: dict[str, Any]) -> str:
        """A store move the tool decided on: sent now, answered by the page."""
        return self.stage.send(move, args, queue=False)

    # ─── The gift edit ──────────────────────────────────────────────────

    @needs_result_now
    async def gift_edit(self, request: GiftRequest) -> str:
        """Set the gift edit with what the shopper said — who it is for, the
        occasion, then the budget (or no budget) — and get the next question,
        or the short list with each pick's reason once all three are set."""
        rec, occ, chip = self.gift
        rec = request.recipient or rec
        occ = request.occasion or occ
        if request.no_budget:
            chip = 0
        elif request.budget is not None:
            chip = budget_chip(request.budget)
        args: dict[str, Any] = {}
        if request.recipient:
            args["recipient"] = request.recipient
        if request.occasion:
            args["occasion"] = request.occasion
        if request.no_budget or request.budget is not None:
            args["budget"] = chip
        if args:
            self._send("gifts.set", args)
        self.gift = (rec, occ, chip)
        if not self.screen.page.startswith("gifts"):
            self._move(page="gifts", product=None)
        if rec is None or occ is None:
            landed("Who is it for, and what's the occasion?")
            return _prose(
                "The gift edit is waiting for who it is for and the occasion.",
                ask_next="Who is it for, and what's the occasion?",
            )
        if chip is None:
            landed(GIFT_BUDGET_QUESTION)
            return _prose(
                f"The gift edit is set to {rec}, {occ}; the budget is not set yet.",
                ask_next=f'ask exactly: "{GIFT_BUDGET_QUESTION}"',
            )
        picks: list[dict[str, str]] = stored_edits()["gifts"].get(gift_key(rec, occ, chip), [])
        ids = tuple(x["product_id"] for x in picks if x["product_id"] in CATALOG.products)
        self._move(page="gifts", product=None, listing=ids, listing_kind="gift edit")
        if not ids:
            return _not_done(
                "nothing in the store fits that budget for that gift", "Offer the next budget up."
            )
        landed("Here's a short list for them. Which one would you like?")
        nearest = (
            f"the budget chip at or under {money(request.budget)} is {money(chip)}"
            if request.budget is not None and chip and abs(chip - request.budget) > 0.005
            else None
        )
        return _prose(
            f"The gift edit is on screen: {len(ids)} picks"
            + (f" up to {money(chip)}" if chip else " with no budget limit")
            + ", in screen order.",
            budget=nearest,
            picks=[
                _line(CATALOG.products[x["product_id"]], x["reason"])
                for x in picks
                if x["product_id"] in CATALOG.products
            ],
            next="name two picks with their reasons; offer to add one to the cart",
        )

    # ─── Your orders: status, delivery day, cancel, earlier, return (v6) ──

    def _tracked(self, text: str) -> Tracked | None:
        return find_tracked(text, self.known_tracked)

    def _all_tracked(self) -> list[Tracked]:
        return [*self.known_tracked.values(), *TRACKED.values()]

    def _slot_now(self, t: Tracked) -> Slot | None:
        chosen = self.delivery.get(t.number)
        return next((x for x in t.slots if x.id == chosen), None) or t.slot

    def _status(self, t: Tracked) -> str:
        """Where it is and what its status allows, in plain words."""
        t = replace(t, slot=self._slot_now(t))
        match group_of(t, t.number in self.cancelled):
            case "cancelled":
                return "It was cancelled; nothing will be delivered."
            case "packed":
                return plain_status(t)
            case "on_the_way":
                asked = (
                    " An earlier delivery has been asked for." if t.number in self.earlier else ""
                )
                return plain_status(t) + asked
            case "delivered":
                order = self.lookup_order(t.number)
                line = order.lines[0] if order and order.lines else None
                if line and line.status == "outside_window":
                    return (
                        plain_status(t) + f" That is outside the {WINDOW_DAYS}-day return window."
                    )
                left = f" It can be returned for {line.days_left} more days." if line else ""
                return plain_status(t) + left

    def _can(self, t: Tracked) -> str:
        """What the shopper can do with it now (the store's policy)."""
        match group_of(t, t.number in self.cancelled):
            case "cancelled":
                return "nothing: it is cancelled"
            case "packed":
                return "change the delivery day (change_delivery) or cancel it (cancel_order)"
            case "on_the_way":
                return (
                    "ask for an earlier delivery (request_earlier — a request to the driver, not "
                    "a promise); it can no longer be cancelled or moved to another day"
                )
            case "delivered":
                order = self.lookup_order(t.number)
                if order and order.eligible:
                    return "start a return (start_return); it cannot be cancelled"
                return "nothing: it is outside the return window; point to the care guide and contact page"

    def _open_order(self, t: Tracked) -> None:
        self._send("orders.open", {"order_number": t.number})
        self._move(page=f"orders?order={t.number}", product=None)

    @needs_result_now
    async def track_order(self, order_number: str | None = None) -> str:
        """The account's orders, or one order: where it is in plain words and
        what its status lets them do. Without a number: every order, one line
        each, on the orders page."""
        if not order_number:
            if not self.screen.page.startswith("orders"):
                self.session.dispatch(Navigate(page="orders"))
            self._move(page="orders", product=None)
            landed("Here are your orders. Which one would you like to look at?")
            return _prose(
                "The orders page is open with every order on the account.",
                orders=[
                    f"{t.number}: {', '.join(t.lines)} — {self._status(t)}"
                    for t in self._all_tracked()
                ],
                next="ask which order they mean, naming what is in it, not the number",
            )
        t = self._tracked(order_number)
        if t is None:
            return _not_done(
                f"{order_number} is not an order on this account",
                "The orders are "
                + ", ".join(x.number for x in self._all_tracked())
                + "; ask which one, by what is in it.",
            )
        self._open_order(t)
        t = replace(t, slot=self._slot_now(t))
        landed(self._status(t))
        timeline = [
            f"{day_words(-int(e['days_ago']))} {e.get('time', '')}: {e['text']}" for e in t.events
        ]
        return _prose(
            f"{t.number} ({', '.join(t.lines)}) is open on screen. {self._status(t)}",
            timeline=timeline,
            they_can=self._can(t),
            next="say where it is in one or two plain sentences, then what they can do now",
        )

    @needs_result_now
    async def change_delivery(self, order_number: str, slot: str | None = None) -> str:
        """Change a packed order's delivery day. Without a slot: open the day
        picker on screen and get the days it can move to ("what are my
        options?"). With a slot (the id or the day and window they chose): pick
        it and save it."""
        t = self._tracked(order_number)
        if t is None:
            return _not_done(
                f"there is no order {order_number!r} on this account", "Ask which order."
            )
        if t.number in self.cancelled:
            return _not_done(f"{t.number} is cancelled", "Say so.")
        if not t.can_reschedule:
            return _not_done(f"{t.number} cannot move: {t.why_not}", "Say why, in plain words.")
        booked = self._slot_now(t)
        offered = [x for x in t.slots if x.id != (booked.id if booked else "")]
        if not slot:
            self._send("orders.show_slots", {"order_number": t.number})
            self._move(page=f"orders?order={t.number}", product=None)
            landed(
                "Here are the days it can move to: "
                + "; ".join(x.words() for x in offered)
                + ". Which suits you?"
            )
            return _prose(
                f"The delivery-day picker of {t.number} is open on screen.",
                booked=booked.words() if booked else None,
                can_move_to=[f"{x.words()} [slot {x.id}]" for x in offered],
                next="read the days in one sentence and ask which suits them",
            )
        chosen = _slot_said(t.slots, slot)
        if chosen is None:
            return _not_done(
                f"'{slot}' is not a day {t.number} offers",
                "Offer these: " + "; ".join(f"{x.words()} [slot {x.id}]" for x in offered),
            )
        self.delivery[t.number] = chosen.id
        self._send("orders.reschedule", {"order_number": t.number, "slot": chosen.id})
        self._move(page=f"orders?order={t.number}", product=None)
        landed(f"Done — it's moved to {chosen.words()}.")
        return _prose(
            f"The delivery of {t.number} is being moved to {chosen.words()} on screen.",
            next="confirm the new day and time window in one sentence",
        )

    @needs_result_now
    async def cancel_order(self, order_number: str, confirmed_by_voice: bool = False) -> str:
        """Cancel a packed order — only with the shopper's yes. The first call
        asks; their plain yes on the next turn cancels it for you. An order on
        its way or delivered cannot be cancelled."""
        t = self._tracked(order_number)
        if t is None:
            return _not_done(
                f"there is no order {order_number!r} on this account", "Ask which order."
            )
        g = group_of(t, t.number in self.cancelled)
        if g == "cancelled":
            line = f"That's already done — order {t.number} is cancelled."
            _exact(line)
            return _prose(f"Already done, not sent again. {line}")
        if g != "packed":
            why = (
                "it is already on its way, and an order can only be cancelled while it is packed; "
                "they can ask for an earlier delivery, or return it once it arrives"
                if g == "on_the_way"
                else "it has been delivered; it can be returned instead"
            )
            return _not_done(f"{t.number} cannot be cancelled: {why}", "Say so, in plain words.")
        if confirmed_by_voice:
            return self._confirmed_by_tool("cancel_order")
        self._open_order(t)
        key = ("cancel_order", t.number)
        label = f"Cancel order {t.number}"
        if (
            dup := self.confirms.ask("cancel_order", key, label, self.turns, number=t.number)
        ) is not None:
            _exact(dup)
            return _prose(f"Not asked again: {dup}")
        question = f"Shall I cancel order {t.number}, the {', '.join(t.lines)}?"
        landed(question)
        return _prose(
            f"{t.number} is packed, so it can still be cancelled. Nothing is cancelled yet.",
            ask=f'ask exactly: "{question}" and wait for their yes',
        )

    def _act_cancel(self, pending: Pending) -> Acted:
        number = str(pending.data["number"])
        ref = self._send("orders.cancel", {"order_number": number})
        self.cancelled.add(number)
        return Acted(
            "Cancelling it now.",
            f"[Order {number} is being cancelled on screen; you say the page's answer when it "
            "comes. Do not call cancel_order again.]",
            ref=ref,
            on_applied=lambda _detail: (
                f"Done — order {number} is cancelled, and nothing will be delivered."
            ),
        )

    @needs_result_now
    async def request_earlier(self, order_number: str) -> str:
        """Ask the driver to bring an order that is on its way earlier — a
        request passed on, never a promise."""
        t = self._tracked(order_number)
        if t is None:
            return _not_done(
                f"there is no order {order_number!r} on this account", "Ask which order."
            )
        if group_of(t, t.number in self.cancelled) != "on_the_way":
            return _not_done(
                f"{t.number} is not on its way",
                "An earlier delivery can be asked for only once it has left the warehouse; "
                "a packed order can move to another offered day instead.",
            )
        self.earlier.add(t.number)
        self._send("orders.request_earlier", {"order_number": t.number})
        self._move(page=f"orders?order={t.number}", product=None)
        landed(
            "I've asked the driver to bring it earlier if they can. It's a request, not a "
            "promise, and you'll hear if they can."
        )
        return _prose(
            f"An earlier delivery of {t.number} is requested on screen.",
            next="say it is a request passed to the driver, not a promise, in one sentence",
        )

    # ─── A return, from a delivered order ───────────────────────────────

    @needs_result_now
    async def start_return(self, order_number: str) -> str:
        """Start a return for a delivered order: its return form opens on the
        items, nothing chosen. Returns the items and the first question."""
        t = self._tracked(order_number)
        order = self.lookup_order(order_number)
        if t is None or order is None:
            return _not_done(
                f"there is no order {order_number!r} on this account", "Ask which order."
            )
        g = group_of(t, t.number in self.cancelled)
        if g != "delivered":
            why = {
                "packed": "it has not left the warehouse yet; a packed order can be cancelled or moved to another day instead",
                "on_the_way": "it is still on its way; a return can start once it arrives",
                "cancelled": "it was cancelled",
            }[g]
            return _not_done(f"{t.number} cannot be returned: {why}", "Say so, in plain words.")
        if not order.eligible:
            line = order.lines[0]
            return _not_done(
                f"{t.number} was delivered {line.days_since_delivery} days ago, outside the "
                f"{WINDOW_DAYS}-day return window",
                "Say so honestly; never promise an exception. Point to the care guide and the "
                "contact page.",
            )
        self.order = order
        self.form = {}
        self.form_items = {}
        self.form_step = 1
        self.form_pending = None
        self.form_later = {}
        self._send("orders.start_return", {"order_number": order.number})
        self._move(page=f"orders/return?order={order.number}", product=None)
        q = self._return_question()
        landed(f"The return form for {order.number} is open. {q}")
        return _prose(
            f"The return form for {order.number} is open on its first step, items; nothing is chosen.",
            items=[
                f"{line.title} ({line.variant}), {line.qty} ordered [id {line.product_id}]"
                for line in order.lines
            ],
            days_left=f"{order.lines[0].days_left} days left in the {WINDOW_DAYS}-day window",
            ask_next=q,
        )

    def _line_for(self, ref: str) -> Any:
        """An order line from the shopper's words: its id, or words of its title."""
        if self.order is None:
            return None
        r = ref.strip().lower()
        for line in self.order.lines:
            if r == line.product_id:
                return line
        words = [w for w in re.findall(r"[a-z]+", r) if len(w) > 2 and w not in _FILLER]
        scored = [
            (sum(w.rstrip("s") in line.title.lower() for w in words), line)
            for line in self.order.lines
        ]
        best = max(scored, key=lambda x: x[0], default=(0, None))
        tied = [x for x in scored if x[0] == best[0]]
        return best[1] if best[0] and len(tied) == 1 else None

    def _form_gap(self) -> tuple[int, str] | None:
        """The first step and field the return still needs, or ``None``."""
        if self.order is None:
            return None
        if self.form_pending or not any(q > 0 for q in self.form_items.values()):
            return 1, "items"
        f = self.form
        for step, name in ((2, "reason"), (2, "condition"), (3, "resolution")):
            if not f.get(name):
                return step, name
        if f["resolution"] == "exchange":
            for pid, q in self.form_items.items():
                if q and not f.get(f"exchange_variant_{pid}") and exchange_options(pid):
                    return 3, f"exchange_variant_{pid}"
        if not f.get("collection"):
            return 4, "collection"
        if f["collection"] == "pickup" and not f.get("pickup_window"):
            return 4, "pickup_window"
        return None

    def _return_question(self) -> str:
        gap = self._form_gap()
        if gap is None:
            return "Everything is filled in. Shall I submit the return?"
        _, name = gap
        if name == "items":
            if self.form_pending and self.order is not None:
                line = next(x for x in self.order.lines if x.product_id == self.form_pending)
                return f"How many of the {line.qty} {line.title} are going back?"
            assert self.order is not None
            names = [x.title for x in self.order.lines]
            return (
                f"Is it the {names[0]} you're returning?"
                if len(names) == 1
                else "Which items are going back: the "
                + ", the ".join(names[:-1])
                + f" or the {names[-1]}?"
            )
        if name.startswith("exchange_variant_"):
            pid = name.removeprefix("exchange_variant_")
            options = [v for _, v in exchange_options(pid)]
            return f"Which would you like instead: {', '.join(options)}?"
        return _FORM_QUESTIONS[name]

    def _flush_form(self) -> list[str]:
        """Put down the answers held for later whose step the form has reached."""
        done: list[str] = []
        moved = True
        while moved:
            moved = False
            gap = self._form_gap()
            reach = 5 if gap is None else gap[0]
            for name in [n for n in _FIELD_STEP if n in self.form_later]:
                if _FIELD_STEP[name] > reach:
                    continue
                value = self.form_later.pop(name)
                self._send("returns.fill", {"field": name, "value": value})
                self.form_step = _FIELD_STEP[name]  # the move opens its own step
                self.form[name] = value
                if name == "collection":
                    self.return_collection = value
                    if value != "pickup":
                        self.form.pop("pickup_window", None)
                done.append(f"{name.replace('_', ' ')}: {_CHOICE_LABELS[value]}")
                moved = True
        return done

    def _form_after(self) -> None:
        """Move the form on to the step that needs something next, as Continue
        does, and ask for the yes once it is complete."""
        gap = self._form_gap()
        target = 5 if gap is None else gap[0]
        while self.form_step < target:
            self._send("returns.next_step", {})
            self.form_step += 1
        if gap is None and self.order is not None:
            self.confirms.ask(
                "submit_return",
                ("submit_return", self.order.number),
                f"Submit the return for {self.order.number}",
                self.turns,
            )

    @needs_result_now
    async def fill_return(self, answers: ReturnAnswers) -> str:
        """Put on the return form what the shopper just said — the items (and
        how many), the reason, the condition, refund / exchange / store credit,
        pickup (with a time of day) or drop-off — as soon as they say it, one
        answer at a time. Returns what is set and the ONE next question; the
        form moves on by itself. Never fill what they have not said."""
        if self.order is None:
            return _not_done("no return is open", "Start it with start_return for their order.")
        if self.stage.moves.get("returns.fill") is None:
            return _not_done(
                "this page cannot fill the return form by voice", "Ask them to tap their answers."
            )
        order = self.order
        done: list[str] = []
        problems: list[str] = []
        for item in answers.items:
            line = self._line_for(item.product)
            if line is None:
                problems.append(
                    f"'{item.product}' is not clearly one item of {order.number} "
                    f"(items: {', '.join(x.title for x in order.lines)})"
                )
                continue
            qty = item.qty if item.qty is not None else (1 if line.qty == 1 else None)
            if qty is None:
                self.form_pending = line.product_id
                continue
            if not 0 <= qty <= line.qty:
                problems.append(f"{line.title}: between 1 and {line.qty} can go back")
                continue
            self._send("returns.select_item", {"product_id": line.product_id, "qty": qty})
            self.form_step = _FIELD_STEP["items"]  # the move opens its own step
            self.form_items[line.product_id] = qty
            if self.form_pending == line.product_id:
                self.form_pending = None
            done.append(
                _how_many(qty, line.qty, line.title) if qty else f"the {line.title} taken off"
            )
        given = {
            "reason": answers.reason,
            "condition": answers.condition,
            "resolution": answers.resolution,
            "collection": answers.collection,
            "pickup_window": answers.pickup_window,
        }
        for name, value in given.items():
            if value is None:
                continue
            if (
                name == "pickup_window"
                and (answers.collection or self.form.get("collection")) != "pickup"
            ):
                problems.append("a time of day is only for a pickup")
                continue
            # An answer for a later step waits until the steps before it are
            # complete: the page refuses a field whose earlier step is not.
            self.form_later[name] = value
        done += self._flush_form()
        if answers.exchange_option:
            chosen = [pid for pid, q in self.form_items.items() if q]
            if self.form.get("resolution") != "exchange" or len(chosen) != 1:
                problems.append("an exchange option needs the exchange resolution and one item")
            else:
                pid = chosen[0]
                options = {v.lower(): v for _, v in exchange_options(pid)}
                pick = options.get(answers.exchange_option.strip().lower())
                if pick is None:
                    problems.append(
                        f"it comes in {', '.join(options.values()) or 'no other option'}"
                    )
                else:
                    self._send("returns.fill", {"field": f"exchange_variant_{pid}", "value": pick})
                    self.form_step = _FIELD_STEP["resolution"]
                    self.form[f"exchange_variant_{pid}"] = pick
                    done.append(f"exchange to {pick}")
        self._form_after()
        q = self._return_question()
        if done:
            landed(f"I've put down {', '.join(done)}. {q}")
        return _prose(
            ("On the form now: " + "; ".join(done) + ".") if done else "Nothing new is set.",
            not_set=problems,
            noted_for_later=[
                f"{n.replace('_', ' ')}: {_CHOICE_LABELS[v]} (goes on once the earlier steps are done)"
                for n, v in self.form_later.items()
            ],
            ask_next=q,
            next=(
                "say what you put down in a few words, then ask exactly the next question"
                if self._form_gap() is not None
                else 'say it is all filled in, then ask "Shall I submit the return?" and wait'
            ),
        )

    @needs_result_now
    async def kiosk_answer(self, request: KioskRequest) -> str:
        """Choose the kiosk's tiles for what the shopper said; with all three
        answers, get the three picks and their reasons."""
        if self.kiosk_screen == "attract":
            self._send("kiosk.start", {})
            self.kiosk_screen = "room"
        for qid in ("room", "feel", "budget"):
            value = getattr(request, qid)
            if value is not None and self.kiosk.get(qid) != value:
                self.kiosk[qid] = value
                self._send("kiosk.answer", {"question": qid, "value": value})
        self._move(page="kiosk", product=None)
        landed("That's on the screen.", "The kiosk has it.")
        return self._kiosk_result()

    def _kiosk_result(self) -> str:
        k = self.kiosk
        missing = [q for q in ("room", "feel", "budget") if q not in k]
        if missing:
            q = next(x for x in KIOSK["questions"] if x["id"] == missing[0])
            return _prose(
                "The kiosk is on its next question.",
                ask_next=f"{q['label']} ({', '.join(o['label'] for o in q['options'])})",
                next="ask it in one short sentence",
            )
        picks: list[dict[str, str]] = stored_edits()["kiosk"].get(
            kiosk_key(k["room"], k["feel"], k["budget"]), []
        )
        ids = tuple(x["product_id"] for x in picks if x["product_id"] in CATALOG.products)
        self.kiosk_screen = "picks"
        self._move(listing=ids, listing_kind="kiosk picks")
        return _prose(
            "The three picks are on the kiosk, with a QR code that takes them to the shopper's phone.",
            picks=[_line(CATALOG.products[x["product_id"]], x["reason"]) for x in picks],
            next="name each pick in a few words with its reason, then mention the QR code; short",
        )

    async def kiosk_restart(self) -> str:
        """Clear the kiosk and go back to its welcome screen."""
        self.kiosk = {}
        self.kiosk_screen = "attract"
        self._send("kiosk.restart", {})
        landed("Starting over.")
        return _prose("The kiosk is back on its welcome screen.")

    def _fold_store_event(self, event: StageEvent) -> str | None:
        """A store page's Stage event (CONTRACT v5, v6), folded into the mirror;
        the line the model reads when the shopper did it by hand."""
        d = event.data
        by_hand = event.by == "visitor"
        match event.name:
            case "gifts.changed":
                rec = str(d.get("recipient") or "") or None
                occ = str(d.get("occasion") or "") or None
                raw = d.get("budget")
                budget = None if raw is None or raw == "" else int(raw)
                self.gift = (rec, occ, budget)
                if not (rec and occ) or budget is None:
                    missing = (
                        "who it is for and the occasion" if not (rec and occ) else "the budget"
                    )
                    return (
                        f"[The shopper set the gift edit to {rec or '—'}, {occ or '—'}; "
                        f"still to choose: {missing}.]"
                    )
                picks = stored_edits()["gifts"].get(gift_key(rec, occ, budget), [])
                ids = tuple(x["product_id"] for x in picks if x["product_id"] in CATALOG.products)
                self.screen = replace(self.screen, listing=ids, listing_kind="gift edit")
                names = "; ".join(f"{n}. {CATALOG.products[i].title}" for n, i in enumerate(ids, 1))
                cap = f"up to {money(budget)}" if budget else "with no budget limit"
                return (
                    f"[The shopper set the gift edit to {rec}, {occ}, {cap}. On screen: {names}.]"
                )
            case "orders.opened":
                number = str(d.get("order_number") or "")
                t = self._tracked(number)
                if t is None:
                    return None
                self.screen = replace(self.screen, page=f"orders?order={t.number}")
                return f"[The shopper opened order {t.number}: {self._status(t)} They can {self._can(t)}.]"
            case "orders.delivery_changed":
                number, slot = str(d.get("order_number") or ""), str(d.get("slot") or "")
                t = self._tracked(number)
                chosen = next((x for x in t.slots if x.id == slot), None) if t else None
                if chosen is None:
                    return None
                self.delivery[number] = slot
                return f"[The shopper moved the delivery of {number} to {chosen.words()}.]"
            case "orders.cancelled":
                number = str(d.get("order_number") or "")
                self.cancelled.add(number)
                return f"[The shopper cancelled order {number} on screen.]"
            case "orders.earlier_requested":
                number = str(d.get("order_number") or "")
                self.earlier.add(number)
                return f"[The shopper asked for an earlier delivery of {number} on screen.]"
            case "orders.return_started":
                number = str(d.get("order_number") or "")
                order = self.lookup_order(number)
                if order is None or (
                    self.order is not None and self.order.number == number and not by_hand
                ):
                    return None
                self.order = order
                self.form, self.form_items, self.form_step, self.form_pending = {}, {}, 1, None
                self.form_later = {}
                return (
                    f"[The shopper opened the return form for {number}. "
                    f"Ask: {self._return_question()}]"
                )
            case "returns.field_filled":
                field, value = str(d.get("field") or ""), str(d.get("value") or "")
                if self.order is None or (
                    d.get("order_number") and d.get("order_number") != self.order.number
                ):
                    return None
                if field.startswith("qty_"):
                    pid = field.removeprefix("qty_")
                    qty = int(value) if value.isdigit() else 0
                    self.form_items[pid] = qty
                    if self.form_pending == pid and qty:
                        self.form_pending = None
                    line = next((x for x in self.order.lines if x.product_id == pid), None)
                    what = (
                        f"ticked {_how_many(qty, line.qty, line.title)}"
                        if qty and line
                        else f"took {pid} off the return"
                    )
                elif value:
                    self.form[field] = value
                    if field == "collection":
                        self.return_collection = value
                    what = f"set {field.replace('_', ' ')} to {_CHOICE_LABELS.get(value, value)}"
                else:
                    self.form.pop(field, None)
                    what = f"cleared {field.replace('_', ' ')}"
                if not by_hand:
                    return None
                held = self._flush_form()
                self._form_after()
                then = f" Answers they gave earlier went on: {'; '.join(held)}." if held else ""
                return (
                    f"[On the return form the shopper {what} by hand.{then} "
                    f"Next: {self._return_question()}]"
                )
            case "returns.step_reached":
                step = d.get("step")
                if isinstance(step, int | float):
                    self.form_step = int(step)
                return None
            case "kiosk.screen":
                self.kiosk_screen = str(d.get("screen") or self.kiosk_screen)
                if self.kiosk_screen == "attract":
                    self.kiosk = {}
                return None
            case "kiosk.answered":
                qid, value = str(d.get("question") or ""), str(d.get("value") or "")
                if qid not in ("room", "feel", "budget"):
                    return None
                self.kiosk[qid] = value
                if len(self.kiosk) == 3:
                    return f"[The shopper chose {value} for {qid} on the kiosk. {self._kiosk_result()}]"
                return f"[The shopper chose {value} for {qid} on the kiosk.]"
            case _:
                return None

    # ─── Browser → brain ────────────────────────────────────────────────

    def apply_event(self, event: FernhollowEvent) -> str | None:
        """Fold what the shopper did into the mirror; return the line the model
        reads next, or ``None`` for an event naming nothing real."""
        match event:
            case PageViewed():
                path = event.path.strip("/") or "home"
                product = path.removeprefix("product/") if path.startswith("product/") else None
                if product is not None and product not in CATALOG.products:
                    product = None
                self.screen = replace(self.screen, page=path, product=product, variant=None)
                self.choices = ()
                job = job_for(path)
                if job is not None and job != self.job:
                    self.job = job
                    return f"[The shopper opened the {path} page. Your job is now: {job}.]"
                return f"[The shopper opened the {path} page.]"
            case ProductViewed():
                p = CATALOG.get(event.product_id)
                if p is None:
                    return None
                self.screen = replace(
                    self.screen, page=f"product/{p.id}", product=p.id, variant=event.variant_id
                )
                return f"[The shopper opened {p.title} [id {p.id}].]"
            case VisibleProducts():
                ids = tuple(i for i in event.product_ids if i in CATALOG.products)
                self.layout = tuple(
                    Layout(x.product_id, x.row, x.col)
                    for x in event.layout
                    if x.product_id in CATALOG.products
                )
                if self.layout and not ids:
                    ids = tuple(
                        x.product_id for x in sorted(self.layout, key=lambda x: (x.row, x.col))
                    )
                self.screen = replace(self.screen, listing=ids, listing_kind="grid")
                return None if not ids else f"[The shopper's screen now lists {len(ids)} products.]"
            case VariantSelected():
                p = CATALOG.get(event.product_id)
                v = next((x for x in p.variants if x.id == event.variant_id), None) if p else None
                if p is None or v is None:
                    return None
                self.screen = replace(self.screen, product=p.id, variant=v.id)
                return f"[The shopper picked {v.value} for {p.title}.]"
            case FilterChanged():
                f = event.filters
                filters = eng.Filters(
                    room=f.room,
                    category=f.category,
                    materials=tuple(f.materials),
                    colours=tuple(f.colours),
                    styles=tuple(f.styles),
                    price_min=f.price_min,
                    price_max=f.price_max,
                    on_sale=f.on_sale,
                )
                ids = filters.results()
                self.screen = replace(
                    self.screen, filters=filters, listing=tuple(ids[:24]), listing_kind="grid"
                )
                return f"[The shopper changed the filters; {len(ids)} products show.]"
            case RoomBoardEdited():
                room = self.screen.room
                if room is None or room.piece(event.slot) is None:
                    return None
                if event.action == "remove":
                    room = replace(
                        room, pieces=tuple(pc for pc in room.pieces if pc.slot != event.slot)
                    )
                    self.screen = replace(self.screen, room=room)
                return f"[The shopper chose '{event.action}' on the {event.slot} tile.]"
            case CartChanged():
                cart: dict[tuple[str, str], int] = {}
                for line in event.lines:
                    p = CATALOG.get(line.product_id)
                    if p is None or line.qty <= 0:
                        continue
                    v = p.variant_for(None)
                    if line.variant_id:
                        v = next((x for x in p.variants if x.id == line.variant_id), v)
                    cart[(p.id, v.id)] = line.qty
                self.cart = cart
                return f"[The shopper changed the cart: {sum(cart.values())} items, {money(self._cart_total())}.]"
            case ConfirmResult():
                pending = self.confirms.pending
                if pending is None:
                    return None
                if not event.confirmed:
                    self.confirms.clear()
                    return f"[The shopper declined: {pending.label}. Nothing was done.]"
                if event.order_number:
                    # The page's number is the one the shopper reads back.
                    pending.data["order_number"] = event.order_number
                acted = self.confirms.act(pending)
                self._say_line_soon(acted.line)
                return f"[The shopper tapped yes. {acted.note}]"
            case ShortlistChanged():
                self.shortlisted = [i for i in event.product_ids if i in CATALOG.products]
                return f"[The shopper's shortlist now holds {len(self.shortlisted)}.]"
            case Pointing():
                if event.product_id in CATALOG.products:
                    self.pointing = (event.product_id, time.monotonic())
                return None  # silent: kept for "this one", never spoken about
            case OrdersKnown():
                self.known_orders = [
                    order_from(
                        {**o.model_dump(), "status": "packed", "delivered_days_ago": None}, "known"
                    )
                    for o in event.orders
                    if o.number
                ]
                self._adopt_page_numbers()
                self.known_tracked = {
                    o.number: tracked_from_known(
                        o.number, [x.model_dump() for x in o.lines], o.total, o.placed_days_ago
                    )
                    for o in event.orders
                    if o.number
                }
                return None  # silent: kept for the orders page
            case Selection():
                things = tuple(
                    (t.kind, t.id)
                    for t in event.things
                    if (t.kind == "product" and t.id in CATALOG.products)
                    or (t.kind == "room" and t.id in CATALOG.rooms)
                    or (t.kind == "category" and t.id in CATALOG.categories)
                    or (t.kind == "article" and t.id in _JOURNAL)
                )[:8]
                self.selection = things
                if not things:
                    return None
                return (
                    f"[The shopper circled {len(things)} thing{'s' if len(things) > 1 else ''} on screen: "
                    f"{self._selection_line()}. Wait for what they say about them; do nothing yet.]"
                )
            case SelectionCleared():
                had = bool(self.selection)
                self.selection = ()
                return "[The shopper cleared what they circled.]" if had else None
            case ChoiceMade():
                p = CATALOG.get(event.product_id)
                if p is None:
                    return None
                self.choices = ()
                return f"[The shopper picked {p.title} [id {p.id}] from the numbered choices.]"
            case CheckoutChanged():
                if not event.field:
                    return None
                if not event.complete:
                    # Half an email, or a field cleared: not filled.
                    self.checkout_filled.discard(event.field)
                    return None
                self.checkout_filled.add(event.field)
                step = self.checkout_step_now
                left = self._still_needed(STEPS[step]) if step in STEPS else []
                if step == "contact" and not left:
                    return (
                        f"[The shopper filled {event.field} at checkout. The contact step is "
                        "complete: when they say they are done, move on with checkout_step.]"
                    )
                if step == "shipping" and not left:
                    return (
                        f"[The shopper filled {event.field} at checkout. The address is complete: "
                        f'say only "{CHECK_ON_SCREEN}" — read none of it aloud.]'
                    )
                return f"[The shopper filled {event.field} at checkout.]"
            case CheckoutStepReached():
                self.checkout_step_now = event.step
                return f"[The checkout is on {event.step}.]"


#: How long after Emily says an outcome a page "speak" reaction is the same news.
_OUTCOME_GAP_S = 15.0


#: "Yes, cancel it", "please cancel the order": a yes to the cancel question,
#: though "cancel" alone reads as a no to any other.
_CANCEL_YES = re.compile(
    r"^\s*(yes,?\s*)?(please\s+)?(go ahead and\s+)?cancel (it|that|the order|my order)\b(?!.*\b(don't|not|wait)\b)",
    re.IGNORECASE,
)

GIFT_BUDGET_QUESTION = "Do you have a budget in mind, or shall I not worry about it?"

#: The return form's choices as the page labels them (src/returns/orders.ts).
_CHOICE_LABELS = {
    "changed_mind": "changed my mind",
    "doesnt_suit_room": "doesn't suit the room",
    "arrived_damaged": "arrived damaged",
    "wrong_item": "received the wrong item",
    "not_as_expected": "not what I expected",
    "unused_in_packaging": "unused, in its packaging",
    "unused_unpacked": "unused, unpacked",
    "damaged_on_arrival": "damaged on arrival",
    "refund": "refund",
    "exchange": "exchange for another option",
    "store_credit": "store credit",
    "pickup": "collect it from you",
    "drop_off": "drop it off",
    "weekday_morning": "weekday morning",
    "weekday_afternoon": "weekday afternoon",
    "saturday": "Saturday",
}

#: The next question for each field of the return form, as the shopper hears it.
_FORM_QUESTIONS = {
    "reason": (
        "Why is it going back: you changed your mind, it doesn't suit the room, it arrived "
        "damaged, it's the wrong item, or it's not what you expected?"
    ),
    "condition": (
        "Is it unused and still in its packaging, unused but unpacked, or was it damaged on arrival?"
    ),
    "resolution": "Would you like a refund, an exchange for another option, or store credit?",
    "collection": "Shall we collect it from you, or will you drop it off?",
    "pickup_window": "When suits you for the collection: a weekday morning, a weekday afternoon, or Saturday?",
}

#: The step of the return form each field is on (the page's steps, CONTRACT v6).
_FIELD_STEP = {
    "items": 1,
    "reason": 2,
    "condition": 2,
    "resolution": 3,
    "collection": 4,
    "pickup_window": 4,
}

_FILLER = frozenset({"the", "and", "one", "ones", "both", "item", "items", "return", "back"})


def _slot_said(slots: Sequence[Slot], said: str) -> Slot | None:
    """The slot the shopper means: its id, or its day (weekday, date, "tomorrow")
    and, where two share a day, its window."""
    text = said.strip().lower()
    exact = next((x for x in slots if x.id == text), None)
    if exact is not None:
        return exact
    tokens = set(re.findall(r"[a-z0-9]+", text))
    on_day = [
        x
        for x in slots
        if set(re.findall(r"[a-z0-9]+", day_words(x.days_from_now).lower())) & tokens
    ]
    windowed = [x for x in (on_day or slots) if x.window in tokens]
    pool = windowed if windowed else on_day
    return pool[0] if len(pool) == 1 else None


def _how_many(qty: int, ordered: int, title: str) -> str:
    """ "the oatmeal wool runner", "both cushions…", "1 of the 2 …" as said."""
    if ordered == 1:
        return f"the {title}"
    if qty == ordered:
        return f"all {qty} of the {title}" if qty > 2 else f"both of the {title}"
    return f"{qty} of the {ordered} {title}"


def _lead_line(lead: str) -> str:
    """The question inside a lead (``ask: "…"``), to speak as a floor line."""
    m = re.search(r'ask: "([^"]+)"', lead)
    return m.group(1) if m else ""


def _together(ids: Sequence[str]) -> str:
    """How saved picks go together, in the catalog's own words: the colour,
    material or feel they share."""
    products = [CATALOG.products[i] for i in ids]
    for kind, attr in (("colour", "colours"), ("material", "materials"), ("feel", "styles")):
        counts: dict[str, int] = {}
        for p in products:
            for w in set(getattr(p, attr)):
                counts[w] = counts.get(w, 0) + 1
        shared = sorted((w for w, n in counts.items() if n >= 2), key=lambda w: -counts[w])
        if shared:
            n = counts[shared[0]]
            who = "all of them" if n == len(products) else f"{n} of them"
            return f"They share {shared[0]} ({kind}), across {who}."
    return "Each is a different kind of piece; see them side by side."


def _reference(detail: str | None) -> str:
    """A return reference in the page's own answer, if it gave one."""
    m = re.search(r"\bRT-[\w-]+", detail or "")
    return m.group(0) if m else ""


_THIS = frozenset({"this", "this one", "that", "that one", "it", "here"})


def _use(text: str) -> str:
    t = text.lower()
    if any(
        k in t for k in ("long", "all day", "hours", "full time", "full-time", "work from home")
    ):
        return "long hours"
    return t.strip()


#: The words shoppers use for a kind of piece that the catalog names otherwise.
_KIND_WORDS = {
    "cushion": "throw-pillows",
    "pillow": "throw-pillows",
    "throw-pillow": "throw-pillows",
    "couch": "sofas",
    "settee": "sofas",
    "carpet": "rugs",
    "runner": "rugs",
    "bed": "beds-bed-frames",
    "bed-frame": "beds-bed-frames",
    "curtain": "curtains-drapes",
    "drape": "curtains-drapes",
    "lamp": "table-lamps",
    "floor-lamp": "floor-lamps",
    "table-lamp": "table-lamps",
    "coffee-table": "coffee-tables",
    "dining-table": "dining-tables",
    "dining-chair": "dining-chairs",
    "office-chair": "office-chairs",
    "desk-chair": "office-chairs",
    "tv-stand": "entertainment-centers-tv-stands",
    "tv-unit": "entertainment-centers-tv-stands",
    "sheet": "bed-sheets",
    "quilt": "quilts-comforters",
    "duvet": "quilts-comforters",
    "comforter": "quilts-comforters",
    "art": "artwork",
    "print": "artwork",
    "painting": "artwork",
    "frame": "picture-frames",
    "towel": "bath-towels-washcloths",
    "bath-mat": "bath-mats-rugs",
    "flower": "artificial-flora",
    "plant": "artificial-flora",
    "shelf": "shelving",
    "bookcase": "shelving",
    "basket": "household-storage-baskets",
}


def _category(text: str) -> str | None:
    """A category slug from a shopper's word ("art" → artwork, "cushions" →
    throw pillows)."""
    t = text.strip().lower().replace(" ", "-")
    if t in CATALOG.categories:
        return t
    for word in (t, t.rstrip("s"), t.removesuffix("es")):
        if word in _KIND_WORDS:
            return _KIND_WORDS[word]
    stem = t.rstrip("s")
    if f"{stem}s" in CATALOG.categories:
        return f"{stem}s"
    for slug in CATALOG.categories:
        if stem and slug.startswith(stem):
            return slug
    for slug, c in CATALOG.categories.items():
        if stem and stem in c.name.lower():
            return slug
    return None


def _journal_slugs() -> set[str]:
    return {p.stem for p in JOURNAL_DIR.glob("*.md")} if JOURNAL_DIR.is_dir() else set()


_JOURNAL = _journal_slugs()


def _valid_page(page: str) -> bool:
    if page in ("home", "journal", "cart", "saved", "gifts", "orders", "kiosk"):
        return True
    kind, _, rest = page.partition("/")
    return (
        (kind == "room" and rest in CATALOG.rooms)
        or (kind == "category" and rest in CATALOG.categories)
        or (kind == "product" and rest in CATALOG.products)
        or (kind == "journal" and rest in _JOURNAL)
        or (kind == "policy" and rest in ("returns", "delivery", "assembly", "care"))
    )
