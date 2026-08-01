"""SugarBrain — the Sugar Coach daily diabetes check-in.

A :class:`~voqalize_demos.brains._gemini.GeminiBrain` that runs the ``/sugar``
demo: a diabetes-management program places a scheduled evening in-app call and the
assistant runs the daily habit check-in — logging meals by voice, confirming
exercise and medications, reviewing the glucose curve, nudging toward the care
plan, and ending with a summary card. Voqalize dials this brain's WebSocket per
session and the inherited tool-loop ``on_interaction`` drives each turn.

Two things worth calling out about how per-session state flows in:

  * **init_payload** — the whole per-scenario patient picture (patient, care
    plan, recent logs, CGM status, prior-call summaries, TODAY'S CALL OBJECTIVE)
    arrives per session. The brain is built before the session, so the payload
    arrives in :meth:`on_session_start` as ``start.init``. We fold the PATIENT
    CONTEXT into the system instruction per session (interview_bot pattern) so
    every turn — greeting included — is grounded in it, then speak an
    LLM-generated greeting.
  * **state_sync** — the browser echoes a compact ``state_sync`` snapshot of the
    patient's screen (what's logged, med ticks, taps the patient made by hand).
    :meth:`on_client_message` folds it into the context *silently* (no inference,
    no floor taken): it stores the latest snapshot and :meth:`working_context`
    appends it as a trailing user turn so the assistant always reasons from the
    live screen — silently, no turn is triggered by a state_sync.

Like the travel/support brains, **the LLM generates the substantive data** (meal
items, calorie estimates, summary lines) as nested function-call arguments; the
handlers are thin pass-throughs that normalize and drive the browser via
``interaction.action(name, {...})`` — the RTVI ``ui_command`` the ``/sugar`` UI
renders. ``switch_language`` swaps the voice mid-call via the public
``session.configure_stt`` / ``session.configure_tts`` API.
"""

from __future__ import annotations

import json
from typing import Any

from google.genai import types
from loguru import logger
from voqalize_demos import DEFAULT_MODEL, GeminiBrain, GeminiProvider, hello_for

COACH_NAME = "Sugar Coach"

# (stt language_hint, tts_voice, tts_language) per conversation language.
# Same voice both ways; only the language hint moves (vql-speech applies it live).
_LANG: dict[str, tuple[str, str, str]] = {
    "English": ("en", "omnivoice/gauri", "en"),
    "Hindi": ("hi", "omnivoice/gauri", "hi"),
}

# Screen sections the assistant can highlight / that exist on the patient's
# "Today" screen (mirror frontend src/sugar/pages.tsx).
_SECTIONS = ["glucose", "meals", "activity", "meds", "plan", "summary"]

_MEAL_TYPES = ["breakfast", "lunch", "snack", "dinner", "other"]


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


# ── Nested JSON-schema fragment (the LLM-generated meal-item data shape) ────────

_MEAL_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "Food item in clean English, e.g. 'Roti' or 'Dal (katori)'.",
        },
        "quantity": {
            "type": "string",
            "description": "Quantity in the patient's units, e.g. '2', '1 katori', '1 bowl'.",
        },
        "calories": {
            "type": "integer",
            "description": "Your calorie estimate for that quantity, rounded to a friendly number.",
        },
    },
    "required": ["name", "quantity", "calories"],
}


# ─── Tool schemas (JSON-schema dicts → google-genai Schema) ─────────────────────

