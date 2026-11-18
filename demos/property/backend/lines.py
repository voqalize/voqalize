"""The lines the brain writes itself, in every language the persona speaks.

The greeting is fixed (no model call, so the agent speaks the moment the call
connects); the landed lines are the floor under a turn that moved the screen and
said nothing (:mod:`voqalize_demos.silent_turn`); the booking lines are said by
the brain when the buyer's yes books a visit. None of them names the character:
the name comes from ``persona.json``. A language added to the persona needs a
row in every table here, which ``brain.py`` asserts at import.
"""

from __future__ import annotations

from collections.abc import Mapping

Lines = Mapping[str, Mapping[str, tuple[str, ...]]]

GREETING: Mapping[str, Mapping[str, str]] = {
    "guide": {
        "en": (
            "Hi, I'm {name}, your property guide at Kosha Homes. Tell me what you're looking "
            "for: the city, how many bedrooms, your budget, or where you work, and I'll narrow "
            "the homes for you."
        ),
        "hi": (
            "नमस्ते, मैं {name} हूँ, Kosha Homes में आपका प्रॉपर्टी गाइड। बताइए आप क्या ढूँढ रहे "
            "हैं: शहर, कितने BHK, बजट, या आपका ऑफ़िस कहाँ है, और मैं आपके लिए घर छाँट दूँगा।"
        ),
    },
    "booker": {
        "en": (
            "Hi, I'm {name} from Kosha Homes. You're looking at {title}. I can book you a site "
            "visit at a time that suits you and the sales team. Which day works for you?"
        ),
        "hi": (
            "नमस्ते, मैं Kosha Homes से {name} हूँ। आप {title} देख रहे हैं। मैं आपके और सेल्स "
            "टीम के लिए सही समय पर साइट विज़िट बुक कर सकता हूँ। आपके लिए कौन सा दिन ठीक रहेगा?"
        ),
    },
}

LANDED: Lines = {
    "filter": {
        "en": ("Here are the homes that fit.", "The list and the map now show what fits."),
        "hi": ("ये रहे आपके हिसाब से घर।", "लिस्ट और मैप अब आपके हिसाब से हैं।"),
    },
    "open": {
        "en": ("Here it is.", "It's on your screen."),
        "hi": ("यह रहा।", "ये आपकी स्क्रीन पर है।"),
    },
    "compare": {
        "en": ("Here they are, side by side.",),
        "hi": ("ये रहे दोनों, आमने-सामने।",),
    },
    "emi": {
        "en": ("The EMI is worked out on screen.",),
        "hi": ("ईएमआई स्क्रीन पर निकाल दी है।",),
    },
    "shortlist": {
        "en": ("Done, it's on your shortlist.",),
        "hi": ("हो गया, शॉर्टलिस्ट में जोड़ दिया।",),
    },
    "slots": {
        "en": ("Here are the free slots.",),
        "hi": ("ये रहे खाली स्लॉट।",),
    },
}

BOOKING: Mapping[str, Mapping[str, str]] = {
    "booking": {"en": "Booking it now.", "hi": "अभी बुक कर रहा हूँ।"},
    "booked": {
        "en": (
            "Your visit is booked for {when}, reference {reference}. {contact} will meet you; "
            "please bring {bring}."
        ),
        "hi": (
            "आपकी विज़िट {when} के लिए बुक हो गई है, रेफ़रेंस {reference}। {contact} आपसे मिलेंगे; "
            "कृपया {bring} साथ लाइए।"
        ),
    },
    "failed": {
        "en": "That slot didn't go through: {why}. Shall I pick another?",
        "hi": "वह स्लॉट बुक नहीं हुआ: {why}। क्या मैं कोई और स्लॉट चुनूँ?",
    },
    "switched": {"en": "Sure, let's continue in English.", "hi": "ज़रूर, अब हिंदी में बात करते हैं।"},
}

#: A short spoken form of the first thing to bring, per language.
BRING_SHORT: Mapping[str, str] = {"en": "a photo ID", "hi": "एक फ़ोटो आईडी"}

#: Words that answer "shall I book it?" with yes, in either language.
YES_WORDS = (
    "yes",
    "yeah",
    "yep",
    "sure",
    "ok",
    "okay",
    "go ahead",
    "book it",
    "please do",
    "confirm",
    "haan",
    "han",
    "ji",
    "theek hai",
    "हाँ",
    "हां",
    "जी",
    "ठीक है",
    "कर दो",
    "कर दीजिए",
    "बुक कर",
)
NO_WORDS = ("no", "not now", "wait", "nahi", "नहीं", "रुको", "रुकिए")
