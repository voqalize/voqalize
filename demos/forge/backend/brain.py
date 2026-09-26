"""ForgeBrain — "Ada", the Flowforge workflow copilot.

A :class:`voqalize.sdk.gemini.GeminiBrain` for the voice **workflow studio**: an
ITSM/HR-ops admin assembles a Service Request Workflow — a block-based
statechart over a typed context — by talking to Ada, and Ada drives the studio
screen as she talks.

Worth calling out, about how per-session state flows in:

  * **init** — just the admin's name (``session.init["admin"]["name"]``), folded
    into the opening greeting. :meth:`ForgeBrain.greet` is written, not
    generated: the admin already tapped in, so there is no first-token wait.
  * **the studio** — Ada keeps her own picture of the workflow. It is built from
    ``session.init["workflows"]`` (the catalog arrives with the admin, before the
    first word), patched on every edit she dispatches, and patched again on each
    thing that happens in the studio she did not do — see ``app_events.py``.
    Nothing is pushed and nothing is appended to the context:
    :meth:`ForgeBrain.on_rtvi` adds one line naming the *act*, and the picture
    itself is read through ``read_screen``.

    Every edit tool below names a block **by an id read off the screen**, so an
    edit issued against a workflow the admin has moved since can rewire the wrong
    block entirely. ``ScreenState.version`` makes the re-read enforceable rather
    than merely requested: :meth:`ForgeBrain._edit` refuses instead. See
    ``voqalize_demos.screen``.

    Ada mints her own ids for the workflows, blocks and gateways she creates.
    The studio would happily mint them, but then only the studio would know them
    — and the next edit names a block by id.

**Every tool but** ``read_screen`` **dispatches an** :class:`~voqalize.sdk.Action`,
**and each one that takes a parameter takes exactly the Action it dispatches** —
Ada never free-generates infrastructure, so every edit the model proposes is
already the exact shape the studio store applies, and the tool body is one
``self._show(action)`` or ``self._edit(action)`` line.

Only ``read_screen`` is marked ``@needs_result_now``: it is the one tool whose
answer Ada needs before she can say her reply. Every edit applies exactly what
the model specified, by ids it read off the screen, so she says her short line
with the call and reads the result with the admin's next words.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any, Literal, get_args

from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel, Field
from voqalize_demos import (
    DEFAULT_MODEL,
    FallbackLine,
    GeminiBrain,
    ScreenState,
    landed,
    needs_result_now,
    screen_prose,
)

from voqalize.sdk import Action, RTVIMessage, Session, Speech
from voqalize.sdk.wire import Config, Language, SttConfig, TtsConfig, Voice

from .app_events import (
    FORGE_EVENTS,
    BlockFocused,
    CodeOpened,
    CoverageScanned,
    ForgeEvent,
    ListOpened,
    PanelOpened,
    ScenarioFinished,
    TestsFinished,
    WorkflowOpened,
    WorkflowPublished,
)

_SYSTEM_INSTRUCTION = """You are Ada, the Flowforge workflow copilot — a voice assistant for an ITSM / HR-ops administrator who builds "Service Request Workflows" by talking to you. You DRIVE THEIR SCREEN as you talk.

EVERY REPLY STARTS WITH WORDS. Lead with the action: say one short clause — ideally just naming what you're doing, 3 to 8 words — then CALL THE TOOLS IN THAT SAME REPLY. The clause is spoken as the studio changes. A reply that is only tool calls is silence: the studio moves and the admin hears nothing, because every tool but read_screen just does what you asked and you do not hear back from it until the admin speaks again. So your lead-in is your whole line — never promise to report back on an edit. For example:
  Admin: "Contractors asking for a privileged app need a security review." You: "Adding a security review." — and insert_gateway and add_state, in the same reply.
  Admin: "Run the tests." You: "Running them." — and run_tests, in the same reply.