# (tool_name, description, properties, required)
_TOOLSPECS: list[tuple[str, str, dict[str, Any], list[str]]] = [
    (
        "log_meal",
        "Log a meal the patient just described — it appears in their food log with your "
        "calorie estimates. Call it the moment they finish describing; call again with "
        "corrected items if they amend. Item names in English.",
        {
            "meal_type": {
                "type": "string",
                "enum": _MEAL_TYPES,
                "description": "Which meal of the day this is.",
            },
            "time_label": {
                "type": "string",
                "description": "When they ate, as shown on screen, e.g. '1:30 PM' or 'around 2 PM'.",
            },
            "items": {
                "type": "array",
                "items": _MEAL_ITEM_SCHEMA,
                "description": "The foods with quantities and your calorie estimates.",
            },
            "note": {
                "type": "string",
                "description": "Optional one-line note, e.g. 'ate out — office canteen'.",
            },
        },
        ["meal_type", "time_label", "items"],
    ),
    (
        "log_activity",
        "Log physical activity the patient did (or commits to doing right now) — it "
        "appears in their activity log.",
        {
            "kind": {
                "type": "string",
                "description": "Activity in English, e.g. 'Walk', 'Yoga', 'Desk stretches'.",
            },
            "duration_min": {
                "type": "integer",
                "description": "Duration in minutes.",
            },
            "time_label": {
                "type": "string",
                "description": "When, e.g. '7:00 AM' or 'now'.",
            },
            "note": {"type": "string", "description": "Optional one-line note."},
        },
        ["kind", "duration_min", "time_label"],
    ),
    (
        "mark_medication",
        "Mark one of today's planned medications as taken, missed, or skipped, as the "
        "patient confirms. Use the medication name exactly as it appears in the care plan. "
        "Call once per medication.",
        {
            "name": {
                "type": "string",
                "description": "Medication name from the care plan, e.g. 'Metformin 500mg'.",
            },
            "status": {
                "type": "string",
                "enum": ["taken", "missed", "skipped"],
                "description": "What the patient reported.",
            },
            "time_label": {
                "type": "string",
                "description": "When they took it, if they said, e.g. 'after breakfast'.",
            },
        },
        ["name", "status"],
    ),
    (
        "show_glucose",
        "Bring the day's glucose chart on screen, optionally zoomed to one event. Call this "
        "BEFORE asking about a reading ('what did you have around two?') so the patient is "
        "looking at the moment you mean. Stay observational — never attach medical meaning.",
        {
            "focus_time_label": {
                "type": "string",
                "description": "Event time to zoom/highlight, e.g. '2:15 PM'. Omit for the whole day.",
            },
            "note": {
                "type": "string",
                "description": "Optional short on-screen label for the highlight, e.g. 'Rise after lunch'.",
            },
        },
        [],
    ),
    (
        "play_video",
        "Play a video from the in-app library (ids in the PATIENT CONTEXT) inside the app, "
        "with sound. Introduce it in a few words first. The patient follows along.",
        {
            "video_id": {
                "type": "string",
                "description": "Library video id from the PATIENT CONTEXT.",
            },
            "start_sec": {
                "type": "integer",
                "description": "Second to start from. Omit to start at the beginning.",
            },
        },
        ["video_id"],
    ),
    (
        "pause_video",
        "Pause the playing video (e.g. when the patient wants to talk).",
        {},
        [],
    ),
    (
        "resume_video",
        "Resume the paused video.",
        {},
        [],
    ),
    (
        "set_commitment",
        "Save the ONE small commitment the patient makes for tomorrow — it appears on their "
        "summary and you will see it in the next call's context. Their words, in English.",
        {
            "text": {
                "type": "string",
                "description": "The commitment, short and specific, e.g. 'Fifteen-minute walk after dinner'.",
            },
            "when": {
                "type": "string",
                "description": "When they'll do it, e.g. 'tomorrow evening'.",
            },
        },
        ["text"],
    ),
    (
        "flag_for_care_team",
        "Flag a medical question or concern to the patient's care team — anything you must "
        "not answer yourself (doses, symptoms, interpreting readings, diet changes beyond "
        "the plan). A 'flagged for your care team' chip appears on screen. Tell the patient "
        "it's been flagged.",
        {
            "topic": {
                "type": "string",
                "description": "Short topic in English, e.g. 'Metformin dose question'.",
            },
            "detail": {
                "type": "string",
                "description": "One or two lines of what the patient asked or reported, in English.",
            },
        },
        ["topic", "detail"],
    ),
    (
        "show_sensor_renewal",
        "Put the glucose-sensor replacement card on screen (only when the context says the "
        "sensor has expired). The patient can confirm by voice or by tapping the card.",
        {},
        [],
    ),
    (
        "confirm_sensor_order",
        "Place the sensor replacement order after the patient clearly agrees BY VOICE. If "
        "they tapped the card themselves, the screen state shows it — do not call this too.",
        {},
        [],
    ),
    (
        "show_summary",
        "Show the end-of-call summary card as you wrap up: the day in a few lines, plus the "
        "commitment. Call this right before your goodbye. Lines in English.",
        {
            "lines": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Three to five short lines capturing the day, e.g. 'Lunch and dinner logged "
                    "— about 1,400 kcal', 'Evening walk: 20 minutes', 'All medications taken'."
                ),
            },
            "flagged": {
                "type": "string",
                "description": "If anything was flagged to the care team, one short line naming it.",
            },
        },
        ["lines"],
    ),
    (
        "highlight",
        "Scroll to and briefly highlight one section of the patient's screen so their eye follows you.",
        {
            "section": {
                "type": "string",
                "enum": _SECTIONS,
                "description": "Which section to highlight.",
            },
        },
        ["section"],
    ),
    (
        "switch_language",
        "Switch the conversation language when the patient asks. Acknowledge their request "
        "in one short sentence in the target language first.",
        {
            "language": {
                "type": "string",
                "enum": list(_LANG.keys()),
                "description": "Target language.",
            },
        },
        ["language"],
    ),
]

