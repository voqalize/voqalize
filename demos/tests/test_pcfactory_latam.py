"""Javier's Spanish is Latin America's, not Spain's, and he says "tú".

PC Factory's visitors are in Chile. The accent is the speech tier's reference
clip; the words are this brain's. Every Spanish line the brain writes itself —
the greetings, the lines for a page move, the done and holding lines, the
landing lines and the prices — carries no word or form only Spain uses, says
"carro" and "notebook", never "cesta" or "ordenador", and addresses the
visitor as "tú", as the store does, never "usted". Prices are said in Spanish
number words. In Spanish the voice is handed "bidéo" for "video", and the
model only ever sees "video".

What the model writes is a property of the prompt and the model; the prompt's
rules are checked here.

Run: ``cd demos && uv run pytest tests/test_pcfactory_latam.py``
"""

from __future__ import annotations

import re

import pytest
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedOpenAI, input_texts, reply

from ._harness import check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.pcfactory import brain as pc  # noqa: E402

#: Words and forms only Spain uses, as they would show in what he says.
_SPAIN = {
    "vídeo": r"\bvídeos?\b",
    "vale": r"\bvale\b",
    "vosotros": r"\bvosotr[oa]s\b",
    "os": r"\bos\b",
    # "dieciséis" and "veintiséis" are numbers, not verbs.
    "vosotros verb (-áis/-éis)": r"\b(?!(?:dieci|veinti)séis\b)\w{2,}(?:áis|éis)\b",
    "ordenador": r"\bordenador(?:es)?\b",
    "portátil": r"\bportátil(?:es)?\b",
    "móvil": r"\bmóvil(?:es)?\b",
    "auriculares": r"\bauriculares\b",
    "coger": r"\bco(?:ger|ge|jo|gemos)\b",
    "rellenar": r"\brellen(?:ar|ad\w*|ando|amos)\b|\b(?:te |lo |la )rellen\w*",
    "te viene bien": r"\bte viene bien\b",
    "perdona": r"\bperdona\b",
    "enseñar (show)": r"\bte (?:lo |la )?enseñ\w*|\benseñárte\w*",
    "he + participle": r"\bhe (?:abierto|cerrado|puesto|completado|marcado|añadido|aplicado)\b",
    "cesta": r"\bcestas?\b",
    "tarjeta gráfica as 'gráfica' alone": r"\buna gráfica\b",
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
    assert spain_words("Dieciséis gigas.") == []
    assert spain_words("¿Buscáis un ordenador portátil con auriculares?") == [
        "vosotros verb (-áis/-éis)",
        "ordenador",
        "portátil",
        "auriculares",
    ]
    assert re.search(_USTED, "¿En qué le ayudo? ¿Qué busca?")
    assert not re.search(_USTED, "¿En qué te ayudo? ¿Qué buscas?")


def _his_spanish_lines() -> list[str]:
    """Every Spanish line the brain writes itself, rather than the model."""
    lines = [
        pc.TOGGLE_CONFIRM["es"],
        pc._INTRO["es"],
        pc._GREETING["es"],
        *(opener["es"] for _, opener in pc._OPENERS),
        *(line["es"] for line in pc._LANDED.values()),
        *(line["es"] for line in pc._DONE.values()),
        *(line for lines in pc._HOLDING.values() for line in lines["es"]),
    ]
    pages = [
        "/",
        "/categoria/computadores-y-tablets/notebooks/notebooks",
        "/categoria/partes-y-piezas-componentes/tarjetas-graficas",
        "/busqueda-avanzada?search=monitor+27",
        "/producto/57233",
        "/carro",
        "/checkout/tipo-entrega",
        "/tiendas",
        "/centro-de-ayuda",
    ]
    lines += [pc.greeting(path, "es") for path in pages]
    lines += [pc.pesos_said(n, "es") for n in (1, 21, 100, 121000, 599990, 1_000_000, 2_499_990)]
    listing = pc.ListingShown.model_validate(
        {
            "path": "/categoria/x",
            "title": "Notebooks",
            "count": 12,
            "items": [{"path": "/producto/1", "name": "Notebook Lenovo IdeaPad", "price": 599990}],
        }
    )
    lines.append(pc.listing_line(listing, "es", ["Lenovo", "16GB"]))
    product = pc.ProductShown.model_validate(
        {"path": "/producto/1", "name": "Notebook HP 14-ep1330la", "price": 529990}
    )
    lines.append(pc.product_line(product, "es"))
    return lines


@pytest.mark.parametrize("line", _his_spanish_lines())
def test_his_own_spanish_lines_are_latin_american_and_say_tu(line: str) -> None:
    assert spain_words(line) == [], line
    assert not re.search(_USTED, line, re.IGNORECASE), line


def test_the_greeting_says_tu_and_the_cart_is_the_carro() -> None:
    assert "tu asesor" in pc._INTRO["es"]
    assert any(re.search(r"\bte\b|\btu\b|\bbuscas\b", o["es"]) for _, o in pc._OPENERS)
    cart_lines = [pc._LANDED[k]["es"] for k in ("cart_add", "cart_show", "cart_close")]
    assert all("carro" in line for line in cart_lines), cart_lines


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
    assert pc.pesos_said(amount, "es") == said
    assert not re.search(r"\d", pc.pesos_said(amount, "es"))


def test_a_landing_line_says_the_price_in_words_never_digits() -> None:
    product = pc.ProductShown.model_validate(
        {"path": "/producto/1", "name": "Notebook Lenovo IdeaPad Slim 3 15IRH8", "price": 599990}
    )
    line = pc.product_line(product, "es")
    assert line == (
        "Aquí está el Notebook Lenovo IdeaPad Slim 3, a quinientos noventa y nueve mil "
        "novecientos noventa pesos con transferencia."
    )


@pytest.mark.parametrize(
    ("written", "for_voice"),
    [
        ("Te muestro un video del notebook.", "Te muestro un bidéo del notebook."),
        ("Mira los videos de pcFactory.", "Mira los bidéos de PC Factory."),
        ("Un vídeo y una videollamada.", "Un bidéo y una videollamada."),
    ],
)
def test_video_is_respelled_for_the_voice_and_back(written: str, for_voice: str) -> None:
    assert pc.for_the_voice(written) == for_voice
    assert pc.from_the_voice(for_voice) == written.replace("vídeo", "video").replace(
        "pcFactory", "PC Factory"
    )


async def test_the_voice_says_bideo_and_the_model_reads_video() -> None:
    llm = ScriptedOpenAI(
        {
            "¿Tiene video el notebook?": reply(
                "{show: Te recomendamos} Hay un video que lo muestra."
            ),
            "¿Y el precio?": reply("Te lo reviso."),
        }
    )
    async with demo("pcfactory", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("¿Tiene video el notebook?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert "Hay un bidéo que lo muestra." in turn.text, turn.text
        cues = [c["payload"] for c in rig.driver.ui_commands if c.get("command") == "stage_cue"]
        assert cues and cues[0]["at"].startswith("Hay un bidéo"), cues
        await rig.driver.user_says("¿Y el precio?")
        context = input_texts(llm.captured_inputs[-1])
        assert "Hay un video que lo muestra." in context and "bidéo" not in context, context


def test_the_prompt_asks_for_latin_american_spanish_and_tu() -> None:
    prompt = pc._prompt(pc.kb.KNOWLEDGE)
    for rule in (
        "neutral Latin American Spanish",
        'Address the visitor as "tú"',
        'never "usted"',
        'never "vosotros"',
        'never "vídeo"',
        '"celular", never "móvil"',
        '"computador", never "ordenador"',
        '"audífonos", never "auriculares"',
        '"notebook" for a laptop',
        '"está bien" or "perfecto", never "vale"',
        "the simple past",
        'the "carro" or "carro de compras", never "cesta"',
        '"despacho" for delivery',
        '"retiro en tienda"',
        '"cuotas sin interés"',
        "Write every number, price and measure as spoken words.",
    ):
        assert rule in prompt, rule


def test_the_prompts_own_spanish_examples_are_latin_american() -> None:
    prompt = pc._prompt(pc.kb.KNOWLEDGE).split("# PC FACTORY")[0]
    said = re.findall(r'"([^"]*[áéíóúñ¿][^"]*)"', prompt)
    assert len(said) > 10
    for line in said:
        # A word or two quoted is a word named, and Spain's are named to forbid them.
        if line.startswith(("never ", "not ")) or len(line.split()) <= 2:
            continue
        assert not re.search(_USTED, line, re.IGNORECASE), line
        assert spain_words(line) == [], line
