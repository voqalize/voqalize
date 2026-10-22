"""What the visitor's ssilva.cl tabs report — the page→brain half of the screen contract.

The other direction is the :class:`~voqalize.sdk.Action` classes in
``brain.py``. These are sent by the extension on ssilva.cl, and they fire for
the visitor's own clicks as well as for Javier's moves, so his picture of their
screen is true whoever moved it.

The site is Ssilva's, not ours, and it changes without asking. So the nested
shapes are plain models that ignore a field they do not know, while the events
themselves are strict: a new event is a change we want to hear about.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from voqalize.sdk import AppEvent, AppEvents

__all__ = [
    "SSILVA_EVENTS",
    "CommandFailed",
    "LanguageRequested",
    "LeadFormState",
    "LeadSubmitted",
    "PageChanged",
    "ProjectsListed",
    "SsilvaEvent",
    "TabInfo",
    "TabsChanged",
    "TypologyShown",
]


class PageChanged(AppEvent):
    """The tab in front loaded a page, or came to the front: what is on it now."""

    url: str = ""
    path: str
    title: str = ""
    kind: Literal["home", "projects", "project", "quote", "page"] = "page"
    """The home page, the project list (/proyectos/, /oportunidades/), one
    project's page, a cotizar page, or another page."""
    project: str = ""
    """The project's name, on a project or cotizar page; empty elsewhere."""
    headings: list[str] = Field(default_factory=list[str])
    """The page's section headings, in order, as the visitor sees them."""
    sections: list[str] = Field(default_factory=list[str])
    """On a project page, the canonical sections it has: ``galería``,
    ``tipologías``, ``amenidades``, ``tour``, ``estado``, ``brochure``,
    ``contacto``, ``formulario``."""
    typologies: list[str] = Field(default_factory=list[str])
    """On a project page, its typologies as labelled ("2D | 2B")."""
    typology: str = ""
    """The typology selected now."""
    price: str = ""
    """The hero's price, as written: "Desde 3.375 UF"."""
    status: str = ""
    """The status bar's active step: "Entrega inmediata"."""


class TypologyShown(AppEvent):
    """A typology was selected on a project page (by Javier or the visitor):
    what its panel shows now."""

    label: str
    price: str = ""
    total_area: str = ""
    useful_area: str = ""
    bedrooms: str = ""
    bathrooms: str = ""
    orientation: str = ""


class ProjectsListed(AppEvent):
    """The project list showed its results for a filter."""

    count: int = 0
    region: str | None = None
    property: str | None = None
    communes: list[str] = Field(default_factory=list[str])
    projects: list[str] = Field(default_factory=list[str])
    """The names on the page of results in front."""


class LeadFormState(AppEvent, name="lead_form"):
    """Where the quote form on a project page stands, after every change: its
    step, what is filled, what is still empty, the exact options of its
    dropdowns on this project's form, and any error it shows."""

    step: Literal["contact", "details", "sent"]
    filled: dict[str, str] = Field(default_factory=dict[str, str])
    """Field key → shown value. Keys: firstname, lastname, rut, email, phone,
    motivo, tipologia, ingreso, pie."""
    missing: list[str] = Field(default_factory=list[str])
    options: dict[str, list[str]] = Field(default_factory=dict[str, list[str]])
    errors: list[str] = Field(default_factory=list[str])


class LeadSubmitted(AppEvent):
    """The visitor pressed "Enviar". ``blocked`` when this preview stopped it
    before it reached Ssilva."""

    blocked: bool = False


class TabInfo(BaseModel):
    tab_id: str
    url: str = ""
    title: str = ""


class TabsChanged(AppEvent):
    """Every ssilva.cl tab the visitor has open, and the one in front: the
    whole list each time."""

    tabs: list[TabInfo] = Field(default_factory=list[TabInfo])
    active: str = ""


class CommandFailed(AppEvent):
    """A move Javier sent could not be carried out on the page."""

    command: str
    reason: str = ""


class LanguageRequested(AppEvent):
    """The visitor pressed the other language on the widget's toggle."""

    language: Literal["en", "es"]


type SsilvaEvent = (
    PageChanged
    | TypologyShown
    | ProjectsListed
    | LeadFormState
    | LeadSubmitted
    | TabsChanged
    | CommandFailed
    | LanguageRequested
)

SSILVA_EVENTS = AppEvents[SsilvaEvent](
    PageChanged,
    TypologyShown,
    ProjectsListed,
    LeadFormState,
    LeadSubmitted,
    TabsChanged,
    CommandFailed,
    LanguageRequested,
)
