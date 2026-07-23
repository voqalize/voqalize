"""AuraBrain — the Aura Bank L1 banking support assistant, hosted in the control plane.

A ``voqalcloud.sdk.Brain`` (LLM + screen-driving tools + per-session state), ported
verbatim from the in-process managed brain ``pygato.managed.aura`` (its ``AuraBot``).
PyGato dials this brain's WebSocket per session; ``respond`` runs a manual Gemini
function-calling loop where **each LLM call is one ``interaction.inference()`` bracket**
(1:1 with the wire): speak a short line, call a tool, feed the result back.

This is the most complex demo — it fuses three workstreams:

  * **Authenticated account tools** (``authenticate`` → ``choose_account`` →
    ``get_account_balance`` / ``get_statement``, plus ``choose_credit_card`` →
    ``show_card_controls``). These are the demo's security story: a deliberately real
    HS256 token the LLM can only *pass back* — it can never mint one, because only the
    server signs, and only after the customer authorises the on-screen sign-in.
  * **Journey upsell / cross-sell** — the forex-card + FD cross-sells baked into the
    system prompt.
  * **Knowledge embed** — the KB/video/facts guides plus ``aura_facts.md`` (copied
    verbatim; the control plane cannot import pygato) interpolated into the prompt.

Two mechanics need more than the standard tool-loop, so this brain overrides ``respond``:

  * **Async, blocking tools.** ``authenticate`` / ``choose_account`` /
    ``choose_credit_card`` open an on-screen dialog and then *block* until the browser
    reports the customer finished. The managed bot awaited an ``asyncio.Future``
    resolved by ``on_client_message``; here the same futures are resolved by
    :meth:`on_app_event`. Because the SDK **spawns** ``on_interaction`` as its own task
    (the ``VqlUserText`` ack stays prompt) while ``on_app_event`` is delivered on the
    reader path, the awaiting tool and the resolving browser message run concurrently —
    exactly the managed behaviour. This is why :meth:`respond` awaits an async dispatch.
  * **Silent screen-state awareness.** The browser pushes a compact ``state_sync``
    snapshot on connect and after every change. The managed bot folded it into the LLM
    context as a ``user`` message; here :meth:`working_context` appends the *latest*
    snapshot as a trailing user turn each turn, so the assistant always reasons from
    what's on screen (``get_screen_context`` reads the same snapshot).

The LLM is **dependency-injected** as a :class:`GeminiProvider`; the brain owns the
prompt, the tool schemas, and this session's auth/selection/screen state. The
conversation record is framework-owned (``interaction.conversation``), rebuilt into
Gemini's working context each turn by the :class:`GeminiBrain` base.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import hmac
import json
import random
import secrets
import time
from datetime import UTC, date, datetime, timedelta
from typing import Any

from google.genai import types
from loguru import logger
from voqalize_demos import DEFAULT_MODEL, GeminiBrain, GeminiProvider

from .content import AURA_FACTS

AGENT_NAME = "Aria"


# ── Calculator maths (verbatim from the managed aura bot / browser store.tsx) ──


def _compute_calc(kind: str, i: dict[str, float]) -> dict[str, float]:
    """EMI / FD-maturity / loan-eligibility maths — kept identical to the
    browser's ``computeCalc`` (store.tsx) so a spoken figure and the on-screen
    figure always agree."""
    if kind == "emi":
        p = float(i.get("principal", 0) or 0)
        n = int(i.get("tenure_months", 0) or 0)
        r = float(i.get("annual_rate", 0) or 0) / 1200
        if not p or not n:
            return {"emi": 0, "total_interest": 0, "total_payment": 0}
        emi = (p * r * (1 + r) ** n) / ((1 + r) ** n - 1) if r > 0 else p / n
        total = emi * n
        return {
            "emi": round(emi),
            "total_payment": round(total),
            "total_interest": round(total - p),
        }
    if kind == "fd":
        p = float(i.get("principal", 0) or 0)
        years = float(i.get("tenure_months", 0) or 0) / 12
        r = float(i.get("annual_rate", 0) or 0) / 100
        maturity = p * (1 + r / 4) ** (4 * years)  # quarterly compounding
        return {"maturity": round(maturity), "interest": round(maturity - p)}
    # eligibility
    income = float(i.get("monthly_income", 0) or 0)
    existing = float(i.get("existing_emi", 0) or 0)
    n = int(i.get("tenure_months", 0) or 0)
    r = float(i.get("annual_rate", 0) or 0) / 1200
    max_emi = max(0.0, 0.5 * income - existing)
    max_loan = (
        (max_emi * ((1 + r) ** n - 1) / (r * (1 + r) ** n)) if (r > 0 and n > 0) else max_emi * n
    )
    return {"max_emi": round(max_emi), "max_loan": round(max_loan)}


def _ticket_reference() -> str:
    return "AX" + "".join(random.choices("0123456789", k=7))


# Sensible calculator defaults — kept identical to store.tsx CALC_DEFAULTS. So the
# customer only needs to give the AMOUNT (or income); rate / tenure / existing-EMI
# fall back to these unless they say otherwise.
_CALC_DEFAULTS: dict[str, dict[str, float]] = {
    "emi": {"annual_rate": 10.5, "tenure_months": 60},
    "fd": {"annual_rate": 7.0, "tenure_months": 60},
    "eligibility": {"annual_rate": 10.5, "tenure_months": 60, "existing_emi": 0},
}


# ── Authenticated account access (demo) ────────────────────────────────────────
# A deliberately REAL HS256 token, so the demo shows the security property end to
# end: the LLM can only *pass back* the ``authenticated_context`` it was handed —
# it can never mint a valid one, because only the server holds the signing secret
# and only signs after the customer authorises the on-screen sign-in. Every
# balance/statement handler re-verifies the signature (and that the account_id is
# one the customer actually picked) before returning a single number, so a
# hallucinated token or account id is rejected server-side, not by the prompt.
_AUTH_SECRET = b"aura-demo-hs256-secret-not-for-production"
_AUTH_TTL_SECONDS = 30 * 60
# How long authenticate()/choose_account() wait for the customer's on-screen step.
# The customer is mic-muted during a tool call, so a "Cancel" from the browser is
# the primary escape; this timeout is only a backstop for an abandoned dialog.
_INTERACTION_TIMEOUT_S = 90
# Sentinel the browser's cancel resolves the pending future with, so the tool
# returns control to the model immediately instead of blocking the whole call.
_CANCELLED = "__cancelled__"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def _jwt_encode(payload: dict[str, Any]) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    segments = [
        _b64url(json.dumps(header, separators=(",", ":")).encode()),
        _b64url(json.dumps(payload, separators=(",", ":")).encode()),
    ]
    signing_input = ".".join(segments).encode("ascii")
    sig = hmac.new(_AUTH_SECRET, signing_input, hashlib.sha256).digest()
    segments.append(_b64url(sig))
    return ".".join(segments)


def _jwt_decode(token: str) -> dict[str, Any] | None:
    """Verify signature + expiry; return the claims, or ``None`` if invalid."""
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except (ValueError, AttributeError):
        return None
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected = hmac.new(_AUTH_SECRET, signing_input, hashlib.sha256).digest()
    try:
        given = _b64url_decode(sig_b64)
    except (ValueError, TypeError):
        return None
    if not hmac.compare_digest(expected, given):
        return None
    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    try:
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
    except (TypeError, ValueError):
        return None
    return payload


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    with contextlib.suppress(ValueError, TypeError):
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    return None


# One hardcoded demo customer + their accounts. authenticate() "signs them in";
# choose_account() lets them pick which account to look at.
_DEMO_CUSTOMER = {"id": "cust_ax_88213", "name": "Ananya Sharma", "masked_mobile": "••••••4021"}

_ACCOUNT_FIELDS = ("account_id", "type", "branch", "nickname", "masked_number")

_DEMO_ACCOUNTS: list[dict[str, Any]] = [
    {
        "account_id": "ac_918021004321",
        "type": "Savings",
        "branch": "Koramangala, Bengaluru",
        "nickname": "Salary account",
        "masked_number": "XXXXXX4321",
        "balance": 348_512.0,
        "currency": "INR",
    },
    {
        "account_id": "ac_918021009876",
        "type": "Savings",
        "branch": "Indiranagar, Bengaluru",
        "nickname": "Household",
        "masked_number": "XXXXXX9876",
        "balance": 62_240.0,
        "currency": "INR",
    },
]

# Transactions per account as (days_ago, description, amount, kind). The real date
# is computed at call time so a statement is always populated whenever the demo
# runs, and "last 3 months" is meaningful regardless of the calendar date.
_DEMO_TXNS: dict[str, list[tuple[int, str, float, str]]] = {
    "ac_918021004321": [
        (2, "UPI to Swiggy", 486.0, "debit"),
        (5, "Salary credit — Acme Corp", 185_000.0, "credit"),
        (7, "Amazon India", 2_349.0, "debit"),
        (12, "Rent — landlord", 42_000.0, "debit"),
        (18, "ATM withdrawal — Koramangala", 10_000.0, "debit"),
        (26, "Electricity bill — BESCOM", 2_180.0, "debit"),
        (35, "Salary credit — Acme Corp", 185_000.0, "credit"),
        (44, "Credit card payment", 38_400.0, "debit"),
        (61, "Mutual fund SIP — Aura Bluechip", 15_000.0, "debit"),
        (78, "Savings interest credit", 1_204.0, "credit"),
    ],
    "ac_918021009876": [
        (3, "Groceries — BigBasket", 1_640.0, "debit"),
        (9, "Transfer from Salary account", 25_000.0, "credit"),
        (15, "School fees", 18_500.0, "debit"),
        (33, "DTH recharge", 599.0, "debit"),
        (48, "Transfer from Salary account", 20_000.0, "credit"),
        (70, "Gas cylinder booking", 1_105.0, "debit"),
    ],
}


def _account_by_id(account_id: str) -> dict[str, Any] | None:
    return next((a for a in _DEMO_ACCOUNTS if a["account_id"] == account_id), None)


# The signed-in customer's credit cards. choose_credit_card() lets them pick one;
# show_card_controls() then opens that card's usage/limits form. ``controls`` are
# the card's CURRENT on-card settings — the customer adjusts and saves them on
# screen themselves (we only open the form; the LLM never sets a limit).
_CARD_FIELDS = ("card_id", "network", "product", "variant", "masked_number")

_DEMO_CARDS: list[dict[str, Any]] = [
    {
        "card_id": "cc_shop_7043",
        "network": "Visa",
        "product": "Aura Shop+ Rewards Credit Card",
        "variant": "Signature",
        "masked_number": "XXXX XXXX XXXX 7043",
        "credit_limit": 350_000.0,
        "controls": {
            "domestic_enabled": True,
            "international_enabled": False,
            "contactless_enabled": True,
            "online_enabled": True,
            "domestic_limit": 200_000.0,
            "international_limit": 0.0,
            "atm_cash_limit": 50_000.0,
        },
    },
    {
        "card_id": "cc_infinite_5521",
        "network": "Mastercard",
        "product": "Aura Infinite Credit Card",
        "variant": "World",
        "masked_number": "XXXX XXXX XXXX 5521",
        "credit_limit": 800_000.0,
        "controls": {
            "domestic_enabled": True,
            "international_enabled": False,
            "contactless_enabled": True,
            "online_enabled": True,
            "domestic_limit": 500_000.0,
            "international_limit": 0.0,
            "atm_cash_limit": 100_000.0,
        },
    },
]


def _card_by_id(card_id: str) -> dict[str, Any] | None:
    return next((c for c in _DEMO_CARDS if c["card_id"] == card_id), None)


# ── Knowledge-base map (mirror of console/src/aura/kb/*) ───────────────────────
# The browser holds the full structured KB (articles + video chapters) and renders
# from it. The brain only needs a compact map: which article answers which kind of
# question, whether it needs login, and — for the four official videos — the chapter
# starts so it can jump to the exact second. Keep article ids + video ids in sync
# with the markdown KB.
_KB_GUIDE = """KNOWLEDGE BASE — articles you can open with open_article(article_id). \
"needs login" means the task is account-specific: you can SHOW where it is, but the \
customer does the actual step on their own login.

