"""The clinic's authored data, and the calendar computed from it.

Everything the front desk says about a slot, a price, a rule or a policy comes
from ``data/clinic.json`` and ``data/bookings.json`` through this module. Slots
are computed, never invented: a time is offered only when the dentist works
then, at that branch, has nothing booked over it, and a chair of a kind the
service needs (or, for a scan, the imaging room that takes it) is free for its
whole length. The page computes the same thing in ``frontend/src/data/slots.ts``
by the algorithm in ``CONTRACT.md``; ``data/slot_fixtures.json``, written by
:func:`write_fixtures`, holds the two to the same answers.

Dates are never stored. A booking names a week relative to the current one
(0 = this week, Monday first) and a weekday, so the calendar is full whatever
day the demo runs; :class:`Calendar` turns them into dates against a "today".
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
IST = ZoneInfo("Asia/Kolkata")
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
Category = Literal["appointment", "procedure", "imaging"]

# ─── The authored data ────────────────────────────────────────────────────────


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class Session(_Model):
    branch: str = ""
    start: str
    end: str


class Chair(_Model):
    id: str
    label: str
    kind: str


class Room(_Model):
    id: str
    label: str
    does: list[str]
    sessions: list[Session]


class Branch(_Model):
    id: str
    name: str
    short: str
    address: str
    landmark: str
    phone: str
    open_days: list[str]
    open: str
    close: str
    parking: str
    chairs: list[Chair]
    imaging: list[Room]


class Dentist(_Model):
    id: str
    name: str
    short: str
    qualification: str
    role: str
    years: int
    languages: list[str]
    bio: str
    schedule: dict[str, list[Session]]


class Price(_Model):
    min: int
    max: int
    note: str = ""


class Gap(_Model):
    min: int
    max: int


class Service(_Model):
    id: str
    category: Category
    name: str
    spoken: list[str]
    duration_min: int
    price: Price
    dentists: list[str] = Field(default_factory=list[str])
    chairs: list[str] = Field(default_factory=list[str])
    resource: str | None = None
    same_day: bool = False
    sittings: int = 1
    sitting_gap_days: Gap | None = None
    requires: str | None = None
    summary: str


class Rule(_Model):
    title: str
    text: str
    consult_services: list[str] = Field(default_factory=list[str])
    within_days: int | None = None
    alternative: str | None = None


class Cancellation(_Model):
    free_until_hours: int
    late_fee: int
    late_fee_waived_for: list[str]
    no_show_fee: int
    imaging_free_until_hours: int
    online_changes_max: int
    text: str
    rct_text: str


class Referral(_Model):
    from_: str = Field(alias="from")
    for_: str = Field(alias="for")
    note: str = ""


class Visit(_Model):
    """A past visit on a patient's record."""

    service: str
    branch: str
    week: int
    day: str
    start: str
    dentist: str | None = None
    sitting: int | None = None


class Patient(_Model):
    id: str
    name: str
    phone: str
    age: int
    since: int
    referral: Referral | None = None
    history: list[Visit] = Field(default_factory=list[Visit])


class Booking(_Model):
    """An appointment on the calendar: another patient's (no ``patient_id``) or
    a sample patient's, before it has a date."""

    id: str
    service: str
    branch: str
    start: str
    duration_min: int
    week: int | None = None
    day: str | None = None
    anchor: Literal["next_open_day"] | None = None
    dentist: str | None = None
    chair: str | None = None
    resource: str | None = None
    patient_id: str | None = None
    sitting: int | None = None
    changes: int = 0


class Instructions(_Model):
    title: str
    text: str = ""
    general: str = ""
    by_service: dict[str, str] = Field(default_factory=dict[str, str])


class Clinical(_Model):
    topics: list[str]
    red_flags: str
    callback_windows: dict[str, str]


class ClinicInfo(_Model):
    name: str
    short: str
    tagline: str
    phone: str
    whatsapp: str
    email: str
    timezone: str
    since: int
    emergency_line: str


class BookingRules(_Model):
    slot_step_min: int
    lead_min: int
    emergency_lead_min: int
    horizon_days: int
    id_prefix: str


class Otp(_Model):
    demo_code: str


