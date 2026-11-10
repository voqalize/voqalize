---
title: Troubleshooting
description: Symptom, usual cause and fix for the common failures, from a session that will not start to an agent that is silent, repeats itself, speaks in the wrong accent or does not move the screen. Each row links the page that owns the fix.
---

Find the symptom, check the cause, apply the fix. If no row fits,
[read the session back](#still-stuck-read-the-session-back).

## The session does not start

| Symptom | Usual cause | Fix |
|---|---|---|
| `connect` throws a `TypeError` that does not mention headers | The connect response's `headers` is a plain object, and the transport needs a `Headers` instance. | Add the one line in [Connect your app](/build/connect/#the-one-line-you-write-yourself), and call `connect` rather than `startBotAndConnect`. |
| `403` `origin_not_allowed` | The page's origin is not in the `pk_` key's allowed origins, or the request has no `Origin` at all (a server or a native app). | Add the origin with `update_api_key_origins`, or start the session from your server with an `sk_`. See [Keys and authentication](/build/keys/#publishable-keys-pk_). |
| `401` | The key is wrong, revoked, or for another agent. | Check `last_used_at` in `list_api_keys`. See [Keys and authentication](/build/keys/). |
| `409` `agent_not_configured` | The agent has no `brain_url` and no Cortex credentials. | Set a `brain_url`, or call `create_agent_credentials`. See [Deploy the brain](/build/hosting/). |
| `409` `agent_archived` | The agent is archived. | `unarchive_agent`. |
| `400` `invalid_config`, `details.code` `unsupported_language` or `unsupported_voice` | The recognizer does not hear `stt.language`, the voice is not served, or the voice does not speak `tts.language`. | Pick values from [the catalog](/reference/catalog/). |
| `400` `recording_not_permitted` | A `pk_` sent `record: true`. | Send it from your server, or set the agent's default. See [Recordings](/operate/recordings/#a-publishable-key-can-turn-recording-off-not-on). |
| `sessions_created` is far above `sessions_started` | The page mints on load, an origin is refused, or `connect` throws before the transport starts. | See [the gap that means a broken embed](/operate/usage/#the-gap-that-means-a-broken-embed). |

## The agent is silent or apologises

| Symptom | Usual cause | Fix |
|---|---|---|
| The user hears "Sorry, I'm having trouble connecting right now", then the session ends | Voqalize could not reach your brain for 10 seconds: the service is down, the `brain_url` is wrong, TLS fails, or the handshake answers `401` or `403`. `end_reason` is `brain_unreachable`. | Check the route and the token. See [Deploy the brain](/build/hosting/) and [what your user hears](/reference/errors/#what-your-user-hears). |
| The session ends at once, with `end_reason` `brain_disconnected` | Your brain closed the socket, often with `4000` after the token failed verification. | See [the brain-connection token](/build/hosting/#the-brain-connection-token). |
| The user hears "Sorry, this is taking a little longer than I expected." | A turn produced no speech within 10 seconds: the model called a tool and said nothing, or a callback raised. | Say the line in the same response as the tool call ([Tools](/build/brain/tools/#speak-first-and-call-in-the-same-response)); check your brain's logs for the exception. |
| The greeting plays, then no turn ever speaks, with `brain: turn failed` and a `TypeError` in your logs | A tool is a plain `def`. | Make every tool `async def`. See [Tools](/build/brain/tools/#async-def-is-required). |
| `on_user_idle` never fires | Idle detection is off by default. | Set `idle.timeout_ms`. See [Voice and language](/build/voice-and-language/). |

## The agent says the wrong thing

| Symptom | Usual cause | Fix |
|---|---|---|
| It refers to things the user never heard | History records what the brain generated, not what was heard. | Record `fin.heard` from `on_finalize`. See [Transcripts and heard truth](/build/brain/transcripts/). |
| The user hears two acknowledgements | Voqalize's acknowledgement is on, and your brain opens with its own. | Turn ack off, or drop your own opener. See [Speaking](/build/brain/speaking/#turn-ack-off-when-your-brain-writes-its-own). |
| Right words, wrong accent | Only one language leg was changed, or `tts.language` was never set. | Set both legs every time. See [Voice and language](/build/voice-and-language/). |
| A `configure` raises `RequestRejected` | The voice does not speak that language, or the recognizer does not hear it. | Read `code` and `detail`. See [Error codes](/reference/errors/#a-rejected-request-comes-back-on-the-request). |

## The screen does not do what the agent says

| Symptom | Usual cause | Fix |
|---|---|---|
| The brain's reply was never heard and the screen did not move | The user talked over the turn before your code reached `dispatch`, so the turn was cancelled (`never_spoken` units in the call record). An action already dispatched still arrives. | Expected barge-in behaviour. Dispatch next to the sentence it belongs with. See [Reading a call back](/operate/reading-a-call/#what-the-record-contains). |
| An action never reaches the page's handler | The action class was renamed, so the page listens for the old name. | Rename both sides together. See [Actions](/build/brain/actions/#the-class-name-is-the-wire-name). |
| Actions go missing under load, with an `overload` error | Your SDK shed frames from a full queue. | See [`overload`](/reference/errors/#overload). |
| Speech and screen disagree on a Stage site | A cue was dropped or a move failed. | Run the `stage-debug` skill. See [Stage](/build/stage/). |

## Still stuck: read the session back

Take the `session_id` from your connect response or your brain's logs, and on
[the MCP server](/reference/mcp/):

1. `get_call_record`: what was said and heard, turn by turn. Check `record` is
   `found` before concluding the session was silent.
2. `get_session_logs`: Voqalize's lines, for why.
3. `get_session_events`: how far the session got, even while it runs.

[Reading a call back](/operate/reading-a-call/) explains each. If you still need
us, send the `session_id`, or the `correlation_id` from a refused request.

## Read next

- [Reading a call back](/operate/reading-a-call/): the record, the logs and the milestones.
- [Error codes](/reference/errors/): every code and refusal.
- [Going to production](/operate/production/): avoid these before launch.
