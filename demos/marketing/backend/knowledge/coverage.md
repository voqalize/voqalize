# Coverage audit

Every question in [`questions.md`](questions.md), against what
[`L1.md`](L1.md) and `l2/` actually contain. Ids are the ones in that file.

**Tier meanings**

- **L1** — the agent answers from the core document, no second read. Includes
  questions whose correct answer is *"we don't publish that"*: refusing to
  improvise is an answer, and L1 carries the refusal list.
- **L1 thin** — L1 has a true, sufficient answer for the question **as asked**,
  but the obvious follow-up is a step deeper. The agent answers, then offers.
- **L2** — L1 does not carry enough; the agent reads exactly one `l2/` file.

Nothing in the set needs more than one `l2/` read, and nothing is uncovered.

---

## The table

| # | Topic | Tier | Where |
|---|---|---|---|
| 1 | integration | L1 | Facts → Integration, first bullet |
| 2 | wire-format | L1 | Facts → The wire |
| 3 | wire-format | **L2** | `wire-and-brain.md`, then `/reference/wire` for the frame set itself |
| 4 | ui-actions | L1 | Facts → The wire, typed pydantic + generated unions |
| 5 | auth | L1 | Facts → Keys and auth, brain-connection token |
| 6 | deployment-mode | L1 | Facts → Deployment |
| 7 | session-init | L1 | Facts → Integration, connect body |
| 8 | architecture | L1 | Facts → Integration, "Behind the URL, anything" |
| 9 | failure-modes | L1 | Facts → Runtime, the ten-second watchdog |
| 10 | failure-modes | L1 | Facts → Runtime, "the socket is the session" |
| 11 | latency | L1 | Not known or not committed — no figure is published |
| 12 | limits | L1 | Facts → Runtime, session cap and idle |
| 13 | interruption | L1 | Facts → Runtime, heard prefix on `Finalize` |
| 14 | async | **L2** | `wire-and-brain.md` → async work that outlives its turn |
| 15 | state-sync | L1 | Facts → The wire, `ui-event` / `AppEvents.parse` |
| 16 | sdk | **L2** | `connect-and-clients.md` → the client is pipecat |
| 17 | mobile | **L2** | `connect-and-clients.md` → the client is pipecat |
| 18 | languages | L1 | Facts → Integration, last bullet |
| 19 | mcp | L1 thin | Facts → Keys and auth + Observability reads; full tool surface in `connect-and-clients.md` |
| 20 | local-dev | **L2** | `connect-and-clients.md` → local development |
| 21 | state | L1 | Facts → Integration, "State is the brain's" |
| 22 | self-host | L1 | Facts → Deployment, "nothing phoning home" |
| 23 | data-retention | L1 | Facts → Integration (direct UDP) + Observability (stored / not stored) |
| 24 | data-retention | L1 | Facts → Observability, "keep your own copy" |
| 25 | compliance | L1 | Facts → Deployment + Not known (the SOC 2 type) |
| 26 | self-host | L1 | Facts → Deployment + Not known (GPU sizing) |
| 27 | avatar | L1 | Facts → Avatar, MIT and standalone by design |
| 28 | speech | L1 | Facts → Speech, last bullet |
| 29 | languages | **L2** | `speech-and-languages.md`, then `/reference/catalog` for the roster |
| 30 | speech | L1 | Facts → Speech, mid-call switching |
| 31 | testing | L1 | Facts → Observability, the conformance harness |
| 32 | observability | L1 | Facts → Observability, "nothing is console-only" |
| 33 | observability | L1 | Facts → Observability, "no webhook, no streaming events API" |
| 34 | comparison | L1 thin | Objections, first bullet; the table is in `company-and-comparison.md` |
| 35 | build-vs-buy | L1 | Objections, second bullet — the cost list is the concrete answer |
| 36 | traction | L1 | Numbers, Recruit41 provenance |
| 37 | traction | L1 | Numbers, Recruit41 provenance |
| 38 | business-model | L1 | Facts → Money |
| 39 | moat | L1 | Objections, third bullet |
| 40 | traction | L1 | Not known — paying customers are not named |
| 41 | partnerships | L1 | Facts → Deployment, forward deployed — no partner is named |
| 42 | positioning | L1 | Identity + Objections, "what a chatbot doesn't" |
| 43 | trial | L1 | Demos |
| 44 | pricing | L1 | Facts → Money |
| 45 | audience | L1 | Objections, "Do I need engineers?" |
| 46 | maturity | L1 thin | Objections, production readiness; the ordered answer is in `pricing-and-plans.md` |
| 47 | differentiation | L1 | Facts → Speech ("ours, on our own GPUs") + Objections, moat |
| 48 | claims | L1 | Numbers, the 1,143 qualifier |
| 49 | value | L1 thin | Facts → Money (what the minute covers) + Objections; argument in `pricing-and-plans.md` |
| 50 | claims | L1 | The Page, known page defect |

---

## The result

Derived from the table above; recount it after any edit to either file rather
than trusting this paragraph.

- **L1 alone answers 88%** of the set, with `19`, `34`, `46` and `49` thin.
- **L1 plus exactly one `l2/` read answers 100%.** No question needs a second
  deep dive, and none is left uncovered.

Targets were 80% and 90%. Each is met with margin, and the margin is deliberate
rather than padding: a live visitor's question is rarely as clean as a written
one, and the agent will spend some of that headroom on phrasing it did not
anticipate.

## Where the margin actually is

The *thin* rows are the honest edge, and they share a shape: L1 states the
position, and the asker wants the argument behind it. Each belongs to a
persona who will keep talking — a CTO comparing against a realtime voice API, an
investor probing the moat, a buyer asking which plan carries their launch.
The agent should answer from L1 and then offer to go further, rather than
reading the L2 file pre-emptively and burying the short answer.

The `l2/` rows are the opposite shape: narrow, factual, and genuinely absent
from L1 because putting them there would cost more than the read does. Some of
them — `3`, `29`, and the version matrix in `16` — end at a documentation page
rather than at our own file, because the frame set, the language roster and
pipecat's supported versions all move on their own schedule. **An agent that
recites those from memory will be wrong before the quarter ends** — route, don't
recall.

## What the audit is not

It measures whether the material *contains* an answer, not whether the agent
*delivers* one. Retrieval quality, the choice of when to read L2 at all, and
whether the spoken answer stays inside its sentence budget are properties of the
brain, and they get tested against this same question set once it exists.

Question `50` stays in the set after the page copy is fixed. It is the cheapest
regression test there is: if the agent ever answers it by picking one of those
words confidently, the knowledge base has started papering over the page instead
of describing it.
