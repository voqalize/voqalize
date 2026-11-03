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

from voqalize.sdk import Action, AppEvents, RTVIMessage, Session, Speech, UserIdle, UserMessage
from voqalize.sdk.stage import Mirror, Stage
from voqalize.sdk.stage.wire import StageEvent, StageHello, StageProgress, StageResult
from voqalize.sdk.wire import Config, IdleConfig, Language, SttConfig, TtsConfig, Voice

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
    REQUIRED,
    STEPS,
    CheckoutField,
    CheckoutStepName,
    check,
    delivery_fee,
    spell_back,
)
from .confirm import Acted, Confirmations, Pending, classify
from .policies import Topic, policy_page, policy_text
from .prompt import GREETING, system_instruction
from .recipes import FINISHING, RECIPES
from .resolve import SELECTED, Layout, Resolution
from .resolve import resolve as resolve_reference
from .returns import WINDOW_DAYS, Order, exchange_options, order_from, plan_return
from .returns import find_order as find_any_order
from .stage_gen import MOVES, SPEC

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
    """The room-brief chips, and the question Emily asks next."""

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
        description="home, room/<room>, category/<slug>, journal, journal/<slug>, cart, policy/<topic>.",
    )
    query: str | None = Field(default=None, description="Search words, for a results grid.")


class ShortlistRequest(BaseModel):
    add: list[str] = Field(default_factory=list[str])
    remove: list[str] = Field(default_factory=list[str])


class AddToCartRequest(BaseModel):
    what: Literal["room", "product"] = "product"
    product: str | None = Field(default=None, description="For one product: the reference.")
    option: str | None = Field(default=None, description="Option value, if they chose one.")
    confirmed_by_voice: bool = Field(
        default=False,
        description="True only when the shopper said yes to a confirmation already on screen.",
    )


class PolicyRequest(BaseModel):
    topic: Topic


class OrderRequest(BaseModel):
    order_number: str = Field(
        description="The order number as the shopper said it, e.g. 'FH-20418'."
    )


class ReturnItem(BaseModel):
    product_id: str = Field(description="An order line's product id, as find_order gives it.")
    qty: int = Field(default=1, description="How many of it go back.")


class PrepareReturn(BaseModel):
    """Every answer the returns form needs, once the shopper has given them."""

    order_number: str = Field(description="As find_order gave it, or 'my last order'.")
    items: list[ReturnItem]
    reason: Literal[
        "changed_mind", "doesnt_suit_room", "arrived_damaged", "wrong_item", "not_as_expected"
    ]
    condition: Literal["unused_in_packaging", "unused_unpacked", "damaged_on_arrival"]
    resolution: Literal["refund", "exchange", "store_credit"]
    collection: Literal["pickup", "drop_off"]
    pickup_window: Literal["weekday_morning", "weekday_afternoon", "saturday"] | None = None
    exchange_variant: str | None = Field(
        default=None, description="For an exchange: the variant id check_exchange gave."
    )


class ResolveRequest(BaseModel):
    spoken: str = Field(description="The shopper's words for the product, as heard.")
    scope: Literal["auto", "screen", "catalog"] = Field(
        default="auto",
        description="auto: the screen first, then the catalog; screen: only what is on screen.",
    )


class CheckoutFields(BaseModel):
    """Checkout fields the shopper just gave, in their words; leave the rest empty."""

    email: str | None = Field(
        default=None, description="As heard, e.g. 'sam dot rivera at example dot com'."
    )
    first_name: str | None = None
    last_name: str | None = None
    address1: str | None = None
    address2: str | None = None
    city: str | None = None
    region: str | None = None
    postcode: str | None = None
    country: str | None = None
    phone: str | None = None
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


