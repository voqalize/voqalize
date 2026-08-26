# Practices — what we agree on

Working notes, not a document. Extracted from the nine outlines so the rules can
be argued with directly instead of being re-derived inside each page. Each line is
either **agreed** (we would defend it today), **contested** (we disagree or the
evidence is thin), or **violated** (we believe it and our own code breaks it).

The wording here is deliberately blunt. `design/voice.md` governs the pages these
become; it does not govern this file.

---

## Output

1. **Speak the pointer, render the payload.** Voice carries intent,
   acknowledgement, and the one number that matters. The screen carries the
   record. — *agreed, and every demo enforces it by hand.* → [1](01-voice-points-screen-holds.md)
2. **Never recite what is on screen.** Lists, prices, ids, SKUs, units: gesture at
   them. — *agreed; eleven prompts say it eleven ways.*
3. **Never narrate your own actions.** The action already painted the screen. — *agreed.*
4. **The default reply is one short line.** Anything longer needs a reason. — *agreed.*
5. **Batch your questions.** Two questions in one breath beat two turns. — *agreed.*

## Latency

6. **Start fast, don't be short.** The interval you own is callback entry → first
   `Chunk`. Nothing else in the product is yours. — *agreed.* → [2](02-the-turn-budget.md)
7. **Never leave silence around a tool call.** Speak a tiny line first, then call. — *agreed.*
8. **`greet` contains no model call.** Fixed line, or a template over `session.init`. — *agreed, enforced by the return type.*
9. **The system prompt is the cache prefix. Write it once per session; never edit it.**
   Volatile context goes at the **tail**, immediately before the latest user turn.
   Rebuilding the prompt each turn is a self-inflicted cache miss, invisible in
   every transcript. — ***violated*** *by `GoogleADKBrain.grounding()`, which appends
   to the system instruction on every model call.* → [5](05-prompt-design.md), [8](08-getting-information-to-the-model.md)
10. **Thinking budget is a latency setting and it is model-specific.** A level a
    model *accepts* is not one it *acts at*. Re-measure on every model change. — *agreed, and measured (`_gemini.py`, 2026-08-14).*

## Tools

11. **A tool that waits is a bug.** Return immediately; if the work is slow, return
    a promise and a note telling the model how to behave meanwhile. — *agreed.* → [6](06-tool-design.md)
12. **Tools are uninterruptible.** Barge-in cancels the *speech*, not the work.
    Half-applied work is worse than completed work.  — *agreed.*
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
    variant swap is never a re-add. The row must not move on screen. — *agreed.* → [9](09-misunderstanding-and-reversal.md)

## Parallelism

17. **Accept the burst, fan it out.** The caller says five things without waiting;
    an agent that serialises them gives back the only speed advantage voice has. — *agreed.* → [4](04-parallel-workstreams.md)
18. **Results surface on screen by default.** Speaking a result is the exception
    and costs a turn. — *agreed.*
19. **The one thing worth blocking on is a human decision.** `aura`'s `authenticate`
    is the sanctioned exception. — *agreed.*

## State

20. **We own the conversation; you own everything else. Every turn is a merge, and
    the merge is your code.** — *agreed.* → [7](07-who-owns-which-state.md)
21. **The screen wins.** The agent's memory of what it did is a hypothesis about
    the screen; the snapshot is the fact. The mirror is a first-beat fallback only. — *agreed.*
22. **Never redo what the human already did themselves.** — *agreed.*
23. **Send whole rows, not patches.** Idempotent re-render; a dropped message
    cannot leave a half-applied diff. — *agreed.*
24. **Keep the raw heard phrase beside the resolved value.** `spoken_text` next to
    `sku`. The evidence for a mistake must survive the resolution. — *agreed.*
25. **Uncertainty is a status, not a null.** `resolving` / `multi_*` / `matched` /
    `not_found` renders as "I am not sure yet." — *agreed.*
26. **Shadow copy with a settling workflow** is the pattern for anything built
    under dictation: hold an uncommitted mirror, let background refinement move
    each element toward committed, keep the raw heard phrase beside the resolved
    value, let the human's direct edits win. — *agreed, and one of the most
    important mechanisms we have.* **Open: who owns it** — the brain writes it
    today (`orderdesk`), and whether the SDK should offer a base for it is a
    separate question from whether it is right. Document the mechanism either way.
    → [7](07-who-owns-which-state.md)

## Getting information to the model