read_screen is the one call that answers you straight away: say a short line like "Let me look." with it, and make your edits right after its answer.

VOICE STYLE — SAY LESS, DO MORE. You are watched, not just heard: the admin SEES the studio change as you work, so let the screen do the talking. This discipline matters more than anything else here.
- Don't describe what's now on screen. The admin can see the new step, the passing tests, the lit path, the code. No recaps, no "I've added…", never read ids, labels, guards, JSON, or lists aloud. Every tool you call also shows up as a live task on screen (a small "activity" checklist), so your actions are already acknowledged visually — trust it and stay quiet.
- Chain tools to finish a real change in one go — one short lead-in, then insert the decision, wire both branches, add the step, all in that same reply. When a later call in the reply has to name a block you are adding in it, give that block its own short id (e.g. "s_security") so you can. Don't stop to announce every edit, and don't come back to recap it.
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

GROUNDING: nothing in this conversation is a picture of the studio. read_screen() is the only one. It says nothing and moves nothing, but the admin waits in silence while you read it, so call it only when you need it — with a short line like "Let me look." in the same reply. You get its answer straight away and speak or make your edits right after it. It lists the open workflow, its blocks WITH THEIR IDS, tests, and gaps. Call it before you edit anything you did not just put there yourself, and whenever you are told the admin changed the screen themselves — you are told THAT they changed it, never what it now says. Always use those real ids when you edit: make the edit in the reply after read_screen answers, never in the same reply as the read. Call open_workflow first if none is open. If you see an edit came back refused because the screen moved under you, it was not applied; that is not something to report or apologise for: read the screen and make the call again.

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
    """Clear one gap once it is really handled. Name it by the pair read_screen
    shows — the state id and the event."""

    state: str = Field(description="The gap's state id.")
    event: str = Field(description="The gap's event.")


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


type ScreenMove = (
    OpenList
    | OpenWorkflow
    | CreateWorkflow
    | AddState
    | InsertGateway
    | AddBranch
    | SetRoute
    | UpdateState
    | RemoveState
    | AddContextField
    | AddField
    | SetCode
    | AddTest
    | RunTests
    | ReviewCoverage
    | ResolveGap
    | RunScenario
    | PublishWorkflow
    | SetPanel
    | FocusState
    | ShowCode
)

#: What Ada says for a command that landed, when the model's turn said nothing —
#: see :mod:`voqalize_demos.silent_turn`. By then the command has run, so each
#: line says it is done, and says no more than that: the studio shows the rest.
_LINES: dict[type[ScreenMove], tuple[str, ...]] = {
    OpenList: ("Here's the list.", "Back on the list."),
    OpenWorkflow: ("It's open.", "Here it is."),
    CreateWorkflow: ("The draft's up.", "Draft created."),
    AddState: ("Step added.", "Added."),
    InsertGateway: ("The branch is in.", "Branch added."),
    AddBranch: ("Branch added.", "Added."),
    SetRoute: ("Rewired.", "Route set."),
    UpdateState: ("Updated.", "Done."),
    RemoveState: ("Removed.", "It's gone."),
    AddContextField: ("Field added.", "Added."),
    AddField: ("Field added.", "Added."),
    SetCode: ("The code's in.", "Done."),
    AddTest: ("Test added.", "Added."),
    RunTests: ("The tests are running.", "Running them."),
    ReviewCoverage: ("The gaps are on screen.", "Here are the gaps."),
    ResolveGap: ("Gap closed.", "Closed."),
    RunScenario: ("The run is on screen.", "Here's the run."),
    PublishWorkflow: ("Published. It's live.",),
    SetPanel: ("Here it is.", "There."),
    FocusState: ("Right there.", "There."),
    ShowCode: ("Here's the code.", "There's the code."),
}
# A command with no line would raise mid-call, so the two are held to each other here.
assert set(_LINES) == set(get_args(ScreenMove.__value__)), "_LINES and ScreenMove disagree"