_JSON_TO_GENAI = {
    "string": types.Type.STRING,
    "integer": types.Type.INTEGER,
    "number": types.Type.NUMBER,
    "boolean": types.Type.BOOLEAN,
    "object": types.Type.OBJECT,
    "array": types.Type.ARRAY,
}


def _to_schema(d: dict[str, Any]) -> types.Schema:
    """Convert a JSON-schema dict to a google-genai Schema (recursive)."""
    kw: dict[str, Any] = {"type": _JSON_TO_GENAI[d["type"]]}
    if d.get("description"):
        kw["description"] = d["description"]
    if d.get("enum"):
        kw["enum"] = d["enum"]
    if d["type"] == "object":
        props = d.get("properties") or {}
        kw["properties"] = {k: _to_schema(v) for k, v in props.items()}
        if d.get("required"):
            kw["required"] = d["required"]
    if d["type"] == "array":
        kw["items"] = _to_schema(d["items"])
    return types.Schema(**kw)


def _tools() -> types.ToolListUnion:
    decls = [
        types.FunctionDeclaration(
            name=name,
            description=desc,
            parameters=_to_schema({"type": "object", "properties": props, "required": req}),
        )
        for name, desc, props, req in _TOOLSPECS
    ]
    tools: types.ToolListUnion = [types.Tool(function_declarations=decls)]
    return tools


