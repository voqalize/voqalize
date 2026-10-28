"""CannonHomeBrain — Javier, a voice guide on cannonhome.cl, Cannon Home's store.

The site is Cannon Home's, not ours. A browser extension injects the widget and
a small adapter into cannonhome.cl; the adapter turns each
:class:`~voqalize.sdk.Action` below into a move on the tab in front — the
search box typed into, a listing filtered, a product opened, an item added to
the cart — and every tab reports what it shows as a typed event
(:mod:`.app_events`), whichever of the visitor and Javier moved it. The store
is Magento: a move to another page is a full page load, and the call rejoins
on the new page.

**He never fetches the store.** The brains run where the store's servers do not
answer, and the store's HTML is cached for hours anyway. Prices and stock are
read in the visitor's browser, by the extension, and reach the brain as app
events; the brain keeps them in a mirror and answers from it. The catalogue he
filters (``knowledge/L3/products.json``) has no price and no stock, ever.

**A price is one he just read.** He says a price only when a line from their
screen carries it: the product page (then its live check, which wins), the
listing, the search box's suggestions, a ``check_prices`` read or the cart.
Without one he says he cannot see it right now and opens the product.

**Delivery details, yes; the RUT and the payment, never.** He may add to the
cart and change or take out a line of it (none of that creates an order), take the visitor from the bag to the guest
checkout ("Terminar pedido", then "Comprar como invitado", never a login), and
fill the delivery form with what they tell him: email, name, phone, región,
comuna and address. He never logs in, never asks for, repeats or types a RUT,
a password or card details, and never presses what goes on to the payment or
places the order: those stay the visitor's. The fill request has no field for
any of them, so they cannot be sent; the extension refuses those fields and
buttons again on the page.

**Every move is a Stage move.** A move on the page — a cue in his reply or a
tool's move — has a class that decides how it is sent and what he hears of
it, is ringed on the page before it acts, and is answered by exactly one
``stage_result`` (:mod:`voqalize.sdk.stage`).

**Never block on the UI.** A tool's move is sent and the tool returns at once;
the page's result comes back, and he talks it through in the next short quiet
spell, with tools off. One move at a time: a move asked for while another is
under way waits for that one to land.

**The screen follows his voice.** He writes his moves into the reply as cues
(``{page: /politicas-de-despacho}``, ``{filter: Tamaño | King}``), at the
start of the sentence they belong to; Stage takes them out of the speech, the
brain checks them against the site, and the page makes each as the voice
reaches its sentence. A filter written that way is applied as it is said, and
its result is a line for his next turn; only a filter that failed is talked
through.

**Spanish or English, as the visitor chose or speaks.** The call opens in
Spanish, the store's language, and moves both legs of the call together.
"""

from __future__ import annotations

import asyncio
import dataclasses
import math
import random
import re
import time
from collections.abc import AsyncGenerator, Callable, Iterable
from datetime import date, datetime
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Annotated, Any, Literal
from zoneinfo import ZoneInfo

from loguru import logger
from openai import AsyncOpenAI
from pydantic import BaseModel, BeforeValidator, Field
from voqalize_demos import (
    PATIENCE,
    FallbackLine,
    configure_soon,
    landed,
    needs_result_now,
    say_line,
)
from voqalize_demos.language_hold import HELD_NOTE, heard_language, holds_spanish, may_write_english

from voqalize.sdk import (
    Action,
    Finalize,
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
from voqalize.sdk.stage import (
    LANDING_FLOOR_MS,
    POLICY,
    RESULT_TIMEOUTS,
    Dropped,
    Landing,
    Move,
    MoveClass,
    RawCue,
    Refused,
    Stage,
    StageHello,
    StageProgress,
    StageResult,
    landed_ask,
)
from voqalize.sdk.voice import ToolChoice
from voqalize.sdk.wire import Config, IdleConfig, SttConfig, TtsConfig, Voice

from . import knowledge as kb
from .app_events import (
    CANNONHOME_EVENTS,
    CannonHomeEvent,
    CartItem,
    CartState,
    CheckoutState,
    LanguageRequested,
    ListingShown,
    PageChanged,
    PricesRead,
    ProductShown,
    SearchSuggest,
    TabInfo,
    TabsChanged,
)
from .knowledge import (
    SIZE_LABELS,
    TOPIC_IDS,
    Category,
    Knowledge,
    Product,
    canonical_path,
    color_stem,
    fold,
    material_key,
    norm,
    size_key,
)

AGENT_NAME = "Javier"

#: GPT-6.1 Terra at low reasoning, for cost: OpenAI caches every prompt over
#: 1,024 tokens, where Gemini 3.8 Flash cached nothing under about 16k, so most
#: of each turn's input is read from the cache.
MODEL = "gpt-6.1-terra"
REASONING = "low"
#: Cannon Home is in Chile: "hoy" and "mañana" are Santiago's.
TIMEZONE = ZoneInfo("America/Santiago")

# ─── Voice and timing ──────────────────────────────────────────────────────────

#: Javier's voice: one man, recorded once in English and once in Spanish.
VOICE = Voice.OMNIVOICE_JAVIER

_IDLE_MS = 20_000
_IDLE_NUDGES = 2
#: The idle window while a result the page produced waits to be talked
#: through: short, since the voice has stopped (dev call ed264469: two
#: seconds here, then the model's first token, was most of the 15 s from the
#: page landing to his voice).
_TALK_THROUGH_MS = 600
#: The idle window once a written line leads (a confirmed move the page
#: confirmed, a listing or product that landed): said as soon as the floor is
#: free, with no model request before it.
_DONE_MS = LANDING_FLOOR_MS
#: A visitor thinking aloud about what they need pauses mid-sentence.
CANNONHOME_PATIENCE = PATIENCE + 2

# ─── Language ──────────────────────────────────────────────────────────────────

Lang = Literal["en", "es"]
#: The store is Spanish (Chile), so the call opens in Spanish.
OPENING: Lang = "es"
LANGUAGE_NAMES: dict[Lang, str] = {"en": "English", "es": "Spanish"}

TOGGLE_CONFIRM: dict[Lang, str] = {
    "en": "Sure, let's continue in English.",
    "es": "Claro, seguimos en español.",
}

# The small words of each language, plus the store's own nouns: a sentence that
# uses several of one and none of the other is in that one. Brand and size
# words both languages say ("king", "Cannon") are in neither.
_SPANISH_WORDS = frozenset(
    # A word list reads as words, so it stays a split string.
    """que qué de del el los las la una unas unos por para con como cómo cuánto cuanto
    cuánta cuesta cuestan puedes puede podrías quiero quisiera necesito tengo tienes
    tiene hay hola gracias sí está están estoy es eso esto esta este estos pero muy
    también hablar habla hablas hablemos español castellano usted ustedes mi mis tu tus
    su sus nosotros vale bueno claro dónde donde cuál cual cuándo cuando precio precios
    enséñame muéstrame dime explícame funciona hace hacer hora horas busco buscando
    sábanas sabanas sábana toalla toallas almohada almohadas plumón plumones cama camas
    carro bolsa despacho envío tienda tiendas tamaño hilos algodón blanco blancas
    agrega agrégalo agregar ábreme muestra otra otro otras otros
    """.split()  # noqa: SIM905
)
#: The store's nouns, which are also its products' names: "Liso Blanco" in an
#: English reply is a product, not Spanish (dev, 2026-10-28: one such name
#: switched the call to Spanish twice). Only the visitor's words count them.
_STORE_NOUNS = frozenset(
    """sábanas sabanas sábana toalla toallas almohada almohadas plumón plumones cama camas
    carro bolsa despacho envío tienda tiendas tamaño hilos algodón blanco blancas
    """.split()  # noqa: SIM905
)
_SPANISH_SMALL = _SPANISH_WORDS - _STORE_NOUNS
_ENGLISH_WORDS = frozenset(
    """the is are was what how can could you your i i'm it it's this that these those do
    does show me my we our for with about and of to have has there here please want
    would like tell sure yes okay right of course let's sheets towel towels pillow duvet
    """.split()  # noqa: SIM905
)
_WRITTEN_ENOUGH = 60
_SENTENCE_END = re.compile(r"[.?!](?:\s|$)")
_SPANISH_MARKS = re.compile(r"[¿¡ñáéíóú]", re.IGNORECASE)
_LETTERS = re.compile(r"[\wáéíóúüñ']+")
#: A cue is the site's own words, in Spanish whatever he speaks.
_CUE_TEXT = re.compile(r"\{[^{}]*\}?")


def name_words(names: Iterable[str]) -> frozenset[str]:
    """The words of ``names`` (products, categories) that say nothing of the
    language around them: all but the small words of either language."""
    words = {w for n in names for w in _LETTERS.findall(n.lower())}
    return frozenset(words - _SPANISH_SMALL - _ENGLISH_WORDS)


def language_of(
    text: str,
    *,
    sure: bool = True,
    names: Iterable[str] = (),
    vocabulary: frozenset[str] = frozenset(),
) -> Lang | None:
    """The language ``text`` is plainly in, or ``None``. ``sure`` is for what
    the visitor said: Spanish needs two of its words (or its marks and one),
    English three of its own and none of Spanish's. His own lines (not
    ``sure``) take one Spanish small word, never a store noun.

    A name is not a language: ``names`` (what is on their screen, in their
    cart) are taken out of ``text`` first, and their words and those of
    ``vocabulary`` (the catalogue's names) neither count nor bring marks."""
    text = _CUE_TEXT.sub(" ", text)
    for name in sorted({n for n in names if n.strip()}, key=len, reverse=True):
        text = re.sub(re.escape(name), " ", text, flags=re.IGNORECASE)
    ignored = name_words(names) | vocabulary
    kept = [w for w in _LETTERS.findall(text.lower()) if w not in ignored]
    found = set(kept)
    marks = bool(_SPANISH_MARKS.search(" ".join(kept))) or "¿" in text or "¡" in text
    es = len(found & (_SPANISH_WORDS if sure else _SPANISH_SMALL)) + (1 if marks else 0)
    en = len(found & _ENGLISH_WORDS)
    if es >= (2 if sure else 1) and es > en:
        return "es"
    if en >= (3 if sure else 2) and es == 0:
        return "en"
    return None


# ─── Words respelled for the voice ─────────────────────────────────────────────
#
# Latin America says "vi-DE-o"; this Spanish voice read plain "video" as Spain's
# "VÍ-deo" one time in three on dev (2026-10-21, clini), and "bidéo" right every
# time. So in Spanish the voice is handed "bidéo", the page's word anchors follow
# (``_anchor_for_voice``), and what comes back as heard is spelled "video" again
# before it reaches the model (``on_finalize``).
#
# "Cannon Home" is left as written: nothing yet says either voice says it
# wrong. The store writes it in capitals ("CANNON HOME"), and a voice may spell
# capitals out letter by letter, so capitals become a word — in both languages,
# only the case, so the page's lower-cased anchors are untouched. If the Spanish
# voice is heard stressing it wrongly, respell it in ``_ES_RESPELL`` (Spanish
# voice only), with its undoing in ``_ES_UNSPELL``: tuned on dev, by ear.

_VIDEO_TO_VOICE = re.compile(r"\b([Vv])[ií]deo(s?)\b")
_VIDEO_FROM_VOICE = re.compile(r"\b([Bb])idéo(s?)\b")
_CAPS_TO_VOICE: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bCANNON HOME\b"), "Cannon Home"),
    (re.compile(r"\bCANNON\b"), "Cannon"),
)
#: Spanish voice only: (written, as the voice must read it). Empty until heard wrong.
_ES_RESPELL: tuple[tuple[re.Pattern[str], str], ...] = ()
_ES_UNSPELL: tuple[tuple[re.Pattern[str], str], ...] = ()


def names_for_the_voice(text: str) -> str:
    """``text`` with the store's capitalised name as a word the voice says."""
    for rx, said in _CAPS_TO_VOICE:
        text = rx.sub(said, text)
    return text


def for_the_voice(text: str) -> str:
    """Spanish ``text`` as the Spanish voice must read it."""
    text = _VIDEO_TO_VOICE.sub(
        lambda m: ("B" if m.group(1) == "V" else "b") + "idéo" + m.group(2),
        names_for_the_voice(text),
    )
    for rx, said in _ES_RESPELL:
        text = rx.sub(said, text)
    return text


def from_the_voice(text: str) -> str:
    """What the voice said, spelled as Latin America writes it."""
    text = _VIDEO_FROM_VOICE.sub(
        lambda m: ("V" if m.group(1) == "B" else "v") + "ideo" + m.group(2), text
    )
    for rx, written in _ES_UNSPELL:
        text = rx.sub(written, text)
    return text


def _anchor_for_voice(at: str, lang: Lang = "es") -> str:
    """A cue's anchor — the spoken text that follows it — spelled as the
    voice will say it, so the page finds it in what it hears."""
    return for_the_voice(at) if lang == "es" else names_for_the_voice(at)


def _chosen_note(language: Lang, how: str) -> str:
    name = LANGUAGE_NAMES[language]
    return (
        f"[The visitor chose {name} {how}. Answer in {name} from now on, whatever "
        "language they speak to you, until they ask for the other one.]"
    )


# ─── Pesos, as said ────────────────────────────────────────────────────────────

_ES_UNITS = [
    "cero",
    "uno",
    "dos",
    "tres",
    "cuatro",
    "cinco",
    "seis",
    "siete",
    "ocho",
    "nueve",
    "diez",
    "once",
    "doce",
    "trece",
    "catorce",
    "quince",
    "dieciséis",
    "diecisiete",
    "dieciocho",
    "diecinueve",
    "veinte",
    "veintiuno",
    "veintidós",
    "veintitrés",
    "veinticuatro",
    "veinticinco",
    "veintiséis",
    "veintisiete",
    "veintiocho",
    "veintinueve",
]
_ES_TENS = {3: "treinta", 4: "cuarenta", 5: "cincuenta", 6: "sesenta", 7: "setenta"} | {
    8: "ochenta",
    9: "noventa",
}
_ES_HUNDREDS = {
    1: "ciento",
    2: "doscientos",
    3: "trescientos",
    4: "cuatrocientos",
    5: "quinientos",
    6: "seiscientos",
    7: "setecientos",
    8: "ochocientos",
    9: "novecientos",
}
_EN_UNITS = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
_EN_TENS = {2: "twenty", 3: "thirty", 4: "forty", 5: "fifty", 6: "sixty", 7: "seventy"} | {
    8: "eighty",
    9: "ninety",
}


