# Changelog

All notable changes to `@voqalize/client-react`. This package is pre-1.0 and
still alpha: the API can break on a minor version.

**The numbering restarts at `0.0.1`.** The `0.1.0` in the manifest before this
was never published — the two applications that used the SDK copied its source
into their own tree, which is exactly the problem this release exists to end.
`0.0.1` is the first version anyone can `npm install`, and starting the public
series at the bottom says plainly that nothing here is promised yet.

## 0.2.0

Follows the control plane's one-entity rename: a call is a **session**, and
there is no longer a Meeting above it.

> **Staged, not published.** The version is bumped and the code is on `wire-v2`,
> but no `react-sdk-v0.2.0` tag has been cut, so npm still serves `0.1.1`. Held
> deliberately: the brain SDK is still moving, and patterns are still being
> lifted out of the demos into this package. Publishing now would freeze a
> surface we expect to widen, and every prior publish is a compatibility
> promise we would have to keep. The demos are unaffected — their build
> overlays this working tree over whatever the registry gave them. Cut the tag
> when the shape settles; until then this section is the record of what is
> already true in the source.

### Added

- **`record` on `createSession`, `useVoqalSession` and `<VoqalAgent>`.** Whether
  this one call is recorded. Omit it and the agent's stored default decides,
  which is off unless someone turned it on. The page is the only party that
  knows whether *this* caller consented — `PreCallGate` is where that is
  collected — so this is where it is reported, and `false` is always honoured
  even for an agent that records by default.

  `true` is refused on a publishable key, and the refusal is the reason this
  landed as more than a field. A `pk_` key ships in page source, so anything
  holding it could otherwise write voice into your storage, on your bill, for an
  agent whose owner chose not to record. The server has always refused it; what
  it could not do is make the refusal audible, because the call it answers with
  is a working one — it connects, it greets, and it keeps no audio. The response
  carries `recording_enabled`, so `createSession` now compares what it asked for
  against what it got and warns on the console when they differ. Turn recording
  on where its owner controls it: the agent's own default, over MCP
  (`update_agent(recording=true)`) or in the console.

  It sits on the publishable-key arm of the options union only. When your own
  backend mints the session, recording is decided there, on a credential that is
  trusted to turn it on.

### Changed — requires a control plane deployed on or after 2026-08-20

- **The bootstrap call is now `POST {apiBase}/sessions.create`.**
  `sessions.create_and_start` is gone from the server, not deprecated on it —
  the two-step create-then-start it was named for had already collapsed into one
  call, and the state between the steps was one nothing guarded. `0.1.1` and
  earlier get a 404 from a current control plane; there is no version of this
  package that talks to both.

- **The request body sends `agent_input` where it sent `payload`.** Same
  contents — `{ pipeline, payload }` — under the name the server now stores it
  by. This one matters more than a rename usually would: unknown fields are
  ignored rather than rejected, so an old client posting to a URL alias would
  have been answered `200` with its pipeline overrides and its brain context
  silently dropped. A 404 is the better failure, which is part of why no alias
  exists.

**Nothing existing changed shape.** `createSession`, `useVoqalSession` and
`<VoqalAgent>` take and return what they did in `0.1.1` — `pipeline` and
`payload` are still the prop names, and `record` above is additive and optional.
An application that upgrades the package and redeploys against a current control
plane needs no source edit.

### Documented

- `payload` is **persisted on the session**, not just signed into the session
  token, so that "what did the page actually send?" is answerable after the
  token expires. Anyone who can read the session can read it. Send identifiers,
  not personal data.

## 0.1.1

Widens the pipecat peer range. No source change; `dist` is byte-identical.

### Changed

