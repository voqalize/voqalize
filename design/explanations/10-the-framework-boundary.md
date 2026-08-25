# 10. The framework boundary

> **The surprise.** The best thing we can do for your tools is nothing. Whatever
> agentic framework you brought already runs them; every wrapper we put in front
> of it is one of their features you lose and one of our bugs you inherit.

This page is about a line, not a mechanism: what the voice tier owns and what it
must keep its hands off. It was argued out over two days against one demo
(`sugar`) and one brain (`GeminiBrain`), and it ended with more code deleted than
written.

## Belief

- **An agentic system owns its tools by definition.** google-genai, ADK, LangGraph
  and the Claude Agent SDK all take a plain list of callables and take it from
  there. Get in front of any of them and we are permanently behind: their next
  tool-calling feature ships broken, with us as the reason.
- **What is ours is narrower and outlives all of them.** Give the agent a voice,
  cut its output into speech units, and tell it what the caller actually heard.
  That is the whole product on this seam.
- **Anything that exists because of a bug upstream must die when the bug does.**
  It is not a feature, it is residue with a shelf life, and shipping it makes it
  permanent.
- **Ask why the wrapper exists — then ask again one layer up.** Most wrappers
  answer the first question well and the second one not at all. The second answer
  is usually "because we made a shape the framework does not want."
- **Our own annotation needs a reason no framework already gives.** A `@tool`
  decorator of ours is one more thing to learn that buys a developer nothing
  anywhere else. If the framework takes bare callables, hand it bare callables.
- **Take the standard's core, not its newest objects.** RTVI 1.0's message set is
  what stock clients implement; the objects added last month are what one version
  of one client implements.
- **Trade compile-time comfort for stock compatibility, deliberately and out
  loud.** Typed action ids and typed action results were ours and were real. They
  went, because a page that runs on an unmodified pipecat client is worth more
  than a type error we would have caught in review anyway. Name the loss, then
  take it.
- **Demo-specific belongs to the demo.** A pattern that has one caller is not a
  platform feature; it is that caller's code sitting in the wrong repository.
- **A hack you would not defend out loud means the answer is one level higher.**
  When the fix is a `__deepcopy__` that returns `self`, stop: ask what the vendor
  recommends for this, and why the problem is not biting everyone else.
- **Declare once.** A tool declared in Python and restated in the prompt is two
  things to keep in sync and one of them will drift silently. The exception is
  admitted in writing, not by accident.
- **The tool must reach the session.** This is a requirement, not a preference —
  a tool that cannot drive the screen is half a tool. Any shape that fails it is
  the wrong shape, however clean it reads.
- **There are two clocks, and AFC only knows one of them.** See below; it is the
  one belief on this page that survived the whole argument unchanged.

## Facts

- **`GeminiBrain.tools` is a property returning bound `async def` methods**
  (`sdk/python/src/voqalize/sdk/gemini.py:213`), read once per turn — so the list
  can depend on the caller. There is no decorator, no registry and no discovery.
  `@tool`, `_collect_tools`, `_bind_tool`, the `_results` ContextVar and
  `_flush_results` were all deleted, together with the execution wrapper that
  laundered a raising tool into a result we then had to un-launder.
- **The method is the declaration.** Its name is what the model calls, its
  docstring is the description the model reads, its single pydantic parameter is
  the schema. Per-parameter descriptions survive because google-genai ≥ 2.19 emits
  `parameters_json_schema` on the callable path — which is why the hand-driven
  tool loop that existed to preserve them could go.
- **Automatic function calling is on**:
  `types.AutomaticFunctionCallingConfig(maximum_remote_calls=max_tool_hops)`,
  default 6 (`gemini.py:119`, `:130`). One turn that calls a tool and then speaks
  about the result is **one call from here**, not a loop of ours.
- **A speech unit is not an LLM call.** It is a bracket the brain opens and
  closes, and it is cut out of one stream that may span many tool hops. That
  misreading was the other reason AFC had been disabled.
- **The session reaches the tool through the brain, never through the signature.**
  `Brain.session` (`brain.py:456`) and `Brain.turn` (`brain.py:475`, backed by the
  `_current_turn` ContextVar at `:123`). A `session` parameter would be part of the
  schema, and the model would try to fill it.
- **Two things are enforced at the seam rather than documented** — `_ready()`,
  `gemini.py:423`:
  - **`async def` is required.** AFC runs a sync tool on a worker thread, where the
    contextvars carrying `self.turn` are unset. Refused, with a message saying why.
  - **What google-genai receives is not a bound method.** It deep-copies the config
    on entry and on every hop, and `copy.deepcopy` of a bound method copies
    `__self__`. `_ready` hands over a `functools.wraps` closure, which `deepcopy`
    treats as atomic. ADK draws the same line in the same place — declarations in
    the config, callables in `LlmRequest.tools_dict` beside it.
- **The context is written from both sides of the seam.** Order comes from the
  stream; tool *responses* come from `automatic_function_calling_history`
  (`_fold_results`, `gemini.py:254`), which is the only place they exist —
  google-genai feeds them to the model and never to us. `_drop_unanswered`
  (`:290`) removes a `function_call` a barge-in left without its response, because
  Gemini will not accept that conversation next turn — while the tool that ran
  beside it stays run, because it did.
