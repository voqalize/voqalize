"""``configure_soon`` — send a configuration change from a tool without waiting
for Voqalize's answer.

A tool runs while the user waits for the agent's next word, so it has to return
within the SDK's tool budget. :meth:`~voqalize.sdk.Session.configure` waits for
Voqalize to accept the change, which is a round trip, so a tool that switches the
language sends the request and returns. Nothing checks later that it applied: a
rejection is logged, and the call goes on in the language it was in.
"""

from __future__ import annotations

import asyncio

from loguru import logger

from voqalize.sdk import Session
from voqalize.sdk.wire import Config

#: How long every demo's recognizer waits through a pause, on the 0-to-10 scale:
#: the floor, the owner's call (2026-10-12). A demo is judged by how quickly the
#: agent answers, and the deployment's calibration (7, what a session that sets
#: nothing gets) is tuned for callers who are not watching a demo. The cost is a
#: visitor cut off when they pause mid-sentence: on Qween's first dialled call
#: at 0 (2026-09-29), a shopper who spoke in phrases had each half-formed reply
#: cancelled by their next phrase and heard nothing for as long as they kept
#: going, and the owner kept it at 0 having seen it. A desk that needs longer
#: raises its own patience for the step that needs it, as the kiosk does for
#: dictation, rather than this.
PATIENCE = 0

# Held here so a request in flight is not garbage-collected before it is sent.
_in_flight: set[asyncio.Task[None]] = set()


def configure_soon(session: Session, config: Config) -> None:
    """Send ``config`` and return at once; log it if Voqalize refuses it.

    ``Config`` still refuses a half-stated language pair when it is built, so
    that mistake raises here, in the tool, before anything is sent."""
    task = asyncio.get_running_loop().create_task(session.configure(config))
    _in_flight.add(task)
    task.add_done_callback(_settled)


def _settled(task: asyncio.Task[None]) -> None:
    _in_flight.discard(task)
    if task.cancelled():
        return
    if (exc := task.exception()) is not None:
        logger.warning("configure was not applied: {}", exc)


__all__ = ["configure_soon"]
