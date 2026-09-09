# 5. Prompt design for voice

> **The surprise.** 80% of what the agent needs must already be in the prompt,
> because every lookup it has to make is silence the caller sits through. A voice
> prompt is not a chat prompt with "be concise" appended — it is a latency budget
> written in English.

## Belief — the 80/10/10 split

| Share | Where it lives | Cost |
|---|---|---|
| **80%** | In the system prompt (**written once**) plus the change note at the tail | tokens only |
| **10%** | One fast tool call away — in-memory, no network | a model round trip |
| **10%** | Genuinely slow — remote, expensive | **must be designed with feedback**: it becomes a background workstream, not a wait |

The split is a *design target*, not a measurement. Its point is that the third
bucket is where agents go silent, so anything you put there has to come with an
answer to "what does the caller hear meanwhile?" ([4](04-parallel-workstreams.md)).

## Belief — the five things a voice prompt must do that a chat prompt need not

1. **Talk less, do more.** The default reply length is one short line. Everything
   longer is on the screen ([1](01-voice-points-screen-holds.md)).
2. **Hold its prompt still.** The system prompt is set once per session and never
   edited. See the facts below — this is the single cheapest latency win available
   and the easiest one to throw away by accident.
3. **Be told where it is.** The agent must have a way to know what is on screen
   *right now* — a tool that reads a mirror the brain owns, kept current by the
   typed events the page sends as the person acts.
4. **Track a task list.** The agent holds several open threads; the prompt has to
   name them and say how they close.
5. **Assume it misheard.** Correction paths are first-class instructions, not an
   afterthought ([9](09-misunderstanding-and-reversal.md)).

## Facts — the seams the SDK gives you

- **`ScreenState`** (`demos/voqalize_demos/screen.py`) is the mechanism for
  bucket one. Two lines cross per gesture and no more: `moved(what)` names the act
  ("The customer changed a quantity") and points at the read tool; `stale()`
  refuses a mutation aimed at a screen the model has not re-read. The screen
  itself never enters the context.
- **The system prompt is the cache prefix, and it is written once.** Everything
  volatile goes at the *tail*, immediately before the latest user turn: the prefix
  stays byte-identical turn after turn, so it stays cached, and the only thing the
  provider re-reads is the small new suffix. A prompt that is rebuilt every turn is
  a prompt that is never cached, and the caller pays for it in silence.
- **The note goes at the tail, never into the system instruction.** Appending to
  the instruction on every model call is the wrong end of the context: it breaks
  the cache prefix for a sentence that was only ever about the last few seconds.
- **A note alone is not enough, which is why `stale()` exists.** A tool is only as
  fresh as the model's decision to call it, so a model that never re-reads answers
  "what's on screen?" from a stale turn. Prompt discipline is a request; the
  version refusal is a rule, and it is retriable — read, then act.
- An event that changes nothing appends **nothing at all** — `apply_event` returns
  `None` and the context is untouched, rather than gaining an empty note the model
  has to interpret.
- `version` is what makes the read enforceable rather than merely requested, and it
  moves only when the *person* moves the screen — so an ordinary turn pays no
  extra hop.
- **Thinking level is part of the prompt budget**, and it is model-specific — see
  [2](02-the-turn-budget.md) for the measured trap.

## Proof — nuggets already in production prompts

**Length and register**
- `orderdesk`: "Start every reply with a tiny phrase so audio begins instantly."
- `orderdesk`: "**Never narrate your own actions.** …call the tool and say only what
  the pharmacist should hear."
- `forge`: "your actions are already acknowledged visually — trust it and stay quiet."
- `sugar`: "don't say units at all; the screen shows them."
- `support`: "Never read out ids or order numbers as raw text."

**Batching, in both directions**
- `orderdesk`: "Do not wait for the previous one to resolve… take them all in ONE
  `add_items` call with a list." / "Batch your questions."

**Never leave silence**
- `orderdesk`: "Say a tiny line before or while calling a tool — never leave silence."
- `aura`: "Speak a short line first, then call the tool."

**Knowing where it is**
- Every demo that has a screen worth reading names its read tool to `ScreenState`
  and nothing else: `aura` `get_screen_context`, `servicing` `get_advisor_context`,
  `legal` `get_reading_position`, `forge`/`sugar`/`travel` `read_screen`.
- `orderdesk` keeps one derived line in the context — **PENDING**, naming the rows
  still short of a SKU and the axes to ask about, so the model never re-asks a
  question the screen already answered. It is not the screen; it is the list of
  open questions, which is conversation state and therefore the brain's.

**The strongest single artifact: `orderdesk`'s disambiguation block.** It is a
prompt fragment that survived an offline eval, and it teaches an *information-
theoretic* rule in plain language:
- "Four or fewer choices need no machinery: the pills are already on his screen."
- "**The sharpest question is the one that eliminates the most candidates WHATEVER
  he answers** — a choice that keeps twenty-three of twenty-four is a wasted turn."
- "Group on the axis that actually partitions the list… Never split on pack size
  while a bigger axis still divides the list."
- "**TWO ROUNDS AT MOST.**"
- With a worked example (twenty-four TELMA SKUs → four groups → three strengths)
  and an explicit *what you must NOT do* list.
- And the closing loop back to the screen: "If he taps a group pill himself, the
  PENDING line shows fewer candidates on that row. Do not repeat the question."

**The mirror is the authority, because the events keep it true.** `orderdesk`
holds the cart and patches it from both sides — its own dispatches and the
pharmacist's typed gestures — so there is no snapshot to prefer over it and no
diff to infer from. The reciprocal instruction is still in the prompt: "**NEVER
redo what he already did himself.**"

**Structure the model cannot get wrong.** `ask_choice` is validated for 2–4
choices, known codes, and total coverage; a bad set is rejected with a retriable
tool error. So "the *shape* of the question is guaranteed even though its wording
is the model's" ([6](06-tool-design.md)).

## Gap

- We publish **no** prompt guidance. Every demo re-derives the same six rules.
  This page's job is to hoist them once.
- **Open:** the 80/10/10 numbers are a conviction, not a measurement. State them
  as a design target and say so, or find a way to instrument the ratio.
- `orderdesk/backend/eval/` is the only demo with an eval harness, and it is
  excluded from pyright as an offline tool. If prompt fragments are load-bearing
  enough to eval, the eval is a proof point worth generalising.
