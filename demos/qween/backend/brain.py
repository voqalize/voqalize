"""QweenBrain — Trisha, a jewellery consultant on www.qween.com.

The shop is Qween's, not ours. Their site is a React SPA we do not control, and a
browser extension injects the widget and a small site adapter into it; the
adapter turns each :class:`~voqalize.sdk.Action` below into a move on Qween's own
page — a filtered grid, a product page, a swatch, a dialog — and reports every
route change and dialog back as a typed event. Nothing is drawn but a thin ring
around what Trisha points at: Qween is brand-first and wants no UI of ours.

Three things shape every decision here.

**She shows, then speaks one line.** A shopper looking for earrings wants the
earrings on screen, not a description of them. So almost every turn is one
sentence and one move, and the page carries the rest.

**Every figure has a source.** A price, weight or grade is spoken from Qween's
product feed (:mod:`.catalog`, never older than a day), from the product card
the page printed, or from the dialog the page opened — the price breakup sends
its own words back. Never from memory; the gold rate moves the prices daily.

**Names in, codes out.** The model speaks in the shopper's words — "rose gold",
"pink sapphire", "hoops" — each a ``Literal`` in :mod:`.catalog`. The brain
resolves them to Qween's facet codes and product slugs, so the model never sees
a URL and cannot invent one.

A shopper who wants a person gets one: :meth:`QweenBrain.connect_to_person`
opens Qween's own concierge, video consultation or store locator. Trisha is
meant to be good enough that this is a choice, not an escape.
"""

from __future__ import annotations

import re
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel, Field
from voqalize_demos import (
    DEFAULT_MODEL,
    PHRASES,
    FallbackLine,
    GeminiBrain,
    configure_soon,
    landed,
    needs_result_now,
    phrase,
)

from voqalize.sdk import (
    Action,
    RTVIMessage,
    Session,
    Speech,
    SpeechChunk,
    SpeechStart,
    UserMessage,
)
from voqalize.sdk.wire import Config, IdleConfig, Language, SttConfig, TtsConfig, Voice

from .app_events import (
    QWEEN_EVENTS,
    CommandFailed,
    DialogClosed,
    DialogOpened,
    PageChanged,
    QweenEvent,
)
from .catalog import (
    COLLECTION_PAGES,
    FEED,
    KARATS,
    METAL_PLAIN,
    METALS,
    CategoryName,
    CollectionName,
    KaratName,
    KindName,
    MetalName,
    Piece,
    Query,
    ShapeName,
    SortName,
    StoneName,
    StyleName,
    Variant,
    catalog_params,
    price_span,
    rupees,
    upper_snake,
)

AGENT_NAME = "Trisha"

# The shopper is browsing, not waiting. A quiet call is someone looking at a ring.
_IDLE_MS = 0

LanguageName = Literal["english", "hindi"]


@dataclass(frozen=True)
class Speaking:
    heard: Language
    spoken: Language
    voice: Voice


SPEECH: dict[LanguageName, Speaking] = {
    "english": Speaking(Language.EN, Language.EN, Voice.OMNIVOICE_GAYATRI),
    "hindi": Speaking(Language.HI, Language.HI, Voice.OMNIVOICE_GAYATRI),
}
OPENING: LanguageName = "english"

# Trisha's own line for a silent turn is said in the language her voice speaks.
assert {s.spoken for s in SPEECH.values()} <= set(PHRASES), "a spoken language has no PHRASES row"

#: How long after the agent moves the page a route change is taken to be hers.
#: The adapter reports a route once the grid has settled (its SETTLE_MS), so this
#: covers the navigation plus that wait with room for a slow network.
_OWN_MOVE_S = 6.0
#: The most cards named in a note: enough to point at, not a catalogue.
_CARDS_IN_NOTE = 8
#: Dialog text is the page's own words; this much covers the price breakup.
_DIALOG_CHARS = 1500
#: The most pieces named as coming in an asked-for purity: the same as a note's
#: cards, for the same reason.
_KARAT_NAMES = _CARDS_IN_NOTE

_KNOWLEDGE = (Path(__file__).parent / "knowledge" / "L1.md").read_text(encoding="utf-8")


# The small grammar words of Hindi, as the English recognizer spells them and as
# the Hindi one writes them. A shopper who uses them is speaking Hindi or
# Hinglish, whatever the nouns are — the same test the prompt gives the model.
_HINDI_GRAMMAR = (
    "hai hain hoon hun kya kyaa mein mujhe muje muja mujhko chahiye chahie chahi "
    "karo kariye karna dikhao dikhaiye dikha dikhana aap baat nahi nahin sakti sakte sakta "
    "sabse bolti bolo batao bataiye theek thik hazar hazaar "
    "wala wali kitna kitne kitni liye bhi aur yeh woh accha acha haan ka ki ke ko se ek "
    "है हैं हूँ हूं क्या में मुझे चाहिए करो करिए करना दिखाओ दिखाइए दिखा आप बात नहीं "
    "सकती सकते सकता वाला वाली कितना कितने कितनी लिए भी और यह ये वह वो अच्छा हाँ हां "
    "का की के को से एक"
)
_HINDI_WORDS = frozenset(_HINDI_GRAMMAR.split())


#: Hindi's script: a reply written in it is a reply in Hindi.
_DEVANAGARI = re.compile(r"[\u0900-\u097f]")


