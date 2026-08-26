"""AuraBrain — the Aura Bank L1 banking support assistant, hosted in the control plane.

A ``voqalize.sdk.Brain`` (LLM + screen-driving tools + per-session state), ported
verbatim from the in-process managed brain ``pygato.managed.aura`` (its ``AuraBot``).
PyGato dials this brain's WebSocket per session; ``respond`` runs a manual Gemini
function-calling loop where **each LLM call is one ``interaction.say()`` bracket**
(1:1 with the wire): speak a short line, call a tool, feed the result back.

This is the most complex demo — it fuses three workstreams:

  * **Authenticated account tools** (``show_auth_popup`` → ``choose_account`` →
    ``get_account_balance`` / ``get_statement``, plus ``choose_credit_card`` →
    ``show_card_controls``). These are the demo's security story: a deliberately real
    HS256 token the LLM can only *pass back* — it can never mint one, because only the
    server signs, and only after the customer authorises the on-screen sign-in.
  * **Journey upsell / cross-sell** — the forex-card + FD cross-sells baked into the
    system prompt.
  * **Knowledge embed** — the KB/video/facts guides plus ``aura_facts.md`` (copied
    verbatim; the control plane cannot import pygato) interpolated into the prompt.

Two mechanics carry the demo, and both run through :meth:`on_rtvi`:

  * **Nothing waits on the customer.** ``show_auth_popup`` / ``choose_account`` /
    ``choose_credit_card`` put a dialog on screen and return in the same breath. What
    the customer then does arrives later as a browser message, and the brain appends a
    line of context saying what happened and handing over whatever it produced — the
    signed token, the chosen account. A tool that awaited the customer would mute their
    mic exactly while asking them to act, and would model a handshake that does not
    exist: they may never do it, may do it in five minutes, or may have done it
    already.
  * **Silent screen-state awareness.** The browser pushes a compact ``state_sync``
    snapshot on connect and after every change, and :meth:`_append_screen_state` folds
    the freshest one into the context without taking the floor, so the assistant always
    reasons from what's on screen (``get_screen_context`` reads the same snapshot).

The LLM's ``genai.Client`` is **dependency-injected**; the brain owns the
prompt, the tool schemas, and this session's auth/selection/screen state. The
conversation record is framework-owned (``interaction.conversation``), rebuilt into
Gemini's working context each turn by the :class:`GeminiBrain` base.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import json
import random
import secrets
import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from google import genai
from google.genai import interactions as gi
from loguru import logger
from pydantic import BaseModel, Field
from voqalize_demos import DEFAULT_MODEL

from voqalize.sdk import Action, RTVIMessage, RTVIType, Session
from voqalize.sdk.gemini_interactions import GeminiInteractionsBrain
from voqalize.sdk.wire import Config, Language, SttConfig, TtsConfig, Voice

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

# What to tell the model when the customer closes a dialog without answering it.
_DISMISSED = {
    "auth": "The customer closed the secure sign-in without signing in, so they are NOT "
    "authenticated and no account or card tool will work. Acknowledge it warmly, offer to "
    "help with something that needs no sign-in, and offer to open it again whenever they "
    "are ready.",
    "account": "The customer closed the account picker without choosing one. Ask which "
    "account they meant, or offer other help.",
    "card": "The customer closed the card picker without choosing one. Ask which card they "
    "wanted to manage, or offer other help.",
}

# What a tool says when the step before it has not happened. These are the signs on
# the must-happen-before edges: the model is told which step is missing and that the
# customer, not it, has to take it — so a model that skipped ahead walks back and
# asks rather than retrying or inventing a token.
_NOT_SIGNED_IN = (
    "The customer is not signed in, so this is refused. Call show_auth_popup(), say one short "
    "line asking them to authorise it, and wait to be handed an authenticated_context. Do not "
    "retry this call until you have one."
)
_NO_ACCOUNT = (
    "The customer has not picked an account, so this is refused. Call "
    "choose_account(authenticated_context) and wait to be told which one they tapped. Do not "
    "guess an account_id."
)
_NO_CARD = (
    "The customer has not picked a card, so this is refused. Call "
    "choose_credit_card(authenticated_context) and wait to be told which one they tapped. Do "
    "not guess a card_id."
)


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


# One hardcoded demo customer + their accounts. show_auth_popup() "signs them in";
# choose_account() lets them pick which account to look at.
_DEMO_CUSTOMER = {"id": "cust_ax_88213", "name": "Ananya Sharma", "masked_mobile": "••••••4021"}

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
1. show_auth_popup() — puts a secure sign-in on screen for the customer to authorise themselves. It returns AT ONCE, before they have signed in. Say one short line ("I'll put a secure sign-in on your screen — authorise it whenever you're ready"), then carry on with whatever else they asked. You will be TOLD when they sign in, and handed an 'authenticated_context' token then. Never ask them to read anything out.
2. choose_account(authenticated_context) — puts the customer's accounts on screen so they tap ONE. This also returns at once; you will be told which account they picked.
3. get_account_balance(authenticated_context, account_id) — the current balance. The balance shows on screen; say just the one figure in words ("your Salary account has about three lakh forty-nine thousand rupees") and stop.
4. get_statement(authenticated_context, account_id, start_date, end_date) — recent transactions; both dates are OPTIONAL and default to the LAST THREE MONTHS. The statement screen already lists every transaction — do NOT enumerate them aloud. Give ONE short highlight line (e.g. "salary's in and your biggest spend was rent") and point at the screen for the rest.

HARD RULES (these are enforced by the server, not just etiquette):
- NEVER call get_account_balance or get_statement until you have been HANDED BOTH a real authenticated_context AND an account_id the customer picked. Both arrive as messages telling you what the customer just did — not as a tool's return value. Until then, the earlier steps have not happened.
- NEVER invent, guess, or reuse from memory an authenticated_context or an account_id — pass back ONLY the exact values you were handed. You cannot fabricate a valid token; the server verifies it and will reject a made-up one.
- If a tool answers "not authenticated" or "choose an account first", the customer has not done that step yet. Do NOT retry the same call. Open the dialog if it isn't up, say one short line asking them to do it, and wait to be told.
- The customer may take a while, or may never do it. That is fine — stay useful in the meantime and never sit silent waiting.
- Reassure the customer it's secure and you only VIEW — you never move money and never need their OTP, PIN or password to sign them in."""


