"""The advisor's and counsellor's logic over the catalogue: matching a learner's
profile to programmes, a programme's facts, a comparison, an eligibility and
scholarship check, and the finder's facet labels the page ticks.

Every sentence here is built from ``data/*.json``; nothing is invented. The
tools in ``brain.py`` return these strings to the model.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from voqalize.sdk.stage import match_label

from .data import Catalogue, Program, admissions, catalogue, inr

# ─── Facets: the finder's sidebar, as the page labels it (CONTRACT.md) ──────


def facets(cat: Catalogue | None = None) -> dict[str, list[str]]:
    """Each facet's option labels, in the page's order."""
    c = cat or catalogue()
    return {
        "Level": [x.label for x in c.levels],
        "School": [s.short for s in c.schools],
        "Mode": [x.label for x in c.modes],
        "Campus": [x.name for x in c.campuses],
        "Fee": [b.label for b in c.fee_bands],
        "Hours": [b.label for b in c.hour_bands],
    }


def _fold(text: str) -> str:
    """Loose form for matching a spoken label: lower case, ₹ and dashes as words."""
    t = text.lower().replace("₹", " ").replace("\u2013", "-").replace("\u2014", "-")
    t = re.sub(r"\brs\.?\b|\brupees?\b|\binr\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def resolve_facet(facet: str, value: str) -> tuple[str, str] | None:
    """The page's ``(facet, option)`` for a spoken pair, or ``None``."""
    table = facets()
    name = match_label(facet, list(table)) or {
        "programme": "Level",
        "type": "Level",
        "area": "School",
        "subject": "School",
        "format": "Mode",
        "city": "Campus",
        "location": "Campus",
        "budget": "Fee",
        "fees": "Fee",
        "time": "Hours",
        "hours a week": "Hours",
    }.get(_fold(facet))
    if name is None:
        return None
    options = table[name]
    aliases = {
        "ug": "Undergraduate",
        "pg": "Postgraduate",
        "bachelor": "Undergraduate",
        "bachelors": "Undergraduate",
        "masters": "Postgraduate",
        "master": "Postgraduate",
        "full-time": "Full-time on campus",
        "full time": "Full-time on campus",
        "on campus": "Full-time on campus",
        "bangalore": "Bengaluru",
        "executive": "Online & Executive",
    }
    want = aliases.get(_fold(value), value)
    hit = match_label(want, options)
    if hit is None:
        folded = {_fold(o): o for o in options}
        hit = folded.get(_fold(want))
    return (name, hit) if hit is not None else None


def resolve_program(said: str) -> str | None:
    """A programme id for an id or a name as spoken, or ``None``."""
    c = catalogue()
    s = said.strip().lower()
    if c.program(s) is not None:
        return s
    by_name = {p.name: p.id for p in c.programs}
    hit = match_label(said, list(by_name))
    return by_name[hit] if hit is not None else None


# ─── Finding programmes ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class Profile:
    level: str | None = None
    school: str | None = None
    interests: str = ""
    mode: str | None = None
    campus: str | None = None
    max_fee_per_year: int | None = None
    hours_per_week: int | None = None


_WORD = re.compile(r"[a-z]+")
_STOP = frozenset(
    [
        "a",
        "an",
        "and",
        "the",
        "in",
        "of",
        "for",
        "to",
        "i",
        "want",
        "like",
        "my",
        "with",
        "or",
        "on",
        "be",
        "at",
        "is",
    ]
)


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 1}


#: Words that only name a level or the kind of programme: "an engineering B.Tech",
#: "undergraduate courses". They say nothing about which programme fits, so they
#: are not interests (U1: "Engineering." ranked civil, data science and EV first
#: because each name has "engineering" in it, and left computer science out).
_KIND_WORDS = frozenset(
    [
        "undergraduate",
        "postgraduate",
        "ug",
        "pg",
        "btech",
        "tech",
        "bachelor",
        "bachelors",
        "master",
        "masters",
        "degree",
        "degrees",
        "course",
        "courses",
        "programme",
        "programmes",
        "program",
        "programs",
        "diploma",
        "certificate",
        "few",
        "some",
        "explore",
        "options",
        "branch",
        "branches",
    ]
)


def _area_words(cat: Catalogue) -> frozenset[str]:
    """Words that name a school: "engineering", "business", "design", "law"..."""
    out: set[str] = set()
    for sc in cat.schools:
        out |= _words(f"{sc.id} {sc.short} {sc.name}")
    return frozenset(out - {"school", "varenya", "online"})


