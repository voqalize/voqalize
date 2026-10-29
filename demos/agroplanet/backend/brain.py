"""AgroplanetBrain — Javier, a voice parts adviser on www.agroplanet.cl, Agroplanet's store.

The site is Agroplanet's, not ours. A browser extension injects the widget and a
small adapter into www.agroplanet.cl; the adapter turns each move below into an
act on the tab in front — the catalogue read, a listing filtered, a product
opened and its specifications shown, the category menu opened, an item added to
the cart, the quote form filled — and every tab reports what it shows as a typed
event (:mod:`.app_events`), whichever of the visitor and Javier moved it. The
store is one Angular app: a move to another page is a route change inside it,
not a load, and the call is held outside the page in any case.

**He never fetches the store, and he has no catalogue of his own.** The brains
run far from the store, and its prices move: products, prices and stock are
read in the visitor's browser by the extension (``find_products``,
``check_prices``, ``check_stock``, the product page's own live read) and reach
the brain as app events; the brain keeps them in a mirror and answers from it.

**A price is one he just read, and some are never said.** The store shows one
price per product, with the struck one and its percentage when it is on offer.
Some products show "Confirmar precio en tienda" instead: he never quotes a
price for those, and says the store confirms it. Stock is said as available,
few units or none online, never as a promise.

**Agroplanet sells by quote, and the quote is theirs to send.** There is no
checkout and no online payment: the cart's Cotizar opens the Formulario de
cotización, and Agroplanet validates the quote and confirms it in writing by
email. He never offers the Webpay link in the top bar.
He may add to the cart, change a line, take them to the form and fill its
name, phone, email, región, comuna, address and notes — each only after a
clear yes — and there he stops: the RUT and "Crear cotización" are the
visitor's. He never asks for, repeats or types a RUT, a password or a card, no
move he can send carries one, and he never logs in or registers.

**Every move is a Stage move.** A move on the page — a cue in his reply or a
tool's move — has a class that decides how it is sent and what he hears of
it, is ringed on the page before it acts, and is answered by exactly one
``stage_result`` (:mod:`voqalize.sdk.stage`).

**Never block on the UI.** A tool's move is sent and the tool returns at once;
the page's result comes back, and he talks it through in the next short quiet
spell, with tools off. One move at a time: a move asked for while another is
under way waits for that one to land.

**The screen follows his voice.** He writes his moves into the reply as cues
(``{tab: specs}``, ``{menu: Baterías}``, ``{filter: Marca | LUBRITEK}``), at
the start of the sentence they belong to; Stage takes them out of the speech,
the brain checks them against the site and what the page in front reports,
and the page makes each as the voice reaches its sentence.

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
    AGROPLANET_EVENTS,
    AgroplanetEvent,
    CartItem,
    CartState,
    LanguageRequested,
    ListingShown,
    PageChanged,
    PricesRead,
    ProductsFound,
    ProductShown,
    QuoteState,
    StockRead,
    StoreShown,
    TabInfo,
    TabsChanged,
    cart_view,
    listing_view,
    product_view,
    quote_view,
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
    product_sku,
    same_product,
    search_path,
    search_query,
)
from .stage_gen import (
    MOVES,
    SPEC,
    CartAddArgs,
    CartShowArgs,
    CartUpdateArgs,
    CheckPricesArgs,
    CheckStockArgs,
    FillQuoteArgs,
    FilterListingArgs,
    FindProductsArgs,
    OpenProductArgs,
    ReadRequest,
    SearchArgs,
    StartQuoteArgs,
    StoresShowArgs,
    TabArgs,
)

AGENT_NAME = "Javier"

#: GPT-6.1 Terra at low reasoning, for cost: OpenAI caches every prompt over
#: 1,024 tokens, so most of each turn's input is read from the cache.
MODEL = "gpt-6.1-terra"
REASONING = "low"
#: Agroplanet is in Chile: "hoy" and "mañana" are Santiago's.
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
#: A farmer describing his machine and the part he needs pauses mid-sentence.
AGROPLANET_PATIENCE = PATIENCE + 2
#: While the quote form is in front: a visitor saying a phone number or
#: spelling an email pauses between digits and letters, and each pause would
#: end the turn (sendpotion's details step, 2026-10-22).
_FORM_PATIENCE = 8

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
# both languages write ("tractor", "motor", "diesel", "hidráulico" folded) are
# in neither.
_SPANISH_WORDS = frozenset(
    # A word list reads as words, so it stays a split string.
    """que qué de del el los las la una unas unos por para con como cómo cuánto cuanto
    cuánta cuesta cuestan puedes puede podrías quiero quisiera necesito tengo tienes
    tiene tienen hay hola gracias sí está están estoy es eso esto esta este estos pero muy
    también hablar habla hablas hablemos español castellano usted ustedes mi mis tu tus
    su sus nosotros bueno claro dónde donde cuál cual cuándo cuando precio precios barato
    barata baratos muéstrame dime explícame funciona hace hacer hora horas busco buscando
    repuesto repuestos batería baterías rodamiento rodamientos aceite aceites neumático
    neumáticos cuchilla cuchillas tienda tiendas despacho retiro carro garantía oferta
    ofertas cotización cotizar máquina campo agrega agrégalo agregar ábreme muestra otra
    otro otras otros sirve
    """.split()  # noqa: SIM905
)
#: The store's nouns, which are also in its products' and categories' names:
#: "Baterías Heavy Duty" in an English reply is a category, not Spanish. Only
#: the visitor's words count them.
_STORE_NOUNS = frozenset(
    """repuesto repuestos batería baterías rodamiento rodamientos aceite aceites neumático
    neumáticos cuchilla cuchillas tienda tiendas despacho retiro carro garantía oferta
    ofertas cotización cotizar máquina campo precio precios
    """.split()  # noqa: SIM905
)
_SPANISH_SMALL = _SPANISH_WORDS - _STORE_NOUNS
_ENGLISH_WORDS = frozenset(
    """the is are was what how can could you your i i'm it it's this that these those do
    does show me my we our for with about and of to have has there here please want
    would like tell sure yes okay right of course let's battery batteries bearing bearings
    oil tire tires tyre tyres blade blades part parts engine mower farm cheap cheaper
    cheapest much price which best need good
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
# The store writes its own name as "Agroplanet", "AgroPlanet" and "AGROPLANET";
# the voice says one brand, "Agroplanet", in both languages. The farm's
# measures are written in codes the voice would spell letter by letter, so a
# code the model leaves in digits is handed to the voice as it is said in the
# field: "15W40" is "quince W cuarenta", "12V" "doce volts", "100Ah" "cien
# amperes hora", "50 HP" "cincuenta hache pe". The prompt asks for the words;
# this is the floor under it. The heard text keeps the spoken form: it is what
# the model was asked to write.

_VIDEO_TO_VOICE = re.compile(r"\b([Vv])[ií]deo(s?)\b")
_VIDEO_FROM_VOICE = re.compile(r"\b([Bb])idéo(s?)\b")
_BRAND_TO_VOICE: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bagro\s?planet\b(?!\.cl)", re.IGNORECASE), "Agroplanet"),
)
_VISCOSITY = re.compile(r"\b(\d{1,2})\s?W\s?-?\s?(\d{2})\b", re.IGNORECASE)
_VOLTS = re.compile(r"\b(\d{1,3})\s?V\b")
_AMP_HOURS = re.compile(r"\b(\d{1,4})\s?Ah\b")
_HORSEPOWER = re.compile(r"\b(\d{1,3})\s?HP\b")
#: Spanish voice only: (written, as the voice must read it). Empty until heard wrong.
_ES_RESPELL: tuple[tuple[re.Pattern[str], str], ...] = ()
_ES_UNSPELL: tuple[tuple[re.Pattern[str], str], ...] = ()


def names_for_the_voice(text: str) -> str:
    """``text`` with the store's name as the one brand the voice says."""
    for rx, said in _BRAND_TO_VOICE:
        text = rx.sub(said, text)
    return text


def measures_said(text: str, lang: Lang) -> str:
    """The farm's measure codes in ``text`` as they are said: "15W40",
    "12V", "100Ah", "50 HP" in words of ``lang``."""
    say = _es_number if lang == "es" else _en_number
    if lang == "es":
        text = _VISCOSITY.sub(lambda m: f"{say(int(m[1]))} W {say(int(m[2]))}", text)
        text = _VOLTS.sub(lambda m: f"{say(int(m[1]))} volts", text)
        text = _AMP_HOURS.sub(lambda m: f"{say(int(m[1]))} amperes hora", text)
        return _HORSEPOWER.sub(lambda m: f"{say(int(m[1]))} hache pe", text)
    text = _VISCOSITY.sub(lambda m: f"{say(int(m[1]))} W {say(int(m[2]))}", text)
    text = _VOLTS.sub(lambda m: f"{say(int(m[1]))} volt", text)
    text = _AMP_HOURS.sub(lambda m: f"{say(int(m[1]))} amp-hour", text)
    return _HORSEPOWER.sub(lambda m: f"{say(int(m[1]))} horsepower", text)


def english_for_the_voice(text: str) -> str:
    """English ``text`` as the English voice must read it."""
    return measures_said(names_for_the_voice(text), "en")


def for_the_voice(text: str) -> str:
    """Spanish ``text`` as the Spanish voice must read it."""
    text = _VIDEO_TO_VOICE.sub(
        lambda m: ("B" if m.group(1) == "V" else "b") + "idéo" + m.group(2),
        measures_said(names_for_the_voice(text), "es"),
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
    return for_the_voice(at) if lang == "es" else english_for_the_voice(at)


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
    """The whole percentage the struck price is above the price charged,
    when it is a real saving (5% or more); else ``None``."""
    if price is None or regular is None or regular <= price or regular <= 0:
        return None
    pct = math.floor((regular - price) * 100 / regular)
    return pct if pct >= 5 else None


# ─── Actions (brain → page) ────────────────────────────────────────────────────


class FocusTab(Action):
    """Bring one of the visitor's Agroplanet tabs to the front."""

    tab_id: str


class LanguageChanged(Action):
    """The call's language moved, by the toggle, by voice or by
    ``set_language``: the widget's toggle follows at once."""

    language: Literal["en", "es"]


# The moves themselves, their arguments included, are declared once in
# ``agroplanet/scene.json`` and generated into ``stage_gen`` for the brain and
# ``scene.gen.ts`` for the page.

SortOrder = Literal["price_asc", "price_desc", "relevance"]
ProductTab = Literal["details", "specs", "photos", "zoom", "price"]


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
        description="A few words to look for on www.agroplanet.cl's information pages and "
        "their panels, in Spanish, e.g. 'despacho regiones', 'garantía batería', 'cambios'."
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
        "'bateria 12v 100ah', 'aceite 15w40', 'rodamiento 6205', 'cuchilla rotofresa', "
        "'filtro aceite massey ferguson'.",
    )
    category: str | None = Field(
        default=None,
        description="A category from the category list: its name ('Baterías Heavy Duty', "
        "'Lubricantes'), its code (AG100) or its path.",
    )
    brand: str | None = Field(default=None, description="A brand, as said: 'Lubritek', 'NSK'.")
    sort: SortOrder | None = Field(
        default=None, description="'price_asc' cheapest first, 'price_desc', 'relevance'."
    )


class SearchProductsRequest(BaseModel):
    query: str = Field(
        description="What to type in the store's search box, in Spanish as the store names "
        "it: 'bateria', 'aceite hidraulico', 'rodamiento 6205'."
    )
    open_index: int | None = Field(
        default=None,
        description="Open the result at this place, 1 for the first; leave it out to only "
        "show the results.",
    )


class FilterRequest(BaseModel):
    """Only the filters the visitor asked for."""

    category: str = Field(
        description="The listing: a category's name, code or path from the category list "
        "('Lubricantes', 'AG100', '/categoria/...'), or 'search: words' for the search results."
    )
    filters: list[str] | None = Field(
        default=None,
        description="Each 'Facet: Option', as the category list or the listing writes them: "
        "['Marca: LUBRITEK', 'Viscosidad: 15W40', 'Precio: $10.000 - $49.999']; several "
        "options of one facet as separate entries.",
    )
    sort: SortOrder | None = Field(
        default=None, description="'price_asc' cheapest first, 'price_desc', 'relevance'."
    )
    remove: list[str] | None = Field(
        default=None,
        description="Filters to take off the listing, each 'Facet: Option' as it is on: "
        "['Marca: LUBRITEK']. Its checkbox is unticked, in place.",
    )
    clear: bool | None = Field(
        default=None, description="True to take every filter off ('Borrar Filtros'), in place."
    )
    page: int | None = Field(
        default=None, description="The listing's page to show, 1 the first (40 a page)."
    )