_CARD_CONTROL_GUIDE = """CREDIT-CARD CONTROLS — changing a card's limits / international usage (secure, reuses the same sign-in):
When the customer wants to raise or enable something on their CREDIT card — international spend/usage, the domestic limit, tap-to-pay (contactless), online use, or the ATM cash limit — drive it on screen: you OPEN the controls, the customer sets and saves them. STRICT ORDER (later tools refuse if you skip a step):
1. AUTHENTICATE ONLY IF NEEDED. If you already hold an authenticated_context from earlier this call, reuse it and do NOT sign in again. Otherwise call show_auth_popup() and wait to be handed one; it does not wait for you.
2. choose_credit_card(authenticated_context) — puts the cards on screen so the customer taps WHICH one. Returns at once; you will be told which card they picked.
3. show_card_controls(authenticated_context, card_id) — opens that card's usage & limits form (international/domestic on-off, contactless, online, and the spend / ATM-cash limits). The customer adjusts and saves it themselves. Say ONE short line pointing at the screen ("your card controls are up — flip International on and set the limit there"); do NOT read the toggles aloud.
4. AS THE FORM COMES UP, this is the natural moment for Journey A (cross-sell): enabling international usually means a trip, so ask one light trip question and, if it fits, offer a forex card.
5. If they want the forex card, once they've set their limits, call show_forex_card() and let them tap 'Request this card' — that captures the lead.

Same guardrails as account access: NEVER invent or guess an authenticated_context or a card_id (pass back only what you were handed); you only OPEN the controls, you never change a limit or move money; and never ask for OTP, PIN, CVV, card number or password."""


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


# ─── Screen actions ────────────────────────────────────────────────────────────
# One class per ui_command the /aura console renders. The class name IS the
# command the browser switches on (``OpenArticle`` → ``open_article``) and the
# fields are the payload it reads — see ``frontend/src/store.tsx``. These are the
# screen's contract, not the model's: a tool takes its arguments flat and builds
# the action here, so an argument the model gives and a field the browser needs
# stay free to differ (``raise_ticket`` mints the reference; ``run_calculator``
# solves the maths).


class OpenHome(Action):
    """Back to the Aura Bank home page."""


class OpenHelpCenter(Action):
    """The help centre's category index."""


class OpenCategory(Action):
    """One help-centre category's article list."""

    category: str


class OpenArticle(Action):
    """One help article, full screen."""

    article_id: str


class PlayHelpVideo(Action):
    """Start Aura's own how-to clip, muted, at a given second."""

    video_id: str
    start_sec: int


class HighlightStep(Action):
    """Move the on-screen step list's focus to one step."""

    index: int


class SeekVideo(Action):
    """Jump the playing clip to another second."""

    start_sec: int


class PauseVideo(Action):
    """Hold the clip where it is."""


class ResumeVideo(Action):
    """Play on from where it was paused."""


class ShowContact(Action):
    """The helpline panel, headed by what they were stuck on."""

    topic: str


# The three closed vocabularies a tool parameter and its Action share. Declared
# once: the tool's signature is what Gemini is offered, the Action's field is what
# the browser is typed against, and they cannot drift into two different lists.
CalcKind = Literal["emi", "fd", "eligibility"]
Product = Literal["savings", "credit_card", "loan"]
CompareKind = Literal["credit_card", "savings"]
Channel = Literal["whatsapp", "sms"]


class RunCalculator(Action):
    """The calculator screen, filled in and already solved.

    ``inputs`` carries the defaults the customer never gave, because the screen
    shows its own working — and ``result`` is computed here rather than in the
    browser so the figure Aria speaks and the figure on screen cannot drift."""

    kind: CalcKind
    inputs: dict[str, float]
    result: dict[str, float]


class StartApplication(Action):
    """Open a blank product application."""

    product: Product


class PrefillField(Action):
    """Type one value into the open application."""

    field: str
    value: str


class SubmitApplication(Action):
    """Send the open application — only ever after the customer says so."""


class CompareItem(BaseModel):
    """One product in a comparison, as its column renders."""

    id: str = Field(description="Short slug for this option, unique within the list.")
    name: str = Field(description="The real Aura product name, in clean English.")
    features: list[str] = Field(
        default_factory=list, description="Three or four short feature lines, in clean English."
    )


class Compare(Action):
    """The side-by-side comparison table, with one column starred."""

    kind: CompareKind
    items: list[CompareItem]
    recommend_id: str
    recommend_reason: str


class BranchResult(BaseModel):
    """One branch or ATM, as its card renders."""

    name: str = Field(description="Branch or ATM name, in clean English.")
    address: str = Field(default="", description="One-line street address, in clean English.")
    kind: Literal["branch", "atm"] = Field(default="branch", description="Which of the two it is.")
    ifsc: str | None = Field(default=None, description="IFSC code — branches only.")
    hours: str | None = Field(
        default=None, description="Opening hours, e.g. 'Mon-Sat, ten to four'."
    )


