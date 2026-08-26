"""ForgeBrain — "Ada", the Flowforge workflow copilot.

A :class:`voqalize.sdk.gemini.GeminiBrain` for the voice **workflow studio**: an
ITSM/HR-ops admin assembles a Service Request Workflow — a block-based
statechart over a typed context — by talking to Ada, and Ada drives the studio
screen as she talks.

Two things worth calling out about how per-session state flows in:

  * **init** — just the admin's name (``session.init["admin"]["name"]``), folded
    into the opening greeting. :meth:`ForgeBrain.greet` is written, not
    generated: the admin already tapped in, so there is no first-token wait.
  * **state_sync** — the studio is the source of truth for the open workflow; it
    echoes a compact ``state_sync`` snapshot (the open workflow, its blocks WITH
    THEIR IDS, tests, and gaps) on every change. :meth:`ForgeBrain.on_rtvi`
    folds it in *silently* — no floor taken, no turn — so the next turn edits
    against the real on-screen ids.

**Twenty-one of twenty-one tools dispatch an** :class:`~voqalize.sdk.Action`
**that IS the tool's own parameter** — Ada never free-generates infrastructure,
so every edit the model proposes is already the exact shape the studio store
applies, and the tool body is one ``self.session.dispatch(action)`` line.
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

_SYSTEM_INSTRUCTION = """You are Ada, the Flowforge workflow copilot — a voice assistant for an ITSM / HR-ops administrator who builds "Service Request Workflows" by talking to you. You DRIVE THEIR SCREEN as you talk.

VOICE STYLE — SAY LESS, DO MORE. You are watched, not just heard: the admin SEES the studio change as you work, so let the screen do the talking. This discipline matters more than anything else here.
- Lead with the action. Say one short clause — ideally just naming what you're about to do, 3 to 8 words — then CALL THE TOOL. E.g. "Adding a security review." then the tool. Never narrate in silence; never call a tool without that brief lead-in.
- Don't describe what's now on screen. The admin can see the new step, the passing tests, the lit path, the code. No recaps, no "I've added…", never read ids, labels, guards, JSON, or lists aloud. Every tool you call also shows up as a live task on screen (a small "activity" checklist), so your actions are already acknowledged visually — trust it and stay quiet.
- Chain tools to finish a real change in one go — insert the decision, wire both branches, add the step — then ONE short line at the end. Don't stop to announce every edit.
- Ask a question ONLY when genuinely blocked by a real fork the admin must decide. Otherwise pick the sensible default, do it, and let them correct you.
- Spoken English, short sentences, no markdown or symbols.

