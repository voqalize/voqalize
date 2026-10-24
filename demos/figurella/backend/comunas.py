"""Which Figurella branch is nearest a visitor's comuna.

The site gives seven branches in Santiago, each with an address (``L3``'s
``branches.json``), and no map of who goes where. This is ours: for each comuna
of the Región Metropolitana, the branches nearest it, closest first, judged
from the branches' addresses and the city's main roads and Metro lines. It is a
suggestion Javier makes ("la que te queda más cerca probablemente es…"), never
a rule: she picks, and the evaluation can be at any branch.

- Huérfanos is in Santiago Centro, on Metro lines 1 and 2: the centre, the west
  and the south of the city.
- Costanera (Nueva Tajamar, by Costanera Center) and Colón (Av. Cristóbal
  Colón 4951) are both in Las Condes: Providencia, Las Condes, Ñuñoa.
- Vitacura (Juan XXIII 6370) and Tabancura (Av. Tabancura, toward Lo
  Barnechea) are in the north-east.
- Chicureo (Av. Chamisero, Colina) is for Colina, Chicureo and Lampa.
- Las Perdices (Av. Las Perdices, Peñalolén) is for the south-east.

Outside Santiago the site lists one more place, Montemar in Concón, only in
its WhatsApp button: a visitor from the Quinta Región is pointed there.
"""

from __future__ import annotations

import re

from .knowledge import fold

#: comuna (folded) → branch keys, nearest first.
NEAREST: dict[str, tuple[str, ...]] = {
    # Centre and west: Huérfanos.
    "santiago": ("huerfanos", "costanera"),
    "santiago centro": ("huerfanos", "costanera"),
    "estacion central": ("huerfanos",),
    "independencia": ("huerfanos",),
    "recoleta": ("huerfanos", "costanera"),
    "quinta normal": ("huerfanos",),
    "lo prado": ("huerfanos",),
    "cerro navia": ("huerfanos",),
    "pudahuel": ("huerfanos",),
    "renca": ("huerfanos",),
    "conchali": ("huerfanos",),
    "quilicura": ("huerfanos", "chicureo"),
    "maipu": ("huerfanos",),
    "cerrillos": ("huerfanos",),
    "padre hurtado": ("huerfanos",),
    "penaflor": ("huerfanos",),
    # South: Huérfanos (Metro line 2) or Las Perdices.
    "san miguel": ("huerfanos", "las_perdices"),
    "san joaquin": ("huerfanos", "las_perdices"),
    "pedro aguirre cerda": ("huerfanos",),
    "lo espejo": ("huerfanos",),
    "la cisterna": ("huerfanos", "las_perdices"),
    "el bosque": ("huerfanos", "las_perdices"),
    "san ramon": ("huerfanos", "las_perdices"),
    "la granja": ("las_perdices", "huerfanos"),
    "san bernardo": ("huerfanos",),
    "la pintana": ("las_perdices", "huerfanos"),
    # South-east: Las Perdices.
    "penalolen": ("las_perdices", "colon"),
    "la florida": ("las_perdices",),
    "macul": ("las_perdices", "costanera"),
    "puente alto": ("las_perdices",),
    "pirque": ("las_perdices",),
    "san jose de maipo": ("las_perdices",),
    "la reina": ("las_perdices", "colon"),
    # East: Costanera and Colón.
    "providencia": ("costanera", "huerfanos"),
    "nunoa": ("costanera", "las_perdices"),
    "las condes": ("colon", "costanera"),
    # North-east: Vitacura and Tabancura.
    "vitacura": ("vitacura", "tabancura"),
    "lo barnechea": ("tabancura", "vitacura"),
    "la dehesa": ("tabancura", "vitacura"),
    "huechuraba": ("vitacura", "chicureo"),
    # North: Chicureo.
    "colina": ("chicureo",),
    "chicureo": ("chicureo",),
    "lampa": ("chicureo",),
    "til til": ("chicureo",),
}

#: Other ways people name a comuna or a part of one.
ALIASES: dict[str, str] = {
    "centro": "santiago centro",
    "stgo": "santiago",
    "stgo centro": "santiago centro",
    "nunoa": "nunoa",
    "nuñoa": "nunoa",
    "penalolen": "penalolen",
    "providencia": "providencia",
    "el golf": "las condes",
    "apoquindo": "las condes",
    "san carlos de apoquindo": "las condes",
    "estoril": "las condes",
    "santa maria de manquehue": "vitacura",
    "piedra roja": "chicureo",
    "chamisero": "chicureo",
    "la florida": "la florida",
    "tobalaba": "providencia",
    "bellavista": "providencia",
    "lastarria": "santiago centro",
    "barrio italia": "providencia",
}

#: The Quinta Región, where only the WhatsApp button's Montemar (Concón) is near.
QUINTA = frozenset(
    {"concon", "vina del mar", "vina", "valparaiso", "quilpue", "villa alemana", "reñaca", "renaca"}
)


def nearest(comuna: str) -> tuple[str, ...] | None:
    """The branch keys nearest ``comuna``, closest first; ``("montemar",)`` for
    the Quinta Región; ``None`` when it is not a comuna we place."""
    said = " ".join(re.sub(r"[^a-z0-9ñ ]", " ", fold(comuna)).split())
    said = said.removeprefix("comuna de ").removeprefix("en ").strip()
    if not said:
        return None
    if said in QUINTA:
        return ("montemar",)
    key = ALIASES.get(said, said)
    if key in NEAREST:
        return NEAREST[key]
    # "Las Condes, cerca del Parque Arauco": the first comuna named in it.
    for name in sorted(NEAREST, key=len, reverse=True):
        if f" {name} " in f" {said} ":
            return NEAREST[name]
    for alias, name in ALIASES.items():
        if f" {alias} " in f" {said} ":
            return NEAREST.get(name)
    return None


__all__ = ["ALIASES", "NEAREST", "QUINTA", "nearest"]
