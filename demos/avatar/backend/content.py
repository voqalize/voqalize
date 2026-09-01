"""What the avatar demo knows: the five slides, the nine avatars, and the
background the model answers from.

Kept out of ``brain.py`` because it is *content* — it is edited when the avatar
library changes, not when the conversation does, and those are two different
review conversations.

Everything here is about `voqalize/avatar` itself. The slides are the answer
surface for a technical question: the model brings one up and then answers with
the picture on screen, so a visitor who asks "how does the lipsync stay in
step?" gets the cue timeline drawn beside the sentence rather than instead of
it. The prose is written to be *spoken* — short clauses, no bullet grammar, no
symbols a synthesizer has to guess at.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from voqalize.sdk.wire import Voice

# ─── The slides ───────────────────────────────────────────────────────────────

SlideId = Literal["wire", "authority", "lipsync", "silence", "rig"]


@dataclass(frozen=True)
class Slide:
    """One slide. ``beats`` is what the page prints; ``notes`` is what the model
    reads before it speaks.

    Two fields rather than one because they are read by two different things at
    two different speeds. A slide is glanced at in about a second, so it carries
    five short lines; an answer is listened to, so it needs the sentences the
    lines were compressed out of.
    """

    id: SlideId
    title: str
    subtitle: str
    beats: tuple[str, ...]
    notes: str


SLIDES: tuple[Slide, ...] = (
    Slide(
        id="wire",
        title="Three commands, and nothing else",
        subtitle="What a server is allowed to say to a face",
        beats=(
            "claim — a durable state the face may adopt",
            "action — one self-completing behaviour",
            "cues — viseme letters on a timeline",
            "One RTVI server-message carries all three",
            "An unknown command is ignored, not versioned",
        ),
        notes=(
            "The whole server-to-avatar vocabulary is three commands. A claim is a "
            "durable candidate state — thinking, working, straining — and exactly one "
            "is in flight at a time, so a later claim replaces the earlier one. An "
            "action is a point-in-time behaviour that completes on its own and leaves "
            "no state behind: a greeting wave, a nod, a wait gesture. Cues are viseme "
            "letters with millisecond offsets, which is the mouth. All three ride one "
            "message on the data channel that is already open, under an envelope that "
            "says type avatar. There is no protocol version field: a command the "
            "browser does not recognise is ignored, so an old page and a new server "
            "still run a call."
        ),
    ),
    Slide(
        id="authority",
        title="Facts outrank claims",
        subtitle="Why the face cannot be told what is happening",
        beats=(
            "The browser owns what it observes",
            "Speaking, listening, muted — all facts",
            "A server claim sits underneath them",
            "A claim retires at any factual boundary",
            "The renderer never invents a reaction",
        ),
        notes=(
            "The precedence is deliberate and it runs one way. What the browser "
            "observes about the audio — that the bot started speaking, that the caller "
            "did, that the microphone is muted — is a fact, and it wins. A claim from "
            "the server is a candidate that sits underneath every fact, and it retires "
            "the moment one arrives. So a server can tell the face what to consider; it "
            "cannot tell it what is happening. Mute is the clearest case: the browser "
            "already knows, so there is no claim for it at all — a second, weaker "
            "spelling of a fact would only be a way to be wrong. The other half of the "
            "same rule is that the renderer never invents a reaction: every nod and "
            "every acknowledgement is an explicit action, because a face that agrees "
            "on its own will eventually agree with the wrong sentence."
        ),
    ),
    Slide(
        id="lipsync",
        title="The mouth is a timeline, not a command",
        subtitle="Two legs, one track, spliced in place",
        beats=(
            "A cue is time, letter, loudness",
            "Zero is the turn's first audio sample",
            "A fast leg guesses from the text",
            "An accurate leg splices in behind it",
            "from_ms says where to cut and repatch",
        ),
        notes=(
            "Cues are never a play-this-now command, and that is the design. Each cue "
            "is a time in milliseconds, a Rhubarb mouth letter from A to H, and "
            "optionally a loudness. Zero on that clock is the first audio sample of the "
            "turn, so arrival time carries no meaning at all — a patch can and usually "
            "does land before the audio it describes. Two legs write the same track. A "
            "fast leg predicts shapes from the text the moment there is text, so the "
            "mouth moves the instant audio starts. An accurate leg comes in behind it "
            "from the real waveform and splices: from_ms says discard the track at and "
            "after this offset, then append these. That one primitive is the whole "
            "correction mechanism, and if it is doing its job you never see the second "
            "leg arrive."
        ),
    ),
    Slide(
        id="silence",
        title="Most of a call is silence",
        subtitle="And a blank face reads as a dropped connection",
        beats=(
            "THINKING — a reply is outstanding",
            "WORKING — a tool is running",
            "STRAINING — nothing came back",
            "Inferred from frames where it can be",
            "Claimed by the brain where it cannot",
        ),
        notes=(
            "Listening and speaking are the easy states. Everything between them is "
            "inference, and getting it wrong is expensive: a face that goes blank while "
            "a model is mid-inference reads as a dropped connection, so idle is the "
            "wrong answer to almost all of the silence in a call. Three claims cover "
            "it. Thinking means a reply is outstanding. Working means a tool is "
            "running. Straining means nothing came back at all. The split is about who "
            "can see what: the pipeline arms thinking itself, because it watches the "
            "turn boundaries and knows a reply is owed. It cannot see a tool running "
            "inside a brain on the other side of a socket — so working is a claim the "
            "brain sends, and this demo sends it, out loud, when you ask it to dig "
            "something up."
        ),
    ),
    Slide(
        id="rig",
        title="Under the wire: a mixer, a rig, a drawing",
        subtitle="Where the motion actually comes from",
        beats=(
            "About thirty pose channels, layered",
            "Per-channel smoothing — the head lags 160 ms",
            "Blink, breath and gaze are never sent",
            "A face is a drawing, not a skin",
            "No build step: what you see is what ships",
        ),
        notes=(
            "Below the wire there are three layers. A mixer takes layered inputs — "
            "idle motion, gaze, a gesture clip, the mouth — and resolves them per "
            "channel. A rig takes about thirty pose numbers and applies them. A face is "
            "a drawing that consumes those numbers. The part worth knowing is the "
            "smoothing: every channel has its own time constant, and the head's is "
            "about a hundred and sixty milliseconds, so a clip's keyframes are authored "
            "already compensated for the lag they will pick up. Keyframes are not what "
            "the face does — the smoothing between them is. And blinking, breathing, "
            "gaze aversion and idle sway are the renderer's own; they are never sent by "
            "anybody, because a server that had to send a blink would be sending it "
            "late."
        ),
    ),
)

SLIDES_BY_ID: dict[str, Slide] = {slide.id: slide for slide in SLIDES}


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

#: The avatar the call opens on. `myna` is the line-art character the library
#: ships in its own demos, and it is the one drawing every rig change is checked
#: against — so the face a visitor meets first is the one under the most scrutiny.
DEFAULT_AVATAR: AvatarKey = "myna"


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
    """The roster as the model reads it — the bracketed key is the tool argument."""
    return "\n".join(f"- [{a.key}] {a.name} — {a.renderer}. {a.blurb}" for a in AVATARS)


def slides_for_prompt() -> str:
    """The slide index as the model reads it. The notes are NOT here: they arrive
    as the tool's return value, so the model reads them with the picture already
    on screen rather than carrying five of them through every turn."""
    return "\n".join(f"- [{s.id}] {s.title} — {s.subtitle}" for s in SLIDES)


# ─── Background the model answers from ────────────────────────────────────────
#
# Facts a visitor asks for that no slide carries. Short, because a voice answer
# is two sentences and a prompt that offers ten paragraphs gets five of them read
# aloud.

BACKGROUND = """\
FACTS ABOUT THE LIBRARY — answer from these, and say you are not sure if it is not here:
- It is called voqalize/avatar. MIT-licensed, on GitHub, and published as @voqalize/avatar on npm and voqalize-avatar on PyPI. The two are ends of one wire format and publish together.
- It is a 2-D talking head, drawn as vectors in the browser. There is no video track, no per-minute avatar vendor and no second media path — the face rides the data channel that is already open.
- The backend half is one pipecat frame processor. It sits between text-to-speech and the transport, and from that seat it publishes the state it infers and the visemes for the audio about to play.
- The browser half is one mount call. You give it the pipecat client you already connected with, and there is nothing else to configure.
- It works against any pipecat pipeline. Voqalize is one consumer of it, not the only one.
- Nine avatars ship today: three line-art faces and six painted ones. You can author your own — a face is a drawing plus a pose spec, and an avatar is any module that exports createAvatar.
- Backchannels — the small acknowledgements, "mm-hm", "one moment", a nod — were the part the brief called out as mattering most, because a face listens far more than it speaks.

FACTS ABOUT THIS CALL — the same again, for how you are being run right now:
- Your voice, your ears and this call's audio are Voqalize. You are a brain: a WebSocket on the other side of it, holding the model and the prompt and these tools, dialled once when the call started.
- The face you are wearing is the open-source library, driven over that same call's data channel.
- Voqalize is what you would use to put a voice on your own agent. The avatar library is free either way, and it is yours whether or not you ever use us.
"""
