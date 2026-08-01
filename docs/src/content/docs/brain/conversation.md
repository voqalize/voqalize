---
title: Handling a conversation
description: Stream from your LLM, call tools, drive the browser UI, react to client messages and idle silence, and reconfigure voice mid-call.
---

The echo brain shows the shape; a real agent adds a model, tools, and — often — a
screen it drives. This page covers the patterns you'll actually use. Examples are
Python; the Go equivalents are one-to-one (see [Build a brain (Go)](/docs/brain/go/)).

## Stream from your LLM

The transcript the SDK maintains (`interaction.conversation.messages`) is your
model context. Rebuild the request each turn from it, then stream the model's
output into `speak`:

```python
async def on_interaction(self, interaction: Interaction) -> None:
    messages = to_model_messages(interaction.conversation.messages)
    async with interaction.say() as speech:
        async for chunk in self.llm.stream(messages):
            await speech.speak(chunk.text)
```

Speak in small chunks as they arrive — the runtime handles TTS chunking and word
timing, and streaming keeps time-to-first-word low.

:::tip[Heard, not intended]
Assistant messages in the transcript hold what the user **heard**, truncated if
they interrupted. Rebuilding context from it means your model never thinks it said
something the user never heard. You don't commit anything yourself.
:::

## Call tools

A single user turn often needs several model calls: think, call a tool, look at the
result, speak. Each model call is its **own speech bracket** — open a new one per
call, and loop until the model stops asking for tools (cap the hops to stay safe):

```python
async def on_interaction(self, interaction: Interaction) -> None:
    messages = to_model_messages(interaction.conversation.messages)
    for _ in range(6):                       # cap tool hops
        async with interaction.say() as speech:
            reply = await self.llm.call(messages, tools=self.tools)
            for chunk in reply.text_chunks:
                await speech.speak(chunk)
        if not reply.tool_calls:
            break
        for call in reply.tool_calls:
            result = await self.run_tool(call.name, call.arguments)
            messages.append(tool_result_message(call, result))
```

The `travel` example (`sdk/python/examples/travel`) is a complete, working version
of this loop against Gemini.

## Drive the browser UI

Agents that *show* things — highlight a row, fill a form, add to a cart — send **UI
commands** to the browser. From within a turn, use `interaction.action`; the
browser receives it and can reply with an outcome:

```python
async with interaction.say() as speech:
    await speech.speak("Adding the Pixel to your cart.")
interaction.action("add_to_cart", {"sku": "pixel-9"})
```

On the browser side this arrives as a server message
`{ type: "ui_command", action: "add_to_cart", action_id, sku: "pixel-9" }` — the
args are spread onto the top level. See [React client SDK](/docs/client/react/)
for rendering these and replying with `action_outcome`.

To act **outside** a turn — render something the moment the call connects, or in
response to a browser event — use `session.action` (Python; the Go SDK does not
expose this yet):

```python
async def on_session_start(self, session, start):
    session.action("show_welcome_screen", {"name": start.init.get("name")})
```

## React to client messages

The browser can send messages to the brain outside any turn — a screen-state sync,
an uploaded photo, a button press. They arrive at `on_client_message`:

```python
async def on_client_message(self, session: Session, message: ClientMessage) -> None:
    if message.type == "state_sync":
        self.browser_state = message.data        # silent: remember what's on screen
    elif message.type == "photo_upload":
        # Take the floor on the id the runtime minted for this message.
        async with message.interaction.say() as speech:
            await speech.speak("Thanks — let me take a look at that.")
```

`message.type` is the message type the client sent via `sendMessage(type, data)`;
`message.data` is its payload.

Every client message arrives with an `interaction_id` the runtime already minted,
but the runtime does **not** decide whether the message deserves a reply — you do.
Read the data and return and nothing is spoken; touch `message.interaction` and you
have claimed the floor, so a barge-in cancels your response and the runtime is told
the interaction completed when your callback returns. Touching it is lazy and
idempotent; if you never touch it, the id simply goes unused.

## Re-engage on silence

If the user goes quiet, the runtime opens an interaction for you and calls
`on_user_idle`. Configure the window with `session.configure_idle(timeout_ms=…)`
(`0` disables idle detection):

```python
async def on_session_start(self, session, start):
    session.configure_idle(timeout_ms=8000)

async def on_user_idle(self, interaction: Interaction) -> None:
    idle = interaction.idle                      # level + idle_ms
    if idle is None or idle.level > 2:
        return                                   # stop nudging; let the silence ride
    async with interaction.say() as speech:
        await speech.speak("Still there? No rush.")
```

`level` starts at 1 and escalates while the silence persists (any user speech
resets it), so you can nudge gently first and wrap up later.
`interaction.transcript` is empty — nothing was said.

## Reconfigure voice mid-call

Change how the agent sounds or listens without dropping the call:

```python
session.configure_tts(voice="omnivoice/gaurav")          # applies to the NEXT inference
session.configure_stt(language_hint="hi")                # applies live, mid-utterance safe
```

`configure_tts` swaps voice/language/model at the next inference boundary (never
mid-utterance). `configure_stt` applies immediately — `language_hint` even switches
the recognition language mid-call, which is how the `lead_qual` demo does
multilingual qualification. Allowed values are in the
[Voice & language catalog](/docs/reference/catalog/).

## Greet on connect

Greeting is just an agent-initiated speech bracket in `on_session_start`:

```python
async def on_session_start(self, session, start):
    name = start.init.get("name", "there")
    async with session.say() as speech:
        await speech.speak(f"Hi {name}! What can I do for you today?")
```

`start.init` is the payload the client passed when it minted the session — use it
to personalize or to load per-call context (the `interview_bot` and `sugar` demos
carry the whole scenario in here).

## Next

- **[Voice protocol reference](/docs/reference/voice-protocol/)** — the frames
  behind `speak`, `action`, and the callbacks.
- **[Demo gallery](/docs/demos/gallery/)** — ten complete agents using these
  patterns.
