---
name: stage-debug
description: Turn a voice session on a Stage site into a timeline of speech against screen (cues written, fired, dropped; move results and their timings; promises kept or not; silences during page loads) to find why the screen and the voice disagreed. Use when a call "didn't move the page", moved it late or wrong, or went quiet.
---

# Debugging a Stage call

You need the session id, the environment (dev or prod) and, for a local brain, its log.

## 1. Get the record

- Voqalize MCP: `whoami`, `list_tenants`, then `get_call_record(tenant, session_id,
  include_events=true)`: the transcript, every RTVI message with its time, and the
  runtime's log lines. `get_session_logs` for more lines.
- The brain's own log (a local brain prints it; a hosted one is in its service logs).

## 2. Build the timeline

Put these on one clock, in order:

| From | Lines |
|---|---|
| Voice | user transcript; agent text; `botStartedSpeaking` / `botStoppedSpeaking` |
| Brain | `stage: cN cue <verb> as <move> <args> at '<words>' before …`, `stage: cN move <move> {args} (now|quiet)`, `stage: dropped …`, `stage: backstop sentence …`, `stage: unkept …`, `turn: … speechless=yes` |
| Page | `stage_progress` (queued, loading, ringing, acting) and `stage_result` (outcome, detail, `fired`, `received_ms`, `queued_ms`, `fired_ms`, `ringed_ms`, `lag_ms`) |
| Brain | `stage: cN <move> -> <outcome> [x ms acting; sent to answered y ms]`, `stage: cN <move> never answered (last phase …); unknown`, landing lines, holding lines, `late` results |

## 3. Read it

- **A cue written but never fired**: was its result `refused` with why `interrupted` (the
  visitor spoke first), or did its words never come (`at` text that was never spoken)? A
  `fuzzy` or `clock` fire means the anchor words drifted from what the voice said.
- **Fired late**: `lag_ms` is screen behind voice. A large `queued_ms` means it waited for
  the move before it; a large `fired_ms − queued_ms` means the page was not ready (a load,
  the site's own scripts).
- **Promised, not done**: a sentence like "I'm opening the calendar" with no move that turn
  shows as `stage: unkept`. The move needs claims or objects (`stage-move` skill), or the
  brain's forced follow-up failed.
- **Wrong thing**: the result's `refused` options show what the page offered; the model named
  something else. Check the spoken labels in the spec and the prompt.
- **Silent**: `speechless=yes` turns, gaps between `botStoppedSpeaking` and the next start
  during a navigation. A page load should never silence the voice; the runtime's
  acknowledgement covers the model's thinking, not a stuck move.
- **`unknown`**: the result never came in time (timeouts are by class); a `late` result after
  it says what really happened.

## 4. Fix it in the right place

A defect on one site is a Stage question until proven otherwise: if the fix is a guard,
a policy or a timing, it goes into `voqalize.sdk.stage` or `@voqalize/stage` so every site
gets it. Add a test that replays the failing sequence, cite the session id in the commit,
and never quote the visitor's words or personal data in it.
