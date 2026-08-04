"""The ``voice()`` accessor — how a native tool reaches the live turn.

A native tool is the *framework's* object: a plain function the framework (ADK)
calls. It has no Voqalize argument, and we do not want to force one — the whole
promise is "your tools stay native." So the SDK exposes the current interaction
through a :class:`~contextvars.ContextVar` the adapter sets around the driven run:
a tool that runs inside that call reads it with :func:`voice`.

    from voqalize.google_adk import voice
    from voqalize.sdk import Action

    class RenderFlights(Action):                 # the browser contract, declared
        flights: list[Flight]

    async def search_flights(destination: str) -> SearchResult:
        flights = await backend.search(destination)
        voice().action(RenderFlights(flights=flights))   # UI side-effect
        return SearchResult(flights=flights)             # goes back to the LLM

(Both halves are typed: the ``Action`` is dumped by alias onto the ``ui_command``
envelope, and a pydantic return value is dumped the same way before ADK hands it
to the model — see :mod:`voqalize.sdk.actions` and
:func:`voqalize._framework.coerce.coerce_result`.)

Because the ambient context propagates into the task that runs the tool,
``voice()`` resolves for **async** tools with no plumbing. Prefer async tools; a
sync tool dispatched on a thread pool runs in a fresh context where the var is
unset, so :func:`voice` would raise :class:`NoActiveVoice` there.

Framework-agnostic: nothing here imports ADK or google-genai.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, overload

from voqalize.sdk.actions import Action

if TYPE_CHECKING:
    from collections.abc import Callable

    from voqalize.sdk.brain import Interaction, Outcome


class NoActiveVoice(RuntimeError):
    """Raised when :func:`voice` is called outside a live interaction turn.

    This means the code ran outside the adapter's driven-run scope — typically a
    synchronous tool dispatched on a thread pool (fresh context, var unset). Make
    the tool ``async`` so it runs in the turn's context."""


class Voice:
    """The narrow capability a tool gets over the live turn.

    Deliberately *not* the raw :class:`~voqalize.sdk.brain.Interaction`: a tool
    must never open its own inference bracket (the SDK drives the run loop and owns
    speech). What it *may* do is fire a UI command and reconfigure the voice.
    """

    def __init__(self, interaction: Interaction) -> None:
        self._interaction = interaction

    @property
    def interaction_id(self) -> int:
        return self._interaction.id

    @overload
    def action(
        self, action: Action, /, *, callback: Callable[[Outcome], Any] | None = None
    ) -> int: ...

    @overload
    def action(
        self,
        name: str,
        args: dict[str, Any] | None = None,
        *,
        callback: Callable[[Outcome], Any] | None = None,
    ) -> int: ...

    def action(
        self,
        name: str | Action,
        args: dict[str, Any] | None = None,
        *,
        callback: Callable[[Outcome], Any] | None = None,
    ) -> int:
        """Fire a UI command to the browser, attributed to this turn.

        Takes either a typed :class:`~voqalize.sdk.Action` instance
        (``voice().action(SearchFlights(leg_id=..., options=...))``) or the legacy
        ``(name, args)`` pair. See :meth:`voqalize.sdk.brain.Interaction.action`."""
        if isinstance(name, Action):
            return self._interaction.action(name, callback=callback)
        return self._interaction.action(name, args, callback=callback)

    def configure_language(self, language: str, *, voice: str | None = None) -> None:
        """Switch the whole call to another language — the only supported way.

        See :meth:`voqalize.sdk.brain.Session.configure_language`: doing it as a
        ``configure_tts`` + ``configure_stt`` pair can half-apply, and a
        half-applied language is silent.
        """
        self._interaction.session.configure_language(language, voice=voice)

    def configure_tts(self, **kwargs: Any) -> None:
        """Change TTS voice/language/model for the next inference (mid-call)."""
        self._interaction.session.configure_tts(**kwargs)

    def configure_stt(self, **kwargs: Any) -> None:
        """Change STT VAD/turn-detection knobs live (mid-call)."""
        self._interaction.session.configure_stt(**kwargs)


@dataclass
class _Turn:
    """Adapter-private per-interaction state, published on the context var.

    Holds the live ``interaction`` and its :class:`Voice` (what a native tool reaches
    through :func:`voice`). Discarded at turn end; only the framework-owned heard
    transcript survives."""

    interaction: Interaction
    voice: Voice


_CURRENT: ContextVar[_Turn | None] = ContextVar("voqalize_turn", default=None)


def voice() -> Voice:
    """The :class:`Voice` for the interaction currently being served.

    Call it from inside a tool (or any code reached during the driven run). Raises
    :class:`NoActiveVoice` if there is no active turn in this context."""
    turn = _CURRENT.get()
    if turn is None:
        raise NoActiveVoice(
            "voice() called outside a live interaction — is this a synchronous tool "
            "dispatched on a thread pool? Make the tool async so it runs in the "
            "turn's context."
        )
    return turn.voice
