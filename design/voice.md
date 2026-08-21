# The Voqalize voice

The writing standard for every surface a developer reads: the documentation, the SDK
docstrings, error messages, the wire contract's prose, the MCP server's instructions and
tool descriptions, the demo source, the blog, the changelog and commit messages. The marketing register is a second document, and it starts by pointing
at this one.

Internal engineering and strategy documents are outside this standard — design notes and
decision records are reasoning, and reasoning argues by contrast. One rule reaches them
anyway: **nothing we write calls Voqalize a platform**, because a word we use internally
is a word that leaks.

*This document teaches with contrast, prohibition and failing examples. The copy it
governs uses none of those.*

## The core

**Voqalize is written by the engineer who built the voice tier and still runs it, to the
engineer who will own the brain on the other end of the socket.** That is the persona, and
it is a relationship rather than a tone: two people own two halves of one running system,
and this half writes so the seam holds. A counterpart does not sell — the reader already
has the hard half — and does not soften a failure mode, because the reader meets it at
1,143 simultaneous sessions and remembers who left it out. Blunt about what breaks, exact
about what it costs in milliseconds, expecting to be argued with. Before publishing a
sentence, ask whether you would say it to someone whose code is on the other side of the
socket, in a shared incident channel, with the call up.

**Two registers share that discipline and divide by purpose.** Documentation speaks in the
imperative, leads with the code, and persuades at no point; it is defined below. Marketing
speaks in the second person, carries the architectural argument in prose, and ends at a
link or a command; it is defined alongside the marketing site, and everything on this page
governs it. Both draw every technical noun from one closed lexicon, and both describe the
boundary by what the reader keeps — their model, their prompts, their tools, their data,
their transcripts, their version control. Neither describes it by what we take.

### Five principles

**Mechanism before outcome.** Name what the system does before naming what it is worth; a
mechanism can be checked and an outcome has to be believed. Write "Voqalize opens one
WebSocket per session and sends you the user's finalized text," and leave the outcome
sentence to the reader. They will write a better one.

**Ownership before capability.** Our product is a separation, so our sentences divide
things the way the architecture does and stand on the reader's side while doing it.
"Everything below the text boundary is ours" is a rejected sentence: true, well-formed,
possessive on the wrong party. Write instead that your model, your prompts and your tools
run in the process you deploy today, and the transcripts and session events land in your
systems, on your schema.

**Address before assertion.** Each paragraph's load-bearing claim carries something the
reader can open — a path, a command, a repository, a version, a demo. "Eleven demo agents
are readable source" has an address; "battle-tested in production" is the same claim with
the address removed, and this reader discounted it before arriving. Where we cannot supply
one, we cut the sentence or move it to a piece that can show the work.

**Limit as fact, and only a real one.** A constraint is a positive statement of what is
true, in its own sentence, at the moment the reader would otherwise find it themselves,
and we never manufacture a concession to sound humble. A previous draft of this page
offered "we cannot debug your agent for you," which is false: we hold the session events,
logs, transcripts and metrics, and the MCP server hands them back inside the reader's own
repository. An invented limit costs what an oversold claim costs — the reader re-reads
everything before it. The same rule governs what has not shipped: the bridge
implementation of the voice tier is committed to open source and is not published yet, so
write it that way, with the date or the condition attached. A roadmap item in the present
tense is the fastest way to lose a reader who checks.

**One word per concept.** The lexicon is closed: a concept keeps its name in the proto,
the SDK, the docs, the site and the deck simultaneously. Synonyms are how a technical
product stops being understood, and they are what makes a corpus unusable to the coding
agent reading it — which, increasingly, is the reader.

## Four signature moves

Positive, repeatable, and ours. A reader should recognize the page without the logo on it.

### 1. Name the silence

Point at a failure that produces no error, no log line and no metric. Say what the
reader's instruments will report, then what is actually happening. This is the move most
identified with us, because a voice stack is full of failures that look like success on
every dashboard.

> A Hindi call read by an English voice reference returns a perfect transcript. The words
> are right and the speaker is wrong, and no transcript, log, metric or WER score can see
> it. So the language moves in one call, on both legs, in the brain.

The version that teaches nothing: *"Be sure to configure both STT and TTS language, or you
may see unexpected results."* It hedges, it names no mechanism, and it gives no reason to
act now rather than later.

