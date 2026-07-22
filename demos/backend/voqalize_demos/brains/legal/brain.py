"""LegalBrain — the "Docket" ambient contract-review copilot.

A ``voqalize.sdk.Brain`` (LLM + document-driving tools + per-session
reading-position state). Voqalize dials this brain's WebSocket
per session; ``respond`` (inherited from :class:`GeminiBrain`) runs the manual
Gemini function-calling loop where **each LLM call is one
``interaction.inference()`` bracket** (1:1 with the wire): speak a short line,
call a document tool, feed the result back.

Every tool body drives the browser via ``interaction.action(name, {...})`` — the
RTVI ``ui_command`` the ``/legal`` "Docket" UI renders (point at a clause,
add a comment, propose a redline, insert a clause, fan out diligence tasks, route
for approval, extract obligations, summarize the session).

Beyond the standard turn, the browser streams the lawyer's *reading position*:
the clause centered in their viewport arrives on :meth:`on_app_event` as a
``clause_focus`` event. Unlike the support brain's ``photo_upload`` — which
triggers an LLM turn — ``clause_focus`` is **silent**: it never runs an
inference, it just folds the current reading position into the working context so
an ambiguous question ("what does this mean", "is this okay") is grounded in the
clause the lawyer is actually looking at (see :meth:`working_context`).

The LLM is **dependency-injected** as a :class:`GeminiProvider`; the brain owns
only the prompt, the tool schemas, and this session's focus state. The
conversation record is framework-owned (the SDK keeps the heard-text transcript
in ``interaction.conversation``), rebuilt into Gemini's working context each turn
by the :class:`GeminiBrain` base.
"""

from __future__ import annotations

import json
from typing import Any

from google.genai import types
from loguru import logger

from voqalize_demos.brains._gemini import DEFAULT_MODEL, GeminiBrain
from voqalize_demos.llm import GeminiProvider

from .content import CLAUSES, CLAUSES_BY_ID, DATA_ROOM, MATTER, PLAYBOOK, PRIOR_DEALS

PRODUCT_NAME = "Docket"


# ─── System-prompt digests ─────────────────────────────────────────────────────


def _clause_digest() -> str:
    lines = []
    for c in CLAUSES:
        lines.append(f"Section {c['number']} ({c['id']}) — {c['heading']}: {c['text']}")
    return "\n".join(lines)


def _playbook_digest() -> str:
    lines = []
    for key, rule in PLAYBOOK.items():
        lines.append(
            f"[{key}] targets {rule['clause_id']} — RULE: {rule['rule']} — "
            f"STATUS IN THIS DOCUMENT: {rule['status'].upper()} — WHY: {rule['why']}"
        )
    return "\n".join(lines)


def _data_room_digest() -> str:
    lines = []
    for d in DATA_ROOM:
        lines.append(f"[{d['id']}] {d['name']} — {d['description']}")
    return "\n".join(lines)


def _prior_deals_digest() -> str:
    lines = []
    for deal in PRIOR_DEALS:
        lines.append(f"{deal['name']}: termination terms — {deal['termination_terms']}")
    return "\n".join(lines)


# ─── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_INSTRUCTION = f"""You are {PRODUCT_NAME}, an ambient voice copilot for a lawyer reviewing a contract. The lawyer is {MATTER["client"]}'s in-house counsel, reviewing a {MATTER["document_title"]} with {MATTER["counterparty"]} before signing. Governing law is {MATTER["governing_law"]}.

YOU ARE AMBIENT, NOT A CHAT ASSISTANT. There is no push-to-talk — the lawyer never presses a button to talk to you, they just speak while reading. Do not behave like a chat widget waiting for "how can I help you" turns. Stay quiet and out of the way; when spoken to, answer briefly and act on the document directly.

