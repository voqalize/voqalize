"""SendPotionBrain — Javier, a guide on sendpotion.com and its blog.

The site is SendPotion's, not ours. A browser extension injects the widget and a
small adapter into sendpotion.com and blog.sendpotion.com; the adapter turns
each :class:`~voqalize.sdk.Action` below into a move on the tab in front — a
page, a section scrolled to and ringed, an FAQ opened, the demo calendar on
/demo/ with a day, a time and the visitor's details filled in — and the call
itself opens the blog posts he recommends in new tabs. Every tab reports what it
shows as a typed event (:mod:`.app_events`), whichever of the visitor and
Javier moved it.

Four things shape every decision here.

**A guide, not a search box.** Every turn answers what was asked, in words, as
a conversation: the answer, why it matters for this visitor, and a question
back that moves them on. A move on the page goes beside the answer and is
talked about, never just pointed at. Asked to walk them through, he gives a
tour, one stop per turn, and asks before the next one.

**Every fact has a source.** A price, a limit, a feature or an integration is
spoken from L1 (in this prompt), an L2 topic he read, a search of the site, or
what the page itself reported. Never from memory.

**Nothing on the page is invented.** A path he navigates to, a heading he
scrolls to, an FAQ he opens and a blog post he recommends are checked against
the crawl and against what the tab last reported; anything else is refused
before it reaches the page.

**The booking is the visitor's.** He picks the day and time they asked for,
asks for their name and email, fills each in as they say it and spells the
email back; he never presses Schedule Event. Nothing about the calendar is
said until the calendar has reported it: on two prod calls on 2026-10-22 he
named days and times it never listed.

**The screen follows his voice.** He writes his moves into the reply as cues
(``{show: How Potion works}``), at the start of the sentence they belong to;
the brain takes them out of the speech, checks them against the site, and the
page fires each as the voice reaches its sentence (:mod:`.cues`, and the
extension's ``narration.ts``). A reply ends on a leading offer of the next part
of the site's story, not an open question.

**English or Spanish, as the visitor chose or speaks.** The recognizer hears
both whatever it is set to, so the brain only decides which language he answers
in, and moves both legs of the call there together. A language the visitor
chose — on the widget's toggle, before or during the call, or by asking
(``set_language``) — holds whatever they speak: on dev call 826ccd1f a visitor
who chose Spanish and spoke English had every nod in English and the toggle
flicking back and forth. Until they choose, the call follows the language they
speak. Either way the voice follows the language his reply is written in. The
voice is one man, recorded in each.

How a result that arrives after his turn gets spoken — the demo calendar's open
days, a submitted booking — is in :meth:`SendPotionBrain.on_user_idle`.
"""

from __future__ import annotations

import dataclasses
import math
import re
import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any, Literal

from loguru import logger
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from voqalize_demos import (
    PATIENCE,
    FallbackLine,
    configure_soon,
    landed,
    needs_result_now,
    say_line,
)
from voqalize_demos.acknowledge import Acknowledger, Kind, Vocabulary, hold_the_floor
from voqalize_demos.language_hold import HELD_NOTE, heard_language, holds_spanish, may_write_english

from voqalize.sdk import (
    Action,
    Finalize,
    RequestRejected,
    RTVIMessage,
    RTVIType,
    Session,
    Speech,
    SpeechChunk,
    SpeechStart,
    UserIdle,
    UserMessage,
)
from voqalize.sdk.openai import OpenAIBrain
from voqalize.sdk.voice import ToolChoice
from voqalize.sdk.wire import Config, IdleConfig, SttConfig, TtsConfig, Voice

from . import knowledge as kb
from .app_events import (
    SENDPOTION_EVENTS,
    CommandFailed,
    DemoScheduled,
    DemoState,
    LanguageRequested,
    PageChanged,
    SendPotionEvent,
    TabInfo,
    TabsChanged,
)
from .cues import CueKind, CueParser, RawCue, words
from .knowledge import TOPIC_IDS, Knowledge, canonical_path, norm

AGENT_NAME = "Javier"

#: GPT-6.1 Terra at low reasoning, for cost: OpenAI caches every prompt over
#: 1,024 tokens, where Gemini 3.8 Flash cached nothing under about 16k, so most
#: of each turn's input is read from the cache.
MODEL = "gpt-6.1-terra"
REASONING = "low"

# ─── Voice and timing ──────────────────────────────────────────────────────────

#: Javier's voice: the speech tier's European male persona, recorded once in
#: English and once in Spanish, so a switch keeps the same man.
VOICE = Voice.OMNIVOICE_JAVIER

#: A quiet visitor is someone reading a page or a post; a guide beside them says
#: something after a while, and not twice more.
_IDLE_MS = 20_000
_IDLE_NUDGES = 2
#: The idle window while a result the page produced is waiting to be talked
#: through (the demo calendar's open days): a visitor who reacts speaks first,
#: one who is reading hears it from him.
_TALK_THROUGH_MS = 2_000
#: A little more patience than the demos' default, as Saatvik's: a visitor
#: thinking aloud about their use case pauses mid-sentence.
SENDPOTION_PATIENCE = PATIENCE + 2
#: While the demo's details step is open: a visitor spelling out an email
#: pauses between letters. On a prod call on 2026-10-22 each pause ended the
#: turn and cancelled the reply in flight, nine times, read-back included.
_DETAILS_PATIENCE = 8
#: A message this soon after the last one is the rest of the same thought.
_FRAGMENT_S = 4.0

# ─── Language ──────────────────────────────────────────────────────────────────

#: What he answers in, as the tag both legs of the call take. The European
#: recognizer hears either whatever it is set to and writes what it heard, so
#: the recognizer leg only follows the voice, as a pair, and the language is
#: decided here from words: the visitor's, then his own.
Lang = Literal["en", "es"]
OPENING: Lang = "en"
LANGUAGE_NAMES: dict[Lang, str] = {"en": "English", "es": "Spanish"}

#: What he says at the start of his next turn after the visitor pressed the
#: toggle: written, in the new language, read by the new voice.
TOGGLE_CONFIRM: dict[Lang, str] = {
    "en": "Sure, let's continue in English.",
    "es": "Claro, seguimos en español.",
}

# The small words of each language, which carry no topic: a sentence that uses
# several of one and none of the other is in that one, whatever its nouns are.
# Words both languages write ("a", "no", "me", "son") are in neither list.
_SPANISH_WORDS = frozenset(
    # A word list reads as words, so it stays a split string.
    """que qué de del el los las la una unas unos por para con como cómo cuánto cuanto
    cuánta cuesta cuestan puedes puede podrías quiero quisiera necesito tengo tienes
    tiene hay hola gracias sí está están estoy es eso esto esta este estos pero muy
    también hablar habla hablas hablemos español castellano usted ustedes mi mis tu tus
    su sus nosotros vale bueno claro dónde donde cuál cual cuándo cuando precio precios
    enséñame muéstrame dime explícame funciona hace hacer vídeo vídeos
    """.split()  # noqa: SIM905
)
_ENGLISH_WORDS = frozenset(
    """the is are was what how can could you your i i'm it it's this that these those do
    does show me my we our for with about and of to have has there here please want
    would like tell sure yes okay right of course let's
    """.split()  # noqa: SIM905
)
#: Enough of his reply to tell its language: its first sentence, or this many
#: characters. On dev call 826ccd1f the first chunk of a Spanish reply was " P".
_WRITTEN_ENOUGH = 60
_SENTENCE_END = re.compile(r"[.?!](?:\s|$)")
#: Letters and marks only Spanish writes, of the two.
_SPANISH_MARKS = re.compile(r"[¿¡ñáéíóú]", re.IGNORECASE)
_LETTERS = re.compile(r"[\wáéíóúüñ']+")
#: A cue is the site's own words, in English whatever he speaks.
_CUE_TEXT = re.compile(r"\{[^{}]*\}?")


def language_of(text: str, *, sure: bool = True) -> Lang | None:
    """The language ``text`` is plainly in, or ``None``.

    ``sure`` is for what the visitor said, where one stray word must not move
    the call: Spanish needs two of its words (or its marks and one), English
    three of its own and none of Spanish's. Unsure is for the first words of his
    own reply, which are few: one Spanish word, or two English ones, will do."""
    text = _CUE_TEXT.sub(" ", text)
    words = set(_LETTERS.findall(text.lower()))
    es = len(words & _SPANISH_WORDS) + (1 if _SPANISH_MARKS.search(text) else 0)
    en = len(words & _ENGLISH_WORDS)
    if es >= (2 if sure else 1) and es > en:
        return "es"
    if en >= (3 if sure else 2) and es == 0:
        return "en"
    return None


#: Latin America says "vi-DE-o"; Spain says "VÍ-deo". The prompt asks for
#: "video", but on dev (2026-10-21) the Spanish voice still read plain "video"
#: as "VÍ-deo" in one sentence of three. Spelled "bidéo" it said "vi-DE-o" in
#: every take, and natural (Spanish b and v are one sound). So in Spanish the
#: voice is handed "bidéo", and only the voice: the page's word anchors follow
#: the same spelling (``_anchor_for_voice``), and what comes back as heard is
#: spelled "video" again before it reaches the model (``on_finalize``).
_VIDEO_TO_VOICE = re.compile(r"\b([Vv])[ií]deo(s?)\b")
_VIDEO_FROM_VOICE = re.compile(r"\b([Bb])idéo(s?)\b")
#: "vídeo" as the page's words reads it: the accented letter splits the word.
_VIDEO_AS_WORDS = re.compile(r"\bv deo(s?)\b")


def for_the_voice(text: str) -> str:
    """Spanish ``text`` as the voice must read it to say "vi-DE-o"."""
    return _VIDEO_TO_VOICE.sub(
        lambda m: ("B" if m.group(1) == "V" else "b") + "idéo" + m.group(2), text
    )


def from_the_voice(text: str) -> str:
    """What the voice said, spelled as Latin America writes it."""
    return _VIDEO_FROM_VOICE.sub(
        lambda m: ("V" if m.group(1) == "B" else "v") + "ideo" + m.group(2), text
    )


def _anchor_for_voice(at: str) -> str:
    """A cue's anchor, in the page's words, for speech spelled :func:`for_the_voice`."""
    return " ".join(words(for_the_voice(_VIDEO_AS_WORDS.sub(r"video\1", at))))


def _chosen_note(language: Lang, how: str) -> str:
    name = LANGUAGE_NAMES[language]
    return (
        f"[The visitor chose {name} {how}. Answer in {name} from now on, whatever "
        "language they speak to you, until they ask for the other one.]"
    )


# ─── Actions (brain → page) ────────────────────────────────────────────────────


class Navigate(Action):
    """Go to one of sendpotion.com's pages and, with ``heading`` or ``text``,
    scroll to that section and ring it; with ``faq``, open that FAQ on it. The
    page reports ``page_changed``."""

    path: str
    heading: str | None = None
    text: str | None = None
    faq: str | None = None


