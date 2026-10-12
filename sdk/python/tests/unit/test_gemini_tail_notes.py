"""`GeminiBrain.tail_notes`: content for one request, never for the record.

What a brain appends is an act, and an act stays true. What the page shows, or a
background result that has just landed, is state: true when the request goes
and stale a turn later. The tail is how state reaches the model without being
written into the context, where it would go on asserting itself.

So the tail is rendered fresh before every request of a turn, sits just before
the latest user turn, and is never kept. The system prompt and the history in
front of it are the same bytes they would be without it, and a brain that does
not override the hook sends exactly what it sent before the hook existed.
"""

from __future__ import annotations

import gc
import time
import warnings
from typing import Any

import pytest
from google.genai import types
from loguru import logger

from tests.unit.test_gemini_turn import (
    _calls,  # pyright: ignore[reportPrivateUsage]
    _Coach,  # pyright: ignore[reportPrivateUsage]
    _drain,  # pyright: ignore[reportPrivateUsage]
    _history,  # pyright: ignore[reportPrivateUsage]
    _open,  # pyright: ignore[reportPrivateUsage]
    _requests,  # pyright: ignore[reportPrivateUsage]
    _ScriptedClient,  # pyright: ignore[reportPrivateUsage]
    _ScriptedModels,  # pyright: ignore[reportPrivateUsage]
    _text,  # pyright: ignore[reportPrivateUsage]
    _user,  # pyright: ignore[reportPrivateUsage]
)
from voqalize.sdk.gemini import (
    _RETRY_NOTE,  # pyright: ignore[reportPrivateUsage]
    TOOL_BUDGET_MS,
    GeminiBrain,
    needs_result_now,
)

Script = list[types.GenerateContentResponse]


class _Prompted(_ScriptedModels):
    """The scripted model, also keeping the system prompt each request carried."""

    def __init__(self, script: Script) -> None:
        super().__init__(script)
        self.prompts: list[Any] = []

    async def generate_content_stream(self, *, model: str, contents: Any, config: Any) -> Any:
        self.prompts.append(config.system_instruction)
        return await super().generate_content_stream(model=model, contents=contents, config=config)


class _Client:
    def __init__(self, script: Script) -> None:
        self.aio = self
        self.models = _Prompted(script)


class _Paged(_Coach):
    """A coach that knows which page the user is on, and says so per request."""

    def __init__(self, client: Any) -> None:
        super().__init__(client)
        self.page: str | None = "glucose"
        self.rendered = 0

    def tail_notes(self) -> list[types.Content]:
        self.rendered += 1
        if self.page is None:
            return []
        return [_user(f"[Page now] {self.page}")]

    @needs_result_now
    async def lookup(self) -> int:
        """Read a number the model needs to answer — and move the page while at it."""
        self.ran.append("lookup")
        self.page = "meals"
        return 42


def _texts(contents: list[types.Content]) -> list[str]:
    """Each content as ``role: what-is-in-it``, as `_history` reads the record."""
    out = []
    for content in contents:
        bits = []
        for part in content.parts or []:
            if part.text:
                bits.append(part.text)
            if part.function_call:
                bits.append(f"call:{part.function_call.name}")
            if part.function_response:
                bits.append(f"resp:{part.function_response.name}")
        out.append(f"{content.role}: {'|'.join(bits)}")
    return out


def _dump(requests: list[list[types.Content]]) -> list[list[dict[str, Any]]]:
    return [[c.model_dump(mode="json") for c in request] for request in requests]


def _without_tail(contents: list[types.Content]) -> list[str]:
    return [line for line in _texts(contents) if "[Page now]" not in line]


def _malformed() -> types.GenerateContentResponse:
    return types.GenerateContentResponse.model_validate(
        {
            "candidates": [
                {
                    "content": {"role": "model", "parts": []},
                    "finishReason": "MALFORMED_FUNCTION_CALL",
                }
            ]
        }
    )


# ─── Where it goes ────────────────────────────────────────────────────────────


