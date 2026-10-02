"""The one line Tanvi says when the cards go up, written here and not generated.

The shortlist is the moment the visit turns from a form into advice, and the
customer is looking at three cards with a "best for you" mark on one of them. So
Tanvi says why that one, in one breath, the moment it is on the glass — and the
line is built here from the ranking's own reason and the card's own perk, with no
model call. It is instant, and it cannot invent a fee or promise an approval.

It is written in English and in Hindi, the two languages the greeting is written
in. Hindi is also what the voice speaks for every language no clip speaks, so a
customer in Odia hears this in Hindi, as they hear everything else. For the
languages with a voice of their own and no line here — Kannada, Tamil and the
rest — :func:`pitch_line` returns ``None`` and the brain has the model say the
English line in their language instead.

Every figure is in words, because this goes to the voice and never to the glass.
"""

from __future__ import annotations

from voqalize.sdk.wire import Language

from .cards import CARD_BY_ID, SPEND_SPOKEN, SpendCategory
from .eligibility import Shortlist

__all__ = ["pitch_line"]

#: Each card's name as the Hindi voice should read it. The voice reads the Latin
#: alphabet as English, so a Hindi sentence carries the name in Devanagari.
_NAME_HI: dict[str, str] = {
    "vantage_rise": "वैंटेज राइज़",
    "vantage_fuel": "वैंटेज फ़्यूल",
    "vantage_everyday": "वैंटेज एवरीडे",
    "vantage_voyage": "वैंटेज वॉयेज",
    "vantage_crest": "वैंटेज क्रेस्ट",
}

#: Each card's perk, in Hindi words. The English is ``Card.perk_spoken``.
_PERK_HI: dict[str, str] = {
    "vantage_rise": "यह आपकी फ़िक्स्ड डिपॉज़िट पर सुरक्षित है, और इसकी लिमिट उस डिपॉज़िट का अस्सी प्रतिशत है",
    "vantage_fuel": "पाँच सौ से चार हज़ार रुपये तक के फ़्यूल पर एक प्रतिशत सरचार्ज माफ़ होता है",
    "vantage_everyday": "रिवॉर्ड सीधे स्टेटमेंट क्रेडिट में आते हैं, कुछ रिडीम नहीं करना पड़ता",
    "vantage_voyage": "साल में अठारह घरेलू और बारह इंटरनेशनल लाउंज विज़िट मिलती हैं",
    "vantage_crest": "दुनिया भर में अनलिमिटेड लाउंज एक्सेस मिलता है, और साथ में एक मेहमान भी",
}

#: Where the money goes, as a Hindi sentence needs it after "पर".
_SPEND_HI: dict[SpendCategory, str] = {
    "fuel": "पेट्रोल",
    "groceries": "राशन",
    "online": "ऑनलाइन शॉपिंग",
    "travel": "यात्रा",
    "dining": "बाहर खाने",
    "bills": "बिलों",
}

# A card or a spend with no Hindi row would raise on a customer, so the tables
# are held to the shelf here instead.
assert set(_NAME_HI) == set(CARD_BY_ID) == set(_PERK_HI), "the Hindi pitch misses a card"
assert set(_SPEND_HI) == set(SPEND_SPOKEN), "the Hindi pitch misses a spend"


def pitch_line(ranked: Shortlist, spend: SpendCategory, language: Language) -> str | None:
    """Why the top card, in the language the voice speaks — or ``None`` when no
    line is written for that language."""
    card = CARD_BY_ID[ranked.recommended_id]
    if language == Language.EN:
        return (
            f"My pick for you is the {card.name}, because {ranked.why_spoken}. "
            f"On top of that, {card.perk_spoken}. A banker at the desk will confirm it."
        )
    if language == Language.HI:
        return (
            f"मेरी सलाह है {_NAME_HI[card.id]}, क्योंकि {_why_hi(ranked, spend)}। "
            f"साथ ही, {_PERK_HI[card.id]}। डेस्क पर बैंकर इसकी पुष्टि करेंगे।"
        )
    return None


def _why_hi(ranked: Shortlist, spend: SpendCategory) -> str:
    """The ranking's reason, in Hindi. It reads the same fact the English reason
    was built from, so the two cannot say different things."""
    if ranked.why == "affinity":
        return f"आपका सबसे ज़्यादा खर्च {_SPEND_HI[spend]} पर होता है, और यह कार्ड उसी पर सबसे ज़्यादा देता है"
    if ranked.why == "secured":
        return "यह आपकी अपनी डिपॉज़िट पर टिका है, इसलिए शुरुआत के लिए सबसे पक्का कार्ड है"
    return "यह आज आपकी प्रोफ़ाइल के लिए सबसे मज़बूत कार्ड है"
