# L2 — the avatar

Read when: how the face is driven, cues, states, what it costs, custom avatars,
or using it without the rest of Voqalize.

## How it works

The avatar is **rendered on the viewer's device** from the audio plus a thin
stream of cues on the WebRTC data channel. There is no video track, no
server-side GPU render, and therefore no per-minute avatar charge.

A photograph is projected onto shallow geometry; eyes, teeth and the lip line are
geometry rather than painted frames, which is what lets it hold a gaze and close
a mouth convincingly at small sizes.

## Mostly listening

The design claim the homepage section is built around: **a face on a call spends
most of its time not talking.** On the recording shown, the agent speaks for
**7.2 seconds of a 28-second call**. The rest is listening, nodding, holding
attention while the user talks or reads the screen. Idle behaviour is the hard
part; lip sync is the easy part everyone demos.

Faces shipping on the page: tanya (the one in the recording), tushar, tess, tara.

## Licence and packages

- Library: **MIT**. `@voqalize/avatar` on npm, `voqalize-avatar` on PyPI, source
  at `github.com/voqalize/avatar`.
- Line-art and painted faces: **MIT**, no attribution.
- Character binaries for the 2.5-D faces (tara, tushar, tanya, tess): **CC-BY 4.0**.

## Using it standalone

Nothing stops it, and nothing is meant to. It works with **any pipecat agent** —
it takes audio and cues, not a Voqalize session. Shipping it MIT is deliberate:
the avatar is not the moat, the voice tier underneath is, and a widely used
avatar library is worth more to us than a gated one.

## Custom avatars

An enterprise engagement — a customer's own presenter, brand character or
localized faces. The pipeline that turns a photograph into a driven face is
private tooling; the runtime that plays the result is the MIT library.

## What it costs

Nothing extra. Because it renders on the device, the avatar does not appear as a
separate meter in the planned pricing. The planned unit is session time on the
voice plane, and the avatar is inside it.