class ClinicData(_Model):
    clinic: ClinicInfo
    booking: BookingRules
    otp: Otp
    branches: list[Branch]
    dentists: list[Dentist]
    services: list[Service]
    rules: dict[str, Rule]
    policies: dict[str, Cancellation]
    instructions: dict[str, Instructions]
    clinical: Clinical
    patients: list[Patient]
    patient_appointments: list[Booking]


class _Bookings(_Model):
    bookings: list[Booking]


def load() -> tuple[ClinicData, list[Booking]]:
    data = ClinicData.model_validate(json.loads((DATA / "clinic.json").read_text()))
    filler = _Bookings.model_validate(json.loads((DATA / "bookings.json").read_text()))
    return data, filler.bookings


DATA_, FILLER = load()


def service(sid: str) -> Service | None:
    return next((s for s in DATA_.services if s.id == sid), None)


def dentist(did: str) -> Dentist | None:
    return next((d for d in DATA_.dentists if d.id == did), None)


def who(did: str | None, *, full: bool = False, none: str = "imaging room") -> str:
    """A dentist's name as said ("Dr Rahul"), or ``none`` for a scan."""
    d = dentist(did) if did else None
    if d is None:
        return none
    return d.name if full else d.short


def branch(bid: str) -> Branch | None:
    return next((b for b in DATA_.branches if b.id == bid), None)


def patient(pid: str) -> Patient | None:
    """A patient on the clinic's record, by id. The brain finds a patient only
    this way: the page signs them in from the number they typed and names them
    by id (FEEDBACK X9), so no lookup by phone number exists here."""
    return next((p for p in DATA_.patients if p.id == pid), None)


def first_name(name: str) -> str:
    """ "Rohan Mehta" → "Rohan"."""
    return name.split()[0] if name.split() else name


def minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def hhmm(total: int) -> str:
    return f"{total // 60:02d}:{total % 60:02d}"


def rupees(n: int) -> str:
    """₹1,25,000 — the Indian grouping."""
    s = str(n)
    if len(s) <= 3:
        return f"₹{s}"
    head, tail = s[:-3], s[-3:]
    groups: list[str] = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return "₹" + ",".join([*groups, tail])


def price_text(s: Service) -> str:
    p = s.price
    core = rupees(p.min) if p.min == p.max else f"{rupees(p.min)} to {rupees(p.max)}"
    return f"{core} ({p.note})" if p.note else core


def spoken_time(t: str) -> str:
    """'14:30' → '2:30 pm'."""
    m = minutes(t)
    h, mm = divmod(m, 60)
    suffix = "am" if h < 12 else "pm"
    h12 = h % 12 or 12
    return f"{h12}:{mm:02d} {suffix}" if mm else f"{h12} {suffix}"


def spoken_date(d: date, today: date | None = None) -> str:
    """'Thu 20 Nov', with 'today' and 'tomorrow' when they are."""
    if today is not None and d == today:
        return f"today, {d:%a} {d.day} {d:%b}"
    if today is not None and d == today + timedelta(days=1):
        return f"tomorrow, {d:%a} {d.day} {d:%b}"
    return f"{d:%a} {d.day} {d:%b}"


# ─── The calendar ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Appt:
    """One appointment with its date: what the calendar and the slots read."""

    id: str
    service: str
    branch: str
    on: date
    start: int
    duration_min: int
    dentist: str | None = None
    chair: str | None = None
    resource: str | None = None
    patient_id: str | None = None
    sitting: int | None = None
    changes: int = 0
    status: Literal["booked", "cancelled"] = "booked"

    @property
    def end(self) -> int:
        return self.start + self.duration_min

    def at(self) -> datetime:
        return datetime(self.on.year, self.on.month, self.on.day, tzinfo=IST) + timedelta(
            minutes=self.start
        )

    def holds(self) -> tuple[str, ...]:
        """The dentist, chair and room this appointment keeps busy."""
        return tuple(k for k in (self.dentist, self.chair, self.resource) if k)


@dataclass(frozen=True)
class Slot:
    on: date
    start: int
    branch: str
    dentist: str | None
    chair: str | None
    resource: str | None

    @property
    def time(self) -> str:
        return hhmm(self.start)


def now_ist() -> datetime:
    return datetime.now(IST)


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def date_of(today: date, week: int, day: str) -> date:
    return monday_of(today) + timedelta(days=7 * week + DAYS.index(day))