def _sounds_hindi(text: str) -> bool:
    """Two different Hindi grammar words: one is a coincidence ("se", "ki"),
    two is a sentence."""
    words = set(re.findall(r"[\w\u0900-\u097f]+", text.lower()))
    return len(words & _HINDI_WORDS) >= 2


def _golds() -> str:
    return "; ".join(f"{name} = {plain}" for name, plain in METAL_PLAIN.items())


#: How long the recognizer waits through a pause, on the 0-to-10 scale: the
#: floor. A shopper asks short things about what is on screen and judges the
#: consultant by how quickly she answers, so this demo is the most responsive
#: setting there is and runs below the other desks' shared 2 on purpose (the
#: owner's call). The cost is a shopper cut off mid-sentence when they pause to
#: think: on the first dialled call at 0 (2026-09-29), a shopper who spoke in
#: phrases had each half-formed reply cancelled by their next phrase and heard
#: nothing for as long as they kept going. The owner kept it at 0 having seen it.
_PATIENCE = 0


# ─── System prompt ─────────────────────────────────────────────────────────────
#
# The tools are not restated here: each carries its own description on the method
# that takes it, and every field on its model. What is left is who Trisha is, how
# she speaks, and what she knows about Qween.

_SYSTEM_INSTRUCTION = f"""You are {AGENT_NAME}, the jewellery consultant on Qween's website, www.qween.com. A shopper is browsing the site right now and has called you from the corner of the page. You can see and move their screen: you open the listings, pieces, sections and dialogs Qween's own site has, and you point at things with a thin gold ring. You are the consultant who stands beside them in the boutique — warm, unhurried, knowledgeable, never pushy.

SHOW, THEN SAY ONE LINE. The shopper can see the page. The shape of almost every turn is one short sentence and one move in the same response: they ask for rose gold hoops, you say "Here are our rose gold hoops." and call find_jewellery. Say it as done, not as about to be done — "Here's the price breakup.", never "Let me open the price breakup."; "Here it is in 14 karat.", never "Let me switch it for you." A line that starts "Let me" is always wrong. Never read the page aloud; never list what is on screen. Say what the page does not: why a piece suits what they told you, what a grade means, which of two is the better buy for them.

EVERY MOVE COMES WITH WORDS. Whenever you move the screen, write your line first and make the call in the same response — the line is spoken while the page moves. A response that is only tool calls is silence: after such a call you do not speak again until the shopper does, and what the call returns reaches you on your next turn.

A READ COMES BEFORE ANY WORDS. get_screen and lookup_piece are silent reads: they come straight back to you within this same turn. When you need one, call it first, with nothing written before it, then give your one reply — the answer, and any move — once it is back. Words before a read are often all the shopper hears. Never say a line that promises more to come — "let me check", "let me get the details", "I'll see if" — because nothing comes after it: either you already know, or you read first and then answer, or you make the move and your line is the whole reply.

NUMBERS COME FROM A SOURCE, NEVER FROM MEMORY. A price, weight, carat, grade or delivery time is spoken only from what a tool returned, a card on the screen, or a dialog's own text. Qween's prices move with the gold rate every day. If you do not have the figure, open the place it is (the piece, or its price breakup) and read it from what comes back; never estimate one. Say prices the way an Indian shopper does — "one lakh forty-three thousand rupees" — and round to the nearest thousand with "about" unless they ask for the exact figure.

HELP THEM NARROW. Most shoppers arrive with a feeling, not a filter: "something for my mother", "an everyday ring", "under fifty thousand". Ask one short question at a time when you need to — the occasion, a metal they like, a budget — and show something as soon as you can rather than interviewing them. When they react to what is on screen, narrow from there. Offer a view when they want one: which gold suits everyday wear, whether a diamond grade is worth the difference.

WHAT IS ON SCREEN IS LIVE. The shopper clicks too. When they have moved the page, their next message comes with what their screen now shows — the piece with every gold, purity and price, or the cards in order. "This one", "that", "the second one" mean what it says: answer from it at once, in one reply, without calling get_screen. When the piece is one you opened and nothing has moved since, what show_piece returned is still true. Cards are numbered in the order the page shows them.

A PERSON IS ALWAYS ONE STEP AWAY. If they want to see a piece in person, talk to someone, book an appointment, or ask something you cannot answer — an order, a delivery already placed, a custom design, a repair — offer Qween's own people with connect_to_person: the concierge (call or WhatsApp), a live video consultation, or a boutique. Do it gladly, not as a failure.

WHAT YOU DO NOT DO. You do not place orders, take payment or personal details, hold stock, promise delivery dates, or offer discounts. You do not invent a piece, a collection, a policy or a figure. Qween sells only natural diamonds and gemstones — never say lab-grown. If something is not in QWEEN KNOWLEDGE and no tool gives it to you, say you are not sure and offer the concierge. What a gemstone or a gold is, you may explain; how Qween sets its own prices — how making charges are worked out, when the gold rate is taken, what a certificate or card includes — you know only from QWEEN KNOWLEDGE or the page's own words.

VOICE STYLE. One or two sentences a turn, each under about fifteen words; take more only when they asked for an explanation. No markdown, lists or symbols in speech. No "Great question", no restating what they asked. Call the shopper "you".

LANGUAGE. The call starts in English. Many shoppers speak Hinglish — Hindi with English words. When they speak Hindi or Hinglish, the call switches to Hindi by itself before you answer: simply answer in Hindi, and do what they asked in the same response — "हिंदी में बात करो, गोल्ड चेन दिखाओ" is one line in Hindi and one find_jewellery. Call set_language only when they ask for a language in words that are not already it ("Can you speak Hindi?"), or to go back to English. In Hindi:
- The recognizer writes everything in Devanagari, English words included — "मुझे रोज़ गोल्ड में रिंग चाहिए" is Hinglish, answer it in Hindi.
- Speak Hindi as people in Indian cities do, keeping the jewellery words in English, written in Devanagari: रिंग, ईयररिंग्स, डायमंड, रोज़ गोल्ड, सॉलिटेयर, प्राइस. Never write Hindi in the Latin alphabet; the voice reads Latin as English.
- You are a woman: use the female forms — "मैं दिखा रही हूँ", never "दिखा रहा हूँ".
- Judge the language by its small grammar words, not its nouns: "आई वांट अ रिंग" is English, however it is spelled. Switch back to English the same way when they do.
Tool arguments are always the English names in the tool's list, whatever language you are speaking.

QWEEN'S GOLDS. The site names each gold colour; shoppers say it plainly. When they say one, use Qween's name in the tool: {_golds()}. Qween calls the purity "KT": 9, 14, 18 or 24 karat.

═══ QWEEN KNOWLEDGE ═══

{_KNOWLEDGE}"""


