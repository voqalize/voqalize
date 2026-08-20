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
Dispatch on `msg.action` and read the args as top-level fields (the browser's
`useUiCommand` hook does both — see `references/frontend.md`).

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

The browser replies with `sendMessage("action_result", {action_id, status, result})`.
The SDK matches it by `action_id` **at session scope** and routes it to your callback
— so a late outcome landing in a later interaction still fires the right one. Those
messages never reach `on_client_message`.

`Outcome` fields: `action_id`, `interaction_id` (the originating turn), `status`,
`result`.

### Declaring the shape: typed actions

The dict form above always works and is the general one. But a UI command is a
contract between two codebases, and a dict is where that contract drifts — a key
renamed in Python becomes a field that silently stops arriving in the browser.
Declare it instead. An `Action` is a pydantic model that carries its own wire name,
`snake_case`d from the class name:

```python
from voqalize.sdk import Action

class AddToCart(Action):            # → "add_to_cart"
    sku: str
    qty: int = 1

interaction.action(AddToCart(sku="oat-milk", qty=2))
```

That is **byte-identical on the wire** to the dict call above, so convert one
command at a time — no coordinated browser release. `callback=` works the same.

Serialization is exactly `model_dump(by_alias=True, mode="json")`:

- **By alias** — a `from_: str = Field(alias="from")` goes out as `from`.
  Construction accepts either spelling.
- **JSON mode** — a `date`/`Enum`/`Decimal`/`UUID` field becomes a JSON scalar here,
  where a bad field is a clear Python error rather than a transport crash.
- **Every declared field is emitted, `None` included** (as `null`). There is no
  `exclude_none`: the wire shape is a function of the *class*, not of which fields
  were set — that's what lets the browser declare one total TypeScript interface.
  If a key should be absent, model it as a value the UI reads as empty (`""`, `[]`).
- **Unknown kwargs are rejected**, so a typo fails at the call site.
- Nested models and lists of models compose, aliases included.

Notes:

- The class name *is* the browser contract. Pin it if you'd rather not couple them:
  `class AddToCart(Action, name="add_to_cart")`.
- A field serializing to `type`, `action` or `action_id` is rejected at class
  definition — those keys belong to the envelope your fields are spread onto.
- Ruff's `RUF012` doesn't see a pydantic model reached through `Action`, so
  `items: list[Row] = []` trips it. Make the field required (usually right — every
  field is emitted anyway) or use `Field(default_factory=list)`.

Mirror each `Action` as a TypeScript interface and hand the map to `useUiCommand`
(`references/frontend.md`). Python stays the source of truth.

### Tools that return models

On the Google ADK adapter, a tool may return a pydantic model directly. The SDK
dumps it with the same rules (`by_alias`, JSON mode) before the result reaches the
model, so your declared field names are the field names the model reads:

```python
async def search_flights(leg_id: str) -> FlightResults:
    """Search one leg."""
    return FlightResults(leg_id=leg_id, options=[...])
```

Models nested inside a returned dict or list are dumped in place; a return with no
model in it passes through untouched.

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
- outcome round-trip: `await driver.send_action_result(action_id, status="ok",
  result={...})`.

## Read next

- **`references/frontend.md`** — the browser half: `onServerMessage`, `sendMessage`,
  and the ambient UI that shows the agent moved the screen.
- **`references/testing.md`** — the full offline loop.
