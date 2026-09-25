"""What the avatar demo knows: the documentation sections, the avatars on the
strip, and the background the model answers from.

Kept out of ``brain.py`` because it is *content* — it is edited when the avatar
library changes, not when the conversation does, and those are two different
review conversations.

Everything here is about `voqalize/avatar` itself. **The page holds the
documentation; this file holds its index and what to say about it.** The model
scrolls the reader to a section and then answers with that section open, so a
visitor who asks "how does the lipsync stay in step?" gets the cue timeline in
front of them rather than instead of the answer. The prose here is written to be
*spoken* — short sentences, no bullet grammar, no symbols a synthesizer has to
guess at — and it deliberately does not repeat the page's sentences, because the
page is already being read.

**Every note is a handful of short sentences, and that is the length control.**
The prompt asks for two short sentences a turn, and the model obeyed it until a
tool handed back a paragraph: whatever arrives as the answer's material is what
gets read aloud, at whatever length it arrived. So a note here is a set of
lines to pick one or two from, each under about twelve words.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from voqalize.sdk.wire import Voice

# ─── The documentation sections ───────────────────────────────────────────────

SectionId = Literal[
    "overview",
    "compare",
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
        title="Avatars for Pipecat Voice Agents",
        notes=(
            "This is an avatar library for Pipecat voice agents. "
            "The server turns the TTS audio into mouth shapes. "
            "The browser animates the face from them, in time with the audio. "
            "There is no video stream and no GPU. "
            "The library is open source, under the MIT licence."
        ),
    ),
    Section(
        id="compare",
        title="Compared with video avatar services",
        notes=(
            "HeyGen, Anam, Protoface, Simli and Tavus stream video of a face. "
            "They sit right after text to speech, and so do I. "
            "They send the audio to their servers and send video back. "
            "I send the browser a few small instructions, and it draws me. "
            "So there is no extra service and no video stream. "
            "A new face starts from one picture, made into a 2.5-D model in Blender. "
            "The server side stays the same; only the browser's file changes. "
            "They look like real video. I do not."
        ),
    ),
    Section(
        id="quickstart",
        title="Add it to a Pipecat app",
        notes=(
            "Install two packages. "
            "Put one processor right after text to speech. "
            "Mount the face with the pipecat client you already have. "
            "That is the whole integration."
        ),
    ),
    Section(
        id="states",
        title="What the avatar shows between turns",
        notes=(
            "Speaking and listening come from the audio. "
            "Between turns, I show thinking, working, or that I cannot hear you. "
            "An idle face there can look like a dropped call. "
            "The pipeline knows when a reply is due, so it sends thinking. "
            "It cannot see a tool that runs outside it, so you send working."
        ),
    ),
    Section(
        id="wire",
        title="Drive the avatar from your own code",
        notes=(
            "A server can say three things to me. "
            "A state is one I hold, like working. "
            "An action is a gesture that finishes by itself, like a wave. "
            "Cues are mouth shapes on a timeline. "
            "What the browser actually hears always beats what you send."
        ),
    ),
    Section(
        id="lipsync",
        title="How the mouth stays in sync",
        notes=(
            "Each cue is a time and a mouth shape. "
            "The clock starts at the first sound of the reply. "
            "So it does not matter when a cue arrives. "
            "A fast guess from the text starts the mouth at once. "
            "A second pass from the audio then replaces those guesses."
        ),
    ),
    Section(
        id="faces",
        title="Choose a face",
        notes=(
            "Every face ships in one package. "
            "The faces on this strip are 2.5-D characters, each built in Blender. "
            "Each face comes with its own voice, so you pick before the call. "
            "Blinks and breathing happen in the browser. Nobody sends them."
        ),
    ),
    Section(
        id="custom",
        title="Build your own avatar",
        notes=(
            "Any module that exports create avatar is an avatar. "
            "There is no registry to join. "
            "You can draw a new face on the shipped rig. "
            "Or write your own renderer, in canvas, S-V-G or W-e-b-G-L. "
            "You get the same pose numbers the shipped faces get."
        ),
    ),
    Section(
        id="limits",
        title="Limits",
        notes=(
            "It is not photoreal video. "
            "Only English mouth shapes are accurate. "
            "Without the compiled aligner, the mouth stays still and the rest works. "
            "And it needs a pipecat pipeline."
        ),
    ),
)

SECTIONS_BY_ID: dict[str, Section] = {section.id: section for section in SECTIONS}


# ─── The avatars ──────────────────────────────────────────────────────────────

AvatarKey = Literal[
    "tanya",
    "tess",
    "tushar",
    "tara",
    "tanvi",
]

#: The face the strip starts on (``DEFAULT_AVATAR`` in ``frontend/src/roster.ts``),
#: and what a payload that named no face wears. Its voice is configured in
#: ``on_session_start`` before a word is spoken, exactly as a picked face's is.
DEFAULT_AVATAR: AvatarKey = "tanya"


@dataclass(frozen=True)
class AvatarIdentity:
    """One avatar, and the voice that goes with it.

    ``voice`` is the whole reason this table exists on the *brain* side. A face
    read as one gender speaking in the other is the first thing anyone notices, before a single nod is judged. Pairing it here, in the
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
        key="tanya",
        name="Tanya",
        renderer="2.5-D",
        blurb="The default here: a head built in Blender and rendered with three.js, on the library's own mixer and wire.",
        voice=Voice.KOKORO_AVA,
    ),
    AvatarIdentity(
        key="tess",
        name="Tess",
        renderer="2.5-D",
        blurb="American, and the first character built from a single supplied picture.",
        voice=Voice.KOKORO_SARAH,
    ),
    AvatarIdentity(
        key="tushar",
        name="Tushar",
        renderer="2.5-D",
        blurb="Built by copying Tara's build and changing only the face.",
        voice=Voice.OMNIVOICE_GAURAV,
    ),
    AvatarIdentity(
        key="tara",
        name="Tara",
        renderer="2.5-D",
        blurb="The first of the Blender characters, and the one the others were copied from.",
        voice=Voice.OMNIVOICE_GAURI,
    ),
    AvatarIdentity(
        key="tanvi",
        name="Tanvi",
        renderer="2.5-D",
        blurb="The first character whose hair is its own layer, drawn over the body rather than painted into it.",
        # A voice of her own rather than Tara's: two faces sharing one voice
        # read as one person in two drawings, and a face heard in the wrong
        # accent is noticed before anything the face does.
        voice=Voice.OMNIVOICE_GAYATRI,
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
    already open in front of the visitor rather than carrying all of them
    through every turn."""
    return "\n".join(f"- [{s.id}] {s.title}" for s in SECTIONS)


# ─── Background the model answers from ────────────────────────────────────────
#
# Facts a visitor asks for that no section carries. Short, because a voice answer
# is two sentences and a prompt that offers ten paragraphs gets five of them read
# aloud.

BACKGROUND = """\
FACTS ABOUT THE LIBRARY — answer from these, and say you are not sure if it is not here:
- It is called voqalize/avatar. MIT-licensed, on GitHub, and published as @voqalize/avatar on npm and voqalize-avatar on PyPI. The two are ends of one wire format; they version separately and the wire is what keeps them compatible.
- It is a face drawn in the browser. There is no video track — the face rides the data channel the call already has open, at a few hundred bytes a second.
- The backend half is one pipecat frame processor. It sits right after text-to-speech, and from there it sends the state it infers and the mouth shapes for the audio about to play. Turning audio into mouth shapes is a little CPU work inside that pipeline, so there is no new service to run or pay for.
- The browser half is one mount call, given the pipecat client you already connected with.
- It works with any pipecat pipeline. Voqalize is one user of it, not the only one.
- The avatars that ship are line-art faces and 2.5-D characters rendered with three.js — Tara, Tushar, Tanya, Tess and Tanvi. All of them are in the one npm package. This page's strip shows only the 2.5-D characters. Anyone can ship their own: an avatar is any module that exports createAvatar.
- Tanya, the face this page opens on, is a 2.5-D character. Her code is MIT like the rest of the library; the character binary the browser loads is artwork, under CC-BY 4.0. A face like hers starts from one picture, which is turned into a 2.5-D model in Blender; the backend stays the same and only the file the browser loads changes.
- HeyGen, Anam, Protoface, Simli and Tavus are video avatar services with pipecat integrations. They also sit right after text-to-speech, but they send the speech audio to their own servers, render video of a face, and send that video and the audio back through the transport — so each call carries a video stream and one more hosted service. This library sends the browser a few small instructions and the browser draws the face. Be fair about it: they produce photoreal video, and this does not.

FACTS ABOUT THIS CALL:
- Your voice, your ears and this call's audio are Voqalize. You are a brain: a WebSocket on the other side of it, holding the model, the prompt and these tools.
- The face you are wearing is driven by the open-source library's mixer and wire, over this call's data channel.
"""
