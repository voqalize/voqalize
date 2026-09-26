"""One brain, two engines: the harness the contract suite runs on both.

A brain is glue. On one side is the wire, which is ours and fixed; on the other
is somebody's agentic framework, which is theirs and different every time. What
sits between them has a job — mint units of speech the runtime can interrupt,
commit only what the caller heard, answer every tool call it made — and that job
does not change with the framework. This module is the seam that lets one suite
put every adapter through the same job.

An engine supplies three things and hides everything else:

  * a **base class**, so the same three tools can be mixed onto either brain;
  * a **scripted client**, which replays hops written in the neutral vocabulary
    below and records what the brain asked for;
  * **accessors**, which read the context, the declarations and the speech
    queue back out in terms that are ours rather than the provider's.

Nothing above the seam names a provider type. That is the test of the design as
much as of the code: an invariant that cannot be stated without saying
``types.Content`` or ``gi.Step`` is not part of the contract, and belongs in the
engine's own suite next door.
"""

from __future__ import annotations

import abc
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal

from google.genai import interactions as gi
from google.genai import types
from pydantic import BaseModel, Field

from voqalize.sdk import Brain, Session
from voqalize.sdk.brain import _adapter_for
from voqalize.sdk.events import Speech, SpeechChunk, SpeechEnd, SpeechStart
from voqalize.sdk.gemini import GeminiBrain, needs_result_now
from voqalize.sdk.gemini_interactions import GeminiInteractionsBrain
from voqalize.sdk.wire import Frame, SessionStartFrame

# ─── What a hop is, in neither provider's words ───────────────────────────────


@dataclass(frozen=True)
class Say:
    """A hop that speaks. Each string is its own chunk, as a stream delivers it."""

    chunks: tuple[str, ...]


@dataclass(frozen=True)
class Call:
    """A hop's tool call. Several in one hop are the parallel case."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


Hop = list[Say | Call]


def says(*chunks: str) -> Hop:
    return [Say(chunks)]


def calls(*wanted: Call) -> Hop:
    return list(wanted)


# ─── The three tools, on either base ──────────────────────────────────────────


class _Section(BaseModel):
    """Which part of the screen to show."""

    name: Literal["glucose", "meals"] = Field(description="Section to show.")


class Tools:
    """Mixed in front of a brain base, so both engines run the same tools.

    `show` takes a declared model, `ping` takes nothing and reads the ambient
    session, `boom` raises. Between them they cover every way a tool can behave
    that the contract has something to say about.

    `ping` and `boom` are marked :func:`needs_result_now`, so a script can go
    round a tool on every engine; `show` is not, because a screen dispatch is
    the tool a model should speak over. An engine that waits on every result
    ignores the mark.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.ran: list[str] = []
        self.seen: Session | None = None
        self.read_tools = 0

    @property
    def tools(self) -> list[Any]:
        self.read_tools += 1
        return [self.show, self.ping, self.boom]

    async def show(self, args: _Section) -> str:
        """Put a section of the screen in front of the caller."""
        self.ran.append(f"show:{args.name}")
        return "shown"

    @needs_result_now
    async def ping(self) -> str:
        """Say hello to nothing in particular."""
        self.ran.append("ping")
        self.seen = self.session
        return "pong"

    @needs_result_now
    async def boom(self) -> str:
        """Fail."""
        raise ValueError("kaboom")


class Wire:
    """An emitter that keeps what the brain put on the wire."""

    def __init__(self) -> None:
        self.frames: list[Frame] = []

    def send(self, frame: Frame) -> None:
        self.frames.append(frame)


# ─── The seam ─────────────────────────────────────────────────────────────────