WHAT A WORKFLOW IS: a block-based statechart. Each workflow has a typed CONTEXT (the request's data) and STATES (blocks) wired by transitions. You ASSEMBLE it from a governed catalog — you never free-generate infrastructure. Block kinds:
- start: the trigger. form: collect fields. approval: a person approves or rejects. service: call ONE connector action. gateway: an exclusive branch on guards. wait: an SLA/timer. code: a JavaScript escape hatch. end: a terminal outcome.

CONNECTOR CATALOG (use these connector_id · action_id):
- entra (Microsoft Entra ID): create_user, disable_user, add_to_group, revoke_sessions
- intune: assign_device, wipe_device, expedite_ship
- okta: provision_app, deprovision_app
- jira: create_issue, transition_issue
- servicenow: create_incident, update_record
- workday: get_worker, update_worker
- github: add_seat, remove_seat
- teams / slack: notify (teams also post_approval)
- docusign: send_envelope
- zoom: schedule_meeting

CODE IS JAVASCRIPT. Guards and code blocks are JavaScript over `ctx` (the context object). Context keys are dotted and nest: `requester.type` reads `ctx.requester.type`; `hire.department` reads `ctx.hire.department`. Derived fields are flat: the access-request workflow has `privilegedApp`, read as `ctx.privilegedApp`. A guard is a JS expression, e.g. `ctx.requester.type === 'contractor' && ctx.privilegedApp`. A code block is JS statements that end with `return ctx;`. Use show_code to reveal the JavaScript behind a decision or a code step when the rigor is worth seeing — but let it show; don't read it aloud.

ROUTING: an approval's `next` is its approve path and `reject_to` is its reject path. A gateway has ordered `branches` (each a guard + target) and an `otherwise` default. To add a branch to an existing linear flow, use insert_gateway(after: <stateId>) — the block that came next becomes the default path automatically; point a branch at a new block that eventually rejoins the flow.

TESTS are the admin's mental model: "the workflow is in {given_state}, {event} occurs, expect {expect_state}". Events by kind — form: submit/cancel; approval: approve/reject/timeout/withdrawn; wait: elapsed/cancelled. Add tests with add_test, then run_tests. The runner executes the real JS guards — the results appear on screen, so don't recite them.

HANDLING EDGE CASES (the core demo loop): review_coverage surfaces the unhandled (state, event) pairs — the gaps — on screen. For each gap the admin wants closed: WIRE A REAL HANDLER (a reject route via set_route, a new step via add_state, a branch via insert_gateway, or a code block via set_code), THEN call resolve_gap to clear it. Prove it with add_test + run_tests. This loop — surface the gap, handle it, resolve it, test it — is the heart of the demo.

PUBLISH: publish_workflow makes the open version live. Say it plainly and briefly — e.g. "Publishing now." — and let the Live panel show it. The story if asked: runs are DURABLE — a request mid-approval keeps its place through any restart, and every step runs exactly once. Never name a specific engine or vendor.

THE FINALE — run_scenario: walk a persona through the live flow from the trigger. Pass persona_label, a context JSON string, and the ordered events the persona fires (e.g. approvals). The screen lights the whole path. Great for proving an edit works, e.g. a contractor requesting a privileged app taking the new security branch.

GROUNDING: a CURRENT WORKSPACE STATE snapshot is folded into your context every turn — it lists the open workflow, its blocks WITH THEIR IDS, tests, and gaps. Always use those real ids when you edit; call open_workflow first if none is open.

Open with a brief greeting and ask what they'd like to build or change."""


# The two closed vocabularies a field and its Action share. Declared once: the
# model picks from this list and the browser is typed against it, so the two
# cannot drift apart.
FieldType = Literal["string", "boolean", "number", "enum", "user"]
Category = Literal["ITSM", "HR", "Security"]


# ─── Nested shapes (not Actions themselves — embedded inside one) ───────────


class ContextFieldSpec(BaseModel):
    """One field in a new workflow's request context."""

    key: str = ""
    label: str = ""
    type: FieldType = "string"
    enum_values: list[str] = Field(default_factory=list)
    derived: bool = Field(False, description="True if computed from other fields by a JS expr.")
    expr: str = Field(
        "", description="JS expression for a derived field, e.g. ctx.app length check."
    )
    note: str = Field("", description="Provenance, e.g. 'from Entra ID'.")


class FormFieldSpec(BaseModel):
    """One field on a form block."""

    key: str = ""
    label: str = ""
    type: FieldType = "string"
    enum_values: list[str] = Field(default_factory=list)


class BranchSpec(BaseModel):
    """One guarded branch of a gateway."""

    label: str = Field("", description="Human summary, e.g. 'Contractor + privileged app'.")
    guard: str = Field("", description="JS expression over ctx, first truthy wins.")
    to: str = Field("", description="Target state id.")


# ─── Actions — each one IS the parameter of the tool that dispatches it ─────


class OpenList(Action):
    """Return to the list of all Service Request Workflows. No fields."""


class OpenWorkflow(Action):
    id: str


class CreateWorkflow(Action):
    id: str = Field("", description="Short kebab id, e.g. 'guest-wifi'. Auto-generated if omitted.")
    name: str
    description: str = ""
    category: Category = "ITSM"
    trigger: str = Field(description="How it starts, in plain words.")
    channels: list[str] = Field(default_factory=list)
    context: list[ContextFieldSpec] = Field(default_factory=list)


class AddState(Action):
    id: str = Field("", description="Optional stable id; auto if omitted.")
    after: str = Field("", description="Insert after this state id.")
    kind: Literal["form", "approval", "service", "wait", "code", "end"]
    label: str
    subtitle: str = ""
    connector_id: str = ""
    action_id: str = ""
    approver: str = Field("", description="e.g. 'Reporting manager', 'VP, Engineering'.")
    fields: list[FormFieldSpec] = Field(default_factory=list)
    code: str = Field("", description="JS body ending in 'return ctx;'.")
    sla_hours: int = 0
    next: str = ""
    reject_to: str = ""
    outcome: str = ""


class InsertGateway(Action):
    after: str
    id: str = ""
    label: str = ""
    subtitle: str = ""
    branches: list[BranchSpec]
    otherwise: str = Field("", description="Optional explicit default target id.")


class AddBranch(Action):
    gateway: str
    label: str = ""
    guard: str
    to: str


class SetRoute(Action):
    state: str
    next: str = ""
    reject_to: str = ""
    otherwise: str = ""


class UpdateState(Action):
    id: str
    label: str = ""
    subtitle: str = ""
    connector_id: str = ""
    action_id: str = ""
    approver: str = ""
    sla_hours: int = 0
    outcome: str = ""


class RemoveState(Action):
    id: str


class AddContextField(Action):
    key: str = Field(description="Dotted key, e.g. 'requester.type' or 'privilegedApp'.")
    label: str = ""
    type: FieldType
    enum_values: list[str] = Field(default_factory=list)
    derived: bool = Field(False, description="True if computed from other fields by a JS expr.")
    expr: str = Field(
        "", description="JS expression for a derived field, e.g. ctx.app length check."
    )
    note: str = Field("", description="Provenance, e.g. 'from Entra ID'.")


class AddField(Action):
    state: str
    field: FormFieldSpec


class SetCode(Action):
    state: str
    code: str


class AddTest(Action):
    name: str
    given_state: str
    event: str
    expect_state: str
    context: str = Field(
        "", description='JSON, e.g. {"requester.type":"contractor","app":"AWS Console"}.'
    )


class RunTests(Action):
    """Run all tests for the open workflow. No fields."""


class ReviewCoverage(Action):
    """Scan for unhandled (state, event) pairs. No fields."""


class ResolveGap(Action):
    id: str = Field("", description="The gap id, if known.")
    state: str = Field("", description="Gap's state id (with `event`) if no id.")
    event: str = Field("", description="Gap's event (with `state`) if no id.")


class RunScenario(Action):
    persona_label: str = Field(description="e.g. 'Contractor · AWS Console'.")
    context: str = Field("", description="JSON object of context values.")
    events: list[str] = Field(default_factory=list)


class PublishWorkflow(Action):
    """Publish the open workflow — makes this version live and durable. No fields."""


class SetPanel(Action):
    panel: Literal["flow", "code", "tests", "runtime"]


class FocusState(Action):
    id: str


class ShowCode(Action):
    id: str = Field(description="The state id whose code to reveal.")


class ForgeBrain(GeminiBrain):
    """One per session. Nearly stateless: the studio owns the workflow; Ada
    relays edits and grounds on the live ``state_sync`` snapshot every turn."""

    def __init__(self, *, client: genai.Client, model: str = DEFAULT_MODEL) -> None:
        super().__init__(client=client, system_instruction=_SYSTEM_INSTRUCTION, model=model)
        self.admin_name = "there"
        self.current_state: dict[str, Any] | None = None
        self._state_message: str | None = None

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        payload = dict(session.init or {})
        raw = payload.get("admin")
        admin = raw if isinstance(raw, dict) else {}
        self.admin_name = str(admin.get("name") or "").strip() or "there"
        # Ada's own voice — not the connecting page's to choose, so it is settled
        # here rather than sent with the connect request. `language` moves both
        # legs at once, and this lands before the greeting.
        await session.configure(
            Config(
                stt=SttConfig(language=Language.EN),
                tts=TtsConfig(voice=Voice.OMNIVOICE_GAURI, language=Language.EN),
            )
        )
        logger.info("forge: session start — admin={!r}", self.admin_name)

    async def greet(self, session: Session) -> str:
        """The opener, written not generated: the admin tapped in to build or
        change a workflow, so Ada says hello and hands them the floor. It does not
        say the admin's name — that arrives as free text in session.init, and this
        line is spoken before any model has run to judge it."""
        return "Hi there — Ada here. Want to open a workflow to change, or build a new one?"

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Browser→brain message. ``state_sync`` carries a compact snapshot of the
        studio's workspace — the open workflow, its blocks, tests, and gaps.
        Ingested *silently* (no floor taken, no turn); the next turn carries it
        as a note, so Ada always edits against the real on-screen ids."""
        if msg.type is not RTVIType.CLIENT_MESSAGE or not isinstance(msg.data, dict):
            return
        if msg.data.get("t") == "state_sync":
            self._ingest_state(msg.data.get("d") or {})

    # ─── Browser → brain: workspace state sync (silent awareness) ────────

    def _ingest_state(self, data: dict[str, Any]) -> None:
        """Put the latest workspace snapshot into the context, so the next turn
        edits against the real on-screen blocks and their ids.

        The studio re-sends the snapshot on every change, and many are the same
        workflow from Ada's point of view (a selection, a scroll). Only a
        changed snapshot is worth appending: the context is append-only, so an
        unguarded append here would put a hundred near-identical workspaces in
        front of the model by the end of a session.
        """
        snapshot = data.get("workspace")
        self.current_state = snapshot if isinstance(snapshot, dict) else None
        if self.current_state is None:
            message = "CURRENT WORKSPACE STATE: the studio is on the workflow list."
        else:
            try:
                blob = json.dumps(self.current_state, ensure_ascii=False)
            except (TypeError, ValueError):
                blob = str(self.current_state)
            message = (
                "CURRENT WORKSPACE STATE (authoritative — the open workflow with block ids, "
                "tests, and gaps; always edit against these ids): " + blob
            )
        if message == self._state_message:
            return
        self._state_message = message
        self.append_to_context(types.Content(role="user", parts=[types.Part(text=message)]))
        logger.info("forge: state_sync ingested (active={})", bool(self.current_state))

    # ─── Tools ──────────────────────────────────────────────────────────
    #
    # The model calls these directly. Twenty of the twenty-one take exactly the
    # Action they dispatch — Ada assembles from a governed catalog, never free
    # generates, so the model's arguments are already the studio's edit. Each
    # returns a short string; most just say "done" and let the screen speak.

    @property
    def tools(self) -> list[Any]:
        """The twenty-one Ada may call, read once per turn."""
        return [
            self.open_list,
            self.open_workflow,
            self.create_workflow,
            self.add_state,
            self.insert_gateway,
            self.add_branch,
            self.set_route,
            self.update_state,
            self.remove_state,
            self.add_context_field,
            self.add_field,
            self.set_code,
            self.add_test,
            self.run_tests,
            self.review_coverage,
            self.resolve_gap,
            self.run_scenario,
            self.publish_workflow,
            self.set_panel,
            self.focus_state,
            self.show_code,
        ]

    async def open_list(self) -> str:
        """Return to the list of all Service Request Workflows."""
        self.session.dispatch(OpenList())
        return "done"

    async def open_workflow(self, action: OpenWorkflow) -> str:
        """Open a workflow by id to edit it."""
        self.session.dispatch(action)
        return f"opened {action.id}"

    async def create_workflow(self, action: CreateWorkflow) -> str:
        """Author a NEW workflow from scratch — creates a draft with a trigger
        and an end, then build it up."""
        self.session.dispatch(action)
        return f"created draft '{action.name}'"

    async def add_state(self, action: AddState) -> str:
        """Add a block into the linear spine after `after` (rewires the flow).
        For service blocks pass connector_id+action_id; for approval pass
        approver; for form pass fields; for code pass code."""
        self.session.dispatch(action)
        return f"added {action.kind} '{action.label}'"

    async def insert_gateway(self, action: InsertGateway) -> str:
        """Splice an exclusive branch (gateway) in after `after`. The block that
        came next becomes the default path; each branch guards a route to
        another block."""
        self.session.dispatch(action)
        return "branch inserted"

    async def add_branch(self, action: AddBranch) -> str:
        """Append one guarded branch to an existing gateway."""
        self.session.dispatch(action)
        return "done"

    async def set_route(self, action: SetRoute) -> str:
        """Rewire a block's transitions."""
        self.session.dispatch(action)
        return "done"

    async def update_state(self, action: UpdateState) -> str:
        """Edit a block's label / connector / approver / SLA / outcome."""
        self.session.dispatch(action)
        return "done"

    async def remove_state(self, action: RemoveState) -> str:
        """Delete a block and heal the flow around it."""
        self.session.dispatch(action)
        return "done"

    async def add_context_field(self, action: AddContextField) -> str:
        """Add a field to the request context. Set derived+expr for a
        JS-computed field."""
        self.session.dispatch(action)
        return "done"

    async def add_field(self, action: AddField) -> str:
        """Add one field to a form block."""
        self.session.dispatch(action)
        return "done"

    async def set_code(self, action: SetCode) -> str:
        """Set the JavaScript on a code block (the escape hatch)."""
        self.session.dispatch(action)
        return "done"

    async def add_test(self, action: AddTest) -> str:
        """Add a transition test: in given_state, on event, expect expect_state.
        `context` is a JSON object string of field values."""
        self.session.dispatch(action)
        return "done"

    async def run_tests(self) -> str:
        """Run all tests for the open workflow (executes the real JS guards)."""
        self.session.dispatch(RunTests())
        return "tests running on screen"

    async def review_coverage(self) -> str:
        """Scan for unhandled (state, event) pairs and surface them as gap
        questions."""
        self.session.dispatch(ReviewCoverage())
        return "coverage scanned — the gaps are on screen"

    async def resolve_gap(self, action: ResolveGap) -> str:
        """Mark a coverage gap handled AFTER you've wired a real handler for it
        (a route, step, branch, or code block). Identify it by its id, or by
        the state+event pair it flagged."""
        self.session.dispatch(action)
        return "gap cleared"

    async def run_scenario(self, action: RunScenario) -> str:
        """THE FINALE: walk a persona through the live flow from the trigger,
        lighting the path. `context` is a JSON object string; `events` are the
        ordered events the persona fires."""
        self.session.dispatch(action)
        return f"walking {action.persona_label or 'the persona'} through the flow"

    async def publish_workflow(self) -> str:
        """Publish the open workflow — makes this version live and durable."""
        self.session.dispatch(PublishWorkflow())
        return "published — now live and durable"

    async def set_panel(self, action: SetPanel) -> str:
        """Switch the right panel."""
        self.session.dispatch(action)
        return "done"

    async def focus_state(self, action: FocusState) -> str:
        """Highlight/select one block on screen."""
        self.session.dispatch(action)
        return "done"

    async def show_code(self, action: ShowCode) -> str:
        """Open the Code panel and reveal the JavaScript behind one block (a
        decision's guards or a code step). Show the rigor; don't read it
        aloud."""
        self.session.dispatch(action)
        return "done"
