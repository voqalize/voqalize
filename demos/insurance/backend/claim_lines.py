"""What Ananya asks for each field of the claim form, and the few lines she
says through a claim, in each language the call can be in.

The model asks in its own words: the tools hand it the next question from
here. These written lines are the floor under it: when a claim turn ends with
nothing said after a fill (I1: "acted on screen and said nothing", "It's this
section here."), the brain says the next question itself, so a claim turn
never ends without one. A language added to ``persona.json`` needs a row here.
"""

from __future__ import annotations

from .persona import LANGUAGES
from .store import CUSTOMER

_BANK = CUSTOMER.get("bank_on_file", {})
_LAST4 = str(_BANK.get("account_number", ""))[-4:]

#: The question for each field, per language. One question, short and spoken.
ASKS: dict[str, dict[str, str]] = {
    "en": {
        "policy_id": "Which policy is this claim on?",
        "contact_phone": "Which mobile number should we reach you on?",
        "contact_email": "Which email should we write to?",
        "incident_kind": "What happened: an accident, theft, fire, flood, vandalism or broken glass?",
        "incident_date": "On what date did it happen?",
        "incident_time": "At about what time?",
        "incident_city": "In which city did it happen?",
        "incident_location": "Where exactly, which road or landmark?",
        "description": "Could you tell me briefly what happened?",
        "vehicle_drivable": "Can the vehicle still be driven?",
        "driver_is_policyholder": "Were you driving at the time?",
        "driver_name": "Who was driving?",
        "driver_licence": "What is the driving licence number?",
        "other_party_involved": "Was another vehicle or person involved?",
        "other_vehicle_number": "Do you have the other vehicle's number?",
        "other_party_name": "Do you know the other person's name?",
        "injuries": "Was anyone hurt?",
        "police_reported": "Was it reported to the police?",
        "fir_number": "What is the FIR or complaint number?",
        "police_station": "At which police station?",
        "garage_id": "Which garage is the vehicle at, or going to?",
        "garage_other_name": "What is the garage's name and address?",
        "vehicle_location": "Where is the vehicle now: at a garage, at home, or on the roadside?",
        "estimate_amount": "Do you have the garage's repair estimate? How much is it?",
        "patient_member": "Who is the patient?",
        "claim_mode": "Is this a cashless claim at a network hospital, or a reimbursement of bills you paid?",
        "hospital_id": "Which hospital is it?",
        "hospital_other_name": "What is the hospital's name and city?",
        "admission_date": "What was the date of admission, and of discharge if they're home?",
        "discharge_date": "What was the date of discharge?",
        "ailment": "What was the illness or injury?",
        "treatment_kind": "Was it medical treatment, a surgery, a day-care procedure, or an accident?",
        "treating_doctor": "What is the treating doctor's name?",
        "claim_amount": "About how much is the bill, or the hospital's estimate?",
        "account_holder": f"Shall I send the money to your {_BANK.get('bank_name', '')} account ending {_LAST4}?",
        "bank_name": "Which bank should the money go to?",
        "account_number": "What is the account number?",
        "ifsc": "And the IFSC code?",
    },
    "hi": {
        "policy_id": "यह क्लेम किस पॉलिसी पर है?",
        "contact_phone": "आपसे किस मोबाइल नंबर पर बात करें?",
        "contact_email": "किस ईमेल पर लिखें?",
        "incident_kind": "क्या हुआ था: एक्सीडेंट, चोरी, आग, बाढ़, तोड़फोड़ या शीशा टूटा?",
        "incident_date": "यह किस तारीख को हुआ?",
        "incident_time": "लगभग कितने बजे?",
        "incident_city": "किस शहर में हुआ?",
        "incident_location": "ठीक कहाँ, कौन-सी सड़क या लैंडमार्क?",
        "description": "थोड़ा बताइए, हुआ क्या था?",
        "vehicle_drivable": "क्या गाड़ी अभी चल सकती है?",
        "driver_is_policyholder": "क्या उस समय आप गाड़ी चला रहे थे?",
        "driver_name": "गाड़ी कौन चला रहा था?",
        "driver_licence": "ड्राइविंग लाइसेंस का नंबर क्या है?",
        "other_party_involved": "क्या कोई और गाड़ी या व्यक्ति शामिल था?",
        "other_vehicle_number": "क्या आपके पास दूसरी गाड़ी का नंबर है?",
        "other_party_name": "क्या आपको दूसरे व्यक्ति का नाम पता है?",
        "injuries": "क्या किसी को चोट लगी?",
        "police_reported": "क्या पुलिस में रिपोर्ट हुई?",
        "fir_number": "FIR या शिकायत का नंबर क्या है?",
        "police_station": "किस पुलिस स्टेशन में?",
        "garage_id": "गाड़ी किस गैराज में है, या जाएगी?",
        "garage_other_name": "गैराज का नाम और पता क्या है?",
        "vehicle_location": "गाड़ी अभी कहाँ है: गैराज में, घर पर, या सड़क पर?",
        "estimate_amount": "क्या गैराज ने रिपेयर का एस्टिमेट दिया है? कितना है?",
        "patient_member": "मरीज़ कौन है?",
        "claim_mode": "यह नेटवर्क अस्पताल में कैशलेस क्लेम है, या आपने बिल भरा है और रीइंबर्समेंट चाहिए?",
        "hospital_id": "कौन-सा अस्पताल है?",
        "hospital_other_name": "अस्पताल का नाम और शहर क्या है?",
        "admission_date": "भर्ती किस तारीख को हुए, और डिस्चार्ज हो गए हों तो किस तारीख को?",
        "discharge_date": "डिस्चार्ज किस तारीख को हुआ?",
        "ailment": "बीमारी या चोट क्या थी?",
        "treatment_kind": "इलाज मेडिकल था, सर्जरी, डे-केयर, या एक्सीडेंट का?",
        "treating_doctor": "इलाज करने वाले डॉक्टर का नाम क्या है?",
        "claim_amount": "बिल या अस्पताल का एस्टिमेट लगभग कितना है?",
        "account_holder": f"क्या पैसे आपके {_BANK.get('bank_name', '')} खाते में भेज दूँ, जिसके आख़िरी अंक {_LAST4} हैं?",
        "bank_name": "पैसे किस बैंक में भेजें?",
        "account_number": "खाता नंबर क्या है?",
        "ifsc": "और IFSC कोड?",
    },
}

