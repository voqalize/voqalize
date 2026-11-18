"""Who answers the call, read from ``demos/insurance/persona.json``.

The character (avatar id, name, voice per language, the languages offered and
the default) lives in that one file, which the page reads too. To change the
character, edit ``persona.json``; to add a language, add a row there and a
greeting row to :data:`GREETINGS` below. Nothing else in the brain names her.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from voqalize.sdk.wire import Config, IdleConfig, SttConfig, TtsConfig

PERSONA_FILE = Path(__file__).resolve().parent.parent / "persona.json"
_RAW: dict[str, Any] = json.loads(PERSONA_FILE.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class Speaking:
    """One language the call can be in: both speech legs and the voice."""

    code: str
    label: str
    voice: str
    stt: str
    tts: str


CHARACTER: str = _RAW["character"]
NAME: str = _RAW["name"]
NAMES: dict[str, str] = dict(_RAW.get("names") or {})
GENDER: str = _RAW.get("gender", "female")
ROLE: str = _RAW.get("role", "")
LANGUAGES: dict[str, Speaking] = {
    row["code"]: Speaking(row["code"], row["label"], row["voice"], row["stt"], row["tts"])
    for row in _RAW["languages"]
}
DEFAULT_LANGUAGE: str = _RAW["default_language"]
assert DEFAULT_LANGUAGE in LANGUAGES, "persona.json: default_language is not one of its languages"


def name_in(lang: str) -> str:
    return NAMES.get(lang, NAME)


def language_of(tag: object) -> str:
    """The language a page's ``lang`` names, or the default for anything else."""
    code = str(tag or "").strip().lower()[:2]
    return code if code in LANGUAGES else DEFAULT_LANGUAGE


def speech_config(lang: str, *, patience: int, idle_ms: int | None = None) -> Config:
    """Both legs of ``lang``, always together (the pairing rule)."""
    s = LANGUAGES[lang]
    return Config(
        stt=SttConfig(language=s.stt, patience=patience),
        tts=TtsConfig(voice=s.voice, language=s.tts),
        idle=IdleConfig(timeout_ms=idle_ms) if idle_ms is not None else None,
    )


#: How she refers to herself in Hindi depends on the character's gender.
HINDI_SELF = (
    "Speak of yourself in the feminine (मैं दिखाती हूँ, मैं भरती हूँ)."
    if GENDER == "female"
    else "Speak of yourself in the masculine (मैं दिखाता हूँ, मैं भरता हूँ)."
)

#: The opening line per job and language, written, never generated. ``{name}``
#: is the character's name in that language, ``{first}`` the customer's first name.
GREETINGS: dict[str, dict[str, str]] = {
    "home": {
        "en": "Hi, I'm {name} from Chhatri Insurance. I can get you a quote, check what your policies cover, or help you file a claim. What would you like to do?",
        "hi": "नमस्ते, मैं {name}, छतरी इंश्योरेंस से। मैं आपके लिए क्वोट बना सकती हूँ, पॉलिसी में क्या कवर है बता सकती हूँ, या क्लेम भरने में मदद कर सकती हूँ। बताइए, क्या करें?",
    },
    "quote": {
        "en": "Hi, I'm {name} from Chhatri. Tell me in a sentence or two what you'd like to insure, and I'll build your quote right here.",
        "hi": "नमस्ते, मैं {name}, छतरी से। एक-दो वाक्य में बताइए कि आप क्या इंश्योर करना चाहते हैं, मैं यहीं आपका क्वोट बना देती हूँ।",
    },
    "policies": {
        "en": "Hi {first}, I'm {name}. Ask me whether something is covered, and I'll show you the exact clause in your policy.",
        "hi": "नमस्ते {first}, मैं {name}। पूछिए कि कोई चीज़ कवर है या नहीं, मैं आपकी पॉलिसी में वही क्लॉज़ दिखा दूँगी।",
    },
    "claim": {
        "en": "Hi {first}, I'm {name}. I'm sorry you need to make a claim. Tell me what happened, in your own words, and I'll fill in the form as you talk.",
        "hi": "नमस्ते {first}, मैं {name}। क्लेम की ज़रूरत पड़ी, यह सुनकर दुख हुआ। अपने शब्दों में बताइए क्या हुआ, मैं साथ-साथ फ़ॉर्म भरती जाऊँगी।",
    },
}
assert all(set(rows) >= set(LANGUAGES) for rows in GREETINGS.values()), (
    "a language in persona.json has no greeting in GREETINGS"
)

#: What she says when the visitor switches language on the toggle mid-call.
SWITCHED: dict[str, str] = {
    "en": "Sure, let's continue in English.",
    "hi": "ज़रूर, अब हिंदी में बात करते हैं।",
}


def greeting(mode: str, lang: str, first_name: str) -> str:
    rows = GREETINGS.get(mode, GREETINGS["home"])
    return rows.get(lang, rows["en"]).format(name=name_in(lang), first=first_name)
