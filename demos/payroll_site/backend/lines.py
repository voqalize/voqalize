"""The lines the brain writes itself, in every language the persona speaks.

The greeting is fixed per job (no model call, so the agent speaks the moment the
call connects); the landed lines are the floor under a turn that moved the
screen and said nothing (:mod:`voqalize_demos.silent_turn`); the booking lines
are said by the brain when the visitor's yes books the demo. None of them names
the character except through ``{name}``, filled from ``persona.json``. A language
added to the persona needs a row in every table here; ``brain.py`` asserts it.
"""

from __future__ import annotations

from collections.abc import Mapping

Lines = Mapping[str, Mapping[str, tuple[str, ...]]]

GREETING: Mapping[str, Mapping[str, str]] = {
    "sdr": {
        "en": (
            "Hi, I'm {name} from Paynora. I can show you how Paynora would run payroll for "
            "your team. Roughly how many people do you have, and how do you run payroll today?"
        ),
        "hi": (
            "नमस्ते, मैं Paynora से {name} हूँ। मैं आपको दिखा सकता हूँ कि Paynora आपकी टीम का "
            "पेरोल कैसे चलाएगा। आपकी टीम में लगभग कितने लोग हैं, और अभी पेरोल कैसे चलता है?"
        ),
    },
    "pricing": {
        "en": (
            "Hi, I'm {name} from Paynora. Tell me how many employees you have and what you "
            "need, and I'll work out your price on the calculator, line by line."
        ),
        "hi": (
            "नमस्ते, मैं Paynora से {name} हूँ। बताइए आपके कितने कर्मचारी हैं और आपको क्या "
            "चाहिए, मैं कैलकुलेटर पर आपकी कीमत लाइन दर लाइन निकाल दूँगा।"
        ),
    },
    "booker": {
        "en": (
            "Hi, I'm {name} from Paynora. I can book you a 30-minute demo with our sales "
            "team. Which day suits you?"
        ),
        "hi": (
            "नमस्ते, मैं Paynora से {name} हूँ। मैं आपके लिए हमारी सेल्स टीम के साथ 30 मिनट "
            "का डेमो बुक कर सकता हूँ। आपके लिए कौन सा दिन ठीक रहेगा?"
        ),
    },
}

#: What the agent says when the call moves to a job's page mid-call and the
#: visitor has not spoken yet. Short: the page already shows the rest.
JOB_SWITCH: Mapping[str, Mapping[str, str]] = {
    "sdr": {"en": "Happy to walk you through it.", "hi": "मैं आपको समझा देता हूँ।"},
    "pricing": {
        "en": "This is the calculator. Tell me your headcount and I'll fill it in.",
        "hi": "यह कैलकुलेटर है। अपने कर्मचारियों की संख्या बताइए, मैं भर देता हूँ।",
    },
    "booker": {
        "en": "Here's the sales calendar. Which day suits you?",
        "hi": "यह सेल्स कैलेंडर है। आपके लिए कौन सा दिन ठीक रहेगा?",
    },
}

LANDED: Lines = {
    "lead": {
        "en": ("Noted on your card.", "That's on your card now."),
        "hi": ("आपके कार्ड पर लिख दिया।", "यह आपके कार्ड पर आ गया।"),
    },
    "modules": {
        "en": ("These are the modules that fit.",),
        "hi": ("ये मॉड्यूल आपके काम के हैं।",),
    },
    "pricing": {
        "en": ("The calculator has your numbers now.", "Here's the working, line by line."),
        "hi": ("कैलकुलेटर में आपके नंबर भर दिए।", "यह रहा हिसाब, लाइन दर लाइन।"),
    },
    "open": {
        "en": ("Here it is.", "It's on your screen."),
        "hi": ("यह रहा।", "यह आपकी स्क्रीन पर है।"),
    },
    "calendar": {
        "en": ("Here are the free slots.",),
        "hi": ("ये रहे खाली स्लॉट।",),
    },
    "pick": {
        "en": ("I've picked that slot.",),
        "hi": ("वह स्लॉट चुन लिया।",),
    },
}

BOOKING: Mapping[str, Mapping[str, str]] = {
    "ask": {
        "en": "Shall I confirm {when} with {rep}?",
        "hi": "क्या मैं {when} पर {rep} के साथ पक्का कर दूँ?",
    },
    "booking": {"en": "Confirming it now.", "hi": "अभी पक्का कर रहा हूँ।"},
    "booked": {
        "en": (
            "You're booked for {when} with {rep}, reference {reference}. An invite with the "
            "video link is on its way to your email."
        ),
        "hi": (
            "आपका डेमो {when} पर {rep} के साथ बुक हो गया है, रेफ़रेंस {reference}। वीडियो लिंक "
            "के साथ इनवाइट आपके ईमेल पर आ रहा है।"
        ),
    },
    "failed": {
        "en": "That didn't go through: {why}. Shall I pick another slot?",
        "hi": "यह बुक नहीं हुआ: {why}। क्या मैं कोई और स्लॉट चुनूँ?",
    },
}

TOGGLE_CONFIRM: Mapping[str, str] = {
    "en": "Sure, let's continue in English.",
    "hi": "ज़रूर, अब हिंदी में बात करते हैं।",
}

#: Words that answer "shall I confirm it?" with yes, in either language.
YES_WORDS = (
    "yes",
    "yeah",
    "yep",
    "sure",
    "ok",
    "okay",
    "go ahead",
    "confirm",
    "confirm it",
    "book it",
    "please do",
    "do it",
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
    "पक्का",
)
NO_WORDS = ("no", "not now", "wait", "don't", "nahi", "nahin", "नहीं", "रुको", "रुकिए")