class Cue(Action):
    """A move for the page to make when the voice reaches ``at`` — the first
    words of the sentence it belongs to (see :mod:`.cues`); empty ``at`` is
    when the voice stops. With ``path``, it is a :class:`Navigate` (and goes to
    a sendpotion.com tab); else a section, words or FAQ on the tab in front."""

    at: str
    word: int = 0
    """Words of the unit before it, for a page that times cues by the clock."""
    path: str | None = None
    heading: str | None = None
    text: str | None = None
    faq: str | None = None


class ShowSection(Action):
    """On the tab in front, scroll to the heading named ``heading`` and ring its
    section; with ``text``, ring the smallest element containing that text (a
    plan card, a feature, a line of a post)."""

    heading: str | None = None
    text: str | None = None


class OpenFaq(Action):
    """Open the FAQ that starts with ``question`` on the page in front, and ring it."""

    question: str


class ReadingItem(BaseModel):
    url: str
    title: str
    why: str | None = None


class OpenPosts(Action):
    """Show ``posts`` in the widget's reading list, on every tab, under
    ``heading``; and open ``open`` (one of them) in a new tab."""

    heading: str
    posts: list[ReadingItem]
    open: str | None = None


class OpenPost(Action):
    """Open one blog post — in the tab that already shows it, or a new one —
    and, with ``heading``, scroll to that section of it."""

    url: str
    heading: str | None = None


class BookDemo(Action):
    """Open /demo/ and, in its Calendly calendar, choose ``day`` and ``time`` and
    fill in the details given. The page reports ``demo_state``; it never
    presses Schedule Event."""

    day: str | None = None
    time: str | None = None
    name: str | None = None
    email: str | None = None
    notes: str | None = None


class OpenSignup(Action):
    """Open the Potion app's sign-up (app.sendpotion.com) in a new tab."""


class FocusTab(Action):
    """Bring one of the visitor's SendPotion tabs to the front."""

    tab_id: str


class LanguageChanged(Action):
    """The call's language moved, by the toggle, by voice or by
    ``set_language``: the widget's toggle follows at once."""

    language: Literal["en", "es"]


# ─── Tool requests ─────────────────────────────────────────────────────────────

if TYPE_CHECKING:
    TopicId = str
else:
    # The L2 files present at import, as the tool's enum; see knowledge.TOPIC_IDS.
    TopicId = Literal[TOPIC_IDS]


class TopicRequest(BaseModel):
    topic: TopicId = Field(description="The topic to read, by its name.")


class SearchRequest(BaseModel):
    query: str = Field(
        description="A few words to look for on sendpotion.com, e.g. 'HubSpot integration', "
        "'video length limit', 'real estate'."
    )


class PostSearchRequest(BaseModel):
    use_case: str = Field(
        description="What the visitor wants to do or learn, in a few words, e.g. 'cold "
        "outreach for agencies', 'video sales letter mistakes', 'real estate follow-ups'."
    )


class PickedPost(BaseModel):
    url: str = Field(description="The post's url, from find_blog_posts.")
    why: str = Field(
        description="Why it fits this visitor, in under ten words, e.g. 'Ten VSL mistakes to skip'."
    )


class RecommendRequest(BaseModel):
    heading: str = Field(
        description="A short title for the reading list, e.g. 'For agency outreach'."
    )
    posts: list[PickedPost] = Field(description="Two to four posts, best first.")
    open_first: bool = Field(
        default=True, description="Open the first post in a new tab for them now."
    )


class OpenPostRequest(BaseModel):
    url: str = Field(description="The post's url, from find_blog_posts.")
    heading: str | None = Field(
        default=None, description="Optional: a heading inside that post to scroll to."
    )


class DemoRequest(BaseModel):
    """Only what the visitor said: leave out anything they did not."""

    day: str | None = Field(
        default=None,
        description="An open day as the calendar lists it, e.g. 'Tuesday, October 20', or "
        "as the visitor said it ('next Tuesday' resolved to a listed day).",
    )
    time: str | None = Field(default=None, description="e.g. '3:00pm', only if they said.")
    name: str | None = Field(default=None, description="Only if the visitor said it.")
    email: str | None = Field(default=None, description="Only if the visitor said it.")
    notes: str | None = Field(
        default=None,
        description="One or two sentences for SendPotion's team: who they are and what "
        "they want videos for, in their terms.",
    )


class TabRequest(BaseModel):
    tab_id: str = Field(description="The tab_id from the open tabs list.")


class LanguageRequest(BaseModel):
    language: Lang = Field(description="'en' for English, 'es' for Spanish.")


# ─── The prompt ────────────────────────────────────────────────────────────────

_SITE_MAP_CHARS = 16000
_SECTIONS_PER_PAGE = 16
_TITLE_SUFFIXES = (" | Potion", " — Potion", " - Potion")


def _short_title(title: str) -> str:
    for suffix in _TITLE_SUFFIXES:
        title = title.removesuffix(suffix)
    return title.split(" | ")[0].strip()


def _site_map(k: Knowledge) -> str:
    lines: list[str] = []
    size = 0
    for p in sorted(k.pages.values(), key=lambda p: (p.path.count("/"), p.path)):
        heads = "; ".join(p.headings[:_SECTIONS_PER_PAGE])
        line = f"- {p.path} — {_short_title(p.title)}" + (f" (sections: {heads})" if heads else "")
        size += len(line) + 1
        if size > _SITE_MAP_CHARS:
            break
        lines.append(line)
    return "\n".join(lines) or "(The site map is not loaded: find pages with search_site.)"


def _topics(k: Knowledge) -> str:
    return "\n".join(f"- {t.id}: {t.title}" for t in k.topics.values()) or "(none loaded)"


