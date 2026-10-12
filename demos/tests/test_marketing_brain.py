"""Tanvi's brain without a model: the page map, her tools, the visitor's events, the
line she says when a turn moves the page in silence, and the generated TypeScript.

    cd demos && uv run pytest tests/test_marketing_brain.py
"""

from __future__ import annotations

import asyncio
import re
import subprocess
import sys
from pathlib import Path

from voqalize_demos.discovery import discover

from voqalize.sdk import SpeechChunk, UserMessage
from voqalize.sdk.events import RTVIMessage, RTVIType

discover()

from voqalize_demos._loaded.marketing.brain import (  # noqa: E402
    GREETING,
    SYSTEM_INSTRUCTION,
    ControlUsed,
    EndConversation,
    OpenLink,
    OpenSection,
    SectionOpened,
    Show,
    SiteCommand,
    TanviBrain,
)
from voqalize_demos._loaded.marketing.site import (  # noqa: E402
    LINKS,
    PAGES,
    SECTIONS,
    SECTIONS_BY_ID,
    TARGETS,
    TARGETS_BY_ID,
    core_knowledge,
    screens,
)

from ._marketing_fakes import (  # noqa: E402, F401
    FakeSession,
    brain_fixture,
    call,
    script,
    session_fixture,
    text,
)

DEMOS = Path(__file__).resolve().parents[1]
SITE = DEMOS / "marketing" / "frontend"
GENERATED = SITE / "src" / "scripts" / "actions.gen.ts"


def run(coro):
    return asyncio.run(coro)


def spoken(brain: TanviBrain, said: str) -> str:
    """Drive one visitor turn through the brain and return what Tanvi says."""

    async def go() -> str:
        out = []
        async for event in brain.on_user_message(brain.session, UserMessage(text=said)):
            if isinstance(event, SpeechChunk):
                out.append(event.text)
        return "".join(out)

    return run(go())


# ── The page map ─────────────────────────────────────────────────────────────


def test_every_target_belongs_to_a_section_or_a_page() -> None:
    pages = {x.id for x in PAGES}
    for t in TARGETS:
        home = t.section or t.page
        assert (t.section in SECTIONS_BY_ID) != (t.page in pages), t.id
        assert t.id.startswith(home + "."), t.id


def test_the_retail_checkout_can_be_shown(brain: TanviBrain, session: FakeSession) -> None:
    from voqalize_demos._loaded.marketing.brain import ShowRequest

    assert "checkout" in TARGETS_BY_ID["retail.scene2"].does.lower()
    run(brain.show(ShowRequest(target="retail.scene2")))
    assert session.actions == [Show(target="retail.scene2")]
    assert brain.page == "retail" and brain.open is None


def test_every_section_hands_the_conversation_back() -> None:
    for s in SECTIONS:
        assert s.follow.endswith("?"), s.id


def test_section_suggestions_name_real_targets() -> None:
    import json

    for s in json.loads((SITE / "src" / "data" / "sections.json").read_text()):
        if "try" in s:
            assert TARGETS_BY_ID[s["try"]["target"]].section == s["id"]


def test_the_controls_the_visitor_asked_for_exist() -> None:
    for wanted in (
        "pricing.inr",
        "pricing.usd",
        "pricing.monthly",
        "pricing.annual",
        "ways.developer",
        "ways.plug_and_play",
    ):
        assert wanted in TARGETS_BY_ID


def test_every_footer_page_is_reachable_except_the_policies() -> None:
    urls = {x.url for x in PAGES}
    for page in (
        "/solutions/retail",
        "/solutions/banking",
        "/solutions/insurance",
        "/solutions/healthcare",
        "/solutions/legal",
        "/solutions/support",
        "/about",
        "/story",
        "/contact",
        "/security",
    ):
        assert page in urls, page
    assert not urls & {"/privacy", "/dpa"}


def test_policy_questions_go_to_the_team() -> None:
    assert "Please reach out to the team" in SYSTEM_INSTRUCTION
    assert 'open_page(page="contact")' in SYSTEM_INSTRUCTION


def test_site_pages_open_beside_her_and_links_leave_the_site() -> None:
    assert all(x.url.startswith("/") for x in PAGES)
    assert all(x.url.startswith("https://") for x in LINKS)
    assert "/experience" in {x.url for x in PAGES}


def test_open_page(brain: TanviBrain, session: FakeSession) -> None:
    from voqalize_demos._loaded.marketing.brain import OpenPage, PageRequest

    run(brain.open_page(PageRequest(page="retail")))
    assert session.actions == [OpenPage(page="retail")]
    assert "Retail" in run(brain.where_they_are())


def test_links_point_where_answers_live() -> None:
    urls = {x.id: x.url for x in LINKS}
    assert urls["docs"] == "https://docs.voqalize.com"
    assert urls["mcp"].startswith("https://docs.voqalize.com/")
    assert not any(u.startswith("mailto:") for u in urls.values())


# ── What she is told ─────────────────────────────────────────────────────────


def test_she_never_sends_anyone_to_an_email_address() -> None:
    for text_ in (SYSTEM_INSTRUCTION, core_knowledge(), screens()):
        assert not re.search(r"[\w.]+@[\w-]+\.\w+", text_), (
            "an email address is in what Tanvi reads"
        )


def test_unknowns_go_to_the_docs_and_the_mcp_server() -> None:
    assert "open_link" in SYSTEM_INSTRUCTION
    assert "MCP server" in SYSTEM_INSTRUCTION
    assert "Never give out an email address" in SYSTEM_INSTRUCTION


def test_the_prompt_lists_every_target_and_link() -> None:
    for t in TARGETS:
        assert f"- {t.id}:" in SYSTEM_INSTRUCTION, t.id
    for x in LINKS:
        assert f"- {x.id}:" in SYSTEM_INSTRUCTION, x.id


