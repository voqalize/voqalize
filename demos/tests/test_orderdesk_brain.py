"""The MedSetu OrderDesk brain, end-to-end over the wire — no network, no LLM key,
**and no catalog build**.

Same shape as ``test_travel_adk.py``: the *real* ``OrderDeskBrain`` — the shipping
``demos/orderdesk/backend/brain.py``, its real prompt, its real seven tools — hosted on
a real ``DirectAgent`` WebSocket, driven by the conformance ``VoiceDriver``, with only
the *model* swapped for a :class:`ScriptedLlm`. Two things are stubbed rather than
real, for opposite reasons:

* the **model**, because a scripted tool call carries the exact arguments we assert
  the browser receives — the ``ui_command`` contract becomes a test, not a hope;
* the **catalog** (``backend/search.py``, ``catalog.db`` — the sibling agent's lane),
  because these tests must run on a fresh checkout before the 20k-SKU database has
  been built. The stub below answers the DESIGN.md §2 API exactly, with the four
  outcomes the brain must render: matched, multi_variant, multi_family, not_found.

What is covered:

* **the resolving → resolved beat.** ``add_items`` puts every row on screen *greyed*
  before it touches the catalog, then upserts the outcome — the two-phase render the
  UI's shimmer depends on.
* **the minimal-question briefing.** The tool's return value — what the model reads —
  carries only the differing axes, the short on-screen option labels and one guidance
  line, so the model asks "ड्रॉप्स या ऑइंटमेंट?" instead of reading the catalogue aloud.
* **the sharpest question** (DESIGN §7-bis). Four candidates or fewer stay leaf pills;
  five or more turn the tool result into a candidate *table* and the row into a
  question. ``ask_choice`` is validated on the way in — 2-4 choices, known codes, total
  coverage — with retriable errors that name the offending codes, and the pill the
  pharmacist taps himself narrows the brain's own candidate set on the next snapshot.
* **the English-only guard.** Devanagari in a tool argument is rejected before it can
  reach the catalog, with a message that tells the model to transliterate and retry —
  on both paths (the pydantic arg model and the plain-``str`` tools).
* **the typed screen contract, pinned byte-for-byte** — whole envelopes, envelope keys
  included, for all five actions, plus the class-name → wire-name coupling
  ``frontend/src/uiCommands.ts`` is hand-mirrored from.
* **grounding.** The browser's ``state_sync`` cart (including a pill the pharmacist
  tapped himself) reaches the next model call as *system instruction*, with the
  PENDING line naming only the rows still waiting on a question.
* **the manual search bar.** ``catalog_search`` is answered with a floor-free
  ``show_search_results`` — no interaction, no speech, mid-keystroke.
* **the hybrid greeting.** An instant Hindi hello, then the generated opener, in one
  bracket — grounded in the PHARMACY CONTEXT the session payload carried.

Run: ``cd demos && uv run pytest tests/test_orderdesk_brain.py``
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

import pytest

pytest.importorskip("google.adk")

from voqalize_demos.discovery import discover

# Discovery is what makes ``demos/orderdesk/backend/`` importable, in place, under the
# synthetic package the umbrella mounts it at — so this test asserts on the module the
# server will actually serve.
discover()

from voqalize_demos._loaded.orderdesk import brain as od  # noqa: E402
from voqalize_demos._loaded.orderdesk.brain import OrderDeskBrain  # noqa: E402

from voqalize.conformance import (  # noqa: E402
    DirectConnection,
    VoiceDriver,
    checks,
    generate_keypair,
    mint_pygato_token,
)
from voqalize.google_adk.testing import ScriptedLlm, call, reply, reply_and_call  # noqa: E402
from voqalize.sdk import DirectAgent, brain_factory  # noqa: E402
from voqalize.sdk.wire import (  # noqa: E402
    LLMTextFrame,
    UpdateSTTSettingsFrame,
    UpdateTTSSettingsFrame,
)

# The trailing "…" is the lookahead character that lets the instant opener flush
# on its own — see `_HELLO_BY_LANGUAGE` in voqalize_demos. It is part of the
# spoken string, so it is part of what the greeting bracket carries.
HELLO = "नमस्ते!…"
OPENER = "गुप्ता जी, MedSetu से। आज का ऑर्डर बता दीजिए।"


# ─── the catalog stub (DESIGN §2's API, four outcomes, zero sqlite) ────────────


@dataclass(frozen=True)
class StubSku:
    """A ``search.SkuView`` lookalike — same fields, same ``wire()`` contract."""

    code: str
    name: str
    family: str
    variant_label: str = ""
    form: str = ""
    strength: str = ""
    pack_size: str = ""
    mrp: float = 0.0
    ptr: float = 0.0
    stock: int = 0
    manufacturer: str = ""
    scheme: str = ""

    def wire(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "family": self.family,
            "variant_label": self.variant_label,
            "form": self.form,
            "strength": self.strength,
            "pack_size": self.pack_size,
            "mrp": self.mrp,
            "ptr": self.ptr,
            "stock": self.stock,
            "manufacturer": self.manufacturer,
            "scheme": self.scheme,
        }


@dataclass(frozen=True)
class StubFamily:
    family: str
    manufacturers: list[str] = field(default_factory=list)
    forms: list[str] = field(default_factory=list)
    sku_count: int = 0
    hint: str = ""

    def wire(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "manufacturers": self.manufacturers,
            "forms": self.forms,
            "sku_count": self.sku_count,
            "hint": self.hint,
        }


@dataclass(frozen=True)
class StubResolution:
    status: str
    sku: StubSku | None = None
    family: str | None = None
    variants: list[StubSku] = field(default_factory=list)
    families: list[StubFamily] = field(default_factory=list)
    differing_axes: list[str] = field(default_factory=list)
    confidence: float = 0.0


TELMA = StubSku(
    code="T4015",
    name="TELMA 40 TAB",
    family="TELMA",
    variant_label="",
    form="TABLET",
    strength="40 MG",
    pack_size="15'S",
    mrp=155.0,
    ptr=124.0,
    stock=240,
    manufacturer="GLENMARK",
    scheme="10 + 1",
)
QUIN_DROPS = StubSku(
    code="Q4D5",
    name="4 QUIN EYE DROPS 5ML",
    family="4 QUIN",
    form="EYE DROPS",
    pack_size="5ML",
    mrp=160.0,
    ptr=128.0,
    stock=30,
    manufacturer="ENTOD",
)
QUIN_OINT = StubSku(
    code="Q4O5",
    name="4 QUIN EYE OINTMENT 5GM",
    family="4 QUIN",
    form="EYE OINTMENT",
    pack_size="5GM",
    mrp=142.0,
    ptr=113.0,
    stock=12,
    manufacturer="ENTOD",
)
COLD = StubSku(
    code="CB10",
    name="COLDBEST TAB",
    family="COLDBEST",
    form="TABLET",
    pack_size="10'S",
    mrp=42.0,
    ptr=33.0,
    stock=100,
    manufacturer="MANKIND",
)


def _telma(code: str, name: str, label: str, strength: str, mrp: float) -> StubSku:
    return StubSku(
        code=code,
        name=name,
        family="TELMA",
        variant_label=label,
        form="TABLET",
        strength=strength,
        pack_size="15'S",
        mrp=mrp,
        ptr=round(mrp * 0.8, 2),
        stock=90,
        manufacturer="GLENMARK",
        scheme="10 + 1" if code == "T4015" else "",
    )


# The wide family — the case §7-bis exists for. Eight SKUs across four suffix lines:
# too many for pills, and a four-way split on `variant_label` lands every group at 1-3.
TELMA_FAMILY = [
    _telma("T2015", "TELMA 20", "", "20 MG", 96.0),
    TELMA,  # T4015 — plain 40, the one the order history and the scheme banner use
    _telma("T8015", "TELMA 80", "", "80 MG", 232.0),
    _telma("TH4015", "TELMA H 40", "H", "40 MG", 178.0),
    _telma("TH8015", "TELMA H 80", "H", "80 MG", 245.0),
    _telma("TAM4015", "TELMA AM", "AM", "40 MG", 199.0),
    _telma("TCT4015", "TELMA CT 40/6.25", "CT 40/6.25", "40 MG", 210.0),
    _telma("TB5015", "TELMA BETA 50", "BETA", "50 MG", 188.0),
]


class StubCatalog:
    """The ``search.py`` module surface (DESIGN §2), keyed by lowercased query."""

    def __init__(self) -> None:
        self.resolved: list[tuple[str, str | None, str | None]] = []

    def resolve(
        self, query: str, *, form_hint: str | None = None, strength_hint: str | None = None
    ) -> StubResolution:
        self.resolved.append((query, form_hint, strength_hint))
        q = query.lower().strip()
        if q == "telma":
            # A bare brand root: the resolver can only say "one family, many SKUs", and
            # it caps its own pill list — the brain widens it to the whole family.
            return StubResolution(
                status="multi_variant",
                family="TELMA",
                variants=list(TELMA_FAMILY),
                differing_axes=["variant_label", "strength"],
                confidence=0.7,
            )
        if q == "telma combo":
            # Already narrowed by what he said: five of the eight, and the resolver did
            # NOT truncate (five is under its cap of eight). The brain must keep these
            # five rather than widening back to the family it narrowed out of.
            return StubResolution(
                status="multi_variant",
                family="TELMA",
                variants=TELMA_FAMILY[3:],
                differing_axes=["variant_label", "strength"],
                confidence=0.75,
            )
        if "telma" in q:
            return StubResolution(status="matched", sku=TELMA, family="TELMA", confidence=0.98)
        if "4 quin" in q or "quin" in q:
            return StubResolution(
                status="multi_variant",
                family="4 QUIN",
                variants=[QUIN_DROPS, QUIN_OINT],
                differing_axes=["form"],
                confidence=0.8,
            )
        if "kwin" in q:
            # Two brands, four SKUs between them — a `multi_family` answer whose whole
            # union sits well under the question floor. The cards on screen must still
            # carry those SKUs (change 1), or a tap on one has nothing to narrow.
            return StubResolution(
                status="multi_family",
                families=[
                    StubFamily(
                        "4 QUIN",
                        ["ENTOD"],
                        ["EYE DROPS", "EYE OINTMENT"],
                        2,
                        "ENTOD · eye drops/ointment · 2 SKUs",
                    ),
                    StubFamily("COLDBEST", ["MANKIND"], ["TABLET"], 1, "MANKIND · tablets · 1 SKU"),
                ],
                confidence=0.35,
            )
        if "abevia" in q:
            return StubResolution(
                status="multi_family",
                families=[
                    StubFamily("ABEVIA", ["USV"], ["TABLET"], 4, "USV · tablets · 4 SKUs"),
                    StubFamily("ABIWAYS", ["ALKEM"], ["SYRUP"], 2, "ALKEM · syrup · 2 SKUs"),
                ],
                confidence=0.4,
            )
        if "abiways" in q:
            return StubResolution(
                status="matched",
                sku=StubSku(
                    code="AW20",
                    name="ABIWAYS SYRUP 200ML",
                    family="ABIWAYS",
                    form="SYRUP",
                    pack_size="200ML",
                    mrp=98.0,
                    ptr=78.0,
                    stock=44,
                    manufacturer="ALKEM",
                ),
                family="ABIWAYS",
                confidence=0.95,
            )
        return StubResolution(status="not_found")

    def search(self, query: str, limit: int = 8) -> list[StubSku]:
        return [COLD] if "cold" in query.lower() else []

    def sku_by_code(self, code: str) -> StubSku | None:
        return {s.code: s for s in self._all()}.get(code)

    def skus_in_family(self, family: str) -> list[StubSku]:
        return [s for s in self._all() if s.family == family.strip().upper()]

    @staticmethod
    def _all() -> list[StubSku]:
        return [*TELMA_FAMILY, QUIN_DROPS, QUIN_OINT, COLD]


# The wire dicts the browser must receive, derived from the stub rows themselves so a
# renamed SkuWire field fails on the Action pin below, not on a hand-typed literal.
W_TELMA = TELMA.wire()
W_DROPS = QUIN_DROPS.wire()
W_OINT = QUIN_OINT.wire()
W_COLD = COLD.wire()
W_FAMILY = [sku.wire() for sku in TELMA_FAMILY]

# The four-way split the scripted model asks for — every candidate in exactly one group.
TELMA_CHOICES = [
    {"label": "Plain Telma", "sku_codes": ["T2015", "T4015", "T8015"]},
    {"label": "Telma H", "sku_codes": ["TH4015", "TH8015"]},
    {"label": "Telma AM", "sku_codes": ["TAM4015"]},
    {"label": "Telma CT / Beta", "sku_codes": ["TCT4015", "TB5015"]},
]


def _row(**over: Any) -> dict[str, Any]:
    """One ``LineItemView`` on the wire — every field, since an Action emits its whole
    declared shape (no ``exclude_none``); ``uiCommands.ts`` mirrors exactly this."""
    return {
        "id": "li1",
        "spoken_text": "",
        "query": "",
        "quantity": None,
        "status": "resolving",
        "sku": None,
        "family": None,
        "variants": [],
        "families": [],
        "candidates": [],
        "question": None,
        "differing_axes": [],
        "note": None,
        "source": "agent",
        **over,
    }


# ─── the scenario payload (the shape frontend/src/data.ts pins) ────────────────

NUDGE = "गुड मॉर्निंग! आज का ऑर्डर लगाने का समय — जॉइन कीजिए।"

PAYLOAD: dict[str, Any] = {
    "language": "Hindi",
    "scenario": {
        "call_type": "ambiguous_day",
        "joined_from_nudge": NUDGE,
        "pharmacy": {
            "name": "Gupta Medical Store",
            "owner": "Ramesh Gupta",
            "city": "Kanpur",
            "area": "Govind Nagar",
            "since": "Customer since 2014",
            "volume": "₹4.2L / month · ~30 orders",
            "credit": "21-day credit · clean record",
            "tags": ["chronic-heavy", "high volume"],
        },
        "prior_calls": [{"day": "Day 1 — Mon", "summary": "First order taken; 9 lines."}],
        "order_history": [
            {
                "sku_code": "T4015",
                "name": "TELMA 40 TAB",
                "pack_size": "15'S",
                "qty": 30,
                "when": "last Tuesday",
            }
        ],
        "usual_items": ["telma 40", "shelcal 500"],
        "todays_call_objective": "Take today's order; several items will be ambiguous.",
    },
}


def _stimulus() -> str:
    """The exact one-shot turn the greeting drives the model with — computed from the
    brain itself so the script cannot drift from the prompt."""
    brain = OrderDeskBrain(model=ScriptedLlm({}), catalog=StubCatalog())
    brain.nudge = NUDGE
    return brain.opening_stimulus()


def _script() -> dict[str, Any]:
    """The scripted dialogue, keyed by the exact user text (the greeting's stimulus is
    a user turn too), one Reply per model call."""
    return {
        _stimulus(): [reply(OPENER)],
        "टेल्मा फोर्टी तीस स्ट्रिप और चार क्विन": [
            reply_and_call(
                "ठीक है।",
                "add_items",
                items=[
                    {"text": "telma 40", "quantity": 30},
                    {"text": "4 quin"},
                ],
            ),
            reply("चार क्विन — ड्रॉप्स या ऑइंटमेंट?"),
        ],
        "ड्रॉप्स वाला, दस": [
            reply_and_call("लग गया।", "choose", item_id="li2", sku_code="Q4D5", quantity=10),
            reply("दोनों लग गए। और कुछ?"),
        ],
        "टेल्मा बारह कर दो": [
            call("set_quantity", item_id="li1", quantity=12),
            reply("बारह कर दी।"),
        ],
        # The row referred to by NAME — the model heard a product, not an id.
        "टेल्मा फोर्टी बारह कर दो": [
            call("set_quantity", item_id="telma 40", quantity=12),
            reply("बारह कर दी।"),
        ],
        # Relative, then clamped: "ten more" is a delta, and no delta reaches zero.
        "दस और डाल दो": [
            call("adjust_quantity", item_id="telma 40", delta=10),
            reply("जोड़ दिया।"),
        ],
        "बहुत कम कर दो": [
            call("adjust_quantity", item_id="li1", delta=-500),
            reply("कम कर दी।"),
        ],
        # Brand right, variant wrong — the swap that must not become a delete-and-re-add.
        "ऑइंटमेंट वाला कर दो": [
            call("change_variant", item_id="li2", want="ointment"),
            reply("बदल दिया।"),
        ],
        # …and the same tool when the answer is not one SKU: the row goes back to being
        # a question, over the two Telma H strengths and nothing else.
        "एच वाला कर दो": [
            call("change_variant", item_id="li1", want="H"),
            reply("चालीस या अस्सी?"),
        ],
        "चार क्विन हटा दो": [
            call("remove_items", item_ids=["li2"]),
            reply("हटा दिया।"),
        ],
        "वो वाली दवा": [
            call("highlight", item_id="li1", note="which strength?"),
            reply("स्क्रीन पर देखिए।"),
        ],
        # The guard: Devanagari in a tool argument. First call is rejected, the model
        # reads the error and retries in English letters.
        "वोलिनी दे दो": [
            call("add_items", items=[{"text": "वोलिनी"}]),
            call("add_items", items=[{"text": "volini"}]),
            reply("ये कैटलॉग में नहीं मिला।"),
        ],
        "अबेविया चाहिए": [
            reply_and_call("देखती हूँ।", "add_items", items=[{"text": "abevia"}]),
            reply("कौन सा ब्रांड — स्क्रीन पर देखिए?"),
        ],
        "अबीवेज़ वाला": [
            call("refine_item", item_id="li1", query="abiways"),
            reply("लग गया।"),
        ],
        # §7-bis: a bare brand root is eight SKUs, so the model gets a candidate table
        # and must split it — one question, four groups, then a leaf.
        "टेल्मा दे दो": [
            reply_and_call("ठीक है।", "add_items", items=[{"text": "telma"}]),
            call(
                "ask_choice",
                item_id="li1",
                question="Which Telma line?",
                choices=TELMA_CHOICES,
            ),
            reply("टेल्मा — कौन सी लाइन? स्क्रीन पर देखिए।"),
        ],
        # He answers the second round by voice, with a code that was never a leaf pill —
        # it only ever existed in the candidate set.
        "एच वाली अस्सी": [
            call("choose", item_id="li1", sku_code="TH8015", quantity=15),
            reply("लग गया।"),
        ],
        # A choice set that leaves two candidates uncovered: rejected, then corrected.
        "टेल्मा वाला फिर से": [
            call(
                "ask_choice",
                item_id="li1",
                question="Which Telma line?",
                choices=TELMA_CHOICES[:2],
            ),
            call(
                "ask_choice",
                item_id="li1",
                question="Which Telma line?",
                choices=TELMA_CHOICES,
            ),
            reply("कौन सी लाइन?"),
        ],
        "अब क्या बाकी है?": [reply("बस एक आइटम पेंडिंग है।")],
        "कुछ नहीं": [reply("ठीक है।")],
    }


async def _host(
    llm: ScriptedLlm,
    catalog: StubCatalog | None = None,
    brains: list[OrderDeskBrain] | None = None,
) -> tuple[DirectAgent, VoiceDriver]:
    """Host the real OrderDeskBrain (scripted model, stubbed catalog) on a real
    localhost socket and open a PyGato-side driver against it.

    ``brains`` collects the session's brain as the factory mints it — the only way to
    assert on the brain's *own* mirror (as opposed to what it says on the wire) from
    this side of a real socket."""

    def _make() -> OrderDeskBrain:
        brain = OrderDeskBrain(
            model=llm, catalog=catalog or StubCatalog(), answer_conformance_dump=True
        )
        if brains is not None:
            brains.append(brain)
        return brain

    keypair = generate_keypair()
    agent = DirectAgent(
        factory=brain_factory(_make),
        host="127.0.0.1",
        port=0,
        public_keys=keypair.public_pem,
    )
    port = await agent.start()
    session_id = "orderdesk-test"
    token = mint_pygato_token(
        private_key_pem=keypair.private_pem,
        session_id=session_id,
        agent_id="orderdesk",
        tenant_id="demo",
    )
    driver = VoiceDriver(
        DirectConnection(f"ws://127.0.0.1:{port}", session_id, token=token),
        session_id=session_id,
        agent_id="orderdesk",
        default_timeout=10.0,
    )
    await driver.open()
    return agent, driver


def _actions(driver: VoiceDriver) -> list[str]:
    """The ui_command actions the brain fired, minus the conformance backchannel."""
    return [
        str(c.get("action"))
        for c in driver.ui_commands
        if not str(c.get("action", "")).startswith("__")
    ]


def _tool_results(llm: ScriptedLlm) -> list[dict[str, Any]]:
    """Every tool result the model was shown, in order — the *briefings* the prompt
    rules are written against."""
    out: list[dict[str, Any]] = []
    for contents in llm.captured_contents:
        for content in contents:
            for part in getattr(content, "parts", None) or []:
                response = getattr(part, "function_response", None)
                if response is not None and response.response not in out:
                    out.append(dict(response.response))
    return out


# ─── tests ─────────────────────────────────────────────────────────────────────


async def test_greeting_is_an_instant_hello_plus_a_grounded_opener() -> None:
    """The hybrid opener: a fixed Hindi hello (no model call, instant audio) and the
    generated line behind it, in ONE bracket. The PHARMACY CONTEXT from the session
    payload is in the system instruction of that very first call, so even the opening
    sentence is grounded in who this pharmacy is."""
    llm = ScriptedLlm(_script())
    agent, driver = await _host(llm)
    try:
        greeting = await driver.start_session(payload=PAYLOAD)
        checks.check_greeting(driver, greeting)
        assert greeting is not None
        assert greeting.text == HELLO + OPENER, repr(greeting.text)

        system = llm.captured_system_instructions[0]
        assert "PHARMACY CONTEXT (authoritative" in system
        assert "Gupta Medical Store" in system
        assert "Take today's order" in system
        # The stimulus is a one-shot user turn, and it carries the push notification.
        assert NUDGE in _stimulus()
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_add_items_lands_rows_then_resolves_them() -> None:
    """One turn, two products: each row is upserted *resolving* first (the shimmer the
    UI shows while the catalog runs) and then upserted again with its outcome — one
    matched, one ambiguous — and the matched row's supplier scheme raises the banner."""
    catalog = StubCatalog()
    llm = ScriptedLlm(_script())
    agent, driver = await _host(llm, catalog)
    try:
        await driver.start_session(payload=PAYLOAD)
        turn = await driver.user_says("टेल्मा फोर्टी तीस स्ट्रिप और चार क्विन")
        # Tool round-trip ⇒ two model calls ⇒ two inference brackets.
        assert len(turn.inferences) == 2, [i.text for i in turn.inferences]
        checks.check_brackets_closed(turn)
        checks.check_completed(turn)

        assert _actions(driver) == [
            "upsert_items",  # li1 resolving
            "upsert_items",  # li1 matched
            "order_note",  # TELMA carries a scheme
            "upsert_items",  # li2 resolving
            "upsert_items",  # li2 multi_variant
        ], _actions(driver)

        # The English text, the hints and the quantity all reached the catalog.
        assert catalog.resolved == [("telma 40", None, None), ("4 quin", None, None)]

        rows = [c for c in driver.ui_commands if c.get("action") == "upsert_items"]
        assert rows[0]["items"][0]["status"] == "resolving"
        assert rows[0]["items"][0]["id"] == "li1"
        assert rows[1]["items"][0]["status"] == "matched"
        assert rows[1]["items"][0]["sku"] == W_TELMA
        assert rows[1]["items"][0]["quantity"] == 30
        assert rows[2]["items"][0] == _row(id="li2", spoken_text="4 quin", query="4 quin")
        assert rows[3]["items"][0]["status"] == "multi_variant"
        assert rows[3]["items"][0]["variants"] == [W_DROPS, W_OINT]
        assert rows[3]["items"][0]["differing_axes"] == ["form"]
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_the_tool_return_is_a_minimal_question_briefing() -> None:
    """What the *model* gets back is the whole point of DESIGN §4: only the axes that
    actually differ, the short option labels already on screen, and one instruction —
    never a data dump it would be tempted to read aloud."""
    llm = ScriptedLlm(_script())
    agent, driver = await _host(llm)
    try:
        await driver.start_session(payload=PAYLOAD)
        checks.check_completed(await driver.user_says("टेल्मा फोर्टी तीस स्ट्रिप और चार क्विन"))

        result = _tool_results(llm)[0]
        assert result == {
            "items": [
                {
                    "id": "li1",
                    "status": "matched",
                    "name": "TELMA 40 TAB",
                    "pack_size": "15'S",
                    "mrp": 155.0,
                    "scheme": "10 + 1",
                    "quantity": 30,
                },
                {
                    "id": "li2",
                    "status": "multi_variant",
                    "family": "4 QUIN",
                    "ask_about": ["form"],
                    # Short labels — the SKU minus the family name, exactly what the
                    # pills on his screen say.
                    "options": ["EYE DROPS 5ML ₹160", "EYE OINTMENT 5GM ₹142"],
                    "guidance": "Ask ONE short question about: form. The options are on screen.",
                },
            ]
        }

        # multi_family briefs point at the brand cards, not at variants.
        checks.check_completed(await driver.user_says("अबेविया चाहिए"))
        family_brief = _tool_results(llm)[-1]["items"][0]
        assert family_brief["ask_about"] == ["family"]
        assert family_brief["options"] == [
            "ABEVIA — USV · tablets · 4 SKUs",
            "ABIWAYS — ALKEM · syrup · 2 SKUs",
        ]
        assert "which brand" in family_brief["guidance"]
    finally:
        await driver.aclose()
        await agent.aclose()


