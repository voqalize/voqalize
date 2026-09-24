"""English, spoken to a recognizer listening for an Indian language.

The recognizer is pinned to the call's language. Speak English to the Kannada
one and it does not fail: it writes what it heard in Kannada script —
"I want to speak in English" arrives as "ಐ ವಾಂಟ್ ಟು ಸ್ಪೀಕ್ ಇನ್ ಇಂಗ್ಲಿಷ್". The
model can read that, and usually does. But in a live eval it answered such a
turn in English about one time in three *without* calling ``switch_language``,
which leaves the voice and the recognizer in the old language while the words
change — the silent half-applied pair, and the customer's next sentence is
mangled again.

So this is checked in Python, before the model runs, and it is deliberately
narrow. It counts English **grammar** words — I, am, is, the, a, in, to, want —
spelled in the script the recognizer writes. Nouns prove nothing: salary,
company, card and fuel are borrowed into every Indian language, and "ನಾನು
ಸ್ಯಾಲರೀಡ್ ಎಂಪ್ಲಾಯಿ" is Kannada. Words that are borrowed as freely as nouns —
yes, no, okay, sorry — are left out for the same reason.

A turn is English when at least two of its words are on the list and they make
up at least a third of it. Anything less is left to the model, which asks the
customer when it is not sure. Only Indian scripts are read: a recognizer set to
an Indian language writes in that language's script, and a Latin-alphabet turn
is left to the model too.
"""

from __future__ import annotations

import re

__all__ = ["reads_as_english"]

#: English grammar words as each recognizer spells them. One line per word, in the
#: order the English reads, so a gap in one script is visible against the others.
_SPELLED: dict[str, tuple[str, ...]] = {
    # Kannada, Devanagari, Tamil, then Telugu spellings; a common variant sits beside its script.
    "i": ("ಐ", "आई", "ஐ", "ఐ"),
    # Not Tamil ஆம்: that is Tamil for "yes".
    "am": ("ಆಮ್", "ऍम", "एम", "ఆమ్"),
    "is": ("ಇಸ್", "ಈಸ್", "इज़", "इज", "இஸ்", "ఇస్"),
    "are": ("ಆರ್", "आर", "ஆர்", "ఆర్"),
    "the": ("ದಿ", "ದ", "द", "दि", "தி", "ది"),
    "a": ("ಎ", "ஏ", "ఎ"),
    "in": ("ಇನ್", "இன்", "ఇన్"),
    "to": ("ಟು", "ಟೂ", "टू", "டு", "டூ", "టు"),
    "want": ("ವಾಂಟ್", "वांट", "வாண்ட்", "వాంట్"),
    "can": ("ಕ್ಯಾನ್", "कैन", "கேன்", "క్యాన్"),
    "what": ("ವಾಟ್", "व्हाट", "वाट", "வாட்", "వాట్"),
    "please": ("ಪ್ಲೀಸ್", "प्लीज़", "प्लीज", "ப்ளீஸ்", "ప్లీజ్"),
    "my": ("ಮೈ", "माय", "மை", "మై"),
    "you": ("ಯು", "ಯೂ", "यू", "யூ", "యూ"),
    "we": ("ವಿ", "ವೀ", "वी", "வீ", "వీ"),
    "speak": ("ಸ್ಪೀಕ್", "स्पीक", "ஸ்பீக்", "స్పీక్"),
    "talk": ("ಟಾಕ್", "टॉक", "டாக்", "టాక్"),
    "english": ("ಇಂಗ್ಲಿಷ್", "ಇಂಗ್ಲೀಷ್", "इंग्लिश", "इंग्लिष", "இங்கிலீஷ்", "ఇంగ్లీష్"),
    "switch": ("ಸ್ವಿಚ್", "स्विच", "ஸ்விட்ச்", "స్విచ్"),
    "working": ("ವರ್ಕಿಂಗ್", "वर्किंग", "வொர்க்கிங்", "వర్కింగ్"),
    "how": ("ಹೌ", "हाउ", "ஹவ்", "హౌ"),
    "much": ("ಮಚ್", "मच", "மச்", "మచ్"),
    "with": ("ವಿತ್", "विद", "வித்", "విత్"),
    "for": ("ಫಾರ್", "फॉर", "ஃபார்", "ఫర్"),
    "and": ("ಅಂಡ್", "ಆಂಡ್", "एंड", "ஆண்ட்", "అండ్"),
    "do": ("ಡು", "डू", "டூ", "డు"),
    "this": ("ದಿಸ್", "दिस", "திஸ்", "దిస్"),
}

_WORDS = frozenset(spelling for spellings in _SPELLED.values() for spelling in spellings)

#: Anything but spaces, punctuation and the danda splits a word; curly quotes are
#: written as escapes so the pattern reads unambiguously.
_TOKEN = re.compile("[^\\s.,!?;:\u0964\u0965\"'\u201c\u201d\u2018\u2019()\\-]+")


def reads_as_english(text: str) -> bool:
    """Whether a turn is English, as a recognizer for another language wrote it."""
    tokens = [t.lower() for t in _TOKEN.findall(text)]
    if not tokens:
        return False
    hits = sum(1 for t in tokens if t in _WORDS)
    return hits >= 2 and hits * 3 >= len(tokens)
