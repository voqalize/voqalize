"""FashioBrain — Fashio's one agent, six jobs.

An :class:`~voqalize.sdk.openai.OpenAIBrain`. One brain, one job per landing page,
followed as the shopper moves (``screen.viewed``): the **shopping assistant** and
site guide on the home page and every shop page (understands a whole request,
filters and shows products, compares, adds to the bag on a spoken yes, guides the
checkout the shopper fills in); the **size and fit advisor** on a product page
(the shared ``recommend`` rule, the size chart, the nearest size in stock); the
**gift finder** on ``/gifts`` (who and the occasion in one breath, then the budget,
then a shortlist with reasons, gift wrap and a note read back once); **order
tracking** on ``/orders`` (status and dates from the data; a delivery date or
address never changes once placed; cancel only before dispatch, pressed by the
shopper); **returns** on ``/returns`` (only within 7 days of delivery, never a
fragrance, the shopper confirms unused with tags and presses Submit); and the
**store kiosk** on ``/kiosk`` (voice search of the whole catalogue, a QR code to
the phone, a floor assistant).

Every move on screen is a Stage move (``frontend/src/stage/scene.json``): the
tools send them with :meth:`Stage.send`, and the ``{show: <id>}`` cue rings a
product as the voice reaches the sentence about it. The page reports what the
shopper does as Stage events, folded into the brain's own state.

Every number comes from ``data/*.json`` and the shared rules in :mod:`.fashio`.
Everything the agent says reaches the voice through :mod:`.spoken`; a budget the
shopper said is read back to the model in rupees, and one no shopper would mean is
confirmed before it is used (FEEDBACK X8).

**One model request a turn (K0 R4).** Searching, opening a product, comparing,
the size advice, the gift shortlist, an order's status and each return step are
actions: the model says a few words of lead-in and calls the tool, and the brain
says the result in its own written line (:data:`.lines.SAID`) straight after, in
the same turn (``say``). The shopper's yes to a bag add, a gift note, a cancel or
"unused with tags" is heard by the brain itself and needs no model request. Only
``product_facts`` and ``read_screen`` wait for their result. The character — name,
roles, voice per language, the languages offered — comes from ``persona.json``.
"""

from __future__ import annotations

import contextlib
import re
from collections.abc import AsyncGenerator, Callable
from contextvars import ContextVar
from dataclasses import dataclass, replace
from datetime import date
from typing import Any, Literal

from loguru import logger
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from voqalize_demos import PATIENCE, FallbackLine, configure_soon, landed, needs_result_now

from voqalize.sdk import (
    Action,
    AppEvent,
    AppEvents,
    RequestRejected,
    RTVIMessage,
    Session,
    Speech,
    SpeechChunk,
    SpeechStart,
    UserIdle,
    UserMessage,
)
from voqalize.sdk.openai import OpenAIBrain
from voqalize.sdk.stage import Mirror, Move, Stage
from voqalize.sdk.stage.wire import StageEvent, StageHello, StageProgress, StageResult
from voqalize.sdk.wire import Config, IdleConfig, RedialConfig, SttConfig, TtsConfig

from . import fashio as f
from .lines import (
    ASK,
    CUT,
    GIFT_WHY,
    GREETING,
    HI_DAYS,
    HI_MONTHS,
    HI_STATUS,
    LANDED,
    MISSES,
    NO_WORDS,
    NUDGE,
    SAID,
    YES_WORDS,
)
from .persona import PERSONA, Persona
from .prompt import system_instruction
from .rejoin import Rejoin
from .spoken import SpokenAmounts, amounts_note, confirm_back, implausible, speak_text
from .stage_gen import MOVES as STAGE_MOVES
from .stage_gen import SPEC, ReadRequest

MODEL = "gpt-6.1-terra"
REASONING = "medium"

#: The quiet spell before the agent may speak up by itself, and how short it gets
#: while it has a line to say (an order the shopper placed, a bag add landed).
_IDLE_MS = 15000
_SAY_NOW_MS = 400

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")

Job = Literal["shopping", "fit", "gifts", "orders", "returns", "kiosk"]

for _table in (*LANDED.values(), *GREETING.values(), *SAID.values(), *GIFT_WHY.values()):
    assert set(PERSONA.languages) <= set(_table), "a persona language has no written line"
for _table in (*CUT.values(), *MISSES.values(), *ASK.values()):
    assert set(PERSONA.languages) <= set(_table), "a persona language has no written line"
assert set(PERSONA.languages) <= set(NUDGE), "a persona language has no nudge"

#: A phone number said aloud: never used, never repeated (X9).
_SPOKEN_PHONE = re.compile(r"(?:\d[\s-]?){7,}")

#: The questions that narrow a search, in the order a good shop assistant asks
#: them: (topic, the search field that answers it).
_TOPICS: tuple[tuple[str, str], ...] = (
    ("dept", "dept"),
    ("types", "types"),
    ("price", "price_max"),
    ("sizes", "sizes"),
)

#: Words that say the item is unused with its tags on (a return's two ticks), and
#: the words that say it is not.
_UNUSED = re.compile(
    r"\b(unused|not used|never used|unworn|not worn|never worn|tags? (?:are |is )?(?:still )?on|"
    r"tags? intact|with (?:the )?tags?)\b|इस्तेमाल नहीं|टैग",
    re.IGNORECASE,
)
_USED = re.compile(
    r"\b(wore it|worn it|washed|used it|tags? (?:are )?off|removed the tags?)\b|पहन लिया|धो",
    re.IGNORECASE,
)


@dataclass
class _Owed:
    """One turn's record: how many units of the model's speech went out and what
    they said, and the brain's own line the turn ends on (property's pattern)."""

    starts: int = 0
    text: str = ""
    line: str | None = None
    at: int = 0
    always: bool = False

    def floor(self) -> str | None:
        if self.line is None:
            return None
        if self.always:
            return self.line
        return self.line if self.starts == self.at else None


async def _counted(
    turn: AsyncGenerator[Speech, None], record: _Owed
) -> AsyncGenerator[Speech, None]:
    try:
        async for s in turn:
            if isinstance(s, SpeechStart):
                record.starts += 1
            elif isinstance(s, SpeechChunk):
                record.text += s.text
            yield s
    finally:
        await turn.aclose()


_OWED: ContextVar[_Owed | None] = ContextVar("fashio_owed", default=None)


def owe(line: str) -> None:
    """Beside a read whose answer the shopper is waiting for: the written answer,
    said by the brain when the model's turn says nothing after the tool ran."""
    if (record := _OWED.get()) is not None:
        record.line = line
        record.at = record.starts
        record.always = False


def say(line: str) -> None:
    """Beside a step the brain answers itself: the line the turn ends on, said
    straight after the model's few words (K0 R4). The last step of a turn wins."""
    if (record := _OWED.get()) is not None:
        record.line = line
        record.at = record.starts
        record.always = True


class LanguageChanged(Action):
    """The call's language moved: the page's EN / हिंदी toggle follows."""

    language: str


class LanguageRequested(AppEvent):
    """The shopper pressed the other language on the call tile's toggle mid-call."""

    language: str = "en"
    by: str = "visitor"


_EVENTS = AppEvents(LanguageRequested, StageResult, StageHello, StageProgress, StageEvent)

Dept = Literal["men", "women", "kids", "boys", "girls", "ethnic", "footwear", "accessories", "all"]
SortBy = Literal["popular", "price_asc", "price_desc", "discount", "new"]
Reason = Literal[
    "size_small",
    "size_large",
    "not_as_pictured",
    "quality",
    "changed_mind",
    "damaged",
    "wrong_item",
]


# ─── Tool parameters ──────────────────────────────────────────────────────────


class SearchRequest(BaseModel):
    """What the shopper asked for. Only what changed; the rest of the search is kept."""

    dept: Dept | None = Field(default=None, description="Who it is for, or the department.")
    types: list[str] | None = Field(default=None, description="Type ids: kurtas, heels, watches.")
    brands: list[str] | None = None
    colours: list[str] | None = Field(
        default=None, description="Catalogue colours: Navy Blue, Maroon."
    )
    sizes: list[str] | None = Field(default=None, description="Their size: M, XL, 32, UK 7.")
    price_min: int | None = Field(default=None, description="Rupees.")
    price_max: int | None = Field(default=None, description="Rupees: their budget.")
    discount_min: int | None = Field(default=None, description="At least this percent off.")
    usage: list[str] | None = Field(
        default=None, description="Casual, Ethnic, Formal, Sports, Party, Smart Casual, Travel."
    )
    seasons: list[str] | None = None
    query: str | None = Field(
        default=None, description="Words the name must contain: silk, floral."
    )
    sort: SortBy | None = None
    clear: list[str] | None = Field(
        default=None, description="Fields to unset, e.g. ['colours', 'price_max']."
    )
    reset: bool = Field(default=False, description="Start the search over first.")


class ProductRef(BaseModel):
    product_id: str = Field(description="A product id, 7421.")


class CompareRequest(BaseModel):
    product_ids: list[str] = Field(description="Two to four product ids.")


class WishRequest(BaseModel):
    product_id: str
    on: bool = True


class ProposeRequest(BaseModel):
    product_id: str
    size: str | None = Field(default=None, description="The size they said: M, 32, UK 7.")
    qty: int = 1


class YesRequest(BaseModel):
    shopper_said_yes: bool = Field(description="True only when they just agreed to the add.")


class PageRequest(BaseModel):
    page: str = Field(
        description="/, /shop, /shop/<dept>, /shop/<dept>/<type>, /wishlist, /bag, /checkout, /orders, /returns, /gifts, /about."
    )


class CheckoutRequest(BaseModel):
    field: Literal["contact", "address", "payment", "place"]


class SizeAdviceRequest(BaseModel):
    product_id: str | None = Field(default=None, description="Empty: the product on screen.")
    usual_size: str | None = Field(
        default=None, description="The size they usually wear: M, 32, UK 7."
    )
    fit: Literal["snug", "regular", "relaxed"] | None = None
    height_cm: int | None = None


class SizeChartRequest(BaseModel):
    product_id: str | None = None
    size: str | None = None


class PickSizeRequest(BaseModel):
    product_id: str | None = None
    size: str


