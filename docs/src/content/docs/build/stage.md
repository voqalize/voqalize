---
title: Stage
description: Stage lets the agent show and do things on a page while it talks. Declare moves once in a Stage Spec; cues in the agent's reply fire as the voice reaches their words, and every move is ringed by the spotlight and answered with one result.
---

[Actions](/build/brain/actions/) move a screen when a tool runs. Stage moves it
**as the agent speaks**: the agent says "These are the king-size sheets", and the
king-size filter is ringed and pressed as those words are heard. A whole tour of
a page is one reply, with no tool round trip between its parts.

Stage ships in two packages, one per half. Pin both:

```bash
pip install voqalize-agent-sdk==0.12.0      # the brain: voqalize.sdk.stage
pnpm add @voqalize/stage@0.1.0              # the page
```

Working with a coding agent? The public repo ships Stage skills in
`.claude/skills/` (`stage-author`, `stage-move`, `stage-explorer`, `stage-debug`,
`stage-review`) that walk it through each step below
([Work with a coding agent](/build/coding-agent/)).

## The words

- A **move** is something the agent can do on a page: show a section, filter a
  listing, add to a cart. Its **class** decides how it behaves:

  | Class | What changes | Can be a cue |
  |---|---|---|
  | `look` | Only what is in view. | yes |
  | `navigate` | Another page opens. | yes |
  | `reversible` | The page's state, and it can be undone. | yes |
  | `confirmed` | Something the user owns, after they said yes. | no, always a tool |

  Paying, consent and submitting personal data are never moves: the user presses
  that button.
- A **cue** is a move written inside the agent's reply, such as
  `{filter: Size | King}`, at the start of the sentence it belongs to. The page
  fires it at its **mark**, the point where the voice reaches those words.
- **The spotlight** rings what a move touches before anything changes, so the
  user sees what the agent is doing.
- Every move gets exactly one **result**: `applied`, `partial`, `refused` (with
  the options the page offers), `failed`, `undone` or `unknown`.
- A **slice** is a named piece of the page's state (`cart`, `listing`), and a
  **state event** is a named act that changes one. The brain keeps the slices;
  the model hears one line naming each act, never the values, and reads the
  values through a tool when it needs them.
- A **kit** is a set of moves, slices and state events many apps share;
  `commerce` is the first.

## Declare moves once, in a Stage Spec

An app's moves, slices and state events are declared in `scene.json` and
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

The Python half gives the brain `MOVES`, `SPEC` and a typed model for each
move's arguments; the TypeScript half hands the spec to `defineScene`, which
infers every move's argument types. `stage check` runs every cue through the
guard that holds back a function call the model wrote as text, so a cue that
would be held back fails the build instead of a call. Run it in CI, with
`--strict` to fail on warnings too.

## Wire Stage into the brain

```python
from google import genai

from voqalize.sdk import RTVIMessage, Session
from voqalize.sdk.gemini import GeminiBrain
from voqalize.sdk.stage import Mirror, Stage, StagePageEvents

from .stage_gen import MOVES, SPEC


class Shop(GeminiBrain):
    def __init__(self) -> None:
        super().__init__(client=genai.Client(), system_instruction="You run the shop.")
        self.stage = Stage(
            dispatch=lambda action: self.session.dispatch(action),
            moves=MOVES,
            mirror=Mirror(SPEC),
        )

    async def respond(self, session: Session):
        async for event in self.stage.cued(super().respond(session)):
            yield event       # the cues are taken out of the words and sent to the page
        self.stage.end_turn()

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        event = StagePageEvents.parse(msg)
        if event is not None:
            self.stage.handle(event)  # the page's results and state events
```

- **`stage.cued`** takes each cue out of the reply's text and sends it ahead of
  the voice, so the user never hears the braces.
- **`stage.handle`** folds in the page's hello, results, progress and state
  events.
- **`stage.end_turn`** reports every move the turn promised in its words ("I'm
  opening the calendar") and never sent, so the brain can make the move after
  all.

### When your app runs its own actions

If your app already has an action runner with its own gates, queue and
timeouts, let it decide when a move goes and let Stage only keep count:

```python
ref = self.stage.send("commerce.cart_add", {"path": sku_path}, queue=False)
# ... later, if your runner gives up on it:
result = self.stage.abandon(ref, "the checkout step timed out")
```

With `queue=False` the move is sent at once, never queued or refused, so `send`
always returns its `call_ref`. Stage still times it, counts it toward the turn's
promises and matches the page's result to it. `abandon` tells Stage your runner
stopped waiting: that move comes back as an `unknown` result now, and if the page
answers it later, `stage.handle` returns that answer once with `late` set. A
move id the brain does not know raises `KeyError`.

## Attach Stage to the page

`@voqalize/stage` attaches to the client your app already has. It never
creates, connects or wraps one.

- **Markup**: `data-stage-thing="sheets"` names something the agent can point at,
  `data-stage-part="Size:King"` an option it can press, and `data-stage-card` one
  product card of a listing, counted from 1. With these, `{show: …}` and
  `{filter: …}` need no code, and from `@voqalize/stage` 0.2.0 nor do the
  `commerce` kit's `{variant: …}` and `{compare: …}`.
- **A page with no build step**: `attach(client, { spec: "/scene.page.json" })`
  from `@voqalize/stage/script` (generate the file with `stage gen --json`), with
  your own performers for anything the markup does not cover.
- **React**: `stageHooks(React)` from `@voqalize/stage/react` gives `useStage`,
  `useMove`, `useSlice` and `useNavigated`. Your app hands its own React in.

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

`@voqalize/stage/conformance` checks your performers in a test: every declared
move is performed, each answers once, and nothing on the page changes before the
spotlight rings it.

### What the page tells the agent

On connect and on every page load the page says hello: the runtime, its contract
version, and the page's address as origin and path only. The query string, the
fragment and the title are never sent, because that is where pages keep sign-in
tokens, order numbers and names; a path longer than 160 characters is cut. A page
that wants the agent told more sends its own `stage_hello` with `send`.

A state event done by the user (`by: "visitor"`) reaches the agent too, and you
choose per event how much it makes of it:

| Mode | What the agent does |
|---|---|
| `silent` | Keeps it; reads it on demand. |
| `note` | Gets one line for its next turn. The default. |
| `speak` | May also say something short once the user pauses, as the event's `ask` says, now and then and never over the user. |

The `watch` kit reports the part of the page the user stays on and the forms they
fill in, by field name only. Nothing is reported unless your spec takes it.

## Read next

- [Actions](/build/brain/actions/): moving the screen from a tool.
- [Connect your app](/build/connect/): the client Stage attaches to.
- [Work with a coding agent](/build/coding-agent/): the Stage skills.
