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
    "NEXT_QUESTION",
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


#: The next booking question, in each language — what the desk says itself when
#: a turn moved the booking on screen and the model said nothing, so the visitor
#: hears where they are rather than a bare "go ahead".
NEXT_QUESTION: dict[LanguageName, dict[str, str]] = {
    "English": {
        "city": "Which city are you in?",
        "branch": "Which branch is closest to you?",
        "service": "What's the visit for?",
        "slot": "Which day would suit you?",
    },
    "Hindi": {
        "city": "आप किस शहर में हैं?",
        "branch": "आपके सबसे पास कौन सी ब्रांच है?",
        "service": "किस लिए आना है?",
        "slot": "कौन सा दिन ठीक रहेगा?",
    },
    "Bengali": {
        "city": "আপনি কোন শহরে আছেন?",
        "branch": "আপনার সবচেয়ে কাছের শাখা কোনটি?",
        "service": "কী কারণে আসতে চান?",
        "slot": "কোন দিনটা আপনার সুবিধা হবে?",
    },
    "Gujarati": {
        "city": "તમે કયા શહેરમાં છો?",
        "branch": "તમારી સૌથી નજીકની શાખા કઈ છે?",
        "service": "શા માટે આવવું છે?",
        "slot": "કયો દિવસ અનુકૂળ રહેશે?",
    },
    "Kannada": {
        "city": "ನೀವು ಯಾವ ನಗರದಲ್ಲಿದ್ದೀರಿ?",
        "branch": "ನಿಮಗೆ ಹತ್ತಿರದ ಶಾಖೆ ಯಾವುದು?",
        "service": "ಯಾವ ಕಾರಣಕ್ಕೆ ಬರುತ್ತಿದ್ದೀರಿ?",
        "slot": "ಯಾವ ದಿನ ನಿಮಗೆ ಅನುಕೂಲ?",
    },
    "Malayalam": {
        "city": "നിങ്ങൾ ഏത് നഗരത്തിലാണ്?",
        "branch": "നിങ്ങൾക്ക് അടുത്തുള്ള ബ്രാഞ്ച് ഏതാണ്?",
        "service": "എന്തിനാണ് വരുന്നത്?",
        "slot": "ഏത് ദിവസമാണ് സൗകര്യം?",
    },
    "Marathi": {
        "city": "तुम्ही कोणत्या शहरात आहात?",
        "branch": "तुमच्या जवळची शाखा कोणती?",
        "service": "कशासाठी यायचं आहे?",
        "slot": "कोणता दिवस सोयीचा आहे?",
    },
    "Punjabi": {
        "city": "ਤੁਸੀਂ ਕਿਹੜੇ ਸ਼ਹਿਰ ਵਿੱਚ ਹੋ?",
        "branch": "ਤੁਹਾਡੇ ਸਭ ਤੋਂ ਨੇੜੇ ਕਿਹੜੀ ਬ੍ਰਾਂਚ ਹੈ?",
        "service": "ਕਿਸ ਲਈ ਆਉਣਾ ਹੈ?",
        "slot": "ਕਿਹੜਾ ਦਿਨ ਠੀਕ ਰਹੇਗਾ?",
    },
    "Tamil": {
        "city": "நீங்கள் எந்த ஊரில் இருக்கிறீர்கள்?",
        "branch": "உங்களுக்கு அருகில் உள்ள கிளை எது?",
        "service": "எதற்காக வருகிறீர்கள்?",
        "slot": "எந்த நாள் உங்களுக்கு வசதியாக இருக்கும்?",
    },
    "Telugu": {
        "city": "మీరు ఏ నగరంలో ఉన్నారు?",
        "branch": "మీకు దగ్గరగా ఉన్న బ్రాంచ్ ఏది?",
        "service": "దేని కోసం రావాలనుకుంటున్నారు?",
        "slot": "ఏ రోజు మీకు వీలుగా ఉంటుంది?",
    },
}

assert set(NEXT_QUESTION) == set(LANGUAGE_CODE), "a language with no next questions"