class GiftBriefRequest(BaseModel):
    """Only what they just said; the rest of the brief is kept."""

    recipient: str | None = Field(
        default=None, description="Her, Him, Mom, Dad, Sister, Brother, Friend, Partner, Kid."
    )
    occasion: str | None = None
    budget_max: int | None = Field(default=None, description="Rupees.")
    no_budget: bool = Field(default=False, description="They said no limit / don't worry about it.")
    size: str | None = None
    colours: list[str] | None = None
    patterns: list[str] | None = Field(
        default=None, description="Solid, Printed, Striped, Checked, Embroidered."
    )
    material: str | None = None


class GiftWrapRequest(BaseModel):
    product_id: str
    size: str | None = None
    on: bool = True
    note: str | None = Field(default=None, description="The note exactly as they dictated it.")


class OrderRef(BaseModel):
    order_id: str | None = Field(default=None, description="FSH-48602, or empty.")


class ChangeRequest(BaseModel):
    order_id: str | None = None
    what: Literal["date", "address"]


class ReturnRequest(BaseModel):
    order_id: str | None = None
    product_id: str | None = Field(default=None, description="The item, if they named it.")


class ReturnDetailsRequest(BaseModel):
    order_id: str | None = None
    product_id: str | None = None
    reason: Reason | None = None
    shopper_said_unused_with_tags: bool = Field(
        default=False, description="True only when they themselves said it is unused with tags on."
    )


class KioskSearchRequest(BaseModel):
    """The whole kiosk search (absent fields are cleared)."""

    query: str | None = None
    genders: list[Literal["men", "women", "boys", "girls", "unisex"]] | None = None
    types: list[str] | None = None
    colours: list[str] | None = None
    sizes: list[str] | None = None
    price_max: int | None = None
    usage: list[str] | None = None


class KioskQrRequest(BaseModel):
    product_id: str | None = Field(default=None, description="Empty: the shortlist's QR code.")


class AssistRequest(BaseModel):
    why: str | None = Field(default=None, description="What they need help with, if they said.")


class LanguageRequest(BaseModel):
    language: Literal["english", "hindi"]


@dataclass
class Pending:
    """Something held for the shopper's yes: a bag add, a gift note, opening the
    cancel, or the two "unused with tags" ticks of a return."""

    kind: Literal["add", "note", "cancel", "unused"]
    turn: int
    product_id: int | None = None
    size: str | None = None
    qty: int = 1
    note: str | None = None
    order_id: str | None = None


def _words(text: str) -> str:
    # The danda (।, ॥) sits inside the Devanagari block: a Hindi "हाँ।" is a yes too.
    return " " + re.sub(r"[^\wऀ-ॿ' ]|[।॥]", " ", text.lower()) + " "


def _yes_no(text: str) -> Literal["yes", "no"] | None:
    t = _words(text)
    if any(f" {w} " in t for w in NO_WORDS):
        return "no"
    if any(f" {w} " in t for w in YES_WORDS):
        return "yes"
    return None


def _unused_said(text: str) -> Literal["yes", "no"] | None:
    """Their answer to "is it unused, with the tags on?"."""
    if _USED.search(text):
        return "no"
    if _UNUSED.search(text):
        return "yes"
    return _yes_no(text)


_JOB_PAGES: dict[str, Job] = {
    "/gifts": "gifts",
    "/orders": "orders",
    "/returns": "returns",
    "/kiosk": "kiosk",
}


def _route(path: str) -> tuple[Job, int | None]:
    m = re.match(r"^/p/(\d+)", path)
    if m:
        return "fit", int(m.group(1))
    return _JOB_PAGES.get(path, "shopping"), None


def _canonical(path: str) -> tuple[str, dict[str, str]]:
    """The route under the app's base without query or trailing slash, and the query."""
    p, _, query = path.partition("?")
    p = p.split("#", 1)[0]
    p = re.sub(r"^/demos/fashio", "", p) or "/"
    params = dict(kv.split("=", 1) for kv in query.split("&") if "=" in kv)
    return p.rstrip("/") or "/", params


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


#: What a brain holds for one socket only. Everything else a call built is carried
#: to the brain a redial starts (rejoin.py).
_PER_SOCKET = frozenset({"_session", "_awaiting"})


