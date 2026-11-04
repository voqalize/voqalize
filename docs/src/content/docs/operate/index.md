---
title: Operate
description: Run an agent in production. Troubleshoot a bad session, go live with the checklist, read a session back by session_id, retrieve recordings, and check usage and limits.
---

Start here when something went wrong, or before you launch.

- [Troubleshooting](/operate/troubleshooting/): a symptom, its usual cause, and the fix.
- [Reading a call back](/operate/reading-a-call/): one session, by its `session_id`.
- [Recordings](/operate/recordings/): turning them on, and what you get back.
- [Going to production](/operate/production/): the checklist before real users arrive.
- [Usage and limits](/operate/usage/): what is counted, and the limits that apply.

Every session has a `session_id`, the same string in your connect response, in
the URL Voqalize dials your brain at, and in your brain's logs. Start every
investigation from it: [Reading a call back](/operate/reading-a-call/) has the
reads and the order to take them in. How long Voqalize keeps session data is on
[Status and support](/overview/status/).

## From your editor

The session reads are tools on [the MCP server](/reference/mcp/), so your
coding agent can list sessions, read one back and check an agent's
configuration without leaving the editor. The console shows the same sessions.

## Read next

- [Troubleshooting](/operate/troubleshooting/): start from the symptom.
- [Reading a call back](/operate/reading-a-call/): the record first, then the logs.
- [Error codes](/reference/errors/): what a code means and whether it ended the session.
