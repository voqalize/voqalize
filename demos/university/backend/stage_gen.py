# Generated from university/frontend/src/stage/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
#   voqalize stage gen university/frontend/src/stage/scene.json --py university/backend/stage_gen.py --ts university/frontend/src/stage/scene.gen.ts
"""The moves of varenya_university, from its Stage Spec."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from voqalize.sdk.stage import Move, MoveClass, MoveSet, StageSpec, load_spec

#: The spec itself, carried here so the brain never reads the JSON at run
#: time (and a deploy that ships this file ships the spec with it).
SPEC: StageSpec = load_spec(
    '{"events":[{"doc":"Filters, picks or the comparison changed.","id":"catalogue.changed","note":"{by} changed the programme finder: {count} programmes match","op":"set","slice":"catalogue"},{"doc":"A field of the application was filled or changed.","id":"application.changed","note":"{by} filled {field} on the application","slice":"application"},{"doc":"The application moved to another step.","id":"application.step_reached","note":"{by} is on step {step} of the application","slice":"application"},{"ask":"congratulate them in one line, give the application number and say what happens next","doc":"The applicant pressed Pay and submit.","id":"application.submitted","note":"{by} paid the application fee and submitted application {reference}","react":"speak","slice":"application"}],"id":"varenya_university","languages":["en","hi"],"moves":[{"args":[{"doc":"A filter group of the programme finder: Level, School, Mode, Campus, Fee, Hours.","name":"facet"},{"doc":"One option of that group as the finder labels it: Postgraduate, Business, Online, Pune, Under ₹1 lakh, Up to 8 hrs a week.","name":"value"}],"claims":["filtering","narrowing it down","ticking"],"class":"reversible","doc":"Tick one option in the programme finder\'s sidebar: the box is ringed, ticked, and the list narrows. Refused with the group\'s options when the value is not one of them. Opens /programs first when the finder is not on screen.","id":"catalogue.filter","objects":["filter","filters","programme","programmes","list"],"say":"{filter: Level | Postgraduate} right before the words that give the reason, one option per cue: \\"Since you already have a degree, postgraduate.\\"","verb":"filter"},{"args":[{"doc":"The filter group to clear, or nothing for every filter.","name":"facet","optional":true}],"class":"reversible","doc":"Untick one group\'s options in the programme finder, or all of them.","id":"catalogue.clear","say":"{clear: Fee} takes the fee filter off; {clear} takes every filter off.","verb":"clear"},{"args":[{"doc":"A programme id from the catalogue, btech-cse.","name":"first"},{"doc":"A second programme id.","name":"second","optional":true},{"doc":"A third programme id.","name":"third","optional":true}],"claims":["shortlisting"],"class":"reversible","doc":"Mark two or three programmes as the advisor\'s picks: each card is ringed in turn and badged 1, 2, 3, and the shortlist tray shows them. Replaces the previous picks.","id":"catalogue.pick","objects":["shortlist"],"say":"{pick: online-mba | pgd-data-analytics} when you name the two or three programmes that fit; each card is ringed and marked as your pick.","verb":"pick"},{"args":[{"doc":"A programme id.","name":"first"},{"doc":"Another programme id.","name":"second"},{"doc":"A third programme id.","name":"third","optional":true}],"claims":["comparing them","putting them side by side"],"class":"look","doc":"Open the side-by-side comparison of two or three programmes: duration, mode, campus, fee per year and in total, hours a week, eligibility, selection, next deadline, scholarships and outcomes.","id":"catalogue.compare","objects":["comparison"],"say":"{compare: online-mba | emba} as you start comparing them; the comparison opens side by side.","verb":"compare"},{"args":[{"doc":"A programme id from the catalogue, mba.","name":"program"},{"doc":"A section of the programme page to scroll to and ring once it is open: overview, eligibility, selection, fees, scholarships, deadlines, outcomes, curriculum, highlights.","name":"section","optional":true}],"claims":["opening the","pulling up"],"class":"navigate","doc":"Open a programme\'s page, or scroll the page already open, and ring the section named (or the title).","id":"site.open","objects":["programme page","page","curriculum","syllabus","modules"],"say":"{open: mba | curriculum} when you start talking about one programme\'s details; its page opens at that section (title alone without one).","verb":"open"},{"args":[{"doc":"home, programs, admissions, scholarships, campus-life, apply, schools, or schools/<school id>: schools/law.","name":"page"}],"class":"navigate","doc":"Go to a page of the university site.","id":"site.go","say":"{go: scholarships} when the conversation moves to another part of the site; that page opens.","verb":"go"},{"args":[{"doc":"A section of the page in front by its name: fees, eligibility, selection, deadlines, scholarships, outcomes, curriculum, highlights, overview, hostel, loans, documents, vusat, process, faqs, refund, instalments.","name":"target"}],"class":"look","doc":"Scroll to a section of the page in front and ring it. Refused with the sections the page has.","id":"site.show","say":"{show: hostel} as you start talking about that section; it scrolls into view and is ringed.","verb":"show"},{"args":[{"doc":"A field of the application by its name: full_name, gender, city, state, class12_stream, class12_percent, entrance_exam, program, campus, intake, hostel, room_type, scholarship, doc_class10, pay_method…","name":"field"},{"doc":"The value: an option id for a choice (science_pcm, pune, twin_ac, upi), a number for marks (92.4), a programme id for program, a scholarship id for scholarship, uploaded or later for a document, the words said for a text field.","name":"value"}],"claims":["filling in","putting down","noting down"],"class":"reversible","doc":"Set one field of the application as the voice says it: the step opens, the input is ringed and filled. Opens /apply first when the form is not on screen. Refused with the field\'s options when the value is not one of them.","id":"apply.fill","objects":["application","form","field"],"say":"{fill: class12_percent | 92.4} at the start of the sentence that says it, one field per cue: \\"92.4 percent in Class 12, noted.\\"","verb":"fill"},{"args":[{"doc":"1 personal details, 2 academics, 3 programme choice, 4 documents, 5 application fee.","name":"step","type":"integer"}],"class":"look","doc":"Open a step of the application and ring it.","id":"apply.step","say":"{step: 3} as you start on that step of the application; it opens and is ringed.","verb":"step"},{"class":"reversible","doc":"Check the step in front as Continue does and open the next one. Refused, naming the required fields still empty.","id":"apply.next","say":"{next} moves the application on to its next step, as Continue does.","verb":"next"}],"slices":[{"doc":"the programme finder: the filters ticked, how many programmes match, the first ones listed, the advisor\'s picks and the comparison open","fields":[{"doc":"Ticked options as Group: Option.","name":"filters","type":"array"},{"doc":"How many programmes match.","name":"count","type":"integer"},{"doc":"The ids of the first programmes listed.","name":"top","type":"array"},{"doc":"The ids marked as picks.","name":"picks","type":"array"},{"doc":"The ids in the open comparison.","name":"compared","type":"array"}],"id":"catalogue","window":12},{"doc":"the application form: the step in front, which fields hold something (by name), and the programme, academic and hostel choices","fields":[{"name":"step","optional":true,"type":"integer"},{"doc":"The field that just changed.","name":"field","optional":true},{"doc":"Names of the fields that hold something.","name":"filled","type":"array"},{"doc":"Required fields of the step in front still empty.","name":"missing","type":"array"},{"name":"program","optional":true},{"name":"campus","optional":true},{"name":"intake","optional":true},{"name":"class12_stream","optional":true},{"name":"class12_percent","optional":true},{"name":"graduation_percent","optional":true},{"name":"entrance_exam","optional":true},{"name":"hostel","optional":true},{"name":"room_type","optional":true},{"name":"scholarship","optional":true},{"doc":"The application number, once paid: VRN-27-48213.","name":"reference","optional":true}],"id":"application"}],"stage":1}'
)
#: The spec's hash: a page reading another spec reports a different one.
SPEC_SHA256 = "16265cb4023954893e427488f9a90fec71c4b8428db865b5fb715a969af1f74e"


class FilterArgs(BaseModel):
    """The arguments of ``catalogue.filter``."""

    facet: str
    """A filter group of the programme finder: Level, School, Mode, Campus, Fee, Hours."""
    value: str
    """One option of that group as the finder labels it: Postgraduate, Business, Online, Pune, Under ₹1 lakh, Up to 8 hrs a week."""


class ClearArgs(BaseModel):
    """The arguments of ``catalogue.clear``."""

    facet: str | None = None
    """The filter group to clear, or nothing for every filter."""


class PickArgs(BaseModel):
    """The arguments of ``catalogue.pick``."""

    first: str
    """A programme id from the catalogue, btech-cse."""
    second: str | None = None
    """A second programme id."""
    third: str | None = None
    """A third programme id."""


class CompareArgs(BaseModel):
    """The arguments of ``catalogue.compare``."""

    first: str
    """A programme id."""
    second: str
    """Another programme id."""
    third: str | None = None
    """A third programme id."""


class OpenArgs(BaseModel):
    """The arguments of ``site.open``."""

    program: str
    """A programme id from the catalogue, mba."""
    section: str | None = None
    """A section of the programme page to scroll to and ring once it is open: overview, eligibility, selection, fees, scholarships, deadlines, outcomes, curriculum, highlights."""


class GoArgs(BaseModel):
    """The arguments of ``site.go``."""

    page: str
    """home, programs, admissions, scholarships, campus-life, apply, schools, or schools/<school id>: schools/law."""


class ShowArgs(BaseModel):
    """The arguments of ``site.show``."""

    target: str
    """A section of the page in front by its name: fees, eligibility, selection, deadlines, scholarships, outcomes, curriculum, highlights, overview, hostel, loans, documents, vusat, process, faqs, refund, instalments."""


class FillArgs(BaseModel):
    """The arguments of ``apply.fill``."""

    field: str
    """A field of the application by its name: full_name, gender, city, state, class12_stream, class12_percent, entrance_exam, program, campus, intake, hostel, room_type, scholarship, doc_class10, pay_method…"""
    value: str
    """The value: an option id for a choice (science_pcm, pune, twin_ac, upi), a number for marks (92.4), a programme id for program, a scholarship id for scholarship, uploaded or later for a document, the words said for a text field."""


class StepArgs(BaseModel):
    """The arguments of ``apply.step``."""

    step: int
    """1 personal details, 2 academics, 3 programme choice, 4 documents, 5 application fee."""


class NextArgs(BaseModel):
    """``apply.next`` takes none."""


FILTER = Move(
    id="catalogue.filter",
    verb="filter",
    cls=MoveClass.REVERSIBLE,
    args=(
        "facet",
        "value",
    ),
    say='{filter: Level | Postgraduate} right before the words that give the reason, one option per cue: "Since you already have a degree, postgraduate."',
    claims=(
        "filtering",
        "narrowing it down",
        "ticking",
    ),
    objects=(
        "filter",
        "filters",
        "programme",
        "programmes",
        "list",
    ),
)
"""Tick one option in the programme finder's sidebar: the box is ringed, ticked, and the list narrows. Refused with the group's options when the value is not one of them. Opens /programs first when the finder is not on screen."""

CLEAR = Move(
    id="catalogue.clear",
    verb="clear",
    cls=MoveClass.REVERSIBLE,
    args=("facet",),
    say="{clear: Fee} takes the fee filter off; {clear} takes every filter off.",
)
"""Untick one group's options in the programme finder, or all of them."""

