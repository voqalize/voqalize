"""Talk to Tushar with the real model and grade every turn.

    cd demos && uv run python -m tests.eval_saatvik.run                # every case
    cd demos && uv run python -m tests.eval_saatvik.run kit-3kw quote  # only these
    cd demos && uv run python -m tests.eval_saatvik.run --repeat 2     # each case twice

Each case is a real ``SaatvikBrain`` on a real ``brain_server`` socket, driven by
the conformance driver exactly as the e2e tests drive it, with the real Gemini in
place of the scripted one and the committed crawl as his knowledge. After each move
he makes, the runner reports the new page back the way the extension's adapter
does.

Two kinds of check:

- Rules, in code: the page actions a turn must or must not take, a reply that only
  points at the screen, too short for a conversation, sentences too long to follow
  by ear, a question at the end, Devanagari for a Hindi visitor, no exclamation mark.
- A judge, a second model call with the rubric below, for what code cannot see: did
  he answer, talk about something on the screen, keep the conversation going, stay
  plain, stay inside what he knows.

Writes ``REPORT.md`` beside this file (committed, so a change in behaviour shows in
review) and exits non-zero if any turn fails. Needs ``GEMINI_API_KEY``; not part of
CI, which has no key and must not depend on a model.
"""

from __future__ import annotations

import argparse
import asyncio
import fnmatch
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from loguru import logger
from voqalize_demos import DEFAULT_MODEL
from voqalize_demos.discovery import discover

from tests._harness import demo_from

from .cases import CASES, Case, Page, Turn

discover()

from voqalize_demos._loaded.saatvik import brain as saatvik  # noqa: E402
from voqalize_demos._loaded.saatvik import knowledge as kb  # noqa: E402

HERE = Path(__file__).resolve().parent
REPORT = HERE / "REPORT.md"
JUDGE_MODEL = os.environ.get("SAATVIK_JUDGE_MODEL", DEFAULT_MODEL)

DEVANAGARI = re.compile(f"[{chr(0x0900)}-{chr(0x097F)}]")
DEVANAGARI_DIGIT = re.compile(f"[{chr(0x0966)}-{chr(0x096F)}]")  # the voice reads digits badly
MAX_WORDS = 20  # one sentence (the prompt asks for under fifteen)
MAX_WORDS_LONG = 24
MAX_SENTENCES = 6
MAX_SENTENCES_LONG = 11
MIN_WORDS = 12  # less is not a conversation: the one-word answers this started from
MIN_WORDS_LONG = 35


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.?!।])\s+", text.strip()) if s]


def action_name(command: dict[str, Any]) -> str | None:
    """A ui-command as ``name:value``, or None for one that is not a page move."""
    name = str(command.get("command", ""))
    if name.startswith("__") or name == "lead_brief":
        return None
    payload = command.get("payload") or {}
    key = {
        "navigate": "path",
        "show_section": "heading",
        "open_faq": "question",
        "open_tab": "label",
        "open_document": "title",
        "open_enquiry": "kind",
        "book_product": "installation",
        "language_changed": "language",
    }.get(name)
    value = payload.get(key) if key else None
    return f"{name}:{value}" if value else name


@dataclass
class TurnResult:
    said: str
    heard: str
    actions: list[str]
    reads: list[str] = field(default_factory=list)
    form: dict[str, Any] | None = None  # the enquiry form's prefill after this turn
    problems: list[str] = field(default_factory=list)
    judge: dict[str, Any] = field(default_factory=dict)
    seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.problems


@dataclass
class CaseResult:
    case: Case
    turns: list[TurnResult]
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and all(t.ok for t in self.turns)