def interest_words(interests: str, cat: Catalogue | None = None) -> set[str]:
    """The words of ``interests`` that say what they want to study, not which
    area or level: what the match ranks on."""
    c = cat or catalogue()
    return _words(interests) - _KIND_WORDS - _area_words(c)


def _score(p: Program, wanted: set[str]) -> int:
    if not wanted:
        return 0
    tags = _words(" ".join(p.interests))
    name = _words(p.name + " " + " ".join(p.specialisations))
    body = _words(" ".join(p.modules) + " " + " ".join(p.outcomes.roles))
    return 3 * len(wanted & tags) + 2 * len(wanted & name) + len(wanted & body)


def matches(profile: Profile, cat: Catalogue | None = None) -> list[Program]:
    """Programmes that meet the hard limits, the best interest match first,
    then the lower fee."""
    c = cat or catalogue()
    out: list[Program] = []
    for p in c.programs:
        if profile.level and p.level != profile.level:
            continue
        if profile.school and p.school != profile.school:
            continue
        if profile.mode and p.mode != profile.mode:
            continue
        if profile.campus and profile.campus not in p.campuses:
            continue
        if profile.max_fee_per_year is not None and p.fee_per_year > profile.max_fee_per_year:
            continue
        if profile.hours_per_week is not None and p.hours_per_week > profile.hours_per_week:
            continue
        out.append(p)
    wanted = interest_words(profile.interests, c)
    return sorted(out, key=lambda p: (-_score(p, wanted), p.fee_per_year))


def suggested_filters(profile: Profile, cat: Catalogue | None = None) -> list[tuple[str, str]]:
    """The finder options that say this profile, in the order to tick them."""
    c = cat or catalogue()
    out: list[tuple[str, str]] = []
    if profile.level:
        out.append(("Level", c.level_label(profile.level)))
    if profile.school:
        out.append(("School", c.school(profile.school).short))
    if profile.mode:
        out.append(("Mode", c.mode_label(profile.mode)))
    if profile.campus:
        out.append(("Campus", c.campus_name(profile.campus)))
    if profile.max_fee_per_year is not None:
        out += [("Fee", b.label) for b in c.fee_bands if b.min <= profile.max_fee_per_year]
    if profile.hours_per_week is not None:
        out += [("Hours", b.label) for b in c.hour_bands if b.min <= profile.hours_per_week]
    return out


def next_deadline(p: Program, cat: Catalogue | None = None) -> str:
    intake = (cat or catalogue()).intakes[p.intake]
    first = intake.rounds[0]
    return f"{first.name}, apply by {first.deadline} (starts {intake.starts})"


def one_line(p: Program, cat: Catalogue | None = None) -> str:
    c = cat or catalogue()
    campuses = ", ".join(c.campus_name(x) for x in p.campuses)
    hours = "full-time" if p.hours_per_week >= 16 else f"about {p.hours_per_week} hrs a week"
    return (
        f"{p.id}: {p.name} — {c.level_label(p.level)}, {c.mode_label(p.mode)}, {campuses}, "
        f"{p.duration_label}, {inr(p.fee_per_year)} a year ({inr(p.fee_total)} in all), {hours}; "
        f"next: {next_deadline(p, c)}"
    )