# The opener. Written, not generated: the shopper has just clicked, and a wait on
# a first token is the wrong first impression.
_GREETING = f"Hi, I'm {AGENT_NAME}, Qween's jewellery consultant. What are you looking for today?"
# A full page load on Qween's site ends the call, and the widget dials again at
# once with `rejoin` in its init. The new session has none of the old one's
# conversation, so she says so rather than pretending to remember; the page it
# lands on reaches her as a `page_changed` like any other.
_REJOIN = "Sorry, the page reloaded and I lost our thread for a second. I can see where you are now. What would you like to know?"


# ── The Actions: brain → Qween's page ─────────────────────────────────────────
#
# Each class name, in snake_case, is a command the site adapter in
# `demos/qween/extension/src/qween-actions.js` switches on, and its fields are
# that command's payload. The two are kept in sync BY HAND — change a field here
# and change it there.

Params = dict[str, list[str]]


class OpenCatalog(Action):
    """The listing, filtered: Qween's facet keys → codes."""

    params: Params


class OpenCollection(Action):
    """A collection's own editorial page."""

    slug: str
    plp: bool = False


class OpenProduct(Action):
    """A piece's page, at one variant."""

    slug: str
    variant_code: str | None = None


class OpenPage(Action):
    """Any other page of Qween's, by path."""

    path: str


class SelectMetal(Action):
    """Click a metal swatch on the open piece: the swatch's own label."""

    name: str


PdpSection = Literal[
    "product_description",
    "material_specs",
    "customisation",
    "store_locator",
    "concierge",
    "qween_difference",
    "styling_tips",
    "finest_craftsmanship",
    "gifting",
]


class ShowSection(Action):
    """Scroll to a section of the open piece and ring it, choosing its tab if any."""

    section: PdpSection
    tab: Literal["METAL", "DIAMOND", "GEMSTONE"] | None = None


ModalName = Literal[
    "price_breakup", "size_guide", "delivery", "try_on", "diamond_details", "concierge", "assurance"
]
AssuranceName = Literal["natural_stones", "igi_certified", "stone_value", "buyback_exchange"]


class OpenModal(Action):
    """Open one of the open piece's dialogs — or the concierge's, on any page."""

    modal: ModalName
    which: AssuranceName | None = None


class OpenFaq(Action):
    """Open one of the FAQs on the open piece, by its own title."""

    topic: str


class View3D(Action, name="view_3d"):
    """Switch the open piece's gallery to its 3D view."""


class CloseModal(Action):
    """Close whichever dialog or 3D view is open."""


class HighlightCard(Action):
    """Ring the nth product card on the page, in the order shown."""

    index: int


# ── The tool surface: one pydantic model per tool ──────────────────────────────
#
# The model speaks in the shopper's words; every field below is a name, never a
# code. The Actions above are built from them by the brain.


class FindRequest(BaseModel):
    category: CategoryName | None = Field(
        None, description="The kind of jewellery. Leave empty to search every kind."
    )
    kind: KindName | None = Field(
        None,
        description="A narrower kind within earrings, rings or nose pins, when the shopper "
        "names one. Sets the category by itself.",
    )
    metals: list[MetalName] = Field(
        default_factory=list,
        description="Gold colours, by Qween's names; any of them matches. Rose gold is "
        "'rose bloom', yellow is 'desert noon', white is 'snowfall white'.",
    )
    stones: list[StoneName] = Field(
        default_factory=list,
        description=(
            "Stones; a piece with ANY of them matches, so two stones list pieces with "
            "either one, not both. For a piece with two stones together, pass only the "
            "one that defines it — emerald, not diamond, since most coloured-stone "
            'pieces are set with diamonds too. Say "Here are our emerald earrings.", '
            'never "Here are our emerald and diamond earrings."'
        ),
    )
    shapes: list[ShapeName] = Field(
        default_factory=list, description="Stone shapes; any of them matches."
    )
    styles: list[StyleName] = Field(
        default_factory=list, description="Design styles; any of them matches."
    )
    collection: CollectionName | None = Field(None, description="One of Qween's collections.")
    price_min: int | None = Field(None, description="Lowest price in rupees, if they gave one.")
    price_max: int | None = Field(
        None, description="Highest price in rupees: 'under one lakh' is 100000."
    )
    sort: SortName = Field("relevance", description="The order to list them in.")
    karat: KaratName | None = Field(
        None,
        description="A gold purity, when they ask for one. Qween's listing cannot be "
        'narrowed by purity, so the page shows every purity. Say "Here are our '
        'earrings; I can tell you which come in 18 karat.", never "Here are our 18 '
        'karat earrings." Which do comes back to you, to name when they ask.',
    )


