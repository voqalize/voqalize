---
title: Error codes
description: Every error code on the wire, what raises it and whether the call survives it; the exceptions the SDK raises in your process; the refusals at sessions.connect; and the lines your user hears when your brain fails.
---

A code that ends the session and a code that refuses one request are different
failures. This page says which is which.

## The codes

`ErrorCode` is exported from `voqalize.sdk`, and these are all its members,
listed by value. In Python, compare members: `error.code is ErrorCode.OVERLOAD`.

| Code | Where it arrives | Fatal | What raises it |
|---|---|---|---|
| `protocol` | `on_error`, from Voqalize | No | Your brain sent something Voqalize refuses: an RTVI type the app owns, an RTVI payload over 64 KiB, a `SpeechStart` with no `speech_id`, or a `SpeechCancel` naming a unit the session never opened. |
| `wire_version` | sent by your SDK | **Yes** | `SessionStart` carried a wire version this SDK does not speak. |
| `rejected` | nowhere | — | Defined in the proto; nothing sends it. |
| `overload` | `on_error`, minted by your SDK | No | Your own SDK shed frames from a full queue. |
| `internal` | `on_error`, or sent by your SDK | Sometimes | From Voqalize: a language change did not land on the recognizer. From your SDK: `on_session_start` or `greet` raised. |
| `unsupported_voice` | `RequestRejected.code` | No | No voice by that id is served. |
| `unsupported_language` | `RequestRejected.code` | No | The voice does not speak the language, the recognizer does not hear it, or the tag is malformed. |
| `invalid_request` | `RequestRejected.code` | No | Anything else wrong with a `configure`: a language on one leg only, a patience off the scale, or one setting given both as a string and as an enum. |
| `unknown` | SDK only | — | Never sent. A code newer than your SDK reads as this. |

`fatal` is a separate field from the code, and it decides whether the call ends.
None of the codes that reach `on_error` arrives fatal, so `on_error` never has to
end a call.

```python
import logging

from voqalize.sdk import Brain, Error, ErrorCode

logger = logging.getLogger(__name__)


class Watchful(Brain):
    async def on_error(self, session, error: Error) -> None:
        if error.code is ErrorCode.OVERLOAD:
            logger.warning("session %s shed frames: %s", session.id, error.message)
        else:
            logger.error("session %s: %s %s", session.id, error.code, error.message)
```

### `protocol`

Voqalize drops the one thing your brain sent and keeps the call running. A
`SpeechChunk` or `SpeechEnd` for a unit you already cancelled is not a protocol
error: it is ignored, because a model may still be streaming when the cancel
goes out.

The SDK catches most of these before they reach the socket: `send_rtvi` raises
`WireError` for a type outside the sendable set, and `cancel_speech` raises
`ValueError` for an unknown id. So a `protocol` error in your logs usually means
an oversized payload. See [RTVI messages](/reference/rtvi/) for the whitelist
and [Actions](/build/brain/actions/) for keeping payloads small.

### `wire_version`

