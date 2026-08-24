---
title: Connections and the handshake
description: How a browser starts a Voqalize call — one HTTP request for the connect params, then stock pipecat. With a publishable key, or through your own backend.
---

A call is two things: one HTTP request that starts it, and a WebRTC connection
your browser negotiates **straight to the machine that will run it**. Nothing of
ours sits between those two. The audio is direct UDP, and the control messages —
transcripts, the agent's UI commands, your client messages — ride RTVI on that
peer connection's data channel.

So the whole browser-side integration is: get the connect params, hand them to
pipecat, stop thinking about us.

```
POST /sessions.connect  ──▶  { where to send the offer, what to present on it }
                              │
                              └─▶  client.connect(params)  ──▶  WebRTC, direct
```

## The one call

```http
POST https://api.voqalize.com/api/v1/sessions.connect
Authorization: Bearer <your key>
Content-Type: application/json

{
  "agent_id": "…",
  "agent_input": { "payload": { "orderId": "A-1183" } },
  "record": false
}
```

`agent_input` is what the page hands the brain. Anything under `payload` is
opaque business context the agent receives at the start of the call; `pipeline`
beside it is per-call media config, which most pages should not set — [voice and
language belong to the brain](/docs/reference/catalog/). `agent_input` is signed
into the session token *and* stored on the session, so send identifiers, not
personal data. `record` rides beside it, not inside it: recording is not the
brain's business.

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

Three things follow from that body being this short.

**The endpoint is a machine, not a load balancer.** A node is chosen when the
session is minted and the token is minted for that node, so the address is
different from one call to the next and cannot be a constant in your page. That
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
recordings — that is `sessions.create`, and it is a different question asked
later.

## Two ways to hold the credential

Same route, same body, same response. The only difference is which key signs the
request and who makes it.

### Path A — a publishable key in the page

`pk_live_…` ships in your page source and the browser calls `sessions.connect`
directly, cross-origin. CORS is open on this route for exactly that reason.

A publishable key can start a call and do nothing else. It is bound to an
allowlist of origins, and **an empty allowlist denies rather than permits** — a
key readable by anyone who opens view-source has to fail closed. Add every site
that embeds it when you create the key, including the `http://localhost:5173`
you develop against; a request from anywhere else is `403`.

Choose this when starting a call needs no decision: a public demo, a marketing
page, a support widget anyone may use.

### Path B — your backend decides who may call

The moment starting a call depends on something the browser must not be trusted
with — who the caller is, whether their subscription is current, which agent they
are entitled to — the decision belongs on your server, and so does the key.

Three hops, and only the middle one is ours:

1. **Your page asks your backend for connect params** — on page load, or when the
   caller presses the button. **How that request is authenticated is entirely
   yours.** Session cookie, bearer token, signed URL, whatever your app already
   does. That trust boundary is yours; we never see it and have no opinion about
   it.
2. **Your backend calls `sessions.connect` with a secret key** (`sk_…`), naming
   whatever `agent_id` and `agent_input` it decided *this* caller gets.
3. **Your backend returns that JSON body to the browser, verbatim.**

```ts
// your server — the only place your sk_ key exists
app.post("/api/voice/start", requireLogin, async (req, res) => {
  const r = await fetch("https://api.voqalize.com/api/v1/sessions.connect", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${process.env.VOQALIZE_SECRET_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      agent_id: agentFor(req.user),
      agent_input: { payload: { customerId: req.user.id } },
      record: req.body.consented === true,
    }),
  });
  res.status(r.status).json(await r.json()); // relay the body AND the status
});
```

**Relay it whole.** Don't unwrap it, rename its keys, or fold it into an envelope
of your own: the browser's next line hands it to pipecat, and a field you dropped
is an address pipecat cannot reach. Relay the status too — a refusal turned into
a `200` with an empty body is a page that fails somewhere much less legible than
where it actually went wrong.

The `sk_` never reaches the browser. Neither does anything else of ours: your
page talks to your origin, and the only Voqalize address it ever learns is the
node it is about to call.

## Connecting

Both paths end in the same place.

```ts
import { PipecatClient } from "@pipecat-ai/client-js";
import { SmallWebRTCTransport } from "@pipecat-ai/small-webrtc-transport";

const client = new PipecatClient({
  transport: new SmallWebRTCTransport(),
  enableMic: true,
});

// Path A: straight to us with a pk_.  Path B: your own route, your own auth.
const params = await fetch("/api/voice/start", {
  method: "POST",
  credentials: "include",
}).then((r) => r.json());

await client.connect(withRealHeaders(params));
```

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

One line, in one place, and it is the only Voqalize-specific code in your
browser. The fix upstream is one type — `HeadersInit` instead of `Headers` — and
when it lands this line goes away and the parsed body passes straight through.

### Not `startBotAndConnect`

Pipecat's `startBotAndConnect` folds the two steps into one, and it is exactly
`connect(await startBot(params))` — the parsed response goes to the transport
with nothing in between, so there is nowhere to put the line above. Do the two
steps yourself. One is a `fetch` your framework already knows how to make.

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
`info`; quote `correlation_id` when you ask us about a call.

| Status | What happened |
| --- | --- |
| `401` | No `Authorization` header, or a key we don't recognise. |
| `403` | A `pk_` from an origin it isn't allowlisted for — or one with no allowlist at all. |
| `404` | No such agent in this key's workspace. A key is scoped to exactly one. |
| `400` `recording_not_permitted` | `record: true` on a publishable key. See below. |
| `500` `missing_connect_params` | The session was minted but no worker is running for that agent. |

## Recording is a per-call decision

Omit `record` and the call does whatever the agent is configured for. That is the
common case: the agent's owner made the decision once, in a place they control.

**`record: false` is always honoured.** A caller who declines is not recorded,
even on an agent that records by default, on either path.

**`record: true` is refused on a publishable key** — `400`, and no call starts, so
nothing is minted and nothing is billed. A `pk_` ships in page source; if it could
turn recording *on*, anyone holding it could write voice into your storage, on
your bill, for an agent whose owner chose not to record. The refusal is loud on
purpose: the failure it replaces was a call that ran, sounded perfectly normal,
and quietly recorded nothing the page thought it had asked for. Turn recording on
where its owner controls it — the agent's default, over MCP, or in the console.

On Path B, `record: true` with an `sk_` is fine and is the right way to express
per-caller consent. Your backend is the party that actually knows the caller
agreed.

## What not to build

- **No relay past the handshake.** Once connected, the media is direct UDP and
  RTVI is on the data channel. Your server is not in the loop and does not want
  to be.
- **No client library of ours.** The browser half is one `fetch`, one `Headers`
  line and `client.connect`. Everything after that is
  [pipecat](https://docs.pipecat.ai)'s own client, used directly — its hooks, its
  transport, its release cadence, with nothing of ours lagging behind it.
- **No polling for readiness.** The endpoint in the response is live when you
  receive it.
- **No caching connect params.** They are one session, and the token expires in
  minutes.

## Next

- **[React client SDK](/docs/client/react/)** — the same handshake with our
  helper package, if you'd rather install one thing than write the line above.
- **[The wire](/docs/reference/wire/)** — the frames underneath the call, and the
  contract they keep.
- **[Voice & language catalog](/docs/reference/catalog/)** — why the brain, and
  not the page, sets how an agent sounds.
