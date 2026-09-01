---
title: Correcting history in your framework
description: For anyone writing a brain against a framework we ship no adapter for. Your framework owns history; two things change it, and both are corrected at one point before each model call.
---

This page is for the reader porting a framework we ship no adapter for — the one
writing the integration rather than using one. A brain built on a shipped adapter
gets all of this already and can skip the page.

Your agent framework already keeps a conversation history, and it keeps it
correctly for chat. A voice call breaks it in exactly two places:

- **What the caller heard is not what your model generated.** They interrupted.
  Voqalize reports the delivered prefix per speech unit, after playout, long
  after the turn that produced it returned.
- **Your app knows things the conversation does not** — the screen the caller is
  looking at, a button they pressed. That has to reach the model without landing
  between a tool call and its result.

Everything else your framework does stays. Do not replace its history; correct
it, at one point, deterministically.

**What ships today, and what does not.** Everything below works when your
framework mints the ids — you are keying corrections to an ADK `Event.id` or a
Responses `msg_…`, and those are yours to read. The SDK's own `speech_id` is
minted inside `Brain._drive` and is first readable on the `Finalize`, so a brain
that brackets speech itself cannot yet name a unit at the moment it opens one;
[Transcripts](/build/brain/transcripts/) has the ordering rule that works in
`0.2.0` in the meantime. Returning the id at `SpeechStart` is the change that
closes that gap and it has not shipped as of 2026-09-01.

## The shape

Keep an **append-only list of immutable events**, and **fold it into history
immediately before each model call**.

```python
# One event per thing that happened. The payload is your framework's own
# object — a types.Content, an ADK Event, a Responses item. Never ours.
Event(kind="generated",  speech_id=..., unit=..., payload=...)   # the model spoke
Event(kind="correction", speech_id=..., unit=..., heard="...")   # what landed
Event(kind="tool",       payload=...)                            # a call and its result
Event(kind="context",    payload=...)                            # your app pushed
Event(kind="compaction", payload=...)                            # ignore what precedes me
```

Nothing is ever edited. A correction is a **second event naming the same speech
unit**, so the record holds both what the model generated and what the caller
heard, and the fold decides which the model sees.

This shape is a ledger, and that word is worth exactly one sentence: it is a
pattern you implement, not a class you import. Nothing in the SDK is named this,
no symbol exposes it, and a brain running on a shipped adapter never meets it.
Each integration builds its own out of whatever its framework already has —
which, in two of the three cases below, is most of it.

Three properties earn their keep:

- **Appended at completion, never during streaming.** The accumulator you fill
  chunk by chunk is transient. The event is written when the unit finishes —
  **including when a barge-in cuts it mid-stream**, from the `finally`, carrying
  the partial text. That is the common case, not an edge.
- **Order of arrival does not matter.** The fold runs before the model call, by
  which time both halves are present. You never wait for a correction.
- **Idempotent.** In some frameworks the fold runs at two points (below). Folding
  already-folded history must be a no-op.

## What the fold does

| Rule | |
|---|---|
| **Correct text by `speech_id`** | The corrections for one generated event, in unit order, are always full prefixes, then one truncated, then empties — a barge-in cuts at one point. The event's text becomes their **concatenation**. |
| **Touch nothing else** | Tool calls, tool results and reasoning blocks pass through verbatim. |
| **Mark it complete** | A framework flag meaning "this turn did not finish" must be cleared on a corrected event. A barge-in is not an error, and some frameworks delete unfinished turns outright. |
| **Drop an unmatched correction** | A correction naming no generated event is speech you chose not to record. |
| **Start at the newest compaction** | Everything before it is represented by its payload. |

`heard` is a verbatim prefix of what you generated, so a fold never invents text
— it only ever shortens.

There is no rule here for a tool call whose result never arrived, because that
state should not be reachable. See below.

## A tool call and its result are one event

**A tool call in a voice brain does not block**, and that constraint does the
work. Two shapes, and there is no third:

- **Synchronous** — it reads state your process already holds and returns. There
  is no window for anything to arrive between the call and the result, because
  there is no wait.
- **Asynchronous** — it starts work and returns *now*, telling the model the
  result is pending and running in the background. The eventual answer arrives as
  its own later event, on its own turn.

Under either shape the call and its result are produced together, so **append
them together, as one event.** Not a call event and then a result event: one
append, at the moment the pair exists. A barge-in that lands before the pair is
complete writes neither, and a fold can then never see a call without its
result.

That is the reason the rule table above has no repair step. A repair is what you
need when the invariant is not enforced, and the shape of the invariant is that
tool calls never occupy time a barge-in can land inside.