**Boundary.** Only where the failure is genuinely invisible to instruments the reader
already has. Applied to a bug that throws a stack trace it reads as theatre, and the third
time it appears it stops being believed.

### 2. The load-bearing absence

Name something our surface does not have, and show the class of bug that therefore cannot
happen. The absence is the guarantee, and stating it is how a reader learns what they can
stop defending against.

> The callback that receives what the user clicked cannot speak. A click can change what
> the agent knows, move the screen, or end the call. There is nothing to yield there, so
> the rule needs no runtime check, and an agent cannot talk over the person who clicked.

> Voice owns the floor and the brain spends it. There is no `request_floor` and no way to
> interrupt the user; that absence is what makes turn order predictable, and the rest of
> the Brain surface follows from it.

**Boundary, and it is the one that matters.** This move describes our own shape. The
moment it reaches for someone else's — *"unlike platforms that let the agent grab the
floor"* — it has stopped being this move and become the banned contrast construction. A
plain negative fact about our own system, in its own clause, is how an absence gets
documented and is always allowed. A comparative frame is not.

### 3. Put the clock in the sentence

Every capability arrives with its position on the audio timeline or its cost in
milliseconds. Latency is the physics of this product, so it belongs in the grammar rather
than in a performance section at the bottom of the page.

> `greet` is the one moment a connected caller is sitting there hearing nothing, so no
> model call belongs in it. A fixed line, or a template over `session.init` — `f"Hi
> {name}, how can I help?"` — and the `async` is there so you can look up that name.

> A tool call in your process is a function call. The same tool reached as a webhook is
> 300–800 ms, on every turn that uses it.

**Boundary.** A number appears only after we measured it and only with the conditions it
was measured under. 1,143 simultaneous voice interviews during a single nationwide campus
drive is a measured claim; "sub-second" without a percentile is a mood. Where we have no
number, name the moment — before the first word, while the user is still speaking, on
every turn after this one.

### 4. Start where the reader already is

The other three moves assume a reader who has decided to care. They are strong at minute
three and inert at second one, and an opening has to earn the next thirty seconds from
someone who has committed nothing. So an opening may make the stakes concrete before any
mechanism arrives — drawn from the reader's situation rather than from what we offer.

> You have been handed "add voice to this." The demo you saw worked on a stage, and the
> thing you have to ship answers a real user on a bad connection while your database is
> slow. Voqalize runs the voice tier and opens one WebSocket per session to a route you
> own.

**Boundary, and it is tight, because this is the one move salesmanship can hide in.** The
first paragraph of a page or a post only. At most two sentences before the mechanism
lands. It describes the reader's situation and never their feelings — no *frustrating*, no
*painful*, no *finally*. It names no benefit. If the situation cannot be stated without
naming what we sell, cut it and open with the mechanism instead, which is always allowed
and never wrong.

## What we believe about voice, and how it shows in the prose

Each belief has a consequence for the sentence, not only for the subject matter.

**A turn has a budget, and prompt and tool design spend it.** So no capability is
described without what it costs the turn. A page that adds a field to a context payload
says in the same breath that the model sees it on every turn after this one, and pays for
it every time.

**Silence is a bug.** The user is kept informed while work happens — avatar state, a
spoken acknowledgement, a screen update. So our samples never contain an `await` the
reader cannot hear: *"say something first, because you are holding the floor, and an
`await` with no speech in front of it is dead air."* A code block with a silent round-trip
in it has shipped a latency bug in prose.

**Work goes in parallel.** So the concurrent version is the first version shown. Putting
`asyncio.gather` in a tips box at the end teaches the serial shape as the normal one, and
the reader keeps it.

**The agent will mishear, so things must be undoable.** So every how-to that changes
something shows the path back, and draft-and-approve is written as the ordinary shape
rather than a safety feature bolted on: the commit is a button in the reader's own UI,
running the reader's own code path.

**Voice in, screen out.** So the verbs divide and never blur. The agent *says* words and
*renders* rows; it never "tells the user" what the mechanism draws. The app *pushes* what
it chooses to push — we never see, watch, observe or understand the screen, because we do
none of those and the words put us in the browser-agent comparison set.

## Where we are allowed to be vivid

A voice made only of restrictions produces prose that is safe and forgettable. These are
licensed, with their edges.

