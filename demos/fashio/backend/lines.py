"""The lines the brain writes itself, in every language the persona speaks.

The greetings are fixed (no model call, so the agent speaks the moment the call
connects); the landed lines are the floor under a turn that moved the screen and
said nothing (:mod:`voqalize_demos.silent_turn`); the ``SAID`` lines are the
brain's own answer to a step it took, said straight after the model's few words
of lead-in, so most turns take one model request. None of them names the
character: the name comes from ``persona.json``. A language added to the persona
needs a row in every table here, which ``brain.py`` asserts at import.

Hindi is the Hindi people in Mumbai or Delhi speak on a call: short, warm,
conversational, in Devanagari, with the English words shoppers use (size, bag,
order, return, kurta, wishlist, checkout) left in English.
"""

from __future__ import annotations

from collections.abc import Mapping

Table = Mapping[str, Mapping[str, str]]

#: The opener per job (the landing page), in the call's language.
GREETING: Mapping[str, Mapping[str, str]] = {
    "shopping": {
        "en": (
            "Hi, I'm {name}, your shopping assistant at Fashio. What are you shopping for today, "
            "and who is it for? Tell me the occasion and a budget too, and I'll pull out the "
            "best pieces."
        ),
        "hi": (
            "नमस्ते, मैं {name} हूँ, Fashio में आपका शॉपिंग असिस्टेंट। आज क्या ढूँढ रहे हैं, और "
            "किसके लिए? मौका और बजट भी बता दीजिए, मैं सबसे अच्छे पीस निकाल देती हूँ।"
        ),
    },
    "fit": {
        "en": (
            "Hi, I'm {name} from Fashio. Let's get your size right in this one. What size do "
            "you usually wear, and do you like a snug, regular or relaxed fit?"
        ),
        "hi": (
            "नमस्ते, मैं Fashio से {name} हूँ। चलिए, इसमें आपका सही size निकालते हैं। आप आमतौर पर "
            "कौन सा size पहनते हैं, और फ़िटिंग कैसी पसंद है, फ़िटेड, रेगुलर या ढीली?"
        ),
    },
    # A product page of a one-size product (a watch, a bag): nothing to size.
    "fit_one": {
        "en": (
            "Hi, I'm {name} from Fashio. This one comes in one size, so there's nothing to "
            "pick. Any questions about it, or shall I find something to go with it?"
        ),
        "hi": (
            "नमस्ते, मैं Fashio से {name} हूँ। ये one size में आता है, तो size की कोई टेंशन नहीं। "
            "इसके बारे में कुछ पूछना है, या इसके साथ कुछ मैचिंग ढूँढूँ?"
        ),
    },
    "gifts": {
        "en": "Hi, I'm {name}, your gift finder at Fashio. Who is the gift for, and what's the occasion?",
        "hi": "नमस्ते, मैं {name} हूँ, Fashio का गिफ़्ट फ़ाइंडर। गिफ़्ट किसके लिए है, और मौका क्या है?",
    },
    "orders": {
        "en": "Hi {first}, I'm {name} from Fashio. Which order would you like to check? Your recent ones are on the screen.",
        "hi": "नमस्ते {first} जी, मैं Fashio से {name} हूँ। कौन सा order देखना है? आपके हाल के orders स्क्रीन पर हैं।",
    },
    "returns": {
        "en": "Hi {first}, I'm {name} from Fashio. Which order would you like to return something from?",
        "hi": "नमस्ते {first} जी, मैं Fashio से {name} हूँ। किस order से कुछ return करना है?",
    },
    # /returns?order=<id>: the order is already chosen on the page.
    "returns_order": {
        "en": "Hi {first}, I'm {name} from Fashio. Which item from this order would you like to return, and what went wrong?",
        "hi": "नमस्ते {first} जी, मैं Fashio से {name} हूँ। इस order से कौन सा item return करना है, और क्या दिक्कत हुई?",
    },
    "kiosk": {
        "en": "Hi, I'm {name}, welcome to Fashio. Tell me what you're looking for, and I'll find it across our whole catalogue.",
        "hi": "नमस्ते, मैं {name} हूँ, Fashio में आपका स्वागत है। बताइए क्या ढूँढ रहे हैं, मैं पूरे कैटलॉग में से निकाल देती हूँ।",
    },
}

