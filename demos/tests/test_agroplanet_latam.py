"""Javier's Spanish is Latin America's, not Spain's, and he says "tú".

Agroplanet's visitors are farmers and contractors in Chile. The accent is the
speech tier's reference clip; the words are this brain's. Every Spanish line
the brain writes itself — the greetings, the lines for a page move, the done
and holding lines, the landing lines and the prices — carries no word or form
only Spain uses, says "carro" and "repuesto", never "cesta" or "recambio", and
addresses the visitor as "tú", as the store does, never "usted". Prices are
said in Spanish number words, and the field's measures ("15W40", "12V") as the
field says them. In Spanish the voice is handed "bidéo" for "video", and the
model only ever sees "video".

What the model writes is a property of the prompt and the model; the prompt's
rules are checked here.

Run: ``cd demos && uv run pytest tests/test_agroplanet_latam.py``
"""

from __future__ import annotations

import re

import pytest
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedOpenAI, input_texts, reply

from ._harness import check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.agroplanet import brain as ag  # noqa: E402

#: Words and forms only Spain uses, as they would show in what he says.
_SPAIN = {
    "vídeo": r"\bvídeos?\b",
    "vale": r"\bvale\b",
    "vosotros": r"\bvosotr[oa]s\b",
    "os": r"\bos\b",
    # "dieciséis" and "veintiséis" are numbers, not verbs.
    "vosotros verb (-áis/-éis)": r"\b(?!(?:dieci|veinti)séis\b)\w{2,}(?:áis|éis)\b",
    "ordenador": r"\bordenador(?:es)?\b",
    "móvil": r"\bmóvil(?:es)?\b",
    "coger": r"\bco(?:ger|ge|jo|gemos)\b",
    "rellenar": r"\brellen(?:ar|ad\w*|ando|amos)\b|\b(?:te |lo |la )rellen\w*",
    "te viene bien": r"\bte viene bien\b",
    "perdona": r"\bperdona\b",
    "enseñar (show)": r"\bte (?:lo |la )?enseñ\w*|\benseñárte\w*",
    "he + participle": r"\bhe (?:abierto|cerrado|puesto|completado|marcado|añadido|aplicado)\b",
    "cesta": r"\bcestas?\b",
    "recambio": r"\brecambios?\b",
    "portes": r"\bportes\b",
}
#: The visitor addressed as "usted": the store, and Javier, say "tú".
_USTED = (
    # "Te lo abro" is "tú"; "lo abro" alone is "usted".
    r"\busted(?:es)?\b|(?<!te )\b(?:le|lo) (?:ayudo|muestro|abro|cuento|reviso)\b"
    r"|\b(?:necesita|quiere|tiene|busca)\b\?"
)


def spain_words(text: str) -> list[str]:
    return [name for name, rx in _SPAIN.items() if re.search(rx, text, re.IGNORECASE)]


def test_the_checks_catch_spain_and_usted() -> None:
    assert spain_words("Vale, te lo enseño en el vídeo. Lo he añadido a la cesta.") == [
        "vídeo",
        "vale",
        "enseñar (show)",
        "he + participle",
        "cesta",
    ]
    assert spain_words("Dieciséis litros.") == []
    assert spain_words("¿Buscáis un recambio para el tractor?") == [
        "vosotros verb (-áis/-éis)",
        "recambio",
    ]
    assert re.search(_USTED, "¿En qué le ayudo? ¿Qué busca?")
    assert not re.search(_USTED, "¿En qué te ayudo? ¿Qué buscas?")


def _his_spanish_lines() -> list[str]:
    """Every Spanish line the brain writes itself, rather than the model."""
    lines = [
        ag.TOGGLE_CONFIRM["es"],
        ag._INTRO["es"],
        ag._GREETING["es"],
        *(opener["es"] for _, opener in ag._OPENERS),
        *(line["es"] for line in ag._LANDED.values()),
        *(line["es"] for line in ag._DONE.values()),
        *(line for lines in ag._HOLDING.values() for line in lines["es"]),
    ]
    pages = [
        "/",
        "/categoria/baterias/AG02",
        "/categoria/lubricantes/AG100",
        "/categoria/repuestos_de_tractor/AG10",
        "/busqueda/aceite%20hidraulico",
        "/producto/aceite_lubritek_utf_semisintetico_19l/1173221",
        "/carro",
        "/cotizacion",
        "/nuestras-tiendas",
        "/politica-despacho",
    ]
    lines += [ag.greeting(path, "es") for path in pages]
    lines += [ag.pesos_said(n, "es") for n in (1, 21, 100, 121000, 599990, 1_000_000, 2_499_990)]
    listing = ag.ListingShown.model_validate(
        {
            "path": "/categoria/lubricantes/AG100",
            "title": "Lubricantes",
            "count": 12,
            "items": [
                {
                    "path": "/producto/x/1",
                    "name": "Aceite LUBRITEK UTF Semisintético 19L",
                    "price": 80000,
                }
            ],
        }
    )
    lines.append(ag.listing_line(listing, "es", ["LUBRITEK", "15W40"]))
    for over in ({"price": 80000}, {"price_hidden": True}, {"stock": "lowStock"}):
        product = ag.ProductShown.model_validate(
            {"path": "/producto/x/1", "name": "Batería 12V 100Ah Heavy Duty"} | over
        )
        lines.append(ag.product_line(product, "es"))
    return lines


