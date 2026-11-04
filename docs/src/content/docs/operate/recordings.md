---
title: Recordings
description: Recording is off by default and decided per session. Who may turn it on (not a publishable key), the files you get back per role, what each state means, and the short-lived download URL.
---

Recording is **off by default** and is decided for each call, at the moment the
session is minted. Most calls have none, and an empty list from `get_recordings`
is a real answer rather than a missing one.

## Who decides

The `record` value in `sessions.connect`'s `config` takes precedence over the
agent default, so your server can apply the user's consent for each session.

| `config.record` | What happens |
|---|---|
| `record: true` | Recorded |
| `record: false` | Not recorded, whatever the agent's default says |
| omitted | The agent's configured default, which itself defaults to off |

## A publishable key can turn recording off, not on

:::caution[`record: true` with a `pk_` is refused]
A `pk_` ships in page source, so it may honour an opt-out but cannot authorize
storing new audio or video. `record: true` from a `pk_` is a `400` with code
`recording_not_permitted`, and no session starts. Send it from your server with
the `sk_` instead.
:::

A `pk_` embed that wants recording sets the **agent's** default, which its owner
controls: `update_agent(recording=true)` over
[the MCP server](/reference/mcp/), or the same switch in the console.

See [keys and authentication](/build/keys/).

## What you get back

`get_recordings(tenant, session_id)` returns one entry **per role**. Every
recorded session has the audio roles: `user_audio` (the user's microphone),
`agent_audio` (what was spoken back) and `audio` (those mixed). Each reports an
entry whatever happened to it, so you can tell "the agent never spoke" from "the
agent was not recorded".

A session whose page turned on the camera or shared a screen also has video:

| Role | `content_type` | What it is |
|---|---|---|
| `camera`, `screen` | `video/webm` | Each lane as the browser sent it, VP8. A lane the page never turned on has no entry. |
| `composite` | `video/mp4` | The one to watch: the screen full-frame with the camera inset, or whichever lane the session had, over `audio`. H.264 and AAC. A session with no video has none. |

`camera` and `screen` also carry a `timeline`: when the lane was on, when its
picture froze and why, its resolution over time, and whether it is in sync with
the audio. It is `null` on every other role and on a lane whose render failed.
[Camera and screen](/build/video/#the-timeline-off-is-not-frozen) turns the
lanes on, and reads the timeline field by field.

**`audio` is the one to play back.** Inspect the separate tracks when you need
the channels apart. `audio` is mixed from both, so it renders only when both
did.

Every file, video included, carries the same `started_at`, `ended_at` and
`duration_secs` and runs from the moment the session connected to the moment it
ended, gaps padded with silence. So a moment in the session's events is the same
offset in every file, and an audio track is as long as the
[usage](/operate/usage/) counted. Each entry also carries its `state`,
`size_bytes`, `content_type` and any `failure_reason`.

## Recording is captured, then rendered

During the session Voqalize captures each recorded track raw; when it ends, it
renders `user_audio.webm`, `agent_audio.webm`, `audio.webm`, any `camera.webm`
and `screen.webm`, then `composite.mp4`. The raw capture is stored beside them,
as `capture_object`, so a track can be rendered again later.

## What each state says is in storage

| `state` | What is in storage |
|---|---|
| `completed` | The rendered file. This is the one to play. |
| `unrendered` | The capture, and no usable rendered file. `failure_reason` says why, and re-rendering from the capture can recover it. |
| `failed` | Nothing. The upload to storage failed. |

A render that produced only a partial file stores it as `{role}.failed.webm`
(`composite.failed.mp4` for the composite), so it is never mistaken for the
rendered file.

## Whether the recording arrived

```python
get_session(tenant, session_id)["files"]["recording"]
# {"status": "uploaded", "reason": null, "size_bytes": 412331, "updated_at": "…"}
```

`status` is `expected` until Voqalize says what became of the recording, then
`uploaded`, `failed` or `skipped`. `failed` and `skipped` carry a `reason`:
`skipped` means there was never going to be a recording — it was off, or the
session never connected. An `uploaded` recording carries a `reason` when the
session was interrupted and the recording was rebuilt from what had been
captured: it plays, and it may end before the session did. A recording that read
`failed` changes to `uploaded` if it is rebuilt later; an `uploaded` one never
changes back. An `expected` recording is looked up in storage an hour
after the session ends, and reads `uploaded` if it is there and `lost` if it is
not. Read this before concluding that an empty `get_recordings` list means the
call was not recorded. See [reading a call back](/operate/reading-a-call/).

## The download URL is a credential

An entry in state `completed` carries a `download_url`: a short-lived signed URL
you fetch with a plain unauthenticated `GET`. An `unrendered` entry carries one
only when the render left a `{role}.failed.*` file behind, and that file is the
partial one rather than the rendered file.

It carries its own credential, so treat it as a secret. Do not write it anywhere
durable: not a ticket, a log line or a spreadsheet.

| `ttl_seconds` | |
|---|---|
| Range | 60 to 1200 seconds |
| Default | 1200 (twenty minutes) |

A download that starts before the URL expires runs to the end. Ask for a fresh
URL rather than holding one, including to resume a download.

The URL lifetime is not the retention period, which is on
[Status and support](/overview/status/). Download anything you need to keep.

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
- [Camera and screen](/build/video/) — turning the video lanes on, and composing them yourself.
