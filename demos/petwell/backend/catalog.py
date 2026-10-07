"""Canonical catalog for the Petwell "Appointment Desk" demo.

Petwell Veterinary Hospitals is a fictional chain of vet hospitals across nine
Indian cities, open 24x7, with everyday and specialty care and a vet-at-home
service. Every name, address and phone number here is invented.

Single source of truth for the brain's prompt and tool returns. The UI mirrors it
in ``frontend/src/catalog.ts`` for rendering — the ``id`` values here, and the
slot rule in :func:`slots_for`, MUST stay in sync with that file.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal, TypedDict

VisitType = Literal["clinic", "home"]


class Branch(TypedDict):
    id: str
    city: str
    name: str
    address: str
    # The branch that takes walk-in emergencies for its city.
    emergency: bool


class Service(TypedDict):
    id: str
    name: str
    group: str  # "Everyday care" | "Specialty care" | "At home"
    visit: VisitType
    # The words a caller might say, so the model maps "shots" → vaccination.
    hint: str


class Helpline(TypedDict):
    region: str
    phone: str
    cities: list[str]


# ── Cities, in the order the screen lists them ─────────────────────────────────
CITIES: list[str] = [
    "Goa",
    "Gurugram",
    "Hyderabad",
    "Jaipur",
    "Kolkata",
    "Lucknow",
    "Mumbai",
    "New Delhi",
    "Noida",
]

# Listed, but not taking appointments yet.
OPENING_SOON: set[str] = {"Kolkata"}

# The nearest Petwell cities for each part of the country — what the desk offers
# when a caller names a city of their own. The prompt states what Petwell has and
# where it is nearest; a call asked about Chennai was once offered "Hyderabad or
# Bengaluru", because the list it had read as an example rather than the whole.
NEAREST_BY_REGION: tuple[tuple[str, str], ...] = (
    ("South India", "Hyderabad"),
    ("West India", "Mumbai or Goa"),
    ("North India", "New Delhi, Gurugram, Noida, Jaipur or Lucknow"),
)

BRANCHES: list[Branch] = [
    {
        "id": "goa-porvorim",
        "city": "Goa",
        "name": "Petwell Porvorim",
        "address": "12 Palm Grove Arcade, Porvorim, Goa 403521",
        "emergency": True,
    },
    {
        "id": "goa-siolim",
        "city": "Goa",
        "name": "Petwell Siolim",
        "address": "3 Chapel Road, Siolim, Goa 403517",
        "emergency": False,
    },
    {
        "id": "ggn-palam-vihar",
        "city": "Gurugram",
        "name": "Petwell Palam Vihar",
        "address": "Plot 21, Palam Vihar Main Road, Sector 23, Gurugram 122017",
        "emergency": False,
    },
    {
        "id": "ggn-sushant-lok",
        "city": "Gurugram",
        "name": "Petwell Sushant Lok",
        "address": "B-14 Market Lane, Sushant Lok 2, Sector 55, Gurugram 122011",
        "emergency": True,
    },
    {
        "id": "hyd-jubilee-hills",
        "city": "Hyderabad",
        "name": "Petwell Jubilee Hills",
        "address": "8-2-293 Road No. 1, Jubilee Hills, Hyderabad 500033",
        "emergency": True,
    },
    {
        "id": "jpr-vaishali-nagar",
        "city": "Jaipur",
        "name": "Petwell Vaishali Nagar",
        "address": "C-41 Amrapali Marg, Vaishali Nagar, Jaipur 302021",
        "emergency": True,
    },
    {
        "id": "kol-ballygunge",
        "city": "Kolkata",
        "name": "Petwell Ballygunge",
        "address": "22 Lake View Road, Ballygunge, Kolkata 700029",
        "emergency": False,
    },
    {
        "id": "lko-gomti-nagar",
        "city": "Lucknow",
        "name": "Petwell Gomti Nagar",
        "address": "5/112 Vibhuti Khand, Gomti Nagar, Lucknow 226010",
        "emergency": True,
    },
    {
        "id": "mum-mahalaxmi",
        "city": "Mumbai",
        "name": "Petwell Mahalaxmi",
        "address": "Racecourse View, 4 Keshavrao Khadye Marg, Mahalaxmi, Mumbai 400034",
        "emergency": True,
    },
    {
        "id": "mum-powai",
        "city": "Mumbai",
        "name": "Petwell Powai",
        "address": "Shop 6, Lakeside Plaza, Central Avenue, Powai, Mumbai 400076",
        "emergency": False,
    },
    {
        "id": "mum-churchgate",
        "city": "Mumbai",
        "name": "Petwell Churchgate",
        "address": "Ground Floor, Oval Court, Veer Nariman Road, Churchgate, Mumbai 400020",
        "emergency": False,
    },
    {
        "id": "del-shanti-niketan",
        "city": "New Delhi",
        "name": "Petwell Shanti Niketan",
        "address": "A-9 Shanti Niketan Market, New Delhi 110021",
        "emergency": False,
    },
    {
        "id": "del-rajouri-garden",
        "city": "New Delhi",
        "name": "Petwell Rajouri Garden",
        "address": "J-7 Ring Road, Rajouri Garden, New Delhi 110027",
        "emergency": False,
    },
    {
        "id": "del-gk1",
        "city": "New Delhi",
        "name": "Petwell Greater Kailash",
        "address": "M-31 M Block Market, Greater Kailash 1, New Delhi 110048",
        "emergency": True,
    },
    {
        "id": "del-east-of-kailash",
        "city": "New Delhi",
        "name": "Petwell East of Kailash",
        "address": "First Floor, E-12 Community Centre, East of Kailash, New Delhi 110065",
        "emergency": False,
    },
    {
        "id": "noida-sec-50",
        "city": "Noida",
        "name": "Petwell Noida Sector 50",
        "address": "C-2/18 Central Market, Sector 50, Noida 201301",
        "emergency": True,
    },
]

SERVICES: list[Service] = [
    # Clinic — everyday care
    {
        "id": "general-consult",
        "name": "General consultation",
        "group": "Everyday care",
        "visit": "clinic",
        "hint": "check-up, not eating, vomiting, limping, lethargic, any general concern",
    },
    {
        "id": "vaccination",
        "name": "Vaccination",
        "group": "Everyday care",
        "visit": "clinic",
        "hint": "shots, rabies, puppy or kitten vaccines, boosters, deworming",
    },
    {
        "id": "grooming",
        "name": "Grooming",
        "group": "Everyday care",
        "visit": "clinic",
        "hint": "bath, haircut, nail trim, ear cleaning, coat care",
    },
    {
        "id": "dental",
        "name": "Dental care",
        "group": "Everyday care",
        "visit": "clinic",
        "hint": "bad breath, teeth cleaning, scaling, broken tooth",
    },
    {
        "id": "skin",
        "name": "Skin & allergy",
        "group": "Everyday care",
        "visit": "clinic",
        "hint": "itching, scratching, rashes, hair loss, ticks, fleas",
    },
    {
        "id": "diagnostics",
        "name": "Diagnostics (X-ray, ultrasound, lab)",
        "group": "Everyday care",
        "visit": "clinic",
        "hint": "blood test, X-ray, scan, ultrasound, CT, MRI",
    },
    # Clinic — specialty care
    {
        "id": "cardiology",
        "name": "Cardiology",
        "group": "Specialty care",
        "visit": "clinic",
        "hint": "heart, murmur, breathing trouble, coughing",
    },
    {
        "id": "orthopaedics",
        "name": "Orthopaedics",
        "group": "Specialty care",
        "visit": "clinic",
        "hint": "bones, joints, fracture, hip, knee, ligament",
    },
    {
        "id": "oncology",
        "name": "Cancer care",
        "group": "Specialty care",
        "visit": "clinic",
        "hint": "lump, tumour, cancer, chemotherapy",
    },
    {
        "id": "neurology",
        "name": "Neurology",
        "group": "Specialty care",
        "visit": "clinic",
        "hint": "seizures history, spine, paralysis, wobbly walking",
    },
    {
        "id": "eye-care",
        "name": "Eye care",
        "group": "Specialty care",
        "visit": "clinic",
        "hint": "eyes, cloudy eye, discharge, cataract",
    },
    {
        "id": "exotic-pets",
        "name": "Exotic pets",
        "group": "Specialty care",
        "visit": "clinic",
        "hint": "birds, parrots, rabbits, turtles, reptiles, hamsters",
    },
    {
        "id": "physiotherapy",
        "name": "Physiotherapy & rehab",
        "group": "Specialty care",
        "visit": "clinic",
        "hint": "after surgery recovery, hydrotherapy, mobility",
    },
    # Vet at home
    {
        "id": "home-vaccination",
        "name": "Vaccination at home",
        "group": "At home",
        "visit": "home",
        "hint": "shots at home",
    },
    {
        "id": "home-consult",
        "name": "Minor illness or injury consult",
        "group": "At home",
        "visit": "home",
        "hint": "vet visit at home for a small problem",
    },
    {
        "id": "home-blood-sample",
        "name": "Blood sample collection",
        "group": "At home",
        "visit": "home",
        "hint": "blood test at home",
    },
    {
        "id": "home-physio",
        "name": "Physiotherapy at home",
        "group": "At home",
        "visit": "home",
        "hint": "rehab session at home",
    },
]

HELPLINES: list[Helpline] = [
    {
        "region": "North India",
        "phone": "+91 90000 01111",
        "cities": ["Gurugram", "Jaipur", "Lucknow", "New Delhi", "Noida"],
    },
    {"region": "Mumbai & Goa", "phone": "+91 90000 02222", "cities": ["Mumbai", "Goa"]},
    {
        "region": "Hyderabad & Kolkata",
        "phone": "+91 90000 03333",
        "cities": ["Hyderabad", "Kolkata"],
    },
]

# ── Slots ─────────────────────────────────────────────────────────────────────
#
# A clinic books every 30 minutes from 09:00 to 19:30; a home visit every hour
# from 10:00 to 17:00. Some are already taken — decided by a small, stable hash so
# a demo run repeats and the UI can compute the same answer on its own.

CLINIC_TIMES: list[str] = [f"{h:02d}:{m:02d}" for h in range(9, 20) for m in (0, 30)]
HOME_TIMES: list[str] = [f"{h:02d}:00" for h in range(10, 18)]

BOOKING_DAYS = 7


def _taken(key: str) -> bool:
    """Mirrors ``isTaken`` in ``frontend/src/catalog.ts`` — keep the two identical."""
    h = 0x811C9DC5  # 32-bit FNV-1a: spreads neighbouring times, so no morning is all taken
    for c in key.encode():
        h = ((h ^ c) * 0x01000193) & 0xFFFFFFFF
    return h % 10 < 3


def slots_for(branch_id: str, date: str, visit: VisitType) -> list[str]:
    """The free times at ``branch_id`` on ISO ``date`` for this kind of visit."""
    times = HOME_TIMES if visit == "home" else CLINIC_TIMES
    return [t for t in times if not _taken(f"{branch_id}|{date}|{t}")]


def booking_dates(today: dt.date) -> list[dt.date]:
    """The days the screen offers: today and the six after it."""
    return [today + dt.timedelta(days=i) for i in range(BOOKING_DAYS)]


# ── Lookups ───────────────────────────────────────────────────────────────────


def get_branch(branch_id: str) -> Branch | None:
    return next((b for b in BRANCHES if b["id"] == branch_id), None)


def get_service(service_id: str) -> Service | None:
    return next((s for s in SERVICES if s["id"] == service_id), None)


def branches_in(city: str) -> list[Branch]:
    return [b for b in BRANCHES if b["city"] == city]


def as_city(name: str) -> str | None:
    """The canonical spelling of a city the model named, case-insensitively."""
    wanted = name.strip().lower().replace("delhi ncr", "new delhi")
    if wanted == "delhi":
        wanted = "new delhi"
    if wanted in ("gurgaon",):
        wanted = "gurugram"
    return next((c for c in CITIES if c.lower() == wanted), None)


def helpline_for(city: str) -> Helpline:
    return next((h for h in HELPLINES if city in h["cities"]), HELPLINES[0])


# ── Prompt ────────────────────────────────────────────────────────────────────


def catalog_for_prompt() -> str:
    lines: list[str] = [
        "BRANCHES — this is every Petwell hospital: nine cities, and these branches in "
        "them (city → branch [id] — address):"
    ]
    for city in CITIES:
        soon = " (OPENING SOON — not taking appointments yet)" if city in OPENING_SOON else ""
        lines.append(f"- {city}{soon}:")
        for b in branches_in(city):
            er = " · 24x7 emergency" if b["emergency"] else ""
            lines.append(f"    - {b['name']} [{b['id']}] — {b['address']}{er}")
    lines.append(
        "When a caller names a city of their own, offer the nearest of these Petwell cities: "
        + "; ".join(f"{region} → {cities}" for region, cities in NEAREST_BY_REGION)
        + ". Every city you name is one from the list above."
    )
    lines.append("")
    lines.append("SERVICES (name [id] — what callers say):")
    for group in ("Everyday care", "Specialty care", "At home"):
        visit = "home visit only" if group == "At home" else "clinic visit"
        lines.append(f"- {group} ({visit}):")
        for s in SERVICES:
            if s["group"] == group:
                lines.append(f"    - {s['name']} [{s['id']}] — {s['hint']}")
    lines.append("")
    lines.append("EMERGENCY HELPLINES:")
    for h in HELPLINES:
        lines.append(f"- {h['region']} ({', '.join(h['cities'])}): {h['phone']}")
    return "\n".join(lines)
