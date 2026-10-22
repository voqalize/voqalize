"""The screen contract between Javier's brain and the UAH extension, both ways.

One file, both halves, so the extension and the brain follow the same thing:
the :class:`~voqalize.sdk.Action` classes are what the brain sends the page
(their snake_case names are the commands ``content.ts`` routes), and the
:class:`~voqalize.sdk.AppEvent` classes are what the page reports back. The
extension's ``src/actions.gen.ts`` is generated from this module
(``pnpm gen``); never edit that file by hand.

The university's sites are three WordPress hosts — admision.uahurtado.cl (where
undergraduate admission lives), postgrados.uahurtado.cl and www.uahurtado.cl —
and every move between pages is a full page load, often across origins. So a
page is named by its whole URL, never a bare path, and a move that needs another
page (``show_admission`` on a career the visitor is not on) carries the URL: the
page goes there first and finishes the move after the load.

**The brain never fetches uahurtado.cl.** It runs far from Chile and the site is
not reachable from it. Every live figure — a 2027 fee, the PAES weights, a
postgraduate application window — is read in the visitor's browser, by the page
adapter or the extension's service worker, and comes back here as an event. The
brain parses and checks what it is given, and Javier only says a figure the page
just reported.

**Forms are filled, never sent.** ``fill_lead_form`` types what the visitor
dictated into the site's own lead form; nothing ever types a RUT, presses
"Enviar", calls ``submit()`` or follows a visit's sign-up link.

The nested shapes are lenient plain models (the site changes without asking);
the events themselves are strict, so a new event is a change we hear about.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from voqalize.sdk import Action, AppEvent, AppEvents

# ─── Brain → page ──────────────────────────────────────────────────────────────


class Navigate(Action):
    """Load ``url`` (a page on one of the three UAH hosts) in the tab the call
    is in and, once it has loaded, scroll to and ring ``heading`` (a heading,
    a tab, pill or accordion label, which is opened first) or ``text``, or open
    the FAQ ``faq``. A page already in front is not reloaded: the move is done
    on it, and it reports ``page_changed`` again."""

    url: str
    heading: str | None = None
    text: str | None = None
    faq: str | None = None


class Cue(Action):
    """A move for the page to make when the voice reaches ``at`` — the first
    three folded words of the sentence it belongs to (empty: when the voice
    stops; ``word`` is the clock fallback). With ``url`` it is a
    :class:`Navigate`; otherwise a heading, tab, pill, accordion, card, words
    or FAQ on the page in front. Cues still owed when the page unloads are
    carried to the next page, across hosts."""

    at: str
    word: int = 0
    """Words of the unit before it, for a page that times cues by the clock."""
    url: str | None = None
    heading: str | None = None
    text: str | None = None
    faq: str | None = None


class ShowSection(Action):
    """On the page in front, open (if it is a tab, pill or accordion label)
    and ring ``heading``; with ``text``, ring the smallest laid-out element
    containing it."""

    heading: str | None = None
    text: str | None = None


class OpenFaq(Action):
    """Open the FAQ (an h3 collapse, a Bootstrap accordion or a details box)
    that starts with ``question`` on the page in front, and ring it."""

    question: str


class FocusTab(Action):
    """Bring one of the visitor's UAH tabs to the front."""

    tab_id: str


class LanguageChanged(Action):
    """The call's language moved, by the toggle, by voice or by
    ``set_language``: the widget's toggle follows at once."""

    language: Literal["en", "es"]


class OpenLink(Action):
    """Open ``url`` in a new tab: the PAES simulator (simula.uahurtado.cl), a
    malla PDF. The extension does nothing on that tab, and on simula it fills
    nothing: its form creates a lead."""

    url: str
    label: str = ""


class OpenCareerMenu(Action):
    """Open the Carreras mega-menu (``#collapseCarreras``, via
    ``#menu-menu-principal-1 > li.boton-carrera > a``) and ring the group of
    ``faculty`` in it (matched loosely, accents folded; ``None``: the whole
    menu). Off admision.uahurtado.cl, the page first loads ``url`` (admision's
    home) and opens the menu there. Answers ``command_done`` (detail: the
    careers listed in the ringed group) or ``command_failed``."""

    faculty: str | None = None
    url: str = "https://admision.uahurtado.cl/"


class PlayAudiomalla(Action):
    """On the career page ``url``, press play on the audiomalla (``#malla
    audio``): the director's own voice about the career. While it plays the
    visitor's microphone is muted, so the call does not take the recording for
    the visitor speaking; it is unmuted when it ends or is paused. Answers
    ``command_done`` once playing, ``command_failed`` if the browser refused (the
    play button is then rung for the visitor to press), and
    ``audiomalla_ended`` when it stops."""

    url: str


