"""LeadQualBrain — the Auric Gold Finance gold-loan lead-qualification advisor.

A :class:`voqalize.sdk.gemini.GeminiBrain`: LLM + Auric Gold Finance tools + this
session's language and enquiry-form state. Voqalize dials this brain's WebSocket
per session; ``respond`` (inherited) runs the turn — google-genai calls the
tools below itself and hands back their results, so a turn that checks
eligibility and then speaks about it is one call from here, not a loop.

The three tools are:

- ``check_eligibility`` — deterministic Auric Gold Finance gold-loan rules, returns
  ``{eligible, reason}`` for the model to translate;
- ``switch_language`` — re-point STT + TTS to another Indic language mid-call;
- ``end_call`` — record the outcome and tell the browser the call has ended.

The LLM's ``genai.Client`` is **dependency-injected**; the brain owns
only the prompt, the tools, and this session's language/payload state.

**One advisor, nine languages, chosen per caller.** The enquiry form's state
(Tamil Nadu → Tamil) does not exist until the session opens, so no agent-level
default could ever be right — :meth:`on_session_start` resolves it and calls
``session.configure`` before the greeting is spoken, and ``switch_language``
moves both legs again mid-call the same way. ``end_call`` drives the browser via
``session.dispatch(CallEnded(...))``, the standard ``ui-command`` envelope the
``/lead_qual`` page reads.
"""

from __future__ import annotations

from typing import Any, Literal

from google import genai
from loguru import logger
from pydantic import BaseModel, Field
from voqalize_demos import DEFAULT_MODEL, GeminiBrain

from voqalize.sdk import Action, Session
from voqalize.sdk.wire import Config, Language, SttConfig, TtsConfig, Voice

# ─── Language tables ───────────────────────────────────────────────────────────

# Auric Gold Finance is Indic-only: STT stays on vql-stt, TTS on OmniVoice
# (omnivoice/gauri) for the whole session — switching only moves the language,
# never the STT model or TTS engine, and the two legs never diverge here.
_LANG_BY_NAME: dict[str, Language] = {
    "Hindi": Language.HI,
    "Telugu": Language.TE,
    "Tamil": Language.TA,
    "Kannada": Language.KN,
    "Malayalam": Language.ML,
    "Marathi": Language.MR,
    "Gujarati": Language.GU,
    "Bengali": Language.BN,
}

LanguageName = Literal[
    "Hindi", "Telugu", "Tamil", "Kannada", "Malayalam", "Marathi", "Gujarati", "Bengali"
]

# Enquiry-form state → the language its callers are answered in.
_STATE_LANG: dict[str, LanguageName] = {
    "Andhra Pradesh": "Telugu",
    "Telangana": "Telugu",
    "Tamil Nadu": "Tamil",
    "Karnataka": "Kannada",
    "Kerala": "Malayalam",
    "Maharashtra": "Marathi",
    "Goa": "Marathi",
    "Gujarat": "Gujarati",
    "West Bengal": "Bengali",
}
_DEFAULT_LANGUAGE: LanguageName = "Hindi"


def _config(language_name: LanguageName) -> Config:
    """Both legs, same language, same voice — one request, for the opener and
    for ``switch_language``."""
    language = _LANG_BY_NAME[language_name]
    return Config(
        tts=TtsConfig(language=language, voice=Voice.OMNIVOICE_GAURI),
        stt=SttConfig(language=language),
    )


def _resolve_initial_language(payload: dict[str, Any]) -> LanguageName:
    """The caller's own choice wins; otherwise the enquiry form's state picks it;
    otherwise Hindi."""
    override = str(payload.get("language", "")).strip()
    if override in _LANG_BY_NAME:
        return override  # type: ignore[return-value]
    state = str(payload.get("state", ""))
    return _STATE_LANG.get(state, _DEFAULT_LANGUAGE)


