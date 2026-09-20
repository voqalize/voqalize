# The question set

What a visitor to the homepage actually asks. Written by an agent given **only**
the rendered text of `voqalize.com/` — no repo, no `CLAUDE.md`, no docs — so the
list reflects what the page raises and what it leaves open, rather than what we
already know the answer to.

Persona weighting, as commissioned: developers / engineers / CTOs carry 70%, the
rest split across investors, casual observers and competitors.

This file is the **coverage target**, not documentation. `L1.md` is sized so that
roughly four in five of these are answerable without a second read, and the
remainder by exactly one `l2/` document. `coverage.md` is the audit.

The numbering is an index into the audit table and is referenced by id from
`coverage.md`. It is not a claim about how many questions a visitor has.

---

## Developers / engineers / CTOs

### Integration and the brain contract

1. What exactly do I have to implement to get a brain running — just one WebSocket endpoint? `[integration]`
2. Is the wire protobuf, JSON, or something else, and where's the schema? `[wire-format]`
3. What's the full set of frames? The page names UserMessage, SpeechChunk, SpeechStart/SpeechEnd, UI events and UI actions — is that all of them? `[wire-format]`
4. How do I define UI actions for my own app? Are they typed by me, or a fixed vocabulary Voqalize knows? `[ui-actions]`
5. How does the brain authenticate the incoming connection — what is "the token to verify"? `[auth]`
6. When do I need Cortex mode instead of inbound, and does anything behave differently on it? `[deployment-mode]`
7. Where does session init data go, and what can I pass at connect time? `[session-init]`
8. Can one conversation be served by multiple agents behind my brain, and does Voqalize care? `[architecture]`

### Runtime, latency and reliability

9. What happens if my brain is slow to respond mid-turn — does the user just hear silence? `[failure-modes]`
10. What if my brain crashes or the WebSocket drops mid-call? Do you reconnect, and is state lost? `[failure-modes]`
11. What's the actual end-to-end latency, in ms, excluding my brain? `[latency]`
12. How long can a session stay open, and is there an idle timeout that kills it? `[limits]`
13. How does interruption work from my side — do I get told my speech was cut off, and where? `[interruption]`
14. That "compare against plan" runs in the background — how do I push a result into the call later, unprompted? `[async]`
15. How do you handle the user editing the document by hand? Is that just a UI event I have to model myself? `[state-sync]`

### Client, SDK and platform

16. "pipecat compatible" — which pipecat client versions and transports actually work? `[sdk]`
17. Is there a React Native or native iOS/Android path, or is mobile just webview? `[mobile]`
18. My backend is Go/Node, not Python. Is the SDK Python-only, or is the wire enough? `[languages]`
19. What does the MCP server actually let my coding agent do — is it setup only, or runtime too? `[mcp]`
20. Can I run this fully locally for development without touching your cloud? `[local-dev]`
21. Is state my problem entirely? If a process restarts, is the in-memory conversation object just gone? `[state]`

### Security, compliance and deployment

22. In VPC mode, what still phones home — licensing, telemetry, model weights, anything? `[self-host]`
23. Does audio ever hit your servers on the cloud plan, and how long is it retained? `[data-retention]`
24. You say retention isn't guaranteed in preview — what does that mean for anything I record? `[data-retention]`
25. Are ISO 27001 and SOC 2 certificates you actually hold today, and is SOC 2 Type I or Type II? `[compliance]`
26. What GPUs does the VPC deployment need, and who pays for them? `[self-host]`

### Avatars and speech

27. The avatar library is MIT and unmetered — what stops me using it without the rest of Voqalize? `[avatar]`
28. Can I swap in my own TTS or STT provider without an enterprise contract? `[speech]`
29. Which 22 Indian languages, and is STT quality comparable across all of them or just Hindi? `[languages]`
30. Can the language switch mid-call, and does the voice follow it? `[speech]`

### Observability and testing