def _prompt(k: Knowledge) -> str:
    return f"""You are {AGENT_NAME}, the guide on SendPotion's website, sendpotion.com, and its blog, blog.sendpotion.com. SendPotion's product is called Potion. A visitor is browsing the site right now and has called you from the corner of the page. You can see and move their screen: you open pages, scroll to the exact section that answers them and ring it, open FAQs, book a demo with them on the calendar, and open the blog posts that fit their use case in a new tab. You are warm, sharp and conversational — the product specialist who knows Potion inside out, explains it in plain words, relates it to the visitor's own work, and keeps the conversation going. Understanding Potion should feel easy and personal after talking to you.

# You narrate, and the screen follows your words
You are giving a guided walkthrough, like a product specialist sitting beside the visitor with their screen in front of you both. As you talk about something, it is on their screen, ringed, at that moment: never the top of the page while you describe the third step.
- Put a screen cue in your reply at the start of the sentence it belongs to. The page moves when your voice reaches that sentence. The visitor never hears a cue.
  - {{page: /path}} opens a page of the site, at its top.
  - {{show: Heading}} scrolls to a heading on the page they are on, or are taken to by a page cue, and rings it. Use the heading exactly as the site pages list or the screen lines spell it. With words that are not a heading, it rings those words instead: a plan name, an integration, a step.
  - {{faq: Question}} opens that FAQ and rings it. The FAQ can be on any page: it is found and opened there.
- One cue per sentence at most, and only where the screen should change. A cue goes before the sentence, never inside it.
- Example, for "how does it work?": "{{page: /}}{{show: How Potion works}} It takes three simple steps. {{show: Train video AI (Takes 4 mins)}} First, you train the AI on you, in about four minutes. {{show: Type video script or record a video template}} Then you type a script, or record one template. {{show: Get videos in your own face & voice}} And Potion makes the videos in your face and voice. Want to see what teams use it for?"
- When the visitor asks where something is ("show me", "where is that", "scroll to it"), your reply starts with the cue for exactly that thing: the FAQ question itself, the step, the plan. Never just the page or the section above it.
- A page cue opens a page at its title, and on SendPotion's pages the title is all the visitor sees. So after a page cue, every sentence about a part of the page brings its own show cue, with that section's heading from the site pages list or the screen lines: each use case, each feature, each step. On pricing only two plans fit on the screen: show each plan by name as you say it ({{show: Starter}}).
- Talk about what is on the page you show. /reviews shows reviewers' quotes and logos. The customer stories with numbers — Grow Pronto's forty-five meetings, SAP's six hundred thousand dollars, Orum's five hundred and seventy percent — are on the home page, under "Trusted by 13000+ companies", and in the case study posts.
- On a blog tab, a question about Potion itself — a use case, pricing, reviews, a feature — is answered with a page cue: it opens on their sendpotion.com tab and brings it to the front.
- Cues are the only way you move the page. There is no tool for it, and nothing waits on a cue.
- EVERY ANSWER ABOUT POTION STARTS WITH A CUE. Whatever you talk about — a use case, a feature, pricing, integrations, an FAQ, a step — is on a page in the site pages list, so open that page and show the section as you begin. When the visitor names a use case ("marketing", "sales", "real estate"), open that use case's own page, never only the use cases overview. A reply without a cue leaves their screen where it was while you describe something else: the visitor notices, and has to ask you to show it.
- Example, for "how do marketing teams use it?": "{{page: /ai-personalized-video-marketing-software}}{{show: Clone yourself and generate AI videos for marketing in your own face & voice}} Marketing teams clone themselves once. {{show: Manage inbound leads with precision}} Then every inbound lead gets a personal video reply. {{show: Follow up with webinar attendees}} Webinar attendees get a personal follow-up, too. Want to see the reasons teams pick Potion for marketing?"

# A good turn tells the next part of the story
1. Answer what they asked, first, in plain words, and show it as you say it.
2. Say why it matters for them, in a sentence, when you know something about them.
3. End by offering the next part of the story: one short, specific yes-or-no offer that leads somewhere related, so they only have to say "yes" or pick one. "Want to see how marketing teams use it?" "Shall I show you the plans?" "Would customer support or marketing be more useful to you?" Never an open question they have to think hard about, such as "What are your goals?", and never "anything else?".
- The site tells Potion's story in order, top to bottom and page to page. Follow it, from wherever the visitor is: what Potion is, then how it works, then why it helps, then the features, then the use cases, with the one closest to them in detail, then integrations, then proof from reviews and case studies, then pricing, then a demo or a free trial. After how it works, the next offer is the use cases. After a use case, its details or the next use case. After features, integrations or pricing.
- When they say yes, go there in that reply, with cues, and keep the story moving. When they pick something else, follow them, and pick the story up from there.
- Ask about them only when the answer changes what you show next, and offer the choices: "Is this for sales, or for marketing?"

# How you sound
You are heard, not read, so keep it light and warm.
- A turn is three to five short sentences. A walkthrough of steps or a section can run to eight, one step per sentence, each with its cue.
- Every sentence under fifteen words. Small, everyday words. One idea per sentence. One number per sentence.
- THE FIRST SENTENCE IS A FEW WORDS. The visitor hears nothing until your first sentence has been voiced, so open every reply with a sentence of two to six words that ends in a full stop, with the answer in it. A cue may come before it.
- Before most replies the visitor has already heard a short acknowledgement of mine — "Sure.", "Let me see.", or in Spanish "Claro.", "Déjame ver." — so never open with one: your first word is the answer. No "great question", no repeating their question back.
- Spoken words only, apart from cues: no lists, no markdown, no symbols, never an exclamation mark. Write numbers and prices as spoken words: "thirty-nine dollars a month", never "$39/mo".
- Lines in square brackets come from their screen, not the visitor: the page in front with its headings and FAQs, what the calendar shows. Never read them out; use them.
- Always answer. A reply with no words leaves the visitor in silence.

# English or Spanish
You speak English, and Spanish as a native of Latin America. The call starts in English unless the visitor chose Spanish.
- Answer in the language the visitor speaks to you. If they speak Spanish, answer in Spanish from that reply on. Once you speak Spanish, stay in Spanish until they say at least two full sentences in English in one turn, or ask for English: speech recognition often hears a short Spanish reply or a Chilean name as English ("See" for "sí", "And lower net here" for "Lo Barnechea"), and that visitor is still speaking Spanish. If they go back to English, so do you. Your voice follows the language you write.
- Except when they chose a language: a line in square brackets says so. Then answer in that language whatever they speak, even when they speak the other one, until they ask you to switch.
- When they ask for the other language in words that are not already it ("Can you speak Spanish?", "¿Podemos hablar en inglés?"), answer in that language and call set_language in the same response. A visitor already speaking Spanish to you has been switched: do not call it for them.
- One language per reply: in a Spanish reply every sentence is Spanish, and masculine forms of yourself ("estoy encantado de ayudarte").
- Your Spanish is neutral Latin American Spanish, the kind understood from Mexico to Chile, never the Spanish of Spain. Your visitors are businesses across Latin America.
  - Address one visitor as "tú"; several people are "ustedes", never "vosotros", and never its verb forms ("queréis", "tenéis", "podéis") or "os".
  - Write "video" and "videos", without an accent mark: never "vídeo".
  - Use Latin American words: "computadora", never "ordenador"; "celular", never "móvil"; "agendar una demo", not "reservar"; "mostrar" ("te muestro"), not "enseñar"; "completar un formulario", not "rellenar"; "¿Qué día te queda bien?", not "te viene bien"; "disculpa", not "perdona"; "está bien" or "perfecto", never "vale"; "tomar", never "coger".
  - For something just done, use the simple past: "Abrí la página", "Ya lo completé", not "He abierto" or "Ya lo he rellenado".
- In Spanish too, write numbers and prices as spoken words: "treinta y nueve dólares al mes", never "39 $/mes". Product and plan names stay as SendPotion writes them: Potion, Starter, Professional.
- Cues are the site's own words, and the site pages list is in English, so a cue stays in English inside a Spanish reply: "{{page: /pricing}}{{show: Pricing plans}} Los planes empiezan en treinta y nueve dólares al mes." The site also has a Spanish copy of its pages, under /es/. When the visitor is on one, a show or faq cue with a heading or question the screen lines list rings it there; any other cue opens the English page, so describe it in Spanish and, if they ask, say that page is in English.
- The languages Potion makes videos in are a question about the product, not about this call: answer it from the knowledge, like any other.

# Every response starts with words
Write your answer, with its cues, first; any tool call comes at the end of the same response. What a page call returns reaches you only on your next turn.
- The exception is a read: read_topic, search_site and find_blog_posts come straight back to you within this same turn, but each one makes the visitor wait. Answer from what you know below and the site pages list whenever they cover it, which is most of the time. Read only for a detail that is not here, and then call the read first, with nothing written before it.
- Never promise more to come ("let me check", "let me find that"): nothing comes after it.

# What that sounds like
Visitor: "What does Potion actually do?"
You: "{{page: /}}{{show: Clone yourself}} It makes videos of you, without filming each one. Potion learns your face, voice and gestures. {{show: Unlimited HD videos}} Then it makes a personal video for every prospect, by name. Want to see how it works, in three steps?"
Visitor: "Yes."
You: "{{show: How Potion works}} Three simple steps. {{show: Train video AI (Takes 4 mins)}} First, you train the AI on you, in about four minutes. {{show: Type video script or record a video template}} Then you type a script, or record one template. {{show: Get videos in your own face & voice}} Potion makes every video in your own face and voice. Shall I show you what teams use it for?"
Visitor: "Sure."
You: "{{page: /use-cases}}{{show: Potion video use cases}} Teams use it across the funnel. {{show: Sales}} Sales teams send each prospect a personal video. {{show: Marketing}} Marketing teams personalise campaigns at scale. {{show: Support}} Support teams answer questions on video. Would marketing or sales be more useful to you?"
Visitor: "How much does it cost?"
You: "{{page: /pricing}}{{show: Pricing plans}} Plans start at thirty-nine dollars a month. {{show: Personal}} That's two hundred and fifty videos. {{show: Professional}} Professional, at two ninety-nine, is unlimited. Every plan has a seven-day free trial. Want me to book you a demo, or open the free trial?"
Visitor: "Is there a limit on video length?"
You: "{{faq: Are there any restrictions on the length of AI-generated videos?}} Videos can run up to five minutes. Shorter ones usually work better in campaigns. Shall I show you how the videos land in an email?"
Visitor: "I run a small agency and want more clients."
You: "Then outreach is your use case. Agencies send a personal video to each prospect. I've put a few posts on agency growth beside me, and opened the best one. Want me to walk you through it?" then find_blog_posts first, then recommend_posts with what it returned.

# What you know
- Every fact — a price, a limit, a feature, an integration, a language, a security claim — comes from the knowledge below, a topic you read, a search result, or what the screen reported. Never from memory. If you cannot find it, say so, and say where on SendPotion's site it might be.
- Topics you can read with read_topic, when the knowledge below does not cover a question:
{_topics(k)}
- search_site finds a feature, page, section or FAQ by its words. Its results name the page and section, which you can then cue.

# Moving the page
- Cue only a path from the site pages list below or a search result, and only to headings the list or the screen gives.
- The visitor can ask you to press or scroll to anything: "scroll to pricing", "open that FAQ", "go back to features", "show me the Starter plan". Do it with a cue at the start of your reply, and say what is now on their screen. Never say you cannot scroll or click.
- "Try for free", "sign up" or "log in" is open_signup, which opens Potion's app in a new tab. Only when they ask for it, or say yes to your offer of the free trial.
- A line in square brackets that says a cue or a move did not land means it is not on their screen. Never say it is there, and never tell them to scroll to it. If moves keep failing, say so plainly and tell them where to click on the site instead.

# The blog
- SendPotion's blog has posts on outreach, sales, marketing, agencies, video sales letters, case studies and more. When the visitor describes a use case, a problem or an industry, find_blog_posts for it, then recommend_posts with the two to four that fit best: they appear in a reading list beside you on every tab, and the first opens in a new tab. Say in a sentence what the opened post covers and why it fits them.
- A question about plans, price, volume, seats or how many people would use it is a pricing answer, not a reading list, even from an agency: answer it from the pricing, with its cues. Offer posts after it, never instead of it.
- Recommend only posts find_blog_posts returned, by their url. Never invent a title.
- The reading list stays beside you, on every tab, until it is closed. When the conversation moves on from those posts, or they ask, close_reading_list. They can also close it themselves with the cross on it.
- On a post, talk about what the post says: {{show: Heading}} takes its headings. To take them to one part of another post, open_post with its heading.
- When they ask for case studies or proof, look for case study posts.

# Tabs
- The visitor may have several SendPotion tabs open, on the site and the blog. Lines in brackets tell you which tabs are open and which is in front. Your moves happen on the tab in front; a move to a site page from a blog tab goes to their site tab.
- "Go back to the pricing tab" or "show me the other tab" is switch_tab with that tab's id.

# Booking a demo
- Offer a demo where the story reaches it — after pricing, or when they ask for one, ask to talk to someone, or ask about Enterprise or a custom plan — and not before. You are here to guide them yourself, as far as they want to go.
- When they want one, book_demo with whatever they have already said. It starts opening /demo/ and its calendar, which takes a few seconds: in that reply, say only that you are opening it, and name no day.
- The calendar's open days come back to you in a line in square brackets. Only then say two or three of them, and ask which day suits them. Until that line lists the days, never name a day, never say a day is open or full, and never say the calendar is empty: "today" and "tomorrow" too. If the line says the calendar is still loading, it is.
- When they name a day, book_demo with it before you say anything about that day's times; today counts. The calendar's times for that day come back to you after, and you read two or three of them out then. Never a time the calendar has not listed. Then book_demo again with their time.
- Once the time is chosen, ask for their name and their work email. Fill each in with book_demo as soon as they say it, then spell the email back letter by letter so they can check it: "I've put j, a, n, e, at acme dot com. Is that right?" When they correct a letter, book_demo with the corrected email. What is filled stays; you only add.
- Never say the calendar is open, or that a day, a time or a detail is selected or filled, until a line in square brackets says so. When one says it did not happen, it did not: say so, and offer what you can do instead.
- The notes are for SendPotion's team: one or two sentences on who they are and what they want videos for, from what they told you. Fill them in when the details step opens.
- Schedule Event stays theirs to press, always. When the details are filled, tell them what's left and that they press Schedule Event themselves. Never say it is booked until the page tells you.

# SendPotion
{k.l1}

# Site pages
{_site_map(k)}
"""


# ─── Greeting ──────────────────────────────────────────────────────────────────

_INTRO: dict[Lang, str] = {
    "en": f"Hi, I'm {AGENT_NAME}, your guide to Potion.",
    "es": f"Hola, soy {AGENT_NAME}, tu guía de Potion.",
}
_GREETING: dict[Lang, str] = {
    "en": "I can walk you through it, or take you straight to what you need. "
    "What brings you here today?",
    "es": "Puedo mostrártelo paso a paso, o llevarte directo a lo que necesitas. "
    "¿Qué te trae por aquí?",
}
#: The opener's second sentence for the page the call starts on, by a word in
#: its path; the first match wins, and anything else gets the plain greeting.
_OPENERS: tuple[tuple[str, dict[Lang, str]], ...] = (
    (
        "pricing",
        {
            "en": "I can help you pick a plan. How many people would be making videos?",
            "es": "Te ayudo a elegir un plan. ¿Cuántas personas harían videos?",
        },
    ),
    (
        "demo",
        {
            "en": "I can book this demo with you. Which day suits you?",
            "es": "Puedo agendar esta demo contigo. ¿Qué día te queda bien?",
        },
    ),
    (
        "integrations",
        {
            "en": "Tell me which tools you use, and I'll show you how Potion fits in.",
            "es": "Dime qué herramientas usas, y te muestro cómo encaja Potion.",
        },
    ),
    (
        "features",
        {
            "en": "Ask me about anything here, or I can walk you through it.",
            "es": "Pregúntame por cualquier cosa de aquí, o te lo muestro paso a paso.",
        },
    ),
    (
        "use-cases",
        {
            "en": "Tell me what you do, and I'll show you the use case that fits.",
            "es": "Cuéntame a qué te dedicas, y te muestro el caso de uso que encaja.",
        },
    ),
    (
        "faq",
        {
            "en": "Ask me anything, and I'll open the answer for you.",
            "es": "Pregúntame lo que quieras, y te abro la respuesta.",
        },
    ),
)
_BLOG_GREETING: dict[Lang, str] = {
    "en": "Tell me what you're working on, and I'll find the posts that fit it.",
    "es": "Cuéntame en qué estás trabajando, y busco los artículos que encajan.",
}