class FindBranch(Action):
    """The branch/ATM locator, showing results for one pincode."""

    pincode: str
    results: list[BranchResult]


class ShowChecklist(Action):
    """A titled list of short lines — documents, eligibility, next steps."""

    title: str
    items: list[str]


class SendToPhone(Action):
    """The 'sent to your phone' confirmation."""

    what: str
    channel: Channel
    number: str


class RaiseTicket(Action):
    """The ticket receipt, with the reference the server minted."""

    reference: str
    topic: str
    summary: str


class Spotlight(Action):
    """Draw a ring around one element on screen."""

    target: str
    label: str


class ShowForexCard(Action):
    """The Multi-Currency Forex Card screen, with its one-tap request."""


# ── The secure screens ────────────────────────────────────────────────────────
# The three that carry a ``nonce`` ask the customer for something. The brain mints
# the nonce, dispatches, and returns; the browser sends the same nonce back when
# the customer answers. Nothing waits on that — the nonce is there so the answer can
# be matched to the dialog that asked for it, and so a stale or replayed one closes
# nothing.


class OpenAuth(Action):
    """The secure sign-in sheet. The browser answers with ``auth_complete`` (or
    ``auth_cancelled``), carrying this nonce; the token is minted there, never
    here — see :meth:`AuraBrain._complete_auth`."""

    nonce: str
    name: str
    masked_mobile: str


class AccountRef(BaseModel):
    """An account as the picker and the balance card show it — the projection of
    the bank's record that is safe to send, with the money left behind."""

    account_id: str
    type: str
    branch: str
    nickname: str
    masked_number: str


class CardRef(BaseModel):
    """A credit card as the screen shows it. Never the real number."""

    card_id: str
    network: str
    product: str
    variant: str
    masked_number: str


class StatementTxn(BaseModel):
    """One row of a statement."""

    date: str
    description: str
    amount: float
    kind: Literal["debit", "credit"]


class CardControls(BaseModel):
    """A card's current usage and limit settings, as the form renders them."""

    domestic_enabled: bool
    international_enabled: bool
    contactless_enabled: bool
    online_enabled: bool
    domestic_limit: float
    international_limit: float
    atm_cash_limit: float


class ChooseAccount(Action):
    """The account picker. Answered by ``account_selected`` / ``account_cancelled``."""

    nonce: str
    accounts: list[AccountRef]


class ShowBalance(Action):
    """The balance card for one account, as of a date."""

    account: AccountRef
    balance: float
    currency: str
    as_of: str


class ShowStatement(Action):
    """A dated transaction list for one account."""

    account: AccountRef
    from_date: str
    to_date: str
    transactions: list[StatementTxn]
    currency: str


class ChooseCreditCard(Action):
    """The card picker. Answered by ``card_selected`` / ``card_cancelled``."""

    nonce: str
    cards: list[CardRef]


class ShowCardControls(Action):
    """The usage & limits form for one card — the customer edits and saves it
    themselves, so the assistant never reads the toggles aloud."""

    card: CardRef
    credit_limit: float
    controls: CardControls


