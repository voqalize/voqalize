"""SugarBrain — the Sugar Coach daily diabetes check-in.

A :class:`voqalize.sdk.gemini.GeminiBrain` that runs the ``/sugar`` demo: a
diabetes-management program places a scheduled evening in-app call and the
assistant runs the daily habit check-in — logging meals by voice, confirming
exercise and medications, reviewing the glucose curve, nudging toward the care
plan, and ending with a summary card.

Two things worth calling out about how per-session state flows in:

  * **init** — the whole per-scenario patient picture (patient, care plan, recent
    logs, CGM status, prior-call summaries, TODAY'S CALL OBJECTIVE) arrives per
    session as ``session.init``. :meth:`SugarBrain.on_session_start` folds the
    PATIENT CONTEXT into the system instruction so every turn is grounded in it.
  * **the screen** — the brain keeps its own picture of the patient's phone. It is
    seeded from that same ``session.init`` (the day's meals, ticks and sensor are
    already in it), patched on every command this brain dispatches, and patched
    again when the patient does one of the two things they can do by hand — see
    ``app_events.py``. Nothing about the screen is pushed and nothing is appended
    to the context: :meth:`SugarBrain.on_rtvi` adds one line naming the *act*, and
    the screen itself is read through ``read_screen``. ``ScreenState.version``
    makes that safe rather than hopeful: a tool aimed at a screen the patient has
    moved since the coach last read refuses instead of acting. See
    ``voqalize_demos.screen``.

**The LLM generates the substantive data** (meal items, calorie estimates,
summary lines): each tool takes one pydantic model, and for thirteen of the
fourteen that model *is* the :class:`~voqalize.sdk.Action` the ``/sugar`` UI
renders — so the tool body is one ``self._show(...)`` line.
``switch_language`` moves both legs of the language instead of the screen.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel, Field, computed_field
from voqalize_demos import DEFAULT_MODEL, GeminiBrain, ScreenState, screen_prose

from voqalize.sdk import Action, RTVIMessage, Session
from voqalize.sdk.wire import Config, Language, SttConfig, TtsConfig, Voice

from .app_events import SUGAR_EVENTS, SensorOrderConfirmed, SugarEvent, VideoClosed

COACH_NAME = "Sugar Coach"


def _config(language: Language) -> Config:
    """Both legs, same language, same voice — one request, for ``switch_language``.

    Both of these languages have a recorded clip, so the legs never have to
    differ here. The session's *opening* language is not built here: it arrives
    as the page's connect-time ``config``, before this brain is dialled.
    """
    return Config(
        stt=SttConfig(language=language),
        tts=TtsConfig(language=language, voice=Voice.OMNIVOICE_GAURI),
    )


# The conversation language, by the name the screen calls it.
_LANG: dict[str, Language] = {
    "English": Language.EN,
    "Hindi": Language.HI,
}

# The opener, per language — a complete fixed sentence, not filled with the
# patient's name: the name arrives as free English text in session.init, and
# English interpolated into the Hindi line would mispronounce. A greeting is
# the one line spoken before any model has run, so it is written here, not
# generated.
_GREETING = {
    "English": "Hi there! Your evening check-in — how did today go?",
    "Hindi": "नमस्ते! आपकी शाम की चेक-इन — आज का दिन कैसा रहा?",
}

# Screen sections the assistant can highlight / that exist on the patient's
# "Today" screen (mirror frontend src/sugar/pages.tsx).
Section = Literal["glucose", "meals", "activity", "meds", "plan", "summary"]

MealType = Literal["breakfast", "lunch", "snack", "dinner", "other"]

# The two languages this coach speaks — the keys of ``_LANG`` above, as a type.
LanguageName = Literal["English", "Hindi"]


_SYSTEM_INSTRUCTION = f"""You are {COACH_NAME}, the daily check-in companion inside a diabetes-care program's mobile app. Each evening the app sends the patient a check-in nudge, and this patient just tapped Join. You are their habit coach — warm, familiar, unhurried — and YOU DRIVE THEIR SCREEN while you talk: what they tell you becomes structured logs they can see appearing live.

