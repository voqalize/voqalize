"""FernhollowBrain — Mira, the design adviser of a home and furniture store.

A :class:`voqalize_demos.GeminiBrain`. Voqalize dials this brain's WebSocket per
session; the inherited tool loop runs Gemini's calls as they arrive. Mira asks
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
from collections.abc import AsyncGenerator, Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from google import genai
from loguru import logger
from pydantic import BaseModel, Field
from voqalize_demos import (
    DEFAULT_MODEL,
    PATIENCE,
    FallbackLine,
    GeminiBrain,
    landed,
    needs_result_now,
)

from voqalize.sdk import Action, RTVIMessage, Session, Speech, UserMessage
from voqalize.sdk.wire import Config, Language, SttConfig, TtsConfig, Voice

from . import engine as eng
from .app_events import (
    FERNHOLLOW_EVENTS,
    CartChanged,
    ConfirmResult,
    FernhollowEvent,
    FilterChanged,
    PageViewed,
    ProductViewed,
    RoomBoardEdited,
    ShortlistChanged,
    VariantSelected,
    VisibleProducts,
)
from .catalog import CATALOG, JOURNAL_DIR, Product, money
from .policies import Topic, policy_page, policy_text
from .prompt import GREETING, system_instruction
from .recipes import FINISHING, RECIPES

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


class UpdateBrief(Action):
    """The room-brief chips."""

    brief: BriefOut
    products_left: int


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


@dataclass
class PendingAdd:
    lines: list[ConfirmLine]
    label: str
    turn: int


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
    return _prose(f"NOT DONE: {why}.", next=what_to_do)


class FernhollowBrain(GeminiBrain):
    """One per session: the brief, the screen mirror, the shortlist and the cart."""

    def __init__(self, *, client: genai.Client, model: str = DEFAULT_MODEL) -> None:
        super().__init__(client=client, system_instruction=system_instruction(), model=model)
        self.brief = eng.Brief()
        self.screen = Screen()
        self.history: list[Screen] = []
        self.shortlisted: list[str] = []
        self.cart: dict[tuple[str, str], int] = {}
        self.pending: PendingAdd | None = None
        self.turns = 0
        self.seen: dict[str, list[str]] = {}  # slot → products shown there
        self.ahead: dict[tuple[Any, ...], Any] = {}
        self.hits = 0
        self._fallback = FallbackLine()

    # ─── Session ────────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        """Emily, in English, on both legs before the greeting. English is the
        only language this demo speaks."""
        await session.configure(
            Config(
                tts=TtsConfig(voice=Voice.OMNIVOICE_EMILY, language=Language.EN),
                stt=SttConfig(language=Language.EN, patience=PATIENCE),
            )
        )

    async def greet(self, session: Session) -> str:
        """Fixed — no model call — so Mira speaks the instant the call connects."""
        return GREETING

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[Speech, None]:
        """The screen as it is goes in front of the shopper's words, so "this
        one" resolves against now."""
        self.turns += 1
        self.append_note(self.screen_now())
        self.append_note(msg.text)
        async for speech in self.respond(session):
            yield speech

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The model's turn, a landed line if it acted in silence, then the
        look-ahead for what is now on screen."""
        async for event in self._fallback.speak_if_silent(self, super().respond(session)):
            yield event
        self.look_ahead()

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Something the shopper did on the page. The mirror follows it and the
        model gets one line; nothing is spoken."""
        event = FERNHOLLOW_EVENTS.parse(msg)
        if event is None:
            return
        note = self.apply_event(event)
        # The page also reports what Mira herself just did (``by: "mira"``): the
        # mirror follows it, but the model already knows, so no note.
        if note is not None and event.by == "visitor":
            logger.info("fernhollow: shopper {}", note)
            self.append_note(note)

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
        if self.pending is not None:
            parts.append(f"waiting for the shopper's yes on: {self.pending.label}")
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
        if r in ("this", "it", "this one", "that", "that one", "current"):
            pid = s.product or (s.listing[0] if len(s.listing) == 1 else None)
            return CATALOG.get(pid) if pid else None
        m = re.fullmatch(
            r"(?:the\s+)?(\d+|first|second|third|fourth|fifth|sixth|last)(?:\s+one)?", r
        )
        if m:
            seq = s.compare if s.listing_kind == "compare" else s.listing
            word = m.group(1)
            if word == "last":
                idx = len(seq)
            else:
                idx = int(word) if word.isdigit() else _ORDINALS[word]
            if 1 <= idx <= len(seq):
                return CATALOG.products[seq[idx - 1]]
            return None
        pool = [
            *s.listing,
            *s.compare,
            *(pc.product_id for pc in (s.room.pieces if s.room else ())),
        ]
        hits = [i for i in dict.fromkeys(pool) if r in CATALOG.products[i].title.lower()]
        if len(hits) == 1:
            return CATALOG.products[hits[0]]
        return None

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
        self.session.dispatch(UpdateBrief(brief=self._brief_out(), products_left=len(left)))
        if (
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
        """Compare two or three products side by side; each row names its winner."""
        found = [self.resolve(r) for r in request.products]
        ids = [p.id for p in found if p is not None]
        if len(ids) < 2 or len(ids) > 3:
            return _not_done(
                "a comparison needs two or three products I can tell apart", "Ask which ones."
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
        if len(current) < 2 or len(current) > 3:
            return _not_done("a comparison holds two or three products", "Ask which to keep.")
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
        for r in request.add:
            p = self.resolve(r)
            if p is not None and p.id not in self.shortlisted:
                self.shortlisted.append(p.id)
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
            if self.pending is None:
                return _not_done(
                    "there is no confirmation on screen",
                    "Call add_to_cart without confirmed_by_voice first.",
                )
            if self.pending.turn >= self.turns:
                return _not_done(
                    "the shopper has not answered the confirmation yet", "Wait for their yes."
                )
            label = self.pending.label
            self._commit_cart()
            landed("It's in your cart.", "Added.")
            return _prose(f"Added to the cart: {label}. Cart total {money(self._cart_total())}.")
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
        self.pending = PendingAdd(lines, label, self.turns)
        self.session.dispatch(ConfirmAdd(lines=lines, label=label))
        self.session.dispatch(Highlight(target="button:add-to-cart"))
        landed("Shall I add it? The button's ready for your yes.", "Just say yes, or tap Add.")
        return _prose(
            f"The confirmation is on the Add button: {label}. Nothing is in the cart until they say yes.",
        )

    def _commit_cart(self) -> None:
        assert self.pending is not None
        for line in self.pending.lines:
            key = (line.product_id, line.variant_id)
            self.cart[key] = self.cart.get(key, 0) + line.qty
        self.pending = None
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
                pending = self.pending
                if pending is None:
                    return None
                if event.confirmed:
                    self._commit_cart()
                    return (
                        f"[The shopper tapped yes: {pending.label} is in the cart. "
                        f"Cart total {money(self._cart_total())}.]"
                    )
                self.pending = None
                return "[The shopper declined adding to the cart.]"
            case ShortlistChanged():
                self.shortlisted = [i for i in event.product_ids if i in CATALOG.products]
                return f"[The shopper's shortlist now holds {len(self.shortlisted)}.]"


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
