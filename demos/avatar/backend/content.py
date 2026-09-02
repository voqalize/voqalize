"""What the avatar demo knows: the eight documentation sections, the nine
avatars, and the background the model answers from.

Kept out of ``brain.py`` because it is *content* — it is edited when the avatar
library changes, not when the conversation does, and those are two different
review conversations.

Everything here is about `voqalize/avatar` itself. **The page holds the
documentation; this file holds its index and what to say about it.** The model
scrolls the reader to a section and then answers with that section open, so a
visitor who asks "how does the lipsync stay in step?" gets the cue timeline in
front of them rather than instead of the answer. The prose here is written to be
*spoken* — short clauses, no bullet grammar, no symbols a synthesizer has to
guess at — and it deliberately does not repeat the page's sentences, because the
page is already being read.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from voqalize.sdk.wire import Voice

# ─── The documentation sections ───────────────────────────────────────────────

SectionId = Literal[
    "overview",
    "quickstart",
    "states",
    "wire",
    "lipsync",
    "faces",
    "custom",
    "limits",
]


@dataclass(frozen=True)
class Section:
    """One section of the page's documentation.

    ``title`` is the heading as the reader sees it, so the model can refer to it
    out loud without inventing a name. ``notes`` is what the model reads before
    it speaks, and it is the part that is *not* on the page: the section is
    already written for someone reading, and an answer is for someone listening.
    """

    id: SectionId
    title: str
    notes: str


SECTIONS: tuple[Section, ...] = (
    Section(
        id="overview",
        title="A talking head for pipecat agents",
        notes=(
            "It is a two-D face, drawn in the browser, driven over the data channel your "
            "pipecat call already has open. There is no video track and no per-minute "
            "avatar vendor — the bytes on the wire are a few hundred a second, not a "
            "second video stream. Two packages, one wire format: a pipecat frame "
            "processor on the server, one mount call in the browser. It is MIT, and it "
            "works against any pipecat pipeline."
        ),
    ),
    Section(
        id="quickstart",
        title="Add it to a pipecat app",
        notes=(
            "Three steps and they are all on screen. Install both halves — they are ends "
            "of one wire format, so they version together. Put the processor between "
            "text-to-speech and the transport, with no arguments: from that seat it can "
            "see the audio about to play, which is what the mouth needs. Then mount it in "
            "the browser with the pipecat client you already connected with. That is the "
            "whole integration. Everything after it is optional."
        ),
    ),
    Section(
        id="states",
        title="What the avatar shows between turns",
        notes=(
            "Listening and speaking are the easy states. Everything between them is "
            "inference, and getting it wrong is expensive: a face that goes blank while a "
            "model is mid-inference reads as a dropped connection. So idle is the wrong "
            "answer to almost all of the silence in a call. Three claims cover it. "
            "Thinking means a reply is outstanding. Working means a tool is running. "
            "Straining means nothing came back at all. The split is about who can see "
            "what — the processor arms thinking itself, because it watches the turn "
            "boundaries and knows a reply is owed. It cannot see a tool running inside a "
            "brain on the far side of a socket, so working is one line you send, and this "
            "demo sends it out loud when you ask it to dig something up."
        ),
    ),
    Section(
        id="wire",
        title="Drive the avatar from your own code",
        notes=(
            "The whole server-to-avatar vocabulary is three commands. A claim is a "
            "durable candidate state, and exactly one is in flight at a time, so a later "
            "claim replaces the earlier one. An action is a point-in-time behaviour that "
            "completes on its own and leaves no state behind — a wave, a nod, a wait "
            "gesture. Cues are viseme letters with millisecond offsets, which is the "
            "mouth. All three ride one message on the channel that is already open. The "
            "precedence runs one way and it is the part worth remembering: what the "
            "browser observes about the audio is a fact and it wins, and your claim sits "
            "underneath every fact and retires the moment one arrives. So you can tell "
            "the face what to consider. You cannot tell it what is happening."
        ),
    ),
    Section(
        id="lipsync",
        title="How the mouth stays in sync",
        notes=(
            "Cues are never a play-this-now command, and that is the design. Each cue is "
            "a time in milliseconds, a mouth letter from A to H, and optionally a "
            "loudness. Zero on that clock is the first audio sample of the turn, so "
            "arrival time carries no meaning at all — a patch usually lands before the "
            "audio it describes. Two legs write the same track. A fast leg predicts "
            "shapes from the text the moment there is text, so the mouth moves the "
            "instant audio starts. An accurate leg comes in behind it from the real "
            "waveform and splices: from underscore m s says discard the track at and "
            "after this offset, then append these. That one primitive is the whole "
            "correction mechanism, and if it is working you never see the second leg "
            "arrive."
        ),
    ),
    Section(
        id="faces",
        title="Choose a face, or ship your own",
        notes=(
            "Nine ship today: three line-art faces and six painted ones, all on the same "
            "rig and the same wire. Swapping one for another is a remount and nothing "
            "else, which is why this demo asks you to choose before you dial rather than "
            "during the call: nine faces share two recorded voices, so the face and the "
            "voice are a single choice, and a voice that changes halfway through an "
            "answer is the thing a listener notices. The part worth knowing is the "
            "smoothing: every channel has its own time constant and "
            "the head's is about a hundred and sixty milliseconds, so keyframes are not "
            "what the face does — the smoothing between them is. Blinking, breathing, "
            "gaze and idle sway are the renderer's own and are never sent by anybody, "
            "because a server that had to send a blink would be sending it late."
        ),
    ),
    Section(
        id="custom",
        title="Ship your own avatar",
        notes=(
            "An avatar is any module that exports a create avatar function. There is no "
            "registry to add yourself to and no renderer interface to implement, on "
            "purpose — you get a canvas and the same pose numbers the shipped faces get, "
            "and what you draw with them is yours. Two ways in. Start from a shipped "
            "face and change the drawing, which keeps the rig and takes an afternoon. Or "
            "write the render function yourself, in canvas, S-V-G, W-e-b-G-L or anything "
            "else that can paint sixty times a second. Either way you handle three "
            "things: mouth shape, which arrives as one of eight letters, plus head turn "
            "and eye state. Everything else has a sensible resting value, so a face that "
            "only does the mouth still works."
        ),
    ),
    Section(
        id="limits",
        title="What it does not do",
        notes=(
            "Four honest ones. It is two-D and vector — it is not photoreal, and it is "
            "not trying to be. Only English is aligned right now, because the aligner's "
            "acoustic model is English. The Python wheel carries a compiled aligner, so "
            "if you install from source instead you lose exactly one thing: the mouth "
            "stops moving, and everything else keeps working. And it needs a pipecat "
            "pipeline — there is no standalone player."
        ),
    ),
)

SECTIONS_BY_ID: dict[str, Section] = {section.id: section for section in SECTIONS}


# ─── The avatars ──────────────────────────────────────────────────────────────

AvatarKey = Literal[
    "peep",
    "wren",
    "myna",
    "arjun",
    "meera",
    "vikram",
    "ishita",
    "kabir",
    "naina",
]

#: The face a call gets when the visitor did not pick one, and the one constraint
#: on choosing it: it must be a face whose gender matches the voice the *agent* is
#: provisioned with (``omnivoice/gaurav``). Every other face arrives in the
#: connect request and is configured before a word is spoken, so it needs no such
#: agreement — this one is the fallback for a payload that named nothing, and a
#: fallback that disagreed with the agent's own voice would be the exact defect
#: the pre-call choice exists to remove.
DEFAULT_AVATAR: AvatarKey = "arjun"


@dataclass(frozen=True)
class AvatarIdentity:
    """One avatar, and the voice that goes with it.

    ``voice`` is the whole reason this table exists on the *brain* side. There
    are two recorded reference speakers, so a face and a voice can only be paired
    by gender — and a face read as one gender speaking in the other is the first
    thing anyone notices, before a single nod is judged. Pairing it here, in the
    place that can actually change the voice, is what stops the page ever holding
    half the answer.
    """

    key: AvatarKey
    name: str
    renderer: str
    blurb: str
    voice: Voice


AVATARS: tuple[AvatarIdentity, ...] = (
    AvatarIdentity(
        key="myna",
        name="Myna",
        renderer="line art",
        blurb="Line-art, wavy hair and hoop earrings. The default, and the drawing every rig change is judged against.",
        voice=Voice.OMNIVOICE_GAURI,
    ),
    AvatarIdentity(
        key="peep",
        name="Peep",
        renderer="line art",
        blurb="The library's default face. Taper fade, polo collar, one accent colour and no strokes anywhere.",
        voice=Voice.OMNIVOICE_GAURAV,
    ),
    AvatarIdentity(
        key="wren",
        name="Wren",
        renderer="line art",
        blurb="Same idiom as Peep, different person: the hair is the silhouette and the glasses are the accent.",
        voice=Voice.OMNIVOICE_GAURI,
    ),
    AvatarIdentity(
        key="arjun",
        name="Arjun",
        renderer="canvas",
        blurb="Painted rather than drawn — a professional interviewer, authored to read at call-tile size.",
        voice=Voice.OMNIVOICE_GAURAV,
    ),
    AvatarIdentity(
        key="meera",
        name="Meera",
        renderer="canvas",
        blurb="The painted interviewer's counterpart. Same rig, same thirty channels, a different drawing.",
        voice=Voice.OMNIVOICE_GAURI,
    ),
    AvatarIdentity(
        key="vikram",
        name="Vikram",
        renderer="canvas",
        blurb="Polished and formal — the one to put in front of a customer who is buying something.",
        voice=Voice.OMNIVOICE_GAURAV,
    ),
    AvatarIdentity(
        key="ishita",
        name="Ishita",
        renderer="canvas",
        blurb="Polished and formal, the other half of that pair.",
        voice=Voice.OMNIVOICE_GAURI,
    ),
    AvatarIdentity(
        key="kabir",
        name="Kabir",
        renderer="canvas",
        blurb="Relaxed. Reads as a colleague rather than a desk.",
        voice=Voice.OMNIVOICE_GAURAV,
    ),
    AvatarIdentity(
        key="naina",
        name="Naina",
        renderer="canvas",
        blurb="Relaxed, and the last of the painted six.",
        voice=Voice.OMNIVOICE_GAURI,
    ),
)

AVATARS_BY_KEY: dict[str, AvatarIdentity] = {a.key: a for a in AVATARS}


def avatars_for_prompt() -> str:
    """The roster as the model reads it. No key: the model does not choose a face
    any more, so a key here would only be something to read out loud."""
    return "\n".join(f"- {a.name} — {a.renderer}. {a.blurb}" for a in AVATARS)


def sections_for_prompt() -> str:
    """The section index as the model reads it. The notes are NOT here: they
    arrive as the tool's return value, so the model reads them with the section
    already open in front of the visitor rather than carrying seven of them
    through every turn."""
    return "\n".join(f"- [{s.id}] {s.title}" for s in SECTIONS)


# ─── Background the model answers from ────────────────────────────────────────
#
# Facts a visitor asks for that no section carries. Short, because a voice answer
# is two sentences and a prompt that offers ten paragraphs gets five of them read
# aloud.

BACKGROUND = """\
FACTS ABOUT THE LIBRARY — answer from these, and say you are not sure if it is not here:
- It is called voqalize/avatar. MIT-licensed, on GitHub, and published as @voqalize/avatar on npm and voqalize-avatar on PyPI. The two are ends of one wire format and publish together.
- It is a 2-D talking head, drawn in the browser. There is no video track, no per-minute avatar vendor and no second media path — the face rides the data channel that is already open.
- The backend half is one pipecat frame processor. It sits between text-to-speech and the transport, and from that seat it publishes the state it infers and the visemes for the audio about to play.
- The browser half is one mount call. You give it the pipecat client you already connected with, and there is nothing else to configure.
- It works against any pipecat pipeline. Voqalize is one consumer of it, not the only one.
- Nine avatars ship today: three line-art faces and six painted ones. You can ship your own: an avatar is any module that exports createAvatar, and there is no registry and no renderer interface to implement.
- Backchannels — the small acknowledgements, "mm-hm", "one moment", a nod — were the part the brief called out as mattering most, because a face listens far more than it speaks.

FACTS ABOUT THIS CALL — the same again, for how you are being run right now:
- Your voice, your ears and this call's audio are Voqalize. You are a brain: a WebSocket on the other side of it, holding the model and the prompt and these tools, dialled once when the call started.
- The face you are wearing is the open-source library, driven over that same call's data channel.
- Voqalize is what you would use to put a voice on your own agent. The avatar library is free either way, and it is yours whether or not you ever use us.
"""