class ShowAdmission(Action):
    """On the career page ``url`` (loaded first if it is not in front), open
    the "Requisitos y Aranceles" tab (``#requisitos_carrera-tab``) and ring its
    fees (``focus`` "fees": the right column, ``h3`` "Aranceles") or its PAES
    weights table ("requirements": the left column). Then read both from the
    visible text — never from ``data-sheets-value`` attributes, which hold old
    figures — and, in the service worker, the site's own record
    (``admision.uahurtado.cl/wp-json/wp/v2/carreras?slug=<slug>&_fields=acf.aranceles_carrera``).
    Answers ``admission_read``, or ``command_failed`` when the tab is not there."""

    url: str
    slug: str
    focus: Literal["fees", "requirements"] = "fees"


class ShowProgram(Action):
    """On the postgraduate programme page ``url`` (loaded first if needed),
    expand "Requisitos y Valores" (``[data-bs-target="#collapseRequisitos"]``)
    and ring it; read it and the sidebar's ``h3`` blocks (Postulaciones,
    Inicio…) from the page, and in the service worker
    ``postgrados.uahurtado.cl/wp-json/wp/v2/programa?slug=<slug>&_fields=acf.postulacion_desde,acf.postulacion_hasta,acf.inicio_programa,acf.requisitos_program``.
    Answers ``program_read``, or ``command_failed``."""

    url: str
    slug: str


class FillLeadForm(Action):
    """Type what the visitor dictated into the lead form ``#admisionForm`` on
    the page in front, field by field (value setter, then ``input``,
    ``change`` and ``blur``), and scroll it into view. A field left ``None`` is
    not touched. ``carrera`` and ``via`` pick a ``<select>`` option by its
    text, where the form has that select. Never the RUT: with ``focus_rut`` the
    RUT field is rung and focused for the visitor to type. Never submit, never
    press "Enviar": once every required field but the RUT is filled, "Enviar"
    is rung. Answers ``lead_form_state`` and ``command_done`` /
    ``command_failed``."""

    nombre: str | None = None
    apellido: str | None = None
    email: str | None = None
    fono: str | None = None
    consulta: str | None = None
    carrera: str | None = None
    via: str | None = None
    focus_rut: bool = False


class ShowSignup(Action):
    """On /ven-y-conocenos/, ring the "Inscribirse aquí" link of the visit
    card titled ``title``. Never click it: sign-ups are Google and HubSpot
    forms the visitor opens themselves. ``command_failed`` if the card is
    marked REALIZADO, has closed sign-ups, or is not there."""

    title: str


# ─── Page → brain ──────────────────────────────────────────────────────────────


class Row(BaseModel):
    """One row of a table as the page shows it: ``label`` → ``value``."""

    label: str
    value: str = ""


class VisitCard(BaseModel):
    """A visit or workshop card on /ven-y-conocenos/."""

    title: str
    text: str = ""
    done: bool = False
    """Marked "REALIZADO": already happened."""
    open: bool = False
    """Has a working "Inscribirse aquí" link (not "Inscripciones cerradas")."""
    signup_label: str = ""
    signup_url: str = ""


class CareerSheet(BaseModel):
    """What a career page (``/carreras/<slug>/``) shows, read off its DOM at
    load — every tab pane is in the document, shown or not."""

    slug: str
    name: str = ""
    facts: list[Row] = Field(default_factory=list[Row])
    """``#malla table`` rows: Carrera, Modalidad, Área, Grado académico, Título
    profesional, Facultad, Sede, Régimen, Duración."""
    tabs: list[str] = Field(default_factory=list[str])
    """The tab labels, in order, as the page writes them."""
    has_audiomalla: bool = False
    audiomalla_label: str = ""
    """Words beside the audio: usually the director's name."""
    malla_pdf: str = ""
    fees_text: str = ""
    """The visible text of the Aranceles column, as one string."""
    weights: list[Row] = Field(default_factory=list[Row])
    """The PAES weights table's rows (criterion → percent; then the minimums)."""
    requirements_text: str = ""
    """The left column's text when it is a list rather than a table (online
    and continuity careers)."""


class ProgramSheet(BaseModel):
    """What a postgraduate programme page (``/programa/<slug>/``) shows."""

    slug: str
    name: str = ""
    requisitos_text: str = ""
    """The visible text of "Requisitos y Valores" (fees, discounts, deadlines)."""
    sidebar: list[Row] = Field(default_factory=list[Row])
    """The sidebar's ``h3`` blocks: Postulaciones, Inicio, Director/a…"""
    accordion: list[str] = Field(default_factory=list[str])
    """The accordion's button labels, in order."""


class LeadFormInfo(BaseModel):
    """The lead form ``#admisionForm`` on the page, if it has one."""

    fields: list[str] = Field(default_factory=list[str])
    """Which of nombre, apellido, rut, email, fono, consulta, carrera, via it has."""
    career_options: list[str] = Field(default_factory=list[str])
    """The career select's option texts, where it is a select."""
    via_options: list[str] = Field(default_factory=list[str])
    career: str = ""
    """The career the form is for, where the page sets it (a hidden field)."""
    filled: list[str] = Field(default_factory=list[str])