def rules(turn: Turn, r: TurnResult) -> None:
    def hit(pattern: str) -> bool:
        return any(fnmatch.fnmatch(a, pattern) for a in r.actions)

    for p in turn.expect:
        if not hit(p):
            r.problems.append(f"missing action {p}")
    if turn.any and not any(hit(p) for p in turn.any):
        r.problems.append(f"none of {', '.join(turn.any)}")
    for p in turn.forbid:
        if hit(p):
            r.problems.append(f"forbidden action {p}")
    text = r.heard.strip()
    if not text:
        r.problems.append("said nothing")
        return
    if "!" in text:
        r.problems.append("exclamation mark")
    parts = sentences(text)
    words = len(text.split())
    longest = max(len(s.split()) for s in parts)
    if words < (MIN_WORDS_LONG if turn.long else MIN_WORDS):
        r.problems.append(f"only {words} words")
    if longest > (MAX_WORDS_LONG if turn.long else MAX_WORDS):
        r.problems.append(f"a sentence of {longest} words")
    if len(parts) > (MAX_SENTENCES_LONG if turn.long else MAX_SENTENCES):
        r.problems.append(f"{len(parts)} sentences")
    if turn.hindi and not DEVANAGARI.search(text):
        r.problems.append("not in Hindi")
    if re.search(r"\d", text):
        r.problems.append("digits (numbers are spoken as words)")
    if DEVANAGARI_DIGIT.search(text):
        r.problems.append("Devanagari digits (the voice reads numbers as words)")
    for p in turn.say_not:
        if m := re.search(p, text, re.IGNORECASE):
            r.problems.append(f"said {m.group(0)!r}")
    if turn.say_any and not any(re.search(p, text, re.IGNORECASE) for p in turn.say_any):
        r.problems.append(f"none of {', '.join(turn.say_any)}")
    if turn.no_fill and any(a.startswith("open_enquiry") for a in r.actions):
        r.problems.append("opened the form for a question")
    if turn.fills:
        held = r.form or {}
        for f in turn.fills:
            if not held.get(f):
                r.problems.append(f"form has no {f}")
    if turn.ask and not text.rstrip().endswith("?"):
        r.problems.append("did not hand the conversation back with a question")


JUDGE = """You grade one turn of Tushar, the voice solar advisor on Saatvik Green Energy's website. A visitor browsing the site talks to him; he answers and moves their page (opens pages, scrolls to sections, opens FAQs and datasheets, runs the calculator, finds dealers, opens the enquiry form). His words are spoken aloud, so they must sound like a friendly, expert advisor on a call, in English or Hindi.

Grade the LAST turn only, against this rubric. Each is true or false.
- answers: he answered what the visitor actually asked, in words, as an advisor would (for something he cannot know, he said so plainly and offered the sales team, the toll-free number or the right page).
- screen: if he moved the page or the visitor is on a page, he talked about something specific on it or in what he showed, not just "here it is", "here's the page" or "ये देखिए". If nothing was shown and the question did not need it, true. The calculator's result, the dealer list and a form's state reach the page only after his turn, so for run_calculator, find_dealer and open_enquiry it is enough that he says what he is doing for them and why. A short "See the …?" naming a section heading counts as specific.
- conversation: he kept the conversation going with a natural, relevant question or offer tied to what the visitor said, and built on what they told him earlier in the call (city, bill, roof, power cuts). A generic "anything else?" is false. For a turn that hands over to a form or a person, an offer of the next step is enough.
- plain: a listener follows it first time: small everyday words, short sentences, no jargon dump, no reading a page aloud. Do NOT count words; length is checked separately.
- factual: everything he stated is supported by HIS INSTRUCTIONS below or by WHAT HE READ this turn; no invented prices, state subsidy amounts, figures or products.
- pass: all of the above are true.
Give "why" in one or two sentences, naming the exact problem if it fails.

HIS INSTRUCTIONS, WHICH ARE EVERYTHING HE KNOWS AND CAN DO
{knowledge}

CASE NOTE: {note}

THE CONVERSATION SO FAR, with the page actions he took and what he read on each turn:
{transcript}"""

GRADE_SCHEMA = {
    "type": "object",
    "properties": {
        k: {"type": "boolean"}
        for k in ("answers", "screen", "conversation", "plain", "factual", "pass")
    }
    | {"why": {"type": "string"}},
    "required": ["answers", "screen", "conversation", "plain", "factual", "pass", "why"],
}