CANDIDATE_TABLE = [
    "T2015 · TELMA 20 · TABLET · 20 MG · 15'S · ₹96",
    "T4015 · TELMA 40 TAB · TABLET · 40 MG · 15'S · ₹155",
    "T8015 · TELMA 80 · TABLET · 80 MG · 15'S · ₹232",
    "TH4015 · TELMA H 40 · TABLET · 40 MG · 15'S · ₹178",
    "TH8015 · TELMA H 80 · TABLET · 80 MG · 15'S · ₹245",
    "TAM4015 · TELMA AM · TABLET · 40 MG · 15'S · ₹199",
    "TCT4015 · TELMA CT 40/6.25 · TABLET · 40 MG · 15'S · ₹210",
    "TB5015 · TELMA BETA 50 · TABLET · 50 MG · 15'S · ₹188",
]

WIRE_QUESTION = {
    "text": "Which Telma line?",
    "choices": [
        {"label": "Plain Telma", "sku_code": None, "narrows_to": ["T2015", "T4015", "T8015"]},
        {"label": "Telma H", "sku_code": None, "narrows_to": ["TH4015", "TH8015"]},
        # One code ⇒ a LEAF pill: the browser can lock the row on the tap.
        {"label": "Telma AM", "sku_code": "TAM4015", "narrows_to": ["TAM4015"]},
        {"label": "Telma CT / Beta", "sku_code": None, "narrows_to": ["TCT4015", "TB5015"]},
    ],
}