27. **Four tiers, chosen by "when does the model need to know?"** Turn-driving user
    message · tail grounding · tool over memory · tool over I/O. — *agreed.* → [8](08-getting-information-to-the-model.md)
28. **Grounding beats a tool for anything on screen.** A tool is only as fresh as
    the model's decision to call it. — *agreed; the argument is already written in
    the ADK docstring.*
29. **An app message may never take the floor.** Enforced by `on_rtvi` returning
    `None` — nothing to yield speech into, and no turn minted. — *agreed, enforced
    by the type.*
30. **An application-triggered turn is a *user message*, not a new frame type.**
    The user uploaded a photo, pressed a button, picked from a list: still the user
    acting, only the modality differs. `sendUserMessage` versus `sendAppMessage` is
    the application declaring which. — *agreed;* ***unfinished***: *wire frame exists
    (`UserMessage`, text-only, "richer content gets new fields"), `on_user_message`
    receives it, browser half not plumbed — the browser has only pipecat's
    `sendClientMessage`, and since `sdk/react` was deleted there is no wrapper of
    ours to put `sendUserMessage` on.*

## The framework boundary

34. **The agentic framework owns its tools; we own the voice.** Give the agent a
    voice, cut its output into speech units, tell it what was heard. Everything
    else is theirs. — *agreed, and it deleted more code than it added.* → [10](10-the-framework-boundary.md)
35. **No annotation of ours where the framework takes bare callables.** `tools` is
    a property returning bound `async def` methods; the method is the declaration.
    — *agreed; `@tool` and its registry are deleted.*
36. **Anything that exists because of an upstream bug dies when the bug does.**
    Ship the bug report, not the workaround. — *agreed;* ***violated*** *by the
    "wrap the field in a model" rule, which is a google-genai execution bug we
    document instead of fix — though the documentation is now derived from a test
    of the bug, which is the closest a workaround gets to shipping its own
    expiry.*
37. **Ask why the wrapper exists, then ask again one layer up.** A hack you would
    not defend out loud means the answer is higher: what does the vendor recommend,
    and why is this not biting everyone else? — *agreed; this is what replaced a
    `__deepcopy__` that returned `self`.*
38. **Trade compile-time comfort for stock compatibility, and name the loss.**
    Typed action ids and typed action results went so a page runs on an unmodified
    pipecat client. — *agreed, deliberately.*
39. **Take the standard's core, not its newest objects.** RTVI 1.0's message set,
    not last month's additions. — *agreed.*
40. **Declared once.** One pydantic model is the tool's parameter *and* the
    dispatched action; the prompt describes how to use tools, never what they are.
    — *agreed;* the one admitted exception is pydantic → TypeScript, which carries
    a comment saying both halves move together.
41. **A tool must be able to reach the session.** Non-negotiable, and it decides
    the shape: bound methods, `self.session`, never a parameter — a parameter would
    be in the schema and the model would try to fill it. — *agreed.*
42. **Two clocks.** Generation and playout. **Speech is reconciled against heard
    truth; tool calls are not.** AFC's record says what was generated, never what
    was heard, so handing the tool loop to the framework retires none of the
    reconciliation. — *agreed, and it survived the argument that tried to kill it.*
    → [3](03-interruption-and-heard-truth.md)
43. **A wrapper's failure mode is silence.** Tools running on a deep-copied clone
    of the brain would have dispatched to nothing and told the model `ok`. It
    crashed only because our client holds an uncopyable lock. — *agreed, and the
    reason 172 passing tests do not close a question like this.*

## The browser

44. **We ship no client library.** The Voqalize-specific surface is the call
    initialisation and nothing else; everything after it is stock pipecat —
    client-js, client-react, voice-ui-kit. — *agreed, and the package is already
    down to four facts.* → [11](11-the-browser-is-pipecats.md)
45. **All server communication is over stock pipecat.** RTVI `client-message`,
    `server-message` and `ui-command`, on the data channel the transport already
    has. No second channel and no envelope of ours. — *agreed, and sugar has no
    Voqalize channel in it.*
46. **A library is a promise to version something; the connection step is a
    schema.** Four facts — path, header, body, response shape — belong in a
    snippet a reader cannot skip, not in a package they must resolve. — *agreed;*
    ***unfinished***: *two things in the package are not connection glue (the real
    `Headers` requirement, the silent `record: true` refusal) and need somewhere
    else to live first.*
47. **Presence renders state, it never sources it.** Take pipecat's transport
    state and RTVI events; do not accumulate a state machine the app then asks
    "what is happening?" — *agreed;* ***violated in spirit***: *the component is
    right, the derivation is copied into eleven pages.*
