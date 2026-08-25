"""OrderDeskBrain — MedSetu's B2B order desk.

A pharmacist taps Join on a 9 AM push notification and rattles off a bulk order in
Hindi. Every spoken line lands on screen as a free-text row, resolves against the
**real 20,148-SKU sqlite catalog** next door (``backend/search.py`` — deterministic
FTS + phonetic, not the model's imagination), and walks a visible state machine to a
confirmed SKU. Ambiguity becomes on-screen pills plus **one** short spoken question.
The pharmacist presses Confirm; the agent never does.

Three things are worth knowing about the shape of this file.

**The catalog is the authority, the model is the interface.** Unlike travel — where
the model invents the flights — nothing here is generated. ``add_items`` hands the
spoken text to :func:`search.resolve` and renders exactly what came back; the tool's
*return value* is a minimal-question briefing (which axes actually differ, the short
option labels already on screen, one guidance line) rather than a data dump the model
would be tempted to read aloud. That is the whole trick behind "4 Quin — drops या
ointment?": the brain computes the question, the model only phrases it.

**Twenty matches are never twenty pills** (DESIGN §7-bis). Up to four candidates the
row shows leaf pills and the model asks the one thing that differs. From five up, the
row carries its *whole* candidate set (the family, capped at 24) and the tool result
becomes a compact candidate table plus one instruction: call :meth:`OrderDesk.ask_choice`
with ONE question and 2-4 choices that split the set most evenly. The brain validates
that choice set — 2-4 choices, known codes, total coverage — and rejects a bad one with
a retriable error, so the *shape* of the question is guaranteed even though its wording
is the model's. Choices become :class:`DisambigChoice` pills (leaf when a choice is a
single SKU, a group otherwise); a group tap narrows ``candidate_codes`` in the browser
snapshot, the mirror follows on the next ``state_sync``, and the next question is asked
over what is left. Two rounds settle 24 candidates.

**Two scripts, one screen.** The call is Hindi, in Devanagari, spoken by a TTS that
mangles pharma brand names; the screen — and therefore every tool argument, every
catalog query — is English. That split is enforced, not merely requested: a
``field_validator`` rejects non-ASCII on the tool argument models (the coercion layer
turns the ``ValueError`` into a retriable tool error), and the plain-``str`` tools
run the same guard in-body and answer with the same message.

**Grounding beats memory.** The browser pushes its cart on every change
(``state_sync``, answered by :meth:`OrderDeskBrain.on_rtvi`) — including pill taps,
manual adds, quantity edits and deletes the pharmacist made with their thumb.
:meth:`OrderDeskBrain._ingest_state` folds that snapshot, plus a PENDING line naming
the rows still waiting on a question, into the context — appended once, only when the
picture actually changed. The brain's own item mirror is only the fallback for the
first beat, before the browser has spoken.

The six ``ui_command``s are :class:`voqalize.sdk.Action` subclasses, mirrored
one-for-one by ``frontend/src/uiCommands.ts``; DESIGN.md §3 is the written contract
for both halves.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from google.genai import types
from loguru import logger
from pydantic import BaseModel, ValidationInfo, field_validator
from voqalize_demos import DEFAULT_MODEL, GeminiBrain, GeminiProvider, hello_for

from voqalize.sdk import Action, RTVIMessage, RTVIType, Session
from voqalize.sdk.wire import Config, Language, SttConfig, TtsConfig, Voice

# The browser→brain messages (DESIGN §3). `state_sync` is the SDK's own convention
# and is handled by the base. Both of these are answered floor-free — no inference,
# no speech — so a thumb on the screen can never interrupt the call.
CATALOG_SEARCH = "catalog_search"
# The inline "Change variant" control on a matched row: show me this family's siblings.
LIST_VARIANTS = "list_variants"

LANGUAGE = "Hindi"

# ─── The prompt ────────────────────────────────────────────────────────────────

_INSTRUCTION = """You are the MedSetu order desk — a Hindi-speaking voice agent for India's largest B2B pharma distributor. It is nine in the morning. A pharmacist tapped Join on your order-taking notification and is about to rattle off today's stock order. YOU DRIVE THEIR SCREEN: every product they name lands as a row, resolves against the real MedSetu catalog, and turns green when it locks to one SKU.

WHO YOU ARE TALKING TO:
- One pharmacy owner. A PHARMACY CONTEXT block gives you everything: the store, the owner, what you discussed on earlier calls, their order history, their usual items, and TODAY'S CALL OBJECTIVE. Ground every sentence in it. Never ask for something the context already tells you.
- They are a trade customer in a hurry behind a counter, not a consumer. Brisk, familiar, respectful. No small talk beyond one line.

LANGUAGE — SPEECH:
- Speak Hindi, always in Devanagari script. English trade words are written in Devanagari too — never the Latin alphabet: "स्ट्रिप", "पैक", "स्क्रीन", "ऑर्डर", "कन्फर्म", "स्कीम", "स्टॉक".
- Example: "टेल्मा फोर्टी की तीस स्ट्रिप लगा दी। आगे बोलिए।" (टेल्मा, स्ट्रिप are English words in Devanagari.)
- Numbers and quantities in Hindi words, never digits: "तीस", "पचास", "एक सौ बीस". Prices likewise, and say "रुपये", never a symbol.
- Short sentences, under ten words. Never more than two short sentences in one turn. Start every reply with a tiny phrase so audio begins instantly.
- No markdown, no lists, no stage directions. Never narrate your own actions ("अब मैं जोड़ रही हूँ") — call the tool and say only what the pharmacist should hear.

LANGUAGE — TOOL ARGUMENTS ARE ENGLISH, ALWAYS:
- The screen is English and the catalog is English. EVERY string you pass to a tool — item text, query, note — is in clean English letters. Transliterate what you heard: "वोलिनी" → "volini", "चार क्विन" → "4 quin", "थायरोनॉर्म" → "thyronorm", "पैन फोर्टी" → "pan 40", "अबीवेज़" → "abiways".
- A tool argument containing Devanagari is rejected and you will have to call again. Do not let that happen.

THE TTS CANNOT PRONOUNCE MEDICINE NAMES. This is the single most important speaking rule:
- Minimise saying brand names out loud. The screen already shows them, spelled correctly.
- Point at the screen instead: "स्क्रीन पर ऑप्शन देखिए", "स्क्रीन पर दिख रहा है", "ऊपर वाला ऑप्शन".
- When a name must be spoken, say only the shortest brand root — "वोलिनी", "टेल्मा", "पैन" — never the full pack line, never the strength, never the manufacturer.
- NEVER read out a list of options, prices, pack sizes or SKU codes. Ever. That is what the screen is for.

THE MINIMAL QUESTION — the heart of this call:
- When an item is ambiguous, the tool tells you exactly which axes differ (`ask_about`) and puts the choices on screen. Ask ONE short question about ONLY those axes. Never about anything else, never twice.
- Worked example. He says "चार क्विन चाहिए". You call add_items with text "4 quin". The tool returns ask_about ["form"] and the options are already pills on his screen — eye drops and eye ointment.
    You: "चार क्विन — ड्रॉप्स या ऑइंटमेंट?"   (nothing else, and the pills are on screen)
    Him: "ड्रॉप्स वाला"
    You: [choose] "लग गया।"
  What you must NOT say: "चार क्विन में आई ड्रॉप्स पाँच एम एल एक सौ साठ रुपये और आई ऑइंटमेंट पाँच ग्राम एक सौ बयालीस रुपये…" — that is reading the screen aloud, and the TTS mangles it.
- If ask_about is ["pack_size"], ask only the size ("वोलिनी जेल — पचहत्तर या सौ ग्राम?"). If it is ["strength"], ask only the strength. If two families could match, ask which brand and let the cards on screen do the rest.
- If two brands sound alike over a phone line, do NOT guess. Ask him to repeat or confirm which one before it locks.

