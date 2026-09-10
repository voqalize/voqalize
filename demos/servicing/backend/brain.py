"""ServicingBrain — the Meridian Servicing Desk copilot.

A :class:`voqalize.sdk.gemini.GeminiBrain` for the voice **servicing console**: a
bank ADVISOR works a mortgage-case queue on an internal desk while talking to the
desk copilot, and the copilot DRIVES THE SCREEN as it talks. The advisor is a
colleague, not a customer.

Two things worth calling out about how per-session state flows in:

  * **init** — the advisor's name and role (``session.init["advisor"]``), folded
    into the opening greeting. :meth:`ServicingBrain.greet` is written, not
    generated: the advisor is already logged in, so there is no first-token wait.
  * **the workspace** — the desk keeps its own picture of the console. It is built
    from ``session.init["cases"]`` (the board arrives with the advisor, before
    the first word), patched on every command this brain dispatches, and patched
    again on each thing the advisor does with his own hand — see ``app_events.py``.
    Nothing is pushed and nothing is appended to the context:
    :meth:`ServicingBrain.on_rtvi` adds one line naming the *act*, and the
    workspace itself is read through ``get_advisor_context``. ``ScreenState.version``
    makes that safe rather than hopeful: a tool aimed at a packet or a blocker the
    advisor has moved since the desk last read refuses instead of acting. See
    ``voqalize_demos.screen``.

Fourteen of the fifteen tools dispatch a :class:`~voqalize.sdk.Action` that IS the
tool's own parameter — the LLM generates the substantive data (payoff figures,
rate offers, drafts, packet fields) as the action's fields, and the tool body is
mostly one ``self._show(action)`` line. ``get_advisor_context`` is the
one exception: it is read-only (no action, no screen draw), and exists so the
copilot can answer about the console without moving it.

Two things every UI-facing tool normalizes before it dispatches, because neither
is something the model can be relied on to produce: a case **ref** reaches the
console upper-cased (the model writes it the way it heard it), and every job,
finding, approval and precedent result gets a stable ``id`` (:func:`_assign_ids`)
the browser keys its rows by — the model is never asked to invent one.
"""

from __future__ import annotations

from typing import Any, Literal

from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel, Field
from voqalize_demos import DEFAULT_MODEL, GeminiBrain, ScreenState, screen_prose

from voqalize.sdk import Action, RTVIMessage, Session
from voqalize.sdk.wire import Config, Language, SttConfig, TtsConfig, Voice

from .app_events import (
    SERVICING_EVENTS,
    ApprovalDecided,
    BoardFiltered,
    BoardOpened,
    CaseOpened,
    CaseRouted,
    NoteAdded,
    PacketSubmitted,
    SearchDismissed,
    ServicingEvent,
    TabOpened,
)

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

KNOW WHERE THE ADVISOR IS ("voice also"). Nothing in this conversation is a picture of the console. get_advisor_context() is the only one, and it is free and silent — it takes no floor, says nothing, and moves nothing. Call it before you reference or act on anything on screen, and whenever you are told the advisor moved it themselves — you are told THAT they moved it, never what it now says. Ground your answer in what it returns (e.g. "I see you're on Cho's pricing tab — his rate is seven-point-one percent"). If a tool refuses because the console moved under you, that is not something to report or apologise for: read it and make the call again. Voice augments the screen; it does not replace it.

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


# ─── Nested shapes (not Actions themselves — embedded inside one) ───────────


class JobSpec(BaseModel):
    """One background prep step of a ``prepare_case`` workup."""

    id: str = Field("", description="Assigned automatically; never set this.")
    label: str = Field(description="Short label of the background step, e.g. 'Pull payoff figure'.")
    detail: str = Field(
        "",
        description=(
            "One short line of the result the step produces, e.g. 'Payoff 284,900 + "
            "1,210 accrued interest'. Shown when the step finishes."
        ),
    )


