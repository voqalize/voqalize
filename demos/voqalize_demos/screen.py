"""The screen is read, never remembered — the one home for that discipline.

Two rules meet here, and they are not the same rule.

**The screen does not go in the context.** Every demo here used to append the
browser's snapshot to the model's context on every change. A 123-second
production call put **twenty-one full carts** in front of the model that way —
about 4,700 tokens, each copy prefixed *authoritative* and none of them saying
which was now — and the model reasoned from whichever it noticed. The complaint
that started this was that the agent did not know what was on screen after the
customer edited it by hand. It had been told. It had been told twenty-one times,
and nothing in the context said which telling was current. On a second call the
model gave up answering and read one of the snapshots out loud instead. So what
reaches the context is one line naming *what the customer just did*, and the
screen itself is read through a tool, which is fast and silent because it reads
the brain's own mirror.

**The browser does not push the screen at all.** The line above used to be
derived: the browser re-sent everything, this object diffed the new picture
against the old one, and *inferred* which act produced the difference. Every
inference is a place the two pictures can part company, and the best the model
could then be told is that *something* moved. Now each gesture arrives as a typed
:class:`~voqalize.sdk.AppEvent` that says what it was, the brain folds it into a
mirror it owns, and :meth:`moved` is handed the sentence rather than guessing at
one. The diff, the fact projection it needed, and the echo-suppression flag that
kept the brain's own commands from reading as the customer's are all gone with
it — a brain's own dispatch is simply not an event.

:attr:`version` is what makes the read enforceable rather than merely requested.
Prompt discipline is a request, and a model that does not re-read is holding ids
and figures that may name something else entirely. So :meth:`stale` refuses the
mutation instead, and the refusal is retriable: read, then act. It also keeps the
read cheap — the version moves only when the *customer* moves the screen, so the
ordinary turn pays no extra hop at all.

Most of what arrives is somebody's decision, and :meth:`moved` names them for it.
:meth:`happened` is the other kind: a test run finishing or a linter answering is
the *browser's* computation, nobody's choice, and nowhere else for the brain to
read it — so that line carries its result where a gesture's never would.

Two things a brain has to supply, because only it can:

``read_tool``
    The name of the tool that serves the mirror, so the note and the refusal can
    both point at it.

``actor``
    Who is on the other side of the screen — the word the change note uses for
    them. A bank customer in one demo, the travel agent running the call in
    another; the note reads back to the model, so it has to name the right person.
"""

from __future__ import annotations

from typing import Any


class ScreenState:
    """What the model may assume about a screen the brain does not own."""

    def __init__(self, *, read_tool: str, actor: str = "customer") -> None:
        self.version = 0
        self._read_tool = read_tool
        self._actor = actor
        self._read_version = 0

    def moved(self, what: str) -> str:
        """The actor did ``what``; return the one line that says so.

        ``what`` is a verb phrase completing "The <actor> …" — *named*, not
        valued: "picked a flight for the outbound leg", never the flight. A note
        that carries values is the old snapshot dump arriving one fact at a time,
        and it goes stale in the context exactly the same way."""
        self.version += 1
        return (
            f"The {self._actor} {what}. "
            f"Call {self._read_tool}() before you act on anything on screen."
        )

    def happened(self, sentence: str) -> str:
        """Something the *screen* did; return the line that says so.

        Not every change is somebody's decision. A test run comes back, a
        coverage linter answers, a persona walk comes to rest — nobody chose the
        result and the browser is the only place it exists, so unlike
        :meth:`moved` this one carries it, and takes the whole sentence because
        naming the actor would be a lie."""
        self.version += 1
        return f"{sentence} Call {self._read_tool}() before you act on anything on screen."

    def read(self) -> None:
        """The model has just been served the screen; it is up to date."""
        self._read_version = self.version

    def stale(self) -> str | None:
        """Why a tool aimed at this screen should refuse, or ``None`` to go ahead."""
        if self._read_version == self.version:
            return None
        return (
            "the screen moved since you last read it, so the ids and figures you are "
            f"working from may no longer be right — call {self._read_tool}() and try again"
        )


def _outline(key: str, value: Any, depth: int) -> list[str]:
    pad = "  " * depth
    label = key.replace("_", " ")
    if isinstance(value, dict):
        out = [f"{pad}{label}:"]
        for k, v in value.items():  # pyright: ignore[reportUnknownVariableType]
            out.extend(_outline(str(k), v, depth + 1))
        return out
    if isinstance(value, list):
        out = [f"{pad}{label}:"]
        for n, item in enumerate(value, 1):  # pyright: ignore[reportUnknownVariableType]
            out.extend(_outline(str(n), item, depth + 1))
        return out
    return [f"{pad}{label}: {value}"]


def screen_prose(where: dict[str, Any], *, actor: str = "customer") -> str:
    """The screen as a sentence plus an indented outline, never a dict repr.

    A tool that returns ``str({...})`` reads as one more JSON blob in a context
    that already had several, and two of those with no prose between them is what
    made a model read the screen aloud instead of answering from it.
    """
    screen = str(where.get("screen") or "home").replace("_", " ")
    lines = [f"The {actor} is on the {screen} screen."]
    for key, value in where.items():
        if key != "screen":
            lines.extend(_outline(str(key), value, 0))
    return "\n".join(lines)
