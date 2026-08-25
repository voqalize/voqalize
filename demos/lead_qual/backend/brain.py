"""LeadQualBrain — the Auric Gold Finance gold-loan lead-qualification advisor.

A ``voqalize.sdk.Brain`` (LLM + Auric Gold Finance tools + per-session language
state). Voqalize dials this brain's WebSocket per session; ``respond`` (inherited
from :class:`GeminiBrain`) runs the manual Gemini function-calling loop where
**each LLM call is one ``interaction.say()`` bracket** (1:1 with the wire):
speak a short line, call a tool, feed the result back.

The three tools are:

- ``check_eligibility`` — deterministic Auric Gold Finance gold-loan rules, returns
  ``{eligible, reason}`` for the model to translate;
- ``switch_language`` — re-point STT + TTS to another Indic language mid-call;
- ``end_call`` — record the outcome and tell the browser the call has ended.

The LLM is **dependency-injected** as a :class:`GeminiProvider`; the brain owns
only the prompt, the tool schemas, and this session's language/payload state. The
conversation record is framework-owned (the SDK keeps the heard-text transcript
in ``interaction.conversation``), rebuilt into Gemini's working context each turn
by the :class:`GeminiBrain` base.

Both browser-facing behaviours use the public SDK surface: ``end_call`` renders
the end screen via ``interaction.action("call_ended", …)`` (the ``ui_command``
envelope every demo page reads), and ``switch_language`` swaps the recognition
language via ``session.configure_stt(language_hint=…)`` alongside the TTS change.
"""

from __future__ import annotations

from typing import Any

from google.genai import types
from loguru import logger
from voqalize_demos import DEFAULT_MODEL, GeminiBrain, GeminiProvider, hello_for

# ─── Language tables ───────────────────────────────────────────────────────────

# (STT language_hint, tts_voice, tts_language, display_name) for vql-speech.
# Auric Gold Finance is Indic-only: STT stays on vql-stt, TTS on OmniVoice
# (omnivoice/gauri) for the whole session — switching only moves the
# language_hint among these Indic languages, never the STT model or TTS engine.
_STATE_LANG: dict[str, tuple[str, str, str, str]] = {
    "Andhra Pradesh": ("te", "omnivoice/gauri", "te", "Telugu"),
    "Telangana": ("te", "omnivoice/gauri", "te", "Telugu"),
    "Tamil Nadu": ("ta", "omnivoice/gauri", "ta", "Tamil"),
    "Karnataka": ("kn", "omnivoice/gauri", "kn", "Kannada"),
    "Kerala": ("ml", "omnivoice/gauri", "ml", "Malayalam"),
    "Maharashtra": ("mr", "omnivoice/gauri", "mr", "Marathi"),
    "Goa": ("mr", "omnivoice/gauri", "mr", "Marathi"),
    "Gujarat": ("gu", "omnivoice/gauri", "gu", "Gujarati"),
    "West Bengal": ("bn", "omnivoice/gauri", "bn", "Bengali"),
}
_DEFAULT_LANG = ("hi", "omnivoice/gauri", "hi", "Hindi")

_LANG_BY_NAME: dict[str, tuple[str, str, str]] = {
    "Hindi": ("hi", "omnivoice/gauri", "hi"),
    "Telugu": ("te", "omnivoice/gauri", "te"),
    "Tamil": ("ta", "omnivoice/gauri", "ta"),
    "Kannada": ("kn", "omnivoice/gauri", "kn"),
    "Malayalam": ("ml", "omnivoice/gauri", "ml"),
    "Marathi": ("mr", "omnivoice/gauri", "mr"),
    "Gujarati": ("gu", "omnivoice/gauri", "gu"),
    "Bengali": ("bn", "omnivoice/gauri", "bn"),
}

_LANGUAGE_NAMES = list(_LANG_BY_NAME.keys())


# ─── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_INSTRUCTION = """You are Priya, a friendly Auric Gold Finance Gold Loan advisor on a follow-up call. The customer filled an enquiry form. Confirm their details, quickly check eligibility, answer questions, and collect a few more details.

LANGUAGE:
- Speak in the customer's language, always in its native script (Devanagari for Hindi, etc.).
- Write English loan words in that same native script — never in the English/Latin alphabet.
  Hindi example: "आपकी गोल्ड लोन की एन्क्वायरी मिली। आपके पास कितने ग्राम ज्वेलरी है?"
  (here गोल्ड लोन, एन्क्वायरी, ग्राम, ज्वेलरी are English words written in Devanagari.)
- Simple words, short sentences. One question per turn, at most 3 sentences.
- If the user requests another language, call switch_language, then continue in that language and its native script.

