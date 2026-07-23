"""ServicingBrain — the Meridian Servicing Console copilot.

A ``voqalize.sdk.Brain`` (LLM + case/board screen-driving tools + per-session
workspace state). Voqalize dials this brain's WebSocket per session; ``respond``
(inherited from :class:`GeminiBrain`) runs the manual Gemini function-calling loop
where **each LLM call is one ``interaction.inference()`` bracket** (1:1 with the
wire): speak a short line, call a tool, feed the result back.

The user here is a bank ADVISOR working a mortgage-case queue, not a customer.
The assistant is the servicing desk — a colleague who works alongside the advisor
by voice while driving the screen. Like the travel brain, **the LLM generates the
substantive data** (payoff figures, rate offers, draft lines, packet fields) and
passes it as nested function-call arguments; the Python handlers are thin
pass-throughs that normalize ids, forward to the UI via
``interaction.action(...)`` (the RTVI ``ui_command`` the ``/servicing`` UI
renders), and ack the model.

The browser echoes a compact workspace snapshot back via ``state_sync``
(delivered to :meth:`on_app_event`). We keep the latest snapshot so the assistant
always knows the live on-screen state — surfaced two ways: the
``get_advisor_context`` tool reads it on demand, and each turn's working context
is grounded with it (folding every ``state_sync`` into the LLM context silently,
no inference).

The LLM is **dependency-injected** as a :class:`GeminiProvider`; the brain owns
only the prompt, the tool schemas, and this session's advisor + workspace state.
The conversation record is framework-owned (``interaction.conversation``),
rebuilt into Gemini's working context each turn by the :class:`GeminiBrain` base.
"""

from __future__ import annotations

import json
from typing import Any

from google.genai import types
from loguru import logger
from voqalize_demos import DEFAULT_MODEL, GeminiBrain, GeminiProvider

DESK_NAME = "Servicing Desk"
BANK_NAME = "Meridian Home Loans"

# Routable department queues (mirror frontend src/servicing/data.ts).
DEPARTMENTS = {
    "pricing": "Pricing",
    "closures": "Closures & Payoffs",
    "legal": "Legal & Custody",
    "insurance": "Insurance & Escrow",
    "compliance": "Compliance",
}

STAGES = ["new", "in_progress", "needs_approval", "with_dept", "done"]


# ─── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_INSTRUCTION = f"""You are the {BANK_NAME} {DESK_NAME} — a voice copilot for a mortgage-servicing ADVISOR working their case queue on an internal bank console. The advisor is your colleague, not a customer. You help them move faster, and YOU DRIVE THEIR SCREEN as you talk.

WHO YOU SERVE:
- You are assisting one specific, logged-in advisor. You will be told their name. Greet them by name and address them as a peer. Everything you do is "for them" / "on their queue".

VOICE STYLE:
- English only. Short, efficient, professional sentences — this is a busy professional, not a consumer. One question or one confirmation per turn, at most 2-3 sentences. No markdown, lists, or symbols. Say "dollars" not the symbol; say figures naturally (e.g. "two hundred eighty-four thousand, nine hundred").

YOU CONTROL THE SCREEN. Whenever you talk about a case, a tab, an assignment, or a draft, call the matching tool so the advisor SEES it. Open the case, switch the tab, move the card, draft the item — never just describe it in words.

KNOW WHERE THE ADVISOR IS ("voice also"). The console continuously tells you the current on-screen state. Before you reference what is on screen, you may call get_advisor_context to confirm exactly which case and tab the advisor is looking at, and ground your answer in it (e.g. "I see you're on Cho's pricing tab — his rate is seven-point-one percent"). Voice augments the screen; it does not replace it.

THE BIG IDEA — WORKING ONE CASE DOESN'T FREEZE THE OTHERS. The advisor can keep working a case on screen while you PREPARE A DIFFERENT CASE in the background. When the advisor asks you to "get a case ready" / "take" / "work on" / "work up" another case, call prepare_case for that case. That kicks off background prep jobs that run on their own while the advisor keeps clicking and talking on whatever they have open. Do NOT pull the advisor away from what they're doing — prepare the other case quietly and tell them when it's ready. They are never blocked.

