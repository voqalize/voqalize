# Generated from explora/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
#   voqalize stage gen explora/scene.json --py explora/backend/stage_gen.py --ts explora/extension/src/scene.gen.ts
"""The moves of explora, from its Stage Spec."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from voqalize.sdk.stage import Move, MoveClass, MoveSet, StageSpec, load_spec

#: The spec itself, carried here so the brain never reads the JSON at run
#: time (and a deploy that ships this file ships the spec with it).
SPEC: StageSpec = load_spec(
    '{"events":[{"doc":"The tab in front loaded a page, or came to the front. Folded in silence: the brain reads the page in with the next thing the visitor says.","id":"page.changed","op":"set","slice":"page"},{"doc":"The booking calendar or the rooms changed, by the visitor or a move. The brain writes its own line for it.","id":"stay.changed","op":"set","slice":"stay"},{"ask":"The visitor has been filling in the enquiry form by themselves. If they paused with required fields still empty, offer once, in one short sentence, to fill in the rest for them; if it is complete, say they can tick I\'m not a robot and you will send it. Never read back what they typed.","doc":"The enquiry form changed: a field filled or emptied, the reCAPTCHA ticked. The brain writes its own line for it; done by the visitor, the agent may also speak up about it once they pause.","id":"enquiry.changed","op":"set","react":"speak","slice":"enquiry"}],"id":"explora","languages":["en","es"],"moves":[{"args":[{"doc":"A heading, tab or accordion as the page writes it, or words on it.","name":"target"}],"class":"look","doc":"Scroll to a heading, open a tab or accordion, or ring words, on the page in front.","id":"core.show","say":"{show: Heading} scrolls to a heading on the page they are on, or are taken to by a page cue, and rings it. Use the heading exactly as the site pages list or the screen lines spell it. With the label of one of the page\'s tabs or accordions (\\"Patagonia [Argentina + Chile]\\"), it opens it. With words that are not a heading, it rings those words: a room, an exploration, a lodge\'s name.","verb":"show"},{"args":[{"doc":"The question as the page writes it.","name":"question"}],"class":"look","doc":"Open a question\'s accordion and ring it.","id":"core.faq","say":"{faq: Question} opens that question\'s accordion on the page and rings it.","verb":"faq"},{"args":[{"doc":"A www.explora.com path.","name":"path"},{"doc":"Words of his still to be heard before the page may go (the holder\'s pacing).","name":"after_words","optional":true,"type":"integer"}],"class":"navigate","doc":"Open a www.explora.com page in the tab in front, once his voice has said\\n``after_words`` words: a full page load. The page reports ``page_changed``.","id":"explora.navigate","notes":["A page cue is not a cue on Explora: every page is a full page load, so the brain splits his reply there and sends this itself, once the words before it are said."]},{"args":[{"enum":["en","es"],"name":"language"}],"class":"navigate","doc":"Load the page in front\'s own twin in ``language``, once his voice is quiet;\\nrefused when it has none.","id":"explora.twin"},{"args":[{"doc":"The lodge\'s code on the booking site, such as EATA.","name":"hotel_code"},{"doc":"The arrival day.","name":"date","optional":true},{"doc":"The month the calendar shows.","name":"month","optional":true},{"name":"nights","optional":true,"type":"integer"},{"doc":"Go on to the rooms and rates.","name":"rooms","optional":true,"type":"boolean"},{"enum":["EN","ES"],"name":"language","optional":true}],"claims":["opening the * calendar","checking availability","checking the * availability","checking the * dates","let me open the * calendar","abro el * calendario","abriendo el * calendario","reviso la * disponibilidad","revisando la * disponibilidad","reviso las * fechas","revisando las * fechas"],"class":"reversible","doc":"On reservations.explora.com, the lodge ``hotel_code``, and with them the\\narrival ``date``, ``month``, ``nights``; with ``rooms``, on to the rooms and\\nrates. Never past them. The page reports ``stay_state``.","id":"explora.check_availability","notes":["Dev call 2f94965e: \\"I\'m opening the Atacama calendar for three nights\\", twice, and no check_availability either time: the claims.","Dev call 453f2e19: \\"I\'ll open the calendar.\\", \\"I\'m selecting three nights to see the rates.\\", \\"I\'m opening the rooms and rates\\", and no call each time; no claim matched any of them. The objects do, by the sentence\'s shape."],"objects":["calendar","availability","dates","days","nights","rooms","rates","prices","calendario","disponibilidad","fechas","dias","noches","habitaciones","tarifas","precios"]},{"args":[{"doc":"The room as the rates page names it.","name":"room"},{"name":"travellers","optional":true,"type":"integer"},{"name":"bed","optional":true},{"name":"count","optional":true,"type":"integer"}],"claims":["selecting the * room","adding the * room","selecciono la * habitacion","agrego la * habitacion"],"class":"reversible","doc":"On the rooms and rates, select ``room`` for ``travellers`` with ``bed``,\\n``count`` times. Never check-out itself.","id":"explora.choose_room","notes":["Objects in the singular, so a plural hears them too; \\"the rooms\\" alone is check_availability\'s first, and either one made keeps the sentence."],"objects":["room","habitacion"]},{"args":[{"doc":"The expedition\'s code, such as XSCM.","name":"expedition_code"},{"name":"title","optional":true},{"name":"first_name","optional":true},{"name":"last_name","optional":true},{"name":"email","optional":true},{"name":"phone","optional":true},{"name":"country","optional":true},{"name":"message","optional":true},{"enum":["EN","ES"],"name":"language","optional":true}],"claims":["filling in the * form","opening the * form","abro el * formulario","completo el * formulario","completando el * formulario"],"class":"reversible","doc":"Open an expedition\'s enquiry form and fill in the fields given.","id":"explora.fill_enquiry","objects":["form","enquiry","formulario"]},{"class":"confirmed","doc":"Press Send Message on the filled form: the visitor\'s own data, so only\\nafter they ticked the reCAPTCHA and the brain checked every field.","id":"explora.send_enquiry"},{"args":[{"name":"tab_id"}],"class":"look","doc":"Bring one of the visitor\'s Explora tabs to the front.","id":"explora.focus_tab"}],"slices":[{"doc":"the page in front: its title, every section heading, tab and accordion, question and sub-page","fields":[{"enum":["site","reservations"],"name":"site","optional":true},{"name":"url","optional":true},{"name":"path"},{"name":"title","optional":true},{"doc":"The section headings, in order: what a show cue takes.","name":"headings","optional":true,"type":"array"},{"doc":"The questions in the page\'s accordions: what a faq cue takes.","name":"faqs","optional":true,"type":"array"},{"doc":"The labels of the in-page tabs and accordions.","name":"tabs","optional":true,"type":"array"},{"doc":"The page\'s own sub-menu, as paths.","name":"links","optional":true,"type":"array"}],"id":"page","window":60},{"doc":"the booking calendar or the rooms and rates on reservations.explora.com: the lodge, the month, the open arrival days, the nights offered, the rooms","fields":[{"enum":["dates","rooms"],"name":"step"},{"name":"hotel_code","optional":true},{"name":"hotel","optional":true},{"name":"month","optional":true},{"name":"open_days","optional":true,"type":"array"},{"name":"date","optional":true},{"fields":[{"name":"nights","type":"integer"},{"name":"label"}],"name":"nights","optional":true,"type":"array"},{"name":"chosen_nights","optional":true,"type":"integer"},{"fields":[{"name":"name"},{"name":"text"}],"name":"rooms","optional":true,"type":"array"}],"id":"stay","window":40},{"doc":"an expedition\'s enquiry form: which fields are filled and which are still empty (never what they hold), and whether I\'m not a robot is ticked","fields":[{"name":"expedition","optional":true},{"name":"expedition_code","optional":true},{"doc":"The names of the fields that hold something; never their values.","name":"filled","optional":true,"type":"array"},{"name":"missing","optional":true,"type":"array"},{"name":"captcha","optional":true,"type":"boolean"}],"id":"enquiry"}],"stage":1}'
)
#: The spec's hash: a page reading another spec reports a different one.
SPEC_SHA256 = "a830ff3608259b71f70fb7ad4fbefd99ae79b80989302c941fa09c3f1c839cbd"


class ShowArgs(BaseModel):
    """The arguments of ``core.show``."""

    target: str
    """A heading, tab or accordion as the page writes it, or words on it."""


class FaqArgs(BaseModel):
    """The arguments of ``core.faq``."""

    question: str
    """The question as the page writes it."""


class NavigateArgs(BaseModel):
    """The arguments of ``explora.navigate``."""

    path: str
    """A www.explora.com path."""
    after_words: int | None = None
    """Words of his still to be heard before the page may go (the holder's pacing)."""


class TwinArgs(BaseModel):
    """The arguments of ``explora.twin``."""

    language: Literal["en", "es"]


class CheckAvailabilityArgs(BaseModel):
    """The arguments of ``explora.check_availability``."""

    hotel_code: str
    """The lodge's code on the booking site, such as EATA."""
    date: str | None = None
    """The arrival day."""
    month: str | None = None
    """The month the calendar shows."""
    nights: int | None = None
    rooms: bool | None = None
    """Go on to the rooms and rates."""
    language: Literal["EN", "ES"] | None = None


class ChooseRoomArgs(BaseModel):
    """The arguments of ``explora.choose_room``."""

    room: str
    """The room as the rates page names it."""
    travellers: int | None = None
    bed: str | None = None
    count: int | None = None


class FillEnquiryArgs(BaseModel):
    """The arguments of ``explora.fill_enquiry``."""

    expedition_code: str
    """The expedition's code, such as XSCM."""
    title: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    country: str | None = None
    message: str | None = None
    language: Literal["EN", "ES"] | None = None


class SendEnquiryArgs(BaseModel):
    """``explora.send_enquiry`` takes none."""


class FocusTabArgs(BaseModel):
    """The arguments of ``explora.focus_tab``."""

    tab_id: str


SHOW = Move(
    id="core.show",
    verb="show",
    cls=MoveClass.LOOK,
    args=("target",),
    say="{show: Heading} scrolls to a heading on the page they are on, or are taken to by a page cue, and rings it. Use the heading exactly as the site pages list or the screen lines spell it. With the label of one of the page's tabs or accordions (\"Patagonia [Argentina + Chile]\"), it opens it. With words that are not a heading, it rings those words: a room, an exploration, a lodge's name.",
)
"""Scroll to a heading, open a tab or accordion, or ring words, on the page in front."""

FAQ = Move(
    id="core.faq",
    verb="faq",
    cls=MoveClass.LOOK,
    args=("question",),
    say="{faq: Question} opens that question's accordion on the page and rings it.",
)
"""Open a question's accordion and ring it."""

# A page cue is not a cue on Explora: every page is a full page load, so the brain splits his reply there and sends this itself, once the words before it are said.
NAVIGATE = Move(
    id="explora.navigate",
    verb=None,
    cls=MoveClass.NAVIGATE,
    args=(
        "path",
        "after_words",
    ),
)
"""Open a www.explora.com page in the tab in front, once his voice has said
``after_words`` words: a full page load. The page reports ``page_changed``.
"""

TWIN = Move(
    id="explora.twin",
    verb=None,
    cls=MoveClass.NAVIGATE,
    args=("language",),
)
"""Load the page in front's own twin in ``language``, once his voice is quiet;
refused when it has none.
"""

# Dev call 2f94965e: "I'm opening the Atacama calendar for three nights", twice, and no check_availability either time: the claims.
# Dev call 453f2e19: "I'll open the calendar.", "I'm selecting three nights to see the rates.", "I'm opening the rooms and rates", and no call each time; no claim matched any of them. The objects do, by the sentence's shape.
CHECK_AVAILABILITY = Move(
    id="explora.check_availability",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "hotel_code",
        "date",
        "month",
        "nights",
        "rooms",
        "language",
    ),
    claims=(
        "opening the * calendar",
        "checking availability",
        "checking the * availability",
        "checking the * dates",
        "let me open the * calendar",
        "abro el * calendario",
        "abriendo el * calendario",
        "reviso la * disponibilidad",
        "revisando la * disponibilidad",
        "reviso las * fechas",
        "revisando las * fechas",
    ),
    objects=(
        "calendar",
        "availability",
        "dates",
        "days",
        "nights",
        "rooms",
        "rates",
        "prices",
        "calendario",
        "disponibilidad",
        "fechas",
        "dias",
        "noches",
        "habitaciones",
        "tarifas",
        "precios",
    ),
)
"""On reservations.explora.com, the lodge ``hotel_code``, and with them the
arrival ``date``, ``month``, ``nights``; with ``rooms``, on to the rooms and
rates. Never past them. The page reports ``stay_state``.
"""