Voqalize stamps its wire version on `SessionStart`. If it is not the version
your SDK speaks, higher or lower, the SDK sends a fatal `wire_version` error and
ends the session before `greet` runs, so the user has heard nothing. You do not
write this check. The current version is in [The wire](/reference/wire/#version).

### `rejected`

Nothing Voqalize or the SDK sends carries this code: a disallowed or oversized
RTVI message comes back as `protocol`. Handle it only if you write directly
against the wire and want to be exhaustive over the enum.

### `overload`

Your SDK holds a priority queue and a bulk queue each way, and the bulk queue holds
256 frames by default. When it fills, the newest droppable frames are shed
(speech chunks and RTVI messages) and one non-fatal `overload` error goes to
`on_error`, not one per dropped frame.

It never crosses the wire. The message reads `inbound queue full` or
`outbound queue full`, which says which side of your brain is behind. A user
message is never shed, and a drop never ends the session.

### `internal`

**From Voqalize:** a language change did not land on the recognizer, so the
session is still listening in the language it was. The error names that
language and is not fatal: your `configure` was already answered accepted, and
this is the correction behind it.

**From your SDK:** `on_session_start` or `greet` raised. The SDK sends a
**fatal** `internal` error naming the hook and ends the session without
greeting, and the browser's `onError` shows it. An exception in any later
callback (`on_user_message`, `on_user_idle`, `on_rtvi`, `on_finalize`) is logged
in your process and goes no further: that turn produces nothing, and the next
turn runs. What the user hears then is [below](#what-your-user-hears).

## A rejected request comes back on the request

`RequestRejected` does not arrive at `on_error`. It is raised by the `await` on
the request that was refused:

```python
import logging

from voqalize.sdk import Brain, RequestRejected, SpeechChunk, SpeechEnd, SpeechStart
from voqalize.sdk.wire import Config, SttConfig, TtsConfig

logger = logging.getLogger(__name__)


class Switcher(Brain):
    async def on_user_message(self, session, msg):
        yield SpeechStart()
        yield SpeechChunk("Switching to Assamese.")
        yield SpeechEnd()
        try:
            await session.configure(
                Config(stt=SttConfig(language="as"), tts=TtsConfig(language="as"))
            )
        except RequestRejected as rejected:
            logger.info("configure refused (%s): %s", rejected.code, rejected.detail)
            yield SpeechStart()
            yield SpeechChunk("I will listen in Assamese and answer in Hindi.")
            yield SpeechEnd()
            await session.configure(
                Config(stt=SttConfig(language="as"), tts=TtsConfig(language="hi"))
            )
```

Speak before you await: the `configure` is a round trip, and an `await` with no
speech in front of it is silence the user sits in.

**A rejection is all-or-nothing.** Nothing in the request applied, so the
previous settings are still in force and the call carries on. `rejected.op` is
the operation, `rejected.detail` is Voqalize's own sentence, written to be shown,
and `rejected.code` is `ErrorCode.UNSUPPORTED_VOICE`,
`ErrorCode.UNSUPPORTED_LANGUAGE` or `ErrorCode.INVALID_REQUEST` (`None` if
Voqalize did not say).

The refusal to plan for is a `tts.language` the chosen voice does not speak. The
languages each voice speaks are in [the catalog](/reference/catalog/).

What is *not* a `RequestRejected`:

- **A configuration the SDK refuses itself** raises `ConfigError` at the call
  site, before anything is sent: a language named on one leg only, a patience
  off the scale, or an empty string. Import it from `voqalize.sdk.wire`.
- **No answer within 10 seconds** raises `TimeoutError`; whether the change
  applied is unknown, and the session lives. An accepted answer means the
  configuration was legal and is being applied. If the recognizer then fails to
  switch, an `internal` error follows.

## Exceptions raised in your process

None of them crosses the wire.

| Exception | Raised when | What to do |
|---|---|---|
| `WireError` | Your brain broke a wire obligation: an unbalanced speech bracket, `send_rtvi` with a type the app originates, or a `yield` in `on_rtvi`. Inside a turn it is caught and logged and the turn ends; from `send_rtvi` it reaches your code. | See [Speaking](/build/brain/speaking/). |
| `Unsupported` | You called something this session did not advertise: `cancel_speech` without `can_cancel_speech`, a string voice or language without `can_configure_strings`, or `report_step` without `can_report_steps`. Raised before anything is sent. `capability` names what was missing. | Check the property first. See [stopping your own speech](/build/brain/speaking/#stopping-your-own-speech). |
| `SessionRejected` | The token on an incoming socket failed verification. `run_session` raises it before your brain is built. | Close the socket with code **4000**. See [Deploy the brain](/build/hosting/#a-route-voqalize-dials). |

## Refused before your brain is dialled

These refuse a session before there is a socket, so your brain sees nothing.
Look at the response to `sessions.connect`; its envelope is in
[Connect your app](/build/connect/#when-it-fails).

| Status | `code` | Cause | Fix |
|---|---|---|---|
| `400` | `invalid_config` | `config` has an unknown field or a wrong type, or an off-scale `stt.patience`. The message names the field. | Fix the field. `config` is parsed as canonical proto3 JSON. |
| `400` | `invalid_config`, with `details.code` `unsupported_voice` or `unsupported_language` | A voice Voqalize does not serve, a `tts.language` the voice does not speak, or an `stt.language` the recognizer does not hear. The message names what is served. | Pick values from [the catalog](/reference/catalog/). |
| `400` | `recording_not_permitted` | `config.record: true` on a `pk_` key. | Record through the agent default or from your server ([Recordings](/operate/recordings/#a-publishable-key-can-turn-recording-off-not-on)). |
| `401` | `not_authenticated` | No `Authorization` header, a value that is not an `sk_` or `pk_` key, or a revoked key. | Send a live key for this agent. |
| `403` | `origin_not_allowed` | A `pk_` from an origin not on its list, or with no `Origin` header. The message names the origin it saw, never the allowed ones. | Add the origin to the key, or call from your server with an `sk_` ([Keys](/build/keys/#publishable-keys-pk_)). |
| `404` | `not_found` | No such agent for this key. Each key names exactly one agent. | Use that agent's key. |
| `409` | `agent_not_configured` | The agent has no `brain_url` and no Cortex credentials. | Set a `brain_url` for an [inbound route](/build/hosting/#a-route-voqalize-dials), or mint credentials to [dial out over Cortex](/build/hosting/#a-brain-that-dials-out). |
| `409` | `agent_archived` | The agent is archived. Sessions in progress continue. | Unarchive it; its existing credentials work again. |
| `422` | `validation_error` | The body has an undeclared key or a wrong type. The message names the field. | Fix the body. |
| `429` | `rate_limited` | Your tenant sent too many requests. | Wait for the `Retry-After` header's seconds, then retry. |
| `500` | | A Voqalize error. | Retry; quote `correlation_id` if it persists. |

A language on one leg only passes `sessions.connect` and is refused at the
offer: `client.connect` rejects with `400 invalid_config` and an `info`
sentence ([Voice and language](/build/voice-and-language/#when-a-configuration-is-refused)).
The voice and its languages are checked with the same rules as your brain's
`configure`, so an unservable `tts.language` is refused at connect when the
connect `config` set it, and comes back as `RequestRejected` when your brain set
it: same rule, same words.

Nothing substitutes for a voice or a language. A voice id or tag Voqalize does
not serve is refused, wherever it came from.

## What your user hears

Voqalize speaks two fixed lines of its own, in the call's language where it has
them. Your brain is not told either was spoken, and its `Finalize` reports carry
only your own words.

**A brain it could not reach.** Voqalize retries the first connect from 100 ms
and gives up after **10 seconds**. Then the user hears (in English):

> Sorry, I'm having trouble connecting right now. Please try again in a bit.

Six seconds later the session ends, as `brain_unreachable`. This plays when your
service is down, the URL is wrong, TLS fails, or the handshake answers `401` or
`403`. A brain that accepts the socket and then closes it, with **4000** or any
other code, ends the session at once, as `brain_disconnected`, with no line.

**A turn that produced no speech.** Once a user message reaches your brain,
Voqalize starts a **10-second** watchdog. If the turn has sent no `SpeechChunk`
by then, the user hears:

> Sorry — that's taking longer than I expected.

**The session stays up**, and the next turn may be fine. The watchdog is
disarmed by your brain's first `SpeechChunk` for that turn and by a barge-in, and a
`UserIdle` never arms it. The common way to trip it is a turn whose only output
is a tool call ([Tools](/build/brain/tools/#speak-first-and-call-in-the-same-response)).
A callback that raises, returns nothing or hangs all land here.

Which one it was is in the session's [record and logs](/operate/reading-a-call/).

## Read next

- [Troubleshooting](/operate/troubleshooting/): symptoms, causes and fixes.
- [Reading a call back](/operate/reading-a-call/): finding the failure afterwards.
- [The wire](/reference/wire/): the frames that carry a code.