def _not_done(why: str, what_to_do: str) -> str:
    # The floor, if the model then says nothing: never a claim it went through.
    landed("That didn't go through yet.")
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
        self.cart: dict[tuple[str, str], int] = {}
        # Every confirmation Emily asks for, one mechanism (confirm.py).
        self.confirms = Confirmations()
        self.confirms.register("add_to_cart", self._act_add)
        self.confirms.register("place_order", self._act_place)
        self.confirms.register("submit_return", self._act_submit)
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
        # The returns form's moves prepare_return sent: call_ref → (step, what).
        self.return_run: dict[str, tuple[str, str]] = {}
        self.return_last: str | None = None
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
        self._fallback = FallbackLine()

    # ─── Session ────────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        """Emily, in English, on both legs before the greeting. English is the
        only language this demo speaks."""
        await session.configure(
            Config(
                tts=TtsConfig(voice=Voice.OMNIVOICE_EMILY, language=Language.EN),
                stt=SttConfig(language=Language.EN, patience=PATIENCE),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
            )
        )

    async def greet(self, session: Session) -> str:
        """Fixed — no model call — so Emily speaks the instant the call connects."""
        return GREETING

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
        async for speech in self.respond(session):
            yield speech

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
            landed(line)
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
            "[The return is being submitted; Emily tells them the page's answer when it comes. "
            "Do not call submit_return again.]",
            ref=ref,
            on_applied=lambda detail: self._submitted_line(
                _reference(detail) or self.last_reference
            ),
        )

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The model's turn, a landed line if it acted in silence, then the
        look-ahead for what is now on screen."""
        turn = self.stage.cued(super().respond(session))
        async for event in self._fallback.speak_if_silent(self, turn):
            yield event
        self.stage.end_turn()
        self.look_ahead()

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
        async for event in self.respond(session):
            yield event

    def _staged(self, event: StageResult | StageHello | StageProgress | StageEvent) -> str | None:
        """One answer from the Stage page, folded in; the line the model reads,
        if any. A cue that landed was spoken past and needs no line; one that
        did not is said plainly, with what the page offers instead."""
        if isinstance(event, StageEvent):
            folded = self.stage.handle(event)
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
        if result.call_ref in self.return_run:
            return self._return_result(result)
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

    def _return_result(self, result: StageResult) -> str | None:
        """One answer to a move prepare_return sent: a refusal stops the run and
        is told exactly, with the step it stopped at; the last move landing says
        the form reached the review."""
        step, what = self.return_run[result.call_ref]
        if result.outcome in ("applied", "partial"):
            if result.call_ref == self.return_last:
                self.return_run = {}
                self._say_line_soon("The form's all filled in — say yes and I'll submit it.")
                return (
                    "[The returns form reached the review step. "
                    "Nothing is submitted until the shopper says yes.]"
                )
            return None
        self.return_run = {}
        if (p := self.confirms.pending) is not None and p.kind == "submit_return":
            self.confirms.clear()
        why = "; ".join(
            f"{r.arg}: {r.why}" + (f" (options: {', '.join(r.options)})" if r.options else "")
            for r in result.refused
        )
        detail = "; ".join(x for x in (result.detail, why) if x) or "no reason given"
        self._say_line_soon(f"The form stopped at step {step.split(' ', 1)[0]}: {detail}.")
        return (
            f"[The returns form stopped at step {step}: {what} was {result.outcome} — {detail}. "
            "Tell the shopper exactly that, ask for what fixes it, then call prepare_return again.]"
        )

    # ─── The screen ─────────────────────────────────────────────────────

    def screen_now(self) -> str:
        s = self.screen
        parts = [f"page: {s.page}"]
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
        if self.cart:
            parts.append(f"cart: {sum(self.cart.values())} items, {money(self._cart_total())}")
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
                    adopted = replace(mine, number=theirs.number, email=theirs.email or mine.email)
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
            self.add_to_cart,
            self.suggest_finish,
            self.store_policy,
            self.find_order,
            self.start_return,
            self.check_exchange,
            self.prepare_return,
            self.submit_return,
            self.resolve_product,
            self.fill_checkout,
            self.checkout_step,
            self.place_order,
            self.clear_selection,
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
        if (
            self.screen.room is None
            and (b.materials or b.colours or b.styles)
            and brief_filters != self.screen.filters
            and (fits := brief_filters.results())
        ):
            self._apply(brief_filters, None)
            on_grid = (
                f"the grid now shows the {len(fits)} that fit; the shopper does not need "
                "to touch the filters"
            )
        elif (
            self.brief.room
            and self.screen.page != f"room/{self.brief.room}"
            and self.screen.room is None
        ):
            self._move(page=f"room/{self.brief.room}")
            self.session.dispatch(Navigate(page=f"room/{self.brief.room}"))
        landed(question.text)
        logger.info(
            "fernhollow: brief {} → {} left, ask {}", self.brief.key(), len(left), question.dim
        )
        return _prose(
            f"The brief is on screen. {len(left)} products in the store fit it so far.",
            grid=on_grid,
            ask_next=question.text,
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
            page="search",
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
                "Use home, room/<room>, category/<slug>, journal, cart or policy/<topic>.",
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

    async def shortlist(self, request: ShortlistRequest) -> str:
        """Save products to, or drop them from, the shortlist tray."""
        added, _ = self.expand(request.add)
        for pid in added:
            if pid not in self.shortlisted:
                self.shortlisted.append(pid)
        for r in request.remove:
            p = self.resolve(r)
            if p is not None and p.id in self.shortlisted:
                self.shortlisted.remove(p.id)
        self.session.dispatch(UpdateShortlist(product_ids=list(self.shortlisted)))
        landed("Saved to your shortlist.", "It's on the shortlist.")
        return _prose(
            f"The shortlist holds {len(self.shortlisted)}.",
            items=[_line(CATALOG.products[i]) for i in self.shortlisted],
        )

    async def add_to_cart(self, request: AddToCartRequest) -> str:
        """Add the room on the board, or one product, to the cart — only with the
        shopper's yes. The first call puts a confirmation on the Add button; a tap
        on it adds by itself. If they say yes out loud on their next turn, call
        again with confirmed_by_voice true."""
        if request.confirmed_by_voice:
            return self._confirmed_by_tool("add_to_cart")
        lines: list[ConfirmLine]
        if request.what == "room":
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
        key = ("add_to_cart", tuple((x.product_id, x.variant_id, x.qty) for x in lines))
        if (
            dup := self.confirms.ask("add_to_cart", key, label, self.turns, lines=lines)
        ) is not None:
            landed(dup)
            return _prose(f"Not asked again: {dup}")
        self.session.dispatch(ConfirmAdd(lines=lines, label=label))
        self.session.dispatch(Highlight(target="button:add-to-cart"))
        landed("Shall I add it? The button's ready for your yes.", "Just say yes, or tap Add.")
        return _prose(
            f"The confirmation is on the Add button: {label}. Nothing is in the cart until they say yes.",
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
    async def find_order(self, request: OrderRequest) -> str:
        """Look an order up for a return: its lines, and for each whether it can
        go back under the returns policy. Answer from the result: say plainly
        when a line is outside the window or not delivered yet."""
        order = self.lookup_order(request.order_number)
        if order is None:
            return _not_done(
                f"there is no order {request.order_number!r}",
                "Ask them to read the order number from their confirmation, e.g. FH-20418.",
            )
        self.order = order
        lines: list[str] = []
        for line in order.lines:
            match line.status:
                case "eligible":
                    when = f"eligible — delivered {line.days_since_delivery} days ago, {line.days_left} days left in the {WINDOW_DAYS}-day window"
                case "outside_window":
                    when = f"outside the window — delivered {line.days_since_delivery} days ago; returns are {WINDOW_DAYS} days from delivery"
                case "not_delivered":
                    when = "not delivered yet — it can go back once it has arrived"
            lines.append(
                f"{line.title} ({line.variant}), qty {line.qty} — {when} [id {line.product_id}]"
            )
        policy = None
        if not order.eligible:
            policy = [
                *policy_text("returns"),
                "Point them to the care guide (policy/care) and to contacting the store; never promise an exception.",
            ]
        logger.info(
            "fernhollow: find_order {} → {}", order.number, [line.status for line in order.lines]
        )
        opened = None
        if order.eligible:
            # One hop: an order that can go back opens its form now, so the
            # answer is spoken from this result without a second model request.
            page = f"returns/start?order={order.number}"
            if self.screen.page != page:
                self._move(page=page, product=None)
                self.session.dispatch(Navigate(page=page))
            opened = "the returns form is open with this order"
            landed("The returns form is open with your order.")
        return _prose(
            f"Order {order.number}: {len(order.eligible)} of {len(order.lines)} lines can be returned.",
            lines=lines,
            policy=policy,
            screen=opened,
            next="ask what is still needed for the return, one thing at a time"
            if order.eligible
            else "no form: explain the policy honestly",
        )

    async def start_return(self, request: OrderRequest) -> str:
        """Open the returns form with the order filled in. Only for an order
        find_order showed has a line that can go back."""
        order = self.lookup_order(request.order_number)
        if order is None:
            return _not_done(
                f"there is no order {request.order_number!r}", "Look it up with find_order first."
            )
        if not order.eligible:
            return _not_done(
                f"nothing on {order.number} can be returned", "Explain the policy honestly instead."
            )
        self.order = order
        page = f"returns/start?order={order.number}"
        self._move(page=page, product=None)
        self.session.dispatch(Navigate(page=page))
        landed("The returns form is open, with your order in.", "Here's the returns form.")
        return _prose(
            f"The returns form is open with order {order.number} filled in. The shopper types their own email.",
            returnable=[
                f"{line.title} ({line.variant}) [id {line.product_id}]" for line in order.eligible
            ],
        )

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
        """Fill checkout fields from what the shopper just said. Read the
        spell-back it returns in one short line, so a mis-heard letter is
        caught; it also says what is still needed."""
        if not self.cart:
            return _not_done("the cart is empty", "Add something to the cart first.")
        if not self.screen.page.startswith("checkout"):
            self._move(page="checkout", product=None)
            self.session.dispatch(Navigate(page="checkout"))
        refused: list[str] = []
        spoken: list[str] = []
        for name in FIELDS:
            raw = getattr(fields, name)
            if raw is None or not str(raw).strip():
                continue
            value, why = check(name, str(raw))
            if why is not None:
                refused.append(f"{name}: {why}")
                continue
            self.checkout[name] = value
            self.session.dispatch(CheckoutFill(field=name, value=value))
            if (said := spell_back(name, value)) is not None:
                spoken.append(said)
        missing = [f for f in REQUIRED if f not in self.checkout and f not in self.checkout_filled]
        landed("That's in.", "Filled in.")
        return _prose(
            "The checkout fields are filled.",
            say_back=" — ".join(spoken) or None,
            not_filled=refused,
            still_needed=", ".join(missing) or "nothing — offer the review step",
        )

    async def checkout_step(self, request: CheckoutStepRequest) -> str:
        """Move the checkout to contact, shipping or review."""
        if not self.cart:
            return _not_done("the cart is empty", "Add something to the cart first.")
        self.checkout_step_now = request.step
        self._move(page="checkout", product=None)
        self.session.dispatch(CheckoutStep(step=request.step))
        landed("Here's that step.", "On to that step.")
        need = [
            f
            for f in STEPS[request.step]
            if f in REQUIRED and f not in self.checkout and f not in self.checkout_filled
        ]
        return _prose(f"The checkout is on {request.step}.", still_needed=", ".join(need) or None)

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
        missing = [f for f in REQUIRED if f not in self.checkout and f not in self.checkout_filled]
        if missing:
            return _not_done(
                f"checkout still needs {', '.join(missing)}", "Ask for them, one at a time."
            )
        total = self._order_total()
        label = f"Place order — {money(total)}"
        key = ("place_order", tuple(sorted(self.cart.items())), total)
        if (
            dup := self.confirms.ask("place_order", key, label, self.turns, total=total)
        ) is not None:
            landed(dup)
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
        """An order Emily placed, with its lines and the checkout email. A demo
        store delivers nothing, so it counts as delivered now (CONTRACT.md, v4)
        and can go back for the whole window."""
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
                    "email": self.checkout.get("email", ""),
                    "name": name,
                    "status": "delivered",
                    "placed_days_ago": 0,
                    "delivered_days_ago": 0,
                    "total": total,
                    "lines": lines,
                },
                "placed",
            )
        )

    async def prepare_return(self, request: PrepareReturn) -> str:
        """Fill the whole returns form in one go, once the shopper has given
        every answer: their order, the items, the reason, the condition, refund
        or exchange or store credit, and pickup (with a window) or drop-off.
        Say one line with the call, then ask "Shall I submit the return?". If the
        page refuses a step, you hear exactly why on the next turn."""
        order = self.lookup_order(request.order_number)
        if order is None:
            return _not_done(
                f"there is no order {request.order_number!r}", "Look it up with find_order first."
            )
        plan = plan_return(
            order,
            [(i.product_id, i.qty) for i in request.items],
            reason=request.reason,
            condition=request.condition,
            resolution=request.resolution,
            collection=request.collection,
            pickup_window=request.pickup_window,
            exchange_variant=request.exchange_variant,
        )
        if isinstance(plan, str):
            return _not_done(
                plan, "Ask the shopper for that one answer, then call prepare_return again."
            )
        missing = sorted({m for m, _, _ in plan if self.stage.moves.get(m) is None})
        if missing:
            return _not_done(
                f"this page cannot fill the form by voice ({', '.join(missing)} missing)",
                "Walk them through the form instead.",
            )
        self.order = order
        page = f"returns/start?order={order.number}"
        if not self.screen.page.startswith("returns/start"):
            self._move(page=page, product=None)
            self.session.dispatch(Navigate(page=page))
        self.return_run = {}
        for move, args, step in plan:
            ref = self.stage.send(move, dict(args), queue=False)
            shown = args.get("field") or args.get("product_id") or ""
            self.return_run[ref] = (step, f"{move.removeprefix('returns.')} {shown}".strip())
            self.return_last = ref
        # The reply with this call asks "Shall I submit the return?": a plain yes
        # on the next turn submits (confirm.py), unless a step is refused.
        self.confirms.ask(
            "submit_return",
            ("submit_return", order.number),
            f"Submit the return for {order.number}",
            self.turns,
        )
        self.return_collection = request.collection
        landed("Filling in the return form now.")
        chosen = {i.product_id: i.qty for i in request.items}
        items = [
            f"{line.title} ({line.variant}), qty {chosen[line.product_id]}"
            for line in order.lines
            if line.product_id in chosen
        ]
        window = f" ({request.pickup_window})" if request.pickup_window else ""
        return _prose(
            f"The returns form for {order.number} is being filled, step by step to the review.",
            items=items,
            answers=f"{request.reason}, {request.condition}, {request.resolution}, "
            f"{request.collection}{window}",
            next="ask 'Shall I submit the return?' and submit only on their yes",
        )

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
            landed(dup)
            return _prose(f"Not asked again: {dup}")
        landed("Shall I submit the return?")
        return _prose("Ask for their yes before submitting. Nothing is submitted yet.")

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
                    order_from(o.model_dump(), "known") for o in event.orders if o.number
                ]
                self._adopt_page_numbers()
                return None  # silent: kept for find_order
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
                if event.field:
                    self.checkout_filled.add(event.field)
                return f"[The shopper filled {event.field} at checkout.]"
            case CheckoutStepReached():
                self.checkout_step_now = event.step
                return f"[The checkout is on {event.step}.]"


#: How long after Emily says an outcome a page "speak" reaction is the same news.
_OUTCOME_GAP_S = 15.0


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


def _category(text: str) -> str | None:
    """A category slug from a shopper's word ("art" → artwork, "lamps" → ...)."""
    t = text.strip().lower().replace(" ", "-")
    if t in CATALOG.categories:
        return t
    stem = t.rstrip("s")
    for slug, c in CATALOG.categories.items():
        if stem and (slug.startswith(stem) or stem in c.name.lower()):
            return slug
    return None


def _journal_slugs() -> set[str]:
    return {p.stem for p in JOURNAL_DIR.glob("*.md")} if JOURNAL_DIR.is_dir() else set()


_JOURNAL = _journal_slugs()


def _valid_page(page: str) -> bool:
    if page in ("home", "journal", "cart"):
        return True
    kind, _, rest = page.partition("/")
    return (
        (kind == "room" and rest in CATALOG.rooms)
        or (kind == "category" and rest in CATALOG.categories)
        or (kind == "product" and rest in CATALOG.products)
        or (kind == "journal" and rest in _JOURNAL)
        or (kind == "policy" and rest in ("returns", "delivery", "assembly", "care"))
    )
