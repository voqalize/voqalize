---
title: Voice and language
description: Choose a session's voice and language at connect or from the brain, always on both legs; switch mid-session; tune turn-taking with stt.patience, idle.timeout_ms and ack; and handle the refusals.
---

Voice, language and turn-taking are set **per session**, never on the agent. You
set them in one of two places, and the later one wins:

1. **At connect**, in `config` on `sessions.connect`, when your server (or page)
   already knows the user's language.
2. **From the brain**, with `await session.configure(Config(...))`, in
   `on_session_start` (it lands before the greeting) or at any point later.

A session with no configuration speaks and listens in English, with ack on and
idle detection off. The values each setting accepts (every voice, every
language) are in the [Voice and language catalog](/reference/catalog/).

## Set the voice and language

At connect, from your server:

```json
{
  "agent_id": "agt_…",
  "config": {
    "tts": { "voice": "omnivoice/gauri", "language": "ta" },
    "stt": { "language": "ta" }
  }
}
```

From the brain, in `on_session_start`:

```python
from voqalize.sdk import Brain
from voqalize.sdk.wire import Config, SttConfig, TtsConfig


class MyBrain(Brain):
    async def on_session_start(self, session):
        await session.configure(
            Config(
                stt=SttConfig(language="ta"),
                tts=TtsConfig(language="ta", voice="omnivoice/gauri"),
            )
        )
```

A voice is its id (`omnivoice/gauri`) and a language its BCP-47 tag (`ta`,
`en-IN`); a tag is matched by the part before the first hyphen. The older
`Voice` and `Language` enums still work and are deprecated
([the catalog](/reference/catalog/) has the details).

### Always set both legs

`stt.language` picks the **recognizer**. `tts.language` picks the language the
voice reads in, which for a cloned voice is a different recorded speaker. Moving
one without the other is silent: the words stay right and only the speaker is
wrong, so no transcript or log shows it. Name a language on one leg and you must
name it on the other.

The two may differ. A voice speaks fewer languages than the recognizer hears, so
to understand Odia and answer with the Hindi voice, say exactly that:

```python
Config(
    stt=SttConfig(language="or"),                            # hear Odia
    tts=TtsConfig(language="hi", voice="omnivoice/gauri"),   # speak Hindi
)
```

Changing only the voice touches no language field and needs no pair.

### A worked example: language from `init`

The `lead_qual` demo ([Examples](/overview/examples/)) is a gold-loan call whose
enquiry form names the user's state. Its server passes the form as `init`, and
its brain picks the language from it before the first word. In outline:

```python
from voqalize.sdk import Brain
from voqalize.sdk.wire import Config, SttConfig, TtsConfig

STATE_LANGUAGE = {"Tamil Nadu": "ta", "Karnataka": "kn", "Maharashtra": "mr"}


class LeadQual(Brain):
    async def on_session_start(self, session):
        state = str((session.init or {}).get("state", ""))
        tag = STATE_LANGUAGE.get(state, "hi")
        await session.configure(
            Config(
                stt=SttConfig(language=tag),
                tts=TtsConfig(language=tag, voice="omnivoice/gauri"),
            )
        )
```

## Switch mid-session

