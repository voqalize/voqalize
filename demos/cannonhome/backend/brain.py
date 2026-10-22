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

**The checkout is the visitor's.** He may add to the cart (it creates no
order); he never presses "Finalizar compra", never logs in, and never types a
RUT, an email, an address or a card.

**Never block on the UI.** A move dispatches and returns at once; the page
answers with ``command_done``, ``command_failed`` or the state it shows, and he
talks that through in the next short quiet spell, with tools off. One move at a
time: a move asked for while another is under way waits for its answer.

**The screen follows his voice.** He writes his moves into the reply as cues
(``{page: /politicas-de-despacho}``), at the start of the sentence they belong
to; the brain takes them out of the speech, checks them against the site, and
the page fires each as the voice reaches its sentence (:mod:`.cues`).

**Spanish or English, as the visitor chose or speaks.** The call opens in
Spanish, the store's language, and moves both legs of the call together.
"""

from __future__ import annotations

import dataclasses
import inspect
import math
import random
import re
import time
from collections.abc import AsyncGenerator
from datetime import date, datetime
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any, Literal
from zoneinfo import ZoneInfo

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
    say_line,
)
from voqalize_demos.acknowledge import (
    Acknowledger,
    Floor,
    Kind,
    Vocabulary,
    classify,
    hold_the_floor,
)

from voqalize.sdk import (
    Action,
    AppEvent,
    Finalize,
    RequestRejected,
    RTVIMessage,
    RTVIType,
    Session,
    Speech,
    SpeechChunk,
    SpeechStart,
    UserIdle,
    UserMessage,
)
from voqalize.sdk.voice import ToolChoice
from voqalize.sdk.wire import Config, IdleConfig, SttConfig, TtsConfig, Voice

from . import knowledge as kb
from .app_events import (
    CANNONHOME_EVENTS,
    CannonHomeEvent,
    CartState,
    CommandDone,
    CommandFailed,
    LanguageRequested,
    ListingShown,
    PageChanged,
    PricesRead,
    ProductShown,
    SearchSuggest,
    TabInfo,
    TabsChanged,
)
from .cues import CueKind, CueParser, RawCue, words
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

#: LOW, as Saatvik measured: at MINIMAL, Gemini mostly made the page call first
#: and wrote nothing; at LOW it writes the answer first and calls at the end.
THINKING = types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)
#: Gemini 3.8 Flash, as clini: first words in about two seconds, no spikes.
MODEL = "gemini-3.8-flash"
#: Cannon Home is in Chile: "hoy" and "mañana" are Santiago's.
TIMEZONE = ZoneInfo("America/Santiago")

# ─── Voice and timing ──────────────────────────────────────────────────────────

#: Javier's voice: one man, recorded once in English and once in Spanish.
VOICE = Voice.OMNIVOICE_JAVIER

_IDLE_MS = 20_000
_IDLE_NUDGES = 2
#: The idle window while a result the page produced waits to be talked through.
_TALK_THROUGH_MS = 2_000
#: A visitor thinking aloud about what they need pauses mid-sentence.
CANNONHOME_PATIENCE = PATIENCE + 2
#: A message this soon after the last one is the rest of the same thought.
_FRAGMENT_S = 4.0

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


def language_of(text: str, *, sure: bool = True) -> Lang | None:
    """The language ``text`` is plainly in, or ``None``. ``sure`` is for what
    the visitor said: Spanish needs two of its words (or its marks and one),
    English three of its own and none of Spanish's."""
    text = _CUE_TEXT.sub(" ", text)
    found = set(_LETTERS.findall(text.lower()))
    es = len(found & _SPANISH_WORDS) + (1 if _SPANISH_MARKS.search(text) else 0)
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
_VIDEO_AS_WORDS = re.compile(r"\bv deo(s?)\b")
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


def _anchor_for_voice(at: str) -> str:
    """A cue's anchor, in the page's words, for speech spelled :func:`for_the_voice`."""
    return " ".join(words(for_the_voice(_VIDEO_AS_WORDS.sub(r"video\1", at))))


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


class Cue(Action):
    """A move for the page to make when the voice reaches ``at`` — the first
    words of the sentence it belongs to (see :mod:`.cues`); empty ``at`` is
    when the voice stops. With ``path``, open that page of cannonhome.cl first
    (a full load); then ``heading`` scrolls to that heading and rings it,
    ``text`` rings the smallest element with those words, ``faq`` opens that FAQ."""

    at: str
    word: int = 0
    """Words of the unit before it, for a page that times cues by the clock."""
    path: str | None = None
    heading: str | None = None
    text: str | None = None
    faq: str | None = None


class FocusTab(Action):
    """Bring one of the visitor's Cannon Home tabs to the front."""

    tab_id: str


class LanguageChanged(Action):
    """The call's language moved, by the toggle, by voice or by
    ``set_language``: the widget's toggle follows at once."""

    language: Literal["en", "es"]