- **`@pipecat-ai/client-js` floor drops from `>=1.7.0` to `>=1.5.0`, and
  `@pipecat-ai/small-webrtc-transport` from `>=1.10.0` to `>=1.8.0`.** The old
  floors were the versions this package happened to be developed against, not
  versions it needs, and that distinction is not academic: the transport pins
  client-js with a *tilde* (`1.10.6` peers `~1.13.0`, `1.8.1` peers `~1.5.0`), so
  our floor propagates through it and lands on client-js exactly. An application
  that adds this SDK therefore has its pipecat version chosen by us, and pipecat
  is very often already load-bearing somewhere else in that application. The
  first host to install `0.1.0` had `client-js` move `1.5.0 → 1.13.0` underneath
  a live product the SDK has nothing to do with.

  Nothing here uses an API newer than 1.5: the surface is `PipecatClient`,
  `RTVIEvent`, `SmallWebRTCTransport({ iceServers })`, `connect`/`disconnect`,
  `enableMic`, `sendClientMessage`, and the standard callbacks. `APIRequest` has
  carried `endpoint` and a `Headers` since 1.5, which is the shape
  `toConnectParams` builds. All eight source files typecheck against
  `client-js@1.5.0` + `small-webrtc-transport@1.8.1` + `client-react@1.1.0`.

  Devdependencies stay at the current releases, so the tested configuration is
  still the top of the range. The floor says what we are willing to support, and
  it should be the oldest thing that works rather than the newest thing we
  happened to have installed.

## 0.1.0

**Breaking.** The call now rides pipecat's own `SmallWebRTCTransport`, and the
bespoke `VoqalWebRTCTransport` is gone.

### Changed

- **`VoqalWebRTCTransport` is deleted; pipecat's `SmallWebRTCTransport` carries
  the call.** The old transport signalled over a WebSocket we hand-rolled: open a
  socket, send a JWT handshake frame, wait for `handshake_ok`, exchange SDP and
  trickle ICE as JSON messages, then keep the socket alive with a heartbeat. All
  of it existed to move an offer and an answer — which is one HTTP POST, and
  pipecat already implements it. Everything the socket carried, the request now
  carries: the token is an `Authorization` header, the answer is the response
  body, and ICE candidates trickle as `PATCH`es to the same URL.

  What that buys is not brevity. A WebSocket makes the *first* request pick the
  process that will hold the peer connection and every later request stick to it,
  which is a load balancer's problem to solve and an availability risk while
  there is no load balancer. Over HTTP the control plane assigns a node when it
  mints the session and hands you its address, so affinity lives in the URL and
  nothing in the media path has to remember anything. It also means the WebRTC
  half of your app is stock pipecat: upgradable, and debuggable with everything
  written about it.

  `@pipecat-ai/small-webrtc-transport` is a new peer dependency — add it
  alongside the ones you already have.

- **`createSession` returns connection parameters, not a URL and a token.** It
  now hands back `{ webrtcRequestParams: { endpoint, headers }, sessionId }`,
  which goes straight into `PipecatClient.connect(...)`. Callers using
  `<VoqalAgent/>` or `useVoqalSession` see nothing; a caller wiring a raw
  `PipecatClient` replaces `pc.connect({ connection_url, token })` with
  `pc.connect(await createSession({…}))`.

- **Peer floor raised to `@pipecat-ai/client-js` 1.7** (from 1.5), because
  `small-webrtc-transport` 1.10 — the oldest release with the request-shaped
  connection parameters this uses — declares that floor itself. React 18.2 and
  `client-react` 1.1 are unchanged. The release job still typechecks against
  exactly those versions, so the range stays a checked claim.

### Added

- **`connectEndpoint` — mint the session on your own backend.** A publishable key
  puts the decision to start a call in the page, which is right for a public demo
  and wrong as soon as that decision depends on something the browser must not be
  trusted with: who the caller is, whether they have credit, which agent they get.
  Point the hook at a route on your server instead and it `POST`s there with
  `credentials: "include"` — your cookie, your credential, your rules — and
  connects to whatever session that route minted. Same hook, same handle, same
  UI; the two paths differ only in who is trusted to say a call may start.

- **`toConnectParams(body)`** — normalize a minted session's `connect_params`
  into transport-ready parameters, reading both the `snake_case` wire form and
  the already-normalized one. Run every server response through it, including
  your own backend's: pipecat builds each request with `headers.entries()`, so
  the plain object a JSON body naturally gives you throws a `TypeError` at the
  offer POST rather than failing anywhere legible. This is the one line that
  makes it a `Headers`.

### Fixed

- **The microphone is asked for before the session is minted.** It used to be
  acquired inside the transport, part-way through connecting — so a caller who
  had blocked their microphone still paid for a session, and the failure arrived
  as whatever the transport happened to throw. The permission prompt now comes
  first, keeps its typed `MicrophoneError` and its `awaiting-microphone` state,
  and nothing is minted until there is a microphone to speak into.

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