# Objects in the singular, so a plural hears them too; "the rooms" alone is check_availability's first, and either one made keeps the sentence.
CHOOSE_ROOM = Move(
    id="explora.choose_room",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "room",
        "travellers",
        "bed",
        "count",
    ),
    claims=(
        "selecting the * room",
        "adding the * room",
        "selecciono la * habitacion",
        "agrego la * habitacion",
    ),
    objects=(
        "room",
        "habitacion",
    ),
)
"""On the rooms and rates, select ``room`` for ``travellers`` with ``bed``,
``count`` times. Never check-out itself.
"""

FILL_ENQUIRY = Move(
    id="explora.fill_enquiry",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "expedition_code",
        "title",
        "first_name",
        "last_name",
        "email",
        "phone",
        "country",
        "message",
        "language",
    ),
    claims=(
        "filling in the * form",
        "opening the * form",
        "abro el * formulario",
        "completo el * formulario",
        "completando el * formulario",
    ),
    objects=(
        "form",
        "enquiry",
        "formulario",
    ),
)
"""Open an expedition's enquiry form and fill in the fields given."""

SEND_ENQUIRY = Move(
    id="explora.send_enquiry",
    verb=None,
    cls=MoveClass.CONFIRMED,
)
"""Press Send Message on the filled form: the visitor's own data, so only
after they ticked the reCAPTCHA and the brain checked every field.
"""

