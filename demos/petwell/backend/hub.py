"""The Petwell Health Hub, as the assistant knows it.

The page renders the full articles from ``frontend/src/hub.ts``; the brain carries
only each article's id, title, the service its call to action books, and the
handful of facts the assistant may say aloud while the article is on screen. The
ids here MUST match that file.

General pet-health information written for this demo — not veterinary advice,
and the prompt says so.
"""

from __future__ import annotations

from typing import TypedDict


class HubArticle(TypedDict):
    id: str
    title: str
    service_id: str
    facts: list[str]


ARTICLES: list[HubArticle] = [
    {
        "id": "parvovirus",
        "title": "Parvovirus in Puppies: Signs, Treatment and the Vaccine Schedule",
        "service_id": "vaccination",
        "facts": [
            "Spreads through infected stool and survives on soil and floors for months.",
            "Signs: repeated vomiting, bloody diarrhoea, weakness, refusing food — an emergency in a puppy.",
            "No drug kills the virus; treatment is fluids, anti-nausea medicine and isolation.",
            "Vaccine doses at 6 to 8, 10 to 12 and 14 to 16 weeks, then a yearly booster.",
        ],
    },
    {
        "id": "diwali-safety",
        "title": "Diwali with Pets: Firecrackers, Sweets and Smoke",
        "service_id": "general-consult",
        "facts": [
            "Set up a quiet inner room; walk dogs on a lead before the noise starts.",
            "Chocolate, raisins, xylitol and rich mithai are risky for pets.",
            "Only give a calming medicine your vet prescribed for that pet.",
        ],
    },
    {
        "id": "cat-urinary",
        "title": "Why Is My Cat Straining to Pee?",
        "service_id": "general-consult",
        "facts": [
            "Often cystitis or crystals, linked to stress and low water intake.",
            "A male cat straining with little or no urine is an emergency — within hours.",
            "More water, clean litter boxes and a calm routine help prevent flare-ups.",
        ],
    },
    {
        "id": "dental-care",
        "title": "Dental Disease in Dogs and Cats — and Why Cleaning Is Done Under Anaesthesia",
        "service_id": "dental",
        "facts": [
            "Bad breath and red gums are early signs of gum disease.",
            "Most disease is below the gum line, so a proper clean needs a monitored anaesthetic.",
            "Brush daily with pet toothpaste — never human toothpaste.",
        ],
    },
    {
        "id": "ticks-fleas",
        "title": "Ticks and Fleas After the Monsoon: A Prevention Plan",
        "service_id": "skin",
        "facts": [
            "Some ticks carry blood parasites that cause fever and low platelets.",
            "Use a vet-recommended preventive on schedule all year, and treat every pet at home.",
            "Fever, pale gums or bruising after a tick bite needs a blood test.",
        ],
    },
    {
        "id": "senior-checks",
        "title": "Senior Pet Health Checks: What to Test After Seven",
        "service_id": "diagnostics",
        "facts": [
            "From about seven years, a yearly check catches problems early.",
            "Covers blood count and chemistry, urine, thyroid, blood pressure and joints.",
            "Every six months for pets with an ongoing condition.",
        ],
    },
]


def get_article(article_id: str) -> HubArticle | None:
    return next((a for a in ARTICLES if a["id"] == article_id), None)


def hub_for_prompt() -> str:
    lines = ["HEALTH HUB ARTICLES (title [id] → service the article books — facts you may share):"]
    for a in ARTICLES:
        lines.append(f"- {a['title']} [{a['id']}] → {a['service_id']}")
        lines.extend(f"    · {fact}" for fact in a["facts"])
    return "\n".join(lines)
