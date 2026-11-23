# Generated from payroll_app/frontend/src/stage/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
#   voqalize stage gen payroll_app/frontend/src/stage/scene.json --py payroll_app/backend/stage_gen.py --ts payroll_app/frontend/src/stage/scene.gen.ts
"""The moves of paynora_app, from its Stage Spec."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from voqalize.sdk.stage import Move, MoveClass, MoveSet, StageSpec, load_spec

#: The spec itself, carried here so the brain never reads the JSON at run
#: time (and a deploy that ships this file ships the spec with it).
SPEC: StageSpec = load_spec(
    '{"events":[{"doc":"The route changed.","id":"screen.viewed","note":"{by} opened {title}","op":"set","react":"silent","slice":"screen"},{"doc":"A leave request was approved or rejected.","id":"leave.decided","note":"{by} decided leave request {request_id}: {decision}","op":"set","slice":"leave"},{"doc":"A claim was fixed, approved or rejected.","id":"claim.changed","note":"{by} set claim {claim_id} to {status}","op":"set","slice":"claim"},{"doc":"A new employee was saved.","id":"employee.added","note":"{by} added {name} as {employee_id}","op":"set","slice":"joiner"},{"doc":"An employee\'s TDS regime was changed.","id":"regime.switched","note":"{by} switched {employee_id} to the {regime} regime","op":"set","slice":"regime"},{"doc":"A hand-off ticket was sent to Paynora\'s payroll team.","id":"ticket.created","note":"{by} sent ticket {ticket_id}","op":"set","slice":"ticket"},{"doc":"The admin approved and locked a payroll run.","id":"run.approved","note":"{by} approved the payroll run {run_id}","op":"set","slice":"run"},{"doc":"The setup wizard moved, or a field on it was filled.","id":"setup.changed","note":"{by} is on the {step} step of setup","op":"set","slice":"setup"}],"id":"paynora_app","languages":["en","hi"],"moves":[{"args":[{"doc":"One of the app\'s main pages, by its name in the sidebar: Dashboard, Employees, Payroll, Payslips, Leave, Reimbursements, Tax, Settings, Help, Setup. Refused with the names when it is not one.","name":"page"}],"claims":["taking you to","opening the * page","आपको * पर ले चलती"],"class":"navigate","doc":"Open one of the sidebar\'s pages and ring its heading.","id":"app.go","objects":["page","screen","पेज"],"say":"{go: Leave} as you take them to one of the app\'s pages.","verb":"go"},{"args":[{"doc":"A part of the screen in front, by the label it shows: a payslip line (Loss of pay, TDS, Net pay), a control (Switch regime, Approve), a panel (Old regime slabs).","name":"thing"}],"class":"look","doc":"Scroll to the data-stage-thing whose label matches and ring it. Refused with the labels on the screen.","id":"app.show","say":"{show: TDS} at the start of the sentence about that part of the screen; it scrolls into view and is ringed.","verb":"show"},{"args":[{"doc":"An app path: /, /employees/BB-1030, /leave, /tax/regime/BB-1007, /me/BB-1030/payslips, /welcome.","name":"path"}],"claims":["opening","taking you to","खोल रही"],"class":"navigate","doc":"Open any screen of the app by its path; ring its heading.","id":"app.open","objects":["page","record","profile","screen"]},{"args":[{"doc":"BB-1030","name":"employee_id"},{"doc":"The payslip\'s month, 2026-01.","name":"month"},{"doc":"The month to compare with, 2025-12; null shows the payslip alone.","name":"against","optional":true}],"claims":["opening * payslip","pulling up * payslip","comparing * payslip"],"class":"navigate","doc":"Open an employee\'s payslip for a month, side by side with another month and the difference per line.","id":"payslip.compare","objects":["payslip","पेस्लिप"]},{"args":[{"doc":"BB-1007","name":"employee_id"}],"claims":["opening * regime","comparing * regime","comparing both regimes"],"class":"navigate","doc":"Open the regime comparison of one employee: both regimes\' computations slab by slab, from the engine.","id":"regime.compare","objects":["regime","comparison","रिजीम"]},{"args":[{"doc":"LV-2412","name":"request_id"},{"enum":["approve","reject"],"name":"decision"}],"claims":["approving * leave","rejecting * leave"],"class":"confirmed","doc":"Approve or reject a pending leave request, after the admin\'s spoken yes. Days beyond the balance become loss of pay in the February draft, recomputed with the engine.","id":"leave.decide","objects":["leave"]},{"args":[{"doc":"RB-3108","name":"claim_id"},{"doc":"The corrected amount, the bill\'s amount.","name":"amount","type":"integer"}],"claims":["fixing * claim","correcting * claim"],"class":"confirmed","doc":"Correct a claim\'s amount to its bill and approve it into the February draft, after the admin\'s spoken yes.","id":"claim.fix","objects":["claim","reimbursement"]},{"args":[{"doc":"RB-3109","name":"claim_id"},{"enum":["approve","reject"],"name":"decision"}],"claims":["approving * claim","rejecting * claim"],"class":"confirmed","doc":"Approve (into the February draft) or reject a pending claim, after the admin\'s spoken yes.","id":"claim.decide","objects":["claim","reimbursement"]},{"args":[{"doc":"RB-3109","name":"claim_id"}],"claims":["opening * claim","pulling up * claim"],"class":"navigate","doc":"Open one claim\'s detail panel on the Reimbursements screen: what was claimed beside the bill, and its Approve, Reject or Fix buttons.","id":"claim.open","objects":["claim","reimbursement","request"]},{"args":[{"doc":"A field of the form by its name: name, email, gender, department, title, grade, location, joined, annual_ctc, tax_regime, manager_id.","name":"field"},{"doc":"As the form takes it: a location by its city, a date as 2026-02-16, CTC in rupees, regime new or old.","name":"value"}],"claims":["filling in","adding * details"],"class":"reversible","doc":"Open the new-employee form if it is not open, ring one field and set it. Refused with the field\'s options.","id":"employee.fill","objects":["form","field","employee"]},{"claims":["saving * employee","adding * to payroll"],"class":"confirmed","doc":"Press Save on the new-employee form after the admin\'s yes: the employee is added and their prorated February pay joins the draft run.","id":"employee.save","objects":["employee"]},{"args":[{"doc":"BB-1007","name":"employee_id"},{"enum":["new","old"],"name":"regime"}],"claims":["switching * regime","moving * to the old regime","moving * to the new regime"],"class":"confirmed","doc":"Change the regime used for an employee\'s TDS after the admin\'s yes; February TDS in the draft is recomputed for the months left.","id":"regime.switch","objects":["regime"]},{"args":[{"doc":"A support request (something is wrong or needs a person) or a feature request (something Paynora does not do yet).","enum":["support","feature"],"name":"kind"},{"name":"subject"},{"doc":"The written summary the payroll team reads: what was asked, what was found, what is needed.","name":"summary"},{"name":"employee_id","optional":true}],"claims":["writing up * request","drafting * request","writing up * ticket"],"class":"reversible","doc":"Open the hand-off panel over the screen in front (a side panel; the page under it stays where it is) with the request written out. Nothing is sent.","id":"ticket.draft","objects":["ticket","request","summary"]},{"claims":["sending * ticket","raising * ticket"],"class":"confirmed","doc":"Send the request on screen to Paynora\'s payroll team after the admin\'s yes. The page answers with the TK- number.","id":"ticket.submit","objects":["ticket"]},{"args":[{"enum":["company","structure","import","leave","test_run","done"],"name":"step"}],"claims":["moving on to","next step"],"class":"navigate","doc":"Open a step of the setup wizard at /welcome and ring it.","id":"setup.step","objects":["step","setup"]},{"args":[{"doc":"A setup field by its name: company_name, legal_name, pan, tan, registered_office, pf_code, esi_code, pt_karnataka, pt_maharashtra, pay_cycle, basic_pct, hra_metro_pct, hra_non_metro_pct, lta_g5, lta_g6_up, pf_rule, esi_rule, el_per_year, cl_per_year, sl_per_year, el_carry_forward, attendance_cutoff, lop_rule.","name":"field"},{"name":"value"}],"claims":["filling in","putting in"],"class":"reversible","doc":"Open the step that holds the field (ringing the stepper), ring the field and set it. Refused with the field names when it is not a setup field.","id":"setup.fill","objects":["field","form","detail"]},{"claims":["running the test payroll","running a test"],"class":"reversible","doc":"Run the February 2026 test payroll with the engine over the imported employees and show its totals.","id":"setup.test_run","objects":["test","payroll","run"]},{"claims":["finishing * setup"],"class":"confirmed","doc":"Finish setup after the admin\'s yes and open the dashboard.","id":"setup.finish","objects":["setup"]},{"args":[{"doc":"BB-1030","name":"employee_id"},{"default":"payslips","enum":["payslips","tax","declarations","leave"],"name":"tab"},{"doc":"On payslips: the payslip\'s month, 2025-11; the latest when left out.","name":"month","optional":true},{"doc":"On payslips: the month to compare with, 2025-10.","name":"against","optional":true}],"claims":["opening * employee view","switching to * view"],"class":"navigate","doc":"Switch to the employee self-service view as that employee, on a tab; on payslips, a month\'s payslip, beside another month\'s when asked. The view stays until the admin leaves it.","id":"me.view","objects":["view","self-service"]}],"slices":[{"doc":"the screen in front: its path and title, and the employee it is about","fields":[{"name":"path"},{"name":"title"},{"name":"employee_id","optional":true},{"name":"tab","optional":true}],"id":"screen"},{"doc":"the last leave request decided","fields":[{"name":"request_id"},{"name":"decision"},{"name":"employee_id"},{"name":"lop_days","type":"number"}],"id":"leave"},{"doc":"the last claim changed","fields":[{"name":"claim_id"},{"name":"status"},{"name":"amount","type":"integer"}],"id":"claim"},{"doc":"the last employee added","fields":[{"name":"employee_id"},{"name":"name"},{"name":"gender"},{"name":"department"},{"name":"title"},{"name":"grade"},{"name":"location"},{"name":"joined"},{"name":"annual_ctc","type":"integer"},{"name":"tax_regime"},{"name":"email","private":true}],"id":"joiner"},{"doc":"the last regime change","fields":[{"name":"employee_id"},{"name":"regime"}],"id":"regime"},{"doc":"the last hand-off ticket sent","fields":[{"name":"ticket_id"},{"name":"subject"}],"id":"ticket"},{"doc":"the last payroll run approved","fields":[{"name":"run_id"},{"name":"status"}],"id":"run"},{"doc":"the setup wizard: the step in front and which fields hold something, by name","fields":[{"name":"step"},{"name":"filled","type":"array"},{"name":"imported","optional":true,"type":"integer"},{"name":"test_run","optional":true,"type":"boolean"},{"name":"finished","optional":true,"type":"boolean"}],"id":"setup"}],"stage":1}'
)
#: The spec's hash: a page reading another spec reports a different one.
SPEC_SHA256 = "40050a71fe0d02677896f87e1683f8e8d9cbce7127d637f0723c46262e36d7b8"


class GoArgs(BaseModel):
    """The arguments of ``app.go``."""

    page: str
    """One of the app's main pages, by its name in the sidebar: Dashboard, Employees, Payroll, Payslips, Leave, Reimbursements, Tax, Settings, Help, Setup. Refused with the names when it is not one."""