PICK = Move(
    id="catalogue.pick",
    verb="pick",
    cls=MoveClass.REVERSIBLE,
    args=(
        "first",
        "second",
        "third",
    ),
    say="{pick: online-mba | pgd-data-analytics} when you name the two or three programmes that fit; each card is ringed and marked as your pick.",
    claims=("shortlisting",),
    objects=("shortlist",),
)
"""Mark two or three programmes as the advisor's picks: each card is ringed in turn and badged 1, 2, 3, and the shortlist tray shows them. Replaces the previous picks."""

COMPARE = Move(
    id="catalogue.compare",
    verb="compare",
    cls=MoveClass.LOOK,
    args=(
        "first",
        "second",
        "third",
    ),
    say="{compare: online-mba | emba} as you start comparing them; the comparison opens side by side.",
    claims=(
        "comparing them",
        "putting them side by side",
    ),
    objects=("comparison",),
)
"""Open the side-by-side comparison of two or three programmes: duration, mode, campus, fee per year and in total, hours a week, eligibility, selection, next deadline, scholarships and outcomes."""

OPEN = Move(
    id="site.open",
    verb="open",
    cls=MoveClass.NAVIGATE,
    args=(
        "program",
        "section",
    ),
    say="{open: mba | curriculum} when you start talking about one programme's details; its page opens at that section (title alone without one).",
    claims=(
        "opening the",
        "pulling up",
    ),
    objects=(
        "programme page",
        "page",
        "curriculum",
        "syllabus",
        "modules",
    ),
)
"""Open a programme's page, or scroll the page already open, and ring the section named (or the title)."""

