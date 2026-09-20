# L2 — pricing and the preview

Read when: pricing shape, preview limits, what "developer preview" means for a
production launch, or support.

## Today: free

Developer preview is free. Not a trial with a clock on it, not a credit balance.
There is a pricing page, and its ledger reads `$0`.

## The planned unit

**Session time on the voice plane** — per session minute. Not seats, not agents,
not requests, not tokens.

A planned minute includes: recognition, synthesis, voice activity detection and
endpointing, WebRTC, interruption handling, the avatar, monitoring, observability
and operating the whole thing. The avatar is inside it rather than beside it,
because the avatar renders on the device.

**Rates land before charges do; nothing meters without notice.** No date is
published for either.

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
- Two speech models, tuned and served, English plus 22 Indic languages.
- WebRTC in production: direct media, node affinity, a real client path through
  stock pipecat.
- The avatar, the recording pipeline, the per-turn measurement, the call record.
- Someone operating it at peak — the observed peak on the voice tier is 1,143
  simultaneous conversations.

It is not transport. Transport is the cheapest thing on that list.

## Enterprise-gated

Named on the homepage: **custom brand voice, bring-your-own TTS, custom
avatars**, VPC deployment, and forward-deployed engineering (delivered with
Think41). Everything else is on the self-serve path.

## Preview limits, concretely

- Tier limits exist in the model but are **not enforced** during preview, and no
  public concurrency ceiling is committed.
- Session cap: one hour.
- Management API and MCP are rate limited per tenant.
- **Retention is not guaranteed or configurable.**
- No SLA.
- "the SDK and wire protocol are still moving" — the wire is versioned, but a
  breaking change is possible without a deprecation window yet.

## Is it safe in front of real customers?

The honest answer, in the right order:

The voice tier underneath has been in production for two years, carrying 50,000
interviews and a measured peak of 1,143 simultaneous conversations. What is in
preview is the **developer surface** — the SDK, the wire, the console — not the
runtime.

What preview means in practice: no SLA, no retention guarantee, and a wire that
can still change under you. A pilot with real users is reasonable and people are
running them; a launch with a contractual uptime commitment is a conversation to
have at `support@voqalize.com` first, not something to infer from this page.

**One term, everywhere: developer preview.** The docs, the pricing page, the
status page, the footer and the closing section all use it. If a visitor quotes
something else back at you, they are reading an old page — say the right term
rather than reconciling the two.

## Support

`support@voqalize.com` for everything: pilots, enterprise, compliance documents,
a concurrency ceiling, a retention requirement, or a rate before it is published.
