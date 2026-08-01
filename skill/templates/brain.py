"""Your Voqalize brain — starter template.

A `Brain` is the whole customer surface: it receives transcribed user turns and
speaks replies. Voqalize's runtime does WebRTC / speech-to-text / text-to-speech /
interruption — this code never touches audio, only text.

The callbacks you'll use:

- `on_session_start(session, start)` — the agent speaks first (the greeting).
  `start.init` is the app payload the browser sent at connect (see the React
  embed's `payload=` prop) — e.g. the logged-in user and their current cart.
- `on_interaction(interaction)` — one user turn; `interaction.transcript` is what
  they said. Reply with `speech.speak(...)` AND/OR drive the screen with
  `interaction.action(...)`.
- `on_client_message(session, message)` — a message the *browser* sent up (a tap,
  a state sync). `message.type` is the message name, `message.data` its payload.
  It arrives with an `interaction_id` Voice already minted: read the data and
  return (silent — nothing is spoken), or take the floor by touching
  `message.interaction` and replying on it.
- `on_user_idle(interaction)` — the user went quiet past the idle timeout, and you
  hold the floor to re-engage. `interaction.idle` carries the escalation `level`
  and elapsed `idle_ms`. Return without speaking to let the silence ride. Set the
  timeout with `session.configure_idle(timeout_ms=…)` (`0` disables it).

## The two-way UI contract (this is what screen-driving apps need)

Brain → browser:  `interaction.action(name, {...args})`  (or `session.action(...)`
outside a turn). The browser receives, via the React SDK's `onServerMessage`:

    { "type": "ui_command", "action": name, "action_id": <int>, ...args }

The `args` dict is spread onto the top level — so `action("add_to_cart",
{"sku": "oat-milk", "qty": 2})` arrives as
`{type:"ui_command", action:"add_to_cart", action_id:7, sku:"oat-milk", qty:2}`.

Declare the command instead of assembling a dict, and both sides get a contract
they can check — same wire bytes, so you can convert one command at a time:

    from voqalize.sdk import Action

    class AddToCart(Action):            # wire name: "add_to_cart"
        sku: str
        qty: int = 1

    interaction.action(AddToCart(sku="oat-milk", qty=2))

Fields serialize by alias in JSON mode, every declared field is emitted (`None`
becomes `null`), and unknown kwargs are rejected. Full rules, plus the browser's
matching `useUiCommand` hook: references/ui-actions.md.

Browser → brain:  the browser calls the SDK's `sendMessage(type, data)`; you
receive it in `on_client_message` as `ClientMessage(type=type, data=data)`. The
one special type is `"action_outcome"` (`{action_id, status, result}`) — if you
passed a `callback=` to `.action(...)`, it's routed there instead of
`on_client_message`.

Install (pre-release — the SDK isn't on PyPI yet). Clone
https://github.com/voqalize/voqalize and install it editable from the clone:

  uv pip install -e voqalize/sdk/python   (or: pip install -e voqalize/sdk/python)

Once it's published the name will be `voqalize-agent-sdk`. Requires Python ≥ 3.12.
The SDK is pipecat-free — installing it pulls no audio dependencies.

Test it without a microphone: `templates/test_brain.py` drives this Brain over a
real socket in text mode using `voqalize.conformance`. Write the tests as you go.
"""

from __future__ import annotations

from voqalize.sdk import Brain, ClientMessage, Interaction, Session, SessionStart


class MyBrain(Brain):
    async def on_session_start(self, session: Session, start: SessionStart) -> None:
        # start.init carries whatever the browser passed as `payload=` at connect.
        user = start.init.get("user", {})
        greeting = f"Hi {user.get('name', 'there')}! What can I get you today?"
        async with session.say() as speech:
            await speech.speak(greeting)

    async def on_interaction(self, interaction: Interaction) -> None:
        heard = interaction.transcript

        # Replace this stub with your logic / LLM. A real brain would parse the
        # request (or let an LLM call tools) and decide what to say + what to draw.
        #   async for chunk in my_llm.stream(interaction.conversation.messages):
        #       await speech.speak(chunk)

        # Drive the on-screen UI. `action(...)` is fire-and-forget: it is NOT a
        # coroutine (don't await it), it enqueues the command and returns an
        # `action_id` the SDK mints for you (used to match an optional outcome
        # callback). It only pushes a message to the browser — it does NOT persist
        # anything; writing the cart to your own backend is your code's job.
        interaction.action("add_to_cart", {"sku": "oat-milk", "qty": 2})

        async with interaction.say() as speech:
            await speech.speak(f"Done — I added that. You said: {heard}")

    async def on_client_message(self, session: Session, message: ClientMessage) -> None:
        # The browser sent something up (a tap, a state sync). React to it — e.g.
        # the user manually edited the cart, so update your working context.
        # Reading `message.data` and returning is SILENT: nothing is spoken.
        if message.type == "state_sync":
            self._cart = message.data.get("cart")

        # To ANSWER a client message instead, take the floor by touching
        # `message.interaction` — the interaction Voice pre-minted for it. Only
        # touching it makes the agent speak; the branch above stays silent.
        if message.type == "help_tapped":
            async with message.interaction.say() as speech:
                await speech.speak("Sure — what do you need a hand with?")

    async def on_user_idle(self, interaction: Interaction) -> None:
        # The user has gone quiet. `interaction.idle.level` escalates (1, 2, 3…)
        # while the silence persists — nudge once, then let it ride.
        idle = interaction.idle
        if idle is not None and idle.level == 1:
            async with interaction.say() as speech:
                await speech.speak("Still there? Take your time.")