class CategoryRequest(BaseModel):
    name: str = Field(
        description="The category, by its name in either language, its code or its path: "
        "'baterías heavy duty', 'aceite hidráulico', 'repuestos para rotofresa', 'AG100'."
    )


class OpenProductRequest(BaseModel):
    path: str = Field(
        description="The product's path, '/producto/<slug>/<sku>', from find_products or "
        "their screen."
    )
    tab: ProductTab | None = Field(
        default=None,
        description="'specs' for its Especificaciones, 'details' for Detalle del Producto, "
        "'photos', 'zoom' for the big photo, or 'price' for its price and buttons.",
    )


class CheckPricesRequest(BaseModel):
    paths: list[str] = Field(description="Up to six '/producto/<slug>/<sku>' paths to price live.")


class CheckStockRequest(BaseModel):
    path: str | None = Field(
        default=None,
        description="The product's '/producto/<slug>/<sku>'; leave it out for the product in "
        "front.",
    )
    store: str | None = Field(
        default=None,
        description="The store they asked about, as said: a store's name or its city "
        "('Talca', 'Los Ángeles', 'Puerto Varas').",
    )


class ShowStoreRequest(BaseModel):
    name: str = Field(description="The store, as said: its name or city.")


class AddToCartRequest(BaseModel):
    path: str = Field(description="The product's path, '/producto/<slug>/<sku>'.")
    qty: int = Field(default=1, description="How many, as they said: 1 to 50.")


class UpdateCartRequest(BaseModel):
    line: str = Field(
        description="The cart line: its product path ('/producto/<slug>/<sku>') from "
        "read_screen's cart, or its name as the cart shows it."
    )
    qty: int = Field(
        description="How many of it they want in the cart now, 1 to 50; 0 takes it out."
    )


class ShowCartRequest(BaseModel):
    open: bool = Field(default=True, description="True to open the cart, false to close it.")


class FillQuoteRequest(BaseModel):
    """Only what the visitor said this call, as they said it. Never a RUT:
    there is no field for it, and the visitor types it."""

    name: str | None = Field(
        default=None, description="Nombre Completo / Razón Social: their name or company."
    )
    phone: str | None = Field(
        default=None, description="Their phone, the digits as they said them: '+56 9 1234 5678'."
    )
    email: str | None = Field(default=None, description="Their email, as they spelled it.")
    region: str | None = Field(
        default=None, description="Their región, as said: 'Maule', 'Metropolitana', 'Biobío'."
    )
    commune: str | None = Field(default=None, description="Their comuna: 'Talca', 'Linares'.")
    street: str | None = Field(default=None, description="Calle: the street's name.")
    number: str | None = Field(default=None, description="Número: the street number.")
    unit: str | None = Field(default=None, description="Dpto / casa / Oficina, if they said one.")
    notes: str | None = Field(
        default=None,
        description="Notas sobre tu cotización: what they want the seller to know, e.g. the "
        "machine the part is for, or store pickup.",
    )


# ─── The prompt ────────────────────────────────────────────────────────────────

_SITE_MAP_CHARS = 9000
_SECTIONS_PER_PAGE = 10
#: About 2,500 tokens: the tree and the facets that matter.
_CATEGORIES_CHARS = 10000
_FACETS_SHOWN = 6
#: The categories ``read_category`` lists under one, at most.
_UNDER_SHOWN = 30
_OPTIONS_SHOWN = 6
#: Facets every listing has, which say nothing about one category.
_COMMON_FACETS = frozenset({"precio", "marca", "categoria"})
#: How the site's titles end, longest first.
_TITLE_SUFFIXES = (
    " | Agroplanet.cl",
    " | Agroplanet",
    " - Agroplanet",
    " | Autoplanet.cl",
)


def _short_title(title: str) -> str:
    for suffix in _TITLE_SUFFIXES:
        title = title.removesuffix(suffix)
    return title.split(" | ")[0].strip()


def _site_map(k: Knowledge) -> str:
    lines: list[str] = []
    size = 0
    listed = (
        p
        for p in k.pages.values()
        if not p.unlisted
        and k.category(p.path) is None
        and product_sku(p.path) is None
        and not _NEVER.match(p.path)
        and p.path not in _MOVE_PAGES
    )
    for p in sorted(listed, key=lambda p: (p.path.count("/"), p.path)):
        heads = "; ".join(p.headings[:_SECTIONS_PER_PAGE])
        line = f"- {p.path} — {_short_title(p.title)}" + (f" (sections: {heads})" if heads else "")
        if p.faqs:
            line += f" (panels: {'; '.join(f.q for f in p.faqs[:_SECTIONS_PER_PAGE])})"
        size += len(line) + 1
        if size > _SITE_MAP_CHARS:
            break
        lines.append(line)
    return "\n".join(lines) or "(The site map is not loaded: find pages with search_site.)"


def _categories(k: Knowledge) -> str:
    """The tree, top level first: each node's name, code and path, and for
    the listings below the top, the facets that tell one apart (the ones every
    listing has are left out) with a few of their options."""
    lines: list[str] = []
    size = 0
    for c in sorted(
        k.unique_categories(), key=lambda c: (c.level or 9, c.hidden, -(c.products or 0), c.path)
    ):
        if c.level > 3:
            continue
        facets = [f for f in c.facets if facet_key(f.name) not in _COMMON_FACETS]
        opts = "; ".join(
            f"{f.name}: {', '.join(f.options[:_OPTIONS_SHOWN])}"
            + (
                f" +{max(f.total, len(f.options)) - _OPTIONS_SHOWN} more"
                if max(f.total, len(f.options)) > _OPTIONS_SHOWN
                else ""
            )
            for f in facets[:_FACETS_SHOWN]
            if f.options
        )
        line = f"- {c.name} ({c.code}) {c.path}" + (f" — {opts}" if opts and c.level >= 2 else "")
        size += len(line) + 1
        if size > _CATEGORIES_CHARS:
            lines.append("- … more: read_category with its name.")
            break
        lines.append(line)
    return "\n".join(lines) or "(The categories are not loaded: use find_products with words.)"


def _stores_list(k: Knowledge) -> str:
    by_region: dict[str, list[str]] = {}
    for s in k.stores:
        by_region.setdefault(s.region or s.zone or "Chile", []).append(
            s.name + (f" ({s.city})" if s.city and norm(s.city) not in norm(s.name) else "")
        )
    return (
        "\n".join(f"- {region}: {', '.join(names)}" for region, names in by_region.items())
        or "(The store list is not loaded: show_store finds them on /nuestras-tiendas.)"
    )


def _topics(k: Knowledge) -> str:
    return "\n".join(f"- {t.id}: {t.title}" for t in k.topics.values()) or "(none loaded)"


