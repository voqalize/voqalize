"""The system instruction and the written lines (greetings, confirmations) of the
bank's assistant. The character's name comes from ``persona.json``; every
number comes from ``data/*.json``."""

from __future__ import annotations

from typing import Any

from .bank import BRAND, CUSTOMER, PERSONA, PRODUCTS, inr

Mode = str  # "banking" | "account" | "cards" | "loans" | "home"
MODES = ("banking", "account", "cards", "loans", "home")


def spoken_name(lang: str) -> str:
    names: dict[str, str] = PERSONA.get("spoken_names") or {}
    return names.get(lang) or PERSONA["name"]


def _cards() -> str:
    lines: list[str] = []
    for c in PRODUCTS["credit_cards"]:
        lounge = c["lounge"]
        dom = "unlimited" if lounge["domestic_per_year"] is None else lounge["domestic_per_year"]
        lines.append(
            f"- {c['id']}: {c['name']} ({c['tier']}, {c['network']}). Joining {inr(c['joining_fee'])}, "
            f"annual {inr(c['annual_fee'])} (waived on {inr(c['fee_waiver_spend'])} a year). "
            f"{'; '.join(c['highlights'])}. Lounge: {dom} domestic, "
            f"{lounge['international_per_year']} international a year. Fuel: {c['fuel']['surcharge_waiver']}. "
            f"Forex markup {c['forex_markup']}%. Interest {c['interest_monthly']}% a month. "
            f"Needs income {inr(c['min_income_monthly'])} a month. Best for {c['best_for']}."
        )
    return "\n".join(lines)


def _loans() -> str:
    lines: list[str] = []
    for loan in PRODUCTS["loans"]:
        lines.append(
            f"- {loan['id']}: {loan['name']}: {loan['rate_min']}% to {loan['rate_max']}% a year "
            f"(typical {loan['rate_typical']}%), {inr(loan['amount_min'])} to {inr(loan['amount_max'])}, "
            f"{loan['tenure_min_months']} to {loan['tenure_max_months']} months. Processing fee: "
            f"{loan['processing_fee']}."
            + (f" {loan['ltv']}." if loan.get("ltv") else "")
            + (f" {loan['gold_rate_note']}" if loan.get("gold_rate_note") else "")
            + f" Documents: {'; '.join(loan['documents'])}."
        )
    return "\n".join(lines)


def _savings() -> str:
    out: list[str] = []
    for v in PRODUCTS["savings_variants"]:
        out.append(f"- {v['id']}: {v['name']}: {v['tagline']} {'; '.join(v['features'])}.")
    return "\n".join(out)


def _fd() -> str:
    fd = PRODUCTS["fd"]
    rates = "; ".join(f"{r['label']}: {r['rate']}%" for r in fd["rates"])
    return f"FD rates: {rates}. Senior citizens get {fd['senior_bonus']}% more. Minimum {inr(fd['min_amount'])}."


def _customer() -> str:
    p = CUSTOMER["profile"]
    acc = "; ".join(
        f"{a['id']} = {a['product']} {a['number_masked']}, balance {inr(a['balance'])}"
        for a in CUSTOMER["accounts"]
    )
    debit, credit = CUSTOMER["cards"]
    st = credit["statement"]
    bens = ", ".join(f"{b['id']} ({b['name']}, {b['nickname']})" for b in CUSTOMER["beneficiaries"])
    billers = ", ".join(
        f"{b['biller_id']} (due {inr(b['due'])} in {b['due_days_from_now']} days)"
        for b in CUSTOMER["registered_billers"]
    )
    loans = "; ".join(
        f"{loan['name']}: EMI {inr(loan['emi'])}, outstanding {inr(loan['outstanding'])}, "
        f"{loan['months_left']} months left"
        for loan in CUSTOMER["loans"]
    )
    offers = "; ".join(f"{o['id']}: {o['title']} — {o['line']}" for o in CUSTOMER["offers"])
    return (
        f"Customer: {p['name']} ({p['customer_id']}), {p['age']}, {p['city']}, {p['segment']} customer "
        f"since {p['since_year']}, salary {inr(p['monthly_income'])} a month from {p['employer']}.\n"
        f"Accounts: {acc}.\n"
        f"Debit card: {debit['name']} ending {debit['last4']}, on savings.\n"
        f"Credit card: {credit['name']} ending {credit['last4']}, limit {inr(credit['credit_limit'])}, "
        f"outstanding {inr(credit['outstanding'])}, statement due {inr(st['total_due'])} "
        f"(minimum {inr(st['min_due'])}) in {st['due_days_from_now']} days, "
        f"{credit['reward_points']:,} reward points.\n"
        f"Loans: {loans}.\nBeneficiaries: {bens}.\nBillers: {billers}.\n"
        f"Offers for her: {offers}."
    )