def _wide_row() -> od.OrderDesk:
    """A desk holding one already-widened row (eight candidates, no question yet) and
    one small leaf row — the two sides of the §7-bis fork, without a voice session."""
    desk = od.OrderDesk(StubCatalog())
    desk.items["li1"] = od.LineItemView(
        id="li1",
        spoken_text="telma",
        query="telma",
        status="multi_variant",
        family="TELMA",
        candidates=[od.SkuWire(**wire) for wire in W_FAMILY],
        differing_axes=["variant_label", "strength"],
    )
    desk.items["li2"] = od.LineItemView(
        id="li2",
        spoken_text="4 quin",
        status="multi_variant",
        family="4 QUIN",
        variants=[od.SkuWire(**W_DROPS), od.SkuWire(**W_OINT)],
        differing_axes=["form"],
    )
    return desk


async def test_a_wide_family_becomes_a_candidate_table_not_pills() -> None:
    """DESIGN §7-bis's fork, on the tool result. A bare brand root resolves to more
    candidates than the resolver will pill (it caps at eight), so the brain re-stocks
    the row with the WHOLE family, clears the leaf pills — twenty pills is the thing
    this mechanic exists to prevent — and hands the model a candidate *table*: the codes
    it must quote back, the axes it can split on, and one instruction to split them."""
    llm = ScriptedLlm(_script())
    agent, driver = await _host(llm)
    try:
        await driver.start_session(payload=PAYLOAD)
        checks.check_completed(await driver.user_says("टेल्मा दे दो"))

        rows = [c for c in driver.ui_commands if c.get("action") == "upsert_items"]
        widened = rows[1]["items"][0]
        assert widened["status"] == "multi_variant"
        assert widened["candidates"] == W_FAMILY
        assert widened["variants"] == []  # no leaf pills while the set is this big
        assert widened["question"] is None  # the model has not asked yet
        # Recomputed over the whole family, not over the resolver's truncated eight.
        assert widened["differing_axes"] == ["variant_label", "strength"]

        assert _tool_results(llm)[0] == {
            "items": [
                {
                    "id": "li1",
                    "status": "multi_variant",
                    "family": "TELMA",
                    "ask_about": ["variant_label", "strength"],
                    "candidate_count": 8,
                    "candidates": CANDIDATE_TABLE,
                    "guidance": (
                        "8 candidates on file. Do NOT list them aloud and do NOT show "
                        "them all. Call ask_choice with ONE question and 2-4 choices "
                        "that split these most evenly — group by the axis that best "
                        "partitions (suffix line / form / strength band). Prefer groups "
                        "of similar size."
                    ),
                }
            ]
        }
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_four_or_fewer_candidates_stay_leaf_pills() -> None:
    """The other side of the fork is unchanged, and deliberately so: two 4 QUIN SKUs are
    two pills and one five-word question. No candidate set, no question, no ask_choice —
    the machinery only appears when the screen would otherwise become a list."""
    llm = ScriptedLlm(_script())
    agent, driver = await _host(llm)
    try:
        await driver.start_session(payload=PAYLOAD)
        checks.check_completed(await driver.user_says("टेल्मा फोर्टी तीस स्ट्रिप और चार क्विन"))

        rows = [c for c in driver.ui_commands if c.get("action") == "upsert_items"]
        quin = rows[3]["items"][0]
        assert quin["variants"] == [W_DROPS, W_OINT]
        assert quin["candidates"] == []
        assert quin["question"] is None

        brief = _tool_results(llm)[0]["items"][1]
        assert "candidates" not in brief and "candidate_count" not in brief
        assert brief["options"] == ["EYE DROPS 5ML ₹160", "EYE OINTMENT 5GM ₹142"]
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_widening_never_undoes_a_narrowing_the_pharmacist_already_spoke() -> None:
    """The candidate set is the resolver's, widened only when the resolver *truncated*
    it. Eight variants is ``resolve()``'s documented cap — "there may be more" — and only
    then is the row re-stocked from the whole family. Five of eight means the resolver
    exhausted its matches ("टेल्मा कॉम्बो", "volini gel"): widening back to the family
    would throw away a narrowing he spoke aloud, so those five stay the candidate set."""
    desk = od.OrderDesk(StubCatalog())
    row = od.LineItemView(id="li1", spoken_text="telma combo")
    desk._resolve_into(row, "telma combo")
    assert [sku.code for sku in row.candidates] == [w["code"] for w in W_FAMILY[3:]]
    assert row.variants == []  # five is still too many for pills

    # And the truncated case does widen — same family, twice the candidates.
    wide = od.LineItemView(id="li2", spoken_text="telma")
    desk._resolve_into(wide, "telma")
    assert [sku.code for sku in wide.candidates] == [w["code"] for w in W_FAMILY]