Frameworks defend this unevenly, which is what you would expect from libraries
written for chat. `openai-agents` 0.22.0 strips an orphaned call **and** the
reasoning item preceding it, because the API rejects a reasoning item not
followed by its associated item. `pi` 0.84.4 keeps the call and injects a
synthetic failed result, explicitly to preserve the reasoning chain. Google ADK
2.8.0 drops an orphaned *response* and passes an orphaned *call* straight to the
model. Three libraries, three answers — which is itself the argument for making
the state unreachable rather than picking one.

The shipped `GeminiBrain` carries a `_drop_unanswered` step for exactly this
state, because automatic function calling delivers a hop's responses on the
first chunk of the next hop and a cut can land between them
(`sdk/python/src/voqalize/sdk/gemini.py`). Whether that becomes an atomic
append instead is open work as of 2026-09-01, not a shipped guarantee.

## What your framework has to give you

Two things, and they are less than most frameworks provide:

1. **Anywhere to hang your own id on a generated unit.** A custom message type,
   a metadata dict, a side table. The framework does not have to offer one.
2. **One deterministic point, before each model call, where you can substitute
   the whole history.**

That is the whole substrate. Immutability, append-only, corrections-as-events
and compaction anchors are your discipline, not the framework's affordance — a
framework that hands you a bare list of provider messages satisfies this at both
points, because you build the list yourself.

Then check the third thing, which is not a requirement but a hazard:

3. **What runs between your fold and the wire.** Every framework normalizes
   history after you hand it over, and the pass is usually undocumented. Probe
   it before you trust the fold. Three real examples, all found by running the
   code rather than reading about it:

   - `pi` 0.84.4 (`@earendil-works/pi-ai`) **deletes any assistant turn whose
     `stopReason` is `aborted`** — exactly what a barge-in produces. Its own
     README documents the opposite behaviour.
   - Google ADK 2.8.0's `_rearrange_events_for_latest_function_response`
     discards **everything between a tool call and a response that arrives after
     further conversation** — agent turns and caller turns alike.
   - `openai-agents` 0.22.0 runs `drop_orphan_function_calls` **before** your
     filter, not after, so an item your fold removes can leave a dangling
     reasoning item that nothing cleans up and the API rejects.

   An interrupted turn is disposable in a coding agent and load-bearing in a
   voice agent. Framework defaults are written by the former.

**Server-held history cannot be corrected.** If your framework chains on a
stored conversation id — `previous_response_id`, a Conversations id, a live
bidi connection — the prior assistant turn is never re-sent, so there is nothing
to rewrite. Send the full input on every call and turn storage off. The shipped
`GeminiInteractionsBrain` sends `store=False` and no `previous_interaction_id`
for this reason (`sdk/python/src/voqalize/sdk/gemini_interactions.py`).

## Google ADK

Verified against `google-adk` 2.8.0.

**Do not build a second record.** `Session.events` is one already — append-only,
with a stable `Event.id` per model step, durably persisted. What is yours is the
metadata convention and the fold.

**The id.** `Event.id` is minted before streaming and is stable across it: every
`partial=True` fragment and the final `partial=False` event share it
(`flows/llm_flows/base_llm_flow.py`, the re-mint after each complete event). So
your code learns the id on the first chunk it forwards to speech, and that id is
the one that lands in the session. `EventActions` forbids extra fields; hang your
keys on `Event.custom_metadata`, which survives persistence.

**One `Event.id` covers one LLM step, not one speech unit.** With
`PROGRESSIVE_SSE_STREAMING` — on by default — consecutive text chunks are merged
into a single `Part`, so there is exactly one text part to correct however many
units you bracketed. Carry a unit ordinal in the correction and concatenate.

**The correction is a real ADK event:**

```python
Event(
    invocation_id=..., author=agent_name, content=None,
    custom_metadata={"kind": "vql.correction", "speech_id": event_id,
                     "unit": n, "heard_text": heard},
)
```

`content=None` makes it invisible to the prompt for free, so a fold you have not
wired up yet ignores corrections rather than leaking them at the model. Never set
`partial=True` — partial events are silently dropped before they reach the
session.

**Where to fold.** Not `before_model_callback`: reassigning `llm_request.contents`
there discards the dynamic instruction and `RunConfig.model_input_context`,
because the instruction processor runs first and writes into the same list.
Replace `contents.request_processor` in the flow's processor list with a wrapper
that swaps in the folded events around ADK's own processor, so everything
downstream still assembles on corrected history. `request_processors` is a plain
public list and `_llm_flow` is an overridable property.

