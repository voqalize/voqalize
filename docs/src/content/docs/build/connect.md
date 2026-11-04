---
title: Connect your app
description: Start a Voqalize session from your page. One sessions.connect request (from your server with an sk_ key, or from the browser with a pk_), then pipecat's client on @voqalize/client-transport. The request, the response, the one line of glue, failures, rejoining after a page load, and recording consent.
---

A session starts with one HTTP request, `sessions.connect`, which returns the
connect params. Your page hands those to pipecat's client, and the browser then
negotiates WebRTC **directly with the Voqalize machine that runs the session**.
Audio is direct UDP; transcripts, actions and your page's events ride RTVI on the
same peer connection's data channel.

```
POST sessions.connect  ──▶  connect params
                              │
                              └─▶  client.connect(params)  ──▶  WebRTC, direct
```

## The request

```http
POST https://app.voqalize.com/api/v1/sessions.connect
Authorization: Bearer <your key>
Content-Type: application/json

{
  "agent_id": "06a2…",
  "config": {
    "tts": { "voice": "omnivoice/gauri", "language": "ta" },
    "stt": { "language": "ta" },
    "record": false
  },
  "init": { "order_id": "A-1183" }
}
```

Every field but `agent_id` is optional. A body with only `agent_id` starts a
session in English with the agent's recording default.

- **`init`** is your data for the brain. It arrives untouched as `session.init`.
  It is stored on the session, so send identifiers and look them up in your own
  store. [Context and history](/build/brain/context/) shows how a brain reads it.
- **`config`** is how this session sounds and listens (`tts`, `stt`, `idle`,
  `ack`) and whether it records (`record`). Set the voice and language here when
  your server already knows the user's language; the brain can still change them
  with `session.configure(...)`, and it has the last word.
  [Voice and language](/build/voice-and-language/) has the rules, including why a
  language goes on both legs.
- **`display_name`** and **`metadata`** label the session in the console and in
  session reads. [HTTP API](/reference/http-api/) has their limits.

The body is strict: an undeclared key is refused with `422`, naming it.

## The response

```json
{
  "webrtc_request_params": {
    "endpoint": "https://…/webrtc",
    "headers": { "Authorization": "Bearer <session token>" }
  },
  "session_id": "…"
}
```

An `ice_config` key is added when the machine running the session has a relay
of its own; forward it with the rest.

- **The endpoint is one machine, chosen for this session.** It changes from one
  session to the next, so it can never be a constant in your page.
- **The session token is scoped to this session** and expires in minutes. It is
  the only Voqalize credential the browser holds.
- **Forward the body; do not read it.** Pipecat's client takes these keys as they
  are. For the session's status, timings and recordings, read the session later
  with `get_session` ([Reading a call back](/operate/reading-a-call/)).

## Choose who makes the request

Same route, same body, same response. What differs is which key signs it and
where it runs.

### From your server, with an `sk_` key

Use this whenever starting a session depends on who the user is: their login,
their plan, which agent they are entitled to. It is also the only path for
native mobile apps, which send no `Origin` header.

1. Your page asks your backend for connect params, authenticated however your
   app already authenticates.
2. Your backend calls `sessions.connect` with the agent's secret `sk_` key, naming
   the `init` and `config` it decided this user gets.
3. Your backend returns the response body and status to the page unchanged.

```ts
// your server: the only place the sk_ key exists
app.post("/api/voice/start", requireLogin, async (req, res) => {
  const r = await fetch("https://app.voqalize.com/api/v1/sessions.connect", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${process.env.VOQALIZE_SECRET_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      agent_id: process.env.VOQALIZE_AGENT_ID,
      init: { customer_id: req.user.id },
      config: { record: req.body.consented === true },
    }),
  });
  res.status(r.status).json(await r.json()); // relay the body and the status
});
```

Renaming or dropping a field breaks the page's connect, so relay it whole.

### From the page, with a `pk_` key

A publishable `pk_` key may sit in page source and call `sessions.connect`
directly from the browser. It can start sessions for its one agent and do
nothing else. Use it when anyone who can load the page may talk to the agent: a
public demo, a marketing page, a support widget.

