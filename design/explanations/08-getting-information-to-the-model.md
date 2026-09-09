# 8. Getting information to the model

> **The surprise.** There are four places a fact can live, they are ordered by
> latency, and choosing wrong costs you either a second of dead air or a wrong
> answer — on *every* turn, not once.

## Belief — the four tiers, and the question that picks one

Ask, of every change in the environment: **when does the model need to know?**

| Answer | Tier | Mechanism | Cost |
|---|---|---|---|
| **Right now** — it must produce a turn | Send it as a **user message** | `sendUserMessage` → `UserMessage` frame → `on_user_message` | a whole turn, and the floor |
| **By the next turn** | Append one line at the **tail** naming what changed | `ScreenState.moved` / `happened` | tokens only — cache-safe |
| **When the model asks** | The mirror those events keep true, behind a tool | tool reading the brain's own state | one model round trip |
| **When the model asks, and it can wait** | Don't store it — fetch on demand | tool doing I/O | a round trip **plus** the fetch |

**Nothing in this table ever writes to the system prompt.** That is tier zero, and
tier zero is immutable for the whole session — see [2](02-the-turn-budget.md).

- The tiers are cheap to get right and expensive to get wrong in a way that never
  shows up as an error. Tier-4 data placed in tier 2 makes every prompt bigger and
  every turn slower. Tier-2 data placed in tier 3 makes the model answer "what's on
  screen?" from a stale turn — which is why tier 2 carries the *notice* and tier 3
  serves the *content*, and neither does the other's job.
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

- **Tiers 2 and 3 are one mechanism, split by cost.** Tier 2 is a sentence the
  model cannot fail to see and cannot mistake for data — "The customer changed a
  quantity. Call `read_screen()` before you act on anything on screen." Tier 3 is
  that tool. The notice is unforgettable and nearly free; the content is exact and
  costs a round trip, and is fetched only when it matters.
- **The notice names, it never values.** `ScreenState.moved` takes a verb phrase
  completing "The <actor> …" — "picked a flight for the outbound leg", never the
  flight. A note carrying values is the old snapshot dump arriving one fact at a
  time, and it goes stale in the context the same way.
- **Placement is the whole design.** The note goes in as a user turn **just before
  the latest user turn**, so the entire prefix stays byte-identical and stays
  cached. Anything written into the system instruction rewrites the prefix on
  every call and throws the cache away ([2](02-the-turn-budget.md)).
- **Tier 1 is first-class on the wire.** `UserMessage { string text }` is a V→B
  frame in `proto/voqalize/frames/frames.proto`, described there as a "**Committed
  user stimulus. Text-only today; richer content gets new fields.**" It lands on
  `on_user_message` — a *speaking* callback — so a tier-1 injection produces a turn
  by the same path a spoken sentence does. Nothing special-cases it.
- **The browser chooses the tier by choosing a method.** `sendUserMessage` (tier 1,
  drives a turn) versus a browser message (tier 2/3, mute). That is what makes the
  split routable without the runtime interpreting payloads — it never has to guess
  whether a payload is worth speaking about, because the sender already said.
- **`None` appends nothing** — no header, no empty block. An event that changes
  nothing the model would act on folds into the mirror in silence.
- **Tier 3's structure is kept current by typed `AppEvent`s.** Each gesture patches
  the mirror; the tool reads that object synchronously. The tool is a *read of
  local memory*, which is why it belongs in tier 3 and not tier 4.
- **`ScreenState.version` makes the read enforceable.** A tool aimed at a screen
  the model has not re-read since it moved refuses, with a retriable reason.
  Prompt discipline is a request; this is a rule.
- **`on_rtvi` is not a generator** — a state push cannot become a turn by
  accident, and an app message mints no turn. Tier 1 is therefore an explicit act, never a side effect.
- Conversation history is the third home for a fact, and what goes in it must be
  the **heard** text ([3](03-interruption-and-heard-truth.md)).

## Proof

- **Tier 2, done conditionally:** an event that moves nothing appends nothing —
  `aura` folds a video's chapter tick into the mirror silently, because the clip
  reaching chapter three is not something the model needs woken for.
- **Tier 2 carrying derived guidance, not data:** `orderdesk`'s PENDING line names
  the rows still short of a SKU and the axes to ask about, so the model never
  re-asks a question the screen already answered. It is not the screen — it is the
  list of open questions, which is conversation state and therefore the brain's.
- **Tier 3, four times:** `aura`'s `get_screen_context`, `servicing`'s
  `get_advisor_context`, `legal`'s `get_reading_position`, `orderdesk`'s
  `catalog_search` — each a tool over the brain's own mirror.
- **Tier 4 handled as a workstream, not a wait:** `servicing`'s `prepare_case`
  returns `preparing_in_background` immediately ([6](06-tool-design.md)).
- **An app event explicitly takes no floor**, and three e2e suites assert it:
  `legal`'s `clause_focused` drives no screen command and mints no turn, `support`'s
  `photo_uploaded` the same, and the answer arrives on the next turn the person
  opens.
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

- **Tier 1's browser half is text-shaped only.** `client.sendText(...)` commits a
  typed sentence as a user turn and reaches `on_user_message`, so the tier is
  usable today — for text. The motivating cases are not text, which is the next
  gap.
- **Tier 2's helper is not in the SDK.** `AppEvent` / `AppEvents` ship in
  `sdk/python`; `ScreenState` lives in `demos/voqalize_demos/screen.py` because the
  read tool's name and the actor's word are things only a brain can supply. Whether
  that stays a demo helper is open — the discipline it encodes is not.
- **The `UserMessage` frame is text-only.** The motivating cases (an uploaded
  photo, a picked item) are not text, and the proto says so: "richer content gets
  new fields." The tier-1 story is honest only if the page says the frame will
  grow.
- **Open:** is there a fifth tier — a fact the model should never see, only the
  screen? (Prices the agent must not read out are exactly this. Since the screen
  left the context they are no longer in front of the model on every turn, but the
  read tool still serves them, so the question stands.)
- **Settled by measurement:** tier-2 cost. A 123-second production call put
  twenty-one full carts in front of one model — about 4,700 tokens, each labelled
  authoritative, none dated. A named change is one line. There is no snapshot size
  at which the snapshot wins.
