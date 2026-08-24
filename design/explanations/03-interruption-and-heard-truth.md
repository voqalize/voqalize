# 3. Interruption and heard truth

> **The surprise.** The caller did not hear what your agent said. They heard the
> part that finished playing before they cut in. If you append what your agent
> *generated* to the conversation history, you have written down a version of the
> call that never happened — and the model will reason from it for the rest of the
> session.

## Belief

- Interruption is not an edge case in voice. It is the majority behaviour on any
  turn longer than a sentence, and it is the caller working correctly: they got
  what they needed and moved on.
- The corruption from recording generated-not-heard text is **silent, cumulative,
  and invisible in every metric.** No transcript, no error, no latency number, no
  eval sees it. The call just gets subtly wronger — the agent thanks you for a
  detail you never received, or re-offers something it believes it already
  covered.
- Therefore the framework must *hand you* the heard prefix, and the SDK must make
  recording it the obvious thing to do. Asking every customer to reconstruct it
  from playout timing is asking them to reimplement the hardest part of the
  runtime.

## Facts — the mechanism

- **`Finalize(speech_id, heard, interrupted)`** arrives after playout, once per
  unit. `heard` is **the delivered prefix** — what actually reached the caller's
  ear, not what you yielded. `interrupted` says whether the caller cut in.
- `on_finalize(session, fin)` is the callback. Its docstring is blunt about the
  stakes: "Record `fin.heard`… a failure that is silent, cumulative, and invisible
  in every metric."
- **Every unit is awaiting a finalize, silent ones included** (commit `22b1fce`).
  A turn that yields no speech still resolves — so the bookkeeping has no hole
  where a silent turn used to be.
- **Barge-in mechanics.** Voqalize sends `Interruption(through_turn)`; the SDK
  records `max(watermark, through_turn)` and runs `_cancel_turns()`. Nothing goes
  back. The watermark is what tells a chunk that was in flight from a chunk
  produced after the cut — a chunk names its turn, and a turn at or below the
  watermark is dead.
- **The generator is closed, not abandoned.** `_drive()` calls `aclose()` so
  `finally` blocks run — your cleanup, your span exit, your "release the lock" all
  execute on an interrupted turn exactly as on a completed one.
- **An open unit is closed on the wire.** If the caller cuts in between
  `SpeechStart` and `SpeechEnd`, the SDK emits the close. The four obligations in
  `ProtocolError` lead with **balanced brackets** — and this is the framework
  keeping that promise on your behalf when you cannot.
- **Turn ids fence turns.** Work belonging to a cancelled turn cannot leak speech
  into the turn that replaced it: the replacement turn is a higher number, and a
  watermark never rises above it.
- Interruption does **not** cancel dispatched actions or in-flight tool work. See
  [6](06-tool-design.md) — this is deliberate, not an oversight.

## Proof

- The conformance harness "models playout/heard-truth finalization the way real
  Voqalize does" (`sdk/python/src/voqalize/conformance/__init__.py`). Heard-truth is
  not documentation about a behaviour; it is an assertion in the suite a brain
  must pass to be called wire-compatible.
- `VoqalizeDriver` records `SpeechObs` / `TurnObs` per unit, so a test can
  assert on the *heard* text rather than the generated text.
- `interrupted` as a rate is the cheapest quality signal we have — see
  [2](02-the-turn-budget.md).

## The reader's obligation, stated plainly

Whatever you persist as the assistant turn — Gemini `Content`, ADK event,
your own log — must be built from `fin.heard`, not from the string you yielded.
Two places this bites:

1. **History for the next model call.** The model plans its next turn against what
   the caller knows. Feed it the generated text and it plans against fiction.
2. **Anything downstream of the transcript** — summaries, QA scoring, handoff
   notes, "what did we tell the customer" audits. All of them inherit the lie.

## Status

**This page's mechanism is being ratified in parallel** — a separate line of work
is settling the exact heard-truth contract. Treat every Fact above as *current
behaviour to be confirmed*, and do not freeze prose here until that lands. The
Belief section is not in question; the mechanics might move.

## Gap

- **We have no page saying this, and it is the single most expensive thing a
  customer can get wrong.** It is invisible until someone reads a transcript
  beside a recording.
- **Open:** should the SDK make the wrong thing *impossible* rather than
  documented — e.g. a history helper that only accepts a `Finalize`? Today
  correctness is opt-in, and opt-in correctness on an invisible failure is a bet
  we lose at scale.
- **Open:** partial-word truncation. `heard` is a prefix of text, but playout cut
  mid-word. Is the prefix character-exact, or does it round? A page cannot claim
  precision we have not verified.
- **Gap:** no demo asserts on `heard` today. The e2e suite exercises interruption
  but the strongest available property — history equals heard — is unchecked.
