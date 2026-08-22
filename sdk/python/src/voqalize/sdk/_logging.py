"""Session-scoped logging for your brain.

A voice call touches several processes — Voqalize, the relay, the
control plane, and *your* brain — and every process on our side already puts the same
``session_id`` on every line it writes. Your brain is where your own code runs, so
it is where the interesting logs are, and without the same tag they are the only
ones that cannot be joined to the rest of the call.

Two pieces, and the split between them is deliberate.

**The context is free and always on.** Every session runs inside
``session_context(...)``, which puts the call's identity into loguru's ``extra``
via a ``ContextVar``. An ``asyncio.Task`` copies the ambient context when it is
created, so your own coroutines — and anything they spawn — inherit it, and a
bare ``from loguru import logger`` anywhere in your brain logs with the session
attached without threading an argument through every signature. This costs you
nothing and cannot break your setup: it only *adds* fields, which your sink is
free to ignore.

**The sink is opt-in.** ``configure_logging()`` is never called by the SDK. A
library that calls ``logger.remove()`` at import time silently deletes the
handlers its host installed, and your brain runs inside *your* application. So
the SDK adds fields and leaves rendering alone: if you have no loguru setup of
your own, call ``configure_logging()`` and get the identity fields rendered; if
you do have one, add ``{extra}`` to your format instead.

That distinction is worth stating because getting it backwards is a real failure
mode — binding fields onto a handler whose format never prints them looks exactly
like working, and every one of those fields is computed and thrown away.

Field names match what Voqalize writes — ``service``, ``session_id``,
``tenant_id``, ``agent_id`` — because being joinable across the whole call is
the entire point.
"""

from __future__ import annotations

import json
import sys
import traceback
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from loguru import logger

SERVICE_NAME = "brain"

# The identity fields that make a line joinable to the same call elsewhere. Kept
# as an explicit tuple so the JSON sink promotes exactly these and leaves your
# own bound fields in `extra`.
IDENTITY_FIELDS = ("session_id", "tenant_id", "agent_id")


@contextmanager
def session_context(
    session_id: str,
    *,
    tenant_id: str = "",
    agent_id: str = "",
) -> Generator[None]:
    """Tag every log line emitted inside this block — and inside any task it
    spawns — with the call's identity.

    Ids are carried whole. A truncated id reads better in a terminal and is
    useless as a join key: Voqalize and the session's own records carry the full
    UUID, so a prefix matches nothing on the other side of the query.
    """
    fields: dict[str, str] = {"service": SERVICE_NAME, "session_id": session_id}
    if tenant_id:
        fields["tenant_id"] = tenant_id
    if agent_id:
        fields["agent_id"] = agent_id
    with logger.contextualize(**fields):
        yield


def _json_sink(message: Any) -> None:
    record = message.record
    extra = dict(record["extra"])
    entry: dict[str, Any] = {
        "timestamp": record["time"].isoformat(),
        "level": record["level"].name,
        "message": record["message"],
        "logger": record["name"],
        "function": record["function"],
        "line": record["line"],
    }
    entry["service"] = extra.pop("service", SERVICE_NAME)
    for field in IDENTITY_FIELDS:
        value = extra.pop(field, "")
        if value:
            entry[field] = value
    if extra:
        entry["fields"] = extra
    if record["exception"] is not None:
        exc = record["exception"]
        entry["exception"] = "".join(traceback.format_exception(exc.type, exc.value, exc.traceback))
    sys.stderr.write(json.dumps(entry, default=str) + "\n")


_CONSOLE_FORMAT = (
    "<green>{time:HH:mm:ss.SSS}</green> <level>{level: <8}</level> "
    "<cyan>{extra[session_id]}</cyan> <level>{message}</level>"
)


def configure_logging(*, level: str = "INFO", json_logs: bool = False) -> None:
    """Install a loguru sink that actually renders the session fields.

    **Opt-in — the SDK never calls this for you.** It replaces loguru's handlers
    for the whole process, which a library has no business doing to its host.
    Call it from your own entrypoint if you have no loguru configuration of your
    own; if you do have one, add ``{extra}`` to your format instead and skip
    this entirely.

    ``json_logs=True`` writes one JSON object per line with the identity fields
    promoted to top level — the shape a log shipper can index on, and the same
    shape Voqalize writes.
    """
    logger.remove()
    if json_logs:
        logger.add(_json_sink, level=level)
        return
    # `extra[session_id]` would raise on a line logged outside any session, so
    # every line gets the key whether or not it is in one.
    logger.configure(extra={"session_id": "-", "service": SERVICE_NAME})
    logger.add(sys.stderr, level=level, format=_CONSOLE_FORMAT)
