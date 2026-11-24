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
    "open": {
        "en": ("Here it is.", "It's on your screen."),
        "hi": ("यह रहा।", "ये आपकी स्क्रीन पर है।"),
    },
    "shortlist": {
        "en": ("Done, it's on your shortlist.",),
        "hi": ("हो गया, शॉर्टलिस्ट में जोड़ दिया।",),
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
    # The same, when the model's words this turn already said their name.
    "confirm_bare": {
        "en": "Your number is in. Shall I book {when} for {who}?",
        "hi": "नंबर आ गया। क्या मैं {when} की विज़िट {who} लिए बुक कर दूँ?",
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
    "none": {
        "en": "Nothing fits all of that yet. Shall I widen the budget or the distance a little?",
        "hi": "अभी इन सब शर्तों पर कोई घर नहीं मिला। क्या मैं बजट या दूरी थोड़ी बढ़ा दूँ?",
    },
    "facts": {
        "en": "{title} is a {bhk} BHK of {carpet} sq ft at {price}. Shall I book you a site visit to see it?",
        "hi": "{title} {bhk} BHK है, {carpet} sq ft का, {price} में। क्या इसे देखने के लिए साइट विज़िट बुक कर दूँ?",
    },
}

#: The brain's own answer to a step it took (K0 R4): said straight after the
#: model's few words of lead-in, in the same turn, with no second model request.
#: Each names a home once and its price once.
SAID: Mapping[str, Mapping[str, str]] = {
    # The homes that fit, and the best of them.
    "fit_many": {
        "en": "{n} homes fit what you told me. {show}The best match is {name} in {locality}, a {bhk} BHK{km} at {price}.",
        "hi": "आपके हिसाब से {n} घर हैं। {show}सबसे अच्छा {name} है, {locality} में, {bhk} BHK{km}, {price} का।",
    },
    "fit_one": {
        "en": "{show}One home fits what you told me: {name} in {locality}, a {bhk} BHK{km} at {price}.",
        "hi": "{show}आपके हिसाब से एक घर है: {name}, {locality} में, {bhk} BHK{km}, {price} का।",
    },
    "km": {"en": ", {km} km from {office},", "hi": ", {office} से {km} km"},
    # They said "around" a budget: nothing at it, one a little over (at most 10%).
    "around": {
        "en": "Nothing is quite at {budget}, but {name} in {locality} comes close: a {bhk} BHK{km} at {price}, just {pct}% over.",
        "hi": "ठीक {budget} में तो कुछ नहीं है, पर {name}, {locality} में, करीब है: {bhk} BHK{km}, {price} का, बस {pct}% ज़्यादा।",
    },
    # Nothing within the budget: the nearest home over it, and how far over.
    "over": {
        "en": "Nothing fits up to {budget} yet. The nearest is {name} in {locality}, a {bhk} BHK at {price}, about {pct}% over your budget. Shall I raise the budget, or change something else?",
        "hi": "{budget} तक अभी कोई घर नहीं है। सबसे करीब {name} है, {locality} में, {bhk} BHK, {price} का, यानी बजट से करीब {pct}% ज़्यादा। बजट थोड़ा बढ़ाऊँ, या कुछ और बदलें?",
    },
    # Nothing fits every limit: the home that misses only one.
    "except": {
        "en": "Nothing fits all of that yet. {name} in {locality}, a {bhk} BHK at {price}, fits everything but {what}. Shall I include homes like it?",
        "hi": "इन सब शर्तों पर अभी कोई घर नहीं है। {name}, {locality} में, {bhk} BHK, {price} का, बाकी सब में ठीक है, बस {what} अलग है। क्या ऐसे घर भी दिखाऊँ?",
    },
    "open": {
        "en": "Here's {name} in {locality}: a {bhk} BHK of {carpet} sq ft, {possession}, at {price}. {fit} Which day would suit you to come and see it?",
        "hi": "ये रहा {name}, {locality} में: {bhk} BHK, {carpet} sq ft, {possession}, {price} का। {fit} इसे देखने कब आना चाहेंगे?",
    },
    "ready": {"en": "ready to move in", "hi": "रेडी-टू-मूव"},
    "building": {"en": "with possession in {date}", "hi": "पज़ेशन {date}"},
    "fit_office": {"en": "It's {km} km from {office}.", "hi": "{office} से सिर्फ़ {km} km है।"},
    "fit_school": {"en": "{school} is {km} km away.", "hi": "{school} सिर्फ़ {km} km पर है।"},
    "fit_metro": {"en": "{metro} is {km} km away.", "hi": "{metro} {km} km पर है।"},
    "compare": {
        "en": "They're side by side now. {name} suits you better, {why}{though}. Shall I book you a site visit there?",
        "hi": "दोनों अब आमने-सामने हैं। {name} आपके लिए बेहतर है, {why}{though}। क्या वहाँ साइट विज़िट बुक कर दूँ?",
    },
    "though": {"en": ", though {what}", "hi": ", हालाँकि {what}"},
    "emi": {
        "en": "On {name}, with {down}% down over {years} years, the EMI comes to {emi} a month.{rival} {nudge}",
        "hi": "{name} पर {down}% डाउन पेमेंट और {years} साल के लोन पर EMI {emi} महीना आती है।{rival} {nudge}",
    },
    "emi_rival": {
        "en": " On the same terms, {other} would be {emi} a month, so {lower} is lower.",
        "hi": " इन्हीं शर्तों पर {other} की EMI {emi} महीना होगी, यानी {lower} की कम है।",
    },
    "slots": {
        "en": "On {day}, {times} {are} free. Which suits you?",
        "hi": "{day} को {times} खाली {are}। कौन सा समय ठीक रहेगा?",
    },
    "weekend": {
        "en": "{day} has {times} free, and {day2} has {times2}. Which suits you?",
        "hi": "{day} को {times} खाली {are}, और {day2} को {times2}। कौन सा ठीक रहेगा?",
    },
    "part_full": {
        "en": "{day} {part} is full, but {times} {is_} free that day. Would that work?",
        "hi": "{day} {part} कोई समय खाली नहीं है, पर उस दिन {times} खाली {is_}। चलेगा?",
    },
    "day_full": {
        "en": "{day} is fully booked. {days} still have free slots; which day suits you?",
        "hi": "{day} पूरा भरा है। {days} को समय खाली है, कौन सा दिन ठीक रहेगा?",
    },
    "closed": {
        "en": "The sales team doesn't take visits on {day}. {days} have free slots; which day suits you?",
        "hi": "{day} को सेल्स टीम विज़िट नहीं लेती। {days} को समय खाली है, कौन सा दिन ठीक रहेगा?",
    },
    "which_day": {
        "en": "Which day suits you? There are free slots on {days}.",
        "hi": "कौन सा दिन ठीक रहेगा? {days} को समय खाली है।",
    },
    "filled": {
        "en": "I've filled in the visit for {when}, for {who}. Please type your mobile number in the highlighted Mobile box.",
        "hi": "{when} की विज़िट {who} लिए भर दी है। बस हाइलाइट किए गए Mobile बॉक्स में अपना मोबाइल नंबर टाइप कर दीजिए।",
    },
    "taken": {
        "en": "That time isn't free. On {day}, {times} {are} free; which suits you?",
        "hi": "वह समय खाली नहीं है। {day} को {times} खाली {are}, कौन सा ठीक रहेगा?",
    },
    "no_name": {
        "en": "Whose name should I put the visit under?",
        "hi": "विज़िट किसके नाम से रखूँ?",
    },
    "office_unknown": {
        "en": "Which of these is closest to where you work: {offices}?",
        "hi": "इनमें से आपका ऑफ़िस किसके सबसे पास है: {offices}?",
    },
    "budget_check": {"en": "Just to check, {amount}, right?", "hi": "बस पक्का कर लूँ, {amount}, सही?"},
    "budget_again": {
        "en": "Sorry, what budget was that?",
        "hi": "माफ़ कीजिए, बजट कितना बताया आपने?",
    },
    "which_home": {"en": "Which home do you mean?", "hi": "आप कौन से घर की बात कर रहे हैं?"},
    "emi_rent": {
        "en": "An EMI is only for a home to buy, and that one is for rent. Shall I find homes to buy?",
        "hi": "EMI सिर्फ़ खरीदने वाले घर पर बनती है, और वो किराए का है। क्या खरीदने के लिए घर देखूँ?",
    },
    "which_two": {
        "en": "Which two homes shall I put side by side?",
        "hi": "कौन से दो घर आमने-सामने रखूँ?",
    },
}

#: Why one home suits them better (compare), in the call's language.
WHY: Mapping[str, Mapping[str, str]] = {
    "office": {"en": "at {km} km from {office}", "hi": "{office} से सिर्फ़ {km} km"},
    "school": {"en": "with {school} just {km} km away", "hi": "{school} सिर्फ़ {km} km पर"},
    "value": {
        "en": "at {per} per sq ft, the most home for the money",
        "hi": "{per} प्रति sq ft, पैसे के हिसाब से सबसे ज़्यादा घर",
    },
    "price": {"en": "at {price}", "hi": "{price} में"},
}

#: The other home's one real advantage (compare), by the comparison's row.
EDGE: Mapping[str, Mapping[str, str]] = {
    "Price": {"en": "{name} costs less, at {value}", "hi": "{name} सस्ता है, {value} का"},
    "Carpet area": {"en": "{name} is bigger, at {value}", "hi": "{name} बड़ा है, {value}"},
    "Nearest metro": {
        "en": "{name} is closer to the metro",
        "hi": "{name} मेट्रो के ज़्यादा पास है",
    },
    "Nearest school": {
        "en": "{name} has a school closer by",
        "hi": "{name} के पास स्कूल ज़्यादा नज़दीक है",
    },
    "Amenities": {"en": "{name} has more amenities", "hi": "{name} में सुविधाएँ ज़्यादा हैं"},
}

#: What a home that misses one limit misses ("except" above).
MISSES: Mapping[str, Mapping[str, str]] = {
    "school": {"en": "the school distance", "hi": "स्कूल की दूरी"},
    "metro": {"en": "the metro distance", "hi": "मेट्रो की दूरी"},
    "commute": {"en": "the distance from your office", "hi": "ऑफ़िस से दूरी"},
    "possession": {"en": "possession", "hi": "पज़ेशन"},
    "localities": {"en": "the locality", "hi": "इलाका"},
    "budget_min": {"en": "the lower end of your budget", "hi": "बजट की निचली सीमा"},
}

#: The next question worth asking, by topic (brain.py's _TOPICS).
ASK: Mapping[str, Mapping[str, str]] = {
    "deal": {"en": "Are you looking to buy or rent?", "hi": "आप खरीदना चाहते हैं या किराए पर?"},
    "city": {"en": "Which city are you looking in?", "hi": "किस शहर में देख रहे हैं?"},
    "budget": {"en": "What budget do you have in mind?", "hi": "आपका बजट कितना है?"},
    "bhk": {"en": "How many bedrooms do you need?", "hi": "कितने BHK चाहिए?"},
    "office": {
        "en": "Where do you work, so I can keep the commute short?",
        "hi": "आपका ऑफ़िस कहाँ है? उसके पास वाले घर दिखा दूँगा।",
    },
    "possession": {
        "en": "Do you need it ready to move, or is under construction fine?",
        "hi": "रेडी-टू-मूव चाहिए, या अंडर-कंस्ट्रक्शन भी चलेगा?",
    },
    "school": {
        "en": "Does a good school nearby matter to you?",
        "hi": "क्या पास में अच्छा स्कूल होना ज़रूरी है?",
    },
}

#: The nudge toward a visit once a home fits, varied so it never repeats two turns
#: running: for a home to buy, and one to rent.
NUDGE: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "buy": {
        "en": (
            "Shall I book you a site visit to see it?",
            "Would you like its EMI, or a site visit this weekend?",
            "Want to go and see it? I can book the visit.",
        ),
        "hi": (
            "क्या इसे देखने के लिए साइट विज़िट बुक कर दूँ?",
            "इसकी EMI निकालूँ, या इस वीकेंड साइट विज़िट रख दूँ?",
            "देखने चलेंगे? मैं विज़िट बुक कर देता हूँ।",
        ),
    },
    "rent": {
        "en": ("Shall I book you a visit to see it?", "Would you like to go and see it this week?"),
        "hi": ("क्या इसे देखने के लिए विज़िट बुक कर दूँ?", "इस हफ़्ते देखने चलेंगे?"),
    },
}

#: Parts of the day, as the Hindi lines say them.
HI_PARTS: Mapping[str, str] = {"morning": "सुबह", "afternoon": "दोपहर", "evening": "शाम", "any": ""}

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