class Engine(abc.ABC):
    """One provider's brain, reduced to what the contract can say about it."""

    id: str

    @abc.abstractmethod
    def brain(self, *hops: Hop, **kwargs: Any) -> Any:
        """A brain with the three tools, scripted to reply with `hops` in order."""

    @property
    @abc.abstractmethod
    def coach(self) -> type[Any]:
        """The class :meth:`brain` builds, to subclass when a test needs a variant."""

    @abc.abstractmethod
    def context(self, brain: Any) -> list[str]:
        """The conversation as ``kind: what-is-in-it``, one line per entry."""

    @abc.abstractmethod
    def declared(self, brain: Any) -> list[list[str]]:
        """The tool names sent to the provider, per request."""

    @abc.abstractmethod
    def declare(self, brain: Any) -> dict[str, str]:
        """Each tool as the provider will read it: name to description.

        The method *is* the declaration on both engines, so this is where that
        claim is checked — and where a tool that cannot be declared raises.
        """

    @abc.abstractmethod
    def requests(self, brain: Any) -> int:
        """How many times the provider was asked to generate."""

    @abc.abstractmethod
    def sent_text(self, brain: Any) -> list[list[str]]:
        """Each request's plain text, in order, so one request can be compared
        against the next."""

    @abc.abstractmethod
    def speak(self, brain: Any, text: str) -> None:
        """Add one delivered unit of speech and queue the finalize it is owed.

        What `respond` does while streaming, done by hand — the heard-truth rules
        are about reconciliation, and a model call would only be scenery.
        """

    @abc.abstractmethod
    def silent_call(self, brain: Any, name: str) -> None:
        """Add a hop that called a tool and said nothing, queueing no finalize."""


async def open_call[B: Brain](engine: Engine, brain: B) -> tuple[B, Wire, Session]:
    wire = Wire()
    adapter = _adapter_for(brain, wire)
    await adapter.handle_frame(SessionStartFrame(turn_id=1, session_id="s"))
    session = adapter._session  # pyright: ignore[reportPrivateUsage]
    assert session is not None
    brain._adapter = adapter  # pyright: ignore[reportAttributeAccessIssue]
    return brain, wire, session


def shape(events: list[Speech]) -> list[str]:
    """A turn's speech as ``[`` chunk… ``]``, which is what a unit looks like."""
    out: list[str] = []
    for ev in events:
        if isinstance(ev, SpeechStart):
            out.append("[")
        elif isinstance(ev, SpeechEnd):
            out.append("]")
        elif isinstance(ev, SpeechChunk):
            out.append(ev.text)
    return out


# ─── Engine: GeminiBrain's own loop ───────────────────────────────────────────


class _GeminiModels:
    """Stands in for ``client.aio.models``: one scripted hop per request.

    It runs no tools. With automatic function calling off, running them is the
    brain's job, and a fake that did it too would hide a brain that didn't.
    """

    def __init__(self, hops: list[Hop]) -> None:
        self._hops = list(hops)
        self.configs: list[Any] = []
        self.sent: list[list[types.Content]] = []

    async def generate_content_stream(self, *, model: str, contents: Any, config: Any) -> Any:
        self.sent.append(list(contents))
        self.configs.append(config)
        # google-genai deep-copies the config, so this does too: it is the step
        # that would clone a brain handed over as a bound method.
        config = config.model_copy(deep=True)
        if config.tools:
            assert config.automatic_function_calling.disable, "AFC must be off"
        hop = self._hops.pop(0) if self._hops else says("")
        mode = config.tool_config and config.tool_config.function_calling_config
        if mode and mode.mode == types.FunctionCallingConfigMode.NONE:
            # What the model does when it may not call: it answers instead.
            hop = [item for item in hop if isinstance(item, Say)]

        async def gen() -> Any:
            parts = _gemini_parts(hop)
            for part in parts:
                yield _gemini_chunk([part])
            yield _gemini_chunk([], finish=True)

        return gen()


