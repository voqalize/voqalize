"""The shared nod's reading of a message (:func:`voqalize_demos.acknowledge.classify`).

Every demo with a nod reads what the user said through it, so a change here is
pinned for all of them at once.
"""

from __future__ import annotations

import pytest
from voqalize_demos.acknowledge import classify


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        # "No, and …" declines his offer and asks something new: on a Santander
        # Arena call it was answered "Entendido, gracias por avisarme."
        ("No, y quiero ir a algunos recitales de Los Tres. ¿Cuándo es?", "request"),
        ("No, and I want to see the bars.", "request"),
        ("No, y ¿dónde estaciono?", "question"),
        # A "no" that corrects him still reads as one.
        ("No, that's wrong.", "correction"),
        ("No, the other one.", "correction"),
        ("No, quiero el otro.", "correction"),
        ("Nahi, woh wala nahi.", "correction"),
        # A bare no, or a no with thanks, is nothing to nod at.
        ("No.", None),
        ("No, gracias, con eso es suficiente.", None),
    ],
)
def test_a_leading_no_is_a_correction_unless_it_goes_on_with_and(
    text: str, kind: str | None
) -> None:
    assert classify(text) == kind
