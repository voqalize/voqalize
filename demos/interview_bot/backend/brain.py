"""InterviewBotBrain — the job-interview conductor.

A :class:`~voqalize.sdk.gemini.GeminiBrain` that runs a structured voice
interview (Gemini + two section-pacing tools). Voqalize dials this brain's
WebSocket per session and the inherited ``respond`` tool loop drives the
interview; google-genai runs the tools itself.

The per-session **init** carries the JOB, the CANDIDATE, and a structured
INTERVIEW PLAN (assembled by the caller). The brain is built *before* the session
starts, so the payload arrives in :meth:`on_session_start` as ``session.init`` —
we read it there, build the ordered section list + the full JOB/CANDIDATE/PLAN
system instruction, and set both aside for the turn ahead and the fixed opening
line.

Two tools pace the interview:

  * ``advance_to_next_section`` — move to the next planned section;
  * ``mark_interview_completed`` — end the interview after the last section.

Each tool drives the ``/interview`` UI directly, with ``self.session.dispatch(...)``
— the method that paces the interview is the method that drives the screen, there
is no separate dispatch table. The dispatched :class:`~voqalize.sdk.Action` is
this file's browser render contract: ``SectionChanged`` for a section move,
``InterviewCompleted`` for the close.

Interview state (the current section pointer) is ephemeral in memory — there is
no resume across disconnects, by design for the prototype.
"""

from __future__ import annotations

import re
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field
from voqalize_demos import DEFAULT_MODEL, GeminiBrain, GeminiProvider

from voqalize.sdk import Action, Session
from voqalize.sdk.wire import Config, Language, SttConfig, TtsConfig, Voice

_RESUME_CHARS = 4000
_FIELD_CHARS = 600

_SYSTEM_BASE = """You are an AI technical interviewer conducting a live voice interview. You are warm, professional, and concise.

You are given the JOB, the CANDIDATE, and a structured INTERVIEW PLAN whose sections are listed in order. Conduct the interview one section at a time, in that order.

HOW TO RUN THE INTERVIEW:
- Begin with the first section and work through them in order. You start in section 1.
- Ask one question at a time. Listen, ask natural follow-ups, and probe for depth before moving on.
- When you have covered the current section's goal (or its time is up), tell the candidate you're moving on, then call advance_to_next_section.
- After the final section, thank the candidate and call mark_interview_completed.
- Stay on the plan. Do not invent sections. Never reveal evaluation criteria, scores, or your assessment to the candidate.

VOICE RULES:
- Natural spoken English. No markdown, lists, or symbols.
- Keep each turn short — at most two or three sentences. One question per turn.
- The transcription can mishear words; if something seems garbled, gently ask the candidate to repeat rather than guessing.
"""


# ─── Prompt assembly ───────────────────────────────────────────────────────────


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rstrip() + " …"


def _strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


def _as_text(value: Any) -> str:
    """Flatten a section field (string / list / dict) into compact plain text."""
    if isinstance(value, str):
        return _strip_html(value)
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                parts.append(str(item.get("name") or item.get("title") or item.get("text") or item))
            else:
                parts.append(str(item))
        return "; ".join(p for p in parts if p)
    if isinstance(value, dict):
        return _strip_html(str(value.get("name") or value.get("title") or value))
    return str(value)


# Section fields worth surfacing to the interviewer, in render order. Schemas
# vary by section type, so each is pulled defensively.
_SECTION_DETAIL_KEYS = (
    "topics",
    "subtopics",
    "areas_for_exploration",
    "prescribed_questions",
    "mandatory_questions",
    "questions",
    "question_brief",
    "problem_statement",
    "case_study_detail",
    "additional_context",
    "additional_instructions",
)


