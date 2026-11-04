---
title: Examples
description: Complete Voqalize demos, grouped by the pattern each shows best (screen actions, Stage, background work, per-session init, authenticated tools, multilingual, the avatar), each with a live link and its source.
---

Each demo is a complete app: a `frontend/` (the client on
`@voqalize/client-transport` in a Vite app) and a `backend/brain.py`; the avatar's page is its own documentation page. Try one
live, then read its brain end to end. Every brain here is a `GeminiBrain`; the
same patterns work on `OpenAIBrain` and `LiteLLMBrain`.

## The brain drives the screen

The agent talks and, in the same turn, dispatches [actions](/build/brain/actions/)
that the page renders. Clicks and form input come back to the brain as app
events.

| Demo | What it shows | Links |
|---|---|---|
| **Travel Advisor** | Builds a client itinerary on screen as a travel agent talks; edits one row at a time. Has the avatar. | [Live](https://voqalize.com/demos/travel/) · [Source](https://github.com/voqalize/voqalize/tree/main/demos/travel) |
| **Mobile Expert** | Walks a phone buyer through a store and fills their cart; one search tool returns results the model reads before answering. | [Live](https://voqalize.com/demos/shopping/) · [Source](https://github.com/voqalize/voqalize/tree/main/demos/shopping) |
| **Returns Assistant** | Looks up an order and drives a returns flow; a photo upload arrives as an app event without taking a turn. | [Live](https://voqalize.com/demos/support/) · [Source](https://github.com/voqalize/voqalize/tree/main/demos/support) |
| **Flowforge** | An admin assembles a workflow by talking; every edit names a block read off the screen. | [Live](https://voqalize.com/demos/forge/) · [Source](https://github.com/voqalize/voqalize/tree/main/demos/forge) |
| **Petwell Appointment Desk** | Books a vet visit on a website, moving the visitor between pages; ten languages. Has the avatar. | [Live](https://voqalize.com/demos/petwell/) · [Source](https://github.com/voqalize/voqalize/tree/main/demos/petwell) |

## Stage

[Stage](/build/stage/) declares the moves an agent may make on a page in one
spec, and can make each one as the voice reaches the words it belongs to.

| Demo | What it shows | Links |
|---|---|---|
| **Fernhollow Home** | A design adviser furnishes a room by voice: sets within budget, comparisons, look-alikes and sale prices on screen. Has the avatar. | [Live](https://voqalize.com/demos/fernhollow/) · [Source](https://github.com/voqalize/voqalize/tree/main/demos/fernhollow) |

## Work that runs in the background

The agent starts slow work, says so, and keeps talking while the results fill
the screen.

| Demo | What it shows | Links |
|---|---|---|
| **Docket: Contract Review** | Follows counsel reading a contract, marks clauses, and fans diligence out in parallel. Has the avatar. | [Live](https://voqalize.com/demos/legal/) · [Source](https://github.com/voqalize/voqalize/tree/main/demos/legal) |
| **Meridian Servicing Desk** | A mortgage advisor's copilot prepares one case while the advisor works another; the case queue arrives in `init`. Has the avatar. | [Live](https://voqalize.com/demos/servicing/) · [Source](https://github.com/voqalize/voqalize/tree/main/demos/servicing) |

## The app passes the user's context

The page's server sends what the brain needs about this user in
[`init`](/build/brain/context/), and the brain reads it in `on_session_start`.

| Demo | What it shows | Links |
|---|---|---|
| **AI Interviewer** | The job, the candidate and the interview plan arrive per session; tools pace the sections. | [Live](https://voqalize.com/demos/interview_bot/) · [Source](https://github.com/voqalize/voqalize/tree/main/demos/interview_bot) |
| **Sugar Coach** | A daily diabetes check-in whose patient and scenario ride `init`; logs meals by voice and can switch to Hindi. | [Live](https://voqalize.com/demos/sugar/) · [Source](https://github.com/voqalize/voqalize/tree/main/demos/sugar) |

## Rules in code, decisions on screen

The brain keeps what must be right (sign-in, eligibility, catalog matches) in
code, and the user confirms on screen.

| Demo | What it shows | Links |
|---|---|---|
| **Aura Bank Support** | Signs the customer in on screen, then reads balances and statements with a handle the model can only pass back. | [Live](https://voqalize.com/demos/aura/) · [Source](https://github.com/voqalize/voqalize/tree/main/demos/aura) |
| **Vantage Bank Card Kiosk** | Asks four questions and ranks three cards; eligibility runs in Python, and figures are spoken from words the tool wrote. Bilingual, with the avatar. | [Live](https://voqalize.com/demos/kiosk/) · [Source](https://github.com/voqalize/voqalize/tree/main/demos/kiosk) |

## Multilingual

The brain sets the language for this user on both legs, and can switch it
mid-session. See [Voice and language](/build/voice-and-language/).

| Demo | What it shows | Links |
|---|---|---|
| **Auric Gold Loan Advisor** | Picks the language from the enquiry form's state before the greeting, and switches between Indic languages mid-session. | [Live](https://voqalize.com/demos/lead_qual/) · [Source](https://github.com/voqalize/voqalize/tree/main/demos/lead_qual) |
| **OrderDesk: B2B Order Intake** | Takes spoken bulk orders in Hindi, resolves them against a real 20,000-SKU catalog, and asks one short question when a match is ambiguous. The user presses Confirm. | [Live](https://voqalize.com/demos/orderdesk/) · [Source](https://github.com/voqalize/voqalize/tree/main/demos/orderdesk) |

## The avatar

| Demo | What it shows | Links |
|---|---|---|
| **The Avatar** | An animated character that explains itself, scrolling the page to the answer and gesturing from the brain. Face and voice are chosen before the session. Its page is the avatar's own documentation page. | [Live](/build/avatar/) · [Brain](https://github.com/voqalize/voqalize/tree/main/demos/avatar/backend) · [Page](https://github.com/voqalize/voqalize/blob/main/docs/src/scripts/avatar-live.ts) |

## Read next

- [Status and support](/overview/status/): versions, clients, region and pricing.
- [Build an agent](/build/): every step, in order.
- [Build the brain](/build/brain/): the callbacks these demos implement.
