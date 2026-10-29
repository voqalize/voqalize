"""KdemBrain — Aria, the voice agent on karnatakadigital.in.

A visitor to KDEM's site (the Karnataka Digital Economy Mission) clicks "Talk to
Aria" and asks a question about doing business in Karnataka. Aria answers from
the site's own approved pages and the PDF documents they link to (policies,
guidelines, reports, newsletters), in a sentence or two, and offers the page or
the PDF that says it in full as a link card beside her face.

Three things shape every decision here.

**She answers only from the pages KDEM approved.** :meth:`search_kdem` reads the
in-memory index ``knowledge.py`` keeps of those pages — their visible text, one
canonical URL per topic, refreshed from the sitemap about once a day — and of
the text of the PDFs they link to, page by page, so she can say where in a
document the answer is. The prompt holds her to what comes back. When nothing does, she says so in one fixed
line and offers Contact Us. A government agency's assistant that improvises a
scheme, a figure or a deadline is worse than one that says it does not know.

**The model never supplies a URL the brain trusts.** :meth:`show_document`,
:meth:`offer_page` and :meth:`go_to_page` take what
the model names, canonicalises it, and sends it only if the index holds that page
now — an approved page the last refresh read, a page it added, or a PDF an
approved page links to and the refresh read — with the page's own title, not
the model's. A listed page the refresh dropped (deleted,
unpublished, or redirecting elsewhere) is not sent; before the first index
exists, only Contact Us is. The browser snippet checks the host again, but the
brain is where "only approved pages" is decided.

**The page is someone else's.** There is no frontend here: the snippet in
``demos/kdem/embed/`` is pasted into the site, connects with
``init = {surface, page, lang}``, and renders four commands: ``show_link`` (a
card for a document, sent by the model's ``show_document``), ``navigate``,
``point_at`` and ``language_changed``. Pages are visited; cards are for documents. The call carries on across
page loads, and on every (re)connect the snippet sends ``page_viewed``
(:mod:`.app_events`): Aria learns the visitor moved, silently, on their next turn.

**She asks before she moves the page.** ``go_to_page`` opens another page in the
visitor's tab, and the brain sends it only for a page ``offer_page`` offered in
her previous turn (the visitor's next turn is the yes), or when the visitor's
own words this turn ask to be taken somewhere. ``point_at`` needs no asking: it
lights up a phrase the brain has checked is on the page they have open.

**Every move is said.** The acknowledgement while the model thinks is the
runtime's own (``Config.ack``, on by default), not the brain's. Each tool
lands a written line that names what it did or why it could not ("Taking you
to the Events page.", "I couldn't find that on this page."); when the model's
turn says nothing, :class:`~voqalize_demos.FallbackLine` says it. A ``go_to_page``
the visitor did not ask for becomes the offer, so their yes takes them there.

The knowledge base is one per process. The first session starts its keeper
(:meth:`~.knowledge.KnowledgeService.start`, idempotent and non-blocking); every
session after that reads the same index.
"""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator, Mapping
from typing import Any, Literal

from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel, Field
from voqalize_demos import (
    DEFAULT_MODEL,
    PATIENCE,
    FallbackLine,
    GeminiBrain,
    landed,
    needs_result_now,
    say_line,
)

from voqalize.sdk import (
    Action,
    RequestRejected,
    RTVIMessage,
    Session,
    Speech,
    SpeechChunk,
    UserMessage,
)
from voqalize.sdk.wire import Config, IdleConfig, Language, SttConfig, TtsConfig

from .app_events import (
    KDEM_EVENTS,
    KanFieldChanged,
    KanFillFailed,
    LanguageRequested,
    MicPermission,
    PageViewed,
    PointMissed,
)
from .content import (
    BY_CODE,
    BY_TAG,
    CONTACT_PATH,
    KAN_LABELS,
    KAN_LOCATIONS,
    KAN_URL,
    OPENING,
    SPEECH,
    KanField,
    LanguageName,
    LanguageTag,
    page_digest,
)
from .content import Speech as LanguageSpeech
from .knowledge import (
    ALLOWLIST,
    KNOWLEDGE,
    SITE,
    Passage,
    host_of,
    is_pdf,
    normalize,
    off_site,
    path_of,
    pdf_url,
)

AGENT_NAME = "Aria"

# The visitor is reading the site, not waiting on her. Nothing hangs up on a
# quiet page — they may be reading the link she just offered.
_IDLE_MS = 0

#: How many passages one search hands back. Three is enough to answer from and
#: few enough that a turn's context stays small.
_PASSAGES = 3

#: The line for anything the approved pages do not answer. Written once, here,
#: so the prompt and the tool results say the same words.
DONT_KNOW = "I don't have that on our website. The KDEM team can help."

#: After the first don't-know in a call, what she says instead, taking turns so
#: no line comes twice running: the question is the KDEM team's, and Contact
#: Us is offered. Kept short; the offer follows from the line it is said with.
TEAM_LEADS: Mapping[Language, tuple[str, str]] = {
    Language.EN: (
        "That one is best answered by the KDEM team.",
        "The KDEM team can help you with that directly.",
    ),
    Language.KN: (
        "ಅದಕ್ಕೆ KDEM ತಂಡವೇ ಸರಿಯಾಗಿ ಉತ್ತರಿಸಬಲ್ಲದು.",
        "ಅದರ ಬಗ್ಗೆ KDEM ತಂಡ ನೇರವಾಗಿ ಸಹಾಯ ಮಾಡಬಲ್ಲದು.",
    ),
}

#: What she says she is. Never a model or a vendor: she is KDEM's assistant.
IDENTITY = "I'm Aria, KDEM's voice assistant, built by Voqalize."

# ─── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_INSTRUCTION = f"""You are {AGENT_NAME}, the voice assistant on the website of KDEM, the Karnataka Digital Economy Mission, at karnatakadigital.in. A visitor is on the site right now, with you in the corner of the page. They are usually a founder, an investor, a company looking at Karnataka, a student or a job seeker.

WHO YOU ARE. You are KDEM's assistant, built for KDEM by Voqalize. Never name a model, an AI company or any vendor or technology behind you, and never call yourself a language model. Asked what you are, who made you or what you run on, say: "{IDENTITY}" and offer to help with KDEM.

EVERY MOVE COMES WITH WORDS. Whenever you offer a page, take them to one, point at something, show a document or fill in the form, write your line first and make the call in that same response — the line is spoken as the page moves. Your line says what you are doing, by name: "Taking you to the Events page.", "Here's the eligibility, on this page.", "I've opened the Startup Policy beside you." A response that is only a tool call is silence: after offer_page, go_to_page, point_at, show_document or fill_kan_field you do not speak again until the visitor does, and what the call returns reaches you on their next turn. For example:
  Visitor: "Do you have a seed fund for startups outside Bengaluru?" You: (search_kdem first, then) "Yes, the Beyond Bengaluru Cluster Seed Fund backs startups in the clusters. Shall I take you to its page?" — and offer_page with that page, in the same response.
search_kdem and set_language are the two calls that take no line. search_kdem is silent and comes straight back to you in the same turn, so call it first and then answer from it. set_language is answered by a line of its own, in the new voice, so call it alone and say nothing.

ANSWER ONLY FROM THE SITE. Everything you may say about KDEM, its programmes, policies, events, reports and news comes from ABOUT KDEM below or from what search_kdem returns. "What is KDEM", "what do you do" and "what programmes do you run" are answered from ABOUT KDEM, with no search; for anything else, search before you answer — even a question you think you know. When what comes back does not answer a broad question, search once more with different words, such as the programme names in THE PAGES, before you give the don't-know line; two searches in a turn at most. Never add a figure, a date, a deadline, an amount, an eligibility rule or a name that is not in what came back. When what came back answers part of the question, say that part, and that the KDEM team can tell them the rest. If the search returns nothing that answers the question, say exactly: "{DONT_KNOW}" and offer to take them to the Contact Us page with offer_page ({CONTACT_PATH}), or point at it with point_at if they are already there. Say that line once in a call, never twice running: after it, what search_kdem returns tells you what to say instead.

THE SHAPE OF AN ANSWER. One or two short sentences that answer the question, then, in the same response:
- when the page that says it in full is another page, offer to take them there with offer_page: "Shall I take you to the Seed Fund page?";
- when they are already on that page, point at the part that says it with point_at;
- when the answer comes from a PDF, name the document and the page in words and show it beside you with show_document.
Do not read a page aloud; the page is there for that. Pass a URL that search_kdem returned or one from THE PAGES below.

DOCUMENTS. Many results come from the PDF documents KDEM's pages link to — policies, guidelines, reports and newsletters — and are marked "PDF document, page N". When you answer from one, say which document and where, in words, for example "the Startup Policy says so on page 12", and show it beside you with show_document, passing the url exactly as search_kdem gave it. A document hosted on another government site, marked "on <site>", opens as the KDEM page that links to it: name the document and the page in what you say, and say it is linked from that KDEM page.