def next_open_day(today: date) -> date:
    d = today + timedelta(days=1)
    while DAYS[d.weekday()] == "sun":
        d += timedelta(days=1)
    return d


def dated(b: Booking, today: date) -> Appt:
    if b.anchor == "next_open_day":
        on = next_open_day(today)
    else:
        assert b.week is not None, b.id
        assert b.day is not None, b.id
        on = date_of(today, b.week, b.day)
    return Appt(
        id=b.id,
        service=b.service,
        branch=b.branch,
        on=on,
        start=minutes(b.start),
        duration_min=b.duration_min,
        dentist=b.dentist,
        chair=b.chair,
        resource=b.resource,
        patient_id=b.patient_id,
        sitting=b.sitting,
        changes=b.changes,
    )


@dataclass
class Calendar:
    """Every appointment as of ``now``: the authored ones, then this session's
    changes (new bookings, moves and cancellations) laid over them."""

    now: datetime
    appts: dict[str, Appt] = field(default_factory=dict[str, Appt])

    @classmethod
    def build(cls, now: datetime) -> Calendar:
        today = now.astimezone(IST).date()
        cal = cls(now=now)
        for b in (*FILLER, *DATA_.patient_appointments):
            cal.appts[b.id] = dated(b, today)
        return cal

    @property
    def today(self) -> date:
        return self.now.astimezone(IST).date()

    @property
    def minute_now(self) -> int:
        n = self.now.astimezone(IST)
        return n.hour * 60 + n.minute

    def put(self, a: Appt) -> None:
        self.appts[a.id] = a

    def live(self) -> Iterable[Appt]:
        return (a for a in self.appts.values() if a.status == "booked")

    def busy(self, key: str, on: date, start: int, end: int, *, ignore: str | None = None) -> bool:
        for a in self.live():
            if (
                a.on == on
                and a.id != ignore
                and key in a.holds()
                and a.start < end
                and start < a.end
            ):
                return True
        return False

    def of_patient(self, pid: str) -> list[Appt]:
        return sorted((a for a in self.appts.values() if a.patient_id == pid), key=lambda a: a.at())

    def upcoming(self, pid: str) -> list[Appt]:
        return [a for a in self.of_patient(pid) if a.status == "booked" and a.at() > self.now]

    # ─── Slots ──────────────────────────────────────────────────────────

    def earliest(self, svc: Service, on: date) -> int:
        """The first minute a booking may start on ``on``: any time on a later
        day; today, the lead time from now."""
        if on != self.today:
            return 0
        lead = DATA_.booking.emergency_lead_min if svc.same_day else DATA_.booking.lead_min
        return self.minute_now + lead

    def bookable_day(self, on: date) -> bool:
        return self.today <= on <= self.today + timedelta(days=DATA_.booking.horizon_days)

    def slots(
        self,
        svc: Service,
        on: date,
        *,
        branch_id: str | None = None,
        dentist_id: str | None = None,
        ignore: str | None = None,
    ) -> list[Slot]:
        """Every start time on ``on`` for ``svc``, earliest first; at most one
        slot per start time and dentist (or room). ``ignore`` leaves one
        appointment out, for moving it."""
        if not self.bookable_day(on):
            return []
        step = DATA_.booking.slot_step_min
        first = self.earliest(svc, on)
        dur = svc.duration_min
        out: list[Slot] = []
        day = DAYS[on.weekday()]
        if svc.resource is not None:
            for b in DATA_.branches:
                if (branch_id and b.id != branch_id) or day not in b.open_days:
                    continue
                for room in b.imaging:
                    if svc.resource not in room.does:
                        continue
                    for s in room.sessions:
                        t, end = minutes(s.start), minutes(s.end)
                        while t + dur <= end:
                            if t >= first and not self.busy(room.id, on, t, t + dur, ignore=ignore):
                                out.append(Slot(on, t, b.id, None, None, room.id))
                            t += step
        else:
            for did in svc.dentists:
                if dentist_id and did != dentist_id:
                    continue
                d = dentist(did)
                if d is None:
                    continue
                for s in d.schedule.get(day, []):
                    if branch_id and s.branch != branch_id:
                        continue
                    b = branch(s.branch)
                    if b is None:
                        continue
                    chairs = [c for c in b.chairs if c.kind in svc.chairs]
                    t, end = minutes(s.start), minutes(s.end)
                    while t + dur <= end:
                        if t >= first and not self.busy(did, on, t, t + dur, ignore=ignore):
                            chair = next(
                                (
                                    c
                                    for c in chairs
                                    if not self.busy(c.id, on, t, t + dur, ignore=ignore)
                                ),
                                None,
                            )
                            if chair is not None:
                                out.append(Slot(on, t, b.id, did, chair.id, None))
                        t += step
        return sorted(out, key=lambda x: (x.start, x.dentist or x.resource or ""))

    def slot_at(
        self,
        svc: Service,
        on: date,
        time: str,
        *,
        branch_id: str | None = None,
        dentist_id: str | None = None,
        ignore: str | None = None,
    ) -> Slot | None:
        t = minutes(time)
        return next(
            (
                s
                for s in self.slots(
                    svc, on, branch_id=branch_id, dentist_id=dentist_id, ignore=ignore
                )
                if s.start == t
            ),
            None,
        )

    def next_days(
        self,
        svc: Service,
        *,
        branch_id: str | None = None,
        dentist_id: str | None = None,
        start: date | None = None,
        days: int = 3,
        ignore: str | None = None,
    ) -> list[tuple[date, list[Slot]]]:
        """The first ``days`` days, from ``start`` (today), that have a slot."""
        out: list[tuple[date, list[Slot]]] = []
        on = max(start or self.today, self.today)
        last = self.today + timedelta(days=DATA_.booking.horizon_days)
        while on <= last and len(out) < days:
            got = self.slots(svc, on, branch_id=branch_id, dentist_id=dentist_id, ignore=ignore)
            if got:
                out.append((on, got))
            on += timedelta(days=1)
        return out

    # ─── Multi-sitting plans ────────────────────────────────────────────

    def plan_sittings(self, svc: Service, first: Slot) -> list[Slot]:
        """The sittings after the first, each 7 to 14 days after the one
        before, with the same dentist: the same time of day if it is free,
        else the nearest free time that day; the earliest such day wins."""
        gap = svc.sitting_gap_days
        if svc.sittings <= 1 or gap is None:
            return []
        out: list[Slot] = []
        prev = first
        for _ in range(svc.sittings - 1):
            pick: Slot | None = None
            for k in range(gap.min, gap.max + 1):
                on = prev.on + timedelta(days=k)
                got = [
                    s
                    for s in self.slots(svc, on, dentist_id=prev.dentist)
                    if not any(
                        o.on == s.on and abs(o.start - s.start) < svc.duration_min for o in out
                    )
                ]
                if got:
                    pick = min(
                        got, key=lambda s: (abs(s.start - first.start), s.branch != first.branch)
                    )
                    break
            if pick is None:
                break
            out.append(pick)
            prev = pick
        return out