VOICE STYLE — YOU ARE A PARALEGAL WORKING QUIETLY IN THE BACKGROUND, NOT A NARRATOR. Your default is to ACT (point_to_clause / add_comment / propose_redline / insert_clause / run_diligence / route_for_approval / extract_obligations / summarize_session) and let the screen carry the answer. Speech is a supplement to the action, not a substitute for it — never describe on screen what you could just show on screen. English only. One short sentence per turn is the target; two is the ceiling except for the single proactive Section 8 catch below. No markdown, lists, or symbols, no throat-clearing ("Sure, let me check that…", "Great question…"), no restating the lawyer's question back to them. When you take an action, say only the minimum that isn't already visible from the action itself — e.g. after propose_redline, "Redlined — capped at two million, carve-out added" beats explaining the whole rationale out loud (the rationale line is already shown on screen). If an answer is a fact with no action to take, give the fact in one sentence and stop. Cite section numbers when you reference the contract ("Section 8, Limitation of Liability"), not internal ids.

GROUND EVERY ANSWER IN THE DOCUMENT AND THE PLAYBOOK BELOW. Do not invent contract language — answer from the clause text and playbook rules given to you. If asked something the document/playbook doesn't cover, say so plainly rather than guessing.

THE DOCUMENT IS CURSOR-AWARE. The browser continuously tells you which clause is centered in the lawyer's viewport (their current reading position). When the lawyer asks something ambiguous like "what does this mean" / "is this okay" / "is this standard", answer about THAT clause unless they name a different one. If your answer or action concerns a DIFFERENT clause than the one in focus, call point_to_clause first so their screen follows you there — never talk about a clause without bringing it on screen if it isn't already.

YOU ACT ON THE DOCUMENT BY VOICE — never just describe an edit, make it:
- To leave a note anchored to a clause ("flag this", "leave a comment that…"), call add_comment.
- To propose an actual redline ("suggest a fix", "redline this", "change the cap to two million"), call propose_redline with the exact original excerpt, your proposed replacement text, and a one-line rationale grounded in the playbook. Never claim the contract itself has changed — you are proposing a redline for the lawyer to accept, not editing the executed document.
- To add a protection that is MISSING from the contract entirely ("we need a data-processing addendum", "there's no mutual indemnification here, add one"), call insert_clause — there is no existing text to strike, only new text to add after a named clause. Use this instead of propose_redline whenever there is nothing in the document to excerpt.

THE HERO MOVE — ONE SPOKEN TURN CAN FAN OUT SEVERAL BACKGROUND ANGLES AT ONCE. This is what makes voice faster than clicking: the lawyer can issue several instructions in one breath ("check the liability cap against our playbook, pull precedent on how we've negotiated this before, and benchmark the indemnification cap against market") and you kick off ALL of those angles as separate background tasks in parallel — you do not do them one at a time and you do not make the lawyer wait. Call run_diligence ONCE with one job per angle whenever the lawyer's turn contains more than one distinct request, or whenever you yourself decide to investigate multiple angles of something. Even a single well-scoped background check is worth a task card if it's not instant.