async def test_ask_choice_puts_one_validated_question_on_the_row() -> None:
    """The happy path, end to end: the model splits eight candidates four ways, the
    brain validates the set and renders it as pills (a one-code group becoming a leaf),
    and what comes back to the model is the group sizes — so it can see the split was
    even — plus one instruction to say the question out loud, and nothing to read."""
    llm = ScriptedLlm(_script())
    agent, driver = await _host(llm)
    try:
        await driver.start_session(payload=PAYLOAD)
        checks.check_completed(await driver.user_says("टेल्मा दे दो"))

        asked = [c for c in driver.ui_commands if c.get("action") == "upsert_items"][-1]
        assert asked == {
            "type": "ui_command",
            "action": "upsert_items",
            "action_id": 3,
            "items": [
                _row(
                    id="li1",
                    spoken_text="telma",
                    query="telma",
                    status="multi_variant",
                    family="TELMA",
                    candidates=W_FAMILY,
                    question=WIRE_QUESTION,
                    differing_axes=["variant_label", "strength"],
                )
            ],
        }

        assert _tool_results(llm)[-1] == {
            "ok": True,
            "asked": "Which Telma line?",
            "groups": [
                {"label": "Plain Telma", "count": 3},
                {"label": "Telma H", "count": 2},
                {"label": "Telma AM", "count": 1},
                {"label": "Telma CT / Beta", "count": 2},
            ],
            "guidance": (
                "Now ask this exact question aloud in one short Hindi sentence. Do not "
                "read the options aloud if they are visible as pills."
            ),
        }

        # And the row is now *awaiting an answer*, not awaiting a question — the next
        # prompt must not tell the model to ask again.
        grounded = llm.captured_system_instructions[-1]
        assert "li1 (telma): awaiting answer to: Which Telma line?" in grounded
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_ask_choice_rejects_a_choice_set_that_would_not_narrow() -> None:
    """The validation, which is what makes a model-authored question safe to render.

    Each failure is a *retriable* tool error that names the offending codes, so the
    model can repair the call in-conversation instead of putting a broken pill set —
    one that cannot reach some SKUs at all — in front of the pharmacist. Nothing
    reaches the screen on any of these paths."""
    desk = _wide_row()
    choices = [od.Choice(**c) for c in TELMA_CHOICES]

    # Coverage: three candidates would be unreachable whatever he taps.
    uncovered = await desk.ask_choice("li1", "Which Telma line?", choices[:2])
    assert "in no choice" in uncovered["error"]
    for code in ("TAM4015", "TCT4015", "TB5015"):
        assert code in uncovered["error"]
    assert uncovered["candidates"] == [w["code"] for w in W_FAMILY]

    # Pill cap: five groups is a list again.
    too_many = await desk.ask_choice(
        "li1",
        "Which Telma?",
        [
            od.Choice(label="20 mg", sku_codes=["T2015"]),
            od.Choice(label="40 mg", sku_codes=["T4015"]),
            od.Choice(label="80 mg", sku_codes=["T8015"]),
            od.Choice(label="H line", sku_codes=["TH4015", "TH8015"]),
            od.Choice(label="Rest", sku_codes=["TAM4015", "TCT4015", "TB5015"]),
        ],
    )
    assert "2 to 4 choices — you sent 5" in too_many["error"]

    # One group narrows nothing at all.
    assert (
        "2 to 4 choices — you sent 1"
        in (
            await desk.ask_choice(
                "li1", "Which?", [od.Choice(label="All", sku_codes=[c["code"] for c in W_FAMILY])]
            )
        )["error"]
    )

    # Invented codes: the candidate set is the brain's fact, not the model's memory.
    unknown = await desk.ask_choice(
        "li1",
        "Which Telma line?",
        [
            od.Choice(label="Plain", sku_codes=["T2015", "T4015", "T8015", "T9999"]),
            od.Choice(
                label="Combos",
                sku_codes=["TH4015", "TH8015", "TAM4015", "TCT4015", "TB5015"],
            ),
        ],
    )
    assert "T9999" in unknown["error"] and "not candidates of li1" in unknown["error"]

    # A choice that keeps nothing.
    empty = await desk.ask_choice(
        "li1",
        "Which Telma line?",
        [
            od.Choice(label="Everything", sku_codes=[c["code"] for c in W_FAMILY]),
            od.Choice(label="Nothing", sku_codes=[]),
        ],
    )
    assert "keep no candidates" in empty["error"]

    # A small row has no candidate set: its pills are already on screen.
    leaf = await desk.ask_choice(
        "li2",
        "Drops or ointment?",
        [
            od.Choice(label="Drops", sku_codes=["Q4D5"]),
            od.Choice(label="Ointment", sku_codes=["Q4O5"]),
        ],
    )
    assert "no candidate set" in leaf["error"]
    assert leaf["options"] == ["Q4D5", "Q4O5"]

    assert (await desk.ask_choice("li9", "Which?", choices))["error"].startswith("no such item")

    # The English-only guard rides both halves of this tool too.
    assert (
        "must be written in English letters"
        in (await desk.ask_choice("li1", "कौन सी लाइन?", choices))["error"]
    )
    with pytest.raises(Exception) as excinfo:
        od.Choice(label="प्लेन", sku_codes=["T4015"])
    assert "must be written in English letters" in str(excinfo.value)

    # Not one of those calls put a question on the row.
    assert desk.items["li1"].question is None
    assert desk.items["li2"].question is None