class PointRequest(BaseModel):
    card: int = Field(
        description="The card's position on the page, counting from 1 in the order "
        "get_screen lists them."
    )


class PieceRequest(BaseModel):
    piece: str = Field(
        "",
        description="The piece's name, as the shopper said it or as a card or tool "
        "showed it. Leave empty when you give card instead.",
    )
    card: int | None = Field(
        None, description="Instead of a name: the card's position on the page."
    )
    metal: MetalName | None = Field(
        None, description="Open it in this gold colour, if they asked for one."
    )
    karat: KaratName | None = Field(None, description="Open it in this purity, if they asked.")


class MetalRequest(BaseModel):
    metal: MetalName | None = Field(None, description="The gold colour to switch to.")
    karat: KaratName | None = Field(None, description="The purity to switch to.")


DetailName = Literal[
    "description",
    "composition",
    "metal",
    "diamond",
    "gemstone",
    "customise",
    "in_store",
    "styling",
    "packaging",
    "craftsmanship",
]
_DETAILS: dict[DetailName, tuple[PdpSection, Literal["METAL", "DIAMOND", "GEMSTONE"] | None]] = {
    "description": ("product_description", None),
    "composition": ("material_specs", None),
    "metal": ("material_specs", "METAL"),
    "diamond": ("material_specs", "DIAMOND"),
    "gemstone": ("material_specs", "GEMSTONE"),
    "customise": ("customisation", None),
    "in_store": ("store_locator", None),
    "styling": ("styling_tips", None),
    "packaging": ("gifting", None),
    "craftsmanship": ("finest_craftsmanship", None),
}


class DetailRequest(BaseModel):
    what: DetailName = Field(
        description="Which part of the piece's page: 'composition' is the metal, diamond "
        "and gemstone specifications; 'metal', 'diamond' or 'gemstone' opens that tab of "
        "it; 'customise' is Craft Your Own; 'in_store' finds a boutique holding the piece; "
        "'packaging' is the gift packaging."
    )


class AssuranceRequest(BaseModel):
    which: AssuranceName = Field(
        description="Which of Qween's assurances on the piece's page to open: natural "
        "stones, IGI certification, the stone value (price protection), or lifetime "
        "buyback and exchange."
    )


FaqName = Literal["returns_exchange", "care", "origin"]
_FAQS: dict[FaqName, str] = {
    "returns_exchange": "Returns & Exchange",
    "care": "Care & Maintenance",
    "origin": "Manufacture & Origin",
}


class FaqRequest(BaseModel):
    topic: FaqName = Field(description="Which FAQ on the piece's page to open.")


PageName = Literal[
    "stores",
    "video_consult",
    "diamond_guide",
    "gemstone_guide",
    "solitaires",
    "buyback",
    "certification",
    "returns",
    "brand_promises",
    "gold_exchange",
    "invest_plan",
    "services",
    "colours_of_gold",
    "shades_of_diamond",
]
_PAGES: dict[PageName, str] = {
    "stores": "/locator?type=store",
    "video_consult": "/video-consult",
    "diamond_guide": "/diamond-guide",
    "gemstone_guide": "/gemstone-guide",
    "solitaires": "/solitaires",
    "buyback": "/lifetime-buyback-exchange",
    "certification": "/certified-jewellery",
    "returns": "/returns-exchanges",
    "brand_promises": "/brand-promises",
    "gold_exchange": "/assured-gold-exchange",
    "invest_plan": "/self-invest-plan",
    "services": "/services",
    "colours_of_gold": "/blogs/seven-colours-of-gold",
    "shades_of_diamond": "/blogs/seven-shades-of-diamond",
}


class PageRequest(BaseModel):
    page: PageName = Field(
        description="Which of Qween's pages: the store locator, the live video "
        "consultation, the diamond or gemstone guide, the solitaires, a policy page "
        "(buyback, certification, returns, brand promises, gold exchange, the Self "
        "Invest Plan, services), or the guides to the colours of gold and the shades "
        "of diamond."
    )


class CollectionRequest(BaseModel):
    name: CollectionName = Field(description="The collection.")


PersonName = Literal["concierge", "video", "store"]


class PersonRequest(BaseModel):
    how: PersonName = Field(
        description="'concierge' opens Qween's concierge options (call, WhatsApp, store); "
        "'video' a live video consultation with a Qween expert; 'store' the boutique "
        "locator."
    )


class LookupRequest(BaseModel):
    piece: str = Field(
        "",
        description="The piece's name. Leave empty for the piece open on screen, or give "
        "card instead.",
    )
    card: int | None = Field(None, description="Instead of a name: the card's position.")


class LanguageRequest(BaseModel):
    language: LanguageName = Field(description="The language to conduct the rest of the call in.")