async def test_the_tail_sits_just_before_the_user_turn() -> None:
    brain, _, session = await _open(_Paged(_ScriptedClient(_text("Sure."))))
    brain.append_to_context(_user("earlier note"))
    brain._history.append(types.Content(role="model", parts=[types.Part(text="Noted.")]))  # pyright: ignore[reportPrivateUsage]

    await _drain(brain, session)

    assert _texts(_requests(brain)[0]) == [
        "user: earlier note",
        "model: Noted.",
        "user: [Page now] glucose",
        "user: hello",
    ]


async def test_several_tail_contents_keep_their_order() -> None:
    class _Two(_Paged):
        def tail_notes(self) -> list[types.Content]:
            return [_user("[Page now] meals"), _user("[Page before] glucose")]

    brain, _, session = await _open(_Two(_ScriptedClient(_text("Sure."))))

    await _drain(brain, session)

    assert _texts(_requests(brain)[0]) == [
        "user: [Page now] meals",
        "user: [Page before] glucose",
        "user: hello",
    ]


async def test_an_appended_note_is_the_latest_user_turn() -> None:
    """A turn opened by the brain itself — an idle turn after a note naming what
    landed — has no words of the user's: the note is the turn, and the tail
    goes in front of it."""
    brain, _, session = await _open(_Paged(_ScriptedClient(_text("It finished."))))
    brain.append_to_context(_user("The search for 'insulin pens' finished."))

    async for _ in brain.respond(session):
        pass

    assert _texts(_requests(brain)[0]) == [
        "user: [Page now] glucose",
        "user: The search for 'insulin pens' finished.",
    ]


async def test_on_a_follow_up_the_tail_stays_before_the_users_words_and_is_rendered_again() -> None:
    """A marked tool asks again at once. The tail does not split the call from
    its answer, and it is rendered for that request too, so a value a tool
    moved mid-turn reaches the follow-up as it is now."""
    brain, _, session = await _open(_Paged(_ScriptedClient(_calls("lookup") + _text("It's 42."))))

    await _drain(brain, session)

    first, follow_up = _requests(brain)
    assert _texts(first) == ["user: [Page now] glucose", "user: hello"]
    assert _texts(follow_up) == [
        "user: [Page now] meals",
        "user: hello",
        "model: call:lookup",
        "user: resp:lookup",
    ]
    assert brain.rendered == 2


async def test_the_retry_carries_the_tail_and_the_note_goes_last() -> None:
    brain, _, session = await _open(_Paged(_ScriptedClient([_malformed(), *_text("Sure.")])))

    await _drain(brain, session)

    first, retry = _requests(brain)
    assert _texts(first) == ["user: [Page now] glucose", "user: hello"]
    assert _texts(retry)[:2] == ["user: [Page now] glucose", "user: hello"]
    assert retry[-1] == _RETRY_NOTE


async def test_with_no_user_turn_the_tail_goes_at_the_end() -> None:
    brain, _, session = await _open(_Paged(_ScriptedClient(_text("Welcome back."))))

    async for _ in brain.respond(session):
        pass

    assert _texts(_requests(brain)[0]) == ["user: [Page now] glucose"]


async def test_a_turn_the_brain_opens_after_an_answered_exchange_puts_the_tail_last() -> None:
    """``respond`` with nothing appended: the latest user turn belongs to an
    exchange already answered, so the tail goes after it, not in front of it."""
    brain, _, session = await _open(_Paged(_ScriptedClient(_text("Sure.") + _text("Still here."))))
    await _drain(brain, session)

    async for _ in brain.respond(session):
        pass

    assert _texts(_requests(brain)[1]) == [
        "user: hello",
        "model: Sure.",
        "user: [Page now] glucose",
    ]


async def test_on_a_turn_the_brain_opens_a_follow_up_keeps_the_tail_where_the_turn_began() -> None:
    script = _text("Sure.") + _calls("lookup") + _text("It's 42.")
    brain, _, session = await _open(_Paged(_ScriptedClient(script)))
    await _drain(brain, session)

    async for _ in brain.respond(session):
        pass

    first, follow_up = _requests(brain)[1:]
    assert _texts(first) == ["user: hello", "model: Sure.", "user: [Page now] glucose"]
    assert _texts(follow_up) == [
        "user: hello",
        "model: Sure.",
        "user: [Page now] meals",
        "model: call:lookup",
        "user: resp:lookup",
    ]