TAKING THEM AROUND THE SITE. You can take the visitor to another page of the site, in this same tab; the call carries on there with them.
- Ask first, in one short line, and call offer_page with that page in the same response: "Shall I take you to the Seed Fund page?" When they say yes, in their next turn, call go_to_page with it and say one short line: "Taking you there."
- When they ask to be taken somewhere ("take me to the events page", "open the policies page"), that is their yes: call go_to_page at once, with "Taking you there." Do not offer it back to them first.
- A page they name ("the events page", "the contact page", "the policies page") is the page in THE PAGES whose title is that name: Events is /events/, Contact Us is the contact page. Take its path from THE PAGES without searching. Search only when they describe what they want rather than naming a page.
- go_to_page goes to a page you offered in your last turn, or one they asked for in this turn. A PDF opens beside you with show_document instead, so the call stays on this page.
- POINTING. On the page they have open, point at the part that answers them with point_at, passing a short exact phrase from that page's text: a heading or a few words, under 80 characters, as they appear in what search_kdem returned for that page. No need to ask. Pointing goes with an answer and never replaces it: say the answer first, in a sentence of your own, then point in the same response: "Private limited companies in the clusters can apply. The eligibility is right here."
- After you take them to a page you are still in the same conversation: carry on from where you were, point at the part they need, and do not greet them again.

CONTACTING KDEM. The Contact Us page ({CONTACT_PATH}) has KDEM's email address, info@karnatakadigital.in (say it as "info at karnatakadigital dot in"), a contact form, and the office address in Bengaluru. The site gives no phone number. Asked for one, say so plainly, and that they can write to that email or use the form on the Contact Us page; offer the page, or on it point at the email address.

THE KAN APPLICATION FORM. The Karnataka Acceleration Network page ({path_of(KAN_URL)}) has an application form, and you fill it in with the visitor, by voice.
- When they want to apply to KAN, or to join the accelerator, offer to take them to that page, asking first as always.
- On that page, say you can fill the form in with them. Then ask for one field at a time, in the form's order: the startup's name, its sector, the founder or co-founder's name, a mobile number, an email ID, and the location they are interested in. As each answer comes, say a short line and call fill_kan_field with it, in the same response. Skip a field they have already filled.
- The mobile number and the email: read it back in one short line ("That's 98450 12345, is that right?") and call fill_kan_field with it in that same response; it goes into the form when they say yes and you call fill_kan_field with it again. If they correct it, read the new one back.
- The location is one of: {"; ".join(KAN_LOCATIONS)}. When they name a city with more than one (Bengaluru has three), ask which.
- In Kannada, names stay as they say them, and the location is still one of those six, written as above.
- At the end, ask them to check the form and press Apply Now themselves: filling it is yours, sending it is theirs.

SAYING GOODBYE. When the visitor says goodbye, or that they are done, say a short goodbye ("Thank you for visiting. Goodbye.") and call end_call in the same response. Nothing is said after it: the call closes when your goodbye has been heard. Never call it for a plain "thank you" in the middle of a conversation.

SOUND LIKE A PERSON, NOT A SCRIPT. Your first word is the answer, with no filler, and your first sentence is short, so it is heard quickly.

VOICE STYLE. Warm, plain and brief. No markdown, no lists, no symbols, no URLs read aloud — say "the Policies page", not its address. Say numbers as a person would. No throat-clearing: not "Great question", not "Sure, let me". English by default.

WHAT YOU DO NOT DO. Each of these gets one polite sentence and, where it helps, the Contact Us page:
- Politics, government decisions, ministers or officials, and opinions about any of them. You talk about what the site says, not about who decided it.
- Commitments on behalf of KDEM or the Government of Karnataka: no promises of funding, approval, a meeting, a timeline or an outcome.
- Problems on the site or a portal (an error, a form that will not submit, a login or a password) and the status of any individual application, registration, payment or tender. You cannot see them; the KDEM team handles them. Say so plainly in one sentence, without searching, and offer the Contact Us page.
- Legal, tax or investment advice beyond what the site's own documents say. Say what the document says and suggest they take advice.
- Personal details. The details you take are the six on the KAN application form, while the visitor is applying on that page (see THE KAN APPLICATION FORM): the startup's name and sector, a founder's name, a mobile number, an email ID and a location. Those go into the form and nowhere else. For anything beyond them — an address, an ID number, an OTP, a password — tell them you do not need it.
- Anything unrelated to KDEM and doing business in Karnataka: say briefly that it is outside what you can help with here.

LANGUAGE. The call starts in English, and English stays the main language. Besides English you speak Kannada, the language of Karnataka, in a Kannada voice.
- NEVER SAY ITS NAME IN ENGLISH. In English speech, never say the name of the Kannada language: the English voice cannot say it. If you must refer to it, say "Karnataka's own language"; usually, simply switch. If they ask which languages you speak, or whether you speak it, say: "I speak English, and Karnataka's own language too. Just speak to me in it, or tap ಕನ್ನಡ at the top of my panel."
- SWITCHING TO KANNADA. If the visitor asks for Kannada, or a turn looks like Kannada, call set_language with kannada at once, in that turn, and say NOTHING yourself: no line before the call and none after. The voice changes first, and then a written Kannada line is said for you, asking them to say it again. From their next turn on, speak Kannada, in Kannada script. While you are in English the recognizer only knows English, so Kannada arrives as English words forced onto Kannada sounds, and the sounds that survive are words like "naanu", "nanna", "beku", "illa", "enu", "hesaru", "maadi", "gottilla". A turn with such words in it is Kannada: do not ask whether to switch, switch. If you were wrong, the visitor speaks English and you switch back, or they tap English on the page.
- MISHEARD. A turn that reads as neither English nor Kannada (garbled words, or words that look like another language) was misheard, often over noise. Say only: "Sorry, I didn't catch that. Could you say it again?" Do not search on it, do not answer a guess at it, and never switch the language on it.
- SWITCHING BACK. In Kannada mode English arrives spelled in Kannada script ("ಐ ವಾಂಟ್ ..." is "I want ..."); judge by the small grammar words, not by nouns. When they speak English or ask for it, call set_language with english, again saying nothing yourself: a written English line is said for you in the English voice.
- What does NOT count as switching: one borrowed English word inside a Kannada sentence ("ನನಗೆ startup fund ಬೇಕು" is still Kannada), or one Kannada word inside an English sentence. Judge by the whole sentence, not a word.
- Only English and Kannada are offered; if they ask for another language, say so in English. The site is in English, so always write search_kdem queries in English, whatever language the call is in.