WHO YOU SERVE:
- One logged-in patient. A PATIENT CONTEXT message gives you everything: who they are, the care plan their doctor set, their recent logs, today's glucose readings, what you discussed on earlier calls, and TODAY'S CALL OBJECTIVE. Ground every sentence in it. Never ask for information the context already gives you — reference it ("I can see you logged breakfast, but nothing after that").
- The app nudged THEM to join. Open like a familiar coach continuing a relationship, not a stranger introducing a service.

YOUR TOOLS DRIVE THEIR SCREEN. Each one carries its own description — read it there; none of it is repeated here. Three rules sit on top of them: put a thing on screen BEFORE you ask about it (the chart, then the question); never narrate your own actions ("let me log that") — call the tool and let the screen speak; and in quiet mode call them in silence.

LANGUAGE:
- Start in the language named in the PATIENT CONTEXT (English or Hindi).
- English: clear, warm Indian English.
- Hindi: always Devanagari script. Write English health words in Devanagari too — never the Latin alphabet. Example: "आपने आज लंच में क्या खाया? मैं कैलोरी लॉग कर दूंगी।" (लंच, कैलोरी, लॉग are English words in Devanagari.)
- If the patient asks for the other language, switch it, then continue in it.
- Tool arguments that render ON SCREEN (meal item names, summary lines, commitments, notes) are ALWAYS in clean English, whatever the spoken language — the app UI is English.

VOICE OUTPUT — your words are read by a TTS that mangles digits and symbols:
- Your output goes straight to a TTS model, so write every word the way a person would SAY it out loud, never the way it's abbreviated in text. Expand acronyms and abbreviations and spell them out: "Doctor" not "Dr.", "milligrams" not "mg", "and so on" not "etc.", the words of the acronym not its letters. If you're unsure how it's spoken, write the spoken form.
- Numbers → words: "one hundred forty", never "140". Times → words: "around two thirty in the afternoon".
- No symbols, no markdown, no lists. Say "calories", "milligrams per decilitre" in words if ever needed — better, don't say units at all; the screen shows them.
- SHORT SENTENCES. Under ten words each, one thought per sentence. "Logged it. How about dinner?" beats a long compound sentence every time.
- NEVER more than two or three short sentences in a single turn — even when you have a lot you could say, pick the one thing that matters and stop. Lead with a tiny phrase so audio starts fast. The screen carries every detail; your voice only points at it ("that's logged — it's on your screen").
- FRIENDLY, not clinical: contractions, everyday words, a light "nice!" or "love that" where it's earned. You're a friend who happens to coach, not a nurse reading a form.
- NEVER recite what is on screen: no reading out calorie numbers, glucose values, med names or lists. Gesture at them instead.

MATCH THE MOMENT — your tone follows the conversation, turn by turn:
- A win (commitment kept, honest log, good day) → bright and celebratory, let it land before moving on.
- Struggling, tired, or stressed → slower and softer; drop the checklist for a beat and just be with them. Shrink the next ask.
- A routine day → light and brisk; in and out, no ceremony.
- Never scold, never lecture, never sound scripted.

HOW MUCH YOU TALK — the PATIENT CONTEXT carries a "talk_mode". It changes how much you lead, NOT the two-or-three-short-sentence ceiling, which always holds:

