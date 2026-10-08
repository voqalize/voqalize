---
title: Connections and the handshake
description: How a browser starts a Voqalize session — one HTTP request for the connect params, then pipecat's client on our transport. With a publishable key, or through your own backend.
---

A session is one HTTP request that starts it and a WebRTC connection your
browser negotiates **straight to the machine that will run it**. Nothing of ours
sits between them. The audio is direct UDP, and the control messages —
transcripts, the agent's UI commands, your client messages — ride RTVI on that
peer connection's data channel.

The app integration gets the connect parameters and passes them to Pipecat.

```
POST /sessions.connect  ──▶  { where to send the offer, what to present on it }
                              │
                              └─▶  client.connect(params)  ──▶  WebRTC, direct
```

## The one request

```http
POST https://app.voqalize.com/api/v1/sessions.connect
Authorization: Bearer <your key>
Content-Type: application/json

{
  "agent_id": "…",
  "init": { "order_id": "A-1183" },
  "config": { "record": false }
}
```

The body is strict: an undeclared key returns a `422` naming it. `display_name`
and a bounded `metadata` map are accepted as labels too, described in
[A session, end to end](/build/session/).

`init` is what the page hands the brain: a flat, opaque blob of business
context, uninterpreted by everything between this request and `session.init`.
The same value arrives as `session.init`. It is stored on the session and
readable by anyone who can read the session, so send identifiers instead of
personal data.

`config` is how this session sounds and listens — `tts`, `stt`, `idle`, and
`record`. Recording lives here rather than beside `init` because it is not the
brain's business. Most pages should set none of it; see
[voice and language](/reference/catalog/) for who sets what, and
[A session, end to end](/build/session/) for the full body.

The answer is the connect params, and nothing else:

```json
{
  "webrtc_request_params": {
    "endpoint": "https://…/webrtc",
    "headers": { "Authorization": "Bearer <session token>" }
  },
  "session_id": "…"
}
```

What follows from that body being this short:

**The endpoint is a machine, not a load balancer.** A node is chosen when the
session is minted and the token is minted for that node, so the address is
different from one session to the next and cannot be a constant in your page. That
is why it comes back in the response rather than being something you configure
once.

**The token is scoped to this one session** and expires in minutes. It is the
only credential the browser ends up holding.

**Every key is one pipecat's transport recognises.** Its client lower-camels the
outer keys itself, so snake\_case is what you send it — `webrtc_request_params`
becomes `webrtcRequestParams`, `session_id` becomes `sessionId`. Keys it does not
recognise are dropped with a console warning, which is the real reason this
response is not a session record: a pipecat page does not *read* the start
response, it *forwards* it. If you want the session record — status, timings,
recordings — that is a read, asked later, and it is
[`get_session`](/operate/reading-a-call/) rather than anything on this route.

## Where the credential lives

Same route, same body, same response. The only difference is which key signs the
request and who makes it.

### Path A — a publishable key in the page

`pk_live_…` ships in your page source and the browser calls `sessions.connect`
directly, cross-origin. CORS is open on this route for exactly that reason.

A publishable key can start a session and do nothing else. It is bound to an
allowlist of origins, and **an empty allowlist denies rather than permits** — a
key readable by anyone who opens view-source has to fail closed. Add every site
that embeds it when you create the key, including the `http://localhost:5173`
you develop against. A request from anywhere else is `403` `origin_not_allowed`,
and so is one with no `Origin` header at all — which is what a server sends. A
`pk_` works only from a browser page; from a server, use an `sk_`.

Choose this when starting a session needs no decision: a public demo, a marketing
page, a support widget anyone may use.

### Path B — your backend decides who gets a session

The moment starting a session depends on something the browser must not be trusted
with — who the user is, whether their subscription is current, which agent they
are entitled to — the decision belongs on your server, and so does the key.

Only the middle hop is ours:

1. **Your page asks your backend for connect params** — on page load, or when the
   user presses the button. **How that request is authenticated is entirely
   yours.** Session cookie, bearer token, signed URL, whatever your app already
   does. That trust boundary is yours; we never see it and have no opinion about
   it.
2. **Your backend calls `sessions.connect` with a secret key** (`sk_…`), naming
   whatever `agent_id` and `init` it decided *this* user gets.
3. **Your backend returns that JSON body to the browser, verbatim.**

```ts
// your server — the only place your sk_ key exists
app.post("/api/voice/start", requireLogin, async (req, res) => {
  const r = await fetch("https://app.voqalize.com/api/v1/sessions.connect", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${process.env.VOQALIZE_SECRET_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      agent_id: agentFor(req.user),
      init: { customer_id: req.user.id },
      config: { record: req.body.consented === true },
    }),
  });
  res.status(r.status).json(await r.json()); // relay the body AND the status
});
```

