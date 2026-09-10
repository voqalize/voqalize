---
title: Recordings
description: Off by default, decided per call, one audio track per role. Who is allowed to turn recording on, why a publishable key is not, and what each recording state says is in storage.
---

Recording is **off by default** and is decided for each call, at the moment the
session is minted. Most calls have none, and an empty list from `get_recordings`
is a real answer rather than a missing one.

## Who decides

The session creator's explicit `record` value takes precedence over the agent
default. This lets your backend apply the user's consent for each call.

| What the mint request says | What happens |
|---|---|
| `record: true` | Recorded |
| `record: false` | Not recorded, whatever the agent's default says |
| omitted | The agent's configured default, which itself defaults to off |

Omitting the field uses the agent default. Sending `false` explicitly disables
recording for that call.

## One asymmetry, and it is about which key you hold

**A publishable (`pk_`) key may turn recording off. It may not turn it on.**

A `pk_` key ships in page source. It may honor an opt-out, but it cannot authorize
storage of new audio for an agent whose owner did not enable recording.

That refusal is an HTTP `400` with code `recording_not_permitted`, and it starts
no call. Handle the error where the session is created.

A `pk_` embed that wants recording sets the **agent's** default, which its owner
controls: `update_agent(recording=true)` over
[the MCP server](/reference/mcp/), or the same switch in the console.

See [keys and authentication](/build/keys/).

## What you get back

`get_recordings(tenant, session_id)` returns one entry **per role**: `role` is
`user` (the user's microphone) or `agent` (what was spoken back). Every role
reports one entry, whatever happened to it.

Separate tracks let you inspect the user and agent channels independently. This
distinguishes missing agent audio from missing user audio.

Each entry carries its state, duration, size, content type, and a
`failure_reason` if it has one.

## Recording runs in two passes

During the session the node writes the raw RTP of both tracks to disk, undecoded
— no codec work and no timestamp arithmetic on the call path. At teardown it
renders one WebM track per role, `user.webm` and `agent.webm`, each running from
the session's start to its end: gaps are padded with silence and the two tracks
are sample-aligned, so both come out the same length and one offset names the
same instant in both.

The raw capture uploads beside the tracks as `capture.tar.gz` —
`capture-user.rtpcap`, `capture-agent.rtpcap`, `events.jsonl` and `render.json`
— so a recording can be rendered again later.

## What each state says is in storage

| `state` | What is in storage |
|---|---|
| `completed` | The rendered track. This is the one to listen to. |
| `unrendered` | The capture, and no usable rendered track. `failure_reason` says why the render produced none, and a later re-render recovers the audio from the capture. |
| `failed` | Nothing. The upload to storage failed. |

`capture_bucket` and `capture_object` are on every entry whose capture uploaded,
`completed` included: the capture is the source and a rendered track is derived
from it, so a track that plays back fine is still re-renderable.

A render that produced a partial file uploads it as `{role}.failed.webm`, so
neither a listing of the prefix nor a download mistakes it for the rendered
track.

`truncated` reads on sessions recorded before 2026-09-09 and is no longer
produced.

## The download URL is a credential

An entry in state `completed` carries a `download_url`: a short-lived signed URL
you fetch with a plain unauthenticated `GET`. An `unrendered` entry carries one
only when the render left a `{role}.failed.webm` behind, and that file is the
partial one rather than the track.

It carries its own credential, so treat it as a secret. Do not write it anywhere
durable — not a ticket, not a log line, not a spreadsheet. `ttl_seconds` sets its
lifetime between 60 and 900 seconds, defaulting to the maximum. Fifteen minutes is
long enough to download and short enough that a leaked URL is dead by the time
anyone finds it.

Ask for a fresh one rather than holding one.

The URL lifetime is not a retention promise. During developer preview,
recording retention is neither configurable nor guaranteed. Download anything
you need to keep, and do not build around an assumed retention interval. See
[current status and supported environments](/overview/status/).

## Which rule decided, after the fact

The call's `session.created` event carries `recording_enabled` and
`recording_source` — `client` when the mint request said so, `agent_default` when
it did not. That is how you answer "why was this call not recorded" without
guessing. See [reading a call back](/operate/reading-a-call/).

`get_session` also carries the same recordings without URLs, for when you only
need to know whether any exist.

## Read next

- [Reading a call back](/operate/reading-a-call/) — the record first, logs second, audio last.
- [Keys and authentication](/build/keys/) — why the key you hold changes what you may ask for.
