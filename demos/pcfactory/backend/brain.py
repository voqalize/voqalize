"""PcFactoryBrain — Javier, a voice tech advisor on www.pcfactory.cl, PC Factory's store.

The site is pcFactory's, not ours. A browser extension injects the widget and a
small adapter into www.pcfactory.cl; the adapter turns each move below into an
act on the tab in front — the catalogue read, a listing filtered, a product
opened and its specifications shown, a store's stock read, an item added to the
cart — and every tab reports what it shows as a typed event (:mod:`.app_events`),
whichever of the visitor and Javier moved it. The store is a multi-page site: a
move to another page is a full page load, and the call rejoins on the new page.

**He never fetches the store, and he has no catalogue of his own.** The brains
run far from the store, and its prices move daily: products, prices and stock
are read in the visitor's browser by the extension (``find_products``,
``check_prices``, ``check_stock``, the product page's own live read) and reach
the brain as app events; the brain keeps them in a mirror and answers from it.

**A price is one he just read, and the headline is the transfer price.** The
store shows three: Transferencia / Débito (the headline he says), otros medios
de pago (the card price, said when cards come up or the difference matters),
and the struck reference price (said with its percentage only when the saving
is real). Delivery is priced only in the checkout; store pickup is free; stock
is approximate and twenty minutes behind.

**He goes as far as Tipo de entrega, never further.** He may add to the cart,
change a line or take it out, apply a coupon, and take a guest from the cart to
the checkout's Tipo de entrega step (each only after a clear yes), and there he
stops: the visitor chooses store pickup or delivery, and logs in or types their
RUT, address and payment themselves. He never asks for, repeats or types a RUT,
a password, a card or an address, and no move he can send carries one.

**Every move is a Stage move.** A move on the page — a cue in his reply or a
tool's move — has a class that decides how it is sent and what he hears of
it, is ringed on the page before it acts, and is answered by exactly one
``stage_result`` (:mod:`voqalize.sdk.stage`).

**Never block on the UI.** A tool's move is sent and the tool returns at once;
the page's result comes back, and he talks it through in the next short quiet
spell, with tools off. One move at a time: a move asked for while another is
under way waits for that one to land.

**The screen follows his voice.** He writes his moves into the reply as cues
(``{tab: specs}``, ``{show: Procesador}``, ``{filter: Marcas | Lenovo}``), at
the start of the sentence they belong to; Stage takes them out of the speech,
the brain checks them against the site and what the page in front reports,
and the page makes each as the voice reaches its sentence.

**A listing he moved is said as it stands.** A listing the page reports with
no products lands only with the move's own result, never as the grid is
drawn; the line that says it is built from the newest report when it is
spoken, and waits for a later filter of the same turn. Every option of every
facet reaches him, and a filter cue keeps only the options the visitor named.

**Comparing is the store's own comparator.** ``compare_products`` ticks each
product's Comparar, presses the bar's Comparar and opens the comparison page
(``/comparador``); its table comes back as the ``compare`` slice, the rows that
differ first, and he walks it row by row with ``{compare: Label}`` cues before
he recommends one.

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
from collections.abc import AsyncGenerator, Callable, Iterable, Mapping
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Literal
from zoneinfo import ZoneInfo

from loguru import logger
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
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
    Mirror,
    Move,
    MoveClass,
    RawCue,
    Refused,
    Stage,
    StageEvent,
    StageHello,
    StageProgress,
    StageResult,
    landed_ask,
)
from voqalize.sdk.voice import ToolChoice
from voqalize.sdk.wire import Config, IdleConfig, SttConfig, TtsConfig, Voice

from . import knowledge as kb
from .app_events import (
    PCFACTORY_EVENTS,
    CartItem,
    CartState,
    CheckoutState,
    CompareShown,
    ComparisonRow,
    ComparisonShown,
    LanguageRequested,
    ListingShown,
    PageChanged,
    PcFactoryEvent,
    PricesRead,
    ProductsFound,
    ProductShown,
    StockRead,
    StoreShown,
    TabInfo,
    TabsChanged,
    cart_view,
    checkout_view,
    comparison_view,
    listing_view,
    product_view,
)
from .knowledge import (
    SEARCH_PATH,
    TOPIC_IDS,
    Category,
    Knowledge,
    Store,
    canonical_path,
    facet_key,
    fold,
    norm,
    product_path,
    search_path,
    search_query,
)
from .stage_gen import (
    MOVES,
    SPEC,
    AddArgs,
    ApplyCouponArgs,
    CartAddArgs,
    CartShowArgs,
    CartUpdateArgs,
    CheckPricesArgs,
    CheckStockArgs,
    FilterListingArgs,
    FindProductsArgs,
    OpenProductArgs,
    ReadRequest,
    RemoveArgs,
    SearchArgs,
    StartCheckoutArgs,
    StoresShowArgs,
    TabArgs,
)

AGENT_NAME = "Javier"

#: GPT-6.1 Terra at low reasoning, for cost: OpenAI caches every prompt over
#: 1,024 tokens, so most of each turn's input is read from the cache.
MODEL = "gpt-6.1-terra"
REASONING = "low"
#: PC Factory is in Chile: "hoy" and "mañana" are Santiago's.
TIMEZONE = ZoneInfo("America/Santiago")

# ─── Voice and timing ──────────────────────────────────────────────────────────

#: Javier's voice: one man, recorded once in English and once in Spanish.
VOICE = Voice.OMNIVOICE_JAVIER

_IDLE_MS = 20_000
_IDLE_NUDGES = 2
#: The idle window while a result the page produced waits to be talked
#: through: short, since the voice has stopped and the visitor is waiting.
_TALK_THROUGH_MS = 600
#: The idle window once a written line leads (a confirmed move the page
#: confirmed, a listing or product that landed): said as soon as the floor is
#: free, with no model request before it.
_DONE_MS = LANDING_FLOOR_MS
#: A visitor thinking aloud about what they need pauses mid-sentence.
PCFACTORY_PATIENCE = PATIENCE + 2

# ─── Language ──────────────────────────────────────────────────────────────────

Lang = Literal["en", "es"]
#: The store is Spanish (Chile), so the call opens in Spanish.
OPENING: Lang = "es"
LANGUAGE_NAMES: dict[Lang, str] = {"en": "English", "es": "Spanish"}

TOGGLE_CONFIRM: dict[Lang, str] = {
    "en": "Sure, let's continue in English.",
    "es": "Claro, seguimos en español.",
}

# The small words of each language, plus the store's own Spanish nouns: a
# sentence that uses several of one and none of the other is in that one. Words
# both languages write ("notebook", "monitor", "gamer", "RAM") are in neither.
_SPANISH_WORDS = frozenset(
    # A word list reads as words, so it stays a split string.
    """que qué de del el los las la una unas unos por para con como cómo cuánto cuanto
    cuánta cuesta cuestan puedes puede podrías quiero quisiera necesito tengo tienes
    tiene tienen hay hola gracias sí está están estoy es eso esto esta este estos pero muy
    también hablar habla hablas hablemos español castellano usted ustedes mi mis tu tus
    su sus nosotros bueno claro dónde donde cuál cual cuándo cuando precio precios barato
    barata baratos muéstrame dime explícame funciona hace hacer hora horas busco buscando
    computador computadores tarjeta tarjetas gráfica gráficas celular celulares procesador
    memoria disco tienda tiendas despacho retiro carro garantía oferta ofertas audífonos
    impresora agrega agrégalo agregar ábreme muestra otra otro otras otros juegos jugar
    """.split()  # noqa: SIM905
)
#: The store's nouns, which are also in its products' and categories' names:
#: "Tarjeta Gráfica" in an English reply is a category, not Spanish. Only the
#: visitor's words count them.
_STORE_NOUNS = frozenset(
    """computador computadores tarjeta tarjetas gráfica gráficas celular celulares procesador
    memoria disco tienda tiendas despacho retiro carro garantía oferta ofertas audífonos
    impresora precio precios
    """.split()  # noqa: SIM905
)
_SPANISH_SMALL = _SPANISH_WORDS - _STORE_NOUNS
_ENGLISH_WORDS = frozenset(
    """the is are was what how can could you your i i'm it it's this that these those do
    does show me my we our for with about and of to have has there here please want
    would like tell sure yes okay right of course let's laptop laptops graphics card phone
    cheap cheaper cheapest much price which best need good
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
    ``vocabulary`` (the categories' names) neither count nor bring marks."""
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
# "VÍ-deo" one time in three (2026-10-21, clini), and "bidéo" right every time.
# So in Spanish the voice is handed "bidéo", the page's word anchors follow
# (``_anchor_for_voice``), and what comes back as heard is spelled "video" again
# before it reaches the model (``on_finalize``).
#
# The store writes its own name every way ("pcFactory", "pc Factory",
# "PCFACTORY"); the voice says one brand, "PC Factory", in both languages.
# If the Spanish voice is heard saying it wrong, respell it in ``_ES_RESPELL``
# (Spanish voice only) with its undoing in ``_ES_UNSPELL``: tuned on dev, by ear.

_VIDEO_TO_VOICE = re.compile(r"\b([Vv])[ií]deo(s?)\b")
_VIDEO_FROM_VOICE = re.compile(r"\b([Bb])idéo(s?)\b")
_BRAND_TO_VOICE: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bp\s?c\s?factory\b(?!\.cl)", re.IGNORECASE), "PC Factory"),
)
#: Spanish voice only: (written, as the voice must read it). Empty until heard wrong.
_ES_RESPELL: tuple[tuple[re.Pattern[str], str], ...] = ()
_ES_UNSPELL: tuple[tuple[re.Pattern[str], str], ...] = ()


def names_for_the_voice(text: str) -> str:
    """``text`` with the store's name as the one brand the voice says."""
    for rx, said in _BRAND_TO_VOICE:
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
    """CLP as the store writes it: ``$729.990``."""
    return "$" + f"{amount:,}".replace(",", ".")


def pesos_said(amount: int, lang: Lang) -> str:
    """CLP as Javier says it: "setecientos veintinueve mil novecientos noventa pesos"."""
    if lang == "en":
        return f"{_en_number(amount)} pesos"
    said = _es_number(amount)
    exact_millions = amount >= 1_000_000 and amount % 1_000_000 == 0
    return f"{said} de pesos" if exact_millions else f"{said} pesos"


def _money(amount: int, lang: Lang) -> str:
    return f"{pesos(amount)} (say: {pesos_said(amount, lang)})"


def saving(price: int | None, regular: int | None) -> int | None:
    """The whole percentage the reference price is above the transfer price,
    when it is a real saving (5% or more); else ``None``."""
    if price is None or regular is None or regular <= price or regular <= 0:
        return None
    pct = math.floor((regular - price) * 100 / regular)
    return pct if pct >= 5 else None


# ─── Actions (brain → page) ────────────────────────────────────────────────────


class FocusTab(Action):
    """Bring one of the visitor's PC Factory tabs to the front."""

    tab_id: str


class LanguageChanged(Action):
    """The call's language moved, by the toggle, by voice or by
    ``set_language``: the widget's toggle follows at once."""

    language: Literal["en", "es"]


# The moves themselves, their arguments included, are declared once in
# ``pcfactory/scene.json`` and generated into ``stage_gen`` for the brain and
# ``scene.gen.ts`` for the page.

SortOrder = Literal["price_asc", "price_desc", "relevance"]
ProductTab = Literal[
    "about", "specs", "warranty", "stock", "photos", "zoom", "pickup", "price_note"
]


# ─── Tool requests ─────────────────────────────────────────────────────────────

if TYPE_CHECKING:
    TopicId = str
else:
    # The L2 files present at import, as the tool's enum; see knowledge.TOPIC_IDS.
    TopicId = Literal[TOPIC_IDS]


class TopicRequest(BaseModel):
    topic: TopicId = Field(description="The topic to read, by its name.")


class CategoryRequest(BaseModel):
    name: str = Field(
        description="The category, by its name in either language, its id or its path: "
        "'notebooks gamer', 'tarjetas de video', 'monitores', 995."
    )


class SearchRequest(BaseModel):
    query: str = Field(
        description="A few words to look for on www.pcfactory.cl's information pages and FAQs, "
        "in Spanish, e.g. 'retiro en tienda', 'garantía extendida', 'despacho regiones'."
    )


class TabRequest(BaseModel):
    tab_id: str = Field(description="The tab_id from the open tabs list.")


class LanguageRequest(BaseModel):
    language: Lang = Field(description="'en' for English, 'es' for Spanish.")


class FindRequest(BaseModel):
    """Only what the visitor said or clearly meant: leave the rest out."""

    query: str | None = Field(
        default=None,
        description="Words to search the catalogue for, in Spanish as the store writes them: "
        "'notebook ryzen 7 16gb', 'rtx 4060', 'monitor 27 144hz', 'iphone 15'.",
    )
    category: str | None = Field(
        default=None,
        description="A category from the category list: its name ('Notebooks Gamer', "
        "'Tarjetas Gráficas'), its id or its path.",
    )
    brand: str | None = Field(default=None, description="A brand, as said: 'Lenovo', 'ASUS'.")
    min_price: int | None = Field(default=None, description="Lowest transfer price, pesos.")
    max_price: int | None = Field(default=None, description="Their budget: highest price, pesos.")
    sort: SortOrder | None = Field(
        default=None, description="'price_asc' cheapest first, 'price_desc', 'relevance'."
    )


class SearchProductsRequest(BaseModel):
    query: str = Field(
        description="What to type in the store's search box, in Spanish as the store names "
        "it: 'notebook gamer', 'monitor 27', 'rtx 4060'."
    )
    open_index: int | None = Field(
        default=None,
        description="Open the result at this place, 1 for the first; leave it out to only "
        "show the results.",
    )


class FilterRequest(BaseModel):
    """Only the filters the visitor asked for."""

    category: str = Field(
        description="The listing: a category's name or path from the category list "
        "('Notebooks', '/categoria/...'), or 'search: words' for the search results."
    )
    filters: list[str] | None = Field(
        default=None,
        description="Each 'Facet: Option', as the category list or the listing writes them: "
        "['Marcas: Lenovo', 'RAM: 16GB']; several options of one facet as separate entries.",
    )
    min_price: int | None = Field(default=None, description="Pesos, for Rango de precios.")
    max_price: int | None = Field(default=None, description="Pesos, for Rango de precios.")
    sort: SortOrder | None = Field(
        default=None, description="'price_asc' cheapest first, 'price_desc', 'relevance'."
    )
    remove: list[str] | None = Field(
        default=None,
        description="Filters to take off the listing in front, each 'Facet: Option' as it is on: "
        "['Marcas: Lenovo']. Its chip is pressed, in place.",
    )
    clear: bool | None = Field(
        default=None, description="True to take every filter off ('Limpiar todos'), in place."
    )
    page: int | None = Field(default=None, description="The listing's page to show, 1 the first.")
    size: Literal[12, 24, 32] | None = Field(
        default=None, description="Products per page: 12, 24 or 32 ('Productos por página')."
    )


class OpenProductRequest(BaseModel):
    path: str = Field(
        description="The product's path, '/producto/<id>', from find_products or their screen."
    )
    tab: ProductTab | None = Field(
        default=None,
        description="'specs' for its Especificaciones, 'about', 'warranty', 'stock' for its "
        "stock by store, 'photos', 'zoom' for the big photos, 'pickup' for the stores that have "
        "it for pickup, or 'price_note' for what Transferencia / Débito means.",
    )


class CheckPricesRequest(BaseModel):
    paths: list[str] = Field(description="Up to six '/producto/<id>' paths to price live.")


class CheckStockRequest(BaseModel):
    path: str | None = Field(
        default=None,
        description="The product's '/producto/<id>'; leave it out for the product in front.",
    )
    store: str | None = Field(
        default=None,
        description="The store they asked about, as said: a store's name, a comuna or a city "
        "('Maipú', 'Concepción', 'Costanera Center').",
    )


class ShowStoreRequest(BaseModel):
    name: str = Field(description="The store, as said: its name, comuna or city.")


class CompareRequest(BaseModel):
    paths: list[str] = Field(
        description="Two or three '/producto/<id>' paths of one category, from their screen or "
        "your reads; the page opens those not in front to tick them."
    )


class UncompareRequest(BaseModel):
    path: str | None = Field(
        default=None, description="The '/producto/<id>' to take out of the comparison."
    )
    all: bool = Field(default=False, description="True to empty the comparator.")


class AddToCartRequest(BaseModel):
    path: str = Field(description="The product's path, '/producto/<id>'.")
    qty: int = Field(default=1, description="How many, as they said: 1 to 10.")


class UpdateCartRequest(BaseModel):
    line: str = Field(
        description="The cart line: its product path ('/producto/<id>') from read_screen's "
        "cart, or its name as the cart shows it."
    )
    qty: int = Field(
        description="How many of it they want in the cart now, 1 to 10; 0 takes it out."
    )


class ShowCartRequest(BaseModel):
    open: bool = Field(default=True, description="True to open the cart, false to close it.")


class CouponRequest(BaseModel):
    code: str = Field(description="The coupon code as the store writes it: 'LEN50'.")


