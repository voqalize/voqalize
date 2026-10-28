# @voqalize/stage

The page half of Stage: the agent's moves, made on the page as its voice reaches
their words, each ringed by the spotlight before anything changes and answered
with one result. The brain half is `voqalize.sdk.stage` in `voqalize-agent-sdk`.

**Not published.** The package is private in this repository until Stage has
been proved on our own sites; then it is released together with the SDK.

It attaches to the pipecat client the app already has. It never creates,
connects, wraps or re-exports one, and it names no pipecat type in its API, so
any client in the peer range fits.

## Entry points

| Import | What it gives |
|---|---|
| `@voqalize/stage` | `defineScene`, `Moves` and `MoveContext`, `Spotlight`, `Timeline`, `attachStage` and `stagePage`, the `data-stage-*` helpers and stock performers, `Plugins`, the wire types |
| `@voqalize/stage/script` | `attach(client, { spec })`: Stage from a spec and the page's markup, for a page with no build step |
| `@voqalize/stage/react` | `stageHooks(React)`: `useStage`, `useMove`, `useSlice`, `useNavigated`, with the app's own React |
| `@voqalize/stage/extension` | the Chrome extension host the site extensions share: one call held across tabs and page loads |
| `@voqalize/stage/conformance` | `checkRegistry` and `conformance`: a page's performers held to Stage's rules in a test |

## A move, from spec to page

The spec (`scene.json`, checked by `stage.schema.json`) declares the move once;
`voqalize stage gen scene.json --ts src/stage/scene.gen.ts` writes it for the page:

```ts
import { Moves, Spotlight, stagePage } from "@voqalize/stage";
import { scene } from "./stage/scene.gen";

const moves = new Moves(new Spotlight({ color: "#2563eb" }));
scene.registerAll(moves, {
  "commerce.filter": async ({ facet, value }, c) => {
    const pill = findPill(facet, value) ?? c.refuse("value", `no ${facet} ${value}`, offered(facet));
    await c.scrollTo(pill);
    await c.ring(pill, `${facet}: ${value}`);
    await c.beat();
    pill.click();
    return `${facet} ${value} applied`;
  },
  // a performer for every move the spec declares, or this does not compile
});
const stage = stagePage(client, moves);
```

Each performer rings before it acts, refuses with the options the page offers
instead of guessing, and returns one short line the agent can repeat.

## Tests

```sh
pnpm typecheck && pnpm test
```

The worked example, a page and its brain, is `sdk/python/examples/stage_shop`.
The build contract is `design/stage.md`.
