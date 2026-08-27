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
import inspect
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal

from google.genai import interactions as gi
from google.genai import types
from pydantic import BaseModel, Field

from voqalize.sdk import Brain, Session
from voqalize.sdk.brain import _adapter_for
from voqalize.sdk.events import Chunk, Speech, SpeechEnd, SpeechStart
from voqalize.sdk.gemini import GeminiBrain
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

    async def ping(self) -> str:
        """Say hello to nothing in particular."""
        self.ran.append("ping")
        self.seen = self.session
        return "pong"

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
        elif isinstance(ev, Chunk):
            out.append(ev.text)
    return out


# ─── Engine: automatic function calling ───────────────────────────────────────


class _AfcModels:
    """Stands in for ``client.aio.models``, including AFC's tool execution and
    the record it keeps of it — which is the only place a tool's answer exists."""

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
        table = {fn.__name__: fn for fn in (config.tools or [])}
        budget = getattr(config.automatic_function_calling, "maximum_remote_calls", 6) or 6
        hops = list(self._hops)

        async def gen() -> Any:
            record = list(contents)
            seen = list(record)
            spent = 0
            while hops:
                hop = hops.pop(0)
                parts = _afc_parts(hop)
                responses: list[types.Part] = []
                for part in parts:
                    if not (part.function_call and part.function_call.name):
                        continue
                    if spent >= budget:
                        return
                    spent += 1
                    fn = table[part.function_call.name]
                    try:
                        result = await fn(**_coerce(fn, part.function_call.args or {}))
                    except Exception as exc:  # what google-genai does with a raising tool
                        response: dict[str, Any] = {"error": str(exc)}
                    else:
                        response = {"result": result}
                    responses.append(
                        types.Part.from_function_response(
                            name=part.function_call.name, response=response
                        )
                    )
                for part in parts:
                    yield _afc_chunk([part], seen)
                yield _afc_chunk([], seen, finish=True)
                if not responses:
                    return
                record.append(types.Content(role="model", parts=parts))
                record.append(types.Content(role="user", parts=responses))
                seen = list(record)

        return gen()


def _afc_parts(hop: Hop) -> list[types.Part]:
    out: list[types.Part] = []
    for item in hop:
        if isinstance(item, Say):
            out.extend(types.Part(text=c) for c in item.chunks)
        else:
            out.append(
                types.Part(
                    function_call=types.FunctionCall(name=item.name, args=dict(item.arguments))
                )
            )
    return out


def _afc_chunk(
    parts: list[types.Part], record: list[types.Content], *, finish: bool = False
) -> types.GenerateContentResponse:
    chunk = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=parts),
                finish_reason=types.FinishReason.STOP if finish else None,
            )
        ]
    )
    return chunk.model_copy(update={"automatic_function_calling_history": list(record)})


def _coerce(fn: Any, args: dict[str, Any]) -> dict[str, Any]:
    """Read off `inspect.signature`, which is where AFC reads it."""
    params = inspect.signature(fn).parameters
    return {
        k: params[k].annotation(**v)
        if k in params and isinstance(v, dict) and issubclass(params[k].annotation, BaseModel)
        else v
        for k, v in args.items()
    }


class _AfcClient:
    def __init__(self, hops: list[Hop]) -> None:
        self.aio = self
        self.models = _AfcModels(hops)


class AfcCoach(Tools, GeminiBrain):
    pass


class AfcEngine(Engine):
    id = "afc"

    def brain(self, *hops: Hop, **kwargs: Any) -> AfcCoach:
        return AfcCoach(client=_AfcClient(list(hops)), system_instruction="be brief", **kwargs)

    @property
    def coach(self) -> type[Any]:
        return AfcCoach

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
        # AFC runs the whole turn inside one call, so a hop is not a request.
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


ENGINES: list[Engine] = [AfcEngine(), InteractionsEngine()]
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