- talk_mode "quiet" (a familiar, routine day — the patient knows the drill): you are TAKING DICTATION, not interviewing. Open with a warm hello and a tiny "go ahead" — that's the whole greeting. Then GO QUIET and let them narrate the whole day in their own order. Log everything SILENTLY as they talk — call the tools, say NOTHING, or at most a four-word acknowledgement ("Got it." / "Nice one."). DO NOT ask a question after each item; do not react to every thing they mention. Across the WHOLE call you get at most ONE real question — tomorrow's commitment — and only if it doesn't already flow from what they've told you (often it does — infer it). Nudge once ONLY if they truly stall ("...and dinner?"). The closing/summary turn is ONE short warm line. When in doubt in quiet mode, say less or nothing and let the tools do the talking.
    Patient: "Evening. Usual day — idli for breakfast, the office thali at lunch, and I got my morning walk in."
    You: "Evening, Rajesh. Go on, I'm listening." [then SILENTLY: log breakfast, log lunch, log the walk — no spoken reply]
    Patient: "Dinner will be two rotis and dal."
    You: [silently log dinner] "Got it."
    Patient: "That's it for me."
    You: "One small thing for tomorrow?" [set the commitment, show the summary, short goodbye]

- talk_mode "guided" (onboarding, a hard restart, or someone who needs a hand): you lead gently, ONE small step at a time. Greet, then one question; walk them through the day beat by beat — but still only two or three short sentences per turn. Speak a short line before a tool call, so the screen never updates into silence.
    You: "Good evening, Meera. Saw you logged breakfast — lovely start. What did lunch look like?"
    Patient: "Curd rice, around one thirty."
    You: "Logged it. And did the evening walk happen?"

If talk_mode is missing, default to quiet.

YOU GENERATE THE DATA. There is no food database on this call — you are it. Estimate calories for Indian home food sensibly and consistently (a roti around eighty to one hundred calories, a katori of dal around one hundred fifty, a bowl of white rice around two hundred, a samosa around two hundred sixty, filter coffee with sugar around sixty). Round to friendly numbers. Quantities in the units the patient used (rotis, katoris, bowls, cups, pieces).

SAFETY — HARD LINES YOU NEVER CROSS. You are a habit coach, NOT a doctor, nurse, or dietician:
- NEVER give medical advice: no diagnosing, no interpreting symptoms or readings ("is that dangerous?"), no medication guidance of any kind (doses, timing changes, skipping, alternatives), no new diets or treatments.
- You only ever RESTATE the doctor's existing plan: "your plan says...", "Doctor Rao has you down for...". Never "you should..." about anything clinical.
- If the patient asks anything medical, warmly decline and route it: say it's a question for their care team, flag it so it reaches them, and tell the patient it's been flagged. This is one sentence, not a lecture.
- If the patient mentions feeling unwell in a way that could be urgent (dizzy, faint, chest pain, a reading that scares them), tell them plainly to contact their doctor or emergency services right away, flag it, and do not continue the routine check-in until they're okay to.
- Glucose talk stays observational and curious, never evaluative: "there was a rise after lunch — what did you have?" not "that spike is bad". Never attach medical meaning to a number.
- Nudges stay inside the established plan: the walk their plan already prescribes, a video from the library, a diet swap the doctor's plan itself lists. Frame nudges as easy invitations, never pressure. One nudge, gracefully accepted or dropped.

THE CHECK-IN — a five-minute evening ritual. Adapt to TODAY'S CALL OBJECTIVE in the context, but the natural arc is:
1. Warm open, grounded in their day ("how did the evening walk go?" / "saw you logged breakfast — how was the rest of the day?").
2. Food: fill the day's gaps, logging as they talk. In quiet mode let them list the whole day and log each one silently; in guided mode take it one meal at a time.
3. Activity: what moved today. If nothing did, one gentle nudge — a fifteen-minute walk now, or a video from the library the PATIENT CONTEXT lists. If they take the video, let it run.
4. Medications: confirm today's doses from the plan, mark each.
5. Glucose: if the context lists a notable event today, show the chart. In GUIDED mode, add the one curious, observational question. In QUIET mode, show it SILENTLY and ask nothing — the patient already narrated the food; do not spend your one question here.
6. Commitment: close with ONE small, specific commitment for tomorrow — their words, not yours, whenever possible.
7. Wrap: show the summary and say a short, warm goodbye. Mention tomorrow's call.

If the context says the patient's glucose sensor has expired, weave the replacement in naturally somewhere: their chart has a gap, and you miss the data that helps your coaching. It is a continuity nudge, never a hard sell — if they decline, drop it gracefully.

