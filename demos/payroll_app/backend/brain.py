"""TankoraBrain — the in-app agent of Tankora, a fictional Indian HR and payroll app.

An :class:`~voqalize.sdk.openai.OpenAIBrain`. The admin of Banyan & Bay Foods
(a fictional customer) is signed in; the agent talks and drives her screen with
Stage (``frontend/src/stage/scene.json``). One brain, three jobs, picked by the
page the call starts on (``init.landing``) and followed as the admin moves:

- **Onboarding guide** on ``/welcome``: the setup wizard, filled step by step
  on screen (:meth:`setup_step`), asking before each next step, ending with a
  February 2026 test payroll whose totals equal the draft run.
- **In-app support** on ``/`` and ``/help``: explains a payslip line by line
  against the month before (:meth:`explain_net_pay`), makes changes after a
  spoken yes (leave, claims, a new joiner), and hands off to a person with a
  written ticket shown on screen.
- **Feature coach** anywhere else: opens the screen for a task and rings its
  controls in turn (:meth:`open_feature`), compares both tax regimes slab by
  slab from the engine (:meth:`compare_regimes`), and switches after a yes.

**Every number is the engine's or the data's.** The session starts from a
fresh copy of ``data/company.json`` (:class:`.books.Books`); the admin's clicks
come back as Stage state events and the agent's own confirmed moves are applied
when the page reports them ``applied``, each with the same recomputation rules
the page's store uses (``CONTRACT.md``), so the voice and the screen agree.

**A change is never a cue.** Tools that change anything only ask
(:mod:`.confirm`); the admin's yes is classified before the model runs and the
brain sends the confirmed move itself, then says the page's answer once.

**English or Hindi**: from the toggle in ``init``, both legs configured in
``on_session_start`` from ``persona.json``; switched mid-call by the toggle, by
``set_language``, or when she speaks Hindi.
"""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator, Callable, Sequence
from typing import Any, Literal

from loguru import logger
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from voqalize_demos import PATIENCE, FallbackLine, configure_soon, landed, needs_result_now

from voqalize.sdk import (
    AppEvents,
    RequestRejected,
    RTVIMessage,
    Session,
    Speech,
    UserIdle,
    UserMessage,
)
from voqalize.sdk.openai import OpenAIBrain
from voqalize.sdk.stage import AutoCue, Mirror, Stage
from voqalize.sdk.stage.wire import StageEvent, StageHello, StageProgress, StageResult
from voqalize.sdk.wire import Config, IdleConfig, Language, SttConfig, TtsConfig, Voice

from . import payroll_engine as eng
from .app_events import LanguageChanged, LanguageRequested
from .books import (
    COMPANY,
    DRAFT_ID,
    FEB_KEY,
    FY_KEYS,
    Books,
    Changed,
    day,
    import_summary,
    inr,
    month_label,
    test_payroll,
)
from .confirm import Acted, Confirmations, Pending, classify
from .persona import PERSONA
from .prompt import JOB_NOTE, TOGGLE_CONFIRM, Lang, Mode, greeting, mode_for, system_instruction
from .stage_gen import MOVES, SPEC, ReadRequest

MODEL = "gpt-6-sol"
REASONING = "medium"

#: Every event the page sends: the language toggle and Stage's own.
_EVENTS = AppEvents(LanguageRequested, StageResult, StageHello, StageProgress, StageEvent)

#: A quiet admin is reading her screen: the agent stays quiet unless the page
#: left her something to say.
_IDLE_MS = 15_000
#: A line the brain already knows (a change's outcome): said as soon as the voice is free.
_SAY_NOW_MS = 400
_REACT_IDLE_MS = 1_500

#: The spoken line while a confirmed move is sent, per language.
HELD: dict[Lang, str] = {"en": "On it.", "hi": "जी, कर रही हूँ।"}

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_HINDI_GRAMMAR = (
    "hai hain hoon kya mein mujhe chahiye karo kariye karna dikhao batao bataiye aap nahi "
    "kaise kitna kitne kyun kyon wala wali liye bhi aur yeh woh accha haan ka ki ke ko se "
    "baat karein kijiye boliye samjhaiye"
)
_HINDI_WORDS = frozenset(_HINDI_GRAMMAR.split())


def _sounds_hindi(text: str) -> bool:
    """Devanagari, or two different Hindi grammar words in Latin letters."""
    if _DEVANAGARI.search(text):
        return True
    words = set(re.findall(r"[a-z]+", text.lower()))
    return len(words & _HINDI_WORDS) >= 2


def _voice(voice_id: str) -> Voice | str:
    """The persona's voice as the catalog member when there is one (understood
    by every Voqalize), else its id string."""
    try:
        return Voice(voice_id)
    except ValueError:
        return voice_id


def _language(tag: str) -> Language | str:
    try:
        return Language(tag)
    except ValueError:
        return tag


def _not_done(why: str, what: str) -> str:
    return f"NOT DONE — {why}. {what}"


# ─── The coach's guide: which screen does a task, and its controls in order ────

Feature = Literal[
    "regime_switch",
    "approve_leave",
    "review_claims",
    "run_payroll",
    "add_employee",
    "compare_payslips",
    "submit_proofs",
    "form16",
    "hand_off",
    "setup",
]

#: Authored: a task → its screen (``{employee}`` filled in) and the controls on
#: it, each by the label the screen marks (``data-stage-label``) and what it does.
GUIDE: dict[Feature, tuple[str, str, tuple[tuple[str, str], ...]]] = {
    "regime_switch": (
        "/tax/regime/{employee}",
        "Regime comparison",
        (
            ("Employee picker", "choose whose tax to look at"),
            ("New regime", "the year's tax under the new regime, step by step"),
            ("Old regime", "the same year under the old regime, with deductions"),
            ("Old regime slabs", "the old regime's slabs: income in each band and its tax"),
            ("TDS for months left", "February's TDS either way, spread over the months left"),
            ("Switch regime", "changes the regime used for TDS; asks before it saves"),
        ),
    ),
    "approve_leave": (
        "/leave?tab=requests",
        "Leave requests",
        (
            ("Pending requests", "requests waiting for a decision, with the balance left"),
            ("Approve", "approves; days beyond the balance become loss of pay in the draft"),
            ("Reject", "rejects with a reason the employee sees"),
            ("Balances", "everyone's earned, casual and sick leave left"),
        ),
    ),
    "review_claims": (
        "/reimbursements",
        "Reimbursements",
        (
            ("Claims to review", "pending claims and the ones that need a fix"),
            ("Bill amount", "what the bill says, beside what was claimed"),
            ("Fix amount", "sets the claim to the bill's amount and approves it"),
        ),
    ),
    "run_payroll": (
        f"/payroll/{DRAFT_ID}",
        "February 2026 draft run",
        (
            ("Review checklist", "pending leave, claims and proofs to clear first"),
            ("Payroll register", "every employee's pay lines for the month"),
            ("Run totals", "gross, deductions, TDS and net pay for the run"),
            ("Approve run", "locks the run for payment; only you can press it"),
        ),
    ),
    "add_employee": (
        "/employees/new",
        "Add employee",
        (
            ("Personal details", "name, email and gender"),
            ("Job", "department, title, grade, location and joining date"),
            ("Salary", "annual CTC; the structure follows the company rule"),
            ("February pay preview", "the prorated February pay from the joining date"),
            ("Save", "adds them and their pay to the February draft"),
        ),
    ),
    "compare_payslips": (
        "/payslips/{employee}/2026-01?against=2025-12",
        "Payslip comparison",
        (
            ("Employee picker", "whose payslip"),
            ("Difference", "each line's change from the month before"),
            ("Net pay", "what reached the bank"),
        ),
    ),
    "submit_proofs": (
        "/tax?tab=declarations",
        "Declarations and proofs",
        (
            ("Declarations", "what each employee declared in April"),
            ("Proof status", "verified, partly verified or not submitted, per item"),
        ),
    ),
    "form16": (
        "/tax?tab=form16",
        "Form 16",
        (("Form 16", "issued for FY 2024-25; FY 2025-26 comes after the March run"),),
    ),
    "hand_off": (
        "/help",
        "Help centre",
        (
            ("Hand-off ticket", "the written summary our payroll team reads"),
            ("Send ticket", "sends it; you get a TK number"),
        ),
    ),
    "setup": (
        "/welcome",
        "Setup",
        (
            ("Company details", "legal name, PAN, TAN and registrations"),
            ("Pay structure", "how CTC splits into basic, HRA, LTA and special"),
            ("Import employees", "your employee file, checked row by row"),
            ("Leave policy", "earned, casual and sick leave"),
            ("Test payroll", "a full February run on the imported data"),
        ),
    ),
}

