"""ForgeBrain — "Ada", the Flowforge workflow copilot.

A ``voqalize.sdk.Brain`` (a :class:`GeminiBrain`) for the voice **workflow
studio**: an ITSM/HR-ops admin assembles a Service Request Workflow — a
block-based statechart over a typed context — by talking to Ada, and Ada drives
the studio screen as she talks.

Like the other demos, the LLM generates the structured edits and each tool body
relays them to the browser via ``interaction.action(name, {...})`` — the RTVI
``ui_command`` the ``/forge`` UI applies to its store. The browser is the source
of truth for the open workflow; it pushes a compact ``state_sync`` snapshot on
every change, folded into every turn's working context (:meth:`grounding`) so Ada
always edits against the real on-screen blocks and their ids.

The tool property names are exactly the keys the store's ops read (``givenState``,
``connectorId``, ``rejectTo``…), so ``dispatch_tool`` forwards the LLM's arguments
to the browser almost verbatim.
"""

from __future__ import annotations

import json
from typing import Any

from google.genai import types
from loguru import logger
from voqalize_demos import DEFAULT_MODEL, GeminiBrain, GeminiProvider

_SYSTEM_INSTRUCTION = """You are Ada, the Flowforge workflow copilot — a voice assistant for an ITSM / HR-ops administrator who builds "Service Request Workflows" by talking to you. You DRIVE THEIR SCREEN as you talk.

VOICE STYLE — SAY LESS, DO MORE. You are watched, not just heard: the admin SEES the studio change as you work, so let the screen do the talking. This discipline matters more than anything else here.
- Lead with the action. Say one short clause — ideally just naming what you're about to do, 3 to 8 words — then CALL THE TOOL. E.g. "Adding a security review." then the tool. Never narrate in silence; never call a tool without that brief lead-in.
- Don't describe what's now on screen. The admin can see the new step, the passing tests, the lit path, the code. No recaps, no "I've added…", never read ids, labels, guards, JSON, or lists aloud. Every tool you call also shows up as a live task on screen (a small "activity" checklist), so your actions are already acknowledged visually — trust it and stay quiet.
- Chain tools to finish a real change in one go — insert the decision, wire both branches, add the step — then ONE short line at the end. Don't stop to announce every edit.
- Ask a question ONLY when genuinely blocked by a real fork the admin must decide. Otherwise pick the sensible default, do it, and let them correct you.
- Spoken English, short sentences, no markdown or symbols.

WHAT A WORKFLOW IS: a block-based statechart. Each workflow has a typed CONTEXT (the request's data) and STATES (blocks) wired by transitions. You ASSEMBLE it from a governed catalog — you never free-generate infrastructure. Block kinds:
- start: the trigger. form: collect fields. approval: a person approves or rejects. service: call ONE connector action. gateway: an exclusive branch on guards. wait: an SLA/timer. code: a JavaScript escape hatch. end: a terminal outcome.

CONNECTOR CATALOG (use these connectorId · actionId):
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

ROUTING: an approval's `next` is its approve path and `rejectTo` is its reject path. A gateway has ordered `branches` (each a guard + target) and an `else` default. To add a branch to an existing linear flow, use insert_gateway(after: <stateId>) — the block that came next becomes the else path automatically; point a branch at a new block that eventually rejoins the flow.

TESTS are the admin's mental model: "the workflow is in {givenState}, {event} occurs, expect {expectState}". Events by kind — form: submit/cancel; approval: approve/reject/timeout/withdrawn; wait: elapsed/cancelled. Add tests with add_test, then run_tests. The runner executes the real JS guards — the results appear on screen, so don't recite them.

HANDLING EDGE CASES (the core demo loop): review_coverage surfaces the unhandled (state, event) pairs — the gaps — on screen. For each gap the admin wants closed: WIRE A REAL HANDLER (a reject route via set_route, a new step via add_state, a branch via insert_gateway, or a code block via set_code), THEN call resolve_gap to clear it. Prove it with add_test + run_tests. This loop — surface the gap, handle it, resolve it, test it — is the heart of the demo.

PUBLISH: publish_workflow makes the open version live. Say it plainly and briefly — e.g. "Publishing now." — and let the Live panel show it. The story if asked: runs are DURABLE — a request mid-approval keeps its place through any restart, and every step runs exactly once. Never name a specific engine or vendor.

THE FINALE — run_scenario: walk a persona through the live flow from the trigger. Pass personaLabel, a context JSON string, and the ordered events the persona fires (e.g. approvals). The screen lights the whole path. Great for proving an edit works, e.g. a contractor requesting a privileged app taking the new security branch.

GROUNDING: a CURRENT WORKSPACE STATE snapshot is folded into your context every turn — it lists the open workflow, its blocks WITH THEIR IDS, tests, and gaps. Always use those real ids when you edit; call open_workflow first if none is open.

Open with a brief greeting and ask what they'd like to build or change."""