class SearchProducts(Action):
    """Type ``query`` into the store's search box (``input.amsearch-input``) at a
    human pace and let its suggestions open; report ``search_suggest``. With
    ``open_index`` (0-based: 0 is the first suggested product), open that
    product: the page then reports ``product_shown``."""

    query: str
    open_index: int | None = None


SortOrder = Literal["price_asc", "price_desc", "relevance", "newest"]


class FilterListing(Action):
    """Go to the listing at ``category_path`` (a full load, if it is not the one
    in front), then apply each filter given with its quick-filter pill — the
    option labels exactly as the listing writes them ("2 Plazas", "Blanco",
    "300", "100% Algodón") — one at a time, waiting for the grid; then the sort.
    Reports ``listing_shown``."""

    category_path: str
    size: str | None = None
    color: str | None = None
    threads: str | None = None
    material: str | None = None
    sort: SortOrder | None = None


ProductTab = Literal["descripcion", "especificaciones", "calificaciones", "fotos"]


class OpenProduct(Action):
    """Open the product at ``path`` (``/x.html``; a full load), then the tab
    named, or step through its photos for ``fotos``. Reports ``product_shown``."""

    path: str
    tab: ProductTab | None = None


class CheckPrices(Action):
    """Read the live price and stock of these products (at most six), with one
    same-origin POST to the store's GraphQL. Moves nothing. Reports ``prices_read``."""

    paths: list[str]


class AddToCart(Action):
    """On the product page at ``path`` (opened first if it is not in front), set
    the quantity to ``qty`` and press Agregar; wait for the cart drawer.
    Reports ``cart_state``. Never the checkout."""

    path: str
    qty: int = 1


class ShowCart(Action):
    """Open the cart drawer (``open``), or close it. Never the checkout."""

    open: bool = True


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


class FilterRequest(BaseModel):
    """Only the filters the visitor asked for."""

    category_path: str = Field(
        description="The listing's path, from the listings list: '/12-ropa-de-cama/20-sabanas'."
    )
    size: str | None = Field(default=None, description="'2 plazas', 'king', '1,5 plazas'…")
    color: str | None = Field(default=None, description="'blanco', 'gris'…")
    threads: str | None = Field(default=None, description="A thread count: '300'.")
    material: str | None = Field(default=None, description="'algodón', 'microfibra'…")
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


class ShowCartRequest(BaseModel):
    open: bool = Field(default=True, description="True to open the cart drawer, false to close it.")


# ─── The prompt ────────────────────────────────────────────────────────────────