Return the response body and HTTP status unchanged. The browser passes the body
to Pipecat, so renaming or removing a field prevents the transport from using
the returned endpoint or credential.

The `sk_` never reaches the browser. Neither does anything else of ours: your
page talks to your origin, and the only Voqalize address it ever learns is the
node it is about to connect to.

## Connecting

Both paths end in the same place.

```ts
import { PipecatClient } from "@pipecat-ai/client-js";
import { createVoqalizeTransport } from "@voqalize/client-transport";

const client = new PipecatClient({
  transport: createVoqalizeTransport(),
  enableMic: true,
});

// Path A: straight to us with a pk_.  Path B: your own route, your own auth.
const params = await fetch("/api/voice/start", {
  method: "POST",
  credentials: "include",
}).then((r) => r.json());

await client.connect(withRealHeaders(params));
```

`createVoqalizeTransport` is pipecat's `SmallWebRTCTransport` with our media
manager in place of its default. [Client libraries](/build/pipecat/) says what
that adds, and how to connect with pipecat's stock transport instead.

### The one line you write yourself

```ts
const withRealHeaders = (p) => ({
  ...p,
  webrtc_request_params: {
    ...p.webrtc_request_params,
    headers: new Headers(p.webrtc_request_params.headers),
  },
});
```

Pipecat builds the offer request with
`Object.fromEntries(headers.entries())` — it expects a constructed `Headers`, and
JSON has no such type, so the plain object `r.json()` gave you throws a
`TypeError` at the offer POST. Not at `connect`, and not with a message about
headers. TypeScript will not catch it for you either: pipecat types connect
params as `unknown`, so the whole path is unchecked.

One line, in one place, and it is the only glue between our response and
pipecat's transport. The fix upstream is one type — `HeadersInit` instead of `Headers` — and
when it lands this line goes away and the parsed body passes straight through.

### Not `startBotAndConnect`

Pipecat's `startBotAndConnect` folds the steps into one, and it is exactly
`connect(await startBot(params))` — the parsed response goes to the transport
with nothing in between, so there is nowhere to put the line above. Do them
yourself. One is a `fetch` your framework already knows how to make.

The other shortcut worth naming so you don't go looking for it: the transport can
derive an offer URL from a static `offerUrlTemplate` when the server returns only
a session id. That works when the offer endpoint is one fixed address. Ours is
the node chosen for this session, which is the same reason there is no load
balancer in the media path at all — so the server tells you the endpoint, every
time.

## When it fails

Every error is the same envelope:

```json
{
  "error": { "code": "recording_not_permitted", "message": "…", "details": {} },
  "info": "…",
  "correlation_id": "…"
}
```

`info` is the same sentence as `error.message`, repeated at the top level for one
reader: pipecat's client, which on a failed start does
`errResp.info ?? errResp.detail ?? e.statusText`. Without it, every sentence we
write reaches a browser as "Bad Request". Branch on `error.code`; show a person
`info`; quote `correlation_id` when you ask us about a session.

| Status | What happened |
| --- | --- |
| `401` | No `Authorization` header, a value that is not an `sk_` or `pk_` key, or a key that was revoked or belongs to another environment. |
| `403` `origin_not_allowed` | A `pk_` from an origin not on its allowlist, from a request with no `Origin` header (a server — use an `sk_`), or with an empty allowlist. The message names the origin it saw and never lists the allowed ones. |
| `404` | No such agent in this key's tenant. A key is scoped to exactly one. |
| `400` `recording_not_permitted` | `config.record: true` on a publishable key. See below. |
| `409` `agent_not_configured` | The agent has no brain URL. Configure inbound or mint Cortex credentials before starting a session. |
| `409` `agent_archived` | The agent is archived. Restore it before starting a new session. Sessions already in progress continue. |
| `500` `missing_connect_params` | The session was minted but no worker is running for that agent. |

## Keeping a call across a page load

A full page load — a reload, or a link to another page of your site — closes
the peer connection but not the call. The node holds a call for 10 seconds
after its connection closes, and takes a fresh offer with the same session
token and no `pc_id` as that call coming back. A new transport handed the
params the last page connected with sends exactly that offer, even after the
token has expired: expiry bounds when a session may start, not how long it may
be rejoined.

Turn on `keepAcrossPageLoads` and the transport does that for you:

```ts
const transport = createVoqalizeTransport({ keepAcrossPageLoads: true });
const client = new PipecatClient({ transport, enableMic: true });

// Every page load.
if (transport.hasLiveCall) {
  client.connect().catch(() => {
    // The call ended while the page was away. hasLiveCall is now false.
  });
}

// The "Start" button, as before.
await client.connect(withRealHeaders(params));

// The "End call" button.
client.disconnectBot();
await client.disconnect();
```

