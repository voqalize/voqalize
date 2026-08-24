# `/docs/design/` — the outlines

Ten explanation pages, one conviction each. These are **reference outlines, not
drafts**: facts, proof points and the top-down belief, gathered so the narrative
can be shaped once. Prose comes later.

## The rule for every page

**Lead with the surprise.** If the headline is not surprising, the page has no
reason to exist. Each outline states its surprise in one sentence at the top; if
that sentence reads as obvious, the page is wrong, not the sentence.

## The ten

| # | Page | The surprise |
|---|---|---|
| 1 | [Voice points, the screen holds](01-voice-points-screen-holds.md) | Voice is the fastest way for a human to express dense intent and the worst way to receive it. |
| 2 | [The turn budget](02-the-turn-budget.md) | You own one interval of the turn — callback to first chunk — and it is the only latency in the product your code controls. |
| 3 | [Interruption and heard truth](03-interruption-and-heard-truth.md) | The caller did not hear what your agent said. Recording what it *generated* corrupts the conversation silently. |
| 4 | [Parallel workstreams](04-parallel-workstreams.md) | Voice is fast only because the caller can say five things without waiting. An agent that handles one at a time gives that speed straight back. |
| 5 | [Prompt design for voice](05-prompt-design.md) | 80% of what the agent needs must already be in the prompt, because every lookup is silence the caller sits through. |
| 6 | [Tool design for voice](06-tool-design.md) | A tool that waits is a bug. Tools return immediately, are never cancelled, and are undone by a compensating call. |
| 7 | [Who owns which state](07-who-owns-which-state.md) | We own the conversation state and you own everything else, so every turn is a merge — and the merge is your code. |
| 8 | [Getting information to the model](08-getting-information-to-the-model.md) | There are four places a fact can live, and choosing wrong costs either latency or accuracy on every turn. |
| 9 | [Misunderstanding and reversal](09-misunderstanding-and-reversal.md) | The caller will be misheard and will correct themselves mid-sentence. Irreversible actions are committed by a click, never by the agent. |
| 10 | [The framework boundary](10-the-framework-boundary.md) | The best thing we can do for your tools is nothing. Whatever agentic framework you brought already runs them. |

Pages 1–9 are written to the developer holding the brain. **Page 10 is written to
us**, about the line we hold — but it is on the same list because every rule on it
is visible from the other side as a shape they do not have to learn.

## Conventions in these outlines

- **Fact** — a mechanism in our code, with the symbol or path.
- **Proof** — something already shipped that demonstrates it, with a file address.
- **Belief** — the top-down claim, ours, arguable.
- **Gap** — what we would have to build or measure before a sentence is honest.

These outlines are internal reasoning and may argue by contrast. The pages they
become are governed by [`design/voice.md`](../voice.md) and may not.

## PRACTICES.md

The flat list of rules the nine pages share, each marked **agreed** / **contested**
/ **violated**, plus what we have not settled and where the evidence has holes.
Argue with it there rather than inside nine separate pages. It is working notes,
not a document, and `design/voice.md` does not govern it.
