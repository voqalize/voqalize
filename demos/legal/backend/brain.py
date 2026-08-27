"""LegalBrain — the "Docket" ambient contract-review copilot.

A :class:`voqalize.sdk.gemini.GeminiBrain` that runs the ``/legal`` demo: in-house
counsel reads a Master Services Agreement out loud while the copilot follows
along, points at clauses, redlines them, fans diligence out in the background and
closes the session with a summary.

Two things worth calling out about how per-session state flows in:

  * **clause_focus** — the browser streams the clause centered in the lawyer's
    viewport. :meth:`LegalBrain.on_rtvi` folds it in *silently* — no floor taken,
    no turn — and :meth:`LegalBrain.note` carries it into the next turn, so
    "what does this mean" is answered about the clause on screen.
  * **the matter is static** — the contract, the playbook, the data room and the
    prior deals are the same for every session, so they are compiled into the
    system instruction once at import.

**The LLM generates the substantive data** (redline text, diligence outcomes,
obligation windows): each tool takes one pydantic model, and that model *is* the
:class:`~voqalize.sdk.Action` the ``/legal`` UI renders — so every tool body is
one ``self.session.dispatch(...)`` line.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel, Field
from voqalize_demos import DEFAULT_MODEL, GeminiBrain

from voqalize.sdk import Action, RTVIMessage, RTVIType, Session
from voqalize.sdk.wire import Config, Language, SttConfig, TtsConfig, Voice

from .content import (
    CLAUSES,
    CLAUSES_BY_ID,
    DATA_ROOM,
    MATTER,
    PLAYBOOK,
    PRIOR_DEALS,
    ClauseId,
)

PRODUCT_NAME = "Docket"


# ─── System-prompt digests ─────────────────────────────────────────────────────


def _clause_digest() -> str:
    return "\n".join(
        f"Section {c['number']} ({c['id']}) — {c['heading']}: {c['text']}" for c in CLAUSES
    )


def _playbook_digest() -> str:
    return "\n".join(
        f"[{key}] targets {rule['clause_id']} — RULE: {rule['rule']} — "
        f"STATUS IN THIS DOCUMENT: {rule['status'].upper()} — WHY: {rule['why']}"
        for key, rule in PLAYBOOK.items()
    )


def _data_room_digest() -> str:
    return "\n".join(f"[{d['id']}] {d['name']} — {d['description']}" for d in DATA_ROOM)


def _prior_deals_digest() -> str:
    return "\n".join(
        f"{deal['name']}: termination terms — {deal['termination_terms']}" for deal in PRIOR_DEALS
    )


# ─── System prompt ─────────────────────────────────────────────────────────────
#
# The tools are not restated here. Each carries its own description on the method
# that takes it, and every field it generates carries its own on the model — read
# them there. What is left is what no single tool can say: who this copilot is,
# how it speaks, and what it is looking at.

_SYSTEM_INSTRUCTION = f"""You are {PRODUCT_NAME}, an ambient voice copilot for a lawyer reviewing a contract. The lawyer is {MATTER["client"]}'s in-house counsel, reviewing a {MATTER["document_title"]} with {MATTER["counterparty"]} before signing. Governing law is {MATTER["governing_law"]}.

YOU ARE AMBIENT, NOT A CHAT ASSISTANT. There is no push-to-talk — the lawyer never presses a button to talk to you, they just speak while reading. Do not behave like a chat widget waiting for "how can I help you" turns. Stay quiet and out of the way; when spoken to, answer briefly and act on the document directly.

VOICE STYLE — YOU ARE A PARALEGAL WORKING QUIETLY IN THE BACKGROUND, NOT A NARRATOR. Your default is to ACT and let the screen carry the answer. Speech is a supplement to the action, not a substitute for it — never describe on screen what you could just show on screen. English only. One short sentence per turn is the target; two is the ceiling except for the single proactive Section 8 catch below. No markdown, lists, or symbols, no throat-clearing ("Sure, let me check that…", "Great question…"), no restating the lawyer's question back to them. When you take an action, say only the minimum that isn't already visible from the action itself — e.g. after a redline, "Redlined — capped at two million, carve-out added" beats explaining the whole rationale out loud, which is already on screen. If an answer is a fact with no action to take, give the fact in one sentence and stop. Cite section numbers when you reference the contract ("Section 8, Limitation of Liability"), not internal ids.

GROUND EVERY ANSWER IN THE DOCUMENT AND THE PLAYBOOK BELOW. Do not invent contract language — answer from the clause text and playbook rules given to you. If asked something the document and playbook don't cover, say so plainly rather than guessing.