31. How do I test a brain in CI — what does "no microphone, no network, no live model" actually give me? `[testing]`
32. Can I export the per-turn timing data, or is it only visible in your console? `[observability]`
33. Do I get transcripts and events over an API/webhook in realtime, or only after the session ends? `[observability]`

### Build-vs-buy and comparison

34. Why not just use OpenAI's or Gemini's realtime voice API directly? `[comparison]`
35. Concretely, how much work am I saving versus assembling pipecat + WebRTC + a speech vendor myself? `[build-vs-buy]`

## Investors

36. Is Recruit41 a customer, an investor, or the same team? What's the relationship? `[traction]`
37. Are the 50,000 interviews and 1,143 concurrent conversations from Recruit41 rather than from Voqalize customers? `[traction]`
38. How do you charge — per minute, per session, per seat? `[business-model]`
39. What's the moat if the avatar is MIT and the client is pipecat-compatible? `[moat]`
40. Who is the paying customer today, outside developer preview? `[traction]`
41. Is Think41 a channel partner, a services arm, or your parent company? `[partnerships]`

## Casual observers / product

42. In one sentence, what does this do that a chatbot doesn't? `[positioning]`
43. Can I try it right now without signing up? `[trial]`
44. What does it cost? `[pricing]`
45. Do I need engineers to use this, or is there a no-code path? `[audience]`
46. "Developer preview" — is it safe to put in front of real customers yet? `[maturity]`

## Competitors

47. Which parts of the speech stack are genuinely yours, and which are wrapped vendors? `[differentiation]`
48. Was 1,143 concurrent conversations load-tested, or is it one lucky day on one event? `[claims]`
49. If the brain, models, prompts and data are all mine, what am I paying you for besides transport? `[value]`
50. The footer says "developer preview" but the CTA says "builder preview" — which is it, and what's actually GA? `[claims]`

---

## What the page does not answer

The gaps the author hit while writing the list. Each one is why an `l2/`
document exists, or why a fact was pulled up into `L1.md`.

- **Pricing.** A Pricing nav item, but no number, no unit, no free tier and no statement of what is enterprise-gated beyond custom voice, BYO TTS and custom avatar.
- **The wire, concretely.** Frame names appear; the encoding, the version discipline, the full frame set and how a developer declares their own action types do not.
- **Failure semantics.** Nothing on brain timeouts, slow first byte, reconnection or mid-call crashes — despite the page's own waterfall showing the brain's span as by far the widest.
- **Latency numbers.** Per-layer measurement is promised; no figure for any layer is published, so there is nothing to compare against a realtime voice API.
- **Provenance of the headline metrics.** The production numbers are attributed to Recruit41, and the page never says what Recruit41 is to Voqalize.
- **Preview status.** "developer preview" and "builder preview" both appear, plus "the SDK and wire protocol are still moving", with no statement of what that means for production use.
- **Auth and identity.** "the token to verify" is named in the nav only; nothing on key kinds, rotation, origin restrictions or how a brain proves the caller is Voqalize.
- **Data handling.** No retention period, no statement of whether audio transits or is stored, no detail on what the consent gate actually is.
- **Limits.** No session length cap, no concurrency limit, no rate limits, no idle-timeout behaviour.
- **Client surface.** "pipecat compatible" is asserted without naming client libraries, versions, or the native-versus-webview story.
- **VPC reality.** "no external dependency" is claimed; GPU requirements, sizing, update path and licensing are absent.
- **Think41.** Named as delivery partner with no description of the commercial relationship.
- **Testing.** "no microphone, no network, no live model" is compelling and unexplained.

## One thing the list found that is a page defect, not a content gap

Question 50 was real. `Close.astro` labelled the closing section **builder
preview** while `Footer.astro` said **developer preview**; the docs, the pricing
page and the status page all said *developer* preview. One of those words was
wrong on the page itself, and no knowledge base should paper over it.

**Fixed:** `Close.astro` says *developer preview*, and the page now uses one
term throughout. Left here because the finding is what this file is for — it is
the audit that built the knowledge base, not a list of open defects.
