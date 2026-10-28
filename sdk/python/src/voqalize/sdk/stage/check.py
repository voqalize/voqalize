"""``voqalize stage check``: what a Stage Spec gets wrong before a call does.

Loading a spec already refuses what can never work (a bad verb, a sixth cue
argument, a note that prints a private field). This goes further, to what loads
but fails in a call:

- **The leaked-call guard holds a cue back.** The SDK holds back a reply that
  looks like a function call written as text. Every cue is run through that
  same guard, at the start of a reply and in the middle of one, so a change to
  the guard or a new verb that trips it breaks the build, not a call.
- **A cue nobody is taught.** A cue move without a ``say`` line is never
  written by the model; a ``say`` line that writes another verb, or a verb the
  spec does not declare, teaches a cue that is dropped.
- **A promise nobody can catch.** A move that changes the page and has neither
  ``claims`` nor ``objects`` cannot be heard promised and never sent.
- **The prompt grows.** The cue lines go into every request: their size is
  counted against a budget.
- **A slice nothing fills.** A slice no event changes always reads as unknown.

Each finding is an ``error`` (it will fail in a call) or a ``warning`` (it
probably will). The command exits non-zero on an error, and on a warning with
``--strict``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from ..voice import _SPOKEN_CALL, _looks_like_call  # pyright: ignore[reportPrivateUsage]
from .policy import MoveClass
from .spec import MoveSpec, StageSpec

__all__ = ["PROMPT_BUDGET_TOKENS", "Finding", "check_spec"]

#: How many tokens the cue lines may take in every request, at about four
#: characters a token.
PROMPT_BUDGET_TOKENS = 800

_TAUGHT = re.compile(r"\{([a-z]{2,12})\s*[:}]")


@dataclass(frozen=True, slots=True)
class Finding:
    level: Literal["error", "warning"]
    where: str
    """The move, slice or event it is about, or ``spec``."""
    message: str

    def __str__(self) -> str:
        return f"{self.level}: {self.where}: {self.message}"


def _sample(move: MoveSpec) -> str:
    """The cue as a reply would write it, with words for its arguments."""
    if not move.args:
        return f"{{{move.verb}}}"
    words = [a.enum[0] if a.enum else "Rooms" for a in move.args]
    return f"{{{move.verb}: {' | '.join(words)}}}"


def _guard(move: MoveSpec) -> list[Finding]:
    cue = _sample(move)
    out: list[Finding] = []
    opening = f"{cue} Here they are."
    for end in range(1, len(opening) + 1):
        if _looks_like_call(opening[:end]) is True:
            out.append(
                Finding(
                    "error",
                    move.id,
                    f"a reply opening with {cue!r} is taken for a function call written as "
                    "text and held back: choose another verb",
                )
            )
            break
    if _looks_like_call(opening) is None:
        out.append(
            Finding(
                "error",
                move.id,
                f"a reply opening with {cue!r} is held until more comes: its speech waits",
            )
        )
    if _SPOKEN_CALL.search(f"Of course. {cue} Here they are."):
        out.append(
            Finding(
                "error",
                move.id,
                f"{cue!r} in the middle of a reply is taken for a function call and cut there",
            )
        )
    return out


def check_spec(spec: StageSpec, *, budget_tokens: int = PROMPT_BUDGET_TOKENS) -> list[Finding]:
    """Everything wrong with ``spec`` that loading it does not refuse."""
    verbs = {m.verb for m in spec.moves if m.verb}
    out: list[Finding] = []
    for move in spec.moves:
        if move.verb is not None:
            out += _guard(move)
            if not move.say:
                out.append(
                    Finding(
                        "warning",
                        move.id,
                        f"no say line: the model is never taught {{{move.verb}: …}}",
                    )
                )
            else:
                taught = set(_TAUGHT.findall(move.say))
                if move.verb not in taught:
                    out.append(
                        Finding(
                            "warning",
                            move.id,
                            f"its say line never writes {{{move.verb}: …}}, so the model "
                            "learns no example of it",
                        )
                    )
                for other in sorted(taught - verbs):
                    out.append(
                        Finding(
                            "error",
                            move.id,
                            f"its say line teaches {{{other}: …}}, which no move declares: "
                            "the model writes it and it is dropped",
                        )
                    )
        elif move.cls is not MoveClass.LOOK and not (move.claims or move.objects):
            out.append(
                Finding(
                    "warning",
                    move.id,
                    "a move that changes the page with no claims or objects: a reply "
                    "promising it and never sending it goes unnoticed",
                )
            )
        for arg in move.args:
            if arg.enum is not None and not arg.enum:
                out.append(Finding("error", move.id, f"{arg.name}'s enum allows nothing"))
    lines = spec.prompt_lines()
    tokens = sum(len(line) for line in lines) // 4
    if tokens > budget_tokens:
        out.append(
            Finding(
                "warning",
                "spec",
                f"the cue lines take about {tokens} tokens in every request; the budget is "
                f"{budget_tokens}",
            )
        )
    changed = {e.slice for e in spec.events}
    for sl in spec.slices:
        if sl.id not in changed:
            out.append(
                Finding("warning", sl.id, "no event changes this slice: it always reads unknown")
            )
    return out