# ─── The prompt ────────────────────────────────────────────────────────────────

_SITE_MAP_CHARS = 9000
_SECTIONS_PER_PAGE = 10
#: About 2,000 tokens: the top levels of the tree and the facets that matter.
_CATEGORIES_CHARS = 8000
_FACETS_SHOWN = 6
#: The categories ``read_category`` lists under one, at most.
_UNDER_SHOWN = 20
_OPTIONS_SHOWN = 6
#: Facets every listing has, which say nothing about one category.
_COMMON_FACETS = frozenset({"tiendas", "rango de precios", "marcas", "categorias"})
#: How the site's titles end, longest first.
_TITLE_SUFFIXES = (
    " - pcfactory.cl",
    " | pcFactory",
    " | pc Factory",
    " - pc Factory",
    " | PC Factory",
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


def _categories(k: Knowledge) -> str:
    """The tree, top level first: each node's name, id and path, and for the
    listings below the top, the facets that tell one apart (the ones every
    listing has are left out) with a few of their options."""
    lines: list[str] = []
    size = 0
    for c in sorted(
        k.unique_categories(), key=lambda c: (c.level or 9, -(c.products or 0), c.path)
    ):
        if c.level > 3:
            continue
        facets = [f for f in c.facets if facet_key(f.name) not in _COMMON_FACETS]
        opts = "; ".join(
            f"{f.name}: {', '.join(f.options[:_OPTIONS_SHOWN])}"
            + (
                f" +{len(f.options) - _OPTIONS_SHOWN} more"
                if len(f.options) > _OPTIONS_SHOWN
                else ""
            )
            for f in facets[:_FACETS_SHOWN]
            if f.options
        )
        line = f"- {c.name} (id {c.id}) {c.path}" + (f" — {opts}" if opts and c.level >= 2 else "")
        size += len(line) + 1
        if size > _CATEGORIES_CHARS:
            lines.append("- … more: read_category with its name.")
            break
        lines.append(line)
    return "\n".join(lines) or "(The categories are not loaded: use find_products with words.)"


def _stores_list(k: Knowledge) -> str:
    by_zone: dict[str, list[str]] = {}
    for s in k.stores:
        by_zone.setdefault(s.zone or "Chile", []).append(
            s.name + (f" ({s.city})" if s.city and norm(s.city) not in norm(s.name) else "")
        )
    return (
        "\n".join(f"- {zone}: {', '.join(names)}" for zone, names in by_zone.items())
        or "(The store list is not loaded: show_store finds them on /tiendas.)"
    )


def _topics(k: Knowledge) -> str:
    return "\n".join(f"- {t.id}: {t.title}" for t in k.topics.values()) or "(none loaded)"


def _prompt(k: Knowledge, today: date | None = None) -> str:
    today = today or datetime.now(TIMEZONE).date()
    return f"""You are {AGENT_NAME}, the voice tech advisor on PC Factory's online store, www.pcfactory.cl. PC Factory is Chile's best-known technology retailer: notebooks, gamer gear, graphics cards, monitors, smartphones, components and much more, with stores across Chile, and "Compra y retira de inmediato". A visitor is shopping on the store right now and has called you from the corner of the page. You can see and move their screen: you search the catalogue live, open products and their specifications, filter and sort a listing, read live prices and each store's stock, show a store, compare products side by side on the store's own comparison page, add to their cart, apply a coupon, and take them to the checkout's delivery step. You are the best advisor in the store: quick, warm and concrete, you know what matters in a machine and you recommend, you don't recite. Say the store's name as "PC Factory".

# You narrate, and the screen follows your words
You talk the visitor through their screen like an advisor standing beside them, pointing as you talk. Fast: you talk and act at the same time.
- Put a screen cue at the start of the sentence it belongs to. The page moves when your voice reaches that sentence. The visitor never hears a cue.
  - {{page: /path}} opens a page of the store at its top: a page from the site pages list, a category's path, a product's /producto/<id> from what you read this call, or the store list /tiendas.
  - {{show: Heading}} scrolls to a heading, section, card or specification on the page in front (or the one a page cue just opened) and rings it. On a product page it rings a row of the Especificaciones table by its label ("Procesador", "Memoria RAM", "Tarjeta de Video", "Almacenamiento", "Pantalla").
  - {{tab: specs}} opens a tab of the product in front: specs (Especificaciones), about (Sobre este producto), warranty (Garantía), stock (its stock by store, Disponibilidad), photos, zoom (the big photos, in the gallery's own window), pickup (the stores that have it for pickup, "Disponibilidad de retiro en tienda") or price_note (the store's own words on what Transferencia / Débito means).
  - {{faq: Question}} opens that question of a FAQ (Centro de ayuda, Cyber, Gamer) and rings its answer.
  - {{store: Name}} shows one store on /tiendas, with its address and hours.
  - {{filter: Facet | Option}} narrows the listing in front by one of its facets, the option exactly as the listing or the category list writes it: {{filter: Marcas | Lenovo}}, {{filter: RAM | 16GB}}, {{filter: Tiendas | Maipú}}. Two options of one facet go in one cue only when the visitor named both: "Lenovo o HP" is {{filter: Marcas | Lenovo, HP}}.
  - {{sort: price_asc}} sorts the listing in front: price_asc (cheapest first), price_desc or relevance.
  - {{compare: Label}} on the comparison page rings one row of the table across the products, by its label as the table writes it ("Procesador", "RAM", "Almacenamiento", "Pantalla", "Tarjeta de Video"); {{compare: diferencias}} switches on "Destacar diferencias", which marks in green what changes; {{compare: precio}} rings the prices.
  - {{menu: Categoría}} opens the store's Categorías menu on a top category ("Computadores y Tablets", "Partes y Piezas / Componentes", "Gamer y Poder Gráfico") and shows what is under it.
- OPEN WITH A CUE, then one cue at the start of each sentence that talks about something on screen. Talk about what you ring, as you ring it:
  - On a product: "{{tab: specs}} Mira las especificaciones. {{show: Procesador}} Trae un Ryzen siete, rápido para todo. {{show: Memoria RAM}} Con dieciséis gigas de RAM, de sobra para la U. {{show: Almacenamiento}} Y un SSD de quinientos doce gigas."
  - On the home page: "{{show: Cupones}} Hoy hay cupones de Lenovo. {{show: Ofertas y Lanzamientos}} Y aquí están las ofertas de la semana."
  - On a listing: "{{filter: Marcas | Lenovo}} Te dejo solo los Lenovo. {{filter: RAM | 16GB}} Con dieciséis gigas. {{sort: price_asc}} Y del más barato al más caro."
  - On a question: "{{page: /centro-de-ayuda/compra-con-retiro-en-tienda}} El retiro en tienda es gratis."
- Use headings, labels and options exactly as the site pages list, the category list or the screen lines spell them. Cues are in Spanish, also inside an English reply: "{{tab: specs}} Here are the specs."
- Never make up a heading, a path or a product id: a product is opened only by an id you read this call.
- One cue per sentence at most, before the sentence, never inside it.
- A filter or sort cue sits on a promise of what you are doing ("Te dejo solo los Lenovo."), never on a statement of the result: the grid changes after. What the listing then shows comes to you in square brackets: say it on your next turn. A filter that could not be applied is said to you, to say so.
- TICK ONLY WHAT THE VISITOR NAMED. "Al menos dieciséis gigas", "16 o más", "minimum 16GB" is {{filter: RAM | 16GB}}, one option, never 16GB, 24GB and 32GB: say that bigger ones exist and offer to add them. Never add an option, a brand or a range they did not say.
- A facet's options in a line may be cut short, and a listing has more than any line shows: NEVER SAY AN OPTION OR A FILTER IS MISSING unless a line from the page says it refused it. Write the cue with the option as they said it; the page answers. read_screen's listing lists every option of every facet.
- A search results listing (/busqueda-avanzada) filters only by Tiendas, Categorías and Marcas. For a spec (processor, RAM, screen, graphics card), open the category's listing with filter_listing and its filters: "notebooks Lenovo con i7" is filter_listing on Notebooks with ["Marcas: Lenovo", "Procesador: INTEL Core i7"].
- A reply that calls a move tool has no page cue: the move takes them there. The cart and the checkout are only ever reached by their moves, never by a cue.

# A tech advisor, not a brochure
- Find out the use, then the budget, one question at a time, only what you do not know yet: "¿Para qué lo vas a usar?", "¿Hasta cuánto quieres gastar?". If they already said, go straight to options.
- Then find_products with the category and the words that matter, and their budget as max_price. When the products come back, name two or three that fit, each with its transfer price and whether it is in stock, recommend one with the reason that matters for their use, and open it with a page cue: "{{page: /producto/57233}} Te abro el Lenovo, que es el que más te conviene."
- What matters, by use: gaming, the graphics card (an RTX or Radeon and its VRAM), then the processor, sixteen gigas of RAM or more and the screen's hertz; study and office, a Core i5 or Ryzen 5, eight to sixteen gigas and an SSD; design, video and programming, sixteen to thirty-two gigas, a good processor and a good screen. Say why in plain words.
- Every spec and every price you say is one you read this call: from find_products, the product page's lines, check_prices or the cart. Never from memory, never invented, never from another product.
- End every turn with one short, useful next step as a yes-or-no question: "¿Te lo abro?", "¿Te reviso si está en tu tienda?", "¿Lo comparamos con el HP?", "¿Te lo agrego al carro?". Never "anything else?".

# How you sound
You are heard, not read, so keep it light and quick.
- A turn is two to five short sentences. Every sentence under fifteen words. One idea per sentence, one number per sentence.
- THE FIRST SENTENCE IS A FEW WORDS. The visitor hears nothing until your first sentence has been voiced, so open every reply with a sentence of two to six words that ends in a full stop, with the answer in it. A cue may come before it.
- Your first word is the answer: no filler, no "great question", no repeating their question back.
- Spoken words only, apart from cues: no lists, no markdown, no symbols, never an exclamation mark.
- Write every number, price and measure as spoken words. Prices are Chilean pesos: "$729.990" is "setecientos veintinueve mil novecientos noventa pesos", in English "seven hundred and twenty-nine thousand nine hundred and ninety pesos"; the lines in square brackets give each price with how to say it. Say a model the short way people say it ("un Ryzen siete", "una RTX cuarenta sesenta", "un Core i cinco"), and capacities in words ("dieciséis gigas de RAM", "un tera de SSD", "quince coma seis pulgadas", "ciento cuarenta y cuatro hertz"). Never say a product id, a path or a full product name with all its codes: "el Lenovo IdeaPad", "el HP de catorce pulgadas".
- Lines in square brackets come from their screen, not the visitor: the page in front, what changed on it, a move's answer. Never read them out; use them.
- read_screen reads what their screen shows now: the product page in front (prices, stock, specifications), the listing (its products in order with prices, its filters), the cart, or the checkout step. Call it before you say a price, a stock or what is in the cart when no line already gives it, with nothing written before it.
- Never list what is on screen: name two or three things, and point at the rest.
- Always answer. A reply with no words leaves the visitor in silence.

# Spanish or English
You speak Spanish as a native of Latin America, and English. The call starts in Spanish unless the visitor chose English.
- Answer in Spanish. Move to English only when the visitor says at least two full sentences in English in one turn, or asks for English; then answer in English from that reply on, and if the visitor goes back to Spanish, so do you. Speech recognition often hears a short Spanish reply or a Chilean name as English ("See" for "sí", "My poo" for "Maipú"): the visitor is still speaking Spanish, so answer in Spanish. Your voice follows the language you write.
- Except when they chose a language: a line in square brackets says so. Then answer in that language whatever they speak, until they ask you to switch.
- When they ask for the other language in words that are not already it ("¿Puedes hablar en inglés?", "Can we speak Spanish?"), answer in that language and call set_language in the same response.
- One language per reply: in a Spanish reply every sentence is Spanish, and masculine forms of yourself ("encantado de ayudarte").
- Your Spanish is neutral Latin American Spanish, warm and natural for a Chilean visitor, never the Spanish of Spain and never heavy slang.
  - Address the visitor as "tú", as the store does, never "usted"; several people are "ustedes", never "vosotros", and never its verb forms ("queréis", "tenéis") or "os".
  - Chile's own store words are right here: the "carro" or "carro de compras", never "cesta"; "despacho" for delivery; "retiro en tienda"; "boleta"; "cuotas sin interés"; "notebook" for a laptop; "computador", never "ordenador"; "celular", never "móvil"; "audífonos", never "auriculares"; "tarjeta de video" or "tarjeta gráfica".
  - Use Latin American words: "mostrar" ("te muestro"), not "enseñar"; "completar", not "rellenar"; "disculpa", not "perdona"; "está bien" or "perfecto", never "vale"; "tomar", never "coger"; "¿te sirve?", not "te viene bien". Write "video", never "vídeo".
  - For something just done, use the simple past: "Abrí el producto", "Lo agregué", not "He abierto".
- In English, say the store's Spanish names as they are written ("Transferencia", "despacho", "retiro en tienda") and explain them in a few words when they are not obvious.

# Every fact has a source
- Every fact comes from the knowledge below, a topic you read, a search result, or what their screen and your moves reported. If you cannot find it, say so, and offer the Centro de ayuda.
- Never promise stock, a delivery date, a delivery cost, a discount or a restock the site does not state.

# Every response starts with words
Write your answer, with its cues, first; any tool call comes at the end of the same response.
- read_topic, read_category, search_site and read_screen come straight back to you within this same turn, but each one makes the visitor wait. Answer from what you know below whenever it covers the question. Read only for what is not here, and then call the read first, with nothing written before it.
- Every other tool is a move: find_products, check_prices, check_stock, search_products, filter_listing, open_product, show_store, compare_products, remove_from_comparison, add_to_cart, update_cart_item, show_cart, apply_coupon, start_checkout. The page does it a moment later and tells you in square brackets, and you talk it through then. In the reply that calls one, say only what you are doing ("Te busco opciones.", "Te reviso el stock en Maipú.", "Te lo agrego al carro."), never that it is done and never a result.
- One move at a time: when a tool says the page is still working on the last move, what you asked for follows by itself. Say so in a few words, and never call it again.
- While a move is still running (a line says so), never say it failed: say you are still on it. Never say the store, the site or the page is slow: it is the store's own site. If a line later says it was done after all, correct yourself in a few words.
- A question about the call itself — "can I speak English?", "can you hear me?", "who are you?" — gets an answer and nothing else: no move, no page.

# Finding products
- find_products reads the store's own catalogue in their browser: up to eight products with their live prices and stock, and how many match. It is how you answer "¿tienen…?", "¿qué me recomiendas?" and "¿cuál es más barato?". Search with the store's Spanish words ("notebook gamer rtx 4060", "monitor 27"), a category from the list below when you know it, a brand and their budget.
- search_products types their words into the store's own search box so the results page shows on their screen; with open_index it opens one of the results. Use it when they want to see the results themselves.
- filter_listing opens a category's listing with its facets already on, in one move. On the listing in front, filter with cues as you talk instead. filter_listing also takes filters off in place (remove, or clear for "Limpiar todos"), shows 12, 24 or 32 per page (size) and turns the page (page): "saca la marca" is remove, "muéstrame todos" is size 32, "la página siguiente" is page.
- open_product opens a product, with a tab when you name one; on the product in front, use a tab cue.

# Prices and stock
- The store shows three prices. The headline is "Transferencia / Débito": the one you say. "Otros medios de pago" is the price with a credit card: say it when they ask about paying with a card or in cuotas, or when the difference matters. The struck "precio de referencia" and its percentage, only when the lines say it is a real saving.
- A price or stock you say is one a line from this call gives. Without one, say you will check it, and call check_prices; never a price from memory.
- Stock is "aprox." and twenty minutes behind, as the store says: say "tiene stock" or "quedan pocas", never a promise. "¿Lo tienen en la tienda de Maipú?" is check_stock with the store: say what it found for that store, and offer to show the store ({{store: Name}}) or nearby stores that have it.
- Delivery is priced only in the checkout, once they choose despacho and their address: never quote a delivery cost; the store has no delivery estimator. Store pickup ("retiro en tienda") is free. The store shows no cuotas calculator: never promise cuotas or their number.
- Never press, and never offer to press, what is the visitor's own: "Usar mi ubicación actual" (ask for their comuna instead), the order tracking form on /estado-despacho (their RUT and boleta), "Copiar código" on a coupon (apply_coupon does it in the cart), the newsletter and the business quote forms, and the human advisor's button ("Asesórate Online", a person, Monday to Friday 9:00 to 18:30, which you may mention).

# Comparing
- compare_products uses the store's own comparator, as the visitor would: it ticks each product's Comparar box (opening a product's page when it is not in front), so the comparator's bar comes up, presses its Comparar, and opens the comparison page with their specs side by side. Two or three products, all of one category: the store refuses a fourth, and refuses mixing categories ("Notebooks" and "Notebooks Gamer" are two). In the reply that calls it, say only that you are comparing them.
- When the comparison page is in front, a line gives you its rows, the ones that differ first. Walk them through it with cues, ROW BY ROW, ONE ROW PER SENTENCE, on the two to four rows that matter for their use, the cue first: "{{compare: Procesador}} El primero trae un Core i siete, el segundo un i cinco. {{compare: RAM}} Los dos tienen dieciséis gigas. {{compare: diferencias}} Te marco en verde lo que cambia." Then recommend one for their use, with the reason, and offer the next step ("¿Te abro el primero?", "¿Lo agregamos al carro?").
- Say only values the comparison line gives. When one product has no value for a row, say so, never guess it. remove_from_comparison takes a product out of the comparison, or empties the comparator.

# The cart, the coupon and the checkout
- add_to_cart, update_cart_item, apply_coupon and start_checkout change what is theirs: call one only when the visitor asked for exactly that in their last words, or said yes to your offer of it. Otherwise offer it as a yes-or-no question and wait for the yes.
- add_to_cart adds the product with the quantity they said (one unless they said more). update_cart_item changes how many of a line they have, 0 takes it out. show_cart opens their cart.
- apply_coupon types a code into the cart's "Cupón de descuento" and presses Aplicar. A code comes from the knowledge below or their screen, or they say it.
- start_checkout takes them from the cart to the checkout as a guest ("Continuar como invitado", never a login), and stops at "Tipo de entrega". There THEY choose "Retiro en tienda" (free) or "Despacho a domicilio", and they log in or type their RUT, address and payment themselves.
- THE RUT, ANY PASSWORD, A CARD AND THE ADDRESS ARE THEIRS, always. Never ask for one, never repeat one, never write one anywhere, even when they say it: say "Eso lo completas tú en la página." in their language. Never log in, never choose the delivery method, never press anything on the payment step. Never say the order is placed.

# Tabs
- The visitor may have several store tabs open. Lines in brackets tell you which tabs are open and which is in front. "Go back to the other tab" is focus_tab with that tab's id.

# What you know
- Today is {today:%A, %d %B %Y}, in Santiago.
- Topics you can read with read_topic, when the knowledge below does not cover a question:
{_topics(k)}
- search_site finds an information page, section or FAQ by its words. Its results name the page and section, which you can then cue.

# PC FACTORY
{k.l1}

# Categories (name, id, path — and for the listings, the facets that tell them apart)
A few options of each facet are shown ("+N more" are not); read_category gives one category's full filters, all their options and the categories under it, and read_screen the listing in front's.
{_categories(k)}

# Stores
{_stores_list(k)}

# Site pages
{_site_map(k)}
"""


# ─── Greeting ──────────────────────────────────────────────────────────────────

_INTRO: dict[Lang, str] = {
    "es": f"Hola, soy {AGENT_NAME}, tu asesor de voz de PC Factory.",
    "en": f"Hi, I'm {AGENT_NAME}, PC Factory's voice advisor.",
}
_GREETING: dict[Lang, str] = {
    "es": "Te ayudo a encontrar el notebook, el celular o el componente que buscas. "
    "¿Qué estás buscando?",
    "en": "I can help you find the right laptop, phone or part. What are you looking for?",
}
#: The opener's second sentence for the page the call starts on, by a word in
#: its path; the first match wins, and anything else gets the plain greeting.
_OPENERS: tuple[tuple[str, dict[Lang, str]], ...] = (
    (
        "/carro",
        {
            "es": "Te ayudo con tu carro: revisarlo, aplicar un cupón o pasar a la compra. "
            "¿Qué necesitas?",
            "en": "I can help with your cart: go over it, apply a coupon or check out. "
            "What do you need?",
        },
    ),
    (
        "/checkout",
        {
            "es": "Te acompaño en la compra; la entrega y tus datos los eliges tú. ¿Alguna duda?",
            "en": "I'm here for your checkout. The delivery type and your details are yours "
            "to choose. Any questions?",
        },
    ),
    (
        "/producto/",
        {
            "es": "Te cuento de este producto o te reviso el stock en tu tienda. "
            "¿Qué quieres saber?",
            "en": "I can tell you about this product or check stock at your store. "
            "What would you like to know?",
        },
    ),
    (
        SEARCH_PATH,
        {
            "es": "Te ayudo a elegir entre estos resultados. ¿Para qué lo vas a usar?",
            "en": "I can help you choose among these results. What will you use it for?",
        },
    ),
    (
        "notebook",
        {
            "es": "Te ayudo a elegir tu notebook. ¿Para qué lo vas a usar?",
            "en": "I can help you choose a laptop. What will you use it for?",
        },
    ),
    (
        "gamer",
        {
            "es": "Te ayudo a armar tu equipo gamer. ¿Qué juegos te gustan?",
            "en": "I can help you pick your gaming gear. What do you like to play?",
        },
    ),
    (
        "tarjetas-graficas",
        {
            "es": "Te ayudo a elegir tu tarjeta de video. ¿Qué juegos y a qué resolución?",
            "en": "I can help you choose a graphics card. Which games, at what resolution?",
        },
    ),
    (
        "monitor",
        {
            "es": "Te ayudo a elegir tu monitor. ¿Es para jugar, trabajar o diseñar?",
            "en": "I can help you choose a monitor. Is it for gaming, work or design?",
        },
    ),
    (
        "smartphones",
        {
            "es": "Te ayudo a elegir tu celular. ¿Qué es lo que más te importa?",
            "en": "I can help you choose a phone. What matters most to you?",
        },
    ),
    (
        "/categoria/",
        {
            "es": "Te ayudo a elegir en esta categoría. ¿Para qué lo necesitas?",
            "en": "I can help you choose in this category. What do you need it for?",
        },
    ),
    (
        "/tiendas",
        {
            "es": "Te ayudo a encontrar tu tienda más cercana. ¿En qué comuna estás?",
            "en": "I can help you find your nearest store. Where are you?",
        },
    ),
    (
        "/centro-de-ayuda",
        {
            "es": "Te ayudo con despacho, retiro, garantía o medios de pago. ¿Qué necesitas saber?",
            "en": "I can help with delivery, pickup, warranty or payment. What do you need to know?",
        },
    ),
)


def _is_product_path(path: str) -> bool:
    return product_path(path) is not None


def greeting(path: str | None, lang: Lang = OPENING) -> str:
    """The written opener, in ``lang``, tailored to the page the call starts on."""
    here = canonical_path(path or "/")
    if search_query(path or "") is not None:
        here = SEARCH_PATH
    line = _GREETING[lang]
    for word, lines in _OPENERS:
        if word in here:
            line = lines[lang]
            break
    return f"{_INTRO[lang]} {line}"


# ─── Written lines for moves ───────────────────────────────────────────────────

#: His line for a silent turn, by what moved. A move is not done when the turn
#: ends: the page answers later, so its line says what he is doing.
_LANDED: dict[str, dict[Lang, str]] = {
    "shown": {"en": "Here it is.", "es": "Aquí lo tienes."},
    "tab": {"en": "There's that tab.", "es": "Ahí tienes esa pestaña."},
    "find": {"en": "I'm looking for options.", "es": "Te busco opciones."},
    "search": {"en": "I'm searching the store for it.", "es": "Lo busco en la tienda."},
    "filter": {"en": "I'm filtering the list for you.", "es": "Te filtro la lista."},
    "product": {"en": "I'm opening the product.", "es": "Te abro el producto."},
    "prices": {"en": "I'm checking the prices.", "es": "Te reviso los precios."},
    "stock": {"en": "I'm checking the stock.", "es": "Te reviso el stock."},
    "store": {"en": "I'm showing you the store.", "es": "Te muestro la tienda."},
    "compare": {"en": "I'm putting them side by side.", "es": "Te los comparo."},
    "uncompare": {
        "en": "I'm taking that out of the comparison.",
        "es": "Lo saco de la comparación.",
    },
    "cart_add": {"en": "I'm adding it to your cart.", "es": "Lo agrego a tu carro."},
    "cart_show": {"en": "I'm opening your cart.", "es": "Te abro el carro."},
    "cart_update": {"en": "I'm changing that in your cart.", "es": "Te lo cambio en el carro."},
    "cart_remove": {"en": "I'm taking it out of your cart.", "es": "Lo saco de tu carro."},
    "cart_close": {"en": "I'm closing the cart.", "es": "Te cierro el carro."},
    "coupon": {"en": "I'm applying the coupon.", "es": "Te aplico el cupón."},
    "checkout": {
        "en": "I'm taking you to the delivery step.",
        "es": "Te llevo al tipo de entrega.",
    },
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
    "commerce.cart_add": {"en": "Done, it's in your cart.", "es": "Listo, ya está en tu carro."},
    "commerce.cart_update": {
        "en": "Done, your cart is updated.",
        "es": "Listo, tu carro quedó al día.",
    },
    "apply_coupon": {"en": "Done, the coupon is applied.", "es": "Listo, el cupón quedó aplicado."},
    "start_checkout": {
        "en": "Here's the delivery step: you choose store pickup, which is free, or delivery.",
        "es": "Listo, aquí eliges retiro en tienda, que es gratis, o despacho a domicilio.",
    },
}
#: The page's detail for an add: "added 1 x Notebook Lenovo …; …" (or a times sign).
_ADDED = re.compile(r"^added \d+ (?:×|x|of) (.+?)(?: \(|;|$)")  # noqa: RUF001


#: His line for a move still running after Stage's ``HOLDING_LINE_S``, by
#: move, said once in a quiet spell with no model request before it, so a move
#: still under way is not heard as a failed one; ``""`` is any other move. A
#: line says he is still at it and never blames the store: "the store is slow"
#: is heard as a fault of the site's owner, whose site this is.
_HOLDING: dict[str, dict[Lang, tuple[str, ...]]] = {
    "commerce.cart_add": {
        "en": ("Still adding it, one moment.", "Almost there, adding it to your cart."),
        "es": ("Lo sigo agregando, un momento.", "Ya casi, lo estoy agregando a tu carro."),
    },
    "commerce.cart_update": {
        "en": ("Still updating your cart, one moment.", "Almost done with your cart."),
        "es": ("Sigo actualizando tu carro, un momento.", "Ya casi termino con tu carro."),
    },
    "compare.add": {
        "en": ("Still setting up the comparison, one moment.", "Almost there with the comparison."),
        "es": ("Sigo armando la comparación, un momento.", "Ya casi está la comparación."),
    },
    "commerce.search": {
        "en": ("Still searching, one moment.", "Almost there with the results."),
        "es": ("Sigo buscando, un momento.", "Ya casi tengo los resultados."),
    },
    "apply_coupon": {
        "en": ("Still applying the coupon, one moment.", "Almost done with the coupon."),
        "es": ("Sigo aplicando el cupón, un momento.", "Ya casi queda el cupón."),
    },
    "start_checkout": {
        "en": ("Getting the checkout ready, one moment.", "Almost there with the checkout."),
        "es": ("Estoy preparando la compra, un momento.", "Ya casi llegamos al tipo de entrega."),
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


#: The tool each move is sent by, where the names differ: what the model
#: called it, and so what a line about its result names.
_TOOL_OF: dict[str, str] = {
    "commerce.search": "search_products",
    "commerce.cart_add": "add_to_cart",
    "commerce.cart_update": "update_cart_item",
    "commerce.cart_show": "show_cart",
    "compare.add": "compare_products",
    "compare.remove": "remove_from_comparison",
    "stores.show": "show_store",
    "product.tab": "open_product",
}

#: The moves whose effect a listing on screen is, and a product page's.
_LISTING_MOVES = ("filter_listing", "commerce.filter", "commerce.sort", "commerce.search")
_PRODUCT_MOVES = ("open_product", "commerce.search")


def _said_list(items: list[str], lang: Lang) -> str:
    """ "Lenovo and HP", "Lenovo, HP y ASUS"."""
    if len(items) < 2:
        return "".join(items)
    last = " and " if lang == "en" else " y "
    return ", ".join(items[:-1]) + last + items[-1]


#: Where a product's name turns into its codes: what is said is what comes before.
_NAME_CODES = re.compile(
    r"\s(?=(?:Intel|AMD|Ryzen|Core|Snapdragon|Apple\s+M\d|\d+\s?(?:GB|TB|Hz)"
    r"|\d+(?:[.,]\d+)?\s?(?:\"|''|”|pulg)|i[3579]-|RTX|GTX|RX\s?\d|[A-Z0-9]{2,}-[A-Z0-9]+|\w*\d\w*-\w+|\("
    # A model code: five or more capitals and digits, mixed ("15IRH8", "FX507ZC4").
    r"|(?=[A-Z0-9]{5,}\b)(?:\d+[A-Z]|[A-Z]+\d)[A-Z0-9]*\b))",
)


#: Words a said name never ends on: they lead into what was cut ("ThinkPad
#: T14 Gen" was "ThinkPad T14 Gen 6", dev call 31a45613).
_DANGLING = frozenset(
    "gen generation generación serie series de del con y and with for para - / + |".split()  # noqa: SIM905
)


def short_name(name: str, words: int = 6) -> str:
    """A product's name as said aloud: up to its first code or spec, at most
    ``words`` words ("Notebook Lenovo IdeaPad Slim 3 Intel Core i5…" →
    "Notebook Lenovo IdeaPad Slim 3"), never ending on a word that leads into
    the cut ("Gen" keeps its number: "ThinkPad T14 Gen 6")."""
    head = _NAME_CODES.split(name.strip(), maxsplit=1)[0].strip(" ,-")
    all_words = (head or name).split() if len((head or name).split()) >= 2 else name.split()
    kept = all_words[:words]
    rest = all_words[words:]
    if (
        kept
        and kept[-1].lower() in {"gen", "generation", "generación"}
        and rest
        and rest[0].isdigit()
    ):
        kept.append(rest[0])
    while len(kept) > 1 and kept[-1].lower().strip(".,") in _DANGLING:
        kept.pop()
    if len(kept) >= 2 and kept[-1].lower() in {"gen", "generation", "generación"}:
        kept.pop()
    return " ".join(kept)


#: Facets whose options read as a brand ("de Lenovo"), a place ("en
#: Maipú") or a category ("en Notebooks"); every other is a spec ("con 16GB").
_BRAND_FACETS = frozenset({"marcas", "marca"})
_PLACE_FACETS = frozenset({"tiendas", "tienda"})
_KIND_FACETS = frozenset({"categorias", "categoria"})
#: An option that is only a size ("16GB", "512 GB") says which facet it is.
_BARE_SIZE = re.compile(r"^\d+(?:[.,]\d+)?\s?(?:GB|TB|MB)$", re.IGNORECASE)


def _option_said(option: str) -> str:
    """An option as said: all-capital words of four letters or more in
    ordinary case ("INTEL Core i7" → "Intel Core i7"); codes stay."""
    return " ".join(
        w.capitalize() if len(w) >= 4 and w.isalpha() and w.isupper() else w for w in option.split()
    )


def filters_said(named: list[tuple[str, str]], lang: Lang) -> str:
    """The filters a move put on, as one natural phrase: "de Lenovo, con
    Intel Core i7 y 16GB de RAM" / "from Lenovo, with Intel Core i7 and 16GB
    of RAM". A manufacturer an option of another facet already names is left
    out ("INTEL" beside "INTEL Core i7")."""
    options = [o for _, o in named]
    kept = [
        (f, o)
        for f, o in named
        if not any(other != o and fold(other).startswith(fold(o) + " ") for other in options)
    ]
    brands = [_option_said(o) for f, o in kept if facet_key(f) in _BRAND_FACETS]
    places = [o for f, o in kept if facet_key(f) in _PLACE_FACETS]
    kinds = [o for f, o in kept if facet_key(f) in _KIND_FACETS]
    specs: list[str] = []
    for f, o in kept:
        key = facet_key(f)
        if key in _BRAND_FACETS | _PLACE_FACETS | _KIND_FACETS:
            continue
        said = _option_said(o)
        if _BARE_SIZE.match(o) and key in ("ram", "memoria ram", "memoria"):
            said = f"{said} of RAM" if lang == "en" else f"{said} de RAM"
        specs.append(said)
    parts: list[str] = []
    if kinds:
        parts.append(("in " if lang == "en" else "en ") + _said_list(kinds, lang))
    if brands:
        parts.append(("from " if lang == "en" else "de ") + _said_list(brands, lang))
    if specs:
        parts.append(("with " if lang == "en" else "con ") + _said_list(specs, lang))
    if places:
        parts.append(("at " if lang == "en" else "en ") + _said_list(places, lang))
    return ", ".join(parts)


def listing_line(
    e: ListingShown, lang: Lang, named: list[tuple[str, str]] | list[str] | None = None
) -> str:
    """His line the moment a listing he filtered, sorted or searched lands: how
    many, with what (``named``: the (facet, option) pairs his move put on, as
    the listing writes them), and the first card with its transfer price. Said
    with no model request before it."""
    n = e.count if e.count is not None else len(e.items)
    pairs = [x if isinstance(x, tuple) else ("", x) for x in (named or [])]
    what = filters_said(pairs, lang)
    if n == 0 or not e.items:
        if lang == "en":
            return f"No products show {what}." if what else "No products show for that."
        return (
            f"No aparece ningún producto {what}." if what else "No aparece ningún producto con eso."
        )
    first = e.items[0]
    name = short_name(first.name)
    price = ""
    if first.price is not None:
        said = pesos_said(first.price, lang)
        price = f", at {said}" if lang == "en" else f", a {said}"
    where = f" {what}" if what else ""
    if lang == "en":
        return (
            f"Here's one{where}: the {name}{price}."
            if n == 1
            else f"Here are {n}{where}. The first is the {name}{price}."
        )
    return (
        f"Aquí hay uno{where}: el {name}{price}."
        if n == 1
        else f"Aquí hay {n}{where}. El primero es el {name}{price}."
    )


def product_line(e: ProductShown, lang: Lang) -> str:
    """His line the moment a product he opened is on screen: its short name
    and its transfer price."""
    name = short_name(e.name) if e.name else ("the product" if lang == "en" else "el producto")
    price = ""
    if e.price is not None:
        said = pesos_said(e.price, lang)
        price = f", at {said} by transfer" if lang == "en" else f", a {said} con transferencia"
    line = f"Here's the {name}{price}." if lang == "en" else f"Aquí está el {name}{price}."
    if e.online_stock.strip() == "0" and not e.stores_with_stock:
        line += " It's out of stock right now." if lang == "en" else " Ahora está sin stock."
    return line


def _option_key(label: str) -> str:
    """A facet option, folded and without spaces: "16 GB" and "16GB" are one."""
    return re.sub(r"[^\w]", "", norm(label))


def _option_set(labels: str | list[str] | None) -> frozenset[str]:
    """The options in a filter's value — a list, or labels joined by ", " —
    folded, as a set: the order never counts."""
    items = labels.split(", ") if isinstance(labels, str) else list(labels or [])
    return frozenset(k for i in items if (k := _option_key(i)))


def _number_words() -> dict[str, str]:
    """Spoken numbers to digits, folded, both languages, up to 2048 (the
    sizes a visitor says: "dieciséis", "thirty-two", "quinientos doce")."""
    out: dict[str, str] = {}
    for n in [*range(1, 129), 256, 512, 1024, 2048]:
        for said in (_es_number(n), _en_number(n)):
            out[fold(said)] = str(n)
            out[fold(said).replace("-", " ")] = str(n)
    return out


_SAID_NUMBERS = _number_words()
_SAID_NUMBER = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in sorted(_SAID_NUMBERS, key=len, reverse=True)) + r")\b"
)


def _heard_tokens(said: str) -> tuple[set[str], str]:
    """What the visitor said, folded, numbers as digits: its words, and all of
    them run together."""
    text = _SAID_NUMBER.sub(lambda m: _SAID_NUMBERS[m.group(0)], fold(said))
    words = re.findall(r"[a-z0-9]+", text)
    return set(words), "".join(words)


def named_in(option: str, said: str) -> bool:
    """Whether the visitor's words ``said`` name ``option`` of a facet: its
    words run together ("intelcorei7" in "intel core i7"), a word of it with a
    digit ("i7"), or its number ("16" for "16GB", "dieciséis gigas")."""
    words, tight = _heard_tokens(said)
    key = _option_key(option)
    if key and key in tight:
        return True
    parts = re.findall(r"[a-z0-9]+", fold(option))
    if any(any(ch.isdigit() for ch in p) and p in words for p in parts):
        return True
    number = re.match(r"\d+", option.strip())
    return number is not None and number.group(0) in words


def _on_of(event: ListingShown, facet: str) -> list[str]:
    """The options checked in ``facet`` on the listing, as it writes them."""
    want = facet_key(facet)
    return next((f.on for f in event.facets if facet_key(f.facet) == want), [])


def _asked_filters(raw: Any) -> dict[str, list[str]]:
    """``filter_listing``'s "Facet: Option" strings, by facet."""
    out: dict[str, list[str]] = {}
    items: list[Any] = raw if isinstance(raw, list) else []  # pyright: ignore[reportUnknownVariableType]
    for item in items:
        if isinstance(item, str) and ":" in item:
            facet, option = item.split(":", 1)
            out.setdefault(facet.strip(), []).append(option.strip())
    return out


def landed_options(
    landing: Landing, event: ListingShown, facets: Iterable[str] = ()
) -> list[tuple[str, str]]:
    """The (facet, option) pairs a filter move put on, as the listing writes
    them, for its landing line: those of the facets this move asked for, and
    of ``facets`` (the other filters of the same turn). A sort names none."""
    move, args, cue = landing.move.id, landing.args or {}, landing.cue_args
    asked: list[str] = list(facets)
    if move == "commerce.filter" and cue:
        asked.append(cue[0])
    elif move == "filter_listing":
        asked += list(_asked_filters(args.get("filters")))
    elif not asked:
        return []
    keys = {facet_key(f) for f in asked}
    return [(f.facet, x) for f in event.facets if facet_key(f.facet) in keys for x in f.on]


def empty_listing(event: ListingShown) -> bool:
    """A listing with no products in it: a real answer only once the move's own
    result confirms it, never as it is drawn (the grid is empty for a moment
    while the store redraws it, dev calls 31a45613 and 8b363867)."""
    return event.count == 0 or not event.items


_CURATED = re.compile(r"^(?:https?://[^/]+)?/busqueda/?\?(?:.*&)?productos=([\d,]+)", re.IGNORECASE)


def _listing_base(path: str) -> str:
    """A listing's address without its query, but a search's with its words
    and a curated list's (``/busqueda?productos=…``) with its products."""
    if (q := search_query(path)) is not None:
        return search_path(q)
    if (m := _CURATED.match(path.strip())) is not None:
        return f"/busqueda?productos={m.group(1)}"
    return canonical_path(path)


def lands(landing: Landing, event: ListingShown | ProductShown) -> bool:
    """Whether ``event`` on screen is what ``landing``'s move asked for: a
    load shows the listing unfiltered before the move filters it, and that is
    not its effect."""
    move, args, cue = landing.move.id, landing.args or {}, landing.cue_args
    if isinstance(event, ProductShown):
        if move == "commerce.search":
            return args.get("open_index") is not None
        want = args.get("path")
        return isinstance(want, str) and product_path(event.path) == product_path(want)
    if empty_listing(event) and not landing.result:
        return False
    if move == "commerce.search":
        return args.get("open_index") is None and search_query(event.path) is not None
    if move == "filter_listing":
        path = args.get("category_path")
        if isinstance(path, str):
            here = _listing_base(event.path)
            want = _listing_base(path)
            if not (here == want or here.startswith(want + "/")):
                return False
        for facet, options in _asked_filters(args.get("filters")).items():
            if not _option_set(options) <= _option_set(_on_of(event, facet)):
                return False
        sort = args.get("sort")
        return not isinstance(sort, str) or event.sort == sort
    if move == "commerce.filter" and len(cue) >= 2:
        want = _option_set(cue[1])
        return bool(want) and want <= _option_set(_on_of(event, cue[0]))
    if move == "commerce.sort" and cue:
        return event.sort == cue[0]
    return False


def late_done_line(move: str, detail: str, lang: Lang) -> str | None:
    """:func:`done_line` for a move he was told was not confirmed, which the
    page then confirmed: "Done after all, … is in your cart."."""
    line = done_line(move, detail, lang)
    if line is None:
        return None
    rest = line.removeprefix("Listo, " if lang == "es" else "Done, ")
    if rest.startswith("Here's"):
        rest = "here's" + rest.removeprefix("Here's")
    return f"Al final sí, {rest}" if lang == "es" else f"Done after all, {rest}"


def done_line(move: str, detail: str, lang: Lang) -> str | None:
    """The written line for a confirmed move the page reports done, built
    from its detail; ``None`` when the detail says part of it is not."""
    if "not " in detail and "not applied" in detail:
        return None
    if move == "commerce.cart_add" and (m := _ADDED.match(detail)) is not None:
        name = m.group(1).strip()
        if name and not name.startswith("/"):
            return _DONE["add_to_cart_named"][lang].format(name=short_name(name))
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
_LISTED_IN_NOTE = 12
_SPECS_IN_NOTE = 30
_MOST_PRICED = 6
_FACETS_IN_NOTE = 10
_COMPARED_SPECS = 12


async def _silence() -> AsyncGenerator[Any, None]:
    for _ in ():
        yield


def _clip(items: list[str] | tuple[str, ...], most: int) -> str:
    more = f"; and {len(items) - most} more" if len(items) > most else ""
    return "; ".join(items[:most]) + more


def _match(want: str, options: list[str] | tuple[str, ...]) -> str | None:
    """The option ``want`` names: the same words, else the one it begins, else
    the one it is inside. Case, accents, spaces and punctuation do not count."""

    def folded(s: str) -> str:
        return " ".join(re.sub(r"[^\w\s]", " ", norm(s)).split())

    w = folded(want)
    if not w:
        return None
    pairs = [(folded(o), o) for o in options]
    tight = w.replace(" ", "")
    for test in (
        lambda o: o == w,
        lambda o: o.replace(" ", "") == tight,
        lambda o: o.startswith(w),
        lambda o: w.startswith(o) and len(o) > len(w) // 2,
        lambda o: w in o,
    ):
        if (hit := next((o for f, o in pairs if f and test(f)), None)) is not None:
            return hit
    return None


#: Paths the store always has, whether or not the crawl kept them as pages.
_FIXED_PAGES = frozenset({"/", "/carro", "/tiendas", "/centro-de-ayuda", "/categorias"})
#: Pages only a move takes them to: never cued from his own sentence.
_MOVE_PAGES = frozenset({"/carro"})
#: Paths no cue may open: the checkout (start_checkout goes there, after a
#: yes), the account, the login, a payment's own pages.
_NEVER = re.compile(
    r"^/(?:checkout|mi-cuenta|cuenta|login|ingres|registr|mis-compras|pago|webpay|"
    r"revisa-boleta|orden-de-servicio)"
)
#: The pages a visitor in the middle of buying is on: a question there is
#: answered in place, and his reply never moves them off it on its own.
_IN_FLOW = ("/producto/", "/carro", "/checkout")


#: The page for what the visitor asked about, when his reply forgets to show
#: it; each with the paths the store has used for it, the first the crawl has
#: wins. Matched on their own words, folded, in Spanish and English; the first
#: named wins. Products and listings are not here: those are moves.
_ASKED_PAGES: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...] = tuple(
    (re.compile(rf"\b(?:{w})", re.IGNORECASE), paths)
    for w, paths in (
        (
            r"retiro en tienda|retirar en (?:la )?tienda|retirarlo|pick ?up|click (?:and|&) collect",
            ("/centro-de-ayuda/compra-con-retiro-en-tienda",),
        ),
        (
            r"estado de mi despacho|seguir mi pedido|track(?:ing)? my order|donde esta mi pedido",
            ("/estado-despacho",),
        ),
        (
            r"despacho|despachan|envios?\b|cuanto (?:demora|tarda) (?:en )?llegar|shipping"
            r"|deliver(?:y|ies|ed|able|s)?\b",
            ("/centro-de-ayuda/compra-con-despacho-a-domicilio",),
        ),
        (
            r"garantia|warranty|devoluci|devolver|returns?\b|refund|cambios?\b de producto",
            ("/centro-de-ayuda/garantia-de-productos",),
        ),
        (
            r"tiendas? fisicas?|sus tiendas|las tiendas|donde (?:queda|quedan|estan) (?:la|las)"
            r" tiendas|sucursales|physical stores?|your stores|store locations?",
            ("/tiendas",),
        ),
        (
            r"medios de pago|formas? de pago|como (?:puedo )?pagar|payment methods?|pay with",
            ("/centro-de-ayuda/precios-y-medios-de-pago",),
        ),
        (r"como (?:se )?compr|how (?:do i|to) buy", ("/centro-de-ayuda/como-comprar",)),
        (r"venta empresas|para (?:mi )?empresa|\bb2b\b|factura (?:para|a) empresa", ("/empresas",)),
        (r"arma tu pc|armar (?:un |mi )?pc|build (?:a|my) pc", ("/arma-tu-pc",)),
        (
            r"centro de ayuda|help cent(?:er|re)|\bfaqs?\b|preguntas frecuentes",
            ("/centro-de-ayuda",),
        ),
        (r"(?:mi |el |tu )?carr(?:o|ito)\b|\bcart\b|basket", ("/carro",)),
    )
)
_ASKED_TAB = re.compile(r"\b(?:tabs?|pestanas?)\b", re.IGNORECASE)
#: Asking to add to the cart is a move, not the cart page.
_ADDS = re.compile(
    r"\b(?:agreg|anad|añad|pon(?:lo|la|er|me)|mete|echa|sum|add|put)\w*", re.IGNORECASE
)
#: A move on the cart: an add, a change, a removal, the checkout. With the
#: cart as recognition hears it ("add this to cut").
_CART_MOVE = re.compile(
    r"\b(?:agreg|anad|añad|pon(?:lo|la|er|me)|mete|echa|add|put|quit|sac(?:a|alo|ala|ar)\b"
    r"|elimin|borr|remove|take (?:it|them|that|one) out|cambi\w* (?:la )?cantidad"
    r"|change the (?:quantity|amount)|me lo llevo|lo llevo|lo compro|i'?ll take it"
    r"|checkout|check out)\w*"
    r"|\b(?:to|into|al|a la|a mi)\s+(?:the |my |mi |el |la )?"
    r"(?:cart|cut|card|carro|carrito)\b",
    re.IGNORECASE,
)


