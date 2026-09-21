"""The homepage as the brain sees it: sections, highlight targets, knowledge, languages.

Three tables live here, and each one exists because the model must not be left to
guess at it.

**The page map.** ``voqalize.com/`` is an Astro site in another repo. The brain
cannot read it, so the sections it may scroll to and the elements it may point at
are enumerated as :data:`SectionId` and :data:`TargetId` — a name the model
invents is a validation error rather than a scroll to nowhere. Every id here has
a ``data-vq`` attribute on the page with the same value; that attribute *is* the
contract, and it spans two repos. Change a component's markup without changing
this file and the agent points at nothing.

**The knowledge base.** ``knowledge/L1.md`` is the dense reference, compiled into
the system instruction once at import — it is what the agent answers from. The
``knowledge/l2/`` deep dives are read through a tool, one at a time, when a
question goes past L1. They are deliberately *not* all in the prompt: the whole
set is an order of magnitude larger than L1 and most of it is never needed.

**The languages.** A visitor may switch language mid-call, and the two legs are
set separately and mean different things — ``stt.language`` picks the recognizer,
``tts.language`` picks the recorded clip the voice is cloned from. Not every
recognized language has a clip, so this table states both, and pairs each with a
voice that can actually speak it. Naming one leg and not the other is refused by
the SDK; naming a clip a voice does not have is rejected by the speech tier. So
the table is the one place that has to be right.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Literal, get_args

from voqalize.sdk.wire import Language, Voice

# ─── The page map ──────────────────────────────────────────────────────────────

SectionId = Literal[
    "top",
    "preview",
    "why",
    "brain",
    "how",
    "provides",
    "avatars",
    "speech",
    "observability",
    "enterprise",
    "start",
]
"""The homepage anchors, in scroll order. The value is the element id: ``#top``."""

TargetId = Literal[
    "hero.h1",
    "hero.sub",
    "hero.cta",
    "hero.mcp",
    "hero.device",
    "preview.status",
    "preview.stat.years",
    "preview.stat.interviews",
    "preview.stat.concurrent",
    "why.line.knows",
    "why.line.acts",
    "why.line.takeover",
    "why.line.flow",
    "why.budget",
    "why.uses",
    "brain.beat.data",
    "brain.beat.stateful",
    "brain.beat.loop",
    "brain.beat.app",
    "brain.keep",
    "how.diagram",
    "how.pipecat",
    "how.cortex",
    "how.cta",
    "provides.cap.webrtc",
    "provides.cap.speech",
    "provides.cap.avatar",
    "provides.cap.ui",
    "provides.cap.testing",
    "provides.cap.observability",
    "provides.cap.recording",
    "provides.swap.voice",
    "provides.swap.tts",
    "provides.swap.avatar",
    "avatars.stage",
    "avatars.bar",
    "avatars.faces",
    "avatars.note",
    "speech.headline",
    "obs.waterfall",
    "obs.holds",
    "obs.lifecycle",
    "obs.reads",
    "ent.card.where",
    "ent.card.certs",
    "ent.card.fdse",
    "start.prompt",
    "start.cta",
]
"""Every element the agent may point at, as its ``data-vq`` attribute value.

Named ``<section-prefix>.<part>`` so a target says which section it is in without
a second table — see :data:`SECTION_OF_TARGET`, which derives that mapping rather
than restating it.
"""


@dataclass(frozen=True)
class Section:
    """One band of the homepage: where it is, what it says, what it can point at."""

    id: SectionId
    title: str
    """The section's own headline, as the visitor reads it."""
    answers: str
    """The question this band is the answer to — how the model chooses between them."""
    targets: tuple[tuple[TargetId, str], ...]
    """Each highlightable element and what a visitor would call it."""


