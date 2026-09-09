"""Typed app events: the browser→brain half of the same contract.

:class:`~voqalize.sdk.Action` says what to render; :class:`~voqalize.sdk.AppEvent`
says what the person did. This file pins the three things a brain depends on — the
wire **name** derived from the class, the two wire **shapes** an event can arrive
in, and the promise that **nothing an app sends can raise**, because an app one
deploy ahead of its brain must not be able to end a call.
"""

from __future__ import annotations

import warnings

import pytest
from pydantic import Field

from voqalize.sdk import AppEvent, AppEvents, app_events
from voqalize.sdk.events import RTVIMessage
from voqalize.sdk.wire import RTVIType


@pytest.fixture(autouse=True)
def _unwarned() -> None:
    """The deprecation is once *per process*, so without this the second test to
    touch it would pass by inheriting the first one's silence."""
    app_events._client_message_warned = False


class QuantitySet(AppEvent):
    item_id: str
    quantity: int


class RowRemoved(AppEvent):
    item_id: str
    reason: str | None = None


class OrderConfirmed(AppEvent, name="confirmed"):
    total_paise: int = Field(alias="totalPaise")


EVENTS = AppEvents(QuantitySet, RowRemoved, OrderConfirmed)


def _ui(event: str, payload: object) -> RTVIMessage:
    return RTVIMessage(type=RTVIType.UI_EVENT, data={"event": event, "payload": payload})


def _client(kind: str, payload: object) -> RTVIMessage:
    return RTVIMessage(type=RTVIType.CLIENT_MESSAGE, data={"t": kind, "d": payload})


def test_the_class_name_is_the_wire_name() -> None:
    assert QuantitySet.__voqal_event__ == "quantity_set"
    assert RowRemoved.__voqal_event__ == "row_removed"


def test_a_pinned_name_survives_a_rename() -> None:
    assert OrderConfirmed.__voqal_event__ == "confirmed"


def test_an_event_arrives_typed_from_the_channel_we_teach() -> None:
    event = EVENTS.parse(_ui("quantity_set", {"item_id": "li3", "quantity": 5}))
    assert event == QuantitySet(item_id="li3", quantity=5)


def test_the_older_channel_still_parses_but_says_so() -> None:
    """``client-message`` predates RTVI's ``ui-event``. A page already built on it
    must not break — that is the whole reason the arm is still here — but nothing
    new should be built on it, so it is deprecated rather than silently equal."""
    with pytest.deprecated_call(match="sendUIEvent"):
        event = EVENTS.parse(_client("quantity_set", {"item_id": "li3", "quantity": 5}))
    assert event == QuantitySet(item_id="li3", quantity=5)


def test_the_deprecation_is_said_once_not_once_per_tap() -> None:
    """It fires on a live call. A developer who has read it once does not need it
    again on every keystroke for the rest of the session."""
    with pytest.deprecated_call():
        EVENTS.parse(_client("quantity_set", {"item_id": "li3", "quantity": 5}))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert EVENTS.parse(_client("quantity_set", {"item_id": "li3", "quantity": 6}))


def test_a_message_that_was_never_an_event_is_not_a_deprecation() -> None:
    """Your app's own requests share that channel. Warning about a name this set
    does not hold would be scolding an app for a message that has nothing to do
    with app events."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert EVENTS.parse(_client("open_the_pod_bay_doors", {})) is None


@pytest.mark.parametrize(
    "msg",
    [
        _ui("never_heard_of_it", {}),
        _ui("quantity_set", {"item_id": "li3"}),
        _ui("quantity_set", {"item_id": "li3", "quantity": 5, "colour": "red"}),
        _ui("quantity_set", "not a payload at all"),
        _ui("quantity_set", None),
        _ui(None, {}),  # type: ignore[arg-type]
        _client("catalog_search", {"query": "shelcal"}),
        RTVIMessage(type=RTVIType.UI_EVENT, data="a string"),
        RTVIMessage(type=RTVIType.SEND_TEXT, data={"event": "quantity_set"}),
    ],
)
def test_nothing_an_app_can_send_raises(msg: RTVIMessage) -> None:
    assert EVENTS.parse(msg) is None


def test_a_set_reads_only_the_events_it_was_handed() -> None:
    """No global registry: two brains in one process may both declare ``RowRemoved``."""
    narrow = AppEvents(QuantitySet)
    assert narrow.parse(_ui("row_removed", {"item_id": "li3"})) is None
    assert len(narrow) == 1
    assert [e.__name__ for e in EVENTS] == ["QuantitySet", "RowRemoved", "OrderConfirmed"]


def test_two_events_answering_to_one_name_is_a_declaration_error() -> None:
    class RowRemovedToo(AppEvent, name="row_removed"):
        item_id: str

    with pytest.raises(ValueError, match="row_removed"):
        AppEvents(RowRemoved, RowRemovedToo)


def test_an_alias_is_read_from_the_wire_and_the_field_name_both() -> None:
    assert EVENTS.parse(_ui("confirmed", {"totalPaise": 4200})) == OrderConfirmed(totalPaise=4200)
    assert EVENTS.parse(_ui("confirmed", {"total_paise": 4200})) == OrderConfirmed(totalPaise=4200)
