---
title: Operate
description: Run an agent in production. Troubleshoot a bad session, go live with the checklist, read a session back by session_id, retrieve recordings, and check usage and limits.
---

Start here when something went wrong, or before you launch.

- [Troubleshooting](/operate/troubleshooting/) — a symptom, its usual cause, and the fix.
- [Going to production](/operate/production/) — the checklist before real users arrive.
- [Reading a call back](/operate/reading-a-call/) — one session, by its `session_id`.
- [Recordings](/operate/recordings/) — turning them on, and what you get back.
- [Usage and limits](/operate/usage/) — what is counted, and the limits that apply.

## Read one session back

Every session has a `session_id`, the same string in your connect response, in
the URL Voqalize dials your brain at, and in your brain's logs. It joins
Voqalize's records to yours. Read in this order:

| Read | What it is | Available |
|---|---|---|
| **The call record** (`get_call_record`) | What was said and what the user heard, turn by turn. **The contract**: versioned and safe to assert on in a test. | When the session ends |
| **Logs** (`get_session_logs`) | Voqalize's own lines: why something happened. Evidence, free to change. | When the session ends |
| **Milestones** (`get_session_events`) | Created, connected, ended: how far the session got. | While it runs |
| **The recording** (`get_recordings`) | What it sounded like. Off by default. | When the session ends |

Your brain logs in your own environment; conversation history is yours, and
Voqalize does not keep it. How long Voqalize keeps session data is on
[Status and support](/overview/status/).

## From your editor

All of these reads are tools on [the MCP server](/reference/mcp/), so your
coding agent can list sessions, read one back and check an agent's
configuration without leaving the editor. The console shows the same sessions.

## Read next

- [Troubleshooting](/operate/troubleshooting/) — start from the symptom.
- [Reading a call back](/operate/reading-a-call/) — the record first, then the logs.
- [Error codes](/reference/errors/) — what a code means and whether it ended the session.
