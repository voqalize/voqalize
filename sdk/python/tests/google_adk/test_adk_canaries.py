"""ADK-compat canaries — pin the ADK behaviors the corrector *couples to*, so an
ADK version bump fails a test that names the stale constant instead of silently
mis-correcting a live call.

The corrector (``google_adk/brain.py``) reaches into **no ADK-private attribute** —
it reads the session through the public ``SessionService.get_session`` and edits the
public ``llm_request.contents``. What remains are two couplings to ADK *behavior*
plus one to ADK's *callback contract*, none of which a normal unit test catches
(the scripted fake emits the hand-off itself, so it can't detect an ADK rename):

1. **ADK still names its hand-off tool ``transfer_to_agent``** and still renders it
   into a sub-agent's prompt as backtick-wrapped text — the ``_ADK_INTERNAL_TOOLS``
   coupling.
2. **ADK still stamps ``"For context:"``** on the flattened foreign-agent turn
   (``_convert_foreign_event``) — the ``_FOREIGN_CONTEXT_PREFIX`` coupling.
3. **ADK's ``PluginManager`` awaits an async plugin ``before_model_callback``** and
   lets its ``contents`` mutation reach the model — the contract that lets the
   corrector be a Runner-scoped plugin (``_make_corrector``) whose ``_correct`` is a
   coroutine and reaches into no ADK-private context.

(1) and (2) are asserted against **raw, uncorrected** ADK output — a bare
``InMemoryRunner`` with no corrector installed — so they observe ADK itself, not our
handling of it.
"""

from __future__ import annotations

import pytest

pytest.importorskip("google.adk")

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types

from voqalize.google_adk.brain import _ADK_INTERNAL_TOOLS, _FOREIGN_CONTEXT_PREFIX
from voqalize.google_adk.testing import ScriptedLlm, call, reply

APP = "voqalize"
UTTERANCE = "Book me a table for two at seven."


def _texts_of(content: object) -> list[str]:
    return [p.text for p in (getattr(content, "parts", None) or []) if getattr(p, "text", None)]


async def _run_to_completion(runner: InMemoryRunner, text: str) -> None:
    await runner.session_service.create_session(app_name=APP, user_id="u", session_id="s")
    msg = types.Content(role="user", parts=[types.Part(text=text)])
    async for _ in runner.run_async(user_id="u", session_id="s", new_message=msg):
        pass


async def test_adk_handoff_shape_matches_our_constants() -> None:
    """Drive a REAL ADK root→sub-agent hand-off through a bare runner (no corrector),
    then inspect the sub-agent's **raw** assembled prompt. It must carry a ``role=user``
    turn whose first text is ``_FOREIGN_CONTEXT_PREFIX`` and whose blob references every
    name in ``_ADK_INTERNAL_TOOLS`` as ``` `name` ```. If ADK renames the hand-off tool
    or rewords the context prefix, this fails and names the stale constant — the failure
    the corrector would otherwise swallow (a leaked routing artifact in every prompt)."""
    root_model = ScriptedLlm({UTTERANCE: [call("transfer_to_agent", agent_name="booking")]})
    booking_model = ScriptedLlm({UTTERANCE: [reply("Booked — a table for two at seven.")]})

    booking = LlmAgent(name="booking", model=booking_model, instruction="You book tables.")
    root = LlmAgent(
        name="triage", model=root_model, instruction="Route to booking.", sub_agents=[booking]
    )
    # No corrector — a bare ADK runner, so captured_contents is ADK's own raw output.
    await _run_to_completion(InMemoryRunner(agent=root, app_name=APP), UTTERANCE)

    assert booking_model.captured_contents, (
        "the sub-agent never ran — ADK did not execute `transfer_to_agent`, so its "
        "hand-off tool may have been renamed (_ADK_INTERNAL_TOOLS is stale)"
    )
    raw = booking_model.captured_contents[0]
    foreign = [
        c
        for c in raw
        if getattr(c, "role", None) == "user"
        and _texts_of(c)
        and _texts_of(c)[0].startswith(_FOREIGN_CONTEXT_PREFIX)
    ]
    assert foreign, (
        f"no raw sub-agent turn starts with {_FOREIGN_CONTEXT_PREFIX!r} — ADK's "
        "_convert_foreign_event wording changed; _FOREIGN_CONTEXT_PREFIX is stale"
    )
    blob = " ".join(t for c in foreign for t in _texts_of(c))
    for name in _ADK_INTERNAL_TOOLS:
        assert f"`{name}`" in blob, (
            f"ADK's hand-off context no longer references `{name}` — the flattened "
            "hand-off shape changed; _ADK_INTERNAL_TOOLS is stale"
        )


async def test_adk_awaits_async_plugin_before_model_callback() -> None:
    """Pin the contract the corrector now rides on: ADK's ``PluginManager`` invokes an
    **async** plugin ``before_model_callback`` (``await callback(...)`` in
    ``_run_callbacks``) and its in-place ``contents`` mutation reaches the model. The
    corrector is a Runner-scoped plugin (``_make_corrector``); if a future ADK stopped
    awaiting async plugin callbacks, ``_correct`` would return an un-awaited coroutine
    and heard-truth correction would silently stop — this catches that."""
    from google.adk.plugins.base_plugin import BasePlugin

    marker = "INJECTED_BY_ASYNC_PLUGIN"
    ran: list[bool] = []

    class _Spy(BasePlugin):
        def __init__(self) -> None:
            super().__init__(name="canary_spy")

        async def before_model_callback(self, *, callback_context, llm_request) -> None:
            ran.append(True)
            # Append a MODEL turn (leaves last-user-text — the fake's script key —
            # untouched) so we can prove the mutation propagated to the model.
            llm_request.contents = [
                *llm_request.contents,
                types.Content(role="model", parts=[types.Part(text=marker)]),
            ]

    model = ScriptedLlm({UTTERANCE: [reply("Done.")]})
    agent = LlmAgent(name="a", model=model, instruction="Assist.")
    runner = InMemoryRunner(agent=agent, app_name=APP)
    runner.plugin_manager.register_plugin(_Spy())
    await _run_to_completion(runner, UTTERANCE)

    assert ran, "ADK did not invoke the async plugin before_model_callback at all"
    assert model.captured_contents, "the model never ran"
    seen = " ".join(t for c in model.captured_contents[0] for t in _texts_of(c))
    assert marker in seen, (
        "the async plugin ran but its contents mutation never reached the model — "
        "ADK may no longer await an async plugin before_model_callback (_correct would break)"
    )
