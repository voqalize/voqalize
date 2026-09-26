"""SupportBrain — the "Returns Assistant" voice agent.

A ``GeminiBrain`` (LLM + screen-driving tools + session state). Voqalize dials
this brain's WebSocket per session; the inherited ``respond`` runs Gemini's
function calls itself, and **a turn is one request**: each call runs as it
arrives, after the speech before it has gone out, and its result is filed in the
context for the model to read with the shopper's next message. Each tool is a
bound ``async def`` method, listed by :attr:`~SupportBrain.tools`; its body
drives the browser via ``self.session.dispatch(...)`` (the RTVI ``ui-command`` the
``/orders`` UI renders) and returns what it did.

**No tool here is marked ``@needs_result_now``.** Every order, item and policy
fact is compiled into the prompt, so no tool knows anything the model does not:
each one puts on screen, or records, something the model has already named. The
prompt therefore has the assistant say its line and make the call in the same
response — a line held back for a result would wait for the shopper to speak
again.

The browser also reaches the brain outside any turn, over
:meth:`~voqalize.sdk.Brain.on_rtvi` — a photo the shopper captures, and the tap
that submits the form, each a typed :class:`~voqalize.sdk.AppEvent` (see
``app_events.py``). Neither takes the floor there: an upload must never put
the assistant's voice over someone still working the screen, so both fold into
the context via :meth:`~voqalize.sdk.GeminiBrain.append_to_context` and mark
that a word is owed. :meth:`~SupportBrain.on_user_idle` pays it — the shopper
going quiet is the one stimulus that means the floor is genuinely free, which is
why this brain arms an idle window at all.

The LLM's ``genai.Client`` is **dependency-injected**; the brain owns
only the prompt, the tool schemas, and this session's return state. The
conversation record lives in the base class's own history, rebuilt into
Gemini's working context every turn.
"""

from __future__ import annotations

import base64
from collections.abc import AsyncGenerator
from typing import Any, Literal

from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel, Field
from voqalize_demos import DEFAULT_MODEL, FallbackLine, GeminiBrain, landed

from voqalize.sdk import Action, RTVIMessage, Session, Speech, UserIdle, UserMessage
from voqalize.sdk.wire import Config, IdleConfig, Language, SttConfig, TtsConfig, Voice

from .app_events import SUPPORT_EVENTS, PhotoUploaded, ReturnSubmitted, SupportEvent
from .catalog import ORDERS, get_item, get_order, order_detail, orders_for_prompt

STORE_NAME = "Voqal Mobile"

DiagnosticResult = Literal["ok", "issue"]
RefundMethod = Literal["original_payment", "store_credit"]


_POLICY_FACTS = f"""RETURN POLICY ({STORE_NAME}) — answer only from these facts:
- Window: 30-day free returns from delivery. Every order below is within the window.
- Condition: item must be in original condition with the original box and all included accessories.
- Defective items: a faulty or not-working item is eligible for a free return or replacement even if opened.
- Refund: to the original payment method in 5-7 business days, or instant store credit.
- Shipping: we email a prepaid return label; the refund is issued once the item is scanned by the carrier."""