**Be vivid about the ear.** Describe what a broken call sounds like, concretely: the agent
references a sentence it never finished saying; the caller hears nothing on the one turn
nothing will retry; the answer arrives after the user has already repeated the question.
*Edge:* the sound follows from a mechanism named in the same paragraph. Sensory writing
with nothing under it is atmosphere.

**Be blunt about fit.** We may tell a reader plainly that this is the wrong product for
them and name what is right: if the product *is* the call, with no screen and no backend
to put a brain in, a telephony specialist will beat us and should. *Edge:* always about
the shape of the workload, never about the reader.

**Be dry.** Understatement is the entire humor budget, and it works because the facts
carry themselves: *"Our own eleven demos run that way in 33 seconds."* Numbers we earned —
1,143 simultaneous, ~50,000 interviews, 18 MCP tools, English plus 22 Indic languages on
our own GPUs — are stated flat and take no adjective, because the adjective is what makes
a reader suspect the number. No exclamation, no wink, no emoji, no joke at a named
product's expense; we build on Pipecat and we say so.

**Take a position in explanation pages.** A page whose job is an argument may state it in
the first person plural and defend it: *"We think the agent's second output channel should
render rather than speak. Voice is the fastest way to express dense intent and the worst
way to receive it, and every primitive we ship follows from that asymmetry."* *Edge:*
positions live in explanation pages and the blog; a how-to cites one and returns to the
steps.

## The documentation register

Gets a working thing running, and stops the reader building around a constraint they did
not understand. Imperative. Code or command first, then the shortest sentence explaining
why the API has that shape. Preconditions before the step, failure modes at the step that
produces them. No persuasion, no adjectives of quality, no forward reference the reader
cannot act on.

> ### Read the user's screen
>
> Send a `state_sync` message from the browser whenever your store changes, debounced to
> around 250 ms:
>
> ```ts
> sendMessage("state_sync", { workspace: snapshot() })
> ```
>
> The brain receives it in `on_app_message`. This callback is not a generator: it can
> update state, dispatch an action, or end the session, and it cannot speak. A click
> arrives while the user is still talking, and an agent that answers a click talks over
> the person making it.
>
> Keep the payload to the fields that change the answer. The model sees this on the next
> turn, and everything you add costs tokens and latency on every turn after it.

Three moves in one snippet: code first, a load-bearing absence, and the clock.

## The other surfaces

**Error messages** are our highest-traffic documentation and they are read at the worst
moment. What happened, the mechanism that makes it wrong, the exact edit that fixes it. No
apology, and never the word "unexpected".

```
AdkBrain: tool(s) book_flight on agent 'concierge' are not `async def`.
Voice tools must be async: ADK dispatches a sync tool on a thread pool, where
the SDK's voice() context var is unset and voice().action(...) raises
NoActiveVoice mid-call. Make them `async def` — the body needs no other
change — or pass allow_sync_tools=True if these tools never call voice().
```

**SDK docstrings** are where the point of view becomes enforceable, because the reader is
in the editor with the decision in front of them. State the rule, then its consequence in
the caller's ear. The `greet` and `ActionHandle` docstrings are the reference standard;
read them before writing a new one.

**MCP server instructions and tool descriptions** are read by an autonomous agent that
follows them literally, across 18 tools on a hosted endpoint. Imperative, one tool per
description, preconditions stated, every description ending in the call to make next. No
"simply", no "just", no persuasion — there is nobody to persuade. Name the silent failure
explicitly, because an agent cannot hear something being wrong.

> `create_agent` — Creates the agent record and returns its id and publishable key. Call
> `update_agent` with `brain_url` next: an agent whose `brain_url` is empty still connects
> and still greets, using the hosted welcome brain, so a session that answers is not
> evidence that your brain is wired.

**Changelog entries** are dated, present tense, written from the reader's migration
inward. First sentence: what is now true. Second: what the reader does. A breaking change
says what breaks before it says what replaces it.

> **2026-08-12 — One key per agent.** A `sk_` secret key names an agent, so the brain leg
> of a Cortex link authenticates with the key the rest of your integration already holds.
> Keys minted before today keep working. A `pk_` is refused at that route, because a
> publishable key ships in page source and what comes back would let the holder claim the
> brain leg.

