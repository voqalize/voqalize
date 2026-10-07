---
title: The avatar
description: A 2.5-D talking head driven by the data channel. Voqalize already sends what it needs in every session; the browser half is one package, and your brain can drive the face directly.
---

Every Voqalize session already sends avatar messages. Voqalize publishes what
the face needs on the call's data channel: the state it infers from turn and
tool-call boundaries, and mouth shapes (visemes) timed to the audio about to be
spoken. Those messages are on your data channel whether or not anything is
rendering them.

So adding a talking head is a browser-side change. There is no video track, no
per-minute avatar vendor, and no second media path.

## What it is

The face is lip-synced to the audio and state-aware: it knows when the user is
speaking, when it has been interrupted, when a tool call is running, and when
the microphone is muted. The mouth shapes come from the sounds the voice
actually spoke, and the mouth follows the audio as the browser receives it.

In the browser:

- **`@voqalize/avatar`**, on npm — a small MIT loader. You give it your
  `PipecatClient` and the name of a character.
- **The avatar runtime and the characters**, which the loader fetches from
  `https://avatar.voqalize.com` when the face mounts. They are licensed
  separately, for use with Voqalize, under the
  [avatar runtime licence](https://avatar.voqalize.com/LICENSE). Each release of
  the package is pinned to the runtime it was released with.

The Playground in the console renders one against a live call, so you can hear
and watch the thing before you install anything. So does
[the avatar demo](https://voqalize.com/demos/avatar), which is the avatar
explaining itself: it scrolls its own documentation to what you asked about
and demonstrates the gestures below on its own face.

## The browser half

```sh
npm install @voqalize/avatar
```

Mount it wherever your page already draws the bot's tile, passing the
`PipecatClient` you connected with — see
[connections and the handshake](/build/connect/):

```js
import { createAvatar } from '@voqalize/avatar';

const avatar = createAvatar({ mount: el, client: pipecatClient, character: 'tara' });
// avatar.destroy() when the tile goes away
```

`createAvatar` returns `{ destroy() }` and nothing else: the face reacts to the
client, so there is nothing to drive from the page and no state to read back.
It returns at once, and the face appears when the runtime and the character
have arrived.

In React, the same thing is a component:

```jsx
import { Avatar } from '@voqalize/avatar/react';

<Avatar client={pipecatClient} character="tara" className="call-tile" />
```

Nothing mounts while `client` is `null`, and a new `client` or `character`
rebuilds the face.

The browser needs WebGL 2. Without it, the tile shows a still picture of the
character, the way a call looks when the other side has turned their camera
off.

## Allow the avatar host

If your page sets a Content-Security-Policy, it has to let the runtime load and
fetch its character. Add these sources; `blob:` is there because the
character's textures are decoded from `blob:` URLs:

```text
script-src  https://avatar.voqalize.com
connect-src https://avatar.voqalize.com blob:
img-src     https://avatar.voqalize.com blob:
```

## Choosing a character

A character is a name, passed as `character`. Each is a 2.5-D character
rendered with WebGL, and you can meet them at
[voqalize.com/demos/avatar](https://voqalize.com/demos/avatar). A page
downloads only the character it mounts.

`listCharacters()` returns the characters the runtime has, each with its name,
a still image, descriptive tags and the voices that suit the face, best first.
Build a picker from it rather than writing the names down:

```ts
import { listCharacters } from "@voqalize/avatar";

const characters = await listCharacters();
const voice = characters[0].suggestedVoices[0]; // e.g. "omnivoice/gauri"
``` A name the runtime does not have logs
an error to the console and mounts nothing.

To change the face, pass another name. In React the face is rebuilt; with
`createAvatar`, destroy the old one and create a new one.

The [package README](https://github.com/voqalize/avatar/tree/main/packages/avatar#readme)
is the reference for the options, sizing and the React binding.

## Driving the face from your brain

The face takes its instructions from Voqalize, and a brain can add to them.
What a brain can ask for is a gesture: a nod, a receipt, a wait, a wave. It
goes out as an RTVI server message, which is on the
[RTVI whitelist](/reference/rtvi/), so it crosses without anything special.

**The action id is open, and these names are required of every character**:
`ACKNOWLEDGE` (the whole backchannel family in one word) and
`RESPONSE_INTERRUPTED`. Anything else belongs to the character that is mounted,
and a name it does not know is ignored rather than an error — so a brain can
address a motion only one character has without checking which one is on
screen.

**Send actions, and leave state alone.** An action is a point-in-time behaviour
that completes on its own and establishes no state — a nod, a receipt, a wait
gesture. A state is durable, one is in flight at a time, and a later one
replaces the earlier: Voqalize is already sending state, so state from your
brain is a race with it, and whichever arrives last wins. Actions compose with
what Voqalize is doing; state contests it.

There is a floor rule here too, and it is the same one everywhere else: an RTVI
message carries no audio, so `send_rtvi` needs no floor and can be called from
anywhere — including work that outlives the turn that started it. See
[parallel workstreams](/design/#parallel-workstreams).

## What the face is told, and what it decides

The face is told a state it may hold (thinking, working,
cannot hear you), a gesture that completes on its own, and a timeline of mouth
shapes for each reply. Voqalize sends the state and the mouth; a brain adds
gestures.

Observed playout outranks all of them. What pipecat reports about the audio —
that the bot started speaking, that the user did, that the microphone is muted
— is a fact, and a state the server sends is a candidate underneath it. The face
can be told what to consider; it cannot be told what is happening.

Blink, breath, gaze aversion and idle motion are the runtime's own and are
never sent.

## Read next

- [Client libraries](/build/pipecat/) — what in the call is pipecat's.
- [The RTVI plane](/reference/rtvi/) — the whitelist this rides.
