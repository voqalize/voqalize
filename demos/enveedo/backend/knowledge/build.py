# pyright: basic
# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Build Enveedo's L3 knowledge: the pages of enveedo.com, English and Spanish,
read from a real browser, and the catalogue of places on them Javier points at.

The build runs offline on a dev machine; its output is committed and the brain
only ever reads the JSON. Network is touched only by ``crawl``; every page's
reading is cached outside the repository, so ``--offline`` rebuilds from it.

enveedo.com is HubSpot CMS drag-and-drop: a full page load per navigation, a
sticky header 66 px high once scrolled (the adapter scrolls with a 90 px
offset). Every top-level section is a ``.row-fluid-wrapper`` whose class holds
its index (``content_bucket-row-3-…``), and the heading of each sits in a
HubSpot module wrapper with a stable id (``#hs_cos_wrapper_module_<digits>``).
The catalogue prefers the module id, which survives a reorder, and keeps the
row selector beside it as ``fallback``, worked out on the live page from the
module's own row. The Spanish site (``/es/…``, same slugs) is a HubSpot
translation of the same templates and shares most module ids; where it does
not, each place lists the Spanish id as a second candidate and the first that
matches on the page wins.

Run from ``voqalize/demos`` (Chromium installed once with ``playwright install
chromium``; always headless)::

    uv run --no-project --with playwright python enveedo/backend/knowledge/build.py crawl
    uv run --no-project --with playwright python enveedo/backend/knowledge/build.py crawl --refresh
    uv run --no-project python enveedo/backend/knowledge/build.py crawl --offline

``crawl`` renders every page of the catalogue below in both languages, one at
a time with :data:`PAUSE_S` between loads (the site is a real company's). A
page already in the cache is not rendered again unless ``--refresh``. No form
is filled or submitted; the only presses are the site's own tabs, accordions
and Without/With toggle, to check the ``reveal`` metadata and read what they
hide. The cookie banner is never pressed. It writes, next to this file:

- ``L3/anchors.json`` — the catalogue (shape in ``../knowledge/README.md``):
  every page under its English **and** its Spanish path, with the same keys.
- ``L3/pages.json`` — one record per page and language: ``{path, url, lang,
  twin, kind, title, description, sections: [{key, heading, text}], text}``.
- ``L3/site.json`` — the twins map, the calls to action that leave the site
  (the scheduler's own page, the sign-in, the gated eBooks and webinars, the
  platform PDF, the blog), the contact details, the contact form's countries.

It also regenerates ``L2/site-map.md``. L1 and the other L2 topics are
hand-written and not touched.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
L3 = HERE / "L3"
SITE = "https://enveedo.com"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "voqalize-enveedo"
#: The sticky header once scrolled, and the offset the adapter scrolls with.
HEADER_PX = 66
SCROLL_OFFSET_PX = 90
TEXT_CAP = 1600
#: Seconds between two page loads: gently, on a real company's site.
PAUSE_S = 4.0

ROW = '#main-content [class*="content_bucket-row-{}-"]'


# ─── The catalogue ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Place:
    """A place on a page. ``ids`` are candidate selectors, tried in order on
    each language's page; the first that matches exactly one laid-out element
    is the place's ``selector``. ``reveal`` is ``(click, open)``: the control
    that opens it, and a selector that matches once it is open."""

    key: str
    label: str
    ids: tuple[str, ...]
    reveal: tuple[str, str] | None = None
    hidden: bool = False
    optional: bool = False
    """Laid out late or only once used (the scheduler's frame): checked to
    exist, not to be laid out."""
    row: bool = True
    """Whether a row ``fallback`` is worked out for it."""


def mod(*ids: str) -> tuple[str, ...]:
    """HubSpot module wrappers by id: ``"module_1745873440679"`` →
    ``#hs_cos_wrapper_module_1745873440679``."""
    return tuple(f"#hs_cos_wrapper_{i}" for i in ids)


def P(key: str, label: str, *ids: str, **kw: Any) -> Place:  # noqa: N802
    return Place(key, label, mod(*ids), **kw)


def S(key: str, label: str, *selectors: str, **kw: Any) -> Place:  # noqa: N802
    return Place(key, label, tuple(selectors), **kw)


@dataclass(frozen=True)
class PageSpec:
    kind: str
    es: str | None
    places: tuple[Place, ...]
    forms: tuple[str, ...] = ()
    header: bool = True
    footer: bool = True
    extra: dict[str, Any] = field(default_factory=dict[str, Any])


HOW = "#featshow_17458729551117"
ABOUT_TABS = "#featshow_17170271512727"


def featshow(root: str, n: int) -> tuple[str, str]:
    li = f"{root} .featshow__nav li:nth-child({n})"
    return (f"{li} .featshow__btn", f"{li} .featshow__btn--active")


def featshow_item(root: str, n: int) -> str:
    return f"{root} .featshow__items > .featshow__item:nth-child({n})"


#: The home page's four "How Enveedo Works" tabs.
HOW_TABS = (
    ("how_business_first", "How Enveedo Works tab: Business-First Risk Management"),
    ("how_integration", "How Enveedo Works tab: Intelligent Integration"),
    ("how_automation", "How Enveedo Works tab: Workflow Automation"),
    ("how_reporting", "How Enveedo Works tab: Executive-Ready Reporting"),
)
ABOUT_TAB_KEYS = (
    ("tab_mission", "Mission tab"),
    ("tab_vision", "Vision tab"),
    ("tab_philosophy", "Philosophy tab"),
)

#: The FAQ: (accordion group module number, item n, key, the question).
FAQ: tuple[tuple[int, int, str, str], ...] = (
    (7, 1, "faq_what_is", "What is Enveedo?"),
    (7, 2, "faq_benefit", "How can Enveedo benefit my organization?"),
    (7, 3, "faq_different", "What makes Enveedo different from other cybersecurity platforms?"),
    (
        7,
        4,
        "faq_msp_or_business",
        "Is the platform for MSPs and MSSPs or for individual businesses?",
    ),
    (7, 5, "faq_msp_support", "Is the platform designed to support MSPs, MSSPs and VARs?"),
    (7, 6, "faq_individual_business", "How can individual businesses leverage the platform?"),
    (10, 1, "faq_who_benefits", "Who can benefit from using Enveedo?"),
    (10, 2, "faq_integrate", "Can Enveedo integrate with my existing security tools?"),
    (10, 3, "faq_prioritize", "How does Enveedo prioritize which assets to protect?"),
    (13, 1, "faq_start", "How do I start using Enveedo?"),
    (13, 2, "faq_support", "What support does Enveedo offer to its partners and clients?"),
    (13, 3, "faq_compliance", "How does Enveedo ensure compliance with regulatory requirements?"),
    (13, 4, "faq_incident", "What support does Enveedo provide during a cybersecurity incident?"),
    (13, 5, "faq_training", "Is there training available for new users?"),
    (13, 6, "faq_data_security", "How does Enveedo ensure the security of its clients' data?"),
)


def faq_place(group: int, n: int, key: str, question: str) -> Place:
    panel = f"accordion-panel-content_bucket-module-{group}-{n}"
    chevron = f'button[aria-controls="{panel}"]'
    return Place(
        key,
        f"FAQ: {question}",
        (f".accordion__item:has({chevron})",),
        reveal=(
            f".accordion__item:has({chevron}) .accordion__header",
            f'{chevron}[aria-expanded="true"]',
        ),
        row=False,
    )


#: The 39 framework cards on /frameworks: (key, name as the card writes it,
#: module id, group). /es/frameworks shares most module ids; where it does
#: not, the Spanish one follows a "|".
FRAMEWORKS: tuple[tuple[str, str, str, str], ...] = (
    ("fw_iso_27001", "ISO/IEC 27001:2022", "17423083193982", "infosec"),
    ("fw_soc2", "SOC 2 Readiness", "1743177126616", "infosec"),
    ("fw_tisax", "TISAX ISA", "1743177252147", "infosec"),
    ("fw_nist_800_82", "NIST SP 800-82", "1745862175346", "infosec"),
    ("fw_iso_9001", "ISO/IEC 9001:2015", "1764085327487|1764085576573", "infosec"),
    ("fw_nist_csf", "NIST CSF v2.0", "17431767373473", "infosec"),
    ("fw_hipaa", "HIPAA Security Rule", "1743177071091", "infosec"),
    ("fw_iso_27002", "ISO/IEC 27002:2022", "1745848877389", "infosec"),
    ("fw_nis2", "NIS2 Directive", "1753745043604|1753745263844", "infosec"),
    ("fw_dora", "DORA", "1765828830775|1765828989069", "infosec"),
    ("fw_pci_dss", "PCI DSS v4.0.1", "1743176773560", "infosec"),
    ("fw_iso_31000", "ISO/IEC 31000:2018", "1743176833397", "infosec"),
    ("fw_iso_27017_csc", "ISO/IEC 27017:2015 (CSC)", "1745848978376", "infosec"),
    ("fw_ens", "ENS (Spain)", "1753745176470|1753745266514", "infosec"),
    ("fw_cis", "CIS CSC V8.1", "17431766360223", "infosec"),
    ("fw_iso_22301", "ISO/IEC 22301:2019", "1743176898816", "infosec"),
    ("fw_iso_27017_csp", "ISO/IEC 27017:2015 (CSP)", "1745849025140", "infosec"),
    ("fw_nist_800_171", "NIST SP 800-171 Rev. 3", "1758909788350|1758909899765", "infosec"),
    ("fw_eu_ai_act", "EU AI Act", "174413455307345", "ai"),
    ("fw_nist_ai_rmf", "NIST AI RMF 600-1", "174413455307346", "ai"),
    ("fw_iso_42001", "ISO/IEC 42001:2023", "174413455307336", "ai"),
    ("fw_gdpr", "GDPR", "17431766853892", "privacy"),
    ("fw_enveedo_pia", "Enveedo PIA", "1743177160817", "privacy"),
    ("fw_colombia_data", "Colombia Data Protection Law", "174413457910928", "privacy"),
    ("fw_mexico_public", "Mexico Data Protection Law (Public)", "174413457910948", "privacy"),
    ("fw_anexo_28", "Anexo 28 RMF 2024", "1761676097678|1761676168215", "privacy"),
    ("fw_nist_privacy", "NIST Privacy Framework v1.0", "1743177010783", "privacy"),
    ("fw_argentina_data", "Argentina Data Protection Law", "174413457910916", "privacy"),
    ("fw_mexico_private", "Mexico Data Protection Law (Private)", "174413457910938", "privacy"),
    ("fw_chile_cyber_law", "Chile Cybersecurity Law", "174413457910917", "privacy"),
    ("fw_circular_co_sa", "Circular CO SA 17.18/24", "1761676101153|1761676165119", "privacy"),
    ("fw_iso_27701", "ISO/IEC 27701:2025", "1744135444019", "privacy"),
    ("fw_chile_21719", "Chile Data Protection Law (21.719)", "174413457910949", "privacy"),
    ("fw_peru_data", "Peru Data Protection Law", "174413457910929", "privacy"),
    ("fw_chile_19628", "Chile Data Protection Law (No. 19628)", "1745849432956", "privacy"),
    ("fw_lgpd", "LGPD (Brazil)", "174413457910927", "privacy"),
    ("fw_ce_007", "CE 007/2018 Requirements", "174413457910939", "privacy"),
    ("fw_panama_data", "Panama Data Protection Law", "1753116360640", "privacy"),
    ("fw_costa_rica_data", "Costa Rica Data Protection Law", "1753116428818", "privacy"),
)

CONTACT_FORM = 'form.hs-form[id^="hsForm_9ab169f1-2d40-4869-9f6f-943c71b98aa7"]'
SOC2_FORM = 'form.hs-form[id^="hsForm_8e75d561-509b-4454-a003-d60115042fc9"]'
EBOOK_FORM = 'form.hs-form[id^="hsForm_f7305477-fec3-4662-8abd-486782f2599d"]'


def form_places(prefix: str, form: str) -> tuple[Place, ...]:
    """The consent box and Submit of a form: the adapter's, to ring for the
    visitor. Never pressed by anyone but them."""
    return (
        S(
            f"{prefix}_consent",
            "Consent checkbox (the visitor ticks it)",
            f"{form} .legal-consent-container",
            hidden=True,
            row=False,
        ),
        S(
            f"{prefix}_submit",
            "Submit button (the visitor presses it)",
            f"{form} input.hs-button[type=submit]",
            hidden=True,
            row=False,
        ),
    )


LEGAL = (
    P("title", "Page title", "module_17158069187937", "module_17158070350337"),
    P("body", "The text", "widget_1715799039480", "module_1733171808937"),
)

PAGES: dict[str, PageSpec] = {
    "/": PageSpec(
        "home",
        "/es/",
        (
            # The Spanish hero's module is an empty box; its content is the row.
            Place(
                "hero",
                "Hero: Security Program Management. Simplified. (Book a Demo)",
                (*mod("widget_1752815223713", "widget_1752815599119"), ROW.format(2)),
            ),
            P(
                "customers",
                "Trusted by Security Leaders: customer logos (DirecTV, Hail & Cotton, Berel, La Seele, Swiss Medical)",
                "module_17512825985702",
            ),
            P(
                "problem",
                "Cybersecurity isn't broken because of missing tools: the problem statement",
                "module_17512822864143",
            ),
            S(
                "without_with",
                "Without / With Enveedo: four cards (Integration & Visibility, Business Alignment, Compliance & Governance, Operational Efficiency)",
                ".cybersecurity-section .cards-container",
            ),
            S(
                "toggle_without",
                "The four cards switched to Without Enveedo",
                ".cybersecurity-section .cards-container",
                reveal=("#toggle-switch", "#without-label.active"),
            ),
            S(
                "toggle_with",
                "The four cards switched to With Enveedo (Unified Security Platform, Strategic Security Partner, Automated Compliance, Optimized Operations)",
                ".cybersecurity-section .cards-container",
                reveal=("#toggle-switch", "#with-label.active"),
            ),
            P(
                "timeline",
                "Impact Timeline: Understand, Plan, Execute, Evolve",
                "widget_1751480269408",
            ),
            *(
                S(
                    f"timeline_{k}",
                    f"Impact Timeline step {n}: {t}",
                    f"#hs_cos_wrapper_widget_1751480269408 .timeline-section:nth-of-type({n})",
                    row=False,
                )
                for n, k, t in (
                    (1, "understand", "Understand (current state)"),
                    (2, "plan", "Plan (strategic roadmap)"),
                    (3, "execute", "Execute (implementation)"),
                    (4, "evolve", "Evolve (continuous improvement)"),
                )
            ),
            P("how_it_works", "How Enveedo Works: four capability tabs", "module_1745873440679"),
            *(
                S(key, label, featshow_item(HOW, n), reveal=featshow(HOW, n), row=False)
                for n, (key, label) in enumerate(HOW_TABS, 1)
            ),
            P(
                "frameworks_intro",
                "Security, AI, and Privacy Frameworks at Your Fingertips",
                "module_17526866102234",
            ),
            P(
                "framework_badges",
                "Framework badges (ISO 27001, CIS, GDPR, NIST CSF 2.0, PCI DSS, SOC 2, EU AI Act, …)",
                "module_17525193611194",
            ),
            P(
                "frameworks_cta",
                "Supporting 45+ frameworks: Explore all Frameworks",
                "module_17458739579293",
            ),
            P(
                "impact_stats",
                "Real-World Impact: 5x faster risk assessment, 50% more efficiency, 3x more strategic focus",
                "module_1745873602846",
            ),
            P(
                "integrations",
                "Supported Integrations: logo carousel",
                "module_17533261030766",
                "module_17533261379964",
            ),
            P(
                "business_advantage",
                "Turn Security into a Business Advantage",
                "module_17458748771523",
            ),
            P("outcome_interruption", "Reduced Business Interruption", "module_17172663113362"),
            P("outcome_innovation", "Accelerated Innovation", "module_17526877148635"),
            P("outcome_confidence", "Improved Stakeholder Confidence", "module_17458756286825"),
            P("outcome_compliance", "Faster Compliance & Audit Readiness", "module_17526729492405"),
            P("testimonials_intro", "Security Leaders Trust Enveedo", "module_17458757464803"),
            P(
                "testimonials",
                "Three anonymous testimonials (CISO, VP IT, CTO)",
                "widget_1752694356992",
                "widget_1752694386938",
            ),
            P(
                "final_cta",
                "Ready to Transform Your Security Program? (value within 30 days; Book a Demo)",
                "module_1752673479051",
            ),
        ),
    ),
    "/enveedo_platform": PageSpec(
        "platform",
        "/es/enveedo_platform",
        (
            P(
                "hero",
                "The Complete Platform for Security Program Management",
                "module_17533669048217",
                "module_17533671860279",
            ),
            P(
                "strategy",
                "Build Your Cybersecurity Strategy: the nerve center of your program",
                "module_1720842160327",
            ),
            P("integrations", "Supported Integrations", "module_17532332226713"),
            P(
                "modules",
                "Fully Integrated Security Management: six modules (Crown Jewel Analysis, Risk Register, Compliance Management, Vendor Risk Management, Incident Response Manager, Security Roadmap)",
                "module_1752529832940",
            ),
            P(
                "integration_capabilities",
                "Integration capabilities: pre-built integrations, API framework, data import/export, identity",
                "module_1752527758938",
            ),
            P(
                "automation",
                "Smart automation: tasks, evidence collection, control testing, risk updates, reporting",
                "module_1753234273260",
            ),
            P(
                "dashboards",
                "Dashboard preview: executive, operational, compliance, risk, vendor",
                "module_17525283940005",
            ),
            P("advantage", "The Enveedo Advantage", "module_1721164175389"),
            P(
                "comparison",
                "Comparison table: Enveedo vs program management, compliance automation and vCISO platforms",
                "module_17525886608353",
            ),
            P("channel_partners", "Channel Partners logos", "module_1753324203208"),
        ),
    ),
    "/security-performance-os": PageSpec(
        "enterprise",
        "/es/security-performance-os",
        (
            P(
                "hero",
                "Security Performance OS: an integrated, governable, measurable system (Request Executive Briefing)",
                "widget_1752815223713",
            ),
            P(
                "why_stall",
                "Why Enterprise Cybersecurity Programs Stall: fragmentation, duplication, hard-to-defend risk, disruptive audits",
                "module_1772628492192",
            ),
            P("our_platform", "Our Platform", "module_17727135982866"),
            P("performance", "Enterprise-grade operational performance", "module_1745873440679"),
            P("control_performance", "Control Performance", "module_17172663113362"),
            P(
                "risk_performance",
                "Risk Performance (qualitative, semi-quantitative, quantitative; financial quantification)",
                "module_17526877148635",
            ),
            P("audit_performance", "Audit Performance", "module_17726289296364"),
            P(
                "document_management",
                "Document Management",
                "module_17900864545886",
                "module_17901075544133",
            ),
            P(
                "multi_workspace",
                "Unified Multi-Workspace Console",
                "module_17900867496555",
                "module_17901077027575",
            ),
            P(
                "ai_suggestions",
                "AI-powered risk suggestions (only anonymized data is shared)",
                "module_17901827904957",
                "module_17901832133927",
            ),
            P(
                "enterprise_complexity",
                "Designed for the real complexity of enterprise environments",
                "module_17901079806726",
                "module_17901077944366",
            ),
            P(
                "comparison",
                "Beyond spreadsheets, more agile than generic GRC platforms: comparison",
                "module_17533261030766",
            ),
            P(
                "strategic_advantage",
                "Turn your cybersecurity program into a strategic advantage",
                "module_17458748771523",
            ),
            P(
                "final_cta",
                "Elevate your Cybersecurity Program to the Enterprise Level (Schedule a Strategic Briefing)",
                "module_1752673479051",
            ),
        ),
    ),
    "/frameworks": PageSpec(
        "frameworks",
        "/es/frameworks",
        (
            P(
                "intro",
                "Frameworks: simplifying compliance, the Assessment module",
                "module_17171691078105",
            ),
            P("infosec", "Information Security Frameworks", "widget_1744134422226_"),
            P("ai", "AI Frameworks", "module_17441345113903_"),
            P(
                "privacy",
                "Privacy Frameworks (and Latin American data laws)",
                "module_17441345691994_",
            ),
            *(
                P(
                    key,
                    f"Framework card: {name}",
                    *(f"module_{m}" for m in mid.split("|")),
                    row=False,
                )
                for key, name, mid, _ in FRAMEWORKS
            ),
            S(
                "contact_form",
                "How can we help? The contact form",
                "#hs_cos_wrapper_widget_1743178741027",
                "#hs_cos_wrapper_widget_1743178741027_",
                row=False,
            ),
            *form_places("contact", CONTACT_FORM),
        ),
        forms=("contact",),
    ),
    "/partners": PageSpec(
        "partners",
        "/es/partners",
        (
            P(
                "hero",
                "A Strategic Security Enabler for MSSPs and MSPs (Become a Partner)",
                "module_17534714210569",
            ),
            P(
                "why_partner",
                "Why Partner with Enveedo? vCISO services at speed and scale",
                "module_1753471456381",
            ),
            P(
                "benefits",
                "Partners Benefits: multitenancy, custom marketplace, deploy in minutes, reporting, API",
                "module_175347146068010",
            ),
            P("ecosystem", "Include Enveedo in Your Ecosystem", "module_17534714643887"),
            P("integrations", "Supported Integrations", "module_17534714756916"),
            P("apply", "Start Your Partner Application Process", "module_17534714832716"),
            P("channel_partners", "Channel Partners logos", "module_17534714876656"),
            S(
                "become_partner",
                "Become a Partner button",
                "#hs_cos_wrapper_module_175347142105613 a.hs-button",
                hidden=True,
                row=False,
            ),
        ),
    ),
    "/book-a-demo": PageSpec(
        "demo",
        "/es/book-a-demo",
        (
            P("hero", "Book a Demo", "widget_1791379111352"),
            P(
                "start_with",
                "Start with Enveedo: continuous risk assessment, integrations, 170+ controls, CISO Concierge",
                "widget_1716876752676",
            ),
            P(
                "demo_request",
                "Request a product demo: a free risk assessment with a CISO strategist",
                "module_1791381102074",
            ),
            S(
                "demo_calendar",
                "The demo scheduler (HubSpot Meetings, Elis Martinez)",
                ".meetings-iframe-container",
                optional=True,
                row=False,
            ),
            P("contact_info", "Contact Us: phone, address, email", "module_1791381650751"),
        ),
        forms=("demo",),
    ),
    "/book-a-demo-grl": PageSpec(
        "demo_ebook",
        "/es/book-a-demo-rsa",
        (
            P("hero", "Security Program Management. Simplified.", "widget_1744399024136"),
            P("about", "About Enveedo", "widget_1716876752676"),
            P("ebook_form", "Request our eBook Now! (form)", "widget_1745500226977"),
        ),
    ),
    "/contact": PageSpec(
        "contact",
        "/es/contact",
        (
            P("contact_form", "How can we help? The contact form", "widget_1716878052199"),
            P("resiliency", "Building Cyber Resiliency is a Necessity", "module_1717112965152"),
            P("contact_info", "Phone, address and email", "module_1716764386729"),
            P(
                "ecosystem",
                "Join an Ecosystem: partnership program and free risk assessment",
                "module_17168774779998",
            ),
            *form_places("contact", CONTACT_FORM),
        ),
        forms=("contact",),
    ),
    "/about-us": PageSpec(
        "about",
        "/es/about-us",
        (
            P("hero", "We are Security: One Team. One Mission.", "module_17170146204427"),
            P("who_we_are", "Who Are We?", "module_17158208562238"),
            P("mission", "Mission, Vision, Philosophy tabs", "module_17170271512727"),
            *(
                S(
                    key,
                    label,
                    featshow_item(ABOUT_TABS, n),
                    reveal=featshow(ABOUT_TABS, n),
                    row=False,
                )
                for n, (key, label) in enumerate(ABOUT_TAB_KEYS, 1)
            ),
            P("team", "Meet the Team", "module_1717082556932"),
            P("principles", "Our Principles", "module_1716939980175"),
            P(
                "investors",
                "Our Investors (Silverton Partners, Runtime Ventures, Blue Venture)",
                "module_17169694491009",
            ),
        ),
    ),
    "/resources": PageSpec(
        "resources",
        "/es/resources",
        (
            P("hero", "Cyber Risk Resources for MSPs (Visit Our Blog)", "module_1717012785500"),
            P("blog", "Cyber Pulse Blog: the latest post", "module_17170553645936"),
            P("about", "Meet Enveedo: mission, vision, philosophy", "module_1717055778282"),
            P("insurance", "Protect Your Business: Cyber Insurance", "module_17170110182913"),
            P(
                "faq_glossary",
                "Enveedopedia and EncyloCISO: FAQ and glossary",
                "module_17170559731104",
            ),
            P(
                "content_guide",
                "All-In-One Strategy Execution Guide (the platform PDF)",
                "module_17167640249185",
            ),
            P("join", "Become a Partner / Book a Risk Free Assessment", "module_17170556932258"),
        ),
    ),
    "/cyber-insurance": PageSpec(
        "insurance",
        "/es/cyber-insurance",
        (
            P("hero", "Cyber Insurance has never been more complex", "module_17170151808127"),
            P("benefits", "Benefits of Cyber Insurance", "module_1717044767953"),
            P("approval", "Increase Approval Decisions", "module_17169623093987"),
            P("procuring", "Procuring Cyber Insurance", "module_17170448622152"),
            P(
                "reduce_friction",
                "Reduce friction during the procurement process",
                "module_17167623970575",
            ),
            P("features", "Enveedo Features at a Glance", "module_17170448238982"),
            P(
                "program_overview",
                "Program Overview: Crown Jewel Analysis and more",
                "module_171676249562610",
            ),
            P("key_benefits", "Key Benefits of Cyber Risk Management", "module_17170448965962"),
            P(
                "prioritize_assets",
                "Prioritize Critical Assets (Crown Jewel Analysis)",
                "module_17172897359946",
            ),
            P(
                "visibility_automation",
                "Continuous visibility and automation",
                "module_17172897468278",
            ),
            P(
                "incident_response",
                "Integrated incident response management",
                "module_17172897793696",
            ),
            P(
                "api_integrations",
                "Streamline Security with API Integrations",
                "module_17172897670088",
            ),
            P("ecosystem", "Join an Ecosystem (Book Risk Assessment)", "module_17168757507576"),
        ),
    ),
    "/faq": PageSpec(
        "faq",
        "/es/faq",
        (
            P("header", "Enveedopedia FAQ", "module_1716931732754"),
            S(
                "faq_general",
                "FAQ group: General Information",
                "#hs_cos_wrapper_content_bucket-module-7",
            ),
            S(
                "faq_platform",
                "FAQ group: Platform Functionality",
                "#hs_cos_wrapper_content_bucket-module-10",
            ),
            S(
                "faq_services",
                "FAQ group: Services & Support",
                "#hs_cos_wrapper_content_bucket-module-13",
            ),
            *(faq_place(*f) for f in FAQ),
            P("glossary", "EncyloCISO: glossary of terms", "module_17170541173493"),
            P(
                "glossary_terms",
                "The glossary's terms (CISO, CJA, CDPO, vCISO, …)",
                "widget_1716932004822",
            ),
            P(
                "benefits",
                "Benefits of Choosing Enveedo: platform report and free risk assessment",
                "module_17169377610588",
            ),
        ),
    ),
    "/trust-center": PageSpec(
        "trust",
        "/es/trust-center",
        (
            P("hero", "Trust Center: Security at the Core of Trust", "module_17171691078105"),
            P("controls", "Our Security Controls", "module_17389560607146"),
            P(
                "network_security",
                "Network and application security: scans, pentest, WAF, IDS, TLS",
                "module_17393787634927",
            ),
            P("soc2", "SOC 2 Compliance: the SOC 2 Type II report", "module_17393868932213"),
            S("soc2_form", "Request the SOC 2 Type II report (form)", SOC2_FORM, row=False),
            *form_places("soc2", SOC2_FORM),
        ),
        forms=("soc2",),
    ),
    "/webinars-and-ebooks": PageSpec(
        "library",
        None,
        (
            P("header", "Webinars and eBooks", "module_1716931732754"),
            P("intro", "We love telling good stories", "widget_1723579818814"),
            S(
                "library",
                "The eBooks and webinars (gated, open in a new tab)",
                "#hs_cos_wrapper_widget_1723575675202",
                row=False,
            ),
            P("benefits", "Benefits of Choosing Enveedo", "module_17169377610588"),
        ),
    ),
    "/privacy-policy": PageSpec("legal", "/es/privacy-policy", LEGAL),
    "/terms-of-service": PageSpec("legal", "/es/terms-of-service", LEGAL),
    "/sub-processors": PageSpec("legal", "/es/sub-processors", LEGAL),
    "/responsible-disclosure-policy": PageSpec("legal", "/es/responsible-disclosure-policy", LEGAL),
}

HEADER = (
    S(
        "menu",
        "The top menu: Platform, Security Performance OS, Partners, Resources, Contact",
        "header nav.nav",
        row=False,
    ),
    S(
        "language_switcher",
        "The site's English/Español switcher",
        ".hs-language-switcher",
        row=False,
    ),
)
FOOTER = (
    S("footer", "The footer: links, newsletter, Trust Center, legal", "footer#footer", row=False),
)


# ─── Reading a page ──────────────────────────────────────────────────────────

_VIS = """const vis = (e) => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e);
  return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
const txt = (e) => (e.innerText || '').replace(/[ \\t]+/g, ' ').replace(/\\n\\s*\\n+/g, '\\n').trim();"""

#: For each place: the first candidate that matches exactly one element, how
#: many are laid out, its row, its words.
_READ = (
    """(rows) => {"""
    + _VIS
    + """
  const out = [];
  for (const [key, cands, wantRow] of rows) {
    // The first candidate that is one laid-out element; else the first that
    // is one element; else the first that matched several.
    let got = null;
    for (const sel of cands) {
      let all = [];
      try { all = [...document.querySelectorAll(sel)]; } catch (e) { continue; }
      if (all.length === 1 && vis(all[0])) { got = {sel, el: all[0]}; break; }
      if (all.length === 1 && !(got && got.el)) got = {sel, el: all[0]};
      if (all.length > 1 && !got) got = {sel, el: null, count: all.length};
    }
    if (!got || !got.el) { out.push({key, selector: got ? got.sel : '', count: got ? got.count : 0, visible: 0}); continue; }
    let row = '';
    if (wantRow) {
      let x = got.el;
      while (x && x !== document.body) {
        const m = [...x.classList].map(c => c.match(/^content_bucket-row-(\\d+)-/)).find(Boolean);
        if (m) { row = m[1]; break; }
        x = x.parentElement;
      }
    }
    out.push({key, selector: got.sel, count: 1, visible: vis(got.el) ? 1 : 0, row,
              text: txt(got.el).slice(0, 4000)});
  }
  return out;
}"""
)

_COUNT = """(sel) => { try { return document.querySelectorAll(sel).length; } catch (e) { return -1; } }"""

_INFO = (
    """() => {"""
    + _VIS
    + """
  const main = document.querySelector('#main-content') || document.body;
  const meta = document.querySelector('meta[name="description"], meta[property="og:description"]');
  const alt = {};
  for (const l of document.querySelectorAll('link[rel=alternate][hreflang]')) alt[l.hreflang] = l.href;
  // A link's card: the first line of the nearest box around it that says more.
  const card = (a) => {
    const own = txt(a);
    let x = a.parentElement;
    while (x && x !== main) {
      const t = txt(x);
      if (t && t !== own) return t.split('\\n')[0].replace(/^[\\u2b50\\s]+/, '').slice(0, 160);
      x = x.parentElement;
    }
    return '';
  };
  const links = [...main.querySelectorAll('a[href]')].map(a => ({label: txt(a) || a.title || '', href: a.href, card: card(a)}))
    .filter(l => l.href && !l.href.startsWith('javascript'));
  const heads = [...main.querySelectorAll('h1,h2,h3')].filter(vis).map(h => txt(h)).filter(Boolean);
  return {title: document.title, lang: document.documentElement.lang, description: meta ? meta.content : '',
          alternates: alt, links, headings: heads, text: txt(main)};
}"""
)

_CLICK = """(sel) => { const el = document.querySelector(sel); if (!el) return false; el.click(); return true; }"""


def cache_file(key: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    return CACHE / (hashlib.sha1(key.encode()).hexdigest()[:16] + ".json")


def _goto(page: Any, url: str) -> int:
    """Load ``url`` and scroll through it once, so lazy parts (the forms, the
    scheduler's frame, the logos) lay out."""
    last: Exception | None = None
    status = 0
    for attempt in range(3):
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=90_000)
            status = resp.status if resp is not None else 0
            break
        except Exception as exc:  # retried, then raised
            last = exc
            print(f"  retry {attempt + 1} {url}: {str(exc).splitlines()[0][:120]}", flush=True)
            time.sleep(8 * (attempt + 1))
    else:
        raise RuntimeError(f"{url}: {last}")
    if status >= 400:
        return status
    with contextlib.suppress(Exception):
        page.wait_for_load_state("load", timeout=30_000)
    height = page.evaluate("document.body.scrollHeight")
    y = 0
    while y < height:
        page.evaluate(f"scrollTo(0, {y})")
        page.wait_for_timeout(120)
        y += 700
        height = page.evaluate("document.body.scrollHeight")
    page.wait_for_timeout(2500)
    page.evaluate("scrollTo(0, 0)")
    page.wait_for_timeout(500)
    return status


def _rows(places: tuple[Place, ...]) -> list[list[Any]]:
    return [[p.key, list(p.ids), p.row] for p in places]


def render(page: Any, path: str, spec: PageSpec) -> dict[str, Any]:
    status = _goto(page, SITE + path)
    if status >= 400:
        return {"path": path, "status": status}
    plain = tuple(p for p in spec.places if p.reveal is None)
    reads = page.evaluate(_READ, _rows(plain + HEADER + FOOTER))
    # The reveals, in order: each opened by its own control (a tab, an
    # accordion, the toggle), checked open, then read.
    revealed: list[dict[str, Any]] = []
    for p in spec.places:
        if p.reveal is None:
            continue
        click, opened = p.reveal
        result: dict[str, Any] = {"click_count": page.evaluate(_COUNT, click)}
        if page.evaluate(_COUNT, opened) != 1:
            page.evaluate(_CLICK, click)
            page.wait_for_timeout(900)
        result["open"] = page.evaluate(_COUNT, opened)
        result |= page.evaluate(_READ, _rows((p,)))[0]
        revealed.append(result)
    return {
        "path": path,
        "status": status,
        "reads": reads + revealed,
        "info": page.evaluate(_INFO),
    }


def crawl(offline: bool, refresh: bool) -> dict[str, dict[str, Any]]:
    todo: list[tuple[str, PageSpec]] = []
    for en, spec in PAGES.items():
        todo.append((en, spec))
        if spec.es:
            todo.append((spec.es, spec))
    rendered: dict[str, dict[str, Any]] = {}
    missing: list[tuple[str, PageSpec]] = []
    for path, spec in todo:
        f = cache_file(SITE + path + "#rendered")
        if f.exists() and not refresh:
            rendered[path] = json.loads(f.read_text(encoding="utf-8"))
        else:
            missing.append((path, spec))
    if missing and offline:
        raise SystemExit(f"not in the cache: {[p for p, _ in missing]}; run without --offline")
    if missing:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
            page = ctx.new_page()
            for i, (path, spec) in enumerate(missing):
                if i:
                    time.sleep(PAUSE_S)
                t0 = time.time()
                try:
                    got = render(page, path, spec)
                except RuntimeError as exc:
                    print(f"FAILED {exc}", flush=True)
                    continue
                if got.get("status", 200) >= 400:
                    print(f"{path}: HTTP {got['status']}: left out", flush=True)
                else:
                    off = [
                        r["key"]
                        for r in got["reads"]
                        if r.get("count") != 1 or (r.get("visible") != 1) or r.get("open") == 0
                    ]
                    print(
                        f"{path}: {len(got['reads'])} places in {time.time() - t0:.1f}s; off: {off}",
                        flush=True,
                    )
                cache_file(SITE + path + "#rendered").write_text(
                    json.dumps(got, ensure_ascii=False), encoding="utf-8"
                )
                rendered[path] = got
            browser.close()
    return rendered


# ─── Records ────────────────────────────────────────────────────────────────


def clean(text: str) -> str:
    return re.sub(r"\n{2,}", "\n", re.sub(r"[ \t]+", " ", text)).strip()


def _place_record(p: Place, r: dict[str, Any] | None, path: str) -> dict[str, Any] | None:
    """The catalogue's entry for ``p`` as the page read it, or ``None`` (and a
    line printed) when it did not match exactly one laid-out element."""
    if r is None or r.get("count") != 1:
        print(f"  dropped {path} {p.key}: {r.get('count') if r else 'unread'} matches")
        return None
    if not p.optional and r.get("visible") != 1:
        print(f"  dropped {path} {p.key}: not laid out")
        return None
    if p.reveal is not None and r.get("open") != 1:
        print(f"  dropped {path} {p.key}: its control did not open it")
        return None
    row: dict[str, Any] = {"key": p.key, "selector": r["selector"], "label": p.label}
    if p.row and r.get("row"):
        fallback = ROW.format(r["row"])
        if fallback != r["selector"]:
            row["fallback"] = fallback
    if p.reveal is not None:
        row["reveal"] = {"click": p.reveal[0], "open": p.reveal[1]}
    if p.hidden:
        row["hidden"] = True
    if p.optional:
        row["optional"] = True
    return row


def twins() -> dict[str, str]:
    """English path → Spanish path, for every page that has one."""
    return {en: spec.es for en, spec in PAGES.items() if spec.es}


def anchors_record(rendered: dict[str, dict[str, Any]]) -> dict[str, Any]:
    pages: dict[str, Any] = {}
    header: list[dict[str, Any]] = []
    footer: list[dict[str, Any]] = []
    for en, spec in PAGES.items():
        for path, lang in ((en, "en"), (spec.es, "es")):
            if path is None:
                continue
            got = rendered.get(path)
            if not got or got.get("status", 200) >= 400:
                print(f"  no render for {path}: left out of the catalogue")
                continue
            reads = {r["key"]: r for r in got["reads"]}
            anchors = [a for p in spec.places if (a := _place_record(p, reads.get(p.key), path))]
            head = [a for p in HEADER if (a := _place_record(p, reads.get(p.key), path))]
            foot = [a for p in FOOTER if (a := _place_record(p, reads.get(p.key), path))]
            if path == "/":
                header, footer = head, foot
            twin = spec.es if lang == "en" else en
            pages[path] = {
                "kind": spec.kind,
                "lang": lang,
                "twin": twin if twin and twin in rendered else None,
                "title": got["info"]["title"],
                "header": len(head) == len(HEADER),
                "footer": len(foot) == len(FOOTER),
                "forms": list(spec.forms),
                "anchors": anchors,
            }
    return {
        "_meta": {
            "site": SITE,
            "header_px": HEADER_PX,
            "scroll_offset_px": SCROLL_OFFSET_PX,
            "viewport": "1440x900",
            "built": time.strftime("%Y-%m-%d"),
            "note": "Built by build.py. Every page is listed under its English and its Spanish path with the "
            "same keys; selectors may differ per path. Each selector matched exactly one laid-out element "
            "on the live page (optional ones: exactly one element). fallback is the section's row (index "
            "based). reveal: click `click` unless `open` already matches, then ring `selector`.",
        },
        "header": header,
        "footer": footer,
        "post": [],
        "pages": pages,
    }


def pages_record(
    rendered: dict[str, dict[str, Any]], anchors: dict[str, Any]
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path, entry in anchors["pages"].items():
        got = rendered[path]
        reads = {r["key"]: r for r in got["reads"]}
        sections = []
        for a in entry["anchors"]:
            if a.get("hidden"):
                continue
            text = clean(reads.get(a["key"], {}).get("text", ""))[:TEXT_CAP]
            sections.append({"key": a["key"], "heading": a["label"], "text": text})
        info = got["info"]
        out.append(
            {
                "path": path,
                "url": SITE + path,
                "lang": entry["lang"],
                "twin": entry["twin"],
                "kind": entry["kind"],
                "title": info["title"],
                "description": info["description"],
                "headings": info["headings"][:40],
                "sections": sections,
                "text": clean(info["text"])[:12000],
            }
        )
    return out


def site_record(rendered: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The calls to action that leave the site, read from the pages that link
    them, and what the hand-written knowledge needs as data."""
    library = rendered.get("/webinars-and-ebooks", {}).get("info", {}).get("links", [])
    gated = []
    seen: set[str] = set()
    for link in library:
        href = link["href"]
        if ("info.enveedo.com" in href or "youtube.com/watch" in href) and href not in seen:
            seen.add(href)
            title = re.sub(r"[\u200b\s]+", " ", link.get("card") or link["label"]).strip()
            gated.append({"label": title, "url": href.split("?hsLang")[0]})
    resources = rendered.get("/resources", {}).get("info", {}).get("links", [])
    pdf = next(
        (
            x["href"].split("?")[0]
            for x in resources
            if x["href"].lower().split("?")[0].endswith(".pdf")
        ),
        "",
    )
    return {
        "twins": twins(),
        "exits": {
            "scheduler": {
                "label": "Elis Martinez's HubSpot Meetings page",
                "url": "https://meetings.hubspot.com/elis-martinez",
            },
            "sign_in": {
                "label": "Enveedo sign-in (customers)",
                "url": "https://app.enveedo.com/login",
            },
            "blog": {"label": "Cyber Pulse blog", "url": "https://blog.enveedo.com/"},
            "blog_es": {
                "label": "Cyber Pulse blog (Spanish)",
                "url": "https://blog.enveedo.com/es",
            },
            "platform_pdf": {
                "label": "Enveedo's All-In-One Strategy Security Platform (PDF)",
                "url": pdf,
            },
        },
        "library": gated,
        "contact": {
            "phone": "+1 786 648 6418",
            "email": "info@enveedo.com",
            "privacy_email": "privacy@enveedo.com",
            "place": "Miami, Florida, United States",
            "address": "66 West Flagler St. Suite 900, Miami, FL 33130",
        },
    }


def write_site_map(anchors: dict[str, Any]) -> None:
    lines = [
        "# Site map: every page and its places",
        "",
        "Sources: generated by `build.py` from the live enveedo.com (English and Spanish).",
        "",
        "Paths are the English site's; every page with a Spanish version has the same slug under /es/ "
        "(except /book-a-demo-grl, whose Spanish twin is /es/book-a-demo-rsa). The keys are the same in "
        "both languages.",
        "",
    ]
    for path, entry in anchors["pages"].items():
        if entry["lang"] != "en":
            continue
        twin = f" (Spanish: {entry['twin']})" if entry["twin"] else " (no Spanish version)"
        lines.append(f"## {path} — {entry['kind']}{twin}")
        lines += [f"- {a['key']}: {a['label']}" for a in entry["anchors"] if not a.get("hidden")]
        lines.append("")
    (HERE / "L2" / "site-map.md").write_text("\n".join(lines), encoding="utf-8")


def dump(path: Path, data: Any, lines: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if lines and isinstance(data, list):
        body = "[\n" + ",\n".join(json.dumps(d, ensure_ascii=False) for d in data) + "\n]\n"
    else:
        body = json.dumps(data, ensure_ascii=False, indent=1) + "\n"
    path.write_text(body, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("command", choices=["crawl"])
    ap.add_argument("--offline", action="store_true", help="build from the cache only")
    ap.add_argument("--refresh", action="store_true", help="render every page again")
    args = ap.parse_args()
    rendered = crawl(args.offline, args.refresh)
    if "/" not in rendered or "/es/" not in rendered:
        raise SystemExit("the home pages did not render: nothing written")
    anchors = anchors_record(rendered)
    pages = pages_record(rendered, anchors)
    dump(L3 / "anchors.json", anchors)
    dump(L3 / "pages.json", pages, lines=True)
    dump(L3 / "site.json", site_record(rendered))
    write_site_map(anchors)
    n = sum(len(p["anchors"]) for p in anchors["pages"].values())
    print(f"wrote {L3}: {len(anchors['pages'])} pages, {n} places")


if __name__ == "__main__":
    sys.exit(main())