# ─── Reusable schema fragments ──────────────────────────────────────────────────

_CONTEXT_FIELD = {
    "type": "object",
    "properties": {
        "key": {
            "type": "string",
            "description": "Dotted key, e.g. 'requester.type' or 'privilegedApp'.",
        },
        "label": {"type": "string"},
        "type": {"type": "string", "enum": ["string", "boolean", "number", "enum", "user"]},
        "enumValues": {"type": "array", "items": {"type": "string"}},
        "derived": {
            "type": "boolean",
            "description": "True if computed from other fields by a JS expr.",
        },
        "expr": {
            "type": "string",
            "description": "JS expression for a derived field, e.g. ctx.app length check.",
        },
        "note": {"type": "string", "description": "Provenance, e.g. 'from Entra ID'."},
    },
}
_FORM_FIELD = {
    "type": "object",
    "properties": {
        "key": {"type": "string"},
        "label": {"type": "string"},
        "type": {"type": "string", "enum": ["string", "boolean", "number", "enum", "user"]},
        "enumValues": {"type": "array", "items": {"type": "string"}},
    },
}
_BRANCH = {
    "type": "object",
    "properties": {
        "label": {
            "type": "string",
            "description": "Human summary, e.g. 'Contractor + privileged app'.",
        },
        "guard": {"type": "string", "description": "JS expression over ctx, first truthy wins."},
        "to": {"type": "string", "description": "Target state id."},
    },
}