async def test_a_bad_choice_set_is_a_retriable_tool_error_on_the_wire() -> None:
    """The validation above, on the real path: a choice set that leaves three candidates
    uncovered comes back through ADK as a *tool error the model reads*, not an exception
    that kills the turn — and the corrected second call renders. Nothing reached the
    screen in between."""
    llm = ScriptedLlm(_script())
    agent, driver = await _host(llm)
    try:
        await driver.start_session(payload=PAYLOAD)
        checks.check_completed(await driver.user_says("टेल्मा दे दो"))
        before = len([c for c in driver.ui_commands if c.get("action") == "upsert_items"])
        checks.check_completed(await driver.user_says("टेल्मा वाला फिर से"))

        errors = [r for r in _tool_results(llm) if "error" in r]
        assert errors and "in no choice" in str(errors[-1]["error"])
        rows = [c for c in driver.ui_commands if c.get("action") == "upsert_items"]
        # Exactly one new row went out: the rejected call rendered nothing.
        assert len(rows) == before + 1
        assert rows[-1]["items"][0]["question"] == WIRE_QUESTION
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_choose_accepts_any_code_from_the_candidate_set() -> None:
    """He answers the second round by voice. ``TH8015`` was never a leaf pill — it only
    ever existed inside the candidate set — and ``choose`` must still lock it, clearing
    the candidates and the question as the row goes green."""
    llm = ScriptedLlm(_script())
    agent, driver = await _host(llm)
    try:
        await driver.start_session(payload=PAYLOAD)
        checks.check_completed(await driver.user_says("टेल्मा दे दो"))
        checks.check_completed(await driver.user_says("एच वाली अस्सी"))

        matched = [c for c in driver.ui_commands if c.get("action") == "upsert_items"][-1]
        row = matched["items"][0]
        assert row["status"] == "matched"
        assert row["sku"]["code"] == "TH8015"
        assert row["quantity"] == 15
        assert row["candidates"] == [] and row["question"] is None
        # And with the row green, nothing is pending any more.
        checks.check_completed(await driver.user_says("कुछ नहीं"))
        assert "PENDING" not in llm.captured_system_instructions[-1]
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_a_group_pill_tap_narrows_the_mirror_through_state_sync() -> None:
    """The local-first half of §7-bis. The pharmacist taps *Plain Telma* himself; the
    frontend narrows the row on the spot and the shrunken ``candidate_codes`` arrive in
    the next snapshot. The brain folds that back into its own candidate set, drops the
    question (he answered it with his thumb) and tells the next model call to ask the
    NEXT question over what is left — never to repeat the one already answered."""
    llm = ScriptedLlm(_script())
    agent, driver = await _host(llm)
    try:
        await driver.start_session(payload=PAYLOAD)
        checks.check_completed(await driver.user_says("टेल्मा दे दो"))

        await driver.send_client_message(
            "state_sync",
            {
                "screen": {
                    "screen": "order",
                    "items": [
                        {
                            "id": "li1",
                            "spoken_text": "telma",
                            "status": "multi_variant",
                            "sku_code": None,
                            "sku_name": None,
                            "pack_size": None,
                            "quantity": None,
                            "source": "agent",
                            "candidate_codes": ["T2015", "T4015", "T8015"],
                        }
                    ],
                    "total_mrp": 0.0,
                    "item_count": 1,
                    "confirmed": False,
                }
            },
        )
        await asyncio.sleep(0.1)

        checks.check_completed(await driver.user_says("अब क्या बाकी है?"))
        grounded = llm.captured_system_instructions[-1]
        assert "li1 (telma): narrowed to 3 — ask the next question or choose" in grounded
        assert "awaiting answer to" not in grounded
        # The snapshot the model reads is the browser's, and it agrees.
        assert '"candidate_codes": ["T2015", "T4015", "T8015"]' in grounded
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_the_mirror_carries_candidate_codes_for_the_snapshot_shape() -> None:
    """The grounding fallback speaks the browser's own ``SnapshotItem`` shape — including
    ``candidate_codes``, so the first beat of a call (before any ``state_sync``) and
    every beat after it read identically to the model."""
    desk = _wide_row()
    mirror = desk.mirror()
    assert mirror is not None
    assert mirror["items"][0]["candidate_codes"] == [w["code"] for w in W_FAMILY]
    assert mirror["items"][1]["candidate_codes"] == []

    # A snapshot that names a code the row never held is ignored, not trusted.
    desk.absorb({"li1": {"status": "multi_variant", "candidate_codes": ["NOPE"]}})
    assert len(desk.items["li1"].candidates) == 8
    # A genuine narrowing is folded in, and only ever downwards.
    desk.absorb({"li1": {"status": "multi_variant", "candidate_codes": ["TH4015", "TH8015"]}})
    assert [sku.code for sku in desk.items["li1"].candidates] == ["TH4015", "TH8015"]
    assert "narrowed to 2 — ask the next question or choose" in str(desk.pending(None))


async def test_a_small_multi_family_row_still_carries_its_brands_skus() -> None:
    """Change 1. A brand card is a control the pharmacist expects to *pick* with, and
    the browser can only narrow in place if the row is holding that family's SKUs. The
    union used to be dropped whenever it fell under the question floor, which is exactly
    the two-brand case the cards are for — so the card looked like a picker and behaved
    like a search box.

    What the *model* is told does not move with it: four candidates is still "ask which
    brand", not a candidate table it would be tempted to read out."""
    desk = od.OrderDesk(StubCatalog())
    row = od.LineItemView(id="li1", spoken_text="kwin")
    desk.items["li1"] = row
    desk._resolve_into(row, "kwin")

    assert row.status == "multi_family"
    assert [fam.family for fam in row.families] == ["4 QUIN", "COLDBEST"]
    # Three SKUs across the two brands — under the floor, and on the row all the same.
    assert [sku.code for sku in row.candidates] == ["Q4D5", "Q4O5", "CB10"]

    brief = desk._brief(row)
    assert brief["status"] == "multi_family"
    assert brief["ask_about"] == ["family"]
    assert "candidates" not in brief and "candidate_count" not in brief
    assert brief["options"] == [
        "4 QUIN — ENTOD · eye drops/ointment · 2 SKUs",
        "COLDBEST — MANKIND · tablets · 1 SKU",
    ]
    assert "li1 (kwin): which brand" in str(desk.pending(None))

    # And the widening a big multi_family gets is unchanged — from the floor up it is
    # still a candidate table and a splitting question.
    wide = od.LineItemView(id="li2", spoken_text="telma")
    desk._resolve_into(wide, "telma")
    assert len(wide.candidates) == 8
    assert desk._brief(wide)["candidate_count"] == 8


async def test_change_variant_swaps_inside_the_family_and_keeps_the_quantity() -> None:
    """Change 3's headline. The family is right and the variant wrong — the pharmacist
    should never have to delete the row and say it again. One matching sibling re-locks
    the row (quantity untouched); several hand it back to the ordinary question
    machinery; and the swap can never leave the brand already on the row."""
    llm = ScriptedLlm(_script())
    agent, driver = await _host(llm)
    try:
        await driver.start_session(payload=PAYLOAD)
        checks.check_completed(await driver.user_says("टेल्मा फोर्टी तीस स्ट्रिप और चार क्विन"))
        checks.check_completed(await driver.user_says("ड्रॉप्स वाला, दस"))
        checks.check_completed(await driver.user_says("ऑइंटमेंट वाला कर दो"))

        swapped = [c for c in driver.ui_commands if c.get("action") == "upsert_items"][-1]
        assert swapped["items"][0] == _row(
            id="li2",
            spoken_text="4 quin",
            query="4 quin",
            quantity=10,  # the number he said about the DROPS, carried across
            status="matched",
            sku=W_OINT,
            family="4 QUIN",
        )
        assert _tool_results(llm)[-1] == {
            "id": "li2",
            "status": "matched",
            "name": "4 QUIN EYE OINTMENT 5GM",
            "pack_size": "5GM",
            "mrp": 142.0,
            "scheme": "",
            "quantity": 10,
        }

        # Two siblings answer to "H", so the row becomes a question again rather than
        # locking one of them — and it keeps its thirty strips while it is a question.
        checks.check_completed(await driver.user_says("एच वाला कर दो"))
        asked = [c for c in driver.ui_commands if c.get("action") == "upsert_items"][-1]
        row = asked["items"][0]
        assert row["id"] == "li1" and row["status"] == "multi_variant"
        assert row["sku"] is None and row["quantity"] == 30
        assert [sku["code"] for sku in row["variants"]] == ["TH4015", "TH8015"]
        assert row["differing_axes"] == ["strength"]
        assert _tool_results(llm)[-1]["ask_about"] == ["strength"]
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_change_variant_never_leaves_the_family_and_never_lies() -> None:
    """The two refusals. A ``want`` that names another brand matches nothing — the tool
    only ever ranks the row's own family, so there is no path by which it could jump —
    and a miss leaves the row exactly as it was while *saying* it did not match. A
    silent no-op here would ship the wrong medicine under the right label."""
    desk = od.OrderDesk(StubCatalog())
    desk.items["li2"] = od.LineItemView(
        id="li2",
        spoken_text="4 quin",
        status="matched",
        family="4 QUIN",
        sku=od.SkuWire(**W_DROPS),
        quantity=10,
    )

    miss = await desk.change_variant("li2", "telma 40")
    assert "nothing in 4 QUIN matches 'telma 40'" in miss["error"]
    assert "UNCHANGED" in miss["error"]
    assert miss["ask_about"] == ["form", "pack_size"]
    assert miss["options"] == ["EYE DROPS 5ML ₹160", "EYE OINTMENT 5GM ₹142"]
    # The row really is untouched — same SKU, same quantity, still green.
    assert desk.items["li2"].sku is not None
    assert desk.items["li2"].sku.code == "Q4D5"
    assert desk.items["li2"].quantity == 10
    assert desk.items["li2"].status == "matched"

    # A row with no brand settled has nothing to swap within.
    desk.items["li3"] = od.LineItemView(id="li3", spoken_text="coldact", status="not_found")
    assert "no brand settled yet" in (await desk.change_variant("li3", "syrup"))["error"]

    # The English guard rides this tool on both arguments.
    assert "must be written in English letters" in str(
        (await desk.change_variant("li2", "ऑइंटमेंट"))["error"]
    )
    assert "must be written in English letters" in str(
        (await desk.change_variant("चार क्विन", "ointment"))["error"]
    )


