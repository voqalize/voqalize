"""``call`` / ``reply_and_call`` can script *any* tool argument, including ``name``.

The keyword form (``call("open_itinerary", name="Poddar")``) reads best, but a tool
argument called ``name`` or ``text`` used to collide with the helper's own parameters —
the script silently changed the tool being called, or Python raised "got multiple values
for argument". Both helpers now take those positionally-only, and accept an explicit
``args=`` dict for the last ambiguous case.
"""

from __future__ import annotations

import pytest

pytest.importorskip("google.adk")

from voqalize.google_adk.testing import call, reply, reply_and_call


def test_a_tool_argument_named_name_does_not_collide() -> None:
    """``name=`` is the *tool's* argument — the tool being called is positional."""
    r = reply_and_call("Opening it.", "open_itinerary", name="Poddar Vietnam")
    assert r.text == "Opening it."
    assert r.calls == (("open_itinerary", {"name": "Poddar Vietnam"}),)


def test_a_tool_argument_named_text_does_not_collide() -> None:
    """Same for ``text=``, which the speech parameter used to shadow."""
    r = reply_and_call("Noting that.", "add_note", text="call back Monday")
    assert r.text == "Noting that."
    assert r.calls == (("add_note", {"text": "call back Monday"}),)


def test_call_takes_a_tool_argument_named_name_too() -> None:
    r = call("open_itinerary", name="Poddar Vietnam")
    assert r.calls == (("open_itinerary", {"name": "Poddar Vietnam"}),)


def test_the_explicit_args_dict_form_covers_every_key() -> None:
    """The dict form escapes even an argument literally named ``args``."""
    r = reply_and_call("Sure.", "run", args={"args": ["-v"], "name": "job"})
    assert r.calls == (("run", {"args": ["-v"], "name": "job"}),)


def test_mixing_the_two_forms_is_rejected() -> None:
    """Ambiguity is an error, not a silent merge."""
    with pytest.raises(TypeError, match="not both"):
        call("run", args={"a": 1}, b=2)


def test_reply_is_unchanged() -> None:
    """The speech-only helper keeps its plain signature."""
    assert reply("Hello.").text == "Hello."