class FindingSpec(BaseModel):
    """One line of the desk's "workup" — the cross-system assembly/reconciliation legwork."""

    id: str = Field("", description="Assigned automatically; never set this.")
    label: str = Field(description="What was checked, e.g. 'Payoff reconciliation'.")
    value: str = Field(
        description=(
            "The assembled/reconciled result, e.g. 'Net payoff 286,400 (a payment "
            "posted yesterday wasn't applied)'."
        )
    )
    flag: Literal["ok", "warn", "info"] = Field(
        "ok",
        description="'warn' for a reconciliation the advisor would likely have missed; 'ok' otherwise.",
    )


class BlockerSpec(BaseModel):
    """A risk the workup caught that gates a regulated step — the thing nav never surfaces."""

    title: str = Field(description="Short headline, e.g. 'Open second lien on the property'.")
    detail: str = Field(
        description=(
            "One or two lines on what it is and why it blocks, e.g. 'A 2021 "
            "home-equity line is still open — releasing the title now is a "
            "compliance exception.'"
        )
    )
    severity: Literal["block", "warn"] = Field(
        description="'block' = a regulated step cannot proceed until cleared; 'warn' = caution only."
    )
    suggested_route: str = Field(
        "", description="Department to route to in order to clear it, e.g. 'Legal & Custody'."
    )


class PacketFieldSpec(BaseModel):
    """A field/section of a regulated packet (multi-step form) the desk fills."""

    label: str = Field(description="Field name, e.g. 'Payoff date'.")
    value: str = Field(description="Field value, e.g. '30 June 2026' or '286,400'.")
    mono: bool = Field(False, description="True for figures/ids shown in monospace.")


class PacketSectionSpec(BaseModel):
    id: str = Field("", description="Short id, e.g. 'payoff', 'release', 'escrow'.")
    title: str = Field(description="Section title, e.g. 'Payoff figures'.")
    fields: list[PacketFieldSpec] = Field(default_factory=list)
    blocked: bool = Field(
        False,
        description=(
            "True if this section is locked by a blocker (e.g. the document-release "
            "section while a lien is open)."
        ),
    )
    blocked_reason: str = Field("", description="If blocked, one short line why.")


class PacketSpec(BaseModel):
    id: str = Field("", description="Short id, e.g. 'closure'.")
    title: str = Field(description="Packet title, e.g. 'Early-closure packet'.")
    summary: str = Field("", description="One line on what this packet does.")
    sections: list[PacketSectionSpec] = Field(
        default_factory=list,
        description="The form sections (e.g. payoff figures, document release, escrow disposition).",
    )


class ApprovalSpec(BaseModel):
    """A draft item dropped into the advisor's 'Needs your approval' queue."""

    id: str = Field("", description="Assigned automatically; never set this.")
    title: str = Field(
        description="Draft title, e.g. 'Settlement letter' or 'Early-closure fee waiver'."
    )
    kind: Literal[
        "settlement_letter",
        "fee_waiver",
        "rate_offer",
        "document_release",
        "escrow_change",
        "other",
    ] = Field("other", description="Category of the draft (drives the icon shown).")
    summary: str = Field(description="One-line summary of what the advisor is approving.")
    lines: list[str] = Field(
        default_factory=list,
        description="A few short detail lines shown on the draft card (figures, terms).",
    )
    amount: float | None = Field(
        None,
        description="Headline dollar amount if relevant (payoff total, fee waived, new payment).",
    )
    recommendation: str = Field(
        "",
        description=(
            "Your brief recommendation + reason for the advisor, e.g. 'Recommend "
            "waiving — 12-year customer in good standing'. Empty if none."
        ),
    )
    blocked: bool = Field(
        False,
        description=(
            "True if this draft CANNOT be approved yet because the workup caught a "
            "blocker (e.g. a document-release that's blocked by an open lien). It "
            "shows locked until the blocker is cleared."
        ),
    )
    blocked_reason: str = Field(
        "", description="If blocked, one short line why, e.g. 'Open second lien must clear first'."
    )


