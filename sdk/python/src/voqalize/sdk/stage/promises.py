"""Hearing a promise in one sentence of a reply.

A sentence promises a move in one of two ways. It says one of the move's
**claims** — a phrase written out for it, "opening the * calendar". Or it has
the **shape** of a promise about one of the move's **objects**: a first person
saying what it is about to do ("I'll", "I'm", "let me", "voy a", "te abro"),
then a verb, then, a few words on, a thing the move acts on ("the calendar",
"three nights", "las habitaciones"). The shape is what catches the sentences
nobody wrote a claim for; a live call (dev 453f2e19) said "I'll open the
calendar.", "I'm selecting three nights to see the rates." and "I'm opening the
rooms and rates for your three nights." and called nothing, and no hand-written
claim matched any of them.

What is never a promise: a question ("Shall I open the calendar?", an offer);
a sentence that only names the thing ("The rooms start at …"); a negation
("I'm not opening the calendar"); a condition ("If you like, I'll open the
calendar", an offer again); and the past ("I opened the calendar"), which
reports a move rather than promising one — true of a move an earlier turn
made, and a false report is a different fault, not one a retry would fix.

Everything is compared folded (:func:`~voqalize.sdk.stage.labels.tokens`:
NFKC, case folded, Latin accents off) and on whole words.
"""

from __future__ import annotations

import re

from .labels import tokens

__all__ = ["CLAIM_GAP", "VERB_REACH", "claim_in", "promise_in"]

#: The most words a ``*`` in a claim stands for, and the most words between a
#: promise's verb and its object (none is fine too).
CLAIM_GAP = 3

#: The most words from a promise's lead to its verb ("I'll just quickly open"):
#: the verb is one of the next this many words.
VERB_REACH = 3

#: Leads after which any word may be the verb: "I'll open", "let me pull up".
_ANY_VERB: tuple[tuple[str, ...], ...] = tuple(
    tuple(lead.split())
    for lead in (
        "i'll",
        "i will",
        "let me",
        "i'm going to",
        "i am going to",
        "i'm about to",
        "i am about to",
        "we'll",
        "let's",
    )
)
#: Leads whose verb is an English present participle: "I'm opening".
_ING: tuple[tuple[str, ...], ...] = (("i'm",), ("i", "am"), ("we're",))
#: Spanish leads whose verb is an infinitive: "voy a abrir", "déjame ver".
_INFINITIVE: tuple[tuple[str, ...], ...] = tuple(
    tuple(lead.split())
    for lead in ("voy a", "vamos a", "dejame", "permiteme", "deja que", "ahora mismo voy a")
)
#: Spanish leads whose verb is a gerund: "estoy abriendo".
_GERUND: tuple[tuple[str, ...], ...] = (("estoy",), ("estamos",))
#: Spanish first-person verbs that are the promise themselves: "te abro el
#: calendario", "reviso las fechas". Folded: no accents.
_ES_VERBS = frozenset(
    {
        "abro",
        "muestro",
        "enseno",
        "busco",
        "reviso",
        "consulto",
        "compruebo",
        "verifico",
        "miro",
        "cargo",
        "pongo",
        "selecciono",
        "elijo",
        "escojo",
        "marco",
        "preparo",
        "lleno",
        "relleno",
        "completo",
        "envio",
        "mando",
        "agrego",
        "anado",
        "traigo",
        "saco",
    }
)

_ING_FORM = re.compile(r"[a-z]{2,}ing")
_CLITICS = r"(?:me|te|se|lo|la|le|los|las|les|nos)*"
_INFINITIVE_FORM = re.compile(rf"[a-z]{{2,}}(?:ar|er|ir){_CLITICS}")
_GERUND_FORM = re.compile(rf"[a-z]{{2,}}(?:ando|iendo|yendo){_CLITICS}")

