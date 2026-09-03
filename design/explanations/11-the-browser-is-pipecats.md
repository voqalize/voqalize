# 11. The browser is pipecat's

> **The surprise.** We ship no client library. The only Voqalize-specific code in
> your page is one HTTP request, and packaging it costs more than writing it out —
> because a package is a thing to version, and what it holds is a schema that
> never changes.

> **Outcome, 2026-08-24.** Carried out. `sessions.connect` answers in the shape
> pipecat's transport connects with, the `record` refusal became a 400 from the
> server, the `Headers` line moved into `docs/client/handshake`, and
> `@voqalize/client-react` is deprecated on npm with no successor. Everything
> below is the analysis as it stood before that — including the gaps, two of
> which (presence, the demo dependency declaration) are what the demos
> still need before the package's source can be removed. Read it as the record of
> an argument, not as a description of the tree.

[10](10-the-framework-boundary.md) drew this line on the server: the agentic
framework owns its tools, we own the voice. This is the same line drawn in the
browser, and it lands harder, because on this side there is nothing left for us to
own at all. A Voqalize call **is** a pipecat call. The transport is pipecat's, the
events are pipecat's, the hooks are pipecat's, the UI kit is pipecat's. What is
ours is the sentence that turns a publishable key into an address.

## The decision, stated

1. **No client library.** The one thing we are required to build is the
   Voqalize-specific call initialisation. Nothing else ships.
2. **Everything after that is stock pipecat** — `@pipecat-ai/client-js`,
   `@pipecat-ai/client-react`, and `@pipecat-ai/voice-ui-kit`. Not "mostly", not
   "with a thin wrapper".
3. **All server communication is over stock pipecat.** RTVI's `client-message`,
   `server-message` and `ui-command`, on the data channel the transport already
   has. No second channel, no envelope of ours.
4. **Presence is built on pipecat states.** Not on a state machine of ours that
   pipecat feeds.
5. **The avatar is a separate addon**, not part of any of this — its own repo, its
   own licence, its own package pair.

## Belief

- **A library is a promise to version something.** The connection step is a
  *schema* — a path, a header, a body, a response shape — and a schema that
  changes is a breaking change whether or not a package number moved. Wrapping it
  buys the customer nothing and costs them a dependency in their bundle, a peer
  range to satisfy, and a version of ours to keep up with.
- **The failure mode of a client wrapper is lag, not breakage.** Ours never
  crashed; it just described a smaller pipecat than the one installed. Every
  event pipecat added, we had to add a case for. That is a debt that compounds
  quietly on somebody else's release schedule.
- **A demo a customer copies is documentation.** If the page they copy imports a
  package of ours, the package is now load-bearing whether we meant it or not.
- **Presence is a rendering of state, never a source of it.** The states are
  pipecat's — transport state, who is speaking, whether the model is running. A
  presence component takes them and paints; it must not subscribe, accumulate, or
  become the thing the app asks "what is happening?"
- **An addon earns its package by adding a capability, not by adapting an
  interface.** The avatar is a package because it draws a face and aligns
  phonemes. The client SDK was a package because it renamed things.
- **Give up compile-time comfort on this side too, and say so.** Typed action
  correlation was real and it is gone. A page that runs on an unmodified pipecat
  client is worth more.

## Facts — what is actually there today

- **The package is already one function's worth.** `@voqalize/client-react` 0.3.0
  is **206 lines of code and 314 lines of prose**, exporting `createSession`,
  `startBotParams`, `toConnectParams`, `fromSessionResponse` and one error class.
  Its own changelog opens: "**This package is now one function.**" It declares no
  dependencies and no peers — it is `fetch` and JSON.
- **Sugar imports exactly two of those five**, `startBotParams` and
  `fromSessionResponse`, in one line of `SugarCoach.tsx`. Everything else on that
  page is stock: `PipecatAppBase` and `usePipecatConnectionState` from
  voice-ui-kit; `usePipecatClient`, `usePipecatClientTransportState`,
  `usePipecatClientMicControl` and `useRTVIClientEvent` from client-react;
  `RTVIEvent.UICommand` and `TransportState` from client-js.