SECTIONS: tuple[Section, ...] = (
    Section(
        id="top",
        title="Voice mode for your app.",
        answers="what Voqalize is, and the one-line split of responsibilities",
        targets=(
            ("hero.h1", "the headline"),
            ("hero.sub", "the tagline: you keep the agent, we run the voice"),
            ("hero.cta", "the start buttons"),
            ("hero.mcp", "the MCP server URL, with its copy button"),
            ("hero.device", "the phone, running the order-desk workflow"),
        ),
    ),
    Section(
        id="preview",
        title="the status strip",
        answers="whether this is real, and who has been running it",
        targets=(
            ("preview.status", "developer preview, built on the tier behind Recruit41"),
            ("preview.stat.years", "two years in production"),
            ("preview.stat.interviews", "fifty thousand interviews"),
            ("preview.stat.concurrent", "1,143 simultaneous conversations"),
        ),
    ),
    Section(
        id="why",
        title="The best voice agent barely speaks.",
        answers="why voice in an app at all, and what makes it different from a chatbot",
        targets=(
            ("why.line.knows", "it knows what is on screen"),
            ("why.line.acts", "it acts on the app"),
            ("why.line.takeover", "the user can take over"),
            ("why.line.flow", "the conversation keeps its flow"),
            ("why.budget", "the flat speech-budget line"),
            ("why.uses", "the pills: where teams put it"),
        ),
    ),
    Section(
        id="brain",
        title="A stateful brain, in your own backend.",
        answers="whose code does the thinking, and what stays on the customer's side",
        targets=(
            ("brain.beat.data", "your data stays yours"),
            ("brain.beat.stateful", "the brain holds state"),
            ("brain.beat.loop", "your own agent loop"),
            ("brain.beat.app", "it drives your app"),
            ("brain.keep", "the boundary band: what you keep"),
        ),
    ),
    Section(
        id="how",
        title="Voqalize calls your WebSocket once per session.",
        answers="how it integrates — the handshake, the socket, the client library",
        targets=(
            ("how.diagram", "the connection diagram"),
            ("how.pipecat", "the browser side is stock pipecat"),
            ("how.cortex", "the footnote on Cortex, for brains behind NAT"),
            ("how.cta", "the docs buttons"),
        ),
    ),
    Section(
        id="provides",
        title="Batteries included.",
        answers="what Voqalize actually runs, and what can be swapped",
        targets=(
            ("provides.cap.webrtc", "WebRTC transport"),
            ("provides.cap.speech", "recognition and synthesis"),
            ("provides.cap.avatar", "the avatar"),
            ("provides.cap.ui", "typed screen actions"),
            ("provides.cap.testing", "the testing harness"),
            ("provides.cap.observability", "per-turn observability"),
            ("provides.cap.recording", "call recording"),
            ("provides.swap.voice", "custom voices"),
            ("provides.swap.tts", "bring your own TTS provider"),
            ("provides.swap.avatar", "a custom avatar"),
        ),
    ),
    Section(
        id="avatars",
        title="A face that spends most of the call listening.",
        answers="the avatar: how it is rendered, what it costs, how it is licensed",
        targets=(
            ("avatars.stage", "the avatar on stage — this is Tanya, the agent's own face"),
            ("avatars.bar", "the bar: 7.2 seconds spoken out of a 28-second recording"),
            ("avatars.faces", "the other characters"),
            ("avatars.note", "the licence note: MIT, on npm and PyPI"),
        ),
    ),
    Section(
        id="speech",
        title="English, Spanish, French, Italian, Japanese and 22 Indian languages.",
        answers="the speech tier — the roster, whose models these are",
        targets=(("speech.headline", "the language headline"),),
    ),
    Section(
        id="observability",
        title="Every turn, measured at every layer.",
        answers="what a developer sees after a call, and what is stored",
        targets=(
            ("obs.waterfall", "the per-turn waterfall, drawn to scale"),
            ("obs.holds", "what is stored"),
            ("obs.lifecycle", "the session lifecycle"),
            ("obs.reads", "how to read it back: console and MCP"),
        ),
    ),
    Section(
        id="enterprise",
        title="Cloud hosted, or deployed in your VPC.",
        answers="running it inside an estate — residency, certifications, delivery",
        targets=(
            ("ent.card.where", "where it runs: cloud or your own VPC"),
            ("ent.card.certs", "the certifications"),
            ("ent.card.fdse", "forward-deployed engineering"),
        ),
    ),
    Section(
        id="start",
        title="Enable voice mode in your app.",
        answers="how to begin, today",
        targets=(
            ("start.prompt", "the prompt to paste into a coding agent"),
            ("start.cta", "the sign-up button"),
        ),
    ),
)

SECTIONS_BY_ID: dict[SectionId, Section] = {s.id: s for s in SECTIONS}

