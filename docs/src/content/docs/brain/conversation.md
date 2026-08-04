---
title: Handling a conversation
description: Stream from your LLM, call tools, drive the browser UI, react to client messages and idle silence, and reconfigure voice mid-call.
---

The echo brain shows the shape; a real agent adds a model, tools, and — often — a
screen it drives. This page covers the patterns you'll actually use. Examples are
Python.

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
response to a browser event — use `session.action`:

```python
async def on_session_start(self, session, start):
    session.action("show_welcome_screen", {"name": start.init.get("name")})
```

### Typed actions

The dict form above is the general one and always works. But a UI command is a
contract between two codebases, and a dict is where that contract goes to drift: a
key renamed in Python becomes a field that silently stops arriving in the browser.

Declare the shape instead. An `Action` is a pydantic model that knows its own wire
name — derived from the class name, `snake_case`:

```python
from voqalize.sdk import Action

class AddToCart(Action):            # → "add_to_cart"
    sku: str
    qty: int = 1

interaction.action(AddToCart(sku="pixel-9"))
```

That call is **byte-identical** to `interaction.action("add_to_cart", {"sku":
"pixel-9", "qty": 1})`, so you can migrate one command at a time with no
coordinated browser release. What you gain is a payload your editor, your linter
and your tests all know.

Actions compose — a field may be another model, or a list of them, and aliases are
respected all the way down:

```python
from pydantic import BaseModel, Field

class Leg(BaseModel):
    from_: str = Field(default="", alias="from")   # `from` is a Python keyword
    to: str = ""

class SearchFlights(Action):
    leg_id: str
    legs: list[Leg]

interaction.action(SearchFlights(leg_id="blr-out", legs=[Leg(**{"from": "BLR"}, to="SGN")]))
# → { "type": "ui_command", "action": "search_flights", "action_id": 3,
#     "leg_id": "blr-out", "legs": [{ "from": "BLR", "to": "SGN" }] }
```

The serialization rules, which are what the browser depends on:

- **By alias.** `from_` goes out as `from`. Construction accepts either spelling.
- **JSON mode.** A `date`, `Enum`, `Decimal` or `UUID` becomes a JSON scalar here,
  where a bad field is a clear Python error — not an opaque crash at the transport.
- **Every declared field is emitted, including `None`** (as JSON `null`). There is
  no `exclude_none`: the wire shape is a function of the *class*, not of which
  fields happened to be set, which is what lets the browser declare one total
  TypeScript interface. If a key should be absent rather than null, model it as a
  value the UI treats as empty (`""`, `[]`).
- **Unknown keyword arguments are rejected**, so a typo fails at the call site.

A few practical notes:

- The class name is part of your browser contract. Pin the wire name explicitly if
  you don't want that coupling: `class AddToCart(Action, name="add_to_cart")`.
- A field that would serialize to `type`, `action` or `action_id` is rejected when
  the class is defined — those keys belong to the envelope your fields are spread
  onto.
- `callback=` works exactly as it does for the dict form.
- Ruff's `RUF012` doesn't recognize a pydantic model reached through `Action`, so a
  mutable default (`items: list[Row] = []`) trips it. Either make the field
  required — usually right for a wire contract, since every field is emitted
  anyway — or write `Field(default_factory=list)`.

On the browser side, mirror each `Action` as a TypeScript interface and hand the
map to [`useUiCommand`](/docs/client/react/#typed-ui-commands-useuicommand). The
`travel` demo does exactly this, in both directions.

### Tools that return models

If you're on the [Google ADK adapter](/docs/brain/python/), a tool may return a
pydantic model directly — the natural thing to write once its arguments are models.
The SDK dumps it with the same rules an `Action` serializes by (`by_alias`, JSON
mode) before the result reaches the model, so the field names your tool declares
are the field names the model reads, and a `date` field doesn't become a
serialization crash at the API boundary:

```python
class SearchResult(BaseModel):
    status: str = "ok"
    legs: list[Leg] = []

async def search(leg_id: str) -> SearchResult:
    """Search one leg."""
    return SearchResult(status="found", legs=[Leg(**{"from": "BLR"}, to="SGN")])
    # the model sees: {"status": "found", "legs": [{"from": "BLR", "to": "SGN"}]}
```

Models nested inside a returned dict or list are dumped in place. A return with no
model in it is passed through untouched.

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
session.configure_language("hi")                         # BOTH halves — the whole call
session.configure_language("ta", voice="omnivoice/gauri")  # …and a different persona
session.configure_tts(voice="omnivoice/gaurav")          # voice only, next inference
session.configure_stt(vad_barge_in_ms=400)               # VAD knobs, applied live
```

**To change language, use `configure_language` — it is the only supported way.**
The two sides name the field differently (TTS `language`, STT `language_hint`), so
doing it as a `configure_tts` + `configure_stt` pair is two calls that can drift,
and a half-applied language is silent: the wrong recognizer just transcribes
badly, and the wrong voice reads the right words in a non-native accent that no
automated check can hear. This is how the `lead_qual` demo does multilingual
qualification.

Timing is inherited from each half: STT applies at the next turn boundary, TTS at
the next inference — never mid-utterance. `configure_stt`'s VAD knobs apply live.
Allowed values are in the [Voice & language catalog](/docs/reference/catalog/).

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