GO = Move(
    id="site.go",
    verb="go",
    cls=MoveClass.NAVIGATE,
    args=("page",),
    say="{go: scholarships} when the conversation moves to another part of the site; that page opens.",
)
"""Go to a page of the university site."""

SHOW = Move(
    id="site.show",
    verb="show",
    cls=MoveClass.LOOK,
    args=("target",),
    say="{show: hostel} as you start talking about that section; it scrolls into view and is ringed.",
)
"""Scroll to a section of the page in front and ring it. Refused with the sections the page has."""

FILL = Move(
    id="apply.fill",
    verb="fill",
    cls=MoveClass.REVERSIBLE,
    args=(
        "field",
        "value",
    ),
    say='{fill: class12_percent | 92.4} at the start of the sentence that says it, one field per cue: "92.4 percent in Class 12, noted."',
    claims=(
        "filling in",
        "putting down",
        "noting down",
    ),
    objects=(
        "application",
        "form",
        "field",
    ),
)
"""Set one field of the application as the voice says it: the step opens, the input is ringed and filled. Opens /apply first when the form is not on screen. Refused with the field's options when the value is not one of them."""

STEP = Move(
    id="apply.step",
    verb="step",
    cls=MoveClass.LOOK,
    args=("step",),
    say="{step: 3} as you start on that step of the application; it opens and is ringed.",
)
"""Open a step of the application and ring it."""

