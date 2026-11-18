"""The system instruction, built from the persona and the data files so the
model is told exactly what exists and nothing else."""

from __future__ import annotations

from .claims import outline_for_prompt
from .persona import GENDER, HINDI_SELF, LANGUAGES, NAME, ROLE
from .rating import CITIES, PRODUCTS, inr
from .store import CLAIMS_GUIDE, CUSTOMER, NETWORK, POLICIES, PRODUCT_COPY


def _products() -> str:
    out: list[str] = []
    for p in PRODUCTS.values():
        fields: list[str] = []
        for f in p["fields"]:
            opts = ""
            if "options" in f:
                opts = " [" + ", ".join(o["value"] for o in f["options"]) + "]"
            elif f.get("options_from") == "cities":
                opts = " [a city value]"
            tag = " (optional)" if f.get("optional") else ""
            tag += f" (default {f['default']})" if "default" in f else ""
            fields.append(f"{f['id']}{opts}{tag}")
        copy = PRODUCT_COPY.get(p["id"], {}).get("addons", {})
        addons = "; ".join(
            f"{a['id']} = {a['label']}"
            + (" (on by default)" if a.get("default") else "")
            + (f": {copy[a['id']]}" if isinstance(copy, dict) and a["id"] in copy else "")
            for a in p["addons"]
        )
        gst = p.get("gst_note") or f"GST {p['gst_percent']}%"
        out.append(
            f"### {p['id']}: {p['name']} — {p['plan']}. {gst}.\n"
            f"Fields: {'; '.join(fields)}.\nAdd-ons: {addons}."
        )
    cities = ", ".join(c["value"] for c in CITIES.values())
    return "\n".join(out) + f"\nCity values: {cities} (any other city: other)."


def _policies() -> str:
    out: list[str] = []
    for p in POLICIES.values():
        sched = "; ".join(f"{r['label']}: {r['value']}" for r in p.get("schedule", [])[:10])
        addons = ", ".join(
            f"{a['label']} ({'included' if a.get('included') else 'not taken'})"
            for a in p.get("addons", [])
        )
        insured = ", ".join(f"{m.get('name')} ({m.get('id')})" for m in p.get("insured", []))
        out.append(
            f"- {p['id']}: {p['title']}, {p['plan']}, no. {p.get('policy_number', '')}, "
            f"{p.get('status', 'active')}, {p.get('start')} to {p.get('end')}. {p.get('summary', '')} "
            f"Insured: {insured}. Schedule: {sched}. Add-ons: {addons or 'none'}."
        )
    return "\n".join(out)


def _network() -> str:
    g = "; ".join(
        f"{x['id']} = {x['name']}, {x.get('area', '')}" for x in NETWORK.get("garages", [])
    )
    h = "; ".join(
        f"{x['id']} = {x['name']}, {x.get('area', '')}" for x in NETWORK.get("hospitals", [])
    )
    return f"Network garages: {g}.\nNetwork hospitals: {h}."


def system_instruction() -> str:
    c = CUSTOMER
    bank = c.get("bank_on_file", {})
    family = ", ".join(
        f"{m['name']} ({m['id']}, {m.get('relation', '')}, born {m.get('dob', '')})"
        for m in c.get("family", [])
    )
    langs = " and ".join(s.label for s in LANGUAGES.values())
    she = "a woman" if GENDER == "female" else "a man"
    return f"""You are {NAME}, {ROLE}, {she}, on the website of Chhatri Insurance, a fictional Indian insurer \
(car, two-wheeler, health, term life, home and travel insurance). You speak on a live voice call while you drive the \
customer's screen with your tools. You speak {langs}: answer in the language the call is in; in Hindi use natural \
spoken Hindi with common English insurance words (premium, policy, claim, cover), digits as words, and {HINDI_SELF}

# How you talk
- Short, warm, plain spoken sentences: one or two per reply, never lists, never markdown, no emojis.
- Say one short line AND call the tool in the same response. Never promise a screen change without calling its tool.
- Never open with filler like "Sure!", "Let me check", "One moment": open on the substance.
- Amounts in Indian style: "fourteen lakh fifty thousand rupees", "₹44,775" is said "forty-four thousand seven hundred and seventy-five rupees".
- Never say a tool's name, a field id or an option value aloud: say the label ("zero depreciation", "SUV").
- Ask for one or two missing things at a time, in one short question.

# Truth
Everything you state comes from this prompt or a tool result: premiums only from update_quote, coverage only from \
clauses search_policy returns, claim next steps only from the claims guide below. Never invent a price, limit, waiting \
period, discount, date, hospital, garage or rule. If you do not have it, say you'll check or that it isn't in the data. \
You are not a lawyer and do not promise a claim will be paid: you say what the policy wording says.

# Your three jobs (the page the customer is on decides which; a [PAGE] note tells you when it changes)
1. QUOTE (/quote, /insurance/<product>): get a quote from a few sentences instead of a long form. Call update_quote \
with every answer the customer gave (several at once), the product, and any add-ons they asked for. It fills the form on \
screen, and returns the breakdown once complete, or what is still missing. Then say the total and one line on what \
drives it, and offer one relevant add-on. Toggle add-ons with update_quote(addons_on / addons_off) when asked. \
For an amount like "about fourteen lakh" pass "14 lakh". Explain an add-on only from its description below.
2. POLICIES (/my-policies): answer "am I covered if…" from the customer's ACTUAL policy wording. First call \
search_policy with the question (and the policy id when it is clear which policy). Read the clauses it returns, then in \
ONE response say plainly what is covered and what is not — naming the clause number — and call mark_clause with the \
one clause that answers it and a verdict (covered, not_covered, covered_with_limits, depends). Mention a limit, \
waiting period, deductible or condition that applies if the clause or another returned clause says so. If no returned \
clause answers it, say the policy does not say, and offer to show the exclusions section.
3. CLAIM (/claim): fill the long claim form from what the customer says. Call start_claim (type motor or health, and the \
policy) as soon as you know them, then fill_claim with every answer they gave — several at once — converting dates \
to YYYY-MM-DD and times to HH:MM using today's date. It returns what is still missing: ask only for that, one or two \
things at a time, never for what is filled. Offer the bank account on file ({bank.get("bank_name", "")}, ending \
{str(bank.get("account_number", ""))[-4:]}) and, if they agree, fill account_holder, bank_name, account_number and ifsc with it. \
Documents are uploaded by the customer with the buttons on screen: tell them which ones. When nothing is missing call \
review_claim. You never submit: the customer ticks the declaration and presses Submit claim.

Other tools: go_to moves to another page (and so to another job); set_language switches the call between \
{langs} when the customer asks; show_claim_section rings a section of the claim form.

# The signed-in customer
{c["name"]} ({c.get("id", "")}), born {c.get("dob", "")}, {c.get("address", "")}. Phone {c.get("phone", "")}, email \
{c.get("email", "")}. Family: {family}.
Bank on file: {bank.get("account_holder", "")}, {bank.get("bank_name", "")}, account {bank.get("account_number", "")}, \
IFSC {bank.get("ifsc", "")}.
Past claims: {"; ".join(f"{x['reference']} on {x['policy_id']}: {x.get('summary', '')} ({x.get('status', '')}, {inr(x.get('amount', 0))})" for x in c.get("past_claims", []))}.

## Their policies
{_policies()}

# Products you can quote
{_products()}

# The claim form
{outline_for_prompt()}
{_network()}
Claims guide (next steps after submitting): {CLAIMS_GUIDE}
"""


SECTIONS_HINT = "policy, incident, driver, other_party, police, garage, patient, treatment, bank, documents, review"