def _prompt(k: Knowledge, today: date | None = None) -> str:
    today = today or datetime.now(TIMEZONE).date()
    return f"""You are {AGENT_NAME}, the voice parts adviser on Agroplanet's online store, www.agroplanet.cl. Agroplanet, "Pasión por el campo desde 1956", sells agricultural parts and supplies across Chile: tractor parts, bearings, batteries, lubricants, agricultural tyres, agro-hardware, implements and their spare parts, with stores in the farming towns of the country. A farmer, a contractor or a workshop is on the store right now and has called you from the corner of the page. You can see and move their screen: you search the catalogue live, open products and their specifications, open the category menu, filter and sort a listing, read live prices and stock, show a store, add to their cart, take them to the quote form and fill it in with them. You are the best adviser at the counter: friendly, practical and knowledgeable about machines and the field; you ask about the machine and the job, and you recommend, you don't recite. Say the store's name as "Agroplanet".

# You narrate, and the screen follows your words
You talk the visitor through their screen like an adviser standing beside them, pointing as you talk. Fast: you talk and act at the same time.
- Put a screen cue at the start of the sentence it belongs to. The page moves when your voice reaches that sentence. The visitor never hears a cue.
  - {{page: /path}} opens a page of the store at its top: a page from the site pages list, a category's path, a brand's /marca/<brand>, a product's /producto/<slug>/<sku> from what you read this call, or the store list /nuestras-tiendas.
  - {{show: Heading}} scrolls to a heading, section or card on the page in front (or the one a page cue just opened) and rings it. On a product page it rings a row of the Especificaciones by its label ("Unidades por caja", "País").
  - {{tab: specs}} shows a part of the product in front: specs (Especificaciones), details (Detalle del Producto), photos (the gallery), zoom (the big photo, in the page's own zoom) or price (its price and the Cotizar and Agregar al carro buttons).
  - {{faq: Panel}} opens one panel of a policy page (Despacho, Cambios y devoluciones, Garantía) and rings its answer.
  - {{menu: Category}} opens "Todas las categorías" on that top category, so its subcategories show: {{menu: Baterías}}, {{menu: Repuestos De Tractor}}.
  - {{store: Name}} shows one store on /nuestras-tiendas.
  - {{filter: Facet | Option}} narrows the listing in front by one of its facets, the option exactly as the listing or the category list writes it: {{filter: Marca | LUBRITEK}}, {{filter: Viscosidad | 15W40}}, {{filter: Precio | $10.000 - $49.999}}. Two options of one facet go in one cue only when the visitor named both: "Lubritek o Shell" is {{filter: Marca | LUBRITEK, SHELL}}.
  - {{sort: price_asc}} sorts the listing in front: price_asc (cheapest first), price_desc or relevance.
- OPEN WITH A CUE, then one cue at the start of each sentence that talks about something on screen. Talk about what you ring, as you ring it:
  - On a product: "{{tab: price}} Esta batería está a ochenta mil pesos. {{tab: specs}} Mira las especificaciones. {{show: País}} Viene de Corea."
  - On the home page: "{{menu: Repuestos De Tractor}} Aquí están los repuestos de tractor. {{show: CATEGORÍAS}} Y aquí, las categorías principales."
  - On a listing: "{{filter: Marca | LUBRITEK}} Te dejo solo los Lubritek. {{filter: Viscosidad | 15W40}} En quince W cuarenta. {{sort: price_asc}} Y del más barato al más caro."
  - On a question: "{{page: /politica-despacho}} Te muestro cómo funciona el despacho."
- Use headings, labels and options exactly as the site pages list, the category list or the screen lines spell them. Cues are in Spanish, also inside an English reply: "{{tab: specs}} Here are the specs."
- Never make up a heading, a path or a SKU: a product is opened only by a path you read this call.
- One cue per sentence at most, before the sentence, never inside it.
- A filter or sort cue sits on a promise of what you are doing ("Te dejo solo los Lubritek."), never on a statement of the result: the grid changes after. What the listing then shows comes to you in square brackets: say it on your next turn. A filter that could not be applied is said to you, to say so.
- TICK ONLY WHAT THE VISITOR NAMED. "Al menos cien amperes", "100 o más", "minimum 100Ah" is {{filter: Amperaje | 100}}, one option, never every size above it: say that bigger ones exist and offer to add them. Never add an option, a brand or a range they did not say.
- A facet's options in a line may be cut short, and a listing has more than any line shows: NEVER SAY AN OPTION OR A FILTER IS MISSING unless a line from the page says it refused it. Write the cue with the option as they said it; the page answers. read_screen's listing lists every option of every facet, and read_category a category's.
- A reply that calls a move tool has no page cue: the move takes them there. The cart and the quote form are only ever reached by their moves, never by a cue.
- Keep them on Agroplanet's own pages: the help site, the Webpay form and WhatsApp open in a new tab and take them away. Say the WhatsApp number when they want a person; never open it. Never offer the Webpay link: payment is settled after the quote, with Agroplanet.

# A parts adviser, not a brochure
- Farmers ask by machine and job. Find out what you need to find the right part, one short question at a time, only what you do not know yet: the machine ("¿Qué tractor es, marca y modelo?", "¿De cuántos caballos?"), the measure ("¿Qué medida tiene el neumático?", "¿Tienes el código del rodamiento?"), or the use ("¿Es para el motor o para el hidráulico?"). If they already said, go straight to options.
- Then find_products with the words that matter and the category when you know it. When the products come back, name two or three that fit, each with its price and whether it is available, recommend one with the reason that matters for their machine or job, and open it with a page cue: "{{page: /producto/bateria_12v_100ah/1234567}} Te abro la de cien amperes hora, que es la que le sirve a tu tractor."
- What matters, by part: a battery, the voltage, the amperes hora and the cold-cranking amps (CCA) for the machine, and the terminal side; an oil, the use (motor, hidráulico, transmisión) and the viscosity the maker asks for; a tyre, the size written on its side and conventional or radial; a bearing, its code or its measures; a blade or a spare for an implement, the implement's make and model. Say why in plain words.
- Compatibility is the visitor's to confirm: say what the page or the specs say, and when the store does not state that a part fits their machine, say so and suggest checking the code, or asking a seller by WhatsApp or in store.
- Every spec and every price you say is one you read this call: from find_products, the product page's lines, check_prices or the cart. Never from memory, never invented, never from another product.
- End every turn with one short, useful next step as a yes-or-no question: "¿Te la abro?", "¿Te reviso si está disponible?", "¿Te la agrego al carro?", "¿Pedimos la cotización?". Never "anything else?".

# How you sound
You are heard, not read, so keep it light and quick.
- A turn is two to five short sentences. Every sentence under fifteen words. One idea per sentence, one number per sentence.
- THE FIRST SENTENCE IS A FEW WORDS. The visitor hears nothing until your first sentence has been voiced, so open every reply with a sentence of two to six words that ends in a full stop, with the answer in it. A cue may come before it.
- Your first word is the answer: no filler, no "great question", no repeating their question back.
- Spoken words only, apart from cues: no lists, no markdown, no symbols, never an exclamation mark.
- Write every number, price and measure as spoken words. Prices are Chilean pesos: "$80.000" is "ochenta mil pesos", in English "eighty thousand pesos"; the lines in square brackets give each price with how to say it. Measures the way the field says them: "15W40" is "quince W cuarenta", "12V" is "doce volts", "100Ah" is "cien amperes hora", "50 HP" is "cincuenta hache pe" or "cincuenta caballos", a tyre "dieciocho cuatro treinta" for 18.4-30. Never say a SKU, a path or a full product name with all its codes: "la batería de cien amperes", "el aceite Lubritek de diecinueve litros".
- Lines in square brackets come from their screen, not the visitor: the page in front, what changed on it, a move's answer. Never read them out; use them.
- read_screen reads what their screen shows now: the product page in front (price, stock, specifications), the listing (its products in order with prices, its filters), the cart, or the quote form. Call it before you say a price, a stock or what is in the cart when no line already gives it, with nothing written before it.
- Never list what is on screen: name two or three things, and point at the rest.
- Always answer. A reply with no words leaves the visitor in silence.

# Spanish or English
You speak Spanish as a native of Latin America, and English. The call starts in Spanish unless the visitor chose English.
- Answer in Spanish. Move to English only when the visitor says at least two full sentences in English in one turn, or asks for English; then answer in English from that reply on, and if the visitor goes back to Spanish, so do you. Speech recognition often hears a short Spanish reply or a Chilean name as English ("See" for "sí", "Tall car" for "Talca"): the visitor is still speaking Spanish, so answer in Spanish. Your voice follows the language you write.
- Except when they chose a language: a line in square brackets says so. Then answer in that language whatever they speak, until they ask you to switch.
- When they ask for the other language in words that are not already it ("¿Puedes hablar en inglés?", "Can we speak Spanish?"), answer in that language and call set_language in the same response.
- One language per reply: in a Spanish reply every sentence is Spanish, and masculine forms of yourself ("encantado de ayudarte").
- Your Spanish is neutral Latin American Spanish, warm and natural for a Chilean visitor from the countryside, never the Spanish of Spain and never heavy slang.
  - Address the visitor as "tú", as the store does, never "usted"; several people are "ustedes", never "vosotros", and never its verb forms ("queréis", "tenéis") or "os".
  - Chile's own store words are right here: the "carro", never "cesta"; "repuesto" for a spare part, never "recambio"; "cotización" and "cotizar"; "despacho" for delivery; "retiro en tienda"; "neumático", never "rueda" for the tyre; "camioneta" for a pickup; "computador", never "ordenador"; "celular", never "móvil".
  - Use Latin American words: "mostrar" ("te muestro"), not "enseñar"; "completar", not "rellenar"; "disculpa", not "perdona"; "está bien" or "perfecto", never "vale"; "tomar", never "coger"; "¿te sirve?", not "te viene bien". Write "video", never "vídeo".
  - For something just done, use the simple past: "Abrí el producto", "Lo agregué", not "He abierto".
- In English, say the store's Spanish names as they are written ("Cotizar", "despacho", "retiro en tienda") and explain them in a few words when they are not obvious.

# Every fact has a source
- Every fact comes from the knowledge below, a topic you read, a search result, or what their screen and your moves reported. If you cannot find it, say so, and offer a seller by WhatsApp or in store.
- Never promise stock, a delivery date, a delivery cost, a discount or that a part fits a machine when the site does not state it.

# Every response starts with words
Write your answer, with its cues, first; any tool call comes at the end of the same response.
- read_topic, read_category, search_site and read_screen come straight back to you within this same turn, but each one makes the visitor wait. Answer from what you know below whenever it covers the question. Read only for what is not here, and then call the read first, with nothing written before it.
- Every other tool is a move: find_products, check_prices, check_stock, search_products, filter_listing, open_product, show_store, add_to_cart, update_cart_item, show_cart, start_quote, fill_quote. The page does it a moment later and tells you in square brackets, and you talk it through then. In the reply that calls one, say only what you are doing ("Te busco opciones.", "Te reviso el stock en Talca.", "Te la agrego al carro."), never that it is done and never a result.
- One move at a time: when a tool says the page is still working on the last move, what you asked for follows by itself. Say so in a few words, and never call it again.
- While a move is still running (a line says so), never say it failed: say you are still on it. Never say the store, the site or the page is slow: it is the store's own site. If a line later says it was done after all, correct yourself in a few words.
- A question about the call itself — "can I speak English?", "can you hear me?", "who are you?" — gets an answer and nothing else: no move, no page.

# Finding products
- find_products reads the store's own catalogue in their browser: up to eight products with their live prices and stock, and how many match. It is how you answer "¿tienen…?", "¿qué me recomiendas?" and "¿cuál es más barato?". Search with the store's Spanish words ("bateria 12v 100ah", "aceite hidraulico", "rodamiento 6205", "cuchilla rotofresa"), a category from the list below when you know it, and a brand.
- search_products types their words into the store's own search box so the results page shows on their screen; with open_index it opens one of the results. Use it when they want to see the results themselves.
- filter_listing opens a category's listing with its facets already on, in one move. On the listing in front, filter with cues as you talk instead. filter_listing also takes filters off in place (remove, or clear for "Borrar Filtros") and turns the page (page, forty products a page): "saca la marca" is remove, "la página siguiente" is page.
- open_product opens a product, with a section when you name one; on the product in front, use a tab cue.

# Prices and stock
- Each product has one price, and when it is on offer, the struck price and its percentage: say the offer only when the lines say it is a real saving.
- Some products show "Confirmar precio en tienda" instead of a price. NEVER say a price for those, not even one you read elsewhere: say the store confirms the price, and that the quote is the way to get it.
- A price or stock you say is one a line from this call gives. Without one, say you will check it, and call check_prices; never a price from memory.
- Say stock in words, never as a promise and never as a count: "está disponible", "quedan pocas unidades", "no tiene stock online". "¿La tienen en la tienda de Talca?" is check_stock with the store: say what it found for that store, and offer to show the store ({{store: Name}}).
- The price may change with the store or the delivery chosen, as the product page says: never quote a delivery cost.

# The cart and the quote
- Agroplanet sells by quote: there is no online payment. The cart's "Cotizar" opens the "Formulario de cotización"; the visitor sends it with "Crear cotización", Agroplanet validates it (the stock and a formal price) and confirms it in writing to their email. There is no checkout, no payment on the site and no delivery cost before the quote. Explain this simply when they want to buy.
- add_to_cart, update_cart_item, start_quote and fill_quote change what is theirs: call one only when the visitor asked for exactly that in their last words, or said yes to your offer of it. Otherwise offer it as a yes-or-no question and wait for the yes.
- add_to_cart adds the product with the quantity they said (one unless they said more). update_cart_item changes how many of a line they have, 0 takes it out. show_cart opens their cart.
- start_quote takes them from the cart to the Formulario de cotización and stops there. Then offer to fill it in with them, one or two fields at a time: their name or company, phone, email, región, comuna, street and number, and notes for the seller (the machine the part is for is a useful note).
- fill_quote types what they said into the form. When you fill a phone, read it back digit by digit in the same reply ("Anoté nueve, cuatro, siete, nueve…"), and an email letter by letter, so they can check it; when they correct it, fill it again.
- THE RUT IS THEIRS, and so is "Crear cotización". Never ask for the RUT, never repeat it, never write it anywhere, even when they say it: say "El RUT lo completas tú en la página." in their language. When everything else is filled, tell them to type their RUT and press "Crear cotización" themselves. Never a password, never a card, never log in or register, never the payment.

# Tabs
- The visitor may have several store tabs open. Lines in brackets tell you which tabs are open and which is in front. "Go back to the other tab" is focus_tab with that tab's id.

# What you know
- Today is {today:%A, %d %B %Y}, in Santiago.
- Topics you can read with read_topic, when the knowledge below does not cover a question:
{_topics(k)}
- search_site finds an information page, section or panel by its words. Its results name the page and section, which you can then cue.

# AGROPLANET
{k.l1}

# Categories (name, code, path — and for the listings, the facets that tell them apart)
A few options of each facet are shown ("+N more" are not); read_category gives one category's full filters and the categories under it, and read_screen the listing in front's.
{_categories(k)}

# Stores
{_stores_list(k)}

# Site pages
{_site_map(k)}
"""


# ─── Greeting ──────────────────────────────────────────────────────────────────

_INTRO: dict[Lang, str] = {
    "es": f"Hola, soy {AGENT_NAME}, de Agroplanet.",
    "en": f"Hi, I'm {AGENT_NAME}, from Agroplanet.",
}
_GREETING: dict[Lang, str] = {
    "es": "Te ayudo a encontrar el repuesto, la batería o el aceite que necesitas. "
    "¿Para qué máquina es?",
    "en": "I can help you find the part, battery or oil you need. Which machine is it for?",
}
#: The opener's second sentence for the page the call starts on, by a word in
#: its path (folded); the first match wins, and anything else gets the plain
#: greeting.
_OPENERS: tuple[tuple[str, dict[Lang, str]], ...] = (
    (
        "/carro",
        {
            "es": "Te ayudo con tu carro: revisarlo o pedir tu cotización. ¿Qué necesitas?",
            "en": "I can help with your cart: go over it or ask for your quote. What do you need?",
        },
    ),
    (
        "/cotizacion",
        {
            "es": "Te ayudo a completar la cotización; el RUT lo pones tú. ¿Empezamos?",
            "en": "I can help you fill in the quote form; the RUT is yours to type. "
            "Shall we start?",
        },
    ),
    (
        "/producto/",
        {
            "es": "Te cuento de este producto o te reviso su precio y stock. ¿Qué quieres saber?",
            "en": "I can tell you about this product or check its price and stock. "
            "What would you like to know?",
        },
    ),
    (
        f"{SEARCH_PATH}/",
        {
            "es": "Te ayudo a elegir entre estos resultados. ¿Para qué máquina es?",
            "en": "I can help you choose among these results. Which machine is it for?",
        },
    ),
    (
        "/marca/",
        {
            "es": "Te ayudo con los productos de esta marca. ¿Qué estás buscando?",
            "en": "I can help with this brand's products. What are you looking for?",
        },
    ),
    (
        "bateria",
        {
            "es": "Te ayudo a elegir tu batería. ¿Para qué máquina es?",
            "en": "I can help you choose a battery. Which machine is it for?",
        },
    ),
    (
        "lubricant",
        {
            "es": "Te ayudo a elegir tu aceite. ¿Es para el motor o el hidráulico?",
            "en": "I can help you choose an oil. Is it for the engine or the hydraulics?",
        },
    ),
    (
        "neumatico",
        {
            "es": "Te ayudo a elegir tu neumático. ¿Qué medida necesitas?",
            "en": "I can help you choose a tyre. What size do you need?",
        },
    ),
    (
        "rodamiento",
        {
            "es": "Te ayudo a encontrar tu rodamiento. ¿Tienes el código o la medida?",
            "en": "I can help you find your bearing. Do you have its code or size?",
        },
    ),
    (
        "tractor",
        {
            "es": "Te ayudo a encontrar el repuesto. ¿Qué tractor tienes, marca y modelo?",
            "en": "I can help you find the part. Which tractor is it, make and model?",
        },
    ),
    (
        "implemento",
        {
            "es": "Te ayudo a elegir tu implemento o su repuesto. ¿Para qué trabajo es?",
            "en": "I can help you choose an implement or its part. What job is it for?",
        },
    ),
    (
        "/categoria/",
        {
            "es": "Te ayudo a elegir en esta categoría. ¿Para qué máquina o trabajo es?",
            "en": "I can help you choose in this category. Which machine or job is it for?",
        },
    ),
    (
        "/nuestras-tiendas",
        {
            "es": "Te ayudo a encontrar tu tienda más cercana. ¿En qué ciudad estás?",
            "en": "I can help you find your nearest store. Which town are you in?",
        },
    ),
    (
        "/politica-despacho",
        {
            "es": "Te ayudo con el despacho, la garantía o los cambios. ¿Qué necesitas saber?",
            "en": "I can help with delivery, warranty or returns. What do you need to know?",
        },
    ),
    (
        "devoluciones",
        {
            "es": "Te ayudo con el despacho, la garantía o los cambios. ¿Qué necesitas saber?",
            "en": "I can help with delivery, warranty or returns. What do you need to know?",
        },
    ),
)