def asks_cart_move(text: str) -> bool:
    """Whether ``text`` asks for a move on the cart (an add, a change, the
    checkout) rather than to see the cart."""
    return bool(_CART_MOVE.search(fold(text)))


#: A plain yes, in either language, as recognition hears it.
_YES = re.compile(
    r"\b(?:si|dale|ya|ok(?:ay|ey)?|yes|yeah|yep|sure|claro|perfecto|de acuerdo|hazlo"
    r"|go ahead|do it|listo|obvio|vamos|confirm\w*|correcto|exacto)\b",
    re.IGNORECASE,
)
_NO = re.compile(
    r"^\W*(?:no|nop|nope|todavia no|aun no|not yet|mejor no|espera|wait)\b", re.IGNORECASE
)
#: What asks for each confirmed move by name, without a yes.
_ASKS_FOR: dict[str, re.Pattern[str]] = {
    "cart": _CART_MOVE,
    "coupon": re.compile(r"\b(?:cupon|coupon|codigo|code|descuento|discount)\b", re.IGNORECASE),
    "checkout": re.compile(
        r"\b(?:pag(?:ar|o|ue)|checkout|check out|compr(?:ar|arlo|o|emos)|finaliz\w*|termin\w*"
        r"|continu\w* (?:con )?(?:la )?compra|buy|pay)\b",
        re.IGNORECASE,
    ),
}


