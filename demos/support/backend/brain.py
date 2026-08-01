"""SupportBrain — the "Returns Assistant" voice agent.

A ``voqalize.sdk.Brain`` (LLM + screen-driving tools + session state). Voqalize
dials this brain's WebSocket per session; the inherited tool-loop ``on_interaction``
runs a manual Gemini function-calling loop where **each LLM call is one
``interaction.say()`` bracket** (1:1 with the wire). Each tool body drives the
browser via ``interaction.action(name, {...})`` — the RTVI ``ui_command`` the
``/orders`` UI renders — while returning order/return data to the model.

Two browser→brain feedback channels beyond the standard turn arrive on
``on_client_message``. Both respond, so each takes the floor via
``message.interaction`` (the interaction Voice pre-minted for the client message):

  * ``photo_upload`` — a browser-captured product photo (data URL). We decode it,
    build a working context from the heard transcript, append the image plus a
    verification instruction as a final user turn, and run one agent-initiated
    inference (with the tool loop) so the agent can *verify* the product matches
    and the original box is present before approving the return.
  * ``return_submitted`` — the shopper tapped submit; we nudge the agent to close
    warmly with the confirmation number.

The LLM is **dependency-injected** as a :class:`GeminiProvider`; the brain owns
only the prompt, the tool schemas, and this session's return state. The
conversation record is framework-owned (``interaction.conversation`` /
``session.conversation``), rebuilt into Gemini's working context each turn.
"""

from __future__ import annotations

import base64
from typing import Any

from google.genai import types
from loguru import logger
from voqalize_demos import DEFAULT_MODEL, GeminiBrain, GeminiProvider

from .catalog import (
    ORDERS,
    VALID_ITEM_IDS,
    VALID_ORDER_IDS,
    get_item,
    get_order,
    order_detail,
    orders_for_prompt,
)

STORE_NAME = "Voqal Mobile"

_REFUND_METHODS = ["original_payment", "store_credit"]


_POLICY_FACTS = f"""RETURN POLICY ({STORE_NAME}) — answer only from these facts:
- Window: 30-day free returns from delivery. All three orders below are within the window.
- Condition: item must be in original condition with the original box and all included accessories.
- Defective items: a faulty or not-working item is eligible for a free return or replacement even if opened.
- Refund: to the original payment method in 5-7 business days, or instant store credit.
- Shipping: we email a prepaid return label; the refund is issued once the item is scanned by the carrier."""