THE DOCUMENT IS CURSOR-AWARE. The browser continuously tells you which clause is centered in the lawyer's viewport, their current reading position. When the lawyer asks something ambiguous like "what does this mean" / "is this okay" / "is this standard", answer about THAT clause unless they name a different one. If your answer or action concerns a DIFFERENT clause than the one in focus, bring their screen there first — never talk about a clause without bringing it on screen if it isn't already.

NEVER CLAIM THE CONTRACT ITSELF HAS CHANGED. You propose redlines and insertions for the lawyer to accept; the executed document is not yours to edit.

THE HERO MOVE — ONE SPOKEN TURN CAN FAN OUT SEVERAL BACKGROUND ANGLES AT ONCE. This is what makes voice faster than clicking: the lawyer can issue several instructions in one breath ("check the liability cap against our playbook, pull precedent on how we've negotiated this before, and benchmark the indemnification cap against market") and you kick off ALL of those angles as background tasks in parallel — you do not do them one at a time and you do not make the lawyer wait. Run diligence ONCE with one job per angle whenever the lawyer's turn contains more than one distinct request, or whenever you yourself decide to investigate several angles of something. Even a single well-scoped background check is worth a task card if it isn't instant.

ACT TWO — HOLDING SEVERAL THREADS AT ONCE (the same hero move, at matter scale). Once the lawyer is working the matter more broadly rather than one clause at a time — referencing the data room, the counterparty's background, or other deals rather than just what's on screen — this is the moment to prove you can run several genuinely different lines of work in parallel, not just several flavors of the same clause check. A compound turn like "search the data room for every liability cap, run a litigation check on Nimbus, and draft me a memo comparing their termination rights against our last two deals" is THREE distinct angles: one diligence call, three jobs, one `search`, one `research`, one `memo`, so all three light up and run concurrently while the lawyer keeps talking. This works at ANY point in the review, not just at Section 8 — trust the data room and prior deals below rather than waiting for a scripted trigger. Prefer mixing kinds when the asks are genuinely different in nature; don't force every angle into the same kind because that is what fired last.