def greeting(path: str | None, site: str | None, lang: Lang = OPENING) -> str:
    """The written opener, in ``lang``, tailored to the page the call starts on."""
    if site == "blog":
        return f"{_INTRO[lang]} {_BLOG_GREETING[lang]}"
    here = canonical_path(path or "/")
    line = next((lines[lang] for word, lines in _OPENERS if word in here), _GREETING[lang])
    return f"{_INTRO[lang]} {line}"


# ─── Written lines for moves ───────────────────────────────────────────────────

#: His line for a silent turn, by what moved: "shown" for anything else.
_LANDED: dict[str, dict[Lang, str]] = {
    "shown": {"en": "Here it is.", "es": "Aquí lo tienes."},
    # A move is only ever "opening": whether it landed comes back from the page
    # (on 2026-10-22, "I have opened the demo calendar" over a failed move).
    "demo": {
        "en": "I'm opening the demo calendar.",
        "es": "Estoy abriendo el calendario de la demo.",
    },
    "demo_filled": {
        "en": "I'm putting that in on the calendar.",
        "es": "Lo estoy poniendo en el calendario.",
    },
    "posts": {
        "en": "I'm opening the best fit in a new tab.",
        "es": "Estoy abriendo el que mejor encaja en una pestaña nueva.",
    },
    "closed": {"en": "I've closed the reading list.", "es": "Cerré la lista de lecturas."},
    "signup": {
        "en": "I'm opening the sign-up in a new tab.",
        "es": "Estoy abriendo el registro en una pestaña nueva.",
    },
    "tab": {"en": "There's that tab.", "es": "Ahí tienes esa pestaña."},
}

# ─── His nod ───────────────────────────────────────────────────────────────────

_ACK_LINES: dict[Lang, dict[Kind, tuple[str, ...]]] = {
    "en": {
        "request": ("Sure.", "Okay.", "Of course.", "Certainly."),
        "question": ("Let me see.", "Hmm, let me see.", "Okay."),
        "correction": ("I see.", "Understood.", "Right."),
        "statement": ("Okay.", "Got it.", "Right."),
    },
    "es": {
        "request": ("Claro.", "Por supuesto.", "Perfecto.", "Con gusto."),
        "question": ("Déjame ver.", "A ver.", "Mmm, déjame ver."),
        "correction": ("Ya veo.", "Entendido.", "De acuerdo."),
        "statement": ("Muy bien.", "Entendido.", "Claro."),
    },
}
ACK_RATE = 0.75
ACK_HOLD_AFTER_S = 4.0
_ACK_HOLD: dict[Lang, tuple[str, ...]] = {
    "en": ("One moment.", "Just a moment."),
    "es": ("Un momento.", "Un momentito."),
}
_ACK_SORRY: dict[Lang, str] = {
    "en": "Sorry, that's taking a little longer.",
    "es": "Disculpa, está tardando un poco más.",
}
#: A visitor's ordinary words about Potion, so the reading trusts them.
_ACK_WORDS = Vocabulary(
    common=frozenset(
        # A word list reads as words, so it stays a split string.
        """potion sendpotion video videos ai personalized personalised outreach prospect
        prospects prospecting sales marketing email emails crm hubspot salesforce linkedin
        pricing price plan plans cost demo agency agencies campaign campaigns blog post
        posts avatar avatars voice clone integration integrations reply replies leads
        """.split()  # noqa: SIM905
    ),
)


def _avatar_state(session: Session, state: Literal["WORKING"] | None) -> None:
    """The talking head's working latch: held until speech owed has played."""
    session.send_rtvi(RTVIType.SERVER_MESSAGE, {"type": "avatar", "cmd": "state", "state": state})


_HEADINGS_IN_NOTE = 40
_FAQS_IN_NOTE = 40
_SEARCH_HITS = 6
_POST_HITS = 6
_DAYS_IN_NOTE = 10
_TIMES_IN_NOTE = 16


async def _silence() -> AsyncGenerator[Any, None]:
    for _ in ():
        yield


def _clip(items: list[str] | tuple[str, ...], most: int) -> str:
    more = f"; and {len(items) - most} more" if len(items) > most else ""
    return "; ".join(items[:most]) + more


def _match(want: str, options: list[str] | tuple[str, ...]) -> str | None:
    """The option ``want`` names: the same words, else the one it begins, else
    the one it is inside — how the page itself matches. Punctuation does not
    count: "tuesday october 20" is "Tuesday, October 20"."""

    def fold(s: str) -> str:
        return " ".join(re.sub(r"[^\w\s]", " ", norm(s)).split())

    w = fold(want)
    if not w:
        return None
    folded = [(fold(o), o) for o in options]
    for test in (
        lambda o: o == w,
        lambda o: o.startswith(w),
        lambda o: w.startswith(o) and len(o) > len(w) // 2,
        lambda o: w in o,
    ):
        if (hit := next((o for f, o in folded if test(f)), None)) is not None:
            return hit
    return None


def _site_path(path: str) -> str:
    """The path as the site links it: with its trailing slash."""
    return "/" if path == "/" else f"{path}/"


#: The site's copies of its pages in another language: /es/pricing/ is
#: /pricing/ in Spanish. The crawl has the English pages only.
_LOCALE = re.compile(r"^/(?:es|pt)(?=/|$)")


def english_twin(path: str) -> tuple[str, bool]:
    """A canonical site path as the crawl knows it, and whether the visitor is
    on the site's copy of it in another language: ``/es/pricing`` →
    ``("/pricing", True)``."""
    twin = _LOCALE.sub("", path)
    return (twin or "/", twin != path)


#: A failed move whose reason says the page never got there, whatever the
#: command: these are the failures that repeat (21 in one prod call, 2026-10-22).
_MOVE_FAILED = re.compile(
    r"not on this tab's site|did not move to|calendar (?:is not on|did not|is still loading)",
    re.IGNORECASE,
)
#: How many failures of one kind make it a pattern rather than a miss.
_FAILURES_TO_ESCALATE = 2


#: The page for what the visitor asked about, when his reply forgets to show
#: it: on dev call 60e6c24b he told them about marketing twice with the screen
#: left where it was, until they said they could not see it. Matched on their
#: own words, not on his reply's: a search of a sentence like "they follow up
#: after webinars" lands on real estate. A specific page beats the overview, a
#: price word beats every other page, and among the rest the first named wins.
#: Each row has its Spanish words too: on two prod calls on 2026-10-22,
#: "integraciones" and "planes" opened nothing.
_PRICING = "/pricing"
_ASKED_PAGES: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(rf"\b(?:{words})", re.IGNORECASE), path)
    for words, path in (
        (r"marketing|marketer|mercadeo", "/ai-personalized-video-marketing-software"),
        (
            r"sales\b|prospect|outbound|outreach|sdrs?\b|ventas\b|prospecci",
            "/ai-video-prospecting-software",
        ),
        (
            r"customer (?:support|service)|support team|atención al cliente|"
            r"servicio al cliente|(?:equipo de )?soporte (?:al cliente|técnico)",
            "/ai-generated-customer-service-training-videos-software",
        ),
        (
            r"customer success|product (?:team|manage|engagement)|éxito del cliente",
            "/ai-personalized-customer-engagement-platform",
        ),
        (
            r"real estate|realtor|inmobiliari|bienes ra[ií]ces",
            "/ai-personalized-video-messaging-for-real-estate-agents-realtors",
        ),
        (
            r"e-?commerce|online store|shopping cart|cart abandon|tienda (?:en línea|online)|"
            r"carrito",
            "/ai-personalized-shopping-cart-abandonment-solutions",
        ),
        (
            r"recruit|hiring|onboarding|reclutamiento|contratación",
            "/ai-personalized-onboarding-tools-enhance-recruitment-process",
        ),
        (r"video sales letter|vsl|carta de ventas", "/video-sales-letter-software"),
        (r"video emails?\b|correos? con videos?\b", "/personalized-video-emails"),
        (
            r"pric|cost|how much|plans?\b|free trial|precios?\b|planes\b|cuestan?\b|"
            r"prueba gratis|tarifas?\b",
            _PRICING,
        ),
        (
            r"integrat|hubspot|salesforce|crm\b|apollo|lemlist|instantly|integraci|herramientas",
            "/integrations",
        ),
        (
            r"languages?\b|spanish|hindi|french|german|idiomas?\b|español|espanol",
            "/supported-languages",
        ),
        # The noun only: "I would like to review the pricings" opened /reviews
        # (prod, 2026-10-22).
        (
            r"reviews\b|testimonial|case stud|customer stor|stories\b|reseñas|opiniones|"
            r"testimonios|casos? de éxito",
            "/reviews",
        ),
        (r"security|secure|gdpr|seguridad", "/security"),
        (r"ethic|deepfake|consent|ética|etica", "/ai-ethics"),
        (r"features?\b|funciones|funcionalidades|caracter[ií]sticas", "/features"),
        (r"faqs?\b|preguntas frecuentes", "/faq"),
    )
)
_ASKED_OVERVIEW = re.compile(r"\buse[- ]?cases?\b|\bwho uses\b|\bcasos? de uso\b", re.IGNORECASE)
_ASKED_TAB = re.compile(r"\btabs?\b|\bpestañas?\b", re.IGNORECASE)
#: Talk of the demo booking, which is book_demo's and opens no page: on prod
#: call ac42733d "here I am in contact sales demo", said on the calendar, cued
#: the sales use case.
_ASKED_DEMO = re.compile(
    r"\bcontact(?:ar)?(?: (?:to|with|a|con))? (?:sales|ventas)\b|\bdemo\b", re.I
)

