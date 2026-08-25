"""Every demo, one check: the voice and the language reach the wire as a pair.

The per-demo e2e files each drive their own demo's conversation. This one is the
sweep — it opens a session against **all eleven** demos and asserts only the thing
that has broken repeatedly and that nothing else can see:

* both halves of the language landed (TTS ``language`` *and* STT ``language_hint``),
  agreeing, before the greeting audio;
* every value is one vql-speech actually serves;
* and where the *page* settles the language instead — it knows the caller's
  choice before the call exists, so it rides the connect request — that the brain
  configured nothing, so one layer owns the answer rather than two.

A brain says it by calling ``session.configure`` from ``on_session_start``, which
runs before the greeting. It used to be a pair of class attributes the SDK
applied for you; those are gone, and the nine demos still on the pre-v3 callback
signature cannot make the call yet. Their rows below are ``unported`` — the pair
they owe, written down, and **strictly** xfailed, so porting one turns green into
a loud XPASS that makes you move the row rather than letting it pass unnoticed.

Why this needs its own file rather than a line in each demo's tests: the failures
it catches are **silent**. A demo speaking Devanagari through the English
reference clip transcribes perfectly — the words are right and only the speaker is
wrong — so WER, logs, and every automated score stay green while the caller hears
a foreign accent. And a value naming an engine that was deleted a release ago is
not a soft failure at all: it is an HTTP 403 at connect. Both have shipped to
production, from three different owners of one field. This file is the guard for
the rule that replaced them: one layer owns a demo's language, named here, and it
is checked for every demo at once, so a new demo cannot quietly opt out.

Run: ``cd demos && uv run pytest tests/test_demo_voice_contract.py``
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pytest
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini

from voqalize.conformance import ConformanceError
from voqalize.sdk import Brain

from ._harness import (
    check_configured_at_connect,
    check_greeting,
    check_voice_pair,
    demo,
    demo_from,
)

discover()


@dataclass(frozen=True)
class Expected:
    """One demo's declared voice/language, and the payload that resolves it.

    ``payload`` matters for the demos that pick a language per caller — which is
    the whole reason the value lives in the brain and not on the agent record: one
    record holds one language, and Tamil Nadu wants Tamil while Gujarat wants
    Gujarati.

    ``at_connect`` is the other shape: the page knew the answer before the call
    existed and sent it with the connect request, so the brain configures nothing
    and the check inverts. A row states one or the other, never both — that is
    what makes "which layer owns this demo's language" a written-down answer
    rather than something read off whichever file you happen to open.

    ``unported`` marks a pair no layer is putting on the wire *yet*: the demo is
    still on the pre-v3 ``on_session_start(self, session, start)`` signature, which
    the SDK never calls, so it has nowhere to make the call from. The pair stays
    written down here and the row is xfailed strictly — the register, not an
    excuse."""

    voice: str | None = None
    language: str | None = None
    at_connect: bool = False
    unported: bool = False
    payload: dict[str, Any] = field(default_factory=dict)
    build: Callable[[], Brain] | None = None

    def __post_init__(self) -> None:
        stated = self.voice is not None and self.language is not None
        if stated == self.at_connect:
            raise ValueError(
                "state either the voice/language pair this demo speaks or "
                "at_connect=True, and exactly one of them"
            )
        if self.unported and not stated:
            raise ValueError("an unported row still states the pair the demo owes")


# The full demo set. Keep this table in step with ``demos/manifest.json`` — the
# test below fails if a demo is discovered and not listed here, so adding a demo
# without declaring its voice is a red suite, not a silent gap.
DEMOS: dict[str, Expected] = {
    "aura": Expected(voice="omnivoice/gauri", language="en", unported=True),
    "forge": Expected(voice="omnivoice/gauri", language="en"),
    "interview_bot": Expected(voice="omnivoice/gauri", language="en"),
    "legal": Expected(voice="omnivoice/gauri", language="en"),
    # Auric opens in the language of the enquiry form's state; nothing in the
    # payload ⇒ the Hindi default.
    "lead_qual": Expected(voice="omnivoice/gauri", language="hi"),
    "orderdesk": Expected(voice="omnivoice/gauri", language="hi"),
    "servicing": Expected(voice="omnivoice/gauri", language="en"),
    "shopping": Expected(voice="omnivoice/gaurav", language="en"),
    # The patient picks sugar's language on the page, before the call exists, so
    # it rides the connect request and this brain configures nothing. What the
    # page sends is checked where it is built
    # (``demos/sugar/frontend/src/data.ts``, which builds both legs from one
    # toggle); what is checkable from here is that no brain-side default has
    # grown back beside it.
    "sugar": Expected(at_connect=True),
    "support": Expected(voice="omnivoice/gaurav", language="en"),
    "travel": Expected(voice="omnivoice/gauri", language="hi"),
}

UNPORTED = (
    "pre-v3 on_session_start signature — the SDK never calls it, so this demo has "
    "nowhere to configure from. Owed by #43; when it lands, drop `unported=True`."
)


def _row(name: str):
    """One parametrized case, xfailed strictly while the demo is unported."""
    marks = [pytest.mark.xfail(strict=True, reason=UNPORTED)] if DEMOS[name].unported else []
    return pytest.param(name, marks=marks)


def _open(name: str, expected: Expected):
    """The rig for one demo — through the umbrella's own factory where the demo
    takes the injected provider, directly where it builds its own model."""
    if expected.build is not None:
        return demo_from(name, expected.build)
    return demo(name, ScriptedGemini())


def test_every_discovered_demo_has_a_row() -> None:
    """A demo dropped into ``demos/`` is registered by existing; this table is not.
    Fail loudly rather than skipping the new demo's voice silently."""
    discovered = {d.name for d in discover()}
    assert discovered == set(DEMOS), (
        f"undeclared: {sorted(discovered - set(DEMOS))}; stale: {sorted(set(DEMOS) - discovered)}"
    )