class AuraBrain(GeminiInteractionsBrain):
    """One per session. The Aura Bank L1 support assistant: LLM + help-centre /
    calculator / application / comparison / branch tools + the four secure account
    tools + the two secure credit-card tools + this session's auth/selection/screen
    state.

    Nothing here waits on the customer. ``show_auth_popup``, ``choose_account``
    and ``choose_credit_card`` dispatch a dialog and return; the customer answers
    it in their own time, or never, and the answer arrives on :meth:`on_rtvi` —
    which appends a line of context saying what they did. The ordering that the
    waiting used to enforce is carried instead by the tool signatures: every
    account and card tool takes an ``authenticated_context`` this brain mints and
    re-verifies, so a model that skips ahead gets an error naming the step it
    skipped rather than a number it should not have.
    """

    def __init__(self, *, client: genai.Client, model: str = DEFAULT_MODEL) -> None:
        super().__init__(
            client=client,
            system_instruction=_SYSTEM_INSTRUCTION,
            model=model,
            # Headroom above the base default: aura's secure flows chain several
            # tool hops in one turn (authenticate → choose → read).
            max_tool_hops=8,
        )
        # Session payload (init). Aura does not seed any account data from it
        # (accounts and cards are hardcoded demo data), so it does not mutate the
        # system prompt; it is kept because the screen half reads it.
        self.payload: dict[str, Any] = {}

        # Latest screen snapshot the browser has told us about, and whether any
        # state_sync has arrived yet.
        self.current_state: dict[str, Any] | None = None
        self._state_synced = False
        self._last_state_note: str | None = None

        # Authenticated-account demo state. ``_open_dialogs`` maps the nonce of
        # each dialog now on screen to what it asks for, so a card answer cannot
        # close the sign-in and a stale answer is discarded; ``_token`` is the
        # signed token once the customer has authorised the sign-in, which makes a
        # second show_auth_popup() a no-op; ``_selected`` / ``_selected_cards``
        # record what the customer actually picked (balance/statement/controls
        # require it). ``_auth_salt`` binds minted tokens to this session instance.
        self._open_dialogs: dict[str, str] = {}
        self._token: str | None = None
        self._selected: set[str] = set()
        self._selected_cards: set[str] = set()
        self._auth_salt = secrets.token_hex(8)

    @property
    def tools(self) -> list[Callable[..., Any]]:
        """The twenty-eight tools Aria may call.

        The last six are the secure ones. Three of those open a dialog and return
        without waiting for it; the other three refuse until the customer has
        answered one. See the section they live in."""
        return [
            self.open_home,
            self.open_help_center,
            self.open_category,
            self.open_article,
            self.play_help_video,
            self.highlight_step,
            self.seek_video,
            self.pause_video,
            self.resume_video,
            self.show_contact,
            self.get_screen_context,
            self.run_calculator,
            self.start_application,
            self.prefill_field,
            self.submit_application,
            self.compare,
            self.find_branch,
            self.show_checklist,
            self.send_to_phone,
            self.raise_ticket,
            self.spotlight,
            self.show_forex_card,
            self.show_auth_popup,
            self.choose_account,
            self.get_account_balance,
            self.get_statement,
            self.choose_credit_card,
            self.show_card_controls,
        ]

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        # The payload rides the connect request; aura does not use it to seed the
        # prompt, but the screen half reads it.
        self.payload = dict(session.init or {})
        # Aria's own voice — not the connecting page's to choose, so it is settled
        # here rather than sent with the connect request. `language` moves both
        # legs at once: the recognizer's hint, and the TTS reference clip, which is
        # the accent. This lands before the greeting.
        await session.configure(
            Config(
                stt=SttConfig(language=Language.EN),
                tts=TtsConfig(voice=Voice.OMNIVOICE_GAURI, language=Language.EN),
            )
        )
        logger.info("aura: session start")

    async def greet(self, session: Session) -> str:
        """The opener, written not generated — the customer is already looking at
        the page, and a support agent who makes them wait on a first token has
        already made them wait."""
        return _GREETING

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Browser→Brain client message. This is where everything the customer does
        on screen arrives, and none of it takes the floor — each folds a line into
        the context, which the model reads on its next turn:

        * ``state_sync`` — a compact snapshot of what's on screen (sent on connect
          and after every change), so the assistant always knows what the customer
          is looking at.
        * ``auth_complete`` — the customer finished the on-screen sign-in. THIS is
          where the server mints the token: it is only reachable via that
          authorisation, which is why the LLM can never produce one itself. The
          token goes into the context as something the model was handed.
        * ``account_selected`` / ``card_selected`` — the customer picked one in the
          on-screen picker; recorded here, and named in the context so the model
          knows what it may now read.
        * ``auth_cancelled`` / ``account_cancelled`` / ``card_cancelled`` — the
          customer dismissed the dialog, which is an answer too: the context says so
          and the model asks rather than assuming.
        """
        if msg.type is not RTVIType.CLIENT_MESSAGE or not isinstance(msg.data, dict):
            return
        name = msg.data.get("t")
        data = msg.data.get("d")
        data = data if isinstance(data, dict) else {}
        if name == "state_sync":
            self._ingest_state(data)
            self._append_screen_state()
        elif name == "auth_complete":
            self._complete_auth(data)
        elif name == "account_selected":
            self._complete_account(data)
        elif name == "card_selected":
            self._complete_card(data)
        elif name in ("auth_cancelled", "account_cancelled", "card_cancelled"):
            self._cancel_pending(data)

    # ─── Screen state: fold the snapshot into the context, silently ─────

    def _append_screen_state(self) -> None:
        """Put the freshest snapshot in front of the model, taking no floor.

        The context is append-only and the browser re-sends on every change, so a
        snapshot that has not moved is not appended twice — otherwise a five-minute
        call puts the same screen in front of the model a hundred times over."""
        if not self._state_synced:
            return
        if self.current_state is None:
            blob = "the customer is on the Aura Bank home page."
        else:
            try:
                blob = json.dumps(self.current_state, ensure_ascii=False)
            except (TypeError, ValueError):
                blob = str(self.current_state)
        note = (
            "CURRENT SCREEN STATE (authoritative — what the customer is looking at right "
            "now; reason from this): " + blob
        )
        if note == self._last_state_note:
            return
        self._last_state_note = note
        self._append_note(note)

    def _append_note(self, text: str) -> None:
        """Put one line in front of the model without taking the floor.

        Appended as the customer's own content, which is what it is: every note that
        goes through here reports something they did on screen. It starts no turn —
        nothing about a tap means they stopped speaking — so the model reads it on
        its next one."""
        self.append_to_context(gi.UserInputStep(content=[gi.TextContent(text=text)]))

    # ─── Tools: the help centre ─────────────────────────────────────────

    async def open_home(self) -> str:
        """Take the customer back to the Aura Bank home page."""
        logger.info("aura: open_home")
        self.session.dispatch(OpenHome())
        return "home open"

    async def open_help_center(self) -> str:
        """Open the help centre's index of categories — for a customer who is
        browsing rather than asking one specific thing."""
        logger.info("aura: open_help_center")
        self.session.dispatch(OpenHelpCenter())
        return "help centre open"

    async def open_category(self, category: str) -> str:
        """Open one help-centre category so its articles are listed on screen.

        Args:
            category: The category to list.
        """
        category = category.strip()
        if not category:
            return "need a category"
        logger.info("aura: open_category {!r}", category)
        self.session.dispatch(OpenCategory(category=category))
        return f"category {category} open"

    async def open_article(self, article_id: str) -> str:
        """Open the help article that answers their question, full screen.

        This is the FIRST thing to do for any how-to question: speak one short
        line, then call this so the page is up before you explain anything.

        Args:
            article_id: Id of the article for this topic.
        """
        article_id = article_id.strip()
        if not article_id:
            return "need an article_id"
        logger.info("aura: open_article {!r}", article_id)
        self.session.dispatch(OpenArticle(article_id=article_id))
        return f"article {article_id} open"

    # ─── Tools: the video ───────────────────────────────────────────────

    async def play_help_video(self, video_id: str, start_sec: int = 0) -> str:
        """Play Aura's own how-to clip, muted, from the second that answers their
        exact question — skip the intro.

        The customer watches while YOU narrate. The on-screen step list carries
        the steps, so never read them aloud.

        Args:
            video_id: Id of Aura's clip for this topic.
            start_sec: Second to start at — the chapter that answers them.
        """
        video_id = video_id.strip()
        if not video_id:
            return "need a video_id"
        start_sec = max(0, int(start_sec))
        logger.info("aura: play_help_video {} @{}s", video_id, start_sec)
        self.session.dispatch(PlayHelpVideo(video_id=video_id, start_sec=start_sec))
        return (
            f"playing {video_id} muted from {start_sec}s. Now narrate the steps in English "
            "in your own words; call highlight_step(index) as you describe each one."
        )

    async def highlight_step(self, index: int) -> str:
        """Move the on-screen step list's focus as you narrate — once per step, in
        order, with one short line that points at it rather than reciting it.

        Args:
            index: Zero-based index of the step to focus.
        """
        index = int(index)
        logger.info("aura: highlight_step {}", index)
        self.session.dispatch(HighlightStep(index=index))
        return f"step {index} highlighted"

    async def seek_video(self, start_sec: int = 0) -> str:
        """Jump the playing clip to another second — a different chapter, or back
        over something they missed.

        Args:
            start_sec: Second to jump to.
        """
        start_sec = max(0, int(start_sec))
        logger.info("aura: seek_video @{}s", start_sec)
        self.session.dispatch(SeekVideo(start_sec=start_sec))
        return f"seeked to {start_sec}s"

    async def pause_video(self) -> str:
        """Hold the clip where it is — they asked you to wait, or to talk."""
        logger.info("aura: pause_video")
        self.session.dispatch(PauseVideo())
        return "paused"

    async def resume_video(self) -> str:
        """Play on from where you paused."""
        logger.info("aura: resume_video")
        self.session.dispatch(ResumeVideo())
        return "resumed"

    async def show_contact(self, topic: str = "") -> str:
        """Put Aura's helpline numbers on screen. For anything genuinely
        account-specific, unresolved, or urgent — a lost or stolen card, or
        suspected fraud — show these immediately rather than playing a video.

        Args:
            topic: What they were stuck on, a few words in clean English.
        """
        topic = topic.strip()
        logger.info("aura: show_contact {!r}", topic)
        self.session.dispatch(ShowContact(topic=topic))
        return "contact shown: helpline 1860-200-0100, emergency card block +91 22 2000 0200"

    async def get_screen_context(self) -> str:
        """What the customer is looking at right now — screen, open article, video
        position. Call it before referring to something on screen you are not
        certain is still there."""
        where = self._screen_summary()
        logger.info("aura: get_screen_context -> {}", where.get("screen"))
        return str(where)

    # ─── Tools: calculators, applications, comparisons ──────────────────

    async def run_calculator(
        self,
        kind: CalcKind,
        principal: float | None = None,
        monthly_income: float | None = None,
        existing_emi: float | None = None,
        annual_rate: float | None = None,
        tenure_months: float | None = None,
    ) -> str:
        """Open an on-screen calculator, fill it in and solve it.

        You only need the AMOUNT from the customer. Rate, tenure and existing EMIs
        default to sensible values and are shown on screen, so do not insist on
        them. Say the ONE headline figure back in words with the indicative
        caveat, and let the screen carry the working.

        Args:
            kind: 'emi' for a loan repayment, 'fd' for deposit maturity,
                'eligibility' for how much they could borrow.
            principal: Loan or deposit amount in rupees — for 'emi' and 'fd'.
            monthly_income: Take-home monthly income in rupees — for 'eligibility'.
            existing_emi: What they already repay each month — for 'eligibility'.
            annual_rate: Annual interest rate as a percentage. Leave unset unless
                they state one.
            tenure_months: Term in MONTHS. Leave unset unless they state one.
        """
        given = {
            "principal": principal,
            "monthly_income": monthly_income,
            "existing_emi": existing_emi,
            "annual_rate": annual_rate,
            "tenure_months": tenure_months,
        }
        keys = {
            "emi": ("principal", "annual_rate", "tenure_months"),
            "fd": ("principal", "annual_rate", "tenure_months"),
            "eligibility": ("monthly_income", "existing_emi", "annual_rate", "tenure_months"),
        }[kind]
        inputs: dict[str, float] = dict(_CALC_DEFAULTS.get(kind, {}))
        for key in keys:
            value = given[key]
            if value is None:
                continue
            with contextlib.suppress(TypeError, ValueError):
                inputs[key] = float(value)
        result = _compute_calc(kind, inputs)
        logger.info("aura: run_calculator {} -> {}", kind, result)
        self.session.dispatch(RunCalculator(kind=kind, inputs=inputs, result=result))
        return str({"kind": kind, "inputs": inputs, "result": result})

    async def start_application(self, product: Product) -> str:
        """Begin a new-customer application — a real top-of-funnel lead, and it
        needs no login. Then prefill_field each detail they give you, and submit
        only once they clearly agree.

        Args:
            product: Which application to open.
        """
        logger.info("aura: start_application {}", product)
        self.session.dispatch(StartApplication(product=product))
        return f"{product} application started"

    async def prefill_field(self, field: str, value: str = "") -> str:
        """Type one detail into the open application.

        Args:
            field: One of name, mobile, email, city, pan, employment,
                monthly_income, loan_amount, tenure_years.
            value: What to type. It renders on screen, so keep it clean English.
        """
        field = field.strip()
        if not field:
            return "need a field"
        logger.info("aura: prefill_field {}", field)
        self.session.dispatch(PrefillField(field=field, value=value))
        return f"{field} filled"

    async def submit_application(self) -> str:
        """Send the open application. ONLY after the customer has clearly agreed —
        never auto-submit."""
        logger.info("aura: submit_application")
        self.session.dispatch(SubmitApplication())
        return "submitted"

    async def compare(
        self,
        kind: CompareKind,
        items: list[CompareItem],
        recommend_id: str = "",
        recommend_reason: str = "",
    ) -> str:
        """Put two or three real Aura products side by side and star the one that
        fits what they told you. Say only why you starred it; the table carries
        the rest.

        Args:
            kind: Which family is being compared.
            items: The options, with real Aura product names.
            recommend_id: The id of the option you are starring.
            recommend_reason: One short line saying why.
        """
        if not items:
            return "need items to compare"
        kind = "savings" if kind == "savings" else "credit_card"
        logger.info("aura: compare {} ({})", kind, len(items))
        self.session.dispatch(
            Compare(
                kind=kind,
                items=items,
                recommend_id=recommend_id,
                recommend_reason=recommend_reason,
            )
        )
        return f"comparison shown, {len(items)} options, recommended {recommend_id}"

    async def find_branch(self, pincode: str, results: list[BranchResult]) -> str:
        """Show nearby branches and ATMs for a pincode. Generate a few plausible
        ones for that area — they render on screen, so keep them clean English.

        Args:
            pincode: The pincode they gave you.
            results: A few nearby branches and ATMs.
        """
        logger.info("aura: find_branch {} ({})", pincode, len(results))
        self.session.dispatch(FindBranch(pincode=pincode, results=results))
        return f"{len(results)} results shown for {pincode}"

    async def show_checklist(self, title: str, items: list[str]) -> str:
        """Put a document or eligibility checklist on screen. Do not read it out;
        the screen is the answer.

        Args:
            title: Heading, in clean English.
            items: Short lines, in clean English.
        """
        logger.info("aura: show_checklist {!r} ({})", title, len(items))
        self.session.dispatch(ShowChecklist(title=title, items=[str(s) for s in items]))
        return f"checklist shown, {len(items)} items"

    async def send_to_phone(
        self,
        what: str = "this guide",
        channel: Channel = "whatsapp",
        number: str = "",
    ) -> str:
        """'Send' the guide or steps you just walked through to their phone — a
        take-away once you have explained something.

        Args:
            what: What you are sending, a few words in clean English.
            channel: Which channel to send it on.
            number: Their mobile number, if they gave one.
        """
        channel = "sms" if channel == "sms" else "whatsapp"
        logger.info("aura: send_to_phone {} via {}", what, channel)
        self.session.dispatch(SendToPhone(what=what, channel=channel, number=number))
        return f"sent on {channel}"

    async def raise_ticket(self, topic: str, summary: str = "") -> str:
        """Register a complaint or a callback request when something is genuinely
        account-specific or you could not resolve it. You get a reference number
        back — read it out in words and tell them to keep it.

        Args:
            topic: What it is about, a few words in clean English.
            summary: One sentence of detail, in clean English.
        """
        reference = _ticket_reference()
        logger.info("aura: raise_ticket {!r} -> {}", topic, reference)
        self.session.dispatch(RaiseTicket(reference=reference, topic=topic, summary=summary))
        return f"ticket raised, reference {reference}"

    async def spotlight(self, target: str, label: str = "") -> str:
        """Draw a ring around one element to point at it.

        Args:
            target: 'calc_result', an application field id (name, mobile, email,
                city, pan, employment, monthly_income, loan_amount, tenure_years),
                or 'recommend' for the starred comparison card.
            label: Optional short caption for the ring.
        """
        target = target.strip()
        if not target:
            return "need a target"
        logger.info("aura: spotlight {}", target)
        self.session.dispatch(Spotlight(target=target, label=label))
        return f"{target} spotlighted"

    async def show_forex_card(self) -> str:
        """Show the Aura Multi-Currency Forex Card with its one-tap request — the
        Journey A cross-sell, once they are enabling international card use.

        Point at it in one short line. Do not recite the benefits; the screen
        lists them, and the customer taps 'Request this card' to register."""
        logger.info("aura: show_forex_card")
        self.session.dispatch(ShowForexCard())
        return "forex card screen up; the customer taps 'Request this card' to register interest"

    # ─── Tools: the six secure ones ─────────────────────────────────────
    #
    # None of these block. ``show_auth_popup``, ``choose_account`` and
    # ``choose_credit_card`` dispatch a screen carrying a nonce and return; the
    # customer answers in their own time and ``on_rtvi`` folds the answer in.
    #
    # What holds the order is the signatures. ``authenticated_context`` is minted
    # in ``_complete_auth``, on the browser's report that the customer completed a
    # real on-screen sign-in — the only path that reaches the signing key. It is
    # never in the model's context as anything but an opaque string it was handed,
    # so no prompt can talk the model into producing one, and every tool below
    # re-verifies it against this session's salt before it returns a figure. The
    # error a missing or invalid one earns is the mechanism, not an edge case: it
    # is what pushes a model that skipped ahead back to asking the customer.

    def _verify(self, token: str) -> dict[str, Any] | None:
        """Return the token claims iff ``token`` is a valid, unexpired token minted
        for THIS session; else None."""
        payload = _jwt_decode(str(token or "").strip())
        if not payload or payload.get("sid") != self._auth_salt:
            return None
        return payload

    def _selected_account(self, account_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        """The account for ``account_id``, iff it belongs to the token AND the
        customer actually picked it via ``choose_account``. Enforces "explicitly
        selected"."""
        account_id = str(account_id or "").strip()
        owned = set(payload.get("accounts") or [])
        if account_id not in owned or account_id not in self._selected:
            return None
        return _account_by_id(account_id)

    def _selected_card(self, card_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        """The card for ``card_id``, iff it belongs to the token AND the customer
        actually picked it via ``choose_credit_card``. Mirrors
        :meth:`_selected_account`."""
        card_id = str(card_id or "").strip()
        owned = set(payload.get("cards") or [])
        if card_id not in owned or card_id not in self._selected_cards:
            return None
        return _card_by_id(card_id)

    def _open_dialog(self, kind: str) -> str:
        """Stamp a fresh nonce and record what it asks for."""
        nonce = secrets.token_hex(8)
        self._open_dialogs[nonce] = kind
        return nonce

    def _close_dialog(self, data: dict[str, Any], kind: str) -> bool:
        """True iff ``data`` answers a dialog of ``kind`` that is actually open.

        The nonce is what makes a browser message trustworthy: it was minted here,
        went out with the dialog, and closes that one dialog once. A replay, or a
        card answer arriving for a sign-in, matches nothing and is dropped."""
        nonce = str(data.get("nonce", ""))
        if self._open_dialogs.get(nonce) != kind:
            logger.info("aura: {} for an unknown or stale dialog", kind)
            return False
        del self._open_dialogs[nonce]
        return True

    async def show_auth_popup(self) -> str:
        """Put a secure sign-in on the customer's screen. Required before anything
        to do with THEIR money — balance, statement, or card.

        Returns as soon as the sheet is up. It does NOT wait: the customer
        authorises it in their own time, and you are told when they have and handed
        an ``authenticated_context`` then. Say one short line ("I'll put a secure
        sign-in on your screen") and carry on being useful. Do not call any account
        or card tool until you hold that token, and never write one yourself."""
        if self._token:
            return str(
                {
                    "status": "already_authenticated",
                    "authenticated_context": self._token,
                    "customer_name": _DEMO_CUSTOMER["name"],
                    "note": "Already signed in this call — do not ask them again. Call "
                    "choose_account(authenticated_context) so they pick which account to view.",
                }
            )
        nonce = self._open_dialog("auth")
        logger.info("aura: show_auth_popup -> secure sign-in on screen")
        self.session.dispatch(
            OpenAuth(
                nonce=nonce,
                name=str(_DEMO_CUSTOMER["name"]),
                masked_mobile=str(_DEMO_CUSTOMER["masked_mobile"]),
            )
        )
        return str(
            {
                "status": "sign_in_opened",
                "note": "The sign-in is on screen and the customer is NOT signed in yet. You "
                "will be told when they authorise it, and handed an authenticated_context. "
                "Until then no account or card tool will work. Never ask them to read anything "
                "out, and do not call this again while it is up.",
            }
        )

    async def choose_account(self, authenticated_context: str) -> str:
        """Put the customer's accounts on screen so they tap the one they mean.

        Returns as soon as the picker is up. It does NOT wait: the customer
        chooses — not you, and not by name over voice — and you are told which one
        when they do. Required before ``get_account_balance`` or ``get_statement``.

        Args:
            authenticated_context: The token you were handed when the customer
                signed in.
        """
        payload = self._verify(authenticated_context)
        if not payload:
            return str(
                {
                    "status": "not_authenticated",
                    "error": "That is not a valid sign-in for this call. The customer has not "
                    "signed in yet. Call show_auth_popup() and wait to be handed a token.",
                }
            )
        owned = set(payload.get("accounts") or [])
        accounts = [
            AccountRef.model_validate(a) for a in _DEMO_ACCOUNTS if a["account_id"] in owned
        ]
        nonce = self._open_dialog("account")
        logger.info("aura: choose_account -> picker ({} accounts)", len(accounts))
        self.session.dispatch(ChooseAccount(nonce=nonce, accounts=accounts))
        return str(
            {
                "status": "picker_opened",
                "accounts_shown": len(accounts),
                "note": "The account picker is on screen and nothing is chosen yet. You will be "
                "told which account the customer taps, with its account_id. Do not call "
                "get_account_balance or get_statement until then, and do not guess an account_id.",
            }
        )

    async def get_account_balance(self, authenticated_context: str, account_id: str) -> str:
        """The current balance of the account the customer picked, on screen.

        The figure is on the card in front of them — say what it means, don't read
        the digits back.

        Args:
            authenticated_context: The token you were handed when the customer
                signed in.
            account_id: The account the customer picked in ``choose_account``.
        """
        payload = self._verify(authenticated_context)
        if not payload:
            return str({"status": "not_authenticated", "error": _NOT_SIGNED_IN})
        acc = self._selected_account(account_id, payload)
        if not acc:
            return str({"status": "account_not_selected", "error": _NO_ACCOUNT})
        as_of = datetime.now(UTC).astimezone().strftime("%Y-%m-%d")
        logger.info("aura: get_account_balance {}", acc["account_id"])
        self.session.dispatch(
            ShowBalance(
                account=AccountRef.model_validate(acc),
                balance=acc["balance"],
                currency=acc["currency"],
                as_of=as_of,
            )
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

    async def get_statement(
        self,
        authenticated_context: str,
        account_id: str,
        start_date: str = "",
        end_date: str = "",
    ) -> str:
        """Put the account's transactions for a date range on screen.

        Defaults to the last ninety days. The list is on screen — summarise it
        (how many, what stands out), never read it out row by row.

        Args:
            authenticated_context: The token you were handed when the customer
                signed in.
            account_id: The account the customer picked in ``choose_account``.
            start_date: Start of the range, YYYY-MM-DD. Blank for ninety days ago.
            end_date: End of the range, YYYY-MM-DD. Blank for today.
        """
        payload = self._verify(authenticated_context)
        if not payload:
            return str({"status": "not_authenticated", "error": _NOT_SIGNED_IN})
        acc = self._selected_account(account_id, payload)
        if not acc:
            return str({"status": "account_not_selected", "error": _NO_ACCOUNT})
        today = datetime.now(UTC).astimezone().date()
        start = _parse_date(start_date) or (today - timedelta(days=90))
        end = _parse_date(end_date) or today
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
        self.session.dispatch(
            ShowStatement(
                account=AccountRef.model_validate(acc),
                from_date=start.isoformat(),
                to_date=end.isoformat(),
                transactions=[StatementTxn.model_validate(r) for r in rows],
                currency=acc["currency"],
            )
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

    async def choose_credit_card(self, authenticated_context: str) -> str:
        """Put the customer's credit cards on screen so they tap the one they mean.

        Returns as soon as the picker is up; it does NOT wait. You are told which
        card they tapped. Required before ``show_card_controls``.

        Args:
            authenticated_context: The token you were handed when the customer
                signed in.
        """
        payload = self._verify(authenticated_context)
        if not payload:
            return str(
                {
                    "status": "not_authenticated",
                    "error": "That is not a valid sign-in for this call. The customer has not "
                    "signed in yet. Call show_auth_popup() and wait to be handed a token.",
                }
            )
        owned = set(payload.get("cards") or [])
        cards = [CardRef.model_validate(c) for c in _DEMO_CARDS if c["card_id"] in owned]
        nonce = self._open_dialog("card")
        logger.info("aura: choose_credit_card -> picker ({} cards)", len(cards))
        self.session.dispatch(ChooseCreditCard(nonce=nonce, cards=cards))
        return str(
            {
                "status": "picker_opened",
                "cards_shown": len(cards),
                "note": "The card picker is on screen and nothing is chosen yet. You will be told "
                "which card the customer taps, with its card_id. Do not call show_card_controls "
                "until then, and do not guess a card_id.",
            }
        )

    async def show_card_controls(self, authenticated_context: str, card_id: str) -> str:
        """Open the usage & limits form for the card the customer picked — domestic
        and international use, online, contactless, ATM, and the spend limit.

        They adjust and save it themselves. Do NOT read the toggles aloud; the
        form shows them.

        Args:
            authenticated_context: The token you were handed when the customer
                signed in.
            card_id: The card the customer picked in ``choose_credit_card``.
        """
        payload = self._verify(authenticated_context)
        if not payload:
            return str({"status": "not_authenticated", "error": _NOT_SIGNED_IN})
        card = self._selected_card(card_id, payload)
        if not card:
            return str({"status": "card_not_selected", "error": _NO_CARD})
        controls = card["controls"]
        logger.info("aura: show_card_controls {}", card["card_id"])
        self.session.dispatch(
            ShowCardControls(
                card=CardRef.model_validate(card),
                credit_limit=card["credit_limit"],
                controls=CardControls.model_validate(controls),
            )
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

    # ── Browser → brain: what the customer did on screen ──────────────────────

    def _cancel_pending(self, data: dict[str, Any]) -> None:
        """The customer closed a dialog without answering it — which is an answer."""
        nonce = str(data.get("nonce", ""))
        kind = self._open_dialogs.pop(nonce, None)
        if kind is None:
            return
        logger.info("aura: {} dialog dismissed by the customer", kind)
        self._append_note(_DISMISSED[kind])

    def _complete_auth(self, data: dict[str, Any]) -> None:
        """The browser reports the customer finished the on-screen sign-in. THIS is
        where the server mints the token — only reachable after that authorisation,
        which is why the LLM can never produce one itself."""
        if not self._close_dialog(data, "auth"):
            return
        now = int(time.time())
        self._token = _jwt_encode(
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
        logger.info("aura: auth_complete -> token minted for {}", _DEMO_CUSTOMER["name"])
        self._append_note(
            "The customer has just authorised the secure sign-in, so they are now signed in. "
            f"Their authenticated_context is {self._token} — pass it back exactly as written to "
            "every account and card tool, and never alter it. Next, call "
            "choose_account(authenticated_context) if they want a balance or statement, or "
            "choose_credit_card(authenticated_context) if they want card controls."
        )

    def _complete_account(self, data: dict[str, Any]) -> None:
        """The customer tapped an account in the picker."""
        if not self._close_dialog(data, "account"):
            return
        account_id = str(data.get("account_id", ""))
        acc = _account_by_id(account_id)
        if acc is None:
            logger.info("aura: account_selected names no account we hold ({})", account_id)
            return
        self._selected.add(account_id)
        logger.info("aura: account_selected -> {}", account_id)
        self._append_note(
            f"The customer has just picked their {acc['type']} account "
            f"({acc['masked_number']}, {acc['branch']}). Its account_id is "
            f"{acc['account_id']} — you may now call get_account_balance or get_statement "
            "with it and the authenticated_context."
        )

    def _complete_card(self, data: dict[str, Any]) -> None:
        """The customer tapped a card in the picker."""
        if not self._close_dialog(data, "card"):
            return
        card_id = str(data.get("card_id", ""))
        card = _card_by_id(card_id)
        if card is None:
            logger.info("aura: card_selected names no card we hold ({})", card_id)
            return
        self._selected_cards.add(card_id)
        logger.info("aura: card_selected -> {}", card_id)
        self._append_note(
            f"The customer has just picked their {card['product']} card "
            f"({card['network']}, {card['masked_number']}). Its card_id is {card['card_id']} — "
            "you may now call show_card_controls with it and the authenticated_context."
        )