_SITE_MAP_CHARS = 12000
_SECTIONS_PER_PAGE = 12
_LISTINGS_CHARS = 6000
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
    lines: list[str] = []
    size = 0
    for c in sorted(k.categories.values(), key=lambda c: (c.path.count("/"), c.path)):
        opts = "; ".join(
            f"{_FILTER_NAMES.get(v, v)}: {', '.join(labels[:10])}"
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
    return f"""You are {AGENT_NAME}, the voice guide on Cannon Home's online store, cannonhome.cl. Cannon Home is a Chilean home-textiles brand: sheets, duvets and duvet covers, pillows, quilts and blankets, towels and bathrobes, beds and mattresses. A visitor is shopping on the store right now and has called you from the corner of the page. You can see and move their screen: you type in the store's search, filter a listing, open a product and its tabs, read live prices, add to their cart and open the cart. You are warm, calm and practical — the friendly person in the store who knows every sheet, thread count and size, and helps them choose without pushing. Say the name as "Cannon Home".

# You narrate, and the screen follows your words
You are giving a guided walk through the store, like someone sitting beside the visitor with their screen in front of you both.
- Put a screen cue in your reply at the start of the sentence it belongs to. The page moves when your voice reaches that sentence. The visitor never hears a cue.
  - {{page: /path}} opens a page of the store, at its top: an information page from the site pages list, a listing from the listings list, or a product's path.
  - {{show: Heading}} scrolls to a heading on the page they are on, or are taken to by a page cue, and rings it. With other words on the page — a product's name, a price, a line of a policy — it rings those words.
  - {{faq: Question}} opens that FAQ and rings it. The FAQ can be on any page: it is found and opened there.
- Use headings and words exactly as the site pages list or the screen lines spell them. The store is in Spanish, so cues are in Spanish, also inside an English reply: "{{page: /politicas-de-despacho}} Deliveries arrive Monday to Saturday, with no exact hour."
- Never make up a heading or a path.
- One cue per sentence at most, and only where the screen should change. A cue goes before the sentence, never inside it.
- When the visitor asks where something is ("muéstrame", "where is that"), your reply starts with the cue for exactly that thing.
- A reply that calls a move (search_products, filter_listing, open_product, add_to_cart, show_cart) has no page cue: the move takes them there.
- Cues move pages; the moves below search, filter, open products and the cart. Nothing waits on a cue.

# A good turn moves them one step closer to the right product
1. Answer what they asked, first, in plain words, and show it as you say it.
2. Add the one thing that matters for them: the size for their bed, the thread count, the material, the weight of a towel.
3. End with one short, specific yes-or-no offer of the next step: "¿Te abro las de dos plazas?", "¿Te lo agrego al carro?", "Want me to show you the white ones?". Never "anything else?".
- A visit to the store has an order. Follow it from wherever the visitor is: what they need (which product, for which bed or bathroom), then narrow it (size, colour, material, thread count), then one product on their screen with its live price, then the cart — and they check out themselves.
- Ask about them only when the answer changes what you show next, and offer the choices: "¿Para una cama de dos plazas o king?", "¿Las prefieres de algodón o de microfibra?".

# How you sound
You are heard, not read, so keep it light and warm.
- A turn is three to five short sentences. Every sentence under fifteen words. Small, everyday words. One idea per sentence. One number per sentence.
- THE FIRST SENTENCE IS A FEW WORDS. The visitor hears nothing until your first sentence has been voiced, so open every reply with a sentence of two to six words that ends in a full stop, with the answer in it. A cue may come before it.
- Before most replies the visitor has already heard a short acknowledgement of mine — "Claro.", "A ver.", or in English "Happy to help.", "Let me see." — so never open with one: your first word is the answer. No "great question", no repeating their question back.
- Spoken words only, apart from cues: no lists, no markdown, no symbols, never an exclamation mark.
- Write every number, price and measure as spoken words. Prices are Chilean pesos: "$28.495" is "veintiocho mil cuatrocientos noventa y cinco pesos", in English "twenty-eight thousand four hundred and ninety-five pesos". The lines in square brackets give each price with how to say it. "300 hilos" is "trescientos hilos"; "50x70" is "cincuenta por setenta". Never say a SKU or a path.
- Lines in square brackets come from their screen, not the visitor: the page in front, a product, a listing, the cart. Never read them out; use them.
- Never list what is on screen: name two or three things, and point at the rest.
- Always answer. A reply with no words leaves the visitor in silence.

# Spanish or English
You speak Spanish as a native of Latin America, and English. The call starts in Spanish unless the visitor chose English.
- Answer in the language the visitor speaks to you. If they speak English, answer in English from that reply on; if they go back to Spanish, so do you. Your voice follows the language you write.
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
- The moves — search_products, filter_listing, open_product, check_prices, add_to_cart, show_cart — are not done when you call them: the page does them a moment later and tells you in square brackets. In the reply that calls one, say only what you are doing ("Te abro las sábanas king.", "Te lo agrego al carro."), never that it is done. When the page's answer comes, say what it says happened: what is done, and plainly what is not.
- One move at a time: when a tool says the page is still working on the last move, what you asked for follows by itself. Say so in a few words, and never call it again.
- Never promise more to come ("let me check"): nothing comes after it.
- A question about the call itself — "can I speak English?", "can you hear me?", "who are you?" — gets an answer and nothing else: no move, no page.

# Finding products
- find_products searches the whole catalogue from what they said, in either language — size, colour, material, thread count, towel weight, type — and returns each product's path, its attributes, and its line's other sizes and colours. When it had to drop a wish to find anything, it says which: tell them plainly what is different.
- Then show what fits: open_product for one product, filter_listing to show a listing narrowed the same way (a strong way to show a choice), or search_products to type their words in the store's search box, where the suggestions show live prices.
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
- filter_listing narrows a listing by tamaño, color, hilos or material, only with the options that listing has (the listings list below), and sorts it by price.

# The cart
- You may add a product to their cart when they ask, or say yes to your offer: add_to_cart with the product's path, the exact size and colour, and the quantity they said (one unless they said more). It opens the product first if it is not in front. Say what you are adding, never that it is added: the cart's answer comes in square brackets.
- show_cart opens their cart drawer; with open false it closes it. A cart line tells you what is in it and what is left for free shipping: say that once.
- CHECKOUT IS THEIRS, always. You never press "Finalizar compra", "Terminar pedido" or "Ir a pagar", never log in, and never type, ask for or repeat a RUT, an email, an address or card details. When they are ready, say they press "Finalizar compra" themselves.

# Tabs
- The visitor may have several store tabs open. Lines in brackets tell you which tabs are open and which is in front. "Go back to the other tab" is switch_tab with that tab's id.

# What you know
- Today is {today:%A, %d %B %Y}, in Santiago.
- Topics you can read with read_topic, when the knowledge below does not cover a question:
{_topics(k)}
- search_site finds an information page, section or FAQ by its words. Its results name the page and section, which you can then cue.

# CANNON HOME
{k.l1}

# The catalogue (category, how many products, what it carries)
{k.catalogue_index()}

# Listings (path — name, and the filter options each has)
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
#: The cart first, then a product page, then the categories.
_OPENERS: tuple[tuple[str, dict[Lang, str]], ...] = (
    (
        "/checkout/cart",
        {
            "es": "Te ayudo a revisar tu carro, o a encontrar algo más. ¿Qué necesitas?",
            "en": "I can help you go over your cart, or find something more. What do you need?",
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
    "cart_close": {"en": "I'm closing the cart.", "es": "Te cierro el carro."},
    "queued": {
        "en": "I'll do that as soon as the page is ready.",
        "es": "Lo hago apenas la página esté lista.",
    },
}

#: What a reply that only promises more says: nothing comes after it.
_PROMISE = re.compile(
    r"\b(?:just |one |un )?(?:moment|momento|momentito|second|segundo)\b"
    r"|\blet me (?:see|check|look)(?: (?:that|into it|at that))?\b|\bdéjame ver\b|\ba ver\b",
    re.IGNORECASE,
)

# ─── His nod ───────────────────────────────────────────────────────────────────

#: Only lines measured to come out in Javier's own voice (Explora's measured
#: set, held by clini): each is voiced on its own, always the same way, and
#: "Right." or "Un momento." came out as somebody else. Measure a new line first.
_ACK_LINES: dict[Lang, dict[Kind, tuple[str, ...]]] = {
    "en": {
        "request": ("Happy to help.", "Absolutely, let me do that.", "Sure thing."),
        "question": ("Let me see.", "Good question, let me see."),
        "correction": ("Got it, thanks for letting me know.", "Ah, I see what you mean."),
        "statement": ("Okay, that makes sense.", "Got it, thanks for letting me know."),
    },
    "es": {
        "request": (
            "Claro.",
            "Con gusto, ya lo hago.",
            "Por supuesto, déjame revisarlo.",
            "Claro, ahora mismo.",
        ),
        "question": ("A ver.", "Déjame revisarlo un momento."),
        "correction": ("Entendido, gracias por avisarme.", "Entendido, eso me ayuda."),
        "statement": ("Entendido, eso me ayuda.", "Claro.", "Entendido, gracias por avisarme."),
    },
}
#: Page loads are silence the nod covers (santanderarena's reason for 0.9);
#: clini's 0.75 here, since a catalogue read answers in the same turn.
ACK_RATE = 0.75
ACK_HOLD_AFTER_S = 5.75
HOLD_WITHOUT_NOD_S = 2.5
ACK_SORRY_AFTER_S = 15.0
_ACK_HOLD: dict[Lang, tuple[str, ...]] = {
    "en": ("Just a moment.", "One moment while I check that for you."),
    "es": ("Dame un momento mientras lo busco.", "Un momento mientras lo reviso para ti."),
}
_ACK_SORRY: dict[Lang, str] = {
    "en": "Sorry, that's taking a little longer.",
    "es": "Lo siento, está tardando un poco más de lo normal.",
}
#: A visitor's ordinary words about the store, so the reading trusts them.
_ACK_WORDS = Vocabulary(
    common=frozenset(
        # A word list reads as words, so it stays a split string.
        """cannon home tienda sábanas sábana sabanas toalla toallas plumón plumones funda fundas
        almohada almohadas cubrecama cubrecamas cobertor quilt frazada frazadas manta mantas
        cojín cojines colchón colchones cama camas bata batas alfombra piso hilos algodón
        microfibra poliéster polycotton tencel pluma plumas tamaño plaza plazas matrimonial
        king super color colores blanco blanca blancas gris azul beige negro precio precios
        oferta ofertas descuento carro carrito bolsa despacho envío retiro tiendas cambio
        cambios devolución cuotas medida medidas gramaje gramos especificaciones opiniones
        sheets sheet towel towels duvet duvets comforter cover pillow pillows blanket quilt
        bed mattress cotton thread count size queen white grey gray price prices cart
        shipping delivery returns store stores discount sale
        """.split()  # noqa: SIM905
    ),
)


@dataclasses.dataclass
class _LateFloor:
    """The floor for a turn that had no nod: a nod for what they said, late,
    else a hold line; then the apology. What :func:`hold_the_floor` reads."""

    ack: Acknowledger[Lang]
    nod: str | None
    hold_after_s: float
    sorry_after_s: float

    @property
    def sorry(self) -> dict[Lang, str]:
        return _ACK_SORRY

    def hold(self, spoken: Lang) -> str:
        return self.nod or self.ack.hold(spoken)


def _late_nod(text: str, spoken: Lang) -> str | None:
    """The nod :class:`Acknowledger` would have chosen, had the dice said yes."""
    kind = classify(text, _ACK_WORDS)
    lines = _ACK_LINES[spoken].get(kind) if kind else None
    return random.choice(lines) if lines else None


def _avatar_state(session: Session, state: Literal["WORKING"] | None) -> None:
    """The talking head's working latch: held until speech owed has played."""
    session.send_rtvi(RTVIType.SERVER_MESSAGE, {"type": "avatar", "cmd": "state", "state": state})


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


#: Paths the store always has, whether or not the crawl kept them as pages.
_FIXED_PAGES = frozenset({"/", "/checkout/cart"})
#: Paths no cue or move may open: the checkout, the account, the login.
_NEVER = re.compile(r"^/(?:checkout(?!/cart$)|customer|sales/order|paypal|braintree|mercadopago)")


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
            r"|delivery|deliver\b",
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
        (r"(?:mi |el |tu )?carr(?:o|ito)\b|mi bolsa|\bcart\b|basket", ("/checkout/cart",)),
    )
)
_ASKED_TAB = re.compile(r"\b(?:tabs?|pestanas?)\b", re.IGNORECASE)
#: Asking to add to the cart is a move, not the cart page.
_ADDS = re.compile(
    r"\b(?:agreg|anad|añad|pon(?:lo|la|er|me)|mete|echa|sum|add|put)\w*", re.IGNORECASE
)

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