THE WORKUP IS YOUR REAL VALUE — DO THE LEGWORK, DON'T JUST CLICK. The advisor's time goes into ASSEMBLING a case across systems and RECONCILING figures before they can act, and into spotting the one thing that's wrong. That is what you do for them:
- ASSEMBLE & RECONCILE: produce findings — the cross-system facts and reconciled figures (payoff, accrued interest, escrow refund, in-flight payments). Where you reconciled something the advisor would likely have missed (a payment that posted but wasn't applied yet, a fee they'd forget), flag it 'warn' and say it out loud.
- CATCH THE BLOCKER: look for the one risk that would cause a costly mistake — the thing they wouldn't know to look for. If you find it, pass it as the blocker and tell them plainly. This is the difference between you and a faster mouse: you surface what they forgot to check. If a regulated step (like releasing a title) is gated by it, mark the matching draft/packet section blocked so they CANNOT approve it until it's cleared, and suggest the department that clears it.
- For a background case, pass findings/blocker/packet inside prepare_case (they appear when prep finishes). For the case the advisor has OPEN ON SCREEN, use post_workup to show your findings/blocker immediately.

PACKETS (regulated multi-step forms). Some cases need a packet filled — e.g. an early-closure packet (payoff figures, document release, escrow disposition). FILL IT from your workup and pass it (in prepare_case, or build it as part of the workup). Voice is for STEERING, not dictation: you fill ~all of it; the advisor adjusts a field by voice ('set the payoff date to month-end' → update_packet_field, and you regenerate any dependent figure). The packet is SUBMITTED via submit_packet — a server-side action that only goes through after the advisor approves the drafts and any blocker is cleared. Never imply it's submitted until then.

PRECEDENT (reach beyond the screen). When the advisor asks 'have we handled this before?' / 'how did we deal with X?', call lookup_precedent — a server-side archive search over PAST cases not in their queue. Generate 2-3 believable past cases with how each was resolved, then summarize the most useful one. This is institutional memory they couldn't get by clicking.

YOU GENERATE THE DATA. There is no live core-banking system in this demo. Generate realistic, internally-consistent figures yourself and pass them as tool arguments:
- Payoff / settlement figures: a sensible payoff close to the balance, plus accrued interest and any early-closure charge.
- Rate offers: a plausible retention rate below the current rate, the new monthly payment, and the monthly/lifetime saving. Reconcile the TRUE net saving after any fees.
- Keep numbers consistent with the case state you were given (balance, current rate, monthly payment, tenure).

MAKER-CHECKER — YOU DRAFT, THE ADVISOR APPROVES. Regulation owns each case's workflow; you NEVER execute a regulated step and you NEVER claim something is "done", "sent", or "released". You DRAFT items into the advisor's "Needs your approval" queue (settlement letters, fee waivers, rate offers, document-release authorizations) and they approve them. Always speak in maker-checker terms: "I've drafted...", "it's waiting for your approval", "once you approve it". When a concession is involved (waiving a fee), make a brief recommendation with a reason, but it is the advisor's call.
- For a case you are co-working on screen with the advisor, use draft_approval to drop a single draft immediately.
- For a case you are preparing in the background, pass the resulting drafts inside prepare_case so they appear when the prep finishes.

ROUTING (Jira-style board). Every case is a ticket with a stage and an assignee. When the advisor says "assign it to <person>" or "send it to <department>", call assign_case. Departments are: Pricing, Closures & Payoffs, Legal & Custody, Insurance & Escrow, Compliance. Use move_case to move a card across stages (new, in progress, needs approval, with department, done) when that helps. Routing is a normal action — it is not a regulated approval.

NOTES (handoff context). A case carries free-text notes — the human context that doesn't fit a field. When the advisor says "make a note…", "add a comment…", or whenever you ROUTE a case to another department, call add_comment to capture WHY in a sentence or two so the receiving desk has the context (e.g. routing Whitmore's closure to Legal: note that there's an open 2021 home-equity line to subordinate before the title can be released). Pass the relevant department in 'dept'. Notes are not approvals — they're context; keep them short and factual. When you add a note, tell the advisor briefly that you've noted it.