SECTION_OF_TARGET: dict[TargetId, SectionId] = {
    target: section.id for section in SECTIONS for target, _ in section.targets
}
"""Which band each target sits in — derived, so a target cannot drift out of its section."""


def page_digest() -> str:
    """The page map as the system instruction carries it: anchor, headline, targets."""
    blocks: list[str] = []
    for section in SECTIONS:
        pointables = " · ".join(f"{target} {what}" for target, what in section.targets)
        blocks.append(
            f"#{section.id} — {section.title} Answers: {section.answers}.\n    {pointables}"
        )
    return "\n".join(blocks)


def _assert_targets_enumerated() -> None:
    """Every declared target belongs to a section, and every section's targets are declared.

    Both halves of :data:`TargetId` and :data:`SECTIONS` are written by hand, and a
    target in one and not the other fails silently — an unreachable literal, or a
    ``data-vq`` name the model can name but nothing maps. So it fails here, at import.
    """
    declared = set(get_args(TargetId))
    mapped = set(SECTION_OF_TARGET)
    if declared != mapped:
        missing = ", ".join(sorted(declared ^ mapped))
        raise RuntimeError(f"marketing: TargetId and SECTIONS disagree on: {missing}")


_assert_targets_enumerated()


# ─── The note panel ────────────────────────────────────────────────────────────

NoteLayout = Literal["note", "steps", "compare"]
"""How the written panel is laid out. The page owns the rendering; this is the
shape the model says the answer has.

It is here, with the page map, because it is the same kind of fact: a name the
model may use that means something in another repo's markup. The page reads it
off :class:`~brain.ShowNote` and lays the same markdown out each way — a single
column, a numbered sequence, or panes side by side — so a layout that does not
fit the writing it was given degrades to prose rather than breaking.
"""


# ─── The knowledge base ────────────────────────────────────────────────────────

KNOWLEDGE = Path(__file__).parent / "knowledge"

TopicId = Literal[
    "wire-and-brain",
    "connect-and-clients",
    "latency-and-failure",
    "deployment-and-vpc",
    "speech-and-languages",
    "avatar",
    "observability-and-testing",
    "security-and-data",
    "pricing-and-preview",
    "company-and-comparison",
]
"""The deep dives in ``knowledge/l2/``. Each is read whole, on demand, or not at all."""

TOPICS: dict[TopicId, str] = {
    "wire-and-brain": (
        "frames, the envelope, turns and speech units, the Brain callbacks, typed "
        "actions and app events, heard truth, implementing the wire in another language"
    ),
    "connect-and-clients": (
        "the connect handshake, the credential paths, the origin allowlist, pipecat "
        "packages and versions, React Native and mobile, local development, the MCP tools"
    ),
    "latency-and-failure": (
        "the turn waterfall, timeouts, what the caller hears when the brain is down, "
        "reconnection, interruption, background work, session limits"
    ),
    "deployment-and-vpc": (
        "inbound versus Cortex in detail, VPC deployment, GPUs, regions, certifications, forward-deployed engineering"
    ),
    "speech-and-languages": (
        "the language roster, the both-legs rule, the voices, switching mid-call, "
        "why there is no provider slot, bring-your-own TTS"
    ),
    "avatar": (
        "how the face is driven, the cue stream, idle behaviour, what it costs, "
        "custom avatars, using it standalone with any pipecat agent"
    ),
    "observability-and-testing": (
        "the call record, logs, events, recordings, the conformance harness, CI, usage counters"
    ),
    "security-and-data": (
        "keys and rotation, what is stored and what is not, certifications, the RTVI "
        "whitelist, why management is OAuth rather than a REST key"
    ),
    "pricing-and-preview": (
        "the pricing shape, what preview does and does not promise, production readiness, support"
    ),
    "company-and-comparison": (
        "Recruit41, the moat, build-versus-buy, realtime voice APIs, "
        "which parts of the stack are genuinely ours"
    ),
}
"""What each deep dive is for — the index the model chooses from, and nothing more."""


def core_knowledge() -> str:
    """L1: the dense reference, read once at import and compiled into the prompt."""
    return (KNOWLEDGE / "L1.md").read_text(encoding="utf-8")


@cache
def read_topic(topic: TopicId) -> str:
    """One deep dive, whole. Cached — a session that asks twice pays for one read."""
    return (KNOWLEDGE / "l2" / f"{topic}.md").read_text(encoding="utf-8")