SPEECH-TO-TEXT: The transcription can mishear words and numbers. Be accommodating — if something seems unclear or inconsistent, gently confirm instead of assuming. Never correct the customer's wording; infer their intent charitably.

STEP 1 — Confirm and check eligibility:
- Confirm or ask: gold weight, desired loan amount, and gold type (jewellery vs coins or bars).
- Once you have weight, loan amount, and jewellery confirmation, tell the customer you are checking, then call check_eligibility.
- Not eligible: explain the reason in their language, answer questions, call end_call(outcome='ineligible').
- Eligible: go to Step 2.

STEP 2 — Collect details, one question per turn:
- Purpose of the loan?
- How soon are the funds needed?
- Branch visit or home visit?
Then invite final questions, mention the nearest branch, say goodbye, call end_call(outcome='qualified').
If a question stays unanswered after two tries, say a brief goodbye and call end_call with the right outcome.
Always pass end_call arguments in English.

AURIC GOLD FINANCE FACTS — answer only from these:
- Loan range: 3000 to 1 crore rupees. Auric accepts household gold jewellery only — no coins or bars, in line with RBI guidelines.
- Interest from 12 percent per year. LTV up to 75 percent; roughly 10000 rupees per gram, final amount after branch assessment.
- Tenure 3 to 12 months. No prepayment penalty for individuals.
- Same-day disbursement at branch. Doorstep service for loans above 50000 rupees, funds in 30 minutes.
- Documents: any KYC identity proof plus address proof. PAN card mandatory.
- Repayment: UPI, debit card, net banking, or branch.
- Ornaments kept in insured strong rooms with round-the-clock surveillance.