@pytest.mark.parametrize("line", _his_spanish_lines())
def test_his_own_spanish_lines_are_latin_american_and_say_tu(line: str) -> None:
    assert spain_words(line) == [], line
    assert not re.search(_USTED, line, re.IGNORECASE), line


def test_the_greeting_says_tu_and_the_cart_is_the_carro() -> None:
    assert ag._INTRO["es"] == "Hola, soy Javier, de Agroplanet."
    assert any(re.search(r"\bte\b|\btu\b|\bnecesitas\b", o["es"]) for _, o in ag._OPENERS)
    cart_lines = [ag._LANDED[k]["es"] for k in ("cart_add", "cart_show", "cart_close")]
    assert all("carro" in line for line in cart_lines), cart_lines
    assert "cotización" in ag._LANDED["quote"]["es"]


@pytest.mark.parametrize(
    ("amount", "said"),
    [
        (599990, "quinientos noventa y nueve mil novecientos noventa pesos"),
        (1_299_990, "un millón doscientos noventa y nueve mil novecientos noventa pesos"),
        (21_000, "veintiún mil pesos"),
        (2_000_000, "dos millones de pesos"),
        (100, "cien pesos"),
    ],
)
def test_prices_are_spanish_number_words(amount: int, said: str) -> None:
    assert ag.pesos_said(amount, "es") == said
    assert not re.search(r"\d", ag.pesos_said(amount, "es"))


def test_a_landing_line_says_the_price_in_words_never_digits() -> None:
    product = ag.ProductShown.model_validate(
        {
            "path": "/producto/x/1",
            "name": "Aceite LUBRITEK UTF Semisintético 19L",
            "price": 80000,
        }
    )
    line = ag.product_line(product, "es")
    assert line == "Aquí está el producto: Aceite LUBRITEK UTF Semisintético, a ochenta mil pesos."


@pytest.mark.parametrize(
    ("written", "for_voice"),
    [
        ("Te muestro un video del arado.", "Te muestro un bidéo del arado."),
        ("Mira los videos de AGROPLANET.", "Mira los bidéos de Agroplanet."),
        ("Un vídeo y una videollamada.", "Un bidéo y una videollamada."),
    ],
)
def test_video_is_respelled_for_the_voice_and_back(written: str, for_voice: str) -> None:
    assert ag.for_the_voice(written) == for_voice
    assert ag.from_the_voice(for_voice) == written.replace("vídeo", "video").replace(
        "AGROPLANET", "Agroplanet"
    )


@pytest.mark.parametrize(
    ("written", "said"),
    [
        ("Aceite 15W40.", "Aceite quince W cuarenta."),
        ("Aceite 10W-30.", "Aceite diez W treinta."),
        ("Batería de 12V.", "Batería de doce volts."),
        ("Batería de 100Ah.", "Batería de cien amperes hora."),
        ("Tractor de 50 HP.", "Tractor de cincuenta hache pe."),
        ("Cuesta ochenta mil pesos.", "Cuesta ochenta mil pesos."),
    ],
)
def test_the_fields_measures_are_said_in_spanish_words(written: str, said: str) -> None:
    assert ag.for_the_voice(written) == said


async def test_the_voice_says_bideo_and_the_model_reads_video() -> None:
    llm = ScriptedOpenAI(
        {
            "¿Tienen video de la rotofresa?": reply(
                "{show: CATEGORÍAS} Hay un video que la muestra."
            ),
            "¿Y el precio?": reply("Te lo reviso."),
        }
    )
    async with demo("agroplanet", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("¿Tienen video de la rotofresa?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert "Hay un bidéo que la muestra." in turn.text, turn.text
        cues = [c["payload"] for c in rig.driver.ui_commands if c.get("command") == "stage_cue"]
        assert cues and cues[0]["at"].startswith("Hay un bidéo"), cues
        await rig.driver.user_says("¿Y el precio?")
        context = input_texts(llm.captured_inputs[-1])
        assert "Hay un video que la muestra." in context and "bidéo" not in context, context


def test_the_prompt_asks_for_latin_american_spanish_and_tu() -> None:
    prompt = ag._prompt(ag.kb.KNOWLEDGE)
    for rule in (
        "neutral Latin American Spanish",
        'Address the visitor as "tú"',
        'never "usted"',
        'never "vosotros"',
        'never "vídeo"',
        '"celular", never "móvil"',
        '"computador", never "ordenador"',
        '"repuesto" for a spare part, never "recambio"',
        '"está bien" or "perfecto", never "vale"',
        "the simple past",
        'the "carro", never "cesta"',
        '"despacho" for delivery',
        '"retiro en tienda"',
        '"cotización" and "cotizar"',
        "Write every number, price and measure as spoken words.",
        '"15W40" is "quince W cuarenta"',
    ):
        assert rule in prompt, rule


def test_the_prompts_own_spanish_examples_are_latin_american() -> None:
    prompt = ag._prompt(ag.kb.KNOWLEDGE).split("# AGROPLANET")[0]
    said = re.findall(r'"([^"]*[áéíóúñ¿][^"]*)"', prompt)
    assert len(said) > 10
    for line in said:
        # A word or two quoted is a word named, and Spain's are named to forbid them.
        if line.startswith(("never ", "not ")) or len(line.split()) <= 2:
            continue
        assert not re.search(_USTED, line, re.IGNORECASE), line
        assert spain_words(line) == [], line