48. **An addon earns its package by adding a capability, not by adapting an
    interface.** The avatar draws a face and aligns phonemes, so it is a package;
    the client SDK renamed things, so it was not. — *agreed.*
49. **The failure mode of a client wrapper is lag, not breakage.** Ours never
    crashed; it described a smaller pipecat than the one installed, and had to
    grow a case for every event pipecat added. — *agreed.*

## Correction and authority

31. **The agent holds no authority over anything irreversible.** No confirm tool,
    no submit without approval. A human commits with a click. — *agreed.*
32. **A click, not a spoken "yes."** A spoken yes can be misheard, can be barge-in
    noise, and can answer a question the caller only half-heard. — *agreed.*
33. **Record what was heard, never what was generated.** — *agreed in principle;
    mechanism being ratified in parallel.* → [3](03-interruption-and-heard-truth.md)

---

## What we have not settled

- Whether the SDK should own an **on-screen task list** (four demos hand-rolled one).
- **Who owns the shadow copy** — brain or SDK. The mechanism is settled (#26); the
  ownership is not. *(Current position: document it as a mechanism and let brains
  build it, because a helper that guesses the merge rule is worse than none. Worth
  revisiting once a second demo needs one.)*
- Whether **withheld authority should be declarable** rather than achieved by not
  writing the tool. Today it is invisible to a reviewer.
- **Conflict semantics** when a `state_sync` and an action cross on the wire.
  Convention today: diff by id, last write wins per row. Unstated, untested.
- Whether the framework boundary **generalises past one vendor**. Everything in
  [10](10-the-framework-boundary.md) is exercised by all eleven demos now, but
  through `GeminiBrain` and `GeminiInteractionsBrain` — two clients of the same
  google-genai SDK. The ADK path that would have been the second vendor is deleted.
- ~~Whether `@voqalize/client-react` is **deleted or kept at four facts**.~~
  **Settled 2026-08-24, the way the position said.** The refusal is a 400 from
  the server (`recording_not_permitted`, and it starts no call), the `Headers`
  line is in `docs/client/handshake`, and `sessions.connect` answers in the shape
  pipecat's transport takes so there is nothing left to lift out of a session
  record. The package is deprecated on npm and takes no successor.
- **Who owns presence** — a hook in `demo-kit` beside the component, or the avatar
  addon, which already derives the same states from the `PipecatClient` by itself.
  Two answers to one problem, in two repositories.
- Whether `_ready` is **residue or an unadmitted wrapper**. A second client from
  the same vendor (the `interactions` API, stateless + streaming + AFC) is the
  cheapest test we have of which.
- Whether there is a **fifth tier** — facts the screen may show and the model may
  not see. (Prices the agent must not read out are exactly this, and today they
  *are* in the grounding.)
- **When a grounding snapshot gets big enough that a tool wins.** No measurement,
  no guidance.

## Known holes in the evidence

- No demo asserts history-equals-`heard`.
- No demo exercises `status="timeout"`.
- **Ten demos still declare `@voqalize/client-react` at `^0.1.0`**, and the
  package was deprecated and its source deleted on 2026-08-24. They keep building:
  deprecating does not unpublish, so `^0.1.0` still resolves 0.1.1 from the
  registry — which is also why the overlay in `build.mjs` can go. What that
  0.1.x surface carries and nothing else now does is **presence**
  (`AmbientPresence`, `useVoqalSession`, `useUiCommand`); the last two are thin
  over pipecat, the first is not, and it needs a home before those ten pages can
  be ported. Sugar and legal are ported already and are the shape to copy.
- **A failed tool never reaches the caller.** google-genai hands the model
  `{'error': …}` and the model says it did the thing; our side can only log.
- No fan-out example has a failing branch.
- No example of correcting something already **committed**.
- No example of a **server-owned** third state in the merge — every demo's other
  state is the screen.
- **Every design here assumes a screen — and that is a scope boundary, not an
  oversight.** There is no telephony anywhere in the product: the runtime is
  WebRTC, all eleven demos are browsers, and nothing in the repo mentions PSTN or
  SIP. So "voice alongside a visual surface" is what we build, and half these
  practices are *defined* by it (#1, #2, #18, #21, #31). State it deliberately at
  the top of the set rather than leaving a reader to discover it on page nine.
- `_gemini.py:59` cites `_TurnClock`, which does not exist in this repo.
