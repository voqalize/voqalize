"""Write ``bookings.json``: the other patients' appointments on every calendar.

The calendar must look like a working clinic's, and the slots the front desk
offers must be the ones the calendar leaves free, so the filler is data, not a
random number at run time. This script lays it down once, from a fixed seed,
around the sample patients' own appointments (``clinic.json``), and the brain and
the page both read the result. Dates are a week relative to the current one
(0 = this week) and a weekday, like everything else in the demo.

    cd demos && uv run python dental/data/build_bookings.py
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
WEEKS = range(-1, 4)
SEED = 20261118
#: How full a dentist's sessions are: the share of 15-minute steps that start a booking.
FILL = 0.2
IMAGING_FILL = 0.12


def minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def hhmm(total: int) -> str:
    return f"{total // 60:02d}:{total % 60:02d}"


def main() -> None:
    clinic: dict[str, Any] = json.loads((HERE / "clinic.json").read_text())
    rng = random.Random(SEED)
    services = {s["id"]: s for s in clinic["services"]}
    branches = {b["id"]: b for b in clinic["branches"]}
    # Busy intervals already taken: per dentist and per chair/room, by (week, day).
    taken: dict[tuple[str, int, str], list[tuple[int, int]]] = {}

    def busy(key: str, week: int, day: str, start: int, end: int) -> bool:
        return any(s < end and start < e for s, e in taken.get((key, week, day), []))

    def take(key: str, week: int, day: str, start: int, end: int) -> None:
        taken.setdefault((key, week, day), []).append((start, end))

    for a in clinic["patient_appointments"]:
        start = minutes(a["start"])
        end = start + int(a["duration_min"])
        if a.get("anchor") == "next_open_day":
            # Kept free on every open day of the weeks it can fall in.
            for week in (0, 1):
                for day in DAYS[:6]:
                    take(a["dentist"], week, day, start, end)
                    take(a["chair"], week, day, start, end)
            continue
        for key in (a.get("dentist"), a.get("chair"), a.get("resource")):
            if key:
                take(key, a["week"], a["day"], start, end)
    for p in clinic["patients"]:
        for h in p["history"]:
            if h["week"] < WEEKS.start:
                continue
            start = minutes(h["start"])
            dur = services[h["service"]].get("duration_min", 30)
            if h.get("dentist"):
                take(h["dentist"], h["week"], h["day"], start, start + dur)
            else:
                room = branches[h["branch"]]["imaging"][0]["id"]
                take(room, h["week"], h["day"], start, start + dur)

    out: list[dict[str, Any]] = []
    for week in WEEKS:
        for dentist in clinic["dentists"]:
            mine = [s for s in services.values() if dentist["id"] in s.get("dentists", [])]
            weights = [0.3 if s["id"] in ("wisdom", "whitening", "rct") else 1.0 for s in mine]
            for day, sessions in dentist["schedule"].items():
                for session in sessions:
                    branch = branches[session["branch"]]
                    t = minutes(session["start"])
                    end = minutes(session["end"])
                    while t < end:
                        if rng.random() >= FILL:
                            t += 15
                            continue
                        service = rng.choices(mine, weights)[0]
                        dur = int(service["duration_min"])
                        chairs = [c for c in branch["chairs"] if c["kind"] in service["chairs"]]
                        free = [c for c in chairs if not busy(c["id"], week, day, t, t + dur)]
                        if t + dur > end or busy(dentist["id"], week, day, t, t + dur) or not free:
                            t += 15
                            continue
                        chair = free[0]
                        take(dentist["id"], week, day, t, t + dur)
                        take(chair["id"], week, day, t, t + dur)
                        row: dict[str, Any] = {
                            "id": f"B-{len(out) + 1:04d}",
                            "week": week,
                            "day": day,
                            "start": hhmm(t),
                            "duration_min": dur,
                            "service": service["id"],
                            "dentist": dentist["id"],
                            "branch": branch["id"],
                            "chair": chair["id"],
                        }
                        if service.get("sittings"):
                            row["sitting"] = rng.randint(1, int(service["sittings"]))
                        out.append(row)
                        t += dur
        for branch in clinic["branches"]:
            for room in branch["imaging"]:
                kinds = [services[k] for k in room["does"]]
                for day in branch["open_days"]:
                    for session in room["sessions"]:
                        t = minutes(session["start"])
                        end = minutes(session["end"])
                        while t < end:
                            if rng.random() >= IMAGING_FILL:
                                t += 15
                                continue
                            service = rng.choice(kinds)
                            dur = int(service["duration_min"])
                            if t + dur > end or busy(room["id"], week, day, t, t + dur):
                                t += 15
                                continue
                            take(room["id"], week, day, t, t + dur)
                            out.append(
                                {
                                    "id": f"B-{len(out) + 1:04d}",
                                    "week": week,
                                    "day": day,
                                    "start": hhmm(t),
                                    "duration_min": dur,
                                    "service": service["id"],
                                    "branch": branch["id"],
                                    "resource": room["id"],
                                }
                            )
                            t += max(dur, 15)

    doc = {
        "$comment": "Generated by build_bookings.py from a fixed seed; do not edit by hand. Other patients' appointments: week relative to the current one (0 = this week, Monday first), weekday, start, length. No names: the page shows them as Booked.",
        "bookings": out,
    }
    rows = ",\n".join("  " + json.dumps(b, ensure_ascii=False) for b in out)
    head = json.dumps(doc["$comment"], ensure_ascii=False)
    (HERE / "bookings.json").write_text(
        f'{{\n "$comment": {head},\n "bookings": [\n{rows}\n ]\n}}\n'
    )
    print(f"bookings.json: {len(out)} bookings")


if __name__ == "__main__":
    main()