#: The lines a claim turn ends on when the model said nothing after its tool.
LINES: dict[str, dict[str, str]] = {
    "en": {
        "ack": "Got it.",
        "amount_ack": "Got it, {amount}.",
        "amount_check": "Just to check: is the amount {amount}?",
        "amount_unclear": "Sorry, I didn't catch the amount. About how much is it, in rupees?",
        "amount_small": "Just to check, I heard {amount}. Is that right, or did you mean lakh?",
        "not_taken": "Sorry, I couldn't fill that in. {ask}",
        "upload": "That's every detail. Now please upload {docs} with the buttons on screen, and I'll open the review.",
        "review": "That's everything. Here's the review: please tick the declaration and press Submit claim.",
        "uploaded_left": "Thanks, that's in. Still to upload: {docs}.",
        "upload_only": "Please upload {docs} with the buttons on screen.",
        "policy_open": "Here's your policy. What would you like to check in it?",
        "start": "The {kind} claim form is open. {ask}",
        "which_policy": "The {kind} claim form is open. Which policy is it on?",
        "and": " and ",
    },
    "hi": {
        "ack": "ठीक है।",
        "amount_ack": "ठीक है, {amount}।",
        "amount_check": "एक बार पक्का कर लूँ: रकम {amount} है?",
        "amount_unclear": "माफ़ कीजिए, रकम ठीक से सुनाई नहीं दी। लगभग कितने रुपये हैं?",
        "amount_small": "एक बार पक्का कर लूँ, मैंने {amount} सुना। सही है, या आपका मतलब लाख से था?",
        "not_taken": "माफ़ कीजिए, यह भर नहीं पाई। {ask}",
        "upload": "सारी जानकारी भर गई है। अब स्क्रीन पर बटन से {docs} अपलोड कर दीजिए, फिर मैं रिव्यू खोल दूँगी।",
        "review": "सब भर गया है। यह रहा रिव्यू: डिक्लेरेशन पर टिक करके Submit claim दबा दीजिए।",
        "uploaded_left": "धन्यवाद, यह आ गया। अभी अपलोड करना है: {docs}।",
        "upload_only": "स्क्रीन पर बटन से {docs} अपलोड कर दीजिए।",
        "policy_open": "यह रही आपकी पॉलिसी। इसमें क्या देखना है?",
        "start": "{kind} क्लेम फ़ॉर्म खुल गया है। {ask}",
        "which_policy": "{kind} क्लेम फ़ॉर्म खुल गया है। यह किस पॉलिसी पर है?",
        "and": " और ",
    },
}

