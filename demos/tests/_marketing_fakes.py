"""Tanvi (demos/marketing) test fakes: a session that records what Tanvi puts on screen, and a Gemini stream
scripted chunk by chunk, so the brain's own code runs with no network and no model."""

from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest
from google import genai
from google.genai import types
from voqalize_demos.discovery import discover

discover()

from voqalize_demos._loaded.marketing.brain import TanviBrain  # noqa: E402


class FakeSession:
    """Collects every action Tanvi dispatches."""

    def __init__(self) -> None:
        self.actions: list[Any] = []

    def dispatch(self, action: Any) -> None:
        self.actions.append(action)


def call(name: str, **args: Any) -> types.GenerateContentResponse:
    """One streamed chunk holding a single function call, finished."""
    part = types.Part(function_call=types.FunctionCall(name=name, args=args))
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=[part]),
                finish_reason=types.FinishReason.STOP,
            )
        ]
    )


def text(words: str, *, done: bool = True) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=[types.Part(text=words)]),
                finish_reason=types.FinishReason.STOP if done else None,
            )
        ]
    )


class ScriptedModels:
    """Answers each request with the next scripted list of chunks."""

    def __init__(self, *responses: list[types.GenerateContentResponse]) -> None:
        self.responses = list(responses)
        self.requests = 0

    async def generate_content_stream(
        self, **kw: Any
    ) -> AsyncIterator[types.GenerateContentResponse]:
        # Gemini's own rule: "Requests ending with a model turn are not supported."
        contents = kw["contents"]
        assert contents and contents[-1].role == "user", "a request ended on the model's turn"
        chunks = self.responses[self.requests]
        self.requests += 1

        async def stream() -> AsyncIterator[types.GenerateContentResponse]:
            for c in chunks:
                yield c

        return stream()


@pytest.fixture(name="session")
def session_fixture() -> FakeSession:
    return FakeSession()


@pytest.fixture(name="brain")
def brain_fixture(session: FakeSession) -> TanviBrain:
    b = TanviBrain(client=genai.Client(api_key="test"))
    b._session = session  # type: ignore[assignment]  # pyright: ignore[reportPrivateUsage]
    return b


def script(brain: TanviBrain, *responses: list[types.GenerateContentResponse]) -> ScriptedModels:
    models = ScriptedModels(*responses)
    brain._client = SimpleNamespace(aio=SimpleNamespace(models=models))  # type: ignore[assignment]  # pyright: ignore[reportPrivateUsage]
    return models
