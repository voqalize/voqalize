"""What the avatar demo knows: the documentation sections, the avatars on the
strip, and the background the model answers from.

Kept out of ``brain.py`` because it is *content* — it is edited when the avatar
changes, not when the conversation does, and those are two different
review conversations.

Everything here is about the Voqalize avatar itself. **The page holds the
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
        title="An avatar for your voice agent",
        notes=(
            "This is the avatar for Voqalize voice calls. "
            "Voqalize sends the mouth shapes and states on the call's data channel. "
            "The browser animates the face from them, in time with the audio. "
            "There is no video stream and no GPU. "
            "You install one small package from npm."
        ),
    ),
    Section(
        id="compare",
        title="Compared with video avatar services",
        notes=(
            "HeyGen, Anam, Protoface, Simli and Tavus stream video of a face. "
            "They send the audio to their servers and send video back. "
            "Voqalize sends the browser a few small instructions, and it draws me. "
            "So there is no extra service and no video stream. "
            "A different face is just a different character name. "
            "They look like real video. I do not."
        ),
    ),
    Section(
        id="quickstart",
        title="Add it to your page",
        notes=(
            "Voqalize already sends everything the face needs. "
            "Install the package from npm. "
            "Mount it with your pipecat client and a character name. "
            "If your page has a content security policy, allow the avatar host."
        ),
    ),
    Section(
        id="states",
        title="What the avatar shows between turns",
        notes=(
            "Speaking and listening come from the audio. "
            "Between turns, I show thinking, working, or that I cannot hear you. "
            "An idle face there can look like a dropped call. "
            "Voqalize knows when a reply is due, so it sends thinking. "
            "It cannot see a slow tool, so your brain sends working."
        ),
    ),
    Section(
        id="wire",
        title="Drive the avatar from your brain",
        notes=(
            "Your brain can send me a state or an action. "
            "A state is one I hold, like working. "
            "An action is a gesture that finishes by itself, like a wave. "
            "Prefer actions, because they never fight what the call is doing. "
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
            "The shapes come from the sounds the voice actually spoke. "
            "The mouth follows the audio your browser receives."
        ),
    ),
    Section(
        id="faces",
        title="Choose a face",
        notes=(
            "A character is a name you pass when you mount the face. "
            "The page downloads only the character it mounts. "
            "Each face here comes with its own voice, so you pick before the call. "
            "Blinks and breathing happen in the browser. Nobody sends them."
        ),
    ),
    Section(
        id="limits",
        title="Limits",
        notes=(
            "It is not photoreal video. "
            "It needs a Voqalize call; there is no standalone player. "
            "The page must be able to reach the avatar host. "
            "Without WebGL 2, you see a still picture instead."
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
        blurb="The default here, and the face on the Voqalize homepage and the legal demo.",
        voice=Voice.KOKORO_AVA,
    ),
    AvatarIdentity(
        key="tess",
        name="Tess",
        renderer="2.5-D",
        blurb="American, and the face of the servicing and travel demos.",
        voice=Voice.KOKORO_SARAH,
    ),
    AvatarIdentity(
        key="tushar",
        name="Tushar",
        renderer="2.5-D",
        blurb="The male face in the bank demo, beside Tara.",
        voice=Voice.OMNIVOICE_GAURAV,
    ),
    AvatarIdentity(
        key="tara",
        name="Tara",
        renderer="2.5-D",
        blurb="The face of the bank demo.",
        voice=Voice.OMNIVOICE_GAURI,
    ),
    AvatarIdentity(
        key="tanvi",
        name="Tanvi",
        renderer="2.5-D",
        blurb="The face of the kiosk demo.",
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
FACTS ABOUT THE AVATAR — answer from these, and say you are not sure if it is not here:
- It is the Voqalize avatar. The browser installs @voqalize/avatar from npm: a small MIT loader, given the pipecat client and a character name.
- The loader fetches the avatar runtime and the character from avatar.voqalize.com when the face mounts. They are Voqalize's, under their own licence, for use with Voqalize.
- It is a face drawn in the browser. There is no video track — the face rides the data channel the call already has open, at a few hundred bytes a second.
- Voqalize sends the avatar's state and the mouth shapes for every reply, in every call. There is nothing to install or run on the server side, and nothing extra to pay for.
- The mouth shapes come from the sounds the voice actually spoke, so they match the audio rather than a guess from the text.
- It needs a Voqalize call. It is not a standalone player, and it does not plug into other voice platforms.
- The characters are 2.5-D, rendered with WebGL 2 in the browser: Tanya, Tess, Tushar, Tara and Tanvi. A browser without WebGL 2 shows a still picture of the character.
- A page with a Content-Security-Policy has to allow avatar.voqalize.com, and blob: for the character's textures.
- HeyGen, Anam, Protoface, Simli and Tavus are video avatar services with pipecat integrations. They send the speech audio to their own servers, render video of a face, and send that video and the audio back through the transport — so each call carries a video stream and one more hosted service. Voqalize sends the browser a few small instructions and the browser draws the face. Be fair about it: they produce photoreal video, and this does not.

FACTS ABOUT THIS CALL:
- Your voice, your ears and this call's audio are Voqalize. You are a brain: a WebSocket on the other side of it, holding the model, the prompt and these tools.
- The face you are wearing is driven by the avatar messages Voqalize sends over this call's data channel, plus the gestures you play.
"""