#: The labels each kind of screen marks, for the backstop that rings what a
#: sentence names when the model wrote no cue. Each label with the words that name it.
SCREEN_LABELS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "payslip": (
        ("Loss of pay", ("loss of pay", "lop", "unpaid leave", "leave without pay")),
        ("TDS", ("tds", "tax deducted", "income tax")),
        ("Reimbursements", ("reimbursement",)),
        ("Net pay", ("net pay", "take-home", "take home")),
        ("Gross", ("gross",)),
        ("Professional tax", ("professional tax",)),
        ("Provident fund", ("provident fund", " pf ")),
    ),
    "regime": (
        ("Old regime slabs", ("old regime slab", "slab")),
        ("Deductions", ("deduction", "80c", "80d", "nps")),
        ("TDS for months left", ("tds", "months left")),
        ("Switch regime", ("switch",)),
        ("Old regime", ("old regime",)),
        ("New regime", ("new regime",)),
    ),
}


def _screen_kind(path: str) -> str | None:
    if path.startswith("/payslips/") or ("/payslips" in path and path.startswith("/me/")):
        return "payslip"
    if path.startswith("/tax/regime/") or (path.startswith("/me/") and path.endswith("/tax")):
        return "regime"
    return None


# ─── Tool parameters ───────────────────────────────────────────────────────────


class EmployeeRef(BaseModel):
    employee: str = Field(description="The employee's name as said (Ravi Kumar), or id (BB-1030).")


class NetPayRequest(BaseModel):
    employee: str = Field(description="The employee's name or id.")
    month: str | None = Field(
        default=None,
        description="The payslip month, 2026-01. Leave empty for the latest paid payslip.",
    )


class FeatureRequest(BaseModel):
    feature: Feature = Field(description="The task she asked how to do.")
    employee: str | None = Field(
        default=None, description="Whose record, when the task is about one employee."
    )


class LeaveRequest(BaseModel):
    request: str = Field(description="The leave request id (LV-2412) or the employee's name.")
    decision: Literal["approve", "reject"]


class ClaimRef(BaseModel):
    claim: str = Field(description="The claim id (RB-3108) or the employee's name.")


class ClaimDecision(BaseModel):
    claim: str = Field(description="The claim id (RB-3109) or the employee's name.")
    decision: Literal["approve", "reject"]


Location = Literal["Bengaluru", "Mumbai", "Pune", "New Delhi", "Hyderabad"]
Department = Literal[
    "Customer Support",
    "Engineering",
    "Finance and HR",
    "Leadership",
    "Marketing",
    "Operations",
    "Product and Design",
    "Sales",
]


class NewEmployee(BaseModel):
    name: str
    title: str = Field(description="Their designation, as said.")
    department: Department
    location: Location
    joined: str = Field(description="Joining date, 2026-02-16.")
    annual_ctc: int = Field(description="Annual CTC in rupees: 7.2 lakh is 720000.")
    gender: Literal["F", "M"]
    grade: Literal["G1", "G2", "G3", "G4", "G5", "G6", "G7"] = "G2"
    tax_regime: Literal["new", "old"] = "new"


class RegimeRequest(BaseModel):
    employee: str = Field(description="The employee's name or id.")
    regime: Literal["new", "old"]


class HandOff(BaseModel):
    subject: str = Field(description="A short subject line.")
    summary: str = Field(
        description=(
            "The written summary the payroll team reads: what she asked, what you found "
            "(with the numbers the tools gave), and what is needed. Three or four sentences."
        )
    )
    employee: str | None = Field(default=None, description="The employee it is about, if any.")


class SetupStep(BaseModel):
    step: Literal["company", "structure", "import", "leave", "test_run", "done"]


class ViewAs(BaseModel):
    employee: str
    tab: Literal["payslips", "tax", "declarations", "leave"] = "payslips"


class LanguageRequest(BaseModel):
    language: Literal["en", "hi"]


class ConfirmRequest(BaseModel):
    kind: str | None = Field(
        default=None,
        description="Leave empty: the question you just asked is the one she said yes to.",
    )


# ─── The brain ─────────────────────────────────────────────────────────────────