async def judge(
    client: genai.Client, prompt: str, case: Case, history: list[str], *, last: bool
) -> dict[str, Any]:
    note = (case.note or "none") if last else "none (this is an earlier turn of the case)"
    text = JUDGE.format(knowledge=prompt, note=note, transcript="\n".join(history))
    for attempt in range(3):
        try:
            res = await client.aio.models.generate_content(
                model=JUDGE_MODEL,
                contents=text,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", response_json_schema=GRADE_SCHEMA
                ),
            )
            return json.loads(res.text or "{}")
        except Exception as exc:
            if attempt == 2:
                return {"pass": False, "why": f"judge failed: {exc}"}
            await asyncio.sleep(2 * (attempt + 1))
    return {}


#: The spec tabs the live site shows (checked with Playwright, 2026-10-14). The
#: crawl keeps no tabs, and the adapter reports them on a call.
_MODULE_TABS = ["Electrical", "Mechanical", "Warranty"]
_PUMP_TABS = ["Pump & Motor", "Controller", "Compliance & Warranty"]
TABS: dict[str, list[str]] = {
    "/modules/bifacial-g12r": _MODULE_TABS,
    "/modules/bifacial-g2g-m10r": _MODULE_TABS,
    "/modules/bifacial-g2tb": _MODULE_TABS,
    "/modules/mono-perc": _MODULE_TABS,
    "/modules/mono-facial-g2wb": _MODULE_TABS,
    "/batteries": [
        "Electrical",
        "BMS",
        "Charge",
        "Discharge",
        "Mechanical",
        "Temperature",
        "Front Panel",
        "Installation",
    ],
    "/bess": ["Battery System", "Conversion & Controls", "Safety & Delivery"],
    "/solar-pumps/submersible-dc": _PUMP_TABS,
    "/solar-pumps/surface-dc": _PUMP_TABS,
}


def page_report(path: str) -> dict[str, Any]:
    """What the adapter reports for ``path``: its title, headings, FAQs and tabs."""
    page = kb.KNOWLEDGE.page(path)
    if page is None:
        return {"path": path, "title": "", "headings": [], "faqs": []}
    return {
        "path": page.path,
        "title": page.title,
        "headings": list(page.headings),
        "faqs": [f.q for f in page.faqs],
        "tabs": TABS.get(page.path, []),
    }


def reads_since(history: list[types.Content], start: int) -> list[str]:
    """What read_topic and search_site returned in the contents after ``start``."""
    out: list[str] = []
    for content in history[start:]:
        for part in content.parts or []:
            fr = part.function_response
            if fr is not None and fr.name in ("read_topic", "search_site"):
                out.append(f"{fr.name}: {str((fr.response or {}).get('result', ''))[:3000]}")
    return out


async def run_case(client: genai.Client, case: Case, gate: asyncio.Semaphore) -> CaseResult:
    async with gate:
        prompt = ""
        history: list[str] = []
        results: list[TurnResult] = []
        try:
            async with demo_from("saatvik", lambda: saatvik.SaatvikBrain(client=client)) as rig:
                greeting = await rig.driver.start_session(
                    init={"page": case.page, "lang": case.lang}
                )
                brain = rig.brain
                prompt = brain.system_instruction  # type: ignore[attr-defined]
                history.append(f"Tushar (greeting): {greeting.text if greeting else ''}")
                for step in case.steps:
                    if isinstance(step, Page):
                        await rig.driver.send_ui_event("page_changed", page_report(step.path))
                        await asyncio.sleep(0.2)
                        history.append(f"[The visitor is on the page {step.path}.]")
                        continue
                    seen = len(rig.driver.ui_commands)
                    context = len(brain._history)  # type: ignore[attr-defined]
                    t0 = time.monotonic()
                    turn = await rig.driver.user_says(step.said, timeout=90.0, quiet_for=1.5)
                    new = rig.driver.ui_commands[seen:]
                    actions = [a for a in (action_name(c) for c in new) if a]
                    r = TurnResult(
                        step.said,
                        turn.text.strip(),
                        actions,
                        reads=reads_since(brain._history, context),  # type: ignore[attr-defined]
                        seconds=time.monotonic() - t0,
                    )
                    fills = [
                        c.get("payload", {}).get("prefill") or {}
                        for c in rig.driver.ui_commands
                        if c.get("command") == "open_enquiry"
                    ]
                    r.form = fills[-1] if fills else None
                    rules(step, r)
                    history.append(f"Visitor: {step.said}")
                    history.append(f"Tushar: {r.heard}   [actions: {', '.join(actions) or 'none'}]")
                    if r.form and any(a.startswith("open_enquiry") for a in actions):
                        history.append(f"   [the form now holds] {r.form}")
                    history.extend(f"   [he read] {x}" for x in r.reads)
                    r.judge = await judge(
                        client, prompt, case, history, last=step is case.steps[-1]
                    )
                    if not r.judge.get("pass"):
                        r.problems.append("judge: " + str(r.judge.get("why", "failed")))
                    results.append(r)
                    # The adapter reports the page he moved to, as on a call.
                    for c in new:
                        if c.get("command") == "navigate":
                            path = str((c.get("payload") or {}).get("path", ""))
                            await rig.driver.send_ui_event("page_changed", page_report(path))
                            await asyncio.sleep(0.2)
        except Exception as exc:
            logger.exception("case {} crashed", case.id)
            return CaseResult(case, results, error=repr(exc))
        mark = "PASS" if all(t.ok for t in results) else "FAIL"
        print(f"{mark}  {case.id}", flush=True)
        return CaseResult(case, results)