async def test_adjust_quantity_is_relative_and_clamps_at_one() -> None:
    """A delta, not a number: "दस और डाल दो" adds ten to whatever the row already has.
    It never reaches zero — a row on the order is a row he wants at least one of, and
    "take it off" is a removal he should hear confirmed as one."""
    llm = ScriptedLlm(_script())
    agent, driver = await _host(llm)
    try:
        await driver.start_session(payload=PAYLOAD)
        checks.check_completed(await driver.user_says("टेल्मा फोर्टी तीस स्ट्रिप और चार क्विन"))

        checks.check_completed(await driver.user_says("दस और डाल दो"))
        assert _tool_results(llm)[-1] == {
            "id": "li1",
            "status": "matched",
            "was": 30,
            "quantity": 40,
        }

        checks.check_completed(await driver.user_says("बहुत कम कर दो"))
        assert _tool_results(llm)[-1] == {
            "id": "li1",
            "status": "matched",
            "was": 40,
            "quantity": 1,  # clamped, not zeroed
        }
        row = [c for c in driver.ui_commands if c.get("action") == "upsert_items"][-1]
        assert row["items"][0]["quantity"] == 1
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_a_row_can_be_named_instead_of_numbered() -> None:
    """Voice rarely has "li1" to hand, so every row-editing tool takes the product name
    too. The tolerance is a ladder — the exact id, then a whole-name match, then
    containment — and it stops at the first rung that answers."""
    llm = ScriptedLlm(_script())
    agent, driver = await _host(llm)
    try:
        await driver.start_session(payload=PAYLOAD)
        checks.check_completed(await driver.user_says("टेल्मा फोर्टी तीस स्ट्रिप और चार क्विन"))
        checks.check_completed(await driver.user_says("टेल्मा फोर्टी बारह कर दो"))

        assert _tool_results(llm)[-1] == {"id": "li1", "status": "matched", "quantity": 12}
        row = [c for c in driver.ui_commands if c.get("action") == "upsert_items"][-1]
        assert row["items"][0]["id"] == "li1" and row["items"][0]["quantity"] == 12
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_an_ambiguous_reference_is_a_question_not_a_guess() -> None:
    """Two rows of the same brand, and "telma" names both. The tools on the other side
    of this delete rows and swap medicines, so a tie is never broken — it comes back as
    a retriable error naming the ids, and nothing on the order moves."""
    desk = od.OrderDesk(StubCatalog())
    desk.items["li1"] = od.LineItemView(
        id="li1",
        spoken_text="telma 40",
        status="matched",
        family="TELMA",
        sku=od.SkuWire(**W_TELMA),
        quantity=30,
    )
    desk.items["li2"] = od.LineItemView(
        id="li2",
        spoken_text="telma h 80",
        status="matched",
        family="TELMA",
        sku=od.SkuWire(**W_FAMILY[4]),
        quantity=10,
    )

    ambiguous = await desk.set_quantity("telma", 5)
    assert "matches 2 rows" in ambiguous["error"] and "Do not guess" in ambiguous["error"]
    assert ambiguous["matching_ids"] == ["li1", "li2"]
    assert desk.items["li1"].quantity == 30 and desk.items["li2"].quantity == 10

    # A deletion cannot be walked back by tapping, so an ambiguous ref removes NOTHING —
    # not even the rows that were unambiguous in the same call.
    kept = await desk.remove_items(["telma"])
    assert kept["matching_ids"] == ["li1", "li2"]
    assert list(desk.items) == ["li1", "li2"]

    # The containment rung: "telma h" is only one of them.
    named = desk._row_for("telma h")
    assert named is not None and named.id == "li2"
    # The id still wins outright, even though "li1" spells no product.
    assert desk._row_for("li1") is desk.items["li1"]
    assert desk._row_for("shelcal") is None

    # A Devanagari reference is the English error, not "no such item" — otherwise the
    # model goes looking for a row instead of transliterating.
    assert "must be written in English letters" in str(
        (await desk.adjust_quantity("टेल्मा", 5))["error"]
    )
    assert (await desk.adjust_quantity("shelcal", 5))["error"].startswith("no such item")


async def test_absorb_folds_a_manual_sku_swap_back_into_the_mirror() -> None:
    """Change 4, at unit level. If the pharmacist changes the SKU by hand — the inline
    variant strip, or a pick out of the search panel — the mirror must follow, or a
    later ``change_variant`` re-resolves from the family he already moved off. The
    catalog stays the authority on what a code *is*: a code it cannot confirm changes
    nothing at all."""
    desk = _wide_row()
    assert desk.items["li1"].sku is None

    desk.absorb({"li1": {"status": "matched", "sku_code": "TH8015", "quantity": 15}})
    row = desk.items["li1"]
    assert row.sku is not None and row.sku.code == "TH8015"
    assert row.status == "matched"
    assert row.candidates == [] and row.question is None and row.differing_axes == []
    assert row.quantity == 15
    # The fallback mirror now speaks the same SKU the browser is showing.
    mirror = desk.mirror()
    assert mirror is not None
    assert mirror["items"][0]["sku_code"] == "TH8015"
    assert desk.pending(None) is None or "li1" not in str(desk.pending(None))

    # A code the catalog cannot confirm is ignored — the mirror never invents a SKU the
    # browser merely asserted.
    desk.absorb({"li2": {"status": "matched", "sku_code": "NOPE"}})
    assert desk.items["li2"].sku is None
    assert desk.items["li2"].status == "multi_variant"


