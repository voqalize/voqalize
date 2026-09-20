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
        yield SpeechChunk(await self.answer(msg.text))
        yield SpeechEnd()
```

That is a brain that runs. The [Quickstart](/build/quickstart/) has the same
class with its imports, its greeting and the route it mounts on; this page is
about everything you can add to it.

## The generator is the mouth

`on_user_message` and `on_user_idle` are async generators, and they are the only
callbacks that are. Speech is the only thing they yield, because speech is the
only thing with a position on the audio timeline. An action, a language switch,
hanging up — each is a method on `session`, callable from anywhere, including
from a callback that is not a generator at all.

## The greeting is static

`greet` returns a string or `None`. It is `async` so you can look something up —
`session.init` carries whatever your page passed at connect — **not so you can
generate the sentence.** The user is connected and hearing nothing while it
runs, so a model call here is dead air before the first word.

## The callbacks

`on_user_message` is the only one you must implement. It and `on_user_idle` are
the generators — the moments the floor is yours. The rest return `None`,
which is what stops a click or an error from talking over the user:
`on_session_start` and `greet` open the call, `on_rtvi` receives what the person
did in your app, `on_finalize` reports what they actually heard, `on_error`
carries a signal from Voqalize, and `on_session_end` runs as the socket closes.

Everything that is not speech is a method on `session` and callable from any of
them: `session.dispatch(action)`, `await session.configure(config)`,
`session.send_rtvi(...)`, `session.end(reason)`.

**`on_finalize` is the one people skip and then debug for a week.** Write
`fin.heard` into your history rather than what you generated — a barged-in reply
that produced three sentences and delivered one must be remembered as one, or the
model will reference things it never finished saying. Nothing in a metric shows
this.

Signatures, what each callback is handed, and when each fires are in
[the Brain API](/reference/brain/).

## Read next

- [Speaking](/build/brain/speaking/) — the frames, why a turn is many units, what streaming buys.
- [Actions](/build/brain/actions/) — the second channel: typed, rendered, never spoken.
- [Tools](/build/brain/tools/) — local function calls, and what the clock costs you.
- [Context and history](/build/brain/context/) — what the person does in your app, flowing back.
- [Transcripts](/build/brain/transcripts/) — what was heard, which is not what you sent.
- [Deploy the brain](/build/hosting/) — a route Voqalize dials, or a relay your brain dials out to.
- [Testing a brain](/build/testing/) — over the real wire, without a microphone.
