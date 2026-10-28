---
title: Stage
description: Stage lets the agent show and do things on a page while it talks. Moves are declared once in a Stage Spec; cues in the agent's reply fire as the voice reaches their words, and every move is ringed by the spotlight and answered with one result.
---

:::caution[Not released yet]
Stage is being proved on our own sites first. `voqalize.sdk.stage` and
`@voqalize/stage` are not in a published release, so nothing on this page can be
installed yet. It describes what the next release adds.
:::

[Actions](/build/brain/actions/) move a screen when a tool runs. Stage moves it
**as the agent speaks**: the agent says "These are the king-size sheets", and
the filter for king size is ringed and pressed as those words are heard. A whole
tour of a page is one reply, with no tool round trip between its parts.

## The words

- A **move** is something the agent can do on a page: show a section, filter a
  listing, add to a cart. It has a **class** that decides how it behaves:
  `look` (only what is in view changes), `navigate` (another page opens),
  `reversible` (the page's state changes and can be undone) and `confirmed`
  (something the person owns changes, after they said yes). Paying, consent and
  submitting personal data are never moves: the person presses that button.
- A **cue** is a move written inside the agent's reply, `{filter: Size | King}`,
  at the start of the sentence it belongs to. The page fires it at its **mark**,
  the point where the voice reaches those words. Only `look`, `navigate` and
  `reversible` moves may be cues; a `confirmed` move is always a tool.
- **The spotlight** rings what a move touches before anything on the page
  changes, so the person sees what the agent is doing.
- Every move gets exactly one **result**: applied, partial, refused (with the
  options the page offers), failed, undone or unknown.
- A **slice** is a named piece of the page's state (`cart`, `listing`), and a
  **state event** is a named act that changes one. The brain keeps the slices
  and the model hears one line naming each act, never the values; it reads the
  values through a tool when it needs them.

## The Stage Spec

An app's moves, slices and state events are declared once, in `scene.json`, and
generated for both halves, so the brain and the page never disagree about a move:

```json
{
  "stage": 1,
  "id": "shop",
  "kits": [{ "id": "commerce", "major": 1, "moves": ["commerce.filter", "commerce.cart_add"] }],
  "moves": [
    {
      "id": "core.show",
      "verb": "show",
      "class": "look",
      "args": [{ "name": "target" }],
      "say": "{show: Heading} scrolls to that part of the page and rings it."
    }
  ]
}
```

```sh
uv run voqalize stage gen scene.json --py brain/stage_gen.py --ts src/stage/scene.gen.ts
uv run voqalize stage check scene.json
```

The Python half gives the brain its moves and a typed model for each move's
arguments; the TypeScript half hands the spec to `defineScene`, which infers
every move's argument types. `stage check` runs every cue through the same
guard that holds back a function call the model wrote as text, so a cue that
would be held back fails the build instead of a call. A **kit** is a set of moves,
slices and state events many apps share; `commerce` is the first.

## The brain

```python
from voqalize.sdk.stage import Mirror, Stage, StagePageEvents
from .stage_gen import MOVES, ReadRequest

self.stage = Stage(dispatch=lambda a: self.session.dispatch(a), moves=MOVES, mirror=Mirror(SPEC))

def respond(self, session):
    return self.stage.cued(super().respond(session))   # cues out of the words, to the page
```

`stage.cued` takes each cue out of the reply's text and sends it ahead of the
voice; `stage.handle` takes the page's results and state events. A sentence that
promises a move ("I'm opening the calendar") and a turn that never sends it is
reported, so the brain can make the move after all.

## The page

`@voqalize/stage` attaches to the pipecat client the app already has. It never
creates, connects or wraps one.

- **Markup**: `data-stage-thing="sheets"` names something the agent can point at,
  `data-stage-part="Size:King"` an option it can press. With these, `{show: …}` and
  `{filter: …}` need no code.
- **A page with no build step**: `attach(client, { spec: "/scene.page.json" })`
  from `@voqalize/stage/script`, with the app's own performers for anything the
  markup does not cover.
- **React**: `stageHooks(React)` from `@voqalize/stage/react` gives `useStage`,
  `useMove`, `useSlice` and `useNavigated`. The app hands its own React in.

A **performer** is the page's code for one move. It rings its target, acts, and
returns one short line the agent can repeat:

```ts
scene.registerAll(moves, {
  "commerce.cart_add": async ({ path }, c) => {
    const button = addButtonFor(path) ?? c.refuse("path", `no ${path} on this page`);
    await c.ring(button, "Add to cart");
    button.click();
    return `added ${path}`;
  },
});
```

`@voqalize/stage/conformance` checks a page's performers in a test: every
declared move is performed, each answers once, and nothing on the page changes
before the spotlight rings it.