_SYSTEM_INSTRUCTION = f"""You are the Returns Assistant, a calm, helpful voice support agent for {STORE_NAME}, an online phone and accessories store. The shopper is signed in, looking at their past orders, and talking to you live. You help them return or get a replacement for something — and you DRIVE THEIR SCREEN as you talk.

EVERY RESPONSE STARTS WITH WORDS. Whenever you call a tool, the same response opens with the one short spoken line that goes with it — the line first, then the calls, so the screen moves while the shopper hears you. A response made only of tool calls is silence: the screen changes and the shopper hears nothing, because you do not get to speak again until they do. For example:
- The shopper says "my bluetooth mic stopped working": say "Is it the Bluetooth mic from your order on May 28th?" and call open_order and highlight_item in that response.
- The shopper answers a check: say the next check as a question, "Does the status light come on?", and call record_diagnostic in that response.
- The shopper wants to send something back: say "Sure, I've started the return." and call start_return in that response.
No tool here needs its result before you speak, and a line like "let me check" promises something that never comes. What a tool hands back, you read on your next turn; everything you need to answer is already written below.

YOU CONTROL THE SCREEN. Whenever you reference an order, an item, or a step, call the matching tool so the shopper SEES it. Open the order, highlight the item, start the return, and fill the form with tools — never just describe, and never act without the line that goes with it.

THE SHOPPER'S ORDERS — these are the only orders. Refer to items by name; use the bracketed id only for tool arguments:
{orders_for_prompt()}

{_POLICY_FACTS}

HOW TO HANDLE A RETURN — follow these steps in order:
1. IDENTIFY: When the shopper describes an item (e.g. "my bluetooth mic"), find the order and item above. In one response, ask them to confirm it's the right one (name the item and when it was ordered) and call open_order to show it and highlight_item to point at the exact line.
2. OPEN THE CHECKLIST (only if they say it's broken / not working): before accepting a return, troubleshoot. Call start_diagnostics with the order, the item, and a list of 3 or 4 SHORT check labels you will run — for the Bluetooth mic, good ones are ["Charged and powered on", "Status LED lights up", "Enters pairing mode", "Re-paired from Bluetooth settings"]. This opens a checklist on the shopper's screen. Ask the first check as your line in that same response.
3. RUN THE CHECKS: ask the checks ONE AT A TIME, in order, as plain questions. After the shopper answers EACH one, call record_diagnostic with the step number (1 for the first check), a one-line summary of their answer, and result "ok" if that check is fine or "issue" if it revealed a problem — and ask the next check in that same response. If a step actually fixes the device, stop and call complete_diagnostics with resolved true.
4. FINISH THE CHECKLIST: after the last check, call complete_diagnostics. If the device works now, set resolved true and reassure them in that same response — no return needed. If it still does not work, set resolved false with a short reason (e.g. "Won't pair after re-pairing") — this moves the shopper to the return form — and ask for the photo (next step) in that same response.
5. ASK FOR A PHOTO: tell them you need one quick photo — the product TOGETHER WITH its original box — and call request_photo in the same response so the photo button stands out. Then stop talking and let them do it.
6. VERIFY THE PHOTO: the moment they upload it you will be shown the image, and you get the next word without being asked for it. Check carefully: (a) does the product in the photo match the item being returned, and (b) is the original retail box visible? In ONE response, say the result in one short sentence and call set_photo_check with what you found. If something is missing (wrong item, or no box), that sentence asks them to retake the photo, and you stop there.
7. FILL THE FORM: if the photo passed, call fill_return_form in that same response to fill in the reason, condition, refund method, and a short note, and make your sentence ask the shopper to review it and tap "Confirm & submit return". Once they submit, thank them and tell them they'll get a prepaid label by email.

If the item is not defective (wrong item, changed their mind), skip the checklist: say one short line and call start_return in the same response to go straight to the return form.

CONVERSATION STYLE:
- This is voice. Keep replies short — usually one or two sentences, never more than three.
- Ask ONE question at a time. Be warm, patient, and concise.
- Never read out ids or order numbers as raw text unless the shopper asks — say "your order from May 28th" instead.
- Never invent policies, orders, or items. If it is not above, say you are not sure.
- Open with a short, warm greeting and ask how you can help with their order."""


# Fixed opener — spoken straight to TTS with no LLM call, so the demo greets the
# instant the session connects (the model's ~1s first token is off the start path).
_GREETING = f"Hi! I'm the {STORE_NAME} Returns Assistant. How can I help with your order?"

# How long a shopper has to be quiet before the assistant may take the floor. It is
# what turns a photo into something answerable: the capture returns at once and the
# shopper replies on screen, so without an idle stimulus there is no turn in which
# to say whether the photo passed. Short, because it is the latency between the tap
# and the verdict; harmless when nothing was tapped, because ``on_user_idle`` stays
# silent unless the screen owes the shopper a reply.
_IDLE_MS = 3000


# ─── Actions (screen-driving payloads) ─────────────────────────────────────────
#
# One class per tool. The wire name is ``snake_case(ClassName)`` — matching the
# tool's own name is what keeps the two readable side by side, not a rule the
# SDK enforces.


class OpenOrders(Action):
    pass


class OpenOrder(Action):
    order_id: str


class HighlightItem(Action):
    order_id: str
    item_id: str


class StartDiagnostics(Action):
    order_id: str
    item_id: str
    steps: list[str]


class RecordDiagnostic(Action):
    step: int
    summary: str
    result: DiagnosticResult = "ok"


class CompleteDiagnostics(Action):
    resolved: bool
    reason: str = ""