def topic_digest() -> str:
    """The deep-dive index as the system instruction carries it."""
    return "\n".join(f"{topic} — {what}" for topic, what in TOPICS.items())


def _assert_topics_present() -> None:
    """Every declared topic has a file. A missing one is a tool call that raises mid-call."""
    missing = sorted(t for t in TOPICS if not (KNOWLEDGE / "l2" / f"{t}.md").is_file())
    if missing:
        raise RuntimeError(f"marketing: knowledge/l2 is missing {', '.join(missing)}")


_assert_topics_present()


# ─── Languages ─────────────────────────────────────────────────────────────────

LanguageName = Literal[
    "english",
    "hindi",
    "bengali",
    "gujarati",
    "kannada",
    "malayalam",
    "marathi",
    "punjabi",
    "tamil",
    "telugu",
    "assamese",
    "bodo",
    "dogri",
    "kashmiri",
    "konkani",
    "maithili",
    "manipuri",
    "nepali",
    "odia",
    "sanskrit",
    "santali",
    "sindhi",
    "urdu",
]
"""What the visitor may switch to, named rather than coded.

The wire wants ISO codes, and some of these have no two-letter one — so the model
picks a language by its name and this file does the translation. It also keeps the
model from naming a language the speech tier does not serve.
"""


@dataclass(frozen=True)
class Speech:
    """One language, resolved to a configuration the speech tier will accept."""

    name: LanguageName
    heard: Language
    """``stt.language`` — the recognizer."""
    spoken: Language
    """``tts.language`` — the reference clip the voice is cloned from."""
    voice: Voice


def _indic(name: LanguageName, code: Language, *, clip: Language | None = None) -> Speech:
    """An Indic language, spoken by Gauri.

    ``clip`` names a *different* language's reference clip, for a language the
    recognizer understands but no clip speaks. That substitution is stated here and
    said out loud rather than made silently — the speech tier refuses the pairing
    outright, so there is no quiet fallback to inherit.
    """
    return Speech(name=name, heard=code, spoken=clip or code, voice=Voice.OMNIVOICE_GAURI)


SPEECH: dict[LanguageName, Speech] = {
    s.name: s
    for s in (
        Speech(name="english", heard=Language.EN, spoken=Language.EN, voice=Voice.KOKORO_AVA),
        # Recognized and spoken: a clip exists for each of these.
        _indic("hindi", Language.HI),
        _indic("bengali", Language.BN),
        _indic("gujarati", Language.GU),
        _indic("kannada", Language.KN),
        _indic("malayalam", Language.ML),
        _indic("marathi", Language.MR),
        _indic("punjabi", Language.PA),
        _indic("tamil", Language.TA),
        _indic("telugu", Language.TE),
        # Recognized, with no clip of their own — heard in the language, answered
        # in the Hindi clip. The visitor is told, not surprised.
        _indic("assamese", Language.AS, clip=Language.HI),
        _indic("bodo", Language.BRX, clip=Language.HI),
        _indic("dogri", Language.DOI, clip=Language.HI),
        _indic("kashmiri", Language.KS, clip=Language.HI),
        _indic("konkani", Language.KOK, clip=Language.HI),
        _indic("maithili", Language.MAI, clip=Language.HI),
        _indic("manipuri", Language.MNI, clip=Language.HI),
        _indic("nepali", Language.NE, clip=Language.HI),
        _indic("odia", Language.OR, clip=Language.HI),
        _indic("sanskrit", Language.SA, clip=Language.HI),
        _indic("santali", Language.SAT, clip=Language.HI),
        _indic("sindhi", Language.SD, clip=Language.HI),
        _indic("urdu", Language.UR, clip=Language.HI),
    )
}

OPENING = SPEECH["english"]
"""The call starts in English, in Ava's voice. The visitor may move it from there."""


def _assert_languages_enumerated() -> None:
    """Every name in :data:`LanguageName` resolves. An unresolvable one is a tool that raises."""
    declared = set(get_args(LanguageName))
    if declared != set(SPEECH):
        missing = ", ".join(sorted(declared ^ set(SPEECH)))
        raise RuntimeError(f"marketing: LanguageName and SPEECH disagree on: {missing}")


_assert_languages_enumerated()