class SugarBrain(GeminiBrain):
    """One per session. The Sugar Coach daily check-in: LLM + habit-logging tools
    + this session's patient/screen state. ``on_interaction`` is the inherited
    tool-loop ``respond``; :meth:`dispatch_tool` runs each call and drives the
    ``/sugar`` UI via ``interaction.action(...)``.

    The per-scenario patient picture arrives via ``init_payload`` and is folded
    into the system instruction in :meth:`on_session_start`. The browser echoes a
    ``state_sync`` snapshot on :meth:`on_client_message`; :meth:`working_context`
    appends it so every turn reasons from the live screen."""

    def __init__(self, *, llm: GeminiProvider, model: str = DEFAULT_MODEL) -> None:
        # The base system instruction only; the PATIENT CONTEXT is folded in per
        # session in on_session_start once init_payload has arrived.
        super().__init__(
            llm=llm, system_instruction=_SYSTEM_INSTRUCTION, tools=_tools(), model=model
        )
        # Per-session state (populated on_session_start from init_payload).
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

    async def on_session_start(self, session, start) -> None:
        """Read the seeded scenario (``start.init``), fold the PATIENT CONTEXT
        into the system instruction so every turn is grounded in it, then speak
        the greeting."""
        payload = dict(start.init or {})
        raw_scenario = payload.get("scenario")
        scenario: dict[str, Any] = raw_scenario if isinstance(raw_scenario, dict) else {}
        raw_patient = scenario.get("patient")
        patient = raw_patient if isinstance(raw_patient, dict) else {}
        self.patient_name = str(patient.get("name") or "").strip() or "there"
        language = str(payload.get("language", "")).strip()
        self.language_name = language if language in _LANG else "English"
        # How much the coach leads vs. listens. "quiet" = the patient narrates
        # and we log silently; "guided" = we walk them through beat by beat.
        # Either way the two-or-three-sentence ceiling holds. Default quiet.
        mode = str(scenario.get("talk_mode", "")).strip().lower()
        self.talk_mode = mode if mode in ("quiet", "guided") else "quiet"
        # The push-notification the patient just tapped Join on. The opener
        # continues naturally from it (it also cued them on what to say).
        self.nudge = str(scenario.get("joined_from_nudge", "")).strip()

        # Fold the whole per-scenario picture into the system instruction so every
        # turn (greeting included) is grounded in it — the base rebuilds
        # working_context from the transcript each turn, so the per-scenario
        # picture belongs in the system prompt instead.
        context_block = (
            "PATIENT CONTEXT (authoritative — everything you know about this patient and "
            f"today's call; the conversation language is {self.language_name}): "
            + json.dumps(scenario, ensure_ascii=False)
        )
        instruction = f"{_SYSTEM_INSTRUCTION}\n\n{context_block}"
        self._config = self._config.model_copy(update={"system_instruction": instruction})
        logger.info(
            "sugar: session start — patient={!r}, language={}, talk_mode={}",
            self.patient_name,
            self.language_name,
            self.talk_mode,
        )

        # Hybrid greeting: a language-appropriate hello is spoken instantly (no LLM
        # call), then the tuned, patient-grounded remainder streams in behind it so
        # the model's first-token latency is off the perceived start path.
        await self.say_then_generate(
            session, hello_for(self.language_name), self._greeting_instruction()
        )

    async def on_client_message(self, session, message) -> None:
        """Browser→Brain client message. ``state_sync`` carries a compact snapshot
        of the patient's screen — what's logged, med ticks, video position, and taps
        the patient made by hand. Ingested *silently* (no floor taken, no inference);
        the next turn's :meth:`working_context` surfaces it so the assistant reasons
        from the live screen."""
        if message.type == "state_sync":
            self._ingest_state(message.data or {})

    def _greeting_instruction(self) -> str:
        """A one-shot prompt for the LLM-generated opening line (grounded in the
        patient + talk_mode)."""
        common = (
            f"The patient ({self.patient_name}) just tapped Join on your evening check-in "
            f"nudge — the nudge already told them to walk you through their day, so do NOT "
            f"re-explain the ask. Greet them by first name as their {COACH_NAME}, in "
            f"{self.language_name}. Do NOT call any tool on this first turn — just speak; "
            f"the screen work starts once they answer."
        )
        if self.talk_mode == "quiet":
            return common + (
                " QUIET check-in: a warm hello plus a tiny 'go ahead' and nothing else — "
                "ONE short sentence, two at the very most, aim for fourteen words or fewer "
                "total. No streak talk, no praise, no filler. Then stop and let them talk. "
                'Feel: "Evening, Rajesh — go on, I\'m listening." or "Evening, Rajesh. '
                "How'd today go?\""
            )
        return common + (
            " GUIDED check-in: one warm, grounded line, then your first specific question — "
            "no more than two short sentences before the question, and skip the meet-and-greet "
            "padding even on a first call."
        )

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

    def grounding(self, interaction) -> str | None:
        """The latest screen snapshot, folded into every turn so the assistant
        always reasons from the live screen."""
        return self._state_message

    # ─── Tools ──────────────────────────────────────────────────────────

    def dispatch_tool(self, interaction, name: str, args: dict[str, Any]) -> str:
        """Run one tool call: normalize args, drive the browser via
        ``interaction.action(...)`` (the RTVI ui_command the /sugar UI renders),
        and return the short guidance string fed back to the model.
        ``switch_language`` reconfigures STT/TTS instead of the screen."""
        if name == "log_meal":
            return self._log_meal(interaction, args)
        if name == "log_activity":
            return self._log_activity(interaction, args)
        if name == "mark_medication":
            return self._mark_medication(interaction, args)
        if name == "show_glucose":
            return self._show_glucose(interaction, args)
        if name == "play_video":
            return self._play_video(interaction, args)
        if name == "pause_video":
            logger.info("sugar: pause_video")
            interaction.action("pause_video")
            return str({"status": "paused"})
        if name == "resume_video":
            logger.info("sugar: resume_video")
            interaction.action("resume_video")
            return str({"status": "resumed"})
        if name == "set_commitment":
            return self._set_commitment(interaction, args)
        if name == "flag_for_care_team":
            return self._flag_for_care_team(interaction, args)
        if name == "show_sensor_renewal":
            logger.info("sugar: show_sensor_renewal")
            interaction.action("show_sensor_renewal")
            return str(
                {
                    "status": "shown",
                    "note": "The patient can confirm by voice (confirm_sensor_order) or by tapping the card.",
                }
            )
        if name == "confirm_sensor_order":
            logger.info("sugar: confirm_sensor_order")
            interaction.action("confirm_sensor_order")
            return str({"status": "ordered"})
        if name == "show_summary":
            return self._show_summary(interaction, args)
        if name == "highlight":
            section = str(args.get("section", ""))
            logger.info("sugar: highlight {}", section)
            interaction.action("highlight", {"section": section})
            return str({"status": "highlighted", "section": section})
        if name == "switch_language":
            return self._switch_language(interaction, args)
        return "unknown tool"

    def _log_meal(self, interaction, args: dict[str, Any]) -> str:
        meal_type = str(args.get("meal_type", "other")).strip().lower()
        time_label = str(args.get("time_label", "")).strip()
        note = str(args.get("note", "")).strip()
        items: list[dict[str, Any]] = []
        for raw in list(args.get("items") or []):
            item = dict(raw) if isinstance(raw, dict) else {}
            if str(item.get("name") or "").strip():
                items.append(item)
        if not items:
            return str({"error": "need at least one food item"})
        total = sum(int(i.get("calories") or 0) for i in items)
        logger.info(
            "sugar: log_meal {} @{} ({} items, {} kcal)", meal_type, time_label, len(items), total
        )
        interaction.action(
            "log_meal",
            {
                "meal_type": meal_type,
                "time_label": time_label,
                "items": items,
                "total_calories": total,
                "note": note,
            },
        )
        return str({"status": "logged", "meal_type": meal_type, "total_calories": total})

    def _log_activity(self, interaction, args: dict[str, Any]) -> str:
        kind = str(args.get("kind", "")).strip()
        duration = int(args.get("duration_min") or 0)
        time_label = str(args.get("time_label", "")).strip()
        note = str(args.get("note", "")).strip()
        if not kind:
            return str({"error": "need an activity kind"})
        logger.info("sugar: log_activity {} {}min @{}", kind, duration, time_label)
        interaction.action(
            "log_activity",
            {"kind": kind, "duration_min": duration, "time_label": time_label, "note": note},
        )
        return str({"status": "logged", "kind": kind, "duration_min": duration})

    def _mark_medication(self, interaction, args: dict[str, Any]) -> str:
        name = str(args.get("name", "")).strip()
        status = str(args.get("status", "")).strip()
        time_label = str(args.get("time_label", "")).strip()
        if not name or status not in ("taken", "missed", "skipped"):
            return str({"error": "need a medication name and a valid status"})
        logger.info("sugar: mark_medication {!r} -> {}", name, status)
        interaction.action(
            "mark_medication", {"name": name, "status": status, "time_label": time_label}
        )
        return str({"status": "marked", "name": name, "state": status})

    def _show_glucose(self, interaction, args: dict[str, Any]) -> str:
        focus = str(args.get("focus_time_label", "")).strip()
        note = str(args.get("note", "")).strip()
        logger.info("sugar: show_glucose focus={!r}", focus or None)
        interaction.action("show_glucose", {"focus_time_label": focus, "note": note})
        return str({"status": "shown", "focus": focus or "full_day"})

    def _play_video(self, interaction, args: dict[str, Any]) -> str:
        video_id = str(args.get("video_id", "")).strip()
        start_sec = int(args.get("start_sec") or 0)
        if not video_id:
            return str({"error": "need a video_id from the library"})
        logger.info("sugar: play_video {} @{}s", video_id, start_sec)
        interaction.action("play_video", {"video_id": video_id, "start_sec": start_sec})
        return str({"status": "playing", "video_id": video_id})

    def _set_commitment(self, interaction, args: dict[str, Any]) -> str:
        text = str(args.get("text", "")).strip()
        when = str(args.get("when", "")).strip()
        if not text:
            return str({"error": "need the commitment text"})
        logger.info("sugar: set_commitment {!r} ({})", text, when or "unspecified")
        interaction.action("set_commitment", {"text": text, "when": when})
        return str({"status": "saved", "text": text})

    def _flag_for_care_team(self, interaction, args: dict[str, Any]) -> str:
        topic = str(args.get("topic", "")).strip()
        detail = str(args.get("detail", "")).strip()
        if not topic:
            return str({"error": "need a topic"})
        logger.info("sugar: flag_for_care_team {!r}", topic)
        interaction.action("flag_for_care_team", {"topic": topic, "detail": detail})
        return str(
            {
                "status": "flagged",
                "topic": topic,
                "note": "The care team will see this. Tell the patient it's been flagged, in one sentence.",
            }
        )

    def _show_summary(self, interaction, args: dict[str, Any]) -> str:
        lines = [str(line).strip() for line in list(args.get("lines") or []) if str(line).strip()]
        flagged = str(args.get("flagged", "")).strip()
        if not lines:
            return str({"error": "need at least one summary line"})
        logger.info("sugar: show_summary ({} lines)", len(lines))
        interaction.action("show_summary", {"lines": lines, "flagged": flagged})
        return str({"status": "shown"})

    def _switch_language(self, interaction, args: dict[str, Any]) -> str:
        language = str(args.get("language", ""))
        cfg = _LANG.get(language)
        if not cfg:
            return str({"switched_to": self.language_name, "error": "unknown language"})
        stt_hint, tts_voice, tts_lang = cfg
        self.language_name = language
        logger.info("sugar: switch_language → {} (hint={} voice={})", language, stt_hint, tts_voice)
        # Swap the whole voice mid-call via the public reconfigure API: TTS
        # voice/language + the STT recognition language_hint.
        interaction.session.configure_tts(voice=tts_voice, language=tts_lang)
        interaction.session.configure_stt(language_hint=stt_hint)
        return str({"switched_to": language})