#: A word that turns a promise into its opposite.
_NOT = frozenset({"not", "never", "no", "nunca", "jamas", "won't", "can't", "cannot"})
#: A word before the lead that makes it a condition, an offer and not a promise.
_IF = frozenset({"if", "when", "whenever", "cuando"})
#: What follows a Spanish "si" that is "if", not "sí" ("Sí, te abro …"), which
#: folds to the same word.
_SI_IF = frozenset(
    {"quieres", "quiere", "prefieres", "prefiere", "deseas", "desea", "te", "le", "me", "lo", "la"}
)


def _conditional(words: list[str]) -> bool:
    """Whether ``words``, before a lead, make what follows a condition."""
    return any(
        w in _IF or (w == "si" and j + 1 < len(words) and words[j + 1] in _SI_IF)
        for j, w in enumerate(words)
    )


def claim_in(claim: str, sentence: str) -> bool:
    """Whether ``sentence`` says ``claim``, as whole folded words, each ``*``
    in it standing for up to :data:`CLAIM_GAP` words."""
    words = tokens(sentence)
    parts = [tokens(p) for p in claim.split("*")]
    return any(_claim_at(parts, words, i, 0) for i in range(len(words)))


def _claim_at(parts: list[list[str]], words: list[str], i: int, k: int) -> bool:
    part = parts[k]
    if words[i : i + len(part)] != part:
        return False
    j = i + len(part)
    if k == len(parts) - 1:
        return True
    return any(_claim_at(parts, words, j + gap, k + 1) for gap in range(CLAIM_GAP + 1))


def _names(word: str, obj: str) -> bool:
    """Whether ``word`` is ``obj`` or its plural ("room" → "rooms",
    "habitacion" → "habitaciones"). Never the other way: "rooms" does not name
    one "room", so two moves can split a noun by number."""
    return word in (obj, obj + "s", obj + "es") or (obj.endswith("y") and word == obj[:-1] + "ies")


def _object_at(words: list[str], i: int, objects: list[list[str]]) -> int | None:
    """Where the object said at word ``i`` ends, if one is."""
    for obj in objects:
        n = len(obj)
        last = i + n - 1
        if last < len(words) and words[i:last] == obj[:-1] and _names(words[last], obj[-1]):
            return i + n
    return None


def _verbs(words: list[str], at: int, lead: tuple[str, ...]) -> list[int]:
    """Where the verb after a lead ending at ``at`` may be, by the lead's kind;
    none past a negation."""
    if lead in _ANY_VERB:
        fits = None
    elif lead in _ING:
        fits = _ING_FORM
    elif lead in _INFINITIVE:
        fits = _INFINITIVE_FORM
    else:
        fits = _GERUND_FORM
    out: list[int] = []
    for j in range(at, min(at + VERB_REACH, len(words))):
        if words[j] in _NOT:
            break
        if fits is None or fits.fullmatch(words[j]):
            out.append(j)
    return out


_LEADS = (*_ANY_VERB, *_ING, *_INFINITIVE, *_GERUND)


def promise_in(objects: tuple[str, ...], sentence: str) -> str | None:
    """The words of ``sentence`` that promise to act on one of ``objects``,
    from the verb to the object ("opening the rooms", "open the calendar"), as
    folded words; ``None`` when it makes no such promise. A question is not
    checked here: the caller skips it, as it skips it for a claim."""
    words = tokens(sentence)
    wanted = [t for t in (tokens(o) for o in objects) if t]
    if not wanted:
        return None
    for i in range(len(words)):
        if _conditional(words[:i]):
            return None
        if i > 0 and words[i - 1] in _NOT:
            continue
        verbs: list[int] = []
        if words[i] in _ES_VERBS:
            verbs = [i]
        else:
            for lead in _LEADS:
                if tuple(words[i : i + len(lead)]) == lead:
                    verbs = _verbs(words, i + len(lead), lead)
                    if verbs:
                        break
        for v in verbs:
            for k in range(v + 1, min(v + 2 + CLAIM_GAP, len(words))):
                end = _object_at(words, k, wanted)
                if end is not None:
                    return " ".join(words[v:end])
    return None