#: The floor under a turn that moved the screen and said nothing.
LANDED: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "open": {"en": ("Here it is.", "It's on your screen."), "hi": ("ये रहा।", "स्क्रीन पर है।")},
    "wishlist": {
        "en": ("Done, it's in your wishlist.",),
        "hi": ("हो गया, wishlist में डाल दिया।",),
    },
    "unwish": {"en": ("Done, it's off your wishlist.",), "hi": ("हो गया, wishlist से हटा दिया।",)},
    "shortlist": {
        "en": ("Added to your shortlist.",),
        "hi": ("शॉर्टलिस्ट में डाल दिया।",),
    },
    "unshortlist": {"en": ("Taken off your shortlist.",), "hi": ("शॉर्टलिस्ट से हटा दिया।",)},
}

#: The brain's own answer to a step it took (K0 R4): said straight after the
#: model's few words, in the same turn, with no second model request.
SAID: Table = {
    # ── Shopping ──
    "fit_many": {
        "en": "{n} pieces fit. {show}The top pick is the {name} at {price}{off}.",
        "hi": "आपके हिसाब से {n} पीस हैं। {show}सबसे अच्छा है {name}, {price} का{off}।",
    },
    "fit_two": {
        "en": "{n} pieces fit. {show}The top pick is the {name} at {price}{off}. {show2}The {name2} at {price2} is close behind.",
        "hi": "आपके हिसाब से {n} पीस हैं। {show}सबसे अच्छा है {name}, {price} का{off}। {show2}{name2} भी अच्छा है, {price2} का।",
    },
    "fit_one": {
        "en": "{show}One piece fits: the {name} at {price}{off}.",
        "hi": "{show}आपके हिसाब से एक पीस है: {name}, {price} का{off}।",
    },
    "off": {"en": ", {pct}% off", "hi": ", {pct}% छूट के साथ"},
    "over": {
        "en": "Nothing fits under {budget} yet. The nearest is the {name} at {price}, a little over. Shall I raise the budget, or change something else?",
        "hi": "{budget} के अंदर अभी कुछ नहीं है। सबसे करीब {name} है, {price} का, थोड़ा ऊपर। बजट थोड़ा बढ़ाऊँ, या कुछ और बदलें?",
    },
    "except": {
        "en": "Nothing fits all of that yet. The {name} at {price} fits everything but {what}. Shall I include pieces like it?",
        "hi": "इन सब शर्तों पर अभी कुछ नहीं है। {name}, {price} का, बाकी सब में ठीक है, बस {what} अलग है। क्या ऐसे पीस भी दिखाऊँ?",
    },
    "none": {
        "en": "Nothing fits all of that yet. Shall I loosen one thing, like the colour or the budget?",
        "hi": "इन सब शर्तों पर अभी कुछ नहीं मिला। क्या एक चीज़ ढीली करूँ, जैसे रंग या बजट?",
    },
    "open": {
        "en": "Here's the {name}, {price}{off}. {stock} What size do you usually wear?",
        "hi": "ये रहा {name}, {price} का{off}। {stock} आप आमतौर पर कौन सा size पहनते हैं?",
    },
    # Opening a product when their size is already known: the offer follows.
    "open_known_add": {
        "en": "Here's the {name}, {price}{off}. It's in stock in {size}; shall I add it to your bag?",
        "hi": "ये रहा {name}, {price} का{off}। {size} स्टॉक में है, bag में डाल दूँ?",
    },
    "open_known": {
        "en": "Here's the {name}, {price}{off}.",
        "hi": "ये रहा {name}, {price} का{off}।",
    },
    "open_one": {
        "en": "Here's the {name}, {price}{off}. It's one size, and it's in stock. Shall I add it to your bag?",
        "hi": "ये रहा {name}, {price} का{off}। ये one size है, और स्टॉक में है। bag में डाल दूँ?",
    },
    "stock_sizes": {"en": "Sizes {sizes} are in stock.", "hi": "{sizes} size स्टॉक में हैं।"},
    "stock_few": {
        "en": "Sizes {sizes} are in stock, only {n} left in {size}.",
        "hi": "{sizes} size स्टॉक में हैं, {size} में बस {n} बचे हैं।",
    },
    "sold_out": {
        "en": "Sorry, this one is sold out in every size. Shall I find something similar?",
        "hi": "माफ़ कीजिए, ये हर size में ख़त्म है। कुछ मिलता-जुलता ढूँढूँ?",
    },
    "compare": {
        "en": "They're side by side now. The {name} is the better buy, {why}. Which one do you like?",
        "hi": "दोनों अब आमने-सामने हैं। {name} बेहतर सौदा है, {why}। आपको कौन सा पसंद है?",
    },
    "why_discount": {"en": "with {pct}% off at {price}", "hi": "{pct}% छूट के साथ {price} का"},
    "why_cheaper": {"en": "at {price}, {diff} less", "hi": "{price} का, {diff} सस्ता"},
    "why_price": {"en": "at {price}", "hi": "{price} का"},
    "propose": {
        "en": "Shall I add the {name} in size {size} to your bag?",
        "hi": "{name}, size {size} में, bag में डाल दूँ?",
    },
    "propose_one": {
        "en": "Shall I add the {name} to your bag?",
        "hi": "{name} bag में डाल दूँ?",
    },
    "oos_alt": {
        "en": "Size {size} is out of stock in this one, but {alt} is in stock. Shall I add the {alt} instead?",
        "hi": "इसमें {size} size ख़त्म है, पर {alt} स्टॉक में है। {alt} डाल दूँ?",
    },
    "which_size": {
        "en": "Which size would you like? {sizes} are in stock.",
        "hi": "कौन सा size चाहिए? {sizes} स्टॉक में हैं।",
    },
    "adding": {
        "en": "Adding the {name} in {size} to your bag.",
        "hi": "{name}, size {size}, bag में डाल रही हूँ।",
    },
    "adding_one": {"en": "Adding the {name} to your bag.", "hi": "{name} bag में डाल रही हूँ।"},
    "added": {
        "en": "It's in your bag. Shall I take you to checkout, or keep looking?",
        "hi": "bag में आ गया। checkout पर चलें, या और देखें?",
    },
    "add_failed": {
        "en": "That didn't go into the bag: {why}. Shall I try another size?",
        "hi": "वो bag में नहीं गया: {why}। कोई और size देखूँ?",
    },
    "add_first": {
        "en": "Which one shall I add? Tell me the piece and the size.",
        "hi": "कौन सा डालूँ? पीस और size बता दीजिए।",
    },
    "checkout_contact": {
        "en": "Type your name and phone number in the highlighted box; I'll leave your details to you.",
        "hi": "हाइलाइट किए गए बॉक्स में अपना नाम और फ़ोन नंबर टाइप कर दीजिए, आपकी details आप ही भरेंगे।",
    },
    "checkout_address": {
        "en": "Now type your delivery address in the highlighted section.",
        "hi": "अब हाइलाइट किए गए हिस्से में अपना डिलीवरी पता टाइप कर दीजिए।",
    },
    "checkout_payment": {
        "en": "Pick how you'd like to pay here: card, UPI or cash on delivery.",
        "hi": "यहाँ पेमेंट का तरीका चुन लीजिए: card, UPI या cash on delivery।",
    },
    "checkout_place": {
        "en": "When everything looks right, press Place order.",
        "hi": "सब ठीक लगे तो Place order दबा दीजिए।",
    },
    "checkout_again": {
        "en": "Please type it yourself in the highlighted box; I never fill in personal details.",
        "hi": "हाइलाइट किए गए बॉक्स में ख़ुद टाइप कर दीजिए, मैं निजी जानकारी कभी नहीं भरती।",
    },
    "bag_empty": {
        "en": "Your bag is empty right now. Shall we find something first?",
        "hi": "अभी आपका bag खाली है। पहले कुछ ढूँढें?",
    },
    "budget_check": {"en": "Just to check, {amount}, right?", "hi": "बस पक्का कर लूँ, {amount}, सही?"},
    "budget_again": {
        "en": "Sorry, what budget was that?",
        "hi": "माफ़ कीजिए, बजट कितना बताया आपने?",
    },
    "which_product": {"en": "Which one do you mean?", "hi": "आप कौन से वाले की बात कर रहे हैं?"},
    "which_two": {
        "en": "Which two shall I put side by side?",
        "hi": "कौन से दो आमने-सामने रखूँ?",
    },
    "facts": {
        "en": "The {name} is {price}{off}, in {colour}. {stock}",
        "hi": "{name} {price} का है{off}, {colour} रंग में। {stock}",
    },
    # ── Fit ──
    "ask_usual_fit": {
        "en": "What size do you usually wear, and do you like a snug, regular or relaxed fit?",
        "hi": "आप आमतौर पर कौन सा size पहनते हैं, और फ़िटिंग कैसी पसंद है, फ़िटेड, रेगुलर या ढीली?",
    },
    "ask_usual": {
        "en": "What size do you usually wear?",
        "hi": "आप आमतौर पर कौन सा size पहनते हैं?",
    },
    "no_convert": {
        "en": "I can't match {usual} to this one's sizes. Which of these do you usually wear: {sizes}?",
        "hi": "{usual} को इसके size से मिला नहीं पा रहा। इनमें से आप कौन सा पहनते हैं: {sizes}?",
    },
    "fit_pick": {
        "en": "Go for {size}. {reason} Shall I add the {size} to your bag?",
        "hi": "{size} लीजिए। {reason} {size} bag में डाल दूँ?",
    },
    "fit_pick_oos": {
        "en": "Your size would be {wanted}, but it's out of stock in this one. {size} is the nearest in stock. Shall I add the {size}?",
        "hi": "आपका size {wanted} होता, पर इसमें वो ख़त्म है। सबसे करीब {size} स्टॉक में है। {size} डाल दूँ?",
    },
    "fit_one_size": {
        "en": "This one comes in one size, so there's nothing to pick. Shall I add it to your bag?",
        "hi": "ये one size में आता है, तो चुनने को कुछ नहीं। bag में डाल दूँ?",
    },
    "why_same": {
        "en": "Your usual size fits this {cut} cut.",
        "hi": "इस {cut} कट में आपका रोज़ का size ही ठीक रहेगा।",
    },
    "why_oos": {
        "en": "{wanted} is out of stock, so {size} is the nearest size in stock.",
        "hi": "{wanted} ख़त्म है, तो स्टॉक में सबसे करीब {size} है।",
    },
    "why_slim_up": {
        "en": "It's a slim cut and you like it relaxed, so one size up.",
        "hi": "ये स्लिम कट है और आपको ढीला पसंद है, तो एक size बड़ा।",
    },
    "why_loose_down": {
        "en": "It's a loose cut and you like it snug, so one size down.",
        "hi": "ये लूज़ कट है और आपको फ़िटेड पसंद है, तो एक size छोटा।",
    },
    "why_tall_up": {
        "en": "At your height, one size up gives you the length.",
        "hi": "आपकी हाइट के हिसाब से एक size बड़ा लेंगे तो लंबाई सही रहेगी।",
    },
    "chart_row": {
        "en": "The size chart is open. In {size}, {cols}.",
        "hi": "साइज़ चार्ट खुल गया है। {size} में {cols}।",
    },
    "chart_open": {
        "en": "The size chart is open. Which size shall I check for you?",
        "hi": "साइज़ चार्ट खुल गया है। कौन सा size देखूँ?",
    },
    "chart_none": {
        "en": "This one has no size chart; it comes in {sizes}.",
        "hi": "इसका कोई साइज़ चार्ट नहीं है, ये {sizes} में आता है।",
    },
    "picked": {
        "en": "Size {size} it is. Shall I add it to your bag?",
        "hi": "{size} size चुन लिया। bag में डाल दूँ?",
    },
    "no_size": {
        "en": "This one doesn't come in {size}. It comes in {sizes}.",
        "hi": "ये {size} में नहीं आता। ये {sizes} में आता है।",
    },
    # ── Gifts ──
    "gift_ask_both": {
        "en": "Who is it for, and what's the occasion?",
        "hi": "गिफ़्ट किसके लिए है, और मौका क्या है?",
    },
    "gift_ask_recipient": {"en": "And who is it for?", "hi": "और गिफ़्ट किसके लिए है?"},
    "gift_ask_occasion": {"en": "And what's the occasion?", "hi": "और मौका क्या है?"},
    "gift_ask_budget": {
        "en": "Do you have a budget in mind, or shall I not worry about it?",
        "hi": "कोई बजट सोचा है, या बजट की चिंता न करूँ?",
    },
    "gift_show": {
        "en": "Here are {n} ideas. {show}The {name} at {price}, {reason}. {show2}And the {name2} at {price2}, {reason2}. Shall I add one to your bag?",
        "hi": "ये रहे {n} आइडिया। {show}{name}, {price} का, {reason}। {show2}और {name2}, {price2} का, {reason2}। इनमें से कोई bag में डाल दूँ?",
    },
    "gift_show_one": {
        "en": "{show}Here's one idea: the {name} at {price}, {reason}. Shall I add it to your bag?",
        "hi": "{show}एक आइडिया है: {name}, {price} का, {reason}। bag में डाल दूँ?",
    },
    "gift_none": {
        "en": "I couldn't find a gift for all of that yet. Shall I widen the budget, or include clothes if you tell me their size?",
        "hi": "इन सब पर अभी कोई गिफ़्ट नहीं मिला। बजट थोड़ा बढ़ाऊँ, या उनका size बताएँ तो कपड़े भी देखूँ?",
    },
    "wrap_on": {
        "en": "Gift wrap is on for the {name}, ₹49. Would you like a note with it?",
        "hi": "{name} पर गिफ़्ट रैप लग गया, ₹49 का। साथ में कोई नोट लिखना है?",
    },
    "wrap_check": {
        "en": 'The note will read: "{note}". Shall I add it?',
        "hi": 'नोट में लिखा होगा: "{note}"। डाल दूँ?',
    },
    "wrap_done": {
        "en": "Done, it's gift wrapped with your note. Anything else, or shall we check out?",
        "hi": "हो गया, आपके नोट के साथ गिफ़्ट रैप हो गया। और कुछ, या checkout करें?",
    },
    "wrap_off": {"en": "Gift wrap is off for the {name}.", "hi": "{name} से गिफ़्ट रैप हटा दिया।"},
    "wrap_not_in_bag": {
        "en": "The {name} isn't in your bag yet. Shall I add it first?",
        "hi": "{name} अभी bag में नहीं है। पहले bag में डाल दूँ?",
    },
    "note_long": {
        "en": "That note is a bit long; it can be up to {max} characters. Could you make it shorter?",
        "hi": "नोट थोड़ा लंबा है, ज़्यादा से ज़्यादा {max} अक्षर हो सकते हैं। थोड़ा छोटा कर देंगे?",
    },
    # ── Orders ──
    "status_placed": {
        "en": "Order {id} is placed and should reach you by {eta}.",
        "hi": "order {id} प्लेस हो गया है, {eta} तक पहुँच जाना चाहिए।",
    },
    "status_packed": {
        "en": "Order {id} is packed and should reach you by {eta}.",
        "hi": "order {id} पैक हो चुका है, {eta} तक पहुँच जाना चाहिए।",
    },
    "status_shipped": {
        "en": "Order {id} has shipped with {courier} and should reach you by {eta}.",
        "hi": "order {id} {courier} से निकल चुका है, {eta} तक पहुँच जाना चाहिए।",
    },
    "status_out_for_delivery": {
        "en": "Order {id} is out for delivery and reaches you today.",
        "hi": "order {id} डिलीवरी के लिए निकल चुका है, आज पहुँच जाएगा।",
    },
    "status_delivered": {
        "en": "Order {id} was delivered on {date}.",
        "hi": "order {id} {date} को डिलीवर हो गया था।",
    },
    "status_cancelled": {
        "en": "Order {id} was cancelled, and the refund went back to {payment}.",
        "hi": "order {id} कैंसल हो गया था, और रिफ़ंड {payment} में वापस चला गया।",
    },
    "status_return_requested": {
        "en": "A return is requested for order {id}; it will be picked up within 2 days.",
        "hi": "order {id} का return रिक्वेस्ट हो चुका है, 2 दिन में पिकअप हो जाएगा।",
    },
    "can_return": {
        "en": " If anything isn't right, you can return it until {until}.",
        "hi": " कुछ ठीक न लगे तो {until} तक return कर सकते हैं।",
    },
    "order_which": {
        "en": "You have {n} orders on the way: {orders}. Which one shall I open?",
        "hi": "आपके {n} orders रास्ते में हैं: {orders}। कौन सा खोलूँ?",
    },
    "order_which_any": {
        "en": "Which order shall I open? Your recent ones are {orders}.",
        "hi": "कौन सा order खोलूँ? आपके हाल के orders हैं {orders}।",
    },
    "order_unknown": {
        "en": "I can't find order {id}. Your recent ones are {orders}; which one is it?",
        "hi": "order {id} नहीं मिला। आपके हाल के orders हैं {orders}, इनमें से कौन सा?",
    },
    "cancel_open": {
        "en": "I've opened the cancel option for order {id}. Press Cancel order to confirm, and the refund goes back to {payment}.",
        "hi": "order {id} का कैंसल ऑप्शन खोल दिया है। पक्का करने के लिए Cancel order दबाइए, रिफ़ंड {payment} में वापस आएगा।",
    },
    "cancel_shipped": {
        "en": "Order {id} has already shipped, so it can't be cancelled now. Once it's delivered, you can return it within 7 days.",
        "hi": "order {id} निकल चुका है, इसलिए अब कैंसल नहीं हो सकता। डिलीवर होने के बाद 7 दिन के अंदर return कर सकते हैं।",
    },
    "cancel_nothing": {
        "en": "Order {id} is {status}, so there's nothing to cancel.",
        "hi": "order {id} {status} है, तो कैंसल करने को कुछ नहीं है।",
    },
    "change_cancellable": {
        "en": "Once an order is placed, its delivery {what} can't be changed. It hasn't shipped yet, so I can open the cancel for you and you can reorder with the new {what}. Shall I?",
        "hi": "order प्लेस होने के बाद डिलीवरी {what} नहीं बदल सकते। ये अभी निकला नहीं है, तो मैं कैंसल खोल देती हूँ और आप नए {what} के साथ दोबारा order कर सकते हैं। खोल दूँ?",
    },
    "change_shipped": {
        "en": "Once an order is placed, its delivery {what} can't be changed, and this one has already shipped. It should reach you by {eta}.",
        "hi": "order प्लेस होने के बाद डिलीवरी {what} नहीं बदल सकते, और ये पहले ही निकल चुका है। {eta} तक पहुँच जाना चाहिए।",
    },
    "change_done": {
        "en": "Once an order is placed, its delivery {what} can't be changed, and order {id} is already {status}.",
        "hi": "order प्लेस होने के बाद डिलीवरी {what} नहीं बदल सकते, और order {id} पहले ही {status} है।",
    },
    "what_date": {"en": "date", "hi": "की तारीख़"},
    "what_address": {"en": "address", "hi": "का पता"},
    # Said by the brain when the page reports what the shopper did themselves.
    "order_placed": {
        "en": "Thank you, {first}! Your order {id} is placed, and it should reach you by {eta}.",
        "hi": "धन्यवाद {first} जी! आपका order {id} प्लेस हो गया है, {eta} तक पहुँच जाएगा।",
    },
    "order_cancelled": {
        "en": "Done, {first}, order {id} is cancelled. The refund goes back to {payment}.",
        "hi": "हो गया {first} जी, order {id} कैंसल हो गया। रिफ़ंड {payment} में वापस आएगा।",
    },
    "return_submitted": {
        "en": "Done, {first}, your return is in. We'll pick it up within 2 days, and the refund reaches your original payment method within 5 to 7 days of pickup.",
        "hi": "हो गया {first} जी, आपका return दर्ज हो गया। 2 दिन में पिकअप होगा, और पिकअप के 5 से 7 दिन में रिफ़ंड आपके पेमेंट के तरीके में आ जाएगा।",
    },
    # ── Returns ──
    "return_which_order": {
        "en": "Which order is it from? Your delivered ones are {orders}.",
        "hi": "किस order से है? आपके डिलीवर हुए orders हैं {orders}।",
    },
    "return_not_delivered": {
        "en": "Order {id} isn't delivered yet, so a return can't start. Returns open once it arrives.",
        "hi": "order {id} अभी डिलीवर नहीं हुआ, तो return अभी शुरू नहीं हो सकता। पहुँचने के बाद return खुल जाएगा।",
    },
    "return_window": {
        "en": "Order {id} was delivered on {delivered}, and the 7-day return window closed on {closed}, so I'm sorry, it can't be returned now.",
        "hi": "order {id} {delivered} को डिलीवर हुआ था, और 7 दिन की return विंडो {closed} को बंद हो गई, तो माफ़ कीजिए, अब return नहीं हो सकता।",
    },
    "return_fragrance": {
        "en": "I'm sorry, fragrances can't be returned, so the {name} has to stay.{other}",
        "hi": "माफ़ कीजिए, परफ़्यूम return नहीं होते, तो {name} return नहीं होगा।{other}",
    },
    "return_other": {
        "en": " The {name} from that order can go back, though.",
        "hi": " हाँ, उस order का {name} return हो सकता है।",
    },
    "return_already": {
        "en": "A return for the {name} is already requested.",
        "hi": "{name} का return पहले ही रिक्वेस्ट हो चुका है।",
    },
    "return_which_item": {
        "en": "You have {left} days left to return from it. Which item is it: {items}?",
        "hi": "इस order से return के लिए {left} दिन बचे हैं। कौन सा item है: {items}?",
    },
    "return_reason": {
        "en": "You have {left} days left to return the {name}. What's the reason for returning it?",
        "hi": "{name} return करने के लिए {left} दिन बचे हैं। return की वजह क्या है?",
    },
    "return_confirm": {
        "en": "Got it. Is the {name} unused, with its original tags still on?",
        "hi": "ठीक है। क्या {name} इस्तेमाल नहीं हुआ है, और उसके ओरिजिनल टैग लगे हुए हैं?",
    },
    "return_ticked": {
        "en": "Thanks, I've ticked both. Please check the details and press Submit return.",
        "hi": "धन्यवाद, दोनों टिक कर दिए। एक बार देख लीजिए और Submit return दबा दीजिए।",
    },
    "return_used": {
        "en": "I'm sorry, only unused items with the original tags on can be returned.",
        "hi": "माफ़ कीजिए, सिर्फ़ बिना इस्तेमाल किए और ओरिजिनल टैग वाले items ही return हो सकते हैं।",
    },
    # ── Kiosk ──
    "kiosk_found": {
        "en": "{n} pieces match. {show}The {name} at {price} is the most popular. Shall I open it, with the QR code for your phone?",
        "hi": "{n} पीस मिले। {show}{name}, {price} का, सबसे पॉपुलर है। खोल दूँ, फ़ोन के लिए QR code के साथ?",
    },
    "kiosk_none": {
        "en": "Nothing matches all of that. Shall I loosen one thing, like the colour or the price?",
        "hi": "इन सब पर कुछ नहीं मिला। एक चीज़ ढीली करूँ, जैसे रंग या दाम?",
    },
    "kiosk_show": {
        "en": "Here's the {name}, {price}{off}. {stock} Scan the QR code to buy it on your phone.",
        "hi": "ये रहा {name}, {price} का{off}। {stock} फ़ोन पर ख़रीदने के लिए QR code स्कैन कीजिए।",
    },
    "kiosk_qr": {
        "en": "Scan this QR code with your phone camera to open it there.",
        "hi": "अपने फ़ोन के कैमरे से ये QR code स्कैन कीजिए, वहीं खुल जाएगा।",
    },
    "kiosk_qr_list": {
        "en": "Scan this QR code to take your whole shortlist to your phone.",
        "hi": "ये QR code स्कैन कीजिए, पूरी शॉर्टलिस्ट आपके फ़ोन पर आ जाएगी।",
    },
    "kiosk_assist": {
        "en": "A floor assistant is on the way to the kiosk.",
        "hi": "फ़्लोर असिस्टेंट कियोस्क पर आ रहे हैं।",
    },
    # ── Language ──
    "switched": {"en": "Sure, let's continue in English.", "hi": "ज़रूर, अब हिंदी में बात करते हैं।"},
}

