"""Javier's Spanish is Latin America's, not Spain's, and he says "tú".

Cannon Home's visitors are in Chile. The accent is the speech tier's reference
clip; the words are this brain's. Every Spanish line the brain writes itself —
the greetings and the lines for a page move — carries no word or form only
Spain uses, says "carro", never "cesta", and addresses the visitor as "tú", as
the store does, never "usted". In Spanish the voice is
handed "bidéo" for "video", and the model only ever sees "video".

What the model writes is a property of the prompt and the model; the prompt's
rules are checked here, and the live check is SendPotion's opt-in eval
(``test_sendpotion_latam.py``), whose rules this prompt carries.

Run: ``cd demos && uv run pytest tests/test_cannonhome_latam.py``
"""

from __future__ import annotations

import re

import pytest
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedOpenAI, input_texts, reply

from ._harness import check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.cannonhome import brain as ch  # noqa: E402

#: Words and forms only Spain uses, as they would show in what he says.
_SPAIN = {
    "vídeo": r"\bvídeos?\b",
    "vale": r"\bvale\b",
    "vosotros": r"\bvosotr[oa]s\b",
    "os": r"\bos\b",
    "vosotros verb (-áis/-éis)": r"\b\w{2,}(?:áis|éis)\b",
    "ordenador": r"\bordenador(?:es)?\b",
    "móvil": r"\bmóvil(?:es)?\b",
    "coger": r"\bco(?:ger|ge|jo|gemos)\b",
    # The verb, not "relleno", a duvet's filling.
    "rellenar": r"\brellen(?:ar|ad\w*|ando|amos)\b|\b(?:te |lo |la )rellen\w*",
    "te viene bien": r"\bte viene bien\b",
    "perdona": r"\bperdona\b",
    "enseñar (show)": r"\bte (?:lo |la )?enseñ\w*|\benseñárte\w*",
    "he + participle": r"\bhe (?:abierto|cerrado|rellenado|puesto|completado|marcado|añadido)\b",
    "cesta": r"\bcestas?\b",
    "edredón": r"\bedred[oó]n(?:es)?\b",
    "nórdico": r"\bn[oó]rdicos?\b",
    "envío a casa (portes)": r"\bportes\b",
}
#: The visitor addressed as "usted": the store, and Javier, say "tú".
_USTED = (
    r"\busted(?:es)?\b|\b(?:le|lo) (?:ayudo|muestro|abro|cuento)\b"
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
    assert spain_words("Te lo relleno ahora.") == ["rellenar"]
    assert spain_words("Un plumón con relleno de pluma.") == []
    assert spain_words("¿Buscáis un edredón nórdico?") == [
        "vosotros verb (-áis/-éis)",
        "edredón",
        "nórdico",
    ]
    assert re.search(_USTED, "¿En qué le ayudo? ¿Qué busca?")
    assert not re.search(_USTED, "¿En qué te ayudo? ¿Qué buscas?")


def _his_spanish_lines() -> list[str]:
    """Every Spanish line the brain writes itself, rather than the model."""
    lines = [
        ch.TOGGLE_CONFIRM["es"],
        ch._INTRO["es"],
        ch._GREETING["es"],
        *(opener["es"] for _, opener in ch._OPENERS),
        *(landed["es"] for landed in ch._LANDED.values()),
    ]
    pages = [
        "/",
        "/12-ropa-de-cama/20-sabanas",
        "/bano/toallas",
        "/12-ropa-de-cama/plumones",
        "/sabanas-king-300-hilos-blanco.html",
        "/checkout/cart",
        "/checkout",
    ]
    lines += [ch.greeting(path, "es") for path in pages]
    lines += [ch.pesos_said(n, "es") for n in (1, 21, 100, 121000, 231990, 1_000_000, 2_500_000)]
    return lines


@pytest.mark.parametrize("line", _his_spanish_lines())
def test_his_own_spanish_lines_are_latin_american_and_say_tu(line: str) -> None:
    assert spain_words(line) == [], line
    assert not re.search(_USTED, line, re.IGNORECASE), line


def test_the_greeting_says_tu_and_the_cart_is_the_carro() -> None:
    assert "tu guía" in ch._INTRO["es"]
    assert any(re.search(r"\bte\b|\btu\b|\bbuscas\b", o["es"]) for _, o in ch._OPENERS)
    cart_lines = [ch._LANDED[k]["es"] for k in ("cart_add", "cart_show", "cart_close")]
    assert all("carro" in line for line in cart_lines), cart_lines


@pytest.mark.parametrize(
    ("written", "for_voice"),
    [
        ("Te muestro un video de las sábanas.", "Te muestro un bidéo de las sábanas."),
        ("Mira los videos de CANNON HOME.", "Mira los bidéos de Cannon Home."),
        ("Un vídeo y una videollamada.", "Un bidéo y una videollamada."),
    ],
)
def test_video_is_respelled_for_the_voice_and_back(written: str, for_voice: str) -> None:
    assert ch.for_the_voice(written) == for_voice
    assert ch.from_the_voice(for_voice) == written.replace("vídeo", "video").replace(
        "CANNON HOME", "Cannon Home"
    )


def test_a_cue_anchor_follows_the_voice() -> None:
    """A cue's anchor is the spoken text after it: spelled as the voice says
    it, or the page never hears it."""
    sentence = "Un video muestra cómo se lavan las toallas de CANNON HOME."
    at = sentence[:40]
    heard = ch.for_the_voice(sentence)
    assert heard.startswith(ch._anchor_for_voice(at, "es")), (at, heard)
    assert ch._anchor_for_voice(at, "es").startswith("Un bidéo muestra")
    assert ch._anchor_for_voice("A video of CANNON HOME.", "en") == "A video of Cannon Home."


async def test_the_voice_says_bideo_and_the_model_reads_video() -> None:
    llm = ScriptedOpenAI(
        {
            "¿Cómo se lavan las toallas?": reply(
                "{page: /politicas-de-despacho} Hay un video que lo muestra."
            ),
            "¿Y las sábanas?": reply("Igual, con agua fría."),
        }
    )
    async with demo("cannonhome", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("¿Cómo se lavan las toallas?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert "Hay un bidéo que lo muestra." in turn.text, turn.text
        # The cue's anchor is what the voice says, so the page hears it.
        cues = [c["payload"] for c in rig.driver.ui_commands if c.get("command") == "stage_cue"]
        assert cues and cues[0]["at"].startswith("Hay un bidéo"), cues
        await rig.driver.user_says("¿Y las sábanas?")
        context = input_texts(llm.captured_inputs[-1])
        assert "Hay un video que lo muestra." in context and "bidéo" not in context, context


def test_the_prompt_asks_for_latin_american_spanish_and_tu() -> None:
    prompt = ch._prompt(ch.kb.KNOWLEDGE)
    for rule in (
        "neutral Latin American Spanish",
        'Address the visitor as "tú"',
        'never "usted"',
        'never "vosotros"',
        'never "vídeo"',
        '"celular", never "móvil"',
        '"está bien" or "perfecto", never "vale"',
        'not "te viene bien"',
        "the simple past",
        'the "carro" or "carro de compras", never "cesta"',
        '"despacho" for delivery',
        '"retiro en tienda"',
        '"plumón" for a duvet',
        '"cobertor", "cubrecama" and "quilt"',
        '"sábanas"',
        '"toalla"',
        '"cuotas sin interés"',
    ):
        assert rule in prompt, rule


def test_the_checkout_lines_say_tu_and_leave_the_rut_and_payment_to_the_visitor() -> None:
    """At the delivery form he says "completar", never "rellenar", and tells
    the visitor, as "tú", that the RUT and the payment are theirs."""
    opener = ch.greeting("/checkout", "es")
    assert "El RUT y el pago los completas tú." in opener
    lines = [opener, ch._LANDED["checkout"]["es"], ch._LANDED["checkout_fill"]["es"]]
    for line in lines:
        assert spain_words(line) == [], line
        assert not re.search(_USTED, line, re.IGNORECASE), line
    prompt = ch._prompt(ch.kb.KNOWLEDGE)
    assert 'say "El RUT y el pago los completas tú." in their language' in prompt
    said = re.findall(r'"([^"]*[áéíóúñ¿][^"]*)"', prompt.split("# The checkout")[1].split("\n#")[0])
    assert said, "the checkout section quotes no Spanish"
    for line in said:
        assert spain_words(line) == [], line