Skip or reorder beats the objective makes irrelevant. An onboarding call replaces beats two to five with walking through the care plan (highlight the plan section, confirm they know their meds and targets, set the daily call time expectation).

STAY GROUNDED: nothing in this conversation is a picture of the patient's screen. read_screen() is the only one, and it is free and silent — it takes no floor, says nothing, and moves nothing. Call it before you act on or refer to anything already on screen (what's logged, what's ticked, what they tapped), and whenever you are told they changed it themselves — you are told THAT they changed it, never what it now says. If a tool refuses because the screen moved under you, that is not something to report or apologise for: read the screen and make the call again.

Open per TODAY'S CALL OBJECTIVE: greet by first name as their {COACH_NAME} — familiar, one or two short sentences, in the context's language, grounded in something real from their recent days."""


# ── The tool surface: one pydantic model per tool ──────────────────────────────
#
# Each class below is declared to Gemini straight from itself: the fields are the
# parameters and every ``Field(description=...)`` reaches the model verbatim. The
# *tool's* own description is the docstring on the method that takes it — one
# sentence of instruction, in one place — so nothing here is written twice.
#
# Thirteen of the fourteen are an ``Action``, which means the validated call is
# also the payload the browser renders: one class, one schema, one place to
# change the shape.
#
# The browser's half of these shapes is generated from them, not written:
#
#     voqalize types sugar/backend/brain.py -o sugar/frontend/src/actions.gen.ts
#
# CI regenerates and diffs, so a field added here without that command is a
# failed build rather than a screen that quietly renders ``undefined``.


class MealItem(BaseModel):
    name: str = Field(description="Food item in clean English, e.g. 'Roti' or 'Dal (katori)'.")
    quantity: str = Field(
        description="Quantity in the patient's units, e.g. '2', '1 katori', '1 bowl'."
    )
    calories: int = Field(
        description="Your calorie estimate for that quantity, rounded to a friendly number."
    )


class LogMeal(Action):
    meal_type: MealType = Field(description="Which meal of the day this is.")
    time_label: str = Field(
        description="When they ate, as shown on screen, e.g. '1:30 PM' or 'around 2 PM'."
    )
    items: list[MealItem] = Field(
        min_length=1, description="The foods with quantities and your calorie estimates."
    )
    note: str = Field("", description="Optional one-line note, e.g. 'ate out — office canteen'.")

    @computed_field
    @property
    def total_calories(self) -> int:
        """Summed here rather than asked of the model, so the number on screen is
        always the sum of the items shown under it — and, being computed, it is
        absent from the schema Gemini is given and present in the payload the
        browser renders. That is the whole reason this is one class and not two."""
        return sum(item.calories for item in self.items)


class LogActivity(Action):
    kind: str = Field(description="Activity in English, e.g. 'Walk', 'Yoga', 'Desk stretches'.")
    duration_min: int = Field(description="Duration in minutes.")
    time_label: str = Field(description="When, e.g. '7:00 AM' or 'now'.")
    note: str = Field("", description="Optional one-line note.")


class MarkMedication(Action):
    name: str = Field(description="Medication name from the care plan, e.g. 'Metformin 500mg'.")
    status: Literal["taken", "missed", "skipped"] = Field(description="What the patient reported.")
    time_label: str = Field(
        "", description="When they took it, if they said, e.g. 'after breakfast'."
    )


class ShowGlucose(Action):
    focus_time_label: str = Field(
        "", description="Event time to zoom/highlight, e.g. '2:15 PM'. Omit for the whole day."
    )
    note: str = Field(
        "",
        description="Optional short on-screen label for the highlight, e.g. 'Rise after lunch'.",
    )


class PlayVideo(Action):
    video_id: str = Field(description="Library video id from the PATIENT CONTEXT.")
    start_sec: int = Field(0, description="Second to start from. Omit to start at the beginning.")


class PauseVideo(Action):
    pass


class ResumeVideo(Action):
    pass


class SetCommitment(Action):
    text: str = Field(
        description="The commitment, short and specific, e.g. 'Fifteen-minute walk after dinner'."
    )
    when: str = Field("", description="When they'll do it, e.g. 'tomorrow evening'.")


class FlagForCareTeam(Action):
    topic: str = Field(description="Short topic in English, e.g. 'Metformin dose question'.")
    detail: str = Field(
        description="One or two lines of what the patient asked or reported, in English."
    )


class ShowSensorRenewal(Action):
    pass


class ConfirmSensorOrder(Action):
    pass


class ShowSummary(Action):
    lines: list[str] = Field(
        min_length=1,
        description=(
            "Three to five short lines capturing the day, e.g. 'Lunch and dinner logged "
            "— about 1,400 kcal', 'Evening walk: 20 minutes', 'All medications taken'."
        ),
    )
    flagged: str = Field(
        "", description="If anything was flagged to the care team, one short line naming it."
    )


class Highlight(Action):
    section: Section = Field(description="Which section to highlight.")


class SwitchLanguage(BaseModel):
    language: LanguageName = Field(description="Target language.")


type ScreenMove = (
    LogMeal
    | LogActivity
    | MarkMedication
    | ShowGlucose
    | PlayVideo
    | PauseVideo
    | ResumeVideo
    | SetCommitment
    | FlagForCareTeam
    | ShowSensorRenewal
    | ConfirmSensorOrder
    | ShowSummary
    | Highlight
)
"""Every command that moves the patient's phone.