#: The page moves, one at a time: a move sent while another loads races it.
_MOVES = frozenset(
    {"search_products", "filter_listing", "open_product", "add_to_cart", "show_cart"}
)
#: Every command whose answer the brain waits for, to talk it through.
_CONFIRMED_COMMANDS = _MOVES | {"check_prices"}
#: How long a move may take on the page before the next one stops waiting for
#: it. The store's ``load`` takes over 15 s (trackers); the adapter waits for
#: DOM content and its selectors, a few seconds.
_MOVE_TAKES_S = {
    "open_product": 25.0,
    "filter_listing": 20.0,
    "search_products": 20.0,
    "add_to_cart": 20.0,
    "check_prices": 10.0,
    "": 8.0,
}
#: A unit of his not reported played this long after it began is taken as done.
_PLAYOUT_MAX_S = 30.0
#: The state reports that answer a move, besides ``command_done``.
_ANSWERED_BY: dict[type[AppEvent], tuple[str, ...]] = {
    ProductShown: ("open_product", "search_products"),
    ListingShown: ("filter_listing", "search_products"),
    SearchSuggest: ("search_products",),
    PricesRead: ("check_prices",),
    CartState: ("add_to_cart", "show_cart"),
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
        f"{i.name} x{i.qty}" + (f", {_money(i.price, lang)} each" if i.price is not None else "")
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
    return note + " Finalizar compra is theirs to press.]"


# ─── The brain ─────────────────────────────────────────────────────────────────


class CannonHomeBrain(GeminiBrain):
    """One per session. Javier: Cannon Home's knowledge and catalogue, a mirror
    of the visitor's tabs and of every price their screen has shown, in Spanish
    or English."""

    def __init__(
        self,
        *,
        client: genai.Client,
        model: str = MODEL,
        knowledge: Knowledge | None = None,
    ) -> None:
        self.kb = knowledge if knowledge is not None else kb.KNOWLEDGE
        super().__init__(client=client, system_instruction=_prompt(self.kb), model=model)
        self._config = self._config.model_copy(update={"thinking_config": THINKING})
        self._heard_at = float("-inf")
        self.spoken: Lang = OPENING
        self._chosen = False
        self._confirm: str | None = None
        self._fallback = FallbackLine()
        self._ack = Acknowledger(
            _ACK_LINES,
            _ACK_HOLD,
            _ACK_SORRY,
            _ACK_WORDS,
            ACK_RATE,
            ACK_HOLD_AFTER_S,
            ACK_SORRY_AFTER_S,
        )
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
        #: Every price and stock their screen has reported this call, by path.
        self.prices: dict[str, Live] = {}
        self._cue_path: str | None = None
        self._idle_short = False
        self._nudges = 0
        self._backstop: str | None = None
        self._paged = False
        self._shown: str | None = None
        #: Whether this reply dispatched a page move: a page cue after it
        #: would race the load it started.
        self._moved = False
        self._heard: list[str] = []
        #: The moves sent and not yet answered, and the answers that came in
        #: since his last turn: talked through together, once, in the next
        #: short quiet spell.
        self._sent: dict[str, float] = {}
        self._outcomes: list[str] = []
        #: The move asked for while another was still under way on the page,
        #: sent once that one answers.
        self._queued: Action | None = None
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
        the screen read in, a nod over the model's thinking, and his own line
        over any dead air after it (:func:`hold_the_floor`)."""
        heard = None if self._chosen else language_of(msg.text)
        if heard is not None and heard != self.spoken:
            await session.configure(self._speaking(heard))
            logger.info("cannonhome: language -> {} (heard)", heard)
        self._talk = None
        # They spoke first: the page's answers are in the context as notes,
        # and he answers them with what they said.
        self._outcomes.clear()
        self._idle_deferred = False
        self._playing = 0
        self._nudges = 0
        self._heard = [*self._heard[-3:], msg.text]
        self._backstop = (
            None
            if asks_call_language(msg.text)
            else asked_page(msg.text, self.kb) or self._backstop
        )
        self._restore_idle()
        self._read_in_screen()
        now = time.monotonic()
        fragment, self._heard_at = now - self._heard_at < _FRAGMENT_S, now
        nod = None if fragment else self._ack.line(msg.text, self.spoken)
        floor: Floor[Lang] = self._ack
        if nod is not None:
            logger.info("cannonhome: ack {!r}", nod)
            async for event in say_line(self, nod):
                yield event
            _avatar_state(session, "WORKING")
        else:
            floor = _LateFloor(
                self._ack,
                None if fragment else _late_nod(msg.text, self.spoken),
                HOLD_WITHOUT_NOD_S,
                ACK_SORRY_AFTER_S,
            )
        working = nod is not None

        def answered() -> None:
            nonlocal working
            if working:
                working = False
                _avatar_state(session, None)

        try:
            turn = super().on_user_message(session, msg)
            async for event in hold_the_floor(self, floor, lambda: self.spoken, turn, answered):
                yield event
        finally:
            answered()

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
        if (ask := self._take_ask()) is not None:
            self._note(ask)
            return self._reply(session, ToolChoice.NONE)
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
        self, session: Session, tools: ToolChoice | None
    ) -> AsyncGenerator[Speech, None]:
        """The model's turn, with its cues taken out of the speech and sent to
        the page; ``tools`` limits it (``None``: any). A move with no words says
        its written line (:func:`landed`); a turn with nothing at all, or only a
        promise, is asked once more with tools off."""
        if (line := self._confirm) is not None:
            self._confirm = None
            async for event in say_line(self, line):
                yield event
        self._cue_path = self._path
        self._paged = False
        self._shown = None
        self._moved = False
        said = ""
        model = (
            super().respond(session) if tools is None else self.respond_with(session, tools=tools)
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

    async def _written(
        self, session: Session, turn: AsyncGenerator[Speech, None]
    ) -> AsyncGenerator[Speech, None]:
        """``turn``, with each unit held back until its first sentence is in,
        and both legs moved to the language it is in when it is not the call's."""
        held: list[Speech] = []
        text = ""

        async def release() -> AsyncGenerator[Speech, None]:
            nonlocal held, text
            written = language_of(text, sure=False)
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

    def _spelled(self, turn: AsyncGenerator[Speech, None]) -> AsyncGenerator[Speech, None]:
        """``turn``, with its speech spelled as the voice must read it."""

        async def spelled() -> AsyncGenerator[Speech, None]:
            async for event in turn:
                if isinstance(event, SpeechChunk):
                    respell = for_the_voice if self.spoken == "es" else names_for_the_voice
                    event = SpeechChunk(respell(event.text))
                yield event

        return spelled()

    async def _cued(self, turn: AsyncGenerator[Speech, None]) -> AsyncGenerator[Speech, None]:
        """``turn`` with every ``{page|show|faq: …}`` taken out of its text and
        sent to the page as a :class:`Cue`, anchored to the words before it."""
        parser = CueParser(self._auto_cues)
        try:
            async for event in turn:
                if isinstance(event, SpeechStart):
                    parser = CueParser(self._auto_cues)
                elif isinstance(event, SpeechChunk):
                    text, raw = parser.feed(self._with_backstop(event.text))
                    for cue in raw:
                        self._send_cue(cue)
                    if text:
                        yield SpeechChunk(text)
                    continue
                else:  # SpeechEnd
                    rest, raw = parser.flush()
                    for cue in raw:
                        self._send_cue(cue)
                    if rest:
                        yield SpeechChunk(rest)
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
        logger.info("cannonhome: the reply has no cue; showing {} first", path)
        return f"{{page: {path}}}{chunk}"

    def _send_cue(self, raw: RawCue) -> None:
        """Check a cue against the site and send it; one that names nothing
        real, or the checkout, is dropped and logged rather than reaching the page."""
        if self.spoken == "es" and raw.at:
            raw = dataclasses.replace(raw, at=_anchor_for_voice(raw.at))
        if self._moved:
            logger.info(
                "cannonhome: cue {} {!r} dropped: a move this reply loads the page",
                raw.kind,
                raw.value,
            )
            return
        cue = self._resolve_cue(raw)
        logger.info("cannonhome: cue {} {!r} at {!r} -> {}", raw.kind, raw.value, raw.at, cue)
        if cue is not None:
            self._paged = self._paged or raw.kind == "page"
            if raw.kind == "show":
                self._shown = cue.heading or cue.text
            self.session.dispatch(cue)

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
        self, sentence: str, index: int, placed: tuple[tuple[CueKind, str], ...]
    ) -> list[tuple[CueKind, str]]:
        """The moves a sentence of his needs and did not bring: the page its
        first sentence is about, and the section or name on the page it describes."""
        out: list[tuple[CueKind, str]] = []
        kinds = {k for k, _ in placed}
        pages = [p for k, v in placed if k == "page" and (p := self._known_path(v)) is not None]
        path = pages[-1] if pages else self._cue_path
        if (
            index == 0
            and not self._paged
            and not self._moved
            and "page" not in kinds
            and not kinds & {"show", "faq"}
            and self._shown is None
        ):
            asked = asked_page(sentence, self.kb)
            if (
                asked is not None
                and asked != self._path
                and self._known_path(asked) is not None
                and self._section_for(sentence, self._path) is None
            ):
                logger.info("cannonhome: he talks about {} with no cue; opening it", asked)
                out.append(("page", asked))
                path = asked
        self._cue_path = path
        if kinds & {"show", "faq"}:
            return out
        shown = self._section_for(sentence, path)
        if shown is not None and shown != self._shown:
            out.append(("show", shown))
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

    def _resolve_cue(self, raw: RawCue) -> Cue | None:
        if raw.kind == "page":
            path = self._known_path(raw.value)
            if path is None:
                return None
            self._cue_path = path
            return Cue(at=raw.at, word=raw.word, path=path)
        target = self.kb.page(self._cue_path) if self._cue_path is not None else None
        moved = self._cue_path is not None and self._cue_path != self._path
        if raw.kind == "faq":
            faqs = [f.q for f in target.faqs] if target else list(self._faqs())
            if not moved:
                faqs = list(dict.fromkeys([*self._faqs(), *faqs]))
            question = _match(raw.value, faqs)
            if question is None:
                found = self._faq_elsewhere(raw.value)
                if found is None:
                    return None
                self._cue_path, question = found
                return Cue(at=raw.at, word=raw.word, path=found[0], faq=question)
            path = self._cue_path if moved else None
            return Cue(at=raw.at, word=raw.word, path=path, faq=question)
        headings = (
            target.headings
            if moved and target
            else self._headings() or (target.headings if target else ())
        )
        heading = _match(raw.value, headings)
        text = None if heading else raw.value[:120]
        path = self._cue_path if moved else None
        return Cue(at=raw.at, word=raw.word, path=path, heading=heading, text=text)

    def _talk_now(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The one extra request a turn that said and moved nothing gets: tools
        declared, none callable."""
        return self.respond_with(session, tools=ToolChoice.NONE)

    async def _run(self, tool: Any, call: types.FunctionCall) -> types.Part:
        """Every tool takes one model, ``request``; Gemini sometimes sends its
        fields flat, which the SDK refuses. Wrap them before the call runs."""
        args = dict(call.args or {})
        if (
            tool is not None
            and args
            and "request" not in args
            and "request" in inspect.signature(tool).parameters
        ):
            logger.info("cannonhome: {} called with flat arguments; wrapping them", call.name)
            call = call.model_copy(update={"args": {"request": args}})
        return await super()._run(tool, call)

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
                note = _product_note(event, before, self.spoken)
                self._state_answers(event, f"the product page shows “{event.name or path}”")
                return note
            case ListingShown():
                self.listing = event
                for i in event.items:
                    self._remember(i.path, i.name, i.price, i.regular_price, None, None, "listing")
                count = f"{event.count} products" if event.count is not None else "products"
                self._state_answers(event, f"the listing shows {count}")
                return _listing_note(event, self.spoken)
            case SearchSuggest():
                self.suggest = event
                for s in event.items:
                    self._remember(s.path, s.name, s.price, None, None, None, "search")
                self._state_answers(
                    event, f"the search box shows {len(event.items)} suggestions for {event.query}"
                )
                return _suggest_note(event, self.spoken)
            case PricesRead():
                for i in event.items:
                    self._remember(
                        i.path, i.name, i.price, i.regular_price, i.in_stock, i.qty, "graphql"
                    )
                self._state_answers(
                    event, f"read {len(event.items)} live prices, {len(event.missing)} not found"
                )
                return _prices_note(event, self.kb, self.spoken)
            case CartState():
                self.cart = event
                for i in event.items:
                    if i.path:
                        self._remember(i.path, i.name, i.price, None, None, None, "cart")
                self._state_answers(event, f"the cart has {event.count or len(event.items)} items")
                return _cart_note(event, self.spoken)
            case CommandDone():
                detail = event.detail or "done"
                self._answered(event.command, f"{event.command} done: {detail}")
                return f"[The page confirms {event.command}: {detail}.]"
            case CommandFailed() if event.command == "cue":
                return (
                    f"[A screen cue of yours did not land ({event.why}). If the visitor "
                    "asks where it is, show it again; otherwise carry on.]"
                )
            case CommandFailed():
                if event.command in _CONFIRMED_COMMANDS:
                    self._talk = None
                    self._restore_idle()
                self._answered(event.command, f"{event.command} not done: {event.why}")
                return (
                    f"[Not done on the page ({event.command}): {event.why}. Tell the visitor "
                    "plainly and offer what you can do instead; never say it worked.]"
                )

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

    def _state_answers(self, event: CannonHomeEvent, what: str) -> None:
        """A state report that answers a move he sent is its answer."""
        for command in _ANSWERED_BY.get(type(event), ()):
            if command in self._sent:
                self._answered(command, f"{command} done: {what}")
                return

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
            "page": "a page of the store",
        }
        note = f"[The tab in front shows {kinds[p.kind]}: “{p.title or p.path}” ({p.path})."
        if p.headings:
            note += f" Its headings: {_clip(p.headings, _HEADINGS_IN_NOTE)}."
        if p.faqs:
            note += f" Its FAQs: {_clip(p.faqs, _FAQS_IN_NOTE)}."
        self._note(note + "]")

    def _note(self, text: str) -> None:
        self.append_to_context(types.Content(role="user", parts=[types.Part(text=text)]))

    def _holding_floor(self) -> bool:
        playing = self._playing > 0 and time.monotonic() - self._played_at < _PLAYOUT_MAX_S
        return self._turns > 0 or playing

    def _shorten_idle(self) -> None:
        """The short quiet spell, for something to talk through: set now, or,
        while he holds the floor, once he has finished."""
        if self._holding_floor():
            self._idle_deferred = True
            return
        self._idle_deferred = False
        if not self._idle_short:
            self._idle_short = True
            configure_soon(self.session, Config(idle=IdleConfig(timeout_ms=_TALK_THROUGH_MS)))

    def _floor_free(self) -> None:
        if self._idle_deferred and not self._holding_floor():
            self._shorten_idle()

    def _answered(self, command: str, outcome: str) -> None:
        """The page answered a move he sent: he says what it did in the next
        short quiet spell, unless the visitor speaks first. A move queued behind
        this one goes to the page now, or, if this one failed, is dropped and said."""
        if command not in self._sent:
            return
        del self._sent[command]
        if (queued := self._queued) is not None and not self._busy():
            self._queued = None
            name = queued.__voqal_action__
            if outcome.startswith(f"{command} done"):
                logger.info("cannonhome: {} answered; sending the {} queued", command, name)
                self._send(queued)
            else:
                outcome += f" (so {name}, asked for while it ran, was not sent)"
        self._outcomes.append(outcome)
        self._shorten_idle()

    def _busy(self) -> str | None:
        """The page move that has not answered yet, within its time."""
        now = time.monotonic()
        for command, until in self._sent.items():
            if command in _MOVES and until > now:
                return command
        return None

    def _send(self, action: Action) -> None:
        command = action.__voqal_action__
        if command in _CONFIRMED_COMMANDS:
            self._sent[command] = time.monotonic() + _MOVE_TAKES_S.get(command, _MOVE_TAKES_S[""])
        self.session.dispatch(action)

    def _move(self, action: Action, line: str) -> str | None:
        """Send a page move, or, while the last one is still under way, queue
        it to follow: ``None`` when sent, else what the tool says."""
        if (running := self._busy()) is None:
            self._queued = None
            self._moved = True
            self._send(action)
            landed(_LANDED[line][self.spoken])
            return None
        self._queued = action
        landed(_LANDED["queued"][self.spoken])
        logger.info("cannonhome: {} queued behind {}", action.__voqal_action__, running)
        return (
            f"Queued, not sent yet: the page is still working on the last move ({running}). It "
            "goes to the page as soon as the page answers that, and what it did comes back to "
            "you after. Say in a few words that you will do it as soon as the page is ready; "
            "never that it is done, and do not call it again."
        )

    def _take_ask(self) -> str | None:
        asks: list[str] = []
        if self._outcomes:
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
            self._idle_short = False
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
        """The refusal for a move called on a question about the call."""
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
        their screen; read live prices; add to the cart (never the checkout);
        move their tabs; switch language."""
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
            self.show_cart,
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
        queued = self._move(action, "search")
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
        size = _filter_value(cat, "tamano", request.size, refused, _size_label)
        color = _filter_value(cat, "color", request.color, refused, _color_label)
        threads = _filter_value(cat, "hilos", request.threads, refused, _threads_label)
        material = _filter_value(cat, "material", request.material, refused, _material_label)
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
        queued = self._move(action, "filter")
        if queued is not None:
            return queued
        applied = ", ".join(
            f"{n} {v}"
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
        queued = self._move(OpenProduct(path=path, tab=request.tab), "product")
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
        self._send(CheckPrices(paths=paths))
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
        queued = self._move(AddToCart(path=path, qty=request.qty), "cart_add")
        if queued is not None:
            return queued
        p = self.kb.product(path)
        return (
            f"Adding {request.qty} of {p.name if p else path} to their cart. "
            + self._sent_note("'Te lo agrego al carro.'")
            + " Finalizar compra is theirs to press."
        )

    async def show_cart(self, request: ShowCartRequest) -> str:
        """Open their cart drawer, or close it. Never the checkout."""
        if (meta := self._meta_turn()) is not None:
            return meta
        queued = self._move(
            ShowCart(open=request.open), "cart_show" if request.open else "cart_close"
        )
        if queued is not None:
            return queued
        return self._sent_note("'Te abro el carro.'" if request.open else "'Te cierro el carro.'")

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


def _filter_value(
    cat: Category | None,
    var: str,
    said: str | None,
    refused: list[str],
    label: Any,
) -> str | None:
    """The option label for what was said, as the listing writes it; a filter
    the listing lacks, or an option it does not list, is refused with what it has."""
    if not said or not said.strip():
        return None
    name = _FILTER_NAMES.get(var, var)
    if cat is not None and cat.filters and var not in cat.filters:
        refused.append(f"{cat.name} has no {name} filter (it has: {', '.join(cat.filters)})")
        return None
    options = cat.labels(var) if cat is not None else ()
    got = label(said, options)
    if got is None:
        listed = ", ".join(options) if options else "none"
        refused.append(f"{name} '{said}' is not an option of this listing (it lists: {listed})")
    return got


__all__ = [
    "AddToCart",
    "CannonHomeBrain",
    "CheckPrices",
    "Cue",
    "FilterListing",
    "FocusTab",
    "LanguageChanged",
    "OpenProduct",
    "SearchProducts",
    "ShowCart",
]