class PageChanged(AppEvent):
    """The tab in front changed page, or came to the front: what is on it now,
    as laid out at this width (hidden mobile duplicates left out)."""

    url: str
    title: str = ""
    kind: Literal["home", "career", "program", "listing", "page"] = "page"
    headings: list[str] = Field(default_factory=list[str])
    """Section headings, in order — what a ``show`` cue takes."""
    toggles: list[str] = Field(default_factory=list[str])
    """Tab, pill and accordion labels — a ``show`` cue on one opens it."""
    faqs: list[str] = Field(default_factory=list[str])
    cards: list[str] = Field(default_factory=list[str])
    career: CareerSheet | None = None
    program: ProgramSheet | None = None
    visits: list[VisitCard] = Field(default_factory=list[VisitCard])
    form: LeadFormInfo | None = None
    translated: bool = False
    """Chrome translated the page: its words may not be the site's."""


class TabInfo(BaseModel):
    tab_id: str
    url: str = ""
    title: str = ""


class TabsChanged(AppEvent):
    """Every UAH tab the visitor has open, and the one in front."""

    tabs: list[TabInfo] = Field(default_factory=list[TabInfo])
    active: str = ""


class CommandDone(AppEvent):
    """A move the brain waits on was carried out: ``detail`` says in a few
    English words what is on screen now."""

    command: str
    detail: str = ""


class CommandFailed(AppEvent):
    """A move Javier sent could not be carried out; ``reason`` is an English
    sentence naming what *is* there."""

    command: str
    reason: str = ""


class LanguageRequested(AppEvent):
    """The visitor pressed the other language on the widget's toggle."""

    language: Literal["en", "es"]


class AdmissionRead(AppEvent):
    """The answer to ``show_admission``: the career's Requisitos y Aranceles,
    read just now in the visitor's browser."""

    slug: str
    url: str = ""
    fees_text: str = ""
    """The Aranceles column's visible text."""
    year: str = ""
    matricula: str = ""
    """The page's own parse, as written: "$277.456"."""
    arancel: str = ""
    titulacion_uf: str = ""
    weights: list[Row] = Field(default_factory=list[Row])
    requirements_text: str = ""
    api_fees_text: str = ""
    """The same career's ``acf.aranceles_carrera``, as text, from the site's
    REST API (read by the service worker); empty if that read failed."""
    error: str = ""


class ProgramRead(AppEvent):
    """The answer to ``show_program``."""

    slug: str
    url: str = ""
    requisitos_text: str = ""
    sidebar: list[Row] = Field(default_factory=list[Row])
    postulacion_desde: str = ""
    """From the REST API, as it writes it (e.g. "20261001" or "01-10-2026")."""
    postulacion_hasta: str = ""
    inicio_programa: str = ""
    api_requisitos_text: str = ""
    error: str = ""


class LeadFormState(AppEvent):
    """The lead form after a fill, or after the visitor typed in it."""

    filled: list[str] = Field(default_factory=list[str])
    missing: list[str] = Field(default_factory=list[str])
    """Required fields still empty, the RUT included."""
    invalid: list[str] = Field(default_factory=list[str])
    career: str = ""
    ready: bool = False
    """Everything required is in: "Enviar" is the visitor's to press."""


class LeadSubmitted(AppEvent):
    """The visitor pressed "Enviar". In a preview build the extension stops
    the post (``blocked``) so a demo never sends UAH a lead."""

    blocked: bool = True


class AudiomallaEnded(AppEvent):
    """The audiomalla stopped: it finished, or the visitor paused it."""

    finished: bool = True


type UahEvent = (
    PageChanged
    | TabsChanged
    | CommandDone
    | CommandFailed
    | LanguageRequested
    | AdmissionRead
    | ProgramRead
    | LeadFormState
    | LeadSubmitted
    | AudiomallaEnded
)

UAH_EVENTS = AppEvents[UahEvent](
    PageChanged,
    TabsChanged,
    CommandDone,
    CommandFailed,
    LanguageRequested,
    AdmissionRead,
    ProgramRead,
    LeadFormState,
    LeadSubmitted,
    AudiomallaEnded,
)

__all__ = [
    "UAH_EVENTS",
    "AdmissionRead",
    "AudiomallaEnded",
    "CareerSheet",
    "CommandDone",
    "CommandFailed",
    "Cue",
    "FillLeadForm",
    "FocusTab",
    "LanguageChanged",
    "LanguageRequested",
    "LeadFormInfo",
    "LeadFormState",
    "LeadSubmitted",
    "Navigate",
    "OpenCareerMenu",
    "OpenFaq",
    "OpenLink",
    "PageChanged",
    "PlayAudiomalla",
    "ProgramRead",
    "ProgramSheet",
    "Row",
    "ShowAdmission",
    "ShowProgram",
    "ShowSection",
    "ShowSignup",
    "TabInfo",
    "TabsChanged",
    "UahEvent",
    "VisitCard",
]