THE PAGES. These are the approved pages, by path, with their titles. Newer news and event pages may also come back from search_kdem; those are approved too.
"""

# The opener. Written, not generated: the visitor has just clicked, and a first
# word that waits on a model makes the site feel slow.
# It names both reasons people come: a business to grow, and jobs and skills.
_GREETING = (
    f"Hello, I'm {AGENT_NAME} from KDEM. I can help with growing a business, "
    "or with jobs and skills in Karnataka. What are you looking for?"
)


#: The opener when the visitor picked ಕನ್ನಡ on the toggle before the call.
#: Written, like the English one. To be checked by a native speaker.
_GREETING_KN = (
    "ನಮಸ್ಕಾರ, ನಾನು KDEM ನ ಆರಿಯಾ. ಕರ್ನಾಟಕದಲ್ಲಿ ವ್ಯವಹಾರ ಬೆಳೆಸಲು, ಅಥವಾ ಉದ್ಯೋಗ ಮತ್ತು "
    "ಕೌಶಲ್ಯಗಳ ಬಗ್ಗೆ ನಾನು ಸಹಾಯ ಮಾಡಬಲ್ಲೆ. ನಿಮಗೆ ಏನು ಬೇಕು?"
)

#: What Aria says, at the start of her next turn, after the visitor switched the
#: language on the toggle. Written, in the new language, read by the new voice.
#: The Kannada line is to be checked by a native speaker.
TOGGLE_CONFIRM: dict[LanguageTag, str] = {
    "en": "Sure, let's continue in English.",
    "kn": "ಸರಿ, ಈಗ ಕನ್ನಡದಲ್ಲಿ ಮಾತಾಡೋಣ.",
}

#: What Aria says when she switches by voice, after both legs have moved, so the
#: new voice reads it, at the end of the turn that asked for it. The visitor's
#: Kannada was heard by the English recognizer and lost, so the Kannada line asks
#: them to say it again. Never the language's English name: the English voice
#: cannot say it. The Kannada line is to be checked by a native speaker.
SWITCH_LINE: dict[LanguageTag, str] = {
    "en": "Sure, let's continue in English.",
    "kn": "ಸರಿ, ಈಗ ಕನ್ನಡದಲ್ಲಿ ಮಾತಾಡೋಣ. ದಯವಿಟ್ಟು ನಿಮ್ಮ ಪ್ರಶ್ನೆಯನ್ನು ಮತ್ತೊಮ್ಮೆ ಹೇಳಿ.",
}

# ─── Her own line for each move ───────────────────────────────────────────────

#: What she says when a turn moved something, or was refused, and the model
#: said nothing: the move by name, so the visitor hears what happened. Spoken
#: only for a silent turn (:class:`~voqalize_demos.FallbackLine`), never in the
#: model's context. ``{title}`` is a page's or a document's own title, ``{text}``
#: what she pointed at, ``{label}`` a KAN form field. The Kannada lines are to
#: be checked by a native speaker.
Said = Literal[
    "offer",
    "go",
    "point",
    "point_soon",
    "document",
    "filled",
    "already_here",
    "cant_open",
    "cant_open_offer",
    "cant_open_here",
    "pdf_not_page",
    "point_miss",
    "document_refused",
    "kan_elsewhere",
    "say_again",
    "goodbye",
    "dont_know",
    "dont_know_offer",
    "dont_know_here",
    "team",
    "team_offer",
    "team_here",
]
LINES: dict[Said, Mapping[Language, str]] = {
    "offer": {
        Language.EN: "Shall I take you to the {title} page?",
        Language.KN: "ನಿಮ್ಮನ್ನು {title} ಪುಟಕ್ಕೆ ಕರೆದುಕೊಂಡು ಹೋಗಲೇ?",
    },
    "go": {
        Language.EN: "Taking you to the {title} page.",
        Language.KN: "ನಿಮ್ಮನ್ನು {title} ಪುಟಕ್ಕೆ ಕರೆದುಕೊಂಡು ಹೋಗುತ್ತಿದ್ದೇನೆ.",
    },
    "point": {
        Language.EN: "Here's {text}, highlighted on the page.",
        Language.KN: "{text} ಇಲ್ಲಿದೆ, ಪುಟದಲ್ಲಿ ಗುರುತಿಸಿದ್ದೇನೆ.",
    },
    "point_soon": {
        Language.EN: "I'll highlight {text} once the page opens.",
        Language.KN: "ಪುಟ ತೆರೆದ ಮೇಲೆ {text} ಅನ್ನು ಗುರುತಿಸುತ್ತೇನೆ.",
    },
    "document": {
        Language.EN: "I've opened {title} beside you.",
        Language.KN: "{title} ಅನ್ನು ಪಕ್ಕದಲ್ಲೇ ತೆರೆದಿದ್ದೇನೆ.",
    },
    "filled": {
        Language.EN: "I've filled in your {label}.",
        Language.KN: "ನಿಮ್ಮ {label} ತುಂಬಿದ್ದೇನೆ.",
    },
    "already_here": {
        Language.EN: "You're already on the {title} page.",
        Language.KN: "ನೀವು ಈಗಾಗಲೇ {title} ಪುಟದಲ್ಲಿದ್ದೀರಿ.",
    },
    "cant_open": {
        Language.EN: "I can't open that page.",
        Language.KN: "ಆ ಪುಟವನ್ನು ನಾನು ತೆರೆಯಲು ಆಗುವುದಿಲ್ಲ.",
    },
    "cant_open_offer": {
        Language.EN: "I can't open that page, but I can take you to the {title} page.",
        Language.KN: ("ಆ ಪುಟವನ್ನು ನಾನು ತೆರೆಯಲು ಆಗುವುದಿಲ್ಲ, ಆದರೆ ನಿಮ್ಮನ್ನು {title} ಪುಟಕ್ಕೆ ಕರೆದುಕೊಂಡು ಹೋಗಬಲ್ಲೆ."),
    },
    "cant_open_here": {
        Language.EN: "I can't open that page. The KDEM team's details are on this page.",
        Language.KN: "ಆ ಪುಟವನ್ನು ನಾನು ತೆರೆಯಲು ಆಗುವುದಿಲ್ಲ. KDEM ತಂಡದ ವಿವರಗಳು ಇದೇ ಪುಟದಲ್ಲಿವೆ.",
    },
    "pdf_not_page": {
        Language.EN: "That's a document. Shall I open it beside you?",
        Language.KN: "ಅದು ಒಂದು ದಾಖಲೆ. ಅದನ್ನು ಪಕ್ಕದಲ್ಲೇ ತೆರೆಯಲೇ?",
    },
    "point_miss": {
        Language.EN: "I couldn't find that on this page.",
        Language.KN: "ಅದು ಈ ಪುಟದಲ್ಲಿ ನನಗೆ ಸಿಗಲಿಲ್ಲ.",
    },
    "document_refused": {
        Language.EN: "I can't open that document.",
        Language.KN: "ಆ ದಾಖಲೆಯನ್ನು ನಾನು ತೆರೆಯಲು ಆಗುವುದಿಲ್ಲ.",
    },
    "kan_elsewhere": {
        Language.EN: "The form is on the {title} page. Shall I take you there?",
        Language.KN: "ಫಾರ್ಮ್ {title} ಪುಟದಲ್ಲಿದೆ. ಅಲ್ಲಿಗೆ ಕರೆದುಕೊಂಡು ಹೋಗಲೇ?",
    },
    "say_again": {
        Language.EN: "Sorry, I didn't catch that. Could you say it again?",
        Language.KN: "ಕ್ಷಮಿಸಿ, ಅದನ್ನು ಮತ್ತೊಮ್ಮೆ ಹೇಳುತ್ತೀರಾ?",
    },
    "goodbye": {
        Language.EN: "Thank you for visiting. Goodbye.",
        Language.KN: "ಭೇಟಿ ನೀಡಿದ್ದಕ್ಕೆ ಧನ್ಯವಾದಗಳು. ನಮಸ್ಕಾರ.",
    },
    "dont_know": {
        Language.EN: DONT_KNOW,
        Language.KN: "ಅದರ ಬಗ್ಗೆ ನಮ್ಮ ವೆಬ್‌ಸೈಟ್‌ನಲ್ಲಿ ಮಾಹಿತಿ ಇಲ್ಲ. KDEM ತಂಡ ಸಹಾಯ ಮಾಡಬಹುದು.",
    },
    "dont_know_offer": {
        Language.EN: DONT_KNOW + " Shall I take you to the {title} page?",
        Language.KN: (
            "ಅದರ ಬಗ್ಗೆ ನಮ್ಮ ವೆಬ್‌ಸೈಟ್‌ನಲ್ಲಿ ಮಾಹಿತಿ ಇಲ್ಲ. KDEM ತಂಡ ಸಹಾಯ ಮಾಡಬಹುದು. "
            "ನಿಮ್ಮನ್ನು {title} ಪುಟಕ್ಕೆ ಕರೆದುಕೊಂಡು ಹೋಗಲೇ?"
        ),
    },
    "dont_know_here": {
        Language.EN: DONT_KNOW + " Their details are on this page.",
        Language.KN: (
            "ಅದರ ಬಗ್ಗೆ ನಮ್ಮ ವೆಬ್‌ಸೈಟ್‌ನಲ್ಲಿ ಮಾಹಿತಿ ಇಲ್ಲ. KDEM ತಂಡ ಸಹಾಯ ಮಾಡಬಹುದು. ಅವರ ವಿವರಗಳು ಇದೇ ಪುಟದಲ್ಲಿವೆ."
        ),
    },
}
LINES["team"] = dict.fromkeys(TEAM_LEADS, "{lead}")
LINES["team_offer"] = {
    Language.EN: "{lead} Shall I take you to the {title} page?",
    Language.KN: "{lead} ನಿಮ್ಮನ್ನು {title} ಪುಟಕ್ಕೆ ಕರೆದುಕೊಂಡು ಹೋಗಲೇ?",
}
LINES["team_here"] = {
    Language.EN: "{lead} Their email address and a contact form are on this page.",
    Language.KN: "{lead} ಅವರ ಇಮೇಲ್ ವಿಳಾಸ ಮತ್ತು ಸಂಪರ್ಕ ಫಾರ್ಮ್ ಇದೇ ಪುಟದಲ್ಲಿವೆ.",
}
# Her own lines are said in the language her voice speaks, so each needs a row
# for every language she speaks — held at import, not on a call.
assert all({s.code for s in SPEECH.values()} <= set(v) for v in LINES.values()), (
    "a spoken language has no written line for a move"
)
assert {s.code for s in SPEECH.values()} <= set(TEAM_LEADS)

#: What marks a reply as a don't-know, in either language: the line itself or
#: one of the team's leads, as the model or the brain said it.
_NOT_KNOWN = tuple(
    _m.casefold()
    for _m in (
        "I don't have that on our website",
        "ಅದರ ಬಗ್ಗೆ ನಮ್ಮ ವೆಬ್‌ಸೈಟ್‌ನಲ್ಲಿ ಮಾಹಿತಿ ಇಲ್ಲ",
        *(lead for leads in TEAM_LEADS.values() for lead in leads),
    )
)

#: The KAN form's fields as she says them in a sentence.
KAN_SPOKEN: dict[Language, dict[KanField, str]] = {
    Language.EN: {
        "startup_name": "startup's name",
        "sector": "sector",
        "founder_name": "founder's name",
        "mobile": "mobile number",
        "email": "email ID",
        "location": "location",
    },
    Language.KN: {
        "startup_name": "ಸ್ಟಾರ್ಟಪ್ ಹೆಸರು",
        "sector": "ವಲಯ",
        "founder_name": "ಸಂಸ್ಥಾಪಕರ ಹೆಸರು",
        "mobile": "ಮೊಬೈಲ್ ಸಂಖ್ಯೆ",
        "email": "ಇಮೇಲ್ ಐಡಿ",
        "location": "ಸ್ಥಳ",
    },
}

#: The most of a pointed-at phrase her own line repeats.
_SPOKEN_TEXT_CHARS = 40


def _spoken_title(title: str) -> str:
    """A page's title as said in "the … page": anything after a " | " (the
    site's name) and a trailing "page" dropped."""
    short = title.split(" | ")[0].strip() or title
    return re.sub(r"\s+page$", "", short, flags=re.IGNORECASE)


