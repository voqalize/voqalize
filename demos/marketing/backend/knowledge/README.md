# The homepage agent's knowledge base

What Tanya answers from. She sits in the corner of the Voqalize homepage,
answers a visitor's question, scrolls them to the section that bears on it, and
puts a line of light on the element being discussed.

This directory is **content, not code**: `brain.py` reads it, nothing imports
it. The page she drives is built from the private repo
(`platform/frontend/apps/marketing`) — see `demos/README.md`, "When the page
lives somewhere else".

## The files

- **[`L1.md`](L1.md)** — the core document, in the context of every session.
  Budgeted at 5,000 tokens and currently just under it. It carries the facts
  behind each section, the numbers with their provenance, the objections that
  recur, the demo roster, and the routing table into `l2/`.
- **[`l2/`](l2/)** — deep dives, each read **only when a question goes past
  L1**, one per topic: `wire-and-brain`, `connect-and-clients`,
  `latency-and-failure`, `deployment-and-vpc`, `speech-and-languages`, `avatar`,
  `observability-and-testing`, `security-and-data`, `pricing-and-plans`,
  `company-and-comparison`. Each is small enough to pull into context without
  crowding the call.
- **[`questions.md`](questions.md)** — what a visitor actually asks, written by
  an agent given only the rendered homepage and nothing else. This is the
  coverage target, not documentation.
- **[`coverage.md`](coverage.md)** — the audit: every question against the tier
  that answers it.

The **page map is not here.** Anchors and highlight targets are generated into
the prompt from the page contract in `brain.py`, so the thing the brain points
with and the thing it is told about cannot drift apart. That map used to be a
table in `L1.md`, maintained by hand, and it was the single most stale-prone
thing in this directory.

## Why tiers

A single document large enough to answer everything would be read in full on
every session, for a visitor who asked one question about pricing. A pile of
small documents with no core would need a retrieval step before the agent could
say anything at all, which is latency on the turn a visitor is least patient
with.

So: L1 is the page plus the answers to the common questions, sized to be
resident. L2 is what a *particular* visitor turns out to need. The routing table
at the foot of L1 is what makes the second read a decision rather than a search —
the agent already knows which file holds the answer before it opens anything.

**One read, never more.** If a question needs a second `l2/` file, that is a
signal to move the shared fact up into L1, not to chain reads. `coverage.md` is
where that shows up.

## The staleness contract

L1 restates the homepage. That is the point, and it is also the liability.

A page goes stale where it **names a symbol** — a field name, a fixed string, a
price. It does not go stale where it names a URL or describes a boundary. So the
rule for this directory:

> **Change a number the homepage displays, and `L1.md` changes in the same
> commit.**

Rewriting a section's prose does not require an L1 edit — L1 deliberately does
not quote the page's sentences, because then every copy tweak would break it.
What it holds is the *facts behind* the copy.

The facts in `l2/` are drawn from `docs.voqalize.com` and from our own internal
records, not from the page, so they follow the product rather than the design.
Where a fact moves faster than this directory can — the frame set, the language
roster, pipecat's supported versions — the file **routes to the documentation
page instead of restating it**. An agent that recites a version matrix from
memory is wrong within a quarter.

When L1 and the page disagree, the page is right and L1 is the bug.

## Keeping the audit honest

`questions.md` was written by an agent with **no access to this repo, this
directory, or our docs** — only the rendered page. That isolation is what makes
it a test rather than a mirror of what we already wrote down. If the question set
is ever regenerated, regenerate it the same way, and do it *before* editing L1,
not after.