Two failure modes at that step. **Fold on events, never on
`llm_request.contents`** — ADK strips `adk-`-prefixed function-call ids during
assembly, so the ids you need are gone by then. And ADK's copy is shallow:
writing a top-level `Part` field is safe, but mutating a nested one
(`function_call.args`) writes straight through into the stored event and corrupts
the record.

**Context is native.** `LlmRequest._insert_transient_user_content` inserts
backward and stops after a `function_response`, so it cannot land between a call
and its result. Do not append an `Event` for this instead: the runner appends a
call and its response as two separate operations with an `await` between them,
and a push arriving in that window lands inside the pair.

**Compaction is a hazard here, not a gift.** ADK's runs over raw `session.events`,
so every summary bakes in what the agent generated rather than what the caller
heard, and its timestamp ranges can swallow a generated event while its later
correction survives outside. Leave it off, or run it over the folded history.

**This does not port to bidi.** `run_live` builds contents once per connection
and keeps history server-side, `Event.id` is re-minted per response, and the
callback sees a single content rather than the history. ADK's own live path
flushes the text generated before the interrupt, which is still ahead of the ear.

## OpenAI Agents SDK

Verified against `openai-agents` 0.22.0.

**The id** is the Responses `item_id` (`msg_…`), known at
`response.output_item.added` — before any text. `RunItemStreamEvent` is too late;
it fires per step, after tools resolve. On Chat Completions there is no id at all:
every synthesized item id is the literal string `"__fake_id__"`, so mint your own
and keep a side table.

**Fold at two points, because neither is enough alone.**

- Implement the `Session` protocol as the record: `add_items` appends events
  verbatim, `get_items` returns the folded view. Make `pop_item` a no-op and
  `clear_session` append a compaction event rather than truncating.
- `Session.get_items` fires **once per `Runner.run()`**, not per tool hop, so a
  correction arriving mid-run would wait for the next run. Apply the same fold in
  `RunConfig.call_model_input_filter`, which runs immediately before every model
  call, receives a copy, and does not mutate the session.

This is why the fold must be idempotent.

**Queued context drains into the record, not into the filter.** Items the filter
adds are discarded on the next hop — the runner rebuilds input from the original
input plus generated items. Append a real user-role event at the flush boundary
and let the fold re-emit it.

**Correct text in place on a shallow copy; never rebuild the item.** Truncating
text leaves `annotations` offsets pointing past the end and invalidates
`logprobs`, and a rebuilt message silently loses `phase`, which some models want
resent.

Reasoning here is a separate top-level item carrying `encrypted_content`, not a
signature on a text part — take it from `output_item.done`, where it is complete,
and never from `.added`.

## A framework that hands you the message list

This is the easiest case and the one that proves the pattern is not
framework-shaped. Where the loop is a function over a plain list — you supply
`messages`, it returns a response — there is no hook to find, because the fold is
just the function you call to build the array. Mint your own ids and hold them in
a custom message type or a side map.

Check the hazard anyway. That is the layer that deleted aborted turns in the
example above, and it sits below every framework, hooks or not.

## What is not settled

**Whether a corrected text part should keep its reasoning signature.** Google's
documentation says a signature must be returned in the exact part it arrived in,
and that signatures on text parts are not strictly validated. Two agent
frameworks read that oppositely in their own source: ADK treats the signature as
bound to the text and returns it verbatim; `pi` documents a production failure
caused by *dropping* one, and strips signatures on model change rather than on
text change. Neither is a live-API result, and as of 2026-09-01 neither are we.

Until that is measured, treat it as provider-conditional and state which you
chose. Note that Gemini ships `skip_thought_signature_validator` as a sentinel
for the "no valid signature for this part" case, which may be the answer rather
than either keeping or dropping. The same question is open on the Responses API:
whether replayed `encrypted_content` is validated against the text of the item
that follows it.

**What an unheard unit looks like is yours to choose.** When `heard` is empty and
the unit carried only text, dropping the turn and keeping an empty one are both
defensible: the caller heard nothing, so nothing was said — and yet the model
then sees two consecutive caller turns. Nothing on the wire depends on it. Decide
it for your framework, write down which you chose, and keep it consistent.

## Read next

- [Transcripts and heard truth](/build/brain/transcripts/) — the callback, the
  guarantees, and the ordering rules.
- [Bringing an agent you already have](/build/existing-agent/) — the port, and
  where the two shipped Gemini adapters fit.
- [Interruption and heard truth](/design/interruption-and-heard-truth/) — the
  argument under all of this.
