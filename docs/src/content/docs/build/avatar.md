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

[`voqalize/avatar`](https://github.com/voqalize/avatar) is a separate library
— `@voqalize/avatar` on npm and `voqalize-avatar` on PyPI, each end of one wire
format. They version independently and the wire is what keeps them compatible.
It works against any pipecat pipeline, and Voqalize is one consumer of it.

The licence follows the kind of avatar. The code, the SVG faces and the
Canvas2D identities are MIT and ask for no attribution. The 2.5-D characters'
`.glb` files are artwork under CC-BY 4.0: use them commercially and modified, and
credit Voqalize with the line in the package's `assets/README.md`. The npm
manifest declares `MIT AND CC-BY-4.0`, so that is what a licence scanner reports
whether or not you import a character.

The face is lip-synced to the audio and state-aware: it knows when the user is
speaking, when it has been interrupted, when a tool call is running, and when
the microphone is muted. Most of that comes from frames a pipecat pipeline
already emits, which is why the integration takes an argument at neither end.

The Playground in the console renders one against a live call, so you can hear
and watch the thing before you install anything. So does
[the avatar demo](https://voqalize.com/demos/avatar), which is the library
explaining itself: it brings the architecture up on screen, demonstrates the
commands below on its own face, and changes which avatar it is while you
watch.

## The browser half

```sh
npm install @voqalize/avatar three   # three only for a 2.5-D character
```

Mount it wherever your page already draws the bot's tile, passing the
`PipecatClient` you connected with — see
[connections and the handshake](/build/connect/):

```js
import { createAvatar } from '@voqalize/avatar/avatars/tara';

const avatar = createAvatar({ mount: el, client: pipecatClient });
// avatar.destroy() when the tile goes away
```

`createAvatar` returns `{ destroy() }` and nothing else: the face reacts to the
client, so there is nothing to drive from the page and no state to read back.

## Choosing an avatar

Each avatar is its own entry point, so a page downloads only the one it imports.

- **2.5-D characters** — `tara`, `tushar`, `tanya`, `tess`, each at
  `@voqalize/avatar/avatars/<name>`. A photograph projected onto shallow
  geometry, with the eyes, teeth and lip line built as geometry so they can move.
  `three` is an optional peer that only these entry points reach, and the `.glb`
  is fetched when the avatar mounts.
- **SVG faces** — `peep`, `wren`, `myna`: hand-drawn line art. The bare
  `@voqalize/avatar` import mounts `peep`; for another, import its value from
  `@voqalize/avatar/faces/<name>` and pass it as `face`.
- **Canvas2D identities** — `arjun`, `meera`, `vikram`, `ishita`, `kabir`,
  `naina`. Frozen, and removed in 0.5.0; do not start a page on one.

The [package README](https://github.com/voqalize/avatar/tree/main/packages/avatar#readme)
is the reference for the React binding, the supported `three` range, sizing, and
authoring an avatar of your own.

## Driving the face from your brain

The avatar reads one envelope, and it accepts it from any source — the
processor in the voice tier's pipeline and a brain sending out of band emit the
same shape:

```python
session.send_rtvi(
    RTVIType.SERVER_MESSAGE,
    {"type": "avatar", "cmd": "action", "id": "ACKNOWLEDGE"},
)
```

`server-message` is on the [RTVI whitelist](/reference/rtvi/), so this
crosses without anything special. The action ids are the avatar library's, and
[`contract-wire.md`](https://github.com/voqalize/avatar/blob/main/docs/contract-wire.md)
is the list of record.

**The action id is open, and these names are required of every face**:
`ACKNOWLEDGE` (the whole backchannel family in one word) and
`RESPONSE_INTERRUPTED`. Anything else belongs to the face that is mounted, and a
name it does not know is ignored rather than an error — so a brain can address a
motion only one avatar has without checking which one is on screen.

**Send actions, and leave state alone.** An action is a point-in-time behaviour
that completes on its own and establishes no state — a nod, a receipt, a wait
gesture. A `state` is durable, one is in flight at a time, and a later one
replaces the earlier: the voice tier's processor is already sending state, so
state from your brain is a race with it, and whichever arrives last wins. Actions
compose with what the processor is doing; state contests it.

There is a floor rule here too, and it is the same one everywhere else: an RTVI
message carries no audio, so `send_rtvi` needs no floor and can be called from
anywhere — including work that outlives the turn that started it. See
[parallel workstreams](/design/#parallel-workstreams).

## What the face is told, and what it decides

What crosses is a `state` (a candidate durable state, `null` to clear it), an
`action` (one self-completing behaviour), and `cues` (a viseme splice correlated
to a text-to-speech context). `state` was spelled `claim` on the wire
before the published line began, and the browser still accepts that spelling at
its parse boundary for a server that has not moved; it comes out when the last
one that sends it has shipped.

Observed playout outranks all of them. What pipecat reports about the audio —
that the bot started speaking, that the user did, that the microphone is muted
— is a fact, and a state the server sends is a candidate underneath it. The face can be
told what to consider; it cannot be told what is happening.

Blink, breath, gaze aversion and idle motion are the renderer's own and are
never sent.

## Read next

- [Voqalize and pipecat](/build/pipecat/) — where the processor sits, and what else in the call is pipecat's.
- [The RTVI plane](/reference/rtvi/) — the whitelist this rides.
