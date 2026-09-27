# L2 — the avatar

Read when: how the face is driven, cues, states, what it costs, licensing,
custom avatars, or using it without the rest of Voqalize.

## How it works

The avatar is **rendered on the viewer's device** from the audio plus a thin
stream of cues on the WebRTC data channel. There is no video track, no
server-side GPU render, and therefore no per-minute avatar charge.

The mouth shapes come from the sounds the voice actually spoke, and the mouth
follows the audio as the browser receives it.

## Mostly listening

The design claim the homepage section is built around: **a face on a call spends
most of its time not talking.** On the recording shown, the agent speaks for
**7.2 seconds of a 28-second call**. The rest is listening, nodding, holding
attention while the user talks or reads the screen. Idle behaviour is the hard
part; lip sync is the easy part everyone demos.

Faces shipping on the page: tanya (the one in the recording), tushar, tess, tara.

## Licence and packages

- The browser installs `@voqalize/avatar` from npm: a small **MIT** loader, source
  at `github.com/voqalize/avatar`. It takes the pipecat client and a character name.
- The avatar runtime and the characters (tanya, tess, tushar, tara, tanvi) are
  fetched from `avatar.voqalize.com` when the face mounts. They are Voqalize's,
  under their own licence, for use with Voqalize.
- A page with a Content-Security-Policy has to allow `avatar.voqalize.com`.

## Using it standalone

It is not built for that. The face is driven by the state and mouth shapes a
Voqalize session sends, so it needs a Voqalize call. The avatar is part of the
product, not a separate library.

## Custom avatars

An enterprise engagement — a customer's own presenter, brand character or
localized faces. We make the character; the page mounts it by name, like any
other.

## What it costs

Nothing extra. Because it renders on the device, the avatar does not appear as a
separate meter in the planned pricing. The planned unit is session time on the
voice plane, and the avatar is inside it.