#: What a label never ends on when she says it: a dash, a colon, a comma, an
#: arrow, or the stop of a heading cut short.
_LABEL_TAIL = " \t,;:.-\u2010\u2011\u2012\u2013\u2014\u2015\u2212|/\u2022\u00b7\u2192\u203a>("


def _spoken_text(text: str) -> str:
    """What she pointed at, as her line repeats it: a few whole words, and
    never a trailing dash or stop ("SEBI-registered Category I AIF" followed by an en dash is said
    "SEBI-registered Category I AIF")."""
    text = text.strip()
    if len(text) > _SPOKEN_TEXT_CHARS:
        cut = text[: _SPOKEN_TEXT_CHARS + 1]
        if cut[-1].isspace():  # the cut fell between two words
            text = cut.rstrip()
        elif " " in cut:
            text = cut.rsplit(None, 1)[0]
        else:
            text = cut[:_SPOKEN_TEXT_CHARS]
    return text.rstrip(_LABEL_TAIL) or text


_ABOUT_URL = f"{SITE}/about-us/"
_ABOUT_CHARS = 600
_FIRST_SENTENCE_CHARS = 220
#: The focus-area hubs: the programme pages ABOUT KDEM names, in list order.
_FOCUS = tuple(
    p.url for p in ALLOWLIST.pages if p.section == "focus-areas-programmes" and p.hub_for
)


def _opening(text: str, limit: int) -> str:
    """The first sentences of a page's text, up to ``limit`` characters, cut at a
    sentence end. Short lines — headings, menus, figures — are passed over."""
    body = " ".join(ln for ln in text.split("\n") if len(ln) >= 60 and " " in ln)
    if len(body) <= limit:
        return body
    cut = body[:limit]
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "), cut.rfind("."))
    return cut[: end + 1] if end > limit // 4 else cut.rsplit(" ", 1)[0] + "..."


def _about_kdem() -> str:
    """ABOUT KDEM for the prompt, built from the index as it is now: the opening
    of the About Us page, and each focus-area hub's title and first sentence.
    Only the site's own words; empty until the About Us page is indexed."""
    kb = KNOWLEDGE.kb
    about = kb.page(_ABOUT_URL)
    if about is None or not (opening := _opening(about.text, _ABOUT_CHARS)):
        return ""
    programmes: list[str] = []
    for url in _FOCUS:
        page, approved = kb.page(url), ALLOWLIST.approved(url)
        if page is None or approved is None:
            continue
        first = _opening(page.text, _FIRST_SENTENCE_CHARS)
        programmes.append(f"- {approved.title} ({path_of(url)})" + (f": {first}" if first else ""))
    lines = "\n".join(programmes)
    return f"ABOUT KDEM. In the site's own words, from the About KDEM page: {opening}" + (
        f"\nIts focus areas and programmes, each with its page:\n{lines}" if lines else ""
    )


def _prompt(where: str = "", spoken: Language = OPENING.code) -> str:
    """The system prompt as things stand: THE PAGES lists only the pages Aria
    may link at this moment, so the model is never offered one the refresh has
    dropped; ABOUT KDEM, from the pages indexed now; the call's language now,
    when it is not English; and where the visitor is."""
    prompt = _SYSTEM_INSTRUCTION + page_digest(lambda url: _page(url) is not None)
    if about := _about_kdem():
        prompt += f"\n\n{about}"
    if spoken == Language.KN:
        prompt += (
            "\n\nTHE CALL IS IN KANNADA NOW. Speak Kannada, in Kannada script, until the "
            "visitor asks for English, speaks it, or switches it on the page."
        )
    return f"{prompt}\n\nWHERE THEY ARE. {where}" if where else prompt


# ── The tool surface ──────────────────────────────────────────────────────────


class ShowLink(Action, name="show_link"):
    """Brain → browser: a link card to one KDEM document, opened in a new tab.

    The model's tool for it is ``show_document``, and it is for PDFs only: pages
    are visited, with ``offer_page`` / ``go_to_page``. The command keeps the wire
    name ``show_link`` and its ``{url, title}`` payload so the snippet already on
    the site renders it unchanged."""

    url: str
    """An absolute ``https://karnatakadigital.in/...`` URL, chosen by the brain: a
    PDF under ``/wp-content/uploads/``, or, for a PDF on another site, the
    approved KDEM page that links it."""
    title: str
    """The document's own title, as the card shows it."""


class SearchRequest(BaseModel):
    query: str = Field(
        description="What the visitor wants to know, as a short search in English — "
        "the site is in English even when the call is in Kannada. Name the topic, "
        "e.g. 'seed fund for startups in Mysuru' or 'upcoming events'."
    )


class LanguageChanged(Action, name="language_changed"):
    """Brain → browser: the language the call is in now. The snippet's
    English | ಕನ್ನಡ toggle shows this and nothing else, so it follows a switch
    made by voice as well as one made on the toggle."""

    language: LanguageTag


class Navigate(Action, name="navigate"):
    """Brain → browser: open this KDEM page in the same tab. The call carries on
    across the page load. Sent only for a page the visitor said yes to, or asked
    for themselves."""

    url: str
    """An absolute ``https://karnatakadigital.in/...`` page URL, chosen by the brain."""


class PointAt(Action, name="point_at"):
    """Brain → browser: scroll to, and briefly highlight, the first visible part
    of the page holding this text. The brain checked it is on the page."""

    text: str


class KanFill(Action, name="kan_fill"):
    """Brain → browser: put ``value`` into one field of the KAN application form,
    found by its label. For the location, ``value`` is the drop-down option's
    exact text. There is no action that sends the form: Apply Now is the
    visitor's."""

    field: KanField
    value: str


class KanFillRequest(BaseModel):
    field: KanField = Field(description="Which field of the KAN application form.")
    value: str = Field(
        description="What goes in it, as the visitor said it. A mobile number as digits; "
        "the location as one of the form's six, or the city or incubator they named."
    )
    replace: bool = Field(
        False,
        description="True only when the visitor typed this field themselves and has "
        "told you to change it.",
    )


class PageRequest(BaseModel):
    url: str = Field(
        description="The page: a URL that search_kdem returned, or a path from THE PAGES, "
        "e.g. '/policies/'."
    )


class PointRequest(BaseModel):
    text: str = Field(
        description="A short exact phrase from the page the visitor has open, under 80 "
        "characters: a heading or a few words, as they appear in its text."
    )


class DocumentRequest(BaseModel):
    url: str = Field(
        description="The PDF document to show: its url exactly as search_kdem returned it."
    )
    title: str = Field(
        "",
        description="A few words naming the document. The card uses its own title.",
    )


class LanguageRequest(BaseModel):
    language: LanguageName = Field(
        description="The language to conduct the rest of the call in. Only English and "
        "Kannada are offered; if they ask for another, say so rather than picking one."
    )


_POINT_CHARS = 80
"""The longest phrase ``point_at`` takes: a heading or a few words, not a passage."""

_ASKS_TO_GO = re.compile(
    r"\b(?:take|bring|walk)\s+(?:me|us)\b|\b(?:go|navigate|jump|head|move)\s+to\b"
    r"|\bopen\b|\bvisit\b|\blet'?s\s+go\b|\bshow\s+(?:me|us)\b|\bcan\s+(?:i|we)\s+see\b"
    r"|\b(?:i'?d|i\s+would|we'?d|we\s+would)\s+(?:like|love)\s+to\s+(?:see|go|visit|view)\b"
    r"|\bwhere(?:'s|\s+is)\s+(?:the|your)\s+(?:[\w'&-]+\s+){0,5}?page\b"
    r"|ಕರೆದುಕೊಂಡು\s*ಹೋಗಿ|ಕರ್ಕೊಂಡು\s*ಹೋಗಿ|ತೆರೆಯಿರಿ|ತೆಗೆಯಿರಿ|ಹೋಗೋಣ|ತೋರಿಸಿ|ನೋಡಬೇಕು"
    r"|ಪುಟ\S*\s+ಎಲ್ಲಿ",
    re.IGNORECASE,
)
"""Words with which a visitor asks to be taken to a page, in English and Kannada:
"take me to", "open", "show me", "I'd like to see", "can I see", "where's the
events page", "ತೋರಿಸಿ" (show), "ನೋಡಬೇಕು" (want to see). Their own request is
the yes that ``go_to_page`` otherwise waits for. A plain question ("what events
are going on?", "tell me about the seed fund") is not one: she answers it, and
offers the page."""


_KANNADA_HEARD = re.compile(
    r"[\u0c80-\u0cff]|\bkannad"
    r"|\b(?:naanu|nanu|nanna|nange|nanage|nimma|beku|beda|illa|ilva|enu|yenu|hesaru|maadi"
    r"|madi|gottilla|gothilla|haudu|howdu|swalpa|bagge|hegide|hegiddira|yaake|elli|yavaga"
    r"|kodi|helkodi|heli|banni|namaskara|dhanyavada|dhanyavadagalu)\b",
    re.IGNORECASE,
)
"""What Kannada heard by the English recognizer still shows: the script, the
language's name, or a common Kannada word that survives as English letters.
A switch to Kannada by voice needs one of them in what the visitor said: a
garbled turn ("Ferro vai la dar agua") switched a call once, and the visitor
then heard a language they had not spoken."""