class PrecedentSpec(BaseModel):
    """A past (archived) case returned by the server-side precedent search."""

    id: str = Field("", description="Assigned automatically; never set this.")
    ref: str = Field(description="Archive case reference, e.g. 'MS-0907'.")
    customer: str = Field("", description="Customer name on the past case.")
    summary: str = Field("", description="One line on what the past case was.")
    resolution: str = Field(
        description="How it was handled/resolved, e.g. 'Legal subordinated the HELOC; title released after.'"
    )
    days: float | None = Field(None, description="How many days it took to resolve, if relevant.")


# ─── Actions — each one IS the parameter of the tool that dispatches it ─────


class OpenBoard(Action):
    """Show the advisor's case board (the worklist of all their cases). No fields."""


class OpenCase(Action):
    ref: str = Field(description="Case reference, e.g. 'MS-1042'.")


class SetTab(Action):
    tab: Literal["overview", "payments", "documents", "activity"] = Field(
        description="Which tab of the open case to show."
    )


class AssignCase(Action):
    ref: str = Field(description="Case reference, e.g. 'MS-1057'.")
    assignee_kind: Literal["person", "department"] = Field(
        description="Whether routing to a teammate or a department queue."
    )
    assignee: str = Field(
        description=(
            "The person's name (e.g. 'Marcus Bell') or department key: one of "
            "pricing, closures, legal, insurance, compliance."
        )
    )


class MoveCase(Action):
    ref: str = Field(description="Case reference.")
    stage: Literal["new", "in_progress", "needs_approval", "with_dept", "done"] = Field(
        description="Target stage column."
    )


class AddComment(Action):
    ref: str = Field(description="Case reference, e.g. 'MS-1057'.")
    text: str = Field(description="The note text — a sentence or two of context for the case.")
    dept: str = Field(
        "",
        description=(
            "Optional department this note is about (one of pricing, closures, legal, "
            "insurance, compliance). Tags the note; omit if it's a general note."
        ),
    )


class PrepareCase(Action):
    ref: str = Field(description="Case reference to prepare, e.g. 'MS-1057'.")
    summary: str = Field("", description="One-line summary of what you're preparing for this case.")
    jobs: list[JobSpec] = Field(
        description="The background prep steps (usually 3-4). They animate to completion."
    )
    findings: list[FindingSpec] = Field(
        default_factory=list,
        description=(
            "The workup result — the cross-system facts you assembled and figures you "
            "reconciled (payoff, accrued interest, escrow, in-flight payments). Flag "
            "the ones the advisor would likely have missed with 'warn'."
        ),
    )
    blocker: BlockerSpec | None = Field(
        None,
        description=(
            "The one risk you caught that gates a regulated step — the thing the "
            "advisor wouldn't have known to look for (e.g. an open second lien before "
            "a title release). Omit if the case is clean."
        ),
    )
    packet: PacketSpec | None = Field(
        None,
        description=(
            "The regulated packet (multi-step form) you filled from the workup, e.g. "
            "an early-closure packet with payoff figures, document-release, escrow "
            "sections. Mark the section a blocker gates with blocked:true. Omit if not "
            "relevant."
        ),
    )
    approvals: list[ApprovalSpec] = Field(
        default_factory=list,
        description=(
            "The draft items to reveal for the advisor's approval once prep finishes "
            "(settlement letter, fee waiver, document release, etc.). If a blocker "
            "gates one (e.g. document release), set blocked:true on it."
        ),
    )


class PostWorkup(Action):
    ref: str = Field(description="Case reference, e.g. 'MS-1042'.")
    findings: list[FindingSpec] = Field(
        description="The facts/reconciliations you assembled for this case."
    )
    blocker: BlockerSpec | None = Field(
        None, description="A risk you caught that needs attention. Omit if the case is clean."
    )


