# L2 — the company, the numbers and the comparison

Read when: Recruit41, delivery partners, the moat, build-versus-buy, realtime voice APIs,
or what is genuinely ours.

## Recruit41

Recruit41 is **the product the voice tier has been running in production for** —
an interviewing product built on the same voice runtime Voqalize now exposes. It
is the origin of the platform, not an external customer who bought it.

So, plainly: **the headline numbers are Recruit41's, not a Voqalize customer's**,
and the homepage attributes them there rather than implying a customer roster.
Say it that way if asked — it is a stronger answer than a vague one, because it
explains why a preview product has production numbers at all.

- **2 years in production** — the voice tier, not the SDK.
- **50,000 interviews**, with per-session context and structured output.
- **1,143 simultaneous conversations** — an observed peak during one nationwide
  campus event. Not a load test, not a committed ceiling.

On the competitor's version of that question — *"was 1,143 load-tested or one
lucky day?"* — it was one real day, and the page does not claim otherwise. It is
what the system actually carried, which is a different and in some ways better
fact than a synthetic benchmark. There is no published load-test number.

**Paying customers outside developer preview are not named publicly.** Don't
improvise one.

## Delivery partners

Forward-deployed engineering is Voqalize's own: the homepage says "our engineers
work alongside yours", in the enterprise section, and that is the whole public
statement. **No delivery or services partner is named publicly — do not name
one**, and do not confirm or deny one if asked; send the question to
`support@voqalize.com`.

## The moat, when the avatar is MIT and the client is pipecat

The giveaways are deliberate, and naming why is more convincing than defending
them:

- The **avatar** is MIT because a widely used avatar library is worth more than a
  gated one, and the avatar is not the hard part.
- The **client** is stock pipecat because a proprietary client SDK is a tax on
  adoption and buys nothing defensible.
- The **wire** is published because a brain the customer cannot port is a brain
  they will not write.

What is actually hard, and is ours: **speech models tuned and served on our
own GPUs**, turn-taking that survives barge-in (endpointing, interruption, the
heard-prefix bookkeeping that keeps the agent's memory honest), WebRTC operated
at real concurrency, and the whole thing deployable inside someone else's VPC
with no external dependency. Two years of production is the part that cannot be
cloned in a quarter.

## Versus a realtime voice API (OpenAI, Gemini)

Not a worse version of the same thing — a different trade.

| | Realtime voice API | Voqalize |
|---|---|---|
| Where the agent's logic lives | inside the vendor's service | the customer's backend, unchanged |
| Model choice | that vendor's | any, including several per call |
| Prompts, tools, data | shipped to the vendor | never leave |
| Speech | the vendor's bundle | ours, on our GPUs, Indic-first |
| Screen control | build it | typed actions, generated types, pipecat handler |
| VPC | no | yes, models included |
| Model bill | bundled | stays the customer's |

The short form: a realtime API asks you to move your agent into it. Voqalize asks
for one WebSocket route and leaves the agent where it is. For a team that already
has an agent — prompts tuned, tools wired, data adjacent — that difference is the
whole decision.

Where a realtime API wins: a greenfield voice-only assistant with no existing
agent, no screen and no data-residency constraint. Say so; pretending otherwise
loses the credible half of the argument.

## Versus assembling it yourself

Everything in the stack is available: pipecat is open source, WebRTC is a
standard, speech vendors sell APIs. Assembling them is a real option and some
teams should.

What assembling costs, specifically: operating WebRTC at concurrency with node
affinity and direct media; endpointing and barge-in tuned until interruption
feels right rather than merely working; keeping the agent's memory equal to what
the user actually heard after an interruption; speech vendors' latency,
pricing and language coverage; the avatar; recording with sample-aligned tracks;
per-turn measurement; and a test harness that can drive a voice agent in CI
without a microphone.

None of it is impossible. All of it is months, and none of it is the product the
team is actually trying to ship.

## What it does that a chatbot doesn't

For a non-technical asker, one sentence: **it talks while the app keeps working**
— it can see what is on the screen, move the user to the right place, fill things
in, and hand control back, instead of being a text box bolted to the corner.