@pytest.mark.parametrize("name", [_row(n) for n in sorted(DEMOS)])
async def test_demo_puts_a_complete_voice_pair_on_the_wire(name: str) -> None:
    """Open a real session against the demo and read the settings frames.

    This is the whole contract: the caller heard *something*, and the recognizer
    and the reference clip were told the same language before they did."""
    expected = DEMOS[name]
    async with _open(name, expected) as rig:
        greeting = await rig.driver.start_session(init=expected.payload)
        check_greeting(rig, greeting)
        if expected.at_connect:
            check_configured_at_connect(rig)
            return
        assert expected.voice is not None and expected.language is not None
        check_voice_pair(rig, voice=expected.voice, language=expected.language)


async def test_a_language_in_the_payload_is_not_a_second_authority() -> None:
    """Sugar's patient picks the language, and ``init`` carries it — but only so the
    coach knows which language to *write* in. The wire was moved by the ``config``
    the page sent beside it.

    So the payload naming Hindi must not make this brain configure anything. Two
    layers both answering "which language" is how they drift: edit one and the
    coach writes Devanagari that an English reference clip reads aloud, correct on
    paper and foreign in the ear — which is exactly what shipped."""
    async with demo("sugar", ScriptedGemini()) as rig:
        await rig.driver.start_session(init={"language": "Hindi", "scenario": {}})
        check_configured_at_connect(rig)


async def test_a_per_caller_language_follows_the_enquiry_state() -> None:
    """Auric resolves the caller's language from the enquiry form's state — one
    agent, nine languages, which no single agent-record field could hold."""
    async with demo("lead_qual", ScriptedGemini()) as rig:
        await rig.driver.start_session(init={"name": "Meera", "state": "Tamil Nadu"})
        check_voice_pair(rig, voice="omnivoice/gauri", language="ta")


async def test_the_check_fails_when_a_half_is_wrong() -> None:
    """The negative control: this suite's own probe must be able to fail.

    A green check against a session that never sent the frames — or sent a
    mismatched pair — would be worse than no check, because it reads as proof. So
    assert against a real, correctly-configured session that the *wrong*
    expectation is rejected, on each half independently."""
    async with demo("legal", ScriptedGemini()) as rig:
        await rig.driver.start_session()
        # The session really is en/gauri — so each of these must raise.
        with pytest.raises(ConformanceError, match="TTS language"):
            check_voice_pair(rig, voice="omnivoice/gauri", language="hi")
        with pytest.raises(ConformanceError, match="TTS voice"):
            check_voice_pair(rig, voice="omnivoice/gaurav", language="en")