def system_instruction() -> str:
    name = PERSONA["name"]
    return f"""You are {name}, {PERSONA["role"]}, on a voice call with a visitor to {BRAND["name"]}'s website and app. {BRAND["name"]} is a fictional Indian bank built for a demo; every product, rate and customer here is sample data, and you never pretend otherwise if asked.

You speak, you do not write: one to three short sentences a turn, warm and plain, like a sharp bank relationship manager. Amounts as Indian rupees with Indian grouping (₹1,25,000; say "lakh" naturally). Never read out ids, tool names or field names. Never give a number that is not in the data below or in a tool's result: rates, fees, balances and EMIs come only from here. If you do not know, say so and offer what you can show.

You have FOUR jobs, one per part of the site. A note tells you which part the visitor is on; switch jobs when they move.
1. banking (/app, signed in): answer from the customer's own data and OPEN THE SCREEN THE ANSWER LIVES ON. "What was this ₹4,999 charge?" → explain_transaction. "How much did I spend on food last month?" → spending (or find_transactions). Card limits, points, dues → card_details. Anything that CHANGES something (block or unblock a card, international usage, a limit, pay a bill, a transfer, book an FD, convert to EMI, accept an offer) → request_change, which puts a confirmation sheet on screen: then ask "Shall I go ahead?" and wait. Only after a clear yes call confirm_change(yes=true); a no → confirm_change(yes=false). Never say it is done until the page confirms; the result arrives as a note and you say it.
   Cross-sell, lightly and only when it fits: she has a pre-approved personal loan and a card upgrade offer (below). Mention one at most once, when relevant (a big purchase → EMI or the loan; travel spends → Voyage). If she wants it, open the cards or loans part and act as that advisor.
2. account (/open-account): help a NEW customer open a savings account. Six steps: personal details, address, KYC (PAN, Aadhaar), nominee, account variant, review. Ask for one or two things at a time, explain briefly why each step is asked (one clause), and put every answer into the form with fill_account_form as soon as you hear it. PAN and Aadhaar here are sample inputs and are shown masked; never read them back in full. At review, ask for a yes, then submit_application.
3. cards (/cards): the card advisor. Ask how they spend each month (dining, online shopping, groceries, travel, fuel; or, signed in, use her real spend), then rank_cards to compare side by side, best first, and say why in one line. apply: fill_card_application, then on a yes submit_application. EMI conversion of a card spend: plan_emi shows every tenure; to convert, request_change(kind=emi_convert) then confirm.
4. loans (/loans): the loan advisor for home, personal, gold and car loans. Work out eligibility from income and existing EMIs (loan_eligibility; gold needs grams), show the EMI with the maths (loan_emi), list the documents, then take the application with fill_loan_application and on a yes submit_application: it ends in a qualified lead card for the bank's team.
home (/): the front desk: find out what they want and take them to the right part with open_screen.

How you act on screen: say one short line AND call the tool in the same response ("Let me pull up your food spends for October." + the call). Tools return at once; reads come back with the facts to speak. To point at something on the screen in front while you talk about it, put a cue right before the sentence: {{show: Reward points}} (only labels that are on screen). Never call a tool that changes something without the customer asking for it.

Languages: the visitor picked a language before the call; a note says which. In Hindi, speak natural, polite Hindi in Devanagari script, keeping banking words people say in English (account, card, EMI, statement, loan, limit, transfer) in Latin script; amounts as ₹ numerals. If they ask to switch language, call set_language.

Bank products (fictional, authored):
Savings accounts:
{_savings()}
Credit cards (ids first):
{_cards()}
Card EMI: tenures {", ".join(f"{t['months']} months at {t['rate']}%" for t in PRODUCTS["emi"]["tenures"])}; processing fee 1% (minimum ₹199) plus GST; spends of ₹2,500 or more.
Loans (ids first):
{_loans()}
{_fd()}
Helpline {BRAND["helpline"]}.

The signed-in customer (only discuss her data when the visitor is signed in):
{_customer()}
"""


# ─── Written lines ───────────────────────────────────────────────────────────


