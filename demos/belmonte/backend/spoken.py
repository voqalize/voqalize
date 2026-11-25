"""How the concierge's words reach the voice, and how the guest's reach the tools.

**Speech.** Dollar amounts ("$18.50", "$1,797.72") and clock times ("7:30 PM")
go to the voice as written: they are the ordinary US forms a TTS reads. A room
number is the exception: "room 1412" read as a number is "one thousand four
hundred twelve", and a hotel says "fourteen twelve". :func:`speak_text`
rewrites room numbers the way a front desk says them ("room fourteen twelve",
"room eleven oh eight", "room five sixteen"), and :class:`Spoken` does it as
the speech streams. The screen keeps "1412".

**Words to values.** The model passes what the guest said; :func:`parse_time`
and :func:`parse_date` turn "7:30 pm", "half past six", "noon", "tomorrow",
"Friday" or "Nov 27" into ``HH:MM`` and ``YYYY-MM-DD`` against the stay's clock.
"""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator
from datetime import date, timedelta

from voqalize.sdk import Speech, SpeechChunk, SpeechEnd

_ONES = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def _two(n: int) -> str:
    if n < 20:
        return _ONES[n]
    t, o = divmod(n, 10)
    return _TENS[t] + (f"-{_ONES[o]}" if o else "")


def room_words(num: str) -> str:
    """1412 -> fourteen twelve; 1108 -> eleven oh eight; 0516 -> five sixteen; 304 -> three oh four."""
    n = num.lstrip("0") or "0"
    if len(n) <= 2:
        return _two(int(n))
    head, tail = n[:-2], int(n[-2:])
    first = _two(int(head))
    if tail == 0:
        return f"{first} hundred"
    return f"{first} {'oh ' + _ONES[tail] if tail < 10 else _two(tail)}"


_ROOM = re.compile(r"\b([Rr]oom|ROOM)\s+(\d{3,4})\b")


def speak_text(text: str) -> str:
    """The words as the voice should say them."""
    return _ROOM.sub(lambda m: f"{m.group(1)} {room_words(m.group(2))}", text)


class Spoken:
    """Rewrites a brain's speech with :func:`speak_text` as it streams, holding the
    last two words back until the next chunk (so "room" and its number meet)."""

    async def wrap(self, speech: AsyncGenerator[Speech, None]) -> AsyncGenerator[Speech, None]:
        held = ""
        try:
            async for event in speech:
                if isinstance(event, SpeechChunk):
                    held += event.text
                    spaces = [m.end() for m in re.finditer(r"\s+", held)]
                    if len(spaces) >= 2:
                        cut = spaces[-2]
                        ready, held = held[:cut], held[cut:]
                        yield SpeechChunk(speak_text(ready))
                    continue
                if isinstance(event, SpeechEnd) and held:
                    yield SpeechChunk(speak_text(held))
                    held = ""
                yield event
        finally:
            await speech.aclose()


# ─── Words to values ─────────────────────────────────────────────────────────

_WORD_NUM = {w: i for i, w in enumerate(_ONES)} | {"half": 30, "quarter": 15}
_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def parse_time(said: str | None, now: str | None = None) -> str | None:
    """'7:30 pm', '19:30', '7 pm', '730', 'noon', 'midnight', 'half past six in the
    evening', 'now' -> 'HH:MM' (24 hour); None when it is not a time."""
    if said is None:
        return None
    s = said.strip().lower().replace(".", "")
    if not s:
        return None
    if s in ("now", "right now", "asap", "as soon as possible") and now:
        return now
    if s in ("noon", "midday", "12 noon"):
        return "12:00"
    if s == "midnight":
        return "24:00"
    pm = bool(re.search(r"\b(pm|p m|evening|tonight|afternoon)\b", s))
    am = bool(re.search(r"\b(am|a m|morning)\b", s))
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\b", s)
    h: int | None = None
    mi = 0
    if m:
        h, mi = int(m.group(1)), int(m.group(2) or 0)
        if m.group(2) is None and len(m.group(1)) <= 2:
            compact = re.search(r"\b(\d{3,4})\b", s)
            if compact:
                v = compact.group(1).zfill(4)
                h, mi = int(v[:2]), int(v[2:])
    else:
        compact = re.search(r"\b(\d{3,4})\b", s)
        if compact:
            v = compact.group(1).zfill(4)
            h, mi = int(v[:2]), int(v[2:])
        else:
            words = s.replace("-", " ").split()
            nums = [_WORD_NUM[w] for w in words if w in _WORD_NUM and w not in ("half", "quarter")]
            if nums:
                h = nums[-1] if "past" in words or "to" in words else nums[0]
                if "past" in words:
                    mi = 30 if "half" in words else 15 if "quarter" in words else 0
                elif "to" in words and "quarter" in words:
                    h, mi = h - 1, 45
                elif len(nums) > 1:
                    mi = nums[1] if nums[1] >= 10 else 0
    if h is None or not (0 <= h <= 24) or not (0 <= mi < 60):
        return None
    if pm and h < 12:
        h += 12
    if am and h == 12:
        h = 0
    return f"{h:02d}:{mi:02d}"


def parse_date(said: str | None, today: str) -> str | None:
    """'today', 'tonight', 'tomorrow', 'Friday', 'Nov 27', '27th', '2026-11-27' -> ISO date."""
    if said is None:
        return None
    s = said.strip().lower()
    t = date.fromisoformat(today)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s
    if s in ("", "today", "tonight", "this evening", "this afternoon", "this morning", "now"):
        return t.isoformat()
    if s in ("tomorrow", "tomorrow morning", "tomorrow evening", "tomorrow night"):
        return (t + timedelta(days=1)).isoformat()
    if "day after tomorrow" in s:
        return (t + timedelta(days=2)).isoformat()
    for i, d in enumerate(_DAYS):
        if d in s or s == d[:3]:
            ahead = (i - t.weekday()) % 7
            return (t + timedelta(days=ahead)).isoformat()
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\b", s)
    month = next((i + 1 for i, mo in enumerate(_MONTHS) if mo in s), None)
    if m:
        dd = int(m.group(1))
        mo = month or t.month
        try:
            out = date(t.year, mo, dd)
        except ValueError:
            return None
        if out < t:
            out = date(t.year + 1, mo, dd) if month else out
        return out.isoformat()
    return None
