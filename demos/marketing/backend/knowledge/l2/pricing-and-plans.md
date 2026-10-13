# L2 — pricing and plans

Read when: what it costs, which plan fits, limits, what production readiness
means, or support.

Every figure here is copied from the pricing page (`voqalize.com/pricing`),
which is the record. If a visitor quotes a different figure, the page wins —
send them there rather than arguing the number.

## The unit

**Conversation minutes on the voice plane.** Not seats, not agents, not
requests, not tokens.

A minute includes: WebRTC transport, speech-to-text, text-to-speech, turn-taking
(VAD, endpointing and interruption handling), the avatar, observability (session
logs, transcripts and per-turn timings) and network egress. The avatar is inside
the minute rather than beside it, because it renders on the device.

Metered on top, each on its own unit: **recording** ($0.004 per recorded minute,
only when you record) and **storage** above the plan's quota ($0.06 per GB a
month). Prices exclude tax; rupee prices are set, not converted live.

## The plans

- **Free** — $0. A one-off signup credit of **350 minutes** (worth $10), no credit
  card. Every feature ungated. 2 concurrent sessions, 1 GB storage. A credit you
  spend once, not an allowance that refills.
- **Starter** — $99 a month (₹9,999). 3,000 minutes included, then $0.03 a
  minute. 5 concurrent sessions, 10 GB. One agent workflow; email support, next
  business day.
- **Growth** — $499 a month (₹49,999). 18,000 minutes included, then $0.027 a
  minute. 25 concurrent sessions, 25 GB. Everything in Starter plus unlimited
  workflows, a custom avatar and a custom voice, a forward-deployed engineer for
  tech support, priority support in a shared Slack channel, and a **99.5% uptime
  SLA**. The recommended plan.
- **Enterprise** — quoted. Everything in Growth plus speech models deployed in
  the customer's VPC, SSO, a DPA and a **99.9% uptime SLA**, a named account
  manager, and bring-your-own TTS. Volume pricing reaches the lowest rate the
  page publishes.

Annual billing is invoiced as ten months for twelve.

## What is not on a Voqalize invoice

The customer's model bill. The brain runs in their environment against their own
model credentials, so the LLM spend is between them and their provider and never
passes through us — not marked up, not resold, not visible to us.

Speech is the opposite case: it is **ours**, our models on our GPUs, so there is
no vendor passthrough hiding in the minute either.

## "Then what am I paying for besides transport?"

A fair question and worth answering straight rather than defensively. The minute
buys the parts of a voice product that are expensive to build and unglamorous to
own:

- Turn-taking that feels right — VAD, endpointing, barge-in, and the heard-prefix
  bookkeeping that keeps the agent's memory honest after an interruption.
- Two speech models, tuned and served, across English, Spanish, French, Italian,
  Japanese and 22 Indic languages.
- WebRTC in production: direct media, node affinity, a real client path through
  stock pipecat.
- The avatar, the recording pipeline, the per-turn measurement, the call record.
- Someone operating it at peak — the observed peak on the voice tier is 1,143
  simultaneous conversations.

It is not transport. Transport is the cheapest thing on that list.

## Limits, concretely

- Concurrent sessions, included minutes and storage are set by the plan (above).
- Session cap: one hour.
- Management API and MCP are rate limited per tenant.
- Stored session data, recordings included, is retained for **30 days**.
- The SDK is pre-1.0: pin the version you build against.

## Is it safe in front of real customers?

The honest answer, in the right order:

The voice tier underneath has been in production for two years, carrying 50,000
interviews and a measured peak of 1,143 simultaneous conversations. That peak is
an observed record, not a plan's ceiling.

An uptime SLA comes with Growth (99.5%) and Enterprise (99.9%). A launch that
needs more concurrency than a plan carries is a conversation at
`support@voqalize.com`.

## Support

Starter has email support, next business day. Growth adds priority support in a
shared Slack channel and a forward-deployed engineer. Enterprise adds a named
account manager. `support@voqalize.com` for pilots, enterprise, compliance
documents, or a concurrency need above a plan.