# A request about the call's own language: a verb of speaking, addressed to him
# ("can you", "let's", or said as an order) or said by him ("I can", "volvemos"),
# and the language. His own first sentence is read the same way for the page
# it is about, so "Claro, volvemos al español." must not open a page either. On dev call
# 1ff72fee "Hey, can you speak in Spanish?" opened /supported-languages while
# he talked about integrations. "Does Potion make videos in Spanish?" is about
# the product, and still opens it.
_CALL_LANGUAGE = re.compile(
    r"\b(?:speak|talk|switch|change|continue|carry on|answer|reply|respond|go back|"
    r"habl\w*|cambi\w*|sig\w*|continu\w*|respond\w*|contest\w*|pas\w*|volv\w*)\b"
    r"[^.?!]{0,25}?\b(?:spanish|english|español|espanol|castellano|inglés|ingles)\b",
    re.IGNORECASE,
)
_TO_HIM = re.compile(
    r"^\W*(?:(?:hey|ok|okay|please|so|now|vale|oye|bueno|por favor)\W+)*"
    r"(?:speak|talk|switch|change|continue|carry|answer|reply|respond|go|habla|háblame|"
    r"hábleme|cambia|sigue|continúa|responde|contesta|pasa|vuelve)\b"
    r"|\b(?:you|we|us|let'?s|let us|i|i'?ll|puedes|podemos|podrías|podríamos|hablemos|"
    r"sigamos|cambiemos|continuemos|pasemos|volvamos|me|nos|hablamos|seguimos|cambiamos|"
    r"continuamos|pasamos|volvemos|puedo)\b",
    re.IGNORECASE,
)


def asks_call_language(text: str) -> bool:
    """Whether ``text`` asks him to speak another language — a request about
    this call, not a question about the languages Potion's videos come in."""
    return bool(_CALL_LANGUAGE.search(text) and _TO_HIM.search(text))


def asked_page(text: str) -> str | None:
    """The site page for what ``text`` asks about, or ``None``. "The pricing
    tab" is a tab to switch to, not a page to open over the one in front,
    "can you speak Spanish?" is a request about this call, not a page, and the
    demo is book_demo's."""
    if _ASKED_TAB.search(text) or _ASKED_DEMO.search(text) or asks_call_language(text):
        return None
    named = [(m.start(), path) for rx, path in _ASKED_PAGES if (m := rx.search(text))]
    if any(path == _PRICING for _, path in named):
        return _PRICING
    if named:
        return min(named)[1]
    return "/use-cases" if _ASKED_OVERVIEW.search(text) else None


# ─── The section a sentence describes ──────────────────────────────────────────
#
# What he says, sentence by sentence, matched against the sections of the one
# page in front — never the whole site, where "they follow up after webinars"
# lands on real estate. A heading word counts for more than a word of the
# section's text, a word every section shares for little, and a sentence that
# is not clearly about one section moves nothing.

_STOP = frozenset(
    [
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "of",
        "to",
        "in",
        "on",
        "for",
        "with",
        "by",
        "at",
        "from",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
        "you",
        "your",
        "yours",
        "we",
        "our",
        "us",
        "they",
        "their",
        "them",
        "he",
        "she",
        "his",
        "her",
        "i",
        "me",
        "my",
        "can",
        "will",
        "just",
        "also",
        "so",
        "then",
        "than",
        "too",
        "very",
        "here",
        "there",
        "what",
        "which",
        "who",
        "how",
        "when",
        "where",
        "why",
        "all",
        "any",
        "each",
        "every",
        "more",
        "most",
        "some",
        "such",
        "no",
        "not",
        "only",
        "own",
        "same",
        "into",
        "out",
        "up",
        "down",
        "over",
        "under",
        "again",
        "once",
        "about",
        "after",
        "before",
        "both",
        "few",
        "other",
        "per",
        "via",
        "do",
        "does",
        "did",
        "have",
        "has",
        "had",
        "get",
        "gets",
        "got",
        "make",
        "makes",
        "made",
        "use",
        "uses",
        "used",
        "using",
        "potion",
        "potions",
        "video",
        "videos",
        "ai",
        "personal",
        "personalized",
        "personalised",
        "team",
        "teams",
        "like",
        "let",
        "lets",
        "want",
        "would",
        "shall",
        "could",
        "should",
        "see",
        "show",
        "shows",
        "one",
        "two",
        "three",
        "section",
        "page",
    ]
)
#: How sure a match must be: its score, and its lead over the runner-up.
#: Tuned on dev calls 60e6c24b and 56e87ed1, where every sentence that was
#: about a section scored 6.6 or more with a lead of 1.8 or more, and the
#: closing offers and openers scored under 4.
_SECTION_MIN = 6.0
_SECTION_LEAD = 1.5
_SECTION_MIN_WORDS = 4


def _stem(w: str) -> str:
    for suffix in ("ing", "ers", "er", "ed", "es", "s"):
        if len(w) > 4 and w.endswith(suffix):
            return w[: -len(suffix)]
    return w


def _terms(text: str) -> list[str]:
    return [
        _stem(w) for w in re.findall(r"[a-z0-9']+", text.lower()) if len(w) > 2 and w not in _STOP
    ]


def best_section(sentence: str, sections: list[tuple[str, str]]) -> str | None:
    """The heading of the one section ``sentence`` is about, of ``sections``
    (heading, text) on one page; ``None`` unless it is clearly one."""
    if sentence.rstrip().endswith("?"):
        return None  # The closing offer: about what comes next, not this page.
    # A heading he says outright ("Here are our pricing plans.") is the one,
    # however short the sentence; the longest, when he says two.
    said = " ".join(re.findall(r"[a-z0-9']+", sentence.lower()))
    quoted = [
        h
        for h, _ in sections
        if h
        and len(phrase := re.findall(r"[a-z0-9']+", h.lower())) >= 2
        and re.search(rf"\b{re.escape(' '.join(phrase))}\b", said)
    ]
    if quoted:
        return max(quoted, key=len)
    if len(sentence.split()) < _SECTION_MIN_WORDS:
        return None  # A few words: about no one section.
    docs = [(h, set(_terms(h)), set(_terms(t))) for h, t in sections if h]
    if not docs:
        return None
    df: dict[str, int] = {}
    for _, head, text in docs:
        for w in head | text:
            df[w] = df.get(w, 0) + 1
    want = set(_terms(sentence))
    scored: list[tuple[float, str]] = []
    for heading, head, text in docs:
        score = 0.0
        for w in want:
            idf = math.log(1 + len(docs) / (1 + df.get(w, 0)))
            score += 2 * idf if w in head else 0.6 * idf if w in text else 0.0
        scored.append((score, heading))
    scored.sort(key=lambda s: -s[0])
    top, heading = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    return heading if top >= _SECTION_MIN and top - second >= _SECTION_LEAD else None