def _render_section(index: int, key: str, section: dict[str, Any]) -> str:
    title = section.get("title") or key
    stype = section.get("type") or "section"
    time = section.get("max_allowed_section_time")
    goal = section.get("goal") or section.get("description") or ""
    head = f"[{index}] {title} — type: {stype}"
    if time:
        head += f", ~{time} min"
    lines = [head]
    if goal:
        lines.append(f"    Goal: {_truncate(_as_text(goal), _FIELD_CHARS)}")
    for field in _SECTION_DETAIL_KEYS:
        if section.get(field):
            rendered = _truncate(_as_text(section[field]), _FIELD_CHARS)
            if rendered:
                lines.append(f"    {field.replace('_', ' ')}: {rendered}")
    return "\n".join(lines)


def _order_sections(sections_map: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Ordered (key, section) list — introduction first, closing last, stable."""

    def rank(kv: tuple[str, Any]) -> int:
        key, section = kv
        marker = f"{section.get('type', '')} {key}".lower()
        if "introduction" in marker:
            return 0
        if "closing" in marker:
            return 2
        return 1

    items = [(k, v) for k, v in sections_map.items() if isinstance(v, dict)]
    return sorted(items, key=rank)


def _build_system_instruction(
    job: dict[str, Any],
    candidate: dict[str, Any],
    plan: dict[str, Any],
    sections: list[tuple[str, dict[str, Any]]],
) -> str:
    """The full JOB/CANDIDATE/PLAN system prompt, rebuilt per session from
    ``session.init``."""
    job_desc = job.get("description") or job.get("short_description") or ""
    resume = candidate.get("resume_text") or ""
    plan_goal = plan.get("goal") or ""

    section_block = (
        "\n".join(_render_section(i + 1, key, section) for i, (key, section) in enumerate(sections))
        or "(no sections provided)"
    )

    return "\n".join(
        [
            _SYSTEM_BASE,
            "",
            "JOB",
            f"Title: {job.get('title', 'this role')}",
            f"Description: {_truncate(_as_text(job_desc), _FIELD_CHARS)}" if job_desc else "",
            "",
            "CANDIDATE",
            f"Name: {candidate.get('name') or 'the candidate'}",
            f"Resume:\n{_truncate(resume, _RESUME_CHARS)}" if resume else "Resume: (not provided)",
            "",
            "INTERVIEW PLAN",
            f"Overall goal: {_truncate(_as_text(plan_goal), _FIELD_CHARS)}" if plan_goal else "",
            "Sections (conduct in this order):",
            section_block,
        ]
    )


def _greeting(
    job: dict[str, Any],
    candidate: dict[str, Any],
    sections: list[tuple[str, dict[str, Any]]],
) -> str:
    """The fixed opening line — no model call, ever. References the candidate,
    the role and the first planned section when ``session.init`` supplies them,
    same as the rest of the prompt."""
    name = str(candidate.get("name") or "").split(" ")[0] or "there"
    role = job.get("title")
    role_phrase = f"the {role} role" if role else "this role"
    first = sections[0][1].get("title") if sections else None
    starting = f" We'll start with {first}." if first else ""
    return (
        f"Hi {name}! I'm your AI interviewer for {role_phrase}. We'll go through "
        f"a few sections together.{starting} Let's get started."
    )


# ─── Actions (browser render contract) ─────────────────────────────────────────


class SectionChanged(Action):
    """Rendered by the ``/interview`` progress rail when the interviewer moves on
    to the next section. ``index``/``is_last`` are the brain's own pointer, not
    the model's count — the UI cannot recompute either from the conversation."""

    index: int
    key: str
    title: str
    is_last: bool


class InterviewCompleted(Action):
    """Rendered when the interview ends. ``summary`` is also this tool's whole
    parameter — the model's own performance summary is what the app renders."""

    summary: str = Field(
        default="", description="A brief overall summary of the candidate's performance."
    )


class SectionNotes(BaseModel):
    """The one parameter of ``advance_to_next_section`` — not rendered, just
    logged, since the section the app draws is computed from the brain's own
    pointer rather than anything the model reports."""

    section_notes: str = Field(
        default="",
        description="One or two sentences on how the candidate did in the section you are leaving.",
    )


class InterviewBotBrain(GeminiBrain):
    """One per session. Runs a structured voice interview: the inherited tool
    loop ``respond`` conducts each turn; the two tools below pace the sections.

    Per-session state (the ordered sections + the current section pointer) is
    seeded from ``session.init`` in :meth:`on_session_start`, since the brain is
    built before the session (and its payload) exists."""

    def __init__(self, *, llm: GeminiProvider, model: str = DEFAULT_MODEL) -> None:
        # The base system instruction only; the full JOB/CANDIDATE/PLAN prompt is
        # applied per session in on_session_start once session.init has arrived.
        super().__init__(client=llm.client, system_instruction=_SYSTEM_BASE, model=model)
        # Per-session interview state (populated in on_session_start). Ephemeral
        # in memory — no resume across disconnects, by design for the prototype.
        self.sections: list[tuple[str, dict[str, Any]]] = []
        self.current_index = 0
        self.ended = False
        self._greeting_text = ""

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        """The two the interviewer may call."""
        return [self.advance_to_next_section, self.mark_interview_completed]

    async def advance_to_next_section(self, notes: SectionNotes) -> str:
        """Move to the next interview section. Call this only when you have
        finished the current section. Tell the candidate you are moving on
        before calling. Returns the section you have now entered."""
        last_index = len(self.sections) - 1
        if self.current_index >= last_index:
            logger.info("interview: advance past final section (notes={!r})", notes.section_notes)
            return "This was the final section. Wrap up and call mark_interview_completed."

        self.current_index += 1
        key, section = self.sections[self.current_index]
        title = section.get("title") or key
        is_last = self.current_index == last_index
        logger.info(
            "interview: advance → [{}/{}] {} (notes={!r})",
            self.current_index + 1,
            len(self.sections),
            key,
            notes.section_notes,
        )
        self.session.dispatch(
            SectionChanged(index=self.current_index, key=key, title=title, is_last=is_last)
        )
        position = f"{self.current_index + 1} of {len(self.sections)}"
        instruction = (
            "This is the final section. After it, call mark_interview_completed."
            if is_last
            else "Conduct this section, then call advance_to_next_section when done."
        )
        return f"Entered section {key} ({title}), position {position}. {instruction}"

    async def mark_interview_completed(self, summary: InterviewCompleted) -> str:
        """End the interview. Call this only after the final section, once you
        have thanked the candidate."""
        self.ended = True
        logger.info("interview: mark_interview_completed (summary={!r})", summary.summary)
        self.session.dispatch(summary)
        return "completed"

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        """Settle this agent's own voice, then read the seeded job/candidate/plan
        (``session.init``), build this session's sections + full system prompt,
        and set aside the fixed greeting for :meth:`greet`."""
        await session.configure(
            Config(
                tts=TtsConfig(voice=Voice.OMNIVOICE_GAURI, language=Language.EN),
                stt=SttConfig(language=Language.EN),
            )
        )

        payload = dict(session.init or {})
        raw_job = payload.get("job")
        raw_candidate = payload.get("candidate")
        raw_plan = payload.get("plan")
        job: dict[str, Any] = raw_job if isinstance(raw_job, dict) else {}
        candidate: dict[str, Any] = raw_candidate if isinstance(raw_candidate, dict) else {}
        plan: dict[str, Any] = raw_plan if isinstance(raw_plan, dict) else {}
        raw_sections = plan.get("sections")
        self.sections = _order_sections(raw_sections if isinstance(raw_sections, dict) else {})
        self.current_index = 0
        self.ended = False

        # Bake the per-session JOB/CANDIDATE/PLAN into the system instruction so
        # every inference this session makes — starting with the first turn —
        # sees the full interview context.
        self.system_instruction = _build_system_instruction(job, candidate, plan, self.sections)
        self._greeting_text = _greeting(job, candidate, self.sections)
        logger.info(
            "interview: session start — {} sections, candidate={!r}, role={!r}",
            len(self.sections),
            candidate.get("name"),
            job.get("title"),
        )

    async def greet(self, session: Session) -> str:
        """The opener, written not generated: it references the candidate, the
        role and the first section straight from ``session.init``, so there is
        nothing for a model call to add and no first-token latency to hide."""
        return self._greeting_text
