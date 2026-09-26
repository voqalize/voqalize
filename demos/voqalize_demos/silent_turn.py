"""A turn that acted on screen and said nothing is asked once more.

The loop runs a tool call and files its result for the *next* request, so a
response made of calls alone ends the turn in silence: the screen changes and the
user hears nothing until PyGato's watchdog apologises for the runtime ten seconds
later. Every prompt here tells the model to say a short line and call in the same
response, and on a dialled call it still did not, on an action tool, in most of
the demos (tool-loop program, D2, 2026-09-26). A prompt is a request; this is the
floor under it.

When the model's turn is over, spoke nothing, and something landed on screen,
:func:`reask_if_silent` runs the model's turn once more. No note goes with it: the
context now ends in the call and its result, and a model handed a result says
what happened, in the language the conversation is in, with the words it would
have used. That last part is why it is a second request and not a canned line of
the brain's own — travel says "Flights are up." from a pool, which holds in one
language, and several demos here speak whatever the user speaks.

It costs one request, about as long as the second hop of a tool marked
``needs_result_now``, and only on a turn that would otherwise be silent. A turn
that spoke, or that only read, runs exactly as before. Once only: a model that acts
silently twice is not converging, and the watchdog is still there.

What a brain does to use it::

    def _show(self, action):
        self.session.dispatch(action)
        acted(type(action).__name__)

    async def respond(self, session):
        async for event in reask_if_silent(super().respond, session):
            yield event
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator, Callable
from contextvars import ContextVar

from loguru import logger

from voqalize.sdk import Session, Speech, SpeechStart

#: What landed on screen in the turn under way, by name. Per turn, not per brain:
#: each turn runs in its own task, and turns overlap when the agent speaks again
#: before the last response has finished streaming, so a record on the brain would
#: hand one turn's dispatch to the other.
_ACTED: ContextVar[list[str] | None] = ContextVar("silent_turn_acted", default=None)


def acted(what: str) -> None:
    """Record that the turn under way put ``what`` on screen.

    Call it beside the dispatch of anything the user sees move. A read, and a
    dispatch the user does not see as an answer, need not call it. Outside a turn
    it does nothing."""
    if (record := _ACTED.get()) is not None:
        record.append(what)


async def reask_if_silent(
    respond: Callable[[Session], AsyncGenerator[Speech, None]], session: Session
) -> AsyncGenerator[Speech, None]:
    """The model's turn, run once more if it acted on screen and said nothing.

    ``respond`` is the inherited turn — ``super().respond`` — so whatever a brain
    layers around it stays outside this."""
    for attempt in ("first", "again"):
        record: list[str] = []
        token = _ACTED.set(record)
        turn = respond(session)
        spoke = False
        try:
            async for event in turn:
                spoke = spoke or isinstance(event, SpeechStart)
                yield event
        finally:
            await turn.aclose()
            # Closed from another context, the token cannot be reset — and there
            # is nothing to reset: the value went with the task that set it.
            with contextlib.suppress(ValueError):
                _ACTED.reset(token)
        if spoke or not record:
            return
        if attempt == "again":
            logger.warning("turn: acted on screen ({}) and said nothing again", ", ".join(record))
            return
        logger.warning(
            "turn: acted on screen ({}) and said nothing; asking the model once more",
            ", ".join(record),
        )