A `pk_` key is locked to the list of origins it was minted with, at least one.
Add every site that embeds it, including the `http://localhost:5173`
you develop against. A request from any other origin, or with no `Origin`
header at all (a server or a native app), is refused with `403
origin_not_allowed`. A `pk_` may turn recording off but never on
([below](#recording-is-a-per-session-decision)). [Keys](/build/keys/) covers
minting both kinds.

## Connect the page

Install pipecat's client and our transport as [Client libraries](/build/pipecat/)
shows, then:

```ts
import { PipecatClient } from "@pipecat-ai/client-js";
import { createVoqalizeTransport } from "@voqalize/client-transport";

const client = new PipecatClient({
  transport: createVoqalizeTransport(),
  enableMic: true,
});

const withRealHeaders = (p) => ({
  ...p,
  webrtc_request_params: {
    ...p.webrtc_request_params,
    headers: new Headers(p.webrtc_request_params.headers),
  },
});

// From your server (above), or straight to sessions.connect with a pk_ key.
const params = await fetch("/api/voice/start", {
  method: "POST",
  credentials: "include",
}).then((r) => r.json());

await client.connect(withRealHeaders(params));
```

Pipecat's events and hooks then give you the transcript, the agent's actions and
a way to send your own events; [Client libraries](/build/pipecat/) lists them.

### The one line you write yourself

`withRealHeaders` turns the plain `headers` object from JSON into a `Headers`
instance. Pipecat's transport requires one, and without it the offer request
throws a `TypeError` that does not mention headers. TypeScript does not catch
it, because pipecat types connect params as `unknown`.

Call `connect` yourself rather than pipecat's `startBotAndConnect`: that helper
passes the parsed response straight to the transport, leaving nowhere to apply
this line.

## When it fails

Every error has the same envelope:

```json
{
  "error": { "code": "invalid_config", "message": "…", "details": { "code": "unsupported_language" } },
  "info": "…",
  "correlation_id": "…"
}
```

Branch on `error.code`. Show a person `info`, which repeats `error.message` where
pipecat's client looks for it. Quote `correlation_id` when you ask us about a
session.

The ones you will meet first:

- `400 invalid_config`: a voice or language Voqalize does not serve; check
  [the catalog](/reference/catalog/). A language on one leg only is refused at
  the offer instead, when `client.connect` runs.
- `400 recording_not_permitted`: `record: true` on a `pk_`
  ([below](#recording-is-a-per-session-decision)).
- `403 origin_not_allowed`: a `pk_` from an origin not on its list.
- `409 agent_not_configured`: the agent has no way to reach a brain
  ([Deploy the brain](/build/hosting/)).

[Error codes](/reference/errors/#refused-before-your-brain-is-dialled) has every
status, cause and fix.

## Keeping a call across a page load

A reload, or a link to another page of your site, closes the peer connection but
not the session. The Voqalize machine holds a session for 10 seconds after its
connection closes and accepts a fresh offer with the same session token as that
session coming back, even after the token has expired.

Turn on `keepAcrossPageLoads` and the transport does it for you:

```ts
const transport = createVoqalizeTransport({ keepAcrossPageLoads: true });
const client = new PipecatClient({ transport, enableMic: true });

// On every page load.
if (transport.hasLiveCall) {
  client.connect().catch(() => {
    // The session ended while the page was away. hasLiveCall is now false.
  });
}

// The "Start" button, as before.
await client.connect(withRealHeaders(params));

// The "End" button.
client.disconnectBot();
await client.disconnect();
```

- **The transport saves the params** each `connect()` used, in `sessionStorage`.
  `connect()` with no arguments rejoins with them; params you pass always win.
- **Do not call `sessions.connect` on a rejoin.** That starts a second session.
- **It forgets the session** on `disconnectBot()` and when the machine refuses
  the rejoin: `410` for a session that ended, another `4xx` for one it no longer
  holds. `connect()` then rejects once.
- **Do not hang up on `pagehide`.** A page that never comes back ends the session
  when the 10-second hold runs out.
- **Construct the client with `enableMic: true`.** Opening the microphone before
  the agent's audio arrives is what lets the browser play it on a page nobody
  has tapped. For a user who was muted, call `enableMic(false)` once connected.
- **`sessionStorage` is per tab**, so a second tab starts its own session. The
  saved params carry the session token: any script on your page can read them.
- **A page restored from the back/forward cache** has lost its connection. Reload
  it on `pageshow` when `event.persisted` is true.

`keepAcrossPageLoads` is a browser feature of `@voqalize/client-transport`.

## Recording is a per-session decision

`config.record` overrides the agent's recording default for one session. Omit it
and the agent default applies.

- **`record: false` is always honoured**, on either key, even on an agent that
  records by default. Send it when the user declines.
- **`record: true` is refused on a `pk_` key** with `400
  recording_not_permitted`, and no session starts: a key in page source must not
  be able to write voice into your storage. Send it from your server with an
  `sk_` when the user consents.

A recorded session also records the user's camera and screen whenever the page
turns them on ([Camera and screen](/build/video/)). [Recordings](/operate/recordings/)
covers what is stored and how to read it.

## On pipecat's stock transport

Pipecat's own `SmallWebRTCTransport` also connects, for now. Pass it where the
examples above pass `createVoqalizeTransport()`:

```bash
pnpm add @pipecat-ai/client-js @pipecat-ai/small-webrtc-transport
```

```ts
import { PipecatClient } from "@pipecat-ai/client-js";
import { SmallWebRTCTransport } from "@pipecat-ai/small-webrtc-transport";

const client = new PipecatClient({ transport: new SmallWebRTCTransport(), enableMic: true });
```

Your page then loads daily's call machine from `c.daily.co`, and the
transport's recoveries do not apply. Everything above applies except
`keepAcrossPageLoads`: to keep a session across a page load, save the params
yourself.

```ts
const CALL = "voice-call"; // your sessionStorage key

// The "Start" button.
async function start() {
  const params = await fetch("/api/voice/start", {
    method: "POST",
    credentials: "include",
  }).then((r) => r.json());
  sessionStorage.setItem(CALL, JSON.stringify(params));
  await client.connect(withRealHeaders(params));
}

// On every page load.
const saved = sessionStorage.getItem(CALL);
if (saved) {
  client.connect(withRealHeaders(JSON.parse(saved))).catch(() => {
    sessionStorage.removeItem(CALL); // the session ended while the page was away
  });
}

// The "End" button.
async function end() {
  sessionStorage.removeItem(CALL);
  try {
    client.disconnectBot();
  } catch {
    // Not connected: there is no session to end.
  }
  await client.disconnect();
}
```

- **Save before you connect**, so a load in the middle of connecting still finds
  the session.
- **End with `disconnectBot()`**, which ends the session at once rather than
  after the hold, and forget the params with it.
- **A rejoin that fails means the session is over** (`410`, or another `4xx`).
  Forget the params and show the page idle.
- **Open the microphone before the agent's audio arrives.** On this transport
  nothing plays held-back audio later.
- The other rules above apply: no `sessions.connect` on a rejoin, no hang-up on
  `pagehide`, one session per tab, reload after a back/forward-cache restore.

## Read next

- [Client libraries](/build/pipecat/): packages, versions, and mobile clients.
- [Keys and authentication](/build/keys/): minting `sk_` and `pk_` keys.
- [Going to production](/operate/production/): the checklist before launch.
