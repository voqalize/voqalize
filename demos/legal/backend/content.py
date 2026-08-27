"""Contract content for the Docket contract-review demo.

Fictional matter: in-house counsel at Acme Robotics, Inc. (a US manufacturer)
reviewing a Master Services Agreement with a SaaS vendor, Nimbus Cloud
Systems, Inc., before signing. Delaware governing law, CCPA/CPRA data
handling, AAA arbitration — ordinary US commercial-contract furniture, not
tied to any real company.

``CLAUSES`` is the single source of truth for clause text; the frontend's
``content.ts`` mirrors it by hand. ``PLAYBOOK`` gives the brain a few named
negotiating-position rules to check the contract against — the Limitation of
Liability clause is scripted to fail one of them (capped too low, no
carve-outs) so the demo has something substantive to catch.
"""

from __future__ import annotations

from typing import Literal, get_args

MATTER = {
    "client": "Acme Robotics, Inc.",
    "counterparty": "Nimbus Cloud Systems, Inc.",
    "document_title": "Master Services Agreement",
    "governing_law": "Delaware",
}

CLAUSES: list[dict[str, str]] = [
    {
        "id": "c1",
        "number": "1",
        "heading": "Services",
        "text": (
            "Nimbus Cloud Systems, Inc. (“Vendor”) shall provide Acme Robotics, "
            "Inc. (“Customer”) with access to Vendor's fleet-telemetry cloud "
            "platform (the “Services”) as described in each Order Form, including "
            "hosting, data ingestion, and analytics dashboards for Customer's robotics "
            "fleet. Vendor shall perform the Services in a professional and workmanlike "
            "manner consistent with generally accepted industry standards."
        ),
    },
    {
        "id": "c2",
        "number": "2",
        "heading": "Term & Termination",
        "text": (
            "This Agreement commences on the Effective Date and continues for an "
            "initial term of thirty-six (36) months, automatically renewing for "
            "successive twelve (12) month terms unless either party gives ninety (90) "
            "days' written notice of non-renewal. Either party may terminate for the "
            "other party's uncured material breach following thirty (30) days' written "
            "notice. Customer may terminate for convenience upon one hundred eighty "
            "(180) days' written notice, subject to payment of a wind-down fee equal to "
            "twenty-five percent (25%) of the remaining committed contract value."
        ),
    },
    {
        "id": "c3",
        "number": "3",
        "heading": "Fees & Payment",
        "text": (
            "Customer shall pay the fees set forth in each Order Form within thirty "
            "(30) days of invoice. Fees are non-refundable except as expressly stated "
            "herein. Vendor may increase fees upon renewal by no more than five percent "
            "(5%) annually over the prior term's fees, with sixty (60) days' advance "
            "notice. Late payments accrue interest at one and one-half percent (1.5%) "
            "per month or the maximum rate permitted by law, whichever is lower."
        ),
    },
    {
        "id": "c4",
        "number": "4",
        "heading": "Confidentiality",
        "text": (
            "Each party shall protect the other's Confidential Information using at "
            "least the same degree of care it uses for its own confidential "
            "information of similar importance, and in no event less than reasonable "
            "care. Confidentiality obligations survive termination for a period of "
            "five (5) years, except with respect to trade secrets, which shall be "
            "protected for as long as the information retains trade secret status "
            "under applicable law."
        ),
    },
    {
        "id": "c5",
        "number": "5",
        "heading": "Data Protection",
        "text": (
            "Vendor shall process Customer Personal Information solely as necessary to "
            "provide the Services and in accordance with the California Consumer "
            "Privacy Act, as amended by the California Privacy Rights Act (CCPA/CPRA), "
            "and other applicable US data-protection law. Vendor shall implement "
            "commercially reasonable administrative, technical, and physical safeguards "
            "designed to protect Customer Personal Information. Vendor shall notify "
            "Customer of a confirmed data breach affecting Customer Personal "
            "Information without undue delay, and in no event later than seventy-two "
            "(72) hours after Vendor becomes aware of the breach."
        ),
    },
    {
        "id": "c6",
        "number": "6",
        "heading": "Intellectual Property",
        "text": (
            "As between the parties, Customer retains all right, title, and interest "
            "in Customer Data and Customer's pre-existing intellectual property. "
            "Vendor retains all right, title, and interest in the Services, the "
            "underlying platform, and any general learnings, provided such learnings "
            "do not include and cannot be used to reconstruct Customer Data. Vendor "
            "grants Customer a non-exclusive, non-transferable license to use the "
            "Services during the term solely for Customer's internal business "
            "purposes."
        ),
    },
    {
        "id": "c7",
        "number": "7",
        "heading": "Indemnification",
        "text": (
            "Vendor shall defend, indemnify, and hold harmless Customer against any "
            "third-party claim alleging that the Services infringe a US patent, "
            "copyright, or trade secret, and shall indemnify Customer for breaches of "
            "Vendor's confidentiality and data-protection obligations under Sections 4 "
            "and 5. Customer shall indemnify Vendor against third-party claims arising "
            "from Customer's misuse of the Services in violation of this Agreement."
        ),
    },
    {
        "id": "c8",
        "number": "8",
        "heading": "Limitation of Liability",
        "text": (
            "EXCEPT FOR A PARTY'S INDEMNIFICATION OBLIGATIONS UNDER SECTION 7, NEITHER "
            "PARTY SHALL BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, "
            "CONSEQUENTIAL, OR PUNITIVE DAMAGES. EACH PARTY'S TOTAL AGGREGATE LIABILITY "
            "ARISING OUT OF OR RELATED TO THIS AGREEMENT SHALL NOT EXCEED TWO HUNDRED "
            "FIFTY THOUSAND DOLLARS ($250,000), REGARDLESS OF THE THEORY OF LIABILITY, "
            "AND REGARDLESS OF WHETHER EITHER PARTY HAS BEEN ADVISED OF THE POSSIBILITY "
            "OF SUCH DAMAGES."
        ),
    },
    {
        "id": "c9",
        "number": "9",
        "heading": "Insurance",
        "text": (
            "Vendor shall maintain, at its own expense, commercial general liability "
            "insurance with limits of not less than $2,000,000 per occurrence, "
            "technology errors and omissions insurance with limits of not less than "
            "$3,000,000 per claim, and cyber liability insurance with limits of not "
            "less than $3,000,000 per claim, and shall provide Customer with "
            "certificates of insurance upon request."
        ),
    },
    {
        "id": "c10",
        "number": "10",
        "heading": "Governing Law & Dispute Resolution",
        "text": (
            "This Agreement shall be governed by the laws of the State of Delaware, "
            "without regard to its conflict-of-laws principles. Any dispute arising "
            "out of or relating to this Agreement shall be resolved by binding "
            "arbitration administered by the American Arbitration Association (AAA) "
            "under its Commercial Arbitration Rules, seated in Wilmington, Delaware, "
            "before a single arbitrator. Either party may seek injunctive relief in a "
            "court of competent jurisdiction to protect its intellectual property or "
            "Confidential Information."
        ),
    },
]