class ShowArgs(BaseModel):
    """The arguments of ``app.show``."""

    thing: str
    """A part of the screen in front, by the label it shows: a payslip line (Loss of pay, TDS, Net pay), a control (Switch regime, Approve), a panel (Old regime slabs)."""


class AppOpenArgs(BaseModel):
    """The arguments of ``app.open``."""

    path: str
    """An app path: /, /employees/BB-1030, /leave, /tax/regime/BB-1007, /me/BB-1030/payslips, /welcome."""


class PayslipCompareArgs(BaseModel):
    """The arguments of ``payslip.compare``."""

    employee_id: str
    """BB-1030"""
    month: str
    """The payslip's month, 2026-01."""
    against: str | None = None
    """The month to compare with, 2025-12; null shows the payslip alone."""


class RegimeCompareArgs(BaseModel):
    """The arguments of ``regime.compare``."""

    employee_id: str
    """BB-1007"""


class LeaveDecideArgs(BaseModel):
    """The arguments of ``leave.decide``."""

    request_id: str
    """LV-2412"""
    decision: Literal["approve", "reject"]


class FixArgs(BaseModel):
    """The arguments of ``claim.fix``."""

    claim_id: str
    """RB-3108"""
    amount: int
    """The corrected amount, the bill's amount."""