def _gemini_parts(hop: Hop) -> list[types.Part]:
    out: list[types.Part] = []
    for i, item in enumerate(hop):
        if isinstance(item, Say):
            out.extend(types.Part(text=c) for c in item.chunks if c)
        else:
            out.append(
                types.Part(
                    function_call=types.FunctionCall(
                        id=f"call_{i}_{item.name}", name=item.name, args=dict(item.arguments)
                    )
                )
            )
    return out


def _gemini_chunk(
    parts: list[types.Part], *, finish: bool = False
) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=parts),
                finish_reason=types.FinishReason.STOP if finish else None,
            )
        ]
    )


class _GeminiClient:
    def __init__(self, hops: list[Hop]) -> None:
        self.aio = self
        self.models = _GeminiModels(hops)


class GeminiCoach(Tools, GeminiBrain):
    pass


class GeminiEngine(Engine):
    id = "gemini"

    def brain(self, *hops: Hop, **kwargs: Any) -> GeminiCoach:
        return GeminiCoach(
            client=_GeminiClient(list(hops)), system_instruction="be brief", **kwargs
        )

    @property
    def coach(self) -> type[Any]:
        return GeminiCoach

    def context(self, brain: Any) -> list[str]:
        out: list[str] = []
        for content in brain._history:
            kind = "user" if content.role == "user" else "model"
            if not content.parts:
                # An entry emptied by reconciliation and not removed. It renders
                # rather than vanishing: a turn the model believes it took and
                # said nothing in is exactly the state the contract forbids.
                out.append(f"{kind}: ")
            for part in content.parts or []:
                if part.text:
                    out.append(f"{kind}: {part.text}")
                elif part.function_call:
                    args = json.dumps(part.function_call.args or {}, sort_keys=True)
                    out.append(f"call: {part.function_call.name}{args}")
                elif part.function_response:
                    body = part.function_response.response or {}
                    got = body.get("error", body.get("result"))
                    out.append(f"result: {part.function_response.name} -> {got}")
        return out

    def declared(self, brain: Any) -> list[list[str]]:
        return [[fn.__name__ for fn in (c.tools or [])] for c in brain._client.models.configs]

    def declare(self, brain: Any) -> dict[str, str]:
        return {fn.__name__: (fn.__doc__ or "").strip() for fn in brain._turn_config().tools or []}

    def requests(self, brain: Any) -> int:
        return len(brain._client.models.configs)

    def sent_text(self, brain: Any) -> list[list[str]]:
        return [
            [p.text for c in sent for p in (c.parts or []) if p.text]
            for sent in brain._client.models.sent
        ]

    def speak(self, brain: Any, text: str) -> None:
        unit = brain._open_unit()
        brain._extend_unit(unit, types.Part(text=text))
        brain._awaiting.append(unit)

    def silent_call(self, brain: Any, name: str) -> None:
        unit = brain._open_unit()
        brain._extend_unit(unit, types.Part(function_call=types.FunctionCall(name=name, args={})))


# ─── Engine: the interactions API ─────────────────────────────────────────────


@dataclass
class _Scripted:
    """One step as the stream delivers it: a skeleton, then its deltas."""

    step: gi.Step
    deltas: list[Any] = field(default_factory=list)


def _steps(hop: Hop) -> list[_Scripted]:
    out: list[_Scripted] = []
    for item in hop:
        if isinstance(item, Say):
            out.append(_Scripted(gi.ModelOutputStep(), [gi.TextDelta(text=c) for c in item.chunks]))
        else:
            # The skeleton really is argument-less on the wire and the JSON really
            # is fragmented mid-token; delivering it whole would let a brain that
            # read `step.start.arguments` pass.
            payload = json.dumps(item.arguments)
            cut = len(payload) // 2
            out.append(
                _Scripted(
                    gi.FunctionCallStep(id=f"call_{item.name}", name=item.name, arguments={}),
                    [
                        gi.ArgumentsDelta(arguments=payload[:cut]),
                        gi.ArgumentsDelta(arguments=payload[cut:]),
                    ],
                )
            )
    return out