# The opener, per language — a complete fixed sentence, not filled with the
# customer's name: the name arrives as free English text off the enquiry form
# in session.init, and English interpolated into a native-script TTS line
# mispronounces. A greeting is the one line spoken before any model has run,
# so it is written here, not generated.
_GREETING: dict[LanguageName, str] = {
    "Hindi": (
        "नमस्ते जी, मैं प्रिया बोल रही हूँ, ऑरिक गोल्ड फाइनेंस से। "
        "आपने जो गोल्ड लोन एन्क्वायरी की थी, उसके बारे में कुछ पूछना था।"
    ),
    "Telugu": (
        "నమస్తే, నేను ప్రియ, ఆరిక్ గోల్డ్ ఫైనాన్స్ నుండి. మీరు చేసిన గోల్డ్ లోన్ ఎంక్వైరీ గురించి కొన్ని ప్రశ్నలు అడగాలనుకుంటున్నాను."
    ),
    "Tamil": (
        "வணக்கம், நான் பிரியா, ஆரிக் கோல்ட் ஃபைனான்ஸிலிருந்து பேசுகிறேன். "
        "நீங்கள் செய்த கோல்ட் லோன் விசாரணை பற்றி சில கேள்விகள் கேட்க விரும்புகிறேன்."
    ),
    "Kannada": (
        "ನಮಸ್ಕಾರ, ನಾನು ಪ್ರಿಯಾ, ಆರಿಕ್ ಗೋಲ್ಡ್ ಫೈನಾನ್ಸ್‌ನಿಂದ ಮಾತನಾಡುತ್ತಿದ್ದೇನೆ. "
        "ನೀವು ಮಾಡಿದ ಗೋಲ್ಡ್ ಲೋನ್ ಎಂಕ್ವೈರಿ ಬಗ್ಗೆ ಕೆಲವು ಪ್ರಶ್ನೆಗಳನ್ನು ಕೇಳಬೇಕಿತ್ತು."
    ),
    "Malayalam": (
        "നമസ്കാരം, ഞാൻ പ്രിയ, ഓറിക് ഗോൾഡ് ഫിനാൻസിൽ നിന്നാണ്. "
        "നിങ്ങൾ ചെയ്ത ഗോൾഡ് ലോൺ എൻക്വയറിയെക്കുറിച്ച് കുറച്ച് ചോദ്യങ്ങൾ ചോദിക്കാൻ ആഗ്രഹിക്കുന്നു."
    ),
    "Marathi": (
        "नमस्कार, मी प्रिया, ऑरिक गोल्ड फायनान्सकडून बोलतेय. "
        "तुम्ही केलेल्या गोल्ड लोन एन्क्वायरीबद्दल काही प्रश्न विचारायचे होते."
    ),
    "Gujarati": (
        "નમસ્તે, હું પ્રિયા, ઓરિક ગોલ્ડ ફાયનાન્સ તરફથી બોલું છું. "
        "તમે કરેલી ગોલ્ડ લોન એન્ક્વાયરી વિશે થોડા પ્રશ્નો પૂછવા હતા."
    ),
    "Bengali": (
        "নমস্কার, আমি প্রিয়া, অরিক গোল্ড ফাইন্যান্স থেকে বলছি। "
        "আপনি যে গোল্ড লোন এনকোয়ারি করেছিলেন সে বিষয়ে কয়েকটা প্রশ্ন জিজ্ঞাসা করতে চেয়েছিলাম।"
    ),
}


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


# ─── Tool parameters ────────────────────────────────────────────────────────────


class CheckEligibility(BaseModel):
    """The one parameter of ``check_eligibility`` — not rendered, just the facts
    the deterministic rules run on."""

    is_jewellery: bool = Field(
        description="True if the gold is household jewellery (not coins or bars)."
    )
    gold_weight_grams: float = Field(description="Gold weight in grams.")
    loan_amount_thousands: int = Field(
        description="Desired loan amount in thousands of rupees (e.g. 50 = 50000)."
    )
    tenure_months: int | None = Field(
        default=None, description="Desired tenure in months (3 to 12)."
    )


class SwitchLanguage(BaseModel):
    language: LanguageName = Field(description="Target language.")


class EndCall(BaseModel):
    """The one parameter of ``end_call``. The identity fields on the rendered
    lead (name/phone/state/city) come from the enquiry-form payload the brain
    already holds, not from here — a hallucinated name is not one the model can
    hand back to us."""

    outcome: Literal["qualified", "not_interested", "unresponsive", "ineligible", "other"] = Field(
        description="Final outcome of the call."
    )
    gold_form: Literal["jewelry", "coins", "bars", "mixed"] | None = Field(
        default=None, description="Form of the customer's gold."
    )
    gold_weight_grams: float | None = Field(default=None, description="Gold weight in grams.")
    loan_amount_inr: float | None = Field(
        default=None, description="Desired loan amount in rupees."
    )
    loan_purpose: str | None = Field(default=None, description="Stated purpose of the loan.")
    timeline: Literal["immediate", "within_week", "within_month", "exploring"] | None = Field(
        default=None, description="How soon the customer needs funds."
    )
    preferred_next_step: Literal["branch_visit", "home_visit"] | None = Field(
        default=None, description="Preferred next step."
    )


