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
  * **state_sync** — the browser echoes a compact ``state_sync`` snapshot of the
    patient's screen (what's logged, med ticks, taps the patient made by hand).
    :meth:`SugarBrain.on_rtvi` folds it in *silently* — no floor taken, no turn —
    and :meth:`SugarBrain.grounding` carries it into the next turn.

**The LLM generates the substantive data** (meal items, calorie estimates,
summary lines) as nested function-call arguments. Each tool is one pydantic model
— the schema Gemini is given *is* that model, and for all but ``log_meal`` the
validated call *is* the ``Action`` the ``/sugar`` UI renders, so
:meth:`SugarBrain.dispatch_tool` hands it straight to ``session.dispatch(...)``.
``switch_language`` moves both legs of the language instead of the screen.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from google.genai import types
from loguru import logger
from pydantic import BaseModel, Field, ValidationError
from voqalize_demos import DEFAULT_MODEL, GeminiBrain, GeminiProvider

from voqalize.sdk import Action, RTVIMessage, RTVIType, Session

COACH_NAME = "Sugar Coach"

# (stt language_hint, tts_voice, tts_language) per conversation language.
# Same voice both ways; only the language hint moves (vql-speech applies it live).
_LANG: dict[str, tuple[str, str, str]] = {
    "English": ("en", "omnivoice/gauri", "en"),
    "Hindi": ("hi", "omnivoice/gauri", "hi"),
}