def _is_product_path(path: str) -> bool:
    return product_sku(path) is not None


def greeting(path: str | None, lang: Lang = OPENING) -> str:
    """The written opener, in ``lang``, tailored to the page the call starts on."""
    here = fold(canonical_path(path or "/"))
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
    "section": {"en": "Here's that part.", "es": "Aquí tienes esa parte."},
    "find": {"en": "I'm looking for options.", "es": "Te busco opciones."},
    "search": {"en": "I'm searching the store for it.", "es": "Lo busco en la tienda."},
    "filter": {"en": "I'm filtering the list for you.", "es": "Te filtro la lista."},
    "product": {"en": "I'm opening the product.", "es": "Te abro el producto."},
    "prices": {"en": "I'm checking the prices.", "es": "Te reviso los precios."},
    "stock": {"en": "I'm checking the stock.", "es": "Te reviso el stock."},
    "store": {"en": "I'm showing you the store.", "es": "Te muestro la tienda."},
    "cart_add": {"en": "I'm adding it to your cart.", "es": "Lo agrego a tu carro."},
    "cart_show": {"en": "I'm opening your cart.", "es": "Te abro el carro."},
    "cart_update": {"en": "I'm changing that in your cart.", "es": "Te lo cambio en el carro."},
    "cart_remove": {"en": "I'm taking it out of your cart.", "es": "Lo saco de tu carro."},
    "cart_close": {"en": "I'm closing the cart.", "es": "Te cierro el carro."},
    "quote": {
        "en": "I'm taking you to the quote form.",
        "es": "Te llevo al formulario de cotización.",
    },
    "form": {"en": "I'm putting that in the form.", "es": "Lo anoto en el formulario."},
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
    "start_quote": {
        "en": "Here's the quote form. Shall I help you fill it in?",
        "es": "Listo, este es el formulario de cotización. ¿Te ayudo a completarlo?",
    },
    "fill_quote": {"en": "Done, it's in the form.", "es": "Listo, quedó en el formulario."},
}
#: The page's detail for an add: "added 1 x Aceite Lubritek …; …" (or a times sign).
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
    "commerce.search": {
        "en": ("Still searching, one moment.", "Almost there with the results."),
        "es": ("Sigo buscando, un momento.", "Ya casi tengo los resultados."),
    },
    "start_quote": {
        "en": ("Getting the quote form ready, one moment.", "Almost there with the form."),
        "es": ("Estoy abriendo el formulario, un momento.", "Ya casi llegamos al formulario."),
    },
    "fill_quote": {
        "en": ("Still filling it in, one moment.", "Almost done with the form."),
        "es": ("Sigo completando el formulario, un momento.", "Ya casi termino el formulario."),
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
    "stores.show": "show_store",
    "product.tab": "open_product",
}

#: The moves whose effect a listing on screen is, and a product page's.
_LISTING_MOVES = ("filter_listing", "commerce.filter", "commerce.sort", "commerce.search")
_PRODUCT_MOVES = ("open_product", "commerce.search")


def _said_list(items: list[str], lang: Lang) -> str:
    """ "Lubritek and Shell", "Lubritek, Shell y Mobil"."""
    if len(items) < 2:
        return "".join(items)
    last = " and " if lang == "en" else " y "
    return ", ".join(items[:-1]) + last + items[-1]


#: Where a product's name turns into its codes and measures: what is said is
#: what comes before ("Aceite LUBRITEK UTF Semisintético 19L" → "Aceite
#: LUBRITEK UTF Semisintético").
_NAME_CODES = re.compile(
    r"\s(?=(?:\d+(?:[.,]\d+)?\s?(?:L|Lt|Lts|lt|lts|cc|ml|cm|mm|mts?|kg|grs?|V|Ah|HP|hp|W|"
    r"pulg|\"|'')\b|\d+\s?W\s?-?\s?\d+|\d+(?:[.,]\d+)?\s?[xX\u00d7]\s?\d|\d+\s\d{3,}|\d{3,}|[A-Z0-9]{2,}-[A-Z0-9]+|\w*\d\w*-\w+|\("
    # A model code: five or more capitals and digits, mixed ("AGPLUBLTUTF", "6205ZZ").
    r"|(?=[A-Z0-9]{5,}\b)(?:\d+[A-Z]|[A-Z]+\d)[A-Z0-9]*\b))",
)


#: Words a said name never ends on: they lead into what was cut (pcfactory
#: dev call 31a45613, "ThinkPad T14 Gen" for "ThinkPad T14 Gen 6").
_DANGLING = frozenset(
    "gen generation generación serie series de del con para y and with for - / + |".split()  # noqa: SIM905
)


def short_name(name: str, words: int = 6) -> str:
    """A product's name as said aloud: up to its first code or measure, at
    most ``words`` words ("Aceite LUBRITEK UTF Semisintético 19L" → "Aceite
    LUBRITEK UTF Semisintético"), never ending on a word that leads into the
    cut ("Repuestos para" is "Repuestos")."""
    head = _NAME_CODES.split(name.strip(), maxsplit=1)[0].strip(" ,-")
    all_words = (head or name).split() if len((head or name).split()) >= 2 else name.split()
    kept = all_words[:words]
    rest = all_words[words:]
    numbered = {"gen", "generation", "generación", "serie"}
    if kept and kept[-1].lower() in numbered and rest and rest[0].isdigit():
        kept.append(rest[0])
    while len(kept) > 1 and kept[-1].lower().strip(".,") in _DANGLING:
        kept.pop()
    return " ".join(kept)


#: Facets whose options read as a brand ("de Lubritek") or a category ("en
#: Lubricantes"); every other is a spec ("con 15W40").
_BRAND_FACETS = frozenset({"marca"})
_KIND_FACETS = frozenset({"categoria"})


def _option_said(option: str) -> str:
    """An option as said: all-capital words of four letters or more in
    ordinary case ("LUBRITEK" → "Lubritek", "SEMI-SINTETICO" stays a code
    only when it has a digit); codes stay ("15W40", "ATF")."""
    return " ".join(
        w.capitalize() if len(w) >= 4 and w.replace("-", "").isalpha() and w.isupper() else w
        for w in option.split()
    )


def filters_said(named: list[tuple[str, str]], lang: Lang) -> str:
    """The filters a move put on, as one natural phrase: "de Lubritek, con
    15W40 y Mineral" / "from Lubritek, with 15W40 and Mineral". An option
    another option begins with is said once."""
    options = [o for _, o in named]
    kept = [
        (f, o)
        for f, o in named
        if not any(other != o and fold(other).startswith(fold(o) + " ") for other in options)
    ]
    brands = [_option_said(o) for f, o in kept if facet_key(f) in _BRAND_FACETS]
    kinds = [o for f, o in kept if facet_key(f) in _KIND_FACETS]
    specs = [_option_said(o) for f, o in kept if facet_key(f) not in _BRAND_FACETS | _KIND_FACETS]
    parts: list[str] = []
    if kinds:
        parts.append(("in " if lang == "en" else "en ") + _said_list(kinds, lang))
    if brands:
        parts.append(("from " if lang == "en" else "de ") + _said_list(brands, lang))
    if specs:
        parts.append(("with " if lang == "en" else "con ") + _said_list(specs, lang))
    return ", ".join(parts)


def listing_line(
    e: ListingShown, lang: Lang, named: list[tuple[str, str]] | list[str] | None = None
) -> str:
    """His line the moment a listing he filtered, sorted or searched lands: how
    many, with what (``named``: the (facet, option) pairs his move put on, as
    the listing writes them), and the first card with its price. Said with no
    model request before it."""
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
            f"Here's one{where}: {name}{price}."
            if n == 1
            else f"Here are {n}{where}. The first is {name}{price}."
        )
    return (
        f"Aquí hay uno{where}: {name}{price}."
        if n == 1
        else f"Aquí hay {n}{where}. El primero es {name}{price}."
    )


def product_line(e: ProductShown, lang: Lang) -> str:
    """His line the moment a product he opened is on screen: its short name
    and its price, or that the store confirms it; and its stock when it is
    short or out."""
    name = short_name(e.name) if e.name else ""
    price = ""
    if e.price_hidden:
        price = (
            ", and its price is confirmed in store"
            if lang == "en"
            else ", y su precio se confirma en tienda"
        )
    elif e.price is not None:
        said = pesos_said(e.price, lang)
        price = f", at {said}" if lang == "en" else f", a {said}"
    if lang == "en":
        line = f"Here's the product: {name}{price}." if name else f"Here's the product{price}."
    else:
        line = (
            f"Aquí está el producto: {name}{price}." if name else f"Aquí está el producto{price}."
        )
    if e.stock == "outOfStock":
        line += " It's out of stock online." if lang == "en" else " No tiene stock online."
    elif e.stock == "lowStock":
        line += " Only a few are left." if lang == "en" else " Quedan pocas unidades."
    return line


def _option_key(label: str) -> str:
    """A facet option, folded and without spaces: "16 GB" and "16GB" are one."""
    return re.sub(r"[^\w]", "", norm(label))


def _option_set(labels: str | list[str] | None) -> frozenset[str]:
    """The options in a filter's value — a list, or labels joined by ", " —
    folded, as a set: the order never counts."""
    items = labels.split(", ") if isinstance(labels, str) else list(labels or [])
    return frozenset(k for i in items if (k := _option_key(i)))


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


def _number_words() -> dict[str, str]:
    """Spoken numbers to digits, folded, both languages, up to 2048 (the
    measures a visitor says: "quince", "cuarenta", "one hundred")."""
    out: dict[str, str] = {}
    for n in [*range(1, 201), 250, 300, 400, 500, 600, 750, 800, 1000, 1200, 1500, 2000]:
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
    words run together ("15w40" in "quince w cuarenta"), a word of it with a
    digit ("12v"), or its number ("100" for "100 Ah", "cien amperes")."""
    words, tight = _heard_tokens(said)
    key = _option_key(option)
    if key and key in tight:
        return True
    parts = re.findall(r"[a-z0-9]+", fold(option))
    if any(any(ch.isdigit() for ch in p) and p in words for p in parts):
        return True
    number = re.match(r"\d+", option.strip())
    return number is not None and number.group(0) in words


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
    while the store redraws it; pcfactory dev calls 31a45613, 8b363867)."""
    return event.count == 0 or not event.items


def _listing_base(path: str) -> str:
    """A listing's address without its query, but a search's with its words."""
    if (q := search_query(path)) is not None:
        return search_path(q)
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
        return isinstance(want, str) and same_product(event.path, want)
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
_FIXED_PAGES = frozenset({"/", "/carro", "/nuestras-tiendas"})
#: Pages only a move takes them to: never cued from his own sentence.
_MOVE_PAGES = frozenset({"/carro", "/cotizacion"})
#: Paths no cue may open: the quote form (start_quote goes there, after a
#: yes) and its confirmation, the account, the login and registration, and
#: the leftover checkout of the shared codebase.
_NEVER = re.compile(
    r"^/(?:cotizacion|registrate|acceso-revision|revision|activar|perfil|sesion-expirada|"
    r"no-autorizado|checkout|login|mi-cuenta|cuenta|pago|webpay)(?:/|$)"
)
#: The pages a visitor in the middle of buying is on: a question there is
#: answered in place, and his reply never moves them off it on its own.
_IN_FLOW = ("/producto/", "/carro", "/cotizacion")
#: A brand's listing: ``/marca/<brand>``, as the product page links it.
_BRAND_PATH = re.compile(r"^/marca/[\w%.-]+$")