def find_text(
    profile: Profile,
    ticked: Iterable[str] = (),
    picks: Sequence[str] = (),
) -> str:
    """What ``find_programs`` returns: the programmes that fit, the filters
    still to tick (``ticked``, as "Level: Undergraduate", are on screen
    already), and how to lead from here.

    Three shapes, by how much they said (U1):

    - only a level: the areas it has, with counts, to ask which;
    - an area but nothing more specific ("Engineering."): every programme of
      it, none picked yet, to ask which branch;
    - something specific: the best fits first, to pick two or three.
    """
    c = catalogue()
    found = matches(profile, c)
    on_screen = set(ticked)
    todo = [(f, v) for f, v in suggested_filters(profile, c) if f"{f}: {v}" not in on_screen]
    cues = " ".join(f"{{filter: {f} | {v}}}" for f, v in todo)
    already = (
        f" Already ticked on their screen (write no cue for these): {', '.join(sorted(on_screen))}."
        if on_screen
        else ""
    )
    tick = (
        f"Tick what is not on screen yet, one cue inside a natural sentence: {cues}."
        if cues
        else "Every filter for this is already ticked: write no filter cue."
    ) + already
    if not found:
        return (
            "No programme meets all of those limits. Say so plainly and offer to relax one "
            "(the budget, the hours or the mode), then call find_programs again."
        )
    specific = bool(interest_words(profile.interests, c))
    if not specific and profile.school is None:
        by_school: dict[str, int] = {}
        for p in found:
            by_school[p.school] = by_school.get(p.school, 0) + 1
        areas = "; ".join(f"{c.school(k).short} {n}" for k, n in by_school.items())
        return (
            f"{len(found)} programmes at this level, by area: {areas}.\n{tick}\n"
            "Pick nothing yet. In one or two sentences say the main areas (not the counts, "
            "not every area) and ask which one they want, or what they enjoy, so you can "
            "narrow it down."
        )
    lines = [one_line(p, c) for p in found[:6]]
    more = f" ({len(found) - 6} more not listed)" if len(found) > 6 else ""
    if not specific and len(found) <= 8:
        names = "; ".join(p.name for p in found)
        return (
            f"All {len(found)} programmes of this area at this level, cheapest first: "
            f"{names}.\n- " + "\n- ".join(lines) + f"\n{tick}\n"
            f"After the ticks all {len(found)} are listed on their screen. They named only the "
            "area, so pick nothing yet: say in one sentence that these are all on screen, name "
            "the branches in a few words each (computer science, electronics...), and ask which "
            "branch or what they enjoy (coding, machines, buildings...)."
        )
    held = (
        f" Your picks on screen now: {', '.join(picks)}. Keep them unless what they just said "
        "changes which fit best."
        if picks
        else ""
    )
    return (
        f"{len(found)} programmes meet the limits{more}, best fit first:\n- "
        + "\n- ".join(lines)
        + f"\n{tick}{held}\n"
        "Name the two or three that fit best with {pick: id | id}, one short sentence each on "
        "why, and offer to compare them or open one's page. Do not repeat back what they told "
        "you."
    )


#: A programme page's sections, as the page names them (``site.open``'s section).
SECTIONS = (
    "overview",
    "eligibility",
    "selection",
    "fees",
    "scholarships",
    "deadlines",
    "outcomes",
    "curriculum",
    "highlights",
)

#: Words a visitor or the model uses for a section.
_SECTION_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "curriculum",
        ("curriculum", "syllabus", "modules", "module", "subjects", "subject", "courses taught"),
    ),
    ("fees", ("fees", "fee", "cost", "costs", "tuition")),
    (
        "outcomes",
        (
            "placement",
            "placements",
            "salary",
            "salaries",
            "package",
            "jobs",
            "careers",
            "outcomes",
            "recruiters",
        ),
    ),
    ("eligibility", ("eligibility", "eligible", "qualify", "criteria", "requirements")),
    ("scholarships", ("scholarship", "scholarships", "waiver")),
    ("deadlines", ("deadline", "deadlines", "last date", "intake", "apply by")),
    ("selection", ("selection", "entrance", "interview", "admission process")),
    ("highlights", ("highlights", "special", "residency", "research track")),
    ("overview", ("overview", "about")),
)


def section_of(said: str) -> str | None:
    """The programme-page section ``said`` names, or ``None``."""
    low = f" {_fold(said)} "
    best: tuple[int, str] | None = None
    for name, words in _SECTION_WORDS:
        for w in words:
            at = low.find(f" {w}")
            if at >= 0 and (best is None or at < best[0]):
                best = (at, name)
    return best[1] if best else None


#: The nouns that name a section outright, for pointing at one unasked: a sentence
#: about "tuition" or "eligible women" is not about the fees or eligibility box.
_SECTION_NOUNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("curriculum", ("curriculum", "syllabus", "modules")),
    ("fees", ("fee ", "fees")),
    ("outcomes", ("placement", "placements", "median salary", "highest salary")),
    ("eligibility", ("eligibility",)),
    ("scholarships", ("scholarship", "scholarships")),
    ("deadlines", ("deadline", "deadlines")),
    ("highlights", ("highlights",)),
)


def section_named(sentence: str) -> str | None:
    """The programme-page section ``sentence`` names outright, first one said."""
    low = f" {_fold(sentence)} "
    best: tuple[int, str] | None = None
    for name, words in _SECTION_NOUNS:
        for w in words:
            at = low.find(f" {w}")
            if at >= 0 and (best is None or at < best[0]):
                best = (at, name)
    return best[1] if best else None