class TankoraBrain(OpenAIBrain):
    """One per session: the company's books, the job, the language, the screen."""

    def __init__(self, *, client: AsyncOpenAI, model: str = MODEL) -> None:
        super().__init__(
            client=client,
            system_instruction=system_instruction(),
            model=model,
            reasoning=REASONING,
        )
        self.books = Books()
        self.mode: Mode = "support"
        self.lang: Lang = PERSONA.default_language  # type: ignore[assignment]
        self.path = "/"
        self.turns = 0
        self.confirms = Confirmations()
        for kind, act in (
            ("leave", self._act_leave),
            ("fix_claim", self._act_fix_claim),
            ("claim", self._act_claim),
            ("employee", self._act_employee),
            ("regime", self._act_regime),
            ("ticket", self._act_ticket),
            ("setup_finish", self._act_setup_finish),
        ):
            self.confirms.register(kind, act)
        #: What each confirmed move does to the books once the page says it
        #: landed, returning the line that says so; by call_ref.
        self._effects: dict[str, Callable[[str | None], str]] = {}
        self._said: dict[str, str] = {}
        self.stage = Stage(
            dispatch=lambda a: self.session.dispatch(a),
            moves=MOVES,
            mirror=Mirror(SPEC),
            backstop=self._backstop,
        )
        self._fallback = FallbackLine()
        self._say_next: Callable[[], str] | None = None
        self._talk: str | None = None
        self._confirm_line: str | None = None
        self.setup_done: set[str] = set()

    # ─── Session ────────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        init = session.init or {}
        self.path = "/" + str(init.get("landing") or "/").strip("/")
        self.mode = mode_for(self.path)
        lang = str(init.get("lang") or PERSONA.default_language)
        self.lang = lang if lang in PERSONA.languages else PERSONA.default_language  # type: ignore[assignment]
        await session.configure(
            Config(
                stt=SttConfig(language=_language(self.lang), patience=PATIENCE),
                tts=TtsConfig(
                    voice=_voice(PERSONA.voice(self.lang)), language=_language(self.lang)
                ),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
            )
        )
        self.append_note(JOB_NOTE[self.mode] + f" [They are on {self.path}.]")
        self.append_note(self._language_note())
        logger.info("payroll_app: session on {} as {} in {}", self.path, self.mode, self.lang)

    async def greet(self, session: Session) -> str:
        return greeting(self.mode, self.lang)

    def _language_note(self) -> str:
        return f"[The call is in {PERSONA.labels[self.lang]}.]"

    def _speaking(self, lang: Lang) -> Config:
        """Both legs of ``lang``, and the toggle moved to it."""
        if lang != self.lang:
            self.session.dispatch(LanguageChanged(language=lang))
        self.lang = lang
        return Config(
            stt=SttConfig(language=_language(lang), patience=PATIENCE),
            tts=TtsConfig(voice=_voice(PERSONA.voice(lang)), language=_language(lang)),
        )

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[Speech, None]:
        self.turns += 1
        self.stage.visitor_spoke()
        self._talk = None
        self._settle_expired()
        if self.lang != "hi" and "hi" in PERSONA.languages and _sounds_hindi(msg.text):
            await session.configure(self._speaking("hi"))
            self.append_note("[She spoke Hindi: the call is now in Hindi.]")
            logger.info("payroll_app: language -> hi (heard)")
        pending = self.confirms.due(self.turns)
        answer = classify(msg.text) if pending is not None else None
        self.append_note(msg.text)
        if pending is not None and answer == "yes":
            acted = self.confirms.act(pending)
            self.append_note(acted.note)
            async for speech in self.say_line(acted.line, remember=True):
                yield speech
            return
        if pending is not None and answer == "no":
            self.confirms.clear()
            self.append_note(f"[She said no to: {pending.label}. Nothing was changed.]")
        async for speech in self.respond(session):
            yield speech

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        if (line := self._confirm_line) is not None:
            self._confirm_line = None
            async for speech in self.say_line(line):
                yield speech
        turn = self.stage.cued(super().respond(session))
        async for speech in self._fallback.speak_if_silent(self, turn):
            yield speech
        self.stage.end_turn()

    def on_user_idle(self, session: Session, idle: UserIdle) -> AsyncGenerator[Speech, None]:
        return self._idle(session)

    async def _idle(self, session: Session) -> AsyncGenerator[Speech, None]:
        self._settle_expired()
        say, self._say_next = self._say_next, None
        ask, self._talk = self._talk, None
        configure_soon(session, Config(idle=IdleConfig(timeout_ms=_IDLE_MS)))
        if say is not None:
            async for speech in self.say_line(say(), remember=True):
                yield speech
            return
        if self._confirm_line is not None:
            line, self._confirm_line = self._confirm_line, None
            async for speech in self.say_line(line):
                yield speech
            return
        if ask is None:
            return
        self.append_note(f"[{ask}]")
        async for speech in self.respond(session):
            yield speech

    def _say_line_soon(self, line: str | Callable[[], str]) -> None:
        self._say_next = line if callable(line) else (lambda: line)
        configure_soon(self.session, Config(idle=IdleConfig(timeout_ms=_SAY_NOW_MS)))

    # ─── Page → brain ───────────────────────────────────────────────────

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        event = _EVENTS.parse(msg)
        if event is None:
            return
        if isinstance(event, LanguageRequested):
            await self._requested(session, event.language)
            return
        if isinstance(event, StageHello):
            self.stage.handle(event)
            return
        if isinstance(event, StageProgress):
            self.stage.handle(event)
            return
        if isinstance(event, StageResult):
            result = self.stage.handle(event)
            if result is not None and (note := self._settle(result)) is not None:
                self.append_note(note)
            return
        folded = self.stage.handle(event)
        note = self._apply(event)
        if event.by == "visitor":
            if note is not None:
                logger.info("payroll_app: admin {}", note)
                self.append_note(note)
            elif folded is not None and folded.note:
                self.append_note(f"[{folded.note}]")
            if ask := self.stage.take_reaction():
                self._talk = ask
                configure_soon(self.session, Config(idle=IdleConfig(timeout_ms=_REACT_IDLE_MS)))

    async def _requested(self, session: Session, lang: Literal["en", "hi"]) -> None:
        """The toggle: both legs in one awaited request, a written line in the
        new language at the next turn or quiet spell."""
        if lang == self.lang or lang not in PERSONA.languages:
            return
        was = self.lang
        try:
            await session.configure(self._speaking(lang))
        except RequestRejected as rejected:
            logger.warning("payroll_app: switch to {} refused: {}", lang, rejected)
            self.lang = was
            self.session.dispatch(LanguageChanged(language=was))
            return
        logger.info("payroll_app: language -> {} (toggle)", lang)
        self._confirm_line = TOGGLE_CONFIRM[lang]
        configure_soon(session, Config(idle=IdleConfig(timeout_ms=_REACT_IDLE_MS)))
        self.append_note(f"[She switched the call to {PERSONA.labels[lang]} on the toggle.]")

    def _apply(self, event: StageEvent) -> str | None:
        """A page state event: the screen it shows, or a change the admin made
        by hand, applied to the books with the page's own rules. The agent's
        own changes are applied when their move's result lands, not here."""
        data = event.data
        if event.name == "screen.viewed":
            self._moved_to(str(data.get("path") or "/"), by=event.by)
            return None
        if event.by != "visitor":
            return None
        b = self.books
        match event.name:
            case "leave.decided":
                rid, decision = str(data.get("request_id")), str(data.get("decision"))
                if decision in ("approve", "reject"):
                    changed = b.decide_leave(rid, "approve" if decision == "approve" else "reject")
                    return f"[She {decision}d {rid} by hand.{self._impact(changed)}]"
            case "claim.changed":
                cid, status = str(data.get("claim_id")), str(data.get("status"))
                c = b.claim(cid)
                if c is not None and status == "approved":
                    amount = data.get("amount")
                    changed = (
                        b.fix_claim(cid, int(amount))
                        if amount is not None and int(amount) != int(c["amount"])
                        else b.decide_claim(cid, "approve")
                    )
                    return f"[She approved claim {cid} by hand.{self._impact(changed)}]"
                if c is not None and status == "rejected":
                    b.decide_claim(cid, "reject")
                    return f"[She rejected claim {cid} by hand.]"
            case "regime.switched":
                eid, regime = str(data.get("employee_id")), str(data.get("regime"))
                if regime in ("new", "old"):
                    changed = b.switch_regime(eid, "old" if regime == "old" else "new")
                    return f"[She switched {b.name(eid)} to the {regime} regime by hand.{self._impact(changed)}]"
            case "employee.added":
                if b.employee(str(data.get("employee_id"))) is None:
                    e, slip = b.add_employee({**data, "id": data.get("employee_id")})
                    return (
                        f"[She added {e['name']} ({e['id']}) by hand: prorated February "
                        f"net pay {inr(slip['net_pay'])}.]"
                    )
            case "ticket.created":
                tid = str(data.get("ticket_id"))
                b.add_ticket(str(data.get("subject") or ""), "", tid)
                return f"[She sent ticket {tid} by hand.]"
            case "run.approved":
                run = b.run(str(data.get("run_id")))
                if run is not None:
                    run["status"] = "approved"
                return f"[She approved the payroll run {data.get('run_id')}. It is locked for payment.]"
            case "setup.changed":
                return None
            case _:
                return None
        return None

    def _moved_to(self, path: str, *, by: str) -> None:
        self.path = "/" + path.strip("/")
        if by != "visitor":
            return
        mode = mode_for(self.path)
        if mode != self.mode:
            self.mode = mode
            self.append_note(JOB_NOTE[mode] + f" [She moved to {self.path}.]")

    # ─── Stage results ──────────────────────────────────────────────────

    def _settle_expired(self) -> None:
        for result in self.stage.expire():
            if (note := self._settle(result)) is not None:
                self.append_note(note)

    def _settle(self, result: StageResult) -> str | None:
        """A confirmed act's outcome is applied and said once; a move that did
        not land is told to the model with what the page offers instead."""
        ref = result.call_ref
        if self.confirms.is_flight(ref):
            why = "; ".join(r.why for r in result.refused)
            if result.outcome in ("applied", "partial") and (
                effect := self._effects.pop(ref, None)
            ):
                self._said[ref] = effect(result.detail)
            line = self.confirms.outcome(ref, result.outcome, result.detail, why)
            self._say_line_soon(line)
            return f"[The page answered: {result.outcome} — {result.detail or why or 'no detail'}.]"
        if result.moved or result.outcome in ("applied", "partial", "undone"):
            return None
        offers = "; ".join(
            f"{r.arg}: {r.why}" + (f" (options: {', '.join(r.options)})" if r.options else "")
            for r in result.refused
        )
        return (
            f"[Your {result.move} did not land ({result.detail or result.outcome}"
            + (f"; {offers}" if offers else "")
            + "). Never say it did; use one of the options, or ask.]"
        )

    def _backstop(
        self, sentence: str, index: int, placed: tuple[tuple[str, tuple[str, ...]], ...]
    ) -> Sequence[AutoCue]:
        """A sentence naming a line of the payslip or regime screen in front,
        with no cue of its own, rings that line as the voice reaches it."""
        if placed:
            return ()
        kind = _screen_kind(self.path)
        if kind is None:
            return ()
        low = f" {sentence.lower()} "
        best: tuple[int, str] | None = None
        for label, words in SCREEN_LABELS[kind]:
            for w in words:
                at = low.find(w)
                if at >= 0 and (best is None or at < best[0]):
                    best = (at, label)
        if best is None:
            return ()
        return [("show", [best[1]], max(0, best[0] - 1))]

    def _send(self, move: str, args: dict[str, Any]) -> str | None:
        ref = self.stage.send(move, args, queue=False)
        if move in ("app.open", "payslip.compare", "regime.compare", "me.view"):
            self.path = _path_of(move, args)
        return ref

    def _impact(self, changed: Changed | None) -> str:
        if changed is None:
            return ""
        e = self.books.employee(changed.employee_id)
        name = e["name"] if e else changed.employee_id
        before = changed.before or {}
        parts = [
            f" {name}'s February draft: net pay {inr(before.get('net_pay', 0))} → "
            f"{inr(changed.after['net_pay'])} ({inr(changed.net_delta)})"
        ]
        if changed.lop_days:
            parts.append(f", {changed.lop_days} day(s) loss of pay")
        if changed.tds_delta:
            parts.append(f", TDS {inr(before.get('tds', 0))} → {inr(changed.after['tds'])}")
        d = self.books.draft
        parts.append(f". Run net pay now {inr(d['net_pay'])}, {d['employees']} employees.")
        return "".join(parts)

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        return [
            self.find_employee,
            self.explain_net_pay,
            self.compare_regimes,
            self.open_feature,
            self.whats_pending,
            self.decide_leave,
            self.fix_claim,
            self.decide_claim,
            self.fill_new_employee,
            self.switch_regime,
            self.hand_off,
            self.confirm,
            self.setup_step,
            self.view_as_employee,
            self.read_screen,
            self.set_language,
        ]

    def _who(self, ref: str) -> dict[str, Any] | str:
        e = self.books.employee(ref)
        if e is not None:
            return e
        hits = self.books.matches(ref)
        if hits:
            return _not_done(
                f"more than one employee matches {ref!r}: "
                + ", ".join(f"{h['name']} ({h['id']}, {h['title']})" for h in hits[:6]),
                "Ask which one.",
            )
        return _not_done(f"no employee called {ref!r}", "Ask her to spell the name.")

    @needs_result_now
    async def find_employee(self, request: EmployeeRef) -> str:
        """Look up one employee: job, location, regime, CTC, leave balances."""
        e = self._who(request.employee)
        if isinstance(e, str):
            return e
        bal = e["leave_balance"]
        feb = self.books.slip(e["id"], FEB_KEY)
        return (
            f"{e['name']} ({e['id']}): {e['title']}, {e['department']}, {e['location']}, grade "
            f"{e['grade']}, joined {day(e['joined'])}. Annual CTC {inr(e['annual_ctc'])}. "
            f"Regime for TDS: {e['tax_regime']}. Leave left: EL {bal['EL']:g}, CL {bal['CL']:g}, "
            f"SL {bal['SL']:g}."
            + (f" February draft net pay {inr(feb['net_pay'])}." if feb else "")
        )

    @needs_result_now
    async def explain_net_pay(self, request: NetPayRequest) -> str:
        """Open an employee's payslip side by side with the month before, and
        get every line that changed with the reason from the data. Use it for
        "why is X's pay lower / higher / different"."""
        e = self._who(request.employee)
        if isinstance(e, str):
            return e
        b = self.books
        slips = [s for s in b.slips(e["id"]) if s["month"] != FEB_KEY or request.month == FEB_KEY]
        month = request.month or (slips[-1]["month"] if slips else "")
        cur = b.slip(e["id"], month)
        if cur is None:
            have = ", ".join(month_label(s["month"]) for s in b.slips(e["id"]))
            return _not_done(f"no payslip for {month}", f"Payslips there are: {have}.")
        idx = FY_KEYS.index(month)
        prev_key = FY_KEYS[idx - 1] if idx > 0 else None
        prev = b.slip(e["id"], prev_key) if prev_key else None
        self._send(
            "payslip.compare",
            {"employee_id": e["id"], "month": month, "against": prev_key if prev else None},
        )
        landed("Here's the payslip, with the month before beside it.")
        if prev is None:
            return f"{e['name']}'s {month_label(month)} payslip is on screen: net pay {inr(cur['net_pay'])}."
        lines = [
            f"{e['name']}'s {month_label(month)} payslip is on screen beside {month_label(prev_key or '')}. "
            f"Net pay {inr(prev['net_pay'])} → {inr(cur['net_pay'])} "
            f"({inr(cur['net_pay'] - prev['net_pay'])})."
        ]
        names = {
            "gross": "Gross",
            "employee_pf": "Provident fund",
            "professional_tax": "Professional tax",
            "tds": "TDS",
            "reimbursements": "Reimbursements",
        }
        for key, label in names.items():
            if cur[key] != prev[key]:
                lines.append(
                    f"{label}: {inr(prev[key])} → {inr(cur[key])} ({inr(cur[key] - prev[key])})."
                )
        # Why each changed, from the data.
        if cur["lop_days"] > prev["lop_days"]:
            leaves = [
                r
                for r in b.requests
                if r["employee_id"] == e["id"]
                and r["status"] == "approved"
                and r["from"].startswith(month)
                and (r["type"] == "LOP" or r.get("lop_days"))
            ]
            why = "; ".join(
                f"{r['id']}, {day(r['from'])} to {day(r['to'])}, {r['days']} days: {r['reason']}"
                for r in leaves
            )
            lines.append(
                f"Loss of pay: {cur['lop_days']} day(s) unpaid in {month_label(month)} "
                f"({cur['paid_days']} of {cur['days']} days paid), so every earning is cut in "
                f"proportion; gross fell by {inr(prev['gross'] - cur['gross'])}. Leave: {why or 'approved leave without pay'}."
            )
        if cur["tds"] != prev["tds"]:
            left = 12 - idx
            text = (
                f"TDS: the year's projected tax is {inr(cur['annual_tax'])} "
                f"(it was {inr(prev['annual_tax'])} last month), less TDS already deducted, "
                f"spread over the {left} months left of FY 2025-26 including {month_label(month)}."
            )
            d = b.declaration(e["id"])
            if d and d.get("proofs_verified_on", "")[:7] == month:
                short = [i for i in d["items"] if int(i["verified"]) < int(i["declared"])]
                if short:
                    text += (
                        f" Investment proofs were verified on {day(d['proofs_verified_on'])}: "
                        + "; ".join(
                            f"{i['label']} ({i['section']}) declared {inr(i['declared'])}, "
                            f"verified {inr(i['verified'])} ({i['proof_status'].replace('_', ' ')})"
                            for i in short
                        )
                        + ". Only verified amounts count, so the year's tax went up."
                    )
            lines.append(text)
        if cur["reimbursements"] != prev["reimbursements"]:
            paid = [
                c
                for c in b.claims
                if c["employee_id"] == e["id"]
                and c["payroll_month"] == month
                and c["status"] == "paid"
            ]
            lines.append(
                f"Reimbursements paid with {month_label(month)}: "
                + "; ".join(f"{c['description']} {inr(c['amount'])}" for c in paid)
                + ". Not taxed; they add to net pay."
            )
        d = b.declaration(e["id"])
        if d and any(i["proof_status"] == "not_submitted" for i in d["items"]):
            closes = COMPANY["company"]["windows"]["proofs"]["closes"]
            comp = b.comparison(e["id"])
            lines.append(
                f"Proofs can still be submitted until {day(closes)}. With verified amounts today, "
                f"the {comp['better']} regime is cheaper for the year by {inr(comp['saving'])} "
                f"(new {inr(comp['new']['total_tax'])}, old {inr(comp['old']['total_tax'])}); "
                f"they are on the {e['tax_regime']} regime."
            )
        nxt = b.slip(e["id"], FEB_KEY)
        if nxt is not None and month != FEB_KEY:
            lines.append(f"February draft net pay: {inr(nxt['net_pay'])}.")
        lines.append(
            "Explain the lines in order, ringing each as you name it. Tax figures are illustrative, FY 2025-26."
        )
        return "\n".join(lines)

    @needs_result_now
    async def compare_regimes(self, request: EmployeeRef) -> str:
        """Open an employee's regime comparison — both regimes' tax for FY
        2025-26 slab by slab, from the engine — and get the numbers."""
        e = self._who(request.employee)
        if isinstance(e, str):
            return e
        comp = self.books.comparison(e["id"])
        self._send("regime.compare", {"employee_id": e["id"]})
        landed("Here are both regimes, side by side.")
        out = [
            f"{e['name']}'s regime comparison is on screen (illustrative, FY 2025-26; actual pay "
            f"April to January plus full months to March; verified declarations). Current regime "
            f"for TDS: {e['tax_regime']}."
        ]
        for regime in ("new", "old"):
            t = comp[regime]
            slabs = "; ".join(
                f"{inr(s['lo'])} to {inr(s['hi']) if s['hi'] else 'above'} at {s['rate']}%: "
                f"{inr(s['taxable'])} taxed {inr(s['tax'])}"
                for s in t["slabs"]
                if s["taxable"] > 0
            )
            ded = (
                f", exempt HRA {inr(t['exempt_hra'])}, exempt LTA {inr(t['exempt_lta'])}, "
                f"professional tax {inr(t['professional_tax'])}, home loan {inr(t['house_property'])}, "
                f"80C {inr(t['ded_80c'])}, 80CCD(1B) {inr(t['ded_80ccd1b'])}, 80D {inr(t['ded_80d'])}"
                if regime == "old"
                else ""
            )
            out.append(
                f"{regime.upper()} regime: gross salary {inr(t['gross_salary'])}, standard deduction "
                f"{inr(t['standard_deduction'])}{ded}; taxable income {inr(t['taxable_income'])}. "
                f"Slabs: {slabs}. Tax {inr(t['tax_on_income'])}, rebate {inr(t['rebate_87a'])}, "
                f"cess {inr(t['cess'])}: total {inr(t['total_tax'])}."
            )
        other: eng.Regime = "old" if e["tax_regime"] == "new" else "new"
        preview = self.books.preview_regime(e["id"], other)
        out.append(
            f"The {comp['better']} regime is lower by {inr(comp['saving'])}. February TDS in the "
            f"draft: {inr((preview.before or {}).get('tds', 0))} on the {e['tax_regime']} regime, "
            f"{inr(preview.after['tds'])} if switched to {other}. "
            f"{COMPANY['company']['regime_change_policy']}"
        )
        return "\n".join(out)

    @needs_result_now
    async def open_feature(self, request: FeatureRequest) -> str:
        """Open the screen where a task is done and get its controls in order,
        to walk her through them, ringing each."""
        path, title, controls = GUIDE[request.feature]
        if "{employee}" in path:
            e = self.books.employee(request.employee or "")
            if e is None:
                return _not_done(
                    "this screen is about one employee and none was named",
                    "Ask whose, then call again with the name.",
                )
            path = path.format(employee=e["id"])
        if request.feature == "regime_switch":
            self._send("regime.compare", {"employee_id": path.rsplit("/", 1)[1]})
        else:
            self._send("app.open", {"path": path})
        landed("Here's the screen.")
        steps = "; ".join(f"{label}: {what}" for label, what in controls)
        return (
            f"{title} is opening at {path}. Its controls, in order — ring each with "
            f"{{show: Label}} as you explain it, one per sentence: {steps}."
        )

    @needs_result_now
    async def whats_pending(self) -> str:
        """What needs the admin before the February run: pending leave, claims
        to review, the proof window, and the draft's totals."""
        b = self.books
        pend = [r for r in b.requests if r["status"] == "pending"]
        leave = "; ".join(
            f"{r['id']} {b.name(r['employee_id'])}, {r['type']} {r['days']} days from {day(r['from'])}"
            + (f" ({lop} would be loss of pay)" if (lop := b.leave_impact(r)[1]) else "")
            for r in pend
        )
        claims = "; ".join(
            f"{c['id']} {b.name(c['employee_id'])}, {c['category']} {inr(c['amount'])}"
            + (
                f" (bill {inr(c['bill_amount'])}: {c['note']})"
                if c["status"] == "needs_fix"
                else ""
            )
            + (f" ({c['note']})" if c["status"] == "pending" and c.get("note") else "")
            for c in b.claims
            if c["status"] in ("pending", "needs_fix")
        )
        d = b.draft
        closes = COMPANY["company"]["windows"]["proofs"]["closes"]
        return (
            f"Pending leave ({len(pend)}): {leave or 'none'}. Claims to review: {claims or 'none'}. "
            f"Proof window closes {day(closes)}. {d['label']} draft ({d['status']}): "
            f"{d['employees']} employees, gross {inr(d['gross'])}, TDS {inr(d['tds'])}, "
            f"net pay {inr(d['net_pay'])}, pay date {day(d['pay_date'])}."
        )

    @needs_result_now
    async def decide_leave(self, request: LeaveRequest) -> str:
        """Approve or reject a pending leave request: says what it would do to
        the February draft and ASKS. Nothing changes until she says yes."""
        b = self.books
        req = b.request(request.request)
        if req is None:
            return _not_done(f"no leave request matches {request.request!r}", "Ask which one.")
        if req["status"] != "pending":
            return _not_done(f"{req['id']} is already {req['status']}", "Tell her so.")
        name = b.name(req["employee_id"])
        what = f"{request.decision} {name}'s {req['type']} leave {req['id']}"
        covered, lop = b.leave_impact(req)
        facts = (
            f"{req['id']}: {name}, {req['type']} {req['days']} days, {day(req['from'])} to "
            f"{day(req['to'])}, '{req['reason']}'."
        )
        if request.decision == "approve":
            impact = b.preview_leave(req)
            if lop and impact is not None:
                facts += (
                    f" Balance covers {covered} day(s); {lop} day(s) become loss of pay in the "
                    f"February draft: net pay {inr((impact.before or {}).get('net_pay', 0))} → "
                    f"{inr(impact.after['net_pay'])} ({inr(impact.net_delta)})."
                )
            elif lop:
                facts += (
                    f" {lop} day(s) become loss of pay in that month's payroll, not February's."
                )
            else:
                facts += f" The {req['type']} balance covers it; no change to pay."
        self._send("app.open", {"path": "/leave?tab=requests"})
        dup = self.confirms.ask(
            "leave",
            ("leave", req["id"], request.decision),
            what,
            self.turns,
            request_id=req["id"],
            decision=request.decision,
        )
        if dup is not None:
            return dup
        return facts + f" Say that, then ask: shall I {what}? Wait for her yes."

    async def _ask_claim(
        self, kind: str, c: dict[str, Any], what: str, facts: str, **data: Any
    ) -> str:
        self._send("app.open", {"path": "/reimbursements"})
        dup = self.confirms.ask(
            kind, (kind, c["id"], data.get("decision")), what, self.turns, **data
        )
        return dup or facts + f" Say that, then ask: shall I {what}? Wait for her yes."

    def _claim(self, ref: str) -> dict[str, Any] | str:
        c = self.books.claim(ref)
        if c is None:
            return _not_done(f"no open claim matches {ref!r}", "Ask which claim.")
        return c

    @needs_result_now
    async def fix_claim(self, request: ClaimRef) -> str:
        """Correct a claim whose amount does not match its bill: set it to the
        bill's amount and approve it into February. ASKS first."""
        c = self._claim(request.claim)
        if isinstance(c, str):
            return c
        name = self.books.name(c["employee_id"])
        if int(c["amount"]) == int(c["bill_amount"]):
            return _not_done(f"{c['id']} already matches its bill", "Offer to approve it instead.")
        facts = (
            f"{c['id']}: {name}, {c['category']}, '{c['description']}', claimed {inr(c['amount'])} "
            f"but the bill says {inr(c['bill_amount'])}. Fixing sets it to {inr(c['bill_amount'])} "
            f"and approves it into the February draft, so {name}'s February net pay rises by "
            f"{inr(c['bill_amount'])}."
        )
        return await self._ask_claim(
            "fix_claim",
            c,
            f"fix {name}'s claim {c['id']} to {inr(c['bill_amount'])}",
            facts,
            claim_id=c["id"],
            amount=int(c["bill_amount"]),
        )

    @needs_result_now
    async def decide_claim(self, request: ClaimDecision) -> str:
        """Approve or reject a pending claim. ASKS first."""
        c = self._claim(request.claim)
        if isinstance(c, str):
            return c
        name = self.books.name(c["employee_id"])
        facts = (
            f"{c['id']}: {name}, {c['category']} {inr(c['amount'])}, bill {inr(c['bill_amount'])}, "
            f"'{c['description']}'." + (f" Note: {c['note']}" if c.get("note") else "")
        )
        return await self._ask_claim(
            "claim",
            c,
            f"{request.decision} {name}'s claim {c['id']}",
            facts,
            claim_id=c["id"],
            decision=request.decision,
        )

    @needs_result_now
    async def fill_new_employee(self, request: NewEmployee) -> str:
        """Open the add-employee form and fill it on screen with what she said,
        field by field, with their prorated February pay. ASKS before saving.
        Never fills PAN or bank details: she types those."""
        b = self.books
        fields = request.model_dump()
        e = b.new_employee(fields)
        slip = b.joiner_slip(e)
        for field in (
            "name",
            "gender",
            "department",
            "title",
            "grade",
            "location",
            "joined",
            "annual_ctc",
            "tax_regime",
        ):
            self._send("employee.fill", {"field": field, "value": str(fields[field])})
        landed("The form's filled in on screen.")
        self.confirms.ask(
            "employee",
            ("employee", e["name"], e["joined"]),
            f"save {e['name']} as a new employee",
            self.turns,
            fields=fields,
        )
        return (
            f"The form is filling in: {e['name']}, {e['title']}, {e['department']}, {e['location']}, "
            f"{e['grade']}, joining {day(e['joined'])}, CTC {inr(e['annual_ctc'])}, {e['tax_regime']} regime. "
            f"They will be {e['id']}. February pay is prorated: {slip['lop_days']} of 28 days before "
            f"joining are unpaid, so gross {inr(slip['gross'])}, TDS {inr(slip['tds'])}, net pay "
            f"{inr(slip['net_pay'])}. PAN and bank details are for her to type. "
            "Say that, then ask: shall I save them?"
        )

    @needs_result_now
    async def switch_regime(self, request: RegimeRequest) -> str:
        """Change the regime used for an employee's TDS. Says what February's
        TDS becomes and ASKS. Nothing changes until she says yes."""
        e = self._who(request.employee)
        if isinstance(e, str):
            return e
        if e["tax_regime"] == request.regime:
            return _not_done(
                f"{e['name']} is already on the {request.regime} regime", "Tell her so."
            )
        p = self.books.preview_regime(e["id"], request.regime)
        comp = self.books.comparison(e["id"])
        self._send("regime.compare", {"employee_id": e["id"]})
        what = f"switch {e['name']} to the {request.regime} regime"
        dup = self.confirms.ask(
            "regime",
            ("regime", e["id"], request.regime),
            what,
            self.turns,
            employee_id=e["id"],
            regime=request.regime,
        )
        if dup is not None:
            return dup
        return (
            f"Switching {e['name']} to the {request.regime} regime: the year's tax becomes "
            f"{inr(comp[request.regime]['total_tax'])} (illustrative, FY 2025-26), and February TDS "
            f"in the draft goes from {inr((p.before or {}).get('tds', 0))} to {inr(p.after['tds'])}, "
            f"net pay {inr((p.before or {}).get('net_pay', 0))} → {inr(p.after['net_pay'])}. "
            f"{COMPANY['company']['regime_change_policy']} Say that, then ask: shall I switch?"
        )

    async def hand_off(self, request: HandOff) -> str:
        """Hand the matter to Tankora's payroll team: the written ticket is
        shown on screen, and it is sent only after she says yes."""
        e = self.books.employee(request.employee or "") if request.employee else None
        args: dict[str, Any] = {"subject": request.subject, "summary": request.summary}
        if e is not None:
            args["employee_id"] = e["id"]
        self._send("ticket.draft", args)
        landed("The ticket's written up on screen.")
        self.confirms.ask(
            "ticket",
            ("ticket", request.subject),
            f"send the ticket '{request.subject}'",
            self.turns,
            subject=request.subject,
            summary=request.summary,
        )
        return "The ticket draft is on screen. Ask her if you should send it to the payroll team."

    async def confirm(self, request: ConfirmRequest) -> str:
        """She said yes to the change you just asked about, in words the brain
        did not catch as a plain yes: do it now. Only after you asked."""
        pending = self.confirms.due(self.turns, request.kind)
        if pending is None:
            if (line := self.confirms.already_kind(request.kind or "")) is not None:
                landed(line)
                return f"Already done, not sent again. {line}"
            return _not_done("nothing is waiting for her yes", "Ask first, then wait for her yes.")
        acted = self.confirms.act(pending)
        landed(acted.line)
        return f"{acted.note} Say: {acted.line}"

    @needs_result_now
    async def setup_step(self, request: SetupStep) -> str:
        """Onboarding: open one step of the setup wizard and do it on screen —
        fill its fields from the company's signup details, import the
        employee file, or run the test payroll. One step per reply; ask before
        the next."""
        step = request.step
        if step == "done":
            self._send("setup.step", {"step": "test_run"})
            self.confirms.ask("setup_finish", ("setup_finish",), "finish setup", self.turns)
            return "Everything is in place. Ask: shall I finish setup and open the dashboard?"
        self._send("setup.step", {"step": step})
        co = COMPANY["company"]
        if step in ("company", "structure", "leave"):
            values = _setup_values(step)
            for field, value in values:
                self._send("setup.fill", {"field": field, "value": value})
            self.setup_done.add(step)
            landed("That step's filled in on screen.")
            said = "; ".join(f"{f.replace('_', ' ')}: {v}" for f, v in values)
            nxt = {
                "company": "the pay structure",
                "structure": "importing employees",
                "leave": "the test payroll",
            }[step]
            return f"Filling the {step} step on screen: {said}. Next would be {nxt}. Ask before moving on."
        if step == "import":
            self._send("setup.import", {})
            s = import_summary()
            self.setup_done.add(step)
            landed("Your employee file is in, with the checks beside it.")
            locs = ", ".join(f"{k} {v}" for k, v in s["by_location"].items())
            errs = "; ".join(s["errors"][:5]) or "no errors"
            return (
                f"employees_import.csv imported: {s['rows']} rows, {s['valid']} valid, {errs}. "
                f"By location: {locs}. Regimes: {s['regimes'].get('new', 0)} new, "
                f"{s['regimes'].get('old', 0)} old. Total annual CTC {inr(s['annual_ctc'])}. "
                f"Year-to-date pay from April 2025 to January 2026 came with {co['name']}'s data. "
                "Next would be the leave policy. Ask before moving on."
            )
        self._send("setup.test_run", {})
        t = test_payroll(self.books)
        self.setup_done.add(step)
        landed("The test payroll has run; the totals are on screen.")
        d = self.books.draft
        same = all(t[k] == d[k] for k in ("gross", "tds", "net_pay", "employees"))
        return (
            f"Test payroll for February 2026 (28 days): {t['employees']} employees, gross "
            f"{inr(t['gross'])}, employee PF {inr(t['employee_pf'])}, ESI {inr(t['employee_esi'])}, "
            f"professional tax {inr(t['professional_tax'])}, TDS {inr(t['tds'])}, reimbursements "
            f"{inr(t['reimbursements'])}, net pay {inr(t['net_pay'])}, employer cost "
            f"{inr(t['employer_cost'])}. "
            + (
                "It matches the February draft exactly."
                if same
                else "It differs from the February draft."
            )
            + " Ask if she wants to finish setup."
        )

    async def view_as_employee(self, request: ViewAs) -> str:
        """Switch to the employee self-service view as one employee: their own
        payslips, tax and regime, declarations, or leave."""
        e = self._who(request.employee)
        if isinstance(e, str):
            return e
        self._send("me.view", {"employee_id": e["id"], "tab": request.tab})
        landed(f"This is what {e['name']} sees.")
        return f"Showing Tankora as {e['name']} sees it, on {request.tab}."

    @needs_result_now
    async def read_screen(self, request: ReadRequest) -> str:
        """Read part of her screen as the page last reported it."""
        return self.stage.mirror.read(request.slice) if self.stage.mirror else "unknown"

    async def set_language(self, request: LanguageRequest) -> str:
        """Conduct the rest of the call in English or Hindi, listening and
        speaking. Call it when she asks for the other language; say one short
        line in the same response."""
        if request.language not in PERSONA.languages:
            return _not_done("that language is not offered", "Stay in this one.")
        configure_soon(self.session, self._speaking(request.language))
        logger.info("payroll_app: language -> {}", request.language)
        return "ok"

    # ─── What each confirmation does on a yes ──────────────────────────

    def _flight(
        self, move: str, args: dict[str, Any], effect: Callable[[], str], note: str
    ) -> Acted:
        ref = self._send(move, args)
        acted = Acted(
            HELD[self.lang],
            note,
            ref=ref,
            on_applied=lambda _d, r=ref: self._said.pop(r or "", "Done."),
        )
        if ref is not None:
            self._effects[ref] = lambda _detail: effect()
        return acted

    def _act_leave(self, p: Pending) -> Acted:
        rid, decision = p.data["request_id"], p.data["decision"]

        def effect() -> str:
            changed = self.books.decide_leave(rid, decision)
            req = self.books.request(rid) or {}
            name = self.books.name(str(req.get("employee_id", "")))
            line = f"Done — {name}'s leave is {decision}d."
            if changed is not None:
                line += (
                    f" {changed.lop_days} day becomes loss of pay, so her February net pay is now "
                    f"{inr(changed.after['net_pay'])}."
                    if changed.lop_days == 1
                    else f" {changed.lop_days} days become loss of pay; February net pay is now "
                    f"{inr(changed.after['net_pay'])}."
                )
            return line

        return self._flight(
            "leave.decide",
            {"request_id": rid, "decision": decision},
            effect,
            f"[Sent: {p.label}. The page answers; do not call decide_leave again.]",
        )

    def _act_fix_claim(self, p: Pending) -> Acted:
        cid, amount = p.data["claim_id"], int(p.data["amount"])

        def effect() -> str:
            changed = self.books.fix_claim(cid, amount)
            line = f"Done — claim {cid} is corrected to {inr(amount)} and approved."
            if changed is not None:
                line += f" It's in the February draft: net pay {inr(changed.after['net_pay'])}."
            return line

        return self._flight(
            "claim.fix",
            {"claim_id": cid, "amount": amount},
            effect,
            f"[Sent: {p.label}. Do not call fix_claim again.]",
        )

    def _act_claim(self, p: Pending) -> Acted:
        cid, decision = p.data["claim_id"], p.data["decision"]

        def effect() -> str:
            self.books.decide_claim(cid, decision)
            return f"Done — claim {cid} is {decision}d."

        return self._flight(
            "claim.decide",
            {"claim_id": cid, "decision": decision},
            effect,
            f"[Sent: {p.label}. Do not call decide_claim again.]",
        )

    def _act_employee(self, p: Pending) -> Acted:
        fields: dict[str, Any] = p.data["fields"]

        def effect() -> str:
            e, slip = self.books.add_employee(fields)
            return (
                f"Done — {e['name']} is {e['id']}, with {inr(slip['net_pay'])} net pay in the "
                "February draft."
            )

        return self._flight(
            "employee.save", {}, effect, f"[Sent: {p.label}. Do not call fill_new_employee again.]"
        )

    def _act_regime(self, p: Pending) -> Acted:
        eid, regime = p.data["employee_id"], p.data["regime"]

        def effect() -> str:
            changed = self.books.switch_regime(eid, regime)
            name = self.books.name(eid)
            if changed is None:
                return f"Done — {name} is on the {regime} regime."
            return (
                f"Done — {name} is on the {regime} regime. February TDS is now "
                f"{inr(changed.after['tds'])}, and net pay {inr(changed.after['net_pay'])}."
            )

        return self._flight(
            "regime.switch",
            {"employee_id": eid, "regime": regime},
            effect,
            f"[Sent: {p.label}. Do not call switch_regime again.]",
        )

    def _act_ticket(self, p: Pending) -> Acted:
        subject, summary = p.data["subject"], p.data["summary"]

        def effect() -> str:
            tid = self.books.add_ticket(subject, summary)
            return (
                f"Sent — your ticket is {tid}. Our payroll team will pick it up from the summary."
            )

        return self._flight(
            "ticket.submit", {}, effect, f"[Sent: {p.label}. Do not call hand_off again.]"
        )

    def _act_setup_finish(self, p: Pending) -> Acted:
        def effect() -> str:
            return (
                "Setup's done. You're on your dashboard, with the February draft ready to review."
            )

        return self._flight("setup.finish", {}, effect, "[Sent: finish setup.]")


