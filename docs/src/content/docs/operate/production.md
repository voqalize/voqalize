---
title: Going to production
description: The checklist before real users talk to your agent. Keys and origins, consent and recording, pinned versions, the inbound route, key rotation, region and retention, limits, error handling, tests in CI and reading sample sessions.
---

Work down the list before launch. Each line links the page that owns it.

## Keys and access

- [ ] **Start sessions from your server with an `sk_` key.** Use a `pk_` only on
  a public page, and never in a native app, which sends no `Origin`.
  [Connect your app](/build/connect/#choose-who-makes-the-request)
- [ ] **List every production origin on each `pk_`**, and only those.
  [Keys and authentication](/build/keys/#publishable-keys-pk_)
- [ ] **Know how you will rotate a key**: mint, redeploy, then revoke the old
  one. Practise it once. [Rotating a key](/build/keys/#rotating-a-key)
- [ ] **Grant members the narrowest role**, and remember `add_member` grants
  access at once. [MCP server](/reference/mcp/#members)

## The brain

- [ ] **Serve an inbound `wss://` route** behind your TLS and load balancer, and
  set it as the agent's `brain_url`. Use Cortex in production only for
  serverless or egress-only brains. [Deploy the brain](/build/hosting/)
- [ ] **Verify the brain-connection token**, which `run_session` does by
  default. Never set `allow_unverified=True` outside local development.
  [The brain-connection token](/build/hosting/#the-brain-connection-token)
- [ ] **Pin exact versions**: `voqalize-agent-sdk==0.12.0` on your server and
  `@voqalize/client-transport` at an exact version in your page.
  [Versions](/build/pipecat/#versions)
- [ ] **Handle `on_error`**, and log `overload` so you know when a lane is
  shedding frames. [Error codes](/reference/errors/#overload)
- [ ] **Run the conformance suite in CI**, plus your own scenarios, so a broken
  turn fails a build rather than a session.
  [Test the brain](/build/testing/#the-built-in-conformance-suite)

## Data and consent

- [ ] **Decide `record` from the user's consent**, per session, on your server.
  [Recordings](/operate/recordings/)
- [ ] **Send identifiers, not personal data, in `init`**: it is stored on the
  session. [Context and history](/build/brain/context/#sessioninit-send-identifiers-not-personal-data)
- [ ] **Check region and retention fit your obligations.** Sessions are
  processed and stored in India today.
  [Status and support](/overview/status/#region-and-limits)
- [ ] **Download any recording you must keep** before retention ends.
  [Status and support](/overview/status/#stored-session-data)

## Limits

- [ ] **Plan for the one-hour session cap**: a session ends with `max_duration`
  at the hour. [Usage and limits](/operate/usage/#limits)
- [ ] **Ask us about concurrency and minutes** if launch traffic may exceed your
  plan. [Usage and limits](/operate/usage/#limits)

## After launch

- [ ] **Alert on the gap** between `sessions_created` and `sessions_started`:
  a wide gap is a broken embed.
  [Usage and limits](/operate/usage/#the-gap-that-means-a-broken-embed)
- [ ] **Read a sample of sessions back** each week, the call record first,
  including `never_spoken` units and gaps.
  [Reading a call back](/operate/reading-a-call/)
- [ ] **Log the `session_id` on your side** with `configure_logging` or your own
  loguru format, so both halves of a session join.
  [Reading a call back](/operate/reading-a-call/#your-half-is-still-yours)

## Read next

- [Troubleshooting](/operate/troubleshooting/) — when something goes wrong anyway.
- [Usage and limits](/operate/usage/) — what is counted.
- [Status and support](/overview/status/) — region, retention and support.