async def test_an_empty_user_content_still_counts_as_the_latest_user_turn() -> None:
    brain, _, session = await _open(_Paged(_ScriptedClient(_text("Sure."))))
    brain.append_to_context(_user("earlier note"))
    brain.append_to_context(types.Content(role="user", parts=[]))

    async for _ in brain.respond(session):
        pass

    assert _texts(_requests(brain)[0]) == [
        "user: earlier note",
        "user: [Page now] glucose",
        "user: ",
    ]


# ─── For this request only ────────────────────────────────────────────────────


async def test_the_tail_is_never_kept_and_the_next_request_has_only_its_own() -> None:
    brain, _, session = await _open(_Paged(_ScriptedClient(_text("Sure.") + _text("Okay."))))

    await _drain(brain, session)
    assert _history(brain) == ["user: hello", "model: Sure."]

    brain.page = "meals"
    await _drain(brain, session)

    second = _requests(brain)[1]
    assert [line for line in _texts(second) if "[Page now]" in line] == ["user: [Page now] meals"]
    assert _texts(second)[-2:] == ["user: [Page now] meals", "user: hello"]
    assert not any("[Page now]" in line for line in _history(brain))


async def test_a_tail_that_goes_empty_leaves_the_next_request_without_one() -> None:
    brain, _, session = await _open(_Paged(_ScriptedClient(_text("Sure.") + _text("Okay."))))

    await _drain(brain, session)
    brain.page = None
    await _drain(brain, session)

    assert _texts(_requests(brain)[1]) == [
        "user: hello",
        "model: Sure.",
        "user: hello",
    ]


async def test_strip_the_tail_and_the_request_is_the_history() -> None:
    """Every request is the record plus the tail and nothing else, and the
    system prompt is the same bytes on every one: the cached prefix holds."""
    client = _Client(_calls("lookup") + _text("It's 42.") + _text("Okay."))
    brain, _, session = await _open(_Paged(client))

    await _drain(brain, session)
    await _drain(brain, session)

    requests = _requests(brain)
    assert len(requests) == 3
    assert _without_tail(requests[-1]) == _history(brain)[:-1]
    assert _without_tail(requests[1]) == _history(brain)[:3]
    assert client.models.prompts == ["be brief"] * 3
    assert brain.system_instruction == "be brief"


# ─── A brain that does not override it ────────────────────────────────────────


def test_the_default_tail_is_empty() -> None:
    assert _Coach.tail_notes is GeminiBrain.tail_notes
    assert GeminiBrain.tail_notes(object()) == []  # pyright: ignore[reportArgumentType]


async def test_without_a_tail_the_requests_are_the_ones_sent_before_the_hook() -> None:
    """The hook is additive: a brain that leaves it alone sends byte-identical
    requests to a brain whose hook renders nothing, and each one is its record
    at the moment it was sent."""

    def script() -> Script:
        return _calls("ping", "lookup") + _text("It's 42.") + [_malformed(), *_text("Okay.")]

    class _Silent(_Coach):
        def tail_notes(self) -> list[types.Content]:
            return []

    lines: list[str] = []
    sink = logger.add(lines.append, level="WARNING", format="{message}")
    try:
        sent = []
        for cls in (_Coach, _Silent):
            brain, _, session = await _open(cls(_ScriptedClient(script())))
            brain.append_to_context(_user("the caller is on the meals tab"))
            await _drain(brain, session)
            await _drain(brain, session)
            sent.append(_dump(_requests(brain)))
    finally:
        logger.remove(sink)

    default, silent = sent
    assert default == silent
    assert len(default) == 4
    assert [len(r) for r in default] == [2, 4, 6, 7]
    assert default[-1][-1] == _RETRY_NOTE.model_dump(mode="json")
    assert not any("tail_notes" in line for line in lines)


# ─── A bad hook never kills the turn ──────────────────────────────────────────


