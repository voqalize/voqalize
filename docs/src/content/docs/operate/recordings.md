---
title: Recordings
description: Off by default, decided per call, one file per role — audio always, video when the page turns on the camera or screen. Who is allowed to turn recording on, why a publishable key is not, and what each recording state says is in storage.
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
storage of new audio or video for an agent whose owner did not enable recording.

That refusal is an HTTP `400` with code `recording_not_permitted`, and it starts
no call. Handle the error where the session is created.

A `pk_` embed that wants recording sets the **agent's** default, which its owner
controls: `update_agent(recording=true)` over
[the MCP server](/reference/mcp/), or the same switch in the console.

See [keys and authentication](/build/keys/).

## What you get back

`get_recordings(tenant, session_id)` returns one entry **per role**. Every
recorded session has the audio roles: `user_audio` (the user's microphone),
`agent_audio` (what was spoken back) and `audio` (those summed). Each of them reports an entry
whatever happened to it — a caller who can only see the tracks that worked
cannot tell "the agent never spoke" from "we never recorded the agent".

A session whose page turned on the camera or shared a screen also has video:

| Role | `content_type` | What it is |
|---|---|---|
| `camera`, `screen` | `video/webm` | Each lane as the browser sent it, VP8. A lane the page never turned on has no entry. |
| `composite` | `video/mp4` | The one to watch: the screen full-frame with the camera inset, or whichever lane the session had, over `audio`. H.264 and AAC. A session with no video has none. |

`camera` and `screen` also carry a `timeline` — when the lane was on, when its
picture froze and why, its resolution over time, and whether it is in sync with
the audio — because a lane's file alone cannot tell "the camera was off" from
"the picture froze". It is `null` on every other role, and on a lane whose
render failed or that was recorded before the field existed.
[Camera and screen](/build/video/#the-timeline-off-is-not-frozen) turns the
lanes on, and reads the timeline field by field.

**`audio` is the one to play back.** The separate tracks are what you inspect
when you need the channels apart, because missing agent audio is a different
fault from missing user audio, and they are the primary sources `audio` is
rendered from. So `audio` exists only when both of them rendered; when one did
not, it reports the way an unrendered track does.

All of them, video included, carry the same `started_at`, `ended_at` and
`duration_secs` — one anchor, read once, so you can lay them on a single
timeline without first checking that they agree. A moment in the session's
events is the same offset in every file.

Each entry also carries its state, size, content type, and a `failure_reason` if
it has one.

## Recording runs in two passes

During the session the node writes the raw RTP of every recorded track to
disk, undecoded — no codec work and no timestamp arithmetic on the call path.
When the session ends it renders `user_audio.webm` and `agent_audio.webm`, each running from
the moment the call connected to the moment it ended: gaps are padded with
silence and they are sample-aligned, so both come out the same length and one
offset names the same instant in both. `audio.webm` is those summed. Connect and
end are the instants `duration_secs` is measured between, so a completed track
is as long as the session it came from — see [usage and limits](/operate/usage/).

A video lane is placed on the same timeline and written as `camera.webm` or
`screen.webm` without being re-encoded. `composite.mp4` is rendered after them,
from the lanes and `audio`.

The raw capture uploads beside the files as `capture.tar.gz` — a
`capture-{role}.rtpcap` per captured track, `sender-reports.rtpcap` (the clock
the video lanes are placed by), `events.jsonl` and `render.json` — so a
recording can be rendered again later.

## What each state says is in storage

| `state` | What is in storage |
|---|---|
| `completed` | The rendered file. This is the one to play. |
| `unrendered` | The capture, and no usable rendered file. `failure_reason` says why the render produced none, and a later re-render recovers the file from the capture. |
| `failed` | Nothing. The upload to storage failed. |

`capture_bucket` and `capture_object` are on every entry whose capture uploaded,
`completed` included: the capture is the source and a rendered track is derived
from it, so a file that plays back fine is still re-renderable.

A render that produced a partial file uploads it as `{role}.failed.webm`
(`composite.failed.mp4` for the composite), so neither a listing of the prefix
nor a download mistakes it for the rendered file.

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
durable — not a ticket, not a log line, not a spreadsheet. `ttl_seconds` sets its
lifetime between 60 and 900 seconds, defaulting to the maximum. Fifteen minutes is
long enough to download and short enough that a leaked URL is dead by the time
anyone finds it.

Ask for a fresh one rather than holding one.

The URL lifetime is not the retention period. Recordings are retained for 30
days; download anything you need to keep longer. See
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
- [Camera and screen](/build/video/) — turning the video lanes on, and composing them yourself.
