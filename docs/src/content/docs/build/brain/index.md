---
title: Build the brain
description: The callbacks a brain implements, the one that is required, and the smallest brain that holds a conversation.
---

A brain is a class. You subclass `Brain`, implement `on_user_message`, and yield
speech. Everything else is a callback you add when you need it, or a method on
`session` when it is not speech. New to the terms? The
[glossary](/build/session/#glossary) defines each one.

```python
from voqalize.sdk import Brain, SpeechChunk, SpeechEnd, SpeechStart


class Concierge(Brain):
    async def greet(self, session):
        return "Hi, I'm the concierge. What can I do for you?"

    async def on_user_message(self, session, msg):
        yield SpeechStart()
        yield SpeechChunk("You said: " + msg.text)
        yield SpeechEnd()
```

That brain runs. The [Quickstart](/build/quickstart/) runs it over Cortex and
takes a call; this page is about what you add to it.

## Speech is yielded; everything else is a session method

`on_user_message` and `on_user_idle` are async generators, and they are the only
callbacks that are. They yield speech and nothing else, because speech is the
only output with a position on the audio timeline. Showing something, switching
language and hanging up are methods on `session`, callable from any callback:

| Method | What it does |
|---|---|
| `session.dispatch(action)` | Sends a typed [action](/build/brain/actions/) to your app. |
| `await session.configure(config)` | Changes voice, language, turn-taking or the idle timer ([Voice and language](/build/voice-and-language/)). |
| `session.send_rtvi(type, data)` | Sends a raw RTVI message to your app. |
| `session.end(reason)` | Hangs up. |

## The callbacks

| Callback | Returns | When it runs |
|---|---|---|
| `on_user_message` | speech (generator) | The user finished a turn. **Required.** |
| `on_user_idle` | speech (generator) | The user has been quiet; you may re-engage or end. |
| `on_session_start` | `None` | The session opened, before the greeting. Read `session.init` here. |
| `greet` | `str` or `None` | Once, for the first line. |
| `on_rtvi` | `None` | The user did something in your app ([Context and history](/build/brain/context/)). |
| `on_finalize` | `None` | A speech unit finished playing; reports what the user heard. |
| `on_error` | `None` | Voqalize sent a signal, such as `OVERLOAD`. |
| `on_session_end` | `None` | The socket is closing. |

Only the two generators can speak, so a click or an error never talks over the
user. Signatures and arguments are in the [Brain API](/reference/brain/).

## The greeting is a string, not a model call

`greet` returns a string or `None`. It is `async` so you can look something up
(for example in `session.init`), not so you can generate the sentence: the user
is connected and hearing nothing while it runs.

:::caution[Record what was heard, not what you generated]
Write `fin.heard` from `on_finalize` into your history. A reply that generated
three sentences and was cut after one must be remembered as one, or the model
refers to things the user never heard. Nothing logs this mistake.
[Transcripts and heard truth](/build/brain/transcripts/) shows how.
:::

## The brain pages, in order

1. [Speaking](/build/brain/speaking/): the speech frames, units, streaming and acknowledgements.
2. [Actions](/build/brain/actions/): put things on the user's screen.
3. [Tools](/build/brain/tools/): function calls on the shipped model brains, and the 20 ms budget.
4. [Context and history](/build/brain/context/): what the user does in your app, and `session.init`.
5. [Transcripts and heard truth](/build/brain/transcripts/): what goes into history.
6. [TypeScript types](/build/brain/typescript/): generate the browser half of actions and events.

Then [test it](/build/testing/) and [deploy it](/build/hosting/). Already have an
agent? [Use another agent framework](/build/existing-agent/).