class LookupPrecedent(Action):
    query: str = Field(
        description="What you're searching for, e.g. 'early closure with an open second lien'."
    )
    results: list[PrecedentSpec] = Field(
        description="The 2-3 most relevant past cases, each with how it was resolved."
    )


class UpdatePacketField(Action):
    ref: str = Field(description="Case reference.")
    section: str = Field(description="Section id or title to edit, e.g. 'payoff'.")
    field: str = Field(description="Field label to set, e.g. 'Payoff date'.")
    value: str = Field(description="The new value.")
    note: str = Field("", description="Optional one-line activity note.")


class ResolveBlocker(Action):
    ref: str = Field(description="Case reference.")
    note: str = Field(
        "", description="What cleared it, e.g. 'Legal subordinated the home-equity line'."
    )


class SubmitPacket(Action):
    ref: str = Field(description="Case reference whose packet to submit.")


class DraftApproval(Action):
    ref: str = Field(description="Case reference.")
    approval: ApprovalSpec = Field(description="The draft to add.")


class Highlight(Action):
    section: Literal[
        "summary", "loan", "payments", "documents", "approvals", "notes", "activity"
    ] = Field(description="Which section to highlight.")


def _assign_ids(items: list[Any], prefix: str) -> None:
    """Give every item missing a stable ``id`` one (``{prefix}{n}``), in place —
    the model is never asked to invent one, but the browser keys its rows by it."""
    for i, item in enumerate(items):
        if not item.id.strip():
            item.id = f"{prefix}{i + 1}"


type ScreenMove = (
    OpenBoard
    | OpenCase
    | SetTab
    | AssignCase
    | MoveCase
    | AddComment
    | PrepareCase
    | PostWorkup
    | LookupPrecedent
    | UpdatePacketField
    | ResolveBlocker
    | SubmitPacket
    | DraftApproval
    | Highlight
)
"""Every command that moves the advisor's console.

Narrower than ``Action`` on purpose: :meth:`ServicingBrain._mirror` matches on
this, so a fifteenth command added and not mirrored is a type error rather than a
picture that has quietly stopped agreeing with the screen."""


def _find(rows: list[Any], ref: str) -> dict[str, Any] | None:
    """The case row for ``ref``, or ``None`` — refs are the console's own ids."""
    wanted = ref.strip().upper()
    for row in rows:
        if isinstance(row, dict) and str(row.get("ref", "")).upper() == wanted:
            return row  # pyright: ignore[reportUnknownVariableType]
    return None


def _blank_workspace() -> dict[str, Any]:
    return {
        "the view they are on": "board",
        "the tab": "overview",
        "the board filter": "all",
        "the open case": None,
        "the cases": [],
        "the last precedent search": None,
    }