# ─── Rules that depend on the patient ────────────────────────────────────────


@dataclass(frozen=True)
class RuleCheck:
    ok: bool | None  # None: the patient is not known yet
    rule: Rule | None = None
    why: str = ""


def visits(p: Patient, cal: Calendar) -> list[tuple[str, date]]:
    """Every visit on the patient's record and calendar: (service, date)."""
    out = [(v.service, date_of(cal.today, v.week, v.day)) for v in p.history]
    out += [(a.service, a.on) for a in cal.of_patient(p.id) if a.status == "booked"]
    return out


def check_rule(svc: Service, p: Patient | None, on: date, cal: Calendar) -> RuleCheck:
    if svc.requires is None:
        return RuleCheck(ok=True)
    rule = DATA_.rules[svc.requires]
    if p is None:
        return RuleCheck(ok=None, rule=rule, why="the patient is not verified yet")
    if svc.requires == "cbct_referral":
        if p.referral is not None and p.referral.for_ == "cbct":
            return RuleCheck(ok=True, rule=rule, why=f"referral on file from {p.referral.from_}")
        seen = [(s, d) for s, d in visits(p, cal) if s in rule.consult_services and d <= on]
        if seen:
            s, d = seen[0]
            name = service(s)
            return RuleCheck(
                ok=True,
                rule=rule,
                why=f"{name.name if name else s} on {spoken_date(d)} counts as the consultation",
            )
        return RuleCheck(ok=False, rule=rule, why="no referral on file and no consultation with us")
    if svc.requires == "opg_recent":
        within = rule.within_days or 180
        recent = [
            d for s, d in visits(p, cal) if s == "opg" and on - timedelta(days=within) <= d <= on
        ]
        if recent:
            return RuleCheck(ok=True, rule=rule, why=f"OPG on {spoken_date(recent[0])}")
        return RuleCheck(ok=False, rule=rule, why="no OPG in the last six months")
    return RuleCheck(ok=True)