def section_text(p: Program, section: str) -> str:
    """The facts of one section of a programme's page, for the line about it."""
    c = catalogue()
    match section:
        case "curriculum":
            return f"Modules: {', '.join(p.modules)}."
        case "fees":
            return (
                f"Fees: {inr(p.fee_per_year)} a year, {inr(p.fee_total)} for the whole "
                f"programme; application fee {inr(p.application_fee)}. Hostel and mess are separate."
            )
        case "outcomes":
            o = p.outcomes
            bits = [
                f"{o.placement_pct}% placed" if o.placement_pct is not None else "",
                f"median salary {o.median_ctc_lpa:g} lakh a year" if o.median_ctc_lpa else "",
                f"highest {o.highest_ctc_lpa:g} lakh" if o.highest_ctc_lpa else "",
                o.note or "",
                f"roles: {', '.join(o.roles)}" if o.roles else "",
            ]
            return "Outcomes: " + ", ".join(b for b in bits if b) + "."
        case "eligibility":
            return f"Eligibility: {p.eligibility.needs}."
        case "scholarships":
            names = [s.name for s in (c.scholarship(x) for x in p.scholarships) if s is not None]
            return f"Scholarships: {', '.join(names) or 'none for this programme'}."
        case "deadlines":
            return f"Next deadline: {next_deadline(p, c)}."
        case "selection":
            return f"Entrance: {', '.join(p.entrance)}. Selection: {' → '.join(p.selection)}."
        case "highlights":
            return f"Highlights: {'; '.join(p.highlights)}."
        case _:
            return one_line(p, c)


def program_text(p: Program) -> str:
    """Every authored fact about one programme, for ``program_details``."""
    c = catalogue()
    school = c.school(p.school)
    intake = c.intakes[p.intake]
    rounds = "; ".join(
        f"{r.name} by {r.deadline}" + (f" ({r.note})" if r.note else "") for r in intake.rounds
    )
    schemes = [s for s in (c.scholarship(x) for x in p.scholarships) if s is not None]
    sch = "; ".join(
        f"{s.name} ({', '.join(f'{t.rule}: {t.waiver}% of tuition' for t in s.tiers)})"
        for s in schemes
    )
    o = p.outcomes
    outcome = ", ".join(
        x
        for x in (
            f"{o.placement_pct}% placed" if o.placement_pct is not None else "",
            f"median salary {o.median_ctc_lpa:g} lakh a year" if o.median_ctc_lpa else "",
            f"highest {o.highest_ctc_lpa:g} lakh" if o.highest_ctc_lpa else "",
            o.note or "",
            f"roles: {', '.join(o.roles)}" if o.roles else "",
        )
        if x
    )
    e = p.eligibility
    exp = f"; {e.min_experience_years} years' work experience" if e.min_experience_years else ""
    return "\n".join(
        [
            f"{p.name} ({p.id}), {school.name}.",
            f"Level {c.level_label(p.level)}; {c.mode_label(p.mode)}; campuses "
            f"{', '.join(c.campus_name(x) for x in p.campuses)}; {p.duration_label}; "
            f"{p.hours_per_week if p.hours_per_week < 16 else 'full-time,'} "
            f"{'hrs a week' if p.hours_per_week < 16 else 'on campus'}; {p.seats} seats.",
            f"Fees: {inr(p.fee_per_year)} a year, {inr(p.fee_total)} for the whole programme; "
            f"application fee {inr(p.application_fee)}. Hostel and mess are separate.",
            f"Eligibility: {e.needs}{exp}.",
            f"Entrance: {', '.join(p.entrance)}. Selection: {' → '.join(p.selection)}.",
            f"Intake {intake.label}, starts {intake.starts}. Deadlines: {rounds}.",
            f"Scholarships: {sch or 'none for this programme'}.",
            f"Outcomes: {outcome}.",
            f"Highlights: {'; '.join(p.highlights)}. Modules: {', '.join(p.modules)}.",
        ]
    )


_ROWS = (
    "Duration",
    "Mode",
    "Campus",
    "Fee per year",
    "Total fee",
    "Hours a week",
    "Eligibility",
    "Next deadline",
    "Outcome",
)