#: What she asks on arriving at a page with go_to: the job's first question.
JOB_ASKS: dict[str, dict[str, str]] = {
    "en": {
        "home": "What would you like to do: a quote, a question about your cover, or a claim?",
        "quote": "Tell me a little about what you'd like to insure, and I'll build the quote right here.",
        "policies": "Here are your policies. What would you like to check?",
        "claim": "Tell me what happened, and I'll fill in the form as you talk.",
    },
    "hi": {
        "home": "बताइए, क्या करें: क्वोट, आपके कवर के बारे में सवाल, या क्लेम?",
        "quote": "थोड़ा बताइए कि क्या इंश्योर करना है, मैं यहीं क्वोट बना देती हूँ।",
        "policies": "ये रहीं आपकी पॉलिसी। क्या देखना है?",
        "claim": "बताइए क्या हुआ, मैं साथ-साथ फ़ॉर्म भरती जाऊँगी।",
    },
}

#: The claim types as said in each language.
KINDS: dict[str, dict[str, str]] = {
    "en": {"motor": "motor", "health": "health"},
    "hi": {"motor": "मोटर", "health": "हेल्थ"},
}

#: Documents as said in Hindi (English uses the form's own labels).
DOCS_HI: dict[str, str] = {
    "driving_licence": "ड्राइविंग लाइसेंस",
    "rc_copy": "RC",
    "damage_photos": "नुकसान की फ़ोटो",
    "fir_copy": "FIR की कॉपी",
    "repair_estimate": "गैराज का एस्टिमेट",
    "discharge_summary": "डिस्चार्ज समरी",
    "hospital_bills": "अस्पताल का फ़ाइनल बिल और रसीदें",
    "reports": "प्रिस्क्रिप्शन और जाँच की रिपोर्ट",
    "id_proof": "मरीज़ का फ़ोटो ID",
    "cancelled_cheque": "कैंसिल्ड चेक",
}

assert all(
    lang in ASKS and lang in LINES and lang in KINDS and lang in JOB_ASKS for lang in LANGUAGES
), "a language in persona.json has no claim lines in claim_lines.py"


def job_ask(mode: str, lang: str) -> str:
    rows = JOB_ASKS.get(lang, JOB_ASKS["en"])
    return rows.get(mode, rows["home"])


def ask(field_id: str, lang: str) -> str:
    rows = ASKS.get(lang, ASKS["en"])
    return rows.get(field_id) or ASKS["en"][field_id]


def line(key: str, lang: str, **kw: str) -> str:
    return LINES.get(lang, LINES["en"])[key].format(**kw)


def _mid(label: str) -> str:
    """A label mid-sentence: "Patient's photo ID" → "patient's photo ID" (RC, FIR kept)."""
    return label if label[1:2].isupper() else label[:1].lower() + label[1:]


def docs_said(docs: list[dict[str, str]], lang: str) -> str:
    names = [DOCS_HI.get(d["id"], d["label"]) if lang == "hi" else _mid(d["label"]) for d in docs]
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + line("and", lang) + names[-1]