DISAMBIGUATION WHEN MANY SKUS MATCH — never twenty pills:
- Four or fewer choices need no machinery: the pills are already on his screen, so just ask the one short thing that differs (the rule above).
- Five or more, and the tool hands you a CANDIDATE TABLE instead of options. Never read it. Never try to show it all. Call ask_choice ONCE with one short English question and TWO TO FOUR choices that split those candidates as evenly as you can. The sharpest question is the one that eliminates the most candidates WHATEVER he answers — a choice that keeps twenty-three of twenty-four is a wasted turn.
- Group on the axis that actually partitions the list: the suffix line first (plain / H / AM / CT / BETA…), then form, then a strength band. Never split on pack size while a bigger axis still divides the list. Labels must be short, English and obviously different from each other.
- Every candidate must sit inside exactly one choice — the tool rejects a choice set that leaves a code uncovered, and you will have to call again.
- TWO ROUNDS AT MOST. Round one cuts twenty-four to a handful; round two is leaf pills he can tap, or he simply says which one and you call choose.
- Worked example — he says "टेल्मा" and the catalog hands you twenty-four TELMA SKUs.
    Round 1: ask_choice(item_id "li1", question "Which Telma line?", choices: "Plain Telma" / "Telma H (with diuretic)" / "Telma AM combos" / "Telma CT / Beta") — then say ONLY: "टेल्मा — कौन सी लाइन? स्क्रीन पर देखिए।"
    Him: "प्लेन वाली" → the tool told you that choice keeps six.
    Round 2: ask_choice(item_id "li1", question "Which strength?", choices: "20 mg" / "40 mg" / "80 mg") — then say ONLY: "कितने एम जी?"
    Him: "फोर्टी" → one or two SKUs left; call choose, or let him tap the pill.
  What you must NOT do: read the twenty-four names aloud, ask "कौन सा टेल्मा चाहिए?" with no choices, or ask about pack size first.
- After ask_choice, say THAT SAME question out loud in ONE short Hindi sentence. Do not list the choices aloud — they are pills on his screen.
- If he taps a group pill himself, your screen grounding shows fewer candidates on that row. Do not repeat the question — ask the NEXT one over what is left, or lock it with choose.

PACE — keep the order moving:
- The moment he names a product, call add_items. Do not wait for the previous one to resolve; do not ask a question in between. He can list six items in one breath — take them all in ONE add_items call with a list.
- Batch your questions. Let him finish his run of items, then at the natural pause ask about the ambiguous rows, one short question each. Never interrogate him after every item.
- Say a tiny line before or while calling a tool ("ठीक है", "लिख लिया") — never leave silence, never speak a whole sentence about what you are doing.

CORRECTIONS:
- By voice: "वोलिनी हटा दो" → remove_items. "तीस नहीं बारह कर दो" → set_quantity (never re-add). "ड्रॉप्स वाला" → choose. A better spelling or a clarified brand → refine_item.
- A QUANTITY TWEAK IS NEVER A RE-ADD. An absolute number ("बारह कर दो") is set_quantity; a relative one ("दस और डाल दो", "थोड़ा कम कर दो", "double कर दो") is adjust_quantity with a delta — plus ten is 10, "ten less" is -10. If he wants none of it, that is remove_items, not a delta down to zero.
- A VARIANT SWAP IS NEVER A RE-ADD EITHER. The brand is already right and only the variant is wrong ("ऑइंटमेंट वाला कर दो", "सौ ग्राम वाला", "फोर्टी कर दो") → change_variant on that row, with the variant in English ("ointment", "100 gm", "40 mg"). It stays inside the brand already on the row and keeps the quantity. Never remove the row and add it again — he loses his place on the screen.
- If you do not have the row id to hand, pass the product name instead of the id — every row tool accepts either. If the name matches two rows you will be told so; ask him which one rather than guessing.
- By hand: he also taps the screen — picks a pill, edits a quantity, deletes a row, adds something from the search bar. Those arrive in your CURRENT ORDER SCREEN grounding. Acknowledge in three words if it is worth acknowledging ("देख लिया") and NEVER redo what he already did himself.

THE REGULAR ORDER:
- If he says "मेरा रेगुलर ऑर्डर लगा दो" or similar, do NOT make him list it. Take his usual items from the PHARMACY CONTEXT (usual_items, else order_history) and add them in ONE add_items call, with the quantities from history. Then say in one line that his usual basket is on screen and ask what to change.

CONFIRMING — he confirms, not you:
- You have no confirm tool and no confirm authority. Your job is a fully matched cart: every row green, every quantity set.
- When the cart is fully matched, say one short line asking him to press Confirm: "सब लग गया — कन्फर्म कर दीजिए।"
- If a row is still amber or red, name what is missing in a few words instead, then fix it.
- Once the screen state says confirmed, close in ONE short line — order placed, delivery as usual, see you next time. Then stop.

STAY GROUNDED — you never invent anything:
- Never invent a SKU, a pack size, a price, a stock number or a scheme. The only product facts you may state are the ones a tool just returned to you or the screen state shows.
- If nothing matched, say so plainly and offer the search bar: "ये कैटलॉग में नहीं मिला — स्क्रीन पर सर्च कर के देखिए।" Never substitute a different brand on your own.
- A scheme banner appears on screen by itself when an item carries a deal. Mention it in one short line ("इस पर स्कीम चल रही है") — do not read the terms aloud.

A WORKED STRETCH OF THE CALL:
  Him: "टेल्मा फोर्टी तीस स्ट्रिप, और शेलकैल फाइव हंड्रेड बीस स्ट्रिप"
  You: [add_items with two items: "telma 40" qty 30, "shelcal 500" qty 20] "दोनों लग गए।"
  Him: "वोलिनी दे दो"
  You: [add_items "volini"] — tool says ask_about ["variant_label","pack_size"] — "वोलिनी — कौन सा, स्क्रीन पर ऑप्शन देखिए?"
  Him: "जॉइंट एक्सपर्ट, पचास ग्राम वाला"
  You: [choose] "लग गया। और कुछ?"
  Him: "बस इतना ही"
  You: "सब लग गया — कन्फर्म कर दीजिए।"

Open the call per TODAY'S CALL OBJECTIVE."""


# The header on the live cart `grounding()` appends to every model call.
_SCREEN_HEADER = "CURRENT ORDER SCREEN (authoritative — reflects manual edits): "

_PENDING_HEADER = (
    "PENDING (rows still waiting on you — ask ONE short question each, about the named axes only): "
)

_NOTHING_ON_SCREEN = "The order screen is empty — no items yet."

# Spoken instantly at session start, before the model has produced a token.
_HELLO = hello_for(LANGUAGE)

# Spoken if the generated opener fails (no key, model error) — the call still starts.
_FALLBACK_OPENER = "MedSetu से बोल रही हूँ। आज का ऑर्डर बताइए।"


# ─── The English-only guard ────────────────────────────────────────────────────
#
# The screen and the catalog are English; the conversation is Hindi. A model that
# passes what it heard straight through ("वोलिनी") would search the catalog for a
# string that cannot exist in it. So every tool string is checked, on both paths:
# the pydantic models raise (the SDK's coercion layer turns that into a *retriable*
# tool error the model reads and corrects — DESIGN §4's demo-able guardrail), and
# the plain-`str` tools run the same check in-body and return the same message.

_NON_ASCII = re.compile(r"[^\x00-\x7f]")


def _english_error(field: str, value: str) -> str:
    """The one message both guard paths use — it tells the model what to do next."""
    return (
        f"{field} must be written in English letters, not Devanagari or any other "
        f"script — the order screen and the product catalog are English. Re-send this "
        f"tool call with {field} transliterated into English, e.g. 'वोलिनी' -> 'volini', "
        f"'चार क्विन' -> '4 quin'. (got: {value!r})"
    )


def _check_english(field: str, value: str) -> str | None:
    """``None`` when ``value`` is clean ASCII; the error message otherwise."""
    return _english_error(field, value) if _NON_ASCII.search(value) else None


class _EnglishArgs(BaseModel):
    """Base for every tool-argument model: no non-ASCII in any string field.

    ``field_validator("*")`` covers each field as declared *and* each string inside a
    list field, so adding a field to a subclass cannot forget the guard. The
    ``ValueError`` becomes a ``CoercionError`` in
    :mod:`voqalize._framework.coerce`, which the ADK adapter hands back as a tool
    error result — the model sees the message and retries in-conversation."""

    @field_validator("*", mode="after")
    @classmethod
    def _english_only(cls, value: Any, info: ValidationInfo) -> Any:
        field = info.field_name or "argument"
        candidates = value if isinstance(value, list) else [value]
        for item in candidates:
            if isinstance(item, str) and (problem := _check_english(field, item)):
                raise ValueError(problem)
        return value


class SpokenItem(_EnglishArgs):
    """One product as it was heard, ready for the catalog.

    Note the sentinel defaults instead of ``| None``. ADK derives ``add_items``'
    schema from ``list[SpokenItem]``, and google-genai's automatic-function-calling
    schema builder **refuses any nullable field inside a nested model** ("Failed to
    parse the parameter items… consider manually parsing your function declaration").
    So "he didn't say one" is ``0`` / ``""`` here and is mapped back to ``None`` at
    the row (see :meth:`OrderDesk.add_items`) — the browser still receives the
    ``quantity: number | null`` its store reads."""

    text: str
    quantity: int = 0
    form_hint: str = ""
    strength_hint: str = ""