def _arr(item: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": item}


# (tool_name, description, properties, required)
_TOOLSPECS: list[tuple[str, str, dict[str, Any], list[str]]] = [
    ("open_list", "Return to the list of all Service Request Workflows.", {}, []),
    ("open_workflow", "Open a workflow by id to edit it.", {"id": {"type": "string"}}, ["id"]),
    (
        "create_workflow",
        "Author a NEW workflow from scratch — creates a draft with a trigger and an end, then build it up.",
        {
            "id": {"type": "string", "description": "Short kebab id, e.g. 'guest-wifi'."},
            "name": {"type": "string"},
            "description": {"type": "string"},
            "category": {"type": "string", "enum": ["ITSM", "HR", "Security"]},
            "trigger": {"type": "string", "description": "How it starts, in plain words."},
            "channels": {"type": "array", "items": {"type": "string"}},
            "context": _arr(_CONTEXT_FIELD),
        },
        ["name", "trigger"],
    ),
    (
        "add_state",
        "Add a block into the linear spine after `after` (rewires the flow). For service blocks pass connectorId+actionId; for approval pass approver; for form pass fields; for code pass code.",
        {
            "id": {"type": "string", "description": "Optional stable id; auto if omitted."},
            "after": {"type": "string", "description": "Insert after this state id."},
            "kind": {
                "type": "string",
                "enum": ["form", "approval", "service", "wait", "code", "end"],
            },
            "label": {"type": "string"},
            "subtitle": {"type": "string"},
            "connectorId": {"type": "string"},
            "actionId": {"type": "string"},
            "approver": {
                "type": "string",
                "description": "e.g. 'Reporting manager', 'VP, Engineering'.",
            },
            "fields": _arr(_FORM_FIELD),
            "code": {"type": "string", "description": "JS body ending in 'return ctx;'."},
            "slaHours": {"type": "integer"},
            "next": {"type": "string"},
            "rejectTo": {"type": "string"},
            "outcome": {"type": "string"},
        },
        ["kind", "label"],
    ),
    (
        "insert_gateway",
        "Splice an exclusive branch (gateway) in after `after`. The block that came next becomes the else/default path; each branch guards a route to another block.",
        {
            "after": {"type": "string"},
            "id": {"type": "string"},
            "label": {"type": "string"},
            "subtitle": {"type": "string"},
            "branches": _arr(_BRANCH),
            "else": {"type": "string", "description": "Optional explicit default target id."},
        },
        ["after", "branches"],
    ),
    (
        "add_branch",
        "Append one guarded branch to an existing gateway.",
        {
            "gateway": {"type": "string"},
            "label": {"type": "string"},
            "guard": {"type": "string"},
            "to": {"type": "string"},
        },
        ["gateway", "guard", "to"],
    ),
    (
        "set_route",
        "Rewire a block's transitions.",
        {
            "state": {"type": "string"},
            "next": {"type": "string"},
            "rejectTo": {"type": "string"},
            "else": {"type": "string"},
        },
        ["state"],
    ),
    (
        "update_state",
        "Edit a block's label / connector / approver / SLA / outcome.",
        {
            "id": {"type": "string"},
            "label": {"type": "string"},
            "subtitle": {"type": "string"},
            "connectorId": {"type": "string"},
            "actionId": {"type": "string"},
            "approver": {"type": "string"},
            "slaHours": {"type": "integer"},
            "outcome": {"type": "string"},
        },
        ["id"],
    ),
    (
        "remove_state",
        "Delete a block and heal the flow around it.",
        {"id": {"type": "string"}},
        ["id"],
    ),
    (
        "add_context_field",
        "Add a field to the request context. Set derived+expr for a JS-computed field.",
        _CONTEXT_FIELD["properties"],
        ["key", "type"],
    ),
    (
        "add_field",
        "Add one field to a form block.",
        {"state": {"type": "string"}, "field": _FORM_FIELD},
        ["state", "field"],
    ),
    (
        "set_code",
        "Set the JavaScript on a code block (the escape hatch).",
        {"state": {"type": "string"}, "code": {"type": "string"}},
        ["state", "code"],
    ),
    (
        "add_test",
        "Add a transition test: in givenState, on event, expect expectState. `context` is a JSON object string of field values.",
        {
            "name": {"type": "string"},
            "givenState": {"type": "string"},
            "event": {"type": "string"},
            "expectState": {"type": "string"},
            "context": {
                "type": "string",
                "description": 'JSON, e.g. {"requester.type":"contractor","app":"AWS Console"}.',
            },
        },
        ["name", "givenState", "event", "expectState"],
    ),
    ("run_tests", "Run all tests for the open workflow (executes the real JS guards).", {}, []),
    (
        "review_coverage",
        "Scan for unhandled (state, event) pairs and surface them as gap questions.",
        {},
        [],
    ),
    (
        "resolve_gap",
        "Mark a coverage gap handled AFTER you've wired a real handler for it (a route, step, branch, or code block). Identify it by its id, or by the state+event pair it flagged.",
        {
            "id": {"type": "string", "description": "The gap id, if known."},
            "state": {"type": "string", "description": "Gap's state id (with `event`) if no id."},
            "event": {"type": "string", "description": "Gap's event (with `state`) if no id."},
        },
        [],
    ),
    (
        "run_scenario",
        "THE FINALE: walk a persona through the live flow from the trigger, lighting the path. `context` is a JSON object string; `events` are the ordered events the persona fires.",
        {
            "personaLabel": {"type": "string", "description": "e.g. 'Contractor · AWS Console'."},
            "context": {"type": "string", "description": "JSON object of context values."},
            "events": {"type": "array", "items": {"type": "string"}},
        },
        ["personaLabel"],
    ),
    (
        "publish_workflow",
        "Publish the open workflow — makes this version live and durable.",
        {},
        [],
    ),
    (
        "set_panel",
        "Switch the right panel.",
        {"panel": {"type": "string", "enum": ["flow", "code", "tests", "runtime"]}},
        ["panel"],
    ),
    ("focus_state", "Highlight/select one block on screen.", {"id": {"type": "string"}}, ["id"]),
    (
        "show_code",
        "Open the Code panel and reveal the JavaScript behind one block (a decision's guards or a code step). Show the rigor; don't read it aloud.",
        {"id": {"type": "string", "description": "The state id whose code to reveal."}},
        ["id"],
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
    return [types.Tool(function_declarations=decls)]


class ForgeBrain(GeminiBrain):
    """One per session. Nearly stateless: the browser owns the workflow; Ada relays
    edits and grounds on the live ``state_sync`` snapshot every turn."""

    def __init__(self, *, llm: GeminiProvider, model: str = DEFAULT_MODEL) -> None:
        super().__init__(
            llm=llm, system_instruction=_SYSTEM_INSTRUCTION, tools=_tools(), model=model
        )
        self.admin_name = "there"
        self.current_state: dict[str, Any] | None = None
        self._state_received = False

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session, start) -> None:
        payload = dict(start.init)
        raw = payload.get("admin")
        admin = raw if isinstance(raw, dict) else {}
        self.admin_name = str(admin.get("name") or "").strip() or "there"
        await self.say(
            session,
            f"Hi {self.admin_name} — Ada here. Want to open a workflow to change, or build a new one?",
        )

    async def on_client_message(self, session, message) -> None:
        # Ingested silently (no floor taken): we never touch message.interaction.
        if message.type == "state_sync":
            snapshot = (message.data or {}).get("workspace")
            self.current_state = snapshot if isinstance(snapshot, dict) else None
            self._state_received = True
            logger.info("forge: state_sync ingested (active={})", bool(self.current_state))

    # ─── Grounding: fold the live workspace into every turn ──────────────

    def grounding(self, interaction) -> str | None:
        if not self._state_received:
            return None
        if self.current_state is None:
            return "CURRENT WORKSPACE STATE: the studio is on the workflow list."
        try:
            blob = json.dumps(self.current_state, ensure_ascii=False)
        except (TypeError, ValueError):
            blob = str(self.current_state)
        return (
            "CURRENT WORKSPACE STATE (authoritative — the open workflow with block ids, tests, and gaps; "
            "always edit against these ids): " + blob
        )

    # ─── Tools ──────────────────────────────────────────────────────────

    def dispatch_tool(self, interaction, name: str, args: dict[str, Any]) -> str:
        """Relay each edit to the browser via ``interaction.action`` — the RTVI
        ``ui_command`` the /forge store applies. Tool arg names already match the
        store's op keys, so we forward them verbatim."""
        logger.info("forge: tool {} {}", name, list(args.keys()))
        act = interaction.action
        known = {t[0] for t in _TOOLSPECS}
        if name not in known:
            return "unknown tool"
        act(name, args)
        return _confirm(name, args)


def _confirm(name: str, args: dict[str, Any]) -> str:
    """A short result string that keeps the tool loop going."""
    if name == "run_tests":
        return "tests running on screen"
    if name == "review_coverage":
        return "coverage scanned — the gaps are on screen"
    if name == "resolve_gap":
        return "gap cleared"
    if name == "publish_workflow":
        return "published — now live and durable"
    if name == "run_scenario":
        return f"walking {args.get('personaLabel', 'the persona')} through the flow"
    if name == "insert_gateway":
        return "branch inserted"
    if name == "add_state":
        return f"added {args.get('kind', 'block')} '{args.get('label', '')}'"
    if name == "create_workflow":
        return f"created draft '{args.get('name', '')}'"
    if name == "open_workflow":
        return f"opened {args.get('id', '')}"
    return "done"