def compare_text(programs: Sequence[Program]) -> str:
    """A side-by-side comparison, row by row, for ``compare_programs``."""
    c = catalogue()

    def cell(p: Program, row: str) -> str:
        o = p.outcomes
        match row:
            case "Duration":
                return p.duration_label
            case "Mode":
                return c.mode_label(p.mode)
            case "Campus":
                return ", ".join(c.campus_name(x) for x in p.campuses)
            case "Fee per year":
                return inr(p.fee_per_year)
            case "Total fee":
                return inr(p.fee_total)
            case "Hours a week":
                return "full-time" if p.hours_per_week >= 16 else str(p.hours_per_week)
            case "Eligibility":
                return p.eligibility.needs
            case "Next deadline":
                return next_deadline(p, c)
            case _:
                if o.placement_pct is not None:
                    pay = f", median {o.median_ctc_lpa:g} lakh" if o.median_ctc_lpa else ""
                    return f"{o.placement_pct}% placed{pay}"
                return o.note or "—"

    head = " | ".join(f"{p.id} ({p.name})" for p in programs)
    rows = [f"{row}: " + " | ".join(cell(p, row) for p in programs) for row in _ROWS]
    return f"Compared, in this order: {head}\n" + "\n".join(rows)


# ─── Eligibility and scholarships ───────────────────────────────────────────


@dataclass(frozen=True)
class Applicant:
    class12_stream: str | None = None
    class12_percent: float | None = None
    graduation_percent: float | None = None
    experience_years: float | None = None
    vusat_rank: int | None = None
    family_income_lakh: float | None = None
    gender: str | None = None
    sports: str | None = None  # "national" | "state"
    defence_family: bool = False


def _tier(waivers: Iterable[tuple[bool, int]]) -> int:
    return max((w for ok, w in waivers if ok), default=0)


def scholarship_waivers(p: Program, a: Applicant) -> list[tuple[str, int]]:
    """Each of the programme's schemes this applicant qualifies for, with its %."""
    out: list[tuple[str, int]] = []
    for sid in p.scholarships:
        pct = 0
        if sid == "merit-12" and a.class12_percent is not None:
            m = a.class12_percent
            pct = _tier(((m >= 95, 50), (90 <= m < 95, 25), (85 <= m < 90, 10)))
        elif sid == "vusat-rank" and a.vusat_rank is not None:
            r = a.vusat_rank
            pct = _tier(((r <= 100, 75), (100 < r <= 500, 40), (500 < r <= 1500, 20)))
        elif sid == "pg-merit" and a.graduation_percent is not None:
            g = a.graduation_percent
            pct = _tier(((g >= 80, 25), (70 <= g < 80, 10)))
        elif sid == "udaan" and a.family_income_lakh is not None:
            i = a.family_income_lakh
            pct = _tier(((i < 4, 60), (4 <= i <= 8, 30)))
        elif sid == "women-stem" and (a.gender or "").lower() in ("female", "woman", "girl"):
            pct = 20
        elif sid == "sports" and a.sports:
            pct = {"national": 50, "state": 20}.get(a.sports.lower(), 0)
        elif sid == "defence" and a.defence_family:
            pct = 15
        if pct:
            out.append((sid, pct))
    return out