class ClaimDecideArgs(BaseModel):
    """The arguments of ``claim.decide``."""

    claim_id: str
    """RB-3109"""
    decision: Literal["approve", "reject"]


class ClaimOpenArgs(BaseModel):
    """The arguments of ``claim.open``."""

    claim_id: str
    """RB-3109"""


class EmployeeFillArgs(BaseModel):
    """The arguments of ``employee.fill``."""

    field: str
    """A field of the form by its name: name, email, gender, department, title, grade, location, joined, annual_ctc, tax_regime, manager_id."""
    value: str
    """As the form takes it: a location by its city, a date as 2026-02-16, CTC in rupees, regime new or old."""


class SaveArgs(BaseModel):
    """``employee.save`` takes none."""


class SwitchArgs(BaseModel):
    """The arguments of ``regime.switch``."""

    employee_id: str
    """BB-1007"""
    regime: Literal["new", "old"]


class DraftArgs(BaseModel):
    """The arguments of ``ticket.draft``."""

    kind: Literal["support", "feature"]
    """A support request (something is wrong or needs a person) or a feature request (something Paynora does not do yet)."""
    subject: str
    summary: str
    """The written summary the payroll team reads: what was asked, what was found, what is needed."""
    employee_id: str | None = None


class SubmitArgs(BaseModel):
    """``ticket.submit`` takes none."""