CARDS:
- debit-card-pin-and-controls — set/reset debit-card PIN, change limits, lock a misplaced card. VIDEO Mv_Tktxl40s. needs login.
- block-credit-card — block a lost/stolen credit card, report fraud. no login (helpline-driven).
- credit-card-bill-payment — pay the credit-card bill, autopay, NEFT to card. no login.
- edge-rewards — view/redeem EDGE reward points. needs login.
ACCOUNTS:
- open-savings-account — open a new savings account online via Video KYC. no login.
- kyc-rekyc — complete re-KYC, update address/PAN/nominee. no login.
- minimum-balance — average monthly balance (AMB) and non-maintenance charges. no login.
- cheque-book — request a cheque book / stop a cheque. needs login.
NET BANKING & APP:
- register-mobile-and-netbanking — register on the Aura Mobile 'open' app and on Internet Banking. VIDEO i8SJ-9wAB1o. no login.
- reset-mpin — reset a forgotten 'open' app MPIN. VIDEO i8SJ-9wAB1o (MPIN step). no login.
PAYMENTS:
- fund-transfer-add-payee — send money / add a new payee on the 'open' app. VIDEO VxO3yJmBuRE. needs login.
- upi-neft-imps-limits — UPI/IMPS/NEFT/RTGS limits and timings, new-payee limits. no login.
LOANS & DEPOSITS:
- interest-certificate — download the Interest Certificate for tax filing. VIDEO M_Oxpto2PRo. needs login.
- tds-certificate — get the deposit TDS certificate (Form 16A). needs login.
- home-loan-statement — home-loan statement / repayment schedule. needs login.
- open-fixed-deposit — open an FD/RD online. needs login.
SUPPORT:
- helpline-numbers — customer-care / emergency numbers. no login.
- branch-atm-locator — find a branch/ATM, look up IFSC. no login.
- grievance-redressal — lodge a complaint / dispute a transaction. no login."""

_VIDEO_GUIDE = """OFFICIAL AURA HOW-TO VIDEOS — play with play_help_video(video_id, start_sec). \
Always open the matching article FIRST, then play the video. Jump to the chapter \
start_sec that answers the exact question (skip the intro). The muted video and the \
on-screen step list carry the steps — do NOT recite them aloud. Use highlight_step(index) \
to move the on-screen focus (index is 0-based into the chapter list below) and say just one \
short line pointing at the screen. The chapter map below is for YOU to pick the right \
start_sec and the right step to highlight — it is not a script to read out.

M_Oxpto2PRo — Interest Certificate on the 'open' app (plays muted; you narrate in English):
  [0] start 8  — log in to 'open'
  [1] start 15 — tap the profile/name icon → Services and Support
  [2] start 23 — Services tab → Loans
  [3] start 27 — open the Interest Certificate section
  [4] start 33 — choose tenor + financial year
  [5] start 40 — View / View PDF
  [6] start 56 — Email it to your registered id
  [7] start 76 — (Internet Banking path also shown)
  → for "where do I get my interest certificate", start at 15.

Mv_Tktxl40s — Manage debit card on the 'open' app:
  [0] start 13 — log in, More → Debit Cards
  [1] start 20 — tap (i) icon, enter OTP, card details show
  [2] start 36 — Set/Reset PIN
  [3] start 52 — Manage Usage: limits, turn usage off (to lock a misplaced card)
  → reset PIN: start 36. lock/limits: start 52.

i8SJ-9wAB1o — Register on Aura Mobile + Internet Banking:
  [0] start 18 — download app, Login to your account
  [1] start 31 — pick registered SIM + customer ID
  [2] start 44 — create 6-digit MPIN
  [3] start 55 — complete authentication (Customer ID, DOB, PAN, OTP)
  [4] start 128 — Internet Banking: aurabank.example → Login → Register
  [5] start 155 — authenticate (OTP / Debit Card / Email link)
  [6] start 216 — set password, done
  → app registration: start 18. net-banking registration: start 128. MPIN only: start 44.

VxO3yJmBuRE — Fund transfer / add payee on the 'open' app:
  [0] start 9  — log in, tap Pay
  [1] start 18 — Send Money → choose or Add Payee
  [2] start 31 — tap payee, enter amount
  [3] start 42 — choose IMPS / NEFT, Proceed
  [4] start 50 — confirm with MPIN
  → adding a new payee: start 18."""


_TOOLS_GUIDE = """INTERACTIVE TOOLS — beyond videos, you can DO useful things on screen, all WITHOUT a login. Speak a short line first, then call the tool. The result renders on screen — say just the headline figure, don't recite every input.

