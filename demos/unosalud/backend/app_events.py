"""What the visitor's tabs report — the page→brain half of the screen contract.

The other direction is the :class:`~voqalize.sdk.Action` classes in
``brain.py``. These are sent by the extension on www.unosalud.cl (the site and
its booking, ``/agenda-tu-hora/``, which is one origin), and they fire for the
visitor's own clicks as well as for Javier's moves, so his picture of their
screen is true whoever moved it.

The site is Uno Salud's, not ours, and it changes without asking. So the nested
shapes are plain models that ignore a field they do not know, while the events
themselves are strict: a new field on a page report is harmless, a new event is
a change we want to hear about.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from voqalize.sdk import AppEvent, AppEvents

__all__ = [
    "UNOSALUD_EVENTS",
    "BookingState",
    "BookingSummary",
    "CallbackFormState",
    "ClinicInfo",
    "CommandDone",
    "CommandFailed",
    "CompanyFormState",
    "DaySlots",
    "LanguageRequested",
    "PageChanged",
    "TabInfo",
    "TabsChanged",
    "UnoSaludEvent",
]

PageKind = Literal[
    "home",
    "specialties",
    "specialty",
    "clinics",
    "clinic",
    "promotions",
    "promo_landing",
    "convenios",
    "convenio",
    "benefits",
    "plans",
    "urgencias",
    "about",
    "why_us",
    "contact",
    "faq",
    "company",
    "callback",
    "booking",
    "blog",
    "post",
    "terms",
    "page",
]

BookingStep = Literal[
    "getPAC",
    "setPAC",
    "setEF",
    "notsetRH",
    "getMRes",
    "getSuc",
    "getHor",
    "getDC",
    "setRH",
    "unknown",
]


class ClinicInfo(BaseModel):
    """A clinic page as it reads: how its hours reach him, live."""

    name: str = ""
    address: str = ""
    hours: str = ""
    references: str = ""
    maps_url: str = ""


class PageChanged(AppEvent):
    """The tab in front changed page, or came to the front: what is on it now."""

    url: str = ""
    path: str
    title: str = ""
    kind: PageKind = "page"
    anchors: list[str] = Field(default_factory=list[str])
    """The catalogue's places (keys of ``anchors.json``) this page shows."""
    faqs: list[str] = Field(default_factory=list[str])
    """The FAQ keys this page shows."""
    form: Literal["booking", "callback", "urgencias", "company", "none"] = "none"
    clinic: ClinicInfo | None = None


class TabInfo(BaseModel):
    tab_id: str
    url: str = ""
    title: str = ""


class TabsChanged(AppEvent):
    """Every Uno Salud tab the visitor has open, and the one in front: the
    whole list each time."""

    tabs: list[TabInfo] = Field(default_factory=list[TabInfo])
    active: str = ""


class CommandFailed(AppEvent):
    """A move Javier sent could not be carried out on the page."""

    command: str
    reason: str = ""


class CommandDone(AppEvent):
    """A move Javier sent was carried out: the page now shows what he asked."""

    command: str
    detail: str = ""
    """What is on screen now, in a few English words."""


class LanguageRequested(AppEvent):
    """The visitor pressed the other language on the widget's toggle."""

    language: Literal["en", "es"]


class DaySlots(BaseModel):
    date: str
    """YYYY-MM-DD."""
    times: list[str] = Field(default_factory=list[str])
    """HH:MM."""


class BookingSummary(BaseModel):
    """The review step's table (``#data-reserva``), as the booking writes it."""

    paciente: str = ""
    fecha: str = ""
    hora: str = ""
    odontologo: str = ""
    direccion: str = ""
    referencia: str = ""


class BookingState(AppEvent):
    """The booking on /agenda-tu-hora/: on load and after every step, whoever
    took it. Never the RUT itself: only whether one was typed."""

    step: BookingStep = "unknown"
    rut_entered: bool = False
    patient_first_name: str = ""
    """From the existing patient's greeting (``#setEF``) only."""
    motivo: int = 0
    region: str = ""
    comuna: str = ""
    sucursal: str = ""
    date: str = ""
    """The day selected, YYYY-MM-DD."""
    slots: list[str] = Field(default_factory=list[str])
    """The hours that day, HH:MM."""
    days: list[DaySlots] = Field(default_factory=list[DaySlots])
    """What ``booking_scan`` read, day by day."""
    no_slots: bool = False
    summary: BookingSummary | None = None
    error: str = ""
    """The booking's own error line (``#dentalsoft-error``)."""
    booked: bool = False


class CallbackFormState(AppEvent):
    """The Te llamamos form (/landing/solicitar-diagnostico/) or the urgencias
    one, after a fill or the visitor's press."""

    form: Literal["te_llamamos", "urgencias"] = "te_llamamos"
    filled: list[str] = Field(default_factory=list[str])
    missing: list[str] = Field(default_factory=list[str])
    rut_typed: bool = False
    result: Literal["none", "success", "error"] = "none"
    message: str = ""


class CompanyFormState(AppEvent):
    """The Convenio Empresas form, after a fill or the visitor's press."""

    filled: list[str] = Field(default_factory=list[str])
    missing: list[str] = Field(default_factory=list[str])
    result: Literal["none", "success", "error"] = "none"
    message: str = ""


type UnoSaludEvent = (
    PageChanged
    | TabsChanged
    | CommandDone
    | CommandFailed
    | LanguageRequested
    | BookingState
    | CallbackFormState
    | CompanyFormState
)

UNOSALUD_EVENTS = AppEvents[UnoSaludEvent](
    PageChanged,
    TabsChanged,
    CommandDone,
    CommandFailed,
    LanguageRequested,
    BookingState,
    CallbackFormState,
    CompanyFormState,
)