NEXT = Move(
    id="apply.next",
    verb="next",
    cls=MoveClass.REVERSIBLE,
    say="{next} moves the application on to its next step, as Continue does.",
)
"""Check the step in front as Continue does and open the next one. Refused, naming the required fields still empty."""

MOVES = MoveSet(
    (
        FILTER,
        CLEAR,
        PICK,
        COMPARE,
        OPEN,
        GO,
        SHOW,
        FILL,
        STEP,
        NEXT,
    )
)

#: The line each cue is taught with, in the spec's order.
PROMPT_LINES: tuple[str, ...] = (
    '{filter: Level | Postgraduate} right before the words that give the reason, one option per cue: "Since you already have a degree, postgraduate."',
    "{clear: Fee} takes the fee filter off; {clear} takes every filter off.",
    "{pick: online-mba | pgd-data-analytics} when you name the two or three programmes that fit; each card is ringed and marked as your pick.",
    "{compare: online-mba | emba} as you start comparing them; the comparison opens side by side.",
    "{open: mba | curriculum} when you start talking about one programme's details; its page opens at that section (title alone without one).",
    "{go: scholarships} when the conversation moves to another part of the site; that page opens.",
    "{show: hostel} as you start talking about that section; it scrolls into view and is ringed.",
    '{fill: class12_percent | 92.4} at the start of the sentence that says it, one field per cue: "92.4 percent in Class 12, noted."',
    "{step: 3} as you start on that step of the application; it opens and is ringed.",
    "{next} moves the application on to its next step, as Continue does.",
)

#: The slices of the page's state a read may name.
SliceId = Literal["catalogue", "application"]


class ReadRequest(BaseModel):
    """What the read tool takes: the slice to read, from the brain's mirror."""

    slice: SliceId = Field(
        description="Which part of their screen to read. catalogue: the programme finder: the filters ticked, how many programmes match, the first ones listed, the advisor's picks and the comparison open; application: the application form: the step in front, which fields hold something (by name), and the programme, academic and hostel choices."
    )
