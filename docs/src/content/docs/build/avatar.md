---
title: The avatar
description: A 2-D talking head driven by the data channel. The pipeline half already runs in your session; the browser half is one package, and your brain can drive the face directly.
---

Every Voqalize session already emits avatar traffic. `AvatarProcessor` sits in
the voice tier's pipeline between text-to-speech and the transport, and from that
seat it publishes what the face needs: the state it infers from turn and
function-call boundaries, and viseme cues aligned to the audio about to be
spoken. Those messages are on your data channel whether or not anything is
rendering them.

So adding a talking head is a browser-side change. There is no video track, no
per-minute avatar vendor, and no second media path.

## What it is

[`voqalize/avatar`](https://github.com/voqalize/avatar) is a separate,
MIT-licensed library — `@voqalize/avatar` on npm and `voqalize-avatar` on PyPI,
two ends of one wire format that publish in lockstep. It works against any
pipecat pipeline, and the Voqalize runtime is one consumer of it.

The face is lip-synced to the audio and state-aware: it knows when the caller is
speaking, when it has been interrupted, when a tool call is running, and when
the microphone is muted. Most of that comes from frames a pipecat pipeline
already emits, which is why the integration takes an argument at neither end.

The Playground in the console renders one against a live call, so you can hear
and watch the thing before you install anything. So does
[the avatar demo](https://voqalize.com/demos/avatar), which is the library
explaining itself: it brings the architecture up on screen, demonstrates the
three commands below on its own face, and changes which avatar it is while you
watch.

## The browser half

```sh
npm install @voqalize/avatar
```

Then mount it wherever your page already draws the bot's tile, passing the
`PipecatClient` you connected with — see
[connections and the handshake](/build/connect/).

The package's own README is the reference for the mount call, the faces that
ship with it, and how to author your own. We link rather than quote it: the
browser surface changes in the next release, and a copy of an API here is a copy
that goes stale in a place you cannot see it change.

## Driving the face from your brain

The avatar reads one envelope, and it accepts it from any source — the
processor in the voice tier's pipeline and a brain sending out of band emit the
same shape:

```python
session.send_rtvi(
    RTVIType.SERVER_MESSAGE,
    {"type": "avatar", "cmd": "action", "id": "GESTURE_GREET"},
)
```

`server-message` is on the [RTVI whitelist](/reference/rtvi/), so this
crosses without anything special. The action ids are the avatar library's, and
[`contract-wire.md`](https://github.com/voqalize/avatar/blob/main/docs/contract-wire.md)
is the list of record.

**Send actions, and leave claims alone.** An action is a point-in-time behaviour
that completes on its own and establishes no state — a nod, a greeting, a wait
gesture. A `claim` is durable, one is in flight at a time, and a later one
replaces the earlier: the voice tier's processor is already claiming, so a claim
from your brain is a race with it, and whichever arrives last wins. Actions
compose with what the processor is doing; claims contest it.

There is a floor rule here too, and it is the same one everywhere else: an RTVI
message carries no audio, so `send_rtvi` needs no floor and can be called from
anywhere — including work that outlives the turn that started it. See
[parallel workstreams](/design/parallel-workstreams/).

## What the face is told, and what it decides

Three commands cross: a `claim` (a candidate durable state), an `action`
(one self-completing behaviour), and `cues` (a viseme splice correlated to a
text-to-speech context).

Observed playout outranks all of them. What pipecat reports about the audio —
that the bot started speaking, that the caller did, that the microphone is muted
— is a fact, and a server claim is a candidate underneath it. The face can be
told what to consider; it cannot be told what is happening.

Blink, breath, gaze aversion and idle motion are the renderer's own and are
never sent.

## Read next

- [Voqalize and pipecat](/build/pipecat/) — where the processor sits, and what else in the call is pipecat's.
- [The RTVI plane](/reference/rtvi/) — the whitelist this rides.
