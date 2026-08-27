"""A second module of actions, to prove the generator scopes to one namespace."""

from __future__ import annotations

from voqalize.sdk import Action


class Unrelated(Action):
    x: int = 0