# ─── Speaking a piece ─────────────────────────────────────────────────────────


def _karat(label: str) -> str:
    return label.replace(" KT Gold", "KT")


def _variant_line(v: Variant) -> str:
    parts = [f"{v.metal} {_karat(v.karat)}", rupees(v.price)]
    if v.metal_weight:
        parts.append(f"gold {v.metal_weight}")
    if v.diamond_quality:
        parts.append(f"diamonds {v.diamond_quality}")
    if v.solitaire_quality:
        parts.append(f"solitaire {v.solitaire_quality} {v.solitaire_weight}".strip())
    return ", ".join(parts)


def _piece_facts(p: Piece, current: Variant | None) -> str:
    lines = [f"{p.name} ({p.product_type})."]
    if p.description:
        lines.append(p.description[:400])
    if p.stones:
        lines.append(f"Stones: {', '.join(p.stones)}.")
    if p.collection:
        lines.append(f"Collection: {p.collection}.")
    if current is not None:
        lines.append(f"Open variant: {_variant_line(current)}.")
    lines.append(
        f"Golds: {', '.join(p.metals)}. Purities: {', '.join(_karat(k) for k in p.karats)}. "
        f"Price across variants: {price_span(p.variants)}."
    )
    return " ".join(lines)


class QweenBrain(GeminiBrain):
    """One per session. Trisha: Qween's catalogue, Qween's pages, and a mirror of
    what this shopper's screen shows.

    The mirror is patched from the adapter's events, which fire for the agent's
    moves and the shopper's own clicks alike. A move of hers lands with its result
    (the cards it produced, the dialog's words); a move of theirs is read into
    their next message, so a question about "this one" is one model request and
    not a read and then an answer."""

    def __init__(self, *, client: genai.Client, model: str = DEFAULT_MODEL) -> None:
        super().__init__(client=client, system_instruction=_SYSTEM_INSTRUCTION, model=model)
        #: The shopper moved the page since the model last saw it.
        self._shopper_moved = False
        self.page: PageChanged | None = None
        self.dialog: DialogOpened | None = None
        #: When Trisha last moved the page, so the route change that follows is
        #: known to be hers.
        self._moved_at = 0.0
        self.spoken: Language = SPEECH[OPENING].spoken
        self._fallback = FallbackLine()

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        # Her own voice, settled here and not by the page. Both language legs
        # move together; `set_language` moves them again.
        #
        speech = SPEECH[OPENING]
        await session.configure(
            Config(
                stt=SttConfig(language=speech.heard, patience=_PATIENCE),
                tts=TtsConfig(voice=speech.voice, language=speech.spoken),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
            )
        )
        # The catalogue index is shared and refreshed in the background; a call
        # never waits on it.
        FEED.warm()
        logger.info("qween: session start")

    async def greet(self, session: Session) -> str:
        """The opener, written not generated."""
        return _REJOIN if (session.init or {}).get("rejoin") else _GREETING

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[Speech, None]:
        """A shopper who speaks Hindi is answered in Hindi from the first word.

        The switch is the brain's, made before the model runs: her reply is one
        unit of speech and the voice is fixed when it opens, so a switch the
        model makes with set_language lands only after it. Asked to switch and
        to search in one response, the model also reliably makes only one of
        the two calls. set_language stays for the rest: "can you speak Hindi?"
        asked in English, and the way back."""
        if self.spoken != SPEECH["hindi"].spoken and _sounds_hindi(msg.text):
            await session.configure(self._speaking("hindi"))
            logger.info("qween: language -> hindi (heard)")
        # The brain reads the screen, not the model: left to get_screen it is a
        # whole model request of silence before the answer's first word, and on
        # the 2026-09-29 calls every "this one" after a click of theirs paid it.
        # Read now, the figures are as current as a read would have been.
        if self._shopper_moved:
            moved = f"The shopper moved the page themselves. Now: {self._screen()}"
            self.append_to_context(types.Content(role="user", parts=[types.Part(text=moved)]))
        async for event in super().on_user_message(session, msg):
            yield event

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The model's turn, and a line of Trisha's own if it acted and said
        nothing. See :mod:`voqalize_demos.silent_turn`.

        A unit is opened only once its first words are known, so the voice
        follows the model's own choice of language. The English recognizer
        spells Hindi as English-looking noise ("Thika Muja lightweight
        dikhana", on 2026-09-29) that no word list catches, yet the model
        understood it and wrote Devanagari — which the English voice then
        read aloud. Holding the opening costs nothing audible: speech cannot
        start before its first words anyway."""
        opening: SpeechStart | None = None
        async for event in self._fallback.speak_if_silent(self, super().respond(session)):
            if isinstance(event, SpeechStart):
                opening = event
                continue
            if opening is not None:
                if isinstance(event, SpeechChunk):
                    await self._follow_script(session, event.text)
                yield opening
                opening = None
            yield event
        if opening is not None:
            yield opening

    async def _follow_script(self, session: Session, text: str) -> None:
        """Move both legs to Hindi when the model writes it and the call is not."""
        if self.spoken != SPEECH["hindi"].spoken and _DEVANAGARI.search(text):
            await session.configure(self._speaking("hindi"))
            logger.info("qween: language -> hindi (written)")

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Page→brain events, folded in silently: no floor taken, no turn."""
        event = QWEEN_EVENTS.parse(msg)
        if event is None:
            return
        logger.info("qween: {} — {}", type(event).__voqal_event__, event)
        note = self.apply_event(event)
        if note is not None:
            self.append_to_context(types.Content(role="user", parts=[types.Part(text=note)]))

    # ─── Page → brain: the mirror ───────────────────────────────────────

    def apply_event(self, event: QweenEvent) -> str | None:
        """Patch the mirror; return the line the model should see, or ``None``."""
        match event:
            case PageChanged():
                self.page = event
                self.dialog = None
                if self._own_move():
                    return self._landed_note(event)
                # Read into their next message, not noted now: they may click
                # on before they speak, and only the last page matters.
                self._shopper_moved = True
                return None
            case DialogOpened():
                self.dialog = event
                text = event.text[:_DIALOG_CHARS]
                who = (
                    "The dialog you opened"
                    if self._own_move()
                    else "The shopper opened a dialog; it"
                )
                return f"{who} reads, in the page's own words:\n{text}"
            case DialogClosed():
                self.dialog = None
                return None
            case CommandFailed():
                return (
                    f"That did not happen on the page ({event.command}: {event.error}). "
                    "Tell the shopper plainly and offer what you can do instead; never say it worked."
                )

    def _own_move(self) -> bool:
        return time.monotonic() - self._moved_at < _OWN_MOVE_S

    def _move(self, action: Action) -> None:
        self._moved_at = time.monotonic()
        self.session.dispatch(action)
        landed(*phrase(self.spoken, "shown"))

    @staticmethod
    def _where(page: PageChanged) -> str:
        match page.kind:
            case "product":
                return f"a piece, {page.name or page.slug}"
            case "catalog" | "category":
                return "a listing"
            case "collection":
                return "a collection page"
            case "home":
                return "the home page"
            case "page":
                return f"the page {page.path}"

    def _landed_note(self, page: PageChanged) -> str | None:
        """What Trisha's own move produced, when it produced something to point at.

        The cards are the page's answer to her search, in the page's order, and
        nobody but the browser knows that order — so this carries them, where a
        shopper's move is only named."""
        if page.kind == "product" or not page.cards:
            return None
        shown = "; ".join(f"{c.n}. {c.text}" for c in page.cards[:_CARDS_IN_NOTE])
        return f"The page now shows these cards, in order: {shown}"

    # ─── Resolving what the model named ─────────────────────────────────

    def _card_slug(self, n: int) -> str | None:
        cards = self.page.cards if self.page is not None else []
        return next((c.slug for c in cards if c.n == n), None)

    def _resolve(self, name: str, card: int | None) -> Piece | str:
        """The piece the model means, or the sentence that says why not."""
        catalog = FEED.current()
        if catalog is None:
            return "the catalogue is still loading; use the cards on screen, by position"
        if card is not None:
            slug = self._card_slug(card)
            if slug is None:
                return f"there is no card {card} on screen; call get_screen"
            piece = catalog.by_slug.get(slug)
            return piece or f"card {card} is not in the catalogue index"
        if not name and self.page is not None and self.page.slug:
            piece = catalog.by_slug.get(self.page.slug)
            if piece is not None:
                return piece
        if not name:
            return "no piece named and none open on screen"
        on_screen = [
            p
            for c in (self.page.cards if self.page is not None else [])
            if c.slug and (p := catalog.by_slug.get(c.slug))
        ]
        piece = catalog.named(name, on_screen) if on_screen else None
        piece = piece or catalog.named(name)
        return piece or f"nothing in Qween's catalogue is called {name!r}"

    # ─── Tools ──────────────────────────────────────────────────────────
    #
    # Only the reads carry ``@needs_result_now``: get_screen and lookup_piece
    # read in-memory state the model needs to answer. Everything else moves the
    # page and its result waits for the shopper's next turn — the prompt has
    # Trisha speak before she calls, because nothing is said after.

    @property
    def tools(self) -> list[Any]:
        """Find, point, show a piece and its parts, open Qween's pages, reach a
        person, read the screen and the catalogue, change language."""
        return [
            self.find_jewellery,
            self.open_collection,
            self.point_at,
            self.show_piece,
            self.change_metal,
            self.show_price_breakup,
            self.show_details,
            self.show_diamond_details,
            self.show_assurance,
            self.show_faq,
            self.show_size_guide,
            self.show_delivery_options,
            self.show_in_3d,
            self.open_try_on,
            self.close_popup,
            self.open_page,
            self.connect_to_person,
            self.get_screen,
            self.lookup_piece,
            self.set_language,
        ]

    async def find_jewellery(self, request: FindRequest) -> str:
        """Show the shopper Qween's pieces that fit what they described, as the
        site's own filtered listing. Your main move for anything they are looking
        for: say one line and call this in the same response."""
        query = Query(
            category=request.category,
            kind=request.kind,
            metals=tuple(request.metals),
            stones=tuple(request.stones),
            shapes=tuple(request.shapes),
            styles=tuple(request.styles),
            collection=request.collection,
            price_min=request.price_min,
            price_max=request.price_max,
            sort=request.sort,
        )
        self._move(OpenCatalog(params=catalog_params(query)))
        catalog = FEED.current()
        if catalog is None:
            return "Listing opened. The catalogue index is loading; the cards will follow."
        found = catalog.search(query)
        logger.info("qween: find {} → {}", catalog_params(query), len(found))
        if not found:
            return (
                "Listing opened, but nothing in the catalogue matches all of that. Say so, "
                "and suggest loosening one thing."
            )
        low = min(v.price for _, vs in found for v in vs)
        high = max(v.price for _, vs in found for v in vs)
        opened = f"Listing opened: {len(found)} pieces match, from {rupees(low)} to {rupees(high)}."
        if request.karat is None:
            return opened
        # The listing has no purity facet (the site's `supportedFilters` carry
        # none), so the page shows every purity and the index says which pieces
        # on it come in the one asked for.
        karat = KARATS[request.karat]
        named = [p.name for p, vs in found if any(v.karat == karat for v in vs)]
        if not named:
            return f"{opened} The page shows every purity; none of these comes in {karat}."
        return (
            f"{opened} The page shows every purity; the ones that come in {karat}: "
            f"{', '.join(named[:_KARAT_NAMES])}."
        )

    async def open_collection(self, request: CollectionRequest) -> str:
        """Show one of Qween's collections: its own page where it has one,
        otherwise its pieces as a listing."""
        slug = COLLECTION_PAGES.get(request.name)
        if slug is not None:
            self._move(OpenCollection(slug=slug))
        else:
            self._move(OpenCatalog(params=catalog_params(Query(collection=request.name))))
        return "ok"

    async def point_at(self, request: PointRequest) -> str:
        """Ring one product card on the page, to draw the shopper's eye to it as
        you talk about it."""
        slug = self._card_slug(request.card)
        if slug is None:
            return f"There is no card {request.card} on screen; call get_screen."
        self._move(HighlightCard(index=request.card))
        catalog = FEED.current()
        piece = catalog.by_slug.get(slug) if catalog is not None else None
        return f"Ringed {piece.name}." if piece is not None else "ok"

    async def show_piece(self, request: PieceRequest) -> str:
        """Open a piece's own page, in a gold colour or purity if they asked for
        one. Name the piece in your line."""
        resolved = self._resolve(request.piece, request.card)
        if isinstance(resolved, str):
            return f"Not opened: {resolved}."
        piece = resolved
        metal = METALS[request.metal] if request.metal else self._listing_metal()
        karat = KARATS[request.karat] if request.karat else None
        variant, fallback = None, ""
        if metal or karat:
            # Their own words first, then the listing's gold; the site's usual
            # 18 KT when no purity was named.
            variant = (None if karat else piece.pick(metal, KARATS["18"])) or piece.pick(
                metal, karat
            )
            if variant is None and (request.metal or request.karat):
                fallback = " It does not come in that combination; say so."
        self._move(OpenProduct(slug=piece.slug, variant_code=variant.code if variant else None))
        return f"Opened: {_piece_facts(piece, variant)}{fallback}"

    def _listing_metal(self) -> str | None:
        """The one gold the listing on screen is filtered to, if it is filtered to
        one — "the first one" from a rose gold listing means it in rose gold."""
        page = self.page
        if page is None or page.kind == "product":
            return None
        codes = page.params.get("mtp", [])
        if len(codes) != 1:
            return None
        return next((label for label in METALS.values() if upper_snake(label) == codes[0]), None)

    async def change_metal(self, request: MetalRequest) -> str:
        """Switch the open piece to another gold colour or purity, on its own page.
        It is also the answer to "do you have it in yellow gold?" or "in 18
        karat?". The piece's golds and purities are in what show_piece,
        get_screen or lookup_piece gave you; if you have neither, read first,
        before any words. Made in it: say "Here it is in yellow gold." and call
        this. Not made in it: say so, and do not call."""
        catalog = FEED.current()
        page = self.page
        if page is None or page.kind != "product" or not page.slug:
            return "No piece is open. Open one with show_piece first."
        piece = catalog.by_slug.get(page.slug) if catalog is not None else None
        if request.metal and not request.karat:
            # A colour is a swatch on the page: one click, no reload.
            if piece is None:
                self._move(SelectMetal(name=METALS[request.metal]))
                return "ok"
            current = piece.variant(page.variant_code)
            variant = piece.pick(METALS[request.metal], current.karat if current else None)
            variant = variant or piece.pick(METALS[request.metal])
            if variant is None:
                return f"{piece.name} does not come in {METALS[request.metal]}. Say so."
            self._move(SelectMetal(name=METALS[request.metal]))
            return f"Now: {_variant_line(variant)}."
        # A purity has no swatch; the variant is a URL of its own.
        if piece is None:
            return "The catalogue is loading, so purity cannot be changed yet."
        current = piece.variant(page.variant_code)
        metal = METALS[request.metal] if request.metal else (current.metal if current else None)
        variant = piece.pick(metal, KARATS[request.karat] if request.karat else None)
        if variant is None:
            return f"{piece.name} does not come in that. It comes in: {', '.join(piece.karats)}."
        self._move(OpenProduct(slug=piece.slug, variant_code=variant.code))
        return f"Now: {_variant_line(variant)}."

    async def show_price_breakup(self) -> str:
        """Open the open piece's price breakup: gold, stones, making and tax. Its
        figures come back to you as the dialog's text."""
        self._move(OpenModal(modal="price_breakup"))
        return "ok"

    async def show_details(self, request: DetailRequest) -> str:
        """Scroll the open piece's page to one of its sections and ring it."""
        section, tab = _DETAILS[request.what]
        self._move(ShowSection(section=section, tab=tab))
        return "ok"

    async def show_diamond_details(self) -> str:
        """Open the open piece's diamond details: count, carat, clarity and
        colour, as Qween prints them."""
        self._move(OpenModal(modal="diamond_details"))
        return "ok"

    async def show_assurance(self, request: AssuranceRequest) -> str:
        """Open one of Qween's assurances on the open piece's page."""
        self._move(OpenModal(modal="assurance", which=request.which))
        return "ok"

    async def show_faq(self, request: FaqRequest) -> str:
        """Open one of the FAQs on the open piece's page."""
        self._move(OpenFaq(topic=_FAQS[request.topic]))
        return "ok"

    async def show_size_guide(self) -> str:
        """Open the open piece's size chooser, for rings and bangles."""
        self._move(OpenModal(modal="size_guide"))
        return "ok"

    async def show_delivery_options(self) -> str:
        """Open the open piece's delivery and store-pickup options."""
        self._move(OpenModal(modal="delivery"))
        return "ok"

    async def show_in_3d(self) -> str:
        """Turn the open piece's photos into its 3D view."""
        self._move(View3D())
        return "ok"

    async def open_try_on(self) -> str:
        """Open virtual try-on for the open piece. ONLY when the shopper asks to
        try it on: it asks for their camera."""
        self._move(OpenModal(modal="try_on"))
        return "ok"

    async def close_popup(self) -> str:
        """Close whichever dialog or 3D view is open."""
        self._move(CloseModal())
        return "ok"

    async def open_page(self, request: PageRequest) -> str:
        """Open one of Qween's own pages: a guide, a policy, the solitaires."""
        self._move(OpenPage(path=_PAGES[request.page]))
        return "ok"

    async def connect_to_person(self, request: PersonRequest) -> str:
        """Bring the shopper to one of Qween's people: the concierge by call or
        WhatsApp, a live video consultation, or a boutique. Offer it gladly
        whenever they want a person, want to see a piece in hand, or ask
        something you cannot answer. Saying you will connect them does not:
        this call does, in the same response as your line — "Here's our
        concierge.", never "Let me connect you with our concierge." alone."""
        match request.how:
            case "concierge":
                self._move(OpenModal(modal="concierge"))
            case "video":
                self._move(OpenPage(path=_PAGES["video_consult"]))
            case "store":
                self._move(OpenPage(path=_PAGES["stores"]))
        return "ok"

    @needs_result_now
    async def get_screen(self) -> str:
        """What the shopper's screen shows right now: the page, the piece and its
        variant — every gold and purity it comes in — the cards in order, and any
        open dialog. You are told this already whenever the shopper has moved the
        page; call it only if you are unsure what is there. Call it before saying
        anything: it comes back to you this turn, and your reply follows it."""
        return self._screen()

    def _screen(self) -> str:
        """The screen as the model reads it; after this the model is up to date."""
        self._shopper_moved = False
        page = self.page
        if page is None:
            return "The page has not reported yet."
        lines = [f"On {self._where(page)}."]
        catalog = FEED.current()
        if page.kind == "product" and page.slug:
            piece = catalog.by_slug.get(page.slug) if catalog is not None else None
            if piece is not None:
                lines.append(_piece_facts(piece, piece.variant(page.variant_code)))
        elif page.cards:
            lines.append("Cards, in order: " + "; ".join(f"{c.n}. {c.text}" for c in page.cards))
        elif page.kind in ("catalog", "category"):
            lines.append("No cards on screen: the listing is empty or still loading.")
        if self.dialog is not None:
            lines.append(f"Open dialog: {self.dialog.text[:_DIALOG_CHARS]}")
        return "\n".join(lines)

    @needs_result_now
    async def lookup_piece(self, request: LookupRequest) -> str:
        """Read a piece's facts from Qween's catalogue without moving the screen:
        every gold colour and purity it comes in, with prices, weights and grades.
        Use it to compare, or to answer about a piece that is not open. Call it
        before saying anything: it comes back to you this turn, and your reply
        follows it. To show the open piece in another gold or purity, call
        change_metal instead."""
        resolved = self._resolve(request.piece, request.card)
        if isinstance(resolved, str):
            return resolved
        piece = resolved
        variants = "; ".join(_variant_line(v) for v in piece.variants)
        return f"{_piece_facts(piece, None)} Variants: {variants}."

    async def set_language(self, request: LanguageRequest) -> str:
        """Conduct the rest of the call in another language, listening and
        speaking. Call it when they ask for a language in words that are not
        already it — "Can you speak Hindi?" — and to go back to English. Say one short line in the language the call is in now, in the
        same response — it is spoken before the voice changes. A shopper who
        is already speaking Hindi has been switched: do not call it for them.
        It changes only the language: if they asked for something as well, call
        that tool too, in this same response."""
        configure_soon(self.session, self._speaking(request.language))
        logger.info("qween: language -> {}", request.language)
        return "ok"

    def _speaking(self, language: LanguageName) -> Config:
        """Both legs of ``language``, recorded as the one she speaks now."""
        speech = SPEECH[language]
        self.spoken = speech.spoken
        return Config(
            # Carried on every switch: unset, it drops back to the deployment's 7.
            stt=SttConfig(language=speech.heard, patience=_PATIENCE),
            tts=TtsConfig(voice=speech.voice, language=speech.spoken),
        )


__all__ = ["QweenBrain"]