async def _events(hop: Hop) -> AsyncIterator[gi.InteractionSSEEvent]:
    resource = gi.InteractionSseEventInteraction(id="int_1", status="completed")
    yield gi.InteractionCreatedEvent(interaction=resource)
    for index, scripted in enumerate(_steps(hop)):
        yield gi.StepStart(index=index, step=scripted.step)
        for delta in scripted.deltas:
            yield gi.StepDelta(index=index, delta=delta)
        yield gi.StepStop(index=index)
    # No steps on it: a streamed lifecycle payload omits what only a
    # non-streaming Interaction carries.
    yield gi.InteractionCompletedEvent(interaction=resource)


class _ScriptedInteractions:
    def __init__(self, hops: list[Hop]) -> None:
        self._hops = list(hops)
        self.requests: list[dict[str, Any]] = []

    async def create(self, **request: Any) -> AsyncIterator[gi.InteractionSSEEvent]:
        self.requests.append(request)
        return _events(self._hops.pop(0) if self._hops else [])


class _InteractionsClient:
    def __init__(self, hops: list[Hop]) -> None:
        self.aio = self
        self.interactions = _ScriptedInteractions(hops)


class InteractionsCoach(Tools, GeminiInteractionsBrain):
    pass


class InteractionsEngine(Engine):
    id = "interactions"

    def brain(self, *hops: Hop, **kwargs: Any) -> InteractionsCoach:
        return InteractionsCoach(
            client=_InteractionsClient(list(hops)), system_instruction="be brief", **kwargs
        )

    @property
    def coach(self) -> type[Any]:
        return InteractionsCoach

    def context(self, brain: Any) -> list[str]:
        return [_one(step) for step in brain._history]

    def declared(self, brain: Any) -> list[list[str]]:
        return [
            [fn.name for fn in r.get("tools", [])] for r in brain._client.aio.interactions.requests
        ]

    def declare(self, brain: Any) -> dict[str, str]:
        from voqalize.sdk.gemini_interactions import _declare

        return {f.name: f.description or "" for f in [_declare(fn) for fn in brain.tools]}

    def requests(self, brain: Any) -> int:
        return len(brain._client.aio.interactions.requests)

    def sent_text(self, brain: Any) -> list[list[str]]:
        return [
            [
                c.text
                for s in r["input"]
                if isinstance(s, gi.UserInputStep | gi.ModelOutputStep)
                for c in (s.content or [])
                if isinstance(c, gi.TextContent)
            ]
            for r in brain._client.aio.interactions.requests
        ]

    def speak(self, brain: Any, text: str) -> None:
        step = gi.ModelOutputStep(content=[gi.TextContent(text=text)])
        brain._history.append(step)
        brain._awaiting.append(step)

    def silent_call(self, brain: Any, name: str) -> None:
        brain._history.append(gi.FunctionCallStep(id=f"call_{name}", name=name, arguments={}))


def _one(step: gi.Step) -> str:
    if isinstance(step, gi.UserInputStep | gi.ModelOutputStep):
        kind = "user" if isinstance(step, gi.UserInputStep) else "model"
        said = "".join(c.text for c in (step.content or []) if isinstance(c, gi.TextContent))
        return f"{kind}: {said}"
    if isinstance(step, gi.FunctionCallStep):
        return f"call: {step.name}{json.dumps(step.arguments, sort_keys=True)}"
    if isinstance(step, gi.FunctionResultStep):
        return f"result: {step.name} -> {step.result}"
    if isinstance(step, gi.ThoughtStep):
        return f"thought: {step.signature}"
    return type(step).__name__


ENGINES: list[Engine] = [GeminiEngine(), InteractionsEngine()]
IDS: list[str] = [e.id for e in ENGINES]

__all__ = [
    "ENGINES",
    "IDS",
    "Call",
    "Engine",
    "Hop",
    "Say",
    "Tools",
    "Wire",
    "calls",
    "open_call",
    "says",
    "shape",
]