# ─── Actions (browser render contract) ─────────────────────────────────────────


class CallEnded(Action, name="call_ended"):
    """Rendered by the ``/lead_qual`` end screen. ``lead`` carries the
    enquiry-form identity plus what ``end_call`` collected; ``branch`` is set
    only for a qualified outcome."""

    outcome: str
    lead: dict[str, Any]
    branch: dict[str, str] | None = None


class LeadQualBrain(GeminiBrain):
    """One per session. The Auric Gold Finance gold-loan advisor: LLM +
    eligibility/language/end-call tools + this session's language and
    enquiry-form state."""

    def __init__(self, *, client: genai.Client, model: str = DEFAULT_MODEL) -> None:
        super().__init__(client=client, system_instruction=_SYSTEM_INSTRUCTION, model=model)
        # Per-session state, set for real in on_session_start once session.init
        # (name/phone/state/city/gold_weight/loan_amount/…) has arrived.
        self.payload: dict[str, Any] = {}
        self.language_name: LanguageName = _DEFAULT_LANGUAGE
        self.ended = False

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        """Resolve the caller's language from the enquiry-form payload and
        configure both legs of the wire before the greeting is spoken — this
        brain is the only thing that knows it, since Tamil Nadu → Tamil does
        not exist until this session starts, so no agent-level default could
        ever have been right."""
        payload = dict(session.init or {})
        self.payload = payload
        self.language_name = _resolve_initial_language(payload)
        await session.configure(_config(self.language_name))
        logger.info(
            "lead-qual: session start — language={}, state={!r}",
            self.language_name,
            payload.get("state"),
        )

    async def greet(self, session: Session) -> str:
        """The opener, written not generated: the enquiry form already named the
        customer's language, so there is nothing for a model call to add and no
        first-token latency to hide. It does not say the customer's name — that
        arrives as free English text, and English read into a native-script line
        mispronounces."""
        return _GREETING[self.language_name]

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        """The three the advisor may call."""
        return [self.check_eligibility, self.switch_language, self.end_call]

    async def check_eligibility(self, details: CheckEligibility) -> str:
        """Check whether a customer qualifies for an Auric Gold Finance gold
        loan. Before calling, inform the user you are checking their
        eligibility. Returns {eligible, reason} in English — translate the
        reason for the customer."""
        result = _check_gold_eligibility(
            is_jewellery=details.is_jewellery,
            gold_weight_grams=details.gold_weight_grams,
            loan_amount_thousands=details.loan_amount_thousands,
            tenure_months=details.tenure_months,
        )
        logger.info("lead-qual: check_eligibility → {}", result)
        return str(result)

    async def switch_language(self, to: SwitchLanguage) -> str:
        """Switch the conversation to a different language when the user
        explicitly requests one. Before calling, acknowledge their request in 1
        short sentence in the target language. Subsequent conversation
        continues in the new language and its native script."""
        self.language_name = to.language
        logger.info("lead-qual: switch_language → {}", to.language)
        # One request moves both halves — recognizer and voice — so there is no
        # moment where the call is half in each.
        await self.session.configure(_config(to.language))
        return str({"switched_to": to.language})

    async def end_call(self, record: EndCall) -> str:
        """End the call and record the outcome. All arguments must be in
        English regardless of the conversation language. Use
        outcome='qualified' when all six questions are answered; a failure
        outcome when the call cannot proceed."""
        self.ended = True
        logger.info("lead-qual: end_call outcome={}", record.outcome)
        lead = {
            "name": str(self.payload.get("name", "")),
            "phone": str(self.payload.get("phone", "")),
            "state": str(self.payload.get("state", "")),
            "city": str(self.payload.get("city", "")),
            "gold_form": record.gold_form,
            "gold_weight_grams": record.gold_weight_grams,
            "loan_amount_inr": record.loan_amount_inr,
            "loan_purpose": record.loan_purpose,
            "timeline": record.timeline,
            "preferred_next_step": record.preferred_next_step,
        }
        branch = (
            {
                "name": str(self.payload.get("branch_name", "")),
                "address": str(self.payload.get("branch_address", "")),
            }
            if record.outcome == "qualified"
            else None
        )
        self.session.dispatch(CallEnded(outcome=record.outcome, lead=lead, branch=branch))
        return str({"status": record.outcome})