#: The page for what the visitor asked about, when his reply forgets to show
#: it; each with the paths the store has used for it, the first the crawl has
#: wins. Matched on their own words, folded, in Spanish and English; the first
#: named wins. Products and listings are not here: those are moves.
_ASKED_PAGES: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...] = tuple(
    (re.compile(rf"\b(?:{w})", re.IGNORECASE), paths)
    for w, paths in (
        (
            r"garantia (?:de (?:la |las )?)?bater|bateria[s]? (?:con|tiene[n]?) garantia"
            r"|battery warranty",
            ("/garantia-devoluciones",),
        ),
        (
            r"cambios?\b|devoluci|devolver|returns?\b|refund"
            r"|garantia(?! (?:de (?:la |las )?)?bater)|warranty",
            ("/cambios-devoluciones", "/garantia-devoluciones"),
        ),
        (
            r"despacho|despachan|envios?\b|cuanto (?:demora|tarda) (?:en )?llegar|shipping"
            r"|deliver(?:y|ies|ed|able|s)?\b",
            ("/politica-despacho",),
        ),
        (
            r"tiendas? fisicas?|sus tiendas|las tiendas|donde (?:queda|quedan|estan) (?:la|las)"
            r" tiendas|sucursales|physical stores?|your stores|store locations?",
            ("/nuestras-tiendas",),
        ),
        (
            r"sobre (?:ustedes|agroplanet)|quienes son ustedes|historia de agroplanet"
            r"|about (?:agroplanet|the company|your company)",
            ("/sobre-nosotros",),
        ),
        (
            r"proteccion de (?:mis )?datos|privacidad|privacy",
            ("/politica-proteccion-datos",),
        ),
        (
            r"bases (?:legales|de (?:la )?promocion)|promociones vigentes",
            ("/bases-promociones-vigentes",),
        ),
        (r"(?:mi |el |tu )?carr(?:o|ito)\b|\bcart\b|basket", ("/carro",)),
    )
)
_ASKED_TAB = re.compile(r"\b(?:tabs?|pestanas?)\b", re.IGNORECASE)
#: Asking to add to the cart is a move, not the cart page.
_ADDS = re.compile(
    r"\b(?:agreg|anad|añad|pon(?:lo|la|er|me)|mete|echa|sum|add|put)\w*", re.IGNORECASE
)
#: A move on the cart: an add, a change, a removal, the quote. With the cart
#: as recognition hears it ("add this to cut").
_CART_MOVE = re.compile(
    r"\b(?:agreg|anad|añad|pon(?:lo|la|er|me)|mete|echa|add|put|quit|sac(?:a|alo|ala|ar)\b"
    r"|elimin|borr|remove|take (?:it|them|that|one) out|cambi\w* (?:la )?cantidad"
    r"|change the (?:quantity|amount)|me lo llevo|me la llevo|lo llevo|la llevo|lo compro"
    r"|la compro|i'?ll take it|cotiz|quote)\w*"
    r"|\b(?:to|into|al|a la|a mi)\s+(?:the |my |mi |el |la )?"
    r"(?:cart|cut|card|carro|carrito)\b",
    re.IGNORECASE,
)


def asks_cart_move(text: str) -> bool:
    """Whether ``text`` asks for a move on the cart (an add, a change, the
    quote) rather than to see the cart."""
    return bool(_CART_MOVE.search(fold(text)))


#: A plain yes, in either language, as recognition hears it.
_YES = re.compile(
    r"\b(?:si|dale|ya|ok(?:ay|ey)?|yes|yeah|yep|sure|claro|perfecto|de acuerdo|hazlo"
    r"|go ahead|do it|listo|obvio|vamos|confirm\w*|correcto|exacto|bueno|ya po)\b",
    re.IGNORECASE,
)
_NO = re.compile(
    r"^\W*(?:no|nop|nope|todavia no|aun no|not yet|mejor no|espera|wait)\b", re.IGNORECASE
)
#: What asks for each confirmed move by name, without a yes.
_ASKS_FOR: dict[str, re.Pattern[str]] = {
    "cart": _CART_MOVE,
    "quote": re.compile(
        r"\b(?:cotiz\w*|quote|pag(?:ar|o|ue)|compr(?:ar|arlo|arla|o|emos)|finaliz\w*"
        r"|termin\w*|continu\w* (?:con )?(?:la )?compra|buy|pay|check ?out)\b",
        re.IGNORECASE,
    ),
    # Saying what goes in the form is asking for it to go in: "me llamo…",
    # "mi correo es…", a phone number.
    "form": re.compile(
        r"\b(?:complet\w*|llen\w*|anot\w*|pon(?:lo|la|los|er)|escrib\w*|fill\w*|put|type"
        r"|me llamo|mi nombre|my name|mi (?:telefono|celular|fono|numero|correo|mail|email"
        r"|direccion|region|comuna|calle)|my (?:phone|number|email|address)|arroba)\b"
        r"|@|\d{4}\D{0,3}\d{4}",
        re.IGNORECASE,
    ),
}


def consents(kind: str, last: str, before: str = "") -> bool:
    """Whether the visitor's last words let him make a confirmed move of
    ``kind`` (``cart``, ``quote``, ``form``): they asked for it by name (in
    their last words, or the fragment before them), or said yes to his offer
    of it; never when their last words are a no."""
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


def private_kind(value: str) -> str | None:
    """What of theirs ``value`` carries that must never be typed or said
    back: a RUT, a card or a password; ``None`` when nothing. Their name,
    phone, email and address are not here: on the quote form they are his to
    fill, once they said yes."""
    if _RUT.search(value) or (_RUT_WORD.search(value) and re.search(r"\d{5,}", value)):
        return "a RUT"
    if _CARD.search(value):
        return "a card number"
    if _SECRET.search(value):
        return "a password"
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
    agroplanet agro planet tienda producto productos precio precios desde aqui puedo""".split()  # noqa: SIM905
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
#: the quote form, and each of its fields typed at a human pace).
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
#: What a reply may write as a part of the product page, folded.
_TABS: dict[str, ProductTab] = {
    "specs": "specs",
    "especificaciones": "specs",
    "specifications": "specs",
    "ficha tecnica": "specs",
    "caracteristicas": "specs",
    "details": "details",
    "detalle": "details",
    "detalle del producto": "details",
    "descripcion": "details",
    "description": "details",
    "about": "details",
    "photos": "photos",
    "fotos": "photos",
    "galeria": "photos",
    "imagenes": "photos",
    "zoom": "zoom",
    "foto grande": "zoom",
    "fotos grandes": "zoom",
    "big photo": "zoom",
    "big photos": "zoom",
    "price": "price",
    "precio": "price",
    "prices": "price",
    "cotizar": "price",
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
#: What the store's stock status is, said: words, never a count or a promise.
_STOCK_SAID = {
    "inStock": "available online (say: está disponible)",
    "lowStock": "few units left online (say: quedan pocas unidades)",
    "outOfStock": "no stock online (say: no tiene stock online)",
}
_HIDDEN_PRICE = (
    'price NOT shown: the page says "Confirmar precio en tienda" — never say a price for it; '
    "the store confirms it, and the quote is how they get it"
)


@dataclasses.dataclass(frozen=True)
class Live:
    """What their screen and his reads last said of one product's price and stock."""

    path: str
    name: str = ""
    price: int | None = None
    regular_price: int | None = None
    discount: int | None = None
    price_hidden: bool = False
    stock: str = ""
    source: str = "page"
    at: float = 0.0

    def line(self, lang: Lang) -> str:
        bits: list[str] = []
        if self.price_hidden:
            bits.append(_HIDDEN_PRICE)
        elif self.price is not None:
            bits.append(f"price {_money(self.price, lang)}")
            pct = saving(self.price, self.regular_price)
            if pct is None and self.discount is not None and self.discount >= 5:
                pct = self.discount if self.regular_price else None
            if pct is not None and self.regular_price:
                bits.append(f"before {pesos(self.regular_price)}, a real saving of {pct}%")
        if self.stock:
            bits.append(_stock_said(self.stock))
        if not bits:
            bits.append("no price read")
        return ", ".join(bits) + f" ({_SOURCE_SAID.get(self.source, self.source)})"


def _stock_said(stock: str) -> str:
    return _STOCK_SAID.get(stock.strip(), f"stock: {stock.strip()}")


def _product_note(e: ProductShown, lang: Lang) -> str:
    name = e.name or e.path
    head = "Live read of" if e.source == "api" else "The product page in front:"
    note = f"[{head} “{name}” ({e.path})" + (f", brand {e.brand}" if e.brand else "")
    note += (f", Código Fabricante {e.maker_code}" if e.maker_code else "") + ". "
    seen = Live(
        e.path, name, e.price, e.regular_price, e.discount, e.price_hidden, e.stock, e.source
    )
    note += seen.line(lang) + "."
    if e.description:
        note += f" Detalle del Producto: {e.description[:600]}."
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
        # is not there (pcfactory dev call 8b363867).
        note += (
            " Its facets, with every option (cue them as written): "
            + "; ".join(f"{f.facet} ({', '.join(f.options)})" for f in offered)
            + "."
        )
    if e.items:
        cards = [
            f"{i.name} ({i.path}), "
            + (_money(i.price, lang) if i.price is not None else "Confirmar precio en tienda")
            for i in e.items
        ]
        note += f" On screen, in order: {_clip(cards, _LISTED_IN_NOTE)}."
    elif e.count == 0:
        note += " No product shows for these filters."
    return note + "]"


def _prices_note(e: PricesRead, lang: Lang) -> str:
    lines: list[str] = []
    for i in e.items:
        path = product_path(i.path) or i.path
        live = Live(
            path, i.name, i.price, i.regular_price, i.discount, i.price_hidden, i.stock, "api"
        )
        lines.append(f"{i.name or path} ({path}): {live.line(lang)}")
    note = f"[Live prices: {'; '.join(lines) or 'none'}."
    if e.missing:
        note += (
            f" Not read: {', '.join(e.missing)} — the store gave nothing for them: say so, "
            "never a price for them."
        )
    return note + "]"


def _found_note(e: ProductsFound, lang: Lang) -> str:
    asked = [
        f"“{e.query}”" if e.query else "",
        f"category {e.category_code}" if e.category_code else "",
        f"brand {e.brand}" if e.brand else "",
    ]
    what = ", ".join(a for a in asked if a) or "everything"
    suggestion = (
        f' The store suggests the spelling "{e.suggestion}".'
        if e.suggestion and norm(e.suggestion) != norm(e.query or "")
        else ""
    )
    if not e.items:
        return (
            f"[find_products found nothing for {what}.{suggestion} Say so plainly, and offer "
            "to widen it: other words, the part's code, or a category.]"
        )
    total = f"{e.total} match" if e.total is not None else "Some match"
    lines: list[str] = []
    for n, i in enumerate(e.items, 1):
        path = product_path(i.path) or i.path
        live = Live(
            path, i.name, i.price, i.regular_price, i.discount, i.price_hidden, i.stock, "found"
        )
        lines.append(
            f"{n}. {i.name} ({path})" + (f", {i.brand}" if i.brand else "") + f": {live.line(lang)}"
        )
    return (
        f"[find_products for {what}: {total}; the first {len(e.items)}, in the store's order — "
        + "; ".join(lines)
        + f".{suggestion} Name two or three that fit what they said, each with its price (or "
        "that the store confirms it) and whether it is available, recommend one for their "
        "machine or job, and open it with {page: /producto/<slug>/<sku>}.]"
    )


_STORE_STOCK = {"inStock": "available", "lowStock": "few units", "outOfStock": "none"}


def _store_stock_said(qty: int | None, status: str) -> str:
    if status in _STORE_STOCK:
        return _STORE_STOCK[status]
    if qty is None:
        return "unknown"
    return "none" if qty <= 0 else "available"


def _stock_note(e: StockRead, k: Knowledge) -> str:
    name = e.name or e.path
    note = f"[Stock of “{name}” ({product_path(e.path) or e.path}): "
    note += _stock_said(e.online) if e.online else "online stock not reported"
    have = [s for s in e.stores if _store_stock_said(s.qty, s.status) != "none"]
    if e.stores:
        listed = [
            f"{s.name}"
            + (f" ({s.city})" if s.city else "")
            + f": {_store_stock_said(s.qty, s.status)}"
            for s in e.stores
        ]
        note += f"; in stores: {_clip(listed, 30)}"
    else:
        note += "; no store reports it"
    note += "."
    if e.asked:
        if e.matched:
            here = next((s for s in e.stores if norm(s.name) == norm(e.matched)), None)
            if here is not None:
                note += (
                    f" The store they asked about, {e.matched}: "
                    f"{_store_stock_said(here.qty, here.status)}."
                )
            else:
                listed_store = k.store(e.matched)
                region = listed_store.region if listed_store is not None else ""
                near = [
                    s.name
                    for s in have
                    if region and (st := k.store(s.name)) is not None and st.region == region
                ]
                note += f" The store they asked about, {e.matched}, reports none."
                if near:
                    note += f" Others in {region} that have it: {', '.join(near[:4])}."
        else:
            note += f" No store matched “{e.asked}”: ask which store they mean."
    return (
        note + " Say stock in words, never a count, and that a seller confirms it with the quote. "
        "Offer to show the store ({store: Name}) when it helps.]"
    )


