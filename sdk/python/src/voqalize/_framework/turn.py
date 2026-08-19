"""Run one driven interaction in its ``voice()`` context, with a no-dead-air guarantee.

Every adapter's ``on_interaction`` does the same two things: publish the live turn on
the context var (so a native tool's :func:`~voqalize._framework.context.voice` call
resolves) around the driven run, and make sure the turn produces *some* audio even
when the run fails. :func:`run_turn` owns both, so the three adapters can't drift on
either.

The no-dead-air contract
-------------------------
A voice turn that ends in silence is a UX failure: the user asked something and heard
nothing back. Two failure classes cause it, and this module handles the second:

* the interaction never *terminates* — the SDK core handles that (the turn task
  always unwinds, even if the brain raised). That keeps the *session* alive.
* the interaction terminates but the brain never *spoke*. Two ways this happens:
  the driven run **raised** (a tool raised and the framework couldn't recover, or the
  model call itself errored), or it **returned cleanly but silently** (the model
  produced an empty or safety-blocked reply — no text, no error). Either way the turn
  completes, so the session lives, but the user got silence. :func:`run_turn` covers
  **both**: it catches the error, and — error or not — checks whether the turn spoke,
  speaking a short fallback if it didn't, so the turn always has a voice.

Barge-in is **not** a failure: a ``CancelledError`` is the user interrupting, and it
must propagate untouched (the driver finalizes the cut inference). :func:`run_turn` only ever handles a real :class:`Exception`; a barged
turn that spoke a partial before the cut is not "silent".

The turn watchdog (``turn_timeout``)
------------------------------------
A third way a turn strands the user: it neither raises nor returns — it *hangs*. A
tool that never comes back, a model stream that stalls, a runaway loop — the driven
run just never completes and the rest of the call is dead air (only a barge-in would rescue it). :func:`run_turn` bounds this
with an optional ``turn_timeout``: it runs ``drive()`` under
:func:`asyncio.wait_for`, and a timeout cancels the stuck run (unwinding its open
brackets), speaks the fallback, and lets the turn complete — the same recovery as a
raised error. The watchdog-cancel surfaces as :class:`TimeoutError`, which is a
plain :class:`Exception`, so it is cleanly distinct from a user barge-in's
:class:`asyncio.CancelledError` (which still propagates and skips completion).
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

from loguru import logger

from voqalize._framework.context import _CURRENT, Voice, _Turn

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from voqalize.sdk.brain import Interaction

# The default spoken recovery line. Short, apologetic, and actionable — it invites a
# retry rather than dead-ending. Each ``*_brain(...)`` entry point can override it, or
# pass ``None`` to opt out (the raw-abort behaviour, for advanced callers who handle
# errors their own way).
DEFAULT_ERROR_FALLBACK = "Sorry, I ran into a problem just now. Could you try that again?"

# The default turn watchdog: no single voice turn should take a minute, but a
# multi-round tool turn legitimately can, so the ceiling is generous. It only ever
# matters when the user is passively waiting — a barge-in cancels far sooner. Each
# ``*_brain(...)`` entry point can override it, or pass ``None`` to disable it.
DEFAULT_TURN_TIMEOUT = 60.0


async def speak_error_fallback(interaction: Interaction, message: str | None) -> None:
    """Speak ``message`` in a fresh inference bracket, so a failed turn still has a
    voice. A falsy ``message`` disables the fallback (opt-out). Any failure to speak
    it (e.g. the socket is already gone) is suppressed — the fallback must never
    become a second source of errors."""
    if not message:
        return
    with contextlib.suppress(Exception):
        async with interaction.say() as inf:
            await inf.speak(message)


async def run_turn(
    interaction: Interaction,
    drive: Callable[[], Awaitable[None]],
    *,
    error_fallback: str | None,
    turn_timeout: float | None = None,
) -> None:
    """Run ``drive()`` as the response to ``interaction``, inside the turn's
    ``voice()`` context and under the no-dead-air guarantee.

    Publishes a :class:`_Turn` on the context var so async tools resolve
    :func:`voice` in the run's context, then awaits ``drive`` (under a
    ``turn_timeout`` watchdog when one is given). A :class:`asyncio.CancelledError`
    (barge-in) propagates untouched; a watchdog :class:`TimeoutError` or any other
    :class:`Exception` is logged and answered with :func:`speak_error_fallback`. If
    the run instead returns cleanly but produced no speech at all (an empty or
    safety-blocked model reply), the fallback is spoken too — so a turn never ends in
    silence, whether it failed loudly, quietly, or by hanging."""
    turn = _Turn(interaction=interaction, voice=Voice(interaction))
    # Set the context BEFORE driving so a framework that runs tools in a background
    # task (the OpenAI/ADK Runners) copies it into that task — the tool then resolves
    # voice() in the turn's context. wait_for's inner Task also snapshots this
    # context at creation, so the watchdog doesn't sever voice() from the run.
    token = _CURRENT.set(turn)
    try:
        if turn_timeout is not None:
            await asyncio.wait_for(drive(), turn_timeout)
        else:
            await drive()
    except asyncio.CancelledError:
        raise
    except TimeoutError:
        # The watchdog fired: the run hung past turn_timeout. wait_for has already
        # cancelled it (unwinding its open brackets); complete the turn with a spoken
        # fallback rather than leave the user waiting on a run that never returns.
        logger.warning(
            "voqalize: interaction {} exceeded turn_timeout={}s; speaking fallback",
            interaction.id,
            turn_timeout,
        )
        await speak_error_fallback(interaction, error_fallback)
    except Exception:
        logger.exception(
            "voqalize: interaction {} failed mid-turn; speaking error fallback",
            interaction.id,
        )
        await speak_error_fallback(interaction, error_fallback)
    else:
        # Clean return, but the turn may have said nothing (empty/safety-blocked
        # reply). Don't leave the user in silence — speak the same fallback.
        if not interaction.spoke:
            logger.warning(
                "voqalize: interaction {} produced no speech; speaking fallback",
                interaction.id,
            )
            await speak_error_fallback(interaction, error_fallback)
    finally:
        _CURRENT.reset(token)