def eligibility_text(p: Program, a: Applicant) -> str:
    """Whether this applicant meets the programme's published bar, and the
    scholarship that would apply, worked out from the authored rules."""
    c = catalogue()
    e = p.eligibility
    problems: list[str] = []
    unknown: list[str] = []
    if e.requires == "class12":
        if e.streams and a.class12_stream is not None and a.class12_stream not in e.streams:
            problems.append(f"needs {e.needs}; their stream is {a.class12_stream}")
        if a.class12_stream is None and e.streams and len(e.streams) < 5:
            unknown.append("Class 12 stream")
        if a.class12_percent is None and e.min_percent:
            unknown.append("Class 12 marks")
        elif a.class12_percent is not None and a.class12_percent < e.min_percent:
            problems.append(
                f"needs {e.min_percent:g}% in Class 12; they have {a.class12_percent:g}%"
            )
    else:
        if a.graduation_percent is None and e.min_percent:
            unknown.append("graduation marks")
        elif a.graduation_percent is not None and a.graduation_percent < e.min_percent:
            problems.append(
                f"needs {e.min_percent:g}% in graduation; they have {a.graduation_percent:g}%"
            )
    if e.min_experience_years:
        if a.experience_years is None:
            unknown.append("years of work experience")
        elif a.experience_years < e.min_experience_years:
            problems.append(f"needs {e.min_experience_years} years' work experience")
    if problems:
        verdict = "NOT eligible: " + "; ".join(problems) + "."
    elif unknown:
        verdict = f"Eligible so far ({e.needs}); still to confirm: {', '.join(unknown)}."
    else:
        verdict = f"Eligible: meets {e.needs}."
    found = scholarship_waivers(p, a)
    stem = next((w for s, w in found if s == "women-stem"), 0)
    others = [(s, w) for s, w in found if s != "women-stem"]
    best = max(others, key=lambda x: x[1], default=None)
    parts = ([best] if best else []) + ([("women-stem", stem)] if stem else [])
    total = min(75, sum(w for _, w in parts))
    if total:
        schemes_used = (c.scholarship(s) for s, _ in parts)
        named = " + ".join(s.name for s in schemes_used if s is not None)
        saving = p.fee_per_year * total // 100
        sch = (
            f"Scholarship: {named}, {total}% of tuition — {inr(saving)} off each year, so "
            f"{inr(p.fee_per_year - saving)} a year instead of {inr(p.fee_per_year)} "
            "(confirmed with the offer; kept with a CGPA of 7.5 or above)."
        )
    else:
        schemes = ", ".join(n.name for n in (c.scholarship(x) for x in p.scholarships) if n)
        sch = (
            f"No scholarship from what they have said. Schemes on this programme: "
            f"{schemes or 'none'}."
        )
    return f"{p.name} ({p.id}): {verdict}\n{sch}"


# ─── The authored admissions content, for the prompt ────────────────────────


def admissions_brief() -> str:
    """The counsellor's reference: process, VUSAT, fees, hostel, loans,
    scholarships, documents and FAQs — all of ``admissions.json``."""
    a = admissions()
    c = catalogue()
    fees = a["fees"]
    hostel = a["hostel"]
    loans = a["loans"]
    lines: list[str] = ["## Process"]
    lines += [f"{s['step']}. {s['title']}: {s['text']}" for s in a["process"]]
    au = a["vusat"]
    lines += [
        f"## {au['name']}",
        au["format"],
        "; ".join(
            f"{x['name']} {x['dates']} (register by {x['register_by']})" for x in au["phases"]
        )
        + ". "
        + au["note"],
        "## Fees",
        fees["what_is_included"],
        "One-time: "
        + "; ".join(
            f"{x['item']} {inr(x['amount'])}{' (refundable)' if x['refundable'] else ''}"
            for x in fees["one_time"]
        )
        + ".",
        f"Seat confirmation: {fees['seat_confirmation']}",
        f"Instalments: {fees['instalments']} {fees['zero_interest_plan']}",
        f"Refund: {fees['refund']}",
        f"Payment: {fees['payment_methods']}",
        "## Hostel",
        hostel["summary"],
        "Rooms a year: "
        + "; ".join(
            f"{c.campus_name(r['campus'])} {r['label']} {inr(r['per_year'])}"
            for r in hostel["rooms"]
        )
        + f". Refundable deposit {inr(hostel['deposit'])}.",
        hostel["allotment"],
        hostel["rules"],
        "## Education loans",
        f"{loans['summary']} {loans['covers']} {loans['timeline']} {loans['who_decides']} "
        f"Contact: {loans['contact']}.",
        "## Scholarships",
    ]
    for s in c.scholarships:
        tiers = "; ".join(f"{t.rule}: {t.waiver}%" for t in s.tiers)
        lines.append(f"- {s.id}: {s.name} — for {s.applies_to}; basis: {s.basis}; {tiers}.")
    lines += a["scholarship_rules"]
    lines += ["## Documents"]
    lines += [f"- {d['id']}: {d['label']} ({d['for']})" for d in a["documents"]]
    lines += ["## FAQs"]
    lines += [f"Q: {f['q']} A: {f['a']}" for f in a["faqs"]]
    ct = a["contact"]
    lines += [
        f"## Contact: {ct['phone']}, {ct['email']}, {ct['hours']}; WhatsApp {ct['whatsapp']}."
    ]
    lines += ["## Intakes"]
    lines += [
        f"- {k}: {v.label}, starts {v.starts}; "
        + "; ".join(f"{r.name} by {r.deadline}" for r in v.rounds)
        for k, v in c.intakes.items()
    ]
    return "\n".join(lines)


def catalogue_brief() -> str:
    """Every programme in one line each, for the prompt."""
    return "\n".join(one_line(p) for p in catalogue().programs)