**Commit messages** say what is, rather than how it got here: `area: the state after the
change, present tense`. This is already the house style and should stay it — *"sdk: greet
is one line, and an inference_id is the brain's alone"*, *"sdk/gemini: every unit is
awaiting a finalize, silent ones included"*. Someone scanning `git log` gets the state of the
system, in order.

**The blog** carries the arguments too big for a docs page: turn latency budgets,
heard-truth history under barge-in, why the second output channel is typed. First person
plural, the measurement included, the failure we hit named. A post that could have been a
feature announcement should have been a changelog entry.

## Mechanics and lexicon

Declarative sentences, active voice. First person plural for what we operate, second
person for what the reader operates, and no construction blurring the two (`we help you`,
`lets you`, `enables you to`). Sentence case in headings.

**Retired constructions.** The banned thing is contrast against an alternative — another
product, another vendor, or the reader's prior experience — in any grammar: `X, not Y`,
`unlike`, `no more`, `without the`. Contrast between two things inside our own system
stays, because that is how an API gets described. Also retired: the fragment pair as a
headline; the question as a heading; and the tricolon run for cadence — *"Faster. Simpler.
Yours."* — which is the real ban there, since a plain enumeration of three true things is
ordinary English.

**Retired words.** *magic, effortless, just works, delight, superpower, unleash, seamless,
transform, unlock, supercharge, revolutionize, empower, leverage, robust,
enterprise-grade, blazing, best-in-class, next-gen, AI-powered, cutting-edge.*

A new term is added to this table first and to the SDK second.

| Concept | Word | Retired |
|---|---|---|
| The developer's WebSocket agent | **brain** | agent backend, bot, handler |
| One call, one socket | **session** | meeting, conversation, call, room |
| What Voqalize runs below text | **the voice tier** | the platform, the runtime, voice infrastructure |
| The runtime that dials the brain | **Voice** | our server, the bot, the runtime |
| Typed message, brain → screen | **action** | UI command, event, tool |
| Screen state, screen → brain | **state sync** | context push, screen capture |
| The published protocol | **the wire** | the protocol, our API |
| The relay for egress-only networks | **Cortex** | tunnel, proxy |
| The compatibility suite | **the conformance harness** | test kit, test suite |
| The 2-D talking head | **the avatar** | video agent, digital human |

**We never describe Voqalize as a platform.** Our argument is that intelligence should not
live on a platform, and the word contradicts the product in the reader's ear. Internal
engineering documents still use it; nothing a customer reads does. **Internal service and
repository names never appear in customer-facing text either** — the runtime is **Voice**,
whatever the process is called in our own logs.

## The recognition test

Before publishing, in order. A failure on any line is a rewrite rather than a softening.

1. Is there a mechanism in the first two sentences?
2. Does the paragraph's main claim carry an address the reader can open?
3. Are the possessives on the reader's side of the boundary?
4. Does every number carry the conditions it was measured under?
5. Is every limit in it real, and stated as a positive fact?
6. Does anything compare us to an alternative, explicitly or by shape?
7. Any retired word, any retired construction?
8. Would you say it to your counterpart, on a live incident, with the call up?

One passage fails, and naming why reproduces the guide:

> Voqalize makes it effortless to add voice to your app. Unlike hosted agent platforms, we
> don't take your prompts hostage — your data stays yours, your stack stays yours, your
> team stays in control. Get started in minutes with our developer-first platform.

A comparative frame ("unlike") and a second one hiding as a denial ("we don't take"); a
tricolon run for cadence; a retired word in the first sentence and *platform* twice;
"minutes" as a number nobody measured; not one mechanism and not one address; and the
boundary drawn by what we refrain from taking rather than by what the reader keeps.

One passes:

> You expose one WebSocket route in the service you already deploy. Voqalize opens it once
> per session, sends the user's finalized text, and receives back the words to speak and
> the typed actions that update your screen. Your model, your prompts, your tools and your
> retrieval stay in that route, in the process they run in today, and the transcripts,
> session events and outcomes land in your systems on your schema. The wire contract is
> published, the eleven demo agents are readable source, and the conformance harness
> drives your agent over the same protocol the runtime speaks — so the boundary is
> something you can check.

Mechanism in sentence one. Every possessive on the reader's side. Three openable addresses
in the last sentence, no comparison, no adjective of quality, no symbol a refactor can
invalidate. It reads like one engineer telling another exactly where the seam is, which is
the only thing this voice is trying to be.