- **Server communication is already all stock.** Screen ← coach is
  `RTVIEvent.UICommand` carrying `{command, payload}`, which is RTVI's own
  `ui-command` — the brain's `session.dispatch(...)` puts it there. Coach ← screen
  is `client.sendClientMessage("state_sync", {screen})` and `client.sendText(...)`,
  both RTVI `client-message`. There is no Voqalize channel in the page.
- **The mint is stock pipecat too, and this is the part that is easy to miss.**
  `VoqalStartBotRequest` is *structurally pipecat's `APIRequest`*, and
  `PipecatAppBase` performs pipecat's own two-step connect with it: `startBot`
  against the control plane, then `connect` the transport against whatever came
  back. We are not bypassing pipecat to mint a session; we are filling in the one
  field pipecat leaves to the application.
- **So the Voqalize-specific surface is exactly four facts:**
  `POST {apiBase}/sessions.create` · `Authorization: Bearer pk_…` ·
  `{agent_id, agent_input: {pipeline, payload}, record?}` ·
  read `connection_details.connect_params` back as
  `{webrtcRequestParams: {endpoint, headers}, sessionId}`.
- **Presence takes state, it does not hold it.** `AmbientPresence`
  (`demos/shared/`, not the SDK) imports one *type* from client-js
  (`TransportState`) and nothing at runtime beyond React. Its props are
  `activity` and `transportState`; it subscribes to nothing. Its own docstring
  names the derivation as the caller's job.
- **The avatar is the addon shape, already built.** `@voqalize/avatar` +
  `voqalize-avatar`, MIT, separate repo, publishing in lockstep from one tag.
  `createAvatar({mount, client})` takes the stock `PipecatClient` and returns
  `{destroy()}` — "there is no avatar to drive and no state to read back". It adds
  **no video track and names no transport**; it rides the RTVI data channel the
  client already has, plus one custom RTVI message for lipsync. `client-js` is an
  **optional** peer, types only.

## What the review found

Four things, in the order they will bite.

**1. Sugar cannot be installed the way its own README says.** Every demo declares
`"@voqalize/client-react": "^0.1.0"` — the published range, deliberately, so the
page reads like a customer's. But `startBotParams` and `fromSessionResponse` do
not exist in 0.1.x; they were added in 0.3.0, which is **staged and unpublished**.
`demos/build.mjs` overlays the locally built SDK over each install, so the
assembled build works and the checked-out tree works — sugar's `node_modules`
holds 0.3.0 right now while its lockfile pins registry 0.1.0. But
`demos/README.md` documents standalone dev as `pnpm install --ignore-workspace`,
which gets 0.1.0 and fails to typecheck. **The overlay masks it**, which is the
worst version of this defect: it is invisible until somebody outside the repo
tries. It is the same shape as C2 and D9 — two places holding a copy, and no build
that sees both.

**2. The presence derivation is copied, not shared.** `AmbientPresence` is right —
it renders and nothing else. But every demo hand-wires the same four
`useRTVIClientEvent` calls into the same four-state `useState`, and sugar's
version reads `BotLlmStarted` for `thinking`. That is a `bot-llm-*` event, which
[60] put on pygato's side of the wire — correct, and worth stating, because it is
the one presence input that does not come from the brain. The duplication belongs
in `@voqalize/demo-kit` as a hook beside the component, not in an SDK.

**3. The avatar already solves presence better, and we have not noticed.**
`createAvatar` derives `SPEAKING`, `LISTENING`, `MUTED`, `OFFLINE` and `DEGRADED`
from the `PipecatClient` **with no backend involvement at all**, and gets
`THINKING`, `WORKING` and `STRAINING` from a pipeline processor watching turn and
LLM boundaries. Presence makes the app do by hand what the avatar does for itself.
Same problem, two answers, and the addon's answer is the one that matches this
decision.

**4. Two things in the package are not connection glue, and they are the real
argument against deleting it.**
- **`Headers` must be a real `Headers`.** Pipecat builds every request with
  `Object.fromEntries(headers.entries())`, so the plain object a JSON body
  naturally gives you throws a `TypeError` at the offer POST — not at the mint,
  where you would look. `toConnectParams` exists largely to prevent this.
