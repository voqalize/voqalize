# L2 — the wire and the brain

Read when: frames, envelope, turns, speech units, callbacks, actions and app
events, typed models, tools, heard truth, or implementing the wire in a language
that is not Python.

## The boundary is text

One WebSocket per session carries **protobuf**, versioned, schema published as
`proto/` in `github.com/voqalize/voqalize`. Planes riding it: the speech/turn
plane, and RTVI messages carried verbatim.

Nothing on the wire declares a tool, carries a JSON schema, or names a model.
Voqalize sends recognized text and typed app events up; the brain sends text,
speech-unit boundaries and typed actions down. Tools, prompts, memory and model
choice are entirely inside the brain's process and Voqalize cannot see them.

Consequence a developer asks about directly: **there is no LangChain, ADK,
OpenAI-Agents or LlamaIndex adapter, and one is not planned.** An adapter would
have to reach across the boundary and inspect a tool registry. Instead the brain
is a plain class; whatever framework it wants lives inside `on_user_message`.

## Callbacks

`Brain` is a Python class. Override what applies:

- `greet() -> str | None` — the opening line. **Static string, template at most,
  never a model call.** It is spoken before the user has said anything, so a
  model call here buys latency on the one turn the user is most sensitive to.
- `on_user_message(turn)` — the main callback. Async generator.
- `on_user_idle(...)` — fires only if `idle.timeout_ms` is non-zero.
- `on_rtvi(...)` — app events that arrived as RTVI.
- `on_finalize(...)` — end of a turn, including what the user actually heard.
- `on_session_start` / `on_session_end` / `on_error`.

Speaking callbacks yield `SpeechStart` → one or more `SpeechChunk` → `SpeechEnd`.
A **turn** is one exchange; a **speech unit** is one continuous stretch of
synthesized speech inside it. A turn may contain several speech units, with the
brain doing work in between.

Because a turn holds many speech units, *silence between units is not
structurally detectable* — that is a known limit, not a bug to report.

## Actions — driving the page

The brain's second output. Define a pydantic model, dispatch it:

```python
class ShowSection(Action):
    id: str
session.dispatch(ShowSection(id="how"))
```

It leaves as an RTVI `ui-command` and arrives in the browser at stock pipecat's
`useUICommandHandler`. The reverse direction — the app telling the brain the user
clicked something, or edited the document by hand — is `ui-event`, parsed on the
brain side by `AppEvents.parse`.

`voqalize types` generates TypeScript discriminated unions from both sets. Add an
action and the browser build **fails until the new case is handled**. That is the
point of generating rather than documenting.

So: UI actions are **typed by the developer**, not a fixed vocabulary Voqalize
knows. Voqalize forwards them without understanding them.

## Never block on the UI

A tool announces and returns. If the brain needs something from the page, that
something is an **unfabricable parameter** on the next tool call, not a wait. The
agent says what it is doing and gives the turn back; when the app sends the
event, the next turn has it.

## Async work that outlives its turn

Long work (a plan comparison, a document fetch) runs in the background and pushes
its result in later, unprompted, by opening a new speech unit on the live
session. The turn that started it already ended. This is how the demos do
"compare against plan" — the agent says it is looking, returns, and speaks again
when the answer lands.

## Heard truth

When the user interrupts, Voqalize stops mid-word and reports the **heard
prefix** for each speech unit on `Finalize`. The brain's history must record what
the user *heard*, not what the brain intended to say — otherwise the model
believes it delivered a sentence the user never got, and the next turn is
incoherent.

The watermark is **one-way**: it only ever moves forward. There is no rollback.

## A typed sentence is a turn

`client.sendText` from the browser is committed as a **user turn**, not a side
channel message, and is always answered aloud. Typing and speaking are the same
input as far as the brain is concerned.

## Another language

The wire is published; implement it. `sk_`-authenticated Cortex mode or an
inbound route both work with any language.

The compatibility path is the **conformance harness** in the Python SDK — it is a
fake Voqalize speaking the real wire over a real socket, so a Go or Node brain
can be driven by it in CI and checked for conformance without a browser or a
model. See `observability-and-testing.md`.

Caution from experience: if you vendor the `.proto` rather than depend on a
released SDK, duplicate generated stubs of the same file **collide in the protobuf
descriptor pool**. Depend on a published package.

## Multiple agents behind one brain

Voqalize does not care. One session is one socket to one brain URL; whatever
routing, hand-off or multi-agent orchestration happens behind it is invisible and
unconstrained. There is no notion of "agent" on the wire beyond the `agent_id`
that selected the brain URL at connect time.

## State

Entirely the developer's problem, deliberately. The `Brain` object is
per-session and in-memory; if the process restarts mid-call, the socket dies with
it and the call ends — **there is no reconnection**, so there is nothing to
rehydrate. For state that must survive, write it to the customer's own store from
inside the brain. Voqalize stores the transcript and events, not the brain's
working memory.