_GOODBYE_HEARD = re.compile(
    r"\b(?:good\s*-?\s*bye|bye(?:\s*-?\s*bye)?|that'?s\s+(?:all|it)|that\s+is\s+all"
    r"|nothing\s+(?:else|more)|i'?m\s+done|we'?re\s+done|see\s+you|end\s+(?:the\s+)?call"
    r"|hang\s+up)\b|ಬೈ|ಹೋಗಿ\s*ಬರ|ಅಷ್ಟೇ|ಸಾಕು",
    re.IGNORECASE,
)
"""Words with which a visitor ends the call: "bye", "that's all", "nothing
else", "ಬೈ", "ಅಷ್ಟೇ" (that's all). ``end_call`` closes the call only after them,
so a model that misreads a plain "thank you" cannot hang up on a visitor."""

_SEARCHES_PER_TURN = 2
"""A broad question may take a second search in other words; never a third."""

_KAN_TEXT_CHARS = 120
"""The longest a name or a sector may be on the KAN form."""

_YES = re.compile(
    r"\b(?:yes|yeah|yep|yup|correct|right|ok|okay|sure|confirm(?:ed)?|perfect)\b"
    r"|ಹೌದು|ಸರಿ|\bhaudu\b|\bsari\b",
    re.IGNORECASE,
)
_NO = re.compile(r"\b(?:no|nope|wrong|incorrect|not)\b|ಇಲ್ಲ|\billa\b", re.IGNORECASE)


def _said_yes(text: str) -> bool:
    """Whether the visitor's words confirm what was read back to them."""
    return bool(_YES.search(text)) and not _NO.search(text)


def _kan_mobile(value: str) -> str | None:
    """An Indian mobile number as ten digits, from however it was said: spaces,
    dashes and a +91, 91 or 0 in front are dropped. ``None`` for anything else."""
    digits = re.sub(r"[\s\-().]", "", value)
    digits = re.sub(r"^(?:\+91|0091|91(?=\d{10}$)|0(?=\d{10}$))", "", digits)
    return digits if re.fullmatch(r"[6-9]\d{9}", digits) else None


def _kan_email(value: str) -> str | None:
    """An email address in lower case, if it has the shape of one."""
    email = re.sub(r"\s+", "", value).lower()
    return email if re.fullmatch(r"[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)*\.[a-z]{2,}", email) else None


_KAN_PLACES: dict[str, str] = {
    "bangalore": "bengaluru",
    "ಬೆಂಗಳೂರು": "bengaluru",
    "mysore": "mysuru",
    "ಮೈಸೂರು": "mysuru",
    "mangalore": "mangaluru",
    "ಮಂಗಳೂರು": "mangaluru",
    "hubli": "hubballi",
    "ಹುಬ್ಬಳ್ಳಿ": "hubballi",
    "ಧಾರವಾಡ": "dharwad",
    "belgaum": "belagavi",
    "ಬೆಳಗಾವಿ": "belagavi",
}
"""Other spellings of the form's cities: older English names and Kannada."""
_KAN_FILLER = frozenset({"the", "in", "at", "a", "an", "and", "for", "of", "location", "centre"})


def _kan_words(text: str) -> list[str]:
    words: list[str] = re.findall(r"[a-z0-9]+|[\u0c80-\u0cff]+", text.casefold())
    return [_KAN_PLACES.get(w) or w for w in words if w not in _KAN_FILLER]


def _kan_location(value: str) -> list[str]:
    """The drop-down options ``value`` names: the one it spells, else every
    option holding all its words (a city, an incubator, or both)."""
    want = _kan_words(value)
    if not want:
        return []
    exact = [o for o in KAN_LOCATIONS if _kan_words(o) == want]
    if exact:
        return exact
    return [o for o in KAN_LOCATIONS if all(w in _kan_words(o) for w in want)]


def _squash(text: str) -> str:
    """Text as compared for pointing: whitespace collapsed, case folded."""
    return re.sub(r"\s+", " ", text).strip().casefold()


def _page(url: str) -> tuple[str, str] | None:
    """The canonical URL and title of the page ``url`` names, if Aria may link it.

    A page the index holds now (aliases fold into it): an approved page the last
    refresh read, under the list's title, a news or event page it added, or a
    PDF an approved page links to, under its link text. A PDF on another site is
    sent as the approved page that links it. A
    page on the list that the refresh dropped (gone from the sitemap, a 404, or a
    redirect elsewhere) is ``None``. Until the first index exists the one page
    sent is Contact Us, so the don't-know answer still has its link. Anything
    else, including every URL off the site, is ``None``."""
    if (theirs := pdf_url(url)) is not None and off_site(theirs):
        # A PDF on another site: the snippet shows only karnatakadigital.in, so
        # the card is the approved page that links it, if the index holds it.
        return _via(theirs)
    if theirs is not None and (offered := ALLOWLIST.offered_by(theirs)) is not None:
        # A policy KDEM hands out through its own page's download form: the
        # card is that page, so the visitor gets it the way KDEM offers it.
        return _page(offered.url) if KNOWLEDGE.kb.page(theirs) is not None else None
    canonical = ALLOWLIST.canonical(url)
    if canonical is None or ALLOWLIST.is_excluded(canonical):
        return None
    approved = ALLOWLIST.approved(canonical)
    if not (KNOWLEDGE.snapshot.built_at or len(KNOWLEDGE.kb)):
        if approved is not None and approved.url == ALLOWLIST.contact_url:
            return approved.url, approved.title
        return None
    if (indexed := KNOWLEDGE.kb.page(canonical)) is None:
        return None
    if approved is not None:
        return approved.url, approved.title
    return indexed.url, indexed.title or path_of(indexed.url)


def _source(p: Passage) -> str:
    """How a search result names where it came from: a page by its title, a PDF
    as a document, with the page the passage is on and, for a PDF on another
    site, that site and the KDEM page that links it."""
    if p.kind != "pdf":
        return p.title
    where = "PDF document"
    if off_site(p.url):
        where += f" on {host_of(p.url)}"
    if p.page:
        where += f", page {p.page}"
    source = f"{p.title} ({where})"
    if off_site(p.url) and (via := _via(p.url)) is not None:
        source += f', linked from the KDEM page "{via[1]}"'
    elif (offered := ALLOWLIST.offered_by(p.url)) is not None:
        source += f', downloaded from the KDEM page "{offered.title}"'
    return source


def _via(url: str) -> tuple[str, str] | None:
    """For a PDF on another site that the index holds: the approved KDEM page
    that links it, which is what the snippet can show."""
    indexed = KNOWLEDGE.kb.page(url)
    if indexed is None or indexed.kind != "pdf" or not off_site(indexed.url):
        return None
    return _page(indexed.via) if indexed.via else None


def _where_they_are(path: str, *, moved: bool) -> str:
    """One line on the page the visitor has open: by its own title and path when
    it is a page Aria may link now, else only "a page of the site". Nothing the
    browser sent is quoted."""
    known = _page(path)
    if known is None:
        return "The visitor is now on a page of the site." if moved else ""
    url, title = known
    if moved:
        return f'The visitor is now on the page "{title}" ({path_of(url)}).'
    return f'The visitor opened you on the page "{title}" ({path_of(url)}).'


def _where_they_started(init: dict[str, Any]) -> str:
    """One line on the page the visitor opened Aria from, for the prompt.

    ``page`` comes from the visitor's browser, so it is named only when it is a
    page Aria may link now, and then by that page's own title and path. Anything
    else is left out: the prompt never quotes what the browser sent."""
    raw = init.get("page")
    if not isinstance(raw, str) or not raw:
        return ""
    return _where_they_are(raw, moved=False)