- **`record: true` is refused on a `pk_` key, silently.** The call connects,
  greets and answers; the recording is simply not there, found weeks later. The
  package warns on the console in two places, and it is the only thing that does.

Neither is a wrapper's job. The first is one line in a snippet
(`new Headers(raw.webrtc_request_params.headers)`) — but only if the snippet is
somewhere a reader cannot skip. The second belongs to the **server**: a request
that cannot be granted should come back saying so, in the response body, where a
page that never imported anything of ours can still see it.

## Proof

- **The deletions, measured.** `1a636d2` took the React package from a client
  library to a connection step: −2168/+362, removing `VoqalAgent.tsx`,
  `useVoqalSession.ts`, `useUiCommand.ts` and `microphone.ts`. `612fec9` rebuilt
  sugar's UI on stock pipecat at −1226/+168. `2195452` handed its call lifecycle
  to `PipecatAppBase`. Nothing was reimplemented to replace any of it.
- **Each removal named the stock thing that already did it.** `useVoqalSession` →
  `PipecatClient` + `PipecatClientProvider`. `useUiCommand` → pipecat's
  `useUICommandHandler` on RTVI's own `ui-command`. `requestMicrophone` →
  pipecat's `DeviceErrorType`, "the same six failures one-for-one".
  `AmbientPresence`/`PreCallGate` → demo chrome, moved to `@voqalize/demo-kit`.
- **The one thing that could not be replaced was written down as a loss**, not
  quietly dropped: "the typed `Action`/`Result` correlation this gave up —
  `action_id`, a compile-time-checked handler map — is a real loss, taken
  deliberately: stock compatibility is worth more."
- **A live call is what proved the lifecycle handover**, and it found the one bug
  static review could not: `BotAudioOutput` has to mount with the *client*, not
  with the *call*, because the bot's track is announced once from a remote `unmute`
  a few hundred milliseconds in — a listener that subscribes late finds nothing,
  and the call plays silently with RTP arriving and nobody decoding it. Same
  lesson as page 10: the failure mode of getting this seam wrong is silence.

## The shape a customer sees

```tsx
<PipecatAppBase
  transportType="smallwebrtc"
  startBotParams={/* the four facts, as a request */}
  startBotResponseTransformer={/* connect_params → { endpoint, Headers } */}
>
  {({ error, handleConnect }) => <YourCallUI … />}
</PipecatAppBase>
```

Everything inside is theirs and pipecat's. The two props are the entire seam, and
under this decision they are a documented snippet rather than an import.

## Gap

- **Whether the package is deleted or published is not settled here.** What is
  settled is that it may hold nothing but the four facts. Deleting it entirely
  costs the `Headers` footgun a home and the `record` refusal its only warning;
  publishing it keeps a version number on a schema. **Position:** move the
  `record` refusal to the server response, put the `Headers` line in the docs
  snippet, and then the package has nothing left to hold.
- **Nothing enforces the boundary.** Nothing fails if a demo grows a wrapper, or
  if the package grows a sixth export. On the Python side `_ready` at least sits
  in one file; here the rule lives only in prose.
- **The demo dependency declaration is unresolved either way.** Declaring the
  published range is right — it is what a customer reads — and it is a lie
  whenever the tree is ahead of npm, which is now. A check at the assemble step
  (does every demo's declared range admit the tree's version?) is the same fix
  C2 and D9 want.
- **Presence has no owner.** It is a component in `demo-kit` with its derivation
  copied into eleven pages, and the avatar does the same job differently in
  another repo. One of those two is the answer and we have not chosen.
- **This is reviewed on one demo.** Sugar. The other ten still import the old
  surface, and the ten-demo port is what will say whether "stock, with a snippet"
  survives contact with a launcher widget, a pre-call gate and a page that is not
  a full-screen call.
- **`voice-ui-kit` is pre-1.0** (`^0.13.0`). Committing the reference
  implementation to it is a bet that its churn is cheaper than our wrapper's lag.
  We believe that; we have not paid for it yet.