_SYSTEM_INSTRUCTION = f"""You are the Returns Assistant, a calm, helpful voice support agent for {STORE_NAME}, an online phone and accessories store. The shopper is signed in, looking at their past orders, and talking to you live. You help them return or get a replacement for something — and you DRIVE THEIR SCREEN as you talk.

YOU CONTROL THE SCREEN. Whenever you reference an order, an item, or a step, call the matching tool so the shopper SEES it. Open the order, highlight the item, start the return, and fill the form with tools — never just describe.

THE SHOPPER'S ORDERS — these are the only orders. Refer to items by name; use the bracketed id only for tool arguments:
{orders_for_prompt()}

{_POLICY_FACTS}

HOW TO HANDLE A RETURN — follow these steps in order:
1. IDENTIFY: When the shopper describes an item (e.g. "my bluetooth mic"), find the order and item above, call open_order to show it, then highlight_item to point at the exact line. Ask them to confirm it's the right one.
2. OPEN THE CHECKLIST (only if they say it's broken / not working): before accepting a return, troubleshoot. Call start_diagnostics with the order, the item, and a list of 3 or 4 SHORT check labels you will run — for the Bluetooth mic, good ones are ["Charged and powered on", "Status LED lights up", "Enters pairing mode", "Re-paired from Bluetooth settings"]. This opens a checklist on the shopper's screen.
3. RUN THE CHECKS: ask the checks ONE AT A TIME, in order, as plain questions. After the shopper answers EACH one, call record_diagnostic with the step number (1 for the first check), a one-line summary of their answer, and result "ok" if that check is fine or "issue" if it revealed a problem. If a step actually fixes the device, stop and call complete_diagnostics with resolved true.
4. FINISH THE CHECKLIST: after the last check, call complete_diagnostics. If the device works now, set resolved true and reassure them — no return needed. If it still does not work, set resolved false with a short reason (e.g. "Won't pair after re-pairing") — this moves the shopper to the return form.
5. ASK FOR A PHOTO: tell them you need one quick photo — the product TOGETHER WITH its original box — and call request_photo so the photo button stands out. Wait for the photo.
6. VERIFY THE PHOTO: once the shopper sends a photo you will be shown the image. Check carefully: (a) does the product in the photo match the item being returned, and (b) is the original retail box visible? Call set_photo_check with what you found, then say the result in ONE short sentence. If something is missing (wrong item, or no box), ask them to retake the photo and stop here.
7. FILL THE FORM: if the photo passed, call fill_return_form to fill in the reason, condition, refund method, and a short note. Then ask the shopper to review it and tap "Confirm & submit return". Once they submit, thank them and tell them they'll get a prepaid label by email.

If the item is not defective (wrong item, changed their mind), skip the checklist and call start_return to go straight to the return form.

CONVERSATION STYLE:
- This is voice. Keep replies short — usually one or two sentences, never more than three.
- Ask ONE question at a time. Be warm, patient, and concise.
- Never read out ids or order numbers as raw text unless the shopper asks — say "your order from May 28th" instead.
- Never invent policies, orders, or items. If it is not above, say you are not sure.
- Open with a short, warm greeting and ask how you can help with their order."""


# Fixed opener — spoken straight to TTS with no LLM call, so the demo greets the
# instant the session connects (the model's ~1s first token is off the start path).
_GREETING = f"Hi! I'm the {STORE_NAME} Returns Assistant. How can I help with your order?"


# ─── Tool schemas (JSON-schema dicts) ──────────────────────────────────────────

