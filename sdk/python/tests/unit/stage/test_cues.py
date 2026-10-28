"""The cue parser: cues out of the speech, each anchored to the words after it.

Ported from the two site demos' parser tests where the behaviour carries over;
``at`` is now the raw spoken text and ``before`` a character count, so the
page segments words and the brain never does.
"""

from __future__ import annotations

from voqalize.sdk.stage import MAX_CUE, CueParser, RawCue
from voqalize.sdk.stage.cues import AutoCues

VERBS = ("page", "show", "faq", "pick")


def _run(*chunks: str, auto: AutoCues | None = None) -> tuple[str, list[RawCue]]:
    p = CueParser(VERBS, auto)
    spoken = ""
    cues: list[RawCue] = []
    for c in chunks:
        text, got = p.feed(c)
        spoken += text
        cues += got
    text, got = p.flush()
    return spoken + text, cues + got


# ─── grammar ────────────────────────────────────────────────────────────────


def test_cues_leave_the_speech_and_anchor_to_the_words_after_them() -> None:
    spoken, cues = _run(
        "{page: /}{show: How Potion works} It takes three steps. "
        "{show: Train video AI} First, you train the AI on you."
    )
    assert spoken == " It takes three steps. First, you train the AI on you."
    assert [(c.verb, c.args, c.at, c.before) for c in cues] == [
        ("page", ("/",), "It takes three steps. First, you train the AI on", 0),
        ("show", ("How Potion works",), "It takes three steps. First, you train the AI on", 0),
        ("show", ("Train video AI",), "First, you train the AI on", 23),
    ]
    # ``before`` counts the spoken text exactly.
    assert spoken[23:].startswith("First")


def test_several_args_split_on_pipes_and_trimmed() -> None:
    spoken, cues = _run("{pick: Size |  Large|Blue } Done, it's large and blue.")
    assert spoken == " Done, it's large and blue."
    assert [c.args for c in cues] == [("Size", "Large", "Blue")]


def test_a_cue_without_args() -> None:
    spoken, cues = _run("Here. {faq} We go.")
    assert spoken == "Here. We go."
    assert [(c.verb, c.args, c.at) for c in cues] == [("faq", (), "We go.")]


def test_too_many_or_empty_or_long_args_are_not_cues_and_not_spoken() -> None:
    long = "x" * 81
    spoken, cues = _run(f"A {{pick: a|b|c|d|e}} B {{pick: a||b}} C {{show: {long}}} D.")
    assert spoken == "A B C D." and cues == []


def test_unknown_verbs_and_other_braces_are_dropped_never_spoken() -> None:
    spoken, cues = _run('Hello {mood: happy} there {"name": "x"} friend.')
    assert spoken == "Hello there friend." and cues == []


