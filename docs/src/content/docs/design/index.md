---
title: Designing for voice
description: What changes when the output is spoken, the user can interrupt, and the screen is right there. The durable half of the problem.
---

Getting a call working is a week. Getting one people use twice is the rest of the
work, and almost none of it is about the API. Speech has no scrollback. A user
can interrupt you mid-word. The screen is right there and it holds detail the ear
cannot.

What follows is the whole argument, written from running production voice agents
rather than from first principles. It is one page because each of these ideas is the same idea from another side,
and reading them apart made that harder to see.

## Voice points, the screen holds

Speech is serial, it cannot be skimmed, and it is gone the moment it is played.
Nine product codes read aloud are nine things the user has forgotten by the
time the tenth arrives. The screen is random-access and it persists, and it
cannot direct attention on its own.

So the division: **voice carries intent, acknowledgement, and the one number that
matters. The screen carries the record.** A number the user must hold in their
head belongs on the screen.

### Speech holds the floor; an action does not

A brain reaches the user by speaking and by dispatching an action, and the
difference between them is audio.

**Speech** is yielded from the turn. `SpeechStart`, `SpeechChunk`, `SpeechEnd` are the
only yieldable types (`sdk/events.py`), and a unit of speech is one thing the
user can be interrupted out of.

**An action** is dispatched, never yielded. It carries no audio, so it holds no
floor, and `session.dispatch(action)` is callable from inside a turn, from a
callback that is not a generator at all, and from work that finished long after
the turn that started it. The mechanism is documented at
[actions](/build/brain/actions/); this page is about what to send and when.

That asymmetry is the whole design. Speaking is a turn and costs the user time.
Rendering costs them nothing, so it can happen at any moment, including while the
agent is saying something else.

### Speak the pointer, render the payload

All of these are running today:

| Shape | What voice says |
|---|---|
| Options on a row the user can tap | "drops or ointment?" — never the prices |
| A video seeked to the second that answers the question | one line pointing at the screen |
| A ring drawn around the field in question | the field's name, and nothing else |

`orderdesk` states the rule in its own prompt, because a text-to-speech engine
reads pharmaceutical brand names badly and the screen spells them correctly:
*"NEVER read out a list of options, prices, pack sizes or SKU codes. Ever. That
is what the screen is for"* (`demos/orderdesk/backend/brain.py`). `aura` plays
the official how-to video muted and seeked to the right chapter while the agent
narrates over it, and carries the chapter map in the prompt marked as material
for choosing a timestamp rather than a script to read out.

### An action is a shape, and the shape is the contract

Subclass `Action` and the fields are the payload. The class name becomes the wire
name — `OpenItinerary` becomes `open_itinerary` — and can be pinned with `name=`
when you would rather the class be free to move.

**Every declared field is emitted, including the ones that are `None`.** The wire
shape of an action is a function of the class rather than of which fields
happened to be set on this call, so the browser declares one total interface and
handles one shape. JSON Schema export is what makes the TypeScript half
generatable rather than hand-copied (`sdk/actions.py`).

Inside a turn, a dispatch reaches the wire in the order it runs, so it cannot
jump ahead of speech already yielded. An action that belongs with a sentence goes
next to that sentence.

### The failure this prevents is invisible

An agent that narrates its own screen produces a correct transcript, a completed
call, and a satisfied dashboard. Every instrument reports success. The only
symptom is that the call took twice as long as it needed to, because the slow
channel repeated what the fast one had already delivered — and no metric you
have distinguishes that from a user who had more to say.

The proxy that does see it is the interruption rate. Users talk over an agent
that is reading things to them.

## The turn budget

Between a user finishing a sentence and hearing the first syllable back, this
happens in order:

1. Voqalize decides the user has stopped and finalizes the recognizer's text.
2. **Your callback runs, until it yields its first `SpeechChunk`.**
3. Voqalize synthesizes that chunk and plays it out.

The middle interval is the only latency in the product your code controls. It has
a measurable name — **time to first chunk** — and it has no idle time you can
reclaim later. If the user waited, they waited.

So a fast turn is not a turn that finishes quickly. It is a turn that *starts*
quickly. After the first chunk you have the user's attention and the rest of
your generation runs underneath it; before the first chunk you have a person
listening to nothing.

### `greet` is not a turn