def _path_of(move: str, args: dict[str, Any]) -> str:
    if move == "payslip.compare":
        return f"/payslips/{args['employee_id']}/{args['month']}"
    if move == "regime.compare":
        return f"/tax/regime/{args['employee_id']}"
    if move == "me.view":
        return f"/me/{args['employee_id']}/{args.get('tab') or 'payslips'}"
    return "/" + str(args.get("path", "/")).split("?")[0].strip("/")


def _setup_values(step: str) -> list[tuple[str, str]]:
    """The setup wizard's fields for a step, from the company's signup data."""
    co = COMPANY["company"]
    if step == "company":
        pt = co["pt_registrations"]
        return [
            ("company_name", co["name"]),
            ("legal_name", co["legal_name"]),
            ("pan", co["pan"]),
            ("tan", co["tan"]),
            ("registered_office", co["registered_office"]),
            ("pf_code", co["pf_code"]),
            ("esi_code", co["esi_code"]),
            ("pt_karnataka", pt.get("Karnataka", "")),
            ("pt_maharashtra", pt.get("Maharashtra", "")),
            ("pay_cycle", co["pay_cycle"]),
        ]
    if step == "structure":
        rules = eng.RULES
        return [
            ("basic_pct", "40"),
            ("hra_metro_pct", str(rules.hra_metro_pct)),
            ("hra_non_metro_pct", str(rules.hra_non_metro_pct)),
            ("lta_g5", "3000"),
            ("lta_g6_up", "5000"),
            ("pf_rule", f"12% of basic up to {inr(rules.pf_ceiling)}"),
            ("esi_rule", f"Employer 3.25% when gross is up to {inr(rules.esi_ceiling)}"),
        ]
    policy = COMPANY["leave"]["policy"]
    types = {t["id"]: t for t in policy["types"]}
    return [
        ("el_per_year", str(types["EL"]["per_year"])),
        ("cl_per_year", str(types["CL"]["per_year"])),
        ("sl_per_year", str(types["SL"]["per_year"])),
        ("el_carry_forward", str(types["EL"]["carry_forward_max"])),
        ("attendance_cutoff", policy["attendance_cutoff"]),
        ("lop_rule", policy["lop_rule"]),
    ]


__all__ = ["GUIDE", "MODEL", "TankoraBrain"]