def _store_note(e: StoreShown) -> str:
    where = ", ".join(x for x in (e.address, e.city) if x)
    note = f"[The store {e.name} is on screen, on /nuestras-tiendas" + (
        f": {where}" if where else ""
    )
    note += "."
    if e.phone:
        note += f" Phone: {e.phone} (say it digit by digit if they want it)."
    note += f" Hours: {e.hours}." if e.hours else " Its card shows no hours."
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
        note += f" Total {_money(e.subtotal, lang)}."
    return note + _QUOTE_IS_THEIRS + "]"


#: What the cart's lines end with: how far he may go, and what is theirs.
_QUOTE_IS_THEIRS = (
    " update_cart_item changes how many of a line they have, or takes it out. Agroplanet sells "
    "by quote: when they want to buy, start_quote takes them to the Formulario de cotización, "
    "and fill_quote fills it with what they say; the RUT and Crear cotización are theirs, a "
    "Agroplanet then validates it and confirms it in writing by email. Never offer the Webpay "
    "link."
)

#: The quote form's fields, as the slice names them, said.
_FIELD_SAID = {
    "name": "Nombre Completo / Razón Social",
    "rut": "RUT",
    "phone": "Teléfono",
    "email": "Correo electrónico",
    "region": "Región",
    "commune": "Comuna",
    "street": "Calle",
    "number": "Número",
    "unit": "Dpto / casa / Oficina",
    "notes": "Notas",
}


def _fields_said(names: list[str]) -> str:
    return ", ".join(_FIELD_SAID.get(n, n) for n in names)


def _quote_note(e: QuoteState, lang: Lang) -> str:
    match e.step:
        case "form":
            note = "[The Formulario de cotización is in front"
            if e.items is not None:
                note += f", for {e.items} products"
            if e.total is not None:
                note += f", Total {_money(e.total, lang)}"
            note += "."
            if e.filled:
                note += f" Filled: {_fields_said(e.filled)}."
            mine = [m for m in e.missing if m != "rut"]
            if mine:
                note += f" Still missing: {_fields_said(mine)} — offer to fill them with them."
            if "rut" in e.missing:
                note += " The RUT is still empty: theirs to type."
            if not mine:
                note += (
                    " Everything you may fill is in: tell them to type their RUT and press "
                    "Crear cotización themselves."
                )
        case "done":
            note = (
                "[The quote was created: the visitor pressed Crear cotización. Agroplanet "
                "validates it (the stock and a formal price) and confirms it in writing to "
                "their email; payment is settled then, with Agroplanet."
            )
        case _:
            note = "[A quote page is in front."
    return note + " The RUT and Crear cotización are theirs; never type or press them.]"


# ─── The brain ─────────────────────────────────────────────────────────────────


#: The menu's top categories, as it writes them, when the knowledge has none.
_MENU_TOPS = (
    "Baterías",
    "Rodamientos",
    "Lubricantes Y Fluidos",
    "Neumáticos, Cámaras Y Llantas.",
    "Agroferretería",
    "Repuestos De Tractor",
    "Implementos Agrícolas",
    "Insumos Agrícolas",
    "Repuestos de Implementos",
    "Maquinaria",
)
#: What a visitor or he says for a top category, folded, and the menu's words.
_MENU_WORDS: dict[str, str] = {
    "lubricantes": "Lubricantes Y Fluidos",
    "aceites": "Lubricantes Y Fluidos",
    "aceite": "Lubricantes Y Fluidos",
    "lubricants": "Lubricantes Y Fluidos",
    "oils": "Lubricantes Y Fluidos",
    "neumaticos": "Neumáticos, Cámaras Y Llantas.",
    "neumatico": "Neumáticos, Cámaras Y Llantas.",
    "llantas": "Neumáticos, Cámaras Y Llantas.",
    "tires": "Neumáticos, Cámaras Y Llantas.",
    "tyres": "Neumáticos, Cámaras Y Llantas.",
    "batteries": "Baterías",
    "bearings": "Rodamientos",
    "rulemanes": "Rodamientos",
    "ferreteria": "Agroferretería",
    "hardware": "Agroferretería",
    "tractor": "Repuestos De Tractor",
    "tractor parts": "Repuestos De Tractor",
    "repuestos": "Repuestos De Tractor",
    "implementos": "Implementos Agrícolas",
    "implements": "Implementos Agrícolas",
    "insumos": "Insumos Agrícolas",
    "maquinas": "Maquinaria",
    "machinery": "Maquinaria",
    "tractores": "Maquinaria",
}

#: The cue verbs that point at something on the page in front.
_POINTING = frozenset({"show", "faq", "filter", "sort", "tab", "store", "menu"})


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


