"""What the advisor did on the console — the browser→brain half of the screen
contract.

The other direction is the :class:`~voqalize.sdk.Action` classes in ``brain.py``:
a declared shape whose wire name comes off the class name, validated at the call
site, with a generated TypeScript twin. :class:`~voqalize.sdk.AppEvent` is that,
mirrored — so ``on_rtvi`` narrows on a *type* rather than being handed the whole
workspace and left to work out what moved in it.

This desk is a colleague working beside the advisor, so both hands are on the
same screen and the vocabulary is correspondingly wide: the advisor opens cases,
routes them, decides approvals and submits packets himself, all while talking.
What matters is that each of those arrives *named* — ``approval_decided``, with
the id and the decision — instead of as a workspace the desk has to compare
against the last one to notice a status flipped.

There is no "console opened" event. The board is in ``session.init`` before the
first word, so the desk builds its picture from what it was handed rather than
asking the browser to hand it back.
"""

from __future__ import annotations

from typing import Literal

from voqalize.sdk import AppEvent, AppEvents

__all__ = [
    "SERVICING_EVENTS",
    "ApprovalDecided",
    "BoardFiltered",
    "BoardOpened",
    "CaseOpened",
    "CaseRouted",
    "NoteAdded",
    "PacketSubmitted",
    "SearchDismissed",
    "ServicingEvent",
    "TabOpened",
]


class BoardOpened(AppEvent):
    """The advisor went back to the case board. No case is open."""


class CaseOpened(AppEvent):
    """The advisor opened a case himself — off the board, the approvals tray, or a
    precedent result."""

    ref: str


class TabOpened(AppEvent):
    """The advisor switched tabs on the open case."""

    tab: Literal["overview", "payments", "documents", "activity"]


class BoardFiltered(AppEvent):
    """The advisor filtered the board — which cases he is now looking at."""

    showing: str


class CaseRouted(AppEvent):
    """The advisor routed a case to a department queue himself."""

    ref: str
    to: str


class NoteAdded(AppEvent):
    """The advisor wrote a note on a case, optionally routing it to a department.

    The text rides the event because the desk's mirror is its only view of the
    console: what the advisor typed exists nowhere else the desk can reach. It
    goes into the mirror, not the context — read through ``get_advisor_context``
    like everything else on screen."""

    ref: str
    text: str = ""
    dept: str = ""


class ApprovalDecided(AppEvent):
    """The advisor approved or declined a draft — the maker-checker half that is
    his alone. The desk must never claim it decided one."""

    ref: str
    approval_id: str
    decision: Literal["approved", "declined"]
    title: str = ""


class PacketSubmitted(AppEvent):
    """The advisor submitted a regulated packet himself."""

    ref: str


class SearchDismissed(AppEvent):
    """The advisor closed the precedent-search panel."""


type ServicingEvent = (
    BoardOpened
    | CaseOpened
    | TabOpened
    | BoardFiltered
    | CaseRouted
    | NoteAdded
    | ApprovalDecided
    | PacketSubmitted
    | SearchDismissed
)

SERVICING_EVENTS = AppEvents[ServicingEvent](
    BoardOpened,
    CaseOpened,
    TabOpened,
    BoardFiltered,
    CaseRouted,
    NoteAdded,
    ApprovalDecided,
    PacketSubmitted,
    SearchDismissed,
)