class StartReturn(Action):
    order_id: str
    item_id: str
    reason: str


class RequestPhoto(Action):
    pass


class SetPhotoCheck(Action):
    matches: bool
    box_present: bool
    passed: bool
    note: str = ""


class FillReturnForm(Action):
    reason: str
    condition: str = "Opened — defective"
    refund_method: RefundMethod = "original_payment"
    notes: str = ""


class PhotoCheckResult(BaseModel):
    """What ``set_photo_check`` asks the model for — everything but ``passed``,
    which is the brain's own conjunction of the two, not something to trust the
    model to compute consistently."""

    matches: bool = Field(
        description="True if the product in the photo matches the item being returned."
    )
    box_present: bool = Field(description="True if the original box is visible in the photo.")
    note: str = Field(
        default="", description="One short line describing what you saw, shown on screen."
    )


async def _silence() -> AsyncGenerator[Any, None]:
    """Yields nothing: an idle tick the assistant has no reason to answer."""
    for _ in ():
        yield


class SupportBrain(GeminiBrain):
    """One per session. Owns this session's return state; the inherited tool
    loop runs each turn, and each tool below drives the screen as it runs.
    ``on_rtvi`` folds the photo and the submit tap into the context without
    taking the floor; ``on_user_idle`` answers them — see the module
    docstring."""

    def __init__(self, *, client: genai.Client, model: str = DEFAULT_MODEL) -> None:
        super().__init__(client=client, system_instruction=_SYSTEM_INSTRUCTION, model=model)
        # The item the current return is for — set on start_return /
        # start_diagnostics so a photo uploaded later, with no item_id of its
        # own, can still be verified against the right product.
        self._active_item_id: str | None = None

        # Set when the shopper does something on screen that wants answering, and
        # cleared the moment the assistant speaks to it. It is what
        # ``on_user_idle`` reads.
        self._owed_a_reply = False

        # Speaks the line of the last call that landed when a turn acted on
        # screen and the model said nothing — see ``respond``.
        self._fallback = FallbackLine()

    # ─── Tools ──────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[Any]:
        """The tools the assistant may call. None is marked ``@needs_result_now``:
        see the module docstring."""
        return [
            self.open_orders,
            self.open_order,
            self.highlight_item,
            self.start_diagnostics,
            self.record_diagnostic,
            self.complete_diagnostics,
            self.start_return,
            self.request_photo,
            self.set_photo_check,
            self.fill_return_form,
        ]

    async def open_orders(self) -> str:
        """Show the shopper's list of past orders on their screen."""
        logger.info("support: open_orders")
        self.session.dispatch(OpenOrders())
        landed("Here are your orders.", "Your orders are on screen.")
        return str({"orders": [order_detail(o) for o in ORDERS]})

    async def open_order(self, action: OpenOrder) -> str:
        """Open one order's detail page on the shopper's screen and get its
        items. Use when the shopper refers to something they bought."""
        order = get_order(action.order_id)
        if order is None:
            return f"error: unknown order {action.order_id!r}"
        logger.info("support: open_order {}", action.order_id)
        self.session.dispatch(action)
        landed("Here's that order.", "The order is open.")
        return str({"order": order_detail(order)})

    async def highlight_item(self, action: HighlightItem) -> str:
        """Highlight one line item on the open order so the shopper sees
        exactly which item you mean. Use to confirm the item before starting a
        return."""
        logger.info("support: highlight_item {} / {}", action.order_id, action.item_id)
        self.session.dispatch(action)
        item = get_item(action.item_id)
        if item is not None:
            landed(f"That's the {item['name']}.", f"Here's the {item['name']}.")
        return str({"status": "highlighted", "item": item["name"] if item else action.item_id})

    async def start_diagnostics(self, action: StartDiagnostics) -> str:
        """Open a troubleshooting checklist on the shopper's screen for a
        broken item. Pass the short labels of the checks you will run, in
        order. Ask the first check in the same response as this call."""
        steps = [s for s in action.steps if s.strip()]
        if get_order(action.order_id) is None or get_item(action.item_id) is None or not steps:
            return "error: need a valid order, item, and steps"
        self._active_item_id = action.item_id
        logger.info(
            "support: start_diagnostics {}/{} steps={}", action.order_id, action.item_id, len(steps)
        )
        self.session.dispatch(
            StartDiagnostics(order_id=action.order_id, item_id=action.item_id, steps=steps)
        )
        landed("The checklist is on your screen.", "Here are the checks we'll run.")
        return str({"status": "diagnostics_open", "steps": steps})

    async def record_diagnostic(self, action: RecordDiagnostic) -> str:
        """Record the shopper's answer to one checklist step: marks it done,
        shows a one-line summary under it, and advances the highlight to the
        next step. Call after the shopper answers each check, in the same
        response that asks the next one."""
        logger.info("support: record_diagnostic step={} result={}", action.step, action.result)
        self.session.dispatch(action)
        landed("Noted.", "Got it, that's recorded.")
        return str({"status": "recorded", "step": action.step})

    async def complete_diagnostics(self, action: CompleteDiagnostics) -> str:
        """Finish the checklist. resolved=true if troubleshooting fixed the
        item (no return needed); resolved=false moves the shopper to the
        return form."""
        logger.info("support: complete_diagnostics resolved={}", action.resolved)
        self.session.dispatch(action)
        if action.resolved:
            landed("Glad it's working now.", "Great, no return needed.")
        else:
            landed("The return form is open.", "Let's get the return started.")
        return str({"status": "diagnostics_complete", "resolved": action.resolved})

    async def start_return(self, action: StartReturn) -> str:
        """Begin a return for one item: opens the return form on the
        shopper's screen, pre-filled for that item. Call after the shopper
        confirms the item and troubleshooting did not fix it — or straight
        away, skipping the checklist, if the item is not defective (wrong
        item, changed their mind)."""
        order = get_order(action.order_id)
        item = get_item(action.item_id)
        if order is None or item is None:
            return "error: unknown order or item"
        self._active_item_id = action.item_id
        logger.info(
            "support: start_return {} / {} ({!r})", action.order_id, action.item_id, action.reason
        )
        self.session.dispatch(action)
        landed("The return form is open.", f"The return for the {item['name']} is started.")
        return str({"status": "return_started", "item": item["name"], "reason": action.reason})

    async def request_photo(self) -> str:
        """Prompt the shopper to take or upload a photo of the product with
        its original box. You are shown the image as soon as it lands and get
        the next word, so do not ask them to tell you. Makes the photo button on the return
        form stand out. Call after start_return, in the same response as the line
        that asks for the photo."""
        logger.info("support: request_photo (item={})", self._active_item_id)
        self.session.dispatch(RequestPhoto())
        landed(
            "Please take a photo of it with its original box.",
            "One photo please, the product with its box.",
        )
        return str({"status": "awaiting_photo"})

    async def set_photo_check(self, result: PhotoCheckResult) -> str:
        """Record the result of verifying the shopper's uploaded photo, once
        you have looked at the image in the conversation. Call it in the same
        response as the one short sentence that tells the shopper the result."""
        passed = result.matches and result.box_present
        logger.info(
            "support: set_photo_check matches={} box={}", result.matches, result.box_present
        )
        self.session.dispatch(
            SetPhotoCheck(
                matches=result.matches,
                box_present=result.box_present,
                passed=passed,
                note=result.note,
            )
        )
        if passed:
            landed("The photo checks out.", "That photo looks good.")
        else:
            landed("Please retake the photo, with the product and its original box.")
        return str({"status": "recorded", "passed": passed})

    async def fill_return_form(self, action: FillReturnForm) -> str:
        """Fill in the return form fields on the shopper's screen and enable
        the submit button. Call only after the photo check has passed, in the
        same response as the line asking the shopper to review it and tap
        'Confirm & submit return'."""
        logger.info(
            "support: fill_return_form reason={!r} refund={!r}", action.reason, action.refund_method
        )
        self.session.dispatch(action)
        landed(
            "The form is filled in. Please review it and tap Confirm and submit return.",
            "It's all filled in. Have a look, then tap Confirm and submit return.",
        )
        return str({"status": "form_filled"})

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session: Session) -> None:
        await session.configure(
            Config(
                tts=TtsConfig(voice=Voice.OMNIVOICE_GAURAV, language=Language.EN),
                stt=SttConfig(language=Language.EN),
                idle=IdleConfig(timeout_ms=_IDLE_MS),
            )
        )

    async def greet(self, session: Session) -> str:
        """The opener is fixed — no model call, no first-token wait — so the
        shopper hears the assistant the instant the session connects."""
        return _GREETING

    async def respond(self, session: Session) -> AsyncGenerator[Speech, None]:
        """The inherited turn, and — when it acted on screen and said nothing —
        the line of the last call that landed, so the shopper is never left in
        silence while the screen moves. No second model request."""
        async for event in self._fallback.speak_if_silent(self, super().respond(session)):
            yield event

    def on_user_message(self, session: Session, msg: UserMessage) -> AsyncGenerator[Speech, None]:
        """The shopper spoke. Whatever they last did on screen is answered by the
        reply this turn produces, so the debt is settled here."""
        self._owed_a_reply = False
        return super().on_user_message(session, msg)

    def on_user_idle(self, session: Session, idle: UserIdle) -> AsyncGenerator[Speech, None]:
        """The shopper has gone quiet — and if the last thing they did was upload a
        photo or submit the return, this is the turn in which to answer it.

        A photo is an answer, but it arrives on :meth:`on_rtvi`, which cannot
        speak: an upload must never put the assistant's voice over someone still
        working the screen. So the verdict waits here, for the one stimulus that
        means the floor is genuinely free. Every other idle tick is silence — a
        shopper reading their screen is not a shopper to be prompted, and the
        context already carries the instruction, so the turn is a plain
        :meth:`respond` with nothing added."""
        if not self._owed_a_reply:
            return _silence()
        self._owed_a_reply = False
        logger.info("support: idle -> answering what the shopper did on screen")
        return self.respond(session)

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        """Browser→brain gesture. Both the photo the shopper captures and the
        submit tap fold into the context without taking the floor — an upload is
        not an interruption — and mark that the assistant owes a word about it,
        which :meth:`on_user_idle` delivers once the shopper is quiet."""
        event = SUPPORT_EVENTS.parse(msg)
        if event is None:
            return
        self.apply_event(event)

    # ─── Browser → brain: photo + submission, folded into the context ───

    def apply_event(self, event: SupportEvent) -> None:
        match event:
            case PhotoUploaded():
                self._ingest_photo(event)
            case ReturnSubmitted():
                self._ingest_submission(event)

    def _ingest_photo(self, event: PhotoUploaded) -> None:
        """Decode the browser-captured photo and fold it into the context as a
        final user turn: the image plus a verification instruction, ahead of the
        turn ``on_user_idle`` opens once the shopper stops fiddling with the
        camera."""
        header, _, b64 = event.image.partition(",")
        if not b64:
            logger.warning("support: photo_upload had no image data")
            return
        mime = "image/jpeg"
        if header.startswith("data:") and ";" in header:
            mime = header[len("data:") : header.find(";")] or "image/jpeg"
        try:
            image_bytes = base64.b64decode(b64)
        except Exception as exc:
            logger.error("support: photo_upload decode failed: {}", exc)
            return

        item_id = event.item_id or self._active_item_id or ""
        item = get_item(item_id)
        item_name = item["name"] if item else "the item being returned"
        logger.info(
            "support: photo received ({} bytes, mime={}) for {}", len(image_bytes), mime, item_id
        )

        instruction = (
            f"The shopper just uploaded this photo for the return of {item_name}. "
            "Verify it now: (1) does the product shown match this item, and (2) is "
            "the original retail box visible? In one response, tell the shopper the "
            "result in one short sentence and call set_photo_check with your findings. "
            "If it passed, also call fill_return_form and ask them to review and submit "
            "it; if not, ask them to retake the photo."
        )
        self.append_to_context(
            types.Content(
                role="user",
                parts=[
                    types.Part.from_bytes(data=image_bytes, mime_type=mime),
                    types.Part(text=instruction),
                ],
            )
        )
        self._owed_a_reply = True

    def _ingest_submission(self, event: ReturnSubmitted) -> None:
        """Fold the confirmation number into the context so the next turn — the one
        ``on_user_idle`` opens once the shopper is quiet — can close warmly."""
        rma = event.rma
        logger.info("support: return_submitted rma={}", rma)
        note = (
            f"The shopper just submitted the return (confirmation {rma}). Next time "
            "you speak, thank them warmly, tell them a prepaid return label is on "
            "its way by email, and that the refund lands once the carrier scans the "
            "package. One or two sentences."
        )
        self.append_to_context(types.Content(role="user", parts=[types.Part(text=note)]))
        self._owed_a_reply = True