CLAUSES_BY_ID: dict[str, dict[str, str]] = {c["id"]: c for c in CLAUSES}

#: The clause ids, as a type. A tool that takes a `ClauseId` cannot be handed one
#: that is not in the document, so nothing downstream has to check.
ClauseId = Literal["c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8", "c9", "c10"]

assert set(get_args(ClauseId)) == set(CLAUSES_BY_ID), "ClauseId has drifted from CLAUSES"

# The "data room" this matter sits in — other documents attached to the same
# deal, plus an external record. Only metadata (name + description), no full
# text: grounds cross-document asks ("pull every liability cap across the
# data room", "check counterparty's litigation history") without
# requiring a second full contract to be authored. Second act of the demo:
# the lawyer works the matter broadly, not just this one document.
DATA_ROOM: list[dict[str, str]] = [
    {
        "id": "d1",
        "name": "Nimbus MSA — this draft",
        "description": "The Master Services Agreement currently under review.",
    },
    {
        "id": "d2",
        "name": "Nimbus MSA — Order Form No. 1",
        "description": "Initial order form: fleet-telemetry platform scope, fees, and term.",
    },
    {
        "id": "d3",
        "name": "Nimbus DPA Amendment (2024)",
        "description": "Prior data-processing addendum amendment already on file for this vendor.",
    },
    {
        "id": "d4",
        "name": "Nimbus litigation & background search",
        "description": "External docket/records search on Nimbus Cloud Systems, Inc. and its principals.",
    },
]

