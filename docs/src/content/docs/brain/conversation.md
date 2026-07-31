---
title: Handling a conversation
description: Stream from your LLM, call tools, drive the browser UI, react to app events, and reconfigure voice mid-call.
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
    async with interaction.inference() as inf:
        async for chunk in self.llm.stream(messages):
            await inf.speak(chunk.text)
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
result, speak. Each model call is its **own inference bracket** — open a new one per
call, and loop until the model stops asking for tools (cap the hops to stay safe):

```python
async def on_interaction(self, interaction: Interaction) -> None:
    messages = to_model_messages(interaction.conversation.messages)
    for _ in range(6):                       # cap tool hops
        async with interaction.inference() as inf:
            reply = await self.llm.call(messages, tools=self.tools)
            for chunk in reply.text_chunks:
                await inf.speak(chunk)
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
async with interaction.inference() as inf:
    await inf.speak("Adding the Pixel to your cart.")
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

## React to app events

The browser can send messages to the brain outside any turn — a screen-state sync,
an uploaded photo, a button press. They arrive at `on_app_event`:

```python
async def on_app_event(self, session: Session, event: AppEvent) -> None:
    if event.name == "state_sync":
        self.browser_state = event.data          # remember what's on screen
    elif event.name == "photo_upload":
        # kick off an agent-initiated inference to look at it
        async with session.inference() as inf:
            await inf.speak("Thanks — let me take a look at that.")
```

`event.name` is the message type the client sent via `sendMessage(type, data)`;
`event.data` is its payload.

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

Greeting is just an agent-initiated inference in `on_session_start`:

```python
async def on_session_start(self, session, start):
    name = start.init.get("name", "there")
    async with session.inference() as inf:
        await inf.speak(f"Hi {name}! What can I do for you today?")
```

`start.init` is the payload the client passed when it minted the session — use it
to personalize or to load per-call context (the `interview_bot` and `sugar` demos
carry the whole scenario in here).

## Next

- **[Voice protocol reference](/docs/reference/voice-protocol/)** — the frames
  behind `speak`, `action`, and the callbacks.
- **[Demo gallery](/docs/demos/gallery/)** — ten complete agents using these
  patterns.
