# L2 — deployment: inbound, Cortex, and the VPC

Read when: inbound versus Cortex in detail, VPC deployment, GPUs, regions, or
what runs where.

## Inbound — the default

The customer exposes **one authenticated `wss://` route** in the backend they
already run. Voqalize dials `{brain_url}?session_id={session_id}` — the path
verbatim, session as a query parameter, so it is an ordinary route rather than a
wildcard path segment carved out for us. No relay in the media or control path.

The premise: anyone already operating a web or mobile backend can add one
WebSocket route trivially, and a relay's indirection is not worth its cost.

## Cortex — the fallback, and the local default

For brains that genuinely cannot accept inbound — serverless functions, laptops,
egress-only networks — the brain dials **out** to a stateless Go relay, and
Voqalize dials the relay. Both legs authenticate to the same **rendezvous scope,
derived from the verified credential each side presents, never from the URL**. A
URL that selected a pool would be a routing decision an attacker gets to make.

Cortex is crash-only: no state, no drain protocol, no graceful-shutdown contract.
Kill it and both ends reconnect.

**Same brain code either way.** Hosting calls: `run_session(socket)` when the
customer's app owns the route, or `await serve(Brain, …)` to dial Cortex. There
is no other.

`deployment.mode` lives in the control-plane record and says only *who writes the
URL*: `inbound` takes the customer's, `cortex` derives ours. It never reaches the
runtime — the runtime receives a URL and dials it. `mode: None` means nobody has
configured the agent, and `sessions.connect` refuses with `409
agent_not_configured`.

## Where things run on the cloud plan

- The brain: entirely in the customer's environment, wherever they run it.
- WebRTC, VAD, endpointing, STT, TTS, interruption, recording: Voqalize's voice
  tier, on Voqalize's own GPUs.
- Control plane: agents, sessions, keys, usage.
- Media: direct UDP between browser and voice node. No SFU.
- Region: calls are processed and stored in **India**. A US region is planned; it
  is not selectable today and has no date.

## VPC deployment

For enterprises, the whole voice tier — **speech models included** — deploys into
the customer's own cloud VPC with **no external dependency**. That phrase is the
commitment: no licence callback, no telemetry egress, no weight download at run
time, no reach back to a Voqalize service to take a call. Models are shipped into
the environment.

What is not published, and should not be improvised:

- **GPU sizing.** It depends on concurrency, language mix and whether the avatar
  is used, and it is scoped in the enterprise conversation. The customer runs and
  pays for their own hardware in their own account; Voqalize does not resell it.
- The update path and licence terms — also part of that conversation.

Forward-deployed engineering for these deployments is Voqalize's own engineers
working alongside the customer's; the engagement is how a VPC deployment and its
integration work get staffed. No delivery partner is named publicly — do not name
one.

## Certifications

Stated publicly: **ISO 27001**, **SOC 2**, **GDPR compliant**, **DPDP compliant**, plus role-based
access, a full audit trail and data-residency controls.

**The SOC 2 report type is not stated publicly — do not assert Type I or Type
II.** Anyone who needs the report, the scope or the certificate dates should be
sent to `support@voqalize.com`, where the actual documents live. Guessing here
would be the worst kind of wrong answer.