def consents(kind: str, last: str, before: str = "") -> bool:
    """Whether the visitor's last words let him make a confirmed move of
    ``kind`` (``cart``, ``coupon``, ``checkout``): they asked for it by name
    (in their last words, or the fragment before them), or said yes to his
    offer of it; never when their last words are a no."""
    said = fold(last)
    if _NO.search(said):
        return False
    return bool(_YES.search(said) or _ASKS_FOR[kind].search(fold(f"{before} {last}")))


_CALL_LANGUAGE = re.compile(
    r"\b(?:speak|talk|switch|change|continue|carry on|answer|reply|respond|go back|"
    r"habl\w*|cambi\w*|sig\w*|continu\w*|respond\w*|contest\w*|pas\w*|volv\w*)\b"
    r"[^.?!]{0,25}?\b(?:spanish|english|español|espanol|castellano|inglés|ingles)\b",
    re.IGNORECASE,
)
_TO_HIM = re.compile(
    r"^\W*(?:(?:hey|ok|okay|please|so|now|oye|bueno|por favor)\W+)*"
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
        if adds and paths == ("/carro",):
            continue
        named.append((m.start(), paths))
    if not named:
        return None
    paths = min(named)[1]
    if k is not None:
        return next((p for p in paths if p in _FIXED_PAGES or k.page(p) is not None), paths[0])
    return paths[0]


# ─── What must never be said back or typed ─────────────────────────────────────

#: A RUT, however it is written: 12.345.678-5, 12345678-K, 7654321-0.
_RUT = re.compile(r"\b\d{1,2}\.?\d{3}\.?\d{3}\s*-\s*[\dkK]\b")
#: The word, as said: "mi RUT es…", "el run".
_RUT_WORD = re.compile(r"\b(?:rut|run)\b", re.IGNORECASE)
#: Thirteen or more digits in a row (spaces and dashes aside): a card.
_CARD = re.compile(r"(?:\d[ -]?){13,}")
#: A password said out loud: the word, then what it is.
_SECRET = re.compile(
    r"\b(?:contrase(?:ñ|n)a|clave|password|cvv|cvc)\s*(?:es|is|:|=)\s*\S{3,}", re.IGNORECASE
)
#: A street address, as said: a street word and a number after it.
_ADDRESS = re.compile(
    r"\b(?:calle|avenida|av\.?|pasaje|camino|street|st\.?|avenue|ave\.?)\s+[\w\s]{2,40}?\d{1,5}\b",
    re.IGNORECASE,
)


def private_kind(value: str) -> str | None:
    """What of theirs ``value`` carries that must never be typed or said
    back: a RUT, a card, a password or an address; ``None`` when nothing."""
    if _RUT.search(value) or (_RUT_WORD.search(value) and re.search(r"\d{5,}", value)):
        return "a RUT"
    if _CARD.search(value):
        return "a card number"
    if _SECRET.search(value):
        return "a password"
    if _ADDRESS.search(value):
        return "an address"
    return None


_PRIVATE_NOTE = (
    "[What the visitor just said holds {what}. Never repeat it, never write it in a reply or "
    "a tool call, never ask for it: say in their language that it is theirs to type on the page "
    '("Eso lo completas tú en la página."), and carry on.]'
)


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
    pc factory pcfactory tienda producto productos precio precios desde aqui puedo""".split()  # noqa: SIM905
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


# ─── Moves and what answers them ───────────────────────────────────────────────

#: How long a move may take on the page before it is taken as unknown, by its
#: class: Stage's own table, but a confirmed move has longer (the cart, then
#: the checkout's full loads, then its guest step).
_MOVE_TAKES_S = {**RESULT_TIMEOUTS, MoveClass.CONFIRMED: 45.0}
#: A unit of his not reported played this long after it began is taken as done.
_PLAYOUT_MAX_S = 30.0
#: A cue's result with this detail says nothing to the model: the visitor
#: talked over it, or its words were never heard.
_QUIET_DROPS = frozenset({"interrupted", "stale"})
#: What a reply may write as a sort cue's order, folded.
_SORTS: dict[str, SortOrder] = {
    "price_asc": "price_asc",
    "price asc": "price_asc",
    "menor precio": "price_asc",
    "precio menor a mayor": "price_asc",
    "precio ascendente": "price_asc",
    "cheapest": "price_asc",
    "price_desc": "price_desc",
    "price desc": "price_desc",
    "mayor precio": "price_desc",
    "precio mayor a menor": "price_desc",
    "precio descendente": "price_desc",
    "relevance": "relevance",
    "relevancia": "relevance",
    "recomendados": "relevance",
}
#: What a reply may write as a product tab, folded.
_TABS: dict[str, ProductTab] = {
    "specs": "specs",
    "especificaciones": "specs",
    "specifications": "specs",
    "about": "about",
    "sobre este producto": "about",
    "descripcion": "about",
    "warranty": "warranty",
    "garantia": "warranty",
    "stock": "stock",
    "disponibilidad": "stock",
    "photos": "photos",
    "fotos": "photos",
    "galeria": "photos",
    "zoom": "zoom",
    "fotos grandes": "zoom",
    "big photos": "zoom",
    "pickup": "pickup",
    "retiro": "pickup",
    "retiro en tienda": "pickup",
    "disponibilidad de retiro en tienda": "pickup",
    "price_note": "price_note",
    "price note": "price_note",
    "transferencia": "price_note",
}
#: Which source of a price wins over which: the store's live read over the
#: page's, the page's over a card's.
_SOURCE_RANK = {"api": 3, "found": 3, "page": 2, "cart": 2, "listing": 1}
_SOURCE_SAID = {
    "api": "read live",
    "found": "read live",
    "page": "on the product page",
    "cart": "in the cart",
    "listing": "on the listing",
}


@dataclasses.dataclass(frozen=True)
class Live:
    """What their screen and his reads last said of one product's prices and stock."""

    path: str
    name: str = ""
    price: int | None = None
    card_price: int | None = None
    regular_price: int | None = None
    stock: str = ""
    source: str = "page"
    at: float = 0.0

    def line(self, lang: Lang) -> str:
        bits: list[str] = []
        if self.price is not None:
            bits.append(f"Transferencia / Débito {_money(self.price, lang)}")
        if self.card_price is not None and self.card_price != self.price:
            bits.append(f"otros medios de pago {_money(self.card_price, lang)}")
        if (pct := saving(self.price, self.regular_price)) is not None and self.regular_price:
            bits.append(
                f"precio de referencia {pesos(self.regular_price)}, a real saving of {pct}%"
            )
        if self.stock:
            bits.append(_stock_said(self.stock))
        return ", ".join(bits) + f" ({_SOURCE_SAID.get(self.source, self.source)})"


def _stock_said(stock: str) -> str:
    s = stock.strip()
    if s in ("0", ""):
        return "no stock online"
    if s.startswith("+"):
        return f"online stock {s} (plenty)"
    return f"online stock {s} units (approximate)"


def _product_note(e: ProductShown, lang: Lang) -> str:
    name = e.name or e.path
    head = "Live read of" if e.source == "api" else "The product page in front:"
    note = f"[{head} “{name}” ({e.path})" + (f", brand {e.brand}" if e.brand else "") + ". "
    seen = Live(e.path, name, e.price, e.card_price, e.regular_price, e.online_stock, e.source)
    note += seen.line(lang) if (e.price is not None or e.online_stock) else "no price read"
    note += "."
    if e.stores_with_stock is not None:
        note += f" In stock in {e.stores_with_stock} stores (approximate, 20 minutes behind)."
    if e.warranty:
        note += f" Garantía: {e.warranty}."
    if e.promo_until:
        note += f" Promo until {e.promo_until}."
    if e.specs:
        specs = [f"{k}: {v}" for k, v in e.specs.items()]
        note += f" Especificaciones (cue a row by its label): {_clip(specs, _SPECS_IN_NOTE)}."
    return note + "]"


def _listing_note(e: ListingShown, lang: Lang) -> str:
    where = e.title or e.path
    note = f"[The listing in front: “{where}” ({e.path})"
    if e.count is not None:
        note += f", {e.count} products"
    if e.filters:
        note += ", filtered by " + "; ".join(f"{k}: {v}" for k, v in e.filters.items())
    if e.sort:
        note += f", sorted {e.sort}"
    note += "."
    offered = [f for f in e.facets if f.options]
    if offered:
        # Every option of every facet: a facet cut short is an option he says
        # is not there (dev call 8b363867, "INTEL Core i7" was the 19th).
        note += (
            " Its facets, with every option (cue them as written): "
            + "; ".join(f"{f.facet} ({', '.join(f.options)})" for f in offered)
            + "."
        )
        if search_query(e.path) is not None:
            note += " A search filters by these only: for a spec, filter_listing on the category."
    if e.items:
        cards = [
            f"{i.name} ({i.path})" + (f", {_money(i.price, lang)}" if i.price is not None else "")
            for i in e.items
        ]
        note += f" On screen, in order (Transferencia / Débito): {_clip(cards, _LISTED_IN_NOTE)}."
    elif e.count == 0:
        note += " No product shows for these filters."
    return note + "]"


def _prices_note(e: PricesRead, lang: Lang) -> str:
    lines: list[str] = []
    for i in e.items:
        path = product_path(i.path) or i.path
        live = Live(path, i.name, i.price, i.card_price, i.regular_price, i.online_stock, "api")
        lines.append(f"{i.name or path} ({path}): {live.line(lang)}")
    note = f"[Live prices: {'; '.join(lines) or 'none'}."
    if e.missing:
        note += (
            f" Not priced: {', '.join(e.missing)} — not buyable right now: say so, never a "
            "price for them."
        )
    return note + "]"


def _found_note(e: ProductsFound, lang: Lang) -> str:
    asked = [
        f"“{e.query}”" if e.query else "",
        f"category {e.category_id}" if e.category_id else "",
        f"brand {e.brand}" if e.brand else "",
        f"from {pesos(e.min_price)}" if e.min_price else "",
        f"up to {pesos(e.max_price)}" if e.max_price else "",
    ]
    what = ", ".join(a for a in asked if a) or "everything"
    if not e.items:
        return (
            f"[find_products found nothing for {what}. Say so plainly, and offer to widen it: "
            "another budget, brand or words.]"
        )
    total = f"{e.total} match" if e.total is not None else "Some match"
    lines: list[str] = []
    for n, i in enumerate(e.items, 1):
        path = product_path(i.path) or i.path
        live = Live(path, i.name, i.price, i.card_price, i.regular_price, i.stock, "found")
        lines.append(
            f"{n}. {i.name} ({path})" + (f", {i.brand}" if i.brand else "") + f": {live.line(lang)}"
        )
    return (
        f"[find_products for {what}: {total}; the first {len(e.items)}, in the store's order — "
        + "; ".join(lines)
        + ". Name two or three that fit what they said, each with its transfer price and "
        "stock, recommend one for their use, and open it with {page: /producto/<id>}.]"
    )


def _stock_note(e: StockRead, k: Knowledge) -> str:
    name = e.name or e.path
    note = (
        f"[Stock of “{name}” ({product_path(e.path) or e.path}), approximate, 20 minutes behind: "
    )
    note += f"online {e.online or '0'}"
    if e.stores:
        listed = [
            f"{s.name}"
            + (f" ({s.zone})" if s.zone else "")
            + f" {s.qty}"
            + ("" if s.pickup is not False else ", no pickup")
            for s in e.stores
        ]
        note += f"; in stores: {_clip(listed, 30)}"
    else:
        note += "; in no store right now"
    note += "."
    if e.asked:
        if e.matched:
            here = next((s for s in e.stores if norm(s.name) == norm(e.matched)), None)
            listed = k.store(e.matched)
            if here is None and listed is not None:
                said = {norm(n) for n in listed.names}
                here = next((s for s in e.stores if norm(s.name) in said), None)
            if here is not None:
                note += f" The store they asked about, {e.matched}, has {here.qty}."
            else:
                zone = listed.zone if listed is not None else ""
                near = [s.name for s in e.stores if zone and s.zone == zone]
                note += f" The store they asked about, {e.matched}, has none right now."
                if near:
                    note += f" Others in {zone} that have it: {', '.join(near[:4])}."
        else:
            note += f" No store matched “{e.asked}”: ask which store they mean."
    return note + " Offer to show the store ({store: Name}) when it helps.]"


def _store_note(e: StoreShown) -> str:
    where = ", ".join(x for x in (e.address, e.city, e.region) if x)
    note = f"[The store {e.name} is on screen, on /tiendas" + (f": {where}" if where else "") + "."
    note += f" Hours: {e.hours}." if e.hours else " Its card shows no hours."
    return note + "]"


def _compare_note(e: CompareShown) -> str:
    names = [f"{i.name or i.path} ({i.path})" for i in e.items]
    return f"[The store's comparator bar holds: {'; '.join(names) or 'nothing'}.]"


_COMPARED_ROWS = 40
_SAME_ROWS = 25


def _comparison_note(e: ComparisonShown, lang: Lang) -> str:
    """The comparison page for the model: the products left to right with
    their prices, the rows that differ first with every value, then the rows
    that are the same."""
    items = [
        f"{n}. {i.name or i.path} ({i.path})"
        + (f", {i.brand}" if i.brand else "")
        + (f": Transferencia {_money(i.price, lang)}" if i.price is not None else "")
        + (
            f", otros medios {_money(i.card_price, lang)}"
            if i.card_price is not None and i.card_price != i.price
            else ""
        )
        for n, i in enumerate(e.items, 1)
    ]
    note = (
        f"[The comparison page is in front ({e.category or 'one category'}), left to right: "
        + "; ".join(items)
        + "."
    )

    def values(r: ComparisonRow) -> str:
        return " | ".join(v or "(none)" for v in r.values)

    differs = set(e.differs)
    differ = [r for r in e.rows if r.label in differs]
    partly = [r for r in e.rows if r.label not in differs and not all(r.values)]
    same = [r for r in e.rows if r.label not in differs and all(r.values)]
    if differ:
        note += (
            " Rows that differ (cue one with {compare: Label}): "
            + _clip([f"{r.label}: {values(r)}" for r in differ], _COMPARED_ROWS)
            + "."
        )
    if partly:
        note += (
            " Rows the store fills for only some of them (say plainly that one has no value): "
            + _clip([f"{r.label}: {values(r)}" for r in partly], _COMPARED_ROWS)
            + "."
        )
    if same:
        note += (
            " The same in all: "
            + _clip([f"{r.label}: {r.values[0] if r.values else ''}" for r in same], _SAME_ROWS)
            + "."
        )
    note += (
        " Destacar diferencias is on."
        if e.highlighted
        else " {compare: diferencias} turns on Destacar diferencias."
    )
    return (
        note + " Walk them through the rows that matter for their use, one cue per sentence, then "
        "recommend one.]"
    )


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
        note += f" Total Transferencia / Débito {_money(e.subtotal, lang)}."
    note += " Delivery is priced only in the checkout; store pickup is free."
    return note + _CHECKOUT_IS_THEIRS + "]"


#: What the cart's lines end with: how far he may go, and what is theirs.
_CHECKOUT_IS_THEIRS = (
    " update_cart_item changes how many of a line they have, or takes it out; apply_coupon "
    "applies a code. When they want to buy, start_checkout takes them to Tipo de entrega as a "
    "guest; the delivery choice, the RUT, the address and the payment are theirs."
)


def _checkout_note(e: CheckoutState) -> str:
    match e.step:
        case "login":
            note = (
                "[The checkout's first step, Inicio de sesión. Logging in is theirs; as a guest "
                "the page goes on with 'Continuar como invitado'."
            )
        case "delivery":
            offered = ", ".join(e.options) or "Retiro en tienda, Despacho a domicilio"
            note = f"[The checkout's Tipo de entrega step: {offered} — theirs to choose."
            if e.chosen:
                note += f" They chose {e.chosen}."
            note += " Store pickup is free; delivery is priced once they type their address."
        case "payment":
            note = "[The checkout's payment step: entirely theirs. Never press anything there."
        case _:
            note = "[A checkout page is in front."
    return note + " The RUT, any password, the address and the payment are theirs to type.]"


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


class PcFactoryBrain(OpenAIBrain):
    """One per session. Javier: PC Factory's knowledge, a mirror of the
    visitor's tabs and of every product, price and stock their screen and his
    reads have shown, in Spanish or English."""

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
        #: The categories' names, as words: never a sign of the language a
        #: line of his is in.
        self._category_words = name_words(c.name for c in self.kb.unique_categories())
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
        #: cart, the checkout step, and what his last catalogue read found.
        self.product: ProductShown | None = None
        self.listing: ListingShown | None = None
        self.cart: CartState | None = None
        self.checkout: CheckoutState | None = None
        self.found: ProductsFound | None = None
        self.compared: CompareShown | None = None
        #: The comparison page in front, as it last reported its table.
        self.comparison: ComparisonShown | None = None
        #: The facets the moves of the visitor's turn asked for, for the
        #: landing line; and the listing move whose line waits to be said.
        self._turn_facets: list[str] = []
        self._landing: tuple[Landing, str, float] | None = None
        self._checkout_asked = False
        #: Every price and stock read this call, by /producto/<id>; and every
        #: product's specifications as its page showed them.
        self.prices: dict[str, Live] = {}
        self.specs: dict[str, dict[str, str]] = {}
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
        #: Whether this reply sent a confirmed move: the cart page is never
        #: cued beside it.
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
            mirror=Mirror(SPEC),
        )
        #: What each cue sent said, as he wrote it, by its call_ref: for the
        #: line about its result (and a late one after an ``unknown``).
        self._cues: dict[str, str] = {}
        #: The move the page is slow on and his one line for it, said in the
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
        raw_path = str(init.get("path") or "/")
        self._path = _listing_base(raw_path) if search_query(raw_path) else canonical_path(raw_path)
        chosen = init.get("lang")
        self._chosen = chosen in LANGUAGE_NAMES
        self.spoken = "en" if chosen == "en" else OPENING
        await session.configure(
            Config(
                stt=SttConfig(language=self.spoken, patience=PCFACTORY_PATIENCE),
                tts=TtsConfig(voice=VOICE, language=self.spoken),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
            )
        )
        logger.info(
            "pcfactory: session start on {} in {}{}",
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
        reversible move the page is slow on gets his one holding line."""

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
        written line for it, in the next quiet spell, which is made short now."""
        if self._holding_floor():
            return
        for run in self.stage.holding():
            line = holding_line(run.move.id, self.spoken)
            logger.info(
                "pcfactory: {} {} still running at {:.1f} s ({}); holding line {!r}",
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
        the screen read in."""
        self._last_heard = msg.text
        heard = None if self._chosen else heard_language(msg.text, self.spoken, self._language_of)
        if heard is not None and heard != self.spoken:
            await session.configure(self._speaking(heard))
            logger.info("pcfactory: language -> {} (heard)", heard)
        if holds_spanish(msg.text, self.spoken, self._language_of):
            logger.info("pcfactory: held in Spanish: {!r}", msg.text)
            self._note(HELD_NOTE)
        if (what := private_kind(msg.text)) is not None:
            logger.info("pcfactory: the visitor said {}; never repeated", what)
            self._note(_PRIVATE_NOTE.format(what=what))
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
        self._turn_facets = []
        self._landing = None
        self._backstop = (
            None
            if asks_call_language(msg.text) or self._in_flow()
            else asked_page(msg.text, self.kb) or self._backstop
        )
        if self._backstop in _MOVE_PAGES and self._asked_cart_move():
            self._backstop = None
        self._restore_idle()
        self._read_in_screen()
        async for event in super().on_user_message(session, msg):
            yield event

    def _in_flow(self) -> bool:
        """Whether they are in the middle of buying: on a product, the cart or
        the checkout, where a question is answered in place."""
        return any(self._path.startswith(p) for p in _IN_FLOW)

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
        twice, then silence. Tools are off: only his cues move the page."""
        self._restore_idle()
        self._backstop = None
        self._expire()
        # What landed on screen, the latest line of it (rebuilt from the
        # listing as it stands now), then any confirmed move's.
        landing = self._fresh_lines(self.stage.take_lines())[-1:]
        done = " ".join([*landing, *self._done])
        self._done = []
        hold = self._take_hold()
        if hold is not None and not done and not self._outcomes and self._talk is None:
            # The page is still working on a move: said so, written, never
            # asked of the model, and no nudge counted.
            respell = for_the_voice if self.spoken == "es" else names_for_the_voice
            return say_line(self, respell(hold))
        if landing and not self._outcomes and self._talk is None:
            # Said first, written; the model may add one sentence.
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
                "Speak into the quiet, briefly, as the advisor beside them would: one useful "
                "thing about what is on their screen, with a cue, or one question that helps you "
                "help them. Never ask whether they are still there, and never repeat your last line."
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
        said before the model is asked (a move that is done); the model may
        then add to it, or say nothing."""
        if (line := self._confirm) is not None:
            self._confirm = None
            async for event in say_line(self, line):
                yield event
        if first is not None:
            logger.info("pcfactory: done line {!r}", first)
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
                logger.warning("pcfactory: the model returned nothing; asking once more")
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
                text, sure=False, names=self._names_on_screen(), vocabulary=self._category_words
            )
            if written == "en" and not may_write_english(
                self._last_heard, self.spoken, self._language_of
            ):
                written = None
            if written is not None and written != self.spoken:
                await session.configure(self._speaking(written))
                logger.info("pcfactory: language -> {} (written)", written)
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
            names += [self.product.name, short_name(self.product.name), *self.product.specs]
        if self.listing is not None:
            names += [self.listing.title, *(i.name for i in self.listing.items)]
        if self.found is not None:
            names += [i.name for i in self.found.items]
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
        # The cart is reached by its moves, whose tool call comes after these
        # words: a page cue for it here would race an add still under way.
        if path in _MOVE_PAGES and (self._confirmed_sent or self._asked_cart_move()):
            logger.info("pcfactory: no backstop to {}: a cart move is asked", path)
            return chunk
        logger.info("pcfactory: the reply has no cue; showing {} first", path)
        return f"{{page: {path}}}{chunk}"

    def _asked_cart_move(self) -> bool:
        """Whether the visitor's last two fragments ask for a move on the cart."""
        return asks_cart_move(" ".join(self._heard[-2:]))

    def _known_path(self, value: str) -> str | None:
        """The store path a page cue names, as the store links it, or ``None``.
        A product only by an id read this call; a search by its words."""
        raw = value.strip()
        if (q := search_query(raw)) is not None:
            return search_path(q) if q else None
        path = canonical_path(raw)
        if _NEVER.match(path):
            return None
        if path in _FIXED_PAGES:
            return path
        if (page := self.kb.page(path)) is not None:
            return page.path
        if self.kb.category(path) is not None:
            return path
        if product_path(path) is not None:
            return path if self._seen(path) else None
        return None

    def _seen(self, path: str) -> bool:
        """Whether this product came up this call: read, listed, found, in the
        cart, compared or in front."""
        key = product_path(path)
        if key is None:
            return False
        if key in self.prices or key in self.specs:
            return True
        if self.product is not None and product_path(self.product.path) == key:
            return True
        if product_path(self._path) == key:
            return True
        rows: list[str] = []
        if self.listing is not None:
            rows += [i.path for i in self.listing.items]
        if self.found is not None:
            rows += [i.path for i in self.found.items]
        if self.cart is not None:
            rows += [i.path for i in self.cart.items]
        if self.compared is not None:
            rows += [i.path for i in self.compared.items]
        return any(product_path(r) == key for r in rows)

    def _auto_cues(
        self, sentence: str, index: int, placed: tuple[tuple[str, tuple[str, ...]], ...]
    ) -> list[tuple[str, list[str]]]:
        """The moves a sentence of his needs and did not bring: the page its
        first sentence is about, and the section on the page it describes."""
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
            and not self._in_flow()
            and "page" not in verbs
            and not verbs & {"show", "faq", "filter", "sort", "tab", "store"}
            and self._shown is None
        ):
            asked = asked_page(sentence, self.kb)
            if (
                asked is not None
                and asked not in _MOVE_PAGES
                and asked != self._path
                and self._known_path(asked) is not None
                and self._section_for(sentence, self._path) is None
            ):
                logger.info("pcfactory: he talks about {} with no cue; opening it", asked)
                out.append(("page", [asked]))
                path = asked
        self._cue_path = path
        # A sentence that filters, sorts or points is about what it points at.
        if verbs & {"show", "faq", "filter", "sort", "tab", "store"}:
            return out
        shown = self._section_for(sentence, path)
        if shown is not None and shown != self._shown:
            out.append(("show", [shown]))
        return out

    def _section_for(self, sentence: str, path: str | None) -> str | None:
        """The heading on ``path`` that ``sentence`` is about."""
        if path is None or product_path(path) is not None:
            return None
        page = self.kb.page(path)
        live = self.page is not None and canonical_path(self.page.path) == path
        if page is None:
            if not live or self.page is None:
                return None
            return best_section(sentence, [(h, "") for h in self.page.headings])
        return best_section(sentence, [(s.heading, s.text) for s in page.sections])

    def _resolve(self, move: Move, args: list[str]) -> list[str] | None:
        """A cue's arguments checked against the site, as the page will take
        them; ``None`` drops it. A move this reply already sent loads the page,
        so a cue after it would race the load. A filter or sort the listing
        cannot take is said to him, so he does not say it happened."""
        self._refusal = None
        if self._moved:
            logger.info(
                "pcfactory: cue {} {} dropped: a move this reply loads the page", move.id, args
            )
            return None
        want = args[0] if args else ""
        match move.id:
            case "page.open":
                return self._resolve_page(want)
            case "page.faq":
                return self._resolve_faq(want)
            case "page.show":
                return self._resolve_show(want)
            case "product.tab":
                return self._resolve_tab(want)
            case "stores.show":
                return self._resolve_store(want)
            case "commerce.filter":
                return self._resolve_filter(want, args[1] if len(args) > 1 else "")
            case "commerce.sort":
                return self._resolve_sort(want)
            case "compare.show":
                return self._resolve_compare(want)
            case "menu.open":
                return self._resolve_menu(want)
            case _:
                return None

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
        """A heading of the page the cue is on, or a specification's label on
        the product in front, in the page's spelling; else as he wrote it."""
        target = self.kb.page(self._cue_path) if self._cue_path is not None else None
        elsewhere = self._moved_to()
        headings: tuple[str, ...] = (
            target.headings
            if elsewhere and target
            else self._headings() or (target.headings if target else ())
        )
        labels: tuple[str, ...] = ()
        if elsewhere is None and self.product is not None and self._on_product():
            labels = tuple(self.product.specs)
        shown = (_match(asked, labels) or _match(asked, headings) or asked)[:80]
        self._shown = shown
        return [shown, elsewhere] if elsewhere else [shown]

    def _on_product(self) -> bool:
        """Whether the product page in front is the one the cues are about."""
        return product_path(self._cue_path or self._path) is not None

    def _resolve_tab(self, asked: str) -> list[str] | None:
        tab = _TABS.get(norm(asked))
        if tab is None or not self._on_product():
            logger.info(
                "pcfactory: tab cue {!r} dropped: no product in front, or no such tab", asked
            )
            return None
        return [tab]

    def _resolve_store(self, asked: str) -> list[str] | None:
        store = self.kb.store(asked)
        if store is None:
            if self.kb.stores:
                logger.info("pcfactory: store cue {!r} dropped: no such store", asked)
                return None
            return [asked.strip()[:60]]
        return [store.name]

    def _listing_for_cue(self) -> tuple[str, Category | None] | None:
        """The listing a filter or sort cue applies to: the one a page cue of
        this reply opens, else the one in front; ``None`` when that is no
        listing. Named by its category, never by the address with its filters
        on: a second filter cue of the same reply must not load the address the
        reply was written on and undo the first."""
        path = self._cue_path or self._path
        if search_query(path) is not None:
            here = self.listing.path if self.listing is not None else path
            return _listing_base(here), None
        cat = self.kb.category_of(path)
        if cat is not None and path.startswith("/categoria/"):
            return path, cat
        if self.listing is not None and _listing_base(self.listing.path) == path:
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
            logger.info("pcfactory: cue {} {} dropped ({})", raw.verb, list(raw.args), why)
            return
        cue = f"{{{raw.verb}: {' | '.join(raw.args)}}}"
        logger.info("pcfactory: cue {} refused: {}", cue, refusal)
        self._note(f"[Not done on the page ({cue}): {refusal}. It was not applied.]")
        self._answered(f"{cue} not done: {refusal}")

    def _facets_for(self, path: str, cat: Category | None) -> list[tuple[str, tuple[str, ...]]]:
        """The facets of the listing at ``path``: as the listing in front
        reports them when it is that one (the live page wins), else as the
        category list has them."""
        if self.listing is not None and _listing_base(self.listing.path) == path:
            live = [(f.facet, tuple(f.options)) for f in self.listing.facets]
            if live:
                return live
        if cat is not None:
            return [(f.name, f.options) for f in cat.facets]
        return []

    def _resolve_filter(self, facet: str, value: str) -> list[str] | None:
        listing = self._listing_for_cue()
        if listing is None:
            self._cue_refused(
                f"the page it applies to ({self._cue_path or self._path}) is not a listing; "
                "open the listing with a page cue first",
            )
            return None
        path, cat = listing
        labels = self._facet_options(path, cat, facet, value)
        if isinstance(labels, str):
            self._cue_refused(labels)
            return None
        name, options = labels
        self._turn_facets.append(name)
        # Several options of one facet ride one cue, ", " between them: the
        # page adds each to what is already on.
        return [name, ", ".join(options)[:160], path]

    def _facet_options(
        self, path: str, cat: Category | None, facet: str, value: str | list[str]
    ) -> tuple[str, list[str]] | str:
        """The facet as the listing writes it and each option asked for, as it
        writes them; or why not, naming what the listing has. Several options
        of one facet keep only those the visitor named in their last words
        (and those already on): "at least sixteen" is 16GB, never 16, 24, 32,
        48 and 64GB (dev call 8b363867)."""
        facets = self._facets_for(path, cat)
        want = facet_key(facet)
        hit = next((f for f in facets if facet_key(f[0]) == want), None)
        if hit is None:
            hit = next(
                (
                    f
                    for f in facets
                    if len(want) >= 3
                    and (facet_key(f[0]).startswith(want) or want.startswith(facet_key(f[0])))
                ),
                None,
            )
        if hit is None and facets:
            has = ", ".join(f[0] for f in facets)
            return f"this listing has no facet '{facet}' (it has: {has})"
        name, options = hit if hit is not None else (facet.strip(), ())
        parts = _said_parts(value)
        if not parts:
            return "say which option, as the listing writes it"
        if facet_key(name) == "rango de precios":
            return "a price range goes in filter_listing's min_price and max_price"
        out: list[str] = []
        unknown: list[str] = []
        for part in parts:
            got = _match(part, options) if options else part
            if got is None and len(options) >= 25:
                # The list is cut at 25: an option past it may still be there.
                got = part
            if got is None:
                unknown.append(part)
            elif got not in out:
                out.append(got)
        if unknown:
            listed = ", ".join(options) or "none"
            return (
                f"{name} has no {' or '.join(repr(u) for u in unknown)} here (it lists: {listed})"
            )
        return name, self._named_only(path, name, out)

    def _named_only(self, path: str, facet: str, options: list[str]) -> list[str]:
        """Of several options of one facet, those the visitor named in their
        last words, and those already on; the first alone when they named
        none of them."""
        if len(options) < 2 or not self._heard:
            return options
        said = " ".join(self._heard)
        on: set[str] = set()
        if self.listing is not None and _listing_base(self.listing.path) == path:
            on = {_option_key(o) for o in _on_of(self.listing, facet)}
        new = [o for o in options if _option_key(o) not in on]
        named = [o for o in new if named_in(o, said)]
        if new and not named:
            named = new[:1]
        kept = [o for o in options if _option_key(o) in on or o in named]
        if kept != options:
            logger.info(
                "pcfactory: {} options {} cut to {}: the visitor named only those ({!r})",
                facet,
                options,
                kept,
                said,
            )
        return kept or options[:1]

    def _resolve_compare(self, asked: str) -> list[str] | None:
        """A row of the comparison page in front, as the table writes it; or
        diferencias, or precio."""
        table = self.comparison
        if table is None or self._moved_to() is not None:
            self._cue_refused("no comparison page is in front; compare_products opens it")
            return None
        said = norm(asked)
        if said in (
            "diferencias",
            "diferencia",
            "differences",
            "difference",
            "destacar diferencias",
        ):
            return ["diferencias"]
        if said in ("precio", "precios", "price", "prices"):
            return ["precio"]
        labels = [r.label for r in table.rows]
        row = _match(asked, labels)
        if row is None:
            self._cue_refused(
                f"the comparison has no row '{asked}' (it has: {', '.join(labels[:40])})"
            )
            return None
        return [row]

    def _resolve_menu(self, asked: str) -> list[str]:
        """A top category of the Categorías menu, as the store names it."""
        if not asked.strip():
            return []
        tops = [c.name for c in self.kb.unique_categories() if c.level == 1]
        return [(_match(asked, tops) or asked.strip())[:60]]

    def _resolve_sort(self, order: str) -> list[str] | None:
        listing = self._listing_for_cue()
        if listing is None:
            self._cue_refused("the page it applies to is not a listing")
            return None
        sort = _SORTS.get(norm(order).replace("-", "_"))
        if sort is None:
            self._cue_refused("this listing sorts by price_asc, price_desc or relevance only")
            return None
        return [sort, listing[0]]

    def _talk_now(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The one extra request a turn that said and moved nothing gets: tools
        declared, none callable."""
        return self.respond_with(session, tools=ToolChoice.NONE)

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Page→brain events, folded in silently: no floor taken, no turn."""
        event = PCFACTORY_EVENTS.parse(msg)
        if event is None:
            return
        logger.info("pcfactory: {} — {}", type(event).__voqal_event__, event)
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
            logger.warning("pcfactory: switch to {} refused: {}", event.language, rejected)
            self.spoken = was
            session.dispatch(LanguageChanged(language=was))
            return
        logger.info("pcfactory: language -> {} (toggle)", event.language)
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
            stt=SttConfig(language=language, patience=PCFACTORY_PATIENCE),
            tts=TtsConfig(voice=VOICE, language=language),
        )

    # ─── Page → brain ───────────────────────────────────────────────────

    def apply_event(self, event: PcFactoryEvent) -> str | None:
        """Patch the mirror; return the line the model should see."""
        match event:
            case PageChanged():
                self.page = event
                self._path = (
                    _listing_base(event.url or event.path)
                    if event.kind in ("search", "category")
                    else canonical_path(event.path)
                )
                self._page_unseen = True
                if event.kind != "product":
                    self.product = None
                if event.kind not in ("category", "search"):
                    self.listing = None
                if event.kind != "compare":
                    self.comparison = None
                return None
            case TabsChanged():
                self.tabs = event.tabs
                self._active = event.active
                self._tabs_unseen = True
                return None
            case LanguageRequested():
                return None
            case StageEvent():
                return self._state(event)
            case PricesRead():
                for i in event.items:
                    self._remember(
                        i.path,
                        i.name,
                        i.price,
                        i.card_price,
                        i.regular_price,
                        i.online_stock,
                        "api",
                    )
                return _prices_note(event, self.spoken)
            case ProductsFound():
                self.found = event
                for i in event.items:
                    self._remember(
                        i.path, i.name, i.price, i.card_price, i.regular_price, i.stock, "found"
                    )
                return _found_note(event, self.spoken)
            case StockRead():
                return _stock_note(event, self.kb)
            case StoreShown():
                return _store_note(event)
            case CompareShown():
                self.compared = event
                return _compare_note(event)
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

    def _state(self, event: StageEvent) -> str | None:
        """One named act on their screen, folded into the mirror: the typed
        view the brain's own rules read is rebuilt from the slice, and the
        model hears the act's one line."""
        folded = self.stage.handle(event)
        if folded is None:
            return None
        value = self._slice(folded.slice)
        if value is None:
            return folded.note
        match folded.slice:
            case "product":
                view = self._merged_product(product_view(value))
                path = product_path(view.path) or canonical_path(view.path)
                view = view.model_copy(update={"path": path})
                self.product = view
                self._path = path
                if view.specs:
                    self.specs[path] = dict(view.specs)
                self._remember(
                    path,
                    view.name,
                    view.price,
                    view.card_price,
                    view.regular_price,
                    view.online_stock,
                    view.source,
                )
                self.stage.landed(
                    _PRODUCT_MOVES, event=view, fits=lambda landing: lands(landing, view)
                )
                return f"{folded.note or 'A product page is in front'}. {_product_note(view, self.spoken)}"
            case "listing":
                listing = listing_view(value)
                self.listing = listing
                for i in listing.items:
                    self._remember(i.path, i.name, i.price, None, i.regular_price, "", "listing")
                self.stage.landed(
                    _LISTING_MOVES, event=listing, fits=lambda landing: lands(landing, listing)
                )
            case "cart":
                cart = cart_view(value)
                self.cart = cart
                for i in cart.items:
                    if i.path:
                        self._remember(i.path, i.name, i.price, None, None, "", "cart")
            case "checkout":
                state = checkout_view(value)
                self.checkout = state
                return _checkout_note(state)
            case "compare":
                table = comparison_view(value)
                self.comparison = table
                for i in table.items:
                    self._remember(
                        i.path, i.name, i.price, i.card_price, i.regular_price, "", "page"
                    )
                return f"{folded.note or 'The comparison page is in front'}. {_comparison_note(table, self.spoken)}"
            case _:
                pass
        return folded.note

    def _merged_product(self, view: ProductShown) -> ProductShown:
        """The product's new report over its last one: the store's live read
        sets the prices and stock, and keeps the page's specs when it has none."""
        before = self.product
        if before is None or product_path(before.path) != product_path(view.path):
            return view
        keep: dict[str, Any] = {}
        if not view.specs and before.specs:
            keep["specs"] = before.specs
        if view.source == "page" and before.source == "api":
            # The page's own copy never undoes the live read.
            keep |= {
                "price": before.price,
                "card_price": before.card_price,
                "regular_price": before.regular_price,
                "online_stock": before.online_stock,
                "source": "api",
            }
        for name in ("brand", "warranty", "promo_until"):
            if not getattr(view, name) and getattr(before, name):
                keep[name] = getattr(before, name)
        if view.stores_with_stock is None and before.stores_with_stock is not None:
            keep["stores_with_stock"] = before.stores_with_stock
        return view.model_copy(update=keep) if keep else view

    def _slice(self, slice_id: str) -> Mapping[str, Any] | None:
        mirror = self.stage.mirror
        return None if mirror is None else mirror.value(slice_id)

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
        move = self.stage.moves.get(r.move)
        if move is None:
            return None
        if self._hold is not None and self._hold[0] == r.call_ref:
            self._hold = None
        if r.late:
            return self._late(r, move)
        landed_ok = r.outcome in ("applied", "partial")
        why = self._why(r)
        cue_ref = r.call_ref in self._cues
        if move.verb is None or not cue_ref:
            name = _TOOL_OF.get(move.id, move.id)
            if r.outcome == "applied" and self.stage.shown(r.call_ref):
                # Its landing line said it already: the result only confirms.
                return f"[The page confirms {name}: {r.detail or 'done'}.]"
            if landed_ok:
                detail = r.detail or "done"
                if r.outcome == "partial":
                    detail = self._partial(r)
                    self._answered(f"{name} only partly done: {detail}")
                    return (
                        f"[The page did only part of {name}: {detail}. Say plainly what is done "
                        "and what is not; never that all of it worked.]"
                    )
                done = (
                    done_line(move.id, detail, self.spoken)
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
        written line ("Al final sí, …") said as soon as the floor is free."""
        landed_ok = r.outcome in ("applied", "partial")
        if r.call_ref in self._cues:
            cue = self._cues.pop(r.call_ref, f"{{{move.verb}: …}}")
            if landed_ok:
                return (
                    f"[Correction: your screen cue {cue} did land after all — "
                    f"{r.detail or 'done'}.]"
                )
            return None  # Already said as not confirmed; nothing to correct.
        name = _TOOL_OF.get(move.id, move.id)
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
                late_done_line(move.id, detail, self.spoken)
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

    def _remember(
        self,
        path: str,
        name: str,
        price: int | None,
        card_price: int | None,
        regular_price: int | None,
        stock: str,
        source: str,
    ) -> None:
        """One more thing their screen or a read said of a product's prices or
        stock. A live read is not overwritten by a page or card copy of it."""
        key = product_path(path)
        if key is None or (price is None and not stock):
            return
        before = self.prices.get(key)
        if (
            before is not None
            and _SOURCE_RANK.get(before.source, 0) > _SOURCE_RANK.get(source, 0)
            and before.price is not None
        ):
            return
        self.prices[key] = Live(
            key,
            name or (before.name if before else ""),
            price,
            card_price if card_price is not None else (before.card_price if before else None),
            regular_price,
            stock or (before.stock if before else ""),
            source,
            time.monotonic(),
        )

    def _read_in_screen(self) -> None:
        """The tabs and the page in front, once per change, ahead of what they say."""
        if self._tabs_unseen and len(self.tabs) > 1:
            listed = "; ".join(
                f"{t.tab_id}: {t.title or t.url}"
                + (" (in front)" if t.tab_id == self._active else "")
                for t in self.tabs
            )
            self._note(f"[The visitor's open PC Factory tabs — {listed}.]")
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
            "checkout": "the checkout",
            "stores": "the store list",
            "help": "a Centro de ayuda page",
            "compare": "the comparison page",
            "page": "a page of the store",
        }
        note = f"[The tab in front shows {kinds[p.kind]}: “{p.title or p.path}” ({self._path})."
        if p.headings:
            note += f" Its headings: {_clip(p.headings, _HEADINGS_IN_NOTE)}."
        if p.faqs:
            note += f" Its FAQs: {_clip(p.faqs, _FAQS_IN_NOTE)}."
        self._note(note + "]")

    def _note(self, text: str) -> None:
        self.append_note(text)

    def _still_running(self) -> str:
        """The moves he made that the page is still working on, a while in, for
        the line that keeps him from calling them failed. One whose effect is
        already on screen is not among them."""
        return "; ".join(
            f"{r.move.id} ({r.phase or 'sent'}, {r.seconds:.0f} s so far)"
            for r in self.stage.running()
            if (r.call_ref not in self._cues or r.move.cls is MoveClass.REVERSIBLE)
            and r.move.cls is not MoveClass.LOOK
            and r.seconds >= 2
            and not r.shown
        )

    def _landing_line(self, landing: Landing) -> str | None:
        """His written line the moment a move he made shows on screen: a
        listing he filtered, sorted or searched, a product he opened. Said in
        the next quiet spell, made short now; the model may add one sentence."""
        event = landing.event
        if (
            event is None
            and landing.result is not None
            and landing.move.id in _LISTING_MOVES
            and self.listing is not None
            and lands(landing, self.listing)
        ):
            # The move's own result, with the listing it left: an empty one
            # lands only here, once the page says the move is done.
            event = self.listing
        if isinstance(event, ListingShown):
            line = listing_line(
                event, self.spoken, landed_options(landing, event, self._turn_facets)
            )
            # When its move was sent, to tell the moves sent after it.
            self._landing = (landing, line, time.monotonic() - landing.seconds)
        elif isinstance(event, ProductShown):
            line = product_line(event, self.spoken)
        else:
            return None
        if self._hold is not None and self._hold[0] == landing.call_ref:
            self._hold = None
        logger.info(
            "pcfactory: {} {} on screen at {:.1f} s; landing line {!r}",
            landing.call_ref,
            landing.move.id,
            landing.seconds,
            line,
        )
        self._shorten_idle(_DONE_MS)
        return line

    def _fresh_lines(self, lines: list[str]) -> list[str]:
        """The landing lines to say now. A listing's is rebuilt from the
        listing as it stands, never from an older report (dev call 8b363867:
        "Here are 38 in Lenovo" said after the screen showed 21); and while
        another listing move of his is still to land, his line waits for
        that one's."""
        waiting, self._landing = self._landing, None
        if not lines or waiting is None or self.listing is None or lines[-1] != waiting[1]:
            return lines
        landing, _, sent_at = waiting
        now = time.monotonic()
        # Only a move sent after this one: an earlier one this listing
        # already answers lands with its own result.
        if any(
            r.move.id in _LISTING_MOVES and not r.shown and now - r.seconds > sent_at + 0.001
            for r in self.stage.running()
        ):
            logger.info("pcfactory: landing line held: another listing move is still running")
            return lines[:-1]
        event = landing.event if isinstance(landing.event, ListingShown) else None
        newer = event is not None and event is not self.listing
        if newer and not empty_listing(self.listing):
            line = listing_line(
                self.listing,
                self.spoken,
                landed_options(landing, self.listing, self._turn_facets),
            )
            logger.info("pcfactory: landing line rebuilt from the newest listing: {!r}", line)
            return [*lines[:-1], line]
        return lines

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

    def _move(self, move: str, args: BaseModel, line: str, *, loads: bool = True) -> str | None:
        """Send a tool's move to the page, or, while the last one is still
        under way, queue it to follow: ``None`` when sent, else what the tool
        says. ``loads``: the move may load another page, so a cue after it in
        this reply would race the load."""
        known = self.stage.moves.get(move)
        if known is not None and known.cls is MoveClass.CONFIRMED:
            self._confirmed_sent = True
        try:
            ref = self.stage.send(move, args.model_dump())
        except Refused as again:
            logger.info("pcfactory: {} asked for again while it runs; not sent twice", move)
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
        if loads:
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
                "next step (the checkout, a coupon, the store near them). For names and prices, "
                "read_screen first. Never say something is done that the page did not confirm."
            )
            self._outcomes = []
        elif self._outcomes:
            asks.append(
                "The page answered what you sent it: "
                + "; ".join(self._outcomes)
                + ". Talk it through now, in the language you speak, with cues as you point: "
                "what it found or did, from the lines in square brackets, and plainly what is not "
                "done, with what you can do instead. End with one next step. Never say "
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
            logger.warning("pcfactory: a move called with tools off; refused")
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

    def _unconsented(self, kind: str, doing: str) -> str | None:
        """The refusal for a confirmed move the visitor has not asked for or
        said yes to in their last words."""
        last = self._heard[-1] if self._heard else ""
        before = self._heard[-2] if len(self._heard) > 1 else ""
        if consents(kind, last, before):
            return None
        logger.info("pcfactory: {} without a yes; not sent", doing)
        return (
            f"Not done, nothing was sent: they have not asked to {doing}, nor said yes to it. "
            "Offer it as a short yes-or-no question, and call it after they say yes."
        )

    @staticmethod
    def _private_arg(*values: str | None) -> str | None:
        """The refusal for a tool call that would type something of theirs."""
        for v in values:
            if v and (what := private_kind(v)) is not None:
                return (
                    f"Not done, nothing was sent: that holds {what}, which is theirs to type on "
                    "the page. Never type, write or repeat it."
                )
        return None

    @staticmethod
    def _sent_note(doing: str) -> str:
        return (
            f"Sent to the page; it has not happened yet. Say only what you are doing "
            f"({doing}), never that it is done; the page's answer will follow."
        )

    def _price_of(self, path: str) -> Live | None:
        key = product_path(path)
        return self.prices.get(key) if key is not None else None

    def _product_known(self, path: str) -> str | None:
        """The product path as the page reports it, if their screen or a read
        of this call showed it; else ``None``."""
        key = product_path(path)
        if key is None or _NEVER.match(key):
            return None
        return key if self._seen(key) else None

    def _unknown_product(self, path: str) -> str:
        return (
            f"Not done: '{path}' is not a product their screen or your reads showed this call. "
            "Find it with find_products first, and use the /producto/<id> it gives."
        )

    def _in_front(self) -> str | None:
        """The product page in front, as /producto/<id>."""
        if self.product is not None:
            return product_path(self.product.path)
        return product_path(self._path)

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        """Read the store's knowledge and their screen; read the catalogue,
        prices and stock live; search, filter and open on their screen; show
        a store; compare; change the cart, apply a coupon and take them to
        Tipo de entrega (never further); move their tabs; switch language."""
        return [
            self.read_screen,
            self.read_topic,
            self.read_category,
            self.search_site,
            self.find_products,
            self.check_prices,
            self.check_stock,
            self.search_products,
            self.filter_listing,
            self.open_product,
            self.show_store,
            self.compare_products,
            self.remove_from_comparison,
            self.add_to_cart,
            self.update_cart_item,
            self.show_cart,
            self.apply_coupon,
            self.start_checkout,
            self.focus_tab,
            self.set_language,
        ]

    @needs_result_now
    async def read_screen(self, request: ReadRequest) -> str:
        """Read part of their screen as the page last reported it: the product
        page in front with its prices, stock and specifications, the listing,
        the cart, or the checkout step."""
        match request.slice:
            case "product":
                if self.product is not None:
                    return _product_note(self.product, self.spoken)
            case "listing":
                if self.listing is not None:
                    return _listing_note(self.listing, self.spoken)
            case "cart":
                if self.cart is not None:
                    return _cart_note(self.cart, self.spoken)
            case "checkout":
                if self.checkout is not None:
                    return _checkout_note(self.checkout)
            case "compare":
                if self.comparison is not None:
                    return _comparison_note(self.comparison, self.spoken)
        mirror = self.stage.mirror
        return mirror.read(request.slice) if mirror is not None else "Nothing to read."

    @needs_result_now
    async def read_topic(self, request: TopicRequest) -> str:
        """Read one of PC Factory's knowledge topics before answering from it."""
        topic = self.kb.topics.get(request.topic)
        if topic is None:
            return f"No topic '{request.topic}' is written yet: use search_site."
        return topic.text

    @needs_result_now
    async def read_category(self, request: CategoryRequest) -> str:
        """Read one category of the store: its path, the categories under it,
        and every filter its listing offers with all their options, written as
        the listing writes them. For a category or a filter the list below
        does not show."""
        said = request.name.strip()
        c = self.kb.category_by_id(int(said)) if said.isdigit() else self.kb.find_category(said)
        if c is None:
            return f"No category matches '{said}'. Use find_products with words instead."
        out = [f"{c.name} (id {c.id}) {c.path}"]
        under = [
            k
            for k in self.kb.unique_categories()
            if k.parent == c.path or any(k.parent == a for a in c.aliases)
        ]
        if under:
            out.append(
                "Under it: "
                + "; ".join(f"{k.name} (id {k.id}) {k.path}" for k in under[:_UNDER_SHOWN])
            )
        for f in c.facets:
            if f.options:
                out.append(f"{f.name}: {', '.join(f.options)}")
        return "\n".join(out)

    @needs_result_now
    async def search_site(self, request: SearchRequest) -> str:
        """Search www.pcfactory.cl's information pages, sections and FAQs (not
        the products: find_products is for those). Each result names the page
        path and the section heading to take them to."""
        hits = self.kb.search(request.query, _SEARCH_HITS)
        if not hits:
            return f"Nothing on www.pcfactory.cl's pages matches '{request.query}'. Say so plainly."
        out: list[str] = []
        for h in hits:
            if h.kind == "faq":
                out.append(f"[FAQ on {h.path}] {h.title}\n  {h.snippet}")
            else:
                where = f", heading: {h.section}" if h.section else ""
                out.append(f"[page] {h.title} — path: {h.path}{where}\n  {h.snippet}")
        return "\n".join(out)

    async def find_products(self, request: FindRequest) -> str:
        """Read the store's own catalogue in their browser, without moving their
        screen: up to eight products with their live prices and stock, and how
        many match, from their words, a category, a brand and their budget. It
        returns at once; the products come back to you in square brackets."""
        if (meta := self._meta_turn()) is not None:
            return meta
        words = " ".join((request.query or "").split())
        if (private := self._private_arg(words)) is not None:
            return private
        cat: Category | None = None
        if request.category:
            cat = self.kb.find_category(request.category)
            if cat is None:
                # A category the list does not have is words to search for.
                words = f"{words} {request.category}".strip()
        if cat is not None and cat.id is None:
            words = f"{words} {cat.name}".strip()
            cat = None
        lo, hi = request.min_price, request.max_price
        if lo is not None and hi is not None and lo > hi:
            lo, hi = hi, lo
        if not words and cat is None and not request.brand:
            return "Not read: give the words, a category or a brand to look for."
        args = FindProductsArgs(
            query=words or None,
            category_id=cat.id if cat is not None else None,
            brand=(request.brand or "").strip() or None,
            min_price=lo if lo and lo > 0 else None,
            max_price=hi if hi and hi > 0 else None,
            sort=request.sort,
        )
        self.stage.send("find_products", args.model_dump())
        landed(_LANDED["find"][self.spoken])
        what = ", ".join(
            x
            for x in (
                f"'{words}'" if words else "",
                f"in {cat.name}" if cat is not None else "",
                f"brand {args.brand}" if args.brand else "",
                f"up to {pesos(hi)}" if args.max_price and hi else "",
            )
            if x
        )
        return f"Reading the catalogue for {what}. " + self._sent_note("'Te busco opciones.'")

    async def check_prices(self, request: CheckPricesRequest) -> str:
        """Read the live prices (transferencia, otros medios, referencia) and the
        online stock of up to six products from the store itself, without moving
        their screen. It returns at once; the prices come back to you after."""
        if (meta := self._meta_turn()) is not None:
            return meta
        paths: list[str] = []
        unknown: list[str] = []
        for raw in request.paths:
            known = product_path(raw)
            if known is None:
                unknown.append(raw)
            elif known not in paths:
                paths.append(known)
        if not paths:
            return (
                f"Not read: {', '.join(unknown) or 'no paths'} — not product paths. "
                "Use '/producto/<id>' from find_products or their screen."
            )
        if len(paths) > _MOST_PRICED:
            return f"Not read: at most {_MOST_PRICED} at a time."
        self.stage.send("check_prices", CheckPricesArgs(paths=paths).model_dump())
        landed(_LANDED["prices"][self.spoken])
        out = f"Reading the live prices of {len(paths)} products. " + self._sent_note(
            "'Te reviso los precios.'"
        )
        if unknown:
            out += f" Not asked, not product paths: {', '.join(unknown)}."
        return out

    async def check_stock(self, request: CheckStockRequest) -> str:
        """Read a product's stock in every store and online, in their browser:
        on its page it scrolls to Disponibilidad and rings the store asked
        about. For "¿lo tienen en Maipú?". It returns at once; the stock comes
        back to you after."""
        if (meta := self._meta_turn()) is not None:
            return meta
        path = product_path(request.path) if request.path else self._in_front()
        if path is None:
            return (
                "Not read: which product? Give its '/producto/<id>', or open it first; "
                "no product page is in front."
            )
        store_said = (request.store or "").strip()
        store: Store | None = self.kb.store(store_said) if store_said else None
        args = CheckStockArgs(path=path, store=(store.name if store else store_said) or None)
        self.stage.send("check_stock", args.model_dump())
        landed(_LANDED["stock"][self.spoken])
        where = f" at {args.store}" if args.store else " in every store"
        out = f"Reading the stock of {path}{where}. " + self._sent_note("'Te reviso el stock.'")
        if store_said and store is None and self.kb.stores:
            out += f" No store on the list is named '{store_said}': the page matches it by city."
        return out

    async def search_products(self, request: SearchProductsRequest) -> str:
        """Type their words into the store's own search box, at a human pace,
        and show the results page on their screen; with open_index, then open
        that result. It returns at once; the results come back to you after."""
        if (meta := self._meta_turn()) is not None:
            return meta
        query = " ".join(request.query.split())
        if len(query) < 2:
            return "Not searched: the search box needs a word or two."
        if (private := self._private_arg(query)) is not None:
            return private
        index = request.open_index
        if index is not None and not 1 <= index <= 12:
            return "Not searched: open_index is 1 to 12, the results on the first page."
        # The model counts from 1, as the visitor does; the page from 0.
        action = SearchArgs(query=query, open_index=None if index is None else index - 1)
        queued = self._move("commerce.search", action, "search")
        if queued is not None:
            return queued
        return f"Typing '{query}' in the store's search box. " + self._sent_note(
            "'Lo busco en la tienda.'"
        )

    async def filter_listing(self, request: FilterRequest) -> str:
        """Open a category's listing (or the search results) with its facets
        already on, one at a time with the listing's own checkboxes, then its
        price range and order. Only facets and options that listing has. It
        returns at once; what the listing shows comes back to you after."""
        if (meta := self._meta_turn()) is not None:
            return meta
        raw = request.category.strip()
        cat: Category | None = None
        if raw.lower().startswith("search:"):
            path = search_path(raw.split(":", 1)[1])
        elif search_query(raw) is not None:
            path = _listing_base(raw)
        else:
            cat = self.kb.find_category(raw)
            if cat is None:
                listing_here = self.listing is not None and _listing_base(
                    self.listing.path
                ) == canonical_path(raw)
                if not listing_here:
                    tops = ", ".join(c.name for c in self.kb.unique_categories() if c.level == 1)
                    return (
                        f"Not done: no category '{raw}'. Use one of the category list "
                        f"(top level: {tops or 'not loaded'}), or find_products with words."
                    )
                path = canonical_path(raw)
            else:
                path = canonical_path(raw) if self.kb.category(raw) is cat else cat.path
        filters: list[str] = []
        refused: list[str] = []
        by_facet: dict[str, list[str]] = {}
        for item in request.filters or []:
            if ":" not in item:
                refused.append(f"'{item}' is not 'Facet: Option'")
                continue
            facet, option = item.split(":", 1)
            by_facet.setdefault(facet.strip(), []).append(option.strip())
        for facet, options in by_facet.items():
            got = self._facet_options(path, cat, facet, options)
            if isinstance(got, str):
                refused.append(got)
            else:
                filters += [f"{got[0]}: {o}" for o in got[1]]
                self._turn_facets.append(got[0])
        removed = [r for r in (request.remove or []) if ":" in r]
        refused += [f"'{r}' is not 'Facet: Option'" for r in request.remove or [] if ":" not in r]
        if request.page is not None and request.page < 1:
            refused.append("page is 1 or more")
        if refused:
            return "Not done: " + "; ".join(refused) + "."
        action = FilterListingArgs(
            category_path=path,
            filters=filters or None,
            min_price=request.min_price,
            max_price=request.max_price,
            sort=request.sort,
            remove=removed or None,
            clear=request.clear or None,
            page=request.page,
            size=request.size,
        )
        queued = self._move("filter_listing", action, "filter")
        if queued is not None:
            return queued
        bits = list(filters)
        if request.min_price:
            bits.append(f"from {pesos(request.min_price)}")
        if request.max_price:
            bits.append(f"up to {pesos(request.max_price)}")
        if request.sort:
            bits.append(f"sorted {request.sort}")
        bits += [f"without {r}" for r in removed]
        if request.clear:
            bits.append("every filter off")
        if request.size:
            bits.append(f"{request.size} per page")
        if request.page:
            bits.append(f"page {request.page}")
        applied = ", ".join(bits)
        return (
            f"Opening {cat.name if cat else path}" + (f" with {applied}" if applied else "") + ". "
        ) + self._sent_note("'Te filtro la lista.'")

    async def open_product(self, request: OpenProductRequest) -> str:
        """Open a product's page on their screen and, with tab, its
        specifications, warranty, stock by store or photos. It returns at once;
        what the page shows, with its prices and specs, comes back to you."""
        if (meta := self._meta_turn()) is not None:
            return meta
        path = self._product_known(request.path)
        if path is None:
            return self._unknown_product(request.path)
        here = self._in_front() == path
        if here and request.tab is None:
            return "Not moved: that product is already on their screen. Answer from read_screen's product."
        if here and request.tab is not None:
            # The product is in front: only its tab moves.
            queued = self._move("product.tab", TabArgs(tab=request.tab), "tab", loads=False)
            if queued is not None:
                return queued
            return f"Opening its {request.tab} tab. " + self._sent_note("'Te muestro esa pestaña.'")
        # The big photos, the pickup window and the price's ⓘ are cues on the
        # product in front: opened first, then cued.
        tab = (
            request.tab
            if request.tab in ("about", "specs", "warranty", "stock", "photos")
            else None
        )
        queued = self._move("open_product", OpenProductArgs(path=path, tab=tab), "product")
        if queued is not None:
            return queued
        live = self._price_of(path)
        then = (
            f" Once it is in front, {{tab: {request.tab}}} opens that."
            if request.tab and not tab
            else ""
        )
        return (
            f"Opening {live.name if live and live.name else path}. "
            + self._sent_note("'Te abro el producto.'")
            + then
        )

    async def show_store(self, request: ShowStoreRequest) -> str:
        """Show one store on /tiendas (opened first if needed): it scrolls to it,
        rings it and opens its map card with the address and hours. It returns
        at once; what the card says comes back to you."""
        if (meta := self._meta_turn()) is not None:
            return meta
        store = self.kb.store(request.name)
        if store is None and self.kb.stores:
            listed = ", ".join(s.name for s in self.kb.stores)
            return f"Not done: no store matches '{request.name}'. The stores: {listed}."
        name = store.name if store is not None else request.name.strip()
        loads = self._path != "/tiendas"
        queued = self._move("stores.show", StoresShowArgs(name=name), "store", loads=loads)
        if queued is not None:
            return queued
        where = f" ({store.address})" if store and store.address else ""
        if store is not None and store.hours:
            where += f"; hours: {store.hours}"
        return f"Showing the {name} store{where}. " + self._sent_note("'Te muestro la tienda.'")

    async def compare_products(self, request: CompareRequest) -> str:
        """Compare two or three products of one category with the store's own
        comparator, through its visible controls: each product's Comparar box
        ticked (its page opened first when it is not in front), the bar's
        Comparar pressed, and the comparison page opened with their specs side
        by side. It returns at once; the comparison comes back to you to walk
        them through, row by row, with {compare: Label} cues."""
        if (meta := self._meta_turn()) is not None:
            return meta
        paths = list(dict.fromkeys(p for raw in request.paths if (p := product_path(raw))))
        if not 2 <= len(paths) <= 3:
            return (
                "Not compared: the store's comparator takes two or three '/producto/<id>' "
                "paths of one category."
            )
        unknown = [p for p in paths if not self._seen(p)]
        if unknown:
            return self._unknown_product(", ".join(unknown))
        queued = self._move("compare.add", AddArgs(paths=paths, open=True), "compare")
        if queued is not None:
            return queued
        return (
            "Comparing on the page. "
            + self._side_by_side(paths)
            + " "
            + self._sent_note("'Te los comparo.'")
        )

    async def remove_from_comparison(self, request: UncompareRequest) -> str:
        """Take one product out of the comparison (its ✕), or empty the
        comparator ("Limpiar selección") with all. It returns at once; what
        the comparison shows then comes back to you."""
        if (meta := self._meta_turn()) is not None:
            return meta
        path = product_path(request.path) if request.path else None
        if path is None and not request.all:
            return "Not done: give the '/producto/<id>' to take out, or all."
        queued = self._move(
            "compare.remove",
            RemoveArgs(path=path, all=request.all or None),
            "uncompare",
            loads=False,
        )
        if queued is not None:
            return queued
        return ("Emptying the comparator. " if request.all else f"Taking {path} out. ") + (
            self._sent_note("'Lo saco de la comparación.'")
        )

    def _side_by_side(self, paths: list[str]) -> str:
        """Each product's prices, and the spec rows the read ones share."""
        out: list[str] = []
        labels: dict[str, int] = {}
        for p in paths:
            for label in self.specs.get(p, {}):
                labels[label] = labels.get(label, 0) + 1
        shared = [label for label, n in labels.items() if n >= 2][:_COMPARED_SPECS]
        for p in paths:
            live = self.prices.get(p)
            name = live.name if live and live.name else p
            price = live.line(self.spoken) if live else "price not read yet"
            specs = self.specs.get(p)
            if specs:
                rows = "; ".join(f"{k}: {specs[k]}" for k in shared if k in specs)
                rows = rows or _clip([f"{k}: {v}" for k, v in specs.items()], 8)
            else:
                rows = "specs not read yet (its page shows them)"
            out.append(f"- {name} ({p}): {price}. {rows}.")
        return "Side by side:\n" + "\n".join(out)

    async def add_to_cart(self, request: AddToCartRequest) -> str:
        """Add a product to their cart, with the quantity they said. Only when
        they asked for it in their last words, or said yes to your offer. It
        opens the product first if needed and returns at once; the cart's
        answer comes back to you. Never the checkout."""
        if (meta := self._meta_turn()) is not None:
            return meta
        if (no := self._unconsented("cart", "add it to the cart")) is not None:
            return no
        path = self._product_known(request.path)
        if path is None:
            return self._unknown_product(request.path)
        if not 1 <= request.qty <= 10:
            return "Not added: the quantity is one to ten."
        queued = self._move(
            "commerce.cart_add", CartAddArgs(path=path, qty=request.qty), "cart_add"
        )
        if queued is not None:
            return queued
        live = self._price_of(path)
        return (
            f"Adding {request.qty} of {live.name if live and live.name else path} to their cart. "
            + self._sent_note("'Te lo agrego al carro.'")
            + _CHECKOUT_IS_THEIRS
        )

    def _cart_line(self, said: str) -> CartItem | None:
        """The line of their cart ``said`` names: by its path, else its name."""
        if self.cart is None:
            return None
        want = product_path(said)
        for item in self.cart.items:
            if want is not None and item.path and product_path(item.path) == want:
                return item
        named = _match(said, [i.name for i in self.cart.items if i.name])
        return next((i for i in self.cart.items if i.name == named), None) if named else None

    async def update_cart_item(self, request: UpdateCartRequest) -> str:
        """Change how many of one line of their cart they have, or take it out
        with qty 0, on the cart page. Only when they asked for it, or said yes
        to your offer. It returns at once; the cart's answer comes back to
        you. Never the checkout."""
        if (meta := self._meta_turn()) is not None:
            return meta
        if not 0 <= request.qty <= 10:
            return "Not done: the quantity is 0 (take it out) to 10."
        if (no := self._unconsented("cart", "change their cart")) is not None:
            return no
        item = self._cart_line(request.line)
        if item is not None and item.path:
            path = product_path(item.path) or item.path
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
            "commerce.cart_update",
            CartUpdateArgs(path=path, qty=request.qty),
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
        """Open their cart (the /carro page), or close it. Never the checkout."""
        if (meta := self._meta_turn()) is not None:
            return meta
        queued = self._move(
            "commerce.cart_show",
            CartShowArgs(open=request.open),
            "cart_show" if request.open else "cart_close",
            loads=request.open,
        )
        if queued is not None:
            return queued
        return self._sent_note("'Te abro el carro.'" if request.open else "'Te cierro el carro.'")

    async def apply_coupon(self, request: CouponRequest) -> str:
        """Type a coupon code into the cart's Cupón de descuento and press
        Aplicar (the cart is opened first). Only when they asked for it, or
        said yes to your offer. It returns at once; the store's answer comes
        back to you."""
        if (meta := self._meta_turn()) is not None:
            return meta
        code = re.sub(r"\s+", "", request.code).upper()
        if not re.fullmatch(r"[A-Z0-9_-]{3,24}", code):
            return f"Not applied: '{request.code}' is not a coupon code. Ask them to spell it."
        if (private := self._private_arg(code)) is not None:
            return private
        if (no := self._unconsented("coupon", "apply the coupon")) is not None:
            return no
        if self.cart is not None and not self.cart.items and not self.cart.count:
            return "Not applied: their cart is empty. A coupon goes on a cart with products."
        queued = self._move("apply_coupon", ApplyCouponArgs(code=code), "coupon")
        if queued is not None:
            return queued
        return f"Applying {code}. " + self._sent_note("'Te aplico el cupón.'")

    async def start_checkout(self) -> str:
        """Take them from the cart to the checkout as a guest ("Continuar como
        invitado", never a login), stopping at Tipo de entrega, where they
        choose store pickup or delivery. Only when they want to buy, or said
        yes to your offer. It returns at once; the page's answer comes back to
        you. Never past Tipo de entrega."""
        if (meta := self._meta_turn()) is not None:
            return meta
        if (no := self._unconsented("checkout", "go to the checkout")) is not None:
            return no
        if self.cart is not None and not self.cart.items and not self.cart.count:
            return "Not done: their cart is empty. Offer to find something first."
        if (
            self.checkout is not None
            and self.checkout.step in ("delivery", "payment")
            and (self._path.startswith("/checkout"))
        ):
            return (
                "Already there: the checkout is in front. Tipo de entrega, the RUT, the address "
                "and the payment are theirs; answer their questions."
            )
        self._checkout_asked = True
        queued = self._move("start_checkout", StartCheckoutArgs(), "checkout")
        if queued is not None:
            return queued
        return (
            "Opening the checkout as a guest. "
            + self._sent_note("'Te llevo al tipo de entrega.'")
            + " It stops at Tipo de entrega: the choice, the RUT, the address and the payment "
            "are theirs."
        )

    async def focus_tab(self, request: TabRequest) -> str:
        """Bring another of the visitor's PC Factory tabs to the front."""
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
        logger.info("pcfactory: language -> {} (asked)", request.language)
        return "ok"


#: Where one said option ends and the next begins: a comma (not the one in
#: "15,6"), "&", or "y"/"o"/"and"/"or" between words.
_SAID_SPLIT = re.compile(r"\s*(?:(?<!\d),|,(?!\d)|&|\b(?:y|o|and|or)\b)\s*", re.IGNORECASE)


def _said_parts(said: str | list[str] | None) -> list[str]:
    """Each option in what was said, in order: "Lenovo y HP" → Lenovo, HP; a
    list's items each split the same way."""
    items = [said] if isinstance(said, str) else list(said or [])
    out: list[str] = []
    for item in items:
        out.extend(p for part in _SAID_SPLIT.split(item) if (p := part.strip(" .")))
    return out


__all__ = [
    "MOVES",
    "SPEC",
    "FocusTab",
    "LanguageChanged",
    "PcFactoryBrain",
    "ReadRequest",
]