class Choice(_EnglishArgs):
    """One pill of an ``ask_choice`` question: a short English label and the candidate
    codes it keeps.

    Both fields are non-nullable — the same google-genai constraint that shaped
    :class:`SpokenItem` (no nullable field inside a nested list model) applies here,
    and a choice that keeps nothing is meaningless anyway."""

    label: str
    sku_codes: list[str]


# ─── Wire shapes (mirrored field-for-field by frontend/src/types.ts) ───────────
#
# Every field carries a default so a partially-populated row from the catalog
# module still renders — the browser reads a total shape either way (an `Action`
# emits all of its declared fields, `None` included).


class SkuWire(BaseModel):
    """One catalog SKU as the browser renders it — ``SkuView.wire()`` from
    ``search.py`` (DESIGN §2), validated into a shape this file owns."""

    code: str = ""
    name: str = ""
    family: str = ""
    variant_label: str = ""
    form: str = ""
    strength: str = ""
    pack_size: str = ""
    mrp: float = 0.0
    ptr: float = 0.0
    stock: int = 0
    manufacturer: str = ""
    scheme: str = ""


class FamilyWire(BaseModel):
    """One candidate brand family — the option card shown when 2-5 brands could match."""

    family: str = ""
    manufacturers: list[str] = []
    forms: list[str] = []
    sku_count: int = 0
    hint: str = ""


LineItemStatus = Literal["resolving", "multi_family", "multi_variant", "matched", "not_found"]

# The axes `resolve()` may report as differing, in the order a question reads best.
_AXES = ("variant_label", "form", "strength", "pack_size")

# How each axis is named to the model (it phrases the Hindi question from this).
_AXIS_WORD = {
    "variant_label": "variant",
    "form": "form",
    "strength": "strength",
    "pack_size": "pack size",
}

# DESIGN §7-bis. Up to four candidates are leaf pills and one small question; from five
# up the row carries its whole family and the model must ask a *splitting* question.
_QUESTION_FLOOR = 5
# The most candidates a row ever carries. 24 is TELMA, the widest family in the catalog,
# and two rounds of four-way questions settle it (log₄ 24 < 2.5).
_MAX_CANDIDATES = 24
# DESIGN §2: `resolve()` returns at most this many variants. A list this long is
# therefore *possibly truncated* — the only case where the row is re-stocked from the
# whole family (see `OrderDesk._widen`).
_VARIANT_CAP = 8
# A question is 2-4 pills. Two is the fewest that splits anything; beyond four the screen
# is a list again, which is the thing §7-bis exists to prevent.
_MIN_CHOICES, _MAX_CHOICES = 2, 4


class DisambigChoice(BaseModel):
    """One pill of a sharpest question — a leaf SKU or a group of them.

    ``sku_code`` is set only when this choice *is* a single SKU: the browser can then
    promote the row to ``matched`` on the tap, without asking anyone. Otherwise the tap
    narrows the row's ``candidates`` to ``narrows_to`` and the next question is asked
    over the remainder (DESIGN §7-bis)."""

    label: str = ""
    sku_code: str | None = None
    narrows_to: list[str] = []


class DisambigQuestion(BaseModel):
    """The question the model asked, as the screen renders it — 2-4 choices whose
    union covers every current candidate. Rendered *instead of* variants/families."""

    text: str = ""
    choices: list[DisambigChoice] = []


class LineItemView(BaseModel):
    """The full render state of one order row — the payload ``upsert_items`` carries.

    The frontend diffs by ``id`` and re-renders the row from this alone, so every
    action carries the *whole* row rather than a patch."""

    id: str
    spoken_text: str = ""
    query: str = ""
    quantity: int | None = None
    status: LineItemStatus = "resolving"
    sku: SkuWire | None = None
    family: str | None = None
    variants: list[SkuWire] = []
    families: list[FamilyWire] = []
    # The full candidate set (≤24) once a row is too big for leaf pills, and the
    # question currently on it. Both empty/None for the ≤4 case, which still renders
    # `variants` as leaf pills exactly as it always did.
    candidates: list[SkuWire] = []
    question: DisambigQuestion | None = None
    differing_axes: list[str] = []
    note: str | None = None
    source: Literal["agent", "manual"] = "agent"


# ─── The screen contract: one Action per ui_command (DESIGN §3) ────────────────


class UpsertItems(Action):
    """Add or update rows — the browser diffs by id and re-renders each."""

    items: list[LineItemView]


class RemoveItems(Action):
    """The agent dropped rows from the order."""

    ids: list[str]


class HighlightItem(Action):
    """Scroll to and pulse one row — the agent is asking about it."""

    id: str
    note: str | None


class ShowSearchResults(Action):
    """The floor-free answer to the manual search bar's ``catalog_search``."""

    query: str
    results: list[SkuWire]


class ShowVariants(Action):
    """The floor-free answer to a row's ``list_variants`` — the siblings of one
    matched SKU, for the inline "Change variant" strip.

    Deliberately *not* an ``UpsertItems``: the row is unchanged until he picks one,
    so this carries the family's SKUs beside the row rather than through it. The
    family is usually right and only the variant wrong, and deleting a row to re-add
    it is the painful path this exists to remove. ``differing_axes`` is what the
    strip labels its pills by, so a family that differs only on pack size reads
    "75 GM / 100 GM" and not the whole product name three times over."""

    item_id: str
    family: str
    results: list[SkuWire]
    differing_axes: list[str]


class OrderNote(Action):
    """One-line banner above the list — a scheme or stock callout."""

    text: str


# ─── Catalog → wire ───────────────────────────────────────────────────────────


def _sku_wire(sku: Any) -> SkuWire:
    """One :class:`search.SkuView` as the browser's ``SkuWire``.

    Prefers the catalog's own ``wire()`` (DESIGN §2's declared serializer); falls
    back to harvesting the declared fields off the object, so a dataclass that has
    not grown ``wire()`` yet still renders."""
    if hasattr(sku, "wire"):
        raw = sku.wire()
    elif isinstance(sku, dict):
        raw = sku
    else:
        raw = {name: getattr(sku, name, None) for name in SkuWire.model_fields}
    return SkuWire.model_validate({k: v for k, v in dict(raw).items() if v is not None})


def _family_wire(family: Any) -> FamilyWire:
    """One :class:`search.FamilyView` as the browser's ``FamilyWire``."""
    if hasattr(family, "wire"):
        raw = family.wire()
    elif isinstance(family, dict):
        raw = family
    else:
        raw = {name: getattr(family, name, None) for name in FamilyWire.model_fields}
    return FamilyWire.model_validate({k: v for k, v in dict(raw).items() if v is not None})


def _option_label(sku: SkuWire) -> str:
    """A short option string: the SKU minus its family name, plus the price.

    Over the 4 QUIN family this reads ``"EYE DROPS 5ML ₹160"`` — the same words the
    pill on screen carries, so the model can point at an option ("ऊपर वाला") without
    reading a catalogue entry aloud. The family is deliberately dropped: it is what
    every option in the list has in common."""
    bits = [str(getattr(sku, axis, "") or "").strip() for axis in _AXES]
    label = " ".join(bit for bit in bits if bit) or sku.name or sku.code
    return f"{label} ₹{sku.mrp:g}" if sku.mrp else label


def _candidate_line(sku: SkuWire) -> str:
    """One row of the candidate table the model groups by (DESIGN §7-bis).

    ``"J0031270 · TELMA 40 · TABLET · 40MG · 15'S · ₹161"`` — the code it must quote
    back in ``ask_choice``, then the axes it can partition on. Unlike
    :func:`_option_label` this keeps the name: with a whole family on the table, the
    suffix line inside the name ("TELMA H 40") is exactly what the sharpest question
    splits on."""
    bits = [sku.code, sku.name, sku.form, sku.strength, sku.pack_size]
    line = " · ".join(bit for bit in (str(b or "").strip() for b in bits) if bit)
    return f"{line} · ₹{sku.mrp:g}" if sku.mrp else line


def _differing_axes(skus: list[SkuWire]) -> list[str]:
    """The axes that actually take more than one value across ``skus``.

    ``resolve()`` reports this over the ≤8 variants it returned; once a row is expanded
    to its whole family the question engine needs it over *that* set instead."""
    return [
        axis
        for axis in _AXES
        if len({str(getattr(sku, axis, "") or "").strip() for sku in skus}) > 1
    ]