class StepArgs(BaseModel):
    """The arguments of ``setup.step``."""

    step: Literal["company", "structure", "import", "leave", "test_run", "done"]


class SetupFillArgs(BaseModel):
    """The arguments of ``setup.fill``."""

    field: str
    """A setup field by its name: company_name, legal_name, pan, tan, registered_office, pf_code, esi_code, pt_karnataka, pt_maharashtra, pay_cycle, basic_pct, hra_metro_pct, hra_non_metro_pct, lta_g5, lta_g6_up, pf_rule, esi_rule, el_per_year, cl_per_year, sl_per_year, el_carry_forward, attendance_cutoff, lop_rule."""
    value: str


class TestRunArgs(BaseModel):
    """``setup.test_run`` takes none."""


class FinishArgs(BaseModel):
    """``setup.finish`` takes none."""


class ViewArgs(BaseModel):
    """The arguments of ``me.view``."""

    employee_id: str
    """BB-1030"""
    tab: Literal["payslips", "tax", "declarations", "leave"] = "payslips"
    month: str | None = None
    """On payslips: the payslip's month, 2025-11; the latest when left out."""
    against: str | None = None
    """On payslips: the month to compare with, 2025-10."""


GO = Move(
    id="app.go",
    verb="go",
    cls=MoveClass.NAVIGATE,
    args=("page",),
    say="{go: Leave} as you take them to one of the app's pages.",
    claims=(
        "taking you to",
        "opening the * page",
        "आपको * पर ले चलती",
    ),
    objects=(
        "page",
        "screen",
        "पेज",
    ),
)
"""Open one of the sidebar's pages and ring its heading."""

