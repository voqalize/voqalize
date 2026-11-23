# Generated from payroll_site/frontend/src/stage/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
#   voqalize stage gen payroll_site/frontend/src/stage/scene.json --py payroll_site/backend/stage_gen.py --ts payroll_site/frontend/src/stage/scene.gen.ts
"""The moves of paynora_site, from its Stage Spec."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from voqalize.sdk.stage import Move, MoveClass, MoveSet, StageSpec, load_spec

#: The spec itself, carried here so the brain never reads the JSON at run
#: time (and a deploy that ships this file ships the spec with it).
SPEC: StageSpec = load_spec(
    '{"events":[{"id":"screen.viewed","note":"{by} opened {title}","op":"set","react":"silent","slice":"screen"},{"id":"lead.changed","note":"{by} changed the lead card: {field}","slice":"lead"},{"id":"pricing.changed","note":"{by} set the calculator to {headcount} employees, {billing} billing: {plan}, {monthly} a month before GST","op":"set","slice":"pricing"},{"id":"booking.changed","note":"{by} changed the booking: {status}","slice":"booking"},{"ask":"The visitor confirmed the demo booking themselves. Thank them, say the reference and that an invite is on its way, in one line.","id":"booking.confirmed","note":"{by} confirmed the demo booking, reference {reference}","react":"speak","slice":"booking"}],"id":"paynora_site","languages":["en","hi"],"moves":[{"args":[{"doc":"A page of the site: /, /modules, /modules/<module id>, /tax, /customers, /pricing, /book-demo.","name":"path"}],"claims":["taking you to","opening the * page","आपको * पेज पर"],"class":"navigate","doc":"Open a page of the site, ringing the link that leads there first.","id":"site.go","objects":["page","pricing","calendar","पेज","प्राइसिंग"]},{"args":[{"doc":"A section by its spoken name: pain points, modules, tax showcase, customer quotes, new regime slabs, old regime slabs, worked example, deductions, PF ESI PT, TDS and Form 16, plans, calculator, FAQ, calendar, booking form.","name":"thing"}],"claims":["showing you the","let me show you the","दिखाता हूँ"],"class":"look","doc":"Scroll to a section of the page in front and ring it. Refused with the sections the page has.","id":"site.show","objects":["section","example","slab","table"],"say":"{show: tax showcase} at the start of the sentence about a section of the page in front; it scrolls there and is ringed.","verb":"show"},{"args":[{"doc":"A module id: payroll, employees, leave, payslips, tax, compliance, reimbursements, declarations, multi_entity, api.","name":"id"}],"class":"look","doc":"Ring one module card on the page in front (the home page\'s grid or the modules page).","id":"modules.show","say":"{module: declarations} at the start of the sentence about one module; its card is ringed.","verb":"module"},{"args":[{"doc":"Module ids that fit what the visitor said, in the order they came up.","name":"ids","type":"array"}],"claims":["highlighting the modules","marking the modules"],"class":"reversible","doc":"Ring each module card in turn and mark it \'Fits your team\'. Replaces the marked set.","id":"modules.highlight","objects":["module","मॉड्यूल"]},{"args":[{"enum":["company","name","headcount","states","current_tool","pains","recommended_plan","email"],"name":"field"},{"doc":"The field\'s value: a name, a number, a tool id, a plan id, an email the visitor confirmed.","name":"value","optional":true},{"doc":"For states and pains: the full list, state names or pain ids.","name":"items","optional":true,"type":"array"}],"claims":["noting that down","adding that to your","putting that on your"],"class":"reversible","doc":"Fill one field of the lead card on the home page, ringing it first. Opens the card when it is closed.","id":"lead.fill","objects":["lead card","brief","card"]},{"args":[{"name":"headcount","type":"integer"},{"doc":"Module ids beyond the plan\'s core six, ticked on the calculator.","name":"modules","type":"array"},{"default":"monthly","enum":["monthly","annual"],"name":"billing"},{"default":false,"name":"filing","type":"boolean"}],"claims":["setting the calculator","putting * into the calculator","working out the price"],"class":"reversible","doc":"Set the pricing calculator\'s controls one by one (headcount, each module checkbox, billing, the filing add-on), ringing each control that changes, then ring the breakdown. Opens /pricing first when the visitor is elsewhere.","id":"pricing.set","objects":["calculator","price","कैलकुलेटर"]},{"args":[{"enum":["base","minimum","filing","subtotal","discount","gst","total","annual","setup"],"name":"item"}],"class":"look","doc":"Ring one line of the calculator\'s breakdown.","id":"pricing.line","say":"{line: minimum} at the start of the sentence about one line of the price breakdown; that line is ringed.","verb":"line"},{"args":[{"doc":"A business day on the calendar, YYYY-MM-DD.","name":"day"}],"claims":["opening the * calendar","pulling up the slots"],"class":"reversible","doc":"Select a day on the sales calendar (opening /book-demo first when needed) and ring its free slots.","id":"calendar.show","objects":["calendar","slot","कैलेंडर","स्लॉट"]},{"args":[{"doc":"A free slot\'s id, 2026-11-19-1030-kavya.","name":"slot_id"}],"claims":["picking the * slot","holding the * slot"],"class":"reversible","doc":"Select one free slot on the calendar, ringing it first. Refused for a taken slot, with the free ones.","id":"booking.pick","objects":["slot","स्लॉट"]},{"args":[{"enum":["company","name","headcount","topic","email"],"name":"field"},{"name":"value"}],"claims":["filling in the","putting your * on the form"],"class":"reversible","doc":"Fill one field of the booking form, ringing it first.","id":"booking.fill","objects":["form","booking form","फ़ॉर्म"]},{"claims":["booking it now","confirming your demo"],"class":"confirmed","doc":"Press Confirm booking, after the visitor said yes. Refused, naming what is missing, while the form is incomplete.","id":"booking.confirm","objects":["booking","बुकिंग"]}],"slices":[{"doc":"the page the visitor is on","fields":[{"name":"path"},{"name":"title"}],"id":"screen"},{"doc":"the lead card on the home page, as filled so far","fields":[{"name":"company","optional":true},{"name":"name","optional":true},{"name":"headcount","optional":true,"type":"integer"},{"name":"states","type":"array"},{"name":"current_tool","optional":true},{"name":"pains","type":"array"},{"name":"recommended_plan","optional":true},{"doc":"Module cards marked as a fit.","name":"modules","type":"array"},{"name":"has_email","type":"boolean"},{"name":"email","optional":true,"private":true},{"doc":"The field that just changed.","name":"field","optional":true}],"id":"lead"},{"doc":"the pricing calculator\'s controls and the plan they give","fields":[{"name":"headcount","type":"integer"},{"name":"modules","type":"array"},{"name":"billing"},{"name":"filing","type":"boolean"},{"name":"plan"},{"doc":"The monthly fee before GST, in rupees.","name":"monthly","type":"integer"}],"id":"pricing"},{"doc":"the demo booking: the day in front, the slot picked, which form fields hold something, and the reference once confirmed","fields":[{"name":"day","optional":true},{"name":"slot_id","optional":true},{"name":"filled","type":"array"},{"name":"status"},{"name":"reference","optional":true}],"id":"booking"}],"stage":1}'
)
#: The spec's hash: a page reading another spec reports a different one.
SPEC_SHA256 = "19d39696cc2ebb9a38670fe2aa865503e67f230705694d4fbed1f6fd2aad6b0d"


class GoArgs(BaseModel):
    """The arguments of ``site.go``."""

    path: str
    """A page of the site: /, /modules, /modules/<module id>, /tax, /customers, /pricing, /book-demo."""


class SiteShowArgs(BaseModel):
    """The arguments of ``site.show``."""

    thing: str
    """A section by its spoken name: pain points, modules, tax showcase, customer quotes, new regime slabs, old regime slabs, worked example, deductions, PF ESI PT, TDS and Form 16, plans, calculator, FAQ, calendar, booking form."""


class ModulesShowArgs(BaseModel):
    """The arguments of ``modules.show``."""

    id: str
    """A module id: payroll, employees, leave, payslips, tax, compliance, reimbursements, declarations, multi_entity, api."""


class HighlightArgs(BaseModel):
    """The arguments of ``modules.highlight``."""

    ids: list[str]
    """Module ids that fit what the visitor said, in the order they came up."""


class LeadFillArgs(BaseModel):
    """The arguments of ``lead.fill``."""

    field: Literal[
        "company",
        "name",
        "headcount",
        "states",
        "current_tool",
        "pains",
        "recommended_plan",
        "email",
    ]
    value: str | None = None
    """The field's value: a name, a number, a tool id, a plan id, an email the visitor confirmed."""
    items: list[str] | None = None
    """For states and pains: the full list, state names or pain ids."""


