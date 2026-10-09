---
title: Camera and screen
description: Record a session's camera and screenshare with the stock pipecat client. Turn lanes on with enableCam and enableScreenShare, optionally cap each lane's bitrate, and read the files back on one timeline.
---

A recorded session can carry video as well as audio: the user's camera, their
screen, or both. Nothing new is installed for it. The stock pipecat client
already negotiates a camera lane and a screen lane on every connection, and
your page turns them on and off with pipecat's own calls.

What you get back, beside the audio, on a session with recording on:

| Role | File | What it is |
| --- | --- | --- |
| `composite` | `composite.mp4` | The one to watch: the screen full-frame with the camera inset, or whichever lane the session had, over the mixed audio. H.264 and AAC, so it plays in every major browser and seeks without downloading first. |
| `camera` | `camera.webm` | The camera lane as the browser sent it, VP8. |
| `screen` | `screen.webm` | The screen lane as the browser sent it, VP8. |

Every file starts at the same instant as the audio and runs the length of the
session, so a moment in the transcript or in the session's events is the same
offset in the video. A lane the page never turned on has no file, and a session
with neither lane has no `composite`. Read them with
[`get_recordings`](/operate/recordings/#what-you-get-back), where `content_type`
is `video/mp4` or `video/webm`.

Video follows the same consent as audio: `config.record` at
[`sessions.connect`](/build/connect/#recording-is-a-per-session-decision), or
the agent's default. A lane is recorded only if the page publishes it.

## Turn lanes on and off

```ts
const client = new PipecatClient({
  transport: new SmallWebRTCTransport(),
  enableMic: true,
  enableCam: false, // the camera can start on, too
});

client.enableCam(true);          // camera on
client.enableScreenShare(true);  // the browser's share picker opens
client.enableScreenShare(false); // sharing off
```

**Use only these calls.** `enableCam()` and `enableScreenShare()` are what tell
Voqalize that a lane went on or off. A page that swaps tracks some other way
still records, but a camera turned off that way reads as one that stalled, and
the video freezes on its last frame instead of showing that the lane was off.

Turning a lane on or off never renegotiates the connection, so it is instant
and the session does not drop a beat.

### When the user stops sharing from the browser

Browsers show their own "Stop sharing" bar. Pressing it ends the screen track,
and the transport does not report that. Watch the track and call
`enableScreenShare(false)` when it ends:

```ts
import { RTVIEvent } from "@pipecat-ai/client-js";

client.on(RTVIEvent.TrackStarted, (track, participant) => {
  const screen = track.getSettings().displaySurface !== undefined;
  if (!participant?.local || !screen) return;
  track.addEventListener("ended", () => client.enableScreenShare(false), {
    once: true,
  });
});
```

## Optional: the video codec

```ts
new SmallWebRTCTransport({ videoCodec: "VP8" });
```

Voqalize records VP8 and accepts only VP8 on the wire, whatever the offer
lists. Setting it here only keeps the offer small. A browser that cannot send
VP8 still connects, with its audio, and its video is not recorded.

## Optional: a bitrate cap per lane

Voqalize caps each lane's bitrate, and the browser sends what the content
needs under the cap: a still screen costs almost nothing, a busy one climbs
towards it. The defaults suit most sessions:

| Lane | Default cap | Minimum |
| --- | --- | --- |
| `camera` | 5000 kbps | 300 kbps |
| `screen` | 5000 kbps | 300 kbps |

There is no maximum. A higher cap lifts the ceiling, not what the browser sends.

To set them, add `requestData.video` to the connect params before you connect.
`requestData` is pipecat's own field, sent with every offer. Either lane may be
left out, and it takes its default.

Keep [`withRealHeaders`](/build/connect/#the-one-line-you-write-yourself), the
one line that turns the `headers` object `sessions.connect` returns into a
`Headers` instance: the stock client calls `headers.entries()`, so a plain
object throws at the offer and `connect` never settles.

```ts
const p = withRealHeaders(params);
await client.connect({
  ...p,
  webrtc_request_params: {
    ...p.webrtc_request_params,
    requestData: {
      video: {
        camera: { max_kbps: 1000 },
        screen: { max_kbps: 4000 },
      },
    },
  },
});
```

The first offer decides for the whole session. Pipecat resends `requestData`
on every offer, including a reconnect, and a later offer with different values
is ignored, not refused. The first offer's value is checked strictly:
`requestData.video` takes only `camera` and `screen`, each takes only
`max_kbps`, and `max_kbps` is a whole number at or above the minimum. Anything
else, a value below the minimum, a string or decimal, or a field such as
`max_fps`, is refused at the offer with HTTP `400`, code `invalid_config`, and
an `info` sentence saying why, and `client.connect` rejects. Use `@pipecat-ai/small-webrtc-transport` 1.10.8 or
later, which stops at a refused offer. An earlier release can resend the
refused offer and then reject with no message, so the `info` sentence never
reaches your page.

The bitrate is the only setting there is. Frame rate, resolution and how the
browser trades them off under pressure are the browser's own choices, and
asking for one in `requestData.video` refuses the session rather than being
ignored.

## Recommended capture sizes

| Lane | Capture |
| --- | --- |
| Camera | Up to 1280×720. Larger costs uplink and gains little in the composite. |
| Screen | The display's native resolution, up to 1920×1080, so text stays sharp. |

These are your page's (or the media manager's) capture constraints; Voqalize
records whatever arrives.

## Compose it yourself

`composite.mp4` is one layout. For your own, download the raw files from
[`get_recordings`](/operate/recordings/#what-you-get-back) and compose them:

| Role | What to take it for |
| --- | --- |
| `camera`, `screen` | The picture, each lane as the browser sent it (VP8 WebM). |
| `audio` | The sound, both sides in one mono track. Or take `user_audio` and `agent_audio` to place the two sides yourself. |

Every file starts at the session's start (`started_at`) and runs its whole
length, so no offsets are needed: a moment is the same time in each. Keep each
file's own timestamps when you read it, because a lane's first frame is not at
zero when the lane came on later. In ffmpeg that is `-copyts`.

### The timeline: off is not frozen

While a lane is off its file has no frames, and a player holds the last one,
so a camera that was switched off and a camera whose picture froze look the
same. A `camera` or `screen` entry whose lane rendered carries a `timeline`
that tells them apart. It is `null` on every other role, and also on a lane
entry whose render failed or that was recorded before the field existed, so
check for it before reading it. Every time in it is in seconds from
the session's start, to the millisecond:

```json
{
  "episodes": [
    { "start_secs": 1.02, "end_secs": 2.53, "closed_by": "off" },
    { "start_secs": 4.02, "end_secs": 7.53, "closed_by": "off" }
  ],
  "freezes": [
    { "start_secs": 0.0, "end_secs": 1.02, "reason": "off" },
    { "start_secs": 2.53, "end_secs": 4.02, "reason": "off" },
    { "start_secs": 7.53, "end_secs": 8.6, "reason": "off" }
  ],
  "resolutions": [{ "at_secs": 1.02, "width": 1280, "height": 720 }],
  "sync": "sr",
  "truncated": false
}
```

- `episodes` are the spans the lane was on. `closed_by` says what ended one:
  `off` (your page switched it off), `stall` (its media stopped and nothing
  said why) or `end` (the session ended first).
- `freezes` are the spans the picture does not move, and `reason` says what
  to show:

  | `reason` | What happened | What to show |
  | --- | --- | --- |
  | `off` | The lane was off. | Black, or your placeholder. Not the last frame. |
  | `stall` | Its media stopped arriving. | Hold the last frame, or mark it as interrupted. |
  | `loss` | Frames were lost on the way. | Hold the last frame, or mark it. |

  A still screen sends almost nothing and is not a freeze: holding its last
  frame is the picture.

- `resolutions` are the picture's size from `at_secs` on. It can change
  mid-file, and a screen is whatever shape the shared window or display was,
  not necessarily widescreen. Scale each picture to fit your layout rather than
  assuming one size.
- `sync` is a quality flag. `sr` means the lane is on the sender's own clock,
  in sync with the audio. `arrival` means some of it was placed by when its
  frames arrived, so lip sync there is approximate. `null` means no frame of
  the lane could be placed.
- `truncated` is `true` only when a very long, troubled session filled one of
  the lists, and then only its earliest rows are kept.

`composite.mp4` already follows these rules: a lane shows black, or is hidden,
while it is off.

### An ffmpeg example

The camera inset bottom right over the screen, with the `audio` track. Each
`enable` is that lane's `episodes`, one `between` per episode, so the canvas
shows black while a lane is off instead of its last frame. The camera's spans
are the example timeline's above; the screen's come from its own entry the
same way:

```sh
ffmpeg -copyts -i screen.webm -i camera.webm -i audio.webm -filter_complex "
  color=black:size=1280x720:rate=30[bg];
  [0:v]scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:-1:-1[screen];
  [1:v]scale=-2:180[cam];
  [bg][screen]overlay=eof_action=pass:enable='between(t,3.02,6.03)'[base];
  [base][cam]overlay=W-w-16:H-h-16:eof_action=pass:enable='between(t,1.02,2.53)+between(t,4.02,7.53)'[v]" \
  -map "[v]" -map 2:a -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest composed.mp4
```

To build an `enable` from a lane's entry, saved as JSON:

```sh
jq -r '[(.timeline.episodes // [])[] | "between(t,\(.start_secs),\(.end_secs))"] | join("+")' camera.json
```

A session with only one lane leaves out the other's input and overlay.

## Read next

- [Recordings](/operate/recordings/) — who may turn recording on, each file's
  state, and the download URL.
- [Connect your app](/build/connect/) — the connect request and the
  `withRealHeaders` line this page builds on.
- [Pipecat client SDKs](/build/pipecat/) — what is pipecat's and which
  versions we hold to.