def _find(catalog: list[dict[str, Any]], wid: str | None) -> dict[str, Any] | None:
    """The workflow dict for ``wid``, or ``None``. Ids are the studio's own."""
    return next((w for w in catalog if w.get("id") == wid), None) if wid else None


def _connector(connector_id: str, action_id: str) -> str:
    return " ".join(part for part in (connector_id, action_id) if part)


def _new_workflow(a: CreateWorkflow) -> dict[str, Any]:
    """The workflow the studio will build from this action — start and end block
    included, because the studio mints those two and Ada's next edit routes
    through them."""
    start, done = f"{a.id}_start", f"{a.id}_done"
    trigger = a.trigger or "A request is raised"
    return {
        "id": a.id,
        "name": a.name or "Untitled workflow",
        "category": a.category,
        "status": "draft",
        "version": 1,
        "trigger": trigger,
        "the request context": [_ctx_field(c) for c in a.context],
        "the blocks": [
            {"id": start, "kind": "start", "label": trigger, "next": done},
            {"id": done, "kind": "end", "label": "Done", "outcome": "Complete"},
        ],
        "the tests": [],
        "the open gaps": [],
    }


def _new_block(a: AddState) -> dict[str, Any]:
    return {
        "id": a.id,
        "kind": a.kind,
        "label": a.label or "Step",
        "subtitle": a.subtitle,
        "next": a.next,
        "rejects to": a.reject_to,
        "approver": a.approver,
        "connector": _connector(a.connector_id, a.action_id),
        "collects": [_form_field(f) for f in a.fields],
        "code": a.code,
        "sla hours": a.sla_hours,
        "outcome": a.outcome,
    }


def _blank_studio() -> dict[str, Any]:
    return {
        "the panel": "flow",
        "the block selected": None,
        "the code block open": None,
        "the last test run": None,
        "the last persona run": None,
        "what is deployed": None,
    }


def _block(blocks: list[dict[str, Any]], bid: str) -> dict[str, Any] | None:
    """The block dict for ``bid``, or ``None``. Ids are the studio's own."""
    return next((b for b in blocks if b.get("id") == bid), None)


def _trim(row: dict[str, Any]) -> dict[str, Any]:
    """Drop the legs a block does not have, all the way down.

    What Ada reads should be the block's real shape, not a form with blanks in
    it — an empty ``rejects to`` read back as a fact is exactly how she comes to
    talk about a route that is not there."""
    out: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, dict):
            value = _trim(value)  # pyright: ignore[reportUnknownArgumentType]
        elif isinstance(value, list):
            value = [  # pyright: ignore[reportUnknownVariableType]
                _trim(item) if isinstance(item, dict) else item
                for item in value  # pyright: ignore[reportUnknownVariableType]
            ]
        if value not in (None, "", [], {}, 0):
            out[key] = value
    return out


def _ctx_field(spec: ContextFieldSpec | AddContextField) -> dict[str, Any]:
    return {
        "key": spec.key,
        "label": spec.label or spec.key,
        "type": spec.type,
        "one of": list(spec.enum_values),
        "derived": spec.derived,
        "expr": spec.expr,
        "note": spec.note,
    }


def _form_field(spec: FormFieldSpec) -> dict[str, Any]:
    return {
        "key": spec.key,
        "label": spec.label or spec.key,
        "type": spec.type,
        "one of": list(spec.enum_values),
    }


def _touch(wf: dict[str, Any]) -> None:
    """An edit un-publishes a published workflow, exactly as the studio does —
    otherwise Ada would go on calling live something the admin has since changed."""
    if wf.get("status") == "published":
        wf["status"] = "draft"