- **Reconciliation is untouched by any of this.** The `_awaiting` FIFO
  (`gemini.py:138`), one `Finalize` per speech unit, truncate-and-drop: all still
  there. See [3](03-interruption-and-heard-truth.md).
- **The client SDK is the connection step and nothing else.** *(And on
  2026-08-24 it stopped being even that: deprecated, no successor — the server
  answers in the transport's own shape now. See
  [11](11-the-browser-is-pipecats.md) and `docs/client/handshake`.)*
  `@voqalize/client-react` exported `createSession`, `startBotParams`,
  `toConnectParams`, `fromSessionResponse` and one error type — step one of
  pipecat's own two-step connect. `VoqalAgent.tsx`, `microphone.ts`,
  `useUiCommand.ts` and `useVoqalSession.ts` are gone. The media transport is
  pipecat's `SmallWebRTCTransport`, the events are RTVI's, and a dispatched action
  arrives at pipecat's `useUICommandHandler`.

## The two clocks

The strongest thing to survive this argument is the thing that did **not** get
simpler.

Handing the tool loop to AFC feels like it should retire heard-truth
reconciliation: the framework runs the whole turn and gives us a complete record,
so surely the record is the history. It is not, and the reason is that there are
two clocks running.

- **The generation clock** — AFC streaming, tools running, hops advancing.
- **The playout clock** — what the caller's ear is receiving, seconds behind it.

A barge-in is an event on the *playout* clock. AFC's record says what was
**generated**, never what was **heard**; the model can be on its third hop while
the caller is still hearing a sentence from the first. So the rule the whole
design rests on is:

> **Speech is reconciled against heard truth. Tool calls are not.**

Tool calls stand because they happened. Speech is rewritten to the delivered
prefix, and the reconciliation is applied at the start of the *next* turn — which
is the general pattern, not a Gemini detail, and it lives entirely inside the SDK
without touching the wire or the runtime.

## Proof

- **Declared once, in one class.** `sugar`'s `LogMeal`
  (`demos/sugar/backend/brain.py:170`) is simultaneously the tool's parameter model
  and the `Action` dispatched to the screen. `total_calories` is a
  `computed_field`: summed on our side, therefore **absent from the schema Gemini
  is given and present in the payload the browser renders**. That is the whole
  reason it is one class and not two.
- **The prompt does not restate the tools.** `sugar`'s system instruction says so
  in as many words: "Each one carries its own description — read it there; none of
  it is repeated here," followed by three rules that sit *on top of* the tools
  rather than repeating them.
- **The deletions, measured.** Sugar's brain: −466/+240 in one file, declaring
  fourteen tools once. The React client: −2168/+362. Sugar's UI on stock pipecat:
  −1226/+168, then its call lifecycle handed to voice-ui-kit's `PipecatAppBase`.
- **The bug that proves the belief.** Because `deepcopy` copies `__self__`, tools
  would have run on a *clone* of the brain: `self.session.dispatch` reaching
  nothing, the context written to an object no one reads, the model told `ok`,
  and not one thing on the wire to say so. It crashed instead of going quiet only
  because our brain happens to hold a `genai.Client` whose lock cannot be copied.
  That was luck. A wrapper's failure mode is silence.
- **172 SDK tests did not find it; dialling the live API did.** The verification
  that counted was a real call: `log_meal` dispatched with a server-computed
  `total_calories=330`, `switch_language` moving both legs before Hindi speech,
  and a 13-entry context with each tool response sitting between the call that
  made it and the unit that answered.

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

## Gap

- **This boundary is proven on one brain and one demo.** `GeminiBrain` and
  `sugar`. The ADK path (`travel`, `orderdesk`) has not been through it, and ten
  demos are unported. Nothing here should be stated as a general shape until a
  second framework has run against it.
- **`_ready` is residue, and we know it.** Every line of it is a fact about
  google-genai's internals — the deep-copy of bound methods, the split between
  `get_type_hints` for the declaration and `inspect.signature` for the call under
  `from __future__ import annotations`. It is the smallest wrapper we could find,
  not the absence of one, and it will rot on somebody else's release schedule.
- **A failed tool is invisible to the caller.** google-genai hands the model
  `{'error': …}` and the model will cheerfully tell the caller it did the thing.
  All we can do on our side of the seam is log a warning. There is no path from a
  tool failure to something the caller hears.
- **Flat parameters are unsupported, and we route around it by documenting.** A
  bare `Literal` gets a correct schema and then fails to *execute*. Telling people
  to wrap it in a model is exactly the kind of workaround rule 2 says must die —
  it lives here because the alternative is a wrapper.
- **Pydantic → TypeScript is a tolerated duplication.** The action models are
  hand-mirrored in `demos/sugar/frontend/src/types.ts`. Generating them is future
  scope; until then the two halves carry a comment saying they must move together.
- **The unexplored test of the whole thesis:** a second Gemini client on the
  `interactions` API (`client.interactions.create`, stateless, streaming, with
  AFC). If the boundary holds across two clients from the same vendor, it is a
  boundary. If it does not, `_ready` was never residue — it was a wrapper we had
  not admitted to.
