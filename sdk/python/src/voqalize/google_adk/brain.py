"""``adk_brain`` — host a native Google ADK agent as a Voqalize :class:`Brain`.

This is the *SDK-drives-the-loop* integration from ``docs/sdk_design.md`` made
real for one framework. The client writes a normal ADK ``LlmAgent`` (model,
instruction, native tools) and hands the SDK a *factory* for it. The SDK then:

* drives ``Runner.run_async`` once per interaction — the client never runs the
  loop, never touches the wire, never manages history;
* opens **one inference bracket per model call** and speaks that call's text, so
  barge-in can cut a reply between the tool-call turn and the answer turn;
* keeps **ADK's own session the source of truth** and merely *corrects* it to
  heard-truth. A customer chooses ADK precisely because its ``SessionService`` is
  the persistence *they* control — their tool/thought log, their resumability, and
  any event they add out of band (a retrieved doc, a CRM note, a policy reminder).
  So the model prompts from ADK's session, not a parallel SDK-owned store. Two
  small, in-place corrections keep it honest:

  - On barge-in we append an **accountant event** to ADK's session — a
    ``role="model"`` turn carrying the *heard* prefix, plus
    ``custom_metadata["voqalize.heard"]`` naming the superseded *generated* reply.
    Where ADK never persisted the reply (a mid-stream barge — partials are never
    appended), the accountant event simply *supplies* the heard turn.
  - A ``before_model_callback`` corrector — registered as a single Runner-scoped
    ADK *plugin* (:func:`_make_corrector`), so it fires for the root agent and every
    sub-agent alike — reads ADK's own event log, drops the superseded generated reply
    the accountant marked (exact-text match), filters ADK's internal control tools
    (the multi-agent hand-off) and any private thinking parts out of the prompt, and
    otherwise leaves history untouched — so the customer's out-of-band events flow
    straight through to the model.

    from voqalize.google_adk import adk_brain, voice
    from voqalize.sdk import serve_direct

    def build_agent() -> LlmAgent:
        return LlmAgent(name="assistant", model="gemini-2.0-flash", tools=[...])

    await serve_direct(adk_brain(build_agent, greeting="Hi! How can I help?"))

What the client writes: the ``LlmAgent`` and its tools (tools call
:func:`voice` for UI side-effects). What the SDK provides: everything else —
the run loop, brackets, heard-truth correction, barge-in, the wire.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from loguru import logger

from voqalize._framework.brain import _FrameworkBrain
from voqalize._framework.heard import spoken_text_of
from voqalize._framework.resume import resolve_greeting
from voqalize._framework.turn import DEFAULT_ERROR_FALLBACK, DEFAULT_TURN_TIMEOUT
from voqalize.sdk.brain import Brain

if TYPE_CHECKING:
    from collections.abc import Sequence

    from google.adk.agents import LlmAgent
    from google.adk.runners import Runner

    from voqalize._framework.resume import GreetingHook
    from voqalize.sdk.brain import Inference, Interaction, Message, Session, SessionStart


# ADK's built-in control tools — bookkeeping the runtime injects (e.g. the
# multi-agent hand-off tool), not the client's tools. They are filtered OUT of the
# prompt the corrector hands the model: replaying ``transfer_to_agent`` as a tool
# exchange would leak an internal routing artifact into every later turn.
_ADK_INTERNAL_TOOLS = frozenset({"transfer_to_agent"})

# The metadata key on an accountant event carrying heard-truth for one inference.
# Lives on ``Event.custom_metadata`` (survives in ADK's session even though ADK
# strips it from ``llm_request.contents``), so the corrector can find which
# generated reply the user only heard a prefix of.
HEARD_METADATA_KEY = "voqalize.heard"

# The literal prefix ADK stamps on a foreign agent's events when it flattens them
# into a ``role="user"`` context turn for a sub-agent (ADK ``_convert_foreign_event``).
# The hand-off's ``transfer_to_agent`` call/response arrive as *text* in one of these
# turns — not as function parts — so the part-level tool filter can't reach them; we
# match this prefix plus ADK's backtick-wrapped tool name to drop the whole turn.
_FOREIGN_CONTEXT_PREFIX = "For context:"


@dataclass
class _InferenceRecord:
    """Per-inference bookkeeping populated as ``_drive`` streams a model call, read
    once at finalize to write the accountant event. Correlates the SDK's
    ``(interaction_id, inference_id)`` to ADK's ``invocation_id`` and the persisted
    model event, so the accountant event points at the exact reply it supersedes."""

    invocation_id: str | None = None
    generated_text: str = ""
    event_id: str | None = None


@dataclass
class _Supersession:
    """One barged reply the corrector must remove from ADK's assembled prompt: the
    full ``generated`` text ADK persisted, the ``heard`` prefix that stands in its
    place, and ``target_event_id`` — the id of the persisted model event.

    ``target_event_id`` is the load-bearing signal: a mid-stream barge is never
    persisted (partials aren't appended), so its id is ``None`` and there is nothing
    in the prompt to drop — the accountant's heard turn simply stands. Only a
    *persisted* reply (id present) is actually in ``contents`` and must be removed.
    Supersessions are read in session order so repeated reply text is disambiguated
    by position + adjacency, never by a global text match."""

    generated: str
    heard: str
    target_event_id: str | None


def _make_corrector(correct: Callable[[Any, Any], Awaitable[None]]) -> Any:
    """Build the heard-truth corrector as an ADK **Runner-scoped plugin**.

    A plugin's ``before_model_callback`` fires for *every* model call in the agent
    tree — the root agent and each sub-agent alike — from a single registration on
    the Runner (ADK ``PluginManager``). It runs *before* the agents' own callbacks,
    on the same fully-assembled ``llm_request``, and is awaited
    (``PluginManager._run_callbacks`` does ``await callback(...)``), so the corrector
    sees exactly the contents the model will (see :meth:`AdkBrain._correct`). A
    multi-agent app's sub-agents make their **own** model calls; one plugin
    registration corrects them all — no walking the ``sub_agents`` tree.

    Living on the Runner — which :class:`AdkBrain` builds fresh per session — instead
    of being mutated onto the agent object, the corrector also cannot *stack*: a
    client whose factory returns one shared ``LlmAgent`` across sessions still gets
    exactly one corrector, on each session's own runner. That structural property (no
    shared-agent corruption, and no dependence on preserving a client's own
    ``before_model_callback``) is the reason this is a plugin rather than a per-agent
    callback appended across the tree."""
    from google.adk.plugins.base_plugin import BasePlugin

    class _HeardTruthCorrector(BasePlugin):
        def __init__(self) -> None:
            super().__init__(name="voqalize_heard_truth")

        async def before_model_callback(self, *, callback_context: Any, llm_request: Any) -> None:
            # Reconcile in place; an implicit None return lets the corrected call proceed
            # (a non-None return would short-circuit the model with a cached response).
            await correct(callback_context, llm_request)

    return _HeardTruthCorrector()


# ─── content helpers (operate on genai ``types.Content`` / ``Part``) ───────────


def _text_of_parts(parts: list[Any]) -> str:
    """Concatenated text of a part list (ignores non-text parts)."""
    return "".join(p.text for p in parts if getattr(p, "text", None))


def _is_internal_tool_part(part: Any) -> bool:
    """Whether ``part`` is a call to / response from an ADK-internal control tool."""
    fc = getattr(part, "function_call", None)
    if fc is not None and fc.name in _ADK_INTERNAL_TOOLS:
        return True
    fr = getattr(part, "function_response", None)
    return fr is not None and fr.name in _ADK_INTERNAL_TOOLS


def _keep_parts(content: Any) -> list[Any]:
    """The parts of ``content`` that belong in the prompt — internal-tool parts (the
    hand-off) and private thinking parts (``thought=True``) filtered out."""
    parts = getattr(content, "parts", None) or []
    return [p for p in parts if not _is_internal_tool_part(p) and not getattr(p, "thought", False)]


def _is_internal_foreign_context(content: Any) -> bool:
    """Whether ``content`` is ADK's flattened context turn for an internal control
    tool. ADK converts another agent's events into a ``role="user"`` turn whose first
    text part is ``"For context:"`` followed by ``[author] called tool `name` …`` /
    ``[author] `name` tool returned result: …`` (ADK ``_convert_foreign_event``). When
    ``name`` is the hand-off, the whole turn is routing bookkeeping — not
    conversation — and must not reach the sub-agent's prompt (nor become a fake
    model's script key)."""
    if getattr(content, "role", None) != "user":
        return False
    texts = [p.text for p in (getattr(content, "parts", None) or []) if getattr(p, "text", None)]
    if not texts or not texts[0].startswith(_FOREIGN_CONTEXT_PREFIX):
        return False
    blob = " ".join(texts)
    return any(f"`{name}`" in blob for name in _ADK_INTERNAL_TOOLS)