FOCUS_TAB = Move(
    id="explora.focus_tab",
    verb=None,
    cls=MoveClass.LOOK,
    args=("tab_id",),
)
"""Bring one of the visitor's Explora tabs to the front."""

MOVES = MoveSet(
    (
        SHOW,
        FAQ,
        NAVIGATE,
        TWIN,
        CHECK_AVAILABILITY,
        CHOOSE_ROOM,
        FILL_ENQUIRY,
        SEND_ENQUIRY,
        FOCUS_TAB,
    )
)

#: The line each cue is taught with, in the spec's order.
PROMPT_LINES: tuple[str, ...] = (
    "{show: Heading} scrolls to a heading on the page they are on, or are taken to by a page cue, and rings it. Use the heading exactly as the site pages list or the screen lines spell it. With the label of one of the page's tabs or accordions (\"Patagonia [Argentina + Chile]\"), it opens it. With words that are not a heading, it rings those words: a room, an exploration, a lodge's name.",
    "{faq: Question} opens that question's accordion on the page and rings it.",
)

#: The slices of the page's state a read may name.
SliceId = Literal["page", "stay", "enquiry"]


class ReadRequest(BaseModel):
    """What the read tool takes: the slice to read, from the brain's mirror."""

    slice: SliceId = Field(
        description="Which part of their screen to read. page: the page in front: its title, every section heading, tab and accordion, question and sub-page; stay: the booking calendar or the rooms and rates on reservations.explora.com: the lodge, the month, the open arrival days, the nights offered, the rooms; enquiry: an expedition's enquiry form: which fields are filled and which are still empty (never what they hold), and whether I'm not a robot is ticked."
    )