# ─── Cancellation and reschedule policy ──────────────────────────────────────


@dataclass(frozen=True)
class ChangeTerms:
    allowed: bool
    fee: int
    why: str


def change_terms(a: Appt, cal: Calendar, *, action: Literal["reschedule", "cancel"]) -> ChangeTerms:
    pol = DATA_.policies["cancellation"]
    svc = service(a.service)
    if a.status != "booked":
        return ChangeTerms(False, 0, "this appointment is already cancelled")
    if a.at() <= cal.now:
        return ChangeTerms(False, 0, "this appointment has already started or passed")
    if a.changes >= pol.online_changes_max:
        return ChangeTerms(
            False,
            0,
            f"it has already been changed online {a.changes} times; after "
            f"{pol.online_changes_max}, the desk arranges it by phone",
        )
    hours = (a.at() - cal.now).total_seconds() / 3600
    if svc is not None and svc.category == "imaging":
        if hours >= pol.imaging_free_until_hours:
            return ChangeTerms(
                True,
                0,
                f"free: scans can be changed up to {pol.imaging_free_until_hours} hours before",
            )
        return ChangeTerms(
            True, pol.late_fee, f"within {pol.imaging_free_until_hours} hours of the scan"
        )
    if hours >= pol.free_until_hours:
        return ChangeTerms(True, 0, f"free: more than {pol.free_until_hours} hours away")
    if a.service in pol.late_fee_waived_for:
        return ChangeTerms(True, 0, "the late-change fee is waived for emergency visits")
    return ChangeTerms(
        True,
        pol.late_fee,
        f"within {pol.free_until_hours} hours: a {rupees(pol.late_fee)} late-change fee",
    )


def sitting_window(a: Appt, cal: Calendar, p: Patient | None) -> tuple[date, date] | None:
    """For a root canal's later sitting: the dates it may move to (7 to 14
    days after the sitting before it)."""
    svc = service(a.service)
    if svc is None or svc.sitting_gap_days is None or not a.sitting or a.sitting <= 1 or p is None:
        return None
    before: date | None = None
    for v in p.history:
        if v.service == a.service and v.sitting == a.sitting - 1:
            before = date_of(cal.today, v.week, v.day)
    for o in cal.of_patient(p.id):
        if o.service == a.service and o.sitting == a.sitting - 1 and o.status == "booked":
            before = o.on
    if before is None:
        return None
    return before + timedelta(days=svc.sitting_gap_days.min), before + timedelta(
        days=svc.sitting_gap_days.max
    )


def moved(a: Appt, slot: Slot) -> Appt:
    return replace(
        a,
        on=slot.on,
        start=slot.start,
        branch=slot.branch,
        dentist=slot.dentist,
        chair=slot.chair,
        resource=slot.resource,
        changes=a.changes + 1,
    )


# ─── Matching what was said ───────────────────────────────────────────────────


def _fold(s: str) -> str:
    return " ".join("".join(ch if ch.isalnum() else " " for ch in s.casefold()).split())


def find_service(said: str) -> Service | None:
    want = _fold(said)
    for s in DATA_.services:
        if want in (s.id, _fold(s.name)):
            return s
    for s in DATA_.services:
        if any(_fold(w) == want for w in s.spoken):
            return s
    for s in DATA_.services:
        if any(_fold(w) in want or want in _fold(w) for w in s.spoken) or want in _fold(s.name):
            return s
    return None


def find_dentist(said: str) -> Dentist | None:
    want = _fold(said).replace("doctor ", "dr ")
    for d in DATA_.dentists:
        names = (d.id, _fold(d.name), _fold(d.short), _fold(d.id.replace("-", " ")))
        if want in names:
            return d
    for d in DATA_.dentists:
        words = set(_fold(d.name).split()) - {"dr"}
        if words & set(want.split()):
            return d
    return None


