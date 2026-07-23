"""InterviewBotBrain — the job-interview conductor.

A :class:`~voqalize_demos.brains._gemini.GeminiBrain` that runs a structured voice
interview (Gemini + two section-pacing tools). Voqalize dials this brain's
WebSocket per session and the inherited ``respond`` tool-loop drives the
interview.

The per-session **init_payload** carries the JOB, the CANDIDATE, and a structured
INTERVIEW PLAN (assembled by the caller). The brain is built *before* the session
starts, so the payload arrives in :meth:`on_session_start` as ``start.init`` — we
read it there, build the ordered section list + the full JOB/CANDIDATE/PLAN system
instruction, and apply it to the config before generating the greeting.

Two tools pace the interview:

  * ``advance_to_next_section`` — move to the next planned section;
  * ``mark_interview_completed`` — end the interview after the last section.

Each tool drives the ``/interview`` UI via ``interaction.action(...)`` — the SDK
wraps the field payload in its RTVI ``ui_command`` envelope (``{"type":
"ui_command", "action": <name>, ...}``). The inner fields
(``index``/``key``/``title``/``is_last`` and ``summary``) are the browser render
contract.

Interview state (the current section pointer) is ephemeral in memory — there is
no resume across disconnects, by design for the prototype.
"""

from __future__ import annotations

import re
from typing import Any

from google.genai import types
from loguru import logger
from voqalize_demos import DEFAULT_MODEL, GeminiBrain, GeminiProvider

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
    init_payload."""
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


def _greeting_prompt(
    job: dict[str, Any],
    candidate: dict[str, Any],
    sections: list[tuple[str, dict[str, Any]]],
) -> str:
    """A one-shot prompt for the LLM-generated opening line (references the
    candidate + first section)."""
    name = str(candidate.get("name") or "").split(" ")[0] or "there"
    title = job.get("title") or "the role"
    first = sections[0][1].get("title") if sections else None
    opening = f" Begin the first section ({first})." if first else ""
    return (
        f"Greet {name} warmly by name and introduce yourself as their AI "
        f"interviewer for the {title} role. Briefly mention you'll go through "
        f"a few sections together.{opening} Keep it to two or three short "
        "sentences, then ask your first question."
    )


# ─── Tool schemas (JSON-schema dicts → genai) ──────────────────────────────────

# (tool_name, description, properties, required)
_TOOLSPECS: list[tuple[str, str, dict[str, Any], list[str]]] = [
    (
        "advance_to_next_section",
        "Move to the next interview section. Call this only when you have finished "
        "the current section. Tell the candidate you are moving on before calling. "
        "Returns the section you have now entered.",
        {
            "section_notes": {
                "type": "string",
                "description": "One or two sentences on how the candidate did in the "
                "section you are leaving.",
            },
        },
        [],
    ),
    (
        "mark_interview_completed",
        "End the interview. Call this only after the final section, once you have "
        "thanked the candidate.",
        {
            "summary": {
                "type": "string",
                "description": "A brief overall summary of the candidate's performance.",
            },
        },
        [],
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


class InterviewBotBrain(GeminiBrain):
    """One per session. Runs a structured voice interview: the inherited tool-loop
    ``respond`` conducts each turn; :meth:`dispatch_tool` paces the sections.

    Per-session state (the ordered sections + the current section pointer) is
    seeded from ``init_payload`` in :meth:`on_session_start`, since the brain is
    built before the session (and its payload) exists."""

    def __init__(self, *, llm: GeminiProvider, model: str = DEFAULT_MODEL) -> None:
        # The base system instruction only; the full JOB/CANDIDATE/PLAN prompt is
        # applied per session in on_session_start once init_payload has arrived.
        super().__init__(
            llm=llm, system_instruction=_SYSTEM_BASE, tools=_tools() or None, model=model
        )
        # Per-session interview state (populated on_session_start). Ephemeral in
        # memory — no resume across disconnects, by design for the prototype.
        self.sections: list[tuple[str, dict[str, Any]]] = []
        self.current_index = 0
        self.ended = False

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session, start) -> None:
        """Read the seeded job/candidate/plan (``start.init``), build this session's
        sections + full system prompt, then speak an LLM-generated greeting."""
        payload = dict(start.init or {})
        job = payload.get("job") or {}
        candidate = payload.get("candidate") or {}
        plan = payload.get("plan") or {}
        self.sections = _order_sections(plan.get("sections") or {})
        self.current_index = 0
        self.ended = False

        # Bake the per-session JOB/CANDIDATE/PLAN into the system instruction. The
        # base built self._config with only _SYSTEM_BASE (no payload at __init__);
        # rebuild it now so this session's inferences — including the greeting
        # below — see the full interview context.
        instruction = _build_system_instruction(job, candidate, plan, self.sections)
        self._config = self._config.model_copy(update={"system_instruction": instruction})
        logger.info(
            "interview: session start — {} sections, candidate={!r}, role={!r}",
            len(self.sections),
            candidate.get("name"),
            job.get("title"),
        )

        # Hybrid greeting: a quick "Hi!" is spoken instantly (no LLM call), then the
        # personalised intro + first question streams in behind it so the model's
        # first-token latency is off the perceived start path.
        await self.say_then_generate(
            session, "Hi!", _greeting_prompt(job, candidate, self.sections)
        )

    # ─── Tools ──────────────────────────────────────────────────────────

    def dispatch_tool(self, interaction, name: str, args: dict[str, Any]) -> str:
        """Pace the interview: mutate the section pointer + drive the ``/interview``
        UI via ``interaction.action(...)``. Returns a short string fed back to the
        model."""
        if name == "advance_to_next_section":
            return self._advance(interaction, args)
        if name == "mark_interview_completed":
            return self._complete(interaction, args)
        return "unknown tool"

    def _advance(self, interaction, args: dict[str, Any]) -> str:
        notes = str(args.get("section_notes", "")).strip()
        last_index = len(self.sections) - 1
        if self.current_index >= last_index:
            logger.info("interview: advance past final section (notes={!r})", notes)
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
            notes,
        )
        # Browser render — the fields pushed in the SDK's ui_command envelope.
        interaction.action(
            "section_changed",
            {"index": self.current_index, "key": key, "title": title, "is_last": is_last},
        )
        position = f"{self.current_index + 1} of {len(self.sections)}"
        instruction = (
            "This is the final section. After it, call mark_interview_completed."
            if is_last
            else "Conduct this section, then call advance_to_next_section when done."
        )
        return f"Entered section {key} ({title}), position {position}. {instruction}"

    def _complete(self, interaction, args: dict[str, Any]) -> str:
        summary = str(args.get("summary", "")).strip()
        self.ended = True
        logger.info("interview: mark_interview_completed (summary={!r})", summary)
        interaction.action("interview_completed", {"summary": summary})
        return "completed"