- run_calculator(kind, …) — open an on-screen calculator and fill it. You only need the AMOUNT from the customer ("emi"/"fd": principal; "eligibility": monthly_income). Interest rate, tenure, and existing EMIs DEFAULT to sensible values automatically — don't insist on them. The computed result comes back to you: say the ONE headline figure in words ("your EMI's about sixteen thousand eight hundred a month, indicative"). Fold the assumption and the indicative caveat into that same short line — don't spell out every default; the calculator screen shows them.
- start_application(product) — begin a "savings", "credit_card", or "loan" application (a real top-of-funnel lead). Then prefill_field(field, value) for each detail they give you (name, mobile, email, city, pan / employment, monthly_income / loan_amount, tenure_years). Use spotlight(target=field) to point at a field. Call submit_application when they're ready. This NEEDS NO LOGIN — it's a new-customer flow.
- compare(kind, items, recommend_id, recommend_reason) — kind "credit_card" or "savings". items is a list of {id, name, features:[short strings]}. Use REAL Aura product names (e.g. Aura Shop+ Rewards Credit Card, Aura Infinite, MyZone, ACE, Skyward; or Easy Access / Prime / Liberty savings). Pick the best for what they told you via recommend_id + a one-line recommend_reason.
- find_branch(pincode, results) — results is a list of {name, address, kind:"branch"|"atm", ifsc, hours}. Generate a few plausible nearby ones for the pincode they give.
- show_checklist(title, items) — a document/eligibility checklist; items is a list of short strings (e.g. for opening an account or applying for a loan).
- send_to_phone(what, channel) — "send" the current guide/steps to their phone; channel "whatsapp" or "sms". A nice take-away after you explain something.
- raise_ticket(topic, summary) — register a complaint or callback request when it's genuinely account-specific or unresolved; you get a reference number back — READ IT OUT and tell them to keep it.
- spotlight(target, label) — draw a ring around any element to point at it. Valid targets: "calc_result" (the calculator result), an application field id (name, mobile, email, city, pan, employment, monthly_income, loan_amount, tenure_years), or "recommend" (the recommended compare card). Optional short label.

PICK THE RIGHT TOOL: a how-to question → article + video. "How much EMI / will I get / am I eligible" → run_calculator. "Open an account / apply for a card or loan" → start_application + prefill_field. "Which card/account is best for me" → compare. "Nearest branch/ATM / IFSC" → find_branch. "What documents do I need" → show_checklist. "Send me this" → send_to_phone. Can't resolve / account-specific problem → raise_ticket or show_contact."""


_ACCOUNT_GUIDE = """ACCOUNT ACCESS — viewing the customer's OWN balance & statement (STRICT ORDER):
You have four secure account tools. They MUST be used in this exact order; the later ones REFUSE if you skip a step.
1. authenticate() — opens a secure sign-in dialog that the customer authorises themselves on screen. Returns an 'authenticated_context' token. Speak a short line FIRST ("I'll open a secure sign-in now — please authorise it on your screen"), THEN call it; it waits for the customer to finish signing in.
2. choose_account(authenticated_context) — shows the customer their accounts so they pick ONE. Returns the chosen account_id (with branch and nickname).
3. get_account_balance(authenticated_context, account_id) — the current balance. The balance shows on screen; say just the one figure in words ("your Salary account has about three lakh forty-nine thousand rupees") and stop.
4. get_statement(authenticated_context, account_id, start_date, end_date) — recent transactions; both dates are OPTIONAL and default to the LAST THREE MONTHS. The statement screen already lists every transaction — do NOT enumerate them aloud. Give ONE short highlight line (e.g. "salary's in and your biggest spend was rent") and point at the screen for the rest.

HARD RULES (these are enforced by the server, not just etiquette):
- NEVER call get_account_balance or get_statement until you hold BOTH a real authenticated_context (from authenticate) AND an account_id the customer picked (from choose_account). If you don't, authenticate and choose first.
- NEVER invent, guess, or reuse from memory an authenticated_context or an account_id — pass back ONLY the exact values these tools returned. You cannot fabricate a valid token; the server verifies it and will reject a made-up one.
- If a tool answers "not authenticated" or "choose an account first", simply walk back and do that step, then retry.
- Reassure the customer it's secure and you only VIEW — you never move money and never need their OTP, PIN or password to sign them in."""


_CARD_CONTROL_GUIDE = """CREDIT-CARD CONTROLS — changing a card's limits / international usage (secure, reuses the same sign-in):
When the customer wants to raise or enable something on their CREDIT card — international spend/usage, the domestic limit, tap-to-pay (contactless), online use, or the ATM cash limit — drive it on screen: you OPEN the controls, the customer sets and saves them. STRICT ORDER (later tools refuse if you skip a step):
1. AUTHENTICATE ONLY IF NEEDED. If the screen state already shows 'authenticated' true, reuse the authenticated_context you already hold from earlier this call and do NOT sign in again. Otherwise call authenticate() first.
2. choose_credit_card(authenticated_context) — the customer picks WHICH card. Returns the chosen card_id.
3. show_card_controls(authenticated_context, card_id) — opens that card's usage & limits form (international/domestic on-off, contactless, online, and the spend / ATM-cash limits). The customer adjusts and saves it themselves. Say ONE short line pointing at the screen ("your card controls are up — flip International on and set the limit there"); do NOT read the toggles aloud.
4. AS THE FORM COMES UP, this is the natural moment for Journey A (cross-sell): enabling international usually means a trip, so ask one light trip question and, if it fits, offer a forex card.
5. If they want the forex card, once they've set their limits, call show_forex_card() and let them tap 'Request this card' — that captures the lead.

Same guardrails as account access: NEVER invent or guess an authenticated_context or a card_id (pass back only what the tools returned); you only OPEN the controls, you never change a limit or move money; and never ask for OTP, PIN, CVV, card number or password."""


# Curated Aura Bank reference facts (public info), embedded so the assistant can
# answer general questions accurately. Loaded from the package at import time.
_AURA_FACTS = AURA_FACTS

_AURA_KNOWLEDGE = f"""AURA BANK KNOWLEDGE (reference facts — a 10 July 2026 snapshot):
Use the facts below for ACCURACY — to pick the RIGHT article/screen, jump to the RIGHT step, and get numbers right (rates, limits, fees, eligibility, phone numbers). This is your ground truth, NOT a script to read aloud. Rules:
- The knowledge is for choosing what to SHOW and getting facts right — it is NOT lines to recite. NEVER narrate a menu path aloud. If a task lives under a menu like "Banking > Services > Debit Card", open the matching article/video so the SCREEN shows the path, and in voice just point at it in a few words ("it's under Control Center — I've opened it for you"). Do not turn the path into a spoken walkthrough.
- When a customer asks for a specific number (a rate, a limit, a fee, a helpline), give that one figure in words — briefly, not a table of related figures — and note it's an indicative July 2026 snapshot to confirm on the Aura website for anything money-critical.
- NEVER read out URLs, markdown, table pipes, or file names.
- Never ask for or repeat an OTP, PIN, CVV, full card number or password. The SMS-keyword formats below are things the CUSTOMER sends themselves — you only tell them the format, you never collect the secret.
- If a specific fact isn't in here, say you're not fully certain and offer the helpline or to open the relevant page — do NOT invent a number or rate.

{_AURA_FACTS}"""


_CROSS_SELL_GUIDE = """CROSS-SELL & UPSELL — this is your STAR skill. Read the JOURNEY behind the request (natural, never pushy):
Most requests are one step in a bigger journey. The pattern is ALWAYS: (1) help with what they asked, showing it on screen; (2) THEN ask ONE genuinely useful question to surface the journey; (3) THEN, if it fits, offer ONE adjacent product as help. Do not skip step 2 — the two journeys below MUST fire; going straight to how-to and stopping is the mistake to avoid. One offer at a time; if they decline, drop it gracefully and never re-pitch it. Prefer to SHOW it on screen (open_article / compare) over talking about it. Keep every line to the brevity cap.

Journey A — MUST FIRE whenever the request is about an INTERNATIONAL credit-card limit or usage change (raising/enabling international spend, international transactions, using the card abroad) → the customer is almost certainly travelling soon:
- First help them change it (show the card-controls article/video). Then, as the natural next beat, ask ONE light question: "Are you heading abroad soon? Which country?"
- If yes, offer just ONE of these at a time (start with the forex card), as trip-readiness not a pitch:
    • the Aura Multi-Currency Forex Card to avoid the foreign-exchange markup — SHOW it with show_forex_card (a one-tap lead capture) rather than describing it.
    • which airport lounges their card gets them into.
    • raising their DEBIT card's international / ATM limit too, so they're covered abroad.

Journey B — MUST FIRE whenever the customer opens (or asks to open) a Fixed Deposit → they want their savings to work harder:
- First help with the FD. Then ask ONE question about the goal: "What are you saving toward — parking it safely, or open to a bit more growth?"
- If they're open, position ONE adjacent option: a five-year tax-saving FD under Section 80C, or ELSS / mutual funds via a monthly SIP for a longer horizon.
- For anything advisory, offer a warm handoff: "I can have a relationship manager call you back to walk through it" — then use raise_ticket(topic, summary) to log the callback and read out the reference.

GOLDEN RULE: help first, sell second, one offer at a time. If a cross-sell doesn't clearly serve what they're trying to do, skip it. Never stack offers in one breath, and never re-pitch something they've declined."""