def _es_below_1000(n: int, *, short: bool) -> str:
    """0 < n < 1000 in Spanish; ``short`` before "mil": "veintiún", "un"."""
    out: list[str] = []
    if n >= 100:
        out.append("cien" if n == 100 else _ES_HUNDREDS[n // 100])
        n %= 100
    if n:
        if n < 30:
            word = _ES_UNITS[n]
        else:
            word = _ES_TENS[n // 10] + (f" y {_ES_UNITS[n % 10]}" if n % 10 else "")
        if short and word == "uno":
            word = "un"
        elif short and word == "veintiuno":
            word = "veintiún"
        elif short and word.endswith(" uno"):
            word = word[:-3] + "un"
        out.append(word)
    return " ".join(out)


def _es_number(n: int) -> str:
    if n == 0:
        return "cero"
    parts: list[str] = []
    millions, rest = divmod(n, 1_000_000)
    thousands, units = divmod(rest, 1000)
    if millions:
        parts.append(
            "un millón" if millions == 1 else f"{_es_below_1000(millions, short=True)} millones"
        )
    if thousands:
        parts.append("mil" if thousands == 1 else f"{_es_below_1000(thousands, short=True)} mil")
    if units:
        parts.append(_es_below_1000(units, short=False))
    return " ".join(parts)


def _en_below_1000(n: int) -> str:
    out: list[str] = []
    if n >= 100:
        out.append(f"{_EN_UNITS[n // 100]} hundred")
        n %= 100
        if n:
            out.append("and")
    if n:
        if n < 20:
            out.append(_EN_UNITS[n])
        else:
            out.append(_EN_TENS[n // 10] + (f"-{_EN_UNITS[n % 10]}" if n % 10 else ""))
    return " ".join(out)


def _en_number(n: int) -> str:
    if n == 0:
        return "zero"
    parts: list[str] = []
    millions, rest = divmod(n, 1_000_000)
    thousands, units = divmod(rest, 1000)
    if millions:
        parts.append(f"{_en_below_1000(millions)} million")
    if thousands:
        parts.append(f"{_en_below_1000(thousands)} thousand")
    if units:
        if (millions or thousands) and units < 100:
            parts.append("and")
        parts.append(_en_below_1000(units))
    return " ".join(parts)


def pesos(amount: int) -> str:
    """CLP as the store writes it: ``$28.495``."""
    return "$" + f"{amount:,}".replace(",", ".")


def pesos_said(amount: int, lang: Lang) -> str:
    """CLP as Javier says it: "veintiocho mil cuatrocientos noventa y cinco pesos"."""
    if lang == "en":
        return f"{_en_number(amount)} pesos"
    said = _es_number(amount)
    exact_millions = amount >= 1_000_000 and amount % 1_000_000 == 0
    return f"{said} de pesos" if exact_millions else f"{said} pesos"


def _money(amount: int, lang: Lang) -> str:
    return f"{pesos(amount)} (say: {pesos_said(amount, lang)})"


# ─── Actions (brain → page) ────────────────────────────────────────────────────


class FocusTab(Action):
    """Bring one of the visitor's Cannon Home tabs to the front."""

    tab_id: str


class LanguageChanged(Action):
    """The call's language moved, by the toggle, by voice or by
    ``set_language``: the widget's toggle follows at once."""

    language: Literal["en", "es"]


# ─── Moves (brain → page, through Stage) ───────────────────────────────────────
#
# Every move on the page is a Stage move: a cue the model writes inside its
# reply, made as the voice reaches its words, or a move a tool sends. Each has
# a class (``MoveClass``) that decides how it is sent and what the model hears
# of it, and each is answered with exactly one ``stage_result``. The page
# rings what a move points at before it acts. The models below are the
# arguments of the tool moves, as the page reads them.

SortOrder = Literal["price_asc", "price_desc", "relevance", "newest"]
ProductTab = Literal["descripcion", "especificaciones", "calificaciones", "fotos"]


class SearchProducts(BaseModel):
    """``search_products``: type ``query`` into the store's search box
    (``input.amsearch-input``) at a human pace and let its suggestions open;
    report ``search_suggest``. With ``open_index`` (0-based: 0 is the first
    suggested product), open that product: the page then reports
    ``product_shown``."""

    query: str
    open_index: int | None = None


class FilterListing(BaseModel):
    """``filter_listing``: go to the listing at ``category_path`` (a full
    load, if it is not the one in front), then apply each filter given with
    its quick-filter pill — the option labels exactly as the listing writes
    them ("2 Plazas", "Blanco", "300", "100% Algodón") — one at a time, waiting
    for the grid; then the sort. Each filter takes one option or several
    (``["Beige", "Blanco"]``: the listing shows either), all active together,
    one address for them all. Reports ``listing_shown``."""

    category_path: str
    size: list[str] | None = None
    color: list[str] | None = None
    threads: list[str] | None = None
    material: list[str] | None = None
    sort: SortOrder | None = None


class OpenProduct(BaseModel):
    """``open_product``: open the product at ``path`` (``/x.html``; a full
    load), then the tab named, or step through its photos for ``fotos``.
    Reports ``product_shown``."""

    path: str
    tab: ProductTab | None = None


class ProductTabArgs(BaseModel):
    """``product_tab``: on the product page in front, open that tab, or step
    through its photos for ``fotos``."""

    tab: ProductTab


class CheckPrices(BaseModel):
    """``check_prices``: read the live price and stock of these products (at
    most six), with one same-origin POST to the store's GraphQL. Moves
    nothing. Reports ``prices_read``."""

    paths: list[str]


class AddToCart(BaseModel):
    """``add_to_cart``: on the product page at ``path`` (opened first if it is
    not in front), set the quantity to ``qty`` and press Agregar; wait for the
    cart drawer. Reports ``cart_state``. Never the checkout."""

    path: str
    qty: int = 1


class ShowCart(BaseModel):
    """``show_cart``: open the cart drawer (``open``), or close it. Never the
    checkout."""

    open: bool = True


class UpdateCartItem(BaseModel):
    """``update_cart_item``: set the cart line of the product at ``path`` to
    ``qty``, or take it out with 0: in the cart drawer with its own minus and
    plus, or its bin and "Aceptar"; on the cart page (/checkout/cart) with the
    request those send, then the reload the page's own controls make, the move
    checked on the page it loads. Reports ``cart_state``. Never the checkout."""

    path: str
    qty: int


class StartCheckout(BaseModel):
    """``start_checkout``: take the visitor to the guest checkout's delivery
    form: on the bag (/checkout/cart/, loaded first if it is not in front)
    press "Terminar pedido", then, in the window it opens, "Comprar como
    invitado" — never its login, Google or "Crear Cuenta" — and wait for the
    form (/checkout). Reports ``checkout_state``. Nothing past the form."""


class FillCheckout(BaseModel):
    """``fill_checkout``: fill the checkout's delivery form with what the
    visitor said (the guest checkout is opened first, as ``start_checkout``,
    if it is not in front). Only the fields given, each set as a finished
    edit: región and comuna picked from the site's own lists (the comuna's list
    loads after the región). There is no RUT, password or payment field here,
    and the page refuses every one of them. Never presses anything after the
    fields. Reports ``checkout_state``."""

    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    """Nine digits as said: a mobile starting with 9, or a Santiago landline
    starting with 2. The form's +56 9 / +56 2 prefix is chosen from the first
    digit and the other eight are typed."""
    region: str | None = None
    """The site's name for the región: "Metropolitana", "Valparaíso"."""
    comuna: str | None = None
    street: str | None = None
    number: str | None = None
    apartment: str | None = None
    """Depto/Casa."""


#: The moves Javier makes. The cue verbs are what a reply may write; the
#: others only a tool sends. Classes: what is only looked at (a section, a
#: FAQ, a product's tab, the cart drawer, a price read), what opens another
#: page (a page, a product), what changes the page and can be undone (a
#: search, a filter, a sort), and what changes what the visitor owns once they
#: said yes (the cart and the delivery form).
MOVES: tuple[Move, ...] = (
    Move("page.open", "page", MoveClass.NAVIGATE, ("path",), say="{page: /path}"),
    Move("page.show", "show", MoveClass.LOOK, ("target", "path"), say="{show: Heading}"),
    Move("page.faq", "faq", MoveClass.LOOK, ("question", "path"), say="{faq: Question}"),
    Move(
        "listing.filter",
        "filter",
        MoveClass.REVERSIBLE,
        ("facet", "value", "path"),
        say="{filter: Tamaño | King}",
    ),
    Move("listing.sort", "sort", MoveClass.REVERSIBLE, ("order", "path"), say="{sort: price_asc}"),
    Move("search_products", None, MoveClass.REVERSIBLE),
    Move("filter_listing", None, MoveClass.REVERSIBLE),
    Move("open_product", None, MoveClass.NAVIGATE),
    Move("product_tab", None, MoveClass.LOOK),
    Move("check_prices", None, MoveClass.LOOK),
    Move("show_cart", None, MoveClass.LOOK),
    Move("add_to_cart", None, MoveClass.CONFIRMED),
    Move("update_cart_item", None, MoveClass.CONFIRMED),
    Move("start_checkout", None, MoveClass.CONFIRMED),
    Move("fill_checkout", None, MoveClass.CONFIRMED),
)


# ─── Tool requests ─────────────────────────────────────────────────────────────

if TYPE_CHECKING:
    TopicId = str
else:
    # The L2 files present at import, as the tool's enum; see knowledge.TOPIC_IDS.
    TopicId = Literal[TOPIC_IDS]


class TopicRequest(BaseModel):
    topic: TopicId = Field(description="The topic to read, by its name.")


class SearchRequest(BaseModel):
    query: str = Field(
        description="A few words to look for on cannonhome.cl's pages and FAQs, in Spanish, "
        "e.g. 'despacho regiones', 'cambio de producto', 'retiro en tienda', 'cuotas'."
    )


class TabRequest(BaseModel):
    tab_id: str = Field(description="The tab_id from the open tabs list.")


class LanguageRequest(BaseModel):
    language: Lang = Field(description="'en' for English, 'es' for Spanish.")


class FindRequest(BaseModel):
    """Only what the visitor said or clearly meant: leave the rest out."""

    query: str | None = Field(
        default=None,
        description="Their words, as said, in either language: 'sábanas king blancas', "
        "'toalla de 700 gramos', 'plumón de plumas', 'egyptian cotton sheets'.",
    )
    category: str | None = Field(
        default=None,
        description="A category path from the listings list, or its name: "
        "'/12-ropa-de-cama/20-sabanas', 'Sábanas', 'Toallas'.",
    )
    type: str | None = Field(
        default=None,
        description="The kind of product: 'sábanas', 'funda plumón', 'plumón', 'almohada', "
        "'toalla', 'cubrecama', 'quilt', 'frazada', 'colchón'.",
    )
    size: str | None = Field(
        default=None,
        description="The bed size or measures, as said: '1 plaza', '1,5 plazas', '2 plazas', "
        "'matrimonial', 'king', 'super king', '50x70'.",
    )
    color: str | None = Field(default=None, description="A colour, as said: 'blanco', 'gris'.")
    material: str | None = Field(
        default=None, description="'algodón', 'polycotton', 'microfibra', 'tencel', 'pluma'."
    )
    threads_min: int | None = Field(default=None, description="Fewest threads (hilos).")
    threads_max: int | None = Field(default=None, description="Most threads (hilos).")
    weight_min: int | None = Field(default=None, description="Lightest towel, g/m².")
    weight_max: int | None = Field(default=None, description="Heaviest towel, g/m².")
    sibling_of: str | None = Field(
        default=None,
        description="A product's path: only its line's other sizes and colours. Leave it out "
        "with a size or colour alone and the product page in front is taken.",
    )


class CompareRequest(BaseModel):
    paths: list[str] = Field(
        description="Two to six product paths ('/x.html'), from find_products or their screen."
    )


class SearchProductsRequest(BaseModel):
    query: str = Field(
        description="What to type in the store's search box, in Spanish as the store names "
        "it: 'sábanas 300 hilos', 'toalla blanca', 'plumón king'."
    )
    open_index: int | None = Field(
        default=None,
        description="Open the suggested product at this place, 1 for the first; leave it out "
        "to only show the suggestions.",
    )


def _as_list(value: Any) -> Any:
    """One option said as a plain string is a list of one."""
    return [value] if isinstance(value, str) else value


#: A filter's options as the visitor named them: one, or several of the same
#: filter ("beige y blanco"), each its own item.
Said = Annotated[list[str] | None, BeforeValidator(_as_list)]


class FilterRequest(BaseModel):
    """Only the filters the visitor asked for. Several options of one filter
    are several items: the listing then shows any of them."""

    category_path: str = Field(
        description="The listing's path, from the listings list: '/12-ropa-de-cama/20-sabanas'."
    )
    size: Said = Field(default=None, description="['2 plazas'], ['king', '1,5 plazas']…")
    color: Said = Field(
        default=None, description="Every colour they named: ['blanco'], ['beige', 'blanco']…"
    )
    threads: Said = Field(default=None, description="Thread counts: ['300'].")
    material: Said = Field(default=None, description="['algodón'], ['microfibra']…")
    sort: SortOrder | None = Field(
        default=None, description="'price_asc' cheapest first, 'price_desc', 'newest'."
    )


class OpenProductRequest(BaseModel):
    path: str = Field(
        description="The product's path, '/x.html', from find_products or the screen."
    )
    tab: ProductTab | None = Field(
        default=None,
        description="'especificaciones' for its specs, 'calificaciones' for its reviews, "
        "'descripcion', or 'fotos' to step through its photos.",
    )


class CheckPricesRequest(BaseModel):
    paths: list[str] = Field(description="Up to six product paths ('/x.html') to price live.")


class AddToCartRequest(BaseModel):
    path: str = Field(description="The product's path, '/x.html': the exact size and colour.")
    qty: int = Field(default=1, description="How many, as they said: 1 to 10.")


class UpdateCartRequest(BaseModel):
    line: str = Field(
        description="The cart line: its product path ('/x.html') from the cart line in square "
        "brackets, or its name as the cart shows it."
    )
    qty: int = Field(
        description="How many of it they want in the cart now, 1 to 10; 0 takes it out."
    )


class ShowCartRequest(BaseModel):
    open: bool = Field(default=True, description="True to open the cart drawer, false to close it.")


class CheckoutRequest(BaseModel):
    """Only what the visitor said, and only these. There is no RUT, password or
    card here: those are theirs to type."""

    email: str | None = Field(default=None, description="As they said it, e.g. ana@correo.cl.")
    first_name: str | None = Field(default=None, description="Nombre, as they said it.")
    last_name: str | None = Field(default=None, description="Apellidos, as they said them.")
    phone: str | None = Field(
        default=None,
        description="Their phone, exactly the digits they said, never changed: a Chilean "
        "mobile is nine digits starting with 9 (912345678); a Santiago landline nine "
        "starting with 2.",
    )
    region: str | None = Field(
        default=None,
        description="The región as the site names it: 'Metropolitana' (Santiago), "
        "'Valparaíso', 'Bío Bío', 'Libertador General Bernardo OHiggins'.",
    )
    comuna: str | None = Field(
        default=None, description="The comuna, as Chile names it: 'Providencia', 'Ñuñoa'."
    )
    street: str | None = Field(
        default=None, description="Dirección: the street's name only, 'Avenida Italia'."
    )
    number: str | None = Field(default=None, description="Número: the street number, '1234'.")
    apartment: str | None = Field(
        default=None, description="Depto/Casa, if they have one: '502', 'B'."
    )


# ─── The prompt ────────────────────────────────────────────────────────────────

_SITE_MAP_CHARS = 12000
_SECTIONS_PER_PAGE = 12
#: About 2,300 tokens: every top-level and second-level listing, with its options.
_LISTINGS_CHARS = 9000
#: How the site's titles end, longest first.
_TITLE_SUFFIXES = (
    " | Cannon Home Chile",
    " | Cannon Home",
    " - Cannon Home",
    " | CANNON HOME",
    " | Cannon",
)


def _short_title(title: str) -> str:
    for suffix in _TITLE_SUFFIXES:
        title = title.removesuffix(suffix)
    return title.split(" | ")[0].strip()


def _site_map(k: Knowledge) -> str:
    lines: list[str] = []
    size = 0
    listed = (p for p in k.pages.values() if not p.unlisted and p.path not in k.categories)
    for p in sorted(listed, key=lambda p: (p.path.count("/"), p.path)):
        heads = "; ".join(p.headings[:_SECTIONS_PER_PAGE])
        line = f"- {p.path} — {_short_title(p.title)}" + (f" (sections: {heads})" if heads else "")
        size += len(line) + 1
        if size > _SITE_MAP_CHARS:
            break
        lines.append(line)
    return "\n".join(lines) or "(The site map is not loaded: find pages with search_site.)"


_FILTER_NAMES = {"tamano": "tamaño", "color": "color", "hilos": "hilos", "material": "material"}


def _listings(k: Knowledge) -> str:
    """Each listing, and the options of each of its filters. A colour is named
    as the visitor says it and the store writes it the same way, and nearly
    every listing has most of them: its list is the one left out (the cue's
    colour is checked against the listing's own), so the budget goes on
    listings, not on the same colours 141 times."""
    lines: list[str] = []
    size = 0
    for c in sorted(k.categories.values(), key=lambda c: (c.path.count("/"), c.path)):
        opts = "; ".join(
            "color" if v == "color" else f"{_FILTER_NAMES[v]}: {', '.join(labels[:12])}"
            for v, labels in c.options
            if v in _FILTER_NAMES
        )
        line = f"- {c.path} — {c.name}" + (f" ({opts})" if opts else "")
        size += len(line) + 1
        if size > _LISTINGS_CHARS:
            break
        lines.append(line)
    return "\n".join(lines) or "(The listings are not loaded: use search_products.)"


def _topics(k: Knowledge) -> str:
    return "\n".join(f"- {t.id}: {t.title}" for t in k.topics.values()) or "(none loaded)"


def _prompt(k: Knowledge, today: date | None = None) -> str:
    today = today or datetime.now(TIMEZONE).date()
    return f"""You are {AGENT_NAME}, the voice guide on Cannon Home's online store, cannonhome.cl. Cannon Home is a Chilean home-textiles brand: sheets, duvets and duvet covers, pillows, quilts and blankets, towels and bathrobes, beds and mattresses. A visitor is shopping on the store right now and has called you from the corner of the page. You can see and move their screen: you type in the store's search, filter a listing, open a product and its tabs, read live prices, add to their cart, change how many of a line they have or take it out, open the cart, and take them to the checkout's delivery form and fill in their delivery details. You are warm, calm and practical — the friendly person in the store who knows every sheet, thread count and size, and helps them choose without pushing. Say the name as "Cannon Home".

# You narrate, and the screen follows your words
You are giving a guided walk through the store, like someone sitting beside the visitor with their screen in front of you both.
- Put a screen cue in your reply at the start of the sentence it belongs to. The page moves when your voice reaches that sentence. The visitor never hears a cue.
  - {{page: /path}} opens a page of the store, at its top: an information page from the site pages list, a listing from the listings list, or a product's path.
  - {{show: Heading}} scrolls to a heading on the page they are on, or are taken to by a page cue, and rings it. With other words on the page — a product's name, a price, a line of a policy — it rings those words.
  - {{faq: Question}} opens that FAQ and rings it. The FAQ can be on any page: it is found and opened there.
  - {{filter: Facet | Option}} narrows the listing in front (or the one a page cue just opened) by one of its filters, with the option exactly as the listings list writes it: {{filter: Tamaño | King}}, {{filter: Color | Blanco}}, {{filter: Hilos | 300}}, {{filter: Material | 100% Algodón}}. The filter's pill opens, the option is ringed and chosen, and the grid follows. A filter cue adds its option to the ones already on: {{filter: Color | Blanco}} then {{filter: Color | Beige}} shows both colours. Several options of one filter may also go in one cue, a comma between them: {{filter: Color | Blanco, Beige}}.
  - {{sort: price_asc}} sorts the listing in front: price_asc (cheapest first), price_desc, or newest.
- Use headings and words exactly as the site pages list or the screen lines spell them. The store is in Spanish, so cues are in Spanish, also inside an English reply: "{{page: /politicas-de-despacho}} Deliveries come with no exact hour."
- Never make up a heading or a path.
- One cue per sentence at most, and only where the screen should change. A cue goes before the sentence, never inside it.
- When the visitor asks where something is ("muéstrame", "where is that"), your reply starts with the cue for exactly that thing.
- When the visitor clearly asks to narrow a listing ("las king blancas", "show me the cotton ones"), filter with cues as you say it, one filter per sentence, each sentence about that filter. Open the listing first when it is not in front. "{{page: /12-ropa-de-cama/20-sabanas}} Te abro nuestras sábanas. {{filter: Tamaño | King}} Te las dejo en tamaño king. {{filter: Color | Blanco}} Y te dejo solo las blancas."
- When the visitor names several options of one filter ("beige y blanco", "king or super king"), they want all of them: put every one on, one cue per option or one cue listing them, and never ask which one first. "{{filter: Color | Beige}} Te dejo las beige. {{filter: Color | Blanco}} Y también las blancas." With filter_listing, each filter takes a list: color ['beige', 'blanco'].
- A filter or sort cue sits on a promise of what you are doing ("Let me narrow it to king size.", "Te las ordeno de la más barata."), never on a statement of the result ("These are for your king bed.", "Estas son las king."): the grid has not changed yet when the voice says it, and the filter may not apply. What the listing then shows comes to you in square brackets: say the result on your next turn, from that line, and if a filter could not be applied you are told, to say so.
- A reply that calls a move (search_products, filter_listing, open_product, add_to_cart, update_cart_item, show_cart, start_checkout, fill_checkout) has no cue: the move takes them there. The cart and the checkout are only ever reached by those moves, never by a cue.
- Cues open pages, show what is on them and filter a listing; the moves below search, open products and change the cart. Nothing waits on a cue.

# A good turn moves them one step closer to the right product
1. Answer what they asked, first, in plain words, and show it as you say it.
2. Add the one thing that matters for them: the size for their bed, the thread count, the material, the weight of a towel.
3. End with one short, specific yes-or-no offer of the next step: "¿Te abro las de dos plazas?", "¿Te lo agrego al carro?", "Want me to show you the white ones?". Never "anything else?".
- A visit to the store has an order. Follow it from wherever the visitor is: what they need (which product, for which bed or bathroom), then narrow it (size, colour, material, thread count), then one product on their screen with its live price, then the cart, then their delivery details — and the RUT and the payment they complete themselves.
- Ask about them only when the answer changes what you show next, and offer the choices: "¿Para una cama de dos plazas o king?", "¿Las prefieres de algodón o de microfibra?".

# How you sound
You are heard, not read, so keep it light and warm.
- A turn is three to five short sentences. Every sentence under fifteen words. Small, everyday words. One idea per sentence. One number per sentence.
- THE FIRST SENTENCE IS A FEW WORDS. The visitor hears nothing until your first sentence has been voiced, so open every reply with a sentence of two to six words that ends in a full stop, with the answer in it. A cue may come before it.
- Your first word is the answer: no filler, no "great question", no repeating their question back.
- Spoken words only, apart from cues: no lists, no markdown, no symbols, never an exclamation mark.
- Write every number, price and measure as spoken words. Prices are Chilean pesos: "$28.495" is "veintiocho mil cuatrocientos noventa y cinco pesos", in English "twenty-eight thousand four hundred and ninety-five pesos". The lines in square brackets give each price with how to say it. "300 hilos" is "trescientos hilos"; "50x70" is "cincuenta por setenta". Never say a SKU or a path.
- Lines in square brackets come from their screen, not the visitor: the page in front, a product, a listing, the cart. Never read them out; use them.
- Never list what is on screen: name two or three things, and point at the rest.
- Always answer. A reply with no words leaves the visitor in silence.

# Spanish or English
You speak Spanish as a native of Latin America, and English. The call starts in Spanish unless the visitor chose English.
- Answer in Spanish. Move to English only when the visitor says at least two full sentences in English in one turn, or asks for English; then answer in English from that reply on, and if the visitor go back to Spanish, so do you. Speech recognition often hears a short Spanish reply or a Chilean name as English ("See" for "sí", "And lower net here" for "Lo Barnechea"): the visitor is still speaking Spanish, so answer in Spanish. Your voice follows the language you write.
- Except when they chose a language: a line in square brackets says so. Then answer in that language whatever they speak, even when they speak the other one, until they ask you to switch.
- When they ask for the other language in words that are not already it ("¿Puedes hablar en inglés?", "Can we speak Spanish?"), answer in that language and call set_language in the same response. A visitor already speaking English to you has been switched: do not call it for them.
- One language per reply: in a Spanish reply every sentence is Spanish, and masculine forms of yourself ("encantado de ayudarte").
- Your Spanish is neutral Latin American Spanish, warm and natural for a Chilean visitor, never the Spanish of Spain and never heavy slang.
  - Address the visitor as "tú", as the store does ("Agrega a tu bolsa"), never "usted"; several people are "ustedes", never "vosotros", and never its verb forms ("queréis", "tenéis", "podéis") or "os".
  - Chile's own store words are right here: the "carro" or "carro de compras", never "cesta"; "despacho" for delivery; "retiro en tienda"; "plumón" for a duvet; "cobertor", "cubrecama" and "quilt"; "sábanas"; "toalla"; "frazada"; "cuotas sin interés"; "boleta".
  - Use Latin American words: "celular", never "móvil"; "computadora", never "ordenador"; "mostrar" ("te muestro"), not "enseñar"; "completar", not "rellenar"; "¿Qué te queda bien?", not "te viene bien"; "disculpa", not "perdona"; "está bien" or "perfecto", never "vale"; "tomar", never "coger". Write "video", never "vídeo".
  - For something just done, use the simple past: "Abrí el producto", "Lo agregué", not "He abierto".
- In English, say the store's Spanish names as they are written ("2 Plazas", "Funda Plumón", "despacho"), and explain them in a few words when they are not obvious: "dos plazas, a queen-size bed".

# Every fact has a source
- Every fact comes from the knowledge below, a topic you read, a search result, find_products or compare_products, or what the screen reported. Never from memory. If you cannot find it, say so, and offer the FAQ or the contact page.
- Never promise stock, a delivery date, a discount or a restock the site does not state.

# Every response starts with words
Write your answer, with its cues, first; any tool call comes at the end of the same response. What a page move returns reaches you only on your next turn.
- The exception is a read: read_topic, search_site, find_products and compare_products come straight back to you within this same turn, but each one makes the visitor wait. Answer from what you know below whenever it covers the question. Read only for what is not here, and then call the read first, with nothing written before it.
- The moves — search_products, filter_listing, open_product, check_prices, add_to_cart, update_cart_item, show_cart, start_checkout, fill_checkout — are not done when you call them: the page does them a moment later and tells you in square brackets. In the reply that calls one, say only what you are doing ("Te abro las sábanas king.", "Te lo agrego al carro."), never that it is done. When the page's answer comes, say what it says happened: what is done, and plainly what is not.
- One move at a time: when a tool says the page is still working on the last move, what you asked for follows by itself. Say so in a few words, and never call it again.
- Some moves take a few seconds. While a move is still running (a line in square brackets says it is still working), never say you could not confirm it or that it failed: say you are still on it. Never say the store, the site or the page is slow: that blames the store, whose site this is. If a line later says it was done after all, correct yourself in a few words.
- A move you already called is under way until the page answers it: never call it a second time for the same thing. When the visitor asks for two things at once ("add both"), call both in the same response, in order: the second waits for the first and follows by itself.
- Never promise more to come ("let me check"): nothing comes after it.
- A question about the call itself — "can I speak English?", "can you hear me?", "who are you?" — gets an answer and nothing else: no move, no page.

# Finding products
- find_products searches the whole catalogue from what they said, in either language — size, colour, material, thread count, towel weight, type — and returns each product's path, its attributes, and its line's other sizes and colours. When it had to drop a wish to find anything, it says which: tell them plainly what is different.
- Then show what fits: open_product for one product, the listing narrowed the same way with filter cues (a strong way to show a choice), or search_products to type their words in the store's search box, where the suggestions show live prices.
- compare_products puts two to six products side by side from the catalogue, with the prices their screen has already shown.
- On a product page the tabs are "descripcion", "especificaciones" (measures, thread count, material, filling), "calificaciones" (reviews) and "fotos": open_product with the tab shows it.

# Prices and stock
- You know no price and no stock of your own: the catalogue has none. A price or stock you say is one their screen just reported, in a line in square brackets: the product page, its live check, a listing, the search box's suggestions, check_prices or the cart.
- A product page is read twice: first from the page, which may be an old cached copy, then live. A line that says "Live check" wins: say that price.
- Say a price in spoken words, in Chilean pesos. With a discount, say the price and that it was more before, once.
- When no line has the price: say you can't see the price right now, and open the product (open_product), whose page shows it; for several products at once, check_prices reads them live. Never a price from memory, from the catalogue, or from another size or colour of the line: each has its own price.
- Stock is "available" or "not available" as the line says. Never promise how many are left beyond what the line says, or when it is back.
- "Cuotas sin interés" and the free-shipping threshold: as the knowledge below states them.

# Sizes and colours
- The product page has no size or colour picker: every size and every colour is its own product, with its own page and its own price.
- "¿La tienes en king?", "in white?": find_products with the size or colour (sibling_of the product in front is taken when you leave the rest out), then open_product on the sibling's path. Never say you changed the size on the page.
- Beds go by "plazas", as Chile sells them: 1 plaza, 1,5 plazas ("plaza y media"), 2 plazas (a "matrimonial", a queen-size bed), king, super king. Pillows and towels go by measures, "cincuenta por setenta"; towels by weight, grams per square metre: more grams, a thicker towel.
- Sheets go by thread count, "hilos": more threads, a denser, softer weave. Say what the catalogue and the knowledge say, no more.
- A listing narrows by tamaño, color, hilos or material, only with the options that listing has (the listings list below), and sorts by price. Filter with cues as you talk the visitor through it; filter_listing does the same in one move, after your words, when you have nothing to say about each filter.

# The cart
- You may add a product to their cart when they ask, or say yes to your offer: add_to_cart with the product's path, the exact size and colour, and the quantity they said (one unless they said more). It opens the product first if it is not in front. Say what you are adding, never that it is added: the cart's answer comes in square brackets.
- show_cart opens their cart drawer; with open false it closes it. A cart line tells you what is in it and what is left for free shipping: say that once.
- You can change their cart too. When they want more or fewer of something in it, or want a line out ("solo uno", "quita las grises", "remove the grey ones"), call update_cart_item with that line's path from the cart line and how many they want now: 0 takes it out. One line per call. It works in the cart drawer, or on the cart page when that is in front. Say what you are changing, never that it is changed: the cart's answer comes in square brackets. Never tell them to change it themselves.
- When they want to buy, or say yes to your offer, start_checkout takes them from the cart to the checkout's delivery form as a guest. Then the section below.

# The checkout: delivery details are yours, the RUT and the payment are theirs
- start_checkout opens the guest checkout: it presses "Terminar pedido" in the cart and then "Comprar como invitado", never the login, Google or "Crear Cuenta". It is one page, /checkout: contact, delivery and personal details, then the payment.
- On that form you may fill, with fill_checkout: their email, nombre, apellidos, teléfono, región, comuna, dirección (the street), número and depto or casa. Nothing else.
- Ask for what is missing one or two fields at a time, in the form's order: email first, then región and comuna, then the address, then name and phone. Never ask for all of it at once.
- Fill each detail the moment they say it: fill_checkout with only what they just said. What is filled stays; you only add, or fill a field again when they correct it.
- A phone is the digits they said, never changed. The form takes a Chilean number, nine digits: a mobile starting with 9, or a Santiago landline starting with 2. If what they said is not one, say the form needs a Chilean number and ask for it; never drop, add or reorder a digit to make it fit. Read the phone back digit by digit in the same reply.
- Read an email back in the same reply. Spell it letter by letter where it could be heard wrong: a name with an unusual spelling, b or v, s or z, numbers in it.
- Región and comuna are the site's names: "Metropolitana" for Santiago, "Valparaíso", "Bío Bío", and the comuna as Chile names it ("Providencia", "Ñuñoa", "Viña del Mar"). Fill the región with its comuna: the comuna's list loads once the región is chosen.
- THE RUT, ANY PASSWORD AND THE PAYMENT ARE THEIRS, always. Never ask for a RUT, never repeat one, never write one anywhere, even when they say it: say "El RUT y el pago los completas tú." in their language, and point at the field. The same for a password and every card detail.
- An email that already has an account makes the site show a password: that is a login, and it is theirs. Say they can sign in themselves, or carry on as a guest.
- They choose the delivery method themselves, "Despacho a domicilio" or "Retiro en tienda", once the comuna is in.
- YOU NEVER PRESS what moves on to the payment or places the order: "Continuar compra", "Completa los pasos", "Realizar pedido", "Ir a pagar", "Pagar", Webpay or anything under "Método de Pago". When the form is complete, say what is filled and that the RUT, the delivery method and the payment are theirs. Never say the order is placed.
- A checkout line in square brackets tells you which fields are filled, which are missing and what the form flags, in the site's words. Say what the form flags in a sentence, and ask for the right one.

# Tabs
- The visitor may have several store tabs open. Lines in brackets tell you which tabs are open and which is in front. "Go back to the other tab" is switch_tab with that tab's id.

# What you know
- Today is {today:%A, %d %B %Y}, in Santiago.
- Home delivery ("despacho") hours are as the knowledge below says, Saturdays shorter than weekdays: never one span for every day.
- Topics you can read with read_topic, when the knowledge below does not cover a question:
{_topics(k)}
- search_site finds an information page, section or FAQ by its words. Its results name the page and section, which you can then cue.

# CANNON HOME
{k.l1}

# The catalogue (category, how many products, what it carries)
{k.catalogue_index()}

# Listings (path — name, and the filter options each has; "color" alone: it filters by colour, named as the visitor says it — Blanco, Beige, Gris)
{_listings(k)}

# Site pages
{_site_map(k)}
"""


# ─── Greeting ──────────────────────────────────────────────────────────────────

_INTRO: dict[Lang, str] = {
    "es": f"Hola, soy {AGENT_NAME}, tu guía de voz de Cannon Home.",
    "en": f"Hi, I'm {AGENT_NAME}, Cannon Home's voice guide.",
}
_GREETING: dict[Lang, str] = {
    "es": "Te ayudo a encontrar sábanas, toallas, plumones y más, y te muestro cada producto. "
    "¿Qué estás buscando?",
    "en": "I can help you find sheets, towels, duvets and more, and show you each one. "
    "What are you looking for?",
}
#: The opener's second sentence for the page the call starts on, by a word in
#: its path; the first match wins, and anything else gets the plain greeting.
#: The cart first, then the checkout, then a product page, then the categories.
_OPENERS: tuple[tuple[str, dict[Lang, str]], ...] = (
    (
        "/checkout/cart",
        {
            "es": "Te ayudo a revisar tu carro, o a encontrar algo más. ¿Qué necesitas?",
            "en": "I can help you go over your cart, or find something more. What do you need?",
        },
    ),
    (
        "/checkout",
        {
            "es": "Te ayudo a completar tus datos de despacho. El RUT y el pago los completas "
            "tú. ¿Empezamos por tu correo?",
            "en": "I can help you fill in your delivery details. The RUT and the payment are "
            "yours to complete. Shall we start with your email?",
        },
    ),
    (
        ".html",
        {
            "es": "Te cuento de este producto, te muestro otros tamaños o colores, y te lo "
            "agrego al carro si quieres. ¿Qué te gustaría saber?",
            "en": "I can tell you about this product, show you other sizes or colours, and "
            "add it to your cart. What would you like to know?",
        },
    ),
    (
        "fundas-plumon",
        {
            "es": "Te ayudo a elegir tu funda de plumón, por tamaño y color. ¿Para qué cama es?",
            "en": "I can help you choose a duvet cover, by size and colour. What size is your bed?",
        },
    ),
    (
        "plumon",
        {
            "es": "Te ayudo a elegir tu plumón: relleno, abrigo y tamaño. ¿Para qué cama es?",
            "en": "I can help you choose a duvet: filling, warmth and size. What size is your bed?",
        },
    ),
    (
        "sabanas",
        {
            "es": "Te ayudo a elegir tus sábanas: tamaño, hilos y material. ¿Para qué cama son?",
            "en": "I can help you choose sheets: size, thread count and material. "
            "What size is your bed?",
        },
    ),
    (
        "toalla",
        {
            "es": "Te ayudo a elegir tus toallas, por tamaño, color y gramaje. ¿Qué buscas?",
            "en": "I can help you choose towels, by size, colour and weight. "
            "What are you looking for?",
        },
    ),
    (
        "/bano",
        {
            "es": "Te ayudo con el baño: toallas, batas y pisos. ¿Qué buscas?",
            "en": "I can help with the bathroom: towels, robes and bath mats. "
            "What are you looking for?",
        },
    ),
    (
        "almohada",
        {
            "es": "Te ayudo a elegir tu almohada, según cómo duermes. ¿De lado o de espalda?",
            "en": "I can help you choose a pillow for the way you sleep. "
            "On your side or your back?",
        },
    ),
)


def _is_product_path(path: str) -> bool:
    return path.endswith(".html") and not path.startswith("/blog")


def greeting(path: str | None, lang: Lang = OPENING) -> str:
    """The written opener, in ``lang``, tailored to the page the call starts on."""
    here = canonical_path(path or "/")
    line = _GREETING[lang]
    for word, lines in _OPENERS:
        if word == ".html":
            if _is_product_path(here):
                line = lines[lang]
                break
        elif word in here:
            line = lines[lang]
            break
    return f"{_INTRO[lang]} {line}"


# ─── Written lines for moves ───────────────────────────────────────────────────

#: His line for a silent turn, by what moved. A move is not done when the turn
#: ends: the page answers later, so its line says what he is doing.
_LANDED: dict[str, dict[Lang, str]] = {
    "shown": {"en": "Here it is.", "es": "Aquí lo tienes."},
    "tab": {"en": "There's that tab.", "es": "Ahí tienes esa pestaña."},
    "search": {"en": "I'm searching the store for it.", "es": "Lo busco en la tienda."},
    "filter": {"en": "I'm filtering the list for you.", "es": "Te filtro la lista."},
    "product": {"en": "I'm opening the product.", "es": "Te abro el producto."},
    "prices": {
        "en": "I'm reading the prices on the store.",
        "es": "Te reviso los precios en la tienda.",
    },
    "cart_add": {"en": "I'm adding it to your cart.", "es": "Lo agrego a tu carro."},
    "cart_show": {"en": "I'm opening your cart.", "es": "Te abro el carro."},
    "cart_update": {"en": "I'm changing that in your cart.", "es": "Te lo cambio en el carro."},
    "cart_remove": {"en": "I'm taking it out of your cart.", "es": "Lo saco de tu carro."},
    "cart_close": {"en": "I'm closing the cart.", "es": "Te cierro el carro."},
    "checkout": {
        "en": "I'm taking you to the delivery details.",
        "es": "Te llevo a los datos de despacho.",
    },
    "checkout_fill": {"en": "I'm filling that in.", "es": "Te lo completo."},
    "queued": {
        "en": "I'll do that as soon as the page is ready.",
        "es": "Lo hago apenas la página esté lista.",
    },
}

#: His line once the page confirms a confirmed move, by move: said with no
#: model request before it. ``{name}`` is the product the page added.
_DONE: dict[str, dict[Lang, str]] = {
    "add_to_cart_named": {
        "en": "Done, {name} is in your cart.",
        "es": "Listo, {name} ya está en tu carro.",
    },
    "add_to_cart": {"en": "Done, it's in your cart.", "es": "Listo, ya está en tu carro."},
    "update_cart_item": {
        "en": "Done, your cart is updated.",
        "es": "Listo, tu carro quedó al día.",
    },
    "start_checkout": {
        "en": "Here's the delivery form.",
        "es": "Listo, aquí está el formulario de despacho.",
    },
    "fill_checkout": {"en": "Done, I filled that in.", "es": "Listo, lo completé."},
}
#: The page's detail for an add: "added 1 (times sign) Liso Blanco (the bag line …); …".
_ADDED = re.compile(r"^added \d+ (?:×|x|of) (.+?)(?: \(the bag line|;|$)")  # noqa: RUF001


#: His line for a move still running after Stage's ``HOLDING_LINE_S``, by
#: move, said once in a quiet spell with no model request before it, so a move
#: still under way is not heard as a failed one; ``""`` is any other move. A
#: line says he is still at it and never blames the store: "the store is slow"
#: is heard as a fault of the site's owner, whose site this is.
_HOLDING: dict[str, dict[Lang, tuple[str, ...]]] = {
    "add_to_cart": {
        "en": ("Still adding it, one moment.", "Almost there, adding it to your cart."),
        "es": ("Lo sigo agregando, un momento.", "Ya casi, lo estoy agregando a tu carro."),
    },
    "update_cart_item": {
        "en": ("Still updating your cart, one moment.", "Almost done with your cart."),
        "es": ("Sigo actualizando tu carro, un momento.", "Ya casi termino con tu carro."),
    },
    "start_checkout": {
        "en": ("Getting the checkout ready, one moment.", "Almost there with the checkout."),
        "es": ("Estoy preparando el pago, un momento.", "Ya casi tengo listo el formulario."),
    },
    "fill_checkout": {
        "en": ("Still filling it in, one moment.", "Almost done with the form."),
        "es": ("Lo sigo completando, un momento.", "Ya casi termino el formulario."),
    },
    "": {
        "en": ("I'm on it, one moment.", "Still working on it, bear with me.", "Almost there."),
        "es": ("Estoy en eso, un momento.", "Sigo en eso, dame un segundo.", "Ya casi."),
    },
}
#: How often the brain looks for a move slow enough for its holding line.
_HOLD_POLL_S = 0.5


def holding_line(move: str, lang: Lang, rng: random.Random | None = None) -> str:
    """His one line for a move the page is still working on, picked at random
    among the move's lines so two in one call are not word for word alike."""
    lines = (_HOLDING.get(move) or _HOLDING[""])[lang]
    return (rng or random).choice(lines)


#: The moves whose effect a listing on screen is, and a product page's.
_LISTING_MOVES = ("filter_listing", "listing.filter", "listing.sort")
_PRODUCT_MOVES = ("open_product", "search_products")
#: ``filter_listing``'s filter arguments, by the listing's request variable.
_FILTER_ARGS = (
    ("size", "tamano"),
    ("color", "color"),
    ("threads", "hilos"),
    ("material", "material"),
)


def _said_list(items: list[str], lang: Lang) -> str:
    """ "Beige and Blanco", "Beige, Blanco y Gris"."""
    if len(items) < 2:
        return "".join(items)
    last = " and " if lang == "en" else " y "
    return ", ".join(items[:-1]) + last + items[-1]


def listing_line(e: ListingShown, lang: Lang, named: list[str] | None = None) -> str:
    """His line the moment a listing he filtered or sorted lands: how many,
    in what (``named``: the options his move put on, as the listing writes
    them), and the first card with its price as the screen shows it ("Here
    are 9 in Beige and Blanco; the first is Liso Menta at …"). Said with no
    model request before it."""
    n = e.count if e.count is not None else len(e.items)
    what = _said_list(named or [], lang)
    if n == 0 or not e.items:
        if lang == "en":
            return f"No products show in {what}." if what else "No products show for that."
        return (
            f"No aparece ningún producto en {what}."
            if what
            else ("No aparece ningún producto con eso.")
        )
    first = e.items[0]
    price = ""
    if first.price is not None:
        said = pesos_said(first.price, lang)
        price = f" at {said}" if lang == "en" else f", a {said}"
    where = f" in {what}" if what and lang == "en" else f" en {what}" if what else ""
    if lang == "en":
        return (
            f"Here's one{where}: {first.name}{price}."
            if n == 1
            else (f"Here are {n}{where}; the first is {first.name}{price}.")
        )
    return (
        f"Aquí hay uno{where}: {first.name}{price}."
        if n == 1
        else (f"Aquí hay {n}{where}; el primero es {first.name}{price}.")
    )


def landed_options(landing: Landing, event: ListingShown) -> list[str]:
    """The options a filter move put on, as the listing writes them, for its
    landing line: a cue's filter, all its options now on (the ones it added
    and the ones it kept); ``filter_listing``'s, every filter it asked for. A
    sort names none."""
    move, args, cue = landing.move.id, landing.args or {}, landing.cue_args
    if move == "listing.filter" and cue:
        return _shown_options(event, cue[0])
    if move == "filter_listing":
        return [x for key, var in _FILTER_ARGS if args.get(key) for x in _shown_options(event, var)]
    return []


def product_line(e: ProductShown, lang: Lang) -> str:
    """His line the moment a product he opened is on screen. A price only from
    the live check: the page's own may be hours old."""
    name = e.name or ("the product" if lang == "en" else "el producto")
    price = ""
    if e.source == "graphql" and e.price is not None:
        said = pesos_said(e.price, lang)
        price = f", at {said}" if lang == "en" else f", a {said}"
    line = f"Here's {name}{price}." if lang == "en" else f"Aquí está {name}{price}."
    if e.in_stock is False:
        line += " It's out of stock right now." if lang == "en" else " Ahora está sin stock."
    return line


def _label_key(label: str) -> str:
    """A filter option, folded: "300 hilos" and "300" are one option."""
    return norm(label).replace(" hilos", "").strip()


def _option_set(labels: str | list[str] | None) -> frozenset[str]:
    """The options in a filter's value — a list, or the page's labels joined
    by ", " ("Beige, Blanco") — folded, as a set: the order never counts."""
    items = labels.split(", ") if isinstance(labels, str) else list(labels or [])
    return frozenset(k for i in items if (k := _label_key(i)))


def _shown_options(event: ListingShown, var: str) -> list[str]:
    """The options active in ``var`` on the listing, as it writes them."""
    return [x for x in event.filters.get(var, "").split(", ") if x.strip()]


def lands(landing: Landing, event: ListingShown | ProductShown) -> bool:
    """Whether ``event`` on screen is what ``landing``'s move asked for: a
    load shows the listing unfiltered before the move filters it, and that is
    not its effect."""
    move, args, cue = landing.move.id, landing.args or {}, landing.cue_args
    if isinstance(event, ProductShown):
        if move == "search_products":
            return args.get("open_index") is not None
        want = args.get("path")
        return isinstance(want, str) and _product_path(event.path) == _product_path(want)
    if move == "filter_listing":
        path = args.get("category_path")
        if isinstance(path, str) and not canonical_path(event.path).startswith(
            canonical_path(path)
        ):
            return False
        # Every option asked for, and no other, in each filter asked for: a
        # set, never a prefix ("Beige" is not "Beige, Blanco").
        for key, var in _FILTER_ARGS:
            value = args.get(key)
            if not value:
                continue
            asked = value if isinstance(value, list) else str(value)
            if _option_set(event.filters.get(var)) != _option_set(asked):
                return False
        sort = args.get("sort")
        return not isinstance(sort, str) or event.sort == sort
    if move == "listing.filter" and len(cue) >= 2:
        # A cue adds to what is active: each of its options is on.
        want = _option_set(cue[1])
        return bool(want) and want <= _option_set(event.filters.get(cue[0]))
    if move == "listing.sort" and cue:
        return event.sort == cue[0]
    return False


def late_done_line(move: str, detail: str, lang: Lang) -> str | None:
    """:func:`done_line` for a move he was told was not confirmed, which the
    page then confirmed: "Done after all, Liso Blanco is in your cart."."""
    line = done_line(move, detail, lang)
    if line is None:
        return None
    rest = line.removeprefix("Listo, " if lang == "es" else "Done, ")
    if rest.startswith("Here's"):  # A product's name keeps its capital.
        rest = "here's" + rest.removeprefix("Here's")
    return f"Al final sí, {rest}" if lang == "es" else f"Done after all, {rest}"


def done_line(move: str, detail: str, lang: Lang) -> str | None:
    """The written line for a confirmed move the page reports done, built
    from its detail; ``None`` when the detail says part of it is not. (A
    ``partial`` outcome never asks for one.)"""
    if "not filled" in detail:
        return None
    if move == "add_to_cart" and (m := _ADDED.match(detail)) is not None:
        name = m.group(1).strip()
        if name and not name.startswith("/"):
            return _DONE["add_to_cart_named"][lang].format(name=name)
    lines = _DONE.get(move)
    return None if lines is None else lines[lang]


#: What a reply that only promises more says: nothing comes after it.
_PROMISE = re.compile(
    r"\b(?:just |one |un )?(?:moment|momento|momentito|second|segundo)\b"
    r"|\blet me (?:see|check|look)(?: (?:that|into it|at that))?\b|\bdéjame ver\b|\ba ver\b",
    re.IGNORECASE,
)

_HEADINGS_IN_NOTE = 40
_FAQS_IN_NOTE = 40
_SEARCH_HITS = 6
_FOUND_SHOWN = 8
_SIBLINGS_SHOWN = 6
_LISTED_IN_NOTE = 12
_SPECS_IN_NOTE = 14
_MOST_PRICED = 6


async def _silence() -> AsyncGenerator[Any, None]:
    for _ in ():
        yield


def _clip(items: list[str] | tuple[str, ...], most: int) -> str:
    more = f"; and {len(items) - most} more" if len(items) > most else ""
    return "; ".join(items[:most]) + more


def _match(want: str, options: list[str] | tuple[str, ...]) -> str | None:
    """The option ``want`` names: the same words, else the one it begins, else
    the one it is inside. Case, accents and punctuation do not count."""

    def folded(s: str) -> str:
        return " ".join(re.sub(r"[^\w\s]", " ", norm(s)).split())

    w = folded(want)
    if not w:
        return None
    pairs = [(folded(o), o) for o in options]
    for test in (
        lambda o: o == w,
        lambda o: o.startswith(w),
        lambda o: w.startswith(o) and len(o) > len(w) // 2,
        lambda o: w in o,
    ):
        if (hit := next((o for f, o in pairs if f and test(f)), None)) is not None:
            return hit
    return None


def _product_path(path: str) -> str:
    """A product's path as the store links it: ``/x.html``."""
    p = canonical_path(path)
    return p if p.endswith(".html") else f"{p}.html"


#: Paths the store always has, whether or not the crawl kept them as pages:
#: the home, the bag, and the checkout's delivery form (one page, /checkout).
_FIXED_PAGES = frozenset({"/", "/checkout/cart", "/checkout"})
#: Pages only a move takes them to: never cued from his own sentence.
_MOVE_PAGES = frozenset({"/checkout/cart", "/checkout"})
#: Paths no cue or move may open: past the delivery form (the payment, the
#: order's success page), the account, the login, a payment's own pages.
_NEVER = re.compile(
    r"^/(?:checkout/(?!cart$)|customer|sales/order|onestepcheckout|webpay|paypal|braintree"
    r"|mercadopago)"
)


#: The page for what the visitor asked about, when his reply forgets to show
#: it; each with the paths the store has used for it, the first the crawl has
#: wins. Matched on their own words, folded, in Spanish and English; the first
#: named wins. Products and listings are not here: those are moves.
_ASKED_PAGES: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...] = tuple(
    (re.compile(rf"\b(?:{w})", re.IGNORECASE), paths)
    for w, paths in (
        (
            r"retiro en tienda|retirar en (?:la )?tienda|retirarlo|pick ?up|click (?:and|&) collect",
            ("/retiro-tiendas",),
        ),
        (
            r"despacho|despachan|envios?\b|cuanto (?:demora|tarda) (?:en )?llegar|shipping"
            r"|deliver(?:y|ies|ed|able|s)?\b",
            ("/politicas-de-despacho",),
        ),
        (
            r"cambios?\b|cambiar(?:lo|la)? (?:un|el|la|por)|devoluci|devolver|returns?\b|refund"
            r"|exchange|garantia|warranty",
            ("/politicas-de-cambios-y-devoluciones",),
        ),
        (
            r"tiendas? fisicas?|sus tiendas|las tiendas|donde (?:queda|quedan|estan) (?:la|las)"
            r" tiendas?|sucursal|physical stores?|your stores|store locations?",
            ("/stores",),
        ),
        (
            r"medios de pago|formas? de pago|como (?:puedo )?pagar|tarjeta|webpay|mercado ?pago"
            r"|payment methods?|pay with",
            ("/preguntas-frecuentes",),
        ),
        (r"preguntas frecuentes|\bfaqs?\b", ("/preguntas-frecuentes",)),
        (r"guia de compras?|buying guide", ("/guia-de-compras",)),
        (r"contacto|contactar|contact (?:you|us)|hablar con alguien", ("/contact",)),
        (
            r"datos de (?:despacho|entrega|envio)|direccion de (?:despacho|entrega|envio)"
            r"|terminar (?:el |mi )?pedido|finalizar (?:la |mi )?compra|\bcheckout\b"
            r"|delivery details|shipping (?:address|details)",
            ("/checkout",),
        ),
        (r"(?:mi |el |tu )?carr(?:o|ito)\b|mi bolsa|\bcart\b|basket", ("/checkout/cart",)),
    )
)
_ASKED_TAB = re.compile(r"\b(?:tabs?|pestanas?)\b", re.IGNORECASE)
#: Asking to add to the cart is a move, not the cart page.
_ADDS = re.compile(
    r"\b(?:agreg|anad|añad|pon(?:lo|la|er|me)|mete|echa|sum|add|put)\w*", re.IGNORECASE
)
#: A move on the cart: an add, a change, a removal, the checkout. With the
#: cart as recognition hears it: "add this to cut" was an add (dev, 2026-10-28).
_CART_MOVE = re.compile(
    r"\b(?:agreg|anad|añad|pon(?:lo|la|er|me)|mete|echa|add|put|quit|sac(?:a|alo|ala|ar)\b"
    r"|elimin|borr|remove|take (?:it|them|that|one) out|cambi\w* (?:la )?cantidad"
    r"|change the (?:quantity|amount)|checkout|check out|terminar (?:el |mi )?pedido"
    r"|finaliz\w* (?:la |mi )?compra)\w*"
    # "to the cart" and "al carro" go somewhere; "in the cart" is where things are.
    r"|\b(?:to|into|al|a la|a mi)\s+(?:the |my |mi |el |la )?"
    r"(?:cart|cut|card|carro|carrito|bolsa)\b",
    re.IGNORECASE,
)


def asks_cart_move(text: str) -> bool:
    """Whether ``text`` asks for a move on the cart (an add, a change, the
    checkout) rather than to see the cart."""
    return bool(_CART_MOVE.search(fold(text)))


_CALL_LANGUAGE = re.compile(
    r"\b(?:speak|talk|switch|change|continue|carry on|answer|reply|respond|go back|"
    r"habl\w*|cambi\w*|sig\w*|continu\w*|respond\w*|contest\w*|pas\w*|volv\w*)\b"
    r"[^.?!]{0,25}?\b(?:spanish|english|español|espanol|castellano|inglés|ingles)\b",
    re.IGNORECASE,
)
_TO_HIM = re.compile(
    r"^\W*(?:(?:hey|ok|okay|please|so|now|vale|oye|bueno|por favor)\W+)*"
    r"(?:speak|talk|switch|change|continue|carry|answer|reply|respond|go|habla|háblame|"
    r"hábleme|cambia|sigue|continúa|responde|contesta|pasa|vuelve)\b"
    r"|\b(?:you|we|us|let'?s|let us|i|i'?ll|puedes|podemos|podrías|podríamos|hablemos|"
    r"sigamos|cambiemos|continuemos|pasemos|volvamos|me|nos|hablamos|seguimos|cambiamos|"
    r"continuamos|pasamos|volvemos|puedo)\b",
    re.IGNORECASE,
)


def asks_call_language(text: str) -> bool:
    """Whether ``text`` asks him to speak another language — a request about
    this call, not a question about the store."""
    return bool(_CALL_LANGUAGE.search(text) and _TO_HIM.search(text))


_ABOUT_THE_CALL = re.compile(
    r"\b(?:can you hear me|are you there|me escuchas|me oyes|who are you|quien eres"
    r"|are you (?:a )?(?:bot|robot|real|human|ai)|eres (?:un )?(?:bot|robot|humano))\b",
    re.IGNORECASE,
)


def about_the_call(text: str) -> bool:
    """Whether ``text`` is only about the call: its language, or him."""
    short = len(text.split()) <= 12
    return short and (asks_call_language(text) or bool(_ABOUT_THE_CALL.search(fold(text))))


def asked_page(text: str, k: Knowledge | None = None) -> str | None:
    """The information page for what ``text`` asks about, or ``None``. A tab
    is a tab to switch to, a language request is about the call, and "add it
    to the cart" is a move, not the cart page."""
    if _ASKED_TAB.search(fold(text)) or asks_call_language(text):
        return None
    said = fold(text)
    adds = bool(_ADDS.search(said))
    named: list[tuple[int, tuple[str, ...]]] = []
    for rx, paths in _ASKED_PAGES:
        if (m := rx.search(said)) is None:
            continue
        if adds and paths == ("/checkout/cart",):
            continue
        named.append((m.start(), paths))
    if not named:
        return None
    paths = min(named)[1]
    if k is not None:
        return next((p for p in paths if p in _FIXED_PAGES or k.page(p) is not None), paths[0])
    return paths[0]


# ─── The section a sentence describes ──────────────────────────────────────────

_STOP = frozenset(
    """a an the and or but of to in on for with by at from as is are was were be been it its
    this that these those you your yours we our us they their them he she his her i me my
    can will just also so then than too very here there what which who how when where why all
    any each every more most some such no not only own same into out up down over under again
    once about after before both few other per via do does did have has had get gets got make
    makes made use uses used like let lets want would shall could should see show shows one two
    three section page el la los las un una unos unas de del y o u en por para con sin que se
    su sus es son al lo le les como mas muy tu te ti mi nos este esta estos estas ese esa eso
    hay ser estan tiene tienen puedes puede quieres aqui alli tambien pero cuando donde
    cannon home tienda producto productos precio precios desde aqui puedo""".split()  # noqa: SIM905
)
_SECTION_MIN = 6.0
_SECTION_LEAD = 1.5
_SECTION_MIN_WORDS = 4


def _stem(w: str) -> str:
    for suffix in ("ing", "ers", "er", "ed", "es", "s"):
        if len(w) > 4 and w.endswith(suffix):
            return w[: -len(suffix)]
    return w


def _terms(text: str) -> list[str]:
    return [
        _stem(w) for w in re.findall(r"[a-z0-9']+", fold(text)) if len(w) > 2 and w not in _STOP
    ]


def best_section(sentence: str, sections: list[tuple[str, str]]) -> str | None:
    """The heading of the one section ``sentence`` is about, of ``sections``
    (heading, text) on one page; ``None`` unless it is clearly one."""
    if sentence.rstrip().endswith("?"):
        return None
    said = " ".join(re.findall(r"[a-z0-9']+", fold(sentence)))
    quoted = [
        h
        for h, _ in sections
        if h
        and len(phrase := re.findall(r"[a-z0-9']+", fold(h))) >= 2
        and re.search(rf"\b{re.escape(' '.join(phrase))}\b", said)
    ]
    if quoted:
        return max(quoted, key=len)
    if len(sentence.split()) < _SECTION_MIN_WORDS:
        return None
    docs = [(h, set(_terms(h)), set(_terms(t))) for h, t in sections if h]
    if not docs:
        return None
    df: dict[str, int] = {}
    for _, head, text in docs:
        for w in head | text:
            df[w] = df.get(w, 0) + 1
    want = set(_terms(sentence))
    scored: list[tuple[float, str]] = []
    for heading, head, text in docs:
        score = 0.0
        for w in want:
            idf = math.log(1 + len(docs) / (1 + df.get(w, 0)))
            score += 2 * idf if w in head else 0.6 * idf if w in text else 0.0
        scored.append((score, heading))
    scored.sort(key=lambda s: -s[0])
    top, heading = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    return heading if top >= _SECTION_MIN and top - second >= _SECTION_LEAD else None


#: Capitalised words that are no name to ring: the store's own words are on
#: every card of every page, so ringing one rings the first of many.
_NOT_NAMES = frozenset(
    # A word list reads as words, so it stays a split string.
    """Cannon Home CANNON HOME King Super Súper Plaza Plazas Hilos RUT Chile Santiago
    I Here This That These Those Then Every Each You Your We Our They It And Or But
    So For With Would Shall Want Yes No First Second Third Next Also Plus Most Many Aquí Este
    Esta Estos Estas Eso Ese Esa Luego Cada Tú Usted Ustedes Nosotros Ellos Y O Pero Para Con
    Sí Primero Segundo Tercero También Además Sin Desde Hoy Mañana Lunes Martes Miércoles
    Jueves Viernes Sábado Domingo Monday Tuesday Wednesday Thursday Friday Saturday Sunday
    """.split()  # noqa: SIM905
)
_NAME = re.compile(
    r"[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúüñ0-9&']*(?:[ -][A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúüñ0-9&']*)*"
)


def named_on_page(sentence: str, text: str, plans: tuple[str, ...]) -> str | None:
    """A name the sentence says that the page shows, to ring as words."""
    for plan in plans:
        if re.search(rf"\b{re.escape(plan)}\b", sentence):
            return plan
    for m in _NAME.finditer(sentence):
        parts = [p for p in re.split(r"[ -]", m.group()) if p not in _NOT_NAMES]
        if not parts:
            continue
        name = " ".join(parts)
        opens = m.start() == 0 and len(parts) == 1 and not re.search(r"[A-Z].*[A-Z]", name)
        if len(name) < 3 or opens:
            continue
        if re.search(rf"\b{re.escape(name)}\b", text):
            return name
    return None


# ─── Moves and what answers them ───────────────────────────────────────────────

#: How long a move may take on the page before it is taken as unknown, by its
#: class: Stage's own table, but a confirmed move has longer. The store's
#: ``load`` takes over 15 s (trackers), which a page move's 25 s covers; the
#: bag, its login window, then the checkout's heavy full load took about 35 s
#: live (2026-10-23), and the drawer's minus and plus about four seconds a
#: press.
_MOVE_TAKES_S = {**RESULT_TIMEOUTS, MoveClass.CONFIRMED: 45.0}
#: A unit of his not reported played this long after it began is taken as done.
_PLAYOUT_MAX_S = 30.0
#: A cue's result with this detail says nothing to the model: the visitor
#: talked over it, or its words were never heard.
_QUIET_DROPS = frozenset({"interrupted", "stale"})
#: What a reply may write as the facet of a filter cue, folded, and the
#: listing's request variable it names.
_FACETS = {
    "tamano": "tamano",
    "tamanos": "tamano",
    "talla": "tamano",
    "size": "tamano",
    "color": "color",
    "colores": "color",
    "colour": "color",
    "hilos": "hilos",
    "threads": "hilos",
    "thread count": "hilos",
    "material": "material",
    "materiales": "material",
}
#: What a reply may write as a sort cue's order, folded.
_SORTS: dict[str, SortOrder] = {
    "price_asc": "price_asc",
    "price asc": "price_asc",
    "menor precio": "price_asc",
    "precio ascendente": "price_asc",
    "cheapest": "price_asc",
    "price_desc": "price_desc",
    "price desc": "price_desc",
    "mayor precio": "price_desc",
    "precio descendente": "price_desc",
    "newest": "newest",
    "nuevos": "newest",
    "novedades": "newest",
    "relevance": "relevance",
    "relevancia": "relevance",
}
#: Which source of a price wins over which: the live GraphQL read over the
#: page's (cached) copy, the page's over a card's.
_SOURCE_RANK = {"graphql": 3, "page": 2, "cart": 2, "listing": 1, "search": 1}
_SOURCE_SAID = {
    "graphql": "read live",
    "page": "on the product page",
    "cart": "in the cart",
    "listing": "on the listing",
    "search": "in the search suggestions",
}


@dataclasses.dataclass(frozen=True)
class Live:
    """What their screen last said of one product's price and stock."""

    path: str
    name: str = ""
    price: int | None = None
    regular_price: int | None = None
    in_stock: bool | None = None
    qty: int | None = None
    source: str = "page"
    at: float = 0.0

    def line(self, lang: Lang) -> str:
        bits: list[str] = []
        if self.price is not None:
            bits.append(f"price {_money(self.price, lang)}")
            if self.regular_price and self.regular_price > self.price:
                bits.append(f"was {_money(self.regular_price, lang)}")
        if self.in_stock is True:
            bits.append("available" + (f", {self.qty} left" if self.qty else ""))
        elif self.in_stock is False:
            bits.append("not available (out of stock)")
        return ", ".join(bits) + f" ({_SOURCE_SAID.get(self.source, self.source)})"


def _product_note(e: ProductShown, live: Live | None, lang: Lang) -> str:
    name = e.name or e.path
    if e.source == "graphql":
        note = f"[Live check of “{name}” ({e.path}): "
    else:
        note = f"[The product page in front: “{name}” ({e.path}). From the page: "
    seen = Live(e.path, name, e.price, e.regular_price, e.in_stock, e.qty, e.source)
    note += seen.line(lang) if (e.price is not None or e.in_stock is not None) else "no price read"
    note += "."
    if e.source == "graphql":
        if live is not None and live.source == "page" and live.price not in (None, e.price):
            note += f" The page showed {pesos(live.price or 0)}, an older copy: say this one."
        else:
            note += " This is the price to say."
    else:
        note += " The page may be an older copy; a live check follows."
    if e.rating is not None:
        note += f" Rating {e.rating:g}" + (f" from {e.reviews} reviews" if e.reviews else "") + "."
    if e.specs:
        specs = [f"{k}: {v}" for k, v in e.specs.items()]
        note += f" Especificaciones: {_clip(specs, _SPECS_IN_NOTE)}."
    return note + "]"


def _listing_note(e: ListingShown, lang: Lang) -> str:
    where = e.title or e.path
    note = f"[The listing in front: “{where}” ({e.path})"
    if e.count is not None:
        note += f", {e.count} products"
    if e.filters:
        note += ", filtered by " + ", ".join(
            f"{_FILTER_NAMES.get(k, k)} {v}" for k, v in e.filters.items()
        )
    if e.sort:
        note += f", sorted {e.sort}"
    note += "."
    if e.items:
        cards = [
            f"{i.name} ({i.path})" + (f", {_money(i.price, lang)}" if i.price is not None else "")
            for i in e.items
        ]
        note += f" On screen, in order: {_clip(cards, _LISTED_IN_NOTE)}."
    elif e.count == 0:
        note += " No product shows for these filters."
    return note + "]"


def _suggest_note(e: SearchSuggest, lang: Lang) -> str:
    if not e.items and not e.categories:
        return f"[The search box suggests nothing for “{e.query}”.]"
    items = [
        f"{i}. {s.name} ({s.path})" + (f", {_money(s.price, lang)}" if s.price is not None else "")
        for i, s in enumerate(e.items, 1)
    ]
    note = f"[The search box suggests for “{e.query}”: {'; '.join(items) or 'no products'}."
    if e.categories:
        note += f" Categories: {', '.join(e.categories)}."
    return note + "]"


def _prices_note(e: PricesRead, k: Knowledge, lang: Lang) -> str:
    lines: list[str] = []
    for i in e.items:
        name = i.name or (p.name if (p := k.product(i.path)) else i.path)
        live = Live(i.path, name, i.price, i.regular_price, i.in_stock, i.qty, "graphql")
        lines.append(f"{name} ({i.path}): {live.line(lang)}")
    note = f"[Live prices: {'; '.join(lines) or 'none'}."
    if e.missing:
        note += (
            f" Not found: {', '.join(e.missing)} — not buyable right now (out of stock or "
            "withdrawn): say so, never a price for them."
        )
    return note + "]"


def _cart_note(e: CartState, lang: Lang) -> str:
    if not e.items and not e.count:
        return "[Their cart is empty.]"
    items = [
        f"{i.name}"
        + (f" ({i.path})" if i.path else "")
        + f" x{i.qty}"
        + (f", {_money(i.price, lang)} each" if i.price is not None else "")
        for i in e.items
    ]
    note = f"[Their cart: {e.count or len(e.items)} items — {'; '.join(items)}."
    if e.subtotal is not None:
        note += f" Subtotal {_money(e.subtotal, lang)}."
    if e.free_shipping_left:
        note += (
            f" {_money(e.free_shipping_left, lang)} more for free shipping "
            "(Región Metropolitana only)."
        )
    elif e.free_shipping_left == 0:
        note += " It has free shipping (Región Metropolitana only)."
    return note + _CHECKOUT_IS_THEIRS + "]"


#: What the cart's lines end with: how far he may go, and what is theirs.
_CHECKOUT_IS_THEIRS = (
    " update_cart_item changes how many of a line they have, or takes it out. When they want to buy, start_checkout takes them to the delivery form as a guest; "
    "the RUT and the payment are theirs."
)


# ─── The checkout's delivery form ──────────────────────────────────────────────

#: The site's regions, exactly as its Región list names them (2026-10-23), with
#: the other names a Chilean uses for each.
_REGIONS: dict[str, tuple[str, ...]] = {
    "Antofagasta": (),
    "Araucanía": ("la araucania", "temuco"),
    "Arica y Parinacota": ("arica",),
    "Atacama": ("copiapo",),
    "Aysén del General Carlos Ibañez del Campo": ("aysen", "aisen", "coyhaique"),
    "Bío Bío": ("biobio", "bio-bio", "concepcion"),
    "Coquimbo": ("la serena",),
    "Libertador General Bernardo OHiggins": ("ohiggins", "o higgins", "rancagua", "libertador"),
    "Los Lagos": ("puerto montt",),
    "Los Ríos": ("valdivia",),
    "Magallanes y la Antártica Chilena": ("magallanes", "punta arenas"),
    "Maule": ("talca",),
    "Metropolitana": ("region metropolitana", "rm", "santiago", "metropolitana de santiago"),
    "Ñuble": ("chillan",),
    "Tarapacá": ("iquique",),
    "Valparaíso": ("valparaiso", "vina del mar", "quinta region"),
}
#: The longest each field takes, as the form's ``maxlength`` says.
_MAX_LENGTH = {"first_name": 15, "last_name": 15, "street": 40, "number": 6, "apartment": 6}
_FIELD_SAID = {
    "email": "email",
    "first_name": "nombre",
    "last_name": "apellidos",
    "rut": "RUT (theirs to type)",
    "phone": "teléfono",
    "region": "región",
    "comuna": "comuna",
    "street": "dirección",
    "number": "número",
    "apartment": "depto/casa",
    "delivery": "delivery method (theirs to choose)",
}
#: A RUT, however it is written: 12.345.678-5, 12345678-K, 7654321-0.
_RUT = re.compile(r"\b\d{1,2}\.?\d{3}\.?\d{3}\s*-\s*[\dkK]\b")
#: The word, as said: "mi RUT es…", "el run".
_RUT_WORD = re.compile(r"\b(?:rut|run)\b", re.IGNORECASE)
#: Thirteen or more digits in a row (spaces and dashes aside): a card.
_CARD = re.compile(r"(?:\d[ -]?){13,}")

#: Digits as a visitor says them, in either language: one by one, or as
#: Chileans read a phone, in pairs ("nueve, ochenta y dos, cuarenta y seis").
_DIGIT_WORDS = {
    "zero": 0,
    "oh": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "cero": 0,
    "uno": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
}
_SPANISH_TEENS = {
    "diez": 10,
    "once": 11,
    "doce": 12,
    "trece": 13,
    "catorce": 14,
    "quince": 15,
    "dieciseis": 16,
    "diecisiete": 17,
    "dieciocho": 18,
    "diecinueve": 19,
    "veinte": 20,
    "veintiuno": 21,
    "veintidos": 22,
    "veintitres": 23,
    "veinticuatro": 24,
    "veinticinco": 25,
    "veintiseis": 26,
    "veintisiete": 27,
    "veintiocho": 28,
    "veintinueve": 29,
}
_SPANISH_TENS = {
    "treinta": 30,
    "cuarenta": 40,
    "cincuenta": 50,
    "sesenta": 60,
    "setenta": 70,
    "ochenta": 80,
    "noventa": 90,
}
#: Fewer digits than this read out of what they said is no number to check against.
_SAID_DIGITS_MIN = 8


def said_digits(text: str) -> str:
    """The digits in what the visitor said, written, spoken one by one, or
    spoken in Spanish pairs (clini's reading)."""
    out: list[str] = []
    found = re.findall(r"\d+|[a-z]+", fold(text))
    i = 0
    while i < len(found):
        token = found[i]
        if token.isdigit():
            out.append(token)
        elif token in _SPANISH_TENS:
            tens = _SPANISH_TENS[token]
            unit = found[i + 2] if i + 2 < len(found) and found[i + 1] == "y" else ""
            if unit in _DIGIT_WORDS and _DIGIT_WORDS[unit] > 0:
                out.append(str(tens + _DIGIT_WORDS[unit]))
                i += 2
            else:
                out.append(str(tens))
        elif token in _SPANISH_TEENS:
            out.append(str(_SPANISH_TEENS[token]))
        elif token in _DIGIT_WORDS:
            out.append(str(_DIGIT_WORDS[token]))
        i += 1
    return "".join(out)


def spaced(digits: str) -> str:
    """Digits one by one, as he reads them back."""
    return " ".join(digits)


def chilean_phone(said: str) -> str | None:
    """A Chilean number as the form takes it: nine digits, a mobile starting
    with 9 or a Santiago landline starting with 2; a leading 56 is the
    country's. Never reshaped otherwise."""
    digits = "".join(c for c in said if c.isdigit())
    if len(digits) == 11 and digits.startswith("56"):
        digits = digits[2:]
    return digits if len(digits) == 9 and digits[0] in "92" else None


def email_address(said: str) -> str | None:
    address = "".join(said.split()).lower()
    return address if re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", address) else None


def region_label(said: str) -> str | None:
    """The site's name for the región said, or ``None``."""
    want = " ".join(re.findall(r"[a-z0-9]+", fold(said)))
    want = re.sub(r"^(?:la )?region (?:de |del )?", "", want).strip()
    for label, names in _REGIONS.items():
        own = " ".join(re.findall(r"[a-z0-9]+", fold(label)))
        if want in (own, *names) or (len(want) > 4 and own.startswith(want)):
            return label
    return None


def _looks_private(value: str) -> str | None:
    """Why ``value`` must not be typed anywhere: a RUT or a card number."""
    if _RUT.search(value) or _RUT_WORD.search(value):
        return "it looks like a RUT"
    if _CARD.search(value):
        return "it looks like a card number"
    return None


def _fields_said(names: list[str]) -> str:
    return ", ".join(_FIELD_SAID.get(n, n) for n in names)


def _checkout_note(e: CheckoutState) -> str:
    said = _fields_said
    note = "[The checkout's delivery form (/checkout)"
    if e.filled:
        note += f": filled — {said(e.filled)}"
    note += "."
    if e.region or e.comuna:
        note += f" Región {e.region or 'not chosen'}, comuna {e.comuna or 'not chosen'}."
    if e.missing:
        note += f" Still missing: {said(e.missing)}."
    if e.invalid:
        flagged = "; ".join(
            f"{_FIELD_SAID.get(i.field, i.field)}: “{i.message}”" if i.message else i.field
            for i in e.invalid
        )
        note += f" The form flags: {flagged}."
    if e.email_has_account:
        note += (
            " That email has an account: the site shows a password to sign in. Signing in is "
            "theirs; they can also carry on as a guest."
        )
    if e.delivery_options and not e.delivery:
        note += f" Delivery methods offered: {', '.join(e.delivery_options)} — theirs to choose."
    elif e.delivery:
        note += f" Delivery method chosen: {e.delivery}."
    if e.payment_open:
        note += " The payment step shows its options: it is theirs."
    return note + " The RUT, any password and the payment are theirs to complete; never yours.]"


# ─── The brain ─────────────────────────────────────────────────────────────────


class _VoicedStage(Stage):
    """Stage, with each cue's anchor spelled as the voice will say it: in
    Spanish the voice is handed "bidéo" for "video", and the page compares an
    anchor with what it hears."""

    def __init__(
        self,
        *,
        respell: Callable[[str], str],
        sent: Callable[[str, RawCue], None],
        **kw: Any,
    ) -> None:
        super().__init__(**kw)
        self._respell = respell
        self._sent = sent

    def cue(self, raw: RawCue) -> str | None:
        ref = super().cue(dataclasses.replace(raw, at=self._respell(raw.at)))
        if ref is not None:
            self._sent(ref, raw)
        return ref


class CannonHomeBrain(OpenAIBrain):
    """One per session. Javier: Cannon Home's knowledge and catalogue, a mirror
    of the visitor's tabs and of every price their screen has shown, in Spanish
    or English."""

    def __init__(
        self,
        *,
        client: AsyncOpenAI,
        model: str = MODEL,
        knowledge: Knowledge | None = None,
    ) -> None:
        self.kb = knowledge if knowledge is not None else kb.KNOWLEDGE
        super().__init__(
            client=client,
            system_instruction=_prompt(self.kb),
            model=model,
            reasoning=REASONING,
        )
        #: The catalogue's product and category names, as words: never a sign
        #: of the language a line of his is in.
        self._catalogue_words = name_words(
            [p.name for p in self.kb.products.values()]
            + [c.name for c in self.kb.categories.values()]
        )
        self.spoken: Lang = OPENING
        self._chosen = False
        self._last_heard = ""
        self._confirm: str | None = None
        self._fallback = FallbackLine()
        #: The tab in front as it last reported itself, and whether the model
        #: has seen it since it changed.
        self.page: PageChanged | None = None
        self._path = "/"
        self._page_unseen = False
        self.tabs: list[TabInfo] = []
        self._active = ""
        self._tabs_unseen = False
        self._talk: str | None = None
        #: What their screen last showed: the product page, the listing, the
        #: search box, the cart.
        self.product: ProductShown | None = None
        self.listing: ListingShown | None = None
        self.suggest: SearchSuggest | None = None
        self.cart: CartState | None = None
        #: The checkout's delivery form as it last reported itself, what he
        #: filled in it this call, and whether he has been taking them there.
        self.checkout: CheckoutState | None = None
        self._filled: dict[str, str] = {}
        self._checkout_asked = False
        #: Every price and stock their screen has reported this call, by path.
        self.prices: dict[str, Live] = {}
        self._cue_path: str | None = None
        #: The short idle window set now (ms; 0: the long one), and the one
        #: to set once he has finished speaking.
        self._idle_short = 0
        self._idle_want = _TALK_THROUGH_MS
        self._nudges = 0
        self._backstop: str | None = None
        self._paged = False
        self._shown: str | None = None
        #: Whether this reply dispatched a page move: a page cue after it
        #: would race the load it started.
        self._moved = False
        #: Whether this reply sent a confirmed move (an add, a cart change,
        #: the checkout): the cart page is never cued beside it.
        self._confirmed_sent = False
        self._heard: list[str] = []
        #: The written line for a confirmed move the page just confirmed:
        #: said as soon as the floor is free, before the model's next words.
        self._done: list[str] = []
        #: Every move on the page, cue or tool: sent, one serial move at a
        #: time, each answered once (:class:`~voqalize.sdk.stage.Stage`).
        self.stage = _VoicedStage(
            dispatch=lambda action: self.session.dispatch(action),
            moves=MOVES,
            resolve=self._resolve,
            backstop=self._auto_cues,
            result_timeout_s=_MOVE_TAKES_S,
            on_drop=self._dropped,
            on_landed=self._landing_line,
            respell=lambda at: _anchor_for_voice(at, self.spoken),
            sent=self._cue_sent,
        )
        #: What each cue sent said, as he wrote it, by its call_ref: for the
        #: line about its result (and a late one after an ``unknown``).
        self._cues: dict[str, str] = {}
        #: The move the store is slow on and his one line for it, said in the
        #: next quiet spell if it is still running then.
        self._hold: tuple[str, str] | None = None
        #: Expiry on a timer, and the look for slow moves: one task a call.
        self._watching: asyncio.Task[None] | None = None
        #: Why the listing cannot take the filter or sort cue being resolved:
        #: said to him when Stage drops it (:meth:`_dropped`).
        self._refusal: str | None = None
        #: Turns running with tools off (a quiet spell's): a move called in one
        #: anyway is refused, never sent.
        self._tools_off = 0
        #: The page's answers that came in since his last turn: talked
        #: through together, once, in the next short quiet spell.
        self._outcomes: list[str] = []
        self._turns = 0
        self._playing = 0
        self._played_at = 0.0
        self._idle_deferred = False

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        init = session.init or {}
        self._path = canonical_path(str(init.get("path") or "/"))
        chosen = init.get("lang")
        self._chosen = chosen in LANGUAGE_NAMES
        self.spoken = "en" if chosen == "en" else OPENING
        await session.configure(
            Config(
                stt=SttConfig(language=self.spoken, patience=CANNONHOME_PATIENCE),
                tts=TtsConfig(voice=VOICE, language=self.spoken),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
            )
        )
        logger.info(
            "cannonhome: session start on {} in {}{}",
            self._path,
            self.spoken,
            " (chosen)" if self._chosen else "",
        )
        if self._chosen:
            self._note(_chosen_note(self.spoken, "before the call"))
        self._watching = asyncio.create_task(self._watch_stage())

    async def on_session_end(self, session: Session) -> None:
        if self._watching is not None:
            self._watching.cancel()
            self._watching = None
        await super().on_session_end(session)

    async def _watch_stage(self) -> None:
        """For the whole call: a move the page never answered is said as
        unknown when its time is up, not at his next turn; and a confirmed or
        reversible move the store is slow on gets his one holding line."""

        async def slow() -> None:
            while True:
                await asyncio.sleep(_HOLD_POLL_S)
                self._hold_slow()

        await asyncio.gather(self.stage.watch(self._expired), slow())

    def _expired(self, r: StageResult) -> None:
        if (note := self._settled(r)) is not None:
            self._note(note)

    def _hold_slow(self) -> None:
        """A move running past Stage's holding time, with the floor free: his
        written line for it, in the next quiet spell, which is made short now.
        Looked for only while the floor is free, so it is said, not skipped."""
        if self._holding_floor():
            return
        for run in self.stage.holding():
            line = holding_line(run.move.id, self.spoken)
            logger.info(
                "cannonhome: {} {} still running at {:.1f} s ({}); holding line {!r}",
                run.call_ref,
                run.move.id,
                run.seconds,
                run.phase or "no phase",
                line,
            )
            self._hold = (run.call_ref, line)
            self._shorten_idle(_DONE_MS)

    def _take_hold(self) -> str | None:
        """The holding line waiting, if its move is still running."""
        hold, self._hold = self._hold, None
        if hold is None or all(r.call_ref != hold[0] for r in self.stage.running()):
            return None
        return hold[1]

    async def greet(self, session: Session) -> str:
        """The opener, written not generated."""
        line = greeting(self._path, self.spoken)
        return for_the_voice(line) if self.spoken == "es" else names_for_the_voice(line)

    async def on_finalize(self, session: Session, fin: Finalize) -> None:
        """What was heard goes into the model's context, spelled as written."""
        heard = from_the_voice(fin.heard)
        if heard != fin.heard:
            fin = dataclasses.replace(fin, heard=heard)
        await super().on_finalize(session, fin)
        self._playing = max(0, self._playing - 1)
        self._floor_free()

    def on_user_message(self, session: Session, msg: UserMessage) -> AsyncGenerator[Speech, None]:
        return self._own_turn(self._answer(session, msg))

    async def _answer(self, session: Session, msg: UserMessage) -> AsyncGenerator[Speech, None]:
        """The visitor's turn: the language they speak (unless they chose one),
        the screen read in. The runtime acknowledges them while the model
        thinks (``Config.ack``, on by default)."""
        self._last_heard = msg.text
        heard = None if self._chosen else heard_language(msg.text, self.spoken, self._language_of)
        if heard is not None and heard != self.spoken:
            await session.configure(self._speaking(heard))
            logger.info("cannonhome: language -> {} (heard)", heard)
        if holds_spanish(msg.text, self.spoken, self._language_of):
            logger.info("cannonhome: held in Spanish: {!r}", msg.text)
            self._note(HELD_NOTE)
        self._talk = None
        self._expire()
        # They spoke first: the page's answers are in the context as notes,
        # and he answers them with what they said.
        self._outcomes.clear()
        self._done.clear()
        self.stage.take_lines()
        self._hold = None
        self._idle_deferred = False
        self._playing = 0
        self._nudges = 0
        self._heard = [*self._heard[-3:], msg.text]
        self._backstop = (
            None
            if asks_call_language(msg.text)
            else asked_page(msg.text, self.kb) or self._backstop
        )
        if self._backstop in _MOVE_PAGES and self._asked_cart_move():
            self._backstop = None
        self._restore_idle()
        self._read_in_screen()
        async for event in super().on_user_message(session, msg):
            yield event

    async def _own_turn(self, turn: AsyncGenerator[Speech, None]) -> AsyncGenerator[Speech, None]:
        """``turn``, counted while it runs and for each unit until it has
        played: the floor is his, and no short idle window is set under it."""
        self._turns += 1
        try:
            async for event in turn:
                if isinstance(event, SpeechStart):
                    self._playing += 1
                    self._played_at = time.monotonic()
                yield event
        finally:
            await turn.aclose()
            self._turns -= 1
            self._floor_free()

    def on_user_idle(self, session: Session, idle: UserIdle) -> AsyncGenerator[Speech, None]:
        return self._own_turn(self._quiet(session, idle))

    def _quiet(self, session: Session, idle: UserIdle) -> AsyncGenerator[Speech, None]:
        """A quiet spell — the only floor he gets without the visitor speaking.
        A result the page produced is talked through here; otherwise a nudge,
        twice, then silence. Tools are off: a quiet spell never moves the page."""
        self._restore_idle()
        self._backstop = None
        self._expire()
        # What landed on screen, the latest line of it (a filter's line is
        # past once the next filter lands), then any confirmed move's.
        landing = self.stage.take_lines()[-1:]
        done = " ".join([*landing, *self._done])
        self._done = []
        hold = self._take_hold()
        if hold is not None and not done and not self._outcomes and self._talk is None:
            # The store is slow on a move: said so, written, never asked of
            # the model, and no nudge counted.
            respell = for_the_voice if self.spoken == "es" else names_for_the_voice
            return say_line(self, respell(hold))
        if landing and not self._outcomes and self._talk is None:
            # Said first, written; the model may add one sentence.
            # The landing line already said the count, the options and the
            # first card: a second hop that says them again, or otherwise,
            # is heard as a correction of it.
            self._note(
                f"[{landed_ask(done)} Never restate or change its count, its filters or its "
                "first product.]"
            )
            return self._reply(session, ToolChoice.NONE, first=done)
        if (ask := self._take_ask(said=done)) is not None:
            self._note(ask)
            return self._reply(session, ToolChoice.NONE, first=done or None)
        if self._confirm is not None:
            line, self._confirm = self._confirm, None
            return say_line(self, line)
        if self._nudges >= _IDLE_NUDGES:
            return _silence()
        self._nudges += 1
        self._read_in_screen()
        quiet = f"The visitor has said nothing for about {round(idle.idle_ms / 1000)} seconds."
        if self._nudges == 1:
            ask = (
                "Speak into the quiet, briefly, as the guide beside them would: one useful thing "
                "about what is on their screen, or one question that helps you help them. Never "
                "ask whether they are still there, and never repeat your last line."
            )
        else:
            ask = (
                "Still quiet. One last, light offer, different from your last: something you "
                "could show them next. Then let them browse."
            )
        self._note(f"{quiet} {ask}")
        return self._reply(session, ToolChoice.NONE)

    def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        return self._reply(session, None)

    async def _reply(
        self, session: Session, tools: ToolChoice | None, *, first: str | None = None
    ) -> AsyncGenerator[Speech, None]:
        """The model's turn, with its cues taken out of the speech and sent to
        the page; ``tools`` limits it (``None``: any). A move with no words says
        its written line (:func:`landed`); a turn with nothing at all, or only a
        promise, is asked once more with tools off. ``first`` is a written line
        said before the model is asked (a confirmed move that is done); the
        model may then add to it, or say nothing."""
        if (line := self._confirm) is not None:
            self._confirm = None
            async for event in say_line(self, line):
                yield event
        if first is not None:
            logger.info("cannonhome: done line {!r}", first)
            respell = for_the_voice if self.spoken == "es" else names_for_the_voice
            async for event in say_line(self, respell(first)):
                yield event
        self._cue_path = self._path
        self._paged = False
        self._shown = None
        self._moved = False
        self._confirmed_sent = False
        said = first or ""
        off = tools is ToolChoice.NONE
        if off:
            self._tools_off += 1
        try:
            model = (
                super().respond(session)
                if tools is None
                else self.respond_with(session, tools=tools)
            )
            turn = self._fallback.speak_if_silent(self, model)
            async for event in self._spelled(self._written(session, self._cued(turn))):
                if isinstance(event, SpeechChunk):
                    said += event.text
                yield event
            if not _PROMISE.sub("", _CUE_TEXT.sub(" ", said)).strip(" .,!?¡¿…"):
                logger.warning("cannonhome: the model returned nothing; asking once more")
                again = self._written(session, self._cued(self._talk_now(session)))
                async for event in self._spelled(again):
                    yield event
        finally:
            if off:
                self._tools_off -= 1

    async def _written(
        self, session: Session, turn: AsyncGenerator[Speech, None]
    ) -> AsyncGenerator[Speech, None]:
        """``turn``, with each unit held back until its first sentence is in,
        and both legs moved to the language it is in when it is not the call's."""
        held: list[Speech] = []
        text = ""

        async def release() -> AsyncGenerator[Speech, None]:
            nonlocal held, text
            written = language_of(
                text, sure=False, names=self._names_on_screen(), vocabulary=self._catalogue_words
            )
            if written == "en" and not may_write_english(
                self._last_heard, self.spoken, self._language_of
            ):
                written = None
            if written is not None and written != self.spoken:
                await session.configure(self._speaking(written))
                logger.info("cannonhome: language -> {} (written)", written)
            out, held, text = held, [], ""
            for event in out:
                yield event

        async for event in turn:
            if isinstance(event, SpeechStart):
                held.append(event)
                continue
            if not held:
                yield event
                continue
            held.append(event)
            if isinstance(event, SpeechChunk):
                text += event.text
                if len(text) < _WRITTEN_ENOUGH and not _SENTENCE_END.search(text):
                    continue
            async for out in release():
                yield out
        if held:
            async for out in release():
                yield out

    def _language_of(self, text: str, *, sure: bool = True) -> Lang | None:
        """:func:`language_of` for what the visitor said, the names on their
        screen set aside."""
        return language_of(text, sure=sure, names=self._names_on_screen())

    def _names_on_screen(self) -> list[str]:
        """The product and category names their screen and cart show: said in
        either language, so never what decides it."""
        names: list[str] = []
        if self.product is not None:
            names.append(self.product.name)
        if self.listing is not None:
            names += [self.listing.title, *(i.name for i in self.listing.items)]
        if self.suggest is not None:
            names += [*(i.name for i in self.suggest.items), *self.suggest.categories]
        if self.cart is not None:
            names += [i.name for i in self.cart.items]
        return names

    def _spelled(self, turn: AsyncGenerator[Speech, None]) -> AsyncGenerator[Speech, None]:
        """``turn``, with its speech spelled as the voice must read it."""

        async def spelled() -> AsyncGenerator[Speech, None]:
            async for event in turn:
                if isinstance(event, SpeechChunk):
                    respell = for_the_voice if self.spoken == "es" else names_for_the_voice
                    event = SpeechChunk(respell(event.text))
                yield event

        return spelled()

    def _cued(self, turn: AsyncGenerator[Speech, None]) -> AsyncGenerator[Speech, None]:
        """``turn`` with every cue taken out of its text and sent to the page
        as a Stage cue, anchored to the words after it; the page the visitor
        asked about first, when the reply brings no cue of its own."""
        return self.stage.cued(self._backstopped(turn))

    def _cue_sent(self, ref: str, raw: RawCue) -> None:
        self._cues[ref] = f"{{{raw.verb}: {' | '.join(raw.args)}}}"

    async def _backstopped(
        self, turn: AsyncGenerator[Speech, None]
    ) -> AsyncGenerator[Speech, None]:
        try:
            async for event in turn:
                if isinstance(event, SpeechChunk):
                    event = SpeechChunk(self._with_backstop(event.text))
                yield event
        finally:
            await turn.aclose()

    def _with_backstop(self, chunk: str) -> str:
        """The reply's first words, with the page the visitor asked about cued
        in front of them when the reply brings no cue of its own."""
        if self._backstop is None or not chunk.strip():
            return chunk
        path, self._backstop = self._backstop, None
        if "{" in chunk or self._moved or path == self._path:
            return chunk
        # The cart and the checkout are reached by their moves, whose tool
        # call comes after these words: a page cue for them here would take
        # the visitor to the cart while the add is still under way.
        if path in _MOVE_PAGES and (self._confirmed_sent or self._asked_cart_move()):
            logger.info("cannonhome: no backstop to {}: a cart move is asked", path)
            return chunk
        logger.info("cannonhome: the reply has no cue; showing {} first", path)
        return f"{{page: {path}}}{chunk}"

    def _asked_cart_move(self) -> bool:
        """Whether the visitor's last two fragments ask for a move on the
        cart: an add said in one fragment and "to the cart" in the next is one."""
        return asks_cart_move(" ".join(self._heard[-2:]))

    def _known_path(self, value: str) -> str | None:
        """The store path a page cue names, as the store links it, or ``None``."""
        path = canonical_path(value)
        if _NEVER.match(path):
            return None
        if path in _FIXED_PAGES:
            return path
        if (page := self.kb.page(path)) is not None:
            return page.path
        if (cat := self.kb.category(path)) is not None:
            return cat.path
        if path.endswith(".html") and (
            self.kb.product(path) is not None or path in self.prices or self._on_screen(path)
        ):
            p = self.kb.product(path)
            return p.path if p is not None else path
        return None

    def _on_screen(self, path: str) -> bool:
        """Whether their screen has listed this product: a card, a suggestion."""
        if self.listing is not None and any(
            canonical_path(i.path) == path for i in self.listing.items
        ):
            return True
        return self.suggest is not None and any(
            canonical_path(i.path) == path for i in self.suggest.items
        )

    def _auto_cues(
        self, sentence: str, index: int, placed: tuple[tuple[str, tuple[str, ...]], ...]
    ) -> list[tuple[str, list[str]]]:
        """The moves a sentence of his needs and did not bring: the page its
        first sentence is about, and the section or name on the page it describes."""
        out: list[tuple[str, list[str]]] = []
        verbs = {v for v, _ in placed}
        pages = [
            p for v, a in placed if v == "page" and a and (p := self._known_path(a[0])) is not None
        ]
        path = pages[-1] if pages else self._cue_path
        if (
            index == 0
            and not self._paged
            and not self._moved
            and "page" not in verbs
            and not verbs & {"show", "faq", "filter", "sort"}
            and self._shown is None
        ):
            asked = asked_page(sentence, self.kb)
            if (
                asked is not None
                # The cart and the checkout are moves (show_cart,
                # start_checkout), never his own sentence's page: "The items
                # are in your cart" took a visitor who asked about delivery to
                # the cart page mid-answer (2026-10-23).
                and asked not in _MOVE_PAGES
                and asked != self._path
                and self._known_path(asked) is not None
                and self._section_for(sentence, self._path) is None
            ):
                logger.info("cannonhome: he talks about {} with no cue; opening it", asked)
                out.append(("page", [asked]))
                path = asked
        self._cue_path = path
        # A sentence that filters or sorts is about the grid it changes.
        if verbs & {"show", "faq", "filter", "sort"}:
            return out
        shown = self._section_for(sentence, path)
        if shown is not None and shown != self._shown:
            out.append(("show", [shown]))
        return out

    def _section_for(self, sentence: str, path: str | None) -> str | None:
        """The heading or words on ``path`` that ``sentence`` is about."""
        if path is None:
            return None
        page = self.kb.page(path)
        live = self.page is not None and canonical_path(self.page.path) == path
        if page is None:
            if not live or self.page is None:
                return None
            return best_section(sentence, [(h, "") for h in self.page.headings])
        heading = best_section(sentence, [(s.heading, s.text) for s in page.sections])
        if heading is not None:
            return heading
        plans = tuple(self.page.plans) if live and self.page is not None else ()
        text = " ".join([page.text, *(f"{s.heading} {s.text}" for s in page.sections)])
        return named_on_page(sentence, text, plans)

    def _resolve(self, move: Move, args: list[str]) -> list[str] | None:
        """A cue's arguments checked against the site, as the page will take
        them; ``None`` drops it. A move this reply already sent loads the page,
        so a cue after it would race the load. A filter or sort the listing
        cannot take is said to him, so he does not say it happened."""
        self._refusal = None
        if self._moved:
            logger.info(
                "cannonhome: cue {} {} dropped: a move this reply loads the page", move.id, args
            )
            return None
        want = args[0] if args else ""
        out: list[str] | None
        match move.id:
            case "page.open":
                out = self._resolve_page(want)
            case "page.faq":
                out = self._resolve_faq(want)
            case "page.show":
                out = self._resolve_show(want)
            case "listing.filter":
                out = self._resolve_filter(want, args[1] if len(args) > 1 else "")
            case "listing.sort":
                out = self._resolve_sort(want)
            case _:
                out = None
        return out

    def _resolve_page(self, value: str) -> list[str] | None:
        path = self._known_path(value)
        if path is None:
            return None
        self._cue_path = path
        self._paged = True
        return [path]

    def _moved_to(self) -> str | None:
        """The page a cue of this reply took them to, when not the one in front."""
        moved = self._cue_path is not None and self._cue_path != self._path
        return self._cue_path if moved else None

    def _resolve_faq(self, asked: str) -> list[str] | None:
        target = self.kb.page(self._cue_path) if self._cue_path is not None else None
        elsewhere = self._moved_to()
        faqs = [f.q for f in target.faqs] if target else list(self._faqs())
        if elsewhere is None:
            faqs = list(dict.fromkeys([*self._faqs(), *faqs]))
        question = _match(asked, faqs)
        if question is None:
            found = self._faq_elsewhere(asked)
            if found is None:
                return None
            self._cue_path, question = found
            return [question[:80], found[0]]
        return [question[:80], elsewhere] if elsewhere else [question[:80]]

    def _resolve_show(self, asked: str) -> list[str]:
        target = self.kb.page(self._cue_path) if self._cue_path is not None else None
        elsewhere = self._moved_to()
        headings = (
            target.headings
            if elsewhere and target
            else self._headings() or (target.headings if target else ())
        )
        shown = (_match(asked, headings) or asked)[:80]
        self._shown = shown
        return [shown, elsewhere] if elsewhere else [shown]

    def _listing_for_cue(self) -> tuple[str, Category | None] | None:
        """The listing a filter or sort cue applies to: the one a page cue of
        this reply opens, else the one in front; ``None`` when that is no
        listing."""
        path = self._cue_path or self._path
        cat = self.kb.category(path)
        if cat is not None:
            return cat.path, cat
        if self.listing is not None and canonical_path(self.listing.path) == path:
            return path, None
        page = self.page
        if (
            page is not None
            and canonical_path(page.path) == path
            and page.kind in ("category", "search")
        ):
            return path, None
        return None

    def _cue_refused(self, why: str) -> None:
        """A filter or sort he wrote that the listing cannot take: ``None``
        from the resolver, and :meth:`_dropped` says why."""
        self._refusal = why

    def _dropped(self, raw: RawCue, why: Dropped) -> None:
        """A cue Stage did not send. A filter or sort the listing cannot take
        is said to him, so he does not say it happened: nothing is sent, and
        he says so in the next short quiet spell. Any other is only logged."""
        refusal, self._refusal = self._refusal, None
        if why != "unresolved" or refusal is None:
            logger.info("cannonhome: cue {} {} dropped ({})", raw.verb, list(raw.args), why)
            return
        cue = f"{{{raw.verb}: {' | '.join(raw.args)}}}"
        logger.info("cannonhome: cue {} refused: {}", cue, refusal)
        self._note(f"[Not done on the page ({cue}): {refusal}. It was not applied.]")
        self._answered(f"{cue} not done: {refusal}")

    def _resolve_filter(self, facet: str, value: str) -> list[str] | None:
        listing = self._listing_for_cue()
        if listing is None:
            self._cue_refused(
                f"the page it applies to ({self._cue_path or self._path}) is not a listing; "
                "open the listing with a page cue first",
            )
            return None
        path, cat = listing
        var = _FACETS.get(norm(facet))
        if var is None:
            has = ", ".join(_FILTER_NAMES[v] for v in (cat.filters if cat else _FILTER_NAMES))
            self._cue_refused(f"a listing has no filter '{facet}' (this one has: {has})")
            return None
        if not value.strip():
            self._cue_refused("say which option, as the listing writes it")
            return None
        refused: list[str] = []
        labels = _filter_values(cat, var, value, refused)
        if not labels:
            self._cue_refused("; ".join(refused) or "say which option, as the listing writes it")
            return None
        # Several options of one filter ride one cue, ", " between them: the
        # page adds each to what is already active.
        return [var, ", ".join(labels)[:160], path]

    def _resolve_sort(self, order: str) -> list[str] | None:
        listing = self._listing_for_cue()
        if listing is None:
            self._cue_refused("the page it applies to is not a listing")
            return None
        sort = _SORTS.get(norm(order))
        if sort is None:
            self._cue_refused("sort by price_asc, price_desc, newest or relevance")
            return None
        return [sort, listing[0]]

    def _talk_now(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The one extra request a turn that said and moved nothing gets: tools
        declared, none callable."""
        return self.respond_with(session, tools=ToolChoice.NONE)

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Page→brain events, folded in silently: no floor taken, no turn."""
        event = CANNONHOME_EVENTS.parse(msg)
        if event is None:
            return
        logger.info("cannonhome: {} — {}", type(event).__voqal_event__, event)
        if isinstance(event, LanguageRequested):
            await self._requested(session, event)
            return
        if (note := self.apply_event(event)) is not None:
            self._note(note)

    async def _requested(self, session: Session, event: LanguageRequested) -> None:
        """The visitor pressed the other language on the toggle: switched in
        code, confirmed in his next turn."""
        if event.language == self.spoken:
            return
        was = self.spoken
        try:
            await session.configure(self._speaking(event.language))
        except RequestRejected as rejected:
            logger.warning("cannonhome: switch to {} refused: {}", event.language, rejected)
            self.spoken = was
            session.dispatch(LanguageChanged(language=was))
            return
        logger.info("cannonhome: language -> {} (toggle)", event.language)
        self._chosen = True
        self._confirm = TOGGLE_CONFIRM[event.language]
        self._shorten_idle()
        self._note(_chosen_note(event.language, "on the toggle"))

    def _speaking(self, language: Lang) -> Config:
        """Both legs of ``language``, recorded as the one he speaks now, and the
        widget's toggle moved to it."""
        if language != self.spoken:
            self.session.dispatch(LanguageChanged(language=language))
        self.spoken = language
        return Config(
            stt=SttConfig(language=language, patience=CANNONHOME_PATIENCE),
            tts=TtsConfig(voice=VOICE, language=language),
        )

    # ─── Page → brain ───────────────────────────────────────────────────

    def apply_event(self, event: CannonHomeEvent) -> str | None:
        """Patch the mirror; return the line the model should see."""
        match event:
            case PageChanged():
                self.page = event
                self._path = canonical_path(event.path)
                self._page_unseen = True
                if event.kind != "product":
                    self.product = None
                return None
            case TabsChanged():
                self.tabs = event.tabs
                self._active = event.active
                self._tabs_unseen = True
                return None
            case LanguageRequested():
                return None
            case ProductShown():
                path = canonical_path(event.path)
                before = self.prices.get(path)
                self.product = event
                self._path = path
                self._remember(
                    path,
                    event.name,
                    event.price,
                    event.regular_price,
                    event.in_stock,
                    event.qty,
                    event.source,
                )
                self.stage.landed(
                    _PRODUCT_MOVES, event=event, fits=lambda landing: lands(landing, event)
                )
                return _product_note(event, before, self.spoken)
            case ListingShown():
                self.listing = event
                for i in event.items:
                    self._remember(i.path, i.name, i.price, i.regular_price, None, None, "listing")
                self.stage.landed(
                    _LISTING_MOVES, event=event, fits=lambda landing: lands(landing, event)
                )
                return _listing_note(event, self.spoken)
            case SearchSuggest():
                self.suggest = event
                for s in event.items:
                    self._remember(s.path, s.name, s.price, None, None, None, "search")
                return _suggest_note(event, self.spoken)
            case PricesRead():
                for i in event.items:
                    self._remember(
                        i.path, i.name, i.price, i.regular_price, i.in_stock, i.qty, "graphql"
                    )
                return _prices_note(event, self.kb, self.spoken)
            case CheckoutState():
                return self._checkout_changed(event)
            case CartState():
                self.cart = event
                for i in event.items:
                    if i.path:
                        self._remember(i.path, i.name, i.price, None, None, None, "cart")
                return _cart_note(event, self.spoken)
            case StageHello():
                self.stage.handle(event)
                return None
            case StageProgress():
                # A slow move is alive: Stage gives it its time again.
                self.stage.handle(event)
                return None
            case StageResult():
                result = self.stage.handle(event)
                return None if result is None else self._settled(result)

    def _settled(self, r: StageResult) -> str | None:
        """What the model hears of one move's final result. A tool's move is
        talked through, done or not, in the next short quiet spell. A cue is a
        line for his next turn, by its class: nothing for a look that landed,
        one line for a page or a filter; a look or a page that missed is a
        quiet line, and a filter or sort that missed is talked through. A cue
        the visitor talked over, or whose words never came, says nothing. A
        result that comes ``late``, after he was told the move was unknown,
        corrects that (:meth:`_late`)."""
        if r.moved:
            return None
        # The move he made: also for one finished on the page it loaded (a
        # search that opened a product), Stage reports it under its own id.
        move = self.stage.moves.get(r.move)
        if move is None:
            return None
        if self._hold is not None and self._hold[0] == r.call_ref:
            self._hold = None
        if r.late:
            return self._late(r, move)
        landed_ok = r.outcome in ("applied", "partial")
        why = self._why(r)
        if move.verb is None:
            name = move.id
            if r.outcome == "applied" and self.stage.shown(r.call_ref):
                # Its landing line said it already: the result only confirms.
                return f"[The page confirms {name}: {r.detail or 'done'}.]"
            if landed_ok:
                detail = r.detail or "done"
                # Some but not all: never taken for the whole of it.
                if r.outcome == "partial":
                    detail = self._partial(r)
                    self._answered(f"{name} only partly done: {detail}")
                    return (
                        f"[The page did only part of {name}: {detail}. Say plainly what is done "
                        "and what is not; never that all of it worked.]"
                    )
                done = (
                    done_line(name, detail, self.spoken)
                    if move.cls is MoveClass.CONFIRMED
                    else None
                )
                self._answered(f"{name} done: {detail}", done=done)
                return f"[The page confirms {name}: {detail}.]"
            self._talk = None
            self._answered(f"{name} not done: {why}")
            return (
                f"[Not done on the page ({name}): {why}. Tell the visitor plainly and offer "
                "what you can do instead; never say it worked.]"
            )
        # Kept past an unknown: a late result names the cue too.
        cue = (
            self._cues.get(r.call_ref, f"{{{move.verb}: …}}")
            if r.outcome == "unknown"
            else self._cues.pop(r.call_ref, f"{{{move.verb}: …}}")
        )
        if r.outcome == "partial":
            # A cue of several options that put on only some: the visitor
            # heard all of them, so what is missing is said.
            detail = self._partial(r)
            self._answered(f"{cue} only partly done: {detail}")
            return (
                f"[On the page, only part of {cue}: {detail}. Say plainly which are on and "
                "which are not; never that all of it worked.]"
            )
        if landed_ok:
            if POLICY[move.cls].tells_model == "on_failure":
                return None
            return f"[On the page, as you said it: {cue} — {r.detail or 'done'}.]"
        if r.outcome == "refused" and r.detail in _QUIET_DROPS:
            return None
        if move.cls is MoveClass.REVERSIBLE:
            self._answered(f"{cue} not done: {why}")
            return (
                f"[Not done on the page ({cue}): {why}. The visitor heard you say it: tell "
                "them plainly, and offer what the listing has instead.]"
            )
        return (
            f"[A screen cue of yours did not land ({why}). If the visitor asks where it is, "
            "show it again; otherwise carry on.]"
        )

    def _late(self, r: StageResult, move: Move) -> str | None:
        """A result after he was told the move was not confirmed: a short
        correction, and for a confirmed move the page did after all, its
        written line ("Done after all, …") said as soon as the floor is free."""
        landed_ok = r.outcome in ("applied", "partial")
        if move.verb is not None:
            cue = self._cues.pop(r.call_ref, f"{{{move.verb}: …}}")
            if landed_ok:
                return (
                    f"[Correction: your screen cue {cue} did land after all — "
                    f"{r.detail or 'done'}.]"
                )
            return None  # Already said as not confirmed; nothing to correct.
        name = move.id
        if r.outcome == "partial":
            detail = self._partial(r)
            self._answered(f"{name} only partly done after all: {detail}")
            return (
                f"[Correction: the page did part of {name} after all: {detail}. You said it was "
                "not confirmed: say in a few words what is done and what is not.]"
            )
        if landed_ok:
            detail = r.detail or "done"
            done = (
                late_done_line(name, detail, self.spoken)
                if move.cls is MoveClass.CONFIRMED
                else None
            )
            self._answered(f"{name} done after all: {detail}", done=done)
            return (
                f"[Correction: the page did {name} after all: {detail}. You said it was not "
                "confirmed: it is done.]"
            )
        return (
            f"[The page has now answered {name}: {self._why(r)}. It is not done; never say "
            "it worked.]"
        )

    @staticmethod
    def _partial(r: StageResult) -> str:
        """A partial result in the page's words: what it did, then what not."""
        missed = [
            refusal.why
            + (f" (it offers: {', '.join(refusal.options[:12])})" if refusal.options else "")
            for refusal in r.refused
        ]
        done = r.detail or "some of it"
        return f"{done}; not done: {'; '.join(missed)}" if missed else done

    @staticmethod
    def _why(r: StageResult) -> str:
        """Why a move did not land, in the page's words, with what it offers."""
        why = r.detail or r.outcome
        offers = [o for refusal in r.refused for o in refusal.options]
        if offers:
            why += f" (it offers: {', '.join(offers[:12])})"
        if r.outcome == "unknown":
            why = f"not confirmed — {why}"
        return why

    def _expire(self) -> None:
        """Moves the page never answered, as unknown: said like any result."""
        for r in self.stage.expire():
            if (note := self._settled(r)) is not None:
                self._note(note)

    def _checkout_changed(self, event: CheckoutState) -> str:
        """The delivery form's report, as a note; and, once he is working on
        it, the ask that has him talk through what changed."""
        before = self.checkout
        self.checkout = event
        note = _checkout_note(event)
        if not self._checkout_asked:
            return note
        ask: str | None = None
        flagged = [(i.field, i.message) for i in event.invalid]
        was_flagged = [(i.field, i.message) for i in before.invalid] if before else []
        ours = [m for m in event.missing if m not in ("rut", "delivery")]
        if before is None:
            ask = (
                "The checkout's delivery form is open, as a guest. Say so in one sentence, and "
                "ask for the first one or two things it needs, in the form's order. Never ask "
                "for the RUT: it is theirs to type."
            )
        elif event.email_has_account and not before.email_has_account:
            ask = (
                "That email has an account on the store: the site shows a password. Say in one "
                "sentence that signing in is theirs, or they can carry on as a guest."
            )
        elif flagged and flagged != was_flagged:
            ask = (
                "The form flags a field, in the line above. Say in one sentence what it says, "
                "and ask for the right one."
            )
        elif not ours and before.missing != event.missing:
            ask = (
                "Every delivery detail you can fill is in. Say so in one sentence, and that the "
                "RUT, the delivery method and the payment are theirs to complete."
            )
        if ask is not None:
            self._talk = ask
            self._shorten_idle()
        return note

    def _remember(
        self,
        path: str,
        name: str,
        price: int | None,
        regular_price: int | None,
        in_stock: bool | None,
        qty: int | None,
        source: str,
    ) -> None:
        """One more thing their screen said of a product's price or stock. A
        live read is not overwritten by a cached or card copy of it."""
        if price is None and in_stock is None:
            return
        key = _product_path(path)
        before = self.prices.get(key)
        if (
            before is not None
            and _SOURCE_RANK.get(before.source, 0) > _SOURCE_RANK.get(source, 0)
            and before.price is not None
        ):
            return
        self.prices[key] = Live(
            key, name, price, regular_price, in_stock, qty, source, time.monotonic()
        )

    def _read_in_screen(self) -> None:
        """The tabs and the page in front, once per change, ahead of what they say."""
        if self._tabs_unseen and len(self.tabs) > 1:
            listed = "; ".join(
                f"{t.tab_id}: {t.title or t.url}"
                + (" (in front)" if t.tab_id == self._active else "")
                for t in self.tabs
            )
            self._note(f"[The visitor's open Cannon Home tabs — {listed}.]")
        self._tabs_unseen = False
        if running := self._still_running():
            self._note(
                f"[Still working on the page: {running}. Not done yet, and not failed: if it "
                "comes up, say it is still working on it.]"
            )
        if not self._page_unseen or self.page is None:
            return
        self._page_unseen = False
        p = self.page
        kinds = {
            "home": "the home page",
            "category": "a listing",
            "search": "search results",
            "product": "a product page",
            "cart": "the cart page",
            "checkout": "the checkout's delivery form",
            "page": "a page of the store",
        }
        note = f"[The tab in front shows {kinds[p.kind]}: “{p.title or p.path}” ({p.path})."
        if p.headings:
            note += f" Its headings: {_clip(p.headings, _HEADINGS_IN_NOTE)}."
        if p.faqs:
            note += f" Its FAQs: {_clip(p.faqs, _FAQS_IN_NOTE)}."
        self._note(note + "]")

    def _note(self, text: str) -> None:
        self.append_note(text)

    def _still_running(self) -> str:
        """The moves he made that the store is still working on, a while in,
        for the line that keeps him from calling them failed. One whose
        effect is already on screen is not among them."""
        return "; ".join(
            f"{r.move.id} ({r.phase or 'sent'}, {r.seconds:.0f} s so far)"
            for r in self.stage.running()
            if r.move.verb is None
            and r.move.cls is not MoveClass.LOOK
            and r.seconds >= 2
            and not r.shown
        )

    def _landing_line(self, landing: Landing) -> str | None:
        """His written line the moment a move he made shows on screen: a
        listing he filtered or sorted, a product he opened. Said in the next
        quiet spell, made short now; the model may add one sentence after.
        A result alone gets none: its talk-through, or its done line, is the
        result's own."""
        event = landing.event
        if isinstance(event, ListingShown):
            line = listing_line(event, self.spoken, landed_options(landing, event))
        elif isinstance(event, ProductShown):
            line = product_line(event, self.spoken)
        else:
            return None
        if self._hold is not None and self._hold[0] == landing.call_ref:
            self._hold = None
        logger.info(
            "cannonhome: {} {} on screen at {:.1f} s; landing line {!r}",
            landing.call_ref,
            landing.move.id,
            landing.seconds,
            line,
        )
        self._shorten_idle(_DONE_MS)
        return line

    def _holding_floor(self) -> bool:
        playing = self._playing > 0 and time.monotonic() - self._played_at < _PLAYOUT_MAX_S
        return self._turns > 0 or playing

    def _shorten_idle(self, ms: int = _TALK_THROUGH_MS) -> None:
        """The short quiet spell, for something to talk through: set now, or,
        while he holds the floor, once he has finished. The shortest asked
        for wins."""
        self._idle_want = min(ms, self._idle_want) if self._idle_deferred else ms
        if self._holding_floor():
            self._idle_deferred = True
            return
        self._idle_deferred = False
        want, self._idle_want = self._idle_want, _TALK_THROUGH_MS
        if not self._idle_short or want < self._idle_short:
            self._idle_short = want
            configure_soon(self.session, Config(idle=IdleConfig(timeout_ms=want)))

    def _floor_free(self) -> None:
        if self._idle_deferred and not self._holding_floor():
            self._shorten_idle(self._idle_want)

    def _answered(self, outcome: str, *, done: str | None = None) -> None:
        """The page answered a move he made: he says what it did in the next
        short quiet spell, unless the visitor speaks first. A confirmed move
        that is done has its written line (``done``), said as soon as the
        floor is free, with no model request before it."""
        self._outcomes.append(outcome)
        if done is not None:
            self._done.append(done)
        self._shorten_idle(_DONE_MS if done is not None else _TALK_THROUGH_MS)

    def _move(self, move: str, args: BaseModel, line: str) -> str | None:
        """Send a tool's move to the page, or, while the last one is still
        under way, queue it to follow: ``None`` when sent, else what the tool
        says."""
        known = self.stage.moves.get(move)
        if known is not None and known.cls is MoveClass.CONFIRMED:
            self._confirmed_sent = True
        try:
            ref = self.stage.send(move, args.model_dump())
        except Refused as again:
            logger.info("cannonhome: {} asked for again while it runs; not sent twice", move)
            doing = self.stage.busy or move
            return (
                f"Not sent again: the page is already doing exactly this ({doing}), and its "
                f"answer comes back to you{'' if again.why == 'running' else ' once it is sent'}. "
                "Never call it again for the same thing; if they asked for something else too, "
                "offer it once this one is done."
            )
        if ref is None:
            landed(_LANDED["queued"][self.spoken])
            return (
                f"Queued, not sent yet: the page is still working on the last move "
                f"({self.stage.busy}). It goes to the page as soon as that one is done, and what "
                "it did comes back to you after. Say in a few words that you will do it as soon "
                "as the page is ready; never that it is done, and do not call it again."
            )
        self._moved = True
        landed(_LANDED[line][self.spoken])
        return None

    def _take_ask(self, *, said: str = "") -> str | None:
        """What the next quiet spell asks of him; ``said`` is the written
        line it opens with, which the model must not say again."""
        asks: list[str] = []
        if self._outcomes and said:
            asks.append(
                "The page answered what you sent it: "
                + "; ".join(self._outcomes)
                + f'. You have just said: "{said}". Never say that again. Add at most one short '
                "sentence, in the language you speak: what is not done, if anything, or the one "
                "next step (free shipping, the checkout). Use the screen lines above for names "
                "and prices. Never say something is done that the page did not confirm."
            )
            self._outcomes = []
        elif self._outcomes:
            asks.append(
                "The page answered what you sent it: "
                + "; ".join(self._outcomes)
                + ". Say in a sentence or two what actually happened, as the page says it, in "
                "the language you speak: what is done, and plainly what is not, with what you "
                "can do instead. Use the screen lines above for names and prices. Never say "
                "something is done that the page did not confirm."
            )
            self._outcomes = []
        if self._talk is not None:
            asks.append(self._talk)
            self._talk = None
        return " ".join(asks) or None

    def _restore_idle(self) -> None:
        if self._idle_short:
            self._idle_short = 0
            configure_soon(self.session, Config(idle=IdleConfig(timeout_ms=_IDLE_MS)))

    def _headings(self) -> tuple[str, ...]:
        if self.page is not None:
            return tuple(self.page.headings)
        page = self.kb.page(self._path)
        return page.headings if page else ()

    def _faqs(self) -> tuple[str, ...]:
        if self.page is not None:
            return tuple(self.page.faqs)
        page = self.kb.page(self._path)
        return tuple(f.q for f in page.faqs) if page else ()

    def _faq_elsewhere(self, asked: str) -> tuple[str, str] | None:
        for page in self.kb.pages.values():
            if (q := _match(asked, [f.q for f in page.faqs])) is not None:
                return page.path, q
        for hit in self.kb.search(asked, 4):
            if hit.kind == "faq" and hit.path is not None:
                return hit.path, hit.title
        return None

    def _meta_turn(self) -> str | None:
        """The refusal for a move called on a question about the call, or in
        a turn with tools off (the model may call one anyway)."""
        if self._tools_off:
            logger.warning("cannonhome: a move called with tools off; refused")
            return (
                "Not done, nothing was sent: this turn only talks through what the page answered. "
                "If something is left to do, say so in a sentence and offer it."
            )
        if self._heard and about_the_call(self._heard[-1]):
            return (
                "Not done: they asked about the call itself, not the store. Answer that only "
                "(set_language for a language), and move nothing."
            )
        return None

    @staticmethod
    def _sent_note(doing: str) -> str:
        return (
            f"Sent to the page; it has not happened yet. Say only what you are doing "
            f"({doing}), never that it is done; the page's answer will follow."
        )

    def _shown_product(self) -> Product | None:
        """The catalogue's entry for the product page in front."""
        if self.product is not None:
            return self.kb.product(self.product.path)
        if _is_product_path(self._path):
            return self.kb.product(self._path)
        return None

    def _price_of(self, path: str) -> Live | None:
        return self.prices.get(_product_path(path))

    def _product_known(self, path: str) -> str | None:
        """The product path as the store links it, if the catalogue or their
        screen knows it; else ``None``."""
        if not path.strip():
            return None
        p = self.kb.product(path)
        if p is not None:
            return p.path
        key = _product_path(path)
        if _NEVER.match(key):
            return None
        if key in self.prices or self._on_screen(key):
            return key
        if self.product is not None and canonical_path(self.product.path) == key:
            return key
        return None

    def _unknown_product(self, path: str) -> str:
        near = self.kb.near_products(path.strip("/").replace("-", " ").removesuffix(".html"), 3)
        listed = ", ".join(f"{p.name} ({p.path})" for p in near) or "none"
        return (
            f"Not done: '{path}' is not a product the store has or their screen showed. "
            f"Find it with find_products first. Closest: {listed}."
        )

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        """Read the store's knowledge and catalogue; search, filter and open on
        their screen; read live prices; add to the cart; take them to the
        checkout's delivery form and fill their delivery details (never the
        RUT, a password or the payment); move their tabs; switch language."""
        return [
            self.read_topic,
            self.search_site,
            self.find_products,
            self.compare_products,
            self.search_products,
            self.filter_listing,
            self.open_product,
            self.check_prices,
            self.add_to_cart,
            self.update_cart_item,
            self.show_cart,
            self.start_checkout,
            self.fill_checkout,
            self.switch_tab,
            self.set_language,
        ]

    @needs_result_now
    async def read_topic(self, request: TopicRequest) -> str:
        """Read one of Cannon Home's knowledge topics before answering from it."""
        topic = self.kb.topics.get(request.topic)
        if topic is None:
            return f"No topic '{request.topic}' is written yet: use search_site."
        return topic.text

    @needs_result_now
    async def search_site(self, request: SearchRequest) -> str:
        """Search cannonhome.cl's information pages, sections and FAQs (not the
        products: find_products is for those). Each result names the page path
        and the section heading to take them to."""
        hits = self.kb.search(request.query, _SEARCH_HITS)
        if not hits:
            return f"Nothing on cannonhome.cl's pages matches '{request.query}'. Say so plainly."
        out: list[str] = []
        for h in hits:
            if h.kind == "faq":
                out.append(f"[FAQ on {h.path}] {h.title}\n  {h.snippet}")
            else:
                where = f", heading: {h.section}" if h.section else ""
                out.append(f"[page] {h.title} — path: {h.path}{where}\n  {h.snippet}")
        return "\n".join(out)

    @needs_result_now
    async def find_products(self, request: FindRequest) -> str:
        """Search Cannon Home's catalogue from what the visitor wants: their
        words, the category or type, the size, colour, material, thread count
        or towel weight. Returns each product's path and attributes and its
        line's other sizes and colours; names any wish it had to drop. No
        prices: those are read on their screen. With a size or colour alone,
        the product page in front gives its own line's."""
        family: Product | None = None
        if request.sibling_of:
            family = self.kb.product(request.sibling_of)
            if family is None:
                return self._unknown_product(request.sibling_of)
        elif (
            (request.size or request.color)
            and not (request.query or request.type or request.category)
            and (here := self._shown_product()) is not None
        ):
            family = here
        found = self.kb.find_products(
            query=request.query,
            category=request.category,
            type=request.type,
            size=request.size,
            color=request.color,
            material=request.material,
            threads_min=request.threads_min,
            threads_max=request.threads_max,
            weight_min=request.weight_min,
            weight_max=request.weight_max,
            family_of=family,
            limit=_FOUND_SHOWN,
        )
        out: list[str] = []
        if not self.kb.products:
            return (
                "The catalogue is not loaded. Use search_products to type their words in the "
                "store's search box, where the suggestions show live."
            )
        if found.unknown:
            out.append(
                f"Not read: {', '.join(found.unknown)}. Bed sizes are "
                f"{', '.join(SIZE_LABELS.values())}."
            )
        if family is not None:
            out.append(f"The line of “{family.name}” ({family.path}):")
        if found.dropped:
            out.append(
                f"Nothing fits all of that. Without {' and '.join(found.dropped)}, these do; "
                "say plainly what is different."
            )
        if not found.products:
            out.append(
                "No product matches. Say so, and offer search_products with their words: the "
                "store's own search may find it."
            )
            return "\n".join(out)
        out.append(f"{found.total} products fit; the first {len(found.products)}:")
        for p in found.products:
            out.append(f"- {self._product_line(p)}")
        out.append(
            "Prices are not in the catalogue: say one only once their screen has shown it "
            "(open_product, or check_prices for several)."
        )
        return "\n".join(out)

    def _product_line(self, p: Product) -> str:
        line = f"{p.name} — {p.path}; {p.facts()}"
        if (live := self._price_of(p.path)) is not None:
            line += f"; on their screen: {live.line(self.spoken)}"
        sizes: list[str] = []
        colors: list[str] = []
        for s in self.kb.siblings(p):
            if s.color and fold(s.color) == fold(p.color) and s.size != p.size and s.size:
                sizes.append(f"{s.size} {s.path}")
            elif s.size == p.size and s.color and fold(s.color) != fold(p.color):
                colors.append(f"{s.color} {s.path}")
        if sizes:
            line += f"; other sizes: {_clip(sizes, _SIBLINGS_SHOWN)}"
        if colors:
            line += f"; other colours: {_clip(colors, _SIBLINGS_SHOWN)}"
        return line

    @needs_result_now
    async def compare_products(self, request: CompareRequest) -> str:
        """Two to six products side by side, from the catalogue: type, size,
        colour, material, thread count, weight, summary — and each one's price
        only if their screen has already shown it."""
        paths = list(dict.fromkeys(request.paths))[:_MOST_PRICED]
        if not paths:
            return "Not compared: give two to six product paths."
        out: list[str] = []
        unread = False
        for raw in paths:
            p = self.kb.product(raw)
            live = self._price_of(raw)
            if p is None and live is None:
                out.append(f"- {raw}: not in the catalogue.")
                continue
            name = p.name if p is not None else (live.name if live else raw)
            facts = p.facts() if p is not None else ""
            summary = f" {p.summary}" if p is not None and p.summary else ""
            price = live.line(self.spoken) if live is not None else "price not read yet"
            unread = unread or live is None or live.price is None
            out.append(f"- {name} ({_product_path(raw)}): {facts}; {price}.{summary}")
        if unread:
            out.append(
                "A price not read yet is not known: check_prices reads it live, or "
                "open_product shows it. Never guess one."
            )
        return "\n".join(out)

    async def search_products(self, request: SearchProductsRequest) -> str:
        """Type their words into the store's search box, as a visitor would, so
        its suggestions (with live prices) show on their screen; with
        open_index, open that suggested product. It returns at once; what the
        search box shows comes back to you after."""
        if (meta := self._meta_turn()) is not None:
            return meta
        query = " ".join(request.query.split())
        if len(query) < 3:
            return "Not searched: the search box needs at least three letters."
        index = request.open_index
        if index is not None and not 1 <= index <= 6:
            return "Not searched: open_index is 1 to 6, the suggested products."
        # The model counts from 1, as the visitor does; the page from 0.
        action = SearchProducts(query=query, open_index=None if index is None else index - 1)
        queued = self._move("search_products", action, "search")
        if queued is not None:
            return queued
        return f"Typing '{query}' in the store's search box. " + self._sent_note(
            "'Lo busco en la tienda.'"
        )

    async def filter_listing(self, request: FilterRequest) -> str:
        """Show a listing narrowed by size, colour, thread count or material,
        with the listing's own filters, and sorted. Only options the listing
        has. It returns at once; what the listing shows comes back to you after."""
        if (meta := self._meta_turn()) is not None:
            return meta
        path = canonical_path(request.category_path)
        if _NEVER.match(path) or path.endswith(".html"):
            return f"Not done: '{request.category_path}' is not a listing."
        cat = self.kb.category(path)
        if cat is None and self.kb.categories:
            listing_here = self.listing is not None and canonical_path(self.listing.path) == path
            page = self.kb.page(path)
            if not listing_here and (page is None or page.kind not in ("category", "listing")):
                near = sorted(
                    self.kb.categories.values(),
                    key=lambda c: -_closeness(path, c.path, c.name),
                )[:4]
                listed = "; ".join(f"{c.path} ({c.name})" for c in near)
                return f"Not done: no listing at '{request.category_path}'. Closest: {listed}."
        refused: list[str] = []
        size = _filter_values(cat, "tamano", request.size, refused)
        color = _filter_values(cat, "color", request.color, refused)
        threads = _filter_values(cat, "hilos", request.threads, refused)
        material = _filter_values(cat, "material", request.material, refused)
        if refused:
            return "Not done: " + "; ".join(refused) + "."
        action = FilterListing(
            category_path=cat.path if cat is not None else path,
            size=size,
            color=color,
            threads=threads,
            material=material,
            sort=request.sort,
        )
        queued = self._move("filter_listing", action, "filter")
        if queued is not None:
            return queued
        applied = ", ".join(
            f"{n} {v if isinstance(v, str) else ' + '.join(v)}"
            for n, v in (
                ("tamaño", size),
                ("color", color),
                ("hilos", threads),
                ("material", material),
                ("sort", request.sort),
            )
            if v
        )
        return (
            f"Filtering {action.category_path}" + (f" by {applied}" if applied else "") + ". "
        ) + self._sent_note("'Te filtro la lista.'")

    async def open_product(self, request: OpenProductRequest) -> str:
        """Open a product's page on their screen — the exact size and colour —
        and, with tab, its specifications, reviews, description or photos. It
        returns at once; what the page shows, with its price, comes back to you."""
        if (meta := self._meta_turn()) is not None:
            return meta
        path = self._product_known(request.path)
        if path is None:
            return self._unknown_product(request.path)
        here = self.product is not None and canonical_path(self.product.path) == path
        if here and request.tab is None:
            return (
                "Not moved: that product is already on their screen. Answer from its lines above."
            )
        if here and request.tab is not None:
            # The product is in front: only its tab moves.
            queued = self._move("product_tab", ProductTabArgs(tab=request.tab), "tab")
            if queued is not None:
                return queued
            return f"Opening its {request.tab} tab. " + self._sent_note("'Te muestro esa pestaña.'")
        queued = self._move("open_product", OpenProduct(path=path, tab=request.tab), "product")
        if queued is not None:
            return queued
        p = self.kb.product(path)
        return f"Opening {p.name if p else path}. " + self._sent_note("'Te abro el producto.'")

    async def check_prices(self, request: CheckPricesRequest) -> str:
        """Read the live price and stock of up to six products from the store
        itself, without moving their screen. It returns at once; the prices come
        back to you after, in square brackets."""
        if (meta := self._meta_turn()) is not None:
            return meta
        paths: list[str] = []
        unknown: list[str] = []
        for raw in request.paths:
            known = self._product_known(raw)
            if known is None:
                unknown.append(raw)
            elif known not in paths:
                paths.append(known)
        if not paths:
            return (
                f"Not read: {', '.join(unknown) or 'no paths'} — not products the store has. "
                "Find them with find_products first."
            )
        if len(paths) > _MOST_PRICED:
            return f"Not read: at most {_MOST_PRICED} at a time."
        self.stage.send("check_prices", CheckPrices(paths=paths).model_dump())
        landed(_LANDED["prices"][self.spoken])
        out = f"Reading the live prices of {len(paths)} products. " + self._sent_note(
            "'Te reviso los precios.'"
        )
        if unknown:
            out += f" Not asked, not products the store has: {', '.join(unknown)}."
        return out

    async def add_to_cart(self, request: AddToCartRequest) -> str:
        """Add a product — the exact size and colour — to their cart, with the
        quantity they said. Only when they ask, or say yes to your offer. It
        opens the product first if needed and returns at once; the cart's answer
        comes back to you. Never the checkout."""
        if (meta := self._meta_turn()) is not None:
            return meta
        path = self._product_known(request.path)
        if path is None:
            return self._unknown_product(request.path)
        if not 1 <= request.qty <= 10:
            return "Not added: the quantity is one to ten."
        live = self._price_of(path)
        if live is not None and live.in_stock is False:
            return (
                "Not added: their screen says it is not available. Say so, and offer another "
                "size or colour of the line (find_products)."
            )
        queued = self._move("add_to_cart", AddToCart(path=path, qty=request.qty), "cart_add")
        if queued is not None:
            return queued
        p = self.kb.product(path)
        return (
            f"Adding {request.qty} of {p.name if p else path} to their cart. "
            + self._sent_note("'Te lo agrego al carro.'")
            + _CHECKOUT_IS_THEIRS
        )

    def _cart_line(self, said: str) -> CartItem | None:
        """The line of their cart ``said`` names: by its path, else its name."""
        if self.cart is None:
            return None
        want = _product_path(said) if said.strip() else ""
        for item in self.cart.items:
            if item.path and _product_path(item.path) == want:
                return item
        named = _match(said, [i.name for i in self.cart.items if i.name])
        return next((i for i in self.cart.items if i.name == named), None) if named else None

    async def update_cart_item(self, request: UpdateCartRequest) -> str:
        """Change how many of one line of their cart they have, or take it out
        with qty 0: in the cart drawer, or on the cart page when that is in
        front. Only when they ask, or say yes to your offer. It returns at
        once; the cart's answer comes back to you. Never the checkout."""
        if (meta := self._meta_turn()) is not None:
            return meta
        if not 0 <= request.qty <= 10:
            return "Not done: the quantity is 0 (take it out) to 10."
        item = self._cart_line(request.line)
        if item is not None and item.path:
            path = _product_path(item.path)
        elif self.cart is not None:
            listed = "; ".join(f"{i.name} ({i.path}) x{i.qty}" for i in self.cart.items)
            return f"Not done: '{request.line}' is not a line of their cart" + (
                f", which has: {listed}." if listed else ", which is empty."
            )
        elif (known := self._product_known(request.line)) is not None:
            # No cart report yet: the page finds the line, or says it is not there.
            path = known
        else:
            return self._unknown_product(request.line)
        name = item.name if item is not None else path
        if item is not None and item.qty == request.qty:
            return f"Nothing to change: their cart already has {item.qty} of {name}."
        queued = self._move(
            "update_cart_item",
            UpdateCartItem(path=path, qty=request.qty),
            "cart_remove" if request.qty == 0 else "cart_update",
        )
        if queued is not None:
            return queued
        if request.qty == 0:
            return f"Taking {name} out of their cart. " + self._sent_note("'Lo saco de tu carro.'")
        had = f" (it has {item.qty})" if item is not None else ""
        return f"Setting {name} to {request.qty} in their cart{had}. " + self._sent_note(
            "'Te lo cambio en el carro.'"
        )

    async def show_cart(self, request: ShowCartRequest) -> str:
        """Open their cart drawer, or close it. Never the checkout."""
        if (meta := self._meta_turn()) is not None:
            return meta
        queued = self._move(
            "show_cart", ShowCart(open=request.open), "cart_show" if request.open else "cart_close"
        )
        if queued is not None:
            return queued
        return self._sent_note("'Te abro el carro.'" if request.open else "'Te cierro el carro.'")

    async def start_checkout(self) -> str:
        """Take them from the cart to the checkout's delivery form, as a guest:
        "Terminar pedido", then "Comprar como invitado", never a login. Only
        when they want to buy, or say yes to your offer. It returns at once;
        the form's answer comes back to you. Never past the delivery form."""
        if (meta := self._meta_turn()) is not None:
            return meta
        if self.cart is not None and not self.cart.items and not self.cart.count:
            return "Not done: their cart is empty. Offer to find something first."
        if self.page is not None and self.page.kind == "checkout":
            return (
                "Already there: the delivery form is in front. Ask for the next one or two "
                "details it needs (fill_checkout); never the RUT."
            )
        self._checkout_asked = True
        queued = self._move("start_checkout", StartCheckout(), "checkout")
        if queued is not None:
            return queued
        return (
            "Opening the guest checkout. "
            + self._sent_note("'Te llevo a los datos de despacho.'")
            + " As a guest, never a login. The RUT and the payment are theirs."
        )

    def _phone(self, said: str, refused: list[str]) -> str | None:
        """The phone the model passed, if it is a Chilean number and the
        digits the visitor said; else why not, in ``refused``. Never reshaped,
        and never a RUT."""
        # What they said just now, or with the fragment before it.
        last = self._heard[-1] if self._heard else ""
        heard = said_digits(last)
        if len(heard) < _SAID_DIGITS_MIN:
            last = " ".join(self._heard[-2:])
            heard = said_digits(last)
        about_rut = bool(_RUT_WORD.search(last)) and not re.search(
            r"tel[eé]fono|celular|\bfono\b|\bphone\b|\bmobile\b|\bcell\b", last, re.IGNORECASE
        )
        if _looks_private(said) or about_rut or _RUT.search(last):
            refused.append(
                "phone: what was passed is their RUT, not a phone. Never typed, never repeated: "
                "the RUT is theirs to type in its own field"
            )
            return None
        given = "".join(c for c in said if c.isdigit())
        phone = chilean_phone(said)
        if phone is None:
            from_them = f" (they said {spaced(heard)})" if len(heard) >= _SAID_DIGITS_MIN else ""
            refused.append(
                f"phone: {spaced(given) if given else repr(said)}{from_them} is not a Chilean "
                "number, nine digits starting with 9 (a mobile) or 2 (a Santiago landline). "
                "Tell them the form needs one and ask; never change or invent digits"
            )
            return None
        if len(heard) >= _SAID_DIGITS_MIN and phone not in heard:
            refused.append(
                f"phone: {spaced(phone)} is not what the visitor said ({spaced(heard)}). Never "
                "change their digits: if theirs is not a Chilean number, nine digits starting "
                "with 9 or 2, tell them the form needs one and ask"
            )
            return None
        return phone

    async def fill_checkout(self, request: CheckoutRequest) -> str:
        """Fill the checkout's delivery form with what the visitor just said:
        email, nombre, apellidos, teléfono, región, comuna, dirección, número,
        depto/casa — only those they said. It opens the guest checkout first if
        it is not in front, and returns at once; what the form took comes back
        to you. Never a RUT, a password or card details, and nothing that goes
        on to the payment."""
        if (meta := self._meta_turn()) is not None:
            return meta
        refused: list[str] = []
        given: dict[str, str] = {}
        for key in ("first_name", "last_name", "street", "number", "apartment"):
            raw = getattr(request, key)
            if raw is None or not raw.strip():
                continue
            value = " ".join(raw.split())
            if (why := _looks_private(value)) is not None:
                refused.append(
                    f"{_FIELD_SAID[key]}: {why}. Never typed, never repeated: the RUT and the "
                    "payment are theirs"
                )
            elif len(value) > _MAX_LENGTH[key]:
                refused.append(
                    f"{_FIELD_SAID[key]}: the form takes at most {_MAX_LENGTH[key]} characters "
                    "there; ask them how to shorten it"
                )
            else:
                given[key] = value
        if request.email and request.email.strip():
            if (address := email_address(request.email)) is not None:
                given["email"] = address
            else:
                refused.append(
                    f"email: {request.email.strip()!r} is not an email address; ask them to "
                    "spell it"
                )
        said_phone = (request.phone or "").strip()
        phone = self._phone(said_phone, refused) if said_phone else None
        if phone is not None:
            given["phone"] = phone
        if request.region and request.region.strip():
            if (label := region_label(request.region)) is not None:
                given["region"] = label
            else:
                refused.append(
                    f"región: {request.region.strip()!r} is not one of the site's. It lists: "
                    + ", ".join(_REGIONS)
                )
        if request.comuna and request.comuna.strip():
            comuna = " ".join(request.comuna.split())
            known = (
                given.get("region")
                or self._filled.get("region")
                or (self.checkout.region if self.checkout is not None else "")
            )
            if _looks_private(comuna) is not None:
                refused.append("comuna: that is not a comuna")
            elif not known:
                refused.append(
                    f"comuna: the form lists comunas once a región is chosen. Fill the región "
                    f"with it (you know Chile's: {comuna} is in which región?)"
                )
            else:
                given["comuna"] = comuna
        if not given:
            why = "; ".join(refused) or "nothing they said to fill"
            return f"Not filled: {why}. The RUT, any password and the payment are theirs."
        self._filled.update(given)
        self._checkout_asked = True
        queued = self._move("fill_checkout", FillCheckout(**given), "checkout_fill")
        out = f"For the delivery form: {_fields_said(list(given))}. " + (
            queued or self._sent_note("'Te lo completo.'")
        )
        if "email" in given:
            out += (
                f" The email sent: {given['email']}. Read it back, letter by letter where it "
                "could be heard wrong."
            )
        if "phone" in given:
            out += f" The phone sent: {spaced(given['phone'])}. Read it back digit by digit."
        if refused:
            out += f" Not filled: {'; '.join(refused)}."
        return (
            out + " The RUT, any password and the payment are theirs; never press what goes on "
            "to the payment."
        )

    async def switch_tab(self, request: TabRequest) -> str:
        """Bring another of the visitor's Cannon Home tabs to the front."""
        tab = next((t for t in self.tabs if t.tab_id == request.tab_id), None)
        if tab is None:
            listed = ", ".join(f"{t.tab_id} ({t.title})" for t in self.tabs) or "none"
            return f"Not switched: no tab '{request.tab_id}'. Open tabs: {listed}."
        self.session.dispatch(FocusTab(tab_id=tab.tab_id))
        landed(_LANDED["tab"][self.spoken])
        return f"Brought '{tab.title or tab.url}' to the front."

    async def set_language(self, request: LanguageRequest) -> str:
        """Conduct the rest of the call in English ('en') or Spanish ('es'),
        listening and speaking. Call it when they ask for the other language in
        words that are not already it, and to go back. Say one short line in the
        language you are switching to, in the same response."""
        self._chosen = True
        configure_soon(self.session, self._speaking(request.language))
        logger.info("cannonhome: language -> {} (asked)", request.language)
        return "ok"


# ─── Filter options, as the listing writes them ────────────────────────────────


def _closeness(path: str, other: str, name: str) -> float:
    return max(_ratio(path, other), _ratio(path.rsplit("/", 1)[-1].replace("-", " "), norm(name)))


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _size_label(said: str, options: tuple[str, ...]) -> str | None:
    want = size_key(said)
    if want is None:
        return _match(said, options) if options else None
    if options:
        return next((o for o in options if size_key(o) == want), None)
    return SIZE_LABELS.get(want, said)


def _color_label(said: str, options: tuple[str, ...]) -> str | None:
    want = next((s for w in said.split() if (s := color_stem(w))), None)
    if not options:
        return said.strip().capitalize() if want else None
    if want is None:
        return _match(said, options)
    return next(
        (o for o in options if any(color_stem(w) == want for w in o.split())), None
    ) or _match(said, options)


def _threads_label(said: str, options: tuple[str, ...]) -> str | None:
    digits = "".join(re.findall(r"\d+", said))
    if not digits:
        return None
    if not options:
        return digits
    return next((o for o in options if "".join(re.findall(r"\d+", o)) == digits), None)


def _material_label(said: str, options: tuple[str, ...]) -> str | None:
    if not options:
        return said.strip() or None
    want = material_key(said)
    if want is not None:
        hit = next((o for o in options if material_key(o) == want), None)
        if hit is not None:
            return hit
    return _match(said, options)


#: Where one said option ends and the next begins: a comma (not the one in
#: "1,5 plazas"), "&", or "y"/"e"/"o"/"and"/"or" — but not the "y" of "plaza y
#: media" or the "and" of "one and a half".
_SAID_SPLIT = re.compile(
    r"\s*(?:(?<!\d),|,(?!\d)|&|\b(?:y|e|o|and|or)\b(?!\s+(?:medi[oa]|a half|half)\b))\s*",
    re.IGNORECASE,
)


def _said_parts(said: str | list[str] | None) -> list[str]:
    """Each option in what was said, in order: "beige y blanco" → beige,
    blanco; a list's items each split the same way."""
    items = [said] if isinstance(said, str) else list(said or [])
    out: list[str] = []
    for item in items:
        out.extend(p for part in _SAID_SPLIT.split(item) if (p := part.strip(" .")))
    return out


def _colour_words(part: str) -> list[str]:
    """``part`` as one colour, or, when it names several different colours
    word by word ("beige blanco"), each of them."""
    stems = [(w, s) for w in part.split() if (s := color_stem(w))]
    if len({s for _, s in stems}) < 2:
        return [part]
    return [w for w, _ in stems]


def _filter_values(
    cat: Category | None,
    var: str,
    said: str | list[str] | None,
    refused: list[str],
) -> list[str] | None:
    """The option labels for what was said, as the listing writes them, one
    per option named ("beige y blanco" → Beige, Blanco), in order, once each;
    ``None`` when nothing was said, or when anything is refused. A filter the
    listing lacks, or any option it does not list, is refused by name with
    what it has: the first of several words is never taken for all of them."""
    parts = _said_parts(said)
    if not parts:
        return None
    name = _FILTER_NAMES.get(var, var)
    if cat is not None and cat.filters and var not in cat.filters:
        refused.append(f"{cat.name} has no {name} filter (it has: {', '.join(cat.filters)})")
        return None
    options = cat.labels(var) if cat is not None else ()
    label = _LABELERS[var]
    if var == "color":
        parts = [w for p in parts for w in _colour_words(p)]
    labels: list[str] = []
    unknown: list[str] = []
    for part in parts:
        got = label(part, options)
        if got is None:
            unknown.append(part)
        elif got not in labels:
            labels.append(got)
    if unknown:
        listed = ", ".join(options) if options else "none"
        named = " and ".join(f"'{u}'" for u in unknown)
        verb = "is not an option" if len(unknown) == 1 else "are not options"
        refused.append(f"{name} {named} {verb} of this listing (it lists: {listed})")
        return None
    return labels


#: Each filter's labeler, by the listing's request variable.
_LABELERS: dict[str, Callable[[str, tuple[str, ...]], str | None]] = {
    "tamano": _size_label,
    "color": _color_label,
    "hilos": _threads_label,
    "material": _material_label,
}


__all__ = [
    "MOVES",
    "AddToCart",
    "CannonHomeBrain",
    "CheckPrices",
    "FillCheckout",
    "FilterListing",
    "FocusTab",
    "LanguageChanged",
    "OpenProduct",
    "ProductTabArgs",
    "SearchProducts",
    "ShowCart",
    "StartCheckout",
    "UpdateCartItem",
]