class SetArgs(BaseModel):
    """The arguments of ``pricing.set``."""

    headcount: int
    modules: list[str]
    """Module ids beyond the plan's core six, ticked on the calculator."""
    billing: Literal["monthly", "annual"] = "monthly"
    filing: bool = False


class LineArgs(BaseModel):
    """The arguments of ``pricing.line``."""

    item: Literal[
        "base", "minimum", "filing", "subtotal", "discount", "gst", "total", "annual", "setup"
    ]


class CalendarShowArgs(BaseModel):
    """The arguments of ``calendar.show``."""

    day: str
    """A business day on the calendar, YYYY-MM-DD."""


class PickArgs(BaseModel):
    """The arguments of ``booking.pick``."""

    slot_id: str
    """A free slot's id, 2026-11-19-1030-kavya."""


class BookingFillArgs(BaseModel):
    """The arguments of ``booking.fill``."""

    field: Literal["company", "name", "headcount", "topic", "email"]
    value: str


class ConfirmArgs(BaseModel):
    """``booking.confirm`` takes none."""


GO = Move(
    id="site.go",
    verb=None,
    cls=MoveClass.NAVIGATE,
    args=("path",),
    claims=(
        "taking you to",
        "opening the * page",
        "आपको * पेज पर",
    ),
    objects=(
        "page",
        "pricing",
        "calendar",
        "पेज",
        "प्राइसिंग",
    ),
)
"""Open a page of the site, ringing the link that leads there first."""

