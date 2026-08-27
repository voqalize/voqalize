# 2. The turn budget

> **The surprise.** Of everything between the caller finishing a sentence and
> hearing a syllable, exactly one interval belongs to you — entering the callback
> to yielding your first `Chunk` — and it is the only latency in the product your
> code controls. A fast turn is not a fast turn. It is a turn that *starts* fast.

## Belief

- The window has no idle time to reclaim later. If the caller waits, they waited.
- After the first chunk you have bought the caller's attention, and the rest of
  your generation runs under it rather than in front of it.
- **Everything else in these nine pages is downstream of this.** A chat agent that
  takes four seconds looks like it is working. A voice agent that takes four
  seconds sounds like it hung up.

## Facts

- The split: endpointing + recognizer finalization (ours) → **your callback to
  your first `Chunk`** (yours) → first audio from the speech tier + playout
  (ours).
- The measurable name for your half: **time to first chunk**.
- `Chunk`s stream. "Stream them as you produce them" (`sdk/events.py`) — a
  streamed sentence begins being spoken before it is finished being generated.
- **`greet` is not a turn.** It returns `str | None`, not a generator. `async` so
  you can look up a name, "not so you can generate the sentence: this is the one
  moment where the caller is sitting on a connected session hearing nothing, and a
  round-trip here is the single most expensive latency in the product"
  (`Brain.greet` docstring). `None` opens silently — correct for an ambient agent.
- The four obligations in `ProtocolError` include "**you don't block**. A callback
  that stalls holds the floor open and the caller hears nothing," and "**`greet`
  is fast.**"

## Proof

- **The hybrid greeting.** `hello_for(LANGUAGE)` speaks a fixed one-word hello
  *instantly*, before the model has produced a token; `_CONTINUE_AFTER_OPENER` is
  appended to the greeting prompt so the model continues rather than greeting
  twice (`demos/voqalize_demos/_gemini.py`). Every demo with a generated opener
  uses it. `orderdesk` additionally carries `_FALLBACK_OPENER` "spoken if the
  generated opener fails (no key, model error) — the call still starts."
- **Thinking budget is a latency setting, and it is model-specific.**
  `VOICE_THINKING = ThinkingConfig(thinking_level=MINIMAL)` — "the least thinking
  this model allows, for lowest voice latency: on a voice turn a reasoning budget
  is spent in silence the caller sits through, and the thought parts are never
  spoken, so the cost has no audible half at all."
  The comment above it is the strongest measured artifact we have, verified
  against the live API on 2026-08-14:
  - the knob moved (`thinking_budget=0` rejected by 3.5+ with a `400` naming no field);
  - the floor moved (`gemini-3.7-flash` refuses MINIMAL; its floor LOW still spends
    ~275 thought tokens and "its turns ran ~2x this one's");
  - **a level a model accepts is not one it acts at** — `gemini-3.5-flash-lite`
    takes MINIMAL then calls `open_itinerary` on only 9 of 15 identical turns.
- **Prompt-level pacing rules, in production.** `orderdesk`: "Start every reply
  with a tiny phrase so audio begins instantly." And: "Say a tiny line before or
  while calling a tool — never leave silence."
- **`aura`**: "Speak a short line first, then call the tool."

## Where your half actually goes

1. Time to the model's **first token**, not its last. An `await`-to-completion
   before speaking converts a streaming system into a batch one.
2. **Tool round trips.** In-process is a function call; over HTTP it is a network
   round trip on every turn that uses it. See [6](06-tool-design.md).
3. **Retrieval** as a serial hop, unless started before it is needed. See
   [4](04-parallel-workstreams.md).
4. **Work that was serial for no reason.** Three `await`s cost the sum; one
   `asyncio.gather` costs the slowest.
5. **Prompt size**, which is the subject of [5](05-prompt-design.md).
6. **A cache miss you caused yourself.** The system prompt is the cache prefix. Set
   it once per session and it is matched turn after turn; edit it — even to append
   one fresh line of context — and every turn re-reads the whole thing. This is the
   one item on this list that is free to get right and silently expensive to get
   wrong, because nothing in a transcript shows it. Volatile context belongs at the
   **tail**, just before the latest user turn ([8](08-getting-information-to-the-model.md)).

## Instruments the reader already has

- `on_finalize` fires once per unit after playout, carrying `heard` and
  `interrupted`. Stamp a monotonic clock at callback entry, close it at the first
  `Chunk`.
- **`interrupted` as a rate** is the cheapest quality proxy in the product:
  callers talk over an agent that is too slow, too long, or wrong.
- `get_session_events` over the MCP server returns our half of the same call,
  joined on the same `session_id`.

## Gap — and it is the constraint on this page

**We have no published latency figure and may not invent one.** The track rule is
"no latency figure is published before it is measured with its conditions." So
this page names *moments* — before the first word, on every turn that uses it —
and hands over instruments. Numbers land here when the harness exists.

- `voqalize_demos/_gemini.py:59` refers to reading "`_TurnClock` think= numbers on
  a real deployed call". **`_TurnClock` does not exist in this repo.** Either it
  is in the platform, or the comment is stale. Resolve before citing it.
- **`GoogleADKBrain.grounding()` currently rewrites the system instruction every
  call**, which is item 6 above, committed. Fix before this page tells anyone not
  to do it.
- **Open:** is a latency page with no numbers credible? My position: more credible
  than one with unmeasured numbers, and the page should say why there are none.