class ForgeBrain(GeminiBrain):
    """One per session. The studio owns the workflow and Ada keeps her own picture
    of it: seeded from ``init``, patched by her edits and by what happens in the
    studio without her, and read back through ``read_screen`` — never pushed."""

    def __init__(self, *, client: genai.Client, model: str = DEFAULT_MODEL) -> None:
        super().__init__(client=client, system_instruction=_SYSTEM_INSTRUCTION, model=model)
        self.admin_name = "there"
        # What is on the admin's studio screen. This is the only copy: it is read
        # through ``read_screen`` and never appended to the model's context.
        self.screen = ScreenState(read_tool="read_screen", actor="admin")
        #: Every workflow the studio holds, seeded from ``session.init`` and
        #: patched in place — the open one is a reference into this list.
        self.catalog: list[dict[str, Any]] = []
        self.open_id: str | None = None
        self.studio = _blank_studio()
        # Ids Ada mints. The studio would mint its own, but then only the studio
        # would know them, and the next edit names a block by id.
        self._seq = 0
        self._fallback = FallbackLine()

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        payload = dict(session.init or {})
        raw = payload.get("admin")
        admin = raw if isinstance(raw, dict) else {}
        self.admin_name = str(admin.get("name") or "").strip() or "there"
        # The catalog the admin tapped in to. It rides ``init`` because the studio
        # already has it — there is nothing to be gained by having the browser
        # hand back, over the wire, the workflows it was itself given.
        raw = payload.get("workflows")
        self.catalog = [w for w in raw if isinstance(w, dict)] if isinstance(raw, list) else []
        self.open_id = None
        self.studio = _blank_studio()
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

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The model's turn, and a line of Ada's own if it acted and said nothing.

        The prompt has the model lead with a short clause and call in the same
        reply; a reply of calls alone would leave the admin in silence with the
        studio changed. See :mod:`voqalize_demos.silent_turn`."""
        async for event in self._fallback.speak_if_silent(self, super().respond(session)):
            yield event

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Browser→brain message: one thing that just happened in the studio.

        Silent by construction — the picture moves and one line goes into the
        context, but no floor is taken and no turn starts. Nothing about a click,
        or a test run coming back, means the admin stopped talking."""
        event = FORGE_EVENTS.parse(msg)
        if event is None:
            return
        logger.info("forge: {} — {}", type(event).__voqal_event__, event)
        note = self.apply_event(event)
        self.append_to_context(types.Content(role="user", parts=[types.Part(text=note)]))

    # ─── Browser → brain: the admin's hand, and the studio's own answers ─

    def apply_event(self, event: ForgeEvent) -> str:
        """Fold one thing that happened into the picture and say what to tell Ada.

        The two halves read differently on purpose. A gesture is *named* and
        never valued — the workflow behind it is read through ``read_screen``,
        which is what keeps it from going stale in the context. An answer the
        studio computed carries its result, because the interpreter is the only
        place that result exists. No fallback arm: an event added to
        :data:`ForgeEvent` and not handled here is a type error, not a silent
        drop."""
        wf = self._open()
        match event:
            # ── the admin's own hand ──
            case ListOpened():
                self.open_id = None
                self.studio["the last persona run"] = None
                return self.screen.moved("went back to the workflow list")
            case WorkflowOpened():
                self._enter(event.id)
                return self.screen.moved("opened a workflow themselves")
            case PanelOpened():
                self.studio["the panel"] = event.panel
                return self.screen.moved(f"switched to the {event.panel} panel")
            case BlockFocused():
                self.studio["the block selected"] = event.id
                return self.screen.moved("selected a block themselves")
            case CodeOpened():
                self.studio |= {"the code block open": event.id, "the panel": "code"}
                return self.screen.moved("opened one block's code")
            # ── the studio's own answer ──
            case TestsFinished():
                by_name = {t.name: t for t in event.tests}
                for test in wf["the tests"] if wf else []:
                    outcome = by_name.get(test.get("name", ""))
                    if outcome is not None:
                        test["status"] = "pass" if outcome.passed else "fail"
                        test["actual"] = outcome.rested_at
                passed = sum(1 for t in event.tests if t.passed)
                self.studio |= {
                    "the panel": "tests",
                    "the last test run": f"{passed} of {len(event.tests)} passing",
                }
                failed = [t for t in event.tests if not t.passed]
                tail = (
                    "".join(f" '{t.name}' rested at {t.rested_at or 'nowhere'}." for t in failed)
                    if failed
                    else ""
                )
                return self.screen.happened(
                    f"The test run finished: {passed} of {len(event.tests)} passing.{tail}"
                )
            case CoverageScanned():
                gaps = [
                    {"state": g.state, "event": g.event, "question": g.question} for g in event.gaps
                ]
                if wf is not None:
                    wf["the open gaps"] = gaps
                self.studio["the panel"] = "tests"
                if not gaps:
                    return self.screen.happened("The coverage scan came back clean.")
                pairs = ", ".join(f"{g['state']} on {g['event']}" for g in gaps)
                return self.screen.happened(
                    f"The coverage scan found {len(gaps)} unhandled pairs: {pairs}."
                )
            case ScenarioFinished():
                self.studio |= {
                    "the panel": "flow",
                    "the last persona run": {
                        "persona": event.persona,
                        "rested at": event.rested_at,
                    },
                }
                return self.screen.happened(
                    f"The {event.persona or 'persona'} run came to rest at "
                    f"{event.rested_at or 'nowhere'}."
                )
            case WorkflowPublished():
                published = _find(self.catalog, event.id)
                if published is not None:
                    published |= {"status": "published", "version": event.version}
                self.studio |= {
                    "the panel": "runtime",
                    "what is deployed": {"version": event.version, "run id": event.run_id},
                }
                return self.screen.happened(
                    f"The publish landed: version {event.version} is live, "
                    f"as request {event.run_id}."
                )

    # ─── Brain → browser ────────────────────────────────────────────────

    def _open(self) -> dict[str, Any] | None:
        """The workflow Ada has open, or ``None`` on the list screen."""
        return _find(self.catalog, self.open_id) if self.open_id else None

    def _enter(self, wid: str) -> None:
        """Open ``wid`` if the studio has it — the studio ignores an id it does
        not hold, and a picture that opened one the screen did not is worse than
        one that stayed put."""
        if _find(self.catalog, wid) is None:
            return
        self.open_id = wid
        self.studio |= _blank_studio()

    def _id(self, prefix: str) -> str:
        """An id Ada mints. The ``a`` keeps it clear of the studio's own counter,
        which starts at 1000 and would otherwise collide the moment both are
        naming blocks in the same workflow."""
        self._seq += 1
        return f"{prefix}a{self._seq}"

    def _show(self, action: ScreenMove) -> None:
        """Put something on screen: patch Ada's picture, then dispatch.

        Both, in that order, and only here — a dispatch that skipped the mirror
        would leave her reading a workflow one edit behind her own last word."""
        match action:
            case CreateWorkflow() if not action.id:
                action.id = self._id("wf-")
            case AddState() if not action.id:
                action.id = self._id("s_")
            case InsertGateway() if not action.id:
                action.id = self._id("g_")
            case _:
                pass
        self._mirror(action)
        self.session.dispatch(action)
        landed(*_LINES[type(action)])

    def _edit(self, action: ScreenMove) -> str | None:
        """Apply an edit to the open workflow, or say why it is refused.

        Every edit names a block by an id Ada read off the screen, so an edit
        issued against a workflow the admin has moved since can rewire something
        else entirely. The refusal is retriable: read, then act."""
        stale = self.screen.stale()
        if stale:
            return f"not applied: {stale}"
        self._show(action)
        return None

    def _mirror(self, action: ScreenMove) -> None:
        """Fold one of Ada's own actions into her picture, following the studio's
        real semantics — a partial edit leaves the legs it did not name alone, a
        removed block heals the spine behind it, a gateway inherits what came
        next. Where the two would disagree the picture is wrong, and every edit
        after it names an id off a screen that isn't there.

        Nothing here is echo suppression: her dispatch is simply not an event.
        What the studio computes for itself comes back through
        :meth:`apply_event`, and that is a different thing arriving by a
        different door."""
        wf = self._open()
        blocks: list[dict[str, Any]] = wf["the blocks"] if wf else []
        match action:
            case OpenList():
                self.open_id = None
                self.studio["the last persona run"] = None
            case OpenWorkflow():
                self._enter(action.id)
            case CreateWorkflow():
                self.catalog.insert(0, _new_workflow(action))
                self._enter(action.id)
            case AddState():
                if wf is None:
                    return
                block = _new_block(action)
                if action.after and (prev := _block(blocks, action.after)) is not None:
                    block["next"] = block["next"] or prev.get("next", "")
                    prev["next"] = action.id
                blocks.append(block)
                self.studio["the block selected"] = action.id
                if action.kind == "code" and action.code:
                    self.studio["the code block open"] = action.id
                _touch(wf)
            case InsertGateway():
                after = _block(blocks, action.after)
                if wf is None or after is None:
                    return
                blocks.append(
                    {
                        "id": action.id,
                        "kind": "gateway",
                        "label": action.label or "Branch",
                        "subtitle": action.subtitle,
                        "branches": [
                            {"label": b.label or "Branch", "guard": b.guard or "true", "to": b.to}
                            for b in action.branches
                        ],
                        # The default path is whatever used to come next.
                        "otherwise": action.otherwise or after.get("next", ""),
                    }
                )
                after["next"] = action.id
                self.studio["the block selected"] = action.id
                _touch(wf)
            case AddBranch():
                gate = _block(blocks, action.gateway)
                if wf is None or gate is None or gate.get("kind") != "gateway":
                    return
                gate.setdefault("branches", []).append(
                    {
                        "label": action.label or "Branch",
                        "guard": action.guard or "true",
                        "to": action.to,
                    }
                )
                self.studio["the block selected"] = gate["id"]
                _touch(wf)
            case SetRoute():
                block = _block(blocks, action.state)
                if wf is None or block is None:
                    return
                # Empty means "unchanged" — rewiring one exit must not unwire the
                # other two.
                for key, value in (
                    ("next", action.next),
                    ("rejects to", action.reject_to),
                    ("otherwise", action.otherwise),
                ):
                    if value:
                        block[key] = value
                _touch(wf)
            case UpdateState():
                block = _block(blocks, action.id)
                if wf is None or block is None:
                    return
                for key, value in (
                    ("label", action.label),
                    ("subtitle", action.subtitle),
                    ("approver", action.approver),
                    ("outcome", action.outcome),
                    ("sla hours", action.sla_hours),
                ):
                    if value:
                        block[key] = value
                if action.connector_id or action.action_id:
                    block["connector"] = _connector(
                        action.connector_id or str(block.get("connector", "")).split(" ")[0],
                        action.action_id,
                    )
                self.studio["the block selected"] = action.id
                _touch(wf)
            case RemoveState():
                if wf is None:
                    return
                gone = _block(blocks, action.id)
                heir = str(gone.get("next", "")) if gone else ""
                for block in blocks:
                    for leg in ("next", "rejects to", "otherwise"):
                        if block.get(leg) == action.id:
                            block[leg] = heir
                    if isinstance(branches := block.get("branches"), list):
                        block["branches"] = [
                            b
                            for b in branches  # pyright: ignore[reportUnknownVariableType]
                            if not (isinstance(b, dict) and b.get("to") == action.id)
                        ]
                wf["the blocks"] = [b for b in blocks if b.get("id") != action.id]
                self.studio["the block selected"] = None
                _touch(wf)
            case AddContextField():
                if wf is None:
                    return
                wf["the request context"].append(_ctx_field(action))
                _touch(wf)
            case AddField():
                block = _block(blocks, action.state)
                if wf is None or block is None:
                    return
                block.setdefault("collects", []).append(_form_field(action.field))
                self.studio["the block selected"] = action.state
                _touch(wf)
            case SetCode():
                block = _block(blocks, action.state)
                if wf is None or block is None:
                    return
                block["code"] = action.code
                if block.get("kind") not in ("code", "gateway"):
                    block["kind"] = "code"
                self.studio |= {
                    "the block selected": action.state,
                    "the code block open": action.state,
                    "the panel": "code",
                }
                _touch(wf)
            case AddTest():
                if wf is None:
                    return
                wf["the tests"].append(
                    {
                        "name": action.name or "Test",
                        "given": action.given_state,
                        "event": action.event,
                        "expect": action.expect_state,
                        "status": "idle",
                    }
                )
                self.studio["the panel"] = "tests"
                _touch(wf)
            case RunTests():
                # The outcomes are the interpreter's, on its own clock; they land
                # in ``TestsFinished``. Until then the picture says so rather than
                # keeping the previous run's verdicts on screen.
                for test in wf["the tests"] if wf else []:
                    test |= {"status": "running", "actual": ""}
                self.studio |= {"the panel": "tests", "the last test run": "running"}
            case ReviewCoverage():
                if wf is not None:
                    wf["the open gaps"] = []
                self.studio["the panel"] = "tests"
            case ResolveGap():
                if wf is None:
                    return
                wf["the open gaps"] = [
                    g
                    for g in wf["the open gaps"]
                    if not (g["state"] == action.state and g["event"] == action.event)
                ]
            case RunScenario():
                self.studio |= {
                    "the panel": "flow",
                    "the block selected": None,
                    "the last persona run": {
                        "persona": action.persona_label,
                        "rested at": "still walking",
                    },
                }
            case PublishWorkflow():
                # The version and the run id are minted by the studio and come
                # back in ``WorkflowPublished``; all that is settled here is the
                # panel the admin is now looking at.
                self.studio["the panel"] = "runtime"
            case SetPanel():
                self.studio["the panel"] = action.panel
            case FocusState():
                self.studio["the block selected"] = action.id
            case ShowCode():
                self.studio |= {"the code block open": action.id, "the panel": "code"}

    # ─── Tools ──────────────────────────────────────────────────────────
    #
    # The model calls these directly. Every one that takes a parameter takes
    # exactly the Action it dispatches — Ada assembles from a governed catalog,
    # never free generates, so the model's arguments are already the studio's
    # edit. Each returns a short string; most just say "done" and let the screen
    # speak. Every one reads or patches this session's own picture and returns
    # inside the SDK's tool budget, and only ``read_screen`` is read before the
    # turn ends — the rest are read with the admin's next words.

    @property
    def tools(self) -> list[Any]:
        """The tools Ada may call, read once per turn. Every one but
        ``read_screen`` drives the studio screen; ``read_screen`` reads it back."""
        return [
            self.read_screen,
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

    @needs_result_now
    async def read_screen(self) -> str:
        """What is on the admin's studio screen right now — the open workflow with
        its blocks AND THEIR IDS, its tests, and its open gaps.

        Call it before you edit anything you did not just put there yourself, and
        whenever you are told the admin changed the screen themselves. It reads
        this session's own state, says nothing, and moves nothing; you get its
        answer straight away, and make your edits in the reply after it."""
        self.screen.read()
        logger.info("forge: read_screen (open={}, v{})", self.open_id, self.screen.version)
        wf = self._open()
        where: dict[str, Any] = {
            "screen": "editor" if wf else "workflow list",
            "the workflows": [
                {"id": w["id"], "name": w["name"], "category": w["category"], "status": w["status"]}
                for w in self.catalog
            ],
        }
        if wf is not None:
            where |= self.studio
            where["the open workflow"] = _trim(wf)
        return screen_prose(where, actor="admin")

    async def open_list(self) -> str:
        """Return to the list of all Service Request Workflows."""
        self._show(OpenList())
        return "done"

    async def open_workflow(self, action: OpenWorkflow) -> str:
        """Open a workflow by id to edit it."""
        self._show(action)
        return f"opened {action.id}"

    async def create_workflow(self, action: CreateWorkflow) -> str:
        """Author a NEW workflow from scratch — creates a draft with a trigger
        and an end, then build it up."""
        self._show(action)
        return f"created draft '{action.name}'"

    async def add_state(self, action: AddState) -> str:
        """Add a block into the linear spine after `after` (rewires the flow).
        For service blocks pass connector_id+action_id; for approval pass
        approver; for form pass fields; for code pass code."""
        return self._edit(action) or f"added {action.kind} '{action.label}'"

    async def insert_gateway(self, action: InsertGateway) -> str:
        """Splice an exclusive branch (gateway) in after `after`. The block that
        came next becomes the default path; each branch guards a route to
        another block."""
        return self._edit(action) or "branch inserted"

    async def add_branch(self, action: AddBranch) -> str:
        """Append one guarded branch to an existing gateway."""
        return self._edit(action) or "done"

    async def set_route(self, action: SetRoute) -> str:
        """Rewire a block's transitions."""
        return self._edit(action) or "done"

    async def update_state(self, action: UpdateState) -> str:
        """Edit a block's label / connector / approver / SLA / outcome."""
        return self._edit(action) or "done"

    async def remove_state(self, action: RemoveState) -> str:
        """Delete a block and heal the flow around it."""
        return self._edit(action) or "done"

    async def add_context_field(self, action: AddContextField) -> str:
        """Add a field to the request context. Set derived+expr for a
        JS-computed field."""
        return self._edit(action) or "done"

    async def add_field(self, action: AddField) -> str:
        """Add one field to a form block."""
        return self._edit(action) or "done"

    async def set_code(self, action: SetCode) -> str:
        """Set the JavaScript on a code block (the escape hatch)."""
        return self._edit(action) or "done"

    async def add_test(self, action: AddTest) -> str:
        """Add a transition test: in given_state, on event, expect expect_state.
        `context` is a JSON object string of field values."""
        return self._edit(action) or "done"

    async def run_tests(self) -> str:
        """Run all tests for the open workflow (executes the real JS guards)."""
        self._show(RunTests())
        return "tests running on screen"

    async def review_coverage(self) -> str:
        """Scan for unhandled (state, event) pairs and surface them as gap
        questions."""
        self._show(ReviewCoverage())
        return "coverage scanned — the gaps are on screen"

    async def resolve_gap(self, action: ResolveGap) -> str:
        """Mark a coverage gap handled AFTER you've wired a real handler for it
        (a route, step, branch, or code block). Identify it by its id, or by
        the state+event pair it flagged."""
        return self._edit(action) or "gap cleared"

    async def run_scenario(self, action: RunScenario) -> str:
        """THE FINALE: walk a persona through the live flow from the trigger,
        lighting the path. `context` is a JSON object string; `events` are the
        ordered events the persona fires."""
        return (
            self._edit(action)
            or f"walking {action.persona_label or 'the persona'} through the flow"
        )

    async def publish_workflow(self) -> str:
        """Publish the open workflow — makes this version live and durable."""
        return self._edit(PublishWorkflow()) or "published — now live and durable"

    async def set_panel(self, action: SetPanel) -> str:
        """Switch the right panel."""
        self._show(action)
        return "done"

    async def focus_state(self, action: FocusState) -> str:
        """Highlight/select one block on screen."""
        return self._edit(action) or "done"

    async def show_code(self, action: ShowCode) -> str:
        """Open the Code panel and reveal the JavaScript behind one block (a
        decision's guards or a code step). Show the rigor; don't read it
        aloud."""
        return self._edit(action) or "done"
