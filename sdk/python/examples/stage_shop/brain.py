"""A shop's brain on Stage: the cues its replies carry reach the page as the
voice says them, and the page's state comes back as named acts.

The moves are declared once, in ``scene.json`` (two of them taken from the
``commerce`` kit), and generated into ``stage_gen.py``::

    voqalize stage gen examples/stage_shop/scene.json --py examples/stage_shop/stage_gen.py

The page half is ``index.html``: the same spec, ``data-stage-*`` attributes in
its markup, and one ``attach`` call.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

from google import genai

from voqalize.sdk import RTVIMessage, Session, Speech
from voqalize.sdk.gemini import GeminiBrain, needs_result_now
from voqalize.sdk.stage import Mirror, Stage, StageEvent, StagePageEvents, StageResult, load_spec

from .stage_gen import MOVES, PROMPT_LINES, CartAddArgs, ReadRequest

SPEC = load_spec(Path(__file__).with_name("scene.json"))

PROMPT = "\n".join(
    [
        "You are the guide on Linen & Co.'s website. You can see and move the visitor's screen.",
        "Put a cue at the start of the sentence it belongs to; the page moves as you say it:",
        *(f"- {line}" for line in PROMPT_LINES),
        "Read the listing or the cart with read_screen before you say what is in it.",
        "Add to the cart only after the visitor said yes, with add_to_cart.",
    ]
)


class ShopBrain(GeminiBrain):
    def __init__(self) -> None:
        super().__init__(client=genai.Client(), system_instruction=PROMPT)
        self.stage = Stage(
            dispatch=lambda action: self.session.dispatch(action),
            moves=MOVES,
            mirror=Mirror(SPEC),
        )

    async def greet(self, session: Session) -> str | None:
        return "Hi! Looking for sheets? I can show you around."

    @property
    def tools(self) -> list[object]:
        return [self.read_screen, self.add_to_cart]

    def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The model's turn with every cue taken out of its words and sent to
        the page, to fire as the voice reaches them."""
        return self.stage.cued(super().respond(session))

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Results and state events from the page: the model hears one line
        for each, never the page's values."""
        event = StagePageEvents.parse(msg)
        if isinstance(event, StageEvent):
            folded = self.stage.handle(event)
            if folded is not None and folded.note:
                self.append_note(folded.note)
        elif isinstance(event, StageResult):
            result = self.stage.handle(event)
            if result is not None and result.outcome not in ("applied", "partial"):
                self.append_note(
                    f"[{result.move} did not happen: {result.detail or result.outcome}]"
                )
        elif event is not None:
            self.stage.handle(event)

    @needs_result_now
    async def read_screen(self, request: ReadRequest) -> str:
        """Read part of their screen, from what the page last reported."""
        assert self.stage.mirror is not None
        return self.stage.mirror.read(request.slice)

    async def add_to_cart(self, args: CartAddArgs) -> str:
        """Add an item to their cart, once they said yes."""
        self.stage.send("commerce.cart_add", args.model_dump())
        return "Adding it now; the page says when it is in."
