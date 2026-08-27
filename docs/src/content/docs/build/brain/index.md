---
title: Your first brain
description: The callbacks a brain implements, the one that is required, and the smallest brain that holds a conversation.
---

A brain is a class. You subclass `Brain`, implement `on_user_message`, and yield
speech. That is the whole required surface — everything else is a callback you
add when you need it, and a method on `session` when it is not speech.

```python
class Concierge(Brain):
    async def on_user_message(self, session, msg):
        yield SpeechStart()
        yield Chunk(await self.answer(msg.text))
        yield SpeechEnd()
```

That is a brain that runs. The [Quickstart](/build/quickstart/) has the same
class with its imports, its greeting and the route it mounts on; this page is
about everything you can add to it.

## The generator is the mouth

`on_user_message` is an async generator and the only one. Speech is the only
thing it yields, because speech is the only thing with a position on the audio
timeline. An action, a language switch, hanging up — each is a method on
`session`, callable from anywhere, including from a callback that is not a
generator at all.

## The greeting is static

`greet` returns a string or `None`. It is `async` so you can look something up —
`session.init` carries whatever your page passed at connect — **not so you can
generate the sentence.** The caller is connected and hearing nothing while it
runs, so a model call here is dead air before the first word.

## The callbacks

Eight, and `on_user_message` is the only one you must implement. Two are
generators — they are the two moments the floor is yours — and the other six
return `None`, which is what stops a click or an error from talking over the
caller.

| Callback | Fires | Yields |
|---|---|---|
| `on_session_start(session)` | Once, before `greet`. Load history, [configure the voice](/reference/catalog/). | — |
| `greet(session)` | Once, after it. Return a string or `None`. | — |
| `on_user_message(session, msg)` | The caller finished a turn. `msg.text` is the finalized transcript. | speech |
| `on_user_idle(session, idle)` | The caller went quiet. `idle.level` counts escalations, so nudge at 1 and wrap up at 3. | speech |
| `on_rtvi(session, msg)` | The app said something — a tap, a keystroke, a [state sync](/build/brain/context/). | — |
| `on_finalize(session, fin)` | One speech unit finished playing. `fin.heard` is what the caller actually got. | — |
| `on_error(session, error)` | Voqalize signalled something. The session is never killed by it. | — |
| `on_session_end(session)` | Once, for any reason. Best-effort; it never blocks the close. | — |

Everything that is not speech is a method on `session` and callable from any of
them: `session.dispatch(action)`, `await session.configure(config)`,
`session.send_rtvi(...)`, `session.end(reason)`.

**`on_finalize` is the one people skip and then debug for a week.** Write
`fin.heard` into your history rather than what you generated — a barged-in reply
that produced three sentences and delivered one must be remembered as one, or the
model will reference things it never finished saying. Nothing in a metric shows
this.

Signatures, types and the exact shape of every argument are in
[the Brain API](/reference/brain/).

## The chapters

| | |
|---|---|
| [Speaking](/build/brain/speaking/) | The three frames, why a turn is many units, what streaming buys. |
| [Actions](/build/brain/actions/) | The second channel — typed, rendered, never spoken. |
| [Tools](/build/brain/tools/) | Local function calls, and what the clock costs you. |
| [Context and history](/build/brain/context/) | What the caller does in the app, flowing back. |
| [Transcripts](/build/brain/transcripts/) | What was heard, which is not what you sent. |

## Read next

- [Where the brain runs](/build/hosting/) — the two hosting paths.
- [Testing a brain](/build/testing/) — over the real wire, without a microphone.