Each job in run_diligence has a `kind` and you generate its full outcome yourself right now (there is no separate research step) — the UI animates queued -> running -> done and reveals the typed outcome card when it "finishes", staggered so several visibly run concurrently:
- `finding` — a reconciled fact about THIS document, e.g. checking a clause against a playbook rule. Fill `finding_value` (the specific fact, with the actual figures/terms) and `finding_flag` (`risk` if it fails the playbook, `warn` if it's borderline, `ok` if it passes).
- `precedent` — how Acme has negotiated a similar point before. Invent ONE named, specific prior deal (not the current one) with a real-sounding company name, plus `precedent_deal` (deal name + one-line context) and `precedent_resolution` (the specific number/term it was resolved at). Example anchor to imitate the style of (do not reuse verbatim): "the TerraLogix DataWorks MSA (closed Q3 2025)" resolved a similar liability-cap fight at "$1.75M aggregate cap, uncapped for confidentiality/data breaches — vendor countered at $500K, we held the line at 1.75M over two rounds."
- `benchmark` — how this clause compares to the broader portfolio of vendor paper Acme holds, not just one deal. Fill `benchmark_percentile` (e.g. "15th percentile" — low percentile framing for a bad-for-Acme term) and `benchmark_note` (one line grounding the number, e.g. "of the 40-odd SaaS vendor MSAs we hold, only a handful cap below $500K").
- `exposure` — a dollar scenario model for a risk clause. Fill `exposure_cap` (what the clause currently limits recovery to), `exposure_estimate` (a realistic incident-severity dollar figure for what a real claim could cost, reasoned from the nature of the data/services at stake — e.g. fleet telemetry + PI at scale), and `exposure_gap` (the delta, stated plainly, e.g. "a gap of roughly $1.75M between what a real breach could cost and what Section 8 actually recovers").
- `search` — a clause pulled/reconciled across MULTIPLE documents in the data room (not just this one), e.g. "every liability-cap and indemnity clause across the data room". Fill `search_scope` (how many/which data-room documents it covers, e.g. "3 of 4 data room documents") and `search_excerpt` (a representative excerpt or reconciled finding across them). Ground it in the actual data-room documents listed below — do not invent clause types the matter wouldn't contain.
- `research` — an external, outside-the-document check, e.g. counterparty litigation/background history. Fill `research_finding` (the specific finding, invented but realistic — e.g. "no active litigation; one closed 2022 contract dispute, settled"), `research_source` (where it's drawn from, e.g. "PACER + state court filings, last 5 years"), and `research_flag` (`risk`/`warn`/`ok` the same way `finding_flag` works).
- `memo` — a short drafted comparison memo, e.g. comparing this deal's terms against named prior deals. Fill `memo_body` (one tight paragraph, citing specific named deals and figures — ground it in THE PRIOR DEALS below, do not invent unnamed comps).
Every job also needs a one-line `summary` regardless of kind — this is what shows before the card is expanded.

ACT TWO — HOLDING SEVERAL THREADS AT ONCE (the same hero move, at matter scale). Once the lawyer is working the matter more broadly rather than one clause at a time — referencing the data room, the counterparty's background, or other deals rather than just what's on screen — this is the moment to prove you can run several genuinely different lines of work in parallel, not just several flavors of the same clause check. A compound spoken turn like "search the data room for every liability cap, run a litigation check on Nimbus, and draft me a memo comparing their termination rights against our last two deals" is THREE distinct angles — call run_diligence ONCE with three jobs, one `search`, one `research`, one `memo`, so all three light up and run concurrently while the lawyer keeps talking. This works at ANY point in the review, not just at Section 8 — trust the data room and prior-deals context below rather than waiting for a scripted trigger. Prefer mixing kinds (search/research/memo alongside finding/precedent/benchmark/exposure) when the lawyer's asks are genuinely different in nature; don't force every angle into the same kind just because that's what fired last.

THE DATA ROOM (other documents attached to this matter — reference these, don't invent unrelated ones):
{_data_room_digest()}

PRIOR DEALS (ground any `memo` comparison in these, cite them by name):
{_prior_deals_digest()}

WHEN THE LAWYER ASKS YOU TO ESCALATE OR ROUTE SOMETHING ("send this to finance", "this needs GC sign-off", "route it"), call route_for_approval — package the specific issue (with its dollar figures if any) into an approval card addressed to the right role (`routed_to`, e.g. "Finance", "General Counsel"). This demonstrates you understand organizational process, not just contract text — do not use it for routine redlines, only for things that cross a real threshold (e.g. the Section 8 exposure gap).

WHEN THE LAWYER ASKS FOR DEADLINES, RENEWAL DATES, OR NOTICE WINDOWS ("what do I need to track", "pull all the deadlines", "what are our obligations here"), call extract_obligations ONCE covering the WHOLE document (not just the focused clause) — walk every clause and pull every date-bound obligation (renewal notice windows, termination notice periods, payment terms, breach-notification windows, insurance certs). This builds a standing register the lawyer keeps, distinct from the ephemeral diligence tray.

AT THE NATURAL END OF A REVIEW SESSION ("that's everything for now", "wrap this up", "give me a summary"), call summarize_session ONCE — a short headline, 2-4 highlight lines (what was flagged/redlined/inserted), and any open items still outstanding. This is the session's closing beat, not something to call proactively mid-review.

THE PLAYBOOK (your standing negotiating positions for this contract):
{_playbook_digest()}

THE HEADLINE ISSUE — LIMITATION OF LIABILITY (Section 8, id c8). This is the one clause in this MSA that fails the playbook: it caps aggregate liability at a flat $250,000 with no carve-out for confidentiality or data-protection breaches, well under the $2,000,000 floor Acme requires, and it would cap Nimbus's exposure for a data breach at the same amount as any other claim. When the lawyer reaches Section 8, or asks generally "does anything stand out" / "check the contract" / "run the playbook", proactively point this out: point_to_clause to bring Section 8 on screen, explain the gap in one or two spoken sentences, and offer to draft a redline (propose_redline with the fix from the playbook) rather than waiting to be asked twice. This is also the best moment to run a `run_diligence` job of kind `exposure` alongside the redline offer — putting a real dollar gap on the $250,000 cap is what makes the catch land.

THE FULL CONTRACT TEXT (ground every answer in this; cite section numbers, not ids):
{_clause_digest()}

Open with ONE brief, quiet line acknowledging you're following along on the {MATTER["counterparty"]} MSA — not a "how can I help you" greeting. Do not summarize the whole contract unprompted."""


# Fixed opener — spoken straight to TTS with no LLM call, so the demo greets the
# instant the session connects (the model's ~1s first token is off the start path).
# A quiet acknowledgement, not a chat-assistant greeting.
_GREETING = f"I've got the {MATTER['counterparty']} MSA open and I'm following along."


# ── Nested JSON-schema fragments (the LLM-generated data shapes) ───────────────
#
# Flat, not nested-per-kind: Gemini function-calling handles a flat property
# bag far more reliably than oneOf/anyOf branching, so every job carries all
# possible outcome fields as optional and `kind` tells the frontend which
# subset to render.

_JOB_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "description": "Short stable id, e.g. 't1'."},
        "label": {
            "type": "string",
            "description": "Short label of the background angle, e.g. 'Check liability cap vs. playbook'.",
        },
        "detail": {
            "type": "string",
            "description": "One short line of what this task is doing, shown while it runs.",
        },
        "kind": {
            "type": "string",
            "enum": [
                "finding",
                "precedent",
                "benchmark",
                "exposure",
                "search",
                "research",
                "memo",
            ],
            "description": "What kind of outcome this job produces — determines which fields below to fill.",
        },
        "summary": {
            "type": "string",
            "description": "One-line result shown before the card is expanded, regardless of kind.",
        },
        "finding_value": {
            "type": "string",
            "description": "kind=finding only: the specific fact/value found, with real figures/terms.",
        },
        "finding_flag": {
            "type": "string",
            "enum": ["ok", "warn", "risk"],
            "description": "kind=finding only: risk if it fails the playbook, warn if borderline, ok if it passes.",
        },
        "precedent_deal": {
            "type": "string",
            "description": "kind=precedent only: invented prior deal name + one-line context.",
        },
        "precedent_resolution": {
            "type": "string",
            "description": "kind=precedent only: the specific number/term that prior deal resolved at.",
        },
        "benchmark_percentile": {
            "type": "string",
            "description": "kind=benchmark only: e.g. '15th percentile'.",
        },
        "benchmark_note": {
            "type": "string",
            "description": "kind=benchmark only: one line grounding the percentile against Acme's vendor portfolio.",
        },
        "exposure_cap": {
            "type": "string",
            "description": "kind=exposure only: what the clause currently limits recovery to.",
        },
        "exposure_estimate": {
            "type": "string",
            "description": "kind=exposure only: realistic incident-severity dollar figure for a real claim.",
        },
        "exposure_gap": {
            "type": "string",
            "description": "kind=exposure only: the delta between exposure_estimate and exposure_cap, stated plainly.",
        },
        "search_scope": {
            "type": "string",
            "description": "kind=search only: how many/which data-room documents this covers, e.g. '3 of 4 data room documents'.",
        },
        "search_excerpt": {
            "type": "string",
            "description": "kind=search only: a representative excerpt or reconciled finding across those documents.",
        },
        "research_finding": {
            "type": "string",
            "description": "kind=research only: the specific external-check finding, e.g. counterparty litigation history.",
        },
        "research_source": {
            "type": "string",
            "description": "kind=research only: where the finding is drawn from, e.g. 'PACER + state court filings'.",
        },
        "research_flag": {
            "type": "string",
            "enum": ["ok", "warn", "risk"],
            "description": "kind=research only: risk/warn/ok, same meaning as finding_flag.",
        },
        "memo_body": {
            "type": "string",
            "description": "kind=memo only: one tight paragraph of drafted comparison text, citing named prior deals/figures.",
        },
    },
    "required": ["label", "kind", "summary"],
}

_OBLIGATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "description": "Short stable id, e.g. 'ob1'."},
        "clause_id": {
            "type": "string",
            "enum": list(CLAUSES_BY_ID.keys()),
            "description": "The clause this obligation comes from.",
        },
        "label": {"type": "string", "description": "Short label, e.g. 'Non-renewal notice'."},
        "window": {
            "type": "string",
            "description": "The date-bound figure, e.g. '90 days before renewal' or 'within 72 hours of breach'.",
        },
        "note": {
            "type": "string",
            "description": "One short line of context, e.g. who owes it and what triggers it.",
        },
    },
    "required": ["clause_id", "label", "window"],
}


# ─── Tool schemas (JSON-schema dicts) ──────────────────────────────────────────

# (tool_name, description, properties, required)
_TOOLSPECS: list[tuple[str, str, dict[str, Any], list[str]]] = [
    (
        "point_to_clause",
        "Bring a clause on screen — smooth-scrolls the document to it and briefly "
        "highlights it, with a light animation from the ambient border to the clause. "
        "Call this BEFORE or WHILE discussing any clause that isn't already the one the "
        "lawyer is looking at.",
        {
            "clause_id": {
                "type": "string",
                "enum": list(CLAUSES_BY_ID.keys()),
                "description": "The clause to bring on screen.",
            },
            "reason": {
                "type": "string",
                "description": "One short phrase for why you're pointing here, e.g. 'the liability cap'.",
            },
        },
        ["clause_id"],
    ),
    (
        "add_comment",
        "Leave a short note anchored to a clause, as a sticky comment bubble. Use for "
        "flags/observations that aren't a proposed text change — e.g. 'flag this' or "
        "'note that this needs a co-marketing carve-out'.",
        {
            "clause_id": {
                "type": "string",
                "enum": list(CLAUSES_BY_ID.keys()),
                "description": "The clause this comment is about.",
            },
            "text": {
                "type": "string",
                "description": "The comment text — a sentence or two.",
            },
        },
        ["clause_id", "text"],
    ),
    (
        "propose_redline",
        "Propose a specific text change to a clause — a real redline, shown as inline "
        "strikethrough of the original text and an inserted replacement, with your "
        "rationale underneath. Use when the lawyer asks you to fix/redline/change "
        "something, or when you proactively catch a playbook failure (like the "
        "liability cap in Section 8) and want to offer the fix. This PROPOSES a change "
        "for the lawyer to accept — it does not alter the executed contract.",
        {
            "clause_id": {
                "type": "string",
                "enum": list(CLAUSES_BY_ID.keys()),
                "description": "The clause being redlined.",
            },
            "original_excerpt": {
                "type": "string",
                "description": "The exact (or near-exact) span of the current clause text being replaced.",
            },
            "proposed_text": {
                "type": "string",
                "description": "Your proposed replacement text for that span.",
            },
            "rationale": {
                "type": "string",
                "description": "One short line on why, grounded in the playbook where relevant.",
            },
        },
        ["clause_id", "original_excerpt", "proposed_text", "rationale"],
    ),
    (
        "insert_clause",
        "Add a wholly new clause after an existing one, for a protection that is "
        "MISSING from the contract entirely — there is nothing to strike, only new text "
        "to add. Rendered as an inserted block (not a strikethrough diff) with your "
        "rationale underneath. Use insert_clause instead of propose_redline whenever "
        "there's no existing excerpt to point at.",
        {
            "after_clause_id": {
                "type": "string",
                "enum": list(CLAUSES_BY_ID.keys()),
                "description": "The clause this new one should be inserted directly after.",
            },
            "heading": {
                "type": "string",
                "description": "Heading for the new clause, e.g. 'Data Processing Addendum'.",
            },
            "proposed_text": {
                "type": "string",
                "description": "The full proposed text of the new clause.",
            },
            "rationale": {
                "type": "string",
                "description": "One short line on why this protection is needed, grounded in the playbook where relevant.",
            },
        },
        ["after_clause_id", "heading", "proposed_text", "rationale"],
    ),
    (
        "run_diligence",
        "Kick off one or more background diligence angles in parallel from a single "
        "spoken turn — the signature move. Use whenever the lawyer's turn contains more "
        "than one distinct request, or you decide to investigate multiple angles "
        "yourself (e.g. playbook check + precedent pull + benchmark, or — at matter "
        "scope — a data-room search + a litigation-history check + a comparison memo). "
        "Each job has a `kind` (finding / precedent / benchmark / exposure / search / "
        "research / memo) and you generate its full typed outcome yourself right now; "
        "the UI animates queued -> running -> done and reveals a typed outcome card when "
        "each job finishes, staggered so they visibly run concurrently.",
        {
            "jobs": {
                "type": "array",
                "items": _JOB_SCHEMA,
                "description": "One entry per background angle (usually 2-4).",
            },
        },
        ["jobs"],
    ),
    (
        "route_for_approval",
        "Package a flagged issue into an approval card routed to a named role, for "
        "when the lawyer wants to escalate something that crosses a real threshold "
        "(dollar exposure, risk severity) rather than just redline it themselves.",
        {
            "title": {"type": "string", "description": "Short title of what's being routed."},
            "summary": {"type": "string", "description": "One-line summary of the issue."},
            "amount": {
                "type": "number",
                "description": "The dollar figure at stake, if any (0 if not applicable).",
            },
            "lines": {
                "type": "array",
                "items": {"type": "string"},
                "description": "2-4 short supporting bullet lines.",
            },
            "recommendation": {"type": "string", "description": "Your one-line recommendation."},
            "routed_to": {
                "type": "string",
                "description": "The role this is routed to, e.g. 'Finance' or 'General Counsel'.",
            },
        },
        ["title", "summary", "recommendation", "routed_to"],
    ),
    (
        "extract_obligations",
        "Walk the WHOLE document and pull every date-bound obligation (renewal/notice "
        "windows, termination notice periods, payment terms, breach-notification "
        "windows, insurance certs) into a standing register the lawyer keeps. Call "
        "once, covering every clause with a real date-bound term, not just the one in "
        "focus.",
        {
            "obligations": {
                "type": "array",
                "items": _OBLIGATION_SCHEMA,
                "description": "One entry per date-bound obligation found across the document.",
            },
        },
        ["obligations"],
    ),
    (
        "summarize_session",
        "Close out the review session with a short summary card — call at the natural "
        "end of a review (the lawyer says something like 'that's everything', 'wrap "
        "this up', 'give me a summary'), not proactively mid-review.",
        {
            "headline": {"type": "string", "description": "One short headline for the session."},
            "highlights": {
                "type": "array",
                "items": {"type": "string"},
                "description": "2-4 short lines on what was flagged/redlined/inserted this session.",
            },
            "open_items": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Anything still outstanding — can be empty.",
            },
        },
        ["headline", "highlights"],
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


class LegalBrain(GeminiBrain):
    """One per session. The Docket contract-review copilot: LLM + document tools +
    this session's reading-position (clause_focus) state. ``on_interaction`` is the
    inherited tool-loop ``respond``; :meth:`dispatch_tool` runs each call. The
    browser's silent ``clause_focus`` reading-position stream arrives on
    :meth:`on_app_event` and is folded into the working context (never an inference).
    """

    def __init__(self, *, llm: GeminiProvider, model: str = DEFAULT_MODEL) -> None:
        super().__init__(
            llm=llm, system_instruction=_SYSTEM_INSTRUCTION, tools=_tools(), model=model
        )
        # Latest reading position the browser pushed (clause_focus). Folded into
        # the working context each turn so ambiguous questions ("what does this
        # mean") ground in the clause on screen. Never triggers an inference.
        self.current_focus: dict[str, Any] | None = None
        self._last_focus_clause_id: str | None = None

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session, start) -> None:
        # Open with a fixed quiet line (no LLM call on the start path).
        await self.say(session, _GREETING)

    async def on_app_event(self, session, event) -> None:
        """Browser→Brain feedback. ``clause_focus`` carries the clause centered in
        the lawyer's viewport; we fold it into context SILENTLY (no inference) so the
        copilot always knows the current reading position without speaking unprompted."""
        if event.name == "clause_focus":
            self._ingest_focus(event.data or {})

    # ─── Browser→brain: reading-position sync (silent awareness) ────────

    def _ingest_focus(self, data: dict[str, Any]) -> None:
        clause_id = str(data.get("clause_id") or "").strip()
        self.current_focus = data if clause_id in CLAUSES_BY_ID else None
        if self.current_focus is None:
            return
        # Only log when the reading position actually changes clause — the browser
        # re-sends the same clause_focus as the lawyer reads within a section. We
        # keep only the latest focus and rebuild it into context each turn, so the
        # dedup is purely to avoid noisy logs.
        if clause_id == self._last_focus_clause_id:
            return
        self._last_focus_clause_id = clause_id
        logger.info("legal: clause_focus ingested (clause_id={})", clause_id)

    def grounding(self, interaction) -> str | None:
        """The lawyer's current reading position (``clause_focus``). The base folds
        it in just before the latest user turn — so an ambiguous question grounds
        in the clause on screen."""
        if not self.current_focus:
            return None
        try:
            blob = json.dumps(self.current_focus, ensure_ascii=False)
        except (TypeError, ValueError):
            blob = str(self.current_focus)
        return (
            "LAWYER IS CURRENTLY VIEWING (authoritative — ground ambiguous questions "
            "in this clause): " + blob
        )

    # ─── Tools ──────────────────────────────────────────────────────────

    def dispatch_tool(self, interaction, name: str, args: dict[str, Any]) -> str:
        """Run one tool call: drive the browser via ``interaction.action(...)`` (the
        RTVI ui_command the /legal Docket UI renders) and return the status payload
        fed back to the model."""
        if name == "point_to_clause":
            return self._point_to_clause(interaction, args)
        if name == "add_comment":
            return self._add_comment(interaction, args)
        if name == "propose_redline":
            return self._propose_redline(interaction, args)
        if name == "insert_clause":
            return self._insert_clause(interaction, args)
        if name == "run_diligence":
            return self._run_diligence(interaction, args)
        if name == "route_for_approval":
            return self._route_for_approval(interaction, args)
        if name == "extract_obligations":
            return self._extract_obligations(interaction, args)
        if name == "summarize_session":
            return self._summarize_session(interaction, args)
        return "unknown tool"

    def _point_to_clause(self, interaction, args: dict[str, Any]) -> str:
        clause_id = str(args.get("clause_id", "")).strip()
        reason = str(args.get("reason", "")).strip()
        if clause_id not in CLAUSES_BY_ID:
            return str({"error": f"unknown clause_id {clause_id!r}"})
        logger.info("legal: point_to_clause {} ({})", clause_id, reason)
        interaction.action("point_to_clause", {"clause_id": clause_id, "reason": reason})
        return str({"status": "pointed", "clause_id": clause_id})

    def _add_comment(self, interaction, args: dict[str, Any]) -> str:
        clause_id = str(args.get("clause_id", "")).strip()
        text = str(args.get("text", "")).strip()
        if clause_id not in CLAUSES_BY_ID or not text:
            return str({"error": "need a valid clause_id and comment text"})
        comment = _normalize_ids([{"clause_id": clause_id, "text": text}], "cm")[0]
        logger.info("legal: add_comment {}", clause_id)
        interaction.action(
            "add_comment", {"id": comment["id"], "clause_id": clause_id, "text": text}
        )
        return str({"status": "comment_added", "clause_id": clause_id})

    def _propose_redline(self, interaction, args: dict[str, Any]) -> str:
        clause_id = str(args.get("clause_id", "")).strip()
        original_excerpt = str(args.get("original_excerpt", "")).strip()
        proposed_text = str(args.get("proposed_text", "")).strip()
        rationale = str(args.get("rationale", "")).strip()
        if clause_id not in CLAUSES_BY_ID or not original_excerpt or not proposed_text:
            return str({"error": "need a valid clause_id, original_excerpt and proposed_text"})
        redline = _normalize_ids(
            [
                {
                    "clause_id": clause_id,
                    "original_excerpt": original_excerpt,
                    "proposed_text": proposed_text,
                    "rationale": rationale,
                }
            ],
            "rl",
        )[0]
        logger.info("legal: propose_redline {}", clause_id)
        interaction.action(
            "propose_redline",
            {
                "id": redline["id"],
                "clause_id": clause_id,
                "original_excerpt": original_excerpt,
                "proposed_text": proposed_text,
                "rationale": rationale,
            },
        )
        return str({"status": "redline_proposed", "clause_id": clause_id})

    def _insert_clause(self, interaction, args: dict[str, Any]) -> str:
        after_clause_id = str(args.get("after_clause_id", "")).strip()
        heading = str(args.get("heading", "")).strip()
        proposed_text = str(args.get("proposed_text", "")).strip()
        rationale = str(args.get("rationale", "")).strip()
        if after_clause_id not in CLAUSES_BY_ID or not heading or not proposed_text:
            return str({"error": "need a valid after_clause_id, heading and proposed_text"})
        insertion = _normalize_ids(
            [
                {
                    "after_clause_id": after_clause_id,
                    "heading": heading,
                    "proposed_text": proposed_text,
                    "rationale": rationale,
                }
            ],
            "ins",
        )[0]
        logger.info("legal: insert_clause after {}", after_clause_id)
        interaction.action(
            "insert_clause",
            {
                "id": insertion["id"],
                "after_clause_id": after_clause_id,
                "heading": heading,
                "proposed_text": proposed_text,
                "rationale": rationale,
            },
        )
        return str({"status": "clause_inserted", "after_clause_id": after_clause_id})

    def _run_diligence(self, interaction, args: dict[str, Any]) -> str:
        jobs = _normalize_ids(list(args.get("jobs") or []), "t")
        jobs = [
            j
            for j in jobs
            if str(j.get("label") or "").strip() and str(j.get("kind") or "").strip()
        ]
        if not jobs:
            return str({"error": "need at least one job with a label and kind"})
        logger.info("legal: run_diligence ({} jobs)", len(jobs))
        interaction.action("run_diligence", {"jobs": jobs})
        return str(
            {
                "status": "running_in_background",
                "jobs": [j["label"] for j in jobs],
                "note": (
                    "Kicked off and running concurrently on screen right now — the lawyer keeps "
                    "reading while they run. Acknowledge in ONE short line that you've set them "
                    "going (e.g. 'Running all three now'); do NOT claim they're finished, and do "
                    "NOT read the results aloud — the cards fill in on screen on their own."
                ),
            }
        )

    def _route_for_approval(self, interaction, args: dict[str, Any]) -> str:
        title = str(args.get("title", "")).strip()
        summary = str(args.get("summary", "")).strip()
        recommendation = str(args.get("recommendation", "")).strip()
        routed_to = str(args.get("routed_to", "")).strip()
        if not title or not summary or not recommendation or not routed_to:
            return str({"error": "need title, summary, recommendation and routed_to"})
        approval = _normalize_ids(
            [
                {
                    "title": title,
                    "summary": summary,
                    "amount": args.get("amount") or 0,
                    "lines": list(args.get("lines") or []),
                    "recommendation": recommendation,
                    "routed_to": routed_to,
                }
            ],
            "ap",
        )[0]
        logger.info("legal: route_for_approval -> {}", routed_to)
        interaction.action("route_for_approval", approval)
        return str({"status": "routed", "routed_to": routed_to})

    def _extract_obligations(self, interaction, args: dict[str, Any]) -> str:
        obligations = _normalize_ids(list(args.get("obligations") or []), "ob")
        obligations = [
            o
            for o in obligations
            if str(o.get("clause_id") or "") in CLAUSES_BY_ID and str(o.get("label") or "").strip()
        ]
        if not obligations:
            return str({"error": "need at least one valid obligation"})
        logger.info("legal: extract_obligations ({} entries)", len(obligations))
        interaction.action("extract_obligations", {"obligations": obligations})
        return str({"status": "obligations_extracted", "count": len(obligations)})

    def _summarize_session(self, interaction, args: dict[str, Any]) -> str:
        headline = str(args.get("headline", "")).strip()
        highlights = [str(h).strip() for h in (args.get("highlights") or []) if str(h).strip()]
        open_items = [str(h).strip() for h in (args.get("open_items") or []) if str(h).strip()]
        if not headline or not highlights:
            return str({"error": "need a headline and at least one highlight"})
        logger.info("legal: summarize_session")
        interaction.action(
            "summarize_session",
            {"headline": headline, "highlights": highlights, "open_items": open_items},
        )
        return str({"status": "session_summarized"})
