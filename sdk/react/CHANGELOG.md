# Changelog

All notable changes to `@voqalize/client-react`. This package is pre-1.0 and
still alpha: the API can break on a minor version.

**The numbering restarts at `0.0.1`.** The `0.1.0` in the manifest before this
was never published — the two applications that used the SDK copied its source
into their own tree, which is exactly the problem this release exists to end.
`0.0.1` is the first version anyone can `npm install`, and starting the public
series at the bottom says plainly that nothing here is promised yet.

## 0.0.1

First release published to npm: `npm install @voqalize/client-react`.

### Added

- **Microphone failures are now a state, not a silence.** A voice agent with no
  microphone is not a degraded call, it is a broken one: the agent greets, the
  caller answers, and nothing they say leaves the page. Every way of not getting
  a microphone is now a typed `MicrophoneError` — `denied`, `no-response`,
  `no-microphone`, `in-use`, `insecure-context` — carrying a message that tells
  the person in front of the browser what to do about it. Two failures that used
  to be invisible are now the loudest: an unanswered permission prompt (which
  never settles, so the caller hung on "Connecting…" forever) gets a hard
  deadline and an `awaiting-microphone` connection state, and a page served over
  plain `http://` — where `navigator.mediaDevices` is simply `undefined` — says
  so instead of reporting a generic failure.

  `awaiting-microphone` is its own connection state rather than a flavour of
  `connecting` because the two need opposite things from the user: one means
  wait, the other means *act*.

  The session handle carries the typed error through as `microphoneError`
  alongside the flat `error` string, so a page can tell "you blocked the
  microphone", which the caller fixes in one click, from "our service is down",
  which they cannot — and stop telling the first one to check their connection.

- **`<PreCallGate/>`** — the notice-and-consent screen shown before a microphone
  opens. Structure only; every word is yours, because what has to be disclosed is
  your call to make, not ours.

- **`<AmbientPresence/>`** — the full-viewport glow that makes the agent read as a
  property of the page rather than a widget in a corner. Neither component ships
  a stylesheet: drop them in and pass a palette.

- **`useUiCommand`** — dispatch the brain's `ui_command`s to typed per-action
  handlers instead of a hand-rolled switch, with the Python `Action` subclass as
  the source of truth for each shape. An action with no handler is not an error:
  the brain and the UI ship separately, and a new command reaching an old page
  must not break it.

- **Speaker selection actually routes.** The transport records the chosen output
  device but cannot play to it — routing is a property of the element doing the
  playing. `<VoqalAgent>`'s audio element now follows `selectedSpeaker` via
  `setSinkId`, feature-detected because Firefox and Safari do not have it.

### Fixed

- **A second microphone capture mid-call no longer mutes the caller.** Acquiring
  the microphone while a track is already live would replace the track the sender
  holds without ever attaching the new one, so the caller went silent with
  everything still reading as connected. `updateMic` remains the only supported
  way to swap devices mid-call.

- **Device changes are noticed on every path.** The `devicechange` watch was
  registered only by `initDevices`, so a caller who connected without it never
  learned about a headset plugged in mid-call. Both paths now start it, and
  starting it twice is a no-op.

- **A remount mid-handshake no longer leaves two live sessions.** The re-entry
  guard was the client ref, which is only set *after* the session is minted — so
  a teardown-and-remount inside that window (React StrictMode does exactly this
  in development) started a second session while the first was still in flight.
  A generation counter now lets the stale attempt notice it lost and bow out.

### Changed

- **Peer ranges widened, because a library that pins its host is not a library.**
  React `^18.2.0 || ^19.0.0`, `@pipecat-ai/client-js` `>=1.5.0 <2`,
  `@pipecat-ai/client-react` `>=1.1.0 <2`. The previous ranges demanded React 19
  and pipecat 1.7 for no reason the code could point at, which was enough on its
  own to keep an application on React 18 vendoring the source instead of
  installing it. The floor is the oldest combination we actually *run*, not the
  oldest that happens to compile, and the release job typechecks the source
  against exactly those versions on every publish.

  One consequence, and the only real one: the transport no longer writes the
  pipecat base class's `_maxMessageSize`, which does not exist below client-js
  1.7. It owns the `maxMessageSize` getter instead, and still reads the true SCTP
  limit off the connection rather than assuming 64 KiB. Nothing in pipecat
  enforces the field — it is advisory, surfaced to callers through that getter.

- Voice and language belong to the brain. The per-session `pipeline` override
  stays for pages that are genuinely the authority (a console auditioning voices,
  an A/B harness), but a brain that declares or configures a voice overrides it,
  and most pages should not set it at all.
