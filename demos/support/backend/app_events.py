"""What the shopper did on their own — the browser→brain half of the contract.

The other direction is the :class:`~voqalize.sdk.Action` classes in ``brain.py``:
a declared shape whose wire name comes off the class name, validated at the call
site, with a generated TypeScript twin. :class:`~voqalize.sdk.AppEvent` is that,
mirrored — so ``on_rtvi`` narrows on a *type* rather than being handed a dict and
left to guess at its keys.

Both events here carry their payload, which is unusual and deliberate. A gesture
normally names an act and leaves the screen to be read back, because a value in
the context goes stale the moment the screen moves again. These two do not go
stale: a photo is a photograph the shopper took, and a confirmation number is
minted once and never changes. The browser is also the only place either one
exists — there is no tool that could read them back.

There is no "order opened" event. The catalog is compiled into the prompt, and
the assistant puts the order on screen itself.
"""

from __future__ import annotations

from pydantic import Field

from voqalize.sdk import AppEvent, AppEvents

__all__ = ["SUPPORT_EVENTS", "PhotoUploaded", "ReturnSubmitted", "SupportEvent"]


class PhotoUploaded(AppEvent):
    """The shopper photographed the item they are returning."""

    item_id: str = ""
    image: str = Field("", description="A data: URL — the captured frame, base64 in its tail.")


class ReturnSubmitted(AppEvent):
    """The shopper tapped submit, and the browser minted the confirmation number."""

    order_id: str = ""
    item_id: str = ""
    rma: str = ""


type SupportEvent = PhotoUploaded | ReturnSubmitted

SUPPORT_EVENTS = AppEvents[SupportEvent](PhotoUploaded, ReturnSubmitted)