SHOW = Move(
    id="app.show",
    verb="show",
    cls=MoveClass.LOOK,
    args=("thing",),
    say="{show: TDS} at the start of the sentence about that part of the screen; it scrolls into view and is ringed.",
)
"""Scroll to the data-stage-thing whose label matches and ring it. Refused with the labels on the screen."""

APP_OPEN = Move(
    id="app.open",
    verb=None,
    cls=MoveClass.NAVIGATE,
    args=("path",),
    claims=(
        "opening",
        "taking you to",
        "खोल रही",
    ),
    objects=(
        "page",
        "record",
        "profile",
        "screen",
    ),
)
"""Open any screen of the app by its path; ring its heading."""

PAYSLIP_COMPARE = Move(
    id="payslip.compare",
    verb=None,
    cls=MoveClass.NAVIGATE,
    args=(
        "employee_id",
        "month",
        "against",
    ),
    claims=(
        "opening * payslip",
        "pulling up * payslip",
        "comparing * payslip",
    ),
    objects=(
        "payslip",
        "पेस्लिप",
    ),
)
"""Open an employee's payslip for a month, side by side with another month and the difference per line."""

REGIME_COMPARE = Move(
    id="regime.compare",
    verb=None,
    cls=MoveClass.NAVIGATE,
    args=("employee_id",),
    claims=(
        "opening * regime",
        "comparing * regime",
        "comparing both regimes",
    ),
    objects=(
        "regime",
        "comparison",
        "रिजीम",
    ),
)
"""Open the regime comparison of one employee: both regimes' computations slab by slab, from the engine."""

LEAVE_DECIDE = Move(
    id="leave.decide",
    verb=None,
    cls=MoveClass.CONFIRMED,
    args=(
        "request_id",
        "decision",
    ),
    claims=(
        "approving * leave",
        "rejecting * leave",
    ),
    objects=("leave",),
)
"""Approve or reject a pending leave request, after the admin's spoken yes. Days beyond the balance become loss of pay in the February draft, recomputed with the engine."""

FIX = Move(
    id="claim.fix",
    verb=None,
    cls=MoveClass.CONFIRMED,
    args=(
        "claim_id",
        "amount",
    ),
    claims=(
        "fixing * claim",
        "correcting * claim",
    ),
    objects=(
        "claim",
        "reimbursement",
    ),
)
"""Correct a claim's amount to its bill and approve it into the February draft, after the admin's spoken yes."""

CLAIM_DECIDE = Move(
    id="claim.decide",
    verb=None,
    cls=MoveClass.CONFIRMED,
    args=(
        "claim_id",
        "decision",
    ),
    claims=(
        "approving * claim",
        "rejecting * claim",
    ),
    objects=(
        "claim",
        "reimbursement",
    ),
)
"""Approve (into the February draft) or reject a pending claim, after the admin's spoken yes."""

CLAIM_OPEN = Move(
    id="claim.open",
    verb=None,
    cls=MoveClass.NAVIGATE,
    args=("claim_id",),
    claims=(
        "opening * claim",
        "pulling up * claim",
    ),
    objects=(
        "claim",
        "reimbursement",
        "request",
    ),
)
"""Open one claim's detail panel on the Reimbursements screen: what was claimed beside the bill, and its Approve, Reject or Fix buttons."""

EMPLOYEE_FILL = Move(
    id="employee.fill",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "field",
        "value",
    ),
    claims=(
        "filling in",
        "adding * details",
    ),
    objects=(
        "form",
        "field",
        "employee",
    ),
)
"""Open the new-employee form if it is not open, ring one field and set it. Refused with the field's options."""

SAVE = Move(
    id="employee.save",
    verb=None,
    cls=MoveClass.CONFIRMED,
    claims=(
        "saving * employee",
        "adding * to payroll",
    ),
    objects=("employee",),
)
"""Press Save on the new-employee form after the admin's yes: the employee is added and their prorated February pay joins the draft run."""

SWITCH = Move(
    id="regime.switch",
    verb=None,
    cls=MoveClass.CONFIRMED,
    args=(
        "employee_id",
        "regime",
    ),
    claims=(
        "switching * regime",
        "moving * to the old regime",
        "moving * to the new regime",
    ),
    objects=("regime",),
)
"""Change the regime used for an employee's TDS after the admin's yes; February TDS in the draft is recomputed for the months left."""