_WORD = re.compile(r"[a-z0-9]+")


def _describes(sku: SkuWire, terms: list[str]) -> bool:
    """Does this SKU answer for **every** word he said about the variant?

    An AND, deliberately: ``change_variant`` locks a row, and "forty" matching the
    400 MG pack because one of two terms landed is how the wrong medicine ships. Each
    term may be a whole axis word, the start of one ("oint" → OINTMENT), or a run
    inside the squashed text — that last one is what makes "100 gm" find a
    ``pack_size`` the catalog wrote as ``100GM``. A one-character term is only ever
    matched whole, so the "H" of the Telma H line does not match the h in every other
    word on the shelf."""
    text = " ".join(str(getattr(sku, axis, "") or "") for axis in (*_AXES, "name")).lower()
    tokens = set(_WORD.findall(text))
    squashed = text.replace(" ", "")
    return all(
        term in tokens
        or (len(term) >= 2 and (any(t.startswith(term) for t in tokens) or term in squashed))
        for term in terms
    )


# ─── One session's order screen ───────────────────────────────────────────────


class OrderDesk:
    """This session's cart mirror and the nine screen-driving tools.

    The tools are ordinary ``async`` methods — google-genai's automatic function
    calling drops the bound ``self`` when it builds their schemas, so session state
    on the instance costs nothing. Each one mutates the mirror, fires
    ``self._dispatch(...)`` (the RTVI ``ui-command`` the ``/orderdesk`` UI renders),
    and returns a compact briefing for the model.

    ``catalog`` is the ``backend/search.py`` module (DESIGN §2). It is imported
    **lazily**, on first use, so this brain imports — and its tests run — without the
    catalog build; tests inject a stub instead."""

    def __init__(self, catalog: Any | None = None) -> None:
        self._catalog = catalog
        # Set by OrderDeskBrain.on_session_start, once, before any tool can run —
        # the RTVI channel `_dispatch` sends on.
        self.session: Session | None = None
        # id → row. Insertion-ordered: the mirror renders in the order he said them.
        self.items: dict[str, LineItemView] = {}
        # The brain is the numbering authority for agent rows (manual adds are "m1"…,
        # minted by the browser), so li-ids are stable across screen and prompt.
        self._counter = 0
        # SKU codes whose scheme banner has already been shown, so a re-resolve of the
        # same row does not re-announce the same deal.
        self._noted: set[str] = set()
        # Rows the pharmacist narrowed himself by tapping a group pill (seen in the
        # browser snapshot, folded in by `absorb`). PENDING names them differently: the
        # question was answered, the row is smaller, and the NEXT question is due.
        self._narrowed: set[str] = set()

    @property
    def catalog(self) -> Any:
        """The deterministic catalog module — imported on first use (see above)."""
        if self._catalog is None:
            from . import search

            self._catalog = search
        return self._catalog

    # ─── mirror ─────────────────────────────────────────────────────────────

    def _next_id(self) -> str:
        self._counter += 1
        return f"li{self._counter}"

    def mirror(self) -> dict[str, Any] | None:
        """This brain's own picture of the cart, in the browser's own
        ``OrderSnapshot`` shape — the grounding fallback until (or without) a
        ``state_sync``. ``None`` when nothing has been ordered yet."""
        if not self.items:
            return None
        rows = [
            {
                "id": row.id,
                "spoken_text": row.spoken_text,
                "status": row.status,
                "sku_code": row.sku.code if row.sku else None,
                "sku_name": row.sku.name if row.sku else None,
                "pack_size": row.sku.pack_size if row.sku else None,
                "quantity": row.quantity,
                "source": row.source,
                "candidate_codes": [sku.code for sku in row.candidates],
            }
            for row in self.items.values()
        ]
        total = sum(
            (row.sku.mrp if row.sku else 0.0) * (row.quantity or 0) for row in self.items.values()
        )
        return {
            "screen": "order",
            "items": rows,
            "total_mrp": round(total, 2),
            "item_count": len(rows),
            "confirmed": False,
        }

    def absorb(self, live: dict[str, dict[str, Any]] | None) -> None:
        """Fold the browser's own per-row facts — the SKU, the quantity, the surviving
        candidates — back into the mirror.

        Trust is split by ownership. The **candidate set** is the brain's fact, so it
        only ever narrows: a group pill is tapped locally (DESIGN §7-bis — the frontend
        owns the narrow, so the screen never waits on a round trip) and the shrunken set
        arrives on the next ``state_sync``; seeing fewer codes than it holds, the mirror
        narrows to match and drops the question — it was answered by thumb — so the next
        model call is told to ask about *what is left* rather than repeating itself. A
        snapshot naming a code the row never had is ignored, not trusted.

        The **SKU and the quantity** are the browser's, because his thumb can change
        either: an inline variant swap, a pick out of the search panel, a typed number.
        A row whose snapshot names a different code is re-locked from the catalog and
        goes ``matched``, its candidates and question spent — otherwise a later
        ``change_variant`` would re-resolve from the family he already moved off, which
        is a wrong medicine, not a stale label. Anything the catalog cannot confirm is
        left alone: the mirror never invents a SKU the browser merely asserted."""
        if not live:
            return
        for row_id, seen in live.items():
            row = self.items.get(row_id)
            if row is None:
                continue
            quantity = seen.get("quantity")
            if isinstance(quantity, int | float) and not isinstance(quantity, bool):
                row.quantity = int(quantity) or None
            if self._relock(row, str(seen.get("sku_code") or "").strip()):
                continue  # re-locked: there is no candidate set left to narrow
            if not row.candidates:
                continue
            codes = {str(c) for c in (seen.get("candidate_codes") or []) if c}
            held = {sku.code for sku in row.candidates}
            if not codes or not codes < held:
                continue
            row.candidates = [sku for sku in row.candidates if sku.code in codes]
            row.question = None
            self._narrowed.add(row_id)

    def _relock(self, row: LineItemView, code: str) -> bool:
        """Move ``row`` onto the SKU the browser says it is on. ``True`` if it moved.

        The catalog is still the authority on what a code *is* — the browser supplies
        which one, this looks it up, and a code the catalog cannot confirm changes
        nothing at all."""
        if not code or (row.sku is not None and row.sku.code == code):
            return False
        try:
            found = self.catalog.sku_by_code(code)
        except Exception as exc:
            logger.warning("orderdesk: sku_by_code({!r}) failed: {}", code, exc)
            return False
        if found is None:
            return False
        row.sku = _sku_wire(found)
        row.family = row.sku.family or row.family
        row.status = "matched"
        row.variants, row.families, row.candidates = [], [], []
        row.question = None
        row.differing_axes = []
        self._narrowed.discard(row.id)
        return True

    def pending(self, live: dict[str, dict[str, Any]] | None) -> str | None:
        """The PENDING line: every row still short of a SKU, and what it is waiting for.

        ``live`` is the browser's own ``id -> {status, candidate_codes}`` map when a
        snapshot has arrived — so a row the pharmacist resolved by tapping a pill, or
        deleted, is not asked about again. A row with a question on it is *awaiting an
        answer* (never a fresh question); a row he narrowed by tapping a group is
        awaiting the NEXT question. ``None`` when nothing is pending."""
        bits: list[str] = []
        for row in self.items.values():
            status = row.status
            if live is not None:
                if row.id not in live:
                    continue  # deleted by hand
                status = str(live[row.id].get("status") or status)
            if status in ("matched", "resolving"):
                continue
            if row.question is not None:
                waiting = f"awaiting answer to: {row.question.text}"
            elif row.id in self._narrowed:
                waiting = f"narrowed to {len(row.candidates)} — ask the next question or choose"
            elif len(row.candidates) >= _QUESTION_FLOOR:
                waiting = f"{len(row.candidates)} candidates — call ask_choice with ONE question"
            elif status == "not_found":
                waiting = "not in catalog — offer the search bar or a different spelling"
            elif status == "multi_family":
                waiting = "which brand"
            else:
                waiting = (
                    ", ".join(_AXIS_WORD.get(a, a) for a in row.differing_axes) or "which variant"
                )
            bits.append(f"{row.id} ({row.spoken_text}): {waiting}")
        return _PENDING_HEADER + "; ".join(bits) if bits else None

    # ─── referring to a row ─────────────────────────────────────────────────
    #
    # Voice rarely has "li3" to hand. Every row-editing tool therefore takes either the
    # id or the product — and never *guesses* between two rows that both answer to it,
    # because the tools on the other side of this delete rows and swap medicines.

    def _rows_matching(self, ref: str) -> list[LineItemView]:
        """Every row a spoken reference could mean, most literal reading first.

        Three rungs, and the first that answers wins: the exact id, then a whole-name
        match on what he said / what the SKU is called / the brand, then containment
        ("telma" for the row he named "telma 40"). Case never matters — the screen
        shouts brand names in capitals and he does not."""
        key = (ref or "").strip()
        if not key:
            return []
        if (exact := self.items.get(key)) is not None:
            return [exact]
        needle = key.lower()
        names = {
            row.id: [row.spoken_text, row.sku.name if row.sku else "", row.family or ""]
            for row in self.items.values()
        }
        for test in (
            lambda field: field == needle,
            lambda field: needle in field,
        ):
            hits = [
                row
                for row in self.items.values()
                if any(test(field.lower()) for field in names[row.id] if field)
            ]
            if hits:
                return hits
        return []

    def _row_for(self, ref: str) -> LineItemView | None:
        """The one row ``ref`` names — ``None`` if nothing matches, and ``None`` if
        more than one does. Ambiguity is not a tie to break; it is a question to ask,
        and :meth:`_ref_error` is what asks it."""
        matches = self._rows_matching(ref)
        return matches[0] if len(matches) == 1 else None

    def _ref_error(self, ref: str) -> dict[str, Any]:
        """Why :meth:`_row_for` came back empty, as something the model can act on.

        The English guard rides here too: a Devanagari reference matches nothing, and
        "no such item 'वोलिनी'" would send the model looking for a row instead of
        transliterating."""
        if problem := _check_english("item_id", ref):
            return {"error": problem}
        matches = self._rows_matching(ref)
        if len(matches) > 1:
            return {
                "error": (
                    f"{ref!r} matches {len(matches)} rows on the order — ask him which one "
                    "he means, or use the row's id. Do not guess."
                ),
                "matching_ids": [row.id for row in matches],
                "known_ids": list(self.items),
            }
        return {"error": f"no such item {ref!r}", "known_ids": list(self.items)}

    # ─── catalog plumbing ───────────────────────────────────────────────────

    def _resolve_into(self, row: LineItemView, query: str, item: SpokenItem | None = None) -> None:
        """Run the deterministic resolver and fold its outcome into ``row``.

        A catalog failure (no db yet, a corrupt row) degrades to ``not_found`` rather
        than killing the turn — the pharmacist gets "not in the catalog", which is
        recoverable by voice, instead of silence."""
        row.query = query
        row.question = None
        row.candidates = []
        self._narrowed.discard(row.id)
        try:
            resolution = self.catalog.resolve(
                query,
                form_hint=(item.form_hint or None) if item else None,
                strength_hint=(item.strength_hint or None) if item else None,
            )
        except Exception as exc:
            logger.warning("orderdesk: resolve({!r}) failed: {}", query, exc)
            resolution = None
        if resolution is None:
            row.status = "not_found"
            row.sku = row.family = None
            row.variants, row.families, row.differing_axes = [], [], []
            return
        status = str(getattr(resolution, "status", "") or "not_found")
        row.status = (
            status if status in ("matched", "multi_variant", "multi_family") else "not_found"
        )
        sku = getattr(resolution, "sku", None)
        row.sku = _sku_wire(sku) if sku is not None else None
        row.family = getattr(resolution, "family", None) or (row.sku.family if row.sku else None)
        row.variants = [_sku_wire(s) for s in (getattr(resolution, "variants", None) or [])][:8]
        row.families = [_family_wire(f) for f in (getattr(resolution, "families", None) or [])][:5]
        row.differing_axes = [
            axis for axis in (getattr(resolution, "differing_axes", None) or []) if axis in _AXES
        ]
        self._widen(row, resolution)

    def _widen(self, row: LineItemView, _resolution: Any) -> None:
        """Give a big row its whole candidate set — the §7-bis fork.

        Under five candidates nothing happens at all: the pills are already on screen
        and one short question finishes the row. At five and above the row becomes a
        question, and its pills are cleared — twenty pills is the thing this mechanic
        exists to prevent.

        The set itself is the resolver's, *widened only when the resolver truncated it*.
        ``resolve()`` returns at most eight variants, so eight means "there may be more"
        and the row is re-stocked from ``skus_in_family`` with the whole family (TELMA:
        eight becomes twenty-four). Fewer than eight means the resolver exhausted its
        matches — "telma ct" is three of twenty-six, "volini gel" is two of ten — and
        widening would *undo* a narrowing the pharmacist already spoke. A ``multi_family``
        row takes the union of its candidate families instead. Everything is capped at
        :data:`_MAX_CANDIDATES`.

        A ``multi_family`` row is widened **whatever the union comes to**, and that is
        the one asymmetry here. Its brand cards are not a search shortcut, they are a
        control the pharmacist expects to *pick* with, and the browser can only narrow
        in place if it is holding that family's SKUs. Two brands of two SKUs each is
        exactly the case that used to arrive empty — cards that looked like a picker
        and behaved like a search box. What the *model* is told does not move with it:
        :meth:`_brief` reads the candidate table only from :data:`_QUESTION_FLOOR` up,
        so a small row still gets "ask which brand"."""
        floor = _QUESTION_FLOOR
        if row.status == "multi_variant":
            if len(row.variants) < _QUESTION_FLOOR:
                return
            truncated = len(row.variants) >= _VARIANT_CAP
            families = [row.family] if (row.family and truncated) else []
            candidates = list(row.variants) if not families else []
        elif row.status == "multi_family":
            families = [fam.family for fam in row.families if fam.family]
            candidates = []
            floor = 1  # the cards need their SKUs however few there are
        else:
            return
        seen = {sku.code for sku in candidates}
        for family in families:
            for sku in self._family_skus(family):
                if sku.code in seen:
                    continue
                seen.add(sku.code)
                candidates.append(sku)
                if len(candidates) >= _MAX_CANDIDATES:
                    break
            if len(candidates) >= _MAX_CANDIDATES:
                break
        if len(candidates) < floor:
            return
        row.candidates = candidates[:_MAX_CANDIDATES]
        row.variants = []
        row.differing_axes = _differing_axes(row.candidates)

    def _family_skus(self, family: str) -> list[SkuWire]:
        """Every SKU of one brand root, or nothing if the catalog cannot say."""
        try:
            return [_sku_wire(sku) for sku in (self.catalog.skus_in_family(family) or [])]
        except Exception as exc:
            logger.warning("orderdesk: skus_in_family({!r}) failed: {}", family, exc)
            return []

    def _dispatch(self, action: Action) -> None:
        """The one ``session.dispatch`` call site every tool method routes through."""
        assert self.session is not None, (
            "OrderDesk.session is unset — a tool ran before on_session_start"
        )
        self.session.dispatch(action)

    def _upsert(self, row: LineItemView) -> None:
        """Put one row on screen (add or replace) and keep the mirror in step."""
        self.items[row.id] = row
        self._dispatch(UpsertItems(items=[row]))

    def _note_scheme(self, row: LineItemView) -> None:
        """Fire the banner when a matched SKU carries a supplier scheme.

        Deterministic and brain-side on purpose: the deal is a fact of the catalog
        row, not something the model should decide to mention (or invent). It is
        announced once per SKU per call."""
        sku = row.sku
        if not sku or not sku.scheme or sku.code in self._noted:
            return
        self._noted.add(sku.code)
        self._dispatch(OrderNote(text=f"{sku.name} — scheme: {sku.scheme}"))

    def _brief(self, row: LineItemView) -> dict[str, Any]:
        """The minimal-question briefing for one row — what the model reads back.

        Deliberately NOT the row: no variant list, no manufacturer, no stock. Only
        the axes that actually differ, the short labels already on the pharmacist's
        screen, and one instruction. Everything the model needs to ask a five-word
        question, and nothing it could read aloud."""
        if row.status == "matched" and row.sku:
            return {
                "id": row.id,
                "status": "matched",
                "name": row.sku.name,
                "pack_size": row.sku.pack_size,
                "mrp": row.sku.mrp,
                "scheme": row.sku.scheme,
                "quantity": row.quantity,
            }
        # The floor, not merely "are there candidates": a small `multi_family` row now
        # carries its brands' SKUs so the browser can narrow a card in place, and that
        # must not turn a two-brand question into a candidate table for the model. Under
        # five the model still gets "ask which brand" / "ask which variant".
        if len(row.candidates) >= _QUESTION_FLOOR:
            return self._candidate_brief(row)
        if row.status == "multi_variant":
            axes = row.differing_axes or ["variant_label"]
            words = ", ".join(_AXIS_WORD.get(a, a) for a in axes)
            return {
                "id": row.id,
                "status": "multi_variant",
                "family": row.family,
                "ask_about": axes,
                "options": [_option_label(sku) for sku in row.variants[:8]],
                "guidance": (f"Ask ONE short question about: {words}. The options are on screen."),
            }
        if row.status == "multi_family":
            return {
                "id": row.id,
                "status": "multi_family",
                "family": None,
                "ask_about": ["family"],
                "options": [f"{fam.family} — {fam.hint}" for fam in row.families[:5]],
                "guidance": (
                    "Ask ONE short question about: which brand. The options are on screen."
                ),
            }
        return {
            "id": row.id,
            "status": "not_found",
            "query": row.query,
            "options": [],
            "guidance": (
                "Nothing in the catalog matched. Tell him it is not in the catalog and "
                "point at the search bar, or ask him to repeat the brand and call "
                "refine_item with a different English spelling. Never substitute another brand."
            ),
        }

    def _candidate_brief(self, row: LineItemView) -> dict[str, Any]:
        """The briefing for a row too big for pills: the table, and one instruction.

        This is the *only* place the model is shown many SKUs at once, and it is shown
        them to **partition**, not to recite: codes it must quote back in ``ask_choice``,
        and the axes it can split on. The guidance says both halves of §7-bis's quality
        bar — split evenly, on the axis that partitions — because the brain can validate
        the shape of a choice set but not its sharpness."""
        count = len(row.candidates)
        axes = ["family"] if row.status == "multi_family" else row.differing_axes
        return {
            "id": row.id,
            "status": row.status,
            "family": row.family,
            "ask_about": axes or ["variant_label"],
            "candidate_count": count,
            "candidates": [_candidate_line(sku) for sku in row.candidates],
            "guidance": (
                f"{count} candidates on file. Do NOT list them aloud and do NOT show "
                "them all. Call ask_choice with ONE question and 2-4 choices that split "
                "these most evenly — group by the axis that best partitions (suffix "
                "line / form / strength band). Prefer groups of similar size."
            ),
        }

    # ─── tools ──────────────────────────────────────────────────────────────

    async def add_items(self, items: list[SpokenItem]) -> dict[str, Any]:
        """Add every product the pharmacist just named to the order, and resolve each
        against the MedSetu catalog.

        Call this the MOMENT he names something — do not wait, do not ask first. If he
        lists several products in one breath, pass them all here in ONE call, in the
        order he said them.

        Each item's text is the product AS HEARD, transliterated into clean English
        letters: "volini", "4 quin", "telma 40", "thyronorm", "pan 40". No Devanagari.
        Do not add a pack size, form or strength he did not say — that is what the
        ambiguity flow is for. quantity is the number of strips/packs/bottles he asked
        for — leave it 0 if he did not say a number. Pass form_hint only if he actually
        said a form ("gel", "drops", "spray", "tablet", "syrup", "ointment"), and
        strength_hint only if he said one ("40 mg", "650", "50 mcg"); leave both empty
        otherwise. Never guess a quantity, a form or a strength.

        Each row appears greyed while it resolves, then settles to matched (green),
        multi_variant / multi_family (a question — the choices become pills or cards on
        his screen), or not_found. The return value tells you, per row, which axes
        actually differ — ask ONE short question about those and nothing else.

        Args:
            items: The products he just named, in spoken order.
        """
        briefs: list[dict[str, Any]] = []
        for item in items:
            row = LineItemView(
                id=self._next_id(),
                spoken_text=item.text,
                query=item.text,
                quantity=item.quantity or None,
                status="resolving",
            )
            # Land the row instantly (greyed, shimmering) so the screen keeps up with
            # his voice, THEN do the (fast, deterministic) catalog work.
            self._upsert(row)
            self._resolve_into(row, item.text, item)
            self._upsert(row)
            self._note_scheme(row)
            briefs.append(self._brief(row))
        return {"items": briefs}

    async def refine_item(self, item_id: str, query: str) -> dict[str, Any]:
        """Re-resolve one existing row with a better English query.

        For when the first spelling missed, or he clarified what he meant ("अबेविया
        नहीं, अबीवेज़") — pass the corrected English spelling as query. The row keeps
        its id and quantity and re-renders with the new outcome.

        Args:
            item_id: The row's id, e.g. "li3".
            query: The corrected product name in English letters, e.g. "abiways".
        """
        if problem := _check_english("query", query):
            return {"error": problem}
        row = self.items.get(item_id)
        if row is None:
            return {"error": f"no such item {item_id!r}", "known_ids": list(self.items)}
        row.status = "resolving"
        row.note = None
        self._upsert(row)
        self._resolve_into(row, query.strip())
        self._upsert(row)
        self._note_scheme(row)
        return self._brief(row)

    async def ask_choice(
        self, item_id: str, question: str, choices: list[Choice]
    ) -> dict[str, Any]:
        """Put ONE splitting question on a row that has too many candidates for pills.

        Use this whenever a tool handed you a candidate table instead of options. Write
        one short English question and two to four choices that divide those candidates
        as evenly as possible — group on the axis that actually partitions them (the
        suffix line first, then form, then a strength band), and give each group a short,
        obviously different English label. The sharpest question is the one that
        eliminates the most candidates whatever he answers.

        Every candidate code must appear in exactly one choice: a choice set that leaves
        a code out, invents a code, or runs past four pills is rejected and you will have
        to call again. A choice holding a single code becomes a leaf pill he can tap to
        lock the row.

        The choices become pills on his screen. After this returns, say the SAME question
        out loud in ONE short Hindi sentence and nothing else — never read the choices,
        never read the candidates. Two rounds of this settle even the widest family.

        Args:
            item_id: The row's id, e.g. "li1".
            question: The question as the screen shows it, short English, e.g. "Which Telma line?".
            choices: 2-4 groups, each a short English label plus the candidate codes it keeps.
        """
        if problem := _check_english("question", question):
            return {"error": problem}
        row = self.items.get(item_id)
        if row is None:
            return {"error": f"no such item {item_id!r}", "known_ids": list(self.items)}
        held = [sku.code for sku in row.candidates]
        if not held:
            return {
                "error": (
                    f"{item_id!r} has no candidate set to split — ask_choice is only for "
                    "rows whose tool result gave you a candidate table. This row's options "
                    "are already pills on his screen: ask the one short question about "
                    "what differs, then call choose."
                ),
                "status": row.status,
                "options": [sku.code for sku in row.variants],
            }
        if not _MIN_CHOICES <= len(choices) <= _MAX_CHOICES:
            return {
                "error": (
                    f"ask_choice takes {_MIN_CHOICES} to {_MAX_CHOICES} choices — you sent "
                    f"{len(choices)}. Merge or split your groups so they still cover all "
                    f"{len(held)} candidates in at most {_MAX_CHOICES} pills."
                ),
                "candidates": held,
            }
        if blank := [choice.label for choice in choices if not choice.sku_codes]:
            return {
                "error": f"these choices keep no candidates at all: {blank} — every "
                "choice must list the codes it keeps.",
                "candidates": held,
            }
        known = set(held)
        unknown = [code for choice in choices for code in choice.sku_codes if code not in known]
        if unknown:
            return {
                "error": (
                    f"these codes are not candidates of {item_id}: {sorted(set(unknown))}. "
                    "Use only the codes from this row's candidate table."
                ),
                "candidates": held,
            }
        covered = {code for choice in choices for code in choice.sku_codes}
        uncovered = [code for code in held if code not in covered]
        if uncovered:
            return {
                "error": (
                    f"these candidates are in no choice: {uncovered}. Every candidate must "
                    "sit in exactly one choice — widen a group or add one (still at most "
                    f"{_MAX_CHOICES})."
                ),
                "candidates": held,
            }
        # Valid. A choice holding exactly one code is a leaf: the browser can promote the
        # row to matched on the tap, without another round trip.
        row.question = DisambigQuestion(
            text=question.strip(),
            choices=[
                DisambigChoice(
                    label=choice.label,
                    sku_code=choice.sku_codes[0] if len(choice.sku_codes) == 1 else None,
                    narrows_to=list(choice.sku_codes),
                )
                for choice in choices
            ],
        )
        row.note = None
        self._narrowed.discard(row.id)
        self._upsert(row)
        return {
            "ok": True,
            "asked": question.strip(),
            "groups": [
                {"label": choice.label, "count": len(choice.sku_codes)} for choice in choices
            ],
            "guidance": (
                "Now ask this exact question aloud in one short Hindi sentence. Do not "
                "read the options aloud if they are visible as pills."
            ),
        }

    async def choose(
        self, item_id: str, sku_code: str, quantity: int | None = None
    ) -> dict[str, Any]:
        """Lock one row to a specific SKU — he answered your question by voice.

        The sku_code is the code of the option you were told about (the pills on his
        screen carry the same codes). If he also said a quantity in the same breath,
        pass it here rather than calling set_quantity after. If he taps the pill
        himself instead, the screen state will already show it matched — do not call
        this too.

        Args:
            item_id: The row's id, e.g. "li2".
            sku_code: The chosen SKU's catalog code.
            quantity: Strips/packs, if he said one.
        """
        if problem := _check_english("sku_code", sku_code):
            return {"error": problem}
        row = self.items.get(item_id)
        if row is None:
            return {"error": f"no such item {item_id!r}", "known_ids": list(self.items)}
        # Any code the row is still holding: a leaf pill, or — once a row has been
        # widened for a question — any of its 24 candidates, whichever round he answered.
        chosen = next(
            (sku for sku in (*row.variants, *row.candidates) if sku.code == sku_code), None
        )
        if chosen is None:
            try:
                found = self.catalog.sku_by_code(sku_code)
            except Exception as exc:
                logger.warning("orderdesk: sku_by_code({!r}) failed: {}", sku_code, exc)
                found = None
            chosen = _sku_wire(found) if found is not None else None
        if chosen is None:
            return {
                "error": f"{sku_code!r} is not one of this row's options",
                "options": [sku.code for sku in (row.variants or row.candidates)],
            }
        if quantity is not None:
            row.quantity = quantity
        return await self._lock(row, chosen)

    async def set_quantity(self, item_id: str, quantity: int) -> dict[str, Any]:
        """Change how many of one row he wants, to an exact number ("तीस नहीं बारह कर दो").

        Use this for every absolute quantity — never re-add an item he already has. If
        he said a *relative* change instead ("दस और", "थोड़ा कम"), use adjust_quantity.

        Args:
            item_id: The row's id, e.g. "li1", or the product name if you do not have
                the id, e.g. "telma 40". If the name matches two rows you will be told
                so — ask him which one instead of guessing.
            quantity: The new number of strips/packs/bottles.
        """
        row = self._row_for(item_id)
        if row is None:
            return self._ref_error(item_id)
        row.quantity = quantity
        self._upsert(row)
        return {"id": row.id, "status": row.status, "quantity": row.quantity}

    async def adjust_quantity(self, item_id: str, delta: int) -> dict[str, Any]:
        """Change how many of one row he wants, by a relative amount ("दस और डाल दो",
        "थोड़ा कम कर दो").

        delta is added to what the row already has: ten more is 10, ten fewer is -10.
        The result never goes below one — if he wants the item off the order entirely,
        that is remove_items, not a delta down to zero. Never re-add a row to change
        its quantity.

        Args:
            item_id: The row's id, e.g. "li1", or the product name if you do not have
                the id, e.g. "telma 40". If the name matches two rows you will be told
                so — ask him which one instead of guessing.
            delta: How many strips/packs to add (positive) or drop (negative).
        """
        row = self._row_for(item_id)
        if row is None:
            return self._ref_error(item_id)
        before = row.quantity or 0
        # Clamped, not floored at zero: a row on the order is a row he wants at least
        # one of, and "make it none" is a removal he should hear confirmed as one.
        row.quantity = max(1, before + delta)
        self._upsert(row)
        return {
            "id": row.id,
            "status": row.status,
            "was": row.quantity if before == 0 else before,
            "quantity": row.quantity,
        }

    async def change_variant(self, item_id: str, want: str) -> dict[str, Any]:
        """Swap one row onto a different variant of the SAME brand, keeping its quantity.

        This is the "brand right, variant wrong" correction — "ऑइंटमेंट वाला कर दो",
        "सौ ग्राम वाली", "फोर्टी कर दो" — and it is always better than removing the row
        and adding it again. want is only the part that changes, in English: "ointment",
        "100 gm", "40 mg", "H 80", "spray". Do not repeat the brand name in it.

        It cannot leave the brand already on the row, by construction — if he actually
        named a different brand, that is add_items or refine_item, not this. If several
        variants match, they become choices on his screen and you ask one short question
        about what still differs. If none match, the row is left exactly as it was and
        you are told which variants the brand actually has — say it did not match and
        ask again. It never quietly keeps the old SKU while sounding like it changed.

        Args:
            item_id: The row's id, e.g. "li1", or the product name if you do not have
                the id, e.g. "volini". If the name matches two rows you will be told so.
            want: The variant he asked for, in English letters, e.g. "ointment", "100 gm".
        """
        if problem := _check_english("want", want):
            return {"error": problem}
        row = self._row_for(item_id)
        if row is None:
            return self._ref_error(item_id)
        family = row.family or (row.sku.family if row.sku else "")
        if not family:
            return {
                "error": (
                    f"{row.id} has no brand settled yet, so there is nothing to swap "
                    "within — resolve it first with refine_item or choose."
                ),
                "status": row.status,
            }
        # The family's own SKUs, never a fresh resolve: a resolve on "ointment" could
        # land on any brand that makes one, and this tool exists to stay put.
        siblings = self._family_skus(family)
        terms = _WORD.findall(want.lower())
        hits = [sku for sku in siblings if _describes(sku, terms)] if terms else []
        if not hits:
            return {
                "error": (
                    f"nothing in {family} matches {want!r} — the row is UNCHANGED and "
                    f"still shows what it showed. Tell him that variant is not there, or "
                    "ask again using the axes below and call change_variant once more."
                ),
                "id": row.id,
                "family": family,
                "ask_about": _differing_axes(siblings) or ["variant_label"],
                "options": [_option_label(sku) for sku in siblings[:_VARIANT_CAP]],
            }
        if len(hits) == 1:
            return await self._lock(row, hits[0])
        # Several: hand the row back to the normal ambiguity machinery — leaf pills under
        # the floor, a candidate table and one splitting question above it.
        row.status = "multi_variant"
        row.sku = None
        row.family = family
        row.families = []
        row.question = None
        row.note = None
        self._narrowed.discard(row.id)
        if len(hits) < _QUESTION_FLOOR:
            row.variants, row.candidates = hits, []
        else:
            row.variants, row.candidates = [], hits[:_MAX_CANDIDATES]
        row.differing_axes = _differing_axes(row.variants or row.candidates)
        self._upsert(row)
        return self._brief(row)

    async def _lock(self, row: LineItemView, sku: SkuWire) -> dict[str, Any]:
        """Put one row on one SKU and clear everything the ambiguity left behind.

        The quantity is deliberately untouched: every path here is a correction to
        *what* he is buying, never to how much of it."""
        row.status = "matched"
        row.sku = sku
        row.family = sku.family or row.family
        row.variants, row.families, row.candidates = [], [], []
        row.question = None
        row.differing_axes = []
        row.note = None
        self._narrowed.discard(row.id)
        self._upsert(row)
        self._note_scheme(row)
        return self._brief(row)

    async def remove_items(self, item_ids: list[str]) -> dict[str, Any]:
        """Drop one or more rows from the order ("वोलिनी हटा दो").

        Args:
            item_ids: The rows to remove — ids, e.g. ["li4"], or product names if you
                do not have the ids, e.g. ["volini"]. If one of them matches two rows,
                NOTHING is removed and you are told which — ask him which one he meant.
        """
        rows: list[LineItemView] = []
        for ref in item_ids:
            row = self._row_for(ref)
            if row is None:
                # A deletion is the one correction that cannot be walked back by
                # tapping, so an ambiguous reference removes nothing at all.
                if len(self._rows_matching(ref)) > 1:
                    return self._ref_error(ref)
                continue
            rows.append(row)
        removed = [row.id for row in rows if self.items.pop(row.id, None) is not None]
        self._narrowed.difference_update(removed)
        if not removed:
            return {"error": "none of those ids are on the order", "known_ids": list(self.items)}
        self._dispatch(RemoveItems(ids=removed))
        return {"removed": removed, "remaining": len(self.items)}

    async def highlight(self, item_id: str, note: str | None = None) -> dict[str, Any]:
        """Scroll to one row and pulse it — use it as you ask about that row, so his
        eye is on the pills you are asking about.

        Args:
            item_id: The row's id, e.g. "li2", or the product name if you do not have
                the id, e.g. "4 quin". If the name matches two rows you will be told so.
            note: A very short English note shown on the row, e.g. "drops or ointment?".
        """
        if note is not None and (problem := _check_english("note", note)):
            return {"error": problem}
        row = self._row_for(item_id)
        if row is None:
            return self._ref_error(item_id)
        row.note = note
        self._dispatch(HighlightItem(id=row.id, note=note))
        return {"id": row.id, "status": row.status, "note": note}

    # ─── the manual search bar (browser → brain, floor-free) ────────────────

    def search_rows(self, query: str) -> list[SkuWire]:
        """Ranked catalog rows for the search bar. Never raises — an empty result is
        a legitimate answer, and the pharmacist is mid-keystroke."""
        if len(query) < 2:
            return []
        try:
            return [_sku_wire(sku) for sku in self.catalog.search(query, limit=8)]
        except Exception as exc:
            logger.warning("orderdesk: search({!r}) failed: {}", query, exc)
            return []

    def variant_rows(self, item_id: str, family: str) -> ShowVariants:
        """The inline variant strip's answer — one brand's SKUs beside a matched row.

        Never raises, and an empty ``results`` is a legitimate answer (same contract as
        :meth:`search_rows`): the pharmacist tapped a control, and a control that throws
        is worse than one that says "nothing here". The row itself is untouched — this
        only offers; the pick is his."""
        results = self._family_skus(family.strip())[:_MAX_CANDIDATES]
        return ShowVariants(
            item_id=item_id,
            family=family,
            results=results,
            differing_axes=_differing_axes(results),
        )

    @property
    def tools(self) -> list[Any]:
        """The nine bound methods the model may call."""
        return [
            self.add_items,
            self.refine_item,
            self.ask_choice,
            self.choose,
            self.set_quantity,
            self.adjust_quantity,
            self.change_variant,
            self.remove_items,
            self.highlight,
        ]