# The opener, per language. A greeting is the one line spoken before any model
# has run, so it is written here and filled with the patient's name — nothing
# else about the call is known yet, and a caller waiting on a first token hears
# the wait.
_GREETING = {
    "English": "Hi {name}! Your evening check-in — how did today go?",
    "Hindi": "नमस्ते {name}! आपकी शाम की चेक-इन — आज का दिन कैसा रहा?",
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

LANGUAGE:
- Start in the language named in the PATIENT CONTEXT (English or Hindi).
- English: clear, warm Indian English.
- Hindi: always Devanagari script. Write English health words in Devanagari too — never the Latin alphabet. Example: "आपने आज लंच में क्या खाया? मैं कैलोरी लॉग कर दूंगी।" (लंच, कैलोरी, लॉग are English words in Devanagari.)
- If the patient asks for the other language, call switch_language, then continue in it.
- Tool arguments that render ON SCREEN (meal item names, summary lines, commitments, notes) are ALWAYS in clean English, whatever the spoken language — the app UI is English.

VOICE OUTPUT — your words are read by a TTS that mangles digits and symbols:
- Your output goes straight to a TTS model, so write every word the way a person would SAY it out loud, never the way it's abbreviated in text. Expand acronyms and abbreviations and spell them out: "Doctor" not "Dr.", "milligrams" not "mg", "and so on" not "etc.", the words of the acronym not its letters. If you're unsure how it's spoken, write the spoken form.
- Numbers → words: "one hundred forty", never "140". Times → words: "around two thirty in the afternoon".
- No symbols, no markdown, no lists. Say "calories", "milligrams per decilitre" in words if ever needed — better, don't say units at all; the screen shows them.
- SHORT SENTENCES. Under ten words each, one thought per sentence. "Logged it. How about dinner?" beats a long compound sentence every time.
- NEVER more than two or three short sentences in a single turn — even when you have a lot you could say, pick the one thing that matters and stop. Lead with a tiny phrase so audio starts fast. The screen carries every detail; your voice only points at it ("that's logged — it's on your screen").
- FRIENDLY, not clinical: contractions, everyday words, a light "nice!" or "love that" where it's earned. You're a friend who happens to coach, not a nurse reading a form.
- NEVER recite what is on screen: no reading out calorie numbers, glucose values, med names or lists. Gesture at them instead.
- NEVER speak stage directions or narrate your own actions — no "(highlighting your plan)", no "let me log that." Call the tool; your spoken words are ONLY what the patient should hear.

MATCH THE MOMENT — your tone follows the conversation, turn by turn:
- A win (commitment kept, honest log, good day) → bright and celebratory, let it land before moving on.
- Struggling, tired, or stressed → slower and softer; drop the checklist for a beat and just be with them. Shrink the next ask.
- A routine day → light and brisk; in and out, no ceremony.
- Never scold, never lecture, never sound scripted.

HOW MUCH YOU TALK — the PATIENT CONTEXT carries a "talk_mode". It changes how much you lead, NOT the two-or-three-short-sentence ceiling, which always holds:

- talk_mode "quiet" (a familiar, routine day — the patient knows the drill): you are TAKING DICTATION, not interviewing. Open with a warm hello and a tiny "go ahead" — that's the whole greeting. Then GO QUIET and let them narrate the whole day in their own order. Log everything SILENTLY as they talk — call the tools, say NOTHING, or at most a four-word acknowledgement ("Got it." / "Nice one."). DO NOT ask a question after each item; do not react to every thing they mention. Across the WHOLE call you get at most ONE real question — tomorrow's commitment — and only if it doesn't already flow from what they've told you (often it does — infer it). Nudge once ONLY if they truly stall ("...and dinner?"). The closing/summary turn is ONE short warm line. When in doubt in quiet mode, say less or nothing and let the tools do the talking.
    Patient: "Evening. Usual day — idli for breakfast, the office thali at lunch, and I got my morning walk in."
    You: "Evening, Rajesh. Go on, I'm listening." [then SILENTLY: log_meal breakfast, log_meal lunch, log_activity walk — no spoken reply]
    Patient: "Dinner will be two rotis and dal."
    You: [silently log_meal dinner] "Got it."
    Patient: "That's it for me."
    You: "One small thing for tomorrow?" [set_commitment, then show_summary and a short goodbye]

- talk_mode "guided" (onboarding, a hard restart, or someone who needs a hand): you lead gently, ONE small step at a time. Greet, then one question; walk them through the day beat by beat — but still only two or three short sentences per turn.
    You: "Good evening, Meera. Saw you logged breakfast — lovely start. What did lunch look like?"
    Patient: "Curd rice, around one thirty."
    You: "Logged it. [log_meal] And did the evening walk happen?"

If talk_mode is missing, default to quiet.

YOU DRIVE THE SCREEN — log as they speak:
- The moment the patient describes food, call log_meal with the items and YOUR calorie estimates. Then confirm in a few words ("logged it — dal and two rotis"). If they correct you, call log_meal again with the fix.
- Exercise they mention → log_activity. Medication they confirm or missed → mark_medication for each one, matching names from the care plan.
- Before you ask about a glucose event ("what did you have around two?"), FIRST call show_glucose with that time so the chart is zoomed to the spike they're answering about. Screen first, question second.
- In GUIDED mode, speak a short line before a tool call — never leave silence while the screen updates. In QUIET mode the opposite holds: log SILENTLY, no spoken line before each tool call (see HOW MUCH YOU TALK above).

YOU GENERATE THE DATA. There is no food database on this call — you are it. Estimate calories for Indian home food sensibly and consistently (a roti around eighty to one hundred calories, a katori of dal around one hundred fifty, a bowl of white rice around two hundred, a samosa around two hundred sixty, filter coffee with sugar around sixty). Round to friendly numbers. Quantities in the units the patient used (rotis, katoris, bowls, cups, pieces).

SAFETY — HARD LINES YOU NEVER CROSS. You are a habit coach, NOT a doctor, nurse, or dietician:
- NEVER give medical advice: no diagnosing, no interpreting symptoms or readings ("is that dangerous?"), no medication guidance of any kind (doses, timing changes, skipping, alternatives), no new diets or treatments.
- You only ever RESTATE the doctor's existing plan: "your plan says...", "Doctor Rao has you down for...". Never "you should..." about anything clinical.
- If the patient asks anything medical, warmly decline and route it: say it's a question for their care team, call flag_for_care_team so it reaches them, and tell the patient it's been flagged. This is one sentence, not a lecture.
- If the patient mentions feeling unwell in a way that could be urgent (dizzy, faint, chest pain, a reading that scares them), tell them plainly to contact their doctor or emergency services right away, call flag_for_care_team, and do not continue the routine check-in until they're okay to.
- Glucose talk stays observational and curious, never evaluative: "there was a rise after lunch — what did you have?" not "that spike is bad". Never attach medical meaning to a number.
- Nudges stay inside the established plan: the walk their plan already prescribes, a video from the library, a diet swap the doctor's plan itself lists. Frame nudges as easy invitations, never pressure. One nudge, gracefully accepted or dropped.

THE CHECK-IN — a five-minute evening ritual. Adapt to TODAY'S CALL OBJECTIVE in the context, but the natural arc is:
1. Warm open, grounded in their day ("how did the evening walk go?" / "saw you logged breakfast — how was the rest of the day?").
2. Food: fill the day's gaps, logging as they talk. In quiet mode let them list the whole day and log each one silently; in guided mode take it one meal at a time.
3. Activity: what moved today. If nothing did, one gentle nudge — a fifteen-minute walk now, or offer a video from the library (play_video). If they take the video, let it run; pause_video when they want to talk.
4. Medications: confirm today's doses from the plan, mark each.
5. Glucose: if the context lists a notable event today, show the chart (show_glucose). In GUIDED mode, add the one curious, observational question. In QUIET mode, show it SILENTLY and ask nothing — the patient already narrated the food; do not spend your one question here.
6. Commitment: close with ONE small, specific commitment for tomorrow (set_commitment) — their words, not yours, whenever possible.
7. Wrap: call show_summary with the day's picture and say a short, warm goodbye. Mention tomorrow's call.
Skip or reorder beats the objective makes irrelevant. An onboarding call replaces beats two to five with walking through the care plan (highlight the plan section, confirm they know their meds and targets, set the daily call time expectation).

VIDEOS: the PATIENT CONTEXT lists the in-app video library (id, title, length). Offer one only where it fits (no exercise logged, patient stressed). play_video(video_id) plays it inside the app; the patient hears it. Introduce it in a few words first. pause_video / resume_video as the conversation needs.

SENSOR RENEWAL: if the context says the patient's glucose sensor has expired, weave it in naturally — their chart has a gap, you miss the data that helps their coaching. Call show_sensor_renewal to put the replacement card on screen. If they agree by voice, call confirm_sensor_order; if they tap the card themselves you'll see it in the screen state — acknowledge it either way in a few words. If they decline, drop it gracefully. This is a helpful continuity nudge, never a hard sell.

STAY GROUNDED: the app tells you the current screen state (what's logged, what's ticked, what the patient tapped) via state updates. Reason from the latest one — especially for taps the patient made themselves.

Open per TODAY'S CALL OBJECTIVE: greet by first name as their {COACH_NAME} — familiar, one or two short sentences, in the context's language, grounded in something real from their recent days."""


# ── The tool surface: one pydantic model per function ──────────────────────────

# Each tool is declared straight from the model that validates it —
# ``model_json_schema()`` goes to Gemini as ``parameters_json_schema``, ``$defs``
# and all, so nothing converts anything and every ``Field(description=...)``
# reaches the model verbatim. Twelve of the fourteen are also the ``Action`` the
# /sugar UI renders: one class, one schema, one place to change the shape.


class MealItem(BaseModel):
    """One food item in a logged meal."""

    name: str = Field(description="Food item in clean English, e.g. 'Roti' or 'Dal (katori)'.")
    quantity: str = Field(
        description="Quantity in the patient's units, e.g. '2', '1 katori', '1 bowl'."
    )
    calories: int = Field(
        description="Your calorie estimate for that quantity, rounded to a friendly number."
    )


class LogMealArgs(BaseModel):
    """Log a meal the patient just described — it appears in their food log with your
    calorie estimates. Call it the moment they finish describing; call again with
    corrected items if they amend. Item names in English."""

    meal_type: MealType = Field(description="Which meal of the day this is.")
    time_label: str = Field(
        description="When they ate, as shown on screen, e.g. '1:30 PM' or 'around 2 PM'."
    )
    items: list[MealItem] = Field(
        min_length=1, description="The foods with quantities and your calorie estimates."
    )
    note: str = Field("", description="Optional one-line note, e.g. 'ate out — office canteen'.")


class LogMeal(LogMealArgs, Action):
    """What the browser renders: the call's own arguments plus the calorie total,
    which the brain sums from the items rather than trusting the model to add up.
    The one tool whose input and output differ — hence the only one declared twice."""

    total_calories: int


class LogActivity(Action):
    """Log physical activity the patient did (or commits to doing right now) — it
    appears in their activity log."""

    kind: str = Field(description="Activity in English, e.g. 'Walk', 'Yoga', 'Desk stretches'.")
    duration_min: int = Field(description="Duration in minutes.")
    time_label: str = Field(description="When, e.g. '7:00 AM' or 'now'.")
    note: str = Field("", description="Optional one-line note.")


class MarkMedication(Action):
    """Mark one of today's planned medications as taken, missed, or skipped, as the
    patient confirms. Use the medication name exactly as it appears in the care plan.
    Call once per medication."""

    name: str = Field(description="Medication name from the care plan, e.g. 'Metformin 500mg'.")
    status: Literal["taken", "missed", "skipped"] = Field(description="What the patient reported.")
    time_label: str = Field(
        "", description="When they took it, if they said, e.g. 'after breakfast'."
    )


class ShowGlucose(Action):
    """Bring the day's glucose chart on screen, optionally zoomed to one event. Call this
    BEFORE asking about a reading ('what did you have around two?') so the patient is
    looking at the moment you mean. Stay observational — never attach medical meaning."""

    focus_time_label: str = Field(
        "", description="Event time to zoom/highlight, e.g. '2:15 PM'. Omit for the whole day."
    )
    note: str = Field(
        "",
        description="Optional short on-screen label for the highlight, e.g. 'Rise after lunch'.",
    )


class PlayVideo(Action):
    """Play a video from the in-app library (ids in the PATIENT CONTEXT) inside the app,
    with sound. Introduce it in a few words first. The patient follows along."""

    video_id: str = Field(description="Library video id from the PATIENT CONTEXT.")
    start_sec: int = Field(0, description="Second to start from. Omit to start at the beginning.")


class PauseVideo(Action):
    """Pause the playing video (e.g. when the patient wants to talk)."""


class ResumeVideo(Action):
    """Resume the paused video."""


class SetCommitment(Action):
    """Save the ONE small commitment the patient makes for tomorrow — it appears on their
    summary and you will see it in the next call's context. Their words, in English."""

    text: str = Field(
        description="The commitment, short and specific, e.g. 'Fifteen-minute walk after dinner'."
    )
    when: str = Field("", description="When they'll do it, e.g. 'tomorrow evening'.")


class FlagForCareTeam(Action):
    """Flag a medical question or concern to the patient's care team — anything you must
    not answer yourself (doses, symptoms, interpreting readings, diet changes beyond the
    plan). A 'flagged for your care team' chip appears on screen. Tell the patient it's
    been flagged."""

    topic: str = Field(description="Short topic in English, e.g. 'Metformin dose question'.")
    detail: str = Field(
        description="One or two lines of what the patient asked or reported, in English."
    )


class ShowSensorRenewal(Action):
    """Put the glucose-sensor replacement card on screen (only when the context says the
    sensor has expired). The patient can confirm by voice or by tapping the card."""


class ConfirmSensorOrder(Action):
    """Place the sensor replacement order after the patient clearly agrees BY VOICE. If
    they tapped the card themselves, the screen state shows it — do not call this too."""


class ShowSummary(Action):
    """Show the end-of-call summary card as you wrap up: the day in a few lines, plus the
    commitment. Call this right before your goodbye. Lines in English."""

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
    """Scroll to and briefly highlight one section of the patient's screen so their eye
    follows you."""

    section: Section = Field(description="Which section to highlight.")


class SwitchLanguage(BaseModel):
    """Switch the conversation language when the patient asks. Acknowledge their request
    in one short sentence in the target language first."""

    language: LanguageName = Field(description="Target language.")


# The declared surface. The key is the name the model calls; the value validates
# that call — and, for all but ``log_meal`` and ``switch_language``, *is* the
# action the browser renders.
_TOOLS: dict[str, type[BaseModel]] = {
    "log_meal": LogMealArgs,
    "log_activity": LogActivity,
    "mark_medication": MarkMedication,
    "show_glucose": ShowGlucose,
    "play_video": PlayVideo,
    "pause_video": PauseVideo,
    "resume_video": ResumeVideo,
    "set_commitment": SetCommitment,
    "flag_for_care_team": FlagForCareTeam,
    "show_sensor_renewal": ShowSensorRenewal,
    "confirm_sensor_order": ConfirmSensorOrder,
    "show_summary": ShowSummary,
    "highlight": Highlight,
    "switch_language": SwitchLanguage,
}


def _declare(name: str, model: type[BaseModel]) -> types.FunctionDeclaration:
    """One function declaration from one model: the docstring is the description the
    model reads, the fields are the parameters. The schema's own title and
    description come off so the prompt carries each of them once."""
    schema = model.model_json_schema()
    description = schema.pop("description", None)
    schema.pop("title", None)
    return types.FunctionDeclaration(
        name=name, description=description, parameters_json_schema=schema
    )


def _tools() -> types.ToolListUnion:
    return [types.Tool(function_declarations=[_declare(n, m) for n, m in _TOOLS.items()])]


class SugarBrain(GeminiBrain):
    """One per session. The Sugar Coach daily check-in: LLM + habit-logging tools
    + this session's patient/screen state. :meth:`dispatch_tool` runs each call
    and drives the ``/sugar`` UI with ``session.dispatch(...)``.

    The per-scenario patient picture arrives as ``session.init`` and is folded
    into the system instruction in :meth:`on_session_start`. The browser echoes a
    ``state_sync`` snapshot to :meth:`on_rtvi`; :meth:`grounding` carries it into
    every turn so the coach reasons from the live screen."""

    # No declared ``voice``/``language``. This coach's language depends on the
    # caller — the patient's own LanguageToggle choice rides
    # ``session.init["language"]`` — so on_session_start resolves it and moves
    # both legs with one ``configure_language`` before the greeting. A declared
    # default here would only mean configuring the language twice.

    def __init__(self, *, llm: GeminiProvider, model: str = DEFAULT_MODEL) -> None:
        # The base system instruction only; the PATIENT CONTEXT is folded in per
        # session in on_session_start once session.init has arrived.
        super().__init__(
            client=llm.client,
            system_instruction=_SYSTEM_INSTRUCTION,
            tools=_tools(),
            model=model,
        )
        # Per-session state (populated on_session_start from session.init).
        # Ephemeral in memory — no resume across disconnects, by design.
        self.patient_name = "there"
        self.language_name = "English"
        self.talk_mode = "quiet"
        self.nudge = ""
        # Latest screen snapshot the browser has told us about (source of truth
        # lives in the browser; this is the brain's view of it) and the trailing
        # user message that carries it into each turn's working context.
        self.current_state: dict[str, Any] | None = None
        self._state_message: str | None = None

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        """Read the seeded scenario (``session.init``), move the language on both
        legs, and fold the PATIENT CONTEXT into the system instruction so every
        turn is grounded in it."""
        payload = dict(session.init or {})
        raw_scenario = payload.get("scenario")
        scenario: dict[str, Any] = raw_scenario if isinstance(raw_scenario, dict) else {}
        raw_patient = scenario.get("patient")
        patient = raw_patient if isinstance(raw_patient, dict) else {}
        self.patient_name = str(patient.get("name") or "").strip() or "there"
        language = str(payload.get("language", "")).strip()
        self.language_name = language if language in _LANG else "English"
        # Apply the patient's chosen language to the wire BEFORE greeting. Until
        # this call existed the choice only reached the prompt, so the coach wrote
        # Devanagari while an en-IN reference voice read it aloud — the whole
        # conversation right on paper and foreign-accented in the ear. It only
        # sounded correct because the browser happened to send a matching
        # per-session override; the brain must not depend on that.
        _, tts_voice, tts_lang = _LANG[self.language_name]
        await session.configure_language(tts_lang, voice=tts_voice)
        # How much the coach leads vs. listens. "quiet" = the patient narrates
        # and we log silently; "guided" = we walk them through beat by beat.
        # Either way the two-or-three-sentence ceiling holds. Default quiet.
        mode = str(scenario.get("talk_mode", "")).strip().lower()
        self.talk_mode = mode if mode in ("quiet", "guided") else "quiet"
        # The push-notification the patient just tapped Join on. The opener
        # continues naturally from it (it also cued them on what to say).
        self.nudge = str(scenario.get("joined_from_nudge", "")).strip()

        # Fold the whole per-scenario picture into the system instruction so every
        # turn is grounded in it — the base rebuilds working_context from the
        # transcript each turn, so the per-scenario picture belongs in the system
        # prompt instead.
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
        that already told them what to do, so the coach says hello by name and
        hands them the floor."""
        return _GREETING[self.language_name].format(name=self.patient_name)

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Browser→brain message. ``state_sync`` carries a compact snapshot of the
        patient's screen — what's logged, med ticks, video position, and taps the
        patient made by hand. Ingested *silently* (no floor taken, no turn); the
        next turn's :meth:`grounding` surfaces it so the coach reasons from the
        live screen."""
        if msg.type is not RTVIType.CLIENT_MESSAGE or not isinstance(msg.data, dict):
            return
        if msg.data.get("t") == "state_sync":
            self._ingest_state(msg.data.get("d") or {})

    # ─── Browser → brain: screen state sync (silent awareness) ──────────

    def _ingest_state(self, data: dict[str, Any]) -> None:
        """Fold the latest screen snapshot into the trailing context message the
        next turn will carry."""
        snapshot = data.get("screen")
        self.current_state = snapshot if isinstance(snapshot, dict) else None
        if self.current_state is None:
            self._state_message = "CURRENT SCREEN STATE: the patient's app is initializing."
        else:
            try:
                blob = json.dumps(self.current_state, ensure_ascii=False)
            except (TypeError, ValueError):
                blob = str(self.current_state)
            self._state_message = (
                "CURRENT SCREEN STATE (authoritative — reflects everything logged so far and "
                "any taps the patient made by hand; always reason from this): " + blob
            )
        logger.info("sugar: state_sync ingested (active={})", bool(self.current_state))

    def grounding(self) -> str | None:
        """The latest screen snapshot, folded into every turn so the assistant
        always reasons from the live screen."""
        return self._state_message

    # ─── Tools ──────────────────────────────────────────────────────────

    async def dispatch_tool(self, session: Session, name: str, args: dict[str, Any]) -> str:
        """Run one tool call: validate the arguments against the model that declared
        the tool, drive the browser with ``session.dispatch(...)`` (the ``ui-command``
        the /sugar UI renders), and return the short guidance string fed back to the
        model. ``switch_language`` reconfigures STT/TTS instead of the screen."""
        model = _TOOLS.get(name)
        if model is None:
            return "unknown tool"
        try:
            call = model.model_validate(args)
        except ValidationError as exc:
            # Hand the model its own mistake — it has hops left to correct it.
            return str({"error": "invalid arguments", "detail": exc.errors(include_url=False)})
        logger.info("sugar: {} {}", name, call.model_dump(mode="json"))

        # Twelve of the fourteen declare the very payload the browser renders, so
        # the validated call *is* the action.
        if isinstance(call, Action):
            session.dispatch(call)

        match call:
            case LogMealArgs():
                # The total is summed here, not asked of the model: the number on
                # screen is then always the sum of the items shown under it.
                total = sum(item.calories for item in call.items)
                session.dispatch(LogMeal(**call.model_dump(), total_calories=total))
                return str(
                    {"status": "logged", "meal_type": call.meal_type, "total_calories": total}
                )
            case SwitchLanguage():
                return await self._switch_language(session, call)
            case LogActivity():
                return str(
                    {"status": "logged", "kind": call.kind, "duration_min": call.duration_min}
                )
            case MarkMedication():
                return str({"status": "marked", "name": call.name, "state": call.status})
            case ShowGlucose():
                return str({"status": "shown", "focus": call.focus_time_label or "full_day"})
            case PlayVideo():
                return str({"status": "playing", "video_id": call.video_id})
            case PauseVideo():
                return str({"status": "paused"})
            case ResumeVideo():
                return str({"status": "resumed"})
            case SetCommitment():
                return str({"status": "saved", "text": call.text})
            case FlagForCareTeam():
                return str(
                    {
                        "status": "flagged",
                        "topic": call.topic,
                        "note": "The care team will see this. Tell the patient it's been flagged, in one sentence.",
                    }
                )
            case ShowSensorRenewal():
                return str(
                    {
                        "status": "shown",
                        "note": "The patient can confirm by voice (confirm_sensor_order) or by tapping the card.",
                    }
                )
            case ConfirmSensorOrder():
                return str({"status": "ordered"})
            case ShowSummary():
                return str({"status": "shown"})
            case Highlight():
                return str({"status": "highlighted", "section": call.section})
            case _:
                return str({"status": "done"})

    async def _switch_language(self, session: Session, call: SwitchLanguage) -> str:
        stt_hint, tts_voice, tts_lang = _LANG[call.language]
        self.language_name = call.language
        logger.info("sugar: switch_language → {} (hint={})", call.language, stt_hint)
        # One call moves both halves — recognizer and voice. This is the only
        # supported way to change language mid-call; the configure_tts +
        # configure_stt pair can drift, and either half missing is silent. Awaited
        # because the model gets the answer Voqalize gave, not the one we hoped for.
        await session.configure_language(tts_lang, voice=tts_voice)
        return str({"switched_to": call.language})