# A second named prior deal (distinct from the run_diligence `precedent`
# kind's usual anchor) for the comparison-memo angle — gives the model two
# concrete comps to actually compare termination rights against.
PRIOR_DEALS: list[dict[str, str]] = [
    {
        "name": "TerraLogix DataWorks MSA (closed Q3 2025)",
        "termination_terms": (
            "180-day termination-for-convenience notice, 15% wind-down fee, "
            "30-day cure period for material breach."
        ),
    },
    {
        "name": "Meridian Robotics MSA (closed Q4 2025)",
        "termination_terms": (
            "120-day termination-for-convenience notice, no wind-down fee, "
            "45-day cure period for material breach."
        ),
    },
]

# Named negotiating-position rules Acme Robotics' legal team checks vendor
# paper against. Only the liability-cap rule is scripted to fail in this
# document — everything else in the MSA is drafted to pass, so the agent has
# one substantive, specific issue to catch rather than a wall of nitpicks.
PLAYBOOK: dict[str, dict[str, str]] = {
    "liability_cap_floor": {
        "clause_id": "c8",
        "rule": (
            "Aggregate liability cap must be no lower than $2,000,000 (or 12 months' "
            "fees, whichever is greater), and the cap must not apply to breaches of "
            "confidentiality or data-protection obligations, which should be "
            "uncapped or capped separately at a materially higher amount."
        ),
        "status": "fails",
        "why": (
            "Section 8 caps aggregate liability at a flat $250,000 with no "
            "carve-out for confidentiality or data-protection breaches — well below "
            "the $2,000,000 floor, and it would cap Vendor's exposure for a data "
            "breach at the same $250,000, which does not match the risk (Customer "
            "fleet telemetry plus any Personal Information Vendor processes)."
        ),
        "proposed_text": (
            "EXCEPT FOR A PARTY'S INDEMNIFICATION OBLIGATIONS UNDER SECTION 7 AND "
            "EITHER PARTY'S BREACH OF ITS CONFIDENTIALITY OR DATA PROTECTION "
            "OBLIGATIONS UNDER SECTIONS 4 AND 5 (WHICH SHALL BE UNCAPPED), NEITHER "
            "PARTY SHALL BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, "
            "CONSEQUENTIAL, OR PUNITIVE DAMAGES. EACH PARTY'S TOTAL AGGREGATE "
            "LIABILITY ARISING OUT OF OR RELATED TO THIS AGREEMENT SHALL NOT EXCEED "
            "THE GREATER OF TWO MILLION DOLLARS ($2,000,000) OR THE FEES PAID OR "
            "PAYABLE IN THE TWELVE (12) MONTHS PRECEDING THE CLAIM."
        ),
    },
    "termination_for_convenience": {
        "clause_id": "c2",
        "rule": "Customer must retain a termination-for-convenience right without an excessive wind-down penalty.",
        "status": "passes",
        "why": "Section 2 grants a 180-day termination-for-convenience right; the 25% wind-down fee is within Acme's tolerance.",
        "proposed_text": "",
    },
    "data_breach_notice_window": {
        "clause_id": "c5",
        "rule": "Vendor must notify Customer of a confirmed data breach within 72 hours.",
        "status": "passes",
        "why": "Section 5 commits to 72-hour breach notification, matching Acme's standard.",
        "proposed_text": "",
    },
}
