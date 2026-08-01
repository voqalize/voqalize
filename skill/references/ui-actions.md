# UI actions — the two-way contract

For agents that drive the screen (a cart, a form, a map, a dashboard), brain and
browser exchange JSON messages with **fixed shapes**. This is what makes Voqalize a
voice *operator* rather than a chat widget: the agent moves the same UI the user
touches, and stays in sync when the user moves it back.

Skip this reference entirely if the agent only talks.

---

## Brain → browser

```python
interaction.action("add_to_cart", {"sku": "oat-milk", "qty": 2})
```

The browser's `onServerMessage` receives:

```json
{ "type": "ui_command", "action": "add_to_cart", "action_id": 7, "sku": "oat-milk", "qty": 2 }
```

**The args dict is spread onto the top level** — not nested under `data` or `args`.
Switch on `msg.action` and read the args as top-level fields.

Rules that trip people up:

- **`action(...)` is not a coroutine.** Don't `await` it. It enqueues the command and
  returns the `action_id` the SDK minted.
- **It only messages the browser.** It persists nothing. Writing the cart to your own
  backend is your brain code's job.
- **`session.action(...)` is the same thing outside a turn** — from
  `on_session_start`, from `on_client_message`, or from a background task that
  resolves after the triggering interaction ended. Actions are floor-free (they carry
  no audio), so the brain may fire one at any time.
  `interaction.action(...)` is just `session.action(...)` attributed to that turn.

### Getting a result back (optional)

```python
def done(outcome):                      # sync or async
    print(outcome.status, outcome.result)

interaction.action("checkout", {"total": 42}, callback=done)
```

The browser replies with `sendMessage("action_outcome", {action_id, status, result})`.
The SDK matches it by `action_id` **at session scope** and routes it to your callback
— so a late outcome landing in a later interaction still fires the right one. Those
messages never reach `on_client_message`.

`Outcome` fields: `action_id`, `interaction_id` (the originating turn), `status`,
`result`.

---

## Browser → brain

The browser calls `session.sendMessage(type, data)` (from `useVoqalSession` or the
`VoqalAgent` render-prop). The brain gets:

```python
async def on_client_message(self, session: Session, message: ClientMessage) -> None:
    ...
```

with `message.type`, `message.data`, `message.id` (browser-supplied, may be empty),
and `message.interaction_id`.

### The interaction_id semantics — this is the important part

Voice mints an `interaction_id` for **every** client message and delivers it
unconditionally. Voice never interprets the message or decides whether it deserves a
reply. **The brain decides**, and it decides by whether it touches
`message.interaction`:

| What you do | What happens |
|---|---|
| Read `message.data`, return | **State-only.** Nothing is spoken. The pre-minted id is spent on posterity. This is the default and the common case. |
| Touch `message.interaction` | **Take the floor.** The interaction materializes lazily, gets registered, and you respond on it (`say()`). Voice is told it completed when `on_client_message` returns, and a barge-in can cancel your response. |

```python
async def on_client_message(self, session, message):
    if message.type == "cart_edited":
        self._cart = message.data.get("cart")        # silent — no interaction
        return

    if message.type == "help_tapped":
        async with message.interaction.say() as speech:   # takes the floor
            await speech.speak("Sure — what do you need a hand with?")
```

Reading `.interaction` is idempotent; never reading it means no interaction is
driven. **Responding is opt-in.**

Design guidance: make state syncs silent and taps vocal. An agent that narrates every
click is exhausting; an agent that doesn't know the user just emptied their cart is
wrong.

---

## Testing both directions

`templates/test_brain.py` covers this without a browser:

- brain → browser: `await driver.collect_ui_commands(min_count=1)` returns the exact
  envelopes above.
- browser → brain, silent: `await driver.send_client_message("cart_edited", {...})`.
- browser → brain, answered: `turn = await driver.client_message("help_tapped", {})`
  — waits for the reply and returns it.
- outcome round-trip: `await driver.send_action_outcome(action_id, status="ok",
  result={...})`.

## Read next

- **`references/frontend.md`** — the browser half: `onServerMessage`, `sendMessage`,
  and the ambient UI that shows the agent moved the screen.
- **`references/testing.md`** — the full offline loop.
