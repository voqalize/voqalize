---
title: The avatar
description: A lip-synced talking head drawn in the browser from the session's data channel. Add it with one package and your PipecatClient, choose a character, and let your brain send it gestures.
---

The avatar is a talking head drawn in the user's browser. Voqalize sends it what
it needs on the session's data channel: mouth shapes (visemes) timed to the audio
the agent speaks, and the state of the call (listening, thinking, interrupted).
There is no video track and no second media path, so adding it is a change to
your page only.

See it before you install anything: the console's Playground renders one on a
live session, and so does [the avatar demo](https://voqalize.com/demos/avatar),
where the avatar explains itself.

What ships:

- **`@voqalize/avatar`**, on npm: a small MIT-licensed loader. You give it your
  `PipecatClient` and the name of a character.
- **The avatar runtime and its characters**, which the loader fetches from
  `https://avatar.voqalize.com` when a face mounts. They are licensed separately,
  for use with Voqalize, under the
  [avatar runtime licence](https://avatar.voqalize.com/LICENSE). Each release of
  the package is pinned to the runtime it was released with, so upgrading the
  package upgrades the avatar.

## Mount it in your page

```sh
npm install @voqalize/avatar
```

Mount it where your page draws the agent's tile, with the `PipecatClient` you
connected ([Connect your app](/build/connect/)):

```js
import { createAvatar } from "@voqalize/avatar";

const avatar = createAvatar({
  mount: document.querySelector("#agent-tile"),
  client: pipecatClient,
  character: "tara",
});

// when the session ends, or the tile goes away
avatar.destroy();
```

`createAvatar` returns at once, and the face appears when the runtime and the
character have loaded. The avatar owns the contents of `mount` and sizes itself
to it. The face follows the client, so there is nothing to drive from the page.
`destroy()` is safe to call at any time.

In React:

```jsx
import { Avatar } from "@voqalize/avatar/react";

<Avatar client={pipecatClient} character="tara" className="agent-tile" />
```

Nothing mounts while `client` is `null`, and a new `client` or `character`
rebuilds the face. Other props go to the `<div>` the face renders into.

Optional gains, from `0` to `2` (`1` is as authored): `mouthGain`, `gestureGain`
and `motionGain`. `motionGain` defaults to `0.5` when the user's system asks for
reduced motion.

The face needs WebGL 2. Without it, the tile shows a still photograph of the
character, like a call whose other side has turned their camera off.

### Build the face before the session

Building a face takes a moment, more than a second on a slow phone. Start it
when the user is about to talk, for example on the page with the call button:

```js
import { preloadAvatar, unloadAvatar } from "@voqalize/avatar";

const face = preloadAvatar("tara");
// later, createAvatar({ ..., character: "tara" }) takes the prepared face
// or, if the user leaves without starting a session:
unloadAvatar(face);
```

One face is preloaded at a time, and you never need to wait for `face.ready`
before mounting.

## Allow the avatar host

If your page sets a Content-Security-Policy, add:

```text
script-src  https://avatar.voqalize.com
connect-src https://avatar.voqalize.com blob:
img-src     https://avatar.voqalize.com blob:
```

The runtime is a module loaded from that host, it fetches the character from it
and decodes the character's textures from `blob:` URLs. The `img-src` host serves
the no-WebGL still, and `img-src blob:` is needed on Safari before 17 and Firefox
before 98.

## Choosing a character

A character is a name, passed as `character`. Each package release mounts a
fixed set; `listCharacters()` returns it, so build a picker from it rather than
writing names down:

```js
import { listCharacters } from "@voqalize/avatar";

const characters = await listCharacters();
const { name, still, suggestedVoices, languages } = characters[0];
// suggestedVoices: voice ids that suit the face, best first, such as "omnivoice/gauri"
// languages: the languages the first suggested voice speaks, default first
```

`suggestedVoices` is advice: the avatar never speaks. Set the voice and the
language of the session yourself, on both legs; see
[Voice and language](/build/voice-and-language/).

A name the runtime does not have mounts nothing: `createAvatar` still returns,
and the console error lists the names it does have. To change the face, pass
another name. In React the face is rebuilt; with `createAvatar`, destroy the old
one and create a new one.

The [package README](https://github.com/voqalize/avatar/tree/main/packages/avatar#readme)
is the reference for every option.

## Gestures from your brain

Voqalize already sends the face its state and its mouth. Your brain can add
**gestures**: an action that plays once and completes on its own, such as a nod.
Send it as an RTVI server message, from anywhere in your brain, including a tool
or background work, since it carries no audio:

```python
from voqalize.sdk import RTVIType


def nod(session) -> None:
    session.send_rtvi(
        RTVIType.SERVER_MESSAGE,
        {"type": "avatar", "cmd": "action", "id": "ACKNOWLEDGE"},
    )
```

| Action id | Meaning |
|---|---|
| `ACKNOWLEDGE` | A backchannel: the face picks which nod or receipt. Every character has it. |
| `RESPONSE_INTERRUPTED` | The agent was cut off. Every character has it. |
| Any other id | Belongs to the character that is mounted. A character that does not know an id ignores it. |

**Send gestures, not state.** Voqalize is already sending the face's state, so a
state from your brain races it and the last one to arrive wins. A gesture
composes with what Voqalize is doing. Blinking, breathing and idle motion are the
runtime's own and are never sent.

## Read next

- [Client libraries](/build/pipecat/): what in the browser is pipecat's.
- [RTVI messages](/reference/rtvi/): the messages that cross between your brain and the page.
