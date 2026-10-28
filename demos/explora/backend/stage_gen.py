# Generated from explora/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
#   voqalize stage gen explora/scene.json --py explora/backend/stage_gen.py --ts explora/extension/src/scene.gen.ts
"""The moves of explora, from its Stage Spec."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from voqalize.sdk.stage import Move, MoveClass, MoveSet

#: The spec's hash: a page reading another spec reports a different one.
SPEC_SHA256 = "9001cb7b62eac15b24dbc1a537b93ac3f817f975d69634b8b35d1afe8f7029db"


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