async def test_a_manual_sku_swap_reaches_the_next_model_call() -> None:
    """The same fold, on the wire and end to end. The pharmacist swaps 4 QUIN's drops
    for the ointment with his thumb; the snapshot carries the new code, the next model
    call's system instruction shows it, the PENDING line drops the row, and the brain's
    own mirror has moved with it."""
    brains: list[OrderDeskBrain] = []
    llm = ScriptedLlm(_script())
    agent, driver = await _host(llm, brains=brains)
    try:
        await driver.start_session(payload=PAYLOAD)
        first = await driver.user_says("टेल्मा फोर्टी तीस स्ट्रिप और चार क्विन")
        desk = brains[0].desk
        assert desk.items["li2"].sku is None  # the agent never resolved it
        assert "li2 (4 quin): form" in llm.captured_system_instructions[-1]

        await driver.send_client_message(
            "state_sync",
            {
                "screen": {
                    "screen": "order",
                    "items": [
                        {
                            "id": "li1",
                            "spoken_text": "telma 40",
                            "status": "matched",
                            "sku_code": "T4015",
                            "sku_name": "TELMA 40 TAB",
                            "pack_size": "15'S",
                            "quantity": 30,
                            "source": "agent",
                            "candidate_codes": [],
                        },
                        {
                            "id": "li2",
                            "spoken_text": "4 quin",
                            "status": "matched",
                            "sku_code": "Q4O5",
                            "sku_name": "4 QUIN EYE OINTMENT 5GM",
                            "pack_size": "5GM",
                            "quantity": 7,
                            "source": "agent",
                            "candidate_codes": [],
                        },
                    ],
                    "total_mrp": 5644.0,
                    "item_count": 2,
                    "confirmed": False,
                }
            },
        )
        await asyncio.sleep(0.1)

        turn = await driver.user_says("अब क्या बाकी है?")
        checks.check_completed(turn)
        grounded = llm.captured_system_instructions[-1]
        cart = json.loads(grounded.split(od._SCREEN_HEADER)[-1].split("\n")[0])
        assert [item["sku_code"] for item in cart["items"]] == ["T4015", "Q4O5"]
        assert cart["items"][1]["sku_name"] == "4 QUIN EYE OINTMENT 5GM"
        assert "PENDING" not in grounded, grounded[-400:]

        # …and the mirror followed, so the next change_variant starts from the ointment
        # rather than from the row the agent last knew about.
        assert desk.items["li2"].sku is not None
        assert desk.items["li2"].sku.code == "Q4O5"
        assert desk.items["li2"].status == "matched"
        assert desk.items["li2"].quantity == 7
        checks.check_no_unsolicited_interactions(
            driver, opened={first.interaction_id, turn.interaction_id}
        )
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_list_variants_answers_the_change_variant_strip_without_speaking() -> None:
    """Change 2's brain half. The Change-variant control on a matched row asks for its
    siblings and gets them back **floor-free** — no inference, no speech, no interaction
    — exactly like the search bar. A tap must never make the agent talk over him.

    An unknown family answers empty rather than raising: he tapped a control, and a
    control that throws is worse than one that says nothing is there."""
    llm = ScriptedLlm(_script())
    agent, driver = await _host(llm)
    try:
        await driver.start_session(payload=PAYLOAD)
        first = await driver.user_says("टेल्मा फोर्टी तीस स्ट्रिप और चार क्विन")
        before = len(llm.captured_contents)

        await driver.send_client_message("list_variants", {"item_id": "li1", "family": "TELMA"})
        await asyncio.sleep(0.2)

        # The class name IS the wire name — `uiCommands.ts` is mirrored from it.
        assert od.ShowVariants.__voqal_action__ == "show_variants"
        cmd = next(c for c in driver.ui_commands if c.get("action") == "show_variants")
        assert cmd == {
            "type": "ui_command",
            "action": "show_variants",
            "action_id": 6,
            "item_id": "li1",
            "family": "TELMA",
            "results": W_FAMILY,
            # What the strip labels its pills by — the family name is what they share.
            "differing_axes": ["variant_label", "strength"],
        }
        # No model call, no interaction: the strip is silent by construction.
        assert len(llm.captured_contents) == before
        checks.check_no_unsolicited_interactions(driver, opened={first.interaction_id})

        await driver.send_client_message("list_variants", {"item_id": "li1", "family": "NOPE"})
        await asyncio.sleep(0.2)
        empty = [c for c in driver.ui_commands if c.get("action") == "show_variants"][-1]
        assert empty == {
            "type": "ui_command",
            "action": "show_variants",
            "action_id": 7,
            "item_id": "li1",
            "family": "NOPE",
            "results": [],
            "differing_axes": [],
        }
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_devanagari_in_a_tool_argument_is_rejected_and_retried() -> None:
    """The English-only guard, on the wire. The first ``add_items`` carries Devanagari;
    it never reaches the catalog and nothing lands on screen. The model is handed a
    *retriable* tool error naming the field and what to do, and its second call — the
    same item transliterated — goes through."""
    catalog = StubCatalog()
    llm = ScriptedLlm(_script())
    agent, driver = await _host(llm, catalog)
    try:
        await driver.start_session(payload=PAYLOAD)
        checks.check_completed(await driver.user_says("वोलिनी दे दो"))

        errors = [r for r in _tool_results(llm) if "error" in r]
        assert errors, _tool_results(llm)
        message = str(errors[0]["error"])
        assert "must be written in English letters" in message
        assert "'volini'" in message

        # The rejected call never touched the catalog; only the retry did.
        assert catalog.resolved == [("volini", None, None)]
        # And only the retry put a row on screen — with the brain's first id.
        rows = [c for c in driver.ui_commands if c.get("action") == "upsert_items"]
        assert [r["items"][0]["id"] for r in rows] == ["li1", "li1"]
        assert rows[-1]["items"][0]["status"] == "not_found"
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_the_english_guard_covers_both_paths() -> None:
    """The same rule, unit-level, on the two mechanisms it rides: the pydantic argument
    model (whose ``ValueError`` the SDK's coercion layer turns into the tool error the
    test above sees) and the in-body check the plain-``str`` tools run."""
    with pytest.raises(Exception) as excinfo:
        od.SpokenItem(text="वोलिनी")
    assert "must be written in English letters" in str(excinfo.value)

    # Every string field is guarded, not just `text`.
    with pytest.raises(Exception):
        od.SpokenItem(text="volini", form_hint="जेल")
    assert od.SpokenItem(text="volini gel 50 gm", quantity=5).text == "volini gel 50 gm"

    desk = od.OrderDesk(StubCatalog())
    # Plain-str tools answer with the same message, before any catalog work — no
    # `voice()` context is needed to reach the guard.
    assert "must be written in English letters" in str(
        (await desk.refine_item("li1", "अबीवेज़"))["error"]
    )
    assert "must be written in English letters" in str(
        (await desk.highlight("li1", "कौन सा?"))["error"]
    )


async def test_typed_actions_pin_the_whole_ui_command_envelope() -> None:
    """The cross-language contract, asserted as literals.

    The sibling tests check the *arguments*; this one checks the **entire message**,
    envelope keys included, for all five typed actions — because the envelope is what
    the React ``useUiCommand`` hook strips, and ``frontend/src/uiCommands.ts`` is
    hand-mirrored from these ``Action`` classes. The wire name is checked against the
    class too: it is *derived* from the class name, so renaming ``UpsertItems`` would
    silently rename the command the UI listens for."""
    llm = ScriptedLlm(_script())
    agent, driver = await _host(llm)
    try:
        await driver.start_session(payload=PAYLOAD)
        checks.check_completed(await driver.user_says("टेल्मा फोर्टी तीस स्ट्रिप और चार क्विन"))
        checks.check_completed(await driver.user_says("ड्रॉप्स वाला, दस"))
        checks.check_completed(await driver.user_says("वो वाली दवा"))
        checks.check_completed(await driver.user_says("चार क्विन हटा दो"))
        await driver.send_client_message("catalog_search", {"query": "cold"})
        await asyncio.sleep(0.2)

        # The class name IS the wire name — the coupling the UI depends on.
        assert od.UpsertItems.__voqal_action__ == "upsert_items"
        assert od.RemoveItems.__voqal_action__ == "remove_items"
        assert od.HighlightItem.__voqal_action__ == "highlight_item"
        assert od.ShowSearchResults.__voqal_action__ == "show_search_results"
        assert od.OrderNote.__voqal_action__ == "order_note"

        cmds = [c for c in driver.ui_commands if not str(c.get("action", "")).startswith("__")]
        by_action = {str(c.get("action")): c for c in cmds}

        # #1: the first row, greyed, the instant it was heard.
        assert cmds[0] == {
            "type": "ui_command",
            "action": "upsert_items",
            "action_id": 1,
            "items": [_row(id="li1", spoken_text="telma 40", query="telma 40", quantity=30)],
        }
        # #2: the same row, resolved — the full matched render state.
        assert cmds[1] == {
            "type": "ui_command",
            "action": "upsert_items",
            "action_id": 2,
            "items": [
                _row(
                    id="li1",
                    spoken_text="telma 40",
                    query="telma 40",
                    quantity=30,
                    status="matched",
                    sku=W_TELMA,
                    family="TELMA",
                )
            ],
        }
        assert cmds[2] == {
            "type": "ui_command",
            "action": "order_note",
            "action_id": 3,
            "text": "TELMA 40 TAB — scheme: 10 + 1",
        }
        # #5: the ambiguous row, with the pills and the axis the UI groups them by.
        assert cmds[4] == {
            "type": "ui_command",
            "action": "upsert_items",
            "action_id": 5,
            "items": [
                _row(
                    id="li2",
                    spoken_text="4 quin",
                    query="4 quin",
                    status="multi_variant",
                    family="4 QUIN",
                    variants=[W_DROPS, W_OINT],
                    differing_axes=["form"],
                )
            ],
        }
        # `choose` locks the row to one SKU and clears the pills. (No scheme banner
        # here — the drops carry no scheme, and only real ones are ever announced.)
        assert cmds[5] == {
            "type": "ui_command",
            "action": "upsert_items",
            "action_id": 6,
            "items": [
                _row(
                    id="li2",
                    spoken_text="4 quin",
                    query="4 quin",
                    quantity=10,
                    status="matched",
                    sku=W_DROPS,
                    family="4 QUIN",
                )
            ],
        }
        assert by_action["highlight_item"] == {
            "type": "ui_command",
            "action": "highlight_item",
            "action_id": 7,
            "id": "li1",
            "note": "which strength?",
        }
        assert by_action["remove_items"] == {
            "type": "ui_command",
            "action": "remove_items",
            "action_id": 8,
            "ids": ["li2"],
        }
        assert by_action["show_search_results"] == {
            "type": "ui_command",
            "action": "show_search_results",
            "action_id": 9,
            "query": "cold",
            "results": [W_COLD],
        }
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_state_sync_grounds_the_next_prompt_with_the_pending_line() -> None:
    """The browser's cart — authoritative, because it carries the manual edits — lands
    in the *system instruction* of the next model call, together with the PENDING line
    naming the rows still waiting on a question.

    The snapshot here says the pharmacist tapped the drops pill himself: li2 is
    matched on screen while the brain's own mirror still has it ambiguous. The screen
    wins, so the model is never told to ask about a row he already answered."""
    llm = ScriptedLlm(_script())
    agent, driver = await _host(llm)
    try:
        await driver.start_session(payload=PAYLOAD)
        first = await driver.user_says("टेल्मा फोर्टी तीस स्ट्रिप और चार क्विन")
        # Before any snapshot the brain's own mirror grounds the call, and li2 is
        # pending on the axis the tool reported.
        mirror_grounded = llm.captured_system_instructions[-1]
        assert "CURRENT ORDER SCREEN (authoritative" in mirror_grounded
        assert '"sku_code": "T4015"' in mirror_grounded
        assert "PENDING" in mirror_grounded
        assert "li2 (4 quin): form" in mirror_grounded

        await driver.send_client_message(
            "state_sync",
            {
                "screen": {
                    "screen": "order",
                    "items": [
                        {
                            "id": "li1",
                            "spoken_text": "telma 40",
                            "status": "matched",
                            "sku_code": "T4015",
                            "sku_name": "TELMA 40 TAB",
                            "pack_size": "15'S",
                            "quantity": 30,
                            "source": "agent",
                        },
                        {
                            "id": "li2",
                            "spoken_text": "4 quin",
                            "status": "matched",
                            "sku_code": "Q4D5",
                            "sku_name": "4 QUIN EYE DROPS 5ML",
                            "pack_size": "5ML",
                            "quantity": 10,
                            "source": "agent",
                        },
                    ],
                    "total_mrp": 6250.0,
                    "item_count": 2,
                    "confirmed": False,
                }
            },
        )
        # Same socket, ordered delivery — a beat so the brain has ingested it before
        # the next turn's model call assembles its instruction.
        await asyncio.sleep(0.1)

        turn = await driver.user_says("अब क्या बाकी है?")
        checks.check_completed(turn)
        grounded = llm.captured_system_instructions[-1]
        assert "CURRENT ORDER SCREEN (authoritative" in grounded
        assert '"sku_name": "4 QUIN EYE DROPS 5ML"' in grounded, grounded[-800:]
        assert '"total_mrp": 6250.0' in grounded
        # The pill he tapped himself closed the only pending question.
        assert "PENDING" not in grounded, grounded[-800:]

        # A client message the brain only records must not open an interaction.
        checks.check_no_unsolicited_interactions(
            driver, opened={first.interaction_id, turn.interaction_id}
        )
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_grounding_is_absent_until_there_is_a_screen() -> None:
    """Nothing on screen, nothing appended — the first prompt of a call is the bare
    system instruction plus the pharmacy context, with no empty cart JSON in it."""
    brain = OrderDeskBrain(model=ScriptedLlm({}), catalog=StubCatalog())
    assert brain.grounding() is None
    brain.desk.items["li1"] = od.LineItemView(id="li1", spoken_text="volini", status="not_found")
    text = brain.grounding()
    assert text is not None
    assert text.startswith("CURRENT ORDER SCREEN (authoritative")
    assert "not in catalog" in text