`greet` returns a string, not a generator. It is `async` so you can look up the
user's name, and not so you can generate the sentence. This is the one moment
where a user is sitting on a connected session hearing nothing at all, and a
model round-trip here is the most expensive latency in the product.

A fixed line, or a template over what the page sent — `f"Hi {name}, how can I
help?"` — is as elaborate as it should get. Returning `None` opens the session
silently, which is what an ambient agent wants.

Where a generated opener is worth having, speak a written one first. The demos
send a one-word hello from a table (`demos/voqalize_demos/greeting.py`) before
any model has run, and append a line to the greeting prompt telling the model to
continue rather than greet again. The user hears a syllable immediately and the
model's sentence arrives underneath it.

### Where your half actually goes

**Time to the model's first token, not its last.** Awaiting a completion before
speaking converts a streaming system into a batch one. Stream chunks as you
produce them.

**Tool round trips.** A tool in your process is a function call. The same tool
reached over HTTP is a network round trip on every turn that uses it — see
[tool design](#tool-design-for-voice).

**Retrieval as a serial hop**, unless it was started before it was needed — see
[parallel workstreams](#parallel-workstreams).

**Work that was serial for no reason.** Three sequential `await`s cost the sum;
one `asyncio.gather` costs the slowest.

**Prompt size**, which is [prompt design](#prompt-design-for-voice).

**A cache miss you caused yourself.** The system instruction is the cache prefix.
Set it once per session and it matches turn after turn; edit it — even to append
one fresh line of context — and every turn re-reads the whole thing. This is the
item on the list that is free to get right and quietly expensive to get wrong,
because nothing in a transcript shows it. Context that changes belongs at the
tail, next to the latest user message.

### Thinking budget is a latency setting

A reasoning budget on a voice turn is spent in silence the user sits through,
and thought tokens are never spoken, so the cost has no audible half at all. The
SDK's `VOICE_THINKING` asks for the least thinking the default model allows
(`sdk/gemini.py`).

Both halves of that setting are model-specific, and each way it bites below was
verified against the live API on 2026-08-14:

- **The knob moved.** `thinking_budget=0` was accepted by the 3.1 models; 3.5 and
  later reject it with a bare `400 INVALID_ARGUMENT` that names no field.
- **The floor moved.** `gemini-3.7-flash` refuses `MINIMAL` outright. Its floor,
  `LOW`, still spends around 275 thought tokens, so it has no zero-thinking
  setting at all, and its turns ran about twice as long as the default model's.
- **A level a model accepts is not one it acts at.** `gemini-3.5-flash-lite`
  takes `MINIMAL` and then drives the screen on 9 of 15 identical turns, asking
  "which trip?" on the rest. At `LOW` it was 11 of 15.

Measure when you change the model. The numbers above are one afternoon against
one set of turns, and they are printed here with that condition attached because
that is all they are.

### Pace the user while the work runs

These are in production. `orderdesk`: *"Start every reply with a
tiny phrase so audio begins instantly,"* and *"Say a tiny line before or while
calling a tool — never leave silence."* `aura`: *"Speak a short line first, then
call the tool."*

This is not a trick to hide latency. A short acknowledgement is what a person
does while they look something up, and it converts dead air into a turn that has
started.

### Instruments you already have

`on_finalize` fires once per speech unit after playout, carrying what was heard
and whether it was interrupted. Stamp a monotonic clock at callback entry and
close it at your first `SpeechChunk`; that is your half of the budget, measured on
every turn, in your own process.

**Interruption rate is the cheapest quality proxy in the product.** Users talk
over an agent that is too slow, too long, or wrong, and those are hard to
tell apart from a transcript and easy to tell apart from a clock.

`get_call_record` over [the MCP server](/reference/mcp/) returns our half
of the same call, joined on the same `session_id` — each turn's `marks` and
the session's `pace`, and every unit the user cut short.

### There are no latency numbers on this page

We publish no figure for the intervals we own, because we have not measured them
under conditions we would be willing to print. A number without its percentile,
its region and its load is a mood, and this reader would check it.

So this section names moments instead — before the first word, on every turn that
uses it — and hands over the instruments to measure your own half, which is the
half you can change today.

## Interruption and heard truth

Your brain yields three sentences. The user cuts in after the first one.

What the user knows is one sentence. What your code produced is three. If the
three go into history, every later turn is planned against a version of the call
that never happened — the agent thanks the user for a detail they never gave,
or declines to repeat something it believes it already covered.

Nothing catches this. There is no error, no dropped frame, no latency spike, no
failed eval. The transcript your own code wrote agrees with itself. The only
artifact that disagrees is the recording, and nobody plays the recording of a call
that went fine.

### Interruption is the normal case

On any turn longer than a sentence, a user who cuts in is a user working
correctly: they got what they needed and moved on. Building for it as an
exception gets the arithmetic backwards — the uninterrupted turn is the one worth
treating as a special case, because it is the one where the user had nothing to
add.

### `on_finalize` hands you the prefix

After a unit of speech finishes playing, one callback fires:

```python
async def on_finalize(self, session: Session, fin: Finalize) -> None:
    ...
```

`Finalize` carries `speech_id`, `heard` and `generated`.

`heard` is **the delivered prefix** — the text that reached the user's ear, not
the text you yielded. `generated` is the text you yielded, kept by the SDK so the
two can be set side by side; `fin.interrupted` is that comparison and nothing
more. This is the
one place Voqalize knows something your process cannot: playout happens on our
side of the wire, so where the audio actually stopped is ours to report and yours
to record.

The callback fires long after the generator that produced the speech has
returned. That ordering is the point — the truth about a unit is not available
while it is still playing.

### The obligation, stated plainly

Whatever you persist as the assistant's turn — a Gemini `Content`, a row in your
own table, a line in a log — is built from `fin.heard`. Not from the string you
yielded, and not from the accumulated chunks.

The same lie twice:

- **History for the next model call.** The model plans its next turn against what
  the user knows.
- **Everything downstream of the transcript** — summaries, QA scoring, handoff
  notes, the "what did we tell this customer" audit that someone runs six months
  later during a dispute.

The downstream record is worse, because by then the recording is gone.

### Not everything that makes noise is an interruption

A user who says "mm-hm" while your agent is talking is agreeing, not cutting
in, and an agent that stops dead for every backchannel is unusable. So barge-in
is gated on a **confidence that ramps with how long real speech has been
sustained** — a phantom detection or a one-word garble stays under the bar, a
sustained interruption crosses it. The bar sits just under the value the
recognizer carries at the barge-in point, so a genuine one clears it with margin.

What follows are design constraints on what you write rather than knobs you can
turn:

**A short imperative may not land.** "Stop" shouted over a long answer is exactly
the shape that stays below the bar — brief, and over before confidence has
climbed. That is the accepted cost of not stopping for "mm-hm", and it is a
reason to keep a spoken answer short enough that the user does not need to
shout it down.

**An idle user is a different case.** When your agent is not speaking, any
speech starts a turn instantly — the bar applies only to cutting off speech in
progress.

**While a tool call runs, the user is muted, and that is not configurable.** A
round trip cannot be barged into. This is the mechanical reason the clock is
yours during a tool call: say something before you make the call, because the
user cannot take the floor to ask what happened.

### What happens to a turn that gets cut

Voqalize sends an interruption naming the last turn it applies to. The SDK marks
that number as a watermark, and every turn at or below it is dead: its task is
cancelled, and any chunk still in flight from it is discarded rather than spoken.

Consequences worth knowing:

**Your `finally` runs.** The generator is closed, not abandoned — the SDK calls
`aclose()`, so cleanup, span exits and released locks all execute on an
interrupted turn exactly as on a completed one.

**Turn ids fence the turns from each other.** The turn that replaces a cancelled
one carries a higher number, and a watermark never rises to reach it. Late work
from a dead turn cannot leak a sentence into its successor.

### What interruption does not undo

An action already dispatched has already arrived. The screen does not roll back
when the user cuts in, and it should not: the itinerary they are looking at is
the itinerary they asked for, whether or not the sentence describing it finished.

In-flight tool work is not cancelled either. A charge that was authorized was
authorized. If a tool must not outlive its turn, that is a decision for your tool
to make, and it needs its own idempotency rather than a hope about timing.

### Testing it without a microphone

The conformance harness models playout and heard-truth finalization the way the
Voqalize does, so heard truth is an assertion your brain passes rather than a
behaviour described on a page. `VoqalizeDriver` records what was delivered per
unit, which means a test can assert on the heard text instead of the generated
text — and the strongest property available is the one worth asserting:
**the history your brain wrote equals what the driver says was heard.**

See [testing a brain](/build/testing/).

### One limit we have not established

`heard` is a prefix of your text, but playout was cut in the middle of a word.
Whether that prefix is character-exact or rounds to a boundary is not something we
have pinned down, and a page should not claim a precision nobody has verified.
Treat `heard` as the honest account of what was delivered, and do not build
anything that depends on its last character.

## Misunderstanding and reversal

The same things go wrong on every voice deployment, and none of them are going
away.

The recognizer mishears. The model misinterprets what it heard correctly. And the
user changes their mind halfway through the sentence — which is not an error at
all. It is how people talk, and a system that treats it as a fault is a system
that argues with its user.

So "how do we prevent mistakes" is the wrong question to build against. The
questions that produce a working design are: **how fast does a mistake become
visible, and how cheap is it to undo?**

The answers follow, and **withholding the authority that matters** is the one
that saves you.

### Show what the agent believes, including that it is unsure

Uncertainty is a state to render, rather than a null to hide. `orderdesk` gives
every row on the cart a status:

```python
LineItemStatus = Literal["resolving", "multi_family", "multi_variant", "matched", "not_found"]
```

A row that has entered but not settled says so on screen. The pharmacist can see
the agent is still working on item four while item five is already matched, and
can fix item four by hand without waiting to be asked.

`spoken_text` and `source` do the same job at a finer grain. Each row keeps
`spoken_text` —
the raw heard phrase — beside the SKU it resolved to, so the *evidence* for a
mistake survives the resolution. Seeing "amlong" next to a row that resolved to
the wrong brand tells the pharmacist immediately whether the recognizer or the
matcher was at fault. And `source: "agent" | "manual"` records who put the row
there, so a hand correction is distinguishable from the agent's own work.

None of that is possible if the screen only shows conclusions.

### Make correction cheap, by voice and by hand

By voice, correction is a taxonomy of tools rather than one re-add:

| What the user says | Tool | What it preserves |
|---|---|---|
| "make it three" | `set_quantity` | the row |
| "one more" | `adjust_quantity` | the row, and the distinction between delta and absolute |
| "the syrup, the tablets" | `change_variant` | the row and its quantity |
| "I meant the 40" | `refine_item` | the row and its history |
| "drop that" | `remove_items` | — |
| picking from options | `choose` | the row |

The shared property is identity. The row stays where it is, so the user's eye
does not have to re-find it. `orderdesk`'s prompt gives the reason in five words:
remove and re-add, and "he loses his place on the screen."

By hand, correction is the same event arriving from the other side. The pharmacist
taps a variant pill, edits a quantity, deletes a row, adds something from the
search bar — and the page's state reaches the brain, which yields to it. That path
is a supported one, and it is how the agent notices a correction it never heard.

The instruction that closes the loop is the reciprocal of everything above:
"**NEVER redo what he already did himself.**"

### Withhold the authority that matters

The strongest correction mechanism is not correcting at all. Anything important or
irreversible is committed by a human, with a click, and the agent has no tool for
it.

- `orderdesk`: "You have no confirm tool and no confirm authority." The pharmacist
  presses Confirm; the brain sees the screen say `confirmed` and closes in one
  line.
- `servicing`: `submit_packet` goes through after the advisor approves.
- `aura`: `authenticate` waits on a tap.

**Why a click and not a spoken "yes."** A spoken yes can be misheard. It can be
background noise the recognizer resolved into a word. It can be a genuine yes to a
question the user only half-heard, because they started talking over the second
half of it — and [what the user heard](#interruption-and-heard-truth) is the part
that finished playing, which your agent does not know at the moment it asks. A
click has none of those failure modes, and it lands on a screen showing exactly
what is being agreed to.

This is also what makes every earlier tool safe. Corrections stay cheap right up
to the commit boundary, and the boundary is a human.

### Where the story stops

Limits, stated because a page that omits them would be selling something.

**We have no worked example of correcting something already committed.** The
compensating-call taxonomy above runs up to the confirm click and stops. Whatever
undoes a placed order is your system's problem, and it is a different kind of
problem.

**All of this assumes a screen.** Every mechanism here — visible uncertainty,
identity-preserving edits, the click that commits — needs somewhere to render. An
agent with no UI has none of them, and has to fall back to spoken confirmation
with all the failure modes just listed. If you are building voice-only, the honest
version is fewer irreversible actions rather than better confirmations.

## Parallel workstreams

A form makes you wait for each field. You type, it validates, it renders the next
one, and the round trip repeats until the form is done. Speech has no such
round trip: a user can name six items in one breath and stop, having spent four
seconds on what the form spends four minutes on.

That burst is where the speed comes from. It is also the thing an agent gives back
first. Handle the six items one at a time — ask, resolve, confirm, ask again —
and you have rebuilt the form, out loud, at the pace of a conversation. Slower
than the form it replaced, because now every field costs a spoken turn.

So parallelism is not a later optimization here. Without it the user's natural
behaviour becomes your worst case.

### Take the burst whole

`orderdesk`'s prompt says it in the imperative, because a model left to itself
will take one item and stop:

> The moment he names a product, call `add_items`. Do not wait for the previous
> one to resolve; do not ask a question in between. He can list six items in one
> breath — take them all in ONE `add_items` call with a list.

One tool call, six items, six independent pieces of work in flight. The rows enter
as `resolving` and settle one at a time — matched, or ambiguous between two pack
sizes, or not stocked — each on its own timeline, in whatever order the lookups
come back. The user is still talking while they settle.

### Work that outlives its turn

`servicing` makes the same shape explicit for long work. `prepare_case` returns
immediately:

```python
{"status": "preparing_in_background",
 "note": "Running in the background; the advisor stays unblocked. Tell them when ready."}
```

The return value is not data. It is an instruction to the model about how to
behave while waiting — the tool's answer to "what do I say now" is "carry on."

What makes this safe:

`session.dispatch(...)` never blocks and is callable from anywhere, including from
a task that outlived the turn that started it. A background job finishing ninety
seconds later can still paint the screen.

An action carries no audio, so it needs no floor. The screen can change while the
agent is mid-sentence, and neither one waits for the other.

### The real design question is how a result comes back

Voice is one serial channel and there are now three finished jobs to report.
Reading them out is almost never the answer. The ways back are not equally
priced:

| Way | When to use it | Shipped in |
|---|---|---|
| A row changes on screen, silently | The result is legible and unambiguous | `orderdesk`, `forge` |
| One short spoken line | It changes what the user should do next | `servicing` |
| A spoken question | Genuinely ambiguous, and only the user can resolve it | `orderdesk` |

The default is the silent row change, and `forge`'s prompt tells the model to
trust it:

> Every tool you call also shows up as a live task on screen (a small "activity"
> checklist), so your actions are already acknowledged visually — trust it and
> stay quiet.

Speaking costs a turn, so a spoken line and a spoken question are spent, not
spread. When
several rows do turn out to need the user, batch them the way you batched the
intake — `orderdesk` again:

> Batch your questions. Let him finish his run of items, then at the natural
> pause ask about the ambiguous rows, one short question each.

### The exception is a human, not a machine

`aura` has one blocking tool. `authenticate` awaits a future that resolves when
the user taps consent on their own screen, and the turn genuinely waits.

That is the rule, drawn tightly: machine work never blocks a turn; waiting on a
person sometimes has to, because there is nothing else the agent could
truthfully be doing. Even then it is worth a spoken line first, so the user
knows the silence is theirs to end.

### Ordering and failure are yours to decide

**Ordering.** Three background jobs finishing at once produce three dispatches in
the order they completed. `orderdesk` sends the whole row rather than a patch, so
last write wins per row and arrival order stops mattering. That is a convention
that works, and it is the one to copy until the SDK reserves something better.

**Failure.** Every worked example here succeeds. A fan-out where one branch fails
is the case you will hit first in production, and the failed row still has to
reach the user through one of the ways above — most often as a row that says
so.

## Prompt design for voice

A chat prompt can afford to be thin. The model can look things up, and the reader
watches a spinner while it does — a two-second tool call reads as work happening.

Say the same two seconds out loud. Nothing happens, on a channel where nothing
happening is the one thing a user reacts to. So the arithmetic changes: what the
agent needs, it should mostly already have.

That is the whole design rule, and it is not "be concise."

### The 80/10/10 target

| Share of what the agent needs | Where it lives | What it costs |
|---|---|---|
| 80% | In the prompt already | tokens |
| 10% | One fast tool call away — in your process, no network | a model round trip |
| 10% | Genuinely slow — remote, expensive | a background workstream, with an answer to "what does the user hear meanwhile" |

These numbers are a design target we hold to, not a ratio we have instrumented.
Their job is the genuinely slow tenth: anything that lands there needs a plan
for the silence, which is [parallel workstreams](#parallel-workstreams).

### What a voice prompt does that a chat prompt need not

**Talk less, do more.** The default reply is one short line, and everything
longer is on the screen. The shipped prompts say it in the imperative, because a
model's default register is a paragraph:

- `orderdesk`: "No markdown, no lists, no stage directions. **Never narrate your
  own actions** — call the tool and say only what the pharmacist should hear."
- `forge`: "your actions are already acknowledged visually — trust it and stay
  quiet."
- `sugar`: "better, don't say units at all; the screen shows them."
- `support`: "Never read out ids or order numbers as raw text — say 'your order
  from May 28th' instead."

**Hold its prompt still.** The system prompt is the cache prefix. Set it once
per session and it matches turn after turn; rebuild it — even to append one fresh
line — and the provider re-reads the whole thing on every turn, which the user
pays for in silence. Volatile context goes at the tail, next to the latest user
message, where a change costs the provider only the small new suffix. This is the
cheapest latency win available and the easiest to throw away by accident, because
nothing in a transcript shows it.

**Know where the user is.** The agent needs a way to answer "what is on screen
right now," and the answer has to be current rather than remembered. Both `aura` and
`servicing` do the same thing: the page keeps pushing its state, the brain parks the latest
snapshot, and a tool reads it on demand — `aura`'s `get_screen_context`,
`servicing`'s `get_advisor_context`. The reciprocal instruction matters as much.
The screen is authoritative over the agent's own memory of it, because the user
has hands: `orderdesk`'s prompt ends that thought with "**NEVER redo what he
already did himself.**"

**Track a task list.** Several threads are open at once and the prompt has to
name them and say how each one closes. `servicing`'s prompt is explicit that
background prep runs while the advisor keeps working: "prepare the other case
quietly and tell them when it's ready. They are never blocked."

**Assume it misheard.** A recognizer on a phone line in a pharmacy will get
things wrong. Correction paths belong in the prompt as first-class instructions
rather than as a fallback paragraph at the end — see
[misunderstanding and reversal](#misunderstanding-and-reversal).

### Never leave silence, in the shipped prompts

- `orderdesk`: "Say a tiny line before or while calling a tool — never leave
  silence, never speak a whole sentence about what you are doing."
- `aura`: "opening a page or loading a video takes a moment; never leave silence.
  Say a brief line FIRST, THEN call the tool."

These are the prompt doing latency work.

### The sharpest fragment we have shipped

`orderdesk` has to disambiguate a spoken drug name against two dozen SKUs, over
the phone, in Hindi, without reading a list aloud. Its prompt teaches an
information-theoretic rule in plain language, and the whole block is worth reading
as a model of how specific this gets:

> Four or fewer choices need no machinery: the pills are already on his screen.
>
> Five or more, and the tool hands you a CANDIDATE TABLE instead of options. Never
> read it. Never try to show it all. Call `ask_choice` ONCE with one short English
> question and TWO TO FOUR choices that split those candidates as evenly as you
> can. **The sharpest question is the one that eliminates the most candidates
> WHATEVER he answers** — a choice that keeps twenty-three of twenty-four is a
> wasted turn.
>
> Group on the axis that actually partitions the list: the suffix line first, then
> form, then a strength band. **Never split on pack size while a bigger axis still
> divides the list.**
>
> **TWO ROUNDS AT MOST.** Round one cuts twenty-four to a handful; round two is
> leaf pills he can tap.

What to take from it: it names the threshold at which machinery starts (five),
it gives the model a decision rule rather than an example, and it caps the
interaction in turns, because a turn is the unit the user feels.

The wording of the question is the model's; the *shape* is not. `ask_choice`
rejects a set that has fewer than two or more than four choices, or that leaves a
candidate uncovered — and the prompt tells the model what happens when it does, so
a rejection is a retry rather than a dead turn.

## Tool design for voice

A tool call in a chat app is a pause. A tool call in a voice call is dead air,
because the model cannot speak while it waits for a result it asked for.

That single fact reshapes every tool you write, and the properties that follow
are properties of the tool rather than of the prompt around it.

### A tool returns immediately

Single-digit milliseconds, or a promise and a note. `servicing`'s `prepare_case`
kicks off minutes of background work and returns this:

```python
{"status": "preparing_in_background",
 "note": "Running in the background; the advisor stays unblocked. Tell them when ready."}
```

There is no data in that return value. It is behavioural instruction — the tool
telling the model how to act while the answer is on its way. That is what a voice
tool's return value is for whenever the work is slower than a sentence.

A tool that genuinely takes two seconds has been mis-split. Break it into a cheap
dispatch plus a background workstream, and report the result the way
[parallel workstreams](#parallel-workstreams) describes.

### A tool is not cancelled

Barge-in cancels the turn. It does not cancel a tool call already running, and it
does not un-dispatch an action already sent.

This sounds untidy and is correct: the user interrupted the *speech*. They did
not interrupt the lookup, and half-applied work is worse to reason about than
completed work. The screen showing what they asked for is right, whether or not
the sentence describing it finished.

Tools also run **one at a time, in the order the model produced them**. Tools
racing would put the user's display in an order the model never asked for, and
the screen is the thing the user is reading.

### A tool is undone by another tool

The undo for a voice tool is a compensating call, and the compensating calls are
worth enumerating separately rather than collapsing into a re-add. `orderdesk`
gives the model an edit tool per operation and shouts why:

> **A QUANTITY TWEAK IS NEVER A RE-ADD.** An absolute number is `set_quantity`; a
> relative one is `adjust_quantity` with a delta. If he wants none of it, that is
> `remove_items`.

> **A VARIANT SWAP IS NEVER A RE-ADD EITHER.** … Never remove the row and add it
> again — he loses his place on the screen.

The reason in that second line is the general rule. Each of these preserves the
identity of the row it touches, so the display updates in place and the user's
eye keeps its position. A re-add is correct in the database and wrong on the
screen.

The premise underneath is that tools are cheap enough to undo this way. A tool
expensive enough that you want to abort it mid-flight is the one to split.

### A failed call is a result, not an exception

A tool that raises comes back to the model as an error it can read and act on:
`is_error` on the step, plus a line in your log. The model sees what went wrong
and calls again.

The SDK's own comment on that path is worth repeating, because the failure mode it
names is the one that reaches production:

> `is_error` is the half the automatic path has no room for: there a failure
> reaches the model as an ordinary payload, and the model narrates it as success.

An agent cheerfully telling a user their order is placed, because the failure
came back as `{"error": …}` and looked like data, is the shape of the worst bug in
this category.

Use the same seam for validation. `orderdesk`'s `ask_choice` is rejected unless it
has two to four choices, uses known codes, and covers every candidate; a separate
validator rejects non-Latin labels headed for a screen that must stay Latin.
These come back as retriable errors, and the prompt warns the model in advance that they
can. So the *shape* of the question is guaranteed even though its wording is the
model's.

### A tool never holds irreversible authority

`orderdesk`'s prompt draws the line in one sentence:

> You have no confirm tool and no confirm authority. Your job is a fully matched
> cart: every row green, every quantity set.

The pharmacist presses Confirm. `servicing` is the same shape — `submit_packet`
goes through after the advisor approves. The agent gets the work to the edge of
the commit and stops there, which is also what makes every earlier tool safe to
undo.

### Some tools must not take the floor

`orderdesk` answers the manual search bar's `catalog_searched` and `variants_opened`
**floor-free** — session-scoped, no inference, no speech. The user is typing in
a search box; a keystroke must not make the agent start talking over them.

If a tool exists to serve the screen rather than the conversation, say so
explicitly. Anything that can be triggered by a tap or a keystroke belongs in this
category.

### The one blocking tool that is allowed

`aura`'s `authenticate` awaits a future resolved when the user taps consent. It
blocks because it is waiting on a human decision, and there is nothing else the
agent could truthfully be doing.

Machine work never blocks a turn. A person's decision sometimes has to.

### The checklist

1. Returns in single-digit milliseconds, or returns a promise and a note.
2. Typed arguments; bad ones come back as an error the model can read.
3. Has an undo that is another tool call.
4. Preserves the identity of what it touched, so the screen does not jump.
5. Holds no authority over anything irreversible.

## When you are done here

You have an application worth putting in front of people. Keeping it working is
[Operate](/operate/).
