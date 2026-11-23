"""InsuranceBrain — the guide of Chhatri Insurance, a fictional Indian insurer.

One brain, three jobs, chosen by the page the customer is on (``init.landing``
at the start, then every Stage ``hello`` as they move):

- **Quote** (``/quote``, ``/insurance/<product>``): a quote in a few sentences
  instead of a long form. :meth:`update_quote` normalises what was said into the
  form's values, fills the form on screen move by move, toggles add-ons, and
  returns the premium from :mod:`.rating` — the same tables the page computes
  from, so the breakdown on screen and the one she says agree.
- **Policies** (``/my-policies``): "am I covered if…". :meth:`search_policy`
  returns the clauses of the customer's own policy wording that match; the model
  says what they say and :meth:`mark_clause` opens the document and marks the
  clause with a verdict.
- **Claim** (``/claim``): the long claim form, filled from what the customer
  says (:meth:`fill_claim`), asking only for what is still missing, up to the
  review step. The customer submits.

Every change to the screen is a Stage move (``frontend/src/stage/scene.json``),
sent with ``stage.send``; the page reports its state back as Stage events.

**The character** (name, face, voice, languages) is ``persona.json``, through
:mod:`.persona`. The call is in English or Hindi: the page's toggle picks it before
the call, :meth:`set_language` or the toggle switch it mid-call, and Hindi heard
on the English recognizer switches it too — both speech legs at once, always.
"""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from loguru import logger
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from voqalize_demos import PATIENCE, FallbackLine, configure_soon, landed

from voqalize.sdk import (
    AppEvents,
    RTVIMessage,
    Session,
    Speech,
    UserIdle,
    UserMessage,
)
from voqalize.sdk.openai import OpenAIBrain, needs_result_now
from voqalize.sdk.stage import Mirror, Stage
from voqalize.sdk.stage.wire import StageEvent, StageHello, StageProgress, StageResult
from voqalize.sdk.wire import Config, IdleConfig, RedialConfig

from . import claims as cl
from . import persona, quotes, rating
from .policies import clause_text, search
from .prompt import system_instruction
from .rejoin import Rejoin
from .stage_gen import MOVES, SPEC
from .store import (
    CLAIMS_GUIDE,
    FIRST_NAME,
    POLICIES,
    clause,
    mode_of,
    pages,
    policies_for,
    route_of,
)

MODEL = "gpt-6.1-terra"
#: COMMON demo rule for new demos: at "low" the model skipped screen moves it had promised.
REASONING = "medium"

_EVENTS = AppEvents(StageResult, StageHello, StageProgress, StageEvent)

#: A quiet spell before she may speak up on her own (only when the page left
#: her something to say), and how short it gets while she has something.
_IDLE_MS = 12_000
_TALK_MS = 1_500
_SAY_NOW_MS = 400

IST = timezone(timedelta(hours=5, minutes=30))

Product = Literal["car", "bike", "health", "term", "home", "travel"]
Verdict = Literal["covered", "not_covered", "covered_with_limits", "depends"]

JOBS: dict[str, str] = {
    "home": "HOME: find out whether they want a quote, an answer about their cover, or to make a claim, and take them there with go_to.",
    "quote": "QUOTE: build their quote from what they say with update_quote.",
    "policies": "POLICIES: answer 'am I covered if…' with search_policy, then say it plainly and mark_clause.",
    "claim": "CLAIM: fill the claim form from what they say with start_claim and fill_claim; ask only for what is missing.",
}

# Hindi grammar words, as either recognizer writes them: two in one turn is Hindi.
_HINDI_WORDS = frozenset(
    [
        "hai",
        "hain",
        "hoon",
        "kya",
        "mein",
        "mujhe",
        "chahiye",
        "karo",
        "kariye",
        "karna",
        "dikhao",
        "aap",
        "baat",
        "nahi",
        "nahin",
        "sakti",
        "sakte",
        "sakta",
        "kitna",
        "kitne",
        "kitni",
        "liye",
        "bhi",
        "aur",
        "yeh",
        "woh",
        "accha",
        "haan",
        "ka",
        "ki",
        "ke",
        "ko",
        "se",
        "mera",
        "meri",
        "mere",
        "hua",
        "tha",
        "thi",
        "है",
        "हैं",
        "हूँ",
        "क्या",
        "में",
        "मुझे",
        "चाहिए",
        "करो",
        "करिए",
        "करना",
        "दिखाओ",
        "आप",
        "बात",
        "नहीं",
        "सकती",
        "सकते",
        "कितना",
        "कितने",
        "लिए",
        "भी",
        "और",
        "यह",
        "ये",
        "वह",
        "वो",
        "अच्छा",
        "हाँ",
        "का",
        "की",
        "के",
        "को",
        "से",
        "मेरा",
        "मेरी",
        "मेरे",
        "हुआ",
        "था",
        "थी",
    ]
)