class AgroplanetBrain(OpenAIBrain):
    """One per session. Javier: Agroplanet's knowledge, a mirror of the
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
        #: cart, the quote form, and what his last catalogue read found.
        self.product: ProductShown | None = None
        self.listing: ListingShown | None = None
        self.cart: CartState | None = None
        self.quote: QuoteState | None = None
        self.found: ProductsFound | None = None
        #: The facets the moves of the visitor's turn asked for, for the
        #: landing line; and the listing move whose line waits to be said.
        self._turn_facets: list[str] = []
        self._landing: tuple[Landing, str, float] | None = None
        #: Every price and stock read this call, by SKU; every product's
        #: specifications as its page showed them; and each SKU's path as the
        #: page linked it, slug included, to open it by.
        self.prices: dict[str, Live] = {}
        self.specs: dict[str, dict[str, str]] = {}
        self._paths: dict[str, str] = {}
        #: The recognizer's patience now: longer while the quote form is in
        #: front, where a phone or an email is said a piece at a time.
        self._patience = AGROPLANET_PATIENCE
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
                stt=SttConfig(language=self.spoken, patience=AGROPLANET_PATIENCE),
                tts=TtsConfig(voice=VOICE, language=self.spoken),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
            )
        )
        logger.info(
            "agroplanet: session start on {} in {}{}",
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
                "agroplanet: {} {} still running at {:.1f} s ({}); holding line {!r}",
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
        return for_the_voice(line) if self.spoken == "es" else english_for_the_voice(line)

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
            logger.info("agroplanet: language -> {} (heard)", heard)
        if holds_spanish(msg.text, self.spoken, self._language_of):
            logger.info("agroplanet: held in Spanish: {!r}", msg.text)
            self._note(HELD_NOTE)
        if (what := private_kind(msg.text)) is not None:
            logger.info("agroplanet: the visitor said {}; never repeated", what)
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
        the quote form, where a question is answered in place."""
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
            respell = for_the_voice if self.spoken == "es" else english_for_the_voice
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
            logger.info("agroplanet: done line {!r}", first)
            respell = for_the_voice if self.spoken == "es" else english_for_the_voice
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
                logger.warning("agroplanet: the model returned nothing; asking once more")
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
                logger.info("agroplanet: language -> {} (written)", written)
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
                    respell = for_the_voice if self.spoken == "es" else english_for_the_voice
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
            logger.info("agroplanet: no backstop to {}: a cart move is asked", path)
            return chunk
        logger.info("agroplanet: the reply has no cue; showing {} first", path)
        return f"{{page: {path}}}{chunk}"

    def _asked_cart_move(self) -> bool:
        """Whether the visitor's last two fragments ask for a move on the cart."""
        return asks_cart_move(" ".join(self._heard[-2:]))

    def _known_path(self, value: str) -> str | None:
        """The store path a page cue names, as the store links it, or ``None``.
        A product only by a SKU read this call; a search by its words; a
        category by its code, whatever slug he wrote."""
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
        if (cat := self.kb.category(path)) is not None:
            return cat.path
        if _BRAND_PATH.match(path):
            return path
        if product_sku(path) is not None:
            return self._product_path(path) if self._seen(path) else None
        return None

    def _seen(self, path: str) -> bool:
        """Whether this product came up this call: read, listed, found, in the
        cart or in front."""
        key = product_sku(path)
        if key is None:
            return False
        if key in self.prices or key in self.specs or key in self._paths:
            return True
        if self.product is not None and product_sku(self.product.path) == key:
            return True
        if product_sku(self._path) == key:
            return True
        rows: list[str] = []
        if self.listing is not None:
            rows += [i.path for i in self.listing.items]
        if self.found is not None:
            rows += [i.path for i in self.found.items]
        if self.cart is not None:
            rows += [i.path for i in self.cart.items]
        return any(product_sku(r) == key for r in rows)

    def _product_path(self, path: str) -> str:
        """The product's path as the page last linked it, its slug included;
        else the one given, canonical."""
        key = product_sku(path)
        if key is not None and (known := self._paths.get(key)) is not None:
            return known
        return product_path(path) or path

    def _link(self, path: str) -> None:
        """Note a product's path as the page links it, by its SKU."""
        key, full = product_sku(path), product_path(path)
        if key is None or full is None:
            return
        # A bare SKU's made-up slug never replaces the page's own.
        if not full.startswith("/producto/producto/") or key not in self._paths:
            self._paths[key] = full

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
            and not verbs & _POINTING
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
                logger.info("agroplanet: he talks about {} with no cue; opening it", asked)
                out.append(("page", [asked]))
                path = asked
        self._cue_path = path
        # A sentence that filters, sorts or points is about what it points at.
        if verbs & _POINTING:
            return out
        shown = self._section_for(sentence, path)
        if shown is not None and shown != self._shown:
            out.append(("show", [shown]))
        return out

    def _section_for(self, sentence: str, path: str | None) -> str | None:
        """The heading on ``path`` that ``sentence`` is about."""
        if path is None or product_sku(path) is not None:
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
                "agroplanet: cue {} {} dropped: a move this reply loads the page", move.id, args
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
            case "menu.open":
                return self._resolve_menu(want)
            case "stores.show":
                return self._resolve_store(want)
            case "commerce.filter":
                return self._resolve_filter(want, args[1] if len(args) > 1 else "")
            case "commerce.sort":
                return self._resolve_sort(want)
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
        return product_sku(self._cue_path or self._path) is not None

    def _resolve_tab(self, asked: str) -> list[str] | None:
        tab = _TABS.get(norm(asked))
        if tab is None or not self._on_product():
            logger.info(
                "agroplanet: tab cue {!r} dropped: no product in front, or no such tab", asked
            )
            return None
        return [tab]

    def _resolve_menu(self, asked: str) -> list[str] | None:
        """A top category of the menu, as the menu writes it: by its name
        (case, accents and a synonym aside: "lubricantes" is "Lubricantes Y
        Fluidos"), or the top a deeper category he named sits under."""
        tops = [c.name for c in self.kb.tops() if not c.hidden] or list(_MENU_TOPS)
        hit = _match(asked, tops) or _match(_MENU_WORDS.get(norm(asked), asked), tops)
        if hit is None and (cat := self.kb.find_category(asked)) is not None:
            top = self.kb.top_of(cat)
            hit = top.name if top.level == 1 else None
        if hit is None:
            logger.info("agroplanet: menu cue {!r} dropped: no such top category", asked)
            return None
        return [hit]

    def _resolve_store(self, asked: str) -> list[str] | None:
        store = self.kb.store(asked)
        if store is None:
            if self.kb.stores:
                logger.info("agroplanet: store cue {!r} dropped: no such store", asked)
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
            return cat.path, cat
        if _BRAND_PATH.match(path):
            return path, None
        if self.listing is not None and _listing_base(self.listing.path) == path:
            return path, None
        page = self.page
        if (
            page is not None
            and canonical_path(page.path) == path
            and page.kind in ("category", "search", "brand")
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
            logger.info("agroplanet: cue {} {} dropped ({})", raw.verb, list(raw.args), why)
            return
        cue = f"{{{raw.verb}: {' | '.join(raw.args)}}}"
        logger.info("agroplanet: cue {} refused: {}", cue, refusal)
        self._note(f"[Not done on the page ({cue}): {refusal}. It was not applied.]")
        self._answered(f"{cue} not done: {refusal}")

    def _facets_for(
        self, path: str, cat: Category | None
    ) -> list[tuple[str, tuple[str, ...], bool]]:
        """The facets of the listing at ``path``, each with whether its options
        are all there: as the listing in front reports them when it is that
        one (the live page wins), else as the category list has them (its
        busiest options only, when the panel has more)."""
        if self.listing is not None and _listing_base(self.listing.path) == path:
            live = [(f.facet, tuple(f.options), True) for f in self.listing.facets]
            if live:
                return live
        if cat is not None:
            return [(f.name, f.options, f.total <= len(f.options)) for f in cat.facets]
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
        writes them; or why not, naming what the listing has."""
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
        name, options, whole = hit if hit is not None else (facet.strip(), (), True)
        parts = _said_parts(value)
        if not parts:
            return "say which option, as the listing writes it"
        out: list[str] = []
        unknown: list[str] = []
        for part in parts:
            got = _match(part, options) if options else part
            if got is None and not whole:
                # The category list keeps a panel's busiest options: one past
                # them may still be there, and the page says if it is not.
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
        none of them: "al menos cien amperes" is one option, never every size
        above it (pcfactory dev call 8b363867)."""
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
                "agroplanet: {} options {} cut to {}: the visitor named only those ({!r})",
                facet,
                options,
                kept,
                said,
            )
        return kept or options[:1]

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
        event = AGROPLANET_EVENTS.parse(msg)
        if event is None:
            return
        logger.info("agroplanet: {} — {}", type(event).__voqal_event__, event)
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
            logger.warning("agroplanet: switch to {} refused: {}", event.language, rejected)
            self.spoken = was
            session.dispatch(LanguageChanged(language=was))
            return
        logger.info("agroplanet: language -> {} (toggle)", event.language)
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
            stt=SttConfig(language=language, patience=self._patience),
            tts=TtsConfig(voice=VOICE, language=language),
        )

    def _patient(self, patience: int) -> None:
        """Set the recognizer's patience, with both language legs as the
        pairing rule asks; nothing is sent when it is already that."""
        if patience == self._patience:
            return
        self._patience = patience
        logger.info("agroplanet: patience -> {}", patience)
        configure_soon(
            self.session,
            Config(
                stt=SttConfig(language=self.spoken, patience=patience),
                tts=TtsConfig(voice=VOICE, language=self.spoken),
            ),
        )

    # ─── Page → brain ───────────────────────────────────────────────────

    def apply_event(self, event: AgroplanetEvent) -> str | None:
        """Patch the mirror; return the line the model should see."""
        match event:
            case PageChanged():
                self.page = event
                self._path = (
                    _listing_base(event.url or event.path)
                    if event.kind == "search"
                    else canonical_path(event.path)
                )
                self._page_unseen = True
                if event.kind != "product":
                    self.product = None
                if event.kind not in ("category", "search", "brand"):
                    self.listing = None
                if event.kind != "quote":
                    self._patient(AGROPLANET_PATIENCE)
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
                    self._link(i.path)
                    self._remember(
                        i.path,
                        i.name,
                        i.price,
                        i.regular_price,
                        i.discount,
                        i.price_hidden,
                        i.stock,
                        "api",
                    )
                return _prices_note(event, self.spoken)
            case ProductsFound():
                self.found = event
                for i in event.items:
                    self._link(i.path)
                    self._remember(
                        i.path,
                        i.name,
                        i.price,
                        i.regular_price,
                        i.discount,
                        i.price_hidden,
                        i.stock,
                        "found",
                    )
                return _found_note(event, self.spoken)
            case StockRead():
                self._link(event.path)
                return _stock_note(event, self.kb)
            case StoreShown():
                return _store_note(event)
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
                self._link(path)
                if view.specs and (sku := product_sku(path)) is not None:
                    self.specs[sku] = dict(view.specs)
                self._remember(
                    path,
                    view.name,
                    view.price,
                    view.regular_price,
                    view.discount,
                    view.price_hidden,
                    view.stock,
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
                    self._link(i.path)
                    self._remember(
                        i.path, i.name, i.price, i.regular_price, None, False, "", "listing"
                    )
                self.stage.landed(
                    _LISTING_MOVES, event=listing, fits=lambda landing: lands(landing, listing)
                )
            case "cart":
                cart = cart_view(value)
                self.cart = cart
                for i in cart.items:
                    if i.path:
                        self._link(i.path)
                        self._remember(i.path, i.name, i.price, None, None, False, "", "cart")
            case "quote":
                quote = quote_view(value)
                self.quote = quote
                self._patient(_FORM_PATIENCE if quote.step == "form" else AGROPLANET_PATIENCE)
                return _quote_note(quote, self.spoken)
            case _:
                pass
        return folded.note

    def _merged_product(self, view: ProductShown) -> ProductShown:
        """The product's new report over its last one: the store's live read
        sets the price and stock, and keeps the page's specs when it has none."""
        before = self.product
        if before is None or not same_product(before.path, view.path):
            return view
        keep: dict[str, Any] = {}
        if not view.specs and before.specs:
            keep["specs"] = before.specs
        if view.source == "page" and before.source == "api":
            # The page's own copy never undoes the live read.
            keep |= {
                "price": before.price,
                "regular_price": before.regular_price,
                "discount": before.discount,
                "price_hidden": before.price_hidden,
                "stock": before.stock,
                "stock_level": before.stock_level,
                "source": "api",
            }
        for name in ("brand", "maker_code", "description", "sku"):
            if not getattr(view, name) and getattr(before, name):
                keep[name] = getattr(before, name)
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
        regular_price: int | None,
        discount: int | None,
        price_hidden: bool,
        stock: str,
        source: str,
    ) -> None:
        """One more thing their screen or a read said of a product's price or
        stock, by its SKU. A live read is not overwritten by a page or card
        copy of it."""
        key = product_sku(path)
        if key is None or (price is None and not price_hidden and not stock):
            return
        before = self.prices.get(key)
        if (
            before is not None
            and _SOURCE_RANK.get(before.source, 0) > _SOURCE_RANK.get(source, 0)
            and (before.price is not None or before.price_hidden)
        ):
            return
        self.prices[key] = Live(
            self._product_path(path),
            name or (before.name if before else ""),
            price,
            regular_price,
            discount,
            price_hidden,
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
            self._note(f"[The visitor's open Agroplanet tabs — {listed}.]")
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
            "category": "a category listing",
            "search": "search results",
            "brand": "a brand's listing",
            "product": "a product page",
            "cart": "the cart page",
            "quote": "the Formulario de cotización",
            "stores": "the store list",
            "policy": "a policy page",
            "page": "a page of the store",
        }
        note = f"[The tab in front shows {kinds[p.kind]}: “{p.title or p.path}” ({self._path})."
        if p.headings:
            note += f" Its headings: {_clip(p.headings, _HEADINGS_IN_NOTE)}."
        if p.faqs:
            note += f" Its panels: {_clip(p.faqs, _FAQS_IN_NOTE)}."
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
            "agroplanet: {} {} on screen at {:.1f} s; landing line {!r}",
            landing.call_ref,
            landing.move.id,
            landing.seconds,
            line,
        )
        self._shorten_idle(_DONE_MS)
        return line

    def _fresh_lines(self, lines: list[str]) -> list[str]:
        """The landing lines to say now. A listing's is rebuilt from the
        listing as it stands, never from an older report; and while another
        listing move of his is still to land, his line waits for that one's."""
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
            logger.info("agroplanet: landing line held: another listing move is still running")
            return lines[:-1]
        event = landing.event if isinstance(landing.event, ListingShown) else None
        newer = event is not None and event is not self.listing
        if newer and not empty_listing(self.listing):
            line = listing_line(
                self.listing,
                self.spoken,
                landed_options(landing, self.listing, self._turn_facets),
            )
            logger.info("agroplanet: landing line rebuilt from the newest listing: {!r}", line)
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
            logger.info("agroplanet: {} asked for again while it runs; not sent twice", move)
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
                "next step (the quote, the form's next field, the store near them). For names and "
                "prices, "
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
            logger.warning("agroplanet: a move called with tools off; refused")
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
        logger.info("agroplanet: {} without a yes; not sent", doing)
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
        key = product_sku(path)
        return self.prices.get(key) if key is not None else None

    def _product_known(self, path: str) -> str | None:
        """The product's path as the page links it, if their screen or a read
        of this call showed it; else ``None``."""
        if product_sku(path) is None or _NEVER.match(canonical_path(path)):
            return None
        return self._product_path(path) if self._seen(path) else None

    def _unknown_product(self, path: str) -> str:
        return (
            f"Not done: '{path}' is not a product their screen or your reads showed this call. "
            "Find it with find_products first, and use the /producto/<slug>/<sku> it gives."
        )

    def _in_front(self) -> str | None:
        """The product page in front, as /producto/<slug>/<sku>."""
        if self.product is not None:
            return product_path(self.product.path)
        return product_path(self._path)

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        """Read the store's knowledge and their screen; read the catalogue,
        prices and stock live; search, filter and open on their screen; show
        a store; change the cart, take them to the quote form and fill it in
        (never the RUT, never Crear cotización); move their tabs; switch
        language."""
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
            self.add_to_cart,
            self.update_cart_item,
            self.show_cart,
            self.start_quote,
            self.fill_quote,
            self.focus_tab,
            self.set_language,
        ]

    @needs_result_now
    async def read_screen(self, request: ReadRequest) -> str:
        """Read part of their screen as the page last reported it: the product
        page in front with its price, stock and specifications, the listing,
        the cart, or the quote form."""
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
            case "quote":
                if self.quote is not None:
                    return _quote_note(self.quote, self.spoken)
        mirror = self.stage.mirror
        return mirror.read(request.slice) if mirror is not None else "Nothing to read."

    @needs_result_now
    async def read_topic(self, request: TopicRequest) -> str:
        """Read one of Agroplanet's knowledge topics before answering from it."""
        topic = self.kb.topics.get(request.topic)
        if topic is None:
            return f"No topic '{request.topic}' is written yet: use search_site."
        return topic.text

    @needs_result_now
    async def read_category(self, request: CategoryRequest) -> str:
        """Read one category of the store: its path, the categories under it,
        and every filter its listing offers with its options, written as the
        listing writes them. For a category or a filter the list below does
        not show."""
        said = request.name.strip()
        c = self.kb.find_category(said)
        if c is None:
            return f"No category matches '{said}'. Use find_products with words instead."
        top = self.kb.top_of(c)
        out = [f"{c.name} ({c.code}) {c.path}" + (f", under {top.name}" if top is not c else "")]
        if c.page_name and norm(c.page_name) != norm(c.name):
            out.append(f"Its listing is titled “{c.page_name}”.")
        under = self.kb.children(c)
        if under:
            out.append(
                "Under it: "
                + "; ".join(f"{k.name} ({k.code}) {k.path}" for k in under[:_UNDER_SHOWN])
                + (f"; and {len(under) - _UNDER_SHOWN} more" if len(under) > _UNDER_SHOWN else "")
            )
        for f in c.facets:
            if f.options:
                more = (
                    f" (+{f.total - len(f.options)} more on the page)"
                    if f.total > len(f.options)
                    else ""
                )
                out.append(f"{f.name}: {', '.join(f.options)}{more}")
        if not c.facets:
            out.append("Its filters are read from the listing once it is in front.")
        return "\n".join(out)

    @needs_result_now
    async def search_site(self, request: SearchRequest) -> str:
        """Search www.agroplanet.cl's information pages, sections and panels
        (not the products: find_products is for those). Each result names the
        page path and the section heading to take them to."""
        hits = self.kb.search(request.query, _SEARCH_HITS)
        if not hits:
            return (
                f"Nothing on www.agroplanet.cl's pages matches '{request.query}'. Say so plainly."
            )
        out: list[str] = []
        for h in hits:
            if h.kind == "faq":
                out.append(f"[panel on {h.path}] {h.title}\n  {h.snippet}")
            else:
                where = f", heading: {h.section}" if h.section else ""
                out.append(f"[page] {h.title} — path: {h.path}{where}\n  {h.snippet}")
        return "\n".join(out)

    async def find_products(self, request: FindRequest) -> str:
        """Read the store's own catalogue in their browser, without moving their
        screen: up to eight products with their live prices and stock, and how
        many match, from their words, a category and a brand. It returns at
        once; the products come back to you in square brackets."""
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
        if cat is not None and not cat.code:
            words = f"{words} {cat.name}".strip()
            cat = None
        if not words and cat is None and not request.brand:
            return "Not read: give the words, a category or a brand to look for."
        args = FindProductsArgs(
            query=words or None,
            category_code=cat.code if cat is not None else None,
            brand=(request.brand or "").strip() or None,
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
            )
            if x
        )
        return f"Reading the catalogue for {what}. " + self._sent_note("'Te busco opciones.'")

    async def check_prices(self, request: CheckPricesRequest) -> str:
        """Read the live price, discount and stock of up to six products from
        the store itself, without moving their screen. It returns at once; the
        prices come back to you after."""
        if (meta := self._meta_turn()) is not None:
            return meta
        paths: list[str] = []
        unknown: list[str] = []
        for raw in request.paths:
            if product_sku(raw) is None:
                unknown.append(raw)
            elif not any(same_product(raw, p) for p in paths):
                paths.append(self._product_path(raw))
        if not paths:
            return (
                f"Not read: {', '.join(unknown) or 'no paths'} — not product paths. "
                "Use '/producto/<slug>/<sku>' from find_products or their screen."
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
        """Read a product's stock online and in the stores that report it, in
        their browser, without moving their screen. For "¿la tienen en
        Talca?". It returns at once; the stock comes back to you after."""
        if (meta := self._meta_turn()) is not None:
            return meta
        path = self._product_path(request.path) if request.path else self._in_front()
        if path is None or product_sku(path) is None:
            return (
                "Not read: which product? Give its '/producto/<slug>/<sku>', or open it first; "
                "no product page is in front."
            )
        store_said = (request.store or "").strip()
        store: Store | None = self.kb.store(store_said) if store_said else None
        args = CheckStockArgs(path=path, store=(store.name if store else store_said) or None)
        self.stage.send("check_stock", args.model_dump())
        landed(_LANDED["stock"][self.spoken])
        where = f" at {args.store}" if args.store else " online and in the stores"
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
        order. Only facets and options that listing has. It returns at once;
        what the listing shows comes back to you after."""
        if (meta := self._meta_turn()) is not None:
            return meta
        raw = request.category.strip()
        cat: Category | None = None
        if raw.lower().startswith("search:"):
            path = search_path(raw.split(":", 1)[1])
        elif search_query(raw) is not None:
            path = _listing_base(raw)
        elif _BRAND_PATH.match(canonical_path(raw)):
            path = canonical_path(raw)
        else:
            cat = self.kb.find_category(raw)
            if cat is None:
                listing_here = self.listing is not None and _listing_base(
                    self.listing.path
                ) == canonical_path(raw)
                if not listing_here:
                    tops = ", ".join(c.name for c in self.kb.tops())
                    return (
                        f"Not done: no category '{raw}'. Use one of the category list "
                        f"(top level: {tops or 'not loaded'}), or find_products with words."
                    )
                path = canonical_path(raw)
            else:
                path = cat.path
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
        removed = [x for x in (request.remove or []) if ":" in x]
        refused += [f"'{x}' is not 'Facet: Option'" for x in request.remove or [] if ":" not in x]
        if request.page is not None and request.page < 1:
            refused.append("page is 1 or more")
        if refused:
            return "Not done: " + "; ".join(refused) + "."
        action = FilterListingArgs(
            category_path=path,
            filters=filters or None,
            sort=request.sort,
            remove=removed or None,
            clear=request.clear or None,
            page=request.page,
        )
        queued = self._move("filter_listing", action, "filter")
        if queued is not None:
            return queued
        bits = list(filters)
        if request.sort:
            bits.append(f"sorted {request.sort}")
        bits += [f"without {x}" for x in removed]
        if request.clear:
            bits.append("every filter off")
        if request.page:
            bits.append(f"page {request.page}")
        applied = ", ".join(bits)
        return (
            f"Opening {cat.name if cat else path}" + (f" with {applied}" if applied else "") + ". "
        ) + self._sent_note("'Te filtro la lista.'")

    async def open_product(self, request: OpenProductRequest) -> str:
        """Open a product's page on their screen and, with tab, its
        specifications, its details, its photos or its price. It returns at
        once; what the page shows, with its price and specs, comes back to you."""
        if (meta := self._meta_turn()) is not None:
            return meta
        path = self._product_known(request.path)
        if path is None:
            return self._unknown_product(request.path)
        here = same_product(self._in_front(), path)
        if here and request.tab is None:
            return (
                "Not moved: that product is already on their screen. "
                "Answer from read_screen's product."
            )
        if here and request.tab is not None:
            # The product is in front: only its section moves.
            queued = self._move("product.tab", TabArgs(tab=request.tab), "section", loads=False)
            if queued is not None:
                return queued
            return f"Showing its {request.tab}. " + self._sent_note("'Te muestro esa parte.'")
        queued = self._move("open_product", OpenProductArgs(path=path, tab=request.tab), "product")
        if queued is not None:
            return queued
        live = self._price_of(path)
        return f"Opening {live.name if live and live.name else path}. " + self._sent_note(
            "'Te abro el producto.'"
        )

    async def show_store(self, request: ShowStoreRequest) -> str:
        """Show one store on /nuestras-tiendas (opened first if needed): it
        scrolls to its card and rings it. It returns at once; what the card
        says comes back to you."""
        if (meta := self._meta_turn()) is not None:
            return meta
        store = self.kb.store(request.name)
        if store is None and self.kb.stores:
            listed = ", ".join(s.name for s in self.kb.stores)
            return f"Not done: no store matches '{request.name}'. The stores: {listed}."
        name = store.name if store is not None else request.name.strip()
        loads = self._path != "/nuestras-tiendas"
        queued = self._move("stores.show", StoresShowArgs(name=name), "store", loads=loads)
        if queued is not None:
            return queued
        where = f" ({store.address}, {store.city})" if store and store.address else ""
        if store is not None and store.hours:
            where += f"; hours: {store.hours}"
        if store is not None and store.phone:
            where += f"; phone: {store.phone}"
        return f"Showing the {name} store{where}. " + self._sent_note("'Te muestro la tienda.'")

    async def add_to_cart(self, request: AddToCartRequest) -> str:
        """Add a product to their cart, with the quantity they said. Only when
        they asked for it in their last words, or said yes to your offer. It
        opens the product first if needed and returns at once; the cart's
        answer comes back to you."""
        if (meta := self._meta_turn()) is not None:
            return meta
        if (no := self._unconsented("cart", "add it to the cart")) is not None:
            return no
        path = self._product_known(request.path)
        if path is None:
            return self._unknown_product(request.path)
        if not 1 <= request.qty <= _MOST_IN_CART:
            return f"Not added: the quantity is one to {_MOST_IN_CART}."
        queued = self._move(
            "commerce.cart_add", CartAddArgs(path=path, qty=request.qty), "cart_add"
        )
        if queued is not None:
            return queued
        live = self._price_of(path)
        return (
            f"Adding {request.qty} of {live.name if live and live.name else path} to their cart. "
            + self._sent_note("'Te lo agrego al carro.'")
            + _QUOTE_IS_THEIRS
        )

    def _cart_line(self, said: str) -> CartItem | None:
        """The line of their cart ``said`` names: by its path, else its name."""
        if self.cart is None:
            return None
        if product_sku(said) is not None:
            for item in self.cart.items:
                if item.path and same_product(item.path, said):
                    return item
        named = _match(said, [i.name for i in self.cart.items if i.name])
        return next((i for i in self.cart.items if i.name == named), None) if named else None

    async def update_cart_item(self, request: UpdateCartRequest) -> str:
        """Change how many of one line of their cart they have, or take it out
        with qty 0, on the cart page. Only when they asked for it, or said yes
        to your offer. It returns at once; the cart's answer comes back to
        you."""
        if (meta := self._meta_turn()) is not None:
            return meta
        if not 0 <= request.qty <= _MOST_IN_CART:
            return f"Not done: the quantity is 0 (take it out) to {_MOST_IN_CART}."
        if (no := self._unconsented("cart", "change their cart")) is not None:
            return no
        item = self._cart_line(request.line)
        if item is not None and item.path:
            path = self._product_path(item.path)
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
        """Open their cart (the /carro page), or close it."""
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

    def _on_quote_form(self) -> bool:
        """Whether the quote form is in front, or a move under way takes them there."""
        if self._path.startswith("/cotizacion") and (
            self.quote is None or self.quote.step == "form"
        ):
            return True
        if self.quote is not None and self.quote.step == "form":
            return True
        return any(r.move.id == "start_quote" for r in self.stage.running())

    async def start_quote(self) -> str:
        """Take them from the cart to the Formulario de cotización (the cart
        is opened first, then its Cotizar), and stop there. Only when they want
        to buy or ask for a quote, or said yes to your offer. It returns at
        once; the form's state comes back to you. Never Crear cotización."""
        if (meta := self._meta_turn()) is not None:
            return meta
        if (no := self._unconsented("quote", "ask for a quote")) is not None:
            return no
        if self.cart is not None and not self.cart.items and not self.cart.count:
            return "Not done: their cart is empty. Offer to find something first."
        if self._on_quote_form() and self._path.startswith("/cotizacion"):
            return (
                "Already there: the Formulario de cotización is in front. Offer to fill it in "
                "with them; the RUT and Crear cotización are theirs."
            )
        queued = self._move("start_quote", StartQuoteArgs(), "quote")
        if queued is not None:
            return queued
        return (
            "Opening the quote form from the cart. "
            + self._sent_note("'Te llevo al formulario de cotización.'")
            + " It stops on the form: then offer to fill it with them, a field or two at a "
            "time. The RUT and Crear cotización are theirs."
        )

    async def fill_quote(self, request: FillQuoteRequest) -> str:
        """Type what the visitor said into the Formulario de cotización: their
        name or company, phone, email, región, comuna, street, number, unit and
        notes. Only what they said, once they said yes or gave it to you for
        the form. Never the RUT, never Crear cotización. It returns at once;
        the form's state comes back to you."""
        if (meta := self._meta_turn()) is not None:
            return meta
        given = {k: " ".join(v.split()) for k, v in request.model_dump().items() if v and v.strip()}
        if not given:
            return "Not done: nothing to fill. Ask them for the next field."
        if (private := self._private_arg(*given.values())) is not None:
            return private
        if (no := self._unconsented("form", "fill in the quote form")) is not None:
            return no
        if not self._on_quote_form():
            return (
                "Not done: the quote form is not in front. When they want to buy, offer the "
                "quote, and start_quote after their yes; then fill it."
            )
        refused: list[str] = []
        if "phone" in given:
            digits = re.sub(r"\D", "", given["phone"])
            if not 8 <= len(digits) <= 12:
                refused.append(f"the phone '{given['phone']}' has {len(digits)} digits")
            else:
                given["phone"] = ("+" if given["phone"].lstrip().startswith("+") else "") + digits
        if "email" in given:
            email = given["email"].replace(" ", "").lower()
            if not _EMAIL.fullmatch(email):
                refused.append(f"'{given['email']}' is not an email address; ask them to spell it")
            else:
                given["email"] = email
        if "region" in given:
            given["region"] = _REGION_WORDS.sub("", given["region"]).strip() or given["region"]
        if refused:
            return "Not done: " + "; ".join(refused) + ". Ask them again."
        queued = self._move("fill_quote", FillQuoteArgs(**given), "form", loads=False)
        if queued is not None:
            return queued
        said = ", ".join(_FIELD_SAID.get(k, k) for k in given)
        out = f"Typing into the form: {said}. " + self._sent_note("'Lo anoto en el formulario.'")
        if "phone" in given or "email" in given:
            out += (
                " Read the phone back digit by digit, and the email letter by letter, if you "
                "have not yet, so they can check it."
            )
        return out + " The RUT and Crear cotización are theirs."

    async def focus_tab(self, request: TabRequest) -> str:
        """Bring another of the visitor's Agroplanet tabs to the front."""
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
        logger.info("agroplanet: language -> {} (asked)", request.language)
        return "ok"


#: An email address, once the spaces recognition put in it are out.
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}")
#: How a región is said around its name: "la Región del Maule" → "Maule".
_REGION_WORDS = re.compile(r"^(?:la\s+)?(?:regi[oó]n\s+(?:(?:de|del)\s+)?)?", re.IGNORECASE)
#: The most of one product a cart line takes from him.
_MOST_IN_CART = 50


#: Where one said option ends and the next begins: a comma (not the one in
#: "15,6"), "&", or "y"/"o"/"and"/"or" between words.
_SAID_SPLIT = re.compile(r"\s*(?:(?<!\d),|,(?!\d)|&|\b(?:y|o|and|or)\b)\s*", re.IGNORECASE)


def _said_parts(said: str | list[str] | None) -> list[str]:
    """Each option in what was said, in order: "Lubritek y Shell" → Lubritek, Shell; a
    list's items each split the same way."""
    items = [said] if isinstance(said, str) else list(said or [])
    out: list[str] = []
    for item in items:
        out.extend(p for part in _SAID_SPLIT.split(item) if (p := part.strip(" .")))
    return out


__all__ = [
    "MOVES",
    "SPEC",
    "AgroplanetBrain",
    "FocusTab",
    "LanguageChanged",
    "ReadRequest",
]