Send another `configure` with both legs. Expose it to the model as a tool and
start the request in the background, because a tool returns within 20 ms
([Tools](/build/brain/tools/#a-tool-returns-within-20-ms)):

```python
import asyncio
from typing import Literal

from google import genai
from pydantic import BaseModel, Field
from voqalize.sdk.gemini import GeminiBrain
from voqalize.sdk.wire import Config, SttConfig, TtsConfig


def both_legs(tag: str) -> Config:
    return Config(
        stt=SttConfig(language=tag),
        tts=TtsConfig(language=tag, voice="omnivoice/gauri"),
    )


class SwitchLanguage(BaseModel):
    """The language to continue in."""

    language: Literal["en", "hi", "ta"] = Field(description="BCP-47 tag.")


class Desk(GeminiBrain):
    def __init__(self) -> None:
        super().__init__(
            client=genai.Client(),
            system_instruction="You are a helpful support agent. Answer in a sentence or two.",
        )
        self._pending: set[asyncio.Task[None]] = set()

    async def on_session_start(self, session):
        await session.configure(both_legs("en"))

    @property
    def tools(self):
        return [self.switch_language]

    async def switch_language(self, args: SwitchLanguage) -> str:
        """Switch the conversation language when the user asks for another one.
        In the same response, say one short line in the current language."""
        task = asyncio.create_task(self.session.configure(both_legs(args.language)))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)
        return f"switched to {args.language}"
```

A change is accepted whole or not at all, and each part lands at its own point:

| Setting | Takes effect |
|---|---|
| `tts` (voice, language) | From the next speech unit. The sentence being spoken finishes in the old voice. |
| `stt.language` | Once the turn in progress ends. That turn is transcribed as it was spoken. |
| `stt.patience` | At once, including the pause in progress. |
| `idle.timeout_ms` | At once; a running timer restarts on the new value. |
| `ack.enabled` | From the next turn. |

So the line said with the switch is spoken in the old voice, and the user's next
turn is heard in the new language.

## Tune turn-taking

| Setting | Values | Default |
|---|---|---|
| `stt.patience` | `0` to `10`: how long the recognizer waits through a pause before it decides the user has finished | `7` |
| `idle.timeout_ms` | `0` (off) to `300000` | `0`: `on_user_idle` never fires |
| `ack.enabled` | `true` or `false` | `true` |

All three go in the same `Config` (and the same `config` at connect), with or
without a language.

**`stt.patience`** is a scale, not a duration. Raise it for users who pause
mid-thought (reading out a number, or speaking a second language); lower it for
quick back-and-forth. Each step up waits longer on every turn.

```python
await session.configure(Config(stt=SttConfig(patience=9)))
```

**`idle.timeout_ms`** is how long after the agent stops speaking a silent user
waits before your brain gets `on_user_idle`, to re-engage or end the session
([The brain](/build/brain/)).

```python
from voqalize.sdk.wire import Config, IdleConfig

await session.configure(Config(idle=IdleConfig(timeout_ms=15000)))
```

**`ack`** is Voqalize's own short acknowledgement ("Sure.", "Let me check.")
said when the user's turn ends and before your reply starts. It is said only in
the languages Voqalize has acknowledgements for. Keep it on and never write a
filler line of your own; turn it off only when your brain writes its own
acknowledgements ([Speaking](/build/brain/speaking/#voqalize-covers-the-wait-before-your-first-word)):

```python
from voqalize.sdk.wire import AckConfig, Config

await session.configure(Config(ack=AckConfig(enabled=False)))
```

At connect, the same settings are
`"stt": {"patience": 9}`, `"idle": {"timeout_ms": 15000}` and
`"ack": {"enabled": false}`.

## When a configuration is refused

A voice that does not speak the language, or a language the recognizer does not
hear, is refused. Voqalize never substitutes another.

| Where | What you get |
|---|---|
| Building `Config` in the SDK | `ConfigError`, before anything is sent: a language on one leg only, or `patience` outside `0` to `10`. |
| `sessions.connect` | `400 invalid_config`, with `details.code` `unsupported_voice` or `unsupported_language` and a message naming what is served. |
| `client.connect` in the page | `400 invalid_config` at the offer, with an `info` sentence, for a connect `config` Voqalize cannot run (for example a language on one leg only). |
| `session.configure` mid-session | `RequestRejected`, with `.code` `UNSUPPORTED_VOICE`, `UNSUPPORTED_LANGUAGE` or `INVALID_REQUEST` and the reason in `.detail`. Nothing in the request applied. |

```python
import logging

from voqalize.sdk import RequestRejected
from voqalize.sdk.wire import Config, SttConfig, TtsConfig

log = logging.getLogger(__name__)


async def switch_to_tamil(session) -> None:
    try:
        await session.configure(
            Config(stt=SttConfig(language="ta"), tts=TtsConfig(language="ta"))
        )
    except RequestRejected as e:
        log.warning("language not switched (%s): %s", e.code, e.detail)  # nothing changed
```

[Error codes](/reference/errors/#a-rejected-request-comes-back-on-the-request)
has the full list.

## Read next

- [Voice and language catalog](/reference/catalog/): every voice and the languages each one speaks.
- [Speaking](/build/brain/speaking/): what your brain says, and when.
- [Connect your app](/build/connect/): the connect request that carries `config`.
