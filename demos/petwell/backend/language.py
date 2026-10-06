"""The languages the Petwell desk speaks, and the one way to move between them.

Tushar's voice, ``omnivoice/gaurav``, speaks English and nine Indic languages
natively — the languages of the cities Petwell is in — so every language here is
heard and spoken in its own right. The voice never changes; only the language
does, and both legs always move in one request (:func:`config_for`), which is
the pairing rule.

The website itself is in English and Hindi. In any other language the voice
follows the caller and the page stays in English (:func:`screen_language_for`).
"""

from __future__ import annotations

from typing import Literal

from voqalize_demos import PHRASES, hello_for

from voqalize.sdk.wire import Config, IdleConfig, Language, SttConfig, TtsConfig, Voice

__all__ = [
    "GREETING",
    "LANGUAGE_CODE",
    "SWITCH_LINE",
    "VOICE",
    "LanguageName",
    "as_language",
    "config_for",
    "screen_language_for",
]

LanguageName = Literal[
    "English",
    "Hindi",
    "Bengali",
    "Gujarati",
    "Kannada",
    "Malayalam",
    "Marathi",
    "Punjabi",
    "Tamil",
    "Telugu",
]

#: The voice the page's avatar (``tushar``) is matched to. It speaks every
#: language below, so a switch never changes who the caller hears.
VOICE = Voice.OMNIVOICE_GAURAV

LANGUAGE_CODE: dict[LanguageName, Language] = {
    "English": Language.EN,
    "Hindi": Language.HI,
    "Bengali": Language.BN,
    "Gujarati": Language.GU,
    "Kannada": Language.KN,
    "Malayalam": Language.ML,
    "Marathi": Language.MR,
    "Punjabi": Language.PA,
    "Tamil": Language.TA,
    "Telugu": Language.TE,
}

# Every language here has written fallback lines, so a silent turn is covered in
# the language the call is in.
assert set(LANGUAGE_CODE.values()) <= set(PHRASES), "a language with no fallback phrases"

#: How long the caller has to be quiet before the desk may answer a tap.
IDLE_MS = 3000


def config_for(name: LanguageName) -> Config:
    """Both legs in one language, in one request — never one without the other."""
    code = LANGUAGE_CODE[name]
    return Config(
        stt=SttConfig(language=code),
        tts=TtsConfig(voice=VOICE, language=code),
        idle=IdleConfig(timeout_ms=IDLE_MS),
    )


def as_language(value: object) -> LanguageName | None:
    """A language named by the page (``"Hindi"``, ``"hi"``), or ``None``."""
    text = str(value or "").strip()
    for name, code in LANGUAGE_CODE.items():
        if text.lower() in (name.lower(), code.value):
            return name
    return None


def screen_language_for(name: LanguageName) -> Literal["en", "hi"]:
    """The website has English and Hindi copy; every other language reads English."""
    return "hi" if name == "Hindi" else "en"


_HOSPITAL = "Petwell Veterinary Hospitals"

#: Only the two languages the page can open a call in. Fixed, so the greeting is
#: spoken the instant the session connects, with no model call.
GREETING: dict[LanguageName, str] = {
    "English": (
        f"{hello_for('english')} I'm Tushar, the AI assistant at {_HOSPITAL}. I can book "
        "a clinic visit or a vet at home, find a branch, or walk you through our health "
        "hub — how can I help your pet today?"
    ),
    "Hindi": (
        f"{hello_for('hindi')} मैं तुषार हूँ, पेटवेल वेटरनरी हॉस्पिटल्स का ए आई असिस्टेंट। "
        "मैं क्लिनिक विज़िट या घर पर डॉक्टर की बुकिंग कर सकता हूँ, नज़दीकी ब्रांच बता सकता "
        "हूँ — बताइए, आपके पेट के लिए क्या करूँ?"
    ),
}

#: Said by the brain, in the new language, once the new voice is on — never by
#: the model, which writes before the voice changes and would be heard in the
#: language being left.
SWITCH_LINE: dict[LanguageName, str] = {
    "English": "Sure, let's continue in English. Go ahead.",
    "Hindi": "ज़रूर, अब हिंदी में बात करते हैं। बताइए।",
    "Bengali": "ঠিক আছে, এখন বাংলায় কথা বলি। বলুন।",
    "Gujarati": "ઠીક છે, હવે ગુજરાતીમાં વાત કરીએ. જણાવો.",
    "Kannada": "ಸರಿ, ಈಗ ಕನ್ನಡದಲ್ಲಿ ಮಾತಾಡೋಣ. ಹೇಳಿ.",
    "Malayalam": "ശരി, ഇനി മലയാളത്തിൽ സംസാരിക്കാം. പറയൂ.",
    "Marathi": "ठीक आहे, आता मराठीत बोलूया. सांगा.",
    "Punjabi": "ਠੀਕ ਹੈ, ਹੁਣ ਪੰਜਾਬੀ ਵਿੱਚ ਗੱਲ ਕਰਦੇ ਹਾਂ। ਦੱਸੋ।",
    "Tamil": "சரி, இனி தமிழில் பேசலாம். சொல்லுங்கள்.",
    "Telugu": "సరే, ఇప్పుడు తెలుగులో మాట్లాడదాం. చెప్పండి.",
}

assert set(SWITCH_LINE) == set(LANGUAGE_CODE), "a language with no switch line"