class ServicingBrain(GeminiBrain):
    """One per session. The Meridian Servicing Console copilot: LLM + case/board
    screen-driving tools + this session's advisor + live workspace state."""

    def __init__(self, *, client: genai.Client, model: str = DEFAULT_MODEL) -> None:
        super().__init__(client=client, system_instruction=_SYSTEM_INSTRUCTION, model=model)
        # Advisor identity, filled for real in on_session_start from the init payload.
        self.advisor_name = "there"
        self.advisor_role = "Servicing Advisor"
        # What is on the advisor's console. This is the only copy: it is read
        # through ``get_advisor_context`` and never appended to the model's context.
        self.screen = ScreenState(read_tool="get_advisor_context", actor="advisor")
        #: The desk's own picture of the console — seeded from ``session.init``,
        #: patched by :meth:`_mirror` and :meth:`apply_event`.
        self.workspace = _blank_workspace()

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        payload = dict(session.init or {})
        raw_advisor = payload.get("advisor")
        advisor = raw_advisor if isinstance(raw_advisor, dict) else {}
        self.advisor_name = str(advisor.get("name") or "").strip() or "there"
        self.advisor_role = str(advisor.get("role") or "").strip() or "Servicing Advisor"
        # The board the advisor logged in to. It rides ``init`` because the console
        # already has it — there is nothing to be gained by having the browser
        # hand back, over the wire, the worklist it was itself given.
        raw_cases = payload.get("cases")
        self.workspace = _blank_workspace() | {
            "the cases": [c for c in raw_cases if isinstance(c, dict)]
            if isinstance(raw_cases, list)
            else []
        }
        # The desk's own voice — settled here rather than sent with the connect
        # request, since this is an internal console with no user to ask.
        await session.configure(
            Config(
                stt=SttConfig(language=Language.EN),
                tts=TtsConfig(voice=Voice.OMNIVOICE_GAURI, language=Language.EN),
            )
        )
        logger.info("servicing: session start — advisor={!r}", self.advisor_name)

    async def greet(self, session: Session) -> str:
        """The opener, written not generated: the advisor is already logged in, so
        the desk greets the instant the session connects — no LLM call, no
        first-token wait. It does not say the advisor's name — that arrives as
        free text in session.init, ahead of any model to judge it."""
        return f"Hi there — {DESK_NAME} here. What would you like to start on?"

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Browser→brain message: one thing the advisor just did on the console.

        Silent by construction — the picture moves and one line goes into the
        context, but no floor is taken and no turn starts. Nothing about a click
        means he stopped talking."""
        event = SERVICING_EVENTS.parse(msg)
        if event is None:
            return
        logger.info("servicing: {} — {}", type(event).__voqal_event__, event)
        note = self.apply_event(event)
        self.append_to_context(types.Content(role="user", parts=[types.Part(text=note)]))

    # ─── Browser → brain: what the advisor did himself ──────────────────

    def apply_event(self, event: ServicingEvent) -> str:
        """Fold one gesture into the picture and say what to tell the model.

        The note names the act and never its values — the case behind it is read
        through ``get_advisor_context``, which is what keeps it from going stale in
        the context. No fallback arm: a gesture added to :data:`ServicingEvent` and
        not handled here is a type error rather than a silent drop."""
        rows = self.workspace["the cases"]
        match event:
            case BoardOpened():
                self.workspace["the view they are on"] = "board"
                self.workspace["the open case"] = None
                return self.screen.moved("went back to the case board")
            case CaseOpened():
                ref = event.ref.strip().upper()
                self.workspace["the view they are on"] = "case"
                self.workspace["the open case"] = ref
                self.workspace["the tab"] = "overview"
                return self.screen.moved(f"opened {ref} himself")
            case TabOpened():
                self.workspace["the tab"] = event.tab
                return self.screen.moved(f"switched to the {event.tab} tab")
            case BoardFiltered():
                self.workspace["the view they are on"] = "board"
                self.workspace["the board filter"] = event.showing
                return self.screen.moved(f"filtered the board to {event.showing}")
            case CaseRouted():
                ref = event.ref.strip().upper()
                if (row := _find(rows, ref)) is not None:
                    row["assignee"] = event.to
                    if row.get("stage") != "done":
                        row["stage"] = "with_dept"
                return self.screen.moved(f"routed {ref} to another queue himself")
            case NoteAdded():
                ref = event.ref.strip().upper()
                if (row := _find(rows, ref)) is not None:
                    row.setdefault("notes", []).append(
                        {"author": self.advisor_name, "text": event.text}
                    )
                    if event.dept and row.get("stage") != "done":
                        row["stage"] = "with_dept"
                return self.screen.moved(f"wrote a note on {ref}")
            case ApprovalDecided():
                ref = event.ref.strip().upper()
                if (row := _find(rows, ref)) is not None:
                    pending = row.get("pending_approvals") or []
                    row["pending_approvals"] = [t for t in pending if t != event.title]
                    row.setdefault("signed off", []).append(f"{event.decision}: {event.title}")
                return self.screen.moved(
                    f"{event.decision} a draft on {ref} himself — his call, never yours"
                )
            case PacketSubmitted():
                ref = event.ref.strip().upper()
                if (row := _find(rows, ref)) is not None:
                    if isinstance(packet := row.get("packet"), dict):
                        packet["status"] = "submitted"
                    row["stage"] = "with_dept"
                return self.screen.moved(f"submitted the packet on {ref} himself")
            case SearchDismissed():
                self.workspace["the last precedent search"] = None
                return self.screen.moved("closed the precedent search")

    def _show(self, action: ScreenMove) -> None:
        """Put something on screen — and into the picture, in the same breath.

        Nothing comes back to say a command landed, and nothing needs to. That is
        also why a gesture can be taken at face value: an event is always the
        advisor, never this brain's own command echoing home."""
        self._mirror(action)
        self.session.dispatch(action)

    def _mirror(self, action: ScreenMove) -> None:
        """Move the picture the way this dispatch is about to move the console."""
        rows = self.workspace["the cases"]
        match action:
            case OpenBoard():
                self.workspace["the view they are on"] = "board"
                self.workspace["the open case"] = None
            case OpenCase():
                self.workspace["the view they are on"] = "case"
                self.workspace["the open case"] = action.ref
                self.workspace["the tab"] = "overview"
            case SetTab():
                self.workspace["the tab"] = action.tab
            case AssignCase():
                if (row := _find(rows, action.ref)) is not None:
                    row["assignee"] = DEPARTMENTS.get(action.assignee.lower(), action.assignee)
                    if action.assignee_kind == "department" and row.get("stage") != "done":
                        row["stage"] = "with_dept"
            case MoveCase():
                if (row := _find(rows, action.ref)) is not None:
                    row["stage"] = action.stage
            case AddComment():
                if (row := _find(rows, action.ref)) is not None:
                    row.setdefault("notes", []).append(
                        {"author": "Servicing desk", "text": action.text}
                    )
            case PrepareCase():
                if (row := _find(rows, action.ref)) is not None:
                    row["findings"] = [f.label for f in action.findings]
                    row["blocker"] = (
                        {"title": action.blocker.title, "status": "open"}
                        if action.blocker
                        else None
                    )
                    if action.packet is not None:
                        row["packet"] = {"title": action.packet.title, "status": "draft"}
                    row["pending_approvals"] = [a.title for a in action.approvals]
            case PostWorkup():
                if (row := _find(rows, action.ref)) is not None:
                    row["findings"] = [f.label for f in action.findings]
                    if action.blocker is not None:
                        row["blocker"] = {"title": action.blocker.title, "status": "open"}
            case LookupPrecedent():
                self.workspace["the last precedent search"] = {
                    "query": action.query,
                    "results": len(action.results),
                }
            case UpdatePacketField():
                row = _find(rows, action.ref)
                if row is not None and isinstance(packet := row.get("packet"), dict):
                    packet.setdefault("fields set", []).append(action.field)
            case ResolveBlocker():
                row = _find(rows, action.ref)
                if row is not None and isinstance(blocker := row.get("blocker"), dict):
                    blocker["status"] = "resolved"
            case SubmitPacket():
                # The console gates this one itself (maker-checker), so the
                # picture only records that it was asked for.
                row = _find(rows, action.ref)
                if row is not None and isinstance(packet := row.get("packet"), dict):
                    packet["status"] = "submitting"
            case DraftApproval():
                if (row := _find(rows, action.ref)) is not None:
                    row.setdefault("pending_approvals", []).append(action.approval.title)
            case Highlight():
                # Where the eye is pointed, not what anyone decided.
                pass

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        """The fifteen the advisor's desk may call."""
        return [
            self.open_board,
            self.open_case,
            self.set_tab,
            self.get_advisor_context,
            self.assign_case,
            self.move_case,
            self.add_comment,
            self.prepare_case,
            self.post_workup,
            self.lookup_precedent,
            self.update_packet_field,
            self.resolve_blocker,
            self.submit_packet,
            self.draft_approval,
            self.highlight,
        ]

    async def open_board(self) -> str:
        """Show the advisor's case board (the worklist of all their cases)."""
        self._show(OpenBoard())
        return "board open"

    async def open_case(self, action: OpenCase) -> str:
        """Open a case by its reference and make it the active case on screen.
        Use when the advisor says 'open Cho's case' or 'pull up MS-1057'."""
        action.ref = action.ref.strip().upper()
        self._show(action)
        return f"opened {action.ref}"

    async def set_tab(self, action: SetTab) -> str:
        """Switch the tab within the open case so the advisor sees the right panel."""
        self._show(action)
        return f"showing {action.tab}"

    async def get_advisor_context(self) -> str:
        """Read where the advisor is right now — which case and tab is on screen,
        that case in full, the board, and any pending approvals.

        Call it before you reference or act on anything on screen, and whenever you
        are told the advisor moved it themselves. It is free — it reads this
        session's own state, takes no floor, says nothing, and moves nothing."""
        self.screen.read()
        logger.info("servicing: get_advisor_context (v{})", self.screen.version)
        rows = self.workspace["the cases"]
        ref = self.workspace["the open case"]
        where = {
            "screen": self.workspace["the view they are on"],
            **self.workspace,
            "the open case": _find(rows, ref) if isinstance(ref, str) else None,
        }
        return screen_prose(where, actor="advisor")

    async def assign_case(self, action: AssignCase) -> str:
        """Route a case to a person or a department (Jira-style assignment). Use
        when the advisor says 'assign it to <person>' or 'send it to
        <department>'. Assigning to a department moves the card to the 'with
        department' stage."""
        action.ref = action.ref.strip().upper()
        self._show(action)
        label = (
            DEPARTMENTS.get(action.assignee.lower(), action.assignee)
            if action.assignee_kind == "department"
            else action.assignee
        )
        return f"assigned {action.ref} to {label}"

    async def move_case(self, action: MoveCase) -> str:
        """Move a case card to a different stage on the board."""
        stale = self.screen.stale()
        if stale:
            return stale
        action.ref = action.ref.strip().upper()
        self._show(action)
        return f"moved {action.ref} to {action.stage}"

    async def add_comment(self, action: AddComment) -> str:
        """Leave an authored note on a case — handoff context the next desk
        needs. Use when the advisor says 'make a note that…', 'add a comment…',
        or when you route a case to another department and want to capture WHY
        so the receiving team has the context. If the note accompanies a
        routing, pass the department in 'dept' (it tags the note; route
        separately with assign_case if the case should actually move). Notes are
        not approvals — they are free-text context."""
        action.ref = action.ref.strip().upper()
        action.dept = action.dept.strip().lower()
        if not action.ref or not action.text.strip():
            return "need a case ref and note text"
        self._show(action)
        dept_label = DEPARTMENTS.get(action.dept, action.dept) or None
        return f"noted on {action.ref}" + (f" ({dept_label})" if dept_label else "")

    async def prepare_case(self, action: PrepareCase) -> str:
        """Run a full WORKUP on a case IN THE BACKGROUND while the advisor stays
        on whatever they have open. Kicks off the listed prep jobs (which run
        and complete on their own) and, when they finish, reveals everything at
        once: your findings (the cross-system assembly + reconciliations), any
        blocker you caught, the regulated packet you filled, and the drafts in
        the 'Needs your approval' queue. Use this for a case the advisor asks
        you to 'get ready' / 'take' / 'work up' — never pull them off their
        current screen for it. This is the heavy lifting: do the legwork they'd
        otherwise do by hand."""
        action.ref = action.ref.strip().upper()
        if not action.ref or not action.jobs:
            return "need a case ref and at least one job"
        _assign_ids(action.jobs, "j")
        _assign_ids(action.findings, "f")
        _assign_ids(action.approvals, "a")
        self._show(action)
        blocker_note = f"; blocker: {action.blocker.title}" if action.blocker else ""
        return (
            f"preparing {action.ref} in the background{blocker_note} — tell the advisor when ready"
        )

    async def post_workup(self, action: PostWorkup) -> str:
        """Attach a workup to the case the advisor has OPEN ON SCREEN right now
        (no background animation) — the findings you assembled and any blocker
        you caught. Use this when you are co-working a case with the advisor
        and want to show your reconciliation (e.g. Cho's true net saving after
        fees, or an eligibility flag) immediately."""
        action.ref = action.ref.strip().upper()
        if not action.ref or not action.findings:
            return "need a case ref and at least one finding"
        _assign_ids(action.findings, "f")
        self._show(action)
        blocker_note = f"; blocker: {action.blocker.title}" if action.blocker else ""
        return f"workup posted on {action.ref}{blocker_note}"

    async def lookup_precedent(self, action: LookupPrecedent) -> str:
        """Search the case ARCHIVE (closed/past cases, not in the advisor's
        current queue) for precedent — how the team handled a similar situation
        before. Use when the advisor asks 'have we done this before?' / 'how
        did we handle X?'. This is a server-side lookup that reaches beyond
        what's on screen. Generate 2-3 believable past cases."""
        _assign_ids(action.results, "p")
        self._show(action)
        return f"searched the archive — {len(action.results)} precedent(s) found"

    async def update_packet_field(self, action: UpdatePacketField) -> str:
        """Change one field of a case's packet (form) — e.g. when the advisor
        says 'set the payoff date to month-end'. Pass the recomputed value
        yourself (regenerate any figure that depends on it, like accrued
        interest, and update those fields too)."""
        action.ref = action.ref.strip().upper()
        stale = self.screen.stale()
        if stale:
            return stale
        if not action.ref or not action.section.strip() or not action.field.strip():
            return "need ref, section and field"
        self._show(action)
        return f"set {action.field} to {action.value!r} on {action.ref}"

    async def resolve_blocker(self, action: ResolveBlocker) -> str:
        """Mark a case's blocker as cleared — e.g. once you confirm Legal has
        subordinated the lien. This unlocks any draft or packet section the
        blocker was gating so the advisor can approve and submit. Only call
        this when the blocking issue is genuinely resolved."""
        action.ref = action.ref.strip().upper()
        stale = self.screen.stale()
        if stale:
            return stale
        if not action.ref:
            return "need a case ref"
        self._show(action)
        return f"blocker cleared on {action.ref}"

    async def submit_packet(self, action: SubmitPacket) -> str:
        """Submit a case's regulated packet to the handling department (a
        server-side action with consequences). Maker-checker: this only goes
        through AFTER the advisor has approved the drafts and any blocker is
        cleared — if something is still pending or blocked, the submission is
        refused. Confirm the advisor wants to submit before calling."""
        action.ref = action.ref.strip().upper()
        stale = self.screen.stale()
        if stale:
            return stale
        if not action.ref:
            return "need a case ref"
        self._show(action)
        return (
            f"submit requested for {action.ref} — the console will only submit if "
            "the advisor has approved the drafts and no blocker is open"
        )

    async def draft_approval(self, action: DraftApproval) -> str:
        """Drop a single draft into a case's 'Needs your approval' queue
        immediately — for a case you are co-working on screen with the advisor
        (e.g. a rate offer for Cho). The advisor approves or declines it. You
        never execute it yourself."""
        action.ref = action.ref.strip().upper()
        stale = self.screen.stale()
        if stale:
            return stale
        if not action.ref:
            return "need a case ref"
        _assign_ids([action.approval], "a")
        self._show(action)
        return f"drafted '{action.approval.title}' for approval on {action.ref}"

    async def highlight(self, action: Highlight) -> str:
        """Scroll to and briefly highlight one section of the open case so the
        advisor's eye follows you."""
        self._show(action)
        return f"highlighted {action.section}"