THE TWO LIVE CASES IN THE ADVISOR'S QUEUE:
- MS-1042 — Daniel Cho — a rate-reduction request. Usually the case the advisor works ON SCREEN with you. He is on a higher rate (around 7.1%) and eligible for a retention offer. Do the workup with post_workup: reconcile the TRUE net saving after fees (e.g. about 1,400 dollars in re-pricing fees the advisor would have forgotten — flag it 'warn'), and confirm eligibility/timing (e.g. a forbearance plan that recently ended, so re-pricing is fine NOW but wouldn't have been a couple of weeks ago — flag it 'info' or 'warn'). Then draft the retention rate offer for approval.
- MS-1057 — Eleanor Whitmore — an early loan closure. A long-tenure (12-year) customer who wants to pay off her loan and get her property documents back. The case to PREPARE IN THE BACKGROUND with a full workup. Jobs: pull the payoff figure, check the early-closure charge, confirm her property-document file. Findings: reconcile the payoff (a payment posted yesterday hasn't been applied yet, so the NET payoff is a bit lower than the ledger shows — flag 'warn'); early-closure charge ~1,200 dollars. BLOCKER (the headline): there is an OPEN SECOND LIEN on the property — a home-equity line from 2021 still open (it's sitting in her documents as a 'Second charge'). Releasing the title now would be a compliance exception — pass it as a 'block' blocker, suggested_route 'Legal & Custody'. Packet: an early-closure packet with a 'Payoff figures' section, a 'Document release' section (mark it blocked:true because of the lien), and an 'Escrow disposition' section. Drafts: settlement letter, early-closure fee waiver (recommend waiving — 12-year customer in good standing), and the document-release authorization (mark it blocked:true). Tell the advisor about the lien plainly and offer to route it to Legal. Once they confirm Legal has cleared/subordinated it, call resolve_blocker, then they can approve the release and you can submit_packet.

Open with a brief, professional greeting BY NAME, say you are the {DESK_NAME}, and ask what they want to start on. One or two short sentences."""


# ── Nested JSON-schema fragments (the LLM-generated data shapes) ───────────────

_JOB_SCHEMA = {
    "type": "object",
    "properties": {
        "label": {
            "type": "string",
            "description": "Short label of the background step, e.g. 'Pull payoff figure'.",
        },
        "detail": {
            "type": "string",
            "description": (
                "One short line of the result the step produces, e.g. 'Payoff 284,900 + "
                "1,210 accrued interest'. Shown when the step finishes."
            ),
        },
    },
    "required": ["label"],
}

_APPROVAL_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "description": "Short stable id, e.g. 'a1'."},
        "title": {
            "type": "string",
            "description": "Draft title, e.g. 'Settlement letter' or 'Early-closure fee waiver'.",
        },
        "kind": {
            "type": "string",
            "enum": [
                "settlement_letter",
                "fee_waiver",
                "rate_offer",
                "document_release",
                "escrow_change",
                "other",
            ],
            "description": "Category of the draft (drives the icon shown).",
        },
        "summary": {
            "type": "string",
            "description": "One-line summary of what the advisor is approving.",
        },
        "lines": {
            "type": "array",
            "items": {"type": "string"},
            "description": "A few short detail lines shown on the draft card (figures, terms).",
        },
        "amount": {
            "type": "number",
            "description": "Headline dollar amount if relevant (payoff total, fee waived, new payment).",
        },
        "recommendation": {
            "type": "string",
            "description": (
                "Your brief recommendation + reason for the advisor, e.g. 'Recommend waiving — "
                "12-year customer in good standing'. Empty if none."
            ),
        },
        "blocked": {
            "type": "boolean",
            "description": (
                "True if this draft CANNOT be approved yet because the workup caught a blocker "
                "(e.g. a document-release that's blocked by an open lien). It shows locked until "
                "the blocker is cleared. Default false."
            ),
        },
        "blocked_reason": {
            "type": "string",
            "description": "If blocked, one short line why, e.g. 'Open second lien must clear first'.",
        },
    },
    "required": ["title", "summary"],
}

# A line of the desk's "workup" — the cross-system assembly/reconciliation legwork.
_FINDING_SCHEMA = {
    "type": "object",
    "properties": {
        "label": {
            "type": "string",
            "description": "What was checked, e.g. 'Payoff reconciliation'.",
        },
        "value": {
            "type": "string",
            "description": "The assembled/reconciled result, e.g. 'Net payoff 286,400 (a payment posted yesterday wasn't applied)'.",
        },
        "flag": {
            "type": "string",
            "enum": ["ok", "warn", "info"],
            "description": "'warn' for a reconciliation the advisor would likely have missed; 'ok' otherwise.",
        },
    },
    "required": ["label", "value"],
}

# A risk the workup caught that gates a regulated step — the thing nav never surfaces.
_BLOCKER_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": "Short headline, e.g. 'Open second lien on the property'.",
        },
        "detail": {
            "type": "string",
            "description": "One or two lines on what it is and why it blocks, e.g. 'A 2021 home-equity line is still open — releasing the title now is a compliance exception.'",
        },
        "severity": {
            "type": "string",
            "enum": ["block", "warn"],
            "description": "'block' = a regulated step cannot proceed until cleared; 'warn' = caution only.",
        },
        "suggested_route": {
            "type": "string",
            "description": "Department to route to in order to clear it, e.g. 'Legal & Custody'.",
        },
    },
    "required": ["title", "detail", "severity"],
}

# A field/section of a regulated packet (multi-step form) the desk fills.
_PACKET_FIELD_SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "description": "Field name, e.g. 'Payoff date'."},
        "value": {
            "type": "string",
            "description": "Field value, e.g. '30 June 2026' or '286,400'.",
        },
        "mono": {"type": "boolean", "description": "True for figures/ids shown in monospace."},
    },
    "required": ["label", "value"],
}

_PACKET_SECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "description": "Short id, e.g. 'payoff', 'release', 'escrow'."},
        "title": {"type": "string", "description": "Section title, e.g. 'Payoff figures'."},
        "fields": {"type": "array", "items": _PACKET_FIELD_SCHEMA},
        "blocked": {
            "type": "boolean",
            "description": "True if this section is locked by a blocker (e.g. the document-release section while a lien is open).",
        },
        "blocked_reason": {"type": "string", "description": "If blocked, one short line why."},
    },
    "required": ["title", "fields"],
}

_PACKET_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "description": "Short id, e.g. 'closure'."},
        "title": {"type": "string", "description": "Packet title, e.g. 'Early-closure packet'."},
        "summary": {"type": "string", "description": "One line on what this packet does."},
        "sections": {
            "type": "array",
            "items": _PACKET_SECTION_SCHEMA,
            "description": "The form sections (e.g. payoff figures, document release, escrow disposition).",
        },
    },
    "required": ["title", "sections"],
}

# A past (archived) case returned by the server-side precedent search.
_PRECEDENT_SCHEMA = {
    "type": "object",
    "properties": {
        "ref": {"type": "string", "description": "Archive case reference, e.g. 'MS-0907'."},
        "customer": {"type": "string", "description": "Customer name on the past case."},
        "summary": {"type": "string", "description": "One line on what the past case was."},
        "resolution": {
            "type": "string",
            "description": "How it was handled/resolved, e.g. 'Legal subordinated the HELOC; title released after.'",
        },
        "days": {"type": "number", "description": "How many days it took to resolve, if relevant."},
    },
    "required": ["ref", "summary", "resolution"],
}


# ─── Tool schemas (JSON-schema dicts → google-genai Schema) ────────────────────

# (tool_name, description, properties, required)
_TOOLSPECS: list[tuple[str, str, dict[str, Any], list[str]]] = [
    (
        "open_board",
        "Show the advisor's case board (the worklist of all their cases).",
        {},
        [],
    ),
    (
        "open_case",
        "Open a case by its reference and make it the active case on screen. "
        "Use when the advisor says 'open Cho's case' or 'pull up MS-1057'.",
        {"ref": {"type": "string", "description": "Case reference, e.g. 'MS-1042'."}},
        ["ref"],
    ),
    (
        "set_tab",
        "Switch the tab within the open case so the advisor sees the right panel.",
        {
            "tab": {
                "type": "string",
                "enum": ["overview", "payments", "documents", "activity"],
                "description": "Which tab of the open case to show.",
            },
        },
        ["tab"],
    ),
    (
        "get_advisor_context",
        "Read where the advisor is right now — which case and tab is on screen, plus a "
        "snapshot of that case and any pending approvals. Call this to ground a turn in "
        "what the advisor is currently looking at before you reference it.",
        {},
        [],
    ),
    (
        "assign_case",
        "Route a case to a person or a department (Jira-style assignment). Use when the "
        "advisor says 'assign it to <person>' or 'send it to <department>'. Assigning to a "
        "department moves the card to the 'with department' stage.",
        {
            "ref": {"type": "string", "description": "Case reference, e.g. 'MS-1057'."},
            "assignee_kind": {
                "type": "string",
                "enum": ["person", "department"],
                "description": "Whether routing to a teammate or a department queue.",
            },
            "assignee": {
                "type": "string",
                "description": (
                    "The person's name (e.g. 'Marcus Bell') or department key: one of "
                    "pricing, closures, legal, insurance, compliance."
                ),
            },
        },
        ["ref", "assignee_kind", "assignee"],
    ),
    (
        "move_case",
        "Move a case card to a different stage on the board.",
        {
            "ref": {"type": "string", "description": "Case reference."},
            "stage": {"type": "string", "enum": STAGES, "description": "Target stage column."},
        },
        ["ref", "stage"],
    ),
    (
        "add_comment",
        "Leave an authored note on a case — handoff context the next desk needs. Use when the "
        "advisor says 'make a note that…', 'add a comment…', or when you route a case to another "
        "department and want to capture WHY so the receiving team has the context. If the note "
        "accompanies a routing, pass the department in 'dept' (it tags the note; route separately "
        "with assign_case if the case should actually move). Notes are not approvals — they are "
        "free-text context.",
        {
            "ref": {"type": "string", "description": "Case reference, e.g. 'MS-1057'."},
            "text": {
                "type": "string",
                "description": "The note text — a sentence or two of context for the case.",
            },
            "dept": {
                "type": "string",
                "description": (
                    "Optional department this note is about (one of pricing, closures, legal, "
                    "insurance, compliance). Tags the note; omit if it's a general note."
                ),
            },
        },
        ["ref", "text"],
    ),
    (
        "prepare_case",
        "Run a full WORKUP on a case IN THE BACKGROUND while the advisor stays on whatever "
        "they have open. Kicks off the listed prep jobs (which run and complete on their own) "
        "and, when they finish, reveals everything at once: your findings (the cross-system "
        "assembly + reconciliations), any blocker you caught, the regulated packet you filled, "
        "and the drafts in the 'Needs your approval' queue. Use this for a case the advisor "
        "asks you to 'get ready' / 'take' / 'work up' — never pull them off their current "
        "screen for it. This is the heavy lifting: do the legwork they'd otherwise do by hand.",
        {
            "ref": {"type": "string", "description": "Case reference to prepare, e.g. 'MS-1057'."},
            "summary": {
                "type": "string",
                "description": "One-line summary of what you're preparing for this case.",
            },
            "jobs": {
                "type": "array",
                "items": _JOB_SCHEMA,
                "description": "The background prep steps (usually 3-4). They animate to completion.",
            },
            "findings": {
                "type": "array",
                "items": _FINDING_SCHEMA,
                "description": (
                    "The workup result — the cross-system facts you assembled and figures you "
                    "reconciled (payoff, accrued interest, escrow, in-flight payments). Flag the "
                    "ones the advisor would likely have missed with 'warn'."
                ),
            },
            "blocker": {
                **_BLOCKER_SCHEMA,
                "description": (
                    "The one risk you caught that gates a regulated step — the thing the advisor "
                    "wouldn't have known to look for (e.g. an open second lien before a title "
                    "release). Omit if the case is clean."
                ),
            },
            "packet": {
                **_PACKET_SCHEMA,
                "description": (
                    "The regulated packet (multi-step form) you filled from the workup, e.g. an "
                    "early-closure packet with payoff figures, document-release, escrow sections. "
                    "Mark the section a blocker gates with blocked:true. Omit if not relevant."
                ),
            },
            "approvals": {
                "type": "array",
                "items": _APPROVAL_SCHEMA,
                "description": (
                    "The draft items to reveal for the advisor's approval once prep finishes "
                    "(settlement letter, fee waiver, document release, etc.). If a blocker gates "
                    "one (e.g. document release), set blocked:true on it."
                ),
            },
        },
        ["ref", "jobs"],
    ),
    (
        "post_workup",
        "Attach a workup to the case the advisor has OPEN ON SCREEN right now (no background "
        "animation) — the findings you assembled and any blocker you caught. Use this when you "
        "are co-working a case with the advisor and want to show your reconciliation (e.g. "
        "Cho's true net saving after fees, or an eligibility flag) immediately.",
        {
            "ref": {"type": "string", "description": "Case reference, e.g. 'MS-1042'."},
            "findings": {
                "type": "array",
                "items": _FINDING_SCHEMA,
                "description": "The facts/reconciliations you assembled for this case.",
            },
            "blocker": {
                **_BLOCKER_SCHEMA,
                "description": "A risk you caught that needs attention. Omit if the case is clean.",
            },
        },
        ["ref", "findings"],
    ),
    (
        "lookup_precedent",
        "Search the case ARCHIVE (closed/past cases, not in the advisor's current queue) for "
        "precedent — how the team handled a similar situation before. Use when the advisor "
        "asks 'have we done this before?' / 'how did we handle X?'. This is a server-side "
        "lookup that reaches beyond what's on screen. Generate 2-3 believable past cases.",
        {
            "query": {
                "type": "string",
                "description": "What you're searching for, e.g. 'early closure with an open second lien'.",
            },
            "results": {
                "type": "array",
                "items": _PRECEDENT_SCHEMA,
                "description": "The 2-3 most relevant past cases, each with how it was resolved.",
            },
        },
        ["query", "results"],
    ),
    (
        "update_packet_field",
        "Change one field of a case's packet (form) — e.g. when the advisor says 'set the "
        "payoff date to month-end'. Pass the recomputed value yourself (regenerate any figure "
        "that depends on it, like accrued interest, and update those fields too).",
        {
            "ref": {"type": "string", "description": "Case reference."},
            "section": {
                "type": "string",
                "description": "Section id or title to edit, e.g. 'payoff'.",
            },
            "field": {"type": "string", "description": "Field label to set, e.g. 'Payoff date'."},
            "value": {"type": "string", "description": "The new value."},
            "note": {"type": "string", "description": "Optional one-line activity note."},
        },
        ["ref", "section", "field", "value"],
    ),
    (
        "resolve_blocker",
        "Mark a case's blocker as cleared — e.g. once you confirm Legal has subordinated the "
        "lien. This unlocks any draft or packet section the blocker was gating so the advisor "
        "can approve and submit. Only call this when the blocking issue is genuinely resolved.",
        {
            "ref": {"type": "string", "description": "Case reference."},
            "note": {
                "type": "string",
                "description": "What cleared it, e.g. 'Legal subordinated the home-equity line'.",
            },
        },
        ["ref"],
    ),
    (
        "submit_packet",
        "Submit a case's regulated packet to the handling department (a server-side action "
        "with consequences). Maker-checker: this only goes through AFTER the advisor has "
        "approved the drafts and any blocker is cleared — if something is still pending or "
        "blocked, the submission is refused. Confirm the advisor wants to submit before calling.",
        {"ref": {"type": "string", "description": "Case reference whose packet to submit."}},
        ["ref"],
    ),
    (
        "draft_approval",
        "Drop a single draft into a case's 'Needs your approval' queue immediately — for a "
        "case you are co-working on screen with the advisor (e.g. a rate offer for Cho). The "
        "advisor approves or declines it. You never execute it yourself.",
        {
            "ref": {"type": "string", "description": "Case reference."},
            "approval": {**_APPROVAL_SCHEMA, "description": "The draft to add."},
        },
        ["ref", "approval"],
    ),
    (
        "highlight",
        "Scroll to and briefly highlight one section of the open case so the advisor's eye follows you.",
        {
            "section": {
                "type": "string",
                "enum": [
                    "summary",
                    "loan",
                    "payments",
                    "documents",
                    "approvals",
                    "notes",
                    "activity",
                ],
                "description": "Which section to highlight.",
            },
        },
        ["section"],
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


def _normalize_ids(items: list[Any], prefix: str) -> list[dict[str, Any]]:
    """Ensure every dict has a stable string ``id`` (assign ``{prefix}{n}`` if missing)."""
    out: list[dict[str, Any]] = []
    for i, raw in enumerate(items):
        item = dict(raw) if isinstance(raw, dict) else {}
        if not str(item.get("id") or "").strip():
            item["id"] = f"{prefix}{i + 1}"
        else:
            item["id"] = str(item["id"])
        out.append(item)
    return out


class ServicingBrain(GeminiBrain):
    """One per session. The Meridian Servicing Console copilot: LLM + case/board
    screen-driving tools + this session's advisor + live workspace state.
    ``on_interaction`` is the inherited tool-loop ``respond``; :meth:`dispatch_tool`
    runs each call. The browser's ``state_sync`` snapshots arrive via
    :meth:`on_app_event` and ground every turn's working context."""

    def __init__(self, *, llm: GeminiProvider, model: str = DEFAULT_MODEL) -> None:
        super().__init__(
            llm=llm, system_instruction=_SYSTEM_INSTRUCTION, tools=_tools(), model=model
        )
        # Advisor identity, filled for real in on_session_start from the init payload.
        self.advisor_name = "there"
        self.advisor_role = "Servicing Advisor"
        # Latest workspace snapshot the browser has told us about (authoritative;
        # source of truth lives in the browser, this is the brain's view of it).
        self.current_state: dict[str, Any] | None = None
        # Whether any state_sync has arrived yet — only fold state into context
        # once the browser has started pushing snapshots.
        self._state_received = False

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session, start) -> None:
        # The advisor payload rides the start frame. Resolve the advisor's
        # name/role and open with a fixed greeting built from the payload — no LLM
        # call on the start path, so the desk greets the instant the session
        # connects.
        payload = dict(start.init)
        raw_advisor = payload.get("advisor")
        advisor = raw_advisor if isinstance(raw_advisor, dict) else {}
        self.advisor_name = str(advisor.get("name") or "").strip() or "there"
        self.advisor_role = str(advisor.get("role") or "").strip() or "Servicing Advisor"
        await self.say(
            session,
            f"Hi {self.advisor_name} — {DESK_NAME} here. What would you like to start on?",
        )

    async def on_app_event(self, session, event) -> None:
        """Browser→Brain feedback. ``state_sync`` carries a compact snapshot of
        the workspace — which case/tab is on screen, pending approvals, and a lean
        view of the cases. We keep the latest silently (no inference) so the
        assistant always knows the live on-screen state; the snapshot grounds every
        turn's working context and backs get_advisor_context."""
        if event.name == "state_sync":
            self._ingest_state(event.data or {})

    def _ingest_state(self, data: dict[str, Any]) -> None:
        snapshot = data.get("workspace")
        self.current_state = snapshot if isinstance(snapshot, dict) else None
        self._state_received = True
        logger.info("servicing: state_sync ingested (active={})", bool(self.current_state))

    # ─── Working context grounding (silent state fold) ──────────────────────

    def grounding(self, interaction) -> str | None:
        """Fold the live workspace snapshot into every turn (every ``state_sync``
        folded into the LLM context, no inference) so the assistant always reasons
        from the authoritative on-screen state."""
        return self._state_grounding()

    def _state_grounding(self) -> str | None:
        """The authoritative-workspace grounding text. ``None`` before the browser
        has pushed any snapshot."""
        if not self._state_received:
            return None
        if self.current_state is None:
            return "CURRENT SCREEN STATE: the advisor's console is initializing."
        try:
            blob = json.dumps(self.current_state, ensure_ascii=False)
        except (TypeError, ValueError):
            blob = str(self.current_state)
        return (
            "CURRENT WORKSPACE STATE (authoritative — reflects where the advisor is and "
            "every edit they or you have made; always reason from this): " + blob
        )

    # ─── Tools ──────────────────────────────────────────────────────────

    def dispatch_tool(self, interaction, name: str, args: dict[str, Any]) -> str:
        """Run one tool call: normalize the model-generated data, drive the browser
        via ``interaction.action(...)`` (the RTVI ui_command the /servicing UI
        renders), and return the same short ack fed back to the model.
        ``get_advisor_context`` is read-only (no UI push)."""
        act = interaction.action
        if name == "open_board":
            logger.info("servicing: open_board")
            act("open_board")
            return str({"status": "board_open"})
        if name == "open_case":
            ref = str(args.get("ref", "")).strip().upper()
            logger.info("servicing: open_case {!r}", ref)
            act("open_case", {"ref": ref})
            return str({"status": "opened", "ref": ref})
        if name == "set_tab":
            tab = str(args.get("tab", "")).strip()
            logger.info("servicing: set_tab {!r}", tab)
            act("set_tab", {"tab": tab})
            return str({"status": "set", "tab": tab})
        if name == "get_advisor_context":
            state = self.current_state or {}
            where = {
                "view": state.get("view"),
                "active_case": state.get("active_case"),
                "tab": state.get("tab"),
                "pending_approvals": state.get("pending_approvals"),
            }
            logger.info("servicing: get_advisor_context -> {}", where)
            return str(where)
        if name == "assign_case":
            ref = str(args.get("ref", "")).strip().upper()
            kind = str(args.get("assignee_kind", "")).strip()
            assignee = str(args.get("assignee", "")).strip()
            logger.info("servicing: assign_case {} -> {}:{}", ref, kind, assignee)
            act("assign_case", {"ref": ref, "assignee_kind": kind, "assignee": assignee})
            label = (
                DEPARTMENTS.get(assignee.lower(), assignee) if kind == "department" else assignee
            )
            return str({"status": "assigned", "ref": ref, "to": label})
        if name == "move_case":
            ref = str(args.get("ref", "")).strip().upper()
            stage = str(args.get("stage", "")).strip()
            logger.info("servicing: move_case {} -> {}", ref, stage)
            act("move_case", {"ref": ref, "stage": stage})
            return str({"status": "moved", "ref": ref, "stage": stage})
        if name == "add_comment":
            ref = str(args.get("ref", "")).strip().upper()
            text = str(args.get("text", "")).strip()
            dept = str(args.get("dept", "")).strip().lower()
            if not ref or not text:
                return str({"error": "need a case ref and note text"})
            logger.info("servicing: add_comment {} (dept={})", ref, dept or None)
            act("add_comment", {"ref": ref, "text": text, "dept": dept})
            return str(
                {"status": "note_added", "ref": ref, "dept": DEPARTMENTS.get(dept, dept) or None}
            )
        if name == "prepare_case":
            ref = str(args.get("ref", "")).strip().upper()
            jobs = _normalize_ids(list(args.get("jobs") or []), "j")
            approvals = _normalize_ids(list(args.get("approvals") or []), "a")
            findings = _normalize_ids(list(args.get("findings") or []), "f")
            blocker = args.get("blocker") if isinstance(args.get("blocker"), dict) else None
            packet = args.get("packet") if isinstance(args.get("packet"), dict) else None
            summary = str(args.get("summary", ""))
            if not ref or not jobs:
                return str({"error": "need a case ref and at least one job"})
            logger.info(
                "servicing: prepare_case {} ({} jobs, {} findings, blocker={}, packet={}, {} approvals)",
                ref,
                len(jobs),
                len(findings),
                bool(blocker),
                bool(packet),
                len(approvals),
            )
            act(
                "prepare_case",
                {
                    "ref": ref,
                    "summary": summary,
                    "jobs": jobs,
                    "findings": findings,
                    "blocker": blocker,
                    "packet": packet,
                    "approvals": approvals,
                },
            )
            return str(
                {
                    "status": "preparing_in_background",
                    "ref": ref,
                    "jobs": [j["label"] for j in jobs],
                    "blocker": blocker.get("title") if blocker else None,
                    "note": "Running in the background; the advisor stays unblocked. Tell them when ready.",
                }
            )
        if name == "post_workup":
            ref = str(args.get("ref", "")).strip().upper()
            findings = _normalize_ids(list(args.get("findings") or []), "f")
            blocker = args.get("blocker") if isinstance(args.get("blocker"), dict) else None
            if not ref or not findings:
                return str({"error": "need a case ref and at least one finding"})
            logger.info(
                "servicing: post_workup {} ({} findings, blocker={})",
                ref,
                len(findings),
                bool(blocker),
            )
            act("post_workup", {"ref": ref, "findings": findings, "blocker": blocker})
            return str(
                {
                    "status": "workup_posted",
                    "ref": ref,
                    "blocker": blocker.get("title") if blocker else None,
                }
            )
        if name == "lookup_precedent":
            query = str(args.get("query", "")).strip()
            results = _normalize_ids(list(args.get("results") or []), "p")
            logger.info("servicing: lookup_precedent {!r} ({} results)", query, len(results))
            act("lookup_precedent", {"query": query, "results": results})
            return str(
                {
                    "status": "searched_archive",
                    "query": query,
                    "results": [
                        {"ref": r.get("ref"), "resolution": r.get("resolution")} for r in results
                    ],
                }
            )
        if name == "update_packet_field":
            ref = str(args.get("ref", "")).strip().upper()
            section = str(args.get("section", "")).strip()
            field = str(args.get("field", "")).strip()
            value = str(args.get("value", "")).strip()
            note = str(args.get("note", "")).strip()
            if not ref or not section or not field:
                return str({"error": "need ref, section and field"})
            logger.info(
                "servicing: update_packet_field {} {}/{} -> {!r}", ref, section, field, value
            )
            act(
                "update_packet_field",
                {"ref": ref, "section": section, "field": field, "value": value, "note": note},
            )
            return str({"status": "field_updated", "ref": ref, "field": field, "value": value})
        if name == "resolve_blocker":
            ref = str(args.get("ref", "")).strip().upper()
            note = str(args.get("note", "")).strip()
            if not ref:
                return str({"error": "need a case ref"})
            logger.info("servicing: resolve_blocker {} ({})", ref, note)
            act("resolve_blocker", {"ref": ref, "note": note})
            return str({"status": "blocker_cleared", "ref": ref})
        if name == "submit_packet":
            ref = str(args.get("ref", "")).strip().upper()
            if not ref:
                return str({"error": "need a case ref"})
            logger.info("servicing: submit_packet {}", ref)
            act("submit_packet", {"ref": ref})
            return str(
                {
                    "status": "submit_requested",
                    "ref": ref,
                    "note": (
                        "The console will submit only if the advisor has approved the drafts and no "
                        "blocker is open; otherwise it stays put. Check the workspace state to confirm."
                    ),
                }
            )
        if name == "draft_approval":
            ref = str(args.get("ref", "")).strip().upper()
            approval = args.get("approval")
            if not ref or not isinstance(approval, dict):
                return str({"error": "need a case ref and an approval object"})
            approval = _normalize_ids([approval], "a")[0]
            logger.info("servicing: draft_approval {} {!r}", ref, approval.get("title"))
            act("draft_approval", {"ref": ref, "approval": approval})
            return str(
                {"status": "drafted_for_approval", "ref": ref, "title": approval.get("title")}
            )
        if name == "highlight":
            section = str(args.get("section", ""))
            logger.info("servicing: highlight {}", section)
            act("highlight", {"section": section})
            return str({"status": "highlighted", "section": section})
        return "unknown tool"