SITE_SHOW = Move(
    id="site.show",
    verb="show",
    cls=MoveClass.LOOK,
    args=("thing",),
    say="{show: tax showcase} at the start of the sentence about a section of the page in front; it scrolls there and is ringed.",
    claims=(
        "showing you the",
        "let me show you the",
        "दिखाता हूँ",
    ),
    objects=(
        "section",
        "example",
        "slab",
        "table",
    ),
)
"""Scroll to a section of the page in front and ring it. Refused with the sections the page has."""

MODULES_SHOW = Move(
    id="modules.show",
    verb="module",
    cls=MoveClass.LOOK,
    args=("id",),
    say="{module: declarations} at the start of the sentence about one module; its card is ringed.",
)
"""Ring one module card on the page in front (the home page's grid or the modules page)."""

HIGHLIGHT = Move(
    id="modules.highlight",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=("ids",),
    claims=(
        "highlighting the modules",
        "marking the modules",
    ),
    objects=(
        "module",
        "मॉड्यूल",
    ),
)
"""Ring each module card in turn and mark it 'Fits your team'. Replaces the marked set."""

LEAD_FILL = Move(
    id="lead.fill",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "field",
        "value",
        "items",
    ),
    claims=(
        "noting that down",
        "adding that to your",
        "putting that on your",
    ),
    objects=(
        "lead card",
        "brief",
        "card",
    ),
)
"""Fill one field of the lead card on the home page, ringing it first. Opens the card when it is closed."""

SET = Move(
    id="pricing.set",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "headcount",
        "modules",
        "billing",
        "filing",
    ),
    claims=(
        "setting the calculator",
        "putting * into the calculator",
        "working out the price",
    ),
    objects=(
        "calculator",
        "price",
        "कैलकुलेटर",
    ),
)
"""Set the pricing calculator's controls one by one (headcount, each module checkbox, billing, the filing add-on), ringing each control that changes, then ring the breakdown. Opens /pricing first when the visitor is elsewhere."""

LINE = Move(
    id="pricing.line",
    verb="line",
    cls=MoveClass.LOOK,
    args=("item",),
    say="{line: minimum} at the start of the sentence about one line of the price breakdown; that line is ringed.",
)
"""Ring one line of the calculator's breakdown."""

CALENDAR_SHOW = Move(
    id="calendar.show",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=("day",),
    claims=(
        "opening the * calendar",
        "pulling up the slots",
    ),
    objects=(
        "calendar",
        "slot",
        "कैलेंडर",
        "स्लॉट",
    ),
)
"""Select a day on the sales calendar (opening /book-demo first when needed) and ring its free slots."""

PICK = Move(
    id="booking.pick",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=("slot_id",),
    claims=(
        "picking the * slot",
        "holding the * slot",
    ),
    objects=(
        "slot",
        "स्लॉट",
    ),
)
"""Select one free slot on the calendar, ringing it first. Refused for a taken slot, with the free ones."""

BOOKING_FILL = Move(
    id="booking.fill",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "field",
        "value",
    ),
    claims=(
        "filling in the",
        "putting your * on the form",
    ),
    objects=(
        "form",
        "booking form",
        "फ़ॉर्म",
    ),
)
"""Fill one field of the booking form, ringing it first."""

CONFIRM = Move(
    id="booking.confirm",
    verb=None,
    cls=MoveClass.CONFIRMED,
    claims=(
        "booking it now",
        "confirming your demo",
    ),
    objects=(
        "booking",
        "बुकिंग",
    ),
)
"""Press Confirm booking, after the visitor said yes. Refused, naming what is missing, while the form is incomplete."""

MOVES = MoveSet(
    (
        GO,
        SITE_SHOW,
        MODULES_SHOW,
        HIGHLIGHT,
        LEAD_FILL,
        SET,
        LINE,
        CALENDAR_SHOW,
        PICK,
        BOOKING_FILL,
        CONFIRM,
    )
)

#: The line each cue is taught with, in the spec's order.
PROMPT_LINES: tuple[str, ...] = (
    "{show: tax showcase} at the start of the sentence about a section of the page in front; it scrolls there and is ringed.",
    "{module: declarations} at the start of the sentence about one module; its card is ringed.",
    "{line: minimum} at the start of the sentence about one line of the price breakdown; that line is ringed.",
)

#: The slices of the page's state a read may name.
SliceId = Literal["screen", "lead", "pricing", "booking"]


class ReadRequest(BaseModel):
    """What the read tool takes: the slice to read, from the brain's mirror."""

    slice: SliceId = Field(
        description="Which part of their screen to read. screen: the page the visitor is on; lead: the lead card on the home page, as filled so far; pricing: the pricing calculator's controls and the plan they give; booking: the demo booking: the day in front, the slot picked, which form fields hold something, and the reference once confirmed."
    )