class FashioBrain(OpenAIBrain):
    """One per session: the job, the search, the bag and wishlist as reported, the
    product in front, the gift brief, the order and return in hand, the kiosk."""

    def __init__(
        self, *, client: AsyncOpenAI, model: str = MODEL, persona: Persona = PERSONA
    ) -> None:
        super().__init__(
            client=client,
            system_instruction=system_instruction(persona),
            model=model,
            reasoning=REASONING,
        )
        self.persona = persona
        self.lang = persona.default_language
        self.path = "/"
        self.job: Job = "shopping"
        #: The product page in front (the fit job), else None.
        self.product_id: int | None = None
        #: The search as the shopper asked for it, which is exactly what the screen
        #: shows: an answer that offers a piece over the budget never widens it.
        self.search = f.Search()
        self.results: list[int] = []
        self.asked: set[str] = set()
        self._nudges = 0
        #: The bag and wishlist as the page last reported them.
        self.bag_lines: list[str] = []
        self.bag_count = 0
        self.bag_total = 0
        self.wishlist: list[int] = []
        self.checkout: dict[str, bool] = {}
        #: Per product: the size picked, and what was said in Find my size.
        self.size_picked: dict[int, str] = {}
        self.fit_inputs: dict[int, dict[str, Any]] = {}
        self.pending: Pending | None = None
        self.gift = f.GiftBrief()
        self.gift_ids: list[int] = []
        #: The order selected (orders, returns), and statuses changed in this call.
        self.order_id: str | None = None
        self.order_status: dict[str, str] = {}
        self.placed: list[dict[str, Any]] = []
        self.returned: set[str] = set()
        self.ret: dict[str, Any] = {}
        self.kiosk: dict[str, Any] = {}
        self.kiosk_saved: list[int] = []
        self.turns = 0
        self._flights: dict[str, Pending] = {}
        self._say_next: Callable[[], str] | None = None
        self.stage = Stage(
            dispatch=lambda a: self.session.dispatch(a),
            moves=STAGE_MOVES,
            resolve=self._resolve,
            mirror=Mirror(SPEC),
        )
        self._fallback = FallbackLine()
        self._spoken = SpokenAmounts(lambda: self.lang)
        #: The shopper's last few turns, as heard: what a budget is checked against.
        self._heard_recent: list[str] = []
        self._rejoined = False

    # ─── Session ────────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        """The persona's voice for the call's language on both legs, and the job
        from the page the call started on. A redial on a call this process still
        holds adopts it as it was (CONTRACT.md, "Redial"), with no second hello."""
        prior = REJOIN.take(session.id)
        self._rejoined = False
        if prior is not None and prior is not self:
            self._adopt(prior)
            self._rejoined = True
            logger.info("fashio: rejoined call {} after its socket dropped", session.id)
        else:
            init = session.init or {}
            self.lang = self.persona.tag(str(init.get("lang") or init.get("language") or ""))
            self._at(str(init.get("page") or "/"))
        REJOIN.hold(session.id, self)
        await session.configure(
            Config(
                stt=SttConfig(language=self.persona.language(self.lang), patience=PATIENCE),
                tts=TtsConfig(
                    voice=self.persona.voice(self.lang), language=self.persona.language(self.lang)
                ),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
                redial=RedialConfig(enabled=True) if session.can_redial else None,
            )
        )
        logger.info("fashio: session on {} as {} in {}", self.path, self.job, self.lang)

    async def on_session_end(self, session: Session) -> None:
        REJOIN.dropped(session.id, self)

    def _adopt(self, prior: FashioBrain) -> None:
        """Take over ``prior``'s call: every piece of state but its socket's."""
        self.__dict__.update({k: v for k, v in prior.__dict__.items() if k not in _PER_SOCKET})
        prior.__dict__ = self.__dict__

    async def greet(self, session: Session) -> str | None:
        """Written, not generated: the job's opener in the call's language. A
        rejoined call opens silently."""
        if self._rejoined:
            return None
        key: str = self.job
        p = f.product(self.product_id)
        if self.job == "fit" and p is not None and p["scale"] == "one":
            key = "fit_one"
        if self.job == "returns" and self.order_id:
            key = "returns_order"
        line = GREETING[key][self.lang].format(name=self.persona.name, first=f.CUSTOMER["first"])
        return speak_text(line, self.lang)

    def _at(self, raw: str) -> bool:
        """The shopper is on ``raw``; True when the job changed."""
        path, params = _canonical(raw)
        self.path = path
        job, pid = _route(path)
        if job == "fit" and f.product(pid) is None:
            job, pid = "shopping", None
        if job in ("orders", "returns") and params.get("order"):
            self.order_id = params["order"]
        changed = job != self.job or pid != self.product_id
        self.job, self.product_id = job, pid
        return changed

    # ─── The turn ───────────────────────────────────────────────────────

    def on_user_message(self, session: Session, msg: UserMessage) -> AsyncGenerator[Speech, None]:
        return self._spoken.wrap(self._answer(session, msg))

    async def _answer(self, session: Session, msg: UserMessage) -> AsyncGenerator[Speech, None]:
        self.turns += 1
        self._heard_recent = [*self._heard_recent[-2:], msg.text]
        self.stage.visitor_spoke()
        self._settle_expired()
        if self.lang != "hi" and "hi" in self.persona.languages and _DEVANAGARI.search(msg.text):
            await session.configure(self._speaking("hi"))
        self.append_note(self.screen_now())
        self.append_note(msg.text)
        if _SPOKEN_PHONE.search(msg.text):
            self.append_note(
                "[They said a phone number aloud. Never repeat it or use it: they type every "
                "personal detail on the page themselves.]"
            )
        elif (said := amounts_note(msg.text)) is not None:
            self.append_note(said)
        pending = self.pending
        if pending is not None and pending.turn < self.turns:
            answer = _unused_said(msg.text) if pending.kind == "unused" else _yes_no(msg.text)
            if answer == "yes":
                line = self._confirmed(pending)
                async for speech in self.say_line(line, remember=True):
                    yield speech
                return
            self.pending = None
            if answer == "no" and pending.kind == "unused":
                async for speech in self.say_line(self._said("return_used"), remember=True):
                    yield speech
                return
            if answer == "no":
                self.append_note("[They said no to what you offered; nothing changed.]")
            else:
                self.append_note(
                    "[They did not answer what you offered; it is no longer held: nothing changed.]"
                )
        async for speech in self.respond(session):
            yield speech

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The model's turn with its cues sent to the page; a written line under a
        turn that moved the screen in silence; and the brain's own line a step
        owes, said straight after."""
        record = _Owed()
        token = _OWED.set(record)
        try:
            turn = _counted(self.stage.cued(super().respond(session)), record)
            async for event in self._fallback.speak_if_silent(self, turn):
                yield event
            if (floor := record.floor()) is not None:
                if not record.always:
                    logger.warning("fashio: a read went unanswered; the brain says {!r}", floor)
                async for event in self.stage.cued(self.say_line(floor, remember=True)):
                    yield event
        finally:
            with contextlib.suppress(ValueError):
                _OWED.reset(token)
        self.stage.end_turn()

    def on_user_idle(self, session: Session, idle: UserIdle) -> AsyncGenerator[Speech, None]:
        return self._spoken.wrap(self._idle(session))

    async def _idle(self, session: Session) -> AsyncGenerator[Speech, None]:
        """A quiet spell: a line the brain owes (an order placed, a bag add landed);
        otherwise stay quiet."""
        self._settle_expired()
        configure_soon(session, Config(idle=IdleConfig(timeout_ms=_IDLE_MS)))
        line, self._say_next = self._say_next, None
        if line is not None:
            async for event in self.say_line(line(), remember=True):
                yield event

    def _say_soon(self, line: Callable[[], str]) -> None:
        self._say_next = line
        configure_soon(self.session, Config(idle=IdleConfig(timeout_ms=_SAY_NOW_MS)))

    def screen_now(self) -> str:
        """The page, the job and the state that matters, in front of what they say."""
        language = self.persona.language_names[self.lang]
        role = self.persona.roles.get(self.job, self.job)
        where = f"{self.path}. Your job: {role.lower()}."
        extra: list[str] = []
        if self.job == "fit" and (p := f.product(self.product_id)) is not None:
            extra.append(f"Product in front: {self._row(p)}")
            if (s := self.size_picked.get(p["id"])) is not None:
                extra.append(f"Size picked: {s}.")
            if inputs := self.fit_inputs.get(p["id"]):
                extra.append(
                    "Find my size: " + ", ".join(f"{k} {v}" for k, v in inputs.items()) + "."
                )
        elif self.job == "gifts":
            extra.append(f"Gift brief: {self._brief_line()}.")
            if self.gift_ids:
                extra.append(
                    "Shortlist on screen: "
                    + "; ".join(self._row(p) for i in self.gift_ids if (p := f.product(i)))
                )
        elif self.job in ("orders", "returns"):
            extra.append("Orders: " + "; ".join(self._order_row(o) for o in self._orders()) + ".")
            if self.order_id:
                extra.append(f"Selected: {self.order_id}.")
            if self.job == "returns" and self.ret:
                extra.append(
                    "Return form: " + ", ".join(f"{k} {v}" for k, v in self.ret.items()) + "."
                )
        elif self.job == "kiosk":
            if self.kiosk:
                extra.append(
                    "Kiosk: " + ", ".join(f"{k} {v}" for k, v in self.kiosk.items() if k != "ids")
                )
            ids = [int(i) for i in self.kiosk.get("ids") or []][:4]
            if ids:
                extra.append(
                    "First results: " + "; ".join(self._row(p) for i in ids if (p := f.product(i)))
                )
            if self.kiosk_saved:
                extra.append(f"Shortlist: {', '.join(map(str, self.kiosk_saved))}.")
        else:
            first = [p for i in self.results[:4] if (p := f.product(i))]
            extra.append(
                f"Search: {self.search.summary()}; {len(self.results)} products match"
                + (": " + "; ".join(self._row(p) for p in first) if first else "")
                + "."
            )
        if self.bag_count:
            extra.append(
                f"Bag: {self.bag_count} items, total {f.inr(self.bag_total)} ({', '.join(self.bag_lines)})."
            )
        if self.wishlist:
            extra.append(f"Wishlist: {', '.join(map(str, self.wishlist))}.")
        if self.pending is not None:
            extra.append(f"Waiting for their yes: {self._pending_line(self.pending)}.")
        return f"[Screen: {where} {' '.join(extra)}] [Language: {language}]"

    def _row(self, p: dict[str, Any]) -> str:
        stock = ", ".join(f"{lb}{'' if n > 3 else f' ({n} left)'}" for lb, n in p["sizes"] if n > 0)
        attrs = ", ".join(f"{k} {v}" for k, v in (p.get("attrs") or {}).items())
        off = f" ({f.discount_pct(p)}% off {f.inr(p['mrp'])})" if f.discount_pct(p) else ""
        return (
            f"{p['id']} {p['name']} by {p['brand']}, {f.type_label(p['type'])}, {p['colour']}, "
            f"{f.inr(p['price'])}{off}, in stock: {stock or 'none'}"
            + (f", {attrs}" if attrs else "")
            + f", {p['usage']}"
        )

    def _pending_line(self, p: Pending) -> str:
        x = f.product(p.product_id)
        name = x["name"] if x else ""
        if p.kind == "add":
            return f"add {p.product_id} {name} in {p.size} to the bag"
        if p.kind == "note":
            return f"gift note {p.note!r} on {p.product_id}"
        if p.kind == "cancel":
            return f"open the cancel for {p.order_id}"
        return f"tick unused and tags for {p.product_id} {name} in the return of {p.order_id}"

    # ─── Stage ──────────────────────────────────────────────────────────

    def _resolve(self, move: Move, args: list[str]) -> list[str] | None:
        """A ``{show: …}`` cue names a product id that exists, or is dropped."""
        if move.id == "shop.show" and args:
            p = f.product(args[0])
            return [str(p["id"])] if p else None
        return args

    def _send(self, move: str, args: dict[str, Any]) -> str:
        """Send a move now. The page runs its moves one at a time in order, so a
        tool that sends two (go to a page, then fill it) never loses the first to
        the director's queue, which keeps only the newest."""
        return self.stage.send(move, args, queue=False)

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        event = _EVENTS.parse(msg)
        if event is None:
            return
        if isinstance(event, LanguageRequested):
            await self._requested(session, event.language)
            return
        if isinstance(event, StageEvent):
            note = self._event(event)
        elif isinstance(event, StageResult):
            result = self.stage.handle(event)
            note = None if result is None else self._settle(result)
        else:
            self.stage.handle(event)
            note = None
        if note is not None:
            logger.info("fashio: {}", note)
            self.append_note(note)

    def _event(self, event: StageEvent) -> str | None:
        """Fold what the page reports into the brain's state; the line the model reads."""
        folded = self.stage.handle(event)
        data = event.data
        visitor = event.by == "visitor"
        match event.name:
            case "screen.viewed":
                pid = data.get("product_id")
                raw = str(data.get("path") or "/")
                if self._at(raw):
                    if self.job == "fit" and (p := f.product(self.product_id)) is not None:
                        return f"[They are now on the page of {p['id']} {p['name']}: your job here is size and fit.]"
                    return f"[They are now on {self.path}: your job here is {self.persona.roles.get(self.job, self.job).lower()}.]"
                if pid and self.job == "fit" and f.product(pid) is not None:
                    self.product_id = int(pid)
                if data.get("order_id"):
                    self.order_id = str(data["order_id"])
                return None
            case "shop.changed":
                self.search = f.Search.of(data)
                self.results = [p["id"] for p in f.search(self.search)]
            case "product.size_picked":
                if (p := f.product(data.get("product_id"))) is not None and data.get("size"):
                    self.size_picked[p["id"]] = str(data["size"])
            case "fit.changed":
                if (p := f.product(data.get("product_id"))) is not None:
                    inputs = self.fit_inputs.setdefault(p["id"], {})
                    for k in ("height_cm", "usual_size", "fit"):
                        if data.get(k) not in (None, ""):
                            inputs[k] = data[k]
            case "bag.changed":
                self.bag_lines = [str(x) for x in data.get("lines") or []]
                self.bag_count = int(data.get("count") or 0)
                self.bag_total = int(data.get("total") or 0)
            case "wishlist.changed":
                self.wishlist = [int(i) for i in data.get("ids") or [] if str(i).isdigit()]
            case "checkout.changed":
                for k in ("contact", "address", "payment"):
                    if k in data:
                        self.checkout[k] = bool(data[k])
            case "order.placed":
                oid = str(data.get("order_id") or "")
                if oid:
                    self.order_status[oid] = "placed"
                    self.placed.append({"id": oid, "total": int(data.get("total") or 0)})
                    self.stage.take_reaction()
                    self._say_soon(
                        lambda: self._said(
                            "order_placed",
                            first=f.CUSTOMER["first"],
                            id=oid,
                            eta=self._date(
                                f.add_days(f.today(), int(f.POLICY["delivery"]["days_max"]))
                            ),
                        )
                    )
            case "order.selected":
                if data.get("order_id"):
                    self.order_id = str(data["order_id"])
            case "order.cancelled":
                oid = str(data.get("order_id") or "")
                if oid:
                    self.order_status[oid] = "cancelled"
                    self.stage.take_reaction()
                    o = self._order(oid)
                    pay = self._payment(o["payment"] if o else "")
                    self._say_soon(
                        lambda: self._said(
                            "order_cancelled", first=f.CUSTOMER["first"], id=oid, payment=pay
                        )
                    )
            case "return.changed":
                for k in ("order_id", "product_id", "reason", "unused", "tags"):
                    if k in data and data[k] not in (None, ""):
                        self.ret[k] = data[k]
            case "return.submitted":
                oid = str(data.get("order_id") or self.ret.get("order_id") or "")
                pid = data.get("product_id") or self.ret.get("product_id")
                if oid:
                    self.order_status[oid] = "return_requested"
                    if pid:
                        self.returned.add(f"{oid}|{pid}")
                    self.ret["reference"] = data.get("reference")
                    self.stage.take_reaction()
                    self._say_soon(
                        lambda: self._said("return_submitted", first=f.CUSTOMER["first"])
                    )
            case "gifts.changed":
                g = self.gift
                for k in ("recipient", "occasion", "size", "material"):
                    if data.get(k):
                        setattr(g, k, str(data[k]))
                if data.get("budget_max") is not None:
                    g.budget_max = int(data["budget_max"])
                for k in ("colours", "patterns"):
                    if data.get(k) is not None:
                        setattr(g, k, [str(x) for x in data[k]])
                if data.get("ids") is not None:
                    self.gift_ids = [int(i) for i in data["ids"] if str(i).isdigit()]
            case "kiosk.changed":
                for k, v in data.items():
                    if k != "by":
                        self.kiosk[k] = v
                if data.get("shortlist") is not None:
                    self.kiosk_saved = [int(i) for i in data["shortlist"] if str(i).isdigit()]
            case _:
                pass
        if folded is None or not visitor:
            return None
        return folded.note

    def _settle_expired(self) -> None:
        for result in self.stage.expire():
            if (note := self._settle(result)) is not None:
                self.append_note(note)

    def _settle(self, result: StageResult) -> str | None:
        """A move's answer: a bag add or a gift note is told in a written line; a
        move that did not land is told to the model with what the page offers."""
        held = self._flights.pop(result.call_ref, None)
        why = "; ".join(
            r.why + (f" (options: {', '.join(r.options)})" if r.options else "")
            for r in result.refused
        )
        landed_ok = result.moved or result.outcome in ("applied", "partial", "undone")
        if held is not None and held.kind == "add":
            if landed_ok:
                self._say_soon(lambda: self._said("added"))
                return f"[Added to the bag: {held.product_id} in {held.size}.]"
            reason = result.detail or why or result.outcome
            self._say_soon(lambda: self._said("add_failed", why=reason))
            return f"[The bag add did not go through: {reason}. Offer another size in stock.]"
        if landed_ok:
            return None
        return (
            f"[Your {result.move} move did not land ({result.detail or result.outcome}"
            + (f"; {why}" if why else "")
            + "). Never say it did.]"
        )

    # ─── Words ──────────────────────────────────────────────────────────

    def _said(self, key: str, **kw: Any) -> str:
        return SAID[key][self.lang].format(**kw)

    def _and(self, items: list[str]) -> str:
        word = " और " if self.lang == "hi" else " and "
        if not items:
            return ""
        return items[0] if len(items) == 1 else ", ".join(items[:-1]) + word + items[-1]

    def _or(self, items: list[str]) -> str:
        word = " या " if self.lang == "hi" else " or "
        return items[0] if len(items) == 1 else ", ".join(items[:-1]) + word + items[-1]

    def _name(self, p: dict[str, Any]) -> str:
        return f.short_name(p)

    def _off(self, p: dict[str, Any]) -> str:
        pct = f.discount_pct(p)
        return self._said("off", pct=pct) if pct >= 1 else ""

    def _stock(self, p: dict[str, Any]) -> str:
        sizes = f.sizes_in_stock(p)
        few = [(lb, n) for lb, n in p["sizes"] if 0 < n <= 3]
        if few:
            return self._said("stock_few", sizes=self._and(sizes), n=few[0][1], size=few[0][0])
        return self._said("stock_sizes", sizes=self._and(sizes))

    def _date(self, d: date) -> str:
        if self.lang == "hi":
            return f"{HI_DAYS[d.weekday()]}, {d.day} {HI_MONTHS[d.month - 1]}"
        return f.spoken_day(d)

    def _status(self, s: str) -> str:
        return HI_STATUS.get(s, s) if self.lang == "hi" else f.status_label(s).lower()

    def _payment(self, payment: str) -> str:
        """Where a refund goes, as a line says it."""
        p = payment.strip()
        low = p.lower()
        if low.startswith("cash"):
            return "आपके जोड़े गए बैंक खाते" if self.lang == "hi" else "the bank account you add"
        if low.startswith("card"):
            digits = re.sub(r"\D", "", p)
            return f"{digits} वाले card" if self.lang == "hi" else f"your card ending {digits}"
        return p or ("आपके पेमेंट के तरीके" if self.lang == "hi" else "your original payment method")

    def _show(self, p: dict[str, Any]) -> str:
        return f"{{show: {p['id']}}} "

    def _nudge(self) -> str:
        options = NUDGE[self.lang]
        self._nudges += 1
        return options[self._nudges % len(options)]

    def _product(self, ref: str | None, *, default: int | None = None) -> dict[str, Any] | None:
        if ref:
            return f.product(ref)
        return f.product(default)

    # ─── Shopping ───────────────────────────────────────────────────────

    def _next_step(self, found: list[dict[str, Any]], s: f.Search) -> str:
        """The next question worth asking (never one asked or answered), or, once
        the pieces are few or nothing is left to ask, a nudge."""
        known = {t for t, name in _TOPICS if getattr(s, name) not in (None, [])}
        open_topics = [t for t, _ in _TOPICS if t not in known and t not in self.asked]
        if len(found) <= 3 or not open_topics:
            return self._nudge()
        topic = open_topics[0]
        self.asked.add(topic)
        return ASK[topic][self.lang]

    def _nearest(self, s: f.Search) -> tuple[str, dict[str, Any]] | None:
        """When nothing fits: the one piece closest to it, and what it misses. Over
        the budget by at most 50%, else one limit dropped. The screen keeps what
        they asked for; this is only what the answer offers."""
        if s.price_max is not None:
            over = [
                p for p in f.search(replace(s, price_max=None)) if p["price"] <= s.price_max * 1.5
            ]
            if over:
                return "budget", min(over, key=lambda p: (p["price"], p["rank"]))
        for name in (
            "sizes",
            "colours",
            "brands",
            "query",
            "usage",
            "seasons",
            "discount_min",
            "price_min",
        ):
            value = getattr(s, name)
            if value in (None, []):
                continue
            found = f.search(replace(s, **{name: [] if isinstance(value, list) else None}))
            if found:
                return name, found[0]
        return None

    def _sizes_said(self, sizes: list[str]) -> list[str]:
        out: list[str] = []
        for x in sizes:
            v = x.strip().upper().replace("XXXL", "3XL").replace("2XL", "XXL")
            if v.isdigit() and int(v) <= 13:
                out.append(f"UK {int(v)}")
            elif re.fullmatch(r"UK\s*\d+", v):
                out.append("UK " + re.sub(r"\D", "", v))
            elif v in ("ONESIZE", "ONE SIZE", "FREE SIZE"):
                out.append("Onesize")
            else:
                out.append(v)
        return out

    async def search_products(self, request: SearchRequest) -> str:
        """Set the listing's search from what the shopper said: each filter rings
        and sets in turn and the grid follows. Pass only what changed. Say only a
        few words before calling it: the pieces that fit are said for you."""
        budgets: dict[str, float | None] = {
            "price_min": request.price_min,
            "price_max": request.price_max,
        }
        heard = self._heard_recent[::-1]
        if (why := implausible(budgets, heard)) is not None:
            amount = confirm_back(budgets, heard)
            say(
                self._said("budget_check", amount=f.inr(amount))
                if amount is not None
                else self._said("budget_again")
            )
            return why
        s = f.Search() if request.reset else replace(self.search)
        for name in request.clear or []:
            if hasattr(s, name):
                setattr(s, name, [] if isinstance(getattr(s, name), list) else None)
        notes: list[str] = []
        given = request.model_dump(exclude={"clear", "reset"}, exclude_none=True)
        if "types" in given:
            picked = [t for t in (f.match_type(v) for v in given["types"]) if t]
            if len(picked) < len(given["types"]):
                notes.append(
                    "Some types are not in the catalogue; use the type ids listed in your instructions."
                )
            given["types"] = picked
        if "colours" in given:
            picked = [c for c in (f.match_colour(v) for v in given["colours"]) if c]
            if len(picked) < len(given["colours"]):
                notes.append(f"Catalogue colours: {', '.join(f.COLOURS)}.")
            given["colours"] = picked
        if "brands" in given:
            picked = [b for b in (f.match_brand(v) for v in given["brands"]) if b]
            if len(picked) < len(given["brands"]):
                notes.append("A brand they named is not in the catalogue; say so if it matters.")
            given["brands"] = picked
        if "sizes" in given:
            given["sizes"] = self._sizes_said(given["sizes"])
        for key, value in given.items():
            setattr(s, key, value)
        self.search = s
        found = f.search(s)
        self.results = [p["id"] for p in found]
        self._send("shop.filter", s.args())
        screen = f"The screen shows {len(found)} products: {s.summary()}."
        detail = ["DETAIL, in the screen's order:", *(self._row(p) for p in found[:6])]
        if found:
            best = found[0]
            words = {
                "n": len(found),
                "show": self._show(best),
                "name": self._name(best),
                "price": f.inr(best["price"]),
                "off": self._off(best),
            }
            if len(found) >= 2:
                second = found[1]
                line = self._said(
                    "fit_two",
                    show2=self._show(second),
                    name2=self._name(second),
                    price2=f.inr(second["price"]),
                    **words,
                )
            else:
                line = self._said("fit_one", **words)
            say(f"{line} {self._next_step(found, s)}")
            return " ".join([screen, *notes, *detail])
        near = self._nearest(s)
        if near is None:
            say(self._said("none"))
            return " ".join([screen, *notes, "Nothing is close; you offered to loosen one thing."])
        what, x = near
        if what == "budget" and s.price_max is not None:
            say(
                self._said(
                    "over", budget=f.inr(s.price_max), name=self._name(x), price=f.inr(x["price"])
                )
            )
            offer = "the nearest piece over their budget, and asked whether to raise it"
        else:
            say(
                self._said(
                    "except",
                    name=self._name(x),
                    price=f.inr(x["price"]),
                    what=MISSES[what][self.lang],
                )
            )
            offer = f"the nearest piece, which misses only {MISSES[what]['en']}, and asked whether to include such pieces"
        return " ".join(
            [
                screen,
                f"Nothing fits; you offered {offer} (it is not on screen; the filter stays as they said until they agree).",
                *notes,
                "DETAIL:",
                self._row(x),
            ]
        )

    @needs_result_now
    async def product_facts(self, request: ProductRef) -> str:
        """Everything the catalogue says about one product, to answer a question about it."""
        p = f.product(request.product_id)
        if p is None:
            return f"No product {request.product_id}."
        chart = f.chart_of(p)
        owe(
            self._said(
                "facts",
                name=self._name(p),
                price=f.inr(p["price"]),
                off=self._off(p),
                colour=p["colour"],
                stock=self._stock(p),
            )
        )
        return (
            "SAY: answer just what they asked, in two short sentences, then nudge. FACTS: "
            + self._row(p)
            + f". Season {p['season']}, year {p['year']}."
            + (f" Model: {p['model']}." if p.get("model") else "")
            + (f" Size chart: {chart['title']}." if chart else "")
            + f" {f.POLICY['delivery']['summary']}"
        )

    async def open_product(self, request: ProductRef) -> str:
        """Open one product's page, for "show me that one" or "tell me more". Say
        only a few words before calling it: it is described for you; then you are
        its size and fit advisor."""
        p = f.product(request.product_id)
        if p is None:
            say(self._said("which_product"))
            return f"No product {request.product_id}."
        if self.path != f"/p/{p['id']}":
            self._send("site.go", {"path": f"/p/{p['id']}"})
        self.path = f"/p/{p['id']}"
        self.job, self.product_id = "fit", p["id"]
        words = {"name": self._name(p), "price": f.inr(p["price"]), "off": self._off(p)}
        if not f.any_stock(p):
            say(self._said("sold_out"))
        elif p["scale"] == "one":
            self.pending = Pending("add", self.turns, p["id"], p["sizes"][0][0])
            say(self._said("open_one", **words))
        else:
            say(self._said("open", stock=self._stock(p), **words))
        return f"Opened {p['id']}; you described it. You are now its size and fit advisor. FACTS: {self._row(p)}"

    async def compare_products(self, request: CompareRequest) -> str:
        """Put two to four products side by side. Say only a few words before
        calling it: which is the better buy is said for you."""
        xs = [p for i in request.product_ids if (p := f.product(i))]
        if len(xs) < 2 or len(xs) > 4 or len(xs) < len(request.product_ids):
            say(self._said("which_two"))
            return "Compare needs two to four product ids from the screen."
        self._send("compare.show", {"ids": [str(p["id"]) for p in xs]})
        best_off = max(xs, key=lambda p: (f.discount_pct(p), -p["price"]))
        cheapest = min(xs, key=lambda p: (p["price"], p["rank"]))
        if f.discount_pct(best_off) >= 10 and f.discount_pct(best_off) > min(
            f.discount_pct(p) for p in xs
        ):
            pick = best_off
            why = self._said("why_discount", pct=f.discount_pct(pick), price=f.inr(pick["price"]))
        elif len({p["price"] for p in xs}) > 1:
            pick = cheapest
            others = [p["price"] for p in xs if p is not pick]
            why = self._said(
                "why_cheaper", price=f.inr(pick["price"]), diff=f.inr(min(others) - pick["price"])
            )
        else:
            pick = cheapest
            why = self._said("why_price", price=f.inr(pick["price"]))
        say(self._said("compare", name=self._name(pick), why=why))
        return (
            "Side by side; you named the better buy and asked which they like. DETAIL: "
            + " | ".join(self._row(p) for p in xs)
        )

    async def save_to_wishlist(self, request: WishRequest) -> str:
        """Save a product to the wishlist, or take it off."""
        p = f.product(request.product_id)
        if p is None:
            return f"No product {request.product_id}."
        if request.on and p["id"] not in self.wishlist:
            self.wishlist.append(p["id"])
        if not request.on and p["id"] in self.wishlist:
            self.wishlist.remove(p["id"])
        self._send("wishlist.set", {"product_id": str(p["id"]), "on": request.on})
        landed(*LANDED["wishlist" if request.on else "unwish"][self.lang])
        return f"{p['id']} {'on' if request.on else 'off'} the wishlist"

    def _offer_add(self, p: dict[str, Any], size: str | None, qty: int = 1) -> str:
        """Hold an add for the shopper's yes and ask it; the tool's result."""
        if not f.any_stock(p):
            say(self._said("sold_out"))
            return f"{p['id']} is sold out in every size; you offered something similar."
        if p["scale"] == "one":
            label = p["sizes"][0][0]
            self.pending = Pending("add", self.turns, p["id"], label, qty)
            say(self._said("propose_one", name=self._name(p)))
            return f"Held: {p['id']} ({label}) for their yes. Nothing is added until they say yes."
        if not size:
            say(self._said("which_size", sizes=self._and(f.sizes_in_stock(p))))
            return f"You asked which size; in stock: {', '.join(f.sizes_in_stock(p))}."
        label = f.size_label(p, size)
        if label is None:
            sizes = [lb for lb, _ in p["sizes"]]
            say(self._said("no_size", size=size, sizes=self._and(sizes)))
            return f"{p['id']} has no size {size}; sizes: {', '.join(sizes)}."
        if not f.in_stock(p, label):
            alt = f.nearest_in_stock(p, label)
            if alt is None:
                say(self._said("sold_out"))
                return f"{p['id']} is sold out."
            self.pending = Pending("add", self.turns, p["id"], alt, qty)
            if self.path == f"/p/{p['id']}":
                self._send("product.size", {"product_id": str(p["id"]), "size": alt})
            say(self._said("oos_alt", size=label, alt=alt))
            return f"Size {label} is out of stock; you offered {alt}, held for their yes."
        self.pending = Pending("add", self.turns, p["id"], label, qty)
        if self.path == f"/p/{p['id']}":
            self._send("product.size", {"product_id": str(p["id"]), "size": label})
        say(self._said("propose", name=self._name(p), size=label))
        return f"Held: {p['id']} in {label} for their yes. Nothing is added until they say yes."

    async def propose_add(self, request: ProposeRequest) -> str:
        """Offer to add a product in a size to the bag: it asks them to confirm, and
        their yes adds it. Say only a few words before calling it."""
        p = f.product(request.product_id)
        if p is None:
            say(self._said("add_first"))
            return f"No product {request.product_id}."
        return self._offer_add(
            p, request.size or self.size_picked.get(p["id"]), max(1, request.qty)
        )

    async def add_to_bag(self, request: YesRequest) -> str:
        """Add the held product to the bag. Only after they just said yes to it."""
        p = self.pending
        if p is None or p.kind != "add":
            return "Nothing is held. Offer the product and size first (propose_add)."
        if not request.shopper_said_yes or p.turn >= self.turns:
            return "Not added: ask them to confirm first and wait for their yes."
        landed(self._confirmed(p))
        return "added; the page answers"

    def _confirmed(self, p: Pending) -> str:
        """Their yes to what was held: the move it sends and the line said while it goes."""
        self.pending = None
        x = f.product(p.product_id)
        if p.kind == "add" and x is not None and p.size is not None:
            ref = self._send("bag.add", {"product_id": str(x["id"]), "size": p.size, "qty": p.qty})
            self._flights[ref] = p
            self.append_note(
                f"[They said yes: adding {x['id']} in {p.size} to the bag. Do not add it again.]"
            )
            if x["scale"] == "one":
                return self._said("adding_one", name=self._name(x))
            return self._said("adding", name=self._name(x), size=p.size)
        if p.kind == "note" and x is not None and p.size is not None:
            self._send(
                "bag.gift", {"product_id": str(x["id"]), "size": p.size, "on": True, "note": p.note}
            )
            self.append_note(f"[They said yes: the gift note {p.note!r} is set on {x['id']}.]")
            return self._said("wrap_done")
        if p.kind == "cancel" and p.order_id:
            o = self._order(p.order_id)
            self._send("orders.cancel_open", {"order_id": p.order_id})
            self.append_note(
                f"[They said yes: the cancel dialog for {p.order_id} is open; they press Cancel order.]"
            )
            return self._said(
                "cancel_open", id=p.order_id, payment=self._payment(o["payment"] if o else "")
            )
        if p.kind == "unused" and p.order_id and x is not None:
            self.ret.update({"unused": True, "tags": True})
            self._send(
                "returns.fill",
                {"order_id": p.order_id, "product_id": str(x["id"]), "unused": True, "tags": True},
            )
            self.append_note(
                f"[They said the {x['name']} is unused with tags on: both ticked. They press Submit return.]"
            )
            return self._said("return_ticked")
        return self._said("which_product")

    async def open_page(self, request: PageRequest) -> str:
        """Open another page of the store."""
        page, _ = _canonical(request.page)
        ok = page in (
            "/",
            "/shop",
            "/wishlist",
            "/bag",
            "/checkout",
            "/orders",
            "/returns",
            "/gifts",
            "/about",
        ) or page.startswith(("/shop/", "/compare"))
        if not ok:
            return "Not a page here. Pages: /, /shop, /shop/<dept>, /wishlist, /bag, /checkout, /orders, /returns, /gifts, /about."
        self._send(
            "site.go", {"path": request.page if request.page.startswith("/compare") else page}
        )
        landed(*LANDED["open"][self.lang])
        return f"opening {page}"

    async def guide_checkout(self, request: CheckoutRequest) -> str:
        """Ring one checkout section the shopper fills in themselves (their name and
        phone, the address, payment) or the Place order button. Fills nothing."""
        if self.bag_count == 0 and not self.bag_lines:
            say(self._said("bag_empty"))
            return "The bag is empty; nothing to check out."
        if self.path != "/checkout":
            self._send("site.go", {"path": "/checkout"})
            self.path = "/checkout"
        self._send("checkout.focus", {"field": request.field})
        say(self._said(f"checkout_{request.field}"))
        return f"Ringed {request.field}; they type it themselves. Filled so far: {self.checkout or 'nothing'}."

    # ─── Fit ────────────────────────────────────────────────────────────

    async def size_advice(self, request: SizeAdviceRequest) -> str:
        """Find their size in this product: fills the Find my size panel with what
        they said and, with their usual size, recommends one from its sizes, cut and
        stock. Say only a few words before calling it: the size is said for you."""
        p = self._product(request.product_id, default=self.product_id)
        if p is None:
            say(self._said("which_product"))
            return "Which product? Open it first."
        if p["scale"] == "one":
            self.pending = Pending("add", self.turns, p["id"], p["sizes"][0][0])
            say(self._said("fit_one_size"))
            return "One size: nothing to pick; you offered to add it."
        inputs = self.fit_inputs.setdefault(p["id"], {})
        said = request.model_dump(exclude={"product_id"}, exclude_none=True)
        inputs.update(said)
        fill = {
            "product_id": str(p["id"]),
            **{k: inputs[k] for k in ("height_cm", "usual_size", "fit") if k in inputs},
        }
        usual = inputs.get("usual_size")
        if not usual:
            if said:
                self._send("fit.fill", fill)
            say(self._said("ask_usual" if inputs.get("fit") else "ask_usual_fit"))
            return f"You asked their usual size. Sizes of {p['id']}: {', '.join(lb for lb, _ in p['sizes'])}."
        answer = f.recommend(p, str(usual), inputs.get("fit"), inputs.get("height_cm"))
        self._send("fit.fill", fill)
        if answer is None:
            if f.base_size(p, str(usual)) is None:
                labels = [lb for lb, _ in p["sizes"]]
                say(self._said("no_convert", usual=usual, sizes=self._and(labels)))
                return f"{usual} does not convert to this product's sizes; you asked which of its sizes they wear."
            say(self._said("sold_out"))
            return "Nothing near their size is in stock."
        key = f"why_{answer.why}"
        reason = (
            self._said(key, cut=CUT[answer.cut][self.lang])
            if answer.why == "same"
            else self._said(key)
        )
        args: dict[str, Any] = {"product_id": str(p["id"]), "size": answer.size, "reason": reason}
        if answer.wanted:
            args["wanted"] = answer.wanted
        self._send("fit.recommend", args)
        self.size_picked[p["id"]] = answer.size
        self.pending = Pending("add", self.turns, p["id"], answer.size)
        if answer.wanted:
            say(self._said("fit_pick_oos", wanted=answer.wanted, size=answer.size))
        else:
            say(self._said("fit_pick", size=answer.size, reason=reason))
        return (
            f"Recommended {answer.size} for {p['id']} (usual {usual}, fit {inputs.get('fit') or 'regular'}, "
            f"cut {answer.cut}, steps {answer.steps}"
            + (f"; {answer.wanted} is out of stock" if answer.wanted else "")
            + f"); selected on screen and offered to add it, held for their yes. In stock: {', '.join(f.sizes_in_stock(p))}."
        )

    async def size_chart(self, request: SizeChartRequest) -> str:
        """Open the product's size chart, ringing a size's row if given. Say only a
        few words before calling it: the row is read for you."""
        p = self._product(request.product_id, default=self.product_id)
        if p is None:
            say(self._said("which_product"))
            return "Which product?"
        chart = f.chart_of(p)
        if chart is None:
            say(self._said("chart_none", sizes=self._and([lb for lb, _ in p["sizes"]])))
            return f"{p['id']} has no size chart."
        label = f.size_label(p, request.size) if request.size else None
        args: dict[str, Any] = {"product_id": str(p["id"])}
        if label:
            args["size"] = label
        self._send("size_chart.open", args)
        row = f.chart_row(p, label) if label else None
        if row is None:
            say(self._said("chart_open"))
        else:
            unit = chart["unit"]
            unit_word = ("इंच" if self.lang == "hi" else "inches") if unit == "in" else unit
            cols = self._and(
                [f"{c.lower()} {v}" for c, v in zip(chart["columns"][1:], row[1:], strict=False)]
            )
            say(self._said("chart_row", size=label, cols=f"{cols} {unit_word}"))
        rows = "; ".join(" ".join(r) for r in chart["rows"])
        return f"{chart['title']} ({chart['unit']}): {' | '.join(chart['columns'])}: {rows}. {chart['how']}"

    async def pick_size(self, request: PickSizeRequest) -> str:
        """Select a size they named on the product page, and offer to add it."""
        p = self._product(request.product_id, default=self.product_id)
        if p is None:
            say(self._said("which_product"))
            return "Which product?"
        label = f.size_label(p, request.size)
        if label is None:
            sizes = [lb for lb, _ in p["sizes"]]
            say(self._said("no_size", size=request.size, sizes=self._and(sizes)))
            return f"No size {request.size}; sizes: {', '.join(sizes)}."
        if not f.in_stock(p, label):
            return self._offer_add(p, label)
        self._send("product.size", {"product_id": str(p["id"]), "size": label})
        self.size_picked[p["id"]] = label
        self.pending = Pending("add", self.turns, p["id"], label)
        say(self._said("picked", size=label))
        return f"Selected {label}; you offered to add it, held for their yes."

    # ─── Gifts ──────────────────────────────────────────────────────────

    def _brief_line(self) -> str:
        g = self.gift
        budget = (
            "not asked yet"
            if g.budget_max is None
            else "no limit"
            if g.budget_max == 0
            else f.inr(g.budget_max)
        )
        bits = [f"for {g.recipient or '?'}", f"occasion {g.occasion or '?'}", f"budget {budget}"]
        if g.size:
            bits.append(f"size {g.size}")
        if g.colours:
            bits.append(f"colours {', '.join(g.colours)}")
        if g.patterns:
            bits.append(f"patterns {', '.join(g.patterns)}")
        if g.material:
            bits.append(f"material {g.material}")
        return ", ".join(bits)

    def _gift_reason(self, p: dict[str, Any]) -> str:
        g = self.gift
        why = GIFT_WHY
        if any(c.lower() == p["colour"].lower() for c in g.colours):
            return why["colour"][self.lang].format(colour=p["colour"])
        words = f"{p['name']} {' '.join(str(v) for v in (p.get('attrs') or {}).values())}".lower()
        hit = next(
            (
                x
                for x in [*g.patterns, *([g.material] if g.material else [])]
                if x and x.lower() in words
            ),
            None,
        )
        if hit:
            return why["match"][self.lang].format(what=hit.lower())
        if f.festive(g.occasion) and p["usage"] == "Ethnic":
            return why["festive"][self.lang].format(occasion=g.occasion)
        if f.discount_pct(p) >= 10:
            return why["discount"][self.lang].format(pct=f.discount_pct(p))
        return why["popular"][self.lang].format(type=f.type_label(p["type"]).lower())

    async def gift_brief(self, request: GiftBriefRequest) -> str:
        """Fill the gift brief with what they just said; ask the next question, or,
        once it knows who, the occasion and the budget, show a shortlist with a
        reason for each. Say only a few words before calling it."""
        heard = self._heard_recent[::-1]
        budgets: dict[str, float | None] = {"budget_max": request.budget_max}
        if (why := implausible(budgets, heard)) is not None:
            amount = confirm_back(budgets, heard)
            say(
                self._said("budget_check", amount=f.inr(amount))
                if amount is not None
                else self._said("budget_again")
            )
            return why
        g = self.gift
        brief: dict[str, Any] = {}
        notes: list[str] = []
        if request.recipient:
            r = f.recipient_of(request.recipient)
            if r is None:
                notes.append(f"Recipients: {', '.join(f.GIFTS['recipients'])}; pick the nearest.")
            else:
                g.recipient = brief["recipient"] = r
        if request.occasion:
            o = f.occasion_of(request.occasion) or _cap(request.occasion.strip())
            g.occasion = brief["occasion"] = o
        if request.no_budget:
            g.budget_max = brief["budget_max"] = 0
        elif request.budget_max is not None:
            g.budget_max = brief["budget_max"] = int(request.budget_max)
        if request.size:
            g.size = brief["size"] = self._sizes_said([request.size])[0]
        if request.colours:
            cs = [c for c in (f.match_colour(x) for x in request.colours) if c]
            g.colours = brief["colours"] = cs or [_cap(x) for x in request.colours]
        if request.patterns:
            g.patterns = brief["patterns"] = [_cap(x) for x in request.patterns]
        if request.material:
            g.material = brief["material"] = _cap(request.material)
        if self.path != "/gifts":
            self._send("site.go", {"path": "/gifts"})
            self.path, self.job = "/gifts", "gifts"
        if brief:
            self._send("gifts.brief", brief)
        if not g.recipient and not g.occasion:
            say(self._said("gift_ask_both"))
            return (
                f"Brief: {self._brief_line()}. You asked who it is for and the occasion. "
                + " ".join(notes)
            )
        if not g.recipient:
            say(self._said("gift_ask_recipient"))
            return f"Brief: {self._brief_line()}. You asked who it is for. " + " ".join(notes)
        if not g.occasion:
            say(self._said("gift_ask_occasion"))
            return f"Brief: {self._brief_line()}. You asked the occasion."
        if g.budget_max is None:
            say(self._said("gift_ask_budget"))
            return f"Brief: {self._brief_line()}. You asked about the budget."
        picks = f.pick_gifts(g)
        if not picks:
            say(self._said("gift_none"))
            return f"Brief: {self._brief_line()}. Nothing fits; you offered to widen the budget or include clothes with a size."
        reasons = [self._gift_reason(p) for p in picks]
        self.gift_ids = [p["id"] for p in picks]
        self._send(
            "gifts.show",
            {"ids": [str(p["id"]) for p in picks], "reasons": [_cap(r) for r in reasons]},
        )
        a = picks[0]
        if len(picks) >= 2:
            b = picks[1]
            say(
                self._said(
                    "gift_show",
                    n=len(picks),
                    show=self._show(a),
                    name=self._name(a),
                    price=f.inr(a["price"]),
                    reason=reasons[0],
                    show2=self._show(b),
                    name2=self._name(b),
                    price2=f.inr(b["price"]),
                    reason2=reasons[1],
                )
            )
        else:
            say(
                self._said(
                    "gift_show_one",
                    show=self._show(a),
                    name=self._name(a),
                    price=f.inr(a["price"]),
                    reason=reasons[0],
                )
            )
        return (
            f"Brief: {self._brief_line()}. Shortlist on screen, best first (you named the first two): "
            + " | ".join(f"{self._row(p)} — {r}" for p, r in zip(picks, reasons, strict=True))
        )

    def _bag_line(self, pid: int, size: str | None) -> str | None:
        """The bag line's size for ``pid`` (and ``size`` when given), as reported."""
        for raw in self.bag_lines:
            parsed = f.parse_bag_line(raw)
            if parsed and parsed[0] == pid and (size is None or parsed[1] == size):
                return parsed[1]
        return None

    async def gift_wrap(self, request: GiftWrapRequest) -> str:
        """Gift wrap a piece in the bag (₹49 an item), with the note they dictated:
        the note is read back once and set on their yes. Say only a few words before
        calling it."""
        p = f.product(request.product_id)
        if p is None:
            say(self._said("which_product"))
            return f"No product {request.product_id}."
        size = self._bag_line(p["id"], f.size_label(p, request.size) if request.size else None)
        if size is None:
            if p["scale"] == "one" or request.size:
                self._offer_add(p, request.size)
            say(self._said("wrap_not_in_bag", name=self._name(p)))
            return f"{p['id']} is not in the bag; you offered to add it first."
        if not request.on:
            self._send("bag.gift", {"product_id": str(p["id"]), "size": size, "on": False})
            say(self._said("wrap_off", name=self._name(p)))
            return "Gift wrap off."
        note = (request.note or "").strip()
        limit = int(f.POLICY["gift_wrap"]["note_max"])
        if note and len(note) > limit:
            say(self._said("note_long", max=limit))
            return f"The note is {len(note)} characters; the most is {limit}. You asked for a shorter one."
        if note:
            self.pending = Pending("note", self.turns, p["id"], size, note=note)
            say(self._said("wrap_check", note=note))
            return "You read the note back; it is set on their yes."
        self._send("bag.gift", {"product_id": str(p["id"]), "size": size, "on": True})
        say(self._said("wrap_on", name=self._name(p)))
        return f"Gift wrap on for {p['id']} ({size}); you asked if they want a note."

    # ─── Orders ─────────────────────────────────────────────────────────

    def _orders(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for o in f.resolve_orders():
            out.append({**o, "status": self.order_status.get(o["id"], o["status"])})
        t = f.today()
        for po in self.placed:
            if any(o["id"] == po["id"] for o in out):
                continue
            out.append(
                {
                    "id": po["id"],
                    "status": self.order_status.get(po["id"], "placed"),
                    "placed": t,
                    "eta": f.add_days(t, int(f.POLICY["delivery"]["days_max"])),
                    "delivered": None,
                    "payment": "",
                    "items": [],
                    "courier": None,
                    "events": [],
                }
            )
        return out

    def _order(self, ref: str | None) -> dict[str, Any] | None:
        if not ref:
            return None
        digits = re.sub(r"\D", "", ref)
        return next(
            (o for o in self._orders() if digits and re.sub(r"\D", "", o["id"]) == digits), None
        )

    def _order_row(self, o: dict[str, Any]) -> str:
        items = ", ".join(
            f"{i['product_id']} {p['name'] if (p := f.product(i['product_id'])) else ''} ({i['size']})"
            for i in o["items"]
        )
        dates = f"placed {f.fmt_date(o['placed'])}"
        if o.get("eta") and o["status"] not in ("delivered", "cancelled"):
            dates += f", ETA {f.fmt_date(o['eta'])}"
        if o.get("delivered"):
            dates += f", delivered {f.fmt_date(o['delivered'])}"
        return f"{o['id']} {f.status_label(o['status'])} ({dates}; {items})"

    def _order_said(self, o: dict[str, Any]) -> str:
        """An order as a line names it: its number and its first item."""
        first = next((p for i in o["items"] if (p := f.product(i["product_id"]))), None)
        return f"{o['id']} ({self._name(first)})" if first else o["id"]

    def _status_line(self, o: dict[str, Any]) -> str:
        s = o["status"]
        kw: dict[str, Any] = {"id": o["id"]}
        if s in ("placed", "packed", "shipped"):
            kw["eta"] = self._date(o["eta"]) if o.get("eta") else ""
        if s == "shipped":
            kw["courier"] = (o.get("courier") or {}).get("name", "our courier")
        if s == "delivered":
            kw["date"] = self._date(o["delivered"])
        if s == "cancelled":
            kw["payment"] = self._payment(o.get("payment") or "")
        line = self._said(f"status_{s}", **kw)
        if s == "delivered":
            chk = f.return_check(o, None, self.returned, status=s)
            if chk.ok and chk.closed_on is not None:
                line += self._said("can_return", until=self._date(chk.closed_on))
        return line

    async def find_order(self, request: OrderRef) -> str:
        """Open an order on the orders page and say its status and dates; with no
        order number, name the orders on the way. Say only a few words before
        calling it."""
        orders = self._orders()
        o = self._order(request.order_id or None)
        if o is None:
            active = [
                x
                for x in orders
                if x["status"] in ("placed", "packed", "shipped", "out_for_delivery")
            ]
            listed = [self._order_said(x) for x in (active or orders[:3])]
            if request.order_id:
                say(self._said("order_unknown", id=request.order_id, orders=self._and(listed)))
            elif active:
                say(self._said("order_which", n=len(active), orders=self._and(listed)))
            else:
                say(self._said("order_which_any", orders=self._and(listed)))
            return "Orders: " + "; ".join(self._order_row(x) for x in orders)
        if self.path != "/orders":
            self._send("site.go", {"path": f"/orders?order={o['id']}"})
            self.path, self.job = "/orders", "orders"
        self._send("orders.open", {"order_id": o["id"]})
        self.order_id = o["id"]
        say(self._status_line(o))
        events = "; ".join(f"{f.fmt_date(e['date'])} {e['time']} {e['text']}" for e in o["events"])
        return f"Opened: {self._order_row(o)}. Payment {o['payment']}. Tracking: {events or 'none yet'}. You said its status."

    async def cancel_order(self, request: OrderRef) -> str:
        """Cancel an order: only before dispatch (placed or packed) it opens the
        cancel dialog for them to press Cancel order; once shipped it cannot. Say
        only a few words before calling it."""
        o = self._order(request.order_id or self.order_id)
        if o is None:
            return await self.find_order(OrderRef(order_id=request.order_id))
        self.order_id = o["id"]
        if f.can_cancel(o["status"]):
            if self.path != "/orders":
                self._send("site.go", {"path": f"/orders?order={o['id']}"})
                self.path, self.job = "/orders", "orders"
            self._send("orders.cancel_open", {"order_id": o["id"]})
            say(
                self._said("cancel_open", id=o["id"], payment=self._payment(o.get("payment") or ""))
            )
            return f"The cancel dialog for {o['id']} is open; they press Cancel order themselves. Nothing is cancelled yet."
        if o["status"] in ("shipped", "out_for_delivery"):
            say(self._said("cancel_shipped", id=o["id"]))
            return f"{o['id']} is {o['status']}: it cannot be cancelled (only {', '.join(f.POLICY['cancel_statuses'])}). You offered a return after delivery."
        say(self._said("cancel_nothing", id=o["id"], status=self._status(o["status"])))
        return f"{o['id']} is {o['status']}; nothing to cancel."

    async def delivery_change(self, request: ChangeRequest) -> str:
        """They want to change an order's delivery date or address. Once placed,
        neither can change; this says so plainly and offers what is possible."""
        o = self._order(request.order_id or self.order_id)
        if o is None:
            return await self.find_order(OrderRef(order_id=request.order_id))
        what = self._said(f"what_{request.what}")
        policy = f.POLICY["changes"]["summary"]
        if f.can_cancel(o["status"]):
            self.pending = Pending("cancel", self.turns, order_id=o["id"])
            say(self._said("change_cancellable", what=what))
            return f"Policy: {policy} You offered to open the cancel so they can reorder; held for their yes."
        if o["status"] in ("shipped", "out_for_delivery"):
            eta = self._date(o["eta"]) if o.get("eta") else self._date(f.today())
            say(self._said("change_shipped", what=what, eta=eta))
            return f"Policy: {policy} {o['id']} has shipped: nothing can change."
        say(self._said("change_done", what=what, id=o["id"], status=self._status(o["status"])))
        return f"Policy: {policy}"

    # ─── Returns ────────────────────────────────────────────────────────

    def _return_refusal(
        self, o: dict[str, Any], chk: f.ReturnCheck, p: dict[str, Any] | None
    ) -> str:
        if chk.why == "not_delivered":
            return self._said("return_not_delivered", id=o["id"])
        if chk.why == "window" and chk.delivered and chk.closed_on:
            return self._said(
                "return_window",
                id=o["id"],
                delivered=self._date(chk.delivered),
                closed=self._date(chk.closed_on),
            )
        if chk.why == "fragrance" and p is not None:
            others = [
                x
                for i in o["items"]
                if (x := f.product(i["product_id"])) is not None
                and x["id"] != p["id"]
                and f.return_check(o, x["id"], self.returned, status=o["status"]).ok
            ]
            other = self._said("return_other", name=self._name(others[0])) if others else ""
            return self._said("return_fragrance", name=self._name(p), other=other)
        if chk.why == "already" and p is not None:
            return self._said("return_already", name=self._name(p))
        return self._said("which_product")

    def _return_item(self, o: dict[str, Any], ref: str | None) -> dict[str, Any] | None:
        """The order's item they named, or its only item."""
        ids = [int(i["product_id"]) for i in o["items"]]
        if ref:
            p = f.product(ref)
            return p if p is not None and p["id"] in ids else None
        if self.ret.get("order_id") == o["id"] and self.ret.get("product_id"):
            return f.product(self.ret["product_id"])
        return f.product(ids[0]) if len(ids) == 1 else None

    def _return_order(self, ref: str | None) -> dict[str, Any] | None:
        return self._order(ref or self.ret.get("order_id") or self.order_id)

    def _ask_return_order(self) -> str:
        delivered = [o for o in self._orders() if o["status"] == "delivered"]
        say(
            self._said(
                "return_which_order", orders=self._and([self._order_said(o) for o in delivered])
            )
        )
        return (
            "Delivered orders: "
            + "; ".join(self._order_row(o) for o in delivered)
            + ". You asked which order."
        )

    async def start_return(self, request: ReturnRequest) -> str:
        """Start a return from an order: checks the dates from the data, refuses
        politely when it cannot, or opens the return form and asks which item and
        why. Say only a few words before calling it."""
        o = self._return_order(request.order_id)
        if o is None:
            return self._ask_return_order()
        self.order_id = o["id"]
        chk = f.return_check(o, None, self.returned, status=o["status"])
        if not chk.ok:
            say(self._return_refusal(o, chk, None))
            return f"Not returnable: {self._order_row(o)}. Window {f.POLICY['returns']['window_days']} days from delivery; today {f.fmt_date(f.today())}."
        p = self._return_item(o, request.product_id)
        if self.path != "/returns":
            self._send("site.go", {"path": f"/returns?order={o['id']}"})
            self.path, self.job = "/returns", "returns"
        if p is not None:
            item = f.return_check(o, p["id"], self.returned, status=o["status"])
            if not item.ok:
                self._send("returns.fill", {"order_id": o["id"]})
                self.ret = {"order_id": o["id"]}
                say(self._return_refusal(o, item, p))
                return f"{p['id']} cannot be returned ({item.why})."
            self.ret = {"order_id": o["id"], "product_id": p["id"]}
            self._send("returns.fill", {"order_id": o["id"], "product_id": str(p["id"])})
            say(self._said("return_reason", left=chk.days_left, name=self._name(p)))
            return f"Return form open for {o['id']}, item {p['id']}; you asked the reason. {self._order_row(o)}"
        self.ret = {"order_id": o["id"]}
        self._send("returns.fill", {"order_id": o["id"]})
        items = [self._name(x) for i in o["items"] if (x := f.product(i["product_id"]))]
        say(self._said("return_which_item", left=chk.days_left, items=self._or(items)))
        return f"Return form open for {o['id']}; you asked which item. {self._order_row(o)}"

    async def return_details(self, request: ReturnDetailsRequest) -> str:
        """Fill the return form with the item and the reason they gave; then ask
        them to confirm it is unused with its tags on (ticked only after they say
        so). They press Submit return themselves. Say only a few words before
        calling it."""
        o = self._return_order(request.order_id)
        if o is None:
            return self._ask_return_order()
        chk = f.return_check(o, None, self.returned, status=o["status"])
        if not chk.ok:
            say(self._return_refusal(o, chk, None))
            return "Not returnable."
        p = self._return_item(o, request.product_id)
        if p is None:
            items = [self._name(x) for i in o["items"] if (x := f.product(i["product_id"]))]
            say(self._said("return_which_item", left=chk.days_left, items=self._or(items)))
            return "You asked which item."
        item = f.return_check(o, p["id"], self.returned, status=o["status"])
        if not item.ok:
            say(self._return_refusal(o, item, p))
            return f"{p['id']} cannot be returned ({item.why})."
        if self.ret.get("order_id") != o["id"] or self.ret.get("product_id") != p["id"]:
            self.ret = {"order_id": o["id"], "product_id": p["id"]}
        if request.reason:
            self.ret["reason"] = request.reason
        args: dict[str, Any] = {"order_id": o["id"], "product_id": str(p["id"])}
        if self.ret.get("reason"):
            args["reason"] = self.ret["reason"]
        if self.path != "/returns":
            self._send("site.go", {"path": f"/returns?order={o['id']}"})
            self.path, self.job = "/returns", "returns"
        if not self.ret.get("reason"):
            self._send("returns.fill", args)
            say(self._said("return_reason", left=chk.days_left, name=self._name(p)))
            return "You asked the reason."
        heard = self._heard_recent[-1] if self._heard_recent else ""
        if (
            request.shopper_said_unused_with_tags
            and _unused_said(heard) == "yes"
            and _UNUSED.search(heard)
        ):
            self.ret.update({"unused": True, "tags": True})
            self._send("returns.fill", {**args, "unused": True, "tags": True})
            say(self._said("return_ticked"))
            return "Filled and both ticked (they said so); they press Submit return themselves."
        self._send("returns.fill", args)
        self.pending = Pending("unused", self.turns, p["id"], order_id=o["id"])
        say(self._said("return_confirm", name=self._name(p)))
        return f"Filled the item and the reason; you asked them to confirm unused with tags on. Reference when submitted: {f.return_ref(o['id'], p['id'])}."

    # ─── Kiosk ──────────────────────────────────────────────────────────

    async def kiosk_search(self, request: KioskSearchRequest) -> str:
        """Search the whole catalogue on the kiosk and show the results grid. Say
        only a few words before calling it: the best is said for you."""
        heard = self._heard_recent[::-1]
        budgets: dict[str, float | None] = {"price_max": request.price_max}
        if (why := implausible(budgets, heard)) is not None:
            amount = confirm_back(budgets, heard)
            say(
                self._said("budget_check", amount=f.inr(amount))
                if amount is not None
                else self._said("budget_again")
            )
            return why
        types = [t for t in (f.match_type(v) for v in request.types or []) if t]
        colours = [c for c in (f.match_colour(v) for v in request.colours or []) if c]
        sizes = self._sizes_said(request.sizes or [])
        s = f.Search(
            types=types,
            colours=colours,
            sizes=sizes,
            price_max=request.price_max,
            usage=list(request.usage or []),
            query=request.query,
        )
        genders = list(request.genders or [])
        found = [p for p in f.search(s) if not genders or p["gender"] in genders]
        args: dict[str, Any] = {
            "query": request.query,
            "genders": genders or None,
            "types": types or None,
            "colours": colours or None,
            "sizes": sizes or None,
            "price_max": request.price_max,
            "usage": list(request.usage or []) or None,
        }
        self._send("kiosk.search", args)
        self.kiosk.update(
            {"summary": s.summary(), "count": len(found), "ids": [p["id"] for p in found[:12]]}
        )
        if not found:
            say(self._said("kiosk_none"))
            return "Nothing matches; you offered to loosen one thing."
        best = found[0]
        say(
            self._said(
                "kiosk_found",
                n=len(found),
                show=self._show(best),
                name=self._name(best),
                price=f.inr(best["price"]),
            )
        )
        return f"{len(found)} results on the kiosk, best first: " + " | ".join(
            self._row(p) for p in found[:6]
        )

    async def kiosk_show(self, request: ProductRef) -> str:
        """Open one product full screen on the kiosk, with its QR code. Say only a
        few words before calling it."""
        p = f.product(request.product_id)
        if p is None:
            say(self._said("which_product"))
            return f"No product {request.product_id}."
        self._send("kiosk.show", {"product_id": str(p["id"])})
        self.kiosk["product_id"] = p["id"]
        stock = self._stock(p) if p["scale"] != "one" else ""
        say(
            self._said(
                "kiosk_show",
                name=self._name(p),
                price=f.inr(p["price"]),
                off=self._off(p),
                stock=stock,
            ).replace("  ", " ")
        )
        return f"Open on the kiosk with its QR code: {self._row(p)}"

    async def kiosk_qr(self, request: KioskQrRequest) -> str:
        """Show the big QR code for a product's page, or for the shortlist."""
        p = f.product(request.product_id) if request.product_id else None
        if request.product_id and p is None:
            say(self._said("which_product"))
            return f"No product {request.product_id}."
        self._send("kiosk.qr", {"product_id": str(p["id"])} if p else {})
        say(self._said("kiosk_qr" if p else "kiosk_qr_list"))
        return "QR code on screen."

    async def kiosk_shortlist(self, request: WishRequest) -> str:
        """Add a product to the kiosk shortlist, or take it off."""
        p = f.product(request.product_id)
        if p is None:
            return f"No product {request.product_id}."
        if request.on and p["id"] not in self.kiosk_saved:
            self.kiosk_saved.append(p["id"])
        if not request.on and p["id"] in self.kiosk_saved:
            self.kiosk_saved.remove(p["id"])
        self._send("kiosk.shortlist", {"product_id": str(p["id"]), "on": request.on})
        landed(*LANDED["shortlist" if request.on else "unshortlist"][self.lang])
        return f"Shortlist: {', '.join(map(str, self.kiosk_saved)) or 'empty'}."

    async def call_floor_assistant(self, request: AssistRequest) -> str:
        """Call a floor assistant to the kiosk."""
        self._send("kiosk.assist", {})
        say(self._said("kiosk_assist"))
        return f"Called. {f.STORE['kiosk']['floor_assistant']}"

    # ─── Language and the screen ────────────────────────────────────────

    async def set_language(self, request: LanguageRequest) -> str:
        """Speak and listen in another language for the rest of the call."""
        tag = self.persona.tag(request.language)
        configure_soon(self.session, self._speaking(tag))
        return f"the call is now in {self.persona.language_names[tag]}"

    async def _requested(self, session: Session, tag: str) -> None:
        """The toggle: both legs in one awaited request, then a written line in the
        new language at the next quiet spell."""
        if tag == self.lang or tag not in self.persona.languages:
            return
        was = self.lang
        try:
            await session.configure(self._speaking(tag))
        except RequestRejected as rejected:
            logger.warning("fashio: switch to {} refused: {}", tag, rejected)
            self.lang = was
            self.session.dispatch(LanguageChanged(language=was))
            return
        name = self.persona.language_names[tag]
        self.append_note(f"[They switched the call to {name} on the toggle; speak {name} now.]")
        self._say_soon(lambda: SAID["switched"][tag])

    def _speaking(self, tag: str) -> Config:
        """Both legs in ``tag``, and the page's toggle moved to it."""
        if tag != self.lang:
            self.session.dispatch(LanguageChanged(language=tag))
        self.lang = tag
        logger.info("fashio: language -> {}", tag)
        return Config(
            stt=SttConfig(language=self.persona.language(tag), patience=PATIENCE),
            tts=TtsConfig(voice=self.persona.voice(tag), language=self.persona.language(tag)),
        )

    @needs_result_now
    async def read_screen(self, request: ReadRequest) -> str:
        """Read part of their screen as the page last reported it."""
        mirror = self.stage.mirror
        return mirror.read(request.slice) if mirror is not None else "nothing reported"

    @property
    def tools(self) -> list[Any]:
        return [
            self.search_products,
            self.product_facts,
            self.open_product,
            self.compare_products,
            self.save_to_wishlist,
            self.propose_add,
            self.add_to_bag,
            self.open_page,
            self.guide_checkout,
            self.size_advice,
            self.size_chart,
            self.pick_size,
            self.gift_brief,
            self.gift_wrap,
            self.find_order,
            self.cancel_order,
            self.delivery_change,
            self.start_return,
            self.return_details,
            self.kiosk_search,
            self.kiosk_show,
            self.kiosk_qr,
            self.kiosk_shortlist,
            self.call_floor_assistant,
            self.set_language,
            self.read_screen,
        ]


#: Live calls by session id, for a redial to rejoin (rejoin.py).
REJOIN: Rejoin[FashioBrain] = Rejoin()

__all__ = ["REJOIN", "FashioBrain", "LanguageChanged"]
