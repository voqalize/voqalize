"""What the avatar demo knows: the nine documentation sections, the ten
avatars, and the background the model answers from.

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
        title="A face for AI voice calls",
        notes=(
            "I am a face for AI voice calls. "
            "My lips follow the voice you hear. "
            "I listen while you talk, and look busy while I work. "
            "The library is free and open source. "
            "A developer adds me to a voice agent in a few lines."
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
            "So there is no new service, no video stream and no avatar bill. "
            "A new face starts from one picture, made into a 2.5-D model in Blender. "
            "The server side stays the same; only the browser's file changes. "
            "The fair trade: they look like real video, and I do not."
        ),
    ),
    Section(
        id="quickstart",
        title="Add it to a pipecat app",
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
            "Speaking and listening are easy. "
            "The hard part is the silence in between. "
            "A blank face there looks like a dropped call. "
            "So I show thinking, working or straining instead. "
            "The pipeline knows when a reply is owed. "
            "It cannot see a tool running in your brain, so you send working."
        ),
    ),
    Section(
        id="wire",
        title="Drive the avatar from your own code",
        notes=(
            "A server can say three things to me. "
            "A claim is a state to hold, like working. "
            "An action is a gesture that finishes by itself, like a wave. "
            "Cues are mouth shapes on a timeline. "
            "What the browser actually hears always beats a claim."
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
            "An accurate pass from the real audio then replaces it, unseen."
        ),
    ),
    Section(
        id="faces",
        title="Choose a face",
        notes=(
            "Nine faces are open source: three drawn and six painted. "
            "Tara is a tenth, a premium Voqalize face, and not open source. "
            "Each face comes with its own voice, so you pick before the call. "
            "Blinks and breathing happen in the browser. Nobody sends them."
        ),
    ),
    Section(
        id="custom",
        title="Ship your own avatar",
        notes=(
            "Any module that exports create avatar is an avatar. "
            "There is no registry to join. "
            "Redraw a shipped face in an afternoon. "
            "Or write your own renderer, in canvas, S-V-G or W-e-b-G-L. "
            "You get the same pose numbers the shipped faces get."
        ),
    ),
    Section(
        id="limits",
        title="What it does not do",
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
    "tara",
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

#: The face the strip starts on (``DEFAULT_AVATAR`` in ``frontend/src/roster.ts``),
#: and what a payload that named no face wears. Its voice is configured in
#: ``on_session_start`` before a word is spoken, exactly as a picked face's is.
DEFAULT_AVATAR: AvatarKey = "tara"


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
    #: False for a face whose code and artwork are proprietary. The model is told,
    #: because a face that claims to be MIT on npm when it is not is a promise
    #: the visitor will try to collect on.
    open_source: bool = True


AVATARS: tuple[AvatarIdentity, ...] = (
    AvatarIdentity(
        key="tara",
        name="Tara",
        renderer="premium 3-D",
        blurb="The default here, and not open source: a Voqalize premium avatar rendered with three.js on the library's own mixer and wire.",
        voice=Voice.OMNIVOICE_GAURI,
        open_source=False,
    ),
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
- It is a face drawn in the browser. There is no video track — the face rides the data channel the call already has open, at a few hundred bytes a second.
- The backend half is one pipecat frame processor. It sits right after text-to-speech, and from there it sends the state it infers and the mouth shapes for the audio about to play. Turning audio into mouth shapes is a little CPU work inside that pipeline, so there is no new service to run or pay for.
- The browser half is one mount call, given the pipecat client you already connected with.
- It works with any pipecat pipeline. Voqalize is one user of it, not the only one.
- Nine avatars ship: three line-art faces and six painted ones. Anyone can ship their own: an avatar is any module that exports createAvatar.
- Tara, the face this page opens on, is NOT one of the nine and NOT open source. She is a premium Voqalize avatar, rendered in 2.5-D with three.js on the library's own mixer and wire. Her code and artwork are proprietary. A face like hers starts from one picture, which is turned into a 2.5-D model in Blender; the backend stays the same and only the file the browser loads changes.
- HeyGen, Anam, Protoface, Simli and Tavus are video avatar services with pipecat integrations. They also sit right after text-to-speech, but they send the speech audio to their own servers, render video of a face, and send that video and the audio back through the transport — so each call carries a video stream and one more hosted service. This library sends the browser a few small instructions and the browser draws the face. Be fair about it: they produce photoreal video, and this does not.

FACTS ABOUT THIS CALL:
- Your voice, your ears and this call's audio are Voqalize. You are a brain: a WebSocket on the other side of it, holding the model, the prompt and these tools.
- The face you are wearing is driven by the open-source library's mixer and wire, over this call's data channel.
"""