#: Why a gift suits them (gifts.show's reasons and the spoken shortlist).
GIFT_WHY: Table = {
    "colour": {"en": "in {colour}, the colour you wanted", "hi": "{colour} रंग में, जैसा आप चाहते थे"},
    "match": {"en": "{what}, just as you asked", "hi": "{what}, जैसा आपने कहा"},
    "festive": {
        "en": "ethnic, just right for {occasion}",
        "hi": "एथनिक, {occasion} के लिए एकदम सही",
    },
    "discount": {"en": "{pct}% off right now", "hi": "अभी {pct}% छूट पर"},
    "popular": {"en": "one of our most loved {type}", "hi": "हमारे सबसे पसंद किए जाने वाले {type} में से"},
}

#: The cut of a product, as the fit lines say it.
CUT: Table = {
    "slim": {"en": "slim", "hi": "स्लिम"},
    "loose": {"en": "loose", "hi": "लूज़"},
    "regular": {"en": "regular", "hi": "रेगुलर"},
}

#: What a product that misses one limit misses ("except" above).
MISSES: Table = {
    "sizes": {"en": "your size", "hi": "आपका size"},
    "colours": {"en": "the colour", "hi": "रंग"},
    "brands": {"en": "the brand", "hi": "ब्रांड"},
    "query": {"en": "the words you asked for", "hi": "आपके बताए शब्द"},
    "usage": {"en": "the occasion", "hi": "मौका"},
    "seasons": {"en": "the season", "hi": "मौसम"},
    "discount_min": {"en": "the discount", "hi": "छूट"},
    "price_min": {"en": "the lower end of your budget", "hi": "बजट की निचली सीमा"},
}

