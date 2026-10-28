---
name: stage-author
description: Add Stage to a developer's own web app (React or plain HTML) so a Voqalize voice agent can show and do things on its screen while it talks. Use when annotating an app with data-stage attributes, writing its Stage Spec, wiring @voqalize/stage into its existing pipecat client, or reporting its state to the agent as named events.
---

# Putting Stage into an app

The app keeps its own pipecat client and its own brain. Stage adds three things: a spec of
what the agent may do (`scene.json`), the page's performers for those moves, and named
events for the state the agent needs. The worked example is
`sdk/python/examples/stage_shop/`; the contract is `design/stage.md`.

## 1. Write the spec

Start from a kit when the app is a store (`"kits": [{"id": "commerce", "major": 1}]`),
then add the app's own moves with the `stage-move` skill. Declare state as slices and
events (a slice's fields are an allowlist; mark anything personal `private`):

```json
"slices": [{ "id": "cart", "doc": "what is in their cart",
             "fields": [{ "name": "count", "type": "integer" },
                        { "name": "items", "type": "array", "fields": [{ "name": "name" }] },
                        { "name": "email", "private": true }] }],
"events": [{ "id": "cart.changed", "slice": "cart", "op": "set",
             "note": "{by} changed the cart: {count} items" }]
```

The note is the one line the model hears: a verb phrase, never the values. The model
reads values with the read tool.

Generate and check:

```sh
uv run voqalize stage gen stage/scene.json --py brain/stage_gen.py --ts src/stage/scene.gen.ts
uv run voqalize stage check stage/scene.json
```

For a page with no build step, add `--json public/scene.page.json` (the kits merged in).

## 2. Mark up what the agent points at

```html
<section data-stage-thing="sheets" data-stage-label="Our sheets">…</section>
<button data-stage-part="Size:King">King</button>
<body data-stage-place="catalog">
```

`{show: Our sheets}` and `{filter: Size | King}` then work with the stock performers and no
code. The attributes are locators only: they never add moves or words.

## 3. Attach to the app's client

Plain page (`@voqalize/stage/script`):

```ts
await attach(client, { spec: "/scene.page.json", performers: { "commerce.cart_add": addToCart } });
```

React (`@voqalize/stage/react`), with the app's own React handed in:

```tsx
const { useStage, useMove, useSlice, useNavigated } = stageHooks(React);
const stage = useStage(usePipecatClient(), scene);
useMove(stage, "commerce.cart_add", async ({ path, qty }, c) => { /* ring, then act */ });
useSlice(stage, cart, (prev, next) => (prev && prev.count !== next.count ? ["cart.changed", next] : null));
useNavigated(stage, pathname);
```

Never wrap, construct or re-export pipecat's client; Stage only attaches to it. Never push
the whole screen to the brain: a change the agent needs to know about is a named event, and
one that matches no event is not sent.

## 4. The brain

```python
self.stage = Stage(dispatch=lambda a: self.session.dispatch(a), moves=MOVES, mirror=Mirror(SPEC))

def respond(self, session):
    return self.stage.cued(super().respond(session))      # cues out of the words, to the page

async def on_rtvi(self, session, msg):
    event = StagePageEvents.parse(msg)                     # results, progress, hello, state events
    ...                                                    # self.stage.handle(event); note the line

@needs_result_now
async def read_screen(self, request: ReadRequest) -> str:  # ReadRequest from stage_gen
    return self.stage.mirror.read(request.slice)
```

A session starts from the backend, not from the screen: load what the app owns (an
account, a cart) from its API when the call starts, and let the page report only what the
visitor does.

## 5. Prove it

A page test with `@voqalize/stage/conformance` (no change before the ring, one result per
move, every declared move performed) and the brain's own tests over the real wire. Then a
real call.