Narrower than ``Action`` on purpose: :meth:`SugarBrain._mirror` matches on this,
so a fourteenth command added and not mirrored is a type error rather than a
picture that has quietly stopped agreeing with the screen."""


def _meal_line(meal: LogMeal) -> dict[str, Any]:
    """A logged meal as the food log shows it — the items, not their calories."""
    return {
        "meal": meal.meal_type,
        "time": meal.time_label,
        "items": [f"{i.name} \u00d7 {i.quantity}" for i in meal.items],
        "total_kcal": meal.total_calories,
    }


def _blank_screen() -> dict[str, Any]:
    return {
        "the meals logged": [],
        "the activity logged": [],
        "the medication ticks": [],
        "the commitment": None,
        "what is flagged for the care team": [],
        "the sensor order": "none",
        "the video": None,
        "whether the summary is up": False,
    }


class SugarBrain(GeminiBrain):
    """One per session. The Sugar Coach daily check-in: LLM + habit-logging tools
    + this session's patient/screen state.

    The per-scenario patient picture arrives as ``session.init`` and is folded
    into the system instruction in :meth:`on_session_start`. The patient's own
    taps reach :meth:`on_rtvi` as typed events, one gesture at a time, and the
    coach reads the screen back when she needs it."""

    # This coach's language is the patient's own LanguageToggle choice, and the
    # page sends it at connect: ``config`` moves both legs of the wire before
    # this brain is dialled, and ``session.init["language"]`` says which language
    # to greet and reason in. So there is nothing to configure at session start
    # — the session already opened in it. What stays here is the change of mind:
    # ``switch_language`` moves the wire mid-call, which is the one part of this
    # that is a runtime event.

    def __init__(self, *, client: genai.Client, model: str = DEFAULT_MODEL) -> None:
        # The base system instruction only; the PATIENT CONTEXT is folded in per
        # session in on_session_start once session.init has arrived.
        super().__init__(client=client, system_instruction=_SYSTEM_INSTRUCTION, model=model)
        # Per-session state (populated on_session_start from session.init).
        # Ephemeral in memory — no resume across disconnects, by design.
        self.patient_name = "there"
        self.language_name = "English"
        self.talk_mode = "quiet"
        self.nudge = ""
        # What is on the patient's screen. This is the only copy: it is read
        # through ``read_screen`` and never appended to the model's context.
        self.screen = ScreenState(read_tool="read_screen", actor="patient")
        #: The brain's own picture of the phone — seeded from ``session.init``,
        #: patched by :meth:`_mirror` and :meth:`apply_event`.
        self.mirror = _blank_screen()

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        """Read the seeded scenario (``session.init``) and fold the PATIENT
        CONTEXT into the system instruction so every turn is grounded in it."""
        payload = dict(session.init or {})
        raw_scenario = payload.get("scenario")
        scenario: dict[str, Any] = raw_scenario if isinstance(raw_scenario, dict) else {}
        raw_patient = scenario.get("patient")
        patient = raw_patient if isinstance(raw_patient, dict) else {}
        self.patient_name = str(patient.get("name") or "").strip() or "there"
        language = str(payload.get("language", "")).strip()
        # Which language to write in. The wire is already in it — the page sent
        # `config` at connect — so this only has to agree with what the session
        # opened as, and "English" is what an absent or unknown name opened as
        # too. Getting these two out of step is the silent failure: the coach
        # writing Devanagari that an English reference clip reads aloud, right on
        # paper and foreign-accented in the ear.
        self.language_name = language if language in _LANG else "English"
        # How much the coach leads vs. listens. "quiet" = the patient narrates
        # and we log silently; "guided" = we walk them through beat by beat.
        # Either way the two-or-three-sentence ceiling holds. Default quiet.
        mode = str(scenario.get("talk_mode", "")).strip().lower()
        self.talk_mode = mode if mode in ("quiet", "guided") else "quiet"
        # The push-notification the patient just tapped Join on. The opener
        # continues naturally from it (it also cued them on what to say).
        self.nudge = str(scenario.get("joined_from_nudge", "")).strip()

        # The day the patient walks in with. It is already in front of us — the
        # page put it in ``init`` — so the mirror is built from it rather than
        # waiting for the browser to hand back what it was given.
        raw_today = scenario.get("today")
        today: dict[str, Any] = raw_today if isinstance(raw_today, dict) else {}
        self.mirror = _blank_screen() | {
            "the meals logged": today.get("logged_meals") or [],
            "the activity logged": today.get("logged_activity") or [],
            "the medication ticks": today.get("medications") or [],
        }

        # Fold the whole per-scenario picture into the system instruction: it is
        # true for the whole call and never changes, so it belongs where it is
        # written once, not in an append that would sit in the context.
        context_block = (
            "PATIENT CONTEXT (authoritative — everything you know about this patient and "
            f"today's call; the conversation language is {self.language_name}): "
            + json.dumps(scenario, ensure_ascii=False)
        )
        self.system_instruction = f"{_SYSTEM_INSTRUCTION}\n\n{context_block}"
        logger.info(
            "sugar: session start — patient={!r}, language={}, talk_mode={}",
            self.patient_name,
            self.language_name,
            self.talk_mode,
        )

    async def greet(self, session: Session) -> str:
        """The opener, written not generated: the patient tapped Join on a nudge
        that already told them what to do, so the coach says hello and hands them
        the floor. It does not say the patient's name — that arrives as free
        English text, and English read into the Hindi line mispronounces."""
        return _GREETING[self.language_name]

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Browser→brain message: one thing the patient just did with their thumb.

        Silent by construction — the mirror moves and one line goes into the
        context, but no floor is taken and no turn starts. A tap does not mean
        they stopped talking."""
        event = SUGAR_EVENTS.parse(msg)
        if event is None:
            return
        logger.info("sugar: {}", type(event).__voqal_event__)
        note = self.apply_event(event)
        self.append_to_context(types.Content(role="user", parts=[types.Part(text=note)]))

    # ─── Browser → brain: what the patient did by hand ──────────────────

    def apply_event(self, event: SugarEvent) -> str:
        """Fold one gesture into the mirror and say what to tell the model.

        The note names the act and never its values — the screen behind it is read
        through ``read_screen``, which is what keeps it from going stale in the
        context. No fallback arm: a gesture added to :data:`SugarEvent` and not
        handled here is a type error rather than a silent drop."""
        match event:
            case SensorOrderConfirmed():
                self.mirror["the sensor order"] = "ordered"
                return self.screen.moved("confirmed the sensor order by tapping the card")
            case VideoClosed():
                self.mirror["the video"] = None
                return self.screen.moved("closed the video")

    def _show(self, action: ScreenMove) -> None:
        """Put something on screen — and into the mirror, in the same breath.

        Nothing comes back to say a command landed, and nothing needs to. That is
        also why a gesture can be taken at face value: an event is always the
        patient, never this brain's own command echoing home."""
        self._mirror(action)
        self.session.dispatch(action)

    def _mirror(self, action: ScreenMove) -> None:
        """Move the mirror the way this dispatch is about to move the phone."""
        match action:
            case LogMeal():
                meals = self.mirror["the meals logged"]
                line = _meal_line(action)
                # A re-log of the same meal is a correction, exactly as the
                # browser treats it — it replaces, rather than logging twice.
                for i, m in enumerate(meals):
                    if m.get("meal") == action.meal_type:
                        meals[i] = line
                        break
                else:
                    meals.append(line)
            case LogActivity():
                self.mirror["the activity logged"].append(
                    f"{action.kind}, {action.duration_min} min ({action.time_label})"
                )
            case MarkMedication():
                wanted = action.name.lower()
                for med in self.mirror["the medication ticks"]:
                    name = str(med.get("name", "")).lower()
                    if name and (name in wanted or wanted in name):
                        med["status"] = action.status
            case SetCommitment():
                self.mirror["the commitment"] = {"text": action.text, "when": action.when}
            case FlagForCareTeam():
                self.mirror["what is flagged for the care team"].append(action.topic)
            case ShowSensorRenewal():
                if self.mirror["the sensor order"] != "ordered":
                    self.mirror["the sensor order"] = "offered"
            case ConfirmSensorOrder():
                self.mirror["the sensor order"] = "ordered"
            case ShowSummary():
                self.mirror["whether the summary is up"] = True
            case PlayVideo():
                self.mirror["the video"] = {"id": action.video_id, "playing": True}
            case PauseVideo():
                if isinstance(video := self.mirror["the video"], dict):
                    video["playing"] = False
            case ResumeVideo():
                if isinstance(video := self.mirror["the video"], dict):
                    video["playing"] = True
            case ShowGlucose() | Highlight():
                # Where the eye is pointed, not what anyone decided.
                pass

    # ─── Tools ──────────────────────────────────────────────────────────
    #
    # The model calls these directly. Each one takes its own pydantic model,
    # already validated, and drives the browser through ``self.session`` — a
    # brain is one instance per call, so the session is simply there, and the
    # ``ui-command`` is stamped with the turn the model is answering.
    #
    # They return "ok" and nothing more. A tool result is prompt the model pays
    # for on every following turn, and "logged, meal_type=lunch" only tells it
    # what it just said. ``log_meal`` is the exception: the total is the one
    # thing the tool knows and the model does not.

    @property
    def tools(self) -> list[Any]:
        """The fifteen the coach may call. Fourteen drive the patient's screen;
        ``read_screen`` reads it back."""
        return [
            self.read_screen,
            self.log_meal,
            self.log_activity,
            self.mark_medication,
            self.show_glucose,
            self.play_video,
            self.pause_video,
            self.resume_video,
            self.set_commitment,
            self.flag_for_care_team,
            self.show_sensor_renewal,
            self.confirm_sensor_order,
            self.show_summary,
            self.highlight,
            self.switch_language,
        ]

    async def read_screen(self) -> str:
        """What the patient is looking at right now — everything logged today, the
        med ticks, the sensor card, and anything they tapped by hand.

        Call it before you act on or refer to something already on screen, and
        whenever you are told they changed it themselves. It is free — it reads this
        session's own state, takes no floor, says nothing, and moves nothing."""
        self.screen.read()
        logger.info("sugar: read_screen (v{})", self.screen.version)
        return screen_prose({"screen": "check-in", **self.mirror}, actor="patient")

    async def log_meal(self, meal: LogMeal) -> str:
        """Log a meal the patient just described — it appears in their food log with
        your calorie estimates. Call it the moment they finish describing it; call
        again with corrected items if they amend. Item names in English."""
        self._show(meal)
        return f"ok, {meal.total_calories} calories"

    async def log_activity(self, activity: LogActivity) -> str:
        """Log physical activity the patient did, or commits to doing right now —
        it appears in their activity log."""
        self._show(activity)
        return "ok"

    async def mark_medication(self, med: MarkMedication) -> str:
        """Mark one of today's planned medications as taken, missed, or skipped, as
        the patient confirms. Use the name exactly as it appears in the care plan.
        Call once per medication."""
        stale = self.screen.stale()
        if stale:
            return stale
        self._show(med)
        return "ok"

    async def show_glucose(self, chart: ShowGlucose) -> str:
        """Bring the day's glucose chart on screen, optionally zoomed to one event.
        Call this BEFORE asking about a reading ("what did you have around two?")
        so the patient is looking at the moment you mean."""
        self._show(chart)
        return "ok"

    async def play_video(self, video: PlayVideo) -> str:
        """Play a video from the in-app library (ids in the PATIENT CONTEXT) inside
        the app, with sound. Introduce it in a few words first."""
        self._show(video)
        return "ok"

    async def pause_video(self) -> str:
        """Pause the playing video, e.g. when the patient wants to talk."""
        self._show(PauseVideo())
        return "ok"

    async def resume_video(self) -> str:
        """Resume the paused video."""
        self._show(ResumeVideo())
        return "ok"

    async def set_commitment(self, commitment: SetCommitment) -> str:
        """Save the ONE small commitment the patient makes for tomorrow. It appears
        on their summary and you will see it in the next call's context. Their
        words, in English."""
        self._show(commitment)
        return "ok"

    async def flag_for_care_team(self, flag: FlagForCareTeam) -> str:
        """Flag a medical question or concern to the patient's care team — anything
        you must not answer yourself (doses, symptoms, interpreting readings, diet
        changes beyond the plan). A chip appears on screen; tell the patient it has
        been flagged."""
        self._show(flag)
        return "ok"

    async def show_sensor_renewal(self) -> str:
        """Put the glucose-sensor replacement card on screen — only when the context
        says the sensor has expired. The patient can confirm by voice or by tapping
        the card themselves."""
        self._show(ShowSensorRenewal())
        return "ok"

    async def confirm_sensor_order(self) -> str:
        """Place the sensor replacement order, after the patient clearly agrees BY
        VOICE. If they tapped the card themselves the screen state shows it — do
        not call this too."""
        stale = self.screen.stale()
        if stale:
            return stale
        self._show(ConfirmSensorOrder())
        return "ok"

    async def show_summary(self, summary: ShowSummary) -> str:
        """Show the end-of-call summary card as you wrap up: the day in a few lines,
        plus the commitment. Call this right before your goodbye. Lines in English."""
        stale = self.screen.stale()
        if stale:
            return stale
        self._show(summary)
        return "ok"

    async def highlight(self, target: Highlight) -> str:
        """Scroll to and briefly highlight one section of the patient's screen, so
        their eye follows you."""
        stale = self.screen.stale()
        if stale:
            return stale
        self._show(target)
        return "ok"

    async def switch_language(self, to: SwitchLanguage) -> str:
        """Switch the conversation language when the patient asks. Acknowledge their
        request in one short sentence in the target language first."""
        language = _LANG[to.language]
        self.language_name = to.language
        logger.info("sugar: switch_language → {} ({})", to.language, language.value)
        # One request moves both halves — recognizer and voice — so there is no
        # moment where the call is half in each. Awaited because the model gets
        # the answer Voqalize gave, not the one we hoped for.
        await self.session.configure(_config(language))
        return "ok"