async def test_catalog_search_answers_the_search_bar_without_speaking() -> None:
    """The manual search bar: ``catalog_search`` is answered with a **floor-free**
    ``show_search_results`` — no inference, no speech, no interaction. He is typing;
    the agent must not start talking because of a keystroke."""
    llm = ScriptedLlm(_script())
    agent, driver = await _host(llm)
    try:
        await driver.start_session(payload=PAYLOAD)
        before = len(llm.captured_contents)

        await driver.send_client_message("catalog_search", {"query": "cold"})
        await asyncio.sleep(0.2)

        cmd = next(c for c in driver.ui_commands if c.get("action") == "show_search_results")
        assert cmd["query"] == "cold"
        assert cmd["results"] == [W_COLD]
        # No model call, no interaction: the search bar is silent by construction.
        assert len(llm.captured_contents) == before
        checks.check_no_unsolicited_interactions(driver, opened=set())

        # A one-character query is below the search floor and answers empty.
        await driver.send_client_message("catalog_search", {"query": "c"})
        await asyncio.sleep(0.2)
        last = [c for c in driver.ui_commands if c.get("action") == "show_search_results"][-1]
        assert last == {
            "type": "ui_command",
            "action": "show_search_results",
            "action_id": 2,
            "query": "c",
            "results": [],
        }
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_corrections_by_voice_edit_the_row_in_place() -> None:
    """The three correction tools, and the conversation they leave behind: a quantity
    change never re-adds, a removal drops exactly the named row, and ``refine_item``
    re-resolves the SAME row (keeping its id) when he clarifies a brand that sounds
    like another."""
    llm = ScriptedLlm(_script())
    agent, driver = await _host(llm)
    try:
        await driver.start_session(payload=PAYLOAD)
        checks.check_completed(await driver.user_says("अबेविया चाहिए"))
        checks.check_completed(await driver.user_says("अबीवेज़ वाला"))

        rows = [c for c in driver.ui_commands if c.get("action") == "upsert_items"]
        # Same id throughout: refine_item is an edit, not a second row.
        assert {r["items"][0]["id"] for r in rows} == {"li1"}
        assert rows[-1]["items"][0]["status"] == "matched"
        assert rows[-1]["items"][0]["query"] == "abiways"
        assert rows[-1]["items"][0]["families"] == []

        state = await driver.dump_conversation()
        checks.check_conversation_sequence(
            state,
            expected=[
                {"role": "assistant", "content": HELLO + OPENER},
                {"role": "user", "content": "अबेविया चाहिए"},
                {"role": "assistant", "content": "देखती हूँ।"},
                {"role": "assistant", "content": "कौन सा ब्रांड — स्क्रीन पर देखिए?"},
                {"role": "user", "content": "अबीवेज़ वाला"},
                {"role": "assistant", "content": "लग गया।"},
            ],
        )
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_quantity_and_removal_keep_the_mirror_honest() -> None:
    """``set_quantity`` edits in place and ``remove_items`` drops the row from the
    brain's own mirror too — so the next prompt's grounding cannot describe a cart the
    pharmacist no longer has."""
    llm = ScriptedLlm(_script())
    agent, driver = await _host(llm)
    try:
        await driver.start_session(payload=PAYLOAD)
        checks.check_completed(await driver.user_says("टेल्मा फोर्टी तीस स्ट्रिप और चार क्विन"))
        checks.check_completed(await driver.user_says("टेल्मा बारह कर दो"))
        checks.check_completed(await driver.user_says("चार क्विन हटा दो"))

        rows = [c for c in driver.ui_commands if c.get("action") == "upsert_items"]
        assert rows[-1]["items"][0] == _row(
            id="li1",
            spoken_text="telma 40",
            query="telma 40",
            quantity=12,
            status="matched",
            sku=W_TELMA,
            family="TELMA",
        )
        removed = next(c for c in driver.ui_commands if c.get("action") == "remove_items")
        assert removed["ids"] == ["li2"]

        checks.check_completed(await driver.user_says("कुछ नहीं"))
        grounded = llm.captured_system_instructions[-1]
        cart = json.loads(
            grounded.split("CURRENT ORDER SCREEN (authoritative — reflects manual edits): ")[-1]
        )
        assert [item["id"] for item in cart["items"]] == ["li1"]
        assert cart["items"][0]["quantity"] == 12
        assert cart["item_count"] == 1
    finally:
        await driver.aclose()
        await agent.aclose()


# ─── the language contract (Hindi audio, English screen) ──────────────────────


async def test_the_brain_puts_hindi_on_both_legs_before_it_greets() -> None:
    """The call is Hindi on both legs, and the brain is the *only* thing making it
    so — ``OrderDeskBrain.language``/``voice``, applied by the SDK on the way into
    ``on_session_start``.

    It used to be the browser's per-session pipeline instead, and this test used to
    read that pipeline out of ``config.ts`` as text. Both moved for the same reason:
    a page and an agent record each held half the answer, and when one link dropped
    the field the model still wrote Devanagari while an en-IN reference voice read
    it aloud. Nothing automated caught it — the transcript is word-perfect and
    accent is invisible to transcription-based scoring — so it shipped, and was
    found by ear weeks later.

    Two properties, both load-bearing:

    * **Both halves.** ``configure_language`` moves the recognizer and the voice
      together. PyGato picks the recognition engine from ``language_hint``, which it
      derives from the TTS-side language; a config that sets only one of the pair
      transcribes Hindi with the English model, and the failure then reads as bad
      recognition rather than bad config.
    * **Before the greeting.** A settings frame that lands after the first audio is
      worse than useless — the caller has already heard the wrong voice say hello.
    """
    llm = ScriptedLlm(_script())
    agent, driver = await _host(llm)
    try:
        await driver.start_session(payload=PAYLOAD)

        tts = [r for r in driver.log if isinstance(r.frame, UpdateTTSSettingsFrame)]
        stt = [r for r in driver.log if isinstance(r.frame, UpdateSTTSettingsFrame)]
        assert [dict(r.frame.settings) for r in tts] == [
            {"voice": "omnivoice/gauri", "language": "hi"}
        ]
        assert [dict(r.frame.settings) for r in stt] == [{"language_hint": "hi"}]

        greeting_at = next(i for i, r in enumerate(driver.log) if isinstance(r.frame, LLMTextFrame))
        first_tts = next(
            i for i, r in enumerate(driver.log) if isinstance(r.frame, UpdateTTSSettingsFrame)
        )
        first_stt = next(
            i for i, r in enumerate(driver.log) if isinstance(r.frame, UpdateSTTSettingsFrame)
        )
        assert first_tts < greeting_at, "the Hindi voice landed after the greeting audio"
        assert first_stt < greeting_at, "the Hindi recognizer landed after the greeting"
    finally:
        await driver.aclose()
        await agent.aclose()
