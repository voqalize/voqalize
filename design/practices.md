# Practices — how we design a voice agent

The internal companion to the one public page,
[Designing for voice](../docs/src/content/docs/design/index.md). That page is the
argument, written for a customer. This is the rule set behind it, written for us
and governed by nothing: blunt, numbered, and argued
with directly rather than re-derived inside each section.

Every line is **agreed** (we would defend it today), **contested** (we disagree,
or the evidence is thin), or **violated** (we believe it and our own code breaks
it). A rule with no citation is one we hold on reasoning alone, and that is worth
seeing.

**Everything here assumes a screen, and that is a scope boundary rather than an
oversight.** There is no telephony in the product: the runtime is WebRTC, every
demo is a browser, and nothing in the repo mentions PSTN or SIP. "Voice alongside
a visual surface" is what we build, and a third of these rules — 1, 2, 18, 21, 31
— are *defined* by it. A telephony product would need a different set, not a
subset.

---

## Output

1. **Speak the pointer, render the payload.** Voice carries intent,
   acknowledgement, and the one number that matters. The screen carries the
   record. — *agreed, and every demo enforces it by hand.*
   → [Voice points, the screen holds](../docs/src/content/docs/design/index.md#voice-points-the-screen-holds)
2. **Never recite what is on screen.** Lists, prices, ids, SKUs, units: gesture at
   them. — *agreed; eleven prompts say it eleven ways.*
3. **Never narrate your own actions.** The action already painted the screen. — *agreed.*
4. **The default reply is one short line.** Anything longer needs a reason. — *agreed.*
5. **Batch your questions.** Two questions in one breath beat two turns. — *agreed.*

## Latency

6. **Start fast, don't be short.** The interval you own is callback entry → first
   `SpeechChunk`. Nothing else in the product is yours. — *agreed.*
   → [The turn budget](../docs/src/content/docs/design/index.md#the-turn-budget)
7. **Never leave silence around a tool call.** Speak a tiny line first, then call. — *agreed.*
8. **`greet` contains no model call.** Fixed line, or a template over `session.init`.
   — *agreed, enforced by the return type.*
9. **The system prompt is the cache prefix. Write it once per session; never edit
   it.** Volatile context goes at the **tail**, immediately before the latest user
   turn. Rebuilding the prompt each turn is a self-inflicted cache miss, invisible
   in every transcript. — *agreed, and now uniform: what goes at the tail is one
   line naming what changed, never the screen itself.*
   → [Prompt design for voice](../docs/src/content/docs/design/index.md#prompt-design-for-voice), and the tiers below
10. **Thinking budget is a latency setting and it is model-specific.** A level a
    model *accepts* is not one it *acts at*. Re-measure on every model change. —
    *agreed, and measured (`_gemini.py`, 2026-08-14).*

## Tools

11. **A tool that waits is a bug.** Return immediately; if the work is slow, return
    a promise and a note telling the model how to behave meanwhile. — *agreed.*
    → [Tool design for voice](../docs/src/content/docs/design/index.md#tool-design-for-voice)
12. **Tools are uninterruptible.** Barge-in cancels the *speech*, not the work.
    Half-applied work is worse than completed work. — *agreed.*
13. **Undo is a compensating call, not a rollback.** If a tool is expensive enough
    that you want to cancel it, it should have been split. — *agreed.*
14. **Typed arguments; errors from the model's point of view.** A bad call returns
    an error result the model can read and retry. **Never a dead turn.** — *agreed;
    the error half is implemented (`sdk/gemini_interactions.py`, `_failed`), the
    typed half only partly. The richer coercion — `list[Model]` arguments,
    `Field(alias=…)` honoured both ways, a returned model dumped by alias — lived
    in `_framework/coerce.py` and went out with the ADK adapter on 2026-08-24. The
    hand-rolled `_coerce` that replaced it builds a single pydantic parameter and
    passes everything else through.*
15. **Validate the shape, let the model write the words.** `ask_choice` guarantees
    2–4 covering choices; the phrasing stays the model's. — *agreed, and generalisable.*
16. **A correction preserves identity.** A quantity tweak is never a re-add; a
    variant swap is never a re-add. The row must not move on screen. — *agreed.*
    → [Misunderstanding and reversal](../docs/src/content/docs/design/index.md#misunderstanding-and-reversal)

## Parallelism

17. **Accept the burst, fan it out.** The caller says five things without waiting;
    an agent that serialises them gives back the only speed advantage voice has. — *agreed.*
    → [Parallel workstreams](../docs/src/content/docs/design/index.md#parallel-workstreams)
18. **Results surface on screen by default.** Speaking a result is the exception
    and costs a turn. — *agreed.*
19. **The one thing worth blocking on is a human decision.** `aura`'s `authenticate`
    is the sanctioned exception. — *agreed.*

## State

20. **We own the conversation; you own everything else — and there is no merge
    point.** Hold one mirror and let both writers name what they changed. The merge
    you were about to write is the bug you were about to ship. — *agreed. This
    corrects the rule it replaces, which said every turn was a merge and the merge
    was your code; that was true of a snapshot and is false of a named gesture.*
21. **The screen wins — but that is a rule about which writes are allowed, not a
    merge rule.** The agent's belief is always at least one turn old, because the
    human edits between turns. The cure is not a better reconciliation; it is the
    human's edit arriving as a fact. — *agreed, restated.*
22. **Never redo what the human already did themselves.** — *agreed.*
23. **An action carries the whole row, not a patch.** Idempotent re-render; a
    dropped message cannot leave the screen holding a half-applied diff. — *agreed.*
24. **Keep the raw heard phrase beside the resolved value.** `spoken_text` next to
    `sku`. The evidence for a mistake must survive the resolution. — *agreed.*
25. **Uncertainty is a status, not a null.** `resolving` / `multi_*` / `matched` /
    `not_found` renders as "I am not sure yet." — *agreed.*
26. **Shadow copy with a settling workflow** is the pattern for anything built
    under dictation: hold an uncommitted mirror, let background refinement move
    each element toward committed, keep the raw heard phrase beside the resolved
    value, let the human's direct edits win. — *agreed, and one of the most
    important mechanisms we have. It exists once, in one 1600-line demo, and is
    named nowhere.*

## Getting information to the model

27. **Four tiers, chosen by "when does the model need to know?"** Turn-driving user
    message · a tail note naming the change · tool over memory · tool over I/O. —
    *agreed; the table is below.*
28. **The notice names, it never values.** `ScreenState.moved` takes a verb phrase
    completing "The <actor> …" — "picked a flight for the outbound leg", never the
    flight. A note carrying values is the old snapshot dump arriving one fact at a
    time, and it goes stale in the context the same way. — *agreed. This replaces
    "grounding beats a tool for anything on screen," which was written when the
    screen was in the context; it no longer is, and tier 2 carries the notice while
    tier 3 serves the content.*
29. **An app message may never take the floor.** Enforced by `on_rtvi` not being a
    generator — nothing to yield speech into, and no turn minted. — *agreed,
    enforced by the type.*
30. **An application-triggered turn is a *user message*, not a new frame type.**
    The user uploaded a photo, pressed a button, picked from a list: still the user
    acting, only the modality differs. — *agreed;* ***partly unfinished***: *the
    text path works today — `client.sendText(...)` commits a user turn and reaches
    `on_user_message`. The frame is text-only ("richer content gets new fields"),
    so the motivating cases — a photo, a picked item — still arrive as an
    `AppEvent` and are answered on the next turn the person opens.*

## Correction and authority

31. **The agent holds no authority over anything irreversible.** No confirm tool,
    no submit without approval. A human commits with a click. — *agreed.*
32. **A click, not a spoken "yes."** A spoken yes can be misheard, can be barge-in
    noise, and can answer a question the caller only half-heard. — *agreed.*
33. **Record what was heard, never what was generated.** — *agreed.*
    → [Interruption and heard truth](../docs/src/content/docs/design/index.md#interruption-and-heard-truth)

## The framework boundary

34. **The agentic framework owns its tools; we own the voice.** Give the agent a
    voice, cut its output into speech units, tell it what was heard. Everything
    else is theirs. — *agreed, and it deleted more code than it added.*
35. **No annotation of ours where the framework takes bare callables.** `tools` is
    a property returning bound `async def` methods; the method is the declaration.
    — *agreed; `@tool` and its registry are deleted.*
36. **Anything that exists because of an upstream bug dies when the bug does.**
    Ship the bug report, not the workaround. — *agreed;* ***violated*** *by the
    "wrap the field in a model" rule, which is a google-genai execution bug we
    document instead of fix — though the documentation is now derived from a test
    of the bug (`tests/unit/test_flat_parameters.py`), which is the closest a
    workaround gets to shipping its own expiry.*
37. **Ask why the wrapper exists, then ask again one layer up.** A hack you would
    not defend out loud means the answer is higher. — *agreed; this is what
    replaced a `__deepcopy__` that returned `self`.*
38. **Trade compile-time comfort for stock compatibility, and name the loss.**
    Typed action ids and typed action results went so a page runs on an unmodified
    pipecat client. — *agreed, deliberately.*
39. **Take the standard's core, not its newest objects.** RTVI 1.0's message set is
    what stock clients implement; the objects added last month are what one version
    of one client implements. — *agreed.*
40. **Declare once.** One pydantic model is the tool's parameter *and* the
    dispatched action; the prompt describes how to use tools, never what they are.
    — *agreed;* the one admitted exception was pydantic → TypeScript, and `voqalize
    types` closed it: CI regenerates and diffs each demo's `actions.gen.ts`, so an
    action added in Python fails to compile in the browser.
41. **A tool must be able to reach the session.** Non-negotiable, and it decides
    the shape: bound methods, `self.session`, never a parameter — a parameter would
    be in the schema and the model would try to fill it. — *agreed.*
42. **Two clocks.** Generation and playout. **Speech is reconciled against heard
    truth; tool calls are not.** — *agreed, and it survived the argument that tried
    to kill it. Expanded below.*
43. **A wrapper's failure mode is silence.** Tools running on a deep-copied clone
    of the brain would have dispatched to nothing and told the model `ok`. It
    crashed only because our client holds an uncopyable lock. — *agreed, and the
    reason 172 passing tests do not close a question like this.*

## The browser

44. **We ship no client library.** The Voqalize-specific surface is the call
    initialisation and nothing else; everything after it is stock pipecat —
    client-js, client-react, voice-ui-kit. — *agreed, and carried out on
    2026-08-24: `@voqalize/client-react` is deprecated on npm with no successor.*
45. **All server communication is over stock pipecat.** RTVI `ui-event`,
    `server-message` and `ui-command`, on the data channel the transport already
    has. No second channel and no envelope of ours. — *agreed. What is ours is the
    generated TypeScript, not a channel.*
46. **A library is a promise to version something; the connection step is a
    schema.** Four facts — path, header, body, response shape — belong in a snippet
    a reader cannot skip, not in a package they must resolve. — *agreed, and the
    two things that were not connection glue found homes: the `record: true`
    refusal became a 400 from the server that starts no call, and the `Headers`
    requirement moved into `docs/client/handshake`.*
47. **Presence renders state, it never sources it.** Take pipecat's transport state
    and RTVI events; do not accumulate a state machine the app then asks "what is
    happening?" — *agreed;* ***violated in spirit***: *the component is right —
    `AmbientPresence` in `demos/shared` subscribes to nothing and takes `activity`
    and `transportState` as props — but its derivation is hand-wired into all
    twelve demos, six to eight `useRTVIClientEvent` calls apiece.*
48. **An addon earns its package by adding a capability, not by adapting an
    interface.** The avatar draws a face and aligns phonemes, so it is a package;
    the client SDK renamed things, so it was not. — *agreed.*
49. **The failure mode of a client wrapper is lag, not breakage.** Ours never
    crashed; it described a smaller pipecat than the one installed, and had to grow
    a case for every event pipecat added. — *agreed.*

---

## The six moving parts, and why there is no merge

A voice session has at least six, with different owners and different clocks:

| What | Who owns it | Changes when |
|---|---|---|
| What the caller said | **Voqalize** | the recognizer finalizes |
| What the caller actually **heard** | **Voqalize** | playout ends or is cut |
| What is on screen right now | **you** (the browser) | a click, a render, a push |
| Your knowledge base / catalog / CRM | **you** | on its own schedule |
| Which tool calls happened and what they returned | **you** | mid-turn |
| The model's own history | **you** | you write it |

Our job is to hand you our two cleanly and never to guess at yours. `heard` is the
one of the three conversation facts you cannot compute, which is why it is the
only one that travels; `speech_id` is the brain's alone, and Voqalize quotes it
back and never reads it. `session_id` is the join key across both halves.

**A snapshot needs merging because two pictures have to be reconciled. A named
gesture is applied.** `apply_event` patches the one mirror, the brain's own
dispatches patch it too, and the model reads that mirror through a tool. What
reaches the context is one line saying what moved.

`orderdesk` is the fullest worked example and the canonical answer: two writers on
one cart (the pharmacist's phone and the voice call), two typed bridges generated
from the same module, `LineItemView.status` walking `resolving → multi_family |
multi_variant → matched | not_found` with `source: "agent" | "manual"` recording
who put each row there, and `pending()` reading the mirror alone so the agent says
"narrowed to 6 — ask the next question" rather than re-asking what a thumb already
answered. **Echo suppression died by construction**: a brain's own dispatch is not
a gesture, so it produces no event and there is nothing to suppress. The same
shape appears smaller in `servicing` (`get_advisor_context`), `aura`
(`get_screen_context`) and `forge`, whose `ScreenState.happened` carries a test
run finishing — the browser's computation rather than anybody's decision.

## The four tiers

Ask, of every change in the environment: **when does the model need to know?**

| Answer | Tier | Mechanism | Cost |
|---|---|---|---|
| **Right now** — it must produce a turn | Send it as a **user message** | `sendUserMessage` → `UserMessage` frame → `on_user_message` | a whole turn, and the floor |
| **By the next turn** | Append one line at the **tail** naming what changed | `ScreenState.moved` / `happened` | tokens only — cache-safe |
| **When the model asks** | The mirror those events keep true, behind a tool | tool reading the brain's own state | one model round trip |
| **When the model asks, and it can wait** | Don't store it — fetch on demand | tool doing I/O | a round trip **plus** the fetch |

**Nothing in this table ever writes to the system prompt.** That is tier zero, and
tier zero is immutable for the whole session (rule 9).

- **Tiers 2 and 3 are one mechanism split by cost.** Tier 2 is a sentence the model
  cannot fail to see and cannot mistake for data; tier 3 is the tool it points at.
  The notice is unforgettable and nearly free; the content is exact, costs a round
  trip, and is fetched only when it matters. Neither does the other's job.
- **Placement is the whole design.** The note goes in as a user turn *just before*
  the latest user turn, so the entire prefix stays byte-identical and stays cached.
- **Tier 1 is the dangerous one, and the wire makes you say so.** To get a turn you
  must send a *user message* — the application declaring "this is a stimulus, the
  same kind a spoken sentence is." Everything else is mute by construction, so the
  default for an environment change is tier 2 and tier 1 is never a side effect.
- **`None` appends nothing** — no header, no empty block. An event that changes
  nothing the model would act on folds into the mirror in silence.
- **`ScreenState.version` makes the read enforceable.** A tool aimed at a screen
  the model has not re-read since it moved refuses, with a retriable reason. Prompt
  discipline is a request; this is a rule.
- **Measured, 2026-09.** A 123-second production call put twenty-one full carts in
  front of one model — about 4,700 tokens, each labelled authoritative, none dated.
  A named change is one line. There is no snapshot size at which the snapshot wins.

Tier choice is the concrete form of the 80/10/10 split in
[Prompt design for voice](../docs/src/content/docs/design/index.md#prompt-design-for-voice):
tiers 1–2 are the 80%, tier 3 is the 10%, tier 4 is the 10% that must be designed
with feedback.

## The two clocks

The strongest thing to survive the framework-boundary argument is the thing that
did **not** get simpler. Handing the tool loop to automatic function calling feels
like it should retire heard-truth reconciliation: the framework runs the whole turn
and gives us a complete record, so surely the record is the history. It is not.

- **The generation clock** — AFC streaming, tools running, hops advancing.
- **The playout clock** — what the caller's ear is receiving, seconds behind it.

A barge-in is an event on the *playout* clock. AFC's record says what was
**generated**, never what was **heard**; the model can be on its third hop while
the caller is still hearing a sentence from the first.

> **Speech is reconciled against heard truth. Tool calls are not.**

Tool calls stand because they happened. Speech is rewritten to the delivered
prefix, and the reconciliation is applied at the start of the *next* turn. It is
the general pattern rather than a Gemini detail, and it lives entirely inside the
SDK without touching the wire or the runtime. `_drop_unanswered` removes a
`function_call` a barge-in left without its response, because Gemini will not
accept that conversation next turn — while the tool that ran beside it stays run,
because it did.

## The test, before you wrap anything

1. **Why do we need this wrapper?** Then ask again, one layer up. Two answers, or
   it does not ship.
2. **Does it exist because of a bug upstream?** Then it dies when the bug does.
   File the bug; do not ship the workaround as a feature.
3. **Would a developer who already knows this framework know this?** If not, it
   costs them attention and buys them nothing in any other project.
4. **Does it have exactly one caller?** Then it belongs to that caller, not to the
   SDK.
5. **What do we lose by going stock?** Name it. Take the loss if the compatibility
   is worth more — and say which one you chose.
6. **Would you defend this out loud?** If it reads as a hack, the answer is one
   level higher: what does the vendor recommend, and why is this not biting
   everyone else?

What survived that test on the Python side is `_ready` (`gemini.py:423`), which
enforces two things at the seam rather than documenting them: **`async def` is
required**, because AFC runs a sync tool on a worker thread where the contextvars
carrying `self.turn` are unset; and **what google-genai receives is not a bound
method**, because it deep-copies the config on entry and on every hop, and
`copy.deepcopy` of a bound method copies `__self__`. ADK draws the same line in
the same place. Had we not, tools would have run on a *clone* of the brain:
`self.session.dispatch` reaching nothing, the context written to an object no one
reads, the model told `ok`, and not one thing on the wire to say so. It crashed
instead of going quiet only because our brain holds a `genai.Client` whose lock
cannot be copied. That was luck.

---

## What we have not settled

- Whether the SDK should own an **on-screen task list** (four demos hand-rolled one).
- Whether **withheld authority should be declarable** rather than achieved by not
  writing the tool. Today it is invisible to a reviewer.
- Whether the framework boundary **generalises past one vendor**. Everything is
  exercised by every demo now, but through `GeminiBrain` and
  `GeminiInteractionsBrain` — two clients of the same google-genai SDK, so it is
  the cheap half of the test. The ADK path that would have been the second vendor
  is deleted. Nothing here should be stated as a general shape until something that
  is not google-genai has run against it.
- Whether `_ready` is **residue or an unadmitted wrapper**. Every line of it is a
  fact about google-genai's internals, and it will rot on somebody else's release
  schedule. The `interactions` client passing was evidence, not proof.
- **Who owns presence** — a hook in `demos/shared` beside the component, or the avatar
  addon, which already derives `SPEAKING`, `LISTENING`, `MUTED`, `OFFLINE` and
  `DEGRADED` from the `PipecatClient` with no backend involvement at all. Two
  answers to one problem, in two repositories, and we have not chosen.
- Whether there is a **fifth tier** — facts the screen may show and the model may
  not see. (Prices the agent must not read out are exactly this. They are out of
  the context now, but the read tool still serves them.)
- Whether the **shadow copy** gets a base class in the SDK. The transport question
  is settled — `AppEvent` / `AppEvents` ship in `sdk/python`, the brain owns the
  mirror, and `ScreenState` stays in `demos/voqalize_demos/screen.py` because the
  read tool's name and the actor's word are things only a brain can supply. Whether
  the discipline it encodes deserves more than a demo helper is open.

## Known holes in the evidence

- No demo asserts history-equals-`heard`.
- No demo exercises `status="timeout"`.
- **A failed tool never reaches the caller.** google-genai hands the model
  `{'error': …}` and the model will cheerfully tell the caller it did the thing;
  our side can only log a warning. There is no path from a tool failure to
  something the caller hears.
- **Neither adapter parses a flat argument.** google-genai checks flat arguments
  with `isinstance` and coerces nothing, so a bare `Literal` raises and a bare
  `Enum`/`date`/`Decimal`/`UUID` is rejected — both into an `{'error': …}` the
  model papers over. See rule 36: this is the workaround we document instead of
  fixing.
- No fan-out example has a failing branch.
- No example of correcting something already **committed**.
- No example of a **server-owned** third state in the merge — every demo's other
  state is the screen.
- `_gemini.py:59` cites `_TurnClock`, which does not exist in this repo.