DRAFT = Move(
    id="ticket.draft",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "kind",
        "subject",
        "summary",
        "employee_id",
    ),
    claims=(
        "writing up * request",
        "drafting * request",
        "writing up * ticket",
    ),
    objects=(
        "ticket",
        "request",
        "summary",
    ),
)
"""Open the hand-off panel over the screen in front (a side panel; the page under it stays where it is) with the request written out. Nothing is sent."""

SUBMIT = Move(
    id="ticket.submit",
    verb=None,
    cls=MoveClass.CONFIRMED,
    claims=(
        "sending * ticket",
        "raising * ticket",
    ),
    objects=("ticket",),
)
"""Send the request on screen to Paynora's payroll team after the admin's yes. The page answers with the TK- number."""

STEP = Move(
    id="setup.step",
    verb=None,
    cls=MoveClass.NAVIGATE,
    args=("step",),
    claims=(
        "moving on to",
        "next step",
    ),
    objects=(
        "step",
        "setup",
    ),
)
"""Open a step of the setup wizard at /welcome and ring it."""

SETUP_FILL = Move(
    id="setup.fill",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "field",
        "value",
    ),
    claims=(
        "filling in",
        "putting in",
    ),
    objects=(
        "field",
        "form",
        "detail",
    ),
)
"""Open the step that holds the field (ringing the stepper), ring the field and set it. Refused with the field names when it is not a setup field."""

TEST_RUN = Move(
    id="setup.test_run",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    claims=(
        "running the test payroll",
        "running a test",
    ),
    objects=(
        "test",
        "payroll",
        "run",
    ),
)
"""Run the February 2026 test payroll with the engine over the imported employees and show its totals."""

FINISH = Move(
    id="setup.finish",
    verb=None,
    cls=MoveClass.CONFIRMED,
    claims=("finishing * setup",),
    objects=("setup",),
)
"""Finish setup after the admin's yes and open the dashboard."""

VIEW = Move(
    id="me.view",
    verb=None,
    cls=MoveClass.NAVIGATE,
    args=(
        "employee_id",
        "tab",
        "month",
        "against",
    ),
    claims=(
        "opening * employee view",
        "switching to * view",
    ),
    objects=(
        "view",
        "self-service",
    ),
)
"""Switch to the employee self-service view as that employee, on a tab; on payslips, a month's payslip, beside another month's when asked. The view stays until the admin leaves it."""

MOVES = MoveSet(
    (
        GO,
        SHOW,
        APP_OPEN,
        PAYSLIP_COMPARE,
        REGIME_COMPARE,
        LEAVE_DECIDE,
        FIX,
        CLAIM_DECIDE,
        CLAIM_OPEN,
        EMPLOYEE_FILL,
        SAVE,
        SWITCH,
        DRAFT,
        SUBMIT,
        STEP,
        SETUP_FILL,
        TEST_RUN,
        FINISH,
        VIEW,
    )
)

#: The line each cue is taught with, in the spec's order.
PROMPT_LINES: tuple[str, ...] = (
    "{go: Leave} as you take them to one of the app's pages.",
    "{show: TDS} at the start of the sentence about that part of the screen; it scrolls into view and is ringed.",
)

#: The slices of the page's state a read may name.
SliceId = Literal["screen", "leave", "claim", "joiner", "regime", "ticket", "run", "setup"]


class ReadRequest(BaseModel):
    """What the read tool takes: the slice to read, from the brain's mirror."""

    slice: SliceId = Field(
        description="Which part of their screen to read. screen: the screen in front: its path and title, and the employee it is about; leave: the last leave request decided; claim: the last claim changed; joiner: the last employee added; regime: the last regime change; ticket: the last hand-off ticket sent; run: the last payroll run approved; setup: the setup wizard: the step in front and which fields hold something, by name."
    )