#: The next question worth asking while shopping, by topic (brain.py's _TOPICS).
ASK: Table = {
    "dept": {"en": "Who is it for: men, women or kids?", "hi": "किसके लिए है: पुरुष, महिला या बच्चे?"},
    "types": {"en": "What kind of piece are you after?", "hi": "किस तरह का पीस चाहिए?"},
    "price": {"en": "What budget do you have in mind?", "hi": "आपका बजट कितना है?"},
    "sizes": {"en": "What size should I look for?", "hi": "कौन सा size देखूँ?"},
}

#: The nudge once a piece fits, varied so it never repeats two turns running.
NUDGE: Mapping[str, tuple[str, ...]] = {
    "en": (
        "Shall I open it so you can see it up close?",
        "Want me to check your size in it?",
        "Shall I save it to your wishlist?",
    ),
    "hi": (
        "खोल दूँ, ताकि आप पास से देख सकें?",
        "इसमें आपका size देख लूँ?",
        "wishlist में सेव कर दूँ?",
    ),
}

#: Hindi day and month names, for the dates the brain writes in Hindi.
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

#: The order statuses, as the lines say them in Hindi (English: store.json's labels).
HI_STATUS: Mapping[str, str] = {
    "placed": "प्लेस",
    "packed": "पैक",
    "shipped": "शिप",
    "out_for_delivery": "डिलीवरी के लिए निकला",
    "delivered": "डिलीवर",
    "cancelled": "कैंसल",
    "return_requested": "return रिक्वेस्टेड",
}

#: Words that answer "shall I add it?" with yes, in either language.
YES_WORDS = (
    "yes",
    "yeah",
    "yep",
    "yup",
    "sure",
    "ok",
    "okay",
    "go ahead",
    "add it",
    "do it",
    "go for it",
    "please do",
    "confirm",
    "haan",
    "han",
    "ji",
    "theek hai",
    "daal do",
    "kar do",
    "हाँ",
    "हां",
    "जी",
    "ठीक है",
    "कर दो",
    "कर दीजिए",
    "डाल दो",
    "डाल दीजिए",
    "जोड़ दो",
)
NO_WORDS = (
    "no",
    "nope",
    "not now",
    "wait",
    "don't",
    "dont",
    "nahi",
    "nahin",
    "mat",
    "नहीं",
    "रुको",
    "रुकिए",
    "मत",
)