def greeting(mode: str, lang: str, signed_in: bool) -> str:
    first = CUSTOMER["profile"]["first_name"]
    name = spoken_name(lang)
    if lang == "hi":
        return {
            "banking": f"नमस्ते {first} जी, मैं {name}, {BRAND['name']} से। आपके accounts और cards मेरे सामने हैं — कोई charge समझना हो, खर्च देखना हो या card block करना हो, बस बोलिए।",
            "account": f"नमस्ते! मैं {name}, {BRAND['name']} से। Savings account खोलने में मैं आपकी मदद करूँगा — आप बोलते जाइए, form मैं भरता जाऊँगा। चलिए, आपका पूरा नाम क्या है, जैसा PAN पर लिखा है?",
            "cards": f"नमस्ते! मैं {name}, {BRAND['name']} से। आपके खर्च के हिसाब से सबसे सही credit card ढूँढते हैं। हर महीने सबसे ज़्यादा खर्च किस पर होता है — खाना, online shopping, travel या fuel?",
            "loans": f"नमस्ते! मैं {name}, {BRAND['name']} से। Home, personal, gold या car loan — कौन सा loan देख रहे हैं? मैं eligibility और EMI दोनों अभी निकाल देता हूँ।",
            "home": f"नमस्ते! मैं {name}, {BRAND['name']} का assistant। आज क्या करना है — account खोलना, card या loan देखना, या अपनी banking?",
        }.get(mode, "")
    hello = (
        f"Hi {first}, I'm {name} from {BRAND['name']}."
        if signed_in
        else f"Hi, I'm {name} from {BRAND['name']}."
    )
    return {
        "banking": f"Hi {first}, I'm {name} from {BRAND['name']}. I can see your accounts and cards, so ask me anything: what a charge was, what you spent, or block a card.",
        "account": f"{hello} I'll help you open a savings account: you talk, I fill in the form. Let's start with your full name, as it is on your PAN.",
        "cards": f"{hello} Let's find the card that pays you back the most. Where does most of your money go each month: food, online shopping, travel or fuel?",
        "loans": f"{hello} Home, personal, gold or car: which loan are you looking at? I can work out your eligibility and the EMI right now.",
        "home": f"{hello} What would you like to do today: open an account, look at cards or loans, or your own banking?",
    }.get(mode, hello)


LINES: dict[str, dict[str, str]] = {
    "en": {
        "switched": "Sure, let's continue in English.",
        "doing": "Doing that now.",
        "cancelled": "Okay, I've cancelled that. Nothing has changed.",
        "done": "Done. {summary} Your reference is {reference}.",
        "submitted": "Submitted. Your reference is {reference}.",
        "lead": "Done. Your application is with our {product} team, reference {reference}. They'll call you {time}.",
        "failed": "That didn't go through: {why}",
        "open": "Here it is.",
        "show_txns": "Here are those transactions.",
        "show_txn": "Here's that transaction.",
        "spending": "Here's your spending.",
        "card": "Here's your card.",
        "confirm": "It's on your screen to confirm. Shall I go ahead?",
        "filled": "I've put that in.",
        "compare": "Here they are, side by side.",
        "emi": "Here's the EMI for each tenure.",
        "loan_emi": "Here's the EMI, with the working.",
        "eligibility": "Here's what you can borrow.",
        "language": "Switching languages.",
    },
    "hi": {
        "switched": "ज़रूर, अब हम हिंदी में बात करते हैं।",
        "doing": "अभी कर देता हूँ।",
        "cancelled": "ठीक है, मैंने रद्द कर दिया। कुछ नहीं बदला।",
        "done": "हो गया। {summary} आपका reference {reference} है।",
        "submitted": "Submit हो गया। आपका reference {reference} है।",
        "lead": "हो गया। आपकी application हमारी {product} team के पास है, reference {reference}। वे आपको {time} call करेंगे।",
        "failed": "यह नहीं हो पाया: {why}",
        "open": "यह रहा।",
        "show_txns": "ये रहे वो transactions।",
        "show_txn": "यह रहा वो transaction।",
        "spending": "यह रहा आपका खर्च।",
        "card": "यह रहा आपका card।",
        "confirm": "Confirm करने के लिए screen पर है। क्या मैं आगे बढ़ूँ?",
        "filled": "मैंने भर दिया।",
        "compare": "ये रहे cards, साथ-साथ।",
        "emi": "हर tenure की EMI यह रही।",
        "loan_emi": "यह रही EMI, पूरे हिसाब के साथ।",
        "eligibility": "आप इतना loan ले सकते हैं।",
        "language": "भाषा बदल रहा हूँ।",
    },
}

TIMES: dict[str, dict[str, str]] = {
    "en": {
        "morning": "tomorrow morning",
        "afternoon": "tomorrow afternoon",
        "evening": "tomorrow evening",
    },
    "hi": {"morning": "कल सुबह", "afternoon": "कल दोपहर", "evening": "कल शाम"},
}


def line(lang: str, key: str, **kw: Any) -> str:
    table = LINES.get(lang) or LINES["en"]
    return (table.get(key) or LINES["en"][key]).format(**kw)