# ─── the adapter ──────────────────────────────────────────────────────────────


class AdkBrain(_FrameworkBrain):
    """A :class:`Brain` that drives an ADK ``Runner`` per interaction.

    Subclass it to build a voice agent — hand your ``LlmAgent`` factory to
    ``super().__init__(...)`` and override the Voice seams you care about
    (``on_user_idle`` / ``on_client_message`` / ``on_resume`` /
    ``on_error``), calling :meth:`~.._framework.brain._FrameworkBrain.run_inference`
    to spend the floor. Holds one ADK agent + runner and one ADK session for the
    session's lifetime. ADK's session is the source of truth for the prompt;
    :meth:`_correct` reconciles it to heard-truth in place.

    For the no-override request/response case, :func:`adk_brain` bundles the same
    constructor into a zero-arg builder. Either way the base owns ``run_inference`` /
    ``on_interaction`` / the conformance + error seams. See :func:`adk_brain` for the
    full constructor-parameter reference."""

    def __init__(
        self,
        agent_factory: Callable[[], LlmAgent],
        *,
        greeting: str | GreetingHook | None = None,
        streaming: bool = True,
        app_name: str = "voqalize",
        runner_factory: Callable[[LlmAgent], Runner] | None = None,
        answer_conformance_dump: bool = False,
        error_fallback: str | None = DEFAULT_ERROR_FALLBACK,
        turn_timeout: float | None = DEFAULT_TURN_TIMEOUT,
    ) -> None:
        super().__init__(
            name="adk_brain",
            answer_conformance_dump=answer_conformance_dump,
            error_fallback=error_fallback,
            turn_timeout=turn_timeout,
        )
        self._agent = agent_factory()
        if runner_factory is not None:
            # The client brings their own Runner — so their own session_service /
            # memory_service / artifact_service (a DatabaseSessionService, a
            # VertexAiSessionService, …) survive, instead of being silently replaced
            # by the in-memory defaults.
            self._runner = runner_factory(self._agent)
        else:
            from google.adk.runners import InMemoryRunner

            self._runner = InMemoryRunner(agent=self._agent, app_name=app_name)
        # Register the corrector plugin on the runner (either path) — a single
        # Runner-scoped registration corrects every model call in the agent tree. Done
        # after construction (not via the deprecated ``plugins=`` argument) so it holds
        # for a client-supplied runner too.
        self._runner.plugin_manager.register_plugin(_make_corrector(self._correct))
        # Track the runner's own app_name, so create_session matches a custom runner
        # configured with a different one.
        self._app_name = getattr(self._runner, "app_name", app_name)
        self._greeting = greeting
        self._streaming = streaming
        self._session_id: str | None = None
        # (interaction_id, inference_id) → the record read at finalize to write the
        # accountant event. Populated as ``_drive`` streams each model call.
        self._inferences: dict[tuple[int, int], _InferenceRecord] = {}

    # ─── heard-truth correction (before_model_callback) ────────────────────────

    async def _correct(self, callback_context: Any, llm_request: Any) -> None:
        """``before_model_callback``: reconcile ADK's own contents to heard-truth.

        ADK has already assembled ``llm_request.contents`` from its session event log
        — including every out-of-band event the customer added and the accountant
        events we wrote on barge-in. We make three minimal, in-place corrections and
        otherwise leave ADK's history untouched (so the customer's ``SessionService``
        stays the source of truth):

        1. Drop each generated model reply the user only heard a prefix of. The
           accountant event we appended at finalize carries the heard prefix as its
           own model turn, and its ``custom_metadata`` names the superseded full text
           to remove (exact match). Where ADK never persisted the reply (a mid-stream
           barge), there is nothing to drop and the accountant's heard turn stands.
        2. Filter ADK's internal control tools (the hand-off) and private thinking
           parts out of the prompt — routing bookkeeping / private reasoning, not
           conversation. (Done per-part in :func:`_keep_parts`.)

        The accountant metadata this reads lives on ``Event.custom_metadata``, which
        ADK strips out of ``llm_request.contents`` — so we re-read the session through
        the **public** ``SessionService.get_session`` (the same call
        :meth:`_write_accountant_event` makes), keyed by the ids we hold. ADK's
        ``PluginManager`` awaits this coroutine (``_run_callbacks`` does ``await
        callback(...)``), so the corrector needs no reach into ADK-private context.
        Returning ``None`` lets the (corrected) call proceed. ``callback_context`` is
        unused — ADK passes it by keyword, so it stays in the signature."""
        session = await self._current_session()
        supersessions = self._supersessions(session)
        contents = list(getattr(llm_request, "contents", None) or [])
        llm_request.contents = self._reconcile_contents(contents, supersessions)

    async def _current_session(self) -> Any:
        """The live ADK session, fetched through the **public**
        ``SessionService.get_session`` and keyed by the ids we already hold. The single
        public entry point both the corrector (to read accountant metadata ADK strips
        from ``contents``) and :meth:`_write_accountant_event` use — so the adapter
        reaches into no ADK-private context. ``None`` if the session is gone."""
        assert self._session_id is not None
        return await self._runner.session_service.get_session(
            app_name=self._app_name, user_id=self._session_id, session_id=self._session_id
        )

    @staticmethod
    def _supersessions(session: Any) -> list[_Supersession]:
        """The barged replies to drop, in session order — read from the
        ``voqalize.heard`` metadata on the session's own events. Only a *persisted*
        reply (``target_event_id`` set) the user heard *less* of than was generated is
        included; a mid-stream barge (``target_event_id`` None) was never persisted, so
        it has nothing in ``contents`` to drop and its accountant heard turn stands.
        Empty when the session is unreadable or nothing was barged."""
        out: list[_Supersession] = []
        for event in getattr(session, "events", None) or []:
            meta = getattr(event, "custom_metadata", None) or {}
            heard_meta = meta.get(HEARD_METADATA_KEY)
            if not isinstance(heard_meta, dict):
                continue
            generated = heard_meta.get("generated") or ""
            heard = heard_meta.get("heard") or ""
            target_event_id = heard_meta.get("target_event_id")
            if generated and generated != heard and target_event_id is not None:
                out.append(
                    _Supersession(generated=generated, heard=heard, target_event_id=target_event_id)
                )
        return out

    def _reconcile_contents(
        self, contents: list[Any], supersessions: list[_Supersession]
    ) -> list[Any]:
        """Apply the corrections to ADK's assembled contents: (1) filter
        internal-tool / thought / foreign-context bookkeeping per-part, (2) drop
        superseded generated replies (heard-truth)."""
        from google.genai import types

        filtered: list[Any] = []
        for content in contents:
            if _is_internal_foreign_context(content):
                # ADK's flattened 'For context: … transfer_to_agent …' turn — routing
                # bookkeeping the sub-agent must not prompt from.
                continue
            kept = _keep_parts(content)
            if not kept:
                # A pure hand-off / pure-thought content — nothing left to say.
                continue
            if len(kept) != len(getattr(content, "parts", None) or []):
                content = types.Content(role=getattr(content, "role", None), parts=kept)
            filtered.append(content)
        return self._drop_superseded(filtered, supersessions)

    @staticmethod
    def _drop_superseded(contents: list[Any], supersessions: list[_Supersession]) -> list[Any]:
        """Remove each superseded generated model turn, consuming supersessions in
        session order.

        A partial-heard barge is matched by **adjacency** — the persisted generated
        turn is immediately followed by its accountant heard-prefix turn — so an
        earlier reply with *identical text* (fully heard, not barged) is passed over
        rather than mis-dropped by a global text match. A zero-heard barge (persisted
        full reply, nothing played) has no adjacent marker, so it falls back to an
        ordered text match. Any supersession that can't be placed raises a drift
        warning: silent corruption becomes telemetry (an ADK upgrade that reorders
        ``contents`` vs ``session.events`` would surface here, not in the prompt)."""
        if not supersessions:
            return contents
        pending = list(supersessions)
        dropped: set[int] = set()
        for i, content in enumerate(contents):
            if not pending or getattr(content, "role", None) != "model":
                continue
            text = _text_of_parts(getattr(content, "parts", None) or [])
            if not text or text != pending[0].generated:
                continue
            spec = pending[0]
            if spec.heard and AdkBrain._next_model_text(contents, i) != spec.heard:
                # Same text, but the heard-prefix turn doesn't immediately follow —
                # this is an earlier, fully-heard reply, not the barged one. Skip it.
                continue
            dropped.add(i)
            pending.pop(0)
        if pending:
            logger.warning(
                "adk corrector: {} superseded repl(y/ies) not matched in the assembled "
                "prompt — possible heard-truth drift (ADK contents/session ordering "
                "changed?)",
                len(pending),
            )
        return [c for i, c in enumerate(contents) if i not in dropped]

    @staticmethod
    def _next_model_text(contents: list[Any], i: int) -> str:
        """Text of the first model turn after index ``i`` (``""`` if none) — used to
        confirm a barged reply is immediately followed by its heard-prefix turn."""
        for content in contents[i + 1 :]:
            if getattr(content, "role", None) == "model":
                return _text_of_parts(getattr(content, "parts", None) or [])
        return ""

    # ─── session lifecycle ─────────────────────────────────────────────────────

    async def on_session_start(self, session: Session, start: SessionStart) -> None:
        self._session_id = session.id
        adk_session = await self._runner.session_service.create_session(
            app_name=self._app_name, user_id=session.id, session_id=session.id
        )
        # Resume-or-greet. A resumed call seeds prior turns into ADK's *own* session
        # (so the corrector's source of truth carries them) and skips the cold
        # greeting — a resumed call is a continuation, not a first hello.
        if await self._resume(session, start, adk_session):
            return
        line = await resolve_greeting(self._greeting, session, start)
        if line:
            async with session.say() as inf:
                await inf.speak(line)

    async def _resume(self, session: Session, start: SessionStart, adk_session: Any) -> bool:
        """Run the client's resume hook (if any) and seed what it returns into both
        the SDK-core ``session.conversation`` (heard-truth spanning sockets) and ADK's
        own session (so the very first prompt already carries prior context). Returns
        whether the session was resumed."""
        messages = await self.on_resume(session, start)
        if not messages:
            return False
        session.conversation.seed(messages)
        await self._seed_adk_session(adk_session, messages)
        return True

    async def _seed_adk_session(self, adk_session: Any, messages: Sequence[Message]) -> None:
        """Append each resumed message to ADK's session as a plain content event, so
        ADK builds them into the first prompt. Only spoken text crosses the boundary —
        a prior session's tool round-trips are not replayed; the client's tools reload
        any domain state they need from their own store."""
        from google.adk.events.event import Event
        from google.genai import types

        for m in messages:
            is_user = m.role == "user"
            await self._runner.session_service.append_event(
                adk_session,
                Event(
                    invocation_id="voqalize-resume",
                    author="user" if is_user else self._agent.name,
                    content=types.Content(
                        role="user" if is_user else "model",
                        parts=[types.Part(text=m.content)],
                    ),
                ),
            )

    # ─── the driven run ────────────────────────────────────────────────────────

    async def _drive(self, interaction: Interaction, message: str | None) -> None:
        from google.adk.agents.run_config import RunConfig, StreamingMode
        from google.genai import types

        assert self._session_id is not None
        run_config = RunConfig(
            streaming_mode=StreamingMode.SSE if self._streaming else StreamingMode.NONE
        )
        # ADK's Runner always requires a new_message; on on_interaction this is the
        # user's utterance, on an idle / app-event turn it's whatever stimulus the
        # brain chose. A None message (a bare re-run over ADK's own session history)
        # sends an empty user turn — ADK has no "continue with no input" mode.
        new_message = types.Content(role="user", parts=[types.Part(text=message or "")])

        # One open bracket at a time: opened at the first event of a model call,
        # closed at that call's aggregated/complete event. Kept across loop
        # iterations because a streamed call spans many partial events. ADK persists
        # its own tool round-trips (function_call + function_response events) into the
        # session; we neither pair nor record them — the corrector reads them back
        # from ADK's session, so tool memory is native, not a parallel store.
        current: Any = None
        record: _InferenceRecord | None = None
        spoke_any = False
        # Hold the generator so a barge-in can aclose() it — otherwise ADK's
        # underlying model stream / tool tasks outlive the cancelled interaction until
        # GC. The `async for` cancels iteration; aclose() tears the generator down now.
        events = self._runner.run_async(
            user_id=self._session_id,
            session_id=self._session_id,
            new_message=new_message,
            run_config=run_config,
        )
        try:
            async for event in events:
                # Tool-result turn: ADK persists it; we only skip it here so it never
                # opens an empty (text-free) bracket on the wire.
                if event.get_function_responses():
                    continue
                # Skip the echoed user turn and content-free control events.
                if event.author == "user" or event.content is None:
                    continue

                # Thinking parts are dropped here — the model's private reasoning is
                # never spoken and never counted as this inference's generated text.
                text = spoken_text_of(event.content)
                if event.partial:
                    # A streamed chunk of the current model call.
                    if current is None:
                        current, record = await self._open(interaction, event)
                    if text:
                        await current.speak(text)
                        spoke_any = True
                    if record is not None:
                        record.generated_text += text
                    continue

                # A pure hand-off event — no speech, only the ADK-internal transfer
                # call — is routing bookkeeping, not a model turn. Skip it whole: open
                # no bracket (no empty inference on the wire). Only reached when
                # nothing streamed into an open bracket first.
                calls = event.get_function_calls()
                if (
                    current is None
                    and not text
                    and calls
                    and all(fc.name in _ADK_INTERNAL_TOOLS for fc in calls)
                ):
                    continue

                # The complete (aggregated, or non-streaming single) model event for
                # one call — the bracket's close.
                if current is None:
                    current, record = await self._open(interaction, event)
                assert record is not None
                if text and not spoke_any:
                    await current.speak(text)
                # The aggregate is authoritative for what was generated; record its
                # id so the accountant event can name the exact persisted reply.
                record.generated_text = text
                record.event_id = getattr(event, "id", None)
                await current.__aexit__(None, None, None)
                current = None
                record = None
                spoke_any = False
        finally:
            # Barge-in (CancelledError) or error mid-call. Close the open bracket
            # FIRST: its ``VqlLLMFullResponseEnd`` emit is a synchronous
            # ``emitter.send`` with no suspension point, so even a *second* barge
            # landing during teardown cannot abort it (the double-``CancelledError``
            # bug — ``CancelledError`` is a ``BaseException``, so it must not be
            # swallowed as ``Exception``, and the load-bearing close must not sit
            # behind an interruptible await). Only then tear down the ADK run
            # generator, whose ``aclose()`` *does* suspend (model/tool cleanup): shield
            # it so it completes even if a second barge cancels us, and absorb that
            # extra cancel — the original one still propagates from the try body, so
            # ``run_turn`` still skips ``VqlInteractionCompleted``.
            if current is not None:
                with contextlib.suppress(Exception):
                    await current.__aexit__(None, None, None)
            with contextlib.suppress(BaseException):
                await asyncio.shield(events.aclose())

    async def _open(self, interaction: Interaction, event: Any) -> tuple[Any, _InferenceRecord]:
        """Open one inference bracket and register its record (keyed by
        ``(interaction_id, inference_id)``, carrying ADK's ``invocation_id``)."""
        inference = interaction.say()
        await inference.__aenter__()
        record = _InferenceRecord(invocation_id=getattr(event, "invocation_id", None))
        self._inferences[(interaction.id, inference.id)] = record
        return inference, record

    async def on_inference_finalized(self, inference: Inference) -> None:
        # Only a *barged* inference that we actually drove needs correcting. A clean
        # inference's generated reply == what was heard, so ADK's own persisted event
        # is already heard-truth; the greeting and other non-driven speech have no
        # record here (they never went through ADK's Runner).
        record = self._inferences.pop((inference.interaction_id, inference.id), None)
        if record is None or not inference.interrupted:
            return
        heard = inference.heard or ""
        # Nothing was actually cut — the whole generated reply was *persisted* by ADK
        # (its aggregate arrived, so ``event_id`` is set) and the user heard all of it.
        # ADK's own model event already IS heard-truth; writing an accountant event
        # would duplicate the turn (the corrector wouldn't drop it — heard == generated
        # supersedes nothing), so skip it. ``interrupted`` can still be set on a
        # fully-played reply (a barge landing on its trailing silence). A mid-stream
        # barge is different: ADK persisted nothing (``event_id`` is None), so even when
        # the accumulated ``generated_text`` happens to equal ``heard`` the accountant
        # event must still be written — it is what *supplies* the heard turn.
        if record.event_id is not None and record.generated_text == heard:
            return
        await self._write_accountant_event(record, heard)

    async def _write_accountant_event(self, record: _InferenceRecord, heard: str) -> None:
        """Append the accountant event to ADK's session: a ``role="model"`` turn
        carrying the *heard* prefix (so a ``SessionService`` the customer resumes from
        carries the truth, and ADK replays the heard turn for free), plus
        ``custom_metadata`` naming the superseded generated reply for the corrector to
        drop. ``heard == ""`` (barged before a word played) writes a content-less
        marker — no phantom assistant turn, only the record that a reply was cut."""
        from google.adk.events.event import Event
        from google.genai import types

        session = await self._current_session()
        if session is None:
            return
        content = types.Content(role="model", parts=[types.Part(text=heard)]) if heard else None
        await self._runner.session_service.append_event(
            session,
            Event(
                invocation_id=record.invocation_id or "voqalize-heard",
                author=self._agent.name,
                content=content,
                interrupted=True,
                custom_metadata={
                    HEARD_METADATA_KEY: {
                        "invocation_id": record.invocation_id,
                        "target_event_id": record.event_id,
                        "generated": record.generated_text,
                        "heard": heard,
                        "interrupted": True,
                    }
                },
            ),
        )