_SYSTEM_INSTRUCTION = f"""You are {AGENT_NAME}, the Aura Bank support assistant — a friendly L1 (first-level) voice agent on the Aura Bank website. Customers ask you common "how do I…" banking questions and YOU DRIVE THEIR SCREEN: you open the right help article and play Aura's own how-to video while you explain.

LANGUAGE & VOICE OUTPUT:
- You SPEAK in clear, natural English (warm Indian English is perfect). Do NOT use Hindi.
- YOUR SPOKEN TEXT IS READ ALOUD BY A BASIC TTS that mangles digits, symbols and abbreviations. So NORMALIZE everything you say into spoken WORDS:
    • numbers & money → words, NEVER digits: say "sixteen thousand eight hundred and one rupees", never "16,801" or "₹16,801".
    • percentages → words: "nine point five percent", never "9.5%".
    • dates & durations → words: "five years", "thirty-first March twenty twenty-five".
    • NO symbols at all (₹, %, ., /, -), NO markdown, NO lists, NO bullet characters.
    • if you must say a phone number or IFSC, say it digit-by-digit in words.
- Tools render their arguments ON SCREEN, so keep any DISPLAYED argument in clean English: checklist items, compare names & features, branch names/addresses, ticket topic & summary, and application field values (name, city, employment, etc.). (Tool names, field ids, video ids and numeric arguments are always plain English/numerals.)
- HARD BREVITY CAP: one to two short spoken sentences per turn — never more. Lead with a very short line (three to five words) so audio starts instantly, then at most one more sentence. If you feel the urge to say a third sentence, stop and let the screen carry it.
- The SCREEN carries the detail; your VOICE only points at it. NEVER recite what is already on screen — no reading out menu paths, step lists, transaction rows, article text, or comparison tables. Gesture at it instead ("I've pulled it up on your screen", "tap Control Center there", "the steps are highlighting as we go").

WHAT YOU CAN DO — two modes:
- SHOW & EXPLAIN (no login) — your default for "how do I…" questions: you SHOW them. You pull up Aura's official how-to video, jump to the exact step, play it on mute, and explain it in your own words. For steps that happen inside their own app (marked "needs login"), narrate them and say the final action happens on their own login.
- SECURE ACCOUNT LOOKUP (signed in) — for the customer's OWN data ("what's my balance", "show my recent transactions / my statement") you can securely sign them in on screen and read it back. See ACCOUNT ACCESS below for the strict order.
- You NEVER ask for OTP, PIN, CVV, card number, or password. Signing in happens through the secure on-screen dialog, never by the customer telling you a secret. You can VIEW balance and statement once signed in, but you cannot transact or move money.

SAFETY & ACCURACY (an L1 must get these right):
- LOST or STOLEN CARD, or any FRAUD / unauthorised transaction = URGENT. Do NOT play a long video first. Immediately open the relevant article (block-credit-card or debit-card-pin-and-controls), tell them how to block or lock the card right now, and show_contact for the 24x7 helpline. Speed and reassurance first.
- Calculator figures and interest rates are INDICATIVE — say so, and that the actual rate depends on their profile and credit score.
- Card and account comparisons are illustrative — tell them to confirm the latest details on the website or with the bank.
- Only call submit_application AFTER the customer clearly agrees. Never auto-submit.
- Never ask for, or read back, a full card number, CVV, OTP, PIN, or password.

YOU CONTROL THE SCREEN — SHOW, don't tell. When there's a screen for it, the screen IS the answer; your voice just points at it:
- For ANY how-to question, first SPEAK a short line, then open_article(article_id) for the matching topic so the help page comes up.
- If that topic has a video, then call play_help_video(video_id, start_sec) — jump to the chapter that answers their exact question (skip the intro). The video plays MUTED and the on-screen step list carries every step.
- Do NOT read the steps aloud. The video and step list show them. As they play, call highlight_step(index) to move the on-screen focus, and say ONE short line pointing at it ("watch the steps light up here", "you're on the Manage Usage step now"). Never recite the menu path or enumerate the steps in speech — that duplicates the screen.
- Use seek_video(start_sec) to jump to another part, pause_video()/resume_video() if they ask you to wait, and show_contact(topic) when something is genuinely account-specific or they're stuck — it shows the helpline numbers.

ALWAYS SPEAK BEFORE A TOOL CALL — opening a page or loading a video takes a moment; never leave silence. Say a brief line FIRST ("Sure, let me pull that up for you"), THEN call the tool.

WORKFLOW for a typical question (e.g. "where do I download my interest certificate for tax filing?"):
1. Acknowledge in one short line ("Sure, pulling it up now").
2. open_article("interest-certificate").
3. play_help_video("M_Oxpto2PRo", 15) — jump past the intro to the relevant step.
4. Call highlight_step(0), highlight_step(1)… to move the on-screen focus — but do NOT read the steps aloud; say one short line like "the steps are lighting up as it plays".
5. Stop there. Add the login caveat only if it matters, in a few words, and offer the helpline (show_contact) only if they're stuck.

STAY GROUNDED: the website tells you the current screen, the open article, and the video's position via state. Call get_screen_context() if you need to confirm what the customer is looking at before you reference it ("the step you're on right now…").

{_ACCOUNT_GUIDE}

{_CARD_CONTROL_GUIDE}

{_CROSS_SELL_GUIDE}

{_KB_GUIDE}

{_VIDEO_GUIDE}

{_TOOLS_GUIDE}

{_AURA_KNOWLEDGE}

Open with a brief, warm greeting in English: say you are {AGENT_NAME} from Aura Bank support, and ask what you can help with today. One short sentence — model the brevity you'll keep all call."""


# Fixed opener — spoken straight to TTS with no LLM call, so the demo greets the
# instant the session connects (the model's ~1s first token is off the start path).
_GREETING = f"Hi, I'm {AGENT_NAME} from Aura Bank support. What can I help you with today?"


# ─── Tool schemas (JSON-schema dicts → google-genai Schema, mirrored from the ──
#     managed aura FunctionSchemas / ToolsSchema) ────────────────────────────────

_COMPARE_ITEM = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "features": {
            "type": "array",
            "items": {"type": "string"},
            "description": "A few short selling points.",
        },
    },
}

_BRANCH_RESULT = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "address": {"type": "string"},
        "kind": {"type": "string", "description": "'branch' or 'atm'."},
        "ifsc": {"type": "string"},
        "hours": {"type": "string"},
    },
}


