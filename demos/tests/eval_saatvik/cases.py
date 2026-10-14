"""The conversations Tushar is held to with the real model: what visitors ask, what
should happen on the page, and what a reply must sound like.

A case is a list of steps. A ``Turn`` is what the visitor says, with what the page
should do:

- ``expect``: every one of these actions must happen; ``any``: at least one;
  ``forbid``: none. ``fnmatch`` patterns over ``navigate:/solar-kits``,
  ``show_section:<heading>``, ``open_faq:<question>``, ``open_document:<title>``,
  ``run_calculator``, ``find_dealer``, ``open_enquiry:<kind>``, ``language_changed:hi``.
- ``ask``: the turn must end with a question that hands the conversation back
  (default yes).
- ``long``: they asked him to explain or talk, so the reply must be longer, and the
  length limits relax.
- ``hindi``: the reply must be in Devanagari.
- ``say_any`` / ``say_not``: regexes over what he said.
- ``fills``: enquiry fields the form must hold after this turn (``name``, ``mobile``…);
  ``no_fill``: the turn must not touch the form (a question asked while it is open).

A ``Page`` step is the extension reporting the page the visitor is on, as the
adapter does after any route change; the runner also sends one by itself after
every ``navigate`` he makes, so "tell me about this" has a page to be about.

The first cases are the dev calls that started this (ab8f6acb and ffdcd2d2,
2026-10-14): one-word answers, "ये देखिए।" and "Here's our SuryaConnect Solar Kit
page." for every question that moved the page.

Everything code cannot check — did he answer, talk about what is on screen, keep
the conversation going, stay plain, stay factual — a second model judges, against
the rubric in ``run.py``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Turn:
    said: str
    expect: tuple[str, ...] = ()
    any: tuple[str, ...] = ()
    forbid: tuple[str, ...] = ()
    ask: bool = True
    long: bool = False
    hindi: bool = False
    say_any: tuple[str, ...] = ()
    say_not: tuple[str, ...] = ()
    fills: tuple[str, ...] = ()  # enquiry fields that must be filled after this turn
    no_fill: bool = False  # this turn must not call open_enquiry


@dataclass(frozen=True)
class Page:
    """The visitor is on ``path`` (the runner fills in its title, headings and FAQs
    from the crawl, as the adapter reports them)."""

    path: str


@dataclass(frozen=True)
class Case:
    id: str
    kind: str  # "calls", "core", "talk", "page", "gray"
    steps: tuple[Turn | Page, ...]
    note: str = ""
    page: str = "/"
    lang: str = "en"


# A reply that only points at the screen.
POINTING = (
    r"^\s*(here it is|here you go|there you go|here's (our|the) [^.?]*\.?)\s*$",
    r"^\s*(ये देखिए|यह रहा|यह देखिए)[।.]?\s*$",
)

CASES: tuple[Case, ...] = (
    # ── The calls that started this ──────────────────────────────────────────
    Case(
        "home-solar-hi",
        "calls",
        (
            Turn(
                "यया मुझे समझना है की मैंने घर पे पहुचा सोलर सिस्टम लगा सकता हूँ", hindi=True, say_not=POINTING
            ),
            Turn("क्या आप उसके बाद बता सकते हो", hindi=True, say_not=POINTING),
            Turn("कुछ बात करो इसके बारे में", hindi=True, long=True, say_not=POINTING),
        ),
        "Session ab8f6acb: he answered 'ये देखिए।' and 'यह रहा।' until asked outright to talk.",
        lang="hi",
    ),
    Case(
        "kit-3kw",
        "calls",
        (
            Turn("I need a three kilowatt system for solar on my home.", say_not=POINTING),
            Turn("In Bangalore, HSR Layout.", say_not=POINTING),
            Turn(
                "Can you recommend the right kit?",
                any=("navigate:/solar-kits*",),
                say_any=(r"SuryaConnect",),
                say_not=POINTING,
            ),
            Turn(
                "Yeah, but which one should I buy from this?",
                say_any=(r"three|3",),
                say_not=POINTING,
            ),
        ),
        "Session ffdcd2d2: 'Here's our SuryaConnect Solar Kit page.' and then nothing. He should "
        "carry the three kilowatts and Bengaluru through.",
    ),
    Case(
        "suitable-for-home",
        "calls",
        (
            Page("/modules/n-topcon"),
            Turn("But is this suitable for a home?", say_not=POINTING),
        ),
        "Session ffdcd2d2, turn 8, on the N-TOPCon page.",
    ),
    # ── Core questions: answered, shown, talked about, handed back ────────────
    Case(
        "which-panel",
        "core",
        (
            Turn(
                "Which panel should I buy for my home?",
                any=("navigate:/modules*", "show_section:*"),
                say_any=(r"TOPCon|PERC",),
            ),
        ),
    ),
    Case(
        "power-cuts",
        "core",
        (
            Turn(
                "We get a lot of power cuts. Which inverter do I need?",
                say_any=(r"hybrid|UDAY Plus|battery",),
            ),
        ),
    ),
    Case(
        "size-from-units",
        "core",
        (
            Turn(
                "My bill is about 350 units a month. What size system do I need?",
                say_any=(r"three kilowatt|3 kilowatt|3 kW",),
            ),
        ),
    ),
    Case(
        "subsidy",
        "core",
        (
            Turn(
                "How much subsidy will I get for a three kilowatt system?",
                say_any=(r"seventy[- ]eight|78",),
            ),
        ),
    ),
    Case(
        "topcon-vs-perc",
        "core",
        (
            Turn(
                "How is TOPCon better than PERC?",
                say_any=(r"heat|temperature|warranty|efficien|degrad",),
            ),
        ),
    ),
    Case(
        "journey",
        "core",
        (
            Turn(
                "Hi, I live in Pune and my electricity bill is about four thousand rupees a month."
            ),
            Turn("What would you suggest for my house?", forbid=("run_calculator",)),
            Turn("We also get power cuts in summer.", say_any=(r"hybrid|UDAY Plus|battery",)),
        ),
        "A real visitor: he should keep Pune, the bill and the power cuts in play, and never run "
        "the calculator from a bill alone.",
    ),
    # ── Asked to talk: a real explanation, not a pointer ──────────────────────
    Case(
        "tell-me-about-this",
        "talk",
        (
            Page("/solar-kits"),
            Turn(
                "Tell me about this.", long=True, say_any=(r"SuryaConnect|kit",), say_not=POINTING
            ),
        ),
    ),
    Case("net-metering", "talk", (Turn("Can you explain net metering in detail?", long=True),)),
    Case(
        "tell-more-hi",
        "talk",
        (
            Page("/modules/n-topcon"),
            Turn("इसके बारे में थोड़ा विस्तार से बताइए।", long=True, hindi=True, say_not=POINTING),
        ),
        lang="hi",
    ),
    # ── Working the page ──────────────────────────────────────────────────────
    Case(
        "calculator",
        "page",
        (
            Turn(
                "I use 400 units a month in Gujarat at 7 rupees a unit. What would I save?",
                expect=("run_calculator",),
            ),
        ),
        "The estimate comes back from the page later; this turn says what he is working out.",
    ),
    Case(
        "dealer",
        "page",
        (Turn("Is there a Saatvik dealer near me in Jaipur?", expect=("find_dealer",)),),
    ),
    Case(
        "datasheet",
        "page",
        (
            Turn(
                "What's the temperature coefficient of the TEJ PLUS panel?",
                say_any=(r"zero point three|0\.3|minus",),
            ),
        ),
    ),
    Case(
        "quote",
        "page",
        (
            Turn(
                "I'd like a quote for a five kilowatt system at my home in Delhi.",
                expect=("open_enquiry:*",),
                ask=False,
            ),
        ),
    ),
    # ── The enquiry form: he fills what they say, as they say it ──────────────
    Case(
        "form-fill",
        "form",
        (
            Turn(
                "I want a quote for a three kilowatt kit at my home in Bengaluru.",
                expect=("open_enquiry:*",),
                ask=False,
            ),
            Turn("My name is Ravi Kumar.", fills=("name",), ask=False),
            Turn(
                "My mobile number is 98475 41790.",
                fills=("name", "mobile"),
                say_any=(r"nine eight four",),
                ask=True,
            ),
            Turn(
                "Yes, that's right. In the message, write that I want it installed before summer.",
                fills=("name", "mobile", "message"),
                ask=False,
            ),
            Turn("What solar products do you have for a restaurant?", no_fill=True),
        ),
        "Session 87f7a6b3: he refused the phone number 'for security', and answered a "
        "product question by opening the form again.",
    ),
    Case(
        "form-fill-hi",
        "form",
        (
            Turn(
                "मुझे तीन किलोवाट की सोलर किट का कोटेशन चाहिए, मैं जयपुर में रहता हूँ।",
                expect=("open_enquiry:*",),
                hindi=True,
                ask=False,
            ),
            Turn(
                "मेरा नाम सुरेश शर्मा है, और मेरा नंबर है नौ आठ सात छह पाँच चार तीन दो एक शून्य।",
                fills=("name", "mobile"),
                hindi=True,
            ),
            Turn("आप मेरा ईमेल भी तो जानते हो ना?", hindi=True, no_fill=True, say_not=(r"@",)),
        ),
        "He knows only what was said in this call: no invented email.",
        lang="hi",
    ),
    # ── Solar kits, the demo ──────────────────────────────────────────────────
    Case(
        "kit-inside",
        "kits",
        (
            Page("/solar-kits"),
            Turn("What comes in the box with this kit?", say_any=(r"inverter",), say_not=POINTING),
        ),
    ),
    Case(
        "kit-power-cut",
        "kits",
        (
            Page("/solar-kits"),
            Turn(
                "Will this kit work during a power cut?",
                say_any=(r"no|not|grid",),
                say_not=POINTING,
            ),
        ),
        "On-grid, no battery: it stops in a power cut; the hybrid inverter and battery give backup.",
    ),
    Case(
        "kit-price",
        "kits",
        (
            Page("/solar-kits"),
            Turn("How much does the three kilowatt kit cost?", say_not=(r"lakh|thousand rupees",)),
        ),
        "Kit prices are not published: no number, the team quotes; he may offer the form.",
    ),
    Case(
        "kit-panels-hi",
        "kits",
        (
            Page("/solar-kits"),
            Turn("तीन किलोवाट की किट में कितने पैनल आते हैं?", hindi=True, say_any=(r"छह|छः",)),
        ),
        "Six 580-watt modules and a 3.3 kVA inverter.",
        lang="hi",
    ),
    Case(
        "kit-why-hi",
        "kits",
        (Page("/solar-kits"), Turn("ये किट क्यों लूँ, इसमें क्या खास है?", hindi=True, say_not=POINTING)),
        lang="hi",
    ),
    Case(
        "kit-subsidy",
        "kits",
        (
            Page("/solar-kits"),
            Turn("Can I get the government subsidy on this kit?", say_any=(r"Surya Ghar|subsidy",)),
        ),
    ),
    # ── Buttons and forms by voice ────────────────────────────────────────────
    Case(
        "click-book-now",
        "buttons",
        (
            Page("/solar-kits"),
            Turn("Click on Book now.", expect=("book_product:*",), ask=False),
            Turn(
                "It's for my home. My name is Anita Rao and I live in Pune.",
                expect=("book_product:residential",),
                fills=(),
                ask=False,
            ),
        ),
        "BOOK NOW is book_product: residential for a home, her name and city filled.",
    ),
    Case(
        "click-datasheet",
        "buttons",
        (
            Page("/solar-kits"),
            Turn("Open the datasheet.", expect=("open_document:*Datasheet*",), say_not=POINTING),
        ),
    ),
    Case(
        "click-brochure-hi",
        "buttons",
        (
            Page("/solar-kits"),
            Turn(
                "ब्रोशर खोल दो।", expect=("open_document:*Brochure*",), hindi=True, say_not=POINTING
            ),
        ),
        lang="hi",
    ),
    Case(
        "click-estimate",
        "buttons",
        (
            Page("/solar-kits"),
            Turn(
                "Click estimate my savings.", any=("navigate:/solar-calculator", "run_calculator")
            ),
        ),
        "He has no units, state or rate yet: open the calculator and ask, one thing at a time.",
    ),
    Case(
        "press-confirm",
        "buttons",
        (
            Page("/solar-kits"),
            Turn("Book this kit for my office.", expect=("book_product:commercial",), ask=False),
            Turn("Just press confirm booking for me.", forbid=("book_product:*",), ask=False),
        ),
        "Confirm booking stays the visitor's: he says so kindly and points to it.",
    ),
    Case(
        "options",
        "buttons",
        (
            Page("/solar-kits"),
            Turn(
                "What options do I have with this kit?",
                say_any=(r"three|five|residential|commercial",),
            ),
        ),
    ),
    # ── The rest of the range ─────────────────────────────────────────────────
    Case(
        "book-module",
        "products",
        (
            Page("/modules/bifacial-g12r"),
            Turn(
                "I want to book this panel for my factory.",
                expect=("book_product:commercial",),
                ask=False,
            ),
        ),
    ),
    Case(
        "book-hybrid-hi",
        "products",
        (
            Page("/inverters/hybrid"),
            Turn(
                "ये इन्वर्टर मेरे घर के लिए बुक कर दो।",
                expect=("book_product:residential",),
                hindi=True,
                ask=False,
            ),
        ),
    ),
    Case(
        "battery-no-booking",
        "products",
        (
            Page("/batteries"),
            Turn("Can I book the UDAY Shakti battery online?", forbid=("book_product:*",)),
        ),
        "The battery has no BOOK NOW: enquiry form or a person, never a booking.",
    ),
    Case(
        "module-tab",
        "products",
        (
            Page("/modules/bifacial-g12r"),
            Turn(
                "Click on mechanical. How heavy is this panel?",
                expect=("open_tab:*",),
                say_any=(r"thirty[- ]three",),
            ),
        ),
    ),
    Case(
        "pump-borewell-hi",
        "products",
        (
            Turn(
                "मेरे खेत में बोरवेल है, कौन सा सोलर पंप लूँ?",
                hindi=True,
                say_any=(r"SaurJal|सौरजल|सबमर्सिबल",),
            ),
        ),
        lang="hi",
    ),
    Case(
        "inverter-power-cut",
        "products",
        (
            Page("/inverters/single-phase"),
            Turn(
                "Will this inverter keep my lights on in a power cut?",
                say_any=(r"no|not|hybrid|UDAY Plus",),
            ),
        ),
    ),
    Case(
        "transformer-rating",
        "products",
        (Turn("What's the largest transformer you make?", say_any=(r"twenty[- ]five|25",)),),
    ),
    # ── Gray areas ────────────────────────────────────────────────────────────
    Case(
        "state-subsidy",
        "gray",
        (Turn("How much extra subsidy does Karnataka give on top of the central scheme?"),),
        "No state figure: state top-ups vary; the national portal or the sales team.",
    ),
    Case(
        "panel-price",
        "gray",
        (Turn("What's the price of one TEJ PLUS panel?"),),
        "Saatvik does not publish panel prices: no number, the sales team quotes.",
    ),
    Case(
        "real-person",
        "gray",
        (
            Turn(
                "Can I talk to a real person?",
                say_any=(r"1800|toll|WhatsApp|call (you )?back|form",),
                ask=False,
            ),
        ),
    ),
    Case(
        "investor",
        "gray",
        (
            Turn(
                "I'm an investor. Where can I find the quarterly results?",
                forbid=("open_enquiry:*",),
            ),
        ),
    ),
    Case(
        "off-topic",
        "gray",
        (Turn("Who won the cricket match yesterday?"),),
        "No answer to it; back to solar.",
    ),
)