def test_the_retired_lines_stay_retired() -> None:
    assert "You speak. It acts." not in SYSTEM_INSTRUCTION.replace(
        'Never say "You speak. It acts."', ""
    )
    assert "avatar" not in GREETING.lower()


def test_the_greeting_asks_a_question() -> None:
    assert GREETING.endswith("?")


# ── Her tools ────────────────────────────────────────────────────────────────


def test_show_switches_pricing_and_remembers_it(brain: TanviBrain, session: FakeSession) -> None:
    from voqalize_demos._loaded.marketing.brain import ShowRequest

    run(brain.show(ShowRequest(target="pricing.inr")))
    run(brain.show(ShowRequest(target="pricing.monthly")))
    assert session.actions == [Show(target="pricing.inr"), Show(target="pricing.monthly")]
    assert brain.open == "pricing"
    where = run(brain.where_they_are())
    assert "INR" in where and "monthly" in where


def test_open_link_and_scrolling(brain: TanviBrain, session: FakeSession) -> None:
    from voqalize_demos._loaded.marketing.brain import CommandRequest, LinkRequest

    run(brain.open_link(LinkRequest(link="mcp")))
    run(brain.site_command(CommandRequest(command="scroll_down")))
    run(brain.end_conversation())
    assert session.actions == [
        OpenLink(link="mcp"),
        SiteCommand(command="scroll_down"),
        EndConversation(),
    ]


# ── The visitor's own clicks ─────────────────────────────────────────────────


def test_a_visitor_click_is_noted_once(brain: TanviBrain) -> None:
    assert brain.note_for(SectionOpened(section="ways")) is not None
    assert brain.note_for(SectionOpened(section="ways")) is None
    note = brain.note_for(ControlUsed(target="pricing.inr"))
    assert note is not None and "rupees" in note
    assert brain.switches["currency"] == "INR" and brain.open == "pricing"


def test_control_used_arrives_over_rtvi(brain: TanviBrain) -> None:
    msg = RTVIMessage(
        type=RTVIType.UI_EVENT,
        data={"event": "control_used", "payload": {"target": "ways.developer"}},
    )
    run(brain.on_rtvi(brain.session, msg))
    assert brain.open == "ways"
    last = brain._history[-1]  # pyright: ignore[reportPrivateUsage]
    assert last.parts and "Developer integration" in (last.parts[0].text or "")


# ── A turn that moves the page and says nothing ──────────────────────────────


def test_a_silent_open_asks_the_model_to_speak(brain: TanviBrain, session: FakeSession) -> None:
    models = script(
        brain,
        [call("open_section", request={"section": "pricing"})],
        [text("It's per minute. See the three hundred free minutes up top? Want it in rupees?")],
    )
    said = spoken(brain, "What does it cost?")
    assert models.requests == 2
    assert session.actions == [OpenSection(section="pricing")]
    assert said.startswith("It's per minute.")


def test_twice_silent_falls_back_to_a_line_and_a_question(
    brain: TanviBrain, session: FakeSession
) -> None:
    script(brain, [call("open_section", request={"section": "pricing"})], [])
    said = spoken(brain, "What does it cost?")
    assert session.actions == [OpenSection(section="pricing")]
    assert SECTIONS_BY_ID["pricing"].line in said
    assert said.endswith("?")


def test_words_then_a_call_speaks_the_words_only(brain: TanviBrain, session: FakeSession) -> None:
    script(
        brain,
        [
            text(
                "Here it is in rupees. Starter is nine thousand nine hundred and ninety-nine a month.",
                done=False,
            ),
            call("show", request={"target": "pricing.inr"}),
        ],
    )
    said = spoken(brain, "Show me the price in rupees")
    assert session.actions == [Show(target="pricing.inr")]
    assert said.startswith("Here it is in rupees.")
    assert "There." not in said


def test_flat_arguments_still_run_the_tool(brain: TanviBrain, session: FakeSession) -> None:
    from voqalize_demos._loaded.marketing.brain import OpenPage

    script(
        brain,
        [
            text("This is the retail page. What do you sell?", done=False),
            call("open_page", page="retail"),
        ],
    )
    spoken(brain, "Show me retail")
    assert session.actions == [OpenPage(page="retail")]


def test_a_promised_link_is_given(brain: TanviBrain, session: FakeSession) -> None:
    models = script(
        brain,
        [text("The docs have that. I've put a link right below me. What are you building?")],
        [call("open_link", request={"link": "docs"})],
    )
    spoken(brain, "Where is the API reference?")
    assert models.requests == 2
    assert session.actions == [OpenLink(link="docs")]


def test_a_given_link_is_not_asked_for_again(brain: TanviBrain, session: FakeSession) -> None:
    models = script(
        brain,
        [
            text("I've put a link right below me. Which one?", done=False),
            call("open_link", request={"link": "docs"}),
        ],
    )
    spoken(brain, "Where are the docs?")
    assert models.requests == 1
    assert session.actions == [OpenLink(link="docs")]


# ── The browser's half ───────────────────────────────────────────────────────


def test_generated_typescript_is_current(tmp_path: Path) -> None:
    out = tmp_path / "actions.gen.ts"
    cli = Path(sys.executable).parent / "voqalize"
    subprocess.run(
        [str(cli), "types", "marketing/backend/brain.py", "-o", str(out)],
        cwd=DEMOS,
        check=True,
        capture_output=True,
    )

    def body(p: Path) -> str:
        return "\n".join(line for line in p.read_text().splitlines() if not line.startswith("//"))

    assert body(out) == body(GENERATED), "run pnpm brain:types in demos/marketing/frontend"
