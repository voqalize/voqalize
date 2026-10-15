"""The site as the brain sees it: the pages Aria may link to, and the languages she speaks.

Two tables live here, and each exists so the model never has to guess.

**The pages.** The approved list is ``knowledge/approved_pages.json``, read by
``knowledge.py`` into :data:`~.knowledge.ALLOWLIST`. This module only turns it
into what the prompt needs: one line per page, in the order KDEM listed them, so
the model can choose a page by what it is for. The model never writes a URL the
brain then trusts — ``offer_page``, ``go_to_page`` and ``show_document``
canonicalise what it names and refuse anything the index does not hold now.

**The languages.** English, and Kannada on demand — the pilot's two. Both legs
move together, and the voice does not change: Aria is one woman in two languages,
and the ``gauri`` clip speaks Kannada. Naming one leg and not the other is
refused by the SDK, so the table states both.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, get_args

from voqalize.sdk.wire import Language, Voice

from .knowledge import ALLOWLIST, SITE, path_of

# ─── The languages ─────────────────────────────────────────────────────────────

LanguageName = Literal["english", "kannada"]
LanguageTag = Literal["en", "kn"]
"""The languages the call can be conducted in. A ``Literal`` so a language the
pilot does not serve is a validation error, not a configure the speech tier refuses."""

VOICE = Voice.OMNIVOICE_GAURI
"""Aria's voice in both languages — one woman, so the voice does not move with the language."""


@dataclass(frozen=True)
class Speech:
    """One language: what the recognizer listens for and what the voice speaks."""

    name: LanguageName
    code: Language
    tag: LanguageTag
    """How the page names it: the snippet's toggle and ``init.lang``."""
    voice: Voice = VOICE


SPEECH: dict[LanguageName, Speech] = {
    "english": Speech("english", Language.EN, "en"),
    "kannada": Speech("kannada", Language.KN, "kn"),
}

BY_TAG: dict[LanguageTag, Speech] = {s.tag: s for s in SPEECH.values()}
BY_CODE: dict[Language, Speech] = {s.code: s for s in SPEECH.values()}

OPENING = SPEECH["english"]
"""A call opens in English, the site's language, unless the visitor picked
Kannada on the snippet's toggle before it started (``init.lang == "kn"``)."""


# ─── The pages ────────────────────────────────────────────────────────────────


def page_digest(linkable: Callable[[str], bool] = lambda _url: True) -> str:
    """One line per approved page that ``linkable`` accepts: the path the model
    names, and the page's title. The brain passes what it may link right now, so
    a listed page the refresh has dropped is not offered."""
    return "\n".join(f"  {path_of(p.url)} — {p.title}" for p in ALLOWLIST.pages if linkable(p.url))


CONTACT_PATH = path_of(ALLOWLIST.contact_url)


# ─── The KAN application form ─────────────────────────────────────────────────

KAN_URL = f"{SITE}/acceleration-network/"
"""The Karnataka Acceleration Network page, which carries its application form."""

KanField = Literal["startup_name", "sector", "founder_name", "mobile", "email", "location"]
"""The form's six fields, in the order the form shows them."""

KAN_LABELS: dict[KanField, str] = {
    "startup_name": "Name of the startup",
    "sector": "Sector",
    "founder_name": "Founder/Co-Founder Name",
    "mobile": "Mobile number",
    "email": "Email ID",
    "location": "Interested Location for Acceleration Network",
}
"""Each field's visible label on the form, which is how the snippet finds it:
Elementor's own field ids do not follow the labels."""

KAN_LOCATIONS: tuple[str, ...] = (
    "Bengaluru - JAIN Launchpad",
    "Bengaluru - GINSERV",
    "Bengaluru - DERBI Foundation",
    "Mysuru - SJCE STEP",
    "Mangaluru - SHINE Foundation",
    "Hubballi-Dharwad-Belagavi \u2013 ASTRA, Dharwad",
)
"""The location drop-down's options, exactly as the form writes them (the last
one with an en dash), the placeholder left out."""


# ─── Import-time checks ───────────────────────────────────────────────────────


def _assert_languages() -> None:
    declared = set(get_args(LanguageName))
    if declared != set(SPEECH):
        missing = ", ".join(sorted(declared ^ set(SPEECH)))
        raise RuntimeError(f"kdem: LanguageName and SPEECH disagree on: {missing}")


def _assert_contact_is_approved() -> None:
    # The don't-know line offers Contact Us, so it has to be a page she may link.
    if ALLOWLIST.approved(ALLOWLIST.contact_url) is None:
        raise RuntimeError(f"kdem: contact_url {ALLOWLIST.contact_url} is not an approved page")


def _assert_pages_are_on_the_site() -> None:
    for p in ALLOWLIST.pages:
        if not p.url.startswith(SITE + "/"):
            raise RuntimeError(f"kdem: approved page {p.url} is not on {SITE}")


def _assert_kan_page_is_approved() -> None:
    # The form fills only on this page, so it has to be one Aria may take them to.
    if ALLOWLIST.approved(KAN_URL) is None:
        raise RuntimeError(f"kdem: the KAN page {KAN_URL} is not an approved page")
    if set(get_args(KanField)) != set(KAN_LABELS):
        raise RuntimeError("kdem: KanField and KAN_LABELS disagree")


_assert_languages()
_assert_contact_is_approved()
_assert_pages_are_on_the_site()
_assert_kan_page_is_approved()