VOICE RULES:
- Under 25 words per response. One question per turn.
- Tell the customer what you are doing before any tool call.
- No markdown, lists, or symbols. Write the words rupees, percent, grams — never the symbols.
- Speak numbers naturally as they would be heard."""


# ─── Deterministic eligibility rules ───────────────────────────────────────────


def _check_gold_eligibility(
    is_jewellery: bool,
    gold_weight_grams: float,
    loan_amount_thousands: int,
    tenure_months: int | None,
) -> dict[str, Any]:
    """Deterministic eligibility rules. All output is in English."""
    loan_inr = loan_amount_thousands * 1000
    if not is_jewellery:
        return {
            "eligible": False,
            "reason": "Auric Gold Finance accepts household gold jewellery only, in line with RBI guidelines. Coins and bars are not eligible.",
        }
    if loan_inr < 3_000:
        return {
            "eligible": False,
            "reason": f"Minimum loan amount is 3000 rupees. The requested {loan_inr} rupees is below the minimum.",
        }
    if loan_inr > 10_000_000:
        return {
            "eligible": False,
            "reason": f"Maximum loan amount is 1 crore rupees. The requested {loan_inr} rupees exceeds the maximum.",
        }
    if tenure_months is not None and not (3 <= tenure_months <= 12):
        return {
            "eligible": False,
            "reason": f"Tenure must be between 3 and 12 months. {tenure_months} months is outside our range.",
        }
    return {
        "eligible": True,
        "reason": (
            f"Eligible. {gold_weight_grams} grams of household ornaments, "
            f"loan of {loan_inr} rupees. "
            "Final amount confirmed after gold assessment at branch."
        ),
    }


def _resolve_initial_language(payload: dict[str, Any]) -> tuple[str, str, str, str]:
    """Pick (stt_lang, tts_voice, tts_lang, display_name) from payload."""
    override = str(payload.get("language", "")).strip()
    if override in _LANG_BY_NAME:
        stt, voice, tts = _LANG_BY_NAME[override]
        return (stt, voice, tts, override)
    state = str(payload.get("state", ""))
    return _STATE_LANG.get(state, _DEFAULT_LANG)


# ─── Tool schemas (JSON-schema dicts → google-genai Schema) ────────────────────

# (tool_name, description, properties, required)
_TOOLSPECS: list[tuple[str, str, dict[str, Any], list[str]]] = [
    (
        "end_call",
        "End the call and record the outcome. All arguments must be in English "
        "regardless of the conversation language. Use outcome='qualified' when all "
        "six questions are answered; a failure outcome when the call cannot proceed.",
        {
            "outcome": {
                "type": "string",
                "enum": ["qualified", "not_interested", "unresponsive", "ineligible", "other"],
                "description": "Final outcome of the call.",
            },
            "gold_form": {
                "type": "string",
                "enum": ["jewelry", "coins", "bars", "mixed"],
                "description": "Form of the customer's gold.",
            },
            "gold_weight_grams": {"type": "number", "description": "Gold weight in grams."},
            "loan_amount_inr": {"type": "number", "description": "Desired loan amount in rupees."},
            "loan_purpose": {"type": "string", "description": "Stated purpose of the loan."},
            "timeline": {
                "type": "string",
                "enum": ["immediate", "within_week", "within_month", "exploring"],
                "description": "How soon the customer needs funds.",
            },
            "preferred_next_step": {
                "type": "string",
                "enum": ["branch_visit", "home_visit"],
                "description": "Preferred next step.",
            },
        },
        ["outcome"],
    ),
    (
        "switch_language",
        "Switch the conversation to a different language when the user explicitly "
        "requests one. Before calling, acknowledge their request in 1 short sentence "
        "in the target language. Subsequent conversation continues in the new "
        "language and its native script.",
        {
            "language": {
                "type": "string",
                "enum": _LANGUAGE_NAMES,
                "description": "Target language.",
            },
        },
        ["language"],
    ),
    (
        "check_eligibility",
        "Check whether a customer qualifies for an Auric Gold Finance gold loan. Before "
        "calling, inform the user you are checking their eligibility. Returns "
        "{eligible, reason} in English — translate the reason for the customer.",
        {
            "is_jewellery": {
                "type": "boolean",
                "description": "True if the gold is household jewellery (not coins or bars).",
            },
            "gold_weight_grams": {"type": "number", "description": "Gold weight in grams."},
            "loan_amount_thousands": {
                "type": "integer",
                "description": "Desired loan amount in thousands of rupees (e.g. 50 = 50000).",
            },
            "tenure_months": {
                "type": "integer",
                "description": "Desired tenure in months (3 to 12).",
            },
        },
        ["is_jewellery", "gold_weight_grams", "loan_amount_thousands"],
    ),
]

_JSON_TO_GENAI = {
    "string": types.Type.STRING,
    "integer": types.Type.INTEGER,
    "number": types.Type.NUMBER,
    "boolean": types.Type.BOOLEAN,
    "object": types.Type.OBJECT,
    "array": types.Type.ARRAY,
}


def _to_schema(d: dict[str, Any]) -> types.Schema:
    """Convert a JSON-schema dict to a google-genai Schema (recursive)."""
    kw: dict[str, Any] = {"type": _JSON_TO_GENAI[d["type"]]}
    if d.get("description"):
        kw["description"] = d["description"]
    if d.get("enum"):
        kw["enum"] = d["enum"]
    if d["type"] == "object":
        props = d.get("properties") or {}
        kw["properties"] = {k: _to_schema(v) for k, v in props.items()}
        if d.get("required"):
            kw["required"] = d["required"]
    if d["type"] == "array":
        kw["items"] = _to_schema(d["items"])
    return types.Schema(**kw)


def _tools() -> types.ToolListUnion:
    decls = [
        types.FunctionDeclaration(
            name=name,
            description=desc,
            parameters=_to_schema({"type": "object", "properties": props, "required": req}),
        )
        for name, desc, props, req in _TOOLSPECS
    ]
    tools: types.ToolListUnion = [types.Tool(function_declarations=decls)]
    return tools


class LeadQualBrain(GeminiBrain):
    """One per session. The Auric Gold Finance gold-loan advisor: LLM + eligibility/
    language/end-call tools + this session's language and enquiry-form state.
    ``on_interaction`` is the inherited tool-loop ``respond``; :meth:`dispatch_tool`
    runs each call."""

    def __init__(self, *, llm: GeminiProvider, model: str = DEFAULT_MODEL) -> None:
        super().__init__(
            llm=llm, system_instruction=_SYSTEM_INSTRUCTION, tools=_tools(), model=model
        )
        # Per-session state, set for real in on_session_start once the init payload
        # (name/state/city/gold_weight/loan_amount/…) arrives on the VqlStartFrame.
        self.payload: dict[str, Any] = {}
        self.language_name: str = _DEFAULT_LANG[3]
        self.ended = False

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session, start) -> None:
        # The enquiry-form payload rides the start frame. Resolve the initial
        # language, then open with a hybrid greeting: a language-appropriate hello
        # is spoken instantly (no LLM call), and the personalised, native-script
        # remainder streams in behind it.
        payload = dict(start.init)
        self.payload = payload
        _stt_lang, voice, tts_lang, self.language_name = _resolve_initial_language(payload)

        # Apply the resolved language BEFORE speaking. This brain is the only
        # thing that knows it — the language comes from the enquiry form's state
        # (Tamil Nadu → Tamil), which does not exist until this session starts, so
        # no agent-level setting could ever have been right. Until this call
        # existed the resolved pair was thrown away and only the display name
        # kept, so a Tamil customer got a Tamil hello read by the *Hindi* voice
        # and transcribed by the *Hindi* recognizer, on the greeting, every time.
        #
        # Ordering is load-bearing and measured: a settings frame emitted here is
        # on the same ordered lane as the speech that follows, so it lands on the
        # greeting rather than the turn after it.
        session.configure_language(tts_lang, voice=voice)

        await self.say_then_generate(
            session, hello_for(self.language_name), self._greeting_instruction(payload)
        )

    def _greeting_instruction(self, payload: dict[str, Any]) -> str:
        """Developer-message content that drives the model's opening turn."""
        name = str(payload.get("name", "Customer"))
        state = str(payload.get("state", ""))
        city = str(payload.get("city", ""))
        gold_weight = str(payload.get("gold_weight", ""))
        loan_amount = str(payload.get("loan_amount", ""))
        parts = [
            f"Customer name: {name}. Customer from {city}, {state}.",
            f"Speak {self.language_name} in native script.",
        ]
        if gold_weight:
            parts.append(f"Form already has gold weight: {gold_weight} grams.")
        if loan_amount:
            parts.append(f"Form already has loan amount: {loan_amount} rupees.")
        parts.append(
            "Greet the customer and let them know you want to ask a few questions "
            "about their gold loan application. One or two short sentences."
        )
        return " ".join(parts)

    # ─── Tools ──────────────────────────────────────────────────────────

    def dispatch_tool(self, interaction, name: str, args: dict[str, Any]) -> str:
        """Run one tool call: mutate session state + drive STT/TTS/the browser;
        return a short string result fed back to the model."""
        logger.info("lead-qual: tool {} {}", name, dict(args))
        if name == "check_eligibility":
            return self._check_eligibility(args)
        if name == "switch_language":
            return self._switch_language(interaction, args)
        if name == "end_call":
            return self._end_call(interaction, args)
        return "unknown tool"

    def _check_eligibility(self, args: dict[str, Any]) -> str:
        tenure = args.get("tenure_months")
        result = _check_gold_eligibility(
            is_jewellery=bool(args.get("is_jewellery")),
            gold_weight_grams=float(args.get("gold_weight_grams") or 0),
            loan_amount_thousands=int(args.get("loan_amount_thousands") or 0),
            tenure_months=(int(tenure) if tenure is not None else None),
        )
        logger.info("lead-qual: check_eligibility → {}", result)
        return str(result)

    def _switch_language(self, interaction, args: dict[str, Any]) -> str:
        language = str(args.get("language", ""))
        cfg = _LANG_BY_NAME.get(language)
        if not cfg:
            return str({"switched_to": self.language_name, "error": "unknown language"})
        stt_hint, tts_voice, tts_lang = cfg
        self.language_name = language
        logger.info(
            "lead-qual: switch_language → {} (hint={} voice={})", language, stt_hint, tts_voice
        )
        # One call moves both halves — recognizer and voice. This is the only
        # supported way to change language mid-call; doing it as a configure_tts
        # + configure_stt pair by hand is two calls that can drift, and either
        # half missing is silent (wrong recognizer transcribes badly; wrong voice
        # just sounds non-native).
        interaction.session.configure_language(tts_lang, voice=tts_voice)
        return str({"switched_to": language})

    def _end_call(self, interaction, args: dict[str, Any]) -> str:
        outcome = str(args.get("outcome", "other"))
        self.ended = True
        logger.info("lead-qual: end_call outcome={}", outcome)
        lead = {
            "name": str(self.payload.get("name", "")),
            "phone": str(self.payload.get("phone", "")),
            "state": str(self.payload.get("state", "")),
            "city": str(self.payload.get("city", "")),
            "gold_form": args.get("gold_form"),
            "gold_weight_grams": args.get("gold_weight_grams"),
            "loan_amount_inr": args.get("loan_amount_inr"),
            "loan_purpose": args.get("loan_purpose"),
            "timeline": args.get("timeline"),
            "preferred_next_step": args.get("preferred_next_step"),
        }
        branch = (
            {
                "name": str(self.payload.get("branch_name", "")),
                "address": str(self.payload.get("branch_address", "")),
            }
            if outcome == "qualified"
            else None
        )
        # Tell the browser to render the end screen. Uses the standard ui_command
        # channel (action "call_ended") — the /lead_qual page reads the ui_command
        # envelope like every other demo page.
        interaction.action("call_ended", {"outcome": outcome, "lead": lead, "branch": branch})
        return str({"status": outcome})