# (tool_name, description, properties, required)
_TOOLSPECS: list[tuple[str, str, dict[str, Any], list[str]]] = [
    (
        "open_orders",
        "Show the shopper's list of past orders on their screen.",
        {},
        [],
    ),
    (
        "open_order",
        "Open one order's detail page on the shopper's screen and get its items. "
        "Use when the shopper refers to something they bought.",
        {
            "order_id": {
                "type": "string",
                "enum": VALID_ORDER_IDS,
                "description": "The id of the order to open.",
            },
        },
        ["order_id"],
    ),
    (
        "highlight_item",
        "Highlight one line item on the open order so the shopper sees exactly "
        "which item you mean. Use to confirm the item before starting a return.",
        {
            "order_id": {"type": "string", "enum": VALID_ORDER_IDS, "description": "The order id."},
            "item_id": {
                "type": "string",
                "enum": VALID_ITEM_IDS,
                "description": "The item to highlight.",
            },
        },
        ["order_id", "item_id"],
    ),
    (
        "start_diagnostics",
        "Open a troubleshooting checklist on the shopper's screen for a broken item. "
        "Pass the short labels of the checks you will run, in order. Call before you "
        "start asking the diagnostic questions.",
        {
            "order_id": {"type": "string", "enum": VALID_ORDER_IDS, "description": "The order id."},
            "item_id": {
                "type": "string",
                "enum": VALID_ITEM_IDS,
                "description": "The item being checked.",
            },
            "steps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3-4 short check labels, e.g. 'Status LED lights up'.",
            },
        },
        ["order_id", "item_id", "steps"],
    ),
    (
        "record_diagnostic",
        "Record the shopper's answer to one checklist step: marks it done, shows a "
        "one-line summary under it, and advances the highlight to the next step. Call "
        "after the shopper answers each check.",
        {
            "step": {"type": "integer", "description": "Which check, 1-based (1 = the first)."},
            "summary": {"type": "string", "description": "One short line summarizing the answer."},
            "result": {
                "type": "string",
                "enum": ["ok", "issue"],
                "description": "'ok' if the check is fine, 'issue' if it revealed a problem.",
            },
        },
        ["step", "summary", "result"],
    ),
    (
        "complete_diagnostics",
        "Finish the checklist. resolved=true if troubleshooting fixed the item (no "
        "return needed); resolved=false moves the shopper to the return form.",
        {
            "resolved": {"type": "boolean", "description": "True if the item works now."},
            "reason": {
                "type": "string",
                "description": "If not resolved, the short return reason.",
            },
        },
        ["resolved"],
    ),
    (
        "start_return",
        "Begin a return for one item: opens the return form on the shopper's "
        "screen, pre-filled for that item. Call after the shopper confirms the "
        "item and troubleshooting did not fix it.",
        {
            "order_id": {"type": "string", "enum": VALID_ORDER_IDS, "description": "The order id."},
            "item_id": {
                "type": "string",
                "enum": VALID_ITEM_IDS,
                "description": "The item being returned.",
            },
            "reason": {
                "type": "string",
                "description": "Short reason for the return, e.g. 'Not working — won't pair'.",
            },
        },
        ["order_id", "item_id", "reason"],
    ),
    (
        "request_photo",
        "Prompt the shopper to take or upload a photo of the product with its "
        "original box. Makes the photo button on the return form stand out. Call "
        "after start_return, then wait for the photo.",
        {},
        [],
    ),
    (
        "set_photo_check",
        "Record the result of verifying the shopper's uploaded photo. Call after "
        "you have looked at the photo, before telling the shopper the result.",
        {
            "matches": {
                "type": "boolean",
                "description": "True if the product in the photo matches the item being returned.",
            },
            "box_present": {
                "type": "boolean",
                "description": "True if the original box is visible in the photo.",
            },
            "note": {
                "type": "string",
                "description": "One short line describing what you saw, shown on screen.",
            },
        },
        ["matches", "box_present", "note"],
    ),
    (
        "fill_return_form",
        "Fill in the return form fields on the shopper's screen and enable the "
        "submit button. Call only after the photo check has passed. Then ask the "
        "shopper to review and tap 'Confirm & submit return'.",
        {
            "reason": {"type": "string", "description": "The return reason."},
            "condition": {
                "type": "string",
                "description": "Item condition, e.g. 'Opened — defective'.",
            },
            "refund_method": {
                "type": "string",
                "enum": _REFUND_METHODS,
                "description": "Where the refund goes.",
            },
            "notes": {
                "type": "string",
                "description": "A short note summarizing the issue and troubleshooting tried.",
            },
        },
        ["reason", "refund_method"],
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


class SupportBrain(GeminiBrain):
    """One per session. Owns this session's return state + screen-driving tools.
    ``on_interaction`` is the inherited tool-loop ``respond``; :meth:`dispatch_tool`
    runs each call. Browser-captured photos + submissions arrive via
    :meth:`on_client_message`."""

    def __init__(self, *, llm: GeminiProvider, model: str = DEFAULT_MODEL) -> None:
        super().__init__(
            llm=llm,
            system_instruction=_SYSTEM_INSTRUCTION,
            tools=_tools() or None,
            model=model,
        )
        # The item the current return is for — set on start_return / start_diagnostics
        # so a photo uploaded later can be verified against the right product.
        self._active_item_id: str | None = None

    # ─── Callbacks ──────────────────────────────────────────────────────

    async def on_session_start(self, session, start) -> None:
        await self.say(session, _GREETING)

    async def on_client_message(self, session, message) -> None:
        """Browser→Brain client message. ``photo_upload`` feeds a captured image
        into a verification turn; ``return_submitted`` nudges a warm close. Both
        respond, so we take the floor via ``message.interaction``."""
        if message.type == "photo_upload":
            await self._handle_photo(message.interaction, message.data or {})
        elif message.type == "return_submitted":
            await self._handle_submitted(message.interaction, message.data or {})

    # ─── Browser→brain: photo verification & submission ─────────────────

    async def _handle_photo(self, interaction, data: dict[str, Any]) -> None:
        """Decode the browser-captured photo and run one verification turn: the
        image + a verify instruction as a final user turn, over the heard transcript.
        The tool loop lets the model call set_photo_check / fill_return_form."""
        data_url = str(data.get("image") or "")
        _, _, b64 = data_url.partition(",")
        if not b64:
            logger.warning("support: photo_upload had no image data")
            return
        # Parse the mime type out of the data URL header (defaults to jpeg).
        header = data_url[: data_url.find(",")]
        mime = "image/jpeg"
        if header.startswith("data:") and ";" in header:
            mime = header[len("data:") : header.find(";")] or "image/jpeg"
        try:
            image_bytes = base64.b64decode(b64)
        except Exception as exc:
            logger.error("support: photo_upload decode failed: {}", exc)
            return

        item_id = str(data.get("item_id") or self._active_item_id or "")
        item = get_item(item_id)
        item_name = item["name"] if item else "the item being returned"
        logger.info(
            "support: photo received ({} bytes, mime={}) for {}", len(image_bytes), mime, item_id
        )

        instruction = (
            f"The shopper just uploaded this photo for the return of {item_name}. "
            "Verify it now: (1) does the product shown match this item, and (2) is "
            "the original retail box visible? Call set_photo_check with your findings, "
            "then tell the shopper the result in one short sentence. If it passed, "
            "call fill_return_form; if not, ask them to retake the photo."
        )
        parts = [
            types.Part.from_bytes(data=image_bytes, mime_type=mime),
            types.Part(text=instruction),
        ]
        await self._app_turn(interaction, parts)

    async def _handle_submitted(self, interaction, data: dict[str, Any]) -> None:
        rma = str(data.get("rma") or "")
        logger.info("support: return_submitted rma={}", rma)
        instruction = (
            f"The shopper just submitted the return (confirmation {rma}). Thank them "
            "warmly, tell them a prepaid return label is on its way by email, and that "
            "the refund lands once the carrier scans the package. One or two sentences."
        )
        await self._app_turn(interaction, [types.Part(text=instruction)])

    async def _app_turn(self, interaction, user_parts: list[types.Part]) -> None:
        """Run one turn triggered by a browser client message: build the working
        context from the heard transcript, append ``user_parts`` as a final user
        turn, and run the same tool loop as ``respond`` — over the client message's
        floor-owning ``interaction`` (the id Voice minted for it)."""
        contents = self.working_context(interaction)
        contents.append(types.Content(role="user", parts=user_parts))
        for _ in range(self._max_tool_hops):
            async with interaction.say() as inf:
                fcalls, model_parts = await self.stream(inf, contents)
            if model_parts:
                contents.append(types.Content(role="model", parts=model_parts))
            if not fcalls:
                return
            for fc in fcalls:
                result = self.dispatch_tool(interaction, fc.name, dict(fc.args or {}))
                contents.append(
                    types.Content(
                        role="tool",
                        parts=[
                            types.Part.from_function_response(
                                name=fc.name, response={"result": result}
                            )
                        ],
                    )
                )

    # ─── Tools ──────────────────────────────────────────────────────────

    def dispatch_tool(self, interaction, name: str, args: dict[str, Any]) -> str:
        """Run one tool call: drive the browser via ``interaction.action(...)`` (the
        RTVI ui_command the /orders UI renders) and return the order/return data the
        model needs. ``interaction`` is an :class:`Interaction` for a normal turn or a
        :class:`Session` for a browser-triggered turn — both expose ``.action``."""
        act = interaction.action
        if name == "open_orders":
            logger.info("support: open_orders")
            act("open_orders")
            return str({"orders": [order_detail(o) for o in ORDERS]})
        if name == "open_order":
            order_id = str(args.get("order_id", ""))
            order = get_order(order_id)
            if order is None:
                return str({"error": f"unknown order '{order_id}'"})
            logger.info("support: open_order {}", order_id)
            act("open_order", {"order_id": order_id})
            return str({"order": order_detail(order)})
        if name == "highlight_item":
            order_id = str(args.get("order_id", ""))
            item_id = str(args.get("item_id", ""))
            logger.info("support: highlight_item {} / {}", order_id, item_id)
            act("highlight_item", {"order_id": order_id, "item_id": item_id})
            item = get_item(item_id)
            return str({"status": "highlighted", "item": item["name"] if item else item_id})
        if name == "start_diagnostics":
            order_id = str(args.get("order_id", ""))
            item_id = str(args.get("item_id", ""))
            steps = [str(s) for s in (args.get("steps") or []) if str(s).strip()]
            order = get_order(order_id)
            item = get_item(item_id)
            if order is None or item is None or not steps:
                return str({"error": "need a valid order, item, and steps"})
            self._active_item_id = item_id
            logger.info("support: start_diagnostics {}/{} steps={}", order_id, item_id, len(steps))
            act("start_diagnostics", {"order_id": order_id, "item_id": item_id, "steps": steps})
            return str({"status": "diagnostics_open", "steps": steps})
        if name == "record_diagnostic":
            try:
                step = int(args.get("step") or 0)
            except (TypeError, ValueError):
                step = 0
            summary = str(args.get("summary", ""))
            result = str(args.get("result", "ok"))
            if result not in ("ok", "issue"):
                result = "ok"
            logger.info("support: record_diagnostic step={} result={}", step, result)
            act("record_diagnostic", {"step": step, "summary": summary, "result": result})
            return str({"status": "recorded", "step": step})
        if name == "complete_diagnostics":
            resolved = bool(args.get("resolved"))
            reason = str(args.get("reason", ""))
            logger.info("support: complete_diagnostics resolved={}", resolved)
            act("complete_diagnostics", {"resolved": resolved, "reason": reason})
            return str({"status": "diagnostics_complete", "resolved": resolved})
        if name == "start_return":
            order_id = str(args.get("order_id", ""))
            item_id = str(args.get("item_id", ""))
            reason = str(args.get("reason", ""))
            order = get_order(order_id)
            item = get_item(item_id)
            if order is None or item is None:
                return str({"error": "unknown order or item"})
            self._active_item_id = item_id
            logger.info("support: start_return {} / {} ({!r})", order_id, item_id, reason)
            act("start_return", {"order_id": order_id, "item_id": item_id, "reason": reason})
            return str({"status": "return_started", "item": item["name"], "reason": reason})
        if name == "request_photo":
            logger.info("support: request_photo (item={})", self._active_item_id)
            act("request_photo")
            return str({"status": "awaiting_photo"})
        if name == "set_photo_check":
            matches = bool(args.get("matches"))
            box_present = bool(args.get("box_present"))
            note = str(args.get("note", ""))
            passed = matches and box_present
            logger.info("support: set_photo_check matches={} box={}", matches, box_present)
            act(
                "set_photo_check",
                {
                    "matches": matches,
                    "box_present": box_present,
                    "passed": passed,
                    "note": note,
                },
            )
            return str({"status": "recorded", "passed": passed})
        if name == "fill_return_form":
            reason = str(args.get("reason", ""))
            condition = str(args.get("condition", "Opened — defective"))
            refund_method = str(args.get("refund_method", "original_payment"))
            notes = str(args.get("notes", ""))
            logger.info("support: fill_return_form reason={!r} refund={!r}", reason, refund_method)
            act(
                "fill_return_form",
                {
                    "reason": reason,
                    "condition": condition,
                    "refund_method": refund_method,
                    "notes": notes,
                },
            )
            return str({"status": "form_filled"})
        return "unknown tool"