def sounds_hindi(text: str) -> bool:
    if re.search(r"[ऀ-ॿ]", text):
        return True
    words = set(re.findall(r"[\wऀ-ॿ]+", text.lower()))
    return len(words & _HINDI_WORDS) >= 2


# ─── Tool arguments ───────────────────────────────────────────────────────────


class Answer(BaseModel):
    field: str = Field(description="A field id, e.g. vehicle_class, incident_date.")
    value: str = Field(
        description="The value: an option value, digits, '14 lakh', YYYY-MM-DD, HH:MM or text."
    )


class QuoteUpdate(BaseModel):
    product: Product
    answers: list[Answer] = Field(
        default_factory=list, description="Every answer the customer gave, all at once."
    )
    addons_on: list[str] = Field(default_factory=list, description="Add-on ids to switch on.")
    addons_off: list[str] = Field(default_factory=list, description="Add-on ids to switch off.")


class PolicyQuestion(BaseModel):
    question: str = Field(description="The customer's question, in English.")
    policy_id: str | None = Field(default=None, description="The policy it is about, when clear.")


class MarkClause(BaseModel):
    policy_id: str
    clause_id: str
    verdict: Verdict


class OpenPolicy(BaseModel):
    policy_id: str
    section: str | None = None


class StartClaim(BaseModel):
    claim_type: Literal["motor", "health"]
    policy_id: str | None = Field(default=None, description="The policy to claim on, once known.")


class ClaimAnswers(BaseModel):
    answers: list[Answer] = Field(description="Every answer the customer gave, all at once.")


class ClaimSection(BaseModel):
    section: str


class GoTo(BaseModel):
    page: str = Field(
        description="home, quote, quote/<product>, insurance/<product>, my-policies, my-policies/<policy_id>, claim"
    )


class LanguageRequest(BaseModel):
    language: str = Field(description="A language code: " + ", ".join(persona.LANGUAGES) + ".")


# ─── The brain ────────────────────────────────────────────────────────────────

#: What a brain holds for one socket only: the session object and the speech
#: units waiting for the runtime to say what was heard. Everything else a call
#: built is carried to the brain a redial starts (rejoin.py).
_PER_SOCKET = frozenset({"_session", "_awaiting"})