def report(runs: list[CaseResult], seconds: float) -> str:
    turns = [t for r in runs for t in r.turns]
    passed = sum(t.ok for t in turns)
    lines = [
        "# Tushar eval report",
        "",
        f"Model `{DEFAULT_MODEL}` at {saatvik.THINKING.thinking_level} thinking, judge `{JUDGE_MODEL}`. "
        f"{len(runs)} conversations, {len(turns)} turns, **{passed}/{len(turns)} turns pass**, "
        f"{sum(r.ok for r in runs)}/{len(runs)} conversations pass. Ran in {seconds:.0f}s. "
        "Generated by `cd demos && uv run python -m tests.eval_saatvik.run`; cases in `cases.py`.",
        "",
        "| Kind | Conversations passing |",
        "|---|---|",
    ]
    by_kind: dict[str, list[CaseResult]] = {}
    for r in runs:
        by_kind.setdefault(r.case.kind, []).append(r)
    lines += [f"| {kind} | {sum(r.ok for r in rs)}/{len(rs)} |" for kind, rs in by_kind.items()]
    lines.append("")
    for kind, rs in by_kind.items():
        lines += [f"## {kind}", ""]
        for r in rs:
            lines.append(f"### {'PASS' if r.ok else 'FAIL'} `{r.case.id}`")
            if r.case.note:
                lines.append(f"_{r.case.note}_")
            lines.append("")
            if r.error:
                lines.append(f"Crashed: `{r.error}`")
            for t in r.turns:
                lines.append(f"- **Visitor:** {t.said}")
                lines.append(f"  **Tushar:** {t.heard or '(silence)'}")
                lines.append(
                    f"  Actions: `{', '.join(t.actions) or 'none'}` · turn {t.seconds:.1f}s"
                )
                if t.problems:
                    lines.append(f"  Problems: {'; '.join(t.problems)}")
            lines.append("")
    return "\n".join(lines) + "\n"


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--parallel", type=int, default=5)
    ap.add_argument("--verbose", action="store_true", help="the brain's own log lines")
    args = ap.parse_args()
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        print("GEMINI_API_KEY is not set", file=sys.stderr)
        return 2
    logger.remove()
    logger.add(sys.stderr, level="INFO" if args.verbose else "ERROR")
    client = genai.Client(api_key=key)
    cases = [c for c in CASES if not args.ids or c.id in args.ids] * args.repeat
    unknown = set(args.ids) - {c.id for c in CASES}
    if unknown:
        print(f"no such case: {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2
    gate = asyncio.Semaphore(args.parallel)
    t0 = time.monotonic()
    runs = list(await asyncio.gather(*(run_case(client, c, gate) for c in cases)))
    text = report(runs, time.monotonic() - t0)
    (REPORT if not args.ids else HERE / ".last.md").write_text(text)
    turns = [t for r in runs for t in r.turns]
    print(
        f"\n{sum(t.ok for t in turns)}/{len(turns)} turns pass; {sum(r.ok for r in runs)}/{len(runs)} conversations"
    )
    return 0 if all(r.ok for r in runs) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