def test_a_stray_brace_past_max_cue_is_spoken() -> None:
    long = "word " * (MAX_CUE // 4)
    spoken, cues = _run("Open { " + long, "and on.")
    assert "{" not in spoken and spoken.startswith("Open ") and cues == []
    assert spoken.endswith("and on.")


def test_an_unclosed_brace_at_the_end_of_the_unit_is_spoken() -> None:
    spoken, cues = _run("Ends with {sho")
    assert spoken == "Ends with sho" and cues == []


def test_cue_free_text_is_byte_identical() -> None:
    chunks = ("Hola, ", "¿cómo estás?  Bien.\n", "Sí. $39.99 total…")
    spoken, cues = _run(*chunks)
    assert spoken == "".join(chunks) and cues == []


def test_several_cues_before_one_sentence_share_its_anchor_in_order() -> None:
    _, cues = _run("{show: A}{faq: B} {show: C} One two three four.")
    assert [(c.args[0], c.at, c.before) for c in cues] == [
        ("A", "One two three", 0),
        ("B", "One two three", 0),
        ("C", "One two three", 1),
    ]


def test_the_verb_is_matched_case_insensitively() -> None:
    _, cues = _run("{Show: Rooms} Here they are now.")
    assert [c.verb for c in cues] == ["show"]


# ─── anchors ────────────────────────────────────────────────────────────────


def test_a_cue_at_the_end_fires_when_the_voice_stops() -> None:
    spoken, cues = _run("Here is the FAQ. {faq: Can I cancel anytime?}")
    assert spoken == "Here is the FAQ. "
    assert [(c.verb, c.at, c.before) for c in cues] == [("faq", "", 17)]


def test_at_is_cut_to_48_chars_on_a_space() -> None:
    _, cues = _run(
        "{show: Rooms} Every one of our rooms looks out across the bay to the mountains."
    )
    assert cues[0].at == "Every one of our rooms looks out across the bay"
    assert len(cues[0].at) <= 48


def test_at_collapses_whitespace() -> None:
    _, cues = _run("{show: Rooms}  Every\n room   here.")
    assert cues[0].at == "Every room here."


def test_spanish_keeps_its_accents_raw() -> None:
    spoken, cues = _run("{show: Exámenes de Resonancia} Así se agenda tu exámen.")
    assert spoken == " Así se agenda tu exámen."
    assert [(c.args, c.at) for c in cues] == [(("Exámenes de Resonancia",), "Así se agenda tu")]


def test_hindi_with_danda_sentence_ends() -> None:
    seen: list[str] = []

    def auto(
        sentence: str, index: int, placed: tuple[tuple[str, tuple[str, ...]], ...]
    ) -> list[tuple[str, list[str]]]:
        seen.append(sentence)
        return []

    spoken, cues = _run("{show: कमरे} यह हमारा सबसे अच्छा कमरा है। {show: कीमत} कीमत यहाँ है।", auto=auto)
    assert spoken == " यह हमारा सबसे अच्छा कमरा है। कीमत यहाँ है।"
    assert seen == ["यह हमारा सबसे अच्छा कमरा है।", "कीमत यहाँ है।"]
    assert [(c.args[0], c.at, c.before) for c in cues] == [
        ("कमरे", "यह हमारा सबसे अच्छा कमरा है। कीमत यहाँ", 0),
        ("कीमत", "कीमत यहाँ है।", spoken.index("कीमत")),
    ]


def test_japanese_without_spaces() -> None:
    seen: list[str] = []

    def auto(
        sentence: str, index: int, placed: tuple[tuple[str, tuple[str, ...]], ...]
    ) -> list[tuple[str, list[str]]]:
        seen.append(sentence)
        return []

    p = CueParser(VERBS, auto)
    text, got = p.feed("{show: 客室}ここが一番人気のお部屋です。")
    # Twelve characters of a spaceless script release it without a space.
    assert text == "ここが一番人気のお部屋です。"
    assert [(c.args, c.at, c.before) for c in got] == [
        (("客室",), "ここが一番人気のお部屋です。", 0)
    ]
    text, got = p.feed("{show: 料金}料金はこちら。")
    assert got == []  # Only six characters follow it so far.
    _, got = p.flush()
    assert [(c.at, c.before) for c in got] == [("料金はこちら。", 14)]
    # A full-width stop ends a sentence with no space after it.
    assert seen == ["ここが一番人気のお部屋です。", "料金はこちら。"]


# ─── streaming ──────────────────────────────────────────────────────────────


def test_a_cue_split_across_chunks_still_parses() -> None:
    spoken, cues = _run(
        "Plans start low. {sh", "ow: Pricing pl", "ans} Thirty-nine dol", "lars a month."
    )
    assert spoken == "Plans start low. Thirty-nine dollars a month."
    # Released once three whole tokens follow it; the fourth may still grow.
    assert [(c.args, c.at, c.before) for c in cues] == [
        (("Pricing plans",), "Thirty-nine dollars a", 17)
    ]


def test_a_cue_waits_for_three_whole_tokens() -> None:
    p = CueParser(VERBS)
    assert p.feed("{show: Rooms} One two thr") == (" One two thr", [])
    assert p.feed("ee") == ("ee", [])
    text, got = p.feed(" four")
    assert text == " four" and [c.at for c in got] == ["One two three"]


def test_the_space_after_a_removed_cue_is_not_said_twice_across_chunks() -> None:
    spoken, _ = _run("Look here. ", "{show: Rooms}", " The rooms.")
    assert spoken == "Look here. The rooms."


def test_unit_is_carried() -> None:
    p = CueParser(VERBS, unit=2)
    p.feed("{show: Rooms} Here.")
    assert [c.unit for c in p.flush()[1]] == [2]


# ─── backstop ───────────────────────────────────────────────────────────────


def test_each_sentence_is_offered_for_the_moves_it_did_not_bring() -> None:
    seen: list[tuple[str, int, tuple[tuple[str, tuple[str, ...]], ...]]] = []

    def auto(
        sentence: str, index: int, placed: tuple[tuple[str, tuple[str, ...]], ...]
    ) -> list[tuple[str, list[str]]]:
        seen.append((sentence, index, placed))
        return [("show", ["Re-engage dormant leads"])] if "dormant" in sentence else []

    spoken, cues = _run(
        "{page: /sales} Hi. Reps wake up dor", "mant leads, too. Want pricing?", auto=auto
    )
    assert seen == [
        ("Hi.", 0, (("page", ("/sales",)),)),
        ("Reps wake up dormant leads, too.", 1, ()),
        ("Want pricing?", 2, ()),
    ]
    assert [(c.verb, c.args, c.at, c.before, c.auto) for c in cues] == [
        ("page", ("/sales",), "Hi. Reps wake up", 0, False),
        ("show", ("Re-engage dormant leads",), "Reps wake up dormant leads, too. Want", 5, True),
    ]
    assert spoken[5:].startswith("Reps")


def test_backstop_cues_with_unknown_verbs_are_dropped() -> None:
    def auto(
        sentence: str, index: int, placed: tuple[tuple[str, tuple[str, ...]], ...]
    ) -> list[tuple[str, list[str]]]:
        return [("wave", []), ("show", ["Rooms"])]

    _, cues = _run("Our rooms are lovely.", auto=auto)
    assert [(c.verb, c.args, c.at) for c in cues] == [("show", ("Rooms",), "Our rooms are lovely.")]


def test_a_backstop_cue_keeps_the_order_of_the_model_cues() -> None:
    def auto(
        sentence: str, index: int, placed: tuple[tuple[str, tuple[str, ...]], ...]
    ) -> list[tuple[str, list[str]]]:
        return [("show", [sentence[:3]])]

    # The model's cue sits mid-sentence and is placed first; the backstop's
    # belongs at the sentence's start, so it fires first.
    _, cues = _run("Our rooms {faq: Q} are lovely to see now.", auto=auto)
    assert [(c.verb, c.auto, c.before) for c in cues] == [("show", True, 0), ("faq", False, 10)]