# ─── The brain ─────────────────────────────────────────────────────────────────


class OrderDeskBrain(GeminiBrain):
    """One per session: the tools above, this call's pharmacy, and the live cart.

    Two seams beyond the tools themselves — the per-session system instruction
    (``on_session_start``) and the live screen, folded into the context by
    ``on_rtvi`` rather than recomputed every call (there is no per-turn grounding
    hook any more; the context is append-only)."""

    def __init__(self, *, llm: GeminiProvider, model: str = DEFAULT_MODEL) -> None:
        super().__init__(client=llm.client, system_instruction=_INSTRUCTION, model=model)
        self.desk = OrderDesk()
        self.scenario: dict[str, Any] = {}
        self.pharmacy: dict[str, Any] = {}
        self.nudge = ""
        # The last screen+PENDING message appended to context, so a state_sync that
        # changed nothing the model needs to know about does not repeat itself.
        self._state_message: str | None = None

    @property
    def tools(self) -> list[Any]:
        """The nine bound methods AFC may call — the desk's, not this brain's own."""
        return self.desk.tools

    # ─── session start: voice, the pharmacy, then the opener ───────────────

    async def on_session_start(self, session: Session) -> None:
        """Configure the Hindi voice, fold this call's PHARMACY CONTEXT into the
        system instruction, and hand the desk its dispatch channel.

        Everything about the store, the previous calls, the order history and
        today's objective goes into the system prompt (not a tool the model has to
        remember to call), so even the opening line is grounded in it."""
        await session.configure(
            Config(
                tts=TtsConfig(voice=Voice.OMNIVOICE_GAURI, language=Language.HI),
                stt=SttConfig(language=Language.HI),
            )
        )
        self.desk.session = session
        payload = dict(session.init or {})
        raw = payload.get("scenario")
        self.scenario = raw if isinstance(raw, dict) else {}
        raw_pharmacy = self.scenario.get("pharmacy")
        self.pharmacy = raw_pharmacy if isinstance(raw_pharmacy, dict) else {}
        self.nudge = str(self.scenario.get("joined_from_nudge") or "").strip()
        language = str(payload.get("language") or LANGUAGE).strip() or LANGUAGE
        if self.scenario:
            block = (
                "PHARMACY CONTEXT (authoritative — everything you know about this "
                "pharmacy, your previous calls with them, what they usually order, and "
                f"today's call objective; the conversation language is {language}): "
                + json.dumps(self.scenario, ensure_ascii=False)
            )
            self.system_instruction = f"{_INSTRUCTION}\n\n{block}"
        logger.info(
            "orderdesk: session start — pharmacy={!r}, call_type={!r}, history={} lines",
            self.pharmacy.get("name"),
            self.scenario.get("call_type"),
            len(self.scenario.get("order_history") or []),
        )

    async def greet(self, session: Session) -> str:
        """Static — no model call, so audio starts the instant the call connects.

        The old opener ran the model once over an ``opening_stimulus`` to speak a
        scenario-grounded line; that generation is exactly what wire-v3 forbids
        here (a greeting is a template at most). The fixed Hindi hello plus the
        fixed fallback line is what that generation used to fall back to anyway
        when the model was unavailable, so nothing about the call's reliability
        changes — only the one case that used to cost a round trip before the
        caller heard anything."""
        return f"{_HELLO} {_FALLBACK_OPENER}"

    # ─── the live screen, folded into context on every state_sync ──────────

    def _ingest_state(self, data: dict[str, Any]) -> None:
        """Fold the browser's live cart into the model's context.

        The browser's own ``state_sync`` snapshot (``data["screen"]``) wins — it is
        the authoritative cart and it carries the pharmacist's manual edits (a pill
        tapped, a quantity typed, a row deleted, Confirm pressed) — with this
        brain's mirror as the fallback for the first beat. The PENDING line names
        the rows still short of a SKU and the axes to ask about, so the model never
        re-asks a question the screen already answered. Appended once, and only
        when the picture actually changed — the context is append-only, and
        ``state_sync`` arrives on every keystroke-adjacent change.

        The snapshot's ``candidate_codes`` are folded back into the mirror first: a
        group pill the pharmacist tapped narrows the row *here*, so the PENDING line
        says "narrowed to 6 — ask the next question" rather than repeating the
        question he just answered with his thumb."""
        snapshot = data.get("screen")
        screen = snapshot if isinstance(snapshot, dict) else self.desk.mirror()
        live: dict[str, dict[str, Any]] | None = None
        if isinstance(snapshot, dict):
            live = {
                str(row.get("id")): row
                for row in (snapshot.get("items") or [])
                if isinstance(row, dict) and row.get("id")
            }
            self.desk.absorb(live)
        pending = self.desk.pending(live)
        if not screen and not pending:
            return
        head = _SCREEN_HEADER + (
            json.dumps(screen, ensure_ascii=False, default=str) if screen else _NOTHING_ON_SCREEN
        )
        message = f"{head}\n{pending}" if pending else head
        if message == self._state_message:
            return
        self._state_message = message
        self.append_to_context(types.Content(role="user", parts=[types.Part(text=message)]))
        logger.info("orderdesk: state_sync ingested ({} items on screen)", len(self.desk.items))

    # ─── browser → brain: the manual search bar, and the live screen ───────

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """The three things the browser tells the desk, all floor-free.

        ``catalog_search`` is the search bar mid-keystroke; ``list_variants`` is the
        Change-variant control on a matched row — both answered with a session-scoped
        action, no inference, no speech, so neither a keystroke nor a tap can make
        the agent start talking over him. ``state_sync`` is folded into context by
        :meth:`_ingest_state`."""
        if msg.type is not RTVIType.CLIENT_MESSAGE or not isinstance(msg.data, dict):
            return
        kind = msg.data.get("t")
        raw_payload = msg.data.get("d")
        payload: dict[str, Any] = raw_payload if isinstance(raw_payload, dict) else {}
        if kind == "state_sync":
            self._ingest_state(payload)
            return
        if kind == CATALOG_SEARCH:
            query = str(payload.get("query") or "").strip()
            results = self.desk.search_rows(query)
            logger.info("orderdesk: catalog_search {!r} → {} rows", query, len(results))
            session.dispatch(ShowSearchResults(query=query, results=results))
            return
        if kind == LIST_VARIANTS:
            item_id = str(payload.get("item_id") or "").strip()
            family = str(payload.get("family") or "").strip()
            action = self.desk.variant_rows(item_id, family)
            logger.info(
                "orderdesk: list_variants {!r} on {!r} → {} rows",
                family,
                item_id,
                len(action.results),
            )
            session.dispatch(action)
            return
