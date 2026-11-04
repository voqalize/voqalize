---
title: The avatar
description: An animated character drawn in the user's browser and lip-synced to the agent, from the session's own data channel. Talk to one on this page, then add it with one package and your client.
---

The avatar is an animated character drawn in the user's browser, in WebGL 2,
lip-synced to the agent's voice. Voqalize sends it what it needs on the session's
data channel, so there is no video track, no second media path and no extra
service. Adding it is a change to your page only.

Talk to one now. Pick a character, press **Talk to it**, and ask it how it
works: it answers out loud and scrolls this page to the section it is answering
from. The session lasts two minutes and needs your microphone.

<div id="avatar-live" class="not-content">
  <p>The live session needs JavaScript and a microphone. Everything it says is in the sections below.</p>
</div>

## How it works

Every Voqalize session already sends what the face needs: the state of the
session, any gesture your brain plays, and the mouth shapes (visemes) for each
reply, timed to the agent's audio. They travel as standard RTVI messages on the
data channel the session already has, at a few hundred bytes a second.

In the browser you give `@voqalize/avatar` your client and the name of a
character. It fetches the avatar runtime and that character from the avatar
host (`https://cdn.voqalize.com` from release 0.7) and draws the face in the
element you give it.

| Part | What it does |
|---|---|
| Voqalize | Sends the avatar's state and the mouth shapes for each reply, in every session. There is nothing to install or turn on. |
| `@voqalize/avatar` | The package you install from npm: a small MIT-licensed loader. You give it your client and a character name, and it mounts the face. |
| The avatar runtime | The renderer and the characters, fetched from the avatar host when a face mounts. Licensed separately, for use with Voqalize, under the [avatar runtime licence](https://cdn.voqalize.com/LICENSE). Each release of the package is pinned to the runtime it was released with, so upgrading the package upgrades the avatar. |

You need a page that runs Voqalize sessions with the client versions
[Client libraries](/build/client/#versions) pins, and a browser with WebGL 2.
React 18 or later is optional.

## Compared with video avatar services

HeyGen, Anam, Protoface, Simli and Tavus are video avatar services. One sits
after the TTS service in the pipeline: it sends the speech audio to its own
servers, renders a video of a face saying it, and sends the
video and the audio back through your transport. Voqalize already knows the
sounds in the audio it synthesizes, turns them into mouth shapes, and sends those
to the browser, which draws the face.

| | Video avatar services | The Voqalize avatar |
|---|---|---|
| What the browser receives | A video track, and the audio that came back with it | The session's audio, and a few hundred bytes a second of avatar messages |
| Where the face is rendered | On the service's servers | In the user's browser |
| Extra services | One hosted service, with its own account and API key | None |
| Running cost | The service's price for the minutes it renders | Nothing beyond the session |
| A different face | Created on the service's platform, then selected by id | A different character name |
| How it looks | Photoreal video of a person | An animated character, rendered in the browser |

Use a video avatar service if the face must look like real video. Use this
avatar if an animated character is enough and you want no extra service in the
audio path.

## Mount it in your page

```sh
npm install @voqalize/avatar
```

The package is ESM, has no runtime dependencies and ships its own types.
`@pipecat-ai/client-js` and React are optional peers.

Mount it where your page draws the agent's tile, with the client you
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
`destroy()` is safe to call at any time, including before the face has appeared.

Nothing in the transport changes. Leave `video_out_enabled`, the path for
server-rendered video avatars, off.

Optional gains, from `0` to `2` (`1` is as authored):

- `mouthGain`: how far the mouth moves.
- `gestureGain`: the size of nods and other gestures.
- `motionGain`: idle and speaking motion of the head, trunk and shoulders. It is
  `0.5` when the user's system asks for reduced motion.

### In React

```jsx
import { Avatar } from "@voqalize/avatar/react";

<Avatar client={pipecatClient} character="tara" className="agent-tile" />
```

Nothing mounts while `client` is `null`, and a new `client` or `character`
rebuilds the face. The gains are read when the face mounts. Other props go to
the `<div>` the face renders into.

### Build the face before the session

Building a face takes the browser a moment: the runtime, the character, a GPU
context and its shaders. On a slow phone that is more than a second. Start it
when the user is about to talk, for example on the page with the call button:

```js
import { preloadAvatar, unloadAvatar } from "@voqalize/avatar";

const face = preloadAvatar("tara");
// later, createAvatar({ ..., character: "tara" }) takes the prepared face
// or, if the user leaves without starting a session:
unloadAvatar(face);
```

- One face is held at a time. Preloading the same character again returns the
  same handle; preloading another frees the one held.
- A mount of that character, through `createAvatar` or `<Avatar>`, takes the
  face. After that, `unloadAvatar` on the handle does nothing.
- `face.ready` settles when the face is built, or when it cannot be (no WebGL 2,
  for example) and the mount will build it the ordinary way. You never need to
  wait for it before mounting. It rejects only for a name that is no character.

### Allow the avatar host

If your page sets a Content-Security-Policy, add the lines for the release of
`@voqalize/avatar` you install. Only the pages that mount a face need them.

**0.7 and later:**

```text
script-src  https://cdn.voqalize.com
connect-src https://cdn.voqalize.com
img-src     https://cdn.voqalize.com
```

The runtime is a module imported from that host, and it fetches the character
from it. The `img-src` host serves the still shown where a browser has no
WebGL 2. The runtime needs nothing else: no `blob:`, no workers, no inline
styles and no `eval`.

**Before 0.7:**

```text
script-src  https://avatar.voqalize.com
connect-src https://avatar.voqalize.com blob:
img-src     https://avatar.voqalize.com blob:
```

These releases also decode the character's textures from `blob:` URLs, and
`img-src blob:` is needed on Safari before 17 and Firefox before 98.

**Upgrading to 0.7:** upgrade the package first, then change the policy,
because a release before 0.7 imports its runtime only from
`avatar.voqalize.com`. The old policy keeps working with 0.7:
`avatar.voqalize.com` is another name for the same host, and a face refused on
one name loads from the other. To trial the new policy, send it as
`Content-Security-Policy-Report-Only` beside your current one.

<!--
Maintainers: delete "Before 0.7" and "Upgrading to 0.7" when releases before
0.7 are retired (avatar-private RELEASING.md, One host, two names), along with
the csp-check policies for them.
-->

## Choosing a character

A character is a name, passed as `character`. The picker at the top of this page
shows every character the current release mounts. Each release mounts a fixed
set, and `listCharacters()` returns it, so build a picker from it rather than
writing names down:

```js
import { listCharacters } from "@voqalize/avatar";

for (const c of await listCharacters()) {
  // c.name, c.still (an image URL), c.gender, c.age.min, c.age.max,
  // c.ethnicity[], c.tags[], c.suggestedVoices[], c.languages[]
}
```

The words in `gender`, `ethnicity` and `tags` come from closed lists, so a filter
you build from one call matches the next. `suggestedVoices` lists Voqalize voice
ids that suit the face, best first, such as `omnivoice/gauri`, and `languages`
the languages the first of them speaks, default first. Both are advice: the
avatar never speaks. Set the voice and the language of the session yourself, on
both legs; see [Voice and language](/build/voice-and-language/). The session on
this page sends the picked character and its first suggested voice to its brain
in `init`, and the brain configures that voice before its first word, which is
why the picker locks once the session starts.

The same list is in [the catalog](/reference/catalog/#avatar-characters), next
to the voices: `GET https://app.voqalize.com/api/v1/catalog.get` returns it as
`characters`, with each character's `suggested_voices` and `languages`, and
needs no key. Read it there when the choice is made on your server, or to match
a face to a voice that speaks the caller's language before anything mounts.

A name the runtime does not have mounts nothing: `createAvatar` still returns,
and the console error lists the names it does have. To change the face, pass
another name. In React the face is rebuilt; with `createAvatar`, destroy the old
one and create a new one. A page downloads only the characters it mounts.

## What it shows between turns

The face shows one state at a time. Speaking and listening come from the audio;
the states between turns are inferred. A face that goes idle while the agent is
still working can look like a dropped session.

| State | Where it comes from |
|---|---|
| `SPEAKING`, `LISTENING`, `MUTED`, `OFFLINE`, `DEGRADED` | Your client, in the browser. Voqalize sends nothing for these. |
| `THINKING` | Voqalize. It sees the user's turn end and knows a reply is due. |
| `WORKING` | Your brain, while a tool runs long enough for the user to notice. |
| `CANT_HEAR` | Your brain, when something it is waiting on has not responded. |

Blinking, breathing, gaze and idle movement are not states. The runtime
generates them in the browser, and nothing sends them.

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
composes with what Voqalize is doing. What the browser observes always wins: when
the agent starts speaking, the user starts speaking or the microphone is muted,
that is what the face shows.

A browser ignores a state or a gesture it does not recognise, so a newer brain
does not break an older page. It does not show the gesture either, so upgrade the
package before your brain relies on a gesture only a newer release has.

## How the mouth stays in sync

Each cue has a time, a mouth shape and an optional loudness. Time zero is the
first sample of the agent's reply audio, so a cue can arrive before or after the
audio it describes. Voqalize knows which sounds it spoke, and when, for every
sentence it synthesizes, and the mouth shapes are made from those. Audio is never
held back to wait for them.

The mouth follows the reply's audio as the browser receives it. It moves whenever
that audio arrives, even if the user has the volume down. The last batch of cues
for a reply means no more are coming, not that the audio has ended: the mouth
stops when the agent stops speaking.

## Limits

- **It is not photoreal.** The faces are animated characters. For photoreal
  video, use a video avatar service.
- **It needs a Voqalize session.** The mouth shapes and states come from
  Voqalize. There is no standalone player and no browser-only lipsync.
- **The page must reach the avatar host**, `cdn.voqalize.com` from 0.7. The
  runtime and the characters are fetched from there when the face mounts, and
  a strict Content-Security-Policy has to allow it.
- **It needs WebGL 2.** Without it, the tile shows a still photograph of the
  character, like a session whose other side has turned their camera off.

The [package README](https://github.com/voqalize/avatar/tree/main/packages/avatar#readme)
is the reference for every option.

## Read next

- [Client libraries](/build/client/): the client and transport in the browser.
- [RTVI messages](/reference/rtvi/): the messages that cross between your brain and the page.