class InsuranceBrain(OpenAIBrain):
    """One per session: the job, the language, the quote and claim as known."""

    def __init__(self, *, client: AsyncOpenAI, model: str = MODEL) -> None:
        super().__init__(
            client=client,
            system_instruction=system_instruction(),
            model=model,
            reasoning=REASONING,
        )
        self.lang: str = persona.DEFAULT_LANGUAGE
        self.mode: str = "home"
        self.route: str = "home"
        self.today = datetime.now(IST).date()
        # The quote builder: answers and add-ons per product, and the product on screen.
        self.answers: dict[str, dict[str, str]] = {}
        self.addons: dict[str, list[str]] = {}
        self.screen_product: str | None = None
        self.claim = cl.ClaimState()
        self.marked: tuple[str, str] | None = None
        self.stage = Stage(
            dispatch=lambda a: self.session.dispatch(a),
            moves=MOVES,
            mirror=Mirror(SPEC),
        )
        self._fallback = FallbackLine()
        self._talk: str | None = None  # an ask for the next quiet spell
        self._say: str | None = None  # a written line for the next quiet spell
        # This socket picked up a call a dropped one had (rejoin.py): no greeting.
        self._rejoined = False

    # ─── Session ────────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        """Both speech legs of the language the page's toggle chose, before the
        greeting; the job from the page the call started on.

        A call outlives a dropped socket (CONTRACT.md, redial; SDK 0.15.0):
        redial is on wherever Voqalize offers it, and a brain started by a
        redial on a session this process still holds adopts that call as it
        was — the job, page and language it had moved to, the quote and claim,
        the model's history — instead of starting over. Its greeting is not
        spoken, and no second start note goes to the model."""
        prior = REJOIN.take(session.id)
        rejoined = False
        if prior is not None and prior is not self:
            self._adopt(prior)
            rejoined = True
            logger.info("insurance: rejoined call {} after its socket dropped", session.id)
        else:
            init = session.init or {}
            self.lang = persona.language_of(init.get("lang"))
            self._arrive(str(init.get("landing") or "/"))
        self._rejoined = rejoined
        REJOIN.hold(session.id, self)
        speech = persona.speech_config(self.lang, patience=PATIENCE, idle_ms=_IDLE_MS)
        await session.configure(
            replace(speech, redial=RedialConfig(enabled=True) if session.can_redial else None)
        )
        if rejoined:
            return
        self.append_note(
            f"[Today is {self.today.strftime('%A, %d %b %Y')} ({self.today.isoformat()}). "
            f"The customer is on /{self.route}. Your job here: {JOBS[self.mode]} "
            f"The call is in {persona.LANGUAGES[self.lang].label}.]"
        )
        logger.info("insurance: session start on /{} ({}) in {}", self.route, self.mode, self.lang)

    async def on_session_end(self, session: Session) -> None:
        """The socket closed: a hang-up, or a drop Voqalize may redial. Kept a
        short while for the redial; runs at least once, and a second run (or
        one on a brain a redial already replaced) changes nothing."""
        REJOIN.dropped(session.id, self)

    def _adopt(self, prior: InsuranceBrain) -> None:
        """Take over ``prior``'s call: every piece of state but its socket's.
        ``prior`` then shares this brain's state, so whatever still points at
        it — the Stage director's dispatch, a line queued for the next quiet
        spell — acts on this call and this socket."""
        self.__dict__.update({k: v for k, v in prior.__dict__.items() if k not in _PER_SOCKET})
        prior.__dict__ = self.__dict__

    async def greet(self, session: Session) -> str | None:
        """The job's fixed opening line; none on a socket that rejoined a call
        already greeted (Voqalize would not speak it anyway)."""
        if self._rejoined:
            return None
        return persona.greeting(self.mode, self.lang, FIRST_NAME)

    def _arrive(self, path: str) -> bool:
        """The page is now ``path``: the job follows it. True when the job changed."""
        self.route = route_of(path)
        parts = self.route.split("/")
        self.screen_product = (
            parts[1] if parts[0] in ("quote", "insurance") and len(parts) > 1 else None
        )
        mode = mode_of(path)
        changed = mode != self.mode
        self.mode = mode
        return changed

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[Speech, None]:
        self.stage.visitor_spoke()
        self._talk = None
        self._say = None
        self._settle_expired()
        if self.lang != "hi" and "hi" in persona.LANGUAGES and sounds_hindi(msg.text):
            logger.info("insurance: language -> hi (heard)")
            await session.configure(self._speaking("hi"))
        async for event in super().on_user_message(session, msg):
            yield event

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The model's turn; a written line if it acted and said nothing."""
        turn = self.stage.cued(super().respond(session))
        async for event in self._fallback.speak_if_silent(self, turn):
            yield event
        for unkept in self.stage.end_turn():
            self.append_note(
                f"[You said {unkept.sentence!r} but made no matching tool call. Make the call now if it is still wanted.]"
            )

    def on_user_idle(self, session: Session, idle: UserIdle) -> AsyncGenerator[Speech, None]:
        return self._idle(session)

    async def _idle(self, session: Session) -> AsyncGenerator[Speech, None]:
        """Quiet. She speaks only when the page left her something: the line
        for a language switch, or an outcome to talk through."""
        self._settle_expired()
        configure_soon(session, Config(idle=IdleConfig(timeout_ms=_IDLE_MS)))
        say, self._say = self._say, None
        if say is not None:
            async for event in self.say_line(say, remember=True):
                yield event
            return
        ask, self._talk = self._talk, None
        if ask is None:
            return
        self.append_note(f"[{ask}]")
        async for event in self.respond(session):
            yield event

    def _soon(self, *, say: str | None = None, talk: str | None = None) -> None:
        if say is not None:
            self._say = say
        if talk is not None:
            self._talk = talk
        configure_soon(
            self.session, Config(idle=IdleConfig(timeout_ms=_SAY_NOW_MS if say else _TALK_MS))
        )

    def _speaking(self, lang: str) -> Config:
        """Both legs of ``lang``, and the toggle moved to it."""
        if lang != self.lang:
            self.stage.send("site.language", {"language": lang}, queue=False)
        self.lang = lang
        return persona.speech_config(lang, patience=PATIENCE)

    def _landed(self, en: str, hi: str) -> None:
        landed(hi if self.lang == "hi" else en)

    def _send(self, move: str, args: dict[str, Any] | None = None) -> str:
        return self.stage.send(move, dict(args or {}), queue=False)

    # ─── What the page says ─────────────────────────────────────────────

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        event = _EVENTS.parse(msg)
        if event is None:
            return
        if isinstance(event, StageHello):
            self.stage.handle(event)
            if event.url and self._arrive(event.url):
                self.append_note(
                    f"[PAGE] The customer is now on /{self.route}. Your job here: {JOBS[self.mode]}"
                )
            return
        if isinstance(event, StageProgress):
            self.stage.handle(event)
            return
        if isinstance(event, StageResult):
            result = self.stage.handle(event)
            if result is not None:
                self._result(result)
            return
        self.stage.handle(event)
        note = self._event(event)
        if note is not None:
            logger.info("insurance: page {}", note)
            self.append_note(note)

    def _event(self, event: StageEvent) -> str | None:
        d = event.data
        visitor = event.by == "visitor"
        match event.name:
            case "quote.changed":
                product = str(d.get("product") or "")
                if product in rating.PRODUCTS:
                    self.screen_product = product
                    if isinstance(answers := d.get("answers"), list):
                        self.answers[product] = {
                            str(a["field"]): str(a["value"])
                            for a in answers  # pyright: ignore[reportUnknownVariableType]
                            if isinstance(a, dict) and a.get("value") not in (None, "")  # pyright: ignore[reportUnknownMemberType]
                        }
                    if isinstance(addons := d.get("addons"), list):
                        self.addons[product] = [str(x) for x in addons]  # pyright: ignore[reportUnknownVariableType]
                if not visitor:
                    return None
                total = d.get("total")
                said = (
                    f" The total on screen is now {rating.inr(float(total))}."
                    if isinstance(total, int | float)
                    else ""
                )
                return f"[The customer changed {d.get('field') or 'the quote'} on the {product} quote themselves.{said}]"
            case "policy.viewed":
                return (
                    f"[The customer opened policy {d.get('policy_id')} themselves.]"
                    if visitor
                    else None
                )
            case "claim.changed":
                if (t := d.get("claim_type")) in cl.TYPES and t != self.claim.claim_type:
                    self.claim.start(str(t), None)
                if pid := d.get("policy_id"):
                    self.claim.values["policy_id"] = str(pid)
                if isinstance(filled := d.get("filled"), list):
                    self.claim.filled_on_page = {str(x) for x in filled}  # pyright: ignore[reportUnknownVariableType]
                if isinstance(missing := d.get("missing"), list):
                    self.claim.page_missing = [str(x) for x in missing]  # pyright: ignore[reportUnknownVariableType]
                field = d.get("field")
                return (
                    f"[The customer filled {field} on the claim form themselves.]"
                    if visitor and field
                    else None
                )
            case "claim.document_uploaded":
                if isinstance(docs := d.get("documents"), list):
                    self.claim.documents = {str(x) for x in docs}  # pyright: ignore[reportUnknownVariableType]
                left = ", ".join(x["label"] for x in self.claim.documents_needed()) or "none"
                return f"[The customer uploaded {d.get('field')}. Documents still needed: {left}.]"
            case "claim.submitted":
                ref = str(d.get("reference") or "")
                self.claim.reference = ref
                steps = self._next_steps()
                self._soon(
                    talk=f"The customer just submitted claim {ref}. Thank them, give the reference, and say what "
                    f"happens next from these steps only, in two short sentences: {steps}"
                )
                return f"[The customer submitted the claim, reference {ref}.]"
            case "site.language_chosen":
                lang = str(d.get("language") or "")
                if visitor and lang in persona.LANGUAGES and lang != self.lang:
                    self.lang = lang
                    configure_soon(self.session, persona.speech_config(lang, patience=PATIENCE))
                    self._soon(say=persona.SWITCHED[lang])
                    return f"[The customer switched the call to {persona.LANGUAGES[lang].label}. Answer in it from now on.]"
                return None
            case _:
                return None

    def _next_steps(self) -> str:
        t = self.claim.claim_type or "motor"
        guide: Any = CLAIMS_GUIDE.get(t, {})
        if t == "health" and isinstance(guide, dict):
            mode = self.claim.values.get("claim_mode", "reimbursement")
            guide = guide.get(mode, guide)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        if isinstance(guide, dict):
            steps: Any = guide.get("next_steps", [])  # pyright: ignore[reportUnknownMemberType]
            turnaround = guide.get("turnaround", "")  # pyright: ignore[reportUnknownMemberType]
            return " ".join(str(s) for s in steps) + (
                f" Turnaround: {turnaround}" if turnaround else ""
            )  # pyright: ignore[reportUnknownVariableType]
        return str(guide)

    def _result(self, result: StageResult) -> None:
        if result.moved or result.outcome in ("applied", "partial", "undone"):
            return
        offers = "; ".join(
            f"{r.arg}: {r.why}" + (f" (options: {', '.join(r.options)})" if r.options else "")
            for r in result.refused
        )
        why = result.detail or offers or result.outcome
        logger.info("insurance: {} {} — {}", result.move, result.outcome, why)
        if result.outcome == "unknown":
            return
        self.append_note(f"[The screen did not do {result.move}: {why}. Never say it did.]")
        self._soon(
            talk="Tell the customer in one short sentence what did not go through on screen, and ask for what fixes it."
        )

    def _settle_expired(self) -> None:
        for result in self.stage.expire():
            self._result(result)

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        return [
            self.update_quote,
            self.search_policy,
            self.mark_clause,
            self.open_policy,
            self.start_claim,
            self.fill_claim,
            self.review_claim,
            self.show_claim_section,
            self.go_to,
            self.set_language,
        ]

    @needs_result_now
    async def update_quote(self, req: QuoteUpdate) -> str:
        """Fill the quote form on screen with the customer's answers (several at
        once), switch add-ons on or off, and get the premium. Returns the
        breakdown when complete, or what is still missing."""
        product = req.product
        answers = self.answers.setdefault(product, {})
        addons = self.addons.setdefault(product, rating.default_addons(product))
        if self.screen_product != product:
            self._send("quote.open", {"product": product})
            self.screen_product = product
        done: list[str] = []
        rejected: list[str] = []
        for a in req.answers:
            value, why = quotes.normalise(product, a.field, a.value)
            if value is None:
                rejected.append(f"{a.field} = {a.value!r} not taken: {why}")
                continue
            answers[a.field] = value
            self._send("quote.fill", {"field": a.field, "value": value})
            done.append(f"{a.field}={value}")
        valid = {x["id"]: x["label"] for x in rating.PRODUCTS[product]["addons"]}
        before = rating.quote(product, answers, addons)
        for add in req.addons_on:
            if add not in valid:
                rejected.append(f"add-on {add!r}: not offered (add-ons: {', '.join(valid)})")
            elif why := before.unavailable.get(add):
                rejected.append(f"add-on {valid[add]}: unavailable, {why}")
            elif add not in addons:
                addons.append(add)
                self._send("quote.addon", {"addon": add, "on": True})
        for add in req.addons_off:
            if add in addons:
                addons.remove(add)
                self._send("quote.addon", {"addon": add, "on": False})
        q = rating.quote(product, answers, addons)
        spec = rating.PRODUCTS[product]
        head = f"{spec['name']} ({spec['plan']}). Set: {', '.join(done) or 'nothing new'}."
        if rejected:
            head += " " + " ".join(rejected) + "."
        if q.error:
            self._landed("That combination doesn't work.", "यह कॉम्बिनेशन नहीं चलेगा।")
            return f"{head} Cannot quote: {q.error}. Tell the customer and ask what to change."
        if not q.complete:
            asks = "; ".join(
                f"{f['id']} ({f['ask']})" for f in spec["fields"] if f["id"] in q.missing
            )
            self._landed("Got it.", "ठीक है।")
            return f"{head} Still needed, in order: {asks}. Ask for the next one or two in one short question."
        self._send("quote.show")
        lines = "; ".join(f"{ln.label} {rating.inr(ln.amount)}" for ln in q.lines)
        gst = (
            f"GST {q.gst_percent}% {rating.inr(q.gst)}"
            if q.gst_percent
            else f"GST nil ({spec.get('gst_note', '')})"
        )
        off = [valid[x] for x in valid if x not in addons and x not in q.unavailable]
        unavailable = "; ".join(f"{valid[k]}: {v}" for k, v in q.unavailable.items())
        self._landed("Here's your quote.", "यह रहा आपका क्वोट।")
        return (
            f"{head} Quote on screen — {lines}; net {rating.inr(q.net)}; {gst}; TOTAL PAYABLE "
            f"{rating.inr(q.total)} a year."
            + (f" IDV {rating.inr(q.idv)}." if q.idv else "")
            + f" Add-ons not taken: {', '.join(off) or 'none'}."
            + (f" Unavailable: {unavailable}." if unavailable else "")
        )

    @needs_result_now
    async def search_policy(self, req: PolicyQuestion) -> str:
        """Find the clauses of the customer's own policy wording that answer a
        question like "am I covered if…". Read them, then answer and mark_clause."""
        pid = req.policy_id if req.policy_id in POLICIES else None
        found = search(req.question, pid)
        if not found and pid is not None:
            found = search(req.question, None)
        if not found:
            sections = (
                "; ".join(f"{s['id']} {s['title']}" for s in POLICIES[pid]["sections"])
                if pid
                else ""
            )
            return f"No clause matched. Sections: {sections or 'see the policy list'}. Say the wording does not say."
        return "\n".join(clause_text(p, s, c) for p, s, c, _ in found)

    async def mark_clause(self, req: MarkClause) -> str:
        """Open the policy document on screen and mark the clause that answers
        the customer's question, with your verdict."""
        if req.policy_id not in POLICIES:
            return f"No policy {req.policy_id!r}; policies: {', '.join(POLICIES)}."
        if clause(req.policy_id, req.clause_id) is None:
            return (
                f"No clause {req.clause_id} in {req.policy_id}. Use an id search_policy returned."
            )
        self._send(
            "policy.mark",
            {"policy_id": req.policy_id, "clause_id": req.clause_id, "verdict": req.verdict},
        )
        self.marked = (req.policy_id, req.clause_id)
        self.route = f"my-policies/{req.policy_id}"
        self.mode = "policies"
        self._landed("Here's the clause.", "यह रहा वह क्लॉज़।")
        return f"Clause {req.clause_id} of {req.policy_id} is marked on screen as {req.verdict}."

    async def open_policy(self, req: OpenPolicy) -> str:
        """Open one of the customer's policy documents on screen (optionally at a section)."""
        if req.policy_id not in POLICIES:
            return f"No policy {req.policy_id!r}; policies: {', '.join(POLICIES)}."
        args: dict[str, Any] = {"policy_id": req.policy_id}
        if req.section:
            args["section"] = req.section
        self._send("policy.open", args)
        self.route, self.mode = f"my-policies/{req.policy_id}", "policies"
        self._landed("Here's your policy.", "यह रही आपकी पॉलिसी।")
        sections = "; ".join(f"{s['id']} {s['title']}" for s in POLICIES[req.policy_id]["sections"])
        return f"{req.policy_id} is open. Sections: {sections}."

    @needs_result_now
    async def start_claim(self, req: StartClaim) -> str:
        """Open the claim form for a motor or health claim (and the policy, once
        known). Returns the form's sections and what to ask first."""
        ps = policies_for(cl.TYPES[req.claim_type]["products"])
        pid = req.policy_id
        if pid is not None and pid not in {p["id"] for p in ps}:
            return f"{pid} is not a {req.claim_type} policy. Options: {', '.join(p['id'] for p in ps)}."
        if pid is None and len(ps) == 1:
            pid = ps[0]["id"]
        self.claim.start(req.claim_type, pid)
        args: dict[str, Any] = {"claim_type": req.claim_type}
        if pid:
            args["policy_id"] = pid
        self._send("claim.start", args)
        self.route, self.mode = "claim", "claim"
        self._landed("The claim form is open.", "क्लेम फ़ॉर्म खुल गया है।")
        which = "" if pid else f" Ask which policy: {cl.policy_options_line(req.claim_type)}."
        return (
            f"The {req.claim_type} claim form is open.{which} Fields (✓ = filled):\n"
            f"{cl.outline(req.claim_type, self.claim)}\nNext: {self._next_ask()}"
        )

    @needs_result_now
    async def fill_claim(self, req: ClaimAnswers) -> str:
        """Fill the claim form on screen with every answer the customer gave.
        Returns what is still missing, so you ask only for that."""
        if self.claim.claim_type is None:
            return "No claim form is open: call start_claim first."
        order = list(cl.FIELDS)
        done: list[str] = []
        rejected: list[str] = []
        for a in sorted(
            req.answers, key=lambda a: order.index(a.field) if a.field in order else 999
        ):
            value, why = cl.normalise(a.field, a.value, self.claim, self.today)
            if value is None:
                rejected.append(f"{a.field} = {a.value!r} not taken: {why}")
                continue
            self.claim.values[a.field] = value
            self._send("claim.fill", {"field": a.field, "value": value})
            done.append(a.field)
        self._landed("That's filled in.", "यह भर दिया है।")
        out = f"Filled on screen: {', '.join(done) or 'nothing'}."
        if rejected:
            out += " " + " ".join(rejected) + "."
        return f"{out} {self._next_ask()}"

    def _next_ask(self) -> str:
        missing = self.claim.missing()
        if not missing:
            docs = ", ".join(d["label"] for d in self.claim.documents_needed()) or "none"
            return (
                "Every required field is filled: call review_claim. "
                f"Documents the customer still uploads: {docs}."
            )
        labels = "; ".join(f"{m} ({cl.FIELDS[m]['label']})" for m in missing[:4])
        return f"Still missing ({len(missing)}): {labels}. Ask for the next one or two in one short question."

    async def review_claim(self) -> str:
        """Check the whole claim form and open its review step. The customer
        ticks the declaration and presses Submit claim themselves."""
        missing = self.claim.missing()
        if self.claim.claim_type is None:
            return "No claim form is open: call start_claim first."
        if missing:
            return f"Not yet: still missing {', '.join(missing)}. Ask for them."
        self._send("claim.review")
        self._landed("Here's the review.", "यह रहा रिव्यू।")
        docs = ", ".join(d["label"] for d in self.claim.documents_needed()) or "none"
        return (
            f"The review step is open. Documents still to upload with the buttons on screen: {docs}. "
            "Then the customer ticks the declaration and presses Submit claim."
        )

    async def show_claim_section(self, req: ClaimSection) -> str:
        """Ring one section of the claim form (documents rings the uploads still missing)."""
        if req.section not in {s["id"] for s in cl.SECTIONS}:
            return f"No section {req.section!r}."
        self._send("claim.section", {"section": req.section})
        self._landed("It's this section here.", "यह वाला सेक्शन।")
        return f"Section {req.section} is ringed on screen."

    async def go_to(self, req: GoTo) -> str:
        """Take the customer to another page (and so to another job)."""
        page = req.page.strip("/") or "home"
        if page not in pages():
            return f"No page {page!r}. Pages: {', '.join(pages())}."
        self._send("site.go", {"page": page})
        self._arrive(page)
        self._landed("Here we are.", "यह रहा।")
        return f"Going to /{page}. Your job there: {JOBS[self.mode]}"

    async def set_language(self, req: LanguageRequest) -> str:
        """Switch the call to English or Hindi (listening and speaking) when the
        customer asks. Say one short line in the new language in the same response."""
        if req.language not in persona.LANGUAGES:
            return f"Not offered; languages: {', '.join(persona.LANGUAGES)}."
        if req.language == self.lang:
            return "The call is already in that language."
        configure_soon(self.session, self._speaking(req.language))
        return f"The call is now in {persona.LANGUAGES[req.language].label}."


#: Live calls by session id, for a redial to rejoin (rejoin.py).
REJOIN: Rejoin[InsuranceBrain] = Rejoin()