# ─── entry point ──────────────────────────────────────────────────────────────


def adk_brain(
    agent_factory: Callable[[], LlmAgent],
    *,
    greeting: str | GreetingHook | None = None,
    streaming: bool = True,
    app_name: str = "voqalize",
    runner_factory: Callable[[LlmAgent], Runner] | None = None,
    answer_conformance_dump: bool = False,
    error_fallback: str | None = DEFAULT_ERROR_FALLBACK,
    turn_timeout: float | None = DEFAULT_TURN_TIMEOUT,
) -> Callable[[], Brain]:
    """Bundle a native ADK agent factory into a zero-arg :class:`AdkBrain` builder for
    the SDK to host — the no-override convenience over subclassing.

    Prefer subclassing :class:`AdkBrain` when you want to react to Voice's other
    triggers (``on_user_idle`` / ``on_client_message``) or to resume a conversation
    (``on_resume``). ``agent_factory`` is a zero-arg callable returning a fresh
    ``LlmAgent`` — the SDK calls it once per session (bind the model/tools inside, e.g.
    ``lambda: build_agent(model)``). The result is a zero-arg Brain builder that
    plugs straight into every hosting entry point (all of which accept a
    ``Callable[[], Brain]``)::

        await serve_direct(adk_brain(build_agent, greeting="Hi!"))
        # or, in your own FastAPI route:
        make = adk_brain(build_agent)
        await run_session(channel, brain=make(), session_id=sid, token=tok)

    * ``greeting`` — the opening line spoken on session start (interaction 0). Either
      a fixed string, or an ``async (session, start) -> str | None`` callable that
      computes it from the session context (e.g. a name read from ``start.init``) —
      return ``None`` to open silently. ``None`` (the default) skips the greeting.
    * ``streaming`` — drive ADK in SSE streaming mode so speech is emitted as the
      model produces it (barge-in can land mid-reply). ``False`` speaks each model
      call's text in one shot.
    * ``app_name`` — the ADK app name for the default ``InMemoryRunner`` (ignored when
      ``runner_factory`` is given — the runner's own ``app_name`` is used).
    * ``runner_factory`` — optional ``(agent) -> Runner`` to build the ADK ``Runner``
      yourself, so you keep your **own** services — a ``DatabaseSessionService`` /
      ``VertexAiSessionService``, a ``MemoryService``, an ``ArtifactService`` — instead
      of the in-memory defaults an ``InMemoryRunner`` installs. Because ADK's session
      *is* the prompt's source of truth, bringing your own ``SessionService`` gives
      you real resumability and a durable tool/thought log; the SDK registers its
      heard-truth corrector plugin on the ``Runner`` you return
      (``plugin_manager.register_plugin``), so prompting is unaffected. Defaults to
      ``InMemoryRunner(agent=agent, app_name=app_name)``.
    * ``answer_conformance_dump`` — answer the conformance harness's backchannel
      dump with the committed conversation (test/CI only; off in production).
    * ``error_fallback`` — the spoken line if a turn fails with an unrecoverable
      error (default a short apology). ``None`` disables it (raw abort — the turn
      still completes, but silently).
    * ``turn_timeout`` — watchdog (seconds) bounding one whole interaction; a run that
      hangs past it (a stalled tool or model stream) is cancelled and answered with
      ``error_fallback`` so a stuck turn can't strand the caller in silence. ``None``
      disables it. Barge-in cancels far sooner and is unaffected.

    To react to Voice's other triggers, resume a conversation, or handle client
    messages / runtime errors, subclass :class:`AdkBrain` and override
    ``on_user_idle`` / ``on_client_message`` / ``on_resume`` / ``on_error`` instead of
    calling this builder.
    """

    def _build() -> Brain:
        return AdkBrain(
            agent_factory,
            greeting=greeting,
            streaming=streaming,
            app_name=app_name,
            runner_factory=runner_factory,
            answer_conformance_dump=answer_conformance_dump,
            error_fallback=error_fallback,
            turn_timeout=turn_timeout,
        )

    return _build