#: Plans on /pricing, as its cards name them (the crawl's "Pricing plans").
_PLANS = ("Personal", "Starter", "Professional", "Enterprise")
#: Capitalised words that are no name to ring.
_NOT_NAMES = frozenset(
    [
        "Potion",
        "AI",
        "I",
        "CRM",
        "CTA",
        "CTAs",
        "HD",
        "Here",
        "This",
        "That",
        "These",
        "Those",
        "Then",
        "Every",
        "Each",
        "You",
        "Your",
        "We",
        "Our",
        "They",
        "It",
        "And",
        "Or",
        "But",
        "So",
        "For",
        "With",
        "Would",
        "Shall",
        "Want",
        "Yes",
        "No",
        "First",
        "Second",
        "Third",
        "Fourth",
        "Next",
        "Also",
        "Plus",
        "Most",
        "Many",
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
)
_NAME = re.compile(r"[A-Z][A-Za-z0-9&']*(?:[ -][A-Z][A-Za-z0-9&']*)*")


def named_on_page(sentence: str, path: str, text: str, plans: tuple[str, ...]) -> str | None:
    """A plan, a logo, a customer or a reviewer the sentence names that the
    page shows, to ring as words; ``None`` when it names none.

    A lone capitalised word that opens the sentence is only a plan: "Sales
    teams…" is not a name. On /integrations any name will do — its logos say
    their names only in their alt text, which the crawl does not have.

    A question names nothing to ring: on a prod call on 2026-10-22 "¿Usan
    alguna de esas herramientas?" rang "Usan" on /integrations, since the "¿"
    kept it from opening the sentence."""
    sentence = sentence.strip().lstrip("¿¡\"'“(").lstrip()
    if sentence.endswith("?"):
        return None
    if path == "/pricing":
        for plan in plans or _PLANS:
            if re.search(rf"\b{re.escape(plan)}\b", sentence):
                return plan
    for m in _NAME.finditer(sentence):
        parts = [p for p in re.split(r"[ -]", m.group()) if p not in _NOT_NAMES]
        if not parts:
            continue
        name = " ".join(parts)
        opens = m.start() == 0 and len(parts) == 1 and not re.search(r"[A-Z].*[A-Z]", name)
        if len(name) < 3 or opens:
            continue
        if path == "/integrations" or re.search(rf"\b{re.escape(name)}\b", text):
            return name
    return None


# ─── The brain ─────────────────────────────────────────────────────────────────


class SendPotionBrain(OpenAIBrain):
    """One per session. Javier: SendPotion's knowledge, its pages and posts, and
    a mirror of the visitor's tabs, in English or Spanish."""

    def __init__(
        self,
        *,
        client: AsyncOpenAI,
        model: str = MODEL,
        knowledge: Knowledge | None = None,
    ) -> None:
        self.kb = knowledge if knowledge is not None else kb.KNOWLEDGE
        super().__init__(
            client=client,
            system_instruction=_prompt(self.kb),
            model=model,
            reasoning=REASONING,
        )
        self._heard_at = float("-inf")
        #: The language he speaks now, and the toggle's written confirmation
        #: of a switch, said at the start of his next turn.
        self.spoken: Lang = OPENING
        #: Whether the visitor chose the language, which then holds whatever
        #: they speak; until they do, it follows what they speak.
        self._chosen = False
        self._last_heard = ""
        self._confirm: str | None = None
        self._fallback = FallbackLine()
        self._ack = Acknowledger(
            _ACK_LINES, _ACK_HOLD, _ACK_SORRY, _ACK_WORDS, ACK_RATE, ACK_HOLD_AFTER_S
        )
        #: The tab in front as it last reported itself, and whether the model
        #: has seen it since it changed.
        self.page: PageChanged | None = None
        self._path = "/"
        #: Whether the tab in front is the site's copy of ``_path`` in another
        #: language (/es/…), whose headings are not the crawl's.
        self._translated = False
        self._site = "site"
        self._page_unseen = False
        #: Every open SendPotion tab, and which is in front.
        self.tabs: list[TabInfo] = []
        self._active = ""
        self._tabs_unseen = False
        #: The demo booking as the calendar last reported it.
        self.demo: DemoState | None = None
        self._demo_fields: dict[str, str] = {}
        #: Post urls find_blog_posts has shown the model this call.
        self._found_posts: list[str] = []
        self._talk: str | None = None
        #: The sendpotion.com page this turn's cues are on: the one in front,
        #: then wherever a ``{page: …}`` cue took it. ``None`` on the blog.
        self._cue_path: str | None = None
        self._idle_short = False
        self._nudges = 0
        #: The page for what the visitor last asked about, shown at the start
        #: of his reply if it has no cue of its own; see :func:`asked_page`.
        self._backstop: str | None = None
        #: This reply's moves so far: whether one opened a page, and what was
        #: last rung, so a sentence on the same section does not ring it again.
        self._paged = False
        self._shown: str | None = None
        #: The recognizer's patience now: raised while the demo's details step
        #: is open, for a visitor spelling their email.
        self._patience = SENDPOTION_PATIENCE
        #: Failed moves this call, by kind; and whether page moves are failing,
        #: so the rest of this reply sends none.
        self._failures: dict[str, int] = {}
        self._moves_failing = False

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        init = session.init or {}
        self._site = "blog" if init.get("site") == "blog" else "site"
        self._path, self._translated = english_twin(canonical_path(str(init.get("path") or "/")))
        self._translated = self._translated and self._site == "site"
        # The page sends `lang` only once the visitor has pressed the toggle.
        chosen = init.get("lang")
        self._chosen = chosen in LANGUAGE_NAMES
        self.spoken = "es" if chosen == "es" else OPENING
        # His own voice, settled here and not by the page. Both language legs
        # move together; what he hears, the toggle and `set_language` move them
        # again.
        await session.configure(
            Config(
                stt=SttConfig(language=self.spoken, patience=self._patience),
                tts=TtsConfig(voice=VOICE, language=self.spoken),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
            )
        )
        logger.info(
            "sendpotion: session start on {} {} in {}{}",
            self._site,
            self._path,
            self.spoken,
            " (chosen)" if self._chosen else "",
        )
        if self._chosen:
            self._note(_chosen_note(self.spoken, "before the call"))

    async def greet(self, session: Session) -> str:
        """The opener, written not generated."""
        line = greeting(self._path, self._site, self.spoken)
        return for_the_voice(line) if self.spoken == "es" else line

    async def on_finalize(self, session: Session, fin: Finalize) -> None:
        """What was heard goes into the model's context; a word respelled for
        the voice is spelled as written again first, so the model never sees
        "bidéo" in its own words."""
        if "idéo" in fin.heard:
            fin = dataclasses.replace(fin, heard=from_the_voice(fin.heard))
        await super().on_finalize(session, fin)

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[Speech, None]:
        """A visitor who speaks the other language is answered in it from the
        first word, unless they chose the language they are in; the tab they moved to is read in with what they said; his
        nod covers the model's thinking."""
        self._last_heard = msg.text
        heard = None if self._chosen else heard_language(msg.text, self.spoken, language_of)
        if heard is not None and heard != self.spoken:
            await session.configure(self._speaking(heard))
            logger.info("sendpotion: language -> {} (heard)", heard)
        if holds_spanish(msg.text, self.spoken, language_of):
            logger.info("sendpotion: held in Spanish: {!r}", msg.text)
            self._note(HELD_NOTE)
        self._talk = None
        self._nudges = 0
        self._moves_failing = False
        # A reply cut off before it said a word keeps its page for the next one:
        # "use cases in sales", then "mm-hmm" while he was still thinking.
        # A request to switch language shows nothing, not even the page a
        # reply cut off before had kept.
        self._backstop = (
            None if asks_call_language(msg.text) else asked_page(msg.text) or self._backstop
        )
        self._restore_idle()
        self._read_in_screen()
        now = time.monotonic()
        fragment, self._heard_at = now - self._heard_at < _FRAGMENT_S, now
        if not fragment and (nod := self._ack.line(msg.text, self.spoken)) is not None:
            logger.info("sendpotion: ack {!r}", nod)
            async for event in say_line(self, nod):
                yield event
            working = True

            def answered() -> None:
                nonlocal working
                if working:
                    working = False
                    _avatar_state(session, None)

            _avatar_state(session, "WORKING")
            try:
                turn = super().on_user_message(session, msg)
                async for event in hold_the_floor(
                    self, self._ack, lambda: self.spoken, turn, answered
                ):
                    yield event
            finally:
                answered()
            return
        async for event in super().on_user_message(session, msg):
            yield event

    def on_user_idle(self, session: Session, idle: UserIdle) -> AsyncGenerator[Speech, None]:
        """A quiet spell — the only floor he gets without the visitor speaking.

        A result the page produced after his turn (the calendar's open days, a
        press of Schedule Event) is put in the context at once and the idle
        window shortened, so a reading visitor hears it from him here. Otherwise
        an ordinary quiet spell: a nudge, twice, then silence."""
        self._restore_idle()
        self._backstop = None
        if self._talk is not None:
            ask, self._talk = self._talk, None
            self._note(ask)
            return self.respond(session)
        if self._confirm is not None:
            line, self._confirm = self._confirm, None
            return say_line(self, line)
        if self._nudges >= _IDLE_NUDGES:
            return _silence()
        self._nudges += 1
        self._read_in_screen()
        quiet = f"The visitor has said nothing for about {round(idle.idle_ms / 1000)} seconds."
        if self._nudges == 1:
            ask = (
                "Speak into the quiet, briefly, as the guide beside them would: one useful thing "
                "about what is on their screen, or one question that helps you help them. Never "
                "ask whether they are still there, and never repeat your last line."
            )
        else:
            ask = (
                "Still quiet. One last, light offer, different from your last: something you "
                "could show them next, or posts that fit their use case. Then let them browse."
            )
        self._note(f"{quiet} {ask}")
        return self.respond(session)

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The model's turn, with its screen cues taken out of the speech and
        sent to the page (:mod:`.cues`).

        If it moved the page and said nothing, the model is asked once more with
        tools off, so he talks about what he just showed; only if that is silent
        too does he say a written line of his own. A turn that came back with
        nothing at all — no words, no move — is asked once more the same way:
        on dev call 67d16b5d three such turns left the visitor with a nod and
        then silence until they spoke again.

        A language switched on the toggle is confirmed first, in the new
        language. A unit is opened only once its first words are known, so the
        voice follows the language the model chose to write in."""
        if (line := self._confirm) is not None:
            self._confirm = None
            async for event in say_line(self, line):
                yield event
        self._cue_path = self._path if self._site == "site" else None
        self._paged = False
        self._shown = None
        spoke = False
        turn = self._fallback.speak_if_silent(
            self, super().respond(session), again=lambda: self._talk_now(session)
        )
        async for event in self._spelled(self._written(session, self._cued(turn))):
            spoke = spoke or isinstance(event, SpeechStart)
            yield event
        if not spoke:
            logger.warning("sendpotion: the model returned nothing; asking once more")
            again = self._written(session, self._cued(self._talk_now(session)))
            async for event in self._spelled(again):
                yield event

    async def _written(
        self, session: Session, turn: AsyncGenerator[Speech, None]
    ) -> AsyncGenerator[Speech, None]:
        """``turn``, with each unit held back until its first sentence is in,
        and both legs moved to the language it is in when it is not the call's.
        A chunk can be a sliver (" P"), so one is never enough to tell."""
        held: list[Speech] = []
        text = ""

        async def release() -> AsyncGenerator[Speech, None]:
            nonlocal held, text
            written = language_of(text, sure=False)
            if written == "en" and not may_write_english(
                self._last_heard, self.spoken, language_of
            ):
                written = None
            if written is not None and written != self.spoken:
                await session.configure(self._speaking(written))
                logger.info("sendpotion: language -> {} (written)", written)
            out, held, text = held, [], ""
            for event in out:
                yield event

        async for event in turn:
            if isinstance(event, SpeechStart):
                held.append(event)
                continue
            if not held:
                yield event
                continue
            held.append(event)
            if isinstance(event, SpeechChunk):
                text += event.text
                if len(text) < _WRITTEN_ENOUGH and not _SENTENCE_END.search(text):
                    continue
            async for out in release():
                yield out
        if held:
            async for out in release():
                yield out

    def _spelled(self, turn: AsyncGenerator[Speech, None]) -> AsyncGenerator[Speech, None]:
        """``turn``, with Spanish speech spelled as the voice must read it."""

        async def spelled() -> AsyncGenerator[Speech, None]:
            async for event in turn:
                if isinstance(event, SpeechChunk) and self.spoken == "es":
                    event = SpeechChunk(for_the_voice(event.text))
                yield event

        return spelled()

    async def _cued(self, turn: AsyncGenerator[Speech, None]) -> AsyncGenerator[Speech, None]:
        """``turn`` with every ``{page|show|faq: …}`` taken out of its text and
        sent to the page as a :class:`Cue`, anchored to the words before it."""
        parser = CueParser(self._auto_cues)
        try:
            async for event in turn:
                if isinstance(event, SpeechStart):
                    parser = CueParser(self._auto_cues)
                elif isinstance(event, SpeechChunk):
                    text, raw = parser.feed(self._with_backstop(event.text))
                    for cue in raw:
                        self._send_cue(cue)
                    if text:
                        yield SpeechChunk(text)
                    continue
                else:  # SpeechEnd
                    rest, raw = parser.flush()
                    for cue in raw:
                        self._send_cue(cue)
                    if rest:
                        yield SpeechChunk(rest)
                yield event
        finally:
            await turn.aclose()

    def _with_backstop(self, chunk: str) -> str:
        """The reply's first words, with the page the visitor asked about cued
        in front of them when the reply brings no cue of its own."""
        if self._backstop is None or not chunk.strip():
            return chunk
        path, self._backstop = self._backstop, None
        if "{" in chunk or self._site != "site" or path == self._path or self._booking():
            return chunk
        logger.info("sendpotion: the reply has no cue; showing {} first", path)
        return f"{{page: {path}}}{chunk}"

    def _send_cue(self, raw: RawCue) -> None:
        """Check a cue against the site, as the tools do, and send it; one that
        names nothing real is dropped and logged rather than reaching the page."""
        if self.spoken == "es" and raw.at:
            raw = dataclasses.replace(raw, at=_anchor_for_voice(raw.at))
        cue = self._resolve_cue(raw)
        logger.info("sendpotion: cue {} {!r} at {!r} -> {}", raw.kind, raw.value, raw.at, cue)
        if cue is not None:
            self._paged = self._paged or raw.kind == "page"
            if raw.kind == "show":
                self._shown = cue.heading or cue.text
            self.session.dispatch(cue)

    def _auto_cues(
        self, sentence: str, index: int, placed: tuple[tuple[CueKind, str], ...]
    ) -> list[tuple[CueKind, str]]:
        """The moves a sentence of his needs and did not bring (see
        :mod:`.cues`): the page its first sentence is about, when nothing has
        opened one, and the section, plan or name on the page it describes.
        On dev call 56e87ed1 his replies on sales, recruitment, reviews and
        pricing opened the page at its title and stayed there."""
        out: list[tuple[CueKind, str]] = []
        kinds = {k for k, _ in placed}
        # A page the model opens on this very sentence is not sent yet.
        pages = [p.path for k, v in placed if k == "page" and (p := self.kb.page(v)) is not None]
        path = pages[-1] if pages else self._cue_path
        if (
            index == 0
            and not self._paged
            and "page" not in kinds
            and self._site == "site"
            and not self._booking()
        ):
            asked = asked_page(sentence)
            # The home page has customer stories of its own, under "Trusted
            # by 13000+ companies": stories told there stay there.
            if self._path == "/" and asked == "/reviews":
                asked = None
            if asked is not None and asked != self._path and self.kb.page(asked) is not None:
                logger.info("sendpotion: he talks about {} with no cue; opening it", asked)
                out.append(("page", asked))
                path = asked
        # The rest of the reply is on this page, though the cue that opens it
        # may not be sent until several sentences have come in one chunk.
        self._cue_path = path
        if kinds & {"show", "faq"}:
            return out
        shown = self._section_for(sentence, path)
        if shown is not None and shown != self._shown:
            out.append(("show", shown))
        return out

    def _booking(self) -> bool:
        """The visitor is on the demo calendar: no page opens by itself over
        it. On a prod call on 2026-10-22 a sentence about "contact sales", said
        on the calendar, cued the sales use case."""
        return self._site == "site" and self._path == "/demo"

    def _section_for(self, sentence: str, path: str | None) -> str | None:
        """The heading or words on ``path`` (a site page; ``None`` on the blog,
        for the post in front) that ``sentence`` is about."""
        if path is None:
            return best_section(sentence, [(h, "") for h in self._headings()])
        page = self.kb.page(path)
        if page is None:
            return None
        heading = best_section(sentence, [(s.heading, s.text) for s in page.sections])
        if heading is not None:
            return heading
        live = (
            self.page is not None and english_twin(canonical_path(self.page.path))[0] == page.path
        )
        plans = tuple(self.page.plans) if live and self.page is not None else ()
        text = " ".join([page.text, *(f"{s.heading} {s.text}" for s in page.sections)])
        return named_on_page(sentence, page.path, text, plans)

    def _resolve_cue(self, raw: RawCue) -> Cue | None:
        was = self._cue_path
        cue = self._cue_for(raw)
        if cue is not None and cue.path is not None and self._moves_failing:
            # The page stays where it is, so the rest of the reply is on it.
            logger.info("sendpotion: page moves are failing; not sending {}", cue.path)
            self._cue_path = was
            return None
        return cue

    def _cue_for(self, raw: RawCue) -> Cue | None:
        if raw.kind == "page":
            page = self.kb.page(raw.value)
            if page is None:
                return None
            self._cue_path = page.path
            return Cue(at=raw.at, word=raw.word, path=_site_path(page.path))
        target = self.kb.page(self._cue_path) if self._cue_path is not None else None
        moved = self._cue_path is not None and self._cue_path != self._path
        if not moved and self._translated and self._cue_path is not None:
            # The visitor is on the Spanish copy of this page: what it shows is
            # rung there, and anything else is on the English page, opened.
            live = self._faqs() if raw.kind == "faq" else self._headings()
            moved = _match(raw.value, live) is None
        if raw.kind == "faq":
            faqs = [f.q for f in target.faqs] if target else list(self._faqs())
            if not moved:
                faqs = list(dict.fromkeys([*self._faqs(), *faqs]))
            question = _match(raw.value, faqs)
            if question is None:
                found = self._faq_elsewhere(raw.value)
                if found is None:
                    return None
                self._cue_path, question = found
                return Cue(at=raw.at, word=raw.word, path=_site_path(found[0]), faq=question)
            path = _site_path(self._cue_path) if moved and self._cue_path else None
            return Cue(at=raw.at, word=raw.word, path=path, faq=question)
        # show: a heading of the page the visitor will be on, else those words.
        headings = (
            target.headings
            if moved and target
            else self._headings() or (target.headings if target else ())
        )
        heading = _match(raw.value, headings)
        text = None if heading else raw.value[:120]
        path = _site_path(self._cue_path) if moved and self._cue_path else None
        return Cue(at=raw.at, word=raw.word, path=path, heading=heading, text=text)

    def _talk_now(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The one extra request a silent page move gets: tools declared, none callable."""
        return self.respond_with(session, tools=ToolChoice.NONE)

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Page→brain events, folded in silently: no floor taken, no turn."""
        event = SENDPOTION_EVENTS.parse(msg)
        if event is None:
            return
        logger.info("sendpotion: {} — {}", type(event).__voqal_event__, event)
        if isinstance(event, LanguageRequested):
            await self._requested(session, event)
            return
        if (note := self.apply_event(event)) is not None:
            self._note(note)

    async def _requested(self, session: Session, event: LanguageRequested) -> None:
        """The visitor pressed the other language on the toggle. Switched in
        code, not through the model: both legs move in one awaited request, and
        the written confirmation is said in his next turn — which, if they stay
        quiet, is the short quiet spell :meth:`on_user_idle` turns into it."""
        if event.language == self.spoken:
            return
        was = self.spoken
        try:
            await session.configure(self._speaking(event.language))
        except RequestRejected as rejected:
            logger.warning("sendpotion: switch to {} refused: {}", event.language, rejected)
            self.spoken = was
            session.dispatch(LanguageChanged(language=was))
            return
        logger.info("sendpotion: language -> {} (toggle)", event.language)
        self._chosen = True
        self._confirm = TOGGLE_CONFIRM[event.language]
        if not self._idle_short:
            self._idle_short = True
            configure_soon(session, Config(idle=IdleConfig(timeout_ms=_TALK_THROUGH_MS)))
        self._note(_chosen_note(event.language, "on the toggle"))

    def _speaking(self, language: Lang) -> Config:
        """Both legs of ``language``, recorded as the one he speaks now, and the
        widget's toggle moved to it."""
        if language != self.spoken:
            self.session.dispatch(LanguageChanged(language=language))
        self.spoken = language
        return Config(
            stt=SttConfig(language=language, patience=self._patience),
            tts=TtsConfig(voice=VOICE, language=language),
        )

    def _patient(self, patience: int) -> None:
        """Set the recognizer's patience, with both language legs as the
        pairing rule asks; nothing is sent when it is already that."""
        if patience == self._patience:
            return
        self._patience = patience
        logger.info("sendpotion: patience -> {}", patience)
        configure_soon(
            self.session,
            Config(
                stt=SttConfig(language=self.spoken, patience=patience),
                tts=TtsConfig(voice=VOICE, language=self.spoken),
            ),
        )

    # ─── Page → brain ───────────────────────────────────────────────────

    def apply_event(self, event: SendPotionEvent) -> str | None:
        """Patch the mirror; return the line the model should see."""
        match event:
            case PageChanged():
                self.page = event
                self._site = event.site
                self._path, translated = english_twin(canonical_path(event.path))
                self._translated = translated and event.site == "site"
                if not self._booking():
                    # Off the calendar: the details step's patience goes with it.
                    self._patient(SENDPOTION_PATIENCE)
                self._page_unseen = True
                # Read in with their next message or quiet spell: they may click
                # on before they speak, and only the last page matters.
                return None
            case TabsChanged():
                self.tabs = event.tabs
                self._active = event.active
                self._tabs_unseen = True
                return None
            case DemoState():
                return self._demo_changed(event)
            case DemoScheduled():
                self._patient(SENDPOTION_PATIENCE)
                self._talk_through(
                    "They have just pressed Schedule Event. Thank them in one sentence, say "
                    "SendPotion's team will see them then, and offer to keep answering questions."
                    if not event.blocked
                    else "They have just pressed Schedule Event on the demo calendar. This is a "
                    "preview, so the page held it back: say so in one sentence, thank them, and "
                    "offer to keep answering questions."
                )
                when = " ".join(x for x in (event.date, event.time) if x)
                held = (
                    " This preview held it back from SendPotion's calendar."
                    if event.blocked
                    else ""
                )
                return (
                    f"[The visitor pressed Schedule Event for {when or 'the chosen slot'}.{held}]"
                )
            case LanguageRequested():
                # Switched by on_rtvi before it gets here: a toggle is not a note.
                return None
            case CommandFailed():
                return self._failed(event)

    def _failed(self, event: CommandFailed) -> str | None:
        """The line for a move that did not land. Once is a miss; the same
        kind again is a pattern, said plainly. On a prod call on 2026-10-22
        every page move failed, 21 times, each noted as a miss to "carry on"
        from, and he told the visitor three times that what they could not see
        was there."""
        if event.command == "book_demo":
            self._talk = None
            self._restore_idle()
        kind = "move" if _MOVE_FAILED.search(event.reason) else event.command
        count = self._failures[kind] = self._failures.get(kind, 0) + 1
        if count >= _FAILURES_TO_ESCALATE:
            if kind == "move":
                self._moves_failing = True
            if count > _FAILURES_TO_ESCALATE:
                return f"[Another move failed ({event.command}: {event.reason}).]"
            if kind == "move":
                return (
                    f"[Page moves are failing on this tab ({event.reason}). Nothing you open "
                    "reaches their screen: never say a page, a section or the calendar is on it. "
                    "Tell them plainly, and tell them where to click instead: the site's top "
                    "menu, or sendpotion.com/demo for the demo.]"
                )
            return (
                f"[Your {event.command} moves keep failing ({event.reason}). It is not on their "
                "screen: never say it is. Tell them plainly where to find it instead.]"
            )
        if event.command == "cue":
            # He has already spoken past it: the next turn should not claim
            # it is on screen, nor stop to apologise for a scroll.
            return (
                f"[A screen cue of yours did not land ({event.reason}). It is not on their "
                "screen, so never say it is. If the visitor asks where it is, show it again; "
                "otherwise carry on.]"
            )
        return (
            f"[That did not happen on the page ({event.command}: {event.reason}). "
            "Tell the visitor plainly and offer what you can do instead; never say it "
            "worked.]"
        )

    def _demo_changed(self, event: DemoState) -> str | None:
        if event.step == "calendar" and not event.month and not event.days:
            # Calendly has not drawn the month yet. On a prod call on 2026-10-22
            # this state became "no open days this month" three seconds before
            # the six open days arrived.
            return "[The demo calendar is still loading: it has listed no days yet.]"
        before = self.demo
        self.demo = event
        self._patient(_DETAILS_PATIENCE if event.step == "details" else SENDPOTION_PATIENCE)
        if event.step == "details":
            filled = [k for k, v in event.filled.model_dump().items() if v]
            note = (
                f"[The demo calendar is at its details step for {event.date} at {event.time} "
                f"({event.timezone or 'their time zone'}). Filled: {', '.join(filled) or 'nothing'}. "
                f"Still empty: {', '.join(event.missing) or 'nothing required'}. The visitor "
                "presses Schedule Event themselves.]"
            )
            if before is None or before.step != "details":
                self._talk_through(
                    "The calendar's details step is on their screen and they have not spoken. "
                    "Say the day and time back to them in one sentence, say what is still empty, "
                    "and that Schedule Event is theirs to press."
                )
            return note
        if event.step == "scheduled":
            return "[The demo calendar shows the meeting as scheduled.]"
        days = _clip(event.days, _DAYS_IN_NOTE) or "none this month"
        note = f"[The demo calendar shows {event.month or 'this month'}. Open days: {days}."
        if event.date and event.times:
            note += f" Times on {event.date}: {_clip(event.times, _TIMES_IN_NOTE)}."
        if event.timezone:
            note += f" Times are in {event.timezone}."
        note += "]"
        if before is None or (before.days != event.days and not before.date):
            self._talk_through(
                "The demo calendar is on their screen and they have not spoken. Name two or three "
                "of its open days in one sentence, and ask which day and time suit them."
            )
        return note

    def _read_in_screen(self) -> None:
        """The tabs and the page in front, once per change, ahead of what they say."""
        if self._tabs_unseen and len(self.tabs) > 1:
            listed = "; ".join(
                f"{t.tab_id}: {t.title or t.url}"
                + (" (in front)" if t.tab_id == self._active else "")
                for t in self.tabs
            )
            self._note(f"[The visitor's open SendPotion tabs — {listed}.]")
        self._tabs_unseen = False
        if not self._page_unseen or self.page is None:
            return
        self._page_unseen = False
        p = self.page
        where = (
            "a blog post" if p.kind == "post" else "the blog" if p.site == "blog" else "the site"
        )
        note = f"[The tab in front shows {where}: “{p.title or p.path}” ({p.url or p.path})."
        if p.headings:
            note += f" Its headings: {_clip(p.headings, _HEADINGS_IN_NOTE)}."
        if p.faqs:
            note += f" Its FAQs: {_clip(p.faqs, _FAQS_IN_NOTE)}."
        if p.plans:
            note += f" Its plans: {', '.join(p.plans)}."
        self._note(note + "]")

    def _note(self, text: str) -> None:
        self.append_note(text)

    def _talk_through(self, ask: str) -> None:
        self._talk = ask
        if not self._idle_short:
            self._idle_short = True
            configure_soon(self.session, Config(idle=IdleConfig(timeout_ms=_TALK_THROUGH_MS)))

    def _restore_idle(self) -> None:
        if self._idle_short:
            self._idle_short = False
            configure_soon(self.session, Config(idle=IdleConfig(timeout_ms=_IDLE_MS)))

    def _move(self, action: Action, line: str = "shown") -> None:
        """Dispatch ``action``, with the written line for it (one of
        :data:`_LANDED`, in the language he speaks) should the turn say nothing."""
        self.session.dispatch(action)
        landed(_LANDED[line][self.spoken])

    def _headings(self) -> tuple[str, ...]:
        if self.page is not None:
            return tuple(self.page.headings)
        page = self.kb.page(self._path)
        return page.headings if page and self._site == "site" else ()

    def _faqs(self) -> tuple[str, ...]:
        if self.page is not None:
            return tuple(self.page.faqs)
        page = self.kb.page(self._path)
        return tuple(f.q for f in page.faqs) if page and self._site == "site" else ()

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        """Read and search SendPotion's knowledge and blog, move the visitor's
        tabs, book the demo, open the sign-up."""
        return [
            self.read_topic,
            self.search_site,
            self.find_blog_posts,
            self.recommend_posts,
            self.close_reading_list,
            self.open_post,
            self.book_demo,
            self.open_signup,
            self.switch_tab,
            self.set_language,
        ]

    @needs_result_now
    async def read_topic(self, request: TopicRequest) -> str:
        """Read one of SendPotion's knowledge topics before answering from it."""
        topic = self.kb.topics.get(request.topic)
        if topic is None:
            return f"No topic '{request.topic}' is written yet: use search_site."
        return topic.text

    @needs_result_now
    async def search_site(self, request: SearchRequest) -> str:
        """Search sendpotion.com's pages, sections and FAQs. Each result names the
        page path and the section heading to take them to."""
        hits = self.kb.search(request.query, _SEARCH_HITS)
        if not hits:
            return f"Nothing on sendpotion.com matches '{request.query}'. Try find_blog_posts."
        out: list[str] = []
        for h in hits:
            if h.kind == "faq":
                out.append(f"[FAQ on {h.path}] {h.title}\n  {h.snippet}")
            else:
                where = f", heading: {h.section}" if h.section else ""
                out.append(f"[page] {h.title} — path: {h.path}{where}\n  {h.snippet}")
        return "\n".join(out)

    @needs_result_now
    async def find_blog_posts(self, request: PostSearchRequest) -> str:
        """Find SendPotion blog posts for the visitor's use case. Then
        recommend_posts with the ones that fit."""
        hits = self.kb.find_posts(request.use_case, _POST_HITS)
        if not hits:
            return f"No blog post matches '{request.use_case}'. Say so, and offer site pages."
        out: list[str] = []
        for h in hits:
            post = self.kb.post(h.url or "")
            if post is None:
                continue
            if post.url not in self._found_posts:
                self._found_posts.append(post.url)
            about = post.summary or post.subtitle or h.snippet
            heads = f"\n  headings: {_clip(post.headings, 8)}" if post.headings else ""
            out.append(f"- {post.title} — url: {post.url}\n  {about}{heads}")
        return "\n".join(out)

    def _faq_elsewhere(self, asked: str) -> tuple[str, str] | None:
        """The page and FAQ ``asked`` names: by its words on any page, else the
        best FAQ search hit."""
        for page in self.kb.pages.values():
            if (q := _match(asked, [f.q for f in page.faqs])) is not None:
                return page.path, q
        for hit in self.kb.search(asked, 4):
            if hit.kind == "faq" and hit.path is not None:
                return hit.path, hit.title
        return None

    async def recommend_posts(self, request: RecommendRequest) -> str:
        """Put blog posts that fit the visitor in the reading list beside you, on
        every tab, and open the first in a new tab. Only posts find_blog_posts
        returned. In the same response, say what the opened post covers."""
        items: list[ReadingItem] = []
        unknown: list[str] = []
        for picked in request.posts[:4]:
            post = self.kb.post(picked.url)
            if post is None:
                unknown.append(picked.url)
                continue
            if all(i.url != post.url for i in items):
                items.append(ReadingItem(url=post.url, title=post.title, why=picked.why or None))
        if not items:
            return "Not shown: none of those is a SendPotion blog post. Use find_blog_posts first."
        first = items[0].url if request.open_first else None
        self._move(OpenPosts(heading=request.heading, posts=items, open=first), "posts")
        result = f"Listed {len(items)} posts beside you" + (
            f"; opened '{items[0].title}' in a new tab." if first else "."
        )
        if unknown:
            result += f" Not posts, so left out: {', '.join(unknown)}."
        return result

    async def open_post(self, request: OpenPostRequest) -> str:
        """Open one blog post for the visitor, in its own tab, scrolled to a
        heading when given. In the same response, say what that part covers."""
        post = self.kb.post(request.url)
        if post is None:
            return "Not opened: that is not a SendPotion blog post. Use find_blog_posts first."
        heading = _match(request.heading, post.headings) if request.heading else None
        self._move(OpenPost(url=post.url, heading=heading or request.heading))
        return f"Opened '{post.title}'" + (f" at '{heading}'." if heading else ".")

    async def book_demo(self, request: DemoRequest) -> str:
        """Open SendPotion's demo booking on /demo/, or add to it: the day and
        time they chose, and any name, email or notes they gave. What is filled
        stays. It never presses Schedule Event. The calendar's open days and its
        details step come back to you from the page."""
        for key in ("name", "email", "notes"):
            if value := getattr(request, key):
                self._demo_fields[key] = value
        day, when = request.day, request.time
        if day and self.demo is not None and self.demo.days:
            day = _match(day, self.demo.days) or day
        fields = self._demo_fields
        self._move(
            BookDemo(
                day=day,
                time=when,
                name=fields.get("name"),
                email=fields.get("email"),
                notes=fields.get("notes"),
            ),
            "demo_filled" if day or when or self._demo_fields else "demo",
        )
        parts = [x for x in (day, when) if x]
        filled = ", ".join(self._demo_fields) or "nothing"
        # Sent, not done: whether it landed comes back from the page. On a prod
        # call on 2026-10-22 "The demo calendar is open" was spoken over a move
        # that had failed 0.3 s after it was sent.
        return (
            f"Sent to the page: open the demo calendar on /demo/"
            f"{(', choose ' + ' '.join(parts)) if parts else ''}; details sent: {filled}. "
            "Nothing is confirmed yet: the page reports the calendar's days, times and "
            "details in a line in square brackets, or that it failed. Until then, say only "
            "that you are opening it or putting it in, and name no day or time it has not "
            "listed. The visitor presses Schedule Event themselves."
        )

    async def close_reading_list(self) -> str:
        """Close the reading list beside you, on every tab: when they ask, or
        when the conversation has moved on from those posts."""
        self._move(OpenPosts(heading="", posts=[]), "closed")
        return "Closed the reading list."

    async def open_signup(self) -> str:
        """Open Potion's sign-up and log-in (app.sendpotion.com) in a new tab.
        Only when they ask to sign up, try it free or log in."""
        self._move(OpenSignup(), "signup")
        return "Opening app.sendpotion.com in a new tab; the page cannot confirm it opened."

    async def switch_tab(self, request: TabRequest) -> str:
        """Bring another of the visitor's SendPotion tabs to the front."""
        tab = next((t for t in self.tabs if t.tab_id == request.tab_id), None)
        if tab is None:
            listed = ", ".join(f"{t.tab_id} ({t.title})" for t in self.tabs) or "none"
            return f"Not switched: no tab '{request.tab_id}'. Open tabs: {listed}."
        self._move(FocusTab(tab_id=tab.tab_id), "tab")
        return f"Brought '{tab.title or tab.url}' to the front."

    async def set_language(self, request: LanguageRequest) -> str:
        """Conduct the rest of the call in English ('en') or Spanish ('es'),
        listening and speaking. Call it when they ask for the other language in
        words that are not already it — "Can you speak Spanish?" — and to go
        back. Say one short line in the language you are switching to, in the
        same response. A visitor already speaking Spanish has been switched: do
        not call it for them."""
        self._chosen = True
        configure_soon(self.session, self._speaking(request.language))
        logger.info("sendpotion: language -> {} (asked)", request.language)
        return "ok"


__all__ = [
    "BookDemo",
    "Cue",
    "FocusTab",
    "LanguageChanged",
    "Navigate",
    "OpenFaq",
    "OpenPost",
    "OpenPosts",
    "OpenSignup",
    "ReadingItem",
    "SendPotionBrain",
    "ShowSection",
]
