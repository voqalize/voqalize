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
        "id": "periodontal-disease",
        "title": "Periodontal Disease in Dogs and Cats: The Four Stages and What Each Needs",
        "service_id": "dental",
        "facts": [
            "The most common illness in adult pets; plaque hardens into tartar within days.",
            "Four stages: gingivitis (reversible), then early, moderate and advanced bone loss.",
            "Bad breath and chewing on one side are often the only signs.",
            "Treatment is a clean under anaesthesia with dental X-rays; most pets need one every 1 to 2 years.",
        ],
    },
    {
        "id": "brushing-teeth",
        "title": "How to Brush Your Pet's Teeth at Home: A Step-by-Step Guide",
        "service_id": "dental",
        "facts": [
            "Brush daily or every other day; plaque sets into tartar in about 48 hours.",
            "Use pet toothpaste only; human toothpaste is harmful when swallowed.",
            "Build up over two weeks: taste, finger, finger brush, then toothbrush on the outer surfaces.",
            "Brushing does not remove existing tartar; that needs a professional clean.",
        ],
    },
    {
        "id": "dental-abscess",
        "title": "Dental Abscess in Dogs and Cats: Swelling Under the Eye and Other Signs",
        "service_id": "dental",
        "facts": [
            "A swelling just below the eye is often a tooth-root abscess, not an eye problem.",
            "Caused by fractured or worn teeth or advanced gum disease; very painful.",
            "Facial swelling with fever or lethargy needs a vet the same day.",
            "Antibiotics alone do not cure it; the tooth is treated or extracted.",
        ],
    },
    {
        "id": "tooth-extraction",
        "title": "Tooth Extraction in Dogs and Cats: When Is It Necessary?",
        "service_id": "dental",
        "facts": [
            "Needed for loose teeth, fractures with exposed pulp, abscesses and painful lesions in cats.",
            "Done under anaesthesia with X-rays and a local block; most pets go home the same day.",
            "Soft food for a few days and no hard chews for two weeks.",
            "Pets eat normally, and often better, with fewer teeth.",
        ],
    },
    {
        "id": "rabbit-teeth",
        "title": "Dental Disease in Rabbits and Small Pets: Signs and Vet Treatment",
        "service_id": "exotic-pets",
        "facts": [
            "Rabbit teeth grow all their lives and are worn down by chewing hay.",
            "Signs: eating less, drooling, fewer droppings, weepy eyes.",
            "A rabbit that has not eaten for 12 hours is an emergency.",
            "Prevention: unlimited hay, fresh greens, and dental checks with an exotic-pet vet.",
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
