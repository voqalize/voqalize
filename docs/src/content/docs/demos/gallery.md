---
title: Demo gallery
description: Eight complete, runnable voice apps — each a Brain plus a UI, and the reference for how real agents are built.
---

The [`demos/`](https://github.com/voqalize/voqalize/tree/main/demos) directory
holds eight complete voice applications. Each is a real example, a live demo, and
an integration test at once. They share one architecture, so reading two or three
teaches the whole pattern.

## The shared spine

Every demo is **one brain + one UI**, bound by a single registry
(`demos/manifest.json`):

- **Backend** — one umbrella FastAPI app hosts every brain and serves the built UI.
  Each brain subclasses a small `GeminiBrain` that runs a manual function-calling
  loop where one model call maps 1:1 to the wire. A brain owns only its prompt, its
  tool schemas, and its session state; the transcript is framework-owned.
- **Frontend** — a Vite multi-page app, one `.html` + entry per demo, all reading
  the same manifest.
- **Deploy** — all demos build into one container and run as one service, routed by
  path: `/{name}` serves the UI, `/{name}/s/{session_id}` is the brain WebSocket
  (so `brain_url = wss://demos.voqalize.com/{name}`), and `/api/*` proxies to the
  control plane.

The URL segment for each demo is its manifest `name` (the first column below).

## The demos

| Name | What it is | Showcases |
|---|---|---|
| **`travel`** — Travel Advisor | A voice trip-planning copilot that builds a client itinerary on screen as the agent talks. | The reference demo. LLM-generated itinerary data, screen-driving tools, parallel background flight/hotel search, two-way sync. |
| **`shopping`** — Mobile Expert | A shopping assistant that walks a phone buyer through the store and fills their cart on screen. | Filter / compare / add-to-cart driven on screen; catalog data returned to the model so it can talk about what's displayed. |
| **`support`** — Returns Assistant | A returns-and-support agent that looks up an order and drives the on-screen returns flow. | Order lookup + form fill; **reading a product photo the user uploads** (an app event triggers an agent-initiated inference); deflecting unneeded returns. |
| **`servicing`** — Meridian Servicing Desk | A copilot for a mortgage-servicing *advisor* working their case queue. | The user is a staff advisor, not a customer. Parallel case work-up, approval drafting, catching a blocker that gates a regulated step; live on-screen state via `state_sync`. |
| **`interview_bot`** — AI Interviewer | A job-interview bot; the job, candidate, and plan arrive per session in the payload. | Structured interview driven entirely by `start.init`; section-pacing tools. |
| **`sugar`** — Sugar Coach | A daily diabetes habit check-in the app places to the patient each evening. | A proactive, scheduled in-app call; voice→data meal logging; medication/exercise confirmation; a clinical safety guardrail; payload context + screen echo. |
| **`legal`** — Docket — Contract Review | An ambient copilot for in-house counsel reviewing a vendor contract, marking clauses on screen. | Ambient document-driving (comment, redline, insert a clause, route for approval); streaming the reader's position via **silent** events to ground ambiguous questions. |
| **`lead_qual`** — Auric Gold Loan Advisor | A multilingual lead-qualification bot that walks an enquiry through to a qualified call. | **Voice-only, no screen.** Deterministic eligibility rules and **switching STT+TTS language mid-call** into another Indic language. |

## Reading them

Start with **`travel`** — it's the most complete and the one both the Python and Go
SDKs implement, so you can compare languages side by side. Then pick a demo whose
*shape* matches what you're building:

- **Screen-driving** (highlight, fill, navigate) → `shopping`, `servicing`, `legal`.
- **Reading what the user shows the agent** → `support` (photo upload).
- **Per-session scenario in the payload** → `interview_bot`, `sugar`.
- **Voice-only + multilingual** → `lead_qual`.

Each demo is co-located under
[`demos/<name>/`](https://github.com/voqalize/voqalize/tree/main/demos): its brain
in `demos/<name>/backend/` and its UI in `demos/<name>/frontend/`.

## Next

- **[Handling a conversation](/docs/brain/conversation/)** — the patterns these
  demos are built from.
- **[Build a brain (Python)](/docs/brain/python/)** — the SDK they use.