async def _logged(brain: GeminiBrain) -> tuple[list[str], list[str]]:
    """Drive one turn; return the first request and every warning logged."""
    lines: list[str] = []
    sink = logger.add(lines.append, level="WARNING", format="{message}")
    try:
        brain, _, session = await _open(brain)
        await _drain(brain, session)  # pyright: ignore[reportArgumentType]
    finally:
        logger.remove(sink)
    return _texts(_requests(brain)[0]), lines


async def test_a_hook_that_raises_sends_the_request_without_a_tail() -> None:
    class _Broken(_Coach):
        def tail_notes(self) -> list[types.Content]:
            raise RuntimeError("no page yet")

    sent, lines = await _logged(_Broken(_ScriptedClient(_text("Sure."))))

    assert sent == ["user: hello"]
    assert any("tail_notes failed" in line for line in lines)


async def test_a_hook_that_writes_the_models_side_sends_no_tail() -> None:
    class _Ventriloquist(_Coach):
        def tail_notes(self) -> list[types.Content]:
            return [
                _user("[Page now] glucose"),
                types.Content(role="model", parts=[types.Part(text="I can see it.")]),
            ]

    sent, lines = await _logged(_Ventriloquist(_ScriptedClient(_text("Sure."))))

    assert sent == ["user: hello"]
    assert any("tail content must be user content" in line for line in lines)


async def test_a_slow_hook_is_logged_against_the_tool_budget_and_still_sent() -> None:
    class _Slow(_Coach):
        def tail_notes(self) -> list[types.Content]:
            # Blocking on purpose: the hook is synchronous, and this is the cost.
            time.sleep(TOOL_BUDGET_MS * 2 / 1000)
            return [_user("[Page now] glucose")]

    sent, lines = await _logged(_Slow(_ScriptedClient(_text("Sure."))))

    assert sent == ["user: [Page now] glucose", "user: hello"]
    slow = [line for line in lines if "over the" in line]
    assert len(slow) == 1 and slow[0].startswith("tail_notes _Slow took ")
    assert TOOL_BUDGET_MS == 20


async def test_a_fast_hook_is_not_logged() -> None:
    _, lines = await _logged(_Paged(_ScriptedClient(_text("Sure."))))
    assert lines == []


@pytest.mark.parametrize(
    ("bad", "why"),
    [
        (types.Content(role="user", parts=[]), "content with no parts"),
        (types.Content(role="user"), "content with no parts"),
        (
            types.Content(
                role="user",
                parts=[types.Part(function_response=types.FunctionResponse(name="x", response={}))],
            ),
            "a function call or response",
        ),
        (
            types.Content(
                role="user", parts=[types.Part(function_call=types.FunctionCall(name="x"))]
            ),
            "a function call or response",
        ),
        (types.Content(parts=[types.Part(text="[Page now] glucose")]), "built with role='user'"),
    ],
    ids=["no-parts", "parts-none", "function-response", "function-call", "no-role"],
)
async def test_tail_content_that_is_not_a_plain_note_sends_no_tail(
    bad: types.Content, why: str
) -> None:
    class _Odd(_Coach):
        def tail_notes(self) -> list[types.Content]:
            return [_user("[Page now] glucose"), bad]

    sent, lines = await _logged(_Odd(_ScriptedClient(_text("Sure."))))

    assert sent == ["user: hello"]
    assert any(why in line and "goes without a tail" in line for line in lines), lines


async def test_an_async_hook_is_named_in_one_line_and_never_left_unawaited() -> None:
    class _Async(_Coach):
        async def tail_notes(self) -> list[types.Content]:  # type: ignore[override]  # pyright: ignore[reportIncompatibleMethodOverride]
            return [_user("[Page now] glucose")]

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        sent, lines = await _logged(_Async(_ScriptedClient(_text("Sure."))))
        gc.collect()

    assert sent == ["user: hello"]
    assert [line.strip() for line in lines if "tail_notes" in line] == [
        "tail_notes _Async is async; it must be a plain def that returns a list, "
        "so this request goes without a tail"
    ]
    assert not [w for w in caught if issubclass(w.category, RuntimeWarning)]