def find_branch(said: str) -> Branch | None:
    want = _fold(said)
    for b in DATA_.branches:
        if want in (b.id, _fold(b.short), _fold(b.name)) or _fold(b.short).split()[0] in want:
            return b
    return None


def parse_date(said: str, today: date) -> date | None:
    """ISO dates, 'today', 'tomorrow', a weekday name (the next one, today
    included), or '20 Nov'."""
    s = _fold(said)
    if not s:
        return None
    try:
        return date.fromisoformat(said.strip()[:10])
    except ValueError:
        pass
    if s in ("today", "aaj"):
        return today
    if s in ("tomorrow", "kal"):
        return today + timedelta(days=1)
    for i, name in enumerate(DAYS):
        full = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")[i]
        if s.split()[-1] in (name, full):
            ahead = (i - today.weekday()) % 7
            if s.startswith("next") and ahead == 0:
                ahead = 7
            return today + timedelta(days=ahead)
    for fmt in ("%d %b", "%d %B", "%b %d", "%B %d"):
        try:
            got = datetime.strptime(said.strip(), fmt).date().replace(year=today.year)
        except ValueError:
            continue
        return got if got >= today else got.replace(year=today.year + 1)
    return None


def parse_time(said: str) -> str | None:
    """'14:30', '2:30 pm', '2 pm', '11' → 'HH:MM' (a bare hour before 8 is pm)."""
    s = said.strip().lower().replace(".", ":").replace(" ", "")
    pm = s.endswith("pm")
    am = s.endswith("am")
    s = s.removesuffix("pm").removesuffix("am")
    try:
        h, m = [*s.split(":"), "0"][:2]
        hh, mm = int(h), int(m)
    except ValueError:
        return None
    if pm and hh < 12:
        hh += 12
    if not pm and not am and hh < 8:
        hh += 12
    if not (0 <= hh < 24 and 0 <= mm < 60):
        return None
    return f"{hh:02d}:{mm:02d}"


# ─── The page's fixtures ──────────────────────────────────────────────────────


def write_fixtures(path: Path = DATA / "slot_fixtures.json") -> None:
    """Slots for a fixed "now", for the page's test to match exactly."""
    now = datetime(2026, 11, 18, 10, 7, tzinfo=IST)  # a Wednesday morning
    cal = Calendar.build(now)
    cases: list[dict[str, object]] = []
    picks: Sequence[tuple[str, str | None, str | None, int]] = (
        ("consult", None, None, 0),
        ("emergency", "hsr", None, 0),
        ("rct", None, "dr-kavitha", 5),
        ("whitening", "indiranagar", None, 2),
        ("wisdom", None, "dr-sameer", 1),
        ("cbct", "indiranagar", None, 1),
        ("iopa", "hsr", None, 0),
        ("aligner", None, None, 5),
        ("scaling", "indiranagar", "dr-farah", 1),
    )
    for sid, bid, did, ahead in picks:
        svc = service(sid)
        assert svc is not None
        on = cal.today + timedelta(days=ahead)
        got = cal.slots(svc, on, branch_id=bid, dentist_id=did)
        cases.append(
            {
                "service": sid,
                "branch": bid,
                "dentist": did,
                "date": on.isoformat(),
                "slots": [
                    {
                        "time": s.time,
                        "branch": s.branch,
                        "dentist": s.dentist,
                        "chair": s.chair,
                        "resource": s.resource,
                    }
                    for s in got
                ],
            }
        )
    rct = service("rct")
    assert rct is not None
    first = cal.next_days(
        rct, dentist_id="dr-kavitha", start=cal.today + timedelta(days=5), days=1
    )[0][1][0]
    plan = cal.plan_sittings(rct, first)
    doc = {
        "$comment": "Written by backend/clinic.py write_fixtures(); the page's slot engine must give the same answers.",
        "now": now.isoformat(),
        "cases": cases,
        "rct_plan": {
            "first": {"date": first.on.isoformat(), "time": first.time, "branch": first.branch},
            "next": [{"date": s.on.isoformat(), "time": s.time, "branch": s.branch} for s in plan],
        },
    }
    path.write_text(json.dumps(doc, indent=1) + "\n")


if __name__ == "__main__":
    write_fixtures()
