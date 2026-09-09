"""What the patient did with their thumb — the browser→brain half of the screen
contract.

The other direction is the :class:`~voqalize.sdk.Action` classes in ``brain.py``:
a declared shape whose wire name comes off the class name, validated at the call
site, with a generated TypeScript twin. :class:`~voqalize.sdk.AppEvent` is that,
mirrored — so ``on_rtvi`` narrows on a *type* rather than reading a snapshot and
working out what changed in it.

There are only two. This screen is almost entirely the coach's to move; what the
patient can do by hand is confirm the sensor order off the card, and close the
video. That is the whole vocabulary, and it being this short is the point: a
snapshot push carries the other forty fields on every keystroke to say the same
two things.

There is no "check-in opened" event. The day's meals, ticks and sensor status
arrive in ``session.init`` before the first word — the brain builds its mirror
from those, rather than waiting for the browser to hand back what it was given.
"""

from __future__ import annotations

from voqalize.sdk import AppEvent, AppEvents

__all__ = ["SUGAR_EVENTS", "SensorOrderConfirmed", "SugarEvent", "VideoClosed"]


class SensorOrderConfirmed(AppEvent):
    """The patient tapped Confirm on the sensor-replacement card themselves,
    rather than agreeing out loud. The order is placed; the coach must not call
    ``confirm_sensor_order`` on top of it."""


class VideoClosed(AppEvent):
    """The patient shut the video the coach opened. Nothing is playing."""


type SugarEvent = SensorOrderConfirmed | VideoClosed

SUGAR_EVENTS = AppEvents[SugarEvent](SensorOrderConfirmed, VideoClosed)
