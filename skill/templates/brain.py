"""Your Voqalize brain — starter template.

A `Brain` is the whole customer surface: it receives transcribed user turns and
speaks replies. Voqalize's runtime does WebRTC / speech-to-text / text-to-speech /
interruption — this code never touches audio, only text.

The callbacks you'll use:

- `on_session_start(session, start)` — the agent speaks first (the greeting).
  `start.init` is the app payload the browser sent at connect (see the React
  embed's `payload=` prop) — e.g. the logged-in user and their current cart.
- `on_interaction(interaction)` — one user turn; `interaction.transcript` is what
  they said. Reply with `inf.speak(...)` AND/OR drive the screen with
  `interaction.action(...)`.
- `on_app_event(session, event)` — a message the *browser* sent up (a tap, a
  state sync). `event.name` is the message type, `event.data` its payload.

## The two-way UI contract (this is what screen-driving apps need)

Brain → browser:  `interaction.action(name, {...args})`  (or `session.action(...)`
outside a turn). The browser receives, via the React SDK's `onServerMessage`:

    { "type": "ui_command", "action": name, "action_id": <int>, ...args }

The `args` dict is spread onto the top level — so `action("add_to_cart",
{"sku": "oat-milk", "qty": 2})` arrives as
`{type:"ui_command", action:"add_to_cart", action_id:7, sku:"oat-milk", qty:2}`.

Browser → brain:  the browser calls the SDK's `sendMessage(type, data)`; you
receive it in `on_app_event` as `AppEvent(name=type, data=data)`. The one special
type is `"action_outcome"` (`{action_id, status, result}`) — if you passed a
`callback=` to `.action(...)`, it's routed there instead of `on_app_event`.

Install (pre-release — the SDK isn't on PyPI yet): install it editable from the
Voqalize agent-sdk source you were given —
  pip install -e path/to/agent-sdk        (or: uv add --editable path/to/agent-sdk)
Once it's published the name will be `voqalize-agent-sdk`. Requires Python ≥ 3.12.
"""

from __future__ import annotations

from voqalize.sdk import AppEvent, Brain, Interaction, Session, SessionStart


class MyBrain(Brain):
    async def on_session_start(self, session: Session, start: SessionStart) -> None:
        # start.init carries whatever the browser passed as `payload=` at connect.
        user = start.init.get("user", {})
        greeting = f"Hi {user.get('name', 'there')}! What can I get you today?"
        async with session.inference() as inf:
            await inf.speak(greeting)

    async def on_interaction(self, interaction: Interaction) -> None:
        heard = interaction.transcript

        # Replace this stub with your logic / LLM. A real brain would parse the
        # request (or let an LLM call tools) and decide what to say + what to draw.
        #   async for chunk in my_llm.stream(interaction.conversation.messages):
        #       await inf.speak(chunk)

        # Drive the on-screen UI. `action(...)` is fire-and-forget: it is NOT a
        # coroutine (don't await it), it enqueues the command and returns an
        # `action_id` the SDK mints for you (used to match an optional outcome
        # callback). It only pushes a message to the browser — it does NOT persist
        # anything; writing the cart to your own backend is your code's job.
        interaction.action("add_to_cart", {"sku": "oat-milk", "qty": 2})

        async with interaction.inference() as inf:
            await inf.speak(f"Done — I added that. You said: {heard}")

    async def on_app_event(self, session: Session, event: AppEvent) -> None:
        # The browser sent something up (a tap, a state sync). React to it — e.g.
        # the user manually edited the cart, so update your working context.
        if event.name == "state_sync":
            self._cart = event.data.get("cart")
