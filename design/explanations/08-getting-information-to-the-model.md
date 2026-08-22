# 8. Getting information to the model

> **The surprise.** There are four places a fact can live, they are ordered by
> latency, and choosing wrong costs you either a second of dead air or a wrong
> answer — on *every* turn, not once.

## Belief — the four tiers, and the question that picks one

Ask, of every change in the environment: **when does the model need to know?**

| Answer | Tier | Mechanism | Cost |
|---|---|---|---|
| **Right now** — it must produce a turn | Send it as a **user message** | `sendUserMessage` → `UserMessage` frame → `on_user_message` | a whole turn, and the floor |
| **By the next turn** | Fold into the next model call, **at the tail** | `grounding()` | tokens only — cache-safe |
| **When the model asks** | In-memory structure behind a tool | tool reading `browser_state` | one model round trip |
| **When the model asks, and it can wait** | Don't store it — fetch on demand | tool doing I/O | a round trip **plus** the fetch |

**Nothing in this table ever writes to the system prompt.** That is tier zero, and
tier zero is immutable for the whole session — see [2](02-the-turn-budget.md).

- The tiers are cheap to get right and expensive to get wrong in a way that never
  shows up as an error. Tier-4 data placed in tier 2 makes every prompt bigger and
  every turn slower. Tier-2 data placed in tier 3 makes the model answer "what's on
  screen?" from a stale turn.
- **Tier 1 is the dangerous one, and the wire makes you say so.** There is no way
  to trigger a turn by accident: to get one you must send a *user message*, which
  is the application declaring "this is a stimulus, the same kind a spoken
  sentence is." Everything else is an app message, and an app message is mute by
  construction. The default for an environment change is tier 2.
- **What tier 1 is actually for:** the human did something the agent must respond
  to *now*, and it did not arrive as speech — they uploaded a photo, pressed a
  button, dropped in a file, picked something from a list. It is still the user
  acting; only the modality differs. That is why it is a user message and not a
  new frame type.

## Facts

- **Tier 2, and why it beats tier 3 for anything on screen.** From
  `GoogleADKBrain.grounding()`: *"Why not a tool the model can call for the same
  data: a tool is only as fresh as the model's decision to call it, so the model
  can answer 'what's on screen?' from a stale turn. Grounding costs no round-trip
  and cannot be forgotten."*
- **Placement is the whole design, and there is a right answer.** `GeminiBrain`
  inserts the note as a user turn **just before the latest user turn** — so the
  entire prefix stays byte-identical and stays cached. `GoogleADKBrain` appends it
  to the **system instruction**, which rewrites the prefix on every single call
  and throws the cache away. Same name, opposite cost. The Gemini placement is the
  standard; the ADK one is a defect ([2](02-the-turn-budget.md), and see the
  practices list).
- **Tier 1 is first-class on the wire.** `UserMessage { string text }` is a V→B
  frame in `proto/voqalize/frames/frames.proto`, described there as a "**Committed
  user stimulus. Text-only today; richer content gets new fields.**" It lands on
  `on_user_message` — a *speaking* callback — so a tier-1 injection produces a turn
  by the same path a spoken sentence does. Nothing special-cases it.
- **The browser chooses the tier by choosing a method.** `sendUserMessage` (tier 1,
  drives a turn) versus a browser message (tier 2/3, mute). That is what makes the
  split routable without the runtime interpreting payloads — it never has to guess
  whether a payload is worth speaking about, because the sender already said.
- **`None` appends nothing** — no header, no empty block. A conditional tier-2 fact
  is genuinely absent when it does not apply.
- **Tier 3's structure is kept current by `state_sync`.** Incoming app messages
  update an in-memory object; the tool reads that object synchronously. The tool is
  a *read of local memory*, which is why it belongs in tier 3 and not tier 4.
- **`on_app_message` is not a generator** — a state push cannot become a turn by
  accident. Tier 1 is therefore an explicit act, never a side effect.
- Conversation history is the third home for a fact, and what goes in it must be
  the **heard** text ([3](03-interruption-and-heard-truth.md)).

## Proof

- **Tier 2, done conditionally:** `forge` — "before any snapshot arrives there is
  deliberately no workspace grounding." `orderdesk` — "`None` (nothing appended)
  until there is anything at all."
- **Tier 2 carrying derived guidance, not just data:** `orderdesk`'s grounding is
  the cart snapshot **plus** a PENDING line "naming the rows still short of a SKU
  and the axes to ask about, so the model never re-asks a question the screen
  already answered." The tier-2 payload does work the prompt would otherwise have
  to teach.
- **Tier 3, three times:** `aura`'s `get_screen_context`, `servicing`'s
  `get_advisor_context`, `orderdesk`'s `catalog_search` — each a tool over an
  in-memory structure fed by `state_sync`.
- **Tier 4 handled as a workstream, not a wait:** `servicing`'s `prepare_case`
  returns `preparing_in_background` immediately ([6](06-tool-design.md)).
- **`state_sync` explicitly takes no floor:** `sugar` — "silently, no turn is
  triggered by a `state_sync`"; the servicing e2e asserts it: "`state_sync` takes
  no floor, and then backs both the turn's grounding and…".
- **Tier 1, as a worked case:** the returns flow in `shopping` is the documented
  motivating example (dated — it predates this wire, and the demo as it stands is
  a catalog, not a returns desk). Worth re-reading before the page cites it.
- **Floor-free responses exist for tier-3 traffic:** `orderdesk` answers
  `catalog_search` with "a floor-free action — session-scoped, no inference, no
  speech — so neither a keystroke nor a tap can make the agent start talking over
  him."

## Cross-cutting

Tier choice is the concrete form of the 80/10/10 split in
[5](05-prompt-design.md): tiers 1–2 are the 80%, tier 3 is the 10%, tier 4 is the
10% that must be designed with feedback.

## Gap

- **`GoogleADKBrain.grounding()` writes to the system instruction and must stop.**
  This is not a documentation gap, it is a latency bug in shipping SDK code: it
  invalidates the prompt cache on every turn of every session. Fix is to append a
  `Content` at the tail in the `before_model_callback` instead. Until then the
  docstring's own argument for grounding ("costs no round-trip") is only half
  true — it costs no round-trip and a full cache miss.
- **Tier 1's browser half is not plumbed.** The wire frame exists, `on_user_message`
  receives it, and the name is chosen — but `sdk/react` today exposes only
  `sendMessage(type, data)` (`useVoqalSession.ts:154`), which is the app-message
  leg. So the tier is wire-supported and unfinished on the browser side — say that
  plainly rather than describing it as if a customer could use it today.
- **The `UserMessage` frame is text-only.** The motivating cases (an uploaded
  photo, a picked item) are not text, and the proto says so: "richer content gets
  new fields." The tier-1 story is honest only if the page says the frame will
  grow.
- **Open:** is there a fifth tier — a fact the model should never see, only the
  screen? (Prices the agent must not read out are exactly this, and today they
  *are* in the grounding.)
- **Open:** grounding cost. Folding a full cart snapshot into every call is tokens
  on every turn. We have no guidance on when a snapshot gets big enough that tier
  3 wins, and no measurement to draw the line.