- **The transport saves the params each `connect()` used** in `sessionStorage`,
  before it sends the offer. `connect()` with no arguments rejoins with them, and
  params you pass always win.
- **Don't call `sessions.connect` on a rejoin.** That starts a second session.
- **It forgets the call** on `disconnectBot()`, and when the node refuses an
  offer: `410` for a call that has ended, another `4xx` for one the node no
  longer holds. A call that ended while the page was away makes `connect()`
  reject once.
- **Don't hang up on `pagehide`.** The page going away is what this survives. A
  page that never comes back ends the call when the hold runs out, dated at the
  close. The transport never connects or hangs up by itself.
- **Rejoin with the microphone on, without asking for a tap.** Construct the
  client with `enableMic: true`: `connect()` opens the microphone before the
  agent's audio arrives, and an open microphone is what lets the browser play
  that audio on a page nobody has touched. For a user who was muted, call
  `enableMic(false)` once connected rather than never opening it. If the browser
  still holds the audio back, the media manager plays it when the microphone
  opens or on the next tap or key press.
- **`sessionStorage` is per tab**, so a second tab starts its own call. The
  saved params carry the session token: they never leave your origin, but any
  script on your page can read them, as it can read the live client.
- **A page restored from the back/forward cache** brings back a client whose
  connection is gone. Reload it on `pageshow` when `event.persisted` is true.

### On pipecat's stock transport

Without our library, keep the params yourself:

```ts
const CALL = "voice-call"; // sessionStorage key, yours to name

// The "Start" button.
async function start() {
  const params = await fetch("/api/voice/start", {
    method: "POST",
    credentials: "include",
  }).then((r) => r.json());
  sessionStorage.setItem(CALL, JSON.stringify(params));
  await client.connect(withRealHeaders(params));
}

// Every page load.
const saved = sessionStorage.getItem(CALL);
if (saved) {
  client.connect(withRealHeaders(JSON.parse(saved))).catch(() => {
    sessionStorage.removeItem(CALL); // the call ended while the page was away
  });
}

// The "End call" button.
async function end() {
  sessionStorage.removeItem(CALL);
  try {
    client.disconnectBot();
  } catch {
    // Not connected: there is no call to end.
  }
  await client.disconnect();
}
```

- **Save before you connect**, so a load in the middle of connecting still
  finds the call.
- **End with `disconnectBot()`.** It ends the call at once rather than after the
  hold, and forgetting the params with it means a reload after End does not dial
  back.
- **A rejoin that fails means the call is over.** An offer for a call that has
  ended is refused with `410`; one for a call the node no longer holds, with
  another `4xx`. Either way, forget the params and show the page idle.
- **Rejoin with the microphone on**, as above. A microphone opened after the
  agent's audio arrives leaves Chrome refusing to play it, and on this path
  nothing plays it later.
- **The rest is as above:** no `sessions.connect` on a rejoin, no hang-up on
  `pagehide`, per tab, and a reload after a back/forward-cache restore.

## Recording is a per-session decision

Recording is `config.record`, a boolean in the same block as the voice and
language settings. Omit it and the session does whatever the agent is configured
for. That is the common case: the agent's owner made the decision once, in a
place they control.

**`config.record: false` is always honoured.** A user who declines is not recorded,
even on an agent that records by default, on either path.

**`config.record: true` is refused on a publishable key** — `400`, and no session starts, so
nothing is minted and nothing is billed. A `pk_` ships in page source; if it could
turn recording *on*, anyone holding it could write voice into your storage, on
your bill, for an agent whose owner chose not to record. Enable recording through
the agent default, MCP, the console, or a backend request authenticated with an
`sk_`.

On Path B, `config.record: true` with an `sk_` is fine and is the right way to express
per-user consent. Your backend is the party that actually knows the user
agreed.

The same decision covers video. A recorded session also records the user's
camera and screen whenever the page turns them on; see
[camera and screen](/build/video/).

## Integration constraints

- **No relay past the handshake.** Once connected, the media is direct UDP and
  RTVI is on the data channel. Your server is not in the loop and does not want
  to be.
- **Pipecat's client, used directly.** `@voqalize/client-transport` replaces
  the media manager inside pipecat's transport and nothing else. The client,
  its hooks, signalling and RTVI are [pipecat](https://docs.pipecat.ai)'s own.
- **No polling for readiness.** The endpoint in the response is live when you
  receive it.
- **No reusing connect params for a new session.** They are one session, and
  the token expires in minutes. Keeping them to rejoin that session after a
  page load is the one reuse, above.

## Read next

- **[The wire](/reference/wire/)** — the frames underneath the session, and the
  contract they keep.
- **[Voice & language catalog](/reference/catalog/)** — why the brain, and
  not the page, sets how an agent sounds.