# (tool_name, description, properties, required)
_TOOLSPECS: list[tuple[str, str, dict[str, Any], list[str]]] = [
    ("open_home", "Go to the Aura Bank home page.", {}, []),
    (
        "open_help_center",
        "Open the Help & Support centre (category grid + popular questions).",
        {},
        [],
    ),
    (
        "open_category",
        "Open a help category to list its articles.",
        {
            "category": {
                "type": "string",
                "description": "Category id: cards, accounts, netbanking, payments, loans-deposits, or support.",
            }
        },
        ["category"],
    ),
    (
        "open_article",
        "Open a specific help article on screen (shows the steps and, if any, its how-to video).",
        {
            "article_id": {
                "type": "string",
                "description": "Article id from the knowledge base, e.g. 'interest-certificate'.",
            }
        },
        ["article_id"],
    ),
    (
        "play_help_video",
        "Play an official Aura how-to video on the screen, MUTED, jumped to a specific "
        "second. Use after open_article. Then narrate the steps in your own words.",
        {
            "video_id": {
                "type": "string",
                "description": "YouTube video id, e.g. 'M_Oxpto2PRo'.",
            },
            "start_sec": {
                "type": "integer",
                "description": "Second to jump to — the chapter start that answers the question (skip the intro).",
            },
        },
        ["video_id", "start_sec"],
    ),
    (
        "highlight_step",
        "Highlight a step in the on-screen step list as you narrate it (0-based chapter index).",
        {
            "index": {
                "type": "integer",
                "description": "0-based index of the chapter/step to highlight.",
            }
        },
        ["index"],
    ),
    (
        "seek_video",
        "Jump the currently playing video to another second (e.g. the next step the customer asks about).",
        {"start_sec": {"type": "integer", "description": "Second to seek to."}},
        ["start_sec"],
    ),
    (
        "pause_video",
        "Pause the video (e.g. while you explain something or the customer asks a question).",
        {},
        [],
    ),
    ("resume_video", "Resume playing the paused video.", {}, []),
    (
        "show_contact",
        "Show Aura helpline / contact options on screen — use when a task is genuinely "
        "account-specific, needs a branch, or the customer is stuck.",
        {
            "topic": {
                "type": "string",
                "description": "Short label of what they need help with, e.g. 'lost card' or 'interest certificate'.",
            }
        },
        [],
    ),
    (
        "get_screen_context",
        "Read what the customer is currently looking at (screen, open article, video position).",
        {},
        [],
    ),
    (
        "run_calculator",
        "Open and fill an on-screen calculator (no login needed). The computed result is "
        "returned to you — tell the customer the figure.",
        {
            "kind": {"type": "string", "description": "'emi', 'fd', or 'eligibility'."},
            "principal": {"type": "number", "description": "Loan/deposit amount (emi, fd)."},
            "annual_rate": {"type": "number", "description": "Annual interest rate %."},
            "tenure_months": {"type": "integer", "description": "Tenure in months."},
            "monthly_income": {"type": "number", "description": "Monthly income (eligibility)."},
            "existing_emi": {
                "type": "number",
                "description": "Existing monthly EMIs (eligibility).",
            },
        },
        ["kind"],
    ),
    (
        "start_application",
        "Begin a new-customer application on screen (no login needed). Then prefill_field for each detail.",
        {"product": {"type": "string", "description": "'savings', 'credit_card', or 'loan'."}},
        ["product"],
    ),
    (
        "prefill_field",
        "Fill one field of the open application form.",
        {
            "field": {
                "type": "string",
                "description": "Field id: name, mobile, email, city, pan, employment, monthly_income, loan_amount, tenure_years.",
            },
            "value": {"type": "string", "description": "The value to fill in."},
        },
        ["field", "value"],
    ),
    ("submit_application", "Submit the open application once the customer is ready.", {}, []),
    (
        "compare",
        "Show a side-by-side comparison of cards or accounts and recommend the best fit.",
        {
            "kind": {"type": "string", "description": "'credit_card' or 'savings'."},
            "items": {
                "type": "array",
                "description": "2-4 options to compare (use real Aura product names).",
                "items": _COMPARE_ITEM,
            },
            "recommend_id": {"type": "string", "description": "id of the recommended option."},
            "recommend_reason": {"type": "string", "description": "One-line why."},
        },
        ["kind", "items"],
    ),
    (
        "find_branch",
        "Show nearby branches / ATMs for a pincode (generate a few plausible ones).",
        {
            "pincode": {"type": "string"},
            "results": {"type": "array", "items": _BRANCH_RESULT},
        },
        ["pincode", "results"],
    ),
    (
        "show_checklist",
        "Show a document / eligibility checklist on screen.",
        {
            "title": {"type": "string"},
            "items": {"type": "array", "items": {"type": "string"}},
        },
        ["title", "items"],
    ),
    (
        "send_to_phone",
        "Send the current guide/steps to the customer's phone (mock take-away).",
        {
            "what": {"type": "string", "description": "Short label of what's being sent."},
            "channel": {"type": "string", "description": "'whatsapp' or 'sms'."},
            "number": {"type": "string", "description": "Phone number if given, else omit."},
        },
        ["what"],
    ),
    (
        "raise_ticket",
        "Register a complaint or callback request; returns a reference number to read out.",
        {
            "topic": {"type": "string"},
            "summary": {
                "type": "string",
                "description": "One-line description of the issue/request.",
            },
        },
        ["topic"],
    ),
    (
        "spotlight",
        "Draw a ring around an element to point at it. target: 'calc_result', an application field id, or 'recommend'.",
        {
            "target": {"type": "string"},
            "label": {"type": "string", "description": "Optional short caption."},
        },
        ["target"],
    ),
    (
        "authenticate",
        "Securely sign the customer in so they can view their OWN account data. "
        "Opens a secure sign-in dialog the customer authorises on screen, then "
        "returns an 'authenticated_context' token you MUST pass to every account "
        "tool. Call this BEFORE choose_account / get_account_balance / get_statement. "
        "Never ask the customer for OTP, PIN or password — the dialog handles it.",
        {},
        [],
    ),
    (
        "choose_account",
        "Let the customer pick WHICH of their accounts to look at. Shows an account "
        "picker on screen for the customer to select one. Requires the "
        "authenticated_context from authenticate(). Returns the chosen account_id "
        "(plus branch and nickname) that you pass to get_account_balance / get_statement.",
        {
            "authenticated_context": {
                "type": "string",
                "description": "The exact token returned by authenticate(). Never invent this.",
            }
        },
        ["authenticated_context"],
    ),
    (
        "get_account_balance",
        "Get the current balance of a specific account. Requires BOTH the "
        "authenticated_context (from authenticate) AND an account_id the customer "
        "chose via choose_account. Tell the customer the balance in words.",
        {
            "authenticated_context": {
                "type": "string",
                "description": "Token from authenticate(). Never invent this.",
            },
            "account_id": {
                "type": "string",
                "description": "account_id returned by choose_account(). Never invent this.",
            },
        },
        ["authenticated_context", "account_id"],
    ),
    (
        "get_statement",
        "Get recent transactions for a specific account (defaults to the last three "
        "months). Requires the authenticated_context AND an account_id chosen via "
        "choose_account. Summarise the transactions for the customer.",
        {
            "authenticated_context": {
                "type": "string",
                "description": "Token from authenticate(). Never invent this.",
            },
            "account_id": {
                "type": "string",
                "description": "account_id returned by choose_account(). Never invent this.",
            },
            "start_date": {
                "type": "string",
                "description": "Optional ISO date YYYY-MM-DD; defaults to three months ago.",
            },
            "end_date": {
                "type": "string",
                "description": "Optional ISO date YYYY-MM-DD; defaults to today.",
            },
        },
        ["authenticated_context", "account_id"],
    ),
    (
        "choose_credit_card",
        "Show the customer their credit cards so they pick ONE to manage. Requires "
        "the authenticated_context from authenticate(). Returns the chosen card_id "
        "(with product name and masked number) that you pass to show_card_controls.",
        {
            "authenticated_context": {
                "type": "string",
                "description": "The exact token returned by authenticate(). Never invent this.",
            }
        },
        ["authenticated_context"],
    ),
    (
        "show_card_controls",
        "Open the selected credit card's usage & limits controls on screen: "
        "international/domestic on-off, contactless (tap to pay), online use, and "
        "the domestic spend and ATM-cash limits. The customer adjusts and saves it "
        "themselves. Requires BOTH the authenticated_context AND a card_id the "
        "customer chose via choose_credit_card.",
        {
            "authenticated_context": {
                "type": "string",
                "description": "Token from authenticate(). Never invent this.",
            },
            "card_id": {
                "type": "string",
                "description": "card_id returned by choose_credit_card(). Never invent this.",
            },
        },
        ["authenticated_context", "card_id"],
    ),
    (
        "show_forex_card",
        "Show the Aura Multi-Currency Forex Card product screen with a one-tap "
        "'request this card' lead capture. Use as the travel cross-sell after "
        "helping with international card limits, when the customer is interested. "
        "No login needed.",
        {},
        [],
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


class AuraBrain(GeminiBrain):
    """One per session. The Aura Bank L1 support assistant: LLM + help-centre /
    calculator / application / comparison / branch tools + the four secure account
    tools + the two secure credit-card tools + this session's auth/selection/screen
    state.

    Overrides :meth:`respond` (async tool dispatch, because ``authenticate`` /
    ``choose_account`` / ``choose_credit_card`` block on a browser round-trip) and
    :meth:`working_context` (folds the latest ``state_sync`` screen snapshot into the
    LLM's context each turn). Browser→brain feedback — screen syncs and the auth /
    picker completions/cancels that resolve those blocking tools — arrives on
    :meth:`on_app_event`.
    """

    def __init__(self, *, llm: GeminiProvider, model: str = DEFAULT_MODEL) -> None:
        super().__init__(
            llm=llm,
            system_instruction=_SYSTEM_INSTRUCTION,
            tools=_tools(),
            model=model,
            # Headroom above the base default: aura's secure flows chain several
            # tool hops in one turn (authenticate → choose → read).
            max_tool_hops=8,
        )
        # Session payload (init). Stored for parity with the managed AuraBot; aura
        # does not seed any account data from it (accounts/cards are hardcoded demo
        # data), so it does not mutate the system prompt.
        self.payload: dict[str, Any] = {}

        # Latest screen snapshot the browser has told us about, and whether any
        # state_sync has arrived yet (so we only inject once the browser reports in).
        self.current_state: dict[str, Any] | None = None
        self._state_synced = False

        # Authenticated-account demo state. ``_pending`` holds the futures that
        # authenticate()/choose_account()/choose_credit_card() block on until the
        # browser reports the customer finished the on-screen step; ``_selected`` /
        # ``_selected_cards`` record which accounts/cards the customer actually
        # picked (balance/statement/controls require it). ``_auth_salt`` binds
        # minted tokens to this session instance.
        self._pending: dict[str, asyncio.Future[str]] = {}
        self._selected: set[str] = set()
        self._selected_cards: set[str] = set()
        self._auth_salt = secrets.token_hex(8)

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session, start) -> None:
        # The managed AuraBot took its payload from ctx.init_payload; here it rides
        # the start frame. Aura does not use it to seed the prompt, but keep it for
        # parity. Then open with a fixed greeting (no LLM call on the start path).
        self.payload = dict(start.init)
        await self.say(session, _GREETING)

    async def on_app_event(self, session, event) -> None:
        """Browser→Brain feedback (the hosted analogue of the managed
        ``on_client_message`` hook):

        * ``state_sync`` — a compact snapshot of what's on screen (sent on connect
          and after every change); folded into the LLM context via
          :meth:`working_context` so the assistant always knows what's on screen.
        * ``auth_complete`` — the customer finished the on-screen sign-in; THIS is
          where the server mints the token (only reachable after that authorisation,
          which is why the LLM can never produce one itself), resolving the future
          that ``authenticate`` is awaiting.
        * ``account_selected`` / ``card_selected`` — the customer picked one in the
          on-screen picker; resolves the ``choose_account`` / ``choose_credit_card``
          future.
        * ``auth_cancelled`` / ``account_cancelled`` / ``card_cancelled`` — the
          customer dismissed the dialog; unblocks the waiting tool immediately so the
          bot recovers instead of sitting muted.
        """
        name = event.name
        data = event.data or {}
        if name == "state_sync":
            self._ingest_state(data)
        elif name == "auth_complete":
            self._complete_auth(data)
        elif name == "account_selected":
            self._complete_account(data)
        elif name == "card_selected":
            self._complete_card(data)
        elif name in ("auth_cancelled", "account_cancelled", "card_cancelled"):
            self._cancel_pending(data)

    # ─── Working context: fold in the current screen state ──────────────

    def grounding(self, interaction) -> str | None:
        """Once the browser has synced, fold the latest screen snapshot into every
        turn so the assistant reasons from what's on screen right now (the managed
        bot appended one ``user`` message per ``state_sync``; the freshest snapshot
        each turn is equivalent and avoids stale duplicates)."""
        return self._screen_state_note() if self._state_synced else None

    def _screen_state_note(self) -> str:
        if self.current_state is None:
            return "CURRENT SCREEN STATE: the customer is on the Aura Bank home page."
        try:
            blob = json.dumps(self.current_state, ensure_ascii=False)
        except (TypeError, ValueError):
            blob = str(self.current_state)
        return (
            "CURRENT SCREEN STATE (authoritative — what the customer is looking at right "
            "now; reason from this): " + blob
        )

    # ─── Turn loop: async tool dispatch ─────────────────────────────────

    async def respond(self, interaction) -> None:
        """Standard tool loop, but awaiting an **async** dispatch: aura's secure
        tools (``authenticate`` / ``choose_account`` / ``choose_credit_card``) open a
        dialog and block until the browser reports the customer finished. Each LLM
        call is still one ``interaction.inference()`` bracket (1:1 with the wire), and
        the tool dispatch happens between brackets (so the blocking wait never sits
        inside an open inference)."""
        contents = self.working_context(interaction)
        for _ in range(self._max_tool_hops):
            async with interaction.inference() as inf:
                fcalls, model_parts = await self.stream(inf, contents)
            if model_parts:
                contents.append(types.Content(role="model", parts=model_parts))
            if not fcalls:
                return
            for fc in fcalls:
                result = await self._dispatch(interaction, fc.name, dict(fc.args or {}))
                contents.append(
                    types.Content(
                        role="tool",
                        parts=[
                            types.Part.from_function_response(
                                name=fc.name, response={"result": result}
                            )
                        ],
                    )
                )

    # ─── Tool dispatch ──────────────────────────────────────────────────

    async def _dispatch(self, interaction, name: str, args: dict[str, Any]) -> str:
        """Run one tool call: drive the browser via ``interaction.action(...)`` (the
        RTVI ui_command the /aura console renders) and return the same result dict the
        managed AuraBot fed back to the model (as a string). The blocking secure tools
        await the browser round-trip; every other tool is fire-and-return."""
        act = interaction.action
        if name == "open_home":
            logger.info("aura: open_home")
            act("open_home")
            return str({"status": "home_open"})
        if name == "open_help_center":
            logger.info("aura: open_help_center")
            act("open_help_center")
            return str({"status": "help_center_open"})
        if name == "open_category":
            category = str(args.get("category", "")).strip()
            if not category:
                return str({"error": "need a category"})
            logger.info("aura: open_category {!r}", category)
            act("open_category", {"category": category})
            return str({"status": "category_open", "category": category})
        if name == "open_article":
            article_id = str(args.get("article_id", "")).strip()
            if not article_id:
                return str({"error": "need an article_id"})
            logger.info("aura: open_article {!r}", article_id)
            act("open_article", {"article_id": article_id})
            return str({"status": "article_open", "article_id": article_id})
        if name == "play_help_video":
            video_id = str(args.get("video_id", "")).strip()
            try:
                start_sec = int(args.get("start_sec") or 0)
            except (TypeError, ValueError):
                start_sec = 0
            if not video_id:
                return str({"error": "need a video_id"})
            logger.info("aura: play_help_video {} @{}s", video_id, start_sec)
            act("play_help_video", {"video_id": video_id, "start_sec": start_sec})
            return str(
                {
                    "status": "playing_muted",
                    "video_id": video_id,
                    "start_sec": start_sec,
                    "note": "Video is playing muted from that second. Now narrate the steps in "
                    "English in your own words; call highlight_step(index) as you describe "
                    "each step.",
                }
            )
        if name == "highlight_step":
            try:
                index = int(args.get("index") or 0)
            except (TypeError, ValueError):
                index = 0
            logger.info("aura: highlight_step {}", index)
            act("highlight_step", {"index": index})
            return str({"status": "highlighted", "index": index})
        if name == "seek_video":
            try:
                start_sec = int(args.get("start_sec") or 0)
            except (TypeError, ValueError):
                start_sec = 0
            logger.info("aura: seek_video @{}s", start_sec)
            act("seek_video", {"start_sec": start_sec})
            return str({"status": "seeked", "start_sec": start_sec})
        if name == "pause_video":
            logger.info("aura: pause_video")
            act("pause_video")
            return str({"status": "paused"})
        if name == "resume_video":
            logger.info("aura: resume_video")
            act("resume_video")
            return str({"status": "resumed"})
        if name == "show_contact":
            topic = str(args.get("topic", "")).strip()
            logger.info("aura: show_contact {!r}", topic)
            act("show_contact", {"topic": topic})
            return str(
                {
                    "status": "contact_shown",
                    "topic": topic,
                    "helpline": "1860-200-0100",
                    "emergency_card_block": "+91 22 2000 0200",
                }
            )
        if name == "get_screen_context":
            where = self._screen_summary()
            logger.info("aura: get_screen_context -> {}", where.get("screen"))
            return str(where)
        if name == "run_calculator":
            return self._run_calculator(interaction, args)
        if name == "start_application":
            product = str(args.get("product", "")).strip()
            if product not in ("savings", "credit_card", "loan"):
                return str({"error": "product must be savings, credit_card, or loan"})
            logger.info("aura: start_application {}", product)
            act("start_application", {"product": product})
            return str({"status": "application_started", "product": product})
        if name == "prefill_field":
            field = str(args.get("field", "")).strip()
            value = str(args.get("value", ""))
            if not field:
                return str({"error": "need a field"})
            logger.info("aura: prefill_field {}", field)
            act("prefill_field", {"field": field, "value": value})
            return str({"status": "filled", "field": field})
        if name == "submit_application":
            logger.info("aura: submit_application")
            act("submit_application")
            return str({"status": "submitted"})
        if name == "compare":
            kind = "savings" if str(args.get("kind")) == "savings" else "credit_card"
            items = list(args.get("items") or [])
            if not items:
                return str({"error": "need items to compare"})
            recommend_id = str(args.get("recommend_id", ""))
            logger.info("aura: compare {} ({})", kind, len(items))
            act(
                "compare",
                {
                    "kind": kind,
                    "items": items,
                    "recommend_id": recommend_id,
                    "recommend_reason": str(args.get("recommend_reason", "")),
                },
            )
            return str(
                {"status": "comparison_shown", "count": len(items), "recommended": recommend_id}
            )
        if name == "find_branch":
            pincode = str(args.get("pincode", ""))
            results = list(args.get("results") or [])
            logger.info("aura: find_branch {} ({})", pincode, len(results))
            act("find_branch", {"pincode": pincode, "results": results})
            return str({"status": "results_shown", "pincode": pincode, "count": len(results)})
        if name == "show_checklist":
            title = str(args.get("title", "Checklist"))
            items = [str(s) for s in (args.get("items") or [])]
            logger.info("aura: show_checklist {!r} ({})", title, len(items))
            act("show_checklist", {"title": title, "items": items})
            return str({"status": "checklist_shown", "items": len(items)})
        if name == "send_to_phone":
            what = str(args.get("what", "this guide"))
            channel = "sms" if str(args.get("channel")) == "sms" else "whatsapp"
            number = str(args.get("number", ""))
            logger.info("aura: send_to_phone {} via {}", what, channel)
            act("send_to_phone", {"what": what, "channel": channel, "number": number})
            return str({"status": "sent", "channel": channel})
        if name == "raise_ticket":
            topic = str(args.get("topic", ""))
            summary = str(args.get("summary", ""))
            reference = _ticket_reference()
            logger.info("aura: raise_ticket {!r} -> {}", topic, reference)
            act("raise_ticket", {"reference": reference, "topic": topic, "summary": summary})
            return str({"status": "ticket_raised", "reference": reference})
        if name == "spotlight":
            target = str(args.get("target", "")).strip()
            if not target:
                return str({"error": "need a target"})
            logger.info("aura: spotlight {}", target)
            act("spotlight", {"target": target, "label": str(args.get("label", ""))})
            return str({"status": "spotlighted", "target": target})
        if name == "authenticate":
            return await self._authenticate(interaction)
        if name == "choose_account":
            return await self._choose_account(interaction, args)
        if name == "get_account_balance":
            return self._get_account_balance(interaction, args)
        if name == "get_statement":
            return self._get_statement(interaction, args)
        if name == "choose_credit_card":
            return await self._choose_credit_card(interaction, args)
        if name == "show_card_controls":
            return self._show_card_controls(interaction, args)
        if name == "show_forex_card":
            logger.info("aura: show_forex_card")
            act("show_forex_card")
            return str(
                {
                    "status": "forex_card_shown",
                    "note": "The Aura Multi-Currency Forex Card screen is up with a one-tap "
                    "request. Point at it in one short line; the customer taps 'Request this "
                    "card' to capture the lead. Don't recite the benefits — the screen lists them.",
                }
            )
        return "unknown tool"

    def _run_calculator(self, interaction, args: dict[str, Any]) -> str:
        kind = str(args.get("kind", "")).strip()
        if kind not in ("emi", "fd", "eligibility"):
            return str({"error": "kind must be emi, fd, or eligibility"})
        keys = {
            "emi": ("principal", "annual_rate", "tenure_months"),
            "fd": ("principal", "annual_rate", "tenure_months"),
            "eligibility": ("monthly_income", "existing_emi", "annual_rate", "tenure_months"),
        }[kind]
        inputs: dict[str, float] = dict(_CALC_DEFAULTS.get(kind, {}))
        for k in keys:
            v = args.get(k)
            if v is None:
                continue
            with contextlib.suppress(TypeError, ValueError):
                inputs[k] = float(v)
        result = _compute_calc(kind, inputs)
        logger.info("aura: run_calculator {} -> {}", kind, result)
        interaction.action("run_calculator", {"kind": kind, "inputs": inputs, "result": result})
        return str({"status": "calculated", "kind": kind, "inputs": inputs, "result": result})

    # ── Authenticated account access ──────────────────────────────────────────

    def _verify(self, args: dict[str, Any]) -> dict[str, Any] | None:
        """Return the token claims iff the authenticated_context arg is a valid,
        unexpired token minted for THIS session; else None."""
        token = str(args.get("authenticated_context", "")).strip()
        payload = _jwt_decode(token)
        if not payload or payload.get("sid") != self._auth_salt:
            return None
        return payload

    def _selected_account(
        self, args: dict[str, Any], payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        """The account for account_id, iff it belongs to the token AND the customer
        actually picked it via choose_account. Enforces "explicitly selected"."""
        account_id = str(args.get("account_id", "")).strip()
        owned = set(payload.get("accounts") or [])
        if account_id not in owned or account_id not in self._selected:
            return None
        return _account_by_id(account_id)

    def _selected_card(
        self, args: dict[str, Any], payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        """The card for card_id, iff it belongs to the token AND the customer actually
        picked it via choose_credit_card. Mirrors ``_selected_account``."""
        card_id = str(args.get("card_id", "")).strip()
        owned = set(payload.get("cards") or [])
        if card_id not in owned or card_id not in self._selected_cards:
            return None
        return _card_by_id(card_id)

    async def _authenticate(self, interaction) -> str:
        nonce = secrets.token_hex(8)
        fut: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._pending[nonce] = fut
        logger.info("aura: authenticate -> opening secure sign-in")
        interaction.action(
            "open_auth",
            {
                "nonce": nonce,
                "name": _DEMO_CUSTOMER["name"],
                "masked_mobile": _DEMO_CUSTOMER["masked_mobile"],
            },
        )
        try:
            token = await asyncio.wait_for(fut, timeout=_INTERACTION_TIMEOUT_S)
        except TimeoutError:
            return str(
                {
                    "status": "not_authenticated",
                    "error": "The customer did not complete the sign-in. Offer to try again.",
                }
            )
        finally:
            self._pending.pop(nonce, None)
        if token == _CANCELLED:
            return str(
                {
                    "status": "declined",
                    "error": "The customer chose not to sign in right now. Acknowledge warmly and "
                    "offer to help another way; you can try again whenever they're ready.",
                }
            )
        return str(
            {
                "status": "authenticated",
                "authenticated_context": token,
                "customer_name": _DEMO_CUSTOMER["name"],
                "note": "Signed in. Now call choose_account(authenticated_context) so the "
                "customer picks which account to view.",
            }
        )

    async def _choose_account(self, interaction, args: dict[str, Any]) -> str:
        payload = self._verify(args)
        if not payload:
            return str(
                {
                    "status": "not_authenticated",
                    "error": "No valid sign-in. Call authenticate() first.",
                }
            )
        owned = set(payload.get("accounts") or [])
        accounts = [
            {k: a[k] for k in _ACCOUNT_FIELDS} for a in _DEMO_ACCOUNTS if a["account_id"] in owned
        ]
        nonce = secrets.token_hex(8)
        fut: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._pending[nonce] = fut
        logger.info("aura: choose_account -> picker ({} accounts)", len(accounts))
        interaction.action("choose_account", {"nonce": nonce, "accounts": accounts})
        try:
            account_id = await asyncio.wait_for(fut, timeout=_INTERACTION_TIMEOUT_S)
        except TimeoutError:
            return str(
                {"status": "no_selection", "error": "The customer did not pick an account yet."}
            )
        finally:
            self._pending.pop(nonce, None)
        if account_id == _CANCELLED:
            return str(
                {
                    "status": "declined",
                    "error": "The customer closed the account picker without choosing. Ask which "
                    "account they'd like to view, or offer other help.",
                }
            )
        acc = _account_by_id(account_id)
        if not acc or account_id not in owned:
            return str({"status": "invalid_selection", "error": "That account is not available."})
        self._selected.add(account_id)
        return str(
            {
                "status": "account_selected",
                "account_id": acc["account_id"],
                "type": acc["type"],
                "branch": acc["branch"],
                "nickname": acc.get("nickname"),
                "masked_number": acc["masked_number"],
            }
        )

    def _get_account_balance(self, interaction, args: dict[str, Any]) -> str:
        payload = self._verify(args)
        if not payload:
            return str({"status": "not_authenticated", "error": "Call authenticate() first."})
        acc = self._selected_account(args, payload)
        if not acc:
            return str(
                {
                    "status": "account_not_selected",
                    "error": "Ask the customer to choose an account first (call choose_account).",
                }
            )
        as_of = datetime.now(UTC).astimezone().strftime("%Y-%m-%d")
        logger.info("aura: get_account_balance {}", acc["account_id"])
        interaction.action(
            "show_balance",
            {
                "account": {k: acc[k] for k in _ACCOUNT_FIELDS},
                "balance": acc["balance"],
                "currency": acc["currency"],
                "as_of": as_of,
            },
        )
        return str(
            {
                "status": "balance",
                "account": {
                    "nickname": acc.get("nickname"),
                    "masked_number": acc["masked_number"],
                    "branch": acc["branch"],
                },
                "balance": acc["balance"],
                "currency": acc["currency"],
                "as_of": as_of,
            }
        )

    def _get_statement(self, interaction, args: dict[str, Any]) -> str:
        payload = self._verify(args)
        if not payload:
            return str({"status": "not_authenticated", "error": "Call authenticate() first."})
        acc = self._selected_account(args, payload)
        if not acc:
            return str(
                {
                    "status": "account_not_selected",
                    "error": "Ask the customer to choose an account first (call choose_account).",
                }
            )
        today = datetime.now(UTC).astimezone().date()
        start = _parse_date(args.get("start_date")) or (today - timedelta(days=90))
        end = _parse_date(args.get("end_date")) or today
        rows: list[dict[str, Any]] = []
        for days_ago, desc, amount, kind in _DEMO_TXNS.get(acc["account_id"], []):
            d = today - timedelta(days=days_ago)
            if start <= d <= end:
                rows.append(
                    {"date": d.isoformat(), "description": desc, "amount": amount, "kind": kind}
                )
        rows.sort(key=lambda r: r["date"], reverse=True)
        credits = sum(r["amount"] for r in rows if r["kind"] == "credit")
        debits = sum(r["amount"] for r in rows if r["kind"] == "debit")
        logger.info("aura: get_statement {} ({} txns)", acc["account_id"], len(rows))
        interaction.action(
            "show_statement",
            {
                "account": {k: acc[k] for k in _ACCOUNT_FIELDS},
                "from_date": start.isoformat(),
                "to_date": end.isoformat(),
                "transactions": rows,
                "currency": acc["currency"],
            },
        )
        return str(
            {
                "status": "statement",
                "from": start.isoformat(),
                "to": end.isoformat(),
                "count": len(rows),
                "total_credits": credits,
                "total_debits": debits,
                "transactions": rows,
                "currency": acc["currency"],
            }
        )

    async def _choose_credit_card(self, interaction, args: dict[str, Any]) -> str:
        payload = self._verify(args)
        if not payload:
            return str(
                {
                    "status": "not_authenticated",
                    "error": "No valid sign-in. Call authenticate() first.",
                }
            )
        owned = set(payload.get("cards") or [])
        cards = [{k: c[k] for k in _CARD_FIELDS} for c in _DEMO_CARDS if c["card_id"] in owned]
        nonce = secrets.token_hex(8)
        fut: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._pending[nonce] = fut
        logger.info("aura: choose_credit_card -> picker ({} cards)", len(cards))
        interaction.action("choose_credit_card", {"nonce": nonce, "cards": cards})
        try:
            card_id = await asyncio.wait_for(fut, timeout=_INTERACTION_TIMEOUT_S)
        except TimeoutError:
            return str({"status": "no_selection", "error": "The customer did not pick a card yet."})
        finally:
            self._pending.pop(nonce, None)
        if card_id == _CANCELLED:
            return str(
                {
                    "status": "declined",
                    "error": "The customer closed the card picker without choosing. Ask which "
                    "card they'd like to manage, or offer other help.",
                }
            )
        card = _card_by_id(card_id)
        if not card or card_id not in owned:
            return str({"status": "invalid_selection", "error": "That card is not available."})
        self._selected_cards.add(card_id)
        return str(
            {
                "status": "card_selected",
                "card_id": card["card_id"],
                "product": card["product"],
                "network": card["network"],
                "masked_number": card["masked_number"],
            }
        )

    def _show_card_controls(self, interaction, args: dict[str, Any]) -> str:
        payload = self._verify(args)
        if not payload:
            return str({"status": "not_authenticated", "error": "Call authenticate() first."})
        card = self._selected_card(args, payload)
        if not card:
            return str(
                {
                    "status": "card_not_selected",
                    "error": "Ask the customer to choose a card first (call choose_credit_card).",
                }
            )
        controls = card["controls"]
        logger.info("aura: show_card_controls {}", card["card_id"])
        interaction.action(
            "show_card_controls",
            {
                "card": {k: card[k] for k in _CARD_FIELDS},
                "credit_limit": card["credit_limit"],
                "controls": controls,
            },
        )
        return str(
            {
                "status": "controls_open",
                "card": {"product": card["product"], "masked_number": card["masked_number"]},
                "controls": controls,
                "note": "The usage & limits form is now on screen for the customer to adjust and "
                "save themselves. Do NOT read the toggles aloud — the form shows them. If the "
                "change is about international usage, this is the moment for the trip / forex-card "
                "cross-sell (one short line).",
            }
        )

    # ── Screen state ──────────────────────────────────────────────────────────

    def _screen_summary(self) -> dict[str, Any]:
        state = self.current_state
        if not state:
            return {"screen": "home", "note": "The customer is on the Aura Bank home page."}
        # The browser's state_sync snapshot already carries everything (article,
        # video position, and the active tool: calculator / application / compare /
        # locator / checklist / ticket), so return it as-is.
        return state

    def _ingest_state(self, data: dict[str, Any]) -> None:
        snapshot = data.get("screen_state")
        self.current_state = snapshot if isinstance(snapshot, dict) else None
        self._state_synced = True
        logger.info(
            "aura: state_sync ingested (screen={})", (self.current_state or {}).get("screen")
        )

    # ── Browser → brain: resolve the blocking secure tools ────────────────────

    def _cancel_pending(self, data: dict[str, Any]) -> None:
        nonce = str(data.get("nonce", ""))
        fut = self._pending.get(nonce)
        if fut is None or fut.done():
            return
        fut.set_result(_CANCELLED)
        logger.info("aura: interaction cancelled by customer")

    def _complete_auth(self, data: dict[str, Any]) -> None:
        """The browser reports the customer finished the on-screen sign-in. THIS is
        where the server mints the token — only reachable after that authorisation,
        which is why the LLM can never produce one itself."""
        nonce = str(data.get("nonce", ""))
        fut = self._pending.get(nonce)
        if fut is None or fut.done():
            logger.info("aura: auth_complete for unknown/stale nonce")
            return
        now = int(time.time())
        token = _jwt_encode(
            {
                "sub": _DEMO_CUSTOMER["id"],
                "name": _DEMO_CUSTOMER["name"],
                "accounts": [a["account_id"] for a in _DEMO_ACCOUNTS],
                "cards": [c["card_id"] for c in _DEMO_CARDS],
                "sid": self._auth_salt,
                "iat": now,
                "exp": now + _AUTH_TTL_SECONDS,
            }
        )
        fut.set_result(token)
        logger.info("aura: auth_complete -> token minted for {}", _DEMO_CUSTOMER["name"])

    def _complete_account(self, data: dict[str, Any]) -> None:
        nonce = str(data.get("nonce", ""))
        account_id = str(data.get("account_id", ""))
        fut = self._pending.get(nonce)
        if fut is None or fut.done():
            logger.info("aura: account_selected for unknown/stale nonce")
            return
        fut.set_result(account_id)
        logger.info("aura: account_selected -> {}", account_id)

    def _complete_card(self, data: dict[str, Any]) -> None:
        nonce = str(data.get("nonce", ""))
        card_id = str(data.get("card_id", ""))
        fut = self._pending.get(nonce)
        if fut is None or fut.done():
            logger.info("aura: card_selected for unknown/stale nonce")
            return
        fut.set_result(card_id)
        logger.info("aura: card_selected -> {}", card_id)
