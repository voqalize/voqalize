"""Finding the clause that answers "am I covered if…" in the customer's own
policy documents. A plain word search over each clause's tags, title and
wording: the documents are small, and the model reads the few clauses it gets
back and says what they say."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from .store import POLICIES, clauses

Json = dict[str, Any]

_STOP = frozenset((
    "a", "an", "the", "i", "im", "i'm", "my", "me", "we", "our", "you", "your", "is", "am",
    "are", "was", "were", "be", "been", "do", "does", "did", "if", "what", "whats", "which",
    "who", "when", "where", "how", "can", "could", "will", "would", "should", "shall",
    "may", "might", "it", "its", "this", "that", "these", "those", "to", "of", "in", "on",
    "at", "for", "from", "by", "with", "and", "or", "but", "not", "no", "yes", "covered",
    "cover", "covers", "coverage", "insurance", "policy", "policies", "claim", "get", "got",
    "have", "has", "had", "any", "some", "about", "under", "there", "their", "them", "they",
    "he", "she", "him", "her", "his", "hers", "kya", "hai", "ki", "ka", "ke", "mein", "me",
    "agar", "toh", "to", "bhi",
))  # fmt: skip


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def terms(text: str) -> list[str]:
    words = re.findall(r"[\w']+", _fold(text))
    return [_stem(w) for w in words if w not in _STOP and len(w) > 1]


def _score(query: list[str], clause: Json) -> float:
    if not query:
        return 0.0
    tags = {t for tag in clause.get("tags", []) for t in terms(tag)}
    title = set(terms(clause.get("title", "")))
    body = set(terms(clause.get("text", "") + " " + clause.get("plain", "")))
    score = 0.0
    for q in query:
        if q in tags:
            score += 3
        if q in title:
            score += 2
        if q in body:
            score += 1
    return score


def search(
    question: str, policy_id: str | None, top: int = 4
) -> list[tuple[str, Json, Json, float]]:
    """(policy_id, section, clause, score), best first."""
    query = terms(question)
    ids = [policy_id] if policy_id is not None and policy_id in POLICIES else list(POLICIES)
    found = [(pid, s, c, _score(query, c)) for pid in ids for s, c in clauses(pid)]
    found = [f for f in found if f[3] > 0]
    found.sort(key=lambda f: -f[3])
    return found[:top]


def clause_text(policy_id: str, section: Json, clause: Json) -> str:
    return (
        f"{policy_id} clause {clause['id']} ({section.get('title', '')}) — {clause['title']} "
        f"[{clause.get('kind', 'info')}]: {clause.get('text', '')} In plain words: {clause.get('plain', '')}"
    )
