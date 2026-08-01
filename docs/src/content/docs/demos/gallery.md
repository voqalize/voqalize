---
title: Demo gallery
description: Ten complete, runnable voice apps — each a Brain plus a UI, and the reference for how real agents are built.
---

The [`demos/`](https://github.com/voqalize/voqalize/tree/main/demos) directory
holds ten complete voice applications. Each is a real example, a live demo, and
an integration test at once. They share one architecture, so reading two or three
teaches the whole pattern.

## The shared spine

Every demo is **one brain + one UI**, co-located under `demos/<name>/`:

- **Backend** — one umbrella FastAPI app discovers and hosts every brain (it scans
  `demos/*/backend`, so nothing binds names in a central registry). Each brain
  subclasses a small `GeminiBrain` that runs a manual function-calling loop where
  one model call maps 1:1 to the wire. A brain owns only its prompt, its tool
  schemas, and its session state; the transcript is framework-owned.
- **Frontend** — each demo is a self-contained Vite app built at base
  `/demos/<name>/`, embedding the public `@voqalize/client-react` SDK.
- **Deploy** — the two halves ship to two places. The **brains** build into one
  container that runs on the pygato voice-runtime node, behind Caddy
  (`brain_url = wss://brain.voqalize.com/{name}`, dialed server-side per
  session). The **UIs** build into a versioned web artifact served
  under the apex domain at `/demos/<name>`, same-origin with these docs and the
  marketing site; the apex rewrites `/api/*` to the control plane so a demo mints
  its session same-origin.

The URL segment for each demo is its `name` (the first column below).

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
| **`aura`** — Aura Bank Support | An authenticated L1 banking-support agent that signs the customer in, reads their accounts, and drives on-screen how-to videos. | Secure sign-in, authenticated account access, journey-aware cross-sell, and driving on-screen how-to content. |
| **`forge`** — Flowforge | A voice workflow studio where an ITSM/HR admin assembles, tests, and ships Service Request Workflows by talking to a copilot. | Block-based statechart editing by voice, a governed connector catalog, surfacing and resolving untested edge cases, and running tests live on screen. |

## Reading them

Start with **`travel`** — it's the most complete demo. Then pick a demo whose
*shape* matches what you're building:

- **Screen-driving** (highlight, fill, navigate) → `shopping`, `servicing`, `legal`, `forge`.
- **Reading what the user shows the agent** → `support` (photo upload).
- **Per-session scenario in the payload** → `interview_bot`, `sugar`.
- **Authenticated account access** → `aura` (secure sign-in, then reads accounts).
- **Voice-only + multilingual** → `lead_qual`.

Each demo is co-located under
[`demos/<name>/`](https://github.com/voqalize/voqalize/tree/main/demos): its brain
in `demos/<name>/backend/` and its UI in `demos/<name>/frontend/`.

## Next

- **[Handling a conversation](/docs/brain/conversation/)** — the patterns these
  demos are built from.
- **[Build a brain (Python)](/docs/brain/python/)** — the SDK they use.
