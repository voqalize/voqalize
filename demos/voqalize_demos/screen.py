"""The screen is read, never remembered — the one home for that discipline.

Every demo here has a browser that re-sends its whole screen on every change, and
every one of them used to append that snapshot to the model's context. A
123-second production call put **twenty-one full carts** in front of the model
that way — about 4,700 tokens, each copy prefixed *authoritative* and none of them
saying which was now — and the model reasoned from whichever it noticed. The
complaint that started this was that the agent did not know what was on screen
after the customer edited it by hand. It had been told. It had been told twenty-one
times, and nothing in the context said which telling was current. On a second call
the model gave up answering and read one of the snapshots out loud instead.

So the snapshot stops here. What reaches the context is one line naming *which*
facts the customer moved — never their values, because a note that carries values
is the old dump one fact at a time — and the screen itself is read through a tool,
which is fast and silent because it reads this object.

:attr:`version` is what makes that enforceable rather than merely requested. Prompt
discipline is a request, and a model that does not re-read is holding ids and
figures that may name something else entirely. So :meth:`stale` refuses the
mutation instead, and the refusal is retriable: read, then act. It also keeps the
read cheap — the version moves only when the *customer* moves the screen, so the
ordinary turn pays no extra hop at all.

Three things a brain has to supply, because only it can:

``facts``
    Which parts of the snapshot are a decision. The browser's snapshot moves for
    reasons that are nobody's decision — a clip advancing a chapter, a result
    landing, a reference appearing — and bumping the version for those costs the
    model a re-read and buys nothing. Project the snapshot down to what the
    customer chose, typed or opened, and name each fact the way you want it read
    back to the model: the keys of this dict are what the change note says.

``read_tool``
    The name of the tool that serves this object, so the note and the refusal can
    both point at it.

``actor``
    Who is on the other side of the screen — the word the change note uses for
    them. A bank customer in one demo, the travel agent running the call in
    another; the note reads back to the model, so it has to name the right person.

:meth:`dispatched`
    Called whenever the brain itself moves the screen. The browser echoes those
    back as syncs indistinguishable from the customer's own, and a change the model
    asked for is one it has already been told about.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

#: A snapshot projected down to the facts a version bump is keyed on. Keys are
#: read back to the model verbatim, so name them for a reader: ``"the open
#: article"``, not ``"article_id"``.
Facts = Callable[[dict[str, Any] | None], dict[str, Any]]


class ScreenState:
    """The live screen, held on the brain and read on request."""

    def __init__(self, facts: Facts, *, read_tool: str, actor: str = "customer") -> None:
        self.snapshot: dict[str, Any] | None = None
        self.version = 0
        self._facts = facts
        self._read_tool = read_tool
        self._actor = actor
        self._read_version = 0
        self._synced = False
        self._echo = False

    @property
    def synced(self) -> bool:
        """Whether the browser has told us anything yet."""
        return self._synced

    def dispatched(self) -> None:
        """The brain just moved the screen; the browser's echo is not news.

        One flag is enough because the echo always comes — every demo store bumps
        its revision unconditionally, so even a command that moves nothing visible
        sends a sync. Two commands far enough apart to send two syncs cost one
        re-read, which is the safe direction to be wrong in."""
        self._echo = True

    def absorb(self, snapshot: dict[str, Any] | None) -> str | None:
        """Fold in what the browser just sent, and say what to tell the model.

        Returns the one line to append, or ``None`` when there is nothing worth
        saying — which is most of the time: an echo of the brain's own command, a
        fact that moved on its own, or the very first sync, which is the screen as
        it loaded rather than something the customer did to it."""
        before, self.snapshot = self.snapshot, snapshot
        first, self._synced = not self._synced, True
        echo, self._echo = self._echo, False
        was, now = self._facts(before), self._facts(snapshot)
        changed = sorted(key for key, value in now.items() if was.get(key) != value)
        if first or echo or not changed:
            return None
        self.version += 1
        return (
            f"The {self._actor} just changed the screen: "
            + ", ".join(changed)
            + f". Call {self._read_tool}() before you act on anything on it."
        )

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
