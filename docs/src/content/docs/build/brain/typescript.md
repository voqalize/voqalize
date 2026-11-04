---
title: TypeScript types
description: Generate TypeScript for your Action and AppEvent classes with `voqalize types`, so the browser half is derived, not copied, and an unhandled action fails the build.
---

An [action](/build/brain/actions/) is already a complete description of a
payload: field names, types, defaults, docstrings. So is an [app
event](/build/brain/context/), in the other direction. Generate the TypeScript
from them rather than writing it again by hand.

```bash
uv run voqalize types backend/brain.py -o frontend/src/actions.gen.ts
```

Out comes one file covering both directions: an interface per action and per
event, an interface per nested model, a union over `command` and a union over
`event`. Check it in, and regenerate it the way you regenerate a lockfile.

## Why generate instead of copying

A hand-written copy fails silently. **Rename a field in Python** and the old
interface still compiles: the page reads `undefined` and draws a blank cell.
**Add an action** and the page's `switch` drops it on `default`: the screen does
not move while the agent says the right sentence. Generated types turn both into
build failures.

## What it emits

For a brain declaring `LogMeal` (with a nested `MealItem`) and `Highlight`:

```ts
// Generated from backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types backend/brain.py -o frontend/src/actions.gen.ts

export interface LogMeal {
  /** Which meal of the day this is. */
  meal_type: 'breakfast' | 'lunch' | 'snack' | 'dinner' | 'other';

  /** The foods with quantities and your calorie estimates. */
  items: MealItem[];

  /** Optional one-line note, e.g. 'ate out — office canteen'. */
  note: string;
}

export interface MealItem {
  name: string;
  quantity: string;
  calories: number;
}

// … and `Highlight`, generated the same way.

/** Everything the brain can put on screen, discriminated by `command`. */
export type UiAction =
  | { command: 'log_meal'; payload: LogMeal }
  | { command: 'highlight'; payload: Highlight };

export function asUiAction(command: string, payload: unknown): UiAction | null;
export function unhandledUiAction(action: never): never;
```

And for the same brain declaring the `QuantitySet` event:

```ts
export interface QuantitySet {
  item_id: string;

  quantity: number;
}

/** Everything the person can do on screen, discriminated by `event`. */
export type AppEvent =
  | { event: 'quantity_set'; payload: QuantitySet };

export const APP_EVENT_NAMES: readonly AppEventName[];
export function sendAppEvent(
  send: ((event: string, payload?: unknown) => void) | null | undefined,
  event: AppEvent,
): void;
```

`sendAppEvent` takes a pipecat client's `sendUIEvent` — or `null` before the call
connects, which drops the gesture, correctly: there is no brain that missed it.

```tsx
sendAppEvent(client?.sendUIEvent.bind(client), {
  event: 'quantity_set',
  payload: { item_id: 'li3', quantity: 5 },
});
```

Docstrings and `Field(description=...)` carry across as JSDoc, so the hint your
model reads is the hint your editor shows. A `Literal` or an `Enum` becomes a
string-literal union — narrower than the `// breakfast | lunch | ...` comment a
hand-written file usually settles for.

## Reading it in the browser

`asUiAction` narrows a raw `ui-command` and returns `null` for a command this file
does not declare, because a page and a brain ship separately and an older page
meeting a newer action should ignore it rather than throw. `unhandledUiAction`
goes in the `default` arm, where its `never` parameter is what fails the build:

```tsx
useRTVIClientEvent(
  RTVIEvent.UICommand,
  useCallback(({ command, payload }: UICommandData) => {
    const action = asUiAction(command, payload ?? {});
    if (!action) return;
    switch (action.command) {
      case 'log_meal':
        // `action.payload` is LogMeal here.
        return store.logMeal(action.payload);
      case 'highlight':
        return store.highlight(action.payload.section);
      default:
        return unhandledUiAction(action);
    }
  }, [store]),
);
```

Add `ShowSummary` to the brain, regenerate, and the build stops on that last line:

```
error TS2345: Argument of type '{ command: "show_summary"; payload: ShowSummary; }'
  is not assignable to parameter of type 'never'.
```

## No action field is optional

A Python field with a default is absent from the schema's `required` list, and
the generated *action* interface still declares it as present. That is not a bug
in the reading of `required` — it is the guarantee `Action` makes: **every
declared field is emitted, `None` included, as JSON `null`.** The wire shape is a
function of the class, not of which fields happened to be set on one instance.

So `note: str = ""` becomes `note: string`, and `caption: str | None = None`
becomes `caption: string | null` — always there, sometimes null. Marking either
one `?` would force every reader to handle an absence that cannot occur.

The same guarantee is why nothing here emits zod or any other validator.
Narrowing on `command` is sound on its own: the brain that minted the message is
the brain these types were generated from.

**Events go the other way, so `required` is the truth there.** Your browser builds
the object and pydantic fills the defaults on arrival, so `question: str = ""`
generates `question?: string` — a field the page may leave out. A nested model
both halves reference is generated whole, which is the stricter read and always
valid to send.

## Pointing it at your module

The argument is the module that *declares* your actions — usually the brain
itself, sometimes a separate `actions.py` that both the brain and your tests
import:

```bash
voqalize types backend/brain.py -o frontend/src/actions.gen.ts   # a file path
voqalize types myapp.brain.actions -o src/actions.gen.ts          # or a dotted module
```

A file path is imported under its real package name, so a brain that does
`from .content import FACTS` loads here exactly as it does when it runs.

**What it reads is that module's namespace**, not every `Action` or `AppEvent`
subclass alive in the process. Importing one brain drags in whatever that brain
imports, and a process-wide registry cannot say which app speaks what. Anything
the module names — declared there or imported into it — is in; nothing else is.
That is the same scoping `AppEvents` uses at runtime, for the same reason.

| Flag | What it does |
|---|---|
| `-o`, `--out` | File to write; stdout when omitted. |
| `--union-name` | Name of the action union, `UiAction` by default. |
| `--event-union-name` | Name of the event union, `AppEvent` by default. |
| `--scene SPEC.json` | Instead of a module, write a [Stage Spec](/build/stage/)'s moves as Python (needs `-o`); the same as `voqalize stage gen --py`. |

Rename a union when one frontend talks to more than one brain: everything derived from it
follows, so `--union-name DeskAction` gives you `DeskAction`,
`DESK_ACTION_COMMANDS`, `asDeskAction` and `unhandledDeskAction`.

## Keeping it honest

The output is byte-identical run to run — no timestamp, no set iteration — so the
check is one line in CI:

```bash
voqalize types backend/brain.py -o frontend/src/actions.gen.ts
git diff --exit-code frontend/src/actions.gen.ts
```

A brain whose types were not regenerated fails there rather than in a browser.

Keep the generated file to itself and import from it. Client-only fields — a
`fresh?: boolean` your reducer sets, an `id` you mint on arrival — belong in your
own view models, which can extend the generated ones. Editing the generated file
works exactly until the next regeneration.

## Read next

- [Test the brain](/build/testing/): drive actions and events over the real wire.
- [Actions](/build/brain/actions/): declaring the payloads this generates from.
- [Context and history](/build/brain/context/): the inbound half these events serve.
