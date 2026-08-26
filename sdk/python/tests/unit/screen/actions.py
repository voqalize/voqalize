"""A brain-shaped module the generator is pointed at.

Deliberately a *package* module with a relative import: that is how a real brain
is laid out, and importing it by file path only works if the generator finds the
package root."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from voqalize.sdk import Action

from .shapes import Row, Urgency

NOT_AN_ACTION = 3


class ShowTable(Action):
    """Put the table up."""

    rows: list[Row]
    title: str = ""
    caption: str | None = None
    urgency: Urgency = Urgency.LOW
    mode: Literal["compact", "full"] = "compact"
    meta: dict[str, str] = {}
    tag: str = Field(default="", serialization_alias="data-tag")


class Dismiss(Action, name="close_it"):
    pass