THE DATA ROOM (other documents attached to this matter — reference these, don't invent unrelated ones):
{_data_room_digest()}

PRIOR DEALS (ground any memo comparison in these, cite them by name):
{_prior_deals_digest()}

THE PLAYBOOK (your standing negotiating positions for this contract):
{_playbook_digest()}

THE HEADLINE ISSUE — LIMITATION OF LIABILITY (Section 8, id c8). This is the one clause in this MSA that fails the playbook: it caps aggregate liability at a flat $250,000 with no carve-out for confidentiality or data-protection breaches, well under the $2,000,000 floor Acme requires, and it would cap Nimbus's exposure for a data breach at the same amount as any other claim. When the lawyer reaches Section 8, or asks generally "does anything stand out" / "check the contract" / "run the playbook", proactively point this out: bring Section 8 on screen, explain the gap in one or two spoken sentences, and offer the redline from the playbook rather than waiting to be asked twice. This is also the best moment to run a diligence job of kind `exposure` alongside the redline offer — putting a real dollar gap on the $250,000 cap is what makes the catch land.

THE FULL CONTRACT TEXT (ground every answer in this; cite section numbers, not ids):
{_clause_digest()}

Open with ONE brief, quiet line acknowledging you're following along on the {MATTER["counterparty"]} MSA — not a "how can I help you" greeting. Do not summarize the whole contract unprompted."""


# The opener. A quiet acknowledgement, not a chat-assistant greeting, and generic
# — no counterparty name, which sidesteps TTS mispronouncing a vendor.
_GREETING = "I have the MSA open. Ready to assist."


# ── The tool surface: one pydantic model per tool ──────────────────────────────
#
# Each class below is declared to Gemini straight from itself: the fields are the
# parameters and every ``Field(description=...)`` reaches the model verbatim. The
# *tool's* own description is the docstring on the method that takes it — one
# sentence of instruction, in one place — so nothing here is written twice.
#
# All eight are an ``Action``, so the validated call is also the payload the
# browser renders: one class, one schema, one place to change the shape. The
# frontend mints its own ids, so none is generated here.
#
# ┌──────────────────────────────────────────────────────────────────────────┐
# │ These shapes are duplicated in the frontend as TypeScript, in            │
# │ ``frontend/src/store.tsx``, and the two are kept in sync BY HAND. Change │
# │ a field here and change it there in the same commit.                     │
# └──────────────────────────────────────────────────────────────────────────┘

Flag = Literal["ok", "warn", "risk"]


class PointToClause(Action):
    clause_id: ClauseId = Field(description="The clause to bring on screen.")
    reason: str = Field(
        "", description="One short phrase for why you're pointing here, e.g. 'the liability cap'."
    )


class AddComment(Action):
    clause_id: ClauseId = Field(description="The clause this comment is about.")
    text: str = Field(description="The comment text — a sentence or two.")


class ProposeRedline(Action):
    clause_id: ClauseId = Field(description="The clause being redlined.")
    original_excerpt: str = Field(
        description="The exact (or near-exact) span of the current clause text being replaced."
    )
    proposed_text: str = Field(description="Your proposed replacement text for that span.")
    rationale: str = Field(
        description="One short line on why, grounded in the playbook where relevant."
    )


class InsertClause(Action):
    after_clause_id: ClauseId = Field(
        description="The clause this new one should be inserted directly after."
    )
    heading: str = Field(description="Heading for the new clause, e.g. 'Data Processing Addendum'.")
    proposed_text: str = Field(description="The full proposed text of the new clause.")
    rationale: str = Field(
        description="One short line on why this protection is needed, grounded in the "
        "playbook where relevant."
    )


class DiligenceJob(BaseModel):
    """One background angle. Flat rather than a shape per kind: Gemini handles a
    property bag far more reliably than oneOf branching, so a job carries every
    outcome field as optional and `kind` tells the frontend which to render."""

    label: str = Field(
        description="Short label of the background angle, e.g. 'Check liability cap vs. playbook'."
    )
    detail: str = Field(
        "", description="One short line of what this task is doing, shown while it runs."
    )
    kind: Literal["finding", "precedent", "benchmark", "exposure", "search", "research", "memo"] = (
        Field(
            description="What kind of outcome this job produces, and therefore which fields "
            "below to fill. `finding` — a reconciled fact about THIS document, e.g. a clause "
            "checked against a playbook rule. `precedent` — how Acme has negotiated a similar "
            "point before. `benchmark` — how this clause compares to the broader portfolio of "
            "vendor paper Acme holds, not just one deal. `exposure` — a dollar scenario model "
            "for a risk clause. `search` — a clause pulled and reconciled across MULTIPLE "
            "data-room documents. `research` — an external, outside-the-document check, e.g. "
            "counterparty litigation history. `memo` — a short drafted comparison against "
            "named prior deals."
        )
    )
    summary: str = Field(
        description="One-line result shown before the card is expanded, regardless of kind."
    )
    finding_value: str = Field(
        "",
        description="kind=finding only: the specific fact found, with the actual figures/terms.",
    )
    finding_flag: Flag | None = Field(
        None,
        description="kind=finding only: risk if it fails the playbook, warn if borderline, "
        "ok if it passes.",
    )
    precedent_deal: str = Field(
        "",
        description="kind=precedent only: ONE invented prior deal — not this one — with a "
        "real-sounding company name plus a line of context, e.g. 'the TerraLogix DataWorks "
        "MSA (closed Q3 2025)'. Imitate that style, don't reuse it.",
    )
    precedent_resolution: str = Field(
        "",
        description="kind=precedent only: the specific number or term that deal resolved at, "
        "e.g. '$1.75M aggregate cap, uncapped for confidentiality and data breaches — vendor "
        "countered at $500K, we held the line over two rounds'.",
    )
    benchmark_percentile: str = Field(
        "",
        description="kind=benchmark only: e.g. '15th percentile' — low percentile framing for "
        "a term that is bad for Acme.",
    )
    benchmark_note: str = Field(
        "",
        description="kind=benchmark only: one line grounding the percentile against Acme's "
        "vendor portfolio, e.g. 'of the 40-odd SaaS vendor MSAs we hold, only a handful cap "
        "below $500K'.",
    )
    exposure_cap: str = Field(
        "", description="kind=exposure only: what the clause currently limits recovery to."
    )
    exposure_estimate: str = Field(
        "",
        description="kind=exposure only: a realistic incident-severity dollar figure for what "
        "a real claim could cost, reasoned from the data and services at stake.",
    )
    exposure_gap: str = Field(
        "",
        description="kind=exposure only: the delta, stated plainly, e.g. 'a gap of roughly "
        "$1.75M between what a real breach could cost and what Section 8 actually recovers'.",
    )
    search_scope: str = Field(
        "",
        description="kind=search only: how many and which data-room documents this covers, "
        "e.g. '3 of 4 data room documents'. Ground it in the data room you were given.",
    )
    search_excerpt: str = Field(
        "",
        description="kind=search only: a representative excerpt or reconciled finding across "
        "those documents.",
    )
    research_finding: str = Field(
        "",
        description="kind=research only: the specific finding, invented but realistic, e.g. "
        "'no active litigation; one closed 2022 contract dispute, settled'.",
    )
    research_source: str = Field(
        "",
        description="kind=research only: where it is drawn from, e.g. 'PACER + state court "
        "filings, last 5 years'.",
    )
    research_flag: Flag | None = Field(
        None, description="kind=research only: risk/warn/ok, the same meaning as finding_flag."
    )
    memo_body: str = Field(
        "",
        description="kind=memo only: one tight paragraph, citing the named prior deals and "
        "their figures. Do not invent unnamed comps.",
    )


class RunDiligence(Action):
    jobs: list[DiligenceJob] = Field(description="One entry per background angle, usually 2-4.")


class RouteForApproval(Action):
    title: str = Field(description="Short title of what is being routed.")
    summary: str = Field(description="One-line summary of the issue.")
    amount: float = Field(0, description="The dollar figure at stake, 0 if not applicable.")
    lines: list[str] = Field(default_factory=list, description="2-4 short supporting lines.")
    recommendation: str = Field(description="Your one-line recommendation.")
    routed_to: str = Field(
        description="The role this is routed to, e.g. 'Finance' or 'General Counsel'."
    )


class Obligation(BaseModel):
    clause_id: ClauseId = Field(description="The clause this obligation comes from.")
    label: str = Field(description="Short label, e.g. 'Non-renewal notice'.")
    window: str = Field(
        description="The date-bound figure, e.g. '90 days before renewal' or 'within 72 "
        "hours of breach'."
    )
    note: str = Field(
        "", description="One short line of context — who owes it and what triggers it."
    )


class ExtractObligations(Action):
    obligations: list[Obligation] = Field(
        description="One entry per date-bound obligation found across the document."
    )


class SummarizeSession(Action):
    headline: str = Field(description="One short headline for the session.")
    highlights: list[str] = Field(
        description="2-4 short lines on what was flagged, redlined or inserted this session."
    )
    open_items: list[str] = Field(
        default_factory=list, description="Anything still outstanding — can be empty."
    )


class LegalBrain(GeminiBrain):
    """One per session. The Docket contract-review copilot: LLM + document tools +
    this session's reading position.

    The browser streams the clause centered in the lawyer's viewport to
    :meth:`on_rtvi`; a note carries it into the next turn, so an ambiguous
    question is answered about the clause on screen."""

    def __init__(self, *, client: genai.Client, model: str = DEFAULT_MODEL) -> None:
        super().__init__(client=client, system_instruction=_SYSTEM_INSTRUCTION, model=model)
        # Latest reading position the browser pushed. Ephemeral in memory — the
        # browser is the source of truth and re-sends on every scroll.
        self.current_focus: dict[str, Any] | None = None
        self._last_focus_clause_id: str | None = None

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        # This agent's own voice — not the connecting page's to choose, so it is
        # settled here rather than sent with the connect request. `language` moves
        # both legs at once: the recognizer's hint, and the TTS reference clip,
        # which is the accent. This lands before the greeting.
        await session.configure(
            Config(
                stt=SttConfig(language=Language.EN),
                tts=TtsConfig(voice=Voice.OMNIVOICE_GAURI, language=Language.EN),
            )
        )
        logger.info("legal: session start")

    async def greet(self, session: Session) -> str:
        """The opener, written not generated: the lawyer is already reading, and a
        copilot that makes them wait on a first token has already interrupted."""
        return _GREETING

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Browser→brain message. ``clause_focus`` carries the clause centered in the
        lawyer's viewport. Ingested *silently* — no floor taken, no turn; the next
        turn carries it as a note."""
        if msg.type is not RTVIType.CLIENT_MESSAGE or not isinstance(msg.data, dict):
            return
        if msg.data.get("t") == "clause_focus":
            self._ingest_focus(msg.data.get("d") or {})

    # ─── Browser → brain: reading-position sync (silent awareness) ──────

    def _ingest_focus(self, data: dict[str, Any]) -> None:
        clause_id = str(data.get("clause_id") or "").strip()
        self.current_focus = data if clause_id in CLAUSES_BY_ID else None
        if self.current_focus is None:
            return
        # Only append when the position actually changes clause — the browser
        # re-sends the same one as the lawyer reads within a section, and the
        # context is append-only, so an unguarded append would put the same clause
        # in front of the model a hundred times over a call.
        if clause_id == self._last_focus_clause_id:
            return
        self._last_focus_clause_id = clause_id
        try:
            blob = json.dumps(self.current_focus, ensure_ascii=False)
        except (TypeError, ValueError):
            blob = str(self.current_focus)
        self.append_to_context(
            types.Content(
                role="user",
                parts=[
                    types.Part(
                        text="LAWYER IS CURRENTLY VIEWING (authoritative — ground ambiguous "
                        "questions in this clause): " + blob
                    )
                ],
            )
        )
        logger.info("legal: clause_focus ingested (clause_id={})", clause_id)

    # ─── Tools ──────────────────────────────────────────────────────────
    #
    # The model calls these directly. Each takes its own pydantic model, already
    # validated — a `clause_id` that is not in the document cannot reach a body,
    # so nothing here checks for one.
    #
    # They return "ok" and nothing more. A tool result is prompt the model pays
    # for on every following turn, and "pointed, clause_id=c8" only tells it what
    # it just said. ``run_diligence`` is the exception: what the model must not do
    # next is the one thing the tool knows and the model does not.

    @property
    def tools(self) -> list[Any]:
        """The eight the copilot may call. Every one drives the lawyer's screen
        through ``self.session``."""
        return [
            self.point_to_clause,
            self.add_comment,
            self.propose_redline,
            self.insert_clause,
            self.run_diligence,
            self.route_for_approval,
            self.extract_obligations,
            self.summarize_session,
        ]

    async def point_to_clause(self, target: PointToClause) -> str:
        """Bring a clause on screen — smooth-scrolls the document to it and briefly
        highlights it. Call this BEFORE or WHILE discussing any clause that isn't
        already the one the lawyer is looking at."""
        self.session.dispatch(target)
        return "ok"

    async def add_comment(self, comment: AddComment) -> str:
        """Leave a short note anchored to a clause, as a sticky comment bubble. Use
        for flags and observations that aren't a proposed text change — "flag this",
        "note that this needs a co-marketing carve-out"."""
        self.session.dispatch(comment)
        return "ok"

    async def propose_redline(self, redline: ProposeRedline) -> str:
        """Propose a specific text change to a clause — shown as inline strikethrough
        of the original and an inserted replacement, with your rationale underneath.
        Use when the lawyer asks you to fix, redline or change something, or when you
        proactively catch a playbook failure and want to offer the fix."""
        self.session.dispatch(redline)
        return "ok"

    async def insert_clause(self, insertion: InsertClause) -> str:
        """Add a wholly new clause after an existing one, for a protection MISSING
        from the contract entirely — there is nothing to strike, only new text to
        add. Use this instead of a redline whenever there is no existing excerpt to
        point at."""
        self.session.dispatch(insertion)
        return "ok"

    async def run_diligence(self, diligence: RunDiligence) -> str:
        """Kick off one or more background diligence angles in parallel from a single
        spoken turn — the signature move. Use whenever the lawyer's turn contains
        more than one distinct request, or you decide to investigate several angles
        yourself. You generate each job's typed outcome yourself right now; the UI
        animates queued → running → done and reveals the card when each finishes,
        staggered so they visibly run concurrently."""
        self.session.dispatch(diligence)
        logger.info("legal: run_diligence ({} jobs)", len(diligence.jobs))
        return (
            "ok — running concurrently on screen now. Acknowledge in ONE short line that "
            "you've set them going; do NOT claim they are finished and do NOT read the "
            "results aloud, the cards fill in on their own."
        )

    async def route_for_approval(self, approval: RouteForApproval) -> str:
        """Package a flagged issue into an approval card routed to a named role, for
        when the lawyer wants to escalate something that crosses a real threshold —
        dollar exposure, risk severity — rather than redline it themselves. Not for
        routine redlines."""
        self.session.dispatch(approval)
        return "ok"

    async def extract_obligations(self, register: ExtractObligations) -> str:
        """Walk the WHOLE document and pull every date-bound obligation — renewal and
        notice windows, termination notice periods, payment terms, breach-notification
        windows, insurance certs — into a standing register the lawyer keeps. Call
        once, covering every clause with a real date-bound term, not just the one in
        focus."""
        self.session.dispatch(register)
        return "ok"

    async def summarize_session(self, summary: SummarizeSession) -> str:
        """Close out the review with a short summary card. Call at the natural end of
        a session — "that's everything", "wrap this up", "give me a summary" — not
        proactively mid-review."""
        self.session.dispatch(summary)
        return "ok"
