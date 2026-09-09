"""App events — what the person did on screen, declared as a shape.

:class:`~voqalize.sdk.actions.Action` is the brain telling the app what to render.
This is the mirror: the app telling the brain what the person did. Subclass
:class:`AppEvent` and your fields *are* the payload::

    class QuantitySet(AppEvent):
        item_id: str
        quantity: int

    EVENTS = AppEvents(QuantitySet, RowRemoved, OrderConfirmed)

    async def on_rtvi(self, session, msg):
        match EVENTS.parse(msg):
            case QuantitySet() as e:
                self.cart[e.item_id] = e.quantity

Everything ``Action`` gets from pydantic this gets too, in the direction that
needs it more: validation at the boundary, aliases, JSON-mode loading, and a JSON
Schema — which is what makes the TypeScript half generatable by ``voqalize types``
rather than hand-copied and silently drifting.

## Why typed, and why fine-grained

The shape this replaces is a whole-state push — a cart, a workspace, an
accessibility tree — echoed back on a debounce. It fails the same way every time.
Nothing in it *names* a change, so the brain has to diff its old picture against
the new one and infer which act produced the difference; every inference is a
place the two pictures can part company, and the best the model can then be told
is that *something* moved. It is also enormous: a real call put twenty-one full
carts in front of one model in 113 seconds, each labelled authoritative and none
of them dated.

``li3 quantity set to 5`` needs no diff, no inference, and no round trip to
interpret. It is also a sentence a model can read.

**There is nothing behind these events.** No snapshot, no repair channel — so
*completeness* is the property to hold, not idempotence: a gesture your app does
not send is a gesture the brain never learns about. That is a trade made on
purpose. A gap in your event vocabulary shows up as a gap, in a log, rather than
being quietly reconciled a beat later by a blob nobody reads.

## The wire name

Derived from the class name in ``snake_case``, exactly as an action's is —
``QuantitySet`` → ``quantity_set``. **The class name is part of your app
contract.** Pin it when you don't want that coupling::

    class QuantitySet(AppEvent, name="quantity_set"):
        ...

## The wire

An event rides RTVI's own ``ui-event``, which is what a stock pipecat client
sends::

    client.sendUIEvent("quantity_set", { item_id: "li3", quantity: 5 })
    # → {"event": "quantity_set", "payload": {...}}

:meth:`AppEvents.parse` also reads a ``client-message`` carrying ``{"t": name,
"d": payload}``, which is what apps written before ``ui-event`` send. **That path
is deprecated on arrival** — kept so a page already built on
``client.sendClientMessage`` can be picked up by a new brain without a rewrite,
not so anything new can be built on it. It warns once per process and will be
removed; move the page to ``sendUIEvent`` and there is nothing to migrate on this
side, because both arrive as the same typed event.

## Names are scoped to the set that declares them

There is no global registry, deliberately. Several brains share one process — the
demo umbrella runs a dozen — and two of them are entitled to both call something
``RowAdded``. An :class:`AppEvents` reads only the classes you hand it, so a name
means what your brain says it means and nothing leaks in from an import.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any, ClassVar

from loguru import logger
from pydantic import BaseModel, ConfigDict, ValidationError

from .actions import _snake_case
from .wire import RTVIType

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterator

    from .events import RTVIMessage

__all__ = ["AppEvent", "AppEvents"]

#: Said once per process, not once per tap: this fires on a live call, and a
#: deprecation the developer has already read is noise on every keystroke after.
_client_message_warned = False


def _warn_client_message(kind: str) -> None:
    """Both channels, once: a ``DeprecationWarning`` so a test suite run with
    ``-W error`` fails on it, and a log line because that is what anyone actually
    watching a deployed brain will see."""
    global _client_message_warned
    if _client_message_warned:
        return
    _client_message_warned = True
    message = (
        f"{kind!r} arrived on the deprecated 'client-message' envelope. Send it with "
        "client.sendUIEvent(name, payload) instead — it parses to the same typed event, "
        "and this path will be removed."
    )
    warnings.warn(message, DeprecationWarning, stacklevel=2)
    logger.warning(message)


class AppEvent(BaseModel):
    """One thing the person did to your app, named.

    ``extra="forbid"`` is deliberate on an *inbound* shape: a field this side does
    not know about is an app that has moved on, and that is worth a loud log
    rather than a silent read of a stale contract. It is not worth a crash — see
    :meth:`AppEvents.parse`."""

    #: The wire name, from the class name. Dunder for the same reason
    #: :class:`Action` uses one — a field called ``event`` must stay payload.
    __voqal_event__: ClassVar[str] = "app_event"

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    def __init_subclass__(cls, name: str | None = None, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.__voqal_event__ = name if name is not None else _snake_case(cls.__name__)


class AppEvents[E: AppEvent]:
    """The app→brain vocabulary of one brain, and the only thing that reads it.

    Hand it your event classes once; ask it to parse every RTVI message. A name it
    does not know, a payload that does not fit, or a message that is not an event
    at all are all ``None`` — never an exception on a live call, because an app one
    deploy ahead of its brain must not be able to end a call.

    Generic in the events it was handed, so :meth:`parse` returns *your* union and
    a ``match`` over it is checked for exhaustiveness — the same guarantee the
    generated ``unhandledUiAction`` gives the browser, in the other direction."""

    def __init__(self, *events: type[E]) -> None:
        self._by_name: dict[str, type[E]] = {}
        for event in events:
            name = event.__voqal_event__
            if (clash := self._by_name.get(name)) is not None:
                raise ValueError(
                    f"two events answer to {name!r}: {clash.__name__} and {event.__name__}. "
                    "Pin one with `class X(AppEvent, name=...)`."
                )
            self._by_name[name] = event

    def __iter__(self) -> Iterator[type[E]]:
        return iter(self._by_name.values())

    def __len__(self) -> int:
        return len(self._by_name)

    def parse(self, msg: RTVIMessage) -> E | None:
        """The event this message names, or ``None``.

        Reads RTVI's ``ui-event`` (``{"event": …, "payload": …}``) and, deprecated,
        a ``client-message`` carrying ``{"t": …, "d": …}`` — see the module
        docstring for why that one is still here and why it should not be reached
        for. It warns once per process, on the first ``client-message`` that
        actually resolves to an event: a name it does not know on that channel is
        your app's own business, not a deprecated event.

        Nothing here raises. An unknown name on ``ui-event`` is an app a deploy
        ahead of its brain naming an act this brain has never heard of — a real
        gap in the mirror, so it is logged loudly. On ``client-message`` it is
        merely a message that was never an event: your app's own requests share
        that channel, so that one is a debug line."""
        if not isinstance(msg.data, dict):
            return None
        if msg.type is RTVIType.UI_EVENT:
            kind, raw, dedicated = msg.data.get("event"), msg.data.get("payload"), True
        elif msg.type is RTVIType.CLIENT_MESSAGE:
            kind, raw, dedicated = msg.data.get("t"), msg.data.get("d"), False
        else:
            return None
        if not isinstance(kind, str):
            return None
        event = self._by_name.get(kind)
        if event is None:
            log = logger.warning if dedicated else logger.debug
            log("no app event answers to {!r}; the app knows an act this brain does not", kind)
            return None
        try:
            parsed = event.model_validate(raw if isinstance(raw, dict) else {})
        except ValidationError as exc:
            logger.warning("{} did not fit {}: {}", kind, event.__name__, exc.errors())
            return None
        if not dedicated:
            _warn_client_message(kind)
        return parsed
