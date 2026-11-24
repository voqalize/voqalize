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
            "Hi, I'm {name}, your property guide at Kosha Homes. Are you looking to buy or rent, "
            "and in which city? Tell me your budget and where you work too, and I'll find the "
            "homes that fit."
        ),
        "hi": (
            "नमस्ते, मैं {name} हूँ, Kosha Homes में आपका प्रॉपर्टी गाइड। आप घर खरीदना चाहते हैं या "
            "किराए पर लेना, और किस शहर में? अपना बजट और ऑफ़िस कहाँ है, ये भी बता दीजिए, मैं आपके "
            "लिए सही घर ढूँढ दूँगा।"
        ),
    },
    "booker": {
        "en": (
            "Hi, I'm {name} from Kosha Homes. You're looking at {title}, and the best way to "
            "judge it is to see it. Which day would suit you for a site visit?"
        ),
        "hi": (
            "नमस्ते, मैं Kosha Homes से {name} हूँ। आप {title} देख रहे हैं, और इसे परखने का सबसे "
            "अच्छा तरीका है इसे खुद देखना। साइट विज़िट के लिए आपको कौन सा दिन ठीक रहेगा?"
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
            "Done, {first}! You're booked for {when}. {contact} will meet {who} there; just bring "
            "{bring}, and the address and contact are on your visit card."
        ),
        "hi": (
            "हो गया, {first} जी! आपकी साइट विज़िट {when} के लिए बुक हो गई है। {contact} वहाँ {who} "
            "मिलेंगे; बस {bring} साथ लाइए, पता और संपर्क आपके visit card पर है।"
        ),
    },
    "failed": {
        "en": "That slot didn't go through: {why}. Shall I pick another?",
        "hi": "वह स्लॉट बुक नहीं हुआ: {why}। क्या मैं कोई और स्लॉट चुनूँ?",
    },
    "switched": {"en": "Sure, let's continue in English.", "hi": "ज़रूर, अब हिंदी में बात करते हैं।"},
    # The visitor typed their mobile number while a visit was held: the one confirmation.
    "confirm": {
        "en": "Thanks, {first}, your number is in. Shall I book {when} for {who}?",
        "hi": "धन्यवाद {first} जी, नंबर आ गया। क्या मैं {when} की विज़िट {who} लिए बुक कर दूँ?",
    },
    # A yes before the number was typed: nothing is booked yet.
    "need_phone": {
        "en": (
            "Happy to. Just type your mobile number in the box I've highlighted on the visit "
            "form, and I'll book it straight away."
        ),
        "hi": (
            "ज़रूर। बस visit form पर हाइलाइट किए गए बॉक्स में अपना मोबाइल नंबर टाइप कर दीजिए, मैं "
            "तुरंत बुक कर दूँगा।"
        ),
    },
}

#: Who is coming, as the confirmation and the booked line say it: (one, two, more).
WHO: Mapping[str, Mapping[str, tuple[str, str, str]]] = {
    "confirm": {
        "en": ("you", "the two of you", "the {n} of you"),
        "hi": ("आपके", "आप दोनों के", "आप {n} लोगों के"),
    },
    "booked": {
        "en": ("you", "you both", "all {n} of you"),
        "hi": ("आपसे", "आप दोनों से", "आप सबसे"),
    },
}

#: The written answer under a read the model left unspoken (``owe`` in brain.py).
OWED: Mapping[str, Mapping[str, str]] = {
    "search": {
        "en": "{count} fit what you told me. The best match is {title} in {locality}, at {price}. {next}",
        "hi": "{count} आपकी बताई ज़रूरत से मेल खाते हैं। सबसे अच्छा {title} है, {locality} में, {price}। {next}",
    },
    "none": {
        "en": "Nothing fits all of that yet. Shall I widen the budget or the distance a little?",
        "hi": "अभी इन सब शर्तों पर कोई घर नहीं मिला। क्या मैं बजट या दूरी थोड़ी बढ़ा दूँ?",
    },
    "next_visit": {
        "en": "Shall I book you a site visit to see it?",
        "hi": "क्या मैं इसे देखने के लिए साइट विज़िट बुक कर दूँ?",
    },
    "next_ask": {
        "en": "Tell me a little more and I'll narrow it further.",
        "hi": "थोड़ा और बताइए, मैं और छाँट दूँगा।",
    },
    "compare": {
        "en": "They're side by side on your screen, and {title} suits you better. Shall I book you a site visit there?",
        "hi": "दोनों आपकी स्क्रीन पर आमने-सामने हैं, और {title} आपके लिए बेहतर है। क्या वहाँ साइट विज़िट बुक कर दूँ?",
    },
    "emi": {
        "en": "On {title}, the EMI comes to {emi} a month with {down}% down over {years} years. Shall I book you a site visit to see it?",
        "hi": "{title} पर {down}% डाउन पेमेंट और {years} साल में EMI {emi} महीना बनती है। क्या इसे देखने के लिए साइट विज़िट बुक कर दूँ?",
    },
    "open": {
        "en": "Here's {title}. Which day would suit you to come and see it?",
        "hi": "ये रहा {title}। इसे देखने आने के लिए कौन सा दिन ठीक रहेगा?",
    },
    "facts": {
        "en": "{title} is a {bhk} BHK of {carpet} sq ft at {price}. Shall I book you a site visit to see it?",
        "hi": "{title} {bhk} BHK है, {carpet} sq ft, {price} में। क्या इसे देखने के लिए साइट विज़िट बुक कर दूँ?",
    },
    "slots": {
        "en": "On {day}, {times} are free. Which one suits you?",
        "hi": "{day} को {times} खाली हैं। आपको कौन सा समय ठीक रहेगा?",
    },
}

#: Hindi day and month names, for the lines the brain writes in Hindi.
HI_DAYS = ("सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार")
HI_MONTHS = (
    "जनवरी",
    "फ़रवरी",
    "मार्च",
    "अप्रैल",
    "मई",
    "जून",
    "जुलाई",
    "अगस्त",
    "सितंबर",
    "अक्टूबर",
    "नवंबर",
    "दिसंबर",
)

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