class KdemBrain(GeminiBrain):
    """One per session. Aria: KDEM's approved pages, and this visitor's call."""

    def __init__(self, *, client: genai.Client, model: str = DEFAULT_MODEL) -> None:
        super().__init__(client=client, system_instruction=_prompt(), model=model)
        #: The language the voice is speaking, for the line the brain says when
        #: the model's turn acted and said nothing.
        self.spoken: Language = OPENING.code
        self._fallback = FallbackLine()
        #: Her own lines this turn that offer a page, by line: said aloud, the
        #: page counts as offered, so the visitor's yes takes them there.
        self._offer_lines: dict[str, str] = {}
        #: The page the visitor has open, as a site URL; ``None`` until known.
        self.here: str | None = None
        #: The WHERE THEY ARE line the prompt carries now.
        self._where = ""
        #: A toggle switch's written confirmation, said when Aria next has the floor.
        self._confirm: str | None = None
        #: A switch the model asked for with ``set_language``, made when its
        #: response has streamed, still inside the turn.
        self._pending: LanguageSpeech | None = None
        #: The visitor's turns so far, and what they said in the latest.
        self._turn = 0
        self._heard = ""
        #: The page Aria offered to take them to, and in which turn.
        self._offered: tuple[str, int] | None = None
        #: The page she took them to, until they arrive there, and in which turn.
        self._took_to: str | None = None
        self._took_turn = 0
        #: A phrase to point at on that page, sent when they arrive there.
        self._point_on_arrival: str | None = None
        #: The phrase she last pointed at, for a page that could not show it.
        self._pointed: str | None = None
        #: KAN form: who filled each field ("aria" or "visitor"), and a mobile
        #: number or email read back and waiting for the visitor's yes.
        self._kan: dict[KanField, str] = {}
        self._kan_pending: dict[KanField, tuple[str, int]] = {}
        #: Searches made in the latest visitor turn: (turn, how many).
        self._searches: tuple[int, int] = (0, 0)
        #: The visitor said goodbye and she said hers: the call closes once the
        #: turn's speech is out, so nothing after it is answered.
        self._ending = False
        #: Don't-know replies this call, and the team lead said last, so the
        #: same line is never said twice running.
        self._dont_knows = 0
        self._last_lead: str | None = None

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        # Aria's voice — not the page's to choose, so it is settled here rather
        # than sent with the connect request. Both legs move together; the voice
        # is gauri in English and Kannada alike. This lands before the greeting.
        # The one thing the page may ask for is the language the visitor picked
        # on the toggle before the call: "kn" opens in Kannada, anything else in
        # English.
        init = dict(session.init or {})
        opening = BY_TAG["kn"] if init.get("lang") == "kn" else OPENING
        await session.configure(
            Config(
                stt=SttConfig(language=opening.code, patience=PATIENCE),
                tts=TtsConfig(voice=opening.voice, language=opening.code),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
            )
        )
        self.spoken = opening.code
        # One keeper per process: the first session starts it, the rest find it
        # running. It never makes this session wait.
        KNOWLEDGE.start()

        self._where = _where_they_started(init)
        self.system_instruction = _prompt(self._where, self.spoken)
        if isinstance(page := init.get("page"), str):
            self.here = normalize(page)
        logger.info(
            "kdem: session start (surface={}, page={}, lang={}, pages indexed={})",
            init.get("surface"),
            init.get("page"),
            init.get("lang"),
            len(KNOWLEDGE.kb),
        )

    async def greet(self, session: Session) -> str:
        """The opener, written not generated, in the language the call opens in."""
        return _GREETING_KN if self.spoken == Language.KN else _GREETING

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[Speech, None]:
        """Count the turn and keep what was said, for ``go_to_page``'s rule;
        then the model's turn."""
        self._turn += 1
        self._heard = msg.text
        self._offer_lines = {}
        async for event in super().on_user_message(session, msg):
            yield event

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The model's turn, and a line of Aria's own if it acted and said nothing.
        See :mod:`voqalize_demos.silent_turn`.

        A language switched on the toggle is confirmed first, in the new language,
        with its written line: a brain has no floor outside a turn, so this is the
        first moment Aria may speak, and it never talks over anyone.

        A language the model switched with ``set_language`` is switched last:
        once its response has streamed (it says nothing with the call), both legs
        move in one awaited request, and only then is the written line said, so
        the new voice reads it. It is the end of the same turn, so there is no
        dead air, and the visitor speaks next."""
        if (left := self._pending) is not None:
            # A switch asked for in a turn the visitor cut short: made now, quietly.
            self._pending = None
            await self._move(session, left, by="you, on what the visitor said")
        if (line := self._confirm) is not None:
            self._confirm = None
            async for event in say_line(self, line):
                yield event
        said: list[str] = []
        async for event in self._fallback.speak_if_silent(self, super().respond(session)):
            if isinstance(event, SpeechChunk):
                said.append(event.text)
                if url := self._offer_lines.get(event.text):
                    # Her own line offered this page: the visitor's yes takes them there.
                    self._offered = (url, self._turn)
            yield event
        self._count_dont_know("".join(said))
        if (speech := self._pending) is not None:
            self._pending = None
            if await self._move(session, speech, by="you, on what the visitor said"):
                async for event in say_line(self, SWITCH_LINE[speech.tag]):
                    yield event
        if self._ending:
            # After everything yielded is on the wire, so the goodbye is heard
            # in full; whatever the microphone picks up after it gets no reply.
            logger.info("kdem: call ended after the goodbye")
            session.end("goodbye")

    async def _move(self, session: Session, speech: LanguageSpeech, *, by: str) -> bool:
        """Move both legs to ``speech`` in one awaited request, and record it.
        ``False`` when Voqalize refused it: the page is told the language that
        still holds, and nothing else changes."""
        try:
            await session.configure(
                Config(
                    stt=SttConfig(language=speech.code, patience=PATIENCE),
                    tts=TtsConfig(voice=speech.voice, language=speech.code),
                )
            )
        except RequestRejected as rejected:
            logger.warning("kdem: switch to {} refused: {}", speech.name, rejected)
            session.dispatch(LanguageChanged(language=BY_CODE[self.spoken].tag))
            return False
        self._switched(speech, by=by, note=by.startswith("the visitor"))
        return True

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Browser→brain: the page the visitor has open. Folded in silently: no
        floor taken and no turn, so a page load never makes Aria speak; the
        model reads where they are with the visitor's next turn. Unknown events
        and payloads that do not fit are dropped by the parser."""
        event = KDEM_EVENTS.parse(msg)
        if event is None:
            return
        match event:
            case PageViewed():
                self._viewed(event)
            case LanguageRequested():
                await self._requested(session, event)
            case KanFieldChanged():
                self._kan_changed(event)
            case MicPermission():
                # Counted from the log; the model is not told: a visitor with no
                # microphone cannot speak the turn it would answer.
                logger.info("kdem: mic_permission {} after {} ms", event.outcome, event.waited_ms)
            case KanFillFailed():
                label = KAN_LABELS[event.field]
                logger.info("kdem: kan_fill_failed {} ({})", event.field, event.reason)
                note = (
                    f'[The form could not take "{label}" ({event.reason.replace("_", " ")}). '
                    "Tell them plainly, and ask them to type it in themselves.]"
                )
                self.append_to_context(types.Content(role="user", parts=[types.Part(text=note)]))
            case PointMissed():
                # Only for the phrase she pointed at: never a line the page made up.
                if event.text == self._pointed:
                    note = (
                        f'[The page could not show "{event.text}": no part of it on screen '
                        "holds that text. Say where it is in words instead.]"
                    )
                    self.append_to_context(
                        types.Content(role="user", parts=[types.Part(text=note)])
                    )

    async def _requested(self, session: Session, event: LanguageRequested) -> None:
        """The visitor pressed the other language on the toggle. Switched in code,
        not through the model: both legs move in one awaited request, the page
        is told, and the written confirmation waits for Aria's next turn. Asking
        for the language the call is already in does nothing."""
        speech = BY_TAG[event.language]
        if speech.code == self.spoken:
            return
        # A refusal puts the toggle back to the language that holds.
        if await self._move(session, speech, by="the visitor, on the page's toggle"):
            self._confirm = TOGGLE_CONFIRM[speech.tag]

    def _switched(self, speech: LanguageSpeech, *, by: str, note: bool = True) -> None:
        """Record a switch that has been sent, tell the page, and (from a
        callback) leave the model one line about it. Shared by the toggle and
        ``set_language``, so the two cannot disagree about what a switch does.
        A tool leaves no note: its own result is the model's record, and a line
        filed mid-turn would land between a call and its result."""
        logger.info("kdem: language {} -> {} (by {})", BY_CODE[self.spoken].name, speech.name, by)
        self.spoken = speech.code
        self._confirm = None
        self.session.dispatch(LanguageChanged(language=speech.tag))
        self.system_instruction = _prompt(self._where, self.spoken)
        if note:
            line = f"[The call is now in {speech.name.capitalize()}, switched by {by}.]"
            self.append_to_context(types.Content(role="user", parts=[types.Part(text=line)]))

    def _kan_changed(self, event: KanFieldChanged) -> None:
        """The visitor filled a field of the KAN form themselves: remember it is
        theirs, so it is not overwritten without asking, and tell the model. A
        mobile number or email is never repeated into the context or the log."""
        value = re.sub(r"\s+", " ", event.value).strip()[:_KAN_TEXT_CHARS]
        label = KAN_LABELS[event.field]
        logger.info("kdem: kan_field_changed {}", event.field)
        self._kan_pending.pop(event.field, None)
        if not value:
            self._kan.pop(event.field, None)
            line = f'[The visitor cleared "{label}" on the form.]'
        else:
            self._kan[event.field] = "visitor"
            if event.field in ("mobile", "email"):
                line = f'[The visitor filled in "{label}" on the form themselves.]'
            else:
                line = f'[The visitor filled in "{label}" on the form themselves: "{value}".]'
        self.append_to_context(types.Content(role="user", parts=[types.Part(text=line)]))

    def _viewed(self, event: PageViewed) -> None:
        here = normalize(event.path)
        if here is None or here == self.here:
            # Not a page of this site, or the one already known: the reconnect
            # on the page the call started on says nothing new.
            return
        self.here = here
        line = self._where = _where_they_are(event.path, moved=True)
        waiting, self._point_on_arrival = self._point_on_arrival, None
        if self._took_to is not None and ALLOWLIST.canonical(here) == self._took_to:
            self._took_to = None
            line += (
                " You took them here: carry on the conversation where it was, pointing at "
                "the part they need, and do not greet them again."
            )
            if waiting is not None:
                # The point she made while the page was loading: shown now it is here.
                self._pointed = waiting
                self.session.dispatch(PointAt(text=waiting))
                logger.info("kdem: point_at {!r} on {} (on arrival)", waiting, path_of(here))
                line += f' What you pointed at ("{waiting}") is highlighted now.'
        elif waiting is not None:
            logger.info("kdem: point_at {!r} dropped: they went elsewhere", waiting)
        logger.info(
            "kdem: page_viewed {} ({})", path_of(here), "named" if _page(here) else "unnamed"
        )
        self.system_instruction = _prompt(line, self.spoken)
        self.append_to_context(types.Content(role="user", parts=[types.Part(text=f"[{line}]")]))

    # ─── Tools ──────────────────────────────────────────────────────────
    #
    # All read memory and return inside the tool budget. Only the search is
    # marked: Aria cannot answer without what it returns. The rest are spoken
    # with, in the same response; set_language's line is the brain's.

    @property
    def tools(self) -> list[Any]:
        """Search the approved pages, offer one as a link, take the visitor to one
        (asking first), point at part of the page they are on, change language."""
        return [
            self.search_kdem,
            self.show_document,
            self.fill_kan_field,
            self.offer_page,
            self.go_to_page,
            self.point_at,
            self.set_language,
            self.end_call,
        ]

    def _say(self, what: Said, *, offers: str | None = None, **names: str) -> None:
        """Land her own line for this call, in the language the voice speaks:
        said only if the turn ends with nothing said. A line that offers a page
        (``offers``) makes it the page offered, once it has been said."""
        line = LINES[what][self.spoken].format(**names)
        landed(line)
        if offers is not None:
            self._offer_lines[line] = offers

    def _offer(self, dest: str, title: str, what: Said = "offer") -> None:
        """Offer ``dest`` now: the visitor's next turn is the yes."""
        self._offered = (dest, self._turn)
        self._say(what, title=_spoken_title(title))

    def _here(self) -> str | None:
        return ALLOWLIST.canonical(self.here) if self.here else None

    def _going_to(self) -> str | None:
        """The page she sent them to that has not opened yet: sent this turn or
        the one before, and no page_viewed for it since. Older than that, the
        move is taken not to have happened."""
        took = self._took_to
        if took is None or took == self._here() or self._turn - self._took_turn > 1:
            return None
        return took

    def _cant_open(self) -> None:
        """Her line for a page she may not open: Contact Us instead, as the
        don't-know answer offers it, or its details when they are on it."""
        contact = _page(ALLOWLIST.contact_url)
        if contact is None:
            self._say("cant_open")
        elif contact[0] == self._here():
            self._say("cant_open_here")
        else:
            self._say("cant_open_offer", offers=contact[0], title=_spoken_title(contact[1]))

    def _count_dont_know(self, said: str) -> None:
        """Count a reply that was a don't-know, the model's or her own, and
        remember which team lead it used."""
        text = said.casefold()
        if not any(marker in text for marker in _NOT_KNOWN):
            return
        self._dont_knows += 1
        for leads in TEAM_LEADS.values():
            for lead in leads:
                if lead.casefold() in text:
                    self._last_lead = lead
        logger.info("kdem: dont_know #{} this call", self._dont_knows)

    def _team_lead(self) -> str:
        """The team lead for the next don't-know: not the one said last."""
        leads = TEAM_LEADS[self.spoken]
        return leads[1] if self._last_lead == leads[0] else leads[0]

    def _dont_know(self) -> None:
        """Her line for a search with nothing to say: the don't-know line, with
        Contact Us offered, or pointed out when they are on it. After the first
        in a call, the team's line instead, never the same one twice running."""
        contact = _page(ALLOWLIST.contact_url)
        if self._dont_knows:
            lead = self._team_lead()
            if contact is None:
                self._say("team", lead=lead)
            elif contact[0] == self._here():
                self._say("team_here", lead=lead)
            else:
                self._say(
                    "team_offer", offers=contact[0], lead=lead, title=_spoken_title(contact[1])
                )
        elif contact is None:
            self._say("dont_know")
        elif contact[0] == self._here():
            self._say("dont_know_here")
        else:
            self._say("dont_know_offer", offers=contact[0], title=_spoken_title(contact[1]))

    def _not_known(self) -> str:
        """What a search result tells the model to say when the pages do not
        answer: the don't-know line the first time in a call, the team's line
        after that, so she never says the same thing twice running."""
        offer = (
            f"offer to take them to the Contact Us page ({CONTACT_PATH}) with offer_page, or "
            "point at it with point_at if they are already there"
        )
        if not self._dont_knows:
            return f'say: "{DONT_KNOW}" and {offer}.'
        return (
            "you have already told them once in this call that the website does not have "
            f'something, so do not say "{DONT_KNOW}" again. Say: "{self._team_lead()}" and '
            f"{offer}."
        )

    def _destination(self, url: str, tool: str) -> tuple[str, str] | str:
        """The page ``url`` would take the visitor to, as ``(url, title)``, or the
        sentence that says why not: the same rules as ``show_document``, a PDF on
        another site going to the KDEM page that links it, and only pages, since a
        PDF in this tab would leave the call behind. A refusal is logged, and
        lands her line that says it."""
        found = _page(url)
        if found is None:
            logger.info("kdem: {} {!r} refused: not an approved page", tool, url)
            self._cant_open()
            return (
                f"Not sent: {url!r} is not one of the approved KDEM pages. Offer a page "
                f"search_kdem returned, or the Contact Us page ({CONTACT_PATH})."
            )
        dest, title = found
        if is_pdf(dest):
            logger.info("kdem: {} {} refused: a PDF", tool, path_of(dest))
            self._say("pdf_not_page")
            return "Not sent: a PDF opens beside you with show_document; go_to_page is for pages."
        if dest == self._here():
            logger.info("kdem: {} {} refused: already there", tool, path_of(dest))
            self._say("already_here", title=_spoken_title(title))
            return f'They are already on "{title}". Point at the part they need with point_at.'
        return dest, title

    async def offer_page(self, request: PageRequest) -> str:
        """Offer to take the visitor to another page of the site. Say your one short
        question ("Shall I take you to the Seed Fund page?") and call this in the
        same response; nothing moves until they say yes."""
        found = self._destination(request.url, "offer_page")
        if isinstance(found, str):
            return found
        self._offer(*found)
        logger.info("kdem: offer_page {}", path_of(found[0]))
        return "Offered. When they say yes, call go_to_page with this page."

    async def go_to_page(self, request: PageRequest) -> str:
        """Take the visitor to another page of the site, in this tab; the call
        carries on there. Only a page you offered in your last turn and they said
        yes to, or one they asked to be taken to in this turn. Say one short line
        ("Taking you there.") and call this in the same response."""
        found = self._destination(request.url, "go_to_page")
        if isinstance(found, str):
            return found
        dest, title = found
        offered = self._offered
        said_yes = offered is not None and offered[0] == dest and offered[1] == self._turn - 1
        if not (said_yes or _ASKS_TO_GO.search(self._heard)):
            # Not asked for: made the offer instead, so their yes takes them there.
            logger.info(
                "kdem: go_to_page {} refused: not offered or asked for; offered instead",
                path_of(dest),
            )
            self._offer(dest, title)
            return (
                f'Not sent yet: they did not ask to go, so it is offered to them instead: "Shall '
                f'I take you to the {_spoken_title(title)} page?" When they say yes, call '
                "go_to_page with it."
            )
        self._offered = None
        self._took_to, self._took_turn = dest, self._turn
        self._point_on_arrival = None
        self.session.dispatch(Navigate(url=dest))
        logger.info(
            "kdem: go_to_page {} ({})", path_of(dest), "a yes" if said_yes else "they asked"
        )
        self._say("go", title=_spoken_title(title))
        return "ok: the page opens, and the call carries on there."

    async def point_at(self, request: PointRequest) -> str:
        """Point at part of the page the visitor has open: it scrolls into view and
        lights up. Pass a short exact phrase from that page. No need to ask; say
        one short line ("Eligibility is right here.") and call this with it."""
        text = re.sub(r"\s+", " ", request.text).strip()
        if not text:
            logger.info("kdem: point_at refused: no phrase")
            self._say("point_miss")
            return "Not shown: pass a short phrase from the page they are on."
        if len(text) > _POINT_CHARS:
            logger.info("kdem: point_at refused: {} characters", len(text))
            self._say("point_miss")
            return f"Not shown: pass a shorter phrase, under {_POINT_CHARS} characters."
        # The page she has just taken them to is still loading: the point is
        # checked against that page, and sent when it has opened.
        going = self._going_to()
        where = going or self.here
        page = KNOWLEDGE.kb.page(where) if where else None
        if page is None:
            logger.info("kdem: point_at {!r} refused: no text for the page they are on", text)
            self._say("point_miss")
            return "Not shown: I do not have the text of the page they are on."
        if _squash(text) not in _squash(f"{page.title}\n{page.text}"):
            logger.info("kdem: point_at {!r} refused: not on {}", text, path_of(page.url))
            self._say("point_miss")
            return (
                f"Not shown: {text!r} is not on the page they are "
                f"{'going to' if going else 'on now'} ({page.title}). "
                "Pass a phrase from that page, or offer to take them to the page that has it."
            )
        if going is not None:
            self._point_on_arrival = text
            logger.info("kdem: point_at {!r} waits for {} to open", text, path_of(page.url))
            self._say("point_soon", text=_spoken_text(text))
            return "ok: the page is still opening; it lights up as soon as it has."
        self._pointed = text
        self.session.dispatch(PointAt(text=text))
        logger.info("kdem: point_at {!r} on {}", text, path_of(page.url))
        self._say("point", text=_spoken_text(text))
        return "ok"

    @needs_result_now
    async def search_kdem(self, request: SearchRequest) -> str:
        """Search KDEM's approved website pages and the PDF documents they link to.
        Call it before answering any question about KDEM, its programmes, policies,
        events, reports or news, and answer only from what it returns."""
        # Her line should the turn end with nothing said after the search: the
        # model found nothing in it worth saying, so it is the don't-know line.
        self._dont_know()
        turn, done = self._searches
        done = done + 1 if turn == self._turn else 1
        self._searches = (self._turn, done)
        if done > _SEARCHES_PER_TURN:
            logger.info("kdem: search {!r} refused: a third search this turn", request.query)
            return (
                "Not searched: that is two searches this turn. Answer from what came back, "
                f"or {self._not_known()}"
            )
        kb = KNOWLEDGE.kb
        if len(kb) == 0:
            logger.warning("kdem: search with an empty knowledge base")
            return (
                "The website's pages are not available right now, so there is nothing to "
                f"answer from. So {self._not_known()}"
            )
        passages = kb.search(request.query, k=_PASSAGES)
        logger.info("kdem: search {!r} -> {} passages", request.query, len(passages))
        if not passages:
            return f"Nothing on the approved pages matches. So {self._not_known()}"
        found = "\n\n".join(
            f"[{i}] {_source(p)}\nurl: {p.url}\n{p.snippet}" for i, p in enumerate(passages, 1)
        )
        return (
            "From karnatakadigital.in. Answer only from this. If it answers part of the "
            "question, say that part and that the KDEM team can tell them the rest; if it "
            f"answers none of it, {self._not_known()}\n\n{found}"
        )

    def _kan_next(self) -> str:
        left = [KAN_LABELS[f] for f in KAN_LABELS if f not in self._kan]
        if not left:
            return "Every field is filled: ask them to check the form and press Apply Now."
        return f'Next, ask for "{left[0]}".'

    async def fill_kan_field(self, request: KanFillRequest) -> str:
        """Put one answer into the KAN application form on the page they are on.
        Say a short line and call this with each answer as it comes. A mobile
        number or email is read back first and goes in after their yes, when you
        call this again with it. The form is sent by the visitor, never by you."""
        field = request.field
        here = ALLOWLIST.canonical(self.here) if self.here else None
        if here != KAN_URL:
            logger.info("kdem: fill_kan_field {} refused: not on the KAN page", field)
            if (kan := _page(KAN_URL)) is not None:
                self._offer(kan[0], kan[1], "kan_elsewhere")
            return (
                "Not filled: the form is on the Karnataka Acceleration Network page. "
                f"Offer to take them there with offer_page ({path_of(KAN_URL)}) first."
            )
        if self._kan.get(field) == "visitor" and not request.replace:
            return (
                f'Not filled: they typed "{KAN_LABELS[field]}" themselves. Ask before changing '
                "it; if they say to, call again with replace set to true."
            )
        value: str | None
        if field == "mobile":
            value = _kan_mobile(request.value)
            if value is None:
                logger.info("kdem: fill_kan_field mobile refused: not a mobile number")
                self._say("say_again")
                return (
                    "Not filled: that is not a ten-digit Indian mobile number. "
                    "Ask them to say it again."
                )
        elif field == "email":
            value = _kan_email(request.value)
            if value is None:
                logger.info("kdem: fill_kan_field email refused: not an email address")
                self._say("say_again")
                return "Not filled: that is not an email address. Ask them to say it again."
        elif field == "location":
            options = _kan_location(request.value)
            if len(options) > 1:
                return "Not filled: more than one matches. Ask which: " + "; ".join(options) + "."
            if not options:
                return (
                    "Not filled: that is not one of the form's locations. They are: "
                    + "; ".join(KAN_LOCATIONS)
                    + "."
                )
            value = options[0]
        else:
            value = re.sub(r"\s+", " ", request.value).strip()
            if not value:
                logger.info("kdem: fill_kan_field {} refused: empty", field)
                self._say("say_again")
                return "Not filled: there is nothing to put in. Ask them again."
            if len(value) > _KAN_TEXT_CHARS:
                return f"Not filled: keep it under {_KAN_TEXT_CHARS} characters."
        if field in ("mobile", "email"):
            # Read back, then filled on the yes: what was read back in the
            # visitor's last turn, confirmed in this one.
            pending = self._kan_pending.get(field)
            confirmed = (
                pending is not None
                and pending == (value, self._turn - 1)
                and _said_yes(self._heard)
            )
            if not confirmed:
                self._kan_pending[field] = (value, self._turn)
                logger.info("kdem: fill_kan_field {} read back, waiting for a yes", field)
                return (
                    "Not in the form yet: read it back to them in one short line and ask if it "
                    "is right; when they say yes, call fill_kan_field with it again."
                )
            self._kan_pending.pop(field, None)
        self._kan[field] = "aria"
        self.session.dispatch(KanFill(field=field, value=value))
        logger.info("kdem: kan_fill {}", field)
        self._say("filled", label=KAN_SPOKEN[self.spoken][field])
        return f"Filled. {self._kan_next()}"

    async def show_document(self, request: DocumentRequest) -> str:
        """Show a PDF document beside you as a card; it opens in a new tab. Name the
        document and the page in your one or two sentences and call this in the
        same response. For PDFs that search_kdem returned; pages are visited."""
        found = _page(request.url) if pdf_url(request.url) is not None else None
        if found is None:
            if (page := _page(request.url)) is not None:
                logger.info("kdem: show_document {!r} refused: a page", request.url)
                if (dest := page[0]) != self._here():
                    self._offer(dest, page[1])
                    return (
                        "Not sent: pages are visited, not shown, so it is offered to them "
                        f'instead: "Shall I take you to the {_spoken_title(page[1])} page?" '
                        "When they say yes, call go_to_page with it."
                    )
                self._say("already_here", title=_spoken_title(page[1]))
                return (
                    "Not sent: pages are visited with offer_page / go_to_page; "
                    "show_document is for PDFs. They are on that page already."
                )
            logger.info("kdem: show_document {!r} refused: not an approved document", request.url)
            self._say("document_refused")
            return (
                f"Not sent: {request.url!r} is not one of the approved KDEM documents. "
                "Show a PDF search_kdem returned."
            )
        url, title = found
        # Sent as the snippet's "show_link" card: the wire name it already renders.
        self.session.dispatch(ShowLink(url=url, title=title))
        logger.info("kdem: show_document {}", path_of(url))
        self._say("document", title=_spoken_title(title))
        return "ok"

    async def end_call(self) -> str:
        """End the call after the visitor says goodbye. Say your short goodbye and
        call this in the same response; the call closes once it has been heard.
        Only when they said goodbye or that they are done, never on a plain thank
        you."""
        if not _GOODBYE_HEARD.search(self._heard):
            logger.info("kdem: end_call refused: the visitor did not say goodbye")
            return "Not ended: they did not say goodbye. Carry on the conversation."
        self._ending = True
        logger.info("kdem: end_call")
        self._say("goodbye")
        return "ok: the call closes after your goodbye."

    async def set_language(self, request: LanguageRequest) -> str:
        """Conduct the rest of the call in English or Kannada — both the listening and
        the speaking. Call it when they ask, and when a turn looks like the other
        one. Call it alone and say nothing: the voice changes when your response
        ends, and then a written line is said for you in the new voice."""
        speech = SPEECH[request.language]
        if speech.code == self.spoken:
            self._pending = None
            return f"Already in {speech.name}. Carry on."
        if speech.code == Language.KN and not _KANNADA_HEARD.search(self._heard):
            # Nothing Kannada in it: a misheard turn, not a language.
            logger.info("kdem: set_language kannada refused: nothing Kannada was heard")
            self._say("say_again")
            return (
                "Not switched: nothing in what was heard is Kannada, so it was most likely "
                "misheard. Ask them to say it again, in English, and keep the call in English."
            )
        # Not sent here: a tool returns within its budget, and the switch has to
        # land before the line the new voice says. respond() makes it, awaited,
        # once this response has streamed.
        self._pending = speech
        logger.info("kdem: set_language {} (made when the response ends)", speech.name)
        return (
            f"Switching to {speech.name}. A written line is said for you in the new voice; "
            f"say nothing more. Speak {speech.name} from the visitor's next turn."
        )


__all__ = [
    "DONT_KNOW",
    "IDENTITY",
    "SWITCH_LINE",
    "TOGGLE_CONFIRM",
    "KanFill",
    "KdemBrain",
    "LanguageChanged",
    "Navigate",
    "PointAt",
    "ShowLink",
]
